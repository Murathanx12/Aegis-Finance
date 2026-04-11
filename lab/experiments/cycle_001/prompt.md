# Aegis Finance - Autonomous R&D Lab - Cycle 1
Time: 2026-04-11T20:42:16.530503

---

## WHO YOU ARE

You are an autonomous quant engineer with full access to the Aegis Finance codebase.
Your job: make the PRODUCTION ENGINE better. Measurably better.

You are NOT following a checklist. You are a researcher who:
1. Looks at real engine output (below)
2. Reads the actual source code (use bash and file tools)
3. Finds problems, bugs, inefficiencies in the BACKEND or FRONTEND
4. Designs an experiment to fix something
5. Implements it
6. Measures if it helped
7. Logs everything honestly

You have FULL creative control. You decide what to work on.

---

## CRITICAL RULES

1. **ONLY modify files in `backend/`, `frontend/`, or `engine/`.**
   - NEVER modify files in `lab/` (data_generator.py, build_prompt.py, compare_results.py, run_lab.sh).
   - The lab tools are READ-ONLY measurement instruments. If the data looks wrong, the fix belongs in the backend service code, not the measurement tool.

2. **Do NOT break existing tests.**
   - Run: `python -m pytest backend/tests/ -v -m "not slow" --tb=short`
   - If your changes cause NEW test failures, they will be auto-reverted.
   - You MAY fix pre-existing test failures (see below) — that counts as an improvement.

3. **Do NOT delete tests or weaken assertions.**

4. **Put parameters in `backend/config.py`**, not hardcoded in services.

5. **Commit your changes** at the end:
   `git add -A && git commit -m "Lab cycle_001: <summary>"`

---

## PRE-EXISTING TEST FAILURES

These tests were already failing BEFORE your cycle started.
Fixing any of these is a valid and valuable improvement.

```
FAILED backend/tests/test_crash_calibration.py::TestCrashCalibration::test_monotonic_horizons
```

---

## WHAT TO LOOK FOR

Priority order:
1. **Fix failing tests** — broken tests are the highest-value target
2. **Accuracy bugs** — wrong formulas, missing corrections, bad defaults in backend services
3. **Missing connections** — services that exist but aren't wired into endpoints
4. **Signal quality** — buy/sell signals that are always the same, crash probs that don't differentiate
5. **Statistical issues** — wrong distributions, look-ahead bias, overfitting
6. **Code quality** — hardcoded values that belong in config.py, missing edge cases

---

## WHAT TO DO

### Step 1: Understand the current state
- Read the engine output data below carefully
- Read past experiment logs below
- Explore the BACKEND codebase yourself:
  - `cat backend/services/monte_carlo.py | head -100`
  - `cat backend/config.py`
  - `cat backend/services/signal_engine.py`
  - `python -m pytest backend/tests/ -v -m "not slow" --tb=short`

### Step 2: Find something worth improving
Focus on backend/services/, backend/routers/, backend/config.py, or engine/.
Do NOT modify lab/ files.

### Step 3: Implement and test
- Make your changes to backend/ or frontend/ or engine/ files
- Run: `python -m pytest backend/tests/ -v -m "not slow" --tb=short`
- If tests break due to your changes, fix them or revert
- Re-run the data generator to see if output improved:
  `python lab/data_generator.py --output-dir lab/experiments/cycle_001/data_test --cycle 1`

### Step 4: Write the experiment report

CRITICAL - You MUST create this file before finishing:
lab/experiments/cycle_001/experiment_report.json

Contents:
{
    "cycle": 1,
    "timestamp": "<now>",
    "what_i_noticed": "<what caught your attention in the data>",
    "hypothesis": "<what you think the problem is>",
    "what_i_did": "<what code you changed and why>",
    "files_modified": ["<list every file you touched — should be in backend/ or engine/>"],
    "results": {
        "before": {"<metric>": "<value>"},
        "after": {"<metric>": "<value>"},
        "improved": true or false
    },
    "tests_fixed": ["<list any previously-failing tests you fixed>"],
    "analysis": "<honest assessment - did it work?>",
    "next_steps": "<what should the next cycle focus on>",
    "confidence": "<low/medium/high>",
    "should_keep": true or false
}

