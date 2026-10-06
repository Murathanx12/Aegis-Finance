# nn_lab: frozen decision-time membership, and the first night that learned since 1 October (2026-10-06)

> **AMENDED 2026-10-07 after the adversarial review**
> (`docs/reviews/REVIEW_2026-10-06_C5_NN_LAB_MEMBERSHIP_FREEZE.md`, 64/100, MERGE WITH FIXES).
> Section 7 lists the fixes. Two claims in sections 2 and 3 are superseded:
>
> - **What "frozen" means.** It is the *first-stored vintage* of each grid row, not "what the
>   model knew". The two coincide only for dates first stored from 2026-10-06 at lag 0.
> - **Final labels are no longer frozen.** They are outcomes, so they are recomputed when
>   they move by more than 1 bp, and the change is logged.

Licence `PRODUCT_EXPERIMENT`. No broker authority. Nothing trades. $0 LLM spend. Chunk C5 of
`ROADMAP_2026-10-06_V1_BETA`.

Receipt: `backend/data/optimus/nn_lab/receipts/nightly_20261006T155130Z.json` (status **OK**).
Revisions: `backend/data/optimus/nn_lab/table/revisions.parquet` (gitignored, append-only).
Code: `nn_lab/membership.py` (new), `nn_lab/nightly.py` (`step_append`, receipt fields,
`tournament`), `nn_lab/table.py` (`price_rows(force_keys=...)`).
Tests: `nn_lab/tests/test_membership_freeze.py` (12 tests).

## RESULTS SCOREBOARD

**RESULT IMPROVEMENT: NONE in returns.** The lab is unblocked: it had refused every night from
2026-10-01 to 2026-10-06. Tonight it ran, refit, and froze forecasts for 2026-10-05.

| line | tonight |
|---|---|
| Best historical net strategy vs the market | unchanged (nothing here is a strategy) |
| Best forward paper strategy | unchanged |
| Independent selector count | unchanged |
| Farm candidates tested / promoted | 0 / 0 |
| New actionable finding | none. Tonight's tournament repeats the walk-forward finding: **the NN does not beat ridge or LightGBM at any horizon** (see §4) |
| nn_lab nightly | **OK** after 6 refused nights; table 1,198,474 -> **1,201,408** rows; grid dates 515 -> **516**; labels y5 / y21 / y63 +2,956 / +2,986 / +2,910; **0 stored rows dropped** |
| Forward evidence | **0 graded forecasts so far** (`forward_grades.jsonl` is empty: every frozen h=5 window from 09-28 onward still needs the 10-06 open) |
| External execution drag / LLM spend | n/a / **$0.00** |

## 1. What broke

From 2026-10-01 the nightly append refused with
`TableShrink: table would LOSE 4 stored grid rows, e.g. [('2026-01-20','EQBK'), ('2026-01-20','THFF'), ('2026-01-27','THFF')]`
(`automation_fixes_2026-10-02.md` §3). The bars vendor had re-adjusted 313 histories for
dividends. That moved the trailing 63-session median dollar volume of four stored members
just under the $3M floor, for example EQBK on 2026-01-20 from 3,007,646 to 2,994,202. The
rebuild then left them out of dates the table had already stored. The guard was right that
the table must not lose a row. It was wrong to treat a re-adjustment as a loss. The lab
learned nothing for a week.

## 2. The rule (owner decision 2026-10-06, binding)

> Freeze historical universe membership once a forecast has been generated. Vendor
> retrospective adjustments are appended as later REVISIONS; what the model knew at
> prediction time is never rewritten.

Implemented in `nn_lab/membership.py`. Once a grid date is in the stored table, **its
members and their feature values are frozen.** A nightly rebuild can do only three things:

1. **Add** new grid dates, and replace yesterday's off-grid live rows.
2. **Add labels:**
   - fill a label that was missing because the outcome has now matured;
   - replace a *provisional* label, meaning one stored before the date's h-session window
     had elapsed on the stored calendar. A dead name's early exit is the usual case: its
     excess return was taken against a median that was not yet final.
