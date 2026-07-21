"""
content_core.workflow
=====================
A minimal step-based workflow engine for content pipelines.

Replaces long, linear `run_pipeline()` functions with named stages that have:
- a clear input/output contract (a shared mutable context dict)
- per-stage retry with backoff
- per-stage error policy (fail the run, or skip and continue)
- a run report (what ran, what failed, how long each stage took)

Deliberately small: no DAGs, no async, no external deps. Content pipelines are
linear with occasional optional stages — this models exactly that and no more.

Usage:
    from content_core.workflow import Workflow, Step

    def hunt_topics(ctx):
        ctx["topics"] = TrendHunter().get_all_trends()
        if not ctx["topics"]:
            raise RuntimeError("no topics found")

    def generate_scripts(ctx):
        ctx["scripts"] = generate_batch(ctx["topics"], count=1)

    wf = Workflow("rapidreelz-daily", steps=[
        Step("hunt_topics", hunt_topics, retries=2),
        Step("generate_scripts", generate_scripts, retries=2),
        Step("thumbnail", make_thumbnail, on_error="skip"),   # optional stage
        Step("upload", upload_all, retries=3),
    ])
    report = wf.run(initial_context={"run_id": run_id})
    print(report.summary())
"""

from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Literal, Optional

logger = logging.getLogger(__name__)

Context = Dict[str, object]
ErrorPolicy = Literal["fail", "skip"]


@dataclass
class Step:
    """A named pipeline stage.

    fn:        callable taking the shared context dict; mutate it to pass data on.
    retries:   how many attempts before applying the error policy (1 = no retry).
    on_error:  "fail" aborts the run; "skip" logs and continues (optional stages).
    """
    name: str
    fn: Callable[[Context], None]
    retries: int = 1
    on_error: ErrorPolicy = "fail"
    backoff_base: float = 1.5


@dataclass
class StepResult:
    name: str
    status: Literal["ok", "skipped", "failed"]
    attempts: int
    duration_s: float
    error: Optional[str] = None


@dataclass
class RunReport:
    workflow: str
    results: List[StepResult] = field(default_factory=list)
    aborted: bool = False

    @property
    def ok(self) -> bool:
        return not self.aborted

    def summary(self) -> str:
        lines = [f"Workflow '{self.workflow}': {'ABORTED' if self.aborted else 'completed'}"]
        for r in self.results:
            mark = {"ok": "✓", "skipped": "⤳", "failed": "✗"}[r.status]
            line = f"  {mark} {r.name:<24} {r.status:<8} {r.duration_s:6.1f}s (attempts: {r.attempts})"
            if r.error:
                line += f"  — {r.error}"
            lines.append(line)
        return "\n".join(lines)


class Workflow:
    def __init__(self, name: str, steps: List[Step]):
        self.name = name
        self.steps = steps

    def run(self, initial_context: Optional[Context] = None) -> RunReport:
        ctx: Context = dict(initial_context or {})
        report = RunReport(workflow=self.name)

        for step in self.steps:
            result = self._run_step(step, ctx)
            report.results.append(result)

            if result.status == "failed" and step.on_error == "fail":
                logger.error("Step '%s' failed — aborting workflow '%s'", step.name, self.name)
                report.aborted = True
                break

        return report

    def _run_step(self, step: Step, ctx: Context) -> StepResult:
        start = time.time()
        last_err: Optional[BaseException] = None

        for attempt in range(1, step.retries + 1):
            try:
                logger.info("[%s] step '%s' (attempt %d/%d)",
                            self.name, step.name, attempt, step.retries)
                step.fn(ctx)
                return StepResult(
                    name=step.name, status="ok",
                    attempts=attempt, duration_s=time.time() - start,
                )
            except Exception as e:  # noqa: BLE001 — policy decides handling
                last_err = e
                if attempt < step.retries:
                    wait = step.backoff_base ** attempt
                    logger.warning("[%s] step '%s' failed: %s — retrying in %.1fs",
                                   self.name, step.name, e, wait)
                    time.sleep(wait)

        duration = time.time() - start
        if step.on_error == "skip":
            logger.warning("[%s] step '%s' failed after %d attempts — skipping (optional stage)",
                           self.name, step.name, step.retries)
            return StepResult(name=step.name, status="skipped",
                              attempts=step.retries, duration_s=duration,
                              error=str(last_err))

        return StepResult(name=step.name, status="failed",
                          attempts=step.retries, duration_s=duration,
                          error=str(last_err))
