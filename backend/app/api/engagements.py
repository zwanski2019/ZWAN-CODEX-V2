from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.base import get_db
from app.db.models import Engagement, Platform

router = APIRouter(prefix="/engagements", tags=["engagements"])


class EngagementCreate(BaseModel):
    name: str
    platform: Platform = Platform.BBS
    scope_urls: list[str]
    agent_config: dict = {}
    llm_budget_usd: float = 5.0


class EngagementOut(BaseModel):
    id: str
    name: str
    platform: str
    scope_urls: list[str]
    llm_budget_usd: float
    llm_spent_usd: float

    class Config:
        from_attributes = True


@router.post("/", response_model=EngagementOut, status_code=201)
async def create_engagement(
    body: EngagementCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Engagement:
    eng = Engagement(
        id=str(uuid.uuid4()),
        name=body.name,
        platform=body.platform,
        scope_urls=body.scope_urls,
        agent_config=body.agent_config,
        llm_budget_usd=body.llm_budget_usd,
    )
    db.add(eng)
    await db.commit()
    await db.refresh(eng)
    return eng


@router.get("/", response_model=list[EngagementOut])
async def list_engagements(db: Annotated[AsyncSession, Depends(get_db)]) -> list[Engagement]:
    result = await db.execute(select(Engagement).order_by(Engagement.created_at.desc()))
    return list(result.scalars().all())


@router.delete("/{engagement_id}", status_code=204)
async def delete_engagement(
    engagement_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    eng = await db.get(Engagement, engagement_id)
    if not eng:
        raise HTTPException(status_code=404, detail="Engagement not found")
    await db.delete(eng)
    await db.commit()


@router.get("/{engagement_id}", response_model=EngagementOut)
async def get_engagement(
    engagement_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Engagement:
    eng = await db.get(Engagement, engagement_id)
    if not eng:
        raise HTTPException(status_code=404, detail="Engagement not found")
    return eng


@router.post("/{engagement_id}/agents/zeroday")
async def start_zeroday_scan(
    engagement_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Enqueue just the ZeroDayScannerAgent for a targeted zero-day scan."""
    eng = await db.get(Engagement, engagement_id)
    if not eng:
        raise HTTPException(status_code=404, detail="Engagement not found")

    from arq import create_pool
    from arq.connections import RedisSettings

    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    await pool.enqueue_job("run_single_agent", engagement_id, "zeroday_scanner")
    await pool.aclose()
    return {"queued": True, "engagement_id": engagement_id, "agent": "zeroday_scanner"}
