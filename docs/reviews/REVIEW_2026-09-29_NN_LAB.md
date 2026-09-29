# REVIEW 2026-09-29 — nn_lab, first night (adversarial)

Reviewer stance: a sceptical quantitative investor who says "you are wrong, I would have done this".
Scope: `nn_lab/` (all modules), the receipts in `backend/data/optimus/nn_lab/receipts/`, the research
note `docs/research_notes/2026-09-28/nn_lab_first_night_2026-09-28.md`, and `nn_lab/tests/test_nn_lab.py`.
No existing file was changed. No process or task was started or stopped. The only commands run
were read-only pandas checks on the table, the walk-forward OOS frame and the bar panels, plus the
nn_lab test suite. The check scripts are in the session scratchpad and are not committed. Every
number below that is not in a builder receipt was measured in this review, and it says so.

`AEGIS_IGNORE_DOTENV=1 AEGIS_PERSONAL_MODE=0 .venv/Scripts/python.exe -m pytest nn_lab/tests -q -p no:cacheprovider`
→ **16 passed**. None of the 16 tests covers findings F1, F2, F4, F6 or F7 below.

## Verdict (three sentences)

The network's small ranking edge comes from a look-ahead leak. The market-cap features multiply
split-adjusted closes by as-filed share counts, so every future split reaches the past: NVDA in 2019
shows up as a $1.9B company with a 255% earnings yield. On a universe with those rows removed, the
NN's top-20 spread falls from +0.48% to +0.08% (t 0.25). LightGBM's weak edge mostly survives the
fix, the "size of the move" result is real but is mostly what a linear risk model already gets, and
the nightly loop is a nightly re-roll with a noise-level promotion gate, not a learner. The most
urgent finding is outside the lab: the spliced tickers in `prices_deep` are in today's live ranking
(JAN is rank 2) and in 31 of 312 frozen books, several of which are in TRIAL-LIB-FWD-TWIN-1.

## What was checked and found CLEAN

So that the findings are read in proportion:

* **Split arithmetic** (`splits.py:30-45`, `check_fold`). A validation label's exit open is at or
  before the first test decision date. Features are taken at the close of t and labels run from
  open(t+1) to open(t+1+h), so no label window overlaps the next block.
* **Label and feature separation** (`table.py:231-261`). The label never uses the close of t.
* **Normalisation.** Cross-sectional ranks and the winsorisation of labels are computed per date
  (`models.py:42-67`). The Platt map is fit on validation only.
* **Fixed hyperparameters.** LightGBM and ridge use fixed parameters, and nothing is tuned on a test
  block.
* **SEC facts** are keyed on the filing date, strictly before t (`table.py:370`). Analyst and news
  events are used only when stamped strictly before day t. The ledger group is never fed to a model.
* **Stamp audit.** `assert_pit` really does raise, and the 0 violations it reports are genuine
  **for the stamps it checks**. The leaks below do not go through a stamp.

## Findings, most severe first

### F1 — CRITICAL. Future stock splits leak into four fundamental features and the price floor

**Where.** `table.py:385-394`: `mcap = close * V["shares"]`, which feeds `f_log_mcap`, `f_ey`,
`f_sy` and `f_bm`. The `close` comes from bars pulled with `adjustment=all`
(`scripts/pull_bars_refresh.py:23-35`), so it is divided by every split and dividend that happens
**after t**. `shares` is the number as filed at t. The repo already knows this defect: it is named
VAL-01 in `backend/services/strategy_library_ext.py:181` and `:849-855`, where the library refused
market cap for exactly this reason. nn_lab reintroduced it.

**Evidence** (measured in this review from the table):

| name, first row of year | f_log_mcap as $ | f_ey |
|---|---|---|
| NVDA 2019 | $1.9B | 2.55 |
| AVGO 2019 | $7.8B | 3.22 |
| CMG 2023 | $0.78B | 1.32 |
| CMG 2025 (after its 50:1 split) | $81B | 0.02 |

A future winner that later splits therefore looks like a deep-value microcap.

