"""Build the UTILITY_TENSOR and print the UTILITY-FLIP ATLAS.

    python -m scripts.gym_build_utility_tensor --stride 5

WHAT IT ADDS TO `gym_build_tensor`
==================================
The same episodes, the same windows, the same stride, the same
episode-clustering correction — scored under several DECLARED objectives
instead of under raw terminal return alone. Identical sample by construction,
so any disagreement between the two tensors is a disagreement about the
objective and cannot be a disagreement about the data.

THE OUTPUT THAT MATTERS
=======================
Not another leaderboard. The **flip atlas**: the (state, horizon) cells where
the preferred action CHANGES when the objective changes, and `gamma*` — the
risk aversion at which the raw-return winner stops being preferred to holding.
A flip whose gap is below the MDE of the difference is reported as NOT material,
because §19 does not stop applying when the quantity becomes interesting.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend import config as _config
from backend.services.research_gym import base_rate as BR
from backend.services.research_gym import utility_tensor as UT

OUT = _config.OPTIMUS_LEDGER_DIR / "research_gym" / "utility_tensor_v1.json"
UNIVERSE = ["SPY", "QQQ", "IWM", "XLF", "XLE", "XLK"]
COST_BPS = 10.0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--start", default="1999-01-01")
    ap.add_argument("--end", default="2026-08-15")
    ap.add_argument("--stride", type=int, default=5)
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
        # The state is read at the close BEFORE the window it labels.
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

    print(f"\nbuilding utility tensor: {len(series)} securities x "
          f"{len(horizons)} horizons x {len(UT.DEFAULT_OBJECTIVES)} objectives, "
          f"stride {a.stride}d, cost {COST_BPS}bps")
    t = UT.build_utility_tensor(
        series, horizons=horizons, cost_bps=COST_BPS, stride_days=a.stride,
        sample_start=a.start, sample_end=a.end,
        progress=lambda tkr, H: print(f"    {tkr} H={H}d done"))

    print(f"\ncells {len(t.cells)}  objectives {t.objectives}")

    # ── 1. where the SIGN disagrees with raw return ─────────────────────────
    print("\nSIGN DISAGREEMENTS — the action earns more and is worth less, "
          "or the reverse\n(detectable cells only)")
    n_dis = 0
    for c in t.cells.values():
        if c.objective == UT.REFERENCE_OBJECTIVE:
            continue
        if c.sign_agrees_with_raw is False and c.edge_is_detectable:
            n_dis += 1
            if n_dis <= 25:
                print(f"  {c.state_key:<9s} H={c.horizon_days:>3d}d "
                      f"{c.action:<30s} {c.objective:<32s} "
                      f"raw {c.raw_edge_pp:+7.2f}pp  util {c.utility_edge:+9.4f} "
                      f"{c.units:<5s} MDE {c.power.mde_mean_pct:7.4f} "
                      f"n_eff {c.power.n_effective:5.1f}")
    print(f"  ... {n_dis} detectable sign disagreements in total")

    # ── 1b. DEGENERACY — read BEFORE the atlas ─────────────────────────────
    print("\nOBJECTIVE DEGENERACY — does this objective just prefer CASH?")
    deg = t.degenerate_objectives()
    for name, d in deg.items():
        flag = "  *** DEGENERATE" if d["degenerate"] else ""
        print(f"  {name:<34s} prefers cash in {d['n_prefers_cash']:>3d}/"
              f"{d['n_cells']:<3d} cells ({d['frac_prefers_cash']:.0%}){flag}")
    bad = {k for k, d in deg.items() if d["degenerate"]}
    if bad:
        print(f"  -> flips produced by {sorted(bad)} are artefacts of the "
              f"objective, not preferences being revealed.")

    # ── 2. THE FLIP ATLAS ──────────────────────────────────────────────────
    flips = t.flips()
    material = [f for f in flips if f.material]
    material_clean = [f for f in material if f.objective not in bad]
    print(f"\nUTILITY-FLIP ATLAS — {len(flips)} flips, {len(material)} MATERIAL "
          f"(gap clears the MDE of the difference), of which "
          f"{len(material_clean)} are NOT from a degenerate objective")
    print(f"{'state':<9s} {'H':>4s}  {'objective':<32s} "
          f"{'best@return':<30s} {'best@objective':<30s} {'gap':>10s} "
          f"{'MDE':>9s} {'n_eff':>6s} {'gamma*':>7s}")
    for f in sorted(flips, key=lambda x: (not bool(x.material), x.state_key,
                                          x.horizon_days)):
        mark = "*" if f.material else (" " if f.material is False else "?")
        g = "-" if f.gamma_star is None else f"{f.gamma_star:6.2f}"
        m = "-" if f.mde_of_gap is None else f"{f.mde_of_gap:9.4f}"
        print(f"{mark}{f.state_key:<8s} {f.horizon_days:>4d}  "
              f"{f.objective:<32s} {f.best_under_reference:<30s} "
              f"{f.best_under_objective:<30s} {f.gap_under_objective:>10.4f} "
              f"{m:>9s} {f.n_effective:>6.1f} {g:>7s}")

    # ── 3. break-even risk aversion ────────────────────────────────────────
    print("\nBREAK-EVEN RISK AVERSION gamma* — the raw-return winner vs HOLD")
    print("  (below gamma* the winner is preferred; above it, holding is. "
          "None = dominance at every gamma in [0, 30].)")
    for (st, H), g in sorted(t.gamma_star.items()):
        ci = t.gamma_star_ci.get((st, H)) or {}
        lo, hi = ci.get("lo"), ci.get("hi")
        band = ("" if lo is None else
                f"   [{lo:5.2f}, {hi:5.2f}]  crossing in "
                f"{ci.get('frac_crossing', 0):.0%} of resamples"
                f"   vs {ci.get('winner', '?')}")
        print(f"  {st:<9s} H={H:>3d}d   "
              + ("gamma* = -   (dominates at every risk aversion)"
                 if g is None else f"gamma* = {g:6.2f}") + band)

    p = Path(a.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(t.as_dict(), indent=2), encoding="utf-8")
    print(f"\nwritten  {p}")
    print("Gym output. Cells are hypotheses, never claims (R2 wall 1).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
