# TRIAL-CALIBRATED-TARGET-UPSIDE-1 — **UNSIGNED DRAFT**

**Status: UNSIGNED.** Nothing below has accrued and nothing below may be
quoted as a result. This file exists so that the day the calibrated upside is
proposed as a rank-bearing signal, the commitment already exists and cannot be
written after looking at the answer. It is the `PRODUCT_EXPERIMENT` display
feature's companion, not its permission slip: the feature ships today as a
`RISK_INPUT` and a display column, which needs no trial at all.

**Written:** 2026-09-11, alongside `backend/services/price_target.py` (roadmap
O11). **Signed by:** — (nobody; Murat signs, a session never does).

---

## 0. THE CORPSE THIS TRIAL MUST NOT BE

`analyst_target_upside_xs` is graded **PERVERSE / CLOSED**
(`backend/data/signal_registry.yaml`, last_updated 2026-08-11):

> Raw upside t −3.6 (largemid) and −7.2 (small) on OSAP. PSZ (2025)
> low-dispersion conditioning halves the bleed but never turns it positive
> (IC t −3.8). TRIAL-TGT-REBUILD (#154-155, 2026-07-26) adjudicated REJECT.
> **ANALYST-IBES-1 (2026-08-11)** rebuilt it on unadjusted IBES `ptgsumu` over
> 2002-2022 and got **−8.6% to −17.6%/yr net in all eight cells — and −8.6% to
> −16.7%/yr GROSS**, so it is not a cost story.

`NEVER_PICKS` bars a PERVERSE grade from any promoting role, and
`rank_invariance()` requires Spearman ρ == 1.0 when a closed signal's values
are permuted across names. **The raw upside may never lead a ranking again, and
this trial does not ask for it to.**

**Resurrects:** `analyst_target_upside_xs` — **new instrument:** the ranked
quantity is not the raw upside. It is the upside after (a) an additive
de-bias measured per sector × cap-tier × vol bucket on data strictly before
each observation, (b) an isotonic map from raw upside to realised 12-month
return fit on the same PIT panel, and (c) a dispersion/coverage condition. The
2026-09-11 walk-forward over **390,368 consensus cells, 7,439 names, 228 months
(2005-2023)** measures the de-biasing step to be worth **MAE 45.29% vs the raw
consensus's 48.82%** and **hit rate 48.35% vs 39.20%**, in every era. That is a
different quantity with a measured difference — which is what "a new
instrument" has to mean, and "we are trying again" does not.

**And the finding that must travel with it:** on the same panel the naive
control — `current price × (1 + trailing mean realised 12-month return)` —
has a **LOWER MAE than either** (37.58% pooled; lower in all four eras). A
de-biased target beats the consensus and still loses to assuming the market's
own drift. Any version of this trial that does not beat THAT control has not
earned anything.

---

## 1. HYPOTHESIS (one sentence, falsifiable, with the honest prior)

Ranking a liquid US cross-section on the **calibrated** consensus upside
produces a forward long-short return whose 95% CI excludes zero and whose point
estimate exceeds the matched control's — **and the honest prior is that it does
not.** Every published study of target LEVELS (Brav-Lehavy 2003;
Asquith-Mikhail-Au 2005; Bradshaw-Brown-Huang 2013; Zhang's −0.047 pooled
Spearman; our own receipt's pooled IC of 0.0289) locates the information in the
REVISION, not the level. The prior here is a null, and the trial exists to be
able to say so with a number rather than by assertion.

## 2. PRIMARY METRIC (the ONE deciding number)

**Forward net long-short return of the calibrated-upside decile spread, minus
the matched control's, per era, on the tradability floor.** One number,
declared now:

- universe: names above `TRADABLE_DOLLAR_VOL` ($3m/day median 21-day) — the
  floor that retracted TRIAL-H5 and RW1's morning cell when it was applied
  late (`feedback_apply_the_execution_floor_before_believing_the_book`);
- costs: charged on realised turnover with the turnover printed, never a flat
  per-day charge (the C2 −237%/yr artefact);
- control: the same construction on a random universe draw from the same
  liquidity band (RW1's random-genome null), AND the drift control above.

Everything else — IC, hit rate, MAE, interval coverage — is **reported, never
deciding.**

## 3. DECISION RULE

| | |
|---|---|
| adopt | the primary metric's 95% CI excludes zero **and** its point estimate exceeds BOTH controls **in at least two of the four eras**, with Holm control across the eras (CANON §63 EXPORT=Holm) |
| reject | the CI includes zero in three or more eras, or the drift control wins pooled |
| minimum window | 24 months of forward evidence for any skill claim (CANON, unamended). The historical panel is a SCREEN and may never be the adoption evidence |
| cadence | monthly, at the calibration refit |
| earliest decision date | **2028-09-11** (24 months from the first forward observation, which has not happened) |
| crash override | an SPY drawdown ≥ 20% defers every decision to ≥ 6 months past the trough |
| contamination | any month in which the calibration artefact was rebuilt from a corrected panel is excluded and named, never silently re-fit |

## 4. FROZEN PARAMETERS (not to be tuned mid-trial)

- the bucket scheme: `sector | cap_tier | vol_bucket`, with the vol
  thresholds in `price_target.VOL_BUCKETS` and the cap thresholds in
  `stock_analyzer._get_cap_tier`;
- `MIN_BUCKET_OBS = 50`, `MIN_COHORT_OBS = 20`, `MIN_ISOTONIC_KNOTS = 3`;
- the isotonic map's shape: decile means with a cumulative maximum — monotone
  by construction, not by fitting;
- the eras: `learner/evaluate`'s existing four. A per-run era boundary is a
  free parameter.

## 5. WHAT THIS RULE MAY NOT DO

1. **It may not rank anything until it passes.** Until then the calibrated
   upside is `RISK_INPUT` + display: it may size a name already chosen and it
   may be a column the user sorts by hand; it may not enter `ranking_score`.
   `signal_registry.rank_invariance()` is the enforcement, not this sentence.
2. **It may not be quoted as alpha.** The 2026-09-11 backtest is a
   FORECAST-ACCURACY measurement with no trades and no costs. "Our target is
   more accurate than the consensus" and "trading on our target makes money"
   are different claims and only the first has a number.
3. **It may not arm a lane, size real capital, or appear in buy/sell language**
   anywhere it surfaces.
4. **Its historical numbers may not be re-fit after a look.** The calibration
   artefact is dated and the receipt names the file; a refit is a new dated
   file, never an edit.

## 6. RECEIPTS THIS TRIAL POINTS AT

- `backend/data/optimus/tracker_backtest/price_target_backtest_2026-09-11.json`
  — the walk-forward, per era and per bucket, three arms.
- `backend/data/optimus/price_target/calibration_2026-09-11.json` — the fitted
  artefact the live service reads (257 buckets).
- `backend/data/optimus/tracker_backtest/analyst_target_grades.json` — the
  1,333,683-target grading receipt the pooled bias comes from.
- `docs/research_notes/2026-09-11/spec_price_targets.md` — the 818-line spec,
  including the literature and the corpse constraint.
