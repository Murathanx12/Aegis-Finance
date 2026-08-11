"""What every decision would have been worth, branched and rolled forward.

THE QUESTION A STOP-LOSS CANNOT ANSWER
======================================

Murat's biggest stated regret is SOC: bought near $5, reached about $20, never
sold. His instinct is that he needs an exit rule. But CANON §15 records that a
trailing stop ranked FIRST on the panel and then lost 3.08 %/yr under realistic
execution — the trigger carried information the vehicle could not deliver. So
"add a stop" is a corpse, and the useful question is the harder one:

    at the moment a position has run up a long way, what OBSERVABLE separates
    the winners worth holding from the winners worth harvesting?

That is answerable without any model. Take every position on every decision
date, branch it — hold, sell to cash, sell to the benchmark, trim, take the
original stake back out — roll every branch forward on real prices, and look at
which state variables predict which branch won.

WHY THIS IS THE LEAKAGE-FREE HALF OF THE GRAND PLAN
---------------------------------------------------
The full market laboratory the reviews proposed needs an LLM reasoning inside a
historical world, and this project already measured that entity masking is
necessary but not sufficient (NIGHT-1) and that masking the name is not masking
the date (CANON §13). A model that has read 2012-2026 cannot be trusted to
simulate 2019. This engine has no such problem because there is no model in it:
it is arithmetic on prices that already happened. It can therefore produce
training data honestly, which the LLM half cannot.

WHAT IT STILL CANNOT DO
-----------------------
Every branch is measured over ONE realised path. Nine months of one market is
one draw, the decision dates overlap heavily, and the names are correlated — so
the effective sample is far smaller than the row count and any rule discovered
here is a HYPOTHESIS for forward testing, never a fitted policy. The row count
and the effective count are both reported for exactly that reason.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from backend.services.conviction_prices import synthetic_names

logger = logging.getLogger(__name__)

#: The branches. Deliberately includes "take the original stake out", because
#: that is the intuition most retail exits are actually reaching for and it is
#: measurably different from both holding and selling.
BRANCHES = ("hold", "sell_to_cash", "sell_to_benchmark", "trim_25", "trim_50",
            "take_original_out", "rotate_to_best_momentum")

#: Branches that are convex combinations of `hold` and `sell_to_cash`. They can
#: NEVER be the maximum of the set, so "was best in 0 of 60 rows" is arithmetic
#: rather than evidence, and counting them as if it were a result would report a
#: theorem as a finding. Their MEAN is meaningful; their win count is not.
INTERPOLATING = ("trim_25", "trim_50", "take_original_out")


@dataclass
class Decision:
    """One position, one date, every branch rolled to the end."""
    ticker: str
    decision_date: str
    entry_date: str
    state: dict
    outcomes: dict
    best_branch: str
    hold_minus_sell: float


def _state_at(px: pd.Series, entry_px: float, when: pd.Timestamp) -> dict | None:
    """What was observable at the decision date, and nothing that was not."""
    hist = px.loc[:when].dropna()
    if len(hist) < 40:
        return None
    p = float(hist.iloc[-1])
    peak = float(hist.max())
    r = hist.pct_change(fill_method=None).dropna()
    return {
        "price": p,
        "gain_since_entry": p / entry_px - 1.0,
        "drawdown_from_peak": p / peak - 1.0,
        "run_up_from_trough": p / float(hist.min()) - 1.0,
        "return_1m": float(p / hist.iloc[-21] - 1.0) if len(hist) > 21 else None,
        "return_3m": float(p / hist.iloc[-63] - 1.0) if len(hist) > 63 else None,
        "vol_3m_annual": (float(r.iloc[-63:].std(ddof=1) * np.sqrt(252))
                          if len(r) > 63 else None),
        "pct_of_peak": p / peak,
    }


def branch_outcomes(px: pd.Series, bench: pd.Series, best_alt: pd.Series | None,
                    when: pd.Timestamp, end: pd.Timestamp,
                    entry_px: float) -> dict:
    """Terminal value of one dollar under each branch, from the decision date.

    Cash earns nothing. That is deliberately assumption-free: any cash return
    assumption is a second decision smuggled into a test about the first.
    """
    p0 = float(px.loc[:when].dropna().iloc[-1])
    p1 = float(px.loc[:end].dropna().iloc[-1])
    b0 = float(bench.loc[:when].dropna().iloc[-1])
    b1 = float(bench.loc[:end].dropna().iloc[-1])
    hold, benchmark = p1 / p0, b1 / b0

    out = {
        "hold": hold,
        "sell_to_cash": 1.0,
        "sell_to_benchmark": benchmark,
        "trim_25": 0.75 * hold + 0.25,
        "trim_50": 0.50 * hold + 0.50,
    }
    # "take the original stake out": sell the fraction that returns the entry
    # cost, let the profit run. Undefined before the position has doubled, which
    # is itself the point — the manoeuvre is only available to a big winner.
    cost_fraction = entry_px / p0
    out["take_original_out"] = (
        cost_fraction + (1.0 - cost_fraction) * hold if cost_fraction < 1.0
        else hold)
    if best_alt is not None:
        a0 = float(best_alt.loc[:when].dropna().iloc[-1])
        a1 = float(best_alt.loc[:end].dropna().iloc[-1])
        out["rotate_to_best_momentum"] = a1 / a0
    return out


def build_decisions(prices: pd.DataFrame, holdings: dict[str, float],
                    decision_dates: list[str], end: str,
                    benchmark: str = "SPY") -> list[Decision]:
    """Every (position, date) pair with all its branches rolled forward.

    `holdings` maps ticker to the entry price the position was opened at.
    """
    synth = synthetic_names()
    endts = pd.Timestamp(end)
    out: list[Decision] = []
    for d in decision_dates:
        when = pd.Timestamp(d)
        if when >= endts:
            continue
        # the alternative available AT the decision date: strongest 3-month
        # momentum among the names, chosen on information available then
        mom = {}
        for t in prices.columns:
            if t in synth or t == benchmark:
                continue
            h = prices[t].loc[:when].dropna()
            if len(h) > 63:
                mom[t] = float(h.iloc[-1] / h.iloc[-63] - 1.0)
        best = max(mom, key=mom.get) if mom else None

        for tkr, entry_px in holdings.items():
            if tkr in synth or tkr not in prices.columns:
                continue
            st = _state_at(prices[tkr], entry_px, when)
            if st is None:
                continue
            alt = prices[best] if best and best != tkr else None
            try:
                oc = branch_outcomes(prices[tkr], prices[benchmark], alt, when,
                                     endts, entry_px)
            except (IndexError, ValueError):
                continue
            best_branch = max(oc, key=oc.get)
            out.append(Decision(
                ticker=tkr, decision_date=str(when.date()),
                entry_date="", state=st, outcomes=oc, best_branch=best_branch,
                hold_minus_sell=oc["hold"] - oc["sell_to_benchmark"]))
    logger.info("built %d decision rows over %d dates", len(out),
                len(decision_dates))
    return out


def effective_sample(rows: list[Decision]) -> dict:
    """How many INDEPENDENT decisions these rows actually contain.

    Every date sees the same names and every branch shares one realised path, so
    the row count overstates the evidence badly. The honest denominator for any
    claim is the number of distinct names, not the number of rows — the dates
    are overlapping views of the same nine months.
    """
    return {
        "n_rows": len(rows),
        "n_distinct_names": len({r.ticker for r in rows}),
        "n_dates": len({r.decision_date for r in rows}),
        "effective_n_for_inference": len({r.ticker for r in rows}),
        "why": ("decision dates overlap on one realised path, so rows are "
                "repeated measurements of the same nine months; only the names "
                "are separate draws, and they are correlated too"),
    }


def separating_power(rows: list[Decision], feature: str, *,
                     n_perm: int = 10_000, seed: int = 20260811) -> dict:
    """Does `feature` separate the decisions where holding won from where it lost?

    Tested by permuting the sign of the outcome across NAMES, not across rows:
    permuting rows would treat six views of one stock as six independent facts
    and would find significance in almost anything.
    """
    usable = [r for r in rows if r.state.get(feature) is not None]
    if len(usable) < 20:
        return {"feature": feature, "n": len(usable), "verdict": "TOO_FEW"}

    by_name: dict[str, list[tuple[float, float]]] = {}
    for r in usable:
        by_name.setdefault(r.ticker, []).append(
            (float(r.state[feature]), r.hold_minus_sell))
    names = sorted(by_name)
    x = np.array([np.mean([v for v, _ in by_name[n]]) for n in names])
    y = np.array([np.mean([o for _, o in by_name[n]]) for n in names])
    if len(names) < 8 or x.std() == 0:
        return {"feature": feature, "n": len(names), "verdict": "TOO_FEW"}

    obs = float(np.corrcoef(x, y)[0, 1])
    rng = np.random.default_rng(seed)
    null = np.array([np.corrcoef(x, rng.permutation(y))[0, 1]
                     for _ in range(n_perm)])
    p = float((np.abs(null) >= abs(obs)).mean())
    # the correlation this design would need to see 80% of the time
    mde = float(np.percentile(np.abs(null), 95) * 1.43)
    return {
        "feature": feature, "n_names": len(names), "n_rows": len(usable),
        "correlation_with_hold_minus_sell": obs,
        "p_value": p, "mde_correlation_80pct_power": mde,
        "detectable": bool(abs(obs) >= mde and p < 0.05),
        "verdict": ("SEPARATES" if abs(obs) >= mde and p < 0.05
                    else "UNRESOLVED"),
        "note": ("permuted across NAMES, not rows — permuting rows treats "
                 "repeated views of one stock as independent facts"),
    }
