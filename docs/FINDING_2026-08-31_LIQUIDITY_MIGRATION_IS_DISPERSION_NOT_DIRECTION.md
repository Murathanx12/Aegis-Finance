# FINDING — 2026-08-31 — a stock changing liquidity band is IN PLAY, not going up

**Receipt:** `backend/data/optimus/wrds/liquidity_migration.json`
**Code:** `scripts/liquidity_migration.py`
**Licence:** PRODUCT_EXPERIMENT — cross-sectional, controlled, gross of costs.
**Status:** Murat's hypothesis **partly confirmed and importantly redirected.**

---

## The hypothesis, in his words

> *"seeing how these bands are changing per stock might be a great showcase of
> growth and potential too. seeing how bid and ask change is also"*

A name that traded $500k/day and now trades $5m/day is being discovered — more
eyes, more capital able to enter, a collapsing spread. Is that visible before
the re-rating finishes?

Intuition generates, data adjudicates. CRSP 2013-2024, **520,142 name-months →
368,558 usable observations**, band ladder identical to the TAQ spread study so
every rung's cost is already known.

## The answer: the mean says no, the tail says yes, the control says "in play"

Forward 12-month return, gross:

| group | n | mean | median | >+50% | **>+100%** | **<−50%** | p90 |
|---|---|---|---|---|---|---|---|
| climbed ≥2 bands | 9,841 | +6.69% | **−15.31%** | 17.5% | **8.7%** | **24.6%** | +89.2% |
| climbed ≥1 band | 63,584 | +12.62% | +1.16% | 16.5% | 6.7% | 11.9% | +75.5% |
| **flat** | 253,055 | **+13.03%** | **+5.45%** | 13.8% | 4.5% | 6.1% | +62.3% |
| fell ≥1 band | 51,919 | +14.06% | −1.89% | 17.6% | 7.8% | 13.2% | +82.9% |

Controlled for the trailing 12-month return (within-month quintiles), which is
the test that separates this from momentum — and with the `fell` group given the
same control, which is what corrected this document:

| trailing-return quintile | climbed | flat | fell | climb−flat | fell−flat | >+100% cl/fl/fe |
|---|---|---|---|---|---|---|
| q0 (worst) | +21.03% | +20.92% | +20.02% | +0.11pp | −0.90pp | 12.1 / 10.0 / 11.5% |
| q1 | +13.43% | +12.83% | +8.34% | +0.60pp | **−4.49pp** | 6.4 / 4.3 / 4.9% |
| q2 | +12.88% | +11.48% | +9.01% | **+1.40pp** | −2.47pp | 5.0 / 2.8 / 3.7% |
| q3 | +11.98% | +10.88% | +7.33% | +1.10pp | −3.55pp | 4.5 / 2.7 / 3.5% |
| q4 (best) | +10.81% | +10.31% | +10.84% | +0.50pp | +0.53pp | 6.9 / 3.9 / 5.9% |

### 1. As a directional signal it fails

Climbers **underperform** flat names on the mean (+12.62% vs +13.03%) and badly
on the median (+1.16% vs +5.45%). Two-band climbers have a **−15.31% median**.
Controlled, the edge is +0.1 to +1.4pp/yr — consistently positive in all five
quintiles, which is worth noting, but far too small to survive the 149 bps
round-trip cost of the band climbers usually start in.

### 2. As a DISPERSION signal it is strong

Climbers reach **+100% in 12 months 1.5× as often** as flat names (6.7% vs
4.5%); two-band climbers **1.9× as often** (8.7%). Their p90 is +89.2% against
+62.3%.

**And they lose >50% four times as often** (24.6% vs 6.1%). The distribution is
fatter in *both* directions. This is the mean/median divergence the first pass
surfaced and the reason a mean was the wrong statistic for the question.

### 3. The control, applied to the fallers too — and it corrected this document

The first version of this finding said climbers and fallers "look almost
identical", on the strength of the UNCONTROLLED table where fallers had the
highest mean of any group (+14.06%). Giving `fell` the same control the climbers
got shows that was a **composition effect**: fallers cluster in the beaten-down
trailing-return quintile, which is the quintile with the highest forward return
for everyone. It was mean reversion being credited to falling liquidity.

Controlled, the two are **not** symmetric on the mean:

- **climbing is mildly POSITIVE** — +0.11 to +1.40pp, positive in all five
  quintiles;
- **falling is NEGATIVE** — −0.90 to −4.49pp, negative in four of five.

But on the tail they behave alike: **both climbers and fallers reach +100% more
often than flat names in all five quintiles** (climbers most, fallers second,
flat always last).

So the corrected statement is narrower and more useful than either the
hypothesis or the first draft:

> **A change in liquidity band — either direction — widens the outcome
> distribution: the right tail is fatter than a flat name's in every
> trailing-return quintile. The DIRECTION of the change is a weak directional
> signal on top of that — climbing mildly good, falling clearly bad — but it is
> far too small to trade on its own.**

The dispersion claim survives the control. The "identical" claim did not, and
this is the second time in one study that an uncontrolled table pointed the
wrong way.

## What follows

1. **Do not build a long-only "climbers" book.** It underperforms flat names on
   the median and pays the widest spreads in the market to do it.
2. **This belongs to the OPTIONS book, not a share book.** A widened outcome
   distribution with no directional claim is a straddle/strangle thesis. Under
   the six-account design that is **hack5** — and it is the first evidence-backed
   candidate generator that account has had.
3. **Band change is a feature, not a strategy.** It belongs on `CompanyState` as
   `band`, `band_change_12m` and — from the TAQ study — `expected_round_trip_bps`,
   so downstream models can condition on "is this name in play" and on what it
   costs to touch.
4. **It carries a cost forecast.** A name climbing band 0→2 sees its round trip
   fall from ~149 bps to ~21. Something unbuyable today may be buyable next year;
   that is a different statement from "the edge is not buyable".
5. **The `fell` group is now controlled and is NOT a hidden opportunity.** Its
   headline +14.06% mean was composition, not signal: −0.90 to −4.49pp against
   flat peers once trailing return is held fixed. Falling liquidity is bad for
   the mean and still fat-tailed — a short-side or volatility candidate, never a
   long one.
6. **Never read this family uncontrolled.** Both wrong turns in this study came
   from a table without the trailing-return control: first the climbers looked
   like momentum, then the fallers looked like an edge. The control is not a
   formality here; it reverses the sign.

## Limits

- **Gross of costs.** Deliberately: the holding period is what a follow-up must
  decide, and each band's measured cost is carried in the receipt rather than
  netted at a flat rate.
- **Not risk-adjusted.** A fatter distribution is a higher variance; nothing here
  claims a Sharpe improvement, and the terminal-wealth lesson (concentration is a
  negative-return decision) applies to any book built on this.
- **12-month horizon only** for the tail table. 3m and 6m are in the receipt.
- **Survivorship:** delist-inclusive returns via CRSP, `shrcd 10/11`,
  `exchcd 1/2/3`, price ≥ $1, ≥15 trading days per month.
- **A band is a coarse cut.** A name at $990k/day and one at $1.01m/day sit in
  different bands and are the same stock; the effect is measured on that coarse
  boundary and would look different on a continuous measure.
