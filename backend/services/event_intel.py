"""
Aegis Finance — EVENT-INTEL, the descriptive news brain
=======================================================

Upgrades news from "headlines + summary" to STRUCTURED EVENTS with honest
context, per the binding acceptance spec in
docs/research/ROADMAP_2026-07-29_POST_FREEZE.md (2026-07-29B amendments).

Typed event:
    {scope, event_type, direction, direction_basis, direction_relative_to,
     source, timestamp, title, extraction: {tier, method}, context}

The playbook, enforced BY CONSTRUCTION:
  - The LLM classifies into ENUMS only (event_type, direction, basis).
    It never writes prose, so it can never write advice. Every rendered
    sentence on this surface is a deterministic template.
  - Direction is always relative to the named scope entity, never the market.
  - Context cards attach ONLY already-measured stats with N-counts; the
    default is {"status": "none_measured"} — "no measured base rate".
  - A failed feed is DISCLOSED unavailable; "no events found" and
    "extraction unavailable" are different values (never fabricate calm).
  - Nothing here arms anything. The moment any event output feeds an
    allocation, it needs pre-registration (CANON §6).

Direction taxonomy (pre-committed 2026-07-29B):
  EXPLICIT — stated by the structured source itself (8-K item code with an
             inherent direction; an earnings beat/miss with numbers).
  IMPLIED  — inferred from headline language; always tier-labeled.
  NEUTRAL  — event carries no direction (scheduled earnings date).
  UNKNOWN  — unclassifiable; said so, never guessed.

Extraction tier = PARSE FIDELITY (HIGH/MEDIUM/LOW/FAILED), never an outcome
probability — outcome-confidence is barred by the D4 closure ruling.
"""

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from backend.config import config
from backend.observability import record_event_extraction

logger = logging.getLogger(__name__)

_CFG = config["event_intel"]

_ALLOWED_EVENT_TYPES = {
    "earnings", "guidance", "regulatory", "ma", "management_change",
    "bankruptcy", "debt", "product", "legal", "macro", "other",
}
_ALLOWED_DIRECTIONS = {"positive", "negative", "neutral", "unknown"}

# Advice/forecast language must never appear in anything this module renders.
# Templates are deterministic, so this is a belt-and-suspenders guard applied
# to every event title imported from external sources into context prose.
_FORBIDDEN_RE = re.compile(
    r"\b(buy(?!back)|sell(?!-?off|ing pressure)|should (?:buy|sell|hold)|"
    r"opportunity to|suggests?|implies|"
    r"will likely|expect(?:ed)? to (?:rise|fall|rally|drop))\b",
    re.IGNORECASE,
)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _llm_disabled() -> bool:
    return os.environ.get("AEGIS_DISABLE_EVENT_LLM", "0") == "1"


def _make_event(
    *,
    scope: str,
    event_type: str,
    direction: str,
    basis: str,
    feed: str,
    title: str,
    timestamp: Optional[str],
    url: Optional[str] = None,
    publisher: Optional[str] = None,
    tier: str = "LOW",
    method: str = "deterministic",
    context: Optional[dict] = None,
) -> dict:
    """Assemble one typed event; invalid enums degrade to honest unknowns."""
    if event_type not in _ALLOWED_EVENT_TYPES:
        event_type = "other"
    if direction not in _ALLOWED_DIRECTIONS:
        direction, basis, tier = "unknown", "UNKNOWN", "FAILED"
    return {
        "scope": scope,
        "event_type": event_type,
        "direction": direction,
        "direction_basis": basis,
        "direction_relative_to": scope,
        "source": {"feed": feed, "url": url, "publisher": publisher},
        "timestamp": timestamp,
        "title": title[:300] if title else "",
        "extraction": {"tier": tier, "method": method},
        "context": context or {"base_rate": {"status": "none_measured"}},
    }


# ── Canaries (per-feed, cached) ──────────────────────────────────────────────
# An empty 200 is not evidence of absence. Before trusting a feed's empty
# result for an arbitrary ticker, check that a known high-volume name returns
# SOMETHING; if even the canary is empty, the feed is suspect and every empty
# result from it is disclosed as unavailable rather than "no events".


