"""The forward catalyst calendar: one point-in-time table of NEXT dates for the universe.

ROADMAP CH-35 (event nodes need next dates), CH-08 (freshness), module M2 UNIVERSE.

Before this module the system had two stored calendars and neither answered
"when does NVIDIA report?" on 2026-11-12: the lab's `pm_catalysts` read covers the
~12 PM-book tickers, and `scripts/contest_calendar.py` writes a table filtered to a
contest window that ended 2026-11-13. This module is the third and is meant to be
the one: every universe name, every pull kept.

THE STORE (append-only, never rewritten)
    <root>/forward_calendar/snapshots/fc_<YYYYmmddTHHMMSSZ>_<h6>.jsonl
        a `pull_header` row (ticker-list hash, requested count, scope), then one row
        per ticker per pull (`row_kind: earnings`) with `pulled_utc`, the date, the
        vendor's confirmation flag, the time of day, whether the event TIME is known,
        the last reported event, the source and the raw vendor fields; plus the macro
        half (`row_kind: macro` / `macro_refusal`) from `macro_calendar.macro_block()`.
    <root>/forward_calendar/snapshots/fc_<...>_receipt.json
        requested / answered / with-date / failed counts, both shares, the scope.
    <root>/forward_calendar/snapshots/fc_<...>_index.json
        file, pulled_utc range, row counts, the tickers in it: the reader decides from
        the index which files it must open, and a file shorter than its index is DAMAGED.
    A pull holds `forward_calendar/.pull.lock` (disk_guard.file_lock) for its whole
    run, writes `fc_<...>.partial.jsonl` batch by batch (resumable only by a pull with
    the SAME ticker list), and is renamed to its final name once, at the end. A final
    file or receipt that already exists is never replaced: the pull REFUSES.

POINT IN TIME
    Earnings dates are revised. "What did we believe on day D about ticker T's
    next report" is `next_dates([T], now=D)`: the newest row whose OWN
    `pulled_utc` is at or before D, never a later one. A ticker with no row by D
    is NOT_COVERED, which is a different fact from NO_DATE_IN_HORIZON (we looked
    and the vendor had no date inside the horizon), and a row older than
    `FORWARD_CALENDAR_STALE_DAYS` is CALENDAR_STALE, never served as fresh. A date
    that has HAPPENED by `now` (the event time when known, else the close of its New
    York session) is never "next": it is returned as `last_reported`. When a newer
    snapshot is damaged (unparseable lines, or fewer rows than its index), a ticker
    served from an older one is labelled FROM_OLDER_SNAPSHOT_NEWEST_DAMAGED.

RED WHEN BROKEN
    `check_coverage(receipt)` raises when fewer than FORWARD_CALENDAR_MIN_ANSWERED_SHARE
    of the names got any vendor answer (LOW_COVERAGE), or fewer than
    FORWARD_CALENDAR_MIN_DATE_SHARE of the issuers got a date (LOW_DATE_SHARE); the CLI
    turns either into rc 2. `p_forward_calendar` is the `system_health` row: UNKNOWN
    with no full-universe receipt, STALE when it is old, low, or its snapshot is
    damaged; dated by the receipt's own stamp (never mtime). `--tickers`/`--limit`
    pulls are PARTIAL and never count for freshness.

CLOCKS
    `pulled_utc` is UTC at the moment the batch answered. "Today" for a report
    date is the America/New_York date (the market's), never the PC's (UTC+8);
    nothing here calls `date.today()`.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional
from zoneinfo import ZoneInfo

from backend import config as C

SCHEMA = "forward-calendar/2"
SNAPSHOT_SUBDIR = "snapshots"
SOURCE = "yahoo/v7/finance/quote (yfinance YfData transport)"
NY = ZoneInfo("America/New_York")
LOCK_NAME = ".pull.lock"

# row status (what one pull saw)
DATE = "DATE"
NO_DATE = "NO_DATE"
FAILED = "FAILED"

# reader labels (what we believed at `now`)
DATE_IN_HORIZON = "DATE_IN_HORIZON"
NO_DATE_IN_HORIZON = "NO_DATE_IN_HORIZON"
NOT_COVERED = "NOT_COVERED"
CALENDAR_STALE = "CALENDAR_STALE"
FROM_OLDER_SNAPSHOT_NEWEST_DAMAGED = "FROM_OLDER_SNAPSHOT_NEWEST_DAMAGED"
LABELS = (DATE_IN_HORIZON, NO_DATE_IN_HORIZON, NOT_COVERED, CALENDAR_STALE,
          FROM_OLDER_SNAPSHOT_NEWEST_DAMAGED)
#: reason on a NO_DATE_IN_HORIZON whose stored date has already happened at `now`
LAST_REPORTED = "LAST_REPORTED"

# pull scope: only a full-universe pull counts for freshness
FULL_UNIVERSE = "FULL_UNIVERSE"
PARTIAL = "PARTIAL"

# refusal codes
LOW_COVERAGE = "LOW_COVERAGE"
LOW_DATE_SHARE = "LOW_DATE_SHARE"
UNIVERSE_EMPTY = "UNIVERSE_EMPTY"
DATA_ROOT_MISSING = "DATA_ROOT_MISSING"
SNAPSHOT_EXISTS = "SNAPSHOT_EXISTS"
RESUME_MISMATCH = "RESUME_MISMATCH"
PULL_LOCKED = "SKIP_PULL_LOCKED"

_FINAL_RE = re.compile(r"^fc_(\d{8}T\d{6}Z)_([0-9a-f]{6})\.jsonl$")
_PARTIAL_RE = re.compile(r"^fc_(\d{8}T\d{6}Z)_([0-9a-f]{6})\.partial\.jsonl$")
_RECEIPT_RE = re.compile(r"^fc_(\d{8}T\d{6}Z)_([0-9a-f]{6})_receipt\.json$")
_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,11}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
#: Raw vendor fields kept on every row (the rest of the quote is not calendar data).
RAW_FIELDS = ("earningsTimestamp", "earningsTimestampStart", "earningsTimestampEnd",
              "isEarningsDateEstimate", "earningsCallTimestampStart",
              "earningsCallTimestampEnd", "quoteType", "exchange", "fullExchangeName",
              "exchangeTimezoneName", "shortName", "marketState")
_NOT_ISSUER_TYPES = ("ETF", "INDEX", "MUTUALFUND", "CURRENCY", "CRYPTOCURRENCY", "FUTURE")


class ForwardCalendarRefused(RuntimeError):
    """The calendar pull or read refused, with a fixed code. Never 'nothing scheduled'."""

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        super().__init__(f"{code}: {message}" if message else code)


# ─────────────────────────────────────────────── small helpers

def _cfg(name: str, default: Any) -> Any:
    return getattr(C, name, default)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(d: Optional[datetime]) -> Optional[str]:
    return d.astimezone(timezone.utc).isoformat(timespec="seconds") if d else None


def _utc(v: Any) -> Optional[datetime]:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _stamp(d: datetime) -> str:
    return d.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _parse_stamp(s: str) -> Optional[datetime]:
    try:
        return datetime.strptime(s, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def market_date(now: datetime) -> date:
    """The America/New_York date of `now`: the market's day, not the PC's."""
    return now.astimezone(NY).date()


def norm_ticker(t: Any) -> Optional[str]:
    s = str(t or "").strip().upper().lstrip("$")
    return s if _TICKER_RE.match(s) else None


def yahoo_symbol(t: str) -> str:
    """BRK.B -> BRK-B (a US share class); 7203.T / 0700.HK keep their exchange suffix."""
    if "." in t:
        head, _, tail = t.rpartition(".")
        if head.isalpha() and len(tail) == 1 and tail.isalpha():
            return f"{head}-{tail}"
    return t


def store_dir(root: Path) -> Path:
    return Path(root) / str(_cfg("FORWARD_CALENDAR_DIRNAME", "forward_calendar"))


def snapshots_dir(root: Path) -> Path:
    return store_dir(root) / SNAPSHOT_SUBDIR


# ─────────────────────────────────────────────── 1. the universe

def _graph_companies(data_root: Path, now: datetime) -> tuple[set, dict]:
    import pandas as pd
    g = Path(data_root) / "universe_graph"
    latest = g / "latest.json"
    if not latest.is_file():
        return set(), {"status": "MISSING", "path": str(latest)}
    rec = json.loads(latest.read_text(encoding="utf-8"))
    built = _utc(rec.get("built_utc"))
    if built is None or built > now:
        return set(), {"status": "BUILT_AFTER_NOW_OR_UNDATED", "built_utc": rec.get("built_utc")}
    nodes = g / str(rec.get("build_id")) / "nodes.parquet"
    if not nodes.is_file():
        return set(), {"status": "NODES_MISSING", "path": str(nodes)}
    df = pd.read_parquet(nodes, columns=["id", "type"])
    syms = {norm_ticker(i.split(":", 1)[1]) for i in df.loc[df["type"] == "company", "id"]}
    syms.discard(None)
    return syms, {"status": "OK", "build_id": rec.get("build_id"), "stamp_utc": _iso(built),
                  "age_days": round((now - built).total_seconds() / 86400, 2), "n": len(syms)}


def _funnel(path: Path, now: datetime) -> tuple[set, dict]:
    if not Path(path).is_file():
        return set(), {"status": "MISSING", "path": str(path)}
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    t = _utc(d.get("generated_at"))
    if t is None or t > now:
        return set(), {"status": "GENERATED_AFTER_NOW_OR_UNDATED", "generated_at": d.get("generated_at")}
    syms = {norm_ticker(c.get("ticker")) for c in d.get("candidates") or [] if isinstance(c, dict)}
    syms.discard(None)
    return syms, {"status": "OK", "stamp_utc": _iso(t), "n": len(syms),
                  "age_days": round((now - t).total_seconds() / 86400, 2),
                  "stages": d.get("stages"), "path": str(path)}


def _pc_book(data_root: Path, now: datetime) -> tuple[set, dict]:
    p = Path(data_root) / "pc_book" / "state_latest.json"
    if not p.is_file():
        return set(), {"status": "MISSING", "path": str(p)}
    d = json.loads(p.read_text(encoding="utf-8"))
    t = _utc(d.get("t"))
    if t is None or t > now:
        return set(), {"status": "STAMPED_AFTER_NOW_OR_UNDATED", "t": d.get("t")}
    syms = {norm_ticker(x.get("symbol")) for x in d.get("positions") or [] if isinstance(x, dict)}
    syms.discard(None)
    return syms, {"status": "OK", "stamp_utc": _iso(t), "n": len(syms),
                  "age_days": round((now - t).total_seconds() / 86400, 2)}


def _book_dna(data_root: Path, now: datetime) -> tuple[set, dict]:
    """The newest `paper_accounts/book_dna_<stamp>.json` stamped at or before `now`:
    every paper account's holdings in one receipt (dated by the stamp in its NAME)."""
    d = Path(data_root) / "paper_accounts"
    rx = re.compile(r"^book_dna_(\d{4}-\d{2}-\d{2}T\d{6}Z)\.json$")
    best = None
    for f in d.glob("book_dna_*.json") if d.is_dir() else []:
        m = rx.match(f.name)
        t = datetime.strptime(m.group(1), "%Y-%m-%dT%H%M%SZ").replace(tzinfo=timezone.utc) if m else None
        if t is not None and t <= now and (best is None or t > best[0]):
            best = (t, f)
    if best is None:
        return set(), {"status": "MISSING", "path": str(d)}
    doc = json.loads(best[1].read_text(encoding="utf-8"))
    syms: set = set()
    for b in doc.get("books") or []:
        for t in (b.get("tickers") or []) if isinstance(b, dict) else []:
            s = norm_ticker(t)
            if s:
                syms.add(s)
    return syms, {"status": "OK", "file": best[1].name, "stamp_utc": _iso(best[0]), "n": len(syms),
                  "n_books": len(doc.get("books") or []),
                  "age_days": round((now - best[0]).total_seconds() / 86400, 2)}


