"""
content_core
============
Shared core for the AI content-automation pipelines.
"""

from .llm import LLMProvider, LLMResponse, LLMError
from .originality_injector import inject_originality, process_content_queue
from .retry import retry, call_with_retry
from .workflow import Workflow, Step, RunReport, StepResult

__version__ = "0.2.0"

__all__ = [
    "LLMProvider", "LLMResponse", "LLMError",
    "inject_originality", "process_content_queue",
    "retry", "call_with_retry",
    "Workflow", "Step", "RunReport", "StepResult",
]
