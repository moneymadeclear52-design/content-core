# ADR-0008: Minimal registry, not a plugin framework

**Status:** Accepted · July 2026

## Decision
Provide a ~60-line decorator registry (`content_core.registry`) for scorers,
publishers, and providers. Do NOT build entry-point discovery, plugin
lifecycle, or sandboxed loading.

## Reasoning
The concrete need is: look up an eval scorer or provider by name so criteria
are configuration rather than hardcoded imports. A decorator registry solves
exactly that. A full plugin framework (dynamic discovery, versioned plugin
APIs, isolation) is speculative generality for a single-operator platform with
a known, in-repo set of components — the kind of unnecessary complexity this
project explicitly avoids.

## Adopt-full-framework triggers
- Third parties shipping components out-of-tree
- Components needing isolation/untrusted execution
- A stable public plugin API with independent release cadence
