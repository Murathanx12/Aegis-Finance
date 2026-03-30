# Gap Analysis — Aegis Finance Backend Services

*Generated: 2026-03-31 by Unit 4 Deep Research*

## Grading Scale

- **A** = Institutional quality, publishable methodology
- **B** = Solid implementation with minor gaps
- **C** = Functional but meaningful methodology or engineering gaps
- **D** = Significant issues that affect correctness
- **F** = Broken or fundamentally flawed

---

## Summary Table

| Module | File | Grade | Does Right | Wrong/Missing | Priority | Effort |
|--------|------|-------|------------|---------------|----------|--------|
| config | `config.py` | **A-** | Centralized params, dataclass APIKeys, scenario definitions, convenience accessors | No validation on config values; `horizon_adjustment` magic number undocumented; `risk_free_rate` not centralized (each module picks its own) | Low | 1hr |
| cache | `cache.py` | **B+** | Two-layer (memory + disk), thread-safe with lock, retry decorator with jitter, TTL-based eviction | `cached` decorator skips `args[0]` assuming `self` — breaks on plain functions; no max memory size limit; disk cache TTL re-checked on every read (no background eviction) | Medium | 2hr |
| data_fetcher | `data_fetcher.py` | **B+** | Batch Yahoo downloads, parallel FRED, thread-safe yf lock, proper treasury conversion, retry with backoff | `ffill().bfill()` on entire DataFrame masks data gaps silently; no validation that returned data is non-stale; FRED parallel fetch has no rate limiting; `get_recession_probability` logistic transform is ad-hoc (not calibrated) | Medium | 3hr |
| monte_carlo | `monte_carlo.py` | **B** | Merton jump compensator (Bug 20 fix), block bootstrap, O-U vol dynamics, leverage effect, scenario weighting, realism validation | Block bootstrap inner loop is O(days * n_sims) Python — very slow; `xi = 0.06` hardcoded (line 175, violates config rule); `rho_leverage = -0.7` hardcoded (line 255); no antithetic variates; no DCC-GARCH correlation; total sim count drifts from `n_sims` due to integer rounding in scenario allocation | High | 4hr |
| risk_scorer | `risk_scorer.py` | **B** | 9-factor composite, config-driven weights, dual z-score for stress sensitivity, VIX floor with graduated thresholds | Momentum exhaustion (line 82) uses SP500 without null-check; `_dual_zscore` takes max of two z-scores but should arguably use the one with more recent signal; VIX floor logic (lines 121-123) uses chained `.where()` incorrectly — condition semantics are inverted from pandas convention | High | 2hr |
| regime_detector | `regime_detector.py` | **C+** | Config-driven thresholds, leading indicator overlay, short-window drawdown override | O(n) loop over every trading day is very slow on 35 years of data; no HMM integration (parallel module exists but not blended); regime labels are string-based (no enum); lookback uses `.iloc[i-21]` which is fragile if index has gaps; no smoothing — regime can flip daily | Medium | 3hr |
| crash_model | `crash_model.py` | **B+** | LightGBM + Logistic blend, isotonic calibration, purged train/val split with gap days, temporal weights, proper SHAP integration | `fillna(0)` on line 203 for Logistic Regression (violates project rule — should impute or drop); calibration on validation set reuses val data (proper approach: hold out separate calibration set); no conformal prediction intervals; `predict_proba` clips to [0.02, 0.98] — calibration should handle this | Medium | 3hr |
| stock_analyzer | `stock_analyzer.py` | **C+** | Cap-tier CAGR caps, analyst target blending, sector-peer mapping, enriched yfinance data (holders, earnings, news) | `risk_free_rate=0.04` hardcoded in function signature (not from config); `STOCK_CAGR_CAPS` and `DEFAULT_WATCHLIST` hardcoded (not in config); sequential stock analysis — no parallelism; MC uses only 3000 sims (config says 10000); no handling of delisted/invalid tickers; `_get_key_stats` sums returns instead of compounding (line 386-389) | High | 3hr |
| sector_analyzer | `sector_analyzer.py` | **B-** | Multi-factor model (beta, momentum, mean reversion, vol), cap-weight normalization to index, per-sector MC | `_SECTOR_WEIGHTS` hardcoded (should be in config or fetched dynamically); `n_sims = 2000` hardcoded (line 165); `crash_freq = 1.0/9.0` hardcoded (line 177); MC called without `historical_residuals` so block bootstrap never activates; no Fama-French factors (only CAPM + ad-hoc) | Medium | 3hr |
| portfolio_engine | `portfolio_engine.py` | **C** | Goal-based templates, risk profiling questionnaire, stress testing, stateless design | No Black-Litterman optimization (Phase 3 goal); no HRP (Phase 3 goal); no Ledoit-Wolf covariance shrinkage; `rf_daily = 0.04/252` hardcoded (line 187); `yf.download` called without thread lock (data_fetcher has one but portfolio_engine doesn't use it); `build_portfolio` makes N sequential yf.Ticker calls — slow; project_portfolio MC is basic GBM (no jumps, no fat tails); templates are static — not data-driven | High | 8hr |
| shap_explainer | `shap_explainer.py` | **B** | Clean separation of concerns, counterfactual analysis, default scenarios, handles edge cases | No caching of SHAP values (expensive to recompute); `DEFAULT_SCENARIOS` feature names may not match trained model features; no SHAP summary plots or waterfall chart data; no force plot data export | Low | 2hr |
| news_intelligence | `news_intelligence.py` | **B-** | GDELT integration (no API key needed), event score with convergence bonus, sector keyword mapping, graceful fallback | Keyword matching is naive (no NLP/embeddings); `_SECTOR_KEYWORDS` hardcoded (not in config); `adjust_crash_probability` only boosts, never dampens — asymmetric by design but undocumented; no rate limiting on GDELT requests; no caching of GDELT responses (caller must cache) | Low | 2hr |
| llm_analyzer | `llm_analyzer.py` | **B** | Lazy client init, graceful fallback, structured prompt parsing, proper caching, availability check | Sentiment detection is keyword-based (should use LLM score); `_DEEPSEEK_API_KEY` read at module level (not from config/APIKeys dataclass); `_MAX_TOKENS = 500` hardcoded; no retry on rate limits; structured parsing (BULL/BEAR/SCORE) is brittle — LLM may not follow format | Low | 2hr |
| savings_calculator | `savings_calculator.py` | **B+** | Clean math, real vs nominal, milestone tracking, required monthly calculation, PMT formula | Expected returns hardcoded (`{"conservative": 0.05, ...}`) not from config; no Monte Carlo variant (documented as "pure math" which is fine); no tax consideration; `monthly_rate - monthly_inflation` approximation is slightly wrong (should be `(1+r)/(1+i)-1`) | Low | 1hr |
| data_quality | `data_quality.py` | **B+** | Config-driven thresholds, severity levels, compact summary API, staleness/range/completeness/consistency checks | No check for weekend/holiday gaps (staleness check uses calendar days, not business days); no distribution checks (e.g., return normality); `summary` truncates to 10 warnings — could miss critical ones; no time-series-specific checks (e.g., unit root) | Low | 2hr |
| net_liquidity | `net_liquidity.py` | **B** | Correct formula (WALCL - TGA - RRP), weekly resampling, proper unit conversion, signal generation | `rrp * 1000` conversion factor (line 74) — comment says "billions to millions" but RRPONTSYD is already in millions, so this may be a bug; signal thresholds (`0.05` trillion WoW) are hardcoded; no config-driven thresholds; no trend analysis beyond WoW | Medium | 2hr |
| return_model | `return_model.py` | **B** | Quantile regression (10th/50th/90th), purged split, temporal decay weights, skill score computation, coverage metric, clean fallback class | `predict` clips to training range * 1.2 — could mask regime changes; no conformal prediction; fallback class `train` returns `success: True` with `skill_score: 0.0` (misleading); `_cfg.get("ml", {}).get("temporal_weight_decay", 0.0005)` — key doesn't exist in config | Low | 2hr |
| external_validator | `external_validator.py` | **B-** | Dataclass result, multiple independent sources (LEI, SLOOS, Fed, sentiment), divergence alerts | Sentiment assessment (line 194-207) thresholds seem off — UMich Sentiment > 100 = "GREED" but normal range is 50-100; `_assess_lei` uses `resample("MS")` which may not align with LEI's monthly release dates; no IMF GDP forecast integration (listed in docstring but not implemented); consensus logic counts booleans, not actual signal strength | Medium | 2hr |
| regime_validator | `regime_validator.py` | **B** | 3-check confirmation (price structure, breadth, consensus), dataclass result, graduated confidence | `_check_consensus` compares static institutional benchmarks (never change) against regime — always returns same answer; breadth check uses 21-day window only — misses medium-term trends; no VIX-based confirmation check | Low | 1hr |
| signal_engine | `signal_engine.py` | **C+** | Composite signal with 6 factors, config-like weight structure, per-stock adjustment with beta/analyst/PE | Valuation signal uses VIX as proxy instead of actual CAPE/PE (misleading name); weights hardcoded in module (not in config.py); `_ACTION_THRESHOLDS` not configurable; no backtest validation of thresholds; mean reversion and momentum signals can conflict without reconciliation | Medium | 3hr |
| signal_optimizer | `signal_optimizer.py` | **C** | Grid search over weights, walk-forward design, Sharpe + hit rate metrics | Uses VIX as crash probability proxy (real crash model not available in backtest); `external` component is always 0 (useless dimension); grid search is brute force — no Bayesian optimization; no out-of-sample validation (tests on same period it optimizes); short backtest period (2020-2025) includes COVID anomaly | Medium | 4hr |
| backtest (service) | `backtest.py` | **C+** | Walk-forward monthly evaluation, downloads data once, records forward returns, hit rate analysis | Same VIX-as-crash-proxy issue; no transaction costs; strategy assumes quarterly rebalancing but uses overlapping 3M returns (inflates Sharpe); `evaluate_backtest` "correct" definition for Hold (line 205) is arbitrary (|return| < 10%); no regime-conditioned analysis | Medium | 3hr |
| garch | `models/garch.py` | **A-** | GJR-GARCH(1,1) with skewed Student-t, multiple param extraction, forward vol simulation, persistence-based extension, clean NamedTuple result | `scaled = clean * 100` is common but can cause issues with very small returns; forecast method uses `method="simulation"` which is stochastic — no analytical forecast option; `_fallback_result` doesn't set sensible omega/alpha/gamma/beta for the specific return series | Low | 1hr |
| hmm | `models/hmm.py` | **B+** | 3-state Gaussian HMM, multiple random restarts, feature standardization, regime probability reordering, clean NamedTuple result | Only 3 features (returns, vol, VIX) — could add credit spread, yield curve; state labeling by mean return assumes sorted states = Crisis/Bear/Bull — may mislabel in unusual regimes; `ffill().bfill().fillna("Bull")` default to Bull is biased; 200 iterations may not converge for all seeds | Low | 2hr |

---

## Detailed Notes per Module

### config.py (A-)

**Strengths:** True single source of truth. Scenarios sum to ~1.0 probability. Institutional benchmarks are sourced and dated. Convenience accessors are clean.

**Gaps:**
1. `risk_free_rate` is not centralized — `stock_analyzer.py` uses 0.04, `portfolio_engine.py` uses 0.04, `sector_analyzer.py` reads T3M from data. Should be one config key or computed from T3M.
2. No schema validation — if someone adds a bad value to config, it silently propagates.
3. `horizon_adjustment = 1.05` — undocumented why 5Y returns are 5% higher than 10Y assumptions.

**Fix:** Add a `risk_free_rate` key to `config["simulation"]` (or a function that reads T3M with fallback). Add docstrings for non-obvious parameters.

---

### cache.py (B+)

**Strengths:** Two-layer architecture is thoughtful. Retry decorator is production-grade with jitter. Thread safety via lock.

**Gaps:**
1. Line 150: `arg_key = str(args[1:])` skips first arg assuming `self`. For module-level functions or static methods, this skips the first real argument. Example: `fetch_safe(ticker, start, end)` would cache `(start, end)` only, not `ticker`.
2. No max memory size — unbounded memory growth possible with many unique cache keys.
3. No cache statistics (hit rate, size, eviction count) for monitoring.

**Fix:** Change `cached` decorator to accept `skip_self=True` parameter. Add optional `max_entries` to memory cache.

---

### data_fetcher.py (B+)

**Strengths:** Batch Yahoo downloads (~5x speedup). Thread lock for yfinance safety. Parallel FRED fetching.

**Gaps:**
1. Line 237: `data = data.ffill().bfill()` — forward-filling is reasonable but back-filling at the start is dangerous. It means the first few years of data for newer series (like SKEW, started 2011) get filled with future values. This is a subtle data leakage vector.
2. `get_recession_probability` (line 299): The logistic transform `1/(1+exp(2*spread))` is not calibrated. The coefficient 2.0 is arbitrary. Academic models (Estrella & Mishkin 1998) use probit with specific coefficients.
3. No data validation after fetch — could return corrupted data if Yahoo has an outage.

**Fix:** Replace `bfill()` with column-specific fill or leave NaN for columns that start late. Calibrate recession model or use the FRED RECPROUSM156N directly.

---

### monte_carlo.py (B)

**Strengths:** Merton jump compensator correctly implemented. Block bootstrap preserves vol clustering. O-U volatility dynamics are more realistic than constant vol. Realism validation catches obvious errors.

**Gaps:**
1. **Performance:** Block bootstrap inner loop (lines 77-85) is pure Python nested loop over `(n_blocks, n_sims)`. With 10,000 sims and 1260 days, this is ~600,000 iterations. Should be vectorized with fancy indexing.
2. **Hardcoded params:** `xi = 0.06` (line 175), `rho_leverage = -0.7` (line 255) — both should come from config or GARCH fit.
3. **No antithetic variates** — Phase 2 roadmap item, would halve variance for same sim count.
4. **Sim count drift:** `sims_for_scenario = int(n_sims * weight)` — due to rounding, total sims across scenarios may not equal n_sims. Could be 9,950 instead of 10,000.
5. **No variance drain correction:** `base_drift` comment says "NO extra -0.5*sigma^2" (line 280-281) but for geometric Brownian motion, the Ito correction IS needed when drift is expressed as arithmetic return. The code converts to log return via `np.log(1+ml_predicted_return)` (line 136) which already accounts for this, but only when `ml_predicted_return` is set. When using `historical_mu` (already log), the correction is indeed not needed — this is correct but the comment is confusing and error-prone.

**Fix:** Vectorize block bootstrap. Move xi and rho_leverage to config. Add sim count reconciliation.

---

### risk_scorer.py (B)

**Strengths:** Dual z-score idea is clever for catching stress that normalizes in long windows. Config-driven weights.

**Gaps:**
1. **VIX floor logic bug (lines 120-123):** The chained `.where()` calls don't work as intended. `pd.Series.where(cond, other)` keeps values where `cond` is True and replaces with `other` where False. The chain `vix_floor.where(vix_10d_avg <= 22, 0.3).where(vix_10d_avg <= 25, 0.5)` means: start with 0.0, replace with 0.3 where VIX > 22, then replace with 0.5 where VIX > 25. But the second `.where()` operates on the result of the first — so values that were set to 0.3 (VIX 22-25) get overwritten to 0.5 if VIX > 25. The logic works but only by accident because higher VIX always triggers later conditions. However, the final `.where(vix_10d_avg <= 30, 0.8)` will also overwrite VIX 25-30 values to 0.8, which is correct — but VIX > 30 values remain at 0.8 instead of getting a higher floor. This caps the floor at 0.8 even for VIX = 80.
2. **No null check** on SP500 before computing momentum exhaustion (line 80).

**Fix:** Replace chained `.where()` with explicit `np.where` or `pd.cut` for clarity. Add `.dropna()` or null check for SP500.

---

### regime_detector.py (C+)

**Strengths:** Leading indicator overlay is the right idea. Short-window drawdown override prevents stale Bull calls.

**Gaps:**
1. **O(n) loop** (line 46): Iterates over every day from `window` to `len(data)` — with 35 years of daily data, that's ~8,800 iterations with rolling window computations inside. This is slow and should use vectorized rolling operations.
2. **No HMM integration:** The HMM model exists in `models/hmm.py` but regime_detector doesn't use it. Two parallel regime systems with no blending.
3. **No smoothing:** Regime can flip between Bull and Volatile on consecutive days based on single-day VIX spikes. Should have a minimum holding period or smoothing window.
4. **Fragile indexing:** `data["SP500"].iloc[i] / data["SP500"].iloc[i - 21]` — if data has gaps (weekends already removed, but holidays create gaps in iloc vs actual dates), this measures the wrong window.

**Fix:** Vectorize with rolling windows. Add regime smoothing (e.g., 5-day minimum hold). Integrate HMM probabilities as a tiebreaker.

---

### crash_model.py (B+)

**Strengths:** Dual-model blend with isotonic calibration is sound. Purged split with horizon-specific gap days. Temporal weighting. Clean save/load.

**Gaps:**
1. **`fillna(0)` violation** (line 203): `train_X_scaled = scaler.fit_transform(train_X.fillna(0))` — the project rule says "DO NOT use fillna(0) on feature matrices." LightGBM handles NaN natively, but Logistic Regression doesn't. Should use `SimpleImputer` with median strategy instead of 0.
2. **Calibration data reuse:** Isotonic calibration is fit on the validation set (line 225), then metrics are computed on the same validation set (line 229). This overfits the calibration. Should use a 3-way split: train / calibration / test, or cross-validate the calibration.
3. **No monotonicity enforcement:** 3m < 6m < 12m crash probability ordering is validated externally but not enforced in the model. Could add a post-processing step.

**Fix:** Replace `fillna(0)` with `SimpleImputer(strategy='median')`. Split validation into calibration + test.

---

### stock_analyzer.py (C+)

**Strengths:** Market-cap-tier CAGR caps prevent unrealistic projections. Analyst target blending. Rich yfinance data extraction.

**Gaps:**
1. **Hardcoded risk_free_rate=0.04** in function signature (line 97) — not from config.
2. **Hardcoded constants** `STOCK_CAGR_CAPS`, `DEFAULT_WATCHLIST`, `SECTOR_STOCK_MAP` — should be in config.
3. **Only 3000 sims** (line 144) when config says 10000.
4. **Return computation bug** (lines 386-389): `float(returns.iloc[-21:].sum()) * 100` — summing simple returns is incorrect for multi-day returns. Should use `(1+returns.iloc[-21:]).prod() - 1`.
5. **No parallelism:** `analyze_stocks` loops sequentially over tickers. With 20+ stocks, each making yfinance calls, this is very slow.
6. **No yf_lock usage:** Uses `yf.Ticker(ticker)` directly without the thread lock from data_fetcher.

**Fix:** Move constants to config. Fix return computation to use compounding. Add ThreadPoolExecutor for parallel analysis. Use n_sims from config.

---

### sector_analyzer.py (B-)

**Strengths:** Multi-factor model with proper CAPM + alpha factors. Cap-weight normalization ensures consistency with index.

**Gaps:**
1. `_SECTOR_WEIGHTS` hardcoded — should be in config or dynamically fetched.
2. `n_sims = 2000` hardcoded (line 165) — config says 10000.
3. `crash_freq = 1.0/9.0` hardcoded (line 177) — should come from market-level calculation.
4. MC called without `historical_residuals` — block bootstrap never activates for sectors.
5. No Fama-French factor loading — only uses single-factor CAPM.

**Fix:** Move weights and sim count to config. Pass historical residuals. Consider adding SMB/HML/momentum factors from academic literature.

---

### portfolio_engine.py (C)

**Strengths:** Clean stateless design. Risk profiling questionnaire is well-structured. Stress test with beta adjustment.

**Gaps:**
1. **No Black-Litterman:** Phase 3 roadmap goal, not implemented. Using static allocation templates instead.
2. **No HRP:** Phase 3 roadmap goal, not implemented.
3. **No Ledoit-Wolf covariance shrinkage:** Using sample covariance which is noisy for many assets.
4. **Hardcoded rf** (line 187): `rf_daily = 0.04 / 252`.
5. **No yf_lock:** `yf.download` and `yf.Ticker` called without thread safety.
6. **project_portfolio** uses basic GBM (no jumps, no fat tails) — inconsistent with the MC engine.
7. **Stress test** uses only beta-scaled S&P drawdown — no correlation structure, no sector-specific drawdowns.
8. **Templates are static** — no data-driven allocation based on current market conditions.

**Fix:** This is the largest gap. Integrate PyPortfolioOpt (already installed) for BL and HRP. Use Ledoit-Wolf shrinkage. This is a multi-session effort.

---

### shap_explainer.py (B)

**Strengths:** Clean API, counterfactual analysis is a differentiator, handles edge cases.

**Gaps:**
1. No caching — SHAP computation is expensive (tree traversal).
2. `DEFAULT_SCENARIOS` feature names may not match actual trained feature names.
3. No visualization data (waterfall, beeswarm) — only raw values.

**Fix:** Add `@cached` decorator. Validate scenario feature names against model.

---

### news_intelligence.py (B-)

**Strengths:** GDELT requires no API key. Event score with convergence bonus is a good design. Graceful fallback.

**Gaps:**
1. Keyword matching is extremely naive — "apple" matches Apple Inc and apple fruit.
2. No caching at service level (relies on caller).
3. `adjust_crash_probability` only increases, never decreases — asymmetric and undocumented.
4. No rate limiting on GDELT (3 requests per call).

**Fix:** Add `@cached` to GDELT functions. Consider basic TF-IDF or at least case-sensitive matching for ambiguous terms.

---

### llm_analyzer.py (B)

**Strengths:** Lazy init, availability check, structured prompt format, fallback handling.

**Gaps:**
1. `_DEEPSEEK_API_KEY` read at module level via `os.getenv` — inconsistent with `APIKeys` dataclass pattern.
2. No retry on API rate limits.
3. Structured response parsing is brittle.
4. No token counting or cost tracking.

**Fix:** Move API key to `APIKeys` dataclass. Add retry decorator. Consider JSON-mode prompts for structured output.

---

### savings_calculator.py (B+)

**Strengths:** Clean math, real vs nominal separation, milestone tracking, PMT formula.

**Gaps:**
1. Expected returns hardcoded (not from config).
2. Real rate approximation `r - i` instead of `(1+r)/(1+i) - 1` — error is ~0.2% which matters over 30+ years.
3. No Monte Carlo variant (but documented as intentional).

**Fix:** Move returns to config. Fix real rate formula.

---

### data_quality.py (B+)

**Strengths:** Config-driven thresholds, multiple check types, severity grading, compact summary.

**Gaps:**
1. Staleness uses calendar days, not business days — weekends trigger false warnings.
2. No distributional checks.
3. Summary truncates to 10 warnings.

**Fix:** Use `pd.bdate_range` for staleness. Return all warnings in summary (paginate in API layer).

---

### net_liquidity.py (B)

**Strengths:** Correct formula, weekly alignment, unit conversion.

**Gaps:**
1. **Potential bug on line 74:** `rrp * 1000` — RRPONTSYD (Overnight Reverse Repurchase Agreements) is reported in billions by FRED, while WALCL and WTREGEN are in millions. So `* 1000` converts billions to millions for alignment. This is correct but the comment says "Convert billions to millions" which is right. However, this should be validated against actual FRED metadata.
2. Signal thresholds hardcoded (not in config).
3. No trend analysis beyond week-over-week.

**Fix:** Add thresholds to config. Add 4-week and 13-week trend analysis.

---

### return_model.py (B)

**Strengths:** Quantile regression with coverage validation. Purged split. Temporal decay. Clean fallback.

**Gaps:**
1. `temporal_weight_decay` config key referenced but doesn't exist in config.py — falls back to 0.0005.
2. Fallback class returns `success: True` which is misleading.
3. No conformal prediction (mentioned in engine/validation but not integrated here).

**Fix:** Add `temporal_weight_decay` to config. Fix fallback to return `success: False` or clearly mark as fallback.

---

### external_validator.py (B-)

**Strengths:** Multiple independent sources, dataclass result, divergence alerts.

**Gaps:**
1. **Sentiment thresholds are off:** UMich Consumer Sentiment historical range is roughly 50-110. The code maps < 60 = EXTREME_FEAR, < 80 = FEAR, < 100 = NEUTRAL, > 100 = GREED. But the long-run average is ~85, so "NEUTRAL" at 80-100 is actually slightly below average. Thresholds should be z-score-based.
2. IMF GDP forecast integration listed in docstring but not implemented.
3. `_check_consensus` always returns True for non-bear regimes because institutional consensus is always > 3% (currently ~5.7%).

**Fix:** Use z-score-based sentiment thresholds. Remove or implement IMF integration. Make consensus check dynamic.

---

### regime_validator.py (B)

**Strengths:** 3-check confirmation framework, graduated confidence.

**Gaps:**
1. Consensus check is effectively a constant — institutional benchmarks don't change between requests.
2. Only 21-day breadth window — misses medium-term deterioration.
3. No VIX confirmation check.

**Fix:** Add VIX confirmation. Add 63-day breadth window. Make consensus dynamic (could use current-year forecast data).

---

### signal_engine.py (C+)

**Strengths:** 6-factor composite, per-stock adjustment, clear action thresholds.

**Gaps:**
1. **Misleading "valuation" signal** — uses VIX, not actual valuation metrics (CAPE, P/E).
2. **Weights not in config.py** — `_DEFAULT_WEIGHTS` defined in module.
3. **No backtest validation** of threshold levels (0.45, 0.15, -0.15, -0.45).
4. **Momentum and mean reversion can conflict** without reconciliation — e.g., 3M return of -10% triggers both bearish momentum and bullish mean reversion simultaneously.

**Fix:** Rename "valuation" to "fear_gauge" or integrate actual CAPE data. Move weights to config. Add conflict resolution logic.

---

### signal_optimizer.py (C)

**Strengths:** Grid search concept, walk-forward structure.

**Gaps:**
1. **In-sample optimization:** Tests and selects on same period — no held-out test set for final evaluation.
2. **VIX as crash proxy** — real crash model not used.
3. **Short period** (2020-2025) dominated by COVID and recovery — not representative.
4. **No Bayesian optimization** — grid search is O(n^6), very slow.
5. **External component always 0** — wasting a dimension.

**Fix:** Add train/test split (e.g., optimize on 2010-2020, validate on 2020-2025). Use Optuna for Bayesian optimization.

---

### backtest.py (C+)

**Strengths:** Walk-forward monthly, forward return measurement, hit rate + Sharpe analysis.

**Gaps:**
1. **Overlapping 3M returns:** Monthly signals with 3M forward returns overlap by 2 months — inflates significance.
2. **No transaction costs.**
3. **Hold "correctness" threshold** (|return| < 10%) is arbitrary.
4. **No regime-conditioned analysis** — can't tell if signal works in bear markets specifically.

**Fix:** Use non-overlapping 3M windows, or adjust Sharpe for autocorrelation. Add regime-conditioned metrics.

---

### garch.py (A-)

**Strengths:** GJR-GARCH(1,1) with skewed-t innovations is state-of-the-art for single-asset vol. Clean NamedTuple. Forward simulation. Proper fallback.

**Gaps:**
1. No Student-t DCC for multi-asset correlation.
2. Forecast simulation is stochastic — could add analytical forecast option for speed.
3. Fallback uses generic params, not fitted to the specific series.

**Fix:** Minor — consider adding analytical variance forecast option.

---

### hmm.py (B+)

**Strengths:** Multiple random restarts avoid local optima. Feature standardization. Clean NamedTuple with feature stats for new data.

**Gaps:**
1. Only 3 features — could benefit from credit spread, yield curve slope.
2. Default to Bull on missing data is biased.
3. State labeling assumes sorted mean returns = Crisis/Bear/Bull — edge cases could mislabel if two states have similar means.
4. No online updating — must refit from scratch.

**Fix:** Add credit spread feature. Handle degenerate state labeling. Consider sticky HMM or HSMM for more realistic regime durations.

---

## Missing Modules (Documented in CLAUDE.md but Not Found)

| Module | Status | Impact |
|--------|--------|--------|
| `drift_detector.py` | Listed in CLAUDE.md, not in codebase | PSI + KS drift detection not available |
| DCC-GARCH | Phase 2 roadmap, not implemented | Multi-asset correlation dynamics missing |
| Black-Litterman | Phase 3, not in portfolio_engine | No view-based portfolio optimization |
| HRP | Phase 3, not in portfolio_engine | No hierarchical risk parity |
| Conformal prediction | In engine/validation/metrics.py but not integrated into services | No prediction intervals on crash model |

---

## Top 10 Fixes by Priority

| # | Module | Issue | Impact | Effort |
|---|--------|-------|--------|--------|
| 1 | portfolio_engine | No BL/HRP/Ledoit-Wolf — just static templates | Portfolio builder is the weakest competitive differentiator | 8hr |
| 2 | monte_carlo | Block bootstrap inner loop is pure Python O(n*m) | Simulation speed bottleneck for 10K paths | 2hr |
| 3 | stock_analyzer | Return computation sums instead of compounds; 3K sims | Incorrect statistics shown to users | 1hr |
| 4 | risk_scorer | VIX floor `.where()` chain semantics potentially confusing | Risk score accuracy | 1hr |
| 5 | regime_detector | O(n) Python loop; no HMM integration | Slow + two parallel regime systems | 3hr |
| 6 | crash_model | `fillna(0)` on LR features; calibration data reuse | Violates project rule; overfits calibration | 2hr |
| 7 | config | `risk_free_rate` not centralized | 3+ modules each hardcode 0.04 | 1hr |
| 8 | signal_engine | "Valuation" signal uses VIX not actual valuation | Misleading signal composition | 2hr |
| 9 | data_fetcher | `bfill()` on entire DataFrame | Subtle data leakage for newer series | 1hr |
| 10 | sector_analyzer | Hardcoded n_sims, crash_freq, sector weights | Inconsistent with config-driven architecture | 1hr |

---

## Overall Assessment

**Backend services average grade: B-/B**

The codebase is well-structured with clear separation of concerns, good docstrings, and consistent patterns. The strongest modules are the statistical models (GARCH, HMM), config management, and the cache layer. The weakest area is portfolio construction, which is still template-based without the PyPortfolioOpt integration that would differentiate Aegis from competitors. The Monte Carlo engine is methodologically sound but has performance bottlenecks. The signal engine and backtesting harness are functional but need more rigorous validation methodology.

Key strengths vs. competitors:
- Jump-diffusion MC with Merton compensator (better than basic GBM)
- Multi-model crash prediction with isotonic calibration (better than single-model)
- 9-factor composite risk score with dual z-score (novel)
- SHAP explainability for every prediction (rare in open-source)

Key gaps vs. institutional practice:
- No proper portfolio optimization (BL, HRP, mean-variance with constraints)
- No DCC-GARCH for multi-asset correlation
- No conformal prediction intervals
- Signal engine not rigorously backtested with proper methodology
- Several hardcoded values violating the config-driven architecture principle
