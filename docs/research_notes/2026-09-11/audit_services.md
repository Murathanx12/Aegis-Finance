# Aegis Desktop Wiring Audit

## Router registration (backend/main.py:517-557)
All routers included with prefix `/api/...` except journal/control which are appended separately (still normal include_router). Desktop mount at `/` happens LAST (main.py:589) via `mount_desktop_frontend()`, gated on `AEGIS_DESKTOP=1` env var, serving `frontend/out` (StaticFiles html=True). CORS origins default to localhost:3000/127.0.0.1:3000 unless `ALLOWED_ORIGINS` env set (main.py:497-502) — desktop app likely runs same-origin (backend serves frontend) so CORS is moot for desktop, but IMPORTANT if the desktop frontend ever calls a *different* port than the one FastAPI bound.

## Router -> services -> source raw grep (to be refined)
- analytics.py (/api/analytics): allocation_backtester, anomaly_detector, conformal_predictor, copula_tail, covariance, crash_timeline, cross_asset_monitor, cross_sectional_momentum, data_fetcher, drawdown_analyzer, economic_surprise, factor_model, fixed_income, liquidity_risk, market_treemap, pair_trading, prediction_confidence, providers, regime_detector, risk_scorer, sector_rotation, stress_testing, survival_model, tail_risk, trends_sentiment, valuation. Mostly yfinance-derived (via data_fetcher) + FRED (fixed_income/valuation). No LLM.
- arena.py (/api/arena): services.arena package (discovery.py uses yfinance). Simulation/paper books, mostly file/sqlite state + yfinance.
- backtest.py (/api/backtest): services.backtest (yfinance via data_fetcher chain likely).
- bond.py (/api/bond): services.bond_analytics (FRED).
- candidates.py (/api/candidates): reads files under backend/data (no live services import at module top — reads local JSON/parquet artifacts). READ-ONLY per comment main.py:542-546.
- control.py (/api/control): services.quiet_subprocess; ALSO (seen later) free_inference/llama_server for /ask, /llama. Desktop control plane — reads always on, mutating routes gated on AEGIS_CONTROL_ENABLED=1 (main.py:556).
- copilot.py (/api/copilot): services.copilot -> uses LLM (DeepSeek) per grep hit in "DeepSeek/LLM users" list.
- correlation.py (/api/correlation): services.tail_dependence (yfinance-derived prices).
- crash.py (/api/crash): anomaly_detector, conformal_predictor, crash_model, data_fetcher, drift_detector, external_validator, regime_detector, regime_validator, shap_explainer, survival_model. yfinance + FRED (via data_fetcher/regime_detector) + local trained model files (crash_model).
- crypto.py (/api/crypto): crypto_market, defi_metrics — likely external crypto APIs (need to check network need).
- drift.py (/api/drift): crash_model, data_fetcher, drift_detector.
- event_intel.py (/api/event-intel): services.event_intel -> SEC/EDGAR + LLM (DeepSeek) for extraction (event_intel.py in DeepSeek list).
- events.py (/api/events): services.edgar_events -> SEC EDGAR (network, no key).
- investment_committee.py (/api/ic): services.investment_committee -> reads local funnel artifact file, degrades gracefully if missing (main.py:897-904 health note).
- journal.py (/api/journal): counterfactual_prices, decision_log, human_thesis, terminal_state_reader — append-only JSONL under backend/data/human_loop + reads execution-repo mirror files. Read-only mostly.
- market.py (/api): anomaly_detector, bubble_detector, conformal_predictor, crash_model, cross_asset_monitor, data_fetcher, data_quality, drawdown_analyzer, drift_detector, economic_surprise, external_validator, macro_indicators, market_dashboard, market_digest, net_liquidity, polygon_client, regime_detector, risk_scorer, sector_rotation, signal_engine, survival_model, systemic_risk, trends_sentiment, volatility_analytics, world_markets. Core market data = yfinance + FRED; polygon_client needs POLYGON_API_KEY (optional paid).
- markets.py (/api/markets): commodity_curves, fx_curves — yfinance + FRED.
- news.py (/api/news): news_intelligence (GDELT, no key + yfinance stock.news), llm_analyzer (DeepSeek), daily_brief (yfinance + GDELT cache + event_intel + LLM). SEE SECTION "NEWS PATH" below.
- optimus_ledger.py (/api/optimus): job_receipts, daily_digest, ledger_calibration, portfolio_intelligence — local file/sqlite state.
- options.py (/api): earnings_intelligence, options_intelligence — yfinance options chains (no key, but yfinance option chains are a live snapshot, need network).
- pm.py (/api/pm): analyst_ledger, pm_actions, pm_engine, pm_journal — local state + yfinance prices.
- portfolio.py (/api/portfolio): attribution, benchmark_analytics, copula_tail, drawdown_analyzer, factor_model, llm_analyzer (DeepSeek), mpc_optimizer, portfolio_currency, portfolio_engine, portfolio_guidance, portfolio_optimizer, risk_number, stress_testing, tearsheet.
- portfolio_intelligence.py (/api/pi): heavy internal module set (alert_engine, conviction_calibration, experiment_registry, fragility, fragility_candidates, nav, real_analyzer, reference_engine, replay, rules, scheduler, tearsheet) + sqlite (backend/db) for paper_nav/lanes.
- prediction_markets.py (/api/prediction-markets): services.prediction_markets — likely external prediction market API (Kalshi/Polymarket?) — TO VERIFY key need.
- risk_layer.py (/api/risk-layer): services.risk_layer, data_fetcher.
- savings.py (/api/savings): retirement_mc, savings_calculator — pure computation, no external data needed (good offline candidate).
- sector.py (/api): crash_model, data_fetcher, regime_detector, sector_analyzer — yfinance.
- simulation.py (/api/simulation): data_fetcher, monte_carlo, regime_detector, risk_scorer — yfinance for calibration, otherwise pure compute.
- stock.py (/api/stock): huge fan-out (analyst_intelligence [Benzinga+yfinance], bubble_detector, conformal_predictor, crash_model, cross_sectional_momentum, data_fetcher, dividend_intelligence, drawdown_analyzer, drift_detector, earnings_intelligence, economic_surprise, esg [FMP], estimate_revisions, explain_move [yfinance+LLM], factor_grades, fundamentals [SEC], insider_trading [SEC], liquidity_risk, llm_analyzer [DeepSeek], options_intelligence, ownership, pattern_recognition, regime_detector, relative_valuation, risk_scorer, sentiment_analyzer [FinBERT local model], shap_explainer, short_interest, signal_analytics, signal_engine, stock_analyzer, style_box, survival_model, systemic_risk, technical_analysis, ticker_resolver, trends_sentiment, volatility_analytics). Mostly yfinance+FRED+SEC, optional FMP/Benzinga/DeepSeek enrichment, all degrade gracefully per repo convention.
- why_moved.py (/api/why-moved): services.why_moved (yfinance + LLM DeepSeek for explanation text).

