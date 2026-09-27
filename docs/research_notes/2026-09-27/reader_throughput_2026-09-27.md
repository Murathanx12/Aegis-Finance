# Reader throughput: fewer CLI calls, interleaved lanes, one worker per site (2026-09-27)

**RESULT IMPROVEMENT: engineering only, not measured live yet.** The live reader
(PID 134396, `queue_run_2026-09-27k.log`) ran the OLD code for this whole session
and was not touched. The throughput numbers below are an estimate built from
measured per-call costs. They become a measurement only after the restart in §6
has run for an hour.

## 1. Profile (read-only, from tonight's receipts)

**Where the time goes.** Every OpenClaw CLI call is a new `node openclaw.mjs`
process.

| measurement | value | source |
|---|---|---|
| CLI calls / seconds, 2-page run | 47 calls, 438.2 s = **9.32 s/call** | `plan_2026-09-27_143041.json` footprint (process scope) |
| `browser profiles` | 4 calls, 32.0 s (8.0 s/call) | same |
| `browser tabs` | **16 calls, 143.1 s (8.9 s/call)**, 34% of calls | same |
| everything else (navigate, wait, press, evaluate, status, snapshot, blank) | 27 calls, 263.1 s (9.7 s/call) | same |
| process start-up with no gateway contact: `browser --help`, `browser batch --help`, `browser wait --help` | **4.1-6.2 s** | timed locally (no browser verb) |
| `--version` fast path | 0.08 s | timed locally (not representative: it skips the command tree) |
| live run since 14:55 UTC: page loads | 28 in 0.76 h = **35 loads/h**, median gap 80 s, drawn targets 13-20 s | `news_corpus/dowjones/_throttle.log` |
| article read (`read_s`) | median **147 s** (n=10) | `plan_2026-09-27_145440.json` |

So roughly **50-65% of each call is fixed process start-up**. The rest is the
gateway plus the browser. The throttle never binds: every realised gap is 4-8
times the drawn target.

The receipts only split CLI time three ways (profiles / tabs / other). The
per-verb rows below come from the code path and are checked against the
measured 147 s median (about 16-17 calls × 9.3 s):

| per article, OLD code | calls | why |
|---|---|---|
| navigate from a blank tab | 1 pre-check `tabs` (always fresh: the cached URL is about:blank) + 1 `navigate` + 1 post-check `tabs` re-read | guard |
| settle `browser wait --time 3500` | 1 + about 0.5 `tabs` (20 s cache expires between 9 s calls) | **a timer** |
| scroll: 2-3 × (`wait --time 1000-3000` + `press PageDown`) | about 5 + about 1.5 `tabs` | **half of these are timers** |
| `read_text` (`evaluate`) | 1 + about 0.5 `tabs` | guard + read |
| blank the tab | 1 | renderer memory |
| `browser status` (`attached_to`, 60 s cache, called on every operator verb) | **about 2.5** | **receipt metadata, not a guard** |
| `browser profiles` (120 s cache) | about 1 | guard |
| **total** | **about 16-17 calls ≈ 150 s** | |

## 2. What was removed or merged, and why every guard is intact

| change | calls saved / article | guard status |
|---|---|---|
| `wait --time N` (the settle and the 2-3 scroll pauses) became **local sleeps**. The gateway runs a time-only wait as `setTimeout(N)` **outside** its Chrome MCP operation lock (openclaw 2026.9.5 `waitForExistingSessionCondition`), so the page sees the same seconds pass. The settle is served *lazily*: only what is left of it when the tab is next touched. | 3-4 calls + about 1 listing | The host check dropped here guarded a timer that touches no page. **Every action** (navigate, click, press, evaluate, close) still has its pre-action host check. This is pinned by `test_every_action_keeps_its_host_check_and_navigate_its_landed_url_check`: checks == actions == presses + 2. |
| Post-navigate landed-URL check now reads **the navigate reply** (`navigated to <url>`). That URL is the gateway's own `list_pages` read of the page, taken inside the same locked operation right after `navigate_page` returned. It is host-checked exactly like the re-read, and the cached listing row for that tab is updated (the cache stamp is **not** extended). No URL in the reply means a fresh `tabs` listing, as before. | 1 listing | The check still happens after the action, on a URL read *earlier* than the old one. An off-host landing refuses: `test_an_off_host_landing_in_the_navigate_reply_still_refuses` (sso.accounts.dowjones.com → `REFUSED_LEFT_HOSTS`). **Caveat:** the gateway returns `page.url ?? params.url`, so a page with a *null* URL would echo the requested URL. Chrome always reports a URL for a live page, and `read_text` host-checks the URL it actually read. click and non-scroll press still re-list. |
| `attached_to()` cache: 60 s → `OPENCLAW_ATTACHED_TTL_S = 900`. It is now **also dropped by every `invalidate_profile_cache`** (a refusal naming a tab, a non-zero verb, a gateway timeout, a start/stop). | about 2.4 | It was metadata and never a guard. It is refreshed *more* often than before on any failure. |
| The scroll plan (2-3 steps, 1-3 s pauses) is drawn at load time from the same generator. | 0 | Same distribution. This also keeps the throttle's draw order identical to the serial run. |

