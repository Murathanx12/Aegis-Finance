# ORDER 24 — 8-HOUR DISCOVERY / REPRESENTATION / ROUTER TOURNAMENT

**Amends ORDER 23 (`docs/ORDER_23_DISCOVERY_RUN.md`). Read that first,
then do not execute it verbatim.** Two independent reviews of Order 23
converged on the same objection: eight hours of compute could produce a
very impressive-looking dataset without producing eight hours of
additional evidence. This order is the corrected version.

Ordered 2026-08-20. Execution log at the bottom — phases are marked as
they resolve, so this file is both the plan and the receipt index.

## The objective is not backtest count

Leave the session knowing:

1. how many genuinely independent strategy behaviours exist;
2. which observable market states change those behaviours;
3. whether state dependence is predictable **prequentially**;
4. whether risk intelligence adds value **beyond simply reading IV**;
5. whether a supervised router generalises to unseen strategy families;
6. which information and model representations deserve the next dollar.

## The six corrections to Order 23

**1. `REGIME-CONDITIONAL-RETURN-1` cannot be "confirmed" on the early
era.** The reason a regime model is wanted at all is that the early era
was already read and its return IC has the opposite sign from the
modern era. Those outcomes therefore *generated* the hypothesis and
cannot independently confirm it. Verdict label is
`ADAPTIVE_HISTORICAL_VALIDATION`, never `CONFIRMED`. Fresh confirmation
is reserved for a separately frozen country/market or forward data.

**2. 3,000 backtests are not 3,000 observations.** Three thousand
strategies on March 2020 are still largely one March 2020. The training
unit is `date block × independent strategy cluster`; every calendar date
carries equal aggregate weight and correlated strategies share the
weight within a date. Cluster count is never evidence count.

**3. BH-FDR does not cover selection overfitting.** BH-FDR is right for
the declared hypothesis family; it says nothing about searching
thousands of variants and celebrating the best. Add Deflated Sharpe
Ratio and PBO/CSCV with **this run's trial count as an explicit input**,
plus an empirical null zoo matched on turnover, persistence,
concentration and coverage — not a naive permutation, whose turnover
would differ materially from the real books.

**4. Trailing PCA is not sufficient for the regime map.** Fitting
PCA/HMM over the full 1990–2024 matrix leaks future regime geometry into
historical state labels even when every feature is backward-looking. The
state estimator must be prequential: fit through t−1 → classify t →
freeze → advance. No future centroids, loadings, or transition matrices.
Output **soft state probabilities**, not categorical labels. Filtered
states only — Baum-Welch *smoothed* states are lookahead and are the
single most common way regime research dies.

**5. Strategy similarity needs five views, not return correlation.** Two
books can correlate 0.5 monthly and own nearly identical stocks and
break on the same day. Measure return correlation, holdings overlap,
action/turnover correlation, factor-residual correlation, and
co-drawdown/tail dependence; then report **effective rank / effective
number of bets**. If 3,000 books collapse to 14 behaviours, 14 is the
number that matters.

**6. The NN is not the destination.** LGBM already beat the MLP on the
risk problem. The task is not "train a bigger NN" but "give ridge,
mechanical baselines, LGBM and NN identical information and make the NN
earn its existence."

## Standing evaluation rules added by this order

- **Report breakeven cost in bps for every strategy**, not "does it
  survive 10bps". One column makes the whole book comparable.
- **Factor-residual gate**: regress every candidate on FF5+MOM+BAB+STR;
  report residual alpha and t-stat. A strategy that is HML in a costume
  dies here, cheaply.
- **Two nulls per finding**: shuffle targets within date (must give
  exactly zero) and permute across firms keeping the calendar.
- **Purged K-fold with embargo** for anything with overlapping labels.
- **Era-transfer as a first-class metric**, both directions, with the
  ratio reported.
- **Net implementable frontier, not Sharpe alone**
  (`IMPLEMENTABLE-EFFICIENT-FRONTIER-1`): +9% at 35% vol and +8% at 12%
  vol are not ranked by "A has higher return". Anything dominated across
  plausible costs leaves the candidate set.
- Any conclusion that flips inside the 0.5×/1×/2×/stressed cost grid is
  labelled `COST_MODEL_SENSITIVE`.
- **Green tests are not evidence.** A suite count never appears in the
  same paragraph as a finding; the NAV date-stamp defect passed every
  one of ~5,090 tests.

## Phases

**PHASE 0 — INTEGRITY (blocking).** WRDS metadata audit; chronology /
`observed_at` audit of every join feeding a standing finding;
shift-invariance probe; known-answer worlds and the empirical null zoo.
If any fails, abort and publish the abort.

**PHASE 1 — MEGA-SWEEP-2 AS A CORPUS.** Frozen grammar; persist per book
per month: gross, net, holdings, weights, turnover, charged costs,
sector/factor exposures, name count, winner actions, delist exits,
realized vol, drawdown state, tail metrics. Cost grid as above. Families
already spent stay DESCRIPTIVE regardless of apparent significance.

**PHASE 2 — SELECTION-OVERFIT BATTERY.** BH-FDR at the declared family
level; Deflated Sharpe; PBO via CSCV; real zoo vs matched null zoo;
top-decile-in-fold → below-median-in-holdout frequency. No "best
strategy" table without these beside it.

