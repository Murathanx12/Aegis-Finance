"""
Daily Brief — "what happened today, and how does it touch YOUR stocks"
========================================================================

The user-facing companion to the brain digest: one endpoint that assembles
today's market tape (indices, oil, gold, rates, VIX), the geopolitical news
read (GDELT conflict/event scores), and the user's own tickers (moves +
headlines), then has the LLM write a three-part brief:

    What happened  ·  How it may affect your holdings  ·  Risks to watch

Pipeline shape borrowed from ZhuLinsen/daily_stock_analysis (MIT) — per-ticker
fan-out feeding one fixed-schema LLM report; prompt contract adapted from
FinGPT-Forecaster (MIT). Everything degrades gracefully: without an LLM key a
deterministic template is served; without GDELT the geopolitical block says so.

Honesty constraints: descriptive only — moves, tendencies, and risks; never
buy/sell language (the LLM prompt forbids it; the template never had it).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from backend.cache import cache_peek

logger = logging.getLogger(__name__)

# Market tape shown in every brief: (label, yahoo symbol)
_MARKET_ROWS = [
    ("S&P 500", "SPY"),
    ("Nasdaq 100", "QQQ"),
    ("Small caps", "IWM"),
    ("VIX", "^VIX"),
    ("Oil (WTI)", "CL=F"),
    ("Gold", "GC=F"),
    ("10Y yield", "^TNX"),
    ("Dollar index", "DX-Y.NYB"),
]

_MAX_USER_TICKERS = 15
_HEADLINE_TICKERS = 5   # fetch headlines only for the biggest movers
_DISCLAIMER = (
    "Educational context from public data — not financial advice. "
    "Moves and tendencies are descriptive, not recommendations."
)


def _changes(series) -> tuple[float | None, float | None]:
    """(1-day %, 5-day %) from a close series; None when not computable."""
    try:
        s = series.dropna()
        if len(s) < 2:
            return None, None
        last = float(s.iloc[-1])
        d1 = (last / float(s.iloc[-2]) - 1) * 100
        d5 = (last / float(s.iloc[-6]) - 1) * 100 if len(s) >= 6 else None
        return round(d1, 2), (round(d5, 2) if d5 is not None else None)
    except Exception:
        return None, None


def _fetch_all_closes(symbols: list[str]) -> dict:
    """ONE batched download for every symbol in the brief."""
    from backend.services.data_fetcher import _fetch_batch_yahoo

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=45)
    try:
        return _fetch_batch_yahoo(
            symbols, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
        )
    except Exception as e:
        logger.warning("daily brief batch fetch failed: %s", e)
        return {}


def _geopolitical_block() -> dict:
    """GDELT read — prefer the already-cached market-news reading."""
    conflict = event_score = event_label = None
    gdelt = {}

    news, _age = cache_peek("news_market", 6 * 3600)
    if news:
        gdelt = news.get("gdelt") or {}
        event = news.get("event_score") or {}
        event_score, event_label = event.get("score"), event.get("label")
    else:
        try:
            from backend.services.news_intelligence import (
                fetch_gdelt_signals, compute_event_score,
            )
            gdelt = fetch_gdelt_signals()
            event = compute_event_score(gdelt)
            event_score, event_label = event.get("score"), event.get("label")
        except Exception as e:
            logger.warning("daily brief GDELT read failed: %s", e)

    # A failed GDELT fetch returns a ZERO-filled default (empty raw_data) —
    # reporting that as "quiet" would fabricate calm. Only trust the score
    # when the underlying timeline actually has data.
    if (gdelt.get("raw_data") or {}).get("conflict"):
        conflict = gdelt.get("conflict_score")

    note = None
    if conflict is None:
        note = "Geopolitical read unavailable right now (news feed throttled)."
    else:
        if conflict >= 0.6:
            note = (
                "Geopolitical news flow is ELEVATED. In past episodes like this, "
                "energy and defense names tended to firm while travel, airlines "
                "and rate-sensitive sectors lagged — a historical tendency, not "
                "a forecast."
            )
        elif conflict >= 0.35:
            note = "Geopolitical news flow is moderately elevated."
        else:
            note = "Geopolitical news flow is quiet."

    return {
        "conflict_score": conflict,
        "event_score": event_score,
        "event_label": event_label,
        "note": note,
    }


def _headlines_for(ticker: str) -> list[dict]:
    """Up to 3 headlines; served from the news cache when warm."""
    cached, _age = cache_peek(f"news_stock:{ticker}", 6 * 3600)
    items = None
    if cached:
        items = cached.get("news")
    if items is None:
        try:
            from backend.services.news_intelligence import fetch_stock_news
            items = fetch_stock_news(ticker, max_items=3)
        except Exception as e:
            # Missing headlines render as an empty list, not fabricated news;
            # still log so a dead news path is visible in prod logs.
            logger.warning("headlines fetch failed for %s: %s", ticker, e)
            items = []
    return [
        {"title": n.get("title", ""), "publisher": n.get("publisher"),
         "link": n.get("link")}
        for n in (items or [])[:3] if n.get("title")
    ]


def _template_summary(market: list[dict], geo: dict, yours: list[dict]) -> dict:
    """Deterministic fallback when no LLM is available."""
    spy = next((m for m in market if m["ticker"] == "SPY"), None)
    oil = next((m for m in market if m["ticker"] == "CL=F"), None)
    vix = next((m for m in market if m["ticker"] == "^VIX"), None)

    bits = []
    if spy and spy["change_1d_pct"] is not None:
        direction = "rose" if spy["change_1d_pct"] >= 0 else "fell"
        bits.append(f"The S&P 500 {direction} {abs(spy['change_1d_pct']):.1f}% today")
    if oil and oil["change_1d_pct"] is not None and abs(oil["change_1d_pct"]) >= 1:
        bits.append(f"oil moved {oil['change_1d_pct']:+.1f}%")
    if vix and vix["change_1d_pct"] is not None and abs(vix["change_1d_pct"]) >= 5:
        bits.append(f"the VIX moved {vix['change_1d_pct']:+.0f}%")
    what = (", ".join(bits) + ".") if bits else "Market data was unavailable today."
    if geo.get("note"):
        what += f" {geo['note']}"

    movers = [t for t in yours if t["change_1d_pct"] is not None]
    movers.sort(key=lambda t: abs(t["change_1d_pct"]), reverse=True)
    if movers:
        top = ", ".join(f"{t['ticker']} {t['change_1d_pct']:+.1f}%" for t in movers[:4])
        impact = f"Among your tickers, the biggest moves today: {top}."
    else:
        impact = "Add tickers to your watchlist or portfolio to see how the day touched them."

    risks = "Watch the VIX, oil, and 10-year yield rows above — sharp moves there tend to lead sector rotation."

    return {
        "what_happened": what,
        "impact_on_holdings": impact,
        "risks_to_watch": risks,
        "sentiment": None,
        "source": "template",
    }


def build_daily_brief(tickers: list[str]) -> dict:
    """Assemble the brief. `tickers` = the user's watchlist/portfolio symbols."""
    tickers = [t.upper() for t in tickers][:_MAX_USER_TICKERS]
    market_symbols = [sym for _label, sym in _MARKET_ROWS]
    closes = _fetch_all_closes(list(dict.fromkeys(market_symbols + tickers)))

    market = []
    for label, sym in _MARKET_ROWS:
        d1, d5 = _changes(closes.get(sym)) if sym in closes else (None, None)
        market.append({"label": label, "ticker": sym,
                       "change_1d_pct": d1, "change_5d_pct": d5})

    yours = []
    for t in tickers:
        d1, d5 = _changes(closes.get(t)) if t in closes else (None, None)
        yours.append({"ticker": t, "change_1d_pct": d1, "change_5d_pct": d5,
                      "headlines": []})

    # Headlines only for the biggest movers — keeps the fan-out bounded.
    movers = sorted(
        (y for y in yours if y["change_1d_pct"] is not None),
        key=lambda y: abs(y["change_1d_pct"]), reverse=True,
    )[:_HEADLINE_TICKERS]
    for y in movers:
        y["headlines"] = _headlines_for(y["ticker"])

    geo = _geopolitical_block()

    status, _age = cache_peek("market_status", 6 * 3600)
    regime = {
        "regime": (status or {}).get("regime"),
        "risk_score": (status or {}).get("risk_score"),
    }

    summary = None
    try:
        from backend.services.llm_analyzer import is_available, summarize_daily_brief
        if is_available():
            payload = json.dumps({
                "market": market,
                "geopolitical": geo,
                "regime": regime,
                "your_tickers": [
                    {k: v for k, v in y.items()} for y in yours
                ],
            }, separators=(",", ":"))
            summary = summarize_daily_brief(payload)
    except Exception as e:
        logger.warning("daily brief LLM summary failed: %s", e)
    if summary is None:
        summary = _template_summary(market, geo, yours)

    return {
        "date": datetime.now(timezone.utc).date().isoformat(),
        "horizon": "today",
        "market": market,
        "geopolitical": geo,
        "regime": regime,
        "your_tickers": yours,
        "summary": summary,
        "disclaimer": _DISCLAIMER,
    }
