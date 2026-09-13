# TRIAL-DRAFT-E — quality-minus-junk, long-only tilt (`qmj_quality_tilt_v0`)

**STATUS: UNSIGNED DRAFT.** Written 2026-09-13, before any read. It is not in
`rule_experiments` and has not incremented `cumulative_trials`: registration is
the attended step, and a draft that registered itself would make the attended
step decorative. Signing it is what starts the clock. This draft licenses a
`PRODUCT_EXPERIMENT` READ only; a `RESEARCH_CLAIM` stays attended.

**Family:** `NIGHT_JOB_BOOKS_2026_09_13` — **four** primary-metric tests, one
per book (E, F, G, and Book C's v1 re-read), sharing one multiplicity budget.
Holm runs across the declared four inside the job. Every other number any of
them computes is `SCREEN`-only under `PRODUCT_EXPERIMENT` licence and is
reported, never deciding. This is a NEW family, declared at size 4 before the
read; it does not extend `NIGHT_JOB_BOOKS_2026_09` (A, B, C, D), whose four
primaries are already read and whose budget is already spent.

**Licence:** `PRODUCT_EXPERIMENT`. Accrues zero capital. Places nothing.

## 0. Corpse check

`python scripts/lint_prereg.py <this file>` from `C:/Users/mrthn/Aegis module`
(verdict recorded in §7).

- **Resurrects: nothing refuted.** `ROADMAP...11c`'s banked-negatives list
  closes **betting-against-beta** ("BAB net alpha ~ 0") and `NEGATIVE_RESULTS`
  §24 closes a short-interest CHANGE feature. Neither is a quality sort. Gross
  profitability (`gp_at`) has never been read in this repository either, and is
  named here as a DIAGNOSTIC leg (§3) precisely so that "QMJ" cannot quietly
  turn out to be it.
- **New instrument:** the JKP characteristic panel already on disk —
  `backend/data/optimus/wrds/jkp_full/jkp_usa_*.parquet` (1926-2012, 32 files)
  and `backend/data/optimus/wrds/jkp_global_factor_usa.parquet` (2013-2024,
  558,369 rows). Its `qmj`, `qmj_prof`, `qmj_growth`, `qmj_safety` columns are
  Jensen-Kelly-Pedersen's own WRDS-contributed construction, PIT-stamped on
  `eom`, and **no book in this repository has ever read one of them**. Every
  earlier book (A, B, C, D) needed a panel built first; this one needed a
  schema read.

## 1. Hypothesis

> The top tercile of JKP's `qmj` composite, inside the $3M-dollar-volume,
> $5-price eligible CRSP cross-section restricted to names that CARRY a `qmj`
> score, beats a turnover-matched random-universe twin drawn from that same
> covered band by more than the MDE in §4, over monthly date blocks 1990-2024.

**Honest prior.** Asness, Frazzini & Pedersen (*Review of Accounting Studies*
24(1):34-112, 2019): the QMJ factor earns a Sharpe ratio of roughly 1 after
hedging other factors and is positive in 23 of 24 countries. **That published
number is a long-short, risk-hedged FACTOR Sharpe, not a raw monthly spread for
a long-only tercile tilt**, and the research note of 2026-09-13 (§2) records
that **no raw monthly-spread percentage was found** in the fetched sources —
marked NOT FOUND there and not filled in from memory here. So the prior is
directional ("quality has been paid, risk-adjusted, over a long sample") and
NOT a magnitude. A long-only tercile tilt captures a fraction of a hedged
long-short factor by construction, and McLean-Pontiff-style post-publication
decay applies on top. The design's threshold is §4's MDE, never the paper's
Sharpe.

## 2. The window, and why there is no separate confirm era

The read is **1990-2024**, the span of the CRSP daily files this repository
holds; the JKP columns themselves reach back to 1926 and are not the binding
constraint. There is no split into a reported era and a deciding era as in
TRIAL-DRAFT-A, because **there is no publication date to sit on either side
of**: AFP's own sample is long and overlapping, and inventing a post-2019
"confirm slice" of 60 blocks would buy a worse MDE and a fake OOS claim. The
four eras `(1990-1999, 2000-2009, 2010-2016, 2017-2024)` are the REPORTED
split, per the family's convention, and decide nothing except through §5's
era-stability clause.

The **coverage** of `qmj` is not uniform and the receipt prints it rather than
averaging over it: 0.765 of rows carry a `qmj` in 2013-2024 and 0.551 in
1990-1991 (measured from the parquet schemas on 2026-09-13, not assumed).

## 3. Primary metric — the ONE deciding number

`net_monthly_excess_vs_random_twin`: the mean over **monthly date blocks**
(canon §58 — names inside a month share the market) of

    (book's net monthly return) - (turnover-matched random twin's net monthly return)

both legs net of the flat 25 bps-per-side interim ruler
(`cost_curve: flat_25bps_pending_5c`, `zero_cost_diagnostic=False`), with a
Newey-West lag-2 t on the block series, at the **$3M primary floor**.

**The twin is drawn from the SAME COVERED POOL.** The eligible band is
restricted to names carrying a `qmj` score that month BEFORE the twin is drawn,
so the book cannot beat its control merely by requiring a characteristic the
control does not have. The twin's turnover is matched to the book's by the
replay engine's own `_turnover_matched_draw`, so the cost term cancels out of
the difference and the difference measures which names, not how often.

**Reported, never deciding:** the **$10M secondary floor** cell with its twin
re-drawn at that floor; the per-era split at both floors; the `qmj_prof`-only
profitability diagnostic; realised turnover; median names selected; the family
Holm block.

Two of the reported legs are **`FAILED_VARIANT` triggers** and not merely
diagnostics (§5).

## 4. Power — §64, computed BEFORE the confirmation

Receipt: `backend/data/optimus/first_books/mde_receipt.json`
(`scripts/first_books_mde.py`, built 2026-09-12). The dispersion inputs are the
ones measured there for **k = 30 on this same monthly CRSP panel**; this book
uses the same k and the same engine, so the arithmetic is the same arithmetic
and is not re-derived from a different sample here.

| quantity | value |
|---|---|
| median cross-sectional monthly return sd | **0.167186** |
| k | 30 |
| implied book monthly sd (`cs_sd / sqrt(k)`) | 0.030524 |
| book-minus-twin monthly sd (`x sqrt(2)`) | **0.043167** |
| monthly blocks, nominal | **360** |
| **MDE at 80% power, alpha 0.05, two-sided, at 360 blocks** | **0.637%/month** |
| the same MDE deflated by TRIAL-DRAFT-C's measured lag-1 rho 0.1268 (n_eff 278.98) | **0.724%/month** |

**Declared effect size: 0.70%/month**, one notch above the nominal-360 MDE and
inside the band the measured deflation implies. BOTH numbers are printed here
rather than only the flattering one, because a power check that quotes the
smaller of two figures it computed is decoration. **The MDE is recomputed from
this book's OWN realised difference series — its own block count and its own
measured lag-1 rho — before the decision is taken, and the recomputation is
reported on the receipt.**

The independence caveat of TRIAL-DRAFT-A §4 applies identically and in the same
direction: `cs_sd/sqrt(k)` assumes the 30 names' residuals are independent, they
are not, so 0.637% is the **optimistic** bound.

declared_effect_size: 0.70% mean net monthly excess of the top-qmj-tercile long-only tilt over a turnover-matched random twin drawn from the same qmj-covered band (one notch above the nominal-360-block MDE of 0.637%/month; the autocorrelation-deflated figure is 0.724%/month and both are stated)
event_frequency_per_year: 12 (a monthly rebalance; 360 nominal monthly date blocks, n_effective 278.98 at the lag-1 rho of 0.1268 measured on this same panel for TRIAL-DRAFT-C; this book's own rho is re-measured from its own difference series before the decision)
outcome_dispersion: 0.0432 (the book-minus-twin monthly sd implied by a measured median cross-sectional monthly return sd of 0.167186 at k=30; the independence caveat above says this is the optimistic bound)
outcome_horizon_days: 21 (one trading month; the book is re-formed monthly and the return earned is the following month's)
dependence_unit: ONE CALENDAR MONTH of the whole cross-section -- the 30 names held in a month share the market and are not 30 independent draws, so one independent observation is one monthly book-minus-twin difference and never one name-month
cross_sectional_k: 30
cross_sectional_rho: 0.1938 (MEASURED, not assumed: mean pairwise correlation of monthly name returns over 1995-2024, 250 names, 31,125 pairs, seed 20260912 -- receipt backend/data/optimus/first_books/mde_receipt.json. It is the same panel and the same k this book uses, which is why it is quoted rather than re-measured)
slice_purpose: CONFIRM -- 1990-2024 is the whole read and the whole decision. No slice of this characteristic has been read by any Aegis session, so there is no earlier fit for a confirm slice to be disjoint FROM, and the draft says that rather than manufacturing a holdout out of the last five years
selection_window_note: none. No threshold, tercile boundary or universe in this draft was chosen after looking at any Aegis result on this column: the `qmj` column has never been read by a book in this repository, and the construction below is JKP's own composite at the family's existing k, floors and price minimum. The 2026-09-13 research note that proposed the book read the parquet SCHEMA and the published literature, not the column's payoff
slice_securities: CRSP common stock above a $3M median dollar-volume floor and a $5 price minimum that ALSO carry a non-null JKP `qmj` score stamped at that month's `eom`; the twin is drawn from the identical covered band
slice_period: 1990-01-01 .. 2024-12-31
information_cutoff: the JKP panel's own `eom` formation stamp, which is the end of the month already closed; the selection happens at that close and the earliest return it can touch is the following month's. JKP's construction derives each characteristic from data public by its `eom` (the panel's own meta.json states it)
selection_period: none
parent_trial: none
hypothesis_source: NONE -- the question comes from the published literature (Asness, Frazzini & Pedersen, Review of Accounting Studies 24(1):34-112, 2019) and from the 2026-09-13 research note's observation that the JKP characteristic panel was already on disk and unread. No Aegis trial's OUTCOMES motivated it

## 5. Decision rule

Evaluated **once**, when the replay job's receipt exists. Earliest decision
date: immediately — this book needs no forward waiting, only the panel that is
already on disk.

- **`PRODUCT_PROMISING`** — the $3M net block-mean >= +0.70%/month at NW lag-2
  t >= 2.0, **AND** both falsifiers pass, **AND** the sign is positive in at
  least 3 of the 4 reported eras, **AND** the $10M cell is also positive.
- **`FAILED_VARIANT`** — **any one** of:
  1. the $3M net block-mean over the registered slice is **<= 0**, whatever the
     falsifiers did (TRIAL-DRAFT-A §5's clause, carried in from the start here
     rather than patched on afterwards as Book C's Amendment 1 had to be);
  2. **the junk leg does not lose.** The bottom-`qmj`-tercile book, run through
     the same engine against the same twin at the same floor, must have a
     NEGATIVE net excess. If quality and junk BOTH beat the twin, the sort is
     not ordering anything and what was measured is the covered band, not the
     characteristic;
  3. **`qmj` dies under the size/beta control.** In a Fama-MacBeth
     cross-sectional regression of next month's return on `z(qmj)`,
     `z(log market_equity)` and `z(beta_60m)` over the same universe, `qmj`'s
     own payoff must survive at |t| >= 2.0. If it does not, the tilt is size and
     beta in quality's clothing.
- **`CONDITIONAL`** — clears the primary metric but fails an era-stability or
  floor check, or NW t lands in [1.0, 2.0), or the block-mean lands between 0
  and the declared effect.
- **`CANNOT_DETERMINE`** — a falsifier that could not be computed is NOT a
  falsifier that passed. If `qmj`'s own RAW payoff is not alive in the
  Fama-MacBeth (|t| < 2.0 before any control is added), clause 3 is
  **untestable, not passed**, and the receipt says so in those words. This is
  the lesson of 2026-09-13: Book C's momentum falsifier "passed" with raw
  momentum at t 0.15 — nothing was alive to subsume.
- **Contamination clause.** If `qmj` coverage inside the eligible band in any
  year falls below 0.25 of that year's eligible names, the year is EXCLUDED and
  the exclusion is reported before the number is.
- **Crash override.** A decision that would land within six months of an SPY
  trough >= -20% is deferred to >= 6 months past the trough.

## 6. Frozen parameters

The selector `qmj_quality_tilt_v0` exactly as
`scripts/night_books_efg_replay.py` constructs it, hashed at the registration
commit. Also frozen: the source column `qmj` (JKP's own composite of
`qmj_prof + qmj_growth + qmj_safety`, not a re-weighting of them); the **top
tercile** cut; k = 30; a monthly rebalance with a one-month holding period; the
$3M primary and $10M secondary floors; the $5 price minimum; the flat 25 bps
per-side cost ruler; the turnover-matched random twin drawn from the covered
band; the 1990-2024 slice.

## 7. Corpse-check result

Run 2026-09-13 against **358 prior experiments**:

```
PASS   (n_required 299, n_available 1958, smallest resolvable effect 0.27pp)
R13e `CALENDAR_DISJOINT_BY_CONSTRUCTION`, R13f `NO_HYPOTHESIS_SOURCE_DECLARED`
```

`PASS` means UNMATCHED, not novel: the linter compares wording against the
graveyard, the registry and the prereg corpus, and knows nothing about the
literature. The nearest neighbours it finds are corpses to respect, not results
that motivated this one.

`CALENDAR_DISJOINT_BY_CONSTRUCTION` is a **claim on the record**: it says no
prior fit was declared, so there is no selection window to overlap. If any
threshold, tercile boundary or universe in §6 was in fact chosen after looking
at this corpus, that declaration is false and the result is not a confirmation.

## 8. What this rule may NOT do

- No prompt, parameter or tercile search after the first read.
- No quoting the $3M-floor number as the result if the $10M-floor cell
  disagrees; both are printed or neither is (TRIAL-DRAFT-A §8's rule, same
  reason: a book quoted at the floor that flatters it is a book quoted at a
  chosen corner).
- No restating AFP's published Sharpe of ~1 as this book's result, and no
  converting it into an implied monthly spread — the research note marked that
  number NOT FOUND and it stays not found.
- No swapping `qmj` for `qmj_prof`, `gp_at` or any sub-score inside this
  registration. That is a separate amendment naming only the input, exactly as
  TRIAL-DRAFT-C §8 requires of Book C's event sign.
- No `RESEARCH_CLAIM` from this registration alone — that needs the family's
  four primary metrics under Holm, matched controls, a holdout and the
  24-month floor.
- No reporting the book's absolute return as an alpha: the claim is a
  DIFFERENCE against a twin, and under a placeholder cost ruler no LEVEL from
  this job may be quoted as measured.

## 9. Registry

`rule_experiments` row `qmj-quality-tilt-v0`, **not yet written** — the same
state TRIAL-DRAFT-A/B/C/D stand in. Signing is the attended step; this file and
its commit timestamp are the tamper evidence that the rule existed before the
read.
