# Aegis Finance — R&D Cycle 36

You are the owner of this codebase. This is your sandbox.

You have 40 minutes. You have COMPLETE freedom:
- Read, write, create, delete any file in backend/, frontend/, engine/
- Install any package (pip install, npm install)
- Clone any open-source repo for reference
- Access any public API (yfinance, FRED, Alpha Vantage, etc.)
- Download datasets, models, or tools
- Restructure code, refactor architecture, add new services
- If you need an API key that costs money, note it in your report — don't block on it

You decide:
- What to work on (no assigned track — find the highest-impact thing)
- How to work (your own workflow — explore, build, test in whatever order makes sense)
- What to test (run targeted tests, not the full 675-test suite — be smart about it)
- When you're done

## Current engine state (from real backend services)

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
    "files": 19,
    "functions": 661
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
  "cycle": 36,
  "timestamp": "2026-04-12T11:50:15.429102",
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
    "confidence": 28,
    "color": "green",
    "composite_score": 0.282,
    "reasons": [
      "Low crash risk (1% 3M)",
      "Bullish market regime",
      "External consensus: BULLISH"
    ],
    "components": {
      "crash_prob": 0.598,
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
      "composite_score": 0.392,
      "confidence": 39
    },
    "NVDA": {
      "action": "Strong Buy",
      "composite_score": 0.605,
      "confidence": 60
    },
    "XOM": {
      "action": "Buy",
      "composite_score": 0.344,
      "confidence": 34
    },
    "JPM": {
      "action": "Buy",
      "composite_score": 0.359,
      "confidence": 35
    },
    "TSLA": {
      "action": "Strong Buy",
      "composite_score": 0.469,
      "confidence": 46
    },
    "JNJ": {
      "action": "Buy",
      "composite_score": 0.268,
      "confidence": 26
    },
    "AMZN": {
      "action": "Buy",
      "composite_score": 0.445,
      "confidence": 44
    },
    "BA": {
      "action": "Buy",
      "composite_score": 0.391,
      "confidence": 39
    },
    "MSFT": {
      "action": "Buy",
      "composite_score": 0.397,
      "confidence": 39
    },
    "GOOGL": {
      "action": "Buy",
      "composite_score": 0.411,
      "confidence": 41
    },
    "META": {
      "action": "Strong Buy",
      "composite_score": 0.471,
      "confidence": 47
    },
    "BAC": {
      "action": "Buy",
      "composite_score": 0.432,
      "confidence": 43
    },
    "CVX": {
      "action": "Buy",
      "composite_score": 0.39,
      "confidence": 38
    },
    "UNH": {
      "action": "Buy",
      "composite_score": 0.395,
      "confidence": 39
    },
    "WMT": {
      "action": "Buy",
      "composite_score": 0.333,
      "confidence": 33
    },
    "CAT": {
      "action": "Buy",
      "composite_score": 0.4,
      "confidence": 39
    }
  },
  "diversity": {
    "action_distribution": {
      "Buy": 13,
      "Strong Buy": 3
    },
    "n_unique_actions": 2,
    "score_spread": 0.337,
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
  "final_mean": 9563.728516616284,
  "final_median": 8701.653406211051,
  "final_p05": 3847.42714876925,
  "final_p10": 4671.161506159584,
  "final_p25": 6351.2529495552335,
  "final_p75": 11814.981856749082,
  "final_p90": 15585.25813483321,
  "final_p95": 18517.610141626727,
  "total_return_pct": 40.294596580071925,
  "annual_return_pct": 7.006014525218052,
  "crash_prob_1y": 25.590000000000003,
  "crash_prob_5y": 82.0,
  "cvar_95_pct": -53.4829518092916,
  "max_dd_pct": -30.689378088793738,
  "max_drawdown_pct": 30.689378088793738
}
```

### stock_analysis
```json
{
  "AAPL": {
    "ticker": "AAPL",
    "current_price": 260.4800109863281,
    "mc_median_5y": 60.9811449839897,
    "mc_p10_5y": -21.148282202195688,
    "mc_p90_5y": 214.29227149960477,
    "garch_vol": 23.90774866523113,
    "garch_nu": 8.0,
    "crash_prob_3m": 1.0,
    "signal_action": "Buy",
    "signal_score": 0.392,
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
    "mc_median_5y": 75.8236455260588,
    "mc_p10_5y": -56.58808745946489,
    "mc_p90_5y": 300.0,
    "garch_vol": 39.9325553135754,
    "garch_nu": 8.0,
    "crash_prob_3m": 1.0,
    "signal_action": "Strong Buy",
    "signal_score": 0.605,
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
    "mc_median_5y": 71.79331178370877,
    "mc_p10_5y": -12.810625648084761,
    "mc_p90_5y": 232.7813857113852,
    "garch_vol": 30.592876565240434,
    "garch_nu": 8.0,
    "crash_prob_3m": 1.0,
    "signal_action": "Buy",
    "signal_score": 0.344,
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
    "mc_median_5y": 52.137696521065656,
    "mc_p10_5y": -18.10706565213436,
    "mc_p90_5y": 182.77481216287788,
    "garch_vol": 20.756939762990825,
    "garch_nu": 8.0,
    "crash_prob_3m": 1.0,
    "signal_action": "Buy",
    "signal_score": 0.359,
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

## Recent cycles (for context, not to constrain you)

Cycle 33: 1. Removed `* 1000` from RRP in net_liquidity.py — all three FRED series are in millions. 2. Added 'net_liquidity' and ' (improved)
Cycle 34: 1. Created _compute_market_signal_for_lab() — a 95-line function that fetches real market data via DataFetcher and wires (improved)
Cycle 35: 1. Moved crash probability clip bounds from hardcoded values to config['ml']['calibration']. 2. Added degenerate calibra (improved)

## Files that have NEVER been modified by the lab

- backend/services/shap_explainer.py
- backend/services/return_model.py
- engine/training/train_crash_model.py
- engine/validation/walk_forward.py
- engine/validation/metrics.py
- frontend/src/app/
- frontend/src/components/
- frontend/src/lib/

## Pre-existing test failures

```
None — all tests passing
```

## One rule

Don't break existing tests. Run `python -m pytest backend/tests/<relevant_file> -v --tb=short`
on the specific tests related to your changes — NOT the full suite (it has 675 tests and
takes 9 minutes). Only run the full suite if you're unsure what you might have affected.

## When you're done

1. Write your experiment report:
   lab/experiments/cycle_036/experiment_report.json

   Include: what you noticed, what you did, files modified, files created,
   tests added, results (before/after), honest analysis, self-critique,
   next steps, confidence, depth rating.

2. Commit: git add -A && git commit -m "Lab cycle_036: <summary>"

Think fresh. Don't follow patterns from past cycles just because they worked.
Find what this codebase actually needs right now and build it.
