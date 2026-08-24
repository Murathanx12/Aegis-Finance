"""Run the portfolio farm over CRSP daily and print the leaderboard.

    python -m scripts.portfolio_farm_run --start 2010 --end 2024
    python -m scripts.portfolio_farm_run --start 2015 --end 2019 --preset holding
    python -m scripts.portfolio_farm_run --preset micron   # the holding-period question

PRESETS
=======
`holding`  — THE MICRON QUESTION. One signal, six holding periods (1, 5, 21,
             63, 126, 252 sessions), at real costs and again at zero costs. The
             pair is the answer: the gap between them IS the cost of trading
             fast, and a 1-day book that wins frictionless and loses net has
             answered the question in the only way that matters.
`signals`  — every registered signal at one holding period, with both nulls.
`breadth`  — top_k from 3 to 50 at ONE rebalance offset. Fast, and its levels
             are a draw; use `breadth_phase` to rank k for real.
`breadth_phase` — k crossed with the rebalance PHASE. The run that settles
             breadth, because a k-ranking read off one offset ranks draws.
`phase`    — every offset in each rebalance cycle, reported by MEDIAN.
`delisting` — the delisting FALLBACK swept 0.0 / -0.30 / -1.0. With
             `crsp.dsedelist` joined this should move the answer barely at all;
             if it moves a lot, the join has stopped working.
`full`     — the cross product. Hundreds of policies; minutes, not hours.

NOTHING HERE IS A CLAIM. See `farm.py` — the leaderboard prints its own nulls
and its own policy count, and a farm winner is a candidate for a frozen forward
book, never evidence of alpha.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.services.portfolio_farm import farm, panel as P  # noqa: E402
from dataclasses import replace  # noqa: E402

from backend.services.portfolio_farm.policy import Policy, grid  # noqa: E402

ALL_SIGNALS = ["mom_12_1", "mom_6_1", "mom_3_1", "mom_12_0", "reversal_1m",
               "reversal_1w", "low_vol", "high_vol", "trend_200", "size_small",
               "size_large", "illiquid", "liquid",
               "random", "random_persistent", "equal"]
HOLDINGS = [1, 5, 21, 63, 126, 252]

#: Phases sampled per rebalance cycle in the `phase` preset. Seven is enough
#: for a median to mean something and small enough that a 252-session cycle
#: does not turn into 252 policies.
MAX_PHASES = 7


#: How many independent random draws accompany every run. Twenty is enough to
#: place a real signal at a percentile with a straight face and cheap enough
#: that no preset can plead cost for running without a control.
NULL_SEEDS = 20


def null_bench(**kw) -> list[Policy]:
    """The control, at the SAME settings as the policies it controls."""
    return ([Policy(signal="random", signal_seed=s,
                    note="null control — chance, MAXIMUM turnover", **kw)
             for s in range(NULL_SEEDS)]
            + [Policy(signal="random_persistent", signal_seed=s,
                      note="null control — chance, NEAR-ZERO turnover", **kw)
               for s in range(NULL_SEEDS)]
            + [Policy(signal="equal", **kw)])


def build(preset: str) -> list[Policy]:
    if preset == "holding":
        real = grid(signal=["mom_12_1", "reversal_1m"], holding_days=HOLDINGS)
        for h in HOLDINGS:
            real += null_bench(holding_days=h)
        # The frictionless twin must differ from its parent in COSTS ONLY.
        # The first version rebuilt each twin from `signal` and `holding_days`
        # alone and dropped `signal_seed`, so twenty-one "independent" random
        # draws came back as twenty-one copies of seed 0 — visible in the first
        # run as twenty-one identical $43,068 rows, which is what a collapsed
        # null looks like when nothing raises. `replace` copies the whole
        # record, so a field added later cannot be silently lost the same way.
        free = [replace(p, transaction_cost_bps=0.0, slippage_bps=0.0,
                        zero_cost_diagnostic=True,
                        note="frictionless twin — the gap IS the cost of speed")
                for p in real]
        return real + free
    if preset == "signals":
        return (grid(signal=[s for s in ALL_SIGNALS if s not in ("random",)],
                     holding_days=[21]) + null_bench(holding_days=21))
    if preset == "breadth":
        sizings = ["equal_weight", "inverse_vol"]
        out = grid(signal=["mom_12_1"], top_k=[3, 5, 10, 20, 50],
                   sizing=sizings)
        # A null bench per (top_k, sizing). The first version benched only the
        # default sizing, so every inverse-vol policy was scored against
        # nothing — invisible while the comparison pooled groups, and printed
        # as `nan` the moment it stopped.
        for k in (3, 5, 10, 20, 50):
            for sz in sizings:
                out += null_bench(top_k=k, sizing=sz)
        return out
    if preset == "full":
        out = grid(signal=[s for s in ALL_SIGNALS
                           if s not in ("random", "random_persistent")],
                   holding_days=[5, 21, 63], top_k=[5, 12, 30],
                   sizing=["equal_weight", "inverse_vol"])
        for h in (5, 21, 63):
            out += null_bench(holding_days=h, top_k=12)
        return out
    if preset == "breadth_phase":
        # THE RUN THAT SETTLES BREADTH. `breadth` sweeps k at ONE rebalance
        # offset, and the phase sweep showed an offset is worth up to 3.75x —
        # so a k-ranking read off one phase is a ranking of draws. This crosses
        # k with the phase, at a holding period the phase sweep found strong
        # (h=5), and benches every (k, sizing) cell against its own nulls.
        ks, sizings, h = [5, 10, 20, 50], ["equal_weight", "inverse_vol"], 5
        out = []
        for k in ks:
            for sz in sizings:
                for ph in range(min(h, MAX_PHASES)):
                    out += grid(signal=["mom_12_1"], holding_days=[h],
                                top_k=[k], sizing=[sz], phase_offset=[ph])
                out += null_bench(holding_days=h, top_k=k, sizing=sz)
        return out
    if preset == "delisting":
        # BOUND THE ASSUMPTION. `crsp.dsf` carries no delisting returns, so the
        # simulator applies a declared one (-0.30, the Shumway (1997) order of
        # magnitude) to any holding that vanishes. An assumption nobody has
        # varied is indistinguishable from a fact, so this runs the two best
        # holding periods at the two ENDPOINTS as well: 0.0 (a delisting costs
        # nothing — the naive, optimistic case every backtest that ignores the
        # problem is silently running) and -1.0 (total loss).
        #
        # Phases are swept too, because at k=12 the phase spread is 1.8x-3.8x
        # and a sensitivity read off one phase would be measuring the calendar.
        out = []
        for h in (1, 5, 63):
            for dr in (0.0, -0.30, -1.0):
                for ph in range(min(h, MAX_PHASES)):
                    out += grid(signal=["mom_12_1"], holding_days=[h],
                                phase_offset=[ph], delisting_return=[dr])
            out += null_bench(holding_days=h)
        return out
    if preset == "phase":
        # THE DE-CONFOUNDED MICRON ANSWER. Every offset inside each rebalance
        # cycle (capped at MAX_PHASES so a 252-session cycle does not become
        # 252 policies), so the answer is the MEDIAN over alignments instead of
        # whichever one the loop happened to start on.
        out = []
        for h in HOLDINGS:
            for ph in range(min(h, MAX_PHASES)):
                out += grid(signal=["mom_12_1", "reversal_1m"],
                            holding_days=[h], phase_offset=[ph])
            out += null_bench(holding_days=h)
        return out
    raise SystemExit(f"unknown preset {preset!r}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    # Defaults are the REPLAYABLE window, not the on-disk one. See
    # panel.replayable_years: the 1990-2012 CRSP pulls lack openprc/retx/shrout,
    # so a wider default would refuse on every invocation.
    ap.add_argument("--start", type=int, default=2013)
    ap.add_argument("--end", type=int, default=2024)
    ap.add_argument("--reduce", action="store_true",
                    help="build the panel from the liquidity-reduced permno "
                         "set (identical NAVs, ~half the memory; REQUIRED for "
                         "windows longer than ~15 years)")
    ap.add_argument("--preset", default="holding",
                    choices=["holding", "signals", "breadth", "full",
                             "phase", "delisting", "breadth_phase"])
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--name", default=None, help="output file stem")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    policies = build(a.preset)
    print(f"PORTFOLIO FARM  preset={a.preset}  window={a.start}-{a.end}  "
          f"policies={len(policies)}")
    usable = P.replayable_years()
    if usable:
        print(f"replayable CRSP window on this host: "
              f"{usable[0]}-{usable[-1]} ({len(usable)} years)")
    pan = P.load_panel(a.start, a.end, reduce_for_universe_n=(500 if a.reduce else None))
    print(f"panel: {pan.shape[0]} sessions x {pan.shape[1]} permnos "
          f"({pan.dates[0]} -> {pan.dates[-1]})")

    results = farm.run_many(pan, policies)
    rep = farm.rank_report(results, top=a.top)
    rep["window"] = [a.start, a.end]
    rep["preset"] = a.preset
    rep["panel"] = {"sessions": int(pan.shape[0]), "permnos": int(pan.shape[1]),
                    "first": str(pan.dates[0]), "last": str(pan.dates[-1]),
                    "source": pan.source}
    out = farm.save(rep, a.name or f"farm_{a.preset}_{a.start}_{a.end}")

    print()
    hdr = (f"{'terminal$':>10} {'CAGR%':>7} {'maxDD%':>8} {'Sharpe':>7} "
           f"{'turn/yr':>8} {'cost$':>7}  policy")
    print(hdr)
    print("-" * len(hdr))
    for r in rep["top"]:
        flag = " [NULL]" if r.get("is_null_control") else ""
        print(f"{r['terminal_usd']:>10,.0f} {r['cagr_pct']:>7.2f} "
              f"{r['max_drawdown_pct']:>8.1f} "
              f"{(r['sharpe'] if r['sharpe'] is not None else float('nan')):>7.2f} "
              f"{r.get('turnover_annual', float('nan')):>8.2f} "
              f"{r.get('total_cost_usd', 0):>7.0f}  {r['label']}{flag}")
    print()
    b = rep.get("benchmark_terminal_usd")
    print(f"  market (CRSP VW, buy & hold)      : "
          f"${b:,.0f}" if b else "  market: unavailable")
    if rep["best_real"]:
        print(f"  best non-null policy              : "
              f"${rep['best_real']['terminal_usd']:,.0f}  "
              f"{rep['best_real']['label']}")
    if rep["best_null"]:
        print(f"  best NULL (random/equal) policy   : "
              f"${rep['best_null']['terminal_usd']:,.0f}  "
              f"{rep['best_null']['label']}")
    nd = rep.get("null_distribution") or {}
    if nd.get("n"):
        print(f"  null spread over {nd['n']:>2} random draws  : "
              f"${nd['min']:,.0f} .. p10 ${nd['p10']:,.0f} .. "
              f"med ${nd['median']:,.0f} .. p90 ${nd['p90']:,.0f} .. "
              f"${nd['max']:,.0f}")
        print(f"  best real sits at PERCENTILE      : "
              f"{rep.get('best_real_percentile_in_null')}  of chance")
    else:
        print("  NULL DISTRIBUTION                 : NONE RAN — nothing here "
              "has a control")
    print(f"  best beats one null draw          : {rep['beats_own_null']}")
    print(f"  best beats the market             : {rep['beats_market']}")
    print(f"  policies tried                    : {rep['n_policies']}  "
          f"(the best of N is high because N is large — this is a RANKING, "
          f"not a finding)")
    comp = sorted(farm.compare_within_groups(results),
                  key=lambda c: (c['group'].get('holding_days') or 0,
                                 c['group'].get('top_k') or 0,
                                 str(c['group'].get('sizing')),
                                 -c['terminal_usd']))
    rep["per_policy_vs_own_null"] = comp
    farm.save(rep, a.name or f"farm_{a.preset}_{a.start}_{a.end}")
    if comp:
        print()
        print("EACH REAL POLICY vs THE NULLS AT ITS OWN SETTINGS")
        h2 = (f"{'policy':<40} {'terminal$':>10} "
              f"{'turn/yr':>8} {'nullHi$':>9} {'nullLo$':>9} "
              f"{'pctHi':>6} {'pctLo':>6} {'both':>5}")
        print(h2)
        print("-" * len(h2))
        for c in comp:
            ph = c["percentile_vs_hi_turnover_null"]
            pl = c["percentile_vs_lo_turnover_null"]
            print(f"{c['label']:<40} {c['terminal_usd']:>10,.0f} "
                  f"{(c.get('turnover_annual') or 0):>8.1f} "
                  f"{(c['null_hi_turnover_median_usd'] or 0):>9,.0f} "
                  f"{(c['null_lo_turnover_median_usd'] or 0):>9,.0f} "
                  f"{(ph if ph is not None else float('nan')):>6} "
                  f"{(pl if pl is not None else float('nan')):>6} "
                  f"{('YES' if c['clears_BOTH_nulls'] else 'no'):>5}")
        print()
        print("  pctHi / pctLo = percentile inside the terminal-wealth "
              "spread CHANCE produced at")
        print("  the same settings, against the HIGH-turnover null (re-draws "
              "every date) and the")
        print("  LOW-turnover null (one fixed random basket). Beating only "
              "pctHi at a short holding")
        print("  period can mean nothing more than 'traded less than a coin "
              "flip would'.")
        print("  `both` = clears the 90th percentile of BOTH. That is the "
              "bar.")
    ph = [r for r in farm.across_phases(results) if r["n_phases"] > 1]
    if ph:
        rep["across_phases"] = farm.across_phases(results)
        farm.save(rep, a.name or f"farm_{a.preset}_{a.start}_{a.end}")
        print()
        print("ACROSS REBALANCE PHASES — the median is the RULE, the spread "
              "is the CALENDAR")
        h3 = (f"{'signal':<13} {'hold':>5} {'n':>3} {'median$':>10} "
              f"{'min$':>10} {'max$':>10} {'max/min':>8}  {'cost':<5}")
        print(h3)
        print("-" * len(h3))
        for r in sorted(ph, key=lambda x: (x["signal"], x["holding_days"])):
            if r["is_null_control"]:
                continue
            print(f"{r['signal']:<13} {r['holding_days']:>5} "
                  f"{r['n_phases']:>3} {r['terminal_median_usd']:>10,.0f} "
                  f"{r['terminal_min_usd']:>10,.0f} "
                  f"{r['terminal_max_usd']:>10,.0f} "
                  f"{(r['phase_spread_ratio'] or 0):>8.2f}  "
                  f"{'FREE' if r['zero_cost_diagnostic'] else 'net':<5}")
        print()
        print("  max/min is how much of the answer is the CALENDAR rather than "
              "the rule. A rule")
        print("  whose phase spread is wider than its edge has not been shown "
              "to have one.")
    print(f"\n  written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
