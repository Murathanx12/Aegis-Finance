# TRIAL-DRAFT-A — low short interest × high turnover, long-only (`si-low-turnover-high-v1`)

**STATUS: UNSIGNED DRAFT.** Written 2026-09-12, before any read. It is not in
`rule_experiments` and has not incremented `cumulative_trials`: registration is
the attended step, and a draft that registered itself would make the attended
step decorative. Signing it is what starts the clock.

**Family:** `NIGHT_JOB_BOOKS_2026_09` — **four** primary-metric tests, one per
book (A, B, C, D), sharing one multiplicity budget. Every other number any of
the four computes is `SCREEN`-only under `PRODUCT_EXPERIMENT` licence and is
reported, never deciding. Promotion of ANY ONE of the four to
`CAPITAL_CANDIDATE` or `RESEARCH_CLAIM` requires re-running the family's four
primary metrics under Holm (canon §63: SCREEN = BH-FDR, EXPORT = Holm) — a book
cannot be promoted by looking only at its own number while three siblings were
tested beside it.

**Licence:** `PRODUCT_EXPERIMENT`. Accrues zero capital. Places nothing.

## 0. Corpse check

`python scripts/lint_prereg.py <this file>` from `C:/Users/mrthn/Aegis module`
(verdict recorded in §7).

- **Resurrects: nothing refuted.** `NEGATIVE_RESULTS.md` §24 tested a
  short-interest **CHANGE** (`si_chg_low`, 3-month Δ, IC t 6.09 raw, DSR 0.457,
  one-way turnover 0.457/month — net-dead from turnover) and a **days-to-cover
  LEVEL** pair (`dtc_low`/`dtc_high`) on the SHORT leg. This book is the
  short-interest **LEVEL × turnover LEVEL** long-only cell held up to six
  months. The flow-versus-level distinction is exactly what §24 turns on, and
  the level was never the survivor because it was never the thing tested.
- **New instrument:** the panel
  `backend/data/optimus/short_interest/comp_sec_shortint/<year>.parquet` —
  2,211,042 rows, 1990-2024, built 2026-09-12 by
  `scripts/short_interest_panel.py` from the WRDS bulk tables already on disk,
  stamped `observed_at = datadate + 14 days`. §24's own features came from
  `batch8.py` in the `Aegis module` repo and nothing from that run persisted
  here; this join did not exist in this repository at all.

## 1. Hypothesis

> Names in the top (low short interest × high turnover) double-sort cell of the
> $3M-dollar-volume-eligible CRSP cross-section, entered on the short-interest
> figure's **publication** date and held one month with a six-month maximum
> hold, beat a random-universe twin drawn from the same liquidity band by more
> than the MDE computed in §4, over monthly date blocks 2011-2024.

**Honest prior.** Boehmer, Huszár & Jordan (*JFE* 96(1):80-97, 2010) document
≈ +1%/month alpha on the low-SI leg over 1988-2005, robust to weighting,
formation timing, risk adjustment, venue and dropping 1998-2000, surviving a
six-month hold. **Decay past 2005 is UNVERIFIED** — no replication was
retrieved — and McLean & Pontiff (2016) put average post-publication decay at
~58%. The prior is therefore "materially decayed, possibly to zero", not
"+1%/month". The published figure is the design's prior and never its
threshold.

## 2. The two eras, and which one decides

| | 1988-2010 (REPORTED, never deciding) | 2011-2024 (**the decision**) |
|---|---|---|
| what it is | BHJ's own sample (to 2005) plus the pre-publication OOS window | the post-publication era the literature has not covered |
| panel | the same build; CRSP daily files begin 1990, so the realised span is 1990-2010 | 1990-2024 build, 2011-2024 slice |
| blocks | 252 monthly | **168 monthly** |
| status | read alongside, reported in every receipt, decides nothing | the sole confirm slice |

The 1990 start is a **declared deviation** from the spec's 1988: the CRSP daily
files on this machine begin 1990-01, and `shrout` is what turnover needs. Two
years are not available and the receipt says so rather than the era label
quietly meaning something else.

