"""Optimus Portfolio Manager — sizing, the wealth question, and the daily brief.

`pm_engine` turns a ticker into decision-relevant state and a return
distribution. This turns a book of those into ONE proposed portfolio, decomposes
the difference into instructions with dollar amounts, and answers the only
question the account owner actually has:

    "Given what I hold and what I am trying to reach, what do I do today, and
     what is the chance this ends badly?"

The second half of that sentence is not optional, and BUILD-1.1 added a third
half: *how much of this is model*. `wealth_scenarios` runs the same book under
a conservative, a base and an optimistic set of assumptions, because a single
"P(reach $100k) = 19.8%" printed off an unvalidated haircut is a statement about
`TARGET_HAIRCUT`, not about the account.

Three structural changes from v1:

* **One portfolio, not two lists.** v1 sized the holdings, ranked the watchlist
  separately, and then labelled a few pairs as switches after the fact. So "BUY
  KYTX funded by AARD" did not mean the engine had re-solved the book without
  AARD — the wealth simulation never saw KYTX at all. Now the eligible set is
  holdings ∪ candidates, it is solved once, and the replacement table is a
  *decomposition* of that single solution.
* **`max_names` is a constraint, not a comment.** It was defined in `MODES` and
  never read.
* **The instructions cannot overdraw the account.** Band and minimum-ticket
  suppression could kill a funding TRIM while leaving the BUY it paid for.
"""
from __future__ import annotations

import logging
import math
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import numpy as np

from backend.services.pm_engine import (BINARY_EXTRA_HAIRCUT,
                                        DEFAULT_CORRELATION, MIN_TICKET,
                                        REBALANCE_BAND, RETAIL_ROUND_TRIP,
                                        RISK_AVERSION, TARGET_HAIRCUT, Book,
                                        analyst_alpha, certainty_equivalent,
                                        distribution, enrich, load_book,
                                        mark_book, validate_book)

logger = logging.getLogger(__name__)

#: A switch must clear this much in EXPECTED-RETURN units, net of the cost of
#: switching, before it is worth doing. Three points of certainty-equivalent a
#: year is a real difference; one point is noise in a number built on an
#: unvalidated haircut.
SWITCH_THRESHOLD = 0.03

#: How much of NAV may sit in positions the engine could not price before the
#: book stops being actionable. Every ticket is sized off NAV, so an unpriced
#: position is uncertainty in every dollar figure — but one permanently-halted
#: microcap must not freeze an otherwise-live book forever.
UNPRICED_NAV_TOLERANCE = 0.10

#: The model-uncertainty envelope. These are NOT tuned to make the goal look
#: reachable — the conservative arm is deliberately the one that matters, and
#: the optimistic arm is capped at a haircut (0.50) that is still below taking
#: the street at half its word.
SCENARIOS: dict[str, dict] = {
    "conservative": {"target_haircut": 0.20, "correlation": 0.55,
                     "vol_mult": 1.15},
    "base":         {"target_haircut": TARGET_HAIRCUT,
                     "correlation": DEFAULT_CORRELATION, "vol_mult": 1.00},
    "optimistic":   {"target_haircut": 0.50, "correlation": 0.25,
                     "vol_mult": 1.00},
}


# ──────────────────────────── sizing and actions ───────────────────────────

def target_weight(dist: dict, alpha: dict, mode: dict) -> float:
    """Fractional Kelly on the return distribution, uncapped here on purpose.

    Kelly on a sketch of a distribution is not a precise object, so it is
    deliberately fractional and then capped in `allocate`. Capping each name
    before normalising made every name in a high-conviction book hit the same
    ceiling and come out equal weight, throwing away the ordering.

    `alpha` is accepted for signature compatibility and is NOT read: the
    analyst evidence reaches this number through `distribution()`, where
    breadth, freshness, dispersion and staleness discount the expected return
    itself. Sizing off a display score and sizing off the distribution are two
    different claims and only one of them can be right.
    """
    if not dist.get("available"):
        return 0.0
    mu = dist.get("expected_return")
    sd = dist.get("annual_vol")
    if mu is None or not sd or mu <= 0:
        return 0.0
    return float(max(0.0, mode["kelly"] * mu / (sd ** 2)))


def allocate(raw: dict[str, float], mode: dict,
             budget: Optional[float] = None) -> dict[str, float]:
    """Scale raw Kelly weights into the budget, then cap, then redistribute."""
    if budget is None:
        budget = 1.0 - mode["min_cash"]
    budget = max(0.0, float(budget))
    cap = mode["max_weight"]
    w = dict(raw)
    total = sum(w.values())
    if total <= 0 or budget <= 0:
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


def build_target_portfolio(rows: list[dict], mode: dict) -> dict:
    """One target portfolio over holdings ∪ candidates. The whole decision.

    Three classes of name, and the distinction is the point:

    * **frozen** — held, but the engine cannot currently see it. It keeps its
      current weight. It is NOT sized to zero, because sizing it to zero would
      be a sale caused by a feed outage.
    * **eligible** — decisionable. Competes for the `max_names` slots on its
      Kelly weight, and the winners are scaled into whatever budget the frozen
      names left.
    * **excluded** — a candidate we cannot see. Never bought, never mentioned
      as an instruction.
    """
    frozen: dict[str, float] = {}
    sizable: dict[str, float] = {}
    zeroed: list[dict] = []
    for r in rows:
        t = r["ticker"]
        if r.get("held") and not r.get("decisionable"):
            frozen[t] = max(0.0, float(r.get("current_weight") or 0.0))
            continue
        if not r.get("decisionable"):
            continue
        w = target_weight(r.get("distribution") or {}, r.get("alpha") or {}, mode)
        if w > 0:
            sizable[t] = w
        elif r.get("held"):
            zeroed.append({"ticker": t,
                           "why": "expected return is not positive after the "
                                  "haircut — a view, not a data gap"})

    frozen_total = sum(frozen.values())
    slots = max(0, int(mode["max_names"]) - len(frozen))
    budget = max(0.0, 1.0 - float(mode["min_cash"]) - frozen_total)

    ranked = sorted(sizable.items(), key=lambda kv: -kv[1])
    kept = dict(ranked[:slots])
    cut = [{"ticker": t, "raw_weight": round(w, 4),
            "why": f"lost the competition for {mode['max_names']} slots"}
           for t, w in ranked[slots:]]

    sized = allocate(kept, mode, budget=budget)
    target = {**frozen, **sized}
    for r in rows:
        target.setdefault(r["ticker"], 0.0)

    return {
        "target_weights": target,
        "frozen": frozen,
        "frozen_weight": round(frozen_total, 4),
        "budget": round(budget, 4),
        "slots": slots,
        "names_at_work": len([w for w in target.values() if w > 0]),
        "max_names": int(mode["max_names"]),
        "min_cash": float(mode["min_cash"]),
        "cash_weight": round(max(0.0, 1.0 - sum(target.values())), 4),
        "dropped_for_max_names": cut,
        "zeroed_by_view": zeroed,
        "constraints_binding": [
            k for k, v in (("max_names", len(ranked) > slots),
                           ("max_weight", any(abs(v - mode["max_weight"]) < 1e-9
                                              for v in sized.values())),
                           ("min_cash", mode["min_cash"] > 0)) if v],
    }


