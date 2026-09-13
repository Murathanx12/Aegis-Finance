# TRIAL-DRAFT-I — buyback-vs-insider-selling divergence (`buyback_insider_divergence_v0`)

**STATUS: UNSIGNED DRAFT.** Written 2026-09-14, **before any read**. It is not in
`rule_experiments` and has not incremented `cumulative_trials`: registration is
the attended step, and a draft that registered itself would make the attended
step decorative. This draft licenses a `PRODUCT_EXPERIMENT` READ only; a
`RESEARCH_CLAIM` stays attended.

**Family:** `NIGHT_JOB_BOOKS_2026_09_14` — **two** primary-metric tests (H and
I) sharing one multiplicity budget, Holm across the declared two inside the job.
A NEW family declared at size 2 **before either read**. It does not extend
`NIGHT_JOB_BOOKS_2026_09_13` (E, F, G, C_v1), whose four primaries are read and
whose budget is spent, nor `NIGHT_JOB_BOOKS_2026_09` (A, B, C, D).

**Licence:** `PRODUCT_EXPERIMENT`. Accrues zero capital. Places nothing.

## 0. Corpse check

`python scripts/lint_prereg.py <this file>` from `C:/Users/mrthn/Aegis module`
(verdict recorded in §7).

- **Resurrects: nothing refuted.** `TRIAL-INSIDER-IC`, `TRIAL-CMP-INSIDER-IC`
  and `TRIAL-BRAIN-003-opportunistic-insider` are all `trans_code == 'P'`
  (open-market PURCHASES) and none of them joins a repurchase field to
  anything. Book B (insider CLUSTER length, `FAILED_VARIANT`) is also code `P`
  and also has no buyback leg. Book H, this family's other primary, is
  `trans_code == 'A'` derivative GRANTS — a different code, a different table
  and a different mechanism from this book's `trans_code == 'S'` sales.
- **New instrument, and it is a JOIN rather than a column:**
  `comp__funda.parquet`'s `prstkc` has never been read by any book in this
  repository, and it has never been joined to the Form-4 tape. **This is the
  first book here to price a corporate action against its own insiders'
  disposals.**
- **This is not `TRIAL-CALIBRATED-TARGET-UPSIDE-1` or any revision book.** No
  analyst input appears anywhere in the construction.

## 1. Hypothesis

> Among US issuers that repurchased stock in their most recent publicly
> available fiscal year (`prstkc > 0`), those whose insiders were
> simultaneously NOT selling — the bottom tercile of a trailing-90-day
> percentage-of-holdings disposal intensity computed from Form-4 filings —
> inside the $3M-dollar-volume, $5-price eligible CRSP cross-section restricted
> to names carrying BOTH a linked repurchase observation and Form-4 coverage,
> beat a turnover-matched random twin drawn from that same covered band by more
> than the MDE in §4, over QUARTERLY date blocks 2006-2024.

**The claim is the DIVERGENCE, not either leg.** A buyback is a management
action and an insider sale is a management action, and the round-3 note's cited
2025 cross-country study (3.7M insider transactions, 34 countries) reports that
buyback-signal quality improves precisely where insider selling stays low. If
"buyback alone" or "low insider selling alone" pays as well as the conjunction,
this book has no mechanism of its own — which is exactly what §5's first
falsifier tests, and why that falsifier is a deciding one rather than a
diagnostic.

**Honest prior.** The cited composite buy/sell measures earn **≥ 1%/month
equal-weighted** across 34 countries. Three things stand between that and this
book, and all three are applied rather than mentioned: (a) it is a
cross-country composite and this is a single-market read; (b) it is a
long-short composite and this book holds one leg; (c) it pays this repository's
flat 25 bps-per-side ruler, which the source does not. The haircut working
prior is therefore **~0.5%/month**, declared in §4 — and §4 shows that number
sitting BELOW this construction's own MDE, which is a property of an annual
buyback field read over nineteen years and not a reason to inflate the
declaration.