def _llm_books(data_root: Path, now: datetime) -> tuple[set, dict]:
    p = Path(data_root) / "llm_portfolio" / "books.jsonl"
    if not p.is_file():
        return set(), {"status": "MISSING", "path": str(p)}
    lo = now - timedelta(days=int(_cfg("FORWARD_CALENDAR_BOOK_LOOKBACK_DAYS", 30)))
    syms: set = set()
    n_books, newest = 0, None
    with p.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                b = json.loads(line)
            except ValueError:
                continue
            t = _utc(b.get("frozen_utc"))
            if t is None or not (lo <= t <= now):
                continue
            n_books += 1
            newest = t if newest is None or t > newest else newest
            for pos in b.get("positions") or []:
                s = norm_ticker((pos or {}).get("ticker"))
                if s:
                    syms.add(s)
    return syms, {"status": "OK", "n": len(syms), "n_books_in_lookback": n_books,
                  "newest_frozen_utc": _iso(newest)}


def _bars_panel(data_root: Path) -> tuple[set, dict]:
    import pandas as pd
    p = Path(data_root) / "prices_2025_26" / "bars.parquet"
    if not p.is_file():
        return set(), {"status": "MISSING", "path": str(p)}
    s = pd.read_parquet(p, columns=["symbol"])["symbol"].drop_duplicates()
    syms = {norm_ticker(x) for x in s}
    syms.discard(None)
    return syms, {"status": "OK", "n": len(syms), "note": "survivor-selected panel (CLAUDE.md 09-22)"}


