# REVIEW 2026-09-29 — the morning test fixes in c0ac5310

Adversarial investor review (Opus). Scope: the test changes shipped in commit
`c0ac5310` that the commit message calls fixes — the telemetry-silencing context
manager, the UTC-midnight fake clock, the bridge-report cache fixture, the
`web_reader.store_social(root=)` path — plus the one test whose ASSERTION was
inverted in the same commit (the gateway memory floor). Question asked of each:
did the fix make a test green by making it weaker?

## RESULTS SCOREBOARD

| item | value |
|---|---|
| RESULT IMPROVEMENT | NONE (hygiene; no money path touched) |
| CI on `c0ac5310` | green (`python -m scripts.ci_watch`: CI success 2026-09-29T00:32:59Z, Prod monitor success) |
| fixes reviewed | 5 |
| fixes that weakened a test to go green | **0** |
| assertions inverted in the same commit | **1** (the gateway memory floor): a deliberate behaviour change, not a weakening, but its docstring now states the old rule and its blast radius was not tested |
| new production-side coverage added by the fixes | 3 (retry budget keyed on the forecast day; the audit reads the writer's month files; importing the audit no longer silences telemetry) |

**Score: 80 / 100** — every fix pins an input or scopes a side effect rather
than loosening a number, and two add a production-side test; points off because
the one inverted assertion dropped a rule that came from a measured kill test,
left the docstring stating the old rule, and gave the new reclaim path the power
to close every tab of the dedicated Chrome with no test of who else was using it.

## Findings, ranked by money / safety impact

### F1 (safety, medium) — the memory floor was inverted, the docstring still states the old rule, and the reclaim path closes every tab in the dedicated Chrome

- **Claim.** "a repair that reclaims memory instead of refusing" (commit message).
- **Evidence.** `backend/tests/test_lane_o_muratclaw.py` (c0ac5310) replaced
  `test_no_gateway_start_under_the_memory_floor` (asserted
  `stopped_because.startswith("LOW_MEMORY")` and `w.cmds == []`) with
  `test_under_the_memory_floor_the_repair_reclaims_then_proceeds` and
  `test_a_reclaim_that_cannot_clear_the_floor_still_does_not_block_the_repair`
  (asserts `["gateway","start"] in w.cmds and r["healthy"]` with free memory
  still at the sub-floor value). The production change is
  `backend/services/gateway_repair.py:396-409`. The docstring of the same
  function, `gateway_repair.py:331-333`, still says "NO gateway (re)start below
  `OPENCLAW_REPAIR_MIN_FREE_GB` ... a started gateway did not bind its port for
  a long time". That rule came from the 2026-09-28 kill test; the new code
  does what the measurement said fails.
- The reclaim default is `reclaim_memory(need_gb=need)`
  (`gateway_repair.py:270-271`) with **no `own_tab_ids`**, so `close_idle_tabs`
  (`gateway_repair.py:653-684`) closes "every other page of the dedicated Chrome"
  and `recycle_dedicated_chrome` (`:687-734`) then restarts it. Its own docstring
  says it is "called only when no reader runs"; nothing in `repair()` checks
  that. The supervisor calls `GR.repair` from four places
  (`scripts/night_reader_supervisor.py:392, 642, 692, 779`). Any other process
  sharing the dedicated Chrome at that moment (another reader lane, a social
  pull, an attended browser-agent session in the MuratClaw profile) loses its
  tabs mid-page.
- The replacement tests pass because the fake frees memory (`w.free = 1.9`) or
  the fake gateway binds at once; the real failure the old test encoded (a
  gateway that takes 15+ minutes to bind under pressure) is not represented. The
  bounded wait and the "never start a second tree" branch
  (`gateway_repair.py:411-433`) still hold, which is the part that matters most.
- **Consequence.** Not a test made green by loosening: it was rewritten to a new
  spec. But a reader of `repair()` trusts a rule the code no longer follows, and
  a tab the repair did not open can be closed. No position is at risk (the
  reader holds none).
- **Fix.** (a) Rewrite `gateway_repair.py:331-333` to state the new rule and why
  the kill-test evidence is overridden. (b) Pass the reader's own tab ids into
  `reclaim`, close only those before a recycle, and refuse the recycle when a
  live lock from another lane or an attended browser session exists. (c) Add one
  test where free memory stays below the floor and the fake gateway binds slower
  than the wait, asserting `stopped_because` names the slow bind and no second
  start happened.
- **Who decides.** Builder for (a) and (c). Owner for (b): whether an unattended
  repair may ever interrupt an attended session in the dedicated Chrome.

### F2 (low) — the bridge-report fixture is a correct isolation, and it hides a production behaviour worth one receipt line

- **Evidence.** `backend/tests/test_bridge_report.py:21-31` point
  `global_prices.cache_path` at an empty tmp path. Root cause per its docstring:
  `llm_portfolio.union_bars` (`backend/services/llm_portfolio.py:1195-1212`)
  keeps ONE source per symbol, whichever reaches the later date, so the real
  cache's IWM replaced the synthetic one.
- **Judgement.** Not a weakening: the test passes its own `bars` and must not
  read the machine's cache. Right fix (pin the input, the family of
  `feedback_a_test_that_derives_from_a_growing_local_dataset`).
