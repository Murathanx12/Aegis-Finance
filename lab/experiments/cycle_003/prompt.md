# Aegis Finance - Autonomous R&D Lab - Cycle 3
Time: 2026-04-11T21:13:45.209933

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
   `git add -A && git commit -m "Lab cycle_003: <summary>"`

---

## PRE-EXISTING TEST FAILURES

These tests were already failing BEFORE your cycle started.
Fixing any of these is a valid and valuable improvement.

```
All tests passing (no pre-existing failures).
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
  `python lab/data_generator.py --output-dir lab/experiments/cycle_003/data_test --cycle 3`

### Step 4: Write the experiment report

CRITICAL - You MUST create this file before finishing:
lab/experiments/cycle_003/experiment_report.json

Contents:
{
    "cycle": 3,
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
git commit -m "Lab cycle_003: <summary>"

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
      "mc_median_return_pct": -1.57,
      "direction_correct": false,
      "absolute_error_pct": 16.28
    },
    {
      "test_start": "2025-07-11",
      "horizon_days": 63,
      "actual_return_pct": 7.59,
      "mc_median_return_pct": 3.6,
      "direction_correct": true,
      "absolute_error_pct": 3.99
    },
    {
      "test_start": "2025-10-09",
      "horizon_days": 63,
      "actual_return_pct": 3.43,
      "mc_median_return_pct": 4.36,
      "direction_correct": true,
      "absolute_error_pct": 0.93
    }
  ],
  "summary": {
    "n_tests": 3,
    "direction_accuracy_pct": 66.7,
    "mean_absolute_error_pct": 7.07
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
    "risk_profile": "growth",
    "total_value_approx": 479070.81,
    "n_holdings": 6,
    "holdings": [
      {
        "ticker": "MSFT",
        "name": "Microsoft",
        "sector": "Technology",
        "shares": 2485,
        "weight": 0.2746,
        "cost_basis": 52.92,
        "purchase_date": "2025-07-01"
      },
      {
        "ticker": "CAT",
        "name": "Caterpillar",
        "sector": "Industrials",
        "shares": 774,
        "weight": 0.0828,
        "cost_basis": 51.23,
        "purchase_date": "2024-09-04"
      },
      {
        "ticker": "BA",
        "name": "Boeing",
        "sector": "Industrials",
        "shares": 155,
        "weight": 0.0442,
        "cost_basis": 136.21,
        "purchase_date": "2025-09-12"
      },
      {
        "ticker": "AAPL",
        "name": "Apple",
        "sector": "Technology",
        "shares": 1124,
        "weight": 0.1495,
        "cost_basis": 63.67,
        "purchase_date": "2025-06-04"
      },
      {
        "ticker": "JNJ",
        "name": "J&J",
        "sector": "Healthcare",
        "shares": 1235,
        "weight": 0.151,
        "cost_basis": 58.52,
        "purchase_date": "2024-08-16"
      },
      {
        "ticker": "XOM",
        "name": "ExxonMobil",
        "sector": "Energy",
        "shares": 1400,
        "weight": 0.298,
        "cost_basis": 101.92,
        "purchase_date": "2024-04-14"
      }
    ]
  },
  {
    "id": "portfolio_2",
    "risk_profile": "moderate",
    "total_value_approx": 398315.42,
    "n_holdings": 6,
    "holdings": [
      {
        "ticker": "JNJ",
        "name": "J&J",
        "sector": "Healthcare",
        "shares": 272,
        "weight": 0.0411,
        "cost_basis": 60.2,
        "purchase_date": "2025-09-27"
      },
      {
        "ticker": "UNH",
        "name": "UnitedHealth",
        "sector": "Healthcare",
        "shares": 102,
        "weight": 0.0368,
        "cost_basis": 143.3,
        "purchase_date": "2025-05-29"
      },
      {
        "ticker": "WMT",
        "name": "Walmart",
        "sector": "Consumer Staples",
        "shares": 846,
        "weight": 0.133,
        "cost_basis": 62.58,
        "purchase_date": "2024-09-22"
      },
      {
        "ticker": "TSLA",
        "name": "Tesla",
        "sector": "Consumer Discretionary",
        "shares": 1275,
        "weight": 0.1676,
        "cost_basis": 52.32,
        "purchase_date": "2024-07-03"
      },
      {
        "ticker": "BAC",
        "name": "Bank of America",
        "sector": "Financials",
        "shares": 2028,
        "weight": 0.5449,
        "cost_basis": 107.01,
        "purchase_date": "2025-05-03"
      },
      {
        "ticker": "CAT",
        "name": "Caterpillar",
        "sector": "Industrials",
        "shares": 250,
        "weight": 0.0765,
        "cost_basis": 121.5,
        "purchase_date": "2024-10-15"
      }
    ]
  },
  {
    "id": "portfolio_3",
    "risk_profile": "aggressive",
    "total_value_approx": 152752.9,
    "n_holdings": 7,
    "holdings": [
      {
        "ticker": "META",
        "name": "Meta",
        "sector": "Technology",
        "shares": 22,
        "weight": 0.0084,
        "cost_basis": 57.28,
        "purchase_date": "2024-07-13"
      },
      {
        "ticker": "UNH",
        "name": "UnitedHealth",
        "sector": "Healthcare",
        "shares": 717,
        "weight": 0.5017,
        "cost_basis": 106.88,
        "purchase_date": "2025-08-31"
      },
      {
        "ticker": "BA",
        "name": "Boeing",
        "sector": "Industrials",
        "shares": 145,
        "weight": 0.0826,
        "cost_basis": 86.43,
        "purchase_date": "2024-09-09"
      },
      {
        "ticker": "JPM",
        "name": "JPMorgan",
        "sector": "Financials",
        "shares": 132,
        "weight": 0.0886,
        "cost_basis": 102.4,
        "purchase_date": "2025-06-01"
      },
      {
        "ticker": "TSLA",
        "name": "Tesla
... [truncated]
```