3. **Append a revision row** for everything else the vendor changed. These are recorded and
   never applied:

| kind | meaning |
|---|---|
| `MEMBERSHIP_WOULD_DROP` | a stored member that the re-adjusted bars now call ineligible; the row is kept, and the reason prints the stored and rebuilt median dollar volume |
| `MEMBERSHIP_WOULD_ADD` | a name the re-adjusted bars would add to a stored date; it is not added |
| `MEMBER_ABSENT_FROM_REBUILD` | a stored symbol the rebuild cannot produce at all; the stored row is kept as stored |
| `FEATURES_REVISED` | changed feature values. The reason names the rescale factor of the adjusted close (`adjusted close rescaled x0.998524 (vendor dividend/split re-adjustment ...)`) or says that the inputs changed while the close did not |
| `LABEL_REVISED` | a *final* label that the rebuild computes differently by more than 1 bp. The stored label stays. Changes under 1 bp are counted on the receipt and not logged |

Every revision row carries `asof_utc`, `run_id` and `vendor_bars_through`. The file is
append-only and de-duplicated on (date, symbol, kind, hash of the rebuilt values):

- the same vendor value seen again tomorrow does not create a new row;
- a further adjustment does create one.

Writes go temp file, then verify, then replace.

**The membership is also frozen inside the label computation.** The excess label of a stored
date is taken against the median over that date's frozen members (`restrict_to_frozen` runs
before `add_excess_labels`). The cross-section the model was trained on is therefore the one
its labels are measured against.

### What still refuses (`TableShrink`, status `REFUSED`, receipt written)

- The merged table loses a stored grid row, a stored grid date or a stored label. This is the
  original `shrink_check`, which still runs on the merged table.
- Any stored date's membership hash changes (`check_frozen`).
- The rebuild cannot reproduce more than **2%** (floor 100 rows) of the stored tail
  membership. That is a broken input, not a vendor re-adjustment: the 25-name rebuild of
  2026-09-26 is the model case. Tonight 4 of 100,074 rows were not reproduced, against a cap
  of 2,001.

A `TableShrink` is now status `REFUSED` with reason `TABLE_SHRINK: ...`. It used to be
`FAILED`. Every receipt carries `table_before`, printed before any rebuild, and
`table_after`.

## 3. The first receipt's numbers (`nightly_20261006T155130Z`)

| | before | after |
|---|---|---|
| rows | 1,198,474 | 1,201,408 |
| grid rows | 1,195,525 | 1,198,469 |
| grid dates | 515 (last 2026-09-28) | 516 (adds 2026-09-30; live date 2026-10-05) |
| y_5 / y_21 / y_63 labels | 1,192,394 / 1,183,457 / 1,157,019 | 1,195,350 / 1,186,443 / 1,159,929 |

The receipt's membership line:
**`5,885 rows re-adjusted; 4 members the rebuild would have dropped kept; 0 dropped; 0 would-add recorded, not added`**.

- **The four members kept:** EQBK on 01-20, THFF on 01-20 and 01-27, and ISTR on 04-09. ISTR
  was new: its median moved from 3,000,933 to 2,988,622.
- **Re-adjusted rows:** 5,885 `FEATURES_REVISED` rows, covering 188 symbols on 35 dates.
- **Labels:** 8,852 labels filled and 42 provisional labels replaced. 4,505 final labels
  were revised by more than 1 bp and logged, not applied. Another 43,389 changed by less than
  1 bp: the dry run put their median change at 0.0017 bp, caused by the date's median moving
  slightly.
- **Revisions appended:** 10,394.
- **Frozen dates:** all 515 stored dates have the same membership hash as in the pre-run
  backup of the table, and no stored grid key is missing. Checked independently after the
  run.
- **Digests:** membership digest before `8599b2d9e894a383...`, after `3dcf0473c45a68a8...`.
  The new digest differs only because one new date was added. Table sha256 `0a4450e1c31c580b...`.
  A dry run on a scratch copy an hour earlier produced the same table sha, so the merge is
  deterministic.
