"""SUE x REACTION quadrants on CRSP 2013-2024: does the dislocation lane have history?

    python -m scripts.sue_dislocation_backtest

WHAT IT TESTS
=============
`EARNINGS_DISLOCATION_v1` (terminal repo) ranks printers by whether the
fundamental surprise and the price reaction DISAGREE. Before that lane gets a
dollar it needs a history, and the history exists locally: IBES consensus
(`ibes_consensus_monthly.parquet`, permno-joined, 2013-2024, with `actual` and
`anndats_act`) beside CRSP daily. The fundamental surprise here is the
classic SUE, (actual - last pre-announcement median estimate) / price, which is
the deterministic stand-in for the council's cube; the reaction is the
two-session close-to-close return around the announcement date (IBES dates
carry no time of day, so day 0 spans the print whether it was BMO or AMC).

The forward return is the next three sessions after the reaction window, in
EXCESS of the equal-weighted market that day -- the same convention as the
wide-universe PEAD receipt in the terminal repo.

PIT DISCIPLINE
==============
The estimate is the last consensus dated STRICTLY BEFORE the announcement date;
the actual is used only from `anndats_act`. Price for scaling is the close two
sessions before the announcement. Nothing here is known before it was public.

OUTPUT
======
A quadrant table (SUE quintile x reaction sign) with n, mean, hit, t over date
blocks, and the same by size tercile so the non-mega-cap question is answered
directly. Written to `backend/data/optimus/sue_dislocation_2013_2024.json`.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
WRDS = ROOT / "backend" / "data" / "optimus" / "wrds"
OUT = ROOT / "backend" / "data" / "optimus" / "sue_dislocation_2013_2024.json"
YEARS = range(2013, 2025)
FWD = 3


def load_dsf() -> pd.DataFrame:
    frames = []
    for y in YEARS:
        p = WRDS / f"crsp_dsf_{y}.parquet"
        if not p.exists():
            continue
        f = pd.read_parquet(p, columns=["permno", "date", "prc", "ret", "shrout"])
        frames.append(f)
    d = pd.concat(frames, ignore_index=True)
    d["date"] = pd.to_datetime(d["date"])
    d["ret"] = pd.to_numeric(d["ret"], errors="coerce")
    d["prc"] = pd.to_numeric(d["prc"], errors="coerce").abs()
    d = d.dropna(subset=["ret"]).sort_values(["permno", "date"]).reset_index(drop=True)
    return d


def main() -> int:
    ib = pd.read_parquet(WRDS / "ibes_consensus_monthly.parquet",
                         columns=["permno", "statpers", "fpi", "medest", "stdev", "actual", "anndats_act", "fpedats", "numest"])
    ib = ib[(ib.fpi == "6") & ib.actual.notna() & ib.anndats_act.notna()].copy()
    ib["statpers"] = pd.to_datetime(ib["statpers"])
    ib["anndats_act"] = pd.to_datetime(ib["anndats_act"], errors="coerce")
    ib = ib.dropna(subset=["anndats_act"])
    ib = ib[ib.statpers < ib.anndats_act]
    # last consensus strictly before the announcement, per (permno, fpedats)
    ib = ib.sort_values(["permno", "fpedats", "statpers"]).groupby(["permno", "fpedats"], as_index=False).tail(1)
    ib = ib[(ib.numest >= 3)]
    print(f"events with a pre-announcement consensus: {len(ib):,}")

    dsf = load_dsf()
    print(f"CRSP rows: {len(dsf):,}; permnos {dsf.permno.nunique():,}")
    # equal-weighted market return per date
    mkt = dsf.groupby("date")["ret"].mean().rename("mkt")
    dsf = dsf.join(mkt, on="date")
    dsf["ex"] = dsf["ret"] - dsf["mkt"]
    dates = np.array(sorted(dsf.date.unique()))
    date_idx = {d: i for i, d in enumerate(dates)}
    # per-permno arrays
    g = {p: (grp.date.values, grp.ret.values, grp.ex.values, grp.prc.values, grp.shrout.values)
         for p, grp in dsf.groupby("permno")}

    rows = []
    for r in ib.itertuples(index=False):
        if r.permno not in g:
            continue
        ds, rets, exs, prcs, shr = g[r.permno]
        # first session >= announcement date
        j = np.searchsorted(ds, np.datetime64(r.anndats_act))
        if j < 2 or j + 1 + FWD >= len(ds):
            continue
        if (ds[j] - np.datetime64(r.anndats_act)).astype("timedelta64[D]").astype(int) > 3:
            continue
        p_pre = prcs[j - 2]
        if not (p_pre and p_pre > 1.0):
            continue
        sue = (float(r.actual) - float(r.medest)) / float(p_pre)
        r0 = (1 + rets[j]) * (1 + rets[j + 1]) - 1.0                # print session + next
        ex0 = exs[j] + exs[j + 1]
        fwd = float(np.sum(exs[j + 2:j + 2 + FWD]))                  # +1..+3 after the reaction window, excess
        cap = float(p_pre * shr[j - 2]) if shr[j - 2] else float("nan")
        rows.append((r.permno, ds[j], sue, r0, ex0, fwd, cap))
    ev = pd.DataFrame(rows, columns=["permno", "day0", "sue", "r0", "ex0", "fwd", "cap"])
    ev = ev[np.isfinite(ev.sue) & np.isfinite(ev.fwd)]
    print(f"events scored: {len(ev):,}")
    ev["sue_q"] = pd.qcut(ev.sue, 5, labels=["q1_worst", "q2", "q3", "q4", "q5_best"])
    ev["react"] = np.where(ev.ex0 > 0.02, "up", np.where(ev.ex0 < -0.02, "down", "flat"))
    ev["size"] = pd.qcut(ev.cap.rank(method="first"), 3, labels=["small", "mid", "large"])
    ev["week"] = pd.to_datetime(ev.day0).dt.to_period("W").astype(str)

    def stats(x: pd.DataFrame) -> dict:
        if len(x) < 30:
            return {"n": int(len(x))}
        wk = x.groupby("week")["fwd"].mean()
        t_wk = wk.mean() / (wk.std(ddof=1) / math.sqrt(len(wk))) if len(wk) > 2 and wk.std(ddof=1) > 0 else float("nan")
        return {"n": int(len(x)), "mean": round(float(x.fwd.mean()), 5), "median": round(float(x.fwd.median()), 5),
                "hit": round(float((x.fwd > 0).mean()), 3),
                "t": round(float(x.fwd.mean() / (x.fwd.std(ddof=1) / math.sqrt(len(x)))), 2),
                "t_week_blocks": round(float(t_wk), 2), "n_weeks": int(len(wk))}

    out = {"events": int(len(ev)), "window": [str(ev.day0.min())[:10], str(ev.day0.max())[:10]], "forward_sessions": FWD,
           "benchmark": "equal-weighted CRSP market, same day", "reaction_window": "print session + next, excess",
           "quadrants": {}, "by_size": {}, "sue_only": {}, "react_only": {}}
    print(f"\n{'SUE quintile':<10}{'reaction':<8}{'n':>7}{'mean fwd':>10}{'hit':>6}{'t':>7}{'t_wk':>7}")
    for q in ["q1_worst", "q2", "q3", "q4", "q5_best"]:
        for rc in ["down", "flat", "up"]:
            s = stats(ev[(ev.sue_q == q) & (ev.react == rc)])
            out["quadrants"][f"{q}|{rc}"] = s
            if "mean" in s:
                print(f"{q:<10}{rc:<8}{s['n']:>7}{s['mean']:>+10.3%}{s['hit']:>6.0%}{s['t']:>7.2f}{s['t_week_blocks']:>7.2f}")
    print("\nSUE only:")
    for q in ["q1_worst", "q5_best"]:
        s = stats(ev[ev.sue_q == q]); out["sue_only"][q] = s
        print(f"  {q:<10}{s['n']:>7}{s['mean']:>+10.3%}{s['hit']:>6.0%}{s['t']:>7.2f}{s['t_week_blocks']:>7.2f}")
    print("\nDISLOCATION cells by size tercile (the non-mega question):")
    for name, cond in [("q5_best|down (under-reaction?)", (ev.sue_q == "q5_best") & (ev.react == "down")),
                       ("q1_worst|up (delayed downside?)", (ev.sue_q == "q1_worst") & (ev.react == "up")),
                       ("q5_best|up (continuation?)", (ev.sue_q == "q5_best") & (ev.react == "up")),
                       ("q1_worst|down (continuation?)", (ev.sue_q == "q1_worst") & (ev.react == "down"))]:
        out["by_size"][name] = {}
        for sz in ["small", "mid", "large"]:
            s = stats(ev[cond & (ev["size"] == sz)]); out["by_size"][name][sz] = s
            if "mean" in s:
                print(f"  {name:<34}{sz:<6}{s['n']:>7}{s['mean']:>+10.3%}{s['hit']:>6.0%}{s['t']:>7.2f}{s['t_week_blocks']:>7.2f}")
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"\nreceipt: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
