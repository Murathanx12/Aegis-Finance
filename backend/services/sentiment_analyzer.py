"""
Aegis Finance — FinBERT Sentiment Analyzer
=============================================

Analyzes news headline sentiment for a given stock ticker using:
  - Primary: ProsusAI/finbert (HuggingFace transformer, CPU-friendly)
  - Fallback: Keyword-based financial sentiment (if transformers unavailable)

Usage:
    from backend.services.sentiment_analyzer import analyze_sentiment

    result = analyze_sentiment("AAPL")
    # -> {"ticker": "AAPL", "sentiment": "bullish", "score": 0.42, ...}
"""

import logging

from backend.config import config

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# FINBERT (primary)
# ══════════════════════════════════════════════════════════════════════════════

_finbert_pipeline = None
_finbert_available = None


def _get_finbert():
    """Lazy-load FinBERT pipeline (first call takes ~5s, subsequent calls instant)."""
    global _finbert_pipeline, _finbert_available
    if _finbert_available is not None:
        return _finbert_pipeline

    try:
        from transformers import pipeline
        _finbert_pipeline = pipeline(
            "sentiment-analysis",
            model="ProsusAI/finbert",
            tokenizer="ProsusAI/finbert",
            truncation=True,
            max_length=512,
        )
        _finbert_available = True
        logger.info("FinBERT loaded successfully")
        return _finbert_pipeline
    except Exception as e:
        logger.warning("FinBERT unavailable (%s), using keyword fallback", e)
        _finbert_available = False
        return None


def _score_with_finbert(headlines: list[str]) -> list[dict]:
    """Score headlines using FinBERT. Returns list of {label, score}."""
    pipe = _get_finbert()
    if pipe is None:
        return []

    try:
        results = pipe(headlines, batch_size=8)
        scored = []
        for r in results:
            label = r["label"].lower()
            score = r["score"]
            # Map FinBERT labels to numeric: positive=+1, negative=-1, neutral=0
            if label == "positive":
                numeric = score
            elif label == "negative":
                numeric = -score
            else:
                numeric = 0.0
            scored.append({"label": label, "score": score, "numeric": numeric})
        return scored
    except (RuntimeError, ValueError, IndexError, TypeError) as e:
        logger.warning("FinBERT scoring failed: %s", e)
        return []


# ══════════════════════════════════════════════════════════════════════════════
# KEYWORD FALLBACK
# ══════════════════════════════════════════════════════════════════════════════

# Financial sentiment keywords (curated from financial NLP literature)
_POSITIVE_KEYWORDS = {
    "beat", "beats", "surge", "surges", "rally", "rallies", "gain", "gains",
    "profit", "profits", "growth", "upgrade", "upgrades", "outperform",
    "bullish", "record", "high", "strong", "positive", "upside", "optimistic",
    "recovery", "boom", "soar", "soars", "exceed", "exceeds", "dividend",
    "buyback", "expansion", "innovative", "breakthrough", "partnership",
}

_NEGATIVE_KEYWORDS = {
    "miss", "misses", "drop", "drops", "fall", "falls", "decline", "declines",
    "loss", "losses", "crash", "crashes", "downgrade", "downgrades",
    "underperform", "bearish", "low", "weak", "negative", "downside",
    "pessimistic", "recession", "slump", "plunge", "plunges", "layoff",
    "layoffs", "bankruptcy", "default", "warning", "risk", "lawsuit",
    "investigation", "probe", "fraud", "sell-off", "selloff", "tariff",
}


def _score_with_keywords(headlines: list[str]) -> list[dict]:
    """Score headlines using keyword counting. Returns list of {label, score, numeric}."""
    scored = []
    for headline in headlines:
        words = set(headline.lower().split())
        pos = len(words & _POSITIVE_KEYWORDS)
        neg = len(words & _NEGATIVE_KEYWORDS)
        total = pos + neg

        if total == 0:
            scored.append({"label": "neutral", "score": 0.5, "numeric": 0.0})
        elif pos > neg:
            confidence = min(pos / total, 1.0)
            scored.append({"label": "positive", "score": confidence, "numeric": confidence})
        elif neg > pos:
            confidence = min(neg / total, 1.0)
            scored.append({"label": "negative", "score": confidence, "numeric": -confidence})
        else:
            scored.append({"label": "neutral", "score": 0.5, "numeric": 0.0})
    return scored


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════════════════════


