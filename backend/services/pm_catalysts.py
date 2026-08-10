"""The catalyst calendar — what is scheduled to happen to these names, and when.

BUILD-1 shipped with nothing here at all, and the handoff called it "the largest
single gap in the product — bigger than anything in the scoring", correctly: a
book holding three pre-revenue clinical names is a book whose returns are
decided on specific dates, and the engine did not know any of them.

This is **v0 and it is deliberately narrow**. The B1 source probe
(`docs/BUILD1/ANALYST_SOURCE_COVERAGE.md`, receipts in the JSON beside it)
established what we can actually get for free today, with printed status codes:

    earnings dates + estimates      Finnhub /calendar/earnings      200  ✓
    earnings surprise history       Finnhub /stock/earnings         200  ✓
    FDA / PDUFA dates               no entitled source                   ✗
    secondary offerings, 13D/G      no entitled source                   ✗
    lockup expiries, investor days  no entitled source                   ✗

So the calendar covers earnings from a vendor, and everything else from the
`catalysts:` block a human writes into the book file. `coverage()` reports that
gap as a first-class field rather than letting an empty list read as "nothing is
coming up" — which for APLT, NTLA and BHVN would be the single most dangerous
thing this product could imply.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, datetime, timedelta
from typing import Any, Optional

from backend.cache import cache_get, cache_set

logger = logging.getLogger(__name__)

_BASE = "https://finnhub.io/api/v1"
_TIMEOUT = 12
CACHE_TTL = 6 * 3600
#: How far ahead the calendar looks.
HORIZON_DAYS = 120

#: What this layer does NOT know. Printed with every calendar.
UNCOVERED = (
    "FDA/PDUFA action dates", "clinical readout windows",
    "secondary offerings and shelf takedowns", "13D/13G filings",
    "lockup expiries", "index adds/deletes", "investor days",
    "guidance updates outside earnings",
)


class CatalystFetchError(RuntimeError):
    """The calendar was not retrieved. Distinct from "nothing is scheduled"."""


def _hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:16]


#: Why the last fetch for a ticker failed, if it did. An empty calendar caused
#: by a 403 and an empty calendar caused by a quiet quarter are different facts,
#: and this module exists precisely so they are never confused.
FETCH_FAILURES: dict[str, str] = {}


def _finnhub(path: str, params: dict) -> Optional[Any]:
    """One GET. Returns None on any failure, and records WHY — loudly.

    Silent-fragility audit, BUILD-1.1: this logged at INFO and returned None,
    so a 403 and "nothing scheduled" produced an identical empty list. For a
    calendar whole purpose is to not let silence read as safety, that is the
    house bug.
    """
    from backend.config import api_keys
    who = f"{path}:{params.get('symbol', '')}"
    if not api_keys.has("finnhub"):
        FETCH_FAILURES[who] = "no finnhub key"
        return None
    import requests
    try:
        r = requests.get(f"{_BASE}/{path}",
                         params={**params, "token": api_keys.finnhub},
                         timeout=_TIMEOUT)
        if r.status_code != 200:
            FETCH_FAILURES[who] = f"HTTP {r.status_code}"
            logger.warning("finnhub %s -> %s", who, r.status_code)
            return None
        FETCH_FAILURES.pop(who, None)
        return r.json()
    except Exception as e:                       # noqa: BLE001
        FETCH_FAILURES[who] = f"request failed: {str(e)[:80]}"
        logger.warning("finnhub %s failed: %s", who, e)
        return None


def _event(kind: str, when: Any, *, source: str, expectedness: str,
           affected_metric: str, direction: Optional[str] = None,
           confidence: str = "scheduled", next_observable: str = "",
           detail: Optional[dict] = None) -> dict:
    """One catalyst, in the shape every catalyst must take.

    `direction` is almost always None and that is correct: knowing that
    earnings are on the 6th is knowledge; knowing which way they go is not.
    """
    return {
        "kind": kind,
        "event_time": str(when)[:10] if when else None,
        "first_public_time": None,       # scheduled events: we learn of them
        "days_away": _days_away(when),   # from the calendar, not from a leak
        "source": source,
        "expectedness": expectedness,    # scheduled | announced | speculative
        "affected_metric": affected_metric,
        "direction": direction,
        "confidence": confidence,
        "next_observable": next_observable,
        "receipt": _hash(detail or {"kind": kind, "when": str(when)}),
        "detail": detail or {},
    }


def _days_away(when: Any) -> Optional[int]:
    try:
        d = datetime.fromisoformat(str(when)[:10]).date()
    except (TypeError, ValueError):
        return None
    return (d - date.today()).days


def earnings_events(ticker: str, *, horizon_days: int = HORIZON_DAYS) -> list[dict]:
    """Scheduled earnings from Finnhub. Free tier, verified 200 on 2026-08-10."""
    key = f"pm_catalyst_earn:{ticker}:{horizon_days}"
    hit = cache_get(key, CACHE_TTL)
    if hit is not None:
        return hit
    today = date.today()
    payload = _finnhub("calendar/earnings", {
        "symbol": ticker, "from": today.isoformat(),
        "to": (today + timedelta(days=horizon_days)).isoformat()})
    if payload is None:
        # DO NOT cache a failure as an empty calendar, and do not let the
        # caller read [] as "nothing scheduled".
        raise CatalystFetchError(
            f"{ticker}: earnings calendar not retrieved — "
            f"{FETCH_FAILURES.get(f'calendar/earnings:{ticker}', 'unknown')}")
    out = []
    for row in ((payload or {}).get("earningsCalendar") or []):
        d = row.get("date")
        if _days_away(d) is None or _days_away(d) < 0:
            continue
        out.append(_event(
            "earnings", d, source="finnhub/calendar/earnings",
            expectedness="scheduled", affected_metric="EPS and revenue vs "
                                                      "consensus",
            next_observable=f"reported EPS vs estimate "
                            f"{row.get('epsEstimate')}",
            detail={"hour": row.get("hour"), "quarter": row.get("quarter"),
                    "year": row.get("year"),
                    "eps_estimate": row.get("epsEstimate"),
                    "revenue_estimate": row.get("revenueEstimate")}))
    out.sort(key=lambda e: e["event_time"] or "9999")
    cache_set(key, out)
    return out


def surprise_history(ticker: str) -> dict:
    """How this name has handled the catalyst it faces most often."""
    key = f"pm_catalyst_surp:{ticker}"
    hit = cache_get(key, CACHE_TTL)
    if hit is not None:
        return hit
    rows = _finnhub("stock/earnings", {"symbol": ticker}) or []
    beats = [r for r in rows if (r.get("surprise") or 0) > 0]
    out = {"available": bool(rows), "quarters": len(rows),
           "beat_rate": round(len(beats) / len(rows), 3) if rows else None,
           "last": rows[0] if rows else None,
           "source": "finnhub/stock/earnings"}
    cache_set(key, out)
    return out


def book_catalysts(position: Any) -> list[dict]:
    """Catalysts a human wrote into the book file.

    The only route by which a PDUFA date reaches this engine today. A YAML
    entry is `{date: 2026-11-14, kind: pdufa, what: "govorestat action date"}`.
    """
    out = []
    for c in (getattr(position, "catalysts", None) or []):
        if not isinstance(c, dict):
            continue
        out.append(_event(
            str(c.get("kind", "manual")), c.get("date"),
            source="book file (human-entered)",
            expectedness=str(c.get("expectedness", "scheduled")),
            affected_metric=str(c.get("what", "unspecified")),
            direction=c.get("direction"),
            confidence=str(c.get("confidence", "human-entered, unverified")),
            next_observable=str(c.get("next_observable", "")),
            detail=dict(c)))
    return out


def catalysts_for(ticker: str, position: Any = None, *,
                  with_surprises: bool = True) -> dict:
    events = earnings_events(ticker) + book_catalysts(position)
    events.sort(key=lambda e: e["event_time"] or "9999")
    out = {"ticker": ticker, "events": events, "next": events[0] if events else None,
           "count": len(events)}
    if with_surprises:
        out["earnings_history"] = surprise_history(ticker)
    return out


def calendar(tickers: list[str], positions: Optional[dict] = None) -> dict:
    """The whole book's catalysts, bucketed the way a morning brief reads them."""
    positions = positions or {}
    buckets: dict[str, list] = {"0_7d": [], "8_30d": [], "31_90d": [],
                                "beyond_90d": []}
    seen, failures, blind = 0, [], []
    for t in tickers:
        try:
            c = catalysts_for(t, positions.get(t), with_surprises=False)
        except CatalystFetchError as e:
            # this ticker's calendar is UNKNOWN, not empty
            blind.append({"ticker": t, "error": str(e)[:140]})
            continue
        except Exception as e:                   # noqa: BLE001
            logger.warning("catalysts for %s failed: %s", t, e)
            failures.append({"ticker": t, "error": str(e)[:100]})
            continue
        seen += 1
        for ev in c["events"]:
            d = ev["days_away"]
            if d is None:
                continue
            row = {"ticker": t, **ev}
            if d <= 7:
                buckets["0_7d"].append(row)
            elif d <= 30:
                buckets["8_30d"].append(row)
            elif d <= 90:
                buckets["31_90d"].append(row)
            else:
                buckets["beyond_90d"].append(row)
    for b in buckets.values():
        b.sort(key=lambda e: e["days_away"])
    total = sum(len(b) for b in buckets.values())
    return {
        **buckets,
        "tickers_checked": seen,
        "tickers_blind": [b["ticker"] for b in blind],
        "events_found": total,
        "failures": failures + blind,
        "coverage": coverage(seen, total, blind=blind,
                             requested=len(tickers)),
    }


