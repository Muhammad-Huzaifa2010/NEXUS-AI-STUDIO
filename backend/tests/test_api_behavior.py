import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from pydantic import ValidationError

from app.api.routes.health import health_check
from app.api.routes.tasks import run_task, stream_task
from app.schemas.tasks import TaskRequest


class TaskRequestTests(unittest.TestCase):
    def test_strips_surrounding_whitespace(self):
        task = TaskRequest(request="  summarize this  ")
        self.assertEqual(task.request, "summarize this")

    def test_rejects_whitespace_only_request(self):
        with self.assertRaises(ValidationError):
            TaskRequest(request="   ")


class HealthCheckTests(unittest.IsolatedAsyncioTestCase):
    async def test_reports_database_configuration_separately_from_connection(self):
        with (
            patch("app.api.routes.health.settings.database_url", "postgresql://configured"),
            patch("app.api.routes.health.database_is_ready", new=AsyncMock(return_value=False)),
        ):
            result = await health_check()

        self.assertTrue(result["dependencies"]["database_configured"])
        self.assertFalse(result["dependencies"]["database_connected"])


class FailedTaskHistoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_saves_failed_task_when_agent_execution_raises(self):
        with (
            patch("app.api.routes.tasks.ensure_ai_configured"),
            patch(
                "app.api.routes.tasks.agent_graph.ainvoke",
                new=AsyncMock(side_effect=RuntimeError("model unavailable")),
            ),
            patch("app.api.routes.tasks.save_task", new=AsyncMock()) as save_task,
        ):
            with self.assertLogs("app.api.routes.tasks", level="ERROR"):
                with self.assertRaises(HTTPException) as raised:
                    await run_task(TaskRequest(request="run this task"))

        self.assertEqual(raised.exception.status_code, 500)
        save_task.assert_awaited_once_with(
            "run this task",
            {"response": "Task execution failed."},
            status="failed",
        )


class StreamingCancellationTests(unittest.IsolatedAsyncioTestCase):
    async def test_stream_propagates_cancellation_without_saving_failure(self):
        started = asyncio.Event()

        async def blocking_stream(*args, **kwargs):
            started.set()
            await asyncio.Event().wait()
            yield "custom", {}

        with (
            patch("app.api.routes.tasks.ensure_ai_configured"),
            patch(
                "app.api.routes.tasks.agent_graph.astream",
                new=blocking_stream,
            ),
            patch("app.api.routes.tasks.save_task", new=AsyncMock()) as save_task,
        ):
            response = await stream_task(
                TaskRequest(request="run this task")
            )
            stream = response.body_iterator

            first_event = await anext(stream)
            self.assertIn("event: status", first_event)

            pending_event = asyncio.create_task(anext(stream))
            await asyncio.wait_for(started.wait(), timeout=2)

            pending_event.cancel()

            with self.assertRaises(asyncio.CancelledError):
                await pending_event

            save_task.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