**How much it drives the results.** I flagged rows that come before an integer-ratio jump in the
implied share count (a split): 273 symbols have a forward split and 66 a reverse split. Pre-split
rows are **3.4%** of the OOS rows but **17.6%** of the NN's top-20. The controls sit well below that:
momentum's top-20 is 10.1%, trailing vol's 10.6% and LightGBM's 6.5%.

| model (21d) | rank IC, all rows | rank IC, split-clean rows | top-20 spread, all rows | top-20 spread, split-clean rows |
|---|---|---|---|---|
| NN dist | +0.0126 (t 1.15) | **+0.0052 (t 0.48)** | +0.48% (t 1.57) | **+0.08% (t 0.25)** |
| LightGBM | +0.0201 (t 2.32) | +0.0158 (t 1.83) | +1.37% | +1.50% |
| 12-1 momentum (control) | +0.0124 | +0.0094 | +1.91% | +1.30% |

Removing the flagged rows also conditions on the future, so the momentum row is the yardstick for
how much that exclusion costs on its own. The NN loses about 59% of its IC, against 24% for
momentum.

**What the leak explains:**

* The note's point that "the NN's IC is the only one that rises after residualising". The
  residualisation controls use `dv_log` as size (`walkforward.py:37`), not market cap, so a
  market-cap-versus-liquidity mismatch is exactly what survives it.
* Why the NN, with its ranked inputs, exploits the leak more than LightGBM does.

**Second leg: the price floor.** The $3 floor (`table.py:286`) is applied to adjusted closes. That
drops future splitters in early years (NVDA before 2017 is not in the table) and admits future
reverse-splitters that really traded below $3.

**Train/live skew.** Live features at t have no future split in them, so the mapping the model
learned is not the one it is applied to.

**Failure scenario.** The shadow rule takes the NN's walk-forward +0.48% at doubled SE, gets a
posterior of about +0.19%/month (note §6), and sizes positions on a number that is about 0.08%.

**What I would have done:**

1. Drop `f_log_mcap`, `f_ey`, `f_sy` and `f_bm` until market cap is rebuilt on one basis. Either
   join raw prices at the filing date (an `adjustment=raw` pull of those dates), or use the VAL-01
   recipe: raw value at `datadate`, rolled forward by the ratio of adjusted closes.
2. Put the price floor on raw prices, or drop it and keep only the dollar-volume floor.
3. Add a planted-split test: a synthetic 10:1 split after t must not change any feature at t.
4. Rebuild the table and re-run the walk-forward.

### F2 — HIGH. `missing_analyst` flags names that will die

**Where.** `models.py:55-59` (the per-group missing flags) together with `table.py:439-466`. The
revisions file is a 2026 yfinance snapshot, so it covers only names alive in 2026.

**Evidence** (measured, pre-2023 rows):

* Analyst features are missing on **100%** of dead-name rows and on 10.8% of living-name rows.
* **55%** of the rows with analyst data missing belong to names that will die. The base rate is 11.6%.
* The NN's top-20 holds future-dead names at **0.04%**, against a 2.84% base rate and 5.45% for
  momentum's top-20. It avoids deaths it could not have known about.

**Size of the effect on the reported numbers.** Small, because dead rows are only 2.8% of the OOS
rows. Living-only spreads are unchanged: LightGBM +1.42%, NN +0.49%.

**Why it still matters.** The model learns "no analyst coverage means it will be delisted". Live,
missing coverage means something else.

**Fix.** Drop the analyst group's missing flag, and keep the group away from any row whose coverage
is decided by the snapshot. Test it by planting a missing-coverage flag that is correlated with
death and asserting that the flag is not a feature.

### F3 — HIGH. Death coverage stops at 2022, so four of the seven test years are survivor-only

**Evidence** (measured). Dead names by the year of their last row:

| year | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|---|
| dead names | 58 | 129 | 111 | 153 | 96 | **4** | **3** | **7** | **9** |

* Dead rows are 0.5%, 0.5%, 0.3% and 0.2% of all rows in 2023 to 2026.
* Names per date grow from 1,712 (2016) to 2,826 (2026), which is the usual signature of a panel
  selected alive at the end.