**Unchanged and still enforced:**
- host check before every tab action, and after navigate, click and non-scroll press;
- own-tab check: `close` only on `_OPENED_TABS`, per process;
- the blank-tab rule;
- the marker rule: `resolve_parent_tabs` with `PARENT_MARKER`, re-applied in every worker and in the launcher;
- the allowlist and `DENIED_DOMAINS`;
- `evaluate` stays out of `ALLOWED_VERBS`; `read_text`'s fixed function is unchanged;
- the `open` verb stays refused on `user`.

**Checked in the OpenClaw code and CLI docs:**
- **No batch mode here.** `browser batch` exists, but the docs say "`batch` is not supported on `profile="user"` / existing-session profiles". The client already refuses it too.
- **The persistent control API is not usable yet.** The loopback HTTP API (`GET /tabs`, `POST /navigate`, `POST /act`) would remove process start-up entirely. It is opt-in: `OPENCLAW_EAGER_BROWSER_CONTROL_SERVER=1` plus a gateway restart, which this task forbids. It is the biggest lever left (see §7).

New per-article cost, measured through the **real** guard with a fake CLI: **7 CLI calls** with 2 scroll steps (profiles 1, tabs 1, navigate 1, status 1, press 2, evaluate 1). Add the blank (1), a cache-expiry listing (about 0.7), profiles about 0.5 in steady state, and status about 0.1. That is **≈ 7.8 calls ≈ 72 s + about 5 s of local pauses ≈ 77 s**, against about 150 s before.

## 3. Interleave within one process

`interleave_order(queues, needs_load)` is the pure rule, and `run_plan` applies it
online:

1. Loads happen in `round_robin` order.
2. A lane's page is **read right after the next lane's load**, so its settle is spent on that load.
3. A lane never has two pages outstanding (one tab each).
4. An in-place item (the tab was opened at it) finishes at its turn.
5. Leftovers finish at the end. There is no finish after a gateway-down stop.

Every load still takes a throttle slot, so the global drawn gap and the same-host
floor still bind. The saving is about 3.5 s per page (the settle). That is small,
because the per-page cost is CLI calls, and those are still serial *inside* one
process.

## 4. Workers, one per site (`--workers`, default 3)

**Is it safe at the gateway? Yes, from OpenClaw's code.** In
`dist/chrome-mcp-DZMaKINm.mjs`:
- `withChromeMcpLease` runs every operation under `getChromeMcpRoutingState(session).withOperationLock`, an async lock per Chrome MCP session;
- `callTargetTool` adds the explicit `pageId` of the named target to every tool call;
- `navigateChromeMcpPage` re-reads `list_pages` inside the same lock.

So concurrent CLI calls queue at the gateway. None of them acts on the "selected
page" or on another caller's tab. The reader's own `read_text` already refuses a
reply whose `targetId` differs (`REFUSED_READ_WRONG_TAB`).

**What was NOT safe, and is now fixed:**

| hazard | fix |
|---|---|
| `open_from_tab` finds its new tab by diffing `tabs` before and after. Two openers in flight could adopt each other's tab. | `open_from_tab` and every operator `close` hold a **tab-topology lock**: `disk_guard.file_lock` on `%TEMP%\aegis_openclaw_tab_topology.lock`, cross-process and cross-thread. |
| The throttle was read, then slept, then appended with no lock. Two processes could take the same slot. | `Throttle.acquire` holds `file_lock(<throttle>.lock)` **through** its sleep. Tests: two threads with their own `Throttle` on one file (every gap ≥ min, stamps unique), plus a real second process holding the lock (`FileLockTimeout`). |
| **`startup_cleanup` with two live runs.** It adopted every session-qualified handle on a Dow Jones host listed in any receipt from the last 3 days, including a **live** run's in-progress receipt. A second run would have closed the first run's lane tabs, and the first would then fail `REFUSED_OPERATOR_TAB_MISSING`. This was latent only because the single lock forbade a second run. | Receipts now carry `worker` + `pid`. `previous_opened_handles(worker=…)` reads only receipts of **the same worker id** whose pid is **not alive**. A crashed worker's tabs are closed by the next start of that id. Single-session receipts are closed only by a single-session run or by the launcher. The refusal path in `main()` no longer overwrites the run's `opened` accounting. |
| One `_reader.lock`. | `_reader_<worker>.lock` per worker id. A worker refuses while a single-session reader is live, and a single-session reader refuses while any worker is live. |
| `_search_seen.jsonl` and corpus rows were appended with no lock. | `DG.locked_append_line`. `store_article` (exists-check + atomic write + corpus row) runs under `file_lock(<corpus>/_store.lock)`. |

