# CLAUDE.md — Aegis Finance

## Project Overview

Aegis Finance is a free, open-source market intelligence web platform combining ML crash prediction, Monte Carlo simulation, portfolio construction, and macroeconomic analysis into a single web dashboard.

**What it does:**
- Stock projections with Monte Carlo simulation (jump-diffusion, Merton-corrected)
- Crash probability estimation (LightGBM + Logistic Regression, 3/6/12-month horizons)
- Portfolio builder with Black-Litterman, HRP, and template methods (risk tolerance, time horizon, goal)
- Stock screener with Buy/Hold/Sell signals across 30+ stocks
- Sector analysis ranked by risk-adjusted expected returns (11 S&P sectors)
- Macro risk dashboard (9-factor composite score, regime detection, FRED indicators)
- SHAP explainability for every prediction
- News intelligence with GDELT event scoring, FinBERT sentiment, and optional DeepSeek AI summaries
- Retirement planner with compound growth projections
- Net liquidity tracker (Fed balance sheet: WALCL - TGA - RRP)

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
| NLP | ProsusAI/FinBERT (sentiment), keyword fallback |
| Data | Yahoo Finance (yfinance), FRED (fredapi), GDELT |
| AI | DeepSeek (optional, for news summaries) |
| Deploy | Vercel (frontend), Railway (backend), Docker |

## Repository Layout

```
aegis-finance/
├── frontend/                    # Next.js 14 App
│   ├── src/app/                 # App Router pages (12 pages)
│   ├── src/components/          # UI components (shadcn + charts)
│   ├── src/lib/                 # API client, utilities
│   └── src/hooks/               # Data fetching hooks
├── backend/                     # FastAPI
│   ├── main.py                  # App entry + CORS + cache prewarming
│   ├── config.py                # All parameters (scenarios, weights, tickers, thresholds)
│   ├── cache.py                 # In-memory TTL cache
│   ├── routers/                 # 9 API routers
│   ├── services/                # 22 business logic modules
│   │   ├── data_fetcher.py      # Yahoo Finance + FRED unified
│   │   ├── monte_carlo.py       # Jump-diffusion MC (Merton-corrected)
│   │   ├── risk_scorer.py       # 9-factor composite z-score
│   │   ├── regime_detector.py   # Bull/Bear/Volatile/Neutral detection
│   │   ├── crash_model.py       # LightGBM + Logistic crash predictor
│   │   ├── stock_analyzer.py    # Per-ticker projections (beta-adjusted crash freq)
│   │   ├── sector_analyzer.py   # 11-sector factor model
│   │   ├── portfolio_engine.py  # BL + HRP + template + goal-based
│   │   ├── signal_engine.py     # Composite buy/sell signal (config-driven weights)
│   │   ├── sentiment_analyzer.py# FinBERT + keyword fallback sentiment
│   │   ├── shap_explainer.py    # Feature importance computation
│   │   ├── news_intelligence.py # GDELT event scoring
│   │   ├── llm_analyzer.py      # DeepSeek AI integration
│   │   ├── savings_calculator.py# Compound growth projections
│   │   ├── data_quality.py      # Staleness, range, completeness checks
│   │   ├── net_liquidity.py     # Fed balance sheet tracker
│   │   ├── return_model.py      # Quantile return predictor (10th/50th/90th)
│   │   ├── external_validator.py# LEI/SLOOS/Fed cross-checks
│   │   ├── regime_validator.py  # Multi-check regime confirmation
│   │   ├── drift_detector.py    # PSI + KS feature drift detection
│   │   └── signal_optimizer.py  # Legacy signal computation
│   └── models/                  # GJR-GARCH, HMM, saved .pkl models
├── engine/                      # Offline research (not served by API)
│   ├── training/                # features.py, feature_selection.py, labeling.py, fracdiff.py, sample_uniqueness.py
│   ├── validation/              # walk_forward.py, purged_cv.py, metrics.py
│   └── autoresearch/            # Autonomous experiment loop (scaffolded)
└── docs/                        # Research findings, gap analysis, stress tests, improvement log
```

## Commands

