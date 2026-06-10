"""
Aegis Finance — In-Process Observability State
================================================

Two small in-memory stores backing /api/health/full so a session (or Murat)
can read the whole system state in one call instead of tailing logs:

  1. A ring buffer of the last N WARNING+ log records (RingBufferHandler).
  2. Data-source outcome counters (yfinance batch success rate, FRED series
     loaded/failed by name), updated by data_fetcher on every real fetch
     (cache hits don't re-record — last_fetch_at shows staleness).

Both are read-only views over process-local state: no persistence, no
write-path involvement, reset on every deploy. This is the one sanctioned
exception (alongside cache.py) to the services-are-stateless rule.
"""

import logging
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Optional

# ── Ring buffer of recent WARNING+ records ───────────────────────────────────

_LOG_BUFFER: deque = deque(maxlen=50)


class RingBufferHandler(logging.Handler):
    """Keeps the last N WARNING+ records in memory for /api/health/full."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            _LOG_BUFFER.append({
                "ts": datetime.fromtimestamp(
                    record.created, tz=timezone.utc
                ).isoformat(timespec="seconds"),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage()[:300],
            })
        except Exception:  # never let observability break the app
            self.handleError(record)


def install_log_buffer() -> None:
    """Attach the ring-buffer handler to the root logger (idempotent)."""
    root = logging.getLogger()
    if any(isinstance(h, RingBufferHandler) for h in root.handlers):
        return
    handler = RingBufferHandler(level=logging.WARNING)
    handler.setLevel(logging.WARNING)
    root.addHandler(handler)


def recent_warnings() -> list[dict]:
    """Last ≤50 WARNING+ log records, oldest first."""
    return list(_LOG_BUFFER)


# ── Data-source health counters ──────────────────────────────────────────────

_lock = threading.Lock()
_sources: dict = {
    "yfinance": {
        "batches": 0,
        "tickers_requested": 0,
        "tickers_fetched": 0,
        "last_fetch_at": None,
        "last_batch": None,  # {"fetched": n, "requested": n}
    },
    "fred": {
        "fetches": 0,
        "series_loaded": [],
        "series_failed": [],
        "last_fetch_at": None,
    },
}


def record_yfinance_batch(fetched: int, requested: int) -> None:
    """Record one yfinance batch download outcome."""
    with _lock:
        s = _sources["yfinance"]
        s["batches"] += 1
        s["tickers_requested"] += requested
        s["tickers_fetched"] += fetched
        s["last_fetch_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        s["last_batch"] = {"fetched": fetched, "requested": requested}


def record_fred_fetch(loaded: list[str], failed: list[str]) -> None:
    """Record one FRED fetch pass: which series loaded / failed, by name."""
    with _lock:
        s = _sources["fred"]
        s["fetches"] += 1
        s["series_loaded"] = sorted(loaded)
        s["series_failed"] = sorted(failed)
        s["last_fetch_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")


def source_health() -> dict:
    """Snapshot of data-source outcomes with derived success rates."""
    with _lock:
        yf = dict(_sources["yfinance"])
        fred = dict(_sources["fred"])
    requested = yf["tickers_requested"]
    yf["success_rate"] = (
        round(yf["tickers_fetched"] / requested, 3) if requested else None
    )
    fred["n_loaded"] = len(fred["series_loaded"])
    fred["n_failed"] = len(fred["series_failed"])
    return {"yfinance": yf, "fred": fred}


def reset_for_tests() -> None:
    """Test helper: clear all in-memory observability state."""
    with _lock:
        _LOG_BUFFER.clear()
        _sources["yfinance"].update({
            "batches": 0, "tickers_requested": 0, "tickers_fetched": 0,
            "last_fetch_at": None, "last_batch": None,
        })
        _sources["fred"].update({
            "fetches": 0, "series_loaded": [], "series_failed": [],
            "last_fetch_at": None,
        })
