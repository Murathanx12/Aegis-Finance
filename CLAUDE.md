# CLAUDE.md — Aegis Finance

## Mission (amended 2026-08-15 — full text in `docs/OPTIMUS_OBJECTIVE.md` §0)

> Build a **self-improving investment intelligence system** whose objective is
> maximising real-world **portfolio utility** — risk-adjusted or deliberately
> risk-seeking by declared choice — using numerical models, LLM reasoning,
> internet-scale information, observed expert behaviour, simulation, and
> continual outcome feedback.

Three deliverables from one system: Murat's own capital · a public open-source
tool others run at *their* utility function · an HKU paper if a novel and
defensible result emerges.

Five rules that follow, and that override habits formed before them:

1. **Investing is a sequential learning problem**, not a bag of independent
   hypothesis tests. The question is *"given what was knowable at t, what action,
   what alternative, what happened, why, and what should change?"*
2. **Explaining a winner afterwards is trivial; finding precursors observable
   beforehand is the research problem.** Every mechanism carries an executable
   precursor that is tested on foreign slices with its parent barred.
3. **The objective is terminal wealth under a declared utility, not
   classification accuracy or raw return.** Every ranked comparison names the
   objective it was computed under. One brain, several personalities
   (preservation / balanced / aggressive / extreme growth).
4. **Study losers as hard as winners** — the informative unit is *winner vs
   matched loser*, never a gallery of survivors.
5. **Maximise information per dollar, not minimise API calls.** Score
   experiments as `P(changes the roadmap) × value of decision improved − cost`.

**The methodology is the guardrail, not the mission.** Pre-registration, MDE,
corpses and matched controls exist to stop a self-learning machine from learning
nonsense — not to conclude that nothing works. Correspondingly: a negative
result requires evidence just as a positive one does, and **a global negative
does not answer a conditional question that was never asked** (scope-aware
verdicts, `docs/HANDOFF_2026-08-16_BRAIN_TO_BUILDER.md` §2).

## THE BOTTLENECK (diagnosed 2026-08-24 — `docs/ROADMAP_2026-08-24_CONNECT_THE_BRAIN.md`)

> All ten arena books declare `selection: composite_top_k` over ONE signal.
> They differ in **portfolio treatment**, not in **alpha source**.

`COMPOSITE_WEIGHTS` is momentum 1.0 + multifactor 1.0 (itself
momentum+insider+revisions) + four 0.5s, and coverage is `{"1": 206, "6": 1}` —
99.5% of names carry exactly one factor, 12-1 momentum. That is why five months
of guardrails did not move the demonstrated edge off 0%.

**So: a new mechanism arrives as its own `PRODUCT_EXPERIMENT` book, never as a
weight in `arena_composite`.** Folding it in hides the only thing being tested —
whether its errors are different errors. A learned router comes *after* several
independent selectors exist, not before.

## THREE LICENCES (adopted 2026-08-23 — `docs/ROADMAP_2026-08-23_PROFIT_FIRST.md`)

> **Research rigour determines what Aegis is allowed to CLAIM. It must not
> determine what Aegis is allowed to TEST in paper.**

One evidence standard had drifted into governing everything, and five months in
the demonstrated edge is 0% partly because every gate that *could* block work
*was* blocking work. There are now three licences; every artefact names one.

| Licence | Permits | Required first |
|---|---|---|
| `PRODUCT_EXPERIMENT` | internal simulation + external **PAPER** brokerage | a frozen strategy contract **before the first decision**: policy hash, timestamp, inputs, costs, fill convention, objective. **No significance gate, no 24-month floor, no preregistration.** |
| `CAPITAL_CANDIDATE` | candidacy for real money | matured forward evidence, realistic costs, calibration, utility improvement, drawdown/ruin bounds. Promotion stays **attended**. |
| `RESEARCH_CLAIM` | "this is alpha" — paper, public skill claim | full preregistration, MDE, multiplicity control, matched controls, holdout. Every standing evidence rule binds. |

**Does NOT relax:** PIT discipline · frozen information states · realistic
costs · immutable policy versions · outcome provenance · no training on future
information · **no LLM authority over real capital** · no backfilled forward
evidence · no mutation of seeded book histories.

**Amended in scope, not repealed:** the 24-month skill floor and CANON §6
("if it isn't pre-registered, it didn't happen") govern **claims**. A
`PRODUCT_EXPERIMENT` needs a frozen strategy contract instead — weaker, still
tamper-evident.

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

