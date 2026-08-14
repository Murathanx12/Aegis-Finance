"""
Aegis Finance — Insider Trading Signal
========================================

Tracks corporate insider (C-suite, directors, 10%+ owners) buying/selling
patterns from SEC filings. Insider buying is a well-documented bullish signal
(Lakonishok & Lee, 2001; Jeng, Metrick & Zeckhauser, 2003).

Key insight: Insiders sell for many reasons (diversification, estate planning,
options expiry) but they BUY for only one reason — they believe the stock is
undervalued. Cluster buying (multiple insiders buying within 30 days) is the
strongest signal.

Data sources:
  - Finnhub API (primary, if FINNHUB_API_KEY is set)
  - SEC EDGAR Form 4 filings (fallback, via edgartools)

Signals:
  - insider_sentiment: -1 (heavy selling) to +1 (heavy buying)
  - cluster_buy: Boolean — multiple insiders bought recently
  - insider_ownership_trend: increasing/stable/decreasing

References:
  - Lakonishok & Lee (2001), "Are Insider Trades Informative?"
  - Jeng, Metrick & Zeckhauser (2003), "Estimating the Returns to Insider Trading"

Usage:
    from backend.services.insider_trading import (
        get_insider_transactions, compute_insider_signal
    )
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

import numpy as np

from backend.config import api_keys

logger = logging.getLogger(__name__)


def get_insider_transactions(
    ticker: str,
    lookback_days: int = 90,
) -> Optional[dict]:
    """Fetch insider transactions for a stock.

    Tries Finnhub first, then falls back to yfinance insider data.
    """
    # Try Finnhub
    if api_keys.has("finnhub"):
        result = _fetch_finnhub_insiders(ticker, lookback_days)
        if result:
            return result

    # Fallback: yfinance insider data
    return _fetch_yfinance_insiders(ticker, lookback_days)


def _fetch_finnhub_insiders(ticker: str, lookback_days: int) -> Optional[dict]:
    """Fetch from Finnhub insider transactions API."""
    import requests

    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=lookback_days)

        url = "https://finnhub.io/api/v1/stock/insider-transactions"
        params = {
            "symbol": ticker,
            "from": start_date.strftime("%Y-%m-%d"),
            "to": end_date.strftime("%Y-%m-%d"),
            "token": api_keys.finnhub,
        }

        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if not data or "data" not in data:
            return None

        transactions = data["data"]
        if not transactions:
            # Zero Form 4 rows is NOT the same as "no insider bought". Foreign
            # private issuers file 40-F/20-F and never file Form 4 at all, so an
            # empty feed conflates "nobody traded" with "this issuer is not in
            # the Form 4 universe". Marked unclassifiable; the consumer decides.
            return {
                "ticker": ticker,
                "source": "finnhub",
                "lookback_days": lookback_days,
                "buys": [],
                "sells": [],
                "n_buys": 0,
                "n_sells": 0,
                "total_buy_value": 0,
                "total_sell_value": 0,
                "n_transactions": 0,
                "n_uncoded": 0,
                "codes_available": False,
            }

        buys = []
        sells = []
        n_uncoded = 0
        for tx in transactions:
            change = tx.get("change", 0) or 0
            # Finnhub returns the SEC Form 4 code in `transactionCode` — a
            # single letter (P/S/A/M/F/G/D). This read `transactionType`, which
            # the API returns as null on 100% of rows, so every transaction
            # arrived UNCODED and the open-market filter downstream silently
            # discarded all of it while reporting "no open-market purchases".
            # `transactionType` is kept as a fallback in case the field returns.
            tx_type = str(tx.get("transactionCode")
                          or tx.get("transactionType") or "").strip()
            if not tx_type:
                n_uncoded += 1

            entry = {
                "name": tx.get("name", "Unknown"),
                "shares": abs(change),
                "value": abs(change) * (tx.get("transactionPrice", 0) or 0),
                "date": tx.get("filingDate", ""),
                "type": tx_type,
                # A "P" on a derivative is not an open-market common-stock
                # purchase, and the opportunistic signal is about the latter.
                "is_derivative": bool(tx.get("isDerivative")),
            }

            # Classify: P = Purchase, S = Sale, A = Award/Grant, M = option
            # exercise, F = tax withholding, G = gift. The `change` sign is the
            # fallback ONLY when the code is absent — it cannot tell an
            # open-market purchase from an award, which is the whole point of
            # the opportunistic score.
            if tx_type.startswith(("P",)) or (not tx_type and change > 0):
                buys.append(entry)
            elif tx_type.startswith(("S",)) or (not tx_type and change < 0):
                sells.append(entry)
            elif change > 0:
                buys.append(entry)
            elif change < 0:
                sells.append(entry)

        total_buy_value = sum(b["value"] for b in buys)
        total_sell_value = sum(s["value"] for s in sells)

        return {
            "ticker": ticker,
            "source": "finnhub",
            "lookback_days": lookback_days,
            "buys": buys[:20],  # Limit for API response size
            "sells": sells[:20],
            "n_buys": len(buys),  # Count BEFORE truncation
            "n_sells": len(sells),
            "total_buy_value": total_buy_value,
            "total_sell_value": total_sell_value,
            # How much of the feed arrived without an SEC code. A consumer that
            # needs the code (the opportunistic score does) must be able to tell
            # "no purchases" from "no codes" — those look identical otherwise.
            "n_transactions": len(transactions),
            "n_uncoded": n_uncoded,
            "codes_available": n_uncoded < len(transactions),
        }

    except Exception as e:
        logger.warning("Finnhub insider data failed for %s: %s", ticker, e)
        return None


def _fetch_yfinance_insiders(ticker: str, lookback_days: int) -> Optional[dict]:
    """Fallback: get insider data from yfinance."""
    try:
        import yfinance as yf
        tk = yf.Ticker(ticker)

        # yfinance provides insider_transactions and insider_purchases
        purchases = getattr(tk, "insider_purchases", None)
        transactions = getattr(tk, "insider_transactions", None)

        buys = []
        sells = []

        if transactions is not None and not transactions.empty:
            for _, row in transactions.iterrows():
                tx_type = str(row.get("Text", "")).lower()
                shares = abs(row.get("Shares", 0) or 0)
                value = abs(row.get("Value", 0) or 0)

                entry = {
                    "name": row.get("Insider Trading", row.get("Insider", "Unknown")),
                    "shares": shares,
                    "value": value,
                    "date": str(row.get("Start Date", row.get("Date", ""))),
                    "type": tx_type,
                }

                if "purchase" in tx_type or "buy" in tx_type:
                    buys.append(entry)
                elif "sale" in tx_type or "sell" in tx_type:
                    sells.append(entry)

        return {
            "ticker": ticker,
            "source": "yfinance",
            "lookback_days": lookback_days,
            "buys": buys[:20],
            "sells": sells[:20],
            "n_buys": len(buys),
            "n_sells": len(sells),
            "total_buy_value": sum(b["value"] for b in buys),
            "total_sell_value": sum(s["value"] for s in sells),
        }

    except Exception as e:
        logger.warning("yfinance insider data failed for %s: %s", ticker, e)
        return None


# Open-market purchase transaction codes (SEC Form 4 / Finnhub). Code "P" is an
# open-market or private PURCHASE — the only insider transaction the literature
# finds informative (Lakonishok-Lee 2001; Cohen-Malloy-Pomorski 2012). Awards
# ("A"), option exercises ("M"), gifts ("G"), tax withholding ("F") and planned
# sales are excluded — they are routine and carry no view on value.
_OPEN_MARKET_BUY_CODES = ("P", "P - Purchase", "P-Purchase")

# Pre-registered constants for the opportunistic-buy score (TRIAL-INSIDER-IC).
CLUSTER_FULL_BUYERS = 3      # 3+ distinct buyers = full cluster signal (Lakonishok-Lee)
VALUE_SCALE_USD = 1_000_000  # $1M of open-market buying saturates the value bonus


def compute_opportunistic_buy_score(insider_data: Optional[dict]) -> dict:
    """Evidence-backed OPPORTUNISTIC OPEN-MARKET BUY score for one ticker.

    Distinct from ``compute_insider_signal`` (raw buy-vs-sell sentiment, which lumps
    in awards, option exercises and planned sales). This isolates the one signal the
    literature finds informative: open-market PURCHASES (code "P"), weighted by the
    number of DISTINCT insiders buying (cluster strength) plus a saturating dollar
    bonus. Selling is deliberately ignored (noisy — diversification/estate/options).

    Pre-registered functional form (TRIAL-INSIDER-IC):
        score = n_distinct_open_market_buyers + tanh(buy_value / $1M)
    Range ≈ [0, n+1], monotonic in the documented signal, rank-friendly for IC.

    Known v1 limitation: true routine-vs-opportunistic classification (Cohen-Malloy-
    Pomorski) needs per-insider multi-year history we don't store; the "P-code only"
    filter is the opportunistic proxy. Documented in the trial doc.
    """
    empty = {"opp_score": 0.0, "n_distinct_buyers": 0, "buy_value": 0.0,
             "cluster_buy": False, "available": True,
             "interpretation": "No open-market insider purchases"}
    unavailable = {"opp_score": None, "n_distinct_buyers": None,
                   "buy_value": None, "cluster_buy": None, "available": False}
    if not insider_data:
        return {**unavailable,
                "interpretation": "No insider feed answered for this ticker",
                "reason": "no_data"}

    # "No purchases" and "cannot tell what these transactions were" are
    # different facts and must not share a return value. Until 2026-08-11 they
    # did: the fetcher read a field the API returns as null, every transaction
    # arrived uncoded, the filter below discarded 100% of real buying, and this
    # function reported a confident 0.0 — "No open-market insider purchases" —
    # for every ticker on earth. It would have run green forever.
    # The SOURCE's own verdict outranks anything inferred from the payload.
    # `fetch_open_market_buys` now says OK_DATA / OK_EMPTY / UNAVAILABLE
    # explicitly; before it did, three different failures (dead CIK map, failed
    # submissions fetch, unreadable filings) all arrived here as an ordinary
    # empty buy list and were scored a confident 0.0.
    status = insider_data.get("status")
    if status == "UNAVAILABLE":
        reason = insider_data.get("reason", "unavailable")
        return {**unavailable,
                "interpretation": (
                    f"The Form 4 source could not answer for this ticker "
                    f"({reason}) — this is NOT evidence of no insider buying"),
                "reason": reason}

    if insider_data.get("codes_available") is False:
        n_tx = insider_data.get("n_transactions", 0)
        if not n_tx:
            return {**unavailable,
                    "interpretation": (
                        "No Form 4 transactions in the window — this issuer may "
                        "not file Form 4 at all (foreign private issuers do "
                        "not), so silence here is not evidence of no buying"),
                    "reason": "no_transactions_in_window"}
        return {**unavailable,
                "interpretation": (
                    f"{n_tx} insider transactions found, none carrying an SEC "
                    f"transaction code — open-market purchases cannot be "
                    f"isolated"),
                "reason": "no_transaction_codes"}

    buys = insider_data.get("buys", []) or []
    open_market = [
        b for b in buys
        if str(b.get("type", "")).strip() in _OPEN_MARKET_BUY_CODES
        and (b.get("shares", 0) or 0) > 0
        and not b.get("is_derivative", False)
    ]
    if not open_market:
        return empty

    distinct_buyers = len({str(b.get("name", "")).strip().lower() for b in open_market})
    buy_value = float(sum((b.get("value", 0) or 0) for b in open_market))
    value_bonus = float(np.tanh(buy_value / VALUE_SCALE_USD))
    score = float(distinct_buyers + value_bonus)
    cluster_buy = distinct_buyers >= CLUSTER_FULL_BUYERS

    if cluster_buy:
        interp = (f"Cluster open-market buying: {distinct_buyers} distinct insiders "
                  f"purchased (${buy_value:,.0f}). Strongest insider signal.")
    elif distinct_buyers >= 1:
        interp = (f"{distinct_buyers} insider(s) bought open-market (${buy_value:,.0f}). "
                  "Single-name buy — weaker than a cluster.")
    else:
        interp = empty["interpretation"]

    return {
        "opp_score": round(score, 4),
        "n_distinct_buyers": distinct_buyers,
        "buy_value": round(buy_value, 0),
        "cluster_buy": cluster_buy,
        "available": True,
        "interpretation": interp,
    }


def compute_insider_signal(insider_data: Optional[dict]) -> dict:
    """Compute insider trading signal from transaction data.

    Returns:
        Dict with sentiment score (-1 to +1), cluster_buy flag, and interpretation.
    """
    if not insider_data or insider_data.get("n_buys", 0) + insider_data.get("n_sells", 0) == 0:
        return {
            "signal": 0.0,
            "cluster_buy": False,
            "interpretation": "No recent insider activity",
            "n_buys": 0,
            "n_sells": 0,
        }

    n_buys = insider_data.get("n_buys", 0)
    n_sells = insider_data.get("n_sells", 0)
    buy_value = insider_data.get("total_buy_value", 0)
    sell_value = insider_data.get("total_sell_value", 0)

    total_tx = n_buys + n_sells

    # Transaction count ratio
    if total_tx > 0:
        buy_ratio = n_buys / total_tx
    else:
        buy_ratio = 0.5

    # Value ratio (more important — $10M buy is more informative than 10 small buys)
    total_value = buy_value + sell_value
    if total_value > 0:
        value_buy_ratio = buy_value / total_value
    else:
        value_buy_ratio = 0.5

    # Weighted signal: 60% value ratio, 40% count ratio
    raw_signal = 0.6 * (value_buy_ratio - 0.5) * 2 + 0.4 * (buy_ratio - 0.5) * 2
    signal = float(np.clip(raw_signal, -1, 1))

    # Cluster buy detection: 3+ insiders buying within the lookback period
    cluster_buy = n_buys >= 3 and buy_ratio > 0.6

    # Interpretation
    if cluster_buy:
        interpretation = (
            f"Cluster buying detected: {n_buys} insiders purchased "
            f"(${buy_value:,.0f} total). Strong bullish signal."
        )
    elif signal > 0.3:
        interpretation = f"Net insider buying ({n_buys} buys vs {n_sells} sells). Moderately bullish."
    elif signal < -0.3:
        interpretation = f"Net insider selling ({n_sells} sells vs {n_buys} buys). Note: selling alone is not necessarily bearish."
    else:
        interpretation = f"Mixed insider activity ({n_buys} buys, {n_sells} sells). No clear signal."

    return {
        "signal": round(signal, 3),
        "cluster_buy": cluster_buy,
        "interpretation": interpretation,
        "n_buys": n_buys,
        "n_sells": n_sells,
        "buy_value": round(buy_value, 0),
        "sell_value": round(sell_value, 0),
    }
