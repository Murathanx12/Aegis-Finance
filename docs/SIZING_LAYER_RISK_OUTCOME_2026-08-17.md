# The sizing layer: risk is measurable where return is not — and it still needs more than six years

**2026-08-17.** M4-SELECTOR refused to spend the reserved window because every
effect in the measured library needs fourteen years or more to detect. §59 named
two exits from that: change the outcome to risk, or change the dependence unit.
This tests the first one on our own data, before committing the roadmap to it.

**Result: the relative claim survives and the absolute one does not.** Risk is
dramatically easier to measure than return here — but not easy enough for the
window we hold.

---

## What was measured

Volatility targeting on SPY total return, daily, 2006-01-01 … 2019-12-31 (the
same EXPLORE window as the library, so no new slice is consumed). Every
parameter declared before running: 60-day realised vol, 15% annual target,
monthly rebalance with the weight set from data through the last day of the
prior month, 10bp per unit of notional traded.

```
                        buy&hold    cap 1.0    cap 1.5
  annual return           9.22%      9.39%     11.39%
  annual volatility      18.78%     13.83%     16.27%
  max drawdown          -55.19%    -31.46%    -33.06%
  sharpe                   0.56       0.72       0.74
```

At cap 1.0 — long only, no leverage, which is what could actually be run — the
worst drawdown of the period is **cut from −55% to −31% with the annual return
unchanged to within 17 basis points.**

## Each difference against its own MDE

```
  outcome             cap      delta        SE       MDE   MDE@74mo   verdict
  annual volatility   1.0    -0.0495    0.0124    0.0346     0.0521   not resolvable on the reserved window
  max drawdown        1.0    +0.2373    0.0607    0.1701     0.2561   rests on 1 crisis episode
  annual return       1.0    +0.0017    0.0185    0.0519     0.0782   below its MDE even here
  annual volatility   1.5    -0.0251    0.0140    0.0394     0.0593   below its MDE even here
  max drawdown        1.5    +0.2212    0.0736    0.2061     0.3103   rests on 1 crisis episode
  annual return       1.5    +0.0217    0.0213    0.0598     0.0901   below its MDE even here
```

**The relative claim holds emphatically.** The volatility reduction at cap 1.0
is −4.95pp against an MDE of 3.46pp — comfortably detectable. The return change
is +0.17pp against an MDE of 5.19pp — a ratio of 0.03, meaning the return
outcome is roughly **30× further from resolution** than the risk outcome on the
identical data. That is §59's point, reproduced rather than repeated.

**The absolute claim does not.** §59 records "max drawdown ~4 yrs". Here the
volatility effect needs the full fourteen years: at 74 months the MDE rises to
5.21pp against a −4.95pp effect, so the reserved window falls **just** short —
by about 5%. The two are not in contradiction (§59's figure came from a
different slice and a different effect size), but the number that matters for
*this* rule on *this* asset is fourteen years, not four, and the roadmap should
carry the measured one.

## The drawdown number is one observation

**There is exactly one drawdown reaching −20% in 2006–2019** (July 2008 →
August 2012, trough −55.2%). So the +23.7pp improvement is a single event.

The block bootstrap returns a tidy SE of 6.07pp for it, and that SE is
answering the wrong question: every resample containing the crash inherits the
*same* crash, so it measures the sampling variation of a statistic rather than
variation across crises — and only the second is what a drawdown claim is about.
§39: *a window is only a window if something measured fits in it.*

The script now reports the episode count beside the difference and labels the SE
as understating it, rather than printing the more flattering half alone. The
honest reading of the drawdown row is **n = 1**, and the volatility row — 3,524
days, one estimate per day — is the one carrying real weight.

## Pricing the ceiling instead of stopping at it

§59's ceiling is *"risk reduced; return effect not established"*. The way past a
ceiling is to price it:

```
  cap 1.0, lambda 1.0:  variance falls 0.0161  ->  worth up to -0.81%/yr
  cap 1.0, lambda 3.0:  variance falls 0.0161  ->  worth up to -2.42%/yr
                        measured return change:  +0.17%/yr
```

A mean-variance investor at λ=1 would accept giving up 0.81%/yr of return for
this variance reduction. The measured return change is **+0.17%/yr** — it did
not cost anything measurable. So the trade is favourable across the whole
plausible λ range, and that statement is built from two measured quantities.

λ prices a trade-off between things that were measured; it cannot supply a
missing return estimate, and it is not being asked to here.

## What this means for the roadmap

1. **The sizing layer is the part of this system closest to certifiable**, and
   it is the part that has had the least attention. Return selection is 30×
   further from resolution on identical data.
2. **It is still not certifiable on the reserved window** — 74 months misses the
   volatility MDE by ~5%. Two ways to close that gap, both honest:
   * **more assets.** §58: the dependence unit is measurable. A vol-targeting
     rule applied across k weakly-correlated sleeves buys effective blocks the
     way calendar cannot.
   * **a lower-variance estimator of the outcome.** Realised volatility measured
     daily rather than the drawdown extreme is already the better-behaved half;
     pushing further in that direction costs nothing in realism.
3. **Do not spend a confirmation slot on a drawdown claim** from a window
   holding one crisis, whatever the bootstrap says.

## Status

* EXPLORE only, on the already-claimed selection window. Nothing reserved,
  nothing consumed, no confirmation run.
* The reserved calendar 2020-06-01 … 2026-07-17 carries exactly two declared
  outcome families (Order 8, k_eff 2.00, α 0.025 each). A volatility outcome
  would be a **third**, which `alpha_for` refuses by design — adding it means a
  fresh declaration at k_eff 3 and α 0.0167 each, and that is a decision to
  take deliberately rather than by running a script.
* `data/library/sizing_layer_risk.json` carries the declarations, the
  differences, the MDEs and the episode count.
