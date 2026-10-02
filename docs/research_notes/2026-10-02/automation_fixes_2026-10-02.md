# Automation fixes, 2026-10-02 evening

Licence: internal operations (`PRODUCT_EXPERIMENT` machinery). No strategy, cap, stop
or sizing was changed. Machine-level details (process ids, memory, power settings) are in
`backend/data/optimus/local_pc/`. Follows the three read-only reviews of the same
evening (`automation_audit_2026-10-02.md`, `review_forecasts_and_books_2026-10-02.md`,
`review_paper_accounts_2026-10-02.md`).

## RESULTS SCOREBOARD

- **RESULT IMPROVEMENT: NONE.** This is plumbing. It does not move any economic
  number; it puts the graders back on current bars and makes failures visible.
- **Bars panels: 2026-09-28 → 2026-10-01 (+18,216 rows, all four panels, 0 symbols
  rejected).** Root cause of four days of HTTP 400: ONE ticker, `BRK-B`, in the
  forecast-only side panel added on 09-29. Alpaca answers
  `{"message":"invalid symbol: BRK-B"}` for the whole request (measured with a
  2-symbol call: `AAPL,BRK-B` → 400, `AAPL,BRK.B` → 200 with 09-28..10-01 bars).
  Receipt `prices_2025_26/bars_refresh/20261002T123000Z.json`.
- **Scheduled tasks: 10 daily jobs now catch up after a missed start and may wake
  the PC (on AC); 2 new tasks** (`AegisReaderSupervisor`, `AegisCatchUp`). The catch-up
  started the 5 jobs that 10-02's sleep ate; 4 ran clean, 1 (nn_lab) refused itself
  for a reason unrelated to scheduling (below).
- **always_on_lab relaunch cause found, two parts:** a Startup-folder
  `AegisAlwaysOnLab.vbs` (2026-09-13) runs the lab at every LOGON, and the lab's
  STOP file lives in a DATED night folder, so the 09-27 STOP stopped nothing on
  09-30. All three relaunches sit two minutes after a `Kernel-Boot` 27 event. A
  persistent `always_on_lab_OFF` marker now stops every launch path.
- **The 10-02 daily pass that "missed" had in fact RUN**, at 11:58 local, started
  by the resurrected lab (its start matches the lab lock to the second). It ran on
  stale bars and `--no-broker`. With the lab OFF, the scheduled task plus
  `AegisCatchUp` is now the only daily-pass trigger.
- **docs/PAPER_ACCOUNTS.md:** the last committed version listing the fleet is
  `3204eb4d` (09-27), NOT `cbfcb3d3` (09-28) as the paper-accounts review says;
  `cbfcb3d3` had already dropped hack1-6 and PC-PAPER. The generator now refuses a
  doc that drops any account the previous doc (or a high-water mark seeded from
  `3204eb4d`) listed.
- **LLM spend this work: $0.0026** (one hyp_lab nightly, run by the catch-up).
- Tests: 30 new offline tests; 906 tests across every touched module's files green
  (`AEGIS_PERSONAL_MODE=0`, no network, full suite NOT run).

## Per item

### 1. Bars refresh: HTTP 400 since 2026-09-29 22:30 UTC

**Cause.** `scripts/pull_bars_refresh.py` pulls the union of all four panels'
symbols. The `forecast_only` panel (139 names, added 09-29 for the world digest's
proxy ETFs and stranded ledger names) carries `BRK-B`. P6's puller sent it as-is;
the vendor rejects the WHOLE 100-symbol request; P6 retried four times and raised;
`refresh()` refused with "nothing overwritten". `scripts/pull_forecast_bars.py`
had already learned this exact lesson (`_vendor_symbol`) and the refresh never
used it.

**Fix.** `pull_bars_refresh.vendor_symbol()` (trailing class letter only) and
`pull_chunked()`: asks in vendor notation, returns rows under the panel's
spelling, and on a 400 that NAMES an invalid symbol drops exactly that symbol,
records it in `receipt.pull.rejected_symbols`, and continues. A non-400 failure
still refuses the whole refresh. A rejected symbol is a `VENDOR_REJECTED` warning
on the receipt headline, never silent.

