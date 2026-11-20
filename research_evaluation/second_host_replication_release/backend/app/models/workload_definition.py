"""Persisted workload classification definition and result."""

import uuid

from sqlalchemy import ForeignKey, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class WorkloadDefinition(Base):
    __tablename__ = "workload_definitions"

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    pipeline_yaml: Mapped[str] = mapped_column(Text, nullable=False)
    dataset_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dataset_profiles.id", ondelete="SET NULL"), nullable=True
    )
    constraints: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    classification: Mapped[dict] = mapped_column(JSON, nullable=False)
