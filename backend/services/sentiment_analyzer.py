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
import threading
import time

from backend.config import config

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# FINBERT (primary)
# ══════════════════════════════════════════════════════════════════════════════

_finbert_pipeline = None
_finbert_available = None
_finbert_last_used: float | None = None
_finbert_lock = threading.Lock()


def maybe_unload_finbert(idle_seconds: int | None = None) -> bool:
    """Free the FinBERT pipeline after a period of no scoring calls.

    The loaded model holds ~1.5-2 GB resident — most of the Railway memory
    bill — while a reload from the local HF cache costs ~5-10s. Off-hours
    the model sits unused for 14+ h/day, so idle-unloading converts a 24/7
    RAM cost into a few load/unload cycles. Quality is untouched: the same
    model reloads on the next scoring call (`_finbert_available` resets to
    None so `_get_finbert` retries).

    Returns True if an unload happened. idle_seconds=0 disables unloading.
    """
    global _finbert_pipeline, _finbert_available, _finbert_last_used
    if idle_seconds is None:
        idle_seconds = int(config.get("sentiment", {})
                           .get("finbert_idle_unload_minutes", 45)) * 60
    if idle_seconds <= 0:
        return False
    with _finbert_lock:
        if _finbert_pipeline is None or _finbert_last_used is None:
            return False
        idle = time.time() - _finbert_last_used
        if idle < idle_seconds:
            return False
        _finbert_pipeline = None
        _finbert_available = None  # next _get_finbert() reloads
        _finbert_last_used = None
    import gc
    gc.collect()
    try:  # return freed pages to the OS (Linux/Railway; no-op elsewhere)
        import ctypes
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass
    logger.info("FinBERT unloaded after %.0f min idle (reloads on next use)", idle / 60)
    return True


def _get_finbert():
    """Lazy-load FinBERT pipeline (first call takes ~5s, subsequent calls instant).

    AEGIS_DISABLE_FINBERT=1 forces the keyword fallback WITHOUT loading
    torch/transformers — the model keeps ~1-2 GB resident, which is most of
    the Railway memory bill. Sentiment quality drops from transformer to
    keyword-lexicon; every response already reports its `method`, so the
    degradation is visible, never silent.
    """
    global _finbert_pipeline, _finbert_available, _finbert_last_used
    with _finbert_lock:
        if _finbert_available is not None:
            _finbert_last_used = time.time()
            return _finbert_pipeline

        import os
        if os.getenv("AEGIS_DISABLE_FINBERT") == "1":
            logger.info("FinBERT disabled via AEGIS_DISABLE_FINBERT=1 — keyword fallback")
            _finbert_available = False
            return None

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
            _finbert_last_used = time.time()
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