def build_universe(data_root: Path, now: datetime, *, funnel_path: Optional[Path] = None,
                   with_bars_panel: bool = False) -> dict:
    """The union of the universe graph's company nodes, the funnel's candidates, every
    name the PC book holds, every name any paper account holds (newest book_dna) and
    every name an LLM-selector book froze within the lookback. Each source carries its
    own stamp and age; a source stamped after `now` contributes nothing."""
    dr = Path(data_root)
    if not dr.is_dir():
        raise ForwardCalendarRefused(DATA_ROOT_MISSING, f"data root {dr} is not a directory")
    # the funnel snapshot lives beside the data root (backend/data/funnel_night10.json);
    # config.IC_FUNNEL_PATH is the code checkout's copy, used only when that is absent
    sib = dr.parent / "funnel_night10.json"
    fp = Path(funnel_path) if funnel_path else (sib if sib.is_file() else Path(_cfg("IC_FUNNEL_PATH", sib)))
    parts = {"universe_graph": _graph_companies(dr, now), "funnel": _funnel(fp, now),
             "pc_book": _pc_book(dr, now), "paper_accounts": _book_dna(dr, now),
             "llm_books": _llm_books(dr, now)}
    if with_bars_panel:
        parts["bars_panel"] = _bars_panel(dr)
    tickers: set = set()
    for syms, _meta in parts.values():
        tickers |= syms
    if not tickers:
        raise ForwardCalendarRefused(UNIVERSE_EMPTY, f"no source under {dr} gave a ticker: "
                                     + json.dumps({k: m for k, (_s, m) in parts.items()}, default=str))
    return {"tickers": sorted(tickers), "n": len(tickers),
            "sources": {k: m for k, (_s, m) in parts.items()}}



# ─────────────────────────────────────────────── 2. when has an event happened

def session_close_utc(d: date) -> datetime:
    """16:00 New York on `d`, in UTC (DST-aware)."""
    return datetime(d.year, d.month, d.day, 16, 0, tzinfo=NY).astimezone(timezone.utc)


def event_passed(day: Any, event_utc: Any, time_known: bool, now: datetime) -> bool:
    """True once the event has HAPPENED at `now`: at its own time when that is known,
    else once the New York session of its date has closed. Never a date-only compare
    against the New York date (a Tokyo 06:00 UTC report is over by New York's open)."""
    d = day if isinstance(day, date) else date.fromisoformat(str(day)[:10])
    t = _utc(event_utc) if time_known else None
    if t is not None:
        return t <= now
    return now >= session_close_utc(d)


# ─────────────────────────────────────────────── 3. parsing one vendor quote

def _ts(v: Any) -> Optional[datetime]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f <= 0:
        return None
    return datetime.fromtimestamp(f, tz=timezone.utc)


def _tz(us: bool, tz_name: Optional[str]) -> Any:
    if us:
        return NY
    try:
        return ZoneInfo(tz_name) if tz_name else timezone.utc
    except Exception:                                                  # noqa: BLE001
        return timezone.utc


def _day_and_timing(t: datetime, *, us: bool, tz_name: Optional[str]) -> tuple[date, str, bool]:
    """(report day, BMO/AMC/INTRA/UNKNOWN, time_known). A stamp at exactly 00:00:00
    UTC is how the vendor writes 'time not supplied' (contest_calendar.is_untimed_stamp):
    its day is the UTC date and its time unknown; so is a local-midnight stamp. Non-US
    listings keep the real event time (time_known) but timing is UNKNOWN: only the US
    09:30/16:00 session rule is applied."""
    if (t.hour, t.minute, t.second) == (0, 0, 0):
        return t.date(), "UNKNOWN", False
    loc = t.astimezone(_tz(us, tz_name))
    if (loc.hour, loc.minute, loc.second) == (0, 0, 0):
        return loc.date(), "UNKNOWN", False
    if not us:
        return loc.date(), "UNKNOWN", True
    mins = loc.hour * 60 + loc.minute
    timing = "AMC" if mins >= 16 * 60 else "BMO" if mins < 9 * 60 + 30 else "INTRA"
    return loc.date(), timing, True


def parse_quote(ticker: str, ysym: str, q: Optional[dict], *, pulled_utc: datetime,
                pull_id: str) -> dict:
    """One snapshot row from one vendor quote (None = the symbol was not in the reply).
    A candidate date that has already happened at `pulled_utc` is the LAST reported
    event, never the next one."""
    base = {"schema": SCHEMA, "row_kind": "earnings", "pull_id": pull_id,
            "pulled_utc": _iso(pulled_utc), "ticker": ticker, "yahoo_symbol": ysym,
            "source": SOURCE, "next_date": None, "date_end": None, "timing": None,
            "confirmation": None, "event_utc": None, "event_time_known": False,
            "call_utc": None, "last_reported_date": None, "last_reported_utc": None,
            "no_date_reason": None, "error": None}
    if q is None:
        return {**base, "status": FAILED, "error": "NOT_IN_RESPONSE", "raw": None}
    raw = {k: q.get(k) for k in RAW_FIELDS if k in q}
    base["raw"] = raw
    qt = str(q.get("quoteType") or "").upper()
    if qt in _NOT_ISSUER_TYPES:
        return {**base, "status": NO_DATE, "no_date_reason": f"NOT_AN_ISSUER ({qt})"}
    cands = []
    for k in ("earningsTimestampStart", "earningsTimestamp"):
        t = _ts(q.get(k))
        if t is not None:
            cands.append(t)
    if not cands:
        return {**base, "status": NO_DATE, "no_date_reason": "VENDOR_HAS_NO_EARNINGS_FIELDS"}
    us = "." not in ysym                    # no exchange suffix: a US listing
    tz_name = q.get("exchangeTimezoneName")
    est = q.get("isEarningsDateEstimate")
    future, past = [], []
    for t in sorted(set(cands)):
        d, tim, known = _day_and_timing(t, us=us, tz_name=tz_name)
        known = known and est is not True   # an estimated date's time is not information
        (past if event_passed(d, t, known, pulled_utc) else future).append((d, tim, t, known))
    if past:
        d, _tim, t, known = past[-1]
        base["last_reported_date"] = d.isoformat()
        base["last_reported_utc"] = _iso(t) if known else None
    if not future:
        return {**base, "status": NO_DATE, "no_date_reason": "ONLY_PAST_DATES"}
    d, tim, t, known = future[0]
    end = _ts(q.get("earningsTimestampEnd"))
    end_d = _day_and_timing(end, us=us, tz_name=tz_name)[0] if end is not None else None
    if est is True or (end_d is not None and end_d != d):
        conf, tim, known = "VENDOR_ESTIMATE", "UNKNOWN", False
    elif est is False:
        conf = "VENDOR_ANNOUNCED"
    else:
        conf = "UNKNOWN"
    call = _ts(q.get("earningsCallTimestampStart"))
    return {**base, "status": DATE, "next_date": d.isoformat(),
            "date_end": end_d.isoformat() if end_d else None, "timing": tim,
            "confirmation": conf, "event_utc": _iso(t), "event_time_known": bool(known),
            "call_utc": _iso(call)}


