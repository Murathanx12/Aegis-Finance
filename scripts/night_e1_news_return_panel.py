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
BENCH = "SPY"
MAX_BODY = 1200

#: 21 sessions of trailing dollar volume, ENDING THE SESSION BEFORE the entry.
#: Defect #5 of 2026-09-10: a liquidity screen that reads the entry session's own
#: dollar volume has already seen the day it is screening.
PIT_DV_WINDOW = 21


def _data_root() -> Path:
    """`<DATA_DIR>/optimus`, resolved at CALL time.

    The module used to hard-code `ROOT/backend/data/optimus`, which pins the
    panel to whichever checkout the script lives in. A run with
    `AEGIS_DATA_DIR` pointed elsewhere read one panel and wrote another. Both
    `BARS()` and `OUT()` now follow the env var, and the receipt prints the
    paths it actually used.
    """
    from backend import config as _config
    return Path(_config.DATA_DIR) / "optimus"


def BARS() -> Path:  # noqa: N802 — kept upper-case; it was a module constant
    return _data_root() / "prices_2025_26" / "bars.parquet"


def OUT() -> Path:  # noqa: N802
    return _data_root() / "text_return_panel"


def _load_bars():
    b = pd.read_parquet(BARS())
    b["date"] = pd.to_datetime(b["date"]).dt.normalize()
    b = b.sort_values(["symbol", "date"]).reset_index(drop=True)
    sessions = np.sort(b.loc[b["symbol"] == BENCH, "date"].unique())
    if len(sessions) < 100:                      # SPY missing -> use the union
        sessions = np.sort(b["date"].unique())
    per = {}
    for sym, g in b.groupby("symbol", sort=False):
        g = g.set_index("date")
        dv = g["close"] * g["volume"]
        per[sym] = pd.DataFrame({
            "open": g["open"], "close": g["close"],
            "next_open": g["open"].shift(-1),
            "dv": dv,
            # `.shift(1)` FIRST, then roll: the window ends on the previous
            # session, so the entry session's own volume is never in it.
            "pit_dv_21": dv.shift(1).rolling(PIT_DV_WINDOW, min_periods=5).median(),
        })
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
    # A publication BEFORE the calendar's first session is off-calendar, not
    # session[0]. Found 2026-09-11 on the Alpaca backfill, which starts at
    # 2015-01-01 while these bars start 2025-01-02: without this clause every
    # one of those 2015 rows would have been labelled at the 2025-01-02 open —
    # a ten-year look-ahead that the funnel would have counted as `kept`.
    if len(sessions) and np.datetime64(day) < sessions[0]:
        return None, "before_calendar"
    i = int(np.searchsorted(sessions, np.datetime64(day), side="left"))
    if not (i < len(sessions) and sessions[i] == np.datetime64(day) and before_bell):
        i = int(np.searchsorted(sessions, np.datetime64(day), side="right"))
    if i >= len(sessions):
        return None, "after_calendar"
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
    out_dir = OUT()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "news_returns_2025_26.parquet"
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
    (out_dir / "E1_receipt.json").write_text(json.dumps(receipt, indent=1, default=str),
                                         encoding="utf-8")
    return receipt


def E1_news_return_panel(smoke: bool = False) -> dict:
    return build(max_rows=3000 if smoke else None)


# ===========================================================================
# N-C — THE NIGHTLY APPEND
# ===========================================================================
# Roadmap 2026-09-11 §3 N-C: new corpus rows -> the first open strictly after
# `first_seen_utc` -> labels minus SPY, `pit_dv_21` from bars, and a PIT
# re-verify on every append: 0 violations or the append is REFUSED.
#
# FOUR RULES THIS FUNCTION KEEPS, each one a decision rather than a detail
# ------------------------------------------------------------------------
# 1. **It reads only `label_source: true` sources.** Google News, Reddit,
#    Nikkei and Quantocracy are `pit_grade: index_state` — a provider can
#    reorder, edit or backfill them after the fact, so a return labelled off one
#    of their timestamps is a look-ahead nobody can detect afterwards. They are
#    breadth on the coverage card and nothing else (invariant 20). The list
#    comes from `news_registry.label_sources()`, so the registry is the single
#    place the rule lives.
#
# 2. **It anchors on `first_seen_utc`, which WE wrote.** Not `published_utc`:
#    two of the four labelling sources are `first_seen_only`, meaning their own
#    stamp is a crawl time the provider may move. Our stamp cannot be moved.
#
# 3. **`pit_dv_21` never contains the entry session's own dollar volume.** The
#    bar frame shifts by one session BEFORE rolling (defect #5, 2026-09-10): a
#    liquidity screen computed on the day it screens has already seen that day.
#
# 4. **A row whose entry session has not happened yet is PENDING, not dropped.**
#    Rows pulled tonight are usually in this state, and that is the normal
#    outcome, not a failure. `pending_future_session` is its own counter so that
#    "nothing labelled" never reads as "the join broke".
#
# THE PIT RE-VERIFY is deliberately a second, independent pass over the rows
# that were about to be written: for every one of them the entry session's 09:30
# ET bell must be strictly after `first_seen_utc`, and its `pit_dv_21` must come
# from sessions strictly before the entry date. A single violation refuses the
# WHOLE append and writes nothing — a partially-poisoned panel is worse than no
# append, because the poison is then indistinguishable from data.


