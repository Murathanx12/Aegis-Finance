# Aegis Finance — R&D Cycle 55

You OWN this codebase. This is your sandbox. Improve the engine.

## Methodology — follow this workflow (it produces the best results)

### Phase 1: AUDIT (15 min)
Read service files thoroughly. Look for:
- Bugs (wrong calculations, off-by-one, type errors, logic flaws)
- Stale code (unused variables, dead branches)
- Missing edge case handling
- Inconsistencies between config values and actual usage
- Performance bottlenecks (redundant computations, missing caching)

### Phase 2: RESEARCH (5 min)
Search the web for state-of-the-art approaches relevant to what you found.
Look at OpenBB, Riskfolio-Lib, skfolio, QuantLib, recent papers.
`pip install` any useful packages you find.

### Phase 3: FIX (10 min)
Fix every bug you found in Phase 1. Each fix should be surgical — don't
refactor surrounding code unless the bug requires it.

### Phase 4: BUILD (10 min)
Add ONE substantial new feature or improvement. Pick from the priority list
below, or from what your audit/research revealed. Quality over quantity.

### Phase 5: TEST (5 min)
- Write tests for your bug fixes (regression tests)
- Write tests for your new feature
- Run ONLY the affected test files: `python -m pytest backend/tests/test_<service>.py -v --tb=short`
- Run 3 core smoke tests: `python -m pytest backend/tests/test_monte_carlo.py backend/tests/test_signal_engine.py backend/tests/test_crash_calibration.py -v --tb=short`

## Your powers — use them

- Modify ANY file: backend/, frontend/, engine/, AND lab/
- Install packages: `pip install X`, `npm install X`
- Web search for state-of-the-art approaches and libraries
- Access APIs: yfinance, FRED, Finnhub, GDELT, SEC EDGAR, any public finance API
- Download reference implementations for study

## Priority areas (don't repeat what past cycles did)

### Already built and integrated (v9) — now improve quality
- Signal engine now includes: economic surprise + momentum breadth signals (v9.1)
- Stock analysis now shows: insider signal, liquidity score, momentum rank (v9.1)
- Portfolio engine now uses denoised covariance (RMT) by default (v9.1)
- Frontend API client has 20+ new endpoint functions (v9.1)

### Still needs deeper integration
- Copula tail dependence: integrate copula VaR into portfolio analysis response
- Liquidity risk: add liquidity-adjusted position sizing in portfolio optimizer
- Insider trading: integrate as additional stock signal factor (additive weight)
- Google Trends: integrate fear/greed into macro risk dashboard endpoint
- Factor model (FF6): show factor exposures on stock analysis page
- Attribution: wire into portfolio analyze endpoint (auto-compute vs SPY)

### Quantitative (highest remaining impact)
- Conformal prediction intervals for crash probabilities
- Regime-switching GARCH or MSVAR (statsmodels.tsa.regime_switching)
- Volatility surface interpolation for options intelligence
- Augmented Black-Litterman with entropy pooling (riskfolio has augmented_black_litterman)
- Walk-forward signal optimization (temporal parameter tuning)
- Factor-tilted portfolio construction (overweight quality/value factors)
- Turnover-constrained optimization (max rebalancing cost)
- Cross-sectional momentum → signal engine integration
- Economic surprise → signal engine integration
- Multi-period optimization (dynamic programming approach)

### Data & integration
- SEC EDGAR quarterly financials pipeline improvements (edgartools)
- VIX term structure → regime detection integration
- Short interest data aggregation (Finnhub short interest endpoint)
- Alpha Vantage integration for technical indicators (free tier)
- Congressional trading data (Capitol Trades / Quiver Quant)
- BLS employment data integration (payrolls, claims detail)
- Treasury auction data (bid-to-cover ratios, indirect bidding)
- Sector rotation signals (relative strength + breadth + RSI)

