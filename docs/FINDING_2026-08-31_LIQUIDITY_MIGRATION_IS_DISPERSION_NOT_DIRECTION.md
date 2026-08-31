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
the test that separates this from momentum:

| trailing-return quintile | climbed | flat | spread |
|---|---|---|---|
| q0 (worst) | +21.03% | +20.92% | +0.11pp |
| q1 | +13.43% | +12.83% | +0.60pp |
| q2 | +12.88% | +11.48% | **+1.40pp** |
| q3 | +11.98% | +10.88% | +1.10pp |
| q4 (best) | +10.81% | +10.31% | +0.50pp |

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

### 3. The control that redirects the whole idea

**Names that FELL a band look almost identical to names that CLIMBED one:**
>+100% at 7.8% vs 6.7%, <−50% at 13.2% vs 11.9%, p90 +82.9% vs +75.5% — and
falling names have the *highest* mean of any group.

So the signal is not "climbing means growth." It is:

> **A change in liquidity band — in either direction — marks a name whose
> outcome distribution has widened. The stock is in play. It does not say which
> way.**

That is a real, measured property and it is not what the hypothesis said. It is
also a much more useful thing to know, because it is directly expressible.

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
5. **The `fell` group deserves its own study.** It has the highest mean of all
   four groups and fat tails. Falling liquidity is usually read as decay; here it
   is not obviously worse than rising. That is a corpse worth opening, not a
   conclusion.

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
