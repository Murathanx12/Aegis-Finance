"""EDGAR 8-K ITEM CODES -- the first scenario-bridge data acquisition.

    python -m scripts.edgar_8k_items --pull                    # scenario + tracker universe
    python -m scripts.edgar_8k_items --pull --universe scenario
    python -m scripts.edgar_8k_items --pull --tickers NVDA,MU  # ad-hoc relaunch
    python -m scripts.edgar_8k_items --compact                 # jsonl -> parquet + manifest

WHY THIS EXISTS
===============
`scripts/scenario_bridge.py` graded 20 LLM-generated scenarios against the
2013-2024 panel and found 7 of 15 retrieval fields map to NOTHING this repo
owns -- `event_type` being the largest absence ("no dated event tape covers
2013-2024 in this repo"). SEC EDGAR's submissions API is a free, dated tape of
8-K filings WITH ITEM CODES (1.01 material agreement, 2.02 results, 2.06
impairment, 5.02 officer changes, 8.01 other ...), which is the cheapest dated
event taxonomy that exists. This collector pulls it.

PIT HONESTY -- THE ONE RULE THAT CANNOT RELAX
=============================================
An 8-K names TWO dates and they are different things:

    event_date            `reportDate` -- "date of earliest event reported".
                          When the thing HAPPENED.
    filing_date           `filingDate` -- when the filing was submitted.
    acceptance_datetime   `acceptanceDateTime` -- the EDGAR acceptance
                          timestamp (UTC). **This is the availability
                          timestamp.** Nothing in this row was knowable to
                          anyone reading EDGAR before this instant.

Every row stores all three, and downstream joins must gate on
`acceptance_datetime`, NEVER on `event_date` -- an event's own date standing in
for when it was knowable is look-ahead by construction (the 13F lesson: the
quarter-end is not the public date; the statutory deadline is).

SEC COURTESY RULES (https://www.sec.gov/os/accessing-edgar-data)
================================================================
- A descriptive User-Agent with a contact address is REQUIRED; anonymous
  clients are blocked. Ours names the project and Murat's email.
- Guidance is <=10 requests/second; this collector throttles to ~5/s
  (`MIN_INTERVAL_S`) and backs off exponentially on 429/403. A rate limit is
  reported as a rate limit, never read as "no filings" -- a rate limit reads
  as absence only to the careless (house rule).

SCOPE OF THE FIRST PULL, AND WHAT "recent" MEANS
================================================
`https://data.sec.gov/submissions/CIK##########.json` carries the ~1,000 most
recent filings per CIK (all form types mixed). For heavy filers that window
does NOT reach 2013, and `filings.files` lists older pages this collector only
fetches under `--full-history`. So the default manifest records, per CIK, the
EARLIEST filing date the pull actually saw (`coverage_start`) -- the tape's
coverage is what was fetched, not what was asked for. Absence of a row before
`coverage_start` is truncation, not evidence of no filing.

Two more coverage truths, named so nobody re-derives them:
- `company_tickers.json` maps CURRENT registrants. A company delisted in 2016
  is not in it, so a universe built from it is survivor-tilted. The manifest
  counts unresolved tickers.
- The ticker->CIK map is cached with its FETCH DATE; it drifts.

RESUMABLE
=========
Rows append to `eightk_rows.jsonl` and every finished CIK is checkpointed in
`checkpoint.json`, so a killed run resumes where it stopped and a later, bigger
range relaunches over the same files. `--compact` folds the jsonl into
`eightk_items.parquet` + `manifest.json` (row counts, date coverage, fetch
time, errors) -- the parquet is what the scenario bridge reads.

Licence: this is DATA ACQUISITION for a PRODUCT_EXPERIMENT. It claims nothing.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OUT_DIR = REPO / "backend" / "data" / "optimus" / "edgar_8k"
TICKER_CIK_CACHE = OUT_DIR / "company_tickers.json"
TICKER_CIK_META = OUT_DIR / "company_tickers.meta.json"
ROWS_JSONL = OUT_DIR / "eightk_rows.jsonl"
CHECKPOINT = OUT_DIR / "checkpoint.json"
PARQUET = OUT_DIR / "eightk_items.parquet"
MANIFEST = OUT_DIR / "manifest.json"

#: The receipt whose exemplar permnos define the scenario universe, and the
#: permno->ticker source used to resolve them.
SCENARIO_RECEIPT = (REPO / "backend" / "data" / "optimus" / "tracker_backtest"
                    / "scenario_bridge_20260903.json")
CRSP_PIT_MONTHLY = (REPO / "backend" / "data" / "optimus" / "crsp_pit"
                    / "crsp_pit_monthly_v1.parquet")
#: The tracker watchlist (aegis-alpha-terminal, READ-ONLY -- this repo never
#: writes into the execution repo's state).
TRACKER_LATEST = Path(r"C:\Users\mrthn\aegis-alpha-terminal\state\tracker\latest.json")

#: SEC requires a descriptive UA with a contact address. Email is Murat's own,
#: used here exactly as its owner directed (SEC UA requirement).
USER_AGENT = "Aegis-Finance research collector (contact: mrthnabdullaev@gmail.com)"

SUBMISSIONS_URL = "https://data.sec.gov/submissions/{name}"
COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

#: ~5 requests/second -- half the SEC's stated 10/s ceiling, on purpose.
MIN_INTERVAL_S = 0.21
MAX_RETRIES = 5
BACKOFF_BASE_S = 2.0

#: 8-K forms carry item codes; nothing else does.
EIGHTK_FORMS = ("8-K", "8-K/A")

_ITEM_CODE_RE = re.compile(r"\d+\.\d{2}")


# ============================================================ pure parsing
# (everything in this section is offline and unit-tested; nothing here opens
#  a socket)

def normalize_items(raw: str | None) -> list[str]:
    """'2.02,9.01' / 'Item 2.02, Item 9.01' -> ['2.02', '9.01'] (sorted, unique).

    Pre-2004 8-Ks used bare item numbers ('5', '7'); those carry no dot-code
    and come back empty -- callers see `items=[]` and must treat it as "item
    regime not parseable", not "no items". The panel starts 2013 so the modern
    regime covers everything we grade.
    """
    if not raw:
        return []
    return sorted(set(_ITEM_CODE_RE.findall(str(raw))))


def parse_submissions(sub: dict, *, cik: int, ticker: str | None,
                      start: str, end: str,
                      forms: Iterable[str] = EIGHTK_FORMS) -> list[dict]:
    """8-K rows from one submissions JSON block (`filings.recent` shape).

    The date-range filter runs on **filing_date**, not event_date: a filing
    made inside the range about an event just before it is knowledge acquired
    inside the range and is KEPT; an event inside the range whose filing came
    after `end` was not knowable by `end` and is EXCLUDED. Two clocks, and the
    filter is on the knowability clock.
    """
    recent = (sub.get("filings") or {}).get("recent") or sub
    forms_l = recent.get("form") or []
    n = len(forms_l)
    cols = {k: (recent.get(k) or [None] * n)
            for k in ("filingDate", "acceptanceDateTime", "reportDate",
                      "accessionNumber", "items", "primaryDocument")}
    want = set(forms)
    rows: list[dict] = []
    for i, form in enumerate(forms_l):
        if form not in want:
            continue
        fdate = cols["filingDate"][i]
        if not fdate or not (start <= fdate <= end):
            continue
        rows.append({
            "cik": int(cik),
            "ticker": ticker,
            "form": form,
            "accession": cols["accessionNumber"][i],
            "event_date": cols["reportDate"][i] or None,
            "filing_date": fdate,
            # THE availability timestamp. Never event_date.
            "acceptance_datetime": cols["acceptanceDateTime"][i] or None,
            "items_raw": cols["items"][i] or "",
            "items": normalize_items(cols["items"][i]),
            "primary_document": cols["primaryDocument"][i] or None,
        })
    return rows


def coverage_start_of(sub: dict) -> str | None:
    """Earliest filing date (ANY form) present in this submissions block --
    the honest left edge of what `recent` actually covers for this CIK."""
    recent = (sub.get("filings") or {}).get("recent") or sub
    dates = [d for d in (recent.get("filingDate") or []) if d]
    return min(dates) if dates else None


# ============================================================ universe

def _log(*a: Any) -> None:
    print(*a, flush=True)


def scenario_universe_tickers() -> dict[str, int | None]:
    """ticker -> permno for the exemplar permnos in the graded-scenario receipt.

    Resolution: last known CRSP ticker per permno (crsp_pit_monthly_v1). A
    permno with no ticker row resolves to nothing and is COUNTED, not dropped
    silently.
    """
    import pandas as pd
    receipt = json.loads(SCENARIO_RECEIPT.read_text(encoding="utf-8"))
    permnos: set[int] = set()
    for sc in receipt.get("scenarios", []):
        for ex in (sc.get("retrieval") or {}).get("exemplars") or []:
            permnos.add(int(ex["permno"]))
    if not permnos:
        raise SystemExit(f"REFUSED: no exemplar permnos in {SCENARIO_RECEIPT}")
    px = pd.read_parquet(CRSP_PIT_MONTHLY, columns=["permno", "date", "ticker"])
    px = px[px["permno"].isin(permnos) & px["ticker"].notna()]
    last = (px.sort_values("date").groupby("permno")["ticker"].last())
    out = {str(t).upper(): int(p) for p, t in last.items()}
    unresolved = permnos - set(int(p) for p in last.index)
    _log(f"[universe] scenario receipt: {len(permnos)} exemplar permnos, "
         f"{len(out)} distinct tickers resolved, "
         f"{len(unresolved)} permnos with no CRSP ticker row")
    return out


def tracker_universe_tickers() -> list[str]:
    """Symbols from the tracker's latest day (read-only on the terminal repo).

    `latest.json` exposes only the day's CANDIDATES (~800); the full watchlist
    (~3k) lives in the day's jsonl next to it. Prefer the jsonl, fall back to
    the candidate list, and say which one was read.
    """
    if not TRACKER_LATEST.exists():
        _log(f"[universe] tracker watchlist ABSENT at {TRACKER_LATEST} -- skipped "
             f"(absence of the file is not evidence about the watchlist)")
        return []
    d = json.loads(TRACKER_LATEST.read_text(encoding="utf-8"))
    day = (d.get("summary") or {}).get("day")
    daily = TRACKER_LATEST.parent / f"{day}.jsonl" if day else None
    if daily and daily.exists():
        syms: set[str] = set()
        for line in daily.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                s = json.loads(line).get("symbol")
            except ValueError:
                continue
            if s:
                syms.add(str(s).upper())
        _log(f"[universe] tracker daily jsonl {day}: {len(syms)} symbols")
        return sorted(syms)
    syms = sorted({str(c.get("symbol", "")).upper()
                   for c in d.get("candidates", []) if c.get("symbol")})
    _log(f"[universe] tracker latest.json (candidates only) day={day}: "
         f"{len(syms)} symbols")
    return sorted(syms)


# ============================================================ HTTP (live only)

class _Client:
    """Throttled EDGAR client. Every response code is accounted for."""

    def __init__(self) -> None:
        import requests
        self.sess = requests.Session()
        self.sess.headers.update({"User-Agent": USER_AGENT,
                                  "Accept-Encoding": "gzip, deflate"})
        self._last = 0.0
        self.stats = {"requests": 0, "ok": 0, "not_found": 0,
                      "rate_limited": 0, "errors": 0, "backoff_seconds": 0.0}

    def get_json(self, url: str) -> dict | None:
        """None means 404 (a real absence at EDGAR). Raises after MAX_RETRIES
        on persistent throttling/errors -- an aborted run says so."""
        for attempt in range(MAX_RETRIES):
            wait = self._last + MIN_INTERVAL_S - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            self.stats["requests"] += 1
            try:
                r = self.sess.get(url, timeout=30)
            except Exception as exc:                          # noqa: BLE001
                self.stats["errors"] += 1
                back = BACKOFF_BASE_S * (2 ** attempt)
                self.stats["backoff_seconds"] += back
                _log(f"  [net] {type(exc).__name__} on {url[-40:]} -- "
                     f"backoff {back:.0f}s")
                time.sleep(back)
                continue
            if r.status_code == 200:
                self.stats["ok"] += 1
                return r.json()
            if r.status_code == 404:
                self.stats["not_found"] += 1
                return None
            if r.status_code in (403, 429, 503):
                self.stats["rate_limited"] += 1
                back = BACKOFF_BASE_S * (2 ** attempt)
                self.stats["backoff_seconds"] += back
                _log(f"  [throttle] HTTP {r.status_code} -- backing off {back:.0f}s")
                time.sleep(back)
                continue
            self.stats["errors"] += 1
            _log(f"  [net] HTTP {r.status_code} on {url[-60:]}")
            time.sleep(BACKOFF_BASE_S)
        raise RuntimeError(
            f"EDGAR still refusing after {MAX_RETRIES} attempts on {url} -- "
            f"stats {self.stats}. This is a rate limit / block, NOT an absence "
            f"of filings. Resume later with the same command (checkpointed).")


def load_ticker_cik_map(client: _Client | None = None,
                        force: bool = False) -> dict[str, int]:
    """ticker -> CIK from EDGAR's company_tickers.json, cached with fetch date."""
    if TICKER_CIK_CACHE.exists() and not force:
        raw = json.loads(TICKER_CIK_CACHE.read_text(encoding="utf-8"))
    else:
        client = client or _Client()
        raw = client.get_json(COMPANY_TICKERS_URL)
        if raw is None:
            raise RuntimeError("company_tickers.json returned 404 -- refusing")
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        TICKER_CIK_CACHE.write_text(json.dumps(raw), encoding="utf-8")
        TICKER_CIK_META.write_text(json.dumps({
            "source": COMPANY_TICKERS_URL,
            "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
            "n_entries": len(raw),
            "caveat": ("CURRENT registrants only; a company delisted before "
                       "today is absent, so any universe resolved through this "
                       "map is survivor-tilted and the manifest counts the "
                       "unresolved"),
        }, indent=2), encoding="utf-8")
    return {str(v["ticker"]).upper(): int(v["cik_str"]) for v in raw.values()}


