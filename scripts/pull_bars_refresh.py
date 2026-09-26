"""Keep the bar panels current — the scheduled, incremental refresh they never had.

    python -m scripts.pull_bars_refresh              # refresh every panel that exists
    python -m scripts.pull_bars_refresh --dry-run    # print ages, pull nothing, write nothing
    python -m scripts.pull_bars_refresh --age        # the age line only (no network)

THE DEFECT THIS FIXES (review 2026-09-26 §1 row 1, §5 item 1)
=============================================================
`prices_2025_26/bars.parquet` and `prices_deep/bars.parquet` both ended at
**2026-09-21** on 2026-09-26, four sessions behind, and nothing refreshed them.
The writers (`night_p6_bars_and_regret`, `pull_deep_bars`, `pull_delisted_bars`)
are whole-history pulls reachable only from a hand-queued night job. Every
reader reported the gap as a normal skip ("bars unchanged since the last rank"),
so the PC-PAPER plan acted on a five-day-old ranking and every forward book was
graded only through 09-21. It is `funnel_night10.json` (CLAUDE.md, 2026-09-22)
in a new file.

WHAT THIS DOES
==============
For each panel that exists (the grader's 2025-26 panel, the ranker's deep
panel, the delisted-names panel) it pulls ONLY the tail — from
`newest - REFRESH_OVERLAP_DAYS` — for that panel's own symbols, with the same
credential resolver, host, feed (SIP) and adjustment (`all`) as P6, and merges:

* a new bar REPLACES the old bar on the same (symbol, date). The old newest date
  is always re-pulled because the 09-21 bars were pulled mid-session (ZYME's
  09-21 volume was 63,525 against ~1.1M on a full day);
* a bar for a session that has not CLOSED yet is dropped — the free plan will
  serve a partial bar for today, and a partial bar is a lie with a date on it;
* ADJUSTMENT DRIFT: with `adjustment=all`, every split or ex-dividend after the
  last pull rescales that symbol's WHOLE history. The overlap window is
  compared close-for-close (excluding the old newest date, which may be
  partial); a symbol whose overlap moved by more than `ADJ_REL_TOL` is re-pulled
  from the panel's own first date and its history replaced, so a panel never
  splices two adjustment bases into one series.

REFUSES, WITHOUT OVERWRITING, when: the credential does not authenticate; the
venue raises; the merged panel's newest date is older than before; the panel
lost symbols; or the swap cannot be made. The old file is untouched in every
one of those cases, and the receipt names which.

IDEMPOTENT: a second run with no new session writes nothing (`unchanged`), so
`sim_run.u_rank`'s size+mtime fingerprint does not move and nothing re-ranks.

Every run writes `prices_2025_26/bars_refresh/<run_id>.json` (never
overwritten) and appends one line to `bars_refresh_index.jsonl`.

THE AGE LINE
============
`bars_age()` is the one function every reader should call: newest bar date, the
last CLOSED XNYS session, and the number of sessions between them, read from
the parquet's own `date` column (row-group statistics; never `st_mtime` —
CLAUDE.md protocol item 7). `sim_run.u_plan` refuses to act when it exceeds
`config.BARS_MAX_AGE_SESSIONS`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config  # noqa: E402

_OPT = Path(_config.OPTIMUS_LEDGER_DIR)

#: The panels, by role. The ORDER is the order they are refreshed and printed.
PANELS: dict[str, Path] = {
    "grader_2025_26": _OPT / "prices_2025_26" / "bars.parquet",
    "ranker_deep": _OPT / "prices_deep" / "bars.parquet",
    "delisted": _OPT / "prices_deep" / "bars_delisted.parquet",
}

#: Which panels an age gate may read. The delisted panel is EXCLUDED on
#: purpose: its names stop trading by definition, so its newest bar lags by
#: construction and a gate on it could never go green (CLAUDE.md, "a gate that
#: cannot go green is a broken gate").
GATED_PANELS = ("grader_2025_26", "ranker_deep")

RECEIPT_DIR = _OPT / "prices_2025_26" / "bars_refresh"
INDEX = _OPT / "prices_2025_26" / "bars_refresh_index.jsonl"

#: Calendar days re-pulled behind a panel's newest bar: enough sessions to
#: compare closes for adjustment drift across a long weekend plus a holiday.
REFRESH_OVERLAP_DAYS = 10

#: Relative close difference in the overlap above which a symbol's history is
#: deemed re-adjusted (split / dividend) and re-pulled whole. A quarterly
#: dividend on a 1% yielder moves history by ~0.25%, far above this.
ADJ_REL_TOL = 1e-4

#: A US session is treated as CLOSED this long after 16:00 ET (the free SIP
#: plan serves with a 15-minute delay).
SESSION_CLOSED_AFTER_ET = dtime(16, 20)

#: Retries for the atomic swap: on Windows `os.replace` fails while another
#: process holds the destination open (a ranker subprocess mid-read).
SWAP_RETRIES = 10
SWAP_SLEEP_S = 3.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ============================================================ calendar + age

def _et(now_utc: datetime | None = None) -> datetime:
    from zoneinfo import ZoneInfo
    now_utc = now_utc or datetime.now(timezone.utc)
    return now_utc.astimezone(ZoneInfo("America/New_York"))


def _sessions(lo: date, hi: date) -> tuple[list[date], str]:
    """XNYS sessions in [lo, hi], and the calendar that produced them."""
    try:
        import exchange_calendars as xc                            # noqa: PLC0415
        cal = xc.get_calendar("XNYS", start="2015-01-01", end="2035-12-31")
        return [s.date() for s in cal.sessions_in_range(lo.isoformat(), hi.isoformat())], "XNYS"
    except Exception:                                              # noqa: BLE001
        out, d = [], lo
        while d <= hi:
            if d.weekday() < 5:
                out.append(d)
            d += timedelta(days=1)
        return out, "WEEKDAY_APPROX (exchange_calendars unavailable)"


def last_closed_session(now_utc: datetime | None = None) -> tuple[date, str]:
    """The most recent XNYS session whose close has passed, and the calendar."""
    et = _et(now_utc)
    today = et.date()
    days, cal = _sessions(today - timedelta(days=14), today)
    if days and days[-1] == today and et.time() < SESSION_CLOSED_AFTER_ET:
        days = days[:-1]
    return (days[-1] if days else today - timedelta(days=1)), cal


def sessions_behind(newest: date, last_closed: date) -> int:
    """Sessions after `newest` up to and including `last_closed` (0 when current)."""
    if newest >= last_closed:
        return 0
    days, _ = _sessions(newest + timedelta(days=1), last_closed)
    return len(days)


def newest_bar_date(path: Path) -> date | None:
    """The parquet's own newest `date`, from row-group statistics when present.

    Reads the file's CONTENT, never its mtime. None when the file is absent or
    carries no readable date.
    """
    path = Path(path)
    if not path.exists():
        return None
    import pyarrow.parquet as pq                                   # noqa: PLC0415
    try:
        f = pq.ParquetFile(path)
        i = f.schema_arrow.get_field_index("date")
        best = None
        for g in range(f.metadata.num_row_groups):
            st = f.metadata.row_group(g).column(i).statistics
            if st is None or not st.has_min_max:
                best = None
                break
            v = st.max
            best = v if best is None or v > best else best
        if best is None:
            import pyarrow.compute as pc                           # noqa: PLC0415
            best = pc.max(pq.read_table(path, columns=["date"])["date"]).as_py()
        if best is None:
            return None
        return best.date() if hasattr(best, "date") else date.fromisoformat(str(best)[:10])
    except Exception:                                              # noqa: BLE001
        return None


def bars_age(paths: dict[str, Path] | list[Path] | None = None, *,
             now_utc: datetime | None = None,
             max_age_sessions: int | None = None) -> dict:
    """Age of each panel in SESSIONS, and whether the oldest gated one is stale.

    `paths` defaults to the gated panels. A missing panel or an unreadable date
    is `UNKNOWN` and counts as stale: missing evidence is never fresh.
    """
    if paths is None:
        paths = {k: PANELS[k] for k in GATED_PANELS}
    elif not isinstance(paths, dict):
        paths = {f"{Path(p).parent.name}/{Path(p).name}": Path(p) for p in paths}
    limit = int(_config.BARS_MAX_AGE_SESSIONS if max_age_sessions is None
                else max_age_sessions)
    last, cal = last_closed_session(now_utc)
    per: dict[str, dict] = {}
    worst: int | None = 0
    newest_all: date | None = None
    for name, p in paths.items():
        nd = newest_bar_date(p)
        if nd is None:
            per[name] = {"path": str(p), "newest": None, "sessions_old": None,
                         "state": "UNKNOWN",
                         "why": "absent" if not Path(p).exists() else "no readable date column"}
            worst = None
            continue
        n = sessions_behind(nd, last)
        per[name] = {"path": str(p), "newest": nd.isoformat(), "sessions_old": n,
                     "state": "STALE" if n > limit else "FRESH"}
        if worst is not None:
            worst = max(worst, n)
        newest_all = nd if newest_all is None or nd < newest_all else newest_all
    stale = worst is None or worst > limit or not per
    newest_s = newest_all.isoformat() if newest_all else None
    line = (f"BARS_STALE: newest={newest_s} sessions_old={worst if worst is not None else 'UNKNOWN'}"
            f" (limit {limit}, last closed session {last.isoformat()}, {cal})"
            if stale else
            f"BARS_FRESH: newest={newest_s} sessions_old={worst} (limit {limit}, "
            f"last closed session {last.isoformat()})")
    return {"stale": bool(stale), "newest": newest_s,
            "sessions_old": worst, "max_age_sessions": limit,
            "last_closed_session": last.isoformat(), "calendar": cal,
            "panels": per, "line": line}


# ================================================================ the merge

def _pull_default(symbols: list[str], start: str) -> Any:
    """P6's own puller and credential resolver — imported, never re-implemented."""
    from scripts import night_p6_bars_and_regret as P6             # noqa: PLC0415
    kid, sec, src = P6.data_credential()
    print(f"    credential: {src}", flush=True)
    return P6.pull_bars(symbols, start, None, kid, sec), src


