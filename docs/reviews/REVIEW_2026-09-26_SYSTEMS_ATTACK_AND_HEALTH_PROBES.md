# Review — 2026-09-26 (22:45 → 23:00 HKT) — systems attack, lost systems, and a health-probe spec

Reviewer: Opus, read-only. Order (Murat, verbatim): *"review everything, attack it to see any bad
rules, false code, non responding lost systems. for keeping track maybe add a health probe to
everything to monitor"*. No code or data was changed, no process was killed, no LLM was called,
`.env` was not opened. Evidence was read at **2026-09-26 14:44–14:58 UTC** (Saturday; last US
session Fri 09-25). Every verdict below cites the evidence it was derived from, never a lock file
or an mtime.

## RESULTS SCOREBOARD
| line | state |
|---|---|
| best historical net strategy vs market | unchanged (none survives multiplicity) — not in scope |
| best forward paper strategy | **cannot be read**: every forward book is graded on `prices_2025_26/bars.parquet`, whose last bar is **2026-09-21** (§1 row 1) |
| independent selectors | unchanged |
| new actionable finding | **three silent stalls found**: the bars panel (5 days), the Railway website backend (asleep; NAV 8 days old), the Telegram agent (dead 3.5 days) |
| LLM spend (this review) | $0.00 |

**RESULT IMPROVEMENT: NONE** — this is a diagnosis. The three worst things (§5) are each a
"static file / dead loop that reads healthy" of exactly the family CLAUDE.md already names.

---

## 1. Census — every long-running or scheduled thing, by its own evidence

Verdicts: **ALIVE** (evidence inside cadence) · **STALE** (evidence older than cadence) · **DEAD**
(no process and no evidence inside 2× cadence) · **UNKNOWN** (the evidence that would decide does
not exist — the reason is the finding).

