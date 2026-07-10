"""
Explain-the-move — evidence for "why did this stock just move?" (Branch 4)
==========================================================================

The user story: "one stock jumped 300% last month and I don't know why."
This module quantifies the move (how unusual vs the ticker's own history) and
assembles the checkable evidence around it — earnings, filings, news
sentiment, insider buying, options positioning — each block isolated and
status-carrying (a dead source says `unavailable`; it never silently
vanishes — the silent-fragility rule).

Narration is LAYERED, not load-bearing: with an LLM key (DeepSeek/Claude via
llm_analyzer) a short natural-language summary is generated FROM the evidence;
without one, a deterministic template renders the same evidence. Either way
the framing contract holds: **context, not causation — never advice, never
buy/sell.** The evidence dossier is the product; the LLM is garnish.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

EXPLAIN_LABEL = ("descriptive context for a price move — possible drivers, not "
                 "causation; not advice, no buy/sell signal")

MOVE_WINDOWS_TD = (1, 5, 21, 63)
ZSCORE_WINDOW_TD = 21          # the "recent move" being explained
ZSCORE_HISTORY_MIN = 120       # need this much history for an honest z-score


# ── The move itself (pure) ────────────────────────────────────────────────────


def compute_move_profile(close: pd.Series) -> dict:
    """Quantify the recent move: returns over standard windows + how unusual
    the trailing-21d return is vs the ticker's OWN rolling-21d history."""
    s = close.dropna()
    if len(s) < 2:
        return {"status": "insufficient_history"}
    out: dict = {"status": "ok", "last_price": round(float(s.iloc[-1]), 4),
                 "as_of": str(s.index[-1].date())}
    for w in MOVE_WINDOWS_TD:
        if len(s) > w:
            out[f"return_{w}d"] = round(float(s.iloc[-1] / s.iloc[-1 - w] - 1.0), 4)
        else:
            out[f"return_{w}d"] = None

    if len(s) >= ZSCORE_HISTORY_MIN:
        roll = s.pct_change(ZSCORE_WINDOW_TD).dropna()
        cur = float(roll.iloc[-1])
        hist = roll.iloc[:-1]
        sd = float(hist.std())
        if sd > 0:
            z = (cur - float(hist.mean())) / sd
            out["move_zscore_21d"] = round(float(z), 2)
            out["move_unusualness"] = (
                "extreme" if abs(z) >= 3 else "unusual" if abs(z) >= 2
                else "notable" if abs(z) >= 1 else "ordinary")
    return out


# ── Evidence assembly (each block isolated) ───────────────────────────────────

def _default_sources() -> dict[str, Callable]:
    """Live fetchers, resolved lazily so tests can inject and offline runs
    degrade block-by-block."""
    from backend.services.earnings_intelligence import get_earnings_summary
    from backend.services.edgar_events import fetch_events_for_ticker
    from backend.services.insider_form4 import fetch_open_market_buys
    from backend.services.insider_trading import compute_opportunistic_buy_score
    from backend.services.options_intelligence import get_iv_signal
    from backend.services.sentiment_analyzer import analyze_sentiment

    def _insider(ticker: str) -> dict:
        raw = fetch_open_market_buys(ticker, lookback_days=90)
        score = compute_opportunistic_buy_score(raw)
        return {**score, "n_buys": raw.get("n_buys"),
                "total_buy_value": raw.get("total_buy_value")}

    def _history(ticker: str) -> pd.Series:
        import yfinance as yf
        return yf.Ticker(ticker).history(period="2y")["Close"]

    return {
        "history": _history,
        "earnings": get_earnings_summary,
        "filings": lambda t: [e.to_dict() for e in
                              fetch_events_for_ticker(t, days_back=45)],
        "news_sentiment": analyze_sentiment,
        "insider": _insider,
        "options": get_iv_signal,
    }


def _block(name: str, fn: Callable, ticker: str) -> dict:
    try:
        v = fn(ticker)
        if isinstance(v, dict) and v.get("error"):
            return {"status": "unavailable", "error": str(v["error"])}
        return {"status": "ok", "data": v}
    except Exception as e:
        logger.warning("explain-move %s block failed for %s: %s", name, ticker, e)
        return {"status": "unavailable", "error": str(e)}


