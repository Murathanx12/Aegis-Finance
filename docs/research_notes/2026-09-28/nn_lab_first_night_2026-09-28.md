# nn_lab, first night (2026-09-28): the model that improves nightly, built and run once

Licence `PRODUCT_EXPERIMENT`. No broker call, no order, no paid LLM call. Code is in `nn_lab/`
(own venv, own tests). Nothing in the live path imports it, and it imports nothing from the live
path. Every number below comes from a receipt in `backend/data/optimus/nn_lab/receipts/`.

## RESULTS SCOREBOARD

**RESULT IMPROVEMENT: NONE in money.** The network does not beat LightGBM at ranking. What is new
is capability: a nightly loop now exists, it has run once end to end, and it wrote 8,709 frozen,
gradeable predictions.

| item | value | receipt |
|---|---|---|
| training table | **1,116,722 rows**: 515 weekly decision dates from 2016-07-01 to 2026-09-25, 3,605 names, median 2,133 names per date (min 1,688, max 2,953) | `table_20260928T142620Z.json` |
| survivorship | 583 dead names carrying 78,637 rows. 63 reused tickers split into separate companies. Still **partially survivor-selected** (see §1) | same |
| PIT violations | 0 in every group (fund, analyst, news, ledger) | same |
| best baseline (21d) | **LightGBM**: rank IC **+0.0201**, SE 0.0087, t 2.32, 80 blocks. Top-20 minus the random portfolio, net of costs: **+1.37% per 21-session hold**, SE 0.82%, t 1.67. Verdict **BETA_EXPLAINS** (residual IC +0.0072) | `wf_20260928_v3.json` |
| the network (dist, 21d) | rank IC **+0.0126**, SE 0.0109, t 1.15. Top-20 minus random net **+0.48%**, SE 0.30%, t 1.57. Verdict **CANNOT_DISTINGUISH**. Reliability weight 0.25 | same |
| the network (rank loss, 21d) | rank IC **−0.0217**, t −1.12. **FAILED_VARIANT** | same |
| AutoGluon (21d, coordinator request) | rank IC **+0.0163**, SE 0.0081, t 2.02. Spread +1.01%, SE 0.74%. **CANNOT_DISTINGUISH**. Beats the NN, below LightGBM | `ag_20260928_h21.json` |
| calibration of P(beat the median), 21d | Brier skill vs base rate is about 0 for every model (NN −0.0004, LightGBM +0.0006, ridge +0.0009). The NN's probabilities sit in 0.39 to 0.60 | `wf_20260928_v3.json` |
| magnitude (the uncertainty head) | the NN's interval width ranks \|excess\| at IC **0.357** vs trailing vol **0.336** at 21d (0.348 vs 0.329 at 5d, 0.364 vs 0.345 at 63d). This is the one place the network beats its baseline | same |
| interval coverage, 21d | NN 50% interval covers **44.6%** and 90% covers **83.2%** (too narrow). Trailing vol around zero covers 59.4% / 91.5% | same |
| nightly run | **completed end to end** (`nightly_20260928T141823Z`, 66 s). Incumbent `nn-645977cc6124`. 8,709 FROZEN rows (2,903 names × 3 horizons), sha256 `99a9a2a5…81e0`. Status **DEGRADED**: no bars newer than 2026-09-25 exist yet | `nightly_20260928T141823Z.json`, `nightly_20260928T143449Z.json` |
| scheduled | `AegisNNLabNightly`, daily at 08:30 HKT, with a STOP file | §7 |

## 0. What have the nights been doing?

From the receipts, and said plainly: **the nights grade, collect and run experiments. No model's
weights have been refit and carried forward from one night to the next. Nothing learned has changed
a decision.**

- **The daily pass** (`night_factory_2026-09-*/daily_pass_*.json`) runs 14 steps: bars, news, the
  decision contract, analyst snapshots, event append, book cadence, grading, paper accounts,
  bridge, coverage, scoreboard and health. On 09-28, 8 steps did work and 6 had nothing to do.
- **The forecast grader.** It has graded 17,524 of 28,529 forecasts, and that count has not moved
  since 09-26.
- **The rule distiller** (`brain/learn_runs.jsonl`). It produced rules once, on 09-26. The other 75
  runs reported `LEARN_DEGRADED: no new graded rows`.
