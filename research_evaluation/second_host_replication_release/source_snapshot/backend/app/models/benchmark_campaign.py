"""Durable benchmark campaign and per-run evidence records."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class BenchmarkCampaign(Base):
    """A controlled comparison of one workload across engine configurations."""

    __tablename__ = "benchmark_campaigns"

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    workload_definition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workload_definitions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    dataset_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dataset_profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="planned", index=True)
    repetitions: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    warmup_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    plan: Mapped[dict] = mapped_column(JSON, nullable=False)
    fairness_contract: Mapped[dict] = mapped_column(JSON, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    runs: Mapped[list["BenchmarkRun"]] = relationship(
        "BenchmarkRun", back_populates="campaign", cascade="all, delete-orphan", order_by="BenchmarkRun.created_at"
    )


class BenchmarkRun(Base):
    """One warm-up or measured attempt, including missing-evidence fields."""

    __tablename__ = "benchmark_runs"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("benchmark_campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    engine: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    repetition: Mapped[int] = mapped_column(Integer, nullable=False)
    is_warmup: Mapped[bool] = mapped_column(nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued", index=True)
    configuration: Mapped[dict] = mapped_column(JSON, nullable=False)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    resource_metrics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    correctness: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    software_versions: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    campaign: Mapped[BenchmarkCampaign] = relationship("BenchmarkCampaign", back_populates="runs")
