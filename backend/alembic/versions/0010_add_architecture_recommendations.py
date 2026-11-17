"""Add persisted evidence-gated architecture recommendations."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_add_architecture_recommendations"
down_revision: Union[str, None] = "0009_add_benchmark_campaigns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "architecture_recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("workload_definition_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workload_definitions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("benchmark_campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("benchmark_campaigns.id", ondelete="SET NULL"), nullable=True),
        sa.Column("optimization_goal", sa.String(length=32), nullable=False),
        sa.Column("selected_engine", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=48), nullable=False),
        sa.Column("resource_constraints", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_architecture_recommendations_workload_definition_id", "architecture_recommendations", ["workload_definition_id"])
    op.create_index("ix_architecture_recommendations_benchmark_campaign_id", "architecture_recommendations", ["benchmark_campaign_id"])
    op.create_index("ix_architecture_recommendations_status", "architecture_recommendations", ["status"])


def downgrade() -> None:
    op.drop_index("ix_architecture_recommendations_status", table_name="architecture_recommendations")
    op.drop_index("ix_architecture_recommendations_benchmark_campaign_id", table_name="architecture_recommendations")
    op.drop_index("ix_architecture_recommendations_workload_definition_id", table_name="architecture_recommendations")
    op.drop_table("architecture_recommendations")
