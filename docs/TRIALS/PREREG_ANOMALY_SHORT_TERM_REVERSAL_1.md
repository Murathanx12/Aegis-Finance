# PREREG — ANOMALY-SHORT-TERM-REVERSAL-1

**Status: UNSIGNED.** Family `PUBLISHED_ANOMALIES_2026`, week 1 of the
eight-anomaly cadence (`scripts/night_anomaly_adjudicate.py`). Registered
BEFORE any cell of this construction has been graded on our tape. A session
may not run the primary until this file is SIGNED by Murat; the smoke run
recorded in the receipt is a plumbing check on a two-year window with its
verdict field forced to `SMOKE_NOT_A_VERDICT`, and it is excluded from the
primary's evidence by construction.

Origin: roadmap §11a, the weekly published-anomaly cadence modelled on
Fidetolabs Notes — pick one published quant-finance result, preregister the
plan BEFORE loading data, test it on our tape from scratch, and publish the
negative weeks with the same prominence as the positive ones.

## Question

Does the SHORT-TERM REVERSAL effect — Jegadeesh (1990), "Evidence of
Predictable Behavior of Security Returns", *Journal of Finance* 45(3), and its
long line of successors — survive on the Aegis CRSP universe, net of declared
costs, in the eras we can measure?

The published claim is GROSS and is a PRIOR, never an Aegis receipt: last
month's losers outperform last month's winners over the following month. Two
things are known to attack it in the direction of zero and both are in the
primary rather than in a footnote: the effect is concentrated in small,
illiquid names (our universe screen is a liquidity screen), and its turnover is
monthly at full book (our cost model charges it).

## Data

- `backend/services/portfolio_farm/panel.py`, CRSP daily, the years present on
  this checkout (1990-2024, 32 replayable). PIT universe: the
  `universe_n`-most-liquid eligible names by TRAILING dollar volume at each
  formation date, `min_price` floor applied at formation. No survivorship
  reconstruction, no name known before it was listed.
- No new data build. That is why short-term reversal is week 1: a cadence
  whose first week blocks on a data pull is a cadence that does not start.

## Primary (ONE deciding cell)

- **Construction, frozen from the paper, not re-optimised:** at each monthly
  formation date rank the eligible universe by the trailing 1-month return
  return and hold the BOTTOM decile -- i.e. BUY the losers -- equal-weighted
  for one month. The engine's existing `reversal_1m` signal IS that sort (it
  returns the NEGATED trailing month return, so its top-k are the month's
  worst performers); no new signal is written for this trial, because a signal
  written for a replication is a degree of freedom the replication does not
  get. Parameters:
  `holding_days=21`, `phase_offset=0`, `top_k = universe_n // 10`,
  `universe_n=500`, `min_price=5.0`, `max_single_name=0.20`.
- **Deciding number:** net Sharpe of the reversal book MINUS the net Sharpe of
  its DRIFT-ONLY control on the same dates, same universe, same costs. The
  control is the same construction with the sort variable replaced by
  `oldest_listing` — a book that holds the same NUMBER of the same KIND of
  names and trades on the same calendar, so the difference isolates the sort
  and not the exposure to being in the market at all.
- **Costs are never omitted.** Declared at signature; the grid the receipt
  carries is `flat 5+1 bps`, `flat 25+5 bps` and `taq_empirical`, and the
  PRIMARY is `taq_empirical` (the measured curve). A result that exists only
  at 6 bps is reported as such.
- **Eras, declared now:** 1990-2001, 2002-2012, 2013-2024. The verdict needs
  2 of 3 eras with the same sign, which is `evidence_memory`'s own existing
  bar, imported rather than restated.
- **Multiplicity:** this is one primary cell in a family of eight anomalies;
  the family is `PUBLISHED_ANOMALIES_2026` and EXPORT-level significance is
  Holm over the eight (§63), computed when the eighth week closes, not
  per-week.

## §64 POWER, BEFORE ANY MEAN WAS SEEN

Declared now, from the tape's own dispersion and the trial's own cadence, so
that nobody — including its author — can discover months later that this
design could never have resolved its claim.

Machine-readable, in the form `lint_prereg.py` parses (R13):

- event_frequency_per_year: 12
- declared_effect_size: 0.60pp
- outcome_dispersion: 3.95pp
- corpus_years: 35
- outcome_horizon_days: 21
- dependence_unit: one monthly formation date for the WHOLE book -- the book holds a decile of one universe, so the names inside a month are one observation and not fifty
- cross_sectional_k: 50
- cross_sectional_rho: 0.35
- slice_purpose: FOREIGN
- slice_securities: CRSP US common stocks, the 500 most liquid eligible names by trailing dollar volume at each formation date
- slice_period: 1990-01-01 .. 2024-12-31
- information_cutoff: the formation date itself -- trailing data only, no value known before it was public
- selection_period: none
- parent_trial: none
- hypothesis_source: Jegadeesh (1990), Evidence of Predictable Behavior of Security Returns, Journal of Finance 45(3)
- hypothesis_source_period: 1929-01-01 .. 1982-12-31

`slice_purpose = FOREIGN` and not CONFIRM, deliberately. The hypothesis was
raised on somebody else's sample and this run is still LOOKING: a positive
week here is a replication on our universe and era, never independent
confirmation of the published effect, and the trial gives up that claim in
advance rather than reaching for it after a good number. The source window
(1929-1982) is disjoint from our slice (1990-2024), which is a fact worth
having on the record either way.


And in words, because the numbers above are the claim and not a formality:

- `declared_effect_size` **0.60pp per month** (about 7.4%/yr, or **0.53 annual
  Sharpe** at the dispersion below) is the smallest advantage over the
  drift-only control this design can actually resolve at 80% power on the
  history that exists. It is NOT the economic bar.
