"""Arq worker — async task queue backed by Redis."""
from __future__ import annotations

from arq import create_pool
from arq.connections import RedisSettings

from app.config import settings
from app.db.base import AsyncSessionLocal
from app.db.models import Engagement


async def hunt_engagement(ctx: dict, engagement_id: str) -> dict:
    """Main task: run the full agent DAG for an engagement."""
    from app.agents.orchestrator import run_engagement

    async with AsyncSessionLocal() as db:
        eng = await db.get(Engagement, engagement_id)
        if not eng:
            return {"error": f"Engagement {engagement_id} not found"}
        await run_engagement(eng, db)
    return {"engagement_id": engagement_id, "status": "complete"}


async def startup(ctx: dict) -> None:
    pass


async def shutdown(ctx: dict) -> None:
    pass


class WorkerSettings:
    functions = [hunt_engagement]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 4
    job_timeout = 7200  # 2 h max per hunt
