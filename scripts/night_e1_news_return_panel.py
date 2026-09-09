"""E1 -- THE JOINED TEXT-AND-RETURN PANEL, at last.

    python -m scripts.night_e1_news_return_panel --smoke
    python -m scripts.night_e1_news_return_panel

WHY THIS IS THE NIGHT'S FIRST JOB
=================================
The memory index has carried this line since 2026-09-08:

    THE HIGHEST-VALUE DATA ITEM: there is NO joined text-and-return panel.
    Only 21,841 of 993,005 event rows carry BOTH a headline and a CRSP permno
    (91 mega-cap names, 2015-2018); the news lane found 9,457 labelled cells
    over 135 names because dense news is 2025-26 while CRSP ends 2024-12.

P6 landed `prices_2025_26/bars.parquet` on the night of 09-08: 1,248,370 daily
bars, 3,060 symbols, 2025-01-02 -> 2026-09-08, from the Alpaca data endpoint.
That is exactly the window where the news corpus is dense (408,218 `kind=news`
rows over 6,605 symbols). The blocker was never the text and never the method:
the prices stopped in 2024 and the news started in 2025. Those two halves have
now met and nobody has joined them.

PIT DISCIPLINE (the only part of this file worth arguing about)
==============================================================
`effective_at` is a DATE; `observed_at` is the publication INSTANT in UTC. We
label off `observed_at`, converted to America/New_York, and enter at the first
regular-session OPEN strictly after it:

    published 09:12 ET Tue  -> entry Tue open   (public before the bell)
    published 09:31 ET Tue  -> entry Wed open   (the bell had already rung)
    published 17:29 ET Tue  -> entry Wed open
    published 11:00 ET Sat  -> entry Mon open

A headline published one minute into the session cannot be traded at that
session's open, so it waits for the next one. This costs the intraday reaction
on most rows and it is not negotiable: the alternative is the look-ahead that
[[feedback-a-within-month-rank-is-a-look-ahead]] was written about, where a
+1.80% spread became +0.76% once the ranking stopped seeing the month it ranked.

Two labels per row, both from the entry session:
    r_oc   open -> close of the entry session (one full session of exposure)
    r_oo   entry open -> next session's open  (adds the following overnight)
and each minus SPY over the identical window, because an equal-weight average
of news-carrying names against nothing at all is a reading of market direction,
not of text ([[feedback-an-ew-average-against-a-vw-market-is-the-regime]]).

NO MODEL, NO SIGNAL, NO CLAIM. This file writes a panel. C2 reads it.
"""
from __future__ import annotations

import argparse
import glob
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ET = ZoneInfo("America/New_York")
ROOT = Path(__file__).resolve().parent.parent
CORPUS = Path(r"C:\Users\mrthn\aegis-alpha-terminal\state\corpus\observations")
BARS = ROOT / "backend" / "data" / "optimus" / "prices_2025_26" / "bars.parquet"
OUT = ROOT / "backend" / "data" / "optimus" / "text_return_panel"
BENCH = "SPY"
MAX_BODY = 1200


def _load_bars():
    b = pd.read_parquet(BARS)
    b["date"] = pd.to_datetime(b["date"]).dt.normalize()
    b = b.sort_values(["symbol", "date"]).reset_index(drop=True)
    sessions = np.sort(b.loc[b["symbol"] == BENCH, "date"].unique())
    if len(sessions) < 100:                      # SPY missing -> use the union
        sessions = np.sort(b["date"].unique())
    per = {}
    for sym, g in b.groupby("symbol", sort=False):
        g = g.set_index("date")
        per[sym] = pd.DataFrame({"open": g["open"], "close": g["close"],
                                 "next_open": g["open"].shift(-1),
                                 "dv": g["close"] * g["volume"]})
    return per, sessions


def _entry_session(observed_at, effective_at, sessions):
    """First regular-session open strictly after publication. None if off the end."""
    ts = None
    if observed_at:
        try:
            ts = pd.Timestamp(observed_at)
            ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
            ts = ts.tz_convert(ET)
        except Exception:                                            # noqa: BLE001
            ts = None
    if ts is None:
        if not effective_at:
            return None, None
        try:                      # dateless fallback: the date, treated as pre-open
            ts = pd.Timestamp(effective_at).tz_localize(ET) + pd.Timedelta(hours=8)
        except Exception:                                            # noqa: BLE001
            return None, None
    day = ts.normalize().tz_localize(None)
    before_bell = (ts.hour, ts.minute) < (9, 30)
    i = int(np.searchsorted(sessions, np.datetime64(day), side="left"))
    if not (i < len(sessions) and sessions[i] == np.datetime64(day) and before_bell):
        i = int(np.searchsorted(sessions, np.datetime64(day), side="right"))
    if i >= len(sessions):
        return None, None
    return pd.Timestamp(sessions[i]), ("pre_bell" if before_bell else "post_bell")


def _symbols(raw):
    if isinstance(raw, str):
        try:
            return json.loads(raw.replace("'", '"'))
        except Exception:                                            # noqa: BLE001
            return [s.strip(" '[]\"") for s in raw.split(",")]
    return list(raw or [])


