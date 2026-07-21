"""
content_core.eval.scorers
=========================
The scoring engine behind evaluation, benchmarking, and experiments.

Two scorer families:
  - Rule-based: cheap, deterministic checks (length bounds, required/forbidden
    substrings, non-empty, regex). No LLM cost. Registered by name.
  - LLM-as-judge: uses content_core.LLMProvider with a CHEAP judge model to
    rate an output against a rubric on a 0-1 scale. Cost-aware by design.

A Score is normalized to 0.0-1.0 with a human-readable reason, so results are
comparable across scorer types and storable in one DB column.

Custom scorers register via @register_scorer and become usable by name in
eval configs — see content_core.registry.
"""

from __future__ import annotations

import re
import json
import logging
from dataclasses import dataclass
from typing import Callable, Optional

from ..registry import register_scorer, get_scorer

logger = logging.getLogger(__name__)


@dataclass
class Score:
    name: str
    value: float          # normalized 0.0 - 1.0
    passed: bool
    reason: str = ""


# ── Built-in rule-based scorers ────────────────────────────────────────────────

@register_scorer("non_empty")
def _non_empty(output: str, ctx: dict) -> Score:
    ok = bool(output and output.strip())
    return Score("non_empty", 1.0 if ok else 0.0, ok,
                 "output present" if ok else "output empty")


@register_scorer("length_bounds")
def _length_bounds(output: str, ctx: dict) -> Score:
    """ctx: {min_words?, max_words?}. Score = fraction of bound satisfied."""
    words = len((output or "").split())
    lo = ctx.get("min_words", 0)
    hi = ctx.get("max_words", 10**9)
    ok = lo <= words <= hi
    return Score("length_bounds", 1.0 if ok else 0.0, ok,
                 f"{words} words (bounds {lo}-{hi})")


@register_scorer("contains_all")
def _contains_all(output: str, ctx: dict) -> Score:
    """ctx: {required: [substrings]}. Score = fraction present."""
    req = ctx.get("required", [])
    if not req:
        return Score("contains_all", 1.0, True, "no requirements")
    low = (output or "").lower()
    hits = sum(1 for s in req if s.lower() in low)
    frac = hits / len(req)
    return Score("contains_all", frac, frac == 1.0,
                 f"{hits}/{len(req)} required phrases present")


@register_scorer("excludes_all")
def _excludes_all(output: str, ctx: dict) -> Score:
    """ctx: {forbidden: [substrings]}. Passes only if none present."""
    forb = ctx.get("forbidden", [])
    low = (output or "").lower()
    present = [s for s in forb if s.lower() in low]
    ok = not present
    return Score("excludes_all", 1.0 if ok else 0.0, ok,
                 "clean" if ok else f"forbidden present: {present}")


@register_scorer("regex_match")
def _regex_match(output: str, ctx: dict) -> Score:
    """ctx: {pattern}. Passes if the pattern is found."""
    pat = ctx.get("pattern", "")
    ok = bool(re.search(pat, output or ""))
    return Score("regex_match", 1.0 if ok else 0.0, ok,
                 f"/{pat}/ {'matched' if ok else 'not found'}")


# ── LLM-as-judge ───────────────────────────────────────────────────────────────

DEFAULT_RUBRIC = (
    "Rate the OUTPUT for overall quality: accuracy, coherence, and fit to the "
    "TASK. 1.0 = excellent, 0.0 = unusable."
)


class LLMJudge:
    """
    LLM-as-a-judge scorer. Uses a cheap model by default (cost-aware). Returns
    a 0-1 score parsed from a strict JSON reply; degrades to a neutral score
    (0.5) on any parse/LLM failure so evaluation never crashes.
    """

    def __init__(self, llm=None, model: Optional[str] = None, pass_threshold: float = 0.6):
        # Lazy import avoids a hard dependency for rule-only evaluation
        from .. import LLMProvider
        self.llm = llm or LLMProvider()
        self.model = model or "claude-haiku-4-5-20251001"
        self.pass_threshold = pass_threshold

    def score(self, output: str, ctx: dict) -> Score:
        task = ctx.get("task", "")
        rubric = ctx.get("rubric", DEFAULT_RUBRIC)
        prompt = (
            f"{rubric}\n\nTASK:\n{task}\n\nOUTPUT:\n{output}\n\n"
            'Respond with ONLY JSON: {"score": <0.0-1.0>, "reason": "<short>"}'
        )
        try:
            raw = self.llm.generate(prompt, model=self.model, max_tokens=200,
                                    temperature=0.0)
            data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
            val = max(0.0, min(1.0, float(data["score"])))
            return Score("llm_judge", val, val >= self.pass_threshold,
                         str(data.get("reason", ""))[:200])
        except Exception as e:  # noqa: BLE001 — judging must not crash eval
            logger.warning("LLM judge failed (%s) — neutral score", e)
            return Score("llm_judge", 0.5, False, f"judge error: {e}")


# ── Convenience runner ─────────────────────────────────────────────────────────

def run_scorers(output: str, criteria: list[dict], llm=None) -> list[Score]:
    """
    criteria: list of {"scorer": name, ...ctx}. The special scorer name
    "llm_judge" invokes the LLMJudge; all others resolve via the registry.
    """
    results: list[Score] = []
    judge: Optional[LLMJudge] = None
    for c in criteria:
        name = c["scorer"]
        ctx = {k: v for k, v in c.items() if k != "scorer"}
        if name == "llm_judge":
            judge = judge or LLMJudge(llm=llm, model=ctx.get("model"))
            results.append(judge.score(output, ctx))
        else:
            fn: Callable = get_scorer(name)
            results.append(fn(output, ctx))
    return results


def aggregate(scores: list[Score]) -> float:
    """Mean normalized score across all criteria (0-1)."""
    return round(sum(s.value for s in scores) / len(scores), 4) if scores else 0.0