## 3. Primary metric — the ONE deciding number

`net_monthly_excess_vs_random_twin`: the mean over **monthly date blocks**
2011-2024 (canon §58 — names inside a month share the market) of

    (book's net monthly return) − (random-universe twin's net monthly return)

with both legs net of the declared `CostModel` (5.0 bps transaction + 1.0 bps
slippage per side; the flag `zero_cost_diagnostic=False` travels on every row),
and a Newey-West lag-2 t on the block series.

**Reported, never deciding:** the 1990-2010 and 2006-2010 cells; the raw
quintile × quintile double-sort table; the $10M-floor re-measurement; the
beta-matched twin's leg; realised turnover; per-era signs.

## 4. Power — §64, computed BEFORE the confirmation

Receipt: `backend/data/optimus/first_books/mde_receipt.json`
(`scripts/first_books_mde.py`, built 2026-09-12).

| quantity | value |
|---|---|
| median cross-sectional monthly return sd, 2011-2024 | **0.162806** |
| k | 50 |
| implied book monthly sd (`cs_sd / √k`) | 0.023024 |
| book-minus-twin monthly sd (`× √2`) | **0.032561** |
| monthly blocks | 168 |
| measured lag-1 ρ of the block series | −0.0269 |
| n_effective | **177.28** |
| **MDE at 80% power, α 0.05, two-sided** | **0.685%/month** |

**Declared effect size: 1.00%/month**, one notch above the MDE, per TRIAL-R2's
convention — deliberately BELOW the published +1.3% so that a materially
decayed but real effect still registers.

**The caveat travels with the number.** `cs_sd/√k` assumes the 50 names'
residuals are independent. They are not; they share factors, so the true
book-minus-twin sd is LARGER and the true MDE is LARGER than 0.685%/month. This
is the **optimistic** bound and is stated as one. If the realised book sd on the
first read exceeds 3.26%/month, the MDE is recomputed from the realised series
before the decision is taken, and the recomputation is reported.