**PHASE 3 — STRATEGY-EFFECTIVE-DIMENSION-1.** Five similarity views,
consensus clusters, effective rank, stability under bootstrap and across
eras. Medoids selected on training windows only when used prospectively;
a full-history clustering is descriptive taxonomy and never prospective.

**PHASE 4 — RULE-INTERVENTION-1.** Matched paired effects of each
grammar decision (weighting, rank vs equal, top-N, trim vs exemption,
signal family, cost assumption), with heterogeneity by observable state.
This is the training material for learning portfolio rules.

**PHASE 5 — PREQUENTIAL-MARKET-STATE-1 + ERA-SHIFT-DECOMPOSITION-1.**
Baselines: hand-coded vol/breadth/correlation state; expanding
PCA/absorption; online change-point; expanding HMM. Then: can a domain
classifier separate early from modern data on observable X, and how much
of the return-model decay is covariate shift in `P(X)` versus a changed
`P(Y|X)`? **Lead with the ORACLE** — measure what perfect foresight of
the state is worth before building any predictor. If the oracle gap is
~0, the family closes for near-zero cost.

**PHASE 6 — OPTION-INCREMENTAL-RISK-1.** The ladder: realized-vol,
HAR-RV, ATM-IV only, RV+IV blend, ridge, LGBM numeric, LGBM
numeric+options, small NN. Targets realized vol, drawdown, barrier
incidence, tail loss. **QLIKE primary**, rank IC secondary, calibration
and sizing consequences reported. Saves both the simple and the NN
artifact.

**PHASE 7 — TRAINING MATERIAL.** `STOCK_RISK_DATASET_V1`,
`STRATEGY_STATE_DATASET_V1`, `WINNER_EPISODE_DATASET_V1`, all with equal
aggregate weight per date block.

**PHASE 8 — SUPERVISED TOURNAMENT.** Router predicts next-period net
relative return, vol, drawdown, cost, tail. Ridge → LightGBM → small
MLP. Blocked walk-forward, leave-one-strategy-family-out,
leave-one-cluster-out, country holdout where substrate permits. Complexity
wins only under the same decision-MDE procedure; on failure the dataset
is preserved and the architecture dies, not the problem.

**PHASE 9 — WINNER MANAGEMENT.** Run the frozen PIT-CRSP replication of
CONVEXITY-PRESERVATION-1. Prepare `REENTRY-OPTION-VALUE-1` (hold / trim /
exit / exit+price-confirmation re-entry / exit+revision re-entry /
exit+options-confirmation re-entry / conditional trim only when several
independent deterioration channels agree). Prepare `STREAK-MECHANISM-1`:
is five-up-day reversal concentrated in abnormal volume, options skew,
lottery/MAX state, attention shocks, low liquidity, extreme vol? The
target distinction is **transient winner vs structural winner**.

**PHASE 10 — MANAGER DATA INTEGRITY.** Split-adjusted actions via
`cfacshr`; audit the 13F metadata/window inconsistency; verify
CUSIP/PERMNO continuity; compare v1 vs v2 transition matrices. No
manager-behaviour conclusions from v1.

**PHASE 11 — LLM SCIENTIST, FIREWALLED.** Two roles, hard-separated. The
**Proposer** sees code, feature definitions, in-sample results and the
corpse list, and may output only pre-registered hypotheses (mechanism,
new information class, target, expected direction, PIT availability,
closest corpse, what makes the claim different, cheap falsification,
fresh evaluation set, MDE/economic margin). It never sees an
out-of-sample result. The **Auditor** sees everything including OOS and
may output only `PASS` / `FAIL` / `LEAK-FLAG:<location>`, never a new
hypothesis. Fixed alpha budget declared before the run. Otherwise
"LLM sees failure → explains failure → proposes variation → same data
judges variation" is an automated overfitting loop.

**PHASE 12 — SCOREBOARD.** Handoff opens with `NEW INFORMATION
ACQUIRED`, then false discoveries / null-zoo, effective dimension, state
map, rule effects, risk baseline tournament, router, artifacts, winner
management, what died, what remains not established, fresh windows
remaining, next 10 machine jobs. Every artifact records source SHAs,
feature schema, formation-time convention, train/test dates, imputation
and scaler hashes, hyperparameters, seed, sample weights, library
versions, target definitions, per-era metrics, calibration, null-world
performance. No mutable `latest.pt`.

## Time / lane rail

The nightly IIF launcher fires **17:00 local** and is mid-receipt-clock
(clean-clock firing #1 is tonight). Heavy compute checkpoints and
quiesces before it; the run resumes afterwards. IIF is never sacrificed
to the discovery run. No lane write-paths, no NAV/positions deployment
during the run, SIMULATION labels throughout, screen survivors earn
registrations and never promotions.

## Execution log

| Phase | Status | Receipt |
|---|---|---|
| 0 — WRDS metadata integrity | **DONE** — 119/119 mislabelled, LABELS_ONLY, repaired | `wrds/meta_audit_2026-08-20.json` |
| 0 — chronology audit | **DONE** — 9 checks, 2 FAIL (13F knowledge date; manager library PIT claim) | `audits/chronology_audit_2026-08-20.json` |
| 6 — OPTION-INCREMENTAL-RISK-1 | **DONE** (modern + early + shift probe) | `risk_ladder/option_incremental_risk_1_*.json` |