def coverage(tickers_checked: int = 0, events_found: int = 0, *,
             blind: Optional[list] = None, requested: int = 0) -> dict:
    """What an empty calendar does and does not mean.

    An empty bucket here means "no EARNINGS date inside the window and nothing
    written into the book file". It does NOT mean nothing is coming. For a
    clinical name, the events that matter are precisely the ones in `uncovered`.
    """
    from backend.config import api_keys
    blind = blind or []
    return {
        "covered": ["scheduled earnings dates (Finnhub, free tier)",
                    "earnings estimate + surprise history (Finnhub)",
                    "anything hand-entered under `catalysts:` in the book"],
        "uncovered": list(UNCOVERED),
        "vendor_available": api_keys.has("finnhub"),
        "tickers_checked": tickers_checked,
        "tickers_requested": requested or tickers_checked,
        "tickers_not_retrieved": len(blind),
        "not_retrieved": blind,
        "events_found": events_found,
        "grade": ("v0 — earnings only" if not blind else
                  f"v0 DEGRADED — {len(blind)} of "
                  f"{requested or tickers_checked} tickers were NOT retrieved; "
                  f"their calendars are UNKNOWN, not empty"),
        "warning": ("an empty calendar means no EARNINGS date was found in the "
                    "window. It is NOT evidence that nothing is scheduled: "
                    "PDUFA dates, readouts, offerings and lockups have no "
                    "entitled source here and must be entered by hand."),
    }
