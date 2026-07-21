"""
content_core.eval
================
Evaluation, benchmarking, and experimentation for the platform.

    from content_core.eval import evaluate, benchmark, experiment, Variant
    from content_core.eval import run_scorers, LLMJudge, Score
    from content_core.eval import PromptRegistry
"""

from .scorers import run_scorers, aggregate, LLMJudge, Score
from .runner import (
    evaluate, benchmark, experiment,
    EvalReport, CaseResult, BenchmarkRow, Variant, ExperimentResult,
)
from .registry import PromptRegistry, PromptTemplate

__all__ = [
    "run_scorers", "aggregate", "LLMJudge", "Score",
    "evaluate", "benchmark", "experiment",
    "EvalReport", "CaseResult", "BenchmarkRow", "Variant", "ExperimentResult",
    "PromptRegistry", "PromptTemplate",
]
