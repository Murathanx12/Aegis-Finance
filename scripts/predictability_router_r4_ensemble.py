"""R1 side lane -- the EQUAL-WEIGHT RANK ENSEMBLE that fell out of the router.

The router needed an honest comparator for "pick the best engine per name", and
the honest comparator for that is "use all of them, equally, with no choice at
all".  The comparator beat everything it was there to measure, so it gets its
own receipt rather than a sentence in someone else's.

WHAT THIS IS AND IS NOT.  It is POST-HOC: nobody pre-registered it, it was found
while building a control, and it is charged to a family that is enumerated here.
It is not a claim; the alpha ruler has not been run on it, no forward paper
exists, and one window is one window.  It is reported because the repo's
standing bottleneck is that ten books select on ONE signal, and the cheapest
observation in this lane is that averaging four existing engines' cross-sectional
RANKS -- adding no new information at all -- moves the top-50 book far more than
any of the four does on its own, while leaving the average rank IC unchanged.

That last clause is the interesting one and it is why this is not just "an
ensemble is better": the ensemble's rank IC (0.098) is NOT higher than the best
single engine's (0.100).  The gain is entirely at the TOP of the ordering, which
is the only part a top-k book ever touches.

Licence: PRODUCT_EXPERIMENT.  Costs never zero.  Nothing here trades.
"""

from __future__ import annotations

import json
import time

import numpy as np
import pandas as pd
from scipy import stats

from learner import evaluate as ev
from scripts.predictability_router_r1 import (
    ENGINES, OUT, ROUTER_ERAS, TEST_START_YEAR, _log, beta_first, bh_fdr,
    build_panel, deflated_sharpe, holm, paired,
)


def main() -> None:
    t0 = time.time()
    d = build_panel()
    d["ew_rank"] = np.nanmean(d[[f"_u_{e}" for e in ENGINES]].to_numpy(), axis=1)
    d = d[d["month"] >= f"{TEST_START_YEAR}-01"].copy()

    # THE FAMILY, ENUMERATED BEFORE THE RESULTS (invariant 16).
    ks = [25, 50, 100]
    weights = ["vw", "ew", "rank"]
    costs = [10.0, 25.0]
    family = [(k, w, c) for k in ks for w in weights for c in costs]
    r: dict = {
        "lane": "R1_SIDE_EW_RANK_ENSEMBLE",
        "licence": "PRODUCT_EXPERIMENT",
        "provenance": "POST-HOC. Found as the control arm for engine routing in "
                      "stage two; never pre-registered.",
        "generated_utc": pd.Timestamp.utcnow().isoformat(),
        "window": {"months": int(d["month"].nunique()),
                   "min": str(d["month"].min()), "max": str(d["month"].max())},
        "signal": "mean of the four engines' cross-sectional percentile ranks; "
                  "no new information, no fitting, no weights to choose",
        "engines": ENGINES,
        "family": {"cells": len(family), "k": ks, "weight": weights,
                   "cost_bps_per_side": costs},
    }

    # rank IC of the ensemble and of each engine -- the point of the lane
    ic = {}
    for c in ENGINES + ["ew_rank"]:
        s = ev.monthly_ic_series(d, c, "excess_vw_1m")
        ic[c] = {"months": int(len(s)), "mean_rank_ic": round(float(s.mean()), 5),
                 "t_across_months": round(float(s.mean() / (s.std(ddof=1) / np.sqrt(len(s)))), 3)}
    r["rank_ic"] = ic

    # the books
    _log("books ...")
    cells, series = {}, {}
    for (k, w, c) in family:
        b = ev.book(d, "ew_rank", k=k, weight=w, cost_bps=c, with_risk=True,
                    return_series=True)
        key = f"ew_rank|k={k}|{w}|{int(c)}bps"
        net, mkt = b["_series"]["net"], b["_series"]["market"]
        series[key] = net
        cells[key] = {"grade": beta_first(net, mkt),
                      "mean_turnover": b["mean_turnover"],
                      "vs_market": paired(net, mkt, f"{key} minus market")}
    r["cells"] = cells

    pv = {k: v["grade"]["alpha_p_two_sided"] for k, v in cells.items()
          if v["grade"].get("alpha_p_two_sided") is not None}
    r["multiplicity"] = {"family_size": len(pv),
                         "family_max_p": round(max(pv.values()), 5),
                         "family_min_p": round(min(pv.values()), 5),
                         "holm_export": holm(pv),
                         "bh_fdr_screen_q10": bh_fdr(pv, 0.10)}

    # the pre-declared headline cell: the house default (k=50, vw, 10 bps)
    key = "ew_rank|k=50|vw|10bps"
    r["headline_cell"] = key
    r["dsr"] = deflated_sharpe(
        series[key], n_trials=len(pv),
        trial_sharpes=[float(s.mean() / s.std(ddof=1)) for s in series.values()])

    # single engines under the same construction, for the "better than what?"
    r["single_engines_same_construction"] = {}
    for e in ENGINES:
        b = ev.book(d, e, k=50, weight="vw", cost_bps=10.0, return_series=True)
        r["single_engines_same_construction"][e] = {
            "grade": beta_first(b["_series"]["net"], b["_series"]["market"]),
            "vs_ensemble": paired(series[key], b["_series"]["net"],
                                  f"ensemble minus {e}"),
        }

    # three eras
    _log("eras ...")
    net = series[key]
    mkt = ev.book(d, "ew_rank", k=50, weight="vw", return_series=True)["_series"]["market"]
    r["eras"] = {}
    idx = np.asarray(net.index.astype(str))
    for name, (lo, hi) in ROUTER_ERAS.items():
        m = (idx >= lo) & (idx <= hi)
        if m.sum() < 6:
            continue
        r["eras"][name] = {"grade": beta_first(net[m], mkt[m]),
                           "vs_market": paired(net[m], mkt[m], f"{name} vs market")}

    # the execution floor, because a book of unbuyable names is a backtest of
    # something unbuyable (`learner.evaluate.TRADABLE_DOLLAR_VOL`)
    bf = ev.book(d, "ew_rank", k=50, weight="vw",
                 tradable_floor=ev.TRADABLE_DOLLAR_VOL, return_series=True)
    r["with_execution_floor_3m_per_day"] = {
        "grade": beta_first(bf["_series"]["net"], bf["_series"]["market"]),
        "rows_after_floor": bf["rows_after_tradable_floor"],
        "mean_turnover": bf["mean_turnover"]}

    r["runtime_seconds"] = round(time.time() - t0, 1)
    p = OUT / "R1_side_ensemble_receipt.json"
    p.write_text(json.dumps(r, indent=1, default=str), encoding="utf-8")
    _log(f"receipt -> {p}")


if __name__ == "__main__":
    main()
