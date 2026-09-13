# Chunk 14 Spec: The Always-On Lab

Source: Murat, 2026-09-13 (verbatim): "run backtest for NN, do a learning lab
for it to continuously learn. for night sims update it such that it is live
whenever pc is on, fetching live data for news the LLM and the engine is
gathering data and learning, decision vs reality, upcoming dates and
possibilities, linkedin theory, business pivot to ai, motivation, holders, the
business, the future anything."

Source roadmap: `docs/ROADMAP_2026-09-11_ROOT_FIRST_THE_OPERATOR_BOARD_AND_THE_LEARNING_LOOP.md`
lanes L, E, M, X, §13 MUST NOT REGRESS (23-28). `docs/AEGIS_STRATEGIC_INVARIANTS.md`
1-16. Read-only spec — no repo files modified by this task.

Repo files this spec builds on (read in full or in relevant part — reused, not
redesigned):

- `scripts/daily_pass.py` — the idempotent-driver pattern: a declared STEP list
  walked in order, five statuses (`ok`/`nothing_to_do`/`refused`/`error`/
  `skipped`), one receipt per date under `night_factory_<date>/`, exits 0
  whenever the receipt was written, `--force` for a second pass, `--schtasks`
  prints the registration and runs nothing.
- `scripts/night_factory.py` — `QUEUE: list[(job_id, minutes)]`, `NIGHT_QUEUE`
  env override (unknown job id refuses at parse), `STOP` file, `TIMEBOXED`
  jobs, `refuse_if_the_machine_may_sleep()` (line ~424, `powercfg`-derived,
  `None` = CANNOT DETERMINE + start anyway + say so), `NIGHT_RUN_DATE` (unset
  = today, never a literal default — the 2026-09-13 lesson in this file's own
  header).
- `scripts/night_factory_jobs.py` — the CPU job bodies (D1/D2/G1/D3/N1/D4/G2/
  RW1/RW2/G3/N2/P6), each PRODUCT_EXPERIMENT, none places an order.
- `scripts/run_night_launcher.py` + `backend/services/night_launcher.py` — the
  decide-then-launch pattern: receipt written BEFORE the launch attempt,
  `AEGIS_IIF1_LAUNCHER_ARMED=1` gates a real launch (attended arming),
  `--dry-run`/`--rehearse` never consult the arm flag, refusal codes are
  strings so a receipt reader never has to know an enum's numbering,
  `ACCEPTANCE_CONSECUTIVE_DATES = 3` before an attended fallback retires.