# ─────────────────────────────────────────────── 4. the default fetcher (network)

def yahoo_quote_batch(symbols: list[str]) -> dict[str, dict]:
    """{yahoo symbol: quote} for one batch, through yfinance's own transport. Raises on
    any transport or HTTP failure; a symbol the vendor does not know is simply ABSENT
    from the reply (the caller records it as FAILED NOT_IN_RESPONSE)."""
    from yfinance.data import YfData                                   # noqa: PLC0415
    from backend.services import data_fetcher as DF                    # noqa: PLC0415
    with DF._yf_lock:
        res = YfData().get_raw_json("https://query1.finance.yahoo.com/v7/finance/quote",
                                    params={"symbols": ",".join(symbols), "formatted": "false"},
                                    timeout=int(_cfg("FORWARD_CALENDAR_TIMEOUT_S", 30)))
    rows = ((res or {}).get("quoteResponse") or {}).get("result")
    if rows is None:
        raise RuntimeError(f"quoteResponse.result missing: {str((res or {}).get('quoteResponse'))[:160]}")
    return {str(r.get("symbol") or "").upper(): r for r in rows if isinstance(r, dict)}


def _is_rate_limit(exc: Exception) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    return "too many requests" in text or "rate limit" in text or "429" in text


# ─────────────────────────────────────────────── 5. reading a snapshot (damage counted)

def _valid_row(r: Any) -> bool:
    if not isinstance(r, dict):
        return False
    if r.get("row_kind") != "earnings":
        return True
    if not isinstance(r.get("ticker"), str) or _utc(r.get("pulled_utc")) is None:
        return False
    for k in ("next_date", "last_reported_date"):
        v = r.get(k)
        if v is not None:
            if not isinstance(v, str) or not _DATE_RE.match(v):
                return False
            try:
                date.fromisoformat(v)
            except ValueError:
                return False
    if r.get("status") not in (DATE, NO_DATE, FAILED):
        return False
    return not (r.get("status") == DATE and not r.get("next_date"))


def read_snapshot(p: Path) -> tuple[list[dict], int]:
    """(rows, n_bad): every line that is not valid UTF-8, not JSON, not an object, or an
    earnings row with a malformed date/stamp/status is COUNTED as bad, never dropped
    silently. A file that cannot be read at all is (rows=[], n_bad=-1)."""
    try:
        data = Path(p).read_bytes()
    except OSError:
        return [], -1
    rows, bad = [], 0
    for line in data.split(b"\n"):
        if not line.strip():
            continue
        try:
            r = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            bad += 1
            continue
        if not _valid_row(r):
            bad += 1
            continue
        rows.append(r)
    return rows, bad


def _read_jsonl(p: Path) -> list[dict]:
    return read_snapshot(p)[0]


# ─────────────────────────────────────────────── 6. the pull (locked, append-only, resumable)

def _append(fh: Any, rows: Iterable[dict]) -> None:
    for r in rows:
        fh.write(json.dumps(r, sort_keys=True, ensure_ascii=True, default=str) + "\n")
    fh.flush()
    os.fsync(fh.fileno())


def tickers_sha(tickers: list[str]) -> str:
    return hashlib.sha256(json.dumps(sorted(tickers)).encode()).hexdigest()


def _resumable_partial(snap: Path, now: datetime) -> Optional[Path]:
    max_h = float(_cfg("FORWARD_CALENDAR_RESUME_MAX_AGE_HOURS", 12.0))
    best = None
    for f in snap.glob("fc_*.partial.jsonl") if snap.is_dir() else []:
        m = _PARTIAL_RE.match(f.name)
        t = _parse_stamp(m.group(1)) if m else None
        if t is not None and timedelta(0) <= now - t <= timedelta(hours=max_h):
            if best is None or t > best[0]:
                best = (t, f)
    return best[1] if best else None


def pull(tickers: list[str], out_root: Path, *, fetch: Optional[Callable[[list[str]], dict]] = None,
         macro: Any = None, now_fn: Callable[[], datetime] = _utcnow,
         sleep_fn: Callable[[float], None] = time.sleep, batch_size: Optional[int] = None,
         universe_meta: Optional[dict] = None, resume: bool = True,
         scope: str = PARTIAL) -> dict:
    """Fetch the next earnings date for every ticker and append ONE snapshot, holding
    the store's OS lock for the whole run (a second pull refuses SKIP_PULL_LOCKED).

    `scope` is FULL_UNIVERSE only when the CLI pulled the whole universe; only such a
    receipt counts for freshness. Every requested ticker gets a row: DATE, NO_DATE
    (looked, vendor had none) or FAILED (with the error). Low coverage is NOT raised
    here (the rows are true observations and are kept); `check_coverage(receipt)` is
    the red exit."""
    from backend.services import disk_guard as DG                      # noqa: PLC0415
    want = []
    for t in tickers:
        s = norm_ticker(t)
        if s and s not in want:
            want.append(s)
    if not want:
        raise ForwardCalendarRefused(UNIVERSE_EMPTY, "no valid ticker to pull")
    snap = snapshots_dir(out_root)
    snap.mkdir(parents=True, exist_ok=True)
    try:
        with DG.file_lock(store_dir(out_root) / LOCK_NAME, timeout_s=0):
            return _pull_locked(want, out_root, snap, fetch=fetch or yahoo_quote_batch, macro=macro,
                                now_fn=now_fn, sleep_fn=sleep_fn, batch_size=batch_size,
                                universe_meta=universe_meta, resume=resume, scope=scope)
    except DG.FileLockTimeout as exc:
        raise ForwardCalendarRefused(PULL_LOCKED, f"another forward-calendar pull holds "
                                                  f"{store_dir(out_root) / LOCK_NAME}: {exc}") from exc


