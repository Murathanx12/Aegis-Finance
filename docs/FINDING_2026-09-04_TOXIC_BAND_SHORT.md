# FINDING 2026-09-04 — The toxic band on the SHORT side

**Question** (from `docs/REVIEW_2026-09-03_GPT_VERDICTS_AND_CAPITAL_ALLOCATOR.md`
PART B): can the `toxic_ge_5` exclusion — the only band effect that survives
BH-FDR in S36 — be monetised as a short, or do borrow costs and the
distribution's own violence erase it?

**Licence**: PRODUCT_EXPERIMENT (post-hoc exploration; PIT discipline, explicit
costs and receipts never relaxed). Nothing here trades, sizes or seals.

**Receipt**: `backend/data/optimus/tracker_backtest/toxic_band_short_20260904.json`
**Code**: `scripts/toxic_band_short_run.py` (mechanics pinned by
`backend/tests/test_toxic_band_short.py`, 10 tests, offline)
**Panel**: same PIT table, investability, beta panel and contamination clause as
`scripts/band_horizon_run.py` (imported, not re-derived). 2013–2024, split-free
primary, ~168 toxic names/month.

---

## VERDICT

**The construction SURVIVES on paper at every borrow tier up to ~20%/yr, and the
hedged, liquidity-floored variant survives even a 50%/yr tier — but the entire
verdict now hangs on ONE unobserved number, the realised borrow fee, which this
repo does not hold.** The honest statement is a breakeven, not a return:

> the beta-hedged, $3m/day-floored 1-month short book breaks even at a
> **57.4%/yr borrow fee** (after 10bps/side trading; 56.6% at 25bps). Naive
> unhedged: **27.9%/yr**.

Hard-to-borrow small caps genuinely trade at 20–100%+/yr fees, so the realised
fee is plausibly the SAME order of magnitude as the edge. Nothing is closed and
nothing is claimed as alpha: the next gate is real borrow data.

## Headline numbers (1-month formation, 141 months, block t on date blocks)

| construction | names/mo | gross %/yr | t_block | breakeven borrow (10bps trading) | net @20%/yr borrow | net @50%/yr | worst period | TW gross (12y) | worst DD |
|---|---|---|---|---|---|---|---|---|---|
| naive short | 168 | +32.3 | 2.83 | **27.9%/yr** | +8.2 (t 0.79) | −20.0 | −27.5% (2020-03) | 13.7x | −59% |
| unit-hedged (short toxic + long $1 VW mkt) | 168 | +56.1 | 6.25 | 44.7% | +27.7 | −5.2 | −17.9% (2021-01) | — | — |
| beta-hedged (k = cohort mean β ≈ 1.27) | 168 | +61.9 | 6.85 | 48.5% | +32.5 (t 3.96) | −1.5 | −18.6% (2021-01) | 207x | −36% |
| liq-floored naive (≥$3m/day) | 63 | +40.1 | 3.14 | 33.7% | +14.6 | −15.1 | −35.1% (2020-03) | 23.5x | −62% |
| **liq-floored beta-hedged** | **63** | **+76.6** | **7.24** | **57.4%** | **+44.5 (t 4.65)** | **+7.6 (t 0.92)** | −19.1% (2020-03) | 530x | −43% |

- **Benchmark is short-the-market, not cash.** Shorting the VW market 2013–24
  lost −15.7%/yr (t −3.47). Paired vs that alternative the naive toxic short
  adds +56.1%/yr t 6.25 — which is, by identity, the unit-hedged book (stated
  in the receipt so it is never counted as two findings).
- **2022–2024 sub-window**: the effect is STRONGEST there — naive +53.4%/yr
  (era breakeven 43.5%), liq-floored beta-hedged +150.0%/yr t 4.98 (era
  breakeven 95.2%). Opposite sign of regime risk to the long 3–5 band, which
  died in 2022–24.
- **Horizon**: gross decays slowly with hold length (naive 32.3 → 22.1%/yr at
  12m) while turnover rises 0.26 → 0.89; **1-month formation dominates**, and
  the 12-month naive book RUINS one of its 12 phase chains outright (the
  2020-03 cohort returned +118% over the following year — an unlevered $1
  short is a wiped account).

