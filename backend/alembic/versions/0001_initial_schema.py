"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-18

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "engagements",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("platform", sa.String(20), nullable=False, server_default="bbs"),
        sa.Column("scope_urls", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("agent_config", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("llm_budget_usd", sa.Float, nullable=False, server_default="5.0"),
        sa.Column("llm_spent_usd", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "findings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("engagement_id", sa.String(36), sa.ForeignKey("engagements.id"), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("cvss_score", sa.Float, nullable=True),
        sa.Column("cvss_vector", sa.String(200), nullable=True),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("reproducer", sa.Text, nullable=False, server_default=""),
        sa.Column("impact", sa.Text, nullable=False, server_default=""),
        sa.Column("http_transcript", sa.Text, nullable=False, server_default=""),
        sa.Column("report_md", sa.Text, nullable=False, server_default=""),
        sa.Column("validator_reasoning", sa.Text, nullable=False, server_default=""),
        sa.Column("dup_similarity", sa.Float, nullable=True),
        sa.Column("chain_ids", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("meta", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("engagement_id", sa.String(36), sa.ForeignKey("engagements.id"), nullable=False),
        sa.Column("agent_name", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("input_data", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("output_data", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("trace", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("llm_tokens_in", sa.Integer, nullable=False, server_default="0"),
        sa.Column("llm_tokens_out", sa.Integer, nullable=False, server_default="0"),
        sa.Column("llm_cost_usd", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime, nullable=True),
        sa.Column("finished_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "assets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("engagement_id", sa.String(36), sa.ForeignKey("engagements.id"), nullable=False),
        sa.Column("host", sa.String(500), nullable=False),
        sa.Column("ip", sa.String(50), nullable=True),
        sa.Column("tech_stack", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("open_ports", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("status_code", sa.Integer, nullable=True),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("is_live", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("meta", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "secrets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("engagement_id", sa.String(36), sa.ForeignKey("engagements.id"), nullable=True),
        sa.Column("source_url", sa.String(2000), nullable=False),
        sa.Column("secret_type", sa.String(100), nullable=False),
        sa.Column("encrypted_value", sa.Text, nullable=False),
        sa.Column("context", sa.Text, nullable=False, server_default=""),
        sa.Column("meta", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_index("ix_findings_engagement_id", "findings", ["engagement_id"])
    op.create_index("ix_findings_status", "findings", ["status"])
    op.create_index("ix_findings_severity", "findings", ["severity"])
    op.create_index("ix_agent_runs_engagement_id", "agent_runs", ["engagement_id"])
    op.create_index("ix_assets_engagement_id", "assets", ["engagement_id"])


def downgrade() -> None:
    op.drop_table("secrets")
    op.drop_table("assets")
    op.drop_table("agent_runs")
    op.drop_table("findings")
    op.drop_table("engagements")
