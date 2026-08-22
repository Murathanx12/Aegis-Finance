"""Process-wide serialization of memory-heavy background work.

Why this exists: the API process also runs endpoint cache warming, PI
prewarming, and the in-process scheduler. On 2026-08-21 the process restarted
4x in 71 minutes with no traceback (the OOM signature) and the arena's first
seeded pass died mid-run; RSS sampling the next morning measured a 3,663 MB
spike at uptime ~8 min against a ~815 MB steady state. No single compute needs
that much — the failure mode is STACKING: two multi-GB background computes
(FinBERT load, scenario Monte Carlo, 80-ticker screener, arena pass) running
at the same moment. This module makes that impossible by putting every heavy
background compute behind one gate.

Rules:
- BACKGROUND work only. Request-path code must never acquire the gate — that
  would trade a rare OOM for routine user-visible latency.
- The gate never deadlocks a caller forever: acquisition times out and the
  work then RUNS ANYWAY with a loud log line. A stuck holder must not starve
  the scheduler — an unserialized run is a risk, a silently skipped close
  mark is an unrecoverable gap.
- Every acquire/release samples RSS, and a daemon sampler fills in the middle,
  so the high-water mark carries the NAME of what was running at the peak.
  /api/health/full surfaces it; the next OOM investigation starts with a
  suspect instead of a guess.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator

logger = logging.getLogger(__name__)

#: One heavy compute at a time. Everything that matters here — scheduler jobs,
#: the endpoint warm loop, PI prewarm — is async on the ONE event loop, so an
#: asyncio primitive is both sufficient and required: a threading acquire
#: inside an async job would stall the whole loop while waiting.
#: Created lazily PER LOOP: asyncio primitives bind to the first loop that
#: awaits them, and test suites run many short-lived loops via asyncio.run().
#: In production uvicorn has exactly one loop, so this is one gate forever.
_gate: asyncio.Semaphore | None = None
_gate_loop: asyncio.AbstractEventLoop | None = None
_state_lock = threading.Lock()


def _get_gate() -> asyncio.Semaphore:
    global _gate, _gate_loop
    loop = asyncio.get_running_loop()
    if _gate is None or _gate_loop is not loop:
        _gate = asyncio.Semaphore(1)
        _gate_loop = loop
    return _gate
_current: str | None = None
_high_water: dict = {"rss_mb": None, "at": None, "during": None}

#: Waiting longer than this means the holder is stuck (every legitimate
#: holder finishes in minutes); run unserialized and say so loudly.
GATE_TIMEOUT_S = 15 * 60

_SAMPLER_INTERVAL_S = 30
_sampler_started = False


def rss_mb() -> float | None:
    """Resident set size in MB from /proc/self/status. None off-Linux."""
    try:
        with open("/proc/self/status", encoding="ascii", errors="ignore") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return round(int(line.split()[1]) / 1024.0, 1)
    except OSError:
        return None
    return None


def note_rss(context: str | None = None) -> float | None:
    """Sample RSS and advance the high-water mark. One /proc read — cheap
    enough to piggyback on any periodic caller."""
    mb = rss_mb()
    if mb is None:
        return None
    with _state_lock:
        if _high_water["rss_mb"] is None or mb > _high_water["rss_mb"]:
            _high_water["rss_mb"] = mb
            _high_water["at"] = datetime.now(timezone.utc).isoformat(
                timespec="seconds")
            _high_water["during"] = _current or context
    return mb


def high_water() -> dict:
    """The peak RSS seen this process lifetime, when, and what held the gate
    at that moment (None = nothing gated was running — the peak came from the
    request path or an ungated task, which is itself a finding)."""
    with _state_lock:
        return {**_high_water, "now_running": _current}


@asynccontextmanager
async def heavy(name: str, timeout_s: float = GATE_TIMEOUT_S) -> AsyncIterator[None]:
    """Serialize a memory-heavy background compute behind the process gate.

    Usage: ``async with heavy("job:pi_arena_daily"): ...`` — the body should
    push its blocking compute through ``asyncio.to_thread`` as before; the
    gate only decides WHEN it may start, never where it runs.
    """
    global _current
    gate = _get_gate()
    try:
        await asyncio.wait_for(gate.acquire(), timeout=timeout_s)
        acquired = True
    except asyncio.TimeoutError:
        acquired = False
        # Refusing to run would silently skip scheduled work; running
        # unserialized merely restores the pre-gate world for one pass.
        logger.error(
            "heavy_work gate: %r waited %.0fs and gave up waiting on %r — "
            "running UNSERIALIZED (stacking risk this pass)",
            name, timeout_s, _current)
    with _state_lock:
        prev = _current
        _current = name if acquired else f"{name} (unserialized)"
    note_rss()
    t0 = time.time()
    try:
        yield
    finally:
        note_rss()
        with _state_lock:
            _current = prev
        if acquired:
            gate.release()
        dt = time.time() - t0
        if dt > 120:
            logger.info("heavy_work: %s held the gate %.0fs", name, dt)


def start_sampler() -> None:
    """Start the 30s RSS sampler (idempotent). Daemon thread: dies with the
    process, costs one /proc read per interval, and is what catches a spike
    in the MIDDLE of a compute rather than only at its edges."""
    global _sampler_started
    with _state_lock:
        if _sampler_started:
            return
        _sampler_started = True

    def _loop() -> None:
        while True:
            time.sleep(_SAMPLER_INTERVAL_S)
            try:
                note_rss("sampler")
            except Exception:                                   # noqa: BLE001
                pass

    threading.Thread(target=_loop, name="rss-sampler", daemon=True).start()