### Frontend / UX (high user impact)
- Liquidity risk display on stock pages
- Copula tail dependence heatmap
- Portfolio optimizer comparison table (Bloomberg PORT style)
- Factor decomposition visualization (bar chart + style box)
- Insider trading timeline display
- Stress test scenario comparison waterfall chart
- Economic surprise dashboard
- Momentum heatmap (sector × stock grid)
- Covariance diagnostics display (eigenvalue spectrum)
- Export functionality (CSV/PDF reports)
- Mobile responsive improvements

### Reliability & performance
- Options calibrator edge cases (no options data, illiquid chains)
- Screener performance with expanded 80+ ticker universe
- Cache warming strategy for new v9 endpoints
- Rate limiting for external API calls
- Parallel data fetching for liquidity/copula analysis
- Error recovery in portfolio optimizer (fallback to simpler method)

### Competitive gaps to close (vs OpenBB, Koyfin, TradingView)
- Alerts/notifications system (threshold-based email or webhook)
- Custom watchlist management (frontend)
- Chart pattern recognition (TA library is installed: `import ta`)
- Multi-asset coverage (ETFs, crypto, commodities via yfinance)
- Backtesting portfolio optimizer decisions (did CVaR outperform?)

## Current engine state

### api_health
```json
{
  "monte_carlo": {
    "status": "ok"
  },
  "stock_analyzer": {
    "status": "ok"
  },
  "sector_analyzer": {
    "status": "ok"
  },
  "portfolio_engine": {
    "status": "ok"
  },
  "crash_model": {
    "status": "ok"
  },
  "signal_engine": {
    "status": "ok"
  },
  "regime_detector": {
    "status": "ok"
  },
  "risk_scorer": {
    "status": "ok"
  },
  "shap_explainer": {
    "status": "ok"
  },
  "news_intelligence": {
    "status": "ok"
  },
  "sentiment_analyzer": {
    "status": "ok"
  },
  "data_quality": {
    "status": "ok"
  },
  "net_liquidity": {
    "status": "ok"
  },
  "return_model": {
    "status": "ok"
  },
  "external_validator": {
    "status": "ok"
  },
  "regime_validator": {
    "status": "ok"
  },
  "drift_detector": {
    "status": "ok"
  },
  "llm_analyzer": {
    "status": "ok"
  },
  "savings_calculator": {
    "status": "ok"
  },
  "factor_model": {
    "status": "ok"
  },
  "stress_testing": {
    "status": "ok"
  },
  "cross_sectional_momentum": {
    "status": "ok"
  },
  "economic_surprise": {
    "status": "ok"
  },
  "liquidity_risk": {
    "status": "ok"
  },
  "copula_tail": {
    "status": "ok"
  },
  "covariance": {
    "status": "ok"
  },
  "portfolio_optimizer": {
    "status": "ok"
  },
  "insider_trading": {
    "status": "ok"
  },
  "trends_sentiment": {
    "status": "ok"
  },
  "survival_model": {
    "status": "ok"
  },
  "anomaly_detector": {
    "status": "ok"
  },
  "crash_timeline": {
    "status": "ok"
  },
  "attribution": {
    "status": "ok"
  }
}
```

### code_metrics
```json
{
  "test_count": {
    "files": 49,
    "functions": 1205
  },
  "code_smells": [],
  "n_smells": 0
}
```

### copula_snapshot
```json
{
  "AAPL_MSFT": {
    "best_copula": "student_t",
    "tail_lower": 0.0751,
    "pearson": 0.4209
  },
  "SPY_GLD": {
    "best_copula": "student_t",
    "tail_lower": 0.1475,
    "pearson": 0.1236
  }
}
```

