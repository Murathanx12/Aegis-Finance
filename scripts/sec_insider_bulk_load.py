"""
I1 — the SEC Insider Transactions bulk loader (resumable, receipted, PIT).
==========================================================================

    python -m scripts.sec_insider_bulk_load pull --start 2006q1 --end 2026q2
    python -m scripts.sec_insider_bulk_load pull            # resumes; --limit N
    python -m scripts.sec_insider_bulk_load report          # coverage by year
    python -m scripts.sec_insider_bulk_load events          # event-table rows

WHY IT IS BUILT THIS WAY
------------------------
The news backfill died on 2026-09-07 at 112/134 months with **no cursor and no
log**, so the only way to finish it was to start again from zero (roadmap §6,
row E). Every design choice below is that failure's negative image:

  * a **cursor** (`_cursor.json`) is rewritten atomically after EVERY quarter,
    so a kill at 83% resumes at 83%;
  * a **log** (`_load.log`) gets one line per quarter, on disk, as it happens;
  * a **coverage receipt** (`receipts/<quarter>.json`) is written PER QUARTER,
    not once at the end — a run that dies still leaves evidence of what it did;
  * a **PID file** (`_load.pid`) so a later session can find the process
    without `taskkill /IM python.exe` (CLAUDE.md rule 6);
  * `--start` / `--end` are absolute quarters, never "N quarters from today" —
    a relative window makes yesterday's receipt unreproducible.

The quarterly ZIP list is SCRAPED from the SEC index page rather than
generated from a URL pattern, because the pattern is already wrong: 2026q2 is
served from `/files/datastandardsinnovation/...` while 2006q1..2026q1 come
from `/files/structureddata/...`. A hard-coded pattern would have silently
skipped the newest quarter, which is the exact shape of a silent-fragility bug.

NETWORK MANNERS
---------------
SEC fair access: a descriptive User-Agent with a contact, and at most 10
requests per second. This job makes ONE request per quarter plus one for the
index, so it is nowhere near the ceiling, but the limiter is here anyway
because the last collector that assumed it was fine got 403'd on 100% of prod
fetches. **A 403 is raised, logged and recorded in the cursor — never
swallowed into an empty result.**

WHAT THIS JOB DOES NOT DO
-------------------------
No book, no return, no edge. The deliverable is clean PIT data plus its
coverage receipt. Cohen-Malloy-Pomorski's 82 bp/month (1989-2007) is carried
in the docs as the PRIOR that motivates the routine/opportunistic split; it is
not a claim, and beta-first grading and family correction belong to whoever
runs the book later.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import sec_insider_bulk as S  # noqa: E402

log = logging.getLogger("sec_insider_bulk_load")

DATA_DIR = REPO / "backend" / "data" / "optimus" / "sec_insider"
RAW_DIR = DATA_DIR / "raw"
PARSED_DIR = DATA_DIR / "parsed"
RECEIPT_DIR = DATA_DIR / "receipts"
CURSOR_PATH = DATA_DIR / "_cursor.json"
INDEX_CACHE = DATA_DIR / "_zip_index.json"
LOG_PATH = DATA_DIR / "_load.log"
PID_PATH = DATA_DIR / "_load.pid"
COVERAGE_PATH = DATA_DIR / "coverage_by_year.json"
EVENTS_PATH = DATA_DIR / "insider_events_v1.parquet"
EVENTS_RECEIPT = DATA_DIR / "insider_events_v1_receipt.json"

CRSP_STOCKNAMES = REPO / "backend" / "data" / "optimus" / "wrds" / "bulk" / "crsp__stocknames.parquet"

#: SEC asks for <=10 req/s. One request per quarter is far under that; the
#: floor exists so a future caller that loops faster still cannot offend.
MIN_REQUEST_INTERVAL_S = 0.2
HTTP_TIMEOUT_S = 300
MAX_RETRIES = 4

CURSOR_VERSION = 2


# --------------------------------------------------------------- utilities

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_atomic(path: Path, text: str) -> None:
    """Write via a temp file + replace. A cursor half-written by a kill is
    worse than no cursor — it resumes at a quarter that never finished."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def _append_log(line: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(f"{_now()}\t{line}\n")
    log.info(line)


