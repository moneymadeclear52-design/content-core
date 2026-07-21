"""API tests for Phase 6 feedback endpoints."""
import importlib
import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/fbapi.db")
    monkeypatch.delenv("PLATFORM_API_KEY", raising=False)
    import content_core.db as db
    import content_core.db.models_phase6  # noqa: F401
    db.init_db()
    import content_core.api.app as appmod
    importlib.reload(appmod)
    from fastapi.testclient import TestClient
    return TestClient(appmod.app)


def test_post_performance_then_get_boosts(client):
    # two strong + two weak in distinct categories
    for i in range(2):
        client.post("/feedback/performance", json={
            "channel": "mmc", "video_ref": f"m{i}", "category": "money",
            "retention": 0.8, "ctr": 0.12, "views": 9000, "likes": 400})
        client.post("/feedback/performance", json={
            "channel": "mmc", "video_ref": f"x{i}", "category": "misc",
            "retention": 0.2, "ctr": 0.03, "views": 300, "likes": 5})
    r = client.get("/feedback/mmc")
    assert r.status_code == 200
    boosts = {b["category"]: b["boost"] for b in r.json()}
    assert boosts["money"] > 1.0 > boosts["misc"]


def test_get_feedback_empty_channel(client):
    assert client.get("/feedback/nobody").json() == []
