# FINDING — 2026-08-31 — 13F: institutions SELLING predicts higher returns, buying predicts lower

**Receipt:** `backend/data/optimus/wrds/holders_13f.json`
**Code:** `scripts/holders_13f.py`
**Licence:** PRODUCT_EXPERIMENT — cross-sectional, doubly controlled, gross of costs.
**Status:** Murat's hypothesis **inverted** — the effect is real and points the other way.

---

## The hypothesis

> *"maybe the biggest holder sell or want more might be good indicator.
> estimating what firms and hedge funds will do will show that too"*

The instinct — that big-holder behaviour carries information — is **correct**.
The assumed direction is backwards.

## The point-in-time trap that had to be cleared first

`tr_13f.s34` carries `rdate` (quarter end) and `fdate`, and `fdate` reads like a
file date. Measured across 24 quarters:

> **`fdate − rdate`: median 0, min 0, max 0.** It *equals* `rdate`.

Using it as the knowability bound would assume a quarter's holdings were public
on the last day of the quarter — **45 days before they were**. On 72.7m rows
that would have produced a confident, wrong answer. The bound used is
`rdate + 45 days` (the SEC deadline), and it is still *optimistic*: managers may
file on the deadline, so true knowability is at or after it.

## The result

Forward 12-month return from a PIT-safe entry, 2013-2024, **152,668 name-quarters**.

Univariate, and monotone on all three independent measures:

| change in institutional shares | n | mean | median | >+100% |
|---|---|---|---|---|
| **sold >10%** | 8,684 | **+26.00%** | −0.29% | **11.8%** |
| sold 2-10% | 26,578 | +17.50% | +6.39% | 6.6% |
| flat | 54,488 | +11.95% | +5.92% | 3.9% |
| bought 2-10% | 30,805 | +10.84% | +3.00% | 5.0% |
| **bought >10%** | 18,113 | **+8.35%** | −4.37% | 7.2% |

| change in manager count | n | mean |
|---|---|---|
| lost >5 managers | 29,344 | **+18.07%** |
| gained >6 managers | 47,598 | **+9.09%** |

The largest holder's own move points the same way: added >20% → +8.74% (median
−5.37%); sold >20% → +13.81%.

### It survives both controls

**Popularity** (the 13F-popularity corpse, manager count, within quarter):
buy−sell negative in 4 of 5 quintiles.

**Trailing 12-month return** — the control that decides it, because institutions
buy what has already risen and what has risen mean-reverts:

| trailing-return quintile | inst sold >10% | inst flat | inst added >10% | buy−sell |
|---|---|---|---|---|
| q0 (worst) | **+40.35%** (3,594) | +18.87% | +16.34% | **−24.01pp** |
| q1 | +30.19% (1,294) | +12.24% | +10.02% | −20.17pp |
| q2 | +20.80% (885) | +10.91% | +10.73% | −10.07pp |
| q3 | +13.08% (884) | +10.45% | +9.99% | −3.09pp |
| q4 (best) | +13.30% (882) | +11.26% | +8.16% | −5.14pp |

**Negative in all five.** Holding fixed what the stock had already done does not
weaken the effect — it *strengthens* it. This is not momentum reversal wearing a
13F label, which is what it looked like before the control was applied.

## Why this is the direction it is

13F is **a 45-day-stale record of flow that has already happened**. By the time
we can see that institutions bought, the buying is done and the price contains
it — we are reading the receipt, not the intention. Selling leaves behind a name
that is under-owned, and the strongest cell in the whole study is the one where
both things are true: a stock that had **already fallen** and that institutions
then **dumped >10%** returns **+40.35%** over the following year.

That looks like forced or capitulation selling, and it is the opposite of a
crowding signal.

## What follows

1. **Invert the intuition, keep the instinct.** Big-holder behaviour carries
   information. "They are buying, so should we" is the wrong reading of it.
2. **This is a CONTRARIAN structural feature**, not a catalyst — quarterly,
   longs-only, 45 days stale by construction. It belongs on `CompanyState` as
   `d_inst_pct`, `d_managers`, `d_top_pct` and `top_share_of_inst`, conditioning
   other generators rather than firing on its own.
3. **It pairs with the coverage thesis.** Institutions leaving and analysts thin
   are two faces of "nobody is looking" — and both associate with the fat right
   tail. Worth testing jointly.
4. **The next control is LIQUIDITY, and it is not optional.** Names institutions
   dump >10% of are plausibly the smallest and widest-spread in the sample, and
   today's TAQ study priced that band at **149 bps round trip**. A +40%/yr gross
   cell in the thin band is not the same claim as a tradeable one. Until the
   band composition of these cells is measured, this is a research result and
   nothing more.

## Limits

- **Gross of costs**, and the strongest cells are most likely to be where costs
  are worst. See item 4 — this is the open question, stated rather than buried.
- **Longs-only.** 13F does not show shorts, so "institutions sold" may mean
  rotated, redeemed or hedged. It is not a directional view by the manager.
- **Optimistic PIT.** `rdate + 45d` assumes filing exactly on the deadline.
- **Survivorship:** delist-inclusive CRSP returns; names needing ≥3 managers and
  two consecutive quarters, which excludes the very smallest.
- **Not risk-adjusted**, and the sold-side cells have far more dispersion —
  median −0.29% against a +26.00% mean is a tail result, not a typical one.
