# PREREG — IV-ORACLE-GAP-1

**Registered 2026-08-16, before any OptionMetrics row has been pulled.**
Status: `REGISTERED`. Nothing below was computed on option data; every number
in the power section is measured on the **existing WM0 artifact**, which
contains no option information at all.

---

## 1. The question

WM0's 2×2 measured a bound rather than a mechanism. Holding the conditional
*shape* fixed and empirical, and replacing the estimated *scale* with a
perfect one:

| | tail pinball |
|---|---|
| empirical shape / estimated scale | **0.83021** |
| empirical shape / **oracle** scale | **0.65255** |

A gap of **0.17766 absolute, 21.4% relative**, and it is the only positive the
world-model family produced. It is an upper bound from an unattainable oracle
and it is evidence for nothing deployable. What it says is *where the next head
should look*: at the scale rung, which N11 measured as commoditised **by
ranking** — four forecasters indistinguishable on IC, on the same folds.

Ranking cannot climb that gap, because the gap is a **level** quantity. So:

> **How much of the 21.4% oracle-scale tail-pinball headroom can information
> already present in option prices recover?**

Bounded, informative in both directions, and it terminates a rung either way.
If daily IV recovers a material share, the volatility layer has headroom that
free data cannot reach and the product has a reason to carry a paid dependency.
If it recovers approximately none, the scale rung is closed against the best
observable information anyone has, N11's "commoditised" verdict is upgraded
from a ranking claim to a level claim, and the search moves off volatility
entirely.

## 2. Hypotheses

**H1 (primary).** At least one option-derived rung reduces block-mean **tail
pinball** at H=20 versus the best cheap realised-volatility rung, by at least
the declared effect, on the Phase-A window.

**H0.** No option-derived rung improves on the best cheap RV rung by the
declared effect. Reported as an **equivalence** result against that margin, not
as "no evidence" — a null here owes both tests (MDE and equivalence).

**H2 (secondary, no separate power claim).** The recovered fraction of the
oracle gap, `(L_cheap − L_IV) / (L_cheap − L_oracle)`, reported with its
interval. This is the number the question asks for and it is a **ratio to a
constant measured on the same panel** — see §7.

## 3. The rungs

Every rung is specified from the literature **before** any data is pulled and
none is tuned on this corpus. Fitting anything here converts this trial from
EXPLORE to something that needs a parent declaration; see §6.

**Cheap (free data, incumbent):** `rv20` · `EWMA` · `HAR` · `log-HAR`
**Option-derived (the question):** `ATM IV` (30d constant-maturity) ·
`IV − RV20 gap` · `term slope` (60d − 30d ATM) · `downside skew`
(25Δ put − ATM) · `simple RV + IV convex combination, weight fixed a priori
at 0.5`

The 0.5 weight is fixed rather than fitted on purpose: a fitted weight is a
free parameter and would need its own selection window.

**No neural network in this trial.** The 2×2 already refuted the
estimator-bottleneck hypothesis; adding capacity to a rung whose ceiling is
being measured would confound the measurement with the fit.

## 4. Losses — the level ladder N11 still owes

Primary: **tail pinball** (quantiles ≤ 0.10, the WM0 definition).
Reported beside it, no separate power claim: mean pinball · QLIKE · MSE ·
log-MSE · Mincer–Zarnowitz slope and intercept · decile calibration · bias ·
upper-tail forecast error · downstream vol-target sizing utility.

Rank IC is reported and is **not** a decision input. N11 established that
ranking cannot see this rung; running the same instrument again and reading it
as an answer would be the §37 error.

## 5. Power — R13 / R13b / R13c / R13d

All measured on `wm0_world_model_v0.npz` before any option data exists. The
surrogate pair is `scaled_empirical` vs `gaussian_vol` — two conditionally
scaled forecasters differing only in how the scale is formed, which is the
closest available analogue of "same shape, different scale information", i.e.
exactly the comparison this trial will run.

```
event_frequency_per_year = 6.37
declared_effect_size     = 5.35pp
outcome_dispersion       = 4.105pp
outcome_horizon_days     = 20
corpus_years             = 14.0
dependence_unit          = one contiguous 40-trading-day block of the whole
                           18-security cross-section, pooled
cross_sectional_n        = 1
```

