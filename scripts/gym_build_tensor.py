"""Build the REGRET_TENSOR: state x action x horizon over a corpus.

    python -m scripts.gym_build_tensor --stride 5

WHAT IT IS FOR
==============
To answer *"which actions are bad in which states, over what horizon"* — with a
sample size and an MDE per cell, so the table cannot be read by scanning for
the largest number. Scanning a table of thousands of cells for its maximum is
a maximum over thousands of noisy draws, which is G1 one dimension up.

The corpus is deliberately NOT just SPY. A tensor built on the index and then
consulted about the index is a tensor consulted about the thing it was built
from wearing a different date.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from backend import config as _config
from backend.services.research_gym import base_rate as BR
from backend.services.research_gym import tensor as T

OUT = _config.OPTIMUS_LEDGER_DIR / "research_gym" / "regret_tensor_v1.json"

UNIVERSE = ["SPY", "QQQ", "IWM", "XLF", "XLE", "XLK"]
COST_BPS_ONE_WAY = 10.0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--start", default="1999-01-01")
    ap.add_argument("--end", default="2026-08-15")
    ap.add_argument("--stride", type=int, default=5,
                    help="trading days between sampled decisions")
    ap.add_argument("--horizons", default="5,20,60,120,252")
    ap.add_argument("--universe", default=",".join(UNIVERSE))
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args(argv)

    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                        # noqa: BLE001
            pass

    import pandas as pd
    import yfinance as yf

    horizons = [int(x) for x in a.horizons.split(",") if x.strip()]
    universe = [x.strip().upper() for x in a.universe.split(",") if x.strip()]

    vix = yf.download("^VIX", start=a.start, end=a.end, progress=False)["Close"]
    if isinstance(vix, pd.DataFrame):
        vix = vix.squeeze()

    series = {}
    for tkr in universe:
        px = yf.download(tkr, start=a.start, end=a.end, progress=False)["Close"]
        if isinstance(px, pd.DataFrame):
            px = px.squeeze()
        px = px.dropna()
        rets = px.pct_change().dropna()
        # The state is read at the close BEFORE the window it labels. Same-day
        # VIX would let the cell see one day of its own outcome.
        vprev = vix.reindex(rets.index).ffill().shift(1)
        ok = vprev.notna()
        rets, vprev = rets[ok], vprev[ok]
        if len(rets) < max(horizons) + 10:
            print(f"  {tkr}: too short, skipped")
            continue
        series[tkr] = ([float(x) for x in rets.to_numpy()],
                       [BR.vix_bucket(float(v)) for v in vprev.to_numpy()])
        print(f"  {tkr:<6s} {len(rets)} returns "
              f"{rets.index[0].date()} -> {rets.index[-1].date()}")

    if not series:
        print("no usable series")
        return 1

    print(f"\nbuilding tensor: {len(series)} securities x {len(horizons)} "
          f"horizons, stride {a.stride}d, cost {COST_BPS_ONE_WAY}bps")
    tens = T.build_regret_tensor(
        series, horizons=horizons, cost_bps=COST_BPS_ONE_WAY, stride_days=a.stride,
        sample_start=a.start, sample_end=a.end,
        progress=lambda tkr, H: print(f"    {tkr} H={H}d done"))

    print(f"\ncells {len(tens.cells)}  menu {tens.menu_hash}")
    print("\nWHICH ACTIONS ARE BAD IN WHICH STATES (edge vs HOLD, "
          "DETECTABLE cells only)")
    for H in horizons:
        for st in ("vix<15", "vix20-25", "vix25-35", "vix>=35"):
            worst = tens.worst_actions(st, H)
            if not worst:
                continue
            print(f"\n  {st}  H={H}d  ({len(worst)} of 17 actions detectable)")
            for c in worst[:4]:
                print(f"    {c.action:<32s} {c.mean_edge_vs_default_pp:+8.2f}pp "
                      f"  MDE {c.power.mde_mean_pct:6.2f}  "
                      f"n_eff {c.power.n_effective:6.1f}")

    p = tens.write(Path(a.out))
    print(f"\nwritten  {p}")
    print("Gym output. Cells are hypotheses, never claims (R2 wall 1).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
