"""The bar the factory has to clear, and how much of it is multiplicity.

    python -m scripts.library_report_2006_2019

206 predictors measured on one window is 206 chances, so the raw table cannot be
read directly — that is the Gym's own failure mode with somebody else's
hypotheses. This applies the SCREEN criterion (Benjamini-Hochberg FDR, m = tests
actually run) through the same `decide()` entry point everything else uses, so
the criterion cannot be chosen after seeing the p-values.

FDR RATHER THAN FWER, DELIBERATELY (S63)
========================================
This is a screen. Holm at m=206 puts the first threshold at 0.00024 and would
leave a handful of microstructure signals, which is the kill machinery becoming
the programme. What a screen owes is control of the PROPORTION of its output
that is false — and it must say out loud how many that is.

THE SURVIVORS THEN GO THROUGH THE COST QUESTION G4 ANSWERED FOR EARNINGS
=======================================================================
Every survivor is re-measured inside each dollar-volume tercile. If the pattern
from the earnings work repeats — largest where it is least tradable — then the
library's headline is not "these N strategies work" but "these N work where you
cannot trade them", and that is a different sentence entirely.
"""

from __future__ import annotations

import json
import math
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from backend.services.research_gym.multiplicity import (SCREEN,
                                                        ConfirmationBudget,
                                                        window_id)
from scripts.library_measure_2006_2019 import (END, MIN_DVOL_PCTILE,
                                               MIN_NAMES, MIN_PRICE, OUT,
                                               SEED_MAP, START, decile_ls,
                                               load_osap, load_panel, score)

DOC = Path("docs/STRATEGY_LIBRARY_MEASURED_2006_2019.md")
Q = 0.10