def build(max_rows=None, years=("2025", "2026")) -> dict:
    t0 = time.time()
    per, sessions = _load_bars()
    bench = per.get(BENCH)
    have = set(per)
    rows, seen = [], set()
    stats = {"news_rows": 0, "no_symbol_bar": 0, "off_calendar": 0,
             "no_bar_that_day": 0, "dup": 0, "kept": 0}
    files = [f for f in sorted(glob.glob(str(CORPUS / "*.jsonl")))
             if Path(f).name[:4] in years]
    stop = False
    for f in files:
        if stop:
            break
        for line in open(f, encoding="utf-8", errors="replace"):
            try:
                d = json.loads(line)
            except Exception:                                        # noqa: BLE001
                continue
            if d.get("kind") != "news" or not d.get("body"):
                continue
            syms = _symbols(d.get("symbols"))
            if not syms:
                continue
            stats["news_rows"] += 1
            day, pos = _entry_session(d.get("observed_at") or "",
                                      d.get("effective_at") or "", sessions)
            if day is None:
                stats["off_calendar"] += 1
                continue
            for s in syms[:8]:
                s = (s or "").strip().upper()
                if not s or s not in have:
                    stats["no_symbol_bar"] += 1
                    continue
                key = (d.get("uid"), s)
                if key in seen:
                    stats["dup"] += 1
                    continue
                g = per[s]
                if day not in g.index:
                    stats["no_bar_that_day"] += 1
                    continue
                r = g.loc[day]
                o, c, nxt = float(r["open"]), float(r["close"]), r["next_open"]
                if not np.isfinite(o) or o <= 0:
                    stats["no_bar_that_day"] += 1
                    continue
                r_oc = c / o - 1.0
                r_oo = (float(nxt) / o - 1.0) if pd.notna(nxt) else np.nan
                b_oc = b_oo = np.nan
                if bench is not None and day in bench.index:
                    br = bench.loc[day]
                    bo = float(br["open"])
                    if np.isfinite(bo) and bo > 0:
                        b_oc = float(br["close"]) / bo - 1.0
                        b_oo = ((float(br["next_open"]) / bo - 1.0)
                                if pd.notna(br["next_open"]) else np.nan)
                seen.add(key)
                stats["kept"] += 1
                rows.append({
                    "uid": d.get("uid"), "symbol": s,
                    "published_utc": d.get("observed_at") or "",
                    "entry_date": day.date().isoformat(), "publish_position": pos,
                    "source": d.get("source"),
                    "independence_group": d.get("independence_group"),
                    "title": (d.get("title") or "")[:400],
                    "body": (d.get("body") or "")[:MAX_BODY],
                    "r_oc": r_oc, "r_oo": r_oo,
                    "x_oc": r_oc - b_oc, "x_oo": r_oo - b_oo,
                    "dollar_vol": float(r["dv"]) if pd.notna(r["dv"]) else np.nan,
                })
                if max_rows and len(rows) >= max_rows:
                    stop = True
                    break
            if stop:
                break

    df = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "news_returns_2025_26.parquet"
    df.to_parquet(path, index=False)

    def _d(col):
        s = pd.Series(col).replace([np.inf, -np.inf], np.nan).dropna()
        if s.size < 3:
            return {"n": int(s.size)}
        return {"n": int(s.size), "mean_bps": round(float(s.mean()) * 1e4, 2),
                "sd_bps": round(float(s.std()) * 1e4, 2),
                "t": round(float(s.mean() / (s.std() / np.sqrt(s.size))), 3)}

    receipt_range = (f"{df['entry_date'].min()}..{df['entry_date'].max()}"
                     if len(df) else "--")
    receipt = {
        "job": "E1_news_return_panel", "licence": "PRODUCT_EXPERIMENT",
        "llm_spend_usd": 0.0,
        "what": "every 2025-26 corpus news row joined to the Alpaca bar of the first "
                "session whose OPEN is strictly after publication; two labels, each minus SPY",
        "path": str(path), "wall_s": round(time.time() - t0, 1),
        "funnel": stats, "rows": int(len(df)),
        "symbols": int(df["symbol"].nunique()) if len(df) else 0,
        "date_range": ([df["entry_date"].min(), df["entry_date"].max()]
                       if len(df) else None),
        "by_publish_position": (df["publish_position"].value_counts().to_dict()
                                if len(df) else {}),
        "labels": {k: _d(df[k]) for k in ("r_oc", "r_oo", "x_oc", "x_oo")} if len(df) else {},
        "prior_best_panel": "9,457 labelled cells over 135 names (2026-09-08 news lane)",
        "verdict": "PANEL BUILT",
        "headline": (f"{len(df):,} labelled text-and-return cells over "
                     f"{df['symbol'].nunique():,} symbols, "
                     f"{receipt_range} -- the prior best was 9,457 over 135 names"
                     if len(df) else "PANEL EMPTY -- see funnel"),
        "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (OUT / "E1_receipt.json").write_text(json.dumps(receipt, indent=1, default=str),
                                         encoding="utf-8")
    return receipt


def E1_news_return_panel(smoke: bool = False) -> dict:
    return build(max_rows=3000 if smoke else None)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()
    print(json.dumps(E1_news_return_panel(smoke=a.smoke), indent=1, default=str))
