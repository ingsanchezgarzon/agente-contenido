"""
Global retry decorator with exponential backoff for all external API calls.

Retries only transient failures: rate limits, server errors, timeouts, and
connection errors. Client errors (bad input, invalid schema) fail immediately
— retrying those wastes money and time.

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

import requests

from utils.logger import warning


def _is_retryable(exc: Exception) -> bool:
    """Check if an exception is transient (retryable) or permanent (fail-fast)."""
    # Gemini API errors
    if isinstance(exc, requests.exceptions.Timeout):
        return True
    if isinstance(exc, requests.exceptions.ConnectionError):
        return True
    if isinstance(exc, requests.exceptions.HTTPError) and exc.response is not None:
        # Retry on 408 (Request Timeout), 429 (Rate Limited), 5xx (Server Error)
        return exc.response.status_code in (408, 429) or exc.response.status_code >= 500
    # Google SDK errors
    try:
        from google.api_core.exceptions import RetryError, InternalServerError, ServiceUnavailable, TooManyRequests, DeadlineExceeded
        if isinstance(exc, (RetryError, InternalServerError, ServiceUnavailable, TooManyRequests, DeadlineExceeded)):
            return True
    except ImportError:
        pass
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