### drift_check
```json
{
  "drift_detected": true,
  "n_features_checked": 158,
  "n_drifted": 142,
  "drift_pct": 89.9,
  "severity": "critical",
  "reference_window": 504,
  "inference_window": 252,
  "drifted_features": [
    "mom_1m",
    "mom_6m",
    "mom_12m",
    "dist_52w_high",
    "dist_52w_low",
    "drawdown_from_peak",
    "vol_1m",
    "vol_3m",
    "vol_6m",
    "vol_12m"
  ],
  "recent_stability": "unstable",
  "scale_used": "long",
  "multi_scale": {
    "long": {
      "severity": "critical",
      "effective_severity": "critical",
      "drift_pct": 89.9,
      "n_drifted": 142,
      "n_features_checked": 158,
      "reference_window": 504,
      "inference_window": 252
    },
    "medium": {
      "severity": "critical",
      "effective_severity": "critical",
      "drift_pct": 95.0,
      "n_drifted": 151,
      "n_features_checked": 159,
      "reference_window": 252,
      "inference_window": 126
    },
    "short": {
      "severity": "critical",
      "effective_severity": "critical",
      "drift_pct": 98.6,
      "n_drifted": 145,
      "n_features_checked": 147,
      "reference_window": 126,
      "inference_window": 63
    }
  }
}
```

### economic_surprise
```json
{
  "composite_score": -0.08,
  "signal": "neutral",
  "trend": "deteriorating",
  "indicators_tracked": 6,
  "positive_surprises": 3,
  "negative_surprises": 2,
  "breadth": 0.5,
  "indicators": [
    {
      "series_id": "NFCI",
      "name": "Chicago Fed NFCI",
      "latest_value": -0.43,
      "trend_value": -0.51,
      "surprise_pct": -15.68,
      "surprise_normalized": -1.0,
      "weight": 1.3,
      "weighted_surprise": -1.3,
      "surprise_trend": -13.01
    },
    {
      "series_id": "BAMLH0A0HYM2",
      "name": "High Yield Spread",
      "latest_value": 2.95,
      "trend_value": 3.12,
      "surprise_pct": 5.6,
      "surprise_normalized": 0.56,
      "weight": 1.2,
      "weighted_surprise": 0.672,
      "surprise_trend": 5.67
    },
    {
      "series_id": "CPIAUCSL",
      "name": "Consumer Price Index",
      "latest_value": 330.29,
      "trend_value": 323.77,
      "surprise_pct": -2.02,
      "surprise_normalized": -0.202,
      "weight": 0.8,
      "weighted_surprise": -0.161,
      "surprise_trend": -1.55
    },
    {
      "series_id": "UMCSENT",
      "name": "Consumer Sentiment",
      "latest_value": 56.6,
      "trend_value": 55.75,
      "surprise_pct": 1.52,
      "surprise_normalized": 0.152,
      "weight": 1.0,
      "weighted_surprise": 0.152,
      "surprise_trend": -5.7
    },
    {
      "series_id": "INDPRO",
      "name": "Industrial Production",
      "latest_value": 102.55,
      "trend_value": 101.55,
      "surprise_pct": 0.98,
      "surprise_normalized": 0.098,
      "weight": 1.2,
      "weighted_surprise": 0.118,
      "surprise_trend": 0.54
    },
    {
      "series_id": "UNRATE",
      "name": "Unemployment Rate",
      "latest_value": 4.3,
      "trend_value": 4.3,
      "surprise_pct": -0.0,
      "surprise_normalized": -0.0,
      "weight": 1.0,
      "weighted_surprise": -0.0,
      "surprise_trend": -2.96
    }
  ]
}
```

### factor_model
```json
{
  "AAPL": {
    "r_squared": 0.4883,
    "alpha_annual": 0.0391,
    "market_beta": 1.2802,
    "style": {
      "market": "aggressive",
      "size": "neutral",
      "value": "blend",
      "profitability": "quality",
      "investment": "neutral"
    }
  },
  "JPM": {
    "r_squared": 0.5931,
    "alpha_annual": 0.0059,
    "market_beta": 1.1553,
    "style": {
      "market": "neutral",
      "size": "large-cap tilt",
      "value": "value",
      "profitability": "speculative",
      "investment": "aggressive"
    }
  },
  "XOM": {
    "r_squared": 0.2402,
    "alpha_annual": 0.0843,
    "market_beta": 0.6224,
    "style": {
      "market": "defensive",
      "size": "neutral",
      "value": "value",
      "profitability": "quality",
      "investment": "conservative"
    }
  }
}
```

