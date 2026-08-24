# SESSION 2026-08-25 (night) — the data, and the fifth instrument defect

## RESULTS SCOREBOARD

| | |
|---|---|
| best historical net strategy vs the market | `mom_12_1 / h5 / k=10 / inverse_vol`, **$85,482** median vs $39,951 (2013-2024) — was $77,002 before the split fix. **Still not seedable.** |
| best forward paper strategy | none launched |
| independent selector count | **1** (12-1 momentum) |
| farm candidates tested / promoted | ~1,700 / **0** |
| new actionable finding | **the panel booked every stock split as a return**, and fixing it changed the ranking of the signal grid |
| external execution drag | not measured this session |
| LLM spend / cost per gradeable output | **$0** — no LLM calls made |

**RESULT IMPROVEMENT: NONE.** No book launched, demonstrated edge still 0%.

Two things did change, and neither is a strategy:

1. **The replayable window went from 12 years to 32** (1993-2024), which is what
   the 2026-08-24 power check said was the gating constraint on every queued
   mechanism.
2. **A simulator defect that had been mis-ranking the entire signal grid was
   found and fixed.** It was worth 0.3%/yr in the mean and the whole ordering
   in the distribution.

---

## 1. The re-pull, and why it buys 32 years and not 35

`wrds_pull_catchup` skips "a table whose parquet exists", which is the right
rule for a pull that either happened or did not and the **wrong** rule for one
that happened with a narrower column list than a later consumer needs. The
1990-2012 CRSP files existed with five columns and could never gain the three
the simulator's conventions depend on.

`scripts/wrds_repull_dsf_early.py` keys its resume rule on **COLUMNS**. That
rule is the actual fix; the pull is what follows from it. It is the sibling of
*"a failure-driven queue cannot see a NEVER-ATTEMPTED item"* (2026-08-23), one
level in: **an existence-keyed queue cannot see a PARTIALLY-PULLED item.**

The window that buys is 1993-2024, not 1990-2024, and two independent
constraints stop at the same year:

| | |
|---|---|
| CRSP began collecting opens in **mid-1992** | `openprc` is 0.0% in 1990, 0.0% in 1991, ~46% in the 1992 file as pulled, 82.6% in 1993, 99.4% by 2024 |
| the early universe is **too thin to screen** | 243-475 eligible names per month in the 32 months from 1990-01 to 1992-10, against a top-500 cut |

32 years against the 36 the observed effect needs. `t` scales with `sqrt(T)`,
so 1.54 → ~2.6 *if the effect is stable* — and whether it is stable is the
actual question. 1993-2024 contains the dot-com peak, the GFC and COVID.

## 2. A column is not data

`replayable_years` certified a year on the PRESENCE of `openprc`. Handing
1990-2012 the full schema would have flipped every one of them to REPLAYABLE
while the column was empty, and a 1990 replay would have filled nothing —
`replay` refuses a non-positive open — producing a **buy-and-never-trade book
wearing a momentum policy's hash**.

Fixing the pull created the hole. The gate is now on measured coverage, with a
floor of 60% sitting inside the empty gap CRSP itself leaves between 41.6% and
82.6%, and an empty column gets its own refusal because its fix is different:
there is nothing to re-pull.

A worry settled on the way past: **inside the top-500 liquid universe the farm
actually trades, `openprc` coverage is 100.00% in every year 2013-2024.** The
2013-2018 vs 2019-2024 disagreement is not a fill artefact.

## 3. The fifth instrument defect: splits

`replay` holds SHARE COUNTS and marked them at raw `abs(prc)`. A share count is
not invariant across a corporate action.

    permno 85035, 2015-01-02
    prc     16.59 -> 70.40      cfacpr  0.25 -> 1.00
    ret            +6.088%      the farm booked   +324%

**Found by printing the DATES, not the distribution.** The excess-concentration
check said the best 10 of 2,746 sessions carried most of the edge; the
histogram said "fat-tailed", which is true of every equity strategy and
explains nothing. The dates said the same session topped the series for two
different rules — and an identical extreme on one date for two rules is an
instrument.

