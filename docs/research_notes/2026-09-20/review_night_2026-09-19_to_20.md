# Review of the night 2026-09-19 → 09-20 (Fable, written 2026-09-20 08:30 HKT)

Murat's instruction this morning, verbatim: *"close the lab i didnt wanted to
spent tokens, local simulation ewas wht i asked"*. The lab was stopped by its
STOP file at 23:51:51Z (exit reason recorded in the lock), the daily pass it had
dispatched was killed by PID, and **from here on no cloud call is made without a
per-run instruction from Murat.** DeepSeek is off. The local model server is the
only thing that may burn compute, and it burns no dollars.

## RESULTS SCOREBOARD (rule: this comes before anything else)

| what | number | source |
|---|---|---|
| paper equity, five readable books | hack1 93,673 · hack3 80,947 · hack4 89,362 · hack5 92,238 · hack6 84,686 = **$440,907** | `/v2/account`, 2026-09-20 00:10Z |
| paper equity, hack2 | **unreadable: HTTP 401** from Alpaca with the key Railway and `.env` both hold | same probe |
| decisions on disk (Decision Contract, chunk 18) | **0. `backend/data/optimus/decisions/ledger.jsonl` does not exist** | the step has never executed (below) |
| forecasts graded in the trailing 24 h | **0 of 24,839** records; 17,614 never graded, 7,219 inside their window | `decision_vs_reality_2026-09-20.json` |
| DeepSeek spent since the $50 top-up | **$2.08** by the provider (57.18 → 55.10); N9 alone $1.67 | `llm_cost_audit --snapshot` |
| N9 library autopsy | 3,050 candidate rows (3,048 CANDIDATE, 2 REFUSED), **0 measured** | `research_gym/library_candidates.jsonl` |
| L2 typing, local 7B | 3,689 rows in the night, 7,863 for the day, 1,436 refused (15.4%, REFUSED_SCHEMA); backlog 18,794 | `typed_events/2026-09-19*.jsonl`, `_cursor.json` |
| NN lab | ran ONCE, 09-19 06:01Z; 12 heads on held-out 2026-08, best IC 0.022; did NOT run overnight | `NN_lab_2026-09-19.json` |
| X_anon_gap (local) | raw −18.9%/yr net, masked −16.9%/yr net, gap −2.0 pp t −0.54 → ADOPTED MASKED; **both arms lose** | `X_anon_gap_run01.json` |
| fleet | hack3/4/6 **crash-looping since the 09-20 deploy**; hack2 never on the wrapper; hack1/5 fine | `railway logs` |

RESULT IMPROVEMENT: NONE. Nothing that ran last night changed a book, a
decision, or a claim.

## What ran (UTC, 09-19 → 09-20)

- 06:44–08:15 and 16:51–18:21: N9 on DeepSeek, two 90-minute boxes, 3,086
  calls, 2.78 M tokens in / 2.45 M out. Each box ended in TIMEOUT, which is the
  design (the candidates file and cursor persist; ~8,300 unwarned moves remain).
- 18:13: the lab's idle queue dispatched `L2_typed_events` (job box 120 min).
  The loop's own box is 60 s, so the loop thread was abandoned at 18:14 and the
  lab refused to re-issue it for the rest of its life. The job was killed at
  20:22 with its rows already on disk. **The GPU then sat loaded and idle from
  20:22 to 23:51.** Six queued jobs never ran (X2, E1, X4, L4, S1, retype v3).
- 21:35: social pull. YouTube 113 rows (the key works), Reddit refused by name.
- 22:16: news pull, 30 rows over 19 sources.
- 23:36: the daily pass dispatched, 66 minutes after its 06:30 local time
  (ticks were regular, 65 in 6.6 h; unexplained). Killed at 23:50 in the
  analyst-snapshot step on Murat's instruction.
- 23:51: lab exit, reason `STOP_file`.

