"""
Generic forward PIT-score collector — the shared engine behind the forward-IC
trials (revisions, multi-factor; insider has its own bespoke copy). Snapshots a
per-ticker score into ``pit_observations`` under ``{key_prefix}{ticker}``,
weekly-throttled and leak-safe (UTC ``observed_at``), so wiring any signal into
the daily check is one thin wrapper.

A signal supplies a ``score_for_ticker(ticker) -> (value: float, payload: dict)``
closure (which does its own fetch + scoring); this engine handles throttling,
the PIT write, per-ticker failure isolation, and the summary. Descriptive only —
it writes to the PIT store and nothing else.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Callable

from backend.db import get_connection, snapshot

logger = logging.getLogger(__name__)


def _last_as_of(conn, key_prefix: str) -> str | None:
    row = conn.execute(
        "SELECT MAX(as_of) AS d FROM pit_observations WHERE key LIKE ?",
        (key_prefix + "%",),
    ).fetchone()
    return row["d"] if row and row["d"] else None


def collect_pit_scores(*, key_prefix: str, source: str,
                       score_for_ticker: Callable[[str], tuple[float, dict]],
                       tickers: list[str], db_path=None, as_of: str | None = None,
                       throttle_days: int = 5) -> dict:
    """Snapshot each ticker's score into the PIT store. Idempotent (``snapshot``
    no-ops on unchanged) and throttled (skips if the last collection for this
    key_prefix was within ``throttle_days``). Returns a summary dict."""
    as_of = as_of or date.today().isoformat()
    conn = get_connection(db_path)
    try:
        last = _last_as_of(conn, key_prefix)
        if last is not None and throttle_days > 0:
            try:
                if date.fromisoformat(as_of) - date.fromisoformat(last) < timedelta(days=throttle_days):
                    return {"status": "throttled", "last_as_of": last, "n": 0}
            except ValueError:
                pass  # malformed stored date — fall through

        observed = datetime.now(timezone.utc).isoformat()  # UTC → leak-safe reads
        scores: dict[str, float] = {}
        written = 0
        for t in tickers:
            try:
                value, payload = score_for_ticker(t)
            except Exception as e:  # one ticker must never break the run
                logger.warning("%s score failed for %s: %s", key_prefix, t, e)
                value, payload = 0.0, {"error": True}
            scores[t] = float(value)
            rid = snapshot(conn, key_prefix + t, as_of, float(value),
                           source=source, observed_at=observed, payload=payload)
            if rid is not None:
                written += 1
        nonzero = sum(1 for v in scores.values() if v != 0)
        logger.info("%s collect: %d tickers, %d written, %d nonzero (as_of %s)",
                    key_prefix, len(tickers), written, nonzero, as_of)
        return {"status": "collected", "as_of": as_of, "n": len(tickers),
                "written": written, "nonzero": nonzero, "scores": scores}
    finally:
        conn.close()
