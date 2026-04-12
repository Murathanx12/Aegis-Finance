# Aegis Finance — R&D Cycle 44

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
    "files": 27,
    "functions": 836
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

### options_intelligence
```json
{
  "vix_term_structure": {
    "values": {
      "VIX": 19.229999542236328,
      "VIX3M": 21.860000610351562,
      "VIX9D": 16.360000610351562
    },
    "vix_vix3m_ratio": 0.88,
    "contango": true,
    "backwardation": false,
    "structure": "normal_contango",
    "signal": "neutral",
    "interpretation": "Normal term structure: VIX (19.2) < VIX3M (21.9)",
    "vix_level": "normal",
    "vix9d_vix_ratio": 0.851
  },
  "options_SPY": {
    "iv_skew": 1.566,
    "put_call_ratio": 1.987,
    "iv_rank": 74.4,
    "signal_score": -0.35,
    "signal_sentiment": "bearish"
  },
  "options_AAPL": {
    "iv_skew": 2.025,
    "put_call_ratio": 0.801,
    "iv_rank": 50.1,
    "signal_score": -0.2,
    "signal_sentiment": "slightly_bearish"
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
  "cycle": 44,
  "timestamp": "2026-04-12T14:05:21.116182",
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
    "confidence": 19,
    "color": "green",
    "composite_score": 0.194,
    "reasons": [
      "Crash model drift (critical) \u2014 ML signal weight reduced to 20%",
      "Low crash risk (3% 3M)",
      "Bullish market regime"
    ],
    "components": {
      "crash_prob": 0.015,
      "regime": 0.7,
      "valuation": 0.1,
      "momentum": -0.012,
      "mean_reversion": 0.0,
      "external": 0.4,
      "macro_risk": -0.074,
      "drawdown": 0.0
    },
    "drift_severity": "critical",
    "drift_crash_weight_mult": 0.2
  },
  "stock_signals": {
    "MA": {
      "action": "Hold",
      "composite_score": 0.073,
      "confidence": 7
    },
    "COST": {
      "action": "Buy",
      "composite_score": 0.223,
      "confidence": 22
    },
    "GOOGL": {
      "action": "Buy",
      "composite_score": 0.324,
      "confidence": 32
    },
    "NVDA": {
      "action": "Buy",
      "composite_score": 0.414,
      "confidence": 41
    },
    "TSLA": {
      "action": "Hold",
      "composite_score": -0.082,
      "confidence": 8
    },
    "HD": {
      "action": "Hold",
      "composite_score": 0.05,
      "confidence": 4
    },
    "FSLR": {
      "action": "Hold",
      "composite_score": 0.083,
      "confidence": 8
    },
    "DDOG": {
      "action": "Hold",
      "composite_score": -0.125,
      "confidence": 12
    },
    "MARA": {
      "action": "Buy",
      "composite_score": 0.28,
      "confidence": 28
    },
    "COIN": {
      "action": "Hold",
      "composite_score": 0.004,
      "confidence": 0
    },
    "CELH": {
      "action": "Hold",
      "composite_score": -0.139,
      "confidence": 13
    },
    "CRWD": {
      "action": "Sell",
      "composite_score": -0.182,
      "confidence": 18
    }
  },
  "diversity": {
    "action_distribution": {
      "Hold": 7,
      "Buy": 4,
      "Sell": 1
    },
    "n_unique_actions": 3,
    "score_spread": 0.596,
    "score_std": 0.188,
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
  "current_price": 6816.89013671875,
  "final_mean": 9565.475750975796,
  "final_median": 8710.23065441188,
  "final_p05": 3874.041020352394,
  "final_p10": 4651.754375154761,
  "final_p25": 6317.051245941873,
  "final_p75": 11883.717195237026,
  "final_p90": 15542.668083585888,
  "final_p95": 18415.763246303435,
  "total_return_pct": 40.32022753970998,
  "annual_return_pct": 7.009924107626508,
  "crash_prob_1y": 25.7,
  "crash_prob_5y": 82.24000000000001,
  "cvar_95_pct": -53.9371387749289,
  "max_dd_pct": -30.764436970253655,
  "max_drawdown_pct": 30.764436970253655
}
```

### stock_analysis
```json
{
  "MA": {
    "ticker": "MA",
    "current_price": 498.6600036621094,
    "mc_median_5y": 76.24515862692391,
    "mc_p10_5y": -1.6227557578356255,
    "mc_p90_5y": 208.09661680728038,
    "garch_vol": 25.14144786211181,
    "garch_nu": 8.0,
    "crash_prob_3m": 3.24,
    "signal_action": "Hold",
    "signal_score": 0.092,
    "beta": 0.831,
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
      "key_stats",
      "peers"
    ]
  },
  "COST": {
    "ticker": "COST",
    "current_price": 998.469970703125,
    "mc_median_5y": 68.95772695643625,
    "mc_p10_5y": -10.346790135807538,
    "mc_p90_5y": 218.18135084831027,
    "garch_vol": 18.828906607317425,
    "garch_nu": 8.0,
    "crash_prob_3m": 3.38,
    "signal_action": "Buy",
    "signal_score": 0.27,
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
      "key_stats",
      "peers"
    ]
  },
  "GOOGL": {
    "ticker": "GOOGL",
    "current_price": 317.239990234375,
    "mc_median_5y": 88.46092642957235,
    "mc_p10_5y": -13.133186675136777,
    "mc_p90_5y": 291.7166246247322,
    "garch_vol": 29.76084104295065,
    "garch_nu": 8.0,
    "crash_prob_3m": 4.26,
    "signal_action": "Strong Buy",
    "signal_score": 0.504,
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
      "key_stats",
      "peers"
    ]
  },
  "NVDA": {
    "ticker": "NVDA",
    "current_price": 188.6300048828125,
    "mc_median_5y": 76.18451322624733,
    "mc_p10_5y": -56.86366556869198,
    "mc_p90_5y": 300.0,
    "garch_vol": 39.932711105491684,
    "garch_nu": 8.0,
    "crash_prob_3m": 7.99,
    "signal_action": "Strong Buy",
    "signal_score": 0.544,
    "beta": 2.335,
    "sector": "Technology",
    "all_keys": [
      "ticker",
      "name",
      "sector",
      "current_price",
      "market_cap",
      "cap_tier",

... [truncated]
```

## Recent cycles (for context, not to constrain you)

Cycle 42: ? (neutral)

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
   lab/experiments/cycle_044/experiment_report.json

   Include: what you noticed, what you did, files modified, files created,
   tests added, results (before/after), honest analysis, self-critique,
   next steps, confidence, depth rating.

2. Commit: git add -A && git commit -m "Lab cycle_044: <summary>"

Think fresh. Don't follow patterns from past cycles just because they worked.
Find what this codebase actually needs right now and build it.