### liquidity_snapshot
```json
{
  "AAPL": {
    "score": 76.0,
    "tier": "liquid",
    "amihud": 0.0,
    "avg_dv_mm": 10146.6
  },
  "NVDA": {
    "score": 100.0,
    "tier": "highly_liquid",
    "amihud": 0.0,
    "avg_dv_mm": 29550.4
  },
  "COIN": {
    "score": 100.0,
    "tier": "highly_liquid",
    "amihud": 0.0,
    "avg_dv_mm": 1973.6
  }
}
```

### market_snapshot
```json
{
  "sp500": {
    "symbol": "^GSPC",
    "price": 6961.46,
    "change_1d_pct": 1.092
  },
  "nasdaq": {
    "symbol": "^IXIC",
    "price": 23605.75,
    "change_1d_pct": 1.82
  },
  "dow": {
    "symbol": "^DJI",
    "price": 48532.64,
    "change_1d_pct": 0.652
  },
  "vix": {
    "symbol": "^VIX",
    "price": 18.36,
    "change_1d_pct": -3.975
  },
  "treasury_10y": {
    "symbol": "^TNX",
    "price": 4.26,
    "change_1d_pct": -0.954
  },
  "gold": {
    "symbol": "GC=F",
    "price": 4865.6,
    "change_1d_pct": 2.598
  },
  "oil": {
    "symbol": "CL=F",
    "price": 91.69,
    "change_1d_pct": -7.459
  },
  "usd_index": {
    "symbol": "DX-Y.NYB",
    "price": 98.11,
    "change_1d_pct": -0.263
  }
}
```

### options_intelligence
```json
{
  "vix_term_structure": {
    "values": {
      "VIX": 18.350000381469727,
      "VIX3M": 20.829999923706055,
      "VIX9D": 16.940000534057617
    },
    "vix_vix3m_ratio": 0.881,
    "contango": true,
    "backwardation": false,
    "structure": "normal_contango",
    "signal": "neutral",
    "interpretation": "Normal term structure: VIX (18.4) < VIX3M (20.8)",
    "vix_level": "normal",
    "vix9d_vix_ratio": 0.923
  },
  "options_SPY": {
    "iv_skew": 1.302,
    "put_call_ratio": 1.144,
    "iv_rank": 0.0,
    "signal_score": 0.0,
    "signal_sentiment": "neutral"
  },
  "options_AAPL": {
    "iv_skew": 1.549,
    "put_call_ratio": 0.414,
    "iv_rank": 52.4,
    "signal_score": -0.35,
    "signal_sentiment": "bearish"
  }
}
```

### portfolio_test
```json
{
  "build_conservative": {
    "success": true,
    "keys": [
      "risk_tolerance",
      "time_horizon",
      "investment_amount",
      "description",
      "method",
      "holdings",
      "goal"
    ]
  },
  "build_moderate": {
    "success": true,
    "keys": [
      "risk_tolerance",
      "time_horizon",
      "investment_amount",
      "description",
      "method",
      "holdings",
      "goal"
    ]
  },
  "build_aggressive": {
    "success": true,
    "keys": [
      "risk_tolerance",
      "time_horizon",
      "investment_amount",
      "description",
      "method",
      "holdings",
      "goal"
    ]
  }
}
```

### regime_risk
```json
{
  "regime": {
    "current": "Bull",
    "type": "tuple(Series, str)"
  },
  "risk_score": {
    "current": 0.874,
    "mean": 0.37,
    "max": 4.0,
    "type": "Series"
  }
}
```

### run_metadata
```json
{
  "cycle": 55,
  "timestamp": "2026-04-15T03:17:44.995667",
  "data_sources": [
    "market_snapshot",
    "stock_analysis",
    "sp500_mc",
    "crash_calibration",
    "signal_quality",
    "regime_risk",
    "sector_analysis",
    "portfolio_test",
    "api_health",
    "validation_metrics",
    "drift_check",
    "options_intelligence",
    "systemic_risk",
    "factor_model",
    "economic_surprise",
    "liquidity_snapshot",
    "copula_snapshot",
    "code_metrics"
  ],
  "errors": []
}
```

