"""Does the edge survive if we hold LONGER? The cheapest attack on §59.

    python -m scripts.night_horizon_sweep --survivorship-free

THE HYPOTHESIS
==============
`NEGATIVE_RESULTS.md` §59 closed price/volume at 21 sessions with one pair of
numbers: the ordering earns **+0.28% gross** and the round trip costs
**~35 bps**. The edge is 28 bps and the toll is 35.

But the toll is paid PER ROUND TRIP, not per day. Hold the same names for 63
sessions and you pay 35 bps once across three times the horizon. So:

    net(H) = gross(H) - toll          where toll is ~constant in H

If the signal is slow-moving -- size, profitability, low skew are all
slow-moving -- then `gross(H)` should grow with H faster than the toll does,
because the toll barely grows at all. There is a horizon at which the same
ordering, with no new data and no new model, stops losing money.

That is the claim. It might be wrong: `gross(H)` could flatten if the signal
decays inside 21 sessions, in which case a longer hold buys drift and noise and
nothing else. Either answer is worth having, and it costs one run over a panel
already on disk.

WHY THIS IS THE FIRST THING TO TRY
==================================
Every other route out of §59 needs something we do not have: fundamentals need a
data pull, event features need a collector, a better model needs a reason to
believe a fifth one differs from four. This needs nothing. It re-labels the same
panel at four horizons and asks the same question four times.

Score: P(changes the roadmap) is high -- a positive answer reopens a closed
family and changes what the live loop is allowed to hold. Cost is one CPU hour.

WHAT IS HELD FIXED
==================
The same features, the same folds, the same purge rule, the same cost model,
the same breadth sweep. ONLY the horizon moves. A comparison in which two things
moved cannot attribute the difference to either.

The purge scales WITH the horizon. At H=126 the labels overlap 125 days, so a
21-day purge would leak five months of outcomes into training -- the exact
defect that makes a backtest look brilliant and lose money. `PURGE = H` is not a
detail here, it is the whole validity of the longer-horizon cells.

TURNOVER, STATED HONESTLY
=========================
A 63-session hold rebalances a third as often as a 21-session hold, so it pays
the toll a third as often -- but it also gets a third as many independent bets.
The receipt reports BOTH the net edge per holding period and the net edge per
YEAR, because a strategy that earns 1% per 126 sessions is not better than one
earning 0.5% per 21 sessions, and the per-period number alone makes it look it.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import warnings
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import xs_ranker as XR      # noqa: E402

OUT = REPO / "backend" / "data" / "optimus" / "xs_ranker"

#: 21 is the incumbent. 42/63 are the plausible wins. 126 is there to show the
#: shape: if the curve is still rising at 126 the signal is slower than anyone
#: thought, and if it peaks at 63 that is the answer.
HORIZONS = (21, 42, 63, 126)
BREADTH_K = (20, 50, 100, 200)
#: Sessions per year, for turning a per-holding-period number into a per-year
#: one. A per-period edge at a long horizon flatters itself otherwise.
SESSIONS_PER_YEAR = 252


def _block(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s).dt.to_period("M").astype(str)


#: Signs declared before any fold, from the cross-sectional literature -- the
#: `composite_prior` of `night_rank_bakeoff`. It is the ONLY model §59 found
#: gross-POSITIVE (+0.20% to +0.28% at every k from 10 to 500), and the first
#: version of this sweep tested LightGBM-on-all-features instead, which §59 had
#: already shown was the WORST of four (gross -0.30%). Sweeping the losing model
#: across horizons answers a question nobody asked.
PRIOR_SIGNS: dict[str, float] = {
    "dollar_vol_log": -1.0, "amihud": +1.0, "skew_63": -1.0, "rev_5": -1.0,
}


def _composite_score(te: pd.DataFrame) -> pd.Series:
    """Signed z-score mean. No fitted parameters, so nothing to overfit."""
    parts = []
    for f, sign in PRIOR_SIGNS.items():
        if f not in te.columns:
            continue
        g = te.groupby("date")[f]
        z = ((te[f] - g.transform("mean")) / g.transform("std")).clip(-3, 3)
        parts.append(z * sign)
    if not parts:
        return pd.Series(np.nan, index=te.index)
    return pd.concat(parts, axis=1).mean(axis=1)


def run_one(bars: pd.DataFrame, horizon: int, *, n_folds: int = 4,
            model: str = "lgbm") -> dict:
    """One horizon, everything else held fixed. `model` is lgbm or composite."""
    import lightgbm as lgb

    panel = XR.build_panel(bars, horizon=horizon)
    fit = panel[panel["eligible"] & panel["y"].notna()].copy()
    if fit.empty:
        return {"horizon": horizon, "status": "REFUSED", "why": "no labelled rows"}

    # The purge MUST scale with the horizon. At H=126 the labels overlap 125
    # days; a 21-day purge would leak five months of outcomes into training.
    saved_purge = XR.PURGE_SESSIONS
    XR.PURGE_SESSIONS = horizon
    try:
        folds = XR.make_folds(fit["date"].values, n_folds=n_folds)
    finally:
        XR.PURGE_SESSIONS = saved_purge
    if not folds:
        return {"horizon": horizon, "status": "REFUSED",
                "why": f"no fold survives a {horizon}-session purge"}

    feats = list(XR.FEATURES)
    preds = []
    for tr_end, te_start, te_end in folds:
        tr = fit[fit["date"] <= tr_end]
        te = fit[(fit["date"] >= te_start) & (fit["date"] <= te_end)]
        if len(tr) < XR.MIN_TRAIN_ROWS or te.empty:
            continue
        p = te[["symbol", "date", "fwd_rel", "median_dollar_vol"]].copy()
        if model == "composite":
            p["score"] = _composite_score(te).values
            p = p.dropna(subset=["score"])
        else:
            m = lgb.LGBMRegressor(**XR.LGB_PARAMS)
            m.fit(tr[feats], tr["y"])
            p["score"] = m.predict(te[feats])
        if p.empty:
            continue
        preds.append(p)
    if not preds:
        return {"horizon": horizon, "status": "REFUSED", "why": "every fold refused"}

    oos = pd.concat(preds, ignore_index=True)
    ic = XR._information_coefficient(oos)
    cells = {}
    for k in BREADTH_K:
        bt = XR.top_k_backtest(oos, k=k)
        if bt.get("mean_net_rel_21d") is None:
            continue
        net, gross = bt["mean_net_rel_21d"], bt["mean_gross_rel_21d"]
        periods = SESSIONS_PER_YEAR / horizon
        cells[k] = {
            "gross_per_hold": gross, "net_per_hold": net,
            "cost_bps": bt["mean_cost_bps"],
            # The honest comparison: a 1% edge per 126 sessions is NOT better
            # than 0.5% per 21, and the per-period number alone makes it look it.
            "net_per_year": net * periods,
            "gross_per_year": gross * periods,
            "t_across_blocks": bt.get("t_across_blocks"),
            "hit_rate": bt["hit_rate_dates"], "n_blocks": bt["n_blocks"],
        }
    return {"horizon": horizon, "status": "OK", "model": model,
            "n_oos_rows": int(len(oos)),
            "n_folds_used": len(preds), **ic, "by_k": cells,
            "purge_sessions": horizon}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--survivorship-free", action="store_true")
    ap.add_argument("--bars", default=None)
    ap.add_argument("--folds", type=int, default=4)
    ap.add_argument("--horizons", default=",".join(str(h) for h in HORIZONS))
    ap.add_argument("--model", default="lgbm", choices=("lgbm", "composite"),
                    help="`composite` is the prior-signed z-score mean -- the only "
                         "model §59 found gross-POSITIVE, and the one this sweep "
                         "should have tested first.")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)

    if a.survivorship_free:
        paths = XR.survivorship_free_paths()
        print("panels: " + ", ".join(p.name for p in paths))
        bars = XR.load_bars(paths)
    else:
        bars = XR.load_bars(Path(a.bars) if a.bars else None)
    audit = XR.survivorship_audit(bars)
    print(f"survivorship: {audit['verdict'][:90]}")

    horizons = [int(h) for h in a.horizons.split(",") if h.strip()]
    rows = {}
    for h in horizons:
        print(f"\n--- horizon {h} sessions (purge {h}) ---", flush=True)
        r = run_one(bars, h, n_folds=a.folds, model=a.model)
        rows[h] = r
        if r.get("status") != "OK":
            print(f"  {r['status']}: {r.get('why')}")
            continue
        print(f"  IC {r['ic_mean']:+.4f} (t {(r.get('ic_t') or float('nan')):+.2f}), "
              f"{r['n_oos_rows']:,} OOS rows")
        for k, c in r["by_k"].items():
            print(f"   k={k:<4} gross {c['gross_per_hold']*100:+6.2f}%/hold "
                  f"net {c['net_per_hold']*100:+6.2f}%/hold  ->  "
                  f"net {c['net_per_year']*100:+6.2f}%/yr  "
                  f"(cost {c['cost_bps']:.0f}bps, t {(c['t_across_blocks'] or float('nan')):+.2f})")

    # the verdict compares ANNUALISED net, which is the only comparable number
    best = None
    for h, r in rows.items():
        for k, c in (r.get("by_k") or {}).items():
            if best is None or c["net_per_year"] > best[2]:
                best = (h, k, c["net_per_year"], c["net_per_hold"],
                        c["t_across_blocks"], c["gross_per_hold"])
    verdict = "CANNOT DETERMINE: no horizon produced a book"
    if best:
        h, k, per_yr, per_hold, t, gross = best
        incumbent = ((rows.get(21) or {}).get("by_k") or {}).get(20, {}).get("net_per_year")
        if per_yr > 0:
            verdict = (
                f"HORIZON HELPS: the best cell is H={h} at k={k}, "
                f"{per_hold*100:+.2f}% net per hold = {per_yr*100:+.2f}%/yr "
                f"(gross {gross*100:+.2f}%, t {t:+.2f}). Incumbent H=21 k=20 was "
                f"{(incumbent or 0)*100:+.2f}%/yr. Holding longer pays the same toll "
                f"over more time, and this says the signal outlives the extra days.")
        else:
            verdict = (
                f"HORIZON DOES NOT RESCUE IT: the best cell anywhere is H={h} k={k} "
                f"at {per_yr*100:+.2f}%/yr, still negative. The edge does not grow "
                f"with the holding period faster than the signal decays, so the "
                f"28-vs-35 bps problem is not a turnover problem. §59 stands and "
                f"the next move is a different INPUT, not a different holding rule.")

    res = {"receipt": "horizon_sweep", "model": a.model,
           "licence": "PRODUCT_EXPERIMENT",
           "llm_spend_usd": 0.0,
           "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "hypothesis": ("§59's toll is paid per ROUND TRIP, not per day. If the "
                          "signal is slow-moving, gross(H) should grow with H "
                          "faster than the ~constant toll, and some H turns the "
                          "same ordering profitable with no new data."),
           "held_fixed": ["features", "folds", "cost model", "breadth k",
                          "universe"],
           "purge_rule": "PURGE = H, so long-horizon cells are not leaking",
           "survivorship": audit, "horizons": rows, "verdict": verdict,
           "read_me_first": ("Compare the PER-YEAR column, never the per-hold one: "
                             "a 1% edge per 126 sessions is not better than 0.5% "
                             "per 21, and the per-hold number alone makes it look it.")}
    OUT.mkdir(parents=True, exist_ok=True)
    # The model goes in the FILENAME. Without it, sweeping a second model on the
    # same day silently overwrites the first one's receipt, and the comparison
    # the two runs exist to make becomes unreadable from disk.
    out = (Path(a.out) if a.out else
           OUT / f"horizon_sweep_{a.model}_{date.today()}.json")
    out.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(f"\nVERDICT: {verdict}")
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
