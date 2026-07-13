# Session Post-Mortem — 2026-07-14 — Web fixes + rate-limit honesty + daily brief

## The reported symptoms vs the real causes

Murat reported three web errors. Triage found they share two roots:

1. **"Could not analyze MARVELL" (404)** — two causes stacked:
   - No name→ticker resolution existed anywhere; "MARVELL" went straight to
     yfinance, which knows only MRVL.
   - Worse: prod was in a **429 storm** (live warning log showed dozens of
     `Too Many Requests` across stock_analyzer/liquidity/drawdown/options).
     A throttled fetch returned None → the router said 404 "Could not
     analyze" — i.e. **rate limiting was being reported as "invalid
     ticker"**. Amplifier: the stock page fans out to ~20 endpoints and each
     service made its OWN `yf.Ticker()` call for the same symbol (5-6
     uncached history fetches per page view).
2. **SHAP "Crash model not trained"** — honest state (crash_model.pkl held
   per NEGATIVE_RESULTS §6), but presented as a scary error instead of an
   explanation.
3. **"Failed to fetch"** — frontend unreachable-backend case; distinct from
   the 404s; copy improved (dev-only uvicorn hint).

## What shipped (`70d8ed6`)

- **Shared per-ticker fetch** (`data_fetcher.fetch_ticker_history/info`):
  ONE canonical 10y history per ticker per 15 min, sliced per requested
  period; `RateLimited` exception; 90s process-wide breaker after a 429;
  stale-serving while throttled. stock_analyzer, liquidity_risk,
  drawdown_analyzer, options IV-rank all routed through it.
- **Honest status codes:** throttle → 503 + Retry-After (never 404). The
  404 detail now carries a did-you-mean suggestion.
- **Ticker resolver** (`ticker_resolver.py` + `GET /api/stock/resolve`):
  ~150-name alias map (offline) + yf.Search fallback (cached 24h,
  breaker-guarded). The stock page auto-redirects "MARVELL" → MRVL.
- **Daily brief** (`GET /api/news/brief` + dashboard card): market tape in
  one batched download, GDELT geopolitical read, the user's
  watchlist/portfolio tickers (moves + headlines for top movers), LLM
  summary under a FinGPT-Forecaster-style contract (what happened / impact
  on your holdings / risks to watch), spend-guarded with a deterministic
  template fallback. Descriptive-only language enforced in prompt + test.
- **SHAP panel copy:** explains the model is deliberately held and links to
  the fragility composite.
- 19 new tests; 203 affected existing tests green; next build clean.

## Silent-fragility catch (in-session)

First live run of the brief hit GDELT 429 and reported geopolitics as
**"quiet" from the zero-default dict** — fabricated calm, the exact house
failure mode. Fixed: the conflict score is only trusted when
`raw_data.conflict` is non-empty; a failed read is disclosed as
"unavailable (news feed throttled)" and test-pinned
(`test_failed_gdelt_is_disclosed_not_quiet`).

## External-repo survey (for the record)

12 repos surveyed for borrowables. Shipped today: #1 daily-brief pipeline
shape (ZhuLinsen/daily_stock_analysis, MIT) + #2 FinGPT-Forecaster prompt
contract (MIT). Ranked backlog (docs pointer): geopolitical shock surface
(concept only — Fincept is AGPL, zero code), qlib Alpha158 feature formulas
(MIT) for the crash-successor/return models, provider fallback-chain
hardening (Vibe-Trading, MIT), FinBERT validation vs FPB/FiQA benchmarks
(FinGPT, MIT), per-signal historical hit rates in the screener UI,
FinanceDatabase for universe metadata. Rejected: vnpy/StockSharp cores,
Qbot (CC BY-NC-SA), Fincept code (AGPL + damages clause), FinGPT LoRA,
hyperswitch. None of the 12 has a crash-prediction edge over what Aegis
already runs.

## Decisions / guardrail collisions

- **Crash-model retrain NOT reopened.** Murat asked to "fix the crash
  prediction"; the retrain stays held per NEGATIVE_RESULTS §6 (binary
  ≥20%-drawdown label unlearnable — zero crash events in the purged
  validation window). The honest path remains the successor plan
  (severity/exceedance LightGBM, PR-AUC + event windows, pre-register
  TRIAL-CRASH-2 BEFORE first fit) — a dedicated session.
- **Backtest-validation ask → T7 stands.** No free-data backtest can
  certify alpha (survivorship); validation stays forward (PIT IC + NAV
  lanes). Restated to Murat rather than re-run.
- **/api/pi/compare default returns replay-simulation numbers** (13-21%
  total returns) — NOT the forward record. Forward truth is
  /api/pi/track-record & aegis_verified_state (35 days, lanes ±1%,
  mirror -13.3%). Worth a label audit later so nobody quotes replay as
  track record.

## Backlog added

- RL-breaker state as a `/api/health/full` canary (throttled hours are
  currently visible only via 503s + logs).
- Resolver 24h negative-cache can pin a transiently-failed name
  unresolvable for a day.
- Remaining per-service `yf.Ticker()` call sites (news, earnings,
  factor_model, volatility_analytics…) not yet routed through the shared
  fetch — top offenders were done; sweep the rest.
