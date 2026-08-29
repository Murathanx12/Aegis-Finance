# CLAUDE.md LESSONS — the long form (moved out of CLAUDE.md on 2026-08-29)

**Status: TIER 0 supplement.** Every paragraph here was in `CLAUDE.md` until
2026-08-29 and is unchanged; it moved because an 809-line operating file was
being skimmed. The farm's seven lessons, the product feature list, the layout,
the test table and the retired lab live here. `CLAUDE.md` keeps the rules;
this file keeps the receipts behind them.

## THE FARM IS HOW STRATEGIES GET TESTED NOW

`backend/services/portfolio_farm/` — hundreds of virtual $10k portfolios
replayed over one frozen CRSP history (`python -m scripts.portfolio_farm_run`).
516 policies over 2013-2024 in ~7 minutes, versus the arena's one strategy per
calendar day. Policies are identities, not brokerage accounts; a farm winner is
a CANDIDATE for a frozen forward book and never evidence of alpha.

Seven things from it that govern what counts as progress
(`docs/FINDING_2026-08-24_HOLDING_PERIOD.md`):

- **32 YEARS DID NOT RESOLVE IT, AND NO SAMPLE WILL**
  (`docs/FINDING_2026-08-25_THIRTY_TWO_YEARS_DID_NOT_RESOLVE_IT.md`). The
  re-pull tripled the window and the answer got *further* away:

  | | 2013-2024 | 1993-2024 |
  |---|---|---|
  | tracking error | 35.7% | 34.4% |
  | observed excess | 16.64% | **12.36%** |
  | implied t | 1.54 | **2.00** |
  | MDE at 80% power | 30.3% | **17.3%** |
  | **years needed** | 36 | **60.7** |

  `sqrt(T)` halved the standard error exactly as advertised; the effect
  estimate shrank at the same time. The bootstrap 95% CI still contains zero
  ([-0.12%, +25.13%]). **CRSP cannot supply 61 years** — the window starts in
  1993 because there are no open prices before mid-1992. And by decade the
  candidate reads **4.38x / 0.43x / 2.09x**: over 2003-2012 it turned $10,000
  into **$6,813** while the market made 58%. A "years needed" figure computed
  from a window that omits a regime is a lower bound dressed as a target;
- **THE LEVER IS TRACKING ERROR, NOT HISTORY.** `MDE = z*te/sqrt(T)`, and te
  barely moved between the two windows because it is a property of the
  CONSTRUCTION, not the sample — ten names out of five hundred is what makes
  it 34%. At k=50 te is 16.4%, which over 32 years implies an MDE near 8%/yr.
  History is the expensive lever and it is exhausted; breadth is the cheap one
  and it has never been pulled. Caveat, and it is the open question:
  2013-2024 says the excess falls FASTER than te does;
- **ASK WHETHER THE SAMPLE COULD HAVE ANSWERED, BEFORE ASKING WHAT IT SAID.**
  `python -m scripts.portfolio_farm_signal_power` reports, per signal, the
  effect this window could detect at 80% power. On 2013-2024, **zero of
  thirteen non-null signals produced an effect it could resolve** — every
  signals leaderboard the farm has printed is a rank without a resolution
  behind it. The ordering by MDE is the useful part, and it is not the
  terminal-wealth ordering: `liquid` carries t=2.55 at a third of momentum's
  tracking error and needs **13 years** where momentum needs 47;
- **THIRTEEN SIGNALS WERE THIRTEEN VIEWS OF ONE FILE.** Every non-null signal
  in `portfolio_farm/signals.py` read from three quantities — past returns,
  market cap, dollar volume — all columns of `crsp.dsf`. A library like that
  cannot produce an INDEPENDENT selector however many entries it gains,
  because independence is a property of the DATA and not of the formula.
  `portfolio_farm/characteristics.py` (added 2026-08-25) joins WRDS `finratio`
  PIT and registers `value_bm` and `profit_roe`, the first two that are not
  transformations of price. `public_date` is the availability stamp and a
  value may be used STRICTLY AFTER it — `searchsorted(side="right")` there
  would be a lookahead that improves every number and raises nothing.
  **`portfolio_farm/revisions.py` (added 2026-08-25) is the THIRD source and
  the first behavioural one**: IBES consensus for both eras, 5.2M rows, permno
  already joined, registering `rev_breadth` / `rev_magnitude` /
  `rev_dispersion` and the `sell_side_state` composite — components ALWAYS
  registered beside the composite, which is the `arena_composite` lesson as
  code. Both non-price joins go through ONE function,
  `characteristics.join_pit_series`, so there is exactly one place the
  `side="left"` lookahead can be typed wrong;

