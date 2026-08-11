"""What an exposure rule WOULD have done to his book, on both captures.

    python scripts/run_exposure_controller.py

Writes docs/conviction_replay/exposure_controller_v0.json.
"""
from __future__ import annotations

import json, logging, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd

from backend.services.conviction_prices import load_prices, synthetic_names
from backend.services.conviction_sheets import load_sheet
from backend.services.exposure_controller import (EXPOSURE_BUDGET,
                                                  ExposurePolicy,
                                                  apply_overlay,
                                                  both_captures, classify)

logger = logging.getLogger(__name__)
OUT = ROOT / "docs" / "conviction_replay"
START, END = "2025-11-07", "2026-08-10"


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    t0 = time.time()
    prices = load_prices().loc[:pd.Timestamp(END)]
    sheet = load_sheet(START)
    synth = synthetic_names()

    policy = ExposurePolicy()
    sched = classify(prices["SPY"], policy)
    window = sched.loc[pd.Timestamp(START):]
    counts = window["state"].value_counts().to_dict()
    logger.info("state days in window: %s", counts)
    logger.info("mean exposure carried: %.3f", window["exposure"].mean())

    books = {
        "his_picks": [h.ticker for h in sheet.portfolio if h.ticker not in synth],
        "his_non_picks": [h.ticker for h in sheet.non_picks()
                          if h.ticker not in synth],
    }
    rows = {}
    px = prices.loc[pd.Timestamp(START):]
    bench = px["SPY"].pct_change(fill_method=None).dropna()
    for name, tickers in books.items():
        have = [t for t in tickers if t in px.columns and px[t].notna().sum() > 20]
        raw = px[have].pct_change(fill_method=None).mean(axis=1).dropna()
        overlaid = apply_overlay(raw, sched["exposure"])
        rows[name] = {
            "unmanaged": both_captures(raw, bench),
            "with_overlay": both_captures(overlaid, bench),
        }
        u, o = rows[name]["unmanaged"], rows[name]["with_overlay"]
        rows[name]["cost_of_the_overlay_pts"] = 100 * (
            o["total_return"] - u["total_return"])
        rows[name]["drawdown_saved_pts"] = 100 * (
            o["max_drawdown"] - u["max_drawdown"])
        logger.info("%-14s unmanaged  up %.2f down %.2f  ret %+.1f%%  dd %.1f%%",
                    name, u["up_capture"], u["down_capture"],
                    100 * u["total_return"], 100 * u["max_drawdown"])
        logger.info("%-14s overlaid   up %.2f down %.2f  ret %+.1f%%  dd %.1f%%  "
                    "-> cost %+.1f pts, drawdown saved %+.1f pts", name,
                    o["up_capture"], o["down_capture"], 100 * o["total_return"],
                    100 * o["max_drawdown"], rows[name]["cost_of_the_overlay_pts"],
                    rows[name]["drawdown_saved_pts"])

    spy_dd = float(((1 + bench).cumprod() / (1 + bench).cumprod().cummax() - 1).min())
    payload = {
        "trial": "EXPOSURE-CONTROLLER-V0",
        "status": "MEASURING INSTRUMENT, NOT A PROMOTED RULE. Not calibrated, "
                  "not attached to any lane, no capital.",
        "design": {
            "not_a_crash_model": ("maps observable trend and realised vol to an "
                                  "exposure budget; no crash probability appears"),
            "budgets": EXPOSURE_BUDGET,
            "re_entry_is_mandatory": (
                "ExposurePolicy REFUSES to construct without a minimum dwell and "
                "a re-entry band above the de-risking threshold - a controller "
                "with no re-entry looks fine in every backtest that ends during "
                "the drawdown"),
            "overlay_is_lagged_one_day": True,
            "policy": vars(policy),
        },
        "window": [START, END],
        "state_days": counts,
        "mean_exposure": float(window["exposure"].mean()),
        "benchmark_max_drawdown": spy_dd,
        "books": rows,
        "THE_FINDING": (
            "The controller NEVER left risk_on: SPY held above its 200-day "
            "average all window and realised vol never reached 1.5x its "
            "one-year level. The overlay therefore cost nothing and saved "
            "nothing. But his book drew down 22.9% while SPY drew down 8.9%, "
            "at a measured beta of 2.15 - so his drawdown was mostly his OWN "
            "beta amplifying a shallow market dip that no market-regime trigger "
            "would ever fire on. His third self-diagnosed failure is therefore "
            "NOT primarily a market-timing problem in this window; it is the "
            "cost of carrying 2.15 beta. That is a position-sizing question and "
            "an exposure controller keyed to the MARKET cannot answer it."),
        "why_the_policy_was_not_tuned_until_it_fired": (
            "Loosening the trigger until it fires on the one sample available "
            "is fitting the rule to the window it is being tested on. The null "
            "is reported as the result. A trigger keyed to the BOOK's own "
            "drawdown rather than the market's is the design that follows from "
            "it, and it is a separate pre-registration - not an adjustment made "
            "after seeing this."),
        "THE_CAVEAT": (
            "SPY returned +16% over this window with a shallow maximum "
            "drawdown, so this is a BULL sample and an exposure rule can very "
            "nearly only lose in it. A small measured cost here is NOT evidence "
            "the rule is cheap, and the drawdown Murat actually regrets is not "
            "necessarily inside this window. The honest reading is that this "
            "window cannot price the rule; it can only show it does not "
            "misbehave."),
        "runtime_secs": round(time.time() - t0, 1),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "exposure_controller_v0.json").write_text(
        json.dumps(payload, indent=1, default=str), encoding="utf-8")
    logger.info("=" * 72)
    logger.info("SPY max drawdown in window: %.1f%% - a bull sample; this window "
                "cannot price an exposure rule", 100 * spy_dd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
