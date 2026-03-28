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
| Data | Yahoo Finance (yfinance), FRED (fredapi), 22+ macro series |
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
│   ├── main.py                  # App entry + CORS + lifespan
│   ├── config.py                # All parameters (scenarios, weights, tickers)
│   ├── cache.py                 # In-memory TTL cache
│   ├── routers/                 # API endpoint definitions
│   │   ├── market.py            # /api/market-status, /api/macro
│   │   ├── crash.py             # /api/crash/prediction, /api/crash/{ticker}
│   │   ├── simulation.py        # /api/simulation/sp500, /api/simulation/scenarios
│   │   ├── stock.py             # /api/stock/{ticker}, /api/stock/{ticker}/shap
│   │   ├── sector.py            # /api/sectors
│   │   └── portfolio.py         # /api/portfolio/analyze, /api/portfolio/build
│   ├── services/                # Business logic
│   │   ├── data_fetcher.py      # Yahoo Finance + FRED unified
│   │   ├── monte_carlo.py       # Jump-diffusion MC (Merton-corrected)
│   │   ├── risk_scorer.py       # 9-factor composite z-score
│   │   ├── regime_detector.py   # Bull/Bear/Volatile/Neutral detection
│   │   ├── crash_model.py       # LightGBM + Logistic crash predictor
│   │   ├── stock_analyzer.py    # Per-ticker projections
│   │   ├── sector_analyzer.py   # 11-sector factor model
│   │   ├── portfolio_engine.py  # Stateless portfolio analytics
│   │   └── shap_explainer.py    # Feature importance computation
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
uvicorn main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev

# Run backend tests
cd backend && python -m pytest tests/ -v

# Train crash model (offline)
cd engine && python -m training.train_crash_model

# Run walk-forward backtest (offline, slow ~30min)
cd engine && python -m validation.walk_forward

