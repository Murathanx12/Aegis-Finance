# TRIAL-H5 — the event-level learner at a five-session hold (pre-registered decision rule)

**Registered 2026-09-09 by Fable 5.1 on Murat's delegation ("you can do them
as well, do them"), BEFORE any further N1 configuration is run, any seal, any
paper arm, or any holdout read beyond the one printed in
`night_factory_2026-09-08/N1_train_reaction_learner_run02.json`.**
**Family:** event-clock learner on IBES announcements (N1), 4 holds × 3 feature
sets × 13 seeds = 156 configurations already looked at. **Licence:**
`RESEARCH_CLAIM` candidate; until it passes, `PRODUCT_EXPERIMENT` shadow only.
**Accrues zero arms. Places nothing.**

## 0. Corpse check

`python scripts/lint_prereg.py <this file>` from `C:/Users/mrthn/Aegis module`
(result recorded in §6).

- Resurrects: R4 §9 / D1 / D3 / D4 (the earnings-REACTION long leg and the
  long-short: `CONSTRUCTION_SENSITIVE` at 25 bps, alive only below the $10m/day
  floor, decay 21%/yr t 2.74) — new instrument: the object here is not the raw
  reaction rank but a LightGBM learner over every PIT event feature, trained
  purged-walk-forward with an embargo equal to the horizon, and its own
  placebo-trained control (the identical pipeline trained and traded on the
  +40-session placebo tape). D4's floor and cost grid apply to it unchanged.
- Resurrects: N1's pre-specified primary `H21|all|s0` (FAILED, t 0.604). H5 was
  found AFTER that failure among 156 configurations; this registration exists
  because the search that found it cannot also certify it.

## Hypothesis

An event-level learner (LightGBM, 400 trees, NaN native) trained on IBES
announcements with every PIT feature of D1's event frame (reaction, z-scored
reaction, PIT rank, SUE, liquidity, 60-day vol, 12-1 momentum, volume surge,
size, price, gap to the prior print), predicting the five-session market-excess
return from the close of session +1, traded long-short (top vs bottom decile of
its PIT-ranked prediction) above the $3m/day floor at 25 bps a side, earns a
β-matched excess over its placebo-trained control that is positive, era-stable,
and survives borrow cost and a drawdown budget.

**Honest prior, from the search that found it (13 seeds, 2004-2024):**
long-short +44.5%/yr t 4.31 pooled; control −3.1%/yr t −0.45; learner minus
control +32.2%/yr t 2.92; eras +29.2 / +71.7 / +35.2 %/yr; holdout 2016-2024
(read once, chose nothing) +28.3%/yr t 1.42; control fires in 0/13 seeds. **Also
from the same search:** max drawdown −78% at 46% annualised volatility; the
short leg carries NO borrow cost; 39 of 156 configurations clear t 2
uncorrected; the long-short's cost-floor behaviour is untested (D4 measured the
raw reaction, not the learner). The prior on the *claim* is therefore weak: a
five-session short leg in small caps is where D4 found the survivors to be
microstructure.

## Power (R13: declared before the read, so a null can be told from a blind test)

The observation unit is one MONTHLY date block of the calendar-time long-short
book (overlapping five-session positions inside a month are one observation),
so every field below is per month, and the corpus is the 2004-2024 purged
walk-forward read.

- slice_purpose: REANALYSIS
- parent_trial: N1_train_reaction_learner (night_factory_2026-09-08, 156 configurations, primary H21 FAILED)
- selection_period: 2004-01-01..2024-12-31
- evaluation_window: the same 2004-2024 read ONCE with the $10m floor and borrow (REANALYSIS), then a 12-month forward leg from the first seal after adoption (the CONFIRM slice)
- event_frequency_per_year: 12
- corpus_years: 21
- outcome_horizon_days: 5
- dependence_unit: one monthly date block of the long-short book; ~1,000 positions a year collapse into 12 blocks
- outcome_dispersion: 14.5 pp per month
- declared_effect_size: 2.6 pp per month

Where those come from: the search printed learner-minus-control +32.2 %/yr at
t 2.92 over ~252 blocks, i.e. an annualised standard error of 11.0 %/yr and a
monthly sd of 0.145. At 80 % power and α 0.05 the 252 blocks resolve an effect
of about 2.6 pp/month (≈ 31 %/yr) and nothing smaller. So the smallest effect
worth acting on is declared at that size, not at the +8-20 %/yr a tidier book
would deserve: a −78 % drawdown, 46 %-vol, five-session short book is not worth
running for less, and the read cannot see less. Anything between +4 %/yr and
+31 %/yr is CONDITIONAL, reported, and sent to the forward leg unadopted.

