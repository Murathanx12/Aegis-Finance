"""Optimus Portfolio Manager — sizing, the wealth question, and the daily brief.

`pm_engine` turns a ticker into decision-relevant state and a score. This turns
a book of those into instructions with dollar amounts, and answers the only
question the account owner actually has:

    "Given what I hold and what I am trying to reach, what do I do today, and
     what is the chance this ends badly?"

The second half of that sentence is not optional. `simulate_wealth` refuses to
report the probability of hitting a stretch target without the floor and ruin
probabilities and the expected drawdown beside it, because a target quoted
alone reads as a forecast, and it is not one.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime

import numpy as np

from backend.services.pm_engine import (BINARY_EXTRA_HAIRCUT,
                                        DEFAULT_CORRELATION, MIN_TICKET,
                                        REBALANCE_BAND, TARGET_HAIRCUT, Book,
                                        analyst_alpha, distribution, enrich,
                                        load_book)

logger = logging.getLogger(__name__)


# ──────────────────────────── sizing and actions ───────────────────────────

def target_weight(dist: dict, alpha: dict, mode: dict) -> float:
    """Fractional Kelly on the three-point distribution, hard-capped by mode.

    Kelly on a three-outcome sketch is not a precise object, so it is
    deliberately fractional and then capped. The cap is what actually controls
    the book; the arithmetic only decides the ordering within it.
    """
    if not dist.get("available") or alpha.get("score") is None:
        return 0.0
    mu = dist.get("expected_return")
    sd = dist.get("annual_vol")
    if mu is None or not sd or mu <= 0:
        return 0.0
    # UNCAPPED here on purpose. Capping each name before normalising made every
    # name in a high-conviction book hit the same ceiling and come out equal
    # weight, which threw away the ordering the score had just computed. The cap
    # is applied in `allocate`, after the raw weights have been scaled.
    return float(max(0.0, mode["kelly"] * mu / (sd ** 2)))


def allocate(raw: dict[str, float], mode: dict) -> dict[str, float]:
    """Scale raw Kelly weights into the budget, then cap, then redistribute.

    Capping first and scaling second destroys the ordering; scaling first and
    capping second leaves cash on the table. So: scale, cap, and hand the
    overflow back to the names still under the ceiling, twice.
    """
    budget = 1.0 - mode["min_cash"]
    cap = mode["max_weight"]
    w = dict(raw)
    total = sum(w.values())
    if total <= 0:
        return {k: 0.0 for k in w}
    w = {k: v * budget / total for k, v in w.items()}
    for _ in range(3):
        over = {k: v - cap for k, v in w.items() if v > cap}
        if not over:
            break
        spill = sum(over.values())
        for k in over:
            w[k] = cap
        room = {k: cap - v for k, v in w.items() if v < cap}
        pool = sum(room.values())
        if pool <= 0:
            break
        for k, r in room.items():
            w[k] += spill * (r / pool)
    return {k: round(min(cap, v), 4) for k, v in w.items()}


def action_for(current_w: float, target_w: float, nav: float, *,
               no_data: bool = False) -> dict:
    """Weights become instructions only outside the band and above a ticket."""
    d = target_w - current_w
    dollars = d * nav
    if no_data and current_w > 0:
        # never issue a ticket on a name the engine cannot see. "No data" is a
        # reason to look, not a reason to sell.
        return {"action": "REVIEW", "dollars": 0.0,
                "current_weight": round(current_w, 4),
                "target_weight": round(target_w, 4),
                "why": "no usable market or analyst data — decide by hand"}
    if target_w <= 0.001 and current_w > 0:
        verb = "SELL"
        dollars = -current_w * nav
    elif abs(d) < REBALANCE_BAND or abs(dollars) < MIN_TICKET:
        verb, dollars = "HOLD", 0.0
    elif d > 0:
        verb = "ADD" if current_w > 0 else "BUY"
    else:
        verb = "TRIM"
    return {"action": verb, "dollars": round(float(dollars), 0),
            "current_weight": round(current_w, 4),
            "target_weight": round(target_w, 4)}


def replacement_edge(candidate: dict, holding: dict,
                     round_trip_cost: float = 0.004) -> dict:
    """Is this candidate a better use of the dollar than that holding?

    The question that separates a portfolio manager from a stock picker: never
    "is X good", always "is X better than what it would have to replace, after
    the cost of switching".
    """
    a = (holding.get("alpha") or {}).get("score")
    b = (candidate.get("alpha") or {}).get("score")
    if a is None or b is None:
        return {"available": False}
    edge = b - a - round_trip_cost
    return {"available": True, "candidate": candidate["ticker"],
            "funded_by": holding["ticker"], "edge": round(edge, 4),
            "verdict": "SWITCH" if edge > 0.05 else "STAY",
            "unit": "analyst-alpha units net of a 40bp round trip, NOT "
                    "expected return"}


# ─────────────────────────── the wealth question ───────────────────────────

def simulate_wealth(rows: list[dict], nav: float, cash: float, targets: dict,
                    *, n: int = 20_000, seed: int = 20260810,
                    correlation: float = DEFAULT_CORRELATION) -> dict:
    live = [r for r in rows
            if r.get("distribution", {}).get("available")
            and r.get("proposed", {}).get("target_weight", 0) > 0]
    start = nav + cash
    if not live or start <= 0:
        return {"available": False, "reason": "no sized positions"}

    rng = np.random.default_rng(seed)
    w = np.array([r["proposed"]["target_weight"] for r in live])
    cash_w = max(0.0, 1.0 - float(w.sum()))
    mu = np.array([_mu(r["distribution"]) for r in live])
    sd = np.array([max(0.10, r["distribution"]["annual_vol"]) for r in live])

    rho = max(0.0, min(0.95, correlation))
    k, steps = len(live), int(targets.get("horizon_months", 12))
    sigma = np.sqrt(np.log1p(sd ** 2))
    drift = (np.log1p(np.maximum(mu, -0.95)) - 0.5 * sigma ** 2) / steps
    step_sd = sigma / math.sqrt(steps)

    # A MONTHLY PATH, not a terminal shock scaled by a fudge factor. The first
    # version used a 1.35x Brownian-bridge proxy and reported an expected max
    # drawdown of -7.8% for a book of 60%-vol small caps, which is not a
    # believable number. Buy-and-hold weights drift with the paths; that is what
    # actually happens between annual reviews.
    nav_path = np.full(n, 1.0)
    peak = np.full(n, 1.0)
    maxdd = np.zeros(n)
    hold = np.tile(w, (n, 1))
    cash_leg = np.full(n, cash_w)
    for _ in range(steps):
        common = rng.standard_normal((n, 1))
        idio = rng.standard_normal((n, k))
        z = math.sqrt(rho) * common + math.sqrt(1 - rho) * idio
        hold = hold * np.exp(drift + step_sd * z)
        nav_path = hold.sum(axis=1) + cash_leg
        peak = np.maximum(peak, nav_path)
        maxdd = np.minimum(maxdd, nav_path / peak - 1.0)
    port = nav_path
    end = start * port
    dd = maxdd
    tgt = float(targets.get("target_value") or 0)
    flr = float(targets.get("floor_value") or 0)
    ruin = float(targets.get("ruin_value") or 0)
    q = np.percentile(end, [5, 25, 50, 75, 95])
    return {
        "available": True,
        "start_value": round(start, 0),
        "horizon_months": int(targets.get("horizon_months", 12)),
        "p5": round(float(q[0]), 0), "p25": round(float(q[1]), 0),
        "median": round(float(q[2]), 0),
        "p75": round(float(q[3]), 0), "p95": round(float(q[4]), 0),
        "p_reach_target": round(float((end >= tgt).mean()), 4) if tgt else None,
        "p_below_floor": round(float((end < flr).mean()), 4) if flr else None,
        "p_below_ruin": round(float((end < ruin).mean()), 4) if ruin else None,
        "expected_max_drawdown": round(float(dd.mean()), 4),
        "p_drawdown_worse_than_50pct": round(float((dd < -0.5).mean()), 4),
        "median_max_drawdown": round(float(np.median(dd)), 4),
        "worst_5pct_max_drawdown": round(float(np.percentile(dd, 5)), 4),
        "required_return_for_target": (round(tgt / start - 1.0, 4)
                                       if tgt else None),
        "assumptions": {
            "average_pairwise_correlation": rho,
            "target_haircut": TARGET_HAIRCUT,
            "binary_extra_haircut": BINARY_EXTRA_HAIRCUT,
                "return_model": "lognormal; median = haircut x analyst upside",
            "drawdown": "worst peak-to-trough of a 12-step MONTHLY path, "
                        "buy-and-hold between reviews",
            "draws": n,
        },
        "health_warning": (
            "probabilities under the assumptions above, not forecasts. The "
            "target is a stretch goal, and the floor and ruin probabilities "
            "are printed beside it so it is never read as an expectation."),
    }


def _mu(d: dict) -> float:
    """The lognormal's own mean. One distribution, read one way."""
    return float(d.get("expected_return", d.get("base", 0.0)))


