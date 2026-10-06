# Review: C8, progress-aware health (2026-10-07)

Reviewer: Opus 5.5, adversarial. Read-only. Evidence: one `python -m scripts.health_probe --no-write --json` run (generated 2026-10-06T23:05Z), the C8 and health test files, read-only `schtasks` queries, and replays of `task_receipts.judge()` against real receipts from the BRK-B blackout (09-30 to 10-02) and against synthetic receipts in a temp dir. Nothing was edited, registered, or deleted.

## VERDICT

**CONDITIONAL PASS, 58/100.** The architecture is right. A task is now judged by the receipt it writes, not by `cmd.exe`'s exit code; every task has a named reader; and UNKNOWN is no longer the default. That is a real step.

The readers are the weak part. Too many of them treat a fresh stamp as "progressing" without reading the producer's own failure field. I replayed the BRK-B blackout and `task:AegisDailyPass` read **ALIVE_PROGRESSING on all three days**. A contest desk that never runs reads **ALIVE_IDLE_EXPECTED indefinitely**. A fleet-manager pass in which every account returns 401 reads **ALIVE_PROGRESSING**. The straddle row goes **STALE every night and weekend** for no reason. C8 removed "UNKNOWN by omission" and replaced it, in at least five readers, with "ALIVE by omission".

Do not merge to main until findings F1 to F4 are fixed. Each fix is one or two lines plus a test.

## Tests (attack 7)

```
AEGIS_PERSONAL_MODE=0 AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/test_task_receipts_c8.py \
    backend/tests/test_health*.py backend/tests/test_system_health*.py -q
158 passed, 1 warning in 103.08s   exit=0
```

Mocks in `test_task_receipts_c8.py`:
- `_ctx()` builds a `ProbeCtx` on `tmp_path`, with `run=lambda argv,t: (None,"not installed")`, `pid_cmdline=lambda pid: None`, and `terminal_repo` pointing at a missing directory.
- `monkeypatch.setattr(SH, "_schtasks", ...)` supplies a fake scheduler table.
- The bridge test redirects `HEARTBEAT` to `tmp_path`.
- No test feeds a reader a receipt that **failed while looking healthy**: a `refused` daily-pass step, an all-ERROR fleet pass, a straddle `state: "REFUSED: ..."`, or a never-run task after its first due day. The suite therefore pins the happy paths and the obvious refusals only. Every one of F1 to F5 passes the current suite.

The repo-scan guard (`_task_names_in_source`) greps lines, not the AST:
- **Too strict:** any `.py` line under `scripts/`, `backend/services/` or `nn_lab/` that contains `TaskName|/TN|TASK|Register-ScheduledTask|schtasks` and a quoted `'AegisX'` must have a receipt reader, including a docstring line that explains a retired or hypothetical task. This is the CLAUDE.md protocol item 10 failure shape: the next reader deletes the explanation to turn the suite green.
- **Too lax:** it reads `.py` only. `backend/data/optimus/local_pc/network_resume.ps1` names `AegisNetworkResume`, which the scan cannot see. At runtime that task would show as a visible UNKNOWN row, so the cost is small.
- **Blind spot in the scheduler read:** `_schtasks` keeps only names starting with `Aegis`. The `OpenClaw Gateway` task, which is running and owned by this stack, is invisible to `task:*` rows. It is covered only by the separate `openclaw_gateway` probe.

## Findings

### F1. HIGH: the daily pass reads ALIVE_PROGRESSING through the BRK-B blackout (attack 1, attack 8)
`r_daily_pass` counts only `error`/`timeout` steps as bad. `refused`, `skipped` and `nothing_to_do` all read OK. Replaying `judge()` on the real receipts:

```
2026-09-30T23:00Z ALIVE_PROGRESSING  daily_pass 2026-09-30: 9 ok / 4 nothing-to-do / 1 refused ...
2026-10-01T23:00Z ALIVE_PROGRESSING  daily_pass 2026-10-01: 9 ok / 4 nothing-to-do / 1 refused ...
2026-10-02T09:00Z ALIVE_PROGRESSING  daily_pass 2026-10-02: 9 ok / 4 nothing-to-do / 1 refused ...
progress hash n_same = 1 each day (the substance moved every day)
```

The refused step was `bars_refresh`, which is the whole blackout. `grade_forecasts` reported `nothing_to_do` three days running while zero forecasts were graded. The headline string already printed "1 refused", and the state ignored it. The same-hash rule could not help because the steps' contents change daily. Fix: a `refused` step makes the reading DEGRADED, naming the step. A `nothing_to_do` on a grading step while due rows exist should also count.

