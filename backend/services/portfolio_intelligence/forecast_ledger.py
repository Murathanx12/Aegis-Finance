"""
TRIAL-FORECAST-LEDGER — Model vs Street forecast-error ledger.

Weekly PIT snapshots pairing the engine's MC-implied 1-year median return
with the Wall Street consensus target-implied return for the same ticker on
the same date, scored at 12-month maturity. A MEASUREMENT of forecast
quality, never a signal: nothing here arms a lane or emits buy/sell language.

Frozen protocol: docs/TRIALS/TRIAL-FORECAST-LEDGER-model-vs-street.md
(pre-registered 2026-07-16; earliest decision date 2027-07-16).

Data source is the cached screener computation — price, MC median and street
mean target come from the SAME snapshot, so the two forecast families are
never timing-mismatched, and collection costs zero extra network calls.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)

TRIAL_PARAM = "forecast-ledger-model-vs-street"
KEY_PREFIX = "fcast:model1y:"
_SCREENER_MAX_STALE_S = 24 * 3600  # accept a screener snapshot up to a day old

DECISION_RULE = {
    "trial": "TRIAL-FORECAST-LEDGER",
    "doc": "docs/TRIALS/TRIAL-FORECAST-LEDGER-model-vs-street.md",
    "purpose": "measurement (forecast calibration), never a trading signal",
    "hypothesis": (
        "MC-implied 1y median return has MAE <= street target-implied return "
        "MAE over matured 12-month windows, with smaller optimistic bias"
    ),
    "primary_metric": "paired MAE (model vs street) + mean signed error, 12m maturity",
    "outcome": "realized simple price return over 365 calendar days from as_of",
    "derivation_model_1y_pct": "((1 + mc_median_5y_return/100)**(1/5) - 1) * 100",
    "derivation_street_1y_pct": "(street_target_mean/price - 1) * 100",
    "min_window": ">=30 matured (ticker, as_of) pairs across >=2 collection dates",
    "earliest_decision": "2027-07-16",
    "crash_override": "SPY -20% drawdown defers decisions to >=6mo past trough",
    "constraints": "never arms a lane; no buy/sell language; formulas frozen",
}


def ensure_forecast_ledger_trial(db_path=None) -> int:
    """Idempotently register the trial row (pattern: ensure_crash2_trial)."""
    from backend.services.portfolio_intelligence.trial_registry import (
        ensure_trial_registered,
    )
    return ensure_trial_registered(TRIAL_PARAM, DECISION_RULE, db_path=db_path)


def _model_1y_pct(mc_median_5y_pct: float) -> float:
    """Frozen derivation — annualize the MC 5y median (percent in, percent out)."""
    return ((1.0 + mc_median_5y_pct / 100.0) ** (1.0 / 5.0) - 1.0) * 100.0


def collect_forecast_snapshots(db_path=None) -> dict:
    """Snapshot model-vs-street forecast pairs from the cached screener.

    Reads the screener cache (stale up to 24h is fine — price/MC/target come
    from one computation); a missing cache is DISCLOSED, never silent.
    """
    from backend.cache import cache_peek
    from backend.services.portfolio_intelligence.pit_score_collector import (
        collect_pit_scores,
    )

    screener, age = cache_peek("stock_screener", max_stale=_SCREENER_MAX_STALE_S)
    stocks = (screener or {}).get("stocks") or []
    if not stocks:
        logger.warning(
            "Forecast ledger: no screener cache available (age=%s) — "
            "skipping this collection, will retry next daily check", age,
        )
        return {"status": "no_screener_cache", "n": 0}

    rows = {s["ticker"]: s for s in stocks if s.get("ticker")}

    def score_for_ticker(ticker: str) -> tuple[float, dict]:
        s = rows[ticker]
        price = s.get("current_price")
        mc5 = s.get("mc_median_5y_return")
        street = s.get("analyst_target")
        if not price or price <= 0 or mc5 is None or not street or street <= 0:
            # Missing either forecast → recorded but excluded from scoring
            return 0.0, {"missing": True, "price": price,
                         "mc_median_5y_pct": mc5, "street_target_mean": street}
        model_1y = _model_1y_pct(float(mc5))
        street_1y = (float(street) / float(price) - 1.0) * 100.0
        return round(model_1y, 4), {
            "price": round(float(price), 4),
            "street_target_mean": round(float(street), 4),
            "street_1y_pct": round(street_1y, 4),
            "mc_median_5y_pct": round(float(mc5), 4),
            "as_of_source": "screener_cache",
        }

    return collect_pit_scores(
        key_prefix=KEY_PREFIX,
        source="screener_cache",
        score_for_ticker=score_for_ticker,
        tickers=sorted(rows),
        db_path=db_path,
        throttle_days=5,
    )


def score_matured_forecasts(db_path=None, min_pairs: int = 30) -> dict:
    """Evaluate matured (>=365d) forecast pairs against realized returns.

    Returns insufficient_forward_data until the frozen minimum window is met
    (>=30 matured pairs across >=2 collection dates). Network: one shared
    history fetch per distinct ticker with matured rows.
    """
    import json

    from backend.db import get_connection

    cutoff = (date.today() - timedelta(days=365)).isoformat()
    conn = get_connection(db_path)
    try:
        matured = conn.execute(
            "SELECT key, as_of, value, payload FROM pit_observations "
            "WHERE key LIKE ? AND as_of <= ? ORDER BY as_of",
            (KEY_PREFIX + "%", cutoff),
        ).fetchall()
    finally:
        conn.close()

    pairs = []
    for row in matured:
        try:
            payload = json.loads(row["payload"]) if row["payload"] else {}
        except (TypeError, ValueError):
            payload = {}
        if payload.get("missing"):
            continue
        pairs.append({
            "ticker": row["key"][len(KEY_PREFIX):],
            "as_of": row["as_of"],
            "model_1y_pct": float(row["value"]),
            "street_1y_pct": payload.get("street_1y_pct"),
            "price_at_forecast": payload.get("price"),
        })

    dates = {p["as_of"] for p in pairs}
    if len(pairs) < min_pairs or len(dates) < 2:
        return {
            "status": "insufficient_forward_data",
            "matured_pairs": len(pairs),
            "collection_dates": len(dates),
            "min_pairs": min_pairs,
            "earliest_decision": DECISION_RULE["earliest_decision"],
        }

    # Realized 365d return per pair (close nearest as_of+365, ±7 trading days)
    from backend.services.data_fetcher import fetch_ticker_history

    scored = []
    hist_cache: dict = {}
    for p in pairs:
        t = p["ticker"]
        try:
            if t not in hist_cache:
                hist_cache[t] = fetch_ticker_history(t, period="5y")
            hist = hist_cache[t]
            if hist is None or hist.empty:
                continue
            target_d = date.fromisoformat(p["as_of"]) + timedelta(days=365)
            closes = hist["Close"]
            idx_dates = [d.date() if hasattr(d, "date") else d for d in closes.index]
            candidates = [
                (abs((d - target_d).days), float(closes.iloc[i]))
                for i, d in enumerate(idx_dates)
                if abs((d - target_d).days) <= 10
            ]
            if not candidates or not p["price_at_forecast"]:
                continue
            realized_price = min(candidates)[1]
            realized_pct = (realized_price / p["price_at_forecast"] - 1.0) * 100.0
            scored.append({
                **p,
                "realized_1y_pct": round(realized_pct, 4),
                "ae_model": abs(p["model_1y_pct"] - realized_pct),
                "ae_street": (abs(p["street_1y_pct"] - realized_pct)
                              if p["street_1y_pct"] is not None else None),
            })
        except Exception as e:
            logger.warning("Forecast ledger scoring failed for %s: %s", t, e)

    both = [s for s in scored if s["ae_street"] is not None]
    if len(both) < min_pairs:
        return {"status": "insufficient_forward_data",
                "matured_pairs": len(both), "min_pairs": min_pairs,
                "earliest_decision": DECISION_RULE["earliest_decision"]}

    n = len(both)
    mae_model = sum(s["ae_model"] for s in both) / n
    mae_street = sum(s["ae_street"] for s in both) / n
    bias_model = sum(s["model_1y_pct"] - s["realized_1y_pct"] for s in both) / n
    bias_street = sum(s["street_1y_pct"] - s["realized_1y_pct"] for s in both) / n
    return {
        "status": "scored",
        "n_pairs": n,
        "mae_model_pct": round(mae_model, 3),
        "mae_street_pct": round(mae_street, 3),
        "bias_model_pct": round(bias_model, 3),
        "bias_street_pct": round(bias_street, 3),
        "note": ("Measurement per TRIAL-FORECAST-LEDGER; no decisions before "
                 + DECISION_RULE["earliest_decision"]),
    }
