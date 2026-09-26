# Review 2026-09-26 — Railway cost (chunk H), review only

**Scope.** Read-only. No `railway up/down/redeploy/variables`, no edits in
`aegis-alpha-terminal`, no orders, no `railway ssh`. Commands run:
`railway status`, `railway metrics` (7d, raw JSON), `railway logs -n`,
`railway list`, `git log`/file reads in the sibling repo, and two local
import-only / read-only ledger measurements.

**RESULT IMPROVEMENT: NONE** (a review; nothing deployed).

---

## 0. The answer in five lines

1. **The five containers are not the cost.** A container outside the window is
   a sleeping `sh` at 0.02 GB (hack2, hack5 on Saturday: 0.02 GB). Five of those
   cost about $1/month.
2. **The gigabytes are file data, not Python.** Importing the loop and every cycle
   step costs about 26 MB. Streaming the 1.1 GB counterfactual ledger through
   `verify_chain` costs 12 MB of private memory and 8.7 s. What remains resident
   between cycles, and on a Saturday with no process running, is the
   **page cache of multi-GB ledgers on the volume**. Railway's pricing page
   counts filesystem cache as memory in use.
3. **A cadence bug multiplies the reads.** Since the 09-20 cadence wrapper, every
   cycle is a fresh `--once` process, and `agent_loop.main()` initialises
   `last = {... 0.0 ...}` in each one. So every 10-minute "exits-only" cycle
   re-runs the hourly and 6-hourly steps: `counterfactual --record` (a full chain
   walk), `candidates`, `window_universe`, and after the close `daily_autopsy`
   and `discovery_autopsy`. That is 10–15 runs per day each instead of 1 per
   night or 4 per day.
4. **Measured run-rate:** fleet memory 4.78 GB averaged over 7 days, about
   **$48/month** for the loops alone. That is *higher* than the pre-cadence
   period's memory spend (§3). The 09-20 change that was meant to cut memory did
   not.
5. **Recommendation: keep the topology** (five services, five volumes, five
   keys: ownership and isolation stay exactly as they are). Fix the two code
   defects in the terminal repo, attended. Expected loops memory falls from about
   $48 to roughly $3–10/month, and the workspace moves to about the $20 Pro floor.
   Consolidation, cron and serverless each save at most about $1/month more, and
   each one weakens isolation or liveness.

---

## 1. What each container actually holds, and why

### 1.1 Measured memory (7 days, hourly samples, 2026-09-19T08Z → 09-26T08Z)

Source: `railway metrics -s aat-loop-<role> --since 7d --raw --json`, series
`MEMORY_USAGE_GB` / `CPU_USAGE` / `DISK_USAGE_GB`, n = 169 samples each. The
window is Mon–Fri 13–22Z (`market_window.sh` default 1300–2210Z).

| role | 7d avg GB | 24h avg GB (Murat's) | in-window avg | outside-window avg | Saturday 09-26 00–08Z | CPU 7d avg vCPU | volume GB |
|---|---:|---:|---:|---:|---|---:|---:|
| hack1 | 1.37 | 3.19 (3.18) | 2.29 | 1.04 | **3.35–3.36 flat** | 0.0107 | 4.61 |
| hack2 | 0.47 | 0.48 (0.50) | 1.21 | 0.20 | 0.02–0.03 | 0.0067 | 3.39 |
| hack4 | 0.57 | 0.94 (0.97) | 0.99 | 0.42 | 1.29 → 0.10 | 0.0042 | 2.55 |
| hack5 | 1.04 | 1.34 (1.38) | 2.85 | 0.38 | 0.88 → 0.02 | 0.0153 | 6.60 |
| hack6 | 1.33 | 2.27 (2.33) | 2.53 | 0.89 | 3.41 → 0.24 (decaying, CPU≈0) | 0.0106 | 4.72 |
| **sum** | **4.78** | 8.22 | | | | **0.0475** | 21.88 |

My 24h figures reproduce Murat's observed averages to within 0.06 GB.
The 7-day figure is the right basis for a monthly estimate. The 24h figure is a
Friday running into a weekend, with hack1 and hack6 stuck high.

### 1.2 Why: the boot path and each cycle

- **Image:** `python:3.12-slim` plus `requirements.txt` = `alpaca-py`, `numpy`,
  `yfinance` (Dockerfile L11–14, requirements.txt). **No pandas, torch or model
  is declared, and none is loaded at boot.** `CMD` is `sh /app/scripts/market_window.sh`.
- **Wrapper** (`scripts/market_window.sh`, commit `f40431c`, 2026-09-20): outside
  Mon–Fri 13:00–22:10Z it runs `sleep 300`. Inside the window, in the default
  `AAT_LOOP_MODE=cadence`, it starts `python -m scripts.agent_loop --once` every
  10 minutes: a "full" cycle every 30 minutes and `--manage-only` in between. It
  also starts `python -m scripts.prediction_book_sync &` for the whole window.
- **Every step is a subprocess** (`agent_loop._run` → `subprocess.call`, L155–175).
  The long-lived Python heap is therefore tiny. Measured locally (Windows, import
  only, `GetProcessMemoryInfo`): `scripts.agent_loop` 26 MB working set,
  `alpha.runner` 28 MB, `scripts.counterfactual` / `daily_autopsy` /
  `candidates` 26 MB each. The wrapper's own comment ("~1.16 GB (pandas, numpy,
  the venue client)") names the wrong cause. The 1.16 GB it measured on 09-20
  was also cgroup memory.
