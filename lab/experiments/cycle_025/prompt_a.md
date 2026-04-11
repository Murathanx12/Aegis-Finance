# Aegis Finance R&D Lab — Cycle 25, Phase A: EXPLORE

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

**Primary: New Features & Capabilities** — CVaR, factor exposure, drawdown signals, new endpoints
**Secondary: Frontend & Visualization** — Fix TS errors, loading states, charts, SHAP visualizations

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
    "files": 15,
    "functions": 393
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
  "cycle": 25,
  "timestamp": "2026-04-12T03:13:10.873357",
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
  "errors": [
    "AAPL: ImportError: `Import lxml` failed.  Use pip or conda to install the lxml package.",
    "NVDA: ImportError: `Import lxml` failed.  Use pip or conda to install the lxml package.",
    "XOM: ImportError: `Import lxml` failed.  Use pip or conda to install the lxml package.",
    "JPM: ImportError: `Import lxml` failed.  Use pip or conda to install the lxml package.",
    "TSLA: ImportError: `Import lxml` failed.  Use pip or conda to install the lxml package.",
    "JNJ: ImportError: `Import lxml` failed.  Use pip or conda to install the lxml package.",
    "AMZN: ImportError: `Import lxml` failed.  Use pip or conda to install the lxml package.",
    "BA: ImportError: `Import lxml` failed.  Use pip or conda to install the lxml package."
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
  "final_mean": 9581.383194244758,
  "final_median": 8690.208477036373,
  "final_p05": 3778.284954119696,
  "final_p10": 4619.502819025169,
  "final_p25": 6286.999547187916,
  "final_p75": 11978.559052629296,
  "final_p90": 15698.001036208048,
  "final_p95": 18448.68004805677,
  "total_return_pct": 40.55358091566181,
  "annual_return_pct": 7.045492084090288,
  "crash_prob_1y": 25.4,
  "crash_prob_5y": 81.89,
  "cvar_95_pct": -54.597419924180016,
  "max_dd_pct": -30.9097510293364,
  "max_drawdown_pct": 30.9097510293364
}
```

### stock_analysis
```json
{}
```

## Past Cycles
Cycle 20: Wiring per-stock signals into the single-stock endpoint will fix the most user-v (OK)
Cycle 21: Parallelizing the screener with ThreadPoolExecutor (8 workers) will reduce laten (OK)
Cycle 22: Changing analyst-target blending from convex combination to additive (with reduc (OK)
Cycle 23: Wiring the existing 3-state Gaussian HMM into all Monte Carlo call sites will ac (OK)
Cycle 24: Writing comprehensive tests for all 7 untested services, narrowing broad except  (OK)

## Files never modified (explore these!)
- backend/services/shap_explainer.py
- backend/services/data_quality.py
- backend/services/net_liquidity.py
- backend/services/return_model.py
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
