"""
TRIAL-QUALITY-IC — forward collector for the gross-profitability score.

Snapshots ``quality_score:{ticker}`` for the book universe into the PIT store,
weekly-throttled, leak-safe. Descriptive only. See
`docs/TRIALS/TRIAL-QUALITY-IC.md`.
"""

from __future__ import annotations

from datetime import date

from backend.services.portfolio_intelligence.insider_collector import book_universe
from backend.services.portfolio_intelligence.pit_score_collector import collect_pit_scores
from backend.services.quality_signal import compute_quality_score, fetch_quality_inputs

KEY_PREFIX = "quality_score:"


def collect_quality_scores(db_path=None, tickers=None, *, fetch=None,
                           as_of=None, throttle_days=5) -> dict:
    """Snapshot the GP/A quality score per book name into the PIT store.
    ``fetch`` defaults to the live yfinance fetcher; tests inject a stub."""
    fetch = fetch or fetch_quality_inputs
    aso = as_of or date.today().isoformat()

    def _score_for(ticker: str) -> tuple[float, dict]:
        s = compute_quality_score(fetch(ticker))
        payload = {k: s.get(k) for k in
                   ("status", "fiscal_period", "piotroski_subset",
                    "n_checks_passed")}
        return s["quality_score"], payload

    return collect_pit_scores(
        key_prefix=KEY_PREFIX, source="yfinance", score_for_ticker=_score_for,
        tickers=tickers if tickers is not None else book_universe(),
        db_path=db_path, as_of=aso, throttle_days=throttle_days,
    )
