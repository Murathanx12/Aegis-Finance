# RUNBOOK 2026-09-26 — systems fixes (review 2026-09-26, fix order §5)

Source review: `docs/reviews/REVIEW_2026-09-26_SYSTEMS_ATTACK_AND_HEALTH_PROBES.md`.
Builder: Opus, 2026-09-26 23:00–00:00 HKT. No order placed, no limit changed, `.env` not opened.

## RESULTS SCOREBOARD
| line | state |
|---|---|
| best forward paper strategy | **now readable again**: the bar panels end 2026-09-25 (were 2026-09-21) |
| new actionable finding | `n_considered: 2` is the POST-gate count; 16 of 25 funnel names score ≤ 0 under the committee's own registry (below) |
| LLM spend | $0.00 |

**RESULT IMPROVEMENT: NONE** (plumbing: every change restores or surfaces evidence; none changes a selection).

---

## 1. What was dead, and what was done

| # | subsystem | was | now | evidence |
|---|---|---|---|---|
| 1 | bar panels (`prices_2025_26/bars.parquet`, `prices_deep/bars.parquet`, `prices_deep/bars_delisted.parquet`) | newest 2026-09-21 (the 09-21 bar was a MID-SESSION partial: ZYME vol 63,525 vs ~1.1M), no scheduled refresher | newest **2026-09-25**; +12,216 / +12,216 / +835 rows; 61 symbols whose adjustment base moved (splits/ex-dividends) re-pulled whole; 0 duplicate keys | `prices_2025_26/bars_refresh/20260926T151224Z.json`, `bars_refresh_index.jsonl` |
| 1b | refresh caller | none | `daily_pass` step **`bars_refresh` runs FIRST** (out of process, box 1,800 s); receipt top-level `bars:` line | `scripts/daily_pass.py` |
| 1c | age gate | none; `u_rank` printed "bars unchanged" as a normal skip | `config.BARS_MAX_AGE_SESSIONS = 2`; `sim_run.u_plan` **REFUSES** (EXPLOIT and PROBE, before any broker call or ledger write) when the ranker's base panel OR `ranking.json.asof` is > 2 closed XNYS sessions old; receipt `verdict: REFUSED_BARS_STALE`, `bars_line: BARS_STALE: newest=<date> sessions_old=<n>`; the `u_rank` skip now carries the age line | `scripts/sim_run.py` `bars_gate()` |
| 2 | `n_considered: 2` (09-20 → 09-26) | read as "the ranker saw 2 names" | root cause below; the contract receipt carries `candidate_set` and `roi_ranking.{candidates_source, n_candidates, candidates_generated_at}` | `decision_contract.candidate_set()` |
| 3 | 130 unresolvable forecasts | `NO_BAR_FOR_RESOLUTION_DATE: 130`, status `nothing_to_do`, daily since August | **130 VOIDED** on 2026-09-26: 123 `UNRESOLVABLE_DELISTED` (AVB 96 — bars stop 2026-08-14; EA 27 — bars stop 2026-08-04; both `inactive` at the venue), 7 `UNRESOLVABLE_NO_EQUITY_BAR` (CL=F ×2, ES=F, ZN=F, GC=F, DX-Y.NYB, ^VIX). Receipt field `voided_unresolvable`; `daily_pass` row is `ok` when it voided | `night_factory_2026-09-26/grade_forecasts_2026-09-26.json` |
| 4 | contract caps | `capital_usd 40000` beside a worst case priced on $1,000,000; four per-name caps | ONE capital base (the contract's own), worst case priced on it, `mandate` block that **REFUSES** when bases/caps disagree (it does today) | `decision_contract.account_mandate()` |
| 5 | Telegram agent | dead since 2026-09-23 01:07Z, no supervisor, `agent.pid` = BOM + dead pid | Scheduled Task **`AegisTelegramAgent`** (at logon, restart-on-failure ×999/1 min, no time limit) runs `--supervise`, which restarts `--serve` on exit or on a heartbeat older than `TELEGRAM_AGENT_HEARTBEAT_MAX_AGE_S` (600 s); restart proven by killing the child by PID (back in ~10 s) | `telegram/agent.log`, `telegram/heartbeat.json`, `telegram/supervisor.jsonl`, `telegram_agent_lock.json` |
| 6a | promise grader | no scheduled caller | `daily_pass` step `grade_promises` (after `grade_forecasts`), through `model_routing.grade_promises_daily` (the stamp is shared with the Telegram digest, so it runs once per UTC day whichever fires first; skips before 2026-09-30 by its own config) | `scripts/daily_pass.py` |
| 6b | lab ↔ llama_server | lab never `touch()`ed | `always_on_lab` calls `llama_server.ensure("lab:l2_typing", wait_s=0)` before the typing batch (only when a server is already LISTENING — it never starts one) and `touch()` after it | `scripts/always_on_lab.py` `_lab_llama()` |

### The `n_considered: 2` root cause (task 2)

Traced hop by hop on 2026-09-26 (`funnel_state(use_cache=False)` on the live funnel):

| hop | size | age |
|---|---|---|
| `backend/data/funnel_night10.json` (`candidates_source`) | **25** | generated 2026-09-24T02:48:34Z (2.5 d) |
| `recommendation.score_candidates` | 25 scored: **16 HOLD**, **7 NO_ACTION**, 2 WATCH | same |
| `compose_book` step-1 eligibility gate (verdict ∈ {BUY, WATCH}, evidence ≠ NO_EVIDENCE, ranking_score > 0) | **2** (SON, ALLE) | same |
| `roi_ranking.n_considered` | **2** | — |

The funnel refresh DID reach the contract (09-24 → 40 names/CVLG+INDV; 09-25 → 25 names/SON+ALLE; the universe hash changed). `n_considered` counts names AFTER the eligibility gate, and the committee's own registry scores 16 of the funnel's 25 profitability-selected names NEGATIVE (ranking_score −0.14 … −0.93, evidence SUPPORTED) and has no licensed evidence for 7. So the "stuck at 2" is two layers (funnel selects on `profitability_small`; the committee scores on its licensed registry) disagreeing about the same names, printed as one opaque number. **Fixed here: the receipt now prints every hop** (`candidate_set.line`, e.g. `candidates 25 (funnel_night10.json, generated 2026-09-24T02:48:34+00:00, 2.5 d old) -> 25 scored {'WATCH': 2, 'NO_ACTION': 7, 'HOLD': 16} -> 2 eligible for the ROI ranking (= n_considered); excluded: 16 ranking score <= 0, 7 no licensed evidence (NO_EVIDENCE)`). **Not changed:** the gate or the registry — whether a funnel name the committee scores negative should be considered is a rule change for Murat, not plumbing.

### The mandate line as it now prints (task 4)

```
MANDATE REFUSED: capital $40,000; per-name cap 2% (tightest: config.PROBE_MAX_WEIGHT (u_plan PROBE));
as configured: 18 EXPLOIT x 10% (gross <= 80%) + 10 PROBE x 2% (<= 20%) = sum|notional|/equity 1.00;
x stop 6.48% = -$2,592; no stop, so the ceiling is -$40,000 on $40,000
[on the largest base seen, $1,000,000: -$64,800 k-sigma, ceiling -$1,000,000]
-- 3 disagreement(s); Murat must confirm ONE mandate
```
with `refusals`: `CAPITAL_BASES_DISAGREE` (contract $40,000 / IC_CAPITAL_LEVELS max $1,000,000 / PC-PAPER equity $999,054), `PER_NAME_CAPS_DISAGREE` (PROBE 2% / IC tilt 3% / EXPLOIT 10% / broker 12%), `GROSS_CAPS_DISAGREE` (reachable 1.00x vs tightest 0.10). The `daily_pass` decision-contract row carries `mandate_line` and `candidate_set_line`. `worst_case_largest_admissible_book` is now priced on the contract's capital ($40,000), not $1,000,000.

---

## 2. ATTENDED — for Murat

1. **Confirm ONE mandate for PC-PAPER** (the contract prints REFUSED until you do). Decide: (a) the capital base the contract sizes on — the IPS's $40,000 or the account's ~$1,000,000; (b) the per-name cap that binds the account — today EXPLOIT may size 10%/name (`ER_EXPLOIT_MAX_WEIGHT`) under the broker's 12% (`pc_broker.MAX_NAME_FRAC`) while the committee tilts at 3% and PROBE at 2%; (c) the gross ceiling — EXPLOIT + PROBE can reach 1.00x with **no stop** (worst session at 3σ ≈ −$64.8k on $1M; ceiling −$1M), against a 20% challenge rule. No limit was changed by this build.
2. **Railway website backend is being put to sleep** (review §5 item 2): in the Railway dashboard, project `selfless-courage` → service `Aegis-Finance` → Settings → turn **off "Serverless / App Sleeping"** (or move the APScheduler jobs to a Railway cron service), and remove the dead start/pre-deploy command `python /app/scripts/arena_paper_repair_once.py`. Verify with the `verify-prod-after-deploy` skill: `/api/health/full` → `scheduler.nav.all_fresh: true` after the next 16:30 ET and `deploy.uptime_seconds > 86400` on a later probe.
3. **Re-link this repo's Railway CLI** (F16 — it points at the retired `loving-elegance / aat-loop-hack3`; a `railway up` from here would deploy the website into hack3):
   ```
   cd C:\Users\mrthn\aegis-finance
   railway unlink
   railway link            # choose project: selfless-courage, environment: production, service: Aegis-Finance
   railway status          # must print Project: selfless-courage / Service: Aegis-Finance
   ```
   (non-interactive: `railway link --project <selfless-courage project id> --service Aegis-Finance --environment production`.)
4. **The 130 voids are reversible and are uncommitted**: `backend/data/optimus/predictions.jsonl` is a tracked, growing file with other writers' rows in it, so this build did not commit it. Each voided record keeps every field and gains `void_reason`, `voided_at`, `voided_by: forecast_grader.void_unresolvable`; removing those three fields un-voids it. (`pull_forecast_bars` had declared voiding "Murat's call"; the review §5 asked for it, and it is done in the least destructive form.)

---

## 3. OWED HOOKS (files this build does not own)

1. **Morning report age line** (task 1d): `night_morning_report.render` / `morning_scoreboard.compose` should print the bars age first. One call: `from scripts.pull_bars_refresh import bars_age; line = bars_age()["line"]` → `BARS_STALE: newest=<d> sessions_old=<n> …` or `BARS_FRESH …`. The daily-pass receipt already carries it as `bars`.
2. **`stack_health.check_telegram`** (F2) must read the agent's OWN evidence, not `getMe`: `from scripts.telegram_agent import heartbeat_age_s` → DEAD when `None` or `> config.TELEGRAM_AGENT_HEARTBEAT_MAX_AGE_S` (600 s); proof = `telegram_agent_lock.json.child_pid` alive with `telegram_agent` in its command line. The first log line of a live child is `telegram agent serving as murat_aegis_bot, pid <n>` in `telegram/agent.log`.
3. **`system_health` probes** (§4 spec): `bars_panel` → `pull_bars_refresh.bars_age()` (reads row-group stats, no mtime); `telegram_agent` → as item 2; `forecast_grader` → `grade_forecasts_<d>.json.voided_unresolvable` and `totals.NO_BAR_FOR_RESOLUTION_DATE` (must not grow); `decision_contract` → `mandate.status` and `candidate_set.n_candidates` beside `roi_ranking.n_considered`.
4. **`always_on_lab` running process** (pid 100684 at 23:00 HKT) still runs the OLD code; the `ensure()/touch()` hook takes effect on its next restart (STOP file → Startup-folder relaunch).

---

## 4. Operating the new pieces

- **Bars:** `python -m scripts.pull_bars_refresh --age` (no network, the age line) · `--dry-run` · plain run refreshes all three panels; rc 2 = REFUSED, nothing overwritten. Refuses when: the credential fails, the venue returns nothing, the merged newest date goes backwards, a panel loses symbols, a duplicate (symbol, date) appears, or the swap cannot be made (file held open). Idempotent: a second run with no new session rewrites nothing (so `u_rank`'s fingerprint does not move).
- **Telegram:** `schtasks /query /tn AegisTelegramAgent /v /fo LIST`. Stop cleanly: create `backend/data/optimus/telegram/STOP` (the supervisor kills its child tree by PID and exits; delete the file before the next start). Start now: `schtasks /run /tn AegisTelegramAgent`. Liveness: `telegram/heartbeat.json.utc` < 600 s old. Never kill by image name — the lock names the supervisor pid and the child pid.
- **Grader:** `grade_forecasts_<d>.json` → `voided_unresolvable`, `void.by_reason`, `void.by_ticker`. Rules: `FORECAST_VOID_DELISTED_MIN_SESSIONS = 10` (bars stopped ≥ 10 panel sessions before the newest), `FORECAST_VOID_NO_BAR_GRACE_DAYS = 21` (no bar anywhere, 21 days past resolution), futures/index notations immediately. Quarantined records are never voided.

## 5. Provenance note

The new `backend/config.py` constants (`BARS_MAX_AGE_SESSIONS`,
`FORECAST_VOID_DELISTED_MIN_SESSIONS`, `FORECAST_VOID_NO_BAR_GRACE_DAYS`,
`TELEGRAM_AGENT_HEARTBEAT_MAX_AGE_S`, and the `bars_refresh` / `grade_promises`
step boxes) were written by this build but landed in commit `3ae60413` (Chunk J),
whose builder staged the whole of `backend/config.py` while this build was
running. They are in HEAD; this build's own commit therefore does not touch
`config.py`.

## 6. What remains (not done here, and why)

- The `n_considered` gate/registry disagreement itself (rule change — Murat).
- R2 (PROBE holdings-based gross cap, same-asof PROBE exits, GOOG/GOOGL dedup), R3 (`policy_state` has no reader), R6 (Railway canary on the retired ledger), R7 (four staleness clocks) — outside this build's files.
- The Telegram agent's 09-23 death cause is still unknown (the last log line is a caught `ConnectionResetError` at 00:59:27Z; nothing after 01:07 — no exit record existed). The supervisor now writes one (`supervisor.jsonl` `child_exit` with rc and lived_s).