- **The data reads are what is large.** `scripts/counterfactual.py` ends with
  `ledger.verify_chain("counterfactual")` (L110). That calls `scan_chain`, which
  streams **the entire** `counterfactual.jsonl` (`alpha/ledger.py` L240–260).
  Measured locally on the August copy (1,118,870,798 bytes): **12 MB peak
  private memory, 8.7 s**. The cost is not heap. It is 1.1 GB pulled into page
  cache. On the volumes, the ledgers are larger: volume usage is 2.5–6.6 GB per
  role. `ledger.read_all()` on the 19 MB decisions ledger peaks at 98 MB private.
- **Why the cache is billed:** Railway's pricing page states that VM billing
  counts "memory in use (including the operating system and filesystem cache)"
  (docs.railway.com/reference/pricing/plans). For containers the docs are not
  explicit. The metrics behave like cache, though:
  - hack6 decays from 3.41 to 0.24 GB over four Saturday hours with CPU at
    about 0.00001 vCPU. Anonymous memory held by a sleeping process does not
    decay; reclaimable cache does, when the host needs it.
  - hack1 climbs monotonically through each window (09-24: 2.40 → 2.90 GB), even
    though every cycle's process exits within 2–3 minutes.

  **This is the one inference in the document that is not directly measured.**
  §5 step 0 is the check that settles it.
- **The cadence bug that multiplies the reads.** `agent_loop.main()` L243
  initialises `last = {"exit": 0.0, "entry": 0.0, "cf": 0.0, ... "autopsy": 0.0,
  "window": 0.0}` in every process. Under `--once`, every cycle therefore sees
  every stamp as overdue. Counted from `railway logs -s aat-loop-<role> -n 5000`
  for 2026-09-25 (roughly the last 1.5–2.3 h of the window only):

  | role | counterfactual | candidates | daily_autopsy | discovery_autopsy | window_universe | dislocation_scan |
  |---|---:|---:|---:|---:|---:|---:|
  | hack1 | 15 | 15 | 13 | 13 | – | – |
  | hack2 | 11 | 11 | 10 | 10 | 11 | – |
  | hack4 | 11 | 11 | 10 | 10 | 11 | – |
  | hack5 | 14 | 14 | 13 | 13 | – | – |
  | hack6 | 11 | 11 | 10 | 10 | 10 | 11 |

  By design these are hourly (`cf`), 6-hourly (`candidates`, `window`) and once
  per night (`autopsy`). The hack1 log at 21:54Z shows a cycle labelled
  `exits-only` running `daily_autopsy`, `discovery_autopsy`, `decision_writeback`,
  `candidates` and `counterfactual --record`.

  Cycle busy time after the close is 22–34% of wall time (median 124–183 s per
  cycle), from the `MARKET WINDOW cycle … at` and `exited … at` stamps.
  `dislocation_scan` on hack6 returns in about 0.1 s, so it is not an LLM cost.
- **CPU is not the problem.** The fleet's 7-day CPU is 0.0475 vCPU, about
  $0.95/month.

### 1.3 Isolation as implemented today

- **One service per role, one volume per service** at `/app/state`
  (`railway status`: `aat-loop-hackN-volume` for each). A Railway volume
  attaches to one service, so ledgers are physically separate.
- **One key pair per service.** `alpha/config.credentials()` refuses when
  `AAT_ACCOUNT_ROLE` and the requested role disagree ("FOURTH REFUSAL",
  config.py L280–300). It never reads the generic `ALPACA_*` names.
  `AlpacaPaper` logs `verified paper account <number> (role=<role>)` at start,
  and this appears in the live logs.
