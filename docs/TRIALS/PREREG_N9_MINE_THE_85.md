# PREREG — N9: can ANY rule in the existing grammar mark the 85% of exceptional moves the library misses?

**Registered:** 2026-08-16, before the search runs.

**Resurrects:** N4 — new instrument: N4 asked whether six hand-built precursors
cover exceptional moves. This asks whether the *grammar those precursors are
written in* can cover them at all, by exhaustively searching it with the full
denominator recorded.

## Why this, before paying for LLM autopsies

Order 3 §5 ranks N9 highest: take the exceptional moves with no precursor and
run the autopsy machinery on them, so N4's null becomes a *generator*. At
~$0.001 per structured autopsy that is cheap, and it is the right shape.

But an LLM autopsy's output has to **compile into the transferable vocabulary**
(`autopsy.TRANSFERABLE_FEATURES`: eight features) or it is refused. So there is
a question that comes first, costs nothing, and decides how to spend the dollar:

> **Does any rule expressible in that vocabulary mark the uncovered moves?**

If the answer is no, then no LLM story compiled into it will either, and the
finding is about the **grammar**, not about the moves — the autopsies would have
to be licensed to propose *new features*, which is a different and much more
expensive project. If the answer is yes, the search has produced candidates
directly and the LLM's job narrows to explaining the survivors.

This is the cheaper experiment that changes what the expensive one should be.

## Hypothesis

**H1:** at least one rule over the eight-feature transferable vocabulary marks
uncovered exceptional moves with lift ≥ `L_min` on foreign slices, where
`L_min` is N4B's break-even de-risking lift.

**H0:** no rule in the grammar does. The grammar, not the library, is the
binding constraint on coverage.

## The bar, inherited rather than invented

N4B derived the lift at which de-risking on a warning breaks even from the
return distribution: **1.69 at 20 days, 2.11 at 60 days**. A candidate that
cannot reach its horizon's number is not worth promoting *whatever* its
p-value, so that is the bar here too. Nothing about it was chosen to make this
search succeed — it was computed before this document existed, for a different
experiment, and is simply reused.

## The search, and its denominator

**Candidates.** Every clause `feature OP threshold` with `feature` in the eight
transferable features, `OP` in `{>=, <=}`, and `threshold` at the deciles of
that feature's own **training** distribution; plus every two-clause conjunction
over two *different* features. The exact count is computed and reported — it is
the multiple-comparison denominator and it is the reason this is a generator and
not a result.

**Target.** Not all exceptional moves — the ones the incumbent library MISSES.
A rule that re-finds what the six already mark adds nothing.

**Split, declared before the run.**

* TRAIN: `SPY`, `XLF`, `XLE`, dates ≤ 2015-12-31
* FOREIGN: `QQQ`, `IWM`, `XLK`, dates ≥ 2016-01-01

Different securities **and** a different period. A candidate is selected on
train and scored once on foreign. It is never re-tuned.

**Parent-barred.** The training securities and the training period are removed
from the foreign evaluation mechanically, not by convention.

## Decision rule (pre-committed)

| outcome | verdict |
|---|---|
| ≥1 candidate clears `L_min` on FOREIGN with lift − MDE > `L_min` | `CANDIDATE_GENERATED` — goes to the atlas as a hypothesis, never a claim |
| candidates clear on train, none on foreign | `NOT_DETECTABLE_IN_SCOPE` — the search found train-set artefacts, which is the expected outcome and must be reported as the expected outcome |
| no candidate clears `L_min` even on TRAIN | **`STRUCTURALLY_CLOSED` for this grammar** — the vocabulary cannot express a rule that marks these moves, in-sample, with the answer known. Ground: `oracle_no_headroom_same_objective`. |

The third row is the informative one and the reason the in-sample number is
reported at all: **an in-sample search that cannot find a rule with the outcome
in hand is a statement about the language, not about the sample.**

## What is reported regardless

* the exact candidate count (the denominator)
* how many cleared on train, and how many of those cleared on foreign
* **the number expected to clear foreign by chance**, given the denominator
* every survivor's lift, MDE, firing rate and n_effective

## R13 — resolvability, declared before compute

- event_frequency_per_year: 25
- declared_effect_size: 15pp
- outcome_dispersion: 2.3pp
- corpus_years: 27

(Coverage percentage points, as in N4B: base rate ~15%, so `L_min ≈ 2`
corresponds to ~15pp of coverage. Exceptional-move episodes are far more common
than crises — this is R14's point, and it is why this question is resolvable
where the crisis questions were not.)

## Run spec (frozen)

`python -m scripts.n9_mine_the_85` — universe SPY QQQ IWM XLF XLE XLK,
1999-01-01 to 2026-08-15, tail quantile 0.10, horizons 20 and 60, precursors
compiled from the same autopsy file N4 used, seed 20260816. ONE run.

## AMENDMENT 1 — the aggregate test, declared as EXPLORATORY, and its confirmation

Written 2026-08-16 after the first run and **before** the confirmation slice was
touched. Stated as an amendment rather than folded into the protocol above,
because a test designed after seeing a result is not the same object as one
designed before it, and pretending otherwise is the failure this whole session
is about.

**What the first run showed.** At 20 days, 582 of 13,728 rules cleared the bar
on train; none cleared it on foreign *individually*; and the foreign lifts of
those 582 did **not** collapse to 1.0 — median 1.51, p90 2.43. That is the
signature of an underpowered instrument used 461 times, not of overfitting. At
60 days the median was 0.91: the overfit signature, and a genuine null.

**The aggregate statistic, run post-hoc.** Median foreign lift of the selected
set, against a placebo that block-shifts the foreign forward returns (SS20:
a set selected for high train lift has no null of 1.0, so the null is measured
rather than assumed). Result: **1.513 vs placebo median 1.011 / p95 1.356,
p = 0.015** at 20 days; 0.905 vs 0.844, p = 0.428 at 60 days.

**This is exploratory and does not close or open anything on its own.**

**The confirmation, declared here before it runs.** The 582 rules selected on
train are **frozen** — no re-selection, no re-tuning, no threshold changes — and
scored once on six securities that appear in neither the train nor the foreign
slice:

    DIA, XLV, XLI, XLP, XLU, XLB          (period: the full history)

Primary statistic: the same median lift against the same block-shift placebo.

| outcome | verdict |
|---|---|
| p < 0.05 on the confirmation slice AND median lift ≥ 1.0 | `SUPPORTED_IN_SCOPE` — the grammar can mark uncovered moves; candidates go to the atlas |
| p ≥ 0.05 | `NOT_DETECTABLE_IN_SCOPE` — the 20-day aggregate was a two-slice coincidence |
| median lift < 1.0 with p < 0.05 | ANTI-transfer; report it and say so |

Whatever the confirmation says, the economic reading is already fixed: **a
median lift of 1.51 is below N4B's break-even 1.69.** A confirmed result here is
a statement about the grammar's reach, **not** an investable signal — the set
would transfer and still not pay for the trade it implies.

## Result (filled in AFTER the run — never edited afterwards)

- Verdict:
- Receipt:
