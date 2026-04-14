# Aegis Finance — R&D Cycle 57

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
    "files": 50,
    "functions": 1232
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
    "tail_lower": 0.075,
    "pearson": 0.4206
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
  "composite_score": 0.027,
  "signal": "neutral",
  "trend": "stable",
  "indicators_tracked": 7,
  "positive_surprises": 3,
  "negative_surprises": 2,
  "breadth": 0.43,
  "indicators": [
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
      "series_id": "ICSA",
      "name": "Initial Jobless Claims",
      "latest_value": 219000.0,
      "trend_value": 211000.0,
      "surprise_pct": -3.79,
      "surprise_normalized": -0.379,
      "weight": 1.5,
      "weighted_surprise": -0.569,
      "surprise_trend": 0.04
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
      "series_id": "MANEMP",
      "name": "Manufacturing Employment",
      "latest_value": 12591.0,
      "trend_value": 12607.5,
      "surprise_pct": -0.13,
      "surprise_normalized": -0.013,
      "weight": 0.8,
      "weighted_surprise": -0.01,
      "surprise_trend": -0.33
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
    "avg_dv_mm": 10197.2
  },
  "NVDA": {
    "score": 100.0,
    "tier": "highly_liquid",
    "amihud": 0.0,
    "avg_dv_mm": 29636.3
  },
  "COIN": {
    "score": 100.0,
    "tier": "highly_liquid",
    "amihud": 0.0,
    "avg_dv_mm": 1978.2
  }
}
```

### market_snapshot
```json
{
  "sp500": {
    "symbol": "^GSPC",
    "price": 6965.26,
    "change_1d_pct": 1.147
  },
  "nasdaq": {
    "symbol": "^IXIC",
    "price": 23613.17,
    "change_1d_pct": 1.852
  },
  "dow": {
    "symbol": "^DJI",
    "price": 48574.41,
    "change_1d_pct": 0.739
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
    "price": 4863.7,
    "change_1d_pct": 2.558
  },
  "oil": {
    "symbol": "CL=F",
    "price": 91.86,
    "change_1d_pct": -7.287
  },
  "usd_index": {
    "symbol": "DX-Y.NYB",
    "price": 98.14,
    "change_1d_pct": -0.237
  }
}
```

### options_intelligence
```json
{
  "vix_term_structure": {
    "values": {
      "VIX": 18.3799991607666,
      "VIX3M": 20.670000076293945,
      "VIX9D": 16.989999771118164
    },
    "vix_vix3m_ratio": 0.889,
    "contango": true,
    "backwardation": false,
    "structure": "normal_contango",
    "signal": "neutral",
    "interpretation": "Normal term structure: VIX (18.4) < VIX3M (20.7)",
    "vix_level": "normal",
    "vix9d_vix_ratio": 0.924
  },
  "options_SPY": {
    "iv_skew": 1.313,
    "put_call_ratio": 1.116,
    "iv_rank": 53.6,
    "signal_score": -0.25,
    "signal_sentiment": "bearish"
  },
  "options_AAPL": {
    "iv_skew": 1.557,
    "put_call_ratio": 0.415,
    "iv_rank": 61.1,
    "signal_score": -0.45,
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
    "current": 0.876,
    "mean": 0.37,
    "max": 4.0,
    "type": "Series"
  }
}
```

### run_metadata
```json
{
  "cycle": 57,
  "timestamp": "2026-04-15T03:45:14.236942",
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
  "errors": [
    "SQ: returned None"
  ]
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
    "composite_score": 0.201,
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
    "MSFT": {
      "action": "Hold",
      "composite_score": -0.024,
      "confidence": 2
    },
    "JNJ": {
      "action": "Buy",
      "composite_score": 0.288,
      "confidence": 28
    },
    "AAPL": {
      "action": "Buy",
      "composite_score": 0.233,
      "confidence": 23
    },
    "GOOGL": {
      "action": "Buy",
      "composite_score": 0.388,
      "confidence": 38
    },
    "JPM": {
      "action": "Buy",
      "composite_score": 0.326,
      "confidence": 32
    },
    "META": {
      "action": "Buy",
      "composite_score": 0.292,
      "confidence": 29
    },
    "MRVL": {
      "action": "Strong Buy",
      "composite_score": 0.573,
      "confidence": 57
    },
    "FSLR": {
      "action": "Hold",
      "composite_score": 0.089,
      "confidence": 8
    },
    "OKTA": {
      "action": "Hold",
      "composite_score": -0.053,
      "confidence": 5
    },
    "HIMS": {
      "action": "Hold",
      "composite_score": 0.028,
      "confidence": 2
    },
    "ROKU": {
      "action": "Buy",
      "composite_score": 0.432,
      "confidence": 43
    },
    "DDOG": {
      "action": "Hold",
      "composite_score": -0.076,
      "confidence": 7
    }
  },
  "diversity": {
    "action_distribution": {
      "Hold": 5,
      "Buy": 6,
      "Strong Buy": 1
    },
    "n_unique_actions": 3,
    "score_spread": 0.649,
    "score_std": 0.203,
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
  "current_price": 6963.72998046875,
  "final_mean": 9792.34052235064,
  "final_median": 8843.025091570462,
  "final_p05": 3935.8749033021004,
  "final_p10": 4749.7949723676675,
  "final_p25": 6464.325057667711,
  "final_p75": 12132.505592512458,
  "final_p90": 15924.636514421143,
  "final_p95": 18955.258613329814,
  "total_return_pct": 40.61918755918632,
  "annual_return_pct": 7.055483411983476,
  "crash_prob_1y": 25.119999999999997,
  "crash_prob_5y": 82.34,
  "cvar_95_pct": -53.561537186942765,
  "max_dd_pct": -30.76977445647727,
  "max_drawdown_pct": 30.76977445647727
}
```

### stock_analysis
```json
{
  "MSFT": {
    "ticker": "MSFT",
    "current_price": 392.68499755859375,
    "mc_median_5y": 91.70007860400386,
    "mc_p10_5y": -3.831862011049536,
    "mc_p90_5y": 271.6115430483278,
    "garch_vol": 29.86813161908798,
    "garch_nu": 8.0,
    "crash_prob_3m": 4.12,
    "signal_action": "Hold",
    "signal_score": -0.033,
    "beta": 1.107,
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
  "JNJ": {
    "ticker": "JNJ",
    "current_price": 240.30499267578125,
    "mc_median_5y": 37.457016541278,
    "mc_p10_5y": -13.62591455875799,
    "mc_p90_5y": 119.02065018822677,
    "garch_vol": 15.838574813180525,
    "garch_nu": 8.0,
    "crash_prob_3m": 1.93,
    "signal_action": "Buy",
    "signal_score": 0.416,
    "beta": 0.329,
    "sector": "Healthcare",
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
  "AAPL": {
    "ticker": "AAPL",
    "current_price": 258.43499755859375,
    "mc_median_5y": 71.65546983364163,
    "mc_p10_5y": -16.01762856005282,
    "mc_p90_5y": 236.41286458289989,
    "garch_vol": 22.9011052627525,
    "garch_nu": 8.0,
    "crash_prob_3m": 4.02,
    "signal_action": "Buy",
    "signal_score": 0.221,
    "beta": 1.109,
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
  "GOOGL": {
    "ticker": "GOOGL",
    "current_price": 332.5400085449219,
    "mc_median_5y": 90.4729976952962,
    "mc_p10_5y": -9.165473189919982,
    "mc_p90_5y": 286.7664708809245,
    "garch_vol": 29.29830197246885,
    "garch_nu": 
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

Cycle 52: Bug fixes (3) + factor exposure integration into stock analysis (improved)
Cycle 53: Copula tail fixes (Student-t AIC, marginal interpolation) + copula VaR portfolio integration (improved)
Cycle 54: Bug fixes (4) + insider trading signal engine integration (improved)
Cycle 55: Bug fixes (3) + portfolio attribution auto-integration (improved)
Cycle 56: Bug fixes (3) + Google Trends fear/greed sentiment integration (improved)

## Unexplored areas

- backend/services/shap_explainer.py
- backend/services/return_model.py
- backend/services/tail_dependence.py
- backend/services/options_calibrator.py
- backend/services/economic_surprise.py
- backend/services/covariance.py
- backend/services/insider_trading.py
- backend/services/trends_sentiment.py
- backend/services/attribution.py
- backend/routers/portfolio.py
- engine/training/train_crash_model.py
- engine/validation/walk_forward.py
- engine/validation/metrics.py
- frontend/src/app/
- frontend/src/components/
- frontend/src/lib/

## When done

1. Experiment report: lab/experiments/cycle_057/experiment_report.json
   {
     "cycle": 57,
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

2. Commit: `git add -A && git commit -m "Lab cycle_057: <summary>"`

Think like a quant researcher who reads code carefully before writing it.
Audit first, then fix, then build. Quality over quantity.
