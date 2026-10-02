"""Free OFFICIAL sources, read through their own APIs and feeds (no browser),
landed as point-in-time TYPED ROWS the CRSP bridge and the hypothesis lab join
by ticker and date.

Murat, 2026-09-29: "use openclaw to review stocks or the general news and the
market positions, insider traders, politics etc anything needed", "digest
everything". The browser reader spends its 4,000 page loads a day on the news
sites; everything that has an OFFICIAL machine-readable form is read here
instead -- faster, allowed, no browser, no account:

| source            | how it is read                                   | table               |
|-------------------|--------------------------------------------------|---------------------|
| SEC Form 4        | EDGAR "latest filings" Atom + each filing's index page (acceptance time) + its XML | insider_tx |
| SEC 8-K, 13D/G, 13F | EDGAR "latest filings" Atom (items from the entry) | filing_events      |
| House PTRs        | the Clerk's annual index (zip) + each PTR PDF's text | politician_filings, politician_trades |
| CFTC COT (TFF, disaggregated) | CFTC Public Reporting (Socrata) JSON  | positioning_cot     |
| FINRA short interest | FINRA Query API (consolidatedShortInterest)    | short_interest      |
| FINRA short-sale volume | the existing `finra_short_volume` store (CDN files) | (its own parquet) |
| Federal Register  | federalregister.gov API: documents + public inspection | policy_events   |
| Fed, ECB, BoJ, BoE, HKMA, White House, Treasury | their RSS / JSON feeds | policy_events |

THE TIMESTAMP RULE (every row): `public_utc` is when the WORLD could know it --
EDGAR acceptance time (a filing accepted after the day's filing window, whose
index shows a later filing date, is public at 06:00 ET on that date), a
disclosure date, a release time -- NEVER the transaction, trade, period or
report date, which are kept in their own fields. `public_ts_basis` names the
rule used; `first_seen_utc` is when this collector first held the row.

REFUSALS (recorded, never worked around): a robots.txt that disallows the
path; a bot check / access-denied page (403/429 with a block marker) cools the
source for `OFFICIAL_COOL_S`; a form in front of the data (the Senate eFD
agreement page) is not submitted. Brokerage, bank, payment and mail hosts are
never on the list. Every request is one line in `official/requests.jsonl`
(source, host, status, class, bytes); each source has its own daily cap and
the SEC path goes through the process-wide EDGAR rate limiter.
"""
from __future__ import annotations

import csv
import io
import json
import math
import re
import time
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from typing import Any, Callable, Iterable, Optional
from urllib.parse import urlsplit

from backend import config as _config
from backend.services import disk_guard as DG


def _cfg(name: str, default: Any) -> Any:
    return getattr(_config, name, default)


try:
    from zoneinfo import ZoneInfo
    ET_TZ = ZoneInfo("America/New_York")
except Exception:  # noqa: BLE001 -- no tz database: a fixed -4 h offset
    ET_TZ = timezone(timedelta(hours=-4))

UA = "AegisFinance-reader/1.0 (personal research; read-only)"

# ─────────────────────────────── the registry ────────────────────────────────
#
# lane: the reading-budget lane the source reports under; day_cap: requests a
# rolling 24 h; every_s: how often a `--due` run reads it; min_gap_s: between
# two requests to its host.

SOURCES: dict[str, dict] = {
    "sec_form4": {"lane": "insiders_filings", "host": "www.sec.gov", "day_cap": 14000,
                  "every_s": 900, "min_gap_s": 0.2, "sec": True,
                  "how": "EDGAR latest-filings Atom + filing index page + ownership XML"},
    "sec_8k": {"lane": "insiders_filings", "host": "www.sec.gov", "day_cap": 300,
               "every_s": 900, "min_gap_s": 0.2, "sec": True,
               "how": "EDGAR latest-filings Atom (8-K items from each entry)"},
    "sec_13dg": {"lane": "insiders_filings", "host": "www.sec.gov", "day_cap": 200,
                 "every_s": 1800, "min_gap_s": 0.2, "sec": True,
                 "how": "EDGAR latest-filings Atom (SCHEDULE 13D / 13G and SC 13D/G)"},
    "sec_13f": {"lane": "positioning", "host": "www.sec.gov", "day_cap": 100,
                "every_s": 3600, "min_gap_s": 0.2, "sec": True,
                "how": "EDGAR latest-filings Atom (13F-HR filed; holdings not parsed)"},
    "sec_tickers": {"lane": "overhead", "host": "www.sec.gov", "day_cap": 4,
                    "every_s": 86400, "min_gap_s": 0.2, "sec": True,
                    "how": "SEC company_tickers.json (CIK -> ticker)"},
    "house_ptr": {"lane": "politics_policy", "host": "disclosures-clerk.house.gov",
                  "day_cap": 150, "every_s": 6 * 3600, "min_gap_s": 2.0,
                  "how": "House Clerk annual FD index (zip) + each PTR PDF's text"},
    "cftc_cot": {"lane": "positioning", "host": "publicreporting.cftc.gov", "day_cap": 40,
                 "every_s": 6 * 3600, "min_gap_s": 2.0,
                 "how": "CFTC Public Reporting API: TFF futures + disaggregated futures"},
    "finra_si": {"lane": "positioning", "host": "api.finra.org", "day_cap": 80,
                 "every_s": 12 * 3600, "min_gap_s": 2.0,
                 "how": "FINRA Query API consolidatedShortInterest (by settlement date)"},
    "finra_sv": {"lane": "positioning", "host": "cdn.finra.org", "day_cap": 20,
                 "every_s": 6 * 3600, "min_gap_s": 2.0,
                 "how": "FINRA Reg SHO daily short-sale volume files (existing store)"},
    "fedreg": {"lane": "politics_policy", "host": "www.federalregister.gov", "day_cap": 60,
               "every_s": 2 * 3600, "min_gap_s": 2.0,
               "how": "Federal Register API: documents published + public inspection"},
    "fed_rss": {"lane": "official_releases", "host": "www.federalreserve.gov", "day_cap": 160,
                "every_s": 3600, "min_gap_s": 2.0,
                "how": "Federal Reserve RSS: all press releases, speeches, testimony; plus each "
                       "item's full text by plain HTTP (policy_texts). Since 2026-09-30 the Fed "
                       "is never opened in the visible browser"},
    "ecb_rss": {"lane": "official_releases", "host": "www.ecb.europa.eu", "day_cap": 40,
                "every_s": 3600, "min_gap_s": 2.0, "how": "ECB press RSS"},
    "boj_rss": {"lane": "official_releases", "host": "www.boj.or.jp", "day_cap": 40,
                "every_s": 3600, "min_gap_s": 2.0, "how": "Bank of Japan what's-new RSS"},
    "boe_rss": {"lane": "official_releases", "host": "www.bankofengland.co.uk", "day_cap": 40,
                "every_s": 3600, "min_gap_s": 2.0, "how": "Bank of England news RSS"},
    "hkma_api": {"lane": "official_releases", "host": "api.hkma.gov.hk", "day_cap": 40,
                 "every_s": 3600, "min_gap_s": 2.0,
                 "how": "HKMA open API: press releases (retried with backoff); when the API is "
                        "down, HKMA's own RSS (press releases, speeches) on www.hkma.gov.hk"},
    "whitehouse_rss": {"lane": "politics_policy", "host": "www.whitehouse.gov", "day_cap": 40,
                       "every_s": 3600, "min_gap_s": 3.0,
                       "how": "White House RSS: presidential actions, news"},
    "treasury_rss": {"lane": "politics_policy", "host": "home.treasury.gov", "day_cap": 40,
                     "every_s": 3600, "min_gap_s": 3.0, "how": "US Treasury RSS"},
}

#: sources looked at and NOT read, with the reason; re-checked by `--probe`
REFUSED_SOURCES: dict[str, dict] = {
    "senate_efd": {"url": "https://efdsearch.senate.gov/search/",
                   "why": "BOT_CHECK_OR_FORM: 403 Access Denied to a plain request, and the "
                          "search sits behind an agreement form; not submitted, not worked around"},
    "senate_hearings": {"url": "https://www.senate.gov/general/committee_schedules/hearings.xml",
                        "why": "ACCESS_DENIED: 403 on the XML and on robots.txt"},
    "pboc": {"url": "http://www.pbc.gov.cn/en/3688110/3688172/index.html",
             "why": "ROBOTS_DISALLOWED: pbc.gov.cn robots.txt disallows the English news path"},
    "nasdaq_earnings": {"url": "https://api.nasdaq.com/api/calendar/earnings",
                        "why": "ROBOTS_DISALLOWED: api.nasdaq.com robots.txt disallows it"},
    "house_hearings": {"url": "https://docs.house.gov/Committee/Calendar/ByWeek.aspx",
                       "why": "JS_RENDERED: the calendar is built by script in the page; no "
                              "machine-readable feed was found. A candidate for the browser lane"},
    "etf_flows": {"url": None,
                  "why": "NO_OFFICIAL_FREE_SOURCE: issuer pages publish shares outstanding per "
                         "fund, but no official free flow feed across funds was found"},
}

RSS_FEEDS: dict[str, list[tuple[str, str]]] = {
    "fed_rss": [("fed_press", "https://www.federalreserve.gov/feeds/press_all.xml"),
                ("fed_speech", "https://www.federalreserve.gov/feeds/speeches.xml"),
                ("fed_testimony", "https://www.federalreserve.gov/feeds/testimony.xml")],
    "ecb_rss": [("ecb_press", "https://www.ecb.europa.eu/rss/press.html")],
    "boj_rss": [("boj_whatsnew", "https://www.boj.or.jp/en/rss/whatsnew.xml")],
    "boe_rss": [("boe_news", "https://www.bankofengland.co.uk/rss/news")],
    "whitehouse_rss": [("wh_actions", "https://www.whitehouse.gov/presidential-actions/feed/"),
                       ("wh_news", "https://www.whitehouse.gov/news/feed/")],
    "treasury_rss": [("treasury", "https://home.treasury.gov/rss.xml")],
}

TABLES = ("insider_tx", "filing_events", "politician_filings", "politician_trades",
          "positioning_cot", "short_interest", "policy_events", "policy_texts")

#: 2026-09-30: sources whose feed items' FULL TEXT is fetched by plain HTTP (the
#: same fetcher: robots, caps, pacing, money rule) into `policy_texts`, because
#: the feed carries only a title and a line. The Fed left the visible browser the
#: same night; this is what keeps its speeches and statements readable.
TEXT_SOURCES: dict[str, dict] = {
    "fed_rss": {"url_prefix": "https://www.federalreserve.gov/", "max_per_run": 15,
                "max_age_days": 14, "max_chars": 40000},
}

#: the schema of each table: field -> meaning (printed by `--schema`, and in the
#: research note). Every table carries row_id, source, public_utc,
#: public_ts_basis, first_seen_utc.
SCHEMAS: dict[str, dict[str, str]] = {
    "insider_tx": {
        "row_id": "accession:line (stable)", "accession": "EDGAR accession", "form_type": "4, 4/A, 5...",
        "public_utc": "EDGAR acceptance (after-hours -> 06:00 ET on the filing date)",
        "ticker": "issuer trading symbol as filed", "issuer_cik": "", "issuer_name": "",
        "owner_name": "first reporting owner", "owner_cik": "", "n_owners": "joint filings",
        "role": "CEO/CFO/officer/director/10pct/other", "officer_title": "",
        "is_officer": "", "is_director": "", "is_ten_pct_owner": "",
        "code": "SEC transaction code (P, S, A, M, F, ...)", "side": "buy/sell/other",
        "is_discretionary_market_trade": "P or S", "rule_10b5_1": "True/False/None (unknown)",
        "transaction_date": "when the insider traded (NOT tradable)", "shares": "", "price": "",
        "value_usd": "shares x price", "shares_owned_after": "", "is_derivative": "",
        "security_title": "", "ownership_type": "D/I", "index_url": ""},
    "filing_events": {
        "row_id": "form:accession:role", "form_type": "8-K, SCHEDULE 13D/G, SC 13D/G, 13F-HR",
        "public_utc": "Atom <updated> = acceptance time", "cik": "", "company": "",
        "role": "Filer / Subject / Filed by", "ticker": "via SEC company_tickers (CIK)",
        "items": "8-K item numbers", "event_types": "edgar_events taxonomy", "index_url": ""},
    "politician_filings": {
        "row_id": "house:DocID", "chamber": "house", "member": "", "state_district": "",
        "filing_type": "P = periodic transaction report", "doc_id": "",
        "disclosure_date": "the filing date on the Clerk's index",
        "public_utc": "disclosure date 23:59 ET (the index gives a date only)", "pdf_url": "",
        "text_status": "TEXT / SCANNED_NO_TEXT / NOT_FETCHED"},
    "politician_trades": {
        "row_id": "house:DocID:n", "doc_id": "", "member": "", "owner": "SP/JT/DC/self",
        "asset": "", "ticker": "from the asset's (TICKER)", "asset_type": "[ST] etc.",
        "tx_type": "P / S / S (partial) / E", "trade_date": "NOT tradable",
        "notification_date": "", "disclosure_date": "", "lag_days": "disclosure - trade",
        "amount_lo": "", "amount_hi": "", "public_utc": "disclosure date 23:59 ET",
        "tradable_from_utc": "the next US session after public_utc"},
    "positioning_cot": {
        "row_id": "report:code:date", "report": "tff / disagg", "market": "", "code": "",
        "report_date": "Tuesday position date (NOT tradable)",
        "public_utc": "Friday 15:30 ET after the report date (CFTC release schedule)",
        "open_interest": "", "groups": "{group: {long, short, net, net_pct_oi, chg_net}}",
        "headline_group": "lev_money (TFF) / managed_money (disagg)",
        "headline_net_pct_oi": "", "headline_pctile_3y": "percentile of net % OI over 156 weeks",
        "headline_chg_z": "z of the weekly change in net over 156 weeks"},
    "policy_texts": {
        "row_id": "the policy_events row_id this text belongs to", "source": "fed_rss",
        "url": "", "title": "", "public_utc": "copied from the policy_events row (the feed time)",
        "public_ts_basis": "", "text": "the release / speech / testimony text (tags stripped)",
        "chars": "length before truncation", "truncated": "", "status": "TEXT / EMPTY / HTTP_<n>"},
    "short_interest": {
        "row_id": "si:symbol:settlement", "symbol": "", "settlement_date": "NOT tradable",
        "public_utc": "settlement + 8 business days 23:00 UTC, or first seen if later",
        "short_qty": "", "prev_short_qty": "", "change_pct": "", "avg_daily_volume": "",
        "days_to_cover": "", "market": ""},
    "policy_events": {
        "row_id": "source:id", "source": "fedreg / fedreg_pi / fed_press / ecb_press / ...",
        "public_utc": "publication / filing / pubDate time", "title": "", "url": "",
        "agency": "", "doc_type": "", "significant": "Federal Register EO 12866 flag",
        "relevant": "an agency / source on the market-relevant list", "summary": "<= 600 chars"},
}


