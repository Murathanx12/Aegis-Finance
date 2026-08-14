"""
Aegis Finance — SEC Form 4 open-market-buy data source
=======================================================

Why this exists (the honest data finding behind TRIAL-INSIDER-IC):

The opportunistic-buy signal needs, per transaction, the **transaction code**
(``P`` = open-market purchase — the only insider trade the literature finds
informative) and the **price**. Two sources were probed and rejected:

  - **Finnhub free tier** returns ``transactionCode: ""`` and
    ``transactionPrice: 0`` (derivative grants), so the informative signal is
    NOT computable from it. Dead end.
  - **edgartools** parses Form 4 but hung for ~50 min on two dozen filings in
    testing — unusable inside a scheduled collector.

The viable path is parsing the **raw SEC Form 4 XML** ourselves: fast, no heavy
dependency, hard per-request timeouts so it can never hang the scheduler. This
module fetches a ticker's recent Form 4s and returns ONLY open-market purchases
(code ``P``), normalised into the dict shape that
``insider_trading.compute_opportunistic_buy_score`` consumes.

Network-touching → mark any test that calls the live functions ``slow``; the
pure parser ``parse_form4_open_market_buys`` is offline and unit-tested.

SEC fair-access: a descriptive User-Agent with contact is required; requests are
paced by the caller (≤10 req/s). Every network failure degrades to an empty
result — never raises, never blocks.
"""

from __future__ import annotations

import logging
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Optional

import requests

# Reuse the ONE process-wide SEC rate limiter. edgar_events' own comment is
# explicit: SEC enforces a hard 10 req/s cap and 403s offenders for ~10 min, so
# "ALL EDGAR HTTP must go through it." This module previously bypassed it with
# raw requests.get calls and fired ~360–1000 unpaced fetches per collector run
# at www.sec.gov → SEC returned 403 on every Archives fetch in prod (Railway's
# fast egress trips the threshold instantly; local dev's few calls never did).
# Routing through the shared limiter is the fix. See FRAGILITY_RESEARCH_2026-06-14.
from backend.services.edgar_events import _RATE_LIMITER

logger = logging.getLogger(__name__)

# SEC mandates a declared User-Agent with contact; env-overridable so prod
# (Railway) can set a compliant identifier without a code change. Defaults to the
# project contact, which is safe to commit.
_UA = os.environ.get("SEC_USER_AGENT", "Aegis Finance Research mrthnabdullaev@gmail.com")
_HEADERS = {"User-Agent": _UA, "Accept-Encoding": "gzip, deflate"}
_TIMEOUT = 10  # hard per-request ceiling — the anti-hang guard
_RETRY_403 = 1            # one retry on a 403 (transient rate-limit block)
_RETRY_BACKOFF_S = 1.0    # brief pause before the retry (limiter handles steady pacing)


def _sec_get(url: str) -> requests.Response:
    """Single choke-point for every SEC HTTP call in this module: pace through the
    shared process-wide limiter (≤8/s, under SEC's 10/s cap), send the mandatory
    UA, and retry once on a 403 (SEC returns 403 — not 429 — when the rate
    threshold trips). Raises on a persistent non-2xx so callers degrade to empty."""
    last: Optional[requests.Response] = None
    for attempt in range(_RETRY_403 + 1):
        _RATE_LIMITER.wait()
        last = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        if last.status_code != 403:
            break
        if attempt < _RETRY_403:
            logger.warning("SEC 403 (rate threshold?) on %s — backing off %.1fs and retrying",
                           url, _RETRY_BACKOFF_S)
            time.sleep(_RETRY_BACKOFF_S)
    assert last is not None
    last.raise_for_status()
    return last


# ── the tri-state source contract ───────────────────────────────────────────
# The prerequisite for Track E, and the same vocabulary the tool layer and the
# feature layer use. "No open-market purchases in the window" and "we could not
# find out" are different facts about the world and must not share a value.
STATUS_OK_DATA = "OK_DATA"
STATUS_OK_EMPTY = "OK_EMPTY"
STATUS_UNAVAILABLE = "UNAVAILABLE"

#: Successful map only. See `_ticker_cik_map`.
_CIK_MAP_CACHE: dict[str, str] = {}


