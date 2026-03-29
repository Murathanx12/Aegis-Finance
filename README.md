# Aegis Finance

> Free, open-source market intelligence platform. Institutional-grade analysis, accessible to everyone.

Aegis Finance combines machine learning crash prediction, Monte Carlo simulation, and macroeconomic analysis into a modern web dashboard. Every prediction is explainable — SHAP values show exactly which factors drive the model's output.

**This is an educational tool, not financial advice.**

## Features

- **Crash Probability** — ML-predicted probability of a 20%+ drawdown over 3, 6, and 12-month horizons
- **Monte Carlo Projections** — Jump-diffusion simulation with fat tails, regime-aware drift, and institutional consensus anchoring
- **Macro Risk Dashboard** — 9-factor composite risk score with real-time regime classification
- **Sector Analysis** — All 11 S&P 500 sectors ranked by risk-adjusted expected return
- **Stock Analysis** — Per-ticker projections with 3-band price expectations, analyst consensus, holders, and earnings
- **Portfolio Builder** — Goal-based allocation with Monte Carlo projection and correlation analysis
- **News Intelligence** — GDELT-powered event scoring with optional DeepSeek AI summaries
- **Retirement Planner** — Compound growth projections with inflation adjustment and milestone tracking
- **Net Liquidity Tracker** — Fed balance sheet (WALCL - TGA - RRP) as a leading market indicator
- **Data Quality Monitoring** — Automated staleness, range, and completeness checks on all market data
- **External Validation** — Cross-checks crash predictions against LEI, SLOOS, Fed Funds, and Consumer Sentiment
- **Regime Confirmation** — Multi-check validation (200d SMA, breadth, institutional consensus) prevents false bear signals

## Architecture

```
+---------------------------------------------------------+
|  Frontend (Next.js 14 + shadcn/ui + Recharts)           |
|  Pages: Dashboard, Crash, Simulation, Stocks,           |
|         Sectors, Portfolio, News, Retirement             |
+------------------------+--------------------------------+
                         | REST API
+------------------------v--------------------------------+
|  Backend (FastAPI)                                      |
|  +----------+ +-----------+ +----------+ +----------+  |
|  |Data      | |Monte Carlo| |Crash     | |Risk      |  |
|  |Fetcher   | |Simulator  | |Model     | |Scorer    |  |
|  |(yfinance | |(Merton    | |(LightGBM | |(9-factor |  |
|  |+ FRED)   | | jump-diff)| |+ Logistic| | z-score) |  |
|  +----------+ +-----------+ +----------+ +----------+  |
|  +----------+ +-----------+ +----------+ +----------+  |
|  |Net       | |External   | |Regime    | |Data      |  |
|  |Liquidity | |Validator  | |Validator | |Quality   |  |
|  +----------+ +-----------+ +----------+ +----------+  |
+---------------------------------------------------------+
```

## Quick Start

### Prerequisites