def _label_sources() -> list[str]:
    from backend.services import news_registry
    return news_registry.label_sources()


def _skipped_sources(label_sources) -> list[str]:
    """The registry ids this append deliberately did NOT read. Named, not implied."""
    from backend.services import news_registry
    return [s for s in news_registry.ids() if s not in label_sources]


def _anchor(row) -> tuple[str, str]:
    """THE PIT anchor for one corpus row, and the field it came from.

    The two labelling grades need different anchors, and using one rule for
    both breaks one of them:

    * `native_stamp` -> `published_utc`. The grade's whole content is that the
      provider's own first-publish stamp is trustworthy and is not silently
      backfilled. Anchoring these on `first_seen_utc` instead would date every
      row of a BACKFILL to the day we downloaded it — the Alpaca backfill
      begins at 2015-01-01, so its rows would have been labelled at tomorrow's
      open, which is not conservative, it is nonsense.
    * `first_seen_only` -> `first_seen_utc`. Here the provider's stamp is a
      crawl time it may move, so the only anchor we control is our own.

    A native_stamp row with no `published_utc` falls back to `first_seen_utc`
    and says so, because a missing stamp is not a trustworthy one.
    """
    grade = (row.get("pit_grade") or "").strip()
    pub = (row.get("published_utc") or "").strip()
    if grade == "native_stamp" and pub:
        return pub, "published_utc"
    return (row.get("first_seen_utc") or "").strip(), "first_seen_utc"


def _corpus_rows(sources, since_iso: str, max_rows=None):
    """Corpus rows newer than the watermark, from the labelling sources only.

    Read through `jsonl_io`, NOT `str.splitlines()`. MEASURED 2026-09-13: nine
    Benzinga bodies in `alpaca_benzinga_news/2026-09-11.jsonl` carry a literal
    U+2028, which `splitlines()` breaks on and JSONL does not, so each of those
    rows arrived here as two unparseable fragments and was dropped by the
    `except: continue` below -- silently, with no count. 9 of 3,799 today; the
    share is a property of the publisher's copy-paste, not a constant.
    """
    from backend.services import jsonl_io as jio
    from scripts.news_pull import corpus_dir

    root = corpus_dir()
    out = []
    for sid in sources:
        d = root / sid
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.jsonl")):
            for line in jio.split_lines(f.read_text(encoding="utf-8", errors="replace")):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except Exception:                                    # noqa: BLE001
                    continue
                fs = row.get("first_seen_utc") or ""
                if since_iso and fs <= since_iso:
                    continue
                out.append(row)
                if max_rows and len(out) >= max_rows:
                    return out
    return out