## What broke, ranked by what it costs

1. **Three of six loops were dead containers, not sleeping shells.** hack3,
   hack4 and hack6 printed `market_window.sh: 37: set: Illegal option -` on
   every start. Every committed blob is LF; the Windows working tree was CRLF
   (`core.autocrlf=true`) and `railway up` ships the working tree, so dash saw
   `set -u<CR>`. Fixed in the execution repo (`0878516`: `.gitattributes`
   `*.sh text eol=lf`); hack2/3/4/6 redeployed and each printed
   `MARKET WINDOW supervisor: role=...` at 1–2 MB. **The 0 MB in
   `railway metrics` that yesterday's message called proof of sleep was proof
   of death. The proof of a live supervisor is its own first log line.**
2. **hack2's Alpaca key is dead on Alpaca's side** (401 on `/v2/account`;
   Railway and `.env` agree). Needs Murat: regenerate the hack2 paper key in the
   Alpaca dashboard, put it in `.env` and Railway as `AAT_HACK2_KEY_ID` /
   `AAT_HACK2_SECRET_KEY`.
3. **The idle GPU queue can run one job per lab instance.** Fix: dispatch the
   job as a detached child with a receipt-keyed gate (the shape `launch_driver`
   already has for the pass) and return from the loop at once.
4. **The Decision Contract has never fired.** The 09-19 pass process started
   at 04:08Z, before the step's commit at 05:25Z, and reported five steps; the
   09-20 pass was killed before reaching it. Until it runs, "the engine
   decides" is a sentence, not a row.
5. **Nothing is being graded.** 17,614 records never graded across the seven
   declared mechanisms; the feedback leg of the learning loop is absent, so
   nothing can learn.
6. **The cloud price table is wrong twice.** Our `deepseek-flash` price
   (0.169 / 1.285 $/M) is neither the peak (0.30 / 1.20) nor the off-peak
   (0.15 / 0.60) rate, and ignores the schedule: peak is 01–04 and 06–10 UTC
   on weekdays (09–12 and 14–18 HKT); everything else, and all weekend, is
   half price. The ledger said $3.12 for what the provider billed $1.67. Four
   ledger lines are unreadable (truncated concurrent appends), which makes
   every telemetry line say "LOWER BOUNDS".
7. **N9 pays for prose.** 87% of its cost is output tokens (~790 per
   candidate); the only fields the admission path reads are the two rule lists
   and one mechanism line. The admission path is local and free, so the value
   is in measuring the 3,050 candidates, not in buying more.
8. **A long-lived lab straddled a commit.** The 04:53Z instance imported the
   new `news_pull` against the old `news_registry` after chunk 20 T1 landed
   and raised on every news tick until it was replaced. The lab should record
   HEAD at start and exit `SOURCE_CHANGED` when it moves.
9. **The analyst snapshot is 2 h 35 m of the pass** (2,362 tickers, serial).
10. **L2 refuses 1 row in 7 on schema** at the 7B reader, the 09-13 pattern.
    Read the first flush before the next run.

## More efficient (in this order)

1. Monday 13:00Z: confirm `agent_loop` starts inside the window on every
   loop, and at 16:30 ET that the authority prints
   `SEAL AUTHORITY ALLOCATED day=2026-09-21`.
2. Idle queue → detached children (item 3). One evening of GPU is then six
   jobs, not one.
3. Reorder the pass so the contract runs before the 2.5-hour snapshot if its
   inputs allow, else box the snapshot at 60 minutes; either way the contract
   runs today.
4. A `grade_forecasts` step in the pass with a count receipt (item 5).
5. Price the ledger by UTC hour with the real peak/off-peak table; write it
   under a file lock. If cloud is ever authorised again, off-peak only. The
   HKT night is entirely off-peak.
6. Cut N9's schema to the rules; measure the 3,050 candidates locally with
   `library_measure_2006_2019.py` + `library_placebo_null.py` before any new
   candidate is bought.

