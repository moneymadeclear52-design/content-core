# ADR-0009: LLM-as-judge with a cheap judge model + rule-based first

**Status:** Accepted · July 2026

## Decision
Output evaluation uses two scorer families: deterministic rule-based checks
(length, required/forbidden content, regex) and an LLM-as-judge that rates
against a rubric on a 0-1 scale. The judge defaults to a CHEAP model
(claude-haiku), and rule-based scorers run without any LLM cost.

## Reasoning
- Rule-based checks catch the majority of regressions for free and
  deterministically; they should run first and always.
- LLM-as-judge covers subjective quality (coherence, fit) that rules can't,
  but costs tokens — so it uses the cheapest capable model and is opt-in per
  criterion.
- The judge degrades to a neutral score on any parse/LLM failure, so
  evaluation never crashes a run.

## Consequence
Every score is normalized to 0-1 with a reason, making rule and judge results
comparable and storable in one column — which is what lets benchmarking and
experiments rank across scorer types.
