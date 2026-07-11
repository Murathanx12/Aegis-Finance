"""
TRIAL-SMARTGROWTH — concentrated smart-money growth basket (forward test).
===========================================================================

Murat's thesis, frozen (docs/TRIALS/TRIAL-SMARTGROWTH.md): weekly top-10
equal-weight basket from a z-scored blend of the engine's own PIT signal
streams — momentum-multifactor 0.35, revisions 0.25, smart money (congress +
ARK) 0.20, clipped analyst upside 0.20. Components missing for the whole
cross-section drop out and weights renormalize (recorded in payload).
Descriptive only; the basket surfaces as measured candidates, never advice;
adoption (vs QQQ, ≥6mo forward) seeds an attended NAV lane.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Callable, Optional

import numpy as np

from backend.db import get_connection
from backend.services.portfolio_intelligence.pit_score_collector import (
    collect_pit_scores,
)

logger = logging.getLogger(__name__)

KEY_PREFIX = "smartgrowth_pick:"
TRIAL_PARAM = "smartgrowth-basket"

# Frozen (TRIAL-SMARTGROWTH) — never tuned mid-trial.
WEIGHTS = {"momentum": 0.35, "revisions": 0.25,
           "smart_money": 0.20, "analyst_upside": 0.20}
BASKET_SIZE = 10
UPSIDE_CLIP = 0.50
MIN_ANALYSTS = 4
PREFETCH_TOP_N = 30  # analyst upside fetched for the top-30 preliminary names

_SIGNAL_PREFIXES = {
    "momentum": "multifactor_score:",
    "revisions": "revisions_score:",
    "congress": "congress_score:",
    "ark": "ark_score:",
}


def _latest_by_ticker(conn, prefix: str) -> dict[str, float]:
    """Latest (as_of, revision) value per ticker for one signal prefix."""
    rows = conn.execute(
        "SELECT key, value FROM pit_observations WHERE key LIKE ? "
        "ORDER BY as_of ASC, revision ASC",
        (prefix + "%",),
    ).fetchall()
    out: dict[str, float] = {}
    for r in rows:  # ascending → the dict keeps the latest
        out[r["key"][len(prefix):]] = float(r["value"])
    return out


def _zscores(values: dict[str, float]) -> dict[str, float]:
    if len(values) < 3:
        return {}
    arr = np.array(list(values.values()), dtype=float)
    std = float(arr.std())
    if std == 0:
        return {t: 0.0 for t in values}
    mean = float(arr.mean())
    return {t: (v - mean) / std for t, v in values.items()}


def fetch_analyst_upside(tickers: list[str]) -> dict[str, float]:
    """Clipped analyst-implied upside per ticker (≥MIN_ANALYSTS only).
    The clip + analyst floor are the T10 containment for a flawed level."""
    import yfinance as yf

    out: dict[str, float] = {}
    for t in tickers:
        try:
            info = yf.Ticker(t).info or {}
            target = info.get("targetMeanPrice")
            price = info.get("regularMarketPrice")
            n = info.get("numberOfAnalystOpinions") or 0
            if target and price and price > 0 and n >= MIN_ANALYSTS:
                upside = target / price - 1
                out[t] = float(np.clip(upside, -UPSIDE_CLIP, UPSIDE_CLIP))
        except Exception as e:
            logger.debug("smartgrowth upside fetch failed %s: %s", t, e)
    return out


def compute_smartgrowth_basket(
    signals: dict[str, dict[str, float]],
    upside_fetch: Optional[Callable[[list[str]], dict[str, float]]] = None,
) -> dict:
    """The frozen selection rule. ``signals`` maps component name →
    {ticker: raw value} (momentum/revisions/congress/ark). Returns
    {picks: {ticker: weight}, components_live, scores}."""
    upside_fetch = upside_fetch or fetch_analyst_upside

    z: dict[str, dict[str, float]] = {}
    z["momentum"] = _zscores(signals.get("momentum", {}))
    z["revisions"] = _zscores(signals.get("revisions", {}))
    smart_raw: dict[str, float] = {}
    for src in ("congress", "ark"):
        for t, v in signals.get(src, {}).items():
            smart_raw[t] = smart_raw.get(t, 0.0) + v
    z["smart_money"] = _zscores(smart_raw)

    universe = sorted(set().union(*[set(m) for m in z.values()]) if any(z.values()) else set())
    if not universe:
        return {"picks": {}, "components_live": [], "scores": {},
                "status": "no_signals"}

    def _blend(components: dict[str, dict[str, float]]) -> dict[str, float]:
        live = [c for c, m in components.items() if m]
        total_w = sum(WEIGHTS[c] for c in live)
        scores: dict[str, float] = {}
        for t in universe:
            s = 0.0
            for c in live:
                s += WEIGHTS[c] * components[c].get(t, 0.0)  # missing → z=0
            scores[t] = s / total_w if total_w else 0.0
        return scores

    # Preliminary rank (3 components) bounds the yfinance fetch, then the
    # final blend adds clipped analyst upside for the top names only.
    prelim = _blend({k: z[k] for k in ("momentum", "revisions", "smart_money")})
    top_prelim = sorted(prelim, key=prelim.get, reverse=True)[:PREFETCH_TOP_N]
    upside_raw = upside_fetch(top_prelim)
    z["analyst_upside"] = _zscores(upside_raw)

    final_scores = _blend(z)
    # Final ranking restricted to the prefetched set (upside coverage bound)
    ranked = sorted(top_prelim, key=lambda t: final_scores.get(t, 0.0),
                    reverse=True)
    picks = {t: round(1.0 / BASKET_SIZE, 4) for t in ranked[:BASKET_SIZE]}
    return {
        "picks": picks,
        "components_live": [c for c, m in z.items() if m],
        "scores": {t: round(final_scores.get(t, 0.0), 4) for t in ranked},
        "status": "ok",
    }


def collect_smartgrowth_picks(db_path=None, *, upside_fetch=None,
                              as_of=None, throttle_days=6) -> dict:
    """Weekly forward snapshot of the basket into the PIT store."""
    aso = as_of or date.today().isoformat()
    conn = get_connection(db_path)
    try:
        signals = {name: _latest_by_ticker(conn, prefix)
                   for name, prefix in _SIGNAL_PREFIXES.items()}
    finally:
        conn.close()

    basket = compute_smartgrowth_basket(signals, upside_fetch=upside_fetch)
    if basket["status"] != "ok" or not basket["picks"]:
        logger.warning("smartgrowth: no basket this week (%s) — inputs sparse",
                       basket["status"])
        return {"status": basket["status"], "n": 0}

    def _score_for(ticker: str) -> tuple[float, dict]:
        return basket["picks"][ticker], {
            "components_live": basket["components_live"],
            "score": basket["scores"].get(ticker),
            "basket_size": len(basket["picks"]),
        }

    return collect_pit_scores(
        key_prefix=KEY_PREFIX, source="smartgrowth",
        score_for_ticker=_score_for, tickers=sorted(basket["picks"]),
        db_path=db_path, as_of=aso, throttle_days=throttle_days,
    )


def ensure_smartgrowth_trial(db_path=None) -> int:
    """Idempotently pre-register TRIAL-SMARTGROWTH."""
    from backend.services.portfolio_intelligence.trial_registry import (
        ensure_trial_registered,
    )

    notes = {
        "hypothesis": (
            "A weekly top-10 EW basket from the frozen blend (momentum .35, "
            "revisions .25, smart-money .20, clipped analyst upside .20) "
            "beats QQQ forward — Murat's tech/forecast/real-investor thesis "
            "made falsifiable; honest prior mixed-to-weak"
        ),
        "purpose": "experimental",
        "canonical_doc": "docs/TRIALS/TRIAL-SMARTGROWTH.md",
        "pre_registered": "2026-07-12",
        "decision_rule": {
            "trial": "TRIAL-SMARTGROWTH",
            "primary_metric": "forward EW basket return (10bps/side costs) "
                              "vs QQQ; co-primary maxDD <= 1.5x QQQ",
            "adopt_threshold": "beats QQQ total return over >=6mo AND Sharpe "
                               ">= QQQ - 0.15 -> attended NAV lane seed",
            "reject_threshold": "trails QQQ by >=5pts at 12mo OR DD condition",
            "earliest_decision": "2027-01-12",
            "params_frozen": "weights/clip/floor/basket 10/weekly/benchmark "
                             "QQQ/prefetch top-30",
            "crash_event_override": "SPY drawdown >=20% defers decisions "
                                    ">=6mo past trough",
            "hard_constraint": "descriptive-only; NEVER arms a lane; no "
                               "buy-sell framing; personal returns are not "
                               "evidence",
        },
    }
    return ensure_trial_registered(TRIAL_PARAM, notes, db_path=db_path)