- **THE FOURTH SOURCE PRICES INSTRUMENTS, NOT STOCKS** (added 2026-08-28,
  `scripts/wrds_pull_etf_option_quotes`, 11,859,415 rows in
  `backend/data/optimus/wrds/optionm_etf_quotes/`). The first three sources all
  describe COMPANIES. `optionm.opprcd` is listed best bid / best offer per
  contract per day, 1996-2025, and it answers a question none of the others can:
  **what did the market CHARGE for a payoff, and did the payoff beat the
  charge?** A structure priced with Black-Scholes at an assumed sigma cannot
  answer that, because the price is the input
  (`docs/FINDING_2026-08-28_THE_CORE_WAS_NEVER_PRICED.md` — a 70%-of-risk
  allocation refuted by this data before it was funded).

  Three traps, all paid for:
  **secids are verified by ROW COUNT, never by ticker match** — `optionm.securd`
  returns four rows for 'SPY' and three carry almost no options (SPY=109820,
  QQQ=107899, IWM=106445, SMH=151720); **`forward_price` is 100% NULL**, so join
  `optionm.secprd` for spot; and **never filter the pull on `delta`** — delta
  moves with the underlying, so a delta band drops the EXIT quotes of trades that
  went wrong and silently deletes the losing tail. Filter on MONEYNESS, which
  the outcome cannot move, and bound DTE by the whole lifecycle rather than by
  the entry;

- **REPRODUCE A KNOWN FACT BEFORE TRUSTING A NOVEL ONE**
  (`python -m scripts.portfolio_farm_calibrate`). Not exact factor returns —
  universes and conventions differ — but the coarse facts a correct join cannot
  violate: high book-to-market must skew SMALLER and be full of banks while the
  low end is biotech and software; high ROE must skew LARGER; net analyst
  breadth must be balanced around zero. **It failed on its first run and the
  bug was mine**: `rev_breadth` was bounded at |1| reasoning that
  `numup + numdown` cannot exceed `numest`. They are a FLOW and a STOCK — an
  analyst may revise twice, revisers may drop coverage — so the bound was
  silently dropping 16,024 rows, 1.52%, and precisely the MOST-REVISED names.
  The signal still "worked" and its leaderboard row looked ordinary. **A bound
  asserted from a formula rather than measured from the data is a filter, and a
  filter on the informative tail is invisible.** A failure here invalidates
  every downstream result from that characteristic, including ones already
  written down;

