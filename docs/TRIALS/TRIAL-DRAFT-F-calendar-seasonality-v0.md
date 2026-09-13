# TRIAL-DRAFT-F — return seasonality, same-calendar-month tilt (`seasonality_11_20_v0`)

**STATUS: UNSIGNED DRAFT.** Written 2026-09-13, before any read. It is not in
`rule_experiments` and has not incremented `cumulative_trials`: registration is
the attended step, and a draft that registered itself would make the attended
step decorative. This draft licenses a `PRODUCT_EXPERIMENT` READ only; a
`RESEARCH_CLAIM` stays attended.

**Family:** `NIGHT_JOB_BOOKS_2026_09_13` — **four** primary-metric tests (E, F,
G, and Book C's v1 re-read) sharing one multiplicity budget, Holm across the
declared four inside the job. A NEW family declared at size 4 before the read;
it does not extend `NIGHT_JOB_BOOKS_2026_09`, whose budget is spent.

**Licence:** `PRODUCT_EXPERIMENT`. Accrues zero capital. Places nothing.

## 0. Corpse check

`python scripts/lint_prereg.py <this file>` from `C:/Users/mrthn/Aegis module`
(verdict recorded in §7).

- **Resurrects: nothing refuted.** The momentum family is the nearest thing on
  the books, and this construction is chosen SPECIFICALLY to be disjoint from
  it: the signal is built from returns **11 to 20 years old**, at lags that are
  exact multiples of twelve months, so it cannot overlap the 12-1 window the
  arena's ten books already price (CLAUDE.md's own bottleneck note: 99.5% of
  names carry exactly one factor, 12-1 momentum). Short-horizon
  winner-chasing is a Holm-surviving ANTI-signal in this repository's results
  and is a different lag structure again.
- **New instrument:** JKP's own `seas_11_15an` and `seas_16_20an` columns on
  the panel already on disk (`jkp_full/jkp_usa_*.parquet` 1926-2012 and
  `jkp_global_factor_usa.parquet` 2013-2024), never read by any book here.

## 1. Hypothesis

> The top tercile of the equal-weight mean of the within-month cross-sectional
> z-scores of `seas_11_15an` and `seas_16_20an`, inside the $3M-dollar-volume,
> $5-price eligible CRSP cross-section restricted to names carrying BOTH
> columns, beats a turnover-matched random-universe twin drawn from that same
> covered band by more than the MDE in §4, over monthly date blocks 1990-2024.

**Honest prior.** Heston & Sadka (*JFE* 87(2):418-445, 2008): the cross-section
of expected returns carries an annual seasonal component with an **annualized
standard deviation of 13.8%**, positive in every calendar month, from a
cross-sectional autocorrelation at lags that are multiples of twelve months out
to twenty years. **That is an SD-shaped ruler, not a mean-return-shaped one.**
The 2026-09-13 research note (§2) records that **no decile-spread percentage
was found** in the fetched sources and marks it NOT FOUND; it is not converted
into an implied monthly return here, and this book's honest prior is therefore
weaker than Book E's or Book G's — the declared effect in §4 sits barely above
the MDE for exactly that reason.

## 2. The alignment, MEASURED before the read

A seasonality signal is an off-by-one-month defect waiting to happen, so the
alignment was measured rather than assumed, on 2026-09-13, before this draft
was written:

> `seas_2_5an` at `eom = t` correlates **0.99999** with the mean of the same
> name's own excess returns at months `t + 1 - 12k`, k = 2..5 (n = 2,294
> sampled rows, seed 1). The same test at shift 0 gives −0.076 and at shift −1
> gives −0.006.

So the JKP column stamped at `eom = t` is the same-calendar-month average for
**month t+1** — which is exactly the month the replay engine earns, since it
selects at the close of `t` and takes `t+1`'s return. The engine's convention
and the column's convention match, and this paragraph is the evidence rather
than the assertion.

**Coverage is the real constraint and the receipt prints it**: in 2013-2024,
`seas_11_15an` is present on 0.468 of rows and `seas_16_20an` on 0.372; in
1990-1991, 0.286 and 0.145. A name needs twenty years of tape to carry both,
so the covered band skews old. The twin is drawn from that SAME covered band
(§3), so the skew is shared and cannot be the result.

The read is **1990-2024**, the span of the CRSP daily files. Eras
`(1990-1999, 2000-2009, 2010-2016, 2017-2024)` are REPORTED.

## 3. Primary metric — the ONE deciding number

`net_monthly_excess_vs_random_twin`: the mean over **monthly date blocks** of

    (book's net monthly return) - (turnover-matched random twin's net monthly return)

both legs net of the flat 25 bps-per-side interim ruler
(`cost_curve: flat_25bps_pending_5c`, `zero_cost_diagnostic=False`), NW lag-2 t
on the block series, at the **$3M primary floor**.

