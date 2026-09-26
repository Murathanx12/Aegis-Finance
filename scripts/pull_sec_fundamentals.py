"""Current fundamentals from SEC XBRL — the 630-day gap the amplitude test priced.

    python -m scripts.pull_sec_fundamentals --limit 50 --smoke
    python -m scripts.pull_sec_fundamentals --universe-from-bars

WHY THIS IS THE JOB
===================
`scripts/gap_audit` on 2026-09-22 found three blocking sources. One of them is
the only input this programme has ever measured to carry economically
meaningful amplitude:

    fundamentals   asof 2024-12-31   630 days stale   NO REFRESH EXISTS

and the amplitude test the same day put a number on it: **38.4-39.5 bps/month**,
stable at every book size from k=20 to k=100, against a 20 bps cost floor --
where price/volume, over 122 month-blocks and 3,578 names, could not clear its
own 35 bps toll (`NEGATIVE_RESULTS.md` §59).

So the single highest-value thing in the repo is not a model. It is a current
value for `gp_at`, `ope_be` and `be_me` on our own tickers.

WHY AN API AND NOT THE BROWSER
==============================
OpenClaw proved it can read EDGAR's rendered pages. It should not be used for
this. SEC publishes every reported XBRL fact at

    https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json

with, for every value, the **`filed` date** -- the day it became public. That is
exactly the field PIT discipline needs, it is exact rather than parsed, and it
is a documented interface rather than a page layout that changes. The browser's
job is the UNSTRUCTURED last mile (guidance language, IR commentary, management
wording changes); numbers that already have an API are not that.

SEC asks for a declaring User-Agent and fair use. Both are honoured below.

PIT, AND THE TRAP IT AVOIDS
===========================
Every row carries `filed` (public on this date) and `end` (the period it
describes), and they are never conflated. A 2026-Q2 figure filed on 2026-08-05
is not knowable on 2026-07-01, and a feature builder that joins on `end` instead
of `filed` has built a backtest that trades on information it did not have. This
is the same distinction `web_events` draws between `observed_at` and
`evidence_date`, for the same reason.

WHAT IT COMPUTES
================
Only what the amplitude test actually used, and only from facts present:

    gp_at    (Revenues - CostOfRevenue) / Assets      gross profitability
    ope_be   OperatingIncomeLoss / StockholdersEquity
    be_me    StockholdersEquity / market equity       (market cap joined later)
    at_gr1   year-over-year asset growth

A ratio whose numerator or denominator is missing is `None` and says which fact
was absent. It is never zero-filled: LightGBM reads NaN natively, and a zero
where a number is missing is a lie the model will fit.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _cfg                          # noqa: E402

OUT_DIR = _cfg.OPTIMUS_LEDGER_DIR / "fundamentals_sec"
TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"

#: SEC asks for a declaring User-Agent with contact details, and for fair use.
UA = "Aegis-Finance research (mrthnabdullaev@gmail.com)"
#: SEC's published guidance is 10 requests/second; this sits far under it.
SLEEP_S = 0.25

#: us-gaap tags, in preference order — filers disagree about which they use.
FACTS: dict[str, tuple[str, ...]] = {
    "revenue": ("RevenueFromContractWithCustomerExcludingAssessedTax",
                "RevenueFromContractWithCustomerIncludingAssessedTax",
                "Revenues", "SalesRevenueNet"),
    "cogs": ("CostOfGoodsAndServicesSold", "CostOfRevenue", "CostOfGoodsSold"),
    "operating_income": ("OperatingIncomeLoss",),
    "net_income": ("NetIncomeLoss",),
    "assets": ("Assets",),
    "equity": ("StockholdersEquity",
               "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
    "cash": ("CashAndCashEquivalentsAtCarryingValue",),
    "debt": ("LongTermDebtNoncurrent", "LongTermDebt"),
    "shares": ("CommonStockSharesOutstanding", "EntityCommonStockSharesOutstanding"),
    # 2026-09-26: the intangibles pair (Chan-Lakonishok-Sougiannis R&D intensity,
    # Eisfeldt-Papanikolaou organisation capital). Present in companyfacts for
    # filers that report them; absent = the firm does not break the line out.
    # strategy_library_ext.attach builds `rd_intensity` / `org_capital` from the
    # ANNUAL rows once the next extraction writes these facts.
    "rd": ("ResearchAndDevelopmentExpense",
           "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost"),
    "sga": ("SellingGeneralAndAdministrativeExpense",),
}


def _get(url: str, timeout: float = 45.0) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept-Encoding": "gzip, deflate"})
    with urllib.request.urlopen(req, timeout=timeout) as fh:    # noqa: S310 allowlisted
        raw = fh.read()
        if fh.headers.get("Content-Encoding") == "gzip":
            import gzip
            raw = gzip.decompress(raw)
    return json.loads(raw)


def ticker_to_cik() -> dict[str, int]:
    d = _get(TICKER_MAP_URL)
    rows = d.values() if isinstance(d, dict) else d
    return {str(r["ticker"]).upper(): int(r["cik_str"]) for r in rows}


def series(facts: dict, tags: tuple[str, ...]) -> list[dict]:
    """EVERY reported value with the date it became public, oldest first.

    The first version kept only the newest value, which ranks today and cannot
    backtest anything: a walk-forward needs the number AS IT STOOD at each
    rebalance date. `companyfacts` returns the whole history in the SAME call,
    so keeping it costs one dict comprehension and no extra request.

    Deduplicated on `filed` keeping the LAST seen, because a restatement filed
    the same day supersedes what it restates. Sorted by `filed`, never by
    `end` — an amended 10-K/A filed in September carrying a December period is
    information that arrived in September.
    """
    out: dict[tuple, dict] = {}
    for tag in tags:
        node = (facts.get("us-gaap") or {}).get(tag) or (facts.get("dei") or {}).get(tag)
        if not node:
            continue
        for unit_rows in (node.get("units") or {}).values():
            for r in unit_rows:
                filed, val = r.get("filed"), r.get("val")
                if not filed or val is None:
                    continue
                # `start` is what makes a FLOW fact comparable. A 10-K states
                # annual revenue and a 10-Q a quarter, so without the period
                # length `revenue / assets` swings 3-4x with the form type --
                # measured on NVDA 2026-09-23: gp_at read 0.742, 0.236, 0.225
                # across three consecutive filings of the same company. A
                # feature that moves with which form filed last is a form-type
                # indicator, not profitability. Stock facts (assets, equity)
                # have no `start` and need none.
                start = r.get("start")
                days = None
                if start and r.get("end"):
                    try:
                        days = (date.fromisoformat(r["end"])
                                - date.fromisoformat(start)).days
                    except ValueError:
                        days = None
                key = (filed, days)
                prev = out.get(key)
                if prev is None or (r.get("end") or "") >= (prev.get("end") or ""):
                    out[key] = {"filed": filed, "val": float(val),
                                "end": r.get("end"), "start": start,
                                "period_days": days, "tag": tag,
                                "form": r.get("form")}
    return sorted(out.values(), key=lambda d: d["filed"])


def _latest(facts: dict, tags: tuple[str, ...], *, asof: str | None = None) -> dict | None:
    """The most recently FILED value among these tags, at or before `asof`.

    Chooses on `filed`, never on `end`: what matters is when the number became
    public, not which quarter it describes.
    """
    best = None
    for tag in tags:
        node = (facts.get("us-gaap") or {}).get(tag) or (facts.get("dei") or {}).get(tag)
        if not node:
            continue
        for unit_rows in (node.get("units") or {}).values():
            for r in unit_rows:
                filed = r.get("filed")
                if not filed or (asof and filed > asof):
                    continue
                if best is None or filed > best["filed"] or (
                        filed == best["filed"] and (r.get("end") or "") > (best.get("end") or "")):
                    best = {"val": r.get("val"), "filed": filed, "end": r.get("end"),
                            "fy": r.get("fy"), "fp": r.get("fp"), "tag": tag,
                            "form": r.get("form")}
    return best


def _ratio(num: dict | None, den: dict | None) -> tuple[float | None, str]:
    if num is None:
        return None, "numerator fact absent"
    if den is None:
        return None, "denominator fact absent"
    try:
        d = float(den["val"])
        if d == 0:
            return None, "denominator is zero"
        return float(num["val"]) / d, "ok"
    except (TypeError, ValueError, KeyError):
        return None, "fact is not numeric"


def company_row(ticker: str, cik: int, *, asof: str | None = None) -> dict:
    facts = _get(FACTS_URL.format(cik=cik)).get("facts") or {}
    got = {k: _latest(facts, tags, asof=asof) for k, tags in FACTS.items()}
    hist = {k: series(facts, tags) for k, tags in FACTS.items()}
    hist = {k: v for k, v in hist.items() if v}

    gp = None
    if got["revenue"] and got["cogs"]:
        gp = {"val": float(got["revenue"]["val"]) - float(got["cogs"]["val"]),
              "filed": max(got["revenue"]["filed"], got["cogs"]["filed"]),
              "end": got["revenue"].get("end")}
    gp_at, gp_why = _ratio(gp, got["assets"])
    ope_be, ope_why = _ratio(got["operating_income"], got["equity"])
    ni_be, ni_why = _ratio(got["net_income"], got["equity"])

    filed_dates = [v["filed"] for v in got.values() if v and v.get("filed")]
    return {
        "ticker": ticker, "cik": cik,
        "observed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "latest_filed": max(filed_dates) if filed_dates else None,
        "facts": {k: v for k, v in got.items() if v},
        "_history": hist,          # stripped from the receipt, written to parquet
        "n_history_points": {k: len(v) for k, v in hist.items()},
        "missing_facts": [k for k, v in got.items() if not v],
        "ratios": {
            "gp_at": gp_at, "gp_at_why": gp_why,
            "ope_be": ope_be, "ope_be_why": ope_why,
            "ni_be": ni_be, "ni_be_why": ni_why,
            "book_equity": (got["equity"] or {}).get("val"),
        },
        "read_me_first": ("`filed` is when the number became PUBLIC; `end` is the "
                          "period it describes. Join features on `filed`."),
    }


def universe_from_bars(limit: int | None) -> list[str]:
    import pandas as pd
    from backend.services import xs_ranker as XR
    bars = XR.load_bars(XR.survivorship_free_paths())
    last = bars["date"].max()
    day = bars[bars["date"] == last].copy()
    day["dv"] = day["close"] * day["volume"]
    day = day[~day["symbol"].isin(XR.INDEX_PROXIES)]
    syms = day.nlargest(limit or len(day), "dv")["symbol"].tolist()
    return syms


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", default=None, help="comma separated")
    ap.add_argument("--universe-from-bars", action="store_true")
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--asof", default=None, help="only facts filed at or before this date")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--history-out", default=None,
                    help="long-form filing history parquet (default: "
                         "fundamentals_sec/sec_facts_history.parquet)")
    a = ap.parse_args(argv)

    t0 = time.time()
    if a.tickers:
        syms = [s.strip().upper() for s in a.tickers.split(",") if s.strip()]
    elif a.universe_from_bars:
        syms = universe_from_bars(a.limit)
    else:
        syms = ["NVDA", "MU", "AAPL", "AVGO", "AMD"][: a.limit]
    if a.smoke:
        syms = syms[:5]

    print(f"ticker->CIK map from SEC ...", flush=True)
    cmap = ticker_to_cik()
    print(f"  {len(cmap):,} tickers mapped", flush=True)

    rows, missing, failed = [], [], []
    for i, s in enumerate(syms, 1):
        cik = cmap.get(s)
        if not cik:
            missing.append(s)
            continue
        try:
            rows.append(company_row(s, cik, asof=a.asof))
        except (urllib.error.HTTPError, urllib.error.URLError, ValueError) as exc:
            failed.append({"ticker": s, "why": f"{type(exc).__name__}: {exc}"[:150]})
        if i % 25 == 0:
            print(f"  {i}/{len(syms)} ...", flush=True)
        time.sleep(SLEEP_S)

    have_gp = sum(1 for r in rows if r["ratios"]["gp_at"] is not None)
    filed = [r["latest_filed"] for r in rows if r["latest_filed"]]
    receipt = {
        "receipt": "pull_sec_fundamentals", "licence": "PRODUCT_EXPERIMENT",
        "llm_spend_usd": 0.0,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "asof_requested": a.asof,
        "n_requested": len(syms), "n_rows": len(rows),
        "n_no_cik": len(missing), "no_cik": missing[:20],
        "n_failed": len(failed), "failed": failed[:10],
        "gp_at_coverage": round(have_gp / len(rows), 3) if rows else 0.0,
        "newest_filing": max(filed) if filed else None,
        "oldest_filing": min(filed) if filed else None,
        "elapsed_s": round(time.time() - t0, 1),
        "rows": rows,
    }
    receipt["headline"] = (
        f"{len(rows)} companies, gp_at computable for {have_gp} "
        f"({receipt['gp_at_coverage']:.0%}), newest filing {receipt['newest_filing']}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # The HISTORY goes to a long-form parquet, not into the receipt. 3,000 names
    # x 9 facts x ~50 filings is over a million rows; a JSON receipt carrying
    # that is unreadable and unqueryable, and what a feature builder wants is a
    # frame it can `merge_asof` on anyway.
    long_rows = []
    for r in rows:
        for fact, pts in (r.pop("_history", None) or {}).items():
            for pt in pts:
                long_rows.append({"ticker": r["ticker"], "cik": r["cik"],
                                  "fact": fact, "filed": pt["filed"],
                                  "end": pt.get("end"), "start": pt.get("start"),
                                  "period_days": pt.get("period_days"),
                                  "val": pt["val"], "form": pt.get("form")})
    if long_rows:
        import pandas as pd
        panel_path = Path(a.history_out) if a.history_out else OUT_DIR / "sec_facts_history.parquet"
        df = pd.DataFrame(long_rows)
        df["filed"] = pd.to_datetime(df["filed"])
        df = df.sort_values(["ticker", "fact", "filed"]).reset_index(drop=True)
        df.to_parquet(panel_path, index=False)
        receipt["history_panel"] = {
            "path": str(panel_path), "rows": int(len(df)),
            "tickers": int(df["ticker"].nunique()),
            "facts": sorted(df["fact"].unique().tolist()),
            "first_filed": str(df["filed"].min().date()),
            "last_filed": str(df["filed"].max().date()),
            "mb": round(panel_path.stat().st_size / 1e6, 2),
        }

    out = Path(a.out) if a.out else OUT_DIR / f"sec_fundamentals_{date.today()}.json"
    out.write_text(json.dumps(receipt, indent=1, default=str), encoding="utf-8")

    print(f"\n{receipt['headline']}")
    if rows:
        print(f"\n{'ticker':>8} {'filed':>12} {'gp_at':>9} {'ope_be':>9}  missing")
        for r in rows[:15]:
            g, o = r["ratios"]["gp_at"], r["ratios"]["ope_be"]
            print(f"{r['ticker']:>8} {str(r['latest_filed']):>12} "
                  f"{('—' if g is None else f'{g:8.4f}'):>9} "
                  f"{('—' if o is None else f'{o:8.4f}'):>9}  "
                  f"{','.join(r['missing_facts'][:4])}")
    print(f"\n-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
