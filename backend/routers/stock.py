"""
Stock Analysis Router
=======================

GET /api/stock/screener             — Top stocks screener (batch analysis)
GET /api/stock/{ticker}             — Per-ticker projection + risk metrics
GET /api/stock/{ticker}/shap        — SHAP explanation for ticker
GET /api/stock/{ticker}/sentiment   — FinBERT news sentiment analysis
GET /api/stock/{ticker}/insiders    — Insider trading signal
GET /api/stock/{ticker}/fundamentals — SEC EDGAR fundamentals
GET /api/stock/{ticker}/technicals  — Technical analysis (RSI, MACD, Bollinger, ADX)
GET /api/stock/{ticker}/valuation   — Relative valuation vs sector peers (Koyfin-style)
GET /api/stock/{ticker}/patterns    — Chart pattern recognition (TradingView-style)
GET /api/stock/{ticker}/volatility  — Volatility analytics (Bloomberg-style vol cone, GARCH)
GET /api/stock/{ticker}/dividends   — Dividend intelligence (Morningstar-style)
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
    universe_cfg = config.get("stock_universe", {})
    per_sector = universe_cfg.get("screener_per_sector", 5)
    max_tickers = universe_cfg.get("screener_max_tickers", 80)
    all_tickers = set(DEFAULT_WATCHLIST)
    for sector_tickers in SECTOR_STOCK_MAP.values():
        for t in sector_tickers[:per_sector]:
            all_tickers.add(t)
    # Performance guard: cap total tickers
    if len(all_tickers) > max_tickers:
        all_tickers = set(sorted(all_tickers)[:max_tickers])

    # Extract crash probability for MC jump rate modulation
    crash_3m_pct = market_sig.get("_crash_3m_pct")
    crash_prob_for_mc = crash_3m_pct / 100.0 if crash_3m_pct is not None else None

    # Extract HMM regime data for per-stock MC simulations
    hmm_means = market_sig.get("_hmm_state_means")
    hmm_probs = market_sig.get("_hmm_regime_probs")
    hmm_vols = market_sig.get("_hmm_state_vols")
    _drift_sev = market_sig.get("_drift_severity")

    # Parallel stock analysis — ~3-5x faster than sequential
    t0 = time.perf_counter()
    sorted_tickers = sorted(all_tickers)
    perf_cfg = config["performance"]
    max_workers = min(perf_cfg["screener_max_workers"], len(sorted_tickers))

    def _analyze_one(ticker: str) -> dict | None:
        """Analyze a single ticker and compute its signal. Thread-safe."""
        try:
            from backend.services.signal_engine import adjust_crash_prob_for_stock

            # Per-stock crash prob: adjust market-level by stock risk factors
            # We need beta/vol before calling analyze_stock, but analyze_stock
            # computes them internally. To avoid double-fetching, we pass the
            # market-level crash prob to MC, then use the returned beta/vol
            # for signal differentiation. The MC uses market crash prob for
            # jump rate modulation; the signal engine uses adjusted crash prob
            # for signal differentiation — these are complementary.
            r = analyze_stock(
                ticker, ml_crash_prob=crash_prob_for_mc,
                hmm_state_means=hmm_means, hmm_regime_probs=hmm_probs,
                hmm_state_vols=hmm_vols, drift_severity=_drift_sev,
            )
            if r is None:
                return None

            stock_sector = r.get("sector", "Unknown")
            sec_mom = sector_momentum.get(stock_sector, 0.0)

            fwd_pe = None
            key_stats = r.get("key_stats")
            if key_stats and "pe_forward" in key_stats:
                fwd_pe = key_stats["pe_forward"]

            # Extract stock-level risk factors for signal differentiation
            stock_vol = r.get("volatility", 20.0) / 100.0  # stored as pct
            stock_dd = None
            price_hist = r.get("price_history")
            if price_hist and len(price_hist) > 10:
                prices_arr = [p["price"] for p in price_hist]
                peak = max(prices_arr)
                current = prices_arr[-1]
                stock_dd = (current / peak - 1) * 100 if peak > 0 else 0.0

            # Use daily-resolution momentum from stock_analyzer (not weekly-sampled)
            stock_mom_1m = r.get("momentum_1m")
            stock_mom_3m = r.get("momentum_3m")

            # Compute per-stock adjusted crash prob for the result
            stock_crash_prob = None
            if crash_prob_for_mc is not None:
                stock_crash_prob = adjust_crash_prob_for_stock(
                    crash_prob_for_mc, r.get("beta", 1.0), stock_vol,
                    stock_dd if stock_dd is not None else 0.0,
                )

            # Options-implied signal (forward-looking: IV skew, P/C ratio)
            options_score = None
            try:
                from backend.services.options_intelligence import get_iv_signal
                iv_sig = get_iv_signal(ticker)
                if iv_sig.get("available"):
                    options_score = iv_sig.get("score")
            except Exception as e:
                logger.debug("options signal skip %s: %s", ticker, e)

            # Earnings quality signal (beat rate, surprise trend, growth)
            earnings_score = None
            try:
                from backend.services.earnings_intelligence import get_earnings_summary
                earn = get_earnings_summary(ticker)
                if earn and "signal" in earn:
                    earnings_score = earn["signal"].get("score")
            except Exception as e:
                logger.debug("earnings signal skip %s: %s", ticker, e)

            # Insider trading signal (cluster buy detection)
            insider_score = None
            try:
                from backend.services.insider_trading import get_insider_transactions, compute_insider_signal
                insider_data = get_insider_transactions(ticker, lookback_days=90)
                insider_sig = compute_insider_signal(insider_data)
                insider_score = insider_sig.get("signal")
            except Exception as e:
                logger.debug("insider signal skip %s: %s", ticker, e)

            # Technical analysis signal (RSI, MACD, Bollinger, ADX composite)
            _ta_score = None
            _ta_ind_result = None
            try:
                import yfinance as yf
                from backend.services.technical_analysis import get_ta_signal, compute_technical_indicators
                _t = yf.Ticker(ticker)
                _hist = _t.history(period="1y")
                if _hist is not None and len(_hist) >= 50:
                    _ta_ind_result = compute_technical_indicators(
                        _hist["Close"], _hist.get("Volume"), _hist["High"], _hist["Low"],
                    )
                    _ta_sig = get_ta_signal(_ta_ind_result)
                    _ta_score = _ta_sig.get("score")
            except Exception as e:
                logger.debug("ta signal skip %s: %s", ticker, e)

            stock_sig = get_stock_signal(
                market_signal=market_sig,
                beta=r.get("beta", 1.0),
                analyst_target=r.get("analyst_target"),
                current_price=r.get("current_price", 0),
                sector_momentum=sec_mom,
                pe_ratio=r.get("pe_ratio"),
                forward_pe=fwd_pe,
                stock_vol=stock_vol,
                drawdown_from_peak=stock_dd,
                stock_momentum_1m=stock_mom_1m,
                stock_momentum_3m=stock_mom_3m,
                options_signal_score=options_score,
                earnings_signal_score=earnings_score,
                insider_signal_score=insider_score,
                ta_signal_score=_ta_score,
            )

            # Liquidity score (lightweight — uses cached price data from analyze_stock)
            _liq_score = None
            _liq_tier = None
            try:
                from backend.services.liquidity_risk import compute_liquidity_metrics
                _liq = compute_liquidity_metrics(ticker, lookback_days=252)
                if _liq:
                    _liq_score = _liq["score"]["composite"]
                    _liq_tier = _liq["score"]["tier"]
            except Exception as e:
                logger.debug("screener liquidity skip %s: %s", ticker, e)

            # Momentum rank from cached rankings
            _mom_rank = None
            _mom_percentile = None
            try:
                from backend.services.cross_sectional_momentum import get_momentum_score
                from backend.cache import cache_get as _cg2
                _cached_mom = _cg2("momentum_rankings", 900)
                if _cached_mom:
                    _ms = get_momentum_score(ticker, _cached_mom)
                    if _ms:
                        _mom_rank = _ms.get("rank")
                        _mom_percentile = _ms.get("percentile")
            except Exception as e:
                logger.debug("screener momentum skip %s: %s", ticker, e)

            # Drawdown stats (reuse price history already fetched)
            _max_dd = None
            _current_dd = None
            try:
                from backend.services.drawdown_analyzer import full_drawdown_analysis
                _dd = full_drawdown_analysis(ticker, period="5y")
                if _dd:
                    _dds = _dd.get("drawdown_summary", {})
                    _max_dd = _dds.get("max_drawdown_pct")
                    _current_dd = _dds.get("current_drawdown_pct")
            except Exception as e:
                logger.debug("screener drawdown skip %s: %s", ticker, e)

            # TA details for display (reuse _ta_sig_result computed above)
            _rsi = None
            _trend = None
            if _ta_score is not None:
                try:
                    if _ta_ind_result is not None:
                        _rsi = _ta_ind_result.get("momentum", {}).get("rsi_14")
                        _trend = _ta_ind_result.get("trend", {}).get("trend_direction")
                except Exception:
                    pass

            # Chart pattern bias (lightweight summary for screener)
            _pattern_bias = None
            _pattern_count = None
            try:
                from backend.services.pattern_recognition import get_ticker_patterns
                _pat = get_ticker_patterns(ticker)
                if _pat:
                    _pattern_bias = _pat.get("bias")
                    _pattern_count = _pat.get("pattern_count", 0)
            except Exception as e:
                logger.debug("screener pattern skip %s: %s", ticker, e)

            # Dividend yield for screener
            _div_yield = None
            _div_safety = None
            try:
                from backend.services.dividend_intelligence import get_dividend_summary
                _div = get_dividend_summary(ticker)
                if _div:
                    _div_yield = _div.get("trailing_yield")
                    _div_safety = _div.get("safety_grade")
            except Exception as e:
                logger.debug("screener dividend skip %s: %s", ticker, e)

            # Factor style classification (value/growth/blend) — lightweight
            _factor_style = None
            _factor_alpha = None
            try:
                fe = r.get("factor_exposure")
                if fe:
                    _factor_style = fe.get("style", {}).get("value")
                    _factor_alpha = fe.get("alpha_annual")
            except Exception:
                pass

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
                "crash_prob_3m": round(stock_crash_prob * 100, 2) if stock_crash_prob else None,
                # MC return fields — needed by signal_analytics for risk_reward computation
                "mc_median_5y_return": r.get("mc_median_5y_return"),
                "mc_p10_5y_return": r.get("mc_p10_5y_return"),
                "mc_p90_5y_return": r.get("mc_p90_5y_return"),
                "signal_action": stock_sig["action"],
                "signal_confidence": stock_sig["confidence"],
                "signal_score": stock_sig["composite_score"],
                "signal_components": stock_sig.get("components"),
                "signal_conviction": stock_sig.get("conviction"),
                "prediction_confidence": r.get("prediction_confidence", {}).get("grade"),
                "prediction_confidence_score": r.get("prediction_confidence", {}).get("score"),
                # Per-stock analytics (cycle_068 integration)
                "liquidity_score": _liq_score,
                "liquidity_tier": _liq_tier,
                "momentum_rank": _mom_rank,
                "momentum_percentile": _mom_percentile,
                "rsi_14": _rsi,
                "trend_direction": _trend,
                "max_drawdown_pct": _max_dd,
                "current_drawdown_pct": _current_dd,
                "pattern_bias": _pattern_bias,
                "pattern_count": _pattern_count,
                "dividend_yield": _div_yield,
                "dividend_safety": _div_safety,
                # Signal sub-scores (cycle_080 integration — previously computed but not exposed)
                "options_score": options_score,
                "earnings_score": earnings_score,
                "insider_score": insider_score,
                "ta_score": _ta_score,
                # Factor style (value/growth/blend from FF5 decomposition)
                "factor_style": _factor_style,
                "factor_alpha": round(_factor_alpha * 100, 2) if _factor_alpha is not None else None,
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

    # Enrich with signal analytics (ranking, risk-reward, opportunity score, concentration)
    try:
        from backend.services.signal_analytics import enrich_screener_signals
        enriched = enrich_screener_signals(stocks, market_sig)
        stocks = enriched["stocks"]
        signal_analytics = enriched["analytics"]
    except Exception as e:
        logger.warning("signal analytics enrichment failed: %s", e)
        signal_analytics = None

    # Sort by opportunity_score (composite of signal, Sharpe, risk-reward, confidence)
    # Falls back to Sharpe if opportunity_score is not available
    stocks.sort(key=lambda x: x.get("opportunity_score", x.get("sharpe", 0)), reverse=True)

    result = {"stocks": stocks, "count": len(stocks), "market_signal": market_sig}
    if signal_analytics:
        result["signal_analytics"] = signal_analytics
    return result


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
    from backend.services.regime_detector import detect_regimes, fit_hmm_for_mc

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

    # Drawdown from 52-week high
    sp500_drawdown = None
    if "SP500" in data.columns:
        from backend.services.signal_engine import compute_drawdown_pct
        sp500_drawdown = compute_drawdown_pct(data["SP500"])

    # Crash model predictions + drift severity (share feature matrix)
    crash_3m = None
    crash_12m = None
    _drift_severity = None
    try:
        from backend.services.crash_model import CrashPredictor
        from backend.config import MODEL_DIR
        model_path = MODEL_DIR / "crash_model.pkl"
        if model_path.exists():
            from engine.training.features import build_feature_matrix
            predictor = CrashPredictor()
            predictor.load_model(str(model_path))
            fred_data = fetcher.fetch_fred_data()
            _feature_matrix = build_feature_matrix(data, fred_data=fred_data)
            available = [f for f in predictor.feature_names if f in _feature_matrix.columns]
            latest = _feature_matrix[available].iloc[[-1]]
            for h in predictor.lgb_models:
                prob = float(predictor.predict_proba(latest, h)[0]) * 100
                if h == "3m":
                    crash_3m = prob
                elif h == "12m":
                    crash_12m = prob
            # Drift detection (importance-weighted, reuses feature matrix)
            try:
                from backend.services.drift_detector import DriftDetector
                _feat_imp = None
                if hasattr(predictor, "get_top_features"):
                    try:
                        top = predictor.get_top_features(n=200)
                        _feat_imp = dict(top) if top else None
                    except Exception:
                        pass
                _drift_report = DriftDetector.from_multi_scale(
                    _feature_matrix, feature_importances=_feat_imp,
                )
                _drift_severity = _drift_report.get("effective_severity",
                                                     _drift_report.get("severity"))
            except Exception as e:
                logger.debug("Drift detection unavailable in screener: %s", e)
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

    # Economic surprise signal (from FRED actual vs trend)
    _eco_surprise = None
    try:
        from backend.services.economic_surprise import compute_surprise_index
        eco = compute_surprise_index()
        if eco:
            _eco_surprise = eco.get("composite_score")
    except Exception as e:
        logger.debug("Economic surprise unavailable: %s", e)

    # Systemic risk signal (turbulence + absorption ratio → single score)
    _systemic_score = None
    try:
        from backend.services.systemic_risk import get_systemic_risk_signal
        _systemic_score = get_systemic_risk_signal(data)
    except Exception as e:
        logger.debug("Systemic risk signal unavailable: %s", e)

    # Momentum breadth (fraction of stocks with positive 3M momentum)
    _mom_breadth = None
    try:
        from backend.cache import cache_get as _cg
        cached_mom = _cg("momentum_rankings", 900)
        if cached_mom and "rankings" in cached_mom:
            rankings = cached_mom["rankings"]
            n_positive = sum(1 for r in rankings if r.get("composite_score", 0) > 0)
            _mom_breadth = n_positive / len(rankings) if rankings else None
    except Exception as e:
        logger.debug("Momentum breadth unavailable: %s", e)

    # VIX term structure signal
    _vts_signal = None
    try:
        from backend.services.regime_detector import get_vix_term_structure_state
        vts = get_vix_term_structure_state(data)
        if vts.get("available"):
            _vts_signal = vts.get("signal")
    except Exception as e:
        logger.debug("VIX term structure unavailable: %s", e)

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
        drawdown_pct=sp500_drawdown,
        drift_severity=_drift_severity,
        economic_surprise=_eco_surprise,
        momentum_breadth=_mom_breadth,
        systemic_risk_score=_systemic_score,
        vix_term_structure_signal=_vts_signal,
    )
    # Attach raw crash_3m so callers can pass it to MC simulation
    sig["_crash_3m_pct"] = crash_3m
    sig["_drift_severity"] = _drift_severity

    # Fit HMM once — callers pass these to per-stock MC simulations
    hmm_data = fit_hmm_for_mc(data)
    sig["_hmm_state_means"] = hmm_data["state_means"]
    sig["_hmm_regime_probs"] = hmm_data["regime_probs"]
    sig["_hmm_state_vols"] = hmm_data["state_vols"]

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
    from backend.services.signal_engine import get_stock_signal, adjust_crash_prob_for_stock

    # Compute market-level signal (includes crash probability)
    market_sig = _compute_market_signal()

    # Extract crash probability for MC jump rate modulation
    crash_3m_pct = market_sig.get("_crash_3m_pct")
    crash_prob_for_mc = crash_3m_pct / 100.0 if crash_3m_pct is not None else None

    # Run MC simulation with crash-aware jump frequency + HMM regime conditioning
    result = analyze_stock(
        ticker, ml_crash_prob=crash_prob_for_mc,
        hmm_state_means=market_sig.get("_hmm_state_means"),
        hmm_regime_probs=market_sig.get("_hmm_regime_probs"),
        hmm_state_vols=market_sig.get("_hmm_state_vols"),
        drift_severity=market_sig.get("_drift_severity"),
    )
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

    # Extract stock-level risk factors for per-stock crash prob and signal
    stock_vol = result.get("volatility", 20.0) / 100.0
    stock_dd = None
    price_hist = result.get("price_history")
    if price_hist and len(price_hist) > 10:
        prices_arr = [p["price"] for p in price_hist]
        peak = max(prices_arr)
        current = prices_arr[-1]
        stock_dd = (current / peak - 1) * 100 if peak > 0 else 0.0

    # Use daily-resolution momentum from stock_analyzer (not weekly-sampled)
    stock_mom_1m = result.get("momentum_1m")
    stock_mom_3m = result.get("momentum_3m")

    # Per-stock crash probability
    if crash_prob_for_mc is not None:
        stock_crash_prob = adjust_crash_prob_for_stock(
            crash_prob_for_mc, result.get("beta", 1.0), stock_vol,
            stock_dd if stock_dd is not None else 0.0,
        )
        result["crash_prob_3m"] = round(stock_crash_prob * 100, 2)

    # Options-implied signal (forward-looking: IV skew, P/C ratio)
    options_score = None
    try:
        from backend.services.options_intelligence import get_iv_signal
        iv_sig = get_iv_signal(ticker)
        if iv_sig.get("available"):
            options_score = iv_sig.get("score")
    except Exception as e:
        logger.debug("options signal skip %s: %s", ticker, e)

    # Earnings quality signal (beat rate, surprise trend, growth)
    earnings_score = None
    try:
        from backend.services.earnings_intelligence import get_earnings_summary
        earn = get_earnings_summary(ticker)
        if earn and "signal" in earn:
            earnings_score = earn["signal"].get("score")
    except Exception as e:
        logger.debug("earnings signal skip %s: %s", ticker, e)

    # Insider trading signal — compute BEFORE get_stock_signal so it's a signal input
    insider_score = None
    insider_sig_data = None
    try:
        from backend.services.insider_trading import get_insider_transactions, compute_insider_signal
        insider_data = get_insider_transactions(ticker, lookback_days=90)
        insider_sig_data = compute_insider_signal(insider_data)
        insider_score = insider_sig_data.get("signal")
    except Exception as e:
        logger.debug("insider signal skip %s: %s", ticker, e)

    # Technical analysis — compute once, use for both signal composite and display
    ta_score = None
    _ta_sig_result = None
    _ta_ind_result = None
    try:
        import yfinance as yf
        from backend.services.technical_analysis import get_ta_signal, compute_technical_indicators
        t = yf.Ticker(ticker)
        hist = t.history(period="1y")
        if hist is not None and len(hist) >= 50:
            _ta_ind_result = compute_technical_indicators(
                hist["Close"], hist.get("Volume"), hist["High"], hist["Low"],
            )
            _ta_sig_result = get_ta_signal(_ta_ind_result)
            ta_score = _ta_sig_result.get("score")
    except Exception as e:
        logger.debug("ta signal for composite skip %s: %s", ticker, e)

    # Compute per-stock signal (same logic as screener)
    stock_sig = get_stock_signal(
        market_signal=market_sig,
        beta=result.get("beta", 1.0),
        analyst_target=result.get("analyst_target"),
        current_price=result.get("current_price", 0),
        sector_momentum=sec_mom,
        pe_ratio=result.get("pe_ratio"),
        forward_pe=fwd_pe,
        stock_vol=stock_vol,
        drawdown_from_peak=stock_dd,
        stock_momentum_1m=stock_mom_1m,
        stock_momentum_3m=stock_mom_3m,
        options_signal_score=options_score,
        earnings_signal_score=earnings_score,
        insider_signal_score=insider_score,
        ta_signal_score=ta_score,
    )

    # Attach signal and crash fields to the result
    result["signal_action"] = stock_sig["action"]
    result["signal_confidence"] = stock_sig["confidence"]
    result["signal_score"] = stock_sig["composite_score"]
    result["signal_components"] = stock_sig.get("components", {})
    result["signal_conviction"] = stock_sig.get("conviction", {})
    result["signal_reasons"] = stock_sig.get("reasons", [])
    result["crash_prob_3m"] = crash_3m_pct
    result["market_signal"] = market_sig["action"]

    # Attach insider signal data for display
    if insider_sig_data:
        result["insider_signal"] = insider_sig_data

    # Liquidity score
    try:
        from backend.services.liquidity_risk import compute_liquidity_metrics
        liq = compute_liquidity_metrics(ticker, lookback_days=252)
        if liq:
            result["liquidity"] = {
                "score": liq["score"]["composite"],
                "tier": liq["score"]["tier"],
                "amihud": liq["metrics"]["amihud_illiquidity"],
                "avg_dollar_volume_mm": liq["metrics"]["avg_dollar_volume_mm"],
                "lvar_95": liq["risk"]["lvar_95"],
            }
    except Exception as e:
        logger.debug("liquidity skip %s: %s", ticker, e)

    # Cross-sectional momentum rank
    try:
        from backend.services.cross_sectional_momentum import get_momentum_score
        from backend.cache import cache_get as _cg
        cached_rankings = _cg("momentum_rankings", 900)
        if cached_rankings:
            mom_score = get_momentum_score(ticker, cached_rankings)
            if mom_score:
                result["momentum_rank"] = mom_score
    except Exception as e:
        logger.debug("momentum rank skip %s: %s", ticker, e)

    # Technical analysis signal (reuse precomputed TA from above)
    if _ta_sig_result is not None:
        result["technical_signal"] = _ta_sig_result
        if _ta_ind_result is not None:
            result["rsi_14"] = _ta_ind_result.get("momentum", {}).get("rsi_14")
            result["trend_direction"] = _ta_ind_result.get("trend", {}).get("trend_direction")

    # Google Trends attention for this ticker
    try:
        from backend.services.trends_sentiment import get_ticker_attention
        attention = get_ticker_attention(ticker, company_name=result.get("name"))
        if attention:
            result["trends_attention"] = {
                "attention_level": attention.get("attention_level"),
                "attention_zscore": attention.get("attention_zscore"),
                "interpretation": attention.get("interpretation"),
            }
    except Exception as e:
        logger.debug("trends attention skip %s: %s", ticker, e)

    # Drawdown analysis (historical drawdown recovery stats)
    try:
        from backend.services.drawdown_analyzer import full_drawdown_analysis
        dd_analysis = full_drawdown_analysis(ticker, period="5y")
        if dd_analysis:
            dd_summary = dd_analysis.get("drawdown_summary", {})
            rolling = dd_analysis.get("rolling_risk", {})
            result["drawdown_analysis"] = {
                "total_drawdowns": dd_summary.get("total_drawdowns"),
                "max_drawdown_pct": dd_summary.get("max_drawdown_pct"),
                "avg_recovery_days": dd_summary.get("avg_recovery_days"),
                "current_drawdown_pct": dd_summary.get("current_drawdown_pct"),
                "rolling_sharpe_1y": rolling.get("rolling_sharpe_1y"),
                "rolling_sortino_1y": rolling.get("rolling_sortino_1y"),
            }
    except Exception as e:
        logger.debug("drawdown analysis skip %s: %s", ticker, e)

    # Relative valuation (peer comparison summary)
    try:
        from backend.services.relative_valuation import get_valuation_summary
        val_summary = get_valuation_summary(ticker)
        if val_summary:
            result["relative_valuation"] = val_summary
    except Exception as e:
        logger.debug("relative valuation skip %s: %s", ticker, e)

    # Dividend intelligence (Morningstar-style summary)
    try:
        from backend.services.dividend_intelligence import get_dividend_summary
        div_data = get_dividend_summary(ticker)
        if div_data:
            result["dividend_intelligence"] = div_data
    except Exception as e:
        logger.debug("dividend intelligence skip %s: %s", ticker, e)

    # Volatility analytics (Bloomberg-style vol summary)
    try:
        from backend.services.volatility_analytics import get_vol_summary
        vol_data = get_vol_summary(ticker)
        if vol_data:
            result["volatility_analytics"] = vol_data
    except Exception as e:
        logger.debug("vol analytics skip %s: %s", ticker, e)

    # Chart pattern recognition (TradingView-style)
    try:
        from backend.services.pattern_recognition import get_ticker_patterns
        pat = get_ticker_patterns(ticker)
        if pat:
            result["chart_patterns"] = {
                "patterns": pat.get("patterns", []),
                "pattern_count": pat.get("pattern_count", 0),
                "bias": pat.get("bias", "neutral"),
                "strongest_pattern": pat.get("strongest_pattern"),
                "support_resistance": pat.get("support_resistance"),
            }
    except Exception as e:
        logger.debug("pattern recognition skip %s: %s", ticker, e)

    # LPPL Bubble detection (Sornette) — per-stock bubble thermometer
    try:
        import pandas as pd
        from backend.services.bubble_detector import get_bubble_status
        price_hist = result.get("price_history", {}).get("prices")
        if price_hist and len(price_hist) > 120:
            bubble_prices = pd.Series(
                [p["close"] for p in price_hist],
                index=pd.to_datetime([p["date"] for p in price_hist]),
            )
            bubble = get_bubble_status(bubble_prices, ticker=ticker)
            if bubble:
                result["bubble_indicator"] = {
                    "confidence": bubble.get("confidence"),
                    "is_bubble": bubble.get("is_bubble"),
                    "status": bubble.get("status"),
                    "tc_date": bubble.get("tc_date"),
                }
    except Exception as e:
        logger.debug("bubble detection skip %s: %s", ticker, e)

    # Survival model crash timing (Cox PH — beta-adjusted per stock)
    try:
        from backend.services.survival_model import CrashSurvivalModel
        from engine.training.features import build_feature_matrix as _bfm_surv
        from backend.services.data_fetcher import DataFetcher as _DF_surv

        _cache_key_surv = "survival_stock_probs"
        _cached_surv = cache_get(_cache_key_surv, 1800)
        if _cached_surv is not None:
            surv_probs = _cached_surv
        else:
            _f_surv = _DF_surv()
            _d_surv, _ = _f_surv.fetch_market_data()
            _fred_surv = _f_surv.fetch_fred_data()
            _feats_surv = _bfm_surv(_d_surv, fred_data=_fred_surv)
            cox = CrashSurvivalModel()
            train_end = int(len(_feats_surv) * 0.8)
            if cox.train(_feats_surv, _d_surv, train_end).get("success"):
                surv_probs = {}
                for h in ["3m", "6m", "12m"]:
                    surv_probs[h] = float(cox.predict_proba(_feats_surv.iloc[[-1]], h)[0])
                cache_set(_cache_key_surv, surv_probs)
            else:
                surv_probs = None

        if surv_probs:
            stock_beta = result.get("beta", 1.0)
            result["survival_crash_timing"] = {
                h: round(min(p * stock_beta, 0.95) * 100, 1)
                for h, p in surv_probs.items()
            }
    except Exception as e:
        logger.debug("survival model skip %s: %s", ticker, e)

    # Conformal prediction interval for crash probability
    stock_crash = result.get("crash_prob_3m")
    if stock_crash is not None:
        try:
            from backend.services.conformal_predictor import conformal_crash_interval
            interval = conformal_crash_interval(stock_crash / 100.0, horizon="3m")
            if interval:
                result["crash_prob_interval"] = {
                    "lower": round(interval["lower"] * 100, 2),
                    "upper": round(interval["upper"] * 100, 2),
                    "width": round(interval["width"] * 100, 2),
                    "coverage_target": interval.get("coverage_target"),
                }
        except Exception as e:
            logger.debug("conformal interval skip %s: %s", ticker, e)

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

    # Get stock data — pass crash probability + HMM regime data so MC can modulate
    crash_3m_pct = market_sig.get("_crash_3m_pct")
    crash_prob_for_mc = crash_3m_pct / 100.0 if crash_3m_pct is not None else None
    stock_data = analyze_stock(
        ticker, ml_crash_prob=crash_prob_for_mc,
        hmm_state_means=market_sig.get("_hmm_state_means"),
        hmm_regime_probs=market_sig.get("_hmm_regime_probs"),
        hmm_state_vols=market_sig.get("_hmm_state_vols"),
        drift_severity=market_sig.get("_drift_severity"),
    )
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

    # Extract stock-level risk factors
    stock_vol = stock_data.get("volatility", 20.0) / 100.0
    stock_dd = None
    price_hist = stock_data.get("price_history")
    if price_hist and len(price_hist) > 10:
        prices_arr = [p["price"] for p in price_hist]
        peak = max(prices_arr)
        current = prices_arr[-1]
        stock_dd = (current / peak - 1) * 100 if peak > 0 else 0.0

    # Use daily-resolution momentum from stock_analyzer (not weekly-sampled)
    stock_mom_1m = stock_data.get("momentum_1m")
    stock_mom_3m = stock_data.get("momentum_3m")

    # Options-implied signal
    options_score = None
    try:
        from backend.services.options_intelligence import get_iv_signal
        iv_sig = get_iv_signal(ticker)
        if iv_sig.get("available"):
            options_score = iv_sig.get("score")
    except Exception as e:
        logger.debug("options signal skip %s: %s", ticker, e)

    # Earnings quality signal
    earnings_score = None
    try:
        from backend.services.earnings_intelligence import get_earnings_summary
        earn = get_earnings_summary(ticker)
        if earn and "signal" in earn:
            earnings_score = earn["signal"].get("score")
    except Exception as e:
        logger.debug("earnings signal skip %s: %s", ticker, e)

    # Insider trading signal
    insider_score = None
    try:
        from backend.services.insider_trading import get_insider_transactions, compute_insider_signal
        insider_data = get_insider_transactions(ticker, lookback_days=90)
        insider_sig = compute_insider_signal(insider_data)
        insider_score = insider_sig.get("signal")
    except Exception as e:
        logger.debug("insider signal skip %s: %s", ticker, e)

    # Technical analysis signal
    ta_score = None
    try:
        import yfinance as yf
        from backend.services.technical_analysis import get_ta_signal, compute_technical_indicators
        _t = yf.Ticker(ticker)
        _hist = _t.history(period="1y")
        if _hist is not None and len(_hist) >= 50:
            _ta_ind = compute_technical_indicators(
                _hist["Close"], _hist.get("Volume"), _hist["High"], _hist["Low"],
            )
            _ta_sig = get_ta_signal(_ta_ind)
            ta_score = _ta_sig.get("score")
    except Exception as e:
        logger.debug("ta signal skip %s: %s", ticker, e)

    signal = get_stock_signal(
        market_signal=market_sig,
        beta=stock_data.get("beta", 1.0),
        analyst_target=stock_data.get("analyst_target"),
        current_price=stock_data.get("current_price", 0),
        sector_momentum=sec_mom,
        pe_ratio=stock_data.get("pe_ratio"),
        forward_pe=fwd_pe,
        stock_vol=stock_vol,
        drawdown_from_peak=stock_dd,
        stock_momentum_1m=stock_mom_1m,
        stock_momentum_3m=stock_mom_3m,
        options_signal_score=options_score,
        earnings_signal_score=earnings_score,
        insider_signal_score=insider_score,
        ta_signal_score=ta_score,
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


@router.get("/{ticker}/fundamentals")
async def get_stock_fundamentals(ticker: str):
    """SEC EDGAR fundamentals (10-K financials, Piotroski F-Score)."""
    ticker = ticker.upper()
    if not _TICKER_RE.match(ticker):
        raise HTTPException(status_code=422, detail="Invalid ticker format")
    cache_key = f"stock_fundamentals:{ticker}"
    cached = cache_get(cache_key, 86400)  # 24hr — filings rarely change
    if cached is not None:
        return cached

    try:
        result = await asyncio.to_thread(_stock_fundamentals, ticker)
        if result is None:
            raise HTTPException(status_code=404, detail=f"No EDGAR data for {ticker}")
        cache_set(cache_key, result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("fundamentals failed for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=str(e))


def _stock_fundamentals(ticker: str) -> dict:
    from backend.services.fundamentals import get_fundamentals
    return get_fundamentals(ticker)


@router.get("/{ticker}/technicals")
async def get_stock_technicals(ticker: str):
    """Technical analysis: RSI, MACD, Bollinger Bands, ADX, patterns, volume."""
    ticker = ticker.upper()
    if not _TICKER_RE.match(ticker):
        raise HTTPException(status_code=422, detail="Invalid ticker format")
    cache_key = f"stock_technicals:{ticker}"
    cached = cache_get(cache_key, _CACHE_TTL["ttl_stock"])
    if cached is not None:
        return cached

    try:
        result = await asyncio.to_thread(_stock_technicals, ticker)
        if result is None:
            raise HTTPException(status_code=404, detail=f"No price data for {ticker}")
        cache_set(cache_key, result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("technicals failed for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=str(e))


def _stock_technicals(ticker: str) -> dict:
    import yfinance as yf
    from backend.services.technical_analysis import get_ta_summary

    t = yf.Ticker(ticker)
    hist = t.history(period="2y")
    if hist is None or len(hist) < 50:
        return None

    close = hist["Close"]
    high = hist["High"]
    low = hist["Low"]
    volume = hist["Volume"] if "Volume" in hist.columns else None

    summary = get_ta_summary(close, volume, high, low)
    return {
        "ticker": ticker,
        **summary,
    }


@router.get("/{ticker}/insiders")
async def get_insider_trading(ticker: str):
    """Insider trading transactions and signal for a stock."""
    ticker = ticker.upper()
    if not _TICKER_RE.match(ticker):
        raise HTTPException(status_code=422, detail="Invalid ticker format")
    cache_key = f"insiders:{ticker}"
    cached = cache_get(cache_key, _CACHE_TTL["ttl_stock"])
    if cached is not None:
        return cached

    try:
        from backend.services.insider_trading import get_insider_transactions, compute_insider_signal
        transactions = await asyncio.to_thread(get_insider_transactions, ticker)
        signal = compute_insider_signal(transactions)
        result = {
            "ticker": ticker,
            **signal,
            "transactions": transactions,
        }
        cache_set(cache_key, result)
        return result
    except Exception as e:
        logger.error("insider trading failed for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{ticker}/valuation")
async def get_stock_valuation(ticker: str):
    """Relative valuation — Koyfin-style peer comparison with percentile rankings."""
    ticker = ticker.upper()
    if not _TICKER_RE.match(ticker):
        raise HTTPException(status_code=422, detail="Invalid ticker format")
    cache_key = f"stock_valuation:{ticker}"
    cached = cache_get(cache_key, _CACHE_TTL["ttl_stock"])
    if cached is not None:
        return cached

    try:
        result = await asyncio.to_thread(_stock_valuation, ticker)
        if result is None:
            raise HTTPException(status_code=404, detail=f"No valuation data for {ticker}")
        cache_set(cache_key, result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("relative valuation failed for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=str(e))


def _stock_valuation(ticker: str) -> dict:
    from backend.services.relative_valuation import get_relative_valuation
    return get_relative_valuation(ticker)


@router.get("/{ticker}/patterns")
async def get_stock_patterns(ticker: str):
    """Chart pattern recognition — TradingView-style automatic detection.

    Detects double top/bottom, head & shoulders, triangles, wedges,
    plus support/resistance levels with touch counts.
    """
    ticker = ticker.upper()
    if not _TICKER_RE.match(ticker):
        raise HTTPException(status_code=422, detail="Invalid ticker format")
    cache_key = f"stock_patterns:{ticker}"
    cached = cache_get(cache_key, _CACHE_TTL["ttl_stock"])
    if cached is not None:
        return cached

    try:
        result = await asyncio.to_thread(_stock_patterns, ticker)
        if result is None:
            raise HTTPException(status_code=404, detail=f"No price data for {ticker}")
        cache_set(cache_key, result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("pattern recognition failed for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=str(e))


def _stock_patterns(ticker: str) -> dict:
    from backend.services.pattern_recognition import get_ticker_patterns
    result = get_ticker_patterns(ticker)
    if result is None:
        return None
    return result


@router.get("/{ticker}/volatility")
async def get_stock_volatility(ticker: str):
    """Volatility analytics — Bloomberg-style vol cone, term structure, GARCH forecast.

    Returns vol cone (percentile bands at 10d-252d), realized vol term structure,
    vol regime (high/normal/low), vol risk premium (IV vs RV), clustering,
    vol-of-vol, Parkinson/Garman-Klass estimators, and GARCH forward curve.
    """
    ticker = ticker.upper()
    if not _TICKER_RE.match(ticker):
        raise HTTPException(status_code=422, detail="Invalid ticker format")
    cache_key = f"stock_vol:{ticker}"
    cached = cache_get(cache_key, _CACHE_TTL["ttl_stock"])
    if cached is not None:
        return cached

    try:
        result = await asyncio.to_thread(_stock_volatility, ticker)
        if result is None or "error" in result:
            detail = result.get("error", f"No vol data for {ticker}") if result else f"No vol data for {ticker}"
            raise HTTPException(status_code=404, detail=detail)
        cache_set(cache_key, result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("volatility analytics failed for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=str(e))


def _stock_volatility(ticker: str) -> dict:
    from backend.services.volatility_analytics import get_volatility_analytics
    return get_volatility_analytics(ticker)


@router.get("/{ticker}/dividends")
async def get_stock_dividends(ticker: str):
    """Dividend intelligence — Morningstar-style analytics.

    Returns yield, growth rates (1Y/3Y/5Y/10Y CAGR), payout ratios,
    safety score (0-100), aristocrat/champion classification,
    Gordon Growth DDM fair value, income projection, and payment history.
    """
    ticker = ticker.upper()
    if not _TICKER_RE.match(ticker):
        raise HTTPException(status_code=422, detail="Invalid ticker format")
    cache_key = f"stock_dividends:{ticker}"
    cached = cache_get(cache_key, _CACHE_TTL["ttl_stock"])
    if cached is not None:
        return cached

    try:
        result = await asyncio.to_thread(_stock_dividends, ticker)
        if result is None:
            raise HTTPException(status_code=404, detail=f"No dividend data for {ticker}")
        cache_set(cache_key, result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("dividend intelligence failed for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=str(e))


def _stock_dividends(ticker: str) -> dict:
    from backend.services.dividend_intelligence import get_dividend_intelligence
    return get_dividend_intelligence(ticker)


@router.get("/{ticker}/style-box")
async def get_stock_style_box(ticker: str):
    """Morningstar-style 3x3 style box (Small/Mid/Large × Value/Blend/Growth).

    Size from market cap; style from peer-relative z-scores on value vs growth
    metrics. Returns the live cell plus the full 9-cell grid for rendering.
    """
    ticker = ticker.upper()
    if not _TICKER_RE.match(ticker):
        raise HTTPException(status_code=422, detail="Invalid ticker format")
    cache_key = f"stock_stylebox:{ticker}"
    cached = cache_get(cache_key, _CACHE_TTL["ttl_stock"])
    if cached is not None:
        return cached

    try:
        from backend.services.style_box import classify_style_box
        result = await asyncio.to_thread(classify_style_box, ticker)
        if result is None:
            raise HTTPException(status_code=404, detail=f"No style box data for {ticker}")
        cache_set(cache_key, result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("style box failed for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{ticker}/short-interest")
async def get_stock_short_interest(ticker: str):
    """Fintel-style short interest + squeeze diagnostics."""
    ticker = ticker.upper()
    if not _TICKER_RE.match(ticker):
        raise HTTPException(status_code=422, detail="Invalid ticker format")
    cache_key = f"stock_short:{ticker}"
    cached = cache_get(cache_key, _CACHE_TTL["ttl_stock"])
    if cached is not None:
        return cached

    try:
        from backend.services.short_interest import get_short_interest
        result = await asyncio.to_thread(get_short_interest, ticker)
        if result is None:
            raise HTTPException(status_code=404, detail=f"No short interest data for {ticker}")
        cache_set(cache_key, result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("short interest failed for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{ticker}/revisions")
async def get_stock_revisions(ticker: str):
    """Analyst estimate revisions trend (7d/30d/90d upgrades vs downgrades + price target)."""
    ticker = ticker.upper()
    if not _TICKER_RE.match(ticker):
        raise HTTPException(status_code=422, detail="Invalid ticker format")
    cache_key = f"stock_revisions:{ticker}"
    cached = cache_get(cache_key, _CACHE_TTL["ttl_stock"])
    if cached is not None:
        return cached

    try:
        from backend.services.estimate_revisions import get_revisions_trend
        result = await asyncio.to_thread(get_revisions_trend, ticker)
        if result is None:
            raise HTTPException(status_code=404, detail=f"No revisions data for {ticker}")
        cache_set(cache_key, result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("revisions trend failed for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{ticker}/grades")
async def get_stock_grades(ticker: str):
    """Seeking Alpha-style A–F factor report card.

    Grades across Value, Growth, Profitability, Momentum, and Revisions.
    Each factor maps to a sector-relative percentile and letter band.
    """
    ticker = ticker.upper()
    if not _TICKER_RE.match(ticker):
        raise HTTPException(status_code=422, detail="Invalid ticker format")
    cache_key = f"stock_grades:{ticker}"
    cached = cache_get(cache_key, _CACHE_TTL["ttl_stock"])
    if cached is not None:
        return cached

    try:
        from backend.services.factor_grades import get_factor_report_card
        result = await asyncio.to_thread(get_factor_report_card, ticker)
        if result is None:
            raise HTTPException(status_code=404, detail=f"No grades available for {ticker}")
        cache_set(cache_key, result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("factor grades failed for %s: %s", ticker, e)
        raise HTTPException(status_code=500, detail=str(e))