- **The "NN lab"** (`lab_nn.py` → `nn_lab_history.jsonl`, 84 rows). It refits 12 heads from scratch
  and scores them on **the same held-out month (2026-08) every night**. Nights 09-15 to 09-18 are
  byte-identical. After that, the ICs wander by about ±0.02, and the shuffled-label controls wander
  just as much. It writes no model, and E1 is FAILED_VARIANT every night.
- **The E[r] refit** (`expected_return/refit_2026-09-2[5-8].json`). It reports `licensed: False`
  with `n_dates: 0` at every horizon.
- **The reputation weights.** They are identical on four consecutive days.
- **The only persisted models**: `learner/models/champion_*.joblib` (09-02) and one encoder
  (09-08). Neither has been touched since.
- **The 09-28 scoreboard says it itself**: "learning changed capital: no."

**What the nights have NOT been doing** is the thing the owner described. Nothing trains a model on
the labelled history, keeps it, predicts tomorrow with it, grades those predictions when their
horizon elapses, and replaces it only when a successor is measurably better. `nn_lab.nightly` is
that loop.

Prior work reused, or checked and not rebuilt:

- the bars panels (`prices_deep` plus `bars_delisted`);
- xs_ranker's feature ideas, eligibility floors, band costs and LightGBM defaults (copied, not
  imported);
- the SEC facts table, analyst revisions (393,637 rows) and the news panel;
- the forecast ledger schema.

Earlier NN verdicts, all consistent with tonight:

- `FINDING_2026-08-24_RELATIVE_VALUE_NN`: the MLP was worst;
- `LEARNER_V2`: permutation-null trouble;
- W3 `nn_pre_causal`: frozen shadow, never produced a book;
- the "learner edge was six rebound months" memory note.

## 1. The table (`nn_lab/table.py`)

A row is (decision date t on a weekly grid, symbol). Features are known at t's close. The label for
h ∈ {5, 21, 63} is `open(t+1+h)/open(t+1) − 1` minus the cross-sectional median of the names
eligible at t. The label is measured on the **session calendar**, so a gap in a name's bars is
never read as consecutive sessions.

| group | features | available when | coverage (grid rows) |
|---|---|---|---|
| price / volume | 27 (returns 1/5/21/63/126, 12-1, vol 21/63, idio vol, beta, residual momentum, dollar-volume level and trends, 52w/MA distances, drawdown, Amihud, skew, max return, gap share, VWAP pressure) | bars ≤ t | 100% |
| fundamentals (SEC) | 12 (log mcap, E/P, S/P, B/M, margins, YoY revenue and NI, leverage, cash, R&D intensity, days since filing) | **FILED strictly before t**; stale after 400 d | 99.5% any; per feature 27% to 81% |
| analyst revisions | 7 (63d up/down/net/init/count, 21d net, mean target change) | event day < t | 86% |
| news | 2 (5d and 21d article counts) | published day < t; from 2025 only | 20% |
| forecast ledger | 2 (10d mean probability and count) | made day < t; from 2026-08 only | 0.05% |

A group below 2% coverage in a fold's training rows is not fed to any model. The ledger group is
never used tonight. News is never active in a walk-forward fold, and it is active in the nightly
model (its training window reaches 2025).

**Two data defects were found and fixed tonight, and they matter beyond this lab:**

1. **`prices_deep` splices reused tickers into one series.** FLY (Fly Leasing to 2021, then
   Firefly from 2025), NIQ, VIA and 60 others each carry two companies under one symbol, with a
   multi-year hole between them. xs_ranker reads the same file, so its 12-1 momentum and its
   history floor straddle two companies for these names. `table.split_reused_symbols` cuts at any
   gap over 20 sessions and makes each earlier segment its own dead name (`FLY#1`).
