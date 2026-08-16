# PREREG — WM0: does a conditional model of the forward-return DISTRIBUTION beat cheap volatility scaling?

**Registered:** 2026-08-16, before any model is fitted. The power declaration
below was produced by `python -m scripts.wm0_train --power-only`, which
estimates the loss-difference dispersion from **baseline against baseline** and
fits nothing — so the model under test cannot inform its own power declaration.

**Gate:** G5 (world model), which stands at zero. This is its first artefact.

**Slice:** eighteen liquid ETFs, 1999-01-01 → 2026-08-15, claimed as
**EXPLORE** in the slice register (`4c16fdf`). It overlaps data N4/N4B/N9/N9B
have read. Exploration may revisit data freely — **this trial may therefore
never be reported as confirmation of anything**, and the register records that.

## Why this, and why not a return forecaster

N6 measured forward-return **sign** at AUC 0.497–0.509 — not detectable — while
`|return|` IC ran 0.17–0.29 and volatility IC 0.53–0.62 on the *same* features
and the *same* folds. The direction of the next move is not in this state
vector. The **shape** of the next move's distribution may be.

Every gate above G5 is waiting on `P(outcome | state)` rather than
`E[outcome | state]`: a sizing policy integrates a utility against a
distribution, and cannot be trained against a point forecast. So v0 predicts
seven quantiles of the H-day forward return and is scored with a strictly
proper scoring rule.

## The comparator of record — chosen to be hard, not flattering

The roadmap's standing ruling is that realised volatility is commoditised **for
ranking**, and that a learned model must earn its keep on tail, drawdown and
co-movement. The comparator is therefore **`scaled_empirical`**: training-window
standardised residual quantiles rescaled by today's `rv20`. Fat-tailed,
conditionally scaled, and free.

`climatology` and `gaussian_vol` are reported as context and are **not** the
comparison of record. Beating climatology would be the flattering comparison —
it knows nothing about today — and a result stated against it would be the
programme's §37 failure mode: a new instrument's first positive being the one
that looks like it working.

**A model that cannot beat `scaled_empirical` has learned nothing that
volatility scaling did not already contain.** That is an acceptable v0 outcome
and is pre-committed as a publishable result, not a failure to be re-run with a
different architecture.

## Hypothesis

**H0:** the state vector carries no distributional information beyond today's
realised volatility. WM0's pinball loss is not below `scaled_empirical`'s.

**H1:** it does, and — per the standing ruling — the gain is concentrated in
the **tail quantiles** (τ ≤ 0.10) rather than spread evenly.

**Honest prior, stated before fitting.** I expect a **small positive** overall
improvement, on the order of 1–3%, driven mostly by the model learning the
vol-ratio and drawdown states rather than by anything novel; and I expect the
per-quantile breakdown to show **more** improvement in the tails than the
middle. I also consider it genuinely possible that the result is a null against
`scaled_empirical`, because square-root-of-time vol scaling with fat-tailed
empirical residuals is a strong model and the features here are all functions
of past returns and VIX. I am registering both expectations now.

## Primary metric — the ONE deciding number

**Mean pinball loss over the seven quantiles, pooled over all out-of-sample
folds, as a paired difference against `scaled_empirical`**, with a
moving-block bootstrap 90% interval (40-day blocks).

Reported, never deciding: per-quantile loss, tail-only loss (τ ≤ 0.10), PIT
calibration for every model, per-fold losses, and the comparisons against
`climatology` and `gaussian_vol`.

## Decision rule, committed before the number exists

Let `[lo, hi]` be the 90% bootstrap interval on
`mean_pinball(WM0) − mean_pinball(scaled_empirical)` (negative = WM0 better).

| condition | verdict |
|---|---|
| `hi < 0` | `BEATS_SCALED_EMPIRICAL` — G5 has a working v0; proceed to the expectation layer |
| interval spans 0 | `NOT_DETECTABLE_IN_SCOPE` — report the MDE, spend the next dollar on STATE (options, cross-section, macro), not on architecture |
| `lo > 0` | `WORSE_THAN_SCALED_EMPIRICAL` — the learned model is actively worse; take the cheap baseline as the world model and say so |

**The economic floor.** An improvement is called *meaningful* only at **≥2% of
baseline loss**. Below that, the quantile levels a vol-target consumes do not
move enough to change an exposure, so a statistically detectable but sub-2%
gain is reported as `DETECTABLE_BUT_IMMATERIAL`. This threshold is set from
what the downstream policy consumes, not from what the sample can see.

## Power declaration (R13 / R13b)

```
declared_effect_size      = 0.0231 pp   (2% of the 1.15492pp baseline loss —
                                         the economic floor above)
event_frequency_per_year  = 12.6        (independent 20-day windows per year)
outcome_dispersion        = 0.11746 pp  (sd of the PAIRED loss difference,
                                         measured baseline-vs-baseline)
outcome_horizon_days      = 20
corpus_years              = 21
```

Measured resolution, from the folds themselves: 92,988 out-of-sample
observations, effective n **2,325** after 40-day blocking (R13b — the raw count
is 40× the independent one, which is the error N20 was passed on), giving a
**smallest resolvable loss difference of 0.00683 pp = 0.59% of baseline loss**.
The declared 2% floor sits comfortably above it, so **this design can resolve
its own claim** and a null will be informative rather than empty.

## Frozen parameters — not tunable mid-trial

```
UNIVERSE          18 ETFs (SPY QQQ IWM XLF XLE XLK XLV XLI XLP XLU XLB XLY
                  DIA TLT GLD EFA EEM IYR)
HORIZON           20 trading days
QUANTILES         0.05 0.10 0.25 0.50 0.75 0.90 0.95
FEATURES          12, all functions of lagged price/VIX; every one shifted
FIRST_TEST_YEAR   2006
FOLDS             expanding-window annual refits
EMBARGO           40 days (2 x horizon) at every train/test boundary
MODEL             LightGBM quantile, 300 trees, lr 0.05, 31 leaves,
                  min_child_samples 200
SEED              20260816
```

**No security-identity feature**, deliberately: the model must generalise
across securities, which keeps a transfer test available later.

**The embargo is not cosmetic.** A 20-day forward return uses prices to t+20,
so training rows within the horizon of the test start have outcomes overlapping
the test period. Without the purge the model is scored partly on data it was
fitted on.

## What this trial may NOT do

- It may **not** claim confirmation of anything — its slice is registered
  EXPLORE and overlaps data four prior trials have read.
- It may **not** be reported as a return forecaster, an alpha signal, or
  evidence about direction. It predicts dispersion and shape; N6 already showed
  sign is not detectable here.
- It may **not** be tuned after seeing the test folds. One configuration, frozen
  above, one run. A second configuration is a second trial and counts against
  the cumulative trial count.
- It may **not** be described as a sizing policy. It produces the distribution a
  policy would consume and stops there; G6 is a separate gate.

## Contamination clause

If any security's history fails to download or is materially short, it is
dropped and **named in the output** — a silently smaller universe would change
the pooled result without changing any reported parameter.
