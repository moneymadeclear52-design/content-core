# ADR-0003: LLM usage/cost telemetry first; defer full OTel/Prometheus

**Status:** Accepted · July 2026

## Decision
Instrument the single LLM choke point (`LLMProvider.generate_full`) to record
provider, model, tokens, latency, and estimated cost per call into the DB,
exposed via `GET /metrics/usage`. Structured JSON logging via
`telemetry.setup_structured_logging()`. Optional **Langfuse** export behind
`LANGFUSE_ENABLED=true` (no hard dependency).

## Why this scope
Token/cost visibility is the observability signal with real decision value
for an AI platform (model tiering choices, budget control). A full
OpenTelemetry + Prometheus + Grafana stack adds collectors and dashboards to
observe a single process on a single machine — cost without a consumer.

## Adopt-full-stack triggers
- Multiple services needing distributed traces
- An on-call rotation consuming alerts
- SLOs that require latency histograms rather than averages