| # | subsystem | last evidence (UTC) | where the evidence lives | expected cadence | verdict | the one line that proves liveness |
|---|---|---|---|---|---|---|
| 1 | **bars panel** `prices_2025_26/bars.parquet` (feeds `u_rank`, `u_learn`, `freeze_gate`, `LP.grade`, `paper_accounts_roi`, morning `nav_vs_spy`) | `max(date) = 2026-09-21` (4 sessions missing: 09-22..09-25) | the parquet's own `date` column | 1 session | **STALE — and nothing refreshes it.** Writers are `night_p6_bars_and_regret` / `pull_deep_bars` / `pull_delisted_bars`, reachable only from a hand-queued night-factory job or `routers/control.py:101`. No scheduled caller. | `pq.read_table(bars).column('date').max() >= last_session()` |
| 2 | `scripts/always_on_lab.py` (pid 100684, child of venv pid 71436) | `lab_status.json.utc = 14:43:57` (tick 17), pid in process table | `backend/data/optimus/lab_status.json` | 5 min | **ALIVE** — but per-loop rows are polluted (§3 F1) | `now - lab_status.utc < 2×heartbeat_minutes` **and** `lab_status.pid` answers with `scripts.always_on_lab` in its command line |
| 3 | sim (`scripts.sim_run`, `sim_session`) | last checkpoint `2026-09-26T02:50:48Z`, `state: STOPPED` ("stop requested 02:54:21") | `sim/sessions.jsonl` last row | a session per US trading day; **no scheduler starts one** | **DEAD until a human starts it** — Monday 09-28 has no automatic PC-PAPER plan, forecast or review unless someone runs `sim_run` (the Telegram `/sim` path is also dead, row 8) | `sessions.jsonl[-1].state == RUNNING and now - heartbeat < 2×cycle` on a trading day |
| 4 | `u_forecast` | `n_rows_written: 270` on 2026-09-26; ledger rows `made_at` 09-25: 1,269, 09-26: 298 | `predictions.jsonl` `made_at` | once per sim day | **ALIVE (only while a sim runs)** | Δ rows with `made_at` today > 0 |
| 5 | `u_review` | `review/review_2026-09-25.json` | review receipt date | pre-open, per trading day | ALIVE (same caveat) | `review_<last_session>.json` exists |
| 6 | `u_plan` (PC-PAPER) | `intended_book.json t=02:50:42Z`, `acting: true`, `n_to_send: 0` | `pc_book/2026-09-26/intended_book.json` | every sim cycle | ALIVE, **acting on a 09-21 ranking** (§2 R1) | `ranking.asof == last_session()` |
| 7 | `u_funnel` | `generated_at 2026-09-24T02:48:34Z`, 25 candidates | `funnel_night10.json` own stamp | ≤ `FUNNEL_STALE_DAYS`=10 | ALIVE (2.5 d) | `generated_at` age < 10 d |
| 8 | **Telegram agent** (`scripts/telegram_agent.py --serve`) | outbox last send `2026-09-23T01:07:14Z`; `agent.pid` = `﻿73584` (BOM + stale pid, not in process table) | `telegram/outbox.jsonl`, `update_offset.json` | poll every `--interval`; a brief daily | **DEAD ~3.5 days.** No scheduled task, no supervisor. The machine has not rebooted since 09-18 06:57, so it did not die on a reboot. `stack_health` on 09-24 reported it **ok/READY** (getMe only). | `update_offset.at` (or a heartbeat row) younger than 2×interval **and** the pid answers with `telegram_agent` in its command line |
| 9 | OpenClaw gateway (pid 60960 + supervisor 66248) | `openclaw gateway status`: "Runtime: running (pid 60960 … last run time 2026-09-26T13:50:57Z)", "Connectivity probe: ok", **"Capability: connected-no-operator-scope"** | CLI status (ANSI-stripped) | always | **ALIVE, degraded capability** (no operator scope — the lab cannot drive tasks through it that need one) | `openclaw_client.health().gateway_probe_ok and capability != 'connected-no-operator-scope'` |
| 10 | llama-server | no process; `lab_status.llama_server.up: false, detail: "not running"` | `llama_server.status()` / `GET :8080/health` → no answer | on demand (`MODEL_ROUTING_START_AT_BOOT=False`) | **ALIVE-BY-DESIGN (idle)**; `l2_typing` sits at `PENDING_MODEL` with 40 units waiting because the lab no longer starts it (`lab_starts_model_server: false`) — a design choice that means typing never happens overnight | `/health` 200 when a loop holds a `touch()` note; else `PENDING_MODEL` rows counted |
| 11 | `scripts/llama_reaper.py` | `2026-09-26T13:46:59Z {"action":"exit","reason":"no owner note: no Aegis-started server"}` | `llama_reaper.log.jsonl` | only while an Aegis server runs | **ALIVE-BY-DESIGN (exited correctly)** | last row is `exit` with a reason, or a tick < 60 s old |
| 12 | `AegisDailyPass` → `scripts/daily_pass.py` | receipt `daily_pass_2026-09-26.json`, steps `utc 22:53–23:49Z` on 09-25; schtasks Last Result 0 at 06:30 local | the receipt's own step `utc` | daily 06:30 HKT | **ALIVE** — but "5 ok / 3 nothing-to-do" hides `NO_BAR_FOR_RESOLUTION_DATE: 130` and a sweep that stopped at 829/2362 symbols (§3 F10) | receipt for `today` exists and every step's `utc` is today |
| 13 | `AegisIIF1NightLauncher` (IIF1 investigator) | `iif1_nights/2026-09-25.json status ok, spend_usd 2.5856` | night receipt | weekdays 16:00 HKT | **ALIVE**; ~$2.59/night (this is the spend nobody watched) | receipt for last weekday with `status ok` |
| 14 | `AegisAnalystPanelDaily` (terminal repo `.cmd`) | Last Run 26/9 05:30, Last Result 0 | schtasks only (no receipt read here) | Tue–Sat 05:30 | **UNKNOWN** — "Last Result 0" is `cmd`'s rc, not the job's | the job's own receipt date |
| 15 | `AegisWRDSPullNight` | one-time, 2026-08-22 | — | none | retired; delete the task | — |
| 16 | `scripts/live_market_loop.py` | **no NAV row tagged `open_of_loop` / `close_of_loop` in any `pc_book/*/nav.jsonl` (09-22..09-26)** | nav tags | per US session | **NEVER RAN end-to-end.** Its role is done by `sim_run`; it is also the ONLY reader of `policy_state` (§2 R3) | a NAV row tagged `open_of_loop` today |
| 17 | Optimus MCP (pids 122712/86200, 136392/89864) | process table; `session_briefing()` → **"STALE health page — generated 319.9 h ago" (2026-09-13)** | the health page's own stamp | refresh after every session | process **ALIVE**, brain snapshot **STALE 13 days** (`tools/refresh_aegis.py` has no scheduled caller) | health page `generated` < 24 h |
| 18 | **Railway website backend** (`selfless-courage` / `Aegis-Finance`) | `/api/health/full`: **`deploy.uptime_seconds: 13`** on my first request (10.1 s response = cold start); Railway log: container started 14:09:53 (deploy healthcheck), **"Stopping Container" 14:18:15 with no redeploy**, restarted 14:47:16 on my curl. `scheduler.nav.*.last_nav_date = 2026-09-18` for all 10 lanes (`expected_nav_date 2026-09-25`), `scheduler.last_mtm: null`, collectors `insider_cmp/revisions/pead/quality/multifactor` last row **2026-09-17**, `status: DEGRADED` | the endpoint's own body + `railway logs` | APScheduler jobs daily 16:30 ET | **STALE / effectively DEAD for scheduled work.** The container is being stopped when idle (serverless sleep signature), and an in-process APScheduler cannot fire while the container is stopped. `scheduler.running: true` and `jobs.status: ok` are read from the process that was just woken. Also: every start runs `python /app/scripts/arena_paper_repair_once.py` → *"No such file or directory"* (a dead pre-start command). | `nav.all_fresh == true` **and** `deploy.uptime_seconds > 86400` on a probe from outside |
| 19 | Railway fleet `aat-loop-hack1/2/4/5/6` + `seal-authority` (terminal repo, `loving-elegance`) | each: "cycle full exited rc=0 at 2026-09-25T22:0xZ … loop exited rc=124 at 22:10:00Z (window close)"; seal-authority "2026-09-26: weekend, no trading seal required" | `railway logs --service <svc>` | per US session | **ALIVE** (Friday close) | a `cycle full exited rc=0` line dated the last session |
| 20 | `aat-loop-hack3` | deployment `FAILED` 2026-09-02; retired 09-22 | `railway status` | none | retired — **but this repo's CLI link points at it** (§3 F16) | — |
| 21 | news collectors (lab `news_pull` + daily_pass `news_pull`) | lab `news_pull.last_tick_utc 14:34:58Z`, `rows_new 58`, 29 sources; daily_pass 514 rows / 19 sources | news receipt `_receipts/<ts>_ALL.json` | 15 min | **ALIVE** (row shows a stale `error` field — §3 F1) | Δ corpus rows with `first_seen_utc` in last 2×cadence > 0 |
| 22 | `social_pull` | 6 rows at 13:02Z; **Reddit `REDDIT_KEYS_ABSENT`** | lab row | 6 h | ALIVE for YouTube; Reddit **DEAD (no keys)** reported as `status: ok` | per-source status, not loop status |
| 23 | learn rota (`u_learn`: backtest_factory / distil / survivorship_audit / breadth_check / idle) | `distil` → `DEGRADED rc 3` "no new graded rows"; survivorship/breadth → `"skipped": "bars unchanged"` | `pc_book/<d>/learn_*.json` | per sim cycle | **STALE** — two of four units cannot run until row 1 is fixed, and a skip is printed as a normal outcome | the unit's input fingerprint changed since the last run, or a STALE line |
| 24 | book grader (`night_backtest_factory` via `u_learn.backtest_factory`; `LP.grade`) | leaderboard `leaderboard_2026-09-26T093458Z.json`; morning scoreboard `nav_vs_spy.window.last_date = 2026-09-21` | receipt | daily | **STALE** (grades end at the last bar = 09-21; the 241 books entering Monday cannot be graded past 09-21 until row 1 is fixed) | `nav_vs_spy.window.last_date == last_session()` |
| 25 | forecast grader (`forecast_grader.grade_due`) | ledger: resolutions on 09-20 (14,703) and 09-24 (2,781), none since; **130 records stuck `NO_BAR_FOR_RESOLUTION_DATE`** (88 are AVB, resolves_after 2026-08-21..09-04) | `predictions.jsonl` `resolved_at` | daily | ALIVE for new rows, **permanently stuck for 130** — printed daily as a refusal, status `nothing_to_do` | Δ `resolved_at` rows > 0 on any day where due rows existed; stuck count not growing |
| 26 | `accrual_canary` | local: runs only inside `daily_learning_report` / Railway `main.py:1108`; Railway: `DEGRADED` ("forecast_accrual: 0 new rows… newest 2026-09-18") | health body | every health read | **ALIVE but pointed at the wrong ledger on Railway** (§2 R6) | — |
| 27 | CI watcher (`scripts.ci_watch`) | `b09de80 completed success 13:50:39Z`; HEAD `af82a6f` is **unpushed (ahead 1)** → `rc=2` with only "watching HEAD af82a6f" | GitHub API | after every push | ALIVE; unhelpful on an unpushed HEAD (§3 F12) | rc 0 for `origin/main` HEAD |
| 28 | Dow Jones pull (`scripts.dowjones_pull --handoff`, pid 82888/136120, started 22:31 HKT) | process table | — | attended, ad hoc | running now (not reviewed; paywalled read gated by `HANDOFF_PC`) | — |
| 29 | `openclaw_api_bridge.py` (pid 77136/37564, spawned by the gateway 22:44) | process table | — | on demand | ALIVE (new; no receipt found) | UNKNOWN — writes no heartbeat |

