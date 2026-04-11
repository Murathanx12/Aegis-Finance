# Aegis Finance - Autonomous R&D Lab - Cycle 5
Time: 2026-04-11T21:34:37.094612

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
   `git add -A && git commit -m "Lab cycle_005: <summary>"`

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
  `python lab/data_generator.py --output-dir lab/experiments/cycle_005/data_test --cycle 5`

### Step 4: Write the experiment report

CRITICAL - You MUST create this file before finishing:
lab/experiments/cycle_005/experiment_report.json

Contents:
{
    "cycle": 5,
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
git commit -m "Lab cycle_005: <summary>"

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
      "mc_median_return_pct": -0.92,
      "direction_correct": false,
      "absolute_error_pct": 15.63
    },
    {
      "test_start": "2025-07-11",
      "horizon_days": 63,
      "actual_return_pct": 7.59,
      "mc_median_return_pct": 3.0,
      "direction_correct": true,
      "absolute_error_pct": 4.59
    },
    {
      "test_start": "2025-10-09",
      "horizon_days": 63,
      "actual_return_pct": 3.43,
      "mc_median_return_pct": 3.9,
      "direction_correct": true,
      "absolute_error_pct": 0.47
    }
  ],
  "summary": {
    "n_tests": 3,
    "direction_accuracy_pct": 66.7,
    "mean_absolute_error_pct": 6.9
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
    "risk_profile": "aggressive",
    "total_value_approx": 405050.46,
    "n_holdings": 7,
    "holdings": [
      {
        "ticker": "TSLA",
        "name": "Tesla",
        "sector": "Consumer Discretionary",
        "shares": 184,
        "weight": 0.047,
        "cost_basis": 103.17,
        "purchase_date": "2026-01-11"
      },
      {
        "ticker": "JPM",
        "name": "JPMorgan",
        "sector": "Financials",
        "shares": 944,
        "weight": 0.2947,
        "cost_basis": 126.39,
        "purchase_date": "2025-11-20"
      },
      {
        "ticker": "AAPL",
        "name": "Apple",
        "sector": "Technology",
        "shares": 33,
        "weight": 0.0083,
        "cost_basis": 100.46,
        "purchase_date": "2024-04-23"
      },
      {
        "ticker": "JNJ",
        "name": "J&J",
        "sector": "Healthcare",
        "shares": 464,
        "weight": 0.1438,
        "cost_basis": 125.41,
        "purchase_date": "2026-02-08"
      },
      {
        "ticker": "META",
        "name": "Meta",
        "sector": "Technology",
        "shares": 708,
        "weight": 0.1646,
        "cost_basis": 94.07,
        "purchase_date": "2024-05-10"
      },
      {
        "ticker": "WMT",
        "name": "Walmart",
        "sector": "Consumer Staples",
        "shares": 568,
        "weight": 0.0795,
        "cost_basis": 56.61,
        "purchase_date": "2025-10-20"
      },
      {
        "ticker": "MSFT",
        "name": "Microsoft",
        "sector": "Technology",
        "shares": 855,
        "weight": 0.2622,
        "cost_basis": 124.16,
        "purchase_date": "2024-12-03"
      }
    ]
  },
  {
    "id": "portfolio_2",
    "risk_profile": "aggressive",
    "total_value_approx": 63422.45,
    "n_holdings": 6,
    "holdings": [
      {
        "ticker": "CAT",
        "name": "Caterpillar",
        "sector": "Industrials",
        "shares": 10,
        "weight": 0.0149,
        "cost_basis": 92.94,
        "purchase_date": "2025-03-04"
      },
      {
        "ticker": "NVDA",
        "name": "NVIDIA",
        "sector": "Technology",
        "shares": 238,
        "weight": 0.5075,
        "cost_basis": 134.86,
        "purchase_date": "2024-06-25"
      },
      {
        "ticker": "AAPL",
        "name": "Apple",
        "sector": "Technology",
        "shares": 28,
        "weight": 0.0385,
        "cost_basis": 84.84,
        "purchase_date": "2025-12-28"
      },
      {
        "ticker": "JPM",
        "name": "JPMorgan",
        "sector": "Financials",
        "shares": 29,
        "weight": 0.0493,
        "cost_basis": 106.8,
        "purchase_date": "2025-02-25"
      },
      {
        "ticker": "TSLA",
        "name": "Tesla",
        "sector": "Consumer Discretionary",
        "shares": 161,
        "weight": 0.3465,
        "cost_basis": 136.35,
        "purchase_date": "2024-09-01"
      },
      {
        "ticker": "MSFT",
        "name": "Microsoft",
        "sector": "Technology",
        "shares": 51,
        "weight": 0.0434,
        "cost_basis": 53.72,
        "purchase_date": "2024-07-10"
      }
    ]
  },
  {
    "id": "portfolio_3",
    "risk_profile": "aggressive",
    "total_value_approx": 421483.89,
    "n_holdings": 8,
    "holdings": [
      {
        "ticker": "JNJ",
        "name": "J&J",
        "sector": "Healthcare",
        "shares": 27,
        "weight": 0.008,
        "cost_basis": 122.89,
        "purchase_date": "2024-12-19"
      },
      {
        "ticker": "CVX",
        "name": "Chevron",
        "sector": "Energy",
        "shares": 393,
        "weight": 0.0599,
        "cost_basis": 64.17,
        "purchase_date": "2026-01-29"
      },
      {
        "ticker": "UNH",
        "name": "UnitedHealth",
        "sector": "Healthcare",
        "shares": 1072,
        "weight": 0.2417,
        "cost_basis": 94.93,
        "purchase_date": "2024-08-01"
      },
      {
        "ticker": "META",
        "name": "Meta",
 
... [truncated]
```

### run_metadata
```json
{
  "cycle": 5,
  "timestamp": "2026-04-11T21:34:11.212947",
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
      "AAPL": 20.52,
      "NVDA": 25.6,
      "XOM": 8.77,
      "JPM": 8.64,
      "TSLA": 55.44,
      "JNJ": 6.42,
      "AMZN": 33.06,
      "BA": 46.39
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
    "median_price": 7420.3,
    "mean_price": 7554.9,
    "p5": 5596.63,
    "p95": 9923.82,
    "prob_positive": 69.3,
    "prob_20pct_crash": 3.7,
    "expected_annual_return_pct": 10.83
  },
  "3y": {
    "median_price": 8922.66,
    "mean_price": 9269.56,
    "p5": 5440.52,
    "p95": 14417.86,
    "prob_positive": 81.5,
    "prob_20pct_crash": 5.0,
    "expected_annual_return_pct": 10.79
  },
  "5y": {
    "median_price": 10469.85,
    "mean_price": 11230.16,
    "p5": 5635.51,
    "p95": 19304.88,
    "prob_positive": 87.1,
    "prob_20pct_crash": 4.2,
    "expected_annual_return_pct": 10.5
  },
  "quality_check": {
    "theoretical_1y_drift": 0.10072,
    "actual_1y_mean_log_return": 0.09043,
    "drift_error_pct": 10.22,
    "variance_ratio": 0.989
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
      "median_price": 311.13,
      "mean_price": 319.19,
      "p5": 190.89,
      "p25": 254.27,
      "p75": 366.04,
      "p95": 487.04,
      "prob_above_current": 72.4,
      "prob_20pct_drawdown": 8.8,
      "expected_return_pct": 22.54,
      "median_return_pct": 19.45
    },
    "mc_quality": {
      "drift_error_pct": 20.52,
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
      "median_price": 244.62,
      "mean_price": 279.32,
      "p5": 108.02,
      "p25": 182.63,
      "p75": 344.34,
      "p95": 554.24,
      "prob_above_current": 72.7,
      "prob_20pct_drawdown": 14.7,
      "expected_return_pct": 48.08,
      "median_return_pct": 29.68
    },
    "mc_quality": {
      "drift_error_pct": 25.6,
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
      "median_price": 173.9,
      "mean_price": 179.22,
      "p5": 118.94,
      "p25": 149.36,
      "p75": 203.01,
      "p95": 262.86,
      "prob_above_current": 72.2,
      "prob_20pct_drawdown": 6.3,
      "expected_return_pct": 17.51,
      "median_return_pct": 14.02
    },
    "mc_quality": {
      "drift_error_pct": 8.77,
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
      "annualiz
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
