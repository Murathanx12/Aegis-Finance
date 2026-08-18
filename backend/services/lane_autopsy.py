"""LANE-AUTOPSY-1++ — the mirror/conviction gap, one difference at a time.

    from backend.services import lane_autopsy as LA
    out = LA.decompose(prices, shares, LA.CONVICTION_RULES, LA.MIRROR_RULES)

THE QUESTION (Order 17 P1, Order 18 §3.3)
==========================================
Two lanes were seeded on 2026-06-08 from the SAME twelve holdings and the same
$100k. `conviction` never rebalances. `mirror` runs monthly HRP with a 5% drift
trigger and position caps. They have since diverged, and the gap is the most
information-dense number on the board for Murat's own investing — because it is
not a comparison of two stock-picking ideas, it is a comparison of the SAME
picks under two management regimes.

A total gap answers nothing on its own. "Mirror lost 14 points to conviction"
is compatible with the rebalancing being wrong, the caps being wrong, the
cadence being wrong, or the costs eating it — and those have completely
different remedies. So the gap is decomposed by turning on ONE mechanism at a
time.

WHY ONE-AT-A-TIME IS NOT ENOUGH, AND WHAT THIS DOES INSTEAD
------------------------------------------------------------
The obvious design — start from conviction, add each mechanism alone, report
five numbers — is wrong in a way that looks right: **the five numbers will not
sum to the gap**, because the mechanisms interact. Caps only bind if a position
has run; rebalancing only costs if it trades; the drift trigger only fires if
weights move. A decomposition presented as additive when it is not is the
Brinson interaction error, and this project already knows that shape.

So this measures BOTH directions and reports the disagreement rather than
choosing one:

    MARGINAL     conviction + exactly one mechanism      "what does it add alone"
    LEAVE-ONE-OUT  mirror minus exactly one mechanism    "what does it add last"

If a mechanism's two numbers agree it is separable and the attribution is
clean. If they disagree, the difference IS the interaction, it is printed, and
no single number is offered in its place. The residual — gap minus the sum of
marginals — is always printed, because a residual that is large is the finding.

WHAT THIS MAY AND MAY NOT CONCLUDE
-----------------------------------
DESCRIPTIVE ONLY. The lanes have run since 2026-06-08, which is far short of
the 24 months before any skill claim, and Order 17 is explicit: the 2027
decision date gates the VERDICT, not the DIAGNOSIS. Nothing here promotes a
lane, seeds a lane, or licenses a change to either. A two-month gap between two
management regimes over twelve names is one draw from a distribution nobody has
characterised, and the module refuses to annualise it for exactly that reason.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import Sequence

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class ReplayRefused(RuntimeError):
    """A replay was asked for something its inputs cannot support.

    The missing input is usually PRICE COVERAGE: a name that stops trading
    mid-window silently drops out of a weight vector and the remaining names
    re-normalise, which shows up as a return rather than as an error. That is
    survivorship arriving through the back door, so it stops here.
    """


#: The mechanisms that differ between the two lanes, named so a contribution can
#: be attributed to one of them rather than to "management".
MECHANISMS = ("weights", "cadence", "drift_trigger", "caps", "costs")


@dataclass(frozen=True)
class LaneRules:
    """One lane's management, with every knob that differs made explicit."""

    label: str
    #: "none" keeps the seeded share counts; "hrp"/"equal" re-weight.
    optimizer: str = "none"
    #: "never" | "monthly"
    rebalance_frequency: str = "never"
    #: Rebalance early if any weight drifts this far from target. None = off.
    rebalance_trigger_drift: float | None = None
    max_single_name: float | None = None
    max_sector: float | None = None
    #: ONE-WAY basis points, charged against `sum(|dw|)` which counts both legs.
    #: The unit is in the name for the Order 18 §1 reason.
    cost_bps_one_way: float = 0.0
    slippage_bps_one_way: float = 0.0

    @property
    def total_cost_bps_one_way(self) -> float:
        return self.cost_bps_one_way + self.slippage_bps_one_way


