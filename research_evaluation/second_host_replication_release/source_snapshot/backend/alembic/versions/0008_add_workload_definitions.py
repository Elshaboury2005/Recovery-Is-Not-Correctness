"""Add persisted workload classification results."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_add_workload_definitions"
down_revision: Union[str, None] = "0007_add_dataset_profiles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workload_definitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("pipeline_yaml", sa.Text(), nullable=False),
        sa.Column("dataset_profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("dataset_profiles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("constraints", sa.JSON(), nullable=True),
        sa.Column("classification", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workload_definitions_name", "workload_definitions", ["name"])


def downgrade() -> None:
    op.drop_index("ix_workload_definitions_name", table_name="workload_definitions")
    op.drop_table("workload_definitions")