def _pull_locked(want: list[str], out_root: Path, snap: Path, *, fetch: Callable, macro: Any,
                 now_fn: Callable[[], datetime], sleep_fn: Callable[[float], None],
                 batch_size: Optional[int], universe_meta: Optional[dict], resume: bool,
                 scope: str) -> dict:
    bs = int(batch_size or _cfg("FORWARD_CALENDAR_BATCH_SIZE", 50))
    gap = float(_cfg("FORWARD_CALENDAR_BATCH_SLEEP_S", 2.0))
    backoff = float(_cfg("FORWARD_CALENDAR_RATE_LIMIT_BACKOFF_S", 60.0))
    sha = tickers_sha(want)
    started = now_fn()
    part = _resumable_partial(snap, started) if resume else None
    done: set = set()
    resumed_from = None
    if part is not None:
        rows0, _bad0 = read_snapshot(part)
        hdr = next((r for r in rows0 if r.get("row_kind") == "pull_header"), None)
        if hdr is None or hdr.get("tickers_sha") != sha or hdr.get("n_requested") != len(want):
            raise ForwardCalendarRefused(
                RESUME_MISMATCH,
                f"{part.name} was started for {((hdr or {}).get('n_requested'))} tickers "
                f"(list {str((hdr or {}).get('tickers_sha'))[:12]}), this pull asks for {len(want)} "
                f"(list {sha[:12]}): not adopted. Re-run with the same list, or `--no-resume` "
                f"to start a new pull (the partial is left in place)")
        resumed_from = part.name
        m = _PARTIAL_RE.match(part.name)
        pull_id = f"fc_{m.group(1)}_{m.group(2)}"
        scope = hdr.get("scope") or scope
        for r in rows0:
            if r.get("row_kind") == "earnings" and r.get("status") in (DATE, NO_DATE):
                done.add(r.get("ticker"))
    else:
        h = hashlib.sha256(json.dumps([_iso(started), sha]).encode()).hexdigest()[:6]
        pull_id = f"fc_{_stamp(started)}_{h}"
        part = snap / f"{pull_id}.partial.jsonl"
    final = snap / f"{pull_id}.jsonl"
    rec_p = snap / f"{pull_id}_receipt.json"
    if final.exists() or rec_p.exists():
        raise ForwardCalendarRefused(SNAPSHOT_EXISTS, f"{final.name} already exists; never overwritten")
    todo = [t for t in want if t not in done]
    batches = [todo[i:i + bs] for i in range(0, len(todo), bs)]
    n_requests, n_rate_limited, stopped = 0, 0, None
    with part.open("a", encoding="utf-8", newline="\n") as fh:
        if resumed_from is None:
            _append(fh, [{"schema": SCHEMA, "row_kind": "pull_header", "pull_id": pull_id,
                          "started_utc": _iso(started), "tickers_sha": sha,
                          "n_requested": len(want), "scope": scope}])
        for bi, batch in enumerate(batches):
            ymap = {yahoo_symbol(t): t for t in batch}
            if stopped:
                _append(fh, [{**parse_quote(t, y, None, pulled_utc=now_fn(), pull_id=pull_id),
                              "error": stopped} for y, t in ymap.items()])
                continue
            if bi:
                sleep_fn(gap)
            got, err = None, None
            for attempt in (1, 2):
                n_requests += 1
                try:
                    got = fetch(list(ymap))
                    err = None
                    break
                except Exception as exc:                               # noqa: BLE001
                    err = f"{type(exc).__name__}: {str(exc)[:160]}"
                    if _is_rate_limit(exc):
                        n_rate_limited += 1
                        if attempt == 1:
                            sleep_fn(backoff)
                            continue
                        stopped = "RATE_LIMITED_PULL_STOPPED"
                    break
            at = now_fn()
            rows = []
            for y, t in ymap.items():
                if got is None:
                    rows.append({**parse_quote(t, y, None, pulled_utc=at, pull_id=pull_id),
                                 "error": f"BATCH_FAILED {err}"})
                else:
                    rows.append(parse_quote(t, y, got.get(y.upper()), pulled_utc=at, pull_id=pull_id))
            _append(fh, rows)
        macro_rows = _macro_rows(macro, pull_id, now_fn) if macro is not False else []
        if macro_rows:
            _append(fh, macro_rows)
    rows, n_bad = read_snapshot(part)
    receipt = _receipt(rows, want, pull_id=pull_id, started=started, finished=now_fn(),
                       n_requests=n_requests, n_rate_limited=n_rate_limited, stopped=stopped,
                       resumed_from=resumed_from, universe_meta=universe_meta, batch_size=bs,
                       scope=scope, tickers_sha=sha, n_bad_lines=n_bad)
    if final.exists():
        raise ForwardCalendarRefused(SNAPSHOT_EXISTS, f"{final.name} appeared during the pull")
    os.replace(part, final)
    _write_json(rec_p, receipt)
    _write_json(snap / f"{pull_id}_index.json", _index(final, rows, scope))
    receipt["snapshot_path"] = str(final)
    receipt["receipt_path"] = str(rec_p)
    return receipt


def _write_json(p: Path, obj: dict) -> None:
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(obj, indent=1, sort_keys=True, default=str), encoding="utf-8")
    os.replace(tmp, p)


def _index(final: Path, rows: list[dict], scope: str) -> dict:
    ear = [r for r in rows if r.get("row_kind") == "earnings"]
    pts = sorted(str(r["pulled_utc"]) for r in rows if r.get("pulled_utc"))
    return {"schema": SCHEMA, "file": final.name, "scope": scope, "n_rows": len(rows),
            "n_earnings_rows": len(ear),
            "first_pulled_utc": pts[0] if pts else None, "last_pulled_utc": pts[-1] if pts else None,
            "usable_tickers": sorted({r["ticker"] for r in ear if r.get("status") in (DATE, NO_DATE)}),
            "failed_tickers": sorted({r["ticker"] for r in ear if r.get("status") == FAILED})}


def _macro_rows(macro: Any, pull_id: str, now_fn: Callable[[], datetime]) -> list[dict]:
    """The macro half, from `macro_calendar.macro_block()` (CPI/NFP via FRED, FOMC from
    the seeded table). A refused leg is stored as a `macro_refusal` row, never as an
    empty calendar. NOTE: macro_calendar dates its horizon by the PC's `date.today()`
    (not this module's clock); its rows are stored as it returns them."""
    if macro is None:
        from backend.services import macro_calendar as MC              # noqa: PLC0415
        macro = MC.macro_block
    try:
        blk = macro()
    except Exception as exc:                                           # noqa: BLE001
        return [{"schema": SCHEMA, "row_kind": "macro_refusal", "pull_id": pull_id,
                 "pulled_utc": _iso(now_fn()), "kind": "ALL",
                 "refusal": f"MACRO_BLOCK_RAISED {type(exc).__name__}: {str(exc)[:160]}"}]
    at = _iso(now_fn())
    out = [{"schema": SCHEMA, "row_kind": "macro", "pull_id": pull_id, "pulled_utc": at,
            "kind": e.get("kind"), "date": e.get("event_time"), "what": e.get("what"),
            "source": e.get("source"), "detail": e.get("detail") or {}}
           for e in blk.get("macro") or [] if e.get("event_time")]
    out += [{"schema": SCHEMA, "row_kind": "macro_refusal", "pull_id": pull_id, "pulled_utc": at,
             "kind": r.get("kind"), "refusal": r.get("refusal")} for r in blk.get("refusals") or []]
    out.append({"schema": SCHEMA, "row_kind": "macro_legs", "pull_id": pull_id, "pulled_utc": at,
                "legs": blk.get("legs"), "fomc_table": blk.get("fomc_table"),
                "horizon_days": blk.get("horizon_days")})
    return out