### sector_analysis
```json
{
  "return_type": "dict",
  "n_sectors": 11,
  "keys": [
    "Technology",
    "Healthcare",
    "Financials",
    "Energy",
    "Consumer Disc.",
    "Consumer Staples",
    "Industrials",
    "Utilities",
    "Real Estate",
    "Materials",
    "Communications"
  ]
}
```

### signal_quality
```json
{
  "market_signal": {
    "action": "Buy",
    "confidence": 20,
    "color": "green",
    "composite_score": 0.204,
    "reasons": [
      "Crash model drift (critical) \u2014 ML signal weight reduced to 20%",
      "Low crash risk (3% 3M)",
      "Bullish market regime"
    ],
    "components": {
      "crash_prob": 0.015,
      "regime": 0.7,
      "valuation": 0.1,
      "momentum": 0.234,
      "mean_reversion": 0.0,
      "external": 0.4,
      "macro_risk": -0.082,
      "drawdown": 0.2,
      "systemic_risk": -0.3
    },
    "drift_severity": "critical",
    "drift_crash_weight_mult": 0.2,
    "regime_weight_profile": "Bull"
  },
  "stock_signals": {
    "NVDA": {
      "action": "Strong Buy",
      "composite_score": 0.591,
      "confidence": 59
    },
    "TSLA": {
      "action": "Hold",
      "composite_score": -0.003,
      "confidence": 0
    },
    "AMZN": {
      "action": "Strong Buy",
      "composite_score": 0.461,
      "confidence": 46
    },
    "JNJ": {
      "action": "Buy",
      "composite_score": 0.29,
      "confidence": 29
    },
    "HD": {
      "action": "Hold",
      "composite_score": 0.082,
      "confidence": 8
    },
    "MSFT": {
      "action": "Hold",
      "composite_score": -0.024,
      "confidence": 2
    },
    "CCL": {
      "action": "Buy",
      "composite_score": 0.272,
      "confidence": 27
    },
    "HOOD": {
      "action": "Hold",
      "composite_score": 0.1,
      "confidence": 10
    },
    "RUN": {
      "action": "Hold",
      "composite_score": -0.049,
      "confidence": 4
    },
    "ABNB": {
      "action": "Buy",
      "composite_score": 0.36,
      "confidence": 36
    },
    "MGM": {
      "action": "Buy",
      "composite_score": 0.38,
      "confidence": 37
    },
    "LUV": {
      "action": "Hold",
      "composite_score": 0.108,
      "confidence": 10
    }
  },
  "diversity": {
    "action_distribution": {
      "Strong Buy": 2,
      "Hold": 6,
      "Buy": 4
    },
    "n_unique_actions": 3,
    "score_spread": 0.64,
    "score_std": 0.199,
    "all_same_action": false
  },
  "n_tickers_with_signal": 12,
  "n_tickers_failed": 0
}
```

### sp500_monte_carlo
```json
{
  "status": "ok",
  "result_keys": [
    "all_paths",
    "paths",
    "mean_path",
    "median_path",
    "p05",
    "p25",
    "p75",
    "p95",
    "final_mean",
    "final_median",
    "final_p05",
    "final_p10",
    "final_p25",
    "final_p75",
    "final_p90",
    "final_p95",
    "total_return_pct",
    "annual_return_pct",
    "crash_prob_1y",
    "crash_prob_5y",
    "crash_probs",
    "cvar_95_pct",
    "max_dd_pct",
    "max_drawdown_pct",
    "scenarios",
    "ml_crash_prob",
    "ml_predicted_return",
    "garch_vol",
    "realism_check"
  ],
  "current_price": 6960.27001953125,
  "final_mean": 9802.148665572124,
  "final_median": 8899.657504106113,
  "final_p05": 3878.7368699601234,
  "final_p10": 4681.2598956288375,
  "final_p25": 6450.262774363785,
  "final_p75": 12231.768358628548,
  "final_p90": 16051.01241755047,
  "final_p95": 18879.73392471461,
  "total_return_pct": 40.830005704753745,
  "annual_return_pct": 7.087563978794842,
  "crash_prob_1y": 25.09,
  "crash_prob_5y": 81.67,
  "cvar_95_pct": -53.98065439339431,
  "max_dd_pct": -30.694105799958304,
  "max_drawdown_pct": 30.694105799958304
}
```

