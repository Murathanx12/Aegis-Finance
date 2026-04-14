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
            }

        buys = []
        sells = []
        for tx in transactions:
            change = tx.get("change", 0) or 0
            tx_type = tx.get("transactionType", "")

            entry = {
                "name": tx.get("name", "Unknown"),
                "shares": abs(change),
                "value": abs(change) * (tx.get("transactionPrice", 0) or 0),
                "date": tx.get("filingDate", ""),
                "type": tx_type,
            }

            # Classify: P = Purchase, S = Sale, A = Award/Grant
            if tx_type in ("P - Purchase", "P") or change > 0:
                buys.append(entry)
            elif tx_type in ("S - Sale", "S - Sale+OE", "S") or change < 0:
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
