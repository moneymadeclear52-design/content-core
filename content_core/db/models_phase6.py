"""
content_core.db.models_phase6
============================
The content_performance table — one row per published item's measured
performance, tagged with the content features that produced it. This is the
substrate for closed-loop feedback: correlate features → performance →
scoring boosts.

Appended to the same Base metadata (import to register).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import String, Integer, Float, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ContentPerformance(Base):
    __tablename__ = "content_performance"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)

    # Identity
    channel: Mapped[str] = mapped_column(String(60), index=True)
    video_ref: Mapped[str] = mapped_column(String(120), index=True)  # platform id

    # Content features (the levers a pipeline controls)
    category: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)
    format: Mapped[str | None] = mapped_column(String(40), nullable=True)
    originality_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Measured performance (from the platform's analytics API)
    views: Mapped[int] = mapped_column(Integer, default=0)
    watch_time_min: Mapped[float] = mapped_column(Float, default=0.0)
    ctr: Mapped[float] = mapped_column(Float, default=0.0)          # click-through rate 0-1
    likes: Mapped[int] = mapped_column(Integer, default=0)
    retention: Mapped[float] = mapped_column(Float, default=0.0)    # avg % viewed 0-1
