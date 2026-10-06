# Review: C5, nn_lab membership freeze (2026-10-06)

Adversarial second review of chunk C5 (`nn_lab/membership.py`, `nn_lab/nightly.py` step_append, receipt fields and tournament, `nn_lab/table.py price_rows(force_keys=...)`, `nn_lab/tests/test_membership_freeze.py`). I did not edit the build, commit anything, or run the nightly. What I did run: the nn_lab tests, the read-only audit, and read-only pandas over the receipt, `revisions.parquet`, the live table and the pre-run copy.

## VERDICT: MERGE WITH FIXES

The mechanism does what it says at the level it says it: the table no longer refuses on a vendor re-adjustment, and stored rows are byte-identical. I checked that independently. What it does not do is what the docstring and the owner's sentence claim. It freezes **the vintage in which a row was first stored**, not **what the model knew at the decision date**, and the forecast's actual inputs are never stored anywhere. Fixes 1-6 below are required before merge. 7-10 can follow.

Required fixes:
1. Rename the claim. The docstring, note and receipt say "frozen first-stored vintage", not "what the model knew". Either persist the live feature matrix next to each frozen forecast file or say in words that it is not persisted (F1, F2).
2. Put a status on a non-zero `member_absent_from_rebuild`: night status DEGRADED with the count. Today up to 2,001 absent members a night pass silently (F5).
3. Move `MAX_DROP_SHARE`, `MAX_DROP_FLOOR`, `REL_TOL`, `ABS_TOL` and `LABEL_REVISION_MIN_ABS` into `nn_lab/config.py`, print their values on the receipt, and add boundary tests (F4).
4. Stamp the tournament block on the receipt itself with `age_days`, a `same_table_as_tonight: false` flag, and the note's own sentence "before the CRSP-deaths rebuild". Add mom_12_1 to the verdict's baseline set (F7).
5. Add the health contract in F8. A seventh unseen refusal is the failure this chunk was built to end.
6. Write `revisions.parquet` after the table write succeeds, not before (F6).

## Evidence I produced

- `AEGIS_PERSONAL_MODE=0 AEGIS_IGNORE_DOTENV=1 python -m pytest nn_lab/tests -q`: **68 passed in 5.44s**.
- `python -m nn_lab.membership`: **exit 0**, `"dates_checked": 516, "n_moved": 0, "status": "OK: no frozen date moved"`, `receipts_with_hashes: [nightly_20261006T155130Z.json]`. That is a single receipt, so the cross-receipt half of the audit has not yet run against anything.
- Independent check against the pre-run copy (`train_table_before_20261006_membership_freeze.parquet`):
  - Membership hashes: 515 → 516 dates, **0 moved**.
  - Feature cells changed on stored grid rows: **0**.
  - Stored non-null labels changed: y_5 **0**, y_21 **3**, y_63 **39**. That is 42, matching `labels_provisional_replaced: 42`.
  - Labels filled: 2,956 / 2,986 / 2,910, which sum to the receipt's 8,852.
  - **Only 35 of the 515 dates were exposed to the merge** (grid dates ≥ the 2026-01-15 tail floor). The other 480 are copied verbatim as `head`, so "all 515 frozen hashes byte-identical" is true but tests the merge on 35.
- `revisions.parquet`: 10,394 rows, 380 KB.
  - By kind: FEATURES_REVISED 5,885 · LABEL_REVISED 4,505 · MEMBERSHIP_WOULD_DROP 4.
  - 99.4% of feature revisions carry the "adjusted close rescaled" reason. Rescale factor: median −0.64%, 5th percentile −3.4%, worst −7.9% (5,852 rows, 188 symbols, dated 2026-01-20 → 2026-09-23).
  - Columns most often revised: `ret_1` 5,663, `mom_5` 5,514, `beta_63` 5,460, `mom_21` 5,288, `dv_log` 2,941, `med_dv` 235.
  - Feature `max_rel_change` median 3.6%, p99 3.6×.
  - LABEL_REVISED |Δ|: median 1.9 bp, p90 5.0 bp, max 47 bp.

## Findings

### F1 (HIGH): the frozen value is a vendor vintage, not a point-in-time value

Code path:
- `table.py` `_price_block` computes `dv = c * v` from the **adjusted** close (`table.py:190-195`), then `med_dv`, `dv_log`, `amihud_21` and `dv_trend_*` from it.
- Eligibility is `med_dv >= MIN_MEDIAN_DOLLAR_VOL` (`table.py:314`).
- The comment at `table.py:313` says "adjusted close x adjusted volume = unadjusted dollar volume". That holds for **splits only**. A dividend back-adjustment scales price and leaves volume alone, so every dollar-volume level on a date d embeds every dividend paid between d and the night the row was computed.
- `config.USE_CLOSE_RAW = False` (`nn_lab/config.py:137`), so the raw-price path that would fix this is off.