## Decision rule

- **Primary metric (the only deciding metric):** `learner_minus_control`
  β-matched annualised excess on monthly date blocks, **at the $10m/day floor,
  with a borrow line of 100 bps/yr on the short leg's notional**, over the
  full purged walk-forward 2004-2024, for the FROZEN configuration
  `H5|all`, seeds 0-12 pooled (one number: the seed-median).
- **Adopt (historical screen → forward leg) threshold:** seed-median ≥ +31.0%/yr (the declared effect) AND Newey-West t ≥ 2.8 AND the
  same sign in each of the three eras (1999-2007 is empty for a 2004 start;
  the eras are 2004-2007 / 2008-2015 / 2016-2024) AND max drawdown of the
  long-short ≥ −45% AND the RW2 random-window excess win rate over the
  random-genome null ≥ +0.15 in every start era.
- **Reject threshold:** seed-median < +4.0%/yr (below one standard error of zero), OR t < 1.5, OR the placebo
  control's own seed-median > +4.0%/yr (the machinery manufactures the
  spread), OR the $10m floor removes more than half of the $3m-floor excess.
- **Minimum window / earliest decision:** the historical read above is one
  computation and may be run ONCE, by a named job (`N1H5_prereg_read`), after
  this file's commit. If it adopts, the FORWARD leg starts: a zero-capital
  shadow book (`nn_shadow` pattern) from the first seal after adoption,
  **minimum 12 months forward, earliest capital question 2027-09-09**, judged
  quarterly on the same primary metric against the same control.
- **Frozen parameters:** hold 5 sessions; entry at the close of session +1;
  feature set `all` as listed in `night_factory_jobs.FEATSETS["all"]`; LightGBM
  400 trees with N1's hyper-parameters; purged walk-forward by year, embargo =
  5 sessions, first test year 2004; PIT rank window 63 sessions, pool ≥ 200;
  top and bottom deciles; 25 bps a side; borrow 100 bps/yr; floors $3m (report)
  and $10m (decide).
- **Secondary metrics (reported, never deciding):** the $3m-floor numbers,
  each seed alone, gross beside net, turnover, the long and short legs
  separately against their own controls, IC by year, the 10 bps and 5 bps
  cost lines.
- **Crash-event override:** if SPY draws down ≥ 20% from its in-window peak
  during the forward leg, no decision until ≥ 6 months past the trough.
- **Contamination clause:** any defect in the event tape (a share-basis or
  timestamp error of the R4 kind) voids the read; the tape is rebuilt, the
  read is re-run once, and the registration date moves to that commit.

## What this rule may NOT do

No metric substitution (the primary is the control-differenced, borrow-charged,
$10m-floor number, not the +44.5% pooled raw line). No re-selection of the hold
or the feature set after this file. No holdout re-read beyond the one already
printed. No "adjusting for regime". No buy/sell language, no seal, no capital
until the forward leg passes. If the historical read rejects, the trial is
recorded REJECTED with both numbers and the configuration goes to
`NEGATIVE_RESULTS.md`; the same instrument is not re-run.

## Registry

`rule_experiments` row `TRIAL-H5-event-learner-five-session`, decision rule in
`notes`, registered on first run (idempotent). Until the row exists, this
document alone is the commitment; its git commit timestamp is the evidence.

## 6. Corpse-check result

`python scripts/lint_prereg.py <this file>` from `C:/Users/mrthn/Aegis module`,
2026-09-09 03:10Z, against 358 prior experiments:

```
TRIAL-H5-event-learner-five-session.md: PASS  (vs 358 prior experiments)
  no close match in 148 graveyard rows, the trial registry or the prereg folder.
  R13: n_required 244  n_available 252  smallest resolvable effect 2.6pp
   [near     ] 0.200  prereg    REGISTERED             PREREG_AEGIS_NET_TOURNAMENT_1
   [near     ] 0.187  prereg    REGISTERED             PREREG_BAND_IS_BETA_1
```

PASS means unmatched, not novel. Two earlier refusals on the way here are part
of the record: `MISSING_POWER_FIELDS` (the first draft declared an adopt
threshold of +8 %/yr that 252 blocks cannot resolve) and
`UNDECLARED_SLICE_PURPOSE`. The registry row is
`backend/services/portfolio_intelligence/h5_trial.py::ensure_h5_trial`, wired
into backend startup beside the ARK and LPPLS trials.