def load_cursor() -> dict:
    if CURSOR_PATH.exists():
        try:
            cur = json.loads(CURSOR_PATH.read_text(encoding="utf-8"))
            if cur.get("version") == CURSOR_VERSION:
                return cur
            _append_log(f"cursor version {cur.get('version')} != {CURSOR_VERSION}; "
                        f"starting a fresh cursor (old one kept as _cursor.v{cur.get('version')}.json)")
            _write_atomic(DATA_DIR / f"_cursor.v{cur.get('version')}.json",
                          json.dumps(cur, indent=1))
        except (json.JSONDecodeError, OSError) as e:
            _append_log(f"cursor unreadable ({e}); starting fresh")
    return {"version": CURSOR_VERSION, "started_utc": _now(), "updated_utc": None,
            "done": [], "failed": {}, "rows_total": 0, "bytes_total": 0}


def save_cursor(cur: dict) -> None:
    cur["updated_utc"] = _now()
    _write_atomic(CURSOR_PATH, json.dumps(cur, indent=1, default=str))


# ------------------------------------------------------------ the SEC index

class _RateLimiter:
    def __init__(self, min_interval: float) -> None:
        self.min_interval = min_interval
        self._last = 0.0

    def wait(self) -> None:
        gap = time.monotonic() - self._last
        if gap < self.min_interval:
            time.sleep(self.min_interval - gap)
        self._last = time.monotonic()


_LIMITER = _RateLimiter(MIN_REQUEST_INTERVAL_S)


def _get(url: str, *, stream: bool = False):
    """One rate-limited SEC GET with retry. A 403 is RAISED with its body's
    first line, because a swallowed 403 is how a collector reports zero rows
    and looks healthy."""
    import requests  # imported lazily: the fast test suite blocks sockets

    headers = {"User-Agent": S.SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"}
    last: Exception | None = None
    for attempt in range(MAX_RETRIES):
        _LIMITER.wait()
        try:
            r = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT_S, stream=stream)
        except Exception as e:  # network-level
            last = e
            time.sleep(2 ** attempt)
            continue
        if r.status_code == 403:
            raise S.SecInsiderBulkError(
                f"SEC returned 403 for {url}. This is a fair-access block, not an "
                f"empty quarter. User-Agent sent: {S.SEC_USER_AGENT!r}. "
                f"Body starts: {r.text[:200]!r}")
        if r.status_code == 429 or 500 <= r.status_code < 600:
            last = S.SecInsiderBulkError(f"HTTP {r.status_code} for {url}")
            time.sleep(2 ** attempt)
            continue
        if r.status_code != 200:
            raise S.SecInsiderBulkError(f"HTTP {r.status_code} for {url}")
        return r
    raise S.SecInsiderBulkError(f"giving up on {url} after {MAX_RETRIES} attempts: {last}")


def discover_zip_urls(*, refresh: bool = False) -> dict[str, str]:
    """{quarter: absolute zip url}. Cached to `_zip_index.json` so a resume
    does not re-fetch the index page."""
    if INDEX_CACHE.exists() and not refresh:
        try:
            cached = json.loads(INDEX_CACHE.read_text(encoding="utf-8"))
            if cached.get("urls"):
                return cached["urls"]
        except (json.JSONDecodeError, OSError):
            pass
    r = _get(S.INDEX_URL)
    hrefs = re.findall(r'href="([^"]*?form345[^"]*?\.zip)"', r.text, re.IGNORECASE)
    urls: dict[str, str] = {}
    for h in hrefs:
        m = re.search(r"(\d{4}q[1-4])_form345\.zip$", h, re.IGNORECASE)
        if not m:
            continue
        urls[m.group(1).lower()] = h if h.startswith("http") else "https://www.sec.gov" + h
    if not urls:
        raise S.SecInsiderBulkError(
            f"no form345 ZIP links found on {S.INDEX_URL} — the page layout changed; "
            f"refusing to fall back to the URL pattern silently")
    _write_atomic(INDEX_CACHE, json.dumps(
        {"fetched_utc": _now(), "source": S.INDEX_URL, "count": len(urls),
         "urls": dict(sorted(urls.items()))}, indent=1))
    _append_log(f"index: {len(urls)} quarterly ZIPs listed "
                f"({min(urls)} .. {max(urls)})")
    return urls


