"""The forward catalyst calendar: one point-in-time table of NEXT dates for the universe.

ROADMAP CH-35 (event nodes need next dates), CH-08 (freshness), module M2 UNIVERSE.

Before this module the system had two stored calendars and neither answered
"when does NVIDIA report?" on 2026-11-12: the lab's `pm_catalysts` read covers the
~12 PM-book tickers, and `scripts/contest_calendar.py` writes a table filtered to a
contest window that ended 2026-11-13. This module is the third and is meant to be
the one: every universe name, every pull kept.

THE STORE (append-only, never rewritten)
    <root>/forward_calendar/snapshots/fc_<YYYYmmddTHHMMSSZ>_<h6>.jsonl
        one row per ticker per pull (`row_kind: earnings`) with `pulled_utc`, the
        date, the vendor's confirmation flag, the time of day, the source and the
        raw vendor fields; plus the macro half (`row_kind: macro` / `macro_refusal`)
        from `macro_calendar.macro_block()`, stored the same way.
    <root>/forward_calendar/snapshots/fc_<...>_receipt.json
        requested / fetched / failed / no-date counts and the share covered.
    A pull writes `fc_<...>.partial.jsonl` batch by batch (resumable), and is
    renamed to its final name once, at the end. A final file or receipt that
    already exists is never replaced: the pull REFUSES.

POINT IN TIME
    Earnings dates are revised. "What did we believe on day D about ticker T's
    next report" is `next_dates([T], now=D)`: the newest row whose OWN
    `pulled_utc` is at or before D, never a later one. A ticker with no row by D
    is NOT_COVERED, which is a different fact from NO_DATE_IN_HORIZON (we looked
    and the vendor had no date inside the horizon), and a row older than
    `FORWARD_CALENDAR_STALE_DAYS` is CALENDAR_STALE, never served as fresh.

RED WHEN BROKEN
    `check_coverage(receipt)` raises `ForwardCalendarRefused(LOW_COVERAGE)` when
    fewer than `FORWARD_CALENDAR_MIN_DATE_SHARE` of the issuers asked for came
    back with a date; the CLI turns that into rc 2. `p_forward_calendar` is the
    `system_health` row: UNKNOWN with no receipt, STALE when the newest receipt is
    old or was a low-coverage pull, dated by the receipt's own stamp (never mtime).

CLOCKS
    `pulled_utc` is UTC at the moment the batch answered. "Today" for a report
    date is the America/New_York date (the market's), not the PC's (UTC+8).
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

SCHEMA = "forward-calendar/1"
SNAPSHOT_SUBDIR = "snapshots"
SOURCE = "yahoo/v7/finance/quote (yfinance YfData transport)"
NY = ZoneInfo("America/New_York")

# row status (what one pull saw)
DATE = "DATE"
NO_DATE = "NO_DATE"
FAILED = "FAILED"

# reader labels (what we believed at `now`)
DATE_IN_HORIZON = "DATE_IN_HORIZON"
NO_DATE_IN_HORIZON = "NO_DATE_IN_HORIZON"
NOT_COVERED = "NOT_COVERED"
CALENDAR_STALE = "CALENDAR_STALE"
LABELS = (DATE_IN_HORIZON, NO_DATE_IN_HORIZON, NOT_COVERED, CALENDAR_STALE)

# refusal codes
LOW_COVERAGE = "LOW_COVERAGE"
UNIVERSE_EMPTY = "UNIVERSE_EMPTY"
DATA_ROOT_MISSING = "DATA_ROOT_MISSING"
SNAPSHOT_EXISTS = "SNAPSHOT_EXISTS"

_FINAL_RE = re.compile(r"^fc_(\d{8}T\d{6}Z)_([0-9a-f]{6})\.jsonl$")
_PARTIAL_RE = re.compile(r"^fc_(\d{8}T\d{6}Z)_([0-9a-f]{6})\.partial\.jsonl$")
_RECEIPT_RE = re.compile(r"^fc_(\d{8}T\d{6}Z)_([0-9a-f]{6})_receipt\.json$")
_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,11}$")
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


# ─────────────────────────────────────────────── 2. parsing one vendor quote

def _ts(v: Any) -> Optional[datetime]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f <= 0:
        return None
    return datetime.fromtimestamp(f, tz=timezone.utc)


def _day_and_timing(t: datetime, *, us: bool, tz_name: Optional[str]) -> tuple[date, str]:
    """(report day, BMO/AMC/INTRA/UNKNOWN). A stamp at exactly 00:00:00 UTC is how
    the vendor writes 'time not supplied' (contest_calendar.is_untimed_stamp): its
    day is the UTC date and its time UNKNOWN."""
    if (t.hour, t.minute, t.second) == (0, 0, 0):
        return t.date(), "UNKNOWN"
    if not us:
        try:
            tz = ZoneInfo(tz_name) if tz_name else timezone.utc
        except Exception:                                              # noqa: BLE001
            tz = timezone.utc
        return t.astimezone(tz).date(), "UNKNOWN"
    loc = t.astimezone(NY)
    if (loc.hour, loc.minute) == (0, 0):
        return loc.date(), "UNKNOWN"
    mins = loc.hour * 60 + loc.minute
    timing = "AMC" if mins >= 16 * 60 else "BMO" if mins < 9 * 60 + 30 else "INTRA"
    return loc.date(), timing


def parse_quote(ticker: str, ysym: str, q: Optional[dict], *, pulled_utc: datetime,
                pull_id: str) -> dict:
    """One snapshot row from one vendor quote (None = the symbol was not in the reply)."""
    base = {"schema": SCHEMA, "row_kind": "earnings", "pull_id": pull_id,
            "pulled_utc": _iso(pulled_utc), "ticker": ticker, "yahoo_symbol": ysym,
            "source": SOURCE, "next_date": None, "date_end": None, "timing": None,
            "confirmation": None, "event_utc": None, "call_utc": None,
            "no_date_reason": None, "error": None}
    if q is None:
        return {**base, "status": FAILED, "error": "NOT_IN_RESPONSE", "raw": None}
    raw = {k: q.get(k) for k in RAW_FIELDS if k in q}
    base["raw"] = raw
    qt = str(q.get("quoteType") or "").upper()
    if qt in _NOT_ISSUER_TYPES:
        return {**base, "status": NO_DATE, "no_date_reason": f"NOT_AN_ISSUER ({qt})"}
    today = market_date(pulled_utc)
    cands = []
    for k in ("earningsTimestampStart", "earningsTimestamp"):
        t = _ts(q.get(k))
        if t is not None:
            cands.append(t)
    if not cands:
        return {**base, "status": NO_DATE, "no_date_reason": "VENDOR_HAS_NO_EARNINGS_FIELDS"}
    us = "." not in ysym                    # no exchange suffix: a US listing
    tz_name = q.get("exchangeTimezoneName")
    future = []
    for t in sorted(set(cands)):
        d, tim = _day_and_timing(t, us=us, tz_name=tz_name)
        if d >= today:
            future.append((d, tim, t))
    if not future:
        return {**base, "status": NO_DATE, "no_date_reason": "ONLY_PAST_DATES",
                "event_utc": _iso(max(cands))}
    d, tim, t = future[0]
    end = _ts(q.get("earningsTimestampEnd"))
    end_d = _day_and_timing(end, us=us, tz_name=tz_name)[0] if end is not None else None
    est = q.get("isEarningsDateEstimate")
    if est is True or (end_d is not None and end_d != d):
        conf = "VENDOR_ESTIMATE"
        tim = "UNKNOWN"                     # an estimated date's time is not information
    elif est is False:
        conf = "VENDOR_ANNOUNCED"
    else:
        conf = "UNKNOWN"
    call = _ts(q.get("earningsCallTimestampStart"))
    return {**base, "status": DATE, "next_date": d.isoformat(),
            "date_end": end_d.isoformat() if end_d else None, "timing": tim,
            "confirmation": conf, "event_utc": _iso(t), "call_utc": _iso(call)}


# ─────────────────────────────────────────────── 3. the default fetcher (network)

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


# ─────────────────────────────────────────────── 4. the pull (append-only, resumable)

def _read_jsonl(p: Path) -> list[dict]:
    out = []
    with Path(p).open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def _append(fh: Any, rows: Iterable[dict]) -> None:
    for r in rows:
        fh.write(json.dumps(r, sort_keys=True, ensure_ascii=True, default=str) + "\n")
    fh.flush()
    os.fsync(fh.fileno())


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
         universe_meta: Optional[dict] = None, resume: bool = True) -> dict:
    """Fetch the next earnings date for every ticker and append ONE snapshot.

    Returns the receipt (also written beside the snapshot). Every requested ticker
    gets a row: DATE, NO_DATE (looked, vendor had none) or FAILED (with the error).
    Low coverage is NOT raised here (the rows are true observations and are kept);
    `check_coverage(receipt)` is the red exit."""
    fetch = fetch or yahoo_quote_batch
    bs = int(batch_size or _cfg("FORWARD_CALENDAR_BATCH_SIZE", 50))
    gap = float(_cfg("FORWARD_CALENDAR_BATCH_SLEEP_S", 2.0))
    backoff = float(_cfg("FORWARD_CALENDAR_RATE_LIMIT_BACKOFF_S", 60.0))
    want = []
    for t in tickers:
        s = norm_ticker(t)
        if s and s not in want:
            want.append(s)
    if not want:
        raise ForwardCalendarRefused(UNIVERSE_EMPTY, "no valid ticker to pull")
    snap = snapshots_dir(out_root)
    snap.mkdir(parents=True, exist_ok=True)
    started = now_fn()
    part = _resumable_partial(snap, started) if resume else None
    done: set = set()
    resumed_from = None
    if part is not None:
        resumed_from = part.name
        m = _PARTIAL_RE.match(part.name)
        pull_id = f"fc_{m.group(1)}_{m.group(2)}"
        for r in _read_jsonl(part):
            if r.get("row_kind") == "earnings" and r.get("status") in (DATE, NO_DATE):
                done.add(r.get("ticker"))
    else:
        h = hashlib.sha256(json.dumps([_iso(started), want]).encode()).hexdigest()[:6]
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
    rows = _read_jsonl(part)
    receipt = _receipt(rows, want, pull_id=pull_id, started=started, finished=now_fn(),
                       n_requests=n_requests, n_rate_limited=n_rate_limited, stopped=stopped,
                       resumed_from=resumed_from, universe_meta=universe_meta, batch_size=bs)
    if final.exists():
        raise ForwardCalendarRefused(SNAPSHOT_EXISTS, f"{final.name} appeared during the pull")
    os.replace(part, final)
    tmp = rec_p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(receipt, indent=1, sort_keys=True, default=str), encoding="utf-8")
    os.replace(tmp, rec_p)
    receipt["snapshot_path"] = str(final)
    receipt["receipt_path"] = str(rec_p)
    return receipt


def _macro_rows(macro: Optional[Callable[[], dict]], pull_id: str,
                now_fn: Callable[[], datetime]) -> list[dict]:
    """The macro half, from `macro_calendar.macro_block()` (CPI/NFP via FRED, FOMC from
    the seeded table). A refused leg is stored as a `macro_refusal` row, never as an
    empty calendar."""
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
    denom = max(n_req - not_issuer, 0)
    share = round(n_date / denom, 4) if denom else 0.0
    min_share = float(_cfg("FORWARD_CALENDAR_MIN_DATE_SHARE", 0.60))
    reasons: dict[str, int] = {}
    errors: dict[str, int] = {}
    for t in want:
        r = latest.get(t) or {}
        if r.get("status") == NO_DATE:
            reasons[str(r.get("no_date_reason"))] = reasons.get(str(r.get("no_date_reason")), 0) + 1
        if r.get("status") == FAILED:
            e = str(r.get("error") or "")[:60]
            errors[e] = errors.get(e, 0) + 1
    conf: dict[str, int] = {}
    for t in want:
        r = latest.get(t) or {}
        if r.get("status") == DATE:
            conf[str(r.get("confirmation"))] = conf.get(str(r.get("confirmation")), 0) + 1
    macro = [r for r in rows if r.get("row_kind") == "macro"]
    mref = [r for r in rows if r.get("row_kind") == "macro_refusal"]
    return {"schema": SCHEMA, "receipt": "forward_calendar_pull", "pull_id": kw["pull_id"],
            "started_utc": _iso(kw["started"]), "finished_utc": _iso(kw["finished"]),
            "source": SOURCE, "batch_size": kw["batch_size"], "n_requests": kw["n_requests"],
            "n_rate_limited": kw["n_rate_limited"], "stopped": kw["stopped"],
            "resumed_from": kw["resumed_from"],
            "requested": n_req, "fetched": n_date + n_no, "with_date": n_date, "no_date": n_no,
            "failed": n_fail, "not_an_issuer": not_issuer,
            "share_covered": share, "min_share": min_share,
            "status": "OK" if share >= min_share else LOW_COVERAGE,
            "no_date_reasons": reasons, "failure_errors": errors, "confirmation_counts": conf,
            "failed_tickers": sorted(t for t, v in st.items() if v in (FAILED, None))[:200],
            "macro": {"n_dates": len(macro), "n_refusals": len(mref),
                      "refusals": [{"kind": r.get("kind"), "refusal": r.get("refusal")} for r in mref]},
            "universe": kw.get("universe_meta")}


def check_coverage(receipt: dict) -> None:
    """Red when the pull returned (almost) nothing: raise with the counts."""
    if receipt.get("status") != "OK":
        raise ForwardCalendarRefused(
            LOW_COVERAGE,
            f"{receipt.get('with_date')} of {receipt.get('requested')} names returned a date "
            f"(share {receipt.get('share_covered')} < {receipt.get('min_share')}); "
            f"failed {receipt.get('failed')}, no-date {receipt.get('no_date')}, "
            f"errors {receipt.get('failure_errors')}")


# ─────────────────────────────────────────────── 5. the reader (point in time)

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


def next_dates(tickers: Iterable[str], now: datetime, horizon_days: Optional[int] = None, *,
               root: Path, stale_days: Optional[float] = None) -> dict:
    """As of `now`: per ticker the newest row whose own `pulled_utc` <= `now` (a later
    row is never used), labelled DATE_IN_HORIZON / NO_DATE_IN_HORIZON / NOT_COVERED /
    CALENDAR_STALE, with the row's age. `root` is the data root holding
    `forward_calendar/`."""
    now = _utc(now)
    if now is None:
        raise ForwardCalendarRefused("NOW_INVALID", "now must be a datetime")
    hz = int(horizon_days if horizon_days is not None else _cfg("FORWARD_CALENDAR_HORIZON_DAYS", 120))
    sd = float(stale_days if stale_days is not None else _cfg("FORWARD_CALENDAR_STALE_DAYS", 3.0))
    want = {}
    for t in tickers:
        s = norm_ticker(t)
        if s:
            want[s] = None
    files, skipped = _final_snapshots(root, now)
    usable: dict[str, dict] = {}
    failed: dict[str, dict] = {}
    n_rows_after_now = 0
    for _t, f in files:
        for r in _read_jsonl(f):
            if r.get("row_kind") != "earnings" or r.get("ticker") not in want:
                continue
            pu = _utc(r.get("pulled_utc"))
            if pu is None:
                continue
            if pu > now:
                n_rows_after_now += 1
                continue
            bucket = failed if r.get("status") == FAILED else usable
            old = bucket.get(r["ticker"])
            if old is None or pu >= _utc(old["pulled_utc"]):
                bucket[r["ticker"]] = r
    today = market_date(now)
    out: dict[str, dict] = {}
    for t in want:
        u, fl = usable.get(t), failed.get(t)
        if u is None:
            out[t] = {"label": NOT_COVERED,
                      "reason": "ONLY_FAILED_ATTEMPTS" if fl else "NO_ROW_BY_NOW",
                      "last_error": (fl or {}).get("error"), "last_attempt_utc": (fl or {}).get("pulled_utc")}
            continue
        pu = _utc(u["pulled_utc"])
        age = round((now - pu).total_seconds() / 86400, 3)
        rec = {"pulled_utc": u["pulled_utc"], "pull_id": u.get("pull_id"), "age_days": age,
               "date": u.get("next_date"), "date_end": u.get("date_end"), "timing": u.get("timing"),
               "confirmation": u.get("confirmation"), "source": u.get("source"),
               "row_status": u.get("status"), "no_date_reason": u.get("no_date_reason"),
               "last_attempt_failed": bool(fl and _utc(fl["pulled_utc"]) > pu)}
        d = date.fromisoformat(u["next_date"]) if u.get("next_date") else None
        rec["days_away"] = (d - today).days if d else None
        if age > sd:
            out[t] = {"label": CALENDAR_STALE, "reason": f"newest row {age} d old > {sd} d", **rec}
        elif u.get("status") == NO_DATE:
            out[t] = {"label": NO_DATE_IN_HORIZON, "reason": u.get("no_date_reason"), **rec}
        elif d is None or d < today:
            out[t] = {"label": NO_DATE_IN_HORIZON, "reason": "DATE_PASSED", **rec}
        elif (d - today).days > hz:
            out[t] = {"label": NO_DATE_IN_HORIZON, "reason": "BEYOND_HORIZON", **rec}
        else:
            out[t] = {"label": DATE_IN_HORIZON, "reason": None, **rec}
    counts = {lab: sum(1 for v in out.values() if v["label"] == lab) for lab in LABELS}
    return {"as_of": _iso(now), "market_date": today.isoformat(), "horizon_days": hz,
            "stale_days": sd, "store": str(snapshots_dir(root)), "n_snapshots_read": len(files),
            "n_snapshots_after_now_skipped": skipped, "n_rows_after_now_skipped": n_rows_after_now,
            "counts": counts, "tickers": out}


def next_macro(now: datetime, horizon_days: Optional[int] = None, *, root: Path) -> dict:
    """The macro rows of the newest snapshot pulled at or before `now`, within the horizon."""
    now = _utc(now)
    hz = int(horizon_days if horizon_days is not None else _cfg("FORWARD_CALENDAR_HORIZON_DAYS", 120))
    files, _ = _final_snapshots(root, now)
    for _t, f in reversed(files):
        rows = [r for r in _read_jsonl(f) if str(r.get("row_kind", "")).startswith("macro")
                and (_utc(r.get("pulled_utc")) or now) <= now]
        if not rows:
            continue
        today = market_date(now)
        lo, hi = today.isoformat(), (today + timedelta(days=hz)).isoformat()
        legs = next((r for r in rows if r["row_kind"] == "macro_legs"), {})
        return {"status": "OK", "pull_id": rows[0].get("pull_id"), "pulled_utc": rows[0].get("pulled_utc"),
                "dates": [{"date": r["date"], "kind": r.get("kind"), "what": r.get("what"),
                           "source": r.get("source"),
                           "days_away": (date.fromisoformat(r["date"][:10]) - today).days}
                          for r in rows if r["row_kind"] == "macro" and lo <= str(r.get("date"))[:10] <= hi],
                "refusals": [{"kind": r.get("kind"), "refusal": r.get("refusal")}
                             for r in rows if r["row_kind"] == "macro_refusal"],
                "legs": legs.get("legs"), "fomc_table": legs.get("fomc_table")}
    return {"status": "NO_MACRO_SNAPSHOT_BY_NOW", "dates": [], "refusals": []}


# ─────────────────────────────────────────────── 6. freshness (the health row)

def newest_receipt(root: Path, now: datetime) -> Optional[tuple[datetime, Path]]:
    snap = snapshots_dir(root)
    best = None
    for f in snap.glob("fc_*_receipt.json") if snap.is_dir() else []:
        m = _RECEIPT_RE.match(f.name)
        t = _parse_stamp(m.group(1)) if m else None
        if t is not None and t <= now and (best is None or t > best[0]):
            best = (t, f)
    return best


def freshness(root: Path, now: datetime, *, stale_days: Optional[float] = None) -> dict:
    """{verdict ALIVE/STALE/UNKNOWN, evidence_utc, age_s, detail} from the newest pull
    receipt, dated by the receipt's OWN `finished_utc` (else the stamp in its name),
    never a file mtime."""
    sd = float(stale_days if stale_days is not None else _cfg("FORWARD_CALENDAR_STALE_DAYS", 3.0))
    nr = newest_receipt(root, now)
    if nr is None:
        return {"verdict": "UNKNOWN", "evidence_utc": None, "age_s": None,
                "detail": f"no forward-calendar pull receipt under {snapshots_dir(root)}: "
                          "the calendar has never been pulled here, so no next date is known"}
    name_t, p = nr
    try:
        rec = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"verdict": "UNKNOWN", "evidence_utc": _iso(name_t), "age_s": None,
                "detail": f"{p.name} unreadable ({type(exc).__name__})"}
    t = _utc(rec.get("finished_utc")) or name_t
    age_s = round((now - t).total_seconds(), 1)
    counts = (f"{rec.get('with_date')}/{rec.get('requested')} with a date (share "
              f"{rec.get('share_covered')}, min {rec.get('min_share')}), failed {rec.get('failed')}")
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
                       proof="forward_calendar/snapshots/fc_<stamp>_receipt.json: finished_utc, "
                             "status, share_covered; never mtime")


__all__ = ["CALENDAR_STALE", "DATE_IN_HORIZON", "ForwardCalendarRefused", "LABELS", "LOW_COVERAGE",
           "NOT_COVERED", "NO_DATE_IN_HORIZON", "build_universe", "check_coverage", "freshness",
           "next_dates", "next_macro", "p_forward_calendar", "parse_quote", "pull",
           "yahoo_quote_batch"]
