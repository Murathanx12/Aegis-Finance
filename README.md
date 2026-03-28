# Aegis Finance

A free, open-source market intelligence platform that democratizes investing. Features stock projections with Monte Carlo simulation, portfolio building based on investor goals, sector analysis ranked by risk-adjusted returns, and a macro risk dashboard.

Built with Next.js, FastAPI, and LightGBM. Educational tool — not financial advice.

## Architecture

```
aegis-finance/
├── frontend/          # Next.js 14 + shadcn/ui + Tailwind + Recharts
├── backend/           # FastAPI + LightGBM + Monte Carlo
│   ├── routers/       # API endpoint definitions
│   ├── services/      # Business logic (MC, risk, crash model, etc.)
│   └── models/        # Statistical models (GARCH, HMM) + saved ML models
├── engine/            # Offline research scripts
│   ├── training/      # Model training + feature selection
│   └── validation/    # Walk-forward backtesting (research paper)
└── docs/              # Methodology + API reference
```

## Quick Start

```bash
# Backend
cd backend
pip install -r requirements.txt
cp ../.env.example ../.env  # Add your FRED_API_KEY
uvicorn main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

## API Keys

| Key | Required | Source |
|-----|----------|--------|
| `FRED_API_KEY` | Yes | [FRED API](https://fred.stlouisfed.org/docs/api/api_key.html) (free) |
| `FINNHUB_API_KEY` | No | [Finnhub](https://finnhub.io/) (free tier available) |

## License

MIT
