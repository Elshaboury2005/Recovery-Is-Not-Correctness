"""Add safe reconfiguration proposal and approval state."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_add_reconfiguration_operations"
down_revision: Union[str, None] = "0010_add_architecture_recommendations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reconfiguration_operations",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("recommendation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("architecture_recommendations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("current_engine", sa.String(length=32), nullable=True),
        sa.Column("target_engine", sa.String(length=32), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False, server_default="proposed"),
        sa.Column("requested_overrides", sa.JSON(), nullable=False),
        sa.Column("preflight_evidence", sa.JSON(), nullable=False),
        sa.Column("audit_events", sa.JSON(), nullable=False),
        sa.Column("execution_result", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reconfiguration_operations_recommendation_id", "reconfiguration_operations", ["recommendation_id"])
    op.create_index("ix_reconfiguration_operations_state", "reconfiguration_operations", ["state"])


def downgrade() -> None:
    op.drop_index("ix_reconfiguration_operations_state", table_name="reconfiguration_operations")
    op.drop_index("ix_reconfiguration_operations_recommendation_id", table_name="reconfiguration_operations")
    op.drop_table("reconfiguration_operations")
