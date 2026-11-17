"""Add persisted dataset profiling jobs and results."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_add_dataset_profiles"
down_revision: Union[str, None] = "0006_add_experiment_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dataset_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("dataset_name", sa.String(length=255), nullable=False),
        sa.Column("source_uri", sa.String(length=2048), nullable=False),
        sa.Column("format", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("profile_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dataset_profiles_dataset_name", "dataset_profiles", ["dataset_name"])
    op.create_index("ix_dataset_profiles_status", "dataset_profiles", ["status"])


def downgrade() -> None:
    op.drop_index("ix_dataset_profiles_status", table_name="dataset_profiles")
    op.drop_index("ix_dataset_profiles_dataset_name", table_name="dataset_profiles")
    op.drop_table("dataset_profiles")