def drift_symbols(path: Path, new_df, *, overlap_start: date, newest: date) -> list[str]:
    """Symbols whose overlap closes moved by more than `ADJ_REL_TOL`.

    Compares dates in [overlap_start, newest) only: the old newest date may be
    a partial (mid-session) bar and would flag every symbol.
    """
    import pandas as pd                                            # noqa: PLC0415
    import pyarrow.parquet as pq                                   # noqa: PLC0415
    if new_df is None or not len(new_df):
        return []
    old = pq.read_table(path, columns=["symbol", "date", "close"],
                        filters=[("date", ">=", pd.Timestamp(overlap_start))]).to_pandas()
    old = old[old["date"] < pd.Timestamp(newest)]
    nw = new_df[["symbol", "date", "close"]].copy()
    nw["date"] = pd.to_datetime(nw["date"])
    cmp = old.merge(nw, on=["symbol", "date"], suffixes=("_old", "_new"))
    if not len(cmp):
        return []
    rel = (cmp["close_new"] - cmp["close_old"]).abs() / cmp["close_old"].abs().clip(lower=1e-12)
    return sorted(cmp.loc[rel > ADJ_REL_TOL, "symbol"].unique().tolist())


def merge_panel(old_path: Path, new_df, *, keep_through: date,
                repulled: Any = None, overlap_start: date | None = None) -> dict:
    """Merge `new_df` into the panel at `old_path`; return the merged TABLE and counts.

    Pure: writes nothing. `new_df` rows REPLACE old rows on (symbol, date).
    Rows after `keep_through` (a session not yet closed) are dropped from the
    new data. Symbols whose overlap closes disagree by more than `ADJ_REL_TOL`
    are returned in `readjusted`; when `repulled` (a full-history frame for
    them) is given, their old rows are replaced by it.
    """
    import pandas as pd                                            # noqa: PLC0415
    import pyarrow as pa                                           # noqa: PLC0415
    import pyarrow.compute as pc                                   # noqa: PLC0415
    import pyarrow.parquet as pq                                   # noqa: PLC0415

    old = pq.read_table(old_path)
    schema = old.schema
    old_syms = set(pc.unique(old["symbol"]).to_pylist())
    old_max = pc.max(old["date"]).as_py()
    old_max_d = old_max.date() if hasattr(old_max, "date") else date.fromisoformat(str(old_max)[:10])
    rows_before = old.num_rows
    first_d = pc.min(old["date"]).as_py()

    new = new_df.copy() if new_df is not None else pd.DataFrame(columns=schema.names)
    if len(new):
        new = new[new["symbol"].isin(old_syms)].copy()
        new["date"] = pd.to_datetime(new["date"])
        new = new[new["date"] <= pd.Timestamp(keep_through)]
    new_min = pd.Timestamp(new["date"].min()) if len(new) else None
    # The split must sit at or before the EARLIEST new row: a new row that
    # landed in the head would be concatenated beside its old twin.
    cands = [x for x in (pd.Timestamp(overlap_start) if overlap_start else None, new_min)
             if x is not None]
    split_at = min(cands) if cands else None

    # --- adjustment drift: compare the overlap BEFORE the old newest date
    readjusted: list[str] = []
    if split_at is not None and len(new):
        tail_mask = pc.greater_equal(old["date"], pa.scalar(split_at.to_pydatetime(), pa.timestamp("ns")))
        old_tail = old.filter(tail_mask).to_pandas()
        cmp = old_tail[old_tail["date"] < pd.Timestamp(old_max_d)].merge(
            new[["symbol", "date", "close"]], on=["symbol", "date"], suffixes=("_old", "_new"))
        if len(cmp):
            rel = (cmp["close_new"] - cmp["close_old"]).abs() / cmp["close_old"].abs().clip(lower=1e-12)
            readjusted = sorted(cmp.loc[rel > ADJ_REL_TOL, "symbol"].unique().tolist())
    else:
        old_tail = old.slice(0, 0).to_pandas()
        tail_mask = None

    # --- head: every old row before the split, minus re-pulled symbols
    if tail_mask is not None:
        head = old.filter(pc.invert(tail_mask))
    else:
        head = old
    replace_syms = set(readjusted) if repulled is not None else set()
    if replace_syms:
        head = head.filter(pc.invert(pc.is_in(head["symbol"], pa.array(sorted(replace_syms)))))

    # --- tail: old tail overridden by new on (symbol, date)
    cols = schema.names
    new_c = new[cols] if len(new) else pd.DataFrame(columns=cols)
    tail = pd.concat([old_tail[cols], new_c], ignore_index=True)
    tail = tail.drop_duplicates(["symbol", "date"], keep="last")
    if replace_syms:
        tail = tail[~tail["symbol"].isin(replace_syms)]
        rp = repulled[repulled["symbol"].isin(replace_syms)].copy()
        rp["date"] = pd.to_datetime(rp["date"])
        rp = rp[(rp["date"] >= pd.Timestamp(first_d)) & (rp["date"] <= pd.Timestamp(keep_through))]
        tail = pd.concat([tail, rp[cols]], ignore_index=True).drop_duplicates(["symbol", "date"], keep="last")
    # schema-faithful: integer columns may carry None from the venue
    for c, t in zip(schema.names, schema.types):
        if pa.types.is_integer(t):
            tail[c] = pd.to_numeric(tail[c], errors="coerce").fillna(0).astype("int64")
        elif pa.types.is_floating(t):
            tail[c] = pd.to_numeric(tail[c], errors="coerce").astype("float64")
    tail_t = pa.Table.from_pandas(tail[cols], schema=schema.remove_metadata(), preserve_index=False)
    merged = pa.concat_tables([head.cast(schema.remove_metadata()), tail_t])
    merged = merged.sort_by([("symbol", "ascending"), ("date", "ascending")])

    n_keys = merged.group_by(["symbol", "date"]).aggregate([]).num_rows
    new_max = pc.max(merged["date"]).as_py()
    new_max_d = new_max.date() if hasattr(new_max, "date") else date.fromisoformat(str(new_max)[:10])
    new_syms = set(pc.unique(merged["symbol"]).to_pylist())
    changed_tail = True
    if not readjusted:
        a = old_tail[cols].sort_values(["symbol", "date"]).reset_index(drop=True)
        b = tail[cols].sort_values(["symbol", "date"]).reset_index(drop=True)
        try:
            changed_tail = not (len(a) == len(b) and a.equals(b.astype(a.dtypes.to_dict())))
        except Exception:                                          # noqa: BLE001
            changed_tail = True
    return {
        "table": merged,
        "rows_before": int(rows_before), "rows_after": int(merged.num_rows),
        "rows_added": int(merged.num_rows - rows_before),
        "symbols_before": len(old_syms), "symbols_after": len(new_syms),
        "newest_before": old_max_d.isoformat(), "newest_after": new_max_d.isoformat(),
        "first_date": str(first_d)[:10],
        "readjusted_symbols": readjusted,
        "duplicate_keys": int(merged.num_rows - n_keys),
        "changed": bool(changed_tail or readjusted or merged.num_rows != rows_before),
    }


