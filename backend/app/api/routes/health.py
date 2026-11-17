import shutil
from datetime import datetime, timezone

from fastapi import APIRouter

from app.core.config import settings
from app.database import database_is_ready

router = APIRouter()


@router.get("/health")
async def health_check():
    database_ready = await database_is_ready()
    dependencies = {
        "groq_configured": bool(settings.groq_api_key),
        "ffmpeg_available": shutil.which("ffmpeg") is not None,
        "ffprobe_available": shutil.which("ffprobe") is not None,
        "speech_engine_available": any(
            shutil.which(engine) for engine in ("edge-tts", "say", "espeak-ng")
        ),
        "database_configured": bool(settings.database_url),
        "database_connected": database_ready,
    }
    core_ready = dependencies["groq_configured"]
    video_ready = all(
        dependencies[name]
        for name in (
            "ffmpeg_available",
            "ffprobe_available",
            "speech_engine_available",
        )
    )

    return {
        "status": "operational" if core_ready else "degraded",
        "service": "NEXUS AI STUDIO Backend",
        "version": settings.app_version,
        "dependencies": dependencies,
        "capabilities": {
            "ai_tasks": core_ready,
            "video_generation": core_ready and video_ready,
            "task_history": database_ready,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