def action_for(current_w: float, target_w: float, nav: float, *,
               no_data: bool = False, decisionable: Optional[bool] = None,
               held: bool = True, reasons: Optional[list] = None,
               round_trip_cost: float = RETAIL_ROUND_TRIP) -> dict:
    """Weights become instructions only outside the band and above a ticket.

    The gate that matters is `decisionable`. A held name the engine cannot
    price, or cannot build a distribution for, produces REVIEW and a zero
    ticket — never SELL, TRIM, ADD or BUY. A SELL requires a real negative
    view: the expected return did not survive the haircut, or the name lost its
    slot to something better. Both of those are decisions. A missing feed is
    not.
    """
    if decisionable is None:
        decisionable = not no_data
    d = target_w - current_w
    dollars = d * nav
    base = {"current_weight": round(float(current_w), 4),
            "target_weight": round(float(target_w), 4)}
    if not decisionable:
        if held and current_w > 0:
            return {**base, "action": "REVIEW", "dollars": 0.0,
                    "why": "no usable market or analyst data — decide by hand. "
                           "The engine does not sell what it cannot see.",
                    "missing": list(reasons or [])}
        return {**base, "action": "SKIP", "dollars": 0.0, "target_weight": 0.0,
                "why": "not decisionable and not held — no instruction",
                "missing": list(reasons or [])}
    if target_w <= 0.001 and current_w > 0:
        return {**base, "action": "SELL", "dollars": round(-current_w * nav, 0),
                "why": "sized to zero on the evidence, not on its absence"}
    # The target portfolio is solved without trading costs, so on its own it
    # will happily churn a name that costs 3% to round-trip for a 2-point
    # improvement. Widen the no-trade band in proportion to what the name
    # actually costs to move: a position five times more expensive to trade
    # has to drift five times further before it is worth touching.
    cost_ratio = (max(RETAIL_ROUND_TRIP, float(round_trip_cost))
                  / RETAIL_ROUND_TRIP)
    band = REBALANCE_BAND * cost_ratio
    if abs(d) < band or abs(dollars) < MIN_TICKET:
        return {**base, "action": "HOLD", "dollars": 0.0,
                "band": round(band, 4), "round_trip_cost": round_trip_cost,
                "why": f"inside the cost-aware {band:.1%} band "
                       f"(round trip {float(round_trip_cost):.2%}) / "
                       f"${MIN_TICKET:,.0f} minimum ticket"}
    verb = ("ADD" if current_w > 0 else "BUY") if d > 0 else "TRIM"
    return {**base, "action": verb, "dollars": round(float(dollars), 0),
            "band": round(band, 4), "round_trip_cost": round_trip_cost}


def enforce_cash_constraint(actions: list[dict], cash: float,
                            nav: float) -> dict:
    """Buys may not exceed the cash the sells actually raise.

    The band and the minimum ticket suppress small instructions. They suppress
    a $200 funding TRIM exactly as happily as a $200 top-up, so a plan could
    come out of the sizer with $4,000 of buys funded by $3,800 of sells and
    $0 of cash. Scale the buys down to what is really available, and say so.
    """
    raised = sum(-a["dollars"] for a in actions
                 if a["action"] in ("SELL", "TRIM"))
    wanted = sum(a["dollars"] for a in actions if a["action"] in ("BUY", "ADD"))
    available = float(cash) + raised
    out = {"cash_before": round(float(cash), 2), "raised_by_sales": round(raised, 2),
           "buys_requested": round(wanted, 2), "scaled": False,
           "scale_factor": 1.0}
    if wanted > available + 1.0 and wanted > 0:
        f = max(0.0, available / wanted)
        out.update(scaled=True, scale_factor=round(f, 4),
                   note=("buys scaled to the cash the sales actually raise — "
                         "suppressed sub-band trims cannot fund a purchase"))
        for a in actions:
            if a["action"] in ("BUY", "ADD"):
                a["dollars"] = round(a["dollars"] * f, 0)
                a["scaled_for_cash"] = True
                if abs(a["dollars"]) < MIN_TICKET:
                    a["action"] = "HOLD"
                    a["dollars"] = 0.0
                    a["why"] = "no cash left to fund a ticket of usable size"
    spent = sum(a["dollars"] for a in actions if a["action"] in ("BUY", "ADD"))
    out["buys_final"] = round(spent, 2)
    out["cash_after"] = round(available - spent, 2)
    out["reconciles"] = out["cash_after"] >= -1.0
    return out