Net it was worth about -0.3%/yr. **The distributional damage was the whole
ranking**, because forward splits are commonest among large, liquid,
appreciating names:

| | before | after |
|---|---|---|
| `liquid` t | 0.26 | **2.55** |
| `size_large` t | -0.83 | **1.21** |
| `mom_12_1` terminal median | $77,002 | $85,482 |

`ret`/`tri` and therefore every SIGNAL were always correct — CRSP adjusts them.
Only the P&L path was wrong, which is why nothing looked broken. Invariant now
pinned: the adjusted price move equals CRSP's `retx` to 1e-6 across 3,950 names
(against `retx`, not `ret` — `ret` includes the dividend, which `replay` credits
as cash separately).

## 4. Three questions that belong before a leaderboard

### Could the sample have answered? — `portfolio_farm_signal_power`

**Zero of thirteen non-null signals produced an effect 2013-2024 could resolve
at 80% power.** Not the leader, not one. White's Reality Check over the grid,
nulls included: **p = 0.358**.

The null baseline makes it intuitive. Over 125 draws (12 seeds × 5 phases), a
random 10-name book returns a median of -3.66%/yr against the cap-weighted
market with a 5th-95th percentile of **[-9.77, +1.00]**. Ten points separate
the 5th and 95th percentile of *doing nothing at all*, and every non-null row
sits inside that band.