def download_quarter(quarter: str, url: str, *, force: bool = False) -> Path:
    dest = RAW_DIR / f"{quarter}_form345.zip"
    if dest.exists() and dest.stat().st_size > 0 and not force:
        return dest
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    r = _get(url, stream=True)
    tmp = dest.with_suffix(".zip.part")
    n = 0
    with tmp.open("wb") as fh:
        for chunk in r.iter_content(chunk_size=1 << 20):
            if chunk:
                fh.write(chunk)
                n += len(chunk)
    if n == 0:
        tmp.unlink(missing_ok=True)
        raise S.SecInsiderBulkError(f"{url} returned 0 bytes")
    os.replace(tmp, dest)
    return dest


# ------------------------------------------------------------- CRSP linking

def load_crsp_index() -> tuple[dict, date | None, str]:
    """(ticker index, vintage_end, note). Absent CRSP is a DECLARED absence:
    every row then refuses with REFUSED_OUTSIDE_CRSP_VINTAGE rather than the
    loader pretending it linked nothing for a good reason."""
    if not CRSP_STOCKNAMES.exists():
        return {}, None, f"CRSP stocknames absent at {CRSP_STOCKNAMES}"
    import pandas as pd
    df = pd.read_parquet(CRSP_STOCKNAMES, columns=["permno", "ticker", "namedt",
                                                   "nameenddt", "shrcd"])
    idx = S.build_crsp_ticker_index(df)
    vintage_end = S.parse_sec_date(str(pd.to_datetime(df["nameenddt"]).max().date()))
    return idx, vintage_end, f"crsp__stocknames.parquet rows={len(df)} vintage_end={vintage_end}"


# ---------------------------------------------------------------- the pull

def _year_breakdown(rows: Iterable[dict]) -> dict[str, dict]:
    by: dict[int, dict] = defaultdict(lambda: {
        "rows": 0, "issuers": set(), "insiders": set(),
        "open_market_purchases": 0, "open_market_sales": 0,
        "linked": 0, "link_refusals": defaultdict(int)})
    for r in rows:
        fd = r.get("filing_date")
        if fd is None:
            continue
        y = fd.year if isinstance(fd, date) else S.parse_sec_date(fd).year
        b = by[y]
        b["rows"] += 1
        if r.get("issuer_cik"):
            b["issuers"].add(r["issuer_cik"])
        if r.get("owner_cik"):
            b["insiders"].add(r["owner_cik"])
        b["open_market_purchases"] += bool(r.get("is_open_market_purchase"))
        b["open_market_sales"] += bool(r.get("is_open_market_sale"))
        if r.get("permno") is not None:
            b["linked"] += 1
        else:
            b["link_refusals"][r.get("permno_link_method") or "UNKNOWN"] += 1
    out = {}
    for y in sorted(by):
        b = by[y]
        out[str(y)] = {
            "rows": b["rows"],
            "distinct_issuers": len(b["issuers"]),
            "distinct_insiders": len(b["insiders"]),
            "open_market_purchases": b["open_market_purchases"],
            "open_market_sales": b["open_market_sales"],
            "rows_linked_to_permno": b["linked"],
            "link_rate": round(b["linked"] / b["rows"], 4) if b["rows"] else None,
            "link_refusals": dict(sorted(b["link_refusals"].items(), key=lambda kv: -kv[1])),
        }
    return out


PARQUET_COLUMNS = [
    "quarter", "accession", "form_type", "is_amendment",
    "issuer_cik", "issuer_name", "symbol", "permno", "permno_link_method",
    "owner_cik", "owner_name", "owner_relationship", "officer_title",
    "is_director", "is_officer", "is_tenpercent", "is_other_insider",
    "table", "trans_sk", "security_title", "trans_form_type",
    "trans_date", "deemed_execution_date", "period_of_report",
    "trans_code", "trans_class", "acquired_disposed",
    "shares", "price_per_share", "dollar_value", "shares_owned_following",
    "direct_indirect", "trans_timeliness",
    "plan_10b5_1", "plan_10b5_1_source",
    "is_open_market_purchase", "is_open_market_sale",
    "filing_date", "observed_at_utc", "observed_at_precision",
    "observed_at_basis", "acceptance_datetime_utc",
]


def _to_frame(rows: list[dict]):
    import pandas as pd
    df = pd.DataFrame(rows)
    for c in PARQUET_COLUMNS:
        if c not in df.columns:
            df[c] = None
    df = df[PARQUET_COLUMNS]
    for c in ("trans_date", "deemed_execution_date", "period_of_report", "filing_date"):
        df[c] = pd.to_datetime(df[c], errors="coerce")
    df["observed_at_utc"] = pd.to_datetime(df["observed_at_utc"], errors="coerce", utc=True)
    return df


