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
| **RESULT IMPROVEMENT** | **FIRST POSITIVE READ AT THE TRADABLE FLOOR (2026-09-13 16:30):** a registered book (F) beats its twin at $10M in the current era. Nothing has traded on it yet; no forward evidence; the scoreboard line stays CONDITIONAL until the allocator runs it in paper beside its twin. Before this line: NONE for five months. |
| best historical net strategy vs market | **F, calendar seasonality (Heston-Sadka years 11-20), +0.43%/mo net vs its random-universe twin at the $10M floor, t 3.12 over 419 blocks, +0.76%/mo t 2.30 in 2017-2024, shift-placebo +0.08% t 0.59** (`B_books_efg_replay_run01`, 2026-09-13; UNSIGNED, one read, flat 25 bps, CONDITIONAL). G forecast dispersion is +0.72%/mo t 4.42 pooled at $10M but **+0.02% t 0.07 in 2017-2024** — a decayed 1990s effect, not a live engine |
| best forward paper strategy | none — **the six Alpaca books $551,653 of $600,000 (−8.1%) read live 2026-09-13 vs SPY −0.66% over 08-28→09-11**; hack1/3/4 lost 5-7% in three sessions against a flat SPY; hack2 retired to lane D |
| only live lane | **R2 REJECTED on its held-out panel (2026-09-13 18:50, `R2_widened_panelB_run02`, 4.1 h on the local 7B, TdrDelay 60): PANEL-B 19 blocks, masked read −3.51%/yr net vs shuffled-digest control −3.25%/yr → −0.26%/yr, t −0.10; gross −0.42%/yr; AMNESIA gap 0.0027.** Panel A's +16.19%/yr (t 3.92, 112 blocks) was the selection panel; the registered clause on panel B rejects. The lane keeps marking as a SHADOW; it is not a candidate. |
| independent selectors with evidence | **one** — still the reason no router is permitted |
| what this session found | **the packaged app runs without a single API key** (§1 R1), and the tour repeats because the window wipes its own storage on every launch |
| LLM spend | $0.00 this session (no model calls; five Sonnet agents) |
| tests / CI | not re-run; CI **green on `87febf1`**; tree clean at start |
| deadline | `learner/evidence_memory.jsonl` **65.16 MB** (62.14 two days ago; GitHub rejects at 100) |

---

## 0b. THE HANDOFF, 2026-09-13 14:00 HKT — Fable runs the business

Murat, verbatim: *"think like a boss and you own this business. aegis has spent 1000usd at this moment on
infrastructure. if we don't make a profitable business we will have to shut down. so do anything you can to
find profit making strategies, combination of strategies etc. test them. run backtest for NN, do a learning
lab for it to continuously learn. for night sims update it such that it is live whenever pc is on ... I am
handing it off to you. you have full freedom."*

**The bar.** $1,000 of infrastructure is sunk; the venue caps us at six paper accounts; the fleet is −8.1%
on an artery that has no historical edge. A business here is a set of books that beat their twins net of
costs at a tradable floor, run unattended, graded every day, with capital moved by a rule that cuts losers
fast and promotes winners slowly. Nothing else counts as progress. Every session opens with the scoreboard
above, and **RESULT IMPROVEMENT: NONE** stays written until a book beats its twin at |t| ≥ 2 on a
registered construction at $10M.

**The order of work from here (one Opus chunk at a time, Sonnet researches ahead, Fable validates):**

| step | what | why first |
|---|---|---|
| **now** | the model night on the GPU (TdrDelay 60 active): R2 panel B, then the 6,020-row typed-event backlog | the only live lane's held-out read, and the NN's missing input |
| **13a** (building) | Books E (quality-minus-junk), F (seasonality), G (forecast dispersion) from the JKP panel already on disk, replayed at $3M AND $10M with twins; Book C v1 with the announcement-window sign | the fleet needs engines with a receipt at a tradable floor before Monday |
| **13b** | the allocator in the execution repo (`spec_allocator_kill_promote.md`): drawdown cuts (halve at −5%, floor at −7.5%), Thompson over survivors from each book's historical prior, equal-weight and random twins, the six-engine map from 13a's $10M receipts, worst case printed before every sizing change; then the fleet deploy | capital stops leaking on the losing artery; "kill losers, give winners dominance" in the form that survives small samples |
| **14** | the always-on lab (`spec_always_on_lab.md`): live news, LLM typing as rows arrive (cloud provider when `research_cloud_llm_readers.md` lands), decision-vs-reality grading of every forecast, the catalyst calendar, the nightly NN refit with four controls and DSR/PBO, the idle-GPU night queue, Murat's themes as typed hypothesis streams | data accumulation compounds with calendar time; every hour the PC is on and idle is an hour not learning |
| **15** | round-3 books from `research_strategy_ideas_round3.md` (de-duplicated against `research_registry.md`), the internal book population scaled to thousands with twins, the LinkedIn/hiring, pivot-to-AI, motivation and holders streams graded by the lab | breadth of DIFFERENT errors, not more momentum |

**Rules that follow from the bar.** A research question is not opened without a line in
`research_registry.md`; a book is not deployed to a venue account without a $10M receipt with its twin;
the allocator cuts on drawdown with no discussion and promotes only on twin-excess with n_effective
printed; cloud LLM spend carries a hard daily cap in dollars in the receipt; the fleet deploy command is
handed to Murat with every book's worst case beside it, and he runs it.

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
| **L2** | **Typed-event extraction**: the local model reads each corpus row and emits a typed row `{event_type ∈ fixed vocabulary, direction, magnitude_bucket, confidence, evidence_span}`; the vocabulary is frozen in a prereg; output is **numeric by construction** (this is "the conclusion becomes numerical data automatically"). **Built 2026-09-13 (chunk 10)**: 40-row vocabulary as a hashed table, the contract, the resumable night job frozen at 6,020 rows `PENDING_MODEL`; prereg UNSIGNED as a SCREEN (55 independent observations on 13 months; the 2015 backfill lifts it). **Known gap:** C1's largest counterfactual kind, `ANALYST` (1,218 rows), has no vocabulary id — the table needs an analyst-action type before X2 can use those rows. | inter-rater κ ≥ 0.61 on `event_type` (a second prompt hash on a 50-row sample); a shuffled-text arm |
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
**Measured 2026-09-13 (E1, run 1, h=5, keyword-proxy events, no model calls, 938 s):** neither head's
typed-event arm beats the SHUFFLED-event control — LightGBM EVENT−SHUFFLE IC +0.0009 (t 0.17),
StockMixer EVENT−SHUFFLE IC +0.0029 (t 0.46), Holm p 1.0 over 276 date blocks (≈55 independent, the
5-session labels overlap). **FAILED_VARIANT for the keyword proxy, not for typed events**: L2 has typed
none of these cells, so this is a verdict on a keyword lookup over the 39-id vocabulary. StockMixer
beats GBM on the identical table (IC +0.0111, t 2.01 over 276 blocks; ≈0.9 once the overlap divides
it) — an architecture difference, and not evidence of text because SHUFFLE keeps the gap. Every net
line is negative at 1.3-1.9 turnover/day × 25 bps; levels are not the verdict. Receipt
`night_factory_2026-09-13/E1_event_head_run01.json`. Next test is the receipt's own: L2's LLM typing
over the same cells, graded through the identical table and controls.

**Measured 2026-09-13 17:40 (E1 run 2, h=5, the FIRST run on LLM-typed rows, `event_source: typed_l2`, 1,323 s):** 6,007 DeepSeek-typed rows → 1,587 joined the panel (3,612 symbols not in the panel, 808 after its end) → **630 of 129,983 cells carry an event (0.5%)**. GBM EVENT−SHUFFLE IC +0.0043 (t 2.22 raw, Holm 0.16), StockMixer +0.0060 (t 1.58, Holm 0.51) → FAILED_VARIANT at this coverage, and the test had almost no power. **What this says:** the NN's input is not the corpus (two days old plus a 2015 backfill outside the panel) but the panel's own 163,284 unique headline texts, none typed. Typing them on DeepSeek is ~$55 at today's rate (a 20,000-row stratified subset ~$7 first); that is the "backtest for the NN" Murat asked for, and it is a night job, not a design change. The receipt's verdict sentence still says "keyword proxy" — a wording defect fixed the same evening.