def _canary_ok(feed: str) -> bool:
    from backend.cache import cache_get, cache_set

    key = f"event_intel:canary:{feed}"
    cached = cache_get(key, _CFG["canary_ttl"])
    if cached is not None:
        return bool(cached["ok"])

    ticker = _CFG["canary_ticker"]
    ok = False
    try:
        if feed == "yfinance_news":
            from backend.services.news_intelligence import fetch_stock_news
            ok = len(fetch_stock_news(ticker, max_items=3)) > 0
        elif feed == "edgar_8k":
            from backend.services.edgar_events import fetch_events_for_ticker
            ok = len(fetch_events_for_ticker(ticker, days_back=90)) > 0
        elif feed == "earnings":
            from backend.services.earnings_intelligence import get_earnings_summary
            summary = get_earnings_summary(ticker)
            ok = "error" not in summary and bool(summary.get("earnings_surprises"))
    except Exception as e:
        logger.warning("EVENT-INTEL canary for %s failed: %s", feed, e)
        ok = False

    if not ok:
        logger.warning(
            "EVENT-INTEL canary EMPTY for feed %s (ticker %s) — feed marked "
            "suspect; empty results disclosed unavailable, not 'no events'",
            feed, ticker,
        )
    cache_set(key, {"ok": ok})
    return ok


# ── News headline classification ─────────────────────────────────────────────


def _classify_keywords(title: str) -> tuple[str, str, str, str]:
    """Deterministic fallback: (event_type, direction, basis, tier)."""
    low = title.lower()
    direction = "unknown"
    for kw in _CFG["positive_keywords"]:
        if kw in low:
            direction = "positive"
            break
    if direction == "unknown":
        for kw in _CFG["negative_keywords"]:
            if kw in low:
                direction = "negative"
                break

    event_type = "other"
    if any(w in low for w in ("earnings", "revenue", "profit", "eps", "quarter")):
        event_type = "earnings"
    elif any(w in low for w in ("guidance", "outlook", "forecast")):
        event_type = "guidance"
    elif any(w in low for w in ("fda", "regulator", "antitrust", "sec ", "doj")):
        event_type = "regulatory"
    elif any(w in low for w in ("acquire", "acquisition", "merger", "takeover", "deal")):
        event_type = "ma"
    elif any(w in low for w in ("ceo", "cfo", "resigns", "appoints", "steps down")):
        event_type = "management_change"
    elif any(w in low for w in ("lawsuit", "settle", "court", "probe", "investigation")):
        event_type = "legal"
    elif any(w in low for w in ("launch", "unveil", "recall", "product")):
        event_type = "product"

    if direction == "unknown":
        return event_type, "unknown", "UNKNOWN", "LOW"
    return event_type, direction, "IMPLIED", "LOW"


def _classify_llm(ticker: str, titles: list[str]) -> Optional[list[dict]]:
    """LLM classification into enums only. None -> caller uses keywords.

    The LLM sees headlines and returns {event_type, direction, basis} per
    headline. It writes NO prose and is never asked about the future.
    """
    if _llm_disabled():
        return None
    try:
        from backend.services import llm_analyzer
        if not llm_analyzer.is_available():
            return None

        system = (
            "You classify financial news headlines about a single company into "
            "typed events. Reply with EXACTLY this JSON (no markdown fences): "
            '{"events": [{"i": <headline index>, '
            '"event_type": "earnings|guidance|regulatory|ma|management_change|'
            'bankruptcy|debt|product|legal|macro|other", '
            '"direction": "positive|negative|neutral|unknown", '
            '"basis": "EXPLICIT|IMPLIED"}]}. '
            "direction is for the named company only, as stated or implied by "
            "the headline itself. If a headline is not primarily about the "
            "named company, use direction unknown. EXPLICIT only when the "
            "headline states a realized outcome about the company itself "
            "(beat/missed/filed/approved/sued/recalled) — announcements and "
            "plans are IMPLIED at most. If a headline is ambiguous use "
            "direction unknown. Never predict, never advise, never add fields."
        )
        numbered = "\n".join(f"{i}: {t}" for i, t in enumerate(titles))
        raw = llm_analyzer._call_llm(system, f"Company: {ticker}\n{numbered}")
        if not raw:
            return None
        text = raw.strip().strip("`")
        parsed = json.loads(text[text.find("{"): text.rfind("}") + 1])
        events = parsed.get("events")
        if not isinstance(events, list):
            return None
        out: list[dict] = []
        for item in events:
            i = item.get("i")
            if not isinstance(i, int) or not (0 <= i < len(titles)):
                continue
            out.append({
                "i": i,
                "event_type": str(item.get("event_type", "other")),
                "direction": str(item.get("direction", "unknown")),
                "basis": str(item.get("basis", "IMPLIED")).upper(),
            })
        return out or None
    except Exception as e:
        logger.warning("EVENT-INTEL LLM classification failed (%s) — keyword fallback", e)
        return None