def pull(args: argparse.Namespace) -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PID_PATH.write_text(str(os.getpid()), encoding="utf-8")
    _append_log(f"pull start pid={os.getpid()} argv={' '.join(sys.argv[1:])}")

    urls = discover_zip_urls(refresh=args.refresh_index)
    available = sorted(urls)
    start = args.start or available[0]
    end = args.end or available[-1]
    wanted = [q for q in S.quarters_between(start, end) if q in urls]
    missing = [q for q in S.quarters_between(start, end) if q not in urls]
    if missing:
        _append_log(f"NOT PUBLISHED by the SEC (skipped, not failed): {missing}")

    cur = load_cursor()
    done = set(cur["done"])
    todo = [q for q in wanted if q not in done or args.force]
    if args.limit:
        todo = todo[:args.limit]
    _append_log(f"plan: {len(wanted)} quarters in [{start}..{end}]; "
                f"{len(done & set(wanted))} already done; {len(todo)} to do this run")

    crsp_idx, vintage_end, crsp_note = load_crsp_index()
    _append_log(f"crsp link source: {crsp_note}")

    ok = failed = 0
    for i, q in enumerate(todo, 1):
        t0 = time.time()
        try:
            zpath = download_quarter(q, urls[q], force=args.redownload)
            rows, receipt = S.parse_quarter_zip(zpath, quarter=q)

            # PIT + fabrication guards run BEFORE anything is written. A
            # quarter that fails a guard leaves no parquet behind to be
            # mistaken for good data.
            receipt["pit_check"] = S.assert_pit_sane(rows)
            receipt["fabrication_check"] = S.assert_not_fabricated(rows)

            link_counts: dict[str, int] = defaultdict(int)
            for r in rows:
                permno, method = S.link_permno(r.get("symbol"), r.get("filing_date"),
                                               crsp_idx, vintage_end)
                r["permno"] = permno
                r["permno_link_method"] = method
                link_counts[method] += 1
            receipt["link_counts"] = dict(sorted(link_counts.items(), key=lambda kv: -kv[1]))
            receipt["link_rate"] = round(
                link_counts.get(S.LINK_OK, 0) / len(rows), 4) if rows else None
            receipt["crsp_link_source"] = crsp_note
            receipt["by_year"] = _year_breakdown(rows)
            receipt["written_utc"] = _now()

            PARSED_DIR.mkdir(parents=True, exist_ok=True)
            _to_frame(rows).to_parquet(PARSED_DIR / f"{q}.parquet", index=False)

            RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
            _write_atomic(RECEIPT_DIR / f"{q}.json",
                          json.dumps(receipt, indent=1, default=str))

            if not args.keep_raw:
                zpath.unlink(missing_ok=True)

            if q not in cur["done"]:
                cur["done"].append(q)
                cur["done"].sort()
            cur["failed"].pop(q, None)
            cur["rows_total"] = int(cur.get("rows_total", 0)) + len(rows)
            cur["bytes_total"] = int(cur.get("bytes_total", 0)) + int(receipt["zip_bytes"] or 0)
            cur["last_quarter"] = q
            save_cursor(cur)
            ok += 1
            _append_log(f"[{i}/{len(todo)}] {q} OK rows={len(rows)} "
                        f"subs={receipt['submissions']} buys={receipt['open_market_purchases']} "
                        f"link={receipt['link_rate']} zip={receipt['zip_bytes']}B "
                        f"{time.time()-t0:.1f}s")
        except Exception as e:  # noqa: BLE001 — recorded, then decided on
            failed += 1
            cur["failed"][q] = f"{type(e).__name__}: {e}"
            save_cursor(cur)
            _append_log(f"[{i}/{len(todo)}] {q} FAILED {type(e).__name__}: {e}")
            if args.stop_on_error:
                break
    _append_log(f"pull end ok={ok} failed={failed} done_total={len(cur['done'])}")
    PID_PATH.unlink(missing_ok=True)
    return 0 if failed == 0 else 1


# --------------------------------------------------------------- the report

def _parsed_files(start: str | None, end: str | None) -> list:
    lo = S.split_quarter(start) if start else None
    hi = S.split_quarter(end) if end else None
    out = []
    for f in sorted(PARSED_DIR.glob("*.parquet")):
        try:
            qq = S.split_quarter(f.stem)
        except S.SecInsiderBulkError:
            continue
        if (lo and qq < lo) or (hi and qq > hi):
            continue
        out.append(f)
    return out


