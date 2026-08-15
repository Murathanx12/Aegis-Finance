"""Build the state-and-action-matched null regret table (G1).

    python -m scripts.gym_build_matched_null

WHAT THIS PRODUCES AND WHY IT IS AN ARTIFACT ON DISK
====================================================
`backend/data/optimus/research_gym/matched_null_v1.json` -- for every (VIX
bucket, policy), the distribution of "regret against the ex-post best of the
menu" scored by a decision-maker who simply always takes that action in that
state. That is the null. Dataset zero's regret numbers are only interpretable
as differences against it.

It is written to disk rather than recomputed because it must be IDENTICAL
across the runs that are compared to each other. A null recomputed per session
-- on a slightly different sample, a slightly different menu, a different cost
-- would drift, and every drift moves the headline in some direction nobody
declared.

MATCHEDNESS IS THE ENTIRE POINT
===============================
The first measurement of this null was run on SPY (dividend-adjusted) at 5bps
while dataset zero ran on ^GSPC (price only) at 10bps. Three mismatches inside
a comparison whose only job is to be matched. Defaults here are pinned to
dataset zero's, and `regret_triple` refuses to subtract a null whose cost or
horizon disagrees with the surface it is handed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from backend import config as _config
from backend.services.research_gym import base_rate as BR
from backend.services.research_gym import regret as RG

OUT = _config.OPTIMUS_LEDGER_DIR / "research_gym" / "matched_null_v1.json"

#: Pinned to dataset zero (`scripts/gym_dissect_timing.py`). Changing any of
#: these invalidates every excess-regret number computed against the artifact,
#: which is why they are constants here and not conveniences on the CLI.
UNIVERSE = "^GSPC"
HORIZON_DAYS = 63
COST_BPS = 10.0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--start", default="1990-01-01")
    ap.add_argument("--end", default="2026-08-15")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args(argv)

    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                        # noqa: BLE001
            pass

    import pandas as pd
    import yfinance as yf

    px = yf.download(UNIVERSE, start=a.start, end=a.end, progress=False)["Close"]
    vix = yf.download("^VIX", start=a.start, end=a.end, progress=False)["Close"]
    if isinstance(px, pd.DataFrame):
        px = px.squeeze()
    if isinstance(vix, pd.DataFrame):
        vix = vix.squeeze()

    rets = px.pct_change().dropna()
    # The state is read at the close BEFORE the window it is matched to. Using
    # same-day VIX would let the null see one day of the outcome it is the null
    # for, which is exactly the leak this table exists to rule out.
    vix_prev = vix.reindex(rets.index).ffill().shift(1)
    ok = vix_prev.notna()
    rets, vix_prev = rets[ok], vix_prev[ok]

    states = [BR.vix_bucket(float(v)) for v in vix_prev.to_numpy()]
    print(f"{UNIVERSE} {rets.index[0].date()} -> {rets.index[-1].date()}  "
          f"{len(rets)} daily returns, horizon {HORIZON_DAYS}d, "
          f"cost {COST_BPS}bps")

    mn = RG.build_matched_null(
        [float(x) for x in rets.to_numpy()], states,
        universe=UNIVERSE, horizon_days=HORIZON_DAYS, cost_bps=COST_BPS,
        sample_start=str(rets.index[0].date()),
        sample_end=str(rets.index[-1].date()))

    print(f"\ncells {len(mn.cells)}  pooled {len(mn.pooled)}  "
          f"menu_hash {mn.menu_hash}")
    print("\nTHE NULL -- mean regret vs ex-post best, by state and action")
    print(f"{'state':<10s} {'action':<30s} {'mean':>7s} {'p90':>7s} "
          f"{'n':>6s} {'n_eff':>7s} {'episodes':>9s}")
    for key in ("hold", "sell_100", "sell_50"):
        for bucket in ("vix<15", "vix15-20", "vix20-25", "vix25-35", "vix>=35"):
            c = mn.cells.get((bucket, key))
            if c is None:
                continue
            print(f"{bucket:<10s} {key:<30s} {c.mean_regret_pct:7.2f} "
                  f"{c.percentile(90):7.2f} {c.power.n_obs:6d} "
                  f"{c.power.n_effective:7.1f} {c.power.n_episodes:9d}")

    p = mn.write(Path(a.out))
    print(f"\nwritten  {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
