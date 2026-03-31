# Aegis Finance

> Free, open-source market intelligence platform combining ML crash prediction, Monte Carlo simulation, and portfolio construction in a web dashboard.

**This is an educational tool, not financial advice.**

## What It Does

- **Crash Probability** — LightGBM + Logistic Regression blend predicting 20%+ drawdown probability over 3, 6, and 12-month horizons. Validated with purged cross-validation and walk-forward backtesting (3m Brier score: 0.046; see [Known Limitations](#known-limitations) for horizon accuracy details).
- **Monte Carlo Projections** — Jump-diffusion simulation (Merton 1976) with GJR-GARCH volatility, Student-t innovations, and antithetic variates. 10,000 paths default. Validated against Goldman Sachs, JPMorgan, and Vanguard 10-year return assumptions ([docs/REALITY_CHECK.md](docs/REALITY_CHECK.md)).
- **Portfolio Builder** — Black-Litterman, Hierarchical Risk Parity (HRP), and template methods with Ledoit-Wolf covariance shrinkage. 5 goal profiles (preservation, income, growth, aggressive growth, retirement). Uses sector ETFs, not individual stock selection.
- **Macro Risk Dashboard** — 9-factor composite risk score from FRED data (yield curve, NFCI, initial claims, VIX, credit spreads, etc.) with regime classification (Bull/Bear/Volatile/Neutral).
- **Stock Analysis** — Per-ticker Monte Carlo projections with beta-adjusted crash frequency, analyst target blending, and SHAP explainability showing which factors drive each prediction.
- **Stock Screener** — 30+ stocks with Buy/Hold/Sell signals, Sharpe ratios, and sector filtering.
- **Sector Analysis** — 11 S&P 500 sectors ranked by risk-adjusted expected return.
- **News Intelligence** — GDELT event scoring with FinBERT sentiment analysis and optional DeepSeek AI summaries.
- **Retirement Planner** — Compound growth projections with inflation adjustment.
- **Net Liquidity Tracker** — Fed balance sheet (WALCL - TGA - RRP) as a market indicator.
- **Data Quality Monitoring** — Automated staleness, range, and completeness checks.
- **External Validation** — Cross-checks crash predictions against LEI, SLOOS, Fed Funds, and Consumer Sentiment.

## What It Is Not

- **Not financial advice** — educational tool with disclaimers on every page
- **Not a trading bot** — no execution, no position sizing, no live orders
- **Not real-time** — data refreshes hourly via Yahoo Finance and FRED, not tick-by-tick

## Comparison to Similar Projects

| Feature | Aegis Finance | OpenBB (60k stars) | WorldMonitor (43k stars) | PyPortfolioOpt (5.5k stars) | QuantConnect LEAN (18k stars) |
|---------|--------------|-------|--------------|----------------|------------|
| ML crash prediction | LightGBM with purged CV | No | No | No | No |
| Monte Carlo simulation | Jump-diffusion + GARCH | No | No | No | Generic |
| Portfolio optimization | BL + HRP + Ledoit-Wolf | No | No | BL + HRP + CLA + more | BL + MVO |
| Web dashboard | Next.js 14 | Commercial product | Next.js | No (library) | Cloud IDE |
| SHAP explainability | Per-stock + per-crash | No | No | No | No |
| Walk-forward validation | Purged k-fold + embargo | N/A | N/A | N/A | Built-in |
| Data sources | 2 (Yahoo Finance, FRED) | 40+ providers | 30+ sources | User-provided | 100+ providers |
| Live trading | No | No | No | No | Yes |
| Fundamental data | No (price + macro only) | Yes (SEC filings, etc.) | Yes | User-provided | Yes |
| Tax optimization | No | No | No | No | No |
| Stars | New project | 60,000 | 43,000 | 5,500 | 18,000 |

Each project has a different focus. OpenBB has broad data coverage (40+ providers vs our 2). QuantConnect supports live trading and backtesting strategies. PyPortfolioOpt has more optimization methods (CLA, CVaR, semicovariance). WorldMonitor covers more data sources globally. Aegis focuses specifically on crash prediction explainability and Monte Carlo projections.

## Known Limitations

- **2 data sources only** (Yahoo Finance, FRED) — institutional platforms use dozens including Bloomberg, Refinitiv, SEC EDGAR
- **No live trading** — display and analysis only, no order execution
- **ML crash prediction is modest** — 3-month horizon Brier score of 0.046 (better than base rate of 0.12), but 12-month predictions show limited improvement over climatological base rates
- **Sector ETF portfolios** — portfolio optimizer builds from ~15 sector/asset-class ETFs, not individual stock selection
- **No fundamental data** — no earnings, balance sheets, or cash flow statements; relies on price and macro data only
- **Single-asset Monte Carlo** — no cross-asset correlation modeling (DCC-GARCH not yet implemented)
- **No tax-loss harvesting** or tax-aware optimization
- **Test coverage ~25%** of backend code (60 fast + 92 slow tests across 9 files); 0% frontend test coverage
- **No mobile optimization** — dashboard designed for desktop browsers
- **GDELT news scoring is metadata-based** — FinBERT adds NLP sentiment but headline-level only, not full-article analysis

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

### Development

```bash
# Start backend dev server (auto-reloads on file changes)
uvicorn backend.main:app --reload --port 8000

# Start frontend dev server (in a separate terminal)
cd frontend
npm run dev
```

### Testing

```bash
# Run fast backend tests (~35s, no network needed)
python -m pytest backend/tests/ -v -m "not slow"

# Run ALL backend tests including stress tests (~5 min, needs network)
python -m pytest backend/tests/ -v

# Build frontend (catches TypeScript errors)
cd frontend && npx next build

# Run frontend linter
cd frontend && npm run lint
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
docker compose up --build          # Build and start full stack
docker compose up --build -d       # Start in background
docker compose down                # Stop all containers
docker compose logs -f backend     # View backend logs
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
| GET | `/api/stock/{ticker}/sentiment` | FinBERT sentiment analysis on recent news |
| GET | `/api/stock/screener` | Top stocks screener with signals |
| GET | `/api/sectors` | 11-sector ranking by risk-adjusted return |
| POST | `/api/portfolio/analyze` | Portfolio analytics (VaR, CVaR, correlation) |
| POST | `/api/portfolio/build` | Goal-based allocation (preservation, income, growth, aggressive, retirement) |
| POST | `/api/portfolio/project` | Monte Carlo portfolio projection |
| GET | `/api/news/market` | Market news with GDELT event scoring + AI summary |
| GET | `/api/news/{ticker}` | Ticker-specific news with AI outlook |
| POST | `/api/savings/project` | Retirement savings projection |

## API Testing (curl)

```bash
curl http://localhost:8000/api/health
curl http://localhost:8000/api/market-status
curl http://localhost:8000/api/crash/prediction
curl http://localhost:8000/api/stock/AAPL
curl http://localhost:8000/api/stock/AAPL/sentiment
curl -X POST http://localhost:8000/api/portfolio/build \
  -H "Content-Type: application/json" \
  -d '{"risk_tolerance":"moderate","time_horizon":10,"investment_amount":10000}'
```

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
| NLP | ProsusAI/FinBERT (sentiment), keyword fallback |
| Data | Yahoo Finance (yfinance), FRED (fredapi), GDELT |
| AI | DeepSeek (optional, for news summaries) |
| Deploy | Vercel (frontend), Railway (backend), Docker |

## Architecture

```
+---------------------------------------------------------+
|  Frontend (Next.js 14 + shadcn/ui + Recharts)           |
|  Pages: Dashboard, Crash, Simulation, Stocks, Screener, |
|         Sectors, Portfolio, News, Retirement, About      |
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
|  |Portfolio | |Sentiment  | |Regime    | |Signal    |  |
|  |Engine    | |Analyzer   | |Validator | |Engine    |  |
|  |(BL+HRP)  | |(FinBERT)  | |(multi)   | |(composite|  |
|  +----------+ +-----------+ +----------+ +----------+  |
+---------------------------------------------------------+
```

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
│   ├── src/app/                 # App Router pages (12 pages)
│   ├── src/components/          # UI components (shadcn + charts)
│   ├── src/lib/api.ts           # API client + TypeScript types
│   └── src/hooks/               # Data fetching hooks
├── backend/                     # FastAPI
│   ├── main.py                  # App entry + CORS + cache prewarming
│   ├── config.py                # All parameters (scenarios, weights, tickers)
│   ├── cache.py                 # In-memory TTL cache
│   ├── routers/                 # 9 API routers
│   ├── services/                # 22 business logic modules
│   ├── models/                  # GJR-GARCH, HMM, saved .pkl models
│   └── tests/                   # 152 tests (60 fast + 92 slow)
├── engine/                      # Offline ML training + validation
│   ├── training/                # Feature builder, LASSO, labeling, fracdiff, uniqueness
│   ├── validation/              # Walk-forward backtest, purged CV, metrics
│   └── autoresearch/            # Autonomous experiment loop (scaffolded)
├── docs/                        # Research findings, gap analysis, stress tests
├── docker-compose.yml           # Full stack containers
└── .env.example                 # Required API keys template
```

## Methodology Status

| Technique | Status | Details |
|-----------|--------|---------|
| Purged CV with embargo | Done | `engine/validation/purged_cv.py` — pre/post embargo, temporal purging |
| Triple-barrier labeling | Done | `engine/training/labeling.py` — Lopez de Prado AFML Ch. 3 |
| Fractional differentiation | Done | `engine/training/fracdiff.py` — FFD with ADF stationarity test |
| Sample uniqueness weighting | Done | `engine/training/sample_uniqueness.py` — temporal decay |
| Student-t MC innovations | Done | GARCH-estimated degrees of freedom fed into jump-diffusion simulation |
| Antithetic variates | Done | Variance reduction in Monte Carlo paths |
| Black-Litterman portfolio | Done | AUM-weighted equilibrium returns + risk tolerance blending |
| HRP portfolio | Done | Position caps + risk tolerance blending |
| Ledoit-Wolf shrinkage | Done | Replaces sample covariance in portfolio computations |
| Goal-based portfolios | Done | 5 profiles: preservation, income, growth, aggressive, retirement |
| FinBERT sentiment | Done | `sentiment_analyzer.py` — ProsusAI/finbert with keyword fallback |
| Drift detection | Done | `drift_detector.py` — PSI + KS test |
| Crash monotonicity | Done | `crash_model.py` — enforced 3m ≤ 6m ≤ 12m in post-processing |
| DCC-GARCH | Not done | Multi-asset dynamic correlation — single-asset MC only |
| Autoresearch loop | Scaffolded | `engine/autoresearch/` — 3-file contract, needs MLflow integration |
| Cross-asset correlation | Not done | Portfolio projection uses aggregate returns, not correlated paths |
| Tax-loss harvesting | Not done | No tax-aware optimization |

## Built With / References

Projects and papers that informed the implementation:

| Resource | What We Used | Link |
|----------|-------------|------|
| PyPortfolioOpt | Black-Litterman API, HRP, Ledoit-Wolf covariance | [github.com/robertmartin8/PyPortfolioOpt](https://github.com/robertmartin8/PyPortfolioOpt) |
| MLFinLab / Lopez de Prado | Purged CV methodology, triple-barrier labeling, fractional differentiation | [github.com/hudson-and-thames/mlfinlab](https://github.com/hudson-and-thames/mlfinlab) |
| Karpathy's autoresearch | Autonomous experiment loop architecture (3-file contract, ratchet pattern) | [github.com/karpathy/autoresearch](https://github.com/karpathy/autoresearch) |
| WorldMonitor | Dashboard design patterns, dark theme reference | [github.com/acatlin/worldmonitor](https://github.com/acatlin/worldmonitor) |
| arch library | GJR-GARCH(1,1) volatility modeling | [github.com/bashtage/arch](https://github.com/bashtage/arch) |
| ProsusAI/finbert | Financial sentiment analysis on news headlines | [github.com/ProsusAI/finBERT](https://github.com/ProsusAI/finBERT) |
| Lopez de Prado (2018) | *Advances in Financial Machine Learning* — purged CV, triple-barrier, fracdiff | Book (Wiley) |
| Gu, Kelly, Xiu (2020) | "Empirical Asset Pricing via Machine Learning" — ML in finance benchmark | [DOI: 10.1093/rfs/hhaa009](https://doi.org/10.1093/rfs/hhaa009) |
| BIS Working Paper 1250 (2025) | Financial stress prediction with tree-based ML | [bis.org/publ/work1250.htm](https://www.bis.org/publ/work1250.htm) |

## Research & Validation

| Document | Contents |
|----------|----------|
| [METHODOLOGY](docs/METHODOLOGY.md) | Full technical methodology — crash model, Monte Carlo, risk scoring, portfolio construction |
| [REALITY_CHECK](docs/REALITY_CHECK.md) | Engine output validated against Goldman Sachs, Wealthfront, Betterment, FRED, Yahoo Finance |

## Free Hosting

| Service | Tier | Use |
|---------|------|-----|
| [Vercel](https://vercel.com) | Free (hobby) | Frontend — auto-deploys from GitHub |
| [Railway](https://railway.app) | Free trial / $5/mo | Backend — supports Docker, auto-deploy |
| [Render](https://render.com) | Free tier | Backend alternative — spins down after inactivity |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions and guidelines.

## Disclaimer

Aegis Finance is an **educational tool**. It is **not financial advice**. All predictions are probabilistic estimates with significant uncertainty. The ML crash model has modest predictive skill at short horizons only. Past performance does not guarantee future results. Always consult a qualified financial advisor before making investment decisions.

## License

MIT
