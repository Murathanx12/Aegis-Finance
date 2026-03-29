# CLAUDE.md — Aegis Finance

## Project Overview

Aegis Finance is a free, open-source market intelligence web platform. It takes the ML crash prediction engine from V7 (standalone Python, PDF reports) and wraps it in a modern full-stack web app so anyone can access institutional-grade market analysis.

**What it does:**
- Stock projections with Monte Carlo simulation (jump-diffusion, Merton-corrected)
- Crash probability estimation (LightGBM + Logistic Regression, 3/6/12-month horizons)
- Portfolio builder based on investor goals (risk tolerance, time horizon)
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
│   ├── routers/                 # API endpoint definitions (8 routers)
│   │   ├── market.py            # /api/market-status, /api/macro, /api/net-liquidity, /api/data-quality
│   │   ├── crash.py             # /api/crash/prediction (+ external validation), /api/crash/{ticker}
│   │   ├── simulation.py        # /api/simulation/sp500, /api/simulation/scenarios
│   │   ├── stock.py             # /api/stock/{ticker}, /api/stock/{ticker}/shap
│   │   ├── sector.py            # /api/sectors
│   │   ├── portfolio.py         # /api/portfolio/analyze, /api/portfolio/build, /api/portfolio/project
│   │   ├── news.py              # /api/news/market, /api/news/{ticker}
│   │   └── savings.py           # /api/savings/project
│   ├── services/                # Business logic (17 modules)
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
│   │   └── regime_validator.py  # Multi-check regime confirmation
│   └── models/                  # Statistical models + saved ML artifacts
│       ├── garch.py             # GJR-GARCH(1,1)
│       ├── hmm.py               # 3-state Hidden Markov Model
│       └── *.pkl                # Serialized trained models (gitignored)
├── engine/                      # Offline research (not served by API)
│   ├── training/                # Model training scripts
│   │   ├── features.py          # Full 80+ feature builder
│   │   ├── feature_selection.py # LASSO: 208 → 25-30 features
│   │   └── train_crash_model.py # Train + serialize to .pkl
│   └── validation/              # Walk-forward backtesting
│       ├── walk_forward.py      # Expanding window, zero data leakage
│       └── metrics.py           # Brier, BSS, reliability diagrams
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

# Run backend tests
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

## Reference Codebases (READ-ONLY)

Code is being extracted and refactored from two legacy projects:

1. **V6 Full-Stack App** — `C:\Users\mrthn\market-engine-v5` ([GitHub](https://github.com/Murathanx12/market-engine))
   - React + MUI + Recharts frontend, FastAPI + PostgreSQL backend
   - Reference for: API patterns, CORS config, Docker setup, chart patterns

2. **V7 ML Engine** — `C:\Users\mrthn\market-prediction-engine` ([GitHub](https://github.com/Murathanx12/Improved-Engine))
   - 5-model ensemble, 80+ features, walk-forward backtest, jump-diffusion MC
   - Reference for: Monte Carlo (with bug fixes), data pipeline, features, risk scoring, SHAP
   - All bug fixes applied (Bugs 1-24): Merton compensator, scenario rebalancing, leading indicators

**Extraction rule:** Copy fixed code from V7, adapt patterns from V6. Never commit back to legacy repos.

## Engine Bug Fixes (Already Applied in V7)

These fixes are already in the V7 source code. When copying to Aegis, the fixed versions come along:

- **Bug 20:** Jump-diffusion drift compensator (Merton 1976) — `-λk` term in drift
- **Bug 21:** Scenario weights rebalanced — 65% positive/neutral (was 87.5% bearish)
- **Bug 22:** Institutional benchmarks updated to 2026 published values
- **Bug 23:** Leading indicators added (ICSA initial claims, NFCI financial conditions)
- **Bug 24:** Backtest hyperparameters aligned with defaults

## ML Simplification (V7 → Aegis)

| V7 (5 models) | Aegis (2 models) | Reason |
|---------------|-----------------|--------|
| LightGBM | Keep | Best single-model Brier score |
| Logistic Regression | Keep | Better generalization with sparse crashes |
| XGBoost | Drop | Correlated with LightGBM, minimal ensemble lift |
| LSTM | Drop | Slow training, marginal improvement on tabular data |
| TCN | Drop | Same as LSTM — temporal models don't justify cost |
| Cox Survival | Drop | Redundant with LightGBM hazard estimation |
| Meta-Stacker | Drop | Not needed with 2 models |

Feature reduction: 208 → 25-30 via LASSO (run `engine/training/feature_selection.py`).
Target: 3-month crash Brier score ≤ 0.05.

## Rules

### DO
- Put all parameters in `backend/config.py` — never hardcode in service files
- Use `np.random.default_rng(seed)` for reproducibility
- Handle missing libraries with `try/except ImportError` + fallback
- Cache aggressively (1hr TTL for prices, 24hr for historical)
- Return proper HTTP error codes from routers (404, 422, 500)
- Add type hints to all function signatures
- Keep services stateless — no mutable global state except cache

### DO NOT
- Use `fillna(0)` on feature matrices — LightGBM handles NaN natively
- Use `np.random.seed()` (legacy API)
- Hardcode file paths — use `Path(__file__).parent`
- Store portfolio state server-side — portfolio lives in browser localStorage
- Skip the Merton jump compensator in Monte Carlo (Bug 20)
- Add a database — this is a stateless API with in-memory cache

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

## Implementation Sessions (ALL COMPLETE)

| Session | Goal | Status |
|---------|------|--------|
| 1 | Engine Core — config, data_fetcher, monte_carlo, cache, main.py | DONE |
| 2 | ML Pipeline — features, feature_selection, crash_model, training, walk_forward | DONE |
| 3 | Backend API — all services (risk_scorer, regime_detector, garch, hmm, sector_analyzer, stock_analyzer, portfolio_engine, shap_explainer) + all routers | DONE |
| 4 | Frontend Scaffold + Dashboard — Next.js 14, shadcn/ui, dark theme, sidebar, dashboard page | DONE |
| 5 | Frontend — Stock, Crash, Simulation pages | DONE |
| 6 | Frontend — Portfolio, Sectors, Polish + pre-session bug fixes (3 critical, 4 medium) | DONE |
| 7 | Deployment — Dockerfiles, docker-compose, Railway/Vercel configs | DONE |
| 8 | Feature Expansion — News intelligence (GDELT + DeepSeek), retirement planner, enhanced stock detail (analyst/holders/earnings), portfolio projection, 7 critical bug fixes (Merton sign, GARCH persistence, cache thread safety, etc.) | DONE |
| 9 | V6/V7 Code Borrowing — data_quality, net_liquidity, return_model, external_validator, regime_validator; enriched metrics.py with conformal prediction + advanced validation; cache prewarming; frontend updates | DONE |

---

## Healthy Output Ranges (Validation)

When the engine is working correctly:
- **Crash probabilities:** 5%-55% range (not clustered at 20-25%)
- **3m < 6m < 12m crash:** Monotonically increasing by horizon
- **MC 5Y annualized return:** +2% to +8% (aligned with institutional consensus ~5.9%)
- **Sector returns:** Differentiated 20-80% range (not uniform)
- **Brier Score (3m):** ≤ 0.05 (random = 0.25, climatology ~0.12)
- **Risk score:** [-4, +4] range, >2.0 = elevated stress
