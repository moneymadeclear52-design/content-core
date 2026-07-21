"""
content_core.telemetry
======================
LLM usage + cost tracking, wired into LLMProvider at its single choke point.

- Extracts token counts defensively from each vendor's response shape.
- Computes cost from a maintainable pricing table (USD per 1M tokens).
- Persists to the DB (content_core.db) — failures here NEVER break generation.
- Optional Langfuse hook, enabled via LANGFUSE_ENABLED=true (off by default;
  no hard dependency).

Structured logging: setup_structured_logging() emits one JSON object per line,
suitable for ingestion by any log system.
"""

from __future__ import annotations

import os
import json
import logging

logger = logging.getLogger(__name__)

# USD per 1M tokens: (input, output). Update as pricing changes; unknown
# models fall back to a conservative default so cost is estimated, not zero.
PRICING_PER_MTOK: dict[str, tuple[float, float]] = {
    # Anthropic
    "claude-sonnet-4-6":        (3.00, 15.00),
    "claude-haiku-4-5-20251001": (0.80, 4.00),
    "claude-opus-4-8":          (15.00, 75.00),
    # OpenAI
    "gpt-4o":                   (2.50, 10.00),
    "gpt-4o-mini":              (0.15, 0.60),
    # Gemini
    "gemini-1.5-pro":           (1.25, 5.00),
}
_DEFAULT_PRICING = (3.00, 15.00)


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    inp, out = PRICING_PER_MTOK.get(model, _DEFAULT_PRICING)
    return (input_tokens * inp + output_tokens * out) / 1_000_000


def extract_tokens(provider: str, raw) -> tuple[int, int]:
    """Best-effort token extraction across vendor response shapes."""
    try:
        if provider == "claude":
            u = getattr(raw, "usage", None)
            return int(getattr(u, "input_tokens", 0)), int(getattr(u, "output_tokens", 0))
        if provider == "openai":
            u = getattr(raw, "usage", None)
            return int(getattr(u, "prompt_tokens", 0)), int(getattr(u, "completion_tokens", 0))
        if provider == "gemini":
            u = getattr(raw, "usage_metadata", None)
            return int(getattr(u, "prompt_token_count", 0)), int(getattr(u, "candidates_token_count", 0))
    except Exception:  # noqa: BLE001 — telemetry must never raise
        pass
    return 0, 0


def record_call(*, provider: str, model: str, raw, latency_s: float,
                caller: str | None = None) -> None:
    """Record one LLM call. Swallows all errors by design: observability must
    never take down the pipeline it observes."""
    try:
        itok, otok = extract_tokens(provider, raw)
        cost = estimate_cost_usd(model, itok, otok)

        from content_core.db import record_llm_usage
        record_llm_usage(provider=provider, model=model,
                         input_tokens=itok, output_tokens=otok,
                         latency_s=latency_s, cost_usd=cost, caller=caller)

        logger.info(json.dumps({
            "event": "llm_call", "provider": provider, "model": model,
            "input_tokens": itok, "output_tokens": otok,
            "latency_s": round(latency_s, 3), "cost_usd": round(cost, 6),
        }))

        _maybe_langfuse(provider, model, itok, otok, latency_s, cost)
    except Exception as e:  # noqa: BLE001
        logger.debug("telemetry record failed (non-fatal): %s", e)


def _maybe_langfuse(provider, model, itok, otok, latency_s, cost):
    """Optional Langfuse export. Enabled only when LANGFUSE_ENABLED=true and
    the langfuse package is installed; otherwise a silent no-op."""
    if os.getenv("LANGFUSE_ENABLED", "").lower() != "true":
        return
    try:
        from langfuse import Langfuse  # optional dependency
        Langfuse().generation(
            name=f"{provider}:{model}",
            model=model,
            usage={"input": itok, "output": otok, "total_cost": cost},
            metadata={"latency_s": latency_s},
        )
    except Exception as e:  # noqa: BLE001
        logger.debug("langfuse export failed (non-fatal): %s", e)


# ── Structured logging ─────────────────────────────────────────────────────────

class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            base["exc"] = self.formatException(record.exc_info)
        return json.dumps(base)


def setup_structured_logging(level: int = logging.INFO) -> None:
    """Route root logging through one-JSON-object-per-line output."""
    handler = logging.StreamHandler()
    handler.setFormatter(_JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
