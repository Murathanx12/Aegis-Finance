# Aegis Finance — R&D Cycle 68 (INTEGRATE)

This project is YOUR SANDBOX. You have complete freedom. You are a senior quant
and fintech expert building an engine to compete with Bloomberg — but more
user-friendly and open-source.


## This is an INTEGRATE cycle

Your primary goal: wire existing services into the main user-facing endpoints.
A service that exists but doesn't show up in API responses is wasted code.

Check these integration points:
1. Stock analysis (`/api/stock/{ticker}`) — does it show: factor exposure,
   liquidity score, insider signal, momentum rank, TA signal, trend attention?
2. Portfolio analysis (`/api/portfolio/analyze`) — does it include: attribution,
   MCTR, copula VaR, factor exposures, risk number (1-100)?
3. Market status (`/api/market-status`) — does it include: trends sentiment,
   VIX term structure state, changepoint detection, sector rotation?
4. Screener (`/api/stock/screener`) — do the stock signals use all 12 components?
   Does it include TA signal per stock?
5. Frontend (`frontend/src/lib/api.ts`) — are ALL backend endpoints callable?
6. Sector rotation (`/api/analytics/sector-rotation`) — is it wired into
   market status or sectors page?
7. Real-time data (`/api/realtime/{ticker}`) — is Polygon used for fresher
   prices in stock analysis when available?

Also:
- Build/improve frontend components that display new analytics
- Add caching to slow endpoints
- Wire new data into the signal engine (every new signal source should
  eventually feed the composite score)

