"""Murat's hypothesis: stops get hunted. Large holders push price through the
obvious level, retail sells into it, and the buyer on the other side is the one
who pushed it.

    python -m scripts.night_stop_hunt --survivorship-free

WHY THIS IS A REAL HYPOTHESIS AND NOT FOLKLORE
==============================================
It makes a sharp, falsifiable prediction that ordinary price behaviour does not.

Under a RANDOM WALK, a position that touches -2% intraday has no particular
future. Its expected return from the touch to any later date is about zero, and
the stop merely converts an unrealised mark into a realised loss -- costing the
spread and nothing else.

Under STOP HUNTING, the touch is not information about the business; it is the
mechanical consequence of someone clearing out resting sell orders. The price
should then RECOVER, and on average the position that was stopped should be
worth more at the horizon than the stop level it was sold at.

So the test is one number:

    recovery = (return if you had HELD) - (return you got by STOPPING)

averaged over the positions that were actually stopped. A random walk says
zero. Stop hunting says positive, and says it should be LARGER for tighter
stops, because a tighter level is a more obvious and more crowded one.

WHAT WOULD MAKE IT FALSE, AND IS EQUALLY WORTH KNOWING
======================================================
If `recovery` is NEGATIVE, then a -2% touch is genuine information -- the market
learned something and kept selling -- and the stop was doing its job even though
it lost money on average. That would mean §62's result ("all eleven exit rules
lose to holding") is about the SELECTOR being weak rather than about stops being
hunted, and the remedy would be different.

Both answers change what we do, which is what makes it worth the CPU.

THE MEASUREMENT IS PAIRED, WHICH IS WHAT MAKES IT CLEAN
=======================================================
Every stopped position is compared against ITSELF -- the same name, the same
entry date, the same window, the one counterfactual where the only thing that
changed is the exit rule. There is no cross-sectional control to get wrong, no
benchmark to compound incorrectly (2026-09-24, where a daily-rebalanced
equal-weight index compounded at +35%/yr and made every arm look identical), and
no survivorship question, because both arms hold the same instrument.

The one thing that MUST be right is the fill convention, and it is inherited
from `night_exit_rules`: the stop triggers on the session LOW, a gap below the
level fills at the OPEN, and a session touching both a stop and a target
resolves to the stop. Those were each checked by hand and are pinned by tests.
"""

from __future__ import annotations

import argparse
import json
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

from backend.services import xs_ranker as XR              # noqa: E402
from scripts.night_exit_rules import (                    # noqa: E402
    _entry_index, _paths_by_symbol, composite_score, walk_one)

OUT = REPO / "backend" / "data" / "optimus" / "xs_ranker"

#: Tighter levels are more obvious and more crowded, so if hunting is real the
#: recovery should be LARGEST at the tight end. A flat profile across levels
#: would argue for something else -- ordinary volatility drag, say.
STOPS = (0.02, 0.03, 0.05, 0.08)