#: The two lanes as seeded, transcribed from `backend/data/book_lanes.yaml`.
#: Transcribed rather than imported so a replay of the 2026-06 lanes cannot
#: silently change when someone edits the live YAML — a replay whose rules move
#: with the config is not a replay.
CONVICTION_RULES = LaneRules(
    label="conviction", optimizer="none", rebalance_frequency="never",
    rebalance_trigger_drift=None, max_single_name=None, max_sector=None,
    cost_bps_one_way=5.0, slippage_bps_one_way=1.0)

MIRROR_RULES = LaneRules(
    label="mirror", optimizer="hrp", rebalance_frequency="monthly",
    rebalance_trigger_drift=0.05, max_single_name=0.25, max_sector=0.60,
    cost_bps_one_way=5.0, slippage_bps_one_way=1.0)

#: Which rule fields each named mechanism owns. A mechanism is flipped by
#: copying exactly these fields across, so "one difference at a time" is
#: enforced by the data structure rather than by careful editing.
_MECHANISM_FIELDS = {
    "weights": ("optimizer",),
    "cadence": ("rebalance_frequency",),
    "drift_trigger": ("rebalance_trigger_drift",),
    "caps": ("max_single_name", "max_sector"),
    "costs": ("cost_bps_one_way", "slippage_bps_one_way"),
}


def differing_mechanisms(a: LaneRules, b: LaneRules) -> tuple[str, ...]:
    out = []
    for mech, fields in _MECHANISM_FIELDS.items():
        if any(getattr(a, f) != getattr(b, f) for f in fields):
            out.append(mech)
    return tuple(out)


def _flip(base: LaneRules, target: LaneRules, mechanisms: Sequence[str]) -> LaneRules:
    """`base` with exactly `mechanisms` taken from `target`."""
    unknown = [m for m in mechanisms if m not in _MECHANISM_FIELDS]
    if unknown:
        raise ReplayRefused(f"unknown mechanism(s) {unknown}; "
                            f"have {sorted(_MECHANISM_FIELDS)}")
    kw = {}
    for m in mechanisms:
        for f in _MECHANISM_FIELDS[m]:
            kw[f] = getattr(target, f)
    label = base.label + "+" + "+".join(mechanisms) if mechanisms else base.label
    return replace(base, label=label, **kw)


# ── weighting ──────────────────────────────────────────────────────────────
def _hrp_weights(returns: pd.DataFrame) -> pd.Series:
    """HRP, with the SAME loud fallback the live lane uses.

    `paper_portfolios.yaml` gates HRP behind `min_observations=252`. A replay
    over a two-month window cannot clear that, so it falls back to equal weight
    exactly as the lane does — and it is reported on every cell rather than
    hidden, because "we replayed HRP" would be false. FACTORIAL-PM-1's M4 hit
    the same wall and made the same disclosure.
    """
    if returns.shape[0] < 252:
        w = pd.Series(1.0 / returns.shape[1], index=returns.columns)
        w.attrs["fallback"] = "EQUAL_WEIGHT_HRP_HISTORY_GATE_NOT_MET"
        return w
    cov = returns.cov()
    ivp = 1.0 / np.diag(cov)
    w = pd.Series(ivp / ivp.sum(), index=returns.columns)
    w.attrs["fallback"] = ""
    return w


