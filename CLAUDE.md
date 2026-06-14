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
- Options-implied intelligence (IV skew, put/call ratio, VIX term structure, max pain)
- Earnings intelligence (surprise history, beat rate, growth metrics, estimate revisions)
- Drift-aware predictions (auto-discounts crash model when features drift out-of-distribution)
- Cross-asset tail dependence and contagion analysis
- Signal backtesting harness (walk-forward hit rates, Sharpe comparison)
- Retirement planner with compound growth projections
- Net liquidity tracker (Fed balance sheet: WALCL - TGA - RRP)
- Fama-French 5-factor decomposition (institutional-grade factor analysis)
- Historical stress testing (GFC, COVID, dot-com, Black Monday, rate shock scenarios)
- Cross-sectional momentum ranking (relative strength across 150+ stocks)
- Economic surprise index (FRED actual vs trend consensus)
- Cox Proportional Hazards survival model for crash timing
- Bayesian changepoint detection (Adams & MacKay 2007 BOCPD)
- Isolation Forest anomaly detection for model confidence
- Monthly crash timeline (60-month forward probability curve)
- Copula-based tail dependence (Clayton, Gumbel, Frank, Student-t with AIC selection)
- Liquidity risk analytics (Amihud illiquidity, Roll spread, Kyle's Lambda, LVaR)
- Denoised covariance matrix (Marchenko-Pastur Random Matrix Theory)
- Advanced portfolio optimization (Mean-CVaR, Risk Parity, Max Diversification via riskfolio-lib)
- Brinson-Fachler performance attribution (allocation, selection, interaction effects)
- Marginal Contribution to Risk (MCTR) for risk budgeting
- FF5 + Momentum (6-factor) model with PCA residual analysis (Axioma hybrid)
- Insider trading signal (Finnhub + SEC Form 4, cluster buy detection)
- Hypothetical stress scenarios (user-defined macro shocks)
- AI portfolio commentary (Claude/DeepSeek — Bloomberg PORT style)
- Drawdown recovery analysis (depth, duration, recovery time for every drawdown)
- Rolling returns analysis (1Y/3Y/5Y annualized, with rolling Sharpe/Sortino)
- Monte Carlo retirement simulation (contributions, withdrawals, Social Security)
- Safe withdrawal rate calculator (Bengen 4% rule comparison with MC)
- Technical analysis (RSI, MACD, Bollinger Bands, ADX, OBV, Stochastic via `ta` library)
- Portfolio risk number (1-100, Bloomberg PORT-style composite risk score)
- Sector rotation model (multi-timeframe relative strength + business cycle mapping)
- Real-time price snapshots via Polygon.io API
- Conformal prediction intervals for crash probabilities

**What it is NOT:**
- Financial advice — educational tool with disclaimers everywhere
- A trading bot — no execution, no position sizing, no live orders
- Real-time — data refreshes hourly, not tick-by-tick

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14 (App Router), shadcn/ui, Tailwind CSS, Recharts |
| Backend | FastAPI, Python 3.12 |
| ML | LightGBM, scikit-learn (Logistic Regression), SHAP, Isolation Forest |
| Statistical | GJR-GARCH, HMM (3-state), Jump-diffusion Monte Carlo, Copula models |
| Portfolio | riskfolio-lib (CVaR, Risk Parity, HRP, Max Div), PyPortfolioOpt |
| NLP | ProsusAI/FinBERT (sentiment), keyword fallback |
| Technical | `ta` library (RSI, MACD, Bollinger, ADX, OBV, Stochastic, ATR) |
| Data | Yahoo Finance (yfinance), FRED (fredapi), GDELT, Kenneth French, Polygon.io |
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
│   ├── routers/                 # 13 API routers (30+ endpoints)
│   ├── services/                # 44 business logic modules
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
│   │   ├── options_intelligence.py # IV skew, P/C ratio, VIX term structure, max pain
│   │   ├── earnings_intelligence.py # Earnings surprises, growth, analyst estimates
│   │   ├── tail_risk.py         # CVaR, Sortino, Calmar, tail concentration
│   │   ├── tail_dependence.py   # Cross-asset tail dependence (copula)
│   │   ├── backtest.py          # Walk-forward signal backtesting
│   │   ├── savings_calculator.py# Compound growth projections
│   │   ├── data_quality.py      # Staleness, range, completeness checks
│   │   ├── net_liquidity.py     # Fed balance sheet tracker
│   │   ├── return_model.py      # Quantile return predictor (10th/50th/90th)
│   │   ├── external_validator.py# LEI/SLOOS/Fed cross-checks
│   │   ├── regime_validator.py  # Multi-check regime confirmation
│   │   ├── drift_detector.py    # PSI + KS feature drift detection
│   │   ├── signal_optimizer.py  # Legacy signal computation
│   │   ├── systemic_risk.py     # Turbulence index + absorption ratio (Kritzman)
│   │   ├── bubble_detector.py   # LPPL bubble detection (Sornette)
│   │   ├── fundamentals.py      # SEC EDGAR 10-K/10-Q financials + Piotroski F-Score
│   │   ├── factor_model.py     # Fama-French 5-factor decomposition (Kenneth French Data Library)
│   │   ├── stress_testing.py   # Historical crisis scenario replay (6 scenarios: GFC, COVID, etc.)
│   │   ├── cross_sectional_momentum.py  # Relative strength ranking across stock universe
│   │   ├── economic_surprise.py  # Economic data surprise index (actual vs trend from FRED)
│   │   ├── survival_model.py   # Cox Proportional Hazards crash timing (lifelines)
│   │   ├── anomaly_detector.py # Isolation Forest + Bayesian changepoint detection (BOCPD)
│   │   ├── crash_timeline.py   # Monthly crash probability out 60 months (MC-based)
│   │   ├── liquidity_risk.py  # Amihud illiquidity, Roll spread, Kyle's Lambda, LVaR
│   │   ├── copula_tail.py     # Clayton/Gumbel/Frank/t-copula tail dependence (AIC selection)
│   │   ├── covariance.py      # Marchenko-Pastur denoised covariance (Random Matrix Theory)
│   │   ├── portfolio_optimizer.py # Mean-CVaR, Risk Parity, Max Diversification, HRP (riskfolio-lib)
│   │   ├── insider_trading.py  # Insider buy/sell signal (Finnhub + SEC Form 4)
│   │   ├── trends_sentiment.py # Google Trends fear/greed proxy (pytrends)
│   │   ├── attribution.py     # Brinson-Fachler attribution + MCTR risk decomposition
│   │   ├── technical_analysis.py # RSI, MACD, BB, ADX, OBV, patterns (ta lib)
│   │   ├── polygon_client.py  # Polygon.io real-time quotes, intraday bars
│   │   ├── risk_number.py     # Bloomberg PORT-style portfolio risk number (1-100)
│   │   ├── sector_rotation.py # Multi-timeframe relative strength + business cycle
│   │   ├── drawdown_analyzer.py # Drawdown recovery analysis + rolling returns
│   │   ├── retirement_mc.py   # Monte Carlo retirement sim + safe withdrawal rate
│   │   └── volatility_analytics.py # Bloomberg-style vol cone, GARCH forecast, regime
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

# Run fast backend tests (~14 min, ~2460 tests; OFFLINE + un-hangable)
# The fast suite is network-BLOCKED (backend/tests/conftest.py) and has a hard
# per-test timeout (pytest.ini) — a non-slow test can never hit the live network
# or hang the suite. Any network call in a unit test is a bug → mark it `slow` or mock it.
python -m pytest backend/tests/ -v -m "not slow"

# Run ALL backend tests (~25 min, slow tests need network)
python -m pytest backend/tests/ -v

# Run autonomous R&D lab (overnight, opus model)
python lab/rd_loop.py --cycles 60 --model opus

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
| Signal Engine | `test_signal_engine.py` | 79 | Fast |
| Options Intelligence | `test_options_intelligence.py` | 10 | Fast |
| Earnings Intelligence | `test_earnings_intelligence.py` | 7 | Fast |
| Drift Awareness | `test_drift_awareness.py` | 17 | Fast |
| Regime Accuracy | `test_regime_accuracy.py` | 5 | Fast |
| Risk Stress | `test_risk_stress.py` | 6 | Fast |
| Crash Calibration | `test_crash_calibration.py` | 2 | Fast |
| Tail Risk | `test_tail_risk.py` | varies | Fast |
| Tail Dependence | `test_tail_dependence.py` | varies | Fast |
| Routers | `test_routers.py` | varies | Fast |
| Edge Cases (MC params) | `test_edge_cases.py` | 12 | Fast |
| Stock Stress (8 tickers) | `test_stress_stocks.py` | 64 | Slow (network) |
| Portfolio Stress (3 profiles) | `test_stress_portfolio.py` | 10 | Slow (network) |
| Portfolio Projection (MC) | `test_portfolio_projection.py` | 5 | Slow (network) |
| Edge Cases (tickers) | `test_edge_cases.py` | 7 | Slow (network) |
| **Total** | **28+ files** | **1177+** | **~780 fast / ~95 slow** |

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
- Merton (1976) — Jump-diffusion option pricing (jump compensator)
- Ang et al. (2006) — Downside Risk (beta, volatility, drawdown as stock-level risk factors)
- Fama-French (1993, 2015) — Multi-factor models for return attribution

## Autonomous R&D Lab

The `lab/` directory contains an autonomous research loop that runs Claude Code sessions
to improve the engine overnight. See `lab/README.md` for details.

```bash
# Run overnight (45 min per cycle, auto-commits to lab/autonomous-rd branch)
python lab/rd_loop.py --cycles 60 --model opus

# Cheaper/faster cycles
python lab/rd_loop.py --cycles 60 --model sonnet
```

Each cycle: generates engine data (16 collectors including factor model + economic surprise) → builds prompt with competitive intelligence → Claude session (45 min) → targeted tests → before/after comparison → auto-commit. Results in `lab/experiments/cycle_NNN/`.
