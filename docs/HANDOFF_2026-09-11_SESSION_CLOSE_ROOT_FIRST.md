# HANDOFF 2026-09-11 (session close) — root first: five chunks in one day, and the loop that grades itself

**From:** Fable 5.1 as the validating session; Sonnet did the research (nine reports), Opus did the
building (chunks 1, 2, 3, 3b, 4 — the last two agents were cut by the account's session limit at
22:50 HKT after committing their work). $0 LLM spend by the programme itself.
**Read order:** this file → `ROADMAP_2026-09-11_ROOT_FIRST_THE_OPERATOR_BOARD_AND_THE_LEARNING_LOOP.md`
(the one TIER 1 roadmap: roots R1-R5, lanes O/N/L/B/E/F/A/M/X, §12 chunks) →
`HANDOFF_2026-09-11_FABLE_TO_OPUS_BUILD_PLAN.md` §6b (what each chunk landed, with commits) →
`AEGIS_VISION_2026-08-28_MURAT_IN_HIS_OWN_WORDS.md` §6 and §6b (Murat's two briefs today, verbatim)
→ `CLAUDE.md`.

---

## 0. RESULTS SCOREBOARD

| | |
|---|---|
| **RESULT IMPROVEMENT** | **NONE on strategies.** No book moved; no lane promoted. |
| **the one measured result of the day** | the **52-week target backtest** (390,368 IBES cells, 7,439 names, 228 months 2005-2023, walk-forward): the de-biased consensus beats the raw consensus on MAE and hit rate in **every** era (pooled MAE 45.3 vs 48.8, hit 48.4% vs 39.2%), and **a drift-only control beats both on MAE in every era** (37.6 pooled). That drift bar is what `TRIAL-CALIBRATED-TARGET-UPSIDE-1` (drafted, UNSIGNED) must clear. |
| best historical net strategy vs market | none surviving its own control above the tradability floor (unchanged) |
| best forward paper strategy | none; the six books were −4.43% aggregate in week one (09-09); no newer venue read this session |
| only live lane | **R2** (local 7B, anonymised monthly digest) +16.19%/yr over its shuffled control, t 3.92; panel B still `PENDING_MODEL` (the model server was down all day; started at close for tonight's queue) |
| independent selectors with evidence | **one** — unchanged |
| **defects found live and fixed** | (1) the packaged app ran with **no API keys** (`config.py` rooted `.env` on `__file__`); (2) the guide repeated because pywebview's private mode wiped storage; (3) **every failed launch was `sys.stdout.isatty()` in a windowless process** (uvicorn dies before binding; the old build, the pythonw shortcut); (4) a second Aegis instance's `stop_if_owned` killed the first's model server (ownership was per checkout); (5) a test appended to the live evidence ledger on every suite run; (6) the desktop backend ran Railway's twelve scheduled jobs on the laptop; (7) the stock page 404'd on all but twelve symbols; (8) heavy endpoints timed out at 45 s on a cold laptop; (9) "Stocks Analyzed 56" was five curated names per sector; (10) the page's "expected return" was a 5-year simulation mean beside a 1-year consensus, with the consensus clipped to a 30% mega-cap ceiling; (11) a ten-year look-ahead the Alpaca backfill would have written (a 2015 headline labelled at the 2025-01-02 open); (12) the capped yfinance sweep re-pulled the same 300 names for ever; (13) the GDELT theme sweep produced nothing and looked healthy; (14) NVDA's p10 sat above spot (band withheld with reason). |
| tests | **7,966 → 8,201 on `68d6154`** (my run); chunk 4 adds 111 lane-N tests; **merged tree `4f59721`: 8,314 passed / 20 skipped / 0 failed** (my run, 574 s) |
| CI | green through `68d6154`; one red (`823fbf1`, a Windows-absolute path in a sandbox test) fixed in `64a9197`; the merge `4f59721` is being watched |
| **data pulled tonight (lane N, first real run)** | Alpaca/Benzinga **3,799** rows (the 2015 backfill resumed from a cursor — the 83.6% stall is fixed) · GDELT 1,019 · SEC EDGAR 8-K current 409 · yfinance news 793 · Google News ×10 regions 352 (zh-CN, zh-TW, ja, ko, en-HK, en-SG, en-IN, en-AU, en-GB, en-US) · Nikkei Asia 50 · r/algotrading 25 · r/SecurityAnalysis 25 · Quantocracy 10 — **6,581 rows, 17 sources, every row with `first_seen_utc`**; analyst snapshot day 1: 250 symbols (PARTIAL, Yahoo throttled at ~3 s/symbol) |
| E1 append | 0 rows appended from 6,014 corpus rows: 808 await the next session's bars, 2,562 predate the 2025-01-02 bar table (the backfill's 2015 rows), 0 PIT violations |
| the app | **`Aegis.lnk` → `dist/AegisDesktop/AegisDesktop.exe`, the thin launcher (37 MB)**, rebuilt after the stdout fix and verified from a no-console launch: backend up in 2.3 s, keys visible, one scheduled job |
| evidence memory | rotated into monthly files (102,029 rows in → 102,029 out); the live month is untracked; a closed month left untracked fails a test |

---

## 1. WHAT LANDED, BY CHUNK (commits in the build plan §6b)

- **Chunk 1** — config root honours `AEGIS_REPO_ROOT`; an AST gate over every `__file__`-rooted path
  (24 allow-listed, 10 of them retired by the launcher); browser storage persists; Ask starts the model.
- **Chunk 2** — the thin launcher (pull → pip-if-hash-changed → export-if-frontend-changed → the shell
  from the checkout's venv under a job object; `git_head` on `/api/health`); ledger rotation; ownership
  by PID; scheduler and warm loops off in desktop mode; the suite's ledger guard; the terminal repo's
  handoff brought to 09-11 (`aegis-alpha-terminal` `e613082`).
- **Chunk 3** — T0 the windowless-stdout fix; one `__ticker__` shell for every symbol; `cache_swr_202`
  (202 + progress instead of a timeout); the desktop screener over the 3,056-name universe in two tiers
  (all scorecards at 0.1 s, the top 200 by `p_beat` through the Monte Carlo in 10.2 min); the universe
  page; the board (`/tree`, `/file`, `/app-log`, `/ledger`; secrets refused by name); the sealed-month
  guard.
- **Chunk 3b** — the Morning click (seven declared steps, one receipt per day; a real run: 389 s);
  Ask with read-only tools and a deterministic router; M3 hindsight-safe retrieval; **O11 the 52-week
  target with no caps** (isotonic calibration in place of every clip; the 12-month figure is
  `paths[252]`, never a root; the audit script; the IBES backtest above); M4 Murphy's Brier split on
  the board.
- **Chunk 4** — the source registry (24 sources, `pit_grade` enforced; an id not in it cannot be
  pulled); the corpus writer with cursors, dedupe, receipts, the zero-twice RED rule; entity resolution
  with a counted refusal (name table 230 of 3,056 named — the analyst snapshot's `--update-name-table`
  closes it); the daily analyst snapshot with checkpoints; the E1 nightly append with a PIT anchor per
  grade and re-verification; the coverage card; **the real pulls**.

## 2. WHAT THE RESEARCH SAID (nine Sonnet reports, all under `research_notes/2026-09-11/`)

News coverage (GDELT → Google News RSS regions → Alpaca → AKShare; World Monitor is AGPL, take its
schema; God's Eye is sensors, not news) · nobody outside has multi-year net OOS evidence vs SPY ·
attention nets: the next text design is typed events + a tabular head, not a new encoder; GBM is the
mandatory control for any net · Qanat/Notes joins (read-only MCP surface, published-anomaly cadence,
decay-blended weights) · the average-investor problem quantified (activity costs ~6.5 pp/yr; robo-
advisors never pick or review; no product does goal intake AND daily control; the eight classic rules
all decay OOS after costs) · the learning loop (ExpeL winner-vs-loser distillation; "Profit Mirage"/
"Alpha Illusion" P1-P6 protocol; the anonymisation gap must be measured) · repos (Alpaca MCP,
edgartools, Metaculus forecasting-tools, the EDT event taxonomy) · social (no audited P&L anywhere; X
pay-per-read, Reddit bars ML use; notify-only before execution) · patents and data (six expired patents
to mine; SEC XBRL `filed` dates; Form 25/15 delistings; daily options-implied-move snapshots) ·
Headline Arena (a fit as read-only independent settlement, ledger first; perpetual licence on
submitted text; registration is Murat's) · idea round 2 (the TAQ cost model, the Frazzini
disposition-overhang conditioner reached by two angles independently, low-SI × high-turnover
long-only, insider clusters by length, the abstention book vs the buy-and-hold receipt) · two specs a
builder can implement: `spec_events_and_calibration.md` (39 event types + `no_event`, the JSON schema,
a 20-row golden set, Murphy's decomposition, the ledger fields, the retrieval predicate) and
`spec_price_targets.md` (built in 3b).

## 3. TONIGHT'S QUEUE (started at close, from the terminal — the "from the app" acceptance is tomorrow's)

`NIGHT_QUEUE="P6_bars_and_regret:60,E1_append:30,N3_frozen_embedding_head:60,R2_widened_panelB:150,G3_evolve_v2:240"`,
the model server started unbound beforehand. P6 refreshes the bars to today (they ended 09-08), E1
labels the 808 pending rows, N3 refits on the grown panel, R2 finally reads panel B (the AMNESIA canary
must be re-run before its number is quoted), G3 resumes from its search state with seeds outside the
union. Receipts under `night_factory_2026-09-11/`. **Check the overlap against the previous G3 log
before crediting discovery** (protocol §9).

## 3b. THE NIGHT'S RECEIPTS (read 2026-09-12 10:45 HKT)

- **P6**: 1,257,540 daily bars for 3,060 symbols over 424 sessions, 2025-01-01..2026-09-11 — the bar
  table is current. **E1_append**: 808 rows appended (0 PIT violations; 2,562 backfill rows predate the
  bar table). **N3**: `FAILED_VARIANT` again — the frozen embedding does not beat shuffled text (IC
  −0.0032 t −0.68 vs TF-IDF +0.0003; difference t −0.70, p 0.48); a replicated negative on the grown
  panel, consistent with 09-10. **R2 panel B**: started 10:46 HKT on the model, running. **G3**: follows.
- **Defect:** N3 ran **11 hours under a 60-minute box** and no TIMEOUT receipt was written — the
  embedding stalled at 8+ hours per chunk under GPU contention with the model server (5.3 GB of 8 GB
  VRAM) and the factory's `subprocess.run(timeout=...)` never fired through the venv's launcher wrapper.
  A time box that cannot go red is a broken gate; chunk 3c fixes it with a real sleeping-job test.
- **CI on the close push was red** on the site build: the worktree merge combined two `STATUS_TONE`
  maps in the board cards (the desktop export tolerated the duplicate; Turbopack's site build did not).
  Fixed in the morning; the site build, `tsc` and the desktop export are now all part of validation.
- **Operational:** removing the merged worktree emptied `frontend/node_modules` in the main checkout
  (most likely a junction the worktree agent made into it; `git worktree remove --force` followed it).
  `npm ci` restored it. Do not junction node_modules into a worktree.

## 3c. THE CRASH OF 2026-09-12 10:53 HKT (read 14:20)

- **Cause, from the System log:** bugcheck **0x116 VIDEO_TDR_ERROR** — the display driver did not
  recover from a GPU timeout — logged at reboot 10:55 (minidump `C:\Windows\Minidump\091226-15453-01.dmp`,
  driver 595.97). At 10:53 the GPU held the model server (5.3 GB of 8 GB) and **R2 panel B was
  reading cells on it** (600 of 18,521 done; the 1,118 completed calls are in `llm_calls.jsonl`; the
  answers file lets it resume). So: an unattended night job on the local model tripped the GPU
  driver. Also found by chunk 3c before the crash: the PC entered **Modern Standby 23:58 → 08:09**,
  which is why N3's embedding "took 8 hours" — the machine was asleep. Awake time still exceeded the
  60-minute box, and the box still never fired.
- **What the crash did to the checkout:** the git index was corrupt (rebuilt); a stale worktree's
  index was the persisting `fsck` complaint (removed); `scripts/night_factory.py` was **18,880 NUL
  bytes** (chunk 3c's uncommitted edit, mid-write at the crash) — restored from HEAD; 1,166 tracked
  receipts showed as modified but only by line endings (restored); the roadmap commit was unpushed
  (pushed). Nothing committed was lost.
- **Rules that follow:** (1) an unattended night that uses the GPU needs a **TDR mitigation** before
  it is trusted — conservative llama-server batch sizes, and Murat may set the `TdrDelay` registry
  value (attended, admin); (2) **disable Modern Standby / sleep for a night run** (`powercfg` — the
  night factory should refuse to start if the active power plan allows sleep, and say so); (3) every
  in-progress edit is committed or stashed before a long unattended run.
- **What chunk 3c then DID about it (2026-09-12, commits under `T1`/`T1b`):**
  - `backend/services/llama_server.py` now starts the server with
    `--batch-size 512 --ubatch-size 128` (llama.cpp's own defaults are 2048 / 512),
    overridable by `AEGIS_LLAMA_BATCH` / `AEGIS_LLAMA_UBATCH` and reported by
    `status()`. A TDR fires when ONE GPU submission outlasts the driver's
    watchdog, and the size of a submission is the batch, so a quarter-size batch
    is a quarter-length submission. It costs prompt-processing throughput and
    nothing else — generation is one token at a time either way — so an
    attended session that wants the speed back sets the two env vars.
  - `scripts/night_factory.py` prints `nvidia-smi`'s driver version and VRAM at
    the start of a run, so the next crash receipt has them without archaeology.
    Measured on this machine: `NVIDIA GeForce RTX 5060 Laptop GPU, 595.97,
    836 MiB, 8151 MiB`.
- **THE ATTENDED OPTION, FOR MURAT ONLY — `TdrDelay`.** Windows kills and resets
  a display driver whose GPU command has not returned within `TdrDelay` seconds
  (default **2**). Raising it lets a long kernel finish instead of bugchecking;
  the cost is that a genuinely hung GPU freezes the desktop for that long
  instead of recovering. **No session may set this.** It needs an elevated
  shell and a **reboot** to take effect:

  | where | `HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Control\GraphicsDrivers` |
  |---|---|
  | value | `TdrDelay` |
  | type | `REG_DWORD` |
  | suggested | `10` (decimal seconds; default is 2 when the value is absent) |
  | takes effect | after a reboot |
  | undo | delete the value, reboot |

  Do the batch-size mitigation first and see whether a night survives; it is
  reversible by an env var and needs no reboot. `TdrDelay` is the second lever,
  not the first, and it is Murat's to pull.

## 3d. WHAT 2026-09-12 LANDED (read 18:30 HKT; details per chunk in the build plan §6b)

- **Chunk 3c** — the time box on its own clock (awake seconds, tree kill by PID, proven by a sleeper);
  the target band on the upside tercile (all eight audited names show a band); the frontend triple
  check; the night page had served the 09-08 board for four nights (a literal path) — fixed; the LLM
  spend ledger rotated. **Chunk 5** — paper books with twins, the cadence scheduler (30m/daily/weekly/
  monthly/quarterly), the ledger's 19 new fields, the books board, Headline Arena dry-run. **Chunk 5b** —
  seven books + fifteen twins seeded and pre-registered (four UNSIGNED drafts, family
  `NIGHT_JOB_BOOKS_2026_09`), Book A's short-interest panel from the local WRDS tables, the replay night
  job (smoke only; full pass 20-45 min, not run), lane D's book `book:f64e8d9912412124` and
  `scripts/monday_night.py`, the arena job on the venue's real protocol. Suite 8,314 → 8,639; CI green
  through 5b's fix. **Chunk 5c** (the cost model) was building at close.
- **Chunk 5c** (the TAQ empirical cost model) landed at 18:50: **the one measured result of the
  evening — re-graded under the empirical curve, the top night result's Sharpe moves 4.5× in level
  (+0.155 → +0.704) and its deflated Sharpe does not move at all (0.0000 → 0.0010 at 40,680 trials).
  The cost model was never what stood between that genome and a claim.** 208 receipts re-graded, 30
  of 31 rankings unchanged; the one that changed is a null control overtaking a prior because a
  cheaper ruler rewards turnover. Suite 8,694.
- **Every remaining chunk has a builder spec** under `research_notes/2026-09-12/` (5c cost model, 6
  agency intake, 7 lane X, 8 memory + stopping rules, 9 heads/conformal/Qwen3) plus two probes (the
  short-interest panel exists locally; Alpaca IEX minute bars: one paginated stream a day, ~10 MB).
- **Owed / attended:** re-seed Books B and B′ so they carry the beta-matched twin; Murat creates a
  dedicated Alpaca paper role for lane D (D2's fill receipt waits on it); the arena registration; the
  `TdrDelay` registry option; `powercfg` is already "never sleep" on AC on this machine.

## 3e. PAUSE POINT — 2026-09-12 21:35 HKT (Murat: "pause now, we continue in a few hours")

- **Pushed and CI-green through chunk 7** (`main` at the chunk-7 docs commit; 9,080 tests).
- **Chunk 6 landed** (the agency: IPS, three options, `POST /agency/hold` the only `human_text`
  route, the review row written before the call, protect-first, plain words; no book held).
- **Chunk 7 landed** (P1-P6 schema + refusal; L3 INCONCLUSIVE on panel B — all cells post-cutoff;
  X4 routing makes R2 worse; anonymisation gap, recall probe and elasticity frozen `PENDING_MODEL`
  with hashed cell lists; the market sensor).
- **Chunk 8 was on its final step (the suite) at the pause**: five task commits are LOCAL and
  UNPUSHED (`E5_stopping_rules`, the decay sweep, `M2_distill`, the anomaly cadence, the read-only
  query surface for the Optimus MCP). **Resume = read `scratchpad/build_chunk8.md`'s report, run
  the fast suite, review, push, `ci_watch`, then chunk 9** (`spec_chunk9_heads.md`).
- Model server: DOWN all day (by design after the crash). The three `PENDING_MODEL` X-lane jobs and
  R2 panel B run when it is next up — with the conservative batch sizes and the power plan checked.
- Attended, unchanged: lane D's paper role, the arena registration, `TdrDelay`, the B/B′ re-seed.

## 3f. RESUMED 2026-09-13 01:30 → 02:20 HKT — chunks 8 and 9 validated and pushed; every planned chunk has now landed once

- **Chunk 8** validated (9,180 after fixes): the night search's one ACTIVE lineage survives deflation
  at 595 trials (per-bank Sharpe 6.27 vs an expected-max bar of 3.15) while the random-genome null has
  0 of 10 survivors; the first learned rule is CANNOT DETERMINE on 0 resolved rows; the decay sweep's
  gain is partly dilution and says so; week 1's published-anomaly prereg passes the linter.
- **Chunk 9** validated (9,272): the frozen embedding FAILED_VARIANT at 5 and 21 sessions (Holm 1.0
  vs shuffled text); the typed-event proxy head beats GBM at 21 sessions but not shuffled events;
  ACI lifts high-vol coverage 0.837 → 0.880; ADWIN needs a [0,1] stream to fire at all; Qwen3 would
  take 25.6 days on panel B vs 3.9 h for the incumbent at the contended rate — the idle measurement
  decides; the stage field is on receipts.
- **Three CI reds in one night, all the same family** (a request validated only after a data file the
  runner lacks): a bad cadence answered 503; re-grades written beside gitignored scratch receipts; an
  unparseable `as_of` answered "no panel". Rule: validate the request before touching data. And one of
  mine: I pushed on the commit chain instead of the suite's exit line (memory written).
- **What is now on disk that was not two days ago:** the launcher; the board; the universe; the
  Morning click; Ask with tools; the 52-week target with its backtest; the news corpus (17 sources);
  books with twins and a cadence; seven pre-registered books; lane D's book; the agency intake; the
  P1-P6 protocol; the empirical cost curve; stopping rules; distillation; the read-only query surface;
  the heads with conformal and drift. **No strategy has moved. RESULT IMPROVEMENT: NONE.** What has
  moved is that every number now sits beside its twin, its cost curve, its calibration and its refusal.
- **Chunk 10 landed 05:30 (9,358):** the typed-event pipeline — vocabulary as a hashed table, the
  contract byte-equal to the spec, the resumable night job frozen at 6,020 rows `PENDING_MODEL`
  (4.9-10 h of reader time), the three consumers reading typed rows when they exist; nine corpus rows a
  `splitlines()` reader was silently losing on every append (U+2028 in headline bodies); a PIT defect in
  the prompt's date caught before any call; the vocabulary lacks an `ANALYST` type (C1's largest kind).
- **Running at close (05:35, detached, CPU only, no model):** `B_first_books_replay:90` (the four
  books' first 1990-2024 read vs their twins, per era, Holm within the family) then `E1_event_head:150`
  (the full two-model run on the proxy). Receipts under `night_factory_2026-09-13/`.
- **The replay landed 06:12 (14 min):** A loses to its random twin (−0.54%/mo, t −2.26, every era);
  B is null and its same-day falsifier is null too; **C, the disposition-overhang conditioner, is
  +0.40%/mo net vs the unconditioned reaction book, t 2.13, positive in all four eras — CONDITIONAL
  (Holm at family size 4 not cleared; the two registered falsifiers are the next test)**; D refused by
  registration. Detail in the roadmap §11c. RESULT IMPROVEMENT: NONE.
- **E1 landed 06:27 (16 min):** the keyword-proxy event table beats nothing — EVENT−SHUFFLE IC
  +0.0009 (GBM) and +0.0029 (StockMixer), Holm p 1.0; **FAILED_VARIANT for the proxy, the typed-event
  question stays open until L2 types the cells** (the receipt's own `next_test`). StockMixer beats GBM
  on the identical table (t 2.01 nominal, ≈0.9 after the 5-session overlap); SHUFFLE keeps that gap, so
  it is the architecture, not the text. Detail in the roadmap lane E.
- **Next:** run C's two falsifiers (a night job, CPU only); once the model server is up under the night rules (TdrDelay
  attended), run in order: R2 panel B, `L2_typed_events` (then re-run E1 on typed rows), the
  anonymisation gap, the recall probe, L4's idle measurement, M2's rule text; add an `ANALYST` type to
  the vocabulary before X2 uses C1; the B/B′ re-seed; the attended items unchanged.

## 3g. 2026-09-13 06:40 → 08:00 HKT — chunk 11: the four books' next tests, run the same morning

- **Chunk 11 landed (9,431 → 9,433 after my two edits):** C's two falsifiers with the registered
  construction re-read, A's $10M corner with the twin re-drawn per floor, B's verdict rule applied to
  run 1's receipt, vocabulary v2 with the analyst family, all three jobs registered and run.
- **The three reads (roadmap §11c "Second read"):** **A FAILED_VARIANT** (−0.94%/mo on its confirm
  slice at its own floor); **B FAILED_VARIANT both arms** (≤ 0 point estimates; the power warning does
  not rescue a negative); **C CONDITIONAL at +0.24%/mo t 1.38** under the registered construction —
  the placebo passes, the momentum falsifier is untestable because momentum was never alive on the
  book's rows. Three of four historical reads closed on their own rules. RESULT IMPROVEMENT: NONE.
- **Three defects found and fixed live:** (i) run 1's overhang warm-up was 24 months against a
  registered 60 (found by the Sonnet literature note asking why the 1990s were weakest); (ii) the night
  factory's folder defaulted to a literal `2026-09-08` — two real receipts landed five days back before
  I set `NIGHT_RUN_DATE`; both the factory and the jobs module now default to today and create the
  folder at write time; (iii) "momentum dies" was vacuous at raw t 0.15 — the verdict function now says
  MOMENTUM_NOT_ALIVE and the sentence says untestable, not passed.
- **Registration hygiene:** TRIAL-DRAFT-C Amendment 1 (a primary ≤ 0 closes the book) written before
  the registered read, with what had been seen recorded in the draft itself.
- **Both agents died once to the session rate limit** (reset 06:40) and were relaunched; nothing
  was lost because neither had written yet.
- **Next:** the model-dependent queue is unchanged (R2 panel B, `L2_typed_events`, then E1 on typed
  rows, the anonymisation gap, the recall probe, L4's idle measurement, M2's rule text — all behind the
  attended `TdrDelay`); C's `next_test` is its own $10M re-measurement and the v1 event sign once L2
  types; B/B′ re-seed; the attended items unchanged. No CPU-only job is owed tonight.

## 4. FOR TOMORROW (chunk 3c, then 5), in order

1. **Read tonight's receipts** and the merged-tree suite count in the build plan; `python -m scripts.ci_watch`.
2. **Condition the target's error quantiles on the upside tercile** (NVDA's band was withheld for this);
   then the page shows the band again. Run `scripts/price_target_audit.py` on Murat's names.
3. **Run the Morning from the app** (the launcher, then the board's button) and the night queue from
   the app — the acceptance test that was deferred twice.
4. **Analyst snapshot day 2** with `--update-name-table` (names the other 2,826 symbols, which lifts
   GDELT/EDGAR resolution from ~3%); re-run `news_pull --source all --resume` (the GDELT theme sweep
   fires for the first time; Alpaca continues the backfill; give the backfill `--since 2025-01-01`
   until older bars exist, or pull older bars).
5. **Chunk 5** — books with twins (B1-B5), the M1 ledger fields, Headline Arena (M6; Murat registers).
6. **Terminal repo:** the tracker's newest day file is 2026-09-02, so the scorecard vintage is
   2026-09-02 — run the tracker there, then `python -m scripts.potential_universe_run`.
7. **Do not** quote the target backtest's per-era table without the drift control beside it; do not
   rank on the calibrated upside before the prereg is signed; do not add a router.

## 5. MUST NOT REGRESS (added today; cumulative list in the roadmap §6 and §13)

17-28 in the roadmap. The two that cost the most today: **a windowless process has no stdout** (bind
the streams, never ask `isatty`; test with `Start-Process`), and **ownership is per process, not per
checkout**.