- **Production note.** In production one extra day in the global cache makes
  the cache's WHOLE history replace the panel's for that factor ETF
  (`scripts/bridge_report.py:435-446`). If the cache holds a shorter window than
  the panel, factor betas are silently fitted on fewer months. Print, on the
  bridge receipt, which source each factor ETF came from and its first date.
- **Who decides.** Builder.

### F3 (none) — the UTC-midnight fake clock is sound and adds the production-side test

- **Evidence.** `backend/tests/test_u_forecast_dependency.py:40-67` start the
  fake clock at today's UTC date, 01:00Z (derived from today, not a literal —
  protocol item 5 respected). `test_the_fake_clock_keeps_the_bounded_scenario_inside_one_utc_date`
  proves the old failure is real (from 20:00Z the span crosses midnight), and
  `test_the_retry_budget_belongs_to_the_forecast_day_not_the_wall_date` exercises
  the production rule across midnight.
- **Residual.** If the retry config grows the span past ~23 h, the first test
  fails loudly rather than silently. Acceptable.

### F4 (none) — the telemetry quieting is correctly scoped

- **Evidence.** `scripts/llm_cost_audit.py:56-74` replace a module-level
  `setLevel(ERROR)` with `_quiet_telemetry()`, used only around the re-price call
  (`:120`). The unpriced COUNT still reaches the report (`n_unpriced`,
  `unpriced_models`), so suppressing per-row warnings loses nothing.
  `backend/tests/test_llm_cost_audit_ledgers.py:62-71` assert importing no longer
  silences the logger and the level is restored. The audit now reads the writer's
  month files (`:22-32`) and prints DISAGREE beyond a stated tolerance
  (`scripts/llm_cost_audit.py:185-194`: $0.05 or 5%). The instrument got stronger.
- **Residual.** A process-global logger level toggled in a context manager is
  not thread-safe; harmless for a CLI.

### F5 (none) — `store_social(root=)` honours its root

- **Evidence.** `backend/services/web_reader.py:2066-2084` (c0ac5310):
  `base = (root or social_root()) / host`; both tests that call it pass
  `root=tmp_path` (`backend/tests/test_reader_pool.py:386,391`,
  `backend/tests/test_lane_o_muratclaw.py:856,860`). The lesson of the 09-28
  incident (`backend/data/optimus/incidents/test_wrote_to_real_corpus_2026-09-28.json`)
  applied to the new writer. Nothing weakened.
- **Residual.** No test asserts that a call WITHOUT `root=` under pytest refuses
  or is redirected; the 09-28 incident was a writer whose `root=` was honoured
  for one file and not another. See the experiment below.

### Also checked, no finding

- `STOPPED_BY_OPERATOR` (`backend/services/system_health.py`, c0ac5310 diff):
  needs the lab's own stop record for the same pid; a crash with a STOP file on
  disk stays DEAD (`test_a_crashed_lab_is_still_dead_even_with_a_stop_file_on_disk`).
  One gap: the verdict has no age bound, so a lab stopped weeks ago never turns
  red. Owner decides whether a stop older than N days becomes STALE.
- The commit ran the full suite with 1 failure, fixed it and verified only a
  targeted set of 72; CI then ran the full suite green. Acceptable because CI
  was watched (this review re-checked it).

## WHAT WORKS

- Every fix pins an input (fixture, clock hour) or scopes a side effect (logger
  level, write root) instead of widening a tolerance.
- Two fixes add the production-side test the bug implied, not only the test-side
  patch.
- CI green on the commit.

## WHAT DOES NOT

- The gateway repair's docstring states a rule the code no longer follows, and
  the rule it dropped came from a measurement.
- The reclaim path can close tabs it did not open; "only when no reader runs"
  lives in a docstring, not in code.
- The corpus-write family is fixed writer by writer, not suite-wide.

## HIGHEST-EV EXPERIMENT

One suite-wide guard, $0: a `conftest.py` session fixture that snapshots file
names and sizes under the real `OPTIMUS_LEDGER_DIR/news_corpus` (and the other
append-only ledgers) before the run and fails the session if any changed. It
turns the 09-28 incident family from "fixed writer by writer" into "cannot recur
unnoticed", and one suite run proves it.