def funding_plan(actions: list[dict], cash: float) -> list[dict]:
    """Which sale pays for which purchase — a decomposition, not a heuristic.

    v1 generated switch pairs by scanning the watchlist against the weakest
    holdings with a separate rule, so the pairing and the portfolio could
    disagree. These pairs come out of the single solved target: the dollars on
    both sides are the dollars in the instructions.
    """
    sources = [[a["ticker"], -a["dollars"]] for a in actions
               if a["action"] in ("SELL", "TRIM") and a["dollars"] < 0]
    if cash > 0:
        sources.append(["CASH", float(cash)])
    dests = [[a["ticker"], a["dollars"], a["action"]] for a in actions
             if a["action"] in ("BUY", "ADD") and a["dollars"] > 0]
    sources.sort(key=lambda s: -s[1])
    dests.sort(key=lambda d: -d[1])
    out, i = [], 0
    for d in dests:
        need = d[1]
        while need > 1 and i < len(sources):
            take = min(need, sources[i][1])
            if take > 1:
                out.append({"buy": d[0], "action": d[2],
                            "funded_by": sources[i][0],
                            "dollars": round(take, 0)})
            sources[i][1] -= take
            need -= take
            if sources[i][1] <= 1:
                i += 1
        if need > 1:
            out.append({"buy": d[0], "action": d[2], "funded_by": "UNFUNDED",
                        "dollars": round(need, 0),
                        "warning": "no source of cash for this ticket"})
    return out


def replacement_edge(candidate: dict, holding: dict, *,
                     switch_cost: Optional[float] = None,
                     risk_aversion: float = RISK_AVERSION) -> dict:
    """Is this candidate a better use of the dollar than that holding?

    Everything below is in EXPECTED-RETURN units over the same 12-month
    horizon, including the cost, which is the whole point of the rewrite. v1
    computed `score(B) - score(A) - 0.004`, subtracting a 40 basis-point
    trading cost from a difference of two arbitrary analyst-alpha scores, and
    then labelled the result "net of a 40bp round trip". Those are not the same
    units; rescaling the score would have silently rescaled the cost away.

        replacement_edge = CE(candidate) - CE(holding) - switching cost
        CE = mu - λσ²/2

    `alpha_score_delta` is still reported, because it is a useful diagnostic —
    but it is reported as itself, gross, and never described as net of cost.
    """
    dc = candidate.get("distribution") or {}
    dh = holding.get("distribution") or {}
    if not dc.get("available") or not dh.get("available"):
        return {"available": False,
                "reason": "both names need a usable return distribution"}
    mu_c, mu_h = float(dc["expected_return"]), float(dh["expected_return"])
    v_c, v_h = float(dc["annual_vol"]), float(dh["annual_vol"])
    ce_c = certainty_equivalent(mu_c, v_c, risk_aversion)
    ce_h = certainty_equivalent(mu_h, v_h, risk_aversion)

    if switch_cost is None:
        # sell one, buy the other: half a round trip each side
        def half(row: dict) -> float:
            liq = ((row.get("state") or {}).get("liquidity") or {})
            return float(liq.get("assumed_round_trip_cost", RETAIL_ROUND_TRIP)) / 2.0
        switch_cost = half(holding) + half(candidate)
    switch_cost = float(switch_cost)

    gross = ce_c - ce_h
    net = gross - switch_cost
    a = (holding.get("alpha") or {}).get("score")
    b = (candidate.get("alpha") or {}).get("score")
    return {
        "available": True,
        "candidate": candidate["ticker"], "funded_by": holding["ticker"],
        "replacement_edge": round(net, 4),
        "gross_edge": round(gross, 4),
        "switch_cost": round(switch_cost, 5),
        "expected_return_delta": round(mu_c - mu_h, 4),
        "risk_delta": round(v_c - v_h, 4),
        "certainty_equivalent": {"candidate": round(ce_c, 4),
                                 "holding": round(ce_h, 4)},
        "alpha_score_delta": (round(b - a, 4)
                              if (a is not None and b is not None) else None),
        "correlation_delta": None,
        "correlation_note": ("the book assumes one average pairwise "
                             "correlation, so there is no per-pair estimate to "
                             "difference. MISSING, not zero."),
        "verdict": "SWITCH" if net > SWITCH_THRESHOLD else "STAY",
        "threshold": SWITCH_THRESHOLD,
        "unit": ("annual expected-return units (certainty equivalent, "
                 f"λ={risk_aversion}); the cost is in the same units"),
        "risk_aversion": risk_aversion,
    }


# ─────────────────────────── the wealth question ───────────────────────────

#: The numeric outputs of `simulate_wealth` that become {"low","high"} RANGES
#: when the cash balance is unknown and the sweep endpoints are simulated.
_SWEEP_RANGE_KEYS = ("start_value", "p5", "p25", "median", "p75", "p95",
                     "p_reach_target", "p_below_floor", "p_below_ruin",
                     "expected_max_drawdown", "p_drawdown_worse_than_50pct",
                     "median_max_drawdown", "worst_5pct_max_drawdown",
                     "required_return_for_target")


