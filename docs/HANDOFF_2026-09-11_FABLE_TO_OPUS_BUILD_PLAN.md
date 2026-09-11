# HANDOFF 2026-09-11 — BUILD PLAN FOR OPUS (root first)

**From:** Fable 5.1 (verification + synthesis; five Sonnet research agents; $0 LLM; no code written).
**To:** the Opus session in Murat's terminal that BUILDS. Spawn build agents on `model: "opus"`,
research/survey agents on `model: "sonnet"`, never Fable.
**Read order:** this file → `ROADMAP_2026-09-11_ROOT_FIRST_THE_OPERATOR_BOARD_AND_THE_LEARNING_LOOP.md`
(the why, the lanes, the controls) → `AEGIS_VISION_2026-08-28_MURAT_IN_HIS_OWN_WORDS.md` §6 (Murat's
words today) → `HANDOFF_2026-09-10_SESSION_CLOSE.md` §2 and §5 (the twelve defects and the must-not-regress
list you inherit) → `CLAUDE.md`. Run `session_briefing()` + `aegis_verified_state()` first.

Murat's mandate, in intent: *go to the root; one click and the app updates itself, pulls all the news,
runs the sims, shows the NN; an assistant inside that reads the project but cannot change it; news from
Asia to the West; books I describe in a sentence, held on paper, graded against what happened; don't give
me tasks Claude Code can do.*

---

## 0. SCOREBOARD AT HANDOFF

| | |
|---|---|
| RESULT IMPROVEMENT | **NONE.** Verification and planning only. |
| verified defects (both silent) | **(1)** `.env` never loads in the packaged app: `backend/config.py:21,97` roots on `__file__`, `AegisDesktop.spec` never bundles `.env`. Every keyed source is absent in the .exe and present from source. **(2)** pywebview 6.2.1 `private_mode=True` default + `webview.start(when_ready)` with no override in `desktop/aegis_desktop.py` → `localStorage` wiped per launch → the guide and tour return every time. |
| verified non-defect | the "~30 news": every news array caps at 15 (`routers/news.py:63`); the `/news` page stacks GDELT + headlines + sectors. Not a bug; a page with no operator purpose. |
| only live lane | R2, panel B **`PENDING_MODEL`** (`night_factory_2026-09-10/R2_widened_panelB_run01.json`; port 8080 refused; last app launch was `--no-llama`) |
| CI / tree | green on `87febf1`; tree clean at session start; this session adds docs only |
| deadline | `learner/evidence_memory.jsonl` 65.16 MB, growing nightly; GitHub rejects at 100 |
| terminal repo | HEAD `637e661`, fully invested six books since 09-09, mandates to 2027-12-31; `docs/HANDOFF.md` there stops at 09-03 |

---

## 1. PHASE 1 — the app runs the code you read (roadmap O1-O3, O7). Do this first, alone, before any agent.

### 1.1 O2 — `.env` and every other `__file__`-rooted path (30 min)
- `backend/config.py`: add `_repo_root()` exactly as `backend/routers/control.py:47-64` does
  (`AEGIS_REPO_ROOT` if set and `is_dir()`, else `Path(__file__).parent.parent`); `PROJECT_ROOT = _repo_root()`.
  `load_dotenv(PROJECT_ROOT / ".env")` then finds the real file under the shell.
- New test `backend/tests/test_frozen_path_family.py`: walk `backend/`, `desktop/`, `scripts/night_factory*.py`
  with the AST (skip docstrings — protocol §10), find every `Path(__file__)`-rooted expression that reaches
  `.env`, `data/`, `vendor/`, `optimus/`, or a `*.json`/`*.db`/`*.jsonl` literal, and assert each is either
  in an allow-list (with a one-line reason) or goes through a root resolver that reads `AEGIS_REPO_ROOT`.
  This is the test that turns defect family #14 from a category into a gate.
- Acceptance: `python -m desktop.aegis_desktop --headless` and the launcher both report
  `llm_usage()["providers"]["configured"] == ["deepseek"]` (the source list). Add that line to the
  headless report.

