# PREREG — N20: is the forgone return in N4B's break-even the return you actually forgo?

**Registered:** 2026-08-16, before the conditional statistic exists. N4B's
point estimates (`b9ee663`) are public and are **not** re-estimated here as
though they were new. What is new is a **different estimand** for one term of
the break-even, its standard error, and a decision rule that was written down
before the number was seen.

**Resurrects:** N4B — new instrument: the forgone-return term is re-estimated
**conditional on the precursor firing**, which is the population the action
actually removes exposure from. N4B measured it unconditionally. That is not
"trying again"; it is a different quantity with a different value.

**Slice:** the N4B exploration universe — `SPY QQQ IWM XLF XLE XLK`, shared
calendar, 1999-01-01 → 2026-08-15. This slice is **already spent** (N4, N4B).
This trial is registered as a **re-analysis of a consumed exploration slice**,
NOT as confirmation. It cannot confirm anything and does not claim to. The
untouched confirmation slice (`DIA XLV XLI XLP XLU XLB`) is **not** touched
here — it was spent by N9 and again by N9B, and consuming it a third time
would be a refusal.

## Why this exists

N4B derives the minimum economically meaningful lift as

```
L_min = (μ_rest + c) / ( q · (|μ_tail| + μ_rest) )
```

and computes `μ_rest` at `n4b_coverage_equivalence.py:205` as

```python
mrs.append(float(f[~mask].mean()) / 100.0)
```

— the mean H-day forward return over **every** non-tail observation.

The action being priced is *"when a precursor fires, cut exposure for H days."*
The return that action forgoes is not the unconditional non-tail return. It is
the non-tail return **on the days the precursor fired**, because those are the
only days exposure is actually removed. If firing days are, on average, worse
than a random day even when no tail follows — which is what a partially
informative warning would look like — then the true forgone return is smaller
and the break-even is lower than N4B reported.

Those two quantities are equal only if firing is independent of the non-tail
return distribution. That is an assumption N4B made implicitly and never tested.
This trial tests it.

## What N4B was protecting, and what this trial gives up

N4B's docstring states the design intent plainly:

> `mu_tail` and `mu_rest` are properties of the unconditional forward-return
> distribution. They cannot be moved by anything this test discovers, which is
> what makes the margin prospective in the only sense that matters.

That is a real property and this trial **forfeits it**. A margin conditioned on
`fire` depends on the precursor library, so it can be moved by the thing being
tested, and it is therefore vulnerable to exactly the circularity N4B avoided.

This is a genuine trade-off, not an oversight being corrected, and the honest
resolution is to report **both**:

| estimand | property | what it is good for |
|---|---|---|
| `μ_rest` unconditional | immune to the signal, prospective | a margin that cannot be gamed |
| `μ_rest \| fire` | the action's real economics | deciding whether to deploy |

Neither supersedes the other. A result is only reported as a break-even claim
when it is stated against a named estimand. **Both are primary outputs; neither
is permitted to be selected after seeing the other.**

## Hypothesis

**H0 (the null this trial defends):** `E[R | fire, not tail] = E[R | not tail]`.
Firing carries no information about the non-tail return, so N4B's break-even is
the correct break-even and Order 5's threshold argument is moot.

**H1:** `E[R | fire, not tail] < E[R | not tail]`. Firing days are worse than
average even when no tail follows, so the true `L_min` is **below** N4B's.

**Honest prior, stated before running:** I expect a negative difference that is
real but small, because the precursors are largely volatility- and
drawdown-state rules and elevated-volatility states have historically carried
*lower* mean returns. I expect it to be **too small to move `L_min` from 1.6907
to below N9's 1.271 at 20d**, because closing that gap requires the conditional
non-tail mean to fall from 2.158% to under 1.516% — a 30% reduction in the
forgone return. I am registering that I expect this trial to **fail to rescue
N4B**, and registering it now so the expectation cannot be revised afterwards.

## Primary metric — the ONE deciding number

**`L_min(μ_rest|fire)` at H = 20d, bottom tail, cost = 0.0010**, with a
moving-block bootstrap 90% interval, compared against **L = 1.271** (N9's
confirmed transfer lift, `2ba9fb3`).

Everything else — 60d, top tail, the cost grid, the block-multiplier grid, the
raw difference in means — is **reported, never deciding**.

## Decision rule, committed before the number exists

