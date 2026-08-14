# DISCHARGE — Opus 5 build session, 2026-08-14

**For Fable, refereeable in one read.** Written against the review contract in
`HANDOFF_OPUS5_2026-08-14.md` §6.

---

## The one-line answer

The first Track B descendant is built, run and **closed** — and it closes more
than itself: **whatever headroom exists for any correlation predictor to improve
a minimum-variance risk model on this panel is bounded at ~15% of the gain the
trailing matrix already delivers**, because perfect foresight of the realised
forward correlation matrix is statistically indistinguishable from that trailing
matrix (and marginally worse on the point estimate). Cost: **$0.00 of vendor
spend**.

---

## 1. What was built

| thing | where |
|---|---|
| `PREREG_GRAPH_COVARIANCE_1.md` — pre-registration with a power gate declared to run first | `Aegis module/TRIALS/` |
| `gc1_config.py` — every free parameter enumerated and frozen before compute, with one dated amendment | `Aegis module/scripts/` |
| `gc1_cov.py` — pure, offline-testable covariance and portfolio primitives (PSD repair, GMV, capped-simplex projection, FISTA long-only solve, Ledoit-Wolf, Marchenko-Pastur) | `Aegis module/scripts/` |
| `gc1_grade.py` — resumable per-arm grading; the gate runs and is written to disk **before** any real arm is graded | `Aegis module/scripts/` |
| `gc1_tables.py` — every reported number printed from JSON, never retyped | `Aegis module/scripts/` |
| `test_gc1_cov.py` — 19 tests: contract, known-answer, leakage, and one regression pin | `Aegis module/tests/` |
| `register_graph_covariance_1.py` — registration before compute, verdict row refused without a receipt | `Aegis module/scripts/` |
| `GRAPH_COVARIANCE_1.md` — the verdict document | `aegis-finance/docs/` |

**Tests.** 19/19 in the new file; **the full `Aegis module` suite is green
(651 tests, exit 0)**. The new code lives in `Aegis module`, not `backend/`, and
`backend/` was not modified — so `backend/tests` was not re-run, which is stated
rather than implied. `pytest_timeout` imports cleanly, so CLAUDE.md's
un-hangable claim holds.

