"""
content_core
============
Shared core for the AI content-automation pipelines.

Public API:
    from content_core import LLMProvider, inject_originality
    from content_core import notion_connect
"""

from .llm import LLMProvider, LLMResponse, LLMError
from .originality_injector import inject_originality, process_content_queue

__version__ = "0.1.0"

__all__ = [
    "LLMProvider",
    "LLMResponse",
    "LLMError",
    "inject_originality",
    "process_content_queue",
]
