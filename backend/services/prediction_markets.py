"""Prediction-market daily PIT snapshots — TRIAL-PREDMARKET-1 and -2.

WHAT THIS IS
============
One snapshot per market per venue per UTC day of the crowd's probability
(bid/ask, mid, open interest / liquidity) for event contracts:

* Kalshi (macro categories) — the substrate for the registered
  model-vs-market Brier comparison (PREREG_PREDMARKET_1) and a live
  calibration benchmark for the house probability models.
* Polymarket (liquid contracts) — the second venue of the registered
  cross-venue divergence measurement (PREREG_PREDMARKET_2), which replaces
  the asserted "arbitrage is rejected" with a measured verdict: either the
  ESCALATE branch produces a written execution proposal for Murat, or the
  rejection stands on receipts.

Forward-only, append-only, written blind to any pairing or matching.

WHAT THIS IS NOT
================
Not a signal. Nothing in any scoring path (arena_composite, signal_engine,
lane logic, fragility composite) may read this corpus before a successor
trial passes. Not an order path: no Kalshi account, no execution — R1
recorded 6/6 LLM forecasters losing real capital here at crowd-matching
Brier, and that receipt is the standing reason this file contains no trading
code.

FAILURE CONTRACT (silent-fragility rules)
=========================================
* A fetch failure RAISES before any write — a broken feed must never land a
  false-zero snapshot that reads as a quiet day.
* A genuinely empty day is written down as a receipt with status `ok_empty`,
  never inferred from silence.
* A truncated pagination is recorded (`pages_truncated`), because a partial
  snapshot wearing a full snapshot's name is the house failure mode.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone

import requests

from backend import config

logger = logging.getLogger(__name__)

TRIAL_ID = "TRIAL-PREDMARKET-1"
#: Sent on every request. Bare default user agents get reset by some edges
#: (the Railway lesson, 2026-08-21) and blocked by some vendors.
USER_AGENT = "aegis-finance-predmarket/1 (open-source research; no execution)"
BANNER = ("DESCRIPTIVE CONTEXT — market-implied probabilities, never a "
          "signal; no scoring path may read this before a successor trial "
          "passes; no execution")

_TIMEOUT_S = 20
_PAGE_LIMIT = 200
#: Gamma's hard per-page cap, measured live 2026-08-21.
_POLYMARKET_PAGE_LIMIT = 100
#: Gamma 422s past offset ~2000 (measured live: 2000 ok, 2100 refused), so
#: deep pagination is impossible. Pages are ordered LIQUIDITY-DESCENDING, so
#: this cap truncates the least liquid names above the floor — declared in
#: the receipt via pages_truncated, never silent.
_POLYMARKET_MAX_PAGES = 20
_PAGE_SLEEP_S = 0.15


class PredictionMarketFetchError(RuntimeError):
    """The source failed BEFORE any write happened."""


def _get_json(url: str, params: dict) -> dict:
    """One HTTP GET. Tests patch this — the fast suite is network-blocked."""
    r = requests.get(url, params=params,
                     headers={"User-Agent": USER_AGENT}, timeout=_TIMEOUT_S)
    r.raise_for_status()
    return r.json()


def _f(x) -> float | None:
    try:
        return None if x in (None, "") else float(x)
    except (TypeError, ValueError):
        return None


def _parse_ts(s) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def _row(ev: dict, m: dict, snapshot_date: str, fetched_at: str) -> dict:
    yes_bid = _f(m.get("yes_bid_dollars"))
    yes_ask = _f(m.get("yes_ask_dollars"))
    # The prereg's frozen price definition: mid = (yes_bid + yes_ask)/2 in
    # dollars. A one-sided book has no mid; the row is still kept (last_price
    # remains reportable) and the pairing spec decides eligibility later.
    mid = (round((yes_bid + yes_ask) / 2.0, 4)
           if yes_bid is not None and yes_ask is not None else None)
    return {
        "snapshot_date": snapshot_date,
        "fetched_at": fetched_at,
        "source": "kalshi",
        "category": ev.get("category"),
        "series_ticker": ev.get("series_ticker"),
        "event_ticker": ev.get("event_ticker"),
        "event_title": ev.get("title"),
        "ticker": m.get("ticker"),
        "title": m.get("title"),
        "yes_sub_title": m.get("yes_sub_title"),
        "market_type": m.get("market_type"),
        "yes_bid": yes_bid,
        "yes_ask": yes_ask,
        "mid": mid,
        "last_price": _f(m.get("last_price_dollars")),
        "open_interest": _f(m.get("open_interest_fp")),
        "volume": _f(m.get("volume_fp")),
        "volume_24h": _f(m.get("volume_24h_fp")),
        "close_time": m.get("close_time"),
        "status": m.get("status"),
    }


def fetch_open_markets(now: datetime | None = None) -> dict:
    """Every open, in-scope market in the watched categories. Raises on failure.

    Scope (declared in config, printed in the receipt): category in
    PREDICTION_MARKET_CATEGORIES, close_time within
    PREDICTION_MARKET_MAX_CLOSE_DAYS, open interest > 0 (a dead book's mid is
    not a probability).
    """
    now = now or datetime.now(timezone.utc)
    snapshot_date = now.date().isoformat()
    fetched_at = now.isoformat(timespec="seconds")
    horizon = now + timedelta(days=config.PREDICTION_MARKET_MAX_CLOSE_DAYS)

    rows: list[dict] = []
    cursor: str | None = None
    pages = 0
    events_seen = 0
    truncated = False
    while True:
        params: dict = {"status": "open", "limit": _PAGE_LIMIT,
                        "with_nested_markets": "true"}
        if cursor:
            params["cursor"] = cursor
        try:
            page = _get_json(f"{config.KALSHI_API_BASE}/events", params)
        except Exception as e:  # noqa: BLE001
            # First page or mid-pagination, the answer is the same: raise.
            # A partial snapshot wearing a full snapshot's name would poison
            # the corpus more quietly than a missing day ever could.
            raise PredictionMarketFetchError(
                f"kalshi /events failed at page {pages}: {e}") from e
        events = page.get("events") or []
        events_seen += len(events)
        for ev in events:
            if ev.get("category") not in config.PREDICTION_MARKET_CATEGORIES:
                continue
            for m in ev.get("markets") or []:
                if m.get("status") not in ("active", "open"):
                    continue
                close_t = _parse_ts(m.get("close_time"))
                if close_t is None or close_t > horizon:
                    continue
                if (_f(m.get("open_interest_fp")) or 0.0) <= 0:
                    continue
                rows.append(_row(ev, m, snapshot_date, fetched_at))
        pages += 1
        cursor = page.get("cursor")
        if not cursor or not events:
            break
        if pages >= config.PREDICTION_MARKET_MAX_PAGES:
            truncated = True
            break
        time.sleep(_PAGE_SLEEP_S)

    return {"rows": rows, "pages": pages, "events_seen": events_seen,
            "pages_truncated": truncated,
            "snapshot_date": snapshot_date, "fetched_at": fetched_at}


def _polymarket_row(m: dict, snapshot_date: str, fetched_at: str) -> dict:
    bid, ask = _f(m.get("bestBid")), _f(m.get("bestAsk"))
    mid = (round((bid + ask) / 2.0, 4)
           if bid is not None and ask is not None else None)
    ev = (m.get("events") or [{}])[0]
    fee = (m.get("feeSchedule") or {})
    return {
        "snapshot_date": snapshot_date,
        "fetched_at": fetched_at,
        "source": "polymarket",
        "category": None,           # gamma /markets carries no category; the
                                    # matching spec pairs by contract terms
        "series_ticker": None,
        "event_ticker": ev.get("ticker") or ev.get("slug"),
        "event_title": ev.get("title"),
        "ticker": m.get("slug") or m.get("conditionId"),
        "title": m.get("question"),
        "yes_sub_title": None,
        "market_type": "binary",
        "yes_bid": bid,
        "yes_ask": ask,
        "mid": mid,
        "last_price": _f(m.get("lastTradePrice")),
        "open_interest": None,
        "liquidity": _f(m.get("liquidityNum")),
        "volume": _f(m.get("volumeNum")),
        "volume_24h": _f(m.get("volume24hr")),
        "spread": _f(m.get("spread")),
        "fee_rate": _f(fee.get("rate")),
        "outcomes": m.get("outcomes"),
        "outcome_prices": m.get("outcomePrices"),
        "close_time": m.get("endDate"),
        "status": "active",
    }


def fetch_polymarket_markets(now: datetime | None = None) -> dict:
    """Every liquid, open Polymarket contract in scope. Raises on failure.

    Scope (FROZEN in PREREG_PREDMARKET_2): active + accepting orders,
    liquidity >= POLYMARKET_MIN_LIQUIDITY (server-side filter), close within
    PREDICTION_MARKET_MAX_CLOSE_DAYS, volume24hr > 0.
    """
    now = now or datetime.now(timezone.utc)
    snapshot_date = now.date().isoformat()
    fetched_at = now.isoformat(timespec="seconds")
    horizon = now + timedelta(days=config.PREDICTION_MARKET_MAX_CLOSE_DAYS)

    rows: list[dict] = []
    pages = 0
    markets_seen = 0
    truncated = False
    while True:
        # Gamma serves at most 100 rows per page regardless of the requested
        # limit (measured live 2026-08-21: limit=200 returned 100). Ask for
        # the real cap and end on an EMPTY page — ending on a short page
        # silently dropped everything after page 1.
        params = {"closed": "false", "active": "true",
                  "liquidity_num_min": config.POLYMARKET_MIN_LIQUIDITY,
                  "order": "liquidityNum", "ascending": "false",
                  "limit": _POLYMARKET_PAGE_LIMIT,
                  "offset": pages * _POLYMARKET_PAGE_LIMIT}
        try:
            page = _get_json(f"{config.POLYMARKET_API_BASE}/markets", params)
        except Exception as e:  # noqa: BLE001
            raise PredictionMarketFetchError(
                f"polymarket /markets failed at page {pages}: {e}") from e
        if not isinstance(page, list):
            raise PredictionMarketFetchError(
                f"polymarket /markets returned a non-list at page {pages}")
        if not page:
            break
        markets_seen += len(page)
        for m in page:
            if not m.get("acceptingOrders", True):
                continue
            close_t = _parse_ts(m.get("endDate"))
            if close_t is None or close_t > horizon:
                continue
            if (_f(m.get("volume24hr")) or 0.0) <= 0:
                continue
            rows.append(_polymarket_row(m, snapshot_date, fetched_at))
        pages += 1
        if pages >= _POLYMARKET_MAX_PAGES:
            # Only a FULL final page means names were left behind.
            truncated = len(page) == _POLYMARKET_PAGE_LIMIT
            break
        time.sleep(_PAGE_SLEEP_S)

    return {"rows": rows, "pages": pages, "events_seen": markets_seen,
            "pages_truncated": truncated,
            "snapshot_date": snapshot_date, "fetched_at": fetched_at}


#: source name -> fetcher. Order is the run order; each source runs and
#: fails INDEPENDENTLY — one venue's outage must not cost the other's day.
SOURCES = {
    "kalshi": fetch_open_markets,
    "polymarket": fetch_polymarket_markets,
}


def _receipt_path(day: str, source: str):
    return config.PREDICTION_MARKET_DIR / "receipts" / f"{day}.{source}.json"


def _day_file(day: str, source: str):
    return config.PREDICTION_MARKET_DIR / "snapshots" / f"{day}.{source}.jsonl"


_FILTERS = {
    "kalshi": lambda: {
        "categories": sorted(config.PREDICTION_MARKET_CATEGORIES),
        "max_close_days": config.PREDICTION_MARKET_MAX_CLOSE_DAYS,
        "open_interest": "> 0",
    },
    "polymarket": lambda: {
        "min_liquidity_usdc": config.POLYMARKET_MIN_LIQUIDITY,
        "max_close_days": config.PREDICTION_MARKET_MAX_CLOSE_DAYS,
        "volume_24h": "> 0",
        "accepting_orders": True,
    },
}

_TRIALS = {"kalshi": "TRIAL-PREDMARKET-1", "polymarket": "TRIAL-PREDMARKET-2"}


def _write_receipt(day: str, source: str, body: dict) -> None:
    """Dated receipt per collection day per source. Never raises."""
    try:
        p = _receipt_path(day, source)
        p.parent.mkdir(parents=True, exist_ok=True)
        body = dict(body)
        body.setdefault("job", "pi_prediction_markets")
        body.setdefault("source", source)
        body.setdefault("trial", _TRIALS.get(source, TRIAL_ID))
        body.setdefault("banner", BANNER)
        body.setdefault("filters", _FILTERS[source]())
        p.write_text(json.dumps(body, indent=2, default=str),
                     encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        logger.error("prediction-market receipt write FAILED (%s: %s) — the "
                     "snapshot was unaffected but left no evidence it ran",
                     type(exc).__name__, exc)


def _snapshot_source(source: str, now: datetime) -> dict:
    """One source's daily snapshot. The fetch happens BEFORE any write.

    `status` is one of `ok` / `ok_empty` / `already_written`. A fetch failure
    raises PredictionMarketFetchError and writes NOTHING — the missing
    receipt for the day is the evidence.
    """
    day = now.date().isoformat()
    df = _day_file(day, source)
    if df.exists() and df.stat().st_size > 0:
        with df.open("r", encoding="utf-8") as fh:
            n = sum(1 for line in fh if line.strip())
        return {"status": "already_written", "day": day, "source": source,
                "rows": n}

    fetched = SOURCES[source](now=now)
    rows = fetched["rows"]
    ran_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    base = {"day": day, "source": source, "ran_at": ran_at,
            "rows_written": len(rows),
            "events_seen": fetched["events_seen"],
            "pages": fetched["pages"],
            "pages_truncated": fetched["pages_truncated"]}

    if not rows:
        # Written down, never inferred: zero in-scope markets on a feed that
        # answered is a RESULT (OK_EMPTY), distinct from a feed that died
        # (raised above, no receipt).
        body = {**base, "status": "ok_empty"}
        _write_receipt(day, source, body)
        return body

    df.parent.mkdir(parents=True, exist_ok=True)
    tmp = df.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, default=str) + "\n")
    tmp.replace(df)

    body = {**base, "status": "ok"}
    _write_receipt(day, source, body)
    return body


def snapshot_daily(now: datetime | None = None) -> dict:
    """All sources, one UTC day. Each source runs and fails INDEPENDENTLY.

    A source that raises is recorded as `{"status": "error", ...}` in the
    summary (and leaves no receipt — the absence is the evidence); the other
    sources still run. `any_error` is the loud flag the job wrapper logs on.
    """
    now = now or datetime.now(timezone.utc)
    day = now.date().isoformat()
    out: dict = {"day": day, "sources": {}, "any_error": False}
    for source in SOURCES:
        try:
            out["sources"][source] = _snapshot_source(source, now)
        except PredictionMarketFetchError as e:
            logger.error("prediction-market source %s FAILED: %s", source, e)
            out["sources"][source] = {"status": "error", "source": source,
                                      "error": str(e)}
            out["any_error"] = True
    return out


def latest_summary(top_n: int = 15) -> dict:
    """Read-only summary of the newest snapshot day, across sources.

    Reads DISK only (no fetch on a request path). OK_EMPTY when no snapshot
    has been written yet — named, not inferred. A source with no file for
    the newest day is reported as absent for that day, not hidden.
    """
    d = config.PREDICTION_MARKET_DIR / "snapshots"
    files = sorted(d.glob("*.jsonl")) if d.exists() else []
    if not files:
        return {"status": "OK_EMPTY", "banner": BANNER,
                "trials": _TRIALS,
                "reason": ("no snapshots yet — pi_prediction_markets runs "
                           "17:55 ET daily")}
    # File stem is "<day>.<source>"; newest day wins, then every source of it.
    newest_day = max(f.stem.split(".")[0] for f in files)
    day_files = [f for f in files if f.stem.split(".")[0] == newest_day]
    rows = []
    for f in day_files:
        with f.open("r", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    by_cat: dict[str, int] = {}
    by_source: dict[str, int] = {}
    for r in rows:
        c = r.get("category") or "uncategorised"
        by_cat[c] = by_cat.get(c, 0) + 1
        s = r.get("source") or "unknown"
        by_source[s] = by_source.get(s, 0) + 1
    # Cross-venue notional interest: OI (kalshi) or liquidity (polymarket).
    def _weight(r):
        return r.get("open_interest") or r.get("liquidity") or 0.0
    top = sorted(rows, key=_weight, reverse=True)[:top_n]
    receipts = {}
    for source in SOURCES:
        rp = _receipt_path(newest_day, source)
        if rp.exists():
            try:
                receipts[source] = json.loads(rp.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                receipts[source] = {"error": "receipt unreadable"}
        else:
            receipts[source] = None
    return {
        "status": "ok",
        "banner": BANNER,
        "trials": _TRIALS,
        "snapshot_date": newest_day,
        "n_markets": len(rows),
        "by_source": by_source,
        "by_category": by_cat,
        "top_by_interest": [
            {k: r.get(k) for k in ("source", "ticker", "title",
                                   "yes_sub_title", "category", "mid",
                                   "yes_bid", "yes_ask", "open_interest",
                                   "liquidity", "close_time")}
            for r in top
        ],
        "receipts": receipts,
    }
