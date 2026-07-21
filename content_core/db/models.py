"""
content_core.db.models
======================
Persistence for platform metadata. SQLite by default (single-operator,
single-writer workload); Postgres-ready via DATABASE_URL — the schema uses
only portable column types, and CI verifies the models against both dialects.

Tables:
    workflow_runs   one row per Workflow.run()
    step_records    one row per step in a run
    llm_usage       one row per LLM call (provider, model, tokens, cost, latency)
    generated_content  produced artifacts (scripts, videos) and their fate
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    String, Integer, Float, Boolean, DateTime, Text, ForeignKey,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    workflow: Mapped[str] = mapped_column(String(100), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    aborted: Mapped[bool] = mapped_column(Boolean, default=False)
    duration_s: Mapped[float] = mapped_column(Float, default=0.0)

    steps: Mapped[list["StepRecord"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class StepRecord(Base):
    __tablename__ = "step_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("workflow_runs.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20))  # ok | skipped | failed
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    duration_s: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    run: Mapped[WorkflowRun] = relationship(back_populates="steps")


class LLMUsage(Base):
    __tablename__ = "llm_usage"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    provider: Mapped[str] = mapped_column(String(30), index=True)
    model: Mapped[str] = mapped_column(String(80), index=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_s: Mapped[float] = mapped_column(Float, default=0.0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    caller: Mapped[str | None] = mapped_column(String(120), nullable=True)


class GeneratedContent(Base):
    __tablename__ = "generated_content"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    channel: Mapped[str] = mapped_column(String(60), index=True)
    kind: Mapped[str] = mapped_column(String(30))  # script | video | thumbnail | episode
    title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    path_or_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    meta: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON blob