- **Fit:** a refit ran because a new labelled grid date exists (2026-09-23), on 1,195,525
  training rows. The three network seeds stopped at epochs 14, 6 and 15. New versions:
  lgbm-b3b782c9cd12, ridge-0994db65798b and nn-6a35f740ae63.
- **Freeze:** forecasts for decision date 2026-10-05 over 2,939 names. Ten models were frozen:
  nn, lgbm, ridge, mom_12_1, zero, trailing_vol, ridge_abs, nn_width, vol_earn and the
  ensemble. The size forecast was also frozen.
- **The ensemble is the zero.** It is the zero because no model has a forward grade yet. Its
  "top 10" (A, AA, AAL, ...) is therefore alphabetical tie order, not a view.
- **Run time:** 168.7 s, on the scheduled invocation (`run_nightly.cmd`). The command line
  matches the `AegisNNLabNightly` task.
- **GPU:** llama-server was not running and nothing needed it. Torch uses CUDA when a card is
  free and falls back to CPU otherwise.

A pre-run copy of the table is kept at
`table/train_table_before_20261006_membership_freeze.parquet` (gitignored, about 200 MB). It
can be deleted once tomorrow's audit passes.

## 4. The model tournament on the receipt (`tournament`)

The owner's rule is that complexity must earn its place. Each receipt therefore prints the
network beside ridge, LightGBM and 12-1 momentum, on the same folds. No new model was added.

- **Walk-forward:** the newest post-review receipt `wf_20260929_post_review.json`: 7 purged
  expanding folds with a 63-session embargo (`splits.py` / `walkforward.py`), the same folds
  for every model. It is printed and **was not refit tonight**, because that is an 8-minute GPU
  run. It was computed on the table as it stood on 2026-09-28, before the CRSP-deaths rebuild.
- **Forward:** mean rank IC over decision dates on which every listed model was graded.
  Tonight that is `NO_FORWARD_GRADES_YET`.

| h | NN rank IC (se) | LightGBM | ridge | mom 12-1 | NN minus best | verdict |
|---|---|---|---|---|---|---|
| 5 | 0.0089 (0.0104) | 0.0102 (0.0047) | 0.0075 (0.0079) | 0.0152 (0.0105) | -0.0013 vs lgbm | NN does not beat the simpler baseline |
| 21 | 0.0008 (0.0131) | 0.0178 (0.0087) | 0.0143 (0.0117) | 0.0126 (0.0139) | -0.0170 vs lgbm | NN does not beat the simpler baseline |
| 63 | 0.0112 (0.0210) | 0.0132 (0.0170) | 0.0241 (0.0221) | 0.0142 (0.0241) | -0.0129 vs ridge | NN does not beat the simpler baseline |

How the verdict is computed:

- The rule: NN minus max(ridge, LightGBM) must exceed one SE of the difference.
- The SE used is an upper bound, `hypot(se_nn, se_best)`. It is conservative only in the NN's
  favour, and the NN fails anyway.
- The top-20-minus-random net at h21 is NN -0.44%, LightGBM +2.07%, ridge +1.85%.
- Nothing about trust changes: trust is still earned only from forward graded blocks.

## 5. How to verify tomorrow

1. **The scheduled night ran and did not shrink.**

   ```
   nn_lab/.venv/Scripts/python.exe -c "import json,glob;r=json.load(open(sorted(glob.glob('backend/data/optimus/nn_lab/receipts/nightly_*.json'))[-1]));print(r['status'],r['evidence']);print(r['table_before']);print(r['table_after']);print(r.get('append',{}).get('membership',{}).get('line'))"
   ```

   Expect status `OK` or `DEGRADED`.

   - `table_after` must be greater than or equal to `table_before` on every count.
   - The membership line must say `0 dropped`.
   - `revisions.n_appended` should be small or 0, because yesterday's vendor values are
     de-duplicated.

