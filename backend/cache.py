"""
Aegis Finance — In-Memory TTL Cache
=====================================

Simple in-memory cache with time-to-live expiration.
Thread-safe for concurrent FastAPI requests.
No external dependencies (no Redis, no database).

Usage:
    from backend.cache import cached, cache_clear

    @cached(ttl=3600)
    def expensive_function(ticker: str) -> dict:
        ...
"""

import time
import logging
import threading
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
