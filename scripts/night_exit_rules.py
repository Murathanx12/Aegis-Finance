"""Does an EXIT RULE rescue a book whose SELECTION is weak?

    python -m scripts.night_exit_rules --survivorship-free

THE HYPOTHESIS, AND WHERE IT CAME FROM
======================================
`docs/FINDINGS_2026-09-24_THE_FLEET_LOSES_ON_EXITS.md` measured the paper fleet's
358 closed round trips and found the loss is not in what it holds (unrealised
−$905 across 20 positions) but in how it trades:

    hit rate        27.7%
    mean winner     +1.91%
    mean loser      −7.00%
    winners held    1.1 days
    losers held     3.5 days

At a 28% hit rate, break-even needs winners 2.6x losers. Instead losers are 3.7x
winners. A hindsight replay said a **−2% stop would have saved $29,426 of the
$39,436 realised loss (75%)**, and that document said plainly what was wrong
with the number:

> this counterfactual assumes capping a loss is free and it is not. Stops get
> whipsawed, some of those −7% losers would have recovered, and a gap can fill
> below the level.

This script is that caveat, executed. It re-runs the same ranking through
genuine exit rules on real OHLC bars and asks whether any of them beats holding.

WHY THIS IS WORTH A RUN WITH §59/§60/§61 ALL CLOSED
===================================================
Those three closed a question about SELECTION -- which names to hold. An exit
rule is a different lever: it changes the return distribution of a book whose
ordering is fixed. If the fleet's pathology is real, the same pathology should
be visible in a top-k book built from `xs_ranker`, and a stop should improve it.
If a stop does NOT improve it here, then the fleet's 75% was the marking and not
the market, and the exit proposal should not be sent to a live book.

Either answer is worth having and it costs one pass over bars already on disk.

THE FILL CONVENTIONS, WHICH ARE THE WHOLE VALIDITY OF THIS
==========================================================
A stop test that gets these wrong will always say stops are free.

* **Intraday trigger, not close-to-close.** The stop fires on the session LOW.
  A close-only test lets a position sit through a −8% excursion and exit at
  −1.9%, which is how a backtest reports that stops cost nothing.
* **A gap through the level fills at the OPEN, not at the level.** If the open
  is already below the stop, the stop price was never available. This is the
  single largest source of optimism in stop backtests.
* **When a stop and a target are both touched in one session, the STOP wins.**
  Daily bars do not record which came first, so the worst admissible ordering is
  assumed. Anything else lets the test choose its own luck.
* **Entry is the NEXT session's open** and the un-stopped exit is the close
  `HORIZON` sessions later -- identical to `xs_ranker.build_target`, so the
  no-rule arm reproduces `fwd_ret` and any difference is the rule.
* **An early exit goes to CASH for the rest of the window.** It does not
  redeploy into the next best name. A real book would, and that would help, so
  this arm is CONSERVATIVE toward exit rules: it charges them the idle capital
  and credits them nothing for it. The receipt carries `mean_hold_sessions` so a
  reader can see how much capital sat idle, and no attempt is made to model the
  redeployment -- a modelled redeploy would be a second strategy smuggled into
  the test of the first.
* **Costs are charged once per round trip** at the name's liquidity band, on
  both arms. An exit rule does not change the number of round trips here (one
  entry, one exit either way), so costs cancel in the comparison; they are still
  charged so the levels are readable.

WHAT IS COMPARED, AND AGAINST WHAT
==================================
Every arm is measured RELATIVE to the equal-weight eligible cross-section over
the same window, the same convention as the panel's own target. A stop that
"saves" money in a month when everything fell has saved nothing.

And every arm reports leave-one-year-out, because 2026-09-24 also produced a
+2.62%/hold cell that became +0.12% on dropping one year.
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

from backend.services import xs_ranker as XR      # noqa: E402

OUT = REPO / "backend" / "data" / "optimus" / "xs_ranker"

#: Book size. 50 is the middle of the breadth sweep and not its best cell.
DEFAULT_K = 50
#: Stop levels. −2% is the one the fleet autopsy proposed; the others bracket it
#: so the answer is a shape rather than one number.
STOPS = (0.02, 0.03, 0.05, 0.08)
#: Take-profit levels, testing the other half of the fleet's pathology: it cut
#: winners at +1.91%. If cutting winners early is what costs it, a tight target
#: should be WORSE than holding, and that is a falsifiable prediction.
TAKES = (0.03, 0.05, 0.10)
#: Trailing stops, from the running high since entry.
TRAILS = (0.03, 0.05)


def _prior_signs() -> dict[str, float]:
    from scripts.night_horizon_sweep import PRIOR_SIGNS
    return PRIOR_SIGNS


def composite_score(te: pd.DataFrame) -> pd.Series:
    """The same prior-signed z-score mean the horizon sweep uses."""
    from scripts.night_horizon_sweep import _composite_score
    return _composite_score(te)


class Path_:
    """One symbol's OHLC as NUMPY arrays, date-sorted.

    Deliberately not a DataFrame. The walk visits up to 21 sessions x 4 prices
    for 42,000 positions x 13 arms; `DataFrame.at` costs ~3us a read, which turns
    a three-minute job into an hour, and 4,793 small frames cost a couple of GB
    where four arrays cost a few hundred MB. The 12-hour run of 2026-09-23 held
    7,835 MB doing this shape of work in pandas.
    """

    __slots__ = ("dates", "open", "high", "low", "close", "n")

    def __init__(self, g: pd.DataFrame) -> None:
        g = g.sort_values("date")
        self.dates = g["date"].values.astype("datetime64[ns]")
        self.open = g["open"].to_numpy(dtype=float)
        self.high = g["high"].to_numpy(dtype=float)
        self.low = g["low"].to_numpy(dtype=float)
        self.close = g["close"].to_numpy(dtype=float)
        self.n = len(g)


def _paths_by_symbol(bars: pd.DataFrame) -> dict[str, Path_]:
    """One `Path_` per symbol. Random access by symbol is what the walk needs;
    a groupby per rebalance date would re-scan 8.5M rows 800 times."""
    return {sym: Path_(g) for sym, g in bars.groupby("symbol", sort=False)}


def walk_one(path: "Path_", i_entry: int, horizon: int, *,
             stop: float | None = None, take: float | None = None,
             trail: float | None = None,
             time_stop: int | None = None) -> tuple[float, int, str]:
    """Return (simple return, sessions held, why it exited) for one position.

    `i_entry` indexes the session whose OPEN is the entry -- i.e. t+1 relative to
    the scoring date, matching `build_target`.
    """
    if i_entry >= path.n:
        return (float("nan"), 0, "no_entry_bar")
    entry = path.open[i_entry]
    if not np.isfinite(entry) or entry <= 0:
        return (float("nan"), 0, "bad_entry_price")

    stop_px = entry * (1.0 - stop) if stop else None
    take_px = entry * (1.0 + take) if take else None
    running_high = entry
    last = min(i_entry + horizon - 1, path.n - 1)

    for j in range(i_entry, last + 1):
        o = path.open[j]
        hi = path.high[j]
        lo = path.low[j]
        held = j - i_entry + 1

        # A trailing stop is recomputed from the running high BEFORE this
        # session's range is consumed, because a trail that uses today's high to
        # justify today's exit is using information from after the trigger.
        trail_px = running_high * (1.0 - trail) if trail else None

        # GAPS FIRST. A level below the open was never available at that level.
        for lvl, why in ((stop_px, "stop"), (trail_px, "trail")):
            if lvl is not None and o <= lvl:
                return (o / entry - 1.0, held, f"{why}_gap")
        if take_px is not None and o >= take_px:
            return (o / entry - 1.0, held, "take_gap")

        # Then intraday. STOP BEFORE TAKE: daily bars do not record the order
        # within the session, so the worst admissible sequence is assumed.
        for lvl, why in ((stop_px, "stop"), (trail_px, "trail")):
            if lvl is not None and lo <= lvl:
                return (lvl / entry - 1.0, held, why)
        if take_px is not None and hi >= take_px:
            return (take_px / entry - 1.0, held, "take")

        running_high = max(running_high, hi)
        if time_stop is not None and held >= time_stop:
            return (path.close[j] / entry - 1.0, held, "time")

    return (path.close[last] / entry - 1.0, last - i_entry + 1, "horizon")


def _entry_index(path: "Path_", score_date: np.datetime64) -> int | None:
    """Index of the first session strictly AFTER the scoring date."""
    idx = int(np.searchsorted(path.dates, score_date, side="right"))
    return idx if idx < path.n else None


def run_arm(oos: pd.DataFrame, paths: dict[str, "Path_"], *,
            k: int, horizon: int, label: str, **rule) -> dict:
    """One exit rule over every rebalance date."""
    rows = []
    for d, grp in oos.groupby("date"):
        top = grp.nlargest(k, "score")
        if len(top) < k:
            continue
        rets, holds, whys = [], [], []
        for sym in top["symbol"]:
            p = paths.get(sym)
            if p is None:
                continue
            i = _entry_index(p, np.datetime64(pd.Timestamp(d), "ns"))
            if i is None:
                continue
            r, h, w = walk_one(p, i, horizon, **rule)
            if not np.isfinite(r):
                continue
            rets.append(r); holds.append(h); whys.append(w)
        if len(rets) < max(5, k // 4):
            continue

        # The BENCHMARK is the same rule applied to nothing: the eligible
        # cross-section's own forward return over the full window. An exit rule
        # that beats a falling market has not beaten anything, and comparing a
        # stopped book against a held benchmark is the standard way to make
        # stops look good in a bear tape.
        bench = float(grp["bench_fwd_ret"].iloc[0]) if "bench_fwd_ret" in grp else np.nan
        if not np.isfinite(bench):
            continue
        bps = float(np.mean([XR.round_trip_bps(v)
                             for v in top["median_dollar_vol"]]))
        gross_rel = float(np.mean(rets)) - bench
        rows.append({"date": str(pd.Timestamp(d).date()),
                     "gross_rel": gross_rel,
                     "net_rel": gross_rel - bps / 10_000.0,
                     "mean_hold": float(np.mean(holds)),
                     "stopped_frac": float(np.mean([w.startswith(("stop", "trail"))
                                                    for w in whys])),
                     "took_frac": float(np.mean([w.startswith("take") for w in whys])),
                     "gap_frac": float(np.mean([w.endswith("_gap") for w in whys])),
                     "n": len(rets)})
    if not rows:
        return {"arm": label, "status": "REFUSED", "why": "no date produced a book"}

    net = np.array([r["net_rel"] for r in rows])
    years = pd.Series([r["date"][:4] for r in rows])
    by_year = {y: float(net[(years == y).values].mean()) for y in sorted(years.unique())}
    loo = {y: float(net[(years != y).values].mean()) for y in sorted(years.unique())
           if (years != y).sum() > 1}
    blocks = pd.Series([r["date"][:7] for r in rows])
    bm = net if len(blocks) == 0 else pd.Series(net).groupby(blocks).mean().values
    se = float(np.std(bm, ddof=1) / np.sqrt(len(bm))) if len(bm) > 1 else float("nan")
    return {
        "arm": label, "status": "OK", "rule": {k_: v for k_, v in rule.items() if v},
        "n_dates": len(rows),
        "mean_net_rel": float(net.mean()),
        "mean_gross_rel": float(np.mean([r["gross_rel"] for r in rows])),
        "mean_hold_sessions": float(np.mean([r["mean_hold"] for r in rows])),
        "stopped_frac": float(np.mean([r["stopped_frac"] for r in rows])),
        "took_frac": float(np.mean([r["took_frac"] for r in rows])),
        "gap_frac_of_exits": float(np.mean([r["gap_frac"] for r in rows])),
        "hit_rate_dates": float((net > 0).mean()),
        "t_across_months": float(np.mean(bm) / se) if np.isfinite(se) and se > 0 else None,
        "by_year": by_year,
        "leave_one_year_out": loo,
        "loo_worst": min(loo.values()) if loo else None,
        "loo_worst_dropped": min(loo, key=loo.get) if loo else None,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--survivorship-free", action="store_true")
    ap.add_argument("--bars", default=None)
    ap.add_argument("--k", type=int, default=DEFAULT_K)
    ap.add_argument("--horizon", type=int, default=XR.HORIZON_SESSIONS)
    ap.add_argument("--folds", type=int, default=4)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)

    bars = (XR.load_bars(XR.survivorship_free_paths()) if a.survivorship_free
            else XR.load_bars(Path(a.bars) if a.bars else None))
    audit = XR.survivorship_audit(bars)
    print(f"survivorship: {audit['verdict'][:90]}", flush=True)

    panel = XR.build_panel(bars, horizon=a.horizon)
    fit = panel[panel["eligible"] & panel["y"].notna()].copy()
    saved = XR.PURGE_SESSIONS
    XR.PURGE_SESSIONS = a.horizon
    try:
        folds = XR.make_folds(fit["date"].values, n_folds=a.folds)
    finally:
        XR.PURGE_SESSIONS = saved

    preds = []
    for tr_end, te_start, te_end in folds:
        te = fit[(fit["date"] >= te_start) & (fit["date"] <= te_end)]
        if te.empty:
            continue
        p = te[["symbol", "date", "median_dollar_vol", "bench_fwd_ret"]].copy()
        p["score"] = composite_score(te).values
        preds.append(p.dropna(subset=["score"]))
    if not preds:
        print("REFUSED: no fold produced scores")
        return 2
    oos = pd.concat(preds, ignore_index=True)
    print(f"OOS rows {len(oos):,} over {oos['date'].nunique():,} dates", flush=True)

    paths = _paths_by_symbol(bars)
    print(f"paths for {len(paths):,} symbols", flush=True)

    arms: list[dict] = []
    def go(label: str, **rule):
        r = run_arm(oos, paths, k=a.k, horizon=a.horizon, label=label, **rule)
        arms.append(r)
        if r.get("status") != "OK":
            print(f"  {label:<18} {r['status']}: {r.get('why')}", flush=True)
            return
        print(f"  {label:<18} net {r['mean_net_rel']*100:+6.2f}%  "
              f"hold {r['mean_hold_sessions']:>4.1f}d  "
              f"exits: stop {r['stopped_frac']*100:>4.0f}% take {r['took_frac']*100:>4.0f}% "
              f"(gap {r['gap_frac_of_exits']*100:>3.0f}%)  "
              f"t {(r['t_across_months'] or float('nan')):+5.2f}  "
              f"LOO worst {(r['loo_worst'] or 0)*100:+6.2f}% (drop {r['loo_worst_dropped']})",
              flush=True)

    print(f"\n--- k={a.k}, horizon={a.horizon} sessions ---", flush=True)
    go("hold")
    for s in STOPS:
        go(f"stop_{int(s*100)}pct", stop=s)
    for t in TAKES:
        go(f"take_{int(t*100)}pct", take=t)
    for tr in TRAILS:
        go(f"trail_{int(tr*100)}pct", trail=tr)
    # The fleet's actual behaviour, reproduced as a rule: cut winners at ~+2%
    # and let losers run to the horizon. If the autopsy is right this must be
    # the WORST arm here, and that is the test of the autopsy.
    go("fleet_mimic", take=0.02)
    # And the pairing the autopsy implies is correct: cut losers, let winners
    # run. Same two levers, opposite assignment.
    go("stop2_take10", stop=0.02, take=0.10)

    base = next((r for r in arms if r["arm"] == "hold" and r.get("status") == "OK"), None)
    ok = [r for r in arms if r.get("status") == "OK" and r["arm"] != "hold"]
    verdict = "CANNOT DETERMINE: the hold arm refused"
    if base and ok:
        best = max(ok, key=lambda r: r["mean_net_rel"])
        d = best["mean_net_rel"] - base["mean_net_rel"]
        # An improvement that vanishes when one year is dropped is a regime, and
        # that check precedes any discussion of size -- 2026-09-24, twice.
        loo_ok = (best.get("loo_worst") is not None
                  and base.get("loo_worst") is not None
                  and best["loo_worst"] > base["loo_worst"])
        if d <= 0:
            verdict = (
                f"NO EXIT RULE BEATS HOLDING: the best of {len(ok)} arms is "
                f"{best['arm']} at {best['mean_net_rel']*100:+.2f}% vs hold's "
                f"{base['mean_net_rel']*100:+.2f}% -- a difference of "
                f"{d*100:+.2f}%. On THIS panel, with gap-aware fills and "
                f"stop-before-take ordering, capping losses is not free. The "
                f"fleet autopsy's 75% saving assumed it was.")
        elif not loo_ok:
            verdict = (
                f"IMPROVES, BUT ONLY IN ONE REGIME: {best['arm']} adds "
                f"{d*100:+.2f}% over holding, and its worst leave-one-year-out "
                f"({best['loo_worst']*100:+.2f}%, dropping "
                f"{best['loo_worst_dropped']}) is no better than the hold arm's "
                f"({base['loo_worst']*100:+.2f}%). An exit rule whose advantage "
                f"lives in one year is a bet on that year repeating.")
        else:
            verdict = (
                f"EXIT RULE HELPS: {best['arm']} earns "
                f"{best['mean_net_rel']*100:+.2f}% vs hold's "
                f"{base['mean_net_rel']*100:+.2f}% ({d*100:+.2f}%), and survives "
                f"leave-one-year-out ({best['loo_worst']*100:+.2f}% vs "
                f"{base['loo_worst']*100:+.2f}%). Fills are gap-aware and a "
                f"same-session stop/target collision resolves to the STOP, so "
                f"this is not the optimistic convention. Next step is forward "
                f"paper, not a live fleet change.")

    res = {"receipt": "exit_rules", "licence": "PRODUCT_EXPERIMENT",
           "llm_spend_usd": 0.0,
           "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "k": a.k, "horizon": a.horizon, "selection": "composite_prior",
           "hypothesis": ("the fleet's loss is an EXIT pathology (27.7% hit rate, "
                          "mean winner +1.91% vs mean loser -7.00%, losers held 3x "
                          "longer); a hindsight replay said a -2% stop saves 75% "
                          "of the realised loss, assuming a cap is free"),
           "fill_conventions": {
               "trigger": "intraday LOW/HIGH, not close-to-close",
               "gap": "a level below the open fills at the OPEN, not the level",
               "collision": "stop resolves BEFORE take within a session",
               "entry": "next session's OPEN (matches build_target)",
               "early_exit": "goes to CASH for the rest of the window; no redeploy",
               "costs": "one round trip at the name's liquidity band, both arms"},
           "survivorship": audit, "arms": arms, "verdict": verdict,
           "read_me_first": ("Every arm is measured RELATIVE to the equal-weight "
                             "eligible cross-section over the same window. A stop "
                             "that 'saves' money while everything falls has saved "
                             "nothing, and comparing a stopped book to a held "
                             "benchmark is how stops are made to look good.")}
    OUT.mkdir(parents=True, exist_ok=True)
    out = Path(a.out) if a.out else OUT / f"exit_rules_{date.today()}.json"
    out.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(f"\nVERDICT: {verdict}")
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
