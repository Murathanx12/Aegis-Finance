"""N23 — how many names does each survivor actually have where it claims to trade?

    python -m scripts.n23_population_in_scope

WHY THIS RUNS DELIBERATELY INSTEAD OF BY ACCIDENT
=================================================
`std_turn` printed +18.28% overall and `n/a` in the liquid tercile, and the only
reason we know why is that a NaN-formatting repair went looking. The answer was
a **median of two eligible names per month** in that tercile against 546 across
the screened universe. A decile sort needs a population; two names have no
deciles, so the cell was never a measurement.

That is `NO_POPULATION_IN_SCOPE`: the effect lives somewhere, we can act
somewhere, and the two sets do not intersect. It is a distinct verdict from
"too small to detect" — an effect below its MDE might be found with more data,
and a universe that does not exist will not appear with more data.

Finding it by accident once is luck. This runs it for **every** BH-FDR survivor,
in **every** tercile, and reports the median eligible population and the implied
decile size. A survivor with single-digit population is not a strategy at any
effect size, and it should never have reached a verdict column.

THE SCREEN IS NOT THE POPULATION
================================
`decile_ls` requires MIN_NAMES eligible names in a month and at least five per
decile, and silently skips months that miss it. Skipping is right — but a
strategy that clears the bar in thirty of 167 months and is scored on those
thirty is being measured on a different universe from the one its table implies.
So months-scored is reported beside the population.

Every number here comes from the ALREADY-SPENT selection window. No outcome is
read: eligibility is a property of price, volume and signal coverage, and it is
computed before any return is touched.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from backend.services.research_gym.population import (MIN_DECILE_MEMBERS,
                                                      assess_population)
from scripts.library_measure_2006_2019 import (END, MIN_DVOL_PCTILE, MIN_NAMES,
                                               MIN_PRICE, N_DECILES, OUT,
                                               START, load_osap, load_panel)

REPORT = Path(r"C:\Users\mrthn\Aegis module\data\library\report_2006_2019.json")

#: The same tercile cut points the report used, so the two tables describe the
#: same cells. Terciles are taken WITHIN the screened universe, month by month.
TERCILES = {"illiquid": (MIN_DVOL_PCTILE, 46.7),
            "mid": (46.7, 73.3),
            "liquid": (73.3, 100.1)}


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                        # noqa: BLE001
            pass

    rep = json.loads(REPORT.read_text(encoding="utf-8"))
    survivors = [s for s in rep["survivors"] if not s.startswith("__")]
    verdicts = {r["predictor"]: r["verdict"] for r in rep["terciles"]}

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
    masks = {"all": OKALL}
    for lab, (lo, hi) in TERCILES.items():
        masks[lab] = OKALL & (rank >= lo) & (rank < hi)

    print("=" * 78)
    print("N23 — POPULATION IN SCOPE, SWEPT ACROSS EVERY BH-FDR SURVIVOR")
    print("=" * 78)
    print(f"  window {START}..{END}   {n_m} months   universe {n_p} permnos")
    print(f"  a decile sort needs {N_DECILES} x {MIN_DECILE_MEMBERS} = "
          f"{N_DECILES * MIN_DECILE_MEMBERS} names, and `decile_ls` also "
          f"requires {MIN_NAMES}")
    print(f"  median eligible names/month, screened universe: "
          f"{np.median(OKALL.sum(1)):.0f}")

    d = load_osap(survivors)
    mi = ((d.yyyymm // 100 - int(str(START)[:4])) * 12
          + (d.yyyymm % 100 - int(str(START)[4:]))).to_numpy()
    pi = d.permno.map(pidx).to_numpy()
    g = np.isfinite(pi.astype("float64")) & (mi >= 0) & (mi < n_m)
    mi, pi = mi[g].astype(int), pi[g].astype(int)

    print(f"\n  {'predictor':<20} {'all':>7} {'illiq':>7} {'mid':>7} "
          f"{'liquid':>7} {'liq dec':>8} {'liq mo':>7}  scope verdict")
    rows = []
    for c in survivors:
        S = np.full((n_m, n_p), np.nan)
        S[mi, pi] = d[c].to_numpy(dtype="float64")[g]
        have = np.isfinite(S) & np.isfinite(FWD)
        counts = {lab: (msk & have).sum(1) for lab, msk in masks.items()}
        med = {lab: float(np.median(v)) for lab, v in counts.items()}
        liq = counts["liquid"]
        # `assess_population` is the guard: it derives the verdict from the
        # counts it is handed and refuses if it is handed none.
        a = assess_population(f"{c} @ liquid dollar-volume tercile", liq,
                              n_deciles=N_DECILES, min_names=MIN_NAMES)
        rows.append({"predictor": c, "median_by_scope": med,
                     "liquid_months_scoreable": a["months_scoreable"],
                     "liquid_median_decile_members": a["median_decile_members"],
                     "scope_verdict": a["verdict"],
                     "tercile_verdict": verdicts.get(c, "")})
        print(f"  {c:<20} {med['all']:>7.0f} {med['illiquid']:>7.0f} "
              f"{med['mid']:>7.0f} {med['liquid']:>7.0f} "
              f"{a['median_decile_members']:>8.0f} "
              f"{a['months_scoreable']:>7d}  {a['verdict']}")

    dead = [r for r in rows if r["scope_verdict"] == "NO_POPULATION_IN_SCOPE"]
    thin = [r for r in rows if r["scope_verdict"] == "THIN_POPULATION"]
    print(f"\n  NO_POPULATION_IN_SCOPE in the liquid tercile: {len(dead)} of "
          f"{len(rows)}")
    for r in dead:
        print(f"    {r['predictor']:<20} median "
              f"{r['median_by_scope']['liquid']:.0f} names/month "
              f"({r['liquid_months_scoreable']} scoreable months)")
    if thin:
        print(f"  THIN_POPULATION (scoreable, but on a fraction of the "
              f"months): {len(thin)}")
        for r in thin:
            print(f"    {r['predictor']:<20} "
                  f"{r['liquid_months_scoreable']} of {n_m} months")

    print("\n" + "=" * 78)
    print("WHAT THIS CHANGES")
    print("=" * 78)
    print("  A scope verdict is not an effect-size verdict. The predictors")
    print("  above with no population were never measured where they claim to")
    print("  trade, so their liquid-tercile cells are ABSENT rather than small,")
    print("  and no amount of forward data fixes that. The check now runs at")
    print("  REGISTRATION (`research_gym.population.assert_population_declared`)")
    print("  so a prereg that names a universe states that universe's median")
    print("  population or is refused — a universe that does not exist should")
    print("  not be discoverable afterwards.")

    out = OUT.parent / "n23_population_in_scope.json"
    out.write_text(json.dumps(
        {"window": f"{START}..{END}", "n_months": n_m,
         "screened_universe_median": float(np.median(OKALL.sum(1))),
         "terciles": TERCILES, "min_names": MIN_NAMES,
         "n_deciles": N_DECILES, "min_decile_members": MIN_DECILE_MEMBERS,
         "rows": rows,
         "n_no_population": len(dead), "n_thin": len(thin),
         "consumed": "nothing — eligibility is price, volume and signal "
                     "coverage, computed before any return is read"},
        indent=1, default=float), encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