def simulate_wealth(rows: list[dict], nav: float, cash: Optional[float],
                    targets: dict,
                    *, n: int = 20_000, seed: int = 20260810,
                    correlation: float = DEFAULT_CORRELATION,
                    haircut: float = TARGET_HAIRCUT,
                    vol_mult: float = 1.0,
                    label: str = "base") -> dict:
    """Where does this book land, and how often does it end badly?

    `rows` are the PROPOSED portfolio — holdings and any candidate the target
    portfolio actually bought. v1 simulated only the existing holdings, so a
    brief that recommended buying KYTX still reported the odds of the book
    without it.

    `haircut` and `vol_mult` exist so the same book can be re-run under
    different assumptions without re-fetching anything: mu is linear in the
    haircut, so scaling it is exact.

    `cash=None` means the cash balance is UNRECOVERABLE (NIGHT-13 §0). The
    simulation then runs at BOTH endpoints of `config.CASH_SENSITIVITY_GRID`
    (as fractions of `nav`) and reports every probability and quantile as a
    {"low","high"} RANGE — never a point estimate that silently assumed zero,
    and never a preferred point in the sweep.
    """
    if cash is None:
        from backend.config import CASH_SENSITIVITY_GRID
        grid = tuple(sorted(CASH_SENSITIVITY_GRID))
        f_lo, f_hi = grid[0], grid[-1]
        ends = {
            f: simulate_wealth(rows, nav, f * float(nav or 0.0), targets,
                               n=n, seed=seed, correlation=correlation,
                               haircut=haircut, vol_mult=vol_mult, label=label)
            for f in (f_lo, f_hi)}
        lo, hi = ends[f_lo], ends[f_hi]
        if not (lo.get("available") and hi.get("available")):
            return lo if not lo.get("available") else hi
        out: dict[str, Any] = {
            "available": True, "scenario": label,
            "cash_basis": ("UNKNOWN — swept over the endpoints of "
                           "CASH_SENSITIVITY_GRID; every figure below is a "
                           "RANGE across the sweep, not a point estimate"),
            "cash_fraction_endpoints": [f_lo, f_hi],
            "horizon_months": lo["horizon_months"],
            "names_simulated": lo["names_simulated"],
            "assumptions": lo["assumptions"],
            "endpoints": {"low_cash": lo, "high_cash": hi},
            "sweep_note": ("reported, never picked — no cash fraction in the "
                           "sweep is chosen, and nothing downstream may rank "
                           "the endpoints (grid-report-never-pick)"),
            "health_warning": lo["health_warning"],
        }
        for k in _SWEEP_RANGE_KEYS:
            a, b = lo.get(k), hi.get(k)
            out[k] = (None if a is None or b is None
                      else {"low": min(a, b), "high": max(a, b)})
        return out

    live = [r for r in rows
            if (r.get("distribution") or {}).get("available")
            and (r.get("proposed") or {}).get("target_weight", 0) > 0]
    # `nav` here is the INVESTED value; total wealth is that plus the cash leg.
    start = float(nav or 0.0) + float(cash or 0.0)
    if not live or start <= 0:
        return {"available": False, "reason": "no sized positions"}

    rng = np.random.default_rng(seed)
    w = np.array([r["proposed"]["target_weight"] for r in live], dtype=float)
    cash_w = max(0.0, 1.0 - float(w.sum()))
    hair_scale = float(haircut) / TARGET_HAIRCUT if TARGET_HAIRCUT else 1.0
    mu = np.array([float(r["distribution"]["expected_return"]) for r in live]) * hair_scale
    sd = np.array([max(0.10, float(r["distribution"]["annual_vol"]))
                   for r in live]) * float(vol_mult)

    rho = max(0.0, min(0.95, float(correlation)))
    k, steps = len(live), int(targets.get("horizon_months", 12) or 12)
    steps = max(1, steps)
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
    end = start * nav_path
    dd = maxdd
    tgt = float(targets.get("target_value") or 0)
    flr = float(targets.get("floor_value") or 0)
    ruin = float(targets.get("ruin_value") or 0)
    q = np.percentile(end, [5, 25, 50, 75, 95])
    return {
        "available": True,
        "scenario": label,
        "start_value": round(start, 0),
        "horizon_months": steps,
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
        "names_simulated": k,
        "assumptions": {
            "average_pairwise_correlation": rho,
            "target_haircut": round(float(haircut), 4),
            "volatility_multiplier": float(vol_mult),
            "binary_extra_haircut": BINARY_EXTRA_HAIRCUT,
            "return_model": ("lognormal with the MEAN pinned to haircut x "
                             "upside x reliability; volatility widens the "
                             "distribution and cannot raise the mean"),
            "drawdown": "worst peak-to-trough of a monthly path, "
                        "buy-and-hold between reviews",
            "draws": n,
        },
        "health_warning": (
            "probabilities under the assumptions above, not forecasts. The "
            "target is a stretch goal, and the floor and ruin probabilities "
            "are printed beside it so it is never read as an expectation."),
    }


def wealth_scenarios(rows: list[dict], nav: float, cash: Optional[float],
                     targets: dict, **kw) -> dict:
    """The same book under three sets of assumptions, reported together.

    "P(reach $100k) = 19.8%" is three significant figures resting on
    `TARGET_HAIRCUT = 0.35`, a number fitted to nothing. The reader is entitled
    to know that the answer moves with the assumption and by how much — that is
    model uncertainty, and it is much larger here than the Monte Carlo error
    the ±0.1% precision implies.
    """
    out: dict[str, Any] = {"scenarios": {}, "definitions": SCENARIOS}
    for name, cfg in SCENARIOS.items():
        out["scenarios"][name] = simulate_wealth(
            rows, nav, cash, targets, label=name,
            correlation=cfg["correlation"], haircut=cfg["target_haircut"],
            vol_mult=cfg["vol_mult"], **kw)
    base = out["scenarios"].get("base", {})
    out["available"] = bool(base.get("available"))
    if not out["available"]:
        out["reason"] = base.get("reason")
        return out
    # A value may itself be a {"low","high"} RANGE when the cash balance is
    # unknown and simulate_wealth swept it — the scenario range then spans the
    # sweep as well as the model assumptions.
    def _lo(v: Any) -> float:
        return v["low"] if isinstance(v, dict) else v

    def _hi(v: Any) -> float:
        return v["high"] if isinstance(v, dict) else v

    for key in ("p_reach_target", "p_below_floor", "p_below_ruin", "median",
                "expected_max_drawdown", "p_drawdown_worse_than_50pct"):
        vals = [s.get(key) for s in out["scenarios"].values()
                if s.get("available") and s.get(key) is not None]
        if vals:
            out.setdefault("range", {})[key] = {
                "low": min(_lo(v) for v in vals),
                "high": max(_hi(v) for v in vals),
                "base": base.get(key)}
    out["base"] = base
    # A stretch target sitting far out in the right tail is reached by
    # VOLATILITY, not by drift. The conservative arm cuts the expected return
    # but raises correlation and vol — and when the target needs +120%, the
    # second effect can dominate the first, so the pessimistic arm prints a
    # HIGHER P(reach). That is not a bug in the scenario and it is not good
    # news: the same arm is simultaneously worse on the median and worse on
    # ruin. Say so, rather than letting a reader take the number as comfort.
    con, opt = out["scenarios"].get("conservative", {}), out["scenarios"].get("optimistic", {})
    if (con.get("available") and base.get("available")
            and con.get("p_reach_target") is not None
            and base.get("p_reach_target") is not None):
        cp, bp = con["p_reach_target"], base["p_reach_target"]
        if isinstance(cp, dict) or isinstance(bp, dict):
            # cash-swept ranges: only claim dominance if it holds at BOTH ends
            # of the sweep; anything else is indeterminate, and saying so is
            # the finding.
            at_low, at_high = _lo(cp) >= _lo(bp), _hi(cp) >= _hi(bp)
            out["volatility_dominates_target"] = (
                at_low if at_low == at_high
                else "INDETERMINATE_WITHIN_CASH_SWEEP")
        else:
            out["volatility_dominates_target"] = (cp >= bp)
        out["tail_note"] = (
            "the cash balance is unknown and the dominance comparison flips "
            "inside the cash sweep — no single reading is honest, so none is "
            "given" if out["volatility_dominates_target"]
            == "INDETERMINATE_WITHIN_CASH_SWEEP" else
            "the conservative arm reaches the target MORE often than the base "
            "arm while ending poorer in the median and ruined more often — the "
            "target is far enough out that it is a volatility outcome, not a "
            "return outcome. Read P(reach) beside the median and P(ruin), "
            "never alone." if out["volatility_dominates_target"] else
            "the target ordering follows the return assumption: the "
            "conservative arm reaches it least often.")
    out["headline"] = (
        "scenario-model probability under stated assumptions, not a forecast. "
        "The spread between the conservative and optimistic arms is MODEL "
        "uncertainty about the haircut and the correlation; the Monte Carlo "
        "error inside any one arm is far smaller and far less important.")
    return out