# ─────────────────────────────── paths, state ────────────────────────────────

def root(base: Optional[Path] = None) -> Path:
    return Path(base) if base is not None else Path(_config.OPTIMUS_LEDGER_DIR) / "official"


def table_path(table: str, base: Optional[Path] = None) -> Path:
    if table not in TABLES:
        raise ValueError(f"unknown table {table!r}")
    return root(base) / "tables" / f"{table}.jsonl"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).isoformat(timespec="seconds")


def _read_json(p: Path, default: Any) -> Any:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def read_table(table: str, base: Optional[Path] = None, *,
               since: Optional[datetime] = None) -> list[dict]:
    """Every row of `table` (optionally only rows public at or after `since`)."""
    out = []
    try:
        lines = table_path(table, base).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    for ln in lines:
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if since is not None:
            try:
                if datetime.fromisoformat(str(r.get("public_utc"))) < since:
                    continue
            except (TypeError, ValueError):
                continue
        out.append(r)
    return out


def append_rows(table: str, rows: Iterable[dict], base: Optional[Path] = None,
                now: Optional[datetime] = None) -> int:
    """Append rows whose `row_id` is not in the table yet (append-only; a row
    is never rewritten). Stamps `first_seen_utc`. Returns rows written."""
    p = table_path(table, base)
    p.parent.mkdir(parents=True, exist_ok=True)
    stamp = iso(now or _now())
    n = 0
    with DG.file_lock(p.with_name(p.name + ".lock")):
        have = set()
        try:
            for ln in p.read_text(encoding="utf-8", errors="replace").splitlines():
                m = re.search(r'"row_id":\s*"([^"]+)"', ln)
                if m:
                    have.add(m.group(1))
        except OSError:
            pass
        out = []
        for r in rows:
            rid = str(r.get("row_id") or "")
            if not rid or rid in have or not r.get("public_utc"):
                continue
            have.add(rid)
            out.append(json.dumps({**r, "first_seen_utc": r.get("first_seen_utc") or stamp},
                                  default=str, ensure_ascii=False))
        if out:
            with p.open("a", encoding="utf-8") as fh:
                fh.write("\n".join(out) + "\n")
            n = len(out)
    return n


# ─────────────────────────── time rules (PURE) ───────────────────────────────

def et_to_utc(d: datetime) -> datetime:
    """A naive New York wall-clock time -> aware UTC."""
    if d.tzinfo is None:
        d = d.replace(tzinfo=ET_TZ)
    return d.astimezone(timezone.utc)


def edgar_public_utc(accepted_et: datetime, filing_date: Optional[date] = None) -> tuple[datetime, str]:
    """PURE. When an EDGAR filing became public. Accepted inside the filing
    window: the acceptance time. Accepted after it (the index shows a LATER
    filing date): 06:00 ET on that filing date, when EDGAR disseminates it."""
    acc = et_to_utc(accepted_et)
    if filing_date is not None and filing_date > accepted_et.date():
        return et_to_utc(datetime.combine(filing_date, datetime.min.time()).replace(hour=6)), \
            "EDGAR_AFTER_HOURS_FILING_DATE_0600ET"
    return acc, "EDGAR_ACCEPTANCE"


def next_business_day(d: date) -> date:
    d = d + timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def add_business_days(d: date, n: int) -> date:
    for _ in range(n):
        d = next_business_day(d)
    return d


def disclosure_public_utc(d: date) -> datetime:
    """PURE. A disclosure dated `d` with no time: public by 23:59 ET that day."""
    return et_to_utc(datetime.combine(d, datetime.min.time()).replace(hour=23, minute=59))


def tradable_from_utc(public: datetime) -> datetime:
    """PURE. The next US regular-session open (09:30 ET) strictly after `public`
    (weekends skipped; exchange holidays are not modelled -- later is safe)."""
    loc = public.astimezone(ET_TZ)
    d = loc.date()
    open_t = datetime.combine(d, datetime.min.time()).replace(hour=9, minute=30, tzinfo=ET_TZ)
    if d.weekday() >= 5 or loc >= open_t:
        d = next_business_day(d)
    return datetime.combine(d, datetime.min.time()).replace(
        hour=9, minute=30, tzinfo=ET_TZ).astimezone(timezone.utc)


def cot_public_utc(report_date: date) -> datetime:
    """PURE. CFTC releases a Tuesday position report on Friday 15:30 ET (3 days
    later; a holiday week slips it -- the schedule time is a lower bound on the
    delay, so a holiday week makes the row later, never earlier, in truth)."""
    d = report_date + timedelta(days=(4 - report_date.weekday()) % 7 or 3)
    return et_to_utc(datetime.combine(d, datetime.min.time()).replace(hour=15, minute=30))


def short_interest_public_utc(settlement: date) -> datetime:
    """PURE. FINRA disseminates a settlement date's short interest about eight
    business days later; 23:00 UTC that day (after its evening release)."""
    d = add_business_days(settlement, 8)
    return datetime.combine(d, datetime.min.time()).replace(hour=23, tzinfo=timezone.utc)


def fedreg_public_utc(publication_date: date) -> datetime:
    """PURE. The Federal Register's daily issue is public at 06:00 ET."""
    return et_to_utc(datetime.combine(publication_date, datetime.min.time()).replace(hour=6))


# ───────────────────────────── the fetcher ───────────────────────────────────

class SourceRefused(RuntimeError):
    """A source was not read, and why (the class is the first token)."""


_BLOCK_MARKERS = re.compile(r"access denied|captcha|are you a robot|verify you are human|"
                            r"just a moment|attention required|request rejected|"
                            r"pardon our interruption|unusual traffic|bot detection", re.I)


def classify_response(status: int, body: bytes | str) -> str:
    """PURE. OK / NOT_FOUND / BOT_CHECK / RATE_LIMITED / SERVER_ERROR / HTTP_<n>."""
    text = body.decode("utf-8", "replace") if isinstance(body, bytes) else (body or "")
    head = text[:3000]
    if status == 429:
        return "RATE_LIMITED"
    if status in (401, 403) or (status >= 400 and _BLOCK_MARKERS.search(head)):
        return "BOT_CHECK" if _BLOCK_MARKERS.search(head) else f"HTTP_{status}"
    if status == 200 and len(text) < 2000 and _BLOCK_MARKERS.search(head):
        return "BOT_CHECK"
    if status == 404:
        return "NOT_FOUND"
    if status >= 500:
        return "SERVER_ERROR"
    return "OK" if 200 <= status < 300 else f"HTTP_{status}"


def robots_allows(text: str | None, url: str, agent: str = UA) -> bool:
    """PURE. No file / no groups = allowed; else the standard parser, for our
    agent name and for `*`."""
    if not text or "user-agent" not in text.lower():
        return True
    from urllib.robotparser import RobotFileParser
    rp = RobotFileParser()
    try:
        rp.parse(text.splitlines())
        return bool(rp.can_fetch(agent.split("/")[0], url) and rp.can_fetch("*", url))
    except Exception:  # noqa: BLE001
        return True


@dataclass
class Fetcher:
    """Every request of this module: day cap per source, a gap per host, the
    host's robots.txt (kept a day), bot-check cooling, one log line each.
    `http` is injectable: `(method, url, headers, json_body, timeout) ->
    (status, content_bytes, content_type)`."""
    base: Optional[Path] = None
    http: Optional[Callable] = None
    now_fn: Callable[[], datetime] = _now
    sleep_fn: Callable[[float], None] = time.sleep
    log_requests: bool = True
    _last: dict = field(default_factory=dict)
    _robots: dict = field(default_factory=dict)
    counts: dict = field(default_factory=dict)
    _stamps: dict = field(default_factory=dict)

    # -- files --
    def _p(self, name: str) -> Path:
        return root(self.base) / name

    def day_count(self, source: str) -> int:
        """Requests for `source` in the last 24 h: read from the log once per
        process, then kept in memory (every request of this process is added
        by `_log`), so a long run does not re-read a growing file per request."""
        now = self.now_fn()
        if source not in self._stamps:
            ts: list[datetime] = []
            try:
                for ln in self._p("requests.jsonl").read_text(
                        encoding="utf-8", errors="replace").splitlines()[-60000:]:
                    if f'"source": "{source}"' not in ln:
                        continue
                    try:
                        ts.append(datetime.fromisoformat(json.loads(ln)["t"]))
                    except (ValueError, KeyError, TypeError):
                        continue
            except OSError:
                pass
            self._stamps[source] = ts
        cut = now - timedelta(days=1)
        self._stamps[source] = [t for t in self._stamps[source] if t > cut]
        return len(self._stamps[source])

    def cooling(self) -> dict:
        return _read_json(self._p("cooling.json"), {})

    def cool(self, source: str, why: str) -> None:
        p = self._p("cooling.json")
        p.parent.mkdir(parents=True, exist_ok=True)
        with DG.file_lock(p.with_name(p.name + ".lock")):
            d = _read_json(p, {})
            d[source] = {"until": iso(self.now_fn() + timedelta(
                seconds=float(_cfg("OFFICIAL_COOL_S", 86400.0)))), "why": why[:300]}
            DG.atomic_write_json(p, d)

    def cooling_until(self, source: str) -> Optional[datetime]:
        r = self.cooling().get(source)
        try:
            t = datetime.fromisoformat(r["until"]) if r else None
        except (KeyError, ValueError, TypeError):
            return None
        return t if t and t > self.now_fn() else None

    def _log(self, row: dict) -> None:
        self.counts[row["source"]] = self.counts.get(row["source"], 0) + 1
        if row["source"] in self._stamps:
            try:
                self._stamps[row["source"]].append(datetime.fromisoformat(row["t"]))
            except (ValueError, KeyError, TypeError):
                pass
        if not self.log_requests:
            return
        p = self._p("requests.jsonl")
        p.parent.mkdir(parents=True, exist_ok=True)
        DG.locked_append_line(p, json.dumps(row))

    # -- transport --
    def _http(self, method: str, url: str, headers: dict, body: Any, timeout: float):
        if self.http is not None:
            return self.http(method, url, headers, body, timeout)
        import requests
        if method == "POST":
            r = requests.post(url, headers=headers, json=body, timeout=timeout)
        else:
            r = requests.get(url, headers=headers, timeout=timeout)
        return r.status_code, r.content, r.headers.get("content-type", "")

    def _headers(self, sec: bool) -> dict:
        if sec:
            from backend.services.insider_form4 import _HEADERS
            return dict(_HEADERS)
        return {"User-Agent": UA, "Accept-Encoding": "gzip, deflate"}

    def _pace(self, host: str, gap: float, sec: bool) -> None:
        if sec:
            from backend.services.edgar_events import _RATE_LIMITER
            _RATE_LIMITER.wait()
        last = self._last.get(host)
        if last is not None:
            w = gap - (time.monotonic() - last)
            if w > 0:
                self.sleep_fn(w)
        self._last[host] = time.monotonic()

    def robots_ok(self, source: str, url: str) -> bool:
        """The host's robots.txt (fetched once a day, kept under
        `official/robots/<host>.json`); a missing file allows everything."""
        host = (urlsplit(url).hostname or "").lower()
        rec = self._robots.get(host)
        path = self._p("robots") / f"{host}.json"
        if rec is None:
            rec = _read_json(path, None)
        fresh = False
        try:
            fresh = rec is not None and self.now_fn() - datetime.fromisoformat(
                rec["fetched_utc"]) < timedelta(days=1)
        except (KeyError, ValueError, TypeError):
            fresh = False
        if not fresh:
            sec = bool(SOURCES.get(source, {}).get("sec"))
            u = f"{urlsplit(url).scheme}://{urlsplit(url).netloc}/robots.txt"
            try:
                self._pace(host, float(SOURCES.get(source, {}).get("min_gap_s", 2.0)), sec)
                st, body, _ = self._http("GET", u, self._headers(sec), None, 20)
                text = body.decode("utf-8", "replace") if st == 200 else ""
            except Exception as exc:  # noqa: BLE001 -- unreachable robots = not known
                st, text = f"ERR {type(exc).__name__}", ""
            self._log({"t": iso(self.now_fn()), "source": source, "host": host, "url": u,
                       "status": st, "class": "ROBOTS", "bytes": len(text)})
            rec = {"host": host, "fetched_utc": iso(self.now_fn()), "status": st,
                   "text": text[:200_000]}
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                DG.atomic_write_json(path, rec)
            except OSError:
                pass
        self._robots[host] = rec
        return robots_allows(rec.get("text"), url)

    def get(self, source: str, url: str, *, method: str = "GET", body: Any = None,
            timeout: float = 30.0, headers: Optional[dict] = None) -> tuple[int, bytes, str]:
        """One request for `source`, or `SourceRefused("<CLASS>: ...")`."""
        spec = SOURCES.get(source)
        if spec is None:                # no declared source = no declared cap: refuse
            raise SourceRefused(f"UNKNOWN_SOURCE: {source!r} is not in official_sources.SOURCES")
        from backend.services import browser_policy as BP
        money = BP.url_refusal(url)     # the same money / checkout / mail rule as the browser
        if money:
            raise SourceRefused(money)
        host = (urlsplit(url).hostname or "").lower()
        cu = self.cooling_until(source)
        if cu is not None:
            raise SourceRefused(f"COOLING: {source} until {iso(cu)}")
        cap = int(spec.get("day_cap", 50))
        if self.day_count(source) >= cap:
            raise SourceRefused(f"DAY_CAP: {source} spent {cap} requests in 24 h")
        if not self.robots_ok(source, url):
            self._log({"t": iso(self.now_fn()), "source": source, "host": host, "url": url[:300],
                       "status": None, "class": "ROBOTS_DISALLOWED", "bytes": 0})
            raise SourceRefused(f"ROBOTS_DISALLOWED: {url}")
        sec = bool(spec.get("sec"))
        self._pace(host, float(spec.get("min_gap_s", 2.0)), sec)
        hd = {**self._headers(sec), **(headers or {})}
        t0 = time.monotonic()
        try:
            st, content, ctype = self._http(method, url, hd, body, timeout)
        except Exception as exc:  # noqa: BLE001 -- a network error is a class, not a crash
            self._log({"t": iso(self.now_fn()), "source": source, "host": host, "url": url[:300],
                       "status": None, "class": f"NETWORK:{type(exc).__name__}", "bytes": 0})
            raise SourceRefused(f"NETWORK: {type(exc).__name__}: {str(exc)[:160]}") from exc
        cls = classify_response(int(st), content)
        self._log({"t": iso(self.now_fn()), "source": source, "host": host, "url": url[:300],
                   "status": st, "class": cls, "bytes": len(content or b""),
                   "ms": int((time.monotonic() - t0) * 1000)})
        if cls in ("BOT_CHECK", "RATE_LIMITED"):
            self.cool(source, f"{cls} at {url[:200]} (status {st})")
            raise SourceRefused(f"{cls}: {source} cooled; nothing is done to get around it")
        return int(st), content or b"", ctype or ""


