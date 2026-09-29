# REVIEW 2026-09-29 — Railway cost changes (build 5 of the 2026-09-28/29 night)

Reviewer: Opus, acting as a sceptical investor. Read-only. Scope: `scripts/railway_cost_check.py`,
`backend/tests/test_railway_cost_check.py`, `docs/NOTE_2026-09-28_RAILWAY_COST.md`, and the local
(gitignored) record under `backend/data/optimus/local_pc/railway/`. No Railway command was run; every
claim below is from files on disk plus one local reproduction of the scheduler's behaviour.

## RESULTS SCOREBOARD

| item | value |
|---|---|
| Result improvement (money) | **NONE** — paper only; bill run-rate ~$53 → ~$48/mo claimed (hack2 stop, −$4.85) |
| Position-holding loops stopped | **0** of 4 (hack1, hack4, hack5, hack6 kept) — correct |
| Loop stopped | hack2, flat and idle since 2026-09-04 — safe |
| Script mutates Railway? | **No** — four GraphQL `query` strings, no `mutation`, no CLI call |
| Secrets printed? | **No** — token used only in the `Authorization` header (`railway_cost_check.py:97`) |
| Website NAV stale since 09-18 | **REAL FAULT**: 6 trading days of close marks missing on 10 public lanes (09-21 → 09-28), and the proposed cheap remedy **would not fix it** |
| Two cost ledgers agree? | **No** — Railway's `currentUsage` $0.74 over 2.02 days vs the priced run-rate implying ~$3.57; nothing reconciles them |
| Score | **62 / 100** |

## Findings, ranked by money / safety impact

### 1. The wake-cron remedy for the stale NAV cannot work: missed slots are never caught up after a cold boot (HIGH — the public track record)

- **Claim** (`docs/NOTE_2026-09-28_RAILWAY_COST.md:25-28`, `RAILWAY_CHANGES_2026-09-28.md:69-73`):
  "APScheduler only catches up a missed slot if the app is awake within its one-hour grace. Keep it
  awake, or wake it in the grace windows from a free cron"; remedy (b) wakes the site at 20:40Z and
  22:50Z (`wake_website_workflow.yml.draft`), "~+$0.5/mo".
- **Evidence.** Every wake of the sleeping Railway service is a **new process**
  (`website_logs_2026-09-28.txt`: `Started server process` / `Scheduler started` 13:18 → `scheduler
  stopped` 13:26; again 14:07 → 14:18 — each awake window is 8–11 minutes). Every job is registered on
  boot with `replace_existing=True` (`backend/services/portfolio_intelligence/scheduler.py:204-215` for
  `pi_hourly_mtm`, and every other job). In APScheduler 3.11 (the installed version), a job added
  before `start()` gets its `next_run_time` computed **from now** at start, overwriting the persisted
  one — so `misfire_grace_time=3600` never applies across a restart. Reproduced locally with the same
  jobstore class and the same flags: boot 1 recorded next run 10:49:30 and shut down; boot 2 after that
  slot scheduled 10:50:00 and **the missed slot did not run**.
- **Consequence.** A wake at 16:40 ET boots, schedules the MTM for 17:30, and sleeps again at ~16:50.
  A wake at 18:50 schedules 19:30 and sleeps at ~19:00. `pi_daily_check` (hour 16 only) and the ARENA
  pass never run. The draft's comment that EST is covered "via the next slot" is also wrong: after the
  1 Nov clock change 20:40Z is 15:40 EST (before the 16:30 slot) and 22:50Z is 17:50 EST. The
  scheduler's own comment (`scheduler.py:195-201`) says "a missed close mark is an unrecoverable gap in
  the track record"; six are already missing, and the draft would add one per weekday while the note
  presents it as a $0.5 fix.
