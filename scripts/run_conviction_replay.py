"""CONVICTION-REPLAY-1 — run the decomposition and issue the registered verdict.

Pre-registered in `Aegis module/TRIALS/PREREG_CONVICTION_REPLAY_1.md`, corpse-lint
PASS against 307 priors, decision rule frozen before any forward return of either
group was computed.

    python scripts/run_conviction_replay.py

Writes docs/conviction_replay/conviction_replay_1.json.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np

from backend.services.conviction_prices import (CORPORATE_ACTIONS,
                                                SHEET_ENTRY_FALLBACK,
                                                load_prices, path_stats,
                                                synthetic_names)
from backend.services.conviction_replay import (MDE_Z, basket, exit_audit,
                                                measure_mde, permutation_test,
                                                rank_alternative,
                                                tie_aware_basket,
                                                up_down_capture)
from backend.services.conviction_sheets import load_sheet

logger = logging.getLogger(__name__)
OUT = Path(__file__).resolve().parents[1] / "docs" / "conviction_replay"

START, END = "2025-11-07", "2026-08-10"
REBAL, BENCHMARKS = "2026-01-13", ("SPY", "QQQ", "IWM", "XBI", "SMH")


def verdict_for(diff: float, p: float, mde: float | None) -> tuple[str, str]:
    """The rule as registered in §3. Written before the numbers existed."""
    if mde is None:
        return ("UNRESOLVED_UNPOWERED",
                "no planted effect on the grid reached 80% power: this design "
                "cannot reliably detect ANY selection edge. A null from it is a "
                "statement about the design, not about him (CANON §19).")
    sig = p < 0.05
    if diff >= mde and sig:
        return ("SELECTION_INFORMATION_PRESENT",
                f"his picks beat his own non-picks by {100*diff:+.1f} pts "
                f"against an MDE of {100*mde:.1f} (p {p:.3f}) — above the "
                f"threshold at which this design finds effects reliably. "
                f"Layer 1: it licenses a forward test, not capital.")
    if diff <= -mde and sig:
        return ("SELECTION_PERVERSE",
                f"his picks UNDERPERFORMED his own non-picks by "
                f"{100*diff:+.1f} pts against an MDE of {100*mde:.1f} "
                f"(p {p:.3f}).")
    if sig:
        return ("UNRESOLVED_SIGNIFICANT_BELOW_MDE",
                f"{100*diff:+.1f} pts at p {p:.3f}, but below the MDE of "
                f"{100*mde:.1f}. Significant findings below their own MDE "
                f"systematically overstate themselves; this is where the "
                f"winner's curse lives and it may not be promoted.")
    return ("UNRESOLVED_ABSENCE_OF_EVIDENCE",
            f"{100*diff:+.1f} pts, p {p:.3f}, MDE {100*mde:.1f}. The design "
            f"cannot see an effect of this size. This is absence of evidence "
            f"and may NOT be recorded as a kill or as a finding about his "
            f"skill (CANON §19).")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    t0 = time.time()
    prices = load_prices()
    sheet = load_sheet("2025-11-07")

    picks = [h.ticker for h in sheet.portfolio]
    nonpicks = [h.ticker for h in sheet.non_picks()]
    pool = picks + nonpicks
    logger.info("pool: %d picks, %d non-picks, window %s..%s",
                len(picks), len(nonpicks), START, END)

    b_pick = basket(prices, picks, START, END, "his picks")
    b_non = basket(prices, nonpicks, START, END, "his non-picks")
    b_all = basket(prices, pool, START, END, "the whole pool")

    pr = np.array([b_pick.per_name[t] for t in b_pick.members])
    nr = np.array([b_non.per_name[t] for t in b_non.members])

    logger.info("picks  %+.1f%%  (n %d)", 100 * b_pick.mean_return, b_pick.n)
    logger.info("non    %+.1f%%  (n %d)", 100 * b_non.mean_return, b_non.n)

    test = permutation_test(pr, nr)
    allr = np.concatenate([pr, nr])
    power = measure_mde(allr, k=len(pr))
    mde = power["mde_at_80pct_power"]

    # Sensitivity to the two names whose entry price comes from HIS SHEET rather
    # than a feed. They pull in opposite directions — APLT is his worst holding,
    # SLNO a watchlist winner — so dropping both is not a neutral simplification
    # and the difference has to be shown, not asserted to be small.
    synth = synthetic_names()
    pr_x = np.array([b_pick.per_name[t] for t in b_pick.members if t not in synth])
    nr_x = np.array([b_non.per_name[t] for t in b_non.members if t not in synth])
    test_x = permutation_test(pr_x, nr_x)
    sensitivity = {
        "excluding_reconstructed_names": {
            "dropped": sorted(synth),
            "n_picks": len(pr_x), "n_non_picks": len(nr_x),
            "picks_mean": float(pr_x.mean()), "non_picks_mean": float(nr_x.mean()),
            "difference": test_x["observed_difference"],
            "p_value_two_sided": test_x["p_value_two_sided"],
        },
        "difference_moved_by": (test["observed_difference"]
                                - test_x["observed_difference"]),
        "verdict_changes": bool(
            (test["p_value_two_sided"] < 0.05)
            != (test_x["p_value_two_sided"] < 0.05)),
    }
    logger.info("sensitivity: dropping %s moves the difference by %+.1f pts "
                "(verdict changes: %s)", sorted(synth),
                100 * sensitivity["difference_moved_by"],
                sensitivity["verdict_changes"])
    verdict, reading = verdict_for(test["observed_difference"],
                                   test["p_value_two_sided"], mde)
    logger.info("difference %+.1f pts  p %.4f  MDE %s  -> %s",
                100 * test["observed_difference"], test["p_value_two_sided"],
                f"{100*mde:.1f}" if mde else "unreachable", verdict)

    # ── the comparison that decides whether the spreadsheet did the work ──
    alternatives = {}
    for key in ("sheet_upside", "consensus_rating"):
        ranking = rank_alternative(sheet.holdings, key, len(picks))
        tb = tie_aware_basket(prices, ranking, START, END, key)
        chosen = set(ranking["strict"]) | set(ranking["tied_at_cutoff"])
        alternatives[key] = {
            **tb, "cutoff": ranking["cutoff"],
            "n_strictly_above_cutoff": len(ranking["strict"]),
            "overlap_with_his_picks": len(chosen & set(picks)),
            "his_picks_minus_this_rule": b_pick.mean_return - tb["mean_return"],
        }
        logger.info("top-%d by %-17s %+.1f%%  [tie-break 5-95: %s]  strict %d "
                    "of %d  real ranking: %s", len(picks), key,
                    100 * tb["mean_return"],
                    f"{100*tb['tie_break_p05']:+.1f}..{100*tb['tie_break_p95']:+.1f}"
                    if tb["tie_break_p05"] is not None else "none",
                    len(ranking["strict"]), len(picks), tb["is_a_real_ranking"])

    bench = {}
    for bm in BENCHMARKS:
        b = basket(prices, [bm], START, END, bm)
        bench[bm] = b.mean_return
        logger.info("%-5s %+.1f%%", bm, 100 * b.mean_return)

    # ── H3: the rebalance, an independent second draw on the same skill ──
    jan = load_sheet(REBAL)
    jan_picks = {h.ticker for h in jan.portfolio}
    promoted = sorted(jan_picks - set(picks))
    demoted = sorted(set(picks) - jan_picks)
    b_prom = basket(prices, promoted, REBAL, END, "promoted")
    b_dem = basket(prices, demoted, REBAL, END, "demoted")
    reb_test = None
    if b_prom.n >= 3 and b_dem.n >= 3:
        reb_test = permutation_test(
            np.array([b_prom.per_name[t] for t in b_prom.members]),
            np.array([b_dem.per_name[t] for t in b_dem.members]), n_perm=20_000)
    logger.info("rebalance: promoted %+.1f%% (n %d) vs demoted %+.1f%% (n %d)",
                100 * b_prom.mean_return, b_prom.n,
                100 * b_dem.mean_return, b_dem.n)

    # ── H2 exits, H4 capture, and the per-name path ──
    exits = exit_audit(prices, REBAL, END)
    signs = {e["verdict"] for e in exits}
    capture = {
        "his_picks": up_down_capture(prices, picks, START, END),
        "his_non_picks": up_down_capture(prices, nonpicks, START, END),
        "whole_pool": up_down_capture(prices, pool, START, END),
    }
    paths = {t: path_stats(prices, t, START, END) for t in pool}
    held = {t: p for t, p in paths.items() if t in picks and p}
    worst = sorted(held.items(), key=lambda kv: kv[1]["total_return"])[:3]
    best = sorted(held.items(), key=lambda kv: -kv[1]["total_return"])[:3]
    captures = [p["capture_of_best"] for p in held.values()
                if p["capture_of_best"] is not None]

    payload = {
        "trial": "CONVICTION-REPLAY-1",
        "prereg": "Aegis module/TRIALS/PREREG_CONVICTION_REPLAY_1.md",
        "status": "EXPLORE / OBSERVATIONAL — designed after seeing the history, "
                  "so it can never be confirmation of it",
        "accrues_to_denominator": 1,
        "window": [START, END],
        "data_note": ("equal-weighted baskets from actual adjusted closes. His "
                      "sheets carry no share counts, no cash and no "
                      "transactions, so NONE of these numbers is his return, "
                      "and the +73.7% vs '2025 +115%' gap is NOT reconciled "
                      "here — the inputs to settle it are not in the repo."),
        "corporate_actions": {k: vars(v) for k, v in CORPORATE_ACTIONS.items()},
        "reconstructed_entry_prices": SHEET_ENTRY_FALLBACK,
        "sensitivity_to_reconstructed_names": sensitivity,
        "primary": {
            "hypothesis": "H1 — his picks beat the non-picks he drew them from",
            "picks": {"n": b_pick.n, "mean": b_pick.mean_return,
                      "median": b_pick.median_return, "members": b_pick.members},
            "non_picks": {"n": b_non.n, "mean": b_non.mean_return,
                          "median": b_non.median_return},
            "whole_pool": {"n": b_all.n, "mean": b_all.mean_return},
            "test": test,
            "power": power,
            "mde_at_80pct_power": mde,
            "verdict": verdict,
            "reading": reading,
        },
        "alternative_rankings": alternatives,
        "benchmarks": bench,
        "rebalance_h3": {
            "promoted": promoted, "demoted": demoted,
            "promoted_mean": b_prom.mean_return, "demoted_mean": b_dem.mean_return,
            "from": REBAL, "test": reb_test,
            "note": ("an independent second draw on the same skill, two months "
                     "later, from the same pool"),
        },
        "exits_h2": {
            "rows": exits,
            "sign_is_uniform": len(signs) == 1,
            "registered_prediction": "the sign is NOT uniform across his exits",
            "prediction_held": len(signs) > 1,
        },
        "capture_h4": capture,
        "position_paths": {
            "best_three_held": [{"ticker": t, **v} for t, v in best],
            "worst_three_held": [{"ticker": t, **v} for t, v in worst],
            "median_capture_of_best_move": (
                float(np.median(captures)) if captures else None),
            "note": ("capture_of_best is the fraction of the best available "
                     "move a buy-and-hold kept; it turns 'I sold too early' "
                     "into a measurement"),
        },
        "may_not_conclude": [
            "that he has or lacks selection skill — one window, 13 names",
            "that his style should be copied into production",
            "that any corpse is reopened",
            "any money claim, Sharpe, or half-life",
        ],
        "runtime_secs": round(time.time() - t0, 1),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "conviction_replay_1.json").write_text(
        json.dumps(payload, indent=1, default=str), encoding="utf-8")

    logger.info("=" * 72)
    logger.info("VERDICT: %s", verdict)
    logger.info("%s", reading)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
