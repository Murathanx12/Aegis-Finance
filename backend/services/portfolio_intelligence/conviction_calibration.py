"""
Conviction calibration — grade the judgment, not just the P&L (V5)
==================================================================

For every logged conviction decision, compute the ticker's realized forward
return at 21/63/126 trading days and grade the CALL: a buy-side decision
(enter/add) is right when the forward return is positive; a sell-side decision
(trim/exit) is right when it is negative (the return avoided). Grouping by the
logged 1-5 conviction level yields Murat's own reliability curve — does
conviction 5 actually outperform conviction 2?

This is process-memory, not training data: the scorecard is descriptive,
read-only, and never feeds an optimizer (CANON prime rule / §4 — no learning
on P&L; the brain gets graded the same honest way the lanes do).

Only MATURED horizons count (decision date + horizon trading days fully
elapsed). Unmatured decisions are reported as pending, never guessed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

logger = logging.getLogger(__name__)

HORIZONS_TD = (21, 63, 126)  # trading days ≈ 1m / 3m / 6m
BUY_ACTIONS = {"enter", "add"}
SELL_ACTIONS = {"trim", "exit"}

CALIBRATION_LABEL = (
    "descriptive reliability curve of logged conviction decisions — "
    "process memory, never a training signal; no skill claim before 24 months"
)


@dataclass
class GradedDecision:
    decision_id: int
    ticker: str
    action: str
    conviction: int
    decided_on: str                    # ISO date
    horizons: dict                     # h -> {"fwd_return", "call_return", "matured"}


def _forward_return(prices: pd.Series, start_date: str, horizon_td: int):
    """(forward simple return, matured) from the first close ON/AFTER start_date
    to `horizon_td` trading days later. Not matured (or no data) → (None, False)."""
    s = prices.dropna()
    if s.empty:
        return None, False
    idx = s.index.searchsorted(pd.Timestamp(start_date))
    if idx >= len(s):
        return None, False
    end = idx + horizon_td
    if end >= len(s):
        return None, False  # horizon not yet matured
    p0, p1 = float(s.iloc[idx]), float(s.iloc[end])
    if p0 <= 0:
        return None, False
    return p1 / p0 - 1.0, True


def grade_decisions(decisions: list[dict], prices_by_ticker: dict[str, pd.Series],
                    horizons=HORIZONS_TD) -> list[GradedDecision]:
    """Pure grading: signed 'call return' per decision per horizon.

    call_return = fwd_return for buy-side, -fwd_return for sell-side —
    positive always means "the call was right".
    """
    graded: list[GradedDecision] = []
    for d in decisions:
        action = str(d.get("action", "")).lower()
        if action not in BUY_ACTIONS | SELL_ACTIONS:
            continue
        sign = 1.0 if action in BUY_ACTIONS else -1.0
        prices = prices_by_ticker.get(str(d.get("ticker", "")).upper())
        decided_on = str(d.get("timestamp", ""))[:10]
        hz: dict = {}
        for h in horizons:
            if prices is None:
                hz[h] = {"fwd_return": None, "call_return": None, "matured": False}
                continue
            fwd, matured = _forward_return(prices, decided_on, h)
            hz[h] = {
                "fwd_return": None if fwd is None else round(fwd, 4),
                "call_return": None if fwd is None else round(sign * fwd, 4),
                "matured": matured,
            }
        graded.append(GradedDecision(
            decision_id=int(d.get("id", 0)), ticker=str(d.get("ticker", "")).upper(),
            action=action, conviction=int(d.get("conviction", 0)),
            decided_on=decided_on, horizons=hz,
        ))
    return graded


def reliability_curve(graded: list[GradedDecision], horizons=HORIZONS_TD) -> dict:
    """Mean call_return + hit rate per conviction level per horizon (matured
    only), with honest counts. Sparse buckets are shown sparse, never smoothed."""
    curve: dict = {}
    for level in range(1, 6):
        row: dict = {}
        for h in horizons:
            vals = [g.horizons[h]["call_return"] for g in graded
                    if g.conviction == level and g.horizons[h]["matured"]]
            row[str(h)] = {
                "n": len(vals),
                "mean_call_return": round(sum(vals) / len(vals), 4) if vals else None,
                "hit_rate": round(sum(1 for v in vals if v > 0) / len(vals), 3)
                if vals else None,
            }
        curve[str(level)] = row
    return curve


def _default_price_fetch(tickers: list[str], start: str) -> dict[str, pd.Series]:
    """Live fetch (injected away in tests): daily closes since `start`."""
    import yfinance as yf
    if not tickers:
        return {}
    px = yf.download(tickers, start=start, progress=False, auto_adjust=True)["Close"]
    if isinstance(px, pd.Series):  # single ticker
        return {tickers[0].upper(): px}
    return {str(c).upper(): px[c] for c in px.columns}


def calibration_scorecard(db_path=None, price_fetch=None) -> dict:
    """The full scorecard: read the immutable decision log, grade matured
    horizons, and report the reliability curve. Descriptive only."""
    from backend.db import get_connection, init_db, list_personal_decisions
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        decisions = list_personal_decisions(conn, limit=500)
    finally:
        conn.close()
    if not decisions:
        return {"status": "no_decisions", "n_decisions": 0,
                "label": CALIBRATION_LABEL}

    tickers = sorted({str(d["ticker"]).upper() for d in decisions})
    start = min(str(d["timestamp"])[:10] for d in decisions)
    fetch = price_fetch or _default_price_fetch
    try:
        prices = fetch(tickers, start)
    except Exception as e:
        logger.warning("Calibration price fetch failed: %s", e)
        return {"status": "prices_unavailable", "n_decisions": len(decisions),
                "label": CALIBRATION_LABEL}

    graded = grade_decisions(decisions, prices)
    n_matured = sum(1 for g in graded
                    if any(v["matured"] for v in g.horizons.values()))
    return {
        "status": "ok" if n_matured else "no_matured_horizons",
        "n_decisions": len(graded),
        "n_with_any_matured_horizon": n_matured,
        "horizons_trading_days": list(HORIZONS_TD),
        "reliability_curve": reliability_curve(graded),
        "decisions": [
            {"id": g.decision_id, "ticker": g.ticker, "action": g.action,
             "conviction": g.conviction, "decided_on": g.decided_on,
             "horizons": g.horizons}
            for g in graded
        ],
        "label": CALIBRATION_LABEL,
    }