# ────────────────────────────── the daily brief ────────────────────────────

def _evidence_basis() -> dict:
    """Which research verdicts are actually constraining today's numbers.

    A brief that prints an analyst-derived number without saying what the lab
    measured about analyst-derived numbers is not a disciplined brief, it is a
    brief with a disclaimer at the bottom. This block names the specific
    verdicts and their receipts.
    """
    try:
        from backend.services import signal_registry as SR
        reg = SR.load()
    except Exception as exc:  # noqa: BLE001 - a missing registry is a finding
        return {"status": "REGISTRY UNAVAILABLE", "error": str(exc)[:200],
                "consequence": ("nothing below is evidence-graded; treat every "
                                "number as ungraded")}
    return {
        "status": "OK",
        "registry_written": reg.written,
        "usable_now": [f"{s.signal_id} [{s.label()}]" for s in reg.pm_allowed()],
        "closed_and_cannot_be_used": [
            f"{s.signal_id} [{s.evidence_grade}]" for s in reg.closed()],
        "queued_not_yet_permitted": [s.signal_id for s in reg.queued()],
        "uncalibrated": [s.signal_id for s in reg.uncalibrated()],
        "the_one_that_matters": (
            "analyst_target_upside_xs is CLOSED/PERVERSE. Ranking a "
            "cross-section by analyst-implied upside lost 8-18%/yr GROSS on "
            "21 years of point-in-time IBES (ANALYST-IBES-1, 2026-08-11), and "
            "-3.6/-7.2 t on two earlier instruments. This brief uses the "
            "haircut target only to SIZE a held name — but its CANDIDATE list "
            "is still ranked by that same quantity, which is choosing. See "
            "registry_conflicts; the contradiction is printed rather than "
            "quietly kept."),
    }


#: Where the funnel leaves its last run. The brief READS this; it never runs
#: the funnel inline, because a 27-batch market screen inside a morning report
#: is how a report becomes something nobody waits for.
MARKET_RADAR_PATH = (Path(__file__).resolve().parents[2] / "docs"
                     / "opportunity_funnel_run.json")
MARKET_RADAR_STALE_HOURS = 36


def _market_radar(path: Path | None = None, *, top: int = 10) -> dict:
    """The last opportunity-funnel run, with its age stated.

    A stale radar is not a missing radar and neither is an outage — all three
    are distinguished, because a market screen that quietly shows last week's
    names is worse than one that shows none.
    """
    import json as _json

    p = Path(path or MARKET_RADAR_PATH)
    if not p.exists():
        return {"status": "NEVER RUN",
                "how": "python -m backend.services.opportunity_funnel, or "
                       "scripts/run_funnel.py",
                "consequence": "the brief can only see the watchlist today"}
    try:
        raw = _json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"status": "UNREADABLE", "error": str(exc)[:200],
                "consequence": "treated as absent, NOT as an empty market"}
    age_h = (time.time() - p.stat().st_mtime) / 3600.0
    out = {
        "status": "STALE" if age_h > MARKET_RADAR_STALE_HOURS else "OK",
        "generated_at": raw.get("generated_at"),
        "age_hours": round(age_h, 1),
        "universe_screened": (raw.get("universe") or {}).get("screened"),
        "stages": raw.get("stages"),
        "funnel_failures": raw.get("failures") or {},
        "ranked_by": (raw.get("evidence_basis") or {}).get("ranked_by"),
        "not_ranked_on": (raw.get("evidence_basis") or {}).get(
            "recorded_but_not_ranked_on"),
        "candidates": (raw.get("candidates") or [])[:top],
    }
    if out["status"] == "STALE":
        out["consequence"] = (
            f"this radar is {age_h:.0f}h old; prices and fundamentals have "
            f"moved and it must not be traded from")
    return out