Consequences:
- The 35 exposed tail dates were first stored by builds whose bars were adjusted through late September. The stored `med_dv` for 2026-01-20 therefore already contains up to eight months of later dividends.
- The four would-drop rows are exactly this effect crossing the floor: EQBK stored 3,007,646 → rebuilt 2,994,202 (−0.45%), THFF 3,002,204 → 2,979,512, ISTR 3,000,933 → 2,988,622.
- Freezing keeps one look-ahead vintage instead of another. The owner's goal ("what the model knew at prediction time is never rewritten") would be met by computing liquidity from unadjusted prices, not by freezing.

Ratio features (`mom_*`, `ret_1`, `px_*`) are invariant to a clean back-adjustment in exact arithmetic, so their look-ahead is nil. Their revisions are rounding noise (see F3).

Severity is HIGH on the claim, LOW-MEDIUM on the numbers: a −0.64% median rescale moves `dv_log` by ~0.006 against a cross-sectional sd of 1.45.

### F2 (HIGH): the table never held what the forecast knew

- `step_freeze` scores the live rows: `tab[tab["date"] == dd]`, the newest date, usually off-grid (`nightly.py:449-451`).
- The frozen prediction file stores `symbol, horizon, scores, in_frozen_book`. It stores no feature vector (`frame()`, `nightly.py:461-462`).
- On the next night, `merge_frozen` replaces yesterday's off-grid live rows (`membership.py:203-205`).

So the inputs behind a frozen forecast are discarded within 24 hours, whatever this chunk freezes. The rows that are frozen are the weekly grid rows the forecasts were **not** made on. The owner's sentence "freeze membership once a forecast has been generated" is not keyed to forecasts at all: every stored grid date is frozen whether or not a forecast exists.

Fix: write `X` (or its sha256 plus the live rows) beside each `pred_*.parquet` and put its hash in the frozen ledger row. That is the point-in-time record, and it costs about 6k rows a night.

### F3 (MEDIUM): the revisions log is about 99% rounding noise, and its thresholds are inconsistent

- Features use a relative tolerance of 1e-4 with an absolute floor of 1e-7 (`membership.py:53-54`). The vendor re-rounds adjusted prices to cents after rescaling, so a $20 stock's `ret_1` moves by ~2.5e-4 absolute. That is a few percent of a 1% return, and it is logged. Hence a median feature `max_rel_change` of 3.6% on `ret_1`, `mom_5` and `beta_63` while no genuine information changed.
- Labels get a 1 bp absolute floor (`LABEL_REVISION_MIN_ABS = 1e-4`). Features get none.
- Result: a 10k-row first night whose signal (the four eligibility crossings and a handful of real dividend-spanning labels) is buried.

Fix: one materiality rule per column family, absolute for returns (e.g. 1 bp) and relative for levels (e.g. 0.5% on `med_dv`), declared in config and printed on the receipt.

### F4 (MEDIUM): thresholds are module constants, untested at the boundary

- `MAX_DROP_SHARE = 0.02`, `MAX_DROP_FLOOR = 100`, `REL_TOL`, `ABS_TOL` and `LABEL_REVISION_MIN_ABS` live in `membership.py:49-58`, not `nn_lab/config.py`.
- Only `drop_cap: 2001` is printed on the receipt. The 1 bp value appears only inside a key name.
- Boundary behaviour:
  - `n_drop > cap` (`membership.py:328`), so exactly 2,001 drops pass.
  - `abs(ry - sy) > 1e-4` (`membership.py:281`), so exactly 1.0 bp is not logged.
  - No test pins either side. `test_a_rebuild_that_loses_a_large_share...` uses a large share, and no test covers the label threshold.
- Compounding question: **no**. A 0.9 bp-per-night drift cannot compound unlogged. Each night compares the rebuild against the **stored** value (`sy`), not against last night's rebuild, so cumulative drift is logged the first night it exceeds 1 bp. That is correct, and it deserves a test because it is the property a later refactor will break.
- Answering the "1 bp" question needs the 43,389 "changed under 1 bp, not logged" count. It is on the receipt, which is good.

### F5 (MEDIUM): the shrink guard got weaker, and silently

- Before C5, one lost stored row refused the night.
- Now up to `max(100, 2% × 100,074) = 2,001` stored members per night can be `MEMBER_ABSENT_FROM_REBUILD`. That is a symbol missing from the bars entirely, which is the truncated-file signature, not a dividend. They are kept, revised, and the night is still `OK`.
- `night_status(new_rows, stale=...)` never reads `mstats`. A partial bars file that drops 15 names × 35 dates (525 rows) would be invisible at status level.

