from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.health import router as health_router
from app.api.routes.tasks import router as tasks_router
from app.api.routes.videos import router as videos_router
from app.core.config import settings
from app.database import close_database, init_database


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_database()
    try:
        yield
    finally:
        await close_database()


app = FastAPI(
    lifespan=lifespan,
    title=settings.app_name,
    version=settings.app_version,
    description="A hybrid autonomous AI agent platform.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_url,
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {
        "message": "Welcome to NEXUS AI STUDIO",
        "version": settings.app_version,
        "status": "online",
    }


app.include_router(health_router, prefix="/api", tags=["System"])
app.include_router(tasks_router, prefix="/api/tasks", tags=["AI Tasks"])
app.include_router(videos_router, prefix="/api/videos", tags=["Videos"])