# ============================================================ the pull

def _load_checkpoint() -> dict:
    if CHECKPOINT.exists():
        return json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    return {"done": {}, "unresolved_tickers": [], "started_utc": None}


def _save_checkpoint(ck: dict) -> None:
    CHECKPOINT.write_text(json.dumps(ck, indent=1), encoding="utf-8")


def pull(universe: str = "both", tickers_extra: str = "",
         start: str = "2013-01-01", end: str | None = None,
         full_history: bool = False, limit: int = 0) -> dict:
    """Fetch 8-K rows for the universe. Resumable; appends to ROWS_JSONL."""
    end = end or datetime.now(timezone.utc).date().isoformat()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # ---- universe
    permno_by_ticker: dict[str, int | None] = {}
    if universe in ("scenario", "both"):
        permno_by_ticker.update(scenario_universe_tickers())
    if universe in ("tracker", "both"):
        for t in tracker_universe_tickers():
            permno_by_ticker.setdefault(t, None)
    for t in (x.strip().upper() for x in tickers_extra.split(",") if x.strip()):
        permno_by_ticker.setdefault(t, None)
    if not permno_by_ticker:
        raise SystemExit("REFUSED: empty universe")

    client = _Client()
    t2c = load_ticker_cik_map(client)
    resolved = {t: t2c[t] for t in permno_by_ticker if t in t2c}
    unresolved = sorted(t for t in permno_by_ticker if t not in t2c)
    _log(f"[cik] {len(resolved)}/{len(permno_by_ticker)} tickers resolved to a "
         f"CIK; {len(unresolved)} unresolved (delisted or non-EDGAR)")

    # one CIK can carry several tickers; fetch each CIK once, keep first ticker
    cik_ticker: dict[int, str] = {}
    for t, c in sorted(resolved.items()):
        cik_ticker.setdefault(c, t)

    ck = _load_checkpoint()
    ck.setdefault("done", {})
    ck["unresolved_tickers"] = unresolved
    ck["started_utc"] = ck.get("started_utc") or datetime.now(
        timezone.utc).isoformat()
    ck["params"] = {"start": start, "end": end, "universe": universe,
                    "full_history": full_history}

    todo = [c for c in cik_ticker if str(c) not in ck["done"]]
    if limit:
        todo = todo[:limit]
    _log(f"[pull] {len(todo)} CIKs to fetch ({len(ck['done'])} already done), "
         f"~{len(todo) * MIN_INTERVAL_S / 60:.1f} min at "
         f"{1 / MIN_INTERVAL_S:.1f} req/s")

    n_rows = 0
    t0 = time.monotonic()
    with ROWS_JSONL.open("a", encoding="utf-8") as fh:
        for i, cik in enumerate(todo):
            ticker = cik_ticker[cik]
            name = f"CIK{cik:010d}.json"
            sub = client.get_json(SUBMISSIONS_URL.format(name=name))
            if sub is None:
                ck["done"][str(cik)] = {"ticker": ticker, "status": "404",
                                        "n_rows": 0}
                _save_checkpoint(ck)
                continue
            rows = parse_submissions(sub, cik=cik, ticker=ticker,
                                     start=start, end=end)
            cov = coverage_start_of(sub)
            extra_pages = 0
            if full_history and cov and cov > start:
                for f in (sub.get("filings") or {}).get("files", []):
                    if f.get("filingTo") and f["filingTo"] < start:
                        continue
                    page = client.get_json(SUBMISSIONS_URL.format(name=f["name"]))
                    if page:
                        rows += parse_submissions(page, cik=cik, ticker=ticker,
                                                  start=start, end=end)
                        pd_ = [d for d in (page.get("filingDate") or []) if d]
                        if pd_:
                            cov = min(cov, min(pd_))
                        extra_pages += 1
            permno = permno_by_ticker.get(ticker)
            for r in rows:
                r["permno"] = permno
                fh.write(json.dumps(r) + "\n")
            fh.flush()
            n_rows += len(rows)
            ck["done"][str(cik)] = {
                "ticker": ticker, "status": "ok", "n_rows": len(rows),
                "coverage_start": cov, "extra_pages": extra_pages,
            }
            if i % 25 == 24 or i == len(todo) - 1:
                _save_checkpoint(ck)
                rate = (i + 1) / max(time.monotonic() - t0, 1e-9)
                _log(f"  [{i + 1}/{len(todo)}] {ticker} rows+={len(rows)} "
                     f"total={n_rows} ({rate:.1f} CIK/s)")
    _save_checkpoint(ck)
    _log(f"[pull] done: {n_rows} new rows; client stats {client.stats}")
    return {"n_rows_new": n_rows, "client": client.stats,
            "n_ciks": len(cik_ticker), "n_unresolved": len(unresolved)}


