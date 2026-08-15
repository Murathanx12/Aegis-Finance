"""REGRET_TENSOR — state x action x horizon, and what each cell is worth.

THE QUESTION THIS ANSWERS
=========================
Not *"what parameter set maximised 2010-2025"*. That question has an answer for
every dataset ever assembled and the answer does not survive contact with the
next one.

The question is **"which actions are bad in which states, and over what
horizon"** — and it is a different shape of question, because it has an answer
per cell rather than a single winner, it has a sample size per cell, and most
cells turn out to say nothing, which is information a leaderboard cannot
express.

THREE NUMBERS PER CELL, FOR THE SAME REASON AS G1
=================================================
Each cell carries:

  * `mean_net_return_pct`   what the action itself returned. Descriptive.
  * `mean_regret_vs_best`   the ex-post-best denominator — kept because it IS
                            the matched null other work subtracts, and labelled
                            an upper bound everywhere it appears.
  * `mean_edge_vs_default`  the action minus a PRE-DECLARED default (hold).
                            **This is the one that answers the question.** It
                            can be negative, which is the property that makes
                            it a measurement rather than a ranking artefact.

`mean_edge_vs_default` is what a policy learner should be fed. Feeding it
regret-against-the-best would teach it that every action is bad in proportion
to how many alternatives exist in that state.

AND EVERY CELL CARRIES ITS OWN SAMPLE SIZE
==========================================
`n_obs` is decisions; `n_effective` shrinks it for horizon overlap and episode
clustering; `mde_pp` says what the cell could have detected. A tensor without
per-cell MDEs invites exactly the reading it should prevent — scanning for the
largest number, which in a table of thousands of cells is a maximum over
thousands of noisy draws. That is G1 again, one dimension up.

WHAT IS NOT IN THE MENU, STATED RATHER THAN OMITTED
====================================================
`REPLACE_WITH_MARKET` and `REPLACE_WITH_SECTOR` are declared in the order and
are NOT implemented here: both need a second asset's return path per episode,
which is a data-plumbing change rather than a policy. They are absent, and this
paragraph is the difference between absent and forgotten.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from backend.services.research_gym import power as PW
from backend.services.research_gym import regret as RG

#: Declared in the order. 1 day is included even though several policies are
#: degenerate there (a 21-day re-entry inside a 1-day window never re-enters) —
#: the degeneracy is visible in the cell rather than hidden by dropping it.
DEFAULT_HORIZONS = (1, 5, 20, 60, 120, 252)

#: The pre-declared comparison. Chosen before any cell was computed; changing it
#: afterwards would be choosing the denominator that flatters.
DEFAULT_POLICY = "hold"


@dataclass(frozen=True)
class TensorCell:
    state_key: str
    action: str
    horizon_days: int
    mean_net_return_pct: float
    mean_regret_vs_best_pp: float
    mean_edge_vs_default_pp: float
    sd_edge_pp: float | None
    percentiles_edge: dict[int, float]
    power: PW.Power
    securities: tuple[str, ...] = ()

    @property
    def edge_is_detectable(self) -> bool | None:
        if self.power.mde_mean_pct is None:
            return None
        return abs(self.mean_edge_vs_default_pp) >= self.power.mde_mean_pct

    def as_dict(self) -> dict:
        return {
            "state_key": self.state_key, "action": self.action,
            "horizon_days": self.horizon_days,
            "mean_net_return_pct": round(self.mean_net_return_pct, 4),
            "mean_regret_vs_best_pp": round(self.mean_regret_vs_best_pp, 4),
            "mean_edge_vs_default_pp": round(self.mean_edge_vs_default_pp, 4),
            "sd_edge_pp": (None if self.sd_edge_pp is None
                           else round(self.sd_edge_pp, 4)),
            "percentiles_edge": {str(k): round(v, 4) for k, v
                                 in sorted(self.percentiles_edge.items())},
            "power": self.power.as_dict(),
            "edge_is_detectable": self.edge_is_detectable,
            "securities": list(self.securities),
        }


@dataclass
class RegretTensor:
    """The whole surface, with its provenance. Never a leaderboard."""
    universe: list[str]
    default_policy: str
    cost_bps: float
    menu_hash: str
    horizons: list[int]
    sample_start: str
    sample_end: str
    stride_days: int
    cells: dict[tuple[str, str, int], TensorCell] = field(default_factory=dict)

    def cell(self, state_key: str, action: str,
             horizon_days: int) -> TensorCell | None:
        return self.cells.get((state_key, action, horizon_days))

    def worst_actions(self, state_key: str, horizon_days: int,
                      *, detectable_only: bool = True) -> list[TensorCell]:
        """Which actions are bad in this state — the question, asked directly.

        `detectable_only` defaults True on purpose. Ranking undetectable cells
        produces a list ordered by noise, and a list ordered by noise looks
        exactly like a finding.
        """
        out = [c for (s, _, h), c in self.cells.items()
               if s == state_key and h == horizon_days
               and (not detectable_only or c.edge_is_detectable)]
        return sorted(out, key=lambda c: c.mean_edge_vs_default_pp)

    def as_dict(self) -> dict:
        return {"universe": self.universe, "default_policy": self.default_policy,
                "cost_bps": self.cost_bps, "menu_hash": self.menu_hash,
                "horizons": self.horizons, "sample_start": self.sample_start,
                "sample_end": self.sample_end, "stride_days": self.stride_days,
                "n_cells": len(self.cells),
                "note": ("RESEARCH-GYM-1 output. Cells are hypotheses. "
                         "`mean_regret_vs_best_pp` is an UPPER BOUND with a "
                         "large positive null; `mean_edge_vs_default_pp` is "
                         "the number that answers 'which actions are bad "
                         "where'."),
                "citable": False,
                "cells": [c.as_dict() for c in self.cells.values()]}

    def write(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.as_dict(), indent=1), encoding="utf-8")
        return path

    @classmethod
    def read(cls, path: Path) -> "RegretTensor":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        t = cls(universe=raw["universe"], default_policy=raw["default_policy"],
                cost_bps=raw["cost_bps"], menu_hash=raw["menu_hash"],
                horizons=raw["horizons"], sample_start=raw["sample_start"],
                sample_end=raw["sample_end"],
                stride_days=raw.get("stride_days", 1))
        for c in raw["cells"]:
            p = c["power"]
            t.cells[(c["state_key"], c["action"], c["horizon_days"])] = \
                TensorCell(
                    state_key=c["state_key"], action=c["action"],
                    horizon_days=c["horizon_days"],
                    mean_net_return_pct=c["mean_net_return_pct"],
                    mean_regret_vs_best_pp=c["mean_regret_vs_best_pp"],
                    mean_edge_vs_default_pp=c["mean_edge_vs_default_pp"],
                    sd_edge_pp=c.get("sd_edge_pp"),
                    percentiles_edge={int(k): v for k, v
                                      in c["percentiles_edge"].items()},
                    power=PW.Power(
                        n_obs=p["n_obs"], horizon_days=p["horizon_days"],
                        n_episodes=p.get("n_episodes"),
                        n_effective=p["n_effective"],
                        mde_mean_pct=p.get("mde_mean_pct"),
                        mde_proportion=p.get("mde_proportion")),
                    securities=tuple(c.get("securities") or ()))
        return t


def build_regret_tensor(series_by_security: dict[str, tuple],
                        *, horizons: Sequence[int] = DEFAULT_HORIZONS,
                        cost_bps: float = 10.0,
                        default_policy: str = DEFAULT_POLICY,
                        stride_days: int = 5,
                        policies: Sequence[str] | None = None,
                        sample_start: str = "", sample_end: str = "",
                        progress=None) -> RegretTensor:
    """Every (state, action, horizon) cell over a corpus of securities.

    `series_by_security` maps a ticker to `(daily_returns, state_keys)`, aligned
    index-for-index, where `state_keys[i]` was OBSERVABLE BEFORE `returns[i]`.
    The caller supplies the state so the tensor is not welded to one state
    definition — VIX buckets today, transition states later.

    `stride_days` samples decisions rather than taking every day. Overlap is
    still paid for in `power`; the stride is here because a 252-day horizon
    sampled daily is 252 nearly identical rows per genuinely new observation,
    and computing all of them buys nothing but time.
    """
    import numpy as np

    from backend.services.research_gym.policies import POLICY_MENU, run_policy

    names = list(policies or POLICY_MENU.keys())
    if default_policy not in names:
        raise ValueError(f"default policy {default_policy!r} is not in the menu")

    # (state, action, horizon) -> lists
    nets: dict[tuple, list[float]] = {}
    regrets: dict[tuple, list[float]] = {}
    edges: dict[tuple, list[float]] = {}
    positions: dict[tuple, list[int]] = {}
    secs: dict[tuple, set] = {}

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
                res = {n: run_policy(n, win, cost_bps=cost_bps).net_return_pct
                       for n in names}
                best = max(res.values())
                base = res[default_policy]
                st = states[i]
                for n, v in res.items():
                    key = (st, n, H)
                    nets.setdefault(key, []).append(v)
                    regrets.setdefault(key, []).append(best - v)
                    edges.setdefault(key, []).append(v - base)
                    positions.setdefault(key, []).append(i)
                    secs.setdefault(key, set()).add(tkr)
            if progress:
                progress(tkr, H)

    t = RegretTensor(
        universe=sorted(series_by_security), default_policy=default_policy,
        cost_bps=cost_bps, menu_hash=RG.menu_hash(names),
        horizons=list(horizons), sample_start=sample_start,
        sample_end=sample_end, stride_days=stride_days)

    for key, ed in edges.items():
        state_key, action, H = key
        arr = np.asarray(ed, dtype=float)
        sd = float(arr.std(ddof=1)) if len(arr) > 1 else None
        # Positions are strided indices into one security's series; episodes are
        # counted on them so a state that persists for a quarter is not read as
        # a quarter's worth of independent draws.
        n_eps = PW.count_episodes(positions[key],
                                  gap_days=max(PW.DEFAULT_EPISODE_GAP_DAYS,
                                               H) // max(stride_days, 1))
        t.cells[key] = TensorCell(
            state_key=state_key, action=action, horizon_days=H,
            mean_net_return_pct=float(np.mean(nets[key])),
            mean_regret_vs_best_pp=float(np.mean(regrets[key])),
            mean_edge_vs_default_pp=float(arr.mean()),
            sd_edge_pp=sd,
            percentiles_edge={p: float(np.percentile(arr, p))
                              for p in RG.KEPT_PERCENTILES},
            power=PW.power_for(n_obs=len(arr), horizon_days=max(H // max(stride_days, 1), 1),
                               sd=sd, n_episodes=n_eps),
            securities=tuple(sorted(secs[key])))
    return t
