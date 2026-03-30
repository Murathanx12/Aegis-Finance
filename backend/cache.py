"""
Aegis Finance — Two-Layer Cache (Memory + Disk) + Retry
=========================================================

Memory cache for hot data, disk cache (diskcache/SQLite) for persistence
across restarts. Thread-safe for concurrent FastAPI requests.

Usage:
    from backend.cache import cached, cache_clear, retry_with_backoff, cache_ready

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
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_cache: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()
_cache_ready = False

# ── Disk Cache Layer ──────────────────────────────────────────────────────────

_CACHE_DIR = Path(__file__).parent.parent / ".cache"
_disk_cache = None


def _get_disk_cache():
    """Lazy-init disk cache (diskcache with SQLite backend)."""
    global _disk_cache
    if _disk_cache is not None:
        return _disk_cache
    try:
        import diskcache
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _disk_cache = diskcache.Cache(str(_CACHE_DIR), size_limit=500 * 1024 * 1024)
        logger.info("Disk cache initialized at %s", _CACHE_DIR)
        return _disk_cache
    except ImportError:
        logger.warning("diskcache not installed — disk persistence disabled")
        return None
    except Exception as e:
        logger.warning("Disk cache init failed: %s", e)
        return None


def _disk_get(key: str, ttl_seconds: int) -> Optional[Any]:
    """Read from disk cache if within TTL."""
    dc = _get_disk_cache()
    if dc is None:
        return None
    try:
        entry = dc.get(key)
        if entry is None:
            return None
        ts, value = entry
        if time.time() - ts > ttl_seconds:
            dc.delete(key)
            return None
        return value
    except Exception:
        return None


def _disk_set(key: str, value: Any) -> None:
    """Write to disk cache."""
    dc = _get_disk_cache()
    if dc is None:
        return
    try:
        dc.set(key, (time.time(), value))
    except Exception as e:
        logger.debug("Disk cache write failed for %s: %s", key, e)


# ── Public API ────────────────────────────────────────────────────────────────


def cache_get(key: str, ttl_seconds: int) -> Optional[Any]:
    """Return cached value if within TTL. Checks memory first, then disk."""
    with _lock:
        entry = _cache.get(key)
        if entry is not None:
            if time.time() - entry["timestamp"] > ttl_seconds:
                del _cache[key]
            else:
                return entry["value"]

    # Memory miss — check disk
    disk_val = _disk_get(key, ttl_seconds)
    if disk_val is not None:
        # Promote to memory
        with _lock:
            _cache[key] = {"value": disk_val, "timestamp": time.time()}
        logger.debug("Disk cache hit (promoted): %s", key)
        return disk_val

    return None


def cache_set(key: str, value: Any) -> None:
    """Store value in both memory and disk."""
    with _lock:
        _cache[key] = {"value": value, "timestamp": time.time()}
    _disk_set(key, value)


def cache_clear() -> None:
    """Clear memory cache. Disk cache persists for next startup."""
    with _lock:
        _cache.clear()
    logger.info("Memory cache cleared")


def set_cache_ready(ready: bool = True) -> None:
    """Mark cache as prewarmed."""
    global _cache_ready
    _cache_ready = ready


def cache_ready() -> bool:
    """Check if cache prewarm is complete."""
    return _cache_ready


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
