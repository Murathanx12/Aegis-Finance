# FEATURE-COVERAGE-AUDIT-1 — is missing data doing the arena's ranking?

**Run:** `python -m scripts.arena_coverage_audit` → `docs/FEATURE_COVERAGE_AUDIT_1.json`
**Date:** 2026-08-20 · **Status:** measured, defect fixed, the bigger finding is NOT fixed
**Class:** SIMULATION under a declared generative model. Not an alpha claim,
not measured on market data. It sizes two choices against each other; that is
all it is licensed to do.

---

## 0. The question

The arena composite z-scores each factor across the cross-section and takes the
**weighted mean of whatever factors a name happens to have**
(`multifactor.compute_multifactor_scores` — the frozen estimator, unchanged by
this work). That is documented behaviour. The audit asks what it *does*.

Two things can be wrong and they are not the same thing:

1. **Aggregation.** Averaging shrinks. A name scored on one factor has
   composite variance ~1; a name scored on six correlated factors has
   variance below that. Better-measured names get pushed toward the middle,
   and a top-k selection reads only one tail.
2. **Coverage.** In the live arena every one of the ~180 candidate names gets
   `mom_12_1`, while the five PIT score families are collected on the ~12-name
   book cross-section only. **~93% of the universe is ranked on 12-1 momentum
   and nothing else.**

## 1. Generative model (declared before the numbers)

180 names, latent skill `s ~ N(0,1)`, six factor views
`f_j = 0.6·s + 0.8·e_j` where the `e_j` are correlated at **ρ = 0.4** — the
Order-24 finding that the sources share 3–7 latent factors is the reason ρ is
high rather than near zero. 12 names carry all six factors, 168 carry
momentum only. 4,000 trials, seed 20260820. Selection is top-12.

## 2. Result — the aggregation defect is real and small

| rule | enriched names in the top-12 | mean latent skill of the selection |
|---|---|---|
| current (weighted mean of available) | **0.429** | 1.1562 |
| coverage-normalized | 1.139 | 1.1682 |
| oracle (true skill) | 0.774 | 1.9161 |

If coverage were irrelevant to rank, 12 enriched names out of 180 would appear
**0.80** times in a top-12. The current rule gives **0.43** — the
better-measured names are under-represented in the tail by ~46%, exactly as
the shrinkage argument predicts. The defect is real.

Its cost is not: normalizing buys **+0.012** in latent-skill units, **1.6% of
the oracle gap**. Twelve names of 180 cannot move a twelve-name selection much
however they are treated.

## 3. The finding that matters — coverage, not aggregation

Same generator, same normalized aggregation, three coverage worlds:

| world | mean latent skill of the selection | value vs momentum-only |
|---|---|---|
| momentum only (what 168/180 names get today) | 1.1501 | — |
| current split (12 enriched, 168 not) | 1.1698 | **+0.020** |
| full coverage (all 180 on all six) | 1.3889 | **+0.239** |
| oracle | 1.9194 | +0.769 |

**Widening coverage to the whole universe is worth ~20× the aggregation fix**
(+0.239 vs +0.012) and closes **31% of the oracle gap**. The current split
buys +0.020 — within rounding distance of nothing.

**Read plainly:** ORDER 25's premise was that the arena is "the caller the 16
descriptive collectors never had". Under the live coverage split that is true
for 12 names out of 180. For the other 168 the arena is a 12-1 momentum
ranker, and no aggregation rule changes that.

## 4. What was changed

* `discovery._add_arena_composite` now divides each name's weighted **sum** by
  the standard deviation implied by **its own** available set, so every name's
  composite has unit variance whatever it was scored on. The factor
  correlation is estimated pairwise and **shrunk toward ρ = 1**, because ρ = 1
  reproduces the plain weighted mean exactly — with no evidence the estimator
  degrades to its own predecessor rather than to a third behaviour.
* `arena_composite_raw_mean`, `coverage` (which factors) and `coverage_n` are
  frozen into the daily state beside the score; `coverage_histogram` goes into
  the day state, every book receipt, the run summary and the scheduler log
  line. The 93%-momentum-only fact cannot go quiet again without the log
  saying so.
* **`spec.policy_fingerprint`** — a separate defect this audit surfaced. The
  YAML SHA-256 was segment identity for the books, but the estimator they
  select on lives in Python. Editing the composite changed every book's policy
  while every config hash stayed byte-identical and every seed still verified.
  Identity now covers `config_hash | discovery.COMPOSITE_VERSION`, is written
  into the seed, and `assert_config_current` refuses to run a book whose
  estimator changed meaning mid-segment.

## 5. What was NOT changed, and why

The registered collectors' cross-sections are **not** widened. Their z-scores
are cross-sectional; widening them mid-trial changes the registered forward-IC
trials (`TRIAL-MULTIFACTOR-IC`, `TRIAL-REVISIONS-IC`, `TRIAL-PEAD-IC`,
`TRIAL-QUALITY-IC`, `TRIAL-INSIDER-IC`). `compute_multifactor_scores` is
untouched.

The door this audit says to walk through is different: the **arena computes
its own features over its own universe** — that is what `arena_composite`
already is for `mom_12_1`. Adding arena-local, universe-wide, PIT-clean
features (the trackers) is the +0.239 experiment. It does not require touching
a single registered trial.

## 6. Caveats that bind any use of these numbers

* ρ = 0.4 is a declared assumption, not a measurement on the arena's own
  factors. At higher ρ the coverage value shrinks (redundant views add less);
  at lower ρ it grows. The **direction** (coverage ≫ aggregation) is robust
  across that range; the magnitude is not.
* Latent-skill units are not returns. Nothing here says +0.239 of anything is
  worth a basis point.
* This is a sizing argument for where to spend the next build. It is not
  evidence that the arena selects well, which no simulation can be.