def _pit_verify(rows, per) -> list[str]:
    """Independent second pass. Returns the violations, named."""
    bad = []
    for r in rows:
        anchor = pd.Timestamp(r["pit_anchor_utc"])
        anchor = anchor.tz_localize("UTC") if anchor.tzinfo is None else anchor.tz_convert("UTC")
        bell = (pd.Timestamp(r["entry_date"]).tz_localize(ET) + pd.Timedelta(hours=9, minutes=30))
        if not bell.tz_convert("UTC") > anchor:
            bad.append(f"{r['symbol']} {r['entry_date']}: entry bell {bell} is not after "
                       f"the {r['pit_anchor_field']} anchor {anchor}")
        g = per.get(r["symbol"])
        if g is not None and pd.notna(r.get("pit_dv_21")):
            day = pd.Timestamp(r["entry_date"])
            prior = g.loc[g.index < day, "dv"].tail(PIT_DV_WINDOW)
            if len(prior) >= 5:
                lo, hi = float(prior.min()), float(prior.max())
                v = float(r["pit_dv_21"])
                if not (lo - 1e-6 <= v <= hi + 1e-6):
                    bad.append(
                        f"{r['symbol']} {r['entry_date']}: pit_dv_21 {v:,.0f} is outside the "
                        f"range of the 21 PRIOR sessions [{lo:,.0f}, {hi:,.0f}] — it has seen "
                        f"the entry session"
                    )
    return bad