- **Fix.** Either (a) turn sleep off for the website (the note's own estimate +$4–6.5/mo), or (b) a
  wake that lands **before** the slot and keeps traffic alive through it (e.g. pings every 5 min from
  16:20 to 18:00 ET, written for both EDT and EST), and then **verify the first mark landed**
  (`/api/health/full` → `scheduler.nav.lanes.*.last_nav_date`) instead of trusting the cron. A code-side
  option: on boot, if today's close mark is missing and it is after 16:30 ET, run `_hourly_mtm` once
  (it already self-skips when the mark exists).
- **Who decides.** Owner (money: sleep off vs cron). Builder owns the boot catch-up if chosen.

### 2. The public track record has been dark for ten days and "DEGRADED" paged no one (HIGH)

- **Claim.** "PRE-EXISTING, not caused tonight" (`RAILWAY_CHANGES_2026-09-28.md:65`).
- **Evidence.** `health_after.json` → `scheduler.nav.lanes`: all ten lanes `last_nav_date 2026-09-18`;
  `degraded_reasons` carries "nav not fresh" and "forecasts have stopped accruing (newest
  2026-09-18T21:16Z)"; `prediction_ledger`: 169 forecasts past due and unresolved. CPU fell to ~0 on
  09-20/21 when `AEGIS_WARM_SKIP=1` was set (`backend/config.py:2826-2838`) — the cost fix of 09-20 is
  what silenced the close jobs, so it *was* a cost change, just an earlier one.
- **Consequence.** The website's forward evidence (inception 2026-06-08) now has a 6+ trading-day hole
  that cannot be backfilled under the no-backfilled-forward-evidence rule, and live_forward forecasts
  are not being resolved. The attribution to sleep is right; calling it pre-existing understates that
  the 09-20 warm-skip shipped with no check that the scheduler still fired — the "scoreboard over a
  dead ledger" shape again.
- **Fix.** Decide #1 today; wire the health route's `nav not fresh` into the Telegram alert lane so a
  second consecutive day pages. Print the missing dates in the track-record receipt instead of letting
  the chart draw straight across them.
- **Who decides.** Owner for the money; builder for the alert.

### 3. The two cost ledgers disagree by ~5× and the projection adds them (MEDIUM)

- **Claim.** "bill ~$50 this period" (`cost_checks/railway_cost_20260928T143405Z-fa41f5.json`).
- **Evidence.** That receipt: period start 2026-09-26T14:03Z, reading 2026-09-28T14:34Z (2.02 days),
  `usage_so_far_usd 0.74`, `run_rate_usd_month 52.98`. 52.98 × 2.02 / 30 ≈ **$3.57** expected so far
  vs **$0.74** reported by Railway. `check()` then sums the two (`railway_cost_check.py:190-193`). The
  previous period's $58 (priced the same way) matches the owner's ~$60 invoice, so the per-service
  pricing is probably right and `currentUsage` lags — but nothing checks which.
- **Consequence.** A few dollars directly; but the Telegram line will report a projection whose first
  term is wrong early in every period, and a keep/stop decision could be made off the wrong ledger.
  Same family as "a cap that reads a different ledger than the writer cannot bind".
- **Fix.** Price usage for `[period_start, now]` with the same usage query, print it beside
  `currentUsage`, and print `LEDGERS DISAGREE` when they differ by more than 25%.
- **Who decides.** Builder.

### 4. hack5's BE call spread expires 2026-10-16 inside a loop whose restart policy can give up (MEDIUM, paper)

- **Evidence.** `alpaca_state_2026-09-28.json`: hack5 long 7 × BE 2026-10-16 C290, short 7 × C320,
  equity $91,798. `RAILWAY_CHANGES_2026-09-28.md:12,14`: hack5 and hack1 (574 SYM, 1 open order) run
  with restart policy `ON_FAILURE/10` — a clean exit is not restarted and ten failures leave it down.
  The note treats the expiry only as the date after which the loop can be stopped.
- **Consequence.** If the loop is down, or does not handle expiry, an in-the-money long 290 call is
  auto-exercised into ~700 shares — roughly twice the account's equity if BE trades near $300; above
  320 both legs exercise/assign. Paper money only, but it is exactly the case a real-money executor must
  survive.
- **Fix.** Confirm in the terminal repo that hack5 closes or rolls the spread before 10-16 close; set
  position-holding loops to `ALWAYS`; do not stop hack5 until the spread is closed.
