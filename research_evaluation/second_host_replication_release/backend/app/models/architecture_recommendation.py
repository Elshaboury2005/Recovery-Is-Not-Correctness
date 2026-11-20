"""Persisted explainable architecture recommendations."""

import uuid

from sqlalchemy import ForeignKey, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class ArchitectureRecommendation(Base):
    __tablename__ = "architecture_recommendations"

    workload_definition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workload_definitions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    benchmark_campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("benchmark_campaigns.id", ondelete="SET NULL"), nullable=True, index=True
    )
    optimization_goal: Mapped[str] = mapped_column(String(32), nullable=False)
    selected_engine: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    resource_constraints: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
