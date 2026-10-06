"""Opportunity Explorer: read the newest stock-list receipt (chunk C4, 2026-10-06).

The owner's review of the 2026-09-27 stock-list PDF asked for a scrollable,
sortable website table instead of a PDF, with this column order:

    1 ticker · 2 weight · 3 sector · 4 price vs analyst targets (low/median/high)
    5 why the engine picked it (named services) · 6 dates / news
    7-8 insiders / holders / anything else the reader can use

This module is the READ side. The WRITE side is `scripts/opportunities_build.py`,
which joins the stock-list inputs (books ledger, the v3 build's ranked tables,
analyst snapshots, revision flow, earnings cache, Form 4, news) into ONE dated
receipt per run under `<OPTIMUS_LEDGER_DIR>/opportunities/`. The router serves
the newest receipt by the run stamp in its FILE NAME (never by mtime: a fresh
checkout makes every file "written today").

Rules the receipt follows, and this reader does not relax:

* A field with no receipt is `null` and its reason sits in the row's
  `missing_because[field]`. Never a guessed target: a public upside screener
  once fabricated 4-20x targets (memory: "a screener number is not evidence").
* `move_score` is MAGNITUDE (how far a name may travel in 21 sessions, from
  its own 63-session volatility). `direction` is a SEPARATE field from analyst
  consensus and revision flow, and is never derived from sigma.
* A list sorted by `move_score` is labelled `MAGNITUDE RANKING: not a long list`.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

from backend import config as _config

SCHEMA = "opportunities/1"

#: receipt file name: opportunities_<asof>_<run id>.json, run id = UTC stamp.
RECEIPT_RE = re.compile(r"^opportunities_(\d{4}-\d{2}-\d{2})_(\d{8}T\d{6}Z)\.json$")

#: a list id is lowercase letters, digits, '_' and '-' (it names a book or a table).
LIST_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_\-]{0,79}$")

#: Yahoo-style suffix -> (exchange, currency). A definitional mapping of the
#: ticker convention, not a lookup of the company.
SUFFIX_EXCHANGE: dict[str, tuple[str, str]] = {
    "KS": ("Korea Exchange (KOSPI)", "KRW"),
    "KQ": ("Korea Exchange (KOSDAQ)", "KRW"),
    "T": ("Tokyo Stock Exchange", "JPY"),
    "TW": ("Taiwan Stock Exchange", "TWD"),
    "TWO": ("Taipei Exchange", "TWD"),
    "HK": ("Hong Kong Stock Exchange", "HKD"),
    "SS": ("Shanghai Stock Exchange", "CNY"),
    "SZ": ("Shenzhen Stock Exchange", "CNY"),
    "DE": ("Deutsche Boerse XETRA", "EUR"),
    "F": ("Frankfurt Stock Exchange", "EUR"),
    "MI": ("Borsa Italiana (Milan)", "EUR"),
    "PA": ("Euronext Paris", "EUR"),
    "AS": ("Euronext Amsterdam", "EUR"),
    "BR": ("Euronext Brussels", "EUR"),
    "MC": ("Bolsa de Madrid", "EUR"),
    "L": ("London Stock Exchange", "GBP"),
    "SW": ("SIX Swiss Exchange", "CHF"),
    "ST": ("Nasdaq Stockholm", "SEK"),
    "CO": ("Nasdaq Copenhagen", "DKK"),
    "OL": ("Oslo Bors", "NOK"),
    "HE": ("Nasdaq Helsinki", "EUR"),
    "TO": ("Toronto Stock Exchange", "CAD"),
    "V": ("TSX Venture Exchange", "CAD"),
    "AX": ("Australian Securities Exchange", "AUD"),
    "NS": ("National Stock Exchange of India", "INR"),
    "BO": ("BSE (Bombay)", "INR"),
    "SI": ("Singapore Exchange", "SGD"),
}


def opportunities_dir(base: Optional[Path] = None) -> Path:
    return Path(base) if base is not None else Path(_config.OPTIMUS_LEDGER_DIR) / "opportunities"


def split_suffix(ticker: str) -> tuple[str, Optional[str]]:
    """'000660.KS' -> ('000660', 'KS'); 'BRK-B' -> ('BRK-B', None)."""
    t = str(ticker or "").strip().upper()
    if "." in t:
        root, suf = t.rsplit(".", 1)
        if root and suf.isalpha():
            return root, suf
    return t, None


def is_foreign(ticker: str) -> bool:
    return split_suffix(ticker)[1] is not None


def exchange_of(ticker: str) -> tuple[Optional[str], Optional[str]]:
    """(exchange, currency) from the suffix; (None, None) for a US-style ticker
    or an unmapped suffix (the builder then records why it is null)."""
    _, suf = split_suffix(ticker)
    if suf is None or suf not in SUFFIX_EXCHANGE:
        return None, None
    ex, cur = SUFFIX_EXCHANGE[suf]
    return ex, (cur or None)


def links(ticker: str, cik: Optional[str | int] = None) -> dict[str, Optional[str]]:
    """Click-through URLs built from the ticker (no data fetched). A foreign
    ticker gets the Yahoo quote page (Yahoo keeps the suffix convention); the
    US-only pages are null for it rather than a wrong US page."""
    t = str(ticker or "").strip().upper()
    q = quote(t, safe="")
    foreign = is_foreign(t)
    out: dict[str, Optional[str]] = {
        "yahoo": f"https://finance.yahoo.com/quote/{q}",
        "yahoo_analysts": f"https://finance.yahoo.com/quote/{q}/analysis",
        "marketwatch": None if foreign else f"https://www.marketwatch.com/investing/stock/{q.lower()}",
        "marketwatch_analysts": None if foreign else
        f"https://www.marketwatch.com/investing/stock/{q.lower()}/analystestimates",
        "benzinga": None if foreign else f"https://www.benzinga.com/quote/{q}",
        "edgar": None,
    }
    if cik:
        out["edgar"] = (f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK="
                        f"{int(cik):010d}&type=&dateb=&owner=include&count=40")
    elif not foreign:
        out["edgar"] = (f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={q}"
                        f"&type=&dateb=&owner=include&count=40")
    return out


def receipts(base: Optional[Path] = None) -> list[Path]:
    """Every receipt, newest first by the (asof, run id) in its NAME."""
    d = opportunities_dir(base)
    if not d.exists():
        return []
    named = []
    for p in d.glob("opportunities_*.json"):
        m = RECEIPT_RE.match(p.name)
        if m:
            named.append(((m.group(1), m.group(2)), p))
    return [p for _, p in sorted(named, reverse=True)]


def load_latest(base: Optional[Path] = None) -> Optional[dict]:
    """The newest READABLE receipt, or None when there is none. An unreadable
    newest file is skipped (and named) rather than served as an empty page."""
    skipped = []
    for p in receipts(base):
        try:
            blob = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            skipped.append({"file": p.name, "error": f"{type(e).__name__}: {e}"})
            continue
        if not isinstance(blob, dict) or blob.get("schema") != SCHEMA:
            skipped.append({"file": p.name, "error": "wrong schema"})
            continue
        blob["receipt_file"] = p.name
        blob["skipped_receipts"] = skipped
        return blob
    return None


def _age_days(stamp: Any, now: datetime) -> Optional[float]:
    if not stamp:
        return None
    try:
        s = str(stamp)
        dt = datetime.fromisoformat(s.replace("Z", "+00:00")) if "T" in s else \
            datetime.fromisoformat(s[:10]).replace(tzinfo=timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return round((now - dt).total_seconds() / 86400.0, 2)
    except ValueError:
        return None


def with_ages(lst: dict, now: Optional[datetime] = None) -> dict:
    """Attach `last_update_age_days` to every row at SERVE time (an age baked
    into the receipt would be wrong the next day)."""
    now = now or datetime.now(timezone.utc)
    rows = []
    for r in lst.get("rows") or []:
        r = dict(r)
        r["last_update_age_days"] = _age_days(r.get("last_update_utc"), now)
        rows.append(r)
    out = dict(lst)
    out["rows"] = rows
    return out


def list_index(blob: dict) -> list[dict]:
    """The switcher: every list without its rows."""
    return [{k: v for k, v in lst.items() if k != "rows"} | {"n_rows": len(lst.get("rows") or [])}
            for lst in blob.get("lists") or []]


def find_list(blob: dict, list_id: str) -> Optional[dict]:
    for lst in blob.get("lists") or []:
        if lst.get("list_id") == list_id:
            return lst
    return None