**The twin is drawn from the SAME COVERED POOL** — names carrying both
seasonality columns that month — so the book cannot beat its control by
requiring twenty years of tape the control does not have. The twin's turnover
is matched to the book's by the replay engine's own `_turnover_matched_draw`,
which also **discharges the research note's second proposed falsifier by
construction**: a shared turnover/liquidity confound between this book and Book
A cannot produce the difference, because the control rotates exactly as much as
the book does and is drawn from the book's own band. A falsifier satisfied by
construction is not run twice; it is named here and replaced by the ex-January
test in §5.

**Reported, never deciding:** the **$10M secondary floor** cell with its twin
re-drawn at that floor; the per-era split at both floors; the
`seas_2_5an` (years 2-5) variant as a lag-structure diagnostic; realised
turnover; median names selected; the family Holm block.

Two of the reported legs are **`FAILED_VARIANT` triggers** (§5).

## 4. Power — §64, computed BEFORE the confirmation

Receipt: `backend/data/optimus/first_books/mde_receipt.json`. Same k, same
engine, same monthly CRSP panel as Book C, so the same arithmetic:

| quantity | value |
|---|---|
| median cross-sectional monthly return sd | **0.167186** |
| k | 30 |
| implied book monthly sd (`cs_sd / sqrt(k)`) | 0.030524 |
| book-minus-twin monthly sd (`x sqrt(2)`) | **0.043167** |
| monthly blocks, nominal | **360** |
| **MDE at 80% power, alpha 0.05, two-sided, at 360 blocks** | **0.637%/month** |
| the same MDE deflated by the measured lag-1 rho 0.1268 (n_eff 278.98) | **0.724%/month** |

**Declared effect size: 0.65%/month** — barely above the nominal MDE, and
deliberately the most conservative of the family's three new books, because the
published ruler is SD-shaped and no mean spread was found to sanity-check
against. Both MDE figures are stated. **The MDE is recomputed from this book's
own realised difference series before the decision and the recomputation is
reported.** The independence caveat of TRIAL-DRAFT-A §4 applies: 0.637% is the
optimistic bound.