**Launcher (`--plan … --workers 3`):**
1. Re-attaches if needed and resolves every parent through the marker rule. No marker tab means `REFUSED_NO_MARKER_TAB` and no process starts.
2. Takes the single-session lock, closes what dead single-session runs left, then releases the lock.
3. Starts `python -m scripts.dowjones_pull --plan <site lanes> --worker <site> --run-stamp … --handoff --profile user`.
4. Binds each child to a Windows job object (`llama_server.bind_lifetime`: kill the launcher by PID and its workers die with it).
5. Writes `dowjones/queue_workers.pid`, waits for the children, and folds their `plan_<stamp>_<site>.json` receipts into `workers_<stamp>.json`.

The `--max-pages` budget is split in proportion to each site's lanes.

## 5. Expected pages/hour (arithmetic; not yet measured)

- **One process, new code.** Articles cost about 77 s and search pages about 40 s (list + navigate + snapshot + blank ≈ 4.5 calls). Tonight's plan mixes roughly 40% articles and 45% searches, plus opens, so a page averages about 55-60 s → **about 60-65 pages/h**, against 35 now.
- **Three workers.** 3 × 60-65 = 180-195 in theory. Two things bound it:
  - **Pacing.** A simulation of 3 hosts loading back to back at the live settings (gap 6-20 s, same host 18 s) gives a ceiling of **about 190 loads/h, CV of gaps 0.33-0.37** (the alarm is < 0.15). The hourly cap is **180**. The per-site floor (max(18, 3 × target) ≈ 40-60 s) allows about 70/h per site.
  - **Contention.** Three concurrent node start-ups on a machine that was already under memory pressure, plus the gateway lock, which is held through each `navigate_page` load (seconds per page).
- **Realistic estimate: 110-150 pages/h**, with 180/h as the hard cap. Verify it from `_throttle.log` (loads per hour) and from the new `cli_by_verb` block in each worker's footprint (seconds per verb, now receipted).

## 6. Restart command (for the orchestrator)

Stop the running queue **by its PIDs** in `dowjones/queue_run.pid` (130988, 134396), never by image name. Then, from the repo root in cmd:

```
cd /d C:\Users\mrthn\aegis-finance
C:\Users\mrthn\aegis-finance\.venv\Scripts\python.exe -m scripts.dowjones_pull --queue backend\data\optimus\dowjones\QUEUE_2026-09-27_wide.txt --handoff --profile user --workers 3 < backend\data\optimus\empty_stdin.txt >> backend\data\optimus\dowjones\queue_run_2026-09-27l.log 2>> backend\data\optimus\dowjones\queue_run_2026-09-27l.log.err
```

- **Resume and cleanup.** The plan line resumes from `--fresh-since 2026-09-27` (MarketWatch pages already stored and searches already recorded are skipped). The launcher closes the old run's lane tabs (t29-t34, from its worker-less receipt) before the workers start.
- **Stopping it later.** Kill the launcher PID (the `launcher` field in `queue_workers.pid`, or the PID Start-Process returned). The job object takes the workers with it. Each worker's PID is in the same file.
- **Which lines use workers.** `--archive` / `--claims` lines ignore `--workers` and run single-process after the plan line.

## 7. Not done, and why

- **No live measurement.** A browser verb was forbidden while the live run was on.
- **The control-API route** (§2) needs `OPENCLAW_EAGER_BROWSER_CONTROL_SERVER=1` and a gateway restart, which only the operator may do. A Python HTTP driver would then have to re-implement every guard in `openclaw_client` before it could be trusted.
- **The blank navigation** (`own_blank_tab("blank")`, one call per article) is kept. It is the renderer-memory rule from the 97-process night.
- **Pre-existing, noticed, not fixed:** `test_openclaw_client`'s `Reader.close(write_footprint=True)` writes footprints into the REAL `backend/data/optimus/web_reader/`. The 1-page, 0.03-CLI-second footprints stamped 22:59, 23:06 and 23:08 tonight are test artefacts, not reader runs.