Fix: absent > 0 → DEGRADED with the count in `evidence`. Absent and would-drop deserve separate caps; a dividend crossing and a missing symbol are different failures.

### F6 (LOW-MEDIUM): write order, and a back door in the frozen check

- `append_revisions` runs **before** the table write and verify (`nightly.py:227-232`). If the table write fails, the log holds revisions from a run whose table never landed. De-duplication then suppresses them on the retry, so the retry's log omits them.
- `hashes_before` is taken **after** the ETF exclusion drops stored rows (`nightly.py:186-193`). Adding a symbol to the exclusion list therefore removes stored members from frozen dates without `check_frozen` noticing. Only the cross-receipt audit would catch it.

Fix: write revisions after `os.replace` succeeds. Compute hashes before the ETF drop, and report ETF-removed keys as their own declared kind.

### F7 (MEDIUM): the tournament is stale, and the verdict omits the simplest baseline

- **Staleness.** The receipt's `walk_forward.note` says "printed from the receipt, not refit tonight ... computed on the table as it stood then", with `written_utc 2026-09-28T15:34:25` and that run's table sha (`ac8f70c4...`, tonight's is `0a4450e1...`). That is labelled. Two things are missing from the receipt:
  - an age in days;
  - the note's own sentence that it was computed **before the CRSP-deaths rebuild**, i.e. on a different survivor set. That sentence lives only in the research note.

  The receipt file name `wf_20260929_post_review.json` against `written_utc 2026-09-28` will confuse the next reader.
- **The verdict compares the NN only to max(ridge, lgbm).** 12-1 momentum, a single column, beats the NN at every horizon on the same receipt: 0.0152 / 0.0126 / 0.0142 against 0.0089 / 0.0008 / 0.0112. It also beats LightGBM at h5. Its top-20 net is the best or second best at h21 and h63 (0.0194 and 0.0621). Leaving the cheapest model out of the comparison flatters the trees too.
- **The t-stats are not independent.** h21 has 80 weekly blocks with a 21-session overlap, so the effective count is about 20, and the lgbm t of 2.04 is inflated by roughly sqrt(4). No `by_year` or `leave_one_year_out` is printed (CLAUDE.md protocol item 11).
- **The §7 shape (backtest presented as earned) is not repeated.** `trust.*.source: "prior_only"`, `walk_forward_used: false`, and every per-model line says `weight 0.0 (was 0.0)` with `neutral (no-view) sleeve h21 1.0`. One plain sentence is still missing: "the ensemble carries zero weight; the book holds the neutral sleeve; no model has earned anything."
- **In-sample validation IC is three to five times the walk-forward IC.** The NN's `val_ic_by_epoch` peaks at 0.034-0.045 tonight against a walk-forward 0.0089 at h5. The receipt should print that gap beside the tournament, because it is the overfit the tournament is meant to expose.

### F8 (MEDIUM): refusals are still invisible outside the receipt

- `nightly.__main__` exits 2 on REFUSED or FAILED (`nightly.py:885`), and `run_nightly.cmd` would surface it.
- `system_health.p_scheduled_tasks` deliberately reports every task not in `_TASK_RECEIPT` as UNKNOWN ("Last Result is cmd's rc, not the job's", `backend/services/system_health.py:1652-1674`), and `AegisNNLabNightly` is not mapped.
- Six non-OK receipts in a row (10-02 → 10-06: five TableShrink FAILED, one LOW_MEMORY REFUSED) therefore turned nothing red. Nothing in C5 changes that.

Proposed one-line contract:

> `nn_lab_nightly`: newest `nn_lab/receipts/nightly_*.json` must have `status ∈ {OK, DEGRADED}` and `written_utc` < 26 h old. Otherwise REFUSED (status REFUSED/FAILED, detail = `refused`/`error` + count of consecutive non-OK receipts) or STALE (older than 26 h). Mapped as `_TASK_RECEIPT["AegisNNLabNightly"] = "nn_lab_nightly"`.

### F9 (LOW): the revisions log is lossy and not tracked

- De-duplication on `(date, symbol, kind, rebuilt_values_hash)` (`membership.py:370-375`) does not collapse two genuinely different revisions on the same key unless their rebuilt values hash equal. Different horizons' LABEL_REVISED rows survive, as the 1,916 repeated `(date, symbol, kind)` triples show.
- It is a set of seen states, not a timeline. A vendor flip B → A → B records B once and the reversion never. A → (stored) produces no row, because it equals the stored value.
- `columns` is not in the key.
- Growth: 10,394 rows and 380 KB on night one. Later nights should mostly de-duplicate, but the rebuild re-diffs ~100k tail rows nightly and rounding noise (F3) will keep minting new hashes whenever the vendor re-rounds. There is no rotation, and the whole file is read, concatenated and rewritten every night. That is fine for a year at this rate and wasteful at the current noise level.
- `table/` is gitignored, so the "append-only, never removed" record of vendor changes is an untracked local file with no tamper evidence. At 380 KB it can be tracked, or its sha can go on each receipt.

### F10 (LOW): final labels are frozen, which goes beyond the owner's decision

- A label is an outcome, not something the model knew at t. Freezing a **final** label (`membership.py:279-295`) keeps a value the vendor has since corrected. A window spanning a newly adjusted ex-date becomes a total return, and the corrected value is the more accurate one.
- Worse case: a name flagged `dead` after a 10-session halt (`DEAD_GAP_SESSIONS = 10`) gets a last-close exit label. Once final, that wrong delisting label is frozen permanently even after the name resumes.
- Tonight's impact is small (median 1.9 bp, max 47 bp), so this is LOW. The principle should flip: freeze features and membership, take the best-known label for training, and log the change.
- Provisional-label replacement is **not** a leak surface. Training restricts to `labelled_dates` (`nightly.py:377, 391, 410`), and forward grades are recomputed from bars by `loop.step_grade`, never read from the table. A label rewritten before its window closes never touches a graded forecast.

### F11 (LOW): the receipt was not written by the reviewed code

`receipts/nightly_20261006T155130Z.json` was written about 40 s before the last edit to `membership.py`. Its `revisions.path` is an absolute local path, while the reviewed `_rel()` returns `backend/data/optimus/nn_lab/table/revisions.parquet`. The difference is cosmetic, but the receipt cited as evidence comes from a slightly different build. Let the next scheduled night produce the evidence receipt, and cite that one. Model paths on the receipt are also absolute local paths; that predates C5.

### Tests

The tests are sound. The two refusal tests monkeypatch `step_append` or `refuse_reason` to raise. They assert that `main()` turns the raise into a REFUSED receipt with `evidence` and `table_before`, which is the wrapper's behaviour, not the mock's return. No test asserts its own mock.

Gaps:
- the 1 bp and 2% boundaries;
- "drift is measured against stored, so it cannot compound unlogged";
- revisions written after a failed table write;
- an ETF-list change moving a frozen date;
- `MEMBER_ABSENT_FROM_REBUILD` changing the night status (it does not today).

## What I would have done instead

1. **Fix the cause, not the symptom.** Compute `med_dv` and every dollar-volume feature from unadjusted close × unadjusted volume (`USE_CLOSE_RAW`, raw_prices), or from a dividend-only de-adjustment factor. Then a dividend re-adjustment cannot move eligibility at all. The 10-01 refusal disappears at the root, and stored liquidity is point-in-time instead of a frozen vintage.
2. **Make stored rows immutable and stop rebuilding them.** Snapshot `(date, symbol)` membership plus a vendor-vintage stamp per grid date (a few KB). Only append new dates. Compute pending labels from bars for the stored keys. Persist the live `X` beside each frozen forecast. No nightly 9-month re-diff, no 430-line merge, no noise log. If vendor drift matters, a weekly diff job with a materiality threshold can report it. Is the freeze worth its complexity over a per-date universe snapshot? Its immutability rule is right. Rebuild-then-reconcile is the expensive way to get it, and on night one its output is 99% rounding noise.
3. **Spend tonight's GPU on deciding whether the NN stays, not on refitting it.**
   - Re-run the walk-forward once on **today's** table (post CRSP-deaths) for NN, ridge, LightGBM and mom_12_1.
   - Use non-overlapping blocks, by_year and leave-one-year-out.
   - Put mom_12_1 in the verdict's baseline set.
   - If the NN still loses to a single column at every horizon, stop the nightly NN refit and train the three cheap models only.

   The roster's zero weights make the nightly NN fit pure cost until forward grades exist, and the first h=5 grades arrive this week whatever the GPU does.

## Score: 64 / 100

The engineering is careful: byte-identical stored rows (verified), a refusal that writes a receipt, an audit with a refusing exit, a tournament the receipt does not oversell. Points come off because:
- the headline claim (point-in-time freeze) is not what the code delivers (F1, F2);
- the guard got silently weaker (F5);
- the thresholds are undeclared and untested (F3, F4);
- the refusal is still invisible outside the receipt, which is the failure that started this chunk (F8).