def _iter_parsed(start: str | None, end: str | None, columns: list[str] | None = None):
    """Stream the parsed quarters ONE AT A TIME.

    The whole tape is 11.5 M rows x 42 columns (~443 MB of parquet, several GB
    in memory). `pd.concat` over all 82 frames is how a report job dies on the
    machine it was written on; every consumer below accumulates counters
    instead, and reads only the columns it names.
    """
    import pandas as pd
    for f in _parsed_files(start, end):
        yield f.stem, pd.read_parquet(f, columns=columns)


def report(args: argparse.Namespace) -> int:
    """Coverage-by-year receipt over every parsed quarter.

    Two streaming passes, never one concat:

      A. read only (owner_cik, trans_date, filing_date) for the DISCRETIONARY
         OPEN-MARKET PURCHASES and build the CMP purchase history across the
         WHOLE tape — the routine/opportunistic rule needs three prior years,
         so it cannot be computed a quarter at a time;
      B. read the counting columns per quarter and accumulate per-year totals.

    Distinct-issuer and distinct-insider counts are per-year SETS carried
    across quarters, because "distinct issuers in 2014" is not the sum of four
    quarterly distinct counts — an issuer that filed in Q1 and Q3 is one
    issuer, and summing would double it.
    """
    import pandas as pd

    files = _parsed_files(args.start, args.end)
    if not files:
        print("NO PARSED QUARTERS — run `pull` first. This is a refusal, not "
              "an empty coverage table.", file=sys.stderr)
        return 2

    # ---- pass A: the CMP history over the whole tape --------------------
    buy_parts = []
    for q, df in _iter_parsed(args.start, args.end,
                              columns=["owner_cik", "trans_date", "filing_date",
                                       "is_open_market_purchase"]):
        b = df[df["is_open_market_purchase"].fillna(False).astype(bool)]
        if len(b):
            buy_parts.append(b[["owner_cik", "trans_date", "filing_date"]].copy())
    buys = (pd.concat(buy_parts, ignore_index=True) if buy_parts
            else pd.DataFrame(columns=["owner_cik", "trans_date", "filing_date"]))
    buys["is_open_market_purchase"] = True
    hist = S.build_purchase_history(buys.to_dict("records"))
    buys["cmp_class"] = [S.classify_routine_opportunistic(c, t, hist)
                         for c, t in zip(buys["owner_cik"], buys["trans_date"])]
    buys["year"] = pd.to_datetime(buys["filing_date"], errors="coerce").dt.year

    cmp_by_year: dict[int, dict[str, int]] = defaultdict(
        lambda: {S.ROUTINE: 0, S.OPPORTUNISTIC: 0, S.UNCLASSIFIABLE: 0})
    for y, cls in zip(buys["year"], buys["cmp_class"]):
        if y == y:
            cmp_by_year[int(y)][cls] += 1

    # ---- pass B: the counting columns -----------------------------------
    acc: dict[int, dict] = defaultdict(lambda: {
        "rows": 0, "filings": set(), "issuers": set(), "insiders": set(),
        "buys": 0, "sells": 0, "linked": 0, "refusals": defaultdict(int),
        "plan_unknown": 0})
    trans_class_totals: dict[str, int] = defaultdict(int)
    plan_totals: dict[str, int] = defaultdict(int)
    plan_src_totals: dict[str, int] = defaultdict(int)
    rows_total = 0
    all_filings: set[str] = set()

    for q, df in _iter_parsed(args.start, args.end,
                              columns=["filing_date", "accession", "issuer_cik",
                                       "owner_cik", "is_open_market_purchase",
                                       "is_open_market_sale", "permno_link_method",
                                       "plan_10b5_1", "plan_10b5_1_source",
                                       "trans_class"]):
        rows_total += len(df)
        df["year"] = pd.to_datetime(df["filing_date"], errors="coerce").dt.year
        for k, v in df["trans_class"].value_counts().items():
            trans_class_totals[str(k)] += int(v)
        for k, v in df["plan_10b5_1"].value_counts().items():
            plan_totals[str(k)] += int(v)
        for k, v in df["plan_10b5_1_source"].value_counts().items():
            plan_src_totals[str(k)] += int(v)
        all_filings.update(df["accession"].dropna().unique().tolist())
        for y, g in df.groupby("year", dropna=True):
            a = acc[int(y)]
            a["rows"] += int(len(g))
            a["filings"].update(g["accession"].dropna().unique().tolist())
            a["issuers"].update(g["issuer_cik"].dropna().unique().tolist())
            a["insiders"].update(g["owner_cik"].dropna().unique().tolist())
            a["buys"] += int(g["is_open_market_purchase"].fillna(False).sum())
            a["sells"] += int(g["is_open_market_sale"].fillna(False).sum())
            a["linked"] += int((g["permno_link_method"] == S.LINK_OK).sum())
            a["plan_unknown"] += int((g["plan_10b5_1"] == S.PLAN_UNKNOWN).sum())
            for k, v in (g.loc[g["permno_link_method"] != S.LINK_OK,
                               "permno_link_method"].value_counts().items()):
                a["refusals"][str(k)] += int(v)

    by_year: dict[str, dict] = {}
    for y in sorted(acc):
        a = acc[y]
        c = cmp_by_year.get(y, {S.ROUTINE: 0, S.OPPORTUNISTIC: 0, S.UNCLASSIFIABLE: 0})
        by_year[str(y)] = {
            "rows": a["rows"],
            "filings": len(a["filings"]),
            "distinct_issuers": len(a["issuers"]),
            "distinct_insiders": len(a["insiders"]),
            "open_market_purchases": a["buys"],
            "open_market_sales": a["sells"],
            "rows_linked_to_permno": a["linked"],
            "link_rate": round(a["linked"] / a["rows"], 4) if a["rows"] else None,
            "link_refusals": dict(sorted(a["refusals"].items(), key=lambda kv: -kv[1])),
            "cmp_routine": c[S.ROUTINE],
            "cmp_opportunistic": c[S.OPPORTUNISTIC],
            "cmp_unclassifiable": c[S.UNCLASSIFIABLE],
            "plan_10b5_1_unknown": a["plan_unknown"],
        }

    cur = load_cursor()
    coverage = {
        "generated_utc": _now(),
        "quarters_parsed": [f.stem for f in files],
        "quarters_done_per_cursor": cur.get("done", []),
        "quarters_failed_per_cursor": cur.get("failed", {}),
        "rows_total": int(rows_total),
        "filings_total": len(all_filings),
        "distinct_issuers_total": len(set().union(*[a["issuers"] for a in acc.values()])) if acc else 0,
        "distinct_insiders_total": len(set().union(*[a["insiders"] for a in acc.values()])) if acc else 0,
        "observed_at_basis": S.OBSERVED_AT_BASIS,
        "pit_rule": ("observed_at_utc = FILING_DATE end-of-day (22:00 ET) in UTC. "
                     "Never TRANS_DATE. Earliest tradable moment is the NEXT "
                     "session's open (next_tradable_session_bound)."),
        "cmp_prior": ("Cohen-Malloy-Pomorski 2012: 82 bp/month VW long-short, "
                      "1989-2007. A PRIOR, not a claim of this repo. No book is "
                      "built in this lane."),
        "cmp_totals": {
            "open_market_purchases": int(len(buys)),
            "routine": int((buys["cmp_class"] == S.ROUTINE).sum()),
            "opportunistic": int((buys["cmp_class"] == S.OPPORTUNISTIC).sum()),
            "unclassifiable": int((buys["cmp_class"] == S.UNCLASSIFIABLE).sum()),
            "insiders_with_purchase_history": int(len(hist)),
        },
        "trans_class_totals": dict(sorted(trans_class_totals.items(), key=lambda kv: -kv[1])),
        "plan_10b5_1_totals": dict(sorted(plan_totals.items(), key=lambda kv: -kv[1])),
        "plan_10b5_1_source_totals": dict(sorted(plan_src_totals.items(), key=lambda kv: -kv[1])),
        "by_year": by_year,
    }
    _write_atomic(COVERAGE_PATH, json.dumps(coverage, indent=1, default=str))

    _print_coverage_table(coverage)
    print(f"\nreceipt: {COVERAGE_PATH}")
    return 0