```bash
# Backend
cd backend && pip install -r requirements.txt && cd ..
uvicorn backend.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend && npm install && npm run dev

# Run fast backend tests (~35s)
python -m pytest backend/tests/ -v -m "not slow"

# Run ALL backend tests (~5 min, needs network)
python -m pytest backend/tests/ -v

# Build frontend (catches type errors)
cd frontend && npx next build

# Train crash model (offline, ~5-10 min)
python -m engine.training.train_crash_model

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

## Reference Libraries (READ-ONLY)

| Repo | Path | What to use |
|------|------|-------------|
| PyPortfolioOpt | `C:\Users\mrthn\reference-codes\PyPortfolioOpt` | Black-Litterman, HRP, Ledoit-Wolf covariance shrinkage |
| MLFinLab | `C:\Users\mrthn\reference-codes\mlfinlab` | Purged CV, triple-barrier labels, fractional differentiation |
| Autoresearch | `C:\Users\mrthn\reference-codes\autoresearch` | Autonomous experiment loop (3-file contract, ratchet pattern) |

**Installed libraries:** `pyportfolioopt`, `arch` (GARCH), `hmmlearn` (HMM), `transformers` + `torch` (FinBERT)

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
- Use `SimpleImputer(strategy="median")` for sklearn pipelines that can't handle NaN
- Enforce monotonicity on multi-horizon predictions (3m ≤ 6m ≤ 12m)

### DO NOT
- Use `fillna(0)` on feature matrices — LightGBM handles NaN natively; sklearn paths use SimpleImputer
- Use `np.random.seed()` (legacy API)
- Hardcode file paths — use `Path(__file__).parent`
- Store portfolio state server-side — portfolio lives in browser localStorage
- Skip the Merton jump compensator in Monte Carlo
- Add a database — this is a stateless API with in-memory cache
- Use standard k-fold CV on time-series data
- Use basic GBM without fat-tailed innovations for tail risk estimation
- Evaluate calibration metrics on the same data used to fit the calibrator

## Test Suite

| Category | File | Tests | Speed |
|----------|------|-------|-------|
| Monte Carlo | `test_monte_carlo.py` | 14 | Fast |
| Signal Engine | `test_signal_engine.py` | 15 | Fast |
| Regime Accuracy | `test_regime_accuracy.py` | 5 | Fast |
| Risk Stress | `test_risk_stress.py` | 6 | Fast |
| Risk Profile Scoring | `test_stress_portfolio.py` | 4 | Fast |
| Edge Cases (MC params) | `test_edge_cases.py` | 12 | Fast |
| Crash Calibration | `test_crash_calibration.py` | 2 | Fast |
| Portfolio Projection | `test_portfolio_projection.py` | 2 | Fast |
| Stock Stress (8 tickers) | `test_stress_stocks.py` | 64 | Slow (network) |
| Portfolio Stress (3 profiles) | `test_stress_portfolio.py` | 10 | Slow (network) |
| Portfolio Projection (MC) | `test_portfolio_projection.py` | 5 | Slow (network) |
| Edge Cases (tickers) | `test_edge_cases.py` | 7 | Slow (network) |
| **Total** | **9 files** | **152** | **60 fast / 92 slow** |

Run fast tests: `python -m pytest backend/tests/ -v -m "not slow"`

## Healthy Output Ranges (Validation)

When the engine is working correctly:
- **Crash probabilities:** 5%-55% range (not clustered at 20-25%)
- **3m ≤ 6m ≤ 12m crash:** Monotonically increasing by horizon (enforced in code)
- **MC 5Y annualized return:** +2% to +8% (validated against institutional consensus ~5.9%)
- **Per-stock 5Y returns:** 30%-120% range, differentiated by beta and sector
- **Sector returns:** Differentiated 20-80% range (not uniform)
- **Brier Score (3m):** ≤ 0.05 (random = 0.25, climatology ~0.12)
- **Risk score:** [-4, +4] range, >2.0 = elevated stress
- **Walk-forward AUC-ROC:** ≥ 0.70 (random = 0.50)
- **Feature importance:** Leading indicators (ICSA, NFCI, yield curve) should rank above lagging (unemployment)
- **Portfolio projection P10 < median < P90** for all horizons

## Key References

- Lopez de Prado — *Advances in Financial Machine Learning* (purged CV, triple-barrier, fractional differentiation)
- Gu, Kelly, Xiu (2020) — "Empirical Asset Pricing via Machine Learning"
- BIS Working Paper 1250 (2025) — Financial stress prediction with ML
- MRS-MNTS-GARCH (JRFM, 2022) — Regime-switching MC blueprint
