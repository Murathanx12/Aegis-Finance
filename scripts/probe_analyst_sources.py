"""BUILD-1.1 / B1 — call every analyst source we hold a key for and write down
what it actually returns.

The standing rule in this programme is that "unavailable" is not a claim you may
make without a printed status code. The PM currently reads analyst data through
Yahoo only, and the single most important field in the mandate — the CHANGE in
the consensus target over 7/30/90 days — does not exist there. Before designing
anything on top of another vendor, call it.

    python scripts/probe_analyst_sources.py [--ticker DKNG] [--json out.json]

For every endpoint this records: HTTP status, whether a payload came back, the
top-level fields, whether the payload carries a per-analyst identity, a firm, a
target value, a TIMESTAMP on that target, and whether any history is present.
Nothing is inferred. An endpoint that 403s is recorded as a 403.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.config import PROJECT_ROOT      # noqa: E402  (loads .env)

TIMEOUT = 20


def _keys() -> dict:
    return {
        "finnhub": os.getenv("FINNHUB_API_KEY", ""),
        "fmp": os.getenv("FMP_API_KEY", ""),
        "polygon": os.getenv("POLYGON_API_KEY", ""),
        "alpha_vantage": os.getenv("ALPHA_VANTAGE_API_KEY", ""),
        "eodhd": os.getenv("EODHD_API_TOKEN", ""),
    }


def endpoints(ticker: str, k: dict) -> list[dict]:
    """Every endpoint that could plausibly carry an analyst target or its history."""
    return [
        # ── Finnhub ────────────────────────────────────────────────────────
        {"vendor": "finnhub", "name": "price-target", "key": k["finnhub"],
         "url": f"https://finnhub.io/api/v1/stock/price-target?symbol={ticker}&token={k['finnhub']}",
         "wants": "current consensus target (low/high/median/mean) + lastUpdated"},
        {"vendor": "finnhub", "name": "recommendation-trend", "key": k["finnhub"],
         "url": f"https://finnhub.io/api/v1/stock/recommendation?symbol={ticker}&token={k['finnhub']}",
         "wants": "monthly buy/hold/sell counts — a real rating HISTORY"},
        {"vendor": "finnhub", "name": "upgrade-downgrade", "key": k["finnhub"],
         "url": f"https://finnhub.io/api/v1/stock/upgrade-downgrade?symbol={ticker}&token={k['finnhub']}",
         "wants": "firm-attributed rating actions with dates"},
        {"vendor": "finnhub", "name": "earnings-calendar", "key": k["finnhub"],
         "url": f"https://finnhub.io/api/v1/calendar/earnings?symbol={ticker}&token={k['finnhub']}",
         "wants": "next earnings date — the catalyst layer (B5)"},
        {"vendor": "finnhub", "name": "earnings-surprises", "key": k["finnhub"],
         "url": f"https://finnhub.io/api/v1/stock/earnings?symbol={ticker}&token={k['finnhub']}",
         "wants": "estimate vs actual history per quarter"},
        # ── FMP. Both the legacy (v3/v4) and the current ("stable") paths are
        #    probed, because a 403 saying "Legacy Endpoint" is a migration
        #    notice, not an entitlement answer, and must not be recorded as one.
        {"vendor": "fmp", "name": "stable/price-target-consensus", "key": k["fmp"],
         "url": f"https://financialmodelingprep.com/stable/price-target-consensus?symbol={ticker}&apikey={k['fmp']}",
         "wants": "current consensus target on the CURRENT api"},
        {"vendor": "fmp", "name": "stable/price-target-news", "key": k["fmp"],
         "url": f"https://financialmodelingprep.com/stable/price-target-news?symbol={ticker}&page=0&limit=5&apikey={k['fmp']}",
         "wants": "per-analyst target CHANGES with dates — the ideal spine"},
        {"vendor": "fmp", "name": "stable/grades-historical", "key": k["fmp"],
         "url": f"https://financialmodelingprep.com/stable/grades-historical?symbol={ticker}&apikey={k['fmp']}",
         "wants": "rating history"},
        {"vendor": "fmp", "name": "price-target (v4)", "key": k["fmp"],
         "url": f"https://financialmodelingprep.com/api/v4/price-target?symbol={ticker}&apikey={k['fmp']}",
         "wants": "PER-ANALYST targets with publishedDate, analystName, "
                  "analystCompany — this is the spine if the free tier serves it"},
        {"vendor": "fmp", "name": "price-target-consensus", "key": k["fmp"],
         "url": f"https://financialmodelingprep.com/api/v4/price-target-consensus?symbol={ticker}&apikey={k['fmp']}",
         "wants": "consensus target high/low/median"},
        {"vendor": "fmp", "name": "upgrades-downgrades", "key": k["fmp"],
         "url": f"https://financialmodelingprep.com/api/v4/upgrades-downgrades?symbol={ticker}&apikey={k['fmp']}",
         "wants": "rating actions with newGrade/previousGrade and a date"},
        {"vendor": "fmp", "name": "analyst-estimates", "key": k["fmp"],
         "url": f"https://financialmodelingprep.com/api/v3/analyst-estimates/{ticker}?apikey={k['fmp']}",
         "wants": "EPS/revenue estimate history — revision measurement"},
        # ── Alpha Vantage ──────────────────────────────────────────────────
        {"vendor": "alpha_vantage", "name": "OVERVIEW", "key": k["alpha_vantage"],
         "url": f"https://www.alphavantage.co/query?function=OVERVIEW&symbol={ticker}&apikey={k['alpha_vantage']}",
         "wants": "AnalystTargetPrice + AnalystRatingStrongBuy..Sell counts"},
        # ── EODHD ──────────────────────────────────────────────────────────
        {"vendor": "eodhd", "name": "fundamentals (AnalystRatings)", "key": k["eodhd"],
         "url": f"https://eodhd.com/api/fundamentals/{ticker}.US?api_token={k['eodhd']}&filter=AnalystRatings&fmt=json",
         "wants": "TargetPrice + rating counts"},
        {"vendor": "eodhd", "name": "fundamentals (Earnings::Trend)", "key": k["eodhd"],
         "url": f"https://eodhd.com/api/fundamentals/{ticker}.US?api_token={k['eodhd']}&filter=Earnings::Trend&fmt=json",
         "wants": "estimate REVISION history (up/down last 7/30 days)"},
        # ── Polygon ────────────────────────────────────────────────────────
        {"vendor": "polygon", "name": "last quote (NBBO)", "key": k["polygon"],
         "url": f"https://api.polygon.io/v2/last/nbbo/{ticker}?apiKey={k['polygon']}",
         "wants": "a REAL bid/ask — the retail execution question (P4)"},
        {"vendor": "polygon", "name": "ticker overview", "key": k["polygon"],
         "url": f"https://api.polygon.io/v3/reference/tickers/{ticker}?apiKey={k['polygon']}",
         "wants": "listing status / share class — universe eligibility"},
    ]


ANALYST_HINTS = {
    "analyst_identity": ("analystname", "analyst_name", "analyst"),
    "firm_identity": ("analystcompany", "gradingcompany", "firm", "company"),
    "target_value": ("pricetarget", "targetmean", "targethigh", "targetlow",
                     "targetmedian", "analysttargetprice", "targetprice",
                     "adjpricetarget", "targetconsensus"),
    "target_timestamp": ("publisheddate", "lastupdated", "date", "period",
                         "updateddate", "newsurl"),
    "rating_action": ("newgrade", "previousgrade", "tograde", "fromgrade",
                      "strongbuy", "buy", "hold", "sell", "action"),
}


def _walk_keys(obj, depth=0, out=None):
    out = out if out is not None else set()
    if depth > 3:
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.add(str(k).lower())
            _walk_keys(v, depth + 1, out)
    elif isinstance(obj, list):
        for v in obj[:3]:
            _walk_keys(v, depth + 1, out)
    return out


def probe(ep: dict) -> dict:
    import requests
    row = {"vendor": ep["vendor"], "endpoint": ep["name"], "wants": ep["wants"],
           "key_present": bool(ep["key"]), "status": None, "ok": False,
           "rows": None, "fields": [], "has": {}, "sample": None,
           "error": None}
    if not ep["key"]:
        row["status"] = "NO_KEY"
        row["error"] = "no API key in .env — not called"
        return row
    try:
        r = requests.get(ep["url"], timeout=TIMEOUT,
                         headers={"User-Agent": "aegis-finance/build1.1"})
        row["status"] = r.status_code
        try:
            payload = r.json()
        except ValueError:
            row["error"] = f"non-JSON body: {r.text[:120]}"
            return row
    except Exception as e:                       # noqa: BLE001
        row["status"] = "EXC"
        row["error"] = str(e)[:200]
        return row

    if isinstance(payload, dict) and any(
            k in payload for k in ("Error Message", "error", "Note",
                                   "Information")):
        row["error"] = json.dumps(payload)[:200]
    row["rows"] = len(payload) if isinstance(payload, list) else 1
    keys = _walk_keys(payload)
    row["fields"] = sorted(keys)[:40]
    for label, hints in ANALYST_HINTS.items():
        row["has"][label] = any(h in k for k in keys for h in hints)
    # "history" = more than one dated observation came back in one call
    row["has"]["history"] = bool(
        isinstance(payload, list) and len(payload) > 1
        and row["has"]["target_timestamp"])
    row["ok"] = (row["status"] == 200 and not row["error"]
                 and bool(payload) and row["rows"] > 0)
    row["sample"] = json.dumps(
        payload[0] if isinstance(payload, list) and payload else payload,
        default=str)[:400]
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", default="DKNG")
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    k = _keys()
    print(f"probing analyst sources for {a.ticker} at "
          f"{datetime.now().isoformat(timespec='seconds')}")
    print(f"keys present: "
          f"{', '.join(n for n, v in k.items() if v) or 'NONE'}\n")

    rows = []
    for ep in endpoints(a.ticker, k):
        row = probe(ep)
        rows.append(row)
        flags = ",".join(f for f, v in row["has"].items() if v) or "-"
        print(f"{row['vendor']:<14} {row['endpoint']:<28} "
              f"status={str(row['status']):<8} rows={str(row['rows']):<5} "
              f"{flags}")
        if row["error"]:
            print(f"{'':<14} error: {row['error'][:150]}")
        elif row["ok"]:
            print(f"{'':<14} sample: {row['sample'][:180]}")
    out = {"ticker": a.ticker,
           "probed_at": datetime.now().isoformat(timespec="seconds"),
           "keys_present": {n: bool(v) for n, v in k.items()},
           "results": rows}
    if a.json:
        Path(a.json).write_text(json.dumps(out, indent=2, default=str),
                                encoding="utf-8")
        print(f"\nwritten: {a.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
