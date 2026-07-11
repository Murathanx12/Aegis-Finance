"""
Aegis Finance — LLM Analysis Service (Claude + DeepSeek)
==========================================================

Uses Claude API (preferred) or DeepSeek API (fallback) for:
  - Market news summarization
  - Stock outlook analysis (bull/bear thesis)
  - Expectations generation
  - Portfolio commentary (v9)

Provider priority:
  1. ANTHROPIC_API_KEY → Claude (Haiku for speed, Sonnet for quality)
  2. DEEPSEEK_API_KEY → DeepSeek (OpenAI-compatible)
  3. No key → graceful fallback (returns None)

Graceful fallback: returns None if no API key or rate limited.
1-hour TTL caching on LLM responses.

Usage:
    from backend.services.llm_analyzer import (
        summarize_market_news, analyze_stock_outlook, generate_expectations,
        generate_portfolio_commentary, is_available,
    )
"""

import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Optional

from backend.cache import cached
from backend.config import config as _cfg

logger = logging.getLogger(__name__)

_llm_cfg = _cfg.get("llm", {})

# ── Provider Detection ──────────────────────────────────────────────────────

_ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
_DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")

# Claude models (fast → quality)
_CLAUDE_MODEL_FAST = _llm_cfg.get("claude_model_fast", "claude-haiku-4-5-20251001")
_CLAUDE_MODEL_QUALITY = _llm_cfg.get("claude_model_quality", "claude-sonnet-4-6")

# DeepSeek settings
_DEEPSEEK_BASE_URL = _llm_cfg.get("base_url", "https://api.deepseek.com")
_DEEPSEEK_MODEL = _llm_cfg.get("model", "deepseek-chat")

_MAX_TOKENS = _llm_cfg.get("max_tokens", 500)

_anthropic_client = None
_openai_client = None

# ── Spend Guards ────────────────────────────────────────────────────────────
# The DeepSeek balance is small and prepaid; two guards keep it alive:
#  1. Daily call cap — beyond it every helper falls back to its template path.
#  2. Billing breaker — a 401/402 (dead/empty key) trips a cooldown so we
#     don't burn a request per cache expiry against a key that cannot pay.

_DAILY_CAP = int(_llm_cfg.get("daily_call_cap", 150))
_BREAKER_COOLDOWN_S = float(_llm_cfg.get("billing_breaker_cooldown_s", 6 * 3600))

_spend_lock = threading.Lock()
_spend_state: dict = {"date": None, "count": 0, "breaker_until": 0.0,
                      "breaker_reason": None, "cap_logged": False}


