# Aegis Finance R&D Lab — Cycle 24, Phase A: EXPLORE

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

**Primary: Test Suite & Code Quality** — Write tests for uncovered services, fix smells, 200+ test target
**Secondary: New Features & Capabilities** — CVaR, factor exposure, drawdown signals, new endpoints

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
    "files": 14,
    "functions": 271
  },
  "code_smells": [
    "portfolio_engine.py: 5 broad excepts",
    "stock_analyzer.py: 8 broad excepts"
  ],
  "n_smells": 2
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
  "cycle": 24,
  "timestamp": "2026-04-12T02:45:31.083869",
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
    "action": "Hold",
    "confidence": 4,
    "color": "amber",
    "composite_score": 0.046,
    "reasons": [
      "Mixed signals \u2014 no strong conviction"
    ],
    "components": {
      "crash_prob": 0.0,
      "regime": 0.0,
      "valuation": 0.3,
      "momentum": 0.0,
      "mean_reversion": 0.0,
      "external": 0.0,
      "macro_risk": -0.0
    }
  },
  "stock_signals": {
    "AAPL": {
      "action": "Hold",
      "composite_score": 0.148,
      "confidence": 14
    },
    "NVDA": {
      "action": "Buy",
      "composite_score": 0.274,
      "confidence": 27
    },
    "XOM": {
      "action": "Buy",
      "composite_score": 0.159,
      "confidence": 15
    },
    "JPM": {
      "action": "Hold",
      "composite_score": 0.12,
      "confidence": 12
    },
    "TSLA": {
      "action": "Buy",
      "composite_score": 0.169,
      "confidence": 16
    },
    "JNJ": {
      "action": "Hold",
      "composite_score": 0.079,
      "confidence": 7
    },
    "AMZN": {
      "action": "Buy",
      "composite_score": 0.182,
      "confidence": 18
    },
    "BA": {
      "action": "Hold",
      "composite_score": 0.146,
      "confidence": 14
    },
    "MSFT": {
      "action": "Buy",
      "composite_score": 0.153,
      "confidence": 15
    },
    "GOOGL": {
      "action": "Buy",
      "composite_score": 0.166,
      "confidence": 16
    },
    "META": {
      "action": "Buy",
      "composite_score": 0.213,
      "confidence": 21
    },
    "BAC": {
      "action": "Buy",
      "composite_score": 0.179,
      "confidence": 17
    },
    "CVX": {
      "action": "Buy",
      "composite_score": 0.183,
      "confidence": 18
    },
    "UNH": {
      "action": "Buy",
      "composite_score": 0.201,
      "confidence": 20
    },
    "WMT": {
      "action": "Hold",
      "composite_score": 0.121,
      "confidence": 12
    },
    "CAT": {
      "action": "Hold",
      "composite_score": 0.127,
      "confidence": 12
    }
  },
  "diversity": {
    "action_distribution": {
      "Hold": 6,
      "Buy": 10
    },
    "n_unique_actions": 2,
    "score_spread": 0.195,
    "score_std": 0.043,
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
  "final_mean": 9559.487819920421,
  "final_median": 8736.504993161801,
  "final_p05": 3857.942336509745,
  "final_p10": 4683.752287533725,
  "final_p25": 6361.071635880475,
  "final_p75": 11822.084082440302,
  "final_p90": 15581.361204115556,
  "final_p95": 18121.238627579834,
  "total_return_pct": 40.23238790997732,
  "annual_return_pct": 6.996523236168128,
  "crash_prob_1y": 24.560000000000002,
  "crash_prob_5y": 81.78,
  "cvar_95_pct": -54.14423238560823,
  "max_dd_pct": -30.74371156131508,
  "max_drawdown_pct": 30.74371156131508
}
```

### stock_analysis
```json
{
  "AAPL": {
    "ticker": "AAPL",
    "current_price": 260.4800109863281,
    "mc_median_5y": 66.08706638334006,
    "mc_p10_5y": -20.855974144341427,
    "mc_p90_5y": 232.81927303171375,
    "garch_vol": 23.907728095157914,
    "garch_nu": 8.0,
    "crash_prob_3m": null,
    "signal_action": null,
    "signal_score": null,
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
    "mc_median_5y": 96.09203582776192,
    "mc_p10_5y": -52.91386927414234,
    "mc_p90_5y": 300.0,
    "garch_vol": 39.932624790838545,
    "garch_nu": 8.0,
    "crash_prob_3m": null,
    "signal_action": null,
    "signal_score": null,
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
    "mc_median_5y": 82.16207783652385,
    "mc_p10_5y": -5.907320924941029,
    "mc_p90_5y": 248.29160200039325,
    "garch_vol": 30.592802722199064,
    "garch_nu": 8.0,
    "crash_prob_3m": null,
    "signal_action": null,
    "signal_score": null,
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
    "mc_median_5y": 55.99751025324375,
    "mc_p10_5y": -17.671333645851206,
    "mc_p90_5y": 196.9226964693579,
    "garch_vol": 20.75692597486423,
    "garch_nu": 8.0,
    "crash_prob_3m": null,
    "signal_action": null,
    "signal_score": null,
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
      "p95
... [truncated]
```

## Past Cycles
Cycle 19: Fixing the 4 broken call sites will activate the external consensus signal in bu (OK)
Cycle 20: Wiring per-stock signals into the single-stock endpoint will fix the most user-v (OK)
Cycle 21: Parallelizing the screener with ThreadPoolExecutor (8 workers) will reduce laten (OK)
Cycle 22: Changing analyst-target blending from convex combination to additive (with reduc (OK)
Cycle 23: Wiring the existing 3-state Gaussian HMM into all Monte Carlo call sites will ac (OK)

## Files never modified (explore these!)
- backend/services/shap_explainer.py
- backend/services/data_quality.py
- backend/services/net_liquidity.py
- backend/services/return_model.py
- backend/services/regime_validator.py
- backend/services/llm_analyzer.py
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
