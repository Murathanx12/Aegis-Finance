# CLAUDE.md — Aegis Finance

## Project Overview

Aegis Finance is a free, open-source market intelligence web platform combining ML crash prediction, Monte Carlo simulation, portfolio construction, and macroeconomic analysis into a single web dashboard.

**Competitive position:** Aegis is the only open-source project that integrates ML crash prediction + jump-diffusion Monte Carlo + goal-based portfolio building + SHAP explainability in one self-hostable web app. OpenBB is a terminal (no ML predictions), QuantConnect is backtesting-only, WorldMonitor is display-only (no ML), and Riskfolio-Lib is a library (no UI).

**What it does:**
- Stock projections with Monte Carlo simulation (jump-diffusion, Merton-corrected)
- Crash probability estimation (LightGBM + Logistic Regression, 3/6/12-month horizons)
- Portfolio builder with Black-Litterman, HRP, and template methods (risk tolerance, time horizon)
- Stock screener with Buy/Hold/Sell signals across 30+ stocks
- Sector analysis ranked by risk-adjusted expected returns (11 S&P sectors)
- Macro risk dashboard (9-factor composite score, regime detection, FRED indicators)
- SHAP explainability for every prediction (why the model thinks what it thinks)
- News intelligence with GDELT event scoring and optional DeepSeek AI summaries
- Retirement planner with compound growth projections
- Net liquidity tracker (Fed balance sheet: WALCL - TGA - RRP)
- Data quality monitoring (staleness, range, completeness checks)
- External validation (LEI, SLOOS, Fed Funds, sentiment cross-checks)
- Regime confirmation (200d SMA, breadth, institutional consensus multi-check)

**What it is NOT:**
- Financial advice — educational tool with disclaimers everywhere
- A trading bot — no execution, no position sizing, no live orders
- Real-time — data refreshes hourly, not tick-by-tick

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14 (App Router), shadcn/ui, Tailwind CSS, Recharts |
| Backend | FastAPI, Python 3.12 |
| ML | LightGBM, scikit-learn (Logistic Regression), SHAP |
| Statistical | GJR-GARCH, HMM (3-state), Jump-diffusion Monte Carlo |
| Data | Yahoo Finance (yfinance), FRED (fredapi), GDELT, 22+ macro series |
| AI | DeepSeek (optional, for news summaries) |
| Deploy | Vercel (frontend), Railway (backend), Docker |

## Repository Layout

