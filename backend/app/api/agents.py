from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.db.models import AgentRun

router = APIRouter(prefix="/agents", tags=["agents"])


class AgentRunOut(BaseModel):
    id: str
    engagement_id: str
    agent_name: str
    status: str
    llm_tokens_in: int
    llm_tokens_out: int
    llm_cost_usd: float
    error: str | None

    class Config:
        from_attributes = True


@router.get("/runs", response_model=list[AgentRunOut])
async def list_runs(
    engagement_id: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[AgentRun]:
    q = select(AgentRun)
    if engagement_id:
        q = q.where(AgentRun.engagement_id == engagement_id)
    result = await db.execute(q.order_by(AgentRun.created_at.desc()).limit(200))
    return list(result.scalars().all())