**And it is a loser-side hypothesis on its reported half.** CLAUDE.md Rule 4
asks that losers be studied as hard as winners: the bearish leg (a firm
repurchasing while its insiders sell heavily — the agency-conflict cell) is
computed and printed on every receipt. It is never traded and never decides,
for the borrow-cost reason `NEGATIVE_RESULTS.md` banks: 162 anomalies go from
+0.14%/month to −0.01%/month after fees, and the short leg is the leg that
finding is about.

## 2. The data and the PIT rule, MEASURED before the read

Measured on disk 2026-09-14, before this draft was written. Nothing below is
assumed from a schema document; every figure came out of a direct pandas read.

**The buyback leg — `backend/data/optimus/wrds/bulk/comp__funda.parquet`**
(941,807 rows, 949 columns, `datadate` 1950-06-30 .. 2026-07-31):

| quantity | measured |
|---|---|
| repurchase columns present | `prstkc`, `prstkcc`, `prstkpc`, `tstk`, `tstkc`, `tstkme`, `tstkn`, `tstkp` |
| **`rdq` — the column the spec expected** | **ABSENT.** `rdq` is a `fundq` field; `funda` does not carry it |
| availability columns that DO exist | `pdate` (9.61% non-null overall), `fdate` (20.67%), `apdedate` (22.78%) |
| standard-filter rows, `datadate` 2004-2024 | **201,000** (`indfmt INDL`, `datafmt STD`, `popsrc D`, `consol C`, `curcd USD`) |
| of those, `pdate` or `fdate` present | **68.86%** |
| `prstkc` non-null on those rows | **70.92%**; `prstkc > 0` on **29.6%** |
| after the CCM link (below), rows with a `prstkc` value | **106,685**, **12,044 distinct permnos** |
| distinct permnos per availability-year | 5,004 (2008), 4,488 (2012), 4,631 (2016), 4,610 (2020), 5,152 (2024) |
| share of those with `prstkc > 0` | 0.486 / 0.474 / 0.527 / 0.592 / 0.570 |

**`apdedate` is NOT an availability date** and is not used: its measured lag
behind `datadate` is 0 days at the median and 0 at the 90th percentile — it is
the actual period end, not a publication stamp, and reading it as one would be
a look-ahead dressed as a PIT column. Measured lags behind `datadate`:
`pdate` q50 **61** days, q90 **125**, q99 692; `fdate` q50 98, q90 283.

**The buyback leg's PIT rule, stated with the column that does not exist.**
`available_date = max(pdate, fdate)` where either is present (**68.86%** of the
band), else **`datadate + 180 calendar days`**. 180 rather than the spec's 90:
the measured `pdate` lag is already 125 days at the 90th percentile, so a
90-day fallback would make roughly a fifth of the fallback rows readable before
Compustat itself had them. The fallback is deliberately LATE, because the error
that matters here is the one that cannot be detected in a backtest. **Which
basis fired is counted per row and printed on the receipt**, exactly as
`sec_insider_bulk.py` prints its own `observed_at_basis`.

**This book is ANNUAL on its buyback leg and says so.**
`compustat_fundq.parquet` — the quarterly panel Books E/F/G/A/C already read —
carries 31 columns and **no repurchase field whatsoever** (`gvkey, datadate,
rdq, fyearq, fqtr, saleq, revtq, cogsq, xsgaq, oibdpq, ibq, niq, epspxq,
epsfxq, atq, actq, cheq, rectq, invtq, lctq, ltq, dlttq, dlcq, ceqq, seqq,
txditcq, oancfy, capxy, dvy, cshoq, prccq`). A quarterly buyback read would
need a Compustat pull this repository has not made.

**The insider-sale leg — `sec_insider/parsed/<YYYYqN>.parquet`**, 82 files,
2006q1..2026q2:

