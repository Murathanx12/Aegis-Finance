"""Kalshi prediction-market daily PIT snapshots — TRIAL-PREDMARKET-1.

WHAT THIS IS
============
One snapshot per market per UTC day of the crowd's probability (yes bid/ask,
mid, open interest) for macro event contracts in the watched categories.
Forward-only, append-only, written blind to any pairing — the corpus is the
substrate for the registered model-vs-market Brier comparison
("Aegis module"/TRIALS/PREREG_PREDMARKET_1.md) and a live calibration
benchmark for the house probability models.

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


def _receipt_path(day: str):
    return config.PREDICTION_MARKET_DIR / "receipts" / f"{day}.json"


def _day_file(day: str):
    return config.PREDICTION_MARKET_DIR / "snapshots" / f"{day}.jsonl"


def _write_receipt(day: str, body: dict) -> None:
    """Dated receipt per collection day. Never raises."""
    try:
        p = _receipt_path(day)
        p.parent.mkdir(parents=True, exist_ok=True)
        body = dict(body)
        body.setdefault("job", "pi_prediction_markets")
        body.setdefault("trial", TRIAL_ID)
        body.setdefault("banner", BANNER)
        body.setdefault("filters", {
            "categories": sorted(config.PREDICTION_MARKET_CATEGORIES),
            "max_close_days": config.PREDICTION_MARKET_MAX_CLOSE_DAYS,
            "open_interest": "> 0",
        })
        p.write_text(json.dumps(body, indent=2, default=str),
                     encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        logger.error("prediction-market receipt write FAILED (%s: %s) — the "
                     "snapshot was unaffected but left no evidence it ran",
                     type(exc).__name__, exc)


def snapshot_daily(now: datetime | None = None) -> dict:
    """One PIT snapshot per UTC day. The fetch happens BEFORE any write.

    Returns a dict whose `status` is one of:
      * `ok`              — rows written to snapshots/<day>.jsonl + receipt
      * `ok_empty`        — the fetch succeeded and found zero in-scope
                            markets; the receipt says so out loud
      * `already_written` — today's snapshot exists; nothing re-fetched
                            (idempotent under the scheduler's retry patterns)
    A fetch failure raises PredictionMarketFetchError and writes NOTHING —
    the missing receipt for the day is the evidence.
    """
    now = now or datetime.now(timezone.utc)
    day = now.date().isoformat()
    df = _day_file(day)
    if df.exists() and df.stat().st_size > 0:
        with df.open("r", encoding="utf-8") as fh:
            n = sum(1 for line in fh if line.strip())
        return {"status": "already_written", "day": day, "rows": n}

    fetched = fetch_open_markets(now=now)
    rows = fetched["rows"]
    ran_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    base = {"day": day, "ran_at": ran_at,
            "rows_written": len(rows),
            "events_seen": fetched["events_seen"],
            "pages": fetched["pages"],
            "pages_truncated": fetched["pages_truncated"]}

    if not rows:
        # Written down, never inferred: zero in-scope markets on a feed that
        # answered is a RESULT (OK_EMPTY), distinct from a feed that died
        # (raised above, no receipt).
        body = {**base, "status": "ok_empty"}
        _write_receipt(day, body)
        return body

    df.parent.mkdir(parents=True, exist_ok=True)
    tmp = df.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, default=str) + "\n")
    tmp.replace(df)

    body = {**base, "status": "ok"}
    _write_receipt(day, body)
    return body


def latest_summary(top_n: int = 15) -> dict:
    """Read-only summary of the newest snapshot, for the API surface.

    Reads DISK only (no fetch on a request path). OK_EMPTY when no snapshot
    has been written yet — named, not inferred.
    """
    d = config.PREDICTION_MARKET_DIR / "snapshots"
    files = sorted(d.glob("*.jsonl")) if d.exists() else []
    if not files:
        return {"status": "OK_EMPTY", "banner": BANNER, "trial": TRIAL_ID,
                "reason": ("no snapshots yet — pi_prediction_markets runs "
                           "17:55 ET daily")}
    newest = files[-1]
    rows = []
    with newest.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    by_cat: dict[str, int] = {}
    for r in rows:
        c = r.get("category") or "unknown"
        by_cat[c] = by_cat.get(c, 0) + 1
    top = sorted(rows, key=lambda r: r.get("open_interest") or 0.0,
                 reverse=True)[:top_n]
    receipt = None
    rp = _receipt_path(newest.stem)
    if rp.exists():
        try:
            receipt = json.loads(rp.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            receipt = {"error": "receipt unreadable"}
    return {
        "status": "ok",
        "banner": BANNER,
        "trial": TRIAL_ID,
        "snapshot_date": newest.stem,
        "n_markets": len(rows),
        "by_category": by_cat,
        "top_by_open_interest": [
            {k: r.get(k) for k in ("ticker", "title", "yes_sub_title",
                                   "category", "mid", "yes_bid", "yes_ask",
                                   "open_interest", "close_time")}
            for r in top
        ],
        "receipt": receipt,
    }