- `backend/services/llama_server.py` — PID-owned lifecycle, `OWNER_FILE` JSON
  (`AEGIS_REPO_ROOT`-honouring, not `__file__`-rooted — defect family #14),
  `status()`/`start()`/`stop()`, foreign-server rule ("already running when
  Aegis started; not ours to stop"), conservative unattended batch defaults
  (`LLAMA_BATCH=512`, `LLAMA_UBATCH=128`, the 2026-09-12 TDR lesson),
  `STOP_GRACE_S=3`, never kill by image name.
- `backend/services/book_cadence.py` + `paper_books.py` + `book_forecasts.py`
  — `PaperBook` = `Strategy` (fingerprinted) + cadence + twin + origin;
  `SUPPORTED_SIGNALS` tuple and `UnsupportedSignal` refusal (never a silent
  substitution); one `PredictionRecord` per decision plus one for the twin at
  `p=0.5`; `p = Φ(trailing IR vs twin)`, deterministic, never an LLM number.
- `backend/services/calibration.py` — Murphy decomposition, `MIN_PER_BIN=15`,
  `MIN_N_FOR_DECOMPOSITION=45`, PIT base-rate row, `report(rows, by=...)`.
- `backend/services/ledger_retrieval.py` — `visible_at(record, t)`: a rule or
  forecast is retrievable at `t` iff `resolution_date < t AND resolved_at is
  not None AND resolved_at <= t AND outcome is not None`.
- `backend/services/market_sensor.py` — `regime()` from 21-session SPY trend +
  VIX (frozen thresholds, printed every receipt); refuses by name without a
  FRED key.
- `backend/services/scenario_forecasts.py` — X3 contract (schema, prompt
  contract, `PredictionRecord` shape, base-rate `pricer`) built and tested,
  **not wired into the Morning**; needs L2's typed rows and E1's base-rate
  table, neither of which exists with real data yet.
- `backend/services/conformal.py` — ACI + non-exchangeable weighting,
  `coverage_table()` runs NAIVE/ACI/ACI_WEIGHTED together, never one alone.
- `backend/services/adwin.py` — ADWIN2 (Bifet & Gavalda 2007), vendored;
  `to_unit()` mandatory (an unscaled stream under 1.0 in magnitude cannot fire
  the detector — measured, not theoretical).
- `learner/event_head.py` + `scripts/night_e1_event_head.py` — the typed-event
  tabular head; `event_source: typed_l2 | keyword_proxy` on every receipt;
  four arms (EVENT/TFIDF/SHUFFLE/NOTEXT), two models (GBM/StockMixer_T1), two
  horizons (5/21); PIT `entry_date`, embargo in the SPLIT not the feature
  window. **Measured 2026-09-13, run 1**: neither head's typed-event arm beats
  SHUFFLE (LightGBM +0.0009 IC t 0.17; StockMixer +0.0029 IC t 0.46) — this is
  a verdict on the **keyword proxy**, because L2 has typed zero of these cells.
  StockMixer beats GBM on the identical table (architecture finding, not a
  text finding — SHUFFLE keeps the same gap).
- `scripts/night_l2_typed_events.py` — resumable, cursor-based
  (`typed_events/_cursor.json`), `label_source: true` sources only, writes
  `PENDING_MODEL` with the frozen input list and hashes when the reader is
  down, **never starts or stops `llama_server` itself**. Current state (per
  `docs/research_notes/2026-09-13/research_cloud_llm_readers.md`): 6,020 rows
  PENDING_MODEL, local wall-time projection 51-261h depending on model and
  prefix-cache availability.
- `scripts/night_e4_adwin_refit.py` — FIXED (monthly) vs ADWIN-gated refit,
  identical test dates, staleness stated on every date.
- `scripts/night_stopping_rules.py` — E5, already built: DSR + PBO
  (`backend/strategy/multipletesting.py`, vendored verbatim) over
  `G3_evaluations.jsonl`; `DEPRIORITIZED` verdict (never `deleted`, never a
  bare `STOP`) written to `G3_lineage_verdicts.jsonl`; excluded lineages are
  removed from `SearchState.update_elites()`.
- `backend/services/brain_queries.py` — the read-only, AST-enforced query
  surface (`panel_query`/`farm_query`/`receipt`/`leaderboard` per
  `spec_chunk8_memory_and_stopping.md` §3b) the Optimus MCP wraps.
- `scripts/monday_night.py` — the 30-minute loop pattern this spec generalises:
  two-clock printing (HKT machine, ET market), five named refusals (sleep,
  TDR/GPU line, no-broker AST test, STOP file, PID-written-down-first), one
  receipt per pass including "nothing to do."
- `docs/research_notes/2026-09-11/research_learning_loop.md` §§1-6 and
  `research_nn.md` — literature grounding, not repeated here; the memory
  design (ExpeL pairing, over-trust guard, Brier-scored rules) is
  `spec_chunk8_memory_and_stopping.md`'s M2, already specced and partly built
  (E5 landed; M2 §1.1-1.2 offline-stubbed is chunk 8 step 6, M2 real-ledger
  wiring is step 8 — check `docs/research_notes/2026-09-12/spec_chunk8_memory_and_stopping.md`
  build-order table before re-specifying any of it here).
- `docs/research_notes/2026-09-13/research_cloud_llm_readers.md` — DRAFT,
  sections 1-8 unfilled as of this reading. **This chunk designs the provider
  hook and does not depend on the draft landing** (per the task brief).
- `backend/services/pm_catalysts.py` — the catalyst calendar **already
  exists, v0**: Finnhub `/calendar/earnings` (free tier), `UNCOVERED` tuple
  (FDA/PDUFA, secondaries, 13D/G, lockups, index adds/deletes, investor days —
  named as gaps, not silently omitted), `coverage()` reports the gap as a
  first-class field. This chunk EXTENDS it (FRED release calendar), it does
  not rebuild the earnings half.
- `backend/services/news_registry.py` + `backend/data/news_sources.yaml` — 26
  registered sources (not 17), `pit_grade ∈ {native_stamp, first_seen_only,
  index_state}`, `index_state` may never be `label_source: true`.
  `greenhouse_lever_ashby_ats` is already registered — the hiring-signal
  source for Murat's "linkedin theory" theme (**LinkedIn itself is banned**,
  per project memory: no LinkedIn scraping, ATS boards are the legal
  substitute already in the registry).
- Roadmap **N-G** — `TRIAL-HIRING-PIVOT-1` is already pre-registered (share of
  open roles with AI/ML titles, 90-day change; named instances ADBE, ADSK,
  GPRO; control = same-sector no-change names; placebo = feature shifted +90
  days). This chunk wires the collector to run on a cadence; it does not
  re-design the trial.
- `backend/services/ownership.py` — 13F / institutional-holders ingestion
  already exists (`grep` hit across `actor_intelligence.py`,
  `book_signals.py`, `stock_analyzer.py`, `pit_collectors.py`,
  `chronology_audit.py` too) — Murat's "holders" theme has a data source
  today; it is a 45-day-lag source (13F filing lag), already flagged THIN in
  `docs/research_notes/2026-09-11/research_agency.md` §4 (copy-trading signal
  weak, consistent with the lag). Reused as a typed hypothesis stream (§7
  below), not re-collected.
- `backend/services/llm_analyzer.py` — `_DAILY_CAP` (line ~122, a **call
  count** cap, default 150/day), `_acquire_call_budget()`, billing breaker on
  401/402 (`_trip_breaker`), `llm_usage()` reports `calls_today`/`daily_cap`/
  `breaker_active`. **This is a count cap, not a dollar cap** — §5 below adds
  a dollar cap beside it, not instead of it.
- `scripts/llm_cost_audit.py` — reconciles PROVIDER-reported spend against
  TELEMETRY (`provider_balance_delta - telemetry_total = unaccounted`); never
  treats a missing balance endpoint as $0; never pools local and production
  ledgers. The dollar cap this chunk adds is a pre-call GUARD; this script
  stays the ground-truth RECONCILIATION — the two are complementary, not
  duplicates.
- `backend/routers/control.py:1996` — the existing `/coverage` endpoint the
  desktop board already reads (per the task brief: "`/coverage` already
  exists"). `lab_status.json` (§8) is a NEW, separate file the desktop polls
  alongside it — it does not replace `/coverage` and does not change its
  shape.

Status: SPEC. Nothing here has been built by this task.

---

## 0. What this chunk is, and what it explicitly is not

**It is** one supervisor process, `scripts/always_on_lab.py`, that runs
whenever the PC is on and drives the eight loops in §3 at their own declared
cadences, writing a receipt per tick per loop into the SAME per-date folder
every other job in this repo already writes into
(`backend/data/optimus/night_factory_<date>/`), plus one small persistent
status file (`lab_status.json`, §8) the desktop board polls.

**It is not** a rewrite of `daily_pass.py`, `night_factory.py`,
`monday_night.py`, `night_l2_typed_events.py`, or any of the E1-E5/L1-L4/M1-M5
modules. Every one of those already exists, is tested, and has its own
receipt discipline. The supervisor's entire job is **arbitration and
cadence**: decide when each existing driver gets to run, make sure two of
them never fight over the GPU or the model server, and write ONE status file
a human or the desktop UI can read without opening eight receipt folders.
A supervisor that re-implements `refuse_if_the_machine_may_sleep()` or the
STOP-file convention instead of importing them is a second copy of a rule
that WILL drift from the first (CLAUDE.md item 10's "read the AST, don't
grep" discipline, applied to *reusing* code rather than *guarding* it).

**It is not a green light to build the eight loops from scratch.** Five of
the eight (news pull, LLM typing, the NN nightly refit, the idle-GPU queue,
the catalyst-calendar earnings half) already exist as callable modules. This
chunk's NEW code is: the supervisor's own scheduling loop, the single-instance
lock, the FOMC/CPI/NFP calendar addition, the "decision vs reality" DAILY
cross-source aggregate receipt (as distinct from the per-mechanism grading
that already exists), the thematic-stream registration for hiring/pivot/
motivation/holders, the dollar cost cap, and `lab_status.json` +
`LEARNED_<date>.md`'s one supervisor-level line.

---

## 1. The supervisor — `scripts/always_on_lab.py`

### 1.1 Registration — ONLOGON, print-only, attended

Same pattern as `daily_pass.py`'s and `run_night_launcher.py`'s `--schtasks`:
this file NEVER calls `schtasks /Create` itself. `--schtasks` prints the
registration command and does nothing else; a human runs it once.

```
python -m scripts.always_on_lab --schtasks
```

prints:

```
schtasks /Create /TN "AegisAlwaysOnLab" /SC ONLOGON /RL LIMITED /TR "<venv python> -m scripts.always_on_lab"
```

`ONLOGON` (not `ONSTART`, not a fixed daily time) is the literal translation
of "live whenever pc is on" — it fires once per interactive logon and the
supervisor itself loops forever until it is told to stop (§1.5), rather than
firing once and exiting like `daily_pass` or `run_night_launcher` do. `/RL
LIMITED` — it must never run elevated; nothing it does needs admin rights and
an elevated unattended loop is a bigger blast radius for the same job.

### 1.2 Single instance, by PID, in the OWNER_FILE shape

Two supervisors racing over the same GPU and the same news cursor files is
the exact failure `llama_server.py`'s ownership design already solved for one
process; reuse the shape, do not invent a second one.

`backend/data/optimus/always_on_lab_lock.json`:
```json
{"pid": 41232, "started_utc": "...", "hostname": "...", "started_by": "always_on_lab"}
```

On start: read the lock file. If a PID is recorded and
`psutil.pid_exists(pid)` (or the Windows-native equivalent already used
elsewhere in this repo — check `quiet_subprocess.py` first, do not add a new
dependency) is true AND the process's command line still names
`always_on_lab`, refuse with `ALREADY_RUNNING: pid <n>` and exit 0 (a refusal
is a finding, not a crash — same convention as `daily_pass`'s exit-code
rule). If the PID is stale (process gone, or a different program now holds
that PID — PID reuse is real on a long-uptime Windows box), overwrite the
lock and proceed, logging the overwrite. Write the lock BEFORE the first
loop tick, same "receipt before the risky thing" discipline as
`run_night_launcher.py`.

### 1.3 The power-plan refusal — imported, not reimplemented

```python
from scripts.night_factory import refuse_if_the_machine_may_sleep
```

Called once at startup and again every `POWER_RECHECK_MINUTES = 60` inside
the main loop (a plan that was "never sleep" at 09:00 can be changed by
Windows Update or a battery-saver mode by 15:00; `night_factory.py` only
checks once because its longest single run is a few hours — this supervisor
runs for days, so it must re-check on a cadence, not just at boot). A refusal
on the periodic recheck does not kill the process; it sets `lab_status.json`'s
`power_plan: "REFUSED, may sleep since <ts>"` and pauses every loop that
touches the GPU or makes a network call until the next recheck clears — the
NN lab and the news pull are paused, but the supervisor keeps running so the
NEXT recheck can un-pause it without a human restarting a task.

### 1.4 Coexistence with the desktop app's llama-server

The supervisor NEVER calls `llama_server.start()` on its own initiative — the
desktop app (O1-O11) and a human are the only starters, exactly as
`night_l2_typed_events.py`'s own docstring already states ("the reader is not
started by this job"). The supervisor's LLM-touching loops (§3.2 typing,
§3.5's model-dependent controls) each call `llama_server.status()` first; if
`owned_by_us=False` and a foreign/desktop-owned server is up, they USE it
(read-only — no start/stop calls); if nothing is listening, they write
`PENDING_MODEL` exactly as `night_l2_typed_events.py` already does and move
to the next loop. This is not a new rule; it is the existing rule, and the
supervisor's only new obligation is to check `llama_server.status()` before
EVERY model-touching tick, not just once at startup, because the desktop app
can start or stop the server at any point during a multi-day supervisor run.

### 1.5 STOP file, same convention as `night_factory`/`monday_night`

`<night folder for today>/STOP` ends the current tick's loop iteration
cleanly and writes a final `lab_status.json` with `"running": false,
"stopped_by": "STOP_file"`. Checked once per loop iteration (§2's shortest
cadence, 5 minutes, bounds the worst-case shutdown latency). No other kill
path is documented or supported — CLAUDE.md rule 6 (kill by a written-down
PID, never by image name) applies to `always_on_lab.exe`/`python.exe`
identically to every other rule in this file.

### 1.6 Coexistence with `daily_pass` and `night_factory`/`monday_night`

These three ALREADY run on their own schedules (`daily_pass` at 06:30 via
`AegisDailyPass`; `night_factory`/the IIF-1 launcher in the evening;
`monday_night` on Monday nights, attended). The supervisor does not replace
any of them and does not duplicate their receipts. Its arbitration rule
(detailed in §4) is: **when one of these three is already running (detected
by their own PID/lock conventions — `night_factory`'s STOP-file directory
existing with today's date and no completion marker, `daily_pass`'s receipt
absent for today), the supervisor's overlapping loops (news pull, idle-GPU
queue) SKIP that tick and say so** rather than launching a second concurrent
copy of the same underlying job. The supervisor's news-pull and typing loops
(§3.1, §3.2) are the ones that run independently of those three, because
they are the genuinely NEW "whenever the PC is on" behavior Murat asked for;
the NN nightly refit and the idle-GPU queue (§3.5, §3.6) are scheduling
WRAPPERS around jobs that already have their own home in `night_factory`'s
queue and must not become a second, competing scheduler for the same jobs.

---

## 2. The cadence table

| # | loop | period | touches GPU/LLM? | touches network? | new code? |
|---|---|---|---|---|---|
| 1 | live news pull | every 15 min | no | yes | thin wrapper only |
| 2 | LLM typing of new rows | every 15 min (after 1) | yes (local, or cloud via hook) | maybe (cloud) | thin wrapper + hook |
| 3 | decision-vs-reality grading | every 60 min | no | no (reads local ledgers) | new aggregate receipt |
| 4 | catalyst calendar refresh | every 6 h (Finnhub cache TTL already 6h) | no | yes | FRED addition only |
| 5 | NN nightly refit orchestration | once/night, when idle (§3.5) | yes | no | orchestration only |
| 6 | idle-GPU night queue | triggered by idle-for-`IDLE_MINUTES=20` | yes | maybe | thin dispatcher |
| 7 | thematic hypothesis streams | daily (hiring/pivot), weekly (motivation/holders placeholder check) | maybe | yes | new registration, mostly reuse |
| 8 | receipts / `lab_status.json` write | every loop tick (always) | no | no | new, small |

The supervisor's own top-level loop wakes every **5 minutes** (the shortest
cadence any sub-loop needs, per invariant 15's "silence is never success" —
a 5-minute heartbeat means `lab_status.json`'s `last_tick_utc` is never more
than 5 minutes stale, so a hung supervisor is detectable from its own status
file within 5 minutes rather than a human noticing the news corpus stopped
growing three days later) and checks, for each of the eight loops, whether
its own period has elapsed since its own last successful tick (stored in
`lab_status.json`, not recomputed from wall-clock drift — a loop due every 15
minutes that the supervisor was asleep for from 02:00-08:00 due to the
machine actually being off runs ONCE at the next wake-up, not six times to
"catch up," because catching up burns the API budget on stale data for no
benefit — the same "unset means today, not five days of backlog" lesson
`night_factory.py`'s own header already states about `NIGHT_RUN_DATE`).

---

## 3. The eight loops

### 3.1 Live news, every 15 minutes, all registered sources

Wraps `scripts/news_pull.py` per source, in the SAME per-source cursor and
per-day-JSONL shape N-A already specifies
(`backend/data/optimus/news_corpus/<source>/<YYYY-MM-DD>.jsonl`, `first_seen_utc`
on every row). The supervisor does not reimplement a fetcher; it calls
`news_pull.pull_all(sources=news_registry.label_sources())` (or the nearest
existing entry point — Opus confirms the actual callable signature when
building, since this spec was written read-only) on the 15-minute cadence and
appends the run's per-source counts to the tick's row in `lab_status.json`.
A source that 404s or times out is recorded by name (N-A's own rule: "a
source that returns 0 twice is red, not silent") — two consecutive empty
pulls from the SAME source inside one calendar day sets that source's
`status: "red"` in `lab_status.json`'s coverage block, read by the existing
`/coverage` endpoint's own aggregation or by a new small merge if `/coverage`
does not already read this file (Opus checks `backend/routers/control.py:1996`
before deciding).

**Rate limits**: `news_sources.yaml`'s per-source rate limit field already
exists (N-B); the 15-minute cadence must not itself violate any source's
declared limit — the wrapper reads the registry's rate-limit field and skips
a source whose limit would be breached by a 15-minute cadence, marking it
`skipped: "rate_limit_would_be_breached_at_this_cadence"` rather than
silently pulling less often than declared (a cadence table with an unstated
exception is the same failure `night_factory.py`'s own header warns about
for `NIGHT_RUN_DATE`).

### 3.2 LLM typing of new rows, local by default, cloud hook designed not built

Wraps `scripts/night_l2_typed_events.py` (already cursor-resumable) on the
15-minute cadence, AFTER §3.1's pull completes for that tick (typing needs
rows to type). Calls the existing entry point with the same `--max-rows`-style
bound already in the module so one tick cannot try to type the entire
6,020-row backlog in 15 minutes and block the next news pull.

**The cloud-provider hook, designed here, not built**: `night_l2_typed_events.py`
currently probes `llama_server.status()` only. This chunk adds ONE new
parameter to the typing call, `reader: Literal["local", "cloud"] = "local"`,
and a `CloudReader` protocol (a single method, `type_batch(rows) ->
list[TypedRow]`, matching the local reader's own return shape exactly) that
`night_l2_typed_events.py` accepts but that has NO concrete implementation
in this chunk — `research_cloud_llm_readers.md`'s sections 1-6 (NVIDIA NIM,
Featherless, DeepSeek pricing, the $5/6,020-rows plan, per-model Lookahead
Propensity, the minimal `llm_analyzer.py` change) are unfilled as of this
spec's writing, and building against an unfilled research draft is how a
spec drifts from the research that was supposed to ground it. The supervisor
reads an env var, `AEGIS_L2_READER` (`local` default), and if it is set to
`cloud` while no `CloudReader` is registered, it REFUSES that tick's typing
loop by name (`CLOUD_READER_NOT_IMPLEMENTED`) rather than silently falling
back to local and calling it a cloud run — same "a refusal is a finding"
discipline as everywhere else in this file. **This is the single largest
piece of chunk 15 by researched-but-unbuilt surface area**: once
`research_cloud_llm_readers.md` names an actual provider, price and the
`llm_analyzer.py` abstraction change, chunk 15 implements `CloudReader` and
the hook here needs no further change.

**What it must never do**: type a row twice. The cursor file is the ONLY
resume mechanism (module docstring: "there is no other mode... `--resume` is
accepted... and is a no-op here"); the supervisor must not add a second
resume mechanism of its own that could race the cursor file across ticks —
each tick's call is synchronous within the supervisor's own loop (no two
typing calls ever run concurrently), enforced by the single-instance lock
(§1.2) plus the fact that the supervisor itself is single-threaded for
LLM-touching loops.

### 3.3 Decision vs reality — the daily cross-source receipt

Every `PredictionRecord` the system writes — books (B5), scenario forecasts
(X3, once wired), the morning read, and (§3.7) the thematic streams — already
gets graded by its OWN mechanism's existing grader
(`pi_ledger_resolve`, `calibration.report()`, `book_forecasts.trailing_ir`).
**This loop does not re-grade anything.** It is a NEW aggregate: once every
60 minutes, read every `PredictionRecord` resolved in the last 24 hours
across ALL `mechanism_id`s (via `ledger_retrieval`'s own hindsight-safe
predicate, so a record graded early is not admitted early — same M3 rule,
reused not reinvented) and write one JSON block per source/mechanism to
`backend/data/optimus/night_factory_<date>/decision_vs_reality_<date>.json`:

```json
{"utc": "...", "window": "trailing_24h",
 "by_mechanism": [
   {"mechanism_id": "paper_book_v1", "n_resolved": 4, "brier": 0.21,
    "brier_vs_base_rate": -0.03, "beats_base_rate": true},
   {"mechanism_id": "x3_scenario_forecast_v1", "n_resolved": 0,
    "status": "not_wired_yet"},
   {"mechanism_id": "hiring_pivot_ai_v1", "n_resolved": 1, "brier": null,
    "status": "insufficient_n"}
 ],
 "worst_miss": {"mechanism_id": "...", "record_id": "...",
                "thesis": "...", "counter_thesis": "...",
                "predicted": 0.72, "outcome": 0, "brier": 0.5184}}
```

This is the board's "what we said vs what happened" object (task item 3) and
IS `docs/ROADMAP...md`'s Lane B6 "Regret page" generalised across every
mechanism instead of just books — B6 is reused as the PER-BOOK view; this
receipt is the CROSS-mechanism roll-up B6 does not attempt. `worst_miss` is
computed the same way B6's spec already states ("the worst miss with its
thesis and counter-thesis side by side"), just not scoped to one book.

A day with zero resolutions writes the receipt anyway with every mechanism's
`n_resolved: 0` — invariant 15, restated for the tenth time in this repo
because it is the rule that costs a session the most when skipped.

### 3.4 Upcoming dates and possibilities — extend, don't rebuild

`pm_catalysts.py` already covers earnings (Finnhub, free tier, cached 6h,
`HORIZON_DAYS=120`) and already NAMES what it cannot cover
(`UNCOVERED` tuple: PDUFA, secondaries, 13D/G, lockups, index adds/deletes,
investor days — no free source found for any of them as of BUILD-1's probe;
this chunk does not re-probe those unless a new free source is found, which
is chunk-15-or-later work, not this chunk's).

**New in this chunk**: a FRED release calendar for FOMC/CPI/NFP.
`market_sensor.py` already reads FRED (`VIXCLS`) with the same-key,
same-refusal-by-name pattern this new fetch reuses verbatim — a second FRED
client with different error handling would be the same "guard applied only
to the dormant Claude branch" mistake CLAUDE.md warns about, transplanted
from providers to fetchers. FRED's `fred/releases/dates` endpoint (release
ids: CPI = 10, Employment Situation/NFP = 50, FOMC statements are not a FRED
series but ARE published on federalreserve.gov's own calendar page, which is
scraped HTML, not an API — mark FOMC dates `source: "manual_calendar_scrape,
untested"` and cap confidence accordingly, or, cheaper for this chunk, seed
FOMC dates from the Fed's own published 2025-2026 schedule as a static table
refreshed manually once a year, exactly the honest shortcut `pm_catalysts.py`
already takes for the `catalysts:` block a human writes for FDA/PDUFA dates).

`calendar_extended(tickers) -> dict` adds a `macro` block beside
`pm_catalysts.calendar()`'s existing per-ticker block:
```json
{"macro": [{"kind": "FOMC", "date": "2026-10-29", "source": "fed_schedule_static"},
           {"kind": "CPI", "date": "2026-10-14", "source": "fred_release_dates"}]}
```

**Scenario probabilities attached, and graded afterwards**: the task asks
for "the engine's scenario probabilities attached and graded afterwards."
`scenario_forecasts.py` (X3) is the contract for this and is **not wired**
per its own docstring (needs L2's typed rows and E1's base-rate table, and
E1's base-rate table needs real typed data, which needs L2, which is
PENDING_MODEL). This chunk therefore does the honest, non-fabricating thing:
the catalyst calendar entries carry an `engine_probability: null,
"status": "AWAITING_L2"` field rather than a fake number, and a
`PredictionRecord` per catalyst is written ONLY once X3 is wired (chunk 15,
gated on L2 having real typed rows — the same gate `spec_chunk8`'s own build
order already applies to M2's real-ledger step). **What this chunk DOES
ship**: the calendar itself, refreshed on cadence, on the board, with every
entry's provenance and every gap named — which is already most of item 4's
value even before the probabilities exist.

### 3.5 The NN learning lab — nightly refit, orchestrated not rebuilt

**What "continuously learn" means, said exactly once so it cannot drift**:
every night the queue is idle (§3.6), the supervisor triggers, IN ORDER:

1. `night_e1_event_head.py` — refit the typed-event tabular head on the
   CURRENT typed-events table (grows as L2 produces real rows; today it is
   still the keyword proxy per the measured 2026-09-13 result above, and the
   receipt's `event_source` field says so every night, unprompted).
2. `night_e4_adwin_refit.py` — the ADWIN-vs-fixed refit comparison on the
   same head.
3. `night_stopping_rules.py` — DSR/PBO over the accumulated
   `G3_evaluations.jsonl` (if G1/G3 ran that night per `night_factory`'s own
   queue — this call is a no-op with a stated reason if they did not).

**The new receipt field this chunk adds**: `beat_last_night: bool | null` —
compare tonight's refit head's IC on a FIXED held-out month (the most recent
FULLY-CLOSED calendar month, never a moving window, so "beat last night" is
answering the same question every night) against last night's SAME head
evaluated on the SAME held-out month (not re-evaluating last night's head on
a NEW month, which would confound "did the head improve" with "did the month
get easier"). Stored per head in `night_factory_<date>/NN_lab_<date>.json`:
```json
{"head": "EVENT_GBM_h5", "held_out_month": "2026-08",
 "ic_tonight": 0.012, "ic_last_night": 0.009,
 "beat_last_night": true, "n_nights_compared": 14}
```
`n_nights_compared < 2` -> `beat_last_night: null` (nothing to compare
against yet, stated, not defaulted to false or true).

**What "continuously learn" must NEVER do, stated because a spec that only
says what to build and not what to refuse is incomplete**:

- **No training on future information.** The held-out month is FIXED and
  CLOSED before the refit that grades against it starts; a refit is never
  allowed to see rows dated inside its own held-out month, enforced by the
  SAME embargo/PIT machinery `learner/event_head.py` already implements
  (`test_no_feature_reaches_past_its_own_date`) — this loop calls that
  machinery, it does not get a parallel, easier-to-violate copy of it.
- **No target leakage.** Same ALLOWED_INPUT_FIELDS-style allowlist discipline
  as M2's prompt contract (`spec_chunk8` §1.2) — a nightly refit that
  accidentally trains on a column derived from the label is not "learning
  faster," it is the oldest bug in this codebase's family wearing a new name.
- **Frozen policy versions once a book trades them.** A nightly refit changes
  the RESEARCH head. It never touches a `PaperBook`'s frozen `Strategy`
  fingerprint — `paper_books.py`'s own docstring already states a mutation is
  a NEW book, never an edit to an existing one's contract. The nightly lab
  produces candidates for a FUTURE book; it does not reach backward and
  change a book already accruing forward evidence. This is not new
  machinery — it is the existing PRODUCT_EXPERIMENT/CAPITAL_CANDIDATE
  boundary (CLAUDE.md "THREE LICENCES") restated for this specific loop so
  an Opus builder cannot read "continuously learn" as licence to make a
  live book's construction a moving target.
- **DEPRIORITIZED, never deleted, never re-promoted on the same regime.**
  E5's own rule, unchanged, reused verbatim by this loop's third step.

### 3.6 The idle-GPU night queue

`IDLE_MINUTES = 20` (configurable, `backend/config.py`, per CLAUDE.md's "put
parameters in config, never hardcode" rule): if neither §3.2 (typing) nor
§3.5 (NN lab) has issued a model-touching call in the last 20 minutes AND
`llama_server.status()` shows either nothing listening or a server the
supervisor itself owns and is idle, the supervisor dispatches the NEXT
not-yet-run-tonight job from a declared priority list, reusing
`night_factory.py`'s own `QUEUE` shape and job registry
(`night_factory_jobs.JOBS`) rather than inventing a second job list:

```
["L2_typed_events", "R2_panel_B", "anonymization_gap_probe",
 "recall_probe", "L4_qwen3_measure", "M2_distillation_offline"]
```

(This is the task's own list — "R2 panel B, L2 backlog, E1 on typed rows,
the anonymisation gap, the recall probe, L4, M2" — reordered so L2's backlog
runs FIRST, since every other item on the list either consumes L2's output
(E1, M2) or is orthogonal to it (R2, L4), and the backlog is the single
biggest measured gap in the system today, 6,020 rows PENDING_MODEL.) Each
dispatched job runs with the SAME time-boxing convention `night_factory.py`
already uses (`TIMEBOXED` set, a declared minute budget) so the queue yields
back to §3.1/§3.2/§3.3 on their own cadences rather than the idle-GPU queue
starving the always-on loops that must run even when the GPU is busy.

**Arbitration with `night_factory.py`'s own evening run**: if a `night_factory`
run is ALREADY IN PROGRESS for today's date (its own STOP-file-directory
exists and its own completion marker does not), the supervisor's idle-GPU
queue REFUSES for that date (`NIGHT_FACTORY_ALREADY_RUNNING`) rather than
double-dispatching the same jobs — the idle-GPU queue exists to fill the
GAPS `night_factory`'s scheduled evening run does not cover (daytime idle
periods, a night `night_factory` was never launched), not to compete with it.

### 3.7 Murat's themes as typed hypothesis streams

Each theme becomes ONE `mechanism_id`, its own `PredictionRecord` stream,
graded like every other forecast (M1's schema, reused unchanged) — **never a
new ledger, never a new grading function**. Per theme, stated honestly per
the task's own instruction ("say which have a data source today and which
are placeholders"):

| theme | mechanism_id | data source TODAY | status |
|---|---|---|---|
| hiring / "linkedin theory" | `hiring_pivot_ai_v1` | `greenhouse_lever_ashby_ats` (already registered, N-B); N-G's own pre-registered trial (ADBE/ADSK/GPRO, control = sector no-change, placebo = +90d shift) | **LIVE** — this chunk wires N-G's collector to the daily cadence (§2 row 7) and writes one `PredictionRecord` per name per week, `predicts.observable = "ai_role_share_change_predicts_forward_return"` |
| pivot-to-AI (the business-strategy version, beyond hiring) | `pivot_to_ai_narrative_v1` | none beyond N-G's hiring proxy and L2's typed events (once real) tagging `strategic_pivot`-class rows if the vocabulary has one (check `event_vocabulary.py`'s 39 ids — this spec did not confirm one exists; Opus checks before wiring) | **PLACEHOLDER** — registers the `mechanism_id` and writes `CANDIDATE` rows with `n_fired=0` so the stream EXISTS in the ledger and can start accruing the day L2 produces a real `strategic_pivot`-tagged row, rather than being invented from nothing later with no history |
| management motivation | `management_motivation_v1` | none identified — would need an LLM read of earnings-call transcripts or shareholder letters, which this repo does not currently ingest as a labelled source | **PLACEHOLDER**, explicitly named as needing a new collector before chunk 15 can promote it past registration |
| holders | `holders_13f_v1` | `backend/services/ownership.py` (13F, already ingested; ALREADY FLAGGED THIN in `research_agency.md` §4 — 45-day filing lag, low best-idea overlap across managers) | **LIVE but WEAK BY DESIGN** — wired on a weekly cadence (13F is quarterly-filed, a weekly check is for freshness not for new information every week), and every `PredictionRecord` this stream writes carries a `known_weak_prior: "13F 45-day lag, THIN per 2026-09-11 research"` note so a reader of `LEARNED_<date>.md` is not surprised when this stream's Brier looks like a coin flip |
| "the business, the future, anything" | not a mechanism — this is the general LLM-read surface X3 (scenario forecasts) and the Morning digest already cover once wired | **NOT a new stream** — building a catch-all `mechanism_id` with no falsifiable `applies_when` is exactly the shape M2's schema (`spec_chunk8` §1.2) refuses (`applies_when` is a TYPED condition list, `minItems: 1`); Murat's "anything" is served by X3 once it is wired (chunk 15, gated on L2 real data), not by a new untyped bucket now |

Each LIVE/PLACEHOLDER stream's origin tag (`origin: "murat_theme"`,
`origin_text: "linkedin theory / business pivot to ai / motivation / holders
/ the business / the future / anything"` — Murat's own sentence, verbatim,
per `paper_books.py`'s own convention for `origin_text`) means
§3.3's decision-vs-reality receipt grades these SEPARATELY from books, from
X3, and from each other — the task's own requirement ("decision vs reality...
graded... with an origin tag so decision-vs-reality grades them separately").

### 3.8 The receipts and the board

`lab_status.json` (single file, overwritten atomically every tick — same
`os.replace` atomic-write pattern `night_launcher.py`/`llama_server.py`
already use for their own state files, never a bare `write_text` that a crash
mid-write can leave truncated):

```json
{"utc": "...", "running": true, "pid": 41232, "started_utc": "...",
 "power_plan": "AC standby timeout 0 (never)",
 "loops": {
   "news_pull": {"last_tick_utc": "...", "status": "ok", "sources_red": []},
   "l2_typing": {"last_tick_utc": "...", "status": "ok", "rows_typed_this_tick": 40,
                 "backlog_remaining": 5980, "reader": "local"},
   "decision_vs_reality": {"last_tick_utc": "...", "status": "ok"},
   "catalyst_calendar": {"last_tick_utc": "...", "status": "ok"},
   "nn_lab": {"last_run_utc": null, "status": "awaiting_idle_window"},
   "idle_gpu_queue": {"last_dispatch_utc": null, "status": "gpu_busy"},
   "thematic_streams": {"hiring_pivot_ai_v1": "live",
                         "pivot_to_ai_narrative_v1": "placeholder",
                         "management_motivation_v1": "placeholder",
                         "holders_13f_v1": "live_weak"}
 },
 "llama_server": {"owned_by_us": false, "foreign_owner_pid": 9981, "up": true},
 "spend_today_usd": 0.00, "spend_cap_usd": 5.00,
 "single_instance_lock": {"pid": 41232, "started_utc": "..."}}
```

The desktop's existing `/coverage` route (`control.py:1996`) is unchanged by
this chunk; if it needs `lab_status.json`'s content surfaced on the board, a
follow-up small route reads this file the same read-only way `brain_queries.py`
reads other receipts — that route is chunk-15-sized only if it needs new UI,
and chunk-14-sized (trivial) if it is a bare passthrough; Opus decides at
build time based on what O4 (the developer board, already speced in the
roadmap) actually needs.

`LEARNED_<date>.md`'s supervisor-contributed line (the file itself is M2's,
per `spec_chunk8` §1.8 — this chunk adds ONE line to the DAILY equivalent for
Optimus, not the monthly `LEARNED_<YYYY-MM>.md` M2 owns):

```
backend/data/optimus/brain/LEARNED_<date>.md
> Always-on lab, <date>: news pulled from N/26 sources (M red); L2 typed
> <k> rows (backlog <n>, reader=local); NN lab ran <j> heads, <b> beat last
> night on 2026-08 held-out; idle-GPU queue ran [<jobs>]; thematic streams:
> hiring LIVE (<n> firings), holders LIVE_WEAK (<n> firings), pivot/motivation
> PLACEHOLDER (0 firings); spend $<x.xx>/$<cap> cap.
```

One line, every day, whether or not anything interesting happened — the
"a session that ships thirty engineering changes and moves none of them says
RESULT IMPROVEMENT: NONE" discipline (CLAUDE.md), applied to a daily cadence
instead of a session.

---

## 4. Arbitration rules, stated once, in priority order

1. **The desktop app and a human own `llama_server` start/stop.** The
   supervisor only ever calls `status()`. If the desktop app stops the server
   mid-tick, the current model-touching call fails, is recorded as
   `error: "server_stopped_mid_call"`, and the NEXT tick re-probes rather
   than retrying immediately (no retry loop against a server a human just
   chose to stop).
2. **`daily_pass` (06:30) and `night_factory`/the IIF-1 launcher (evening) own
   their own scheduled windows.** The supervisor's overlapping capabilities
   (news pull, idle-GPU dispatch) SKIP when one of those is actively running
   for today's date, detected from their own receipt/lock conventions, never
   from a guessed wall-clock window (a `daily_pass` running late is still
   running, regardless of what time it is).
3. **GPU/model access is FIFO across the supervisor's own loops, never
   concurrent.** §3.2 (typing) and §3.5 (NN lab, when it uses the model for
   anything beyond CPU-only GBM refits) and §3.6 (idle queue's GPU job, C1
   equivalent) never run at the same wall-clock moment; the supervisor is
   single-threaded for anything that touches `llama_server`, enforced by a
   simple in-process lock, not a second PID file (this is WITHIN one process,
   `threading.Lock()`, the same pattern `era_replay_v2.py`'s `SPEND.lock`
   already uses elsewhere in this repo for a different resource).
4. **`monday_night.py`'s attended 30-minute device protocol, when Murat runs
   it, takes priority over the supervisor's idle-GPU queue** on the same
   machine during that window — `monday_night` is attended and time-boxed by
   Murat's own choice to leave the PC on; the supervisor detects it the same
   way it detects `night_factory` (a running process / receipt convention)
   and yields.
5. **A refusal from any imported guard (`refuse_if_the_machine_may_sleep`,
   `llama_server`'s foreign-owner rule, `news_registry`'s unknown-source
   refusal) is never retried in the same tick.** It is recorded, and the NEXT
   tick re-evaluates from scratch — no backoff-and-retry ladder that could
   turn one refused tick into a burst of retries at tick end.

---

## 5. Failure modes, and the mitigation already required or newly added

| failure mode | mitigation | source |
|---|---|---|
| the power plan allows sleep | `refuse_if_the_machine_may_sleep()`, imported, re-checked every 60 min (§1.3) | existing, reused |
| GPU TDR under sustained unattended load | `LLAMA_BATCH=512`/`LLAMA_UBATCH=128` defaults already set in `llama_server.py`; the supervisor changes NEITHER — it inherits them by calling the same module | existing, reused |
| a stuck loop (one of the eight hangs) | each loop call runs with a hard wall-clock timeout (`subprocess.run(..., timeout=...)` where the loop shells out, or a watchdog thread where it does not); a timeout is recorded as `status: "timeout_after_<n>s"`, the loop is skipped for that tick, and `lab_status.json`'s `last_tick_utc` for THAT loop stops advancing — which is exactly the detectable signal a human or a future guard needs, because the supervisor's OWN top-level 5-minute heartbeat keeps advancing (it is not itself blocked by one stuck sub-loop; each loop call is issued with a timeout FROM the top-level loop, never awaited unboundedly) | new |
| a runaway cloud bill (once §3.2's `CloudReader` hook is ever filled in, chunk 15+) | a **dollar** cap, new, beside `llm_analyzer.py`'s existing CALL-COUNT cap (`_DAILY_CAP=150`, which bounds calls, not spend, and says nothing about a provider charging more per call than assumed): `AEGIS_LAB_DAILY_SPEND_CAP_USD` (config default `$5.00`), tracked in `lab_status.json`'s `spend_today_usd`, checked BEFORE every cloud call the lab itself issues (not retroactively via `llm_cost_audit.py`, which stays the ground-truth RECONCILIATION run separately — this is a pre-call GUARD, cheaper and less accurate, the same relationship the call-count cap already has to the billing breaker). Exceeding the cap REFUSES further cloud calls for the rest of the UTC day (same day-boundary convention as `_DAILY_CAP`) and is a loud line in `lab_status.json`, never a silent throttle. Local-model calls are UNMETERED by this cap (they cost compute, not dollars) — the cap exists for the day this repo has a live cloud reader, and is inert (`spend_today_usd` stays 0.00) until then, which is the honest state to ship given `research_cloud_llm_readers.md` is still a draft | new |
| PID reuse making the single-instance lock stale-positive | the lock check also compares the recorded process's command line, not just PID liveness (§1.2) | new |
| two supervisor instances from two Windows user sessions | `ONLOGON` fires per logon; if Murat has two concurrent sessions the SECOND supervisor's lock check (§1.2) refuses with `ALREADY_RUNNING` and exits — this is why the lock file lives in the shared `backend/data/optimus/` path, not a per-user temp directory | new |

---

## 6. Tests — all mocked, `tmp_path`, dates from `today`, no network

Following `backend/tests/test_daily_pass.py`'s own shape exactly (the
`out(tmp_path, monkeypatch)` fixture pattern, one test per declared
behavior, never a giant end-to-end test that hides which behavior broke):

1. `test_every_declared_loop_ticks_on_its_own_cadence` — a fake clock
   (monkeypatched `time.time`/`datetime.now`) advances past each loop's
   period one at a time; assert each loop's `last_tick_utc` in
   `lab_status.json` advances exactly when its period elapses, not before,
   not on every 5-minute heartbeat.
2. `test_a_second_instance_refuses` — write a lock file with a PID that
   `psutil.pid_exists` (mocked) reports alive AND a matching command line;
   assert the second `always_on_lab` invocation exits 0 with
   `ALREADY_RUNNING` and writes no new lock.
3. `test_a_stale_lock_is_overwritten` — same, but the mocked PID is not
   alive; assert the new instance overwrites the lock and proceeds.
4. `test_sleeping_power_plan_pauses_gpu_touching_loops_not_all_of_them` —
   mock `refuse_if_the_machine_may_sleep` to return a refusal string; assert
   `news_pull` (§3.1) still ticks (no GPU, network only — task does not ask
   for the news pull to stop just because sleep is allowed, only that the
   supervisor itself refuses to START a GPU job into a machine that might
   suspend mid-job) while `nn_lab`/`l2_typing`/`idle_gpu_queue` are paused
   and say so.
5. `test_foreign_llama_server_is_used_not_started` — mock
   `llama_server.status()` to report a foreign owner up; assert the typing
   loop calls the reader against that server and issues NO `start()` call
   (assert the mock's `start` was never called — the AST-test discipline
   applied at the call-site level, not just the file level).
6. `test_no_server_means_pending_model_not_a_crash` — mock `status()` to
   report nothing listening; assert the tick completes with
   `status: "PENDING_MODEL"` and the loop returns to the top-level scheduler
   rather than raising.
7. `test_decision_vs_reality_admits_only_hindsight_safe_rows` — synthetic
   `PredictionRecord`s, one resolved BEFORE the aggregate's `as_of` cutoff and
   one resolved AFTER; assert the receipt's `n_resolved` counts only the
   first, reusing `ledger_retrieval.visible_at` directly (not a re-implemented
   predicate) — assert via a spy that the retriever function was actually
   called, so a future edit that inlines a similar-looking check would fail
   this test rather than silently drifting from M3.
8. `test_worst_miss_ties_to_thesis_and_counter_thesis` — a synthetic ledger
   with one badly-missed forecast; assert the receipt's `worst_miss` block
   carries that record's `thesis`/`counter_thesis` fields verbatim.
9. `test_dollar_cap_refuses_before_the_call_not_after` — a mocked
   `CloudReader.type_batch` that would report a cost; set
   `spend_today_usd` to just under the cap via a pre-seeded `lab_status.json`;
   assert the NEXT call is refused BEFORE the mock is invoked (assert the
   mock's call count is 0, not 1-then-refunded).
10. `test_cloud_reader_env_var_without_implementation_refuses_by_name` —
    `AEGIS_L2_READER=cloud` with no `CloudReader` registered; assert
    `CLOUD_READER_NOT_IMPLEMENTED`, never a silent fallback to local (this is
    the test that keeps §3.2's hook honest before chunk 15 fills it in).
11. `test_idle_gpu_queue_yields_to_a_running_night_factory` — a fake
    `night_factory` lock/receipt-in-progress for today's date; assert the
    idle queue's dispatch is `NIGHT_FACTORY_ALREADY_RUNNING`, not a second
    concurrent `L2_typed_events` invocation.
12. `test_thematic_stream_registration_is_idempotent` — calling the
    registration twice (e.g. across two supervisor restarts) produces ONE
    `mechanism_id` row per theme in the ledger, not a duplicate — the
    fingerprint-identity discipline `paper_books.py` already uses for
    `Strategy` objects, applied to `mechanism_id` registration.
13. `test_a_tick_with_nothing_new_writes_nothing_to_do_not_silence` —
    invariant 15, restated as a test for every loop: an empty news pull, a
    typing tick with an empty backlog, a decision-vs-reality tick with zero
    resolutions all write their loop's block with an explicit `nothing_to_do`
    or `n=0`, never an omitted key.
14. All dates constructed via `date.today()` / a fixture that freezes
    `today` for the test's own duration — never a literal `"2026-09-13"` in
    a fixture, per CLAUDE.md rule 5 ("test fixtures never encode a calendar
    moment").

---

## 7. Acceptance receipt

`always_on_lab` is ACCEPTED (same word `night_launcher.py`'s own acceptance
concept uses) when a single receipt,
`backend/data/optimus/night_factory_<date>/always_on_lab_acceptance_<date>.json`,
shows, over three CONSECUTIVE calendar dates the machine was on for at least
6 continuous hours (not three consecutive TASK RUNS — `ONLOGON` could fire
and die repeatedly in a bad state and still produce three "runs"; the bar is
three dates with real elapsed coverage):

- `lab_status.json`'s `last_tick_utc` for `news_pull` never gapped by more
  than 2× its declared period on any of the three dates;
- at least one full `decision_vs_reality` receipt per date, even if
  `n_resolved: 0` everywhere;
- the catalyst calendar refreshed at least once per date with the `macro`
  block populated (or `status: "FRED_KEY_ABSENT"` named, per
  `market_sensor.py`'s own refusal convention — CANNOT DETERMINE is an
  acceptable acceptance state, a silent gap is not);
- zero `ALREADY_RUNNING` collisions with `night_factory`/`daily_pass`
  recorded as anything other than a clean skip (a collision that produced a
  double-write would fail acceptance outright);
- the dollar spend cap never breached (trivially true while
  `spend_today_usd` stays 0.00 pre-chunk-15, and this line is the reason to
  KEEP checking it once a cloud reader exists rather than assuming the guard
  still works);
- `LEARNED_<date>.md`'s supervisor line present for all three dates.

Until this receipt exists, the honest status is "built, unaccepted" — the
same distinction `night_launcher.py`'s own `acceptance_report()` already
draws between a green process and three dated receipts.

---

## 8. Build order for Opus (cheapest, most-reused-code first)

| step | item | why this order | receipt |
|---|---|---|---|
| 1 | supervisor skeleton: lock (§1.2), power check (§1.3), STOP file (§1.5), 5-minute heartbeat writing `lab_status.json` with all eight loops stubbed `"status": "not_yet_implemented"` | proves the process model (single instance, refuses cleanly, never crashes on missing pieces) before any loop has real logic | `lab_status.json` itself |
| 2 | loop 1 (news pull wrapper) + loop 8 (status writes, already scaffolded in step 1) | pure wiring to an existing, tested module; zero new mechanism | `lab_status.json`'s `news_pull` block populated for real |
| 3 | loop 3 (decision-vs-reality aggregate) | needs only `ledger_retrieval`/`calibration`, both existing and read-only; can be built and tested against SYNTHETIC ledger rows before real books exist | `decision_vs_reality_<date>.json` |
| 4 | loop 2 (L2 typing wrapper, local reader only) + the `CloudReader` hook stub (§3.2) that only ever refuses `CLOUD_READER_NOT_IMPLEMENTED` | wires the single biggest measured backlog (6,020 rows) into the always-on cadence; the cloud hook is a stub, cheap to add now while the local path is fresh in context | backlog count decreasing in `lab_status.json` across ticks |
| 5 | loop 4 (catalyst calendar: FRED addition atop existing `pm_catalysts.py`) | small, isolated, no dependency on steps 1-4 beyond the shared receipt folder | `macro` block populated |
| 6 | §5's dollar cap machinery (inert until a cloud reader exists, but the GUARD must exist before step 4's hook is ever filled in, per §1.6-style "the gate exists before the first rule is written" discipline already used for M3/M2 in this programme) | cheap, and belongs beside the cloud hook it protects, added in the SAME chunk that adds the hook so the two are never separated in git history | `spend_today_usd`/`spend_cap_usd` in `lab_status.json` |
| 7 | loop 7 (thematic streams: hiring LIVE via N-G, holders LIVE_WEAK via `ownership.py`, pivot/motivation PLACEHOLDER registration only) | needs M1's ledger schema (already extended per `spec_chunk8`) and nothing else new; the two LIVE streams reuse existing collectors entirely | `mechanism_id` rows appear in the ledger, `LEARNED_<date>.md`'s line names all four |
| 8 | loop 5 (NN lab orchestration: E1/E4/E5 nightly sequence + `beat_last_night` field) | depends on steps 1-3's receipt plumbing; the underlying E1/E4/E5 modules are untouched, this step only sequences and adds one comparison field | `NN_lab_<date>.json` |
| 9 | loop 6 (idle-GPU queue dispatcher) + arbitration rule 2/4 (§4) against `night_factory`/`monday_night` | last, because it is the one loop that can actively COLLIDE with existing scheduled work if the arbitration rules are wrong — build it once every other loop's receipt conventions are proven, so a collision is easy to diagnose from receipts already trustworthy | `idle_gpu_queue` block, plus a manual same-night collision test against a running `night_factory` |
| 10 | `--schtasks` registration print + the three-date acceptance receipt (§7) | last: needs everything above running for real to accrue the three dates | `always_on_lab_acceptance_<date>.json` |

**The chunk-14 gate**, stated the way `spec_chunk8`'s own gate was stated: if
three consecutive on-machine dates have not yet accrued by the time this
chunk closes (plausible — acceptance needs real wall-clock days, not agent
time), the honest close is "the supervisor and all eight loops are built and
unit-tested against synthetic data; ACCEPTANCE is pending N more days of the
machine actually being left on," not a fabricated acceptance receipt.

---

## 9. Named explicitly as chunk 15, not built here

- **`CloudReader` implementation** for L2 typing (needs
  `research_cloud_llm_readers.md` sections 1-6 filled in first: provider
  choice, pricing, the `llm_analyzer.py` abstraction change, per-model
  Lookahead Propensity).
- **X3 scenario forecasts wired into the Morning and into the catalyst
  calendar's `engine_probability` field** (needs L2 producing real typed
  rows first, which needs the reader question above answered, or enough
  local wall-clock hours to burn through the 51-261h local-only estimate).
- **`management_motivation_v1`'s actual collector** (earnings-call/
  shareholder-letter ingestion does not exist in this repo today).
- **A new `event_vocabulary.py` id for `strategic_pivot`-class events**, if
  none already exists, needed before `pivot_to_ai_narrative_v1` can move past
  PLACEHOLDER.
- **ONC clustering for E5's effective-trial count** — already named as
  deferred in `spec_chunk8` §2.2.2/step 9; this chunk's NN-lab orchestration
  (§3.5) consumes E5 as-is (the `n_trials_effective_proxy` stand-in) and does
  not reopen that gap.
- **M2's real-ledger rule distillation running nightly** — `spec_chunk8`'s
  own build order (step 8) already gates this on the ledger accruing ≥45
  resolved rows per cell; this chunk's §3.5 orchestrates E1/E4/E5, not M2,
  and a future chunk adds M2 to the same nightly sequence once that gate
  clears.
- **A `/coverage`-adjacent board route surfacing `lab_status.json`** if O4's
  developer board needs more than a bare file read (see note at the end of
  §3.8).
- **PDUFA/lockup/13D-G/index-rebalance data sources**, if a free one is ever
  found — `pm_catalysts.py`'s `UNCOVERED` list stays honestly non-empty until
  then.