**What it is NOT** *(scoped 2026-08-23 — the old wording described a system that
no longer exists; see `docs/ROADMAP_2026-08-23_PROFIT_FIRST.md` §5)*:

- **Financial advice** — educational tool, disclaimers everywhere. Unchanged.
- **Not autonomous over anyone's real money.** The public product never controls
  a user's brokerage capital, and no LLM has authority over real capital
  anywhere in this system.

What it emphatically *does* do internally, and what the old three bullets wrongly
denied:

- **Position sizing** — Kelly, CE-Kelly, inverse-trailing-vol, risk budgeting.
- **Simulated execution** — ten paper books, daily decisions, next-open fills,
  NAV series, transaction costs and slippage; plus an Alpaca **paper** broker
  integration.
- **Intraday perception** — event ingestion may run continuously. Ordinary
  portfolio decisions remain event/decision-driven, not high-frequency; the
  dashboard's own data still refreshes hourly.

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
│   ├── routers/                 # 19 API routers (130+ endpoints)
│   ├── services/                # 100+ business logic modules
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

# Run fast backend tests (~4090 tests; OFFLINE + un-hangable; ~2-7 min on the
# dev machine, measured 2026-08-15 — the old "~20 min" figure predates fixture
# work. The spread is real: the suite competes with whatever else is running.)
# The fast suite is network-BLOCKED (backend/tests/conftest.py) and has a hard
# per-test timeout (pytest.ini). Any network call in a unit test is a bug →
# mark it `slow` or mock it.
#
# TWO CAVEATS, both paid for on 2026-08-12 when the suite hung mid-swarm:
#  1. The block covers Python sockets AND curl_cffi. It did NOT cover curl_cffi
#     until then — which is yfinance's transport, so every yfinance call in the
#     suite was unguarded. `test_network_guard.py` pins both transports; if a
#     dependency moves to a third (a new CFFI/Rust binding), that guard must be
#     extended or this claim silently becomes false again.
#  2. `pytest-timeout` is in requirements but CAN BE ABSENT locally, and when it
#     is, pytest.ini's `timeout` is inert with only a config warning. Verify it
#     is installed before trusting "un-hangable": python -c "import pytest_timeout"
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

## Discipline Skills (.claude/skills/)

Five project skills codify the disciplines that keep getting skipped — invoke
them at their trigger points, don't re-derive the procedure:

| Skill | Trigger |
|---|---|
| `verify-prod-after-deploy` | after every push that deploys (CI gate → commit flip → exercise the changed surface live) |
| `lane-integrity-check` | before/after any change near lanes, lane YAMLs, rebalance, or NAV tables |
| `seed-a-lane` | any new paper lane (attended, env-gated; human flips flags) |
| `pre-register-trial` | before any new signal/strategy/hypothesis accrues or is evaluated on data |
| `silent-fragility-audit` | after adding collectors/fetchers/loaders/try-except; "audit X" requests |

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
- Give every new module a caller, or classify it in
  `backend/services/signal_reachability.py` — the suite fails on an unreachable,
  unclassified module. A collector that feeds nobody must be a red suite, not a
  discovery three weeks later (`detectability_gate` was one for two days)
- Put every headline number in a receipt. `corr = 0.516` lived in prose only and
  turned out to be a filtered subset nobody had named

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
| Research Gym (episodes, charter) | `test_research_gym.py` | 30 | Fast |
| Gym denominators (G1/G2) | `test_gym_regret_denominator.py` | 29 | Fast |
| Autopsy → rule | `test_research_gym_autopsy.py` | 30 | Fast |
| Regret tensor | `test_research_gym_tensor.py` | 9 | Fast |
| **Total** | **44+ files** | **4190+** | **~4090 fast / ~95 slow** (fast count measured 2026-08-15) |

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

## Autonomous R&D Lab — **RETIRED 2026-08-23**

`lab/rd_loop.py` is **not scheduled, not run, and not maintained**. Decision and
reasoning: `docs/DECISION_2026-08-23_RETIRE_LAB.md`. Nothing was deleted; the
abandoned v5 rewrite lives on branch `lab-v5-abandoned`.

**Do not start it.** It last ran 2026-04-17, it auto-commits from autonomous
sessions, and its working tree carried a half-finished rewrite that removed 23
of 27 collectors.

**The arena replaced it** and does the same job with a licence, a seeded
identity, self-grading against matured outcomes, and a daily production run.
The nightly critic loop in `docs/ROADMAP_2026-08-23_PROFIT_FIRST.md` is the
successor to the *idea*.
