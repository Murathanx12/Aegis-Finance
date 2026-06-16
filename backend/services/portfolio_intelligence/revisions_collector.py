"""
TRIAL-REVISIONS-IC — forward collector for the analyst revision-momentum signal.

The roadmap "flip": rank by the FLOW of analyst revisions/upgrades (dated Raises/
Lowers + grade up/downs over 90d), NOT by raw implied upside. Snapshots
``revisions_score:{ticker}`` for the book universe into the PIT store each run,
weekly-throttled, leak-safe — starting the forward IC clock. Descriptive only.
See `docs/TRIALS/TRIAL-REVISIONS-IC.md`.
"""

from __future__ import annotations

from datetime import date

from backend.services.estimate_revisions import (
    compute_revision_momentum_score, fetch_revision_actions,
)
from backend.services.portfolio_intelligence.insider_collector import book_universe
from backend.services.portfolio_intelligence.pit_score_collector import collect_pit_scores

KEY_PREFIX = "revisions_score:"
WINDOW_DAYS = 90


def collect_revision_scores(db_path=None, tickers=None, *, fetch=None,
                            as_of=None, throttle_days=5) -> dict:
    """Snapshot the revision-momentum score per book name into the PIT store.
    ``fetch`` defaults to the live yfinance fetcher; tests inject a stub."""
    fetch = fetch or fetch_revision_actions
    aso = as_of or date.today().isoformat()

    def _score_for(ticker: str) -> tuple[float, dict]:
        s = compute_revision_momentum_score(fetch(ticker), as_of=aso,
                                            window_days=WINDOW_DAYS)
        payload = {k: s[k] for k in ("raises", "lowers", "upgrades",
                                     "downgrades", "n_actions", "rating_drift")}
        return s["revisions_score"], payload

    return collect_pit_scores(
        key_prefix=KEY_PREFIX, source="yfinance", score_for_ticker=_score_for,
        tickers=tickers if tickers is not None else book_universe(),
        db_path=db_path, as_of=aso, throttle_days=throttle_days,
    )