**Evidence.** `bars_refresh/20261002T123000Z.json`: grader 1,290,721 → 1,299,875
rows, ranker 6,802,911 → 6,810,689, delisted 1,861,180 → 1,861,817 (1,784 symbols
kept: survivorship panel intact), forecast_only 59,109 → 59,756 (the proxies, incl.
`BRK-B` through 2026-10-01). 313 symbols' histories re-adjusted (dividends) and
re-pulled whole, as designed. Today's partial session is deliberately NOT stored
(the refresh drops an unclosed session). The bar-defect screen is applied at
LOAD (`xs_ranker.load_bars → stitched_tickers.split_stitched → bar_defects.screen`),
so the refreshed file passes through it unchanged. The daily pass's own bars step
then logged `unchanged` (idempotent).

**Loud line.** New `backend/services/bars_health.py`: any gated panel missing ONE
closed session is `DEGRADED` (stricter than `BARS_MAX_AGE_SESSIONS`, which gates
acting). It heads the daily-pass receipt (`degraded` block, printed first, and
`DEGRADED(n) |` in the headline), the alert-pass receipt `state`, the alert log,
and any held-over digest's header. First live alert receipt after the change:
`bars OK: newest 2026-10-01 = last closed session 2026-10-01`.

**Grading.** See "Daily pass" below.

### 2. The reader supervisor had no scheduled task

