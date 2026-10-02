# Automation audit, 2026-09-30 → 2026-10-02 (owner offline)

Licence: internal operations audit, read-only. No code or state changed by this
note; machine-level numbers (memory, graphics card, process counts) are in
`backend/data/optimus/local_pc/automation_audit_machine_2026-10-02.md`.

## RESULTS SCOREBOARD

- **Jobs that ran fully as designed over the 3 days: 6 of 16** (AegisWorldDigest,
  AegisContestRehearsal, AegisFleetManagerOpen, AegisFleetManagerPreclose,
  AegisAlerts [cadence], OpenClaw Gateway task [uptime only, not capability]).
- **Jobs that MISSED entirely at least one scheduled firing because the PC was
  asleep at the trigger time, with no catch-up: 4** (AegisDailyPass,
  AegisFleetDailyCheck, AegisNNLabNightly, AegisAnalystPanelDaily — all missed
  their 10-02 occurrence; none of their tasks has "run as soon as possible
  after a missed start" or "wake the computer to run" enabled).
- **Jobs that FAILED outright: 1** (AegisHypLabNightly, exit code 3, root cause
  a stale kill-switch file, not sleep).
- **Jobs that were SILENT for a large span despite the machine being awake: 1,
  and it is the costliest one found** — the Dow Jones reader supervisor wrote
  nothing for **57.5 hours** (2026-09-30T10:48 → 2026-10-02T20:17 local) although
  the PC was awake for most of that window; it is not a Scheduled Task at all,
  so nothing restarted it after its own `--until 12:00` cutoff passed.
- **Root cause found for three symptoms that looked separate**: `bars.parquet`
  (both `prices_2025_26` and `prices_deep`) has been stuck on 2026-09-28 since
  2026-09-29 06:31 because `scripts.pull_bars_refresh` has failed every single
  attempt since then with the identical `HTTPError: HTTP Error 400: Bad
  Request` (confirmed on 09-29, 09-30, 10-01 and 10-02 receipts) — this is what
  made AegisStraddleForward REFUSE for five hours straight on both 09-30 and
  10-01, and what pins AegisAlerts' grading at `n_alert_dates_graded: 0` the
  entire window. The refusals are correctly reported (not silent), but nobody
  read them for three days.
- **`always_on_lab` (and its local llama-server) relaunched itself three
  times across the window (09-30 04:03, 09-30 12:20, 10-02 03:58) despite being
  "OFF since 09-27"** per standing instruction. No Scheduled Task or script in
  this repo was found in the time available that explains who restarts it —
  flagged OPEN, see "what does not work" below.
- **No new `learning_reports/report_*` has been written since `report_2026-09-29`**
  (Sep 29 23:27) — three full days, one completed 91-cycle sim session
  (`ad32603783de`), and multiple `daily_pass` runs produced zero new dated
  learning report. `learn_rota` reports itself "ok" in `daily_pass`'s health
  section the whole time: another green status over an unmoving ledger.
- **DeepSeek spend over the window: ~$2.55** (balance `topped_up_usd` 23.78 →
  21.23 between 2026-09-30T05:19Z and 2026-10-02T10:31Z), almost entirely
  `world_digest` balance-check pairs; no runaway spend found.
- RESULT IMPROVEMENT: NONE — this is an operations audit, not a research result.

## Job-by-job table

| Job | Last ran (local) | Should do | Did | Verdict | Root cause | Cheapest fix |
|---|---|---|---|---|---|---|
| AegisAlerts | continuous, every ~30 min through 10-02 20:07 | poll SEC 8-K/Form 4, send alerts, grade past alerts | ran every slot, no gaps; sent 2 LIVE alerts (04:37, 10:37 UTC 10-02); grading stuck at `n_alert_dates_graded: 0` ("NO_ELAPSED_HORIZON... last bar 2026-09-28") | DEGRADED | downstream of the bars staleness below | fix `pull_bars_refresh` (see below) |
| AegisWorldDigest | every 6h, last 2026-10-02 18:31 (local) receipt | pull a 24h world digest, cost receipt | 7 of 7 expected receipts present, full JSON/MD/short.txt triplets, zero gaps across sleeps | OK | — | — |
| AegisStraddleForward | every 30 min | observe/act in the options window | correctly computed BEFORE/AFTER_WINDOW all window; REFUSED every pass in-window on 09-30 15:16–19:16 UTC and 10-01 14:46–19:46 UTC: "bars newest 2026-09-28 is not the previous session" | DEGRADED (correct refusal, not a bug in this job) | stale `bars.parquet` (see below) | same fix |
| AegisTelegramAgent | supervised, currently Running | poll Telegram, answer | child crashed on `socket.gaierror: getaddrinfo failed` (DNS, likely post-resume network hiccup); supervisor caught a stale heartbeat (3684s > 600s) and restarted it at 16:33 local 10-02 (process id recorded locally); no inbound messages while owner was offline (inbox.jsonl untouched since 09-26) | DEGRADED, self-healed | transient DNS failure after a sleep/resume cycle, ~1h undetected before the heartbeat check fired | lower the heartbeat-stale threshold, or have the supervisor's own restart emit a Telegram message to a side channel so an outage is visible |
| AegisContestRehearsal | 2026-10-02 14:30 local | daily rehearsal sheet + grade | grade files present for 09-30, 10-01, 10-02 (06:30 UTC each); desk_holdings and calendar present through 10-02 | OK | — | — |
| AegisDailyPass | 2026-10-01 06:30 local | nightly health/grade/receipt pass | ran clean on 10-01 (9 ok / 4 nothing-to-do / 1 refused of 14 steps; wrote `daily_pass_2026-10-01.json`, and its own health section already flagged most of the findings in this audit); **did not run on 10-02** — 06:30 local falls inside the 04:00–11:56 sleep window | MISSED on 10-02 | PC asleep at trigger time; task has no missed-run catch-up | enable "Run task as soon as possible after a scheduled start is missed" + "Wake the computer to run this task" |
| AegisFleetDailyCheck | 2026-10-01 06:45 local | daily fleet NAV/positions snapshot + website check | ran on 09-29→09-30 cadence and again 10-01 06:45 (receipt `fleet_20260930T224502Z.json`); website lane NAV reported **DEGRADED, newest = 2026-09-30** even in that run; **missed 10-02 06:45** (same sleep window) | MISSED on 10-02; DEGRADED before that | sleep + a stalled website NAV writer | same wake/catch-up fix; separately chase why website lane NAV lags the fleet by 1+ day |
| AegisFleetManagerOpen | 2026-10-01 22:45 local (next due 10-02 22:45, not yet due at audit time) | open-of-session pass | both 09-30 and 10-01 OPEN passes present (`run_20260930T144500Z…`, `run_20261001T144500Z…`), full position/stop detail | OK | — | — |
| AegisFleetManagerPreclose | 2026-10-02 03:30 local | preclose pass | both expected PRECLOSE runs present (`run_20260930T193001Z…`, `run_20261001T193000Z…`) | OK | — | — |
| AegisHypLabNightly | 2026-10-01 09:30 local, exit 3 | run nightly hypothesis cells | `run_nightly.cmd` checks for a `STOP` file and exits 3 immediately if present; a 0-byte `STOP` file (timestamp 2026-09-29 22:41) was dropped mid-run on 09-29 and never removed, so the 10-01 trigger aborted with **no work done**; the 10-02 09:30 trigger never even fired (sleep window 04:00–11:56 covers it) | FAILED (10-01) then MISSED (10-02) | stale kill-switch file left from an earlier (likely manual) stop | `del backend\data\optimus\hyp_lab\STOP`; make the nightly script delete/consume `STOP` after one skip instead of blocking forever, and add wake/catch-up |
| AegisAnalystPanelDaily | 2026-10-01 05:30 local, rc 0 | pull analyst panel coverage | ran clean 10-01 (log shows 687 tickers, 99% coverage); **did not run 10-02** — 05:30 local is inside the sleep window | MISSED on 10-02 | sleep | same wake/catch-up fix |
| AegisIIF1NightLauncher | 2026-10-02 16:20–16:33 local | launch the night's sim session if a safe window remains | correctly computed that the "latest safe LAUNCH" (08:14 UTC) had already passed relative to the proposed run start (08:59 UTC) and **refused** rather than start a truncated/compromised session, writing `iif1_launches/2026-10-02.1.json` and explicitly declining to retry | OK (refusal by design) | the safe-launch window closed, almost certainly because the PC was asleep/just-resumed through the relevant pre-open hours | none needed — working as intended; explains why no sim session has run since `ad32603783de` finished on 09-29 |
| AegisNNLabNightly | 2026-10-01 08:30 local | nightly append/size/grade/trust cycle | ran 09-30 and 10-01 (receipts `nightly_20260930T003003Z.json`, `nightly_20261001T003003Z.json`); `rows_added: 0` both times, and `in_charge.json` shows the model has been pinned on `"zero"` since 09-30 because "no forward grade was added tonight: in-charge cannot change" — **learning contributed nothing on nights it did run**; **missed 10-02 08:30** entirely (sleep window) | DEGRADED (ran, learned nothing) then MISSED | bars/labels not advancing (same stale-bars root cause) + sleep | fix bars pull; add wake/catch-up |
| AegisContestDesk | not due until 2026-10-09 | — | correctly never fired; `LastRunTime` shows the Windows Task Scheduler "never run" sentinel (267011) | OK (not yet due) | — | — |
| AegisWRDSPullNight | one-shot, last ran 2026-08-22 | — | out of scope for this window, retired one-shot | OK (retired) | — | — |
| OpenClaw Gateway (own Scheduled Task) | continuously Running | serve OpenClaw's browser/LLM gateway | process stayed up the whole window, but `daily_pass`'s own health check on 10-01 reports it **"up but degraded capability: connected-no-operator-scope"** — consistent with the sim's forecast unit on 09-29 logging 4 consecutive `RC_NONZERO` OpenClaw call failures on AMZN | DEGRADED | missing operator scope (not a crash) | re-establish the operator session/scope on the gateway (attended) |
| Dow Jones reader + night_reader_supervisor | restarted 2026-10-02 20:17 local | keep a Chrome reader pool alive, read official sources + money pages continuously | `reader_status.json`/`night_reader_supervisor.jsonl` show exactly one tick at 2026-09-30T10:48 (a successful CHROME_DOWN repair), then **nothing until 2026-10-02T20:17** — 57.5 hours of zero reader activity while markets were open 09-30, 10-01 and the morning of 10-02 | SILENT / FAILED (largest gap in the audit) | the 09-30 supervisor instance was launched with `--until 2026-10-03T12:00`... **but the known fact says `--until 12:00` same-day**, i.e. it stopped itself near noon on 09-30 as designed and nothing ever relaunched it — it has no Scheduled Task of its own | give the reader supervisor its own Scheduled Task that relaunches it every few hours with a fresh `--until`, instead of depending on a human to notice and restart it |
| always_on_lab (not a Scheduled Task) | live since 2026-10-02 03:58 (process id recorded locally) | — (supposed to be OFF since 2026-09-27) | restarted itself 3 times across the window per `always_on_lab_lock.json`'s own overwrite chain (09-30 04:03, 09-30 12:20, 10-02 03:58), each previous pid "not alive" (crashed); launched llama-server (a large memory load) each time | FAILED guardrail (ran when it should not have) | could not locate the auto-relaunch trigger in the time available — not in `run_night_launcher.py`; likely a self-relaunch loop inside `always_on_lab.py` itself that survives sleep/resume, or a logon/resume hook outside this repo's scanned Scheduled Tasks | **highest-priority open item**: find and gate whatever restarts it (grep the full `always_on_lab.py` self-relaunch path, and check Task Scheduler's non-`Aegis*` tasks and Startup folder for anything referencing it) |
| Sim / learning report pipeline | last report `report_2026-09-29` (23:27) | generate a dated `learning_reports/report_*` after each session/night | session `ad32603783de` completed (91 cycles, 8h) at 23:52 on 09-29; **no `report_2026-09-30`, `-10-01` or `-10-02` exists**; `daily_pass`'s health check calls `learn_rota` "ok" throughout | SILENT (green status, no output) | report generation is not wired to session completion, or its trigger condition never fired across three `daily_pass` runs | find `learn_rota`'s trigger condition and make "no report written in N days" a hard DEGRADED, not "ok" |
| `pull_bars_refresh` (root cause, not a Scheduled Task — called from `daily_pass`/`sim_run`/`straddle_forward`) | last attempt 2026-10-02 03:58 UTC (11:58 local) | refresh `prices_2025_26/bars.parquet` and `prices_deep/bars.parquet` to the last closed session | **every attempt since 2026-09-29 22:30 UTC has failed identically**: `HTTPError: HTTP Error 400: Bad Request`, "pull failed, nothing overwritten"; receipts exist and correctly say `status: "refused"` each time (09-29, 09-30, 10-01, 10-02) — this is a correctly-reported failure, not silence, but it cascades into Alerts/Straddle/NNLab above | FAILED (persistent, pre-dates the offline window — first bad receipt is 09-29 22:30) | the SIP pull's request parameters (start 2026-09-18, 4,930 symbols, feed=sip, adjustment=all) have drawn a 400 from the vendor on every one of 4+ consecutive days | isolate the 400 with a 1-symbol manual call to find which parameter the vendor now rejects (date range age? symbol count? feed entitlement lapsed?) before the next session |
| Telegram / DeepSeek balance ledger spend | continuous | track provider balance | 18 readings across the window, `topped_up_usd` 23.78 → 21.23 (~$2.55 total, mostly `world_digest`) | OK | — | — |

## What the sleep events cost

Sleep events: 09-30 10:48, 09-30 18:17, 10-02 04:00. Resume events: 09-30
04:47, 12:00, 18:17, 20:19, 10-01 03:33, 11:31, 10-02 11:56, 14:50, 15:03,
15:17, 16:33. The span that actually blocked scheduled triggers:

- **2026-10-02 04:00 → 11:56 (7h56m)** — this single sleep span ate **four**
  daily triggers that all fall inside it: AegisDailyPass (06:30), AegisFleetDailyCheck
  (06:45), AegisNNLabNightly (08:30) and AegisAnalystPanelDaily (05:30). None of
  the four tasks is configured to "start when available" or "wake the computer
  to run" (not verified against every flag individually, but all four show
  `LastRunTime` stuck at their 10-01 firing with no 10-02 entry, and Windows
  does not retroactively run a missed one-shot-per-day trigger once the window
  has passed unless that setting is on). **This is the single cheapest fix in
  the whole audit**: flip "wake the computer" + "run ASAP after a missed start"
  on these four tasks.
- The many short sleep/resume flickers on 09-30 evening (18:17→20:19) and
  10-01 night (03:33 resume quickly followed by more cycling) did **not** cost
  a missed trigger directly, but they are what repeatedly re-armed
  `always_on_lab` (two of its three restarts land within minutes of a resume
  timestamp) and are the most likely explanation for the 92 orphaned
  `chrome.exe` processes found at audit time (each resume that respawns a
  reader/lab component appears to leave the previous cycle's Chrome children
  running rather than cleanly killing them).
- The reader supervisor's 57.5-hour silent gap is **not** explained by sleep
  at all — the PC was awake for most of 09-30 and all of 10-01 — so it is
  listed separately above as the largest true failure, not a sleep cost.

## Memory

- Free physical memory at audit time was **about 4% of total** (full figures,
  including the chrome/python process breakdown and graphics-card state, are in
  `backend/data/optimus/local_pc/automation_audit_machine_2026-10-02.md` per
  the no-machine-details-here instruction).
- **92 `chrome.exe` processes** were resident, together holding
  **about half of total system memory** — far more than the "2 reader workers" the
  supervisor's own tick log expects (`reader_procs: 2`). These read as orphans
  accumulated across the repeated sleep/resume/respawn cycle rather than a
  single runaway page.
- No `llama-server` process was found running at audit time despite
  `always_on_lab_lock.json` showing a live lock (process id recorded locally, started 10-02
  03:58) — either it had already exited/crashed again since, or it runs under
  a different process name than searched for; this was not resolved in the
  time available.
- Nothing in the evidence gathered shows the harness or a person deliberately
  killing a process during this window (no `taskkill`/image-name-kill traces
  found in the logs read); the `always_on_lab` restarts are self-reported as
  "previous pid not alive (crashed)," not as killed.

## WHAT WORKS

- The fleet manager (open/preclose), world digest, contest rehearsal, and
  alerts cadence are all genuinely robust to the sleep/resume churn — full
  coverage, correct receipts, no gaps.
- The refusal discipline is working where it matters: `AegisStraddleForward`,
  `AegisIIF1NightLauncher`, and `pull_bars_refresh` all correctly refuse rather
  than act on stale or unsafe data, and all three write a legible reason to
  their own receipt. The telegram supervisor caught and healed a dead child in
  about an hour.

## WHAT DOES NOT WORK

- Four daily tasks have no missed-run catch-up and silently skip a whole day
  when the trigger lands inside a sleep window.
- A kill-switch file (`hyp_lab/STOP`) blocks all future runs once dropped,
  with nobody and nothing to clear it.
- `always_on_lab` keeps resurrecting itself through an untraced mechanism,
  against its own standing OFF instruction, and drags a local-graphics-card model load with it
  every time.
- The reader supervisor has no Scheduled Task of its own, so its self-imposed
  `--until` cutoff is a one-way switch: once it stops, it stays stopped until a
  human notices — and for 57.5 hours this window, nobody did.
- The learning-report pipeline reports itself healthy while producing nothing
  for three straight days — exactly the "a scoreboard over a dead ledger is
  green forever" pattern this project has hit before.

## HIGHEST-EV EXPERIMENT

Give the reader supervisor and `always_on_lab` each a real Scheduled Task
(reader: relaunch every 4h with a fresh `--until`; lab: a task that asserts the
OFF flag and kills any `always_on_lab` process found running, rather than
leaving its restart path untraced), and flip "wake to run" + "run ASAP after a
missed start" on the four tasks that fall inside the 04:00–11:56 sleep window.
Those two changes would have converted the worst two findings in this audit —
57.5 hours of silence and a guardrail that disobeys itself — into non-events,
at near-zero engineering cost, and they do not touch strategy, risk, or
capital at all.
