# Aegis Finance — R&D Cycle 51

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
    "files": 47,
    "functions": 1158
  },
  "code_smells": [
    "anomaly_detector.py: 1 fillna(0) (banned)"
  ],
  "n_smells": 1
}
```

### copula_snapshot
```json
{
  "AAPL_MSFT": {
    "best_copula": "clayton",
    "tail_lower": 0.2694,
    "pearson": 0.4213
  },
  "SPY_GLD": {
    "best_copula": "gumbel",
    "tail_lower": 0.0,
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
  "composite_score": -0.125,
  "signal": "neutral",
  "trend": "deteriorating",
  "indicators_tracked": 8,
  "positive_surprises": 3,
  "negative_surprises": 3,
  "breadth": 0.38,
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
    "score": 75.0,
    "tier": "liquid",
    "amihud": 0.0,
    "avg_dv_mm": 10106.0
  },
  "NVDA": {
    "score": 100.0,
    "tier": "highly_liquid",
    "amihud": 0.0,
    "avg_dv_mm": 29355.6
  },
  "COIN": {
    "score": 100.0,
    "tier": "highly_liquid",
    "amihud": 0.0,
    "avg_dv_mm": 1962.8
  }
}
```

### market_snapshot
```json
{
  "sp500": {
    "symbol": "^GSPC",
    "price": 6962.08,
    "change_1d_pct": 1.101
  },
  "nasdaq": {
    "symbol": "^IXIC",
    "price": 23604.18,
    "change_1d_pct": 1.814
  },
  "dow": {
    "symbol": "^DJI",
    "price": 48525.84,
    "change_1d_pct": 0.638
  },
  "vix": {
    "symbol": "^VIX",
    "price": 18.41,
    "change_1d_pct": -3.713
  },
  "treasury_10y": {
    "symbol": "^TNX",
    "price": 4.26,
    "change_1d_pct": -0.908
  },
  "gold": {
    "symbol": "GC=F",
    "price": 4859.1,
    "change_1d_pct": 2.461
  },
  "oil": {
    "symbol": "CL=F",
    "price": 92.12,
    "change_1d_pct": -7.025
  },
  "usd_index": {
    "symbol": "DX-Y.NYB",
    "price": 98.09,
    "change_1d_pct": -0.289
  }
}
```

### options_intelligence
```json
{
  "vix_term_structure": {
    "values": {
      "VIX": 18.450000762939453,
      "VIX3M": 20.850000381469727,
      "VIX9D": 17.1200008392334
    },
    "vix_vix3m_ratio": 0.885,
    "contango": true,
    "backwardation": false,
    "structure": "normal_contango",
    "signal": "neutral",
    "interpretation": "Normal term structure: VIX (18.5) < VIX3M (20.9)",
    "vix_level": "normal",
    "vix9d_vix_ratio": 0.928
  },
  "options_SPY": {
    "iv_skew": 1.302,
    "put_call_ratio": 1.13,
    "iv_rank": 64.5,
    "signal_score": -0.35,
    "signal_sentiment": "bearish"
  },
  "options_AAPL": {
    "iv_skew": 1.576,
    "put_call_ratio": 0.458,
    "iv_rank": 44.2,
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
    "current": 0.875,
    "mean": 0.37,
    "max": 4.0,
    "type": "Series"
  }
}
```

### run_metadata
```json
{
  "cycle": 51,
  "timestamp": "2026-04-15T02:06:51.812361",
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
    "confidence": 26,
    "color": "green",
    "composite_score": 0.261,
    "reasons": [
      "Crash model drift (critical) \u2014 ML signal weight reduced to 20%",
      "Low crash risk (3% 3M)",
      "Bullish market regime"
    ],
    "components": {
      "crash_prob": 0.015,
      "regime": 0.7,
      "valuation": 0.1,
      "momentum": 0.236,
      "mean_reversion": 0.0,
      "external": 0.4,
      "macro_risk": -0.082,
      "drawdown": 0.2
    },
    "drift_severity": "critical",
    "drift_crash_weight_mult": 0.2,
    "regime_weight_profile": "Bull"
  },
  "stock_signals": {
    "BRK-B": {
      "action": "Hold",
      "composite_score": -0.011,
      "confidence": 1
    },
    "COST": {
      "action": "Buy",
      "composite_score": 0.239,
      "confidence": 23
    },
    "META": {
      "action": "Buy",
      "composite_score": 0.369,
      "confidence": 36
    },
    "GOOGL": {
      "action": "Strong Buy",
      "composite_score": 0.451,
      "confidence": 45
    },
    "MA": {
      "action": "Buy",
      "composite_score": 0.21,
      "confidence": 20
    },
    "PG": {
      "action": "Hold",
      "composite_score": 0.137,
      "confidence": 13
    },
    "NU": {
      "action": "Buy",
      "composite_score": 0.311,
      "confidence": 31
    },
    "ENPH": {
      "action": "Hold",
      "composite_score": 0.089,
      "confidence": 8
    },
    "TTD": {
      "action": "Hold",
      "composite_score": 0.035,
      "confidence": 3
    },
    "GOLD": {
      "error": "argument of type 'NoneType' is not iterable"
    },
    "ARM": {
      "action": "Strong Buy",
      "composite_score": 0.61,
      "confidence": 61
    },
    "LUV": {
      "action": "Buy",
      "composite_score": 0.171,
      "confidence": 17
    }
  },
  "diversity": {
    "action_distribution": {
      "Hold": 4,
      "Buy": 5,
      "Strong Buy": 2
    },
    "n_unique_actions": 3,
    "score_spread": 0.621,
    "score_std": 0.178,
    "all_same_action": false
  },
  "n_tickers_with_signal": 11,
  "n_tickers_failed": 1
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
  "current_price": 6961.77978515625,
  "final_mean": 9794.669526941701,
  "final_median": 8882.129594200811,
  "final_p05": 3943.449068531788,
  "final_p10": 4797.019014072645,
  "final_p25": 6432.576423869801,
  "final_p75": 12158.853293759796,
  "final_p90": 15954.173932113132,
  "final_p95": 18957.048237294508,
  "total_return_pct": 40.69203320429173,
  "annual_return_pct": 7.066572809419602,
  "crash_prob_1y": 25.490000000000002,
  "crash_prob_5y": 81.58999999999999,
  "cvar_95_pct": -53.752294335624974,
  "max_dd_pct": -30.68184927287937,
  "max_drawdown_pct": 30.68184927287937
}
```

### stock_analysis
```json
{
  "BRK-B": {
    "ticker": "BRK-B",
    "current_price": 477.2300109863281,
    "mc_median_5y": 59.61420882648181,
    "mc_p10_5y": 0.6883458574428625,
    "mc_p90_5y": 155.17606450110213,
    "garch_vol": 15.167220304809737,
    "garch_nu": 8.0,
    "crash_prob_3m": 2.7,
    "signal_action": "Hold",
    "signal_score": 0.054,
    "beta": 0.699,
    "sector": "Financial Services",
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
      "options_calibration"
    ]
  },
  "COST": {
    "ticker": "COST",
    "current_price": 974.47998046875,
    "mc_median_5y": 84.56118106604455,
    "mc_p10_5y": -2.611532753104473,
    "mc_p90_5y": 245.33585282997973,
    "garch_vol": 21.44505390239638,
    "garch_nu": 8.0,
    "crash_prob_3m": 3.4,
    "signal_action": "Buy",
    "signal_score": 0.231,
    "beta": 0.978,
    "sector": "Consumer Defensive",
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
      "options_calibration"
    ]
  },
  "META": {
    "ticker": "META",
    "current_price": 664.4099731445312,
    "mc_median_5y": 83.53347257887687,
    "mc_p10_5y": -38.14892068148911,
    "mc_p90_5y": 300.0,
    "garch_vol": 41.2997850902,
    "garch_nu": 8.0,
    "crash_prob_3m": 5.86,
    "signal_action": "Buy",
    "signal_score": 0.354,
    "beta": 1.309,
    "sector": "Communication Services",
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
      "options_calibration"
    ]
  },
  "GOOGL": {
    "ticker": "GOOGL",
    "current_price": 332.6700134277344,
    "mc_median_5y": 88.84526181307666,
    "mc_p10_5y": -13.590284903299166,
    "mc_p90_5y": 293.0763095209403,
    "garch_vol": 29.300899354647004,
    "garch_nu": 8.0,
    "crash_prob_3m": 4.21,
    "signal_action": "Strong 
... [truncated]
```

### systemic_risk
```json
{
  "turbulence_current": 6.1021,
  "turbulence_percentile": 72.3,
  "turbulence_threshold_pctl": 90,
  "absorption_ratio_current": 0.9981,
  "absorption_ratio_change_1m": -0.0003,
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

Cycle 46: Wire options and earnings intelligence into stock signals (neutral)
Cycle 47: Signal analytics — consensus scoring, conviction decomposition, ranking, risk-reward (neutral)
Cycle 48: Stock signal component decomposition and conviction quality (neutral)
Cycle 49: Bug fixes + opportunity score ranking for stock screener (neutral)
Cycle 50: Multi-scale drift detection — reduce false-critical severity from regime changes (neutral)

## Unexplored areas

- backend/services/shap_explainer.py
- backend/services/return_model.py
- backend/services/earnings_intelligence.py
- backend/services/tail_risk.py
- backend/services/tail_dependence.py
- backend/services/backtest.py
- backend/services/systemic_risk.py
- backend/services/bubble_detector.py
- backend/services/fundamentals.py
- backend/services/options_calibrator.py
- backend/services/factor_model.py
- backend/services/stress_testing.py
- backend/services/cross_sectional_momentum.py
- backend/services/economic_surprise.py
- backend/services/survival_model.py
- backend/services/anomaly_detector.py
- backend/services/crash_timeline.py
- backend/services/liquidity_risk.py
- backend/services/copula_tail.py
- backend/services/covariance.py

## When done

1. Experiment report: lab/experiments/cycle_051/experiment_report.json
   {
     "cycle": 51,
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

2. Commit: `git add -A && git commit -m "Lab cycle_051: <summary>"`

Think like a quant researcher who reads code carefully before writing it.
Audit first, then fix, then build. Quality over quantity.