```
aegis-finance/
├── frontend/                    # Next.js 14 App
│   ├── src/app/                 # App Router pages
│   ├── src/components/          # UI components (shadcn + charts)
│   ├── src/lib/                 # API client, utilities
│   └── src/hooks/               # Data fetching hooks
├── backend/                     # FastAPI
│   ├── main.py                  # App entry + CORS + cache prewarming
│   ├── config.py                # All parameters (scenarios, weights, tickers)
│   ├── cache.py                 # In-memory TTL cache
│   ├── routers/                 # API endpoint definitions (9 routers)
│   │   ├── market.py            # /api/market-status, /api/macro, /api/net-liquidity, /api/data-quality
│   │   ├── crash.py             # /api/crash/prediction (+ external validation), /api/crash/{ticker}
│   │   ├── simulation.py        # /api/simulation/sp500, /api/simulation/scenarios
│   │   ├── stock.py             # /api/stock/{ticker}, /api/stock/{ticker}/shap, /api/stock/screener
│   │   ├── sector.py            # /api/sectors
│   │   ├── portfolio.py         # /api/portfolio/analyze, /api/portfolio/build, /api/portfolio/project
│   │   ├── news.py              # /api/news/market, /api/news/{ticker}
│   │   ├── savings.py           # /api/savings/project
│   │   └── backtest.py          # /api/backtest/walk-forward
│   ├── services/                # Business logic (21 modules)
│   │   ├── data_fetcher.py      # Yahoo Finance + FRED unified
│   │   ├── monte_carlo.py       # Jump-diffusion MC (Merton-corrected)
│   │   ├── risk_scorer.py       # 9-factor composite z-score
│   │   ├── regime_detector.py   # Bull/Bear/Volatile/Neutral detection
│   │   ├── crash_model.py       # LightGBM + Logistic crash predictor
│   │   ├── stock_analyzer.py    # Per-ticker projections
│   │   ├── sector_analyzer.py   # 11-sector factor model
│   │   ├── portfolio_engine.py  # Stateless portfolio analytics
│   │   ├── shap_explainer.py    # Feature importance computation
│   │   ├── news_intelligence.py # GDELT event scoring
│   │   ├── llm_analyzer.py      # DeepSeek AI integration
│   │   ├── savings_calculator.py# Compound growth projections
│   │   ├── data_quality.py      # Staleness, range, completeness checks
│   │   ├── net_liquidity.py     # Fed balance sheet tracker (WALCL - TGA - RRP)
│   │   ├── return_model.py      # Quantile return predictor (10th/50th/90th)
│   │   ├── external_validator.py# Cross-checks vs LEI, SLOOS, Fed, sentiment
│   │   ├── regime_validator.py  # Multi-check regime confirmation
│   │   ├── drift_detector.py    # PSI + KS feature drift detection
│   │   └── signal_optimizer.py  # Buy/Hold/Sell signal engine
│   └── models/                  # Statistical models + saved ML artifacts
│       ├── garch.py             # GJR-GARCH(1,1)
│       ├── hmm.py               # 3-state Hidden Markov Model
│       └── *.pkl                # Serialized trained models (gitignored)
├── engine/                      # Offline research (not served by API)
│   ├── training/                # Model training scripts
│   │   ├── features.py          # Full 80+ feature builder
│   │   ├── feature_selection.py # LASSO: 208 → 25-30 features
│   │   ├── train_crash_model.py # Train + serialize to .pkl
│   │   ├── labeling.py          # Triple-barrier labeling (AFML Ch. 3)
│   │   ├── fracdiff.py          # Fixed-width fractional differentiation
│   │   └── sample_uniqueness.py # Overlapping label weight computation
│   ├── validation/              # Walk-forward backtesting
│   │   ├── walk_forward.py      # Expanding window, zero data leakage
│   │   ├── purged_cv.py         # Purged K-Fold CV with embargo (AFML Ch. 7)
│   │   └── metrics.py           # Brier, BSS, reliability diagrams
│   └── autoresearch/            # Autonomous experiment loop (scaffolded)
│       ├── aegis_prepare.py     # Immutable data pipeline
│       ├── aegis_train.py       # Mutable training config
│       └── aegis_program.md     # Agent constraints
├── docs/                        # Documentation
├── .env.example                 # Required API keys template
├── docker-compose.yml           # Backend + frontend containers
├── ABSTRACT.md                  # Project abstract + methodology
├── CONTRIBUTING.md              # How to contribute
└── README.md                    # Setup + usage guide
```

## Commands

```bash
# Backend
cd backend
pip install -r requirements.txt
cd ..
uvicorn backend.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev

# Run backend tests (fast only — skips network-dependent stress tests)
python -m pytest backend/tests/ -v -m "not slow"

# Run ALL backend tests including stress tests (~3-5 min, needs network)
python -m pytest backend/tests/ -v

# Build frontend (catches type errors)
cd frontend && npx next build

# Train crash model (offline, ~5-10 min)
python -m engine.training.train_crash_model

# Run walk-forward backtest (offline, slow ~30min)
python -m engine.validation.walk_forward

# Docker (full stack)
docker compose up --build
```

## API Keys

| Key | Required | Get it at |
|-----|----------|-----------|
| `FRED_API_KEY` | Yes | https://fred.stlouisfed.org/docs/api/api_key.html (free) |
| `DEEPSEEK_API_KEY` | No | https://platform.deepseek.com/ (free tier, enables AI news summaries) |
| `FINNHUB_API_KEY` | No | https://finnhub.io/ (free tier) |
| `FMP_API_KEY` | No | https://financialmodelingprep.com/ (free tier) |

