"""
content_core.db.models_phase5
============================
Additional tables for evaluation, benchmarking, prompts, and approvals.
These are appended to the same Base metadata as models.py (import this module
so the tables register). Kept in a separate file only for review clarity; in
the shipped package they live in models.py.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import String, Integer, Float, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .models import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Prompt(Base):
    __tablename__ = "prompts"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    versions: Mapped[list["PromptVersion"]] = relationship(
        back_populates="prompt", cascade="all, delete-orphan")


class PromptVersion(Base):
    __tablename__ = "prompt_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    prompt_id: Mapped[int] = mapped_column(ForeignKey("prompts.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(32), index=True)
    author: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    prompt: Mapped[Prompt] = relationship(back_populates="versions")


class EvalRun(Base):
    __tablename__ = "eval_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    prompt_name: Mapped[str] = mapped_column(String(120), index=True)
    prompt_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model: Mapped[str] = mapped_column(String(80))
    mean_score: Mapped[float] = mapped_column(Float)
    pass_rate: Mapped[float] = mapped_column(Float)
    results: Mapped[list["EvalResult"]] = relationship(
        back_populates="run", cascade="all, delete-orphan")


class EvalResult(Base):
    __tablename__ = "eval_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("eval_runs.id"), index=True)
    case_id: Mapped[str] = mapped_column(String(120))
    output: Mapped[str] = mapped_column(Text)
    aggregate: Mapped[float] = mapped_column(Float)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    run: Mapped[EvalRun] = relationship(back_populates="results")


class BenchmarkRun(Base):
    __tablename__ = "benchmark_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    prompt_excerpt: Mapped[str] = mapped_column(String(300))
    provider: Mapped[str] = mapped_column(String(30), index=True)
    model: Mapped[str] = mapped_column(String(80), index=True)
    score: Mapped[float] = mapped_column(Float)
    latency_s: Mapped[float] = mapped_column(Float)


class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    workflow: Mapped[str] = mapped_column(String(100), index=True)
    item_ref: Mapped[str] = mapped_column(String(200))     # e.g. job/content id
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)  # pending|approved|rejected
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
