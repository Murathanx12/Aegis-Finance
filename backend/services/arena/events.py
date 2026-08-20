"""EVENT_CONTEXT — the news, filings and earnings the LLM was never shown.

WHAT WAS MISSING
================
The arena's LLM saw a numeric snapshot: close, ret21, vol63, streak, PIT
scores. It was asked to revise a belief about a company while being told
nothing about the company. Meanwhile `backend/services/event_intel.py` — a
typed event feed over yfinance news, EDGAR 8-Ks and earnings, with per-feed
degradation already disclosed — had exactly ONE caller, `daily_brief.py`,
which nothing schedules. Live prod reports `events_extracted: 0` and
`last_extraction_at: null`. It is the 17th collector feeding nobody.

WHY THIS MODULE EXISTS RATHER THAN A DIRECT CALL
================================================
`get_ticker_events` fetches LIVE at call time. That is fine for PIT — it runs
after the close, for a decision that fills at the next open — but it is **not
reproducible**: replaying the day next month fetches different news. An
information state that cannot be replayed cannot grade the decision made from
it, which is the whole contract `information_state_hash` carries.

So the context is FROZEN: fetched once, normalised, stamped with every
source's own timestamp and each feed's status, and written into the day state
BEFORE any decision. What the model saw is then a fact on disk rather than a
claim about what the internet said that evening.

BOUNDED BY CONSTRUCTION. Only the names the belief review will actually look
at get fetched (`max_names`), because this is network I/O inside the 17:45
pass and an unbounded fetch over a 400-name scan would be a different kind of
outage.

ABLATION. `event_context` is a per-book flag, so LLM_PERCEPTION_v1 (numeric
only) and LLM_EVENTS_v1 (numeric + events) differ by exactly one rule and the
question "does the news buy anything" has an arm rather than an opinion.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

#: Fields kept per event. The raw feed carries more; this is what a belief
#: review can act on, and trimming it here keeps the frozen state readable.
EVENT_FIELDS = ("title", "timestamp", "direction", "category", "source",
                "tier")

MAX_EVENTS_PER_NAME = 6


def _norm_event(ev: dict) -> dict:
    ext = ev.get("extraction") or {}
    return {
        "title": str(ev.get("title") or "")[:240],
        "timestamp": ev.get("timestamp"),
        "direction": ev.get("direction"),
        "category": ev.get("category"),
        "source": ev.get("source") or ev.get("feed"),
        "tier": ext.get("tier"),
        "method": ext.get("method"),
    }


def fetch(tickers: list[str], *, max_names: int = 12,
          as_of: str | None = None) -> dict:
    """Frozen event context for `tickers`. Never raises.

    A feed that is down is recorded as DOWN per name, not omitted: "no events"
    and "the feed did not answer" are different facts and only one of them is
    about the company.
    """
    out: dict = {
        "fetched_at": (as_of or datetime.now(timezone.utc)
                       .isoformat(timespec="seconds")),
        "requested_n": len(tickers),
        "fetched_n": 0,
        "names": {},
        "feed_health": {},
        "errors": {},
    }
    try:
        from backend.services.event_intel import get_ticker_events
    except ImportError as exc:                                  # noqa: BLE001
        out["errors"]["_import"] = str(exc)
        logger.warning("ARENA event context unavailable: %s", exc)
        return out

    for t in tickers[:max_names]:
        try:
            payload = get_ticker_events(t)
        except Exception as exc:                                # noqa: BLE001
            out["errors"][t] = f"{type(exc).__name__}: {exc}"
            logger.warning("ARENA event context failed for %s: %s", t, exc)
            continue
        events = [_norm_event(e) for e in
                  (payload.get("events") or [])[:MAX_EVENTS_PER_NAME]]
        out["names"][t] = {
            "events": events,
            "n_events": len(payload.get("events") or []),
            "unavailable_feeds": payload.get("unavailable_feeds") or [],
            "generated_at": payload.get("generated_at"),
        }
        out["fetched_n"] += 1
        for feed, st in (payload.get("feeds") or {}).items():
            bucket = out["feed_health"].setdefault(
                feed, {"ok": 0, "degraded": 0})
            bucket["ok" if st.get("status") == "ok" else "degraded"] += 1
    if out["fetched_n"] == 0 and tickers:
        # Loud: an empty context and a context nobody fetched look identical
        # downstream, and the LLM would silently be back to numbers only.
        logger.warning("ARENA event context: 0 of %d names returned anything "
                       "— the belief review runs NUMERIC-ONLY this session",
                       min(len(tickers), max_names))
        out["status"] = "empty"
    else:
        out["status"] = "ok"
    return out


def for_name(context: dict, ticker: str) -> dict:
    """What the prompt gets for one name, including the honest empty case."""
    block = (context or {}).get("names", {}).get(ticker)
    if block is None:
        return {"events": [], "coverage": "NOT_FETCHED",
                "note": "no event context was retrieved for this name"}
    if not block["events"]:
        return {"events": [], "coverage": "FETCHED_NO_EVENTS",
                "unavailable_feeds": block.get("unavailable_feeds") or [],
                "note": ("the feeds answered and reported nothing for this "
                         "name — that is different from not having looked")}
    return {"events": block["events"], "coverage": "FETCHED",
            "n_events_total": block["n_events"],
            "unavailable_feeds": block.get("unavailable_feeds") or []}
