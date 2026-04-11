# Aegis Finance R&D Lab — Cycle 34, Phase A: EXPLORE

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

**Primary: Service Integration & Wiring** — Find dead code, wire disconnected services, verify E2E
**Secondary: Performance & Reliability** — Caching, retries, timeouts, structured logging

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
    "files": 17,
    "functions": 584
  },
  "code_smells": [],
  "n_smells": 0
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
  "cycle": 34,
  "timestamp": "2026-04-12T05:51:53.332757",
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
    "composite_score": 0.047,
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
      "macro_risk": -0.0,
      "drawdown": 0.0
    }
  },
  "stock_signals": {
    "AAPL": {
      "action": "Hold",
      "composite_score": 0.149,
      "confidence": 14
    },
    "NVDA": {
      "action": "Buy",
      "composite_score": 0.276,
      "confidence": 27
    },
    "XOM": {
      "action": "Buy",
      "composite_score": 0.16,
      "confidence": 15
    },
    "JPM": {
      "action": "Hold",
      "composite_score": 0.121,
      "confidence": 12
    },
    "TSLA": {
      "action": "Buy",
      "composite_score": 0.17,
      "confidence": 16
    },
    "JNJ": {
      "action": "Hold",
      "composite_score": 0.08,
      "confidence": 8
    },
    "AMZN": {
      "action": "Buy",
      "composite_score": 0.183,
      "confidence": 18
    },
    "BA": {
      "action": "Hold",
      "composite_score": 0.147,
      "confidence": 14
    },
    "MSFT": {
      "action": "Buy",
      "composite_score": 0.154,
      "confidence": 15
    },
    "GOOGL": {
      "action": "Buy",
      "composite_score": 0.167,
      "confidence": 16
    },
    "META": {
      "action": "Buy",
      "composite_score": 0.214,
      "confidence": 21
    },
    "BAC": {
      "action": "Buy",
      "composite_score": 0.18,
      "confidence": 18
    },
    "CVX": {
      "action": "Buy",
      "composite_score": 0.184,
      "confidence": 18
    },
    "UNH": {
      "action": "Buy",
      "composite_score": 0.201,
      "confidence": 20
    },
    "WMT": {
      "action": "Hold",
      "composite_score": 0.122,
      "confidence": 12
    },
    "CAT": {
      "action": "Hold",
      "composite_score": 0.128,
      "confidence": 12
    }
  },
  "diversity": {
    "action_distribution": {
      "Hold": 6,
      "Buy": 10
    },
    "n_unique_actions": 2,
    "score_spread": 0.196,
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
  "final_mean": 9576.774708554529,
  "final_median": 8704.145224216427,
  "final_p05": 3822.382537798876,
  "final_p10": 4588.776030764966,
  "final_p25": 6339.194920316094,
  "final_p75": 11935.806226000192,
  "final_p90": 15536.728026303032,
  "final_p95": 18502.586686299062,
  "total_return_pct": 40.48597698486931,
  "annual_return_pct": 7.035192682701341,
  "crash_prob_1y": 25.240000000000002,
  "crash_prob_5y": 81.36,
  "cvar_95_pct": -53.262229090105464,
  "max_dd_pct": -30.66634524720502,
  "max_drawdown_pct": 30.66634524720502
}
```

### stock_analysis
```json
{
  "AAPL": {
    "ticker": "AAPL",
    "current_price": 260.4800109863281,
    "mc_median_5y": 66.4862335424705,
    "mc_p10_5y": -20.53491270906568,
    "mc_p90_5y": 232.58648012207837,
    "garch_vol": 23.907750518538847,
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
    "mc_median_5y": 97.01687468490626,
    "mc_p10_5y": -52.70722328343334,
    "mc_p90_5y": 300.0,
    "garch_vol": 39.93270518152288,
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
    "mc_median_5y": 82.69864077584496,
    "mc_p10_5y": -7.164829063331391,
    "mc_p90_5y": 249.922249926168,
    "garch_vol": 30.5928999528494,
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
    "mc_median_5y": 56.4181381726758,
    "mc_p10_5y": -15.609500643517515,
    "mc_p90_5y": 191.93031902044027,
    "garch_vol": 20.756949625428444,
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
      "p95_price
... [truncated]
```

## Past Cycles
Cycle 31: Adding comprehensive router-level tests with hardened input validation on the ba (OK)
Cycle 32: Adding drawdown from 52-week high as an 8th signal component would improve signa (OK)
Cycle 33: Fixing the RRP unit conversion would produce correct net liquidity values on the (OK)

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
