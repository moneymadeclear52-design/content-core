"""
content_core.eval.runner
========================
Three composed capabilities on top of scorers + registry + telemetry:

  evaluate()   — run a prompt against golden cases, score each, persist an
                 eval_run + eval_results. This is regression testing for prompts.
  benchmark()  — run the SAME prompt across multiple providers/models, score
                 and time each, persist benchmark_runs. "Which model for this?"
  experiment() — run N prompt variants against the same input, score each,
                 return the winner. Prompt A/B/n.

All results land in the existing SQLAlchemy layer, so the API/dashboard can
read history without new plumbing.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from .scorers import run_scorers, aggregate, Score


@dataclass
class CaseResult:
    case_id: str
    output: str
    scores: list[Score]
    aggregate: float


@dataclass
class EvalReport:
    prompt_name: str
    prompt_version: Optional[int]
    model: str
    mean_score: float
    pass_rate: float
    cases: list[CaseResult] = field(default_factory=list)
    run_id: Optional[int] = None


# ── Evaluate: prompt vs golden cases ───────────────────────────────────────────

def evaluate(prompt_template: str, cases: list[dict], criteria: list[dict],
             *, llm=None, model: Optional[str] = None,
             prompt_name: str = "ad-hoc", prompt_version: Optional[int] = None,
             persist: bool = True) -> EvalReport:
    """
    cases:    [{"id","inputs":{...},"task"?}] — inputs render the template.
    criteria: scorer configs (see scorers.run_scorers).
    """
    from .. import LLMProvider
    llm = llm or LLMProvider()

    case_results: list[CaseResult] = []
    for case in cases:
        rendered = prompt_template.format(**case.get("inputs", {}))
        output = llm.generate(rendered, model=model, max_tokens=800)
        crit = [dict(c, task=case.get("task", rendered)) for c in criteria]
        scores = run_scorers(output, crit, llm=llm)
        case_results.append(CaseResult(case["id"], output, scores, aggregate(scores)))

    mean = round(sum(c.aggregate for c in case_results) / len(case_results), 4) if case_results else 0.0
    pass_rate = round(
        sum(1 for c in case_results if all(s.passed for s in c.scores)) / len(case_results), 4
    ) if case_results else 0.0

    report = EvalReport(prompt_name, prompt_version, model or "default",
                        mean, pass_rate, case_results)
    if persist:
        report.run_id = _persist_eval(report)
    return report


def _persist_eval(report: EvalReport) -> Optional[int]:
    try:
        from ..db import get_session, init_db
        from ..db.models_phase5 import EvalRun, EvalResult
        init_db()
        with get_session() as s:
            run = EvalRun(prompt_name=report.prompt_name,
                          prompt_version=report.prompt_version,
                          model=report.model, mean_score=report.mean_score,
                          pass_rate=report.pass_rate)
            for c in report.cases:
                run.results.append(EvalResult(
                    case_id=c.case_id, output=c.output[:2000],
                    aggregate=c.aggregate,
                    detail="; ".join(f"{s.name}:{s.value}" for s in c.scores),
                ))
            s.add(run)
            s.flush()
            return run.id
    except Exception:
        return None


# ── Benchmark: same prompt across models ──────────────────────────────────────

@dataclass
class BenchmarkRow:
    provider: str
    model: str
    output: str
    score: float
    latency_s: float


def benchmark(prompt: str, targets: list[dict], criteria: list[dict],
              *, persist: bool = True) -> list[BenchmarkRow]:
    """
    targets: [{"provider","model"}]. Runs the same prompt across each, scores
    and times the output. Telemetry (Phase 4) records cost automatically.
    """
    from .. import LLMProvider
    rows: list[BenchmarkRow] = []
    for t in targets:
        llm = LLMProvider(provider=t["provider"])
        t0 = time.time()
        output = llm.generate(prompt, model=t["model"], max_tokens=800)
        latency = time.time() - t0
        crit = [dict(c, task=prompt) for c in criteria]
        score = aggregate(run_scorers(output, crit, llm=llm))
        rows.append(BenchmarkRow(t["provider"], t["model"], output, score, round(latency, 3)))

    if persist:
        _persist_benchmark(prompt, rows)
    return sorted(rows, key=lambda r: r.score, reverse=True)


def _persist_benchmark(prompt: str, rows: list[BenchmarkRow]) -> None:
    try:
        from ..db import get_session, init_db
        from ..db.models_phase5 import BenchmarkRun
        init_db()
        with get_session() as s:
            for r in rows:
                s.add(BenchmarkRun(prompt_excerpt=prompt[:300], provider=r.provider,
                                   model=r.model, score=r.score, latency_s=r.latency_s))
    except Exception:
        pass


# ── Experiment: variant A/B/n ─────────────────────────────────────────────────

@dataclass
class Variant:
    label: str
    template: str


@dataclass
class ExperimentResult:
    winner: str
    scores: dict            # label -> aggregate score
    outputs: dict           # label -> output


def experiment(variants: list[Variant], inputs: dict, criteria: list[dict],
               *, llm=None, model: Optional[str] = None) -> ExperimentResult:
    """Run each prompt variant on the same inputs; the highest mean score wins."""
    from .. import LLMProvider
    llm = llm or LLMProvider()
    scores, outputs = {}, {}
    for v in variants:
        rendered = v.template.format(**inputs)
        out = llm.generate(rendered, model=model, max_tokens=800)
        crit = [dict(c, task=rendered) for c in criteria]
        outputs[v.label] = out
        scores[v.label] = aggregate(run_scorers(out, crit, llm=llm))
    winner = max(scores, key=scores.get) if scores else ""
    return ExperimentResult(winner=winner, scores=scores, outputs=outputs)