2. **Nothing frozen moved:** `PYTHONPATH=. nn_lab/.venv/Scripts/python.exe -m nn_lab.membership`.
   It exits 0 with `OK: no frozen date moved`, comparing every receipt's per-date hashes with
   the next receipt's and with the table on disk. It exits 2 and names the dates if anything
   moved. With no hashed receipt it says `CANNOT_DETERMINE`, never OK.

3. **The first forward grades:** on the first night after the 2026-10-06 open is in the bars,
   `grade.graded_now` should become non-zero for the 2026-09-28 / 09-29 h=5 files. The
   tournament's `forward` block then prints NN, LightGBM, ridge and momentum on the same graded
   dates.

4. **The tests:** `AEGIS_PERSONAL_MODE=0 AEGIS_IGNORE_DOTENV=1 python -m pytest nn_lab/tests -q`
   (68 pass).

## 6. Not done / open

- **The walk-forward was not re-run on the rebuilt table** (CRSP deaths, ETF exclusion, frozen
  membership). The tournament prints the 2026-09-28 receipt and says so. A re-run is about 8
  minutes on the GPU and can be done on an attended night.
- **Revision volume:** about 10k rows on the first night, mostly the 313-symbol re-adjustment.
  Later nights should append only new vendor changes. If `revisions.parquet` grows past about
  50 MB, roll it up by month.
- **Still no alert channel for a REFUSED night.** A refusal is visible only in the receipt,
  `nightly.log` and exit code 2. That is how six refused nights went unseen.

## 7. Review fixes (2026-10-07)

Tests: `AEGIS_PERSONAL_MODE=0 AEGIS_IGNORE_DOTENV=1 python -m pytest nn_lab/tests -q`, **79 passed**
under both the nn_lab and the project interpreter. The new tests are in
`test_membership_freeze.py` and `test_review_c5.py`.

| fix | what changed | where it shows on the receipt |
|---|---|---|
| F1 dollar volume carries later dividends | No unadjusted daily series is on disk: `bars_raw_monthly` is monthly, and was last pulled on 09-29. The fix is therefore the vintage. Each new grid date is stored from the bars of its own night and frozen, and `membership_vintage.jsonl` records its lag (09-30 was first stored at lag 3, `pit_dollar_volume: false`). The older dates are marked plainly (`config.PRE_FREEZE_DV_NOTE`). | `append.pre_freeze_dollar_volume_note`, `append.frozen_means`, `append.vintage_of_new_grid_dates` |
| F2 a forecast's inputs were discarded within 24 h | `save_frozen_inputs` writes the exact scored rows to `frozen/<date>/inputs_<run_id>.parquet`, with their sha in `frozen_inputs_ledger.jsonl`. `score_live` is the single scoring path, used by both the freeze and the re-score. Tonight's real 2026-10-05 inputs were saved after the fact: re-scoring them reproduces every frozen nn / lgbm / ridge / mom score at every horizon. | `freeze.frozen_inputs.rescore_check`, `rescore_reproduces_scores` |
| F3 the revisions log was rounding noise | Features need \|Δ\| > 1e-3 (any feature), or > 0.5% relative for the level columns `med_dv` and `close`. On a scratch copy, 99.4% of the remaining feature revisions carry the dividend-rescale reason, and the most frequent column is now `dv_log` (the genuine look-ahead of F1), not `ret_1`. A second identical night appends **0** rows. | `membership.thresholds`, `revisions.n_appended` |
| F4 thresholds were undeclared and untested | All thresholds moved to `config.py` and are printed. Tests cover the boundaries: a change of exactly 1.0 bp is not a revision and 1.0001 bp is; exactly the cap of absent members passes and one more refuses. A 0.9 bp/night drift is logged on night 2, because each night is measured against the stored value. | `membership.thresholds` |
| F5 the guard was weaker, and silently | Absent and ineligible members are capped separately. More than 0 absent, more than 25 would-drop, or any frozen member removed by the exclusion list makes the night DEGRADED, with the reason in `evidence`. | `degraded_reasons`, `status`, `evidence` |
| F6 write order, and the ETF back door | Revisions are appended only after the table write is verified (tested with a planted `os.replace` failure). Frozen hashes are taken before the exclusion list is applied. A removal is allowed only as `ETF_EXCLUDED_FROM_FROZEN_DATE`, which is counted and degrades the night. | `membership.etf_removed_from_frozen_dates`, `frozen_dates_changed_by_declared_exclusion` |
| F7 the tournament was stale and the verdict omitted momentum | Walk-forward re-run tonight on the GPU (452 s, table sha `0a4450e1…`, CRSP deaths on). The block stats now carry a non-overlapping view (every other block) and leave-one-year-out. 12-1 momentum is in the baseline set. | `tournament.walk_forward.{age_days, same_table_as_tonight, verdict.baselines_compared, in_sample_val_ic_vs_walk_forward}`, `tournament.forward_weight_sentence` |
| F8 refusals were invisible | `nn_lab.health_contract()` returns ALIVE, REFUSED (with the reason and the count of consecutive non-OK receipts), STALE or UNKNOWN. C8 wires it into the probe. | n/a (it reads the receipts) |
| F10 final labels were frozen | A final label is recomputed when it moves by more than 1 bp, and the change is logged as `LABEL_RECOMPUTED`. On the scratch copy, the first night recomputed 4,505 final labels and the second recomputed 0. | `membership.labels_final_recomputed_applied_and_logged` |