# Docker (full stack)
docker compose up --build
```

## API Keys

| Key | Required | Get it at |
|-----|----------|-----------|
| `FRED_API_KEY` | Yes | https://fred.stlouisfed.org/docs/api/api_key.html (free) |
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

## Implementation Sessions

### Session 1: Engine Core (Data Pipeline + Monte Carlo)
**Goal:** Working data fetch and Monte Carlo simulation, verified with tests.

**Steps:**
1. `backend/config.py` — Convert V7 `engine_config.yaml` to Python dict (scenarios, tickers, FRED series, weights, simulation params). Include `get_institutional_return()` helper.
   - Source: `C:/Users/mrthn/market-prediction-engine/engine_config.yaml`

2. `backend/services/data_fetcher.py` — Merge V7's Yahoo + FRED fetchers into one `DataFetcher` class.
   - Source: `V7/src/finpredict/data/fetchers.py` + `V7/src/finpredict/data/fred_fetcher.py`
   - Keep: publication lag shift, parquet caching, ICSA/NFCI leading indicators

3. `backend/services/monte_carlo.py` — Copy V7's jump-diffusion MC (~756 lines). Already has Merton compensator, block bootstrap, OU vol dynamics, HMM blending.
   - Source: `V7/src/finpredict/simulation/monte_carlo.py`
   - Fix imports only: `from finpredict.config` → `from backend.config`

4. `backend/cache.py` — In-memory TTL cache with `@cached(ttl=3600)` decorator.
   - Pattern from: `V6/backend/main.py` lines 89-100

5. `backend/main.py` — Minimal FastAPI app: CORS, lifespan, `GET /api/health`.

6. **Validate:** Run 10,000 MC sims, verify median terminal return ≈ drift, jump-neutral.

---

### Session 2: ML Pipeline
**Goal:** Simplified crash prediction (LightGBM + Logistic only), trained and serialized.

**Steps:**
1. `engine/training/features.py` — Copy V7's full 80+ feature builder for offline use.
   - Source: `V7/src/finpredict/ml/features.py`

2. `engine/training/feature_selection.py` — LASSO logistic regression to rank and select top 25-30 features. Output: `SELECTED_FEATURES` list.

3. `backend/services/crash_model.py` — Adapt V7's `CrashPredictor` class. Keep LightGBM + Logistic + Platt scaling. Drop XGBoost/LSTM/TCN/Cox/MetaStacker. Add `save_model()`/`load_model()`.
   - Source: `V7/src/finpredict/ml/crash_model.py`

4. `engine/training/train_crash_model.py` — Offline: fetch → features → LASSO → train → serialize to `backend/models/crash_model.pkl`.

5. `engine/validation/walk_forward.py` — Copy V7's walk-forward backtest, simplified to 2 models. Keep for research paper.
   - Source: `V7/src/finpredict/simulation/backtest.py`

6. **Validate:** 3-month crash Brier ≤ 0.05 after feature reduction.

---

### Session 3: Backend API (All Endpoints)
**Goal:** All services and routers operational, tested with sample data.

**Services to build:**
- `backend/services/risk_scorer.py` — 9-factor composite z-score (from `V7/risk/scoring.py`)
- `backend/services/regime_detector.py` — Rule-based + HMM (from `V7/risk/regimes.py`)
- `backend/models/garch.py` — GJR-GARCH (from `V7/models/garch.py`)
- `backend/models/hmm.py` — 3-state HMM (from `V7/models/hmm_regimes.py`)
- `backend/services/sector_analyzer.py` — Factor model (from `V7/models/sectors.py`)
- `backend/services/stock_analyzer.py` — Per-ticker projections (from `V7/models/stocks.py`)
- `backend/services/portfolio_engine.py` — Stateless analytics (new)
- `backend/services/shap_explainer.py` — SHAP TreeExplainer wrapper (new)

**Routers:**
| File | Endpoints |
|------|-----------|
| `routers/market.py` | `GET /api/market-status`, `GET /api/macro` |
| `routers/crash.py` | `GET /api/crash/prediction`, `GET /api/crash/{ticker}` |
| `routers/simulation.py` | `GET /api/simulation/sp500`, `GET /api/simulation/scenarios` |
| `routers/stock.py` | `GET /api/stock/{ticker}`, `GET /api/stock/{ticker}/shap` |
| `routers/sector.py` | `GET /api/sectors` |
| `routers/portfolio.py` | `POST /api/portfolio/analyze`, `POST /api/portfolio/build` |

**Validate:** Every endpoint returns valid JSON with sane value ranges.

---

### Session 4: Frontend — Scaffold + Dashboard
**Goal:** Next.js app with working dashboard page.

**Steps:**
1. Initialize Next.js 14 with TypeScript, Tailwind, App Router
2. Install shadcn/ui + Recharts
3. Dark theme (adapt V6 "Carbon Slate" palette)
4. Layout: sidebar nav (6 pages), responsive (collapses on mobile)
5. Dashboard page (`app/page.tsx`): Market Status banner, Crash Gauge, SP500 Projection chart, Macro Cards, Sector Heatmap

---

### Session 5: Frontend — Stock + Crash + Simulation Pages
**Goal:** Three more pages functional.

**Steps:**
1. `app/stock/[ticker]/page.tsx` — Ticker search, projection chart, SHAP waterfall, risk metrics
2. `app/dashboard/page.tsx` — Full macro dashboard with regime indicator
3. Crash prediction view — 3-horizon probs + SHAP feature breakdown

---

### Session 6: Frontend — Portfolio + Sectors + Polish
**Goal:** All pages complete, polished.

**Steps:**
1. `app/portfolio/build/page.tsx` — Add/remove holdings (localStorage), goal-based allocation
2. `app/portfolio/analyze/page.tsx` — Allocation pie, correlation matrix, VaR/CVaR
3. Sectors page — 11-sector ranking table with expected returns
4. Loading skeletons, error boundaries, responsive testing

---

### Session 7: Deployment
**Goal:** Live on the internet.

**Steps:**
1. `backend/Dockerfile` — python:3.12-slim, uvicorn
2. `docker-compose.yml` — backend + frontend (no database)
3. Deploy backend to Railway (set `FRED_API_KEY`, `PORT=8000`)
4. Deploy frontend to Vercel (set `NEXT_PUBLIC_API_URL`)
5. End-to-end smoke test on live URLs
6. Update README with live links

---

## Healthy Output Ranges (Validation)

When the engine is working correctly:
- **Crash probabilities:** 5%-55% range (not clustered at 20-25%)
- **3m < 6m < 12m crash:** Monotonically increasing by horizon
- **MC 5Y annualized return:** +2% to +8% (aligned with institutional consensus ~5.9%)
- **Sector returns:** Differentiated 20-80% range (not uniform)
- **Brier Score (3m):** ≤ 0.05 (random = 0.25, climatology ~0.12)
- **Risk score:** [-4, +4] range, >2.0 = elevated stress
