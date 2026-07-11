# Aegis Finance

Aegis Finance is a free, open-source market-intelligence platform with an unusual spine: it **measures itself in public and tells you when it's wrong**. Every strategy idea is pre-registered before it touches data, tested on live forward paper portfolios (running since 2026-06-08), and published whether it works or not — the failures live in [NEGATIVE_RESULTS.md](NEGATIVE_RESULTS.md), at the top level, where a skeptic finds them first. Around that spine sits a full market dashboard: crash-risk and fragility measurement, Monte Carlo projections, portfolio construction, factor analysis, and a growing set of point-in-time data collectors — all on free data sources.

**This is an educational tool, not financial advice.**

## Live

| Surface | URL |
|---|---|
| Web app | https://aegis-finance-six.vercel.app |
| API | Railway (FastAPI backend, auto-deployed from `main`) |
| Optimus brain showcase | https://optimus-brain-alpha.vercel.app |

## The honesty machine

Most retail finance tools show you a backtest and ask you to trust it. Aegis assumes backtests lie (ours did — see below) and runs the discipline instead:

- **Pre-registered trials.** Every signal, strategy, or overlay gets a written hypothesis, primary metric, decision rule, and earliest decision date *before* it accrues data (`docs/TRIALS/`). If it isn't pre-registered, it didn't happen.
- **Forward paper lanes.** Seven paper portfolios ($100k each) marked to market daily since inception **2026-06-08**: four reference lanes (conservative, balanced-HRP, aggressive, equal-weight control), two book lanes (mirror + conviction), and an ATR exit-overlay lane. NAV accrues only with elapsed time and cannot be cherry-picked.
- **Decision clocks, not vibes.** TRIAL-001 (HRP vs equal-weight) reads out no earlier than **June 2027**. The project makes **no skill claims before 24 months** of forward record. Period.
- **Published negative results.** The signal engine *loses* to buy-and-hold as a timing tool. The 12-month crash model has no skill. LPPLS bubble timing was refuted twice. A survivorship-free backtest universe is not buildable on free data — so no backtested alpha claim here is trustworthy, and we say so. [Read them all.](NEGATIVE_RESULTS.md)
- **Overfitting guards.** Deflated Sharpe, PBO (probability of backtest overfitting), Harvey-Liu thresholds, and purged cross-validation gate every candidate — and even a "pass" goes to human review, never auto-adoption.

## What it does

**Market intelligence**
- Macro risk dashboard: 9-factor composite score from FRED data, regime detection (Bull/Bear/Volatile/Neutral)
- Fragility composite: LPPLS + systemic stress + Sahm rule + turbulence + net liquidity + credit spreads (descriptive — it never fires trades)
- News intelligence (GDELT + FinBERT sentiment), economic surprise index, net liquidity tracker

**Stock analysis**
- Per-ticker Monte Carlo projections (Merton jump-diffusion, GJR-GARCH vol, Student-t innovations)
- SHAP explainability on every prediction — you see *why*, not just *what*
- Screener with signals across 150+ names; options-implied intelligence (IV skew, put/call, max pain); earnings, insider, technicals, valuation

**Portfolio tools**
- Builder: Black-Litterman, Hierarchical Risk Parity, Mean-CVaR, Risk Parity (riskfolio-lib), goal-based templates
- Analytics: Brinson-Fachler attribution, MCTR risk budgeting, FF5+momentum factor decomposition, drawdown recovery, stress testing (GFC, COVID, dot-com replays)
- Retirement: Monte Carlo simulation with contributions/withdrawals, safe-withdrawal-rate calculator

**The forward track record**
- 7 paper lanes with daily NAV, tamper-evident config hashes, and a public track-record API
- Forward information-coefficient trials on selection signals: insider Form 4 clusters, analyst revision momentum, multi-factor composite

**Data collectors (point-in-time, leak-free)**
- SQLite PIT store with `observed_at` stamps so nothing can peek at the future
- Congressional trading disclosures (Senate + House, by disclosure date), **ARK daily fund flows** (6 funds), EDGAR 13F, SEC Form 4 insider filings — all validated forward, never by backtest