def _print_coverage_table(cov: dict) -> None:
    print(f"\nSEC INSIDER BULK — COVERAGE BY YEAR  (rows={cov['rows_total']:,}, "
          f"filings={cov['filings_total']:,})")
    print(f"PIT: {cov['observed_at_basis']}")
    hdr = (f"{'year':>5} {'rows':>10} {'filings':>9} {'issuers':>8} {'insiders':>9} "
           f"{'buys':>8} {'sales':>8} {'link%':>7} {'routine':>8} {'opport':>8} {'unclass':>8}")
    print(hdr)
    print("-" * len(hdr))
    for y, b in sorted(cov["by_year"].items()):
        lr = "n/a" if b["link_rate"] is None else f"{100*b['link_rate']:.1f}"
        print(f"{y:>5} {b['rows']:>10,} {b['filings']:>9,} {b['distinct_issuers']:>8,} "
              f"{b['distinct_insiders']:>9,} {b['open_market_purchases']:>8,} "
              f"{b['open_market_sales']:>8,} {lr:>7} {b['cmp_routine']:>8,} "
              f"{b['cmp_opportunistic']:>8,} {b['cmp_unclassifiable']:>8,}")


# ---------------------------------------------------------------- events

#: The `insider_*` families this lane contributes to the event table. Each is
#: a TYPED family name, so a later book states which family it ran and family
#: correction has something to count.
EVENT_FAMILIES = {
    "insider_open_market_buy": "A discretionary open-market purchase (code P, acquired, non-derivative, not 10b5-1).",
    "insider_open_market_sell": "A discretionary open-market sale (code S, disposed, non-derivative, not 10b5-1).",
    "insider_opportunistic_buy": "An open-market purchase by a CMP-OPPORTUNISTIC insider.",
    "insider_routine_buy": "An open-market purchase by a CMP-ROUTINE insider (the control arm).",
    "insider_cluster_buy": "A day on which >=3 distinct insiders of one issuer filed open-market purchases.",
}