- **Ledger single-writer:** an `O_CREAT|O_EXCL` lock file (`ledger.py` L159) and
  tail-only `_last_hash`. The Dockerfile's rule: "NEVER run the same role from
  two hosts at once."
- **No runtime execution lease** equivalent to `pc_broker.check_lease()`. Every
  role's `client_order_id` is `aat-<sha256[:32]>` (`broker/alpaca.py` L392), so
  the prefix does **not** identify the role. Exits go out as
  `DELETE /v2/positions` and come back broker-named, so a "halt on any
  unprefixed fill" rule copied from `pc_broker` would trip on every exit.
  `scripts/reconcile.py` separates `aat-` orphans (a lost row, which is a
  defect) from broker-named exits (expected), but it is run by hand.
  Ownership in the fleet is therefore **structural** (one key in one container),
  not measured.

---

## 2. The options, designed concretely

### CURRENT — five cadence workers (as deployed)
One service per role, the wrapper above, one volume each. Isolation and
ownership are as described in §1.3. Cost is dominated by the cached ledgers and
by the cadence bug.

### CURRENT + two fixes (the recommendation; same topology)
1. **Persist the cadence stamps.** `--once` reads and writes `last` from
   `$AAT_LEDGER_DIR/loop_cadence_<role>.json` (atomic write). An exits-only cycle
   then runs `manage` plus `fill_audit` only. `counterfactual` runs hourly,
   `candidates` and `window_universe` every 6 h, and the autopsy once per night
   (its retry semantics are kept, because the stamp now survives).
2. **Stop walking the whole chain every cycle.** Store a verified checkpoint
   (`byte_offset`, `prev_hash`, `size`, `lines`) and verify only the appended
   tail on `--record`. Keep a **full** `scan_chain` once per night after the
   close, so "every break is reported, not just the first" still holds and a
   rewrite before the checkpoint is still caught by the nightly walk. After any
   full scan, call `os.posix_fadvise(fd, 0, 0, POSIX_FADV_DONTNEED)` (Linux
   only, guarded) so the pages are released instead of billed.

Optional: remove the separate `prediction_book_sync &` poller, since
`_cycle()` already calls `prediction_book_sync.sync_once()` every cycle
(agent_loop L350–357).

### OPTION 1 — one multi-mandate process
One service runs a supervisor that spawns one child process per role. Each
child gets an explicit env: its own `AAT_ACCOUNT_ROLE`, its own key pair and
`AAT_LEDGER_DIR=/app/state/<role>`. The supervisor restarts a crashed child
without touching the others. A process pool, not threads: `AAT_ACCOUNT_ROLE` is
read from the environment in about 145 places.

**Blocking defect for this option:** 51 module-level paths are hardcoded as
`Path(__file__).parent.parent / "state"` or `ROOT / "state"` and ignore
`AAT_LEDGER_DIR`. Examples: `alpha/liveness.py`, `alpha/spend.py`,
`alpha/event_state.py`, `alpha/epoch.py`, `scripts/prediction_book.py`,
`scripts/discovery_autopsy.py`, `scripts/premarket_digest.py`. In one container
those would all write into a **shared** `/app/state`: five roles' heartbeats,
spend, epochs and sealed books in one directory. Every one would have to be
moved onto the env var first.

Migration means merging five volumes (about 22 GB of hash-chained ledgers) into
one, by byte copy. One OOM or one redeploy stops all five books at once.