* `load_bars` DROPS 51 dead companies because their ticker was later reused (`table.py:113-115`),
  instead of renaming them to `SYM#k`.

**What the table can and cannot show.** IC on living names only equals IC on all rows (+0.0201),
so the dead names that ARE present do not drive the result. The bias sits in names that are absent
altogether, and the table cannot measure that. **UNVERIFIED magnitude.** Seven test years cannot
separate 2020-22 (with deaths) from 2023-26 (without).

**Fix.** Before quoting any 2023-26 number, find out why the inactive list stops at 2022.
`pull_delisted_bars` or the vendor list is the first suspect.

### F4 — HIGH, LIVE, MOST URGENT. The spliced tickers are in today's ranking and in frozen books

**Blast radius** (measured on `prices_deep/bars.parquet`):

* **17 living symbols** carry an internal gap of more than 20 sessions. The note's "63" counts
  the delisted file as well, and it also counts genuine suspensions of the same company. NBIS
  (Yandex, then Nebius, 44 sessions) is one, and splitting it is itself a false positive.
* **11 of the 17** resume inside the 12-1 momentum window: ITG, HAWK, PS, XE, JAN, CCXI, LIFE,
  AKTS, WLTH, NP and VIA.
* For those names, `xs_ranker`'s 12-1 momentum compares a new company with a dead one:

| symbol | last price of the old company | first price of the new company |
|---|---|---|
| JAN | $2.12 (2024-07-12) | $23.34 (IPO, 2026-03-20) |
| LIFE | $1.85 | $16.85 |
| AKTS | $0.04 | $22.40 |

**Live path.** `sim_run.py:419` builds its ranking from
`XR.load_bars(XR.survivorship_free_paths())`, which is `prices_deep` plus the delisted file.
`pc_book/2026-09-28/ranking.json` ranks **JAN #2 of 25**.

**Frozen books** (`llm_portfolio/books.jsonl`):

* **31 of 312** books hold at least one spliced name.
* The largest combined weights are 26.5% (`lib_qc470_mom252_quarterly_riskparity_lead_2026-09-27__control`,
  with JAN at 15%) and 26.3% (`lib_mom_12_1_ivw_lead_2026-09-27__control`).
* `lib_mom_12_1`, `lib_mom_12_1_q`, `lib_mom_no_downgrades`, `lib_disp_short_avoid` and their `__ew`
  variants hold JAN, LIFE and AKTS at 5% each. Their theses say "12-1 momentum … score 12.84" and
  "score 15.19", and those scores are the splice. These `lib_` books are the population that
  TRIAL-LIB-FWD-TWIN-1 compares from the 2026-09-28 open.

**Failure scenario.** The trial reads "momentum book vs twin" on 2026-10-26, and part of what it
grades is a data error that picked three IPOs.

**Fix** (live path, a separate commit, attended):

1. Split reused tickers in `xs_ranker.load_bars`. Tell reuse apart from suspension with an
   asset id or name check, not the gap alone.
2. Re-rank.
3. Add a dated note to the trial record naming the affected holdings. **Do not mutate any frozen
   book.**

### F5 — HIGH. The nightly loop refits and re-rolls; nothing learned accumulates

**Where.** `nightly.py:329-381` and `should_promote` at `:52-67`.

1. **Every night trains from scratch** on new seeds. Nothing reads `grades.jsonl`. There is no
   warm start and no ensemble across nights. The only things that accumulate are table rows and
   the seed ledger.
2. **Promotion is a coin flip.** Challenger and incumbent both early-stopped on the block they are
   compared on. Within one seed, validation IC swings from −0.015 to +0.064 between epochs (fold
   2020, seed 813075358, from the receipt). From the walk-forward receipt, NN IC has
   SE 0.0109 × √80 ≈ 0.10 per 21-session block, so a 26-date validation block (about 6.5
   blocks) has an SE of about **0.04**. The margin of 0.005 is about one eighth of an SE.
