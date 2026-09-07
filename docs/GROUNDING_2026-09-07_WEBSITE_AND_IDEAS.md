# GROUNDING REPORT — the website today, and what the ideas rest on

Read-only survey, 2026-09-07. Repos: `C:\Users\mrthn\aegis-finance` (this),
`C:\Users\mrthn\aegis-alpha-terminal` (execution), `C:\Users\mrthn\Aegis module` (investor brain).
Nothing was modified. Anything not found is marked **CANNOT DETERMINE**.

---

# PART A — THE WEBSITE TODAY

## A.1 Frontend routes

**Note on layout:** the pages live under `frontend/src/app/`, **not** `frontend/app/` or `frontend/pages/`.
Next.js App Router. All paths below are relative to `C:\Users\mrthn\aegis-finance\`.

| Route | File | What it shows |
|---|---|---|
| `/` | `frontend\src\app\page.tsx` | Dashboard: growth×inflation regime, risk-on/risk-off, market banner, crash gauge, daily brief, sector heatmap, S&P chart, model-vs-firms |
| `/about` | `frontend\src\app\about\page.tsx` | Methodology cards (Monte Carlo, crash prediction, …) |
| `/copilot` | `frontend\src\app\copilot\page.tsx` | LLM chat over `/api/copilot/chat` |
| `/crash` | `frontend\src\app\crash\page.tsx` | Crash-probability model + diagnostics |
| `/dev` | `frontend\src\app\dev\page.tsx` | Dev dashboard — `/api/health/full`, data-quality, drift |
| `/investment-committee` | `frontend\src\app\investment-committee\page.tsx` | The IC view over `/api/ic/committee` |
| `/news` | `frontend\src\app\news\page.tsx` | News & Intelligence (market news + brief) |
| `/outlook` | `frontend\src\app\outlook\page.tsx` | Market outlook, macro, economic-calendar card |
| `/portfolio` | `frontend\src\app\portfolio\page.tsx` | **Builder & Analysis** — holdings typed by hand into `localStorage["aegis_holdings"]`, POSTed to `/api/portfolio/*` |
| `/portfolio-intelligence` | `frontend\src\app\portfolio-intelligence\page.tsx` | PI hub |
| `/portfolio-intelligence/compare` | `…\compare\page.tsx` | Lane-vs-lane comparison |
| `/portfolio-intelligence/conviction` | `…\conviction\page.tsx` | **Decision-journal UI (TRIAL-003)** — form: ticker, action, shares, price, conviction 1-5, rationale (min-length enforced), target, stop, planned exit trigger, late-entry flag; plus the logged-decision table |
| `/portfolio-intelligence/my-portfolio` | `…\my-portfolio\page.tsx` | Holdings (same `aegis_holdings` key) → `/api/pi/real-portfolio/analyze` |
| `/portfolio-intelligence/reference` | `…\reference\page.tsx` | Reference-lane state/history + equity curve |
| `/portfolio-intelligence/risk-watch` | `…\risk-watch\page.tsx` | Fragility reading, candidates, alerts |
| `/portfolio-intelligence/track-record` | `…\track-record\page.tsx` | Live track record / lane NAVs |
| `/retirement` | `frontend\src\app\retirement\page.tsx` | Retirement calculator (`localStorage["aegis_retirement"]`) |
| `/risk` | `frontend\src\app\risk\page.tsx` | Risk layer — sizing/exposure over `/api/risk-layer/*` |
| `/screener` | `frontend\src\app\screener\page.tsx` | Screener over `/api/stock/screener` |
| `/sectors` | `frontend\src\app\sectors\page.tsx` | Sector analysis |
| `/simulation` | `frontend\src\app\simulation\page.tsx` | Monte Carlo S&P simulation |
| `/stock` | `frontend\src\app\stock\page.tsx` | Ticker-search landing |
| `/stock/[ticker]` | `frontend\src\app\stock\[ticker]\page.tsx` | Single name: signal, two-sided, factor lens, events, grades, style box, analysts |
| `/watchlist` | `frontend\src\app\watchlist\page.tsx` | **Personal watchlist, ≤50 tickers, localStorage only** ("never leaves your browser") |
| `/workspace` | `frontend\src\app\workspace\page.tsx` | Bloomberg-style tile grid, ≤6 tiles, `localStorage["aegis.workspace.v1"]` |
| `/world` | `frontend\src\app\world\page.tsx` | World markets |

Nav is authoritative in `frontend\src\components\sidebar.tsx` (lines 48-87), grouped
Markets / Equities / Portfolio / Tools.

Main components — `frontend\src\components\`:
`dashboard\{crash-gauge, daily-brief-card, hero-section, macro-cards, market-banner, model-vs-firms-card, sector-heatmap, signal-badge, sp500-chart}.tsx`,
`pi\{lane-equity-chart, lane-stats-ci}.tsx`,
`stock\{events-card, factor-lens-card, two-sided-card}.tsx`,
`copilot-chat.tsx`, `command-bar.tsx`, `watchlist-toggle.tsx`, `factor-grades-card.tsx`,
`style-box-card.tsx`, `outlook\economic-calendar-card.tsx`, `data-freshness.tsx`,
`methodology-banner.tsx`, `disclaimer-banner.tsx`, `first-run-tour.tsx`, `shortcut-manager.tsx`.

Client state — `frontend\src\hooks\`: `use-watchlist.ts`, `use-workspace.ts`,
`use-beginner-mode.ts`, `use-api.ts`, `use-shortcuts.ts`.
API client — `frontend\src\lib\api.ts`: `API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"`,
45 s default fetch timeout, 120 s "heavy" budget.

## A.2 Backend routers — `backend\routers\`

Wired in `backend\main.py` lines 503-527 and 592-593. App-level endpoints:
`GET /`, `GET /api/health`, `GET /api/health/full`, `GET /health/scheduler`, `GET /api/providers`.

- **`market.py`** — `/api`: `market-status`, `dashboard`, `brain/digest`, `signal`,
  `model-vs-firms` (our 5y MC expected return beside published firm CMAs), `macro`,
  `world-markets`, `economic-calendar`, `net-liquidity`, `data-quality`, `realtime/{ticker}`.
- **`stock.py`** — `/api/stock`: `screener`, `resolve`, `{ticker}`, and per-ticker
  `signal`, `two-sided`, `shap`, `sentiment`, `fundamentals`, `analysts`, `technicals`,
  `insiders`, `ownership`, `etf-lookthrough`, `valuation`, `patterns`, `volatility`,
  `dividends`, `style-box`, `short-interest`, `revisions`, `explain-move`, `esg`, `grades`.
- **`portfolio.py`** — `/api/portfolio` (all POST, all stateless): `questionnaire`, `guidance`,
  `analyze`, `project`, `build`, `optimize`, `attribution`, `risk-contributions`, `commentary`,
  `factor-exposures`, `copula-risk`, `benchmark`, `compare`, `optimize-mpc`,
  `tearsheet.html`, `tearsheet.xlsx`, `currency-exposure`.
- **`portfolio_intelligence.py`** — `/api/pi`: `real-portfolio/analyze`,
  `reference/{lane}/{state,history,explain,snapshot}`, `registry`, `fragility`,
  **`POST conviction/decision`**, `conviction/decisions`, `conviction/calibration`,
  `risk-watch`, `alerts`, `track-record`, `lane/{id}/{stats-ci,tearsheet,positions}`,
  `compare`, `POST trigger-check`, `replay/{lane}`, `POST replay/{lane}/refresh`.
- **`pm.py`** — `/api/pm`, the Optimus PM surface, **no frontend page**: `book`,
  `book/validate`, `revisions/{ticker}` (our own PIT ΔTarget 7/30/90d), `daily`
  (the morning brief: state / actions / opportunities / threats / odds), `name/{ticker}`,
  `wealth`, `catalysts`, **`journal`** ("every recommendation ever issued, so they can be
  scored later"), **`POST journal/record`** (freeze today's brief into the decision journal),
  **`POST snapshot`** (append today's analyst state to the PIT ledger).
- **`analytics.py`** — `/api/analytics`, 40 endpoints: `factors/{ticker}`, `factors-ff6/{ticker}`,
  `factors/pca-residuals`, `factors/portfolio`, `scenarios`, `stress-test[/{ticker}|/hypothetical]`,
  `momentum[/{ticker}]`, `economic-surprise`, `economic-calendar`, `crash-timeline`, `changepoint`,
  `vix-term-structure`, `liquidity[/{ticker}]`, `copula/…`, `covariance-diagnostics`,
  `trends-sentiment[/{ticker}]`, `drawdowns/{ticker}`, `conformal-interval`, `earnings-calendar`,
  **`analyst-consensus/{ticker}`**, `prediction-confidence`, `sector-rotation`, `fixed-income`,
  `valuation`, `pairs/…`, `tail-risk/{ticker}`, `survival-model`, `cross-asset`, `macro-regime`,
  `allocation-strategies`, `allocation-backtest[/{name}]`, `treemap`.
- **`arena.py`** — `/api/arena`: `status`, `books/{id}/nav`, `books/{id}/decisions`,
  `experiences/summary`, `beliefs`, `reliability`, `router`, `personalities`, `regret`.
- **`optimus_ledger.py`** — `/api/optimus`: `calibration`, `job_receipts`, `digest`,
  `POST run_job/{job_id}`.
- **`news.py`** — `/api/news`: `market`, `brief`, `{ticker}`.
- **`events.py`** — `/api/events`: `taxonomy` (8-K item → event_type/materiality), `8k/{ticker}`, `8k`.
- **`event_intel.py`** — `/api/event-intel`: `stats`, `{ticker}`.
- **`why_moved.py`** — `/api/why-moved`: `attribution`, `explain`, `lenses`.
- **`risk_layer.py`** — `/api/risk-layer`: `evidence`, `POST exposure`.
- **`investment_committee.py`** — `/api/ic`: `committee`.
- **`copilot.py`** — `/api/copilot`: `status`, `tools`, `POST chat`.
- **`prediction_markets.py`** — `/api/prediction-markets`: root, `divergence`, `surface`.
- Smaller: `simulation.py` (`/api/simulation/{sp500,scenarios}`), `crash.py`
  (`/api/crash/{prediction,diagnostics,{ticker}}`), `sector.py` (`/api/sectors`),
  `markets.py` (`/api/markets/{fx,fx/{pair},futures,futures/{symbol}}`),
  `crypto.py` (`/api/crypto/{markets,{coin}/history,defi,defi/protocols}`),
  `bond.py` (`/api/bond/{treasury-curve,analytics,key-rate-durations,ladder}`),
  `options.py` (`/api/options/vix-term`, `/api/options/{ticker}`, `/api/earnings/{ticker}`),
  `savings.py` (`/api/savings/{project,simulate,safe-rate}`),
  `backtest.py` (`/api/backtest/signal`), `correlation.py` (`/api/correlation/tail-dependence`),
  `drift.py` (`/api/drift/check`).

## A.3 Local run — `docker-compose.yml`

Two services, and **it runs fully without Railway**:

- **`backend`** — built from `backend/Dockerfile` (python:3.12-slim, gcc/g++/libgomp for
  lightgbm/scipy/hmmlearn, `MALLOC_ARENA_MAX=2`), command
  `uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}`. Published on `${PORT:-8000}:${PORT:-8000}`.
  `env_file: .env`. Env: `PORT`, `ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000`.
  Healthcheck hits `/api/health` (15 s interval, 30 s start period).
- **`frontend`** — built from `frontend/Dockerfile` (Next standalone output, `node server.js`),
  port `3000:3000`, `depends_on: backend service_healthy`. Build-arg **and** runtime env
  `NEXT_PUBLIC_API_URL=http://localhost:${PORT:-8000}` (it is baked at build time for client bundles).

Non-docker path (CLAUDE.md § Commands): `uvicorn backend.main:app --reload --port 8000`
plus `cd frontend && npm install && npm run dev`.
Env needs: a root `.env` (DeepSeek key etc.). `AEGIS_IGNORE_DOTENV=1` disables loading it
(`backend/config.py`) — never move `.env`.
`railway.json` deploys **only the backend** Dockerfile with healthcheck `/api/health`;
the compose stack is self-contained and the Railway project `selfless-courage` places no orders.

## A.4 What already exists for a human-in-the-loop mode

| Capability | Where it lives | Web surface today |
|---|---|---|
| **Candidate / potential list** | `learner\potential_universe.py` (`CODE_VERSION = "potential_universe_v1/2026-09-03"`); runner `scripts\potential_universe_run.py`; only vintage on disk `backend\data\optimus\potential_universe\2026-09-02.jsonl` = **3,057 lines (1 header + 3,056 scorecards)**, 6.37 MB | **NONE** |
| **Tracker watchlist (whole market)** | terminal `scripts\tracker.py`; nightly `C:\Users\mrthn\aegis-alpha-terminal\state\tracker\2026-09-02.jsonl` (**3,056 rows**; 09-01 had 3,059); summary `state\tracker\latest.json`; `transitions.jsonl` 27,537 rows | **NONE** |
| **Personal watchlist** | `frontend\src\hooks\use-watchlist.ts` | YES — `/watchlist`, browser-only, ≤50 tickers |
| **Analyst targets vs our own estimate** | `backend\services\analyst_ledger.py` → `/api/pm/revisions/{ticker}`; `/api/stock/{ticker}/analysts`; `/api/analytics/analyst-consensus/{ticker}`; `/api/model-vs-firms` (index level) | PARTIAL — single-name analyst card on `/stock/[ticker]`; the PIT ΔTarget ledger has no page |
| **Band prior / fair value** | receipts `backend\data\optimus\tracker_backtest\band_horizon_2026090{3,5}.json` (+ a `.SUPERSEDED_BY.json` sidecar); terminal `alpha\analyst_targets.py` | **NONE** |
| **Pre-open prediction book** | terminal `scripts\prediction_book.py`, `scripts\prediction_book_sync.py`; typed theses `scripts\thesis.py` + `alpha\human.py` | **NONE — the terminal repo has no HTTP layer at all** (`grep -l 'APIRouter\|FastAPI'` over its `alpha/`, `scripts/`, `backend/` returns zero files) |
| **Decision journal (typed)** | **two, in this repo**: (1) `POST /api/pi/conviction/decision` → immutable `personal_decisions` table (`backend\db.py`); (2) `/api/pm/journal` + `POST /api/pm/journal/record` (`backend\services\pm_journal.py`) | (1) YES — `/portfolio-intelligence/conviction`; (2) **no page** |
| **Portfolio builder in localStorage** | `frontend\src\app\portfolio\page.tsx` (key `aegis_holdings`), mirrored by `…\my-portfolio\page.tsx`, `app\risk\page.tsx`, `components\dashboard\daily-brief-card.tsx` | YES |
| **Capital allocator v0** | `learner\allocator.py`; runner `scripts\allocator_run.py`; artefacts `backend\data\optimus\decision_artifacts\2026-09-02_{balanced,aggressive}.json` | **NONE** |
| **News / corpus** | `/api/news/*`, `/api/events/*`, `/api/event-intel/*`, `/api/why-moved/*`. The 30.9k-row observation corpus is in the terminal repo (`scripts\corpus_digest.py`, `docs\CORPUS_2026-08-29_*`) | PARTIAL — market news YES; corpus NO |
| **Daily learning report / autopsy / recall** | terminal `scripts\daily_learning_report.py` (→ `state\learning_report\<day>.json`), `scripts\daily_autopsy.py` (→ `state\autopsy\<date>.json` + `state\autopsy_templates.jsonl`), `scripts\discovery_autopsy.py`, `alpha\recall.py` (miss types `NOT_OBSERVED` / `GENERATED_NOT_RANKED` / `RANKED_NOT_BOUGHT` / `BOUGHT_SOLD_EARLY`) | **NONE — CLI + JSON files only, zero endpoints** |
| **Paper books / arena** | `/api/arena/*` | Endpoints exist, **no page** |

**The one existing typed-decision schema, worth reusing verbatim** —
`backend\routers\portfolio_intelligence.py:341-357`, `ConvictionDecisionRequest`:
`ticker`, `action` (`enter|add|trim|exit`), `shares_delta`, `price`,
`rationale` (≥50 chars, "honest-record discipline"), `conviction` (1-5),
`thesis_tags: list[str]`, `target_price`, `stop_price`, `planned_exit_trigger`,
`catalyst_dates: list[str]`, `amends_id` (corrections append, never update),
`late_entry` (the action already happened), `portfolio_snapshot`.
Timestamp is always server-now, never client-supplied; the table's triggers forbid update/delete.

## A.5 THE GAP LIST — no web surface today

1. **The candidate list itself** (3,056 scorecards, `learner/potential_universe.py`) — the single
   most load-bearing gap for "build a portfolio from the machine's candidate lists".
2. **The 3,056-name tracker watchlist** and its 806 candidates / status histogram.
3. **The pre-open prediction book and typed theses** — and with them the *entire* execution repo,
   which has no HTTP layer whatsoever.
4. **The daily learning report, daily autopsy, discovery autopsy and opportunity-recall ledger.**
5. **Capital allocator v0** — its decision artefacts are JSON on disk, unreadable from a browser.
6. **The band prior / fair-value work** (analyst-target bands, toxic-band exclusions).
7. **`/api/pm/*`** — morning brief, catalysts, wealth, book validation and the PM journal all have
   endpoints but no page renders them.
8. **`/api/arena/*`** — beliefs, reliability, regret, personalities: endpoints, no page.
9. **Cross-repo reachability**: the website backend cannot see `aegis-alpha-terminal\state\` at all.
   `learner/` reads the terminal's tracker files from the local filesystem; a deployed backend has
   no such path. Any human-in-the-loop surface wanting seals, fills or refusals needs a sync or a
   new reader service.
10. **No auth and no server-side per-user state** — holdings, watchlist and workspace are
    browser-local by design (CLAUDE.md DO NOT: "Store portfolio state server-side"). The single
    carved-out exception is the `personal_decisions` SQLite table behind `/api/pi/conviction/*`,
    which is the natural anchor for a human-in-the-loop journal.
11. **Staleness**: the newest tracker and potential_universe vintages are both **2026-09-02** —
    five days old. Any candidate-list UI needs the nightly job running, not just an endpoint.

---

# PART B — WHAT THE IDEAS ARE GROUNDED IN

## (a) TRIAL-LLM-AMNESIA-1 — "can you tell an LLM to forget?"

Verdict: `C:\Users\mrthn\Aegis module\docs\AMNESIA_VERDICT_2026-08-08.md`.
Pre-registration: `C:\Users\mrthn\Aegis module\TRIALS\PREREG_LLM_AMNESIA_1.md`
(copy at `…\runs\AMNESIA\PREREG_LLM_AMNESIA_1.md`). Receipts: `…\runs\AMNESIA\AMNESIA_1.json`,
`AMNESIA_1B.json`, `event_set.csv`, `cache\`, `cache_1b\`. Runner code, also in the Aegis module:
`scripts\llm_amnesia_1.py` (the four-arm runner; cache at `runs/AMNESIA/cache/<key>.json` "so a
re-run costs nothing and the transcript is auditable"), `scripts\llm_amnesia_1b.py` (the positive
control), `aegis_brain\llm\amnesia.py` (the masking + synthetic scenario generator),
`scripts\abn_ingest_amnesia.py`. `TRIALS\registry.jsonl` lines 72-73 record registration at
2026-08-08T12:47:59Z and 12:54:50Z — both **before compute**; line 76 records a third descendant,
`TRIAL-NAME-ONLY-1` (2026-08-09), measuring "the contamination ceiling for any unmasked
diagnostic" on the same 120 situations (`runs\NIGHT3\NAME_ONLY.json`, `NAME_ONLY_FORCED.json`).

**The verdict document itself lives only in the Aegis module, but `aegis-finance\docs` carries
seven cross-references and two named successors:**
`docs\EXTERNAL_REVIEW_DOSSIER_2026-08-09.md:43` and §301 ("Contamination (1,080 DeepSeek calls,
'AMNESIA')"); `docs\DESIGN_MEMORY_TAXONOMY_2026-08-09.md:8,105`;
`docs\PROMPT_FACTORY_OVERNIGHT_2026-08-08.md:230` (cites the verdict as **"(binding)"**);
`docs\TRIALS\TRIAL-LEAK-1-identified-vs-masked.md` (the named successor — "this trial is that
successor… honest prior: we expect H1 to come back NOT DETECTABLE");
`docs\TRIALS\PREREG_ABLATION_1.md:21` ("Resurrects: PREREG_LLM_AMNESIA_1 — new instrument: amnesia
asked whether the model could be made to forget a name's identity; this asks whether its SEMANTIC
CONTENT survives a distribution-preserving permutation"); plus session logs
`docs\archive\SESSION_2026-08-08_FACTORY_NIGHT1.md` and `docs\archive\SESSION_2026-08-09_NIGHT3.md`.

Design: one real historical situation, four disclosure arms — A0 NAMED-RAW, A1 NAMED-INSTRUCTED,
A2 MASKED, A3 SYNTHETIC. 120 events (60 beat / 60 lagged), US large/mid, formation months
2005-01…2021-12, seed 20260808, `deepseek-chat` at temperature 0, single sample, 1,080 calls
across trials 1 and 1B. The six pre-registered predictions and what happened:
**P1** "A0 recall ≥ 40%" → **MISS** (15.8%);
**P2** "the instruction fails: A1 recall within 15 pts of A0 and |ΔBrier| < 0.02" → **HIT**;
**P3** "A2/A3 identification ≤ 10%" → **HIT** (0 of 240);
**P4** "Brier(A2) − Brier(A0) ≥ +0.02" → **MISS** (0.007);
**P5** "neither A2 nor A3 beats the logistic baseline" → **HIT**;
**P6** "A3 ≈ A2 within 0.01 Brier" → **HIT** (0.0004). **Score 4/6.**
Measured (n = 120/arm): A0 Brier 0.2495 / AUC 0.550 / recall 15.8%; A1 0.2530 / 0.532 / **15.8%**;
A2 0.2568 / 0.519 / identified 0; A3 0.2564 / 0.521 / identified 0; climatology 0.2500;
logistic OOS 0.2538 / 0.511. Positive control 1B declined on 95.8% but was 5/5 correct on the
famous collapses (PYPL −64%, CHK −71%, GOEV −81%, THQI −41%, BTU −16%); numeric 12-month returns
answered 4.2% of the time with median absolute error 43.6 pp; the survival leg is recorded
"VOID by metric mismatch". Verdict, verbatim: "**the instruction does nothing** … 15.8% vs 15.8%
— identical to three decimals"; "never accept an instruction as a control"; "masking is the
control, and canaries are how you know it held"; "the model remembers catastrophes, not returns".
The task is retired for LLM evaluation; successor AMNESIA-2 moves to 5-day abnormal returns around
earnings/FDA.

## (b) The fantasy stress-exam code path

Two rounds in two repos. **Round 1**: `C:\Users\mrthn\aegis-alpha-terminal\scripts\labor_b2_fantasy_exams.py`,
receipt `…\state\labor_day_lab_2026-09-07\B2_fantasy_exams.json` (+ `_run02`, `_dryrun`).
**Round 2**: `C:\Users\mrthn\aegis-finance\scripts\n6b_fantasy_exams_round2.py` (909 lines),
receipt `backend\data\optimus\night_lab_2026-09-07\N6b_fantasy_exams_round2.json` (+ `_dryrun`),
documented in `docs\BUILD_NIGHT_LAB_2026-09-07.md` and `docs\NIGHT_LAB_2026-09-07_OPUS_PROMPT.md` (lane N6.2).
**How pairs are built:** entirely fictional companies (round 2 mints names in-code from an
adjective×noun word bank keyed on `random.Random(20260907)`; round 1 used
`alpha.transpose.build_entity_map`). A *pair* is two briefs about the same fictional company,
identical except one flipped causal clause — a GOOD leg and a BAD leg drawn from a `FAMILIES`
table. Round 1 mechanisms: `fda, sanction, funding, supply, guidance, customer`. Round 2 event
archetypes: `earnings_surprise, guidance, activist_stake, index_membership, financing_dilution`.
Clauses are deliberately qualitative and the prompt carries **no numeric bound** (the S28
anchoring lesson: a bound the model can see is an anchor). Round 2 adds a second axis, **clause
position** — each pair asked with the causal fact at the END (round 1's convention) and at the
FRONT — as the control for the "it just moves with the last clause read" attack.
Decider `deepseek-chat`, temperature 0.1, max_tokens 400, via `backend.services.llm_swarm.default_llm_call`;
output keys `p_up_21d`, `exp_return`, `downside_5pct`, `confidence`, `reason`.
**The canary:** 8 extra pairs whose flipped fact cannot move a price a month out (round 2: IR email
domain, lobby paint, coffee vendor, careers-page stock photos, an unrelated law-firm partner hire,
a chat-channel rename, the holiday-party venue, decorative signage). `CANARY_TOLERANCE = 0.05`;
in `grade_pair`, `canary_moved = abs(d_p_up) > CANARY_TOLERANCE`. The canary rate is "the rate at
which the decider manufactures a view out of nothing", and it is what makes a monotonicity share
mean anything.
**The monotonicity grader:** `grade_pair()` (round 2 line 405; round 1 line 307), aggregated by
`summarise_position()` / `summarise()` and `compare_positions()`. GOOD minus BAD on three fields,
all three must agree: `d_p_up > 0`, `d_exp_return > 0`, `d_downside >= 0` (note the `>=`).
**Results:** round 1 — 40 pairs, monotonicity 1.0/1.0/1.0, canary **0.125**, mean |Δp_up| 0.3695;
round 2 END — 40 pairs, 1.0/1.0/1.0, canary **0.0**, 0.301; round 2 FRONT — 15 pairs, 1.0/1.0/1.0,
canary 0.125, 0.2913. Position verdict: **POSITION-INSENSITIVE** — the last-clause hypothesis is
not supported (`share_same_sign_both_positions` 1.0).
**Cost per exam:** round 1, 96 calls, **$0.014829** (cap $5.00), provider balance $9.36 → $9.36;
round 1 run02, 96 calls, $0.014856; round 2, 142 graded calls, **$0.018406** (whole campaign
192 calls / $0.025525; cap $3.00), balance $9.28 → $9.28. Round 2 also records a first-attempt
refusal: after 50 calls ($0.007121) `research_budget` halted it — "zero-yield rate 100.0% exceeds
40% over 50 resolvable calls … this campaign is buying tokens, not information" — and the refusal
was left standing rather than worked around.

## (c) Era replay / T13 / the historical LLM portfolio manager

**v1 = T13**, terminal repo: `C:\Users\mrthn\aegis-alpha-terminal\scripts\era_replay.py`, library
`alpha\transpose.py`, state `state\era_replay\` (`grade.json`, `windows.jsonl`, `entity_map.json`,
`decisions_{real,real_anon,fantasy,fantasy_b,numbers_only}.jsonl`, `rewritten_*.jsonl`).
Arms are `("real", "real_anon", "fantasy", "numbers_only")` — **there is no diary arm in v1**.
Rewriter `openai` (gpt-5-mini), decider `deepseek` (a different family so it is not reading its own
prose), horizon 21 sessions, benchmark SPY. Nulls: (1) shuffled outcomes (`TP.shuffled_null`, seed
`"aegis-t13-null"`) plus an `null_shuffled_informative` flag that says whether the null could have
failed at all; (2) the NULL basket (equal-weight every name); and a `--parity` pre-gate so the
rewriter is not the source of the variation. Last result — `grade.json` graded 2026-08-30T14:50:10Z,
1,001 windows, 150 in the common intersection, k=5, balanced, 11 rebalances: terminal wealth
real 1.67 (t 2.333), real_anon 1.7563 (t 2.074), fantasy 1.5665 (t 2.116), numbers_only 0.9236
(t −0.156), NULL basket 1.1485; `fantasy_minus_numbers_only_wealth` **+0.6429**. **Calibration was
negative in every arm** (skill vs climatology −0.008 to −0.010). **Cost $0.30**
(`docs\FINDING_2026-09-06_ERA_REPLAY_V2.md` §4; `docs\REVIEW_2026-09-04_FABLE51_VERDICTS.md:194`).

**v2**, this repo: `scripts\era_replay_v2.py` (2,235 lines), tests
`backend\tests\test_era_replay_v2.py` (26), finding `docs\FINDING_2026-09-06_ERA_REPLAY_V2.md`,
receipts `backend\data\optimus\continuation_2026-09-06\L10_era_replay_v2_run01.json` (+ `_windows`,
`_pilot`) and cache `backend\data\optimus\era_replay_v2\`. **This is where the diary axis lives**:
a 2×2 of naming × diary — `fantasy_nodiary`, `fantasy_diary`, `realanon_nodiary`, `realanon_diary`
— 192 windows (4 threads × 48 months of 2016-2019), K=8 names, top-3 held, 10 bps/side,
benchmark equal-weight basket of the same 8. Rewriter **gpt-5-nano** (not in
`config.LLM_PRICE_PER_MTOK`, so its telemetry cost is a declared lower bound), decider
`deepseek-chat`. Canary: the decider is asked what year it thinks it is *after* committing the
ranking in the same JSON object. Three nulls, all code-side and free: shuffled companies, shuffled
dates (the calendar null), and same-day paired top-half-minus-bottom-half — the primary statistic.
Last result: **RESULT IMPROVEMENT: NONE. VERDICT: NOISE.** All four arms have negative mean IC
(−0.026 to −0.053) and lose to equal weight (TW 1.459-1.759 vs 1.939); nothing survives BH-FDR;
DSR 0.0805 `WITHIN_SELECTION_NOISE`; SPA p 1.000; PBO 0.386 `SELECTION_IS_FRAGILE`; MDE 8.75%/yr.
Non-P&L findings: the blind held completely (0 of 768 decisions named the true year); blinded,
`deepseek-chat` assumes it is 2023-24 (190 said 2023, 53 said 2024, none said 2016-2019); the diary
suppresses the canary (declines to guess in 191 of 192 diary windows). The EDGAR 8-K tape was
deliberately excluded as a survivorship leak. **Cost $0.48 of a $5.00 mandate** ($0.3032 gpt-5-nano
telemetry + $0.1785 DeepSeek estimate; provider balance $9.81 → $9.39 on a shared key), reusable at
**$0.0025/window**.
CANNOT DETERMINE: no era-replay/T13 pre-registration exists under `docs\TRIALS\`; the three-era sign
table for v2 is itself marked CANNOT DETERMINE (only 2016-2019 ran). Beware: `docs\BACKLOG.md:45`
uses the label "T13" for an unrelated item.

## (d) The DeepSeek spend gate

**There is no constant or env var anywhere in either repo naming a *per-session* dollar cap.**
There are three independent dollar gates in `aegis-finance` plus a non-dollar justification gate
in the terminal repo, and they read **different ledgers**.

1. **Campaign gate** — `backend\services\llm_research.py`. `CAMPAIGN_BUDGET_USD = 30.00`
   (line 56, hardcoded, no env var). Enforced in `ask()` (lines 187-191): `already = spent_usd(ledger_path)`,
   raise `BudgetExhausted` if `already >= CAMPAIGN_BUDGET_USD`. **`spent_usd()` (lines 103-113)
   sums the `cost_usd` field of every line of the JSONL resolved by `config.build1_path("llm_ledger.jsonl")`**,
   which searches `docs/BUILD1/` then `docs/archive/BUILD1/`. On disk today:
   `docs\archive\BUILD1\llm_ledger.jsonl`, 74 rows, total $0.055435. It returns `0.0` when the file
   is absent — the "a docs move disarmed a budget gate" incident
   (`docs\FINDING_2026-08-30_A_DOCS_MOVE_DISARMED_A_BUDGET_GATE.md`, `backend\tests\test_build1_paths.py`).
2. **Campaign governor** — `backend\services\research_budget.py`, constants in `backend\config.py:2061-2105`:
   `RESEARCH_LLM_ENABLED` (env `AEGIS_RESEARCH_LLM`), `RESEARCH_LLM_MAX_CALLS` (env
   `AEGIS_RESEARCH_LLM_MAX_CALLS`, default 120000), **`RESEARCH_LLM_MAX_USD` (env
   `AEGIS_RESEARCH_LLM_MAX_USD`, default 40.0)**, `RESEARCH_LLM_MAX_ZERO_YIELD_RATE`
   (env `AEGIS_RESEARCH_LLM_MAX_ZERO_YIELD`, default 0.40), `RESEARCH_LLM_ZERO_YIELD_MIN_N = 50`.
   `require()` raises `ResearchBudgetExhausted`; callers `llm_swarm.py:812`, `leakage_probe.py:813,934`,
   `architecture_arena.py:88`. It reads **`llm_telemetry.spend()`** →
   `backend\services\llm_telemetry.py:76-77`: `LEDGER_DIR = backend/data/optimus`,
   `LLM_CALLS = LEDGER_DIR / "llm_calls.jsonl"` (~52 MB, mtime today). Overridable via env
   `AEGIS_LLM_TELEMETRY_PATH` (`config.py:1926`).
3. **Nightly ceiling — the closest thing to a per-session cap** — `backend\services\investigator_night.py`:
   `NIGHTLY_MAX_USD = 12.00` (line 61), `NIGHTLY_MAX_CALLS = 3_000` (line 62),
   `WORST_CASE_CALL_USD = 0.05` (line 148), `SPEND_KEY = "total_cost_usd"`. Class `SpendGovernor`
   reserves before transmitting under a threading lock; `NightlyBudgetExhausted`;
   `assert_production_invocation` refuses a run whose `max_usd` overrides the registered value.
   `_spend_since()` → `llm_telemetry.spend(since=…)`, same `llm_calls.jsonl`, and it **raises**
   rather than defaulting to 0.0 if the ledger is unreadable.
4. **Terminal repo** — `C:\Users\mrthn\aegis-alpha-terminal\alpha\spend.py`. Ledger
   `state\llm_spend.jsonl`; `MIN_CHARS = 30`. **No dollar ceiling**: it refuses calls lacking a
   `WHY_THIS_CALL_CAN_CHANGE_A_DECISION` string of ≥30 chars containing a decision verb.

**The price constants — there are TWO tables and they disagree.**

*Table A, the one the $30 campaign gate prices with* — `backend\services\llm_research.py:58-64`:
```python
PRICE_PER_MTOK = {
    "deepseek-chat":     {"in": 0.27, "out": 1.10},
    "deepseek-reasoner": {"in": 0.55, "out": 2.19},
}
DEFAULT_MODEL = "deepseek-chat"
```
`_price()` = `(pin * p["in"] + pout * p["out"]) / 1_000_000.0`.

*Table B, the programme-wide, balance-derived table* — `backend\config.py:1832-1852`
(`LLM_PRICE_AS_OF = "2026-09-05"`):
```python
LLM_PRICE_PER_MTOK = {
    "deepseek-v4-flash":  {"in": 0.169413, "cached_in": 0.00338826, "out": 1.284835},
    "deepseek-v4-pro":    {"in": 0.526390, "cached_in": 0.00438659, "out": 3.992166},
    "deepseek-chat":      {"in": 0.169413, "cached_in": 0.00338826, "out": 1.284835},
    "deepseek-reasoner":  {"in": 0.169413, "cached_in": 0.00338826, "out": 1.284835},
    ...
}
```
Derivation is machine-readable in `LLM_PRICE_DERIVATION` (config.py:1856+): two-rate linear solve
on provider-balance windows, derived 2026-09-05, receipt
`backend\data\optimus\continuation_2026-09-06b\C3_deepseek_price_derivation_run01.json`,
script `scripts\c6b_deepseek_price_derivation.py`, source of truth
`backend\data\optimus\deepseek_balance.jsonl`. The old table was 1.2101× off on input and
**4.5887× off on output**. `cached_in` is 50× cheaper than a cache miss, which makes a shared long
prompt prefix worth more than any other cost optimisation available.
**Live discrepancy worth flagging:** `llm_research.PRICE_PER_MTOK` never imports
`config.LLM_PRICE_PER_MTOK`, so the $30 gate still prices `deepseek-chat` at 0.27/1.10.
Also note `deepseek-chat` and `deepseek-reasoner` are **silent server-side aliases for
deepseek-v4-flash** — any experiment whose arms were "chat vs reasoner" compared v4-flash with itself.

## (e) Capital allocator v0

File `C:\Users\mrthn\aegis-finance\learner\allocator.py` (1,007 lines); runner
`scripts\allocator_run.py`; tests `backend\tests\test_allocator.py` and
`backend\tests\test_allocator_refuses_void_receipts.py`. Commit `2a16ad0`, 2026-09-04.
**Objective** (line 51, implemented in `utility_of()` line 651):
`U_i = E[R_i − R_bench] − l1·CVaR_i − l2·Costs_i − l3·Uncertainty_i`, with
`PERSONALITIES = {preservation: l1 .50/l2 1.0/l3 2.00/max_sleeve .25, balanced: .25/1.0/1.00/.40,
aggressive: .10/1.0/0.50/.60, extreme_growth: .05/1.0/0.25/.80}`, `GROSS_CAP = 1.0`,
`CODE_VERSION = "capital_allocator_v0/2026-09-04"`. CVaR is `|max drawdown|` as a v0 proxy.
A sleeve is funded only when `U_i > U_bench`; positive-margin sleeves split `GROSS_CAP` in
proportion to their margin, clipped at `max_sleeve_weight`. Cash is thesis-gated: a positive cash
margin without an explicit bearish thesis is recorded, not funded.
**Inputs**: one PotentialUniverse vintage (`backend\data\optimus\potential_universe\<day>.jsonl`)
plus four receipts under `backend\data\optimus\tracker_backtest\` —
`revision_6m_cohorts_20260904.json`, `learner_v2_20260903.json`,
`learner_v1_model_null_64_20260904.json`, `toxic_band_short_20260904.json`; sleeve arm constant
`REV_ARM = "cohort_H6m_falsifier_toxic_leftband_mktpark_25bps"`. Stdlib-only imports by design.
**Output**: `write_decision_artifact()` → `backend\data\optimus\decision_artifacts\<day>_<personality>.json`;
on disk `2026-09-02_balanced.json` and `2026-09-02_aggressive.json`. Five sleeves always print,
gated ones at weight 0 (`revision_6m`, `learner_v2_monthly`, `toxic_band_short` gated
`NOT_DEPLOYABLE_NO_BORROW_DATA`, `benchmark_SPY`, `cash`), each with a `binding_constraint`, plus a
`__residual__` row documenting where the unused dollar went.
**"SHADOW ONLY" is four mechanisms, not a flag.** (1) verbatim constants carried into every
artifact — `LICENCE = "PRODUCT_EXPERIMENT (shadow)"` and
`AUTHORITY = "SHADOW_ONLY — this artifact places nothing and nothing reads it for execution"`,
pinned by `test_authority_field_is_verbatim`; (2) no order path exists — no broker client, no
`submit_order`, no execution-repo import; (3) a regex source scan as a failing test
(`test_allocator.py:254-290`, `_FORBIDDEN = alpaca|submit_order|brokerage|aegis-alpha-terminal|alpha\.universe|alpha\.brains|TradingClient|OrderRequest`,
docstrings excluded so lineage citations are allowed); (4) an AST stdlib-only import audit
(`_STDLIB_OK = {__future__, hashlib, json, datetime, pathlib, typing}`). There is no execution flag
to flip and no dry-run boolean — isolation is enforced by tests.

## (f) The tracker watchlist

**Size today:** the latest nightly is **2026-09-02, five days stale**.
`C:\Users\mrthn\aegis-alpha-terminal\state\tracker\2026-09-02.jsonl` = **3,056 rows** (2.29 MB;
2026-09-01 had 3,059). `state\tracker\latest.json` (schema `tracker-1`, generated 2026-09-02T07:04:49Z):
`n_symbols 3056`, `n_with_coverage 3022`, `n_with_target 2955`, **`n_candidates 806`**,
status histogram `{STRONG_BUY 15, BUY 791, SELL 882, WATCH 1368}`. Also in that directory:
`profiles.json` (permanent sector/market-cap cache) and `transitions.jsonl` (27,537 rows).
Writer `scripts\tracker.py` ("rebuild the whole-market watchlist, once a day, and keep it"),
nightly job `python -m scripts.tracker --refresh`. Universe = `universe.load()` UNION the ownership
attention watchlist (`state\research\ownership\attention_watchlist.json`); unioned names carry
`universe_source: "ownership_attention"` vs `"screen"`. Row keys: `symbol, day, observed_at, close,
high_60d, ret_12m, sessions, rec_counts, rec_period, rec_status, mean_target, target_high,
target_low, target_source, target_status, n_analysts_yf, median_dollar_volume, dv_bucket,
market_cap_usd, realised_vol_20d, days_to_catalyst, days_to_catalyst_units, sector, exchange,
tradable, shortable`.
**The potential list:** `learner\potential_universe.py`, run by `scripts\potential_universe_run.py`,
tested by `backend\tests\test_potential_universe.py`; output
`backend\data\optimus\potential_universe\2026-09-02.jsonl` = 1 header + 3,056 scorecards (6.37 MB;
only vintage on disk). `SCORECARD_KEYS = (symbol, day, observed_at, pit, identity, engine_prior,
learner_v1, learner_v2, p_beat, state, disagreement, execution, days_to_catalyst, falsifiers)`;
`HEADER_KEYS = (artefact, version, licence, day, generated_at_utc, broker_authority, motivation,
source, champion, conventions, field_readability, whole_universe_refusals, counts,
graded_like_a_book, schema)`; `ENGINE_VERDICTS = (unreadable, no_opinion, toxic_ge_5, sub_floor,
admitted_shadow)`; `CAPACITY_TIERS = (CANNOT_DETERMINE, NONE, OBSERVE_ONLY, FULL)`. It reads the
terminal's tracker file read-only and declares `broker_authority: "NONE -- this file is written,
never sent."` 2026-09-02 counts: unreadable 109, no_opinion 2, toxic_ge_5 7, sub_floor 2355,
admitted_shadow 583; `learner_v2` and `state` are whole-universe refusals at 3056/3056.
**OBSERVE_ONLY** has two parallel, deliberately un-imported definitions. Authoritative:
`aegis-alpha-terminal\alpha\universe.py::execution_authority` (line 144) with
`MIN_DOLLAR_VOLUME = 3_000_000.0`, tiers `UNKNOWN / NONE / OBSERVE_ONLY / FULL`, size-aware execute
floor via `book_size_usd`, `CANNOT_DETERMINE` on a failed derivation. Re-derived in
`learner\potential_universe.py:160-171`: `OBSERVE_FLOOR_USD = 20_000.0`,
`EXECUTE_FLOOR_USD = 3_000_000.0`, `MAX_ADV_PARTICIPATION = 0.01`,
`LIQUIDITY_COLUMN = "median_dollar_volume"`; `capacity_of()` line 265. OBSERVE_ONLY means
observable and gradeable, at most 1% of ADV transactable — "a fact about our size, not about the
company". **In practice the tier is empty**: the 2026-09-02 vintage is
`{CANNOT_DETERMINE 0, NONE 0, OBSERVE_ONLY 0, FULL 3056}` because the tracker screen applies the
$3m floor upstream. Populating it was attempted and **refused** —
`backend\data\optimus\night_lab_2026-09-07\N3_populate_observe_tier.json`: "live population needs a
network call to the venue and broker credentials, outside this lane's offline scope"
(`scripts\n3_size_aware_floors.py:774-799`). Consumers that exclude OBSERVE_ONLY names:
`learner\evaluate.py:46`, `learner\neural_long.py:653`, `learner\shadow.py:75`,
`scripts\learner_v2_run.py:597`.
**STATE_SEMANTICS is a constant, not a doc** — `learner\potential_universe.py:139-145`, quoting
"broken-lottery-ticket: mean −4.9%/3m t −3.4, worst-5% −75%, big-upside freq 21.7% — the
lost-winners address", receipt
`backend\data\optimus\tracker_backtest\unsupervised_states_20260903.json`. It is embedded into
every vintage's header (line 577) and exported (line 779). It exists **only in aegis-finance** —
an exhaustive grep of the terminal repo returns zero hits. **Known-stale**: the four states were
demoted to informational-only (final verdict CANNOT_DETERMINE; null 1 p 0.000, null 2 p 1.000,
null 3 p 0.005) in `backend\data\optimus\night_lab_2026-09-07\N5_states_third_null.json`, and
`docs\BUILD_NIGHT_LAB_2026-09-07.md:109` records that STATE_SEMANTICS "is already inert but its
text quotes null 1 alone and reads as validated". Not yet corrected.

## (g) `docs\MURAT_2026-09-05_INPUTS.md`

The file exists. §4 "Typed hypotheses (each with a falsifier; entered into `human_theses`)" holds
seven rows (lines 77-83), each with `hypothesis`, `direction / horizon`, `falsifier`:

| id | hypothesis (title) |
|---|---|
| H-2026-09-05-LULU | big one-day drop on a large cap bounces |
| H-2026-09-05-GPRO | pivot/attention keeps the move going |
| H-2026-09-05-ADSK | "industry standard" software recovers after a drawdown |
| H-2026-09-05-REVERSAL | biggest gainers/losers reverse next day |
| H-2026-09-05-OPTIONS | call activity / open interest leads the stock and its peers |
| H-2026-09-05-POLY | prediction-market belief changes lead sector returns |
| H-2026-09-05-PSYCH | 52-week-high proximity (anchoring) predicts continuation |

**Brokerage digests:** §2 "Brokerage 'First look at the market' digests (verbatim summaries)"
records **two entries, identified only by date — 2026-09-02 and 2026-08-25**. §3 attributes the
lists to "source: brokerage screen, unverified". **No broker or newsletter is named anywhere in the
file — CANNOT DETERMINE which house they came from** (the Turkish content — BIST 100, TUPRS/KCHOL,
AKBNK — implies a Turkish broker, but the file does not say so). Other named sources: the
ingestion path `alpha/human.py` → `state/human_theses.jsonl`, and receipt id `band_horizon_20260905`.

## (h) `scripts.thesis` and the prediction-book seal chain

CLI `C:\Users\mrthn\aegis-alpha-terminal\scripts\thesis.py` (`--list`, `--example`, or record).
The row itself is `@dataclass(frozen=True) class Thesis` ("HUMAN_THESIS_ARM_v1") in
`C:\Users\mrthn\aegis-alpha-terminal\alpha\human.py`. **Fields:** `author`, `symbol`,
`direction` (`up|down|none`), `magnitude` (`wider|narrower|unknown`), `catalyst`,
`catalyst_at_utc`, `horizon_days`, `reason`, `falsifier`, `expected_move` (signed fraction of
spot), `conviction` (default 1.0), `stated_at_utc`, `evidence` (dict). Derived: `claim` →
`distribution | direction | dispersion`; `brain` → `f"human:{author}"`; `thesis_id()` = first 16
hex of sha256 over the sorted-key JSON; `width_multiplier` → 1.25 / 0.75 / None. `__post_init__`
raises `ThesisRefusal` on: no direction and no width claim; direction without `expected_move`; sign
disagreement; `expected_move == 0` with a direction; falsifier < 15 chars; reason < 10 chars;
conviction outside (0, 1.5]; non-positive horizon; and **`stated_at >= catalyst_at`** ("a thesis
recorded after its own catalyst is a memory"). Storage: append-only
`state/human_theses.jsonl`, with a committed read-only seed at `docs/seed/human_theses.jsonl`;
`load_all()` de-dupes on content hash and silently drops a row that no longer validates.
**Grading is not in `human.py`** — `to_forecast()` converts it to an `alpha.brains.base.Forecast`
under brain `human:<author>` and it enters the ordinary counterfactual machinery; `sd` is a
placeholder resolved per-structure at `runner.effective_sd`.
**Prediction book:** `scripts\prediction_book.py` (+ `prediction_book_sync.py`,
`tests_smoke_prediction_book.py`). One file per ET trading day at `state/predictions/<day>.json`,
append-only log `state/predictions/seals.jsonl`. `_sha(payload)` = sha256 over
`json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",",":"))`, stored back as
`content_sha256`. `seal(book)` (line 1133) first runs `check_contracts()` and raises
`ContractRefusal` if any portfolio lacks a valid contract or any holding lacks a contract stamp;
if the day file exists with a different hash it writes a sibling
`<day>.resealed_HHMMSS.json` and logs a `RESEAL:` note — the original is never overwritten.
`_append_seal` writes `{day, sealed_at_utc, file, content_sha256, claims, considered, note}`.
**Important nuance: this is a hash LOG, not a linked hash chain** — there is no `prev_hash` field
anywhere in `_append_seal` or in the on-disk rows. Tamper-evidence comes from self-hash +
`verify()` (line 1168, re-hashes every book, prints `ok`/`TAMPERED`) and from append-only reseal
records. **A true prev-hash chain: NOT FOUND.**
**Grading a sealed book** — `grade(day, horizon=HORIZON_SESSIONS)` (line 1205): outcome metric is
**SPY-relative return, next-session OPEN → CLOSE n sessions later**; `hit = (ret − benchmark) > 0`;
`HORIZON_SESSIONS = 21` with `CHECKPOINT_SESSIONS = 5`; only rows with `claims: True` are graded;
returns `hit_rate`, `mean_rel`, and `reads_as_evidence: len(hits) >= 20` (under 20 it is stamped
"a receipt, not a result"). The per-row falsifier is generated text naming the 21-session
SPY-relative test.
Related: `alpha\contract.py` — `@dataclass(frozen=True) class Contract` with `REQUIRED_FIELDS`
(line 86): `book, expected_horizon_sessions, min_normal_hold_sessions, thesis_expiry,
hard_falsifiers, risk_budget_usd, emergency_exit_reasons, profit_target_frac, stop_frac, profile,
min_edge_over_stop, source`; typed exit enum `THESIS_INVALIDATED, DATA_ERROR, HARD_RISK_LIMIT,
EXECUTION_CORRECTION, DEADLINE, EXPLICIT_EVENT_STRATEGY_EXIT`. Sealed inside `content_sha256` via
`_contract_block` and re-stamped onto every holding; `alpha\exits.py` reads it back off the entry
ledger row.

## (i) Strategy genomes

**There are two different Genome dataclasses; they are not the same object.**

**1. `PortfolioGenome` — `C:\Users\mrthn\Aegis module\aegis_brain\arena\genome.py`.**
`@dataclass(frozen=True)`; fields: `genome_id`, `signals: tuple[tuple[str, float], ...]`,
`signal_family`, `segment` ("small"), `top_k` (25), `weighting` ("equal_weight"), `max_weight` (1.0),
`rebalance_months` (1), `cash_floor` (0.0), `reliability_floor` (0.0), `cost_model` ("flat25"),
`hypothesis`, **`distinct_from: tuple[str, ...]`** ("which corpse this genome is NOT, when it lives
near one"), `tags`. `__post_init__` validates weighting ∈ {equal_weight, score_weight, inverse_vol,
reliability_shrunk, fractional_kelly}, segment ∈ {small, largemid, all}, `top_k >= 3`, ≥1 signal,
`cash_floor ∈ [0,1)`, `max_weight * top_k >= 0.999`. `genome_hash()` = 12-hex sha256 of `as_dict()`
excluding `genome_id`, `hypothesis`, `tags`. Same file: `signal_sets()`, `CONSTRUCTION_ARRAY`
(8-row orthogonal array), `generate()`, `manifest()` (schema `arena-manifest-v1`).
**It does not exist in `aegis-finance` backend/, engine/ or learner/.**

**2. `Genome` — `C:\Users\mrthn\aegis-finance\learner\growth_lab.py:384-394`** — the one the Growth
Book mutates. Fields: `genome_id`, `family`, `base` (base rule key), `spec: dict`,
`overlay: tuple[str, ...]`, `parent_ids: tuple[str, ...]`, `mutation_history: tuple[str, ...]`, `note`.

**The G3 LLM mutation proposer:** `C:\Users\mrthn\aegis-finance\scripts\growth_g3_mutations.py`
("G3 — THE MUTATION ROUND. The LLM proposes; code decides; the corpse is named"). `propose()` calls
`backend.services.llm_research.ask(prompt, purpose="growth_g3_mutations", temperature=0.0,
max_tokens=4000)` on DeepSeek, with a job-local `LLM_CAP_USD = 3.00` measured as the delta of
`LR.spent_usd()`; `MAX_MUTATIONS = 20`, `N_PARENTS = 5`. `MUTATION_GRAMMAR` (lines 72-85) is a
closed key/range set — `pred_col`, `k (10,150)`, `weight`, `hold_k (11,400)`,
`overlay [dd, tg, bsc]`, `dd_lookback_months`, `dd_scale`, `dd_floor`, `bsc_lookback_months`,
`bsc_cap` — and an out-of-grammar key or out-of-range value is **refused, not clipped**. Key
functions: `validate(child, parents, corpse_ids)` (160), `child_genome()` (197), `build_prompt()`
(268), `corpses()` (126, derived from `signal_registry` NEVER_PICKS grades, never re-typed).
Receipts `backend\data\optimus\growth_book\G3_mutations.json` and
`G3_mutations_round01_ALL_REFUSED.json` — round 1 was 20/20 refused because the prompt printed the
CELL id, not the GENOME id. Tests `backend\tests\test_growth_g3_validator.py`.

**`assert_distinct_from_corpses`** — `backend\services\research_daemon.py:381-398`. It does **not**
compare mechanisms: if `job.parent_corpse_ids` is empty it returns; otherwise it raises `JobRefused`
unless `job.distinct_claim` has ≥5 words ("a distinct claim is a sentence, not a feeling"). Called
from `ResearchDaemon.submit()` (line 446). G3 reimplements the same rule inline at
`growth_g3_mutations.py:160-175` because `scripts/lint_prereg.py`, referenced by
`llm_research.generate_hypotheses`'s docstring, **does not exist in the repo** — the receipt records this.
**The real mechanistic comparator is elsewhere:** `backend\services\research_gym\scope.py:450`,
`corpse_check(...)`, which compares `rule_exact(spec)` = (feature, op, repr(value)) and
`rule_shape(spec)` = (feature, op), plus the `(proposed_action, default_action)` pair and scope —
exact rule + same actions + same scope → BLOCKED; same shape → BLOCKED unless prospectively
declared, else RESURRECTION_TAX; shape-or-action overlap only, not prospectively declared →
BLOCKED; otherwise ALLOWED_WITH_PARENT_CONTROL with the parent corpse as a mandatory control. Only
`REFUTED_IN_SCOPE` and `STRUCTURALLY_CLOSED` corpses can block; the rest are named in
`corpses_that_block_nothing`. Tests `backend\tests\test_research_gym_scope.py`.

## (j) Evidence memory and registry `conditional_evidence`

Module `C:\Users\mrthn\aegis-finance\learner\evidence_memory.py` (`VERSION = "evidence-memory-1"`).
Files: store `backend\data\optimus\learner\evidence_memory.jsonl` (65 MB, 101,992 observations);
snapshot `…\evidence_memory_state.json`; **supersession log
`…\evidence_memory_supersessions.jsonl`** (438 B, one rule today); registry target
`backend\data\signal_registry.yaml`, `conditional_evidence:` block at **lines 921-1152** between
`# ═══ BEGIN conditional_evidence …` / `# ═══ END conditional_evidence ═══` markers. Tests
`backend\tests\test_evidence_memory_superseded.py`, `backend\tests\test_evidence_registry_export.py`.
**Observation row schema** (`observe()`, lines 154-181; every key always written):
`screen_cleared, controlled_t, holm_p, utc, version, family_id, cell, job, run, variant, n_months,
sharpe, dsr, spa_p, pbo, verdict, powered, years_needed_for_t2, years_observed, eras,
gross_beats_market, net_beats_market, note`. States: `IDEA, CONDITIONAL, SUPPORTED,
REGIME_SPECIFIC, COST_KILLED, REFUTED`; bars `DSR_BAR .95`, `SPA_BAR .10`, `PBO_BAR .5`,
`MIN_PASSES_TO_PROMOTE 2`, `MIN_PASSES_TO_REFUTE 3`. `evidence_key()` collapses re-runs of a
deterministic job to one observation.
**Registry export row schema** (`registry_rows()`, one row per (family, era, state)):
`family, era, state, n, sharpe, dsr, spa_p, pbo, verdict, cells_in_this_state,
representative_cell, distinct_observations, recorded_verdict, note`. Verdict vocabulary:
`NOVEL, DECAYED, SCREEN_SURVIVOR, SCREEN_ONLY, CANNOT DETERMINE, NOISE, REFUTED`. `EXPORTED_STATES`
excludes IDEA; `export_verdict()` derives then **caps** at the job's own recorded
NOISE/REFUTED/CANNOT DETERMINE; era slices cap at SCREEN_ONLY; screens can never reach NOVEL.
**Supersession** — `supersede()` (lines 187-224). Nothing is deleted; an explicit reasoned rule is
appended to `evidence_memory_supersessions.jsonl` with schema
`{utc, family_id, before_utc, cell_prefix, why}`. `family_id` is required (else the rule would
silently retract the whole memory); `why` is required ("an unreasoned retraction is
indistinguishable from data loss six weeks later"); `_check_before_utc()` refuses a partial
timestamp because `is_superseded` compares ISO strings lexicographically; `before_utc = None` means
the whole family for all time. `read_supersessions()` **raises** on an unparseable line (unlike
`read_all()`, which skips) — a dropped supersession would re-admit a retracted experiment.
`live_rows()` is the single call site where rules are applied (`snapshot()`, `state_of()`,
`registry_rows()` all route through it); it returns `(kept, dropped_by_reason, per_rule_effect)`
and attaches a `"WARNING"` to any rule that excludes zero observations ("a retraction that matches
nothing is a broken guard, not a lax one"). Asymmetry: `superseded_families()` bars an entire
touched family from the *export* (conservative), while row-level supersession only drops
pre-boundary observations from the *state*; excluded families are named in `families_excluded`
with `reason` (`SUPERSEDED` / `RETRACTED`), `why`, `cells_withheld_by_state`,
`observations_row_superseded`. A live verdict string containing `"RETRACT"` also excludes its family.
The one rule on file today: family `weekend-W7-matched-loser`, before
`2026-09-05T05:40:00+00:00`, cell_prefix null — "W7 matched-control LEAK: the control pool excluded
future LOSERS as well as winners … Fixed in 35915db; `log_dollar_vol_20d` went Holm 0.000178 → 0.158."
Export safety: `to_registry()` edits the YAML as **text** between the two markers (never
round-trips through a loader, preserving 56 comment lines and CRLF endings), re-parses, and refuses
to write if any block other than `conditional_evidence` changed. The block is structurally
read-only for the PM until B9 — `backend\services\signal_registry.py` builds `Registry` from exactly
five top-level keys and has no field for it. Helper: `scripts\write_superseded_sidecars.py`.

---

# PART C — COST OF A 25-YEAR QUARTERLY LLM NEWS REPLAY

**Constants file: `C:\Users\mrthn\aegis-finance\backend\config.py`, `LLM_PRICE_PER_MTOK`
(lines 1832-1852), `LLM_PRICE_AS_OF = "2026-09-05"`.** Rates are USD per **1,000,000** tokens.
`deepseek-chat` is a server-side alias for `deepseek-v4-flash`, and both carry:

    in = $0.169413 / Mtok    cached_in = $0.00338826 / Mtok    out = $1.284835 / Mtok

Formula: `cost = (tokens_in / 1e6) * in + (tokens_out / 1e6) * out`.

### 100 names × 4 quarters × 25 years = 10,000 calls

**At 1,500 in / 300 out:**
- input: 10,000 × 1,500 = 15,000,000 tok = 15.0 Mtok × $0.169413 = **$2.5412**
- output: 10,000 × 300 = 3,000,000 tok = 3.0 Mtok × $1.284835 = **$3.8545**
- **total ≈ $6.40**

**At 3,000 in / 600 out:** exactly double the token counts →
30.0 × 0.169413 = $5.0824 plus 6.0 × 1.284835 = $7.7090 → **total ≈ $12.79**

### 1,000 names × 4 quarters × 25 years = 100,000 calls

Ten times the above:
- **1,500 / 300 → ≈ $63.96** (150 Mtok in = $25.41, 30 Mtok out = $38.55)
- **3,000 / 600 → ≈ $127.91** (300 Mtok in = $254.12/10 = $50.82, 60 Mtok out = $77.09)

### The prefix-cache variant — the number that actually matters

`cached_in` is **50× cheaper** than a cache miss, and config.py says so explicitly: "sharing a long
common prefix across the arms of an experiment is worth more than any other cost optimisation
available to us." If the whole input were a cache hit (an upper bound on the saving; in practice
only the shared prefix is):

| calls | in/out | full price | all-input-cached |
|---|---|---|---|
| 10,000 | 1,500 / 300 | $6.40 | $3.91 |
| 10,000 | 3,000 / 600 | $12.79 | $7.81 |
| 100,000 | 1,500 / 300 | $63.96 | $39.05 |
| 100,000 | 3,000 / 600 | $127.91 | $78.11 |

The output leg dominates in every cell — output is 7.58× the input rate — so trimming
`max_tokens` buys more than trimming the prompt.

### If the legacy table were used instead

`backend\services\llm_research.py:58-64` still carries `deepseek-chat: {in 0.27, out 1.10}`. Under
that table the same four cells are $7.35 / $14.70 / $73.50 / $147.00. This table is **known wrong**
(config.py: the old table's output leg was off by 4.5887×) but it is the one the $30
`CAMPAIGN_BUDGET_USD` gate prices against, so a run of this size would trip that gate at a
different point than its true cost implies.

### Current DeepSeek balance (from receipts; no API call was made)

- **$9.28** — most recent, `backend\data\optimus\night_lab_2026-09-07\N6b_fantasy_exams_round2.json`,
  `spend.balance_usd_before / balance_usd_after` both 9.28, receipt generated 2026-09-06T17:11 UTC.
- **$9.38** — `backend\data\optimus\deepseek_balance.jsonl`, last row, `read_at`
  2026-09-05T12:23:33 UTC, `label: "cost_audit"` (this file is the declared source of truth for the
  price derivation). Prior rows: $13.36 (2026-09-05T11:58), $23.99 (2026-08-24).
- Corroborating: the era-replay-v2 receipt records $9.81 → $9.39 across its run.

**So the balance is roughly $9.28-$9.38.** A 10,000-call replay at 1,500/300 (**$6.40**) fits, with
little margin. **A 100,000-call replay at any token size does not fit** — $63.96 is ~7× the
balance, and the 3,000/600 variant is ~14×. It also exceeds `NIGHTLY_MAX_USD = 12.00` and the
`CAMPAIGN_BUDGET_USD = 30.00` gate, and would need `AEGIS_RESEARCH_LLM_MAX_USD` (default 40.0)
raised as well.