*(One draw is not a baseline: `random` at seed 0 returned -11.00%/yr over
2013-2018, near its own 5th percentile. Reading that as the construction drag
would have inflated every signal's edge by seven points.)*

### Does the edge survive breadth? — `portfolio_farm_breadth_power`

Grinold: `IR ~ IC * sqrt(breadth)`, so a real cross-sectional signal spread
over more names should show `t` RISING. Fitted over k=10..50:

    mom_12_1   slope -0.40,  peak t at k=10
    liquid     slope -2.37,  peak t at k=10
    size_large slope -1.24,  peak t at k=10

Every one falls and peaks at the narrowest book in the grid.

### What did it actually buy? — `portfolio_farm_concentration`

`liquid` finished with the best t (2.55), the lowest tracking error, the widest
temporal spread of its excess and a 13-year resolution requirement. On the
statistics alone, "build it as the second independent selector" was defensible
— and independent selectors are the stated bottleneck, so it was an easy ship.

The census, sampled quarterly:

    GOOG 48/44,  AAPL 44/44,  FB 44/44,  MSFT 44/44,  AMZN 43/44,
    TSLA 36,  NVDA 32,  AMD 24,  BAC 17,  NFLX 14

**A hand-drawn FAANG portfolio**, rebalanced every five days, over the one
decade when that was the best trade available. Every statistic about it is true
and it is not a signal.

The contrast with momentum on the same measure is what makes it legible:

    mom_12_1   NVDA 9, AMD 7, CVNA 6, SMCI 6, TSLA 5, MARA 5, PLUG 4
    mom_6_1    NFLX 5, DXCM 5, NVDA 5, AMD 5, CVNA 5, MARA 5, W 4

Momentum is a rotating high-beta book; `liquid` is a static mega-cap one.

## 5. The bottleneck, stated one level deeper

`CLAUDE.md` had it as *all ten arena books select on ONE signal — they differ in
portfolio treatment, not in alpha source*. True, and one level short. Audited
tonight, every one of the thirteen non-null farm signals reads from exactly
three quantities, all columns of `crsp.dsf`:

    past returns    mom_12_1, mom_6_1, mom_3_1, mom_12_0, reversal_1m,
                    reversal_1w, low_vol, high_vol, trend_200
    market cap      size_small, size_large
    dollar volume   liquid, illiquid

**Thirteen signals are thirteen transformations of one file.** Such a library
cannot produce an independent selector however many entries it gains, because
independence is a property of the DATA, not of the formula. Adding a fourteenth
price transformation is the expensive way to do nothing — which the grid
already demonstrated.

So `backend/services/portfolio_farm/characteristics.py` joins WRDS `finratio`
PIT onto the daily grid and registers **`value_bm`** and **`profit_roe`**, the
first two farm signals that are not transformations of price. Both era files
are on disk, so they span the whole replayable window.

The join is the hard part and it is where a silent lookahead would live.
`public_date` is WRDS's own availability stamp, so a value stamped `d` may be
used **strictly after** `d` plus a declared one-session margin;
`searchsorted(side="left") - 1` enforces it, and `side="right"` would make a
ratio visible on its own publication date. That leak would *not* show up as an
oracle correlation, because the characteristic really is a legitimate signal —
just known too early. Tested three ways. Forward-fill is bounded at ~14 months,
because a company that stops reporting would otherwise stay a value stock
forever and the companies that stop reporting are not a random sample.

Measured 2013-2024 (coverage 90.7% of traded cells for `bm`, 89.8% for `roe`):

    profit_roe   te  8.7%   excess  0.41%   t  0.16   MDE  7.35   <- 2nd lowest
    value_bm     te 19.0%   excess -2.73%   t -0.47   MDE 16.12

Neither wins, and neither should — value had a famously bad decade after 2013
and profitability was mediocre in a mega-cap growth regime. The point is that
`profit_roe` carries the second-cheapest MDE on the whole board, and that
**1993-2024 contains value's actual era**. Those two rows are where the widened
window has the most to say.

**The strongest evidence the join is right is the holdings, not the coverage.**
Census at k=10, quarterly:

    profit_roe   CL 33, MHP 26, HD 24, ORLY 22, KMB 19, MCO 18, LMT 16,
                 IDXX 16, CLX 15, UPS 13
    value_bm     AIG 28, C 28, MET 27, CFG 21, KHC 18, X 17, PRU 17,
                 CTL 13, WLL 12, MRO 11

Colgate, McGraw-Hill, Home Depot, O'Reilly, Kimberly-Clark, Moody's, Lockheed —
a textbook high-ROE quality book. AIG, Citigroup, MetLife, Kraft Heinz, US
Steel, CenturyLink, Whiting, Marathon — a textbook deep value book. **Neither
overlaps the momentum books (NVDA, AMD, CVNA, SMCI, MARA) or the `liquid` book
(the FAANGs) at all.** That is what a second data source looks like, and it is
visible in the holdings before it is visible in any statistic.

One defect caught by the same discipline: both ratios have a balance-sheet
quantity in the denominator, and `bm` runs to **89,351** in the raw file
against a median of 0.50. A `top_k` book does not merely tolerate that, it
SELECTS it, on every date, ahead of every real firm. Values outside declared
economic bounds are dropped (not winsorised — clipping makes them tie at the
cap and the tie-break is permno order). Cost: 0.029% of `bm` rows, 0.402% of
`roe`.

Next, and not built: **IBES consensus is on disk for both eras** with
`numup`/`numdown`, so an estimate-revision signal is one join away.

## 6. What is left

- **The 32-year run.** Queued and running unattended; results land in the
  receipts under `backend/data/optimus/portfolio_farm/`. The single most
  informative comparison it makes available: does `t` RISE with breadth where
  2013-2024 shows it falling? If so the extra history bought a different
  answer, not merely a tighter one.
- **`liquid` over 1993-2024 is the decisive test for that rule** — in
  1993-2000 the most-traded names were different ones and 2000-2002 punished
  them hard.
- **EVENT-RESPONSE-2 is `NOT_LICENSED_BORROW_CONFOUNDED`** — excluding the top
  borrow quintile (20% of events) removes >50% of the drift IC at 1d and 61% at
  5d, and the point estimate halves rather than the error widening. So the
  board has no unblocked alpha item, which is why the data was the right thing
  to spend the night on.
- **There is no premarket news job to move.** The morning jobs are
  `pi_ownership_collect` (06:00 ET, structurally one day behind — EDGAR
  publishes a day's index after that day closes) and `pi_congress_collect`
  (07:30 ET, timed for a fresh FMP quota). Neither is news. The decision loop
  is post-close: it decides at 16:30-17:45 ET and fills at the next open, so
  pre-market news on the fill day is *by construction* unusable. That is
  correct PIT discipline, not a lost opportunity.
