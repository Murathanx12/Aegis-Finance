# Opus research session — kickoff prompt (2026-08-01)

Copy everything below the line into a fresh `/model opus` session started in
`C:\Users\mrthn\aegis-finance`.

---

You are running a pre-planned research execution session for the Aegis
program. The thinking and registration were done in advance; your job is
**disciplined execution of frozen protocols**, not ideation. Read these first,
in order:

1. `docs/research/AI_PANEL_2026-08-01_ROUND16.md` — current adjudication + roadmap v2
2. `C:\Users\mrthn\Aegis module\TRIALS\TRIAL-ABIO-KIRK.md` — the frozen trial you will run
3. `NEGATIVE_RESULTS.md` §20-§25 — the receipts that constrain today's work
4. `C:\Users\mrthn\Aegis module\data\DATA_DICTIONARY.md` — what is on disk

House rules that bind you absolutely:

- **The explore/confirm wall:** explore 2004-01..2018-12; confirm 2019-01..2024-12
  is read at most ONCE per graduating arm. Never peek.
- **One shot per registered run.** A crash before results are readable is
  repairable (fix, disclose the repair in the trial doc, re-run). A completed
  run is final. No reruns, no parameter tweaks after numbers exist.
- **Nothing new gets evaluated on data without pre-registration first**
  (trial doc + registry row committed BEFORE run code). TRIAL-ABIO-KIRK is
  already frozen at module commit `66add9e` — for it, go straight to build.
- **Registry lines are ASCII** (`json.dumps(..., ensure_ascii=True)`).
- **Never touch:** lane YAMLs, paper_nav, the scheduler, backend config
  hashes, anything under the product deploy path. This session is module-side
  research only.
- **Write results into the trial doc + NEGATIVE_RESULTS.md** in the house
  style: frozen verdict first, both-hands interpretation after, numbers in
  tables, repairs disclosed.
- Use `.venv\Scripts\python` in `C:\Users\mrthn\Aegis module` for all runs.

## Task 1 — run TRIAL-ABIO-KIRK (registered, candidates 164-166)

Build `scripts/run_trial_abio_kirk.py` implementing the frozen spec EXACTLY as
written in the trial doc (io construction, ncusip date-valid link, ambiguous
links dropped, 1/99 per-quarter winsorisation, fdate+60cd lag, three arms,
five-characteristic residualisation for io_abn, factory `scan_signal`,
explore-only, deciding arms largemid@flat25 + small@KO-half, zero-cost bound
reported). Where the doc is silent, follow the most recent precedent
(`scripts/run_instr_small_shelf.py`, `scripts/run_instr_resid_mom.py`) and
disclose the choice as mechanical plumbing in the results write-up.

Write spec tests BEFORE the run (precedent: `tests/test_resid_mom.py` caught
an off-by-one that would have voided the trial). Minimum: the lag rule
excludes a fdate 59 days before month-end; winsorisation is per-quarter; the
residual arm's regression is per-quarter cross-sectional; ambiguous cusip
links are dropped not resolved.

Then one shot. Record: per-arm/per-segment IC t, gross t, net t (all arms),
turnover, the pre-declared decisive comparison t_ic(io_abn) vs t_ic(io_level),
and the frozen verdict. Append results to the trial doc + a new
NEGATIVE_RESULTS section (or a graduation note if any arm clears — then STOP
before confirm and flag for Murat; confirm on a graduate is his call to
authorize since it burns the one read).

## Task 2 — build the daily event harness (no registration needed for the harness itself)

The admissible successor for PEAD (§14), 8-K (§20), FDA (§16) and the queued
13D/13G family. Build `aegis_brain/factory/daily_events.py` against
`data/wrds_raw/dsf_full/` (24.0M rows, 2002-2024):

- Event study core: given (permno, event_date) pairs, compute CAR windows
  (+1..+5, +1..+20, +1..+60) vs a **matched control arm** — same-segment,
  same-month, nearest dollar-volume-rank non-event names (the §20 lesson:
  distress-8-K "drift" was selection, not information; the control arm IS the
  test).
- Delisting-aware (dsf `ret` already includes delisting returns where CRSP
  provides them — verify and document).
- t-stats clustered by event-month (events cluster in time; naive iid t is
  inflated — say so in the module docstring).
- Spec tests: a synthetic panel where the true CAR is known; control-matching
  returns names with no event within ±60 days.

Do NOT register or run any event family in this session unless Task 1 + tests
are done and clean. If time remains, draft (but do not commit as frozen) a
13D/13G registration for review: hypothesis, arms, kill condition — Murat and
the next session freeze it.

## Task 3 — only if `data/wrds_raw/manifest_optionm.json` exists (P0b landed)

Verify the pull (rows > 0 per year, secid link coverage vs CRSP universe,
spot-check one known name's ATM IV against public history), then draft — again
NOT frozen — the option-implied cohort registration per roadmap §3 P3: six
arms (ATM IV level, RIV-spread, 25Δ put-call skew, 91-30 term slope, O/S,
put-call volume ratio), each a counted candidate, §23 receipt declared as
prior against the residual-skew variant, R15-2/R15-3 ledger predictions
attached as the scoreable external forecasts. If the manifest does not exist,
skip — do not attempt WRDS yourself (Duo is attended).

## Definition of done

A results write-up in the trial doc + NEG_RESULTS, module tests green
(`.venv\Scripts\python -m pytest tests/ -q`), module committed and pushed,
and a session summary that states: verdicts as frozen, repairs disclosed,
candidate count (166 + anything you drafted-but-did-not-register stays 166),
and what is queued for the next attended step.