def _ticker_cik_map() -> dict[str, str]:
    """Ticker → zero-padded 10-digit CIK, from SEC's master list.

    THIS WAS `@lru_cache(maxsize=1)` AND RETURNED `{}` ON FAILURE.

    That combination is the worst bug in this file's history, and it never
    raised anything. One transient SEC hiccup — a 403 from the rate threshold, a
    timeout, a bad gateway — cached an EMPTY MAP for the entire process
    lifetime. Every ticker afterwards resolved to "no CIK", every fetch returned
    the zero-buy shape, and `compute_opportunistic_buy_score` reported a
    confident `0.0 — "No open-market insider purchases"` for the whole universe,
    forever, until someone redeployed. On Railway that is until the next push.

    It is the exact shape of the failure the docstring above already describes
    happening once with Finnhub, reproduced one layer down by a caching
    decorator.

    Now: only a NON-EMPTY map is cached. A failure is a failure every time it is
    asked, which is the only honest answer.
    """
    if _CIK_MAP_CACHE:
        return _CIK_MAP_CACHE
    try:
        r = _sec_get("https://www.sec.gov/files/company_tickers.json")
        m = {v["ticker"].upper(): str(v["cik_str"]).zfill(10)
             for v in r.json().values()}
    except Exception as e:                                     # network/parse
        logger.warning("SEC ticker→CIK map fetch failed: %s — NOT cached; the "
                       "next call retries rather than reporting an empty "
                       "universe", e)
        return {}
    if m:
        _CIK_MAP_CACHE.update(m)
    else:
        logger.warning("SEC ticker→CIK map came back EMPTY — not cached")
    return m


def cik_map_is_loaded() -> bool:
    """Whether a real CIK map is in hand. Distinguishes 'unknown ticker' from
    'we never got the map', which is what makes the tri-state honest."""
    return bool(_CIK_MAP_CACHE)


def cik_for(ticker: str) -> Optional[str]:
    return _ticker_cik_map().get(ticker.upper())


def parse_form4_open_market_buys(xml_text: str) -> list[dict]:
    """Pure parser: extract open-market PURCHASES (code 'P', acquired) from one
    Form 4 XML document. Returns a list of {name, shares, value, date, type}.
    Offline + deterministic — this is the unit-tested core."""
    out: list[dict] = []
    try:
        root = ET.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
    except ET.ParseError:
        return out
    owner = (root.findtext(".//reportingOwner/reportingOwnerId/rptOwnerName") or "").strip()
    # Owner CIK enables per-insider history lookups (CMP routine/opportunistic);
    # normalised without leading zeros to match SEC bulk-file RPTOWNERCIK.
    owner_cik = (root.findtext(".//reportingOwner/reportingOwnerId/rptOwnerCik") or "").strip()
    owner_cik = owner_cik.lstrip("0") or owner_cik
    for tx in root.findall(".//nonDerivativeTransaction"):
        code = tx.findtext(".//transactionCoding/transactionCode")
        if code != "P":  # open-market purchase only
            continue
        ad = tx.findtext(".//transactionAcquiredDisposedCode/value")
        if ad and ad != "A":  # 'P' is an acquisition; guard against odd filings
            continue
        try:
            shares = float(tx.findtext(".//transactionShares/value") or 0)
            price = float(tx.findtext(".//transactionPricePerShare/value") or 0)
        except (TypeError, ValueError):
            continue
        if shares <= 0:
            continue
        out.append({
            "name": owner or "Unknown",
            "cik": owner_cik,
            "shares": shares,
            "value": shares * price,
            "date": tx.findtext(".//transactionDate/value") or "",
            "type": "P",
        })
    return out


def _filing_xml(cik_int: int, accession_nodash: str, primary_doc: str) -> Optional[str]:
    """Fetch a filing's ownership XML, falling back to the directory listing if
    the primary document is an xslt-rendered HTM rather than the raw XML."""
    base = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_nodash}/"
    try:
        r = _sec_get(base + primary_doc)
        if r.text.lstrip().startswith("<?xml") or "<ownershipDocument" in r.text:
            return r.text
        # primary doc was an xslt view → find the real .xml in the directory
        idx = _sec_get(base).text
        xmls = re.findall(r'href="([^"]+\.xml)"', idx)
        if not xmls:
            return None
        name = xmls[0].split("/")[-1]
        return _sec_get(base + name).text
    except Exception as e:
        logger.warning("Form 4 XML fetch failed (%s%s): %s", base, primary_doc, e)
        return None


