# Gap Analysis — Engine & Frontend

*Generated: 2026-03-31*

## Engine Modules

| Module | File | Grade | Does Right | Wrong/Missing | Fix | Priority | Effort |
|--------|------|-------|------------|---------------|-----|----------|--------|
| Features | `engine/training/features.py` | B | 80+ features across 10 categories; backward-looking only; graceful handling of missing columns; FRED macro integration; interaction features | `fillna(0)` at line 317 violates CLAUDE.md rule (LightGBM handles NaN natively); `realized_kurt` uses slow lambda with `raw=False`; no fractional differentiation (Phase 1 roadmap) | Remove `.fillna(0)` at end; use `pd.Series.kurt()` directly; add fracdiff features | P1 | Medium |
| Feature Selection | `engine/training/feature_selection.py` | B | MI + LASSO two-stage pipeline; sensible defaults; min/max feature bounds; balanced class weights | Uses standard 5-fold CV (`cv=5`) instead of purged CV — data leakage risk on time-series; `fillna(0)` on line 72/93 | Replace CV with `PurgedKFold` from MLFinLab; remove `fillna(0)` | P1 | Medium |
| Train Crash Model | `engine/training/train_crash_model.py` | B+ | Clean 7-step pipeline; proper threshold from config; feature selection with fallback; smoke test; top features report | No purged CV (delegates to CrashPredictor); no hyperparameter tuning (hardcoded `n_estimators=800`); no composite metric (AUC+Brier+Sharpe+MaxDD) — just Brier/AUC | Add optuna or grid search; use composite metric from roadmap | P2 | Large |
| Retrain | `engine/training/retrain.py` | A- | Model versioning with timestamps; holdout comparison; improvement threshold gate; CSV audit log; auto-cleanup of old versions; `--force` flag | Holdout evaluation re-evaluates on last 504 rows which overlap with training data (no temporal gap/embargo); no composite metric for comparison — uses only 3m Brier | Add embargo gap between train and holdout; use composite metric | P2 | Small |
| Walk Forward | `engine/validation/walk_forward.py` | B | Expanding window; step every 6 months; proper temporal ordering; uses `compute_metrics`; saves CSV results | Actual outcome lookup on line 136 uses index offset instead of date-based forward lookup (could misalign if data has gaps); no purged CV within each fold; `n_estimators=400` differs from training (800) | Use date-based forward lookup; align hyperparameters with training script | P2 | Medium |
| Metrics | `engine/validation/metrics.py` | A- | Comprehensive: Brier, BSS, AUC, reliability diagram, ECE, conformal prediction, prediction spread check, lead-time accuracy, false alarm rate, missed crash rate, regime-conditional BSS | `regime_conditional_bss` on line 334 passes args in wrong order (`y_pred, y_true` but function expects `y_true, y_pred`) | Fix argument order in `regime_conditional_bss` | P1 | Trivial |
| Validate Fixes | `engine/validation/validate_fixes.py` | B+ | 4 tests covering variance drag, jump compensator, scenario weights, positive returns sanity; clear pass/fail; exit code on failure | Tests are script-based, not pytest — cannot be discovered by `pytest`; tolerance on test 2 (5%) is loose; `get_scenario_configs` may not exist in config.py | Convert to pytest; tighten tolerance | P3 | Small |
| Labeling | *MISSING* | F | N/A | Triple-barrier labeling (AFML Ch. 3) listed in Phase 1 roadmap — not implemented | Create `engine/training/labeling.py` | P1 | Large |
| Fracdiff | *MISSING* | F | N/A | Fractional differentiation (AFML Ch. 5) listed in Phase 1 roadmap — not implemented | Create `engine/training/fracdiff.py` | P1 | Large |
| Sample Uniqueness | *MISSING* | F | N/A | Overlapping label weight computation listed in Phase 1 roadmap — not implemented | Create `engine/training/sample_uniqueness.py` | P1 | Medium |
| Purged CV | *MISSING* | F | N/A | Purged K-Fold with embargo (AFML Ch. 7) listed in Phase 1 roadmap — not implemented | Create `engine/validation/purged_cv.py` | P1 | Medium |
| Autoresearch | *MISSING (entire dir)* | F | N/A | Phase 4 roadmap: 3-file contract (`aegis_prepare.py`, `aegis_train.py`, `aegis_program.md`) — directory does not exist | Scaffold `engine/autoresearch/` | P3 | Large |