def _news_block(ticker: str) -> dict:
    """Headline feed -> typed events. Independent degradation."""
    try:
        from backend.services.news_intelligence import fetch_stock_news

        items = fetch_stock_news(ticker, max_items=_CFG["max_headlines_per_ticker"])
        if not items:
            if _canary_ok("yfinance_news"):
                return {"status": "ok", "events": []}  # feed healthy: genuinely quiet
            return {"status": "unavailable", "error": "news feed suspect (canary empty)"}

        cutoff = _now_utc() - timedelta(days=_CFG["news_window_days"])
        recent = []
        for it in items:
            ts = _parse_ts(it.get("published"))
            if ts is None or ts >= cutoff:
                recent.append((it, ts))
        titles = [it["title"] for it, _ in recent if it.get("title")]

        llm_labels = _classify_llm(ticker, titles) if titles else None
        by_index = {lab["i"]: lab for lab in llm_labels} if llm_labels else {}

        events = []
        for idx, (it, ts) in enumerate(recent):
            title = it.get("title") or ""
            if not title:
                continue
            lab = by_index.get(idx)
            if lab is not None:
                basis = lab["basis"] if lab["basis"] in ("EXPLICIT", "IMPLIED") else "IMPLIED"
                if lab["direction"] in ("neutral", "unknown"):
                    basis = lab["direction"].upper() if lab["direction"] == "neutral" else "UNKNOWN"
                events.append(_make_event(
                    scope=ticker, event_type=lab["event_type"],
                    direction=lab["direction"], basis=basis,
                    feed="yfinance_news", title=title,
                    timestamp=ts.isoformat(timespec="seconds") if ts else None,
                    url=it.get("link"), publisher=it.get("publisher"),
                    tier="MEDIUM", method="llm",
                ))
            else:
                etype, direction, basis, tier = _classify_keywords(title)
                events.append(_make_event(
                    scope=ticker, event_type=etype, direction=direction,
                    basis=basis, feed="yfinance_news", title=title,
                    timestamp=ts.isoformat(timespec="seconds") if ts else None,
                    url=it.get("link"), publisher=it.get("publisher"),
                    tier=tier, method="keyword",
                ))
        return {"status": "ok", "events": events}
    except Exception as e:
        logger.warning("EVENT-INTEL news block failed for %s: %s", ticker, e)
        return {"status": "unavailable", "error": str(e)}


def _parse_ts(value) -> Optional[datetime]:
    """Defensive parse of yfinance 'published' (epoch, ISO, or absent)."""
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc)
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, OSError, OverflowError):
        return None


# ── EDGAR 8-K feed ───────────────────────────────────────────────────────────


def _edgar_block(ticker: str) -> dict:
    """8-K filings -> typed events. Structured source: tier HIGH, and the
    item code itself carries direction only where the taxonomy says so."""
    try:
        from backend.services.edgar_events import fetch_events_for_ticker

        filings = fetch_events_for_ticker(
            ticker, days_back=_CFG["edgar_days_back"], only_8k=True)
        if not filings:
            if _canary_ok("edgar_8k"):
                return {"status": "ok", "events": []}
            return {"status": "unavailable", "error": "EDGAR feed suspect (canary empty)"}

        item_dir = _CFG["edgar_item_direction"]
        events = []
        for f in filings:
            directions = {item_dir[i] for i in f.items if i in item_dir}
            if len(directions) == 1:
                direction, basis = directions.pop(), "EXPLICIT"
            else:
                direction, basis = "unknown", "UNKNOWN"
            etype = f.event_types[0] if f.event_types else "other"
            if etype not in _ALLOWED_EVENT_TYPES:
                etype = "other"
            events.append(_make_event(
                scope=ticker, event_type=etype, direction=direction,
                basis=basis, feed="edgar_8k",
                title=f"8-K filed (items {', '.join(f.items)})",
                timestamp=f.filed, url=f.primary_doc_url, publisher="SEC EDGAR",
                tier="HIGH", method="deterministic",
                context={
                    "base_rate": {"status": "none_measured"},
                    "materiality": f.materiality,
                    "note": ("Filing-conditioned cohorts are selection-contaminated "
                             "(NEGATIVE_RESULTS §20) — no drift stat is attached."),
                },
            ))
        return {"status": "ok", "events": events}
    except Exception as e:
        logger.warning("EVENT-INTEL edgar block failed for %s: %s", ticker, e)
        return {"status": "unavailable", "error": str(e)}


# ── Earnings feed ────────────────────────────────────────────────────────────