# ──────────────────────────── parsers (PURE) ─────────────────────────────────

_ATOM = "{http://www.w3.org/2005/Atom}"


def parse_edgar_atom(xml_text: str | bytes) -> list[dict]:
    """PURE. EDGAR 'latest filings' Atom -> `[{form, company, cik, role,
    accession, index_url, updated_utc, items}]`."""
    try:
        rootx = ET.fromstring(xml_text if isinstance(xml_text, bytes) else xml_text.encode("utf-8"))
    except ET.ParseError:
        return []
    out = []
    for e in rootx.findall(f"{_ATOM}entry"):
        title = (e.findtext(f"{_ATOM}title") or "").strip()
        cat = e.find(f"{_ATOM}category")
        form = (cat.get("term") if cat is not None else "") or title.split(" - ", 1)[0]
        link = e.find(f"{_ATOM}link")
        href = link.get("href") if link is not None else ""
        m = re.match(r"^(.+?) - (.+) \((\d{10})\) \(([^)]+)\)\s*$", title)
        company = m.group(2).strip() if m else title
        cik = m.group(3).lstrip("0") if m else ""
        role = m.group(4) if m else ""
        summ = unescape(e.findtext(f"{_ATOM}summary") or "")
        acc = re.search(r"AccNo:</b>\s*([\d-]{20})", summ)
        idm = re.search(r"accession-number=([\d-]{20})", e.findtext(f"{_ATOM}id") or "")
        accession = (acc.group(1) if acc else (idm.group(1) if idm else ""))
        upd = e.findtext(f"{_ATOM}updated") or ""
        try:
            up = datetime.fromisoformat(upd.strip()).astimezone(timezone.utc)
        except ValueError:
            up = None
        items = re.findall(r"Item (\d+\.\d+)", summ)
        out.append({"form": form.strip(), "company": company, "cik": cik, "role": role,
                    "accession": accession, "index_url": href, "updated_utc": up,
                    "items": items})
    return out


def parse_index_page(html: str) -> dict:
    """PURE. An EDGAR filing index page -> `{accepted_et, filing_date, xml_docs}`
    (`accepted_et` naive New York time)."""
    out: dict = {"accepted_et": None, "filing_date": None, "xml_docs": []}
    m = re.search(r'Accepted</div>\s*<div class="info">\s*([\d-]{10} [\d:]{8})', html)
    if m:
        out["accepted_et"] = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
    m = re.search(r'Filing Date</div>\s*<div class="info">\s*([\d-]{10})', html)
    if m:
        out["filing_date"] = date.fromisoformat(m.group(1))
    xs = re.findall(r'href="([^"]+\.xml)"', html)
    out["xml_docs"] = [x for x in xs if "xsl" not in x.lower()] or xs
    return out


def _role(p: dict) -> str:
    t = (p.get("officer_title") or "").lower()
    if re.search(r"\b(ceo|chief executive)", t):
        return "CEO"
    if re.search(r"\b(cfo|chief financial)", t):
        return "CFO"
    if p.get("is_officer"):
        return "officer"
    if p.get("is_director"):
        return "director"
    if p.get("is_ten_pct_owner"):
        return "10pct"
    return "other"


def aff10b5_flag(xml: bytes | str) -> Optional[bool]:
    """PURE. The filing-level Rule 10b5-1 checkbox of a Form 4/5 XML
    (`<aff10b5One>`), or None when the filing has none.

    MEASURED 2026-09-30 on live EDGAR XML: the element filers use is
    `aff10b5One`; `ownership_forms._is_10b5_1` looks for `rule10b5-1Checked`
    (not present in any of the documents checked) and a footnote, so it returns
    None ("unknown") for almost every current filing. The box applies to the
    whole filing, so it is used only where the per-line reading is unknown."""
    t = xml.decode("utf-8", "replace") if isinstance(xml, bytes) else (xml or "")
    m = re.search(r"<aff10b5One>\s*([^<\s]+)\s*</aff10b5One>", t)
    if not m:
        return None
    return m.group(1).strip().lower() in ("1", "true", "y", "yes")


def insider_rows(parsed: dict, *, accession: str, public_utc: datetime, basis: str,
                 index_url: str = "", accepted_utc: Optional[datetime] = None,
                 plan_flag: Optional[bool] = None) -> list[dict]:
    """PURE. One `ownership_forms.parse_ownership_form` result -> typed rows,
    one per reported transaction line. `plan_flag` is the filing's
    `aff10b5One` box (`aff10b5_flag`), used when the line's own reading is
    unknown; `rule_10b5_1_basis` says which was used."""
    out = []
    for i, tx in enumerate(parsed.get("transactions") or []):
        line_flag = tx.get("rule_10b5_1")
        flag = line_flag if line_flag is not None else plan_flag
        # since 2026-09-30 the shared parser reads the filing box itself and
        # names its basis (line_element / filing_box / footnote / none)
        pb = str(tx.get("rule_10b5_1_basis") or "line_or_footnote")
        flag_basis = (("aff10b5One_filing_box" if pb == "filing_box" else pb)
                      if line_flag is not None else
                      "aff10b5One_filing_box" if plan_flag is not None else "unknown")
        code = tx.get("code") or ""
        side = ("buy" if code == "P" else "sell" if code == "S" else
                "other_acquire" if tx.get("acquired_disposed") == "A" else
                "other_dispose" if tx.get("acquired_disposed") == "D" else "other")
        out.append({
            "row_id": f"{accession}:{i}", "source": "sec_form4", "accession": accession,
            "form_type": parsed.get("form_type"),
            "public_utc": iso(public_utc), "public_ts_basis": basis,
            "accepted_utc": iso(accepted_utc) if accepted_utc else None,
            "ticker": (parsed.get("ticker") or "").upper() or None,
            "issuer_cik": parsed.get("issuer_cik"), "issuer_name": parsed.get("issuer_name"),
            "owner_name": parsed.get("owner_name"), "owner_cik": parsed.get("owner_cik"),
            "n_owners": parsed.get("n_reporting_owners"),
            "role": _role(parsed), "officer_title": parsed.get("officer_title"),
            "is_officer": parsed.get("is_officer"), "is_director": parsed.get("is_director"),
            "is_ten_pct_owner": parsed.get("is_ten_pct_owner"),
            "code": code, "code_meaning": tx.get("code_meaning"), "side": side,
            "is_discretionary_market_trade": tx.get("is_discretionary_market_trade"),
            "rule_10b5_1": flag, "rule_10b5_1_basis": flag_basis,
            "transaction_date": tx.get("transaction_date"),
            "shares": tx.get("shares"), "price": tx.get("price_per_share"),
            "value_usd": tx.get("value"), "shares_owned_after": tx.get("shares_owned_after"),
            "is_derivative": tx.get("is_derivative"), "security_title": tx.get("security_title"),
            "acquired_disposed": tx.get("acquired_disposed"),
            "ownership_type": tx.get("ownership_type"), "index_url": index_url})
    return out


def parse_house_index(txt: str) -> list[dict]:
    """PURE. The Clerk's `<year>FD.txt` (tab-separated) -> filing dicts."""
    rows = []
    lines = [ln for ln in (txt or "").splitlines() if ln.strip()]
    if not lines:
        return rows
    head = [h.strip() for h in lines[0].split("\t")]
    for ln in lines[1:]:
        parts = [x.strip() for x in ln.split("\t")]
        if len(parts) < len(head):
            parts += [""] * (len(head) - len(parts))
        d = dict(zip(head, parts))
        try:
            fd = datetime.strptime(d.get("FilingDate", ""), "%m/%d/%Y").date()
        except ValueError:
            continue
        name = " ".join(x for x in (d.get("First"), d.get("Last"), d.get("Suffix")) if x)
        rows.append({"member": name, "prefix": d.get("Prefix"), "last": d.get("Last"),
                     "filing_type": d.get("FilingType"), "state_district": d.get("StateDst"),
                     "year": d.get("Year"), "disclosure_date": fd, "doc_id": d.get("DocID")})
    return rows


_PTR_TX = re.compile(
    r"(?:\b(?P<owner>SP|JT|DC)\s+)?(?P<asset>[^\[\]]{3,240}?)\s*\[(?P<atype>[A-Z]{2,3})\]\s*"
    r"(?:F\s*S\s*:\s*\w+\s*)?(?P<tx>P|S\s*\(partial\)|S|E)\s+"
    r"(?P<td>\d{2}/\d{2}/\d{4})\s*(?P<nd>\d{2}/\d{2}/\d{4})\s*"
    r"(?P<amt>\$[\d,]+\s*-\s*\$[\d,]+|Over\s+\$[\d,]+|\$[\d,]+)")
_PTR_HEADER_NOISE = re.compile(
    r"(ID\s+Owner\s+Asset\s+Transaction\s+Type\s+Date\s+Notification\s+Date\s+Amount\s+Cap\.\s+"
    r"Gains\s*>\s*\$200\?)|Filing ID #\d+|Digitally Signed:.*", re.I)


def _money(s: str) -> float | None:
    try:
        return float(s.replace("$", "").replace(",", "").strip())
    except ValueError:
        return None


def parse_ptr_text(text: str) -> list[dict]:
    """PURE. The text of an electronically filed House PTR -> transactions
    `{owner, asset, ticker, asset_type, tx_type, trade_date, notification_date,
    amount_lo, amount_hi}`. A scanned (image) PTR has no text and yields []."""
    flat = " ".join((text or "").split())
    flat = _PTR_HEADER_NOISE.sub(" ", flat)
    out = []
    for m in _PTR_TX.finditer(flat):
        asset = m.group("asset").strip(" :-")
        owner = m.group("owner") or None
        # the text before an asset carries the previous line's tail (its filing
        # status "F S: New" and sub-holding "S O: <account>") or the page header
        # ending "Cap. Gains > $200?": keep what follows them
        if "$200?" in asset:
            asset = asset.split("$200?")[-1]
        asset = re.sub(r"F\s+S\s*:\s*\w+", " ", asset)
        if re.search(r"\bO\s*:", asset):
            asset = re.split(r"\bO\s*:\s*", asset)[-1]
        codes = list(re.finditer(r"\b(SP|JT|DC)\b\s+", asset))
        if codes:
            owner, asset = codes[-1].group(1), asset[codes[-1].end():]
        asset = " ".join(asset.split()).strip(" :-")
        tk = re.search(r"\(([A-Z][A-Z0-9.\-]{0,6})\)", asset)
        amt = m.group("amt")
        if amt.lower().startswith("over"):
            lo, hi = _money(amt.split("$", 1)[1]), None
        elif "-" in amt:
            a, b = amt.split("-", 1)
            lo, hi = _money(a), _money(b)
        else:
            lo = hi = _money(amt)
        try:
            td = datetime.strptime(m.group("td"), "%m/%d/%Y").date()
            nd = datetime.strptime(m.group("nd"), "%m/%d/%Y").date()
        except ValueError:
            continue
        out.append({"owner": owner or "self", "asset": asset[-160:],
                    "ticker": tk.group(1) if tk else None, "asset_type": m.group("atype"),
                    "tx_type": re.sub(r"\s+", " ", m.group("tx")), "trade_date": td,
                    "notification_date": nd, "amount_lo": lo, "amount_hi": hi})
    return out


