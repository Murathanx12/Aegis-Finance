"""Does a farm candidate survive when the window is cut in half?

    python -m scripts.portfolio_farm_subperiod

WHY THIS IS SEPARATE FROM THE PRESETS
=====================================
Every number the farm has produced comes from ONE window, 2013-2024, and one
price path. Twelve years feels long and is one regime: the whole span is a bull
market interrupted twice. A rule fitted to nothing can still be a rule that only
works in the half of history where its factor happened to pay.

So this splits the replayable window and runs the candidate — and its nulls —
in each half independently, at every rebalance phase. It is not a holdout (the
candidate was chosen after seeing the full window, so nothing here is
out-of-sample in the strict sense) and it is not preregistered. It is the
cheapest available check on the most obvious way the result could be an
accident: **if the edge lives entirely in one half, the twelve-year number is an
average of a thing and a nothing.**

Reported per half: the median across phases, the worst phase, and how many
phases clear BOTH nulls. The bar is the same as everywhere else in the farm.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


from backend.services.portfolio_farm import farm, panel as P  # noqa: E402
from backend.services.portfolio_farm.policy import Policy, grid  # noqa: E402

#: The candidate, and the two nulls at its exact settings.
CANDIDATE = dict(signal="mom_12_1", holding_days=5, top_k=10,
                 sizing="inverse_vol")
N_SEEDS = 20


def policies() -> list[Policy]:
    out = grid(**{k: [v] for k, v in CANDIDATE.items()},
               phase_offset=list(range(CANDIDATE["holding_days"])))
    base = {k: v for k, v in CANDIDATE.items() if k != "signal"}
    for s in range(N_SEEDS):
        out.append(Policy(signal="random", signal_seed=s, **base))
        out.append(Policy(signal="random_persistent", signal_seed=s, **base))
    return out


def run_half(start: int, end: int, reduce: bool = False) -> dict:
    pan = P.load_panel(start, end,
                       reduce_for_universe_n=(500 if reduce else None))
    res = farm.run_many(pan, policies(), progress=False)
    ph = [r for r in farm.across_phases(res) if not r["is_null_control"]]
    comp = farm.compare_within_groups(res)
    bench = next((r.as_row().get("benchmark_terminal_usd") for r in res
                  if r.metrics.get("benchmark_terminal_usd") is not None), None)
    real = ph[0] if ph else {}
    return {
        "window": [start, end],
        "sessions": int(pan.shape[0]),
        "benchmark_terminal_usd": bench,
        "median_usd": real.get("terminal_median_usd"),
        "worst_phase_usd": real.get("terminal_min_usd"),
        "best_phase_usd": real.get("terminal_max_usd"),
        "phase_spread": real.get("phase_spread_ratio"),
        "n_phases": real.get("n_phases"),
        "phases_clearing_both": sum(1 for c in comp if c["clears_BOTH_nulls"]),
        "phases_total": len(comp),
        "worst_phase_beats_market": (
            None if not (real.get("terminal_min_usd") and bench)
            else bool(real["terminal_min_usd"] > bench)),
        "median_beats_market": (
            None if not (real.get("terminal_median_usd") and bench)
            else bool(real["terminal_median_usd"] > bench)),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--halves", default="2013:2018,2019:2024",
                    help="comma-separated start:end pairs")
    ap.add_argument("--reduce", action="store_true",
                    help="liquidity-reduced panel (identical NAVs, half the memory)")
    a = ap.parse_args(argv)
    label = "/".join(f"{k}={v}" for k, v in CANDIDATE.items())
    print(f"SUB-PERIOD CHECK — {label}\n")
    hdr = (f"{'window':<12} {'sess':>5} {'median$':>10} {'worst$':>10} "
           f"{'best$':>10} {'market$':>10} {'clear':>7} {'worst>mkt':>10}")
    print(hdr)
    print("-" * len(hdr))
    out = []
    for pair in a.halves.split(","):
        s, e = (int(x) for x in pair.split(":"))
        r = run_half(s, e, reduce=a.reduce)
        out.append(r)
        print(f"{s}-{e:<7} {r['sessions']:>5} {(r['median_usd'] or 0):>10,.0f} "
              f"{(r['worst_phase_usd'] or 0):>10,.0f} "
              f"{(r['best_phase_usd'] or 0):>10,.0f} "
              f"{(r['benchmark_terminal_usd'] or 0):>10,.0f} "
              f"{r['phases_clearing_both']}/{r['phases_total']:<5} "
              f"{str(r['worst_phase_beats_market']):>10}")
    print()
    print("  Not a holdout — the candidate was chosen after seeing the whole")
    print("  window, so neither half is out-of-sample. It answers only the")
    print("  cheapest question: does the edge live in one half?")
    path = farm.save({"check": "subperiod", "candidate": CANDIDATE,
                      "halves": out}, "farm_subperiod_candidate")
    print(f"\n  written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