def _registry_conflicts(actions: list[dict]) -> list[dict]:
    """Where this brief is doing something the research lab has graded against.

    This is not decoration. On 2026-08-11 the lab measured analyst-implied
    upside as a CROSS-SECTIONAL PICKER and found it negative on three
    independent instruments, most recently -8% to -18%/yr GROSS over 21 years
    of point-in-time IBES. The registry therefore permits the haircut target
    only as a RISK_INPUT: it may size a name chosen on other grounds.

    The brief's candidate list does not yet obey that. Candidates are ranked by
    a certainty equivalent built from implied upside, which IS using it to
    choose. Rather than redesign the selection layer in the same session that
    produced the finding -- and ship an untested ranking on Murat's real book --
    the contradiction is printed at the top of every brief until it is fixed.

    A product that knows it is inconsistent and says so is recoverable. One
    that quietly keeps ranking on a killed signal is the thing this programme
    exists to prevent.
    """
    from backend.services import signal_registry as SR

    out: list[dict] = []
    try:
        reg = SR.load()
    except Exception as exc:  # noqa: BLE001
        # An unreadable registry must not produce a CLEAN brief. Returning an
        # empty conflict list here would make "no known conflicts" and "we
        # could not check" render identically — the house bug, in the one
        # function whose whole job is to notice a problem.
        logger.error("registry unavailable; conflicts NOT checked: %s", exc)
        return [{
            "severity": "HIGH",
            "what": "the signal registry could not be loaded, so NOTHING in "
                    "this brief was checked against a research verdict",
            "signal": "(registry)",
            "grade": "UNKNOWN",
            "evidence": f"{type(exc).__name__}: {str(exc)[:160]}",
            "affects": ["every recommendation below"],
            "consequence": "absence of a warning here is not evidence of "
                           "absence of a conflict",
            "fix": "restore backend/data/signal_registry.yaml and re-run",
        }]

    buys = [a for a in actions
            if a.get("action") in ("BUY", "ADD") and not a.get("held")]
    if buys and not reg.permits("analyst_target_upside_xs", "PICKER"):
        out.append({
            "severity": "HIGH",
            "what": ("candidates are ranked by a certainty equivalent built "
                     "from analyst-implied upside, which is CHOOSING on a "
                     "signal the registry permits only for SIZING"),
            "signal": "analyst_target_upside_xs",
            "grade": reg.get("analyst_target_upside_xs").evidence_grade,
            "evidence": ("-8% to -18%/yr GROSS over 21 years of point-in-time "
                         "IBES (ANALYST-IBES-1, 2026-08-11); t -3.6 largemid "
                         "and -7.2 small on two earlier instruments"),
            "affects": [a["ticker"] for a in buys],
            "consequence": ("every BUY in this brief rests on an ordering the "
                            "lab has measured as negative. Treat them as "
                            "candidates for your own judgement, not as a "
                            "ranked recommendation."),
            "fix": ("select candidates with a registry-permitted PICKER "
                    "(profitability_small is the one available on free data, "
                    "and the opportunity funnel already uses it), then use the "
                    "haircut target only to size what was chosen."),
        })
    return out


