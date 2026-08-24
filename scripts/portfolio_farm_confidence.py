"""How wide is a farm result, and could this sample have resolved it at all?

    python -m scripts.portfolio_farm_confidence
    python -m scripts.portfolio_farm_confidence --start 2013 --end 2024

RUN THE POWER CHECK FIRST. It is the only one of the three that can tell you the
study was incapable of answering its question, and canon §64 requires it BEFORE
any confirmation. The farm ran ~1,700 policies without one.

Three instruments, in the order they should be read:

1. **`power_check`** — tracking error, standard error, implied t, MDE, and the
   years the observed effect would need. A row whose
   `sample_can_resolve_observed_effect` is False answered nothing, whatever
   terminal wealth it reported.
2. **`excess_interval`** — stationary block bootstrap (Politis & Romano 1994)
   on the daily excess series, per rebalance phase. Turns a point into a band.
3. **`reality_check`** — White (2000), over every policy in the run including
   the nulls. Prices the SEARCH: a leaderboard's top row was selected for being
   the top row.

MEASURED 2026-08-24 on `mom_12_1 / h=5 / k=10 / inverse_vol`:

    tracking error   35.7%/yr    implied t          1.54
    excess           16.6%/yr    MDE at 80% power  30.3%/yr
    bootstrap CI     contains zero in all five phases
    reality-check p  0.126 over 45 policies
    years needed     36          (CRSP 1990-2024 is 35)

Four instruments, one underlying variance. The candidate is a plausible
hypothesis and not a finding, and the fix is history rather than cleverness.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from backend.services.portfolio_farm import (bootstrap as B, farm,  # noqa: E402
                                             panel as P)
from backend.services.portfolio_farm.policy import Policy  # noqa: E402

#: The candidate under examination. Kept in one place so this script and
#: `portfolio_farm_subperiod` cannot drift apart about what "the candidate" is.
CANDIDATE = dict(signal="mom_12_1", holding_days=5, top_k=10,
                 sizing="inverse_vol")
N_SEEDS = 20


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--start", type=int, default=2013)
    ap.add_argument("--end", type=int, default=2024)
    ap.add_argument("--n-boot", type=int, default=1000)
    a = ap.parse_args(argv)

    pan = P.load_panel(a.start, a.end)
    bench_all = P.market_benchmark(pan.dates)
    base = {k: v for k, v in CANDIDATE.items() if k != "signal"}
    pols = [Policy(**CANDIDATE, phase_offset=p)
            for p in range(CANDIDATE["holding_days"])]
    pols += [Policy(signal=s, signal_seed=k, **base)
             for s in ("random", "random_persistent") for k in range(N_SEEDS)]

    res = farm.run_many(pan, pols, progress=False)
    w0 = len(pan.dates) - len(res[0].dates)
    bench = np.where(np.isfinite(bench_all[w0:]), bench_all[w0:], np.nan)

    label = "/".join(f"{k}={v}" for k, v in CANDIDATE.items())
    print(f"CONFIDENCE — {label}   window {a.start}-{a.end}\n")

    # ── 1. POWER, first and always ──────────────────────────────────────────
    lead = max((r for r in res if r.policy.signal == CANDIDATE["signal"]),
               key=lambda r: r.metrics["terminal_usd"])
    pw = B.power_check(B.daily_returns(lead.nav), bench)
    print("1. POWER CHECK (canon §64 — run BEFORE believing anything below)")
    for k in ("years", "tracking_error_annual_pct", "se_of_mean_excess_pct",
              "observed_excess_annual_pct", "implied_t",
              "mde_at_80pct_power_annual_pct",
              "years_needed_for_observed_effect"):
        print(f"     {k:<36} {pw.get(k)}")
    resolvable = pw.get("sample_can_resolve_observed_effect")
    print(f"     {'SAMPLE CAN RESOLVE THIS EFFECT':<36} {resolvable}")
    if resolvable is False:
        print("     -> the study was incapable of answering its question. "
              "Everything below\n        is width around a number that could "
              "not have been established.")

    # ── 2. the band, per phase ──────────────────────────────────────────────
    print(f"\n2. STATIONARY BLOCK BOOTSTRAP  ({a.n_boot} resamples, "
          f"mean block {B.DEFAULT_BLOCK} sessions)")
    print(f"   {'phase':>5} {'excess%/yr':>11} {'95% CI':>22} "
          f"{'excl 0':>7} {'P(<=0)':>8}")
    print("   " + "-" * 56)
    excess = {}
    for r in sorted(res, key=lambda r: (r.policy.signal, r.policy.signal_seed,
                                        r.policy.phase_offset)):
        sr = B.daily_returns(r.nav)
        key = (f"{r.policy.signal}#{r.policy.signal_seed}"
               f"p{r.policy.phase_offset}")
        excess[key] = np.where(np.isfinite(sr) & np.isfinite(bench),
                               sr - bench, np.nan)
        if r.policy.signal != CANDIDATE["signal"]:
            continue
        o = B.excess_interval(sr, bench, n_boot=a.n_boot)
        print(f"   {r.policy.phase_offset:>5} {o['excess_annual_pct']:>10.2f}% "
              f"[{o['ci_lo_pct']:>7.2f}%,{o['ci_hi_pct']:>7.2f}%] "
              f"{str(o['excludes_zero']):>7} "
              f"{o['share_at_or_below_zero']:>8.3f}")

    # ── 3. the search ───────────────────────────────────────────────────────
    rc = B.reality_check(excess, n_boot=a.n_boot)
    print(f"\n3. WHITE'S REALITY CHECK  ({rc['n_policies']} policies: the "
          f"candidate's phases + {2 * N_SEEDS} nulls)")
    print(f"     best policy                 {rc['best_policy']}")
    print(f"     its excess                  "
          f"{rc['best_excess_annual_pct']:.2f}%/yr")
    print(f"     reality-check p             {rc['reality_check_p']}")
    print("     (the p prices the SEARCH. It does not price the fact that only "
          "one\n      price path exists — that is what the sub-period split is "
          "for.)")

    farm.save({"check": "confidence", "candidate": CANDIDATE,
               "window": [a.start, a.end], "power": pw, "reality_check": rc},
              "farm_confidence_candidate")
    print("\n  written: "
          f"{farm.RESULTS_DIR / 'farm_confidence_candidate.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
