# Verdict corrections — the 2026-08-15/16 overnight ledger

Ordered by the principal review of 2026-08-16 §1 and §12. Four corrections, one
of them found while making the other three. Every number below comes from the
saved artifacts, not from the morning report.

**Nothing here changes a measurement. Every correction is to a label.** That is
the point: this programme's stated failure mode is turning "we could not see it"
into "it is not there", and three of the four corrections are exactly that
substitution, made by us, in a report whose §9 was about how to avoid it.

---

## C1 — D4 is `NOT_DETECTABLE_IN_SCOPE`, not a kill

The pre-registration, committed at `f091809` before any number existed
(`docs/OVERNIGHT_2026-08-16_PROTOCOL.md:171`):

> If the gated policy's utility edge does not clear the MDE of its difference
> against the unconditional one (§18 — the DIFFERENCE, with its own SE), **D4 is
> NOT_DETECTABLE and is reported as such.**

What was measured (`backend/data/optimus/research_gym/n6_moments.json`,
`d4_magnitude_gated_direction`):

| H | AUC unconditional | AUC top-quintile magnitude | difference | MDE of the difference | verdict |
|---|---|---|---|---|---|
| 5d | 0.4989 | 0.4934 | **−0.0056** | 0.0375 | not detectable |
| 20d | 0.5123 | 0.5089 | **−0.0034** | 0.0396 | not detectable |
| 60d | 0.4965 | 0.5007 | **+0.0042** | 0.0539 | not detectable |

Every difference is between one seventh and one tenth of its own MDE. The
morning report nonetheless recorded *"cheap kills: 2 (D4; the reactive-corpus
hope)"* and *"D4 killed"*.

**Corrected verdict: `NOT_DETECTABLE_IN_SCOPE`.** It closes nothing. The
resurrection condition is an instrument with roughly an order of magnitude more
power on the conditional-AUC difference — six folds of a twelve-security panel
cannot see a 0.005 AUC difference and was never going to.

**And the part worth keeping:** `scripts/n6_moments.py:341` prints
`-> D4 NOT_DETECTABLE at every horizon`. The code obeyed the protocol. The
mislabelling happened in the summary, between a correct artifact and a human
sentence — which is the cheapest place for it to happen and the hardest to
catch with a test.

---

## C2 — N6's rv20 comparison: the MDEs existed and were not printed, and one claim is wrong

The report wrote:

> model minus baseline: −0.085 to +0.025. Not detectable anywhere. […] at sixty
> days **it is materially worse**.

Those two sentences contradict each other, and the second is wrong. The full
saved comparison, which the report reduced to a range:

| H | target | model | rv20 alone | diff | MDE of diff | verdict |
|---|---|---|---|---|---|---|
| 5d | \|return\| | 0.2963 | 0.3005 | −0.0042 | 0.0369 | not detectable |
| 5d | realised vol | 0.5365 | 0.5203 | +0.0162 | 0.0982 | not detectable |
| 20d | \|return\| | 0.2431 | 0.2795 | −0.0364 | 0.0682 | not detectable |
| 20d | realised vol | 0.6223 | 0.5967 | +0.0256 | 0.0766 | not detectable |
| 60d | \|return\| | 0.1622 | 0.2472 | **−0.0850** | **0.1802** | not detectable |
| 60d | realised vol | 0.5650 | 0.5624 | +0.0027 | 0.0814 | not detectable |

The −0.085 at sixty days sits at **47% of its own MDE**. It is the least
detectable cell in the table, not evidence of the model being worse.

Two corrections follow.

1. **The order's N11.1 is already satisfied in the artifact.** Every rival
   comparison carries `diff_mde`; `scripts/n6_moments.py:273` prints it. The
   report dropped it while quoting the range. The failure was in reporting, not
   in instrumentation — worth knowing, because building an MDE that already
   exists is a night spent on nothing.
2. **Delete "do not expect ML to add to it."** The supported statement is:
   *this model was not shown to add incremental information over rv20 at the
   power of this experiment* — a statement about six folds, not about ML.

---

## C3 — N6's comparative claim needs §18 or it needs rewording

Kept, because it was measured: **direction was not detectable and both second
moments were, on the same features, the same model class and the same folds.**

Not supported by that alone: *second moments are more predictable than first
moments.* That is the §18 error the canon already names — detectable in A and
not detectable in B is not a test of A−B. It is worse here than in the usual
case, because AUC-ROC and Spearman IC are not on a common scale, so the point
estimates cannot be differenced at all.

Two ways to earn the comparative claim, neither yet run:

* put both moments on a **baseline-relative skill** scale (skill score against
  the same climatological benchmark), so a difference exists to test; or
* skip the statistical comparison and go to **downstream economic utility** —
  what does a decision made on each moment earn in log-wealth. That is the
  objective this programme declared anyway, and it makes the comparison
  meaningful rather than merely computable.

