"""NFP_FINAL_BOSS_v1 -- what the index actually does on Employment Situation day.

    python -m scripts.nfp_reaction_history
    python -m scripts.nfp_reaction_history --symbols SPY,QQQ,IWM --since 1996

WHY THIS, AND WHY NOW
=====================
The August Employment Situation is released 08:30 ET on 4 September 2026. The
competition deadline is 11:00 ET the same morning. That makes it the last
information event of the contest and the only one whose timing is known to the
minute -- so the decision about it should be frozen days early, not improvised
at 08:29.

`scripts/nfp_straddle_backtest` (terminal repo) already grades a 0DTE straddle,
but only over 2024-2026: 28 releases, because Alpaca's option history starts
there. Twenty-eight events is a sample in which a 57% hit rate and a 1.5-sigma
result are indistinguishable from noise.

The UNDERLYING, though, we have back to 1996 -- `optionm.secprd` daily OHLC for
SPY/QQQ/IWM was pulled alongside the option quotes. So the reaction can be
measured over ~350 releases instead of 28, which is the difference between a
regime and a fact.

WHAT IT MEASURES, AND THE HONEST LIMIT
======================================
Daily bars support exactly three segments:

    overnight   prior close -> release-day OPEN     (the gap; release is 08:30,
                                                     the open is 09:30, so the
                                                     gap CONTAINS the reaction)
    intraday    open -> close on release day
    full day    prior close -> close

They do NOT support open -> 10:00 or open -> 10:45, which is the window the
contest actually trades. That is a real limitation and is not papered over: a
daily-bar study can say whether NFP day carries an unusual return or an unusual
RANGE, and cannot say when within the day it arrived. The 2024-2026 minute-bar
work is the only evidence about intraday timing and it stays the authority
there.

THE CONTROL IS THE POINT
========================
"SPY rose on NFP days" is not a finding if SPY rose on all days. Every number
is reported against NON-release days over the same span, with a two-sample t.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config  # noqa: E402,F401  (loads .env)

DATA = REPO / "backend" / "data" / "optimus" / "wrds" / "optionm_etf_quotes"
SECIDS = {"SPY": 109820, "QQQ": 107899, "IWM": 106445, "SMH": 151720}

#: FRED release 50 is the BLS Employment Situation. Using the release calendar
#: rather than "first Friday of the month" because the rule has exceptions
#: (shutdowns, holidays) and each exception is a day the study would otherwise
#: label backwards -- a real event marked as a control and vice versa.
FRED_RELEASE_EMPLOYMENT_SITUATION = 50


def nfp_dates(since: str) -> list[str]:
    key = os.getenv("FRED_API_KEY", "").strip()
    if not key:
        raise SystemExit("FRED_API_KEY not set; refusing to guess release dates "
                         "from a first-Friday rule that has known exceptions")
    q = urllib.parse.urlencode({
        "release_id": FRED_RELEASE_EMPLOYMENT_SITUATION,
        "realtime_start": since, "realtime_end": "9999-12-31",
        "include_release_dates_with_no_data": "true",
        "limit": 10000, "api_key": key, "file_type": "json"})
    url = f"https://api.stlouisfed.org/fred/release/dates?{q}"
    with urllib.request.urlopen(url, timeout=60) as r:
        d = json.loads(r.read().decode())
    return sorted({x["date"] for x in d.get("release_dates", [])})


def load_under(symbol: str, start: int, end: int) -> pd.DataFrame:
    secid = SECIDS[symbol]
    frames = []
    for y in range(start, end + 1):
        f = DATA / f"under_{y}.parquet"
        if not f.exists():
            continue
        b = pd.read_parquet(f)
        b = b[b["secid"] == secid]
        if len(b):
            frames.append(b)
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").drop_duplicates("date").reset_index(drop=True)
    for c in ("open", "high", "low", "close"):
        df[c] = df[c].astype(float).abs()   # CRSP-style negatives mark a quote midpoint
    df["prev_close"] = df["close"].shift(1)
    df["gap"] = df["open"] / df["prev_close"] - 1.0
    df["intraday"] = df["close"] / df["open"] - 1.0
    df["full"] = df["close"] / df["prev_close"] - 1.0
    df["range"] = (df["high"] - df["low"]) / df["open"]
    return df.dropna(subset=["prev_close"])


def welch(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    """Two-sample t with unequal variances. Returns (t, difference in means)."""
    a, b = a[np.isfinite(a)], b[np.isfinite(b)]
    if a.size < 3 or b.size < 3:
        return float("nan"), float("nan")
    va, vb = np.var(a, ddof=1) / a.size, np.var(b, ddof=1) / b.size
    se = math.sqrt(va + vb)
    d = float(np.mean(a) - np.mean(b))
    return (d / se if se > 0 else 0.0), d


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="SPY,QQQ,IWM")
    ap.add_argument("--since", default="1996-01-01")
    ap.add_argument("--start", type=int, default=1996)
    ap.add_argument("--end", type=int, default=2025)
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    dates = set(nfp_dates(args.since))
    print(f"NFP REACTION HISTORY   {len(dates)} Employment Situation releases "
          f"from FRED release {FRED_RELEASE_EMPLOYMENT_SITUATION} since {args.since}")
    print("daily bars: gap CONTAINS the 08:30 release; they cannot locate the "
          "reaction within the session.")
    print("=" * 94)

    out = {}
    for sym in args.symbols.split(","):
        df = load_under(sym, args.start, args.end)
        if df.empty:
            print(f"\n{sym}: no underlying data")
            continue
        df["is_nfp"] = df["date"].dt.strftime("%Y-%m-%d").isin(dates)
        ev, ct = df[df["is_nfp"]], df[~df["is_nfp"]]
        print(f"\n{sym}  {df['date'].min().date()} .. {df['date'].max().date()}   "
              f"{len(ev)} release days vs {len(ct)} control days")
        print(f"  {'segment':<12}{'NFP mean':>11}{'ctrl mean':>11}{'diff':>10}"
              f"{'t':>7}{'NFP |mv|':>10}{'ctrl |mv|':>11}{'NFP hit':>9}")
        print("  " + "-" * 81)
        seg_out = {}
        for seg in ("gap", "intraday", "full"):
            a, b = ev[seg].to_numpy(), ct[seg].to_numpy()
            t, d = welch(a, b)
            print(f"  {seg:<12}{np.mean(a):>+11.3%}{np.mean(b):>+11.3%}"
                  f"{d:>+10.3%}{t:>+7.2f}{np.mean(np.abs(a)):>10.3%}"
                  f"{np.mean(np.abs(b)):>11.3%}{(a > 0).mean():>9.1%}")
            seg_out[seg] = {"nfp_mean": float(np.mean(a)),
                            "ctrl_mean": float(np.mean(b)), "diff": d, "t": t,
                            "nfp_abs": float(np.mean(np.abs(a))),
                            "ctrl_abs": float(np.mean(np.abs(b))),
                            "hit": float((a > 0).mean()), "n": int(a.size)}

        ta, da = welch(ev["range"].to_numpy(), ct["range"].to_numpy())
        print(f"  {'range':<12}{ev['range'].mean():>+11.3%}"
              f"{ct['range'].mean():>+11.3%}{da:>+10.3%}{ta:>+7.2f}")

        # The question a long-premium trade actually turns on: is the release-day
        # ABSOLUTE move bigger than an ordinary day's? A straddle buyer needs
        # that, and a spread seller needs its opposite.
        t_abs, d_abs = welch(np.abs(ev["full"].to_numpy()),
                             np.abs(ct["full"].to_numpy()))
        ratio = float(np.mean(np.abs(ev["full"])) / np.mean(np.abs(ct["full"])))
        print(f"\n  ABSOLUTE full-day move on release days is {ratio:.2f}x an "
              f"ordinary day (t {t_abs:+.2f} on the difference)")
        if t_abs < 2.0:
            print("  -> NOT resolvably larger. A long-premium NFP trade is paying "
                  "for an excess move this sample cannot demonstrate.")

        # By decade: one regime is not evidence.
        ev = ev.copy()
        ev["era"] = pd.cut(ev["date"].dt.year, [1995, 2007, 2012, 2019, 2026],
                           labels=["<=2007", "2008-2012", "2013-2019", "2020-2025"])
        print(f"  by era (full day):")
        for era, g in ev.groupby("era", observed=True):
            if len(g) < 5:
                continue
            x = g["full"].to_numpy()
            sd = float(np.std(x, ddof=1))
            tt = float(np.mean(x) / sd * math.sqrt(x.size)) if sd > 0 else 0.0
            print(f"    {str(era):<12} n={len(g):>3}  mean {np.mean(x):>+7.3%}"
                  f"  hit {(x > 0).mean():>5.1%}  t {tt:>+5.2f}"
                  f"  |mv| {np.mean(np.abs(x)):>6.3%}")
        out[sym] = seg_out

    if args.json:
        Path(args.json).write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(f"\nreceipt -> {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
