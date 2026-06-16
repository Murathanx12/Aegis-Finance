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
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_UA = "Aegis Finance Research mrthnabdullaev@gmail.com"
_HEADERS = {"User-Agent": _UA}
_TIMEOUT = 10  # hard per-request ceiling — the anti-hang guard


@lru_cache(maxsize=1)
def _ticker_cik_map() -> dict[str, str]:
    """Ticker → zero-padded 10-digit CIK, from SEC's master list (cached once)."""
    try:
        r = requests.get("https://www.sec.gov/files/company_tickers.json",
                         headers=_HEADERS, timeout=_TIMEOUT)
        r.raise_for_status()
        return {v["ticker"].upper(): str(v["cik_str"]).zfill(10) for v in r.json().values()}
    except Exception as e:  # network/parse — degrade to empty
        logger.warning("SEC ticker→CIK map fetch failed: %s", e)
        return {}


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
        r = requests.get(base + primary_doc, headers=_HEADERS, timeout=_TIMEOUT)
        r.raise_for_status()
        if r.text.lstrip().startswith("<?xml") or "<ownershipDocument" in r.text:
            return r.text
        # primary doc was an xslt view → find the real .xml in the directory
        idx = requests.get(base, headers=_HEADERS, timeout=_TIMEOUT).text
        xmls = re.findall(r'href="([^"]+\.xml)"', idx)
        if not xmls:
            return None
        name = xmls[0].split("/")[-1]
        return requests.get(base + name, headers=_HEADERS, timeout=_TIMEOUT).text
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
    empty = {"ticker": ticker, "source": "sec_form4", "lookback_days": lookback_days,
             "buys": [], "n_buys": 0, "total_buy_value": 0.0}
    cik = cik_for(ticker)
    if not cik:
        return empty
    try:
        sub = requests.get(f"https://data.sec.gov/submissions/CIK{cik}.json",
                          headers=_HEADERS, timeout=_TIMEOUT).json()
        rec = sub["filings"]["recent"]
    except Exception as e:
        logger.warning("SEC submissions fetch failed for %s: %s", ticker, e)
        return empty

    cutoff = (date.today() - timedelta(days=lookback_days)).isoformat()
    cik_int = int(cik)
    buys: list[dict] = []
    seen = 0
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
        if xml_text:
            buys.extend(parse_form4_open_market_buys(xml_text))

    return {"ticker": ticker, "source": "sec_form4", "lookback_days": lookback_days,
            "buys": buys, "n_buys": len(buys),
            "total_buy_value": float(sum(b["value"] for b in buys))}
