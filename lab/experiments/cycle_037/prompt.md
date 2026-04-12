# Aegis Finance — R&D Cycle 37

You OWN this codebase. This is your sandbox. Improve the engine.

## Your powers — use them

- Modify ANY file: backend/, frontend/, engine/, AND lab/ (yes, you can improve the lab tools too)
- Install packages: `pip install X`, `npm install X`
- Clone repos: `git clone https://github.com/...` into a temp directory for reference
- Web search: search for state-of-the-art approaches, open-source quant engines, papers
- Access APIs: yfinance, FRED, Alpha Vantage, Finnhub, any public finance API
- Download anything: datasets, pre-trained models, reference implementations
- If an API key is needed and it's vital, note it in your report

## Your goal

Make this engine compete with institutional-grade tools. Think about what
Bloomberg Terminal, QuantConnect, OpenBB, or a prop trading desk would have
that we don't. Then build it.

Don't do what past cycles did. Find something NEW:
- A technique from a paper you can implement
- A data source nobody's wired in yet
- A risk metric that's missing (CVaR? Omega ratio? Tail dependence?)
- A smarter way to combine signals
- A feature the frontend is missing
- Something from the reference repos at C:\Users\mrthn\reference-codes\

## Current engine state (randomized tickers each cycle)

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
    "functions": 673
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
  "cycle": 37,
  "timestamp": "2026-04-12T12:00:03.521755",
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
    "confidence": 17,
    "color": "green",
    "composite_score": 0.178,
    "reasons": [
      "Low crash risk (1% 3M)",
      "Bullish market regime",
      "External consensus: BULLISH"
    ],
    "components": {
      "crash_prob": 0.079,
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
    "NVDA": {
      "action": "Strong Buy",
      "composite_score": 0.459,
      "confidence": 45
    },
    "COST": {
      "action": "Hold",
      "composite_score": 0.147,
      "confidence": 14
    },
    "MSFT": {
      "action": "Buy",
      "composite_score": 0.289,
      "confidence": 28
    },
    "UNH": {
      "action": "Buy",
      "composite_score": 0.309,
      "confidence": 30
    },
    "META": {
      "action": "Buy",
      "composite_score": 0.357,
      "confidence": 35
    },
    "BRK-B": {
      "action": "Hold",
      "composite_score": 0.07,
      "confidence": 6
    },
    "AFRM": {
      "action": "Buy",
      "composite_score": 0.429,
      "confidence": 42
    },
    "NEM": {
      "action": "Buy",
      "composite_score": 0.333,
      "confidence": 33
    },
    "DASH": {
      "action": "Buy",
      "composite_score": 0.337,
      "confidence": 33
    },
    "TDOC": {
      "action": "Buy",
      "composite_score": 0.296,
      "confidence": 29
    },
    "ARM": {
      "action": "Buy",
      "composite_score": 0.403,
      "confidence": 40
    },
    "ELF": {
      "action": "Strong Buy",
      "composite_score": 0.462,
      "confidence": 46
    }
  },
  "diversity": {
    "action_distribution": {
      "Strong Buy": 2,
      "Hold": 2,
      "Buy": 8
    },
    "n_unique_actions": 3,
    "score_spread": 0.392,
    "score_std": 0.113,
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
  "final_mean": 9588.075259500862,
  "final_median": 8729.562010681497,
  "final_p05": 3812.7589382255146,
  "final_p10": 4659.684076388647,
  "final_p25": 6307.845615720307,
  "final_p75": 11862.56706078455,
  "final_p90": 15641.303349276985,
  "final_p95": 18457.723602470636,
  "total_return_pct": 40.651749803848205,
  "annual_return_pct": 7.06044097724865,
  "crash_prob_1y": 24.73,
  "crash_prob_5y": 81.63,
  "cvar_95_pct": -54.56538294520148,
  "max_dd_pct": -30.72466709547998,
  "max_drawdown_pct": 30.72466709547998
}
```

### stock_analysis
```json
{
  "NVDA": {
    "ticker": "NVDA",
    "current_price": 188.6300048828125,
    "mc_median_5y": 75.82268095225658,
    "mc_p10_5y": -57.9515144946251,
    "mc_p90_5y": 300.0,
    "garch_vol": 39.932659138534966,
    "garch_nu": 8.0,
    "crash_prob_3m": 1.0,
    "signal_action": "Strong Buy",
    "signal_score": 0.459,
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
  "COST": {
    "ticker": "COST",
    "current_price": 998.469970703125,
    "mc_median_5y": 68.87194483471623,
    "mc_p10_5y": -11.817630425195635,
    "mc_p90_5y": 223.2915952893343,
    "garch_vol": 18.82890431724533,
    "garch_nu": 8.0,
    "crash_prob_3m": 1.0,
    "signal_action": "Hold",
    "signal_score": 0.147,
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
  "MSFT": {
    "ticker": "MSFT",
    "current_price": 370.8699951171875,
    "mc_median_5y": 76.64520704176543,
    "mc_p10_5y": -11.398060138499455,
    "mc_p90_5y": 240.62616337334083,
    "garch_vol": 30.147804240143213,
    "garch_nu": 8.0,
    "crash_prob_3m": 1.0,
    "signal_action": "Buy",
    "signal_score": 0.289,
    "beta": 1.107,
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
  "UNH": {
    "ticker": "UNH",
    "current_price": 304.3299865722656,
    "mc_median_5y": 15.601889680860626,
    "mc_p10_5y": -50.363247550049714,
    "mc_p90_5y": 159.02958807318396,
    "garch_vol": 37.39070841632694,
    "garch_nu": 8.0,
    "crash_prob_3m": 1.0,
    "signal_action": "Buy",
    "signal_score": 0.309,
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
      "p05_pr
... [truncated]
```

## Recent cycles (don't repeat these — do something different)

Cycle 34: 1. Created _compute_market_signal_for_lab() — a 95-line function that fetches real market data via DataFetcher and wires (improved)
Cycle 35: 1. Moved crash probability clip bounds from hardcoded values to config['ml']['calibration']. 2. Added degenerate calibra (improved)

## Unexplored areas

- backend/services/shap_explainer.py
- backend/services/return_model.py
- engine/training/train_crash_model.py
- engine/validation/walk_forward.py
- engine/validation/metrics.py
- frontend/src/app/
- frontend/src/components/
- frontend/src/lib/

## Testing — be smart, not exhaustive

There are 675+ tests. DON'T run them all (takes 9 min).
Run only what's relevant: `python -m pytest backend/tests/test_<service>.py -v --tb=short`
You decide what to test. You can also write new tests.

## When done

1. Experiment report: lab/experiments/cycle_037/experiment_report.json
   (what you noticed, what you built, honest assessment, self-critique, next steps)

2. Commit: `git add -A && git commit -m "Lab cycle_037: <summary>"`

Think like a quant researcher with unlimited access. What would YOU build?
