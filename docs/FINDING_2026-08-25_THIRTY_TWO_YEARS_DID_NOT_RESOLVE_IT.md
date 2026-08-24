# FINDING 2026-08-25 — 32 years did not resolve it, and no sample will

## The one-line result

Tripling the sample halved the standard error exactly as `sqrt(T)` predicts.
**The effect estimate shrank at the same time, so the target moved further
away:** from 36 years needed to **61**, which CRSP cannot supply.

| | 2013-2024 (12y) | 1993-2024 (32y) |
|---|---|---|
| tracking error | 35.7%/yr | 34.4%/yr |
| SE of mean excess | 10.81% | **6.19%** |
| observed excess | 16.64%/yr | **12.36%/yr** |
| implied `t` | 1.54 | **2.00** |
| MDE at 80% power | 30.3%/yr | **17.3%/yr** |
| **years needed** | 36 | **60.7** |
| **sample can resolve it** | No | **No** |

Bootstrap 95% CI on the excess after 32 years, five rebalance phases and every
guardrail: **[-0.12%, +25.13%]**. It still contains zero, by a hair.

Receipt: `backend/data/optimus/portfolio_farm/farm_widened_1993_2024.json`.
Policy: `mom_12_1 / hold 2d / k=10 / inverse_vol / u500 / 12bp`, the best rule
on the 32-year holding grid by median terminal wealth.

## The decade split, which is the part that matters

    window        median$     market$   x market
    1993-2002      89,718      20,464      4.38
    2003-2012       6,813      15,839      0.43
    2013-2022      52,593      25,207      2.09

**Over 2003-2012 the leading candidate turned $10,000 into $6,813 — a 32% loss
— while buy-and-hold made 58%.** That decade contains the 2009 momentum crash,
the most famous failure of momentum strategies on record, and the 12-year
sample contained none of it.

So "3.97x the market over 32 years" is not an edge with variance around it. It
is a regime bet that has already had one decade in which it destroyed a third
of the capital. The 2026-08-24 verdict — *must not be seeded as a forward book*
— was right, and is now right for a demonstrated reason rather than a
suspected one.

## Why this could not have been learned any other way

No amount of bootstrapping, phase-averaging or multiplicity control on
2013-2024 could reveal a decade that was not in the sample. The stationary
block bootstrap resamples the path that happened; White's Reality Check prices
the search. Neither can manufacture 2003-2012.

That is the whole case for having spent the night on data rather than on
another mechanism, and it is the concrete form of the standing rule: **a farm
number read off ONE window is a regime, not an edge.**

## What "36 years" actually was

The 2026-08-24 power check said 36 years were needed. That figure was computed
as `(z * te / observed_excess)^2` from a 12-year excess estimate of 16.64%/yr —
and the 12-year estimate was inflated, because the window happened to exclude
momentum's worst decade. With 32 years the excess reads 12.36%/yr and the
requirement is 61 years.

**A "years needed" figure computed from a biased effect estimate is itself
biased, in the same direction.** It is a lower bound dressed as a target. The
lesson generalises past this candidate: whenever `years_needed` is quoted,
quote the excess it was computed from and say which regimes the window omits.

## The constructive half: the lever is tracking error, not history

`MDE = z * te / sqrt(T)`. Tracking error barely moved between the two windows —
35.7% to 34.4% — because **it is a property of the portfolio construction, not
of the sample.** Ten names out of five hundred is what makes it 34%.

`sqrt(T)` is the expensive lever and it is nearly exhausted: the replayable
window starts in 1993 because CRSP has no open prices before mid-1992, so there
are no more years to buy.

`te` is the cheap lever and it has never been pulled. Measured 2013-2024 at
h=5, `mom_12_1`:

    k=10   te 33.6%      k=30   te 21.0%
    k=20   te 25.4%      k=50   te 16.4%

At k=50 over 32 years the implied MDE is roughly **8%/yr** rather than 17%.

**But the 2013-2024 breadth diagnostic says the excess falls faster than the
tracking error does** (`t` peaks at k=10 and decays, slope -0.40 over
k=10..50), which is the opposite of what Grinold's law predicts for a real
cross-sectional signal. If that still holds over 32 years, breadth does not
rescue resolvability either — and the honest conclusion is that price-only
momentum at any breadth is not demonstrable on the data that exists.

That comparison is the single most informative thing left to run, and it is
queued.

## Status of the candidate

`RETIRED_FROM_CURRENT_SEARCH` as a `CAPITAL_CANDIDATE`. Not
`MECHANISM_REJECTED`: this is one implementation — 12-1 momentum, ten names,
inverse-vol, weekly-ish rebalance — and the finding is about what a 34%
tracking error can be shown to do, not about whether momentum exists.

It remains a legitimate `PRODUCT_EXPERIMENT` object. Nothing here forbids
paper-trading it under a frozen contract; what it forbids is calling it alpha
or pointing real capital at it.