Failed experiments are fine. Log them honestly so the next cycle learns.

### Step 5: Commit
git add -A
git commit -m "Lab cycle_001: <summary>"

---

## ENGINE OUTPUT (fresh data from this cycle)

### backtest_accuracy
```json
{
  "tests": [
    {
      "test_start": "2025-04-09",
      "horizon_days": 63,
      "actual_return_pct": 14.71,
      "mc_median_return_pct": -1.31,
      "direction_correct": false,
      "absolute_error_pct": 16.02
    },
    {
      "test_start": "2025-07-11",
      "horizon_days": 63,
      "actual_return_pct": 7.59,
      "mc_median_return_pct": 3.44,
      "direction_correct": true,
      "absolute_error_pct": 4.16
    },
    {
      "test_start": "2025-10-09",
      "horizon_days": 63,
      "actual_return_pct": 3.43,
      "mc_median_return_pct": 4.32,
      "direction_correct": true,
      "absolute_error_pct": 0.89
    }
  ],
  "summary": {
    "n_tests": 3,
    "direction_accuracy_pct": 66.7,
    "mean_absolute_error_pct": 7.02
  }
}
```

### cross_asset_correlations
```json
{
  "matrix": {
    "SP500": {
      "SP500": NaN,
      "VIX": NaN,
      "10Y_Yield": NaN,
      "Gold": NaN,
      "Oil": NaN,
      "USD": NaN
    },
    "VIX": {
      "SP500": NaN,
      "VIX": NaN,
      "10Y_Yield": NaN,
      "Gold": NaN,
      "Oil": NaN,
      "USD": NaN
    },
    "10Y_Yield": {
      "SP500": NaN,
      "VIX": NaN,
      "10Y_Yield": NaN,
      "Gold": NaN,
      "Oil": NaN,
      "USD": NaN
    },
    "Gold": {
      "SP500": NaN,
      "VIX": NaN,
      "10Y_Yield": NaN,
      "Gold": NaN,
      "Oil": NaN,
      "USD": NaN
    },
    "Oil": {
      "SP500": NaN,
      "VIX": NaN,
      "10Y_Yield": NaN,
      "Gold": NaN,
      "Oil": NaN,
      "USD": NaN
    },
    "USD": {
      "SP500": NaN,
      "VIX": NaN,
      "10Y_Yield": NaN,
      "Gold": NaN,
      "Oil": NaN,
      "USD": NaN
    }
  },
  "period": "1Y daily returns",
  "n_observations": 0
}
```

### market_snapshot
```json
{
  "sp500": {
    "symbol": "^GSPC",
    "price": 6816.89,
    "change_1d_pct": -0.114,
    "volatility_20d_annualized": 19.95
  },
  "nasdaq": {
    "symbol": "^IXIC",
    "price": 22902.89,
    "change_1d_pct": 0.353,
    "volatility_20d_annualized": 25.33
  },
  "dow": {
    "symbol": "^DJI",
    "price": 47916.57,
    "change_1d_pct": -0.559,
    "volatility_20d_annualized": 19.01
  },
  "vix": {
    "symbol": "^VIX",
    "price": 19.23,
    "change_1d_pct": -1.334,
    "volatility_20d_annualized": 143.29
  },
  "treasury_10y": {
    "symbol": "^TNX",
    "price": 4.32,
    "change_1d_pct": 0.559,
    "volatility_20d_annualized": 19.99
  },
  "gold": {
    "symbol": "GC=F",
    "price": 4761.9,
    "change_1d_pct": -0.632,
    "volatility_20d_annualized": 38.44
  },
  "oil": {
    "symbol": "CL=F",
    "price": 96.57,
    "change_1d_pct": -1.328,
    "volatility_20d_annualized": 97.35
  },
  "usd_index": {
    "symbol": "DX-Y.NYB",
    "price": 98.65,
    "change_1d_pct": -0.172,
    "volatility_20d_annualized": 7.4
  }
}
```

