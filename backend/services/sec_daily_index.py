"""Every Form 3/4/5 filed on a given day, from SEC's own daily index.

WHY AN INDEX AND NOT A TICKER LIST
==================================
The existing Form 4 path asks "what did insiders do at AAPL", once per ticker in
a universe we chose. That is fine for enriching a stock page and wrong for a
Teacher Library, for two reasons that both bite in the same direction:

1. **Universe bias.** A corpus assembled by looping over the 150 names we already
   track can only ever contain insider activity at companies we already thought
   were interesting. Any cross-sectional claim built on it inherits our
   selection, invisibly.
2. **It cannot be complete, and cannot say so.** A per-ticker sweep has no idea
   what it missed. The daily index is the SEC's own list of everything filed
   that day, so coverage is checkable: the count in the index is the
   denominator.

The index is also point-in-time by construction, which is the property COPY-LAB
needs. `form.idx` for a date is published that day and lists what became public
that day — so a collector that walks forward one day at a time can never see a
filing before the world did. That is not a rule we impose on ourselves and hope
to keep; it is a property of the file.

NO BACKFILLS
============
`fetch_index` will happily fetch an old date, and `collect_day` refuses to write
one unless `allow_historical=True` is passed explicitly. COPY-LAB's inception
rule already refused a qualifying cluster for being pre-inception; the same
discipline belongs at the source. History is for the Gym; the lanes get forward
data only.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta, timezone

logger = logging.getLogger(__name__)

#: Ownership forms and their amendments. Form 3 is the opening balance, 4 the
#: changes, 5 the annual catch-up for what 4 did not have to report in time.
OWNERSHIP_FORMS = frozenset({"3", "4", "5", "3/A", "4/A", "5/A"})

INDEX_URL = ("https://www.sec.gov/Archives/edgar/daily-index/"
             "{year}/QTR{qtr}/form.{stamp}.idx")

#: SEC asks for <=10 req/s and a descriptive UA. The shared `_sec_get` in
#: `insider_form4` already carries the throttle and the header, so this module
#: reuses it rather than opening a second, unthrottled path to the same host.


def index_url(d: date) -> str:
    return INDEX_URL.format(year=d.year, qtr=(d.month - 1) // 3 + 1,
                            stamp=d.strftime("%Y%m%d"))


def parse_index(text: str) -> list[dict]:
    """`form.idx` → one dict per ownership filing. Pure; unit-tested offline.

    The file is fixed-width-ish with a ruler line of dashes. Splitting on
    whitespace breaks on company names with spaces, which is most of them, so
    the form type and the trailing path are anchored and the middle is taken as
    the name.

    The date is `YYYYMMDD` with no separators in the live file — verified
    against `form.20260813.idx`, 1.39 MB, on 2026-08-14. A first version of
    this parser required `YYYY-MM-DD` because the fixture had been written that
    way, and it therefore matched nothing at all: it reported a Thursday with
    hundreds of Form 4s as `OK_EMPTY`, "index published but held no ownership
    forms". Green tests, zero rows, a plausible-looking status. Both spellings
    are accepted now and both are in the fixtures.
    """
    out: list[dict] = []
    started = False
    for line in text.splitlines():
        if not started:
            # The dashed ruler separates the header block from the rows.
            if set(line.strip()) == {"-"} and len(line.strip()) > 10:
                started = True
            continue
        if not line.strip():
            continue
        m = re.match(r"^(\S+)\s+(.+?)\s+(\d{1,10})\s+"
                     r"(\d{4}-?\d{2}-?\d{2})\s+(\S+)\s*$", line)
        if not m:
            continue
        form_type, company, cik, filed, path = m.groups()
        if "-" not in filed:
            filed = f"{filed[:4]}-{filed[4:6]}-{filed[6:8]}"
        if form_type not in OWNERSHIP_FORMS:
            continue
        out.append({
            "form_type": form_type,
            "company": company.strip(),
            "cik": cik.lstrip("0") or cik,
            "filed_date": filed,
            "path": path,
            "accession": path.rsplit("/", 1)[-1].replace(".txt", ""),
        })
    return out


def published_days(year: int, qtr: int) -> set[str]:
    """Which `form.YYYYMMDD.idx` files actually exist for a quarter.

    EDGAR's daily index is served from S3, and **S3 answers a missing key with
    403 AccessDenied, not 404**. So "today's index has not been published yet"
    and "we have been blocked" arrive as the same status code — and the retry
    logic then backs off, retries, and eventually reports a timeout. Measured
    2026-08-14 15:00 UTC: the latest published file was 2026-08-13, and asking
    for 2026-08-14 produced `403 AccessDenied` followed by a ReadTimeout, which
    the caller would have recorded as a source failure.

    The directory listing is the only honest way to tell them apart, and it is
    one cheap request that removes an entire class of false alarm.
    """
    from backend.services.insider_form4 import _sec_get
    url = (f"https://www.sec.gov/Archives/edgar/daily-index/"
           f"{year}/QTR{qtr}/index.json")
    try:
        items = _sec_get(url).json()["directory"]["item"]
    except Exception as exc:                                   # noqa: BLE001
        logger.warning("could not list %s (%s) — publication status unknown",
                       url, type(exc).__name__)
        return set()
    return {i["name"] for i in items
            if str(i.get("name", "")).startswith("form.")}


def fetch_index(d: date) -> dict:
    """The day's ownership filings, or an explicit reason there are none.

    A weekend, a holiday and an outage all produce zero filings, and they are
    not the same fact. The status vocabulary keeps them apart, because "no
    insider bought anything today" and "we could not ask" are the two readings
    this project has paid the most to keep separate.
    """
    from backend.services.insider_form4 import _sec_get

    if d.weekday() >= 5:
        return {"date": d.isoformat(), "status": "OK_EMPTY",
                "reason": "weekend_no_edgar_index", "filings": []}
    url = index_url(d)
    # Ask what exists BEFORE asking for it, because a missing key 403s and a
    # 403 is indistinguishable from a block. `NOT_YET_PUBLISHED` is a real,
    # expected state — EDGAR posts the day's index after the close — and it must
    # never be recorded as a source failure or, worse, as a day with no
    # insider activity.
    published = published_days(d.year, (d.month - 1) // 3 + 1)
    fname = url.rsplit("/", 1)[-1]
    if published and fname not in published:
        return {"date": d.isoformat(), "status": "NOT_YET_PUBLISHED",
                "reason": ("EDGAR has not posted this day's index yet (it is "
                           "published after the filing day closes); this is "
                           "not an absence of filings and not a failure"),
                "url": url, "filings": []}
    try:
        r = _sec_get(url)
    except Exception as exc:                                   # noqa: BLE001
        return {"date": d.isoformat(), "status": "UNAVAILABLE",
                "reason": f"fetch_failed:{type(exc).__name__}", "url": url,
                "filings": []}
    if getattr(r, "status_code", 200) in (403, 404):
        # EDGAR publishes no index on federal holidays.
        return {"date": d.isoformat(), "status": "OK_EMPTY",
                "reason": "no_index_published (holiday)",
                "url": url, "filings": []}
    filings = parse_index(r.text)
    return {
        "date": d.isoformat(),
        "status": "OK_DATA" if filings else "OK_EMPTY",
        "reason": "" if filings else "index_published_but_held_no_ownership_forms",
        "url": url,
        "n_index_rows": len(r.text.splitlines()),
        "filings": filings,
    }


def filing_xml_url(cik: str, accession: str) -> str:
    nodash = accession.replace("-", "")
    return (f"https://www.sec.gov/Archives/edgar/data/{cik}/{nodash}/"
            f"{accession}-index.htm")


def fetch_filing_document(cik: str, accession: str) -> str | None:
    """The ownership XML for one filing, or None with a warning.

    Reuses `insider_form4._filing_xml`'s fallback (primary doc may be an
    xslt-rendered HTM rather than the raw XML) instead of re-deriving it.
    """
    from backend.services.insider_form4 import _filing_xml, _sec_get

    nodash = accession.replace("-", "")
    base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{nodash}/"
    try:
        idx = _sec_get(base).text
        xmls = re.findall(r'href="([^"]+\.xml)"', idx)
        # The rendered xslt view lives at a path containing "xslF345X"; the raw
        # document is the other one. Preferring the raw file avoids parsing HTML
        # that merely looks like the filing.
        raw = [x for x in xmls if "xsl" not in x.lower()] or xmls
        if not raw:
            return None
        return _sec_get(base + raw[0].rsplit("/", 1)[-1]).text
    except Exception as exc:                                   # noqa: BLE001
        logger.warning("ownership XML fetch failed for %s/%s: %s",
                       cik, accession, exc)
        return _filing_xml(int(cik), nodash, "")


def collect_day(d: date | str, *, limit: int | None = None,
                allow_historical: bool = False,
                today: date | None = None) -> dict:
    """Fetch, parse and summarise one day of ownership filings.

    Returns a receipt. Writing to the Teacher Library ledger is the caller's
    job (`teacher_library.adapters_ownership`), so this stays a pure collection
    step that can be run and inspected without touching evidence.
    """
    if isinstance(d, str):
        d = date.fromisoformat(d)
    today = today or datetime.now(timezone.utc).date()

    # NO SILENT BACKFILLS. Same rule COPY-LAB already enforces at the lane, at
    # the source this time: a corpus that quietly absorbed history would make
    # every forward claim built on it unfalsifiable.
    if d < today - timedelta(days=1) and not allow_historical:
        return {"date": d.isoformat(), "status": "REFUSED",
                "reason": (f"{d.isoformat()} is historical relative to "
                           f"{today.isoformat()}; pass allow_historical=True "
                           f"and expect the rows to be Gym material, not "
                           f"forward evidence"),
                "filings": [], "parsed": []}

    idx = fetch_index(d)
    if idx["status"] != "OK_DATA":
        return {**idx, "parsed": [], "n_parsed": 0, "n_parse_errors": 0}

    filings = idx["filings"]
    truncated = limit is not None and len(filings) > limit
    if truncated:
        # Announced, never silent. A capped run that reported its parsed count
        # without saying it capped would read as complete coverage.
        logger.warning("collect_day: capping %d filings at %d for %s — this "
                       "run is a SAMPLE, not the day", len(filings), limit,
                       d.isoformat())
        filings = filings[:limit]

    parsed, errors = [], 0
    for f in filings:
        xml = fetch_filing_document(f["cik"], f["accession"])
        if not xml:
            errors += 1
            parsed.append({**f, "status": "UNAVAILABLE",
                           "reason": "document_not_retrievable"})
            continue
        from backend.services.ownership_forms import parse_ownership_form
        p = parse_ownership_form(xml)
        if p["status"] == "PARSE_ERROR":
            errors += 1
        parsed.append({**f, **p})

    return {
        "date": d.isoformat(),
        "status": "OK_DATA",
        "url": idx.get("url"),
        "n_ownership_filings_in_index": len(idx["filings"]),
        "n_attempted": len(filings),
        "sampled": truncated,
        "coverage": (len(filings) / len(idx["filings"])
                     if idx["filings"] else 0.0),
        "n_parsed": len(parsed) - errors,
        "n_parse_errors": errors,
        "parsed": parsed,
    }