def _is_billing_error(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    if status in (401, 402):
        return True
    msg = str(exc).lower()
    return "insufficient balance" in msg or "invalid api key" in msg


def _trip_breaker(exc: Exception) -> None:
    with _spend_lock:
        _spend_state["breaker_until"] = time.time() + _BREAKER_COOLDOWN_S
        _spend_state["breaker_reason"] = str(exc)[:200]
    logger.error(
        "LLM billing error — provider disabled for %.0f min: %s",
        _BREAKER_COOLDOWN_S / 60, exc,
    )


def _acquire_call_budget() -> bool:
    """True if one LLM call may proceed (counts it); False → use fallbacks."""
    with _spend_lock:
        if time.time() < _spend_state["breaker_until"]:
            return False
        today = datetime.now(timezone.utc).date().isoformat()
        if _spend_state["date"] != today:
            _spend_state["date"] = today
            _spend_state["count"] = 0
            _spend_state["cap_logged"] = False
        if _spend_state["count"] >= _DAILY_CAP:
            if not _spend_state["cap_logged"]:
                _spend_state["cap_logged"] = True
                logger.warning(
                    "LLM daily call cap reached (%d) — template fallbacks "
                    "until UTC midnight", _DAILY_CAP,
                )
            return False
        _spend_state["count"] += 1
        return True


def llm_usage() -> dict:
    """Current spend-guard state (for health/diagnostics)."""
    with _spend_lock:
        return {
            "provider": _get_provider(),
            "calls_today": _spend_state["count"],
            "daily_cap": _DAILY_CAP,
            "breaker_active": time.time() < _spend_state["breaker_until"],
            "breaker_reason": _spend_state["breaker_reason"],
        }


def _get_provider() -> str:
    """Detect which LLM provider is available."""
    if _ANTHROPIC_API_KEY:
        return "claude"
    elif _DEEPSEEK_API_KEY:
        return "deepseek"
    return "none"


def _get_anthropic_client():
    """Lazy-init Anthropic client."""
    global _anthropic_client
    if _anthropic_client is not None:
        return _anthropic_client
    if not _ANTHROPIC_API_KEY:
        return None
    try:
        import anthropic
        _anthropic_client = anthropic.Anthropic(api_key=_ANTHROPIC_API_KEY)
        return _anthropic_client
    except ImportError:
        logger.warning("anthropic SDK not installed — Claude unavailable")
        return None
    except Exception as e:
        logger.warning("Failed to init Anthropic client: %s", e)
        return None


def _get_openai_client():
    """Lazy-init OpenAI client for DeepSeek."""
    global _openai_client
    if _openai_client is not None:
        return _openai_client
    if not _DEEPSEEK_API_KEY:
        return None
    try:
        from openai import OpenAI
        _openai_client = OpenAI(
            api_key=_DEEPSEEK_API_KEY,
            base_url=_DEEPSEEK_BASE_URL,
        )
        return _openai_client
    except ImportError:
        logger.warning("openai SDK not installed — DeepSeek unavailable")
        return None
    except Exception as e:
        logger.warning("Failed to init DeepSeek client: %s", e)
        return None


def _call_llm(
    system_prompt: str,
    user_prompt: str,
    quality: bool = False,
) -> Optional[str]:
    """Make a single LLM call. Tries Claude first, then DeepSeek.

    Args:
        system_prompt: System instructions
        user_prompt: User message
        quality: If True, use higher-quality model (Sonnet vs Haiku)

    Returns:
        LLM response text or None on failure.
    """
    provider = _get_provider()
    if provider == "none" or not _acquire_call_budget():
        return None

    # Try Claude first
    if provider == "claude":
        client = _get_anthropic_client()
        if client:
            try:
                model = _CLAUDE_MODEL_QUALITY if quality else _CLAUDE_MODEL_FAST
                response = client.messages.create(
                    model=model,
                    max_tokens=_MAX_TOKENS,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                )
                return response.content[0].text.strip()
            except Exception as e:
                logger.warning("Claude API call failed: %s", e)
                if _is_billing_error(e):
                    _trip_breaker(e)
                    return None
                # Fall through to DeepSeek

    # Try DeepSeek
    if _DEEPSEEK_API_KEY:
        client = _get_openai_client()
        if client:
            try:
                response = client.chat.completions.create(
                    model=_DEEPSEEK_MODEL,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_tokens=_MAX_TOKENS,
                    temperature=_llm_cfg.get("temperature", 0.3),
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                logger.warning("DeepSeek API call failed: %s", e)
                if _is_billing_error(e):
                    _trip_breaker(e)

    return None


# ── Public API ──────────────────────────────────────────────────────────────


@cached(ttl=3600, key_prefix="llm_market_summary")
def summarize_market_news(news_items: list[dict]) -> Optional[dict]:
    """Generate a 2-3 sentence market news summary.

    Args:
        news_items: List of {title, publisher, published}

    Returns:
        {summary: str, sentiment: str, provider: str} or None
    """
    if not news_items:
        return None

    headlines = "\n".join(
        f"- {item.get('title', '')} ({item.get('publisher', '')})"
        for item in news_items[:15]
    )

    system = (
        "You are a concise financial analyst. Summarize market news in 2-3 sentences. "
        "Include the overall market sentiment (bullish/bearish/neutral/mixed). "
        "Be factual, not speculative. No disclaimers."
    )
    user = f"Summarize these recent market headlines:\n\n{headlines}"

    result = _call_llm(system, user)
    if result is None:
        return None

    # Detect sentiment from the summary
    lower = result.lower()
    if any(w in lower for w in ["bullish", "rally", "surge", "optimis"]):
        sentiment = "bullish"
    elif any(w in lower for w in ["bearish", "decline", "crash", "pessimis", "fear"]):
        sentiment = "bearish"
    elif any(w in lower for w in ["mixed", "uncertain", "volatile"]):
        sentiment = "mixed"
    else:
        sentiment = "neutral"

    return {"summary": result, "sentiment": sentiment, "provider": _get_provider()}


@cached(ttl=3600, key_prefix="llm_stock_outlook")
def analyze_stock_outlook(
    ticker: str,
    news: list[dict],
    fundamentals: dict,
) -> Optional[dict]:
    """Generate bull/bear thesis for a stock.

    Args:
        ticker: Stock ticker
        news: Recent news items
        fundamentals: Dict with pe_ratio, market_cap, beta, analyst_target, etc.

    Returns:
        {bull_case, bear_case, sentiment_score, summary} or None
    """
    headlines = "\n".join(
        f"- {item.get('title', '')}" for item in news[:10]
    ) if news else "No recent news available."

    pe = fundamentals.get("pe_ratio", "N/A")
    mc = fundamentals.get("market_cap")
    mc_str = f"${mc/1e9:.1f}B" if mc and mc > 0 else "N/A"
    beta = fundamentals.get("beta", "N/A")
    target = fundamentals.get("analyst_target", "N/A")
    price = fundamentals.get("current_price", "N/A")

    system = (
        "You are a senior equity analyst. Provide a concise bull case (2 sentences) "
        "and bear case (2 sentences) for the given stock. Then give a sentiment score "
        "from -1.0 (very bearish) to +1.0 (very bullish). Format:\n"
        "BULL: ...\nBEAR: ...\nSCORE: X.X\nSUMMARY: One sentence outlook."
    )
    user = (
        f"Stock: {ticker}\n"
        f"Price: ${price}, P/E: {pe}, Market Cap: {mc_str}, Beta: {beta}\n"
        f"Analyst Target: ${target}\n"
        f"Recent News:\n{headlines}"
    )

    result = _call_llm(system, user)
    if result is None:
        return None

    # Parse structured response
    bull_case = ""
    bear_case = ""
    score = 0.0
    summary = ""

    for line in result.split("\n"):
        line = line.strip()
        if line.startswith("BULL:"):
            bull_case = line[5:].strip()
        elif line.startswith("BEAR:"):
            bear_case = line[5:].strip()
        elif line.startswith("SCORE:"):
            try:
                score = float(line[6:].strip())
            except ValueError:
                score = 0.0
        elif line.startswith("SUMMARY:"):
            summary = line[8:].strip()

    if not bull_case and not bear_case:
        return {"summary": result, "bull_case": "", "bear_case": "", "sentiment_score": 0.0}

    return {
        "bull_case": bull_case,
        "bear_case": bear_case,
        "sentiment_score": max(-1.0, min(1.0, score)),
        "summary": summary or result.split("\n")[0],
        "provider": _get_provider(),
    }


@cached(ttl=3600, key_prefix="llm_expectations")
def generate_expectations(
    ticker: str,
    analyst_targets: Optional[dict] = None,
    earnings: Optional[dict] = None,
) -> Optional[dict]:
    """Generate 'What to watch' section for a stock.

    Returns:
        {expectations: str, key_catalysts: list[str]} or None
    """
    target_info = ""
    if analyst_targets:
        target_info = (
            f"Analyst Price Targets — Low: ${analyst_targets.get('low', 'N/A')}, "
            f"Mean: ${analyst_targets.get('mean', 'N/A')}, "
            f"High: ${analyst_targets.get('high', 'N/A')}"
        )

    earnings_info = ""
    if earnings:
        next_date = earnings.get("next_date", "N/A")
        estimate = earnings.get("estimate", "N/A")
        earnings_info = f"Next Earnings: {next_date}, EPS Estimate: ${estimate}"

    if not target_info and not earnings_info:
        return None

    system = (
        "You are a financial analyst. List 3-4 key catalysts/risks to watch for this stock. "
        "Be specific and actionable. Format as a short paragraph followed by bullet points."
    )
    user = f"Stock: {ticker}\n{target_info}\n{earnings_info}"

    result = _call_llm(system, user)
    if result is None:
        return None

    catalysts = []
    for line in result.split("\n"):
        line = line.strip()
        if line.startswith(("-", "*", "•")) and len(line) > 5:
            catalysts.append(line.lstrip("-*• "))

    return {
        "expectations": result,
        "key_catalysts": catalysts[:5],
    }


@cached(ttl=3600, key_prefix="llm_portfolio_commentary")
def generate_portfolio_commentary(
    holdings: list[dict],
    metrics: dict,
    factor_exposures: Optional[dict] = None,
    risk_contributions: Optional[dict] = None,
) -> Optional[dict]:
    """Generate AI portfolio commentary — Bloomberg PORT Enterprise style.

    Takes portfolio holdings, performance metrics, factor exposures, and risk
    contributions and produces plain-English analysis a client could read.

    Args:
        holdings: List of {ticker, weight, return_1m, sector}
        metrics: {total_return, sharpe, volatility, max_drawdown, ...}
        factor_exposures: Optional Fama-French factor loadings
        risk_contributions: Optional per-holding MCTR data

    Returns:
        {commentary: str, key_points: list[str], risk_alerts: list[str]}
    """
    # Build context
    holdings_str = "\n".join(
        f"  {h.get('ticker', '?')}: {h.get('weight', 0)*100:.1f}% weight, "
        f"{h.get('return_1m', 0):.1f}% 1M return, sector={h.get('sector', '?')}"
        for h in (holdings or [])[:20]
    )

    metrics_str = ""
    if metrics:
        metrics_str = (
            f"Portfolio Return (1M): {metrics.get('return_1m', 'N/A')}%\n"
            f"Annualized Volatility: {metrics.get('volatility', 'N/A')}%\n"
            f"Sharpe Ratio: {metrics.get('sharpe', 'N/A')}\n"
            f"Max Drawdown: {metrics.get('max_drawdown', 'N/A')}%\n"
            f"VaR (95%): {metrics.get('var_95', 'N/A')}%\n"
        )

    factor_str = ""
    if factor_exposures:
        factor_str = "Factor Exposures:\n" + "\n".join(
            f"  {k}: {v:.3f}" for k, v in factor_exposures.items()
        )

    risk_str = ""
    if risk_contributions:
        top_risk = sorted(risk_contributions.items(), key=lambda x: abs(x[1]), reverse=True)[:5]
        risk_str = "Top Risk Contributors:\n" + "\n".join(
            f"  {k}: {v*100:.1f}% of portfolio risk" for k, v in top_risk
        )

    system = (
        "You are a portfolio analyst writing a monthly client report. "
        "Write a 3-4 paragraph portfolio commentary covering: "
        "1) Performance summary and key drivers, "
        "2) Risk assessment and concentration concerns, "
        "3) Factor tilts and style observations, "
        "4) Recommendations or areas to monitor. "
        "Be professional, specific, and actionable. No disclaimers. "
        "End with 3 bullet-point key takeaways."
    )
    user = (
        f"Portfolio Holdings:\n{holdings_str}\n\n"
        f"Performance Metrics:\n{metrics_str}\n"
        f"{factor_str}\n{risk_str}"
    )

    result = _call_llm(system, user, quality=True)
    if result is None:
        return None

    # Extract key points (bullet points at the end)
    key_points = []
    risk_alerts = []
    for line in result.split("\n"):
        line = line.strip()
        if line.startswith(("-", "*", "•")) and len(line) > 10:
            point = line.lstrip("-*• ")
            if any(w in point.lower() for w in ["risk", "concern", "warning", "alert", "concentration"]):
                risk_alerts.append(point)
            else:
                key_points.append(point)

    return {
        "commentary": result,
        "key_points": key_points[:5],
        "risk_alerts": risk_alerts[:3],
        "provider": _get_provider(),
    }


def is_available() -> bool:
    """Check if LLM analysis is available (any API key configured + SDK installed)."""
    provider = _get_provider()
    if provider == "claude":
        return _get_anthropic_client() is not None
    elif provider == "deepseek":
        return _get_openai_client() is not None
    return False
