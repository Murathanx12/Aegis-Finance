# Adversarial review: the CRSP library board and CRSP_BLEND_v0 (2026-09-29)

Reviewer role: a sceptical investor. Licence of the object under review: `PRODUCT_EXPERIMENT`.
This review changed no production code and no book. $0.00, no LLM, no network. The throwaway
scripts that produced every number below are in `scripts/review_crsp_blend_2026-09-29/`
(`build_series.py <dir>` first, then `sel.py`, `sel2.py`, `wf.py`, `fac.py`, `reg.py`, `impl.py`,
`mkt.py`, `dsr.py`, each taking the same `<dir>`). They read only the receipts of run
`LIB_2026-09-29T0802Z`, board `2026-09-29T081355Z`, the panel `library_panel_2026-09-29T075640Z`,
the fundamentals `library_fund_2026-09-29T041550Z` and `wrds/ff_factors_monthly.parquet`.

## RESULTS SCOREBOARD

**RESULT IMPROVEMENT: NONE.** The +0.64%/mo blend is real in-sample structure, but it is the
selected maximum of a large search. When the same selection procedure is run forward in time, it
earns about zero to +0.3%/mo, and no variant reaches t 2.

| item | claimed | this review |
|---|---|---|
| blend rule - twin, 1995-2024 | +0.64%/mo, t 5.3 | reproduced exactly: +0.643, t 5.27 (block t); the iid t is 5.10 and the lag-1 autocorrelation is -0.01, so **the t is not inflated by blocking or overlap** |
| where the chosen four sit among every 4-of-33 candidate blend | not computed | **rank 2 of 40,920**. Median t 2.23, p90 3.14, max 5.27 |
| the same pick rule, select 1991-Y and test after Y (5 splits x 6 variants) | not computed | **OOS mean +0.01%/mo, 0 of 30 variants at t >= 2, best t +0.67** |
| walk-forward, reselected every year 2001-2024 (expanding window) | not computed | **+0.14 to +0.34%/mo, t +0.36 to +1.56** across 4 pick variants |
| DSR | 0.962 at n = 1,298 | **0.815** at n = 42,216 (adds the 4-of-33 space). **0.399** at n = 12.4M (4-of-133). **0.14** on 2008-2024 alone at n = 1,298 |
| factor spanning of the gap (FF3+UMD + low-vol, BAB, idio-vol, profitability, leverage, large-cap trend L/S) | FF3+UMD only, per rule | alpha **+0.64 to +0.87%/mo, t 5.1 to 6.8**. **This attack FAILS**: the gap is not a known factor premium on my proxies |
| blend net vs the market (not vs the twin) | not headlined | +0.42%/mo, **t 1.61**. 2010-2019: **+0.02%/mo**. With era-realistic spreads on the two small-name sleeves: +0.17%/mo, t 0.60 |
| twin net vs the market | not headlined | **-0.22%/mo** (twin CAGR 5.9% vs market 10.5%). About a third of the gap is the twin being a poor portfolio |
| kill rule false-kill rate | 5% implied by -1.645 sd | **about 20%** if "noise sd" is idiosyncratic-only (the SHADOW_BAYES convention); the gap's real 6-month sd is 5.8% |
| sessions needed to confirm +0.64%/mo at t 2 | "cannot confirm in 2026" | about **55 months**. At the walk-forward estimate of +0.3%/mo it is about **250 months** |

**Verdict:** the single-rule board findings stand as CANNOT_DISTINGUISH, as the note says. The
**blend's selection procedure is a FAILED_VARIANT when run forward in time**. The blend itself is
**CANNOT_DISTINGUISH** (DEPRIORITIZED as a lead, kept as a cheap shadow). **Score 34/100.**
**P(true positive edge over its matched twin, net of realistic costs) = 0.30.**

---

## 1. Look-ahead and leakage

**WRDS ratios are point-in-time by construction, with one soft edge.** I measured `public_date - qdate`
on the ratio file: the minimum is 59 days, and so is the 5th percentile. The median lag from the
annual date is 215 days. The merge takes `public_date <= decision date`, with a 70-day tolerance.

- The 59-day convention is safe for 10-Qs (45-day deadline).
- It is about a month early for 1990s annual numbers from small filers, which had a 90-day 10-K
  deadline before 2003.
- The values are also Compustat's current vintage, not as-first-reported.

Two sleeves read these proxies: `co03` (gross margin, top 30%) and `trend_quality_trend`. This is a
second-order leak. It is not what drives the result.

**The market-trend gate is known at decision time.** `mkt_trend_up` is the market close at the
decision date against its own 200-day MA. Entry is the next open. No leak.

