# Silent-fragility audit — TRIAL-CONGRESS-IC collector, 2026-09-20

Read-only audit per `.claude/skills/silent-fragility-audit/SKILL.md`. No edits
outside this file, no LLM calls, no orders, no state-changing git commands.

## Path traced (file:line)

1. `backend/services/portfolio_intelligence/scheduler.py:261-267` —
   `pi_congress_collect`, `CronTrigger(hour=7, minute=30, day_of_week="mon-fri",
   timezone="US/Eastern")` → `_congress_morning_collect`.
2. `scheduler.py:1187-1205` — `_congress_morning_collect` (decorated
   `@receipted()` then `@_gated`). Body: `try: cg = await asyncio.to_thread(
   collect_congress_scores) ... except Exception as e: logger.error(...)`. **No
   re-raise, no `JR.note()` call.**
3. `backend/services/portfolio_intelligence/congress_collector.py:35-54` —
   `collect_congress_scores`: `fetch_congress_trades` (raises on source
   failure) → `compute_congress_scores` → `collect_pit_scores`.
4. `backend/services/congress_trades.py:40-79` (`_fmp_get`) — budget check
   `fmp_budget.try_spend(priority=True)` (line 48), then the live HTTP call
   (line 53), 402 handling (line 58-69).
5. `backend/services/portfolio_intelligence/pit_score_collector.py:33-71` —
   the PIT write (`snapshot()`, throttled 5 days, `backend/db.py:483` writes
   `payload_json = json.dumps(payload, sort_keys=True)` into the row — **the
   payload column is already a JSON blob**, relevant to the fix below).

## Findings, ranked

**F1 — the collector's "fail loud" contract is swallowed one hop up the stack.
Silent today. Fix now.**
`congress_trades.py` and `congress_collector.py` are correctly written to
raise on any source failure (both files say so in their own docstrings and do
it: `fetch_congress_trades` raises on 402, on empty page 0, on unparsed
payload). But `scheduler.py:1200-1205` wraps that raise in its own
`try/except Exception: logger.error(...)` and does not re-raise. The
`@receipted()` wrapper's own except block (`job_receipts.py:202-205`, sets
`status="raised"`) never sees the exception, because it never leaves
`_congress_morning_collect`. Net effect: a hard FMP failure and a clean
success both produce `status: "ran", exception: null` on the receipt. This is
confirmed live (see Production, below) — 15/15 production receipts show this
identical shape.
*Fix (~2 lines): drop the try/except in `_congress_morning_collect` and let
`@receipted()`'s own handler set `status="raised"` + capture `exception`, or
add `except Exception as e: JR.note(...); raise` inside it.*

**F2 — `writes: null` is a dead field for this job, not a report of zero
writes. Silent today, mildly misleading. Fix now.**
`job_receipts.note(writes=...)` (job_receipts.py:94-113) is the only thing
that ever sets `r["writes"]`; the `@receipted()` wrapper itself never
populates it from the function's return value. `grep -n "note(" scheduler.py`
returns **zero matches in the entire file** — no job registered in
`scheduler.py`, congress included, ever calls it. (`_ownership_collect` gets
real content into its receipt, but via its own bespoke
`_write_collection_receipt`, `scheduler.py:1258-1276`, which bypasses this
field entirely.) So `writes: null` on every congress receipt means "nobody
annotated this," not "zero rows written" — the backtest doc's reading of it as
suggestive evidence of failure is not wrong in conclusion but is not
supported by that field specifically.
*Fix (~1 line): `JR.note(writes=cg)` right after `cg = await
asyncio.to_thread(collect_congress_scores)` — `cg` is already the summary
dict (`{"status", "n", "written", "nonzero", ...}`) and is already logged, just
never attached to the receipt.*

