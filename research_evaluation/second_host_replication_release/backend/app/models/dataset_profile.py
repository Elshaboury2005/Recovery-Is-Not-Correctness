"""Persisted dataset profiling job and result."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class DatasetProfile(Base):
    """A versioned profile generated from one immutable source observation."""

    __tablename__ = "dataset_profiles"

    dataset_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_uri: Mapped[str] = mapped_column(String(2048), nullable=False)
    format: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued", index=True)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<DatasetProfile id={self.id} name={self.dataset_name!r} status={self.status!r}>"