Quality bar: At least 2 services that were standalone-only are now
integrated into a user-facing endpoint.


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
    "files": 63,
    "functions": 1427
  },
  "code_smells": [
    "technical_analysis.py: 5 broad excepts"
  ],
  "n_smells": 1
}
```

### copula_snapshot
```json
{
  "AAPL_MSFT": {
    "best_copula": "student_t",
    "tail_lower": 0.0748,
    "pearson": 0.4216
  },
  "SPY_GLD": {
    "best_copula": "student_t",
    "tail_lower": 0.1464,
    "pearson": 0.1199
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
  "composite_score": 0.006,
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
    "avg_dv_mm": 10662.0
  },
  "NVDA": {
    "score": 100.0,
    "tier": "highly_liquid",
    "amihud": 0.0,
    "avg_dv_mm": 29246.5
  },
  "COIN": {
    "score": 100.0,
    "tier": "highly_liquid",
    "amihud": 0.0,
    "avg_dv_mm": 1952.5
  }
}
```

### market_snapshot
```json
{
  "sp500": {
    "symbol": "^GSPC",
    "price": 7036.48,
    "change_1d_pct": 0.193
  },
  "nasdaq": {
    "symbol": "^IXIC",
    "price": 24082.21,
    "change_1d_pct": 0.276
  },
  "dow": {
    "symbol": "^DJI",
    "price": 48579.96,
    "change_1d_pct": 0.24
  },
  "vix": {
    "symbol": "^VIX",
    "price": 17.95,
    "change_1d_pct": -1.211
  },
  "treasury_10y": {
    "symbol": "^TNX",
    "price": 4.31,
    "change_1d_pct": 0.631
  },
  "gold": {
    "symbol": "GC=F",
    "price": 4812.7,
    "change_1d_pct": 0.265
  },
  "oil": {
    "symbol": "CL=F",
    "price": 90.14,
    "change_1d_pct": -1.26
  },
  "usd_index": {
    "symbol": "DX-Y.NYB",
    "price": 98.17,
    "change_1d_pct": 0.114
  }
}
```

### options_intelligence
```json
{
  "vix_term_structure": {
    "values": {
      "VIX": 17.93000030517578,
      "VIX3M": 20.700000762939453,
      "VIX9D": 15.710000038146973
    },
    "vix_vix3m_ratio": 0.866,
    "contango": true,
    "backwardation": false,
    "structure": "normal_contango",
    "signal": "neutral",
    "interpretation": "Normal term structure: VIX (17.9) < VIX3M (20.7)",
    "vix_level": "calm",
    "vix9d_vix_ratio": 0.876
  },
  "options_SPY": {
    "iv_skew": 1.45,
    "put_call_ratio": 1.777,
    "iv_rank": 40.4,
    "signal_score": -0.1,
    "signal_sentiment": "slightly_bearish"
  },
  "options_AAPL": {
    "iv_skew": 2.368,
    "put_call_ratio": 0.409,
    "iv_rank": 48.3,
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
  "cycle": 68,
  "timestamp": "2026-04-17T03:45:02.882161",
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
    "confidence": 23,
    "color": "green",
    "composite_score": 0.237,
    "reasons": [
      "Crash model drift (critical) \u2014 ML signal weight reduced to 20%",
      "Low crash risk (3% 3M)",
      "Bullish market regime"
    ],
    "components": {
      "crash_prob": 0.015,
      "regime": 0.7,
      "valuation": 0.1,
      "momentum": 0.277,
      "mean_reversion": 0.0,
      "external": 0.4,
      "macro_risk": 0.031,
      "drawdown": 0.2,
      "systemic_risk": -0.15,
      "vix_term_structure": 0.1
    },
    "drift_severity": "critical",
    "drift_crash_weight_mult": 0.2,
    "regime_weight_profile": "Bull"
  },
  "stock_signals": {
    "PG": {
      "action": "Hold",
      "composite_score": 0.089,
      "confidence": 8
    },
    "COST": {
      "action": "Buy",
      "composite_score": 0.229,
      "confidence": 22
    },
    "GOOGL": {
      "action": "Buy",
      "composite_score": 0.431,
      "confidence": 43
    },
    "V": {
      "action": "Buy",
      "composite_score": 0.205,
      "confidence": 20
    },
    "ABBV": {
      "action": "Hold",
      "composite_score": 0.121,
      "confidence": 12
    },
    "HD": {
      "action": "Hold",
      "composite_score": 0.08,
      "confidence": 8
    },
    "OKTA": {
      "action": "Hold",
      "composite_score": -0.1,
      "confidence": 9
    },
    "MRVL": {
      "action": "Strong Buy",
      "composite_score": 0.629,
      "confidence": 62
    },
    "ENPH": {
      "action": "Hold",
      "composite_score": 0.072,
      "confidence": 7
    },
    "LUV": {
      "action": "Hold",
      "composite_score": 0.096,
      "confidence": 9
    },
    "TDOC": {
      "action": "Hold",
      "composite_score": 0.074,
      "confidence": 7
    },
    "PENN": {
      "action": "Buy",
      "composite_score": 0.32,
      "confidence": 31
    }
  },
  "diversity": {
    "action_distribution": {
      "Hold": 7,
      "Buy": 4,
      "Strong Buy": 1
    },
    "n_unique_actions": 3,
    "score_spread": 0.729,
    "score_std": 0.186,
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
  "current_price": 7038.85986328125,
  "final_mean": 9882.127069839584,
  "final_median": 8960.943856709922,
  "final_p05": 4005.8304737914614,
  "final_p10": 4853.383085459066,
  "final_p25": 6526.975287904583,
  "final_p75": 12357.635736027667,
  "final_p90": 16185.327051781474,
  "final_p95": 18805.337191765902,
  "total_return_pct": 40.39386011064738,
  "annual_return_pct": 7.021152371160078,
  "crash_prob_1y": 24.62,
  "crash_prob_5y": 81.69999999999999,
  "cvar_95_pct": -53.930728922022375,
  "max_dd_pct": -30.74800090855537,
  "max_drawdown_pct": 30.74800090855537
}
```

### stock_analysis
```json
{
  "PG": {
    "ticker": "PG",
    "current_price": 143.41000366210938,
    "mc_median_5y": 20.13813002409335,
    "mc_p10_5y": -29.912063007426703,
    "mc_p90_5y": 101.5709650498784,
    "garch_vol": 19.3690718029682,
    "garch_nu": 8.0,
    "crash_prob_3m": 2.16,
    "signal_action": "Hold",
    "signal_score": 0.057,
    "beta": 0.403,
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
      "options_calibration",
      "factor_exposure"
    ]
  },
  "COST": {
    "ticker": "COST",
    "current_price": 985.8800048828125,
    "mc_median_5y": 49.8619168606147,
    "mc_p10_5y": -21.65164381115533,
    "mc_p90_5y": 187.02932616739298,
    "garch_vol": 21.067680221312244,
    "garch_nu": 8.0,
    "crash_prob_3m": 3.39,
    "signal_action": "Buy",
    "signal_score": 0.308,
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
      "options_calibration",
      "factor_exposure"
    ]
  },
  "GOOGL": {
    "ticker": "GOOGL",
    "current_price": 335.57000732421875,
    "mc_median_5y": 56.02802925644104,
    "mc_p10_5y": -27.58934659848016,
    "mc_p90_5y": 221.77453898748732,
    "garch_vol": 28.929522442301174,
    "garch_nu": 8.0,
    "crash_prob_3m": 4.21,
    "signal_action": "Strong Buy",
    "signal_score": 0.565,
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
    "current_price": 315.6600036621094,
    "mc_median_5y": 47.20280836859245,
    "mc_p10_5y": -17.46965766008204,
    "mc_p90_5y": 157.65186684527492,
    "garch_vol": 21.92
... [truncated]
```

### systemic_risk
```json
{
  "turbulence_current": 1.9998,
  "turbulence_percentile": 28.6,
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

Cycle 63: Deep audit: 4 bugs fixed in retirement_mc.py and drawdown_analyzer.py (improved)
Cycle 64: Relative Valuation & Peer Comparison (Koyfin-style) (improved)
Cycle 65: Deep frontend integration: 10+ backend analytics wired into stock detail, portfolio, and screener pages (improved)
Cycle 66: Deep audit: 3 math/logic bugs fixed in retirement_mc, sector_rotation, technical_analysis (improved)

## When done

1. Write experiment report to: lab/experiments/cycle_068/experiment_report.json
   {
     "cycle": 68,
     "cycle_type": "INTEGRATE",
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

2. Commit: `git add -A && git commit -m "Lab cycle_068: <summary>"`

You own this. Make it better. Don't hold back.
