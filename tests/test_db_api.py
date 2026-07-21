"""Tests for content_core.db, telemetry cost math, and the FastAPI layer.
DB tests use an isolated SQLite file; API tests use FastAPI's TestClient with a
mocked LLM. No API keys, no network."""

import os
import importlib

import pytest


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    """Point the db module at a throwaway SQLite file and reload it."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    import content_core.db as db
    importlib.reload(db)
    db.init_db()
    yield db


# ── DB layer ───────────────────────────────────────────────────────────────────

def test_record_and_query_workflow_report(isolated_db):
    from content_core.workflow import Workflow, Step

    def ok(ctx): ctx["x"] = 1
    def boom(ctx): raise RuntimeError("nope")

    report = Workflow("t-wf", [Step("ok", ok), Step("opt", boom, on_error="skip")]).run()
    run_id = isolated_db.record_report(report)
    assert run_id >= 1

    runs = isolated_db.recent_runs()
    assert runs[0]["workflow"] == "t-wf"
    statuses = {s["name"]: s["status"] for s in runs[0]["steps"]}
    assert statuses == {"ok": "ok", "opt": "skipped"}


def test_llm_usage_aggregation(isolated_db):
    isolated_db.record_llm_usage(provider="claude", model="claude-sonnet-4-6",
                                 input_tokens=1000, output_tokens=500,
                                 latency_s=1.2, cost_usd=0.0105)
    isolated_db.record_llm_usage(provider="claude", model="claude-sonnet-4-6",
                                 input_tokens=2000, output_tokens=1000,
                                 latency_s=0.8, cost_usd=0.0210)
    summary = isolated_db.usage_summary(days=1)
    assert len(summary) == 1
    row = summary[0]
    assert row["calls"] == 2
    assert row["input_tokens"] == 3000
    assert row["cost_usd"] == pytest.approx(0.0315, abs=1e-4)


# ── Telemetry cost math ────────────────────────────────────────────────────────

def test_cost_estimation_known_and_unknown_models():
    from content_core.telemetry import estimate_cost_usd
    # claude-sonnet-4-6: $3/M in, $15/M out
    assert estimate_cost_usd("claude-sonnet-4-6", 1_000_000, 0) == pytest.approx(3.0)
    assert estimate_cost_usd("claude-sonnet-4-6", 0, 1_000_000) == pytest.approx(15.0)
    # unknown model falls back to a nonzero conservative estimate
    assert estimate_cost_usd("mystery-model", 1_000_000, 0) > 0


def test_token_extraction_shapes():
    from content_core.telemetry import extract_tokens

    class U: input_tokens = 11; output_tokens = 7
    class R: usage = U()
    assert extract_tokens("claude", R()) == (11, 7)

    class UO: prompt_tokens = 5; completion_tokens = 3
    class RO: usage = UO()
    assert extract_tokens("openai", RO()) == (5, 3)

    assert extract_tokens("claude", object()) == (0, 0)  # defensive default


# ── API layer ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def client(isolated_db, monkeypatch):
    monkeypatch.delenv("PLATFORM_API_KEY", raising=False)
    import content_core.api.app as appmod
    importlib.reload(appmod)
    # Mock the LLM so jobs complete without network
    class FakeLLM:
        def generate(self, prompt, **kw): return "FAKE SCRIPT"
    appmod._llm = FakeLLM()
    from fastapi.testclient import TestClient
    return TestClient(appmod.app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_script_job_lifecycle(client):
    r = client.post("/jobs/script", json={"topic": "test topic"})
    assert r.status_code == 200
    job_id = r.json()["id"]
    # TestClient runs BackgroundTasks before returning → job already finished
    r2 = client.get(f"/jobs/{job_id}")
    assert r2.json()["status"] == "done"
    assert r2.json()["result"]["script"] == "FAKE SCRIPT"


def test_unknown_job_404(client):
    assert client.get("/jobs/doesnotexist").status_code == 404


def test_metrics_endpoint(client, isolated_db):
    isolated_db.record_llm_usage(provider="claude", model="m", input_tokens=1,
                                 output_tokens=1, latency_s=0.1, cost_usd=0.001)
    r = client.get("/metrics/usage")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_api_key_enforced_when_set(isolated_db, monkeypatch):
    monkeypatch.setenv("PLATFORM_API_KEY", "sekrit")
    import content_core.api.app as appmod
    importlib.reload(appmod)
    from fastapi.testclient import TestClient
    c = TestClient(appmod.app)

    assert c.get("/jobs").status_code == 401                      # missing key
    assert c.get("/jobs", headers={"X-API-Key": "wrong"}).status_code == 401
    assert c.get("/jobs", headers={"X-API-Key": "sekrit"}).status_code == 200
    assert c.get("/health").status_code == 200                    # health stays open