### stock_analysis
```json
{
  "NVDA": {
    "ticker": "NVDA",
    "current_price": 196.1750030517578,
    "mc_median_5y": 101.64962178321363,
    "mc_p10_5y": -46.72898020494647,
    "mc_p90_5y": 300.0,
    "garch_vol": 38.430182711638054,
    "garch_nu": 8.0,
    "crash_prob_3m": 7.99,
    "signal_action": "Strong Buy",
    "signal_score": 0.546,
    "beta": 2.335,
    "sector": "Technology",
    "all_keys": [
      "ticker",
      "name",
      "sector",
      "current_price",
      "market_cap",
      "cap_tier",
      "beta",
      "pe_ratio",
      "analyst_target",
      "hist_drift",
      "capped_drift",
      "volatility",
      "expected_return",
      "median_return",
      "p05_price",
      "p95_price",
      "prob_loss_5y",
      "avg_max_drawdown",
      "sharpe",
      "mc_median_5y_return",
      "mc_p10_5y_return",
      "mc_p90_5y_return",
      "garch_annual_vol",
      "garch_nu",
      "garch_persistence",
      "ml_crash_prob",
      "tail_risk",
      "prediction_confidence",
      "analyst_targets",
      "recommendations",
      "holders",
      "news",
      "earnings",
      "price_history",
      "momentum_1m",
      "momentum_3m",
      "key_stats",
      "peers",
      "options_calibration",
      "factor_exposure"
    ]
  },
  "TSLA": {
    "ticker": "TSLA",
    "current_price": 365.2200012207031,
    "mc_median_5y": 14.486134846706044,
    "mc_p10_5y": -77.99582160805481,
    "mc_p90_5y": 300.0,
    "garch_vol": 44.86684925960848,
    "garch_nu": 8.0,
    "crash_prob_3m": 7.99,
    "signal_action": "Hold",
    "signal_score": -0.032,
    "beta": 1.915,
    "sector": "Consumer Cyclical",
    "all_keys": [
      "ticker",
      "name",
      "sector",
      "current_price",
      "market_cap",
      "cap_tier",
      "beta",
      "pe_ratio",
      "analyst_target",
      "hist_drift",
      "capped_drift",
      "volatility",
      "expected_return",
      "median_return",
      "p05_price",
      "p95_price",
      "prob_loss_5y",
      "avg_max_drawdown",
      "sharpe",
      "mc_median_5y_return",
      "mc_p10_5y_return",
      "mc_p90_5y_return",
      "garch_annual_vol",
      "garch_nu",
      "garch_persistence",
      "ml_crash_prob",
      "tail_risk",
      "prediction_confidence",
      "analyst_targets",
      "recommendations",
      "holders",
      "news",
      "earnings",
      "price_history",
      "momentum_1m",
      "momentum_3m",
      "key_stats",
      "peers",
      "options_calibration",
      "factor_exposure"
    ]
  },
  "AMZN": {
    "ticker": "AMZN",
    "current_price": 248.82009887695312,
    "mc_median_5y": 38.17569279487203,
    "mc_p10_5y": -41.43148962040102,
    "mc_p90_5y": 208.56264297901217,
    "garch_vol": 31.60632825374608,
    "garch_nu": 8.0,
    "crash_prob_3m": 5.18,
    "signal_action": "Buy",
    "signal_score": 0.424,
    "beta": 1.383,
    "sector": "Consumer Cyclical",
    "all_keys": [
      "ticker",
      "name",
      "sector",
      "current_price",
      "market_cap",
      "cap_tier",
      "beta",
      "pe_ratio",
      "analyst_target",
      "hist_drift",
      "capped_drift",
      "volatility",
      "expected_return",
      "median_return",
      "p05_price",
      "p95_price",
      "prob_loss_5y",
      "avg_max_drawdown",
      "sharpe",
      "mc_median_5y_return",
      "mc_p10_5y_return",
      "mc_p90_5y_return",
      "garch_annual_vol",
      "garch_nu",
      "garch_persistence",
      "ml_crash_prob",
      "tail_risk",
      "prediction_confidence",
      "analyst_targets",
      "recommendations",
      "holders",
      "news",
      "earnings",
      "price_history",
      "momentum_1m",
      "momentum_3m",
      "key_stats",
      "peers",
      "options_calibration",
      "factor_exposure"
    ]
  },
  "JNJ": {
    "ticker": "JNJ",
    "current_price": 240.30999755859375,
    "mc_median_5y": 37.400352508880076,
    "mc_p10_5y": -14.201957577068946,
    "mc_p90_5y": 119.55666374335672,
    "garch_vol": 15.838612435219481,
    "garch_nu
... [truncated]
```

