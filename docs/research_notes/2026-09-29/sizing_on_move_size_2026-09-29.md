# Sizing on the size of the move (2026-09-29)

Licence `PRODUCT_EXPERIMENT`. $0 spent: no LLM, no broker, no network, no paid data pulled. Code:
`backend/services/move_size_sizing.py` (pure pieces and the verdict rule, declared before the
first run), `scripts/sizing_lab.py` (library panel) and `scripts/sizing_lab_crsp.py` (CRSP world).
Tests: `backend/tests/test_move_size_sizing.py` (16, offline). No cap, stop, sizing, book, ledger
row or past receipt was changed. **No shadow book was frozen** (§6 says why).

## RESULTS SCOREBOARD

**RESULT IMPROVEMENT: NONE for any stock book.** A better forecast of move size does not raise log
utility, Sharpe or terminal wealth when it is used to size, budget or time a stock position. It
does pick option straddles better than trailing volatility does. That result holds at 100 names
per leg and at a quintile, but not at 20, and the straddle book does not beat cash once a 10%
cost is charged.

| item | value |
|---|---|
| best historical net strategy vs the market | unchanged. Sizing by our size forecast never beat sizing by trailing vol in a stock book |
| best forward paper strategy | unchanged (nothing frozen today) |
| independent selector count | unchanged. The straddle selector is a candidate, not a book |
| farm candidates tested / promoted | 4 questions, 2 panels, 21 stock-book variants and a 3-cell straddle breadth sweep / **0 promoted** |
| new actionable finding | the point-in-time size forecast carries information **beyond option-implied vol**. Its partial rank coefficient on next month's \|move\| is **+0.21, t 20.8**, positive in every year 2014-2024. Used to pick straddles, it beats trailing vol by **+8.2 bp of equity a month at 100 names per leg (t 4.75)** |
| external execution drag | not measured. The straddle cost is an assumption (5 / 10 / 20% of premium); no option bid-ask data is on disk |
| LLM spend | $0.00 |

### The table of results (verdicts under the rule declared in `move_size_sizing.py`)

The objective is log utility, the mean monthly log(1+r). It is read on the variant **minus its
matched twin**: the SAME names on the SAME calendar, sized by the baseline input, so selection
cancels exactly. The t is on non-overlapping 3-month date blocks, and MDE = 2.8 x SE. "rand" is
the mean over 20 random 20-name books (seeded).

