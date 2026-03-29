"""
Aegis Finance — DeepSeek LLM Analysis Service
================================================

Uses DeepSeek API (OpenAI-compatible) for:
  - Market news summarization
  - Stock outlook analysis (bull/bear thesis)
  - Expectations generation

Graceful fallback: returns None if no API key or rate limited.
1-hour TTL caching on LLM responses.

Usage:
    from backend.services.llm_analyzer import (
        summarize_market_news, analyze_stock_outlook, generate_expectations,
    )
"""

import logging
import os
from typing import Optional

from backend.cache import cached

logger = logging.getLogger(__name__)

_DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
_MODEL = "deepseek-chat"
_MAX_TOKENS = 500

_client = None


def _get_client():
    """Lazy-init OpenAI client for DeepSeek."""
    global _client
    if _client is not None:
        return _client

    if not _DEEPSEEK_API_KEY:
        return None

    try:
        from openai import OpenAI
        _client = OpenAI(
            api_key=_DEEPSEEK_API_KEY,
            base_url=_DEEPSEEK_BASE_URL,
        )
        return _client
    except ImportError:
        logger.warning("openai SDK not installed — LLM analysis unavailable")
        return None
    except Exception as e:
        logger.warning("Failed to init DeepSeek client: %s", e)
        return None


def _call_llm(system_prompt: str, user_prompt: str) -> Optional[str]:
    """Make a single LLM call. Returns None on failure."""
    client = _get_client()
    if client is None:
        return None

    try:
        response = client.chat.completions.create(
            model=_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=_MAX_TOKENS,
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.warning("DeepSeek API call failed: %s", e)
        return None


@cached(ttl=3600, key_prefix="llm_market_summary")
def summarize_market_news(news_items: list[dict]) -> Optional[dict]:
    """Generate a 2-3 sentence market news summary.

    Args:
        news_items: List of {title, publisher, published}

    Returns:
        {summary: str, sentiment: str} or None
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

    return {"summary": result, "sentiment": sentiment}


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
        # Fallback: treat entire response as summary
        return {"summary": result, "bull_case": "", "bear_case": "", "sentiment_score": 0.0}

    return {
        "bull_case": bull_case,
        "bear_case": bear_case,
        "sentiment_score": max(-1.0, min(1.0, score)),
        "summary": summary or result.split("\n")[0],
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

    # Extract bullet points as catalysts
    catalysts = []
    for line in result.split("\n"):
        line = line.strip()
        if line.startswith(("-", "*", "•")) and len(line) > 5:
            catalysts.append(line.lstrip("-*• "))

    return {
        "expectations": result,
        "key_catalysts": catalysts[:5],
    }


def is_available() -> bool:
    """Check if LLM analysis is available (API key configured + SDK installed)."""
    return bool(_DEEPSEEK_API_KEY) and _get_client() is not None