def _f(x: Any) -> float | None:
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


COT_GROUPS = {
    "tff": {"dealer": ("dealer_positions_long_all", "dealer_positions_short_all"),
            "asset_mgr": ("asset_mgr_positions_long", "asset_mgr_positions_short"),
            "lev_money": ("lev_money_positions_long", "lev_money_positions_short"),
            "other_rept": ("other_rept_positions_long", "other_rept_positions_short"),
            "nonrept": ("nonrept_positions_long_all", "nonrept_positions_short_all")},
    "disagg": {"prod_merc": ("prod_merc_positions_long", "prod_merc_positions_short"),
               "swap": ("swap_positions_long_all", "swap__positions_short_all"),
               "managed_money": ("m_money_positions_long_all", "m_money_positions_short_all"),
               "other_rept": ("other_rept_positions_long", "other_rept_positions_short"),
               "nonrept": ("nonrept_positions_long_all", "nonrept_positions_short_all")},
}
COT_HEADLINE = {"tff": "lev_money", "disagg": "managed_money"}


def _pctile(hist: list[float], x: float) -> float | None:
    """PURE. Share of `hist` at or below `x`; None with under 20 points or a
    history that barely moves (a contract whose group is always flat would
    read 100th percentile every week)."""
    if len(hist) < 20 or len(set(round(h, 6) for h in hist)) < 5:
        return None
    return round(sum(1 for h in hist if h <= x) / len(hist), 4)


def cot_rows(records: list[dict], report: str) -> list[dict]:
    """PURE. Socrata COT records (any order, many contracts) -> typed rows with
    each group's net, net % of open interest and weekly change, and for the
    headline group (leveraged funds / managed money) its percentile and the z
    of its weekly change over the trailing 156 reports of that contract."""
    groups = COT_GROUPS[report]
    by: dict[str, list[dict]] = {}
    for r in records:
        code = str(r.get("cftc_contract_market_code") or "").strip()
        if code:
            by.setdefault(code, []).append(r)
    out = []
    head = COT_HEADLINE[report]
    for code, rs in by.items():
        rs = sorted(rs, key=lambda r: str(r.get("report_date_as_yyyy_mm_dd")))
        hist_net_pct: list[float] = []
        hist_chg: list[float] = []
        prev_net: dict[str, float] = {}
        for r in rs:
            try:
                rd = date.fromisoformat(str(r.get("report_date_as_yyyy_mm_dd"))[:10])
            except ValueError:
                continue
            oi = _f(r.get("open_interest_all")) or 0.0
            g = {}
            for name, (lk, sk) in groups.items():
                lo, sh = _f(r.get(lk)), _f(r.get(sk))
                if lo is None or sh is None:
                    continue
                net = lo - sh
                g[name] = {"long": lo, "short": sh, "net": net,
                           "net_pct_oi": round(100.0 * net / oi, 3) if oi > 0 else None,
                           "chg_net": (net - prev_net[name]) if name in prev_net else None}
                prev_net[name] = net
            hn = g.get(head, {})
            npct, chg = hn.get("net_pct_oi"), hn.get("chg_net")
            pct = _pctile(hist_net_pct[-156:], npct) if npct is not None else None
            z = None
            win = hist_chg[-156:]
            if chg is not None and len(win) >= 20:
                mu = sum(win) / len(win)
                sd = math.sqrt(sum((x - mu) ** 2 for x in win) / (len(win) - 1)) or None
                z = round((chg - mu) / sd, 3) if sd else None
            out.append({"row_id": f"{report}:{code}:{rd.isoformat()}", "source": "cftc_cot",
                        "report": report, "market": str(r.get("market_and_exchange_names") or "")[:120],
                        "commodity": r.get("commodity_name"),
                        "code": code, "report_date": rd.isoformat(),
                        "public_utc": iso(cot_public_utc(rd)),
                        "public_ts_basis": "CFTC_SCHEDULE_FRIDAY_1530ET",
                        "open_interest": oi, "groups": g, "headline_group": head,
                        "headline_net_pct_oi": npct, "headline_pctile_3y": pct,
                        "headline_chg_z": z})
            if npct is not None:
                hist_net_pct.append(npct)
            if chg is not None:
                hist_chg.append(chg)
    return out


def finra_si_rows(csv_text: str, *, now: datetime) -> list[dict]:
    """PURE. FINRA consolidatedShortInterest CSV -> typed rows."""
    out = []
    rd = csv.DictReader(io.StringIO(csv_text or ""))
    for r in rd:
        try:
            sd = date.fromisoformat(str(r.get("settlementDate"))[:10])
        except ValueError:
            continue
        sym = str(r.get("symbolCode") or "").strip().upper()
        if not sym:
            continue
        sched = short_interest_public_utc(sd)
        pub, basis = (sched, "FINRA_SCHEDULE_SETTLEMENT_PLUS_8BD") if now >= sched else \
            (now, "FIRST_SEEN_BEFORE_SCHEDULE")
        dtc = _f(r.get("daysToCoverQuantity"))
        out.append({"row_id": f"si:{sym}:{sd.isoformat()}", "source": "finra_si", "symbol": sym,
                    "ticker": sym, "settlement_date": sd.isoformat(),
                    "public_utc": iso(pub), "public_ts_basis": basis,
                    "short_qty": _f(r.get("currentShortPositionQuantity")),
                    "prev_short_qty": _f(r.get("previousShortPositionQuantity")),
                    "change_pct": _f(r.get("changePercent")),
                    "avg_daily_volume": _f(r.get("averageDailyVolumeQuantity")),
                    "days_to_cover": None if dtc is None or dtc >= 999 else dtc,
                    "market": r.get("marketClassCode"), "issue_name": r.get("issueName")})
    return out


#: agencies whose Federal Register documents are market-relevant (substring match)
FEDREG_RELEVANT = ("treasury", "securities and exchange", "commodity futures", "federal reserve",
                   "commerce", "trade representative", "industry and security", "energy",
                   "food and drug", "environmental protection", "federal communications",
                   "federal trade", "justice", "comptroller of the currency", "federal deposit",
                   "consumer financial", "executive office of the president", "state department",
                   "defense", "transportation", "health and human", "labor", "international trade",
                   "customs", "foreign assets control", "federal energy regulatory",
                   "nuclear regulatory", "agriculture")


def _relevant(agencies: list[str], doc_type: str) -> bool:
    a = " ".join(agencies).lower()
    return doc_type.lower().startswith("presidential") or any(x in a for x in FEDREG_RELEVANT)


def fedreg_rows(results: list[dict], *, pi: bool, now: datetime) -> list[dict]:
    """PURE. Federal Register API results -> policy_events rows. Public
    inspection documents are public at their `filed_at` (before publication)."""
    out = []
    for r in results or []:
        num = str(r.get("document_number") or "")
        if not num:
            continue
        agencies = [str(a) for a in (r.get("agency_names") or
                                      [x.get("name") for x in r.get("agencies") or [] if isinstance(x, dict)])
                    if a]
        doc_type = str(r.get("type") or "")
        if pi:
            try:
                pub = datetime.fromisoformat(str(r.get("filed_at"))).astimezone(timezone.utc)
                basis = "FEDREG_PUBLIC_INSPECTION_FILED_AT"
            except ValueError:
                continue
        else:
            try:
                pub = fedreg_public_utc(date.fromisoformat(str(r.get("publication_date"))[:10]))
                basis = "FEDREG_ISSUE_0600ET"
            except ValueError:
                continue
        out.append({"row_id": f"{'fedreg_pi' if pi else 'fedreg'}:{num}",
                    "source": "fedreg_pi" if pi else "fedreg", "public_utc": iso(pub),
                    "public_ts_basis": basis, "title": str(r.get("title") or "").strip()[:300],
                    "url": r.get("html_url"), "agency": "; ".join(agencies)[:200],
                    "doc_type": doc_type, "significant": r.get("significant"),
                    "publication_date": r.get("publication_date"),
                    "executive_order": r.get("executive_order_number"),
                    "relevant": _relevant(agencies, doc_type),
                    "summary": str(r.get("abstract") or r.get("action") or "")[:600]})
    return out


def rss_rows(xml_text: str | bytes, feed: str, *, now: datetime) -> list[dict]:
    """PURE. An RSS 2.0 / Atom feed -> policy_events rows (pubDate is the
    public time; an undated item is stamped when first seen)."""
    from email.utils import parsedate_to_datetime
    try:
        rx = ET.fromstring(xml_text if isinstance(xml_text, bytes) else xml_text.encode("utf-8"))
    except ET.ParseError:
        return []
    out = []
    items = rx.findall(".//item") or rx.findall(f".//{_ATOM}entry")
    for it in items:
        title = (it.findtext("title") or it.findtext(f"{_ATOM}title") or "").strip()
        link = (it.findtext("link") or "").strip()
        if not link:
            le = it.find(f"{_ATOM}link")
            link = le.get("href", "") if le is not None else ""
        ds = (it.findtext("pubDate") or it.findtext(f"{_ATOM}updated")
              or it.findtext("{http://purl.org/dc/elements/1.1/}date") or "").strip()
        pub, basis = None, "RSS_PUBDATE"
        if ds:
            try:
                pub = parsedate_to_datetime(ds)
            except (TypeError, ValueError):
                try:
                    pub = datetime.fromisoformat(ds.replace("Z", "+00:00"))
                except ValueError:
                    pub = None
        if pub is not None and pub.tzinfo is None:
            pub = pub.replace(tzinfo=timezone.utc)
        if pub is None:
            pub, basis = now, "FIRST_SEEN_UNDATED"
        if pub > now + timedelta(minutes=5):        # a future-dated item is not public yet
            pub, basis = now, "FIRST_SEEN_FUTURE_DATED"
        desc = re.sub(r"<[^>]+>", " ", unescape(it.findtext("description") or
                                                it.findtext(f"{_ATOM}summary") or ""))
        key = link or title
        if not key:
            continue
        out.append({"row_id": f"{feed}:{re.sub(r'[^A-Za-z0-9]+', '', key)[-90:]}",
                    "source": feed, "public_utc": iso(pub.astimezone(timezone.utc)),
                    "public_ts_basis": basis, "title": title[:300], "url": link[:400],
                    "agency": feed.split("_")[0], "doc_type": feed.split("_", 1)[-1],
                    "significant": None, "relevant": True,
                    "summary": " ".join(desc.split())[:600]})
    return out


def hkma_rows(payload: dict, *, now: datetime) -> list[dict]:
    """PURE. HKMA press-release API JSON -> policy_events rows (its date has no
    time: 23:59 Hong Kong time, UTC+8, is the conservative public time)."""
    out = []
    for r in ((payload or {}).get("result") or {}).get("records") or []:
        title = str(r.get("title") or "").strip().lstrip("﻿")
        link = str(r.get("link") or "")
        try:
            d = date.fromisoformat(str(r.get("date"))[:10])
            pub = datetime.combine(d, datetime.min.time()).replace(
                hour=15, minute=59, tzinfo=timezone.utc)
            basis = "HKMA_DATE_2359_HKT"
        except ValueError:
            pub, basis = now, "FIRST_SEEN_UNDATED"
        if pub > now:
            pub, basis = now, "FIRST_SEEN_SAME_DAY"
        if not (title or link):
            continue
        out.append({"row_id": f"hkma_press:{re.sub(r'[^A-Za-z0-9]+', '', link or title)[-90:]}",
                    "source": "hkma_press", "public_utc": iso(pub), "public_ts_basis": basis,
                    "title": title[:300], "url": link[:400], "agency": "hkma",
                    "doc_type": "press", "significant": None, "relevant": True, "summary": ""})
    return out


# ──────────────────────────── ticker mapping ─────────────────────────────────

def cik_ticker_map(fx: Fetcher, *, now: Optional[datetime] = None) -> dict[str, str]:
    """CIK (no leading zeros) -> ticker, from SEC company_tickers.json, cached a
    day under `official/company_tickers.json`."""
    p = root(fx.base) / "company_tickers.json"
    rec = _read_json(p, None)
    now = now or fx.now_fn()
    try:
        if rec and now - datetime.fromisoformat(rec["t"]) < timedelta(days=1):
            return rec["map"]
    except (KeyError, ValueError, TypeError):
        pass
    try:
        st, body, _ = fx.get("sec_tickers", "https://www.sec.gov/files/company_tickers.json")
        d = json.loads(body.decode("utf-8", "replace")) if st == 200 else {}
        m = {}
        for v in d.values():
            c = str(v.get("cik_str") or "").lstrip("0")
            if c and c not in m:
                m[c] = str(v.get("ticker") or "").upper()
        if m:
            DG.atomic_write_json(p, {"t": iso(now), "map": m})
            return m
    except (SourceRefused, ValueError):
        pass
    return (rec or {}).get("map") or {}