- **ASK THE CROSS SECTION BEFORE THE PORTFOLIO**
  (`python -m scripts.portfolio_farm_diagnose`,
  `docs/FINDING_2026-08-25_ASK_THE_CROSS_SECTION_FIRST.md`). Every farm result
  before this was `characteristic -> rank -> top-k -> benchmark`, read as a
  statement about the CHARACTERISTIC. It is not one — it entangles signal
  quality, construction, factor exposure and benchmark choice, and when the
  answer disappoints nothing says which ate it. `diagnostics.py` asks first
  whether return moves MONOTONICALLY with the score: rank IC over
  NON-OVERLAPPING dates, a quantile curve, top-minus-bottom, turnover, and a
  holdings census whose age/size percentiles are measured **against the
  eligible set on each date** (against the panel they would report a book of
  ancient mega-caps as "average age"). First run, three results:
  **`profit_roe` is NOT confounded by listing age — I hypothesised it was and
  the test refuted me.** age% is 51.1 at k=20 and **49.5 at k=100**, against the
  age book's 1.9 and 9.9; it never becomes an age book. The 126 years is POWER
  ARITHMETIC on a small excess — +1.53%/yr over a 6.11% paired te, and
  `(2.8*6.11/1.53)^2 = 125`. **So the real tension is CONSTRUCTION: the
  strongest cross-sectional evidence in the project (ic_t 4.18, monotone 0.90,
  32y) produces a WEAK BOOK, and a long-only top-k slice is capturing almost
  none of it.** **The DECILES answer why, and each candidate needs a DIFFERENT
  construction:** `profit_roe` is a STEP (~9%/yr below median, a PLATEAU at
  14.3-14.8 across deciles 7-10), so a top-4% book sits on its flattest part —
  **build it WIDE**; `mom_12_1` (14.1 -> 19.2) and `rev_dispersion`
  (10.6 -> 19.0) are TAILS — **build them NARROW**. That is also the measured
  MECHANISM for "breadth is the cheap lever": flat return across the top
  deciles means widening k cuts te in `MDE = z*te/sqrt(T)` at no cost to the
  numerator. **Ranking signals by ic_t alone gets this backwards** — momentum
  clears the age book by +9.23%/yr on a WEAKER ic_t than ROE.
  **AND A COMPOSITE CAN DILUTE ITS OWN BEST COMPONENT:** top-decile lift is
  `rev_dispersion` +7.6 against `sell_side_state` +2.3, because equal-weight
  z-averaging of a TAIL signal with GRADIENT signals washes the tail out. Check
  any fixed stack against its own best component, not only against the market.
  **`value_bm` fails monotonically in the WRONG
  DIRECTION** (-0.90), so extreme top-k value in a mega-liquid universe selects
  distress and the REVERSED signal is the one to test; and **`size_large`
  carries ic_t 2.35 on 3.6 distinct names per slot**, which only the census can
  say. A high t with a flat quantile curve is one bucket, not an edge;
- **BREADTH is the first screen on a candidate, and the 12-year reading of it
  was itself a regime** (`python -m scripts.portfolio_farm_breadth_power`,
  `docs/FINDING_2026-08-25_BREADTH_WAS_THE_LEVER.md`). Grinold: `IR ~ IC *
  sqrt(breadth)`, so a real cross-sectional signal spread over more names
  should show t RISING. On 2013-2024 every signal fell and peaked at the
  narrowest book. **On 1993-2024 `mom_12_1` reverses** — slope -0.40 becomes
  +0.02, peak t at k=20, which is ALSO its best book by terminal wealth
  ($971k vs $614k at k=10). 2013-2024 was a mega-cap decade in which
  concentration paid. **Every holding-period result on record was computed at
  k=10 and is due a re-run at k=20.**

  It still separates a signal from a description of a decade, which is what it
  is for: `liquid` runs slope -1.11, gone by k=20, negative by k=30 — its whole
  edge is ten names (MSFT 123/124 samples, GOOG 87, AAPL 81). Exactly two
  signals score as scaling on 32 years: `profit_roe` (+0.69) and `mom_12_1`.
  **A rising t on a NEGATIVE excess is not scaling** — it is a loss diluting,
  and it produces an identical slope; the verdict refuses to score it;
- **ASK "BETTER THAN WHAT?" BEFORE "HOW MUCH BETTER?"** Every power check in
  this project compared to the CAP-WEIGHTED MARKET for five months. That asks
  "should I hold this instead of an index" — right for a product, wrong for a
  claim about a signal, because two books can beat the market for the same
  reason and neither of them be the reason.
  `python -m scripts.portfolio_farm_paired_power` compares a book to ANOTHER
  BOOK at the same construction with phases matched pairwise. The first time it
  ran, **both candidates failed the hardest available benchmark**: `profit_roe`
  at k=100 clears the age book by +1.53%/yr and needs **126 years**; `mom_12_1`
  at k=20 clears it by +9.23%/yr and needs **72**.

  **A BASELINE MUST STATE WHAT IT SELECTS.** `equal` was never equal-weighting:
  with every score tied, `top_k` fell through to permno order, so it was **the
  k oldest surviving listings** — a real alternative explanation, because
  high-ROE large caps ARE old listings. It is now `oldest_listing`, scored
  explicitly as `-permno`, with `newest_listing` as the opposite-tail control;
  `Policy(signal="equal")` is REFUSED and names its replacement (refused, not
  silently resolved — a Policy is a frozen hashed record and rewriting its
  signal would break the hash on its own receipt). The rename is
  holdings-identical ONLY because `Panel.permnos` is ascending, which is
  precisely the argument for declaring a score instead of inheriting one.
  **Never let a tie-break decide a research baseline**;
  **Pairing is not automatically the easier test** — it cancels shared market
  exposure and ADDS the difference in holdings (te 5.10% vs market against
  6.11% vs the age book). Which term wins is a fact about overlap, so it is
  measured and printed, never assumed;