Copy `.env.example` to `.env` and fill in your keys.

## Reference Libraries (READ-ONLY)

| Repo | Path | What to use |
|------|------|-------------|
| PyPortfolioOpt | `C:\Users\mrthn\reference-codes\PyPortfolioOpt` | Black-Litterman, HRP, Ledoit-Wolf covariance shrinkage |
| MLFinLab | `C:\Users\mrthn\reference-codes\mlfinlab` | Purged CV, triple-barrier labels, fractional differentiation, sequential bootstrap |
| Autoresearch | `C:\Users\mrthn\reference-codes\autoresearch` | Autonomous experiment loop (3-file contract, ratchet pattern) |
| WorldMonitor | `C:\Users\mrthn\reference-codes\worldmonitor` | Dashboard layout patterns, dark theme, card density |

**Installed libraries:** `pyportfolioopt` (use as library), `arch` (GARCH), `hmmlearn` (HMM)
**Read-only repos:** OpenBB (too large to clone — read docs at docs.openbb.co), Riskfolio-Lib (pip install for CVaR optimization)

## Rules

### DO
- Put all parameters in `backend/config.py` — never hardcode in service files
- Use `np.random.default_rng(seed)` for reproducibility
- Handle missing libraries with `try/except ImportError` + fallback
- Cache aggressively (1hr TTL for prices, 24hr for historical)
- Return proper HTTP error codes from routers (404, 422, 500)
- Add type hints to all function signatures
- Keep services stateless — no mutable global state except cache
- Use purged CV with embargo for all ML validation
- Use walk-forward temporal splits (never random k-fold)
- Target composite metric (AUC + Brier + Sharpe + MaxDD), not just Brier alone

### DO NOT
- Use `fillna(0)` on feature matrices — LightGBM handles NaN natively
- Use `np.random.seed()` (legacy API)
- Hardcode file paths — use `Path(__file__).parent`
- Store portfolio state server-side — portfolio lives in browser localStorage
- Skip the Merton jump compensator in Monte Carlo (Bug 20)
- Add a database — this is a stateless API with in-memory cache
- Use standard k-fold CV on time-series data
- Report accuracy without walk-forward validation
- Use basic GBM without fat-tailed innovations for tail risk estimation

## Commit Convention

```
feat: description              # New feature or endpoint
fix: description               # Bug fix
refactor: description          # Code restructuring, no behavior change
docs: description              # Documentation only
test: description              # Test additions or fixes
chore: description             # Dependencies, config, CI
```

---

## Test Suite

| Category | File | Tests | Speed |
|----------|------|-------|-------|
| Monte Carlo | `test_monte_carlo.py` | 14 | Fast |
| Regime Accuracy | `test_regime_accuracy.py` | 5 | Fast |
| Risk Stress | `test_risk_stress.py` | 6 | Fast |
| Risk Profile Scoring | `test_stress_portfolio.py` | 4 | Fast |
| Edge Cases (MC params) | `test_edge_cases.py` | 12 | Fast |
| Stock Stress (8 tickers) | `test_stress_stocks.py` | 64 | Slow (network) |
| Portfolio Stress (3 profiles) | `test_stress_portfolio.py` | 10 | Slow (network) |
| Edge Cases (tickers) | `test_edge_cases.py` | 7 | Slow (network) |
| **Total** | **7 files** | **130** | **43 fast / 87 slow** |

Run fast tests: `python -m pytest backend/tests/ -v -m "not slow"`
Run all tests: `python -m pytest backend/tests/ -v`

## Methodology Roadmap

