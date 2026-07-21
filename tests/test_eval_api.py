"""API tests for Phase 5 endpoints (eval runs, benchmarks, approvals)."""
import importlib
import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/api5.db")
    monkeypatch.delenv("PLATFORM_API_KEY", raising=False)
    import content_core.db as db
    import content_core.db.models_phase5  # noqa: F401
    db.init_db()
    import content_core.api.app as appmod
    importlib.reload(appmod)
    from fastapi.testclient import TestClient
    return TestClient(appmod.app)


def test_approvals_flow(client):
    from content_core.approvals import auto_or_queue
    auto_or_queue(workflow="w", item_ref="vid1", summary="A video", score=0.3, threshold=0.75)
    r = client.get("/approvals")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    aid = items[0]["id"]
    d = client.post(f"/approvals/{aid}/decide", json={"approved": True})
    assert d.status_code == 200 and d.json()["status"] == "approved"
    assert client.get("/approvals").json() == []


def test_decide_unknown_404(client):
    assert client.post("/approvals/9999/decide", json={"approved": False}).status_code == 404


def test_eval_and_benchmark_endpoints_empty(client):
    assert client.get("/eval/runs").json() == []
    assert client.get("/benchmarks").json() == []