### 1.2 O3 — storage that survives the window (10 min)
- `webview.start(when_ready, private_mode=False, storage_path=str(root / "backend" / "data" / "optimus" / "webview_profile"))`
  where `root = repo_root() or REPO`. Never a path inside the bundle (family #14).
- Add `webview_profile/` to `.gitignore`. Log the storage path in `aegis_desktop.log` at start.
- Acceptance: launch, dismiss the guide, close, relaunch: no guide; `? Guide` reopens it.
  Verify by reading the log AND by Murat relaunching (roadmap §5 item 1).

### 1.3 O1 — the thin launcher (the architectural change; half a day)
The bundled `backend/` is the reason the app cannot update itself and the reason five path defects
existed. Replace the frozen backend with a launcher:

- `desktop/launcher.py` (what PyInstaller freezes; ~10 MB with pywebview only) does, in order, each with a
  log line and a field in a `launch_receipt.json` under `backend/data/optimus/`:
  1. find the checkout (`AEGIS_REPO_ROOT`, then the .exe's parents, then a `%LOCALAPPDATA%\Aegis\repo_path`
     file written on first run; refuse with a readable window if none);
  2. `git status --porcelain` — if dirty, **skip the pull and say so on the splash** (never stash, never
     reset); else `git pull --ff-only` and record before/after HEAD;
  3. `pip install -r requirements.txt` only if `sha256(requirements.txt)` differs from the one in the
     receipt of the last successful launch; use the checkout's interpreter (`control.job_python()` logic,
     lifted into a shared `desktop/_interp.py`);
  4. rebuild `frontend/out` only if `git diff --quiet <last_export_head> HEAD -- frontend/` is non-zero
     (needs Node; if Node is absent, say so and serve the last export);
  5. `subprocess` the shell: `<interp> -m desktop.aegis_desktop --page /desktop`, with the launcher owning
     the child through the same Windows job object `llama_server.py` uses, so closing the launcher kills the
     shell and the shell kills the model server (must-not-regress 16).
- `AegisDesktop.spec` shrinks to the launcher; delete the 8 MB walker and the `backend/` datas. Keep the
  icon. The smoke test becomes: build, run from a directory outside the repo, assert `/api/health` reports
  the checkout's HEAD (add `git_head` to `/api/health` — a five-line change in `backend/main.py`).
- Acceptance: on a checkout one commit behind origin, the .exe pulls, skips pip (hash unchanged), skips the
  frontend rebuild (no frontend change), starts, and the board shows the new HEAD. On a dirty checkout it
  starts without pulling and the splash says "local changes present — not updated".
- **What this retires:** defects #8, #9, #10, #11 and the `--run-module` dispatch become dead weight;
  keep `dispatch_module` for one release, then delete it with its three tests once the launcher has run for
  a week without needing it.

### 1.4 O7 — the model starts when asked (20 min)
- `POST /api/control/ask`: if `llama_server.status()` is `down` and the request carries `start=true`
  (the Ask page sends it after the user confirms), call `llama_server.start(wait_s=90)` then answer;
  if `listening && !ready`, wait up to 90 s polling `/health`; foreign-server rule unchanged.
- Then run R2 panel B from the app (`R2_monthly_llm_widened` is in `night_factory_jobs.JOBS`); the receipt
  must lose `PENDING_MODEL`. Re-run the AMNESIA canary on the widened set — a widened result without it is
  not a result.

### 1.5 Suite, commit, CI
`python -c "import pytest_timeout"` → `AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/ -m "not slow"`.
Commit 1: config root + family test. Commit 2: storage + launcher + spec + health HEAD. Then
`python -m scripts.ci_watch --wait`. A red CI is this session's next task.

---

## 2. PHASE 2 — the board and the morning click (O4, O5, O6). Two Opus agents in parallel after Phase 1.

