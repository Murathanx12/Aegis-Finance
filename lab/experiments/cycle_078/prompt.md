# Aegis Finance — R&D Cycle 78 (DEEP_AUDIT)

This project is YOUR SANDBOX. You have complete freedom. You are a senior quant
and fintech expert building an engine to compete with Bloomberg — but more
user-friendly and open-source.


## This is a DEEP AUDIT cycle

Your primary goal: find and fix bugs. Read code carefully before writing any.

1. Pick 3-5 service files and READ THEM LINE BY LINE
2. For each bug you find, write a regression test FIRST, then fix the bug
3. Look for: wrong math, off-by-one errors, NaN handling, stale code,
   inconsistencies between config values and actual usage, broad except blocks
4. Run the full fast test suite at the end: `python -m pytest backend/tests/ -v -m "not slow" --tb=line -q`
5. Fix any failures you caused

Quality bar: Find at least 3 real bugs (not style issues). Each fix should
have a test that would have caught it.


## Your powers — USE THEM (the lab has historically underused these)

- **Install packages**: `pip install X` — do this! Past 54 cycles installed 0 packages.
  Useful: `ta` (technical analysis), `arch` (GARCH), `ruptures` (changepoint),
  `plotly` (charts), `pytrends` (Google Trends), `fredapi`, etc.
- **Web search**: Search for state-of-the-art approaches, competitor features,
  recent papers, new free data APIs. The lab has never done web research.
- **Download and study code**: Look at OpenBB, riskfolio-lib, skfolio source code
  for implementation patterns.
- **Access APIs**: yfinance, FRED, Finnhub, SEC EDGAR, Treasury.gov, BLS, GDELT
- **Modify ANY file**: backend/, frontend/, engine/, lab/, config, requirements.txt
- **Create new services**: Build entire new .py files with tests and endpoints

## Current engine (53 services, 45+ endpoints, 1350+ tests)

Backend services: monte_carlo, stock_analyzer, sector_analyzer, portfolio_engine,
crash_model, signal_engine (12 components), regime_detector, risk_scorer, shap_explainer,
news_intelligence, llm_analyzer (Claude+DeepSeek), sentiment_analyzer, data_fetcher,
data_quality, net_liquidity, return_model, external_validator, regime_validator,
drift_detector, tail_risk, tail_dependence, backtest, signal_optimizer,
options_intelligence, earnings_intelligence, systemic_risk, bubble_detector,
fundamentals, options_calibrator, prediction_confidence, signal_analytics,
factor_model (FF6+PCA), stress_testing (+hypothetical), cross_sectional_momentum,
economic_surprise, survival_model, anomaly_detector, crash_timeline,
liquidity_risk, copula_tail, covariance (RMT), portfolio_optimizer (CVaR/RP/MaxDiv/HRP),
insider_trading, trends_sentiment, attribution (Brinson+MCTR), conformal_predictor,
**technical_analysis** (RSI/MACD/BB/ADX/OBV via `ta` lib),
**polygon_client** (real-time quotes, intraday bars),
**risk_number** (Bloomberg PORT-style 1-100 risk score),
**sector_rotation** (multi-timeframe relative strength + business cycle),
**drawdown_analyzer** (drawdown recovery analysis + rolling returns/Sharpe),
**retirement_mc** (Monte Carlo retirement sim + safe withdrawal rate)

API keys available: FRED, Finnhub, FMP, DeepSeek, Alpha Vantage, Polygon.io, ANTHROPIC
Installed packages: ta, polygon-api-client, riskfolio-lib, copulas, ruptures, pytrends

Signal engine components: crash_prob, regime, valuation, momentum, mean_reversion,
external, macro_risk, drawdown, economic_surprise, momentum_breadth, insider_trading,
vix_term_structure