### random_portfolios
```json
[
  {
    "id": "portfolio_1",
    "risk_profile": "conservative",
    "total_value_approx": 473299.0,
    "n_holdings": 3,
    "holdings": [
      {
        "ticker": "BA",
        "name": "Boeing",
        "sector": "Industrials",
        "shares": 3816,
        "weight": 0.8754,
        "cost_basis": 108.56,
        "purchase_date": "2026-02-01"
      },
      {
        "ticker": "NVDA",
        "name": "NVIDIA",
        "sector": "Technology",
        "shares": 73,
        "weight": 0.0221,
        "cost_basis": 142.99,
        "purchase_date": "2026-01-03"
      },
      {
        "ticker": "AMZN",
        "name": "Amazon",
        "sector": "Technology",
        "shares": 416,
        "weight": 0.1026,
        "cost_basis": 116.45,
        "purchase_date": "2024-11-20"
      }
    ]
  },
  {
    "id": "portfolio_2",
    "risk_profile": "conservative",
    "total_value_approx": 131084.73,
    "n_holdings": 3,
    "holdings": [
      {
        "ticker": "CAT",
        "name": "Caterpillar",
        "sector": "Industrials",
        "shares": 140,
        "weight": 0.0944,
        "cost_basis": 87.97,
        "purchase_date": "2024-11-25"
      },
      {
        "ticker": "GOOGL",
        "name": "Alphabet",
        "sector": "Technology",
        "shares": 994,
        "weight": 0.845,
        "cost_basis": 111.4,
        "purchase_date": "2024-10-01"
      },
      {
        "ticker": "UNH",
        "name": "UnitedHealth",
        "sector": "Healthcare",
        "shares": 86,
        "weight": 0.0606,
        "cost_basis": 92.04,
        "purchase_date": "2024-12-12"
      }
    ]
  },
  {
    "id": "portfolio_3",
    "risk_profile": "conservative",
    "total_value_approx": 145951.96,
    "n_holdings": 5,
    "holdings": [
      {
        "ticker": "TSLA",
        "name": "Tesla",
        "sector": "Consumer Discretionary",
        "shares": 164,
        "weight": 0.1547,
        "cost_basis": 137.37,
        "purchase_date": "2025-07-25"
      },
      {
        "ticker": "BA",
        "name": "Boeing",
        "sector": "Industrials",
        "shares": 968,
        "weight": 0.6153,
        "cost_basis": 92.73,
        "purchase_date": "2026-02-22"
      },
      {
        "ticker": "NVDA",
        "name": "NVIDIA",
        "sector": "Technology",
        "shares": 1,
        "weight": 0.0008,
        "cost_basis": 59.54,
        "purchase_date": "2024-08-11"
      },
      {
        "ticker": "XOM",
        "name": "ExxonMobil",
        "sector": "Energy",
        "shares": 32,
        "weight": 0.0245,
        "cost_basis": 110.93,
        "purchase_date": "2025-11-02"
      },
      {
        "ticker": "META",
        "name": "Meta",
        "sector": "Technology",
        "shares": 503,
        "weight": 0.2047,
        "cost_basis": 59.31,
        "purchase_date": "2024-10-18"
      }
    ]
  },
  {
    "id": "portfolio_4",
    "risk_profile": "aggressive",
    "total_value_approx": 210190.75,
    "n_holdings": 5,
    "holdings": [
      {
        "ticker": "WMT",
        "name": "Walmart",
        "sector": "Consumer Staples",
        "shares": 389,
        "weight": 0.1172,
        "cost_basis": 63.27,
        "purchase_date": "2026-03-09"
      },
      {
        "ticker": "BAC",
        "name": "Bank of America",
        "sector": "Financials",
        "shares": 152,
        "weight": 0.0949,
        "cost_basis": 130.71,
        "purchase_date": "2024-06-17"
      },
      {
        "ticker": "AAPL",
        "name": "Apple",
        "sector": "Technology",
        "shares": 1057,
        "weight": 0.6394,
        "cost_basis": 127.07,
        "purchase_date": "2025-07-25"
      },
      {
        "ticker": "JNJ",
        "name": "J&J",
        "sector": "Healthcare",
        "shares": 20,
        "weight": 0.0086,
        "cost_basis": 88.73,
        "purchase_date": "2025-09-04"
      },
      {
        "ticker": "XOM",
        "name": "ExxonMobil",
        "sector": "Energy",
        "shares": 210,
        
... [truncated]
```