---

## 2. Attack on the rules

Worst case is printed per session-protocol item 4 on the largest admissible book of the account
it governs (PC-PAPER, equity **$999,054** at 02:50Z).

**R1 — `u_plan` acts on a ranking five days old, and no rule can stop it.** *(wrong)*
Receipt (sim checkpoint 09-26 02:50Z): `rank: {"skipped": "bars unchanged since the last rank",
"asof": "2026-09-21"}` beside `plan: {"acting": true, "probe_acting": true}`.
`u_rank` (`scripts/sim_run.py:364-385`) re-ranks only when the bars *fingerprint* (size + mtime,
`sim_run.py:221`) moves; there is no age check anywhere on the ranking path. The same bars make
`freeze_gate()` refuse every library book (`STALE_BARS`, `night_backtest_factory.py:1564-1569`,
"none pass") — **one gate refuses the data another gate acts on** (contradiction with R7).
Worst case: PROBE sizes on live prices, so it is bounded by R2's numbers; the damage is that
EXPLOIT's `MEASURED_NEGATIVE` verdict and every E[r] are computed on a 09-21 panel forever.

**R2 — `PROBE_GROSS_CAP = 0.20` caps targets, not holdings; a same-day refusal cannot exit.** *(wrong)*
Receipt: `reconcile.invested_frac = 0.2184` (11 names × ~$19.9k) at 02:50Z; `intended_book`:
10 PROBE targets, `n_orders: 1` (ALLE, $19,927.92), **`n_to_send: 0`**, `contract_clash: ["ALLE","SON"]`.
Cause: `_prior_probe_holdings` (`sim_run.py:732-748`) skips plan files with `p.stem >= asof`, so a
name PROBE bought under the *current* asof is classed `EXIT`, and `EXIT` is sent only when
`exploit_acting` — which is False. ALLE self-heals on the next asof (09-28) only if a sim runs.
Worst case at the largest admissible book: a session in which the contract refuses all ten of the
day's PROBE buys leaves **40% gross** (20% intended + 20% stuck) for one session, ceiling
−$399,622 with no stop, 3σ-day ≈ −$32.9k (40% × 3 × 2.74%). Also: **GOOG and GOOGL are both held at
2% — one issuer at 4%**; no rule dedups share classes.