### The tournament, walk-forward `wf_20261007T_c5_review.json` (tonight's table, 7 folds, 3 seeds)

| h | NN rank IC (t, t non-overlapping) | LightGBM | ridge | mom 12-1 | NN minus best | top-20 net: NN / lgbm / ridge / mom |
|---|---|---|---|---|---|---|
| 5 | 0.0107 (1.24, 0.86) | 0.0138 (3.26, 2.51) | 0.0105 (1.43, 2.14) | **0.0178** (1.70, 0.29) | -0.0072 vs mom | +0.18% / +0.23% / +0.25% / +0.46% |
| 21 | 0.0149 (1.32, 0.97) | **0.0254** (3.09, 2.28) | 0.0209 (1.99, 1.52) | 0.0175 (1.25, 0.88) | -0.0105 vs lgbm | -0.25% / +1.77% / +1.65% / +1.83% |
| 63 | 0.0263 (1.28, 1.84) | 0.0233 (1.57, 0.45) | **0.0329** (1.68, 0.38) | 0.0201 (0.84, 2.23) | -0.0066 vs ridge | -0.84% / +7.75% / +3.14% / +6.03% |

- **Verdict at every horizon:** the NN does not beat the simpler baseline, so complexity has
  not earned its place. At h5 the best model is the single column, 12-1 momentum.
- **Validation versus test:** the NN's validation IC at its best epoch averages 0.049, against
  a test IC of 0.011 / 0.015 / 0.026. That is the overfit gap.
- **By year at h21:** LightGBM is negative only in 2022 (-0.035); the NN is negative in 2020.
- **Weights:** no model has earned forward weight, and the ensemble weights are zero.
- **Next decision:** if the NN still loses once forward grades exist, stop the nightly NN refit
  and train the three cheap models only. That is the reviewer's §3 proposal, not done tonight.

### Still open

- **The evidence receipt is the scheduled one.** That is the 08:30 HKT run of 2026-10-07
  (review F11). It is the first night to run all of the above end to end on the real table. It
  will apply about 4,505 final-label recomputations and log them once, and it will save its own
  inputs file with the re-score check.
- **F9 is not done.** The revisions log is still a set of seen states, not a timeline, and it
  is untracked. Each receipt carries `n_total`, not a sha.
- **Higher-moment features are still noisy.** `skew_63`, `beta_63` and `gap_share_21` still
  produce rounding-level revisions at the 1e-3 floor (about 3.9k / 2.6k / 2.0k cells). A
  per-family tolerance for them is the next tightening.