def events(args: argparse.Namespace) -> int:
    """Emit `insider_*` event-table rows in `scripts/n4_event_table.py`'s shape.

    `observed_at_utc` is the FILING day's end — the availability bound, which
    is the filing-acceptance day at date precision (see the parser docstring
    for why an exact acceptance TIMESTAMP is a separate per-accession job and
    is carried as a declared NULL rather than a guess).

    Written as its own parquet rather than appended into `event_table_v1`:
    that table is a sealed artefact of the night lab, and mutating someone
    else's receipt is not this lane's business. The N4 build reads this file
    when it next runs.

    Streamed, like `report`: only the buy/sell rows of each quarter are kept,
    and only the columns the event schema needs.
    """
    import pandas as pd

    files = _parsed_files(args.start, args.end)
    if not files:
        print("NO PARSED QUARTERS — run `pull` first.", file=sys.stderr)
        return 2

    COLS = ["permno", "permno_link_method", "symbol", "issuer_cik", "accession",
            "owner_cik", "is_officer", "is_director", "is_tenpercent",
            "trans_code", "shares", "price_per_share", "dollar_value",
            "plan_10b5_1", "trans_date", "filing_date", "observed_at_utc",
            "is_open_market_purchase", "is_open_market_sale"]

    parts = []
    for q, df in _iter_parsed(args.start, args.end, columns=COLS):
        keep = (df["is_open_market_purchase"].fillna(False).astype(bool)
                | df["is_open_market_sale"].fillna(False).astype(bool))
        if keep.any():
            parts.append(df[keep].copy())
    if not parts:
        print("NO OPEN-MARKET ROWS — refusing to write an empty event table.",
              file=sys.stderr)
        return 2
    df = pd.concat(parts, ignore_index=True)
    del parts

    is_buy = df["is_open_market_purchase"].fillna(False).astype(bool)
    hist = S.build_purchase_history(
        df.loc[is_buy, ["owner_cik", "trans_date", "is_open_market_purchase"]]
          .to_dict("records"))
    df["cmp_class"] = [
        S.classify_routine_opportunistic(c, t, hist) if b else None
        for c, t, b in zip(df["owner_cik"], df["trans_date"], is_buy)]

    # Cluster flag: >=3 distinct insiders buying the same issuer on the same
    # FILING day — a cluster a reader could actually SEE, which is why it is
    # keyed on the filing day and not on the transaction day.
    cluster = (df.loc[is_buy].groupby(["issuer_cik", "filing_date"])["owner_cik"]
               .nunique().rename("insider_cluster_buyers").reset_index())
    df = df.merge(cluster, on=["issuer_cik", "filing_date"], how="left")
    is_buy = df["is_open_market_purchase"].fillna(False).astype(bool)

    etype = pd.Series("insider_open_market_sell", index=df.index, dtype="object")
    etype[is_buy] = "insider_open_market_buy"
    etype[is_buy & (df["cmp_class"] == S.OPPORTUNISTIC)] = "insider_opportunistic_buy"
    etype[is_buy & (df["cmp_class"] == S.ROUTINE)] = "insider_routine_buy"

    out = pd.DataFrame({
        "permno": df["permno"],
        "permno_link_method": df["permno_link_method"],
        "symbol": df["symbol"],
        "event_type": etype,
        "event_time_utc": pd.to_datetime(df["trans_date"], errors="coerce", utc=True),
        "observed_at_utc": df["observed_at_utc"],
        "observed_at_precision": "date",
        "observed_at_basis": S.OBSERVED_AT_BASIS,
        "source": "sec_insider_bulk",
        "title": None,
        "insider_cik": df["owner_cik"],
        "insider_is_officer": df["is_officer"],
        "insider_is_director": df["is_director"],
        "insider_is_tenpercent": df["is_tenpercent"],
        "insider_cmp_class": df["cmp_class"],
        "insider_trans_code": df["trans_code"],
        "insider_shares": df["shares"],
        "insider_price": df["price_per_share"],
        "insider_dollar_value": df["dollar_value"],
        "insider_plan_10b5_1": df["plan_10b5_1"],
        "insider_cluster_buyers": df["insider_cluster_buyers"],
        "independence_group": "sec:form4",
        "year": pd.to_datetime(df["filing_date"], errors="coerce").dt.year.astype("Int16"),
    })
    out = out.dropna(subset=["observed_at_utc"])

    pit = S.assert_pit_sane([
        {"filing_date": fd, "trans_date": td, "observed_at_utc": ob, "accession": acc}
        for fd, td, ob, acc in zip(df["filing_date"], df["trans_date"],
                                   df["observed_at_utc"], df["accession"])])

    EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(EVENTS_PATH, index=False)
    receipt = {
        "generated_utc": _now(),
        "path": str(EVENTS_PATH),
        "rows": int(len(out)),
        "families": EVENT_FAMILIES,
        "event_type_counts": {str(k): int(v)
                              for k, v in out["event_type"].value_counts().items()},
        "quarters": [f.stem for f in files],
        "observed_at_basis": S.OBSERVED_AT_BASIS,
        "pit_check": pit,
        "link_rate": round(float((out["permno_link_method"] == S.LINK_OK).mean()), 4)
        if len(out) else None,
        "rows_with_permno": int((out["permno_link_method"] == S.LINK_OK).sum()),
        "cluster_buy_rows_ge3": int((out["insider_cluster_buyers"] >= 3).sum()),
        "note": ("observed_at_utc is the FILING day's end, never the transaction "
                 "date. event_time_utc carries the transaction date and is NOT "
                 "safe to condition on."),
    }
    _write_atomic(EVENTS_RECEIPT, json.dumps(receipt, indent=1, default=str))
    print(json.dumps({k: v for k, v in receipt.items() if k != "families"},
                     indent=1, default=str))
    return 0