### Detailed Notes per Engine Module

**features.py** — Strongest module in the engine. The 80+ features are well-organized into logical categories, all backward-looking. The `fillna(0)` on line 317 is the most critical issue: it masks missing data that LightGBM can split on natively (NaN-aware). The realized kurtosis computation uses a slow lambda; `pd.Series.kurtosis()` would be faster. No fractional differentiation features means stationary transformations rely solely on pct_change/diff, which destroys long memory.

**feature_selection.py** — Good two-stage pipeline. The critical gap is using standard 5-fold CV inside LASSO, which creates temporal leakage (future data in training folds). The hardcoded `SELECTED_FEATURES` fallback list is a nice safety net. Mutual information uses `fillna(0)` which could distort information scores.

**train_crash_model.py** — Well-structured pipeline with proper logging. Missing hyperparameter search: `n_estimators=800` and `random_state=42` are hardcoded. No early stopping. No composite metric evaluation — only reports Brier and AUC separately.

**retrain.py** — Best-in-class retraining with versioning. The holdout evaluation on `features.iloc[-holdout_size:]` has no embargo gap, meaning training data and holdout may have overlapping crash windows (crash labels look forward 63-252 days).

**walk_forward.py** — Solid expanding-window design. The actual outcome lookup on line 136 uses `crash_targets[horizon].iloc[actual_idx]` — if the index has gaps, this could return the wrong date's label. Should use date-based alignment instead.

**metrics.py** — Most complete module. The `regime_conditional_bss` function on line 334 calls `brier_skill_score(y_pred, y_true)` but the function signature expects `(y_true, y_pred)` — arguments are swapped. This would produce incorrect regime-stratified BSS scores.

**validate_fixes.py** — Good regression tests but not discoverable by pytest. Converting these to proper test functions with `test_` prefix would integrate them into the CI pipeline.

**Missing Modules** — The 4 missing Phase 1 modules (labeling, fracdiff, sample_uniqueness, purged_cv) and the entire Phase 4 autoresearch directory represent the largest gaps in the engine. These are all referenced in CLAUDE.md's methodology roadmap but have no implementation.

---

## Frontend Pages

