# FINDING — 2026-08-31 — De-contaminating the +400% band made it WORSE. The believable extreme target is the toxic one.

**Receipt:** `backend/data/optimus/tracker_backtest/upside_band_decontamination.json`
**Code:** `scripts/upside_band_decontamination.py` (machinery imported from
`scripts/tracker_ibes_backtest.py`, never retyped; rules sha in the receipt)
**Licence:** PRODUCT_EXPERIMENT — post-hoc, exploratory, paired-vs-market
convention identical to the parent backtest. 2013–2024, 434,212 name-months.
**Status:** The hypothesis this was built to test is **REFUTED**, and the
refutation is more useful than a confirmation would have been.

---

## The hypothesis, and whose it was

Murat: *"when we limit stocks by high increase band saying overall bad we are
losing on great winners too… rather than all %400+ upside band we can be more
specific."* The Fable brief (`2237e7c`) proposed downgrading the >400% hard
reject to `HIGH_UPSIDE_ANOMALY — DEEPER REVIEW REQUIRED`, on the theory that
the band's −26.47%/yr was *"largely because it contained stale/share-basis
garbage"* and that a *"legitimate, correctly adjusted"* 500% opportunity is
being thrown out with it.

My own feedback (`cf2b09d` §3) rated the retraction branch likely, citing the
median-44× receipt. **We were all wrong, in the same direction.**

## The experiment

Every cell graded twice — names in the +400%+ band inside the cell, and ALL
names inside the same cell — so "cheap names lose money" can never be misread
as a fact about the band. The +200–400% band (the healthy neighbour, +17.19%/yr
in the parent run) rides along as the control band in every cell.

## The result

**The dirty rows were diluting the damage, not causing it.**

| cell (within +400%+) | n | band excess/yr | t | ALL names in cell | band adds |
|---|---|---|---|---|---|
| price < $1 | 12,363 | **+6.30%** | 0.39 | +10.65% | −4.3pp |
| price $1–2 | 11,864 | −19.36% | −2.57 | −4.01% | −15.3pp |
| price $2–5 | 15,256 | −33.04% | −5.60 | −5.26% | −27.8pp |
| price ≥ $5 | 14,827 | **−47.17%** | **−8.45** | +0.53% | **−47.7pp** |
| crashed ≤−50% (12m) | 22,051 | −15.70% | −1.72 | −6.13% | −9.6pp |
| not crashed | 32,259 | −33.22% | −6.76 | +0.26% | −33.5pp |
| coverage 1 | 10,542 | −24.89% | −3.65 | −3.50% | −21.4pp |
| coverage ≥ 2 | 43,768 | −25.91% | −4.40 | +0.37% | −26.3pp |
| **CLEAN** (≥$2, no crash, no split, ≥2) | 19,204 | **−41.40%** | **−8.94** | +0.37% | **−41.8pp** |
| DIRTY (any marker) | 35,106 | −17.03% | −2.18 | −1.29% | −15.7pp |

The marginal toxicity of carrying a 5× consensus target is **monotone in how
believable the row is**: −4.3pp under $1 → −15.3 → −27.8 → **−47.7pp at $5+**.
The more reliable the price, the fresher the coverage, the *worse* the news.

### And the control band shows the winners are real — one band down

| cell (within +200–400%) | band excess/yr | t |
|---|---|---|
| price < $1 | **+77.76%** | 1.91 |
| crashed ≤−50% | +34.45% | 1.70 |
| DIRTY (any) | **+28.06%** | **2.55** |
| CLEAN | +9.95% | 1.44 |
| split in prior year | **−8.27%** | −0.60 |

Murat's *"we are losing great winners"* is **true** — and they live at
**+200–400% upside in cheap, crashed, under-covered names**, a region the
current bar at 4.0 already admits and the *execution* floor is what actually
excludes. The one negative cell in the healthy band is `split_prior_year`: the
single genuine data-integrity signature in the whole table.

## Why (mechanism, offered not proven)

A consensus target 5× the price of a **liquid, covered, non-crashed** stock is
not a measurement error — it is a maintained, believed opinion that the market
has persistently declined to converge to. That is the analyst-anchored glamour
signature, and the market is right about it to the tune of −41%/yr. In a
sub-$1 name the same ratio is usually arithmetic (a stale number over a moved
price) and carries almost no information either way (t 0.39).

## What follows — three rules instead of one, each in its own class

Using the Fable brief's own four-class framework:

1. **Keep the bar at 4.0 for CLEAN rows, as a statistical prior with teeth.**
   The proposed softening (`HIGH_UPSIDE_ANOMALY — REVIEW`) would spend review
   effort on exactly the wrong rows: the "legitimate, correctly adjusted" high
   upside is the **−41.40%/yr, t −8.94** cell. The bar is also remarkably
   well-placed: the same CLEAN cut is **+9.95% one band below it**.
2. **`split_prior_year` upside becomes UNREADABLE — a data-integrity rule,**
   in every band. It is the only cell negative on both sides of the bar
   (−30.18% above, −8.27% below). Refuse the ratio, don't interpret it.
3. **Sub-$2 band membership is UNINFORMATIVE, not damning.** For a WBUY-shaped
   row (sub-$1, one voice, algorithmic target) the band prior contributes
   nothing (t 0.39) and should be *silent*: the binding constraints there are
   target provenance (which "$5"? whose?) and execution authority (~$250),
   not this prior. The engine may say "no opinion from this evidence" — it
   must not say "historically bad."

## The methodological point, for canon

**Three of us — the human, GPT, and me — shared the same wrong prior**, that an
ugly average over a contaminated population must be the contamination's fault.
The de-contamination control was worth running precisely because we would not
have chosen its outcome: it turned a retraction candidate into the strongest
conditional result the band work has produced. Pairs with
`feedback_run_the_control_you_would_not_have_chosen` and with the 13F
inversion from the same day — the second time today an instinct survived while
its assumed direction flipped.

## Limits

- Monthly rebalance, one-month holding, paired vs equal-weight market; costs
  not charged (band grading, not a strategy claim) — identical to parent.
- `coverage` is analysts *rating* the name (recdsum), a proxy for target
  freshness, not target age itself; `ptgdetu`'s per-target `anndats` can
  sharpen this and is the natural follow-on.
- CLEAN-cell toxicity is an average over 19,204 name-months with a thin right
  tail (0.33% of months over +100%); this licenses the *bar*, not a short —
  shorting it would need borrow, costs and the drawdown work.
- The +77.76% under-$1 cell in the control band has t 1.91 on 953 rows —
  suggestive, not established. It is a hypothesis for the observe-universe
  work, not a tradeable claim.
