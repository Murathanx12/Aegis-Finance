# nn_lab: the nightly-improving cross-sectional model

Started 2026-09-28. Licence: `PRODUCT_EXPERIMENT`. **No broker authority.** It writes
predictions and grades them, and places no orders.

This is a separate lab. It reads the project's data files: bars, SEC facts, analyst
revisions, the news panel and the forecast ledger. It imports nothing from the live
decision path, and nothing in `backend/`, `scripts/` or `engine/` imports it. A test
(`test_nn_lab_is_not_imported_by_the_live_path`) pins both directions.

## What it does

| module | job |
|---|---|
| `table.py` | Builds ONE point-in-time training table from `prices_deep` (living names) plus `bars_delisted` (dead names). A row is (weekly decision date t, symbol). Features are known at t's close. Labels are open(t+1) to open(t+1+h) for h = 5, 21, 63, minus the cross-sectional median of that date. Each feature group carries its own availability stamp. `assert_pit` raises if any stamp is on or after t. Fundamentals are keyed on the SEC **filing** date, never the period end. |
| `splits.py` | Walk-forward: expanding train, then a 63-session embargo, then a 26-date validation block, then another 63-session embargo, then one test year. |
| `models.py` | Feature preparation (per-date ranks, median-imputed, one missing flag per group) and the baselines: zero, 12-1 momentum, trailing vol (magnitude), ridge, and LightGBM with the library defaults. |
| `nn.py` | A small MLP (256-128-64, dropout 0.15, AdamW with weight decay, early stopping on the validation block). For each horizon it predicts a mean, five quantiles and P(beat the median). The `rank` variant swaps the mean loss for a per-date ListNet loss. |
| `evaluate.py` | Rank IC with standard errors over DATE BLOCKS, top-20 minus the panel's random portfolio net of the band costs, the reliability table and Brier score, interval coverage, results by HOLD year, leave-one-year-out, the mean without the best 5 months, the verdict, and the reliability weight. |
| `walkforward.py` | The only evaluation that gets reported. Receipt: `backend/data/optimus/nn_lab/receipts/wf_*.json`. |
| `nightly.py` | The loop (rebuilt 2026-09-29 after the review): append (shrink guard on the TABLE), grade, trust, fit (only on a new labelled grid date, train+val), freeze every roster model + the ensemble + the size forecast, receipt. No promotion on a validation block. |
| `membership.py` | Frozen membership (owner decision 2026-10-06; amended after review C5 on 2026-10-07). What is frozen is the **first-stored vintage** of each grid row: its membership and its feature values as computed on the night the date was first stored. That is point-in-time only for grid dates first stored from 2026-10-06 at lag 0 (`membership_vintage.jsonl` records the lag per date). A rebuild may add new dates. It sets labels to their best-known value, because a label is an outcome; a final label is replaced, and the change logged as `LABEL_RECOMPUTED`, only when it moved by more than 1 bp. Every material vendor change to membership or features is appended to `table/revisions.parquet` and never applied. `TableShrink` refuses a genuine shrink, and a rebuild that cannot reproduce more than 2% of stored membership (absent and ineligible capped separately). Smaller counts above the declared levels make the night DEGRADED. Every threshold is in `config.py` and printed on the receipt. `python -m nn_lab.membership` audits that no frozen date moved. |
| `health.py` | `nn_lab.health_contract()`: ALIVE when the newest nightly receipt is OK or DEGRADED and under 26 h old. Otherwise REFUSED (with the reason and the count of consecutive non-OK receipts) or STALE. With no receipt it is UNKNOWN, never ALIVE. |
| `loop.py` | Freeze (immutable file per date x model, sha256 in `frozen_ledger.jsonl`), grade (sha verified; a delisted name exits at its last close, never dropped), trust (posterior mean rank IC from FORWARD graded blocks only, prior N(0, 0.03^2), 11-block prior strength, shrunk per model by its own block count; the walk-forward is printed, never used: amended 2026-09-29), ensemble (weight = trust / TRUST_FULL_IC, never renormalised; the rest is a neutral no-view sleeve, so with no forward grade the ensemble is the zero), the model in charge (only a model with positive forward trust; otherwise the zero), the size-of-move choice and conformal intervals. |
| `seeds.py` | Every seed any run used is recorded. A night draws outside that set, so no night is a replay. |

