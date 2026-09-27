# The plan reads what the night learned (preferences only) — 2026-09-27

**RESULT IMPROVEMENT: NONE yet (plumbing).** No new measurement, no LLM spend, no
order type, no limit moved. What changed is that the overnight learning now has
a reader on the paper-decision path, and a health row that goes red when it
does not.

## The finding (review 2026-09-26 item 7; roadmap Lane R)

`policy_state.json` was refreshed every night (reputation weights per arm,
persona weights at 0, the PROBE gate, direction-vs-magnitude skill) and nothing
that makes a paper decision read it. The only reader was
`scripts/live_market_loop.py`, which has never run end to end. The learning was
write-only.

## What `sim_run.u_plan` reads now, and when it ignores it

`policy_state.plan_view(asof)` decides first:

| state | plan does |
|---|---|
| reputation block dated ≤ `PLAN_MAX_AGE_SESSIONS` (2) XNYS sessions before `asof`, ≥ 1 arm with weight > 0 | **uses it**: receipt `policy_state_used` {generated_at, age_sessions, reputation_date, reputation_arms_with_weight, probe_weighting, order_source} |
| older than 2 sessions / undateable / missing / unparseable / no arm > 0 | **ignores it**: shortlist order, equal weights, receipt `policy_state_ignored` {reason, order_source}. Stale is UNKNOWN, never fresh (the `funnel_staleness` pattern) |
| sandbox caller (injected ledger) that names no `policy_state_path` | ignores it: a test never reads this machine's state |

When it is used:

1. **Order of PROBE candidates.** The shortlist is re-ordered by
   `policy_state.reputation_er`: Σ w_c·x_c over the E[r_5] components
   (`expected_return` view, h = 5, the horizon PROBE is graded on) whose
   weight is > 0. A forecast-arm component (`investigator_dir`,
   `thesis_card`) also needs its family to carry weight > 0 in the night's
   `reputation_weights`, so a family at 0 has no vote. Names with no
   contributing component keep their shortlist order *after* priced names (no
   E[r] is not E[r] = 0). Ties go to the larger **σ63·√h vol-prior magnitude**
   (the $0 formula that beat the LLM's own magnitude read); the LLM magnitude
   read is never used. Order changes WHICH ten of the shortlist enter; it
   cannot change how many or how big.
2. **PROBE weighting preference** (`equal` / `inverse_vol` / `bigmove_tilt`),
   from `policy_state.probe_weighting`.

## Why the caps cannot move

* `PROBE_MAX_WEIGHT` (2%) and `PROBE_GROSS_CAP` (20%) are read from `config`
  inside `u_plan` and passed as arguments to `policy_state.probe_weights`. The
  state has no key that reaches them; `SCHEMA` does not declare them and
  `_check` refuses any undeclared key on write.
* `probe_weights` spreads the SAME total as equal weights in proportion to the
  scheme, then **clips each name at the cap without redistributing** — a shape
  can only shrink the gross, never raise it. With ten names at 2% already, any
  non-equal scheme lowers gross below 20%. A post-hoc check falls back to equal
  on any breach.
* `probe_weighting` is an enum key (`ENUM_KEYS`); any other value is refused on
  write and read back as `equal`.
* Tests: 200 random (n, caps, sigmas) per scheme never exceed either cap; an
  end-to-end `u_plan` with `bigmove_tilt` plus smuggled `PROBE_MAX_WEIGHT: 0.5`,
  `PROBE_GROSS_CAP: 1.0`, `MAX_NAME_FRAC: 1.0` in the state sends every order
  ≤ 2% of equity and ≤ 20% gross.

## The weighting preference: `equal` until the twins say otherwise

`policy_state.refresh` now writes `probe_weighting` + an evidence block from the
newest `llm_portfolio/leaderboard_*.json`:

* all three twins (`probe_equal/inverse_vol/bigmove_tilt_2026-09-26`) must be
  `status: OK` with ≥ `PROBE_TWIN_MIN_SESSIONS` = **21** graded sessions, and
* the leader must beat EACH other twin by ≥ `PROBE_TWIN_MARGIN` = **0.01**
  net-to-date (declared today, before any twin had a session).

Otherwise `equal`, with `reason: twins immature (n sessions ...)`. On
2026-09-27 the value is `equal`: the twins enter 2026-09-28 and have 0 sessions.
That is the honest value for about a month. A flip is one journal line with the
leaderboard as evidence.

## Health

New probe `policy_state` in `system_health.PROBES`: ALIVE only when a `u_plan`
receipt (`pc_book/<day>/decisions.jsonl`) whose `asof` is within 2 sessions
carries `policy_state_used`. STALE (prefixed `WRITE-ONLY`) when the state exists
but the newest plan ignored it (the reason printed), predates the reader, was
refused before reaching it, or no plan ran. UNKNOWN only with no evidence at all.
Before the reader ran it read **STALE: the plan predates the reader**. After
the 10-hour `paper_profit` sim `94f7b8ff15e5` (started 2026-09-27T13:54Z from
this working tree) ran its first `u_plan`, the probe on the live machine reads
**ALIVE**: `plan asof 2026-09-27 read it: age 0 session(s), order: shortlist
order (no shortlist name carries a contributing component), weighting equal`.
Both directions are pinned in tests (UNKNOWN with no evidence -> STALE
`WRITE-ONLY` when written and unread -> STALE with the plan's ignore reason ->
ALIVE when a recent plan used it; STALE again when the only reading plan is
older than 2 sessions).

## A defect fixed on the way

`sim_run._daily_module_unit` calls `policy_state.refresh(None)` right after the
`distil` subprocess has refreshed it with the real receipt. That second call
overwrote `sources.reputation_date` with `None`, which would have made the
weights undateable, so the new reader would ignore them every night. `refresh`
now **carries the previous receipt's path and date** when it finds no new
receipt (`reputation_carried_from_previous: true`): weights are dated by the
receipt they came from. The `refresh(None)` call itself sits outside `u_plan`
and was left alone.

## Not done

* `bigmove_tilt` in `u_plan` tilts by σ63 (the vol prior). The twin book tilts
  by the investigator's P(|r5| > thr) when that covers every name, else σ63. The
  preference the twins earn can therefore be applied as a slightly different
  shape than the book that earned it. Wire the magnitude rows into the plan or
  freeze the twin's σ-only variant before the preference can first flip (~21
  sessions).