## More profitable (what would actually move terminal wealth)

- The loop closing: a decision row every day, delivered to the executor,
  graded against reality. Everything above serves that; nothing last night
  did it.
- Monday's allocator run. Since 09-11 no weekday allocation exists, so every
  loop runs on budget 1.0 with `claimed=None`. If Monday prints REFUSED, the
  artery is the day's only job.
- The Kelly v2 book is live and accruing; it needs sessions, not code.
- Stop spending GPU on digest reads at 7B. X_anon_gap says both arms lose
  17–19%/yr net; put the GPU on the typing backlog and the E1 typed-event
  head, which is the design of record.
- hack2 restored, or declared retired; a book that answers 401 is neither.

## Needs Murat

1. hack2's Alpaca paper key (item 2).
2. Reddit script-app keys, when wanted.
3. The local-only policy is now the default; say "cloud ok for job X, $Y" per
   run to lift it.

---

## The 18:00–21:00 HKT block (Fable, unattended; Murat: "identify problems and solve them")

Brief, verbatim: "sonnet for resaerch and opus for built. run backtests everytime u have an idea ... Use deepseek for anytasks or resarch u need as well dont run the openclaw yet ... we need to fix the decision making engine ... it should go with the highest ROI ... gut feeling ... test with llm and made up scenarios ... make sure railways doesnt passes 20 dolars a month. if it makes more money u can try day traiding but if holding for months is better thats better search this and see what people that won in markets are saying find correlations between things."

### Landed (every item pushed, CI green unless stated)

