"""Three denominators for regret, because the obvious one has a non-zero null.

THE DEFECT THIS MODULE FIXES (G1, 2026-08-15)
=============================================
`ResponseSurface.regret_pct()` is *"best available minus what was done. Never
negative by construction."* The words "never negative by construction" are the
whole problem stated out loud. It is a maximum over seventeen noisy 63-day
outcomes minus one of them. A decision-maker with no skill whatsoever scores
large positive regret under that denominator, because the maximum of seventeen
draws is an upward-biased estimator of anything.

Measured on real index history, same menu, same cost, same horizon:

    always-HOLD                       ~ +5pp mean regret
    a policy picked at random         ~ +6pp
    always-SELL_100                   ~ +8pp
    always-SELL_100 given VIX >= 25   ~ +13pp

Dataset zero's headline was +26.5pp mean regret across five de-risking
decisions, read as a measurement of the engine. The state-and-action-matched
null for exactly that decision is around +13pp. **Roughly half of the headline
was the denominator.** The finding survives directionally; its size did not.

SO A REGRET NUMBER IS REPORTED AS A TRIPLE, NEVER AS A SCALAR
=============================================================
  1. **vs the ex-post best.** Kept, because it answers "how much was on the
     table". Labelled an UPPER BOUND everywhere it appears. Never negative,
     which is the tell that it is not an estimate of skill.
  2. **vs a fixed default (HOLD).** The honest, unbiased comparison: one
     pre-declared alternative chosen before seeing the outcome, so it has no
     selection bias and *can be negative* when the decision was good. A
     denominator that can exonerate is the only kind that can convict.
  3. **excess over the state-and-action-matched null.** The same denominator as
     (1) minus what a blameless decision-maker taking the SAME action in the
     SAME state scores under it. This is the one that answers "was this
     decision worse than nothing".

MATCHEDNESS IS THE POINT, AND IT IS EASY TO GET WRONG
=====================================================
The first measurement of this null was run on SPY at 5bps while dataset zero
ran on ^GSPC at 10bps. Those are three mismatches (universe, dividends, cost)
inside a comparison whose entire purpose is to be matched, and each one moves
the answer by more than a rounding error. `MatchedNull` therefore carries its
universe, cost, horizon and menu hash, and `excess_regret` REFUSES rather than
subtracting a null that was computed under different assumptions than the
episode it is being subtracted from.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from backend.services.research_gym import power as PW

#: Percentiles kept for every null cell. The threshold layer needs the tail,
#: not the mean: "worse than 90% of blameless decisions in this state" is a
#: statement a scalar mean cannot make.
KEPT_PERCENTILES = (10, 25, 50, 75, 90, 95)

#: Where a decision is called a failure. Replaces the round number 1.0pp, which
#: was never calibrated: P(a blameless always-HOLD scoring >1.0pp regret) was
#: measured at 0.931, so the old gate labelled 93% of neutral holds as failures.
#: Expressed as a percentile of the matched null so the bar moves with the state
#: -- a 3pp regret in a calm market and a 3pp regret in a panic are not the same
#: claim, and a fixed threshold treats them as if they were.
DEFAULT_FAILURE_PERCENTILE = 90


def menu_hash(names: Sequence[str]) -> str:
    """Identifies the menu a regret number was computed against.

    Regret vs the best of 17 and regret vs the best of 25 are different
    quantities. Without this, adding a policy silently changes every historical
    number in the direction of "the engine looks worse".
    """
    return hashlib.sha256("|".join(sorted(names)).encode()).hexdigest()[:12]


@dataclass(frozen=True)
class NullCell:
    """What a blameless decision-maker scores here, and how well we know it."""
    state_key: str
    policy: str
    mean_regret_pct: float
    percentiles: dict[int, float]
    power: PW.Power

    def percentile(self, p: int) -> float | None:
        return self.percentiles.get(int(p))

    def as_dict(self) -> dict:
        return {"state_key": self.state_key, "policy": self.policy,
                "mean_regret_pct": round(self.mean_regret_pct, 4),
                "percentiles": {str(k): round(v, 4)
                                for k, v in sorted(self.percentiles.items())},
                "power": self.power.as_dict()}


@dataclass
class MatchedNull:
    """A null regret table, keyed by (state, action), with its provenance.

    The provenance fields are not documentation. `excess_regret` compares them
    and refuses on a mismatch, because a null measured on a different universe
    or a different cost assumption is not this episode's null.
    """
    universe: str
    horizon_days: int
    cost_bps: float
    menu_hash: str
    sample_start: str
    sample_end: str
    cells: dict[tuple[str, str], NullCell] = field(default_factory=dict)
    #: Pooled over states, per policy. Used only when a state cell is missing,
    #: and the caller is told which one it got.
    pooled: dict[str, NullCell] = field(default_factory=dict)

    def cell(self, state_key: str, policy: str) -> tuple[NullCell | None, str]:
        """(cell, how_it_was_matched). Never silently substitutes."""
        c = self.cells.get((state_key, policy))
        if c is not None:
            return c, "state_and_action"
        p = self.pooled.get(policy)
        if p is not None:
            return p, "action_only_pooled_over_states"
        return None, "unmatched"

    def as_dict(self) -> dict:
        return {
            "universe": self.universe, "horizon_days": self.horizon_days,
            "cost_bps": self.cost_bps, "menu_hash": self.menu_hash,
            "sample_start": self.sample_start, "sample_end": self.sample_end,
            "cells": [c.as_dict() for c in self.cells.values()],
            "pooled": [c.as_dict() for c in self.pooled.values()],
        }

    def write(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.as_dict(), indent=2), encoding="utf-8")
        return path

    @classmethod
    def read(cls, path: Path) -> "MatchedNull":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        mn = cls(universe=raw["universe"], horizon_days=raw["horizon_days"],
                 cost_bps=raw["cost_bps"], menu_hash=raw["menu_hash"],
                 sample_start=raw["sample_start"], sample_end=raw["sample_end"])
        for section, dest in (("cells", mn.cells), ("pooled", mn.pooled)):
            for c in raw.get(section, []):
                p = c["power"]
                cell = NullCell(
                    state_key=c["state_key"], policy=c["policy"],
                    mean_regret_pct=c["mean_regret_pct"],
                    percentiles={int(k): v
                                 for k, v in c["percentiles"].items()},
                    power=PW.Power(
                        n_obs=p["n_obs"], horizon_days=p["horizon_days"],
                        n_episodes=p.get("n_episodes"),
                        n_effective=p["n_effective"],
                        mde_mean_pct=p.get("mde_mean_pct"),
                        mde_proportion=p.get("mde_proportion")))
                if section == "cells":
                    dest[(c["state_key"], c["policy"])] = cell
                else:
                    dest[c["policy"]] = cell
        return mn


class NullMismatch(ValueError):
    """The null on hand was not computed under this episode's assumptions."""