**Fix.** `scripts/task_keeper.py reader`, run by the new task
`AegisReaderSupervisor` (at logon, on unlock, on resume-from-sleep
[Power-Troubleshooter event 1], daily 07:00, and every 2 h). Idempotent: exits
when a `night_reader_supervisor` process is alive (matched on the command line,
one-shots `--probe`/`--repair-once` ignored); exits when
`dowjones/SUPERVISOR_STOP` exists (the owner's pause, unchanged semantics); if
the process scan itself fails it does NOT launch (CANNOT DETERMINE). Otherwise it
launches `dowjones/supervisor_run.cmd <HH:MM> <dated log>` detached, with
`--until` rolling 23 h ahead, and logs the PID to `task_keeper/keeper.jsonl`.
`supervisor_run.cmd` with no arguments behaves exactly as before.

**Evidence.** Task fired by hand at 20:42: `{"action": "alive", "pids": [two ids, recorded locally]}`, rc 0, no second supervisor. The launch branch is covered by
an offline test (one launch, then `alive`); a live launch will happen when the
current supervisor reaches its own 12:00 end.

### 3. Missed triggers

**Cause, two parts.** (a) Four daily tasks had no StartWhenAvailable; (b) four had
a power-source start condition, so a catch-up could be skipped
silently (AegisAnalystPanelDaily had StartWhenAvailable AND still missed). Also:
the local power settings did not allow wake timers, so "wake to run" did nothing (recorded locally).

**Fix.** StartWhenAvailable + WakeToRun + power-source conditions off on the 10 daily
jobs. Wake timers were enabled for part of the local power settings (details recorded
locally; the rest is the owner's call). New `AegisCatchUp` (`task_keeper catchup`, same triggers
as the reader task): for each job in `CATCHUP_TASKS` it computes the last
scheduled occurrence from the task's own trigger and starts the task BY NAME if
it has not run since (15 min grace for Windows' own catch-up, 20 h maximum age).
The fleet-manager OPEN/PRECLOSE passes are excluded on purpose: a live-order pass
at the wrong time of day is not a catch-up. STOP files are untouched: the task's
own action still honours them.

**Evidence.** `task_keeper/keeper.jsonl` 12:43:03Z: started AegisDailyPass,
AegisFleetDailyCheck, AegisNNLabNightly, AegisAnalystPanelDaily,
AegisHypLabNightly; ContestRehearsal `ok`. Outcomes: FleetDailyCheck rc 0
(`fleet_daily/fleet_20261002T124304Z.json`, 0 flags; website lane NAV DEGRADED,
newest 10-01); HypLab rc 0 (3 hypotheses declared and run, $0.0026); AnalystPanel
running at the time of writing; DailyPass rc 2 (refused correctly: the hand-run
pass below held the day); **nn_lab FAILED: `TableShrink`, 4 stored grid rows
(EQBK, THFF in 2026-01) would be lost.** The bars for those dates are present;
the 313 re-adjusted histories moved a marginal grid membership. The guard is right
to refuse. Owed to the owner (it is nn_lab's universe rule, not scheduling): freeze
stored grid membership on append and only fill labels, or accept the re-adjusted
membership deliberately.

**Daily pass.** The broker read: `run_paper_accounts` now runs WITHOUT
`--no-broker` (config `DAILY_PASS_PAPER_ACCOUNTS_BROKER_READ = True`, read-only
GETs). A pass without broker rows, or with a broker error, or with a refused doc,
is a `DEGRADED` line at the top of the receipt. RESULT OF THE HAND RUN: see
"Daily pass, hand run" at the end.

### 4. hyp_lab STOP

**Cause.** A 0-byte `hyp_lab/STOP` (2026-09-29 22:41) and a `.cmd` that exited 3
BEFORE python started, so no receipt ever said which file or how old.

**Fix.** The `.cmd` no longer checks STOP; `hyp_lab nightly` does, and writes a
receipt whose FIRST key is `why_exited` (file, since, age) and still exits 3. A STOP
older than `config.STOP_FILE_STALE_WARN_H` (48 h) is reported as "possibly
forgotten" and still stops (owner's call). `cmd_schtasks` writes the new `.cmd`.

**Evidence.** With the old STOP in place: `nightly_20261002T123858Z.json`
`why_exited: STOPPED by ...hyp_lab\STOP (since 2026-09-29T14:41:35+00:00, 70.0 h
old) -- WARNING: older than 48 h, possibly forgotten`. STOP then removed; the
catch-up run completed OK.

### 5. always_on_lab relaunching

**Cause (evidence).** `Startup\AegisAlwaysOnLab.vbs` (LastWrite 2026-09-13) runs
`always_on_lab.cmd` at every logon. System log `Kernel-Boot` id 27 (a boot, not a
resume from sleep) at 09-30 12:00:43, 09-30 20:19:33, 10-02 11:56:30; the lab lock
starts 2-3 min later (04:03Z, 12:20Z, 03:58Z); LogonTrigger tasks (Telegram,
OpenClaw) last ran 11:56:31. The previous OFF was a `STOP` in the 09-27 night
folder (`always_on_lab.stop_path()` is dated), so it bound 09-27 only. No
scheduled task, Run key, run_night_launcher or Telegram path launches it.

**Fix.** Persistent `backend/data/optimus/always_on_lab_OFF` (config
`ALWAYS_ON_LAB_OFF_MARKER`), dated by the stamp written in it. Honoured by
`always_on_lab.cmd` (before python starts), `always_on_lab.main()` (before the
lock, model server or any loop), and `night_run_until --lab`. Health
(`p_always_on_lab`) reports `STOPPED_BY_OPERATOR: OFF (marker ...)`, and `DEAD`
if a lab process is alive while the marker exists. The lab and the .vbs are not
deleted; deleting the marker switches the lab back on.

**Evidence.** `.cmd` run by hand: `OFF: always_on_lab_OFF marker present, lab not
started` (rc 0); `python -m scripts.always_on_lab --ticks 1`: `OFF: ... the lab
does not start`; live probe: `always_on_lab: OFF (marker always_on_lab_OFF, since
2026-10-02T12:38:15+00:00)`.

### 6. Learning report and the zero-order sim

**Cause (report).** `sim_run.learning_report_at_exit()` swallowed the exception
into the sim's logger; session ad32603783de COMPLETED at 2026-09-29T23:56Z, and
`report_2026-09-29.json` stayed at its 15:27Z version (the earlier STOPPED exit of
the same session). Re-running it today succeeded, so the exit-time failure was
transient; the defect is that it left no trace. `learn_rota` never looked.

**Fix.** Every attempt is a row in `learning_reports/report_runs.jsonl` (ok or
FAILED with the exception). `task_keeper catchup` calls
`daily_learning_report.ensure_session_reports()`: any session finished in the last
4 days with no ok row and no report generated after it ended gets its report (or a
FAILED row). `learn_rota` health names a finished session without a report, or a
FAILED newest row.

**Evidence.** `report_2026-09-29.{json,md}` regenerated (`generated_utc
2026-10-02T12:45:22Z`) with its closing lines; row recorded; the catch-up then
finds nothing owed. Live `learn_rota` is STALE for a real, different reason:
`survivorship_audit computed on bars through 2026-09-28 while the panel reaches
2026-10-01`.

**Zero orders: NOT the mandate.** Across all 91 cycles: `n_orders 0`,
`mandate_gates_orders: false`, `exploit_acting: false` (verdict
`MEASURED_NEGATIVE`), `probe_acting: true` with the PROBE book already held (10
positions, 19.7-19.9% invested against `PROBE_GROSS_CAP` 0.20). The plan receipt
now carries `why_zero_orders`, `mandate_capital_bases` and
`mandate_disagreements`. The two numbers that disagree: the contract is sized on
**$40,000** (`IC_CAPITAL_LEVELS` middle level, the IPS) while PC-PAPER broker
equity is **$997,811-$999,276** (`max(IC_CAPITAL_LEVELS)` $1,000,000); plus
per-name caps 2% / 3% / 10% / 12%. That is an unconfirmed mandate, not a config
drift, and it gates nothing; left for the owner. No cap, stop or size changed.

### 7. OpenClaw gateway "no operator scope"

**Cause.** `openclaw gateway status` prints `Capability:
connected-no-operator-scope`: the STATUS CLI's own probe connects without an
operator-scoped token, so it cannot read the deep status RPCs. It says nothing
about what the gateway serves; the reader read 105 pages OK in the last hour
through it.

**Fix.** The probe now reads the reader's own evidence
(`dowjones/reader_status.json` `t`, `pages_ok_60m`): ALIVE "capability PROVEN by
the reader" when an OK page is less than an hour old, STALE "capability UNPROVEN"
otherwise. **Live:** `ALIVE gateway running, probe ok; the status CLI has no
operator scope (connected-no-operator-scope), capability PROVEN by the reader:
105 pages OK in 60 min`.

### 8. docs/PAPER_ACCOUNTS.md

**Cause.** A `--no-broker` pass on a day with no broker receipt wrote the doc
(`write_doc = date_copy and (with_broker or not wide.exists())`).

**Fix.** `paper_accounts_roi.doc_drop_check()` parses the doc's "Priced and
broker accounts" table and REFUSES a rewrite that drops an account listed by the
doc on disk OR by `paper_accounts/doc_accounts_high_water.json` (seeded from
`3204eb4d`: 47 accounts incl. hack1-6 and PC-PAPER). `--allow-drop` retires
accounts deliberately. The refusal is printed, in the receipt, in the child
summary and as a DEGRADED line on the daily pass.

## Daily pass, hand run

`python -m scripts.daily_pass --force` (the lab's 11:58 run already held the
date), 20:38 → 22:01 local, receipt
`night_factory_2026-10-02/daily_pass_2026-10-02_run02.json`:
**12 ok / 2 nothing-to-do / 0 refused / 0 error**, `degraded: []`
(`BARS_FRESH: newest=2026-10-01 sessions_old=0`; 7 broker rows).

- `grade_forecasts`: **674 newly resolved** (new rows since the last run > 0);
  18,457 of 33,014 records now carry an outcome; 2 wait on a bar; 14,419 not yet
  due. Receipt `grade_forecasts_2026-10-02.json`.
- `grade_books`: 319 books OK, bars through 2026-10-01. Shadow books graded:
  SHADOW_BAYES_v0 / v1 and CRSP_BLEND_v0 at session 3 of 21 (`READ_NOT_DUE`: reported,
  not read); SHADOW_NEWS_v0 PENDING (both trusts 0, tilt zero by construction).
- `paper_accounts`: **broker-priced receipt** `paper_accounts/roi_2026-10-02.json`
  (`with_broker: true`, 7 broker accounts attempted, 367 rows). hack1 −8.32%,
  hack2 +1.14%, hack4 −20.52%, hack5 −4.75%, hack6 −18.32% (own windows), PC-PAPER
  +0.14% ($1,001,358), hack3 CREDENTIAL_INVALID (retired 401). docs/PAPER_ACCOUNTS.md
  regenerated WITH the fleet and PC-PAPER.
- Health (non-ALIVE rows worth the owner's eye): `book_grader` says the paper
  BOOKS (book_cadence) are graded through 09-28; `learn_rota` survivorship audit on
  09-28 bars; `sim_session` DEAD (no sim since ad32603783de; the IIF1 launcher
  refused 10-02's window); `decision_contract` n_considered static for ≥5 contracts.
- Scoreboard: 100% benchmark / 0% exploit / 0% explore, "nothing learned since
  then has moved a dollar".

Post-run refinement (code only, the running pass had loaded the earlier version):
the broker-error matcher now also catches `CREDENTIAL_INVALID`/`FAILED`/`STALE`,
and `config.PAPER_ACCOUNTS_RETIRED_UNREADABLE = ("hack3",)` keeps a retired key
from making the DEGRADED line permanently red (a gate that cannot go green).

## Files

Code: `scripts/pull_bars_refresh.py`, `backend/services/bars_health.py` (new),
`backend/services/alerts.py`, `scripts/alert_pass.py`, `scripts/daily_pass.py`,
`scripts/paper_accounts_roi.py`, `scripts/hyp_lab.py`, `scripts/always_on_lab.py`,
`scripts/night_run_until.py`, `backend/services/system_health.py`,
`scripts/daily_learning_report.py`, `scripts/sim_run.py`, `scripts/task_keeper.py`
(new), `backend/config.py` (three settings appended), tests
`backend/tests/test_automation_fixes_2026_10_02.py` (new) and one expectation in
`backend/tests/test_daily_pass.py` (the argv is no longer `--no-broker`).
Runtime (untracked): `always_on_lab.cmd`, `always_on_lab_OFF`,
`hyp_lab/run_nightly.cmd`, `dowjones/supervisor_run.cmd`, `task_keeper/`,
`paper_accounts/doc_accounts_high_water.json`,
`learning_reports/report_runs.jsonl`.

## WHAT WORKS

- One bad ticker can no longer freeze every panel: it is dropped, named, and the
  other 4,929 advance.
- A stale panel is the first line of the daily pass and of the alert receipt.
- OFF means off for the lab, across days and boots, and the health row says so.
- A missed daily trigger is caught up within two hours of the PC being awake, by
  the task's own action, so its STOP file still binds.
- The reader has a relaunch path that cannot start a second supervisor.

## WHAT DOES NOT

- nn_lab refuses every night until the owner chooses how a re-adjusted history may
  change stored grid membership (`TableShrink`, EQBK/THFF).
- Wake timers are on for only part of the local power settings; a PC asleep outside them still misses its trigger
  until it wakes (then the catch-up runs it).
- The mandate stays UNRECONCILED ($40,000 vs ~$1,000,000) until the owner confirms
  one capital base; the sim places nothing new while EXPLOIT is MEASURED_NEGATIVE
  and PROBE is full.
- `survivorship_audit` (learn rota) still reads bars through 09-28 until its next
  run.

## HIGHEST-EV EXPERIMENT

Let the repaired graders run one full session (10-02 close → 10-05) untouched and
read the first DEGRADED-free daily pass: if `grade_forecasts` adds rows,
`paper_accounts` prints all seven broker accounts and `learn_rota` turns ALIVE,
the machine is measuring again and the next research session can trust the
leaderboard it reads. Cost $0, and it decides whether the evening's fixes hold
across a real sleep/wake cycle.
