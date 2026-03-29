"""
Aegis Finance — In-Memory TTL Cache + Retry
=============================================

Simple in-memory cache with time-to-live expiration.
Thread-safe for concurrent FastAPI requests.
Includes retry with exponential backoff for external API calls.
No external dependencies (no Redis, no database).

Usage:
    from backend.cache import cached, cache_clear, retry_with_backoff

    @cached(ttl=3600)
    def expensive_function(ticker: str) -> dict:
        ...

    @retry_with_backoff(max_retries=3, base_delay=1.0)
    def flaky_api_call():
        ...
"""

import time
import logging
import threading
import random
from functools import wraps
from typing import Any, Optional

logger = logging.getLogger(__name__)

_cache: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def cache_get(key: str, ttl_seconds: int) -> Optional[Any]:
    """Return cached value if within TTL, else None."""
    with _lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        if time.time() - entry["timestamp"] > ttl_seconds:
            del _cache[key]
            return None
        return entry["value"]


def cache_set(key: str, value: Any) -> None:
    """Store value with current timestamp."""
    with _lock:
        _cache[key] = {"value": value, "timestamp": time.time()}


def cache_clear() -> None:
    """Clear entire cache."""
    with _lock:
        _cache.clear()
    logger.info("Cache cleared")


def cached(ttl: int = 3600, key_prefix: str = ""):
    """Decorator: cache function results by args for ttl seconds.

    Args:
        ttl: Time-to-live in seconds (default: 1 hour)
        key_prefix: Optional prefix for cache key (defaults to function name)
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            # Build cache key from function name + arguments
            prefix = key_prefix or fn.__qualname__
            arg_key = str(args[1:]) + str(sorted(kwargs.items()))  # skip 'self'
            cache_key = f"{prefix}:{arg_key}"

            result = cache_get(cache_key, ttl)
            if result is not None:
                logger.debug("Cache hit: %s", prefix)
                return result

            result = fn(*args, **kwargs)
            if result is not None:
                cache_set(cache_key, result)
            return result
        return wrapper
    return decorator


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    jitter: bool = True,
    retryable_exceptions: tuple = (Exception,),
):
    """Decorator: retry with exponential backoff on failure.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds (doubles each retry)
        max_delay: Maximum delay cap in seconds
        jitter: Add random jitter to prevent thundering herd
        retryable_exceptions: Tuple of exception types to retry on
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_retries + 1):
                try:
                    return fn(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exc = e
                    if attempt == max_retries:
                        break
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    if jitter:
                        delay *= 0.5 + random.random()
                    logger.warning(
                        "Retry %d/%d for %s after %.1fs: %s",
                        attempt + 1, max_retries, fn.__qualname__, delay, e,
                    )
                    time.sleep(delay)
            raise last_exc
        return wrapper
    return decorator
