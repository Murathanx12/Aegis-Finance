# Aegis Finance — R&D Cycle 39

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
    "files": 21,
    "functions": 737
  },
  "code_smells": [],
  "n_smells": 0
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
    "price": 4787.4,
    "change_1d_pct": -0.1
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
  "cycle": 39,
  "timestamp": "2026-04-12T12:50:04.358198",
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
    "confidence": 16,
    "color": "green",
    "composite_score": 0.165,
    "reasons": [
      "Low crash risk (3% 3M)",
      "Bullish market regime",
      "External consensus: BULLISH"
    ],
    "components": {
      "crash_prob": 0.015,
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
    "TSLA": {
      "action": "Buy",
      "composite_score": 0.32,
      "confidence": 32
    },
    "JPM": {
      "action": "Buy",
      "composite_score": 0.241,
      "confidence": 24
    },
    "XOM": {
      "action": "Buy",
      "composite_score": 0.252,
      "confidence": 25
    },
    "AAPL": {
      "action": "Buy",
      "composite_score": 0.271,
      "confidence": 27
    },
    "GOOGL": {
      "action": "Buy",
      "composite_score": 0.29,
      "confidence": 28
    },
    "MA": {
      "action": "Buy",
      "composite_score": 0.298,
      "confidence": 29
    },
    "TTD": {
      "action": "Buy",
      "composite_score": 0.384,
      "confidence": 38
    },
    "LUV": {
      "action": "Buy",
      "composite_score": 0.271,
      "confidence": 27
    },
    "CELH": {
      "action": "Buy",
      "composite_score": 0.281,
      "confidence": 28
    },
    "CRWD": {
      "action": "Buy",
      "composite_score": 0.229,
      "confidence": 22
    },
    "OSCR": {
      "action": "Buy",
      "composite_score": 0.237,
      "confidence": 23
    },
    "ENPH": {
      "action": "Buy",
      "composite_score": 0.394,
      "confidence": 39
    }
  },
  "diversity": {
    "action_distribution": {
      "Buy": 12
    },
    "n_unique_actions": 1,
    "score_spread": 0.165,
    "score_std": 0.051,
    "all_same_action": true
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
  "current_price": 6816.89013671875,
  "final_mean": 9583.405022973833,
  "final_median": 8733.29448305587,
  "final_p05": 3799.6075350274396,
  "final_p10": 4675.442368421929,
  "final_p25": 6277.014314890251,
  "final_p75": 11985.416217976906,
  "final_p90": 15751.924232630097,
  "final_p95": 18272.217634955246,
  "total_return_pct": 40.58324002250564,
  "annual_return_pct": 7.050009373112709,
  "crash_prob_1y": 25.1,
  "crash_prob_5y": 81.25,
  "cvar_95_pct": -54.74743639421461,
  "max_dd_pct": -30.73978753239785,
  "max_drawdown_pct": 30.73978753239785
}
```

### stock_analysis
```json
{
  "TSLA": {
    "ticker": "TSLA",
    "current_price": 348.95001220703125,
    "mc_median_5y": 10.68235550853105,
    "mc_p10_5y": -79.9431837329399,
    "mc_p90_5y": 300.0,
    "garch_vol": 46.19372297953308,
    "garch_nu": 8.0,
    "crash_prob_3m": 7.99,
    "signal_action": "Buy",
    "signal_score": 0.26,
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
    "mc_median_5y": 52.01004771784397,
    "mc_p10_5y": -19.94620163750014,
    "mc_p90_5y": 189.84473641046722,
    "garch_vol": 20.756991103967138,
    "garch_nu": 8.0,
    "crash_prob_3m": 3.64,
    "signal_action": "Buy",
    "signal_score": 0.235,
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
    "mc_median_5y": 72.09943200563198,
    "mc_p10_5y": -11.336306903874938,
    "mc_p90_5y": 229.19108658698732,
    "garch_vol": 30.592890689518804,
    "garch_nu": 8.0,
    "crash_prob_3m": 2.12,
    "signal_action": "Buy",
    "signal_score": 0.266,
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
  "AAPL": {
    "ticker": "AAPL",
    "current_price": 260.4800109863281,
    "mc_median_5y": 60.43901977811197,
    "mc_p10_5y": -23.08419525108565,
    "mc_p90_5y": 219.93209636923004,
    "garch_vol": 23.907738457528534,
    "garch_nu": 8.0,
    "crash_prob_3m": 3.99,
    "signal_action": "Buy",
    "signal_score": 0.261,
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
      
... [truncated]
```

## Recent cycles (for context, not to constrain you)

Cycle 36: ? (neutral)
Cycle 37: ? (neutral)
Cycle 38: ? (neutral)

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
   lab/experiments/cycle_039/experiment_report.json

   Include: what you noticed, what you did, files modified, files created,
   tests added, results (before/after), honest analysis, self-critique,
   next steps, confidence, depth rating.

2. Commit: git add -A && git commit -m "Lab cycle_039: <summary>"

Think fresh. Don't follow patterns from past cycles just because they worked.
Find what this codebase actually needs right now and build it.