| quantity | measured |
|---|---|
| rows with `trans_code == 'S'`, `table == 'NONDERIV'`, `acquired_disposed == 'D'` | **3,168,530** |
| of those, carrying a resolved `permno` | **0.8507** (2,695,472 rows) |
| distinct issuers / permnos on the resolved subset | **7,851 / 7,731** |
| `dollar_value` non-null | **0.9961** |
| `shares_owned_following` non-null | **0.9998** |
| `plan_10b5_1 == 'YES'` | **40.73%** |
| `plan_10b5_1_source` | `ABSENT` 1,504,871 / `FOOTNOTE_TEXT` 1,023,841 / `AFF10B5ONE` 166,760 |
| `plan_10b5_1 == 'YES'` by filing year | 36.6% (2010), 40.1% (2015), 53.1% (2020), 39.6% (2023), 48.8% (2024) |

**The 2023 coverage seam the spec warned about does not exist on the SALE
side** — and that is a measurement, not an opinion. The spec expected the
10b5-1 flag to be usable only from 2023 Q2 (when the SEC checkbox became a
filed field); on this table `plan_10b5_1_source == 'FOOTNOTE_TEXT'` carries the
flag back to 2006 at a rate between 36% and 53% in every year sampled. So the
10b5-1 recomputation is COMPUTABLE here, unlike on Book H's grant side where it
covers 0.734% of rows. It is still REPORTED and not deciding (§5), because this
draft declares exactly two deciding falsifiers and declaring a third after
measuring that it would work is choosing the tests after seeing the data.

**The insider leg's PIT rule** is Book H's, unchanged: `observed_at_utc` =
`filing_date` at 22:00 America/New_York, `observed_at_basis ==
"FILING_DATE_EOD_CONSERVATIVE"`. `acceptance_datetime_utc` exists on the table
and is **100% NULL on this vintage** (checked on 2015q1: 0 of 170,696
non-null). **Every date is `filing_date`, never `trans_date`.**

**The link — `backend/data/optimus/wrds/link_ccm.parquet`**, 33,324 rows,
columns `gvkey, permno, linktype, linkprim, linkdt, linkenddt`; filtered to
`linktype in ('LU','LC')` and `linkprim in ('P','C')` and required to bracket
the funda row's **`available_date`** (not its `datadate`): 29,163 gvkeys,
29,567 permnos survive the filter, and 126,651 of the 201,000 standard funda
rows link to a permno.

**THE DIVERGENCE FORMS AT THE LATER OF THE TWO DATES.** A block's score exists
only where both legs are public at that block's close. This is the whole PIT
defence of a two-source signal and it is enforced in the code, not promised
here.

The read is **2006-2024** — Form-4 coverage begins 2006q1 and CRSP daily ends
2024-12-31. Eras `(1990-1999, 2000-2009, 2010-2016, 2017-2024)` are REPORTED
with their block counts; the first is empty by construction and says so.

## 3. Primary metric — the ONE deciding number

`net_quarterly_excess_vs_random_twin`: the mean over **QUARTERLY date blocks**
of

    (book's net quarterly return) - (turnover-matched random twin's net quarterly return)

both legs net of the flat 25 bps-per-side interim ruler
(`cost_curve: flat_25bps_pending_5c`, `zero_cost_diagnostic=False`), NW lag-2 t
on the block series, at the **$3M primary floor**.

**The cadence is quarterly and the engine is unmodified.** The monthly CRSP
panel is pre-aggregated into quarterly `ym` buckets (returns compounded, price
taken at the quarter's last month, dollar volume the median of its months,
turnover summed) and `night_first_books_replay.run_monthly` is then run over
those buckets. That is the spec's own preferred option: a `rebalance_months`
gate inside the engine would change the code Books A/C/E/F/G were read under,
and a monthly rebalance on an annual buyback field would charge four
rebalances' costs for one refresh of information. **The receipt states which
approach was taken**, because "quarterly" and "monthly on a stale score" are
different books.

**The twin is drawn from the SAME COVERED POOL** — names with a linked,
available `prstkc` observation AND Form-4 coverage — so the book cannot beat
its control by requiring data the control does not have. Turnover is matched by
the engine's own `_turnover_matched_draw`.

**Reported, never deciding:** the **$10M secondary floor** cell with its twin
re-drawn at that floor; the per-era split at both floors; the BEARISH leg
(buyback + top-tercile selling); the 10b5-1-excluded recomputation with its
measured coverage beside it; the large-sale-only / small-sale-only split; the
dollar-scaled buyback-intensity diagnostic; realised turnover; median names
selected; the family Holm block over the declared two.