def assemble_move_evidence(ticker: str, sources: Optional[dict] = None) -> dict:
    """The dossier: move profile + evidence blocks. Never raises; a source
    failure degrades that block only."""
    src = sources or _default_sources()
    try:
        close = src["history"](ticker)
        move = compute_move_profile(close)
    except Exception as e:
        logger.warning("explain-move history failed for %s: %s", ticker, e)
        move = {"status": "unavailable", "error": str(e)}

    evidence = {name: _block(name, src[name], ticker)
                for name in ("earnings", "filings", "news_sentiment",
                             "insider", "options") if name in src}
    return {"ticker": ticker.upper(), "move": move, "evidence": evidence,
            "label": EXPLAIN_LABEL}


# ── Narration (LLM optional, template fallback) ───────────────────────────────


def _template_narration(dossier: dict) -> str:
    """Deterministic narration from the evidence — used when no LLM key."""
    m = dossier.get("move", {})
    bits: list[str] = []
    r21 = m.get("return_21d")
    if r21 is not None:
        unusual = m.get("move_unusualness")
        z = m.get("move_zscore_21d")
        tail = (f" — an {unusual} move ({z}σ vs its own history)"
                if unusual and z is not None else "")
        bits.append(f"{dossier['ticker']} moved {r21:+.1%} over the last 21 "
                    f"trading days{tail}.")
    ev = dossier.get("evidence", {})

    e = ev.get("earnings", {})
    if e.get("status") == "ok":
        d = e["data"]
        if d.get("earnings_imminent") or (d.get("days_until_earnings") or 99) <= 7:
            bits.append(f"Earnings are near ({d.get('next_earnings_date')}).")
        elif d.get("earnings_surprises"):
            bits.append(f"Last earnings surprise trend: {d.get('surprise_trend')}, "
                        f"beat rate {d.get('beat_rate')}.")
    f = ev.get("filings", {})
    if f.get("status") == "ok" and f["data"]:
        bits.append(f"{len(f['data'])} SEC 8-K filing(s) in the last 45 days "
                    f"(latest: {f['data'][0].get('filed', '?')[:10]}).")
    ns = ev.get("news_sentiment", {})
    if ns.get("status") == "ok":
        d = ns["data"]
        bits.append(f"News sentiment: {d.get('sentiment')} across "
                    f"{d.get('headline_count')} headlines ({d.get('method')}).")
    ins = ev.get("insider", {})
    if ins.get("status") == "ok" and (ins["data"].get("n_distinct_buyers") or 0) > 0:
        bits.append(f"Insiders: {ins['data']['n_distinct_buyers']} distinct "
                    f"open-market buyer(s) in 90 days.")
    op = ev.get("options", {})
    if op.get("status") == "ok" and op["data"].get("available"):
        bits.append(f"Options: {op['data'].get('sentiment')} positioning "
                    f"(P/C {op['data'].get('put_call_ratio')}).")

    unavailable = [k for k, v in ev.items() if v.get("status") != "ok"]
    if unavailable:
        bits.append(f"(No data available for: {', '.join(unavailable)}.)")
    bits.append("This is context around the move, not an explanation of its "
                "cause — and not advice.")
    return " ".join(bits)


def narrate(dossier: dict) -> dict:
    """Narrate the dossier: LLM when a provider key exists, template otherwise."""
    try:
        from backend.services.llm_analyzer import _call_llm, is_available
        if is_available():
            system = ("You explain stock price moves from supplied evidence for a "
                      "retail investor. Three sentences max: what moved, what the "
                      "evidence shows, what remains uncertain. NEVER give advice, "
                      "predictions, or buy/sell language. If evidence is thin, say "
                      "the move is unexplained by the available data.")
            text = _call_llm(system, str(dossier))
            if text:
                return {"narration": text.strip(), "method": "llm",
                        "label": EXPLAIN_LABEL}
    except Exception as e:
        logger.warning("explain-move LLM narration failed: %s", e)
    return {"narration": _template_narration(dossier), "method": "template",
            "label": EXPLAIN_LABEL}


def _to_native(obj):
    """Recursively coerce numpy/pandas scalars to JSON-safe natives — live
    service payloads carry np.bool_/np.float64 that the ASGI encoder rejects
    (found live on prod, invisible with pure-python test fixtures)."""
    if isinstance(obj, dict):
        return {str(k): _to_native(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_native(v) for v in obj]
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    if isinstance(obj, (pd.Series, pd.DataFrame, np.ndarray)):
        return None  # bulk data never belongs in the dossier
    return obj


def explain_move(ticker: str, sources: Optional[dict] = None) -> dict:
    """The full feature: dossier + narration. Never raises."""
    dossier = _to_native(assemble_move_evidence(ticker, sources=sources))
    return {**dossier, **narrate(dossier)}