Until then the claim is: *first-moment predictability was not detectable here;
second-moment predictability was.* Which is enough to order the build queue, and
not enough for a paper.

---

## C4 — N4 has not demonstrated coverage; it has not shown coverage is absent

The descriptive result stands and is the week's most important number:

> **85.6% / 87.6% of exceptional moves were preceded by no precursor in the
> six-mechanism library**, whose unconditional firing rate is 15.3%.

The inference drawn from it does not. Pooled lift against MDE, recomputed from
the saved rows:

| H | tail | pooled lift | sd across cells | n_eff | MDE | what the report said | what it supports |
|---|---|---|---|---|---|---|---|
| 20d | bottom | 0.946 | 0.147 | 2.0 | 0.292 | "NO COVERAGE" | not demonstrated |
| 20d | top | 1.152 | 0.124 | 2.0 | 0.246 | "NO COVERAGE" | not demonstrated |
| 60d | bottom | 0.820 | 0.315 | 2.0 | 0.624 | "NO COVERAGE" | not demonstrated |
| 60d | top | 1.078 | 0.181 | 2.0 | 0.359 | "NO COVERAGE" | not demonstrated |

Failure to separate a lift from 1.0 is a statement about the instrument. With
an MDE of 0.62 at sixty days the interval still covers lifts that would change
a portfolio decision.

**And this one was not a reporting slip.** The string `"NO COVERAGE"` was the
literal verdict emitted by `scripts/n4_precursor_coverage.py:207`, computed as
`abs(mean_lift - 1.0) < mde`. The false kill was compiled in. It now reads
`NOT DEMONSTRATED`, and the equivalence test that could turn it into a real
negative is registered separately (`docs/TRIALS/PREREG_N4B_COVERAGE_EQUIVALENCE.md`)
with its margin derived from economics before the estimate is looked at.

Corrected statement: **the six-rule library has not demonstrated precursor
coverage beyond its own base firing rate.** The programme-level implication the
order ratified is untouched by this correction — coverage, not validity, is the
binding constraint either way, because *demonstrated* coverage is what a
library has to have to be worth adjudicating.

### C4b — and then the equivalence test ran, and it says more than the null did

`N4B` (prereg registered before the statistic existed; run 2026-08-16) supplies
the margin the null was missing. The library's only declared action is to cut
exposure when a precursor fires, so `L_min` is whatever makes that trade
break even:

```
L_min = (mu_rest + cost) / ( q * (|mu_tail| + mu_rest) )
```

| H | tail | lift | precision | upper 95% bound | break-even `L_min` | verdict |
|---|---|---|---|---|---|---|
| 20d | bottom | 0.954 | 9.5% | 1.257 | **1.69** | **`RULED_OUT`** |
| 60d | bottom | 0.808 | 8.1% | 1.234 | **2.11** | **`RULED_OUT`** |

Stable across all nine cost × block-length combinations. **So the honest verdict
is stronger than the corrected one, not weaker: `REFUTED_IN_SCOPE` as a
de-risking trigger.** When a precursor fires, a bottom-decile move follows 9.5%
of the time; cutting exposure needs 16.9%. The upper bound of the interval does
not reach break-even either.

This is the first powered negative the programme has produced from an
equivalence test rather than from a failure to detect, and it exists only
because the margin was derived from the return distribution instead of from
whatever the sample could see. **The correction to C4 was not a softening —
demanding the right test made the result sharper.**

---

## The corrected accounting

| | as reported | corrected |
|---|---|---|
| dollars spent | $0.00 | $0.00 |
| serious distinct hypotheses attempted | 5 | 5 |
| **cheap kills** | **2** | **1** — the reactive-corpus hope only |
| **`NOT_DETECTABLE_IN_SCOPE`** | (not a category) | **1** — D4 |
| unresolved / underpowered | 1 | 1 — N8's headline |
| survivors | 1 | 1 — N6, scoped per C3 |
| findings that changed architecture | 3 | 3 |
| defects found | 2 | **3** — plus the compiled-in "NO COVERAGE" verdict |
| new investment candidates | ZERO | ZERO |

**Net: one fewer kill, one more defect.** Both moves are in the direction the
methodology exists to enforce, and both were found by a reader who checked the
verdicts against the pre-registrations rather than against the prose.

## The category rule (review §12), binding from here

Every future report separates, and never pools:

* `REFUTED_IN_SCOPE` — powered evidence against, or an equivalence test that
  ruled out the economically meaningful region
* `NOT_DETECTABLE_IN_SCOPE` — ran, below its own MDE, says nothing
* `UNPOWERED_IN_SCOPE` / `UNPOWERED_AT_REGISTRATION` — never could have resolved it
* `STRUCTURALLY_CLOSED` — genuine impossibility

and reports **descriptive findings**, **scientific findings**, **infrastructure
findings** and **investment candidates** under separate headings. A result can
matter without being investable; the categories may not blur.

— builder, 2026-08-16