Two of the reported legs are **`FAILED_VARIANT` triggers** (§5).

## 4. Power — §64, computed BEFORE the confirmation

The family's shared power baseline
(`backend/data/optimus/first_books/mde_receipt.json`, the same k and engine
Books C/E/F/G were read under), then this book's own arithmetic, which is
quarterly and is NOT the family baseline:

| quantity | value |
|---|---|
| median cross-sectional MONTHLY return sd (measured) | **0.167186** |
| implied cross-sectional QUARTERLY return sd (× √3) | 0.289575 |
| k | 30 |
| implied book quarterly sd (`cs_sd / sqrt(k)`) | 0.052867 |
| **book-minus-twin quarterly sd (× √2)** | **0.074765** |
| nominal quarterly blocks (first scoreable block ≈ 2007q3) | **≈ 70** |
| **MDE at 80% power, alpha 0.05, two-sided, at 70 blocks** | **2.502%/quarter ≈ 0.834%/month** |
| the same, deflated by the measured lag-1 rho 0.1268 (n_eff 54.2) | **2.852%/quarter ≈ 0.951%/month** |

**Declared effect size: 1.50%/QUARTER (0.50%/month)** — the haircut working
prior of §1, not a number chosen to clear a bar. **The declaration is stated in
the unit the book earns**, because a per-month effect quoted beside a
per-quarter dispersion is a unit error and not a power statement; the first
draft of this file made it and the linter caught it. **It is BELOW this book's
own MDE at both figures.** That is stated here, before the read, and it binds §5:
this construction is **underpowered for the effect it most plausibly has**, an
outcome in (0, 1.50%/quarter) is `CONDITIONAL` and explicitly **not** a
rejection of the mechanism, and a null here may never be read as
`MECHANISM_REJECTED`. **The MDE is recomputed from this book's own realised
difference series, its own block count and its own measured lag-1 rho before
the decision, and the recomputation is reported.**