def _apply_caps(w: pd.Series, rules: LaneRules) -> pd.Series:
    """Cap single names, then re-normalise. Iterated, and REFUSES if infeasible.

    Two failures live here, and the tests found the second one:

    1. Re-normalising after a cap can push another name over it, so a single
       pass leaves a violation behind that is small enough to miss in a weight
       table. Hence the loop.

    2. **A cap can be arithmetically impossible.** `n` names capped at `c` can
       only hold `n*c` of the book, so any `n*c < 1` has NO feasible weight
       vector — and the naive loop does not fail, it OSCILLATES, and returns a
       violating vector on whichever iteration it happens to stop. That is a
       constraint violation wearing the shape of a converged answer. It is
       refused instead.

    The live mirror lane is feasible (12 names at 25% holds 3.0x the book), so
    this refusal never fires there — which is exactly why it would have gone
    unnoticed until a lane with fewer names met it.
    """
    if rules.max_single_name is None:
        return w
    cap, n = float(rules.max_single_name), len(w)
    if n * cap < 1.0 - 1e-12:
        raise ReplayRefused(
            f"a cap of {cap:.3f} over {n} names can hold at most {n * cap:.3f} "
            f"of the book: there is NO feasible weight vector. The iteration "
            f"that would 'apply' this cap oscillates and returns whichever "
            f"violating vector it stopped on, which looks like a converged "
            f"answer. Refusing.")
    out = w.astype(float).copy()
    for _ in range(200):
        over = out > cap + 1e-12
        if not over.any():
            break
        excess = float((out[over] - cap).sum())
        out[over] = cap
        under = ~over
        room = float((cap - out[under]).clip(lower=0).sum())
        if room <= 0:
            break
        # Distributed in proportion to REMAINING ROOM, not to weight: sharing
        # by weight sends the most to the name closest to the cap, which puts
        # it over and is what makes the naive version oscillate.
        share = (cap - out[under]).clip(lower=0) / room
        out[under] = out[under] + excess * share
    out = out / out.sum()
    if float(out.max()) > cap + 1e-6:
        raise ReplayRefused(
            f"capping did not converge: max weight {float(out.max()):.4f} "
            f"still exceeds {cap}. Returning this would report a constraint "
            f"as satisfied when it is not.")
    return out


def _target_weights(rules: LaneRules, hist: pd.DataFrame,
                    seed_w: pd.Series) -> pd.Series:
    if rules.optimizer == "none":
        w = seed_w.copy()
    elif rules.optimizer == "equal":
        w = pd.Series(1.0 / len(seed_w), index=seed_w.index)
    elif rules.optimizer == "hrp":
        w = _hrp_weights(hist)
    else:
        raise ReplayRefused(f"unknown optimizer {rules.optimizer!r}")
    return _apply_caps(w, rules)


# ── the replay ─────────────────────────────────────────────────────────────
def replay(prices: pd.DataFrame, shares: dict[str, float],
           rules: LaneRules) -> dict:
    """One lane's NAV path over `prices`, under `rules`."""
    if prices.empty or prices.shape[0] < 2:
        raise ReplayRefused("a replay needs at least two price rows")
    names = [t for t in shares if t in prices.columns]
    missing = sorted(set(shares) - set(names))
    if missing:
        raise ReplayRefused(
            f"no price column for {missing}. A name that silently drops out "
            f"lets the remaining weights re-normalise, which reads as a return "
            f"rather than as an error — survivorship through the back door.")
    px = prices[names].astype(float)
    if px.isna().any().any():
        px = px.ffill()
    if px.iloc[0].isna().any():
        raise ReplayRefused(
            f"names with no price at inception: "
            f"{sorted(px.columns[px.iloc[0].isna()])}")

    v0 = float(sum(shares[t] * px.iloc[0][t] for t in names))
    seed_w = pd.Series({t: shares[t] * px.iloc[0][t] / v0 for t in names})

    hist_for_w = px.pct_change().dropna()
    target = _target_weights(rules, hist_for_w, seed_w)
    fallback = getattr(target, "attrs", {}).get("fallback", "")

    w = target.copy()
    nav = [1.0]
    turnover_total, cost_total, n_rebal = 0.0, 0.0, 0
    rebal_dates: list[str] = []
    rate = rules.total_cost_bps_one_way / 1e4

    # Entry trade: moving off the seeded weights is a real trade and is charged.
    entry_turn = float(np.abs(target - seed_w).sum())
    if entry_turn > 0:
        turnover_total += entry_turn
        cost_total += entry_turn * rate
        nav[0] = 1.0 - entry_turn * rate

    rets = px.pct_change().fillna(0.0)
    prev_month = px.index[0].to_period("M")
    for i in range(1, len(px)):
        day = px.index[i]
        r = rets.iloc[i]
        port_r = float((w * r).sum())
        # Weights drift with prices before any rebalance decision.
        w = w * (1.0 + r)
        w = w / w.sum()
        nav.append(nav[-1] * (1.0 + port_r))

        due = False
        if rules.rebalance_frequency == "monthly":
            if day.to_period("M") != prev_month:
                due = True
        if rules.rebalance_trigger_drift is not None:
            if float(np.abs(w - target).max()) >= rules.rebalance_trigger_drift:
                due = True
        prev_month = day.to_period("M")

        if due:
            new_target = _target_weights(rules, rets.iloc[:i + 1], seed_w)
            turn = float(np.abs(new_target - w).sum())
            if turn > 0:
                cost = turn * rate
                nav[-1] *= (1.0 - cost)
                turnover_total += turn
                cost_total += cost
            w, target = new_target.copy(), new_target.copy()
            n_rebal += 1
            rebal_dates.append(str(day.date()))

    return {
        "label": rules.label,
        "nav": nav,
        "total_return": nav[-1] - 1.0,
        "n_rebalances": n_rebal,
        "rebalance_dates": rebal_dates,
        "turnover_total": round(turnover_total, 6),
        "cost_drag": round(cost_total, 6),
        "hrp_fallback": fallback,
        "n_days": len(nav),
        "n_names": len(names),
    }


