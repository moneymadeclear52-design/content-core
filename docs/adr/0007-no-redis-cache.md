# ADR-0007: No Redis caching layer

**Status:** Accepted · July 2026

## Decision
Do not introduce Redis for embedding/prompt/response caching or state.

## Reasoning
- Embedding cache: already exists (fingerprint-invalidated on-disk index in
  content_core.rag) — a second cache would cache a cache.
- LLM response cache: generation is creative (temp > 0, unique topics);
  expected hit rate ≈ 0.
- Workflow/job state: persisted in the DB (ADR-0001).
Redis would be a stateful service with nothing to hold.