**Measured 2026-09-13 20:25 (E1 run 4, h=5, corpus + a 20,000-text stratified subset of the panel's own headlines, join fixed):** **30,275 of 129,983 cells carry an event (23.3%)**, 41,148 event rows. GBM EVENT−SHUFFLE IC +0.0046 (t 1.13, Holm 0.96); StockMixer EVENT−SHUFFLE +0.0000 (t 0.0); StockMixer−GBM on the identical table +0.0112 (t 1.88, p 0.06) → **FAILED_VARIANT: at a quarter of the cells, LLM-typed events add no IC over their own shuffle at 5 sessions in 2025-26.** Every net line is negative at 25 bps on daily turnover (levels, not the verdict). Run 3 had silently dropped all 41,289 panel cells at the join (a set of integers against datetime64 keys; the receipt printed the drop count, which is how it was caught). The full-panel typing (100% coverage, ~$10 real) is the last read this design gets before it is filed; the 21-session horizon and the typed-event COUNTS over windows (not one-hots) are the two constructions not yet tried.

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
| **M6** | ~~Independent settlement — Headline Arena~~ **REMOVED 2026-09-13 (Murat: "just a vibe-code project")**: the daily job, its registry entry and its credential names are deleted in chunk 12; independent settlement stays wanted, from a venue with an entity behind it. | — |
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

**Measured 2026-09-12 (chunk 7, no model calls):** L3's before/after-cutoff design **cannot run on
panel B** — every cell is after Qwen2.5-7B's ~2024-06 cutoff, so the panel B number is INCONCLUSIVE
on lookahead, never CLEAN; panel A (2015-2024) straddles the cutoff and is the cheap within-panel test.
X4: routing R2's read by the regime sensor makes it **worse** in-sample (−13.2%/yr net on the 10 risk-on
blocks vs −3.9%/yr unrouted) — FINSABER's asymmetry does not rescue this lane. The anonymisation gap,
the recall probe and the elasticity run are frozen at hashed cell lists, `PENDING_MODEL`.

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
| 3 | **Low short interest × high turnover, long-only** (Boehmer-Huszár-Jordan 2010, ~+1%/mo, 6-month hold). **The panel exists locally** (probe 09-12): WRDS `comp__sec_shortint` + `_legacy`, 1973-2026, 10.0M rows, joined to CRSP through `link_ccm`; FINRA's free CDN (2017-12 → today) is the forward leg. `datadate` is the settlement date — usable only from publication (measured lag 10-26 days). | B | NEGATIVE_RESULTS §24's flow-signal sweep already carries a short-interest *change* row (`si_chg_low`, small cap, t 6.09 raw → DSR 0.457) — a level-vs-flow pair; the level was not the survivor | a PRODUCT_EXPERIMENT book with its random-universe twin at the `TRADABLE_DOLLAR_VOL` floor |
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

**First historical read, 2026-09-13 (`night_factory_2026-09-13/B_first_books_replay_run01.json`;
1990-2024, 420 months, 18,684 permnos, twins turnover-matched, flat 25 bps pending 5c's curve — no
LEVEL quotable, differences only):** **A** (low SI × high turnover) −0.54%/mo net vs its random twin,
t −2.26, negative in all four eras — loses to a random book at the same turnover; **B** (insider
clusters 4-5 days) −0.14%/mo, t −0.08, and the same-day falsifier arm −0.16%/mo — length conditioning
not supported (the draft's own rule: a point estimate ≤ 0 is not rescued by under-power); **C** (the
disposition-overhang conditioner) **+0.40%/mo net vs the UNCONDITIONED reaction book, t 2.13, p 0.033,
positive in all four eras** (t 0.29 / 1.64 / 1.53 / 1.07) — not Holm-significant at the declared
family size (α 0.0167), so **CONDITIONAL**, not PRODUCT_PROMISING; its two registered falsifiers decide
(the sign-flip placebo Frazzini reports at ~0, and momentum orthogonalisation: `mom_12_1` must die with
overhang on the right-hand side); **D** refused by registration (forward-only; the 24th monthly block is
its earliest read). No verdict clears Holm: **RESULT IMPROVEMENT: NONE**; C is the first candidate in
this repo with the right shape (a difference against its own control, same sign in every era).

**Two corrections to C's read, found 2026-09-13 before the falsifiers ran** (Sonnet literature note
`research_notes/2026-09-13/research_overhang_literature_vs_book_c.md`, code verified by Fable):
(i) the replay computes the overhang once a name has **24 months** of history while the registration
declares a 60-month warm-up and a **1995 start** — so the pooled 395 blocks and the whole 1990s bucket
carry a truncated reference price, and the weakest era is exactly the truncated one. The falsifier
job re-reports the primary metric under the registered construction (60 months, 1995-2024) beside the
falsifiers; until then the pooled t 2.13 is a number from a construction the draft did not register.
(ii) Riley-Summers-Duxbury (2020, *Management Science*, US equities to 2016) find 12-1 momentum
**survives** overhang in the Fama-MacBeth (t 2.93), the opposite of Grinblatt-Han's 1967-1996 table —
so falsifier (b) firing is the modal expectation, not a surprise. For scale: Frazzini's net
overhang-conditioned PEAD spread is 0.9-1.1%/mo (1980-2002, doubly conditioned, quintiles, TAQ costs);
our +0.40%/mo is a tercile cut with a monthly revision-count news sign and 25 bps flat — below the
literature and inside a 50% post-publication decay, which argues "not suspicious", not "confirmed".

**Second read, 2026-09-13 morning (chunk 11: `A_corner_run01`, `B_verdict_run01`, `C_falsifiers_run03`
under `night_factory_2026-09-13/`; CPU only, 103 s + 0 s + 60 s):**
- **A → FAILED_VARIANT** on its own registered floor: −0.94%/mo vs the random twin on the 2011-2024
  confirm slice (t −2.09, 168 blocks) at $3M; the $10M cell −0.25%/mo (t −0.64), twin re-drawn at each
  floor, no contamination year excluded. The corner did not kill it; it was already below zero.
- **B → FAILED_VARIANT, both arms**, by the draft's own clause (2017-2024 net block-mean −2.41% and
  −0.33%, both ≤ 0). The 7.17% MDE protects a null, not a negative. The tradability clause is CANNOT
  DETERMINE by name (run 1 carries no per-year count); the 2000-2009 +6.1% is one era, not a rescue.
- **C → CONDITIONAL, weaker than run 1.** Under the registered construction (60-month warm-up, read
  from 1995): **+0.24%/mo, t 1.38, 359 blocks** (run 1's +0.40%/t 2.13 was the truncated window from
  1990; both numbers kept, neither replaces the other). Eras 1995-99 +0.02% (t 0.05), 2000s +0.39%
  (1.01), 2010-16 +0.30% (1.17), 2017-24 +0.16% (0.54). The sign-flip placebo does not pay (−0.03%/mo,
  t −0.13); Frazzini's own long-short shape −0.13%/mo (t −0.51). **The momentum falsifier is
  untestable, not passed:** raw 12-1 momentum carries t 0.15 on the book's own rows (a scratch check
  prices momentum at rank-IC 0.011, t 1.4, and one-month reversal at IC −0.016, t −2.5 on the same
  rows — right signs, weak, as expected for seasoned liquid names with five years of history), so there
  was nothing for overhang to subsume; the "momentum in costume" clause does not fire because momentum
  earns nothing here. January diagnostic (unregistered): −0.18%/mo in January vs +0.28% Feb-Dec — the
  Grinblatt-Han sign flip in direction, not in significance. TRIAL-DRAFT-C gained **Amendment 1**
  before this read (a primary ≤ 0 closes the book, the clause A always carried).