| Page | File | Grade | Does Right | Wrong/Missing | Fix | Priority | Effort |
|------|------|-------|------------|---------------|-----|----------|--------|
| Dashboard | `src/app/page.tsx` | A | React Query for all 5 data sources; stale times; auto-refresh 5min; live "updated ago" indicator; graceful null handling; error card with retry | None significant — cleanest page in the app | N/A | — | — |
| Outlook | `src/app/outlook/page.tsx` | B | Rich layout: crash gauges, fan chart, scenarios, SHAP, external validation, regime confirmation; React Query for main queries | `TickerCrashCard` sub-component uses `useApi` hook (line 161) instead of React Query — inconsistent caching; fan chart stacking may produce visual artifacts (bands overlap, not envelope) | Migrate `TickerCrashCard` to `useQuery` | P2 | Small |
| Stock Detail | `src/app/stock/[ticker]/page.tsx` | C+ | Comprehensive: 8 metrics, price history, MC range, analyst vs model, SHAP waterfall, consensus, peers, holders, earnings, news | **All 3 API calls use `useApi`** (lines 339-341) instead of React Query — no caching, no deduplication, no background refresh; page is 662 lines (too large, should extract components); `use(params)` for async params is correct for Next.js 15 | Migrate to React Query; split into component files | P1 | Medium |
| Stock Search | `src/app/stock/page.tsx` | B+ | Clean search + popular tickers; form submission; simple and focused | No autocomplete/suggestions; no screener integration (screener endpoint exists in backend but no frontend) | Add screener table; debounced search suggestions | P3 | Medium |
| Sectors | `src/app/sectors/page.tsx` | A- | React Query; bar chart + full ranking table; responsive column hiding; summary cards; proper accessibility (`aria-label`, `scope`) | Minor: no sorting capability in the table | Add client-side column sorting | P3 | Small |
| Portfolio | `src/app/portfolio/page.tsx` | C+ | Two tabs (analyze/build); localStorage persistence; per-holding signals; correlation matrix; pie chart; projection chart; risk questionnaire UX | **No React Query** — manual `useState`/`setLoading` pattern throughout (770 lines); per-holding signal colors use light-mode classes (`bg-emerald-50`, `text-emerald-700`) that break in dark mode (line 384-391); empty catch on line 455; projection silently fails | Migrate to React Query mutations; fix dark mode signal colors; handle projection errors | P1 | Large |
| News | `src/app/news/page.tsx` | B+ | React Query; GDELT event score gauge; risk components; tone chart; sector impact; AI summary with sentiment badge; market signal integration | Gauge SVG `strokeDasharray` calculation may clip at extremes; no loading state for individual sections | Minor polish | P3 | Small |
| Retirement | `src/app/retirement/page.tsx` | B | localStorage persistence; inflation-adjusted projections; milestone tracker; target reached/missed feedback; growth chart with 3 lines | No React Query (manual fetch with `useState`); no beginner mode tooltips; no Monte Carlo uncertainty bands (uses deterministic compound growth only) | Migrate to React Query mutation; add MC bands | P2 | Medium |
| Crash (redirect) | `src/app/crash/page.tsx` | B | Clean redirect to `/outlook` | Redirect-only page — search engines may index old `/crash` URL; no 301 status | Use `permanentRedirect` instead of `redirect` | P3 | Trivial |
| Simulation (redirect) | `src/app/simulation/page.tsx` | B | Clean redirect to `/outlook` | Same as crash — should be permanent redirect | Use `permanentRedirect` | P3 | Trivial |
| About | `src/app/about/page.tsx` | A- | Methodology, chart guide, limitations, data sources, credits, disclaimer; well-organized static content | No link to GitHub repo; methodology section is static (could pull from backend health/version endpoint) | Add GitHub link; minor | P3 | Trivial |

### Detailed Notes per Frontend Page

**Dashboard (`page.tsx`)** — The gold standard page. All 5 queries use React Query with proper `queryKey`, `staleTime`, and `refetchInterval`. Error handling aggregates all query errors into a single `ErrorCard`. The "updated X ago" timer is a nice UX touch.

**Outlook (`outlook/page.tsx`)** — Combines crash, simulation, and scenario analysis into a single unified view. Three main queries use React Query correctly. The `TickerCrashCard` component internally uses the legacy `useApi` hook, creating an inconsistency: the main page data is cached by React Query but per-ticker crash lookups are not. The fan chart has a potential visual issue — the percentile bands use separate `Area` components with `stackId`, but they should form an envelope, not stacked areas.

**Stock Detail (`stock/[ticker]/page.tsx`)** — **The most problematic page.** All 3 data fetches (`getStockAnalysis`, `getStockShap`, `getStockSignal`) use the custom `useApi` hook instead of React Query. This means: (1) no shared cache with other pages, (2) no background refetch, (3) no stale-while-revalidate, (4) no deduplication if component re-renders. The page is also 662 lines — far too large for a single file. It should be split into `StockMetrics`, `StockCharts`, `StockAnalyst`, `StockFundamentals` components.

**Portfolio (`portfolio/page.tsx`)** — **Second most problematic page.** At 770 lines with entirely manual state management (`useState` + `setLoading` + `try/catch`), it misses all React Query benefits. The per-holding signal cards use hardcoded light-mode colors (`bg-emerald-50/50`, `text-emerald-700`) that will look wrong in dark mode. The projection `catch {}` on line 455 silently swallows errors with no user feedback.