2. **The nightly tail rebuild must use the same sources as the build.** The first run read
   `prices_2025_26` alone and lost 606 labels. The second run REFUSED by name ("would LOSE 606
   labels … original table kept"), which is how the defect was found.

**Survivorship caveat, on every receipt.** The living names were selected alive on 2026-09-01 with
a $3M dollar-volume floor. The dead names come only from Alpaca's 1,784 inactive listed symbols, so
there is no OTC and no death before 2016. A dead name exits at its last close, and its true
delisting return is unknown.

## 2. Baselines, then the network

Everything below is in `wf_20260928_v3.json`. Test years run from 2020 to 2026 (2026 is partial).
Each fold is: expanding train, then a 63-session embargo, then 26 validation dates, then a
63-session embargo, then the test year. The SE is over date blocks of max(h, 21) sessions. The
spread is top-20 minus the all-eligible random portfolio, both net of band costs (6/10/18/35 bps
round trip), with one round trip per hold.

| model | h | rank IC (SE, t) | top-20 − random, net (SE, t) | mean without best 5 hold months | LOYO worst | verdict |
|---|---|---|---|---|---|---|
| zero (median) | all | 0 | 0 | 0 | 0 | the floor |
| 12-1 momentum | 21 | +0.0124 (0.0138, 0.90) | +1.91% (0.88%, 2.16) | +0.70% | +1.36% | CANNOT_DISTINGUISH |
| ridge | 21 | +0.0212 (0.0116, 1.83) | +1.47% (0.61%, 2.43) | +0.80% | +0.97% | BETA_EXPLAINS |
| **LightGBM** | 21 | **+0.0201 (0.0087, 2.32)** | **+1.37% (0.82%, 1.67)** | **+0.22%** | +0.75% | BETA_EXPLAINS |
| NN dist | 21 | +0.0126 (0.0109, 1.15) | +0.48% (0.30%, 1.57) | +0.16% | +0.31% | CANNOT_DISTINGUISH |
| NN rank | 21 | −0.0217 (0.0194, −1.12) | +2.36% (1.07%, 2.21) | +0.88% | +1.30% | FAILED_VARIANT |
| LightGBM | 5 | +0.0105 (0.0048, 2.20) | +0.35% (0.26%, 1.37) | +0.03% | | BETA_EXPLAINS |
| NN dist | 5 | +0.0077 (0.0084, 0.92) | +0.03% (0.14%, 0.23) | −0.11% | | CANNOT_DISTINGUISH |
| LightGBM | 63 | +0.0208 (0.0173, 1.20), 26 blocks | +4.39% (2.31%, 1.90) | +2.04% | | BETA_EXPLAINS |
| NN dist | 63 | +0.0107 (0.0191, 0.56) | +0.50% (1.34%, 0.38) | −0.44% | | CANNOT_DISTINGUISH |

**Which part of the sample is it (protocol item 11)?**

- **LightGBM's 21d spread is mostly five months.** Without its best five hold months (2020-05,
  2023-12, 2025-06, 2025-05, 2020-12) the mean falls from +1.37% to +0.22%.
- **By hold year**, LightGBM's spread was +3.8% (2020), +0.1% (2021), **−3.5% (2022)**, +1.5% (2023),
  +2.5% (2024), +4.9% (2025) and +0.2% (2026).
- **Its IC is mostly factor tilt.** Residualised on ranked momentum, beta, vol and size, it falls
  from +0.020 to +0.007. That is BETA_EXPLAINS.
- **Every positive top-20 spread here is partly a volatility and skew effect.** The labels are
  excess over the MEDIAN, so a high-vol top-20 has a positive mean against a median benchmark from
  skew alone.
- **The rank variant shows it most clearly.** It has negative IC and +2.36% spread, the signature of
  a tail bet rather than a ranking. Treat its spread as a warning, not a result.

**The network against LightGBM, as the literature predicts: it loses on ranking.** The NN's IC is
lower (+0.0126 vs +0.0201) and its spread smaller (+0.48% vs +1.37%). But the NN's IC is the only
one that **rises** after residualising on momentum, beta, vol and size (+0.0126 to +0.0164). Its
little signal is less factor-tilt than LightGBM's. It is also the lowest-variance spread (SE
0.30%).

**Selection optimism is visible.** The NN's validation IC (0.03 to 0.09 per fold, used for early
stopping) runs far above its test IC (+0.013). The nightly promotion comparison inherits this,
because both challenger and incumbent early-stop on the same block (§5).

## 3. Calibration and uncertainty