def daily_brief(book: Book | None = None, *, include_watchlist: bool = True,
                max_candidates: int = 10,
                record_snapshots: bool = False,
                market_radar_path: Path | None = None) -> dict:
    book = book or load_book()
    market_radar = _market_radar(market_radar_path)
    mode = book.mode
    problems = validate_book(book)

    # ── 1. what do we know about each name we hold ──────────────────────────
    rows: list[dict] = []
    for p in book.positions:
        e = enrich(p.ticker, p, record_snapshot=record_snapshots)
        rows.append({"ticker": p.ticker, "state": e, "alpha": analyst_alpha(e),
                     "distribution": distribution(e),
                     "held": True,
                     "decisionable": bool(e.get("decisionable")),
                     "thesis": p.thesis, "kill_condition": p.kill_condition,
                     "kill_condition_provenance": p.kill_condition_provenance,
                     "cost_basis": p.cost_basis, "shares": p.shares,
                     "dollars": p.dollars})

    # ── 2. mark the book to market. shares x live price, not a YAML number ──
    prices = {r["ticker"]: (r["state"] or {}).get("price") for r in rows}
    marked = mark_book(book, prices)
    nav = marked["nav"]
    for r in rows:
        m = marked["marks"][r["ticker"]]
        r["market_value"] = round(m["market_value"], 2)
        r["current_weight"] = round(m["weight"], 4)
        r["valuation_basis"] = m["basis"]
        r["priced_live"] = m["priced"]
        px, cb, sh = m.get("price"), r["cost_basis"], m.get("shares")
        r["pnl_pct"] = round(px / cb - 1.0, 4) if (px and cb) else None
        r["pnl_dollars"] = (round((px - cb) * sh, 2)
                            if (px and cb and sh is not None) else None)

    # ── 3. candidates, from the watchlist. Not-decisionable ones never enter ─
    held = {p.ticker for p in book.positions}
    candidates: list[dict] = []
    if include_watchlist:
        for t in book.watchlist:
            if t in held:
                continue
            e = enrich(t, record_snapshot=record_snapshots)
            if not e.get("decisionable"):
                continue
            d = distribution(e)
            if not d.get("available"):
                continue
            candidates.append({"ticker": t, "state": e,
                               "alpha": analyst_alpha(e), "distribution": d,
                               "held": False, "decisionable": True,
                               "current_weight": 0.0})
        # rank on the certainty equivalent — the same currency the portfolio is
        # solved in, not the display score
        candidates.sort(key=lambda c: -(c["distribution"]
                                        .get("certainty_equivalent") or -9))
        candidates = candidates[:max_candidates]

    # ── 4. ONE target portfolio over holdings ∪ candidates ──────────────────
    plan = build_target_portfolio(rows + candidates, mode)
    tw = plan["target_weights"]
    for r in rows + candidates:
        r["proposed"] = {"target_weight": tw.get(r["ticker"], 0.0)}

    actions: list[dict] = []
    for r in rows + candidates:
        rec = action_for(r.get("current_weight", 0.0),
                         r["proposed"]["target_weight"], nav,
                         decisionable=r.get("decisionable", False),
                         held=r.get("held", False),
                         reasons=(r.get("state") or {}).get("missing_reasons"),
                         round_trip_cost=(((r.get("state") or {})
                                           .get("liquidity") or {})
                                          .get("assumed_round_trip_cost",
                                               RETAIL_ROUND_TRIP)))
        rec["ticker"] = r["ticker"]
        rec["thesis"] = r.get("thesis", "")
        rec["kill_condition"] = r.get("kill_condition", "")
        rec["kill_condition_provenance"] = r.get("kill_condition_provenance",
                                                 "")
        # the row holds the SAME object, so a later cash-constraint rescale is
        # reflected in the holdings table and not just in the ticket list
        r["recommendation"] = rec
        if rec["action"] not in ("HOLD", "SKIP"):
            actions.append(rec)
    # Unknown cash buys nothing: for FUNDING purposes an unrecoverable balance
    # is $0 (the conservative reading), while NAV and the wealth question sweep
    # it as a sensitivity parameter instead of assuming it away.
    funding_cash = 0.0 if book.cash is None else float(book.cash)
    cash_check = enforce_cash_constraint(actions, funding_cash, nav)
    if book.cash is None:
        cash_check["cash_basis"] = (
            "UNKNOWN — treated as $0 for funding buys (unknown cash may not "
            "fund a ticket); swept over CASH_SENSITIVITY_GRID in NAV and the "
            "wealth simulation")
    actions = [a for a in actions if a["action"] not in ("HOLD", "SKIP")]

    # ── 5. the replacement table is a DECOMPOSITION of that one solution ────
    funding = funding_plan(actions, funding_cash)
    replacements = []
    for f in funding:
        if f["funded_by"] in ("CASH", "UNFUNDED"):
            continue
        c = next((x for x in rows + candidates if x["ticker"] == f["buy"]), None)
        h = next((x for x in rows if x["ticker"] == f["funded_by"]), None)
        if not c or not h:
            continue
        edge = replacement_edge(c, h)
        edge["dollars"] = f["dollars"]
        edge["source"] = "decomposition of the solved target portfolio"
        # The optimiser does not charge trading costs; this is the pair-level
        # check of whether the move it chose actually pays for itself. A STAY
        # here is DISSENT against a trade the plan is making, not a suggestion
        # to do nothing — and it is worth reading, because it is the only place
        # the cost of a specific swap is priced.
        edge["clears_own_cost_hurdle"] = edge.get("verdict") == "SWITCH"
        edge["reading"] = (
            "the plan makes this trade; the pair-level economics clear the "
            f"{SWITCH_THRESHOLD:.0%} hurdle" if edge["clears_own_cost_hurdle"]
            else "DISSENT — the plan makes this trade, but this pair does not "
                 "clear its own switching cost. The cost-aware band suppresses "
                 "the worst of these; anything left is a judgement call.")
        replacements.append(edge)

    # ── 6. the wealth question, on the PROPOSED book, in three scenarios ────
    proposed_rows = [r for r in rows + candidates
                     if r["proposed"]["target_weight"] > 0]
    wealth = wealth_scenarios(proposed_rows, marked["invested"], book.cash,
                              book.wealth_targets)
    threats = [{"ticker": r["ticker"], "why": w} for r in rows
               for w in threats_for(r)]

    # ── 7. what is scheduled to happen to these names, and what we cannot see
    from backend.services import pm_catalysts
    try:
        cal = pm_catalysts.calendar([p.ticker for p in book.positions],
                                    {p.ticker: p for p in book.positions})
    except Exception as e:                       # noqa: BLE001
        logger.warning("catalyst calendar unavailable: %s", e)
        cal = {"0_7d": [], "8_30d": [], "31_90d": [], "beyond_90d": [],
               "events_found": 0, "failures": [{"error": str(e)[:100]}],
               "coverage": pm_catalysts.coverage()}

    stale_value = sum(m["market_value"] for t, m in marked["marks"].items()
                      if not m["priced"])
    stale_frac = (stale_value / nav) if nav > 0 else 1.0
    # One permanently-halted microcap must not freeze the whole book forever,
    # but every ticket is sized off NAV, so an unpriced position is real
    # uncertainty in every number below. Tolerate a small one, name it, and
    # refuse above the threshold.
    material = stale_frac > UNPRICED_NAV_TOLERANCE
    # NIGHT-13 §0: `confirmed` no longer gates actionability — it grades the
    # evidence. A book is actionable when it LOADS AND VALIDATES and its NAV is
    # priced within tolerance; an unconfirmed book's proposals are priced on
    # the best-evidence book and LABELLED with that grade instead of blocked.
    actionable = not problems and not material
    grade = book.evidence_grade
    grade_note = (None if book.confirmed else
                  "proposals priced on best-evidence book (unconfirmed) — "
                  "evidence grade, not a blocker")
    blockers = _blockers(book, problems, marked, stale_frac)
    if actionable:
        ticket_label = ("TODAY'S TICKETS" if book.confirmed else
                        "TODAY'S TICKETS — BEST-EVIDENCE BOOK (UNCONFIRMED)")
        banner = grade_note
    else:
        ticket_label = "SIMULATED TICKETS — BOOK INCOMPLETE — DO NOT EXECUTE"
        banner = ("SIMULATED — this book cannot produce an executable ticket. "
                  + "; ".join(blockers))
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "account": book.account,
        "positions_confirmed": book.confirmed,
        "evidence_grade": grade,
        "evidence_grade_note": grade_note,
        "actionable": actionable,
        "actionable_blockers": blockers,
        "nav_uncertainty": {
            "unpriced_value": round(stale_value, 2),
            "unpriced_share_of_nav": round(stale_frac, 4),
            "tolerance": UNPRICED_NAV_TOLERANCE,
            "material": material,
            "note": ("every ticket is sized off NAV, so an unpriced position is "
                     "uncertainty in every dollar figure here")},
        "ticket_label": ticket_label,
        "banner": banner,
        "book_problems": problems,
        "sizing_mode": book.sizing_mode,
        "mode_limits": mode,
        "valuation": marked,
        "portfolio_value": round(nav, 2),
        "nav_basis": marked.get("nav_basis", "equity_plus_cash"),
        "cash": (None if book.cash is None else round(book.cash, 2)),
        "cash_reconciliation": cash_check,
        "holdings": rows,
        "actions": actions,
        "plan": plan,
        "opportunities": [{"ticker": c["ticker"],
                           "score": c["alpha"].get("score"),
                           "certainty_equivalent":
                               c["distribution"].get("certainty_equivalent"),
                           "expected_return":
                               c["distribution"].get("expected_return"),
                           "in_target_portfolio":
                               c["proposed"]["target_weight"] > 0,
                           "target_weight": c["proposed"]["target_weight"],
                           "implied_upside": c["alpha"].get("implied_upside"),
                           "distribution": c["distribution"],
                           "state": {k: c["state"].get(k) for k in
                                     ("price", "target_median", "n_analysts",
                                      "rating_drift_3m", "net_90d",
                                      "binary_event_risk")}}
                          for c in candidates],
        "opportunity_scope": ("watchlist only — this is a user watchlist view. "
                              "The market-wide funnel is a separate section; "
                              "see `market_radar`."),
        "market_radar": market_radar,
        "evidence_basis": _evidence_basis(),
        "registry_conflicts": _registry_conflicts(actions),
        "funding_plan": funding,
        "replacements": replacements,
        "threats": threats,
        "catalysts": cal,
        "wealth": wealth,
        "model_status": {
            **model_status(book, rows, marked, wealth, problems, cal),
            "trades_not_clearing_their_own_cost":
                sum(1 for r in replacements if not r["clears_own_cost_hurdle"]),
            "trades_priced_pairwise": len(replacements)},
        "evidence_note": (
            "Everything analyst-derived here is OBSERVATIONAL and has not been "
            "validated by the Aegis research lab. That label is deliberate: "
            "the lab's job is to say how much to trust it, and until it has, "
            "this is a disciplined version of a process that has been run by "
            "hand — not a demonstrated edge."),
    }