declared_effect_size: 1.00% mean net monthly excess of the top double-sort cell over its random-universe twin (one notch above the computed MDE of 0.685%/month, and deliberately BELOW Boehmer-Huszar-Jordan's published +1.3%/month so that a materially decayed but real effect still registers)
event_frequency_per_year: 12 (a monthly rebalance; 168 monthly date blocks over the 2011-2024 confirm slice, n_effective 177.28 after the measured lag-1 rho of -0.0269)
outcome_dispersion: 0.0326 (the book-minus-twin monthly sd implied by a measured median cross-sectional monthly return sd of 0.162806 at k=50; the independence caveat in the table above says this is the optimistic bound)
outcome_horizon_days: 21 (one trading month; the six-month maximum hold is a cap on rotation, not the grading horizon)
dependence_unit: ONE CALENDAR MONTH of the whole cross-section -- the 50 names held in a month share the market and are not 50 independent draws, so one independent observation is one monthly book-minus-twin difference and never one name-month
cross_sectional_k: 50
cross_sectional_rho: 0.2345 (MEASURED, not assumed: mean pairwise correlation of monthly name returns over 2011-2024, 250 names with >=90% month coverage, 31,125 pairs, seed 20260912 -- receipt backend/data/optimus/first_books/mde_receipt.json)
slice_purpose: CONFIRM -- 2011-2024 is the sole confirm slice and is chosen BEFORE the read because it is the post-publication era, not because of anything seen in it; 1990-2010 is read and reported and decides nothing
selection_window_note: none. No slice of this panel has been read by any Aegis session: the join was built on 2026-09-12 and this draft was written the same day, before any portfolio was formed on it. The nearest prior object, NEGATIVE_RESULTS §24, ran in the `Aegis module` repo on a short-interest CHANGE feature and nothing from that run persisted here
slice_securities: CRSP common stock (share codes 10/11) that carry a PUBLISHED Compustat short-interest print and a full 21-session CRSP volume window, above a $3M median dollar-volume floor and a $5 price minimum; 1,772-4,532 permnos per year on the built panel
slice_period: 2011-01-01 .. 2024-12-31
information_cutoff: each decision uses only rows whose `observed_at` (= settlement date + 14 calendar days, the measured median publication lag) is on or before the rebalance close, and only price/volume up to that close. Never `datadate`
selection_period: none
parent_trial: none
hypothesis_source: NONE -- the question comes from the published literature (Boehmer, Huszar & Jordan, JFE 96(1):80-97, 2010) and from the 09-12 probe's observation that the panel was already on disk. No Aegis trial's OUTCOMES motivated it; NEGATIVE_RESULTS §24 is quoted as a corpse to avoid, not as a result that suggested this one

## 5. Decision rule

Evaluated **once**, when the replay job's receipt exists. Earliest decision
date: immediately — this book needs no forward waiting, only the built panel.

- **`PRODUCT_PROMISING`** — 2011-2024 net block-mean ≥ +1.00%/month, NW lag-2
  t ≥ 2.0, sign positive, AND the same test at the $10M floor also clears. Seeds
  / continues the forward paper leg, unadopted as capital.
- **`FAILED_VARIANT`** — 2011-2024 net block-mean ≤ 0, OR the $10M-floor cell
  fails while the $3M-floor cell passes (tradability killed it, TRIAL-H5's own
  lesson).
- **`CONDITIONAL`** — passes one floor and not the other, or NW t in [1.0, 2.0),
  or the block-mean lands between 0 and the MDE. Reported, paper-tracked,
  unadopted, revisited at the next scheduled read.
- **Contamination clause.** If the panel's per-year join rate for any year in
  the confirm slice falls below 0.50 (it is 0.62-0.82 today), that year is
  excluded and the exclusion is reported before the number is.
- **Crash override.** A decision that would land within six months of an SPY
  trough ≥ −20% is deferred to ≥ 6 months past the trough.

## 6. Frozen parameters

The `Strategy` object `si_low_turnover_high_v1` exactly as
`scripts/seed_first_books.py` constructs it, hashed at the registration commit
(the book id is `book:<fingerprint>` and a changed field is a different book,
not an edited one). Also frozen: `PUBLICATION_LAG_DAYS = 14`;
`TURNOVER_WINDOW = 21` sessions; winsorisation at the 1st/99th percentile within
each output year; the composite `z(turnover_21d_w) − z(si_ratio)`; k = 50; the
$3M primary and $10M secondary floors; the 2011-2024 confirm slice.

## 7. Corpse-check result

Run 2026-09-12 against **358 prior experiments**:

```
PASS   (n_required 83, n_available 1729, smallest resolvable effect 0.22pp)
R13e `CALENDAR_DISJOINT_BY_CONSTRUCTION`, R13f `NO_HYPOTHESIS_SOURCE_DECLARED`
```

`PASS` means UNMATCHED, not novel: the linter compares wording against the
graveyard, the registry and the prereg corpus, and knows nothing about the
literature. The nearest neighbours it found are named in §0 and are quoted
there as corpses to respect, not as results that motivated this one.

`CALENDAR_DISJOINT_BY_CONSTRUCTION` is a **claim on the record**: it says no
prior fit was declared, so there is no selection window to overlap. If any
threshold, bucket boundary or universe in §6 was in fact chosen after looking
at this corpus, that declaration is false and the result is not a confirmation.

## 8. What this rule may NOT do

- No prompt, parameter or bucket search after the first read.
- No quoting the $3M-floor number as the result if the $10M-floor cell
  disagrees; both are printed or neither is.
- No claiming `RESEARCH_CLAIM` from this registration alone — that needs the
  family's four primary metrics under Holm, matched controls, a holdout and the
  24-month floor.
- No restating BHJ's published +1.3%/month as this book's result.
- No reporting the `turnover_21d` column as venue-adjusted: Nasdaq
  double-counting (Anderson-Dyl 2005) is **UNRESOLVED** and every panel row
  carries `turnover_unadjusted_for_venue = True`. A cross-venue turnover sort is
  exactly what this bites.

## 9. Registry

`rule_experiments` row `si-low-turnover-high-v1`, **not yet written**.