- **the instrument moved the answer more than the strategy did, SIX times.**
  Rebalance PHASE is worth up to 3.75x (so every policy runs at multiple
  `phase_offset`s and is reported by its MEDIAN); the DELISTING assumption was
  worth 18x until `crsp.dsedelist` was joined; an implicit-leverage bug in
  the fill step was silently buying with capital locked in unsellable
  positions; breadth read off one phase crowned k=50 when the optimum is
  k=10; and **the panel marked SHARE COUNTS at raw prices, so every split was
  booked as a return** — one reverse split was +36.34% of a single day's
  "excess" and the top session of twelve years for both momentum signals, and
  fixing it moved `liquid` from t=0.26 to t=2.55; and SIXTH, the BENCHMARK —
  five months of power checks against the cap-weighted market said `profit_roe`
  was four months short of resolvable, and one run against an age-matched book
  moved that to 126 years. **Distrust a farm number before you distrust a farm
  result. And split the window before believing any of them —
  `python -m scripts.portfolio_farm_subperiod`;**
- **`crsp.dsedelist` is joined and delisting returns are MEASURED** (97%+
  coverage). 2xx mergers return ~0.0, 5xx performance delists ~-0.20, and 60.5%
  of all events are at or above zero — the old blanket -30% was wrong for two
  thirds of the population, and 12-1 momentum is especially exposed because it
  systematically selects acquisition targets. Every receipt carries
  `n_delist_measured` / `n_delist_assumed`.

**The replayable window is 1993-2024** (32 years) after the 2026-08-25 re-pull
(`python -m scripts.wrds_repull_dsf_early`, whose resume key is COLUMNS rather
than file existence — an existence-keyed queue can never see a partially-pulled
table). Two independent constraints stop at 1993 and neither is fixable:

- CRSP began collecting open prices in **mid-1992**, so `openprc` is 0.0% in
  1990-91 and ~46% in 1992. No open, no next-open fill. `replayable_years`
  gates on COVERAGE, not on the column being present — **a column is not
  data**, and the re-pull would otherwise have certified an empty 1990;
- the early PIT universe carries **243-475 eligible names** in the 32 months
  from 1990-01 to 1992-10, against a top-500 cut, so there the cut IS the
  screen boundary.

Panels longer than ~15 years must pass `reduce_for_universe_n=500`
(`--reduce` on the scripts): the dense 1993-2024 panel is ~4.8 GB, only 28.5%
of permnos ever reach the top 500, and the reduction was verified to produce
**byte-identical NAVs** across four signals, three holding periods, two sizings
and five phases.

**Every farm run carries `n_delist_measured` vs `n_delist_assumed`.** A run
that fell back on most of its exits still has an assumption for a headline; the
receipt has to be able to say so.


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
│   │   ├── volatility_analytics.py # Bloomberg-style vol cone, GARCH forecast, regime
│   │   ├── deepseek_balance.py  # the PROVIDER's own balance — the economic truth on LLM spend
│   │   └── portfolio_farm/      # ASOF_REPLAY + policy farm over CRSP daily
│   │       ├── panel.py         # CRSP dsf -> aligned (date x permno) matrices; refuses thin years
│   │       ├── signals.py       # 16 PIT signals, scalar spec + vectorised twin, two nulls
│   │       ├── policy.py        # frozen hashed strategy record; zero costs is a REFUSAL
│   │       ├── replay.py        # decide at close, fill at next open, costs/dividends/delisting
│   │       ├── metrics.py       # terminal wealth first, then the ratios
│   │       └── farm.py          # run many, rank, attach the nulls to the leaderboard
│   └── models/                  # GJR-GARCH, HMM, saved .pkl models
├── engine/                      # Offline research (not served by API)
│   ├── training/                # features.py, feature_selection.py, labeling.py, fracdiff.py, sample_uniqueness.py
│   ├── validation/              # walk_forward.py, purged_cv.py, metrics.py
│   └── autoresearch/            # Autonomous experiment loop (scaffolded)
└── docs/                        # Research findings, gap analysis, stress tests, improvement log
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
