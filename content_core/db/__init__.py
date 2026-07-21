"""
content_core.db
===============
Session management + convenience recorders.

Engine selection: DATABASE_URL env var; defaults to a local SQLite file so the
platform needs zero database infrastructure out of the box, while remaining
Postgres-compatible (`DATABASE_URL=postgresql+psycopg://...`).

Public helpers:
    init_db()                       create tables (idempotent)
    get_session()                   context-managed Session
    record_report(report)           persist a Workflow RunReport
    record_llm_usage(**fields)      persist one LLM call's usage/cost
    usage_summary(days)             aggregate tokens/cost per provider+model
    recent_runs(limit)              latest workflow runs with steps
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker, joinedload

from .models import Base, WorkflowRun, StepRecord, LLMUsage, GeneratedContent
from . import models_phase5  # register eval/benchmark/approval tables
from . import models_phase6  # register content_performance table

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

def _current_url() -> str:
    return os.getenv("DATABASE_URL", "sqlite:///content_core.db")

_engine = None
_Session = None

def _ensure_engine():
    global _engine, _Session
    url = _current_url()
    if _engine is None or str(_engine.url) != url:
        _engine = create_engine(url, future=True)
        _Session = sessionmaker(bind=_engine, future=True, expire_on_commit=False)
    return _engine, _Session


def init_db() -> None:
    """Create all tables if they don't exist. Safe to call repeatedly."""
    engine, _ = _ensure_engine()
    Base.metadata.create_all(engine)


@contextmanager
def get_session():
    _, Session = _ensure_engine()
    s = Session()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


# ── Recorders ──────────────────────────────────────────────────────────────────

def record_report(report) -> int:
    """Persist a content_core.workflow.RunReport. Returns the run id."""
    init_db()
    with get_session() as s:
        run = WorkflowRun(
            workflow=report.workflow,
            aborted=report.aborted,
            duration_s=sum(r.duration_s for r in report.results),
        )
        for r in report.results:
            run.steps.append(StepRecord(
                name=r.name, status=r.status, attempts=r.attempts,
                duration_s=r.duration_s, error=r.error,
            ))
        s.add(run)
        s.flush()
        return run.id


def record_llm_usage(*, provider: str, model: str, input_tokens: int,
                     output_tokens: int, latency_s: float, cost_usd: float,
                     caller: str | None = None) -> None:
    init_db()
    with get_session() as s:
        s.add(LLMUsage(
            provider=provider, model=model,
            input_tokens=input_tokens, output_tokens=output_tokens,
            latency_s=latency_s, cost_usd=cost_usd, caller=caller,
        ))


def record_content(*, channel: str, kind: str, title: str | None = None,
                   path_or_ref: str | None = None, meta: str | None = None) -> None:
    init_db()
    with get_session() as s:
        s.add(GeneratedContent(channel=channel, kind=kind, title=title,
                               path_or_ref=path_or_ref, meta=meta))


# ── Queries (consumed by the API / dashboard) ─────────────────────────────────

def usage_summary(days: int = 30) -> list[dict]:
    init_db()
    since = datetime.now(timezone.utc) - timedelta(days=days)
    with get_session() as s:
        rows = s.execute(
            select(
                LLMUsage.provider, LLMUsage.model,
                func.count(LLMUsage.id),
                func.sum(LLMUsage.input_tokens),
                func.sum(LLMUsage.output_tokens),
                func.sum(LLMUsage.cost_usd),
                func.avg(LLMUsage.latency_s),
            ).where(LLMUsage.at >= since)
             .group_by(LLMUsage.provider, LLMUsage.model)
        ).all()
    return [
        {
            "provider": p, "model": m, "calls": c,
            "input_tokens": int(it or 0), "output_tokens": int(ot or 0),
            "cost_usd": round(float(cost or 0.0), 4),
            "avg_latency_s": round(float(lat or 0.0), 3),
        }
        for p, m, c, it, ot, cost, lat in rows
    ]


def recent_runs(limit: int = 20) -> list[dict]:
    init_db()
    with get_session() as s:
        runs = s.execute(
            select(WorkflowRun)
            .options(joinedload(WorkflowRun.steps))
            .order_by(WorkflowRun.started_at.desc())
            .limit(limit)
        ).unique().scalars().all()
    return [
        {
            "id": r.id, "workflow": r.workflow,
            "started_at": r.started_at.isoformat(),
            "aborted": r.aborted, "duration_s": round(r.duration_s, 2),
            "steps": [
                {"name": st.name, "status": st.status, "attempts": st.attempts,
                 "duration_s": round(st.duration_s, 2), "error": st.error}
                for st in r.steps
            ],
        }
        for r in runs
    ]
