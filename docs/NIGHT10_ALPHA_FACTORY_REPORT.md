# NIGHT-10 — the Alpha Factory: what the search learned about itself

The night's search work produced **no new tradeable mechanism**. What it
produced instead is a measurement that changes how every previous null in this
programme should be read.

Receipts: `Aegis module/runs/HERESY/heresy_1.json`,
`runs/ARENA1/ANALYST_IDENT_1/{results,power_audit_factory}.json`,
`docs/BUILD1/llm_hypothesis_diversity.json`.

---

## 1. Phase 0 — ARENA-1 validated on disk, with one correction

The home handoff required ARENA-1 to be validated before anything was built on
it. It was, and it holds:

| check | result |
|---|---|
| freeze commit `d0ab548` predates scoring `580c9ed` | ✅ 01:04:58 < 01:26:02, and the freeze commit contains no results file |
| every scored genome_hash is in the frozen pool | ✅ 0 orphans, 384/384 |
| survivor count under the frozen rule reproduces | ✅ **66**, exactly as published |
| the best genome is EXCLUDED by the frozen turnover gate | ✅ G0245, +6.06%/yr, t 2.69, turnover 3.03 vs a gate of 3.00 |
| a control genome ranks 4th of 384 | ✅ G0004, equal-weight control, +4.87%/yr |
| void pass-1 preserved, not deleted | ✅ 384 rows, 100% negative — the tell that voided it |
| holdout unread | ✅ |

**The correction.** The published "+4.87%/yr false-discovery bar — best of 384
when nothing predicts anything" does **not** trace to the null-world receipt it
describes. `synthetic_results.json → null_calibration` says **+2.73%/yr**, and
that is a single seed; the power curve's three null seeds give **+2.73, +4.16,
+7.43 %/yr** (mean 4.77). The published +4.87 is numerically the **real-data
equal-weight control**, which is also the separately-published "4th of 384" — so
two of the four headline numbers are one measurement counted twice.

**ARENA-1's null survives the correction at every candidate bar.** At the lowest
defensible one (2.73%), 27 non-control genomes clear it, best t = 1.96, and
Bonferroni p_adj = **1.000**. The verdict was never bar-sensitive.

**What should be said instead:** best-of-384 under the null is **+2.7 to
+7.4 %/yr across three seeds**. There is no credible single-point bar at n=3,
and any future arena needs many more null seeds before quoting one.

---

## 2. The measurement that reframes the graveyard

Two independent audits, run for different reasons, found the same thing.

**ANALYST-IBES-1 (10 arms, re-measured through the parent's own Factory, 8 of
10 reproducing their published numbers to 0.00 points):**

* **0 of 10** arms report an effect above their own 80%-power MDE.
* 1 of 10 is significant at 5%.
* The small-segment "sign disagreement" that moved the verdict to UNRESOLVED —
  A2 at +6.05%/yr against A3 at −0.73%/yr — tested on the **paired** monthly
  series (correlation 0.578, so an independent-errors formula would have
  overstated the SE) gives mean difference +3.70%/yr, SE 3.60, **t = 1.03**.

**HERESY-1 (11 forbidden configurations, 6 distinct closed signals, control
reproduced its kill):**

* **11 of 11** show |effect| below their own 80%-power MDE.
* MDEs run **6.3% to 19.9 %/yr**. Effects run −6.2% to +5.1 %/yr.

| signal | segment | effect %/yr | SE | t | 80%-power MDE |
|---|---|---:|---:|---:|---:|
| analyst_target_upside_xs (control) | small | −1.02 | 7.10 | −0.14 | 19.9 |
| analyst_target_upside_xs (control) | largemid | −4.79 | 5.82 | −0.82 | 16.3 |
| momentum_12_1 | small | −3.96 | 4.39 | −0.90 | 12.3 |
| momentum_12_1 | largemid | +1.57 | 4.34 | +0.36 | 12.1 |
| value_btm | small | +3.91 | 4.55 | +0.86 | 12.7 |
| value_btm | largemid | +5.09 | 3.80 | +1.34 | 10.6 |
| accruals | small | −6.22 | 4.54 | −1.37 | 12.7 |
| accruals | largemid | −2.44 | 3.31 | −0.74 | 9.3 |
| reversal_dip | small | −2.57 | 7.03 | −0.36 | 19.7 |
| reversal_dip | largemid | −1.34 | 5.36 | −0.25 | 15.0 |
| drawdown_trigger_information | small | −1.25 | 2.26 | −0.56 | 6.3 |