## Run

```bash
# one-time: its own interpreter (CUDA torch); the project's .venv is untouched
python -m venv nn_lab/.venv
nn_lab/.venv/Scripts/python.exe -m pip install -r nn_lab/requirements.txt
nn_lab/.venv/Scripts/python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cu128

nn_lab/.venv/Scripts/python.exe -m nn_lab.table                 # ~75 s, ~1.1M rows
nn_lab/.venv/Scripts/python.exe -m nn_lab.walkforward --seeds 3  # ~8 min on the GPU
nn_lab/.venv/Scripts/python.exe -m nn_lab.nightly                # the nightly loop

# tests: synthetic data only, no GPU, no network
AEGIS_IGNORE_DOTENV=1 AEGIS_PERSONAL_MODE=0 .venv/Scripts/python.exe -m pytest nn_lab/tests -q -p no:cacheprovider
```

## To stop the nightly loop

Create `backend/data/optimus/nn_lab/STOP`. The loop refuses by name while that file
exists. To remove the scheduled task:
`schtasks /Delete /TN "AegisNNLabNightly" /F`.

## Honest limits, printed on every receipt

* **Partially survivor-selected.** The living names were chosen alive on 2026-09-01
  with a $3M dollar-volume floor. The dead names come only from the 1,784-symbol
  inactive listed list, so there is no OTC and no death before 2016. A dead name exits
  at its last close, and its true delisting return is unknown.
* **Coverage limits on two groups.** News coverage starts in 2025. The forecast ledger
  starts in August 2026. A group whose coverage in the training rows is below 2% is
  built and printed but never fed to a model.
* **Analyst revisions carry a snapshot bias.** They come from a 2026 snapshot of
  yfinance history, which covers names alive in 2026. Since 2026-09-29 the group is
  NaN for every name before the first snapshot (2026-09-24), and no later-pull group
  carries a missing-indicator (review F2).
* **Dollar volume before 2026-10-06 carries later dividends.** Grid dates before
  2026-10-06 carry adjusted-close dollar volume (`med_dv`, `dv_log`, `dv_trend_*`,
  `amihud_21`, and the $3M eligibility floor). The look-ahead is bounded at a median of
  -0.64% and a worst case of -7.9% of the adjusted close; that dividend rescale was
  measured on 2026-10-06. From 2026-10-06 each new grid date is stored from its own night's
  bars and frozen. Its lag is recorded in `membership_vintage.jsonl`, and at lag 0 no
  later dividend can be in it. No unadjusted daily series is on disk.
* **Each forecast's inputs are saved.** The exact rows a night's forecasts were scored on
  are written beside the frozen files as `frozen/<date>/inputs_<run_id>.parquet`, with
  their sha256 in `frozen_inputs_ledger.jsonl`. The receipt's
  `freeze.frozen_inputs.rescore_reproduces_scores` proves that re-scoring them gives the
  frozen numbers.
* **No market cap, no $3 floor.** Every bar file is split-adjusted, so market cap and
  the three yields need an unadjusted close, which is not on disk; they are NaN, and
  only the dollar-volume floor applies (review F1).
* **The expected result for a network is a loss to LightGBM.** A neural net that cannot
  beat LightGBM on a tabular problem is the usual finding in the literature. It is
  tested anyway, and whatever the verdict, the model still emits a probability. A weak
  model gets a small weight (`evaluate.reliability_weight`), not zero.

## How its output would reach a decision (specified, NOT wired)

See `docs/research_notes/2026-09-28/nn_lab_first_night_2026-09-28.md` §6. In short:
the model is one more component `j` in the shrink-to-zero rule of
`docs/research_notes/2026-09-28/how_the_engine_decides_2026-09-28.md` §(f). Its edge
m_j and standard error se_j come from its **graded forward rows** (`grades.jsonl`), and
from the walk-forward only at doubled SE.