### F2. HIGH: a contest desk that never runs reads ALIVE_IDLE_EXPECTED indefinitely
`r_contest_desk`: `if first and today < first: idle "not yet due"`, `elif never: idle "the scheduler says it has never run"`. The second branch is wrong. After the first sheet day, a task that has never run is the failure itself, yet it is declared idle. Replay on an empty receipt folder with `Last Result 267011`:

```
2026-10-08  ALIVE_IDLE_EXPECTED  not yet due: first sheet day 2026-10-09        (correct)
2026-10-13  ALIVE_IDLE_EXPECTED  the scheduler says it has never run (0x41303)  (WRONG)
2026-11-20  ALIVE_IDLE_EXPECTED  the scheduler says it has never run (0x41303)  (WRONG)
```

The same branch fires when `contest_calendar` fails to import (`first is None`). This is the live contest task and goes live on 2026-10-09. Fix: never-run on or after `first` is STALE (DEAD if unregistered). Drop the `never` idle branch.

### F3. HIGH: an all-accounts-ERROR fleet manager pass reads ALIVE_PROGRESSING
`_fleet_pass` reads a top-level `status`. Fleet-manager run receipts do not have one: 21 of 21 runs on disk have `status: None`. Per-account failures are written as `{"role":..,"status":"ERROR","why":..}` (`scripts/fleet_manager_run.py:1113`). Replay with five accounts all `ERROR 401` gives `ALIVE_PROGRESSING`. `r_fleet_daily` already does this check correctly with per-account status and the retired-role excuse. Fix: reuse that logic.

### F4. HIGH: the straddle reader ignores its own REFUSED state and goes falsely STALE every night
- The producer writes `state: "REFUSED: bars newest ... is not the previous session"` (the 10-01 blackout receipt `pass_20261001T174630Z.json` says exactly this), `"STOPPED: STOP file present"`, and `grade.error`. The reader parses none of these. Replay: REFUSED state gives **ALIVE_PROGRESSING**.
- The idle path reads `window.in_window` from the newest receipt. Out-of-window passes write nothing (all `pass_*` on disk are in-window), so the newest receipt is always an in-window one. With a 0.5 h cadence and `session_only=False`, the row goes STALE about 38 min after 15:30 ET, every evening and all weekend. **Live probe tonight: `task:AegisStraddleForward STALE newest receipt 3.8h old (allowed 38m)`.** A row that is red every night trains people to skip red lines, the same lesson as the never-green gate. Fix: parse the `state` prefix (REFUSED/STOPPED/IDLE). Mark the task session-only with its 10:45 to 15:30 ET window, so the allowed age runs from the last in-window slot.

### F5. MEDIUM: other readers that ignore the producer's failure field (attack 1)
- `r_world_digest` ignores `sections_error`, `spend.failed` and `n_items == 0`. A digest with zero items and failed LLM calls reads ALIVE_PROGRESSING, and only the hash rule might catch it, two probes later.
- `r_alerts` ignores the receipt's own `state` and `bars_health.state`. During the blackout, `alert_pass_20261001T153741Z` said `state OK` with no `bars_health`. The hash rule is also switched off (`hash_off`), so alerts can never go stale on content.
- `r_rehearsal` reads only `error`. Its substance includes `day`, so the hash moves every day by construction (see F6).
- `r_sim_owner`: `outside_window` reads **ALIVE_PROGRESSING**, though it should be ALIVE_IDLE_EXPECTED. Only `refused`/`paused`/`stopped_by_operator` are mapped. Any future action such as `error` defaults to OK.
- `r_analyst_pull` checks only `action == "refused"` in `analyst.jsonl`. A `failed` row (rc != 0, or the 150-min timeout) is ignored, and the previous good `analyst_pull_<day>.json` keeps the row ALIVE_PROGRESSING for up to 210 h. Today the row reads ALIVE_PROGRESSING while `AegisAnalystPull` has never run (`Last Result 267011`). The receipt came from a manual pull, so the row certifies data freshness, not that the task is alive.

### F6. MEDIUM: the substance hash strips too much and too little at the same time (attack 2)
`_VOLATILE` is an unanchored substring regex. Keys stripped from tonight's real receipts include:
- `stock_page`, `coverage_rate`, `stage` (match "age")
- `sentiment_news`, `sentiment_social` (match "time")
- `outcome` (matches "utc")
- `n_blocks` (matches "lock")
- `rows_written`, `written` (match "written")

