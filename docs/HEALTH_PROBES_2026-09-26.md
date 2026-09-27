# Health probes — 2026-09-26

Implements §4 of `docs/reviews/REVIEW_2026-09-26_SYSTEMS_ATTACK_AND_HEALTH_PROBES.md`.
Code: `backend/services/system_health.py`. CLI: `python -m scripts.health_probe`.
Tests: `backend/tests/test_system_health.py`.

## The contract

Every verdict is **derived** from evidence the producer itself wrote: a stamp inside a
receipt, a pid that answers with the expected module in its command line, an HTTP body
field, or a row-count delta since the previous probe. Never an mtime (an AST test bans
`stat`/`st_mtime`/`getmtime` in the module), never a lock file alone.

| verdict | meaning |
|---|---|
| ALIVE | evidence inside the declared cadence (+25% grace) |
| STALE | evidence older than cadence, or a process that answers but writes nothing |
| DEAD | a process or endpoint is gone (pid not in the process table, pid reused, endpoint unreachable). Only process/endpoint probes say DEAD |
| UNKNOWN | the evidence that would decide does not exist; `detail` says why. Never ALIVE. A probe that raises is UNKNOWN with the exception class |

Trading-day cadences use the XNYS calendar (`exchange_calendars`; weekday fallback):
"last closed session" is the newest session whose close + 20 min has passed in New York.

## Surfaces

- `python -m scripts.health_probe [--json] [--only a,b] [--no-proc] [--no-write]` prints
  the table (DEAD, STALE, UNKNOWN, ALIVE), writes
  `backend/data/optimus/health/health_<YYYYmmddTHHMMSSZ>.json` (never overwritten),
  `HEALTH.md`, one line of `health_index.jsonl`, and `_state.json` (what the delta probes
  diff against). **Exit code: 1 any DEAD · 2 any STALE · 3 all UNKNOWN · 0 otherwise.**
- `/api/health/full` → `subsystems {generated_utc, source, counts, exit_code, rows}`,
  cached 60 s. On a request only file-derived probes run; the probes that shell out or
  open a socket (`needs_proc`) are copied from the newest PC receipt when it is ≤ 2 h old,
  else UNKNOWN "not computed on a request". On Railway every `pc` probe is UNKNOWN
  "runs on the PC" unless such a receipt exists. It does not fold into top-level `status`.
- Morning report (`scripts/night_morning_report.render`) opens with
  "## 0. Subsystems not ALIVE"; the Telegram brief (`telegram_bridge.send` with tag
  `brief`/`cmd:brief`) is prefixed with the same DEAD/STALE lines. Both call
  `system_health.non_alive_lines()`: newest receipt if ≤ 2 h old, else file probes now.

## Probes