3. **It promotes on nights with no new data.** On DEGRADED nights the loop still trains and can
   promote on an unchanged block. With a 08:30 HKT schedule that is at least two of seven mornings
   (Sunday and Monday) plus US holidays. Each such promotion picks the best of several seeds on
   the same data, so the incumbent accumulates winner's curse, not skill.
4. **The served model is about ten months stale.** Tonight's incumbent trained up to 2025-12-04 and
   predicts 2026-09-25, because the validation block and the embargo come out of the training
   window and the model is never refit on train+val.
5. **The last validation dates are nearly empty.** The validation block runs to 2026-09-09 because
   `latest_split` selects dates where `y_21` is not null. Those last dates hold one or two
   dead-name labels (2026-09-01 has 2 rows, 09-09 has 1). The IC routines skip them today, but
   label availability should come from the calendar.

Where `new_rows_since_last_run` stands: it can go red (0 gives DEGRADED), but DEGRADED exits 0 and
is the NORMAL state two mornings a week, so it cannot tell "the bar refresh failed" from "Sunday".
It should compare the table's last date with the last closed XNYS session, which
`pull_bars_refresh.last_closed_session` already provides. The resumed receipt also re-counts the
previous run's rows (`nightly.py:534`).

On a DEGRADED night, what gets overwritten: the table file is rewritten every night
(`nightly.py:235`), and its tail from 2026-01-15 onward has its side-group features recomputed from
the CURRENT analyst, SEC and news files. Backfilled vendor rows therefore enter old rows with stamps
earlier than t, and no "first seen" date is recorded (**UNVERIFIED** magnitude). No receipt carries
a hash of the table, so the walk-forward receipts point at a file that no longer exists
byte-for-byte. Predictions were not overwritten (ALREADY_FROZEN). The challenger's checkpoints and
seeds were written.

### F6 — MEDIUM-HIGH. The append step will refuse on ordinary weekdays

**Where.** `nightly.py:210-234`.

**Mechanism.** The old table holds yesterday's live (off-grid) rows. The rebuild keeps grid dates
plus TODAY's live rows only. Whenever today's eligible count is below yesterday's,
`len(new) < len(tab)` and the step raises "table would SHRINK". The night then FAILS with no
predictions and exit code 2.

**Status.** Derived from reading the code, not observed. **UNVERIFIED by execution.** I would
expect it on a large share of off-grid nights.

**Fix.** Count only grid rows in the shrink and label guards, or keep live rows in their own file.

**Related** (`nightly.py:504-510`). A night that fails after `append` leaves `done.append`, and the
NEXT night reuses it without checking the date, so it silently skips that night's append. The
90-minute time box is checked only between steps.

### F7 — MEDIUM. Frozen predictions: honest entry, but weak immutability and a survivor-biased grader

**Entry convention.**

* It is honest: 2026-09-25 features, written 09-28 14:19 UTC, so entry is the **09-29** open,
  because the 09-28 13:30 UTC open came before the rows were written.
* It is mismatched to training, which enters at t+1. This file skips a whole session. The scheduled
  00:30 UTC runs will line up.
* 13:30 UTC is conservative in winter too.

**Immutability.**

* The prediction files are gitignored, and the only guard is a filename glob (`nightly.py:421-424`).
* The grader never checks the file's sha256 against the receipt (`:244-248`, `:262-270`).
* `prediction_id` hashes the date, symbol, horizon and model, but **not the values**, so a
  rewritten file would be graded under the same ids.

**Fix:** verify the sha against the tracked receipt before grading, include the values in the row
hash, and track a compact append-only copy.

**`in_frozen_book`.** It is 0 in the frozen file. Leave the file alone and write a dated sidecar
correction.

**The grader drops the dead.** `grade_predictions` (`:110-117`) drops any name without an exit bar
(NaN) and takes the median without it. A name that delists during the hold therefore vanishes from
the forward record, which is F3's survivorship repeated forward. It must exit at the last close,
the way `table._labels_block` does. It also reads `prices_2025_26` only, and 16 of the 2,903
predicted names are not in it.

