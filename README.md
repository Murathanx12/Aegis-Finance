# Aegis Finance

> Free, open-source market intelligence platform. Institutional-grade analysis, accessible to everyone.

Aegis Finance combines machine learning crash prediction, Monte Carlo simulation, and macroeconomic analysis into a modern web dashboard. Every prediction is explainable — SHAP values show exactly which factors drive the model's output.

**This is an educational tool, not financial advice.**

## Features

- **Crash Probability** — ML-predicted probability of a 20%+ drawdown over 3, 6, and 12-month horizons
- **Monte Carlo Projections** — Jump-diffusion simulation with fat tails, regime-aware drift, and institutional consensus anchoring
- **Macro Risk Dashboard** — 9-factor composite risk score with real-time regime classification
- **Sector Analysis** — All 11 S&P 500 sectors ranked by risk-adjusted expected return
- **Stock Analysis** — Per-ticker projections with probability distributions and SHAP explainability
- **Portfolio Builder** — Goal-based allocation using risk tolerance and time horizon

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Frontend (Next.js 14 + shadcn/ui + Recharts)           │
│  Pages: Dashboard, Crash, Simulation, Stocks,           │
│         Sectors, Portfolio                               │
└──────────────────────┬──────────────────────────────────┘
                       │ REST API
┌──────────────────────▼──────────────────────────────────┐
│  Backend (FastAPI)                                       │
│  ┌──────────┐ ┌───────────┐ ┌──────────┐ ┌──────────┐  │
│  │Data      │ │Monte Carlo│ │Crash     │ │Risk      │  │
│  │Fetcher   │ │Simulator  │ │Model     │ │Scorer    │  │
│  │(yfinance │ │(Merton    │ │(LightGBM │ │(9-factor │  │
│  │+ FRED)   │ │ jump-diff)│ │+ Logistic│ │ z-score) │  │
│  └──────────┘ └───────────┘ └──────────┘ └──────────┘  │
└─────────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites
- Python 3.12+
- Node.js 20+
- [FRED API key](https://fred.stlouisfed.org/docs/api/api_key.html) (free)

### Local Development

```bash
# Clone
git clone https://github.com/Murathanx12/Aegis-Finance.git
cd aegis-finance

# Environment
cp .env.example .env
# Edit .env → add your FRED_API_KEY

# Backend
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend (new terminal)
cd frontend
npm install
npm run dev
```

Open http://localhost:3000

### Docker

```bash
cp .env.example .env
# Edit .env → add your FRED_API_KEY
docker compose up --build
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/market-status` | Current regime, VIX, risk score |
| GET | `/api/macro` | FRED macro indicators |
| GET | `/api/crash/prediction` | 3m/6m/12m crash probabilities |
| GET | `/api/crash/{ticker}` | Ticker-specific crash analysis |
| GET | `/api/simulation/sp500` | 5Y Monte Carlo projection |
| GET | `/api/simulation/scenarios` | 8-scenario breakdown |
| GET | `/api/stock/{ticker}` | Stock projection + risk metrics |
| GET | `/api/stock/{ticker}/shap` | SHAP feature importance |
| GET | `/api/sectors` | 11-sector ranking |
| POST | `/api/portfolio/analyze` | Portfolio analytics |
| POST | `/api/portfolio/build` | Goal-based allocation |

## Data Sources

| Source | Data | Update Frequency |
|--------|------|-----------------|
| Yahoo Finance | Prices, VIX, sector ETFs, treasuries | Hourly |
| FRED | 22+ macro series (yield curve, unemployment, CPI, NFCI, etc.) | Monthly |

## API Keys

| Key | Required | Cost | Sign Up |
|-----|----------|------|---------|
| `FRED_API_KEY` | Yes | Free | [fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html) |
| `FINNHUB_API_KEY` | No | Free tier | [finnhub.io](https://finnhub.io/) |

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14, shadcn/ui, Tailwind CSS, Recharts |
| Backend | FastAPI, Python 3.12 |
| ML | LightGBM, scikit-learn, SHAP |
| Statistical Models | GJR-GARCH, HMM, Jump-diffusion Monte Carlo |
| Deploy | Vercel (frontend), Railway (backend) |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions and guidelines.

## Methodology

See [ABSTRACT.md](ABSTRACT.md) for the full project abstract including methodology, validation results, and known limitations.

## Disclaimer

Aegis Finance is an **educational tool**. It is **not financial advice**. All predictions are probabilistic estimates with significant uncertainty. Past performance does not guarantee future results. Always consult a qualified financial advisor before making investment decisions.

## License

MIT