def run(oos: pd.DataFrame, paths: dict, *, k: int, horizon: int,
        stop: float) -> dict:
    """Per stopped position: what the stop got, and what holding would have."""
    rows = []
    for d, grp in oos.groupby("date"):
        top = grp.nlargest(k, "score")
        if len(top) < k:
            continue
        for sym in top["symbol"]:
            p = paths.get(sym)
            if p is None:
                continue
            i = _entry_index(p, np.datetime64(pd.Timestamp(d), "ns"))
            if i is None:
                continue
            r_stop, held, why = walk_one(p, i, horizon, stop=stop)
            if not np.isfinite(r_stop) or not why.startswith("stop"):
                continue                      # only positions that WERE stopped
            r_hold, _, _ = walk_one(p, i, horizon)
            if not np.isfinite(r_hold):
                continue
            rows.append({"date": str(pd.Timestamp(d).date()), "symbol": sym,
                         "stopped_at": r_stop, "would_have": r_hold,
                         "recovery": r_hold - r_stop,
                         "held_sessions": held,
                         "gapped": why.endswith("_gap")})
    if not rows:
        return {"stop": stop, "status": "REFUSED", "why": "nothing was stopped"}

    d = pd.DataFrame(rows)
    rec = d["recovery"].to_numpy()
    years = pd.Series([r[:4] for r in d["date"]])
    by_year = {y: float(rec[(years == y).values].mean()) for y in sorted(years.unique())}
    loo = {y: float(rec[(years != y).values].mean())
           for y in sorted(years.unique()) if (years != y).sum() > 20}
    # Block by month so the standard error is not counting overlapping windows
    # as independent -- the defect corrected in `top_k_backtest` on 2026-09-24.
    bm = pd.Series(rec).groupby(pd.Series([r[:7] for r in d["date"]])).mean()
    se = float(bm.std(ddof=1) / np.sqrt(len(bm))) if len(bm) > 1 else float("nan")
    return {
        "stop": stop, "status": "OK", "n_stopped": int(len(d)),
        "n_symbols": int(d.symbol.nunique()),
        "mean_stop_return": float(d["stopped_at"].mean()),
        "mean_hold_return": float(d["would_have"].mean()),
        "mean_recovery": float(rec.mean()),
        "median_recovery": float(np.median(rec)),
        "share_recovered": float((rec > 0).mean()),
        "mean_held_sessions": float(d["held_sessions"].mean()),
        "gapped_share": float(d["gapped"].mean()),
        "t_across_months": float(bm.mean() / se) if np.isfinite(se) and se > 0 else None,
        "n_months": int(len(bm)),
        "by_year": by_year,
        "loo_worst": min(loo.values()) if loo else None,
        "loo_worst_dropped": min(loo, key=loo.get) if loo else None,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--survivorship-free", action="store_true")
    ap.add_argument("--k", type=int, default=50)
    ap.add_argument("--horizon", type=int, default=XR.HORIZON_SESSIONS)
    ap.add_argument("--folds", type=int, default=4)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)

    bars = (XR.load_bars(XR.survivorship_free_paths()) if a.survivorship_free
            else XR.load_bars())
    panel = XR.build_panel(bars, horizon=a.horizon)
    fit = panel[panel["eligible"] & panel["y"].notna()].copy()
    saved = XR.PURGE_SESSIONS
    XR.PURGE_SESSIONS = a.horizon
    try:
        folds = XR.make_folds(fit["date"].values, n_folds=a.folds)
    finally:
        XR.PURGE_SESSIONS = saved

    preds = []
    for _tr_end, te_start, te_end in folds:
        te = fit[(fit["date"] >= te_start) & (fit["date"] <= te_end)]
        if te.empty:
            continue
        p = te[["symbol", "date"]].copy()
        p["score"] = composite_score(te).values
        preds.append(p.dropna(subset=["score"]))
    oos = pd.concat(preds, ignore_index=True)
    paths = _paths_by_symbol(bars)
    print(f"OOS {len(oos):,} rows / {oos['date'].nunique():,} dates, "
          f"{len(paths):,} symbol paths\n", flush=True)

    arms = []
    for s in STOPS:
        r = run(oos, paths, k=a.k, horizon=a.horizon, stop=s)
        arms.append(r)
        if r.get("status") != "OK":
            print(f"  stop {s*100:.0f}%  {r['status']}"); continue
        print(f"  stop {s*100:>2.0f}%  stopped {r['n_stopped']:>6,}  "
              f"got {r['mean_stop_return']*100:+6.2f}%  would have got "
              f"{r['mean_hold_return']*100:+6.2f}%  ->  RECOVERY "
              f"{r['mean_recovery']*100:+6.2f}% (median "
              f"{r['median_recovery']*100:+6.2f}%, {r['share_recovered']*100:.0f}% "
              f"recovered, t {(r['t_across_months'] or float('nan')):+5.2f} on "
              f"{r['n_months']} months, LOO worst "
              f"{(r['loo_worst'] or 0)*100:+6.2f}%)", flush=True)

    ok = [r for r in arms if r.get("status") == "OK"]
    verdict = "CANNOT DETERMINE"
    if ok:
        tight = ok[0]
        loose = ok[-1]
        rising = tight["mean_recovery"] > loose["mean_recovery"]
        pos = tight["mean_recovery"] > 0
        loo_ok = (tight.get("loo_worst") or -1) > 0
        if pos and rising and loo_ok:
            verdict = (
                f"CONSISTENT WITH STOP HUNTING: positions stopped at "
                f"{tight['stop']*100:.0f}% realised "
                f"{tight['mean_stop_return']*100:+.2f}% and would have been worth "
                f"{tight['mean_hold_return']*100:+.2f}% at the horizon -- a recovery "
                f"of {tight['mean_recovery']*100:+.2f}%, positive in every "
                f"leave-one-year-out (worst {tight['loo_worst']*100:+.2f}%). And it "
                f"is LARGER at the tight stop than the loose one "
                f"({tight['mean_recovery']*100:+.2f}% vs "
                f"{loose['mean_recovery']*100:+.2f}%), which is the direction the "
                f"hypothesis predicts: a more obvious level is a more crowded one. "
                f"This does NOT prove intent -- the same pattern is produced by "
                f"ordinary short-horizon mean reversion -- but it does say the "
                f"touch is not information, and it is why §62's stops lost money.")
        elif pos and not rising:
            verdict = (
                f"POSITIONS RECOVER, BUT NOT MORE AT TIGHTER STOPS: recovery is "
                f"{tight['mean_recovery']*100:+.2f}% at "
                f"{tight['stop']*100:.0f}% and {loose['mean_recovery']*100:+.2f}% at "
                f"{loose['stop']*100:.0f}%. Recovery without the level-dependence is "
                f"what ordinary mean reversion looks like; hunting predicts the "
                f"crowded level specifically.")
        elif pos and not loo_ok:
            verdict = (
                f"RECOVERS IN SOME YEARS ONLY: mean recovery "
                f"{tight['mean_recovery']*100:+.2f}% but the worst "
                f"leave-one-year-out is {(tight.get('loo_worst') or 0)*100:+.2f}% "
                f"(dropping {tight.get('loo_worst_dropped')}).")
        else:
            verdict = (
                f"NOT SUPPORTED: positions stopped at {tight['stop']*100:.0f}% were "
                f"worth {tight['mean_recovery']*100:+.2f}% MORE by holding, i.e. the "
                f"touch carried real information and the price kept going. The stop "
                f"was doing its job; §62's losses are then about the SELECTOR, not "
                f"about the level being hunted.")

    res = {"receipt": "stop_hunt", "licence": "PRODUCT_EXPERIMENT",
           "llm_spend_usd": 0.0,
           "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "hypothesis": ("Murat, 2026-09-24: 'sometimes they suddenly drop and "
                          "increase a lot more, maybe big funds do that so people "
                          "accidentally sell and they buy and it increases'. A "
                          "stopped position should therefore RECOVER, and more so "
                          "at tighter (more crowded) levels."),
           "design": ("PAIRED: every stopped position is compared against itself "
                      "held to the horizon. Same name, same entry, same window, "
                      "one difference. No cross-sectional benchmark to get wrong."),
           "fill_conventions": "inherited from night_exit_rules; gap fills at the OPEN",
           "k": a.k, "horizon": a.horizon, "arms": arms, "verdict": verdict}
    OUT.mkdir(parents=True, exist_ok=True)
    out = Path(a.out) if a.out else OUT / f"stop_hunt_{date.today()}.json"
    out.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(f"\nVERDICT: {verdict}")
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
