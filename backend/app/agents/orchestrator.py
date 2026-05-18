"""
Runs agents in DAG order for a given engagement.
M1: just fires ReconAgent as a no-op stub. M2+ adds real agents.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Engagement
from app.llm.router import LLMRouter
from app.ws.manager import manager

AGENT_REGISTRY: dict[str, type] = {}


def register_agent(cls: type) -> type:
    AGENT_REGISTRY[cls.name] = cls
    return cls


async def run_engagement(engagement: Engagement, db: AsyncSession) -> None:
    llm = LLMRouter(
        engagement_id=engagement.id,
        budget_usd=engagement.llm_budget_usd,
    )

    enabled = engagement.agent_config.get("enabled_agents", list(AGENT_REGISTRY))

    await manager.broadcast(
        engagement.id,
        {"type": "orchestrator", "data": {"message": "Hunt started", "agents": enabled}},
    )

    for agent_name in enabled:
        cls = AGENT_REGISTRY.get(agent_name)
        if not cls:
            continue
        agent = cls(engagement=engagement, db=db, llm=llm)
        try:
            await agent.run()
        except Exception as exc:
            await manager.broadcast(
                engagement.id,
                {"type": "error", "agent": agent_name, "data": {"message": str(exc)}},
            )

    # Update engagement spend
    engagement.llm_spent_usd = llm.spent
    await db.commit()

    await manager.broadcast(
        engagement.id,
        {"type": "orchestrator", "data": {"message": "Hunt complete", "spent_usd": llm.spent}},
    )