def _receipt(rows: list[dict], want: list[str], **kw: Any) -> dict:
    latest: dict[str, dict] = {}
    for r in rows:
        if r.get("row_kind") != "earnings":
            continue
        t = r.get("ticker")
        if t not in latest or str(r.get("pulled_utc")) >= str(latest[t].get("pulled_utc")):
            latest[t] = r
    st = {t: (latest.get(t) or {}).get("status") for t in want}
    n_req = len(want)
    n_date = sum(1 for v in st.values() if v == DATE)
    n_no = sum(1 for v in st.values() if v == NO_DATE)
    n_fail = sum(1 for v in st.values() if v == FAILED or v is None)
    not_issuer = sum(1 for t in want if str((latest.get(t) or {}).get("no_date_reason") or "")
                     .startswith("NOT_AN_ISSUER"))
    answered = n_date + n_no
    answered_share = round(answered / n_req, 4) if n_req else 0.0
    issuers = max(n_req - not_issuer, 0)
    date_share = round(n_date / issuers, 4) if issuers else 0.0
    # Issuers whose row carries the vendor's earnings fields at all: a next date, or only a
    # past one (it reported recently and the next date is not posted yet). The second kind is
    # seasonal, not a fault; a vendor that stops sending the fields lowers THIS share.
    n_past_only = sum(1 for t in want if (latest.get(t) or {}).get("status") == NO_DATE
                      and (latest.get(t) or {}).get("no_date_reason") == "ONLY_PAST_DATES")
    fields_share = round((n_date + n_past_only) / issuers, 4) if issuers else 0.0
    min_ans = float(_cfg("FORWARD_CALENDAR_MIN_ANSWERED_SHARE", 0.90))
    min_date = float(_cfg("FORWARD_CALENDAR_MIN_DATE_SHARE", 0.20))
    min_fields = float(_cfg("FORWARD_CALENDAR_MIN_FIELDS_SHARE", 0.80))
    status = (LOW_COVERAGE if answered_share < min_ans else
              LOW_DATE_SHARE if (date_share < min_date or fields_share < min_fields) else "OK")
    reasons: dict[str, int] = {}
    errors: dict[str, int] = {}
    conf: dict[str, int] = {}
    for t in want:
        r = latest.get(t) or {}
        if r.get("status") == NO_DATE:
            reasons[str(r.get("no_date_reason"))] = reasons.get(str(r.get("no_date_reason")), 0) + 1
        if r.get("status") == FAILED:
            e = str(r.get("error") or "")[:60]
            errors[e] = errors.get(e, 0) + 1
        if r.get("status") == DATE:
            conf[str(r.get("confirmation"))] = conf.get(str(r.get("confirmation")), 0) + 1
    macro = [r for r in rows if r.get("row_kind") == "macro"]
    mref = [r for r in rows if r.get("row_kind") == "macro_refusal"]
    return {"schema": SCHEMA, "receipt": "forward_calendar_pull", "pull_id": kw["pull_id"],
            "scope": kw["scope"], "tickers_sha": kw["tickers_sha"],
            "started_utc": _iso(kw["started"]), "finished_utc": _iso(kw["finished"]),
            "source": SOURCE, "batch_size": kw["batch_size"], "n_requests": kw["n_requests"],
            "n_rate_limited": kw["n_rate_limited"], "stopped": kw["stopped"],
            "resumed_from": kw["resumed_from"], "n_bad_lines": kw["n_bad_lines"],
            "requested": n_req, "answered": answered, "fetched": answered, "with_date": n_date,
            "no_date": n_no, "failed": n_fail, "not_an_issuer": not_issuer,
            "answered_share": answered_share, "min_answered_share": min_ans,
            "date_share": date_share, "min_date_share": min_date,
            "earnings_fields_share": fields_share, "min_earnings_fields_share": min_fields,
            "share_covered": date_share,
            "status": status,
            "no_date_reasons": reasons, "failure_errors": errors, "confirmation_counts": conf,
            "failed_tickers": sorted(t for t, v in st.items() if v in (FAILED, None))[:200],
            "macro": {"n_dates": len(macro), "n_refusals": len(mref),
                      "refusals": [{"kind": r.get("kind"), "refusal": r.get("refusal")} for r in mref]},
            "universe": kw.get("universe_meta")}


def check_coverage(receipt: dict) -> None:
    """Red when the pull returned (almost) nothing: raise with BOTH shares and the counts."""
    if receipt.get("status") != "OK":
        raise ForwardCalendarRefused(
            str(receipt.get("status")),
            f"answered {receipt.get('answered')} of {receipt.get('requested')} (share "
            f"{receipt.get('answered_share')}, floor {receipt.get('min_answered_share')}); "
            f"{receipt.get('with_date')} with a date (date share {receipt.get('date_share')}, floor "
            f"{receipt.get('min_date_share')}; earnings-fields share "
            f"{receipt.get('earnings_fields_share')}, floor "
            f"{receipt.get('min_earnings_fields_share')}); failed {receipt.get('failed')}, "
            f"no-date {receipt.get('no_date')} {receipt.get('no_date_reasons')}, "
            f"errors {receipt.get('failure_errors')}")


# ─────────────────────────────────────────────── 7. the reader (point in time)

def _load_index(snap: Path, pull_id: str) -> Optional[dict]:
    p = snap / f"{pull_id}_index.json"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    return d if isinstance(d, dict) else None


def _final_snapshots(root: Path, now: datetime) -> tuple[list[tuple[datetime, Path]], int]:
    snap = snapshots_dir(root)
    out, skipped = [], 0
    for f in snap.glob("fc_*.jsonl") if snap.is_dir() else []:
        m = _FINAL_RE.match(f.name)
        t = _parse_stamp(m.group(1)) if m else None
        if t is None:
            continue
        if t > now:
            skipped += 1
            continue
        out.append((t, f))
    return sorted(out), skipped


_SESSION_MEMO: dict = {}


def sessions_away(today: date, d: date) -> tuple[Optional[int], str]:
    """XNYS sessions s with today < s <= d (a report today = 0), via the project's
    `counterfactual_prices.sessions_between` / `sessions_after` (exchange_calendars,
    weekday arithmetic when absent; the basis is returned beside the count)."""
    if d < today:
        return None, "PASSED"
    key = (today, d)
    if key not in _SESSION_MEMO:
        from backend.services import counterfactual_prices as CP            # noqa: PLC0415
        n, basis = CP.sessions_between(today, d)
        is_session = CP.sessions_after(today - timedelta(days=1), 1)[0] == today
        _SESSION_MEMO[key] = (n if is_session else n + 1, basis)
    return _SESSION_MEMO[key]


