"""Optional PostgreSQL persistence for NEXUS task history."""

import json
import logging
from typing import Any
from uuid import UUID

try:
    import asyncpg
except ImportError:  # Allows local development without PostgreSQL extras installed.
    asyncpg = None

from app.core.config import settings

logger = logging.getLogger(__name__)
_pool: Any = None


async def init_database() -> None:
    """Connect to PostgreSQL and create the task-history table if configured."""
    global _pool
    if not settings.database_url:
        logger.info("DATABASE_URL is not configured; task history persistence is disabled.")
        return
    if asyncpg is None:
        raise RuntimeError("Install the asyncpg package to enable PostgreSQL persistence.")

    _pool = await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=1,
        max_size=10,
        command_timeout=30,
    )
    async with _pool.acquire() as connection:
        await connection.execute(
            """
            CREATE TABLE IF NOT EXISTS task_history (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                request TEXT NOT NULL,
                status VARCHAR(24) NOT NULL,
                workflow VARCHAR(80) NOT NULL DEFAULT 'unknown',
                selected_agent TEXT NOT NULL DEFAULT '',
                response TEXT NOT NULL DEFAULT '',
                video_url TEXT,
                video_filename VARCHAR(80),
                tool_events JSONB NOT NULL DEFAULT '[]'::jsonb,
                activity_events JSONB NOT NULL DEFAULT '[]'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    logger.info("PostgreSQL task history is ready.")


async def close_database() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def database_is_ready() -> bool:
    if _pool is None:
        return False
    try:
        async with _pool.acquire() as connection:
            return await connection.fetchval("SELECT 1") == 1
    except Exception:
        logger.exception("PostgreSQL health check failed.")
        return False


def persistence_enabled() -> bool:
    return _pool is not None


async def save_task(request: str, result: dict[str, Any], status: str = "completed") -> str | None:
    if _pool is None:
        return None

    try:
        async with _pool.acquire() as connection:
            task_id = await connection.fetchval(
                """
                INSERT INTO task_history (
                    request, status, workflow, selected_agent, response,
                    video_url, video_filename, tool_events, activity_events
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb)
                RETURNING id::text
                """,
                request,
                status,
                str(result.get("workflow", "unknown")),
                str(result.get("selected_agent", "")),
                str(result.get("response", "")),
                result.get("video_url"),
                result.get("video_filename"),
                json.dumps(result.get("tool_events") or [], ensure_ascii=False),
                json.dumps(result.get("activity_events") or [], ensure_ascii=False),
            )
        return str(task_id)
    except Exception:
        logger.exception("Unable to persist NEXUS task history; task result remains available.")
        return None


def _record_to_dict(record: Any) -> dict[str, Any]:
    item = dict(record)
    item["id"] = str(item["id"])
    item["created_at"] = item["created_at"].isoformat()
    for field in ("tool_events", "activity_events"):
        value = item.get(field)
        if isinstance(value, str):
            item[field] = json.loads(value)
    return item


async def list_tasks(limit: int = 50) -> list[dict[str, Any]]:
    if _pool is None:
        return []
    async with _pool.acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT id, request, status, workflow, selected_agent, response,
                   video_url, video_filename, tool_events, activity_events, created_at
            FROM task_history
            ORDER BY created_at DESC
            LIMIT $1
            """,
            limit,
        )
    return [_record_to_dict(row) for row in rows]


async def get_task(task_id: str) -> dict[str, Any] | None:
    if _pool is None:
        return None
    try:
        parsed_id = UUID(task_id)
    except ValueError:
        return None
    async with _pool.acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT id, request, status, workflow, selected_agent, response,
                   video_url, video_filename, tool_events, activity_events, created_at
            FROM task_history WHERE id = $1
            """,
            parsed_id,
        )
    return _record_to_dict(row) if row else None