- **C at the $10M floor (chunk 12 T2, `C_floor10m_run02`, 168 s):** **+0.07%/mo, t 0.45** against
  +0.24%/mo t 1.38 at $3M, both 359 blocks, twins re-drawn per floor; placebo pays at neither;
  momentum not alive at either; the four-era sign becomes 2 of 4. §5's floor clause cannot fire on
  a primary that never cleared, so C stands CONDITIONAL — **with its tradable cell at zero.** It is
  therefore NOT a live-account engine (the allocator spec's hack3 → Book C mapping is withdrawn);
  hack3's replacement is chosen from the three new books' receipts at $10M, once they exist.
- **Vocabulary v2** adds the analyst-action family (43 ids; v1's hash byte-identical); C1's kinds now
  map 2,577 of 6,676 rows (38.6%, was 20.4%).
- **RESULT IMPROVEMENT: NONE.** Of seven pre-registered books, four have a historical read: three closed
  as FAILED_VARIANT on their own rules, one CONDITIONAL below its MDE. Nothing outruns its twin at t ≥ 2
  on a registered construction. The lesson that generalises: the first replay warmed a signal on a
  shorter window than its registration and nobody noticed until the literature note asked why the
  1990s were weakest — **the registered construction is a test input, and the receipt must print it.**

**The six Alpaca paper accounts, read live 2026-09-13 12:10 HKT (`scripts.fleet --check` per role through
each Railway service's own variables; start $100,000 each):**

| role | mandate | equity | positions | orders (any status) |
|---|---|---|---|---|
| hack1 | theme basket | $93,863 | 3 | 30 |
| hack2 | post-event drift | $98,821 | 0 | 8 |
| hack3 | tracker balanced | $83,342 | 10 | 98 |
| hack4 | tracker profit-max | $92,941 | 4 | 62 |
| hack5 | convexity (options) | $95,095 | 1 | 12 |
| hack6 | tracker diversified | $87,591 | 15 | 130 |

Fleet $551,653 of $600,000 (−8.1%); every book below its start; the three tracker books carry the
losses. **Decision (Murat, 12:05 HKT): Alpaca allows six paper accounts, so lane D takes one of these
instead of a seventh — hack2**, the one with no position and the least-touched equity. Alpaca creds
for lane D use the names `ALPACA_LANE_D_API_KEY_ID` / `ALPACA_LANE_D_API_SECRET_KEY` (chunk 12 T6);
the `aat-loop-hack2` Railway service is retired when the keys move. **"Thousands of paper accounts"
(VISION §6b) is NOT built**: what exists is seven registered books, fifteen twins and lane D's book
as internal ledgers at cadence, plus these six venue accounts. Scaling the internal population to
thousands (every mechanism × personality × cadence × universe, each with a twin and a frozen
contract) is chunk 13's job, and the accumulation it buys is calendar time, not compute.

**Third read, 2026-09-13 16:30 (chunk 13a: `B_books_efg_replay_run01`, `C_v1_run01`; family
`NIGHT_JOB_BOOKS_2026_09_13` declared at 4 before any read; 1990-2024; twins re-drawn per floor; 25 bps flat;
differences vs twin only):**

| book | $3M | $10M | $10M by era 1990s / 2000s / 2010-16 / 2017-24 | falsifiers | verdict |
|---|---|---|---|---|---|
| **F seasonality** (yrs 11-20, JKP `seas_11_15an`/`seas_16_20an`) | +0.47% t 3.05 | **+0.43% t 3.12** | +0.46 / +0.32 / +0.17 / **+0.76 (t 2.30)** | shift placebo +0.08% t 0.59 ✓; ex-Jan +0.38% t 2.44 ✓ | CONDITIONAL — **the first engine with a current-era receipt at the floor** |
| **G dispersion** (IBES `stdev/|meanest|`, low tercile) | +0.89% t 4.82 | +0.72% t 4.42 | +0.96 / +1.09 / +0.65 / **+0.02 (t 0.07)** | high-disp leg loses ✓; survives SI at t 2.0065 (a hair) | PRODUCT_PROMISING by its own rule, **but decayed to zero where we trade**; and +0.89% exceeds the published 0.79% long-short, an earnings-level tilt from the `|meanest|` denominator — next amendment: scale by price |
| **C v1** (overhang × announcement-window sign, Amendment 2) | +0.55% t 3.43 | +0.33% t 1.93 | +0.24 / +0.53 / +0.03 / +0.38 (t 1.42) | placebo −0.18% ✓; momentum not alive → untestable | CONDITIONAL — v1 more than doubles v0, as the amendment predicted |
| **E quality-minus-junk** (`qmj`) | +0.41% t 2.56 | +0.11% t 0.70 | +0.36 / +0.25 / −0.10 / −0.19 | junk leg loses ✓; survives size+beta ✓ | CONDITIONAL — dead at the floor |

Holm against the declared four: all reject (G 1e-6, C_v1 6e-4, F 2.3e-3, E 1.0e-2). **What this changes:** hack3's
engine is F, not C (chunk 13b); G goes to the price-scaled amendment before any account; C_v1 waits for a
falsifier that can run; E is filed. What it does not change: every number is one read of one construction on
one cost ruler, unsigned. **The scoreboard's RESULT line moves for the first time in five months, to CONDITIONAL.**

**R2 panel B, 2026-09-13 18:50 — the only live lane's held-out read: REJECT.** The registered clause (masked read vs shuffled digest, net, 19 monthly blocks 2025-01..2026-07) fires: −0.26%/yr net, t −0.10; gross −0.42%/yr. The panel-A number (+16.19%/yr, t 3.92) was the number the lane was selected on, and it does not travel. AMNESIA gap 0.0027 (the anonymised digest does not leak the name). RESULT: the scoreboard's "only live lane" row is struck; R2 stays a shadow. This is the fourth registered read today and the fourth honest closure or conditional; the programme's standing candidate at the tradable floor remains F.

**Overnight 2026-09-14 (chunks 15a/15b; receipts `G_price_scaled_run01`, `E1_event_head_run05`, `L2_panel_run01`):** the typed-event design is closed on its own terms — at 23% coverage, at 5 sessions and at 1 session, with one-hots or a scalar direction×confidence, no arm beats a capacity-matched shuffle (family of 14, max p 1.0) — so the panel's remaining headlines are not typed and the $10 stays. **Book G under Amendment 1 (`stdev/price`) is +1.19%/mo t 6.07 at $10M with the current era at +0.83% t 1.78**, and the payoff is the AVOIDED high-dispersion leg (−2.47%/mo t −7.8): what it says is "do not hold the names analysts disagree most about", a filter, not a pick. It is UNSIGNED; adopting the amendment (input only) is the morning's call, and its first use is as a screen on every other book's universe, not as hack6's engine. The hiring stream now has a collector (8.1% board coverage of the band).

**X2 belief elasticity, 2026-09-14 04:02 (the lab's idle queue, local 7B, 78 min; `night_factory_2026-09-14/X2_elasticity_run01.json`): PRODUCT_PROMISING.** 10,063 counterfactual pairs: the model's forecast moves by 0.463 under a sign-flipped headline vs 0.350 under a date-shifted placebo pair — the true pair exceeds its own placebo by 0.227 on 5,437 uids, paired t 31.9; the direction-flip test passes on 81%. The belief depends on the news, not the calendar. This is a FEATURE result, not a book: the next test is elasticity as an arm in the tabular head beside the closed typed-event arms (E1 is closed on its own terms; a new feature is a new arm). The anonymisation gap (`X_anon_gap`) ran while the model server was stopped for a suite and is PENDING_MODEL — it is re-queued.

**The rest of the model-dependent queue, 2026-09-14 05:00-06:00 (local 7B, `night_factory_2026-09-14/`):** `X_anon_gap` run 3 — naming the company does not help: raw −18.9%/yr net vs masked −16.9%/yr on 300 cells / 19 blocks, gap −2.0 pp t −0.54, AMNESIA canary 0.0027 → the masked default stands, ADOPTED_ARM=MASKED. `X4_regime_route` — routing to risk-on keeps 10 of 19 blocks at −4.04%/yr vs −3.51%/yr unrouted → EXPLORATORY_IN_SAMPLE, worse, not admitted. `E1_event_head` at 5 sessions with the scalar arm — FAILED_VARIANT again (30,690 cells, 23.6%). With chunk 15c's two closures (H option-grant timing, I buyback-vs-insider, both FAILED_VARIANT, neither in the current era at $10M), the night read nine registered questions and closed seven; the two standing positives are **F seasonality (deployed to hack3) and G price-scaled (UNSIGNED, a filter)**, plus X2 elasticity as a feature. RESULT IMPROVEMENT: NONE beyond yesterday's F; the map of what does NOT work is much larger.

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
| **5c** | **Lane E #1 — the TAQ empirical cost model** (spec `research_notes/2026-09-12/spec_cost_model.md`): `CostModel.curve ∈ {flat, taq_empirical, retail_paper}`; half effective spread from the 4,224-row panel (`taq_effective_spreads_v1.jsonl`, unconsumed until now) + the vendored `sqrt_impact` term calibrated to Frazzini-Israel-Moskowitz; a log-dollar-volume/price/vol regression for unmeasured names; per-fill application in the farm; every receipt prints the curve id and realised bps; a migration re-grades every "net" receipt under the curve and files the deltas (levels move, rankings stated). The institutional half needs nothing from 5b; the retail half waits for D2's fill receipt. Caveat carried: NEGATIVE_RESULTS §25 already has two cost rulers disagreeing 3.4-9.1×; this is a fourth ruler, not a verdict on the others. | the six known-answer tests; an old receipt re-graded under `flat` reproduces to the cent |
| **6** | A1-A5 the agency intake, options, daily review, protect-first (spec `research_notes/2026-09-12/spec_agency_intake.md`) | Murat states a goal and receives three graded options |
| **7** | X1-X4 LLM-in-backtest workarounds under P1-P6 + L3 Lookahead Propensity + the anonymisation gap | each receipt carries LAP and the flip test |
| **8** | M2 distillation → `LEARNED_<month>.md` for Optimus · M4 calibration on the board · E5 DSR/PBO stopping rules · §11 cheap joins | the first rule with its own Brier |
| **9** | E1-E4 heads against GBM · L4 Qwen3 as a new arm · the stage contract (big) | a head beats GBM and its three controls, or the result is filed |
| **10** (landed 09-13 05:30) | the typed-event pipeline: vocabulary, contract, resumable L2 job, three consumers | 6,020 rows frozen PENDING_MODEL |
| **11** (landed 09-13 07:30) | the four books' next tests: C's falsifiers + registered construction, A's corner, B's verdict, vocabulary v2 | three closed, C CONDITIONAL |
| **12** (landed 09-13 12:45) | the daily pass (scheduled) · C at $10M · C v1's announcement sign built (unread) · lane D's role · Headline Arena removed | the board updates without a click |
| **13a/13b/13c** (landed 09-13 15:40-17:40) | books E/F/G + C v1 at both floors; hack3 → F; the allocator; the allocator moved into the seal authority | F positive at $10M in the current era; deploy plan handed to Murat |
| **14** (landed 09-13 18:00) | the always-on lab: eight loops, the dollar cap, decision-vs-reality, the catalyst calendar, the nightly NN refit, the idle-GPU queue, the theme streams; registered at logon | `BUILT_UNACCEPTED` until three on-machine dates pass |
| **15a/15b** (landed 09-14 02:00) | concurrent panel typing; engines served by the authority; the snapshot on the band; G price-scaled (+1.19%/mo t 6.07 at $10M, UNSIGNED); the hiring collector live on 192 boards; E1 at horizon 1 with a scalar arm — nothing beats its shuffle, the typing stops | G Amendment 1 is the morning's adoption decision |
| **15c** (landed 09-14 05:00) | **Books H and I**: option-grant opportunistic timing on `trans_code == 'A'` DERIV grant awards (the code `sec_insider_bulk_load.py` discards when it distils the events table) and buyback-vs-insider-selling divergence (`comp__funda.prstkc` joined through `link_ccm` to Form-4 sales -- the first join of the two in this repo). New family `NIGHT_JOB_BOOKS_2026_09_14` declared at size 2 BEFORE either read; both pre-registered UNSIGNED, linter PASS x2; one job, both floors, twin re-drawn at each, two deciding falsifiers each. **BOTH FAILED_VARIANT.** H: $3M -0.091%/mo t -0.29, $10M +0.347%/mo t 1.06 -- both falsifiers passed on legs that were never alive, and the draft says so. I: $3M +0.355%/qtr t 0.33, and BOTH falsifiers fired -- `buyback_only` beats the conjunction (+1.093%/qtr) and the top half of the band is negative. **Neither book carries the current era at $10M** (H +0.35%/mo t 0.54; I **-0.48%/qtr t -0.24**). Three spec assumptions died on contact with the disk: `funda` has no `rdq`, `apdedate` is not an availability date (measured lag 0 days at q50 AND q90), and the 10b5-1 flag DOES cover the sale side back to 2006 at 36-53%. | nothing to promote. The morning decides whether `buyback_only` earns its own registration -- at $10M that same control is -0.144%/qtr, so it is a small-name cell and probably not |
| **13 (spec)** (superseded by the rows above; spec `research_notes/2026-09-13/spec_allocator_kill_promote.md` + `research_next_books_published_rulers.md`) | **13a (this repo, CPU):** books E/F/G from the JKP panel on disk, replayed at $3M AND $10M with twins; C v1 read once Amendment 2 is signed. **13b (terminal repo):** the allocator — drawdown cuts, Thompson over survivors, equal-weight and random twins, the six-engine map from 13a's receipts, worst case printed before every sizing change | an engine with a positive $10M cell, or the accounts stay on 1/N |

**Every chunk from 5b on has a builder spec** (Sonnet, 2026-09-12, `research_notes/2026-09-12/`):
5b `spec_first_books.md` (+ `probe_short_interest.md`) · 5c `spec_cost_model.md` · lane D
`research_daytrading.md` · 6 `spec_agency_intake.md` · 7 `spec_lane_x.md` · 8
`spec_chunk8_memory_and_stopping.md` · 9 `spec_chunk9_heads.md`; and from 2026-09-11: L2/M1/M3/M4
`spec_events_and_calibration.md`, O11 `spec_price_targets.md`. A builder reads the spec, not this table.

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

---

## 14. THE ROOT-CAUSE AMENDMENT — 2026-09-19 (Fable, from six Sonnet reads; Murat's brief of the same morning)

Murat, condensed: *"we work on the roadmap a lot but we make no decisions. First settle HOW we
work: value proposition, the root of the problem, how it has been solved (patents, research,
public data). Sonnet researches, Opus builds, Fable validates and writes the roadmap. The engine
must DECIDE — buy, short, size, why. Strip the educational disclaimers for my own build. Social,
video and earnings-call text as inputs. Attach existing repos, do not rebuild. A thesis on every
closed family: doable? why did it fail? would something else have worked?"*

The six reads are under `docs/research_notes/2026-09-19/` (README there lists them). The
external GPT dossier Murat supplied (`Downloads/deep-research-report.md`, 2026-09-18) reaches
the same diagnosis as §0b: **the bottleneck is the artery from decision to paper account, not
discovery.** This amendment changes the order of work accordingly and adds nothing that is not
already licensed by a receipt. The one-file synthesis for any future session is
`docs/AEGIS_CONTEXT_DOSSIER_2026-09-19.md`.

### 14.1 The scoreboard, 2026-09-19 12:00 HKT (replaces the §0 fleet line)

| | |
|---|---|
| RESULT IMPROVEMENT | **NONE since 09-13.** F stays CONDITIONAL; nothing has traded on it. |
| best forward paper strategy | none — fleet **$440,907** live (hack1 93,673 · hack3 80,947 · hack4 89,362 · hack5 92,239 · hack6 84,686); 09-13 $452,832; 09-18 $448,555. Never deployed. hack2 retired (401 by design). |
| uptime | `AegisDailyPass` and `AegisIIF1NightLauncher` both 0x80070520 today (interactive-only tasks, session ended overnight); 0x80070420 for four days last week; the lab died and restarted three times since 09-18 13:41 with no exit reason recorded. The lab DID start the model server itself today (chunk 16a works). |
| LLM spend | DeepSeek balance $7.18 → **$56.98** (Murat's $50 top-up, 09-19); lab $0.00/$3.00 every day (local model). |
| tests / CI | 9,853 local (09-18), CI green `48fcf4b5`, docs pushed `92efb9d8`. |

### 14.2 HOW WE WORK — the loop, written down once

**Value proposition (personal build first):** every morning the system states, from registered
evidence only, *what it would buy or short today, at what size, why, and what would make it
wrong* — and it grades yesterday's statement against what happened. That sentence is the
product; the fleet, the lab and the ledger exist to produce and grade it. The public build is
the same sentence with the disclaimers back on.

**The loop (one question at a time, no step skipped):**

1. **A question enters** as one line in the registry with its corpse check — `brain_query` +
   `aegis_postmortems` + `NEGATIVE_RESULTS.md` — and a verdict class before any data is read:
   ALREADY_TESTED (read the receipt, do not re-run) · OPEN_AND_CHEAP · OPEN_BUT_NEEDS_DATA ·
   NOT_A_HYPOTHESIS (what observation separates it from factor beta?).
2. **Sonnet researches** the open ones: literature, patents, public data, what exists in the
   repo, and writes a note with a build spec (the six notes of 09-19 are the template).
3. **Fable** turns the note into a roadmap chunk + an UNSIGNED pre-registration draft
   (`docs/TRIALS/TRIAL-DRAFT-*`), with the family size declared and the twin named.
4. **Opus builds** the chunk — a night job, a book with twins, a pipe, a page — with tests,
   committed locally, never pushed.
5. **Fable validates**: reads the diff against the spec, runs the suite under the memory
   recipe (hold file → server stopped → suite → server unbound), pushes the verified SHA,
   watches CI, reads the first receipt.
6. **The night factory / the lab runs it** unattended; receipts carry the registered
   construction; the scoreboard changes only when a receipt does.
7. **Paper capital moves by rule** (the allocator: cut on drawdown, promote on twin-excess);
   the Decision Contract records what was decided, delivered, seen, refused, filled, scored.

**Rules earned this round:** a scheduled task is not an uptime guarantee (two failure codes in
one week; the lab owns its clock from chunk 17) · a verdict's construction is a test input
(the ledger has six ruler-caused kills) · "closed" families are read for their own reopening
clause before a new idea is registered · nothing LLM-derived allocates, still.

### 14.3 What the six reads changed (decisions, each with its receipt)

| read | decision |
|---|---|
| **failure thesis** (`research_failure_thesis.md`) | 57 entries: ~14 genuine mechanism deaths (stay closed), **six ruler-caused kills** (§32/34/36/38/40/41), the rest construction, data or process. **Five re-tests adopted, in this order:** (1) io_level / io_abn / skew as EXCLUSION SCREENS on existing long-only books (§26-28 flagged it three times, never run; $0); (2) a **13D event-window book** entering days 1-20 post-filing with the 13G placebo (the ledger's only placebo-confirmed positive event, §29-31); (3) LLM-autopsy precursor-library expansion (§51: 85% of exceptional moves unwarned; ~$0.001 each — the right use of the $50); (4) a $10M-floor re-audit of §35's ten adoptions and §22's KO-half graduates; (5) the TAQ cost curve on `fscore_lite` / `industry_mom`. |
| **ideas adjudicated** (`research_murat_ideas_adjudicated.md`) | CXMT/Micron: not a hypothesis as a trade (MU −5.2% on 09-14 was a SOXX-wide day) but **a missing event class** — add a `foreign_entrant_capacity` vocabulary id and register `TRIAL-FOREIGN-ENTRANT-IC` ($0). Supplier discovery: §12 reopens only as event-conditioned daily links keyed to a typed guidance event (the social spec's `growth_constraint_cited`). Insider buys, congress, ARK: **accruing forward, do not re-register**. Options flow: closed institutionally (§27); retail UOA needs $99-199/mo data — not now. ICT ritual: a frozen mechanical FVG rule on Alpaca 1-min bars is testable in lane D's contract; the prior is low. Overnight: read the 08-23 receipt; the survivor is an execution rule (reduce exposure intraday, never overnight) — adopt it in the allocator. **Construction:** `ce_kelly` sizing exists and is correct (`arena/policies.py`) but runs in 1 of 10 books; register a second arena book, same selection, Kelly-sized vs the EW twin, declared `ic_prior` and `kelly_fraction`. |
| **decision path** (`spec_decision_contract_and_path_audit.md`) | The engine already sizes (`investment_committee.compose_book`, kill conditions) and the fleet already refuses with a 43-class taxonomy; **no chat surface can reach either**, and the desktop Ask's system prompt forbids sizing. Build the Decision Contract on top of the existing numbers (spec §4: two new services, one copilot tool, one Ask route, one card) — no new model, no new capital risk. Personal mode = one backend flag + one frontend env var across 8 files (spec §5); the three export artefacts keep their disclaimer pending Murat. |
| **infra & cost** (`research_infra_cost_audit.md`) | Railway: `selfless-courage` (website backend, healthy) + `loving-elegance` (5 loops online, hack2 down by design, **`aat-loop-staging` orphaned — delete it**, seal-authority online but taking 404s on `/2026-09-19.json` from a client on the wrong path). Dollars are dashboard-only (path in the note). DeepSeek burn $16.81 over 08-24→09-13 by balance snapshots; the lab spends $0. **The lab owns its clock** (spec §4.3: dispatch the daily pass at 06:30 and the night launcher at 16:00 local with receipt-keyed already-ran gates, boxed; `atexit` exit reason on the lock). |
| **social/video** (`spec_social_video_pipeline.md`) | Phase 1 = Reddit comments (PRAW, free) + YouTube Data API (free quota) + SEC 8-K Ex.99 for calls; **Instagram has no lawful path (not built)**; X is pay-per-read (metered, off automatic cadence); transcripts need residential proxies at scale. Five variables with their nulls; new vocabulary id `growth_constraint_cited`; the seam is the existing `news_pull` registry + the local model with the enum on the wire. Needs Murat's keys. |
| **repos** (`research_external_repos_round4.md`) | **Scrapling ATTACH_NOW** (BSD, fixes the 403-ing collector class); NautilusTrader ATTACH_LATER (LGPL, fill-level cross-check for lane D); Kronos ATTACH_LATER (MIT K-line transformer as a NN-lab arm behind a prereg); FreqTrade (GPL, ideas only, done 09-07), Ghostfolio, Hummingbot, Osiris (token-promotion supply chain) IGNORE; **Xfield could not be identified** — Murat to send the URL. |

### 14.4 THE CHUNKS FROM HERE (one Opus at a time; Fable validates each)

| chunk | contents | gate to the next |
|---|---|---|
| **17** (landed 09-19 13:00) | **the lab owns its clock** (infra spec §4.3-4.4) + exit reason on the lock · **personal mode** (decision spec §5, 8 files) · the overnight execution rule noted for the allocator (terminal repo, next terminal chunk) | the lab's own 06:30 and 16:00 receipts land two days running; `AEGIS_PERSONAL_MODE=1` hides every banner in the desktop build |
| **18** (landed 09-19 15:30) | **the Decision Contract** (decision spec §4): `decision_contract.py`, `decision_ledger.py`, `step_decision_contract` in the morning, `get_todays_decisions` copilot tool, the `decisions` Ask route before the morning words, the IC card with falsifier + expiry | Murat asks the local model "what would you buy today" and reads engine-sized rows with kill conditions |
| **18b** (landed 09-20 18:20) | **the contract runs first; the grader exists.** `step_decision_contract` moved from fifth to SECOND in `scripts/daily_pass.py` (it had never executed once — see below) · the analyst box 4 h → 1 h with `DAILY_PASS_ANALYST_BUDGET_S = 3300` so the sweep stops ITSELF and names the shortfall instead of timing out · `refusal_class_basis` on every REFUSED contract row · new `backend/services/forecast_grader.py` + a `grade_forecasts` step after `book_cadence` | the decision ledger exists with DECIDED rows, and the prediction ledger stops being 100% ungraded |
| **19** (landed 09-19 17:30; re-test 1 READ: 4× FAILED_VARIANT, §58; N9 1,750 candidates) | **re-tests 1, 3 and the Kelly book**: `B_exclusion_screen` night job over the existing rank files; the LLM-autopsy library expansion under a $10 cap; `PROFIT_ALLOCATOR_v2` (the Kelly book: v1 retired 2026-08-24 under the router-identity fix with its construction never measured; v2 seeds under the corrected router, ENGINE_BASELINE_v1 is its EW twin, the seed flag stays Murat's); vocabulary v3 with `foreign_entrant_capacity` + `growth_constraint_cited` and the `L2_retype_v3` idle job; TRIAL-DRAFT-FOREIGN-ENTRANT written 09-19 | three receipts on the leaderboard, each with its twin |
| **20** (landed 09-19 18:30; refuses by name until the two keys exist) | **social phase 1** (social spec §3): Scrapling attached; Reddit comments + YouTube search via the registry; `growth_constraint_cited`; the five variables computed nightly into the panel; the shuffled-ticker and anonymised controls | the first `mention_velocity` and `stance_dispersion` columns on the E1 panel with their nulls (needs Murat's two keys) |
| **21** | **re-test 2**: the 13D event-window book with the 13G placebo, at $3M and $10M with twins | a receipt with the placebo beside it |
| **22** | re-tests 4 and 5 (the $10M re-audit; TAQ costs on the §22 graduates) · Kronos as a NN-lab arm behind a prereg · NautilusTrader cross-check for lane D | filed results, not activity |
| terminal | the fleet deploy (Murat's lines, unchanged) · delete `aat-loop-staging` · the overnight execution rule in the allocator · ~~the seal-authority 404 client~~ (benign: 2026-09-19 is a Saturday; the loops poll for a weekend book) | `SEAL AUTHORITY ALLOCATED day=` in the logs |

### 14.4b THE NIGHT QUEUE, after chunk 19

Two jobs join `scripts/night_factory_jobs.JOBS` in chunk 19. Neither is in
`night_factory.QUEUE`'s legacy default list — that list is the 09-08/09-09
night — so both are queued by name, with an explicit box. **A job killed at its
time limit writes no receipt at all** (2026-09-10, G3 at generation 340), so
these are the measured/projected boxes and not a default:

```
NIGHT_QUEUE="B_exclusion_screen:120,N9_library_autopsy:90" python -m scripts.night_factory
```

| job | stage | box | what it needs | what it refuses |
|---|---|---|---|---|
| `B_exclusion_screen` | `pnl` | **120 min** (it rebuilds Book F's monthly replay four times plus four rank panels; the three-book EFG replay alone measured 829 s) | `wrds/crsp_dsf_<year>.parquet`, `wrds/jkp_*`, and per screen: `wrds/tr13f_s34_<year>.parquet` + `wrds/tr13f_permno_link.json` (io_level, io_abn) or `learner/features_options.parquet` (skew_25d, skew_resid) | a screen whose rank sources are absent is REFUSED BY NAME with the paths it looked for, and is still NAMED in the Holm block; `--floor-usd` moves the book, the screen and both controls together |
| `N9_library_autopsy` | `signal` | **90 min** (resumable by cursor; a killed run continues rather than re-billing, and now writes a receipt when it is killed) | the incumbent autopsy JSONL under `research_gym/`, bars for the held panel, a reader, and — for a PAID run — a readable call ledger | `--reader local` refuses by name when no server is listening; `REFUSED_NO_LEDGER` before the first paid submission when the cap's ledger cannot be read; `REFUSED_UNPRICED_CALL` at the first flush that sees a row the price table could not price, naming the model id; the run stops at `config.N9_LIBRARY_AUTOPSY_MAX_USD` and prints the spend the CALL LEDGER reports, never a constant |

**The first probe is why the last two refusals exist** (2026-09-19 14:10 local,
`--max-usd 1.0 --workers 2 --reader deepseek`). DeepSeek renamed
`deepseek-chat`'s served model to `deepseek-flash` on 2026-09-14; the price
table did not carry the id; all 424 ledger rows came back `cost_usd: null`;
`spend_from_ledger` sums a null as **0.0**, so a $1.00 cap read **$0.00** for
fifteen minutes while the balance moved **$0.21**. The cap was not loose — it
could not bind. The run also filed 400 candidates, was interrupted, and left no
receipt at all, because the receipt is written by `night_factory_jobs.main()`
only after the job function returns. **A cap that reads an unpriced row as zero
is not a cap, and fifteen minutes of spend with no receipt is not a run.**

**It was built as `X5_exclusion_screen` and renamed the same day.** `X` is
lane X's numbering — the LLM inside the backtest — and the prefix is not
decorative: `protocol_p16.X_JOB_RE` (`^(X[0-9_]|L3[_$])`) binds EVERY receipt
whose job id matches it to the P1-P6 protocol, Lookahead Propensity and a
measured anonymisation gap, and `test_x_lane_receipt_completeness` walks every
receipt on disk to enforce it. This job reads no text and calls no model, so
it can never satisfy that block and the suite went red the night the first
receipt landed. **The prefix is a CONTRACT, not a label**, and the right fix
was the name: `B` is lane B (book constructions — `B_books_efg_replay`,
`B_verdict`), which is what this job actually is. The id `X5` was also already
taken twice — by lane X's own §10 row and by a 2026-09-07 weekend-lab
experiment.

`B` is a **defensive overlay on an existing book**, not a new selector: it adds
nothing to the one-selector bottleneck and may not be read as a return source
(§26/§27 close that and this job never reopened it). `N9` files **candidates**;
a candidate enters the precursor library only through `library_measure_*` +
`library_placebo_null`, because §37/§41's lesson is that a verdict which kills
or admits is the hardest kind to notice being wrong.

### 14.4c CHUNK 18b — 2026-09-20: two steps that existed and never ran

Chunks 18 and 14 both shipped working code that nothing called. Neither failure
was visible from the code, and both were visible in one `ls` of the data
directory. The pattern is the house failure mode with a new face: not "it runs
green and does nothing" but **"it would do the right thing and is never
reached."**

- **The Decision Contract had never executed once.** `step_decision_contract`
  was declared FIFTH in `scripts/daily_pass.py`, after the 2,362-symbol analyst
  sweep. The only pass that ever carried it — the 09-14 06:30 firing — wedged
  inside that sweep four steps earlier and was killed four days later, so
  `record_decided` was never called and
  `backend/data/optimus/decisions/ledger.jsonl` **did not exist at all**. Run
  by hand on 09-20 the builder produced **43 rows in 12 seconds**: 4 BUY, 1
  WATCH, 38 REFUSED (31 `EDGE_BELOW_BAR`, 7 `UNCLASSIFIED`). Twelve seconds of
  work had been standing behind two and a half hours of network for four weeks.
  It is now SECOND, immediately after `news_pull`, and it may move because it
  depends on nothing the sweep writes: `config.IC_FUNNEL_PATH` is a committed
  artefact, the IPS store is local, `paper_books.load_bars()` is a static
  parquet, and no step of the pass refreshes any of them.

- **The analyst box comes down 4 h → 1 h, and the sweep stops itself.**
  `DAILY_PASS_ANALYST_BUDGET_S = 3300` is the sweep's OWN budget, inside the
  3,600 s box. The two are different findings and the difference is the point:
  a thread abandoned at the box writes a `timeout` row and no receipt, while a
  sweep that reaches its budget flushes its parquet and returns a receipt
  carrying `truncated`, `symbols_reached`, `symbols_not_reached` and the
  reason. At the measured 4.45 s/symbol the 2,362-name band needs ~2.9 h, so it
  will truncate visibly, in a counted field, until the sweep is made cheaper —
  a box that timed out every morning would be a red line the reader learns to
  skim. The healthy-pass ceiling is now 9,300 s (2.58 h), down from 18,600 s.

- **The 7 UNCLASSIFIED refusals were one sentence, and it stays UNCLASSIFIED.**
  All seven came from `_refusal_sentence`'s NO_EVIDENCE branch — "no licensed
  signal speaks to this name". None of the 31 classes in
  `aegis-alpha-terminal/alpha/refusal_classes.py` covers it: that vocabulary
  was derived from an options book whose candidates are STRUCTURES on a
  forecast that already exists, so `REFUTED_ROUTE`, `EDGE_BELOW_BAR`, `MDE` and
  `CHAIN_UNUSABLE` all presuppose a signal that spoke. The terminal state
  `DATA_MISSING` is exact and is what a cross-repo census joins on. Every
  REFUSED row now carries `refusal_class_basis`, because UNCLASSIFIED had been
  covering two opposite findings: a sentence deliberately mapped to it (nothing
  owed) and a sentence nothing matched (a pattern owed). The payload counts
  both and `unclassified_owing_a_pattern` is the number that is work.

- **The prediction ledger was 100% ungraded, and now is not.** 24,839 records,
  every one with `resolved_at: null`; **17,614 past their resolution date**,
  the oldest since 2026-08-11. `lab_decision_vs_reality` printed that number
  every hour and re-grades nothing by design; the graders it aggregates over
  had no caller on this machine, because the only production caller of
  `ledger_resolver.resolve_due` is a background thread inside a server process
  that does not run here. `backend/services/forecast_grader.py` is the caller,
  and it contains **no return arithmetic**: it hands `resolve_due` a LOCAL
  price panel from `paper_books.load_bars()` in place of the yfinance default,
  and adds a named reason per record plus a receipt. First real run
  (`night_factory_2026-09-20/grade_forecasts_2026-09-20.json`): **14,703 newly
  resolved**, 2,911 `NO_BAR_FOR_RESOLUTION_DATE` over 105 tickers the local
  panel does not carry (it ends 2026-09-11), 6 `VOID`, 7,219 not yet due, 0
  `RECORD_LACKS_TARGET`, 0 `MECHANISM_HAS_NO_GRADER`. Every record is in
  exactly one bucket of a closed set; every declared mechanism is on the
  receipt, six of them at zero.

- **The first thing the ledger has ever said about itself is not flattering.**
  Over the 14,703 graded records: mean probability **0.510** against a base
  rate of **0.340**, Brier **0.2625** against a climatology of **0.2244**. The
  swarm is overconfident and does not beat the base rate. That is one number on
  one population and it is not a verdict on any mechanism — but it is the first
  time the question could be asked at all, and it is the reason the grader is a
  daily step rather than a one-off script.

- **The cost, paid in the making, and the guard it bought.** The new seam was
  not stubbed in `test_daily_pass.py`'s `calls` fixture, so one unit-test run
  drove the real grader against the live ledger. The ledger was restored from
  git and the seam list is no longer written by hand: it is derived from
  `scripts/daily_pass.py`'s own AST, and a pass whose seams are not all stubbed
  is a failing test rather than a write into `backend/data`. A seam list that
  depends on the memory of whoever adds the next step is not a weaker test — it
  is the real function running against the real data.

### 14.4d CHUNK 18c — 2026-09-20: the ROI rule, and what it refuses to rank

Murat, the same afternoon, verbatim: *"we need to fix the decision making
engine. it shouldnt make bad dessicions but it cant be sure so it doesnt make
one. from good decisions and return potetnials it should go with the highest
ROI like we have talked."* Spec (Sonnet):
`docs/research_notes/2026-09-20/spec_decision_engine_and_scenario_gym.md` §B
and §D. Built: `backend/services/roi_rank.py`, `config.IC_ROI_RANKING`,
`decision_contract.revise`, `decision_ledger`'s `REVISED` at rank 3.5.

- **The rule.** Among candidates that already cleared the hard gates, rank by
  `expected_return_net / downside` at the declared horizon, take the top
  `IC_MAX_TILT_NAMES`, size by fractional Kelly. Kelly is
  `arena.policies.size_ce_kelly` reused, not rewritten: feed it `z = roi_score`
  and `sigma = vol_horizon` with `ic_prior = ROI_DOWNSIDE_Z` and its Grinold
  form collapses to `w = f * mu / sigma^2` exactly. The four personalities are
  the `f`. **The worst case does not move** — `IC_SINGLE_NAME_TILT_CAP` (3%)
  and `IC_TOTAL_TILT_BUDGET` (10%) still bind after sizing, `_refuse_cap_breach`
  REFUSES rather than trims if the two layers ever disagree, and today's
  contract prints the same `-$100,000 of $1,000,000` it printed this morning.

- **The honesty rule, which is the whole of the second clause.** A candidate is
  ROI-scored only when BOTH numbers are measured — its leading signal's net
  forward return, copied off a receipt in `config.SIGNAL_MEASURED_RETURN`, and
  its own `vol_annual` — and only when that signal's measured **t** clears
  `ROI_MIN_T` (2.0). Anything else keeps today's verdict × confidence sizing
  and the row says `roi: NOT_CALIBRATED: <field> — <why>`. A test fails if any
  row's receipt path is not in this checkout: a measured return whose receipt
  moved is prose with a filename, and it would be sizing positions.

- **Which signals have a measured read, and which do not.** A sweep of
  `docs/TRIALS/`, `docs/archive/`, `NEGATIVE_RESULTS.md`,
  `STRATEGY_LIBRARY_MEASURED_2006_2019.md` and every `night_factory_*` receipt
  found a per-name NET magnitude for exactly three of the eight adapter
  signals — and they are exactly the three the registry independently permits
  to LEAD:

  | signal | measured | t | receipt |
  |---|---|---|---|
  | `profitability_small` | +0.241%/mo net, held-out 2019-2024 (72 months) | **none on the return** — the receipt states rank IC t 4.29, a statistic about the ORDER | `docs/TRIALS/TRIAL-SMQ-FWD.md` |
  | `insider_opportunistic` | +0.17%/mo net (BRAIN-003) | 1.40 | `docs/AEGIS_FINANCE_DOSSIER_2026-08-02.md` |
  | `fusion_insider_profitability` | +0.153%/mo net (BRAIN-007) | 1.66 NW | `docs/TRIALS/TRIAL-SMQ-FWD.md` |

  No row for `low_volatility` (registry: "ZERO net excess return", role
  FILTER — and its adapter is `higher_is_better=False` on vol, so a positive
  return there would license a risk filter to pick), `short_interest_level`
  (no per-name net magnitude anywhere in this repo), `earnings_surprise_monthly`
  (measured INVERTED, IC t −2.6), `rating_drift_3m` (`known_effect: null` —
  nothing has ever been measured for it) or `momentum_12_1` (CLOSED/REJECTED;
  −1.11%/yr net in the measured library, and an explicit written prohibition
  against forward seeding). **Books E/F/G/C — including F's +0.43%/mo t 3.12,
  the best number on the board — are BOOK-level reads against their own
  random-universe twins with no per-name column.** Attaching F's seasonality
  number to a `profitability_small` candidate would be a category error wearing
  the best number we have.

- **So today's contract scores 0 of 43.** 2 rows reached the rule and were
  refused at the confidence gate by name (CVLG on "no t on the return",
  INDV on "t 1.40 below ROI_MIN_T 2.00"); 38 never entered it, because the
  hard gates run first and the rule only ever sees survivors; 3 are agency
  BOOK rows. **The BUY set, every weight and every `decision_id` are
  byte-identical to this morning's file** — the rule changed what the rows SAY,
  not what the engine did. That is the finding and it is about the programme's
  evidence, not about a setting: the day a signal earns a t ≥ 2 read on its
  *return*, it gets a row and the rule fires with no code change.

- **Nothing here takes an LLM probability.** The grader's first run the same
  morning put the swarm at mean probability 0.510 against a base rate of 0.340,
  Brier 0.2625 against a climatology of 0.2244. A number that loses to its own
  climatology is not an expected return, and `roi_rank`'s docstring says so at
  the top so the next reader does not have to rediscover it.

- **§D, `REVISED`.** One new ledger state at rank 3.5 (the RANK map is floats
  now, so inserting it moved nobody) and `decision_contract.revise`, which
  re-scores through `recommendation.score_candidates`, recomposes the book at
  the parent's own capital, and writes a child row with `parent_decision_id`
  **only if direction or rank-cut changed** — otherwise nothing is written at
  all. The parent row on disk is never edited: it must stay gradeable exactly
  as it was decided. `revise` takes candidate FIELDS and refuses a string, a
  list, a dict or a bool by name, and a test runs the same revision under two
  different `reason` strings and asserts the child is identical. **An LLM
  cannot revise a decision**, and that is now a red test rather than a
  convention. No event wiring and no CLI yet — the service and its state
  machine only.

- **Still owed from the spec:** a `revise` caller wired to L2's typed events.
  §C, the scenario gym, was built the same evening — §14.4e.

### 14.4e CHUNK 18d — 2026-09-20: the SCENARIO GYM, and why its weight is zero

Murat, the same afternoon, verbatim: *"we cant be fully sure but we can have a
gut feeling thats what we are trying to cover it it has a good feeling about
something (test with llm and made up scenarios (make good and bad scenarios
using data we have like same situation in a ficiton setting to see what it will
respond) and we can use this with the engine to make a decison and update it on
events and news."* Spec §C. Built: `scripts/night_scenario_gym.py`
(`S2_scenario_gym`, stage `features`, box **90 min**, RESUMABLE),
`backend/tests/test_scenario_gym.py` (50 tests, no model, no `backend/data`),
and ten `SCENARIO_GYM_*` parameters in `config.py`.

- **What it asks.** N decision points from the E1 text-return panel joined to
  its forward SPY-excess open-to-open return, drawn by
  `x_lane_data.stratified_cells` (equal across MONTH BLOCKS, seed 20260920)
  and frozen with `cells_fingerprint` **before any model call**. Each is turned
  into a FICTIONAL case: X_anon_gap's own masking
  (`night_r2_monthly_llm.widened_digests`, the same object — a test asserts
  identity, not similarity) plus a fixed per-cell seeded date shift, with every
  number kept verbatim. The reader commits to
  `{direction, size_pct, expected_return_20d, confidence, falsifier}`, and
  **the whole schema travels in the system message** (the 09-13 lesson;
  `prompt_fingerprint().schema_in_system` is on the receipt).

- **The twins, and the one that matters.** Each case is asked five ways:
  `real`, `good_twin`, `bad_twin`, `control_good_twin`, `control_bad_twin`
  and `control_shuffled`. The
  twins append exactly ONE sentence to a byte-identical base, drawn from a
  frozen, hashed library of eleven good/bad development pairs keyed by the
  cell's dominant typed event and the vocabulary's own `direction_prior`. **No
  model writes a twin** — a twin the reader authored tests whether it agrees
  with itself. The two controls append a development from an UNRELATED family,
  **sign-matched** to the twin each is differenced against, and **the headline
  is the lift over them**: a gut that moves on the bad twin has proved nothing
  if it moves just as much on an unrelated sentence of the same tone.

- **The trap the grader is built around.** The spec's literal pass condition is
  `Δ ≥ 0 on a majority of three deltas`, which **a model that answers the same
  thing every time passes at 100%**. So the receipt prints `unmoved_rate`, both
  readings, and takes its `gut_score` from the STRICT rates — and the primary
  is `good_twin_lift_vs_control` / `bad_twin_lift_vs_control`, block-paired
  with a Newey-West lag-2 t over month blocks, never a level.

- **The adoption cap is CODE.** `adoption()` returns
  `reliability_weight: 0.0` unless N ≥ `SCENARIO_GYM_ADOPT_MIN_N` (300) **and**
  a forward record exists, and a test runs it at N = 300 *with* a forward
  record and *with* a measured resolution of 0.08 and still asserts 0.0. The
  measured number rides beside it as
  `reliability_weight_measured_not_granted`, labelled as what it would be. Its
  only route into the engine is one candidate field,
  `gut_signal {direction, confidence, reliability_weight}`, scored alongside
  the licensed signals — never a veto, never an override, never able to flip a
  REFUSED to a BUY (`roi_rank`'s docstring already said so before this existed).

- **Refusals by name, always all four.** `PENDING_MODEL`, `REFUSED_SCHEMA`,
  `REFUSED_LANGUAGE`, `INSUFFICIENT_N` — printed at zero when none fired, each
  mapped to one of `decision_contract.TERMINAL_STATES` (a derived check, not a
  third taxonomy). A reply that fails the schema is refused, **not repaired and
  not retried**: a repaired answer is a different experiment under the same job
  name. With the reader down the job writes `PENDING_MODEL` with the cells and
  the library hashed, and it never starts llama-server.

- **THE SMOKE RUN CHANGED THE DESIGN, which is what a smoke run is for.**
  First pass, ONE control twin appending an unrelated *favourable* sentence:
  good-twin lift **+5.3 pp (t 0.40)**, bad-twin lift **+52.6 pp (t 3.89)** —
  a headline result. It was an artefact: the bad twin's adverse sentence was
  being differenced against a *favourable* control, so the number measured
  **valence, not relevance**. Each twin is now differenced against an
  unrelated development of ITS OWN SIGN (six arms, not five), and the same 20
  cells say: good-twin lift **+5.3 pp (t 0.53)**, bad-twin lift **+23.7 pp
  (t 1.82)**, mean **+14.5 pp**. Roughly half of the apparent gut was the
  model following the tone of the last appended sentence. A test now pins the
  sign-matching.

- **Smoke receipt** (`night_factory_2026-09-20/S2_scenario_gym_run01_smoke.json`,
  cells `0f36bc53634e`, library `dc1d71a5509a`): 20 cases × 6 arms =
  **120 local calls in 127 s, $0.00**, refusals `{PENDING_MODEL 0,
  REFUSED_SCHEMA 0, REFUSED_LANGUAGE 0, INSUFFICIENT_N 1}` — **zero schema
  refusals on the first paid-for-nothing run**, which is what sending the
  schema in the system message buys. Gut score 0.55 (good twin raises 55% of
  20 pairs, bad twin lowers 55%); control-good raises 50%, control-bad lowers
  30%. The RETURN leg says nothing and says so: the reader answered HOLD or
  CASH on **60%** of cases, leaving 8 directional calls over 8 month blocks,
  sign accuracy 0.25, calibration `INSUFFICIENT_N` (8 < 45), block MDE
  **±235 pp/yr** and per-decision MDE ±16.6 pp. `paired_vs` REFUSED the
  real-minus-shuffled difference by name because the two arms did not share
  their month blocks. Nothing here is a finding; it is the machine working.

- **What it needs next, in order.** (1) The full N = 300 on an unattended
  night — see the queue line below. (2) **Typed-event coverage**: on the 20
  smoke cells only 15% carried a typed event, so most twins took the `generic`
  pair; the receipt prints that coverage, and L2's panel typing is what raises
  it. (3) A forward record: until the gym grades its own decisions forward,
  rule 4's second condition cannot be met and the weight stays 0 by
  construction, which is the intended state and not a defect.

**The night queue line** (§14.4b's table, one more row):

```
NIGHT_QUEUE="S2_scenario_gym:90" python -m scripts.night_factory
```

| job | stage | box | what it needs | what it refuses |
|---|---|---|---|---|
| `S2_scenario_gym` | `features` | **90 min** (300 cells × 6 arms = 1,800 local completions, ~32 min at the smoke's measured 1.06 s/call; the job owns its own clock too and stops ASKING at the box, then grades what it has, because a job killed at its limit writes no receipt at all) | `text_return_panel/news_returns_2025_26.parquet`, `prices_2025_26/bars.parquet`, `typed_events/*.jsonl`, and llama-server answering on 127.0.0.1:8080 | `PENDING_MODEL` with the cell list and the twin library frozen and hashed when the reader is down, and again after ten consecutive provider refusals mid-run (`--resume` continues from the answers on disk); `REFUSED_SCHEMA` on a reply that is not the committed-decision object; `INSUFFICIENT_N` on the calibration below 45 gradeable decisions; and `reliability_weight` 0 whatever the Brier says |

### 14.5 WHAT MURAT DOES (only what Claude Code cannot)

1. **Run the fleet deploy lines** (`aegis-alpha-terminal/docs/DEPLOY_PLAN_2026-09-14.md` §5) —
   every day on the old engines costs the fleet thousands of paper dollars on a tracker artery
   with no historical edge.
2. On Railway: **delete `aat-loop-staging`**, and read the Usage tab of both projects once
   (the note names the path); tell me the two monthly numbers.
3. **Rotate the FRED key** that lived in `market-engine`'s history (fred.stlouisfed.org →
   API keys); paste nothing here.
4. **Two API keys for chunk 20**: a YouTube Data API v3 key (Google Cloud console) and a
   Reddit script app (client id + secret), into `.env` under the names the spec gives.
5. **Xfield**: send the URL or a screenshot; nobody can find it.
6. Decide whether the three export artefacts (daily brief, tearsheet, guidance) keep their
   disclaimer in the personal build (default: they keep it).
7. Book G Amendment 1 (unchanged): adopt as a screen or not.

### 14.6 MUST NOT REGRESS (added 2026-09-19)

29. **A scheduled task is a fallback, never the clock.** Two distinct scheduler failure codes
    in one week (0x80070420, 0x80070520); the supervisor that is "live whenever the PC is on"
    dispatches its own time-of-day jobs with receipt-keyed gates.
30. **A supervisor records why it died.** Three lab deaths with no exit reason; `atexit` +
    the lock's `exit_reason`, and a kill by PID is a recorded reason too.
31. **Read the reopening clause before registering an idea.** Three of Murat's nine ideas were
    accruing forward or closed with a named reopener; a re-registration would have spent a
    family slot for nothing.
32. **An idle-queue job dates its outputs by the day** (09-18: three literal `RUN_DATE`s
    overwrote committed receipts three nights running; AST test over `LAB_IDLE_QUEUE`).

## 15. THE EXPLOIT/EXPLORE AMENDMENT — 2026-09-20 21:30 HKT (Fable, from Murat's review of the evening block)

Source: `docs/research_notes/2026-09-20/feedback_murat_review_2026-09-20_evening.md`
(his words, kept). The loop now exists end to end (§14.4c–e). His verdict:
"we fixed the fact that AEGIS was producing no decisions; now fix the fact that
its decision logic can still either make heuristic trades with no measured ROI
or refuse to explore anything uncertain."

### 15.1 The rule that governs every chunk below (Murat, absolute)

> No new research module is "finished" until it either changes a virtual/paper
> position, improves the weighting of an existing position, or kills a
> hypothesis that would otherwise have received capital.

A chunk's receipt therefore ends with one of three lines — `CAPITAL_CHANGED:`,
`WEIGHT_CHANGED:`, `HYPOTHESIS_KILLED:` — or the chunk is not closed.

### 15.2 The chunks, in his order (one Opus at a time; Fable validates each)

| chunk | what | the line it must print to close |
|---|---|---|
| 21 | **EXPLOIT / EXPLORE authority split** in `decision_contract` + `roi_rank`: EXPLOIT buys only a name with a calibrated positive `μ_i` (chunk 22's output; until then the EXPLOIT set is empty and printed empty); EXPLORE takes unproven positive-EV candidates (insider t 1.4, fusion t 1.66, ...) under a fixed paper-risk budget (`config.EXPLORE_BUDGET_PCT`, default 2% of equity, 0.25% per name) allocated by Thompson sampling over each hypothesis's posterior (`exploration_score = est_alpha − costs − risk_penalty + uncertainty_bonus`). The four heuristic BUYs stop existing as a third kind of thing: each is either EXPLOIT (calibrated) or EXPLORE (budgeted) or REFUSED. **Every dollar resolves daily to `benchmark` / `active_exploit` / `active_explore` / `cash`** (his item 11) and the contract prints that split. **The morning scoreboard** (his item 12) is the first block of the pass receipt and of the desktop Ask: NAV vs SPY, exploit P&L, explore P&L, decisions made, forecasts matured/graded, calibration, strongest new positive, strongest killed, one sentence on whether anything learned changed capital. | `CAPITAL_CHANGED: explore book seeded with N names at X% ...` |
| 22 | **Rank → return calibration.** For every signal `recommendation.score_candidates` can lead with, an out-of-sample map from signal decile to abnormal return AND downside at 5/21/63/126 sessions with a CI, from the panels on disk (walk-forward, date blocks, Holm over the family). Output `config`-free: a table under `backend/data/optimus/calibration/<signal>_<date>.json` that `roi_rank` reads by receipt path. Per-name `μ_i` replaces the family average. | `WEIGHT_CHANGED:` or `HYPOTHESIS_KILLED:` per signal |
| 22b | **Pre-decision evidence refresh** (2–5 min, boxed): last price, overnight news rows, catalysts, latest Form 4s, options snapshot where present, incremental analyst revisions — for the CANDIDATE names only — written to the contract's inputs before the rule runs. | `CAPITAL_CHANGED:` only if a decision flipped; else the count of refreshed fields |
| 23 | **Book-of-Books allocator.** Independent policies (SPY, F, quality/low-vol, insider, analyst, event, supply-chain, explore, random, cash) each with expected excess return, vol, drawdown, correlations and forward-evidence length; weights by independent contribution (Numerai MMC-shaped: the part of a book's return not explained by the others), under the drawdown budget; Book F enters HERE, never as a stock signal. | `WEIGHT_CHANGED: F 0 → x%` |
| 24 | **`world_model/` sidecar** (MiroFish-shaped, AGPL boundary kept: separate directory, separate process, structured JSON in/out, no import into `backend/`): one event package → graph → economic actors and mechanical chains → 20–50 LOCAL scenarios → consequence probabilities. Then its **historical replay** on 2018–2024 events with four controls (single LLM, graph-no-sim, shuffled agents, swarm). "If swarm adds nothing, kill it." | `HYPOTHESIS_KILLED:` or a feature table with a measured IC |
| 25 | **Event-conditioned supply-chain book** (the bridge to 24): typed event → causal graph → customer/supplier consequences → low-attention second-order names → 5/21/63-day outcomes, vs the rejected unconditional customer-momentum corpse (NEGATIVE_RESULTS, read the § before registering). | one of the three |
| 26 | **Analyst v2** (revision magnitude, text opinion, disagreement, stickiness, reaction already priced; NOT target upside) and **Insider v2** (open-market cash, cluster, role, distress state, drawdown, short interest; 1/5/21/63 d). Each as its own PRODUCT_EXPERIMENT book. | one of the three, each |
| 27 | **NN routing**, last: predicts which specialist is useful now and return distributions, trained on the resolved decisions the ledger now accumulates; world-model outputs as features; targets are reality. | one of the three |

Also in 21, the two code items: the config comment "five arms / 100" → six /
120; and `SCENARIO_GYM_ADOPT_MIN_BLOCKS` (independent month blocks, default 12)
beside `SCENARIO_GYM_ADOPT_MIN_N` — three hundred correlated scenarios are not
three hundred observations.

### 15.3 Interdisciplinary intake (Murat: "find projects like these")

A Sonnet read is due at `docs/research_notes/2026-09-20/research_world_model_and_analogous_projects.md`:
MiroFish/OASIS/Graphiti, agent-based market simulators, generative-agent
social sims, prediction-market aggregation, behavioural-finance measures that
exist as DATA, media/trend and political event data, supply-chain graphs, and
the quant references for 22/23. Every entry: licence, what to take, what to
refuse, the first test. Ideas enter as chunks only through §15.1.

### 15.4 MUST NOT REGRESS (added 2026-09-20 evening)

33. **A metric at zero can be a dead process.** `railway metrics` read 0 MB on three
    crash-looping containers; liveness is the process's own first log line.
34. **A rule that scores the empty set prints why per row.** The ROI rule refused
    every name today and said which field was missing; a rule that had guessed
    would have been a worse rule with a better-looking receipt.
35. **A control must match the treatment's valence.** The gym's first bad-twin lift
    (+52.6 pp, t 3.9) was tone; sign-matched controls halved it. Every twin is
    differenced against an unrelated development of its own sign.
36. **Uncertain means EXPLORE, never freeze.** t ≥ 2 governs claims and EXPLOIT
    capital; it does not govern what paper money may test.