def _swap(table, dst: Path) -> tuple[bool, str]:
    """Write to a sibling tmp, read it back, then atomically replace."""
    import pyarrow.parquet as pq                                   # noqa: PLC0415
    tmp = dst.with_name(f"{dst.name}.refresh.{os.getpid()}.tmp")
    try:
        pq.write_table(table, tmp)
        back = pq.ParquetFile(tmp).metadata.num_rows
        if back != table.num_rows:
            tmp.unlink(missing_ok=True)
            return False, f"read-back {back} rows != written {table.num_rows}"
        last = ""
        for _ in range(SWAP_RETRIES):
            try:
                os.replace(tmp, dst)
                return True, "swapped"
            except PermissionError as exc:
                last = f"{type(exc).__name__}: {exc}"
                time.sleep(SWAP_SLEEP_S)
        tmp.unlink(missing_ok=True)
        return False, f"os.replace failed {SWAP_RETRIES}x (file held open?): {last[:160]}"
    except Exception as exc:                                       # noqa: BLE001
        tmp.unlink(missing_ok=True)
        return False, f"{type(exc).__name__}: {str(exc)[:200]}"


def refresh(panels: dict[str, Path] | None = None, *, now_utc: datetime | None = None,
            dry_run: bool = False,
            puller: Callable[[list[str], str], Any] | None = None,
            receipt_dir: Path | None = None, index: Path | None = None) -> dict:
    """Refresh every panel that exists. Returns the receipt (and writes it).

    `puller(symbols, start) -> (DataFrame, credential_source)` is the network
    seam; tests inject a fake.
    """
    import pandas as pd                                            # noqa: PLC0415
    import pyarrow.compute as pc                                   # noqa: PLC0415
    import pyarrow.parquet as pq                                   # noqa: PLC0415

    t0 = time.time()
    panels = dict(panels or PANELS)
    puller = puller or _pull_default
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    keep_through, cal = last_closed_session(now_utc)
    before = bars_age({k: v for k, v in panels.items() if k in GATED_PANELS} or panels,
                      now_utc=now_utc)
    receipt: dict = {"receipt": "bars_refresh", "run_id": run_id,
                     "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
                     "started_utc": _now(), "dry_run": bool(dry_run),
                     "last_closed_session": keep_through.isoformat(), "calendar": cal,
                     "age_before": before, "panels": {}}

    present = {k: Path(p) for k, p in panels.items() if Path(p).exists()}
    for k, p in panels.items():
        if k not in present:
            receipt["panels"][k] = {"path": str(p), "status": "absent"}
    if not present:
        receipt["status"] = "refused"
        receipt["reason"] = "no panel exists to refresh"
        return _finish(receipt, t0, receipt_dir, index, now_utc=now_utc, panels=panels, write=not dry_run)

    sym_by: dict[str, set[str]] = {}
    starts: list[date] = []
    for k, p in present.items():
        nd = newest_bar_date(p)
        t = pq.read_table(p, columns=["symbol"])
        sym_by[k] = set(pc.unique(t["symbol"]).to_pylist())
        if nd is not None:
            starts.append(nd - timedelta(days=REFRESH_OVERLAP_DAYS))
    start = min(starts) if starts else keep_through - timedelta(days=REFRESH_OVERLAP_DAYS)
    all_syms = sorted(set().union(*sym_by.values()))
    receipt["pull"] = {"start": start.isoformat(), "symbols": len(all_syms),
                       "feed": "sip", "adjustment": "all",
                       "keep_through": keep_through.isoformat()}
    if dry_run:
        receipt["status"] = "dry_run"
        return _finish(receipt, t0, receipt_dir, index, now_utc=now_utc, panels=panels, write=False)

    try:
        new_df, cred = puller(all_syms, start.isoformat())
    except BaseException as exc:                                   # noqa: BLE001  SystemExit from the credential refusal
        receipt["status"] = "refused"
        receipt["reason"] = f"pull failed, nothing overwritten: {type(exc).__name__}: {str(exc)[:300]}"
        return _finish(receipt, t0, receipt_dir, index, now_utc=now_utc, panels=panels, write=True)
    receipt["pull"]["credential_source"] = cred
    receipt["pull"]["rows_returned"] = int(len(new_df)) if new_df is not None else 0
    if new_df is None or not len(new_df):
        receipt["status"] = "refused"
        receipt["reason"] = "the venue returned no bars; nothing overwritten"
        return _finish(receipt, t0, receipt_dir, index, now_utc=now_utc, panels=panels, write=True)

    # first pass: which symbols drifted, per panel (reads only each tail)
    drift_by: dict[str, list[str]] = {}
    firsts: list[date] = []
    for k, p in present.items():
        nd = newest_bar_date(p)
        drift_by[k] = drift_symbols(p, new_df, overlap_start=nd - timedelta(days=REFRESH_OVERLAP_DAYS),
                                    newest=nd) if nd else []
        if drift_by[k]:
            import pyarrow.compute as _pc                          # noqa: PLC0415
            firsts.append(_pc.min(pq.read_table(p, columns=["date"])["date"]).as_py().date())
    drift = sorted(set().union(*[set(v) for v in drift_by.values()]))
    repulled = None
    if drift:
        first = min(firsts)
        print(f"    {len(drift)} symbol(s) re-adjusted since the last pull; re-pulling "
              f"their history from {first}", flush=True)
        try:
            repulled, _ = puller(drift, first.isoformat())
        except BaseException as exc:                               # noqa: BLE001
            receipt["status"] = "refused"
            receipt["reason"] = (f"re-pull of {len(drift)} re-adjusted symbol(s) failed; "
                                 f"splicing two adjustment bases is refused, nothing "
                                 f"overwritten: {type(exc).__name__}: {str(exc)[:200]}")
            return _finish(receipt, t0, receipt_dir, index, now_utc=now_utc, panels=panels, write=True)
    receipt["readjusted_symbols"] = {"n": len(drift), "sample": drift[:25]}

    statuses: list[str] = []
    for k, p in present.items():
        m = merge_panel(p, new_df, keep_through=keep_through, repulled=repulled,
                        overlap_start=newest_bar_date(p) - timedelta(days=REFRESH_OVERLAP_DAYS))
        table = m.pop("table")
        row = {"path": str(p), **{kk: v for kk, v in m.items() if kk != "readjusted_symbols"},
               "readjusted": len(m["readjusted_symbols"])}
        if m["newest_after"] < m["newest_before"]:
            row["status"], row["reason"] = "refused", "merged newest date is OLDER than before"
        elif m["duplicate_keys"]:
            row["status"], row["reason"] = "refused", (
                f"merged panel carries {m['duplicate_keys']} duplicate (symbol, date) keys")
        elif m["symbols_after"] < m["symbols_before"]:
            row["status"], row["reason"] = "refused", (
                f"merged panel lost symbols ({m['symbols_before']} -> {m['symbols_after']})")
        elif not m["changed"]:
            row["status"] = "unchanged"
        else:
            ok, why = _swap(table, p)
            row["status"] = "ok" if ok else "refused"
            row["swap"] = why
            if not ok:
                row["reason"] = why
        del table
        statuses.append(row["status"])
        receipt["panels"][k] = row
        print(f"    {k}: {row['status']}  rows {row['rows_before']:,} -> {row['rows_after']:,} "
              f"(+{row['rows_added']:,})  newest {row['newest_before']} -> {row['newest_after']}"
              f"  symbols {row['symbols_after']:,}", flush=True)
    receipt["status"] = ("refused" if "refused" in statuses else
                         "ok" if "ok" in statuses else "unchanged")
    return _finish(receipt, t0, receipt_dir, index, now_utc=now_utc, panels=panels, write=True)