@dataclass(frozen=True)
class RegretTriple:
    """Three denominators, declared, never collapsed to one number."""
    #: Upper bound. Selection-biased by the size of the menu. Never negative.
    vs_ex_post_best: float
    #: Unbiased. Pre-declared alternative. NEGATIVE when the decision was good.
    vs_fixed_default: float | None
    fixed_default_policy: str
    #: vs_ex_post_best minus the matched null's mean. The skill-relevant one.
    excess_vs_matched_null: float | None
    null_cell: NullCell | None
    match_quality: str
    #: Percentile of the matched null the raw regret lands on, when computable.
    null_percentile_rank: float | None = None

    @property
    def is_interpretable(self) -> bool:
        """False when only the biased denominator is available."""
        return self.excess_vs_matched_null is not None

    def as_dict(self) -> dict:
        return {
            "vs_ex_post_best_pp": round(self.vs_ex_post_best, 4),
            "vs_ex_post_best_note":
                "UPPER BOUND -- max over the menu, never negative, not an "
                "estimate of skill",
            "vs_fixed_default_pp": (None if self.vs_fixed_default is None
                                    else round(self.vs_fixed_default, 4)),
            "fixed_default_policy": self.fixed_default_policy,
            "excess_vs_matched_null_pp":
                (None if self.excess_vs_matched_null is None
                 else round(self.excess_vs_matched_null, 4)),
            "null_percentile_rank": (None if self.null_percentile_rank is None
                                     else round(self.null_percentile_rank, 1)),
            "match_quality": self.match_quality,
            "null_cell": None if self.null_cell is None
            else self.null_cell.as_dict(),
        }


