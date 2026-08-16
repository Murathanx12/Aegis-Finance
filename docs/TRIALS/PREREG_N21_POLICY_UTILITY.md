# PREREG — N21: what does the precursor policy actually PAY, on securities nobody has read?

**Registered:** 2026-08-16, after `--freeze` and `--power-only` and **before**
any utility difference exists. The frozen rule set is committed with its hash;
the power stage read prices and computed no policy outcome.

**Resurrects:** N4B / N9 — new instrument: every prior result prices the
precursors through a *model* of the action (`L_min`). This measures the action.

**Slice:** `XRT XHB KRE XOP ITB SMH IBB IGV`, 2006-07-01 → 2026-08-15. The
slice register reports these as read by **no trial** at H=20. Claimed as
`CONFIRM`. The spent slices — `SPY QQQ IWM XLF XLE XLK` (N4, N4B, N20) and
`DIA XLV XLI XLP XLU XLB` (N9, N9B) — are not touched.

---

## What is frozen, and how you can check it was frozen first

```
frozen rules       docs -> backend/data/optimus/research_gym/n21_frozen_rules.json
rules_sha256       8093cf7306159108ecacca4499a1297b3a39ad42a6b21a7264c224cb5a5c9ac0
n_rules            598          selected on SPY/XLF/XLE to 2015-12-31 at lift >= 1.69
search denominator 13728        every survivor is quoted against this
aggregation        vote_share >= theta
theta              0.1371       calibrated on TRAIN to the incumbent library's
                                13.7% firing rate — NOT on the fresh slice
```

`--freeze` never downloads a fresh-slice ticker, so a rule cannot have been
chosen with any knowledge of the evaluation data. The run stage recomputes the
hash and **refuses** if the file has been edited.

### Two things the freeze stage found, recorded because they are corrections

1. **N9's selection has a 20-day embargo leak.** N9 downloads prices to 2026
   and slices to `TRAIN_END` *after* computing `fwd_20`, so its late-2015
   training rows carry forward returns built from up to 20 trading days of 2016
   — across the train/foreign boundary. This freeze cannot commit it (it never
   downloads past the cutoff), which is why it selects 598 rules where N9
   reported 582. Reproducing N9's download window here returns **exactly 582**,
   which is how the cause was established rather than guessed. ~60 of ~12,830
   rows, 0.5%. N9's headline was a confirmation result on six *other*
   securities over 2016–2026, which 20 days of early-2016 SPY/XLF/XLE prices
   cannot plausibly inform. Recorded because "small and probably immaterial" is
   how a leak survives.

2. **The union of 598 rules is not a policy.** OR-ing them fires on 76% of
   train days and 75–99% of fresh-slice days — that is holding cash, not a
   signal. N9 scored rules *individually* and never as a set, so the set had no
   defined aggregation. The vote threshold above is that definition, calibrated
   on train. The fresh slice's union firing rate was seen at the design stage
   and is what exposed the defect; no return or utility was computed from it.

---

## The unit problem, and why it decides the whole design

Terminal wealth over one path is **one number per security**. Eight co-moving
ETFs are not eight observations, and a test with `n_eff = 1` cannot resolve
anything — the class of error R13c exists to refuse.

So the outcome is measured over **non-overlapping 6-month calendar blocks**,
and the effective cross-section is **measured, not assumed**, as the design
effect `k / (1 + (k-1)ρ̄)` on a policy-free surrogate (half exposure vs full):

| | ρ̄ | effective cross-section | n_effective | 80%-power MDE |
|---|---|---|---|---|
| terminal log growth | 0.488 | **1.81** of 8 | 74 | **3.23pp/block = 6.45pp/yr** |
| max drawdown | 0.691 | 1.37 of 8 | 56 | **1.85pp/block** |
| worst day | 0.753 | 1.27 of 8 | 52 | 0.63pp/block |
| downside semideviation | 0.797 | 1.22 of 8 | 50 | 0.10pp/block |

**This is the finding, and it is registered before the test rather than
discovered after it:**

> Resolving the programme's own +3%/yr execution standard on terminal log
> growth needs **172 years**. This slice holds 20.

And widening the cross-section does not rescue it: the effective count is
bounded by `1/ρ̄ ≈ 2` however many equity ETFs are added. **Any objective
containing a terminal-return term is unresolvable on 20 years of equity data at
the standard this programme has set itself.** Only pure-risk outcomes are
resolvable — and they are resolvable by a wide margin, because their dispersion
falls far faster than their correlation rises.

## Hypothesis

