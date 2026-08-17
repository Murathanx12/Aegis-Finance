"""M6 — the product surface, and the only one the evidence permits.

WHAT THE RESEARCH LEFT US WITH
==============================
The routed line (pull → library → M4 → replay) is complete and it terminated in
measured negatives. On our own panel, 2006-2019, net of 10bp:

* **Return prediction does not clear its bar.** 206 published predictors,
  median net −0.12%/yr; one is detectable net among tradable names, at 1.01× its
  own MDE, after a screen that expects ~1.1 false. Momentum's break-even is 2.6
  basis points per crossing. There is no established published benchmark in the
  liquid tercile at all.
* **M4 refused to spend its confirmation window** — the selected candidate's
  effect (+8.64%/yr) sits below the MDE that window can deliver (12.84%).
* **Risk control does resolve**, roughly 30× sooner than return on identical
  data.
* **And it is not merely "hold less".** Against a constant-exposure book at the
  SAME average weight, targeting constant volatility lowered max drawdown
  detectably in 3 of 4 configurations and volatility in 2 of 4.

So the product is an EXPOSURE RULE with an honest return statement. Not a stock
picker. This module exists to make that shape structural rather than editorial:
a claim that is not carried in `EVIDENCE` cannot be rendered, because there is
no code path that produces one.

WHY N18's NULL AND THE RISK RESULT ARE BOTH TRUE
================================================
N18 tested the declared personality objective, `net return − λ × max drawdown`,
against the matched constant and found 0 of 16 detectable. That objective mixes
in a RETURN term which is unresolvable on this window, and the noise from it
swamped the comparison. Isolating the risk statistic removes that term. Both
results stand, and quoting either one alone would misdescribe the product:

    the drawdown reduction is real; the *utility* improvement is not established.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

#: Trading days used for the realised-volatility estimate. The same 60 the
#: measurement used — a product that reports a number its evidence was not
#: computed on is quoting a different experiment.
LOOKBACK_DAYS = 60
TRADING_DAYS = 252

#: Below this many observations the volatility estimate is not trustworthy and
#: the layer refuses rather than sizing a book from noise.
MIN_OBSERVATIONS = 40


class RiskLayerRefused(RuntimeError):
    """The layer was asked for a number it has no evidence or data to give."""


@dataclass(frozen=True)
class Claim:
    """One measured statement, with everything needed to argue with it.

    `established` is not a mood. It is `|effect| >= mde`, decided when the
    measurement ran, and it is the only field the UI is allowed to branch on.
    """
    outcome: str
    effect: float | None
    units: str
    mde: float | None
    established: bool
    comparator: str
    note: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Evidence:
    """Everything the page may assert, and its provenance.

    Frozen because a product surface that can be edited at runtime is a product
    surface that will be, and then the claim on screen stops matching the
    measurement that justified it.
    """
    window: str
    base_asset: str
    n_days: int
    cost_bps_per_crossing: float
    status: str
    k_eff: float
    claims: tuple[Claim, ...]
    #: Whether a confirmation of these claims is REACHABLE — N22, asked before
    #: spending anything. "EXPLORE" without this reads as "confirmation
    #: pending", and on this corpus it is not pending, it is unavailable.
    confirmation: str = ""
    confirmation_note: str = ""

    def claim(self, outcome: str) -> Claim:
        for c in self.claims:
            if c.outcome == outcome:
                return c
        raise RiskLayerRefused(
            f"no measured claim for {outcome!r}. The page may only state what "
            f"was measured; there is deliberately no fallback that invents one.")

    def established_claims(self) -> tuple[Claim, ...]:
        return tuple(c for c in self.claims if c.established)

    def as_dict(self) -> dict:
        return {**asdict(self), "claims": [c.as_dict() for c in self.claims]}


#: THE MEASURED RECORD. Every number below comes from
#: `scripts/replay_personalities.py` and `scripts/sizing_layer_risk_outcome.py`
#: on 2006-01-03..2019-12-31, SPY total return, 3,523 days, 10bp per crossing.
#: Changing a number here without re-running those is the failure this whole
#: programme is built to prevent.
EVIDENCE = Evidence(
    window="2006-01-03..2019-12-31",
    base_asset="SPY total return, daily",
    n_days=3523,
    cost_bps_per_crossing=10.0,
    # EXPLORE, not confirmed: this window selected the rule, and M4's
    # confirmation window is reserved disjoint and deliberately unspent.
    status="EXPLORE — selection window, not a confirmation",
    k_eff=1.41,
    # N22 (2026-08-17), asked before spending: NONE of the eight
    # policy x outcome cells clears its own MDE on the 74 reserved months, at
    # either the declared alpha 0.025 or the laxer 0.05.
    confirmation="UNREACHABLE — this claim is permanently screen-grade on this "
                 "corpus",
    confirmation_note=(
        "The reserved 2020-06..2026-07 window is 74 months. Measured on that "
        "horizon rather than projected onto it, the volatility effect is "
        "-2.84pp against an MDE of 4.94 and the drawdown effect -6.09pp "
        "against 17.36. At the selection window's own crisis rate, 74 months "
        "expects 0.44 drawdowns of 20% — below one. So the window is not "
        "unspent because we are saving it; it cannot be spent usefully, and "
        "no confirmation of this claim is pending."),
    claims=(
        Claim(outcome="annual_volatility_vs_buy_and_hold",
              effect=-4.95, units="pp/yr", mde=3.46, established=True,
              comparator="buy and hold",
              note="targeting 15% vol at cap 1.0 lowered realised volatility "
                   "from 18.78% to 13.83%"),
        Claim(outcome="max_drawdown_vs_matched_exposure",
              effect=-19.18, units="pp", mde=16.55, established=True,
              comparator="constant exposure at the SAME average weight",
              note="3 of 4 configurations detectable; this is the one that "
                   "shows the rule is not merely holding less"),
        Claim(outcome="annual_volatility_vs_matched_exposure",
              effect=-2.91, units="pp/yr", mde=3.03, established=False,
              comparator="constant exposure at the SAME average weight",
              note="0.96x its own MDE — the tightest cell, and by S37 exactly "
                   "the kind of number that looks like it working"),
        Claim(outcome="annual_return", effect=+0.17, units="pp/yr", mde=5.19,
              established=False, comparator="buy and hold",
              note="NOT ESTABLISHED, and 30x further from resolution than the "
                   "risk outcome on identical data. This is the honest half "
                   "and it is not a disclaimer, it is the finding"),
        Claim(outcome="utility_vs_matched_exposure", effect=None, units="pts",
              mde=None, established=False,
              comparator="constant exposure at the SAME average weight",
              note="N18: 0 of 16 declared-personality objectives detectable. "
                   "`return - lambda x drawdown` carries the unresolvable "
                   "return term, so the utility gain is not established even "
                   "though the drawdown reduction is"),
        Claim(outcome="stock_selection", effect=None, units="", mde=None,
              established=False, comparator="206 published predictors",
              note="median net -0.12%/yr; nothing published clears +3%/yr net "
                   "in tradable names. This layer does not pick stocks and "
                   "there is no code path here that would"),
    ),
)

#: What a mean-variance investor at this risk aversion would pay, per year, for
#: the measured variance reduction. Both inputs are measured; lambda prices the
#: trade-off and does not supply a missing return estimate.
BREAK_EVEN_SACRIFICE = {1.0: 0.81, 3.0: 2.42}

#: N24 — THE BOUND, NOT JUST THE ESTIMATE.
#:
#: "Not established" is an `mde_mean` statement: our instrument could not
#: separate the estimate from zero. It says nothing about which values were
#: EXCLUDED, and exclusion is what a decision needs. So the upper one-sided 95%
#: bound on the return DRAG is carried beside the break-even it has to clear:
#:
#:     UCB(drag) < break_even(lambda)  =>  worth it wherever the truth sits.
#:
#: On the shipped configuration it does NOT clear at either declared lambda,
#: and that is the finding rather than a reason to look for a lambda that does.
#: `extra_years_required` is what would decide it — single digits at lambda 3,
#: against the ~95 years a RETURN claim needs. S59's ratio, a third time.
RETURN_DRAG_UPPER_BOUND_PCT = 2.93
RETURN_SACRIFICE_BOUND = {
    1.0: {"break_even_pct": 0.81, "verdict": "NOT_DEMONSTRATED",
          "extra_years_required": 128.0},
    3.0: {"break_even_pct": 2.42, "verdict": "NOT_DEMONSTRATED",
          "extra_years_required": 6.0},
}


@dataclass
class ExposureDecision:
    """What the layer would hold, why, and what would change it."""
    realised_vol: float
    target_vol: float
    cap: float
    weight: float
    capped: bool
    raise_to_cap_below_vol: float | None
    halve_above_vol: float
    note: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def realised_vol(returns) -> float:
    """Annualised realised volatility over the declared lookback.

    Refuses below `MIN_OBSERVATIONS`. A volatility computed from twelve days is
    a number, and sizing a real book from it is the honour-system failure with
    money attached.
    """
    xs = [float(r) for r in returns if r is not None and math.isfinite(float(r))]
    if len(xs) < MIN_OBSERVATIONS:
        raise RiskLayerRefused(
            f"{len(xs)} usable returns is below the {MIN_OBSERVATIONS} this "
            f"estimator needs. No exposure is recommended — a volatility from "
            f"too few days would size a real book from noise.")
    xs = xs[-LOOKBACK_DAYS:]
    m = sum(xs) / len(xs)
    var = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
    return math.sqrt(var * TRADING_DAYS)


def decide_exposure(returns, *, target_vol: float, cap: float = 1.0
                    ) -> ExposureDecision:
    """The exposure, and THE ONE THING THAT WOULD CHANGE IT.

    The thresholds are the point. "Hold 0.83" is an instruction; "hold 0.83,
    and this goes to 1.00 if 60-day volatility drops under 15.0%" is something
    a person can actually check against the world tomorrow.
    """
    if target_vol <= 0:
        raise RiskLayerRefused("target volatility must be positive")
    if cap <= 0:
        raise RiskLayerRefused("exposure cap must be positive")
    v = realised_vol(returns)
    raw = target_vol / v
    w = min(cap, raw)
    return ExposureDecision(
        realised_vol=v, target_vol=target_vol, cap=cap, weight=w,
        capped=raw > cap,
        # Below this volatility the rule wants more than the cap allows, so the
        # book sits at the cap and stops responding.
        raise_to_cap_below_vol=(target_vol / cap) if cap > 0 else None,
        halve_above_vol=2.0 * target_vol / w if w > 0 else float("inf"),
        note=("at the cap — the rule wants more exposure than it is allowed, "
              "so volatility would have to RISE before anything changes"
              if raw > cap else
              "responding to volatility; both thresholds below are live"))


def decision_log(dates, returns, *, target_vol: float, cap: float = 1.0,
                 n: int = 12) -> list[dict]:
    """What it would have held at each of the last `n` month-ends, and the cost.

    `cost_vs_full` is what de-risking gave up (negative) or saved (positive)
    over the month that FOLLOWED the decision, which is the only version of
    that number a person can check. Reporting the contemporaneous month would
    be scoring the rule on data it did not have.
    """
    if len(dates) != len(returns):
        raise RiskLayerRefused(
            f"{len(dates)} dates against {len(returns)} returns — a decision "
            f"log built from misaligned series would attribute each decision "
            f"to the wrong month")
    rows: list[dict] = []
    by_month: dict[str, list[int]] = {}
    for i, d in enumerate(dates):
        by_month.setdefault(str(d)[:7], []).append(i)
    months = sorted(by_month)
    for k in range(1, len(months)):
        prior = [i for m in months[:k] for i in by_month[m]]
        if len(prior) < MIN_OBSERVATIONS:
            continue
        try:
            dec = decide_exposure([returns[i] for i in prior],
                                  target_vol=target_vol, cap=cap)
        except RiskLayerRefused:
            continue
        nxt = by_month[months[k]]
        realised = 1.0
        for i in nxt:
            realised *= (1.0 + float(returns[i]))
        realised -= 1.0
        rows.append({
            "month": months[k],
            "weight": round(dec.weight, 4),
            "realised_vol": round(dec.realised_vol, 4),
            "market_return": round(realised, 4),
            # Positive = the de-risking helped that month; negative = it cost.
            "cost_vs_full": round((dec.weight - 1.0) * realised, 4),
        })
    return rows[-n:]


def sacrifice_bound(lam: float) -> dict:
    """The equivalence half of the return statement (N24).

    `verdict` is recomputed here from the two numbers rather than read from the
    table, for the same reason `established` is: a stored verdict is an opinion
    that can drift away from its arithmetic, and this one decides whether the
    page says "worth it whatever the truth is" or "we still cannot say".
    """
    if lam not in RETURN_SACRIFICE_BOUND:
        raise RiskLayerRefused(
            f"no sacrifice bound computed at lambda={lam}; declared: "
            f"{sorted(RETURN_SACRIFICE_BOUND)}")
    b = RETURN_SACRIFICE_BOUND[lam]
    ucb, be = RETURN_DRAG_UPPER_BOUND_PCT, b["break_even_pct"]
    ruled_out = ucb < be
    if ruled_out != (b["verdict"] == "RULED_OUT"):
        raise RiskLayerRefused(
            f"the stored verdict {b['verdict']!r} at lambda={lam} disagrees "
            f"with its own arithmetic (upper bound {ucb} vs break-even {be}). "
            f"A verdict that no longer follows from its numbers is the failure "
            f"this module exists to make impossible.")
    return {
        "upper_95_one_sided_drag_pct": ucb,
        "break_even_pct": be,
        "verdict": b["verdict"],
        "worth_it_across_the_interval": ruled_out,
        "extra_years_required": b["extra_years_required"],
        "statement": (
            f"the return sacrifice is bounded above by {ucb:.2f}%/yr; at risk "
            f"aversion {lam:g} the measured variance reduction is worth "
            f"{be:.2f}%/yr, so the policy is worth it wherever the true return "
            f"sits in the interval"
            if ruled_out else
            f"the return sacrifice is bounded above by {ucb:.2f}%/yr, which "
            f"still exceeds the {be:.2f}%/yr the variance reduction is worth "
            f"at risk aversion {lam:g} — short by {ucb - be:.2f}pp. About "
            f"{b['extra_years_required']:.0f} more years of data would decide "
            f"it"
            # Only invoke the comparison where it is actually favourable. At
            # lambda 1 the requirement EXCEEDS the ~95 years a return claim
            # needs, and quoting the ratio there would be citing a benchmark
            # this cell loses to.
            + (", against the ~95 a return claim would need"
               if b["extra_years_required"] < 90 else
               " — which is longer than the ~95 a return claim needs, so at "
               "this risk aversion the bound is the harder question, not the "
               "easier one")),
    }


def honest_claim(target_vol: float, lam: float = 1.0) -> dict:
    """The claim shape, assembled only from measured pieces.

    *"Risk reduced by X; return effect not established; break-even sacrifice
    Y."* Rendering this is the only way the page states a benefit, so a claim
    that is not in `EVIDENCE` cannot appear on screen.
    """
    vol = EVIDENCE.claim("annual_volatility_vs_buy_and_hold")
    dd = EVIDENCE.claim("max_drawdown_vs_matched_exposure")
    ret = EVIDENCE.claim("annual_return")
    if lam not in BREAK_EVEN_SACRIFICE:
        raise RiskLayerRefused(
            f"no break-even computed at lambda={lam}; declared: "
            f"{sorted(BREAK_EVEN_SACRIFICE)}")
    bound = sacrifice_bound(lam)
    return {
        "risk_reduced": {"volatility_pp": vol.effect, "mde_pp": vol.mde,
                         "vs": vol.comparator, "established": vol.established},
        "not_merely_holding_less": {
            "max_drawdown_pp": dd.effect, "mde_pp": dd.mde,
            "vs": dd.comparator, "established": dd.established},
        "return_effect": {"estimate_pp": ret.effect, "mde_pp": ret.mde,
                          "established": False,
                          "statement": "NOT ESTABLISHED — the estimate is "
                                       "0.03x its own MDE, so this window "
                                       "cannot tell a small gain from a small "
                                       "loss",
                          "bound": bound},
        "break_even_sacrifice_pct_per_year": BREAK_EVEN_SACRIFICE[lam],
        "break_even_note": (
            f"at risk aversion {lam:g} the measured variance reduction is "
            f"worth up to {BREAK_EVEN_SACRIFICE[lam]:.2f}%/yr of return; the "
            f"measured return change was {ret.effect:+.2f}%/yr"),
        "evidence": EVIDENCE.as_dict(),
        "target_vol": target_vol,
    }