- **Who decides.** Owner (hack5's mandate); builder in the other repo.

### 5. The website's own Alpaca targets were not in the "who holds positions" check (LOW-MEDIUM)

- **Evidence.** `health_after.json` → `paper_broker.targets`: `lane:mirror` and `arena:CURRENT_BEST_v1`,
  credentials `present`. `alpaca_state_2026-09-28.json` reads hack1–hack6 only. `execution_ledger` is
  `ABSENT` ("no external order has been submitted yet") and grep finds no `submit_order` path in
  `backend/services/portfolio_intelligence/`, so probably nothing is held — but it was not read.
- **Consequence.** The note's principle ("a stopped loop cannot manage exits") was applied to the loops
  and not to the website. If sleep is turned off (#1), `pi_arena_daily` and `pi_daily_check` resume in
  one pass after ten idle days.
- **Fix.** One read-only positions GET for those two credentials, recorded beside the others, before the
  #1 remedy is chosen.
- **Who decides.** Builder (the read); owner (whether the website should hold a broker key at all).

### 6. hack3 is an ownerless account the record calls "evidence" (LOW, paper)

- **Evidence.** `docs/ACCOUNTS_2026-09-22_THE_PAPER_FLEET.md:18`: hack3 9 positions, $80,821 on 09-22;
  now HTTP 401 (`alpaca_state_2026-09-28.json`). `RAILWAY_CHANGES_2026-09-28.md:86-87` offers "keep as
  evidence or delete" for its volume without mentioning the nine positions nobody can see or close.
- **Consequence.** No money; its NAV is unmeasurable, so it is neither evidence nor a live book.
- **Fix.** Record it as `ABANDONED_UNREADABLE` with the last known state; regenerate a key only if the
  owner wants the final number.
- **Who decides.** Owner.

### 7. Small, not money

- The script has **no caller**; the note says the line is "suitable for" the Telegram report
  (`NOTE:36-38`), not that it is wired. "Monthly" depends on someone remembering.
- `check()` reads only `workspaces[0]` (`railway_cost_check.py:161`); a second workspace would be
  silently omitted. Print the workspace count.
- The rollback commands and the hack2 backup exist on one disk only (gitignored by design,
  `.gitignore:394`). Right privacy call; a second copy of the backup is owed.
- Change 2 (removing `arena_paper_repair_once.py` from the start command) is a genuine hazard removal: a
  "temporary" hook that would have run a decision pass and submitted paper intent on every wake had the
  file come back.

## Answers to the questions asked

- **Anything holding positions put at risk?** Not by tonight's change: hack2 was flat and idle since
  09-04 (checked twice, `RAILWAY_CHANGES:26`) and backed up with a verified SHA-256 first. Open risk is
  hack5's expiry (#4) and the unread website targets (#5).
- **Does the script mutate Railway?** No. Only `Q_ME`, `Q_WORKSPACE`, `Q_PROJECTS`, `Q_USAGE`
  (`railway_cost_check.py:113-121`). The night's one mutation (`railway down` on hack2) was done by hand
  and recorded with its rollback.
- **Secrets?** The token is read from env or the CLI config (`:77-86`), used only in the header, and
  never written — the `Reading` dataclass has no token field; errors carry only HTTP codes.
- **Website NAV stale since 09-18?** A real fault. The writer is the in-process `pi_hourly_mtm` →
  `mark_all_lanes`; it is not dead, it is never awake at 16:30–19:30 ET, and the proposed cron would not
  change that (#1).

## Score: 62 / 100

Careful wherever it touched positions (flat-check twice, verified backup, written rollback) and honest
about UNKNOWN, but the one thing actually costing the project — ten days of missing public NAV — got a
remedy the scheduler's restart semantics make inert, and the cost reading adds two ledgers that disagree
fivefold.

## WHAT WORKS

- No position-holding loop was stopped; the flat check was done twice, read-only.
- Backup before removal, verified by size and SHA-256 in both places; rollback commands recorded.
- The script is read-only, never prints the token, reports UNKNOWN (exit 2) instead of $0, derives its
  window from `now`, names deleted services instead of dropping them, writes a run-id receipt.
- The dangerous `arena_paper_repair_once.py` hook is gone from the website's start command.

## WHAT DOES NOT

- The stale-NAV remedy (wake inside the grace window) cannot fire a missed job after a cold boot, and
  its DST handling is wrong.
- `currentUsage` and priced usage disagree ~5×, and the projection adds them.
- hack5's option expiry and `ON_FAILURE` restart policy on two position-holding loops are open.
- The website's own two Alpaca targets were not read.

## HIGHEST-EV EXPERIMENT

Turn website sleep off for **one** weekday (cost about $0.20) and read `/api/health/full` at 20:00 ET.
If all ten `last_nav_date` equal today, the diagnosis is proven and the owner chooses between sleep-off
(~$5/mo) and a boot-time catch-up; if they do not, the sleep story is wrong and the real writer fault is
still hidden. Either outcome stops the track-record hole growing, which is worth more than every dollar
saved this week.