### Phase 1 — ML Methodology (Critical) — DONE
- Purged cross-validation with embargo periods (MLFinLab reference)
- Walk-forward validation hardening (expanding window, no future leakage)
- Triple-barrier labeling (Lopez de Prado) — replace fixed-threshold crash labels
- Fractionally differentiated features — preserve memory while achieving stationarity
- Sample uniqueness weighting — reduce overfit from overlapping labels

### Phase 2 — Monte Carlo Upgrade — DONE
- GARCH(1,1) with Student-t innovations (upgrade from Gaussian; `arch` library)
- DCC-GARCH for multi-asset correlation dynamics — NOT YET (single-asset only)
- 10,000 paths default (50,000 for tail estimation mode)
- Variance reduction: antithetic variates — DONE
- GARCH-estimated nu passed to MC as Student-t df (with floor of 3)

### Phase 3 — Portfolio Construction — DONE
- Black-Litterman (PyPortfolioOpt drop-in) — DONE
- Hierarchical Risk Parity (HRP) — DONE
- Ledoit-Wolf covariance shrinkage — DONE (replaces sample covariance)
- Goal-based sub-portfolio wrapper — partial (no `goal` parameter yet)

### Phase 4 — Autoresearch Loop — SCAFFOLDED
- Three-file contract: `aegis_prepare.py`, `aegis_train.py`, `aegis_program.md`
- Composite metric: 0.40 x AUC + 0.25 x Brier + 0.20 x Sharpe + 0.15 x MaxDD penalty
- MLflow tracking, drift detection (PSI), automated retraining triggers

### Phase 5 — Data & Distribution
- Additional data: Alpha Vantage, SEC EDGAR filings
- NLP sentiment integration (FinBERT or similar)
- Community: Reddit r/algotrading, Hacker News, GitHub Discussions
- Free hosting: Vercel (frontend) + Railway/Render free tier (backend)

## Deep Research Findings (2026-03-31)

Comprehensive research docs are in `docs/`:
- `DEEP_RESEARCH_FINDINGS.md` — Market snapshot, institutional forecasts, Aegis alignment
- `DEEP_RESEARCH_FINDINGS_ACADEMIC.md` — Academic ML + MC best practices (2024-2026 papers)
- `DEEP_RESEARCH_FINDINGS_INDUSTRY.md` — Robo-advisor methodology, FinBERT, caching patterns
- `GAP_ANALYSIS.md` — All 23 backend modules graded A-F with specific fix suggestions
- `GAP_ANALYSIS_ENGINE_FRONTEND.md` — Engine + frontend gap analysis
- `STRESS_TEST_RESULTS.md` — 30-stock stress test results
- `STRESS_TEST_PORTFOLIOS.md` — Portfolio profile + edge case results
- `IMPROVEMENT_LOG.md` — Iteration 1 + 2 findings, fixes, and priorities

## Key References

- Lopez de Prado — *Advances in Financial Machine Learning* (purged CV, triple-barrier, fractional differentiation)
- Gu, Kelly, Xiu (2020) — "Empirical Asset Pricing via Machine Learning" (ML in finance benchmark)
- BIS Working Paper 1250 (2025) — Financial stress prediction with ML
- MRS-MNTS-GARCH (JRFM, 2022) — Regime-switching MC blueprint

---

## Healthy Output Ranges (Validation)

When the engine is working correctly:
- **Crash probabilities:** 5%-55% range (not clustered at 20-25%)
- **3m < 6m < 12m crash:** Monotonically increasing by horizon
- **MC 5Y annualized return:** +2% to +8% (aligned with institutional consensus ~5.9%)
- **Sector returns:** Differentiated 20-80% range (not uniform)
- **Brier Score (3m):** ≤ 0.05 (random = 0.25, climatology ~0.12)
- **Risk score:** [-4, +4] range, >2.0 = elevated stress
- **Walk-forward AUC-ROC:** ≥ 0.70 (random = 0.50)
- **Feature importance:** Leading indicators (ICSA, NFCI, yield curve) should rank above lagging (unemployment)
