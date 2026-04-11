# Aegis Finance R&D Lab — Cycle 19, Phase A: EXPLORE

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

**Primary: Frontend & Visualization** — Fix TS errors, loading states, charts, SHAP visualizations
**Secondary: Service Integration & Wiring** — Find dead code, wire disconnected services, verify E2E

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
    "files": 9,
    "functions": 79
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
  "cycle": 19,
  "timestamp": "2026-04-12T00:46:34.251446",
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
      "action": "Buy",
      "composite_score": 0.217,
      "confidence": 21
    },
    "NVDA": {
      "action": "Buy",
      "composite_score": 0.345,
      "confidence": 34
    },
    "XOM": {
      "action": "Buy",
      "composite_score": 0.188,
      "confidence": 18
    },
    "JPM": {
      "action": "Buy",
      "composite_score": 0.153,
      "confidence": 15
    },
    "TSLA": {
      "action": "Buy",
      "composite_score": 0.241,
      "confidence": 24
    },
    "JNJ": {
      "action": "Hold",
      "composite_score": 0.077,
      "confidence": 7
    },
    "AMZN": {
      "action": "Buy",
      "composite_score": 0.257,
      "confidence": 25
    },
    "BA": {
      "action": "Buy",
      "composite_score": 0.222,
      "confidence": 22
    },
    "MSFT": {
      "action": "Buy",
      "composite_score": 0.229,
      "confidence": 22
    },
    "GOOGL": {
      "action": "Buy",
      "composite_score": 0.242,
      "confidence": 24
    },
    "META": {
      "action": "Buy",
      "composite_score": 0.288,
      "confidence": 28
    },
    "BAC": {
      "action": "Buy",
      "composite_score": 0.252,
      "confidence": 25
    },
    "CVX": {
      "action": "Buy",
      "composite_score": 0.219,
      "confidence": 21
    },
    "UNH": {
      "action": "Buy",
      "composite_score": 0.279,
      "confidence": 27
    },
    "WMT": {
      "action": "Buy",
      "composite_score": 0.153,
      "confidence": 15
    },
    "CAT": {
      "action": "Hold",
      "composite_score": 0.077,
      "confidence": 7
    }
  },
  "diversity": {
    "action_distribution": {
      "Buy": 14,
      "Hold": 2
    },
    "n_unique_actions": 2,
    "score_spread": 0.268,
    "score_std": 0.07,
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
  "final_mean": 9565.518114626899,
  "final_median": 8713.598829253122,
  "final_p05": 3834.2381785957546,
  "final_p10": 4653.347223834305,
  "final_p25": 6358.100832794762,
  "final_p75": 11836.074550577709,
  "final_p90": 15516.359031734659,
  "final_p95": 18456.50271801082,
  "total_return_pct": 40.32084899099131,
  "annual_return_pct": 7.010018892730274,
  "crash_prob_1y": 25.25,
  "crash_prob_5y": 81.86,
  "cvar_95_pct": -53.89644542231955,
  "max_dd_pct": -30.759638553683587,
  "max_drawdown_pct": 30.759638553683587
}
```

### stock_analysis
```json
{
  "AAPL": {
    "ticker": "AAPL",
    "current_price": 260.4800109863281,
    "mc_median_5y": 67.20335035859677,
    "mc_p10_5y": -21.193761541487877,
    "mc_p90_5y": 235.80429799036676,
    "garch_vol": 23.90772670036577,
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
    "mc_median_5y": 96.67993783099243,
    "mc_p10_5y": -51.47540696260799,
    "mc_p90_5y": 300.0,
    "garch_vol": 39.931857728936144,
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
    "mc_median_5y": 82.4470949935842,
    "mc_p10_5y": -6.299667884049409,
    "mc_p90_5y": 249.74752221538458,
    "garch_vol": 30.592922421361134,
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
    "mc_median_5y": 56.062835866198554,
    "mc_p10_5y": -15.623500576361293,
    "mc_p90_5y": 191.66554229853426,
    "garch_vol": 20.75694522048977,
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
Cycle 14: Upgrading project_portfolio to use the same GARCH-enhanced MC engine will produc (OK)
Cycle 15: Applying Ito correction consistently — using the actual base_vol that simulate_p (OK)
Cycle 16: Moving the GARCH fitting block (lines 178-205) before the Ito correction (lines  (OK)
Cycle 17: Per-sector GARCH fitting will produce more accurate sector-specific tail dynamic (OK)
Cycle 18: Wiring crash model predictions into stock MC will make per-stock simulations res (OK)

## Files never modified (explore these!)
- backend/services/regime_detector.py
- backend/services/risk_scorer.py
- backend/services/shap_explainer.py
- backend/services/news_intelligence.py
- backend/services/sentiment_analyzer.py
- backend/services/data_quality.py
- backend/services/net_liquidity.py
- backend/services/return_model.py
- backend/services/external_validator.py
- backend/services/regime_validator.py
- backend/services/drift_detector.py
- backend/services/llm_analyzer.py
- engine/training/features.py
- engine/training/train_crash_model.py
- engine/validation/walk_forward.py

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
