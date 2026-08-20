"""CONVEXITY-CONDITIONAL-1 — is there a STATE in which trimming is right?

CONVEXITY-PRESERVATION-1 resolved that mechanically trimming or exiting a
+40% winner destroys subsequent 60-day wealth (−1.29% / −2.58% / −5.16%
for trim-25 / trim-50 / full exit, Holm-surviving). That is an AVERAGE
over the episode population, and the review's response to it was exactly
right:

    the summary "selling your winners early costs money" is too broad;
    the next experiment should be about CONDITIONAL selling.

This is that experiment, and it needs no new simulation: the episode
library already carries per-episode terminal wealth under six management
arms plus the PIT feature state at the crossing date.

THE QUESTION. For each episode, delta = tw(arm) - tw(hold). The average
delta is negative and that is settled. Is there an observable state AT
CROSSING TIME in which delta turns positive — i.e. a condition under
which trimming is the right call rather than a costly reflex?

WHY THIS IS A SCREEN AND CAN NEVER BE A CONFIRMATION. The convexity trial
already RESOLVED on this exact episode population. Every number here is
computed on spent data, so nothing found can confirm anything; it can
only generate a candidate for a trial on the frozen CRSP replication
population, which has not been read.

AND THE SEARCH IS THE DANGER. Slicing a population many ways until
trimming wins somewhere is how a spurious rule is born. Three guards,
declared before running:

  1. The state variables and their cut points are FIXED below, before any
     delta is computed. No cut is chosen after seeing an outcome.
  2. Every cell is tested against a NULL built by permuting the state
     labels across episodes, preserving the marginal distribution of
     delta and destroying only its relationship to state.
  3. Holm across the declared cell count. A cell that wins only under
     BH-FDR is reported as a lead, never as a survivor.

DECLARED EXPECTATION: most cells stay negative. The interesting outcome
is whether ANY state flips the sign with enough episodes behind it to
matter — and if none does, "do not trim winners" strengthens from an
average into a statement that survived a search for exceptions.

    python -m scripts.convexity_conditional_1

SCREEN on a spent population.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config                        # noqa: E402

CONV = _config.OPTIMUS_LEDGER_DIR / "convexity"
OUT = CONV
SEED = 20260820
N_NULL = 2000

#: FROZEN before any delta is computed. Terciles are computed WITHIN the
#: episode population so the cut points do not depend on an outcome.
STATES = {
    "momentum_21d": ("pit_mom_21", "tercile"),
    "momentum_63d": ("pit_mom_63", "tercile"),
    "momentum_12_1": ("pit_mom_12_1", "tercile"),
    "volatility_21d": ("pit_vol_21", "tercile"),
    "volatility_63d": ("pit_vol_63", "tercile"),
    "drawdown_252d": ("pit_drawdown_252", "tercile"),
    "speed_to_crossing": ("days_to_crossing", "tercile"),
    "gain_at_crossing": ("gain_at_crossing", "tercile"),
}
ARMS = ("trim_25", "trim_50", "exit_full", "trail_stop_20")
MIN_EPISODES = 200


def main() -> int:
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=0.40)
    a = ap.parse_args()

    df = pd.read_parquet(CONV / "episodes_v2.parquet")
    df = df[np.isclose(df["threshold"], a.threshold)]
    print(f"episodes at +{a.threshold:.0%}: {len(df):,}")
    if len(df) < 500:
        raise SystemExit("too few episodes")

    rng = np.random.default_rng(SEED)
    rows = []
    for arm in ARMS:
        col, hold = f"tw_{arm}", "tw_hold"
        if col not in df.columns:
            continue
        sub = df[[col, hold] + [c for c, _ in STATES.values()]].dropna()
        delta = (sub[col] - sub[hold]).to_numpy(float)
        overall = float(delta.mean())
        for state, (feat, _) in STATES.items():
            v = sub[feat].to_numpy(float)
            try:
                lab = pd.Series(pd.qcut(v, 3,
                                        labels=["low", "mid", "high"]))
            except Exception:                                  # noqa: BLE001
                continue
            for cell in ("low", "mid", "high"):
                m = (lab == cell).to_numpy()
                if m.sum() < MIN_EPISODES:
                    continue
                obs = float(delta[m].mean())
                # NULL: permute the state labels, keeping delta's marginal
                # distribution and destroying only its link to state
                null = np.empty(N_NULL)
                idx = np.arange(len(delta))
                k = int(m.sum())
                for i in range(N_NULL):
                    null[i] = delta[rng.choice(idx, size=k,
                                               replace=False)].mean()
                p_hi = float((null >= obs).mean())
                p_lo = float((null <= obs).mean())
                rows.append({
                    "arm": arm, "state": state, "cell": cell,
                    "n": int(m.sum()),
                    "mean_delta_vs_hold": round(obs, 5),
                    "overall_delta": round(overall, 5),
                    "beats_hold": bool(obs > 0),
                    "p_better_than_null": round(p_hi, 5),
                    "p_worse_than_null": round(p_lo, 5),
                    "null_mean": round(float(null.mean()), 5)})
        print(f"  {arm:14s} overall delta {overall:+.4f}")

    res_df = pd.DataFrame(rows)
    m_declared = len(res_df)
    # Holm on the two-sided p, across every declared cell
    res_df["p_two_sided"] = 2 * np.minimum(res_df["p_better_than_null"],
                                           res_df["p_worse_than_null"])
    res_df["p_two_sided"] = res_df["p_two_sided"].clip(0, 1)
    order = res_df["p_two_sided"].to_numpy().argsort()
    holm = np.zeros(m_declared, dtype=bool)
    for rank, i in enumerate(order):
        if res_df["p_two_sided"].to_numpy()[i] <= 0.05 / (m_declared - rank):
            holm[i] = True
        else:
            break
    res_df["holm_survives"] = holm

    positive = res_df[res_df["beats_hold"]]
    pos_holm = res_df[res_df["beats_hold"] & res_df["holm_survives"]]

    if len(pos_holm):
        verdict = (f"CONDITIONAL EXCEPTION FOUND — {len(pos_holm)} cell(s) "
                   f"where trimming beats holding and survives Holm at "
                   f"m={m_declared}; candidate for the frozen CRSP "
                   f"replication, NOT a result on this spent population")
    elif len(positive):
        verdict = (f"NO SURVIVING EXCEPTION — {len(positive)} of "
                   f"{m_declared} cells lean positive but none survives "
                   f"Holm at m={m_declared}. 'Do not trim winners' "
                   f"strengthens: it survived a declared search for "
                   f"exceptions across {len(STATES)} state variables")
    else:
        verdict = (f"NO EXCEPTION AT ALL — every one of {m_declared} "
                   f"declared cells is negative. The rule is unconditional "
                   f"on every state tested")

    res = {"trial": "CONVEXITY-CONDITIONAL-1", "mode": "SCREEN",
           "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "threshold": a.threshold,
           "population": "CONVEXITY-EPISODES-1 v2, ALREADY SPENT by "
                         "CONVEXITY-PRESERVATION-1 — nothing here can "
                         "confirm; survivors are candidates for the "
                         "frozen CRSP replication population",
           "n_episodes": int(len(df)),
           "states_declared": {k: v[0] for k, v in STATES.items()},
           "arms": list(ARMS), "m_declared": int(m_declared),
           "min_episodes_per_cell": MIN_EPISODES,
           "null": "permute state labels across episodes; preserves "
                   "delta's marginal distribution, destroys only its "
                   "relationship to state",
           "n_positive_cells": int(len(positive)),
           "n_positive_holm_survivors": int(len(pos_holm)),
           "cells": res_df.to_dict("records"),
           "verdict": verdict}
    p = OUT / f"convexity_conditional_1_{int(a.threshold*100)}_2026-08-20.json"
    p.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")

    print(f"\n{m_declared} declared cells; {len(positive)} lean positive, "
          f"{len(pos_holm)} survive Holm")
    show = res_df.sort_values("mean_delta_vs_hold", ascending=False).head(8)
    print(f"\n{'arm':13s} {'state':18s} {'cell':5s} {'n':>6s} "
          f"{'delta':>9s} {'p2':>7s} holm")
    for _, r in show.iterrows():
        print(f"{r['arm']:13s} {r['state']:18s} {r['cell']:5s} "
              f"{r['n']:>6d} {r['mean_delta_vs_hold']:>+9.4f} "
              f"{r['p_two_sided']:>7.3f} "
              f"{'YES' if r['holm_survives'] else ''}")
    print(f"\nVERDICT: {verdict}")
    print(f"receipt -> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