def two_sided_p(z: float) -> float:
    if not np.isfinite(z):
        return 1.0
    return float(math.erfc(abs(z) / math.sqrt(2.0)))


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                        # noqa: BLE001
            pass

    payload = json.loads(OUT.read_text(encoding="utf-8"))
    res = payload["results"]
    ok = {k: v for k, v in res.items()
          if not v.get("refused") and not v.get("insufficient")
          and np.isfinite(v.get("z", np.nan))}
    for v in ok.values():
        v["p"] = two_sided_p(v["z"])

    nets = np.array([v["net_annual"] for v in ok.values()])
    print("=" * 74)
    print(f"THE PUBLISHED WHEEL ON OUR PANEL, {START}-{END}, NET OF 10bp")
    print("=" * 74)
    print(f"  predictors measured        {len(ok)}")
    print(f"  median net annual          {100 * np.median(nets):+.2f}%")
    print(f"  mean net annual            {100 * nets.mean():+.2f}%")
    print(f"  share with net > 0         "
          f"{100 * (nets > 0).mean():.0f}%")
    print(f"  share clearing +3%/yr      {100 * (nets >= 0.03).mean():.0f}%  "
          f"(the execution standard, before any multiplicity control)")

    # ── the screen, through the one entry point ────────────────────────────
    cb = ConfirmationBudget(Path(tempfile.mkdtemp()) / "screen.jsonl")
    W = window_id(universe="crsp_us_2006_2019", period=f"{START}..{END}",
                  outcome="ls_decile_net_annual")
    cb.declare_budget(W, budget=len(ok), declared_by="library-screen",
                      purpose=SCREEN, rate=Q,
                      note="EXPLORE window slc_c3246e5093c41c25; a SCREEN "
                           "result may never be quoted as a confirmation")
    for name, v in ok.items():
        cb.reserve(W, trial=name, hypothesis="ls decile spread != 0")
        cb.record_result(W, trial=name, hypothesis="ls decile spread != 0",
                         p_value=v["p"])
    rep = cb.decide(W)
    survivors = [d["trial"] for d in rep["decisions"] if d["rejected"]]

    print(f"\n  criterion                  {rep['criterion']} at q={Q}, "
          f"m={rep['m_used']}")
    print(f"  survive the screen         {rep['n_rejected']}")
    print(f"  would have been claimed    {rep['naive_n_below_alpha']} "
          f"(uncontrolled p <= {Q})")
    print(f"  expected false among them  "
          f"~{rep['expected_false_among_rejected']}  BY DESIGN")

    # ── what the seeded library actually delivered ─────────────────────────
    print("\n" + "=" * 74)
    print("THE TEN SEEDED STRATEGIES")
    print("=" * 74)
    print(f"  {'strategy':<40} {'gross':>8} {'net':>8} {'z':>6} {'be':>8}")
    for nm, col in SEED_MAP.items():
        if col is None or f"__refused::{nm}" in res:
            print(f"  {nm:<40} {'REFUSED — no faithful implementation':>8}")
            continue
        v = ok.get(col)
        if v is None:
            print(f"  {nm:<40} {'not measured':>8}")
            continue
        mark = " *" if col in survivors else ""
        print(f"  {nm:<40} {100 * v['gross_annual']:+7.2f}% "
              f"{100 * v['net_annual']:+7.2f}% {v['z']:+6.1f} "
              f"{v['breakeven_bps']:7.1f}bp{mark}")
    print("  * survives the FDR screen")

    # ── the survivors, by liquidity ────────────────────────────────────────
    print("\n" + "=" * 74)
    print("EVERY SURVIVOR, RE-MEASURED INSIDE EACH DOLLAR-VOLUME TERCILE")
    print("=" * 74)
    published = [s for s in survivors if not s.startswith("__")]
    ret, prc, dvl = load_panel()
    months = pd.period_range(f"{str(START)[:4]}-{str(START)[4:]}",
                             f"{str(END)[:4]}-{str(END)[4:]}", freq="M")
    perms = sorted(set(ret.columns))
    pidx = {p: i for i, p in enumerate(perms)}
    n_m, n_p = len(months), len(perms)
    R = ret.reindex(index=months, columns=perms).to_numpy()
    P = prc.reindex(index=months, columns=perms).to_numpy()
    V = dvl.reindex(index=months, columns=perms).to_numpy()
    FWD = np.vstack([R[1:], np.full((1, n_p), np.nan)])
    base = np.isfinite(P) & (P >= MIN_PRICE) & np.isfinite(V)
    rank = np.full((n_m, n_p), np.nan)
    for t in range(n_m):
        m = base[t]
        if m.sum() > 10:
            rank[t, m] = pd.Series(V[t, m]).rank(pct=True).to_numpy() * 100
    OKALL = base & (rank >= MIN_DVOL_PCTILE)
    # Terciles WITHIN the screened universe, month by month: pooling across
    # years would sort on the calendar, since volume grows about tenfold.
    masks = {}
    for lab, (lo, hi) in {"illiquid": (MIN_DVOL_PCTILE, 46.7),
                          "mid": (46.7, 73.3),
                          "liquid": (73.3, 100.1)}.items():
        masks[lab] = OKALL & (rank >= lo) & (rank < hi)

    d = load_osap(published) if published else None
    rng = np.random.default_rng(20260817)
    rows = []
    if d is not None:
        mi = ((d.yyyymm // 100 - int(str(START)[:4])) * 12
              + (d.yyyymm % 100 - int(str(START)[4:]))).to_numpy()
        pi = d.permno.map(pidx).to_numpy()
        g = np.isfinite(pi.astype("float64")) & (mi >= 0) & (mi < n_m)
        mi, pi = mi[g].astype(int), pi[g].astype(int)
        print(f"  {'predictor':<20} {'all':>9} {'illiquid':>10} {'mid':>9} "
              f"{'liquid':>9}   verdict")

        def cell(v) -> str:
            """A cell that was not measured prints as such.

            The first version formatted a NaN as `+nan%` and then attached a
            verdict to it. An unmeasured cell must never be mistaken for a
            measured zero — that is the same defect as a clean verdict over
            unscoreable rows, one column to the left.
            """
            x = v.get("net_annual")
            return (f"{100 * x:+8.2f}%" if x is not None and np.isfinite(x)
                    else f"{'n/a':>9}")

        for c in published:
            S = np.full((n_m, n_p), np.nan)
            S[mi, pi] = d[c].to_numpy(dtype="float64")[g]
            cells = {}
            for lab, msk in masks.items():
                r, tn = decile_ls(S, FWD, msk)
                cells[lab] = score(r, tn, rng)
            allv = ok[c]
            lq, il = cells["liquid"], cells["illiquid"]
            lqx = lq.get("net_annual")
            ilx = il.get("net_annual")
            measured_liq = lqx is not None and np.isfinite(lqx)

            # FOUR STATES, NOT TWO. The first version had "survives in liquid"
            # and "concentrated where it cannot be traded", and sent everything
            # that was not the first into the second — including VolumeTrend,
            # whose liquid tercile is LARGER than its illiquid one. Not
            # detectable is not the same as concentrated elsewhere, and neither
            # is the same as not measured.
            if allv["net_annual"] < 0:
                verdict = "SIGN INVERTED vs publication — not a strategy"
            elif not measured_liq:
                verdict = "NOT MEASURABLE in the liquid tercile"
            elif lq.get("detectable") and lqx > 0:
                verdict = "detectable and positive where it CAN be traded"
            elif ilx is not None and np.isfinite(ilx) and ilx > lqx:
                verdict = "larger in the illiquid tercile"
            else:
                verdict = "below its own MDE in the liquid tercile"

            rows.append({"predictor": c, "all": allv["net_annual"],
                         "illiquid": ilx, "mid": cells["mid"].get("net_annual"),
                         "liquid": lqx,
                         "liquid_n_months": lq.get("n_months"),
                         "liquid_mde": lq.get("mde_annual"),
                         "liquid_detectable": bool(lq.get("detectable")),
                         "verdict": verdict})
            print(f"  {c:<20} {100 * allv['net_annual']:+8.2f}% "
                  f"{cell(il)} {cell(cells['mid'])} {cell(lq)}   {verdict}")

    tradable = [r for r in rows if r["liquid_detectable"] and r["liquid"]
                and r["liquid"] > 0 and r["all"] > 0]
    print(f"\n  survivors that are also detectable in the LIQUID tercile: "
          f"{len(tradable)} of {len(rows)}")
    best = max(tradable, key=lambda r: r["liquid"], default=None)
    bar = best["liquid"] if best else None
    print(f"  THE FACTORY'S BAR (best net annual a published predictor "
          f"delivers\n  in the tradable tercile on this window): ", end="")
    if best is None:
        print("NONE ESTABLISHED")
    else:
        print(f"{100 * bar:.2f}%  ({best['predictor']}, "
              f"MDE {100 * best['liquid_mde']:.2f}%, "
              f"{best['liquid_n_months']} months)")
        print("  A mechanism the factory produces has to beat THIS, net, on a "
              "window\n  it did not choose — not the literature's headline and "
              "not the gross number.")

    out = OUT.parent / "report_2006_2019.json"
    out.write_text(json.dumps(
        {"screen": rep, "survivors": survivors, "terciles": rows,
         "factory_bar_net_annual_liquid": bar,
         "median_net_annual": float(np.median(nets)),
         "n_measured": len(ok)}, indent=1, default=float), encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
