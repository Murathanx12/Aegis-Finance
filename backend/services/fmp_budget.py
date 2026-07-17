"""Process-wide FMP daily-quota ledger (2026-07-17).

FMP's free tier is ~250 requests/day shared by an unbounded set of callers:
the provider-registry fallback (equity history / snapshots / fundamentals /
analyst estimates — the big drain, amplified when yfinance 401-storms push
traffic onto the fallback), ESG lookups, and the pre-registered congress-IC
collector. The collector died on 402 at its 07:30 ET slot (2026-07-17)
because fallback traffic had burned the whole quota overnight — a
scheduling fix cannot protect an unmetered shared resource. This ledger
meters it, same pattern as the LLM spend guard:

- Background/fallback callers call ``try_spend()`` and MUST honor a False
  by skipping the HTTP call (the provider registry then falls through to
  its next provider; ESG returns its cached/None path).
- Priority callers (pre-registered forward collectors) pass
  ``priority=True`` and may draw down the reserved slice.
- A live 402 calls ``mark_exhausted()`` so every subsequent caller
  fast-fails locally instead of burning round-trips on a dead quota.

Best-effort by design: in-memory, resets on process restart, day boundary
is UTC (FMP's observed reset). A restarted process undercounts until its
first 402 re-marks exhaustion — still strictly better than no meter.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from backend.config import config

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_STATE = {"date": None, "spent": 0, "exhausted": False, "denied": 0}


def _cfg() -> tuple[int, int]:
    fmp_cfg = config.get("fmp", {})
    return int(fmp_cfg.get("daily_budget", 240)), int(fmp_cfg.get("priority_reserve", 40))


def _rollover_locked() -> None:
    today = datetime.now(timezone.utc).date().isoformat()
    if _STATE["date"] != today:
        if _STATE["date"] is not None and (_STATE["spent"] or _STATE["denied"]):
            logger.info("FMP budget day rolled: %s spent=%d denied=%d exhausted=%s",
                        _STATE["date"], _STATE["spent"], _STATE["denied"], _STATE["exhausted"])
        _STATE.update(date=today, spent=0, exhausted=False, denied=0)


def try_spend(n: int = 1, priority: bool = False) -> bool:
    """Reserve `n` FMP requests from today's budget. Returns False when the
    caller must NOT make the HTTP call."""
    budget, reserve = _cfg()
    with _LOCK:
        _rollover_locked()
        if _STATE["exhausted"]:
            _STATE["denied"] += n
            return False
        ceiling = budget if priority else budget - reserve
        if _STATE["spent"] + n > ceiling:
            _STATE["denied"] += n
            if not priority and _STATE["spent"] <= ceiling:
                # log once, at the moment the non-priority ceiling is first hit
                logger.info("FMP non-priority budget spent (%d/%d) — reserve of %d "
                            "held for priority collectors", _STATE["spent"], budget, reserve)
            return False
        _STATE["spent"] += n
        return True


def mark_exhausted() -> None:
    """Record a live 402: the day's quota is gone regardless of our count
    (other processes / a restart may have spent it)."""
    with _LOCK:
        _rollover_locked()
        if not _STATE["exhausted"]:
            logger.warning("FMP quota exhausted (live 402) — fast-failing all FMP "
                           "calls until the UTC day rolls; ledger had counted %d",
                           _STATE["spent"])
        _STATE["exhausted"] = True


def snapshot() -> dict:
    """Observability: current day's ledger state."""
    budget, reserve = _cfg()
    with _LOCK:
        _rollover_locked()
        return {
            "date": _STATE["date"],
            "spent": _STATE["spent"],
            "denied": _STATE["denied"],
            "exhausted": _STATE["exhausted"],
            "daily_budget": budget,
            "priority_reserve": reserve,
        }


def _reset_for_tests() -> None:
    with _LOCK:
        _STATE.update(date=None, spent=0, exhausted=False, denied=0)