**Delisting returns are applied to the book and the twin alike.** They are booked in
`crsp_rebuild.wide_from_crsp` from CRSP `dlret`, with a -30% fill for a missing 400-599 code. Both
legs read the same panel `fwd_ret`. `vol_compression` alone takes 817 delisting fills, which tells you
what it holds (see §5).

**The "large" filter is a fixed nominal $100M/day, and it defines a different strategy in each era.**
It is computed from 63-session median dollar volume known at the decision date. Eligible names in the
band, by year (monthly mean):

| 1991 | 1993 | 1995 | 1996 | 1997 | 1998 | 1999 | 2000 | 2008 | 2016 | 2024 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 3 | 6 | 17 | 29 | 52 | 76 | 113 | 196 | 332 | 345 | 520 |

- `px_vs_ma200_large` holds k = 20, so its series cannot start until 1995-07. That is why the blend's
  "1991-2024" is really **1995-07 to 2024-10, 352 months**.
- In 1995-96 the rule holds most of the band. The twin, which excludes the rule's holdings, runs out of
  same-band names: an estimated **87% (1995) and 54% (1996)** of its slots fall back outside the band,
  to mid and small names. After 1997 this is under 3%.
- In 1996-1999 the rule is a top-20-of-30-to-110 mega-cap momentum book. It rode the late-90s
  large-growth run, with rule - twin of **+30% in 1998 and +62% in 1999**.
- Today the same code is "top 20 of 520".

The run does not record twin fallback counts per rule, so the numbers above are my reconstruction from
the panel.

## 2. The twin: what it matches, and what it does not

The twin matches size band x vol_63 tercile x 12-1 tercile. On the blend's gap:

| regression of blend rule - twin (Newey-West, 3 lags) | alpha %/mo | t |
|---|---:|---:|
| FF3 + UMD | +0.75 | 6.69 |
| + low-vol, BAB, idio-vol L/S (built from the panel, EW terciles) | +0.87 | 6.80 |
| + profitability (gprof) and low leverage L/S | +0.80 | 6.52 |
| + large-cap price/MA200 L/S | +0.74 | 6.31 |
| same, 2000-2024 only | +0.64 | 5.16 |

**The factor attack does not kill the gap.** It does show that the twin is not neutral:

- The gap loads **-0.15 on the market (t -4)**, **-0.25 to -0.30 on SMB**, **+0.2 on BAB (t 3)** and
  **+0.14 on profitability (t 2.6)**. So the rule tilts lower-beta, larger and more profitable than its
  matched twin inside the same cell.
- By sleeve, `vol_compression` is -0.40 on the market, and `px_vs_ma200_large` is +0.66 on its own
  trend L/S (t 7.4).
- After all proxies, `trend_quality_trend` is alpha **+0.19 (t 0.9)**: it is explained by
  profitability and leverage. The other three keep t 2.7 to 4.5.

Caveats on the factors: they are equal-weight tercile L/S built on the same eligible panel. They are
not the published BAB (beta-neutral, levered) or FF5. RMW and CMA are not on disk.

**The larger point: "beats its twin" is a weaker claim than it sounds.**

- Net of costs, the blend's twin earned a CAGR of **5.9%** against the market's **10.5%**, with a
  twin-minus-market of -0.22%/mo.
- The twin is a randomly redrawn, 100%-turnover draw from cells that are full of small, high-vol names.
  Beating it is partly beating a bad portfolio.
- Against the market, the blend is +0.42%/mo at **t 1.61**. By decade: 1995-99 +1.34, 2000-09 +0.38,
  **2010-19 +0.02**, 2020-24 +0.47.
- The per-rule receipts say the same. The **net books' own FF3+UMD alphas are all
  CANNOT_DISTINGUISH (t 0.5 to 1.6)**. `co03` compounds at 10.9% net vs the market's 11.2%.

**Costs.** The engine charges 6/10/18/35 bps round trip by band. That is a 2026 schedule, applied with
nominal bands to 1991.

- `co03` turns over **92%/month** and `vol_compression` **77%/month**. Both hold names with a median
  of **$6-20M/day**, down to the $3.3M/day floor, and 84-98% of their slots are in the small/mid bands.
- Before decimalisation, round trips for such names were 100-300 bps.
- The twin pays the same schedule, so the gap moves less than the level does. But `co03` buys
  five-day losers, whose spreads are wider than their cell's average, off a close-to-close signal. That
  is the textbook bid-ask-bounce trade, and a flat band cost cannot see it.
