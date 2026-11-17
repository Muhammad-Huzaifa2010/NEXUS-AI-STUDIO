import json
import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.database import get_task, list_tasks, save_task, persistence_enabled
from app.schemas.tasks import TaskRequest, TaskResponse
from app.workflows.agent_graph import agent_graph

router = APIRouter()
logger = logging.getLogger(__name__)


def encode_sse(event_name: str, data: dict) -> str:
    """Encode a Python dictionary as a Server-Sent Event."""
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event_name}\ndata: {payload}\n\n"


def ensure_ai_configured():
    if not settings.groq_api_key:
        raise HTTPException(
            status_code=503,
            detail="AI service is not configured. Add GROQ_API_KEY to backend/.env.",
        )


@router.post("/run", response_model=TaskResponse)
async def run_task(task: TaskRequest):
    ensure_ai_configured()
    try:
        result = await agent_graph.ainvoke({"request": task.request})
        task_id = await save_task(task.request, result, status="completed")
        return TaskResponse(
            task_id=task_id,
            status="completed",
            workflow=result.get("workflow", "unknown"),
            selected_agent=result.get("selected_agent", ""),
            response=result.get("response", ""),
            video_url=result.get("video_url"),
            video_filename=result.get("video_filename"),
            tool_events=result.get("tool_events", []),
            activity_events=result.get("activity_events", []),
        )
    except HTTPException:
        raise
    except Exception as error:
        logger.exception("NEXUS task execution failed")
        try:
            await save_task(
                task.request,
                {"response": "Task execution failed."},
                status="failed",
            )
        except Exception:
            logger.exception("Unable to save failed task history.")
        raise HTTPException(
            status_code=500,
            detail="The task could not be completed. Check the backend logs for details.",
        ) from error


@router.post("/stream")
async def stream_task(task: TaskRequest):
    ensure_ai_configured()

    async def event_generator():
        yield encode_sse("status", {
            "status": "started",
            "message": "NEXUS task execution started.",
        })

        try:
            final_result = None
            async for mode, chunk in agent_graph.astream(
                {"request": task.request},
                stream_mode=["custom", "values"],
            ):
                if mode == "custom":
                    yield encode_sse("activity", chunk)
                elif mode == "values" and "response" in chunk:
                    final_result = {
                        "status": "completed",
                        "workflow": chunk.get("workflow", "unknown"),
                        "selected_agent": chunk.get("selected_agent", ""),
                        "response": chunk.get("response", ""),
                        "video_url": chunk.get("video_url"),
                        "video_filename": chunk.get("video_filename"),
                        "tool_events": chunk.get("tool_events", []),
                        "activity_events": chunk.get("activity_events", []),
                    }

            if final_result is None:
                raise RuntimeError("The agent graph returned no final result.")

            final_result["task_id"] = await save_task(task.request, final_result, status="completed")
            yield encode_sse("result", final_result)
            yield encode_sse("status", {
                "status": "completed",
                "message": "NEXUS task execution completed.",
            })
        except Exception:
            logger.exception("NEXUS streaming task failed")
            try:
                await save_task(task.request, {"response": "Task execution failed."}, status="failed")
            except Exception:
                logger.exception("Unable to save failed task history.")
            yield encode_sse("error", {
                "status": "failed",
                "message": "The task failed. Check the backend logs for details.",
            })

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/history")
async def task_history(limit: int = Query(default=50, ge=1, le=100)):
    return {
        "items": await list_tasks(limit),
        "persistence_enabled": persistence_enabled(),
    }


@router.get("/history/{task_id}")
async def task_history_detail(task_id: str):
    item = await get_task(task_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    return item