## ENV KEYS declared in backend/config.py (providers block, line ~195-199)
- FRED_API_KEY, FINNHUB_API_KEY, FMP_API_KEY, ALPHA_VANTAGE_API_KEY, POLYGON_API_KEY
NOTE: FRED actually has a free-tier key requirement (FRED API requires a key even though FRED itself is "free data" — need to verify FRED_API_KEY is REQUIRED not optional; data_fetcher/fred usage TBD).
Also DEEPSEEK-related config around line 2095-2166 (RESEARCH_LLM_*, SWARM_MODEL=deepseek-chat, SWARM_* settings) but NOT the runtime DEEPSEEK_API_KEY read — that's read directly via os.getenv in llm_analyzer.py (to verify).

## ROOT CAUSE CANDIDATE #1 (HIGH CONFIDENCE): .env never loads in the frozen .exe
`backend/config.py:21` — `PROJECT_ROOT = Path(__file__).parent.parent`
`backend/config.py:97` — `load_dotenv(PROJECT_ROOT / ".env")` (gated only on `AEGIS_IGNORE_DOTENV`)
This does NOT honour `AEGIS_REPO_ROOT`. Contrast with the fix already applied in
`backend/services/llama_server.py:_repo_root()` (lines ~49-63) and
`backend/routers/control.py:_repo_root()` (lines ~47-63), both of which read
`AEGIS_REPO_ROOT` FIRST because of the exact documented defect family in
`docs/HANDOFF_2026-09-10_SESSION_CLOSE.md` §2 ("a path that resolves somewhere
believable and wrong inside the frozen build" — defects #8/#9/#10/#11) and
"MUST NOT REGRESS" item #14. `config.py` was never updated to match.
In the PyInstaller onedir build, `Path(__file__)` for `backend/config.py`
resolves inside the bundle (`dist/AegisDesktop/_internal/...`), so
`PROJECT_ROOT / ".env"` points at a location that does not exist (confirmed:
`AegisDesktop.spec`'s `datas` loop only walks `REPO/backend` and explicitly
skips `data`/`tests`/`vendor`/`__pycache__`; the repo-root `.env` file is never
copied into the bundle at all). `load_dotenv()` silently no-ops when the file
is missing (python-dotenv does not raise). Confirmed `.env` exists at repo root
with real (blank-in-audit, but presumably filled-in for the user) keys:
DEEPSEEK_API_KEY, FRED_API_KEY, FMP_API_KEY, NVIDIA_API_KEY, POLYGON_API_KEY,
ALPACA_*, FINNHUB_API_KEY, ALPHA_VANTAGE_API_KEY, HF_TOKEN, EODHD_API_TOKEN.
CONSEQUENCE: in the packaged .exe, `os.environ` never receives any of these,
so every module-level `os.getenv(...)` read at import time -- `backend/services/
llm_analyzer.py:43 _DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()`,
`config.py:195-199` fred/finnhub/fmp/alpha_vantage/polygon block, and
`model_provider.py`'s NVIDIA_API_KEY lookup used by `free_inference`'s DEFAULT
backend `nvidia_nim` -- reads empty. `llm_analyzer.is_available()` returns
False app-wide (news LLM summary, daily brief LLM summary, stock outlook LLM,
portfolio commentary LLM, why_moved LLM, event_intel LLM extraction all silently
degrade to template/None). FRED-backed analytics (bond, macro, valuation,
economic_surprise, external_validator, fixed_income, fx_curves, market_dashboard,
net_liquidity, world_markets, portfolio_currency, options_pit_store) silently
drop FRED series. `free_inference`'s DEFAULT_BACKEND ("nvidia_nim") cannot
authenticate. This is very plausibly THE central cause of "some of the APIs
don't seem connected" -- not that endpoints 404 or CORS-fail, but that they
return 200 with everything gracefully degraded/empty because the desktop
process never had its keys.
FIX IDEA (not applied — audit is read-only): make `config.py`'s dotenv load use
the same `AEGIS_REPO_ROOT`-aware resolution as `control.py`/`llama_server.py`'s
`_repo_root()`, e.g. read `os.getenv("AEGIS_REPO_ROOT")` before falling back to
`Path(__file__).parent.parent`. Note `aegis_desktop.py` sets `AEGIS_REPO_ROOT`
via `os.environ.setdefault(...)` in `start_backend()` (line ~176) BEFORE
`from backend.main import app` runs — so the value IS available in time if
`config.py` reads it.

## NEWS PATH (section 2)
Endpoint: `GET /api/news/market` (`backend/routers/news.py:26-35`), cache key
`news_market`, TTL `config["cache"]["ttl_news"] = 900s` (`backend/config.py:871`).
Handler `_fetch_market_news` (news.py:38-67):
1. `news_intelligence.fetch_gdelt_signals()` — GDELT DOC API
   (`https://api.gdeltproject.org/api/v2/doc/doc`, `backend/services/
   news_intelligence.py:38`), NO KEY required, network required. Cached
   (`gdelt:signals:...` 	result cache + `gdelt:last_good` stale-serve fallback,
   `_GDELT_CACHE_TTL`/`_GDELT_FAIL_COOLDOWN` from `config["performance"]`).
2. `news_intelligence.fetch_stock_news("SPY", max_items=10)` +
   `fetch_stock_news("QQQ", max_items=5)` (news.py:49-51) — both via
   `yfinance.Ticker(t).news` (news_intelligence.py:236-260), NO KEY, network
   required. Combined list capped to **15** items total
   (`all_news[:15]`, news.py:63) — NOT ~30 as the owner described; the /news
   page (`frontend/src/app/news/page.tsx:251-277`, "Recent Market Headlines")
   renders exactly this same `data.news` array (max 15). Likely the owner's
   "~30" is an approximation, or refers to a different page/run where SPY+QQQ
   both returned their max and it visually looked larger, or to the per-stock
   news endpoint (`/api/news/{ticker}`, up to 15 items) seen on a stock page.
   No single surface in this repo currently renders 30 news items — worth the
   owner re-checking which page/count exactly, since the code caps at 15.
3. Optional LLM summary via `llm_analyzer.summarize_market_news()`
   (DeepSeek) — gated on `is_available()`; see root cause #1 above — likely
   absent in the desktop app.
4. `news_intelligence.map_news_to_sectors()` — pure local computation on the
   already-fetched headlines, no extra network/key.
Home page (`frontend/src/app/page.tsx`) does NOT call `/api/news/market`
directly — it renders `DailyBriefCard` (`frontend/src/components/dashboard/
daily-brief-card.tsx`) which calls `getDailyBrief` → `GET /api/news/brief`
(news.py:70-93) → `backend/services/daily_brief.py:build_daily_brief`. That
function fetches OHLC closes for 8 market tape symbols + up to 15 user
tickers via `data_fetcher._fetch_batch_yahoo` (yfinance, no key), a
GDELT-derived geopolitical block (reads `cache_peek("news_market", ...)`
first, else re-fetches GDELT), an events block via `event_intel.
get_events_for_brief` (SEC/EDGAR-derived), headlines (`_headlines_for`, up to
3 per top-5 mover, via yfinance `news_intelligence.fetch_stock_news`), and an
optional DeepSeek summary (falls back to `_template_summary` when
`is_available()` is False). No single field here totals ~30 either — headline
count is bounded at `5 movers * 3 headlines = 15` max. CONCLUSION: the "~30
items" the owner reports does not map cleanly onto any one array in the
current code; the closest candidates are `/api/news/market`'s `news[:15]` or
`/api/news/{ticker}`'s `news[:15]` — worth asking the owner exactly which
page/section they counted.

### Every other news/collector surface in the repo (grep for news/benzinga/rss/feedparser/gdelt/newsapi)
- `backend/services/news_intelligence.py` — GDELT + yfinance `stock.news`. USED by news.py, daily_brief.py. Reachable (main consumer).
- `backend/services/daily_brief.py` — composed brief. USED by news.py `/brief`, DailyBriefCard.
- `backend/services/event_intel.py` — SEC/EDGAR-derived structured "events" (not headline news per se) + LLM (DeepSeek) extraction. USED by event_intel.py router, daily_brief.py `_events_block`.
- `backend/services/edgar_events.py` — raw SEC EDGAR filings/events. USED by events.py router (`/api/events`).
- `backend/services/analyst_intelligence.py` — Benzinga (per earlier grep hit) + yfinance. USED by stock.py router.
- `backend/services/llm_research.py`, `llm_swarm.py`, `investigator_agent.py`, `investigator_night.py` — LLM-driven research/collector jobs, mostly used by `scripts/night_factory` jobs (offline batch), NOT by any live router — these are research-programme artifacts, not part of the served app. Did not find a router that calls them directly (grep of routers/*.py services imports above shows none import these names).
No feedparser/newsapi usage found in backend/services (grep returned nothing for those literal terms beyond the ones listed above — GDELT + yfinance + Benzinga + SEC/EDGAR are the only news-shaped sources reachable from routers).

## LOCAL MODEL PATH (section 3)
Chain: `frontend/src/app/desktop/ask/page.tsx` → `frontend/src/lib/control-api.ts`
`ask(q)` → `POST {CONTROL_BASE}/api/control/ask?question=...` where
`CONTROL_BASE = DESKTOP_BUILD ? "" : (NEXT_PUBLIC_API_URL || "http://localhost:8000")`
(control-api.ts:20-23) — same-origin in the packaged app (correct, see section 4).
Backend: `backend/routers/control.py:455-486 ask()`. Default `backend="local_gguf"`
(matches the Ask page's expectation). Before answering it calls
`llama_server.status()` (control.py:463) and REFUSES with a readable message if
`not st.get("ready")` (control.py:464-470) rather than 500ing — good UX, but
means "not connected" symptom on this page is really "llama-server isn't
started/ready" surfaced correctly, not a wiring bug per se.
If ready, it builds a prompt from `_ask_context()` (control.py:435-452, reads
`NIGHT_DIR`'s `LEADERBOARD.md` files — NOT arbitrary app data, just night-run
receipts) and calls `free_inference.complete(backend="local_gguf", ...)`
(control.py:478) which wires through `model_provider.py`'s `PROVIDERS["local"]`
row: `base_url="http://127.0.0.1:8080/v1"`, `key_env=None` (model_provider.py:93-105).
llama-server itself: `backend/services/llama_server.py`. Config via
`backend/config.py` `LLAMA_HOME`/`LLAMA_BIN`/`LLAMA_MODEL`/`LLAMA_HOST`/`LLAMA_PORT`
(default 8080)/`LLAMA_CTX`/`LLAMA_NGL`/`LLAMA_N_CPU_MOE`, overridable via
`AEGIS_LLAMA_*` env vars (llama_server.py:80-89) — these fall back through
`backend.config` via `_conf()`, so if config.py's LLAMA_* attributes aren't
defined the module still works from hardcoded defaults (`Path.home()/"llama"`),
independent of the dotenv bug above (llama.cpp needs no API key).
`status()` (llama_server.py:239-268) distinguishes `listening` (port bound) from
`ready` (`/health` returns 200) — `listening and not ready` = still loading.
The Ask page reads exactly this three-state signal (`page.tsx:45`
`phase = ... ? "ready" : st.listening ? "loading" : "down"`), polling every 15s
(`refetchInterval: 15_000`). WHAT MAKES IT LOOK "NOT CONNECTED": (a) llama-server
is simply not started — `aegis_desktop.py`'s `maybe_start_llama()` only starts it
if the binary+model files exist AND nothing is already listening
(`llama_server.py:start()` refuses a second copy); if the binary/model paths
(`~/llama/bin/llama-server.exe`, `~/llama/models/Qwen2.5-7B-Instruct-Q4_K_M.gguf`
by default) are absent on the machine building/running the .exe, `maybe_start_llama`
returns `{"action":"unavailable", ...}` and NOTHING is running — Ask page
correctly shows "local model not running", which reads as "not connected" to a
user who doesn't know the model has to be downloaded separately; (b) cold start:
`start(wait_s=0.0, ...)` in aegis_desktop.py does NOT block on readiness (returns
immediately so the splash screen can proceed) — so right after opening the app
the model is `listening=True, ready=False` for potentially ~10s-90s depending on
model size (nemotron/qwen numbers in free_inference.py docstring), and the
`/ask` route's refusal + Ask page's "loading the model" state should handle this
gracefully already — this looks like it was already fixed per S51/S52 memory notes.
`free_inference.DEFAULT_BACKEND = "nvidia_nim"` (free_inference.py:97-99), NOT
`local_gguf` — any OTHER caller of `free_inference.complete()` without an
explicit backend argument will try NVIDIA NIM (needs `NVIDIA_API_KEY`, network)
rather than the local model. `control.ask()` explicitly passes
`backend="local_gguf"` as its own default so THIS path is fine, but any future
or existing caller relying on `free_inference`'s module default would silently
require an NVIDIA key + network instead of using the "free local inference" the
user asked for — worth checking for such callers if "local-model services
seemed not connected" refers to something other than the Ask page.
`local_review.py` not yet inspected in depth — grepped as a DeepSeek/LLM user; did not find a router importing it directly (not in the services-import grep for any router file above) — likely called from `scripts/` night jobs only, not from a live endpoint.

## FRONTEND API CLIENT (section 4)
`frontend/src/lib/api.ts:20-23` (main client, ~all non-control pages):
```
export const API_BASE =
  process.env.NEXT_PUBLIC_AEGIS_DESKTOP_BUILD === "1" ? "" :
  (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000");
```
`frontend/src/lib/control-api.ts:20-23` (desktop control-plane pages, `/desktop/*`):
same pattern, own `CONTROL_BASE` constant.
`frontend/next.config.ts:16-35`: when `AEGIS_DESKTOP_BUILD=1` (set by the build
command `AEGIS_DESKTOP_BUILD=1 npx next build`, see AegisDesktop.spec:4), Next's
`env:` block FORCES `NEXT_PUBLIC_AEGIS_DESKTOP_BUILD="1"` and
`NEXT_PUBLIC_API_URL=""` at compile time, overriding whatever `.env.local` says
(`.env.local` has `NEXT_PUBLIC_API_URL=https://aegis-finance-production.up.railway.app`
for the Vercel/website deploy). This was previously broken (commit `07669b0`,
"The desktop app was calling Railway from every page except /desktop") and is
now fixed — verified: `grep -rl "railway.app" frontend/out/_next/static/chunks/*.js`
returns NOTHING in the current build (checked 70 JS chunks). So same-origin
API calls appear CORRECTLY WIRED in the current `frontend/out` build (built
2026-09-10 16:46, per file mtimes) — this specific historical bug is resolved,
contingent on whoever builds the .exe always using `AEGIS_DESKTOP_BUILD=1`.
Remaining hardcoded external URLs found in frontend/src (none call the API,
all benign per grep):
- `frontend/src/app/dev/page.tsx:14` — `const BRAIN_URL = "https://optimus-brain-alpha.vercel.app"` — an `<a href>` link out to the Optimus brain UI, not a fetch (per HANDOFF_2026-09-10_SESSION_CLOSE.md item 9, "the last remote reference in the desktop build", acknowledged/left deliberately).
- `frontend/src/app/robots.ts:17` and `frontend/src/app/sitemap.ts:9` — SEO metadata for the public Vercel deploy (`aegis-finance-six.vercel.app`), generated at build time, irrelevant to the desktop app's runtime data fetching.
No other `railway.app`/`vercel.app`/absolute `https://` API base found in frontend/src.

## LIKELY CONCRETE REASONS FOR "APIs NOT CONNECTED" (section 5)
1. **`.env` never loads in the packaged .exe** — `backend/config.py:21,97`
   (`PROJECT_ROOT = Path(__file__).parent.parent`; `load_dotenv(PROJECT_ROOT / ".env")`)
   ignores `AEGIS_REPO_ROOT`, unlike `control.py`/`llama_server.py`'s `_repo_root()`.
   Fix idea: make config.py's dotenv resolution `AEGIS_REPO_ROOT`-aware, matching
   the existing pattern in the other two modules.
2. **Every DeepSeek-backed feature silently degrades** as a direct consequence
   of #1 — `backend/services/llm_analyzer.py:43` reads `DEEPSEEK_API_KEY` at
   import time; with an empty string, `is_available()` is False app-wide (news
   summaries, daily brief narrative, stock outlook, portfolio commentary,
   why_moved explanations, event_intel LLM extraction all fall back to
   template/None). Fix: same as #1.
3. **Every FRED-backed feature silently drops FRED series** as a direct
   consequence of #1 — `backend/services/data_fetcher.py:470-471` logs
   "FRED_API_KEY not set, skipping FRED data" and just continues without it;
   affects macro/bond/economic-surprise/fixed-income/world-markets/
   net-liquidity panels app-wide. Fix: same as #1.
4. **`free_inference.DEFAULT_BACKEND = "nvidia_nim"`** (`backend/services/
   free_inference.py:97-99`) needs `NVIDIA_API_KEY` + network; any call site
   that doesn't explicitly pass `backend="local_gguf"` will look "disconnected"
   offline even though a local model exists. `control.ask()` already passes
   the right backend explicitly; worth checking for other call sites.
5. **llama-server must be downloaded/placed by hand** at
   `~/llama/bin/llama-server.exe` + `~/llama/models/Qwen2.5-7B-Instruct-Q4_K_M.gguf`
   (`backend/services/llama_server.py:80-83` defaults) — a fresh machine/user
   without these files gets `"binary_present": false` / `"model_present": false`
   and the Ask page correctly reports "local model not running", which reads
   as "not connected" to a first-time user with no in-app guidance on how/where
   to get the model. Fix idea: surface a clearer first-run message or a
   download helper.
6. **Cold-start heavy endpoints can look dead** — `frontend/src/lib/api.ts`'s
   `FETCH_TIMEOUT_MS = 45_000` (line ~29) will hard-fail a request into a
   never-before-warmed endpoint (Monte Carlo, GARCH/HMM regime, crash model,
   80-ticker screener) on the FIRST call in the desktop app, since
   `main.py`'s `_warm_endpoint_caches_loop`/`_prewarm_cache` warm the SAME
   process's cache but the desktop app is a cold process every launch with no
   persistent warm loop history from a prior Railway deploy. Per
   `docs/HANDOFF_2026-09-10_SESSION_CLOSE.md` §4 item 8: "only the four
   `/desktop` pages have been exercised; the rest of the app now talks to the
   local backend for the first time and some endpoints will want network data
   on first call" — i.e. this is a documented, KNOWN-UNVERIFIED gap, not
   something already proven fixed.
7. **Optional paid/keyed sources (Polygon, FMP, Finnhub, Alpha Vantage,
   Benzinga, Alpaca)** degrade gracefully per repo convention when keys are
   absent — this is BY DESIGN, not a bug, but combined with #1 (no keys load
   at all) it means the desktop app currently runs in "every optional source
   absent" mode even for keys the owner actually has configured in `.env`.
8. **The "~30 news items" count does not match any array size found in the
   current code** (max is 15 in every news-shaped endpoint checked) — worth
   the owner re-confirming exactly which page/section was counted; could be a
   misremembered number, could be a page not covered by this audit's search.
9. Everything requiring network (yfinance, GDELT, SEC/EDGAR, CoinGecko/DefiLlama
   for crypto, Kalshi for prediction markets) will show data-source errors if
   the desktop machine truly has no internet — most of these DO require
   network even though they need no key (yfinance/GDELT/SEC have no key
   requirement but do require live HTTP access).

