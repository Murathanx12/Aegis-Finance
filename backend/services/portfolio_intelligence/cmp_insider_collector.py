"""
TRIAL-CMP-INSIDER-IC — forward collector for the CMP-classified opportunistic
insider signal, promoted from the brain module (BRAIN-003, the research arc's
first kill-condition survivor).

This is the successor TRIAL-INSIDER-IC's own doc pre-announced: true
routine-vs-opportunistic classification (Cohen-Malloy-Pomorski) using the
per-insider multi-year history the live feed can't provide — now shipped as the
brain module's routine-history artifact. Runs BESIDE the T9 `insider_opp:`
clock (different signal: T9 counts all open-market buyers; this drops routine
and unclassifiable buyers), never replaces it — both clocks accrue and the
forward IC comparison is itself informative.

Snapshots `insider_cmp:{ticker}` for the book universe into the PIT store,
weekly-throttled, leak-safe, descriptive only. See
docs/TRIALS/TRIAL-CMP-INSIDER-IC.md for the frozen spec and decision rule.
"""

from __future__ import annotations

from datetime import date

from backend.services.cmp_insider import (
    LIVE_FETCH_LOOKBACK_DAYS, compute_cmp_insider_score, load_artifact,
)
from backend.services.insider_form4 import fetch_open_market_buys
from backend.services.portfolio_intelligence.insider_collector import book_universe
from backend.services.portfolio_intelligence.pit_score_collector import collect_pit_scores

KEY_PREFIX = "insider_cmp:"
MAX_FILINGS = 60  # covers ~200d of Form 4s for a large cap; paced via _sec_get


def collect_cmp_insider_scores(db_path=None, tickers=None, *, fetch=None,
                               artifact=None, as_of=None, throttle_days=5) -> dict:
    """Snapshot the CMP opportunistic-buyer count per book name into the PIT
    store. ``fetch``/``artifact`` default to the live SEC fetcher and the
    bundled routine-history artifact; tests inject stubs."""
    fetch = fetch or (lambda t: fetch_open_market_buys(
        t, lookback_days=LIVE_FETCH_LOOKBACK_DAYS, max_filings=MAX_FILINGS))
    art = artifact if artifact is not None else load_artifact()
    aso = as_of or date.today().isoformat()

    def _score_for(ticker: str) -> tuple[float, dict]:
        data = fetch(ticker) or {}
        return compute_cmp_insider_score(ticker, data.get("buys") or [], aso, art)

    return collect_pit_scores(
        key_prefix=KEY_PREFIX, source="sec_form4_cmp", score_for_ticker=_score_for,
        tickers=tickers if tickers is not None else book_universe(),
        db_path=db_path, as_of=aso, throttle_days=throttle_days,
    )
