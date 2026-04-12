# Aegis Finance — R&D Cycle 48

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
    "files": 30,
    "functions": 939
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
  "cycle": 48,
  "timestamp": "2026-04-12T15:11:59.749784",
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
    "ABBV": {
      "action": "Hold",
      "composite_score": 0.016,
      "confidence": 1
    },
    "UNH": {
      "action": "Hold",
      "composite_score": 0.029,
      "confidence": 2
    },
    "AMZN": {
      "action": "Buy",
      "composite_score": 0.383,
      "confidence": 38
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
    "PG": {
      "action": "Hold",
      "composite_score": 0.071,
      "confidence": 7
    },
    "RUN": {
      "action": "Hold",
      "composite_score": -0.083,
      "confidence": 8
    },
    "NEM": {
      "action": "Buy",
      "composite_score": 0.353,
      "confidence": 35
    },
    "SQ": {
      "action": "Buy",
      "composite_score": 0.172,
      "confidence": 17
    },
    "RIVN": {
      "action": "Sell",
      "composite_score": -0.151,
      "confidence": 15
    },
    "DAL": {
      "action": "Buy",
      "composite_score": 0.347,
      "confidence": 34
    },
    "OKTA": {
      "action": "Hold",
      "composite_score": -0.08,
      "confidence": 8
    }
  },
  "diversity": {
    "action_distribution": {
      "Hold": 5,
      "Buy": 6,
      "Sell": 1
    },
    "n_unique_actions": 3,
    "score_spread": 0.534,
    "score_std": 0.182,
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
  "final_mean": 9569.306631703494,
  "final_median": 8717.77874290922,
  "final_p05": 3841.3009522926895,
  "final_p10": 4663.414109510047,
  "final_p25": 6320.6765178189335,
  "final_p75": 11937.15669927522,
  "final_p90": 15559.176357129545,
  "final_p95": 18187.384189428045,
  "total_return_pct": 40.376424436694755,
  "annual_return_pct": 7.018494023252564,
  "crash_prob_1y": 25.19,
  "crash_prob_5y": 82.08,
  "cvar_95_pct": -54.57798159793621,
  "max_dd_pct": -30.815966436840263,
  "max_drawdown_pct": 30.815966436840263
}
```

### stock_analysis
```json
{
  "ABBV": {
    "ticker": "ABBV",
    "current_price": 207.94000244140625,
    "mc_median_5y": 87.85887625881064,
    "mc_p10_5y": 1.9772730168143848,
    "mc_p90_5y": 248.275550331189,
    "garch_vol": 23.83686476845013,
    "garch_nu": 8.0,
    "crash_prob_3m": 2.15,
    "signal_action": "Buy",
    "signal_score": 0.246,
    "beta": 0.364,
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
      "key_stats",
      "peers",
      "options_calibration"
    ]
  },
  "UNH": {
    "ticker": "UNH",
    "current_price": 304.3299865722656,
    "mc_median_5y": 12.511963588083841,
    "mc_p10_5y": -51.18814948346782,
    "mc_p90_5y": 151.8194930986542,
    "garch_vol": 37.39071284818097,
    "garch_nu": 8.0,
    "crash_prob_3m": 2.9,
    "signal_action": "Hold",
    "signal_score": -0.089,
    "beta": 0.408,
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
      "key_stats",
      "peers",
      "options_calibration"
    ]
  },
  "AMZN": {
    "ticker": "AMZN",
    "current_price": 238.3800048828125,
    "mc_median_5y": 37.16028456062668,
    "mc_p10_5y": -42.79778225082984,
    "mc_p90_5y": 207.5445400001799,
    "garch_vol": 32.134140405958654,
    "garch_nu": 8.0,
    "crash_prob_3m": 5.18,
    "signal_action": "Buy",
    "signal_score": 0.338,
    "beta": 1.383,
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
      "key_stats",
      "peers",
      "options_calibration"
    ]
  },
  "JPM": {
    "ticker": "JPM",
    "current_price": 309.8699951171875,
    "mc_median_5y": 62.86355839819699,
    "mc_p10_5y": -14.060383052321523,
    "mc_p90_5y": 208.67364823491133,
    "garch_vol": 20.756950491020522,
    "garch_nu": 8.0,
    "crash_prob_3m": 3.64,
    "signal_action": "Buy",
    "signal_score": 0.361,
    "beta": 1.043,
    "sector": "Financial Services",
    "all_keys": [
      "ticker",
      "name",
      
... [truncated]
```

## Recent cycles (for context, not to constrain you)

Cycle 45: ['Added regime_signal_weights to config.py with 3 regime-specific weight profiles (Bull, Bear, Volatile)', 'Bull profile: momentum 0.20 (up from 0.12), drawdown 0.15 (confirm trend), crash_prob 0.14 (less relevant in trends)', 'Bear profile: crash_prob 0.24 (critical), mean_reversion 0.16 (contrarian opportunities), momentum 0.06 (breaks down in bears)', 'Volatile profile: valuation 0.16 (VIX signals matter most), mean_reversion 0.14, momentum 0.08 (unreliable in whipsaws)', 'Neutral/Unknown fall through to default weights (backward compatible)', 'Modified signal_engine.py get_market_signal() to select weight profile based on regime parameter', 'Drift adjustment applies ON TOP of regime-selected weights (layered, not conflicting)', 'Added regime_weight_profile key to result dict for transparency', 'Wrote 15 tests covering: profile selection, behavioral effects, drift interaction, config validation, backward compatibility'] (neutral)
Cycle 46: ? (neutral)
Cycle 47: ? (neutral)

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
   lab/experiments/cycle_048/experiment_report.json

   Include: what you noticed, what you did, files modified, files created,
   tests added, results (before/after), honest analysis, self-critique,
   next steps, confidence, depth rating.

2. Commit: git add -A && git commit -m "Lab cycle_048: <summary>"

Think fresh. Don't follow patterns from past cycles just because they worked.
Find what this codebase actually needs right now and build it.