## Engine data snapshot

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
    "files": 67,
    "functions": 1539
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
    "tail_lower": 0.0748,
    "pearson": 0.4213
  },
  "SPY_GLD": {
    "best_copula": "student_t",
    "tail_lower": 0.1463,
    "pearson": 0.1198
  }
}
```

### drift_check
```json
{
  "drift_detected": true,
  "n_features_checked": 158,
  "n_drifted": 141,
  "drift_pct": 89.2,
  "severity": "critical",
  "reference_window": 504,
  "inference_window": 252,
  "drifted_features": [
    "mom_6m",
    "mom_12m",
    "dist_52w_high",
    "dist_52w_low",
    "drawdown_from_peak",
    "vol_1m",
    "vol_3m",
    "vol_6m",
    "vol_12m",
    "vol_ratio_1m_3m"
  ],
  "recent_stability": "unstable",
  "scale_used": "long",
  "multi_scale": {
    "long": {
      "severity": "critical",
      "effective_severity": "critical",
      "drift_pct": 89.2,
      "n_drifted": 141,
      "n_features_checked": 158,
      "reference_window": 504,
      "inference_window": 252
    },
    "medium": {
      "severity": "critical",
      "effective_severity": "critical",
      "drift_pct": 94.3,
      "n_drifted": 150,
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
  "composite_score": -0.067,
  "signal": "neutral",
  "trend": "deteriorating",
  "indicators_tracked": 8,
  "positive_surprises": 3,
  "negative_surprises": 2,
  "breadth": 0.38,
  "indicators": [
    {
      "series_id": "NFCI",
      "name": "Chicago Fed NFCI",
      "latest_value": -0.47,
      "trend_value": -0.5,
      "surprise_pct": -6.44,
      "surprise_normalized": -0.644,
      "weight": 1.3,
      "weighted_surprise": -0.837,
      "surprise_trend": -11.73
    },
    {
      "series_id": "CPIAUCSL",
      "name": "Consumer Price Index",
      "latest_value": 330.29,
      "trend_value": 323.77,
      "surprise_pct": -241.63,
      "surprise_normalized": -1.0,
      "weight": 0.8,
      "weighted_surprise": -0.8,
      "surprise_trend": -41.78
    },
    {
      "series_id": "BAMLH0A0HYM2",
      "name": "High Yield Spread",
      "latest_value": 2.85,
      "trend_value": 3.0,
      "surprise_pct": 5.0,
      "surprise_normalized": 0.5,
      "weight": 1.2,
      "weighted_surprise": 0.6,
      "surprise_trend": 6.78
    },
    {
      "series_id": "ICSA",
      "name": "Initial Jobless Claims",
      "latest_value": 207000.0,
      "trend_value": 211000.0,
      "surprise_pct": 1.9,
      "surprise_normalized": 0.19,
      "weight": 1.5,
      "weighted_surprise": 0.284,
      "surprise_trend": 0.67
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
      "latest_value": 101.79,
      "trend_value": 101.6,
      "surprise_pct": 0.18,
      "surprise_normalized": 0.018,
      "weight": 1.2,
      "weighted_surprise": 0.022,
      "surprise_trend": 0.29
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
    "avg_dv_mm": 10825.6
  },
  "NVDA": {
    "score": 100.0,
    "tier": "highly_liquid",
    "amihud": 0.0,
    "avg_dv_mm": 29470.0
  },
  "COIN": {
    "score": 100.0,
    "tier": "highly_liquid",
    "amihud": 0.0,
    "avg_dv_mm": 1964.0
  }
}
```

### market_snapshot
```json
{
  "sp500": {
    "symbol": "^GSPC",
    "price": 7041.28,
    "change_1d_pct": 0.261
  },
  "nasdaq": {
    "symbol": "^IXIC",
    "price": 24102.7,
    "change_1d_pct": 0.361
  },
  "dow": {
    "symbol": "^DJI",
    "price": 48578.72,
    "change_1d_pct": 0.237
  },
  "vix": {
    "symbol": "^VIX",
    "price": 17.94,
    "change_1d_pct": -1.266
  },
  "treasury_10y": {
    "symbol": "^TNX",
    "price": 4.31,
    "change_1d_pct": 0.631
  },
  "gold": {
    "symbol": "GC=F",
    "price": 4817.7,
    "change_1d_pct": 0.369
  },
  "oil": {
    "symbol": "CL=F",
    "price": 89.82,
    "change_1d_pct": -1.61
  },
  "usd_index": {
    "symbol": "DX-Y.NYB",
    "price": 98.18,
    "change_1d_pct": 0.122
  }
}
```

### options_intelligence
```json
{
  "vix_term_structure": {
    "values": {
      "VIX": 17.940000534057617,
      "VIX3M": 20.770000457763672,
      "VIX9D": 15.460000038146973
    },
    "vix_vix3m_ratio": 0.864,
    "contango": true,
    "backwardation": false,
    "structure": "normal_contango",
    "signal": "neutral",
    "interpretation": "Normal term structure: VIX (17.9) < VIX3M (20.8)",
    "vix_level": "calm",
    "vix9d_vix_ratio": 0.862
  },
  "options_SPY": {
    "iv_skew": 1.443,
    "put_call_ratio": 1.849,
    "iv_rank": 47.8,
    "signal_score": -0.1,
    "signal_sentiment": "slightly_bearish"
  },
  "options_AAPL": {
    "iv_skew": 2.267,
    "put_call_ratio": 0.367,
    "iv_rank": 42.2,
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
    "current": 0.389,
    "mean": 0.37,
    "max": 4.0,
    "type": "Series"
  }
}
```

### run_metadata
```json
{
  "cycle": 78,
  "timestamp": "2026-04-17T07:33:23.260383",
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
    "confidence": 22,
    "color": "green",
    "composite_score": 0.224,
    "reasons": [
      "Crash model drift (critical) \u2014 ML signal weight reduced to 20%",
      "Low crash risk (3% 3M)",
      "Bullish market regime"
    ],
    "components": {
      "crash_prob": 0.015,
      "regime": 0.7,
      "valuation": 0.1,
      "momentum": 0.285,
      "mean_reversion": 0.0,
      "external": 0.4,
      "macro_risk": 0.037,
      "drawdown": 0.2,
      "systemic_risk": -0.3,
      "vix_term_structure": 0.1
    },
    "drift_severity": "critical",
    "drift_crash_weight_mult": 0.2,
    "regime_weight_profile": "Bull"
  },
  "stock_signals": {
    "TSLA": {
      "action": "Hold",
      "composite_score": 0.104,
      "confidence": 10
    },
    "GOOGL": {
      "action": "Buy",
      "composite_score": 0.418,
      "confidence": 41
    },
    "V": {
      "action": "Buy",
      "composite_score": 0.19,
      "confidence": 18
    },
    "PG": {
      "action": "Hold",
      "composite_score": 0.074,
      "confidence": 7
    },
    "UNH": {
      "action": "Hold",
      "composite_score": 0.145,
      "confidence": 14
    },
    "JNJ": {
      "action": "Buy",
      "composite_score": 0.282,
      "confidence": 28
    },
    "ENPH": {
      "action": "Hold",
      "composite_score": 0.06,
      "confidence": 6
    },
    "CCL": {
      "action": "Buy",
      "composite_score": 0.233,
      "confidence": 23
    },
    "OKTA": {
      "action": "Hold",
      "composite_score": -0.107,
      "confidence": 10
    },
    "NET": {
      "action": "Hold",
      "composite_score": 0.143,
      "confidence": 14
    },
    "OSCR": {
      "action": "Hold",
      "composite_score": 0.075,
      "confidence": 7
    },
    "U": {
      "action": "Hold",
      "composite_score": 0.061,
      "confidence": 6
    }
  },
  "diversity": {
    "action_distribution": {
      "Hold": 8,
      "Buy": 4
    },
    "n_unique_actions": 2,
    "score_spread": 0.525,
    "score_std": 0.127,
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
  "current_price": 7041.27978515625,
  "final_mean": 9887.773966434044,
  "final_median": 9005.301765073611,
  "final_p05": 3921.6883422982205,
  "final_p10": 4781.910710037948,
  "final_p25": 6551.435526508683,
  "final_p75": 12299.857827855958,
  "final_p90": 16154.538359382377,
  "final_p95": 18996.35500754464,
  "total_return_pct": 40.425807071017125,
  "annual_return_pct": 7.026022511994712,
  "crash_prob_1y": 25.35,
  "crash_prob_5y": 82.21000000000001,
  "cvar_95_pct": -54.32432826432616,
  "max_dd_pct": -30.809548547781485,
  "max_drawdown_pct": 30.809548547781485
}
```

### stock_analysis
```json
{
  "TSLA": {
    "ticker": "TSLA",
    "current_price": 388.8999938964844,
    "mc_median_5y": -12.51884355809969,
    "mc_p10_5y": -83.99316780439369,
    "mc_p90_5y": 290.78259037698314,
    "garch_vol": 48.38068508016434,
    "garch_nu": 8.0,
    "crash_prob_3m": 7.99,
    "signal_action": "Hold",
    "signal_score": -0.098,
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
  "GOOGL": {
    "ticker": "GOOGL",
    "current_price": 336.0199890136719,
    "mc_median_5y": 55.48367113414483,
    "mc_p10_5y": -28.59941408534278,
    "mc_p90_5y": 222.6893786535853,
    "garch_vol": 28.942164194960668,
    "garch_nu": 8.0,
    "crash_prob_3m": 4.26,
    "signal_action": "Strong Buy",
    "signal_score": 0.523,
    "beta": 1.128,
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
      "options_calibration",
      "factor_exposure"
    ]
  },
  "V": {
    "ticker": "V",
    "current_price": 315.1000061035156,
    "mc_median_5y": 48.240845262188216,
    "mc_p10_5y": -17.98221828498989,
    "mc_p90_5y": 158.5668650412756,
    "garch_vol": 21.9230583085462,
    "garch_nu": 8.0,
    "crash_prob_3m": 3.1,
    "signal_action": "Hold",
    "signal_score": 0.114,
    "beta": 0.799,
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
      "options_calibration",
      "factor_exposure"
    ]
  },
  "PG": {
    "ticker": "PG",
    "current_price": 143.11000061035156,
    "mc_median_5y": 20.413361075164826,
    "mc_p10_5y": -30.860809262814826,
    "mc_p90_5y": 103.8069814083638,
    "garch_vol": 19.36
... [truncated]
```

### systemic_risk
```json
{
  "turbulence_current": 2.7567,
  "turbulence_percentile": 40.1,
  "turbulence_threshold_pctl": 90,
  "absorption_ratio_current": 0.9248,
  "absorption_ratio_change_1m": -0.0065,
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

## Recent cycles (don't repeat)

Cycle 73: Portfolio Benchmark Analytics — Bloomberg PORT-style tracking error, IR, active share, capture ratios (improved)
Cycle 74: Integrated survival model + tail risk into user-facing endpoints (improved)
Cycle 75: Deep audit: 4 bugs fixed in economic_surprise, liquidity_risk, drawdown_analyzer, retirement_mc (improved)
Cycle 76: Volatility Analytics — Bloomberg-style vol cone, GARCH forecast, regime detection (improved)
Cycle 77: Frontend integration: portfolio attribution/MCTR/benchmark, crash timeline, market valuation dashboard (improved)

## When done

1. Write experiment report to: lab/experiments/cycle_078/experiment_report.json
   {
     "cycle": 78,
     "cycle_type": "DEEP_AUDIT",
     "timestamp": "<ISO timestamp>",
     "title": "<one-line summary of what you did>",
     "category": "<quantitative|data|frontend|reliability|integration>",
     "observation": {
       "bugs_found": ["<list of bugs found>"],
       "gap_identified": "<the main gap you addressed>"
     },
     "implementation": {
       "bugs_fixed": ["<description of each fix>"],
       "feature_built": "<what you added>",
       "files_changed": ["<list>"],
       "files_created": ["<list>"],
       "packages_installed": ["<list of pip packages installed>"]
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

2. Commit: `git add -A && git commit -m "Lab cycle_078: <summary>"`

You own this. Make it better. Don't hold back.
