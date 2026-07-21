# ADR-0006: Keep the Director orchestration; do not adopt LangGraph

**Status:** Accepted · July 2026

## Context
LangGraph provides graph-structured agent orchestration: cycles, checkpoints,
human-in-the-loop interrupts, state persistence.

## Decision
Keep the in-house Director (Writer/Visual/Audio + bounded single-revision
critique loop).

## Reasoning
The production flow is linear with one conditional. Modeling it as a graph
adds a framework dependency and an abstraction layer over ~150 tested lines
whose control flow is readable top-to-bottom. The bounded revision loop is a
deliberate safety property that a general graph engine makes easier to
accidentally relax.

## Adopt-LangGraph triggers
- Dynamic branching between >3 conditional agent paths
- Human-in-the-loop checkpoints mid-workflow
- Long-running agent state requiring persistence/resumption
