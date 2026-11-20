"""Add durable benchmark campaigns and per-run evidence."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_add_benchmark_campaigns"
down_revision: Union[str, None] = "0008_add_workload_definitions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _common_columns() -> list[sa.Column]:
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "benchmark_campaigns",
        *_common_columns(),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("workload_definition_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workload_definitions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("dataset_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("dataset_profiles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="planned"),
        sa.Column("repetitions", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("warmup_runs", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("plan", sa.JSON(), nullable=False),
        sa.Column("fairness_contract", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_benchmark_campaigns_name", "benchmark_campaigns", ["name"])
    op.create_index("ix_benchmark_campaigns_workload_definition_id", "benchmark_campaigns", ["workload_definition_id"])
    op.create_index("ix_benchmark_campaigns_dataset_profile_id", "benchmark_campaigns", ["dataset_profile_id"])
    op.create_index("ix_benchmark_campaigns_status", "benchmark_campaigns", ["status"])

    op.create_table(
        "benchmark_runs",
        *_common_columns(),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("benchmark_campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("engine", sa.String(length=32), nullable=False),
        sa.Column("repetition", sa.Integer(), nullable=False),
        sa.Column("is_warmup", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("resource_metrics", sa.JSON(), nullable=False),
        sa.Column("correctness", sa.JSON(), nullable=False),
        sa.Column("software_versions", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_benchmark_runs_campaign_id", "benchmark_runs", ["campaign_id"])
    op.create_index("ix_benchmark_runs_engine", "benchmark_runs", ["engine"])
    op.create_index("ix_benchmark_runs_status", "benchmark_runs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_benchmark_runs_status", table_name="benchmark_runs")
    op.drop_index("ix_benchmark_runs_engine", table_name="benchmark_runs")
    op.drop_index("ix_benchmark_runs_campaign_id", table_name="benchmark_runs")
    op.drop_table("benchmark_runs")
    op.drop_index("ix_benchmark_campaigns_status", table_name="benchmark_campaigns")
    op.drop_index("ix_benchmark_campaigns_dataset_profile_id", table_name="benchmark_campaigns")
    op.drop_index("ix_benchmark_campaigns_workload_definition_id", table_name="benchmark_campaigns")
    op.drop_index("ix_benchmark_campaigns_name", table_name="benchmark_campaigns")
    op.drop_table("benchmark_campaigns")
