# ADR-0005: Keep the custom LLMProvider; do not adopt LiteLLM

**Status:** Accepted · July 2026

## Context
LiteLLM offers a unified interface over 100+ providers and is the right tool
when provider breadth or proxy-level cost controls are requirements.

## Decision
Keep the in-house `LLMProvider` (Claude/OpenAI/Gemini).

## Reasoning
- We use two providers, occasionally three; breadth is not a requirement.
- The abstraction is ~200 tested lines with full control of retry semantics
  and telemetry hooks; replacing it deletes working, understood code to add a
  dependency.
- The abstraction itself is a demonstration artifact of this platform.
LiteLLM re-evaluation trigger: needing >3 providers or centralized
key/proxy management.