# ─────────────────────────────── collectors ──────────────────────────────────

ATOM_URL = ("https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type={t}&company=&dateb="
            "&owner=include&start={s}&count=100&output=atom")


def _state(fx: Fetcher) -> dict:
    return _read_json(root(fx.base) / "state.json", {})


def _save_state(fx: Fetcher, st: dict) -> None:
    p = root(fx.base) / "state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    DG.atomic_write_json(p, st)


def atom_entries(fx: Fetcher, source: str, type_q: str, forms: tuple[str, ...], *,
                 stop_before: Optional[datetime], max_pages: int) -> list[dict]:
    """Pages of the EDGAR latest-filings Atom for `type_q` (a PREFIX match on
    EDGAR's side, so `4` also returns 424B2 / 425: filtered to `forms`), newest
    first, until an entry older than `stop_before` or `max_pages`."""
    got: list[dict] = []
    for page in range(max_pages):
        st, body, _ = fx.get(source, ATOM_URL.format(t=type_q.replace(" ", "%20"), s=page * 100))
        if st != 200:
            break
        es = parse_edgar_atom(body)
        if not es:
            break
        got += [e for e in es if e["form"] in forms]
        oldest = min((e["updated_utc"] for e in es if e["updated_utc"]), default=None)
        if stop_before is not None and oldest is not None and oldest < stop_before:
            break
    return got


def collect_sec_form4(fx: Fetcher, *, max_filings: int = 400, max_pages: int = 20,
                      lookback_h: float = 30.0) -> dict:
    """New Forms 4 / 4/A from the Atom feed: each filing's index page (the
    acceptance time, the XML's name) and its ownership XML, parsed by
    `ownership_forms.parse_ownership_form`, landed in `insider_tx`."""
    from backend.services.ownership_forms import parse_ownership_form
    st = _state(fx)
    done = set(st.get("form4_done") or [])
    now = fx.now_fn()
    last = st.get("form4_last_updated")
    stop = max(now - timedelta(hours=lookback_h),
               datetime.fromisoformat(last) - timedelta(minutes=30)) if last else \
        now - timedelta(hours=lookback_h)
    rec = {"source": "sec_form4", "entries": 0, "filings_new": 0, "parsed": 0, "rows": 0,
           "errors": {}, "refused": None}
    try:
        es = atom_entries(fx, "sec_form4", "4", ("4", "4/A"), stop_before=stop,
                          max_pages=max_pages)
    except SourceRefused as exc:
        rec["refused"] = str(exc)
        return rec
    rec["entries"] = len(es)
    seen_acc: dict[str, dict] = {}
    for e in es:
        if e["accession"] and e["accession"] not in done:
            seen_acc.setdefault(e["accession"], e)
    todo = sorted(seen_acc.values(), key=lambda e: e["updated_utc"] or now)[-max_filings:]
    rec["filings_new"] = len(todo)
    rows: list[dict] = []
    newest = last
    for e in todo:
        try:
            s1, idx, _ = fx.get("sec_form4", e["index_url"])
            if s1 != 200:
                rec["errors"][f"index_{s1}"] = rec["errors"].get(f"index_{s1}", 0) + 1
                continue
            ip = parse_index_page(idx.decode("utf-8", "replace"))
            if not ip["xml_docs"]:
                rec["errors"]["no_xml"] = rec["errors"].get("no_xml", 0) + 1
                done.add(e["accession"])
                continue
            base = e["index_url"].rsplit("/", 1)[0] + "/"
            x = ip["xml_docs"][0]
            xurl = ("https://www.sec.gov" + x) if x.startswith("/") else base + x.rsplit("/", 1)[-1]
            s2, xml, _ = fx.get("sec_form4", xurl)
            if s2 != 200:
                rec["errors"][f"xml_{s2}"] = rec["errors"].get(f"xml_{s2}", 0) + 1
                continue
        except SourceRefused as exc:
            rec["refused"] = str(exc)
            break
        parsed = parse_ownership_form(xml)
        if parsed.get("status") == "PARSE_ERROR":
            rec["errors"]["parse"] = rec["errors"].get("parse", 0) + 1
            done.add(e["accession"])
            continue
        acc_et = ip["accepted_et"]
        if acc_et is not None:
            pub, basis = edgar_public_utc(acc_et, ip["filing_date"])
            acc_utc = et_to_utc(acc_et)
        else:
            pub, basis, acc_utc = e["updated_utc"] or now, "ATOM_UPDATED", e["updated_utc"]
        rows += insider_rows(parsed, accession=e["accession"], public_utc=pub, basis=basis,
                             index_url=e["index_url"], accepted_utc=acc_utc,
                             plan_flag=aff10b5_flag(xml))
        rec["parsed"] += 1
        done.add(e["accession"])
        u = iso(e["updated_utc"]) if e["updated_utc"] else None
        if u and (newest is None or u > newest):
            newest = u
        if len(rows) >= 300:          # land as we go: a long run is readable mid-way
            rec["rows"] += append_rows("insider_tx", rows, fx.base, now)
            rows = []
            st2 = _state(fx)
            st2["form4_done"] = sorted(done | set(st2.get("form4_done") or []))[-40000:]
            _save_state(fx, st2)
    rec["rows"] += append_rows("insider_tx", rows, fx.base, now)
    st = _state(fx)
    done |= set(st.get("form4_done") or [])
    st["form4_done"] = sorted(done | set(st.get("form4_done") or []))[-40000:]
    if newest:
        st["form4_last_updated"] = newest
    _save_state(fx, st)
    return rec


#: 2026-09-30: requests the backfill leaves in sec_form4's rolling 24 h cap for
#: the live 15-minute feed (a backfill that spends the whole cap stops the live
#: Form 4 rows until the window frees)
FORM4_BACKFILL_RESERVE = 3000
#: flush rows and progress every this many filings (a stopped backfill loses at
#: most this much work)
FORM4_BACKFILL_FLUSH_EVERY = 150


def collect_sec_form4_backfill(fx: Fetcher, *, days: int = 7, max_filings: int = 6000,
                               today: Optional[date] = None,
                               reserve: int = FORM4_BACKFILL_RESERVE) -> dict:
    """The last `days` business days of Forms 4 from EDGAR's daily index
    (`sec_daily_index.fetch_index`), each filing's index page (its acceptance
    time) and XML -> `insider_tx`, rows flagged `backfill: true`. The public
    time is still each filing's own acceptance time, so a backfilled row is
    exactly as point-in-time as a live one; only `first_seen_utc` is late."""
    from backend.services.ownership_forms import parse_ownership_form
    from backend.services.sec_daily_index import fetch_index
    today = today or fx.now_fn().date()
    st = _state(fx)
    done = set(st.get("form4_done") or [])
    rec = {"source": "sec_form4", "mode": "backfill", "days": [], "parsed": 0, "rows": 0,
           "errors": {}, "refused": None}
    d, n_days = today, 0
    todo: list[dict] = []
    while n_days < days:
        d -= timedelta(days=1)
        if d.weekday() >= 5:
            continue
        n_days += 1
        idx = fetch_index(d)
        fx._log({"t": iso(fx.now_fn()), "source": "sec_form4", "host": "www.sec.gov",
                 "url": f"daily-index form.{d:%Y%m%d}.idx", "status": None,
                 "class": idx.get("status"), "bytes": 0})
        fil = [f for f in idx.get("filings") or [] if f.get("form_type") in ("4", "4/A")]
        rec["days"].append({"date": d.isoformat(), "status": idx.get("status"), "form4": len(fil)})
        seen = set()
        for f in fil:
            if f["accession"] in done or f["accession"] in seen:
                continue
            seen.add(f["accession"])
            todo.append(f)
    rows: list[dict] = []
    cap = int(SOURCES["sec_form4"].get("day_cap", 14000))
    rec["todo"] = len(todo)
    since_flush = 0
    for f in todo[:max_filings]:
        if fx.day_count("sec_form4") >= cap - int(reserve):
            rec["refused"] = (f"RESERVE: stopped with {int(reserve)} of the {cap} daily "
                              f"sec_form4 requests left for the live feed")
            break
        nodash = f["accession"].replace("-", "")
        iurl = (f"https://www.sec.gov/Archives/edgar/data/{f['cik']}/{nodash}/"
                f"{f['accession']}-index.htm")
        try:
            s1, idxb, _ = fx.get("sec_form4", iurl)
            if s1 != 200:
                rec["errors"][f"index_{s1}"] = rec["errors"].get(f"index_{s1}", 0) + 1
                continue
            ip = parse_index_page(idxb.decode("utf-8", "replace"))
            if not ip["xml_docs"] or ip["accepted_et"] is None:
                rec["errors"]["no_xml_or_time"] = rec["errors"].get("no_xml_or_time", 0) + 1
                done.add(f["accession"])
                continue
            x = ip["xml_docs"][0]
            xurl = ("https://www.sec.gov" + x) if x.startswith("/") else \
                iurl.rsplit("/", 1)[0] + "/" + x.rsplit("/", 1)[-1]
            s2, xml, _ = fx.get("sec_form4", xurl)
            if s2 != 200:
                rec["errors"][f"xml_{s2}"] = rec["errors"].get(f"xml_{s2}", 0) + 1
                continue
        except SourceRefused as exc:
            rec["refused"] = str(exc)
            break
        parsed = parse_ownership_form(xml)
        done.add(f["accession"])
        if parsed.get("status") == "PARSE_ERROR":
            rec["errors"]["parse"] = rec["errors"].get("parse", 0) + 1
            continue
        pub, basis = edgar_public_utc(ip["accepted_et"], ip["filing_date"])
        rs = insider_rows(parsed, accession=f["accession"], public_utc=pub, basis=basis,
                          index_url=iurl, accepted_utc=et_to_utc(ip["accepted_et"]),
                          plan_flag=aff10b5_flag(xml))
        rows += [dict(r, backfill=True) for r in rs]
        rec["parsed"] += 1
        since_flush += 1
        if len(rows) >= 2000 or since_flush >= FORM4_BACKFILL_FLUSH_EVERY:
            since_flush = 0
            rec["rows"] += append_rows("insider_tx", rows, fx.base, fx.now_fn())
            rows = []
            st = _state(fx)
            st["form4_done"] = sorted(done | set(st.get("form4_done") or []))[-40000:]
            _save_state(fx, st)
    rec["rows"] += append_rows("insider_tx", rows, fx.base, fx.now_fn())
    st = _state(fx)
    st["form4_done"] = sorted(done | set(st.get("form4_done") or []))[-40000:]
    _save_state(fx, st)
    return rec


EVENT_FORMS = {
    "sec_8k": ("8-K", ("8-K", "8-K/A")),
    "sec_13dg": ("SC 13", ("SC 13D", "SC 13G", "SC 13D/A", "SC 13G/A")),
    "sec_13f": ("13F-HR", ("13F-HR", "13F-HR/A")),
}
EVENT_FORMS_EXTRA = {"sec_13dg": ("SCHEDULE 13", ("SCHEDULE 13D", "SCHEDULE 13G",
                                                  "SCHEDULE 13D/A", "SCHEDULE 13G/A"))}


def collect_sec_events(fx: Fetcher, source: str, *, max_pages: int = 5,
                       lookback_h: float = 30.0) -> dict:
    """8-K / 13D/G / 13F entries from the Atom feed -> `filing_events` (no
    document fetch: the 8-K items are in the entry; 13F holdings are not
    parsed)."""
    from backend.services.edgar_events import ITEM_TAXONOMY
    now = fx.now_fn()
    rec = {"source": source, "entries": 0, "rows": 0, "refused": None}
    cmap = cik_ticker_map(fx)
    es: list[dict] = []
    for type_q, forms in [EVENT_FORMS[source]] + ([EVENT_FORMS_EXTRA[source]]
                                                  if source in EVENT_FORMS_EXTRA else []):
        try:
            es += atom_entries(fx, source, type_q, forms,
                               stop_before=now - timedelta(hours=lookback_h), max_pages=max_pages)
        except SourceRefused as exc:
            rec["refused"] = str(exc)
    rows = []
    for e in es:
        if not e["accession"] or e["updated_utc"] is None:
            continue
        items = e["items"]
        rows.append({"row_id": f"{e['form']}:{e['accession']}:{e['role']}:{e['cik']}",
                     "source": source, "form_type": e["form"], "accession": e["accession"],
                     "public_utc": iso(e["updated_utc"]), "public_ts_basis": "ATOM_UPDATED_ACCEPTANCE",
                     "cik": e["cik"], "company": e["company"][:160], "role": e["role"],
                     "ticker": cmap.get(e["cik"]), "items": items,
                     "event_types": sorted({ITEM_TAXONOMY[i][0] for i in items if i in ITEM_TAXONOMY}),
                     "index_url": e["index_url"]})
    rec["entries"] = len(es)
    rec["rows"] = append_rows("filing_events", rows, fx.base, now)
    return rec