def next_dates(tickers: Iterable[str], now: datetime, horizon_days: Optional[int] = None, *,
               root: Path, stale_days: Optional[float] = None) -> dict:
    """As of `now`: per ticker the newest row whose own `pulled_utc` <= `now` (a later
    row is never used), labelled DATE_IN_HORIZON / NO_DATE_IN_HORIZON / NOT_COVERED /
    CALENDAR_STALE / FROM_OLDER_SNAPSHOT_NEWEST_DAMAGED, with its age. A stored date
    that has happened by `now` is `last_reported`, never `date`.

    Snapshots are read NEWEST FIRST; a file is opened only when its index says it holds
    a ticker still unresolved (or it has no index / straddles `now`), and reading stops
    once every ticker has a usable row. `root` is the data root holding
    `forward_calendar/`."""
    now = _utc(now)
    if now is None:
        raise ForwardCalendarRefused("NOW_INVALID", "now must be a datetime")
    hz = int(horizon_days if horizon_days is not None else _cfg("FORWARD_CALENDAR_HORIZON_DAYS", 120))
    sd = float(stale_days if stale_days is not None else _cfg("FORWARD_CALENDAR_STALE_DAYS", 3.0))
    want: dict[str, None] = {}
    for t in tickers:
        s = norm_ticker(t)
        if s:
            want[s] = None
    snap = snapshots_dir(root)
    files, skipped = _final_snapshots(root, now)
    need = set(want)
    usable: dict[str, tuple[dict, datetime]] = {}
    failed: dict[str, dict] = {}
    damaged: list[dict] = []
    n_opened, n_rows_after_now = 0, 0
    for stamp, f in reversed(files):
        if not need:
            break
        m = _FINAL_RE.match(f.name)
        idx = _load_index(snap, f"fc_{m.group(1)}_{m.group(2)}")
        idx_tickers = None
        if idx is not None:
            idx_tickers = set(idx.get("usable_tickers") or []) | set(idx.get("failed_tickers") or [])
            last = _utc(idx.get("last_pulled_utc"))
            if last is not None and last <= now and not (need & idx_tickers):
                continue                                   # nothing we still need: not opened
        rows, n_bad = read_snapshot(f)
        n_opened += 1
        n_ear = sum(1 for r in rows if r.get("row_kind") == "earnings")
        short = (idx is not None and isinstance(idx.get("n_earnings_rows"), int)
                 and n_ear < idx["n_earnings_rows"])
        if n_bad or short:
            damaged.append({"file": f.name, "stamp_utc": _iso(stamp), "n_bad_lines": n_bad,
                            "rows_missing_vs_index": (idx["n_earnings_rows"] - n_ear) if short else 0,
                            "tickers": idx_tickers})
        found: dict[str, dict] = {}
        for r in rows:
            if r.get("row_kind") != "earnings" or r.get("ticker") not in need:
                continue
            pu = _utc(r.get("pulled_utc"))
            if pu > now:
                n_rows_after_now += 1
                continue
            if r.get("status") == FAILED:
                old = failed.get(r["ticker"])
                if old is None or pu > _utc(old["pulled_utc"]):
                    failed[r["ticker"]] = r
                continue
            old = found.get(r["ticker"])
            if old is None or pu >= _utc(old["pulled_utc"]):
                found[r["ticker"]] = r
        for t, r in found.items():
            usable[t] = (r, stamp)
        need -= set(found)
    today = market_date(now)
    out: dict[str, dict] = {}
    for t in want:
        u = usable.get(t)
        fl = failed.get(t)
        newer_damage = [d for d in damaged
                        if (u is None or _utc(d["stamp_utc"]) > u[1])
                        and (d["tickers"] is None or t in d["tickers"])]
        if u is None:
            out[t] = {"label": NOT_COVERED,
                      "reason": ("NEWEST_SNAPSHOT_DAMAGED" if newer_damage else
                                 "ONLY_FAILED_ATTEMPTS" if fl else "NO_ROW_BY_NOW"),
                      "damaged_snapshot": newer_damage[0]["file"] if newer_damage else None,
                      "last_error": (fl or {}).get("error"), "last_attempt_utc": (fl or {}).get("pulled_utc")}
            continue
        u_row, u_stamp = u
        pu = _utc(u_row["pulled_utc"])
        age = round((now - pu).total_seconds() / 86400, 3)
        rec = {"pulled_utc": u_row["pulled_utc"], "pull_id": u_row.get("pull_id"), "age_days": age,
               "date": None, "date_end": u_row.get("date_end"), "timing": u_row.get("timing"),
               "confirmation": u_row.get("confirmation"), "event_utc": u_row.get("event_utc"),
               "event_time_known": bool(u_row.get("event_time_known")),
               "source": u_row.get("source"), "row_status": u_row.get("status"),
               "no_date_reason": u_row.get("no_date_reason"),
               "last_reported": ({"date": u_row.get("last_reported_date"),
                                  "event_utc": u_row.get("last_reported_utc")}
                                 if u_row.get("last_reported_date") else None),
               "last_attempt_failed": bool(fl and _utc(fl["pulled_utc"]) > pu),
               "days_away": None, "days_away_basis": "calendar days from the New York date",
               "sessions_away": None, "sessions_away_basis": None}
        nd = u_row.get("next_date")
        happened = bool(nd) and event_passed(nd, u_row.get("event_utc"),
                                             bool(u_row.get("event_time_known")), now)
        if happened:
            rec["last_reported"] = {"date": nd, "event_utc": u_row.get("event_utc")
                                    if u_row.get("event_time_known") else None}
        elif nd:
            d = date.fromisoformat(nd)
            rec["date"] = nd
            rec["days_away"] = (d - today).days
            rec["sessions_away"], rec["sessions_away_basis"] = sessions_away(today, d)
        if newer_damage:
            dm = newer_damage[0]
            out[t] = {"label": FROM_OLDER_SNAPSHOT_NEWEST_DAMAGED,
                      "reason": f"{dm['file']} damaged ({dm['n_bad_lines']} bad line(s), "
                                f"{dm['rows_missing_vs_index']} row(s) missing vs its index); served "
                                f"from the older snapshot pulled {u_row['pulled_utc']}",
                      "damaged_snapshot": dm["file"], "damaged_snapshot_utc": dm["stamp_utc"], **rec}
        elif age > sd:
            out[t] = {"label": CALENDAR_STALE, "reason": f"newest row {age} d old > {sd} d", **rec}
        elif u_row.get("status") == NO_DATE:
            out[t] = {"label": NO_DATE_IN_HORIZON, "reason": u_row.get("no_date_reason"), **rec}
        elif happened:
            out[t] = {"label": NO_DATE_IN_HORIZON, "reason": LAST_REPORTED, **rec}
        elif rec["days_away"] > hz:
            out[t] = {"label": NO_DATE_IN_HORIZON, "reason": "BEYOND_HORIZON", **rec}
        else:
            out[t] = {"label": DATE_IN_HORIZON, "reason": None, **rec}
    counts = {lab: sum(1 for v in out.values() if v["label"] == lab) for lab in LABELS}
    return {"as_of": _iso(now), "market_date": today.isoformat(), "horizon_days": hz,
            "stale_days": sd, "store": str(snap), "n_snapshots_available": len(files),
            "n_snapshots_opened": n_opened,
            "n_snapshots_after_now_skipped": skipped, "n_rows_after_now_skipped": n_rows_after_now,
            "damaged_snapshots": [{k: v for k, v in d.items() if k != "tickers"} for d in damaged],
            "counts": counts, "tickers": out}


