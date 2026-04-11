"""
Stock Analysis Router
=======================

GET /api/stock/screener            — Top stocks screener (batch analysis)
GET /api/stock/{ticker}            — Per-ticker projection + risk metrics
GET /api/stock/{ticker}/shap       — SHAP explanation for ticker
GET /api/stock/{ticker}/sentiment  — FinBERT news sentiment analysis
"""

import asyncio
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from fastapi import APIRouter, HTTPException

from backend.cache import cache_get, cache_set
from backend.config import config

router = APIRouter(prefix="/api/stock", tags=["stock"])
logger = logging.getLogger(__name__)

_CACHE_TTL = config["cache"]

_TICKER_RE = re.compile(r"^[A-Z0-9.\-]{1,10}$")


@router.get("/screener")
async def get_stock_screener():
    """Top stocks screener — batch analysis of watchlist stocks."""
    cached = cache_get("stock_screener", _CACHE_TTL["ttl_stock"])
    if cached is not None:
        return cached

    try:
        result = await asyncio.to_thread(_screener)
        cache_set("stock_screener", result)
        return result
    except Exception as e:
        logger.error("stock screener failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


def _screener() -> dict:
    from backend.services.stock_analyzer import analyze_stock, DEFAULT_WATCHLIST, SECTOR_STOCK_MAP
    from backend.services.signal_engine import get_market_signal, get_stock_signal

    # Compute market-level signal once (shared across all stocks)
    market_sig = _compute_market_signal()

    # Compute sector 3-month momentum for each sector ETF
    sector_momentum = _compute_sector_momentum()

    # Build full list: DEFAULT_WATCHLIST + top picks from each sector
    all_tickers = set(DEFAULT_WATCHLIST)
    for sector_tickers in SECTOR_STOCK_MAP.values():
        for t in sector_tickers[:3]:  # top 3 per sector
            all_tickers.add(t)

    # Extract crash probability for MC jump rate modulation
    crash_3m_pct = market_sig.get("_crash_3m_pct")
    crash_prob_for_mc = crash_3m_pct / 100.0 if crash_3m_pct is not None else None

    # Parallel stock analysis — ~3-5x faster than sequential
    t0 = time.perf_counter()
    sorted_tickers = sorted(all_tickers)
    perf_cfg = config["performance"]
    max_workers = min(perf_cfg["screener_max_workers"], len(sorted_tickers))

    def _analyze_one(ticker: str) -> dict | None:
        """Analyze a single ticker and compute its signal. Thread-safe."""
        try:
            r = analyze_stock(ticker, ml_crash_prob=crash_prob_for_mc)
            if r is None:
                return None

            stock_sector = r.get("sector", "Unknown")
            sec_mom = sector_momentum.get(stock_sector, 0.0)

            fwd_pe = None
            key_stats = r.get("key_stats")
            if key_stats and "pe_forward" in key_stats:
                fwd_pe = key_stats["pe_forward"]

            stock_sig = get_stock_signal(
                market_signal=market_sig,
                beta=r.get("beta", 1.0),
                analyst_target=r.get("analyst_target"),
                current_price=r.get("current_price", 0),
                sector_momentum=sec_mom,
                pe_ratio=r.get("pe_ratio"),
                forward_pe=fwd_pe,
            )

            return {
                "ticker": r["ticker"],
                "name": r.get("name", ticker),
                "sector": r.get("sector", "Unknown"),
                "current_price": r.get("current_price", 0),
                "expected_return": r.get("capped_drift", r.get("expected_return", 0)),
                "sharpe": r.get("sharpe", 0),
                "prob_loss": r.get("prob_loss_5y", 0),
                "volatility": r.get("volatility", 0),
                "beta": r.get("beta", 1.0),
                "pe_ratio": r.get("pe_ratio"),
                "analyst_target": r.get("analyst_targets", {}).get("mean") if r.get("analyst_targets") else None,
                "market_cap": r.get("market_cap"),
                "signal_action": stock_sig["action"],
                "signal_confidence": stock_sig["confidence"],
                "signal_score": stock_sig["composite_score"],
            }
        except Exception as e:
            logger.warning("screener skip %s: %s", ticker, e)
            return None

    stocks = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_analyze_one, t): t for t in sorted_tickers}
        for future in as_completed(futures):
            result = future.result()
            if result is not None:
                stocks.append(result)

    elapsed = time.perf_counter() - t0
    logger.info(
        "Screener analyzed %d/%d stocks in %.1fs (parallel, %d workers)",
        len(stocks), len(sorted_tickers), elapsed, max_workers,
    )

    # Sort by Sharpe ratio descending
    stocks.sort(key=lambda x: x["sharpe"], reverse=True)

    return {"stocks": stocks, "count": len(stocks), "market_signal": market_sig}