**R3 — `policy_state` is write-only on the running path.** *(dead)*
`policy_state.SCHEMA` declares 12 mutable keys. `sim_run.py:1373` refreshes it; **nothing in
`sim_run`, `pc_broker`, `decision_contract` or `night_investigator_forecast` reads it.** The only
readers are `live_market_loop.py:104-105` (`book_size`, `replan_drift_frac`) — a process that has
never run (§1 row 16). `exploration_temperature`, `min_decile_confidence`, `reader_reliability_*`,
`source_trust`, `horizon_weights`, `watchlist_attention`, `persona_weights` have **zero** readers;
`reputation_weights` is read only by a report. Contradiction: policy `replan_drift_frac = 0.05`
vs the band that actually binds, `pc_broker.REBALANCE_DRIFT_FRAC = 0.10` (and that one is
env-overridable, `AEGIS_PC_REBALANCE_DRIFT_FRAC`). "The learning layer now writes rules +
policy_state" (S57) is true and changes no decision.

**R4 — three single-name caps and three gross caps for one account.** *(contradictory)*
Decision contract 2026-09-26: `capital_usd: 40000.0` **and** `worst_case_largest_admissible_book.equity_usd: 1000000.0`
in the same file; tilts `single_name_cap 0.03`, `total_budget 0.10` (worst case −$100,000).
`u_plan` EXPLOIT: `ER_EXPLOIT_MAX_WEIGHT = 0.10`/name, gross ≤ `1 − PROBE gross` = **80%**, no stop
→ ceiling **−$799k**, 3σ-day ≈ −$51.8k (80% × 3 × 2.16%). `pc_broker.MAX_NAME_FRAC = 0.12`,
`MAX_INVESTED_FRAC = 1.00`. Challenge rule ≤ 20%. The plan receipt's `worst_case_line` prints the
PROBE book only; the EXPLOIT line is computed (`wc_exploit`) but is not the headline. Which cap
is the mandate? Today it is whichever function happens to run.

**R5 — `n_considered: 2` on every contract 09-20 → 09-26 (seven in a row), and the guard that
exists for exactly this cannot see it.** *(dead guard)*
`decisions/2026-09-2{0..6}.json → roi_ranking.n_considered = 2`, capital 40000 on all seven,
even after the funnel was rebuilt to 25 candidates on 09-24. `accrual_canary.stuck_counter(min_run=5)`
exists; it runs on Railway, whose canary says *"n_considered: no decision contract carries
roi_ranking.n_considered"* — the contracts are on the PC. Locally no scheduled surface calls it.
This is the 2026-09-22 CLAUDE.md headline bug, recurring one layer down.

**R6 — the Railway accrual canary watches a ledger nobody writes.** *(cannot go green)*
`/api/health/full → forecast_populations.live_forward.notes: "Its true size is ZERO …"`,
producer "production nightly specialists" (retired 08-27). `accrual_canary.forecast_accrual`
reads `/data/optimus/predictions.jsonl` = that population → `DEGRADED` "newest 2026-09-18" and the
site's top-level `status: DEGRADED` for 8 days. The real producer (`u_forecast`) is on the PC.
A permanent red beside the real one (NAV 8 days stale) teaches the reader to skim both.