| Tool | Required? | How to Check |
|------|-----------|-------------|
| Python 3.12+ | Yes | `python --version` |
| Node.js 20+ | Yes | `node --version` |
| Git | Yes | `git --version` |
| [FRED API Key](https://fred.stlouisfed.org/docs/api/api_key.html) | Yes (free) | Sign up at link |
| [DeepSeek API Key](https://platform.deepseek.com/) | Optional | Enables AI news summaries |

### Setup

```bash
# Clone
git clone https://github.com/Murathanx12/Aegis-Finance.git
cd aegis-finance

# Environment variables
cp .env.example .env
# Edit .env -> add your FRED_API_KEY (required)
# Optionally add DEEPSEEK_API_KEY for AI analysis

# Backend
cd backend
pip install -r requirements.txt
cd ..
uvicorn backend.main:app --reload --port 8000

# Frontend (new terminal)
cd frontend
npm install
npm run dev
```

Open http://localhost:3000

Verify backend: http://localhost:8000/api/health

### Train the Crash Model (optional, ~5-10 min)

```bash
python -m engine.training.train_crash_model
```

Creates `backend/models/crash_model.pkl`. Without it, crash prediction returns "model not trained" but everything else works.

### Docker

```bash
cp .env.example .env
# Edit .env -> add your FRED_API_KEY
docker compose up --build
```

## Commands Reference

### Installation

```bash
# Install backend dependencies
cd backend
pip install -r requirements.txt
cd ..

# Install frontend dependencies
cd frontend
npm install
```

### Development

```bash
# Start backend dev server (auto-reloads on file changes)
uvicorn backend.main:app --reload --port 8000

# Start frontend dev server (in a separate terminal)
cd frontend
npm run dev
```

### Building

```bash
# Build frontend for production (also catches TypeScript errors)
cd frontend
npm run build

# Start frontend production server (after building)
cd frontend
npm start
```

### Testing & Linting

```bash
# Run backend tests
python -m pytest backend/tests/ -v

# Run frontend linter
cd frontend
npm run lint
```

### ML Engine (Offline)

```bash
# Train crash prediction model (~5-10 min, creates backend/models/crash_model.pkl)
python -m engine.training.train_crash_model

# Run LASSO feature selection (208 → 25-30 features)
python -m engine.training.feature_selection

# Run walk-forward backtest (~30 min)
python -m engine.validation.walk_forward
```

### Docker

```bash
# Build and start full stack (backend + frontend)
docker compose up --build

# Start in detached mode (runs in background)
docker compose up --build -d

# Stop all containers
docker compose down

# Rebuild a single service
docker compose build backend
docker compose build frontend

# View logs
docker compose logs -f           # all services
docker compose logs -f backend   # backend only
docker compose logs -f frontend  # frontend only
```

### API Testing (curl)

```bash
# Health check
curl http://localhost:8000/api/health

# Market overview
curl http://localhost:8000/api/market-status
curl http://localhost:8000/api/macro
curl http://localhost:8000/api/net-liquidity
curl http://localhost:8000/api/data-quality

# Crash prediction
curl http://localhost:8000/api/crash/prediction
curl http://localhost:8000/api/crash/AAPL

# Simulation
curl http://localhost:8000/api/simulation/sp500
curl http://localhost:8000/api/simulation/scenarios

# Stock & sectors
curl http://localhost:8000/api/stock/AAPL
curl http://localhost:8000/api/stock/AAPL/shap
curl http://localhost:8000/api/sectors

# News
curl http://localhost:8000/api/news/market
curl http://localhost:8000/api/news/AAPL

# Portfolio (POST)
curl -X POST http://localhost:8000/api/portfolio/analyze \
  -H "Content-Type: application/json" \
  -d '{"tickers":["AAPL","MSFT","GOOGL"],"weights":[0.4,0.3,0.3]}'

# Retirement planner (POST)
curl -X POST http://localhost:8000/api/savings/project \
  -H "Content-Type: application/json" \
  -d '{"monthly_contribution":500,"current_savings":0,"current_age":20,"target_age":65}'
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/market-status` | Regime, VIX, risk score, data quality, net liquidity |
| GET | `/api/macro` | FRED macro indicators with 1-month changes |
| GET | `/api/net-liquidity` | Fed net liquidity (WALCL - TGA - RRP) with 52-week history |
| GET | `/api/data-quality` | Data staleness, range, and completeness checks |
| GET | `/api/crash/prediction` | 3m/6m/12m crash probabilities + external validation + regime confirmation |
| GET | `/api/crash/{ticker}` | Beta-adjusted ticker crash analysis |
| GET | `/api/simulation/sp500` | 5Y Monte Carlo projection |
| GET | `/api/simulation/scenarios` | 7-scenario breakdown |
| GET | `/api/stock/{ticker}` | Stock projection, risk metrics, analyst data, holders, earnings |
| GET | `/api/stock/{ticker}/shap` | SHAP feature importance |
| GET | `/api/sectors` | 11-sector ranking by risk-adjusted return |
| POST | `/api/portfolio/analyze` | Portfolio analytics (VaR, CVaR, correlation) |
| POST | `/api/portfolio/build` | Goal-based allocation |
| POST | `/api/portfolio/project` | Monte Carlo portfolio projection |
| GET | `/api/news/market` | Market news with GDELT event scoring + AI summary |
| GET | `/api/news/{ticker}` | Ticker-specific news with AI outlook |
| POST | `/api/savings/project` | Retirement savings projection |

## Data Sources

| Source | Data | Update Frequency |
|--------|------|-----------------|
| Yahoo Finance | Prices, VIX, sector ETFs, treasuries | Hourly (cached) |
| FRED | 22+ macro series (yield curve, unemployment, CPI, NFCI, etc.) | Daily (cached 24hr) |
| GDELT | Global event tone, volume, conflict scores | On request |

## API Keys

| Key | Required | Cost | Sign Up |
|-----|----------|------|---------|
| `FRED_API_KEY` | Yes | Free | [fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html) |
| `DEEPSEEK_API_KEY` | No | Free tier | [platform.deepseek.com](https://platform.deepseek.com/) |
| `FINNHUB_API_KEY` | No | Free tier | [finnhub.io](https://finnhub.io/) |
| `FMP_API_KEY` | No | Free tier | [financialmodelingprep.com](https://financialmodelingprep.com/) |

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14 (App Router), shadcn/ui, Tailwind CSS, Recharts, TanStack React Query |
| Backend | FastAPI, Python 3.12 |
| ML | LightGBM, scikit-learn (Logistic Regression), SHAP |
| Statistical | GJR-GARCH, HMM (3-state), Jump-diffusion Monte Carlo |
| Data | Yahoo Finance (yfinance), FRED (fredapi), GDELT |
| AI | DeepSeek (optional, for news summaries) |
| Deploy | Vercel (frontend), Railway (backend), Docker |

## Deployment

**Backend (Railway):**
1. Create Railway account, connect GitHub repo
2. Set env vars: `FRED_API_KEY`, `PORT=8000`, `ALLOWED_ORIGINS=https://your-frontend.vercel.app`
3. Deploys automatically via `railway.json`

**Frontend (Vercel):**
1. Create Vercel account, import repo, set root to `frontend/`
2. Set env var: `NEXT_PUBLIC_API_URL=https://your-backend.railway.app`
3. Deploys automatically

## Project Structure

```
aegis-finance/
├── frontend/                    # Next.js 14 App
│   ├── src/app/                 # App Router pages (8 pages)
│   ├── src/components/          # UI components (shadcn + charts)
│   ├── src/lib/api.ts           # API client + TypeScript types
│   └── src/hooks/               # Data fetching hooks
├── backend/                     # FastAPI
│   ├── main.py                  # App entry + CORS + cache prewarming
│   ├── config.py                # All parameters (scenarios, weights, tickers)
│   ├── cache.py                 # In-memory TTL cache
│   ├── routers/                 # 8 API routers
│   │   ├── market.py            # market-status, macro, net-liquidity, data-quality
│   │   ├── crash.py             # crash prediction + external validation
│   │   ├── simulation.py        # SP500 projection, scenarios
│   │   ├── stock.py             # per-ticker analysis + SHAP
│   │   ├── sector.py            # 11-sector ranking
│   │   ├── portfolio.py         # analyze, build, project
│   │   ├── news.py              # GDELT + AI news
│   │   └── savings.py           # retirement projection
│   ├── services/                # 17 business logic modules
│   │   ├── data_fetcher.py      # Yahoo Finance + FRED
│   │   ├── monte_carlo.py       # Jump-diffusion MC (Merton-corrected)
│   │   ├── risk_scorer.py       # 9-factor composite z-score
│   │   ├── regime_detector.py   # Bull/Bear/Volatile/Neutral
│   │   ├── crash_model.py       # LightGBM + Logistic crash predictor
│   │   ├── stock_analyzer.py    # Per-ticker projections
│   │   ├── sector_analyzer.py   # 11-sector factor model
│   │   ├── portfolio_engine.py  # Stateless portfolio analytics
│   │   ├── shap_explainer.py    # Feature importance
│   │   ├── news_intelligence.py # GDELT event scoring
│   │   ├── llm_analyzer.py      # DeepSeek AI integration
│   │   ├── savings_calculator.py# Compound growth projections
│   │   ├── data_quality.py      # Staleness, range, completeness checks
│   │   ├── net_liquidity.py     # Fed balance sheet tracker
│   │   ├── return_model.py      # Quantile return predictor
│   │   ├── external_validator.py# LEI/SLOOS/Fed cross-checks
│   │   └── regime_validator.py  # Multi-check regime confirmation
│   ├── models/                  # GJR-GARCH, HMM, saved .pkl models
│   └── tests/                   # 14 tests
├── engine/                      # Offline ML training + validation
│   ├── training/                # Feature builder, LASSO, model training
│   └── validation/              # Walk-forward backtest, metrics (with conformal prediction)
├── docker-compose.yml           # Full stack containers
├── railway.json                 # Backend deployment config
└── .env.example                 # Required API keys template
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions and guidelines.

## Methodology

See [ABSTRACT.md](ABSTRACT.md) for the project abstract and [docs/METHODOLOGY.md](docs/METHODOLOGY.md) for the full technical methodology (research paper foundation) covering:
- Crash probability estimation (LightGBM + Logistic Regression, walk-forward validation)
- Jump-diffusion Monte Carlo (Merton 1976 compensator, GJR-GARCH, HMM)
- 9-factor composite risk scoring
- Scenario framework with dynamic weight adjustment
- External validation and regime confirmation

## Disclaimer

Aegis Finance is an **educational tool**. It is **not financial advice**. All predictions are probabilistic estimates with significant uncertainty. Past performance does not guarantee future results. Always consult a qualified financial advisor before making investment decisions.

## License

MIT