- **The economic bar is 0.25 annual Sharpe and it does not move.** It sits
  BELOW the resolvable floor, so it is declared NOT_ANSWERABLE_AT_N here and
  now: a real reversal effect worth 0.25 Sharpe will come back
  `CANNOT_DETERMINE` from this design, and that is a fact about the sample,
  not a null. Shrinking the bar to make the verdict reachable is the move this
  declaration exists to prevent.
- `outcome_dispersion` **3.95pp monthly** (13.7%/yr) is MEASURED on the
  drift-only control book alone, on 2013-2016, with the primary's mean never
  computed. It is an UPPER BOUND on the paired difference's dispersion,
  because the market factor cancels in a paired read and does not cancel here.
  If the realised paired dispersion comes in at half of this -- plausible --
  the resolvable floor halves with it and the run REPORTS the realised number
  beside this declared one rather than quietly re-deriving the bar.
- `cross_sectional_rho` 0.35 is the declared average pairwise correlation of
  the names inside one monthly book; with `cross_sectional_k` 50 that is why
  the dependence unit is the MONTH and not the name-month.

- `declared_effect_size (in words)`: **0.25 annual net Sharpe** of advantage over the
  drift-only control (the economic bar above). It never shrinks.
- `event_frequency_per_year`: **12** formation dates a year (monthly
  rebalance, `holding_days=21`), i.e. ~420 monthly observations pooled over
  1990-2024 and ~140 per era.
- `outcome_dispersion`: **0.0395 monthly** (13.7%/yr) — measured on the
  DRIFT-ONLY CONTROL book alone, on 2013-2016, with the primary's mean never
  computed. It is an UPPER BOUND on the dispersion of the paired difference,
  because the market factor cancels in a paired read and does not cancel here;
  the realised paired dispersion is reported at run time beside this number.

**MDE at that dispersion:** 2.8 sigma / sqrt(n) gives 0.54%/month pooled
(6.7%/yr, i.e. **0.47 annual Sharpe**) and 0.94%/month per era (**0.82 annual
Sharpe**).

**Therefore, declared prospectively:** the 0.25 bar sits BELOW the pooled MDE
upper bound, so `REPLICATES` is ANSWERABLE only if the paired difference's
realised dispersion comes in at roughly half the control's or less — which is
plausible for a paired read and is MEASURED at run time, not assumed. If it
does not, the answerable verdicts are `DOES_NOT_REPLICATE` (a sign test the
era rule can still carry) and `CANNOT_DETERMINE`, and the run says so instead
of reporting a null as evidence of absence. The bar is not lowered to make a
verdict reachable.

## Decision rule (committed before any data is loaded)

| verdict | condition |
|---|---|
| `REPLICATES` | net Sharpe difference vs the drift-only control > 0 in ≥ 2 of 3 eras AND DSR > 0.95 at the family trial count AND PBO < 0.5 |
| `REPLICATES_GROSS_ONLY` | the same is true GROSS and fails NET at the primary cost curve |
| `DOES_NOT_REPLICATE` | the difference is ≤ 0 pooled, or fails the era rule |
| `CANNOT_DETERMINE` | the window cannot carry the test (MDE above the economic bar, or fewer than 2 eras with enough formation dates) |

- Economic bar: **0.25 net Sharpe** of advantage over the drift-only control.
  The bar never shrinks.
- Earliest decision date: the first run AFTER this file is signed. There is no
  forward accrual to wait for — this is a replay over a closed history — so the
  tamper evidence is the commit timestamp of this file against the commit
  timestamp of the receipt, and nothing else.
- Contamination clause: if the panel for any era is found to be missing a
  required column (`panel.replayable_years` shrinks), that era is reported
  ABSENT and the verdict falls back to `CANNOT_DETERMINE` rather than being
  decided on the eras that happen to be loadable.

## Frozen parameters

`holding_days=21`, `phase_offset=0`, decile cut, `universe_n=500`,
`min_price=5.0`, `sizing=equal_weight`, `max_single_name=0.20`, the three era
boundaries, the drift-only control's identity (`oldest_listing`), and the
primary cost curve (`taq_empirical`). None may be tuned after the first graded
cell. A variant of any of them is a SCREEN cell, reported and never deciding.

## SCREEN (reported, never deciding)

Quintile instead of decile; the long-short (bottom minus top) rather than the
long leg; `holding_days` in {5, 21, 63}; the other two cost regimes; the
`decay` axis. BH-FDR 0.10 over the screen cells actually run.

## May NOT

- Feed any lane, arm or book. This is a `RESEARCH_CLAIM`-track replication of
  a published result, and a replication that clears its bar licenses a
  `PRODUCT_EXPERIMENT` book with its own frozen contract — never a position.
- Be quoted gross. A gross-only replication is reported as
  `REPLICATES_GROSS_ONLY` with the cost that killed it named.
- Be re-run with a different sort variable under this trial's name. A different
  construction is a different anomaly and gets its own week and its own file.

## Hard constraint — THE NEGATIVE WEEK IS PUBLISHED

A week whose anomaly does NOT replicate writes to `NEGATIVE_RESULTS.md` with
the same prominence as a week that does, per canon and CLAUDE.md rule 4. The
cadence's value is the ratio of published to replicated, and a cadence that
quietly drops its failures reports a ratio of 1.

— design registered 2026-09-12; priors: STRONG for the gross effect
(thirty-five years of literature), UNKNOWN net of our costs on our liquidity
screen, and the two known attacks (small-cap concentration, monthly full-book
turnover) are both pointed at the net number.