### Agent A — the developer board (O4)
- `frontend/src/app/desktop/page.tsx` becomes the board. Cards, each from one `/api/control/*` payload:
  services (existing) · night (last `LEADERBOARD.md` rows + tonight's `NIGHT_PLAN` — existing routes) ·
  fleet (existing `/fleet`, render `se_daily_excess_pct` and `estimable`) · **coverage** (new
  `GET /api/control/coverage`, reads the source registry and the corpus dir; em dashes until lane N lands) ·
  **ledger** (new `GET /api/control/ledger`: open forecasts, graded last 24 h, Brier by `model`, from
  `belief_state.ledger_health()` + `calibration()`) · **code tree** (new `GET /api/control/tree?root=scripts`
  and `GET /api/control/file?path=…` — read-only, path must resolve inside the checkout, size cap 512 KB,
  returns the file plus `git log -3 --format=%h %ad %s -- path`) · app log tail (new
  `GET /api/control/app-log?tail=200` reading `aegis_desktop.log`).
- In desktop mode the sidebar's first entry is the board; the website's pages remain below a divider.
- Rule: a card shows a number with its receipt path, or an em dash. No stand-ins.
- Test: `test_control_router_authority.py` extended — the new routes are GETs, no writes, paths sandboxed
  (a `..` or absolute path outside the root is a 403 with the path named).

### Agent B — the Morning click (O5) and the reading assistant (O6)
- `POST /api/control/morning` runs, in order, each step writing into ONE receipt
  `backend/data/optimus/morning/<YYYY-MM-DD>_run<n>.json`: `news_pull` (lane N; until N-A exists, the
  existing GDELT + yfinance fetch, honestly labelled `dashboard_fetch_not_corpus`) → `digest` (the R2 digest
  builder over yesterday's rows, anonymised, same spec hash) → `mark_books` (the PI daily-check function,
  called in-process) → `forecasts` (B5 stub: one `PredictionRecord` per book with `model="engine"` until
  the local model writes its own) → `coverage` → `ready`. A step with no network refuses by name. Idempotent
  per day (run<n> increments; the board shows the latest).
- `POST /api/control/ask` gains retrieval: a deterministic router — a repo-relative path in the question →
  `file` tool; a job id → its latest receipt; "fleet"/"books" → `/fleet`; "tonight"/"queue" → the plan;
  else context = `docs/INDEX.md` TIER 0 names + the newest handoff's §0 + today's morning receipt. The
  tool set is the five GETs above and nothing else; the AST test asserts no `open(…, "w")`, no
  `subprocess`, no broker, no `requests.post` in `control_ask.py` (split `ask` into its own module so the
  test is narrow). Every answer ends with `sources: [paths]`.
- "What do you think happens today?" answers from today's forecast rows; if none, it says the morning has
  not run and offers the button. It never invents a forecast in the answer path; the forecast is written
  by the morning step, graded by `pi_ledger_resolve`.
- Register `pi_ledger_resolve` in the desktop backend's scheduler (it already runs on Railway) so the local
  `predictions.jsonl` is graded; the ledger card shows `graded_last_24h` moving.

---

## 3. PHASE 3 — whole-market news (lane N). One Opus agent, then a Sonnet agent for N-D's name table.

- `scripts/news_pull.py` with `--source {alpaca,gdelt,gnews,akshare,edgar,nikkei} --since --until --resume`;
  per-source cursor in `backend/data/optimus/news_corpus/_cursors/<source>.json`; rows as in roadmap N-A;
  `first_seen_utc = datetime.now(timezone.utc)` at write time, `published_utc` parsed with the source's
  timezone recorded as `tz_source`. Registry `backend/data/news_sources.yaml` (N-B) gates the source list;
  an id not in it is a parse-time refusal. Receipt per run per source: requested, received, new, dupes
  (by `raw_id`), failures with the first error string. A source with two consecutive zero-row runs is
  `RED` in the coverage payload.
- Order of sources: Alpaca first (finish the backfill from the last cursor; the 83.6% stall had no cursor —
  this is the fix), GDELT DOC 2.0 (queries: one per region × one per theme list from `theme_baskets.yaml`;
  honour the rate limit with backoff; fall back to NGrams bulk on 429), Google News RSS sweep (registry
  `pit_grade: index_state` — usable for coverage counts, **never for labels**), AKShare, EDGAR Atom, Nikkei.
- `E1_news_return_panel --append` (N-C): reads only rows newer than the panel's `max(first_seen_utc)`,
  labels at the first open strictly after `first_seen_utc`, `pit_dv_21` from bars, PIT re-verify on every
  append (0 violations or refuse). Add it to `night_factory.QUEUE` after `N3_frozen_embedding_head` and
  give both receipts a `next_test` field (the planner is starved without it — 09-10 §5).
- N-E analyst snapshot: `scripts/analyst_snapshot.py`, one parquet row per (symbol, date), yfinance +
  Finnhub free tier; the receipt says the series starts today.
- N-G: `pre-register-trial` for TRIAL-HIRING-PIVOT-1 BEFORE the collector labels anything; then
  `scripts/hiring_pull.py` over Greenhouse/Lever/Ashby public JSON for names that expose a board; store
  role titles and counts per (company, date); features computed in the trial's own script. Control and
  placebo as the roadmap states. **No LinkedIn.**
- Coverage card reads all of the above.

---

## 4. PHASE 4 — books as data (lane B). One Opus agent; B2's UI after B1/B3/B4 are tested.

- `backend/services/paper_books.py`: `PaperBook` dataclass wrapping `backend.strategy.contract.Strategy`
  (+ cadence, origin, origin_text, control_twin_id); `create(strategy, cadence, origin, origin_text)` builds
  the twin(s) (random-universe same-band; beta-matched if long-only), writes both to `paper_portfolios`
  with `portfolio_id = fingerprint`, and returns the pair. Refuses a book without a twin.
- `backend/services/book_cadence.py`: a scheduler pass that, per cadence bucket, marks every book from the
  local bars parquet (`prices_2025_26/bars.parquet`) and yfinance for missing symbols, writes `paper_nav`
  rows keyed (portfolio_id, timestamp), writes one receipt per pass (nothing-to-do included), and at a
  decision time writes the `PredictionRecord` (B5) with `benchmark = control_twin_id`.
- `POST /api/control/books/propose` (B2): sends Murat's sentence to the local model with the `Strategy`
  schema and the `theme_baskets.yaml` universe names; the model returns JSON; the engine validates through
  `Strategy.__post_init__` and `CostModel` (zero cost refused by construction), resolves the universe (≥ 5
  names or refuse), prints the worst case in dollars, and returns the contract + twin + worst case.
  `POST /api/control/books/hold` (B2) freezes it — the only write, gated on `AEGIS_CONTROL_ENABLED=1`, and
  it writes a paper book, never an order. The AST test stays: no broker symbol anywhere in the control
  plane.
- Regret page (B6) reads `predictions.jsonl` grades per book and model.
- Tests: fingerprint stability across a reload; a twin exists for every book; a mutated `Strategy` is a new
  fingerprint; a decision writes exactly one forecast row per book; the worst case printed equals
  `n × notional% × stop%`.

---

## 5. PHASE 5 — the engine lanes (L, E), as night-queue jobs with three controls each

In `scripts/night_*.py` pattern, each with a receipt and `next_test`:
- **L2** typed-event extraction (`night_l2_typed_events.py`): vocabulary frozen in a prereg; 500-row
  inter-prompt kappa; shuffled-text arm.
- **L3** Lookahead Propensity (`night_l3_lookahead.py`): hit rate before vs after cutoff for Qwen2.5-7B and
  DeepSeek on the R2 digests; result attached to every 2015-2024 LLM number on the leaderboard.
- **E1** typed-event tabular head; **E2** frozen embedding at 5/21 sessions; both with TF-IDF, shuffled,
  no-text controls per era.
- **E3** adaptive conformal intervals on the winner (if any) with realised coverage per vol regime; **E4**
  ADWIN-gated refit vs fixed window.
- **E5** DSR + PBO over `G3_evaluations.jsonl` as the archive's stopping rule; a failing lineage is
  `DEPRIORITIZED` with the number printed.
- **E6** evidence-memory rotation — **do this in Phase 1's session if the file passes 80 MB.** Split by each
  row's own stamp; live month untracked; a test that every row survives.
- **L4** Qwen3-30B-A3B measured idle (prompt-eval tok/s is the deciding number), then `R2-Qwen3` as a new
  arm with its own registration.

---

## 6. WHAT NOT TO DO

- Do not add a learned router or combine the LLM read with the engine score. One independent selector
  with evidence.
- Do not quote N3 against R2, C2's levels without the look-ahead note, or any 2015-2024 LLM number without
  L3.
- Do not scrape LinkedIn. Do not use Google News RSS rows to label a return.
- Do not fix "APIs not connected" by bundling `.env` into the .exe. The launcher reads the checkout.
- Do not rebuild the 1.1 GB onedir. Phase 1.3 replaces it.
- Never `taskkill /IM`; never move `.env`; never `--no-verify`.

## 6b. AMENDED THE SAME EVENING — chunks, and four more lanes

Murat re-stated the problem (VISION §6b): an investing agency for an average person, thousands of paper
books as data accumulation, the LLM inside the backtest, results as context for the brain. The roadmap's
amendment (§7-§13) adds lane **A** (goal intake → three graded options → daily hold/sell/buy-more with a
forecast row → protect-first), lane **M** (one ledger schema; ExpeL-style distillation into
`brain/LEARNED_<month>.md` with each rule carrying its own Brier; hindsight-safe retrieval; GBM as the
mandatory control for any net), lane **X** (LLM-in-backtest REOPENED: horizon/hold rule, belief
elasticity from C1's counterfactual rows, scenario forecasts, regime routing — all under the P1-P6
protocol, Lookahead Propensity and a measured anonymisation gap), and the cheap joins from Qanat/Notes
(published-anomaly cadence, read-only MCP surface, decay-blended weights).

**Chunk 1 landed (validated by Fable 2026-09-11):** `110aec1` config root + `test_frozen_path_family.py`
(24 allow-listed hits, 10 of them `_PENDING_LAUNCHER` — the launcher retires them), `6f9c265` storage
survives the window (+ `llm_providers` in the headless report: `configured: ["deepseek"]` from source),
`ae71a37` ask starts the model only when nothing is listening. Suite 7,966 → 7,983. Not verified: the
packaged .exe (not rebuilt; chunk 2 replaces it) and the relaunch acceptance (Murat).
**Defect found during validation, for chunk 2:** `backend/tests/test_n6_battery_v2_and_n7.py:233` feeds
fake N9 receipts from `tmp_path` to a function that appends its summary row to the LIVE
`learner/evidence_memory.py:STORE` — every suite run adds a `SKIPPED -- nothing here` row to a tracked
65 MB ledger (one was discarded on 09-11). Give the writer a store parameter (or monkeypatch `STORE`
in the test), and add a guard test that the fast suite leaves `evidence_memory.jsonl` byte-identical.

**Found live 2026-09-11 13:46-13:56 (Murat ran the old .exe twice):** the 09-10 bundle's backend thread
dies before binding a port, deterministically (two runs, `health never answered within 242s`), while
`python -m desktop.aegis_desktop --headless --no-llama` from source reports `health_ok` in 1.55 s with
`configured: ["deepseek"]`. The old build has no stderr, so the cause is unrecoverable from it; the
launcher (chunk 2) runs the shell from source and captures the child's stderr. Also found: a second
instance's `stop_if_owned` killed the first instance's model server (ownership is per checkout) — roadmap
O9. Interim: a desktop shortcut `Aegis (source).lnk` runs `pythonw -m desktop.aegis_desktop` from the
checkout; `.env` was copied to `dist/AegisDesktop/_internal/` (local, gitignored) and should be deleted
with the old dist. **Chunk 3 gains O8 (the uncapped universe page) and O9 (instance ownership + no
Railway scheduler on the laptop).**

**Chunk 2 landed (validated 2026-09-11 afternoon, CI green on `571bf98`):** `8e3a69c` the suite's ledger
guard (the run exits 1 if any test writes the evidence ledger), `73f7a2b` E6 rotation (102,029 rows in →
102,029 out, split by each row's own stamp; the live month untracked), `ae073ca` the thin launcher (1,058
MB → 37 MB; pull → pip-if-hash-changed → export-if-frontend-changed → shell from the checkout's venv,
under a job object; `git_head` on `/api/health`; ownership by PID; scheduler and warm loops off in
desktop mode unless `AEGIS_DESKTOP_SCHEDULER=1`), `f7bf875` an env leak in its own test, and in the
terminal repo `e613082` the handoff brought to 09-11. Suite 7,983 → 8,063.

**Chunk 3 landed (validated 2026-09-11 evening; one agent died mid-T1 on an auth error and a second
resumed from the tree):** `0175297` **T0 — the root cause of every failed launch today**: a windowless
process (pythonw, `console=False`) has `sys.stdout is None` and uvicorn's log formatter calls
`sys.stdout.isatty()` before binding; streams are now bound to the app log and `use_colors=False` is
passed; the launcher redirects both child streams; pywebview pinned in `requirements.txt` (the venv
lacked it). `1b8e257`/`5a25e97` T1 one `__ticker__` shell serves every symbol (and answers HEAD).
`9f8e25f` T2 `cache_swr_202`: desktop heavy endpoints answer 202 with progress until the cache fills
(56 names: 232.7 s cold). `e5af37b` T2b the desktop screener over the real universe: tier 1 all 3,056
scorecards at 0.1 s, tier 2 the top 200 by `p_beat` through the Monte Carlo in 10.2 min (a full deep
pass would be ~2.8 h); the Railway path keeps its 80-name cap, pinned both ways by an AST test.
`e2207d1` T3+T4 the universe page (`potential_universe/2026-09-02.jsonl`, 3,056 rows, joined with
books, the analyst snapshot and the last review) and the board (`/tree`, `/file`, `/app-log`,
`/ledger`; `.env` and secrets refused by name before resolution, then the checkout sandbox).
`a6d8a39` T5 a closed month left untracked fails a test and warns on the night plan. Suite 8,063 →
8,107. **Upstream fact for Murat:** the scorecard vintage is 2026-09-02 because the terminal repo's
newest tracker day file is 2026-09-02; refresh = run the tracker there, then
`python -m scripts.potential_universe_run`.

**Chunk 3b landed (validated 2026-09-11 night):** `2d4ca31` O5 the Morning click (seven declared
steps, one receipt per day; a real run on this machine took 389 s and exposed three defects, fixed) +
O6 Ask with read-only tools (deterministic router; the AST test walks both modules for no write, no
subprocess, no broker, no POST; M3's hindsight-safe retrieval with its three tests); `2940d1a` O11 the
52-week target with **no caps** (`STOCK_CAGR_CAPS` gone; the consensus clip replaced by an isotonic map
that is the identity until fitted and says so; the 12-month figure is `paths[252]` of the same
simulation, never a root) + M4 Murphy's Brier split on the board; `9e83cfc` three defects the full
suite found; `51953d5` (Fable) a band wholly above spot is withheld with its reason (NVDA's p10 was
$234.93 on a $218.36 stock — the error quantiles are pooled per bucket and not yet conditioned on the
upside tercile; that conditioning is chunk 3c's first item). **The IBES backtest ran**: 390,368 cells,
7,439 names, 228 months (2005-2023), walk-forward — de-biased target MAE 45.3 / hit 48.4% vs consensus
48.8 / 39.2% in POOLED and better in **every** era; **the drift-only control beats both on MAE in every
era** (37.6 pooled), which is the bar `TRIAL-CALIBRATED-TARGET-UPSIDE-1` (drafted, UNSIGNED) must clear.
Audit on the six names: NVDA's gap to the consensus is `HORIZON_MISMATCH +165.6pp`. **The launcher was
rebuilt after T0 and verified from a no-console launch** (`Start-Process`): backend up in 2.32 s, the
board's routes answering, FRED 23/23 with keys visible, one scheduled job (the ledger resolver), stopped
by the launcher's PID with nothing left running.

**Execution is now the chunk table in roadmap §12.** Phases 1-5 above map onto chunks 1-5 and 9; lanes A,
X and M are chunks 6-8. Chunk 1 is running as an Opus agent (config root, family test, storage, ask-start);
chunk 2 (the thin launcher + evidence-memory rotation + terminal handoff) is next. Each chunk: Opus commits
locally → Fable reviews the diff, runs the fast suite, pushes, `ci_watch --wait`.

## 7. SESSION ORDER

1. Protocol (briefing, verified state, `brain_query` "thin launcher desktop", `aegis_postmortems`).
2. Phase 1 alone: 1.1 → 1.2 → 1.3 → 1.4 → suite → two commits → `ci_watch --wait`.
   Ask Murat (roadmap §5 item 1) to relaunch the .exe and report; that is the acceptance of 1.2 and 1.3.
3. Phase 2: agents A and B on Opus, in parallel; each writes its report incrementally; suite; commit;
   `ci_watch --wait`.
4. Phase 3: one Opus agent for N-A/N-B/N-C/N-E; one Sonnet agent for the N-D name table; the N-G prereg
   is written by the session, not an agent.
5. Phase 4, then Phase 5 as night-queue jobs. E6 whenever the file passes 80 MB.
6. Handoff with a SCOREBOARD first; memory file; push; `ci_watch --wait`. Update
   `docs/INDEX.md`'s TIER 1 line only if a new roadmap replaces this one.