Let `CI_hi` be the upper end of the 90% bootstrap interval on `L_min(μ_rest|fire)`.

| condition | verdict |
|---|---|
| `CI_hi < 1.271` | `BREAK_EVEN_CLEARED_IN_SCOPE` — the action is economically live on this slice and earns a confirmation trial on an unspent slice |
| interval spans 1.271 | `NOT_RESOLVED` — the conditional correction is real but the slice cannot decide it; report the width, do not pick a side |
| `CI_lo > 1.271` | `REFUTED_IN_SCOPE` — conditioning does not rescue N4B; the full-de-risking action stays dead and the surviving levers are payoff shape and objective, not the estimand |

**Weakest-cell reporting is inherited from N4B**: the verdict reported is the
weakest one produced anywhere in the cost × block-multiplier grid. Reporting the
headline cell would be choosing the flattering assumption after seeing the answer.

**Power gate (R13).** If the 90% interval on the *difference*
`E[R|fire,¬tail] − E[R|¬tail]` is wider than the difference required to move
`L_min` below 1.271, the trial reports `NOT_DETECTABLE_IN_SCOPE` and **may not
report either of the other three verdicts.** The required difference is computed
from the registered formula before the bootstrap runs and printed alongside it.
A null here is a statement about this slice's power, never about the world.

## Power declaration (R13) — measured at the design stage, estimand unseen

Produced by `python -m scripts.n20_conditional_mu_rest --power-only`, which
computes the fire rate and the outcome dispersion and is **structurally unable
to compute the conditional mean** — it never calls `_conditional_mu_rest`. The
declared effect size is inverted from the frozen `L_min` formula, not read off
the data.

```
declared_effect_size      = 0.642 pp   (20d, primary)   mu_rest 2.158% -> 1.516%
                            2.200 pp   (60d, reported)  mu_rest 4.742% -> 2.542%
event_frequency_per_year  = 40.3       (precursor fires on 16.0% of days,
                                        pooled across the six securities)
outcome_dispersion        = 6.20 pp    (sd of 20d forward return, pooled)
                            10.45 pp   (sd of 60d forward return, pooled)
```

Standardised effect at the primary horizon: **0.642 / 6.20 = 0.104**. With 20d
overlapping windows on 6,591 shared days the block bootstrap has on the order of
330 independent blocks, and the six securities co-move, so the effective
cross-section is nearer one than six. **This design is close to its own
resolution limit and may well return `NOT_DETECTABLE_IN_SCOPE`.** That is
registered here, in advance, as an expected and acceptable outcome — a null from
this trial is a statement about the slice, never about the world.

At 60d the required effect is 2.200pp against a 10.45pp dispersion with roughly
110 independent blocks. **I expect 60d to be underpowered outright** and am
registering it as reported-never-deciding for that reason as well.

## Frozen parameters — not tunable mid-trial

```
UNIVERSE   = SPY QQQ IWM XLF XLE XLK      (N4B's, unchanged)
HORIZONS   = (20, 60)                      primary = 20
TAIL_Q     = 0.10                          unchanged from N4B
COST       = 0.0010                        grid (0.0, 0.0010, 0.0025) reported
SEED       = 20260816
N_BOOT     = 2000
BLOCK_MULT = (0.5, 1.0, 2.0)
comparison lift L = 1.271                  frozen from N9, not re-estimated
```

Block starts are drawn **once per replicate and shared across all six
securities** on the common calendar — N4B's discipline, kept, because
resampling six co-moving ETFs independently is the error that manufactured
confidence in γ* (SS41).

## What this trial may NOT do

- It may **not** claim confirmation. Its slice was consumed twice before it.
- It may **not** be used to revive partial sizing. δ cancels exactly under
  linear exposure and proportional cost (erratum `4784faa`); this trial changes
  one estimand, not the payoff shape.
- It may **not** license deployment on its own. A cleared break-even here buys
  a confirmation trial on an unspent slice, nothing more.
- It may **not** substitute for the direct policy-utility measurement
  (`U(precursor sizing) − U(baseline)`), which is a different and better test.
  This trial prices one term of a model; that one measures the thing itself.

## Contamination clause

If the precursor library on disk differs from the one N4B compiled — different
autopsy file, different compiled count — the run is **void** and re-registered,
because the conditioning set would not be N4B's conditioning set and the
comparison to 1.6907 would be against a different world.