| probe | cadence | evidence | ALIVE when |
|---|---|---|---|
| bars_panel | 1 session | `prices_2025_26/bars.parquet` max(date) (row-group stats) | sessions behind last closed ≤ `BARS_MAX_AGE_SESSIONS` (2) |
| ranking | 1 session | `pc_book/<d>/ranking.json.asof` | same limit |
| u_funnel | 10 d | `funnel_night10.json.generated_at` via `funnel_staleness()` | not stale |
| always_on_lab | heartbeat_minutes | `lab_status.json.utc` + pid cmdline contains `always_on_lab` | both |
| lab_loop:<loop> | period×2 | `loops[*].last_tick_utc` + status | fresh and status not error/timeout |
| sim_session | trading day | `sim/session.json` state/heartbeat + pid cmdline `sim_run` | RUNNING in US hours; idle outside them |
| live_market_loop | 1 session | NAV rows tagged `open_of_loop`/`close_of_loop` | a tagged row on the last session |
| u_forecast | 1 session | ledger max(`made_at`), rows made today | newest made_at ≥ last session |
| forecast_ledger | 1 d | ledger row count delta since previous probe | delta > 0; zero for ≥ 1 d = STALE (DEGRADED) |
| u_review | 1 session | `review/review_<last session>.json.generated_utc` | exists |
| u_plan | 1 session | `intended_book.json` t/asof/invested_frac + ranking asof | fresh, under `PROBE_GROSS_CAP`, ranking within limit |
| policy_state | 1 d | `pc_book/<d>/decisions.jsonl` plan rows (`asof` within `POLICY_STATE_READ_SESSIONS` = 2) + `pc_book/policy_state.json.refreshed_utc` | a recent plan carries `policy_state_used`; STALE `WRITE-ONLY` when the state is written and no plan read it (or the plan ignored it, reason printed); UNKNOWN with neither (added 2026-09-27) |
| decision_contract | 1 d | `decisions/<d>.json.written_utc` + `accrual_canary.n_considered_row` | fresh and not stuck |
| forecast_grader | 1 d | ledger max(`resolved_at`) vs due-unresolved rows; daily_pass "N wait on a bar" | resolved_at moved while due rows exist; no bar-wait > 21 d |
| book_grader | 1 session | daily_pass `scoreboard.nav_vs_spy.window.last_date` (+ newest leaderboard name stamp) | == last session |
| learn_rota | 1 d | `pc_book/<d>/learn_*.json` status / skipped / `panel_last_session` vs bars | nothing degraded, skipped or computed on old bars |
| daily_pass | 1 d | `daily_pass_<d>.json` steps[*].utc/status (+ schtasks Last Run as info) | today's receipt, no error/timeout step |
| iif1_night | weekday | `iif1_nights/<last weekday>.json.status` | `ok` |
| news_collectors | 15 min | newest `_receipts/*_ALL.json.written_utc`, red/refused, newest `first_seen_utc` per source | fresh (≤ 30 min), no red |
| social:<source> | 6 h | `lab_status.loops.social_pull.per_source` | per source; refused ⇒ UNKNOWN |
| dowjones_feeds | 1 d | `dowjones/feeds_<d>.json.generated_utc` | fresh, no red |
| telegram_agent | 120 s | `telegram/heartbeat.json` (else `update_offset.at`) + pid cmdline `telegram_agent` | both; pid alive without heartbeat ⇒ UNKNOWN |
| openclaw_gateway | 5 min | `openclaw gateway status` (ANSI-stripped) | running, probe ok, capability ≠ no-operator-scope |
| openclaw_api_bridge | — | none written | always UNKNOWN (writes no heartbeat) |
| llama_server | on demand | `GET :8080/health` + owner note + lab `l2_typing` | up, or idle with nothing PENDING_MODEL > 1 h |
| llama_reaper | 30 s | `llama_reaper.log.jsonl[-1]` | `exit` with a reason, or tick < 60 s |
| optimus_brain | 24 h | `~/optimus/brain/projects/aegis-health/aegis-health-latest.md` `generated … UTC` | < 24 h |
| task:<name> | — | `schtasks /query /fo CSV /v` | UNKNOWN for tasks with no receipt mapped (Last Result is cmd's rc); daily pass, IIF-1 and Telegram tasks are judged by their own probes |
| railway_backend | 1 d | `GET /api/health/full` `deploy.uptime_seconds`, `scheduler.nav.all_fresh` | all_fresh and uptime > 1 d (shorter = the container slept) |
| railway_fleet | 1 session | `railway status` linked service | UNKNOWN while the CLI is linked to retired `aat-loop-hack3` |
| ci | per push | `gh run list --commit origin/main` | success |
| git | per push | `git rev-list --count origin/main..HEAD` (local ref, not fetched) | 0 |
| accrual_canary | per probe | `accrual_canary.forecast_accrual` + `n_considered_row` on PC paths | both ok |

## Deviations from the review spec, stated

- Exit code follows the builder brief (1/2/3), not §4.3's "rc = number of DEAD rows".
- `bars_panel` is STALE beyond `BARS_MAX_AGE_SESSIONS` (the config's tolerance), so one
  session behind is ALIVE with its age printed; §4.4 test 3 asked for one-behind = STALE.
- `always_on_lab` does not yet run a `health` loop and `daily_pass` has no `health` step:
  both files belong to the systems-fixes builder tonight. `stack_health` is not yet a
  wrapper over these probes. These are the owed callers; until one exists, the table is
  as fresh as the last manual run (the API and the morning report fall back to the
  file-derived probes computed on the spot).

## First run — 2026-09-26T15:32:40Z (rc 2: 0 DEAD, 13 STALE, 6 UNKNOWN, 25 ALIVE)

STALE: accrual_canary / decision_contract (`n_considered` stuck ≥ 5 contracts) ·
book_grader (graded through 09-21, 4 sessions behind) · forecast_grader (135 due
unresolved, newest resolved_at 09-24, 130 wait on a bar) · git (10 local commits ahead) ·
lab_loop:idle_gpu_queue (timeout, GPU_BUSY) · learn_rota (distil DEGRADED rc 3;
survivorship computed on bars through 09-21) · live_market_loop (never ran end-to-end) ·
openclaw_gateway (connected-no-operator-scope) · optimus_brain (13.4 d) · railway_backend
(`all_fresh=False`, uptime ~15 min: the container slept) · ranking (as of 09-21, 4
sessions behind, while the bars panel itself is now current to 09-25) · u_plan (acting on
that ranking).

UNKNOWN: forecast_ledger (first run, nothing to diff) · openclaw_api_bridge (no
heartbeat) · railway_fleet (CLI linked to hack3) · social:reddit (keys absent) ·
task:AegisAnalystPanelDaily (no receipt mapped) · task:AegisWRDSPullNight (retired
one-shot; delete it).

The receipt is `backend/data/optimus/health/health_20260926T153240Z.json`.

## 2026-09-27 — the disk: two probes and a write guard

**Why.** From about 17:50 to 19:15 HKT on 09-27, C: sat at 0 bytes free
(handoff `HANDOFF_2026-09-26_WAVE2_...` §20). The lab died, the reader stopped,
a crawl lost its checkpoint, and 13 receipts were truncated to zero bytes. None
of the probe rows went red, because nothing measured the disk. Agents found out by
tripping over it.

**`disk_free`** (`pc`, cadence 5 min) is `shutil.disk_usage` on the volume that
holds `OPTIMUS_LEDGER_DIR`. It reads **ALIVE** at 10 GB free or more, **STALE**
below 10 GB and **DEAD** below 2 GB. The thresholds are
`config.DISK_FREE_STALE_GB` and `config.DISK_FREE_DEAD_GB`. The row's evidence
is the measured free GB and the volume. If the volume cannot be measured, or no
reader is on the context, the row is UNKNOWN, never ALIVE. First live reading
(11:48Z): **10.2 GB free on C:\ of 952 GB, ALIVE by 0.2 GB**, and falling about
0.6 GB in seven minutes while other agents ran.

**`zero_byte_receipts`** (`pc`, cadence 1 d) counts zero-byte files under the
ledger dir. It looks only at receipt-shaped names (`*.json*`, including
`.json.tmp`, plus `.md`, `.csv` and `.parquet`). Each file is dated by the
**stamp in its own name**: `20260927T111250Z`, `2026-09-27_111242`, or else
`2026-09-27`. It never uses mtime (the AST test in `test_system_health.py` still
passes). Any stamped empty file from the last 24 h turns the row **STALE**, and
the row names up to five. Empty files with no stamp are counted and named under
`undated`, but they cannot turn the row red because they carry no date. Logs
(`*.log`, `*.err`) are left out on purpose: an empty stderr log is what a clean
run leaves behind. If no file is stamped in the window, the row is UNKNOWN.

**The reports.** `system_health.disk_status()` measures the disk NOW, never
from a two-hour-old receipt. `non_alive_lines()` feeds both the morning report
and the Telegram brief. When the disk is STALE or DEAD its line comes **first**,
above the subsystems header. When the disk is fine, its line comes last. The
daily-pass receipt carries `disk` and prints `disk free: <n> GB`. When the disk
is STALE or DEAD, both the printed receipt and its `headline` start with that
line. A STALE `zero_byte_receipts` row appears among the DEAD/STALE rows like
any other probe.

**The guard** (`backend/services/disk_guard.py`):

- `require_free(gb, what)` raises `DiskTooFull`, naming the run, the volume and
  the measured GB. A volume it cannot measure also refuses. `DiskTooFull` is an
  `OSError` as well as a `RuntimeError`, so every existing `except OSError`
  around a write still catches it. It is enrolled in the missing-input contract.
- `atomic_write_json` / `atomic_write_text` write a temp file in the same
  directory, then fsync it, check its size against the bytes written, re-parse
  it (for JSON) and `os.replace` it over the target. When a write fails, the
  temp is removed and the **old file stays whole**. ENOSPC is raised as
  `DiskTooFull`.
- Writers converted (these are the ones that were truncated on 09-27):
  - the reader's receipts: `dowjones_pull._write` (plan, queue, feeds, reads,
    archive, claims), `_progress`, the queue `.done` markers and the
    queue-file writers
  - `web_reader`: footprint, the per-article record, the session lock
  - the health receipt, `HEALTH.md` and `_state.json`, all in
    `system_health.run`
  - the lab's `_write_atomic`, which covers `lab_status.json` and the lock.
    It had no fsync and left a zero-byte `.tmp` on ENOSPC. The running lab
    picks this up at its next restart.
  - `news_pull`: the per-source and `_ALL` receipts, and the cursors
  - the daily-pass receipt
- Start-up refusals. Each of these calls
  `require_free(DISK_FREE_DEAD_GB + 1, ...)`, which means 3 GB, before doing
  any work:
  - `night_backtest_factory` returns rc 2
  - `daily_pass` returns rc 2
  - `dowjones_pull --queue` returns rc 2
  - `sim_run` returns rc 4 and writes `STOPPED` / `REFUSED_DISK`, so the
    session can resume after space is freed

### Space on this machine: what is safe to clear, and what is not

**Safe to clear.** All of this regenerates on the next install or build:

| what | how | size seen |
|---|---|---|
| pip cache | `pip cache purge` | 4.3 GB on 09-27 (purged; 1.7 MB now) |
| npm cache | `npm cache clean --force` | 6.4 GB on 09-27 (cleaned) |
| `frontend/.next` | delete the folder; `npx next build` rebuilds it | ~2.2 GB |
| `__pycache__` folders | delete them; Python rewrites them on import | ~50 MB |

**Not safe to clear.** None of this can be regenerated, or it is the record
itself:

- **Models**: the llama-server GGUFs, e.g. Qwen3-30B-A3B at 17.28 GB. They are
  re-downloadable, but only at hours of bandwidth, and the lab expects them.
- **Ledgers**: `backend/data/optimus/**` (predictions, books, claims, sessions,
  decisions, receipts, `news_corpus`, `evidence_memory`). These are the evidence.
- **Bars**: `prices_2025_26/bars.parquet` and the delisted-bars panels. Pulling
  them again costs hours, and a mid-pull state is survivor-biased.

11 GB free is roughly one day of margin at the 09-27 write rate. Real space has
to be freed on C:. The caches are only a stopgap.
