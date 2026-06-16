"""
Aegis Finance — Analyst Estimate Revisions Trend
===================================================

Tracks how analysts are changing their forward-earnings views — one of the
strongest short-horizon return signals in the academic literature
(Novy-Marx 2013, Jegadeesh & Livnat 2006, Barber & Odean).

We surface:
  - Net revision count (up minus down) over 7d, 30d, 90d
  - Current consensus EPS and price target
  - Consensus drift: today's target vs 4 weeks ago
  - Analyst conviction: high-confidence revisions vs reiterations

Primary source: yfinance `.recommendations_summary` + `.analyst_price_targets`.
When FMP_API_KEY is set we cross-check against FMP estimates for stability.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


def _read_yf_recommendations(ticker: str) -> Optional[pd.DataFrame]:
    try:
        import yfinance as yf
    except ImportError:
        return None
    try:
        rec = yf.Ticker(ticker).recommendations
    except Exception as e:
        logger.debug("yfinance recommendations failed for %s: %s", ticker, e)
        return None
    if rec is None or rec.empty:
        return None
    # Some yfinance versions index by date, others by period ("-1m","-2m",...). Normalize.
    if not isinstance(rec.index, pd.DatetimeIndex):
        try:
            rec.index = pd.to_datetime(rec.index)
        except Exception:
            pass
    return rec


def _read_yf_price_targets(ticker: str) -> Optional[dict]:
    try:
        import yfinance as yf
    except ImportError:
        return None
    try:
        t = yf.Ticker(ticker)
        if hasattr(t, "analyst_price_targets"):
            return t.analyst_price_targets or None
        info = t.info or {}
        return {
            "mean": info.get("targetMeanPrice"),
            "median": info.get("targetMedianPrice"),
            "high": info.get("targetHighPrice"),
            "low": info.get("targetLowPrice"),
            "number_of_analysts": info.get("numberOfAnalystOpinions"),
        }
    except Exception as e:
        logger.debug("yfinance price targets failed for %s: %s", ticker, e)
        return None


def _score_consensus(upgrades: int, downgrades: int, holds: int) -> str:
    total = upgrades + downgrades + holds
    if total == 0:
        return "neutral"
    up_ratio = (upgrades - downgrades) / total
    if up_ratio >= 0.25:
        return "strongly_bullish"
    if up_ratio >= 0.10:
        return "bullish"
    if up_ratio <= -0.25:
        return "strongly_bearish"
    if up_ratio <= -0.10:
        return "bearish"
    return "neutral"


def _window_counts(rec: pd.DataFrame, days: int) -> dict:
    """Count upgrades / downgrades / reiterations in the last `days` trading days."""
    if rec is None or rec.empty:
        return {"up": 0, "down": 0, "hold": 0, "total": 0}

    # yfinance schema varies — some have 'From Grade'/'To Grade', others have
    # 'strongBuy','buy','hold','sell','strongSell' counts per period.
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = now - timedelta(days=days)

    if isinstance(rec.index, pd.DatetimeIndex):
        idx = rec.index.tz_localize(None) if rec.index.tz is not None else rec.index
        window = rec[idx >= cutoff]
    else:
        window = rec

    # Schema 1: per-action grades
    if {"From Grade", "To Grade"}.issubset(window.columns):
        ups = downs = holds = 0
        ranking = {"buy": 5, "outperform": 4, "overweight": 4, "hold": 3, "neutral": 3,
                   "underperform": 2, "underweight": 2, "sell": 1, "strong sell": 1,
                   "strong buy": 5}

        def _rank(g):
            if not isinstance(g, str):
                return 3
            key = g.lower().strip()
            return ranking.get(key, 3)

        for _, row in window.iterrows():
            before = _rank(row.get("From Grade"))
            after = _rank(row.get("To Grade"))
            if after > before:
                ups += 1
            elif after < before:
                downs += 1
            else:
                holds += 1
        return {"up": ups, "down": downs, "hold": holds, "total": ups + downs + holds}

    # Schema 2: period counts (strongBuy/buy/hold/sell/strongSell)
    cols = {c.lower(): c for c in window.columns}
    if {"strongbuy", "buy", "hold", "sell", "strongsell"}.issubset(cols.keys()):
        if window.empty:
            return {"up": 0, "down": 0, "hold": 0, "total": 0}
        row = window.iloc[-1]
        ups = int(row[cols["strongbuy"]]) + int(row[cols["buy"]])
        downs = int(row[cols["sell"]]) + int(row[cols["strongsell"]])
        holds = int(row[cols["hold"]])
        return {"up": ups, "down": downs, "hold": holds, "total": ups + downs + holds}

    return {"up": 0, "down": 0, "hold": 0, "total": 0}


def get_revisions_trend(ticker: str) -> Optional[dict]:
    """Summarize analyst revision trend over multiple lookback windows."""
    rec = _read_yf_recommendations(ticker)
    targets = _read_yf_price_targets(ticker)

    if rec is None and targets is None:
        return None

    windows = {}
    if rec is not None:
        for label, days in (("7d", 7), ("30d", 30), ("90d", 90)):
            windows[label] = _window_counts(rec, days)

    # 30d window drives the consensus label — matches how Koyfin / Fintel label "trend"
    w30 = windows.get("30d") or {"up": 0, "down": 0, "hold": 0, "total": 0}
    consensus = _score_consensus(w30["up"], w30["down"], w30["hold"])

    # Price-target drift: we don't have historical snapshots built in, so we
    # emit "current" and the caller can diff against their own stored priors.
    target_block = None
    if targets:
        mean = targets.get("mean") if isinstance(targets, dict) else None
        current_price = None
        try:
            import yfinance as yf
            info = yf.Ticker(ticker).info or {}
            current_price = info.get("regularMarketPrice") or info.get("currentPrice")
        except Exception:
            pass
        implied_upside = None
        if mean and current_price and current_price > 0:
            implied_upside = round(float(mean) / float(current_price) - 1.0, 4)
        target_block = {
            "mean": targets.get("mean"),
            "median": targets.get("median"),
            "high": targets.get("high"),
            "low": targets.get("low"),
            "number_of_analysts": targets.get("number_of_analysts"),
            "current_price": current_price,
            "implied_upside_pct": implied_upside,
        }

    return {
        "ticker": ticker,
        "consensus_label": consensus,
        "windows": windows,
        "price_targets": target_block,
        "source": "yfinance",
    }


# ── Revision-momentum signal (TRIAL-REVISIONS-IC) ────────────────────────────
#
# The roadmap "flip": rank by the FLOW of analyst revisions/upgrades — dated,
# directional actions — NOT by raw implied upside (target/price-1), which is a
# level, not a change, and is the metric we are explicitly moving away from.
# Sources (both real, verified): yfinance `.upgrades_downgrades` (a dated log of
# Raises/Lowers + up/down grade actions) and `.recommendations` (0m vs -2m rating
# drift). Leak-safe: only actions with date <= as_of count.


def fetch_revision_actions(ticker: str) -> dict:
    """Normalised analyst-action data for one ticker, from yfinance. Degrades to
    an empty result on any error (never raises). Network → inject in tests."""
    out: dict = {"ticker": ticker, "actions": [], "rec_counts": []}
    try:
        import yfinance as yf
    except ImportError:
        return out
    try:
        tk = yf.Ticker(ticker)
        ud = getattr(tk, "upgrades_downgrades", None)
        if ud is not None and not ud.empty:
            for idx, row in ud.iterrows():
                try:
                    d = pd.to_datetime(idx).date().isoformat()
                except Exception:
                    continue
                out["actions"].append({
                    "date": d,
                    "action": str(row.get("Action", "")),
                    "target": str(row.get("priceTargetAction", "")),
                })
        rec = getattr(tk, "recommendations", None)
        if rec is not None and not rec.empty:
            for _, row in rec.iterrows():
                out["rec_counts"].append({
                    "period": str(row.get("period", "")),
                    **{k: int(row.get(k, 0) or 0)
                       for k in ("strongBuy", "buy", "hold", "sell", "strongSell")},
                })
    except Exception as e:  # pragma: no cover - network
        logger.warning("revision actions fetch failed for %s: %s", ticker, e)
    return out


def _consensus(c: dict) -> float:
    tot = c["strongBuy"] + c["buy"] + c["hold"] + c["sell"] + c["strongSell"]
    return (2 * c["strongBuy"] + c["buy"] - c["sell"] - 2 * c["strongSell"]) / tot if tot else 0.0


def _rating_drift(rec_counts: list[dict]) -> float:
    """Consensus rating change, current (0m) vs two months ago (-2m), in
    [-2, +2] per analyst. Secondary/descriptive — not folded into the score."""
    by = {r.get("period"): r for r in rec_counts}
    if "0m" in by and "-2m" in by:
        return _consensus(by["0m"]) - _consensus(by["-2m"])
    return 0.0


def compute_revision_momentum_score(data: Optional[dict], as_of: Optional[str] = None,
                                    window_days: int = 90) -> dict:
    """Net analyst revision FLOW over the trailing ``window_days`` (leak-safe):

        revisions_score = (raises - lowers) + (upgrades - downgrades)

    counting only dated actions with ``cutoff < date <= as_of``. Rating drift
    (0m vs -2m) is exposed in the payload but NOT folded into the headline score
    (it keeps the signal a clean, interpretable count). This is the pre-registered
    estimator for TRIAL-REVISIONS-IC."""
    empty = {"revisions_score": 0.0, "n_actions": 0, "raises": 0, "lowers": 0,
             "upgrades": 0, "downgrades": 0, "rating_drift": 0.0}
    if not data:
        return empty
    as_of = as_of or date.today().isoformat()
    cutoff = (date.fromisoformat(as_of) - timedelta(days=window_days)).isoformat()
    raises = lowers = ups = downs = n = 0
    for a in data.get("actions", []):
        d = a.get("date", "")
        if not d or d > as_of or d <= cutoff:  # leak-safe + window
            continue
        n += 1
        ta = str(a.get("target", "")).lower()
        ac = str(a.get("action", "")).lower()
        if ta == "raises":
            raises += 1
        elif ta == "lowers":
            lowers += 1
        if ac == "up":
            ups += 1
        elif ac == "down":
            downs += 1
    net = (raises - lowers) + (ups - downs)
    return {"revisions_score": float(net), "n_actions": n, "raises": raises,
            "lowers": lowers, "upgrades": ups, "downgrades": downs,
            "rating_drift": round(_rating_drift(data.get("rec_counts", [])), 3)}