**Universe.** The universe includes ETFs and ETNs such as VXX, SILJ, BKCH and OILU.
`INDEX_PROXIES` excludes only seven index ETFs, so structural decay becomes free "skill".

### F8 — MEDIUM. The "size of the move" result is real, but mostly not the network

All numbers here were measured in this review from the v3 OOS frame, with SEs over 21-session blocks.

**The builder's comparison holds.** At 21 days, the NN's width minus trailing vol in rank IC with
|excess| is **+0.0202 (SE 0.0015, t 13.9, 80 blocks)**. It is positive in every hold year:

| year | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|
| NN width minus trailing vol | +0.024 | +0.013 | +0.022 | +0.017 | +0.019 | +0.032 | +0.012 |

It is the same at 5 days (t 13.9) and 63 days (t 8.4). On living names only it is unchanged
(0.357).

**The fair baseline is a fitted linear risk model, not one trailing volatility.** A ridge of ranked
|y| on ranked PRICE features, walk-forward with the same 63-session gap, reaches **0.352**. That is
about 80% of the NN's gain over trailing vol (0.336). The NN beats that ridge by only **+0.0037 to
+0.0048 (t 4.6 to 5.7)**, and it is negative in 2020. A plain average of vol_21 and vol_63 (0.331)
is below trailing vol.

**Practical size.** Realised |excess| by quintile runs from 5.1% to 15.0% on trailing vol and from
4.9% to 15.3% on the NN width.

**Calibration.** The intervals are too narrow: 90% nominal covers 83%.

**Worth, if it holds.** It is worth using for sizing and for the contest's risk budget, after a
conformal width scale fitted on graded rows. Most of the value comes from a cheap multivariate risk
model, which does not need a GPU or a network. Ship the ridge or LightGBM magnitude model as the
baseline, and keep the NN only if its graded forward width beats that baseline.

### F9 — LOW-MEDIUM. The fundamentals join can pick comparative or restated periods

`_asof` on `filed` (`table.py:323-337`, used at `:370` and `:377`) breaks ties among rows that
share a filing date arbitrarily. **24.8%** of (ticker, filed) quarterly-revenue groups carry more
than one period end, because a 10-Q files the prior-year comparative on the same date. The
"current" value can therefore be last year's quarter or a restated one. This is stale data, not a
future leak, and it adds noise to `f_rev_yoy` and `f_ni_yoy`.

**Fix.** Among rows filed before t, take the latest `end`, then the latest `filed`.

### F10 — LOW. The variant was chosen on test data

`variant_choice.json` picked `dist` over `rank` on the pooled walk-forward TEST IC from
`wf_20260928_full`. It is a choice between only two options and both are about zero, but it is
still a selection on test data. It should have been made on the validation blocks.

## MUST FIX BEFORE COMMIT (nn_lab)

1. **F1.** Remove `f_log_mcap`, `f_ey`, `f_sy` and `f_bm`, and move the price floor off adjusted
   closes. Add the planted-split test, rebuild the table and re-run the walk-forward. In the
   research note, withdraw the NN's +0.48%, the "residual IC rises" reading, and the +0.19%/month
   posterior in §6.
2. **F2.** Drop the analyst missing flag, and keep snapshot-covered groups away from rows whose
   coverage depends on survival. Add a planted-flag test.
3. **F5 (minimum).** Do not train or promote on a night without a new labelled grid date. Freeze
   promotion until graded forward rows exist, and meanwhile keep the incumbent.
4. **F6.** Fix the shrink guard so it counts grid rows only, and make the resume check the date.
5. **F7.** Make the grader exit delisted names at their last close, and verify the file sha256
   against the receipt before grading.
6. **Status line.** Report STALE_BARS against the last closed XNYS session instead of a generic
   DEGRADED. Make a failed or refused night visible through the existing alert channel, not only
   through `nightly.log` and an exit code nobody reads.

**Outside nn_lab, and first in time: F4.** Split the stitched tickers in `xs_ranker.load_bars`,
re-rank, and add a dated note to TRIAL-LIB-FWD-TWIN-1 naming JAN, LIFE and AKTS. The frozen books
are not mutated. This touches the live path, so it needs its own attended commit.