declared_effect_size: 1.50% per QUARTER (0.50% per month) mean net quarterly excess of the buyback-plus-low-insider-selling confirmation leg over a turnover-matched random twin drawn from the same covered band (BELOW this book's own nominal-70-block MDE of 2.502%/quarter and its deflated 2.852%/quarter; both are stated, and the book is declared underpowered for its own declared effect rather than sized to clear a bar cosmetically)
event_frequency_per_year: 4 (a QUARTERLY rebalance on a quarterly-refreshed sale leg and an ANNUAL buyback leg; approximately 70 nominal quarterly date blocks over 2007-2024, n_effective 54.2 at the lag-1 rho of 0.1268 measured on this same panel for TRIAL-DRAFT-C; this book's own rho is re-measured from its own difference series before the decision)
outcome_dispersion: 0.0748 (the book-minus-twin QUARTERLY sd implied by a measured median cross-sectional monthly return sd of 0.167186 scaled by root-three at k=30; the independence caveat of TRIAL-DRAFT-A section 4 applies and this is the optimistic bound)
outcome_horizon_days: 63 (one trading quarter; the book is re-formed at each quarter's close and earns the next quarter)
dependence_unit: ONE CALENDAR QUARTER of the whole cross-section -- the 30 names held in a quarter share the market and are not 30 independent draws, so one independent observation is one quarterly book-minus-twin difference and never one name-quarter
cross_sectional_k: 30
cross_sectional_rho: 0.1938 (MEASURED, not assumed: mean pairwise correlation of monthly name returns over 1995-2024, 250 names, 31,125 pairs, seed 20260912 -- receipt backend/data/optimus/first_books/mde_receipt.json, the same panel and k this book uses)
slice_purpose: CONFIRM -- 2006-2024 is the whole read and the whole decision. No slice of `prstkc` has been read by any Aegis session and no session has joined it to the Form-4 tape, so there is no earlier fit for a confirm slice to be disjoint FROM, and the draft says so rather than manufacturing a holdout
selection_window_note: none. The trailing-90-day sale window, the percentage-of-holdings intensity, the tercile cut, the 18-month buyback-recency requirement, the 180-day availability fallback and the direction of the held leg were all fixed BEFORE any read -- from the round-3 note's own cited literature and from the measured Compustat publication lags in section 2. The 2026-09-14 measurements in section 2 are COVERAGE and DATE-LAG counts; no return was computed before this draft was written
slice_securities: CRSP common stock above a $3M median dollar-volume floor and a $5 price minimum that ALSO carry a CCM-linked Compustat annual row with a non-null `prstkc` available within the trailing 18 months and at least one Form-4 filing of any code in the trailing 12 months; the twin is drawn from the identical covered band
slice_period: 2006-01-01 .. 2024-12-31
information_cutoff: the LATER of the two legs. Buyback leg: max(pdate, fdate) where present, else datadate + 180 calendar days, with the basis counted per row. Insider leg: each filing's own `filing_date` at 22:00 America/New_York (`observed_at_basis == FILING_DATE_EOD_CONSERVATIVE`). A block scores a name only where both legs are public at that block's close
selection_period: none
parent_trial: none
hypothesis_source: NONE -- the question comes from the published buyback and insider-trading literature (the 2025 34-country insider-transaction study cited in the 2026-09-13 round-3 research note; Financial Analysts Journal 2004 on large versus small insider sales) and from that note's observation that `prstkc` and the Form-4 sale rows were both already on disk and had never been joined. No Aegis trial's OUTCOMES motivated it

## 5. Decision rule

Evaluated **once**, when the replay job's receipt exists. Earliest decision
date: immediately.

- **`PRODUCT_PROMISING`** — the $3M net block-mean ≥ +1.50%/quarter at NW lag-2
  t ≥ 2.0, **AND** both falsifiers pass, **AND** the sign is positive in at
  least 3 of the reported eras that carry blocks, **AND** the $10M cell is also
  positive.
- **`FAILED_VARIANT`** — **any one** of:
  1. the $3M net block-mean over the registered slice is **≤ 0**, whatever the
     falsifiers did. (The TRIAL-DRAFT-C Amendment-1 clause, carried into this
     draft from the start rather than added after a read.)
  2. **the DIVERGENCE does not beat either leg alone.** Two single-leg books
     are run on the identical pool, floor, k, cost ruler and twin construction:
     `buyback_only` (every covered name with `prstkc > 0`, ranked by
     `prstkc / market_equity` descending, insider selling ignored) and
     `low_selling_only` (the bottom tercile of sale intensity, the buyback flag
     ignored). If EITHER single leg's net block-mean is greater than or equal
     to the divergence book's, the conjunction adds nothing and §1's claim —
     "the divergence is the signal, not either leg alone" — is falsified, and
     the book is closed even if its own number clears. This is a deciding
     falsifier because it tests the mechanism rather than the payoff.
  3. **the effect does not survive outside the smallest names.** Re-run inside
     the TOP HALF of the covered eligible band by median dollar volume, with
     the twin RE-DRAWN there, and require the net excess to stay positive. A
     buyback signal that lives only in the smallest names of a $3M-floor
     universe is small-cap beta with a corporate action attached, and the
     round-3 note's own source reports the composite as equal-weighted — which
     is the weighting that hides exactly this.
- **`CONDITIONAL`** — clears the primary metric but fails an era-stability or
  floor check, or NW t in [1.0, 2.0), or the block-mean lands between 0 and the
  declared effect. **§4 makes this the most likely honest outcome of a real
  effect at this sample size, and it is not a euphemism for failure.**
- **`CANNOT_DETERMINE`** — a falsifier that could not be computed is not a
  falsifier that passed, stated in those words. If either single-leg cell of
  clause 2, or the big-half cell of clause 3, cannot produce a readable block
  mean over at least **12 quarterly blocks**, that clause is **untestable, not
  passed**.
- **The 10b5-1 exclusion is REPORTED and NOT deciding, and the reason is that
  the order of operations matters.** §2 measures it as computable on the sale
  side (36-53% flagged in every year sampled, carried back to 2006 by footnote
  parsing). This draft nonetheless declares exactly TWO deciding falsifiers,
  because adding a third after measuring that it would work is choosing the
  tests after seeing the data — the failure mode this whole file exists to
  prevent. The recomputation with `plan_10b5_1 == 'YES'` sales excluded is
  printed on every receipt with its per-era coverage beside it. **If the
  morning wants it deciding, that is an amendment naming only that clause**, in
  the shape TRIAL-DRAFT-G §8b uses, and not a reinterpretation of this line.
- **The large-sale / small-sale split is REPORTED and NOT deciding**, for the
  same reason and with the same amendment route. The FAJ 2004 finding (only
  sales that are a large share of holdings carry negative information) predicts
  the intensity measure should work BETTER restricted to sales that are ≥ 10%
  of pre-sale holdings; both restrictions are computed and printed.
- **Contamination clause.** If the covered band (names with both legs
  available) in any year falls below **0.10** of that year's eligible names, or
  below **3 × k** names in the median quarter of that year, the year is
  EXCLUDED and the exclusion is reported before the number is.
- **Crash override.** A decision that would land within six months of an SPY
  trough ≥ −20% is deferred to ≥ 6 months past the trough.

## 6. Frozen parameters

The selector `buyback_insider_divergence_v0` exactly as
`scripts/night_books_hi_replay.py` constructs it, hashed at the registration
commit. Also frozen:

- the buyback field **`prstkc`** and nothing else of the eight repurchase
  columns; the Compustat standard filter `indfmt == 'INDL'`, `datafmt ==
  'STD'`, `popsrc == 'D'`, `consol == 'C'`, `curcd == 'USD'`;
- `available_date = max(pdate, fdate)` where present, else `datadate + 180
  calendar days`, with the basis counted per row;
- the **18-month availability-recency** requirement on the buyback row (an
  annual field plus a measured multi-month publication lag; a 12-month window
  would drop a firm whose filing slipped);
- `buyback_flag = prstkc > 0`; buyback intensity `prstkc / (csho × prcc_f)`
  from the SAME funda row, so the ratio carries one stamp and not two;
- the sale filter `trans_code == 'S'`, `table == 'NONDERIV'`,
  `acquired_disposed == 'D'`, stamped on `filing_date`;
- the **trailing 90-day** sale window ending at the block close;
- `sell_intensity = Σ shares_sold / (Σ shares_sold + Σ shares_owned_following
  at each insider's last filing in the window)`, a bounded [0, 1]
  percentage-of-holdings measure at the ISSUER level. A name with no sale in
  the window scores **0** — that is the signal, not a missing value;
- the **bottom tercile** of `sell_intensity` inside the covered band as the
  held leg; the top tercile as the reported bearish leg, **never shorted**;
- the rank inside the held leg: `sell_intensity` ASCENDING, ties broken by
  buyback intensity DESCENDING (the purest instance of the divergence first);
- the CCM link filter `linktype in ('LU','LC')`, `linkprim in ('P','C')`, the
  link range bracketing the **`available_date`**, not the `datadate`;
- the **12-month Form-4 coverage** requirement (any code) in the pool filter;
- k = 30; the **quarterly** cadence via pre-aggregated quarterly buckets; the
  $3M primary and $10M secondary floors; the $5 price minimum; the flat 25 bps
  per-side cost ruler; the turnover-matched random twin drawn from the covered
  band; 2006-2024.

## 7. Corpse-check result

Run 2026-09-14 against the recorded corpus, before the read
(`python scripts/lint_prereg.py` from `C:/Users/mrthn/Aegis module`):

```
PASS   (vs 358 prior experiments)
R13: n_required 195  n_available 653  smallest resolvable effect 0.82pp
R13e `CALENDAR_DISJOINT_BY_CONSTRUCTION`, R13f `NO_HYPOTHESIS_SOURCE_DECLARED`
nearest: 0.201 PREREG_TEACHER_LIBRARY_1 | 0.196 PREREG_REVISION_FORECASTER_1
         0.194 PREREG_WINNER_GENOME_1
```

`PASS` means UNMATCHED, not novel: it compares wording against what this
programme has recorded and knows nothing about the literature.
`CALENDAR_DISJOINT_BY_CONSTRUCTION` is a claim on the record — if any
threshold, tercile boundary, window or universe in §6 was in fact chosen after
looking at this join's payoff, that declaration is false and the result is not
a confirmation.

**R13's `n_available` is NOT this book's block count, and §4 is what binds.**
The linter models availability as `event_frequency_per_year` over the corpus's
own calendar span and arrives at 653 observations; **this book has ≈ 70**,
because Form-4 coverage starts 2006q1 and CRSP daily ends 2024-12-31. R13's
`smallest resolvable effect 0.82pp` is therefore an optimistic bound on a
longer sample than exists, and §4's **2.502%/quarter** (2.852% deflated) is the
MDE this registration is read against. The first version of this draft quoted
`declared_effect_size` per MONTH beside a per-QUARTER `outcome_dispersion` and
the linter returned `UNPOWERED_AT_REGISTRATION` on the unit mismatch; the
declaration now carries the unit the book earns, and the underpowering §4
declares is a real property of the sample and not an artefact of that error.

## 8. What this rule may NOT do

- No swapping `prstkc` for `prstkcc`, `prstkpc` or any treasury-stock LEVEL
  column after the first read. The eight columns are named in §2 so that a
  later reader can see that seven of them were available and not used; reading
  a second one for a better number would be eight books wearing one
  registration's clothes.
- No moving the 90-day sale window, the 18-month buyback recency, the 180-day
  availability fallback or the tercile cut after the first read. Each is a
  separate amendment naming only the input, in TRIAL-DRAFT-G §8b's shape.
- No promoting the 10b5-1-excluded leg, the large/small-sale split or the
  dollar-scaled buyback-intensity diagnostic to primary without the amendment
  §5 describes.
- **No short leg.** The bearish cell (buyback + heavy insider selling) is
  REPORTED and never traded; a short-side number from this job may not be
  quoted as a strategy return, because the borrow cost that took 162 anomalies
  to −0.01%/month is not in this cost ruler.
- No quoting the $3M-floor number as the result if the $10M cell disagrees;
  both are printed or neither is.
- No restating the cited ≥ 1%/month cross-country composite as this book's
  result, and no quoting the haircut ~0.5%/month as a measured number — it is
  an arithmetic prior and is labelled one.
- No quoting a MONTHLY number from this book without dividing the quarterly
  block mean by three and saying that is what was done. The book earns
  quarters.
- No reading a null here as `MECHANISM_REJECTED`. §4 declares this construction
  underpowered for its own declared effect; a global negative from an
  underpowered read is `FAILED_VARIANT` for this implementation at most, and it
  closes the ANNUAL-`funda` implementation of the divergence and not the
  divergence.
- No `RESEARCH_CLAIM` from this registration alone.
- No reporting the book's absolute return as an alpha: the claim is a
  DIFFERENCE, and no LEVEL under a placeholder cost ruler may be quoted as
  measured.

## 9. Registry

`rule_experiments` row `buyback-insider-divergence-v0`, **not yet written** —
the same state TRIAL-DRAFT-A/B/C/D/E/F/G/H stand in. Signing is the attended
step; this file and its commit timestamp are the tamper evidence that the rule
existed before the read.

## 10. The first read, 2026-09-14 — what it said

Receipt: `backend/data/optimus/night_factory_2026-09-14/B_books_hi_replay_run01.json`
(the same 75 s CPU run as Book H, `NIGHT_RUN_DATE=2026-09-14`, 75 quarterly
blocks 2006-2024, no year excluded at either floor, `honours_the_registration:
true`). **UNSIGNED. Nothing is adopted by this section; it records what the read
said.**

| | $3M | $10M | 1990s | 2000s | 2010-16 | 2017-24 |
|---|---|---|---|---|---|---|
| `buyback_insider_divergence_v0` @ $3M | **+0.355%/qtr t 0.33** | | empty | -1.44 (t -0.83) | +0.37 (t 0.39) | +1.18 (t 0.53) |
| the same @ $10M | | **+0.566%/qtr t 0.56** | empty | +1.39 (t 0.72) | +1.31 (t 1.54) | **-0.48 (t -0.24)** |

**Verdict under §5: `FAILED_VARIANT`, on BOTH falsifier clauses.** Clause 1 did
not fire — the primary is positive. Clauses 2 and 3 both did:

- **Clause 2, the divergence must beat either leg alone: FIRED.** On the
  identical pool, floor, k, cost ruler and twin construction, `buyback_only`
  returned **+1.093%/quarter (t 0.95)** against the conjunction's
  **+0.355%/quarter**. `low_selling_only` returned +0.011%/quarter (t 0.02). So
  whatever is in the primary cell is the buyback leg diluted by a sell-intensity
  cut that adds nothing — §1's claim, "the divergence is the signal, not either
  leg alone", is **not supported by this read**.
- **Clause 3, survives outside the smallest names: FIRED.** Inside the top half
  of the covered band by dollar volume, with the twin re-drawn there, the book is
  **-0.158%/quarter (t -0.16)**.

**The thing clause 2 turned up may NOT be quoted as a finding, and the reason is
on the receipt rather than in principle.** `buyback_only` is a CONTROL in this
registration, §8 forbids promoting it to primary, and — decisively — **at the
$10M floor the same control is -0.144%/quarter**. A leg that pays +1.09% at $3M
and -0.14% at $10M is a small-name cell, not a mechanism, and the big-half
result above says the same thing from the other direction. If anyone wants to
test buyback intensity as a book, that is a NEW registration with its own family
and its own falsifiers, not a row lifted out of this one.

**The FAJ 2004 prediction is not supported here either, and it was a REPORTED
leg rather than a deciding one, exactly as §5 declared before the read.**
Restricting the intensity to sales of >= 10% of pre-sale holdings gives
+0.372%/quarter; restricting it to SMALL sales gives **+0.525%/quarter** — the
opposite ordering to the one the large-sales-carry-the-information finding
predicts. Excluding `plan_10b5_1 == 'YES'` sales collapses the cell to
+0.024%/quarter (t 0.02). The bearish leg — a firm repurchasing while its
insiders sell heavily — is **-0.509%/quarter (t -0.77)**, the right sign for the
agency-conflict story and nowhere near significance; it is reported and was
never traded.

**Power, recomputed from the book's own realised series** (as §4 promised):
**3.402%/quarter** at $3M (75 blocks, realised difference sd 0.0852, measured
lag-1 rho **0.208**, n_eff 49.2) and 2.882%/quarter at $10M. The $3M figure is
**WORSE than the registered 2.502%**, because the realised block series is more
autocorrelated than the family baseline assumed. So this book is even more
underpowered than §4 declared it to be, the declared 1.50%/quarter effect sits
further below its own MDE than the registration said, and **this result may not
be read as `MECHANISM_REJECTED`**. It closes the ANNUAL-`funda` implementation
of the divergence, which is what §8 already said a null here could close.

**Coverage and the PIT basis, measured on the run:** 105,691 linked `prstkc`
rows, 2,695,472 resolved-permno sale rows, 9,106,525 Form-4 filing dates for the
coverage requirement, 76 quarters with a frame. The availability stamp fired
**354,872 times as `COMPUSTAT_PDATE_OR_FDATE` and 25,453 times as
`DATADATE_PLUS_180D_CONSERVATIVE` (93.3% / 6.7%)**, counted per (permno,
quarter) SELECTION rather than per `funda` row — which is the unit a PIT claim
is actually about. Covered share inside the eligible band: 0.887 (2006), 0.936
(2015), 0.944 (2024); no year fell below the 0.10 / 3k clause.

**The current era at the tradable floor, asked and answered plainly:** the
2017-2024 cell at $10M is **-0.48%/quarter at t -0.24 over 32 blocks**. It is
NEGATIVE. **The current era does not carry this effect** — and unlike Book H,
here the current era is the worst of the three populated ones at that floor.
