"""
Aegis Finance — SEC EDGAR Event Stream
========================================

Pulls each company's recent SEC submissions feed (free, no key required)
and classifies 8-K filings by Item number into the event taxonomy that
event-driven traders watch:

    earnings              (Item 2.02 — Results of Operations)
    material_agreement    (Item 1.01 — Entry into a Material Definitive Agreement)
    bankruptcy            (Item 1.03 — Bankruptcy or Receivership)
    asset_acquisition     (Item 2.01 — Completion of Acquisition or Disposition)
    impairment            (Item 2.06 — Material Impairments)
    creation_obligation   (Item 2.03 — Creation of a Direct Financial Obligation)
    delisting             (Item 3.01 — Notice of Delisting)
    unregistered_sale     (Item 3.02 — Unregistered Sales of Equity Securities)
    accountant_change     (Item 4.01 — Changes in Registrant's Certifying Accountant)
    non_reliance          (Item 4.02 — Non-Reliance on Previously Issued Statements)
    asset_disposal        (Item 5.02 — Departure of Directors or Officers / Compensation)
    bylaws_change         (Item 5.03 — Amendments to Articles of Incorporation or Bylaws)
    regulation_fd         (Item 7.01 — Regulation FD Disclosure)
    other_events          (Item 8.01 — Other Events)
    financial_statements  (Item 9.01 — Financial Statements and Exhibits)
    management_change     (Items 5.02 and adjacent)

Why this matters:
    Bloomberg's TOP/FIRST and Refinitiv NewsScope live event streams
    drive the entire alpha-discovery workflow at most institutional
    desks. SEC EDGAR's feed is **free, official, and updates intraday**
    — but the raw filing list is unindexed by item. Item-level
    classification + materiality scoring turns it into a usable feed.

Data source
-----------
SEC EDGAR Submissions JSON API:
    https://data.sec.gov/submissions/CIK{cik:010d}.json
Required header: ``User-Agent`` (SEC enforces a contact identifier).

Cache: per-ticker submissions live ~10 min; CIK lookup table lives 24h.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

import requests

logger = logging.getLogger(__name__)

# SEC requires a non-bot User-Agent with contact info; this is a project
# identifier rather than a personal email so it can be safely committed.
_USER_AGENT = "AegisFinance Research aegis-finance@github.io"
_CIK_LOOKUP_URL = "https://www.sec.gov/files/company_tickers.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"

# In-process caches (cheap, refreshed via expiry timestamps).
_CIK_CACHE: dict[str, str] = {}
_CIK_CACHE_TS: Optional[datetime] = None
_CIK_CACHE_TTL_HOURS = 24

_SUBMISSION_CACHE: dict[str, tuple[datetime, dict]] = {}
_SUBMISSION_TTL_MIN = 10


# ── 8-K Item taxonomy ──────────────────────────────────────────────────────
# Classification rule: each Item maps to one event_type + a materiality
# score in [0,1] reflecting typical price impact (rough priors, refined
# by FinBERT sentiment when text is available).
ITEM_TAXONOMY: dict[str, tuple[str, float]] = {
    "1.01": ("material_agreement", 0.65),
    "1.02": ("agreement_termination", 0.60),
    "1.03": ("bankruptcy", 0.95),
    "1.04": ("mine_safety", 0.20),
    "2.01": ("asset_acquisition", 0.70),
    "2.02": ("earnings", 0.85),
    "2.03": ("debt_obligation", 0.55),
    "2.04": ("debt_acceleration", 0.85),
    "2.05": ("exit_disposal", 0.70),
    "2.06": ("impairment", 0.75),
    "3.01": ("delisting", 0.90),
    "3.02": ("unregistered_sale", 0.55),
    "3.03": ("rights_modification", 0.50),
    "4.01": ("accountant_change", 0.60),
    "4.02": ("non_reliance", 0.85),
    "5.01": ("control_change", 0.85),
    "5.02": ("management_change", 0.70),
    "5.03": ("bylaws_change", 0.40),
    "5.04": ("trading_blackout", 0.45),
    "5.05": ("ethics_code", 0.30),
    "5.06": ("shell_status_change", 0.60),
    "5.07": ("shareholder_vote", 0.40),
    "5.08": ("shareholder_director", 0.35),
    "6.01": ("abs_disclosure", 0.30),
    "7.01": ("regulation_fd", 0.50),
    "8.01": ("other_event", 0.40),
    "9.01": ("financial_statements", 0.30),
}

# Items typically considered HIGH materiality (single-handedly market-moving)
HIGH_MATERIALITY_ITEMS = {"1.03", "2.02", "2.04", "3.01", "4.02", "5.01", "5.02"}


@dataclass
class EdgarEvent:
    """One classified 8-K (or other) event."""

    ticker: str
    cik: int
    accession: str
    form: str
    filed: str          # ISO date
    items: list[str]    # raw item codes
    event_types: list[str]
    materiality: float  # 0..1
    primary_doc_url: str
    is_8k: bool

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


# ── CIK lookup ─────────────────────────────────────────────────────────────


def _refresh_cik_lookup() -> None:
    """Pull SEC's master ticker→CIK file."""
    global _CIK_CACHE, _CIK_CACHE_TS
    try:
        resp = requests.get(
            _CIK_LOOKUP_URL,
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        # Schema: {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ...}
        cache: dict[str, str] = {}
        for entry in data.values():
            ticker = str(entry.get("ticker", "")).upper().strip()
            cik = entry.get("cik_str")
            if ticker and cik is not None:
                cache[ticker] = str(cik)
        if cache:
            _CIK_CACHE = cache
            _CIK_CACHE_TS = datetime.now(timezone.utc)
            logger.info("Refreshed EDGAR CIK lookup: %d tickers", len(cache))
    except Exception as e:
        logger.warning("CIK lookup refresh failed: %s", e)


def lookup_cik(ticker: str) -> Optional[int]:
    """Return SEC CIK for a ticker, refreshing the lookup table as needed."""
    global _CIK_CACHE_TS
    ticker = (ticker or "").upper().strip()
    if not ticker:
        return None

    if (
        _CIK_CACHE_TS is None
        or datetime.now(timezone.utc) - _CIK_CACHE_TS
        > timedelta(hours=_CIK_CACHE_TTL_HOURS)
    ):
        _refresh_cik_lookup()

    cik = _CIK_CACHE.get(ticker)
    return int(cik) if cik else None


# ── Submission fetcher ────────────────────────────────────────────────────


def _fetch_submissions(cik: int) -> Optional[dict]:
    """Hit the EDGAR submissions endpoint for a CIK with a small TTL cache."""
    now = datetime.now(timezone.utc)
    cached = _SUBMISSION_CACHE.get(str(cik))
    if cached and (now - cached[0]) < timedelta(minutes=_SUBMISSION_TTL_MIN):
        return cached[1]

    try:
        resp = requests.get(
            _SUBMISSIONS_URL.format(cik=int(cik)),
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        _SUBMISSION_CACHE[str(cik)] = (now, data)
        return data
    except Exception as e:
        logger.warning("EDGAR submissions fetch failed for CIK %s: %s", cik, e)
        return None


# ── Classification helpers ────────────────────────────────────────────────

# 8-K item codes appear in the "items" field as a comma-separated list of
# entries that look like "5.02 — Departure of Directors or Officers"
_ITEM_RE = re.compile(r"\b(\d+\.\d+)\b")


def parse_item_codes(items_field) -> list[str]:
    """Extract canonical item codes from an EDGAR 'items' field."""
    if items_field is None:
        return []
    if isinstance(items_field, list):
        text = " ".join(str(x) for x in items_field)
    else:
        text = str(items_field)
    seen: list[str] = []
    for match in _ITEM_RE.findall(text):
        if match not in seen:
            seen.append(match)
    return seen


def classify_items(item_codes: list[str]) -> tuple[list[str], float]:
    """Map raw 8-K item codes → (event_types, max materiality score)."""
    types: list[str] = []
    max_mat = 0.0
    for code in item_codes:
        info = ITEM_TAXONOMY.get(code)
        if not info:
            continue
        evt, mat = info
        if evt not in types:
            types.append(evt)
        if mat > max_mat:
            max_mat = mat
    return types, max_mat


def _doc_url(cik: int, accession: str, primary_doc: str) -> str:
    """EDGAR 'Archives' URL for the primary document of a filing."""
    acc_no_dashes = accession.replace("-", "")
    safe_doc = quote_plus(primary_doc) if primary_doc else ""
    return (
        f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
        f"{acc_no_dashes}/{safe_doc}"
    )


# ── Public API ───────────────────────────────────────────────────────────


def fetch_events_for_ticker(
    ticker: str,
    *,
    days_back: int = 90,
    only_8k: bool = True,
    high_materiality_only: bool = False,
) -> list[EdgarEvent]:
    """Recent classified events for one ticker."""
    cik = lookup_cik(ticker)
    if cik is None:
        return []

    sub = _fetch_submissions(cik)
    if not sub:
        return []

    recent = (sub.get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []
    accessions = recent.get("accessionNumber") or []
    filed_dates = recent.get("filingDate") or []
    items_list = recent.get("items") or [""] * len(forms)
    primary_docs = recent.get("primaryDocument") or [""] * len(forms)

    cutoff = datetime.now(timezone.utc).date() - timedelta(days=max(1, days_back))

    out: list[EdgarEvent] = []
    for i, form in enumerate(forms):
        try:
            filed_date = datetime.fromisoformat(filed_dates[i]).date()
        except Exception:
            continue
        if filed_date < cutoff:
            continue
        if only_8k and not str(form).startswith("8-K"):
            continue

        item_codes = parse_item_codes(items_list[i] if i < len(items_list) else "")
        evt_types, materiality = classify_items(item_codes)
        if high_materiality_only and not any(c in HIGH_MATERIALITY_ITEMS for c in item_codes):
            continue

        out.append(
            EdgarEvent(
                ticker=ticker.upper(),
                cik=cik,
                accession=accessions[i] if i < len(accessions) else "",
                form=str(form),
                filed=filed_date.isoformat(),
                items=item_codes,
                event_types=evt_types,
                materiality=round(materiality, 3),
                primary_doc_url=_doc_url(
                    cik,
                    accessions[i] if i < len(accessions) else "",
                    primary_docs[i] if i < len(primary_docs) else "",
                ),
                is_8k=str(form).startswith("8-K"),
            )
        )

    out.sort(key=lambda e: e.filed, reverse=True)
    return out


def fetch_events_for_universe(
    tickers: list[str],
    *,
    days_back: int = 14,
    high_materiality_only: bool = True,
) -> list[EdgarEvent]:
    """Aggregate event stream across a watchlist."""
    aggregated: list[EdgarEvent] = []
    for t in tickers:
        try:
            evts = fetch_events_for_ticker(
                t,
                days_back=days_back,
                only_8k=True,
                high_materiality_only=high_materiality_only,
            )
            aggregated.extend(evts)
        except Exception as e:
            logger.warning("event fetch failed for %s: %s", t, e)
    aggregated.sort(key=lambda e: e.filed, reverse=True)
    return aggregated


def event_summary(events: list[EdgarEvent]) -> dict:
    """Cheap rollup useful for dashboards."""
    if not events:
        return {"count": 0, "by_event_type": {}, "by_ticker": {}}
    by_type: dict[str, int] = {}
    by_ticker: dict[str, int] = {}
    high = 0
    for e in events:
        for t in e.event_types or ["unclassified"]:
            by_type[t] = by_type.get(t, 0) + 1
        by_ticker[e.ticker] = by_ticker.get(e.ticker, 0) + 1
        if any(item in HIGH_MATERIALITY_ITEMS for item in e.items):
            high += 1
    return {
        "count": len(events),
        "high_materiality_count": high,
        "by_event_type": dict(sorted(by_type.items(), key=lambda kv: -kv[1])),
        "by_ticker": dict(sorted(by_ticker.items(), key=lambda kv: -kv[1])),
    }