### run_metadata
```json
{
  "cycle": 1,
  "timestamp": "2026-04-11T20:41:50.869919",
  "data_sources": [
    "market_snapshot",
    "stock_analysis",
    "sp500_monte_carlo",
    "random_portfolios",
    "cross_asset_correlations",
    "backtest_accuracy"
  ],
  "errors": [],
  "engine_services_available": [
    "crash_model",
    "regime_detector",
    "risk_scorer",
    "signal_engine"
  ],
  "quality_metrics": {
    "mc_drift_errors": {
      "AAPL": 16.15,
      "NVDA": 33.6,
      "XOM": 10.96,
      "JPM": 18.02,
      "TSLA": 57.64,
      "JNJ": 6.45,
      "AMZN": 30.68,
      "BA": 55.31
    },
    "data_completeness": 6,
    "errors_count": 0,
    "engine_services_active": 4
  }
}
```

### sp500_monte_carlo
```json
{
  "start_price": 6816.89,
  "1y": {
    "median_price": 7420.17,
    "mean_price": 7535.06,
    "p5": 5642.62,
    "p95": 9794.23,
    "prob_positive": 69.3,
    "prob_20pct_crash": 3.3,
    "expected_annual_return_pct": 10.54
  },
  "3y": {
    "median_price": 8808.93,
    "mean_price": 9234.92,
    "p5": 5522.05,
    "p95": 14410.75,
    "prob_positive": 80.9,
    "prob_20pct_crash": 4.6,
    "expected_annual_return_pct": 10.65
  },
  "5y": {
    "median_price": 10532.4,
    "mean_price": 11281.08,
    "p5": 5652.95,
    "p95": 19469.64,
    "prob_positive": 87.8,
    "prob_20pct_crash": 4.2,
    "expected_annual_return_pct": 10.6
  },
  "quality_check": {
    "theoretical_1y_drift": 0.10072,
    "actual_1y_mean_log_return": 0.08182,
    "drift_error_pct": 18.77,
    "variance_ratio": 0.949
  }
}
```