| # | question | panel / book | diff (log utility, %/month) | t | MDE | verdict |
|---|---|---|---|---|---|---|
| 1 | inverse size: ridge (dispersion held equal) vs trailing vol | library, rand | -0.007 | -0.46 | 0.041 | **CANNOT_DISTINGUISH** |
| 1 | same | library, mom_12_1_q tranche | -0.265 | -1.95 | 0.381 | **FAILED_VARIANT** |
| 1 | same, bar-defect screen | library, mom | -0.185 | -1.72 | 0.301 | FAILED_VARIANT |
| 1 | same, winsorised inputs | library, mom / rand | -0.200 / -0.006 | -2.14 / -0.42 | 0.262 / 0.041 | FAILED_VARIANT / CANNOT_DISTINGUISH |
| 1 | inverse size: point-in-time earnings ridge vs trailing vol | CRSP 2014-24, rand | -0.002 | -0.17 | 0.026 | **CANNOT_DISTINGUISH** |
| 1 | same | CRSP, mom | +0.087 | +0.83 | 0.292 | CANNOT_DISTINGUISH |
| 1 | **ORACLE ceiling** (realised hold vol, look-ahead) vs trailing vol | CRSP, rand | **+0.032** | +1.58 | 0.057 | ceiling, not a strategy |
| 2 | sit out every earnings window vs hold through | CRSP, rand, monthly | -0.059 | -1.59 | 0.104 | **FAILED_VARIANT** |
| 2 | sit out the top third by past earnings-move size vs hold | CRSP, rand | -0.034 | -1.61 | 0.060 | FAILED_VARIANT |
| 2 | ...chosen by past earnings-move size vs by trailing vol (twin) | CRSP, rand | -0.017 | -1.30 | 0.036 | FAILED_VARIANT |
| 2 | seek: event names, top vs bottom third by past earnings-move size | CRSP, rand | -0.056 | -0.14 | 1.08 | CANNOT_DISTINGUISH |
| 3 | half-Kelly on a fixed edge: ridge (dispersion held equal) vs trailing vol | library, rand / mom | -0.007 / -0.138 | -0.35 / -1.08 | 0.057 / 0.360 | CANNOT_DISTINGUISH / FAILED_VARIANT |
| 3 | same, point-in-time earnings ridge | CRSP, rand / mom | +0.003 / -0.042 | +0.25 / -0.61 | 0.034 / 0.192 | CANNOT_DISTINGUISH |
| 3 | 15% vol target: point-in-time ridge vs trailing vol | CRSP, rand | +0.006 | +0.74 | 0.023 | CANNOT_DISTINGUISH |
| 4 | straddle L/S picked by the point-in-time ridge vs by trailing vol, **20** names per leg | CRSP x OptionMetrics 2014-24 | +4.1 bp of equity | +1.45 | 8.0 bp | **CANNOT_DISTINGUISH** (the sweep's worst cell) |
| 4 | same, **100** names per leg | same | **+8.2 bp** | **+4.75** | 4.8 bp | **ALPHA_DETECTED** (PRODUCT_EXPERIMENT, post-hoc breadth) |
| 4 | same, **quintile** (~350 per leg) | same | +6.8 bp | +5.28 | 3.6 bp | ALPHA_DETECTED (same caveats) |
| 4 | the straddle L/S book itself vs cash, 10% cost | 20 / 100 / quintile | | +2.05 / +1.99 / -4.31 | | BETA_EXPLAINS / CANNOT_DISTINGUISH / FAILED_VARIANT |

**The honest verdict.** Size is predictable, and the size forecast is better than trailing vol
(IC 0.348 vs 0.332 on the library panel; 0.356 vs 0.332 point-in-time on CRSP). But in a stock
book, sizing on it is worth nothing measurable, and the ORACLE says why. Knowing each name's
realised volatility over the hold *in advance* adds only **+0.032%/month** of log utility over
trailing vol in a 20-name random book. The whole prize for sizing is about 0.4%/year, and a
forecast that closes a fraction of the gap between trailing vol (0.332) and the oracle (0.444)
buys a fraction of that. The only place the skill is worth first-order money is where the payoff
is convex in |move|: options. There it adds information the option market did not price
(§5). Whether that survives real option costs is not known from disk.

## 1. What was built, and the two panels

- **Library panel** (experiments 1 and 3): `night_backtest_factory.load_wide` + `build_panel`
  over the survivorship-free bars (living + delisted, reused tickers cut by
  `stitched_tickers.cut_reader_bars`). Month-end decisions, entry at the next session's open,
  delisting fill -30%. It has 372,751 rows, 117 dates and 4,848 symbols; 1,810 rows die inside
  the period. The survivorship caveat still applies: the living names were chosen alive on
  2026-09-01.
- **CRSP world** (experiments 2 and 4, plus a foreign-slice replication of 1 and 3), 2013-2024:
  - CRSP daily for the 4,796 permnos ever eligible in `crsp_pit_monthly_v1` (price >= $5,
    >= $100M dollar volume a month). 1,761 delisting returns were booked; 15 missing
    performance-code returns took -30%.
  - Earnings dates from Compustat `rdq` via CCM: 140,409 events.
  - OptionMetrics 30-day ATM implied vol.
  - 260,680 panel rows. Survivorship-free by construction.
- **The size forecast.** A walk-forward ridge on |next month's excess over the median|, refit every
  decision date. It trains only on dates whose target had closed (gap 2 decision dates; tested).
  - Library inputs: 13 price/volume columns.
  - CRSP inputs: 8 price columns, plus past earnings-move size (the mean |2-day abnormal| of the
    previous 2-4 reports) and an earnings-in-window flag.
- **The engine.** `move_size_sizing.run_book` reproduces `strategy_library.run_strategy`
  **exactly**: max abs difference 0.0 on all three quarterly offsets, printed on every receipt.
  Costs are the band toll, and zero costs are refused. Cash earns 0.
- **The selection.** `mom_12_1_q`, one third in each quarterly offset (calendar-neutral), plus
  20 random 20-name books. Weights: w ~ 1/size, capped at 10%.

### Three corrections made during the session (each disclosed on the receipt that follows it)

1. **Dispersion confound** (receipt `...025839Z`, kept).
   - The raw ridge's per-date dispersion (cv 0.35) is a quarter of trailing vol's (cv 1.36), so
     inverse-ridge weights sat near equal weight (mean L1 distance from equal 0.14 vs 0.29).
     The first comparison measured dispersion, not skill.
   - Fix: the PRIMARY variants map the ridge's ranks onto trailing vol's per-date distribution
     (`quantile_map`). The two books then differ only in which name gets which size.
2. **Calibration trap.**
   - A mean-square calibration gave trailing vol a kappa of 0.069 against a naive sqrt(21/252)
     = 0.289, because a few `vol_63` outliers dominate squares. That inflated every sigma and
     starved every Kelly book.
   - Replaced by a mean-absolute calibration (`calibrate_scale`), which is applied identically
     to every input.
3. **The earnings date was a look-ahead** (receipt `...030448Z`, kept).
   - The first earnings flag used the *actual* Compustat report date. A month-end decision does
     not know it for every name. The point-in-time flag projects from the last KNOWN report
     date in 91-day steps; it agrees with the actual flag on 83.8% of rows.
   - It cost the forecast 0.013 of IC: 0.369 with the actual date, 0.356 point-in-time.
   - It also removed the forecast's lead over implied vol, from +0.013 (t 4.5) to +0.004
     (t 1.4). **Every exp-4 headline above is the point-in-time version.** The actual-date
     straddle diff (+7.3 bp, t 2.45) is `BETA_EXPLAINS` on the |market| regression and is
     withdrawn.

## 2. Experiment 1: volatility-targeted sizing

The forecast is better. Library ridge IC **0.348 vs 0.332**, diff +0.016 with t 6.7 over 102
months, positive in 8 of 9 hold years; 2021 is negative. On CRSP the order is:

| forecast (CRSP) | IC with next month's \|excess\| |
|---|---|
| trailing vol | 0.332 |
| price-only ridge | 0.346 |
| point-in-time earnings ridge | 0.356 |
| actual-date earnings ridge (look-ahead) | 0.369 |
| oracle | 0.444 |

The books do not improve.

**Random books, where the comparison is cleanest**, give a tight null:

| panel | diff (%/month) | t | MDE |
|---|---|---|---|
| library | -0.007 | -0.46 | 0.041 |
| CRSP, point-in-time | -0.002 | -0.17 | 0.026 |

The ridge beats trailing vol in terminal wealth on 7 of 20 seeds (library) and 11 of 20 (CRSP).
By hold year the library diff, in % summed over the year, is:

| 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|
| +0.03 | +0.65 | -0.48 | -0.39 | -0.62 | +0.65 | -0.50 | -0.01 | -0.01 |

Leave-one-year-out worst: -0.015%/month (dropping 2019).

**In the momentum book the ridge LOSES on the library panel.**
- -0.27%/month, t -1.95. The market-regression alpha t is -2.02.
- It still loses with the bar-defect screen (-0.19%/month) and with winsorised inputs
  (-0.20%/month).
- On the foreign CRSP slice it is +0.09%/month, t 0.83.

The oracle says this is not a risk effect. Perfect foresight of volatility ALSO loses to trailing
vol in the CRSP momentum book (-0.18%/month, t -1.64). What inverse trailing vol earns inside
momentum is a return tilt toward calmer winners, which is direction by another name. It is not
risk reduction.

**Mechanical sizes.**
- Mean L1 distance between the (a) and (b) weights of the same names: 0.25. The book changes
  measurably; the outcome does not.
- Largest weight: 10% (the cap).
- Inverse vol vs equal weight: CANNOT_DISTINGUISH everywhere. Library mom +0.17%/month,
  t 1.13; CRSP rand +0.09%/month, t 1.16, beating equal weight on 19 of 20 seeds, with an
  alpha t of 3.2 that is the low-beta tilt.

## 3. Experiment 2: earnings events

**The size prediction replicates**, event by event (128,221 US events, 2014-2024):
- IC of past earnings-move size with the next |2-day abnormal| return: **0.297**, against
  **0.254** for trailing vol. Diff +0.043, t 6.7, MDE 0.018.
- Rank-regression b on past earnings-move size: **0.228 (t 33.8)**, beside b_vol 0.145. By year
  it runs from 0.15 (2022) to 0.26 (2017-18).
- This matches the contest desk's US 0.28-0.39 in shape.

**Acting on it loses.**
- Sitting out every earnings window cuts the random book's volatility from 22.8% to 22.1% a
  year. It gives up the announcement premium and a round trip: CAGR 5.3% becomes 4.4%, and log
  utility changes by -0.059%/month (t -1.59, FAILED_VARIANT).
- Choosing WHICH events to sit out by past earnings-move size is worse than choosing them by
  trailing vol: -0.017%/month, t -1.30.
- Seeking big predicted events is CANNOT_DISTINGUISH (MDE 1.1%/month; the top-third book has
  28.8% volatility and a -54.7% drawdown).
- Holding event names at all vs any name: +0.047%/month, t 0.37.

**In a 20-name long book, event variance is a rounding error on log utility, and the premium you
give up is not.**

## 4. Experiment 3: risk budget / fractional Kelly

**Declared constants:**
- a fixed edge of 0.5% a month for every selected name;
- half Kelly;
- average correlation 0.30;
- no leverage;
- a 15%/yr vol-target twin.

**The better variance forecast changes the sized book, but not its outcome.**
- The half-Kelly gross series under (a) and (b) correlate at 0.65. The mean invested share is
  0.21 vs 0.13 on the library momentum book.
- Every ridge-vs-vol risk-budget comparison is CANNOT_DISTINGUISH in random books: CRSP
  point-in-time +0.003%/month, MDE 0.034.

**Predicting the book's own risk.** The book's predicted sigma does not rank the realised book
|return| any better:
- Spearman over 100 rebalances: trailing vol 0.040, ridge 0.016.
- One month's |return| is a noisy variance proxy.

**Kelly at a 6%/yr assumed edge holds 13-21% gross.** Against a fully invested equal-weight book
it is FAILED_VARIANT: -1.76%/month on momentum, because cash is credited at 0. This is the
honest cost of a small assumed edge, not a property of the forecast.

## 5. Experiment 4: forecast size vs implied move (straddle paper test)

The data allows it:
- OptionMetrics 30-day ATM IV 2013-2024 is on disk (licensed WRDS pull, nothing new pulled);
- 229,741 name-months, a median of 1,755 names a month, 128 months.

**Conventions:**
- Signal at the decision close.
- Priced at the NEXT session's IV (entry).
- Payoff = |close(i+1+21) / close(i+1) - 1|, against premium ~ IV_entry x sqrt(30/365) x 0.798.
- A synthetic European-at-horizon ATM straddle; no early exercise, dividends or discounting.
- Cost 10% of premium round trip (sensitivity 5% and 20%).
- Utility is read at 2% of equity in premium per leg.
- The diff is regressed on |market return| over the window, which is the volatility shock.

**Size information the option market has not priced.** Per date, rank(|r21|) was regressed on
rank(implied) and rank(forecast):

| forecast | its coefficient beyond implied | t | smallest year |
|---|---|---|---|
| trailing vol | +0.119 | 13.2 | |
| price-only ridge | +0.183 | 18.1 | |
| **point-in-time ridge** | **+0.211** | **20.8** | +0.142 (2020) |

On its own, the point-in-time ridge ranks |r21| about as well as implied does (0.365 vs 0.361,
diff t 1.4). Implied still carries weight beside it (b 0.18, t 19.6). The two are complements.

**Straddle selection** (long the 20/100/quintile cheapest by forecast/implied, short the richest).
The diff vs the trailing-vol twin is cost-invariant, because both books make the same number of
trades.

| names per leg | diff (bp of equity/month) | t | MDE | alpha t (\|mkt\|) | LOYO worst | w/o best 5 months | years positive | verdict |
|---|---|---|---|---|---|---|---|---|
| 20 | +4.1 | +1.45 | 8.0 | -2.48 | +2.2 (drop 2022) | +0.6 (86% of the total in 5 months) | 6 of 11 (negative 2014-18) | CANNOT_DISTINGUISH |
| 100 | **+8.2** | **+4.75** | 4.8 | +3.17 | +7.4 (drop 2023) | +6.3 (27% in 5 months) | **11 of 11** | ALPHA_DETECTED |
| quintile | +6.8 | +5.28 | 3.6 | +3.94 | +6.3 (drop 2018) | +5.5 | 10 of 11 (2021 negative) | ALPHA_DETECTED |

**What the ALPHA_DETECTED rows can and cannot carry:**
- **The breadth sweep was declared after the 20-name read.** The worst cell of the sweep is
  CANNOT_DISTINGUISH, and that is its verdict under the house rule.
- **It is a relative result.** The ridge-selected straddle book beats the vol-selected one.
  **Neither beats cash robustly.** At 10% cost the 100-name L/S makes +2.09% of premium a month
  (vol twin -2.01%), and its utility t vs cash is 1.99. At a quintile both lose. At 20 names the
  result is +8.3% (5% cost), +3.3% (10%) and -6.7% (20%).
- **Most of the absolute P&L is the short leg,** i.e. the variance risk premium. The mean
  straddle returned -7.2% of premium a month before costs.
- **The pricing is synthetic and the cost is assumed.**
- **No live option-IV source is on disk.** OptionMetrics ends 2024-12, so no existing grader can
  mark a straddle book.

## 6. Why no shadow book was frozen

The rule was: freeze ONE shadow contract that uses size-forecast SIZING, if and only if something
improves the declared objective out of sample.
- **Nothing in the sizing experiments did** (§2-§4: every stock-book comparison is
  CANNOT_DISTINGUISH or FAILED_VARIANT).
- **The one positive result is option SELECTION, not sizing.**
- **It is relative to its twin, not to cash.**
- **Its breadth was chosen after the first read.**
- **It needs option prices that no grader on this machine can read forward.**

A contract that cannot be graded would be a promise without a grader. Nothing was frozen.

**Worst-case print (protocol 4) for the sizing rule that would have been proposed** (inverse
point-in-time size, mom_12_1_q top 20, decision 2026-09-28):
- Equity $1,000,000; 20 names; a 10% cap per name; gross / equity = 1.0.
- **No stop** (held to the quarterly rebalance), so the bound is notional: one name to zero is
  **-$100,000**, and every name to zero is **-$1,000,000**.
- In sigma: current names run 22-38% a month (SNDK 0.28, WOLF 0.38, AXTI 0.29). At
  inverse-sigma weights a 3-sigma one-month move costs **-$35,758 per name**, and -$715,157 if
  all 20 move 3 sigma together.
- A straddle book at 2% of equity in premium per leg has a long leg capped at its premium
  (-$20,000). The short leg is unbounded: at 20 names and 10% cost its worst drawdown was
  -6.2% of equity.

## 7. Data defect found (reported, not fixed; the factory's files are not this lane's)

The library panel's `vol_63` and `mom_252_21` carry bar defects:
- **LINE on 2024-09-30**: vol_63 = 895.7 (89,574% a year) and 12-1 momentum = +462.9x.
  SN, BIOA, VAL, OBE, WLL and WOLF are further examples.
- **646 eligible rows (0.25%, 259 symbols)** are above 200% a year.
- **172 of 2,080 momentum top-20 slots** hold a row with vol_63 > 3 or |12-1| > 20. Momentum
  *buys* these.
- Inverse vol zero-weights them mechanically, which is part of why inverse vol beat the ridge in
  the momentum book. The screened re-run keeps that verdict.
- These look like reused tickers or split-adjustment breaks that `cut_reader_bars` did not cut.
  They are worth a `stitched_tickers` audit before any momentum number is quoted again.

## 8. Files and receipts

Every file name carries a run id; nothing was overwritten.

| role | path |
|---|---|
| pure pieces + verdict rule | `backend/services/move_size_sizing.py` |
| library runner | `scripts/sizing_lab.py` |
| CRSP runner | `scripts/sizing_lab_crsp.py` |
| tests (16) | `backend/tests/test_move_size_sizing.py` |
| **PRIMARY library receipt** | `backend/data/optimus/sizing_lab/sizing_library_2026-09-29T030603Z.json` |
| **PRIMARY CRSP receipt** | `backend/data/optimus/sizing_lab/sizing_crsp_2026-09-29T031829Z.json` |
| superseded, kept | library `...025839Z` (raw ridge, mean-square calibration), `...030337Z` (before the screen / winsor); CRSP `...030448Z` (actual-date earnings flag only), `...031017Z`, `...031402Z` (before the breadth sweep / beyond-implied) |
| monthly series | `sizing_*_monthly_<run>.parquet` beside each receipt (gitignored) |

The module is reachable from `scripts/` (tooling closure; `assert_no_unclassified_orphans`
passes).

## WHAT WORKS / WHAT DOES NOT / HIGHEST-EV EXPERIMENT

**WHAT WORKS:** the size forecast is real, and it is complementary to the option market. The
point-in-time ridge ranks next month's |move| better than trailing vol (0.356 vs 0.332, t 8.9).
Past earnings-move size predicts the next earnings move beyond volatility (b 0.228, t 33.8). The
forecast carries information beyond option-implied vol (+0.21, t 20.8, every year 2014-2024).
Used to choose which straddles to buy and sell, it beats trailing vol by +8.2 bp of equity a month
at 100 names per leg (t 4.75, 11 of 11 years), in a post-hoc breadth cell.

**WHAT DOES NOT:** using that skill in a stock book. Inverse-size weights, event avoidance, event
seeking, a half-Kelly risk budget and a vol target are all CANNOT_DISTINGUISH or FAILED_VARIANT
against the same book sized by trailing vol. The oracle shows the ceiling: perfect foresight of
volatility is worth +0.03%/month of log utility in a 20-name long-only book. Sitting out earnings
costs the announcement premium (-0.06%/month).

**HIGHEST-EV EXPERIMENT:** a forward, $0 paper log of straddle selection on LIVE option chains.
- Each month-end: record the point-in-time ridge's E|r21| for the liquid optionable names.
- Record each name's quoted ATM straddle mid AND bid/ask at the next session.
- Grade 21 sessions later: the 100-name L/S by forecast/implied against the trailing-vol twin,
  on real quoted costs.
- Build first: a free delayed chain source for the IV and spreads, and an options grader. Neither
  exists on disk.

It is the only use of the engine's one demonstrated skill that the history says could pay. The
two unknowns that decide it are the real round-trip cost and whether the 2014-2024 relative edge
holds forward, and both need live chains.