- My stress adds 150/60/30 bps (pre-2001 / 2001-07 / 2008+) of extra round trip to the two small
  sleeves, on the rule only. It takes blend-minus-market to **+0.17%/mo (t 0.60)** and blend-minus-twin
  to +0.39%/mo.

## 3. Selection: the number that decides it

- **The candidate filter changed after looking.** This was disclosed, and the fix itself is sensible:
  the v1 filter could not go green.
- **The four were then picked from 33 candidates screened on the same 34 years.** I enumerated all
  **40,920** four-rule blends of the 33:

  | statistic of the 40,920 blends | block t |
  |---|---:|
  | median | 2.23 |
  | p90 | 3.14 |
  | share with t >= 3 | 13.7% |
  | share with t >= 4 | 0.8% |
  | **the chosen blend** | **5.27, rank 2** |

  The "best of each cluster" picking landed on essentially the maximum of the space. It also beat the
  mechanical version of its own rule, which is best-by-mean greedy at |rho| < 0.3 on the full sample,
  picks `qc629, mom_12_1_large, co03, trend_quality_trend` and reaches t 4.36. That is discretion on
  top of the search.
- **Random 4-of-133 blends** (60,000 draws): median t 0.12, p99 2.70, max 4.86. So there is population
  structure here, not pure noise.
- **The 1991-2016 "holdout" is not a holdout for the blend.** The candidate filter required a positive
  mean in 1991-2016, and the blend was chosen after reading it. The +0.63 (t 4.6) there is in-sample.
- **Running the pick rule forward in time is the only test that mimics deployment.** I split at 2003,
  2005, 2007, 2009 and 2011. For each split I rebuilt the filter in-sample (both sub-halves positive,
  majority of years, trimmed mean > 0, LOO > 0), picked 4 in six ways (by mean or t; |rho| < 0.3, < 0.5
  or no limit), and read the later years:
  - **forward (select early, test later): mean OOS +0.01%/mo, 0 of 30 variants at t >= 2, max t +0.67**;
  - backward (select late, test early): +0.37%/mo, 4 of 30 at t >= 2. The early era is where almost
    every rule beats its twin: the equal-weight average of all 133 rules is +0.22%/mo (t 1.9) there and
    -0.06 afterwards;
  - equal weight of all in-sample candidates (1991-2007) over 2008-2024: **-0.01%/mo**.