**Behavioral guidance**
- Per-position guidance: levels, signals, and nudges against the classic mistakes (selling winners early, averaging into losers)

## What it does NOT do

- **Not financial advice.** Educational tool, disclaimers everywhere, consult a professional.
- **Not a trading bot.** No execution, no live orders, no position sizing for real money.
- **No alpha claims.** The pre-registered clocks haven't matured; until they do, the honest answer to "does it beat the market?" is *we don't know yet, and here's the live experiment that will tell us*. Our own backtest showed the timing signals underperforming buy-and-hold — we published it: [NEGATIVE_RESULTS.md](NEGATIVE_RESULTS.md).
- **Not real-time.** Data refreshes hourly, not tick-by-tick.

## Quickstart

Prerequisites: Python 3.12+, Node.js 20+, a free [FRED API key](https://fred.stlouisfed.org/docs/api/api_key.html).

```bash
git clone https://github.com/Murathanx12/Aegis-Finance.git
cd aegis-finance
cp .env.example .env   # add your FRED_API_KEY

# Backend
cd backend && pip install -r requirements.txt && cd ..
uvicorn backend.main:app --reload --port 8000

# Frontend (new terminal)
cd frontend && npm install && npm run dev
```

Open http://localhost:3000 — API health at http://localhost:8000/api/health.

Or run the full stack with Docker: `docker compose up --build`

### Environment keys

| Key | Required | Enables | Get it |
|-----|----------|---------|--------|
| `FRED_API_KEY` | **Yes** | Macro data (the core) | [fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html) (free) |
| `DEEPSEEK_API_KEY` | No | AI news summaries | [platform.deepseek.com](https://platform.deepseek.com/) |
| `FINNHUB_API_KEY` | No | Extra fundamentals | [finnhub.io](https://finnhub.io/) |
| `FMP_API_KEY` | No | Congressional trades collector | [financialmodelingprep.com](https://financialmodelingprep.com/) |

### Tests

```bash
# Fast suite (~2,500 tests, offline — network calls are blocked by design)
python -m pytest backend/tests/ -m "not slow"

# Everything (slow tests need network)
python -m pytest backend/tests/
```

## Architecture

```
Next.js 14 (Vercel)  ──REST──►  FastAPI (Railway)
                                 ├─ 19 routers / 130+ endpoints
                                 ├─ 100+ services (MC, crash, portfolio, factors…)
                                 ├─ APScheduler → daily lane marks + PIT collectors
                                 └─ SQLite PIT store + paper-lane NAV (persistent volume)
Data: Yahoo Finance · FRED · SEC EDGAR · GDELT · Kenneth French · Polygon · FMP · ARK
```

- **Frontend:** Next.js 14 (App Router), shadcn/ui, Tailwind, Recharts
- **Backend:** FastAPI, Python 3.12, in-memory TTL cache, stateless except the track record
- **ML/stats:** LightGBM, scikit-learn, SHAP, GJR-GARCH, HMM, copulas, riskfolio-lib, FinBERT
- **Track record:** APScheduler marks the paper lanes daily; lane configs are hash-pinned so any tampering is detectable
- **Offline research:** `engine/` (training, purged CV, walk-forward) — not served by the API

## The track record, precisely

| Fact | Value |
|---|---|
| Paper lanes | 7 ($100k each, daily NAV) |
| Inception | 2026-06-08 |
| First decision date | TRIAL-001 (HRP vs EW): June 2027 |
| Skill-claim policy | None before 24 months of forward record |
| Registry | All trials pre-registered in `docs/TRIALS/` + experiment registry |

Replay and comparison endpoints are methodology backtests, not the track record — the policy is written down in `docs/TRACK_RECORD_POLICY.md`.

## Contributing

Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). One house rule above all: nothing touches the paper-lane NAV write path, and no strategy gets evaluated without pre-registration. Deeper docs live in `docs/` (`METHODOLOGY.md`, `STATE_OF_THE_REPO.md`, `CAPABILITY_MATRIX.md`, `BACKLOG.md`).

## License

[MIT](LICENSE)

---

*All outputs are probabilistic estimates with significant uncertainty. Past performance does not guarantee future results. The negative results are not a reason to distrust this project — they are the reason to trust it.*