### run_metadata
```json
{
  "cycle": 3,
  "timestamp": "2026-04-11T21:13:20.875784",
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
      "AAPL": 19.86,
      "NVDA": 25.61,
      "XOM": 22.96,
      "JPM": 11.26,
      "TSLA": 63.33,
      "JNJ": 8.46,
      "AMZN": 53.91,
      "BA": 56.63
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
    "median_price": 7458.6,
    "mean_price": 7560.1,
    "p5": 5676.82,
    "p95": 9798.47,
    "prob_positive": 70.0,
    "prob_20pct_crash": 2.8,
    "expected_annual_return_pct": 10.9
  },
  "3y": {
    "median_price": 8874.02,
    "mean_price": 9245.71,
    "p5": 5449.6,
    "p95": 14301.82,
    "prob_positive": 81.3,
    "prob_20pct_crash": 5.0,
    "expected_annual_return_pct": 10.69
  },
  "5y": {
    "median_price": 10399.75,
    "mean_price": 11135.04,
    "p5": 5601.54,
    "p95": 19299.13,
    "prob_positive": 87.2,
    "prob_20pct_crash": 4.3,
    "expected_annual_return_pct": 10.31
  },
  "quality_check": {
    "theoretical_1y_drift": 0.10072,
    "actual_1y_mean_log_return": 0.08493,
    "drift_error_pct": 15.68,
    "variance_ratio": 0.99
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
      "median_price": 310.35,
      "mean_price": 318.64,
      "p5": 197.87,
      "p25": 256.55,
      "p75": 365.98,
      "p95": 483.38,
      "prob_above_current": 72.6,
      "prob_20pct_drawdown": 8.2,
      "expected_return_pct": 22.33,
      "median_return_pct": 19.14
    },
    "mc_quality": {
      "drift_error_pct": 19.86,
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
      "median_price": 244.6,
      "mean_price": 281.64,
      "p5": 111.03,
      "p25": 177.41,
      "p75": 356.01,
      "p95": 560.4,
      "prob_above_current": 70.8,
      "prob_20pct_drawdown": 16.2,
      "expected_return_pct": 49.31,
      "median_return_pct": 29.67
    },
    "mc_quality": {
      "drift_error_pct": 25.61,
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
      "median_price": 170.49,
      "mean_price": 175.44,
      "p5": 118.79,
      "p25": 145.85,
      "p75": 199.37,
      "p95": 246.18,
      "prob_above_current": 68.7,
      "prob_20pct_drawdown": 6.6,
      "expected_return_pct": 15.03,
      "median_return_pct": 11.79
    },
    "mc_quality": {
      "drift_error_pct": 22.96,
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
      "annuali
... [truncated]
```

---

## PAST EXPERIMENTS (your accumulated knowledge)

