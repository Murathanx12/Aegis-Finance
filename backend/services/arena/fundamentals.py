"""Universe-wide QUALITY for the arena, without touching a registered trial.

THE HOLE THIS FILLS
===================
`arena_composite` declares six factors. FEATURE-COVERAGE-AUDIT-1 measured what
actually populates them live:

    coverage_histogram: {"1": 206, "6": 1}

206 names scored on momentum alone; ONE name carrying the other five. The
composite is 12-1 momentum for 99.5% of the cross-section, and the audit
prices closing that at ~20x what fixing the aggregation was worth.

WHY NOT JUST WIDEN THE COLLECTOR
================================
`quality_collector` snapshots `quality_score:{ticker}` into the PIT store for
`book_universe()` — about twelve names — and that cross-section is REGISTERED
(`TRIAL-QUALITY-IC`). Its scores are cross-sectional; widening the collector
would change every z-score mid-trial. So the arena computes its own, over its
own universe, into its own namespace. The registered collector is untouched.

WHY yfinance AND NOT EDGAR
==========================
EDGAR is the better source and `docs/DATA_OPTIONS.md` rates it ADOPT — but
`edgartools` **hung for ~50 minutes** on the Form 4 path (CANON §412, BACKLOG
T9), which is exactly why Piotroski/quality was deferred in the first place.
A 50-minute hang inside the 17:45 arena pass would take the whole session
down. This uses `quality_signal.fetch_quality_inputs` — the existing
hang-safe yfinance path — and `compute_quality_score` — the existing PURE
scorer. Same definition of quality as the registered trial, so there are not
two things called `quality` in this codebase.

BUDGETED AND INCREMENTAL. Fundamentals change quarterly; refetching 180 names
daily would spend minutes of the pass to learn nothing. Each run refreshes at
most `budget` names whose cached score is missing or older than `MAX_AGE_DAYS`,
oldest first, so coverage fills in over a few sessions and then stays warm.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone

from backend.services.arena import store

logger = logging.getLogger(__name__)

#: A fundamental score older than this is refetched. Annual statements do not
#: move faster than this and the fetch is the expensive part.
MAX_AGE_DAYS = 45

#: Names refreshed per pass. MEASURED 2026-08-21 against the live 180-name
#: universe: 60 names took 104s (~1.7s each), 53 scored, 7 unscorable, 0
#: failed. 40 is ~70s inside the 17:45 pass and fills 180 names in four or
#: five sessions.
#:
#: The budget only governs the INITIAL fill. At a 45-day refresh the steady
#: state is 180/45 = ~4 names a day, so this is a warm-up cost, not a running
#: one — and on a fresh volume (Railway) coverage starts at 0% and climbs over
#: the first working week rather than appearing on day one.
DEFAULT_BUDGET = 40

#: Statuses `compute_quality_score` returns when it could not score. Stored so
#: "we looked and there was nothing" stays distinct from "we never looked".
UNSCORABLE = ("insufficient_fundamentals", "periods_mismatch")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def cache(root=None) -> dict:
    """{ticker: latest record}. Append-only file, last row wins."""
    out: dict[str, dict] = {}
    for r in store.read_fundamentals(root):
        t = r.get("ticker")
        if t:
            out[t] = r
    return out


def _stale(rec: dict | None, today: date) -> bool:
    if rec is None:
        return True
    try:
        seen = date.fromisoformat(str(rec.get("as_of"))[:10])
    except (TypeError, ValueError):
        return True
    return (today - seen) > timedelta(days=MAX_AGE_DAYS)


def refresh(universe: list[str], *, budget: int = DEFAULT_BUDGET,
            root=None, today: date | None = None, fetch=None,
            score=None) -> dict:
    """Refresh at most `budget` stale names. Never raises.

    `fetch`/`score` are injectable so tests never touch the network; the
    defaults are the same two functions the registered collector uses.
    """
    today = today or date.today()
    result = {"attempted": 0, "scored": 0, "unscorable": 0, "failed": 0,
              "budget": budget, "cached_before": 0, "status": "ok"}
    try:
        from backend.services.quality_signal import (
            compute_quality_score, fetch_quality_inputs,
        )
    except ImportError as exc:                                  # noqa: BLE001
        result["status"] = f"import_failed: {exc}"
        return result
    fetch = fetch or fetch_quality_inputs
    score = score or compute_quality_score

    have = cache(root)
    result["cached_before"] = len(have)
    stale = [t for t in universe if _stale(have.get(t), today)]
    # Oldest first, never-seen before that, so coverage grows monotonically
    # instead of the same few names being refetched.
    stale.sort(key=lambda t: str((have.get(t) or {}).get("as_of") or ""))
    rows = []
    for t in stale[:budget]:
        result["attempted"] += 1
        try:
            s = score(fetch(t))
        except Exception as exc:                                # noqa: BLE001
            result["failed"] += 1
            logger.warning("ARENA fundamentals failed for %s: %s", t, exc)
            continue
        status = str(s.get("status") or "ok")
        value = s.get("quality_score")
        unscorable = status in UNSCORABLE
        if unscorable:
            result["unscorable"] += 1
        else:
            result["scored"] += 1
        rows.append({
            "ts": _now(), "as_of": str(today), "ticker": t,
            # An unscorable name stores NULL, never the 0.0 the scorer
            # returns alongside its status — a fabricated in-distribution
            # value is the C6 lesson and it would sit mid-pack in a z-score.
            "quality_score": (None if unscorable else value),
            "status": status,
            "fiscal_period": s.get("fiscal_period"),
            "n_checks_passed": s.get("n_checks_passed"),
            "source": "yfinance_annual_statements",
            "scorer": "quality_signal.compute_quality_score",
        })
    if rows:
        store.append_fundamentals(rows, root)
    result["stale_remaining"] = max(0, len(stale) - budget)
    result["written"] = len(rows)
    return result


def scores(root=None, *, today: date | None = None,
           max_age_days: int = MAX_AGE_DAYS * 4) -> dict[str, float]:
    """{ticker: quality_score} for names with a usable, not-ancient value.

    A score far past its refresh age is dropped rather than served: the
    registered collector treats an observation older than its staleness bound
    as ABSENT (`multifactor.STALENESS_DAYS`), and a factor that silently goes
    stale is a factor that silently stops meaning anything.
    """
    today = today or date.today()
    out: dict[str, float] = {}
    for t, r in cache(root).items():
        if r.get("quality_score") is None:
            continue
        try:
            seen = date.fromisoformat(str(r.get("as_of"))[:10])
        except (TypeError, ValueError):
            continue
        if (today - seen) > timedelta(days=max_age_days):
            continue
        out[t] = float(r["quality_score"])
    return out


def coverage(universe: list[str], root=None, **kw) -> dict:
    """How much of the universe this factor actually reaches — the number
    FEATURE-COVERAGE-AUDIT-1 had to reconstruct."""
    s = scores(root, **kw)
    hit = [t for t in universe if t in s]
    return {"universe_n": len(universe), "scored_n": len(hit),
            "coverage_pct": (round(100.0 * len(hit) / len(universe), 1)
                             if universe else 0.0)}


def _cli() -> None:  # pragma: no cover - manual driver
    from backend.services.arena import discovery
    u = discovery.candidate_universe()
    print(json.dumps(refresh(u), indent=2))
    print(json.dumps(coverage(u), indent=2))


if __name__ == "__main__":  # pragma: no cover
    _cli()
