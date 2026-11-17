import os
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter()

PROJECT_ROOT = Path(__file__).resolve().parents[4]
STORAGE_DIR = Path(os.getenv("NEXUS_STORAGE_DIR", str(PROJECT_ROOT / "storage")))
VIDEO_DIR = STORAGE_DIR / "videos"


@router.get("/{filename}")
async def serve_video(filename: str):
    if not re.fullmatch(r"[a-f0-9]{32}\.mp4", filename):
        raise HTTPException(status_code=404, detail="Video not found.")

    video_path = VIDEO_DIR / filename

    if not video_path.is_file():
        raise HTTPException(status_code=404, detail="Video not found.")

    return FileResponse(
        path=video_path,
        media_type="video/mp4",
        headers={"Cache-Control": "public, max-age=3600"},
    )