def _percentile_rank(cell: NullCell, value: float) -> float | None:
    """Roughly where `value` falls in the null, by linear interpolation.

    Deliberately coarse: the kept percentiles are a summary, and pretending to
    read a 97.3rd percentile off six knots would be false precision.
    """
    pts = sorted(cell.percentiles.items())
    if not pts:
        return None
    if value <= pts[0][1]:
        return float(pts[0][0])
    if value >= pts[-1][1]:
        return float(pts[-1][0])
    for (p0, v0), (p1, v1) in zip(pts, pts[1:]):
        if v0 <= value <= v1:
            if v1 == v0:
                return float(p1)
            return p0 + (p1 - p0) * (value - v0) / (v1 - v0)
    return None


def regret_triple(surface, *, state_key: str | None = None,
                  matched_null: MatchedNull | None = None,
                  fixed_default: str = "hold",
                  universe: str | None = None,
                  menu: Sequence[str] | None = None) -> RegretTriple:
    """All three denominators for one replayed decision.

    `surface` is a `ResponseSurface`; typed loosely to avoid a circular import
    with `counterfactual`, which needs this module.
    """
    taken, best = surface.taken, surface.best()
    if taken is None or best is None:
        raise ValueError("surface has no taken policy or no results")

    raw = best.net_return_pct - taken.net_return_pct
    dflt = surface.results.get(fixed_default)
    vs_default = (None if dflt is None
                  else dflt.net_return_pct - taken.net_return_pct)

    cell, quality, excess, rank = None, "no_null_supplied", None, None
    if matched_null is not None:
        if abs(matched_null.cost_bps - surface.cost_bps) > 1e-9:
            raise NullMismatch(
                f"null was measured at {matched_null.cost_bps}bps and this "
                f"surface at {surface.cost_bps}bps. Subtracting one from the "
                f"other compares two different experiments; recompute the null "
                f"at the surface's cost rather than accepting the difference")
        if matched_null.horizon_days != surface.horizon_days:
            raise NullMismatch(
                f"null horizon {matched_null.horizon_days}d vs surface "
                f"{surface.horizon_days}d -- regret scales with horizon")
        if universe and matched_null.universe != universe:
            raise NullMismatch(
                f"null universe {matched_null.universe!r} vs episode "
                f"{universe!r}")
        # THE MENU IS PART OF THE QUANTITY, AND THIS WAS THE GAP.
        #
        # `menu_hash` was introduced in this module precisely because regret
        # against the best of 17 and against the best of 25 are different
        # numbers — and then nothing checked it. Adding one policy would have
        # silently raised every historical regret figure, in the direction that
        # makes the engine look worse, with no error anywhere. Found by
        # auditing this file rather than by it failing.
        observed = menu_hash(menu if menu is not None else surface.results)
        if observed != matched_null.menu_hash:
            raise NullMismatch(
                f"the null was measured against menu {matched_null.menu_hash} "
                f"and this surface carries {observed}. Regret vs the best of "
                f"one menu is not comparable to regret vs the best of another "
                f"— recompute the null against the menu in use rather than "
                f"subtracting across them")
        cell, quality = matched_null.cell(state_key or "", surface.taken_policy)
        if cell is not None:
            excess = raw - cell.mean_regret_pct
            rank = _percentile_rank(cell, raw)
    return RegretTriple(
        vs_ex_post_best=raw, vs_fixed_default=vs_default,
        fixed_default_policy=fixed_default, excess_vs_matched_null=excess,
        null_cell=cell, match_quality=quality, null_percentile_rank=rank)