# ============================================================ compact

def compact() -> dict:
    """jsonl -> parquet + manifest. The parquet is the tape downstream reads."""
    import pandas as pd
    if not ROWS_JSONL.exists():
        raise SystemExit(f"REFUSED: {ROWS_JSONL} absent -- nothing was pulled.")
    rows = [json.loads(l) for l in
            ROWS_JSONL.read_text(encoding="utf-8").splitlines() if l.strip()]
    df = pd.DataFrame(rows)
    if df.empty:
        raise SystemExit("REFUSED: zero rows in the jsonl.")
    # one accession can appear twice after a resume; the accession is the key
    df = df.drop_duplicates(subset=["cik", "accession"], keep="last")
    df["items_joined"] = df["items"].map(lambda x: ",".join(x))
    df = df.sort_values(["cik", "filing_date", "accession"]).reset_index(drop=True)
    df.to_parquet(PARQUET, index=False)

    ck = _load_checkpoint()
    done = ck.get("done", {})
    cov = [v.get("coverage_start") for v in done.values()
           if v.get("coverage_start")]
    item_counts = (df["items"].explode().value_counts().to_dict()
                   if len(df) else {})
    manifest = {
        "tape": "edgar_8k_items",
        "built_utc": datetime.now(timezone.utc).isoformat(),
        "source": "SEC EDGAR submissions API (data.sec.gov)",
        "user_agent": USER_AGENT,
        "throttle_req_per_s": round(1 / MIN_INTERVAL_S, 2),
        "rows": int(len(df)),
        "ciks": int(df["cik"].nunique()),
        "tickers": int(df["ticker"].nunique()),
        "with_permno": int(df["permno"].notna().sum()),
        "filing_date_min": str(df["filing_date"].min()),
        "filing_date_max": str(df["filing_date"].max()),
        "rows_with_items": int((df["items"].map(len) > 0).sum()),
        "item_histogram": {str(k): int(v) for k, v in
                           sorted(item_counts.items(),
                                  key=lambda kv: -kv[1])},
        "params": ck.get("params", {}),
        "ciks_fetched": len(done),
        "ciks_404": sum(1 for v in done.values() if v.get("status") == "404"),
        "unresolved_tickers": len(ck.get("unresolved_tickers", [])),
        "coverage_start_median": sorted(cov)[len(cov) // 2] if cov else None,
        "coverage_truncation_caveat": (
            "the default pull reads only `filings.recent` (~1,000 most recent "
            "filings per CIK, all forms); a heavy filer's 8-K history is "
            "TRUNCATED at its coverage_start. Absence of a row before "
            "coverage_start is truncation, not evidence of no filing. "
            "--full-history fetches the older pages."),
        "pit_rule": ("availability = acceptance_datetime (EDGAR acceptance, "
                     "UTC). event_date is when the thing happened; it is NEVER "
                     "the knowability gate."),
        "survivor_caveat": ("universe resolved via company_tickers.json = "
                            "CURRENT registrants; names delisted before the "
                            "map's fetch date are absent"),
    }
    MANIFEST.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    _log(f"[compact] {len(df)} rows -> {PARQUET}")
    _log(f"[manifest] -> {MANIFEST}")
    return manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pull", action="store_true")
    ap.add_argument("--compact", action="store_true")
    ap.add_argument("--universe", choices=("scenario", "tracker", "both"),
                    default="both")
    ap.add_argument("--tickers", default="", help="extra tickers, comma-sep")
    ap.add_argument("--start", default="2013-01-01")
    ap.add_argument("--end", default=None)
    ap.add_argument("--full-history", action="store_true",
                    help="also fetch older submission pages back to --start")
    ap.add_argument("--limit", type=int, default=0,
                    help="fetch at most N CIKs (smoke runs)")
    a = ap.parse_args(argv)
    if a.pull:
        pull(universe=a.universe, tickers_extra=a.tickers, start=a.start,
             end=a.end, full_history=a.full_history, limit=a.limit)
    if a.compact:
        compact()
    if not (a.pull or a.compact):
        ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