def next_macro(now: datetime, horizon_days: Optional[int] = None, *, root: Path) -> dict:
    """The macro rows of the newest snapshot pulled at or before `now`, within the horizon."""
    now = _utc(now)
    hz = int(horizon_days if horizon_days is not None else _cfg("FORWARD_CALENDAR_HORIZON_DAYS", 120))
    files, _ = _final_snapshots(root, now)
    for _t, f in reversed(files):
        rows = [r for r in read_snapshot(f)[0] if str(r.get("row_kind", "")).startswith("macro")
                and (_utc(r.get("pulled_utc")) or now) <= now]
        if not rows:
            continue
        today = market_date(now)
        lo, hi = today.isoformat(), (today + timedelta(days=hz)).isoformat()
        legs = next((r for r in rows if r["row_kind"] == "macro_legs"), {})
        dates = []
        for r in rows:
            ds = str(r.get("date") or "")[:10]
            if r["row_kind"] == "macro" and _DATE_RE.match(ds) and lo <= ds <= hi:
                dates.append({"date": ds, "kind": r.get("kind"), "what": r.get("what"),
                              "source": r.get("source"), "days_away": (date.fromisoformat(ds) - today).days})
        return {"status": "OK", "pull_id": rows[0].get("pull_id"), "pulled_utc": rows[0].get("pulled_utc"),
                "dates": dates,
                "refusals": [{"kind": r.get("kind"), "refusal": r.get("refusal")}
                             for r in rows if r["row_kind"] == "macro_refusal"],
                "legs": legs.get("legs"), "fomc_table": legs.get("fomc_table")}
    return {"status": "NO_MACRO_SNAPSHOT_BY_NOW", "dates": [], "refusals": []}


# ─────────────────────────────────────────────── 8. freshness (the health row)

def _receipts(root: Path, now: datetime) -> list[tuple[datetime, Path, dict]]:
    snap = snapshots_dir(root)
    out = []
    for f in snap.glob("fc_*_receipt.json") if snap.is_dir() else []:
        m = _RECEIPT_RE.match(f.name)
        t = _parse_stamp(m.group(1)) if m else None
        if t is None or t > now:
            continue
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            rec = {"_unreadable": True}
        out.append((t, f, rec if isinstance(rec, dict) else {"_unreadable": True}))
    return sorted(out, key=lambda x: x[0])


def newest_receipt(root: Path, now: datetime, *, full_only: bool = False) -> Optional[tuple[datetime, Path]]:
    for t, f, rec in reversed(_receipts(root, now)):
        if not full_only or rec.get("scope") == FULL_UNIVERSE:
            return t, f
    return None


def freshness(root: Path, now: datetime, *, stale_days: Optional[float] = None) -> dict:
    """{verdict ALIVE/STALE/UNKNOWN, evidence_utc, age_s, detail} from the newest
    FULL-UNIVERSE pull receipt (a `--tickers`/`--limit` receipt is PARTIAL: counted in
    the detail, never evidence), dated by its OWN `finished_utc` (never mtime). STALE
    when old, when its status is not OK, or when its snapshot is DAMAGED."""
    sd = float(stale_days if stale_days is not None else _cfg("FORWARD_CALENDAR_STALE_DAYS", 3.0))
    recs = _receipts(root, now)
    full = [x for x in recs if x[2].get("scope") == FULL_UNIVERSE]
    n_partial = len(recs) - len(full)
    if not full:
        return {"verdict": "UNKNOWN", "evidence_utc": None, "age_s": None,
                "detail": f"no FULL-UNIVERSE forward-calendar receipt under {snapshots_dir(root)} "
                          f"({n_partial} partial/unscoped receipt(s) ignored): no next date is known "
                          "for the universe"}
    name_t, p, rec = full[-1]
    t = _utc(rec.get("finished_utc")) or name_t
    age_s = round((now - t).total_seconds(), 1)
    snap_p = snapshots_dir(root) / f"{rec.get('pull_id')}.jsonl"
    rows, n_bad = read_snapshot(snap_p)
    idx = _load_index(snapshots_dir(root), str(rec.get("pull_id")))
    n_ear = sum(1 for r in rows if r.get("row_kind") == "earnings")
    short = idx is not None and isinstance(idx.get("n_earnings_rows"), int) and n_ear < idx["n_earnings_rows"]
    counts = (f"answered {rec.get('answered')}/{rec.get('requested')} (share {rec.get('answered_share')}, "
              f"floor {rec.get('min_answered_share')}), with a date {rec.get('with_date')} (date share "
              f"{rec.get('date_share')}, floor {rec.get('min_date_share')}), failed {rec.get('failed')}; "
              f"{n_partial} partial receipt(s) ignored")
    if n_bad or short:
        return {"verdict": "STALE", "evidence_utc": _iso(t), "age_s": age_s,
                "detail": f"{snap_p.name} DAMAGED: {n_bad} bad line(s)"
                          + (f", {idx['n_earnings_rows'] - n_ear} row(s) missing vs its index" if short else "")}
    if rec.get("status") != "OK":
        return {"verdict": "STALE", "evidence_utc": _iso(t), "age_s": age_s,
                "detail": f"{p.name}: {rec.get('status')} - {counts}"}
    verdict = "ALIVE" if age_s <= sd * 86400 else "STALE"
    return {"verdict": verdict, "evidence_utc": _iso(t), "age_s": age_s,
            "detail": f"{p.name}: {counts}; {age_s / 86400:.2f} d old (stale after {sd} d)"}


def p_forward_calendar(ctx: Any) -> Any:
    """`system_health` probe: one row, from `ctx.optimus_dir/forward_calendar/`."""
    from backend.services.system_health import ProbeResult                # noqa: PLC0415
    f = freshness(Path(ctx.optimus_dir), ctx.now)
    return ProbeResult(f["verdict"], f["evidence_utc"], f["age_s"], f["detail"],
                       proof="forward_calendar/snapshots/fc_<stamp>_receipt.json (scope FULL_UNIVERSE): "
                             "finished_utc, status, both shares; the snapshot's bad lines vs its index; "
                             "never mtime")


__all__ = ["CALENDAR_STALE", "DATE_IN_HORIZON", "FROM_OLDER_SNAPSHOT_NEWEST_DAMAGED",
           "ForwardCalendarRefused", "LABELS", "LAST_REPORTED", "LOW_COVERAGE", "LOW_DATE_SHARE",
           "NOT_COVERED", "NO_DATE_IN_HORIZON", "build_universe", "check_coverage", "event_passed",
           "freshness", "next_dates", "next_macro", "p_forward_calendar", "parse_quote", "pull",
           "read_snapshot", "yahoo_quote_batch"]