## OWED LATER

* **F3.** Death coverage for 2023-26, and rename the 51 dropped dead companies instead of
  dropping them.
* **Recency.** Refit on train+val with the chosen epoch count before predicting, so the served
  model is not ten months stale.
* **Accumulation.** Average the ensemble over the last N nights' models, and warm-start from the
  incumbent.
* **Calibration.** A conformal width scale and a reliability weight, both updated from
  `grades.jsonl`.
* **F8.** A fitted magnitude baseline (ridge or LightGBM on |y|) in every walk-forward receipt.
* **F9.** The comparative-period join.
* **Universe.** Remove ETFs and ETNs.
* **Tamper evidence.** A sha256 of the table on every receipt.
* **F10.** A validation-block variant choice.

## Should `AegisNNLabNightly` stay enabled?

**Pause it with the STOP file until MUST-FIX items 1 to 4 land.** That is about a day of work.

The forward grades of a leaky model would still be honest, because live features cannot see a
future split. But:

* the model now freezing rows will be discarded after F1;
* F6 will make a share of nights fail;
* F5 means any promotion it records is noise that will read as "learning".

Registration notes for when it resumes:

* It is set to "Interactive only" and "No Start On Batteries", so it runs only while the owner is
  logged in and plugged in.
* The daily pass finished at about 07:50-08:00 HKT on recent days, which leaves a 30-40 minute
  margin before 08:30 HKT. Nothing checks that the pass finished before nn_lab starts.
* The schedule itself is right: after the US close in both daylight-saving regimes, and after the
  bar refresh.

## What I would have built with the same night

1. **Magnitude first, where the skill is.** A risk model: ridge or LightGBM on |excess| and
   realised vol at 5, 21 and 63 days, with conformal intervals. Graded nightly, fed to position
   sizing and the contest risk budget. Its skill exists today (IC about 0.35 against 0.336) and
   does not depend on any leaky feature.
2. **Direction as a heavily shrunk prior.** One LightGBM on a clean feature set: price features,
   and fundamental ratios that do not use market cap. Its score enters the shrink-to-zero rule only
   through graded forward IC, never through walk-forward t.
3. **Spend the engineering on the loop, not the architecture:**
   * freeze every night's predictions from the champion AND from two or three challengers;
   * grade all of them as horizons mature;
   * promote only on a sequential comparison of graded forward results, pooled over dates, with a
     pre-set stopping rule;
   * update the reliability weight and the interval scale from those grades every night.

   That is the part that improves every night. Refitting on new seeds is not.
4. **Data hygiene before any model:** a planted-split test, a planted-death-flag test, a
   death-coverage-by-year line on every table receipt, and the reused-ticker split applied to the
   shared bar loader, not only inside the lab.

## For the owner, in plain language

The engine is not learning yet. Every night it throws away yesterday's model, trains a new one from
scratch with different random numbers, and keeps whichever scores better on the same six-month
exam. At that exam size the difference between the two is mostly luck. Worse, part of what the
network "knew" was a peek at the future. The price history it trains on is adjusted for stock
splits that happened later, so a company that would go on to split, such as NVIDIA before its big
run, looked cheap and tiny in the past, and the network learned to buy that. Remove the peek and
its stock-picking edge is about zero. The real, honest skill it has is predicting how BIG a stock's
next move will be. That is useful for deciding how much to put in each position, but a simple
model gets about 80% of it.

The shortest path to an engine that learns has four steps:

1. Remove the peek. This is roughly a day of work.
2. Every night, write down predictions from the current model and from a few rivals.
3. Score them only after the outcome is known.
4. Let the scores, not the training run, decide which model is in charge and how much its opinion
   is trusted.

After a few weeks of scored predictions that loop is genuinely improving. Before them, nothing can
honestly claim it is. Separately, and more urgently: a data error in the shared price file makes
three recently listed stocks (JAN, LIFE, AKTS) look like enormous momentum winners, and they are in
today's live ranking and in several frozen trial books. That should be fixed and noted first.