### Cycle 1
What I tried: 1. The crash model's LogisticRegression objects loaded from a sklearn 1.8.0 pickle are missing the 'multi_class' attribute that sklearn 1.4.0's predict_proba requires. Patching this attribute on load should fix the test. 2. Normalizing Student-t innovations to unit variance will remove the excess diffusion variance bias in the backend's MC paths, preserving fat tails (kurtosis) while correcting the drift.
Method: Unknown
Result: IMPROVED
Before: {"test_monotonic_horizons": "FAILED (AttributeError: multi_class)", "total_fast_tests_passing": "59/60", "student_t_variance": "1.333 (df=8, unscaled)"}
After: {"test_monotonic_horizons": "PASSED", "total_fast_tests_passing": "60/60", "student_t_variance": "1.0 (normalized to unit variance)"}
What I learned: The crash model test fix is definitive — the root cause was a sklearn version incompatibility, and the patch is forward/backward compatible. The Student-t normalization is mathematically sound: raw Student-t(8) has Var=8/6=1.333, which inflates the diffusion term by ~33%, adding ~0.5*sigma^2*0.333 excess annual drift to price paths. This is most impactful for high-vol stocks (TSLA, BA at ~40-50% vol: ~3-4% annual excess). The data_generator's drift error metrics are NOT affected by this fix since it runs its own separate GBM. Note: the data_generator's drift_error formula itself has a measurement bias (compares mu*T against (mu-0.5*sigma^2)*T), inflating reported errors — but this cannot be fixed per lab/ read-only constraint.
Next steps: 1. Consider adding a variance-drag Ito correction (-0.5*sigma_t^2*dt) to the MC drift when base_drift is intended as the TARGET ARITHMETIC return rather than log return — the current code's comment says it's log return but run_monte_carlo passes log(1+arithmetic_return). 2. Investigate why cross-asset correlations show 0 observations (n_observations=0). 3. Look into the block bootstrap code path — it's enabled in config but never activated since historical_residuals is never passed to simulate_paths from run_monte_carlo.
Files changed: backend/services/crash_model.py, backend/services/monte_carlo.py

### Cycle 2
What I tried: The scenarios endpoint produces inaccurate results because crash frequency is inflated 59% above the calibrated rate, simulation count is 3.3x too low, and tail estimation defaults to a fixed Student-t(8) instead of GARCH-estimated nu. The antithetic variate issue means crash probability estimates from antithetic paths have higher variance than necessary.
Method: Unknown
Result: IMPROVED
Before: {"scenarios_crash_freq": "0.111 (hardcoded 1/9)", "scenarios_n_sims": "3000 (hardcoded)", "scenarios_risk_score": "0.0 (hardcoded)", "scenarios_garch_nu": "null (not passed, defaults to config t_df=8)", "antithetic_jump_draws": "shared (same Z_jump for both paths)", "fast_tests_passing": "60/60"}
After: {"scenarios_crash_freq": "0.07 (from config)", "scenarios_n_sims": "10000 (from config)", "scenarios_risk_score": "computed from build_risk_score()", "scenarios_garch_nu": "estimated from fit_garch()", "antithetic_jump_draws": "antithetic (1-U for antithetic paths)", "fast_tests_passing": "60/60"}
What I learned: Both fixes are correctness improvements to the production backend. The _compute_scenarios fix is the higher-impact change: the 59% crash frequency overestimate (0.111 vs 0.07) would cause scenario projections to be too pessimistic, with more frequent crash jumps dragging down all scenario median returns. Using the proper n_sims (10000 vs 3000) also improves convergence of percentile estimates. The antithetic variate fix is a statistical quality improvement — it doesn't change expected values (no bias) but reduces variance of crash probability estimates when antithetic mode is enabled. The cross-asset correlation bug (all NaN) was diagnosed as a timezone mismatch in yfinance individual-ticker fetches (data_generator uses per-ticker .history() while backend uses batch yf.download which handles alignment). This cannot be fixed from the backend since it's in the read-only data_generator code.
Next steps: 1. The cross-asset correlation NaN issue persists in the data_generator output — would need a data_generator update to normalize timezone-aware indexes to dates before combining. 2. The data_generator's mc_drift_errors have a known measurement bias (compares mu*T vs actual, should be (mu-0.5*sigma^2)*T) — also requires data_generator fix. 3. Consider wiring block bootstrap into run_monte_carlo by computing historical_residuals from fetched price data. 4. The stock_analyzer calls simulate_paths without GARCH vol, HMM, or ML predictions — enriching this would improve per-stock MC quality.
Files changed: backend/routers/simulation.py, backend/services/monte_carlo.py

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