**The standard adjudication shape used across this programme — EW top-50,
monthly, 2002–2022 — can only reliably detect double-digit annual alpha.**
Nothing anyone is realistically looking for is that large. A kill from such a
design is absence of evidence, and the graveyard has recorded it identically to
evidence of absence for 195 experiments.

### What this does NOT license

* **No corpse is reopened.** The consequence is a `kill_power: INADEQUATE`
  annotation and nothing else. Reopening one requires its own pre-registration,
  the corpse as a control arm, and an instrument whose MDE clears the effect
  sought.
* **No signal becomes tradeable, permitted, or shadow-seeded** in any branch.
  That was fixed in the pre-registration before the trial ran.
* The heresy run used one **standardised** design, not literally each corpse's
  original harness. The pre-registration said the latter; the gap is recorded
  in every row as `design_caveat`. The claim supported is about the shape most
  verdicts are issued in.
* Multi-instrument kills are not overturned by one underpowered arm.
  `analyst_target_upside_xs` was killed three independent ways and its
  PERVERSE/CLOSED grade is untouched.

---

## 3. The search was reopened, and closed again on its own terms

Murat reopened the search under an explore/freeze/validate partition. What
actually ran:

* **10 LLM-generated hypotheses** — all passed the corpse linter against 306
  priors, and all **collapsed to one connected component** against each other
  (37 of 45 pairs at or above the block threshold). Effective distinct ideas:
  **1**. Nothing was frozen, because there was nothing distinct to freeze. See
  `NIGHT10_LLM_RESEARCH_REPORT.md`.
* **ANALYST-IDENT-1** — stopped at its own POWER gate before any arm ran.
  Registered MDE target 4.0%/yr; realised 10.8%/yr against a disputed gap of
  6.8. No number quoted, small segment stays UNRESOLVED.
* **The holdout was not read.** It remains unread.

**Zero arms accrued to the search denominator tonight.** Both trials were
declared non-accruing in their pre-registrations before they ran, and both were
diagnostics of existing verdicts rather than searches for a winner.

---

## 4. Failure decomposition

| strategy / arm | label | why |
|---|---|---|
| analyst target LEVELS | WRONG_DIRECTION | negative on three independent instruments, gross — not a cost story |
| analyst target REVISIONS (breadth) | TOO_WEAK **and** underpowered | +6.05%/yr gross at t 2.23, dies at 10.2× turnover; below its own MDE of 7.6 |
| analyst target REVISIONS (Δ-consensus) | UNKNOWN | disagreed with breadth by t = 1.03 — which is to say it did not disagree |
| the churn hypothesis | POWER_FAILED | never tested; the gate stopped it |
| all 6 heresy signals | **UNKNOWN, previously recorded as NO_INFORMATION** | the correction this night makes |
| the 10 LLM hypotheses | OVERFIT (as a batch) | one idea in ten costumes; the batch, not any member, is the unit that failed |

The taxonomy's most important distinction — information present but delivery
failed, versus nothing there — is exactly what an underpowered kill cannot
resolve. That is why the audit matters more than any individual re-run would
have.

---

## 5. What Optimus wants to test next

1. **Raise the instrument's power before searching again.** Longer windows,
   more names per leg, or a panel estimator with a standard error smaller than
   the effects being sought. Searching harder with a 12%/yr MDE is spending
   compute to produce ambiguity.
2. **Re-run the ARENA null calibration with many seeds**, and quote the bar as
   a distribution. Three seeds spanning 2.7–7.4%/yr is not a bar.
3. **The revision family, on an instrument that can see it.** The gross signal
   is real-ish and the turnover kills it; both facts sit below the noise floor
   of the design that measured them.
4. **Ten separate LLM calls, each forbidden the previous answers' vocabulary**,
   scored by `lint_batch`. A testable claim about prompting, not about markets.

## 6. What prevents Optimus from being materially better today

**Its instruments cannot see effects of the size that actually exist.** Every
other constraint is downstream of that. The programme has been running a search
whose detection threshold is roughly double the largest credible equity anomaly,
recording the resulting ambiguity as knowledge, and building a registry on top
of it.
