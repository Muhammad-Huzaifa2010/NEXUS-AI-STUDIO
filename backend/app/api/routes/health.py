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
        "database_configured": bool(settings.database_url),
        "database_connected": database_ready,
    }
    core_ready = dependencies["groq_configured"]

    return {
        "status": "operational" if core_ready else "degraded",
        "service": "NEXUS AI STUDIO Backend",
        "version": settings.app_version,
        "dependencies": dependencies,
        "capabilities": {
            "ai_tasks": core_ready,
            "task_history": database_ready,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