- **Walk-forward with annual reselection, 2001-2024** (expanding window, 287 months):

  | pick variant | OOS %/mo | t |
  |---|---:|---:|
  | best-by-mean, \|rho\| < 0.3 (the note's method) | +0.34 | 1.56 (15/24 years positive) |
  | best-by-mean, \|rho\| < 0.5 | +0.22 | 0.78 |
  | best-by-t, \|rho\| < 0.3 | +0.14 | 0.93 |
  | best-by-mean, no correlation limit | +0.14 | 0.36 |

  Of the frozen four, `px_vs_ma200_large` was **never** picked in 24 annual reselections and
  `vol_compression` once. `co03` was picked 23 times, which makes it the load-bearing sleeve.
- **The honest deflated number:**

  | search counted | DSR |
  |---|---:|
  | 1,296 cells + 4-of-33 (n = 42,216) | 0.815 |
  | 1,296 cells + 4-of-133 (n = 12.4M) | 0.399 |
  | 2008-2024 alone, at the note's n = 1,298 | 0.14 |

  The analytic null also assumes independent trials, and these are not. That cuts both ways, but no
  honest count gets to 0.95.

## 4. Regime (all keyed on the hold month)

**By decade** (%/mo): 1990s **+1.49** (53 months), 2000s +0.51, 2010s +0.40, 2020s +0.65.

**By hold year** (sum, %):

| 1995 | 1996 | 1997 | 1998 | 1999 | 2000 | 2001 | 2002 | 2003 | 2004 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 6.7 | 4.8 | 8.6 | **27.9** | **30.8** | 9.4 | **20.6** | 13.3 | 3.0 | 2.4 |

| 2005 | 2006 | 2007 | 2008 | 2009 | 2010 | 2011 | 2012 | 2013 | 2014 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 7.3 | 2.6 | 7.9 | 5.9 | **-11.2** | 2.2 | 4.1 | 0.1 | -1.6 | 7.0 |

| 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 13.5 | -4.1 | 9.1 | 14.0 | 3.9 | 7.9 | 16.0 | 11.2 | -4.6 | 7.7 |

**Concentration and robustness:**

- The top three years (1999, 1998, 2001) carry **35%** of the total.
- The top 5% of months by |value| carry 23%. The top 1% of months are 2020-12, 1999-10 and 2001-09.
- The worst leave-one-year-out mean is +0.57 (drop 1999). Leave-one-decade-out: drop the 1990s
  **+0.49**, drop the 2000s +0.71, drop the 2010s +0.77, drop the 2020s +0.64.

**Drawdown of the gap:** -17.3% (cumulative sum), from a 2008-11 peak to 2010-01. **2022-2024 alone:**
+0.41%/mo, iid t 0.91 on 35 months.

**2009, the momentum crash:** the blend lost -11.2% vs the twin, worst in March-May (-3.1, -6.1,
-1.2). It is **all `px_vs_ma200_large`: -40.7% in one year**. The other three were -3.5, -0.8 and +0.4.

**The sleeves do not share the regime:**

| sleeve | 1990s | 2000s | 2010s | 2020s |
|---|---:|---:|---:|---:|
| `px_vs_ma200_large` | 1.94 | **-0.02** | 0.59 | 2.62 |
| `co03` | 0.92 | 1.35 | 0.34 | **-0.27** |
| `vol_compression` | 0.63 | 0.43 | 0.31 | **-0.03** |

`px_vs_ma200_large` carries the 2020s, with 2021 at +84.5% for the sleeve. `co03` and
`vol_compression` have decayed to about zero. The blend's recent strength is one momentum sleeve in a
momentum decade.

Read fairly, the in-sample series is **not** carried by one year or one decade. This attack does not
kill the in-sample number; §3 is what kills the claim.

## 5. Implementability, and is the frozen book the backtested rule?

**Turnover and names:**

| sleeve | turnover per month | median $ volume of picks | what it holds |
|---|---:|---:|---|
| `px_vs_ma200_large` | 40% | about $150-300M/day | large and mega only |
| `vol_compression` | 77% | $6-20M/day | 84-98% small/mid |
| `co03` | 92% | $7-42M/day | 71-97% small/mid |

**Capacity:**

- **At $1M** it is fine: $12.5k per name, a fraction of a percent of daily volume.
- **At $100M** the two small sleeves put about $1.25M per name into names that trade $3-20M a day, and
  turn them over at 77-92% a month. That is 6-40% of daily volume per trade, so **not implementable**
  at the backtested costs. The practical capacity of the blend as specified is in the low tens of
  millions at most.

**The frozen book is the same concept, not the same rule:**

1. It selects on the vendor panel with SEC-facts fundamentals, while the backtest used WRDS proxies
   (disclosed).
2. "large" today is the top 20 of about 520 names. In the evidence years that carried the most weight
   (1995-1999) it was the top 20 of 17 to 113.
3. `trend_quality_trend` has no size floor. The frozen sleeve holds names at $6-45M/day (IBTA, QMCO,
   CDNA), which is consistent with the CRSP rule but is the least capacity-robust part of the book.
4. The forward twin is one 21-draw twin over the combined 77 names. In the backtest, the gap is the
   average of four separate sleeve gaps. This is equal to first order. It was not tested.

## 6. The kill rule at 126 sessions

The registration says "below -1.645 x its 21-draw noise sd". **This sd is not implemented anywhere for
`CRSP_BLEND_v0`.** The only implementation in the repo is `shadow_bayes_rule.kill_rule_power`. It uses
the names' idiosyncratic sd x sqrt(1 + 1/21) and assumes names are independent, so it leaves out the
book-vs-twin factor mismatch measured in §2 (market -0.15, SMB -0.25, BAB +0.2).

- **The real gap volatility:** the CRSP gap has a monthly sd of 2.37%, so **5.8% over 126 sessions**.
- **An idiosyncratic-only sd** for 77 names at about 10%/month residual is about 2.9%. That puts the
  kill line near -4.7%.
- **Under zero edge**, P(kill) = Phi(-4.7 / 5.8) ≈ **21%**, not 5%.
- **Under the claimed +0.64%/mo** (+3.9% over 126 sessions), P(kill) ≈ 7%.
- **Under the walk-forward +0.3%/mo**, P(kill) ≈ 14%.

A kill at 126 sessions would therefore move P(edge) only modestly, and an absence of kill almost not
at all. Confirming +0.64%/mo at t 2 takes about **55 months**. At +0.3%/mo it takes about 20 years.
**The forward book can falsify a large negative; it cannot adjudicate anything in 2026 or 2027.**

## Verdict

| object | verdict |
|---|---|
| single rules on CRSP (board) | as the note says: CANNOT_DISTINGUISH for all at honest multiplicity (best DSR 0.31) |
| the blend's selection procedure (filter -> clusters -> best four) run forward in time | **FAILED_VARIANT** (OOS about 0 on fixed splits; +0.14 to +0.34, t < 1.6, on walk-forward) |
| CRSP_BLEND_v0 as a forward candidate | **CANNOT_DISTINGUISH**, **DEPRIORITIZED** as a lead. Keep it as a free shadow, but recompute its kill line (§6) before any read. It must not be quoted as "the first positive number" |
| "large-cap trend survives, small momentum does not" (the note's new finding) | partly an **era artefact of a nominal $100M floor**: 1995-99 is a 17-to-113-name mega-cap book. Re-test with a rank-based size floor (top N by dollar volume) before calling it a finding |

**Score: 34/100.**

- For: the engineering, the receipts, the reproduction, the honest labels ("chosen after looking",
  "forward candidate, not a claim"), and the fact that the gap survives factor spanning.
- Against: rank 2 of 40,920, a forward-in-time OOS of about zero, a twin that underperforms the market,
  a vs-market t of 1.6, small-name sleeves at optimistic costs, and a kill rule whose sd is undefined.

**P(true positive edge over the matched twin, net of realistic costs) = 0.30.** The walk-forward
point estimate is positive but weak (+0.14 to +0.34), the population structure in the random-blend
draws is real, and costs push it down. **P(edge over the market net of costs) is about 0.2.**

## WHAT WORKS

- The CRSP bridge and the board. 140 rules on 34 survivor-free years in minutes, every number in a
  receipt, and the momentum note reproduced to the digit (`mom_12_1_q` +0.10, t 0.33).
- The blend's in-sample robustness. LOO-year worst +0.57, every LOO-decade at least +0.49, 26 of 30
  years positive, t not inflated by blocking (the iid t is 5.1).
- Factor spanning. The gap keeps +0.64 to +0.87%/mo alpha (t 5-7) after FF3+UMD, low-vol, BAB,
  idio-vol, profitability and leverage proxies. Whatever it is, it is not one of those proxies.
- `co03` is the most persistent member. It was picked in 23 of 24 walk-forward years.
- Disclosure. The filter amendment, the proxy labels and the chosen-after-looking status were all on
  the receipt.

## WHAT DOES NOT

- **Selection.** The blend is rank 2 of 40,920 candidates, the same procedure run forward earns about
  0, and the "1991-2016 holdout" was used to select it.
- **The benchmark.** The twin compounds at 5.9% against the market's 10.5%. Against the market the
  blend is t 1.6, and about zero in 2010-2019.
- **The era-dependent universe.** A nominal $100M floor makes the 1990s leg a 17-to-113-name mega-cap
  book, with a twin that fell outside its band in 87% of slots in 1995. The rule's biggest years
  (1998-99) sit there.
- **Costs and capacity.** Two sleeves are 77-92%/month turnover in $3-20M/day names, costed at a
  flat 2026 schedule. Adding era spreads cuts the vs-market edge to +0.17%/mo (t 0.6).
- **Decay.** `co03` -0.27 and `vol_compression` -0.03 in the 2020s. The recent strength is one
  momentum sleeve, which also lost 40.7% vs its twin in 2009.
- **The kill rule.** Its sd is not implemented for this book, and the idiosyncratic-only convention
  gives about a 21% false kill.

## HIGHEST-EV EXPERIMENT

**Test whether `co03`, the one sleeve the walk-forward keeps picking, survives real spreads and a
one-day skip.** Cost is about 1 hour and $0.

1. Re-run `co03_reversal_in_high_margin` and its twin on CRSP.
2. Enter at the open of t+2 instead of t+1, which removes the bid-ask bounce.
3. Charge each held and twin name its own half-spread for that month. Estimate it with Corwin-Schultz
   or Abdi-Ranaldo from the daily high and low. The `crsp_dsf` files on disk carry `askhi`/`bidlo` and
   `openprc`, but no closing bid/ask.
4. Read rule - twin by hold year, by decade and on the walk-forward.

**Why this one:** `co03` carries the only persistent part of the walk-forward result, and it is the
sleeve most exposed to microstructure.

- If it keeps at least +0.4%/mo, t >= 2, in 2001-2024 after this, P(edge) rises to about 0.45, and the
  blend should be re-registered as that sleeve plus a rank-based large-cap trend sleeve.
- If it falls to about zero, P falls to about 0.1, and CRSP_BLEND_v0 should be voided rather than
  graded.

**Second, also about 1 hour:** replace the nominal $100M floor with a rank floor (top 300 by dollar
volume at each date) and re-read `px_vs_ma200_large` and `mom_12_1_large`. That separates "large-cap
trend works" from "1996-99 mega-cap growth worked".