* **`corpus_years = 14.0`** — the Phase-A window only (§6). 3,523 trading days.
* **`event_frequency_per_year = 6.37`** — 89 blocks / 13.98 years, counted from
  the panel rather than declared. R13b's cap at the declared horizon is
  252/20 = 12.6, so this rate is below it by a factor of two — and that is not
  luck: the block is **40 trading days against a 20-day horizon**, so no two
  blocks can share a label window. The binding constraint is the block length,
  not the cap, which is the right way round.
* **`outcome_dispersion = 4.105pp`** — **measured**: sd of the per-block tail
  pinball *difference* on the surrogate pair, 0.03211 against a Phase-A
  baseline of 0.78202, = 4.105% of baseline. Not assumed, not a preset.
* **`cross_sectional_n = 1`** — the block already pools all 18 securities, so
  the count is of **date blocks, not rows** (§58). Declaring a cross-sectional
  multiplier on top would count the cross-section twice.
* **`declared_effect_size = 5.35pp`** — 25% of the 21.4% oracle gap. The
  economic argument, and it is a cost argument rather than a sample argument:
  recovering less than a quarter of an unattainable ceiling does not justify
  adding a paid daily data dependency, a nightly extraction and a new failure
  surface to a product whose incumbent rung is free. It is **declared before
  the measurement and does not move afterwards.**

Implied: `n_required ≈ 4.6` blocks against `n_available = 89` — about **19×
headroom**, and the smallest resolvable effect is ~1.22% of baseline, i.e. 5.7%
of the oracle gap.

### The refusal this design accepts in advance

The dispersion above is measured on the **closest** surrogate. A less
correlated pair is far noisier — the same computation against `climatology`
gives sd 0.369/block and an MDE of 51% of the gap, which would make this
design unpowered. **Before H1 is read, the per-block dispersion is recomputed
on the actual cheap-vs-IV pair.** If the realised MDE exceeds 5.35pp, the trial
terminates `UNPOWERED_AT_REGISTRATION` and no p-value is reported. That
recomputation uses the predictions only, never the outcome ordering.

## 6. Slice claim and R13e

```
slice_purpose             = EXPLORE
selection_period          = NONE
parent_trial              = NONE
benchmark_source          = WM0  (the 0.17766 constant only — NOT fitted here)
hypothesis_source         = WM0                                     ← R13f
hypothesis_source_period  = 2006-01-03 .. 2026-07-17                ← R13f
```

**Why EXPLORE and not CONFIRM.** This trial measures a bound. It cannot and
must not be described later as a transfer result, and saying so now is what
that costs. Every rung is literature-specified, so no window of this corpus
selected them; `parent_trial = NONE` is the claim on the record, and it is
**false if any weight, threshold or rung is chosen after looking at Phase-A
output.** If that happens the trial is re-registered with WM0's window declared.

**Why `benchmark_source` is not `parent_trial`.** WM0 supplies a constant that
this trial divides by. It selected none of the rungs. Treating a benchmark
source as a parent would spend the calendar of every trial that ever quotes a
prior measurement — the over-strict reading R13e was explicitly scoped to
avoid. The distinction is declared here so a reader can attack it rather than
discover it.

**AMENDED 2026-08-16, and the amendment weakens this document.** The paragraph
above is correct and was *not sufficient*, which two reviewers caught
independently. There is a third relation to a prior trial that neither
`parent_trial` nor `benchmark_source` names: **WM0's 21.4% oracle-gap
measurement is the entire reason this question exists.** WM0 selected nothing
here — every rung is literature-specified — so `parent_trial = NONE` stays true.
But WM0 read the panel **end to end**, including every date in Phase B.

So Phase B is **not pristine confirmation**, and the original §6 wording
("it exists so that a confirmation is *possible*") oversold it. Under `R13f`
(`prereg_power.check_hypothesis_provenance`, built out of this) Phase B's own
pre-registration will return:

```
ADAPTIVE_HISTORICAL_VALIDATION      may_claim_independent_confirmation = False
```

That is a **claim ceiling, not a refusal** — Phase B runs, and it is written up
as *validation on dates whose outcomes were already seen by the work that raised
the question*. The honest upgrade path is a route WM0 never read: a foreign
market, a security set outside WM0's eighteen, or forward time. **None of those
exists yet, so the strongest result this family can currently produce is an
adaptive validation, and saying so now costs nothing while saying it later would
cost the result.**

R13f's rule, stated so it cannot drift: **the test is selection, not citation.**
If a prior trial chose which rungs exist, it is a parent and spends the calendar.
If it supplies a number this one divides by, it is a benchmark and spends
nothing. If seeing its outcomes is why the hypothesis exists, it is a
`hypothesis_source` — it spends no calendar but it caps the claim.

