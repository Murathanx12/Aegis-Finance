# ROADMAP 2026-09-11 — root first: the operator board, whole-market news, and the loop that grades itself

**Status:** TIER 1 — the ONE current roadmap (replaces the 09-10 model/news/event-net
roadmap as the active file; that file's three lanes are folded in below as L and E).
**Licence:** `PRODUCT_EXPERIMENT` throughout. Nothing here promotes anything.
**From:** Fable 5.1, 2026-09-11, after Murat used the desktop app for two sessions.
**Read with:** `AEGIS_STRATEGIC_INVARIANTS.md` (the sixteen points),
`AEGIS_VISION_2026-08-28_MURAT_IN_HIS_OWN_WORDS.md` §6 (today's intent, verbatim),
`HANDOFF_2026-09-11_FABLE_TO_OPUS_BUILD_PLAN.md` (the build order, for the terminal).
**Method note:** five Sonnet agents did the surveys (two on the code, three on the
web); this file is the synthesis. Every number below names its receipt or its
file:line; every external claim carries a URL in the agent notes (§2).

---

## 0. RESULTS SCOREBOARD (unchanged by this document — it is a plan)

| | |
|---|---|
| **RESULT IMPROVEMENT** | **NONE.** No strategy moved. This session verified and planned; it built nothing. |
| best historical net strategy vs market | none surviving its own control above the tradability floor |
| best forward paper strategy | none — six books −4.43% aggregate in week one vs SPY −0.12% (09-09); no newer read |
| only live lane | **R2** (local 7B, anonymised monthly digest): +16.19%/yr over its shuffled-digest control, t 3.92, 112 blocks; net CANNOT DETERMINE; **panel B still `PENDING_MODEL`** (`night_factory_2026-09-10/R2_widened_panelB_run01.json`: port 8080 refused) |
| independent selectors with evidence | **one** — still the reason no router is permitted |
| what this session found | **the packaged app runs without a single API key** (§1 R1), and the tour repeats because the window wipes its own storage on every launch |
| LLM spend | $0.00 this session (no model calls; five Sonnet agents) |
| tests / CI | not re-run; CI **green on `87febf1`**; tree clean at start |
| deadline | `learner/evidence_memory.jsonl` **65.16 MB** (62.14 two days ago; GitHub rejects at 100) |

---

## 1. THE ROOTS — five problems, stated as roots, not as products

Murat, 2026-09-11: *"we are always focusing on so much of the product, but never
the problem. What are the problems? We need to go to the root."* Here they are.
Each one is a cause; the lanes in §3 are the effects we build.

### R1. The app you click does not run the code you read.

Verified today, from the source:

- `backend/config.py:21` sets `PROJECT_ROOT = Path(__file__).parent.parent` and
  `:97` calls `load_dotenv(PROJECT_ROOT / ".env")`. Inside the PyInstaller build
  `__file__` is `<dist>/_internal/backend/config.py`, so `PROJECT_ROOT` is the
  bundle, and `desktop/AegisDesktop.spec` never copies `.env` in (it walks
  `backend/` only). **Every key is absent inside the .exe**: DeepSeek, FRED, FMP,
  Polygon, NVIDIA. `llm_analyzer.is_available()` is False app-wide, FRED panels
  log "skipping" and continue, `free_inference.DEFAULT_BACKEND = "nvidia_nim"`
  (`free_inference.py:77`) fails on any caller that does not name `local_gguf`.
  From source (`python -m desktop.aegis_desktop`) the same code has every key.
  That is why "some of the APIs don't seem connected": nothing is broken, the
  keys are in a file the frozen build cannot see. It is the **sixth** instance
  of the 09-10 handoff's defect family #14 ("a path that resolves differently
  when frozen"); `control.py:60` and `llama_server.py:65` already carry the fix
  (`AEGIS_REPO_ROOT`), `config.py` does not.
- `desktop/aegis_desktop.py` calls `webview.start(when_ready)` with no
  `private_mode`/`storage_path`; pywebview 6.2.1 defaults to
  `private_mode=True`, so `localStorage` — where both `aegis.guide.dismissed.v1`
  (`components/desktop/guide.tsx:33`) and `aegis-tour-done`
  (`first-run-tour.tsx:8`) live — is discarded when the window closes. **The
  guide will reappear on every launch until this is one argument.** The storage
  path must be outside the bundle (family #14 again).
- The backend the .exe serves is the **bundled copy** of `backend/`; a `git pull`
  updates the night scripts (they run under the real interpreter via
  `control.job_python()`) but not the API. So "the app should always update
  itself" cannot be true of this build shape at all: a fix to the backend needs
  a 1.1 GB rebuild.
- The "~30 news": no array in the code exceeds 15 (`routers/news.py:63`
  `all_news[:15]`; the brief caps at 5 movers × 3). The `/news` page renders the
  GDELT block + 15 headlines + sector rows, which reads as ~30 items. The count
  is not the defect; the defect is that the page answers no question an
  operator has ("which sources, how fresh, what did we miss?").

**Root:** the product is a frozen snapshot of a moving source tree, with three
path resolutions that differ from source. **Every one of them was silent.**

### R2. There is one selector with evidence, and the outside world has none.

Five months of honest measurement: every apparent edge has been beta, one era
(1999-2007, or five rebound months), a look-ahead, or below the tradability
floor. Murat calls the backtests "terrible"; the external survey (§2.2) says the
honest word is **normal**: no open-source repo or hackathon project surveyed has
a multi-year, cost-inclusive, out-of-sample record beating SPY. TradingAgents
cites a 30-day run; FinMem beat buy-and-hold on TSLA and lost on AMZN; the
Alpaca hackathon results page is not populated. Nothing to copy; our evidence
bar is already above theirs. **The root is not the backtest engine. It is that
the programme has one text reader that works (R2) and no second independent
source of decisions to compare it with** — so no router, no committee, no
"engine and LLM together" is permitted yet (CLAUDE.md bottleneck section).

### R3. The whole-market news loop does not run by itself, and Asia is not in it.

- The collector is in the OTHER repo, on Railway, Alpaca/Benzinga only, and its
  historical backfill **died at 83.6% with no cursor** (S44). Dense text is
  2025-26; CRSP ends 2024-12; every text lane lives in a 21-month window.
- The one join that exists (E1, 339,657 cells) is a **one-shot script**, not a
  nightly appending job.
- GDELT is wired (`news_intelligence.py:38`) as a dashboard block, not as a
  corpus writer with a first-seen stamp. There is no Google News RSS sweep, no
  Chinese/Japanese/Korean source, no HKEX/TDnet/KIND reader, no hiring signal,
  no daily analyst snapshot (Finnhub keeps only four months, so a series that is
  not snapshotted daily does not exist).

**Root:** WORLD SENSORS → EVIDENCE is a dashboard fetch, not a corpus.

### R4. "What we thought vs what happened" exists and does not close on the laptop.

`backend/services/belief_state.py` is exactly that object: `PredictionRecord`
with thesis, counter-thesis, probability, horizon, model, prompt hash; **24,828
rows** in `backend/data/optimus/predictions.jsonl`; graded by `pi_ledger_resolve`
→ `ledger_resolver.resolve_due` → `belief_state.resolve_all` against real
prices, writing `outcome` and `brier`. But: **0 of the 24,828 local rows carry an
outcome** (the graded copy is on Railway), no row is a per-book forecast, no
book has a control twin, and nothing in the desktop app writes a row or shows a
grade. The 54 `docs/TRIALS/*.md` sit a level above and are hand-written.

**Root:** the learning loop's memory is on a server the operator does not see;
the app that the operator sees has no memory.

### R5. Intent enters through Claude Code sessions, not through the product.

No code path turns *"a very high-risk, cheap, industry-focused portfolio"* into
a frozen contract and a paper book. `copilot.py` is Q&A with read-only tools;
`investment_committee.py` composes from pre-registered archetypes;
`pm.py` is GETs plus a journal. `backend/strategy/contract.py` (the frozen,
hashed `Strategy`, 2026-09-07) is the right object and has **no producer but a
session**. The six Alpaca books are one real account each (`alpha/fleet.py`,
six manual setups, six Railway services) — a shape that does not reach "thousands".

**Root:** the human is the only hypothesis generator, and every hypothesis costs
a terminal session.

---

## 2. WHAT THE RESEARCH SAYS (five agent reports, condensed)

Agent notes with URLs: `research_news.md`, `research_backtests.md`,
`research_nn.md`, `audit_services.md`, `survey_paper_books.md` — copied into
`docs/research_notes/2026-09-11/`.

### 2.1 News coverage without an LLM
- **World Monitor** (`koala73/worldmonitor`, 86k stars, **AGPL-3.0**): 500+
  attributed feeds catalogued by provider/tier/licence/method, Python SDK on
  PyPI. Borrow its **source-catalogue schema**, not its backend (AGPL binds a
  public tool). **God's Eye** (`bilawalsidhu/gods-eye-view`, 24.7k, MIT) is a
  geospatial *sensor* dashboard (flights, vessels, fires, quakes), not news;
  its `DATA_SOURCES.md` pattern — one thin fetcher per public API — is the
  reusable part.
- **Best coverage per dollar, in build order:** (1) **GDELT DOC 2.0** — no key,
  65 languages, rolling 3 months, tone + themes; rate-limited in spikes, bulk
  NGrams as fallback. (2) **Google News RSS** per `hl/gl/ceid` (zh-CN, zh-TW,
  ja, ko, en-HK, en-SG) — breadth for Asia; **not point-in-time** (index state,
  not first-seen). (3) **Alpaca/Benzinga** — the only feed with ticker tags and
  a native `created_at`; free with the account we hold; 200 req/min. (4)
  **AKShare** for Chinese sources (Eastmoney/Sina/Xueqiu) before any bespoke
  HKEX/TDnet/KIND scraper. (5) SEC EDGAR full-text + Atom RSS; Finnhub free
  tier for recommendation trends, **snapshotted daily**.
- **Hiring as a signal** (Murat's Adobe/Autodesk/GoPro pivot idea): public ATS
  JSON at Greenhouse/Lever/Ashby needs no key and no login; LinkedIn scraping
  is a ToS violation and stays out. Evidence: Kothari & O'Doherty 2023 (JOE
  ratio → +6.60% next-month annualised excess per 1 sd), Kuehn-Simutin-Wang
  2017 (6%/yr decile spread, t≈3.7), Belo-Lin-Bazdresch 2014 (hiring rate is a
  cross-sectional predictor). Aggregate and cross-sectional, not
  company-pivot — so the pivot story is a **typed hypothesis with a control**,
  not a rule (§3 N-G).
- **Two PIT pitfalls:** stamp everything to UTC at ingest and record
  `first_seen_utc` ourselves; Google News/NewsAPI backfill and edit silently.

### 2.2 How others "beat SPY"
Nobody surveyed clears our own bar (multi-year, walk-forward, gross AND net,
benchmark's own drawdown shown, per era, a t or DSR). What to copy: CPCV,
deflated Sharpe and PBO as the night factory's **stopping rule**; Arnott-Harvey-
Markowitz's protocol as the prereg checklist (already `pre-register-trial`).
What not to copy: any 30-day or single-ticker number. **One new test we owe
ourselves:** Gao-Jiang-Yan 2026 "Lookahead Propensity" (arXiv:2512.23847) — an
LLM's hit rate on pre-cutoff dates collapses right after its training cutoff;
run it on every LLM read over 2015-2024 (DeepSeek and Qwen) before quoting any
such number.

### 2.3 Attention nets for events
The next text design is **not a new encoder** — that is what corpses (1)-(3)
say. Ranked by evidence given our corpses: (a) scale the monthly-digest read
(R2) — the only live lane; (b) **typed-event extraction** by the local LLM
(guidance cut, M&A, FDA, hiring…) → a small tabular head (StockMixer-class,
AAAI 2024, fits 8 GB); (c) one retry of the frozen embedding at a **5-21 day**
horizon with horizon the only changed variable; (d) HAN-style attention over a
company's headline *sequence* only if (b)/(c) show signal; (e) contrastive
price pretraining last (thin stock evidence). Chen-Kelly-Xiu (SSRN 4416687)
finds LLM embeddings beat bag-of-words for returns; Lopez-Lira & Tang's
next-day drift is strongest in small caps and negative news, and its
pre-cutoff half is memorisation. Patents: Google's US10452978 is not known to
be enforced; Apache-2.0 carries a patent grant; nothing constrains a personal
open-source project. Tokenisation: reuse a pretrained tokenizer; feed numbers
as **relative-to-expectation features**, never as tokens. "These are the
probabilities" = **adaptive/non-exchangeable conformal intervals** (plain
conformal drops to ~50% coverage in high-vol regimes); drift = ADWIN-gated
refits graded against a fixed-window control.

### 2.4 Books at scale
Reuse `backend/strategy/contract.py` (frozen `Strategy`, fingerprint =
SHA-256; `CostModel` refuses zero cost by construction), the `paper_nav` sqlite
schema (already keyed by `portfolio_id, date`), and `belief_state` +
`pi_ledger_resolve`. **Not** `alpha/fleet.py` (one broker account per book).
Missing: a per-book cadence scheduler, a natural-language → `Strategy` builder
that the ENGINE validates and freezes, an auto-generated control twin per
book, and a page.

---

## 3. THE LANES — gate-ordered, each with its evidence and its control

Gates outrank dates. Nothing below is dated. Each lane names what blocks it.

### Lane O — the operator board (the app; blocks everything the operator sees)

| id | item | acceptance |
|---|---|---|
| **O1** | **Thin launcher, not a frozen backend.** The .exe becomes a launcher that runs the backend and the shell **from the checkout's own interpreter** (`control.job_python()` already finds it). On launch, with a receipt: `git pull --ff-only` (refuse on a dirty tree, say so), `pip install -r requirements.txt` only when the requirements hash changed, rebuild `frontend/out` only when `frontend/` changed since the last export (hash recorded), then start. This is Murat's "always update itself", and it **retires defect family #14 wholesale**: nothing is frozen but the launcher. PyInstaller packages ~10 MB, not 1.1 GB. | the .exe on a stale checkout pulls, rebuilds only what changed, writes `aegis_desktop.log` lines for each step, and the served `/api/health` reports the checkout's HEAD |
| **O2** | `config.py` dotenv honours `AEGIS_REPO_ROOT` (the same three lines as `control.py:60`); a test walks `backend/`, `desktop/`, `scripts/night_factory*.py` for `Path(__file__)`-rooted opens of `.env`, `data/`, `vendor/`, state files, and lists them against an allow-list. Still needed with O1 (the shell sets the root). | the launcher shows `providers.configured` = the same list as source |
| **O3** | `webview.start(when_ready, private_mode=False, storage_path=<repo>/backend/data/optimus/webview_profile)`; guide **once**, "? Guide" reopens; bump `GUIDE_DISMISSED_KEY` only when the guide changes. | close and relaunch: no guide |
| **O4** | **Home = the developer board**, not the website dashboard. One page: services (backend HEAD, llama phase, network), tonight's queue and last leaderboard, the fleet card (with its standard errors), the coverage card (sources × region × freshness × count, from lane N), the ledger card (open forecasts, graded last night, Brier by model), the code tree (`scripts/`, `learner/`, `backend/services/` — read-only file viewer with `git log -3` per file), and the app log tail. Every number from a receipt. The website's marketing pages stay reachable but are not the landing page in desktop mode. | `/desktop` opens in under 1 s to a page where every card either shows a number with its receipt path or an em dash |
| **O5** | **One click = Morning.** `POST /api/control/morning`: pull news (lane N jobs, incremental), build the digest, mark every paper book, write the pre-open forecast rows (lane B5), refresh the coverage card, then hand the operator the Ask page with today's brief loaded. One receipt for the run; every step's status in it; a step that did nothing says so (invariant 15). | the receipt lists each step with rows written; a network-less run refuses each network step by name |
| **O6** | **Ask Aegis reads the project.** Read-only tools on the local model, retrieval-first: `read_file(path)` bounded to the checkout and `docs/`, `receipt(job, run)`, `leaderboard()`, `night_status()`, `git_log(path, n)`, `fleet()`, `ledger_summary()`, `coverage()`. Router is deterministic (a path or a job id in the question routes to the tool; else `docs/INDEX.md` + the last handoff + today's receipts as context). **No write tool exists**; the AST test extends to "no file open for writing, no subprocess, no broker" in the ask module. Answers quote the receipt path. Second prompt: "what do you think happens today?" answers from the pre-open forecast rows the model itself wrote in O5, so the answer is graded tomorrow. | "what is the NN doing right now?" returns the live N-lane job's log tail and its last receipt line; "look at scripts/night_g3_evolve_v2.py" returns the file's docstring and `git log -3` |
| **O7** | The Ask page starts the model when it is down and the operator asks (`/api/control/llama/start`, wait, then answer) instead of refusing; foreign-server rule unchanged. `R2 panel B` runs from the app once the model is up. | panel B receipt no longer says `PENDING_MODEL` |
| **O8** | **The universe, uncapped** (Murat, 09-11: *"I want it to show all the stocks — first time I opened I saw the 3,000+, and all of our reviews + analyst reviews"*). One board page: every name in the tracker universe (3,056 on 09-09) with our scorecard (the sealed upside × consensus fields the tracker books already read), the analyst consensus snapshot (N-E), the last event and its typed class (L2 when it exists), the book(s) holding it, and our last review sentence with its receipt. Server-side paging and search over the full set; no cap anywhere on the path (`routers/news.py:63`'s 15 was a news-feed cap and stays there). | the page's row count equals the universe file's row count, printed beside it |
| **O10** | **Every stock page and every heavy endpoint works in the desktop app** (Murat, 09-11: "when I search a stock I get 404", "the screener doesn't work"). The static export pre-renders twelve `[ticker]` shells; one `__ticker__` shell served by FastAPI for any symbol fixes the 404 without 3,000 pre-rendered pages. Heavy endpoints return a `computing` state with progress instead of timing out at 45 s now that the warm loops are off on the laptop. **And the screener runs over the full universe on the desktop** — "Stocks Analyzed 56" was `screener_per_sector: 5` × 11 curated sectors (`config.py` ~1121), never the market; desktop mode uses the tracker universe (~3,056 names) with progress, batches, a 24 h cache and the universe's name and row count printed beside the count. The Railway deploy keeps its 80-name cap. | search NVDA → its page; screener shows computing n/3,056 → results; the subtitle names the universe and the horizon actually computed |
| **O11** | **A 52-week price target the analyst way** (Murat, 09-11: "we can't run a 5-year Monte Carlo and then divide it by 5; analysts make 52-week targets; learn how they do it and build the same system"). Today `stock_analyzer.py:147-182` blends a shrunk historical drift 60/40 with the Yahoo consensus 1-year target and feeds the jump-diffusion Monte Carlo over a multi-year horizon; the central number is a simulation mean, not a valuation. New `backend/services/price_target.py`: three legs — justified forward multiple × NTM EPS, a 3-stage DCF-lite with our beta module, and the consensus de-biased by the IBES grading receipt (bias persists, Spearman 0.376) — combined by inverse-error weights learned PIT on IBES 2010-2024, reported as an **interval** (p10/p50/p90 from the sector × vol error distribution) with the probability of touching the target in 52 weeks and this method's historical hit rate on this sector. The Monte Carlo keeps path risk and drawdown, never the central target. **Measured 09-11 on six names** (price · consensus 1-y upside · ours): NVDA 218 · +49.8% · **+114.6%** (median +88.7); ADBE 249 · +12.5% · +25.1% (median **−3.2**); TSM 428 · +28.8% · **+151.3%**; GPRO 1.40 · −64.3% · −45.1%. The first defect is the **horizon**: the page's "expected return" is the 5-year simulation mean (`forecast_days=1260`), right-skewed so the mean sits far above the median, shown beside a 12-month consensus. The second is the clip chain. **No caps: corrections** (Murat: "not caps or limits but corrections on every mistake") — today the consensus upside is clipped to [−30%, tier cap] at `:181` before the blend, the drift is shrunk toward 7%, and simulated prices are capped at +300%; every clip becomes a monthly-refit calibration table (raw upside → realised 12-month return by sector × vol × cap bucket, PIT on IBES) that the ledger's grades update, with an audit script that attributes each name's gap to the consensus to the step that produced it. **The corpse that binds:** `analyst_target_upside_xs` is graded **PERVERSE/CLOSED** — ranking on the raw consensus upside lost **−8 to −18%/yr gross** over 21 years of PIT IBES (ANALYST-IBES-1, 2026-08-11; `recommendation.py:15`), and `signal_registry` bars a PERVERSE signal from leading a ranking. So the raw upside never ranks; the **calibrated** upside enters as a `RISK_INPUT` and display column, and may drive a ranking only after a fresh pre-registered trial (`CALIBRATED-TARGET-UPSIDE-1`) clears the same registry gate. Spec: `research_notes/2026-09-11/spec_price_targets.md` (818 lines: three legs, the audit script, the monthly calibration loop, the output schema, tests). | backtest per era vs the consensus and vs a drift-only control on IBES 2010-2024; the page shows target, interval, weights, consensus, hit rate |
| **O9** | **Two Aegis instances in one checkout must not fight** (found live 09-11: a headless source run's `stop_if_owned` killed the model server the running .exe had started, because the ownership note is per checkout). Ownership carries the owner PID and start time; `stop_if_owned` stops only for its own PID or a dead owner. The desktop backend does **not** start the twelve Railway scheduler jobs or the warm loops unless `AEGIS_DESKTOP_SCHEDULER=1` — a keyed laptop must not mark a second track record or spend DeepSeek in parallel with Railway. | two instances: the second reports `left_alone: owned by pid N` |

### Lane N — whole-market news, no LLM in the pull (blocks L, E, B3)

| id | item | control / receipt |
|---|---|---|
| **N-A** | `scripts/news_pull.py` — a **corpus writer**, resumable, one JSONL per source per day under `backend/data/optimus/news_corpus/<source>/<YYYY-MM-DD>.jsonl`, every row `{source, first_seen_utc, published_utc, tz_source, url, title, body?, lang, tickers[], entity_tags[], raw_id}`; a **cursor file per source**; a receipt per run with rows/new/dupes/failures per source. Sources in order: Alpaca/Benzinga (incremental by `created_at`, and **finish the 83.6% backfill** with the cursor), GDELT DOC 2.0 (queries per region and per theme; NGrams fallback), Google News RSS sweep (zh-CN, zh-TW, ja, ko, en-HK, en-SG, en-IN, en-AU, en-GB, en-US), AKShare (CN A-share news), SEC EDGAR Atom, Nikkei Asia RSS. | the receipt; a source that returns 0 twice is red, not silent |
| **N-B** | **Source registry** `backend/data/news_sources.yaml` in World Monitor's shape: provider, region, language, tier, licence, method, pit_grade (`native_stamp` / `first_seen_only` / `index_state`), rate limit. The coverage card reads it. | a source not in the registry cannot be pulled (refusal at parse) |
| **N-C** | **The E1 join as a nightly appending job** (`E1_news_return_panel` gains `--append`): new corpus rows → first open strictly after `first_seen_utc` → labels minus SPY; `pit_dv_21` from bars, never the entry session's own dollar volume (defect #5, 09-10). | PIT re-verify on every append: 0 violations or the append is refused |
| **N-D** | **Entity resolution** for non-US and non-ticker rows: issuer-name → symbol table for HK/JP/KR/CN names that also list in the US (ADRs) and for the 3,060-symbol Alpaca universe; unresolved rows kept with `tickers=[]` and counted. | resolution rate per source in the receipt |
| **N-E** | **Daily analyst snapshot**: yfinance recommendations/targets + Finnhub recommendation trends, one row per (symbol, date), because Finnhub keeps four months. | a series that starts the day the job starts, and says so |
| **N-F** | **Coverage card** on the board: per region and per source, last row age, rows today, 7-day trend, resolution rate. "Asia first" becomes a number on the board, not a sentence in a doc. | — |
| **N-G** | **TRIAL-HIRING-PIVOT-1** (pre-register before the collector writes a label): public ATS JSON (Greenhouse/Lever/Ashby) for the Alpaca universe's names that expose one; features = share of open roles with AI/ML titles, its 90-day change, total roles change. Named instances: ADBE, ADSK, GPRO. **Control:** same-sector names with no change in AI-role share; **placebo:** the feature shifted +90 days. Primary: 63-session SPY-adjusted return, per era (there is only 2025-26 — say so), MDE printed first. Not a rule, a hypothesis: *what observation separates this from sector beta?* — the control answers. | the prereg file; the collector's receipt |

### Lane L — the LLM as reader and typer (blocks nothing; feeds B5, E1)

| id | item | control |
|---|---|---|
| **L1** | R2 panel B run (18,501 cells, 19 blocks, MDE 14.05%/yr) with the AMNESIA canary re-run on the widened set. | shuffled-digest, as registered |
| **L2** | **Typed-event extraction**: the local model reads each corpus row and emits a typed row `{event_type ∈ fixed vocabulary, direction, magnitude_bucket, confidence, evidence_span}`; the vocabulary is frozen in a prereg; output is **numeric by construction** (this is "the conclusion becomes numerical data automatically"). | inter-rater: a second prompt hash on a 500-row sample, kappa printed; a shuffled-text arm |
| **L3** | **Lookahead Propensity** test (Gao-Jiang-Yan 2026) on Qwen2.5-7B and DeepSeek over 2015-2024 digests: hit rate before vs after each model's cutoff. Any 2015-2024 LLM number quoted after this carries the result. | the cutoff itself is the control |
| **L4** | Qwen3-30B-A3B measured **idle** (prompt-eval tok/s decides), then R2-Qwen3 as a **new arm** beside R2. Plain Instruct first; abliterated only if refusal rate > 0 on R2's own prompts. | R2's own shuffled control under both models |

### Lane B — books as data accumulation (Murat's "thousands of paper accounts")

The unit is not an account. It is a **frozen contract + a cadence + a control
twin + a forecast row**, marked from local bars. Thousands of daily NAV rows a
day is nothing to sqlite; thousands of Alpaca accounts is impossible.

| id | item | control |
|---|---|---|
| **B1** | `PaperBook` = `Strategy` (from `contract.py`, fingerprinted) + `cadence ∈ {30m, daily, weekly, quarterly}` + `created_utc` + `origin ∈ {human_text, night_job, mutation}` + `origin_text` (the sentence Murat typed, verbatim) + `control_twin_id`. Stored in `paper_nav`/`paper_portfolios` (existing schema) with `portfolio_id = fingerprint`. | — |
| **B2** | **Natural language → contract.** The local model proposes a `Strategy` JSON from Murat's sentence; the engine validates (unknown field → refusal; zero cost → refusal by construction; universe must resolve to ≥ 5 names; licence = PRODUCT_EXPERIMENT), prints the worst case in dollars (`n × notional% × stop%`, protocol §4), and shows the contract; Murat clicks **Hold**. The LLM proposed; the engine allocated; a human froze it. No order path, no real capital (invariant: no LLM authority over capital). | — |
| **B3** | **Every book gets a twin at creation**: same construction, same cadence, universe drawn at random from the same liquidity band (the random-genome null of RW1), and a beta-matched twin where the book is long-only. A book's number is never shown without its twin's. | the twin IS the control |
| **B4** | **Cadence scheduler** in the desktop backend: marks from the local Alpaca bars (1.25M rows, 3,060 symbols) and yfinance for what they lack; a 30-minute book marks from minute bars during the session; a quarterly book marks daily but *decides* quarterly. Marks are one row per (book, timestamp); the scheduler writes a receipt per pass. | invariant 15: a pass with nothing to do writes "nothing to do" |
| **B5** | **Forecast rows per book**: at each decision, a `PredictionRecord` (`belief_state.make_prediction`) with `model` = the local model or the engine, `observable = beats_benchmark`, `benchmark = control_twin`, horizon = the book's cadence. `pi_ledger_resolve` runs in the desktop backend, so the local `predictions.jsonl` is graded on the laptop (R4 closes). | Brier vs the twin's forecast (p = 0.5) |
| **B6** | **Regret page** (was 10.7's "Regret"): yesterday's forecasts vs outcomes per book and per model; calibration curve by model; the worst miss with its thesis and counter-thesis side by side. This is "what we thought versus what happened" as a page. | — |

### Lane E — the engine that learns from its own backtests (needs N-C, L2)

| id | item | control |
|---|---|---|
| **E1** | Typed events (L2) → StockMixer-class tabular head on (event features + PIT price features) at 5- and 21-session horizons. | TF-IDF head, shuffled-event head, no-text head, per era (2025-26 only: say so) |
| **E2** | Frozen bge/e5 embedding + rank head at **5-21 sessions** — horizon the only changed variable from N3. | the same three |
| **E3** | **Probabilities, not confidence**: adaptive conformal intervals on whichever head has a positive control-adjusted IC; the board shows the interval and its realised coverage. | naive-coverage baseline; realised coverage per vol regime |
| **E4** | ADWIN-gated rolling refit vs fixed-window refit, both graded. | the fixed window |
| **E5** | **Stopping rules for the night factory**: deflated Sharpe and PBO on G3's evaluations log; a lineage that fails DSR at its trial count is `DEPRIORITIZED`, not deleted. "Infinite backtests that learn" = the night factory + `SearchState` (elites across nights, seeds outside the union) + these rules. | the random-genome null on the same windows (RW1) |
| **E6** | **Evidence memory rotation** (deadline): monthly files split by each row's own stamp, live month untracked, sealed months committed once; a test that the reader returns every row across the split. Compaction refused. | row count before = row count after |

### Lane F — the fleet (attended)

| id | item |
|---|---|
| **F1** | The terminal repo's `docs/HANDOFF.md` stops at 2026-09-03; work since lives in commit messages only. Write the 09-09 fully-invested state into it (books, mandates to 2027-12-31, worst cases from `state/deploy_receipts/2026-09-09_fully_invested_and_six_books.json`). |
| **F2** | Read the six books from the venue once (one GET per book, cached, opt-in — the existing `paper-snapshot` route) and put the numbers on the board with their standard errors. Beta is not estimable under 20 sessions; the card says so. |

---

## 4. GATE ORDER (what blocks what)

```
O1 O2 O3 ─┐
          ├─ O4 ─ O5 ─ O6 ─ O7 ─ L1
N-A N-B ──┤
          ├─ N-C ─ N-D ─ N-F ──── L2 ─ E1
N-E N-G ──┘                        │
B1 ─ B2 ─ B3 ─ B4 ─ B5 ─ B6        E2 E3 E4
E5, E6, L3, L4, F1, F2: independent; E6 has a deadline
```

Two things cannot be parallelised (invariants §9): prospective evidence (every
book's grade arrives one cadence at a time) and statistical power (2025-26 is
21 months; nothing text-based gets a third era until the backfill reaches 2015).

## 5. WHAT MURAT DOES (only what Claude Code cannot)

1. Launch the .exe after O1 lands and say what he sees; close it; relaunch;
   confirm the guide did not return.
2. Confirm the keys in `.env` are the ones he wants the app to use (it will now
   read them).
3. Type the first book sentence into B2 and click Hold — the first
   `origin=human_text` contract is his, by design.
4. Decide, later, on the extra device; nothing here needs it. Qwen3-30B-A3B is
   measured on this laptop first (L4).
5. Nothing else. Deploy flags, lane seeds, and sealing stay attended and stay
   his, but none is on this roadmap's critical path.

## 6. MUST NOT REGRESS (added to the 09-09 / 09-10 lists)

17. **Nothing the operator runs is frozen but the launcher.** A code path that
    resolves a file by `__file__` is tested against the launcher's root.
18. **A book is never shown without its twin**, and a twin is created with the
    book, not after its number is known (a control picked on the outcome is not
    a control).
19. **The LLM proposes a contract; the engine validates and freezes it; a human
    holds it.** No tool the model can call writes to the repo, a book, or a
    broker.
20. **Every corpus row carries `first_seen_utc` written by us**, beside the
    source's own stamp and its timezone. A source graded `index_state` in the
    registry is never used to label a return.
21. **A number from an LLM read over dates before that model's cutoff carries
    its Lookahead Propensity result** or is not quoted.
22. **A forecast the model writes is graded by a job it cannot see**
    (`record_outcome` returns `None`; that stays).

---
---

# AMENDMENT (2026-09-11, later the same day) — the investing agency, the memory, and the reopened LLM-in-the-backtest lane

Murat, an hour after the roots above (VISION §6b): *"not a research paper — an
investing tool that makes investments on my behalf and an engine I can interact
with; my own investing agency; for an average person with under $1M: no data, no
info, no experience, no time; thousands of paper accounts, all different; don't
kill good ideas; use the LLM in the backtests with made-up news; the results
become context for the brain or numbers for the net."* Three more Sonnet agents
answered (notes: `research_notes/2026-09-11/research_agency.md`,
`research_learning_loop.md`, `research_qanat.md`). This amendment adds four
lanes and re-orders execution into chunks.

## 7. THE PROBLEM STATEMENT — what an average investor is actually losing, and what nothing sells them

The research put numbers on Murat's sentence. Barber & Odean (J. Finance 2000):
66,465 households earned 16.4%/yr against 17.9% for the market, and the
highest-turnover quintile earned 11.4% — **activity costs ~6.5 pp/yr**. Barber
& Odean (RFS 2008): individuals are net *buyers* of attention-grabbing stocks
because they can only sell what they own. Kumar (2009): lottery-stock chasers
lose 2-3 pp/yr. Morningstar's 2015-24 gap is −1.2 pp/yr, −2.1 for volatile
funds (contested by Fulkerson et al. 2026 as partly mechanical). Robo-advisors
fixed diversification, rebalancing bands and tax-loss harvesting and **do not
pick stocks, read news, or make hold/sell/buy calls**. Composer automates rules
the user must write; Public Alpha and Robinhood Cortex are research layers;
ai-hedge-fund and TradingAgents have the multi-agent shape and no audited
record. **No surveyed product does both goal intake ("X money for Y time" →
allocation, risk, hold time) and daily autonomous review.** That is the gap,
and it is the deliverable.

Eight classic rules an agency would be tempted to encode (Graham net-nets,
Piotroski, Greenblatt, Antonacci, Faber GTAA, O'Shaughnessy, Dalio all-weather,
Bogle arithmetic) **all decayed, reversed, or drew down hard exactly when tested
out of sample after costs** (Piotroski's literal rule: −9.5 to −11.8%/yr in
recent decades; GTAA's own ETF closed in 2017; all-weather −22% in 2022). So the
library enters as **competing, individually falsifiable paper books**, never as
rules the engine trusts — which is lane B's design already.

Social data: X is pay-per-read since Feb 2026; Reddit's Nov-2025 policy requires
pre-approval and bars ML use without permission; StockTwits labels 30-50% of
posts. Renault (2017): StockTwits sentiment predicts the *last half hour of the
same day*; WSB peak-attention entries averaged −8.5%. **Social signals are a
cheap secondary layer for hypothesis generation, never adjudication.** 13F
copying stays thin (Cohen-Polk-Silli best ideas do not overlap across managers;
the 45-day lag), as our own TRIAL-ARK/CONGRESS/INSIDER lanes are finding.

Regulatory boundary, stated and not advised: SEC IM Guidance 2017-02 governs
tools that advise *others* for compensation; a personal tool one person runs on
their own account sits outside that definition. **Before any multi-user
distribution, this is a question for counsel, and the README says so.**

## 8. Lane A — the agency (goal intake, the daily review, the hold/sell/buy-more call)

| id | item | control / acceptance |
|---|---|---|
| **A1** | **Intake = an IPS.** `POST /api/agency/intake` takes `{capital, horizon_months, personality ∈ four, constraints[], liquidity_need}` and returns an Investment Policy Statement (the CFA five-part shape: facts, objectives and constraints, risk ability vs willingness, eligible universe, review cadence) as a frozen JSON with a hash. The LLM drafts the prose; the engine fills every number. | the IPS hash is on every book the intake creates |
| **A2** | **Options, not one answer.** From one IPS the engine proposes three books (lane B) — preservation / balanced / aggressive expressions of the same IPS — each with its twin, worst case in dollars (`n × notional% × stop%`), expected drawdown at the declared budget, and the hold rule. Murat picks one; the other two are held as **shadow books** so the choice itself is graded. | the un-chosen books are marked and shown beside the chosen one |
| **A3** | **The daily review** is the Morning click (O5) applied per book: for each holding, `{hold, sell, buy_more, trim}` with a probability, the news and events that moved it (typed events from L2, upcoming prints from the calendar), and the forecast row written BEFORE the call is shown (B5). The call is a proposal; in paper it executes; a real-money path does not exist and stays attended. | every call has a forecast row; every forecast row is graded |
| **A4** | **Protect first.** Drawdown budget per book from the IPS; a breach flips the book to its preservation twin's construction, logged, reversible by a human. This is the "protect its money" half, and it is a rule the engine derives from the IPS, not a parameter. | breach → receipt → the board shows it in red |
| **A5** | **Explain in plain words.** Every number the agency shows has a one-sentence explanation the local model writes from the receipt, and the receipt path. The average investor reads the sentence; the sceptic reads the path. | — |

Lane A sits on lanes B (books), O (the board), N (news) and M (memory). It does
not need lane E to ship: an agency that runs the book library with twins and
grades itself is already better than a rule set, because it can say which rule
is currently working.

## 9. Lane M — the memory that learns (the ledger the LLM reads and the net consumes)

The literature's one consistent answer (Reflexion, ExpeL, Voyager, FinCon,
FactorMiner 2026) is that agents improve without weight updates by storing
**graded experience** and retrieving it — and its one consistent failure is
**over-trust of retrieved experience** and **hindsight contamination**. Nobody
scores verbal reflections with a proper scoring rule; we will.

| id | item | control |
|---|---|---|
| **M1** | **One ledger schema** for every forecast the system makes (book, name, scenario, rule): `id, made_utc, decision_date, resolution_date, horizon, mechanism_id, hypothesis_text, policy_hash, inputs_used (PIT provenance), llm_provider, prompt_hash, probability, confidence, benchmark, control_twin_id, control_construction, outcome, vs_benchmark, vs_control, costs_charged (bool, rate), brier, calibration_bucket, LAP_score, anonymization_gap, era_tag, licence, n_effective_trials_at_time, notes_text, embedding_id`. `belief_state.PredictionRecord` is extended, not replaced. | the base-rate forecaster (p = base rate) is a row in the same ledger |
| **M2** | **Distillation, ExpeL-style, from winner vs matched loser.** A night job diffs graded pairs (a book vs its twin; a rule that paid vs the same rule in the era it did not) and writes candidate **rules as text with their own Brier**: a rule is a forecast about future forecasts and is graded like one. Output: `backend/data/optimus/brain/LEARNED_<YYYY-MM>.md` — the markdown Murat asked for, fed to Optimus — and `learned_rules.jsonl` for retrieval. | a rule must generalise to a held-out mechanism family or it is `NOT_GENERALISED`; a shuffled-pair distillation produces the noise floor |
| **M3** | **Retrieval that cannot see hindsight.** When the model is asked for a forecast at date t, it may retrieve only rules whose `resolution_date < t` and whose Brier was computed on data before t. Enforced in the retriever, tested both ways. | the same forecast with retrieval off |
| **M4** | **Calibration on the board:** Brier split into calibration and resolution (Murphy 1973), reliability diagram per model and per mechanism, rolling; Tetlock-style persistence check (does last quarter's calibration predict this quarter's?). | the base-rate row |
| **M6** | **Independent settlement — Headline Arena** (issue #8, Kopei, 2026-09-11; note `research_notes/2026-09-11/research_headlinearena.md`). A daily read-only job maps our sensors (NVDA/SPY sensor, FRED, vol regime, the pre-open local read) to direction + confidence on the overlapping targets (GC, CL, ZN, ES, DXY), **locks the row in our own ledger first** (`belief_state.make_prediction`), then posts (`POST /api/v1/eval/challenges/{id}/predict`, reading each challenge's own `dead_zone_pct` rather than hardcoding a threshold), and reconciles their settlement against our grade the next day. Adds what self-measurement cannot: a record settled by a party that is not us, on shared targets, with a public curve. Caveats to carry: their terms take a perpetual, sublicensable licence to submitted text (treat `reasoning` as public and non-recallable); no legal entity or jurisdiction is named; the plugin is a one-maintainer repo; the financial track's score is `50 ± 50·confidence`, not Brier (Brier/CRPS only on the Civic track); the top agent is near coin-flip. Registration is attended (magic link to Murat's e-mail). The mapping is pre-registered before the first submission. | acceptance: for every resolved challenge our ledger's grade equals their settlement; credit-earning never touches the stated confidence |
| **M5** | **Numeric side:** the ledger's numeric fields are a training table; **GBM is the mandatory control for any net** (Gu-Kelly-Xiu 2020: trees and shallow nets lead; no attention/memory architecture has beaten that bar on cross-sectional returns). A Decision-Transformer-style model conditioned on the four personalities is a permitted experiment against that control, not a default. | GBM on the same table |

## 10. Lane X — the LLM inside the backtest, REOPENED with workarounds and a protocol

The 09-11 morning text over-closed this. What the receipts close, precisely:
FINSABER (KDD 2026) closes the LLM **as the trader** (daily, named large caps,
after commissions); Glasserman-Lin close the **per-headline daily** long-short;
C2 closes **pre-training a representation** on made-up news. "Profit Mirage"
(arXiv:2510.07920) and "The Alpha Illusion" (arXiv:2605.16895) add the numbers:
FinMem's returns fall ~72% and QuantAgent's Sharpe ~51% across the training
cutoff; TradingAgents' Sharpe goes 0.43 → 0.22 and QuantAgent's negative once
frictions are charged. None of that closes the mechanism. The workarounds, each
with its control, and the protocol that makes an LLM-in-history experiment
legitimate:

**The protocol (P1-P6, from "The Alpha Illusion", adopted):** temporal
integrity (anonymised, date-shifted placebo, and where possible a time-locked
model such as ChronoGPT as the same-era control); dynamic universe (P7 vintage);
**direction-flip test** (flip the news sign, the forecast must flip); Expected
Calibration Error reported; full frictions; disaggregated agents. Plus
**Lookahead Propensity** (L3) on every pre-cutoff read, and the **anonymisation
gap measured** (arXiv:2511.15364: anonymisation can destroy more signal than the
bias it prevents — R2's anonymised read is compared to a raw read on the same
dates, not assumed costless).

| id | workaround | what it reuses | control |
|---|---|---|---|
| **X1** | **Horizon and hold rule.** The per-headline read at 5 and 21 sessions with a hold rule, not next-open daily. The same signal that dies at 1.8 turnover/day can pay at monthly turnover (R2 is the existence proof). | E1 panel, N3 code | shuffled text, per era; 25 bps on realised turnover |
| **X2** | **Belief elasticity as a feature.** C1's 1,962 counterfactual rows (sign flip, ×3 escalation, …) are shown to the model beside the real headline on the same day; the **change in its forecast** is a number per name-day — how much the belief depends on the news, not the calendar. The direction-flip test becomes a feature. Feeds the tabular head (E1). | C1 rows, R2 prompt | the elasticity from a date-shifted placebo pair |
| **X3** | **Scenario forecasts.** For each name in a book, the model writes k plausible next-session headlines with probabilities ("these are the things that might happen"); the engine prices each by historical analogue (typed event × era); the forecast row stores the scenario set; the ledger grades which scenario reality picked and the Brier of the set. Murat's "probabilities, not confidence", as a graded object. | belief_state, L2 vocabulary | a base-rate scenario set (the era's unconditional event frequencies) |
| **X4** | **Regime-conditional use.** FINSABER's failure is asymmetric (right in bulls, wrong in bears): route the LLM read through a market sensor (the NVDA/SPY sensor of invariant 4) and grade routed vs unrouted. | RW1 windows | the unrouted read |
| **X5** | **The LLM as an auditable information interface, never the allocator** — the Alpha Illusion authors' own recommendation and our invariant 5. Every X-lane output is a feature or a forecast row; the engine sizes, costs and gates. | contract.py | — |

**Reopening closed hypotheses without p-hacking (lane X's licence to look
again):** McLean-Pontiff (2016) split factor decay into ~26% overfitting and
~58% publication crowding — a `DEPRIORITIZED` idea is re-opened only with a
stated reason of which kind it was; re-tests run on **new data only** under
O'Brien-Fleming alpha spending (already in `iif1_read_gate.py`; transplant it to
a generic `retest_gate`). "Don't kill good ideas" becomes a procedure, not a
mood: any corpse can be re-registered with (a) the receipt it must rebut,
(b) the new data it will use, (c) the spending boundary. Value's 2020-22 revival
is the worked example of why.

## 10b. Lane D — the day-trading book (Murat, 2026-09-12: "if we can make 1% a day…")

> "If we can make 1% return every day in a day-trading part of the project with our live data and
> analysis, relying on future outcomes and dates, that would be a winner. Dedicate a paper account;
> check for signals in the market, monitor them, find the small details, make the engine and NN
> train on it. I will leave the PC open on Monday nights to let it test on the device."

Note: `research_notes/2026-09-12/research_daytrading.md`. Licence `PRODUCT_EXPERIMENT`; paper only;
the declared target is 1%/day and the result is measured, not asserted.

**The arithmetic, stated once.** 1%/day is +1,127%/yr compounded, above Medallion's gross. At the
TAQ-measured effective spread on liquid names (1.08 bp one-way) costs are ~2-9 bp/day and the gross
edge needed is ~1.02-1.09%/day; at the retail 25 bp/side assumption, 2× daily turnover alone costs the
whole 1%, so the needed gross edge is 1.5-3.0%/day. **Which cost regime applies is decided by fill
quality on Alpaca paper (IEX quotes, marketable orders, 10% random partials, no depth check), and that
has not been measured** — it is the first receipt lane D writes. The statistics are cheap: on a
12-name equal-weight book with book σ ≈ 1.2%/day, **~12 sessions** separate a true 1%/day from zero at
t 2.8 (≈71 sessions at the universe's measured 2.93%/day intraday σ). The population evidence is the
prior: fewer than 1% of Taiwanese day traders profitable net of fees (Barber-Lee-Liu-Odean), 97% of
persisting Brazilian futures day traders lose (Chague-De Losso-Giovannetti 2020), US 1998-99 profits
tied to Nasdaq beta (Jordan-Diltz 2003). The lane exists so the measurement can happen; the prior is
in its contract.

**What we already know (do not re-ask):** `FINDING_2026-08-23_OVERNIGHT_INTRADAY.md` — at daily
resolution on CRSP 2013-2024 the overnight/intraday split is measured (t 8.71, n 3,019 days) and
buy-and-hold beats overnight-only at zero cost; the earnings gap is a bigger bet, not a better one
(Sharpe 0.94 vs 0.96). The daily reaction lane is closed in every form (RW2). **What is genuinely
untested and only we can test:** the FIRST HOUR after a native-stamped headline, by typed event
(`first_seen_utc` from Alpaca/Benzinga; L2's vocabulary).

| id | item | control |
|---|---|---|
| **D1** | **The book**: a `Strategy` contract at `cadence=30m` — universe = TAQ-covered liquid names at the dollar-volume floor; signal ∈ {typed event in the first hour, first-half-hour return, overnight gap}; `Construction(k=12-20, ew)`; hold in 30-minute bars with a stop and **forced flat at the close**; `CostModel` from the TAQ effective-spread panel per name PLUS an IEX-vs-SIP slippage add-on measured from paper fills; `Objective.periods_per_year` recalibrated (the default assumes monthly). Wrapped as a `PaperBook` (B1) with **two twins**: random entry at the same clock and size, and an **overnight-only twin** (holds through the open, nothing intraday). Daily loss limit printed as `n × notional% × stop%`. | the two twins; SPY intraday |
| **D2** | **Fill quality receipt**: every paper fill vs the IEX quote and vs the SIP NBBO where available; the realised spread per name per session is the cost model's input from day one. `tif=opg` is never used (13/15 expired unfilled on 09-02). | — |
| **D3** | **The pre-open row**: for each name in the book, a scenario forecast (X3) with the implied move from the options snapshot and the sensor; graded at the close; Brier per model. | the base-rate scenario set |
| **D4** | **The NN**: trains on the ledger's rows (decision-time features → close outcome), purged walk-forward, **GBM the mandatory control**. | GBM |
| **D5** | **The Monday-night device protocol**: paper keys only; the launcher's `--serve` mode; a receipt per 30-minute pass ("nothing to do" included); PID-only process control; every network step refuses by name when offline; the app never holds an order path to a real account (AST test). | — |

**First three experiments, ranked by information per session:** (1) the first-hour continuation after a
native-stamped headline, by typed event — the only untested slice, ~12 sessions to a first read; (2) the
overnight-vs-intraday twin as a **systems check** against a known answer (already closed at daily
resolution); (3) SPY/QQQ intraday momentum with vol targeting (Gao-Han-Li-Zhou 2018, R² 1.6%; the
cleanest execution, ~70 sessions). **Chunk 5b** builds D1-D2 on top of chunk 5's `PaperBook` and
cadence scheduler; D3-D5 follow L2 and M1.

## 11. Joins from Qanat and Fidetolabs Notes (what to take, what we already do better)

Qanat (`fidetolabs/qanat`, MIT, created 2026-09-05, one contributor) is a DAG
backtest engine with an MCP server so an LLM can author, run and compare alphas
itself, under a **stage contract** (raw is source-only, data flows forward only,
one weights stage per alpha, no alpha reads another's weights, every table has a
producer) that makes leakage structurally impossible; it declines to compute a
benchmark. Fidetolabs Notes is a cadence of pre-registered replications of
published papers with negative results published.

| take | as | cost |
|---|---|---|
| a standing **"adjudicate one published anomaly"** cadence, pre-registered, negatives published | lane B books from §7's library + `pre-register-trial`; one per week as a night job | cheap |
| a **read-only MCP surface** over the joined panel, the farm and the leaderboard, so an agent can query without the ability to write (Qanat's `--read-only` as a structural gate) | extend the Optimus MCP with `panel_query`, `farm_query`, `receipt` tools; O6's tool set becomes the same surface | cheap |
| **decay-blended target weights** (`w_t = λ w_{t-1} + (1-λ) target`) as a first-class cost-control parameter swept with `fee_bps` | `portfolio_farm.Policy` gains `decay`; control λ = 0 | cheap |
| a **typed stage contract** over farm → arms → lanes, so one weights artefact drives backtest AND paper (today two stacks) | big; after lane B, because B1's `PaperBook` is that artefact | big |
| an **externally anchored, tamper-evident forecast ledger** (NeuPortal anchors to Bitcoin via OpenTimestamps); our ledger hash chain has been broken since 2026-08-25 and never repaired | first repair the chain in the open (write the break into the record, restart the chain from a signed epoch), then consider anchoring | medium |

What Aegis already does better and keeps: benchmark-relative evaluation with the
benchmark's own drawdown (Qanat has none by design), zero cost refused by
construction, matched controls per era, DSR/PBO, a night search that carries
elites and advances seeds (population-based training by another name).

## 11b. The afternoon's three research notes (repos, social, patents + data), by lane

Notes: `research_notes/2026-09-11/research_repos.md`, `research_social.md`,
`research_patents_data.md`.

**Repos worth integration hours** (all MIT, all active): `alpacahq/alpaca-mcp-server`
(official; paper-account operations in natural language → O, B); `dgunning/edgartools`
(typed EDGAR/XBRL/Form 4/13F with a rate limiter → N, E); `Metaculus/forecasting-tools`
(Brier and calibration utilities → M); the EDT dataset's **11-type corporate-event
taxonomy** as L2's starting vocabulary; `openevolve` (Apache-2.0, 7.3k) as the reference
the night search is compared against (E5); `Agent-Trading-Arena` (EMNLP 2025) for an
honest self-play tournament protocol (B). Method only, no code: the "self-evolving
agent" repos with big star counts carry no clear licence and no OOS discipline.

**Social:** essentially no 2025-26 "I built a trading agent" post publishes audited
live P&L vs SPY with costs; the two loudest X track records dissolve into a few lucky
picks when checked. Threads is unindexed; X needs a paid key. Daily feeds that are
free and legal for **hypothesis generation only**: r/algotrading and r/SecurityAnalysis
by RSS, Composer's public symphony leaderboard, QuantConnect's verified live strategies,
the Quantocracy aggregator, AltIndex's composite alt-data list. One design detail
worth copying from a third-party Serenity follower: **notify-only mode before any
execution**. Practitioner claims that survive skepticism map onto lanes we already
run (PEAD as a regime gate, insider clusters as a composite, job postings) — each
enters as a typed hypothesis with a control (invariant 27).

**Patents as design sources** (not legal advice): six are expired or abandoned and
free to mine — tax-loss harvesting with correlated substitutes (US6687681), per-asset
marginal contribution to **drawdown** as the risk-budget unit (US20150206244; exactly
protocol §4's worst case), multi-period stochastic programming with utility as a
function of wealth (US8768810; the terminal-wealth objective), Goldman's macro-shock →
sector → company cascade "Wavefront" (US7949590; invariant 4's sensor), an
order-difficulty lookup for execution (US8719148), lifecycle leverage glide paths
(US20090018969; the four personalities). Active ones (Google attention US10452978,
Citadel toxicity, Refinitiv sentiment, Franklin Templeton goals-based allocation
US11100587) are ideas to read, not claims to copy; use Apache-2.0 implementations and
inherit their patent grant. JPMorgan's pending US20260111964 (LoRA-tuned LLM with
multi-horizon monotonic ratings) validates a pattern this repo already uses.

**Data acquisition, the five with the most information per dollar for an
event-driven engine that has CRSP/IBES/TAQ to 2024:** (1) **daily options-implied-move
snapshots** — free (Alpaca Basic, CBOE delayed JSON, yfinance chains), and nobody sells
the history, so it compounds from the day the job starts; (2) **SEC XBRL `companyfacts`
with `filed` dates** — true PIT fundamentals, free, 10 req/s, via `edgartools`; (3)
**SEC Form 25/15** as the free delisting source for 2025-26 (P7's survival look-ahead);
(4) congress disclosures (official, free); (5) **AKShare** for CN/HK at zero marginal
cost. Daily schedule in HKT: 06:00 Asia EOD + delistings · 08:00 EDGAR diff + earnings
calendar · 22:00 options snapshot · 05:00 US EOD + 8-K/Form 25 + congress. All under
every free limit. No clean free transcript source exists (ToS); budget a small paid
tier if transcripts matter. `pytrends` is fragile; Wikipedia pageviews' official API is
not. These are chunk 4's data-acquisition tasks (Sonnet).

## 11c. Idea round 2 — four angles outside the mainstream, reconciled with the corpse ledger

Murat, 09-11: *"research again — more patents, education, theories, strategies — a different
approach; an idea-generation session."* Four Sonnet passes (theory outside finance, patents from a
different search, documented after-cost strategies we have not tested, a structured ideation session);
notes in `research_notes/2026-09-11/research_ideas_round2.md` and `ideas_round2/angle{1-4}_*.md`.
Two independent angles converged on the same mechanism, which is why it leads.

| # | idea | lane | corpse it must respect | first test |
|---|---|---|---|---|
| 1 | **TAQ-derived empirical cost model** replacing the flat bps that produced C2's −237%/yr artefact | E | `portfolio_farm.Policy` refuses zero cost; the 4,224-name-day effective-spread panel (08-19) exists | re-grade every night receipt that says "net" under the measured curve; the ranking of nothing may change and the LEVEL of everything will |
| 2 | **Disposition-overhang as an event conditioner** (Frazzini 2006: momentum and post-event drift live where holders sit on unrealised gains/losses; the capital-gains overhang is computable from CRSP volume × price history) — converged on by the theory angle and the ideation angle independently | N, B | the reaction lane is closed in every form (RW2) and PEAD is closed; this is a **conditional** question those verdicts never asked — scope-aware, per canon | the closed reaction book split by overhang tercile, with its own control per tercile |
| 3 | **Low short interest × high turnover, long-only** (Boehmer-Huszár-Jordan 2010, ~+1%/mo, 6-month hold, FINRA data free) | B | NEGATIVE_RESULTS §24's flow-signal sweep already carries a short-interest *change* row (`si_chg_low`, small cap, t 6.09 raw → DSR 0.457) — a level-vs-flow pair; the level was not the survivor | a PRODUCT_EXPERIMENT book with its random-universe twin at the `TRADABLE_DOLLAR_VOL` floor |
| 4 | **Insider cluster buys split by cluster length** (Kang-Kim-Wang: 4-5-day clusters +5% BHAR, same-day clusters −0.7%) on our 11.5M Form-4 rows | N, B | §46 (N1): the insider return does NOT accrue before disclosure on five filing days, so the copy is not pre-empted; the 13D/13G family is NO CONCLUSION | cluster-length buckets, graded from the FILING date, own twin |
| 5 | **Option-implied borrow fee** from OptionMetrics (put-call parity residual) as a free lending-cost panel to 2024 | M, data | S49's borrow-cost lesson: a short's edge is compared to its stop AND its borrow | build the panel; use it in every short-side control before any short book |
| 6 | **Mutual information between typed event and forward return** as the screening statistic instead of IC | X, L2 | must re-derive the known corpses (reaction, revision) as low-MI or it is not a better screen | run on the E1 panel once L2 types exist |
| 7 | **The abstention book** — cash/index by default, deviate only on a strong typed event; control = the always-invested twin | B, A | NEGATIVE_RESULTS §1: the timing strategy lost to buy-and-hold (+28.3% vs +114.8%); abstention is timing with a stricter trigger and must beat that receipt, not ignore it | the twin IS the buy-and-hold control |
| 8 | **Drawdown-constrained sizing** (surplus above a floor, CPPI-shaped; no patent ever covered CPPI) | E, A4 | S38g: the NN sizer lost to trailing vol and both lost to flat 1×; must beat trailing vol at equal drawdown | on the growth-book dev window |
| 9 | **Delta-spliced lookback straddle in shares** (Aspect Capital, abandoned application) — a share-only convexity book with no expiry, answering hack1's empty-chain refusal and hack6's stop-before-hold problem | B | hack1's `no chain at 2027-12-31` receipt; hack6's 56.3% stopped before session 10 | replay on the six books' windows against the stop-based construction |
| 10 | **The Brier ledger gates the LLM lane's authority** — a lane whose rolling calibration decays loses its sizing until it recovers | X, L, M | a gate that cannot go green or red is broken: it must print CANNOT DETERMINE below n | lane M4's calibration feed |

**Banked as negatives, cheaply and immediately:** LPPLS point forecasts are refuted by the
non-Sornette literature (Brée-Challet-Peirano 2013: the critical time is a sloppy parameter;
Grobys 2025: 84.8% false rejections) — consistent with our own §3, so `lppls` stays descriptive and
its docstring now cites the critique; the loser-decile short is predicted dead before a line is
written (Muravyev-Pearson-Pollet 2025: 162 anomalies go from +0.14%/mo to −0.01%/mo after borrow
fees) — pre-register it only to close it with evidence; S&P inclusion (7.4% → 0.8%), pre-FOMC drift
(three replications to ~0), IV skew (Sharpe 1.18 → 0.16, part timestamp look-ahead), BAB (net alpha
≈ 0) and spin-offs are confirmed dead in the literature and get no book.

**Where these enter the chunks:** #1 in chunk 4 (data), #2/#3/#4/#7 as the first `origin=night_job`
books in chunk 5 (each with its twin), #5 in chunk 4, #6/#10 in chunk 7, #8/#9 in chunk 9.

## 12. EXECUTION IN CHUNKS — Sonnet researches, Opus builds, Fable validates

Roles, from Murat: *"Sonnet for research and data acquisition, Opus 5 for
building, you as the central unit check their work and validate; divide the work
into chunks and one by one move on."* Each chunk ends with: Opus commits
locally, Fable reviews the diff, runs the fast suite, pushes, watches CI.

| chunk | contents | gate to the next |
|---|---|---|
| **1** (running 2026-09-11) | O2 config root + frozen-path family test · O3 storage · O7 ask starts the model | suite green, CI green, Murat relaunches and the guide stays dismissed |
| **2** | O1 thin launcher · E6 evidence-memory rotation (deadline) · F1 terminal handoff | the .exe on a stale checkout pulls and serves the new HEAD |
| **3** | O4 board · O10 stock shell + computing state + full-universe screener · O8 universe page · E6 sealed-month guard (running 2026-09-11 afternoon; O5 Morning and O6 Ask-with-tools move to chunk 3b) | every board card shows a receipt path or an em dash; search any symbol; screener over the universe |
| **3b** | O5 Morning · O6 Ask-with-tools · **O11 the 52-week target** (spec from Sonnet, build on Opus, backtest on IBES before the page shows it) | the Morning receipt; the target's per-era backtest beside the consensus |
| **4** | N-A corpus writer + N-B registry + N-C nightly join (Sonnet: source-by-source pulls and the N-D name table; Opus: the writer and the tests) | coverage card shows Asia rows with `first_seen_utc` |
| **5** | B1-B5 books with twins + M1 ledger schema + M3 hindsight-safe retrieval + M6 Headline Arena daily job (attended registration by Murat) | the first `origin=human_text` book has a twin and a graded forecast; the first arena settlement equals our grade |
| **5b** | **Lane D** D1-D2: the 30-minute paper book with two twins and the fill-quality receipt; a dedicated Alpaca paper account role for it (attended: Murat creates it); the Monday-night protocol | the first session's receipt: fills vs quotes, net vs both twins |
| **6** | A1-A5 the agency intake, options, daily review, protect-first | Murat states a goal and receives three graded options |
| **7** | X1-X4 LLM-in-backtest workarounds under P1-P6 + L3 Lookahead Propensity + the anonymisation gap | each receipt carries LAP and the flip test |
| **8** | M2 distillation → `LEARNED_<month>.md` for Optimus · M4 calibration on the board · E5 DSR/PBO stopping rules · §11 cheap joins | the first rule with its own Brier |
| **9** | E1-E4 heads against GBM · L4 Qwen3 as a new arm · the stage contract (big) | a head beats GBM and its three controls, or the result is filed |

**Compaction rule for the validating session:** summarise when context passes
half; the chunk table above is the resume point.

## 13. MUST NOT REGRESS (added by the amendment)

23. **`FAILED_VARIANT` closes a route; the mechanism is re-opened by procedure**
    (§10): name the receipt to rebut, the new data, the spending boundary.
24. **An LLM read over history carries P1-P6, its LAP score and its
    anonymisation gap**, or it is not quoted.
25. **A rule the memory learns is a forecast and carries a Brier.** Retrieval
    at date t sees only rules resolved before t.
26. **The agency shows options with twins and worst cases; a human picks; the
    un-chosen options are graded as shadows.**
27. **Social data generates hypotheses; it never adjudicates.**
28. **Every result is compared to an outside reference and tested against the past** (Murat,
    09-11: *"when we have any results compare it to firms and other results; test it from the
    past to see how it differed from reality"*). A number the engine produces for today
    (a target, a forecast, a book's expected return) is shown beside the external comparator
    it has (the consensus target, the arena's settlement, the benchmark lane, the published
    paper's figure) AND beside the same method's historical error against realised outcomes,
    per era. A method with no backtest of its own past errors prints CANNOT DETERMINE for
    its hit rate; it does not print a bare point. The price-target audit (O11), the Brier
    ledger (M4) and Headline Arena (M6) are the three instruments of this rule.