### stock_analysis
```json
{
  "AAPL": {
    "ticker": "AAPL",
    "sector": "Technology",
    "current_price": 260.48,
    "market_cap_b": 3828.5,
    "pe_ratio": 33.013943,
    "forward_pe": 27.928572,
    "returns": {
      "1m_pct": -0.13,
      "3m_pct": 0.52,
      "6m_pct": 2.73,
      "1y_pct": 31.56,
      "annualized_pct": 27.7
    },
    "risk": {
      "annual_volatility_pct": 28.31,
      "sharpe_ratio": 0.978,
      "max_drawdown_pct": -33.36,
      "current_drawdown_pct": -8.9
    },
    "analyst_targets": {
      "mean": 296.33,
      "low": 205.0,
      "high": 350.0,
      "upside_to_mean_pct": 13.76
    },
    "monte_carlo": {
      "n_simulations": 1000,
      "horizon_days": 252,
      "start_price": 260.48,
      "median_price": 312.97,
      "mean_price": 322.75,
      "p5": 190.67,
      "p25": 256.08,
      "p75": 375.15,
      "p95": 499.42,
      "prob_above_current": 73.3,
      "prob_20pct_drawdown": 9.6,
      "expected_return_pct": 23.91,
      "median_return_pct": 20.15
    },
    "mc_quality": {
      "drift_error_pct": 16.15,
      "drift_accurate": false
    },
    "statistics": {
      "daily_mean_return": 0.08131,
      "daily_volatility": 1.7706,
      "skewness": 0.913,
      "kurtosis": 13.062
    }
  },
  "NVDA": {
    "ticker": "NVDA",
    "sector": "Technology",
    "current_price": 188.63,
    "market_cap_b": 4584.7,
    "pe_ratio": 38.49592,
    "forward_pe": 16.968699,
    "returns": {
      "1m_pct": 1.4,
      "3m_pct": 2.04,
      "6m_pct": -2.04,
      "1y_pct": 65.03,
      "annualized_pct": 63.47
    },
    "risk": {
      "annual_volatility_pct": 49.38,
      "sharpe_ratio": 1.285,
      "max_drawdown_pct": -36.88,
      "current_drawdown_pct": -8.88
    },
    "analyst_targets": {
      "mean": 268.22,
      "low": 140.0,
      "high": 380.0,
      "upside_to_mean_pct": 42.19
    },
    "monte_carlo": {
      "n_simulations": 1000,
      "horizon_days": 252,
      "start_price": 188.63,
      "median_price": 238.06,
      "mean_price": 273.67,
      "p5": 109.26,
      "p25": 173.69,
      "p75": 335.33,
      "p95": 556.7,
      "prob_above_current": 69.2,
      "prob_20pct_drawdown": 17.5,
      "expected_return_pct": 45.08,
      "median_return_pct": 26.2
    },
    "mc_quality": {
      "drift_error_pct": 33.6,
      "drift_accurate": false
    },
    "statistics": {
      "daily_mean_return": 0.14674,
      "daily_volatility": 3.1153,
      "skewness": -0.008,
      "kurtosis": 4.704
    }
  },
  "XOM": {
    "ticker": "XOM",
    "sector": "Energy",
    "current_price": 152.51,
    "market_cap_b": 633.9,
    "pe_ratio": 22.762686,
    "forward_pe": 15.488045,
    "returns": {
      "1m_pct": 0.61,
      "3m_pct": 23.21,
      "6m_pct": 37.16,
      "1y_pct": 49.1,
      "annualized_pct": 19.04
    },
    "risk": {
      "annual_volatility_pct": 23.27,
      "sharpe_ratio": 0.818,
      "max_drawdown_pct": -18.92,
      "current_drawdown_pct": -11.06
    },
    "analyst_targets": {
      "mean": 162.71,
      "low": 123.0,
      "high": 195.0,
      "upside_to_mean_pct": 6.69
    },
    "monte_carlo": {
      "n_simulations": 1000,
      "horizon_days": 252,
      "start_price": 152.51,
      "median_price": 173.13,
      "mean_price": 178.6,
      "p5": 121.55,
      "p25": 148.69,
      "p75": 202.85,
      "p95": 254.41,
      "prob_above_current": 71.0,
      "prob_20pct_drawdown": 5.3,
      "expected_return_pct": 17.1,
      "median_return_pct": 13.52
    },
    "mc_quality": {
      "drift_error_pct": 10.96,
      "drift_accurate": false
    },
    "statistics": {
      "daily_mean_return": 0.05838,
      "daily_volatility": 1.4712,
      "skewness": -0.526,
      "kurtosis": 1.906
    }
  },
  "JPM": {
    "ticker": "JPM",
    "sector": "Financial Services",
    "current_price": 309.87,
    "market_cap_b": 835.7,
    "pe_ratio": 15.478022,
    "forward_pe": 13.260674,
    "returns": {
      "1m_pct": 8.32,
      "3m_pct": -5.39,
      "6m_pct": 2.4,
      "1y_pct": 34.8,
      "annualized
... [truncated]
```

---

## PAST EXPERIMENTS (your accumulated knowledge)

This is the FIRST cycle. No past experiments yet.

---

## CODEBASE LAYOUT

Key directories (explore yourself, dont just trust this list):

backend/
  services/       # Core engine — THIS IS WHERE IMPROVEMENTS GO
  routers/        # API endpoints
  config.py       # All thresholds, weights, parameters
  tests/          # Test suite — fix failures here
engine/
  training/       # ML model training
  validation/     # Backtesting
frontend/
  src/app/        # Next.js pages
  src/components/ # React components
  src/lib/        # API client, utilities
lab/              # READ-ONLY — do NOT modify these files
  data_generator.py   # Measurement tool (hands off)
  build_prompt.py     # Prompt builder (hands off)
  compare_results.py  # Comparator (hands off)

---

## GO

Read the data. Explore the backend code. Find something to improve.
Make it better. Run tests. Write the experiment report. Commit.
Remember: only modify backend/, frontend/, or engine/ files.
