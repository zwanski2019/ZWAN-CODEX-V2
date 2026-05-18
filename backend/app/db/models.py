from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Platform(str, Enum):
    BBS = "bbs"
    H1 = "h1"
    BUGCROWD = "bugcrowd"
    HACKENPROOF = "hackenproof"


class FindingStatus(str, Enum):
    PENDING = "pending"
    VALID = "valid"
    KILLED = "killed"
    NEEDS_REVIEW = "needs_review"
    SUBMITTED = "submitted"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class AgentStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class Engagement(Base):
    __tablename__ = "engagements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[Platform] = mapped_column(String(20), nullable=False, default=Platform.BBS)
    scope_urls: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    agent_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    llm_budget_usd: Mapped[float] = mapped_column(Float, nullable=False, default=5.0)
    llm_spent_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    findings: Mapped[list[Finding]] = relationship("Finding", back_populates="engagement")
    agent_runs: Mapped[list[AgentRun]] = relationship("AgentRun", back_populates="engagement")
    assets: Mapped[list[Asset]] = relationship("Asset", back_populates="engagement")


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    engagement_id: Mapped[str] = mapped_column(ForeignKey("engagements.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    severity: Mapped[Severity] = mapped_column(String(20), nullable=False)
    status: Mapped[FindingStatus] = mapped_column(String(20), nullable=False, default=FindingStatus.PENDING)
    cvss_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    cvss_vector: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reproducer: Mapped[str] = mapped_column(Text, nullable=False, default="")
    impact: Mapped[str] = mapped_column(Text, nullable=False, default="")
    http_transcript: Mapped[str] = mapped_column(Text, nullable=False, default="")
    report_md: Mapped[str] = mapped_column(Text, nullable=False, default="")
    validator_reasoning: Mapped[str] = mapped_column(Text, nullable=False, default="")
    dup_similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    chain_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    meta: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    engagement: Mapped[Engagement] = relationship("Engagement", back_populates="findings")


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    engagement_id: Mapped[str] = mapped_column(ForeignKey("engagements.id"), nullable=False)
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[AgentStatus] = mapped_column(String(20), nullable=False, default=AgentStatus.QUEUED)
    input_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    output_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    trace: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    llm_tokens_in: Mapped[int] = mapped_column(nullable=False, default=0)
    llm_tokens_out: Mapped[int] = mapped_column(nullable=False, default=0)
    llm_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    engagement: Mapped[Engagement] = relationship("Engagement", back_populates="agent_runs")


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    engagement_id: Mapped[str] = mapped_column(ForeignKey("engagements.id"), nullable=False)
    host: Mapped[str] = mapped_column(String(500), nullable=False)
    ip: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tech_stack: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    open_ports: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status_code: Mapped[int | None] = mapped_column(nullable=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_live: Mapped[bool] = mapped_column(nullable=False, default=True)
    meta: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    engagement: Mapped[Engagement] = relationship("Engagement", back_populates="assets")


class Secret(Base):
    __tablename__ = "secrets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    engagement_id: Mapped[str | None] = mapped_column(ForeignKey("engagements.id"), nullable=True)
    source_url: Mapped[str] = mapped_column(String(2000), nullable=False)
    secret_type: Mapped[str] = mapped_column(String(100), nullable=False)
    # value stored Fernet-encrypted
    encrypted_value: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[str] = mapped_column(Text, nullable=False, default="")
    meta: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AppSetting(Base):
    """Persistent key-value settings store. Sensitive values are Fernet-encrypted."""
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_sensitive: Mapped[bool] = mapped_column(nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
