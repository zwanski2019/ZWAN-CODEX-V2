from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.db.models import Asset, Secret

router = APIRouter(prefix="/loot", tags=["loot"])


class AssetOut(BaseModel):
    id: str
    engagement_id: str
    host: str
    ip: str | None
    tech_stack: list
    status_code: int | None
    title: str | None
    is_live: bool

    class Config:
        from_attributes = True


class SecretOut(BaseModel):
    id: str
    engagement_id: str | None
    source_url: str
    secret_type: str
    context: str

    class Config:
        from_attributes = True


@router.get("/assets", response_model=list[AssetOut])
async def list_assets(
    engagement_id: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[Asset]:
    q = select(Asset)
    if engagement_id:
        q = q.where(Asset.engagement_id == engagement_id)
    result = await db.execute(q.order_by(Asset.created_at.desc()).limit(500))
    return list(result.scalars().all())


@router.get("/secrets", response_model=list[SecretOut])
async def list_secrets(
    engagement_id: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[Secret]:
    q = select(Secret)
    if engagement_id:
        q = q.where(Secret.engagement_id == engagement_id)
    result = await db.execute(q.order_by(Secret.created_at.desc()).limit(500))
    return list(result.scalars().all())
