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
`breadth`  — top_k from 3 to 50: concentration as a declared personality axis.
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
        out = grid(signal=["mom_12_1"], top_k=[3, 5, 10, 20, 50],
                   sizing=["equal_weight", "inverse_vol"])
        for k in (3, 5, 10, 20, 50):
            out += null_bench(top_k=k)
        return out
    if preset == "full":
        out = grid(signal=[s for s in ALL_SIGNALS
                           if s not in ("random", "random_persistent")],
                   holding_days=[5, 21, 63], top_k=[5, 12, 30],
                   sizing=["equal_weight", "inverse_vol"])
        for h in (5, 21, 63):
            out += null_bench(holding_days=h, top_k=12)
        return out
    raise SystemExit(f"unknown preset {preset!r}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    # Defaults are the REPLAYABLE window, not the on-disk one. See
    # panel.replayable_years: the 1990-2012 CRSP pulls lack openprc/retx/shrout,
    # so a wider default would refuse on every invocation.
    ap.add_argument("--start", type=int, default=2013)
    ap.add_argument("--end", type=int, default=2024)
    ap.add_argument("--preset", default="holding",
                    choices=["holding", "signals", "breadth", "full"])
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
    pan = P.load_panel(a.start, a.end)
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
    comp = farm.compare_within_groups(results)
    rep["per_policy_vs_own_null"] = comp
    farm.save(rep, a.name or f"farm_{a.preset}_{a.start}_{a.end}")
    if comp:
        print()
        print("EACH REAL POLICY vs THE NULLS AT ITS OWN SETTINGS")
        h2 = (f"{'hold':>5} {'cost':>5} {'signal':<13} {'terminal$':>10} "
              f"{'turn/yr':>8} {'nullHi$':>9} {'nullLo$':>9} "
              f"{'pctHi':>6} {'pctLo':>6} {'both':>5}")
        print(h2)
        print("-" * len(h2))
        for c in comp:
            g = c["group"]
            ph = c["percentile_vs_hi_turnover_null"]
            pl = c["percentile_vs_lo_turnover_null"]
            print(f"{g.get('holding_days', '?'):>5} "
                  f"{'FREE' if g.get('zero_cost_diagnostic') else 'net':>5} "
                  f"{c['signal']:<13} {c['terminal_usd']:>10,.0f} "
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
    print(f"\n  written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