def E1_append(max_rows=None) -> dict:
    """Append newly pulled corpus rows to the text-and-return panel."""
    t0 = time.time()
    out_dir = OUT()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "news_returns_2025_26.parquet"

    existing = pd.read_parquet(path) if path.exists() else pd.DataFrame()
    watermark = ""
    if len(existing) and "first_seen_utc" in existing.columns:
        vals = existing["first_seen_utc"].dropna().astype(str)
        watermark = str(vals.max()) if len(vals) else ""

    sources = _label_sources()
    raw = _corpus_rows(sources, watermark, max_rows)
    # `before_calendar` and `pending_future_session` are OPPOSITE causes and were
    # one counter until the first live run put 3,370 rows in it: the Alpaca
    # backfill's 2015 rows (older than the bars) and tonight's rows (newer than
    # the bars) are not the same problem and do not have the same fix.
    stats = {"corpus_rows": len(raw), "no_ticker": 0, "no_symbol_bar": 0,
             "before_calendar": 0, "pending_future_session": 0,
             "no_bar_that_day": 0, "dup": 0, "kept": 0}

    if not BARS().exists():
        return {
            "job": "E1_append", "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
            "verdict": "REFUSED", "rows_appended": 0, "funnel": stats,
            "headline": f"REFUSED: no bars parquet at {BARS()} — nothing can be labelled",
            "next_test": "run P6_bars_and_regret to land prices_2025_26/bars.parquet, then re-run E1_append",
            "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    per, sessions = _load_bars()
    bench = per.get(BENCH)
    have = set(per)
    seen_keys = set()
    if len(existing) and {"raw_id", "symbol"} <= set(existing.columns):
        seen_keys = set(zip(existing["raw_id"].astype(str), existing["symbol"].astype(str)))

    new_rows = []
    for d in raw:
        syms = [s for s in (d.get("tickers") or []) if s]
        if not syms:
            stats["no_ticker"] += 1
            continue
        anchor, anchor_field = _anchor(d)
        day, pos = _entry_session(anchor, "", sessions)
        for s in syms[:8]:
            s = str(s).strip().upper()
            if s not in have:
                stats["no_symbol_bar"] += 1
                continue
            key = (str(d.get("raw_id") or ""), s)
            if key in seen_keys:
                stats["dup"] += 1
                continue
            if day is None:
                # Two opposite causes, counted apart. `before_calendar`: the row
                # predates the bars (the Alpaca backfill starts 2015; these bars
                # start 2025) and needs OLDER bars. `pending_future_session`: the
                # row is newer than the last bar and needs the NEXT session —
                # the normal state of anything pulled tonight.
                stats["before_calendar" if pos == "before_calendar"
                      else "pending_future_session"] += 1
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
            seen_keys.add(key)
            stats["kept"] += 1
            new_rows.append({
                "uid": d.get("raw_id"), "symbol": s,
                "first_seen_utc": d.get("first_seen_utc") or "",
                "published_utc": d.get("published_utc") or "",
                "pit_anchor_utc": anchor, "pit_anchor_field": anchor_field,
                "entry_date": day.date().isoformat(), "publish_position": pos,
                "source": d.get("source"), "pit_grade": d.get("pit_grade"),
                "independence_group": d.get("source"),
                "raw_id": str(d.get("raw_id") or ""),
                "title": (d.get("title") or "")[:400],
                "body": (d.get("body") or "")[:MAX_BODY],
                "r_oc": r_oc, "r_oo": r_oo,
                "x_oc": r_oc - b_oc, "x_oo": r_oo - b_oo,
                "dollar_vol": float(r["dv"]) if pd.notna(r["dv"]) else np.nan,
                "pit_dv_21": float(r["pit_dv_21"]) if pd.notna(r["pit_dv_21"]) else np.nan,
            })

    violations = _pit_verify(new_rows, per)
    receipt = {
        "job": "E1_append", "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
        "what": ("corpus rows from label_source sources only, labelled at the first "
                 "session OPEN strictly after the row's PIT anchor, each minus SPY, "
                 "with pit_dv_21 from the 21 sessions BEFORE the entry"),
        "pit_anchor_rule": (
            "native_stamp -> published_utc (the grade asserts the provider's own stamp "
            "is trustworthy, and anchoring a BACKFILL on first_seen would date 2015 news "
            "to today); first_seen_only -> first_seen_utc (the provider's stamp is a "
            "crawl time it may move, so only our own anchor is safe)"),
        "anchors_used": {
            f: sum(1 for r in new_rows if r["pit_anchor_field"] == f)
            for f in ("published_utc", "first_seen_utc")
        } if new_rows else {},
        "label_sources": sources,
        "skipped_index_state_sources": _skipped_sources(sources),
        "watermark_first_seen_utc": watermark or None,
        "funnel": stats,
        "rows_appended": 0,
        "panel_rows_before": int(len(existing)),
        "pit_violations": len(violations),
        "pit_violations_first_10": violations[:10],
        "paths": {"panel": str(path), "bars": str(BARS())},
        "wall_s": round(time.time() - t0, 2),
        "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    if violations:
        receipt["verdict"] = "REFUSED"
        receipt["panel_rows_after"] = int(len(existing))
        receipt["headline"] = (
            f"APPEND REFUSED: {len(violations)} PIT violations in {len(new_rows)} candidate rows. "
            f"Nothing was written — a partially-poisoned panel is worse than no append, "
            f"because the poison is then indistinguishable from data."
        )
        receipt["next_test"] = ("read pit_violations_first_10, fix the labelling anchor, re-run; "
                               "do NOT relax the check to make the append go green")
        (out_dir / "E1_append_receipt.json").write_text(
            json.dumps(receipt, indent=1, default=str), encoding="utf-8")
        return receipt

    if new_rows:
        combined = pd.concat([existing, pd.DataFrame(new_rows)], ignore_index=True) \
            if len(existing) else pd.DataFrame(new_rows)
        combined.to_parquet(path, index=False)
        receipt["rows_appended"] = len(new_rows)
        receipt["panel_rows_after"] = int(len(combined))
    else:
        receipt["panel_rows_after"] = int(len(existing))

    pending, ancient = stats["pending_future_session"], stats["before_calendar"]
    receipt["verdict"] = "APPENDED" if new_rows else ("NOTHING TO DO" if not raw else "PENDING")
    receipt["headline"] = (
        f"{len(new_rows):,} rows appended from {len(raw):,} corpus rows over "
        f"{len(sources)} labelling sources; {pending:,} awaiting a session that "
        f"has not happened yet; {ancient:,} older than the first bar; "
        f"0 PIT violations"
    )
    # The planner is starved without this (2026-09-10 §5): a receipt says what
    # the NEXT run should ask, not only what this one found.
    receipt["next_test"] = (
        ("re-run after the next session's bars land to label the pending rows"
         + (f"; {ancient:,} rows PREDATE the bars (the Alpaca backfill starts "
            f"2015-01-01 and prices_2025_26 starts 2025-01-02) and need older "
            f"bars or a --since on the backfill" if ancient else "")
         + "; when the panel passes ~20k labelled cells over 2+ months, run "
           "N3_frozen_embedding_head and C2 against the TF-IDF and shuffled controls")
        if (pending or ancient) else
        "pull more corpus (scripts/news_pull.py --source all --resume), then re-run"
    )
    (out_dir / "E1_append_receipt.json").write_text(
        json.dumps(receipt, indent=1, default=str), encoding="utf-8")
    return receipt


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--append", action="store_true",
                    help="N-C: append newly pulled corpus rows instead of rebuilding")
    ap.add_argument("--max-rows", type=int, default=None)
    a = ap.parse_args()
    if a.append:
        print(json.dumps(E1_append(max_rows=a.max_rows), indent=1, default=str))
    else:
        print(json.dumps(E1_news_return_panel(smoke=a.smoke), indent=1, default=str))
