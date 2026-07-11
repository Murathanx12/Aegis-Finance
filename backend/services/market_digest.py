"""
Daily market-context digest — the engine's news reading, in brain-ingestible form.
===================================================================================

Assembles ONE markdown document per day from readings the engine has already
computed (news + LLM summary, event score, market status/regime, fragility
composite) so the Optimus brain can ingest "what the engine saw today" the way
it ingests a git repo. Deterministic template; the only LLM text included is
the already-cached news summary (no new spend).

Honesty constraints: the digest is DESCRIPTIVE context — it reports readings
with their labels and never contains buy/sell language. Sections whose source
is not in cache say so explicitly (degraded ≠ fabricated).

Consumption: GET /api/brain/digest → {date, markdown, sections}. A local
script (optimus repo) fetches and saves it into a folder the brain ingests.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from backend.cache import cache_peek

logger = logging.getLogger(__name__)

_MAX_STALE = 24 * 3600  # readings older than a day are reported as missing


def _peek(key: str) -> tuple:
    """(value, age_minutes) — age is DISCLOSED in the digest, because a stale
    reading presented under today's date is the house failure mode."""
    value, age = cache_peek(key, _MAX_STALE)
    if value is None:
        return None, None
    return value, round((age or 0) / 60)


def _aged(title: str, age_min) -> str:
    if age_min is None or age_min <= 60:
        return f"## {title}"
    return f"## {title} — reading is {age_min} min old"


def build_market_digest() -> dict:
    """Assemble today's digest from cached readings only (never computes)."""
    today = datetime.now(timezone.utc).date().isoformat()
    sections: dict[str, dict] = {}
    lines: list[str] = [
        f"# Market context digest — {today}",
        "",
        "_Descriptive readings assembled by the Aegis engine from public data;"
        " context, not advice. Missing sections mean the source was not"
        " available — never assume a quiet reading._",
        "",
    ]

    news, news_age = _peek("news_market")
    if news:
        summary = (news.get("llm_summary") or {})
        event = news.get("event_score") or {}
        headlines = [n.get("title", "") for n in (news.get("news") or [])[:8]]
        sections["news"] = {
            "summary": summary.get("summary"),
            "sentiment": summary.get("sentiment"),
            "event_score": event.get("score"),
            "headlines": headlines,
            "age_minutes": news_age,
        }
        lines += [_aged("News", news_age)]
        if summary.get("summary"):
            lines += [f"**Engine summary ({summary.get('sentiment', '?')}):** "
                      f"{summary['summary']}", ""]
        if event:
            lines += [f"GDELT event score: {event.get('score')} "
                      f"({event.get('label', '')})", ""]
        if headlines:
            lines += ["Top headlines:"] + [f"- {h}" for h in headlines] + [""]
    else:
        sections["news"] = {"status": "not_available"}
        lines += ["## News", "_Not available (news cache empty)._", ""]

    status, status_age = _peek("market_status")
    if status:
        sections["market"] = {
            "regime": status.get("regime"),
            "risk_score": status.get("risk_score"),
            "vix": status.get("vix"),
            "sp500": status.get("sp500"),
            "age_minutes": status_age,
        }
        lines += [_aged("Market state", status_age),
                  f"- Regime: {status.get('regime')}",
                  f"- Risk score: {status.get('risk_score')} "
                  "(z-composite, >2 = elevated stress)",
                  f"- VIX: {status.get('vix')}",
                  f"- S&P 500: {status.get('sp500')}", ""]
    else:
        sections["market"] = {"status": "not_available"}
        lines += ["## Market state", "_Not available._", ""]

    signal, signal_age = _peek("market_signal")
    if signal:
        sections["signal"] = {"action": signal.get("action"),
                              "composite_score": signal.get("composite_score"),
                              "age_minutes": signal_age}
        lines += [_aged("Composite signal (measured, not advice)", signal_age),
                  f"- Reading: {signal.get('action')} "
                  f"(score {signal.get('composite_score')})", ""]
    else:
        sections["signal"] = {"status": "not_available"}

    try:
        # Last PERSISTED composite — the daily check's reading; never a live
        # recompute (this endpoint must stay cheap and cache-only).
        from backend.services.portfolio_intelligence.fragility import (
            latest_persisted_composite,
        )
        frag = latest_persisted_composite()
        if frag.get("composite") is not None:
            sections["fragility"] = {
                "composite": frag.get("composite"),
                "level": frag.get("level"),
                "evaluated_at": frag.get("evaluated_at"),
            }
            lines += ["## Structural fragility (descriptive composite)",
                      f"- Composite: {frag.get('composite')} "
                      f"({frag.get('level')}, as of {frag.get('evaluated_at')})",
                      ""]
        else:
            sections["fragility"] = {"status": "no_reading"}
            lines += ["## Structural fragility", "_No persisted reading yet._", ""]
    except Exception as e:
        sections["fragility"] = {"status": "not_available", "error": str(e)[:120]}
        lines += ["## Structural fragility", "_Not available._", ""]

    lines += ["---",
              "_Generated by Aegis Finance for the Optimus brain. All readings"
              " are pre-registered-or-descriptive; nothing here is a trade"
              " instruction._"]

    return {"date": today, "markdown": "\n".join(lines), "sections": sections}
