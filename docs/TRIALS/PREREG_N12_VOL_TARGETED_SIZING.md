# PREREG — N12: volatility-targeted sizing, as a PRODUCT_EXPERIMENT

**Registered:** 2026-08-16, before any wealth path is computed.

**Label: `PRODUCT_EXPERIMENT`, not an alpha claim.** We are implementing a
well-known technique because our own evidence kept independently pointing at it
— four times, from four unrelated directions — not because we discovered it.

## Why now, and why it is not a research claim

Four convergent findings, none of them designed to be about sizing:

| | finding | what it pointed at |
|---|---|---|
| NIGHT-12 | drawdown 22.9% vs SPY 8.9% at beta 2.15 | exposure, not selection |
| NIGHT-13 | constant half-exposure **beat** the timing ladder | sizing, not timing (3rd time) |
| the de-risking result | the failure was the map from state to *exposure* | sizing |
| N6 | the moment that governs sizing is the predictable one | sizing is the reachable objective |

And order 3 §3 settles the objection that killed this last time: **vol-targeted
sizing does not require beating `rv20`. It requires volatility to be
forecastable at all, by anything, including `rv20` itself.** The free baseline
matching the model is *good news for a product* — the input is cheap, robust and
carries no model risk. It is bad news only for a paper claiming a better
forecaster, and this is not that paper.

## The comparison that would be dishonest, and the one that is not

Volatility targeting lowers average exposure. In a rising market it therefore
loses to buy-and-hold **by being less invested**, and wins on drawdown for the
same trivial reason. Reporting either number alone is a way of choosing the
answer.

So the primary comparison is at **matched ex-post realised volatility**: each
policy is scaled by a single constant so that all policies have the same
realised volatility over the evaluation window, and terminal log-wealth is
compared at that common risk level. The raw (unmatched) table is reported
alongside, never instead.

## Policies (frozen)

1. `buy_hold` — exposure 1.0 always
2. `constant_half` — exposure 0.5 always (NIGHT-13's winner)
3. `vol_target_1x` — exposure `min(target / rv20_trailing, 1.0)` — the honest
   product default, no leverage
4. `vol_target_2x` — the same, capped at 2.0

`target = 15%` annualised, declared here, not tuned. `rv20_trailing` is the
20-day realised vol as of the **previous** close, so no policy sees the day it
is sizing for. Costs: **10bp** per unit of turnover, one way.

## Primary metric

Terminal **log-wealth** at matched realised volatility, with max drawdown, time
under water, expected shortfall and probability of ruin printed beside it —
never a return number on its own (P0.5's objective layer).

Difference tested as a **difference** (§18): a paired moving-block bootstrap
over the daily return series, the same blocks for every policy, so the market's
path cancels and only the policy difference remains. 2,000 resamples, block
length 63 days.

## Decision rule (pre-committed)

| outcome | verdict |
|---|---|
| `vol_target_1x` beats `buy_hold` in matched-vol log-wealth, difference above its own MDE | `PRODUCT_ADOPT_CANDIDATE` — build the sizing head |
| difference below its MDE | `NOT_DETECTABLE_IN_SCOPE` — and **build it anyway if the drawdown/ruin side is materially better**, because a product decision under a declared utility is not the same object as a detectable difference in mean log-wealth |
| `vol_target_1x` materially worse on both | do not build |

The middle row is deliberate and is the honest position for a
`PRODUCT_EXPERIMENT`: the four convergent findings are about *risk*, and a
technique that leaves growth unchanged while cutting drawdown is a product
improvement under every personality the tool offers except the risk-neutral one.

## R13 — resolvability, declared before compute

- event_frequency_per_year: 252
- declared_effect_size: 1pp
- outcome_dispersion: calm
- corpus_years: 27

## Run spec (frozen)

`python -m scripts.n12_vol_targeted_sizing` — SPY, QQQ, IWM, EFA, 1999-01-01 to
2026-08-15, seed 20260816. ONE run.

## Result (filled in AFTER the run — never edited afterwards)

Run 2026-08-16. SPY 6,925 / QQQ 6,880 / IWM 6,572 / EFA 6,257 days, 2,000
paired block resamples at 63 days, 10bp one-way, target 15%.

### At matched ex-post realised volatility (the primary table)

| | CAGR vs buy-hold | max drawdown vs buy-hold |
|---|---|---|
| SPY | 10.08% vs 8.71% | 59.8% vs 55.2% (**worse**) |
| QQQ | **17.14%** vs 10.60% | **69.6%** vs 83.0% |
| IWM | 7.39% vs 8.45% (worse) | **50.2%** vs 58.6% |
| EFA | 7.91% vs 7.25% | **50.7%** vs 61.0% |
| **pooled** | better in **3/4** | better in **3/4**, mean **−6.87pp** |

`vol_target_2x`: drawdown better in **4/4**, mean **−10.54pp**.

### Verdict

**Primary metric: `NOT_DETECTABLE_IN_SCOPE`.** Matched-vol log-wealth
differences run +0.30 (SPY) to +1.54 (QQQ) against MDEs of 0.94 to 1.54. One
27-year path per security is not a sample and the MDEs say so plainly.

**And the pre-committed middle row fires: `PRODUCT_ADOPT_CANDIDATE`.** The
drawdown side is materially better and the ruin side is categorical —
**QQQ buy-and-hold hits the ruin floor (`ruin: True`, −83%) and every
vol-targeted variant does not.** Under every personality the tool offers except
the risk-neutral one, cutting the drawdown by ~7pp at the same realised
volatility, while the growth difference is undetectable, is a product
improvement. That is exactly the case the middle row was written for, before
the numbers existed.

**Build the sizing head on `rv20`. Label it a risk improvement at unchanged
growth, because that is what was measured.**

### The finding nobody was looking for: `constant_half` is buy-and-hold

At matched volatility, `constant_half` is **identical** to `buy_hold` — 0/4 on
both metrics, Δlog exactly 0.0000 with zero variance, ΔMaxDD exactly +0.00pp.
That is not a bug; it is arithmetic. Scaling a constant exposure by a constant
returns the same strategy at a different risk level.

**So NIGHT-13's "constant half-exposure beat the timing ladder" was a statement
about the risk LEVEL, not about the policy.** The programme has repeated "sizing
not timing" three times; this run says what it must mean to be non-trivial:
**state-dependent sizing**, not merely lower sizing. Constant leverage carries
no information and cannot be the thing four findings were pointing at.

### Limitations, disclosed

* **The bootstrapped drawdown difference is not an estimate.** Block resampling
  destroys the path, and max drawdown is a path statistic; the block-resampled
  ΔMaxDD is reported for its dispersion only. The full-sample matched paths are
  the drawdown evidence, and they are one path each.
* `gamma*` on SPY returns the boundary of the search range (15.00) rather than
  an interior crossing — read it as "does not flip in the searched range", not
  as a measurement.
* Four securities that co-move. 3/4 is a pattern, not a p-value, and it is
  labelled that way in the output.
* The target (15%) and the cost (10bp) were declared, not tuned. No sensitivity
  grid was run over them, so nothing here says the result is insensitive to them.

- Receipt: `backend/data/optimus/research_gym/n12_vol_targeted_sizing.json`
- Script: `scripts/n12_vol_targeted_sizing.py`
