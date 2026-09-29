# TRIAL-PT-REVERSAL-1: after an analyst price-target change, the next session moves AGAINST the stated direction (pre-registered decision rule)

> Pre-registered 2026-09-29, **before** the 2025 cells it will be read on are converted and
> before any 2025 outcome is joined to a price-target label. The file's SHA-256 and a UTC
> timestamp are recorded in `backend/data/optimus/ft_lab/receipts/pt_reversal_registration.json`
> BEFORE the conversion job is launched. This file is not committed in this session (the
> instruction was no commit); the receipt hash is the tamper evidence until it is. Changing
> anything below after the read invalidates the trial; a successor gets a new id.

Licence: `PRODUCT_EXPERIMENT` for any paper log that follows; this read licenses **no claim**.
A pass makes it a forward candidate, nothing more. Not registered in `rule_experiments`
(no backend edit was allowed in this session); owed when the file is committed.

## Where the lead comes from, and why it is a hypothesis

`docs/research_notes/2026-09-29/ft_lab_first_run_2026-09-29.md` (afternoon §3),
`backend/data/optimus/ft_lab/receipts/bulk_analysis.json`,
`conditional.drift_by_type.h1.types.analyst_target_change`.

On the TEST block (entry 2026-05-15..09-28), for the 543 cells the typed-event student labelled
`analyst_target_change` with a non-zero direction, the return in the student's direction was
**-0.34% gross, -0.54% net of 20 bps (t -2.74, MDE 0.55%, 21 weekly blocks, 0 of 5 months
positive)**. The type was NOT selected on the validation block, where the same trade was
**-0.19% net (t -0.67, MDE 0.79%), i.e. gross about +0.01%**: the validation block shows no
reversal.

**Multiplicity carried: 38 looks** (19 event types x 2 horizons) on the test block. A t of
-2.74 does not survive Bonferroni over 38 two-sided looks (|t| about 3.2 at 5%). The test block
is therefore spent: it generated the hypothesis and cannot confirm it.

**What the tradable version actually is.** The losing side is the "follow" trade. The trade
this trial tests is the FADE, whose test-block result was **+0.34% gross, +0.14% net of 20 bps**:
it barely clears the assumed cost even where it was found. September 2026 alone (gross fade
about +1.25%) carries a large share of the mean; the other four months were about +0.18..+0.35%
gross.

**Honest prior: weak.** Validation shows nothing; the test effect is partly one month; the
economically relevant net is small. The literature on price-target revisions reports modest
drift in the revision's direction over longer windows; a one-session reversal is the opposite
claim at a different horizon. A null is the expected outcome.

## Hypothesis

For 2025 news cells where the typed-event student reads an analyst price-target change with a
stated direction, the SPY-relative open-to-close return of the first session whose open follows
publication is, on average, opposite in sign to the stated direction.

## Exact construction (frozen)

- **Label source**: `ft_lab/data/bulk_events.jsonl`, rows with
  `source == "panel_cell_first_doc"`, `split == "train"`, `valid == true`, model
  `qwen2.5-1.5b-instruct+ft_lab/extract_qwen15_lora/last` (the frozen adapter; no retrain before
  the read). The label is the student's reading of the cell's FIRST document only.
- **Event**: `event_type == "analyst_target_change"` and `direction in {-1, +1}`
  (`direction == 0` rows are excluded, as on the test block).
- **Cell**: one (symbol, entry_date) of `ft_lab/data/cells.parquet` with `split == "train"`
  (entry 2025-01-02..2025-12-31), joined on (`first_uid`, `symbol`).
- **Entry**: the OPEN of `entry_date`, the first session whose open is after publication
  (the panel's definition; pre-bell stories enter the same day's open).
- **Exit**: the CLOSE of the same session.
- **Return**: `x_oc` from `cells.parquet` = the stock's open-to-close minus SPY's open-to-close
  (SPY-hedged, one session).
- **Position**: FADE, `R = -direction * x_oc` (gross).
- **Costs**: 20 bps round trip on the stock leg: `net20 = R - 0.0020`.
  Spread sensitivity (reported; the 40 bps line is part of the forward-log gate):
  `net40 = R - 0.0040`, `net60 = R - 0.0060`.
- **Aggregation**: per entry_date mean of R across that date's events; the statistic is the
  mean over dates (`ft_lab.evaluate.block_stats`).
- **Clustering**: SE from weekly date blocks (`W-FRI` weeks), `t = mean / SE`,
  **MDE = 2.8 x SE** printed beside every t.
- Cells with `x_oc` missing are dropped and counted. No winsorising, no filter on price,
  liquidity or size (none was applied on the test block).

## The untouched sample

- 2025 train block: **79,435 cells** (entry 2025-01-02..2025-12-31). At registration
  **13,608** are converted by the student and **65,827** are not.
- **Not looked at for this question.** `ft_lab/analyze_bulk.py` reads val and test cells only.
  The 2025 cells were used earlier only for SIZE (|move|) models: DeepSeek typed-field dummies
  (including `ev_analyst_target_change`) and `|direction|` as ridge features on |x_oc|
  (`baselines.json`), and event-type SHARES (`dataset.json`). No signed return has been joined
  to a direction label on the 2025 block for any event type. The 13,608 already-converted 2025
  rows have not been opened for this question; they enter the read on the same footing as the
  rest.
- **Conversion order** for the remaining cells (text only, no outcomes): 2025 cells whose first
  document's title+body matches a price-target keyword regex go first
  (`ft_lab/bulk_pt_priority.py`), then the other 2025 cells, each group in the queue's existing
  random order. The keyword only orders the queue; the event is defined by the student's label.