**F3 — the "07:30 ET is when the quota is fresh" premise is false by
construction. Silent today (not paged). Backlog / fix soon.**
`fmp_budget.py:20` states the ledger's day boundary is **UTC**
("day boundary is UTC (FMP's observed reset)"), but `congress_collector.py:1-14`
and `scheduler.py:255-260`'s comment justify the 07:30 ET slot as "when the
shared FMP daily quota is fresh." 07:30 ET is 11:30-12:30 UTC — roughly
halfway through the UTC budget day, not near its start. Any fallback/warm-loop
FMP traffic from 00:00 UTC (≈19:00-20:00 ET the prior evening) through the
morning can exhaust the shared, in-process ledger — or the real FMP
account-level quota — before congress's "fresh" slot fires. This is
structurally the same failure the backtest hit this evening (live 402,
`fmp_budget` had counted only 1 spend from this run, i.e. someone else's
traffic burned it). `fmp_budget.snapshot()` is surfaced on `/api/health/full`
(`fmp_budget` key) but `exhausted`/`denied` are **not** folded into
`_degraded_reasons` (`backend/main.py:1107-1139` — only `nav`, forecast
populations, IC funnel, and scheduler job drift page today).
*Fix (~5-10 lines): add `if fmp_budget.snapshot().get("exhausted"):
_degraded_reasons.append(...)` to `main.py`'s existing reason-building block,
same pattern as the other checks already there.*

