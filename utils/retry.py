"""
Global retry decorator with exponential backoff for all external API calls.

Retries only transient failures: rate limits (429), server errors (>=500),
overloaded responses, and network timeouts/disconnects. Client errors
(400/401/404, schema problems) fail immediately — retrying those wastes money.

Usage:
    from utils.retry import with_retry

    @with_retry()                       # 4 attempts, 2s base delay
    def call_api(...): ...

    @with_retry(max_attempts=6, base_delay=5.0)
    def poll_something(...): ...
"""

import functools
import random
import time

import anthropic
import requests

from utils.logger import warning


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, (anthropic.RateLimitError, anthropic.APIConnectionError,
                        anthropic.InternalServerError)):
        return True
    if isinstance(exc, anthropic.APIStatusError):
        return exc.status_code in (408, 429, 529) or exc.status_code >= 500
    if isinstance(exc, (requests.exceptions.Timeout, requests.exceptions.ConnectionError)):
        return True
    if isinstance(exc, requests.exceptions.HTTPError) and exc.response is not None:
        return exc.response.status_code in (408, 429) or exc.response.status_code >= 500
    return False


def with_retry(max_attempts: int = 4, base_delay: float = 2.0):
    """Retry *fn* on transient API errors with exponential backoff + jitter."""
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except Exception as exc:
                    if attempt == max_attempts or not _is_retryable(exc):
                        raise
                    delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 1)
                    warning(
                        "retry",
                        f"{fn.__name__} attempt {attempt}/{max_attempts} failed "
                        f"({type(exc).__name__}: {exc}) — retrying in {delay:.1f}s",
                    )
                    time.sleep(delay)
        return wrapper
    return decorator