def _compute_sector_momentum() -> dict:
    """Compute 3-month return for each sector ETF (parallel fetch).

    Returns:
        Dict of {sector_name: 3m_return_pct}
    """
    import yfinance as yf
    from backend.config import config

    sector_etfs = config["data"]["sectors"]

    def _fetch_one(sector_name: str, etf_ticker: str) -> tuple[str, float | None]:
        try:
            hist = yf.Ticker(etf_ticker).history(period="6mo")
            if hist is not None and len(hist) >= 63:
                current = float(hist["Close"].iloc[-1])
                past = float(hist["Close"].iloc[-63])
                return sector_name, (current / past - 1) * 100
        except (KeyError, IndexError, ValueError, TypeError) as e:
            logger.debug("sector momentum skip %s: %s", sector_name, e)
        return sector_name, None

    momentum = {}
    sec_workers = config["performance"]["sector_momentum_workers"]
    with ThreadPoolExecutor(max_workers=sec_workers) as executor:
        futures = [
            executor.submit(_fetch_one, name, tick)
            for name, tick in sector_etfs.items()
        ]
        for future in as_completed(futures):
            name, val = future.result()
            if val is not None:
                momentum[name] = val

    return momentum


def _compute_market_signal() -> dict:
    """Compute the market-level signal once for the screener."""
    from backend.services.signal_engine import get_market_signal
    from backend.services.data_fetcher import DataFetcher
    from backend.services.risk_scorer import build_risk_score
    from backend.services.regime_detector import detect_regimes

    fetcher = DataFetcher()
    data, _ = fetcher.fetch_market_data()
    data["Risk_Score"] = build_risk_score(data)
    _, regime = detect_regimes(data)

    vix = float(data["VIX"].iloc[-1]) if "VIX" in data.columns else 20.0
    sp500_1m = float(data["SP500"].pct_change(21).iloc[-1]) * 100
    sp500_3m = float(data["SP500"].pct_change(63).iloc[-1]) * 100

    # YTD return: compare current price to last trading day of previous year
    sp500_ytd = 0.0
    try:
        import pandas as pd
        sp500_series = data["SP500"].dropna()
        now = sp500_series.index[-1]
        year_start = pd.Timestamp(year=now.year, month=1, day=1)
        prev_year_prices = sp500_series[sp500_series.index < year_start]
        if len(prev_year_prices) > 0:
            sp500_ytd = float((sp500_series.iloc[-1] / prev_year_prices.iloc[-1] - 1) * 100)
    except (KeyError, IndexError, ValueError, TypeError) as e:
        logger.debug("YTD return calculation failed: %s", e)

    yield_curve = None
    if "T10Y" in data.columns and "T3M" in data.columns:
        yield_curve = float(data["T10Y"].iloc[-1] - data["T3M"].iloc[-1])

    # Crash model predictions
    crash_3m = None
    crash_12m = None
    try:
        from backend.services.crash_model import CrashPredictor
        from backend.config import MODEL_DIR
        model_path = MODEL_DIR / "crash_model.pkl"
        if model_path.exists():
            from engine.training.features import build_feature_matrix
            predictor = CrashPredictor()
            predictor.load_model(str(model_path))
            fred_data = fetcher.fetch_fred_data()
            features = build_feature_matrix(data, fred_data=fred_data)
            available = [f for f in predictor.feature_names if f in features.columns]
            latest = features[available].iloc[[-1]]
            for h in predictor.lgb_models:
                prob = float(predictor.predict_proba(latest, h)[0]) * 100
                if h == "3m":
                    crash_3m = prob
                elif h == "12m":
                    crash_12m = prob
    except (ImportError, FileNotFoundError, ValueError, KeyError) as e:
        logger.debug("Crash model unavailable in screener signal: %s", e)

    # External consensus
    external = None
    try:
        from backend.services.external_validator import validate_external
        fred_data_ext = fetcher.fetch_fred_data()
        ext = validate_external(fred_data_ext, crash_12m / 100 if crash_12m else None, regime)
        external = ext.consensus_direction
    except (ImportError, KeyError, TypeError, ValueError) as e:
        logger.debug("External validation unavailable: %s", e)

    sig = get_market_signal(
        crash_prob_3m=crash_3m,
        crash_prob_12m=crash_12m,
        regime=regime,
        risk_score=float(data["Risk_Score"].iloc[-1]),
        sp500_1m_return=sp500_1m,
        sp500_3m_return=sp500_3m,
        sp500_ytd_return=sp500_ytd,
        vix=vix,
        yield_curve=yield_curve,
        external_consensus=external,
    )
    # Attach raw crash_3m so callers can pass it to MC simulation
    sig["_crash_3m_pct"] = crash_3m
    return sig