def _blockers(book: Book, problems: list[str], marked: dict,
              stale_frac: float = 0.0) -> list[str]:
    """What actually stops a ticket. NIGHT-13 §0: lack of confirmation is NOT
    a blocker any more — it is an evidence grade, reported beside the answer
    (`evidence_grade`, `evidence_grade_note`), never in this list."""
    out = []
    if problems:
        out.append(f"{len(problems)} book validation problem(s)")
    if marked.get("no_shares"):
        out.append(f"{len(marked['no_shares'])} position(s) have no share "
                   f"count, so their value cannot move with the price")
    if marked.get("no_quote"):
        out.append(f"no live quote for {', '.join(marked['no_quote'])} — "
                   f"{stale_frac:.1%} of NAV is unpriced "
                   f"(tolerance {UNPRICED_NAV_TOLERANCE:.0%})")
    return out


def model_status(book: Book, rows: list[dict], marked: dict, wealth: dict,
                 problems: list[str], catalysts: Optional[dict] = None) -> dict:
    """Can a reader tell in five seconds how much to trust today's answer?

    Everything that determines the grade of the output, in one object: how the
    book was valued, how complete the evidence is, whether we hold any target
    history at all, whether there is a catalyst layer (there is not), and how
    far the answer moves when the assumptions do.
    """
    from backend.services import analyst_ledger
    comp = [(r["state"].get("evidence") or {}).get("completeness", {})
            for r in rows if r.get("state", {}).get("decisionable")]
    frac = (sum(c.get("known_fraction", 0) for c in comp) / len(comp)) if comp else 0.0
    rel = [(r["state"].get("evidence") or {}).get("reliability", {})
           .get("multiplier") for r in rows if r.get("decisionable")]
    try:
        led = analyst_ledger.coverage()
    except Exception as e:                       # noqa: BLE001
        led = {"rows": 0, "revisions_possible": False, "error": str(e)[:80]}
    rng = (wealth.get("range") or {}).get("p_reach_target") or {}
    decisionable = sum(1 for r in rows if r.get("decisionable"))
    return {
        "book_confirmed": book.confirmed,
        "book_evidence_grade": book.evidence_grade,
        "book_problems": problems,
        "valuation_basis": marked["basis"],
        "valuation_grade": marked["valuation_grade"],
        "nav_basis": marked.get("nav_basis", "equity_plus_cash"),
        "nav_complete": marked["nav_complete"],
        "positions": len(rows),
        "decisionable_positions": decisionable,
        "review_positions": len(rows) - decisionable,
        "mean_evidence_completeness": round(frac, 3),
        "mean_reliability_multiplier": (round(sum(rel) / len(rel), 3)
                                        if rel else None),
        "analyst_sources": ["yahoo (yfinance)"],
        # Silent-fragility surface: a fabricated sigma changes every Kelly
        # weight, and a binary-event check that did not run makes the riskiest
        # names LARGER. Both must be visible or they are not fixable.
        "volatility_fallbacks": [r["ticker"] for r in rows
                                 if (r.get("state") or {})
                                 .get("vol_measured") is False],
        "binary_check_did_not_run": [r["ticker"] for r in rows
                                     if (r.get("state") or {})
                                     .get("binary_check_ran") is False],
        "analyst_history_available": bool(led.get("revisions_possible")),
        "analyst_ledger": led,
        "target_revision_fields": ("MISSING — needs two snapshots of the same "
                                   "ticker spanning the window"
                                   if not led.get("revisions_possible")
                                   else "available from the snapshot ledger"),
        "catalyst_coverage": _catalyst_grade(catalysts),
        "catalysts_uncovered": ((catalysts or {}).get("coverage") or {})
                               .get("uncovered", list()),
        "return_model_grade": "OBSERVATIONAL, unvalidated — TARGET_HAIRCUT is "
                              "fitted to nothing",
        "scenario_sensitivity": ({"p_reach_target_low": rng.get("low"),
                                  "p_reach_target_base": rng.get("base"),
                                  "p_reach_target_high": rng.get("high")}
                                 if rng else None),
        "last_refresh": datetime.now().isoformat(timespec="seconds"),
    }


def _catalyst_grade(cal: Optional[dict]) -> str:
    """An empty calendar is never allowed to read as "nothing is coming"."""
    if not cal:
        return "NONE — no catalyst layer ran"
    cov = cal.get("coverage") or {}
    if not cov.get("vendor_available"):
        return "NONE — no Finnhub key, so not even earnings dates are covered"
    return (f"v0 — EARNINGS ONLY ({cal.get('events_found', 0)} scheduled "
            f"across {cov.get('tickers_checked', 0)} names). NOT covered: "
            + ", ".join(cov.get("uncovered", [])[:4]) + ", ...")


def threats_for(r: dict) -> list[str]:
    e, out = r.get("state") or {}, []
    if not e.get("decisionable"):
        return [f"NOT DECISIONABLE — {'; '.join(e.get('missing_reasons') or ['no data'])}"]
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