- **The probabilities are honest and nearly uninformative.**
  - Reliability at 21d: a mean prediction of 0.487 hit 0.495; a mean prediction of 0.512 hit 0.504.
  - Brier 0.2501 vs 0.2500 for the base rate.
  - This matches the operator's shadow rule, whose stated P sits between 0.494 and 0.510. The
    honest width of our knowledge about direction is about ±1 point.
- **The distribution head carries real information about SIZE, not direction.**
  - Its 5-95 width ranks next month's \|excess\| better than trailing volatility at every horizon
    (21d: 0.357 vs 0.336, both t > 50).
  - Its intervals are too narrow (90% nominal covers 83%). The fix is a conformal width scale from
    the graded rows, not a new model.
- **For position sizing, the risk half of the network is usable tonight. The return half is not.**

### 3b. AutoGluon (coordinator request)

AutoGluon-Tabular 1.6.3 installed cleanly into `nn_lab/.venv`. The only side effect was
pyarrow 25 → 24, in that venv alone.

**Setup.** Same folds, embargo and raw features as LightGBM. Only h = 21. 10 minutes per fold,
preset `medium_quality`, no KNN. Training rows were subsampled to 400,000 per fold (seed recorded)
to stay inside the memory budget. CatBoost, XGBoost and FastAI were not installed, so AutoGluon
skipped them. The best model in all 7 folds was a WeightedEnsemble of LightGBM and its own torch
MLP. Total 17 minutes, peak about 1.8 GB.

**Result.** Rank IC **+0.0163** (SE 0.0081, t 2.02). Top-20 minus random net **+1.01%** (SE 0.74%,
t 1.37); without its best 5 hold months it is +0.12%. Residual IC +0.0085. Brier skill −0.0004.
Verdict **CANNOT_DISTINGUISH**.

**Reading.** AutoGluon lands between our NN (+0.0126) and LightGBM (+0.0201). The NN does not
beat it, and it does not beat plain LightGBM on the full data. Nothing here suggests model class is
the bottleneck; the features are. Receipt: `ag_20260928_h21.json`.

## 4. Verdicts and weights

With the verdict vocabulary applied at 21d, **nothing is ALPHA_DETECTED**:

- LightGBM and ridge: BETA_EXPLAINS.
- Momentum and NN dist: CANNOT_DISTINGUISH.
- NN rank: FAILED_VARIANT.

The model still emits a probability every night. `evaluate.reliability_weight` (t²/(t²+4), floor
0.05) gives the NN mean 0.25 at 21d and 0.17 at 5d. It gives LightGBM 0.57. The weight is small,
not zero.

## 5. The nightly loop (`python -m nn_lab.nightly`)

**Steps.**

1. **append**: rebuilds the tail from the refreshed bars and REFUSES if any label would be lost.
2. **grade**: grades only frozen rows whose horizon has elapsed. Entry is the first session whose
   13:30 UTC open falls after the moment the row was written.