@router.get("/{ticker}")
async def get_stock_analysis(ticker: str):
    """Per-ticker projection using fundamental-aware Monte Carlo."""
    ticker = ticker.upper()
    if not _TICKER_RE.match(ticker):
        raise HTTPException(status_code=422, detail="Invalid ticker format")
    cache_key = f"stock:{ticker}"
    cached = cache_get(cache_key, _CACHE_TTL["ttl_stock"])
    if cached is not None:
        return cached

    try:
        result = await asyncio.to_thread(_analyze_stock, ticker)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Could not analyze {ticker}")
        cache_set(cache_key, result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("stock analysis failed for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=str(e))


def _analyze_stock(ticker: str) -> dict:
    from backend.services.stock_analyzer import analyze_stock
    from backend.services.signal_engine import get_stock_signal

    # Compute market-level signal (includes crash probability)
    market_sig = _compute_market_signal()

    # Extract crash probability for MC jump rate modulation
    crash_3m_pct = market_sig.get("_crash_3m_pct")
    crash_prob_for_mc = crash_3m_pct / 100.0 if crash_3m_pct is not None else None

    # Run MC simulation with crash-aware jump frequency
    result = analyze_stock(ticker, ml_crash_prob=crash_prob_for_mc)
    if result is None:
        return None

    # Compute sector momentum for this stock
    stock_sector = result.get("sector", "Unknown")
    sec_mom = _compute_sector_momentum().get(stock_sector, 0.0)

    # Extract forward PE from key_stats if available
    fwd_pe = None
    key_stats = result.get("key_stats")
    if key_stats and "pe_forward" in key_stats:
        fwd_pe = key_stats["pe_forward"]

    # Compute per-stock signal (same logic as screener)
    stock_sig = get_stock_signal(
        market_signal=market_sig,
        beta=result.get("beta", 1.0),
        analyst_target=result.get("analyst_target"),
        current_price=result.get("current_price", 0),
        sector_momentum=sec_mom,
        pe_ratio=result.get("pe_ratio"),
        forward_pe=fwd_pe,
    )

    # Attach signal and crash fields to the result
    result["signal_action"] = stock_sig["action"]
    result["signal_confidence"] = stock_sig["confidence"]
    result["signal_score"] = stock_sig["composite_score"]
    result["signal_components"] = stock_sig.get("components", {})
    result["signal_reasons"] = stock_sig.get("reasons", [])
    result["crash_prob_3m"] = crash_3m_pct
    result["market_signal"] = market_sig["action"]

    return result


@router.get("/{ticker}/signal")
async def get_stock_signal_endpoint(ticker: str):
    """Per-stock buy/sell signal (market signal + stock-specific adjustments)."""
    ticker = ticker.upper()
    if not _TICKER_RE.match(ticker):
        raise HTTPException(status_code=422, detail="Invalid ticker format")
    cache_key = f"stock_signal:{ticker}"
    cached = cache_get(cache_key, _CACHE_TTL["ttl_stock"])
    if cached is not None:
        return cached

    try:
        result = await asyncio.to_thread(_stock_signal, ticker)
        cache_set(cache_key, result)
        return result
    except Exception as e:
        logger.error("stock signal failed for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=str(e))


def _stock_signal(ticker: str) -> dict:
    from backend.services.stock_analyzer import analyze_stock
    from backend.services.signal_engine import get_stock_signal

    # Reuse the shared market signal computation
    market_sig = _compute_market_signal()

    # Get stock data — pass crash probability so MC can modulate jump frequency
    crash_3m_pct = market_sig.get("_crash_3m_pct")
    crash_prob_for_mc = crash_3m_pct / 100.0 if crash_3m_pct is not None else None
    stock_data = analyze_stock(ticker, ml_crash_prob=crash_prob_for_mc)
    if stock_data is None:
        return {"ticker": ticker, "action": "Hold", "confidence": 0, "error": "Could not analyze stock"}

    # Compute sector momentum for this stock
    stock_sector = stock_data.get("sector", "Unknown")
    sec_mom = _compute_sector_momentum().get(stock_sector, 0.0)

    # Extract forward PE from key_stats
    fwd_pe = None
    key_stats = stock_data.get("key_stats")
    if key_stats and "pe_forward" in key_stats:
        fwd_pe = key_stats["pe_forward"]

    signal = get_stock_signal(
        market_signal=market_sig,
        beta=stock_data.get("beta", 1.0),
        analyst_target=stock_data.get("analyst_target"),
        current_price=stock_data.get("current_price", 0),
        sector_momentum=sec_mom,
        pe_ratio=stock_data.get("pe_ratio"),
        forward_pe=fwd_pe,
    )
    signal["ticker"] = ticker
    signal["name"] = stock_data.get("name", ticker)
    signal["current_price"] = stock_data.get("current_price")
    signal["market_action"] = market_sig["action"]
    return signal


@router.get("/{ticker}/shap")
async def get_stock_shap(ticker: str):
    """SHAP explanation for how crash model views this ticker's risk."""
    ticker = ticker.upper()
    if not _TICKER_RE.match(ticker):
        raise HTTPException(status_code=422, detail="Invalid ticker format")
    cache_key = f"stock_shap:{ticker}"
    cached = cache_get(cache_key, _CACHE_TTL["ttl_stock"])
    if cached is not None:
        return cached

    try:
        result = await asyncio.to_thread(_stock_shap, ticker)
        cache_set(cache_key, result)
        return result
    except Exception as e:
        logger.error("stock shap failed for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=str(e))


def _stock_shap(ticker: str) -> dict:
    from backend.config import MODEL_DIR
    from backend.services.crash_model import CrashPredictor
    from backend.services.shap_explainer import explain_prediction

    model_path = MODEL_DIR / "crash_model.pkl"
    if not model_path.exists():
        return {
            "ticker": ticker,
            "status": "model_not_trained",
            "message": "Crash model not yet trained",
        }

    # SHAP is market-level (not per-ticker), but we label it for the ticker
    from backend.services.data_fetcher import DataFetcher
    from engine.training.features import build_feature_matrix

    predictor = CrashPredictor()
    predictor.load_model(str(model_path))

    fetcher = DataFetcher()
    data, _ = fetcher.fetch_market_data()
    fred_data = fetcher.fetch_fred_data()

    features = build_feature_matrix(data, fred_data=fred_data)
    available = [f for f in predictor.feature_names if f in features.columns]
    latest = features[available].iloc[[-1]]

    explanation = explain_prediction(predictor, latest, horizon="3m")
    explanation["ticker"] = ticker

    return explanation


@router.get("/{ticker}/sentiment")
async def get_stock_sentiment(ticker: str):
    """FinBERT-powered news sentiment analysis for a ticker."""
    ticker = ticker.upper()
    if not _TICKER_RE.match(ticker):
        raise HTTPException(status_code=422, detail="Invalid ticker format")
    cache_key = f"stock_sentiment:{ticker}"
    cached = cache_get(cache_key, _CACHE_TTL["ttl_stock"])
    if cached is not None:
        return cached

    try:
        result = await asyncio.to_thread(_stock_sentiment, ticker)
        if result is None:
            raise HTTPException(status_code=404, detail=f"No sentiment data for {ticker}")
        cache_set(cache_key, result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("stock sentiment failed for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=str(e))


def _stock_sentiment(ticker: str) -> dict:
    from backend.services.sentiment_analyzer import analyze_sentiment
    return analyze_sentiment(ticker)