| # | what | evidence |
|---|---|---|
| 1 | **The Decision Contract runs, and first.** Reordered to step two of the pass; the analyst sweep stops itself at 55 min. The real pass reached it at 18:39 and `decisions/ledger.jsonl` exists for the first time: 43 DECIDED rows (4 BUY, 1 WATCH, 38 REFUSED). | `3d1afd9f`, `backend/data/optimus/decisions/ledger.jsonl` |
| 2 | **Forecasts are graded.** New `forecast_grader` step: 14,703 of 17,614 due records graded on the first run; 2,911 refused `NO_BAR_FOR_RESOLUTION_DATE` (local panel ends 09-11). **First honest grade of the swarm: mean probability 0.510 vs base rate 0.340, Brier 0.2625 vs climatology 0.2244 — overconfident, does not beat the base rate.** | `4603cce9`, `night_factory_2026-09-20/grade_forecasts_2026-09-20.json` |
| 3 | **Railway.** Warm loop off (`AEGIS_WARM_SKIP=1`) and Serverless on for the website backend: cache status reads `skipped`, RSS 685 → 301 MB, CPU 0. Loops run in `--once` cycles (full every 30 min, exits-only every 10 min; `AAT_LOOP_MODE=persistent` rolls back). Period usage read on the workspace page: $48.05 (memory $25.20, CPU $20.52). The Pro plan fee is $20 and INCLUDES $20 of usage, so "≤ $20" means usage ≤ $20 next period. | `92ed017f`; terminal `f40431c`; six deployments 18:10 |
| 4 | **N9's 3,048 candidates measured locally in 64 s.** Zero BH survivors on either read. The whole foreign-read excess is one family (rebound after a stressed drawdown: top tail 22.8% at p≤0.05 vs 5.5% for the bottom tail). One rule family to register, not 3,050 rules to buy. | `937228e9`, `N9_candidate_measure_run01.json` |
| 5 | **Congress collector repaired.** Fifteen production receipts said "ran" in 0.3 s while writing nothing: the job swallowed its own source failure below the receipt, and 07:30 ET is eleven hours into an FMP quota day already marked exhausted. Failures now reach the receipt, writes are on it, the slot is 00:40 UTC, and `buyer_ids`/`seller_ids` ride in the PIT payload. First real run: Tue 2026-09-22 00:40 UTC. | `b018f211`, `audit_congress_collector.md` |
| 6 | **Typing salvage.** 30% of the 7B reader's rows were refused over an `entities` block on ids that declare no roles; the block is now dropped and named on the row. Applies from the next typing run. | `25c703db` |
| 7 | **Research.** Horizon and winners (verdict: hold weeks to months; day trading loses to costs; 12 winner rules tagged testable/needs-data; "SP1/SP3" NOT found anywhere — ask Murat). Decision-rule + scenario-gym spec (the gate that refuses everything: `compose_book`'s eligible filter and `expected_payoff = "NOT CALIBRATED"`). | `research_horizon_and_winners.md`, `spec_decision_engine_and_scenario_gym.md` |
| 8 | **Local GPU.** Model server restarted (PID 32000, mine); E1 head read closed FAILED_VARIANT again at 24% coverage; L2 typing run 2 raising coverage (120-min box). | `night_local_1822.log` |

### The ROI decision rule (chunk 18c) — landed `5b35c398`, `4f1eb079`, `a58091ee`, `07aa42b6`, CI green

Spec Part B + D built: `backend/services/roi_rank.py` (score = measured net return / vol-based downside, top-K, fractional Kelly via the existing `size_ce_kelly`, personalities as Kelly fractions, behind `IC_ROI_RANKING`), `config.SIGNAL_MEASURED_RETURN` (every row carries its receipt path, test-pinned to exist), a `t` floor `ROI_MIN_T = 2.0`, and the `REVISED` ledger state with `decision_contract.revise()` (a revision is a new row with `parent_decision_id`; no text can revise, only re-ranked candidate fields).

**Today's contract rebuilt under the rule: 0 of 43 rows scored.** 38 never reached it (refused at a hard gate), 3 are agency book rows, and the two names that did reach it were refused by name: CVLG's `profitability_small` receipt states an IC t (4.29) but no t on the net return; INDV's `insider_opportunistic` read carries t 1.40, below the floor. BUY set, sizes and the worst case are byte-identical to the morning. The rule fires on a fixture (an insider read at t 2.6 sizes a 25%-vol name to the 3% cap and an 80%-vol name to 0.80%).

**What this says, plainly:** the engine now has the rule Murat asked for, and nothing in the repo qualifies for it. The signals with a measured per-name net read are insider (+0.17%/mo, t 1.40), small-cap profitability (+0.24%/mo, no t on the return) and their fusion (+0.15%/mo, t 1.66); low-vol, short interest, rating drift have no per-name net magnitude; earnings surprise is measured inverted; momentum is closed. The best number on the board, Book F seasonality (+0.43%/mo, t 3.12), is a BOOK read against its own twin and cannot be attached to a name. So "highest ROI among sure-enough candidates" is currently the empty set, printed as such on every row — which is the honest version of "it can't be sure so it doesn't make one". The way to a non-empty set is measurement, not code: net per-name reads with date blocks for the signals the committee already scores, and the pre-registered books accruing forward.

### Building at the time of writing
- **The scenario gym (chunk 18d, spec Part C)** — local model only, smoke N tonight, full N on the next unattended night; its output enters only as `gut_signal` with a measured reliability weight, NOT_ADOPTED until N ≥ 300 and a forward record exists.

### Not done, in order of value
1. The scenario gym's FULL run (N ≥ 300) on the next unattended night, then its reliability read.
2. The DeepSeek price table by UTC hour (peak 01–04, 06–10 UTC weekdays at 0.30/1.20; off-peak 0.15/0.60).
3. The idle-queue detach in the lab (one job per instance) — moot while the lab is closed.
4. hack2's Alpaca key (401) — Murat.
5. Monday 13:00Z: every loop's first `MARKET WINDOW cycle full` line; 16:30 ET: `SEAL AUTHORITY ALLOCATED day=2026-09-21`.
