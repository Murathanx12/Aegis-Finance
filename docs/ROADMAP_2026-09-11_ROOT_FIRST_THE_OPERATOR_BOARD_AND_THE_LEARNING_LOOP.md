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