declared_effect_size: 0.65% mean net monthly excess of the top-seasonality-tercile book over a turnover-matched random twin drawn from the same covered band (barely above the nominal-360-block MDE of 0.637%/month, deliberately conservative because the published ruler is an SD and not a mean spread; the autocorrelation-deflated MDE is 0.724%/month and both are stated)
event_frequency_per_year: 12 (a monthly rebalance; 360 nominal monthly date blocks, n_effective 278.98 at the lag-1 rho of 0.1268 measured on this same panel for TRIAL-DRAFT-C; this book's own rho is re-measured from its own difference series before the decision)
outcome_dispersion: 0.0432 (the book-minus-twin monthly sd implied by a measured median cross-sectional monthly return sd of 0.167186 at k=30; the independence caveat above says this is the optimistic bound)
outcome_horizon_days: 21 (one trading month; seasonality is a single-month effect by construction and the book is re-formed every month)
dependence_unit: ONE CALENDAR MONTH of the whole cross-section -- the 30 names held in a month share the market and are not 30 independent draws, so one independent observation is one monthly book-minus-twin difference and never one name-month
cross_sectional_k: 30
cross_sectional_rho: 0.1938 (MEASURED, not assumed: mean pairwise correlation of monthly name returns over 1995-2024, 250 names, 31,125 pairs, seed 20260912 -- receipt backend/data/optimus/first_books/mde_receipt.json, the same panel and k this book uses)
slice_purpose: CONFIRM -- 1990-2024 is the whole read and the whole decision. No slice of these columns has been read by any Aegis session, so there is no earlier fit for a confirm slice to be disjoint FROM, and the draft says so rather than manufacturing a holdout
selection_window_note: none. The lag structure (11-15 and 16-20 years) was chosen BEFORE any read, from Heston-Sadka's own lag structure and from the requirement that it be mechanically disjoint from the 12-1 momentum window the arena already prices -- not from anything seen in this column's payoff. The 2026-09-13 alignment check measured which MONTH the column refers to; it did not look at the column's return
slice_securities: CRSP common stock above a $3M median dollar-volume floor and a $5 price minimum that ALSO carry non-null `seas_11_15an` AND `seas_16_20an` at that month's `eom` (i.e. roughly twenty years of tape); the twin is drawn from the identical covered band
slice_period: 1990-01-01 .. 2024-12-31
information_cutoff: the JKP panel's own `eom` formation stamp. Every input is the name's own past return at lags of 11-20 years, known entirely as of that close; the selection happens at the close and the earliest return it can touch is the following month's
selection_period: none
parent_trial: none
hypothesis_source: NONE -- the question comes from the published literature (Heston & Sadka, JFE 87(2):418-445, 2008) and from the 2026-09-13 research note's observation that JKP's own seasonality columns were already on disk and unread. No Aegis trial's OUTCOMES motivated it

## 5. Decision rule

Evaluated **once**, when the replay job's receipt exists. Earliest decision
date: immediately.

- **`PRODUCT_PROMISING`** — the $3M net block-mean >= +0.65%/month at NW lag-2
  t >= 2.0, **AND** both falsifiers pass, **AND** the sign is positive in at
  least 3 of the 4 reported eras, **AND** the $10M cell is also positive.
- **`FAILED_VARIANT`** — **any one** of:
  1. the $3M net block-mean over the registered slice is **<= 0**, whatever the
     falsifiers did;
  2. **the one-month-shifted placebo ALSO pays.** The same book built from the
     SAME columns read one month EARLIER on the same name (`eom = t-1`, which
     by §2's measurement is the *neighbouring* calendar month's seasonality and
     is strictly older information, so it is PIT-safe) must be indistinguishable
     from zero. If picking names on the wrong calendar month pays as well as
     picking them on the right one, what was measured is a persistent
     name-level premium and not a calendar effect, and the book is closed;
  3. **the whole effect is January.** The ex-January block mean must still
     carry NW lag-2 t >= 1.5. Heston-Sadka's own effect is strongest in
     Oct/Dec/Jan and tax-loss-selling reversal is a known January confound
     (Grinblatt-Han's own January table, cited in
     `research_overhang_literature_vs_book_c.md` §4). A book whose payoff lives
     entirely in one month of the year is a January book, and must be called
     one rather than "seasonality".
- **`CONDITIONAL`** — clears the primary metric but fails an era-stability or
  floor check, or NW t in [1.0, 2.0), or the block-mean lands between 0 and the
  declared effect.
- **`CANNOT_DETERMINE`** — a falsifier that could not be computed is not a
  falsifier that passed. If fewer than 24 January blocks are readable, clause 3
  is **untestable, not passed**, and the receipt says so in those words.
- **Contamination clause.** If the covered band (names carrying BOTH columns)
  in any year falls below 0.10 of that year's eligible names, or below 3 x k
  names in the median month of that year, the year is EXCLUDED and the
  exclusion is reported before the number is.
- **Crash override.** A decision that would land within six months of an SPY
  trough >= -20% is deferred to >= 6 months past the trough.

## 6. Frozen parameters

The selector `seasonality_11_20_v0` exactly as
`scripts/night_books_efg_replay.py` constructs it, hashed at the registration
commit. Also frozen: the two source columns `seas_11_15an` and `seas_16_20an`
and the requirement that BOTH be present; their equal-weight combination as
within-month cross-sectional z-scores; the **top tercile** cut; k = 30; a
monthly rebalance with a one-month holding period; the $3M primary and $10M
secondary floors; the $5 price minimum; the flat 25 bps per-side cost ruler;
the turnover-matched random twin drawn from the covered band; 1990-2024.

## 7. Corpse-check result

Run 2026-09-13 against **358 prior experiments**:

```
PASS   (n_required 347, n_available 1958, smallest resolvable effect 0.27pp)
R13e `CALENDAR_DISJOINT_BY_CONSTRUCTION`, R13f `NO_HYPOTHESIS_SOURCE_DECLARED`
```

`PASS` means UNMATCHED, not novel. `CALENDAR_DISJOINT_BY_CONSTRUCTION` is a
claim on the record: if any threshold, lag choice or universe in §6 was in fact
chosen after looking at this corpus, that declaration is false and the result is
not a confirmation.

## 8. What this rule may NOT do

- No lag search after the first read. `seas_1_1*`, `seas_2_5*` and
  `seas_6_10*` exist on the same panel and reading them for a better number
  would be four books wearing one registration's clothes. `seas_2_5an` is a
  REPORTED diagnostic and may not become the primary.
- No quoting the $3M-floor number as the result if the $10M cell disagrees;
  both are printed or neither is.
- No converting Heston-Sadka's 13.8% annualized SD into an implied monthly
  spread, and no restating it as this book's result.
- No dropping the January split or the shifted placebo because the primary
  metric alone looks good. They are triggers, not decorations.
- No `RESEARCH_CLAIM` from this registration alone.
- No reporting the book's absolute return as an alpha: the claim is a
  DIFFERENCE, and no LEVEL under a placeholder cost ruler may be quoted as
  measured.

## 9. Registry

`rule_experiments` row `seasonality-11-20-v0`, **not yet written** — the same
state TRIAL-DRAFT-A/B/C/D/E stand in. Signing is the attended step; this file
and its commit timestamp are the tamper evidence that the rule existed before
the read.
