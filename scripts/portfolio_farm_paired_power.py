"""Is a signal's edge over ANOTHER BOOK resolvable — not just over the market?

    python -m scripts.portfolio_farm_paired_power --start 1993 --end 2024 --reduce \
        --signal profit_roe --benchmark equal --top-k 100

WHY THIS EXISTS
===============
Every power check in the farm compares a book to the CAP-WEIGHTED market. That
answers "should I hold this instead of an index", which is the right question
for a product and the wrong one for a claim about a signal, because two books
can both beat the market for the same reason and neither of them be the reason.

On 2026-08-25 that gap became load-bearing. `profit_roe` at k=100 returned
+2.56%/yr excess over the market with `t`=2.79 and needed 31.2 years against a
30.88-year window — the closest anything in this project has come to being
resolvable. But the null `equal` returned +1.12%/yr at the same breadth, and
`equal` is not equal-weighting: with every score tied, `top_k` falls through to
permno order, so it is *the hundred oldest surviving listings*. High-ROE names
in a large-cap universe are old names — CL, CLX, AVP, LMT, UST, MHP are among
the most venerable listings in CRSP. **Roughly 44% of the excess was matched by
a book selected on listing age alone.**

Comparing each book's excess-over-market cannot settle that, because those two
excesses are not independent: they share the market, they share the
construction, and they overlap in holdings. The quantity that decides it is the
tracking error of the DIFFERENCE, and nothing computed it.

WHAT THIS DOES
==============
Runs the signal and the benchmark at the SAME construction — same holding
period, same `top_k`, same sizing, same phase — and power-checks the signal's
daily returns against the BENCHMARK POLICY's daily returns instead of the
market's. No new statistics: `power_check` already accepts any benchmark
series. What is new is refusing to let the market be the only comparator.

The phase is matched pairwise and never pooled. A signal book at phase 0 and a
benchmark book at phase 3 rebalance on different days, so their difference
would carry the calendar as well as the signal — the 3.75x phase spread this
farm has already paid for says how large that contamination can be.

READING IT
==========
  `te`        annualised tracking error of the signal book vs the BENCHMARK BOOK
  `excess`    annualised return difference, signal minus benchmark
  `t`         excess / standard error
  `mde80`     the difference this window could have detected at 80% power
  `resolves`  excess > mde80

`resolves=False` here is a stronger negative than `resolves=False` against the
market, because a paired comparison cancels the shared construction drag and
should therefore be the EASIER test. A signal that cannot clear its benchmark
book after that cancellation has not been shown to be about its own quantity.

This is a diagnostic under the `PRODUCT_EXPERIMENT` licence. It prices one
alternative explanation; it does not license a claim.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from backend.services.portfolio_farm import (bootstrap as B, farm,  # noqa: E402
                                             panel as P, signals as SIG)
from backend.services.portfolio_farm.policy import Policy  # noqa: E402

HOLDING_DAYS = 5
SIZING = "inverse_vol"
#: A null benchmark is one draw of an arbitrary book, so it gets several seeds
#: and the median one is used. `equal` is deterministic and takes only seed 0.
NULL_SEEDS = 12
#: Below a year of overlap a paired power check reports a number it cannot
#: support, so the pair is dropped rather than reported.
MIN_PAIRED_SESSIONS = 250


def _median_run(results, key=lambda r: r.metrics["terminal_usd"]):
    ok = [r for r in results if r.metrics.get("status") == "ok"]
    if not ok:
        return None
    ok.sort(key=key)
    return ok[len(ok) // 2]


def paired_returns(lead, bench):
    """Daily returns of two books over the sessions they BOTH have.

    Aligning on DATES rather than on length is the whole point. Two books at
    the same phase can still start on different sessions — a signal with a
    warm-up (`mom_12_1` needs a year, `value_bm` needs a `public_date` to have
    passed) forfeits leading rows that a null does not. Slicing by length would
    then subtract Tuesday from Wednesday for the whole history and report the
    calendar as an effect.

    Returns None when under a year of sessions overlap.
    """
    s_dates = np.asarray(lead.dates)
    s_nav = np.asarray(lead.nav, dtype=np.float64)
    b_dates = np.asarray(bench.dates)
    b_nav = np.asarray(bench.nav, dtype=np.float64)
    common = np.intersect1d(s_dates, b_dates)
    if len(common) < MIN_PAIRED_SESSIONS:
        return None
    return (B.daily_returns(s_nav[np.isin(s_dates, common)]),
            B.daily_returns(b_nav[np.isin(b_dates, common)]))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--start", type=int, default=1993)
    ap.add_argument("--end", type=int, default=2024)
    ap.add_argument("--reduce", action="store_true")
    ap.add_argument("--signal", required=True)
    ap.add_argument("--benchmark", required=True,
                    help="another signal name, or 'market'")
    ap.add_argument("--top-k", type=int, default=100)
    ap.add_argument("--holding-days", type=int, default=HOLDING_DAYS)
    a = ap.parse_args(argv)

    for s in (a.signal, a.benchmark):
        if s != "market" and s not in SIG.SIGNALS:
            raise SystemExit(f"unknown signal {s!r}; known: {sorted(SIG.SIGNALS)}")

    pan = P.load_panel(a.start, a.end,
                       reduce_for_universe_n=(500 if a.reduce else None))
    h = a.holding_days

    def build(name: str) -> list[Policy]:
        seeds = (range(NULL_SEEDS)
                 if name in SIG.NULL_SIGNALS and name != "equal" else (0,))
        return [Policy(signal=name, holding_days=h, top_k=a.top_k,
                       sizing=SIZING, phase_offset=p, signal_seed=k)
                for p in range(h) for k in seeds]

    pols = build(a.signal) + ([] if a.benchmark == "market" else build(a.benchmark))
    res = farm.run_many(pan, pols, progress=False)

    sig_by_phase: dict[int, list] = {}
    ben_by_phase: dict[int, list] = {}
    for r in res:
        if r.metrics.get("status") != "ok":
            continue
        bucket = sig_by_phase if r.policy.signal == a.signal else ben_by_phase
        bucket.setdefault(r.policy.phase_offset, []).append(r)

    print(f"PAIRED POWER — {a.start}-{a.end}, h={h} k={a.top_k} {SIZING}")
    print(f"  panel {pan.shape[0]:,} sessions x {pan.shape[1]:,} permnos")
    print(f"  {a.signal}  vs  {a.benchmark}   "
          f"(same construction, phase matched pairwise)\n")

    mkt_all = P.market_benchmark(pan.dates) if a.benchmark == "market" else None

    per_phase = []
    for phase in sorted(sig_by_phase):
        lead = _median_run(sig_by_phase[phase])
        if lead is None:
            continue
        s_dates, s_nav = np.asarray(lead.dates), np.asarray(lead.nav, float)
        sr = B.daily_returns(s_nav)
        if a.benchmark == "market":
            w0 = len(pan.dates) - len(lead.dates)
            br = np.where(np.isfinite(mkt_all[w0:]), mkt_all[w0:], np.nan)
            ben_terminal = float("nan")
        else:
            bl = _median_run(ben_by_phase.get(phase, []))
            if bl is None:
                continue
            # align on DATES, not on length: a phase can lose leading sessions
            # to a signal's own warm-up, and two books that start on different
            # days are not a paired comparison however similar the lengths are.
            pair = paired_returns(lead, bl)
            if pair is None:
                continue
            sr, br = pair
            ben_terminal = float(bl.metrics["terminal_usd"])
        pw = B.power_check(sr, br)
        if pw.get("status") != "ok":
            continue
        per_phase.append({"phase": phase,
                          "signal_terminal_usd": float(lead.metrics["terminal_usd"]),
                          "benchmark_terminal_usd": ben_terminal,
                          **pw})

    if not per_phase:
        raise SystemExit("no phase produced a comparable pair")

    hdr = (f"{'phase':>5} {'signal$':>12} {'bench$':>12} {'te%':>7} "
           f"{'excess%':>8} {'t':>6} {'mde80%':>7}  resolves")
    print(hdr)
    print("-" * len(hdr))
    for r in per_phase:
        print(f"{r['phase']:>5} {r['signal_terminal_usd']:>12,.0f} "
              f"{r['benchmark_terminal_usd']:>12,.0f} "
              f"{r['tracking_error_annual_pct']:>7.2f} "
              f"{r['observed_excess_annual_pct']:>8.2f} "
              f"{r['implied_t']:>6.2f} "
              f"{r['mde_at_80pct_power_annual_pct']:>7.2f}  "
              f"{r['sample_can_resolve_observed_effect']}")

    # the MEDIAN phase by paired excess, so the headline is a property of the
    # rule and not of the calendar alignment that happened to be tried
    per_phase.sort(key=lambda r: r["observed_excess_annual_pct"])
    med = per_phase[len(per_phase) // 2]
    ts = [r["implied_t"] for r in per_phase]
    exc = [r["observed_excess_annual_pct"] for r in per_phase]
    n_res = sum(bool(r["sample_can_resolve_observed_effect"]) for r in per_phase)

    print(f"\n  MEDIAN PHASE (phase {med['phase']}) — this is the headline")
    for k in ("years", "tracking_error_annual_pct", "observed_excess_annual_pct",
              "implied_t", "mde_at_80pct_power_annual_pct",
              "years_needed_for_observed_effect",
              "sample_can_resolve_observed_effect"):
        print(f"     {k:<42s} {med.get(k)}")
    print(f"\n  across {len(per_phase)} phases: excess "
          f"[{min(exc):+.2f}, {max(exc):+.2f}]%/yr, t [{min(ts):+.2f}, "
          f"{max(ts):+.2f}], {n_res}/{len(per_phase)} resolve")

    if n_res == 0:
        print(f"\n  NOT RESOLVED. `{a.signal}` has not been shown to beat "
              f"`{a.benchmark}` at this\n  construction, and a paired test is "
              f"the EASIER one — it cancels the drag\n  both books share. An "
              f"excess over the market that does not survive this\n  is not "
              f"evidence about {a.signal}; it is evidence about the two books "
              f"together.")
    elif n_res == len(per_phase):
        print(f"\n  RESOLVED AT EVERY PHASE. `{a.signal}` clears `{a.benchmark}` "
              f"by more than this\n  window's detection threshold regardless of "
              f"calendar alignment. That prices\n  ONE alternative explanation. "
              f"It is not a holdout and it is not a claim.")
    else:
        print(f"\n  PHASE-DEPENDENT: {n_res} of {len(per_phase)} phases resolve. "
              f"Treat as UNRESOLVED —\n  a result that needs a particular "
              f"rebalance day is a calendar artefact until\n  shown otherwise.")

    path = farm.save({"check": "paired_power", "window": [a.start, a.end],
                      "signal": a.signal, "benchmark": a.benchmark,
                      "top_k": a.top_k, "holding_days": h, "sizing": SIZING,
                      "reduced": bool(a.reduce), "phases": per_phase,
                      "median_phase": med, "n_phases_resolving": n_res},
                     f"farm_paired_{a.signal}_vs_{a.benchmark}_k{a.top_k}"
                     f"_{a.start}_{a.end}")
    print(f"\n  written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
