# Progress-aware health (chunk C8), 2026-10-06 night

**RESULT IMPROVEMENT: NONE** (this is plumbing: it changes what the machine can SEE, not what it earns).
**UNKNOWN `task:*` rows: 17 → 0.** `optimus_brain`: STALE 23.4 d → ALIVE (refreshed by its new owner).

## Before / after (same probe, same machine, about two hours apart)

| | DEAD | STALE | REFUSED | UNKNOWN | STOPPED | ALIVE | rows |
|---|---|---|---|---|---|---|---|
| before, `health_20261006T153238Z.json` | 1 | 15 | 0 | 17 | 13 | 17 | 63 |
| after, `health_20261006T175305Z.json` | 0 | 11 | 0 | 4 | 13 | 42 | 73 |

`health_20261006T160857Z.json` was a partial run (`--only`, two rows) and is not a baseline.
The before-DEAD row was `sim_session`. C2's sim owner fixed it, not this chunk.

The fine states in the after run: ALIVE_PROGRESSING 18, ALIVE_IDLE_EXPECTED 2, DEGRADED 3,
STALE 8, UNKNOWN 4, STOPPED_BY_OPERATOR 13, ALIVE 22. The plain ALIVE rows come from probes that
still return only the coarse verdict.

**Task rows after (21):** 18 ALIVE_PROGRESSING, 1 ALIVE_IDLE_EXPECTED (`AegisContestDesk`: its first
live sheet day is 2026-10-09), 2 DEGRADED:
- `AegisDataCatalog`: the receipt is fresh, but no scheduled task has that name, so nothing writes
  the next one. C10 printed the registration in `task_keeper register` and did not run it.
- `AegisWRDSPullNight`: a retired one-shot from 2026-08-21. Delete it with
  `schtasks /Delete /TN AegisWRDSPullNight /F`. Not deleted by this chunk.

The four remaining UNKNOWN rows are not task rows: `learn_rota`, `u_plan`, `railway_fleet` and
`social:reddit`. Each one names its missing evidence.

## What changed

1. **`task:*` rows read the job's receipt, never schtasks' Last Result.** The scheduler is read only
   for three things: which tasks exist, whether one is Disabled, and whether it has ever run
   (0x41303). `backend/services/task_receipts.py` maps every task to a reader in `TASK_RECEIPT`.
   The full list:
   daily pass → `daily_pass_<d>.json` step stamps · IIF1 → the `iif1_night` probe ·
   nn_lab → `nn_lab.health_contract()` · sim owner → `sim/owner.jsonl` · catalog →
   `data_catalog/catalog_*.json` · rehearsal → `contest/rehearsal/runs.jsonl` · contest desk →
   `contest/live/runs.jsonl` or `contest/live/refusals/live_gate_*.json` (REFUSED with reasons) ·
   hyp_lab → `hyp_lab/receipts/nightly_*.json` · world digest → `digest/world_digest_*.json` ·
   alerts → `alerts/receipts/` · straddle → `straddle_forward/runs/` · fleet open/preclose →
   `fleet_manager/runs/` by `pass` · fleet daily → `fleet_daily/fleet_*.json` (hack3 excused by
   `config.PAPER_ACCOUNTS_RETIRED_UNREADABLE`, and named) · reader → supervisor `tick` rows ·
   catch-up → `task_keeper/keeper.jsonl` · telegram → the `telegram_agent` probe · analyst panel →
   the terminal repo's `state/research/analyst_panel/<date>.jsonl` (UNKNOWN with a reason if that
   repo is absent) · analyst pull → `analyst/analyst_pull_<day>.json` or `task_keeper/analyst.jsonl` ·
   brain refresh → `task_keeper/brain.jsonl`.
   Two names are mapped but `registered_only`, so they produce a row only if someone registers them:
   `AegisAlwaysOnLab` (started from a Startup script) and `AegisNightPreOpen` (a printed command
   whose sentinel writes NO receipt).
2. **States.** The full set is ALIVE_PROGRESSING / ALIVE_IDLE_EXPECTED / DEGRADED / STALE / REFUSED /
   DEAD / UNKNOWN / STOPPED_BY_OPERATOR. Each sits beside a coarse `verdict` (ALIVE / STALE /
   REFUSED / DEAD / UNKNOWN / STOPPED), so every existing consumer keeps working: the daily pass
   `!= "ALIVE"` check, the Telegram brief's DEAD/STALE filter, and `test_health_full`. DEGRADED maps
   to STALE, which is red. Rows gain `state`, and receipts gain `state_counts`.
