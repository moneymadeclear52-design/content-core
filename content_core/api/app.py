"""
content_core.api.app
====================
The platform's REST service layer. A thin shell over the existing engine:
endpoints construct Workflow runs / LLM calls and return their results —
no business logic lives here.

Async model: long-running generations return a job id immediately
(FastAPI BackgroundTasks + an in-process registry persisted to the DB).
See docs/adr/0002 for why this — and not Celery/Redis — is the right
mechanism at this platform's scale.

Auth: static API key via X-API-Key (env: PLATFORM_API_KEY). If the env var
is unset, auth is disabled (local development). See docs/adr/0004.

Run:
    pip install -e ".[api]"
    uvicorn content_core.api.app:app --reload
Docs:
    http://localhost:8000/docs   (OpenAPI, generated)
"""

from __future__ import annotations

import os
import uuid
import secrets
import threading
from datetime import datetime, timezone
from typing import Optional, Literal

from fastapi import FastAPI, BackgroundTasks, Depends, HTTPException, Header
from pydantic import BaseModel, Field

from content_core import LLMProvider, __version__
from content_core.agents import Director
from content_core.db import init_db, usage_summary, recent_runs

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = FastAPI(
    title="Content Platform API",
    version=__version__,
    description="REST access to the AI content-automation platform: "
                "script generation, multi-agent episode production, "
                "run history, and LLM usage/cost metrics.",
)

_llm = LLMProvider()


# ── Auth ───────────────────────────────────────────────────────────────────────

def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    expected = os.getenv("PLATFORM_API_KEY", "")
    if not expected:
        return  # auth disabled for local development
    if not (x_api_key and secrets.compare_digest(x_api_key, expected)):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


# ── Job registry (in-process; see ADR-0002) ───────────────────────────────────

class Job(BaseModel):
    id: str
    kind: str
    status: Literal["queued", "running", "done", "failed"]
    created_at: str
    result: Optional[dict] = None
    error: Optional[str] = None


_jobs: dict[str, Job] = {}
_jobs_lock = threading.Lock()


def _new_job(kind: str) -> Job:
    job = Job(id=uuid.uuid4().hex[:12], kind=kind, status="queued",
              created_at=datetime.now(timezone.utc).isoformat())
    with _jobs_lock:
        _jobs[job.id] = job
    return job


def _finish(job_id: str, *, result: dict | None = None, error: str | None = None):
    with _jobs_lock:
        job = _jobs[job_id]
        job.status = "failed" if error else "done"
        job.result, job.error = result, error


# ── Request models ─────────────────────────────────────────────────────────────

class ScriptRequest(BaseModel):
    topic: str = Field(..., examples=["The Zodiac cipher finally cracked"])
    channel: str = "RapidReelz"
    duration_sec: int = Field(45, ge=15, le=180)


class EpisodeRequest(BaseModel):
    series_bible: str
    premise: str


# ── Workers ────────────────────────────────────────────────────────────────────

def _run_script_job(job_id: str, req: ScriptRequest):
    with _jobs_lock:
        _jobs[job_id].status = "running"
    try:
        prompt = (
            f"Write a short-form video narration script for '{req.channel}'.\n"
            f"TOPIC: {req.topic}\nTARGET DURATION: ~{req.duration_sec}s.\n"
            "Open with a scroll-stopping hook; end with a payoff + follow CTA. "
            "Script only."
        )
        text = _llm.generate(prompt, max_tokens=800)
        _finish(job_id, result={"script": text})
    except Exception as e:  # noqa: BLE001 — reported through the job record
        _finish(job_id, error=str(e))


def _run_episode_job(job_id: str, req: EpisodeRequest):
    with _jobs_lock:
        _jobs[job_id].status = "running"
    try:
        ep = Director(llm=_llm).produce_episode(req.series_bible, req.premise)
        _finish(job_id, result={
            "script": ep.script, "shot_list": ep.shot_list,
            "audio_notes": ep.audio_notes, "revisions": ep.revisions,
        })
    except Exception as e:  # noqa: BLE001
        _finish(job_id, error=str(e))


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


@app.post("/jobs/script", response_model=Job, dependencies=[Depends(require_api_key)])
def create_script_job(req: ScriptRequest, background: BackgroundTasks) -> Job:
    """Queue a script generation job; poll GET /jobs/{id} for the result."""
    job = _new_job("script")
    background.add_task(_run_script_job, job.id, req)
    return job


@app.post("/jobs/episode", response_model=Job, dependencies=[Depends(require_api_key)])
def create_episode_job(req: EpisodeRequest, background: BackgroundTasks) -> Job:
    """Queue a multi-agent story episode production job."""
    job = _new_job("episode")
    background.add_task(_run_episode_job, job.id, req)
    return job


@app.get("/jobs/{job_id}", response_model=Job, dependencies=[Depends(require_api_key)])
def get_job(job_id: str) -> Job:
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Unknown job id")
    return job


@app.get("/jobs", dependencies=[Depends(require_api_key)])
def list_jobs() -> list[Job]:
    with _jobs_lock:
        return sorted(_jobs.values(), key=lambda j: j.created_at, reverse=True)


@app.get("/runs", dependencies=[Depends(require_api_key)])
def workflow_runs(limit: int = 20) -> list[dict]:
    """Workflow run history with per-step status and timing."""
    return recent_runs(limit=limit)


@app.get("/metrics/usage", dependencies=[Depends(require_api_key)])
def metrics_usage(days: int = 30) -> list[dict]:
    """LLM usage + estimated cost, aggregated per provider and model."""
    return usage_summary(days=days)


@app.on_event("startup")
def _startup():
    init_db()