def build_matched_null(daily_returns: Sequence[float],
                       state_keys: Sequence[str], *,
                       universe: str,
                       horizon_days: int,
                       cost_bps: float,
                       sample_start: str,
                       sample_end: str,
                       policies: Sequence[str] | None = None,
                       episode_gap_days: int =
                       PW.DEFAULT_EPISODE_GAP_DAYS) -> MatchedNull:
    """Measure, for every (state, action), the regret a blameless actor scores.

    `daily_returns[i]` is the return of day i and `state_keys[i]` is the state
    OBSERVED AT THE DECISION, i.e. before day i's return is known. The forward
    window is `daily_returns[i : i + horizon_days]`, so a state read at the
    close of day i-1 is matched to the returns that follow it and nothing here
    peeks.

    Every day contributes. The windows overlap heavily on purpose -- that is
    what the market gives you -- and the resulting dependence is paid for
    honestly in `power`, not avoided by throwing away data.
    """
    import numpy as np

    from backend.services.research_gym.policies import POLICY_MENU, run_policy

    names = list(policies or POLICY_MENU.keys())
    rets = [float(x) for x in daily_returns]
    if len(state_keys) != len(rets):
        raise ValueError(
            f"{len(state_keys)} state keys for {len(rets)} returns -- these "
            f"must be aligned index-for-index or the null is matched to the "
            f"wrong states")

    samples: dict[tuple[str, str], list[float]] = {}
    positions: dict[tuple[str, str], list[int]] = {}
    last = len(rets) - horizon_days
    for i in range(max(0, last)):
        win = rets[i:i + horizon_days]
        res = {n: run_policy(n, win, cost_bps=cost_bps).net_return_pct
               for n in names}
        best = max(res.values())
        st = state_keys[i]
        for n, v in res.items():
            samples.setdefault((st, n), []).append(best - v)
            positions.setdefault((st, n), []).append(i)

    mn = MatchedNull(universe=universe, horizon_days=horizon_days,
                     cost_bps=cost_bps, menu_hash=menu_hash(names),
                     sample_start=sample_start, sample_end=sample_end)

    def _cell(state_key: str, policy: str, vals: list[float],
              pos: list[int]) -> NullCell:
        arr = np.asarray(vals, dtype=float)
        return NullCell(
            state_key=state_key, policy=policy,
            mean_regret_pct=float(arr.mean()),
            percentiles={p: float(np.percentile(arr, p))
                         for p in KEPT_PERCENTILES},
            power=PW.power_for(
                n_obs=len(arr), horizon_days=horizon_days,
                sd=float(arr.std(ddof=1)) if len(arr) > 1 else None,
                n_episodes=PW.count_episodes(pos, episode_gap_days)))

    for (st, n), vals in samples.items():
        mn.cells[(st, n)] = _cell(st, n, vals, positions[(st, n)])
    for n in names:
        vals = [v for (st, nn), lst in samples.items() if nn == n for v in lst]
        pos = [p for (st, nn), lst in positions.items() if nn == n for p in lst]
        if vals:
            mn.pooled[n] = _cell("ALL_STATES", n, vals, sorted(set(pos)))
    return mn


def failure_threshold_pct(cell: NullCell | None, *,
                          percentile: int = DEFAULT_FAILURE_PERCENTILE,
                          fallback_pct: float = 1.0) -> tuple[float, str]:
    """Where regret stops being what a blameless decision looks like.

    Returns `(threshold_pp, provenance)`. The provenance string is returned
    rather than logged because it ends up in the classification detail: a
    reader must be able to see whether a decision was convicted against a
    measured null or against a round number nobody calibrated.
    """
    if cell is None:
        return fallback_pct, (
            f"UNCALIBRATED fixed threshold {fallback_pct:.1f}pp -- no matched "
            f"null available for this state and action, so this gate has not "
            f"been shown to exceed what a blameless decision scores")
    v = cell.percentile(percentile)
    if v is None:
        return fallback_pct, "UNCALIBRATED fixed threshold (percentile missing)"
    return float(v), (
        f"p{percentile} of the matched null for ({cell.state_key}, "
        f"{cell.policy}): a blameless decision taking this action in this "
        f"state scores below {v:.2f}pp {percentile}% of the time "
        f"(n_effective {cell.power.n_effective:.1f})")