# ────────────────────────────── the daily brief ────────────────────────────

def daily_brief(book: Book | None = None, *, include_watchlist: bool = True,
                max_candidates: int = 10) -> dict:
    book = book or load_book()
    mode = book.mode
    held = {p.ticker: p for p in book.positions}

    rows: list[dict] = []
    for p in book.positions:
        e = enrich(p.ticker, p)
        rows.append({"ticker": p.ticker, "state": e, "alpha": analyst_alpha(e),
                     "distribution": distribution(e),
                     "thesis": p.thesis, "kill_condition": p.kill_condition,
                     "cost_basis": p.cost_basis, "dollars": p.dollars})

    invested = sum(float(p.dollars or 0) for p in book.positions)
    total = invested + book.cash
    for r in rows:
        r["current_weight"] = (float(r["dollars"] or 0) / total) if total else 0
        r["proposed"] = {"target_weight": target_weight(r["distribution"],
                                                        r["alpha"], mode)}
        px = (r["state"] or {}).get("price")
        cb = r["cost_basis"]
        r["pnl_pct"] = round(px / cb - 1.0, 4) if (px and cb) else None

    sized = allocate({r["ticker"]: r["proposed"]["target_weight"]
                      for r in rows}, mode)
    for r in rows:
        r["proposed"]["target_weight"] = sized[r["ticker"]]
    for r in rows:
        r["recommendation"] = action_for(
            r["current_weight"], r["proposed"]["target_weight"], total,
            no_data=not (r.get("state") or {}).get("available"))

    candidates: list[dict] = []
    if include_watchlist:
        for t in book.watchlist:
            if t in held:
                continue
            e = enrich(t)
            a = analyst_alpha(e)
            if a.get("score") is None:
                continue
            candidates.append({"ticker": t, "state": e, "alpha": a,
                               "distribution": distribution(e)})
        candidates.sort(key=lambda c: c["alpha"]["score"], reverse=True)
        candidates = candidates[:max_candidates]

    scored = [r for r in rows if r["alpha"].get("score") is not None]
    weakest = sorted(scored, key=lambda r: r["alpha"]["score"])
    switches, used = [], set()
    for c in candidates[:5]:
        for h in weakest:
            if h["ticker"] in used:
                continue
            se = replacement_edge(c, h)
            if se.get("verdict") == "SWITCH":
                switches.append(se)
                used.add(h["ticker"])
                break

    wealth = simulate_wealth(rows, invested, book.cash, book.wealth_targets)
    threats = [{"ticker": r["ticker"], "why": w} for r in rows
               for w in threats_for(r)]

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "account": book.account,
        "positions_confirmed": book.confirmed,
        "banner": (None if book.confirmed else
                   "POSITIONS ARE UNCONFIRMED — every dollar figure below is a "
                   "reconstructed placeholder. Edit backend/data/"
                   "murat_book.yaml, set confirmed: true, and only then treat "
                   "a ticket size as real."),
        "sizing_mode": book.sizing_mode,
        "mode_limits": mode,
        "portfolio_value": round(total, 2),
        "cash": round(book.cash, 2),
        "holdings": rows,
        "actions": [dict(ticker=r["ticker"], thesis=r["thesis"],
                         kill_condition=r["kill_condition"],
                         **r["recommendation"])
                    for r in rows if r["recommendation"]["action"] != "HOLD"],
        "opportunities": [{"ticker": c["ticker"], "score": c["alpha"]["score"],
                           "implied_upside": c["alpha"].get("implied_upside"),
                           "distribution": c["distribution"],
                           "state": {k: c["state"].get(k) for k in
                                     ("price", "target_median", "n_analysts",
                                      "rating_drift_3m", "net_90d",
                                      "binary_event_risk")}}
                          for c in candidates],
        "replacements": switches,
        "threats": threats,
        "wealth": wealth,
        "evidence_note": (
            "Everything analyst-derived here is OBSERVATIONAL and has not been "
            "validated by the Aegis research lab. That label is deliberate: "
            "the lab's job is to say how much to trust it, and until it has, "
            "this is a disciplined version of a process that has been run by "
            "hand — not a demonstrated edge."),
    }


def threats_for(r: dict) -> list[str]:
    e, out = r.get("state") or {}, []
    if not e.get("available"):
        return ["no data available for this name"]
    if (e.get("rating_drift_3m") or 0) < -0.05:
        out.append(f"street getting LESS positive (3m rating drift "
                   f"{e['rating_drift_3m']})")
    if (e.get("net_90d") or 0) < 0:
        out.append(f"net downgrades in 90d: {e['net_90d']}")
    if e.get("binary_event_risk"):
        out.append("single-event risk: pre-revenue clinical/regulatory name")
    if (e.get("implied_upside") or 0) < 0:
        out.append("trading ABOVE the consensus target")
    liq = e.get("liquidity") or {}
    if liq.get("available") and not liq.get("tradeable_at_retail_size"):
        out.append(f"thin: median ADV ${liq.get('adv_dollar', 0):,.0f}")
    ds = e.get("days_since_last_action")
    if ds is not None and ds > 180:
        out.append(f"stale coverage: {ds} days since the last rating action")
    if r.get("pnl_pct") is not None and r["pnl_pct"] < -0.5:
        out.append(f"down {r['pnl_pct']:.0%} against cost — is the thesis or "
                   f"the kill condition the thing that changed?")
    return out
