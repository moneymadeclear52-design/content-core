# ADR-0010: Unified closed-loop feedback; fetch stays per-pipeline

**Status:** Accepted · July 2026

## Context
Three pipelines had invented separate performance-feedback mechanisms
(rapidreelz's category_performance.json, crimescope's topic_optimizer, mmc's
Claude analysis) and one (stories) had none. Divergent implementations and
coverage gaps — the same duplication the shared core exists to prevent.

## Decision
Add `content_core.feedback` owning the STORE → CORRELATE → SCORE layer:
- `content_performance` table stores measured metrics tagged with content
  features (category, format, originality).
- `compute_boosts()` correlates category → a blended performance score and
  returns per-category scoring multipliers, clamped to [0.5, 1.5].
- `get_boosts(channel)` is the pipeline-facing call; empty when there's no
  data, so scoring degrades to current behavior until evidence exists.

Each pipeline keeps its own analytics FETCH (platform APIs differ and own their
credentials) and calls `record_performance()` + `get_boosts()`.

## Why not fetch analytics in content-core too
YouTube/TikTok/Instagram analytics APIs differ and use per-channel OAuth. A
shared fetcher would either leak credentials across channels or reimplement
each API. The store/score layer is the part that benefits from unification;
fetch does not.

## Honest limitation
Live value requires real analytics data flowing into `record_performance()`.
The mechanism is fully testable with synthetic data (and is tested that way),
but until each pipeline wires its real numbers in, `get_boosts()` returns
empty and scoring is unchanged. This is documented, not hidden.

## Adopt-more triggers
- Enough data to justify per-format (not just per-category) boosts
- A learned model (regression) replacing the linear blend, if signal warrants
