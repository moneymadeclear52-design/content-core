"""Tests for content_core.feedback — synthetic performance data, isolated DB.
Verifies the closed-loop scoring logic without any analytics API."""

import importlib
import pytest


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/p6.db")
    import content_core.db as db
    import content_core.db.models_phase6  # noqa: F401 — register table
    db.init_db()
    return db


def _seed(fb, channel, category, n, *, retention, ctr, views, likes):
    for i in range(n):
        fb.record_performance(channel=channel, video_ref=f"{category}-{i}",
                              category=category, format="short",
                              retention=retention, ctr=ctr, views=views, likes=likes)


def test_record_and_compute_boosts(isolated_db):
    import content_core.feedback as fb
    importlib.reload(fb)

    # "money" clearly outperforms "misc"
    _seed(fb, "mmc", "money", 3, retention=0.8, ctr=0.12, views=10000, likes=500)
    _seed(fb, "mmc", "misc", 3, retention=0.2, ctr=0.03, views=500, likes=10)

    boosts = fb.compute_boosts("mmc")
    by = {b.category: b for b in boosts}
    assert "money" in by and "misc" in by
    # the strong category boosts above 1.0, the weak one below
    assert by["money"].boost > 1.0 > by["misc"].boost
    assert by["money"].sample_size == 3


def test_min_samples_filters_thin_categories(isolated_db):
    import content_core.feedback as fb
    importlib.reload(fb)
    _seed(fb, "c", "solid", 3, retention=0.6, ctr=0.1, views=1000, likes=50)
    _seed(fb, "c", "thin", 1, retention=0.9, ctr=0.2, views=9999, likes=999)  # 1 sample

    cats = {b.category for b in fb.compute_boosts("c", min_samples=2)}
    assert "solid" in cats
    assert "thin" not in cats  # too few samples to trust


def test_boost_is_clamped(isolated_db):
    import content_core.feedback as fb
    importlib.reload(fb)
    # extreme disparity would push raw ratio >1.5; must clamp
    _seed(fb, "c", "viral", 2, retention=1.0, ctr=0.5, views=1_000_000, likes=99999)
    _seed(fb, "c", "flop", 2, retention=0.01, ctr=0.001, views=1, likes=0)
    by = {b.category: b for b in fb.compute_boosts("c")}
    assert by["viral"].boost <= 1.5
    assert by["flop"].boost >= 0.5


def test_get_boosts_dict_and_empty(isolated_db):
    import content_core.feedback as fb
    importlib.reload(fb)
    # no data yet → empty dict → callers treat as no change
    assert fb.get_boosts("nobody") == {}

    _seed(fb, "x", "a", 2, retention=0.7, ctr=0.1, views=1000, likes=50)
    _seed(fb, "x", "b", 2, retention=0.3, ctr=0.05, views=200, likes=10)
    d = fb.get_boosts("x")
    assert set(d) == {"a", "b"}
    assert all(isinstance(v, float) for v in d.values())


def test_apply_boost():
    import content_core.feedback as fb
    importlib.reload(fb)
    boosts = {"money": 1.3, "misc": 0.7}
    assert fb.apply_boost(10.0, "money", boosts) == 13.0
    assert fb.apply_boost(10.0, "misc", boosts) == 7.0
    assert fb.apply_boost(10.0, "unknown", boosts) == 10.0   # default 1.0
    assert fb.apply_boost(10.0, None, boosts) == 10.0
