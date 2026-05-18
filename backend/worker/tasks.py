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


async def run_single_agent(ctx: dict, engagement_id: str, agent_name: str) -> dict:
    """Run a single named agent against an engagement (e.g. zeroday_scanner)."""
    # Import all agents so registry is populated before we look up agent_name
    import app.agents.recon  # noqa: F401
    import app.agents.js_miner  # noqa: F401
    import app.agents.oauth_chain  # noqa: F401
    import app.agents.desync  # noqa: F401
    import app.agents.race  # noqa: F401
    import app.agents.ssrf  # noqa: F401
    import app.agents.agentic_target  # noqa: F401
    import app.agents.chain_hunter  # noqa: F401
    import app.agents.validator  # noqa: F401
    import app.agents.report  # noqa: F401
    import app.agents.zeroday_scanner  # noqa: F401
    from app.agents.orchestrator import AGENT_REGISTRY
    from app.llm.router import LLMRouter

    async with AsyncSessionLocal() as db:
        eng = await db.get(Engagement, engagement_id)
        if not eng:
            return {"error": f"Engagement {engagement_id} not found"}

        agent_cls = AGENT_REGISTRY.get(agent_name)
        if not agent_cls:
            return {"error": f"Agent '{agent_name}' not registered. Available: {list(AGENT_REGISTRY)}"}

        llm = LLMRouter(engagement_id=eng.id, budget_usd=eng.llm_budget_usd)
        agent = agent_cls(engagement=eng, db=db, llm=llm)
        result = await agent.run()

        eng.llm_spent_usd = llm.spent
        await db.commit()

    return {"engagement_id": engagement_id, "agent": agent_name, "result": result}


async def startup(ctx: dict) -> None:
    pass


async def shutdown(ctx: dict) -> None:
    pass


class WorkerSettings:
    functions = [hunt_engagement, run_single_agent]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 4
    job_timeout = 7200  # 2 h max per hunt