**F4 — member identity is aggregated away before the PIT write. Not silent —
documented design choice, but a structural ceiling. Confirmed independently
by tonight's backtest.**
`congress_trades.py:154-201` (`compute_congress_scores`) builds per-symbol
`buyers`/`sellers` **sets** of `member_id` but only `len()` survives into the
stored payload (`n_buy_members`, `n_sell_members`) — the identities are
discarded at function return. Matches the frozen registration
(`congress_collector.py:84`, `params_frozen`: "distinct-member counting... no
amount weights") — this is intentional, not a bug in the accrual path — but it
means no member-conditioned question (leadership, committee, repeat-offender)
is answerable from `congress_score:*` as built.

## Production check (no credentials) — `aegis-finance-production.up.railway.app`

- `/api/health/full`: top status `DEGRADED` (unrelated reason: 26 stale
  `live_forward` forecasts). `scheduler.jobs.status = "ok"`, `missing: []`,
  `unexpected: []` — `pi_congress_collect` **is** registered, live, next run
  `2026-09-21T07:30:00-04:00` (correct — today, 09-20, is Saturday-analog
  Sunday, cron is mon-fri only, so no run was expected today).
  `fmp_budget` today: `spent=0, denied=0, exhausted=false` (consistent with no
  run today). `data_sources` has no FMP entry at all (only `yfinance`, `fred`)
  — FMP health is invisible on that specific canary.
- `/api/optimus/job_receipts?limit=10` (route exists:
  `backend/routers/optimus_ledger.py:36-97`, reads `JR.known_jobs()` off the
  Railway volume) — **this is the live evidence the local repo couldn't see**,
  confirming CLAUDE.md's "absence of a local object is not evidence of
  absence": production's `congress_morning_collect` has **15 receipts**
  (2026-09-01 → 09-18 weekdays, not just the one local 09-07 receipt), every
  single one: `status: "ran", exception: null, writes: null, duration_seconds`
  in a **tight 0.27-0.33s band** across five different days and two different
  deploy commits (`92efb9d8...`, `1be531ad0...`).
  A real fetch (two chambers, FMP HTTP round-trips, up to 8 pages each) would
  not land in a ~300ms band that consistently across days/commits/deploys —
  that duration signature is far more consistent with something
  short-circuiting before any network call: either the 5-day PIT throttle
  (`pit_score_collector.py:44-47`, an early `return` before any fetch) or the
  in-process `fmp_budget` ledger denying the call before the first HTTP
  request (`congress_trades.py:48-52`, `RuntimeError` with no network I/O).
  **F1 and F2 together are exactly why this cannot be resolved further from
  the outside**: neither receipt field distinguishes "quietly throttled" from
  "quickly denied" from "fetched successfully in an unusually fast run," and
  the exception (if any) never reaches the receipt.

No router exposes `pit_observations` row counts or a congress-specific
`last_run`/success field directly (`grep -rln "pit_observations" backend/ |
grep -v tests` finds no router); `/api/optimus/job_receipts` is the closest
available signal and it is timing evidence, not a row count.

## FMP quota (item 3)

`fmp_budget.py:39-71`: `daily_budget=240`, `priority_reserve=40` (config
`fmp.daily_budget`/`fmp.priority_reserve`, else these defaults). Congress
calls `try_spend(priority=True)` (`ceiling = budget`, i.e. all 240, not
240-40). But `mark_exhausted()` (line 74-83) sets `_STATE["exhausted"]=True`
globally on ANY live 402 from ANY caller, and the exhausted check
(`_STATE["exhausted"]` at line 59) is checked **before** the priority ceiling
— so a non-priority caller's 402 anywhere else in the UTC day denies the
priority congress collector too, for the rest of that UTC day. Given F3's UTC
vs. ET mismatch, that window is wide open every morning. The ledger is also
in-process/in-memory (line 20-22 docstring: "resets on process restart") — a
Railway redeploy silently un-exhausts it regardless of the real account-level
state, which is a second reason the local ledger and the FMP-side truth can
diverge in either direction.

## Verdict table

| # | Failure mode | Where | Silent today? | One-line fix |
|---|---|---|---|---|
| F1 | fail-loud raise swallowed by the job's own try/except before `@receipted()` sees it | `scheduler.py:1200-1205` | Yes — confirmed live, 15/15 prod receipts identical shape | remove the try/except (or re-raise after `JR.note`) so `@receipted()`'s own handler sets `status="raised"` |
| F2 | `writes` field never populated — `note(writes=...)` called nowhere in `scheduler.py` | `scheduler.py` (whole file) | Yes | `JR.note(writes=cg)` after the collect call |
| F3 | "quota fresh at 07:30 ET" false — ledger's day boundary is UTC, ~11-12h earlier | `congress_collector.py` docstring / `scheduler.py:255-260` comment vs `fmp_budget.py:20` | Yes — not paged in `/api/health/full` | fold `fmp_budget.snapshot()["exhausted"]` into `main.py`'s `_degraded_reasons` |
| F4 | member identity discarded before PIT write | `congress_trades.py:154-201` | No — documented, by design | see minimal fix below |
| F5 | no router exposes `pit_observations` row counts (congress or otherwise) | repo-wide | Not exactly silent, but unobservable | out of scope tonight |

## Minimal fix to keep member identity (sized)

Cheapest viable option, found while tracing F4: the PIT `payload` column is
**already a JSON blob** (`backend/db.py:503`,
`payload_json = json.dumps(payload, sort_keys=True)`), and
`compute_congress_scores` already builds a `buyers`/`sellers` **set** of
`member_id` per ticker before collapsing it to counts
(`congress_trades.py:175, 185-187, 193-200`). No new key prefix, no schema
migration, no signature change to `collect_congress_scores` or its callers:

```python
# congress_trades.py, inside compute_congress_scores's per-symbol loop,
# where payload is built (~line 194-200):
out[sym] = (score, {
    "n_buy_members": len(a["buyers"]),
    "n_sell_members": len(a["sellers"]),
    "buyer_ids": sorted(a["buyers"]),     # + these two lines
    "seller_ids": sorted(a["sellers"]),   #
    "n_trades": a["n_trades"],
    "n_nonstock": a["n_nonstock"],
    "chambers": sorted(a["chambers"]),
})
```
**~2 lines.** A leadership/committee split then filters existing
`congress_score:*` rows' `payload.buyer_ids`/`seller_ids` against a roster —
no second collector, no new PIT key, no re-registration debate (the frozen
`params_frozen` list covers window/universe/counting/weights, not payload
contents). Still gated on F1-F3 actually letting the collector write rows at
all.

## Not covered

Whether the real, off-ledger FMP account-level quota (vs. the in-process
`fmp_budget` estimate) is the binding constraint on a normal weekday morning —
would need the FMP dashboard or a live credentialed call, out of scope
(read-only, no keys used). Whether production's `aegis_pi.db` actually holds
zero `congress_score:*` rows — no route exposes that count; the 0.3s receipt
timing is circumstantial, not a row count.