**H0:** the frozen vote policy does not reduce max drawdown. Its de-risking
windows are not concentrated where drawdowns are made, so the drawdown of the
policy path is not below buy-and-hold's by an economically relevant margin.

**H1:** it does. N12 measured a **−6.87pp** matched-volatility drawdown
difference for a vol-targeting policy; a precursor-triggered policy that marks
tail states should show the same sign.

**Honest prior, stated before the number exists.** I expect a **real drawdown
reduction and no detectable utility gain**, because a policy that is out of the
market ~20% of the time mechanically reduces drawdown whether or not its timing
carries information. That is exactly why the placebo below is mandatory and why
a bare drawdown reduction is **not** evidence of skill.

## Primary metric — the ONE deciding number

**Mean difference in max drawdown per 6-month block, policy minus buy-and-hold,
at δ = 0.0**, with a 90% block bootstrap interval over calendar blocks across
the whole cross-section.

**Against a matched-exposure placebo, not against zero.** For each security a
placebo policy is drawn that de-risks the *same number of days* in randomly
chosen windows of the same length, 200 draws. The deciding quantity is

```
Δ = drawdown(policy) − drawdown(buy-hold)   compared to the placebo distribution
```

Beating zero says only that being out of the market lowers drawdown. Beating
the placebo says the *timing* did it. §37: a new instrument's first positive is
the one that looks like it working.

## Decision rule, committed before the number exists

| condition | verdict |
|---|---|
| Δ below the placebo 5th percentile **and** \|Δ\| ≥ 3.0pp | `POLICY_REDUCES_DRAWDOWN` — the timing carries tail information; earns a sizing trial, nothing more |
| Δ below the placebo 5th percentile, \|Δ\| < 3.0pp | `DETECTABLE_BUT_IMMATERIAL` |
| Δ inside the placebo distribution | `NO_TIMING_INFORMATION` — the reduction, if any, is the exposure and not the signal |
| Δ above the placebo 95th percentile | `POLICY_WORSENS_DRAWDOWN` |

The 3.0pp floor is set from N12's measured −6.87pp, halved — an effect less
than half of what a *mechanical* vol-target achieved is not worth a precursor
library.

## Reported, never deciding — and registered as UNPOWERED in advance

Terminal log growth, the four declared personalities, per-security paths, δ =
0.5, average exposure, turnover cost. **Their MDE is 6.45pp/yr against an
execution standard of 3pp/yr, so they cannot produce a verdict and none will be
read off them.** They are reported because a policy's cost belongs next to its
benefit, not because this design can adjudicate them. Any sentence of the form
"the policy earned/lost X" is out of scope for this trial by registration.

## Power declaration (R13/R13b/R13c)

Measured by `--power-only`, which computes dispersion from a **policy-free**
surrogate and never calls the policy — so the hypothesis cannot inform its own
power.

```
declared_effect_size      = 3.0 pp     (drawdown, per 6-month block)
event_frequency_per_year  = 2.0        (non-overlapping 6-month blocks)
outcome_dispersion        = 4.936 pp   (sd of the block drawdown difference)
outcome_horizon_days      = 126
corpus_years              = 20
dependence_unit           = one non-overlapping 6-month calendar block spanning
                            the ENTIRE cross-section; the eight securities
                            contribute at most one observation between them
cross_sectional_n         = 1
cluster_size              = 1
```

`cross_sectional_n = 1` is the **conservative** declaration and is deliberately
below the measured design effect of 1.37. The cross-section does add something;
declaring that it adds nothing costs power and cannot flatter the result.

## Frozen parameters — not tunable mid-trial

```
FRESH_SLICE   XRT XHB KRE XOP ITB SMH IBB IGV
EVAL          2006-07-01 .. 2026-08-15
RULES         sha256 8093cf73...  (598, train-selected, hash-checked at run)
THETA         0.1371              (train-calibrated vote threshold)
HORIZON       20 days de-risking after a fire; overlapping fires EXTEND
DELTA         0.0 primary, 0.5 reported
COST          0.0010 per unit of exposure change
BLOCK         6 months
SEED          20260816
```

## What this trial may NOT do

- It may **not** report a utility or return verdict. Registered unpowered above.
- It may **not** treat a drawdown reduction that fails the placebo as evidence
  of anything except reduced exposure.
- It may **not** re-select, re-tune or re-threshold anything after the run.
- It may **not** claim deployment. A pass buys a sizing trial (G6), which is a
  different gate with a different slice.
- It may **not** be re-run on this slice. One CONFIRM claim, recorded.