# -------------------------------------------------------------------- CLI

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    pl = sub.add_parser("pull", help="download + parse + receipt, resumable")
    pl.add_argument("--start", help="first quarter, e.g. 2006q1 (default: earliest published)")
    pl.add_argument("--end", help="last quarter, e.g. 2026q2 (default: latest published)")
    pl.add_argument("--limit", type=int, help="stop after N quarters this run")
    pl.add_argument("--force", action="store_true", help="re-do quarters already in the cursor")
    pl.add_argument("--redownload", action="store_true", help="re-fetch ZIPs already on disk")
    pl.add_argument("--refresh-index", action="store_true", help="re-scrape the SEC index page")
    pl.add_argument("--keep-raw", action="store_true",
                    help="keep the ZIPs (~13 MB each, ~1.0 GB for all 82)")
    pl.add_argument("--stop-on-error", action="store_true")
    pl.set_defaults(func=pull)

    rp = sub.add_parser("report", help="coverage-by-year receipt over parsed quarters")
    rp.add_argument("--start")
    rp.add_argument("--end")
    rp.set_defaults(func=report)

    ev = sub.add_parser("events", help="write insider_* event-table rows")
    ev.add_argument("--start")
    ev.add_argument("--end")
    ev.set_defaults(func=events)
    return p


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