**Retirement (`retirement/page.tsx`)** — Functional but basic. Uses manual fetch pattern (no React Query). The deterministic compound growth projection (no variance/uncertainty) is a significant methodology gap — the backend's `savings_calculator.py` likely just does `FV = PV*(1+r)^n + PMT*((1+r)^n - 1)/r`. Compare this to the portfolio page's MC projection which shows 10th-90th percentile bands.

---

## Frontend Infrastructure

### API Client (`src/lib/api.ts`)
**Grade: B+**
- Clean `fetchAPI` wrapper with Content-Type header and error status parsing
- 19 endpoint functions covering all backend routes
- 34 TypeScript interfaces for API responses — good type coverage
- Missing: request cancellation (AbortController), retry logic at the fetch level, response validation (zod/valibot), request timeout

### Query Keys (`src/lib/query-keys.ts`)
**Grade: A**
- Centralized factory pattern with `as const` for type safety
- Parametric keys for dynamic endpoints (ticker, nSims, etc.)
- Sensible stale times (5min market, 15min stock, 1hr sectors/simulation)
- Well-organized by domain

### Custom Hook — `useApi` (`src/hooks/use-api.ts`)
**Grade: C**
- Legacy hook that should be deprecated in favor of React Query
- Has auto-retry (1 retry on network errors) and friendly error messages — these features should be migrated to a React Query `queryClient` default config
- `deps` array passed directly to `useCallback` with eslint-disable — fragile
- No caching, no deduplication, no background refetch, no stale-while-revalidate
- **Used by: Stock Detail page (3 calls), Outlook page TickerCrashCard (1 call)**

### Beginner Mode Hook (`src/hooks/use-beginner-mode.ts`)
**Grade: B+**
- Clean context-based toggle with localStorage persistence
- Used by `InfoTooltip` component to show simplified explanations
- Minor: no SSR guard on initial `localStorage.getItem` (will throw in SSR)

### React Query Adoption Status

| Page | React Query | useApi | Manual fetch | Status |
|------|-------------|--------|-------------|--------|
| Dashboard | 5 queries | 0 | 0 | Fully migrated |
| Outlook | 3 queries | 1 (TickerCrashCard) | 0 | Partial |
| Sectors | 1 query | 0 | 0 | Fully migrated |
| News | 2 queries | 0 | 0 | Fully migrated |
| Stock Detail | 0 | 3 | 0 | **Not migrated** |
| Portfolio | 0 | 0 | 4 (manual useState) | **Not migrated** |
| Retirement | 0 | 0 | 1 (manual useState) | **Not migrated** |
| Stock Search | 0 | 0 | 0 | Static (no fetch) |
| About | 0 | 0 | 0 | Static (no fetch) |

**Pages still using custom `useApi` hook: 2** (Stock Detail, Outlook/TickerCrashCard)
**Pages using manual useState fetch (worse than useApi): 2** (Portfolio, Retirement)

### Test Coverage Gaps

| Layer | Files | Tests | Coverage |
|-------|-------|-------|----------|
| Backend services | 17+ modules | 4 test files (monte_carlo, crash_calibration, regime_accuracy, risk_stress) | ~20% — no tests for data_fetcher, portfolio_engine, stock_analyzer, sector_analyzer, news_intelligence, savings_calculator, data_quality, net_liquidity, signal_optimizer |
| Engine training | 4 modules | 0 test files | 0% |
| Engine validation | 3 modules | 0 test files (validate_fixes.py exists but not pytest-compatible) | 0% |
| Frontend pages | 11 pages | 0 test files | 0% |
| Frontend hooks | 2 hooks | 0 test files | 0% |
| Frontend API client | 1 module | 0 test files | 0% |

**Total estimated test coverage: ~10%** — well below production quality. The existing 4 backend test files cover only the statistical/ML core. Zero coverage for API routers, engine modules, and frontend.