Tests shipped as required: **shape/contract** (a capped-simplex projection that
cannot reach a unit sum raises rather than returning something that silently
corrupts every downstream variance); **known-answer** (a correlation is planted
and the true matrix must beat a wrong one in ≥36 of 40 forward windows, and a
*sparse* correction must still win in ≥34 of 40); **leakage** (the same
correction attached to the wrong pairs must not win — the unit-scale version of
the trial's own placebos).

---

## 2. What was registered, with its bars

**`GRAPH-COVARIANCE-1`**, registered `2026-08-14T04:27:33Z`, commit `6dcffa8`,
**before any covariance matrix was built**. Corpse check **PASS vs 335 prior
experiments** (nearest: its own parent at 0.334). Accrues zero arms.

- **H1** — a residual-correlation block predicted *with* semantic edge features
  produces a lower-realised-variance minimum-variance portfolio than the
  identical block without them. Prior stated in advance: ~40/60 against.
- **H2** — the same survives a long-only, 10%-capped, total-return portfolio.
  Prior: ~15/85 against.
- **Bar:** paired per-cut-date difference in realised annualised volatility,
  differenced within the date (§18), n = graded cut dates, Newey-West at 2 lags,
  SE = max(HAC, IID), **MDE = 2.80 × SE** (§19). Adoption required the gate, the
  MDE, *all three* placebos null, **and** H2.

---

## 3. What resolved — each number beside its own MDE

| claim | number | MDE | t | verdict |
|---|---:|---:|---:|---|
| **H1** `model_semantic − model_numeric` (resid-GMV vol) | **−0.000369** | 0.000384 | −2.69 | **NOT DETECTABLE** (96% of its MDE, wrong direction) |
| **H2** same, long-only capped total-return | −0.000176 | 0.000324 | −1.52 | **NOT DETECTABLE** |
| placebo — node-label shuffle | −0.06% | — | −1.92 | **null** |
| placebo — random matched density | −0.02% | — | −0.68 | **null** |
| placebo — stratified (date × sector × ρ decile) | +0.03% | — | +0.28 | **null** |
| gate — `oracle_on_edges` | −16.85% | 0.000875 | −5.11 | **detectably WORSE** ⇒ gate FAILED |
| instrument — `oracle_feature` (perfect edge feature *inside the real ridge*) | −7.57% | 0.000584 | −3.44 | **detectably WORSE** ⇒ architecture ceiling is negative |
| instrument — `oracle_full` (truth everywhere) | +43.28% | 0.002203 | +5.22 | **DETECTABLE** ⇒ the metric is not blind |
| context — `sample` (trailing residual correlation) | +44.95% | 0.001278 | +9.34 | **DETECTABLE** |
| context — `diagonal` (the industry assumption) | −86.58% | 0.002483 | −9.26 | **detectably WORSE** |
| **headroom: `oracle_full` over `sample`** | **−0.000158** | **0.001916** | **0.23** | **NOT DETECTABLE**, point estimate negative |

---

## 4. What died, and why the death is trustworthy

**H1 and H2 are `NOT_DETECTABLE`** — under §19 neither a kill nor a win. But the
family around them *is* closed, and by a different number than the one the trial
was built to produce.

The death is trustworthy for four reasons that are checkable rather than
asserted:

1. **The metric has a working positive control.** `diagonal` — the assumption
   every commercial risk model actually ships — is 86.6% worse than `sample` at
   t = 12.60. A metric that ranks the known-wrong model as known-wrong, by an
   enormous margin, is not asleep.
2. **All three placebos are clean**, sitting within 0.06% of the reference
   against a real-arm effect of −3.89%. The nuisance channel the
   pre-registration named in advance did not fire.
3. **The instrument was itself validated before it was trusted.** `oracle_full`
   clears its MDE at t = +5.22, so the metric demonstrably rewards a better
   matrix. The null is a null about information, not about sensitivity.
4. **The verdict is stable under the one numerical judgement it contains.** The
   eigenvalue floor was declared a free choice in advance and the primary is
   reported at {0.05, 0.10, 0.20} with the rule that the sensitivity can only
   demote. See `runs/GRAPH-COVARIANCE-1/floor_sensitivity.json` and Table 4.

**And one defect, disclosed with its numbers rather than deleted.** The first
gate run was VOID: an absolute eigenvalue floor of `1e-8` did not repair the
indefinite predicted matrices, it manufactured near-zero-variance directions that
a minimum-variance solve levered into. The matrices forecast **0.13% annualised
volatility for portfolios realising 2.7%** — a calibration ratio of **4,519** —
while every PSD check passed. Void artifacts are committed at
`runs/GRAPH-COVARIANCE-1/void_run_eigfloor_1e-8/`. The fix is a *relative*
eigenvalue floor plus entry clipping, chosen from the spectrum of the predicted
matrices (which contains no outcome). Two things now exist that did not: a
runtime `VOID` assertion on the calibration ratio, so this cannot again depend on
a human reading a diagnostic; and a regression test pinning the failure mode
under the old floor and its absence under the new one.

---

## 5. Two reusable instrument rules earned here

Candidates for CANON, if the brain agrees they generalise:

- **A model improvement measured under one loss function may not be assumed
  under another.** MARKET-GRAPH-1's ridge beats the trailing correlation matrix
  on out-of-sample entrywise MSE (R² 0.126 → 0.127); the same ridge family
  realises **45% more portfolio risk** than that same trailing matrix. Both
  numbers are right. Any future arm claiming a better covariance, correlation or
  risk estimate must print the loss function it will be used under.
- **An oracle must be constructed inside the architecture it is the ceiling
  for.** `oracle_on_edges` wrote full-dispersion truth (σ = 0.180) into 0.58% of
  a matrix whose remaining 99.42% carried quarter-dispersion predictions
  (σ = 0.063) — a matrix no predictor could emit. It came in detectably *worse*
  with perfect information. `oracle_feature`, the same information fed through
  the same ridge, is the ceiling the pre-registration meant.

---

## 6. What it cost

**$0.00.** No LLM call was made. The MARKET-GRAPH-1 edge corpus was already
paid for ($2.66) and every arm here is a refit and a matrix solve. DeepSeek
balance is unchanged at **$37.12**.

Per invariant 9, `$0 spent on an LLM night is a defect` — and this session was
not an LLM night. It was the compute-only Track B experiment the roadmap places
first, and it needed no vendor call by design. **This is flagged rather than
glossed:** if the brain wants LLM spend exercised, the next session should be
Track C (`INTERNET-INVESTIGATOR-FWD-1`), which is where the dollars belong.

---

## 7. Where I exercised freedom against the roadmap's default order

Three deviations, all with receipts:

1. **I added two arms the pre-registration does not contain** — `oracle_full` and
   `oracle_feature`. Both are declared instrument diagnostics, both read the
   outcome and are therefore **never adoptable**, and both were added *after* the
   pre-registered gate failed, in order to distinguish "the metric cannot reward
   a better matrix" from "coverage is the constraint" from "the oracle was built
   wrong". Without them the honest report would have been the pre-registered
   `UNDERPOWERED_BY_CONSTRUCTION` and the pre-committed escalation (raise
   `UNIVERSE_N`) — which would have spent real compute chasing a gap that these
   two arms show is not there.
2. **I amended the PSD repair mid-trial** rather than reporting the first run.
   The justification is a matrix diagnostic, not an arm comparison, and the void
   run is committed so the amendment can be audited.
3. **I did not run the pre-committed escalation.** The prereg says a failed gate
   escalates to more edges under a new name. `oracle_full − sample` says the gap
   that escalation would compete for does not exist, so escalating would burn
   compute on a measured emptiness. I recommend the escalation be **cancelled**,
   not deferred.

---

## 8. The one decision I want the brain to make next

**Track B's covariance branch is closed; where does the next session go?**

My recommendation, in priority order, and the reasoning:

1. **Track C — `INTERNET-INVESTIGATOR-FWD-1`.** It is forward-only, so it starts
   accruing against the ledger immediately (first resolutions **2026-08-16**);
   it is the one open question the campaign has never actually tested; and it is
   where the LLM budget belongs. Everything historical is now heavily fenced,
   while forward evidence is the only thing that can certify anything (A7).
2. **`REACTION-GAP-1`**, as the surviving Track B descendant most likely to
   carry information — it lives on residual *returns* and *events*, not on the
   covariance matrix, so nothing measured today constrains it.
3. **Not `MARKET-WORLD-MODEL-1` yet.** Today's result is a direct warning to the
   NN plan: the roadmap makes "future correlation/co-movement" the *first* dense
   reality target because it is the one with a proven semantic signal. That
   signal is real at the pair level and has now been measured **not to transfer**
   to a portfolio-level risk objective. If the world model trains a correlation
   head, it should be graded on the loss function the output will be used under,
   or it will reproduce exactly the 45% gap found here.

Everything else in the handoff's P2–P4 is untouched and unblocked.

---

## FABLE REVIEW — rulings (2026-08-14, appended after verification)

Verified before ruling: registration commit precedes compute (`6dcffa8` →
`84b5df2` → `0c644c1`), both registry rows present, void-run artifacts on disk
at `runs/GRAPH-COVARIANCE-1/void_run_eigfloor_1e-8/`, `test_gc1_cov.py`
**19/19 green re-run by the reviewer**, and every number in this discharge
matches `GRAPH_COVARIANCE_1.md`.

**Deviation 1 — the two unregistered instrument arms: APPROVED.** They are
declared never-adoptable, they read the outcome only to arbitrate a broken
gate, and the pre-registered gate result is reported unamended beside them.
Without them the trial would have escalated into a measured emptiness — the
arms are what §22 now says they are: legitimate instrument forensics. The
generalised licence is written into CANON §22's corollary so the next session
doesn't have to re-argue it.

**Deviation 2 — the mid-trial PSD repair amendment: APPROVED.** The void run
is committed as evidence, the replacement floor was chosen from the spectrum
(which contains no outcome and no arm comparison), the runtime VOID assertion
and the regression pin exist, and the verdict is reported at three floors under
a demote-only rule. This is the same decision class as MARKET-GRAPH-1's
universe amendment and it is handled to the same standard.

**Deviation 3 — the escalation: CANCELLED, with its boundary stated.** The
pre-committed escalation (more edges into the same min-variance solve) is
cancelled, not deferred — `oracle_full − sample` at |t| = 0.23 across all
three floors is a measurement that the gap it would compete for does not
exist. Per standing canon the closure is **pool- and objective-specific**:
minimum-variance realised volatility, N ≈ 300 US large-cap, 126-day horizon,
2015–2024. Reopening requires a new pre-registration that names which of those
four boundaries has changed and why headroom should exist there (§4 of the
verdict lists the unmeasured objectives honestly). Recorded in CANON's closed
rabbit holes.

**The two offered rules: ADOPTED as CANON §21 and §22**, with the GC1 receipts
attached.

**Next session: Track C, `INTERNET-INVESTIGATOR-FWD-1` — approved as
recommended**, with four binding constraints from the roadmap: the
belief-change contract (`prior / posterior / belief_change`; zero is a valid
answer), served-model logging on every call, microtask contracts rather than
one mega-schema, and a **$10–15 dollar ceiling** logged from served responses.
Forward-only, graded on the fast-horizon ledger, accruing from 2026-08-16.
`REACTION-GAP-1` is the approved fallback if the investigator design stalls on
tooling.

**The Track D warning: ACCEPTED and made binding.** `MARKET-WORLD-MODEL-1`'s
correlation head must be graded under the loss function its output will be
used under (§21); entrywise error alone grades nothing. The roadmap is amended
accordingly.

— Fable

---

## FABLE REVIEW 2 — Track C checkpoint rulings (2026-08-14)

Verified before ruling: `d8d1514` corrects the roadmap's GC1 sign (the
reviewer's own error — the verdict doc was right, the roadmap edit was wrong);
`cd058fd` registers `INTERNET-INVESTIGATOR-FWD-1` before accrual with
`iif1_power.py` and `iif1_sigma.py` committed alongside;
`MIN_GRADED_NIGHTS_BEFORE_READ = 40` is frozen in `iif1_config.py:96` and the
verdict writer refuses below it; the prereg pre-declares the direction
observables underpowered-by-construction while still recording them; commit
`02245f8` gives every arm the same 40 names per night.

**Deviation — primary observable moved from direction to magnitude:
APPROVED.** This is the strongest kind of deviation: a measurement made before
money, committed with the prereg, that overturns a default the roadmap wrote
from intuition. σ_π ≈ 0.004–0.006 on direction means a direction primary never
resolves at any trigger count — running it anyway would have violated the
spirit of §19 (a trial designed to be unable to say anything). Note for the
record: this is the **third independent instrument** to push the programme
from direction to magnitude/risk — the exposure-vs-selection oracle gap, the
GC1 diagonal result, and now the σ_π decomposition. That convergence is itself
a finding about where information lives.

Two conditions attach:
1. **The verdict's language is bound now:** a positive H1 is the claim
   "autonomous investigation improves *magnitude/volatility* forecast
   calibration" — never "the LLM picks stocks", never promoted past
   research-result status. The direction observables stay recorded and stay
   unreadable as either kill or win.
2. **Freeze a read schedule, not just a read floor.** 40 graded nights is when
   the primary may first be read; without a declared schedule, repeated looks
   after that become optional stopping. Declare the checkpoints now (e.g.
   reads at 40 / 80 / 120 graded nights, decision only where the §19 MDE is
   met) and put them in the config next to the floor, before the first night
   runs.

**MIN_GRADED_NIGHTS_BEFORE_READ = 40: APPROVED.** Eight blind weeks is
consistent with a programme that refuses skill claims before 24 months. The
floor is a *read* gate, not a power target — the §19 MDE still governs any
decision, and a read at 40 that doesn't clear power is an interim report, not
a verdict.

**The first dollar: GREEN-LIT.** Build the nightly runner and run the pilot
under the standing constraints ($10–15/night ceiling, spend logged from served
responses, served-model recorded per call). After the first pilot night,
report measured cost-per-night so the 40-night bill can be projected against
the $37.12 balance before the trial is committed to its own accrual clock.

**The stale CLAUDE.md figures: fixed by the reviewer** (fast suite now
documented at ~3,650 tests / 4m23s measured 2026-08-14), since the measurement
existed and the claim was off by 4× on runtime.

— Fable

---

## FABLE REVIEW 3 — pre-Night-1 lockdown + TEACHER-LIBRARY-1 adoption (2026-08-14, Murat's rulings incorporated)

**Correction accepted:** `origin/main` resolves past `d0e14f8` — the runner
(`34922f2`) and a tools fix (`ff3950e`) are pushed. Verified now:
`READ_CHECKPOINTS` exists **nowhere** in either repo, so Night 1 remains
blocked on exactly the steps below.

### IIF-1 status line (Murat's wording, adopted verbatim)

> **IIF-1: CONDITIONALLY GREEN-LIT — scientific design frozen;
> magnitude/volatility primary approved; Night 1 blocked only on executable
> 40/80/120 read-schedule enforcement and runner completion. No further
> architecture changes before pilot.**

### Binding pre-Night-1 orders (narrow; nothing else may change)

1. **`READ_CHECKPOINTS_GRADED_NIGHTS = (40, 80, 120)`** frozen beside the
   floor, **enforced in executable code** — a read at 39, 41, 57, 79, 81, 119
   or 121 is refused as firmly as at 39. Config text alone does not remove
   optional stopping.
2. **Terminal rule frozen now:** at 40/80 without the MDE →
   `INTERIM_UNDERPOWERED`, carrying **no** H1 win/kill reading. **At 120
   without detectability the prereg terminates `NOT_DETECTABLE`;** accrual
   beyond 120 requires a new prospective amendment/pre-registration. Anything
   else just moves optional stopping from 40 to 120.
3. **Boundary tests pin it:** 39→REFUSE, 40→READ, 41→REFUSE, 79→REFUSE,
   80→READ, 81→REFUSE, 119→REFUSE, 120→READ, 121→REFUSE/NEW_PREREG_REQUIRED;
   plus: a checkpoint lacking the MDE can produce neither a positive nor a
   negative substantive verdict.
4. **The runner stays a boring orchestration layer:** frozen trigger set
   selected once; identical cells to every arm, equality asserted before calls
   AND before grading; requested/served model, tokens, cost, tool failures,
   malformed/drop counts, arm completion — all durable; **no trial-result
   statistics** during the blind besides operational diagnostics.
5. **Budget framing corrected and adopted:** $37.12 ÷ 40 = **$0.928/night**
   is the funding average; **$10–15 is a hard safety ceiling, not a planning
   budget.** Night-1 report must print `measured_cost_night_1`,
   `projected_40_night_cost`, `current_balance`, `funding_gap_or_surplus` —
   and the funding decision happens before the accrual schedule is committed
   to, not when the balance runs out.
6. **CI skip-integrity, before paid accrual:** the backend tests that skip
   their frozen-config consistency assertion when the `Aegis module` sibling
   tree is absent must not let a missing prereg/config read as green — a
   conspicuous integrity failure or a separate prerequisite check, either is
   acceptable; a silent `SKIP` is not.

### TEACHER-LIBRARY-1 / PUBLIC-ACTOR-TRAJECTORY-1: ADOPTED as the next major lane

Roadmap Track E written (`ROADMAP_BRAIN_V3_2026-08-14.md`), with the corrected
hypothesis (conditional structure, not celebrity skill — the STOCK Act
literature's mean-politician null is the stated prior). Brain-level
constraints the corpse check surfaced:

- **The predecessors are alive.** `TRIAL-CONGRESS-IC` (decision 2027-01-11),
  `TRIAL-INSIDER-IC`/`TRIAL-CMP-INSIDER-IC` (2027-07-21) and `TRIAL-ARK-IC`
  are accruing forward right now. TL-1 must extend them (historical bulk +
  behaviour taxonomy + `public_at` ledger), never re-register them, and never
  read them early.
- The **13F-popularity corpse** (small-cap t(IC)=2.70, net-dead book) is the
  mandatory control for H3.
- **H1 + H5 run first** — free SEC bulk data, and H5 (activity predicts
  magnitude/risk where direction is absent) points where three instruments
  now agree the information lives.
- The **Form 4 tri-state source contract** (`OK_EMPTY`/`OK_DATA`/`UNAVAILABLE`)
  is a prerequisite before the dataset scales — accepted exactly as argued;
  it is the IIF tool-layer lesson applied to a collector with a prod-403
  history.
- **Masking trio** on any historical-LLM arm; `public_at` only; teachers as
  features/weak labels with reality as the only supervised target; **no
  shadow lanes until feature-level results earn them**, and then only through
  `seed-a-lane` (attended).
- **Sequencing: after IIF-1 Night 1 runs cleanly.** The pilot does not share
  its builder with a new lane.

— Fable

---

## OPUS 5 — Review 3 orders discharged (2026-08-14, appended)

Status board with the receipts: **`IIF1_PRE_NIGHT_1_CHECKLIST.md`**.
All six built; **one attended decision remains** (§7 there).

| # | order | where | state |
|---|---|---|---|
| 1 | executable 40/80/120 enforcement | `Aegis module/scripts/iif1_read_gate.py` | **DONE** |
| 2 | terminal rule frozen | `iif1_read_gate.classify()` | **DONE** |
| 3 | the nine boundary tests | `Aegis module/tests/test_iif1_read_gate.py` (37 green) | **DONE** |
| 4 | boring runner, equality before calls | `backend/services/investigator_night.py` | **DONE** |
| 5 | budget framing on the receipt | `investigator_night.project_funding()` | **DONE** |
| 6 | CI skip-integrity | `backend/tests/iif1_prereg_check.py` | **DONE** |

**The correction the orders were aimed at, stated plainly.** Before this
session the trial's entire read discipline was one line —
`register_internet_investigator_fwd_1.py:145`, `if n < 40: raise`. It refuses a
read at 39 and permits one at 41, 57, 79, 119 and 600. `READ_SCHEDULE` existed
in the config as text and was enforced nowhere. The referee's phrasing was
exact: *config text alone does not remove optional stopping.*

**Two things found while building, neither of them in the orders:**

1. **A pre-call divergence crashed the runner.** The new equality check raised
   `ValueError` straight out of `run_night`, losing the receipt — an ops
   incident instead of a record. Caught by its own test, which asserts zero LLM
   calls were made; now it voids the night with the reason on disk.
2. **Only the trigger rule was checked against the frozen config.** `ARMS` —
   the thing the entire trial compares — plus the requested model, the
   benchmark and both ceilings were retyped into the runner and unguarded. Now
   checked, through the same loader that no longer skips.

**The one decision surfaced, and Murat's ruling.** The registered row froze a
read *floor* and the flat house `MDE_Z = 2.80`. `cc0bb4c` replaced that with
three looks carrying O'Brien-Fleming constants — a change to the **decision
rule**, made before any accrual, documented only in a config comment. Under
*pre-register or it didn't happen* that needs a registry row. It was raised
rather than taken unilaterally, because registering increments the cumulative
multiple-testing count and the registry has no delete API by design.

**Ruled: register.** `AMEND-INTERNET-INVESTIGATOR-FWD-1-READ-SCHEDULE` written
`2026-08-14T08:38:13Z` — looks `[40, 80, 120]`, constants
`[4.3117, 3.2955, 2.8452]`, `graded_nights_at_amendment: 0`,
`llm_spend_at_amendment_usd: 0.0`, terminal rule as its kill condition. The
bars that decide this trial now have tamper evidence rather than a comment.
**Night 1 is unblocked.**

Nothing else changed. No architecture, no observables, no arms, no budget
constants, no LLM call made — **$0.00 spent this session**; the DeepSeek balance
is still **$37.12** and Night 1 is still the first dollar.