def collect_house(fx: Fetcher, *, max_pdfs: int = 40, year: Optional[int] = None,
                  pdf_text: Optional[Callable[[bytes], str]] = None) -> dict:
    """The Clerk's annual index -> `politician_filings` (PTRs); the newest PTR
    PDFs not read yet -> their text -> `politician_trades`."""
    now = fx.now_fn()
    year = year or now.year
    rec = {"source": "house_ptr", "filings": 0, "filings_new": 0, "pdfs_read": 0,
           "scanned": 0, "trades": 0, "refused": None}
    try:
        st, body, _ = fx.get("house_ptr", f"https://disclosures-clerk.house.gov/public_disc/"
                                          f"financial-pdfs/{year}FD.zip", timeout=60)
    except SourceRefused as exc:
        rec["refused"] = str(exc)
        return rec
    if st != 200:
        rec["refused"] = f"HTTP_{st}"
        return rec
    try:
        z = zipfile.ZipFile(io.BytesIO(body))
        txt = z.read(f"{year}FD.txt").decode("utf-8", "replace")
    except (zipfile.BadZipFile, KeyError) as exc:
        rec["refused"] = f"BAD_ZIP: {exc}"
        return rec
    ptrs = [f for f in parse_house_index(txt) if f["filing_type"] == "P" and f["doc_id"]]
    rec["filings"] = len(ptrs)
    frows = []
    for f in ptrs:
        pub = disclosure_public_utc(f["disclosure_date"])
        frows.append({"row_id": f"house:{f['doc_id']}", "source": "house_ptr", "chamber": "house",
                      "member": f["member"], "state_district": f["state_district"],
                      "filing_type": "P", "doc_id": f["doc_id"],
                      "disclosure_date": f["disclosure_date"].isoformat(),
                      "public_utc": iso(pub), "public_ts_basis": "DISCLOSURE_DATE_2359ET",
                      "pdf_url": (f"https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/"
                                  f"{year}/{f['doc_id']}.pdf")})
    rec["filings_new"] = append_rows("politician_filings", frows, fx.base, now)
    st_ = _state(fx)
    read = set(st_.get("house_pdfs_read") or [])
    todo = sorted(frows, key=lambda r: (r["disclosure_date"], r["doc_id"]), reverse=True)
    todo = [r for r in todo if r["doc_id"] not in read][:max_pdfs]
    trows = []
    for r in todo:
        try:
            s2, pdf, _ = fx.get("house_ptr", r["pdf_url"], timeout=60)
        except SourceRefused as exc:
            rec["refused"] = str(exc)
            break
        read.add(r["doc_id"])
        if s2 != 200:
            continue
        rec["pdfs_read"] += 1
        try:
            text = (pdf_text or _pdf_text)(pdf)
        except Exception:  # noqa: BLE001 -- an unreadable PDF is a scanned one here
            text = ""
        txs = parse_ptr_text(text)
        if not text.strip() or ("[" not in text and not txs):
            rec["scanned"] += 1
        dd = date.fromisoformat(r["disclosure_date"])
        pub = datetime.fromisoformat(r["public_utc"])
        for i, t in enumerate(txs):
            trows.append({"row_id": f"house:{r['doc_id']}:{i}", "source": "house_ptr",
                          "chamber": "house", "doc_id": r["doc_id"], "member": r["member"],
                          "state_district": r["state_district"], "owner": t["owner"],
                          "asset": t["asset"], "ticker": t["ticker"], "asset_type": t["asset_type"],
                          "tx_type": t["tx_type"], "trade_date": t["trade_date"].isoformat(),
                          "notification_date": t["notification_date"].isoformat(),
                          "disclosure_date": r["disclosure_date"],
                          "lag_days": (dd - t["trade_date"]).days,
                          "amount_lo": t["amount_lo"], "amount_hi": t["amount_hi"],
                          "public_utc": r["public_utc"],
                          "public_ts_basis": "DISCLOSURE_DATE_2359ET",
                          "tradable_from_utc": iso(tradable_from_utc(pub)),
                          "pdf_url": r["pdf_url"]})
    rec["trades"] = append_rows("politician_trades", trows, fx.base, now)
    st_["house_pdfs_read"] = sorted(read)[-5000:]
    _save_state(fx, st_)
    return rec


def _pdf_text(pdf: bytes) -> str:
    from pypdf import PdfReader
    return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(pdf)).pages)


COT_DATASETS = {"tff": "gpe5-46if", "disagg": "72hh-3qpy"}
#: disaggregated contracts kept (substring of the market name): the commodities
#: a macro digest reads; the TFF report is kept whole (it is all financials)
DISAGG_KEEP = ("CRUDE OIL, LIGHT SWEET", "BRENT", "NATURAL GAS (NYME", "GOLD - COMMODITY",
               "SILVER - COMMODITY", "COPPER", "CORN - CHICAGO", "SOYBEANS - CHICAGO",
               "WHEAT-SRW", "GASOLINE", "NY HARBOR ULSD", "PLATINUM", "COFFEE", "SUGAR NO. 11",
               "LIVE CATTLE", "LEAN HOGS", "COTTON NO. 2")


def collect_cot(fx: Fetcher, *, weeks: int = 170) -> dict:
    """TFF (all financial futures) and disaggregated (the main commodities)
    over the last `weeks` reports -> `positioning_cot` (history rows are
    public long ago; their public time is still their own release)."""
    now = fx.now_fn()
    since = (now - timedelta(weeks=weeks)).date().isoformat()
    rec = {"source": "cftc_cot", "records": {}, "rows": 0, "refused": None}
    rows = []
    for report, ds in COT_DATASETS.items():
        grp = COT_GROUPS[report]
        cols = ["market_and_exchange_names", "report_date_as_yyyy_mm_dd",
                "cftc_contract_market_code", "open_interest_all",
                "commodity_name"] + \
            [c for pair in grp.values() for c in pair]
        where = f"report_date_as_yyyy_mm_dd >= '{since}'"
        if report == "disagg":
            where += " AND (" + " OR ".join(
                f"market_and_exchange_names like '%{k}%'" for k in DISAGG_KEEP) + ")"
        from urllib.parse import quote
        url = (f"https://publicreporting.cftc.gov/resource/{ds}.json?$select={','.join(cols)}"
               f"&$where={quote(where)}&$limit=50000")
        try:
            st, body, _ = fx.get("cftc_cot", url, timeout=90)
        except SourceRefused as exc:
            rec["refused"] = str(exc)
            continue
        if st != 200:
            rec["refused"] = f"HTTP_{st}"
            continue
        try:
            recs = json.loads(body.decode("utf-8", "replace"))
        except ValueError:
            continue
        rec["records"][report] = len(recs)
        rows += cot_rows(recs, report)
    rec["rows"] = append_rows("positioning_cot", rows, fx.base, now)
    return rec


def si_settlement_candidates(today: date, n: int = 6) -> list[date]:
    """PURE. FINRA settlement dates (the 15th and the month's last business
    day, moved back to a business day), newest first."""
    out = []
    y, m = today.year, today.month
    for _ in range(n):
        last = (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1))
        mid = date(y, m, 15)
        for d in (last, mid):
            while d.weekday() >= 5:
                d -= timedelta(days=1)
            if d <= today:
                out.append(d)
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return sorted(set(out), reverse=True)[:n]


def collect_finra_si(fx: Fetcher, *, dates_back: int = 2, page: int = 5000,
                     max_pages: int = 8) -> dict:
    """The newest `dates_back` published settlement dates of FINRA's
    consolidated short interest -> `short_interest`."""
    now = fx.now_fn()
    rec = {"source": "finra_si", "settlements": [], "rows": 0, "refused": None}
    url = "https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest"
    st_ = _state(fx)
    have = set(st_.get("si_done") or [])
    got_dates = 0
    for sd in si_settlement_candidates(now.date(), 8):
        if got_dates >= dates_back:
            break
        if sd.isoformat() in have:
            got_dates += 1
            continue
        rows_d: list[dict] = []
        for pg in range(max_pages):
            body = {"limit": page, "offset": pg * page,
                    "compareFilters": [{"compareType": "EQUAL", "fieldName": "settlementDate",
                                        "fieldValue": sd.isoformat()}]}
            try:
                s, b, _ = fx.get("finra_si", url, method="POST", body=body, timeout=90,
                                 headers={"Accept": "text/plain", "Content-Type": "application/json"})
            except SourceRefused as exc:
                rec["refused"] = str(exc)
                break
            if s not in (200, 204):
                break
            rs = finra_si_rows(b.decode("utf-8", "replace"), now=now)
            rows_d += rs
            if len(rs) < page:
                break
        if rows_d:
            rec["rows"] += append_rows("short_interest", rows_d, fx.base, now)
            rec["settlements"].append({"date": sd.isoformat(), "rows": len(rows_d)})
            have.add(sd.isoformat())
            got_dates += 1
        if rec["refused"]:
            break
    st_["si_done"] = sorted(have)[-60:]
    _save_state(fx, st_)
    return rec


def collect_finra_sv(fx: Fetcher, *, days_back: int = 6) -> dict:
    """The existing FINRA short-sale-volume store, brought up to date (its own
    fetcher; one CDN file per trading day). Counted against `finra_sv`."""
    rec = {"source": "finra_sv", "refused": None}
    if fx.cooling_until("finra_sv") or fx.day_count("finra_sv") >= SOURCES["finra_sv"]["day_cap"]:
        rec["refused"] = "COOLING_OR_DAY_CAP"
        return rec
    try:
        from backend.services import finra_short_volume as FSV
        today = fx.now_fn().date()
        r = FSV.pull(start=today - timedelta(days=days_back), end=today)
        rec["result"] = {k: v for k, v in (r or {}).items() if not isinstance(v, (list, dict))} \
            if isinstance(r, dict) else str(r)[:300]
    except Exception as exc:  # noqa: BLE001 -- recorded
        rec["refused"] = f"ERROR: {type(exc).__name__}: {str(exc)[:200]}"
    fx._log({"t": iso(fx.now_fn()), "source": "finra_sv", "host": "cdn.finra.org",
             "url": "finra_short_volume.pull", "status": None,
             "class": "DELEGATED" if not rec["refused"] else "ERROR", "bytes": 0})
    return rec


FEDREG_FIELDS = ("title", "type", "abstract", "action", "document_number", "html_url",
                 "publication_date", "agency_names", "significant", "executive_order_number")


def collect_fedreg(fx: Fetcher, *, days_back: int = 2) -> dict:
    """Documents published in the last `days_back` days, and today's public
    inspection list (documents public BEFORE they are published)."""
    now = fx.now_fn()
    rec = {"source": "fedreg", "published": 0, "public_inspection": 0, "rows": 0, "refused": None}
    rows = []
    fl = "".join(f"&fields[]={f}" for f in FEDREG_FIELDS)
    since = (now - timedelta(days=days_back)).date().isoformat()
    for pg in range(1, 6):
        url = (f"https://www.federalregister.gov/api/v1/documents.json?per_page=200&page={pg}"
               f"&order=newest&conditions[publication_date][gte]={since}{fl}")
        try:
            st, body, _ = fx.get("fedreg", url, timeout=60)
        except SourceRefused as exc:
            rec["refused"] = str(exc)
            break
        if st != 200:
            break
        d = json.loads(body.decode("utf-8", "replace"))
        rs = fedreg_rows(d.get("results") or [], pi=False, now=now)
        rows += rs
        rec["published"] += len(rs)
        if not d.get("next_page_url"):
            break
    try:
        st, body, _ = fx.get("fedreg", "https://www.federalregister.gov/api/v1/"
                                       "public-inspection-documents/current.json", timeout=60)
        if st == 200:
            d = json.loads(body.decode("utf-8", "replace"))
            rs = fedreg_rows(d.get("results") or [], pi=True, now=now)
            rows += rs
            rec["public_inspection"] = len(rs)
    except SourceRefused as exc:
        rec["refused"] = str(exc)
    rec["rows"] = append_rows("policy_events", rows, fx.base, now)
    return rec


_ARTICLE_DIV = re.compile(r'<div[^>]+id="(?:article|content|main-content)"[^>]*>', re.I)