`rows_written` and `outcome` are progress, not clocks, so removing them pushes the hash toward a **false "same output"**.

In the other direction, the rule strips keys but never values. Day strings, dated file names and sheet hashes stay in the substance, which makes several series **unique by construction**:
- rehearsal: `day`, `sheet.sha256`
- nn_lab: `receipt` filename
- analyst panel / pull: `p.name`
- daily pass: `receipt_path`

Those series can never trip the rule even when their content is frozen. The contest rehearsal graded `relative_0bps 0.023417` identically on 10-03, 10-04 and 10-05, and the hash moved each day.

On the false-STALE question: the fleet manager with no orders and the contest sheet with no reporters will **not** go falsely STALE, because prices and the day always move. The `idle_reason` mechanism exists, but only as hard-coded reader logic: `contest_desk`, `straddle`, and session-only tasks. A producer has no way to declare "legitimately identical today" in its receipt.

The rule also counts **probes**, not time: `first_seen` is the probe's clock. With `always_on_lab` OFF, the only scheduled caller is the daily pass, about once a day, so detection latency is about one day regardless of cadence. Fix: anchor the regex (`^(.*_)?(utc|at|ts|stamp|run_id|pid|elapsed_s|seconds)$`). Hash a declared progress field per reader (`page_loads_total`, `n_items`, `rows_added`, `n_graded`) rather than the whole receipt.

### F7. MEDIUM: DEGRADED-as-STALE does not hide DEAD, but two other paths soften red (attack 5)
- An unregistered task whose newest receipt is an **old refusal** returns `STALE` (the "OLD refusal" branch in `judge`), not `DEAD`, even though nothing will write again.
- A task whose scheduler state is `Disabled` returns `STOPPED_BY_OPERATOR` **before the receipt is read** and never ages. Replay: a Disabled `AegisDailyPass` with no receipt at all gives `STOPPED_BY_OPERATOR`, which is not counted in `exit_code`. Disabled is not proof that the operator did it. A crash script, an agent, or a Windows policy can disable a task. It needs an age bound or a declared marker, as `always_on_lab_OFF` has.

Consumers:
- `daily_pass.step_health` uses `!= "ALIVE"`, which is correct. It copies every non-ALIVE row, including REFUSED.
- The Telegram `health_answer` lists only `DEAD` and `STALE` by name. REFUSED rows (nn_lab, the contest live gate, which C8 surfaced for the first time) appear only as a count.
- `aegis_verified_state` (Optimus MCP) reads Railway `/api/health/full` and **never sees PC task rows**. C8's states do not reach the session-start protocol.
- `test_health_full` tests the Railway endpoint. Unaffected.

### F8. LOW: the remaining UNKNOWN rows are honest, but two are permanent (attack 4)
Tonight shows 3 UNKNOWN. `learn_rota` is now STALE with a real cause.
- **`railway_fleet`**: "CLI linked to aat-loop-hack3". The Railway loops were stopped on purpose (S60), and `FLEET_SERVICES` still lists hack1 to hack6. This row can never go ALIVE. It should be `STOPPED_BY_OPERATOR` with the stop decision cited, or be removed.
- **`social:reddit`**: `REDDIT_KEYS_ABSENT`. A key that was never provisioned is a permanent, declared absence (REFUSED/NOT_PROVISIONED), not an unknown.
- **`u_plan`**: "no pc_book/<day>/intended_book.json" is evidence of a missing plan, not missing evidence. It should be session-aware: idle off-session, STALE in-session.

None of these are C8 task rows, but the note's claim "each names its missing evidence" is true and incomplete: two of them name a cause that will never change.

### F9. LOW: owners verified, with caveats (attack 6)
`schtasks /Query`:
- `AegisBrainRefresh`: Daily 05:45, last run 2026-10-07 05:45, Last Result 0. `brain.jsonl` shows `ok n_ok 10 n_fail 0`. Matches the note.
- `AegisAnalystPull`: Weekly SUN 10:00, never run (267011), next run 2026-10-11 10:00. Matches the note.

If `../optimus` or its `.venv` is absent, `run_brain_refresh` writes `action: refused` with a reason and `r_brain` reads REFUSED. That behaviour is correct and tested. `refresh_aegis.py` returns 1 on any `[FAIL]`, so partial failure becomes `failed`, which maps to DEGRADED. Correct.

