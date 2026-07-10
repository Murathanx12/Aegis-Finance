"""
TRIAL-PEAD-IC — forward collector for the PEAD (earnings-surprise) score.

Snapshots ``pead_score:{ticker}`` for the book universe into the PIT store
each run, weekly-throttled, leak-safe — starting the forward IC clock.
Descriptive only. See `docs/TRIALS/TRIAL-PEAD-IC.md`.
"""

from __future__ import annotations

from datetime import date

from backend.services.pead_signal import compute_pead_score, fetch_pead_inputs
from backend.services.portfolio_intelligence.insider_collector import book_universe
from backend.services.portfolio_intelligence.pit_score_collector import collect_pit_scores

KEY_PREFIX = "pead_score:"


def collect_pead_scores(db_path=None, tickers=None, *, fetch=None,
                        as_of=None, throttle_days=5) -> dict:
    """Snapshot the PEAD score per book name into the PIT store.
    ``fetch`` defaults to the live yfinance fetcher; tests inject a stub."""
    fetch = fetch or fetch_pead_inputs
    aso = as_of or date.today().isoformat()

    def _score_for(ticker: str) -> tuple[float, dict]:
        s = compute_pead_score(fetch(ticker), as_of=aso)
        payload = {k: s.get(k) for k in
                   ("status", "announcement_date", "days_since_earnings",
                    "surprise_pct", "abnormal_3d_excess_return",
                    "two_way_aligned", "n_components")}
        return s["pead_score"], payload

    return collect_pit_scores(
        key_prefix=KEY_PREFIX, source="yfinance", score_for_ticker=_score_for,
        tickers=tickers if tickers is not None else book_universe(),
        db_path=db_path, as_of=aso, throttle_days=throttle_days,
    )