* The twin comparison is raw net-to-date. `bridge_report` says to read the
  differences regressed on USMV before calling any of them skill; that
  regression is not in the flip rule.
* `live_market_loop` still reads `policy_state` separately and was not touched.

## Verified 2026-09-27 (continuation builder)

**The live plan step did not break.** Sim `94f7b8ff15e5` cycle 1, unit `plan`:
`ok: True`, verdict `MEASURED_NEGATIVE`, `policy_state_used: True`,
`probe_weighting: equal`, `probe_gross: 0.2`, `n_probe: 10`, no exception. The
receipt (`pc_book/2026-09-27/decisions.jsonl`, t 13:54:30Z) carries
`policy_state_used` with `reputation_date 2026-09-27`, `age_sessions 0`, five
investigator arms with weight > 0, `probe_weighting_reason: twins immature (0
sessions; each needs 21; statuses ['MISSING'])`.

**But the ORDER is a no-op today, and that is the next thing to fix.**
`order_source: shortlist order (no shortlist name carries a contributing
component)`. In `expected_return/er_2026-09-27.json` every one of 46 names has
an EMPTY `h5` cell: the ranker is calibrated at 21 sessions only,
`investigator_dir` has "no investigator beats_benchmark row at h=5",
`thesis_card` has no h=5 row, catalyst has no PDUFA inside 5 sessions, and
revision_flow has no h=5 rule table. The reader is live and reads the right
weights; the E[r_5] view it multiplies them against is entirely asleep. Until
some component is awake at h=5, the learned reputation weights cannot move a
single name. (Reading h=21 instead would change the order today, but PROBE is
graded at 5 sessions; that is a decision, not a fix, and was not made here.)

**Invariants now pinned** (`backend/tests/test_policy_state_is_read.py`, 41 tests):

* reputation weights of 5.0, a negative, NaN or inf are refused by the schema,
  the plan says `policy_state_ignored: unparseable: REFUSED ...`, and the book
  is the pre-change book exactly (SL00..SL09, every weight = `PROBE_MAX_WEIGHT`,
  gross = `PROBE_GROSS_CAP`), even with `PROBE_GROSS_CAP: 1.0` /
  `PROBE_MAX_WEIGHT: 0.5` smuggled into `values`;
* missing, zero-byte and unparseable state -> the old book and a named reason;
* a `probe_weighting` value of 5.0 / "leverage_2x" / None / -1 -> `equal`;
* a NaN / inf / negative / missing sigma -> `equal` weights;
* an undateable stamp (None, "", "not-a-date", "2026-13-45", the bare integer
  20260927) is UNKNOWN -> stale. **Fixed on the way:** the integer 20260927
  used to parse as a date (`date.fromisoformat` accepts the basic format), so
  a non-string stamp read as fresh. `_sessions_between` now dates only an ISO
  `YYYY-MM-DD` string, and treats a stamp more than one calendar day after the
  plan date as undateable (one day of slack for the UTC+8 machine vs the ET
  plan date);
* a sandbox caller that names no path never CALLS `plan_view` (spy), even with
  a fresh valid state at `STATE_PATH`.

## Worst case in dollars (session protocol item 4)

From the live receipt's `worst_case_line`, equity $999,054, largest admissible
PROBE book = `PROBE_MAX_NAMES` 10 x min(`PROBE_MAX_WEIGHT` 2%, `PROBE_GROSS_CAP`
20% / 10) x 3 sigma of the shortlist's largest daily sigma (2.74%/day = 8.23%):

| | n x notional% x stop% | 3-sigma session | sum\|notional\|/equity | no-stop ceiling |
|---|---|---|---|---|
| before (equal only) | 10 x 2.00% x 8.23% | -$16,436 | 0.20 | -$199,811 |
| after (any shape) | 10 x <= 2.00% x <= 8.23% | <= -$16,436 | <= 0.20 | <= -$199,811 |

The change cannot raise it: every w_i <= 2% (clip, no redistribution), sum w_i
<= 20%, and the receipt's bound already uses the max sigma over the WHOLE
shortlist, so re-ordering which ten enter cannot pick a name outside it. Pinned
by `test_the_admissible_worst_case_bounds_every_shape` (300 random books x 3
shapes: sum w_i sigma_i <= n_max w_max max sigma). Honest caveat: under
`bigmove_tilt` the REALISED 3-sigma loss of a given book moves toward that
bound (more weight on high-sigma names) while its gross falls; under
`inverse_vol` it moves away. Neither can cross it. Today the shape is `equal`,
so the planned book equals the admissible one.

No new exception class was added in `backend/services/` (`PolicyRefused`
already existed), so `test_guard_missing_input_contract.CASES` was not touched.
