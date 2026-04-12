# Aegis Finance — R&D Cycle 50

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
    "files": 36,
    "functions": 1038
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
  "cycle": 50,
  "timestamp": "2026-04-12T15:57:13.496575",
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
    "confidence": 17,
    "color": "green",
    "composite_score": 0.172,
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
    "drift_crash_weight_mult": 0.2,
    "regime_weight_profile": "Bull"
  },
  "stock_signals": {
    "HD": {
      "action": "Hold",
      "composite_score": 0.027,
      "confidence": 2
    },
    "JPM": {
      "action": "Buy",
      "composite_score": 0.27,
      "confidence": 27
    },
    "JNJ": {
      "action": "Buy",
      "composite_score": 0.267,
      "confidence": 26
    },
    "UNH": {
      "action": "Hold",
      "composite_score": 0.029,
      "confidence": 2
    },
    "GOOGL": {
      "action": "Buy",
      "composite_score": 0.301,
      "confidence": 30
    },
    "ABBV": {
      "action": "Hold",
      "composite_score": 0.016,
      "confidence": 1
    },
    "MRVL": {
      "action": "Strong Buy",
      "composite_score": 0.552,
      "confidence": 55
    },
    "FCX": {
      "action": "Strong Buy",
      "composite_score": 0.559,
      "confidence": 55
    },
    "PENN": {
      "action": "Hold",
      "composite_score": 0.087,
      "confidence": 8
    },
    "ABNB": {
      "action": "Buy",
      "composite_score": 0.166,
      "confidence": 16
    },
    "UPST": {
      "action": "Hold",
      "composite_score": -0.033,
      "confidence": 3
    },
    "DKNG": {
      "action": "Sell",
      "composite_score": -0.183,
      "confidence": 18
    }
  },
  "diversity": {
    "action_distribution": {
      "Hold": 5,
      "Buy": 4,
      "Strong Buy": 2,
      "Sell": 1
    },
    "n_unique_actions": 4,
    "score_spread": 0.742,
    "score_std": 0.218,
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
  "final_mean": 9565.040528263467,
  "final_median": 8702.219887407646,
  "final_p05": 3806.662404894401,
  "final_p10": 4689.846939266736,
  "final_p25": 6343.849107213701,
  "final_p75": 11826.137130601372,
  "final_p90": 15630.460798163367,
  "final_p95": 18207.772289869576,
  "total_return_pct": 40.313843063745125,
  "annual_return_pct": 7.008950313990492,
  "crash_prob_1y": 25.35,
  "crash_prob_5y": 81.95,
  "cvar_95_pct": -54.071567859475586,
  "max_dd_pct": -30.73771874714267,
  "max_drawdown_pct": 30.73771874714267
}
```

### stock_analysis
```json
{
  "HD": {
    "ticker": "HD",
    "current_price": 337.3399963378906,
    "mc_median_5y": 44.307264677725186,
    "mc_p10_5y": -27.713793728194712,
    "mc_p90_5y": 176.3509701303247,
    "garch_vol": 26.274400848498452,
    "garch_nu": 8.0,
    "crash_prob_3m": 3.83,
    "signal_action": "Hold",
    "signal_score": -0.039,
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
      "options_calibration"
    ]
  },
  "JPM": {
    "ticker": "JPM",
    "current_price": 309.8699951171875,
    "mc_median_5y": 50.39092126688316,
    "mc_p10_5y": -20.909377007240337,
    "mc_p90_5y": 185.43977531691138,
    "garch_vol": 20.756945492998867,
    "garch_nu": 8.0,
    "crash_prob_3m": 3.64,
    "signal_action": "Buy",
    "signal_score": 0.361,
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
      "options_calibration"
    ]
  },
  "JNJ": {
    "ticker": "JNJ",
    "current_price": 238.4600067138672,
    "mc_median_5y": 30.08208099076015,
    "mc_p10_5y": -17.11110828773582,
    "mc_p90_5y": 103.72521218466768,
    "garch_vol": 15.831580557624509,
    "garch_nu": 8.0,
    "crash_prob_3m": 1.93,
    "signal_action": "Buy",
    "signal_score": 0.421,
    "beta": 0.329,
    "sector": "Healthcare",
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
      "options_calibration"
    ]
  },
  "UNH": {
    "ticker": "UNH",
    "current_price": 304.3299865722656,
    "mc_median_5y": 16.460826136665176,
    "mc_p10_5y": -48.30836469859411,
    "mc_p90_5y": 155.39953916017782,
    "garch_vol": 37.39067738422383,
    "garch_nu": 8.0,
    "crash_prob_3m": 2.9,
    "signal_action": "Hold",
  
... [truncated]
```

## Recent cycles (for context, not to constrain you)

Cycle 47: ? (neutral)
Cycle 48: ["Refactored get_stock_signal() to track each component's score contribution individually", "Added 'components' dict to stock signal output with 10 named components: market_base, beta_adjustment, analyst_target, sector_momentum, valuation (PE + earnings growth combined), crash_risk, drawdown, momentum, options, earnings", 'Added _compute_conviction_quality() function that measures cross-component agreement', 'Conviction quality classifies signals as high/moderate/low based on whether components agree or conflict', "Added 'conviction' dict to stock signal output with quality level, agreement_pct, dominant_driver, n_contributing", 'Wired new fields through screener endpoint (signal_components, signal_conviction) and single-stock endpoint', 'Wrote 31 targeted tests covering component structure, attribution correctness, conviction quality classification, backward compatibility, and stock differentiation'] (neutral)
Cycle 49: ['Fixed MC xi parameter: now reads garch_derived_params.xi from config instead of hardcoded 0.06', 'Fixed risk scorer VIX floor: replaced cascading pd.where with np.select for correct graduated thresholds', 'Fixed signal conviction dominant_driver: excludes market_base, uses only stock-specific components', 'Fixed stock_analyzer: recomputes Ito correction when options calibration changes vol', 'Added daily-resolution momentum fields to stock_analyzer output (momentum_1m, momentum_3m)', 'Updated stock router to use daily momentum from analyzer instead of computing from weekly-sampled data', 'Fixed screener to pass MC return fields to signal_analytics — risk_reward now actually works', 'Added prediction_confidence_score to screener output for opportunity scoring', 'Built compute_opportunity_score() — composite ranking metric combining signal score, Sharpe ratio, risk-reward ratio, and prediction confidence', 'Replaced Sharpe-only screener sort with opportunity_score sort', 'Added opportunity_score aggregate stats to signal analytics output', 'Wrote 14 new tests for opportunity score (differentiation, edge cases, monotonicity, clamping)'] (neutral)

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
   lab/experiments/cycle_050/experiment_report.json

   Include: what you noticed, what you did, files modified, files created,
   tests added, results (before/after), honest analysis, self-critique,
   next steps, confidence, depth rating.

2. Commit: git add -A && git commit -m "Lab cycle_050: <summary>"

Think fresh. Don't follow patterns from past cycles just because they worked.
Find what this codebase actually needs right now and build it.
