# Aegis Finance R&D Lab — Cycle 35, Phase A: EXPLORE

You are a senior quant engineer and the DE FACTO OWNER of this codebase.
You have FULL autonomy. You can:
- Modify ANY file in backend/, frontend/, engine/
- Install new packages (pip install, npm install)
- Clone reference repos or download datasets
- Access any public API (yfinance, FRED, etc.)
- Create new services, endpoints, tests, components
- Restructure code, refactor architectures
- If an API key is needed and you think it's vital, note it in the report

This is YOUR sandbox. Build what the project needs.

## Research Track

**Primary: Performance & Reliability** — Caching, retries, timeouts, structured logging
**Secondary: ML & Feature Engineering** — Improve crash model features, retrain, improve AUC-ROC

## Engine Output (from real backend services)

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
  }
}
```

### code_metrics
```json
{
  "test_count": {
    "files": 18,
    "functions": 619
  },
  "code_smells": [],
  "n_smells": 0
}
```

### drift_check
```json
{
  "drift_detected": true,
  "n_features_checked": 163,
  "n_drifted": 161,
  "drift_pct": 98.8,
  "drifted_features": [
    "daily_ret",
    "log_ret",
    "mom_1w",
    "mom_2w",
    "mom_1m",
    "mom_2m",
    "mom_3m",
    "mom_6m",
    "mom_12m",
    "dist_52w_high"
  ]
}
```

### market_snapshot
```json
{
  "sp500": {
    "symbol": "^GSPC",
    "price": 6816.89,
    "change_1d_pct": -0.114
  },
  "nasdaq": {
    "symbol": "^IXIC",
    "price": 22902.89,
    "change_1d_pct": 0.353
  },
  "dow": {
    "symbol": "^DJI",
    "price": 47916.57,
    "change_1d_pct": -0.559
  },
  "vix": {
    "symbol": "^VIX",
    "price": 19.23,
    "change_1d_pct": -1.334
  },
  "treasury_10y": {
    "symbol": "^TNX",
    "price": 4.32,
    "change_1d_pct": 0.559
  },
  "gold": {
    "symbol": "GC=F",
    "price": 4761.9,
    "change_1d_pct": -0.632
  },
  "oil": {
    "symbol": "CL=F",
    "price": 96.57,
    "change_1d_pct": -1.328
  },
  "usd_index": {
    "symbol": "DX-Y.NYB",
    "price": 98.65,
    "change_1d_pct": -0.172
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
    "current": 1.14,
    "mean": 0.369,
    "max": 4.0,
    "type": "Series"
  }
}
```

### run_metadata
```json
{
  "cycle": 35,
  "timestamp": "2026-04-12T06:25:08.831863",
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
    "confidence": 27,
    "color": "green",
    "composite_score": 0.279,
    "reasons": [
      "Low crash risk (2% 3M)",
      "Bullish market regime",
      "External consensus: BULLISH"
    ],
    "components": {
      "crash_prob": 0.584,
      "regime": 0.7,
      "valuation": 0.1,
      "momentum": -0.012,
      "mean_reversion": 0.0,
      "external": 0.4,
      "macro_risk": -0.073,
      "drawdown": 0.0
    }
  },
  "stock_signals": {
    "AAPL": {
      "action": "Buy",
      "composite_score": 0.389,
      "confidence": 38
    },
    "NVDA": {
      "action": "Strong Buy",
      "composite_score": 0.601,
      "confidence": 60
    },
    "XOM": {
      "action": "Buy",
      "composite_score": 0.342,
      "confidence": 34
    },
    "JPM": {
      "action": "Buy",
      "composite_score": 0.356,
      "confidence": 35
    },
    "TSLA": {
      "action": "Strong Buy",
      "composite_score": 0.466,
      "confidence": 46
    },
    "JNJ": {
      "action": "Buy",
      "composite_score": 0.265,
      "confidence": 26
    },
    "AMZN": {
      "action": "Buy",
      "composite_score": 0.442,
      "confidence": 44
    },
    "BA": {
      "action": "Buy",
      "composite_score": 0.388,
      "confidence": 38
    },
    "MSFT": {
      "action": "Buy",
      "composite_score": 0.393,
      "confidence": 39
    },
    "GOOGL": {
      "action": "Buy",
      "composite_score": 0.408,
      "confidence": 40
    },
    "META": {
      "action": "Strong Buy",
      "composite_score": 0.468,
      "confidence": 46
    },
    "BAC": {
      "action": "Buy",
      "composite_score": 0.429,
      "confidence": 42
    },
    "CVX": {
      "action": "Buy",
      "composite_score": 0.387,
      "confidence": 38
    },
    "UNH": {
      "action": "Buy",
      "composite_score": 0.392,
      "confidence": 39
    },
    "WMT": {
      "action": "Buy",
      "composite_score": 0.33,
      "confidence": 33
    },
    "CAT": {
      "action": "Buy",
      "composite_score": 0.396,
      "confidence": 39
    }
  },
  "diversity": {
    "action_distribution": {
      "Buy": 13,
      "Strong Buy": 3
    },
    "n_unique_actions": 2,
    "score_spread": 0.336,
    "score_std": 0.071,
    "all_same_action": false
  },
  "n_tickers_with_signal": 16,
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
  "current_price": 6816.89013671875,
  "final_mean": 9566.077079510791,
  "final_median": 8727.819091196889,
  "final_p05": 3875.965462808997,
  "final_p10": 4638.022426122768,
  "final_p25": 6339.989497760751,
  "final_p75": 11887.658922065231,
  "final_p90": 15617.911538168597,
  "final_p95": 18199.580032181664,
  "total_return_pct": 40.32904869602809,
  "annual_return_pct": 7.011269498165262,
  "crash_prob_1y": 25.330000000000002,
  "crash_prob_5y": 81.54,
  "cvar_95_pct": -54.32641201844148,
  "max_dd_pct": -30.744284753786093,
  "max_drawdown_pct": 30.744284753786093
}
```

### stock_analysis
```json
{
  "AAPL": {
    "ticker": "AAPL",
    "current_price": 260.4800109863281,
    "mc_median_5y": 60.55691923563711,
    "mc_p10_5y": -20.806356195286302,
    "mc_p90_5y": 214.23330459484555,
    "garch_vol": 23.907740007619584,
    "garch_nu": 8.0,
    "crash_prob_3m": 2.0,
    "signal_action": "Buy",
    "signal_score": 0.389,
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
      "analyst_targets",
      "recommendations",
      "holders",
      "news",
      "earnings",
      "price_history",
      "key_stats",
      "peers"
    ]
  },
  "NVDA": {
    "ticker": "NVDA",
    "current_price": 188.6300048828125,
    "mc_median_5y": 76.27189659291899,
    "mc_p10_5y": -56.717568327445754,
    "mc_p90_5y": 300.0,
    "garch_vol": 39.93386303122934,
    "garch_nu": 8.0,
    "crash_prob_3m": 2.0,
    "signal_action": "Strong Buy",
    "signal_score": 0.601,
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
      "analyst_targets",
      "recommendations",
      "holders",
      "news",
      "earnings",
      "price_history",
      "key_stats",
      "peers"
    ]
  },
  "XOM": {
    "ticker": "XOM",
    "current_price": 152.50999450683594,
    "mc_median_5y": 71.8933490175608,
    "mc_p10_5y": -12.371731323946955,
    "mc_p90_5y": 234.9660211119387,
    "garch_vol": 30.592826019784354,
    "garch_nu": 8.0,
    "crash_prob_3m": 2.0,
    "signal_action": "Buy",
    "signal_score": 0.342,
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
      "analyst_targets",
      "recommendations",
      "holders",
      "news",
      "earnings",
      "price_history",
      "key_stats",
      "peers"
    ]
  },
  "JPM": {
    "ticker": "JPM",
    "current_price": 309.8699951171875,
    "mc_median_5y": 52.587503589747065,
    "mc_p10_5y": -17.83637937080694,
    "mc_p90_5y": 181.9546693046473,
    "garch_vol": 20.7569619999961,
    "garch_nu": 8.0,
    "crash_prob_3m": 2.0,
    "signal_action": "Buy",
    "signal_score": 0.356,
    "beta": 1.043,
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
 
... [truncated]
```

## Past Cycles
Cycle 31: Adding comprehensive router-level tests with hardened input validation on the ba (OK)
Cycle 32: Adding drawdown from 52-week high as an 8th signal component would improve signa (OK)
Cycle 33: Fixing the RRP unit conversion would produce correct net liquidity values on the (OK)
Cycle 34: Porting the routers/stock.py _compute_market_signal() logic into data_generator  (OK)

## Files never modified (explore these!)
- backend/services/shap_explainer.py
- backend/services/return_model.py
- engine/training/train_crash_model.py
- engine/validation/walk_forward.py
- engine/validation/metrics.py

## Pre-existing test failures
```
None
```

## Phase A Instructions

This is Phase 1 of 4. Right now: EXPLORE ONLY.
1. Read 8+ source files across backend/services/, routers/, engine/
2. Run tests: python -m pytest backend/tests/ -v -m "not slow" --tb=short
3. Look at the engine output data above — what's broken or suboptimal?
4. Check at least 3 files from the "never modified" list
5. Report your top 3 findings with file paths and line numbers

Don't implement yet — explore thoroughly. The deeper you go now, the better Phase B will be.
