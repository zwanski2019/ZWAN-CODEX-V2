from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.db.models import Finding, FindingStatus, Severity

router = APIRouter(prefix="/findings", tags=["findings"])


class FindingOut(BaseModel):
    id: str
    engagement_id: str
    title: str
    severity: str
    status: str
    cvss_score: float | None
    description: str
    reproducer: str
    impact: str
    report_md: str
    validator_reasoning: str
    dup_similarity: float | None

    class Config:
        from_attributes = True


class FindingUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    reproducer: str | None = None
    impact: str | None = None
    report_md: str | None = None
    status: FindingStatus | None = None


@router.get("/", response_model=list[FindingOut])
async def list_findings(
    engagement_id: str | None = None,
    status: str | None = None,
    severity: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[Finding]:
    q = select(Finding)
    if engagement_id:
        q = q.where(Finding.engagement_id == engagement_id)
    if status:
        q = q.where(Finding.status == status)
    if severity:
        q = q.where(Finding.severity == severity)
    result = await db.execute(q.order_by(Finding.created_at.desc()))
    return list(result.scalars().all())


@router.get("/{finding_id}", response_model=FindingOut)
async def get_finding(finding_id: str, db: AsyncSession = Depends(get_db)) -> Finding:
    f = await db.get(Finding, finding_id)
    if not f:
        raise HTTPException(status_code=404, detail="Finding not found")
    return f


@router.patch("/{finding_id}", response_model=FindingOut)
async def update_finding(
    finding_id: str,
    body: FindingUpdate,
    db: AsyncSession = Depends(get_db),
) -> Finding:
    f = await db.get(Finding, finding_id)
    if not f:
        raise HTTPException(status_code=404, detail="Finding not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(f, k, v)
    await db.commit()
    await db.refresh(f)
    return f
