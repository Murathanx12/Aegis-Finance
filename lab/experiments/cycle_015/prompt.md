# Aegis Finance - Autonomous R&D Lab - Cycle 15
Time: 2026-04-11T23:16:39.481013

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
   `git add -A && git commit -m "Lab cycle_015: <summary>"`

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
  `python lab/data_generator.py --output-dir lab/experiments/cycle_015/data_test --cycle 15`

### Step 4: Write the experiment report

CRITICAL - You MUST create this file before finishing:
lab/experiments/cycle_015/experiment_report.json

Contents:
{
    "cycle": 15,
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
git commit -m "Lab cycle_015: <summary>"

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
      "mc_median_return_pct": -1.53,
      "direction_correct": false,
      "absolute_error_pct": 16.25
    },
    {
      "test_start": "2025-07-11",
      "horizon_days": 63,
      "actual_return_pct": 7.59,
      "mc_median_return_pct": 3.09,
      "direction_correct": true,
      "absolute_error_pct": 4.5
    },
    {
      "test_start": "2025-10-09",
      "horizon_days": 63,
      "actual_return_pct": 3.43,
      "mc_median_return_pct": 4.22,
      "direction_correct": true,
      "absolute_error_pct": 0.79
    }
  ],
  "summary": {
    "n_tests": 3,
    "direction_accuracy_pct": 66.7,
    "mean_absolute_error_pct": 7.18
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
    "total_value_approx": 473338.28,
    "n_holdings": 3,
    "holdings": [
      {
        "ticker": "AMZN",
        "name": "Amazon",
        "sector": "Technology",
        "shares": 2685,
        "weight": 0.38,
        "cost_basis": 66.97,
        "purchase_date": "2025-06-21"
      },
      {
        "ticker": "BA",
        "name": "Boeing",
        "sector": "Industrials",
        "shares": 2769,
        "weight": 0.6038,
        "cost_basis": 103.21,
        "purchase_date": "2025-07-08"
      },
      {
        "ticker": "JNJ",
        "name": "J&J",
        "sector": "Healthcare",
        "shares": 109,
        "weight": 0.0161,
        "cost_basis": 69.59,
        "purchase_date": "2025-01-13"
      }
    ]
  },
  {
    "id": "portfolio_2",
    "risk_profile": "aggressive",
    "total_value_approx": 337536.35,
    "n_holdings": 3,
    "holdings": [
      {
        "ticker": "TSLA",
        "name": "Tesla",
        "sector": "Consumer Discretionary",
        "shares": 2411,
        "weight": 0.4276,
        "cost_basis": 59.86,
        "purchase_date": "2025-03-26"
      },
      {
        "ticker": "BA",
        "name": "Boeing",
        "sector": "Industrials",
        "shares": 2541,
        "weight": 0.5208,
        "cost_basis": 69.17,
        "purchase_date": "2025-04-18"
      },
      {
        "ticker": "MSFT",
        "name": "Microsoft",
        "sector": "Technology",
        "shares": 285,
        "weight": 0.0516,
        "cost_basis": 61.02,
        "purchase_date": "2025-09-03"
      }
    ]
  },
  {
    "id": "portfolio_3",
    "risk_profile": "aggressive",
    "total_value_approx": 425234.72,
    "n_holdings": 4,
    "holdings": [
      {
        "ticker": "BA",
        "name": "Boeing",
        "sector": "Industrials",
        "shares": 1921,
        "weight": 0.6088,
        "cost_basis": 134.72,
        "purchase_date": "2026-03-01"
      },
      {
        "ticker": "CAT",
        "name": "Caterpillar",
        "sector": "Industrials",
        "shares": 5,
        "weight": 0.0018,
        "cost_basis": 140.54,
        "purchase_date": "2025-01-02"
      },
      {
        "ticker": "JNJ",
        "name": "J&J",
        "sector": "Healthcare",
        "shares": 1053,
        "weight": 0.2955,
        "cost_basis": 119.26,
        "purchase_date": "2024-08-06"
      },
      {
        "ticker": "META",
        "name": "Meta",
        "sector": "Technology",
        "shares": 405,
        "weight": 0.0939,
        "cost_basis": 98.42,
        "purchase_date": "2025-09-05"
      }
    ]
  },
  {
    "id": "portfolio_4",
    "risk_profile": "aggressive",
    "total_value_approx": 473425.37,
    "n_holdings": 6,
    "holdings": [
      {
        "ticker": "JNJ",
        "name": "J&J",
        "sector": "Healthcare",
        "shares": 461,
        "weight": 0.0605,
        "cost_basis": 62.04,
        "purchase_date": "2024-09-23"
      },
      {
        "ticker": "CAT",
        "name": "Caterpillar",
        "sector": "Industrials",
        "shares": 790,
        "weight": 0.1353,
        "cost_basis": 81.03,
        "purchase_date": "2024-12-30"
      },
      {
        "ticker": "BAC",
        "name": "Bank of America",
        "sector": "Financials",
        "shares": 457,
        "weight": 0.1083,
        "cost_basis": 112.01,
        "purchase_date": "2024-04-21"
      },
      {
        "ticker": "UNH",
        "name": "UnitedHealth",
        "sector": "Healthcare",
        "shares": 2047,
        "weight": 0.4239,
        "cost_basis": 98.0,
        "purchase_date": "2025-03-08"
      },
      {
        "ticker": "JPM",
        "name": "JPMorgan",
        "sector": "Financials",
        "shares": 1475,
        "weight": 0.187,
        "cost_basis": 59.99,
        "purchase_date": "2025-10-11"
      },
      {
        "ticker": "XOM",
        "name": "ExxonMobil",
        "sector": "Energy",
        "shares": 275,
        "weight": 0
... [truncated]
```

### run_metadata
```json
{
  "cycle": 15,
  "timestamp": "2026-04-11T23:16:14.190449",
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
      "AAPL": 20.2,
      "NVDA": 37.47,
      "XOM": 17.2,
      "JPM": 16.73,
      "TSLA": 64.28,
      "JNJ": 10.32,
      "AMZN": 36.7,
      "BA": 51.19
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
    "median_price": 7426.99,
    "mean_price": 7534.37,
    "p5": 5638.45,
    "p95": 9752.72,
    "prob_positive": 69.2,
    "prob_20pct_crash": 3.4,
    "expected_annual_return_pct": 10.53
  },
  "3y": {
    "median_price": 8846.17,
    "mean_price": 9195.22,
    "p5": 5490.98,
    "p95": 14134.57,
    "prob_positive": 81.1,
    "prob_20pct_crash": 4.8,
    "expected_annual_return_pct": 10.49
  },
  "5y": {
    "median_price": 10562.27,
    "mean_price": 11341.86,
    "p5": 5663.71,
    "p95": 19655.58,
    "prob_positive": 87.4,
    "prob_20pct_crash": 4.2,
    "expected_annual_return_pct": 10.72
  },
  "quality_check": {
    "theoretical_1y_drift": 0.10072,
    "actual_1y_mean_log_return": 0.08385,
    "drift_error_pct": 16.75,
    "variance_ratio": 1.001
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
      "median_price": 310.76,
      "mean_price": 318.22,
      "p5": 195.69,
      "p25": 255.35,
      "p75": 367.93,
      "p95": 479.22,
      "prob_above_current": 72.8,
      "prob_20pct_drawdown": 7.8,
      "expected_return_pct": 22.17,
      "median_return_pct": 19.3
    },
    "mc_quality": {
      "drift_error_pct": 20.2,
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
      "median_price": 237.61,
      "mean_price": 267.32,
      "p5": 107.48,
      "p25": 169.62,
      "p75": 331.19,
      "p95": 512.83,
      "prob_above_current": 67.9,
      "prob_20pct_drawdown": 17.0,
      "expected_return_pct": 41.71,
      "median_return_pct": 25.97
    },
    "mc_quality": {
      "drift_error_pct": 37.47,
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
      "median_price": 170.28,
      "mean_price": 177.17,
      "p5": 118.08,
      "p25": 146.39,
      "p75": 202.71,
      "p95": 253.1,
      "prob_above_current": 69.6,
      "prob_20pct_drawdown": 7.7,
      "expected_return_pct": 16.17,
      "median_return_pct": 11.65
    },
    "mc_quality": {
      "drift_error_pct": 17.2,
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
      "annualize
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

### Cycle 3
What I tried: Wiring crash probabilities into stock signals will activate 25% of signal weight that was previously dead (crash_prob component was excluded when None). Adding GARCH to stock_analyzer will give more accurate forward-looking volatility and stock-specific tail thickness for Monte Carlo paths.
Method: Unknown
Result: IMPROVED
Before: {"stock_signal_crash_prob_component": "always 0.0 (excluded, weight=0)", "stock_signal_yield_curve": "not passed (None)", "stock_signal_external_consensus": "not passed (None)", "stock_mc_garch_vol": "None (uses historical_sigma fallback)", "stock_mc_garch_nu": "None (uses config t_df=8 fallback)", "stock_mc_garch_persistence": "None (uses default 0.97)", "fast_tests_passing": "60/60", "backtest_mae": 7.07}
After: {"stock_signal_crash_prob_component": "computed from crash model (activates 25% weight)", "stock_signal_yield_curve": "computed from T10Y-T3M spread", "stock_signal_external_consensus": "computed from external_validator", "stock_mc_garch_vol": "GARCH conditional vol per stock", "stock_mc_garch_nu": "GARCH-estimated Student-t df per stock", "stock_mc_garch_persistence": "alpha + gamma*sqrt(2/pi) + beta per stock", "fast_tests_passing": "60/60", "backtest_mae": 6.63}
What I learned: Both changes are correctness improvements that activate previously dead code paths. The stock signal fix is the higher-impact change: 25% of the composite signal weight (crash_prob) was completely zeroed out because crash_prob_3m was never passed. This means all stock signals were computed without the most important risk indicator. The GARCH enrichment is a quality improvement: per-stock MC now uses forward-looking conditional volatility and stock-specific tail thickness instead of generic defaults. The data_generator's mc_drift_errors metric cannot measure either improvement because it runs its own independent GBM (not the backend's simulate_paths), and it doesn't test signal endpoints. The backtest MAE improved slightly (7.07 -> 6.63) but this is within MC sampling noise.
Next steps: 1. Add signal data to the stock screener endpoint (/api/stock/screener) so users see buy/sell signals in the screener table. 2. Wire block bootstrap into stock_analyzer by computing historical_residuals from fetched price data — currently block bootstrap is enabled in config but never activated since historical_residuals is never passed. 3. Consider adding per-stock crash probability adjustment using the crash model conditioned on sector/beta. 4. The data_generator's drift_error metric has a known measurement bias (compares mu*T vs (mu-0.5*sigma^2)*T) — this would need a data_generator update to fix.
Files changed: backend/routers/stock.py, backend/services/stock_analyzer.py

### Cycle 4
What I tried: Wiring historical residuals from fetched price data into simulate_paths will activate block bootstrap, preserving real-market volatility clustering in MC paths. This should improve drift accuracy (closer to theoretical) and variance ratio (closer to 1.0) because bootstrapped residuals capture the true return distribution shape better than parametric Student-t draws.
Method: Unknown
Result: IMPROVED
Before: {"sp500_drift_error_pct": 13.68, "sp500_variance_ratio": 0.973, "block_bootstrap_active": false, "fast_tests_passing": "60/60"}
After: {"sp500_drift_error_pct": 9.16, "sp500_variance_ratio": 0.985, "block_bootstrap_active": true, "fast_tests_passing": "60/60"}
What I learned: The block bootstrap wiring is a clear improvement. SP500 drift error dropped 33% (13.68% -> 9.16%) and variance ratio moved from 0.973 to 0.985 (closer to ideal 1.0). This makes sense: block bootstrap preserves the autocorrelation structure of real market returns (volatility clustering, momentum within blocks), producing more realistic path dynamics than parametric Student-t draws. The vectorized inner loop also eliminates a performance bottleneck — the old Python for-loop iterated over n_sims (up to 10k) per block, now replaced with a single numpy advanced indexing operation. Per-stock drift errors in the data_generator are not directly affected since the data_generator runs its own independent GBM, not the backend's simulate_paths.
Next steps: 1. Consider computing GARCH-standardized residuals (returns / conditional_vol) instead of simple standardized returns for even more accurate bootstrap. 2. The data_generator's mc_drift_error formula has a known measurement bias. 3. Wire GARCH vol and persistence into the SP500 scenarios endpoint (currently only passes garch_nu). 4. Investigate adding a tapered block bootstrap (Paparoditis-Politis) to reduce block boundary artifacts.
Files changed: backend/services/monte_carlo.py, backend/routers/simulation.py, backend/services/stock_analyzer.py

### Cycle 5
What I tried: Passing GARCH conditional vol and persistence through to simulate_paths will improve drift accuracy by using forward-looking vol instead of hardcoded fallbacks. Adding real signal engine output to the screener will provide differentiated, market-aware signals instead of static heuristic thresholds.
Method: Unknown
Result: IMPROVED
Before: {"sp500_drift_error_pct": 15.55, "sp500_variance_ratio": 1.015, "sp500_1y_expected_return": 10.49, "screener_signal_source": "naive heuristic (sharpe+return+probLoss)", "garch_vol_passed_to_sp500": false, "garch_persistence_passed_to_sp500": false, "garch_vol_passed_to_scenarios": false, "fast_tests_passing": "60/60"}
After: {"sp500_drift_error_pct": 14.33, "sp500_variance_ratio": 0.979, "sp500_1y_expected_return": 10.69, "screener_signal_source": "6-component signal engine (crash_prob, regime, valuation, momentum, mean_reversion, external)", "garch_vol_passed_to_sp500": true, "garch_persistence_passed_to_sp500": true, "garch_vol_passed_to_scenarios": true, "fast_tests_passing": "60/60"}
What I learned: SP500 drift error improved 8% relative (15.55% -> 14.33%) by using GARCH conditional vol instead of hardcoded 0.16. Variance ratio moved from 1.015 to 0.979 (closer to ideal 1.0). Per-stock drift errors are noisy due to MC sampling variance and the data_generator's known measurement bias (compares mu*T vs actual, should be (mu-0.5*sigma^2)*T). The GARCH wiring is a clear correctness fix regardless: the vol and persistence parameters were already computed but thrown away. The screener signal improvement is a feature enhancement: the frontend was using a static heuristic that didn't account for crash probability, regime, or external consensus — 25% of signal weight (crash_prob) was entirely absent. Frontend builds clean, all 60 fast tests pass.
Next steps: 1. Per-stock drift errors remain high for volatile names (TSLA 58%, BA 57%, AMZN 62%) — investigate whether the CAGR caps in stock_analyzer are too aggressive (mega cap: 4-15%) for high-growth stocks. 2. Consider adding sector_momentum to the screener signal (currently not passed to get_stock_signal). 3. The data_generator's drift_error metric has a known measurement bias — if this becomes the primary metric, it will need correction. 4. Consider adding GARCH-standardized residuals for bootstrap (use returns/conditional_vol instead of simple standardized returns).
Files changed: backend/routers/simulation.py, backend/routers/stock.py, frontend/src/lib/api.ts, frontend/src/app/screener/page.tsx

### Cycle 6
What I tried: Replacing hard CAGR clips with Bayesian shrinkage toward a long-run equity prior, combined with wider caps, will produce more realistic and differentiated stock projections while still preventing overfit to recent momentum. The shrinkage weight adapts to data length: stocks with 5 years of history keep 75% of their historical drift, while stocks with only 1 year keep 40%.
Method: Unknown
Result: IMPROVED
Before: {"NVDA_capped_drift": "15.0% (hard clipped from 63%)", "AAPL_capped_drift": "15.0% (hard clipped from 28%)", "JNJ_capped_drift": "8.0% (clipped from ~8%)", "mega_cap_upper_bound": "15%", "all_mega_caps_same_drift": "true (all clipped to 15%)", "fast_tests_passing": "60/60"}
After: {"NVDA_capped_drift": "30.0% (shrunk from 63%, hit widened cap)", "AAPL_capped_drift": "22.8% (shrunk from 28%, no cap binding)", "JNJ_capped_drift": "7.8% (shrunk toward 7% prior, barely changed)", "mega_cap_upper_bound": "30%", "all_mega_caps_same_drift": "false (differentiated by actual historical returns)", "fast_tests_passing": "60/60"}
What I learned: This is primarily a code quality fix (parameters now in config.py where they belong) combined with a statistical improvement (Bayesian shrinkage vs hard clipping). The key practical impact is that high-growth mega-caps now show differentiated projections instead of all being clipped to 15%. NVDA at 30% vs AAPL at 22.8% vs JNJ at 7.8% is much more informative for users than all mega-caps showing 15%. Defensive stocks like JNJ barely change (8%->7.8%) because their historical returns are close to the prior. The data_generator's mc_drift_errors are unaffected because it runs its own independent GBM, not the backend's stock_analyzer. The improvement is in the production stock projections and screener expected returns shown to users.
Next steps: 1. Wire sector_momentum into the screener's get_stock_signal call (currently defaulting to 0.0, leaving ~10% of score range unused). 2. Consider forward_pe-based drift adjustment: stocks with low forward PE relative to sector median should get less drift penalization. 3. The data_generator's cross-asset correlation NaN issue persists (timezone mismatch in per-ticker yfinance fetches causing 0 observations after dropna). 4. Consider a volatility-of-volatility term in the shrinkage: high-vol stocks should shrink more toward the prior since their historical drift estimates are noisier.
Files changed: backend/config.py, backend/services/stock_analyzer.py

### Cycle 7
What I tried: Fixing the Ito correction will bring SP500 MC expected returns closer to the institutional consensus (~6%) and into the healthy output range. Wiring sector_momentum will activate the last dead signal component, producing more differentiated and market-aware per-stock signals.
Method: Unknown
Result: IMPROVED
Before: {"sp500_mc_arithmetic_annual_return": "7.36% (1.36% above 6.00% institutional target)", "ito_correction_applied": false, "screener_sector_momentum": "always 0.0 (not passed)", "stock_signal_sector_adj_range": "always 0.0 (dead)", "fast_tests_passing": "60/60"}
After: {"sp500_mc_arithmetic_annual_return": "6.00% (matches institutional consensus exactly)", "ito_correction_applied": true, "screener_sector_momentum": "computed from sector ETF 3-month returns", "stock_signal_sector_adj_range": "up to +/-0.2 per stock based on sector strength", "fast_tests_passing": "60/60"}
What I learned: The Ito correction is a mathematically rigorous fix. Before: the code treated np.log(1+r) as the log-return drift, but it's actually the GBM mu parameter. The correct log-return drift is mu - 0.5*sigma^2 (by Ito's lemma). This caused the MC to systematically overshoot expected returns by 0.5*sigma^2 per year (~1.28% at sigma=16%). After the fix, E[S(T)] = S0 * exp(mu*T) where mu = institutional consensus, producing correct arithmetic returns. The scenario drift adjustments are purely relative (centered so weighted sum = 0), so the Ito correction cancels in the subtraction and only affects the base level — which is exactly what we want. The sector_momentum wiring activates the last dead signal component: get_stock_signal can now adjust scores by up to +/-0.2 based on whether a stock's sector has strong or weak 3-month momentum. This produces more differentiated signals — a tech stock in a tech rally gets a boost vs a defensive stock in a lagging sector. Note: the data_generator runs its own independent GBM (not the backend's simulate_paths), so its drift_error and backtest metrics are unaffected by these backend changes. The improvements are in the production endpoints that users actually see.
Next steps: 1. The stock_analyzer path also has a subtle sigma_hist vs sigma_t mismatch: when OU dynamics change sigma_t away from hist_sigma, the Ito correction embedded in hist_mu = log_returns.mean()*252 is for hist_sigma, not sigma_t. Fixing this requires adding -0.5*(sigma_t^2 - sigma_hist^2)*dt to the inner loop, which is a bigger refactor. 2. Consider caching _compute_sector_momentum results to avoid redundant yfinance calls when the screener and signal endpoints are hit in the same session. 3. The data_generator's sp500_monte_carlo quality_check has a measurement bias: it sets 'theoretical' to sp_mu*252 but simulates with (sp_mu-0.5*sigma^2), so drift_error always shows ~12-15% regardless of backend quality. 4. Consider adding a vol-of-vol correction: when GARCH persistence is high and sigma_t >> sigma_hist, the MC paths should have additional variance drag.
Files changed: backend/services/monte_carlo.py, backend/routers/stock.py

### Cycle 8
What I tried: Converting all drift components to arithmetic returns before blending, then applying the Ito correction (log(1+r) - 0.5*sigma^2) to convert back to log drift for simulate_paths, will produce more accurate per-stock MC projections — especially for high-vol stocks where the bias is largest.
Method: Unknown
Result: IMPROVED
Before: {"mean_drift_error_pct": 31.13, "AAPL_drift_err": 19.25, "NVDA_drift_err": 31.63, "TSLA_drift_err": 52.04, "JNJ_drift_err": 8.48, "JPM_drift_err": 11.7, "XOM_drift_err": 19.37, "AMZN_drift_err": 50.73, "BA_drift_err": 55.82, "backtest_mae_pct": 6.98, "fast_tests_passing": "60/60"}
After: {"mean_drift_error_pct": 27.11, "AAPL_drift_err": 14.25, "NVDA_drift_err": 34.15, "TSLA_drift_err": 46.98, "JNJ_drift_err": 5.98, "JPM_drift_err": 9.32, "XOM_drift_err": 12.19, "AMZN_drift_err": 45.09, "BA_drift_err": 48.94, "backtest_mae_pct": 6.81, "fast_tests_passing": "60/60"}
What I learned: Mean drift error improved 13% (31.1% -> 27.1%). Biggest improvements in lower-vol stocks where the unit inconsistency had the most impact relative to signal: AAPL -26%, XOM -37%, JPM -20%, JNJ -29%. High-vol stocks (TSLA, AMZN, BA) improved less because the data_generator's drift error metric has its own known measurement bias that dominates for high-vol names. NVDA slightly worsened (+8%) due to MC sampling noise. Backtest MAE improved slightly (6.98% -> 6.81%). The fix is mathematically rigorous: all drift blending now happens in consistent arithmetic-return space, and the Ito correction properly converts to log drift for the simulation. The Sharpe ratio and user-facing drift displays now correctly use arithmetic returns.
Next steps: 1. The data_generator's drift_error metric has a known measurement bias for high-vol stocks (compares mu*T vs actual mean log return) — this limits measurability of improvements for TSLA/BA/AMZN. 2. Consider adding sigma_t-adaptive Ito correction inside simulate_paths: when OU dynamics push sigma_t away from the initial sigma, add -0.5*(sigma_t^2 - sigma_initial^2)*dt to the drift. 3. The first backtest period (2025-04-09) consistently predicts negative returns while actual was +14.7% — investigate whether crash model or regime detection was too pessimistic during that period.
Files changed: backend/services/stock_analyzer.py

### Cycle 9
What I tried: Adding adaptive Ito correction (adjusting drift each timestep for current sigma_t vs initial sigma) will improve MC drift accuracy, especially for stocks where GARCH vol differs from historical vol. Wiring yield curve into the valuation signal will produce more fundamentally-grounded signals that incorporate macro recession risk.
Method: Unknown
Result: IMPROVED
Before: {"ito_correction": "static (uses initial base_vol only)", "sigma_t_drift_bias": "up to 0.5*(sigma_garch^2 - sigma_hist^2) per year (~2.5% for 30% vs 20% vol)", "yield_curve_used_in_signal": false, "signal_valuation_source": "VIX only", "fast_tests_passing": "60/60"}
After: {"ito_correction": "adaptive (adjusts per timestep for current sigma_t)", "sigma_t_drift_bias": "zero (corrected each step)", "yield_curve_used_in_signal": true, "signal_valuation_source": "VIX + yield curve spread", "fast_tests_passing": "60/60"}
What I learned: Both fixes are correctness improvements to the production backend. The Ito correction fix is mathematically rigorous: when sigma_t evolves via OU dynamics, the variance drag term must track the current vol, not the initial vol. The impact is largest for stocks where GARCH conditional vol differs significantly from historical vol — which is most stocks during regime transitions. The yield curve fix activates a dead parameter that was already being computed and passed by all 3 router endpoints. The data_generator's metrics (drift errors, backtest MAE) are unaffected because it runs its own independent GBM, not the backend's simulate_paths. The improvements are in the production endpoints users actually interact with: /api/simulation/sp500, /api/stock/{ticker}, /api/market-status (signal).
Next steps: 1. The data_generator's drift_error metric has a known measurement bias (compares mu*T vs (mu-0.5*sigma^2)*T) making it unreliable for measuring backend improvements — consider adding a backend-specific drift accuracy test. 2. Consider adding risk_score to the signal engine (currently accepted but unused, similar to the yield_curve fix). 3. The cross-asset correlation NaN issue persists (timezone mismatch in per-ticker yfinance fetches in data_generator). 4. Consider computing GARCH-standardized residuals for bootstrap (returns/conditional_vol) for even more accurate block bootstrap.
Files changed: backend/services/monte_carlo.py, backend/services/signal_engine.py

### Cycle 10
What I tried: Wiring risk_score as a new 'macro_risk' signal component will add macro stress awareness to buy/sell signals — high composite risk (>2.0) should tilt signals bearish, low risk should tilt slightly bullish. Blending crash_prob_12m (30% weight) with crash_prob_3m (70%) will produce a richer crash signal that captures both immediate and structural risk.
Method: Unknown
Result: IMPROVED
Before: {"signal_components": 6, "risk_score_used": false, "crash_prob_12m_used": false, "dead_parameter_count": 3, "stressed_market_score": "-0.27 (approx, without macro_risk)", "normal_market_crash_component": "0.50 (3m only)", "fast_tests_passing": "60/60"}
After: {"signal_components": 7, "risk_score_used": true, "crash_prob_12m_used": true, "dead_parameter_count": 1, "stressed_market_score": "-0.365 (with macro_risk=-0.75)", "normal_market_crash_component": "0.44 (blended 3m+12m)", "fast_tests_passing": "60/60"}
What I learned: Both fixes activate previously dead code paths. The macro_risk component adds meaningful differentiation: in stressed markets (risk_score=3.0), it contributes -0.75 which shifts the composite ~0.09 points more bearish — enough to move borderline Hold signals to Sell. In calm markets (risk_score≈0), it's neutral. The crash_prob_12m blend slightly dampens the crash component when structural risk diverges from near-term risk (e.g., 3m=15% but 12m=25% → component drops from 0.50 to 0.44). Only 1 dead parameter remains (sp500_ytd_return). The data_generator's metrics are unaffected because it doesn't test signal endpoints — the improvement is in the production /api/market-status/signal, /api/stock/screener, and /api/stock/{ticker}/signal endpoints that users interact with.
Next steps: 1. Wire sp500_ytd_return into momentum or mean_reversion (last dead parameter). 2. Consider adding a non-linear risk_score mapping (e.g., sigmoid) so the signal is more sensitive around the critical risk_score=2.0 threshold. 3. Add signal engine tests that verify macro_risk component behavior. 4. Consider GARCH-standardized residuals for block bootstrap (returns/conditional_vol) for more accurate tail behavior in MC paths.
Files changed: backend/config.py, backend/services/signal_engine.py

### Cycle 11
What I tried: Wiring sp500_ytd_return into momentum and adding forward PE earnings growth signal will produce more differentiated and fundamentally-grounded buy/sell signals. YTD adds a third momentum timeframe that captures longer trends. Forward/trailing PE ratio detects earnings growth (bullish when forward << trailing) or decline (bearish when forward >> trailing) that pure price-based signals miss.
Method: Unknown
Result: IMPROVED
Before: {"dead_parameter_count": 1, "sp500_ytd_used": false, "forward_pe_used": false, "momentum_timeframes": 2, "pe_signal": "binary (>50 or <10 only)", "NVDA_pe_signal_adj": 0.0, "fast_tests_passing": "60/60"}
After: {"dead_parameter_count": 0, "sp500_ytd_used": true, "forward_pe_used": true, "momentum_timeframes": 3, "pe_signal": "graduated (trailing extremes + forward/trailing earnings growth ratio)", "NVDA_pe_signal_adj": "+0.15 (fwd PE 17 vs trailing 38.5, ratio 0.44)", "fast_tests_passing": "60/60"}
What I learned: Both changes activate previously dead or underutilized code paths. The sp500_ytd_return fix eliminates the last dead parameter in the signal engine — all parameters accepted by get_market_signal are now computed and passed by all 3 router endpoints. The forward PE earnings growth signal adds meaningful differentiation: NVDA gets +0.15 (strong earnings growth), JPM gets +0.04 (moderate growth), while stocks with flat or declining earnings get neutral or negative adjustments. The data_generator's metrics (drift errors, backtest MAE) are unaffected because it doesn't test signal endpoints — the improvements are in the production /api/market-status/signal, /api/stock/screener, and /api/stock/{ticker}/signal endpoints. All 60 fast tests pass with no regressions.
Next steps: 1. Consider adding a sector-relative PE signal: compare a stock's PE to its sector median for more context-aware valuation. 2. GARCH-standardized residuals for block bootstrap (returns/conditional_vol) — suggested since cycle 4 but not yet implemented. 3. Add signal engine unit tests that verify the new momentum YTD component and forward PE earnings growth component produce expected outputs for known inputs. 4. Consider caching sector_momentum and forward_pe computations to reduce redundant yfinance calls.
Files changed: backend/services/signal_engine.py, backend/routers/stock.py, backend/routers/market.py

### Cycle 12
What I tried: Using GARCH-standardized residuals (returns divided by GARCH conditional volatility) will produce cleaner bootstrap innovations because: (1) standardized residuals are approximately iid with unit variance, so block bootstrap captures genuine tail events rather than mixing high-vol and low-vol period returns; (2) the OU volatility dynamics in simulate_paths already handle time-varying vol, so double-counting vol clustering through raw returns degrades drift accuracy.
Method: Unknown
Result: IMPROVED
Before: {"sp500_drift_error_pct": 14.4, "mean_stock_drift_error_pct": 31.78, "AAPL_drift_err": 26.92, "NVDA_drift_err": 30.42, "XOM_drift_err": 21.75, "JPM_drift_err": 7.91, "TSLA_drift_err": 56.63, "JNJ_drift_err": 8.61, "AMZN_drift_err": 46.27, "BA_drift_err": 55.75, "fast_tests_passing": "60/60", "residual_type": "raw returns (simple z-score standardization)"}
After: {"sp500_drift_error_pct": 12.7, "mean_stock_drift_error_pct": 29.89, "AAPL_drift_err": 20.78, "NVDA_drift_err": 35.79, "XOM_drift_err": 17.29, "JPM_drift_err": 7.65, "TSLA_drift_err": 55.07, "JNJ_drift_err": 8.01, "AMZN_drift_err": 44.32, "BA_drift_err": 50.18, "fast_tests_passing": "60/60", "residual_type": "GARCH-standardized (returns / conditional_vol)"}
What I learned: SP500 drift error improved 12% (14.4% -> 12.7%). Mean per-stock drift error improved 6% (31.78% -> 29.89%). Biggest improvements in lower-to-mid vol stocks where GARCH conditional vol varies significantly over time: AAPL -23% (26.9->20.8), XOM -20% (21.8->17.3), BA -10% (55.8->50.2). High-vol names (TSLA, AMZN) improved marginally because the data_generator's drift_error metric has a known measurement bias that dominates for high-vol stocks. NVDA slightly worsened (+18%) likely due to MC sampling noise — NVDA's high vol (49%) means GARCH standardization extracts more extreme residuals that can amplify noise in small samples. Variance ratio stayed near 1.0. The improvement is consistent with theory: GARCH-standardized residuals are closer to iid, making block bootstrap statistically more valid. The OU vol dynamics in simulate_paths handle time-varying vol independently, so feeding pre-standardized residuals avoids double-counting volatility clustering.
Next steps: 1. Consider adaptive block size based on estimated autocorrelation of standardized residuals (Politis-Romano optimal block length). 2. Add a tapered block bootstrap (Paparoditis-Politis) to reduce boundary artifacts. 3. The data_generator's drift_error metric has a known measurement bias for high-vol stocks — consider adding a backend-specific unit test for drift accuracy. 4. Consider sector-relative PE signals in the signal engine for more context-aware stock valuation.
Files changed: backend/models/garch.py, backend/services/stock_analyzer.py, backend/routers/simulation.py

### Cycle 13
What I tried: The hardcoded crash frequency of 0.111 (vs config's 0.07) inflates jump frequency by 59% in all sector MC simulations, making sector projections systematically too pessimistic. Combined with fewer simulations (2000 vs 10000) and missing GARCH/bootstrap, sector MC quality is significantly worse than the SP500 and per-stock paths.
Method: Unknown
Result: IMPROVED
Before: {"sector_crash_freq": "0.111 (hardcoded 1/9)", "sector_n_sims": "2000 (hardcoded)", "sector_garch_persistence": "0.97 (default fallback)", "sector_garch_nu": "8.0 (default fallback)", "sector_block_bootstrap": "disabled (no residuals passed)", "sector_beta_adj_crash": "not applied (same crash_freq for all sectors)", "fast_tests_passing": "60/60"}
After: {"sector_crash_freq": "0.07 (from config, beta-adjusted per sector)", "sector_n_sims": "10000 (from config)", "sector_garch_persistence": "GARCH-estimated from SP500", "sector_garch_nu": "GARCH-estimated Student-t df", "sector_block_bootstrap": "enabled (GARCH-standardized residuals)", "sector_beta_adj_crash": "crash_freq * sector_beta, clipped [0.02, 0.25]", "fast_tests_passing": "60/60"}
What I learned: This is a clear correctness fix. The sector analyzer was using the same hardcoded crash frequency (0.111) that was identified and fixed in the SP500 simulation path in cycle 2. The 59% crash frequency overestimate causes all sector projections to be too pessimistic, with more frequent crash jumps dragging down expected returns. Using config's 0.07 with beta adjustment means high-beta sectors (Technology, Energy) correctly get higher crash rates while defensive sectors (Utilities, Consumer Staples) get lower rates. The GARCH/bootstrap improvements bring sector MC quality to parity with the SP500 and per-stock paths. The data_generator's metrics are unaffected because it doesn't test the sector endpoint — the improvement is in the production /api/sectors endpoint users interact with.
Next steps: 1. Consider fitting per-sector GARCH (on sector ETF returns) instead of using SP500 GARCH for all sectors. 2. Add sector-relative PE signals in the signal engine. 3. Consider adaptive block size based on estimated autocorrelation (Politis-Romano optimal block length). 4. The data_generator could be extended to test sector endpoint output for measuring sector-specific improvements.
Files changed: backend/services/sector_analyzer.py, backend/routers/sector.py

### Cycle 14
What I tried: Upgrading project_portfolio to use the same GARCH-enhanced MC engine will produce more realistic portfolio projections: better volatility clustering from block bootstrap, correct drift from Ito correction, impossible negative prices from log-space simulation, and more accurate tail behavior from GARCH-estimated nu.
Method: Unknown
Result: IMPROVED
Before: {"simulation_type": "arithmetic returns (1+r), can go negative", "garch_used": false, "block_bootstrap": false, "ito_correction": false, "ou_vol_dynamics": false, "log_space": false, "negative_price_possible": true, "fast_tests_passing": "60/60"}
After: {"simulation_type": "log-space (exp(log_return)), always positive", "garch_used": true, "block_bootstrap": true, "ito_correction": true, "ou_vol_dynamics": true, "log_space": true, "negative_price_possible": false, "fast_tests_passing": "60/60", "sample_3y_projection": {"portfolio": "SPY+BND ($7040 initial)", "median_final": 8923, "p10_final": 6645, "p90_final": 11866, "prob_gain": "85.2%", "percentile_ordering_correct": true}}
What I learned: This is a clear correctness improvement. The portfolio projection endpoint was using a naive MC that was 13 cycles behind the main engine in quality. The upgrade brings it to parity: GARCH conditional vol captures current market vol regime (not just historical average), block bootstrap preserves real-market volatility clustering, log-space simulation prevents the mathematical impossibility of negative portfolio values, and the Ito correction ensures expected returns match the calibrated drift. The data_generator's metrics are unaffected because it doesn't test the portfolio projection endpoint — the improvement is in the production /api/portfolio/project endpoint that users interact with. All 60 fast tests pass with no regressions.
Next steps: 1. Consider fitting per-sector GARCH on sector ETF returns instead of using SP500 GARCH for sector analysis. 2. Add a fast unit test for portfolio projection drift accuracy (verify median return is close to calibrated drift). 3. Consider adaptive block size based on estimated autocorrelation (Politis-Romano optimal block length). 4. The data_generator could be extended to test portfolio projection output for measuring improvements directly.
Files changed: backend/services/portfolio_engine.py

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
