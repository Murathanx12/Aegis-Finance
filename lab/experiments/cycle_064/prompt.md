# Aegis Finance — R&D Cycle 64 (BUILD)

This project is YOUR SANDBOX. You have complete freedom. You are a senior quant
and fintech expert building an engine to compete with Bloomberg — but more
user-friendly and open-source.


## This is a BUILD cycle

Your primary goal: add a substantial new capability. Think like a quant at a hedge fund.

1. Search the web for what Bloomberg, OpenBB, Koyfin, or QuantConnect offer
   that Aegis doesn't. Pick the highest-impact gap.
2. `pip install` any packages that would help (riskfolio-lib, ta, arch, etc.)
3. Build the feature properly — full service file, config entries, API endpoint,
   tests, and frontend API client function.
4. Wire it into existing endpoints where it makes sense (don't just create
   isolated endpoints nobody calls).

Quality bar: The feature should be something a user would actually notice.
Not internal plumbing — visible analytics that show up in API responses.

Competitive targets (what we're missing that they have):
- Bloomberg PORT: risk budgeting, tracking error analysis, fixed income analytics
- Koyfin: 500+ screening metrics, custom screening filters, relative valuation tools
- TradingView: chart pattern recognition (head/shoulders, triangles, flags), alerts system
- OpenBB: broad data source coverage (we have ~10 sources, they have 100+), crypto/forex
- QuantConnect: walk-forward strategy backtesting with transaction costs
- Morningstar: style box analysis, fund overlap detection, income projections

ALREADY DONE (don't rebuild): technical analysis (ta lib), risk number (1-100),
sector rotation, drawdown recovery, rolling Sharpe/Sortino, retirement MC,
safe withdrawal rate, Polygon.io real-time data, copula tail risk, factor models


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
    "files": 61,
    "functions": 1374
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
    "tail_lower": 0.0753,
    "pearson": 0.4225
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
    "avg_dv_mm": 10603.4
  },
  "NVDA": {
    "score": 100.0,
    "tier": "highly_liquid",
    "amihud": 0.0,
    "avg_dv_mm": 29071.1
  },
  "COIN": {
    "score": 100.0,
    "tier": "highly_liquid",
    "amihud": 0.0,
    "avg_dv_mm": 1938.5
  }
}
```

### market_snapshot
```json
{
  "sp500": {
    "symbol": "^GSPC",
    "price": 7021.57,
    "change_1d_pct": -0.02
  },
  "nasdaq": {
    "symbol": "^IXIC",
    "price": 23997.68,
    "change_1d_pct": -0.076
  },
  "dow": {
    "symbol": "^DJI",
    "price": 48535.63,
    "change_1d_pct": 0.148
  },
  "vix": {
    "symbol": "^VIX",
    "price": 18.41,
    "change_1d_pct": 1.321
  },
  "treasury_10y": {
    "symbol": "^TNX",
    "price": 4.31,
    "change_1d_pct": 0.631
  },
  "gold": {
    "symbol": "GC=F",
    "price": 4810.8,
    "change_1d_pct": 0.225
  },
  "oil": {
    "symbol": "CL=F",
    "price": 91.12,
    "change_1d_pct": -0.186
  },
  "usd_index": {
    "symbol": "DX-Y.NYB",
    "price": 98.24,
    "change_1d_pct": 0.182
  }
}
```

### options_intelligence
```json
{
  "vix_term_structure": {
    "values": {
      "VIX": 18.3700008392334,
      "VIX3M": 21.040000915527344,
      "VIX9D": 16.43000030517578
    },
    "vix_vix3m_ratio": 0.873,
    "contango": true,
    "backwardation": false,
    "structure": "normal_contango",
    "signal": "neutral",
    "interpretation": "Normal term structure: VIX (18.4) < VIX3M (21.0)",
    "vix_level": "normal",
    "vix9d_vix_ratio": 0.894
  },
  "options_SPY": {
    "iv_skew": 1.444,
    "put_call_ratio": 1.899,
    "iv_rank": 81.7,
    "signal_score": -0.45,
    "signal_sentiment": "bearish"
  },
  "options_AAPL": {
    "iv_skew": 2.218,
    "put_call_ratio": 0.418,
    "iv_rank": 45.6,
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
    "current": 0.393,
    "mean": 0.37,
    "max": 4.0,
    "type": "Series"
  }
}
```

### run_metadata
```json
{
  "cycle": 64,
  "timestamp": "2026-04-17T02:27:09.199860",
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
    "composite_score": 0.236,
    "reasons": [
      "Crash model drift (critical) \u2014 ML signal weight reduced to 20%",
      "Low crash risk (3% 3M)",
      "Bullish market regime"
    ],
    "components": {
      "crash_prob": 0.015,
      "regime": 0.7,
      "valuation": 0.1,
      "momentum": 0.271,
      "mean_reversion": 0.0,
      "external": 0.4,
      "macro_risk": 0.029,
      "drawdown": 0.2,
      "systemic_risk": -0.15,
      "vix_term_structure": 0.1
    },
    "drift_severity": "critical",
    "drift_crash_weight_mult": 0.2,
    "regime_weight_profile": "Bull"
  },
  "stock_signals": {
    "HD": {
      "action": "Hold",
      "composite_score": 0.083,
      "confidence": 8
    },
    "GOOGL": {
      "action": "Buy",
      "composite_score": 0.427,
      "confidence": 42
    },
    "XOM": {
      "action": "Buy",
      "composite_score": 0.284,
      "confidence": 28
    },
    "JPM": {
      "action": "Buy",
      "composite_score": 0.37,
      "confidence": 37
    },
    "UNH": {
      "action": "Hold",
      "composite_score": 0.143,
      "confidence": 14
    },
    "AAPL": {
      "action": "Buy",
      "composite_score": 0.372,
      "confidence": 37
    },
    "LCID": {
      "action": "Hold",
      "composite_score": -0.142,
      "confidence": 14
    },
    "SEDG": {
      "action": "Hold",
      "composite_score": 0.02,
      "confidence": 2
    },
    "DAL": {
      "action": "Buy",
      "composite_score": 0.422,
      "confidence": 42
    },
    "HIMS": {
      "action": "Hold",
      "composite_score": 0.053,
      "confidence": 5
    },
    "RIVN": {
      "action": "Hold",
      "composite_score": 0.113,
      "confidence": 11
    },
    "UAL": {
      "action": "Buy",
      "composite_score": 0.226,
      "confidence": 22
    }
  },
  "diversity": {
    "action_distribution": {
      "Hold": 6,
      "Buy": 6
    },
    "n_unique_actions": 2,
    "score_spread": 0.569,
    "score_std": 0.174,
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
  "current_price": 7018.68994140625,
  "final_mean": 9854.58918240498,
  "final_median": 8995.000563635569,
  "final_p05": 3923.4853307561457,
  "final_p10": 4732.672360529956,
  "final_p25": 6497.349918754572,
  "final_p75": 12247.632901299736,
  "final_p90": 15984.431986142581,
  "final_p95": 18757.79704984506,
  "total_return_pct": 40.40496538062679,
  "annual_return_pct": 7.022845409854139,
  "crash_prob_1y": 25.19,
  "crash_prob_5y": 81.97,
  "cvar_95_pct": -54.43474740084523,
  "max_dd_pct": -30.81096046085114,
  "max_drawdown_pct": 30.81096046085114
}
```

### stock_analysis
```json
{
  "HD": {
    "ticker": "HD",
    "current_price": 337.7200012207031,
    "mc_median_5y": 26.237329876407635,
    "mc_p10_5y": -38.038431097405066,
    "mc_p90_5y": 147.08860476818563,
    "garch_vol": 25.55539826044454,
    "garch_nu": 8.0,
    "crash_prob_3m": 3.82,
    "signal_action": "Hold",
    "signal_score": 0.032,
    "beta": 1.085,
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
    "current_price": 334.70001220703125,
    "mc_median_5y": 54.29598383845982,
    "mc_p10_5y": -29.905951879409464,
    "mc_p90_5y": 222.75059632998304,
    "garch_vol": 28.936468215665514,
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
  "XOM": {
    "ticker": "XOM",
    "current_price": 152.4499969482422,
    "mc_median_5y": 52.79054211471752,
    "mc_p10_5y": -20.84866792572043,
    "mc_p90_5y": 191.1018125464175,
    "garch_vol": 29.456775655194082,
    "garch_nu": 8.0,
    "crash_prob_3m": 2.12,
    "signal_action": "Strong Buy",
    "signal_score": 0.527,
    "beta": 0.288,
    "sector": "Energy",
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
  "JPM": {
    "ticker": "JPM",
    "current_price": 308.80499267578125,
    "mc_median_5y": 37.3723904880964,
    "mc_p10_5y": -27.05482942280495,
    "mc_p90_5y": 159.72598161058818,
    "garch_vol": 24.055
... [truncated]
```

### systemic_risk
```json
{
  "turbulence_current": 1.9675,
  "turbulence_percentile": 28.1,
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

Cycle 59: Bug fixes (4) + VIX term structure regime detection integration (improved)
Cycle 60: Bug fixes (5) + portfolio factor exposures & copula risk endpoints (improved)
Cycle 62: Deep integration: 9 services wired into 3 user-facing endpoints + TA signal in composite + 10 frontend API functions (improved)
Cycle 63: Deep audit: 4 bugs fixed in retirement_mc.py and drawdown_analyzer.py (improved)

## When done

1. Write experiment report to: lab/experiments/cycle_064/experiment_report.json
   {
     "cycle": 64,
     "cycle_type": "BUILD",
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

2. Commit: `git add -A && git commit -m "Lab cycle_064: <summary>"`

You own this. Make it better. Don't hold back.