**The calendar is split at registration, which is the whole point of R13e.**

| | window | trading days | blocks |
|---|---|---|---|
| **Phase A — this trial, EXPLORE** | 2006-01-03 .. 2019-12-31 | 3,523 | 89 |
| **Phase B — reserved, NOT run here** | 2020-06-01 .. 2026-07-17 | — | ~41 |

The 153-day gap clears R13e's requirement at every horizon this family uses
(42 days at H=20, 98 at H=60). Phase B is **not** registered by this document
and no result from it may be quoted; it exists so that a *second look* is
possible rather than discovered to be impossible three sessions after a
positive. Its own pre-registration must pass R13e with
`selection_period = 2006-01-03 .. 2019-12-31` and `parent_trial = IV-ORACLE-GAP-1`
— and will return `ADAPTIVE_HISTORICAL_VALIDATION` under R13f, per the
amendment below.

**Known and stated:** Phase B contains COVID and is not a regime-typical
window. A confirmation there is a confirmation on an unusual slice, and that
belongs in its verdict rather than in a footnote afterwards.

**Also known and stated:** the WM0 panel has already been read end-to-end by
WM0 as EXPLORE. If a future confirmation declares WM0 a parent, the register
will refuse this calendar entirely and the confirmation will need forward time
or a foreign market. Phase A is deliberately scoped so that this trial's *own*
lineage does not spend Phase B.

## 7. What H2's ratio can and cannot say

The denominator `L_cheap − L_oracle` is measured on the same panel as the
numerator. So the recovered *fraction* inherits that panel's noise twice and is
reported with an interval, never as a point. If the interval spans zero the
honest statement is "the recovered fraction is not resolvable here", not "IV
recovers X%".

The oracle is also **unattainable by construction** — it is a ceiling, not a
competitor. A rung recovering 40% of it is not 40% as good as anything that
exists.

## 8. Null specification (Null Invariance Contract)

The primary is a **paired block difference**, so its null is a permutation of
the *sign* of the per-block difference, which holds fixed by construction:
block membership, block length, the cross-sectional composition of each block,
and the calendar. It does **not** hold fixed the serial correlation of the
difference across adjacent blocks; that is declared here and measured by
`research_gym.null_invariance` before the p-value is accepted. If the measured
invariances disagree with this declaration, the p-value is refused, per §57.

A path-dependent secondary (sizing utility) is moved by the arrangement of
exposure and gets a circular block-shift null of the actual weight path, not a
uniform-window placebo. That is the N21 lesson and it is not re-learned here.

## 9. Data provenance — declared before the pull

Source: OptionMetrics IvyDB US, `optionm.vsurfd` — the **daily** standardised
volatility surface. The month-end limitation reported twice in this programme
was **our own `WHERE` clause**, not a vendor limitation, and this trial exists
partly because that was checked rather than repeated.

Recorded at pull time, in a manifest, before any analysis: exact SQL · query
timestamp · schema · date coverage · secid coverage · surface coordinates per
security-date · row count · content hash. The extraction is a **new immutable
dataset version**; the existing month-end extraction is not overwritten. A run
made under a different extraction is evidence about the process that produced
it, not about the world.

ETF secid mapping is by CUSIP/ticker with the mapping table itself hashed. Any
security-date whose surface is absent is **named**, never imputed; a rung
scored on a partially covered panel against one scored on a full panel is a
comparison of coverage, not of information.

## 10. Decision rule

* **H1 supported** — a rung beats the best cheap rung by ≥5.35pp of baseline
  tail pinball, the paired-block interval excludes the margin, and the null
  passes its invariance contract. Consequence: register Phase B. **No product
  change on Phase A alone.**
* **H1 refuted in scope** — the interval excludes the declared effect in the
  *other* direction: an equivalence result. Consequence: the scale rung is
  closed against option information on this universe and window, N11's
  commoditisation verdict is upgraded to a level claim, and volatility
  forecasting stops consuming research budget.
* **NOT DETECTABLE** — the recomputed MDE exceeds 5.35pp. No verdict about the
  world, a verdict about the instrument, and the design is reported as
  unpowered rather than as a null.

Earliest decision date: **on completion of the Phase-A run**, which requires
the daily extraction to exist. No interim read of H1 at any partial coverage.

## 11. Cost and scope

Compute is trivial: eight rungs, one panel, no training. The cost is the
extraction and the analyst-time to verify it. **This trial touches no
production path, no lane, no NAV, no live registry, and deploys nothing.**