### OPTION 2 — scheduled workers (Railway cron)
Five cron services, `*/10 13-22 * * 1-5` UTC (Railway's minimum interval is
5 minutes, and "if a previous execution is still running … Railway will skip
the new cron job", per docs.railway.com/reference/cron-jobs). Each run executes
`agent_loop --once`, with full or exits-only chosen from the persisted stamp,
which is fix 1 again and therefore a prerequisite. Same volume per role.

Cold start is a container start plus about 26 MB of imports each run; the
container start time was not measured. What breaks on overlap: nothing at the
ledger, because Railway skips. But a `run_pass` that takes more than 10 minutes
(the median is 368 s according to agent_loop L533) makes the next exits check
skip, not queue. The in-window liveness line becomes the cron history instead
of the wrapper log. Whether volumes mount on cron services was not verified
here: **check that before designing on it.**

### OPTION 3 — serverless / app sleeping
Railway sleeps a service after about 5–10 minutes with **no outbound packets**
and wakes it only on **inbound** traffic. Its docs say that "background workers
sending periodic outbound traffic will remain active and won't benefit"
(docs.railway.com/reference/app-sleeping).

The loop has no HTTP surface, and during the window it calls Alpaca every
cycle, so it would never sleep while the market is open. Outside the window it
would never wake without an external pinger (for example seal-authority over the
private network). No role needs the loop outside 13:00–22:10Z, and the wrapper
already makes that time cost 0.02 GB. hack2 (0 positions and 100% cash as of
09-22, per ACCOUNTS) is the only role where even in-window exits cycles do
nothing. Its entries still need the window.

---

## 3. Monthly cost of each

**Prices** (docs.railway.com/reference/pricing/plans, fetched 2026-09-26):
memory $10/GB/month, CPU $20/vCPU/month, volume $0.15/GB/month, egress $0.05/GB.
The Pro plan is $20/month including $20 of usage, so the bill is
`max($20, usage)`. Hobby is $5 including $5 of usage.

**Measured workspace run-rate, 7 days** (`railway metrics … --since 7d --raw --json`):

| item | basis | $/month |
|---|---|---:|
| loops memory | 4.78 GB | 47.8 |
| loops CPU | 0.0475 vCPU | 0.95 |
| loop volumes | 21.88 GB | 3.28 |
| hack3 volume (retired) + detached staging volume | 2.59 + 0.8 GB | 0.51 |
| seal-authority | 0.075 GB, 0.0005 vCPU | 0.76 |
| website `selfless-courage/Aegis-Finance` | 0.474 GB, 0.169 vCPU (peak 5.4), 0.34 GB volume | 8.16 |
| egress | 0.14 MB in 7d (website) | ~0 |
| **workspace** | | **≈ 61.5** |

**Sanity check against the actual bill.** The memory note
`reference_local_suite_env_traps_2026_09_20.md` records usage of $48.05 for
Aug 26 → Sep 20 (read 09-20): memory $25.20, CPU $20.52 (the website warm loop,
since reduced), volume $1.28, egress $0.18, agent $0.87. That is about 25 days,
or roughly **$30/month of memory**.

Today's memory run-rate is **$57/month** (loops, seal and website). The CPU line
fell by about $16/month, while memory roughly doubled after the cadence change.
Both moves are consistent with §1.2: every cycle re-reads the ledgers, and the
ledgers keep growing.

**Per option, loops only (seal and website unchanged at about $9/month):**

| option | memory | CPU | volumes | loops total | isolation |
|---|---|---:|---:|---:|---|
| CURRENT as-is | $47.8 (measured) | 0.95 | 3.28 | **≈ $52** | intact |
| CURRENT + 2 fixes | 5 × (0.02 GB shell + 0.1–0.5 GB × ~10% process time) ≈ 0.15–0.35 GB → **$1.5–3.5**; I budget **$3–10** until measured | ≤ 0.95 | 3.28 | **≈ $7–14** | intact |
| OPTION 1, one process, with the fixes | the fixed figure minus 4 shells (4 × 0.02 GB = $0.80) | ≤ 0.95 | 3.28 (same GB) | ≈ $6–13 | weakened (§4) |
| OPTION 1 without the fixes | the same five ledgers cached in one cgroup ≈ unchanged | | | ≈ $50 | weakened |
| OPTION 2 cron, with the fixes | the fixed figure minus 5 shells ($1.00) + cold starts | ≤ 0.95 | 3.28 | ≈ $6–13 | intact; liveness changes |
| OPTION 3 serverless | in the window it never sleeps = CURRENT; outside, it saves at most the shell | | | ≈ same as fixed current | liveness risk |

About the "~10% process time" basis: the window is 45.8 h of the 168-hour week
(27%), and measured busy time is 22–34% of the window after the close. I assumed
up to about 40% in session, where `run_pass` runs. The 0.1–0.5 GB per active
process runs from the measured 98 MB `read_all(decisions)` up to a margin for
larger volume ledgers. **This band is an estimate and is marked as one.** The
live metric in §5 is what decides it.

**Workspace after the fixes:** about $16–23 usage, so the bill is about
**$20 flat on Pro**. Hobby would only win if usage stays below about $15, and
its service and resource limits were not checked here.

---

## 4. Risks to broker ownership, ledger isolation and the lease

| option | broker ownership | ledger isolation | lease / liveness |
|---|---|---|---|
| CURRENT (+ fixes) | one key per container env; `credentials()` refuses a role mismatch | one volume per service (physical); `O_EXCL` lock | no runtime lease; shared `aat-` prefix. The fixes change neither. The persisted stamp file must be per role, which it is by living on the role's own volume |
| OPTION 1 | five keys in one environment: a child spawned with the parent env, or a module reading the parent's `AAT_ACCOUNT_ROLE`, trades another book's account. The `pc_broker` lesson "a fallback is how one book quietly trades another's account" applies directly | **51 hardcoded state paths collide** in a shared `/app/state`; the volume merge moves 22 GB of hash-chained history | one OOM or deploy stops five books; a crash is isolated only if the supervisor is correct |
| OPTION 2 | unchanged (one service per role) | unchanged; overlap is prevented by Railway skipping | a skipped run means a missed exits check, not a queued one; a cold-start failure is silent unless the cron history is read |
| OPTION 3 | unchanged | unchanged | no inbound traffic means no wake, which means no stop checks. This is only partly mitigated by broker-side protective stops (`protect.STOP_PREFIX`) where a book places them |

**Lease note (independent of cost).** If a fleet lease is ever wanted, it cannot
copy `pc_broker`'s "any unprefixed fill halts" rule, because every fleet exit is
broker-named. It would need a role-tagged prefix (`aat-<role>-…`), and the
reconcile classification would have to run in the loop instead of by hand. The
id is deliberately replay-collision-stable, so changing its shape is a
terminal-repo design decision, not a cost fix.

---

## 5. Recommendation and attended checklist

**Keep CURRENT topology. Fix the two defects in `aegis-alpha-terminal`, in a
session in that repo** (tests only via `python run_tests.py`, its rule). Do not
consolidate, cron or sleep: the ceiling on further saving is about $1/month
against real isolation and liveness risk.

Murat runs, attended:

- [ ] **0. Confirm cache versus anon before coding** (read-only, in the
      container): `railway ssh -s aat-loop-hack1`, then
      `grep -E '^(anon|file|shmem) ' /sys/fs/cgroup/memory.stat`,
      `ps -eo pid,rss,etime,args`, and `du -sh /app/state/* | sort -h | tail`.
      If `file` dominates, §1.2 holds. If `anon` dominates, look for an
      orphaned step process instead: `timeout -s TERM` at the close kills
      `agent_loop` but not its running child.
- [ ] 1. Terminal repo: persist `last` to `$AAT_LEDGER_DIR/loop_cadence_<role>.json`.
      Add a test that two `--once` runs 10 minutes apart run `candidates` once
      and `daily_autopsy` once per night.
- [ ] 2. Terminal repo: add the incremental `verify_chain` checkpoint, keep the
      nightly full walk, and add `posix_fadvise(DONTNEED)` after full scans. The
      test: a break inside the already-verified prefix is still reported by the
      nightly walk.
- [ ] 3. Correct the wrapper comment's cause ("pandas, numpy" → cached ledger
      reads) so the next reader does not optimise imports.