def _earnings_block(ticker: str) -> dict:
    """Earnings results/schedule -> typed events with MEASURED context.

    The one place a real base rate exists today: the ticker's own measured
    surprise history (beat_rate over N quarters). Attached with its N.
    """
    try:
        from backend.services.earnings_intelligence import get_earnings_summary

        summary = get_earnings_summary(ticker)
        if "error" in summary:
            if _canary_ok("earnings"):
                return {"status": "ok", "events": []}
            return {"status": "unavailable", "error": "earnings feed suspect (canary empty)"}

        events = []
        window = timedelta(days=_CFG["earnings_window_days"])
        now = _now_utc()

        surprises = summary.get("earnings_surprises") or []
        if surprises:
            latest = surprises[0]
            beat = latest.get("beat")
            surprise_pct = latest.get("surprise_pct")
            n_q = len(surprises)
            base_rate = {"status": "none_measured"}
            if summary.get("beat_rate") is not None:
                base_rate = {
                    "status": "measured",
                    "stat": "beat_rate",
                    "value": summary["beat_rate"],
                    "n": n_q,
                    "window": f"last {n_q} reported quarters",
                }
            if beat is not None:
                events.append(_make_event(
                    scope=ticker, event_type="earnings",
                    direction="positive" if beat else "negative",
                    basis="EXPLICIT", feed="earnings",
                    title=(f"Reported EPS {'beat' if beat else 'missed'} estimates"
                           + (f" ({surprise_pct:+.1f}% surprise)"
                              if isinstance(surprise_pct, (int, float)) else "")),
                    timestamp=str(latest.get("quarter") or ""),
                    publisher="yfinance",
                    tier="HIGH", method="deterministic",
                    context={"base_rate": base_rate},
                ))

        next_date = summary.get("next_earnings_date")
        days_until = summary.get("days_until_earnings")
        if next_date and isinstance(days_until, (int, float)) \
                and 0 <= days_until <= window.days:
            events.append(_make_event(
                scope=ticker, event_type="earnings", direction="neutral",
                basis="NEUTRAL", feed="earnings",
                title=f"Earnings scheduled {next_date} ({int(days_until)}d)",
                timestamp=str(next_date), publisher="yfinance",
                tier="HIGH", method="deterministic",
            ))
        _ = now  # window anchor documented; date math uses provider's days_until
        return {"status": "ok", "events": events}
    except Exception as e:
        logger.warning("EVENT-INTEL earnings block failed for %s: %s", ticker, e)
        return {"status": "unavailable", "error": str(e)}


# ── Public API ───────────────────────────────────────────────────────────────


def get_ticker_events(ticker: str) -> dict:
    """All typed events for one ticker, per-feed degradation disclosed."""
    feeds = {
        "yfinance_news": _news_block(ticker),
        "edgar_8k": _edgar_block(ticker),
        "earnings": _earnings_block(ticker),
    }
    events: list[dict] = []
    for block in feeds.values():
        events.extend(block.get("events", []))
    # Titles are external text — scrub any advice-shaped phrasing before serving.
    for ev in events:
        if ev["title"] and _FORBIDDEN_RE.search(ev["title"]):
            ev["title"] = _FORBIDDEN_RE.sub("[…]", ev["title"])
    events.sort(key=lambda e: e.get("timestamp") or "", reverse=True)

    feed_statuses = {
        name: {"status": b["status"], **({"error": b["error"]} if b.get("error") else {})}
        for name, b in feeds.items()
    }
    record_event_extraction(events, feed_statuses)

    unavailable = [n for n, b in feeds.items() if b["status"] != "ok"]
    return {
        "ticker": ticker,
        "events": events,
        "feeds": feed_statuses,
        "unavailable_feeds": unavailable,
        "generated_at": _now_utc().isoformat(timespec="seconds"),
        "disclaimer": (
            "Descriptive event log. Direction is what the source stated or "
            "implied about the named company — not a forecast, not a signal, "
            "not advice. Where no measured base rate exists, none is shown."
        ),
    }


def get_events_for_brief(tickers: list[str]) -> dict:
    """Compact cross-ticker event digest for the daily brief.

    Prefers already-warm per-ticker caches; fetches at most
    max_tickers_per_brief tickers. Never raises.
    """
    from backend.cache import cache_get, cache_set

    capped = tickers[: _CFG["max_tickers_per_brief"]]
    all_events: list[dict] = []
    unavailable: dict[str, list[str]] = {}
    for t in capped:
        key = f"event_intel:{t}"
        payload = cache_get(key, _CFG["cache_ttl"])
        if payload is None:
            try:
                payload = get_ticker_events(t)
                cache_set(key, payload)
            except Exception as e:  # brief is additive — never block it
                logger.warning("EVENT-INTEL brief fetch failed for %s: %s", t, e)
                unavailable[t] = ["all"]
                continue
        all_events.extend(payload["events"])
        if payload["unavailable_feeds"]:
            unavailable[t] = payload["unavailable_feeds"]

    tiers = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "FAILED": 3}
    all_events.sort(
        key=lambda e: (tiers.get(e["extraction"]["tier"], 9),
                       -(len(e.get("timestamp") or ""))))
    directed = [e for e in all_events if e["direction"] in ("positive", "negative")]
    return {
        "events": all_events[:12],
        "n_events": len(all_events),
        "n_directed": len(directed),
        "unavailable": unavailable,  # {} means every feed answered
    }
