# M4-SELECTOR: the window is not spent, and that is the result

**2026-08-17.** The selector was the next routed step after the library. It ran,
it selected, and then it asked the question N9 never got asked — *can the
reserved window actually resolve this?* — and the answer was no.

**Ruling: DO NOT SPEND. The confirmation window stays reserved.**

---

## The N9 sequence, caught two steps earlier

N9 selected on a calendar, confirmed on the same calendar with different
securities, and produced a 1.271 that had to be withdrawn when the split at the
selection boundary showed **1.464 overlapping against 0.765 disjoint**. The
register had the wrong axis; the confirmation was never clean.

This time the order was inverted before any number existed:

1. 2006–2019 registered **EXPLORE** (`slc_c3246e5093c41c25`) *before the first
   return was computed*, because if we later choose what to deploy from those
   numbers, that window selected them.
2. Confirmation reserved **disjoint** on 2020-06-01 … 2026-07-17, budget 5,
   FWER now **0.025** after Order 8's calendar allocation (k_eff 2.00, shared
   with IV-ORACLE-GAP-1).
3. **And then this step**, which is new: before spending a slot, ask whether
   the reserved window has the power to resolve what the selection produced.

## The rule, frozen before it was applied

| clause | requirement |
|---|---|
| 1 | survives BH-FDR at q=0.10 over the 206 tests run |
| 2 | net annual > 0 inside the **liquid** dollar-volume tercile (§62 — an effect that is not reachable is not a strategy) |
| 3 | \|net annual\| ≥ its own 80%-power MDE in that tercile, tested on **net**, because net is the claim |
| 4 | break-even ≥ 3× the assumed 10bp/crossing, so the choice does not hinge on the cost model being right |
| 5 | sign agrees with the publication — an inverted sign is a different hypothesis, not this one |

## What it selected

**One of eleven.**

```
  ShareIss5Y     liquid net +8.64%/yr   MDE 8.54%   break-even 195bp/crossing
```

The ten rejections, in the selector's own words:

```
  CPVolSpread        below its own MDE in liquid; break-even 27.4bp < 3x cost
  SmileSlope         below its own MDE in liquid
  PriceDelayRsq      not positive in liquid; SIGN INVERTED vs publication
  std_turn           not positive in liquid; below its own MDE
  MomSeason16YrPlus  below its own MDE in liquid; break-even 11.7bp < 3x cost
  VolumeTrend        below its own MDE in liquid
  OptionVolume1      below its own MDE in liquid
  Tax                below its own MDE in liquid
  ShareIss1Y         below its own MDE in liquid
  dCPVolSpread       not positive in liquid; break-even 12.7bp < 3x cost
```

Nine of ten fall to clause 3. The library's survivors are overwhelmingly things
that are not detectable *net* where they can be traded.

## Then the question that decided it

```
  reserved   2020-06-01..2026-07-17                 = 74 months
  PIT-clean data on hand today (CRSP ends 2024-12)  = 55 months

  candidate       effect     MDE@74m    MDE@55m   verdict
  ShareIss5Y      +8.64%     12.84%     14.89%    the window cannot resolve this
```

The standard error scales as 1/√months, so an effect that *barely* cleared its
MDE over 167 months is **1.5× below** it over 74. A confirmation with that
property returns "not established" whatever the world does — and afterwards the
window is gone **and** nothing was learned. That is strictly worse than not
running it.

Nothing was consumed by asking. The power computation uses the selection
window's standard error and a **count of months on a calendar**; a month count
is not an outcome.

## What changes as a result

**The requirement moves forward.** A candidate must clear the **forward** MDE —
the one computed on the window that will judge it — not the backward one it was
selected under. Written as a rule so it binds the next batch too:

> A confirmation slot may only be reserved for a candidate whose selected
> effect exceeds the MDE of the confirmation window at its actual length. The
> MDE is computed and recorded at reservation time, not at decision time.

This is §19 run **forwards**. §19 says an arm below its own MDE is not
detectable and never a kill; as a budgeting rule that means a test which cannot
resolve its own hypothesis should not be started.

## The larger thing this exposes

Every effect in the measured library is of a magnitude that needs **fourteen
years or more** to detect at 80% power on this universe. The reserved six-year
forward window therefore cannot confirm *any* of them — not just this one.

So a six-year forward confirmation is **not a viable certification route for
cross-sectional return effects of this size**, and no amount of patience fixes
it before roughly 2034. §59 said the same thing about a market-level return
claim (≈95 years for +3%/yr); this is the cross-sectional version, and it points
at the same two exits:

* **Change the outcome.** Risk resolves in about 4 years where return needs 95
  (§59). A sizing or risk claim is confirmable on the window we hold.
* **Change the dependence unit.** §58: `k/(1+(k−1)ρ̄)` — residual cross-sectional
  ρ̄ of 0.05–0.15 gives roughly 10× the effective sample. More names and foreign
  markets buy effective date blocks in a way more calendar cannot.

Neither is a workaround. They are the two directions in which the arithmetic
actually moves.

## Status

* Nothing claimed on the confirmation window. Budget untouched at 0/5.
* The selection window's EXPLORE claim was already recorded before the first
  return; this document adds no new consumption.
* `data/library/m4_selector_prereg.json` carries the rule, the selection, the
  rejections with reasons, and the power table.
