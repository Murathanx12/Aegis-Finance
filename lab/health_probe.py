"""
Aegis Lab — Data Source Health Probe
=======================================

Runs before a cycle starts to decide whether the engine has enough live
data to produce a meaningful session. If yfinance + FRED are both
flatlined, Claude's data snapshot is useless and we'd just waste a cycle
producing hallucinated improvements.

Returns a report the rd_loop consults:

  {
    "healthy": bool,             # overall good-to-go
    "live_sources": int,
    "total_sources": int,
    "results": {"yfinance": {...}, "fred": {...}, ...}
  }
"""

from __future__ import annotations

import os
import socket
import time


PROBE_TIMEOUT = 10  # seconds per probe


def _probe_yfinance() -> dict:
    try:
        import yfinance as yf
    except ImportError:
        return {"ok": False, "error": "yfinance not installed"}
    try:
        t0 = time.time()
        hist = yf.Ticker("SPY").history(period="5d", auto_adjust=True)
        elapsed = time.time() - t0
        if hist is None or hist.empty:
            return {"ok": False, "error": "empty history", "elapsed_s": round(elapsed, 2)}
        return {"ok": True, "rows": int(len(hist)), "elapsed_s": round(elapsed, 2)}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def _probe_fred() -> dict:
    key = os.getenv("FRED_API_KEY", "")
    if not key:
        return {"ok": False, "error": "FRED_API_KEY not set"}
    try:
        from fredapi import Fred
    except ImportError:
        return {"ok": False, "error": "fredapi not installed"}
    try:
        t0 = time.time()
        fred = Fred(api_key=key)
        series = fred.get_series("UNRATE", observation_start="2024-01-01")
        elapsed = time.time() - t0
        if series is None or series.empty:
            return {"ok": False, "error": "empty series", "elapsed_s": round(elapsed, 2)}
        return {"ok": True, "rows": int(len(series)), "elapsed_s": round(elapsed, 2)}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def _probe_dns() -> dict:
    """Quick DNS probe — distinguishes 'internet is down' from 'data API is down'."""
    try:
        socket.gethostbyname("github.com")
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def probe_all() -> dict:
    results = {
        "dns": _probe_dns(),
        "yfinance": _probe_yfinance(),
        "fred": _probe_fred(),
    }
    live = sum(1 for r in results.values() if r.get("ok"))
    total = len(results)
    # yfinance is the floor — we can tolerate FRED outages but not yf
    healthy = results["yfinance"].get("ok", False)
    return {
        "healthy": bool(healthy),
        "live_sources": live,
        "total_sources": total,
        "results": results,
    }