def decompose(prices: pd.DataFrame, shares: dict[str, float],
              base: LaneRules = CONVICTION_RULES,
              target: LaneRules = MIRROR_RULES) -> dict:
    """The gap, attributed both ways, with the interaction printed."""
    mechs = differing_mechanisms(base, target)
    if not mechs:
        raise ReplayRefused(
            "the two rule sets are identical; there is no gap to decompose "
            "and a zero-mechanism report would read as 'management does not "
            "matter'")

    base_run = replay(prices, shares, base)
    full_run = replay(prices, shares, target)
    gap = full_run["total_return"] - base_run["total_return"]

    rows = []
    for m in mechs:
        marginal = replay(prices, shares, _flip(base, target, [m]))
        others = [x for x in mechs if x != m]
        loo = replay(prices, shares, _flip(base, target, others))
        d_marg = marginal["total_return"] - base_run["total_return"]
        d_loo = full_run["total_return"] - loo["total_return"]
        # A mechanism that moves NOTHING in either direction is not a small
        # effect — it is a rule that cannot fire, and the canon rule about dead
        # branches applies: a threshold that makes a branch unenterable is a
        # dead branch. Reporting it as "+0.00%" alongside real effects invites
        # the reading "we tested it and it did not matter", which is a
        # different and much stronger claim than "it never ran".
        inert = (abs(d_marg) < 1e-9 and abs(d_loo) < 1e-9)
        rows.append({
            "mechanism": m,
            "marginal_effect": round(d_marg, 6),
            "leave_one_out_effect": round(d_loo, 6),
            "interaction": round(d_loo - d_marg, 6),
            "separable": bool(abs(d_loo - d_marg) < 0.1 * max(abs(gap), 1e-9)),
            "inert": inert,
            "inert_note": ("this rule never fired on this window — it is a DEAD "
                           "BRANCH here, not a tested-and-immaterial effect"
                           if inert else ""),
            "n_rebalances_marginal": marginal["n_rebalances"],
            "turnover_marginal": marginal["turnover_total"],
        })

    sum_marg = sum(r["marginal_effect"] for r in rows)
    return {
        "base": base_run, "target": full_run,
        "gap_total": round(gap, 6),
        "mechanisms": rows,
        "sum_of_marginals": round(sum_marg, 6),
        "residual": round(gap - sum_marg, 6),
        "residual_share_of_gap": (round((gap - sum_marg) / gap, 4)
                                  if gap else None),
        "additive": bool(abs(gap - sum_marg) < 0.1 * max(abs(gap), 1e-9)),
        "note": ("marginal and leave-one-out are the SAME number only when a "
                 "mechanism is separable; where they differ the difference is "
                 "the interaction and no single attribution exists"),
        "may_not_conclude": ("DESCRIPTIVE. Inception 2026-06-08 is far short "
                             "of the 24 months before any skill claim; the "
                             "2027 date gates the verdict, not the diagnosis. "
                             "Not annualised, deliberately."),
    }