**R7 — four staleness rules, four clocks.** *(contradictory)*
`FUNNEL_STALE_DAYS = 10` (`investment_committee.py:83`, own stamp) · bars: **no rule** ·
`freeze_gate`: bars ≤ 1 session · `pm_actions.MARKET_RADAR_STALE_HOURS = 36` computed from
**`st_mtime`** (`pm_actions.py:682`) while `generated_at` is printed beside it — on a Railway
deploy the file's mtime is the deploy time, so the radar reads `OK` on any age. One constant, one
source of truth (the artefact's own stamp), per input.

**R8 — the reputation pool has no production caller.** *(dead)*
`forecast_reputation.pool()` (`:292`) is called by no script or service outside tests; weights
(`D_all 0.42 …`, personas 0.0) are computed nightly and bind nothing. The floor-0 rule is correct
and inert.

**R9 — 130 forecasts can never resolve, and the grader calls that "nothing to do".** *(wrong)*
`daily_pass_2026-09-26.json: grade_forecasts status "nothing_to_do", refusals ["NO_BAR_FOR_RESOLUTION_DATE: 130 record(s)"]`;
88 are AVB with `resolves_after` 08-21..09-04 (bars for AVB absent from the grader's panel). Printed
every day since August; never escalates, never voids. The Railway row counts the same 128/130 as
`overdue_actionable`.

**R10 — `lab_status.power_plan = "ok (or CANNOT DETERMINE)"`** (`always_on_lab.py:1951-1952`) is
a guard that prints green for "I could not tell". The log line beside it *can* tell ("AC standby
timeout 0 (never)"); the status field throws that away.

Rules that held up under attack (for balance): `freeze_gate` (None → `_UNKNOWN` → CONTROL, never
PASS); `policy_state._check` bounds and evidence requirement; `forecast_reputation.weights`
(all-zero, not uniform, when no arm is positive); `pc_broker.plan_orders` refusals are returned,
not dropped; the drift band's rationale; the funnel CLI's rc-2 + unmoved-`generated_at` check.

---

## 3. False code (file:line)

| # | finding | file:line | evidence |
|---|---|---|---|
| F1 | **Per-loop status rows merge keys across ticks.** `row.update(out)` never clears keys the new tick did not return, so `news_pull` reads `status: ok` beside `error: "news_pull: no return in 900s (thread abandoned)"`, `reason: DAILY_PASS_RUNNING`, `pids: [112704]` (a pid not in the process table); `idle_gpu_queue` reads `status: ok` beside `reason: GPU_BUSY, detail: "…19 min ago"`. A reader cannot tell this tick from three ticks ago. | `scripts/always_on_lab.py:1879` | `lab_status.json` 14:43:57Z |
| F2 | `stack_health.check_telegram` measures the bot token (`getMe`), not the agent; `check_sim` counts `COMPLETED`/`STOPPED` as ok. The 09-24 receipt says telegram `ok: READY` a day after the agent died, and simulation `ok` with nothing running. | `scripts/stack_health.py:146-165` | `stack_health_2026-09-24.json` vs `telegram/outbox.jsonl` last row 09-23 |
| F3 | `u_grade` turns every exception into a string and returns normally, so the sim unit is `ok: true` with `forecasts: "FAILED …"` inside. | `scripts/sim_run.py:1270-1290` | code |
| F4 | `u_rank` / `u_learn` skip on an unchanged size+mtime fingerprint and print the skip as a normal outcome; there is no age of the data anywhere in the result. | `scripts/sim_run.py:221, 375-381, 1318-1327` | checkpoint `"bars unchanged since the last rank", asof 2026-09-21` |
| F5 | Market-radar staleness from `st_mtime` (protocol item 7). | `backend/services/pm_actions.py:682` | code |
| F6 | `policy_state.load()` serves defaults on an unreadable file; the next `update()` writes the whole default state back, silently resetting every learned value. | `backend/services/policy_state.py:109-119, 160-172` | code |
| F7 | Same-asof PROBE holdings excluded from `_prior_probe_holdings` → unexitable while EXPLOIT refuses (R2). | `scripts/sim_run.py:740-741` | `intended_book.json n_to_send 0` |
| F8 | IIF1 funding guard defaults to a hand-typed balance from a month ago. | `backend/services/investigator_night.py:193-194`, `backend/services/iif1_run.py:456` | `DEFAULT_BALANCE_USD = 23.99`, `BALANCE_AS_OF = "2026-08-24"` |
| F9 | `forecast_accrual` checks only that rows are *written* (`made_at`), never that they *resolve*; a stalled grader (R9) is green. On Railway it watches the retired ledger (R6). | `backend/services/accrual_canary.py:83-138` | health body |
| F10 | `daily_pass` step statuses: `analyst_snapshot` is `ok` after reaching its budget at **829 of 2,362 symbols** (1,533 with no row for the day); `grade_forecasts` is `nothing_to_do` with 130 stuck. The summary line "5 ok / 3 nothing-to-do / 0 refused" is the only line most readers see. | `scripts/daily_pass.py` (step `_row` statuses) | `daily_pass_2026-09-26.json` |
| F11 | `social_pull` loop `status: ok` while Reddit is `REFUSED: REDDIT_KEYS_ABSENT` — loop status is not source status. | `scripts/always_on_lab.py` (social loop) | `lab_status.json` |
| F12 | `ci_watch` exits rc 2 on an unpushed HEAD with only "watching HEAD af82a6f" — "not pushed" is indistinguishable from "CI missing". | `scripts/ci_watch.py` (default `--sha HEAD`, commit `3e0a25d3`) | run at 14:5xZ |
| F13 | Learn `distil` reason says "no new graded rows since **2026-09-26** (… resolved through 2026-09-24)" — the date labels the run, not the last resolution. | `learn_distil.json` writer (`scripts/daily_learning_report.py` distil path) | sim checkpoint |
| F14 | The website container runs `python /app/scripts/arena_paper_repair_once.py` on every start → "No such file or directory". A dead pre-deploy/start command in the Railway service settings (not in `railway.json`). | Railway service config | `railway logs -s Aegis-Finance` |
| F15 | **Three `.env` backups are NOT git-ignored in a PUBLIC repo**: `.env.bak_2026-09-20`, `.env.bak_before_cleanup_2026-09-22`, `.env.bak_telegram_2026-09-22` (`git check-ignore` matches only `.env`, `.gitignore:27`). One `git add -A` publishes keys. | `.gitignore:27` | `git status` `??` |
| F16 | This repo's Railway CLI link is `loving-elegance / aat-loop-hack3` (the terminal repo's retired service). A `railway up` from here deploys the website code into hack3. | `railway status` | — |
| F17 | `telegram/agent.pid` = `﻿73584` (UTF-8 BOM + dead pid). Any pid-file liveness check reads a lie or fails to parse. | `backend/data/optimus/telegram/agent.pid` | file |
| F18 | `always_on_lab.log` lines carry no timestamps, so the log can be dated only by mtime; liveness must come from `lab_status.json.utc`. | `scripts/always_on_lab.py` (print sites) | log tail |
| F19 | Optimus `session_briefing()` serves a health page generated **2026-09-13** (319.9 h) with no scheduled refresher; the session-start protocol step 1 therefore reads 13-day-old git state. | `optimus/tools/refresh_aegis.py` (no caller) | tool output |

Already-known and still true (not re-counted): the ledger hash chain broken since 08-25; the
`q2_run.log`/`.err` both empty (never-ran vs ran-empty indistinguishable).

---

## 4. Health-probe spec — `backend/services/system_health.py` (for a builder)

### 4.1 Contract
```python
Verdict = Literal["ALIVE", "STALE", "DEAD", "UNKNOWN"]

@dataclass(frozen=True)
class Probe:
    name: str                     # "bars_panel"
    where: Literal["pc", "railway", "external"]
    cadence: timedelta            # expected interval between evidence
    evidence: str                 # the exact field read, e.g. "bars.parquet: max(date)"
    fn: Callable[[ProbeCtx], ProbeResult]

@dataclass
class ProbeResult:
    verdict: Verdict
    evidence_utc: str | None      # timestamp FROM INSIDE the evidence, never st_mtime
    age_s: float | None
    detail: str                   # one sentence; for UNKNOWN, WHY it cannot be determined
    delta: int | None = None      # row-count delta since the previous probe run, if applicable
    proof: str = ""               # the one line that proved it ("pid 100684 cmdline scripts.always_on_lab")
```
Rules, each enforced by a test:
1. **No `st_mtime`/`getmtime` anywhere in the module** (AST test, skipping docstrings — CLAUDE.md
   protocol item 10).
2. **Missing evidence ⇒ `UNKNOWN`, never `ALIVE`.** A probe that raises ⇒ `UNKNOWN` with the
   exception class in `detail`.
3. `ALIVE` needs `age ≤ cadence` (+ a declared grace); `STALE` if `cadence < age ≤ 3×cadence`;
   `DEAD` if older **and** (for a process probe) the pid does not answer with the expected module
   in its command line. A pid that answers but writes nothing is `STALE`, not `ALIVE`.
4. Calendar-aware cadences: trading-day probes compute "last session" from the bars/venue
   calendar, not "yesterday" (a Monday is not stale because Sunday had no bar).
5. `delta` probes persist the previous count in `health/_state.json` (own stamp) and are `STALE`
   when a producer is due and `delta == 0` — *a scoreboard over a dead ledger is green forever*.
6. A probe of a PC subsystem run **on Railway** returns `UNKNOWN("runs on the PC; last PC health
   receipt is <age>")` — never a verdict it cannot measure.

### 4.2 Probes and their exact evidence
| probe | where | cadence | evidence field (derived) | ALIVE when |
|---|---|---|---|---|
| `bars_panel` | pc | 1 session | `bars.parquet` → `max(date)` | `== last_session()` |
| `ranking` | pc | 1 session | `pc_book/<d>/ranking.json.asof` | `== last_session()` |
| `funnel` | pc/railway | 10 d | `funnel_night10.json.generated_at` | age < `FUNNEL_STALE_DAYS` |
| `always_on_lab` | pc | 5 min | `lab_status.json.utc` + `pid` cmdline contains `scripts.always_on_lab` | both |
| `lab_loops` (one sub-row per loop) | pc | `periods_minutes[loop]` | `loops[loop].last_tick_utc` + **status from the latest tick only** (needs F1 fixed: builder adds `tick_utc` to each row and ignores keys not written on that tick) | age ≤ period×2 and status not in (error,timeout) |
| `sim_session` | pc | 1 trading day | `sim/sessions.jsonl[-1]`: `state`, `heartbeat`, `checkpoint.at` | on a trading day: `RUNNING` and `checkpoint.at` < 2×cycle; off-day: `STOPPED/COMPLETED` = ALIVE-IDLE |
| `u_forecast` | pc | 1 trading day | `predictions.jsonl` count with `made_at` date = today (delta) | delta > 0 on a sim day |
| `u_review` | pc | 1 trading day | `review/review_<last_session>.json` exists (+ its `written_utc`) | exists |
| `u_plan` | pc | 1 trading day | `intended_book.json.t`, `asof`, `n_to_send`, `invested_frac` vs `PROBE_GROSS_CAP` | fresh **and** `invested_frac ≤ cap + probe weight` (else STALE with "holdings exceed cap") |
| `decision_contract` | pc | 1 day | `decisions/<today>.json.written_utc` + `stuck_counter(roi_ranking.n_considered over last 7)` | fresh and not stuck |
| `forecast_grader` | pc | 1 day | Δ `resolved_at` since last probe + `NO_BAR_FOR_RESOLUTION_DATE` count (must not grow; >0 for >21 d ⇒ STALE) | as stated |
| `book_grader` | pc | 1 session | newest `leaderboard_*T*Z.json` + morning `nav_vs_spy.window.last_date` | `last_date == last_session()` |
| `daily_pass` | pc | 1 day | `night_factory_<today>/daily_pass_<today>.json` step `utc`s; each step's own status incl. refusals | receipt for today, no step `error` |
| `iif1_night` | pc | weekday | `iif1_nights/<last weekday>.json.status`, `spend_usd` | `ok` |
| `news_collectors` | pc | 15 min | newest `news_corpus/_receipts/<ts>_ALL.json` stamp + `rows_new` | fresh, `sources_red == []` |
| `social_sources` | pc | 6 h | per-source status in the social receipt | each source separately (Reddit ⇒ UNKNOWN "keys absent") |
| `telegram_agent` | pc | poll interval (default 60 s) | `telegram/update_offset.json.at` **plus** a new heartbeat row the agent writes each loop (`telegram/heartbeat.json {utc,pid}`) + pid cmdline contains `telegram_agent` | both |
| `openclaw_gateway` | pc | 5 min | `openclaw_client.health()`: `gateway_probe_ok`, `profile_pinned`, `capability` | probe ok and capability ≠ `connected-no-operator-scope` (else STALE with the capability string) |
| `llama_server` | pc | on demand | `llama_server.status()`: `up`, `ready`, owner note; lab `l2_typing.status` | ALIVE-IDLE when down and no loop is `PENDING_MODEL` > 1 h; STALE when units wait > 1 h |
| `llama_reaper` | pc | 30 s while a server is owned | `llama_reaper.log.jsonl[-1].t`, `action` | last row `exit` with reason, or tick < 60 s |
| `optimus_brain` | pc | 24 h | Optimus health page `generated` stamp (parsed from the page) | < 24 h |
| `scheduled_tasks` | pc | per task | `schtasks /query /v /fo CSV` Last Run + **the task's own receipt date** (never "Last Result") | receipt date matches Last Run |
| `railway_backend` | external | 1 day | `GET /api/health/full`: `deploy.uptime_seconds`, `scheduler.nav.all_fresh`, `nav.lanes.*.last_nav_date` vs `expected_nav_date`, `accrual_canary.collectors[*].last_row_date` | `all_fresh` **and** uptime > 24 h (an uptime < cadence means the container was asleep and the scheduler did not run) |
| `railway_fleet` | external | 1 session | `railway logs -s aat-loop-<role> --lines 50`: last `cycle full exited rc=0 at <ts>` | ts on last session |
| `ci` | external | per push | `ci_watch --sha origin/main` conclusion + `git rev-list origin/main..HEAD --count` | success and ahead == 0 (ahead > 0 ⇒ STALE "unpushed") |
| `accrual_canary` | pc | per probe | reuse `accrual_canary.forecast_accrual` / `collector_liveness` / `n_considered_row` **against the PC paths** | as their status |

### 4.3 Surfaces
- `python -m scripts.health_probe [--json] [--only name,...]` → prints a table sorted
  **DEAD, STALE, UNKNOWN, ALIVE**, writes `backend/data/optimus/health/health_<YYYYmmddTHHMMSSZ>.json`
  (run id in the name, never overwritten — the 09-26 D+E receipt lesson), rc = number of DEAD rows
  (capped 99), and appends one line to `health/health_index.jsonl`.
- Callers: `always_on_lab` gains a `health` loop (period 30 min, $0, no model); `daily_pass` gains a
  final `health` step; `stack_health` becomes a thin wrapper over the same probes (do not keep two
  truth sources).
- `/api/health/full` gains `subsystems: {generated_utc, source: "pc_receipt"|"railway_local", rows: [...]}`.
  On Railway, PC rows come from the newest PC health receipt shipped by the PC (the PC can POST it,
  or commit it — builder's choice), and are `UNKNOWN` when that receipt is older than 2 h. Railway's
  own rows (scheduler, NAV, collectors, uptime) are computed in-process.
- Telegram digest (`telegram_agent.daily_jobs`) and `night_morning_report.render` print the
  DEAD/STALE rows **first**, one line each: `DEAD telegram_agent — last poll 2026-09-23T01:07Z (3.5 d); proof: pid 73584 not running`.

### 4.4 Tests (minimum)
1. Every probe with its evidence file absent ⇒ `UNKNOWN` (parametrised over all probes, using a
   tmp data dir). **This is the test Murat asked for.**
2. A lab status file with a fresh `utc` but a pid that does not answer ⇒ `DEAD`, not `ALIVE`.
3. Bars with `max(date)` one session behind ⇒ `STALE`; the probe never calls `stat()`
   (AST guard over the module, docstrings skipped).
4. A forecast ledger whose `made_at` rows are fresh but whose `resolved_at` has not moved while
   due rows exist ⇒ grader `STALE` (the scoreboard-over-a-dead-ledger case).
5. `railway_backend` with `uptime_seconds: 13` and `all_fresh: false` ⇒ `STALE` with "container
   was asleep" in detail.
6. Fixtures derive dates from `today` (protocol item 5); no literal dates.

---

## 5. Verdict — the three worst things, and the order to fix

Ranked by *how long it can stay broken unnoticed × what it costs*.

1. **The bars panel is a static file again (`max(date)=2026-09-21`, no scheduled refresher, no
   age gate).** Unnoticed: indefinitely — every consumer reports a *skip* ("bars unchanged"), not a
   fault. Cost: the PC-PAPER plan acts on a stale ranking; every forward book, the morning
   `nav_vs_spy`, the 241 books entering Monday and the 2026-10-26 bridge reading are graded only
   through 09-21; `freeze_gate` can never pass; two learn units are permanently idle. This is the
   `funnel_night10.json` failure of 09-22 in a new file. **Fix first:** a scheduled bars refresh in
   `daily_pass` (the P6 puller, out of process, refuses without overwriting on failure) + an age
   gate in `u_rank` that turns the plan into `REFUSED: bars N sessions old` + the `bars_panel` probe.
2. **The Railway website backend is being put to sleep, so its in-process scheduler has not run a
   daily job since ~09-18.** Evidence: uptime 13 s and a 10 s cold start on first request; "Stopping
   Container" 8 min after a deploy with no redeploy; all ten lane NAVs at 09-18; five collectors at
   09-17; `last_mtm: null`. Unnoticed: 8 days so far, because `scheduler.running: true` is read from
   the process the probe just woke, and the site's DEGRADED line is permanently red for an
   unrelated reason (R6). Cost: the public track record (inception 06-08, 110 days) has an 8-day
   hole that cannot be backfilled honestly; every PI collector's forward IC trial stopped accruing.
   **Fix (attended — production):** Murat turns serverless/app-sleeping off for `Aegis-Finance`
   (or moves the jobs to a Railway cron service), removes the dead `arena_paper_repair_once.py`
   start command; then R6 is re-pointed so the site's red means something. Verify with
   `verify-prod-after-deploy`: `nav.all_fresh` true after the next 16:30 ET.
3. **The Telegram agent has been dead since 2026-09-23 01:07Z with no supervisor, and the one
   health check for it said READY.** Unnoticed: 3.5 days and counting; `stack_health` would keep
   saying ok. Cost: the operator surface Murat was told to use (`/sim`, `/brief`, `/research`), the
   daily digest, and — from 09-30 — the promise grader's only caller (OPENCLAW doc owed hook 1) are
   all off. **Fix:** add `grade_promises` to `daily_pass` STEPS (the exact patch is in
   `docs/OPENCLAW_2026-09-26_LOCAL_SERVICE.md` §Owed hooks); run the agent under the lab as a
   supervised driver (restart on death, pid written without BOM) with a heartbeat row; change
   `stack_health.check_telegram` to read that heartbeat.

Then, in order: F15 (ignore `.env.bak*` — one line, but a public-repo key leak is irreversible;
do it before anything is committed); `system_health.py` + `scripts/health_probe.py` + its lab loop
(§4); F1 (per-tick status rows); R2 (holdings-based gross cap + same-asof PROBE exits + share-class
dedup); R4 (one mandate table for the PC-PAPER account, printed on every plan); R5 (`stuck_counter`
on the PC contracts); R3 (either wire `policy_state` into `u_plan` or delete the unread keys —
a declared preference nothing reads is a promise the night keeps to nobody); R9 (void or re-source
the 130 stuck forecasts, attended); F16 (re-link the CLI to `selfless-courage`, attended); F19
(schedule `refresh_aegis.py` after `daily_pass`).

*Not verified here:* why the Telegram agent exited (no exit record exists — itself a finding);
whether Railway's stop is the serverless setting or a platform eviction (the dashboard setting was
not readable from the CLI); the terminal repo's code; `AegisAnalystPanelDaily`'s own receipt.