### systemic_risk
```json
{
  "turbulence_current": 6.1989,
  "turbulence_percentile": 72.9,
  "turbulence_threshold_pctl": 90,
  "absorption_ratio_current": 0.9252,
  "absorption_ratio_change_1m": -0.0067,
  "systemic_stress": true,
  "n_assets_used": 6,
  "assets_used": [
    "SP500",
    "NASDAQ",
    "Russell",
    "Gold",
    "HYG",
    "LQD"
  ]
}
```

## Recent cycles (don't repeat these)

Cycle 50: Multi-scale drift detection — reduce false-critical severity from regime changes (neutral)
Cycle 51: Bug fixes (3) + systemic risk signal engine integration (improved)
Cycle 52: Bug fixes (3) + factor exposure integration into stock analysis (improved)
Cycle 53: Copula tail fixes (Student-t AIC, marginal interpolation) + copula VaR portfolio integration (improved)
Cycle 54: Bug fixes (4) + insider trading signal engine integration (improved)

## Unexplored areas

- backend/services/shap_explainer.py
- backend/services/return_model.py
- backend/services/tail_dependence.py
- backend/services/bubble_detector.py
- backend/services/fundamentals.py
- backend/services/options_calibrator.py
- backend/services/economic_surprise.py
- backend/services/survival_model.py
- backend/services/liquidity_risk.py
- backend/services/covariance.py
- backend/services/insider_trading.py
- backend/services/trends_sentiment.py
- backend/services/attribution.py
- backend/routers/portfolio.py
- backend/routers/analytics.py
- engine/training/train_crash_model.py
- engine/validation/walk_forward.py
- engine/validation/metrics.py
- frontend/src/app/
- frontend/src/components/

## When done

1. Experiment report: lab/experiments/cycle_055/experiment_report.json
   {
     "cycle": 55,
     "timestamp": "<ISO timestamp>",
     "title": "<one-line summary>",
     "category": "<quantitative|data|frontend|reliability>",
     "observation": {
       "bugs_found": ["<list of bugs found in audit>"],
       "gap_identified": "<the gap you're fixing>"
     },
     "implementation": {
       "bugs_fixed": ["<list of bug descriptions>"],
       "feature_built": "<what you added>",
       "files_changed": ["<list>"],
       "files_created": ["<list>"],
       "packages_installed": ["<list>"]
     },
     "validation": {
       "tests_written": 0,
       "tests_passing": 0,
       "regressions": 0
     },
     "assessment": {
       "verdict": "improved|neutral|regressed",
       "confidence": "low|medium|high",
       "depth": 1-5,
       "limitations": ["<honest list>"],
       "self_critique": "<what you'd do differently>"
     },
     "next_steps": ["<actionable items for next cycle>"]
   }

2. Commit: `git add -A && git commit -m "Lab cycle_055: <summary>"`

Think like a quant researcher who reads code carefully before writing it.
Audit first, then fix, then build. Quality over quantity.