- **The read uses every 2025 cell converted by 20:30 local (12:30Z) on 2026-09-29.** Coverage
  (converted / total, and converted / keyword-matched) is printed with the result.
- **Minimum to read**: >= 300 directional PT cells and >= 30 weekly blocks. Counting these uses
  labels only, never outcomes. If the minimum is not met, the read is NOT performed and waits
  for more conversion (the read is not consumed).

## Primary statistic (the ONLY deciding number)

Mean over 2025 entry dates of the per-date mean gross fade return R, with its weekly-block t
and MDE. The net lines, by-month table, leave-one-month-out and direction split are reported;
the economic gate below uses the net lines.

**Ex-ante MDE.** The test block gave SE about 0.20% on 543 cells / 21 blocks. With about 2.1% of
cells carrying a directional PT label (the test-block share), a fully converted 2025 block gives
about 1,700 cells on about 52 blocks: SE about 0.13%, **MDE about 0.35-0.40%**, roughly equal to
the test-block gross effect (0.34%). Power to confirm an effect of the test-block size is
therefore only about 50%; a true effect of the validation-block size (about 0) is undetectable.
Stated before the read.

Power fields (all from the spent test block, none from 2025):

- `declared_effect_size`: +0.34% gross fade per event, one session (+0.14% net of 20 bps).
- `event_frequency_per_year`: about 1,700 directional PT cells per fully converted year
  (543 of 25,365 test cells = 2.1%, x 79,435 cells in 2025); 399 raises : 144 cuts on test.
- `outcome_dispersion`: per-cell sd of the fade return 3.31% (test block, 543 cells).
  i.i.d. SE with 1,700 cells would be 0.08%; the weekly-block SE is larger because events
  cluster by date, hence the 0.13% used above.

Machine-readable (R13):

- declared_effect_size: 0.34pp
- event_frequency_per_year: 1700
- outcome_dispersion: 3.31pp
- outcome_horizon_days: 1
- dependence_unit: calendar week (date blocks; events on the same dates share market news)
- corpus_years: 1

**Corpse check / R13 linter (`Aegis module/scripts/lint_prereg.py`, run before hashing):
`UNPOWERED_AT_REGISTRATION`.** No corpse match (nearest: PREREG_REVISION_FORECASTER_1 at
0.19 similarity). The linter caps one year of 1-day outcomes at 252 independent windows and says
the smallest resolvable effect is **0.58pp**, above the declared 0.34pp. Its cap treats every
event on a date as one observation; the block estimate above (MDE about 0.35-0.40%) credits
some cross-sectional averaging. Both say the same thing: **this one-year read is at best
marginally powered for the effect it was found at.** It is run anyway, as a `PRODUCT_EXPERIMENT`
read costing $0, because the decision rule already routes an underpowered positive to
`CANNOT_DISTINGUISH` and only a positive with t >= 2 can advance it. This is a stated deviation
from the linter's refusal; a `RESEARCH_CLAIM` could not be registered on this design.

## Decision rule (one read, exactly once)

Let m, t, MDE be the primary statistic on 2025.

| outcome | condition | verdict |
|---|---|---|
| existence confirmed | m > 0, t >= 2.0, >= 7 of 12 calendar months with positive gross mean, and leave-one-month-out worst m > 0 | `CONDITIONAL_POSITIVE` (gross reversal exists) |
| ...and tradable | above, AND net20 mean >= +0.10% with net20 t >= 2.0, AND net40 mean > 0 | register a forward PAPER log (`PRODUCT_EXPERIMENT`, frozen contract, next-open entry); nothing else |
| exists, not tradable | existence confirmed, economic gate fails | `CONDITIONAL_POSITIVE` gross, `DEPRIORITIZED` as a trade |
| underpowered | m > 0 but t < 2.0 (or the month / LOO condition fails) and MDE > 0.34% | `CANNOT_DISTINGUISH` |
| refuted at this power | m <= 0, or (t < 2.0 and MDE <= 0.34%) | `FAILED_VARIANT` (this construction, this student); lead `RETIRED_FROM_CURRENT_SEARCH` |

The threshold t >= 2.0 is one-sided about 2.5%: the 2025 read is a single pre-registered test on
a sample outside all 38 looks, so no further multiplicity correction is applied to it. The 38
looks are the reason the test block cannot be used as evidence, not a correction on 2025.

**Not permitted after the read:** changing the horizon (5 sessions was one of the 38 looks and
is reported only), splitting by direction or by magnitude to rescue a null, restricting to a
subset of months, adding a liquidity filter, or swapping the student for DeepSeek labels. Any of
these is a new trial on a new sample.

## Reported, never deciding

By month (gross, net20); leave-one-month-out worst; raises vs cuts separately; share of the
total carried by the 5 largest dates; n cells, n dates, n blocks; the 5-session fade (entry open
to 5th close, minus SPY) as a descriptive line only.

## What would count as refutation

A non-positive gross mean on 2025, or a positive but insignificant mean with MDE at or below the
test-block effect (0.34%), refutes the one-session fade for this label source. It closes this
implementation (the student's price-target reading, first document, next session), not
price-target information in general (`MECHANISM_REJECTED` is not available from one year).

## What this rule may NOT do

- It may not place an order, seed a lane, or enter any book; a pass licenses only the
  registration of a forward paper log.
- It may not be described as alpha, a signal, or "predicts" anywhere it surfaces before a
  forward record exists.
- It may not be re-read on 2025 with a different construction.

## Execution caveat (stated before the read)

This is a short-horizon reversal that needs execution AT THE OPEN, on names with a news story
that morning, where opening spreads are widest. The 20 bps round trip is optimistic at the
auction for the smaller names; the 40 and 60 bps lines are there because real spreads may take
the whole effect.
