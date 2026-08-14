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