3. **Progress contract.** Each receipt series records a SUBSTANCE hash in `health/_state.json →
   progress`: the receipt with its stamps and ids removed. The series reads STALE "same output for
   X h" when the same hash is seen in at least `HEALTH_PROGRESS_SAME_HASH_PROBES` (2) probes, for
   longer than the allowed age, with no declared idle reason. Cadences live in
   `config.HEALTH_TASK_CADENCE_H`. Session-only tasks get 24 h per non-XNYS day and read
   ALIVE_IDLE_EXPECTED on a non-session day. Four series switch the hash rule off and say why on the
   row: the sim owner, catch-up and alerts (their output is legitimately constant), and the brain
   refresh (its page's stamp is the `optimus_brain` row).
4. **OpenClaw API bridge heartbeat.** `scripts/openclaw_api_bridge.py` atomically rewrites
   `openclaw_api_bridge/heartbeat.json` on server start and on every tool call. A refused route is
   recorded apart from an error. The probe reads ALIVE_PROGRESSING when a call came within 7 days,
   ALIVE_IDLE_EXPECTED when no call came (the agent calls it on demand), DEGRADED when the last call
   errored, and UNKNOWN when there is no heartbeat at all. Tonight's row says "server started, no call
   yet": the gateway spawned the bridge, and no agent call has happened since.
5. **`decision_contract` names its cause.** The static `n_considered` is now marked DEGRADED with:
   "NOT a stale file -- the candidate set is fresh (25 candidates, 0.0 d old); only 2 of 25 pass the
   eligibility gate (excluded: 19 ranking score <= 0, 4 NO_EVIDENCE)". A genuinely old candidate
   file still says so.

## Owners added

| task | schedule | runs | refuses when |
|---|---|---|---|
| `AegisBrainRefresh` | daily 05:45 HKT | `task_keeper brain` → `tools/refresh_aegis.py` under the Optimus venv | repo or its venv is absent (REFUSED, reason in `brain.jsonl`) |
| `AegisAnalystPull` | weekly Sunday 10:00 HKT | `task_keeper analyst` → `pull_analyst_targets --universe bars` (150-min box) | the US regular session is open |

Both are also in `task_keeper.CATCHUP_TASKS`. They were registered with
`python -m scripts.task_keeper register-owners --apply`, which prints the exact
`Register-ScheduledTask` PowerShell first. `AegisBrainRefresh` was then fired once by name: 10
ingests ok, 0 failed, and the brain page regenerated.

**Not duplicated:** the Dow Jones feeds. C7 made them a `daily_pass` step, so they have no task of
their own.

## Still owed

- Register `AegisDataCatalog` (C10's printed registration): `python -m scripts.task_keeper register`.
- Delete `AegisWRDSPullNight` (command above).
- nn_lab refusals now show on `task:AegisNNLabNightly` as REFUSED. Contest live-gate refusals now
  show on `task:AegisContestDesk` as REFUSED with reasons. Both reach the morning report through
  the daily pass health step, which copies every non-ALIVE row.
- `daily_pass.step_health` still counts `verdict != "ALIVE"`. That is correct under the coarse
  verdict, but it does not print the fine states yet. That file is C7's tonight.

## Review fixes (2026-10-07, `docs/reviews/REVIEW_2026-10-07_C8_PROGRESS_AWARE_HEALTH.md`, 58/100)

The first version replaced "UNKNOWN by omission" with "ALIVE by omission" in five readers. Replayed on
the BRK-B blackout, the daily pass read ALIVE_PROGRESSING three days running. What changed:

- **One status mapping** (`task_receipts.map_status` / `receipt_status`) that every reader calls.
  An unrecognised status word is DEGRADED, never OK. A parametrised property test feeds every
  declared task a fresh REFUSED / DEGRADED / STOPPED / DEAD reading and asserts that none of them
  reads ALIVE_*.
- **Worst real receipts committed as fixtures** (`backend/tests/fixtures/c8/`, trimmed, machine
  paths scrubbed, re-dated to today in the tests). The 2026-09-30 daily pass now reads DEGRADED
  "bars_refresh=refused". The 2026-10-01 straddle pass now reads REFUSED. A synthetic all-ERROR
  fleet run reads DEAD, and a single ERROR reads DEGRADED (fleet daily and both fleet-manager
  passes share `accounts_status`). A grading step that did `nothing_to_do` while due rows wait
  reads DEGRADED.
- **Contest desk:** never-run after its first sheet day (2026-10-09) reads STALE (DEAD if
  unregistered). A calendar import failure reads UNKNOWN with the exception class.
- **Straddle:** session-only, with its window read from `STRADDLE_FWD_ENTRY_START/END_ET`. It
  reads idle-expected after the window when the last window produced, and STALE when it did not.
- **Other readers:**
  - the world digest reads zero items, failed LLM calls and `sections_error`;
  - alerts read their own `state` and `bars_health`;
  - the sim owner's `outside_window` reads idle-expected;
  - a failed analyst pull reads REFUSED, and a receipt from a MANUAL pull before the task's first
    run says so.
- **Substance hash:** exact volatile key names plus an anchored suffix rule. Progress keys such as
  `rows_written`, `outcome` and `coverage_rate` are kept. ISO dates, compact stamps and hex ids are
  normalised inside values. Readers declare progress fields (the rehearsal hashes
  `grade.relative_0bps`, `grade.n_closed`, so 10-03, 10-04 and 10-05 hash identical). A producer
  may write `identical_ok: true` with a reason.
- **Registration states:**
  - an unregistered task whose last receipt is an old refusal reads DEAD;
  - a Disabled task reads STALE unless the owner wrote `task_keeper/disabled/<name>`;
  - the Telegram brief names REFUSED rows;
  - `AegisPublicFlow` reads UNREGISTERED (coarse STOPPED_BY_OPERATOR) until its review passes.
- **Non-task rows:** `railway_fleet` and `social:reddit` read STOPPED_BY_OPERATOR with their
  reasons (`config.RAILWAY_FLEET_STOPPED_REASON`; no key provisioned). `u_plan` reads DEGRADED
  "no plan written for session X". `decision_contract` and `accrual_canary` lead with the cause.
- **Repo scan:** reads task names structurally (AST assignments to TASK-named variables, and
  `/TN` / `-TaskName` inside non-docstring literals, plus `.ps1` files). `OpenClaw Gateway` is now
  read from the scheduler and has a row.

Probe after the fixes (`--no-write`, 2026-10-06 23:26 UTC): DEAD 0, STALE 12, REFUSED 0,
**UNKNOWN 0**, STOPPED_BY_OPERATOR 16, ALIVE 49. Task rows (22, including OpenClaw Gateway):
16 progressing, 4 idle-expected (analyst pull, contest desk, sim owner, straddle),
2 DEGRADED (`AegisDataCatalog` unregistered, `AegisWRDSPullNight` retired), 1 UNREGISTERED.