3. **retrain**: 3 seeds drawn OUTSIDE `seeds_used.jsonl` (the ledger now holds 93 seeds from
   tonight's runs).
4. **promote**: only if IC21 beats the incumbent by +0.005 on the most recent validation block and
   Brier is no worse by 0.002.
5. **predict**: FROZEN rows, one file per decision date, never overwritten, sha256 in the receipt.
6. **receipt**: `new_rows_since_last_run`, where 0 means DEGRADED.

**Guards.** It refuses by name on a STOP file, low disk (<5 GB), low RAM (<1.5 GB) or a concurrent
run. It is resumable (`night_state.json`) and time-boxed at 90 minutes.

**Tonight's three runs:**

| run | what happened |
|---|---|
| `nightly_20260928T141823Z` | First model `nn-645977cc6124` became the incumbent (validation IC21 0.0636, which is early-stopping optimistic). It froze 8,709 rows for decision date 2026-09-25, 25 of them in the candidate funnel. P21 ranges 0.401 to 0.573. Top-5 by mean among candidates: PDS, SON, JAZZ, ARCO, TS. It agrees in sign with the operator's shadow rule on JAZZ/TS/SNDR. **Its `in_frozen_book` flag reads 0 because it looked for the wrong key** (books store `positions`). This is fixed in code, but the frozen file keeps the wrong flag; grading does not use it. |
| `nightly_20260928T142134Z` | **FAILED by design**: the tail rebuild would have lost 606 labels. The original table was kept. |
| `nightly_20260928T143449Z` | Resumed the failed run. Lost 0 labels. Status **DEGRADED** (true: no bar after 2026-09-25 exists yet). Challenger `nn-36f2300eb71c` scored IC21 0.0511 against the incumbent's 0.0636 + 0.005, so it was **not promoted and the incumbent was kept**. Predictions: ALREADY_FROZEN. |

**Known weakness.** Challenger and incumbent both early-stopped on the block they are compared on.
The fair version keeps a separate promotion block after the early-stopping block, which costs one
63-session embargo of recency. This is the first change to make once graded forward rows exist,
because then the promotion test should be **graded forward IC**, not validation IC.

## 6. How it would reach a decision (specified, not wired)

It fits the operator's rule in `how_the_engine_decides_2026-09-28.md` §(f) as one more component
j, with nothing new.

- **m_j and se_j.** Tonight the only evidence is the walk-forward: +0.48% per 21-session hold,
  SE 0.30%. Doubled because the variant was chosen on it, the SE becomes 0.61%.
- **Posterior.** With the rule's tau = 0.5%, the shrink is 0.25/(0.25+0.37) = 0.40, so the
  posterior is **about +0.19%/month**. That is the same order as momentum's +0.22%.
- **Caveat.** This spread is against the random all-eligible portfolio, not the rule's
  size × vol × momentum matched twin. The NN's residual IC suggests the twin-matched number would
  not be smaller, but that is not measured.
- **Replacement.** From the first graded forward rows (h5 on about 2026-10-06, h21 on about
  2026-10-28), m_j and se_j come from `grades.jsonl` instead (top-20 minus the median, per decision
  date, SE over date blocks), and the walk-forward number is dropped.
- **Exposure and uncertainty.** e_ij would be the name's percentile of the NN mean. Its
  contribution to s_i² would use the NN's own width, which beats trailing vol at ranking magnitude
  (§3), after a conformal scale.
- **Nothing was wired.** `sim_run.py`, `policy_state.py`, `pc_broker.py` and every limit were left
  untouched.

**Shadow book: not frozen, deliberately.**

- The operator froze `SHADOW_BAYES_v0` (`439fd84f869744e0`, with twins `ec29c635db8ac686`,
  `d00f3ab5451adc9e` and `3e0a91bed8759db0`) at 14:05 UTC. It is the vehicle built to carry
  components of exactly this form, and its v1 is where this one belongs.
- The TIER 1 roadmap also says no new book before 2026-10-26.
- The NN's forward record does not need a book. Every night it freezes a probability, a mean and
  an interval for all 2,903 eligible names, graded at 5/21/63 sessions. That is a larger and
  cleaner forward test than a 20-name book, with no broker path.

## 7. Schedule

- **Task.** `AegisNNLabNightly`, registered 2026-09-28. It runs daily at **08:30 HKT**, which is
  after the 04:00 HKT US close and the 06:30 HKT `pull_bars_refresh`, and before the 21:30 HKT open.
- **Command.** `nn_lab\run_nightly.cmd`. The log goes to `backend/data/optimus/local_pc/nn_lab/nightly.log`.
- **Stop.** Create `backend/data/optimus/nn_lab/STOP`.
- **Remove.** `schtasks /Delete /TN "AegisNNLabNightly" /F`.
- **When bars are refreshed.** Each night then adds rows (a new session every night, and a new grid
  date every fifth), fills labels, grades matured rows and trains a challenger on new seeds.

## 8. Files

- `nn_lab/` holds `config.py`, `table.py`, `splits.py`, `models.py`, `nn.py`, `evaluate.py`,
  `walkforward.py`, `ag_baseline.py` (AutoGluon), `seeds.py`, `nightly.py`, `run_nightly.cmd`, `README.md`,
  `requirements.txt`, `requirements.lock.txt` and `tests/test_nn_lab.py`.
- **Receipts** (tracked): `backend/data/optimus/nn_lab/receipts/`, including the current table
  receipt `table_20260928T142620Z.json`.
  - The earlier table receipts are the spliced builds that §1 describes.
  - `wf_20260928_full.json` ran on the spliced table and is superseded by `wf_20260928_v3.json`.
    The two differ by at most 0.0053 in any IC, mostly NN seed noise.
- **Tracked ledgers**: `seeds_used.jsonl` and `variant_choice.json`.
- **Local** (gitignored): the table, models, walk-forward OOS frames and prediction files.

**WHAT WORKS:** The loop exists. It builds a PIT table with zero violations, trains on the GPU in
about a minute, refuses by name when data would be lost, and freezes 8,709 gradeable
probabilities per night. Its distribution head ranks next month's move size better than trailing
volatility at every horizon.

**WHAT DOES NOT:** The network does not beat LightGBM at ranking (IC +0.013 vs +0.020, t 1.15), its
probabilities of beating the median carry no measurable skill (Brier skill ≈ 0), and LightGBM's own
edge is mostly five hold months and factor tilt.

**HIGHEST-EV EXPERIMENT:** Grade the frozen rows as they mature (h5 from about 2026-10-06) and
switch promotion to graded forward IC. In parallel, put the NN's calibrated width into the shadow
rule's s_i as a sizing input, where the measured gain over trailing vol already exists.


---

# AFTER REVIEW (2026-09-28 ~16:00Z, answering `docs/reviews/REVIEW_2026-09-29_NN_LAB.md`)

**RESULT IMPROVEMENT: NONE in money. The network's ranking edge is gone.** With the future-split
leak and the death-predicting flag removed, the network ranks next month at IC **+0.0008**
(t 0.06) and its top 20 lose **-0.44%** a hold to the random portfolio: FAILED_VARIANT. The
results got worse, as the review said they would. LightGBM survives. The size-of-move skill
survives, and a plain ridge gets it.

## The corrected table beside the withdrawn one (21 sessions)

Same folds, splits, embargo, seeds policy and costs. Old: `wf_20260928_v3.json` on the leaky
table. New: `wf_20260929_post_review.json` on `table_20260928T152902Z.json`.

| model | rank IC OLD (withdrawn) | rank IC NEW | top 20 - random, net OLD (withdrawn) | NEW | w/o best 5 months NEW | verdict NEW |
|---|---|---|---|---|---|---|
| 12-1 momentum | +0.0124 (t 0.90) | +0.0126 (t 0.91) | +1.91% (t 2.16) | +1.94% (t 2.21) | +0.75% | CANNOT_DISTINGUISH |
| ridge | +0.0212 (t 1.83) | **+0.0143 (t 1.22)** | +1.47% (t 2.43) | +1.85% (t 2.24) | +0.60% | BETA_EXPLAINS |
| **LightGBM** | +0.0201 (t 2.32) | **+0.0178 (t 2.04)** | +1.37% (t 1.67) | +2.07% (t 2.36) | +0.88% | BETA_EXPLAINS |
| **NN dist** | +0.0126 (t 1.15) | **+0.0008 (t 0.06)** | +0.48% (t 1.57) | **-0.44% (t -1.20)** | -0.93% | **FAILED_VARIANT** |
| NN rank | -0.0217 (t -1.12) | -0.0237 (t -1.20) | +2.36% (t 2.21) | +4.32% (t 2.61) | +1.05% | FAILED_VARIANT |

Other horizons, NEW: LightGBM h5 IC +0.0101 (t 2.17), spread +0.41%; h63 IC +0.0132 (t 0.78),
spread +7.37% (t 2.42). NN h5 +0.0089 (t 0.86), spread +0.01%; h63 +0.0112, spread -0.57%.
Residual IC after momentum, beta, vol and size: LightGBM +0.0072 -> **+0.0030**, NN +0.0164 ->
+0.0102 (h21). Brier skill is still about zero for every model (LightGBM +0.0004).

**Read the spreads with care.** The universe changed: without an adjusted price floor, names
that traded under $3 are now eligible (1,131,456 rows vs 1,116,722), and a top 20 that buys
cheap, volatile names gains against a median benchmark from skew alone (§2 above). The rank
variant's +4.32% with a NEGATIVE IC is that effect at its clearest. LightGBM's +2.07% is
2025-heavy (by hold year: +3.5% 2020, -0.3% 2021, -1.4% 2022, +2.1% 2023, +1.6% 2024,
**+7.2% 2025**, +1.9% 2026). Its IC fell; its spread rose; the IC is the number to believe.

### WITHDRAWN (every number in this note that changed)

- §2 table: every NN row, the ridge and LightGBM ICs and spreads, all residual ICs. The NN's
  **+0.48%**, SE 0.30%, t 1.57, and "CANNOT_DISTINGUISH" are withdrawn; it is FAILED_VARIANT.
- §2 "the NN's IC is the only one that **rises** after residualising (+0.0126 to +0.0164)":
  withdrawn. It was the market-cap leak surviving a size control built on dollar volume.
- §2 "It is also the lowest-variance spread": withdrawn.
- §4 reliability weights: NN 0.25 (21d) and 0.17 (5d) -> **0.05** (the floor); LightGBM 0.57 -> 0.51.
- §6 posterior **"about +0.19%/month"** for the NN: withdrawn. On the corrected walk-forward
  its spread is negative; the rule would give it no positive mean.
- The scoreboard rows "the network (dist, 21d)", "best baseline" (LightGBM IC +0.0201 ->
  +0.0178), "magnitude" (updated below) and "training table" (1,131,456 rows, 3,610 names).
- §5 "Challenger ... not promoted, the incumbent was kept": the mechanism is retired (below).
  The incumbent `nn-645977cc6124` was trained on the leaky table; its frozen 2026-09-25 file is
  graded forward as `nn_v0_leaky` and is never trusted or ensembled.
- §3 "The distribution head carries real information about SIZE" stands, but "for position
  sizing, the risk half of the network is usable" is replaced by: a ridge on |y| does as well.

### What survived: the size of the move

| h | trailing vol IC with \|excess\| | ridge on \|y\| | NN width | ridge - vol (t) | NN - vol (t) |
|---|---|---|---|---|---|
| 5 | 0.334 | 0.350 | 0.350 | +0.0164 (t 12.3) | +0.0161 (t 16.2) |
| 21 | 0.342 | **0.358** | 0.359 | +0.0163 (t 11.7) | +0.0168 (t 16.3) |
| 63 | 0.351 | 0.367 | 0.367 | +0.0157 (t 7.3) | +0.0162 (t 9.6) |

The NN's 90% interval still covers only 82% (50%: 46%). The nightly size forecast therefore
uses the ridge, with a conformal scale (below).

## What was fixed (each has a test that fails on the 2026-09-28 code)

| review item | fix | test (`nn_lab/tests/test_after_review.py`) |
|---|---|---|
| F1 future split | `f_log_mcap`, `f_ey`, `f_sy`, `f_bm` only from an unadjusted close (`close_raw`); none is on disk, so they are NaN everywhere. The $3 floor applies only to `close_raw`; only the dollar-volume floor applies (adjusted close x adjusted volume is split-invariant). The repo's VAL-01 fix needs Compustat, which ends 2024-12 and cannot serve the nightly. | a planted 10:1 split after t changes no price feature, no eligibility and no fundamental at t |
| F2 death flag | missing-indicators only for groups whose coverage is decided at the time (`GROUP_COVERAGE`); none of fund, analyst, news gets one. Analyst is NaN for every name before its first snapshot (2026-09-24, derived from the first `analyst_pull_*.json`), so it is never in training. Measured coverage, dead vs living: analyst 0% vs 87-97%; fund 100% vs 99.4%; news 93.4% vs 94.2% (2025). | a snapshot covering only the survivor is unavailable before its pull for BOTH names and yields no `missing_*` column |
| F9 comparative period | among filings on one date, the latest period end wins | covered by the fundamentals tests |
| F6 append | the shrink guard compares the TABLE: every stored grid row and label must survive; today's live rows may be fewer | the false alarm passes, a lost row and a lost label refuse |
| F5 resume | a failed night resumes only on the same UTC day | test |
| F5.5 labels | training dates come from the calendar (window elapsed), not "y is not null" | test |
| F7 grader | sha256 checked against the ledger before grading; a row hash includes the values; a delisted name exits at its last close, never dropped; one outcome file per (date, h), written once | a tampered file is refused; a name that delists mid-hold is graded at its last close |
| 11 immutability | frozen files are created exclusively (`open(..., "xb")`); a second freeze returns ALREADY_FROZEN and leaves the bytes | test |
| in_frozen_book | read from `positions[].ticker`; the 2026-09-25 file keeps its 0s, and a sidecar `pred_2026-09-25_...in_frozen_book_correction_2026-09-29.json` gives the right answer: 907 names, not 0 | test |

## The loop that learns (`nn_lab/loop.py`, `nn_lab/nightly.py`)

Promotion on a validation block is gone. Each night:

1. **FREEZE**: nn, lgbm, ridge, mom_12_1, zero (direction; h 5/21/63), trailing_vol,
   ridge_abs, nn_width (size; h 5/21), and the ensemble each write one immutable file under
   `nn_lab/frozen/<date>/<model>.parquet`; the sha256 goes to `frozen_ledger.jsonl` (tracked,
   append-only).
2. **GRADE**: files whose horizon elapsed are graded after the sha check, into
   `forward_grades.jsonl` (per model, date, horizon: rank IC, top-20 minus median, Brier,
   |move| IC, interval coverage, delisting count).
3. **TRUST**: posterior mean of rank IC per model and horizon. Prior N(0, 0.03^2); a block is
   max(h, 21) sessions; block noise sd 0.10 (walk-forward NN: SE 0.0109 x sqrt 80). **Prior
   strength k = 11.1 blocks**: 1 graded block earns 8% of its mean, 11 blocks 50%, 44 blocks
   80%. Until forward blocks exist, walk-forward blocks count 0.1 each (fading to 0 as forward
   blocks reach k), from the POST-REVIEW receipt only. Every receipt prints the source.
4. **ENSEMBLE**: trust-weighted mean of the direction models' per-date ranks; negative trust
   weighs zero; with no trust it is the zero.
5. **IN CHARGE**: the highest-trust model; it changes only on a night that added forward
   grades, and only by 0.002 of posterior IC.
6. **FIT**: the fitted rivals refit only on a new labelled grid date, on train+val (the NN
   picks its epoch count on the latest block, then refits on all labelled rows with it).
7. **SIZE**: `nn_lab/size_forecast/size_<date>.parquet` (+ `.json`): ticker, expected |excess
   move| over 5 and 21 sessions, 50% and 90% intervals, model, trust. The model is the SIMPLEST
   whose posterior gain over trailing vol is at least half the best one's (tonight: ridge_abs at
   both horizons). The interval scale is conformal: walk-forward rows now (c90 2.78 at h5, 2.70
   at h21), forward rows from 500 graded rows on. It says nothing about direction.

