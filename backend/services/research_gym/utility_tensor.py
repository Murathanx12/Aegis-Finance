"""UTILITY_TENSOR — state x action x horizon x OBJECTIVE, and where it flips.

WHAT THIS ADDS TO `REGRET_TENSOR`, AND WHAT IT DOES NOT TAKE AWAY
==================================================================
`REGRET_TENSOR` measures `mean_edge_vs_default` — the action minus a
pre-declared HOLD — and that number is a raw-return result against a declared
default. It is not an artefact of the best-of-17 ranking and it is not being
restated here. What it is, is **incomplete relative to the objective the
programme actually holds**: terminal wealth under a declared utility.

So this is another dimension on the same measurement, not a replacement. Every
cell carries BOTH:

  * `raw_edge_pp`      action minus default in net return — the existing
                       quantity, recomputed identically so the two tensors can
                       be checked against each other rather than trusted.
  * `utility_edge`     action minus default under a NAMED objective, in that
                       objective's own units.

THE OUTPUT THAT MATTERS IS NOT A LEADERBOARD
=============================================
It is the **UTILITY-FLIP ATLAS**: the (state, horizon) cells where the
preferred action CHANGES when the objective changes. Another global ranking
would be one more table to scan for the largest number. A flip is a decision
that depends on who is asking — which is precisely the thing "one brain, four
personalities" has to know, and which no amount of raw-return work can produce.

A flip is only reported as MATERIAL when the gap between the two contenders
clears the MDE of the difference. §19 does not stop applying because the
quantity became more interesting: an ordering that reverses on a gap smaller
than the cell could detect is a coin landing differently, not a preference
being revealed.

BREAK-EVEN GAMMA IS REPORTED PER (state, horizon)
==================================================
`gamma_star` says *at what risk aversion* the default stops being preferred to
the best alternative. That is more useful than "selling was wrong" and it is
computable in cells where neither edge clears its own MDE — it is a statement
about preferences given the sample, not a claim that the sample resolved
anything. Cells report it alongside their power so the two are never read apart.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from backend.services.research_gym import power as PW
from backend.services.research_gym import utility as U

#: The objectives a tensor is built over unless told otherwise. `total_return`
#: is always first and is the reference the flips are measured against, because
#: it is the objective every previous ranked comparison was computed under.
DEFAULT_OBJECTIVES = ("total_return", "sortino",
                      "drawdown_penalised_lambda1",
                      "drawdown_penalised_lambda0.25",
                      "expected_log_growth", "log_growth_with_ruin_constraint",
                      "aggressive_growth_lambda0.15")

REFERENCE_OBJECTIVE = "total_return"

#: Policies that hold NO exposure for the whole window. They earn nothing and
#: risk nothing, so any objective that trades return against risk at a steep
#: enough rate prefers them everywhere — see `degenerate_objectives`.
CASH_POLICIES = frozenset({"sell_100"})

#: Fraction of (state, horizon) cells an objective may prefer cash in before it
#: is reported as DEGENERATE rather than as a preference.
DEGENERACY_THRESHOLD = 0.5


@dataclass(frozen=True)
class UtilityCell:
    state_key: str
    action: str
    horizon_days: int
    objective: str
    #: The action's own utility level, averaged over episodes.
    mean_utility: float | None
    #: Action minus the pre-declared default, in the objective's units.
    utility_edge: float | None
    sd_utility_edge: float | None
    #: The SAME cell's raw-return edge, recomputed here rather than joined in.
    raw_edge_pp: float
    power: PW.Power
    units: str
    n_ruin_action: int = 0
    n_ruin_default: int = 0

    @property
    def edge_is_detectable(self) -> bool | None:
        if self.power.mde_mean_pct is None or self.utility_edge is None:
            return None
        return abs(self.utility_edge) >= self.power.mde_mean_pct

    @property
    def sign_agrees_with_raw(self) -> bool | None:
        """Does the utility edge point the same way as the raw-return edge?

        A disagreement is the cheapest possible flag that the objective is
        doing work: the action earns more and is worth less, or the reverse.
        """
        if self.utility_edge is None:
            return None
        if abs(self.utility_edge) < 1e-12 or abs(self.raw_edge_pp) < 1e-12:
            return None
        return (self.utility_edge > 0) == (self.raw_edge_pp > 0)

    def as_dict(self) -> dict:
        def _r(x, n=4):
            return None if x is None else round(float(x), n)
        return {
            "state_key": self.state_key, "action": self.action,
            "horizon_days": self.horizon_days, "objective": self.objective,
            "units": self.units,
            "mean_utility": _r(self.mean_utility, 6),
            "utility_edge": _r(self.utility_edge, 6),
            "sd_utility_edge": _r(self.sd_utility_edge, 6),
            "raw_edge_pp": _r(self.raw_edge_pp),
            "power": self.power.as_dict(),
            "edge_is_detectable": self.edge_is_detectable,
            "sign_agrees_with_raw": self.sign_agrees_with_raw,
            "n_ruin_action": self.n_ruin_action,
            "n_ruin_default": self.n_ruin_default,
        }


@dataclass(frozen=True)
class Flip:
    """One (state, horizon) where the preferred action changed with the aim."""
    state_key: str
    horizon_days: int
    objective: str
    reference_objective: str
    best_under_reference: str
    best_under_objective: str
    #: How much the reference's winner loses by, under the new objective.
    gap_under_objective: float
    mde_of_gap: float | None
    material: bool | None
    n_effective: float
    gamma_star: float | None = None

    def as_dict(self) -> dict:
        def _r(x, n=5):
            return None if x is None else round(float(x), n)
        return {
            "state_key": self.state_key, "horizon_days": self.horizon_days,
            "objective": self.objective,
            "reference_objective": self.reference_objective,
            "best_under_reference": self.best_under_reference,
            "best_under_objective": self.best_under_objective,
            "gap_under_objective": _r(self.gap_under_objective),
            "mde_of_gap": _r(self.mde_of_gap),
            "material": self.material,
            "n_effective": _r(self.n_effective, 3),
            "gamma_star": _r(self.gamma_star, 3),
        }


@dataclass
class UtilityTensor:
    universe: list[str]
    default_policy: str
    objectives: list[str]
    cost_bps: float
    horizons: list[int]
    sample_start: str
    sample_end: str
    stride_days: int
    cells: dict[tuple[str, str, int, str], UtilityCell] = field(
        default_factory=dict)
    #: (state, horizon) -> gamma at which the default and the raw-return winner
    #: are exactly indifferent. None where one dominates at every gamma.
    gamma_star: dict[tuple[str, int], float | None] = field(default_factory=dict)
    #: Bootstrap interval for the same quantity. A gamma* without one invites
    #: exactly the reading SS19 exists to prevent: 0.35 and 2.86 look like a
    #: large difference until both intervals turn out to span the plausible
    #: range of risk aversions.
    gamma_star_ci: dict[tuple[str, int], dict] = field(default_factory=dict)

    def cell(self, state_key: str, action: str, horizon_days: int,
             objective: str) -> UtilityCell | None:
        return self.cells.get((state_key, action, horizon_days, objective))

    def actions_in(self, state_key: str, horizon_days: int,
                   objective: str) -> list[UtilityCell]:
        return [c for (s, _a, h, o), c in self.cells.items()
                if s == state_key and h == horizon_days and o == objective]

    def best_action(self, state_key: str, horizon_days: int,
                    objective: str) -> UtilityCell | None:
        cs = [c for c in self.actions_in(state_key, horizon_days, objective)
              if c.utility_edge is not None]
        return max(cs, key=lambda c: c.utility_edge) if cs else None

    def flips(self, *, reference: str = REFERENCE_OBJECTIVE) -> list[Flip]:
        """THE UTILITY-FLIP ATLAS.

        For every (state, horizon), compare the action preferred under the
        reference objective with the one preferred under each other objective.
        A difference is reported; whether it is MATERIAL is decided by the MDE
        of the gap, not by its size.
        """
        out: list[Flip] = []
        keys = sorted({(s, h) for (s, _a, h, _o) in self.cells})
        for state_key, H in keys:
            ref = self.best_action(state_key, H, reference)
            if ref is None:
                continue
            for obj in self.objectives:
                if obj == reference:
                    continue
                alt = self.best_action(state_key, H, obj)
                if alt is None or alt.action == ref.action:
                    continue
                ref_under_alt = self.cell(state_key, ref.action, H, obj)
                gap = (alt.utility_edge -
                       (ref_under_alt.utility_edge
                        if ref_under_alt and ref_under_alt.utility_edge
                        is not None else 0.0))
                # §18: the quantity is a DIFFERENCE, so its SE is the SE of a
                # difference — not either arm's own.
                se_a = _se(alt)
                se_b = _se(ref_under_alt)
                mde = None
                if se_a is not None and se_b is not None:
                    mde = PW.mde_from_se((se_a ** 2 + se_b ** 2) ** 0.5)
                out.append(Flip(
                    state_key=state_key, horizon_days=H, objective=obj,
                    reference_objective=reference,
                    best_under_reference=ref.action,
                    best_under_objective=alt.action,
                    gap_under_objective=gap, mde_of_gap=mde,
                    material=(None if mde is None else abs(gap) >= mde),
                    n_effective=min(alt.power.n_effective,
                                    (ref_under_alt.power.n_effective
                                     if ref_under_alt else alt.power.n_effective)),
                    gamma_star=self.gamma_star.get((state_key, H))))
        return out

    def degenerate_objectives(self) -> dict[str, dict]:
        """Which objectives prefer CASH almost everywhere — a specification
        error wearing the clothes of a preference.

        FOUND ON THE FIRST REAL RUN, 2026-08-15. The atlas reported thirteen
        MATERIAL flips. Every one was `drawdown_penalised` at lambda=1.0, and
        every one was `buy_50 -> sell_100`. A zero-exposure policy has zero
        return AND zero drawdown, so it scores ~0 while any long policy whose
        drawdown exceeds its return scores below zero. The optimum is cash in
        nearly every state for a reason that has nothing to do with markets.

        Reported rather than removed. §37 says check the kills as hard as the
        passes; the same applies to a new instrument's FIRST POSITIVE RESULT,
        which is the one that looks like it working.
        """
        out: dict[str, dict] = {}
        keys = sorted({(s, h) for (s, _a, h, _o) in self.cells})
        for obj in self.objectives:
            best = [self.best_action(s, h, obj) for s, h in keys]
            best = [b for b in best if b is not None]
            if not best:
                continue
            n_cash = sum(1 for b in best if b.action in CASH_POLICIES)
            frac = n_cash / len(best)
            out[obj] = {
                "n_cells": len(best), "n_prefers_cash": n_cash,
                "frac_prefers_cash": round(frac, 4),
                "degenerate": frac >= DEGENERACY_THRESHOLD,
            }
        return out

    def as_dict(self) -> dict:
        return {
            "universe": self.universe,
            "default_policy": self.default_policy,
            "objectives": self.objectives,
            "reference_objective": REFERENCE_OBJECTIVE,
            "cost_bps": self.cost_bps,
            "horizons": self.horizons,
            "sample_start": self.sample_start,
            "sample_end": self.sample_end,
            "stride_days": self.stride_days,
            "n_cells": len(self.cells),
            "cells": [c.as_dict() for c in self.cells.values()],
            "flip_atlas": [f.as_dict() for f in self.flips()],
            # Read this BEFORE the atlas. A flip produced by a degenerate
            # objective is an artefact of the objective, not a finding.
            "degenerate_objectives": self.degenerate_objectives(),
            "gamma_star": {f"{s}|{h}": v
                           for (s, h), v in sorted(self.gamma_star.items())},
            "gamma_star_interval": {f"{s}|{h}": v for (s, h), v
                                    in sorted(self.gamma_star_ci.items())},
        }


def _se(c: UtilityCell | None) -> float | None:
    if c is None or c.sd_utility_edge is None:
        return None
    n = c.power.n_effective
    if not n or n < 2.0:
        return None
    return c.sd_utility_edge / (n ** 0.5)


def build_utility_tensor(
        series_by_security: dict[str, tuple[Sequence[float], Sequence[str]]],
        *, horizons: Sequence[int], default_policy: str = "hold",
        policies: Sequence[str] | None = None,
        objectives: Sequence[str] = DEFAULT_OBJECTIVES,
        cost_bps: float = 10.0, stride_days: int = 5,
        sample_start: str = "", sample_end: str = "",
        progress=None) -> UtilityTensor:
    """Same episodes as `REGRET_TENSOR`, scored under several declared aims.

    The episode construction is deliberately identical — same windows, same
    stride, same episode-clustering correction — so a disagreement between the
    two tensors is a disagreement about the OBJECTIVE and cannot be a
    disagreement about the sample.
    """
    import numpy as np

    from backend.services.research_gym.policies import POLICY_MENU, run_policy

    names = list(policies or POLICY_MENU.keys())
    if default_policy not in names:
        raise ValueError(f"default policy {default_policy!r} is not in the menu")
    objs = [U.get_objective(o) for o in objectives]

    # (state, action, horizon, objective) -> per-episode edge contributions
    util_edges: dict[tuple, list[float]] = {}
    util_levels: dict[tuple, list[float]] = {}
    raw_edges: dict[tuple, list[float]] = {}
    positions: dict[tuple, list[int]] = {}
    ruins: dict[tuple, int] = {}
    # (state, horizon) -> terminal wealths, for gamma*
    wealth_by_action: dict[tuple, dict[str, list[float]]] = {}

    for tkr, (rets, states) in series_by_security.items():
        rets = [float(x) for x in rets]
        if len(states) != len(rets):
            raise ValueError(
                f"{tkr}: {len(states)} state keys for {len(rets)} returns — "
                f"these must be aligned index-for-index or every cell is "
                f"matched to the wrong state")
        for H in horizons:
            last = len(rets) - H
            for i in range(0, max(0, last), stride_days):
                win = rets[i:i + H]
                res = {n: run_policy(n, win, cost_bps=cost_bps) for n in names}
                st = states[i]
                stats = {n: U.path_stats(r.wealth_path)
                         for n, r in res.items()}
                base_stats = stats[default_policy]
                base_raw = res[default_policy].net_return_pct
                if base_stats is None:
                    continue
                for n in names:
                    s = stats[n]
                    if s is None:
                        continue
                    wealth_by_action.setdefault((st, H), {}).setdefault(
                        n, []).append(s.terminal_wealth)
                    if s.ruin:
                        ruins[(st, n, H)] = ruins.get((st, n, H), 0) + 1
                    for obj in objs:
                        key = (st, n, H, obj.name)
                        cu = U.contribution(obj, s)
                        cb = U.contribution(obj, base_stats)
                        if cu is not None and cb is not None:
                            util_edges.setdefault(key, []).append(cu - cb)
                            util_levels.setdefault(key, []).append(cu)
                        raw_edges.setdefault(key, []).append(
                            res[n].net_return_pct - base_raw)
                        positions.setdefault(key, []).append(i)
            if progress:
                progress(tkr, H)

    t = UtilityTensor(
        universe=sorted(series_by_security), default_policy=default_policy,
        objectives=[o.name for o in objs], cost_bps=cost_bps,
        horizons=list(horizons), sample_start=sample_start,
        sample_end=sample_end, stride_days=stride_days)

    units = {o.name: o.units for o in objs}
    for key, raw in raw_edges.items():
        state_key, action, H, obj_name = key
        ue = util_edges.get(key, [])
        arr = np.asarray(ue, dtype=float) if ue else None
        sd = (float(arr.std(ddof=1)) if arr is not None and len(arr) > 1
              else None)
        n_eps = PW.count_episodes(positions[key],
                                  gap_days=PW.DEFAULT_EPISODE_GAP_DAYS)
        t.cells[key] = UtilityCell(
            state_key=state_key, action=action, horizon_days=H,
            objective=obj_name,
            mean_utility=(float(np.mean(util_levels[key]))
                          if util_levels.get(key) else None),
            utility_edge=(float(arr.mean()) if arr is not None else None),
            sd_utility_edge=sd,
            raw_edge_pp=float(np.mean(raw)),
            power=PW.power_for(
                n_obs=len(raw),
                horizon_days=max(round(H / max(stride_days, 1)), 1),
                sd=sd, n_episodes=n_eps),
            units=units[obj_name],
            n_ruin_action=ruins.get((state_key, action, H), 0),
            n_ruin_default=ruins.get((state_key, default_policy, H), 0))

    # gamma*: the default against the RAW-RETURN winner, per (state, horizon).
    # That is the pair the question is actually about — "the action that looked
    # best on return, is it still preferred once risk aversion is declared?"
    for (st, H), by_action in wealth_by_action.items():
        base = by_action.get(default_policy)
        if not base:
            t.gamma_star[(st, H)] = None
            continue
        winner, best_mean = None, None
        for n, ws in by_action.items():
            if n == default_policy or len(ws) != len(base):
                continue
            m = sum(ws) / len(ws)
            if best_mean is None or m > best_mean:
                winner, best_mean = n, m
        if winner:
            t.gamma_star[(st, H)] = U.break_even_gamma(by_action[winner], base)
            # Block length = the overlap factor of these windows. Sampling
            # every `stride_days` from an H-day horizon makes consecutive
            # episodes share H - stride days, and an i.i.d. resample of them
            # returns an interval far tighter than the data supports.
            t.gamma_star_ci[(st, H)] = dict(
                U.bootstrap_gamma_star(
                    by_action[winner], base,
                    block=max(1, round(H / max(stride_days, 1)))),
                winner=winner)
        else:
            t.gamma_star[(st, H)] = None
            t.gamma_star_ci[(st, H)] = {}
    return t
