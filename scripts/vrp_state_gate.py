"""VRP_STATE_GATE_v1 -- is there a STATE in which the refuted core works?

    python -m scripts.vrp_state_gate
    python -m scripts.vrp_state_gate --symbols SPY,QQQ,IWM --bins 5

THE QUESTION THIS ASKS, AND WHY IT IS NOT THE ONE ALREADY ANSWERED
==================================================================
`optionmetrics_core_replay` refuted the short put spread GLOBALLY: over
1996-2025 it fails on two of three underlyings and beats buy-and-hold on none.

**A global negative does not answer a conditional question that was never
asked** (CANON, and `docs/HANDOFF_2026-08-16_BRAIN_TO_BUILDER.md` section 2).
Selling variance is not supposed to pay unconditionally -- it is supposed to pay
when the market is charging MORE for variance than the underlying goes on to
deliver. If that compensation is measurable at entry, the structure is
conditional rather than dead, and the gate is worth building.

So: sort every block by the compensation ON OFFER at entry, and ask whether the
subsequent return rises with it.

    vrp        = short-leg implied vol  -  trailing 20d realised vol (shifted)
    credit     = credit / width, the price actually received

Both are known strictly before the decision. `rv20` is `.shift(1)`-ed so the
entry session's own return is not inside the volatility it is compared against.

WHAT WOULD COUNT AS AN EDGE, DECIDED BEFORE LOOKING
===================================================
A monotone rise in TERMINAL WEALTH across the state bins, with the top bin
beating buy-and-hold over the same blocks. Not a rise in the median -- the whole
refutation was a structure with a positive median and 0.05x wealth
(`feedback-rank-on-terminal-wealth-not-the-mean`).

A rise in the top bin ALONE is not enough: with 5 bins and 3 symbols this
inspects 15 cells, and the largest of 15 noise draws is routinely 2 sigma. The
monotonicity is what distinguishes a mechanism from a maximum.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.optionmetrics_core_replay import (  # noqa: E402
    replay_symbol, stats, wealth)


def by_state(df: pd.DataFrame, col: str, bins: int, risk_frac: float) -> pd.DataFrame:
    d = df[np.isfinite(df[col])].copy()
    if len(d) < bins * 10:
        return pd.DataFrame()
    d["bin"] = pd.qcut(d[col], bins, labels=False, duplicates="drop")
    rows = []
    for b, g in d.groupby("bin"):
        ror = (g["short_put_spread_pnl"] / g["short_put_spread_risk"]).to_numpy()
        st = stats(ror)
        rows.append({
            "bin": int(b), "n": st["n"],
            f"{col}_lo": float(g[col].min()), f"{col}_hi": float(g[col].max()),
            "median": st["median"], "mean": st["mean"], "hit": st["hit"],
            "t": st["t"], "worst": st["worst"],
            "wealth": wealth(ror, risk_frac),
            "hold": float(np.prod(1.0 + g["under_ret"].to_numpy())),
        })
    return pd.DataFrame(rows)


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    """Rank correlation without scipy."""
    if x.size < 3:
        return float("nan")
    rx = pd.Series(x).rank().to_numpy()
    ry = pd.Series(y).rank().to_numpy()
    rx, ry = rx - rx.mean(), ry - ry.mean()
    d = math.sqrt(float((rx ** 2).sum()) * float((ry ** 2).sum()))
    return float((rx * ry).sum() / d) if d > 0 else float("nan")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="SPY,QQQ,IWM")
    ap.add_argument("--bins", type=int, default=5)
    ap.add_argument("--hold", type=int, default=5)
    ap.add_argument("--delta", type=float, default=0.25)
    ap.add_argument("--width-frac", type=float, default=0.05)
    ap.add_argument("--risk-frac", type=float, default=0.20)
    ap.add_argument("--start", type=int, default=1996)
    ap.add_argument("--end", type=int, default=2025)
    args = ap.parse_args()

    print("VRP STATE GATE   does the compensation ON OFFER at entry predict the "
          "spread's return?")
    print("a global negative does not answer a conditional question. Ranking on "
          "TERMINAL WEALTH.")
    print("=" * 100)

    verdicts = []
    for sym in args.symbols.split(","):
        r = replay_symbol(sym, hold=args.hold, short_delta=args.delta,
                          width_frac=args.width_frac, start=args.start,
                          end=args.end)
        if r["n"] == 0:
            print(f"\n{sym}: no blocks")
            continue
        df = r["df"]
        ror = (df["short_put_spread_pnl"] / df["short_put_spread_risk"]).to_numpy()

        for col in ("vrp", "credit_ratio"):
            tab = by_state(df, col, args.bins, args.risk_frac)
            if tab.empty:
                print(f"\n{sym} / {col}: too few blocks to bin")
                continue
            m = np.isfinite(df[col])
            rho = spearman(df.loc[m, col].to_numpy(), ror[m.to_numpy()])
            print(f"\n{sym}  state = {col}   {int(m.sum())} blocks   "
                  f"rank corr with return {rho:+.3f}")
            print(f"  {'bin':<5}{'range':>20}{'n':>6}{'median':>9}{'mean':>9}"
                  f"{'hit':>8}{'t':>7}{'worst':>9}{'wealth':>9}{'hold':>8}")
            print("  " + "-" * 92)
            for _, row in tab.iterrows():
                rng = f"{row[f'{col}_lo']:+.3f}..{row[f'{col}_hi']:+.3f}"
                print(f"  {int(row['bin']):<5}{rng:>20}{int(row['n']):>6}"
                      f"{row['median']:>+9.2%}{row['mean']:>+9.2%}"
                      f"{row['hit']:>8.1%}{row['t']:>+7.2f}{row['worst']:>+9.2%}"
                      f"{row['wealth']:>9.2f}x{row['hold']:>7.2f}x")

            w = tab["wealth"].to_numpy()
            mono = spearman(tab["bin"].to_numpy().astype(float), w)
            top_beats_hold = bool(w[-1] > tab["hold"].to_numpy()[-1])
            verdicts.append((sym, col, mono, top_beats_hold, float(w[-1])))
            print(f"  monotonicity of WEALTH across bins: {mono:+.2f}   "
                  f"top bin {'BEATS' if top_beats_hold else 'loses to'} "
                  f"buy-and-hold on its own blocks")

    print("\n" + "=" * 100)
    print("VERDICT")
    good = [v for v in verdicts if v[2] > 0.5 and v[3]]
    for sym, col, mono, beats, w in verdicts:
        print(f"  {sym:<5} {col:<14} monotonicity {mono:+.2f}   "
              f"top-bin wealth {w:>6.2f}x   "
              f"{'CONDITIONAL EDGE' if (mono > 0.5 and beats) else 'no'}")
    if not good:
        print("\n  NO STATE RESCUES THE STRUCTURE. The compensation on offer at "
              "entry does not\n  order the outcome, so there is no gate to build "
              "-- the refutation stands\n  unconditionally, not merely on average.")
    else:
        print(f"\n  {len(good)} of {len(verdicts)} cells show a monotone, "
              f"hold-beating conditional edge.\n  With {args.bins} bins x "
              f"{len(args.symbols.split(','))} symbols x 2 states this inspects "
              f"{len(verdicts) * 1} cells;\n  treat the ORDERING as the finding "
              f"and the level as an upper bound.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
