"""Branch every decision in his book and roll them forward on real prices.

Answers the SOC question mechanically: at the moment a position has run a long
way, what observable separates the winners worth holding from the winners worth
harvesting? No LLM, so no temporal leakage.

    python scripts/run_counterfactual_exits.py

Writes docs/conviction_replay/counterfactual_exits.json.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd

from backend.services.conviction_prices import load_prices, price_on
from backend.services.conviction_replay import MDE_Z
from backend.services.counterfactual_replay import (BRANCHES, INTERPOLATING,
                                                    build_decisions,
                                                    effective_sample,
                                                    separating_power)
from backend.services.conviction_sheets import load_sheet

logger = logging.getLogger(__name__)
OUT = ROOT / "docs" / "conviction_replay"

ENTRY, END = "2025-11-07", "2026-08-10"
#: Month-ends with at least three months of forward path left. A decision date
#: too close to the end grades a branch on a window that has barely opened.
DECISION_DATES = ["2025-12-01", "2026-01-02", "2026-02-02", "2026-03-02",
                  "2026-04-01", "2026-05-01"]
#: `pct_of_peak` is 1 + `drawdown_from_peak` — the same feature twice. Testing
#: both would report one result as two and inflate any count of how many
#: observables separate.
FEATURES = ("gain_since_entry", "drawdown_from_peak", "return_1m", "return_3m",
            "vol_3m_annual", "run_up_from_trough")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    t0 = time.time()
    prices = load_prices()
    sheet = load_sheet(ENTRY)

    holdings = {}
    for h in sheet.portfolio:
        p = price_on(prices, h.ticker, ENTRY)
        if p is not None:
            holdings[h.ticker] = p
    logger.info("branching %d positions over %d decision dates",
                len(holdings), len(DECISION_DATES))

    rows = build_decisions(prices, holdings, DECISION_DATES, END)
    eff = effective_sample(rows)
    logger.info("%d rows, %d distinct names, effective n for inference = %d",
                eff["n_rows"], eff["n_distinct_names"],
                eff["effective_n_for_inference"])

    wins = Counter(r.best_branch for r in rows)
    means = {b: float(np.mean([r.outcomes[b] for r in rows if b in r.outcomes]))
             for b in BRANCHES}
    for b in sorted(means, key=means.get, reverse=True):
        n = sum(1 for r in rows if b in r.outcomes)
        tag = " (interpolating: cannot win a max, by construction)"             if b in INTERPOLATING else ""
        logger.info("  %-24s mean terminal %.3f   best in %3d of %3d rows%s",
                    b, means[b], wins.get(b, 0), n, tag)

    # ── the SOC question ──
    big = [r for r in rows if r.state["gain_since_entry"] > 0.5]
    big_hold = float(np.mean([r.outcomes["hold"] for r in big])) if big else None
    big_sell = (float(np.mean([r.outcomes["sell_to_benchmark"] for r in big]))
                if big else None)
    big_take = (float(np.mean([r.outcomes["take_original_out"] for r in big]))
                if big else None)

    seps = [separating_power(rows, f) for f in FEATURES]
    for s in sorted(seps, key=lambda s: -abs(s.get(
            "correlation_with_hold_minus_sell") or 0)):
        if s.get("verdict") == "TOO_FEW":
            logger.info("  %-22s TOO_FEW", s["feature"])
            continue
        logger.info("  %-22s corr %+.3f  p %.3f  MDE %.3f  -> %s", s["feature"],
                    s["correlation_with_hold_minus_sell"], s["p_value"],
                    s["mde_correlation_80pct_power"], s["verdict"])
    found = [s for s in seps if s.get("detectable")]

    payload = {
        "trial": "COUNTERFACTUAL-EXITS-1",
        "status": "EXPLORE / OBSERVATIONAL — a hypothesis generator, never a "
                  "fitted policy. Every branch is one realised path.",
        "leakage": ("none possible: no model is involved, only arithmetic on "
                    "prices that already happened. This is the half of the "
                    "market-laboratory proposal that CAN be run honestly today "
                    "(CANON §13 — masking the name is not masking the date)."),
        "window": [ENTRY, END], "decision_dates": DECISION_DATES,
        "branches": list(BRANCHES),
        "effective_sample": eff,
        "mean_terminal_value_per_dollar": means,
        "times_each_branch_was_best": {
            k: v for k, v in wins.items() if k not in INTERPOLATING},
        "win_counts_omitted_for": {
            "branches": list(INTERPOLATING),
            "why": ("each is a convex combination of hold and sell_to_cash, so "
                    "it can never exceed both and its win count is a theorem "
                    "rather than a result. Their MEANS are reported and are "
                    "meaningful."),
        },
        "the_soc_question": {
            "definition": "rows where the position was already up more than 50%",
            "n_rows": len(big),
            "n_names": len({r.ticker for r in big}),
            "mean_hold": big_hold,
            "mean_sell_to_benchmark": big_sell,
            "mean_take_original_out": big_take,
            "hold_minus_sell": (big_hold - big_sell
                                if big_hold is not None else None),
            "reading": (
                "the average big winner was worth holding" if big_hold and big_sell
                and big_hold > big_sell else
                "the average big winner was worth rotating"),
        },
        "separating_features": seps,
        "n_features_that_separate": len(found),
        "verdict": (
            "NO_OBSERVABLE_SEPARATES_AT_THIS_SAMPLE" if not found else
            "CANDIDATE_OBSERVABLES_FOR_FORWARD_TEST"),
        "may_not_conclude": [
            "that any of these branches is a policy — one path, one regime",
            "that a stop-loss is rehabilitated; CANON §15 stands",
            "any money claim",
        ],
        "runtime_secs": round(time.time() - t0, 1),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "counterfactual_exits.json").write_text(
        json.dumps(payload, indent=1, default=str), encoding="utf-8")
    logger.info("=" * 72)
    logger.info("VERDICT: %s", payload["verdict"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