`analyst_gate` uses `SH.in_session_hours`, which is zoneinfo `America/New_York` (DST-correct) plus `exchange_calendars` XNYS holidays. Two caveats:
- The gate can essentially never fire from the schedule. Sunday 10:00 HKT is Saturday 22:00 ET, so it guards only catch-up and manual runs. That is acceptable, but the refusal path is mostly theoretical.
- If `exchange_calendars` is missing, `_sessions` silently falls back to `WEEKDAY_APPROX`. `_today_idle`/`_non_session_days` then treat Thanksgiving as a session and throw the label away. Early closes (13:00 ET) are not modelled.

### F10. LOW: wording and housekeeping
- The `decision_contract` detail opens with "a static candidate input" and only later says "CAUSE: NOT a stale file". `accrual_canary` truncates before the cause, so it still reads "a static candidate". Lead with the cause.
- Coarse STALE on a policy outcome (2 of 25 eligible) is a permanent red line that is not a health failure.
- `AegisPublicFlow` (C16) reappeared as **DEAD** because it is unregistered, so the note's "DEAD 1 to 0" no longer holds.
- `AegisDataCatalog` registration and `AegisWRDSPullNight` deletion are still owed. Both are correctly DEGRADED.

## Attack 3: idle windows
The declaration lives in code: `TaskSpec.session_only` plus per-reader `idle_reason`. US holidays are handled through `exchange_calendars`, except under the silent weekday fallback in F9. Tasks that should run on weekends (digest, alerts, catch-up, reader) are **not** `session_only`, so they are never idle-expected by mistake. The failures are in the opposite direction: a windowed task is not declared as windowed (straddle, F4), and "never ran" is declared idle (contest desk, F2).

## Attack 8: the failure the probe would still miss
**The BRK-B three-day grader stall**, at the task layer. With C8, `task:AegisDailyPass`, `task:AegisStraddleForward` and `task:AegisAlerts` would all have read ALIVE_PROGRESSING through 09-30 to 10-02. Replayed for the daily pass; F4 and F5 cover the other two.

The only row that goes red is the older `bars_panel` probe, after its 2-session limit. On a holiday-adjacent weekend that is day 3 or later. The task table, which is C8's whole contribution, would have contradicted it.

Delivery has not changed either. With the lab OFF, the probe runs once a day, inside the daily pass it is judging, and nothing pushes a red row to the owner. The Telegram brief is pull-only and omits REFUSED by name. The S61 lesson, "all LOUD in receipts, none READ", is half-answered.

The other four:
- The 57 h dead reader: caught, via tick age.
- The week-dead sim: caught, via `sim_session`.
- The nn_lab refused nights: caught as REFUSED, but not named on Telegram.
- The 584-process leak: caught by C14's `process_census`, not C8.

## Three things I would have done instead
1. **One producer contract instead of 21 bespoke readers.** Every scheduled job ends by writing one line, `{stamp, status: OK|REFUSED|DEGRADED|IDLE, reason, progress: {field: value}}`, through a shared helper. `nightly_receipt_contract` is already the template. The reader becomes generic. "Same output" compares the declared `progress` dict, not a regex-stripped receipt. Idle becomes a status the producer writes ("IDLE: outside 10:45-15:30 ET"), not a guess the health code makes. F1, F3, F4, F5 and F6 disappear by construction.
2. **Test every reader against its producer's worst real receipt.** Commit the 09-30 daily pass, the 10-01 straddle REFUSED pass, and a synthetic all-ERROR fleet run as fixtures, and assert that none reads ALIVE. Also add a property test: for every reader, a receipt whose status field says REFUSED, ERROR or STOPPED never maps to ALIVE_*. That would have caught F1 to F4 the same night.
3. **Give the probe its own owner and a push.** Register an `AegisHealthProbe` task every 2 h, independent of the daily pass it judges. It sends Telegram a diff only when a row changes from ALIVE to anything else (including REFUSED), with a daily all-clear. Have the session-start surface (`session_briefing` or `aegis_verified_state`) read the newest PC health receipt and its age, so the PC's state is part of protocol step 1.

## Score: 58 / 100
- Concept and plumbing: +30 (receipt-first judging, fine state beside coarse verdict, a row for every unregistered declared task, retired task named with its delete command, honest UNKNOWN reasons)
- Owners registered correctly, refusal paths written: +10
- Tests green, with a repo-scan guard: +8 (the guard is line-grep and `.py`-only)
- Bridge heartbeat and decision_contract cause: +10
- Deductions: F1, F2, F3 and F4 are each a failure that reads green or a false red, all reproducible today. The hash rule is mostly inert on the series that matter. REFUSED is not named on the operator's surface.