def analyze_sentiment(ticker: str, max_headlines: int = 20) -> dict:
    """Analyze news sentiment for a stock ticker.

    Fetches recent headlines from yfinance, scores them with FinBERT
    (or keyword fallback), and returns aggregate sentiment.

    Returns:
        Dict with sentiment analysis (always returns a dict, never None).
    """
    from backend.services.news_intelligence import fetch_stock_news

    news = fetch_stock_news(ticker, max_items=max_headlines)
    if not news:
        return {
            "ticker": ticker,
            "sentiment": "neutral",
            "score": 0.0,
            "confidence": 0.0,
            "headline_count": 0,
            "method": "none",
            "breakdown": {"positive": 0, "negative": 0, "neutral": 0},
            "headlines": [],
            "summary": f"No recent news found for {ticker}.",
        }

    headlines = [item["title"] for item in news if item.get("title")]
    if not headlines:
        return {
            "ticker": ticker,
            "sentiment": "neutral",
            "score": 0.0,
            "confidence": 0.0,
            "headline_count": 0,
            "method": "none",
            "breakdown": {"positive": 0, "negative": 0, "neutral": 0},
            "headlines": [],
            "summary": f"No usable headlines found for {ticker}.",
        }

    # Try FinBERT first, fall back to keywords
    scores = _score_with_finbert(headlines)
    method = "finbert"
    if not scores:
        scores = _score_with_keywords(headlines)
        method = "keyword"

    # Aggregate
    n = len(scores)
    avg_numeric = sum(s["numeric"] for s in scores) / n if n > 0 else 0.0
    avg_confidence = sum(s["score"] for s in scores) / n if n > 0 else 0.0

    # Count labels
    pos_count = sum(1 for s in scores if s["label"] == "positive")
    neg_count = sum(1 for s in scores if s["label"] == "negative")
    neu_count = sum(1 for s in scores if s["label"] == "neutral")

    # Map aggregate score to sentiment label (thresholds from config)
    sent_cfg = config.get("sentiment", {})
    bullish_t = sent_cfg.get("bullish_threshold", 0.15)
    sl_bullish_t = sent_cfg.get("slightly_bullish_threshold", 0.05)
    bearish_t = sent_cfg.get("bearish_threshold", -0.15)
    sl_bearish_t = sent_cfg.get("slightly_bearish_threshold", -0.05)

    if avg_numeric > bullish_t:
        sentiment = "bullish"
    elif avg_numeric > sl_bullish_t:
        sentiment = "slightly_bullish"
    elif avg_numeric < bearish_t:
        sentiment = "bearish"
    elif avg_numeric < sl_bearish_t:
        sentiment = "slightly_bearish"
    else:
        sentiment = "neutral"

    # Build per-headline detail
    headline_details = []
    for item, score in zip(news[:len(scores)], scores):
        headline_details.append({
            "title": item.get("title", ""),
            "publisher": item.get("publisher", ""),
            "sentiment": score["label"],
            "score": round(score["numeric"], 3),
        })

    # Summary text
    if sentiment in ("bullish", "slightly_bullish"):
        tone = "positive"
    elif sentiment in ("bearish", "slightly_bearish"):
        tone = "negative"
    else:
        tone = "mixed"

    summary = (
        f"News sentiment for {ticker} is currently {sentiment} "
        f"based on {n} recent headlines. "
        f"{pos_count} positive, {neg_count} negative, {neu_count} neutral. "
        f"Overall tone is {tone} (score: {avg_numeric:+.2f})."
    )

    return {
        "ticker": ticker,
        "sentiment": sentiment,
        "score": round(avg_numeric, 4),
        "confidence": round(avg_confidence, 4),
        "headline_count": n,
        "method": method,
        "breakdown": {
            "positive": pos_count,
            "negative": neg_count,
            "neutral": neu_count,
        },
        "headlines": headline_details,
        "summary": summary,
    }