## The violence, quantified (why position sizing is not optional)

Worst single name-months a 1m short would have carried, EW at ~1/168 each:
+476% (2020-07, ratio 37.2), +365% (2020-06), +354% (2020-05), +345%
(2016-02), +317% (2021-08, ratio 70.9), … +244% (2024-11). Ten name-months
above +235%. The worst book-level month is −27.5% naive / −18.6% hedged
(2020-03/2021-01 — COVID rebound and the meme-squeeze month, exactly where a
real short desk gets bought in). Squeezes cluster: 2020-05/06/07 are three of
the top four.

## Population realism (the fraction of the "edge" that is fictional)

- Raw ratio≥5 population (55,564 name-months, hygiene ignored): **45.2%
  sub-$2** (widely unborrowable), 58.2% sub-$3, **78.3% below $3m/day** dollar
  volume, 52.1% below $100m cap.
- Tradable band cohort (hygiene ≥$2 / coverage≥2 already applied, 24,450
  name-months): 0% sub-$2 by construction, 21.2% still sub-$3, **59.9% below
  the $3m/day floor — only 40.1% of the cohort passes** (median 63
  names/month). A short in the excluded 60% is fictional at size.
- Capacity is therefore small-book: ~63 EW names at $3m/day ADV. A few $100k
  per name at 1–5% participation; this is a personal-book or overlay-scale
  instrument, not a fund.

## What is honest and what is not yet

Honest: PIT panel, matured targets, delisting handled (short PROFITS on
delistings are captured, mildly understated where CRSP lacks the delisting
return — conservative for a short), pre-period betas, costs and borrow tiers
explicit, ruin reported as ruin, no rebate credited (conservative).

Not yet known, and DECISIVE: (1) realised borrow fees per name-month — the
breakeven sits inside the observed hard-to-borrow fee range; (2) availability
and buy-in risk (fees spike exactly when the squeeze comes — the fee and the
loss are positively correlated, which no constant tier models); (3) whether
10–25bps/side is achievable in sub-$5 names (breakeven moves only ~0.6pp from
10→25bps because turnover is 0.26, so trading cost is NOT the binding
friction); (4) the liq-floored subset's outperformance is post-hoc within this
study — it was picked as a realism screen, and it happening to also have the
larger gross is unexamined.

## Status, per the house taxonomy

- `naive_short @ 12m`: **FAILED_VARIANT** (one phase chain ruins; gross lowest,
  turnover highest). Closes the 12-month naive hold, not the family.
- `naive_short @ 1m`: **DEPRIORITIZED** — survives only ≤~20%/yr borrow, t
  under 2 at that tier; dominated by the hedged variants in both return and
  worst-month.
- `hedged_beta @ 1m` and `liq_floored_hedged_beta @ 1m`: **LIVE CANDIDATE
  CONSTRUCTIONS** for the next evidence gate. NOT a capital candidate, NOT a
  research claim — a PRODUCT_EXPERIMENT that survived its first frictions pass
  and now needs the one dataset that can kill it.

## Next step (what data adjudicates)

1. **Real borrow rates**: IBKR stock-loan API (fee + shares available,
   free with the account) per current toxic-band name; or Markit/S3 if ever
   entitled. Even a 3-month prospective log of (fee, availability) on the live
   toxic watchlist decides which tier row is real.
2. **Options as the short**: for the ~40% of the cohort passing the liquidity
   floor, long puts / call credit spreads cap the squeeze loss and embed the
   borrow in the option price. Needs OptionMetrics coverage check on toxic-band
   names (we hold 11.86m quote rows from S17 — the join is an afternoon).
3. **Fee–squeeze correlation**: any borrow-fee panel must be tested for the
   adverse correlation (fees highest exactly before the worst months) before a
   constant-tier net number is believed.
4. If (1) or (2) survives: a `PRODUCT_EXPERIMENT` paper book as its own
   separate book (never a weight in `arena_composite`), frozen contract before
   the first decision, short-the-market as its declared benchmark.