### Tonight's receipt: `receipts/nightly_20260928T153656Z.json` (94 s, attended, STOP left in place for this process only)

- status **DEGRADED** (no bar after 2026-09-25 exists yet; the last closed weekday is 09-25);
  append kept all 1,128,492 grid rows; the legacy file registered (sha verified against its own
  receipt); 0 graded (the first h5 grades land about 2026-10-06); refit: yes (first night;
  groups price, fund, news; NN best epochs 11 / 9 / 9).
- 9 files frozen for decision date 2026-09-25 (2,964 names; 913 in a frozen book), entry at
  the 2026-09-29 open.
- trust at h21, all `walk_forward_only`: lgbm +0.0075, ridge +0.0060, mom_12_1 +0.0053,
  nn +0.0004, zero 0. **In charge: lgbm.** Ensemble weights h21: lgbm 0.39, ridge 0.31,
  mom_12_1 0.28, nn 0.02.
- The ensemble's top 10 at h21 (ALTO, DMRA, BW, EVC, OILU, AGL, NVCT, QTTB, ZURA, CLYM)
  includes an ETN (OILU) and low-priced names: the ETF/ETN universe fix is still owed.

## Schedule

The pause file was removed after the tests passed (exit 0) and the attended run completed.
`AegisNNLabNightly` is **Ready**, next run 2026-09-29 08:30 HKT.

## Still owed

- F3: death coverage stops at 2022; the 51 dead companies dropped as reused tickers.
- An unadjusted close (an `adjustment=raw` pull) to restore market cap and the $3 floor.
- The universe: ETFs and ETNs.
- A failed or refused night is visible in the receipt and exit code only, not on the alert
  channel (alerts are another builder's files).
- STALE_BARS uses a weekday calendar: the day after a US holiday reads stale.