- [ ] 4. Deploy **hack2 first** (0 positions, cash only), with
      `fleet --deploy hack2 --up` or `railway up` from the terminal repo. Leave
      the other four on the old image for one full window as the control.
- [ ] 5. Then hack4, hack5, hack6 and hack1, one per day.

**Verify live after each deploy** (the `verify-prod-after-deploy` skill):

- [ ] `railway logs -s aat-loop-<role> -n 5000 | grep -c "run scripts.candidates"`
      shows no more than 2 in the window (6-hourly), `daily_autopsy` exactly 1
      per night, and `counterfactual` no more than about 10 per day.
- [ ] Exits still run within 10 minutes in session: `run scripts.manage` appears
      on every exits-only cycle while the market is open.
- [ ] The chain still verifies: the `counterfactual` output line and the nightly
      full walk both print a verdict, and a break count equal to today's is not
      treated as new.
- [ ] `verified paper account <same number> (role=<role>)` appears in the log;
      `python -m scripts.accounts --role <role>` shows the same account number;
      `python -m scripts.reconcile` shows 0 `LOST-ROW`.
- [ ] After 7 days: `railway metrics --all --since 7d --raw --json`. Memory × $10
      should sit inside the $3–10 band. If it does not, the estimate was wrong;
      say so in the receipt.

**Out of scope, but noticed:** hack3's volume (2.59 GB) and the detached
staging volume (0.8 GB) cost $0.51/month. Keep hack3's volume, because it is the
retired book's ledger evidence. The website backend's 7-day CPU still averages
0.17 vCPU with a 5.4 vCPU peak, about $3.4/month.
