"""Durable safe-reconfiguration proposal and approval records."""

import uuid

from sqlalchemy import ForeignKey, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class ReconfigurationOperation(Base):
    __tablename__ = "reconfiguration_operations"

    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("architecture_recommendations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    current_engine: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_engine: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="proposed", index=True)
    requested_overrides: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    preflight_evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    audit_events: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    execution_result: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
