"""
content_core.feedback
=====================
Closed-loop feedback: the one place the platform learns which content performs,
so pipelines can score topics using evidence instead of static heuristics.

THE LOOP
--------
    generate → publish → record_performance(metrics)   [days later]
                              ↓
                        compute_boosts()   (correlate features → performance)
                              ↓
    next run: pipeline calls get_boosts(channel) when scoring candidate topics

This CONSOLIDATES what rapidreelz (category_performance.json) and crimescope
(topic_optimizer) each did separately, and gives mmc + stories the same
capability for the first time — all reading/writing the shared
content_performance table.

WHAT THIS MODULE DOES NOT DO
----------------------------
It does not fetch analytics from any platform — each channel's analytics API
differs, so fetching stays in the pipeline that owns those credentials. This
module owns the store → correlate → score layer, which is where the value and
the duplication were.

A "performance score" blends the normalized signals into one number so
different-scale metrics (views vs CTR vs retention) are comparable. Weights are
deliberately simple and explicit; tune per channel as real data accrues.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# Blend weights for the composite performance score. Explicit and tunable.
SIGNAL_WEIGHTS = {
    "retention": 0.40,   # how much of the video people watch — strongest signal
    "ctr":       0.30,   # thumbnail/title effectiveness
    "views_norm":0.20,   # reach (normalized within the batch)
    "likes_norm":0.10,   # engagement
}


def record_performance(*, channel: str, video_ref: str,
                       category: Optional[str] = None,
                       format: Optional[str] = None,
                       originality_score: Optional[float] = None,
                       views: int = 0, watch_time_min: float = 0.0,
                       ctr: float = 0.0, likes: int = 0,
                       retention: float = 0.0) -> int:
    """Persist one measured item. Returns the row id."""
    from .db import get_session, init_db
    from .db.models_phase6 import ContentPerformance
    init_db()
    with get_session() as s:
        row = ContentPerformance(
            channel=channel, video_ref=video_ref, category=category,
            format=format, originality_score=originality_score,
            views=views, watch_time_min=watch_time_min, ctr=ctr,
            likes=likes, retention=retention,
        )
        s.add(row)
        s.flush()
        return row.id


@dataclass
class CategoryBoost:
    category: str
    boost: float       # multiplier around 1.0 (e.g. 1.2 = score 20% higher)
    sample_size: int
    avg_performance: float


def _performance_score(row, view_max: int, like_max: int) -> float:
    views_norm = (row.views / view_max) if view_max else 0.0
    likes_norm = (row.likes / like_max) if like_max else 0.0
    return (
        SIGNAL_WEIGHTS["retention"] * row.retention +
        SIGNAL_WEIGHTS["ctr"] * row.ctr +
        SIGNAL_WEIGHTS["views_norm"] * views_norm +
        SIGNAL_WEIGHTS["likes_norm"] * likes_norm
    )


def compute_boosts(channel: str, *, min_samples: int = 2,
                   lookback_days: int = 60) -> list[CategoryBoost]:
    """
    Correlate category → performance for a channel and return scoring boosts.
    Boost is each category's average performance relative to the channel mean:
    above-average categories get >1.0, below-average get <1.0. Categories with
    fewer than min_samples are omitted (not enough evidence).
    """
    from datetime import datetime, timedelta, timezone
    from .db import get_session, init_db
    from .db.models_phase6 import ContentPerformance
    init_db()
    since = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    with get_session() as s:
        rows = (s.query(ContentPerformance)
                 .filter(ContentPerformance.channel == channel,
                         ContentPerformance.at >= since).all())
    if not rows:
        return []

    view_max = max((r.views for r in rows), default=0)
    like_max = max((r.likes for r in rows), default=0)

    # per-row score, then group by category
    by_cat: dict[str, list[float]] = {}
    for r in rows:
        cat = r.category or "uncategorized"
        by_cat.setdefault(cat, []).append(_performance_score(r, view_max, like_max))

    cat_avg = {c: sum(v) / len(v) for c, v in by_cat.items() if len(v) >= min_samples}
    if not cat_avg:
        return []

    channel_mean = sum(cat_avg.values()) / len(cat_avg)
    if channel_mean == 0:
        return []

    boosts = []
    for cat, avg in sorted(cat_avg.items(), key=lambda kv: kv[1], reverse=True):
        # clamp the multiplier to a sane range so one lucky video can't dominate
        raw = avg / channel_mean
        boost = max(0.5, min(1.5, raw))
        boosts.append(CategoryBoost(cat, round(boost, 3), len(by_cat[cat]), round(avg, 4)))
    return boosts


def get_boosts(channel: str) -> dict[str, float]:
    """
    The pipeline-facing call: returns {category: multiplier} for topic scoring.
    Empty dict when there's no evidence yet — callers treat a missing category
    as boost 1.0 (no change), so the system degrades to current behavior until
    real performance data exists.
    """
    try:
        return {b.category: b.boost for b in compute_boosts(channel)}
    except Exception as e:  # noqa: BLE001 — feedback must never break scoring
        logger.warning("get_boosts failed (%s) — no boosts applied", e)
        return {}


def apply_boost(base_score: float, category: Optional[str], boosts: dict[str, float]) -> float:
    """Helper for pipelines: multiply a topic's base score by its learned boost."""
    if not category:
        return base_score
    return base_score * boosts.get(category, 1.0)
