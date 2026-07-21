"""
content_core.retry
==================
A small, dependency-free retry decorator with exponential backoff, for wrapping
calls to flaky external services (LLM APIs, TTS, upload endpoints, Notion).

Usage:
    from content_core.retry import retry

    @retry(attempts=3, backoff_base=1.5, exceptions=(requests.RequestException,))
    def upload_video(path):
        ...

    # or ad hoc, without decorating:
    from content_core.retry import call_with_retry
    result = call_with_retry(lambda: client.upload(path), attempts=3)

Design notes:
- `exceptions` limits which failures are retried; anything else propagates
  immediately (a 401 auth error should fail fast, not retry).
- Backoff is exponential: wait = backoff_base ** attempt (1.5s, 2.25s, 3.4s...).
- On final failure the ORIGINAL exception is re-raised, preserving traceback.
"""

from __future__ import annotations

import time
import logging
import functools
from typing import Callable, Tuple, Type, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def retry(
    attempts: int = 3,
    backoff_base: float = 1.5,
    exceptions: Tuple[Type[BaseException], ...] = (Exception,),
    on_retry: Callable[[int, BaseException], None] | None = None,
):
    """
    Decorator: retry the wrapped function up to `attempts` times with
    exponential backoff, retrying only on the given `exceptions`.
    """
    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs) -> T:
            last_err: BaseException | None = None
            for attempt in range(1, attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except exceptions as e:
                    last_err = e
                    if attempt == attempts:
                        break
                    wait = backoff_base ** attempt
                    logger.warning(
                        "%s failed (attempt %d/%d): %s — retrying in %.1fs",
                        fn.__name__, attempt, attempts, e, wait,
                    )
                    if on_retry:
                        on_retry(attempt, e)
                    time.sleep(wait)
            assert last_err is not None
            raise last_err
        return wrapper
    return decorator


def call_with_retry(
    fn: Callable[[], T],
    attempts: int = 3,
    backoff_base: float = 1.5,
    exceptions: Tuple[Type[BaseException], ...] = (Exception,),
) -> T:
    """Functional form for one-off calls without decorating."""
    return retry(attempts=attempts, backoff_base=backoff_base, exceptions=exceptions)(fn)()
