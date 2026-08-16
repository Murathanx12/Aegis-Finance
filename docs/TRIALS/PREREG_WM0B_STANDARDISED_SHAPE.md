# PREREG — WM0B: with scale handed to it for free, does the model earn its keep on SHAPE?

**Registered:** 2026-08-16, after WM0 and before WM0B fits anything.

**Resurrects:** WM0 — new instrument: the model is fitted in **standardised
space**, `z = y / (rv20 · √(H/252))`, and its predicted quantiles are rescaled
by today's volatility. One change. Everything else — universe, features, folds,
embargo, hyperparameters, seed, comparator, decision rule — is byte-identical.

**This counts as a second trial** against the cumulative count, as WM0's prereg
required. It is not a retune of WM0.

## What WM0 measured, and why this follows from it rather than from hope

WM0 was **6.17% worse** than `scaled_empirical` (90% CI [+0.055, +0.089], MDE
2.48% — a powered negative), and worse than climatology too. Two diagnostics
point at the same cause:

- **Calibration.** `P(y ≤ q_05) = 0.087` against a target of 0.05, and
  `P(y ≤ q_95) = 0.900` against 0.95. The predicted distribution is too narrow
  at both ends.
- **The fold pattern.** WM0 wins 4 of 21 folds — 2011, 2014, 2019, 2024, all
  calm — and loses worst in **2020 (1.278×)** and **2008 (1.139×)**. It fails
  precisely in the crisis years.

The mechanism: a quantile regressor fitted in **level** space must re-derive the
scale of the distribution from features, and cannot extrapolate to volatility
levels it never saw in training. `scaled_empirical` is handed scale by today's
`rv20` and √time, so it extrapolates into 2008 and 2020 without having seen
them.

This is also, precisely, the roadmap's standing ruling made testable:
**realised volatility is commoditised, so take the cheap baseline for scale and
make the learned model earn its keep on tail and shape.** WM0 did not do that —
it made the model compete on scale, which is the part already solved. WM0B does.

## Hypothesis

**H0:** conditioning shape on state adds nothing once scale is given. WM0B's
pinball loss is not below `scaled_empirical`'s — the standardised residual
distribution is effectively state-independent, and `scaled_empirical`'s single
pooled residual distribution is already the right answer.

**H1:** the standardised distribution's **shape** depends on state — fatter or
more skewed after drawdowns, at inverted vol ratios, at high VIX — and a model
given scale for free can capture it.

**Honest prior, registered before fitting.** I expect WM0B to **beat WM0
substantially**, because the level-space handicap is large and removing it is
most of the 6.17%. Whether it beats `scaled_empirical` I genuinely do not know,
and I put it near even. Beating WM0 is **not** the claim and will not be
reported as success: `scaled_empirical` remains the comparator of record, and
improving on one's own failed variant is the flattering comparison this
programme has been burned by (§37).

I am also registering the failure mode I would find most likely if H1 is false:
the standardised residual distribution is dominated by a fat tail that is
roughly constant across states, so there is little conditional shape left to
learn once vol is removed.

## Primary metric — unchanged from WM0, deliberately

**Mean pinball loss over the seven quantiles, pooled over all out-of-sample
folds, as a paired difference against `scaled_empirical`**, 90% moving-block
bootstrap interval, 40-day blocks.

Keeping the metric identical is what makes WM0 and WM0B comparable. Changing it
alongside the model would make the two runs uninterpretable against each other,
which is the standard way a "v2 improvement" is manufactured.

## Decision rule, committed before the number exists

Let `[lo, hi]` be the 90% interval on
`mean_pinball(WM0B) − mean_pinball(scaled_empirical)`.

| condition | verdict |
|---|---|
| `hi < 0` **and** improvement ≥ 2% of baseline loss | `BEATS_SCALED_EMPIRICAL` — conditional shape is real; G5 has a working v0 |
| `hi < 0` but improvement < 2% | `DETECTABLE_BUT_IMMATERIAL` — real, and too small to move an exposure |
| interval spans 0 | `NOT_DETECTABLE_IN_SCOPE` — spend on STATE, not architecture |
| `lo > 0` | `WORSE_THAN_SCALED_EMPIRICAL` — take the cheap baseline as the world model and say so |

The 2% economic floor is unchanged and is set from what a vol-target's exposure
consumes, not from what the sample can see.

**Secondary, reported and never deciding:** the paired difference against WM0,
per-quantile loss, tail loss (τ ≤ 0.10), PIT calibration, per-fold losses, and
specifically the 2008 and 2020 folds — the ones that produced the diagnosis.

## Power

Unchanged from WM0 and already measured on these exact folds: 92,988
out-of-sample observations, effective n **2,325** after 40-day blocking,
smallest resolvable loss difference **0.00683 pp = 0.59% of baseline loss**
against a declared floor of 2%.

```
declared_effect_size      = 0.0231 pp
event_frequency_per_year  = 12.6
outcome_dispersion        = 0.11746 pp
outcome_horizon_days      = 20
corpus_years              = 21
```

## Frozen — identical to WM0 except the target space

```
UNIVERSE / FEATURES / QUANTILES / FOLDS / EMBARGO / MODEL / SEED
                  all unchanged from PREREG_WM0_WORLD_MODEL_V0.md
TARGET            z = y / (rv20 * sqrt(20/252))     <- THE ONLY CHANGE
PREDICTION        model quantiles of z, multiplied by today's scale,
                  then re-sorted for monotonicity
```

`rv20` remains in the feature set, unchanged. It is not removed, because the
model may legitimately use the volatility *level* to condition shape (fat tails
are not uniform across vol regimes) — and removing a frozen feature would be a
second change.

## What this trial may NOT do

- It may **not** report beating WM0 as success. The comparator of record is
  `scaled_empirical`.
- It may **not** be followed by a WM0C in this session if it fails. Two
  registered attempts is the budget; a third without a new *reason* derived
  from measurement is fishing.
- It may **not** claim confirmation — the slice is EXPLORE and overlaps four
  prior trials.
- It may **not** be described as a sizing policy (G6 is a separate gate).