def fetch_open_market_buys(ticker: str, lookback_days: int = 180,
                           max_filings: int = 30) -> dict:
    """A ticker's open-market insider PURCHASES over the lookback window, as a
    normalised dict consumable by ``compute_opportunistic_buy_score``.

    Robust by construction: missing CIK, network errors, or unparseable filings
    all degrade to an empty (zero-buy) result — this never raises and, with the
    hard per-request timeout, never hangs the scheduler.
    """
    base = {"ticker": ticker, "source": "sec_form4",
            "lookback_days": lookback_days, "buys": [], "n_buys": 0,
            "total_buy_value": 0.0, "n_filings_examined": 0,
            "n_filings_unfetchable": 0}

    def unavailable(reason: str, **extra) -> dict:
        return {**base, "status": STATUS_UNAVAILABLE, "reason": reason,
                "codes_available": False, **extra}

    cik = cik_for(ticker)
    if not cik:
        # These are DIFFERENT facts. Before the tri-state they were the same
        # return value, so a dead CIK map read as "this company has no insider
        # buying" for every ticker at once.
        if not cik_map_is_loaded():
            return unavailable("cik_map_unavailable")
        return unavailable("ticker_not_in_cik_map")

    try:
        sub = _sec_get(f"https://data.sec.gov/submissions/CIK{cik}.json").json()
        rec = sub["filings"]["recent"]
    except Exception as e:
        logger.warning("SEC submissions fetch failed for %s: %s", ticker, e)
        return unavailable("submissions_fetch_failed", error=str(e)[:200])

    cutoff = (date.today() - timedelta(days=lookback_days)).isoformat()
    cik_int = int(cik)
    buys: list[dict] = []
    seen = 0
    unfetchable = 0
    for form, acc, doc, fdate in zip(
        rec.get("form", []), rec.get("accessionNumber", []),
        rec.get("primaryDocument", []), rec.get("filingDate", []),
    ):
        if form != "4" or fdate < cutoff:
            continue
        if seen >= max_filings:
            break
        seen += 1
        xml_text = _filing_xml(cik_int, acc.replace("-", ""), doc)
        if not xml_text:
            # A filing we could not read is not a filing with no purchases in
            # it. Counted, and it can invalidate an otherwise-empty answer.
            unfetchable += 1
            continue
        parsed = parse_form4_open_market_buys(xml_text)
        for b in parsed:
            b["filing_date"] = fdate   # PIT stamp: fires on filing, not trans
        buys.extend(parsed)

    out = {**base, "buys": buys, "n_buys": len(buys),
           "total_buy_value": float(sum(b["value"] for b in buys)),
           "n_filings_examined": seen, "n_filings_unfetchable": unfetchable,
           "codes_available": True}

    if buys:
        # Real purchases found. If some filings were unreadable the COUNT is a
        # lower bound, and saying so is the difference between a measurement and
        # a number.
        out["status"] = STATUS_OK_DATA
        if unfetchable:
            out["partial"] = True
            out["reason"] = f"{unfetchable}_of_{seen}_filings_unreadable"
        return out

    if unfetchable:
        # Nothing found, and part of the window could not be read. An absence we
        # did not fully look for is not an absence.
        return unavailable("empty_but_unverified",
                           n_filings_examined=seen,
                           n_filings_unfetchable=unfetchable)

    if seen == 0:
        # No Form 4s at all in the window. Real, and informative — but not the
        # same as "insiders did not buy": foreign private issuers do not file
        # Form 4 at all, so silence here has two explanations.
        out["status"] = STATUS_OK_EMPTY
        out["reason"] = "no_form4_filings_in_window"
        return out

    out["status"] = STATUS_OK_EMPTY
    out["reason"] = "no_open_market_purchases"
    return out
