"""
content_core
============
Shared core for the AI content-automation pipelines.

Public API:
    from content_core import LLMProvider, inject_originality
    from content_core.workflow import Workflow, Step
    from content_core.retry import retry, call_with_retry
    from content_core.rag import PerspectiveIndex, retrieve_relevant_perspectives
    from content_core.agents import Director
"""

from .llm import LLMProvider, LLMResponse, LLMError
from .originality_injector import inject_originality, process_content_queue
from .retry import retry, call_with_retry
from .workflow import Workflow, Step, RunReport, StepResult

__version__ = "0.5.0"

__all__ = [
    "LLMProvider", "LLMResponse", "LLMError",
    "inject_originality", "process_content_queue",
    "retry", "call_with_retry",
    "Workflow", "Step", "RunReport", "StepResult",
]