def _finish(receipt: dict, t0: float, receipt_dir: Path | None, index: Path | None,
            *, write: bool, now_utc: datetime | None = None,
            panels: dict[str, Path] | None = None) -> dict:
    gated = {k: v for k, v in (panels or PANELS).items() if k in GATED_PANELS}
    after = bars_age(gated or panels, now_utc=now_utc)
    receipt["age_after"] = after
    receipt["line"] = after["line"]
    receipt["elapsed_s"] = round(time.time() - t0, 1)
    receipt["written_utc"] = _now()
    added = sum(int((r or {}).get("rows_added") or 0) for r in receipt["panels"].values())
    receipt["headline"] = (f"bars refresh {receipt.get('status')}: +{added:,} rows; "
                           f"{after['line']}"
                           + (f"; {receipt['reason']}" if receipt.get("reason") else ""))
    if write:
        rd = Path(receipt_dir or RECEIPT_DIR)
        rd.mkdir(parents=True, exist_ok=True)
        path = rd / f"{receipt['run_id']}.json"
        path.write_text(json.dumps(receipt, indent=1, default=str), encoding="utf-8")
        receipt["path"] = str(path)
        ix = Path(index or INDEX)
        with ix.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"run_id": receipt["run_id"], "status": receipt.get("status"),
                                 "rows_added": added, "newest": after.get("newest"),
                                 "sessions_old": after.get("sessions_old"),
                                 "receipt": str(path), "written_utc": receipt["written_utc"]},
                                default=str) + "\n")
    return receipt


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--age", action="store_true", help="print the age line only (no network)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.age:
        age = bars_age()
        print(json.dumps(age, indent=1) if a.json else age["line"])
        return 0
    rec = refresh(dry_run=a.dry_run)
    if a.json:
        print("<<<" + json.dumps({k: rec.get(k) for k in
                                  ("status", "headline", "line", "path", "panels", "reason")},
                                 default=str) + ">>>")
    print(rec["headline"])
    # rc 2 = REFUSED (nothing overwritten). A refusal is a finding the caller must
    # read, and a subprocess that exits 0 on refusal is how 2026-09-24's funnel
    # remedy reported success while changing nothing.
    return 2 if rec.get("status") == "refused" else 0


if __name__ == "__main__":
    raise SystemExit(main())