def html_to_text(html: str | bytes) -> str:
    """PURE. The readable text of a release page: from the `id="article"` (or
    content) block when the page has one, else the body; scripts, styles, nav
    and tags removed, entities decoded, whitespace collapsed by paragraph."""
    t = html.decode("utf-8", "replace") if isinstance(html, bytes) else (html or "")
    m = _ARTICLE_DIV.search(t)
    if m:
        t = t[m.start():]
        end = re.search(r'<div[^>]+id="(?:footer|lastUpdate|page-footer)"', t, re.I)
        if end:
            t = t[:end.start()]
    else:
        b = re.search(r"<body[^>]*>", t, re.I)
        t = t[b.end():] if b else t
    t = re.sub(r"(?s)<!--.*?-->", " ", t)
    t = re.sub(r"(?is)<(script|style|noscript|nav|header|footer)[^>]*>.*?</\1>", " ", t)
    t = re.sub(r"(?i)<br\s*/?>|</p>|</h[1-6]>|</li>", "\n", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = unescape(t)
    paras = [" ".join(x.split()) for x in t.split("\n")]
    return "\n".join(x for x in paras if x)


def texts_due(source: str, events: list[dict], have: set[str], now: datetime) -> list[dict]:
    """PURE. The policy_events rows of `source` whose text is not fetched yet:
    on the source's URL prefix, public within `max_age_days`, newest first, at
    most `max_per_run`."""
    spec = TEXT_SOURCES.get(source)
    if not spec:
        return []
    feeds = {f for f, _ in RSS_FEEDS.get(source, [])}
    cut = now - timedelta(days=float(spec["max_age_days"]))
    out = []
    for r in events:
        if r.get("source") not in feeds or r.get("row_id") in have:
            continue
        if not str(r.get("url") or "").startswith(spec["url_prefix"]):
            continue
        try:
            if datetime.fromisoformat(str(r.get("public_utc"))) < cut:
                continue
        except (TypeError, ValueError):
            continue
        out.append(r)
    out.sort(key=lambda r: str(r.get("public_utc")), reverse=True)
    return out[:int(spec["max_per_run"])]


def collect_texts(fx: Fetcher, source: str) -> dict:
    """Fetch the full text of `source`'s newest feed items (see TEXT_SOURCES)."""
    now = fx.now_fn()
    rec = {"due": 0, "fetched": 0, "rows": 0, "refused": None}
    spec = TEXT_SOURCES.get(source)
    if not spec:
        return rec
    have = {str(r.get("row_id")) for r in read_table("policy_texts", fx.base)}
    due = texts_due(source, read_table("policy_events", fx.base), have, now)
    rec["due"] = len(due)
    rows = []
    for r in due:
        try:
            st, body, _ = fx.get(source, r["url"], timeout=45)
        except SourceRefused as exc:
            rec["refused"] = str(exc)[:200]
            if str(exc).startswith(("DAY_CAP", "COOLING", "ROBOTS")):
                break
            continue
        rec["fetched"] += 1
        txt = html_to_text(body) if st == 200 else ""
        mx = int(spec["max_chars"])
        rows.append({"row_id": r["row_id"], "source": source, "url": r["url"],
                     "title": r.get("title"), "public_utc": r.get("public_utc"),
                     "public_ts_basis": r.get("public_ts_basis"), "text": txt[:mx],
                     "chars": len(txt), "truncated": len(txt) > mx,
                     "status": ("TEXT" if txt else "EMPTY") if st == 200 else f"HTTP_{st}"})
    rec["rows"] = append_rows("policy_texts", rows, fx.base, now)
    return rec


def collect_rss(fx: Fetcher, source: str) -> dict:
    now = fx.now_fn()
    rec = {"source": source, "items": 0, "rows": 0, "refused": None}
    rows = []
    for feed, url in RSS_FEEDS[source]:
        try:
            st, body, _ = fx.get(source, url, timeout=45)
        except SourceRefused as exc:
            rec["refused"] = str(exc)
            continue
        if st == 200:
            rs = rss_rows(body, feed, now=now)
            rec["items"] += len(rs)
            rows += rs
    rec["rows"] = append_rows("policy_events", rows, fx.base, now)
    if source in TEXT_SOURCES:            # 2026-09-30: the items' full text, by HTTP
        try:
            rec["texts"] = collect_texts(fx, source)
        except Exception as exc:  # noqa: BLE001 -- the feed rows are already written
            rec["texts"] = {"error": f"{type(exc).__name__}: {exc}"[:200]}
    return rec


#: 2026-09-30: api.hkma.gov.hk timed out / answered 502 on every request for a
#: day while www.hkma.gov.hk answered. The API is tried with a short backoff;
#: when it stays down, the same releases are read from HKMA's own RSS on the
#: main site, and the outage is recorded (never retried in a loop).
HKMA_API_URL = "https://api.hkma.gov.hk/public/press-releases?lang=en&pagesize=20"
HKMA_RSS = [("hkma_press", "https://www.hkma.gov.hk/eng/other-information/rss/rss_press-release.xml"),
            ("hkma_speech", "https://www.hkma.gov.hk/eng/other-information/rss/rss_speeches.xml")]
HKMA_RETRY_BACKOFF_S = (10.0, 30.0)


def collect_hkma(fx: Fetcher, *, sleep_fn: Callable[[float], None] = time.sleep,
                 backoff_s: tuple[float, ...] = HKMA_RETRY_BACKOFF_S) -> dict:
    now = fx.now_fn()
    rec = {"source": "hkma_api", "items": 0, "rows": 0, "refused": None, "attempts": 0,
           "via": None, "api_errors": []}
    rows: list[dict] = []
    for k in range(len(backoff_s) + 1):
        rec["attempts"] += 1
        try:
            st, body, _ = fx.get("hkma_api", HKMA_API_URL, timeout=30)
        except SourceRefused as exc:
            msg = str(exc)
            rec["api_errors"].append(msg[:120])
            if not msg.startswith("NETWORK"):          # a cap, a cool-down, robots: stop
                rec["refused"] = msg
                break
            if k < len(backoff_s):
                sleep_fn(backoff_s[k])
            continue
        if st == 200:
            try:
                rows = hkma_rows(json.loads(body.decode("utf-8-sig", "replace")), now=now)
                rec["via"] = "api"
            except ValueError as exc:
                rec["api_errors"].append(f"JSON: {exc}"[:120])
            break
        rec["api_errors"].append(f"HTTP_{st}")
        if st < 500:
            break
        if k < len(backoff_s):
            sleep_fn(backoff_s[k])
    if rec["via"] is None and not (rec["refused"] or "").startswith(("DAY_CAP", "COOLING")):
        for feed, url in HKMA_RSS:                    # the same releases, main-site RSS
            try:
                st, body, _ = fx.get("hkma_api", url, timeout=45)
            except SourceRefused as exc:
                rec["api_errors"].append(f"rss: {exc}"[:120])
                continue
            if st == 200:
                rows += [dict(r, agency="hkma") for r in rss_rows(body, feed, now=now)]
                rec["via"] = "rss_fallback"
    st8 = _state(fx)
    if rec["via"] == "api":
        st8.pop("hkma_api_down_since", None)
    elif rec["api_errors"]:
        st8.setdefault("hkma_api_down_since", iso(now))
    rec["api_down_since"] = st8.get("hkma_api_down_since")
    _save_state(fx, st8)
    rec["items"] = len(rows)
    rec["rows"] = append_rows("policy_events", rows, fx.base, now)
    return rec


COLLECTORS: dict[str, Callable[[Fetcher], dict]] = {
    "sec_form4": collect_sec_form4,
    "sec_8k": lambda fx: collect_sec_events(fx, "sec_8k"),
    "sec_13dg": lambda fx: collect_sec_events(fx, "sec_13dg"),
    "sec_13f": lambda fx: collect_sec_events(fx, "sec_13f"),
    "house_ptr": collect_house,
    "cftc_cot": collect_cot,
    "finra_si": collect_finra_si,
    "finra_sv": collect_finra_sv,
    "fedreg": collect_fedreg,
    "fed_rss": lambda fx: collect_rss(fx, "fed_rss"),
    "ecb_rss": lambda fx: collect_rss(fx, "ecb_rss"),
    "boj_rss": lambda fx: collect_rss(fx, "boj_rss"),
    "boe_rss": lambda fx: collect_rss(fx, "boe_rss"),
    "whitehouse_rss": lambda fx: collect_rss(fx, "whitehouse_rss"),
    "treasury_rss": lambda fx: collect_rss(fx, "treasury_rss"),
    "hkma_api": collect_hkma,
}


def due_sources(last_run: dict[str, str], now: datetime) -> list[str]:
    """PURE. Sources whose `every_s` has passed since their last run."""
    out = []
    for s in COLLECTORS:
        t = last_run.get(s)
        try:
            age = (now - datetime.fromisoformat(t)).total_seconds() if t else None
        except ValueError:
            age = None
        if age is None or age >= float(SOURCES[s]["every_s"]):
            out.append(s)
    return out


def run(sources: Optional[list[str]] = None, *, due: bool = False, fx: Optional[Fetcher] = None,
        printer: Callable[[str], None] = print) -> dict:
    """Run the given (or due, or all) collectors; one receipt."""
    fx = fx or Fetcher()
    now = fx.now_fn()
    st = _state(fx)
    last = dict(st.get("last_run") or {})
    names = sources or (due_sources(last, now) if due else list(COLLECTORS))
    out = {"t": iso(now), "sources": {}, "refused_sources": REFUSED_SOURCES}
    for s in names:
        t0 = time.monotonic()
        try:
            r = COLLECTORS[s](fx)
        except Exception as exc:  # noqa: BLE001 -- one source never takes the run down
            r = {"source": s, "error": f"{type(exc).__name__}: {str(exc)[:300]}"}
        r["seconds"] = round(time.monotonic() - t0, 1)
        out["sources"][s] = r
        printer(f"{s}: {json.dumps({k: v for k, v in r.items() if k != 'source'}, default=str)[:400]}")
        st = _state(fx)
        st.setdefault("last_run", {})[s] = iso(fx.now_fn())
        _save_state(fx, st)
    out["requests_this_run"] = dict(fx.counts)
    out["tables"] = table_counts(fx.base)
    age = panel_age_s(fx.base)
    if age is None or age >= float(_cfg("OFFICIAL_PANEL_EVERY_S", 3600)):
        try:                              # 2026-09-30: the joinable daily panel
            pr = build_daily_panel(fx.base, now=fx.now_fn())
            out["panel"] = {k: pr[k] for k in ("rows", "rows_by_block", "path") if k in pr}
        except Exception as exc:  # noqa: BLE001 -- the tables are already written
            out["panel"] = {"error": f"{type(exc).__name__}: {exc}"[:300]}
        printer(f"panel: {json.dumps(out['panel'], default=str)[:300]}")
    rp = root(fx.base) / "receipts" / f"run_{now.strftime('%Y%m%dT%H%M%SZ')}.json"
    rp.parent.mkdir(parents=True, exist_ok=True)
    DG.atomic_write_json(rp, out)
    out["receipt"] = str(rp)
    return out


# ───────────────── the joinable DAILY PANEL (2026-09-30) ──────────────────────
#
# One parquet keyed by (ticker, public_date) for the other agents: insider net
# buying, politician trades by disclosure date, short interest level and change,
# and futures positioning extremes mapped onto the liquid proxies the digest
# grades against (`config.WORLD_DIGEST_SUBJECT_PROXIES`). `public_date` is the
# New York calendar date of each row's own public time; `tradable_date` is the
# first session a trader could act in (after 16:00 ET or on a weekend -> the next
# business day). Holidays are not modelled: a consumer joining to bars takes the
# first bar on or after `tradable_date`.

PANEL_NAME = "official_daily_panel.parquet"

#: CFTC contract code -> (subject in WORLD_DIGEST_SUBJECT_PROXIES, extra sign).
#: The extra sign turns the contract's net into the SUBJECT's direction: the
#: euro and the yen are the dollar's mirror (-1). Codes with no subject fall
#: back to digest_sections.COT_PROXIES (SPY, QQQ).
COT_SUBJECTS: dict[str, tuple[str, int]] = {
    "239742": ("sector:small_caps", 1),
    "020601": ("macro:bonds", 1), "020604": ("macro:bonds", 1),
    "043602": ("macro:bonds", 1), "043607": ("macro:bonds", 1),
    "088691": ("macro:gold", 1), "084691": ("macro:silver", 1),
    "067651": ("macro:crude_oil", 1), "067411": ("macro:crude_oil", 1),
    "06765T": ("macro:crude_oil", 1), "111659": ("macro:oil", 1),
    "098662": ("macro:dollar", 1), "099741": ("macro:dollar", -1), "097741": ("macro:dollar", -1),
    "133741": ("sector:crypto", 1), "244042": ("macro:emerging", 1),
    "085692": ("sector:materials_mining", 1),
}
COT_PANEL_EXTREME = 0.05

PANEL_SCHEMA: dict[str, str] = {
    "ticker": "issuer symbol (insiders), asset ticker (House), FINRA symbol (short "
              "interest), or the proxy ETF (futures positioning)",
    "public_date": "New York date of the rows' public time (acceptance / disclosure / "
                   "FINRA schedule / CFTC release). JOIN KEY with ticker",
    "tradable_date": "first session one could act in (max over the rows of the day)",
    "ins_n_insiders_buy": "distinct officers/directors/other (not 10% owners) with an "
                          "open-market purchase (code P), non-derivative",
    "ins_n_insiders_sell": "the same for open-market sales (code S)",
    "ins_buy_usd": "", "ins_sell_usd": "", "ins_net_usd": "buy - sell (insiders, not 10% owners)",
    "ins_net_usd_ex_plan": "net excluding lines flagged Rule 10b5-1 True",
    "ins_officer_buy": "any officer among the buyers", "ins_officer_sell": "",
    "ins_n_plan_lines": "lines flagged 10b5-1 True", "ins_n_plan_unknown": "lines with no reading",
    "ins_10b5_1_basis": "where the flag came from, '|'-joined: aff10b5One_filing_box / "
                        "line_element / footnote / unknown",
    "ins_ten_pct_net_usd": "net of 10% owners (kept apart)",
    "ins_n_lines": "P/S lines of the day",
    "pol_n_members_buy": "House members (or spouse/joint) with a purchase disclosed that day",
    "pol_n_members_sell": "", "pol_buy_mid_usd": "sum of range mid-points",
    "pol_sell_mid_usd": "", "pol_n_trades": "", "pol_median_lag_days": "disclosure - trade",
    "pol_members": "up to 5 names",
    "si_settlement_date": "FINRA settlement date (NOT the public date)",
    "si_short_qty": "", "si_prev_short_qty": "", "si_change_pct": "",
    "si_days_to_cover": "", "si_avg_daily_volume": "",
    "cot_subject": "the WORLD_DIGEST_SUBJECT_PROXIES subject the contract maps to",
    "cot_markets": "contracts mapped to this proxy that day ('; '-joined)",
    "cot_n_markets": "", "cot_pctile_3y": "the most extreme headline-group net % OI "
                                          "percentile over 156 weeks, turned into the PROXY's "
                                          "direction (1 = most long the proxy)",
    "cot_net_pct_oi": "", "cot_chg_z": "z of the weekly change (proxy direction)",
    "cot_extreme": "proxy_crowded_long / proxy_crowded_short / '' (5% tails)",
    "cot_proxy_basis": "subject:<key> or code_map (digest_sections.COT_PROXIES)",
}


def ny_date(ts: str) -> Optional[date]:
    try:
        return datetime.fromisoformat(str(ts)).astimezone(ET_TZ).date()
    except (TypeError, ValueError):
        return None


def tradable_date(ts: str) -> Optional[date]:
    """PURE. The first session one could act in after public time `ts`: the
    same New York date before 16:00 ET on a weekday, else the next business day."""
    try:
        t = datetime.fromisoformat(str(ts)).astimezone(ET_TZ)
    except (TypeError, ValueError):
        return None
    d = t.date()
    if d.weekday() >= 5 or t.hour >= 16:
        return next_business_day(d)
    return d


def _num_or_none(x: Any) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def panel_insiders(rows: list[dict]) -> dict[tuple, dict]:
    """PURE. insider_tx rows -> {(ticker, public_date): columns}."""
    out: dict[tuple, dict] = {}
    for r in rows:
        if r.get("code") not in ("P", "S") or r.get("is_derivative"):
            continue
        tk = str(r.get("ticker") or "").upper().strip()
        d = ny_date(r.get("public_utc"))
        if not tk or d is None:
            continue
        v = _num_or_none(r.get("value_usd")) or 0.0
        buy = r.get("code") == "P"
        c = out.setdefault((tk, d), {"_buyers": set(), "_sellers": set(), "ins_buy_usd": 0.0,
                                     "ins_sell_usd": 0.0, "ins_net_usd_ex_plan": 0.0,
                                     "ins_officer_buy": False, "ins_officer_sell": False,
                                     "ins_n_plan_lines": 0, "ins_n_plan_unknown": 0,
                                     "_basis": set(), "ins_ten_pct_net_usd": 0.0,
                                     "ins_n_lines": 0, "_trad": []})
        c["ins_n_lines"] += 1
        c["_trad"].append(tradable_date(r.get("public_utc")))
        c["_basis"].add(str(r.get("rule_10b5_1_basis") or "unknown"))
        plan = r.get("rule_10b5_1")
        if plan is True:
            c["ins_n_plan_lines"] += 1
        elif plan is None:
            c["ins_n_plan_unknown"] += 1
        if r.get("role") == "10pct":
            c["ins_ten_pct_net_usd"] += v if buy else -v
            continue
        who = str(r.get("owner_cik") or r.get("owner_name") or "?")
        if buy:
            c["_buyers"].add(who)
            c["ins_buy_usd"] += v
            c["ins_officer_buy"] |= bool(r.get("is_officer"))
        else:
            c["_sellers"].add(who)
            c["ins_sell_usd"] += v
            c["ins_officer_sell"] |= bool(r.get("is_officer"))
        if plan is not True:
            c["ins_net_usd_ex_plan"] += v if buy else -v
    for c in out.values():
        c["ins_n_insiders_buy"] = len(c.pop("_buyers"))
        c["ins_n_insiders_sell"] = len(c.pop("_sellers"))
        c["ins_net_usd"] = c["ins_buy_usd"] - c["ins_sell_usd"]
        c["ins_10b5_1_basis"] = "|".join(sorted(c.pop("_basis")))
        tr = [x for x in c.pop("_trad") if x]
        c["tradable_date"] = max(tr) if tr else None
    return out


def panel_politicians(rows: list[dict]) -> dict[tuple, dict]:
    """PURE. politician_trades rows -> {(ticker, public_date): columns}."""
    out: dict[tuple, dict] = {}
    for r in rows:
        tk = str(r.get("ticker") or "").upper().strip()
        d = ny_date(r.get("public_utc"))
        if not tk or d is None:
            continue
        tx = str(r.get("tx_type") or "").upper()
        side = "buy" if tx.startswith("P") else "sell" if tx.startswith("S") else None
        if side is None:
            continue
        lo, hi = _num_or_none(r.get("amount_lo")), _num_or_none(r.get("amount_hi"))
        mid = ((lo or 0.0) + (hi if hi is not None else (lo or 0.0))) / 2.0
        c = out.setdefault((tk, d), {"_b": set(), "_s": set(), "pol_buy_mid_usd": 0.0,
                                     "pol_sell_mid_usd": 0.0, "pol_n_trades": 0, "_lags": [],
                                     "_names": [], "_trad": []})
        who = str(r.get("member") or "?")
        c["_b" if side == "buy" else "_s"].add(who)
        c["pol_buy_mid_usd" if side == "buy" else "pol_sell_mid_usd"] += mid
        c["pol_n_trades"] += 1
        lag = _num_or_none(r.get("lag_days"))
        if lag is not None:
            c["_lags"].append(lag)
        if who not in c["_names"]:
            c["_names"].append(who)
        try:
            c["_trad"].append(datetime.fromisoformat(str(r.get("tradable_from_utc")))
                              .astimezone(ET_TZ).date())
        except (TypeError, ValueError):
            c["_trad"].append(tradable_date(r.get("public_utc")))
    for c in out.values():
        c["pol_n_members_buy"] = len(c.pop("_b"))
        c["pol_n_members_sell"] = len(c.pop("_s"))
        lags = sorted(c.pop("_lags"))
        c["pol_median_lag_days"] = (lags[len(lags) // 2] if len(lags) % 2 else
                                    (lags[len(lags) // 2 - 1] + lags[len(lags) // 2]) / 2) \
            if lags else None
        c["pol_members"] = "; ".join(c.pop("_names")[:5])
        tr = [x for x in c.pop("_trad") if x]
        c["tradable_date"] = max(tr) if tr else None
    return out


def panel_short_interest(rows: list[dict]) -> dict[tuple, dict]:
    """PURE. short_interest rows -> {(symbol, public_date): columns} (one
    settlement per symbol and public date; the latest settlement wins)."""
    out: dict[tuple, dict] = {}
    for r in rows:
        tk = str(r.get("symbol") or r.get("ticker") or "").upper().strip()
        d = ny_date(r.get("public_utc"))
        if not tk or d is None:
            continue
        cur = out.get((tk, d))
        if cur and str(cur["si_settlement_date"]) >= str(r.get("settlement_date")):
            continue
        out[(tk, d)] = {"si_settlement_date": r.get("settlement_date"),
                        "si_short_qty": _num_or_none(r.get("short_qty")),
                        "si_prev_short_qty": _num_or_none(r.get("prev_short_qty")),
                        "si_change_pct": _num_or_none(r.get("change_pct")),
                        "si_days_to_cover": _num_or_none(r.get("days_to_cover")),
                        "si_avg_daily_volume": _num_or_none(r.get("avg_daily_volume")),
                        "tradable_date": tradable_date(r.get("public_utc"))}
    return out


def cot_proxy(code: str) -> tuple[Optional[str], int, Optional[str], str]:
    """(proxy ticker, sign into the proxy's direction, subject, basis) for a
    CFTC contract code, or (None, 0, None, '')."""
    from backend import config as _c
    subj = COT_SUBJECTS.get(str(code))
    if subj:
        px = dict(getattr(_c, "WORLD_DIGEST_SUBJECT_PROXIES", {}) or {}).get(subj[0])
        if px:
            return px[0], int(px[1]) * int(subj[1]), subj[0], f"subject:{subj[0]}"
    try:
        from backend.services import digest_sections as DS
        tk, sg = DS.COT_PROXIES.get(str(code), (None, 0))
    except Exception:  # noqa: BLE001
        tk, sg = None, 0
    return (tk, int(sg), None, "code_map") if tk else (None, 0, None, "")


def panel_positioning(rows: list[dict]) -> dict[tuple, dict]:
    """PURE. positioning_cot rows of MAPPED contracts -> {(proxy, public_date):
    columns}; per proxy and day the most extreme contract (in the proxy's
    direction) is reported, with every mapped contract listed."""
    out: dict[tuple, dict] = {}
    for r in rows:
        tk, sg, subj, basis = cot_proxy(str(r.get("code") or ""))
        d = ny_date(r.get("public_utc"))
        p = _num_or_none(r.get("headline_pctile_3y"))
        if not tk or d is None or p is None:
            continue
        pp = p if sg > 0 else 1.0 - p
        z = _num_or_none(r.get("headline_chg_z"))
        net = _num_or_none(r.get("headline_net_pct_oi"))
        c = out.setdefault((tk, d), {"_m": [], "cot_pctile_3y": None, "tradable_date": None})
        c["_m"].append(str(r.get("market") or r.get("code"))[:40])
        cur = c["cot_pctile_3y"]
        if cur is None or abs(pp - 0.5) > abs(cur - 0.5):
            c.update({"cot_pctile_3y": round(pp, 4), "cot_subject": subj,
                      "cot_net_pct_oi": None if net is None else net * sg,
                      "cot_chg_z": None if z is None else z * sg, "cot_proxy_basis": basis,
                      "tradable_date": tradable_date(r.get("public_utc"))})
    for c in out.values():
        ms = c.pop("_m")
        c["cot_markets"] = "; ".join(dict.fromkeys(ms))
        c["cot_n_markets"] = len(set(ms))
        p = c["cot_pctile_3y"]
        c["cot_extreme"] = ("proxy_crowded_long" if p >= 1 - COT_PANEL_EXTREME else
                            "proxy_crowded_short" if p <= COT_PANEL_EXTREME else "")
    return out


def build_daily_panel(base: Optional[Path] = None, *, now: Optional[datetime] = None,
                      write: bool = True) -> dict:
    """The joinable daily panel from the typed tables -> parquet + schema JSON
    under `official/panel/`. Returns a receipt (rows per block, path, schema)."""
    import pandas as pd
    now = now or _now()
    blocks = {"insiders": panel_insiders(read_table("insider_tx", base)),
              "politicians": panel_politicians(read_table("politician_trades", base)),
              "short_interest": panel_short_interest(read_table("short_interest", base)),
              "positioning": panel_positioning(read_table("positioning_cot", base))}
    merged: dict[tuple, dict] = {}
    for name, blk in blocks.items():
        for key, cols in blk.items():
            m = merged.setdefault(key, {"ticker": key[0], "public_date": key[1],
                                        "tradable_date": None})
            td = cols.get("tradable_date")
            if td and (m["tradable_date"] is None or td > m["tradable_date"]):
                m["tradable_date"] = td
            m.update({k: v for k, v in cols.items() if k != "tradable_date"})
    cols = list(PANEL_SCHEMA)
    df = pd.DataFrame([merged[k] for k in sorted(merged)], columns=cols)
    for c in ("public_date", "tradable_date"):
        df[c] = pd.to_datetime(df[c])
    rec = {"t": iso(now), "rows": int(len(df)),
           "rows_by_block": {k: len(v) for k, v in blocks.items()},
           "tickers": int(df["ticker"].nunique()) if len(df) else 0,
           "public_date_min": str(df["public_date"].min().date()) if len(df) else None,
           "public_date_max": str(df["public_date"].max().date()) if len(df) else None,
           "schema": PANEL_SCHEMA}
    if write:
        pdir = root(base) / "panel"
        pdir.mkdir(parents=True, exist_ok=True)
        path = pdir / PANEL_NAME
        tmp = path.with_suffix(".tmp.parquet")
        df.to_parquet(tmp, index=False)
        back = pd.read_parquet(tmp)
        if len(back) != len(df):                     # verify before replacing
            raise RuntimeError(f"panel write verify failed: {len(back)} != {len(df)}")
        tmp.replace(path)
        rec["path"] = str(path)
        DG.atomic_write_json(pdir / "official_daily_panel.receipt.json", rec)
    return rec


def panel_age_s(base: Optional[Path] = None) -> Optional[float]:
    p = root(base) / "panel" / "official_daily_panel.receipt.json"
    r = _read_json(p, None)
    try:
        return (_now() - datetime.fromisoformat(r["t"])).total_seconds()
    except (TypeError, KeyError, ValueError):
        return None


def table_counts(base: Optional[Path] = None, now: Optional[datetime] = None) -> dict:
    """Rows per table, and rows made public in the last 24 h."""
    now = now or _now()
    out = {}
    for t in TABLES:
        rows = read_table(t, base)
        n24 = 0
        for r in rows:
            try:
                if now - datetime.fromisoformat(str(r["public_utc"])) < timedelta(days=1):
                    n24 += 1
            except (KeyError, ValueError, TypeError):
                continue
        out[t] = {"rows": len(rows), "public_last_24h": n24, "path": str(table_path(t, base))}
    return out


def request_counts(base: Optional[Path] = None, now: Optional[datetime] = None) -> dict:
    """Requests per source and class over the last hour and day (health)."""
    now = now or _now()
    out: dict[str, dict] = {}
    try:
        lines = (root(base) / "requests.jsonl").read_text(encoding="utf-8",
                                                          errors="replace").splitlines()[-60000:]
    except OSError:
        return out
    for ln in lines:
        try:
            r = json.loads(ln)
            age = (now - datetime.fromisoformat(r["t"])).total_seconds()
        except (ValueError, KeyError, TypeError):
            continue
        if age >= 86400:
            continue
        s = out.setdefault(r.get("source") or "?", {"req_60m": 0, "req_24h": 0, "ok_24h": 0,
                                                    "classes_24h": {},
                                                    "lane": SOURCES.get(r.get("source"), {}).get("lane")})
        s["req_24h"] += 1
        if age < 3600:
            s["req_60m"] += 1
        if r.get("class") == "OK":
            s["ok_24h"] += 1
        c = str(r.get("class"))
        s["classes_24h"][c] = s["classes_24h"].get(c, 0) + 1
    return out
