# ft_lab: fine-tuning a small local LLM to turn news into numbers

Started 2026-09-29. Licence: `PRODUCT_EXPERIMENT`. **No broker authority, not wired into
anything live.** Nothing in `backend/`, `scripts/` or `engine/` imports this package.

The question the owner asked: can a fine-tuned local model turn non-numeric text (news
psychology, events) into numbers cheaply, and do those numbers help predict the SIZE of the
next move? Direction is not the goal: no LLM here has predicted direction
(`docs/WHAT_WE_ALREADY_KNOW_LLM.md`).

First-run write-up: `docs/research_notes/2026-09-29/ft_lab_first_run_2026-09-29.md`.
Receipts: `backend/data/optimus/ft_lab/receipts/` (`dataset.json`, `baselines.json`,
`first_run.json`, `deepseek_arm_runs.jsonl`, `infer_runs.jsonl`).

## What it does

| module | job |
|---|---|
| `dataset.py` | One row per (symbol, entry_date) news cell of the E1 text-return panel, joined to trailing priors from `prices_deep` (all as of the session BEFORE entry) and to the target \|x_oc\| (entry open to close, minus SPY). Time split train 2025 / val 2026-01-16..04-30 / test 2026-05-15..09-28 with a 10-session embargo. `assert_time_split` and `assert_features_pit` refuse a leak. Also the extraction table: DeepSeek's typed-event rows (teacher labels, not ground truth). |
| `baselines.py` | Vol prior, ridge on trailing priors, + news metadata, + overnight gap, TF-IDF ridge, bge-small ridge, and DeepSeek's own typed fields. Alpha chosen on validation only. A second 2025 fold gives a by-year reading. |
| `evaluate.py` | Per-date cross-sectional Spearman IC, SE over weekly blocks, MDE = 2.8 x SE beside every t, by month, leave-one-month-out, tercile accuracy, absolute-bucket accuracy. |
| `deepseek_arm.py` | DeepSeek zero-shot on a small sample (project interpreter; own dollar cap): news psychology (tone, emotion, uncertainty, surprise, management confidence, novelty, attention) plus a size bucket. Train-period rows become teacher labels; test-period rows are the paid baseline. |
| `train_size.py` | LoRA on Qwen2.5-0.5B with a regression head: text -> the part of size the numeric prior misses. |
| `train_extract.py` | LoRA SFT on Qwen2.5-1.5B-Instruct: text -> typed-event JSON and psychology JSON (distillation from DeepSeek). |
| `infer.py` | Batched generation, base zero-shot vs student, pages per minute. |
| `analyze.py` | Grades everything into `first_run.json`. |
| `loader.py` | `load_extractor()` -- one function returning a callable, for a future digest job. |
| `safety.py` | RAM floor, VRAM cap, awake-time box, STOP file, working-set trim. |

## Run

```bash
# one-time: its own interpreter (CUDA torch); the project's .venv is untouched
py -3.12 -m venv ft_lab/.venv
ft_lab/.venv/Scripts/python.exe -m pip install torch==2.11.0 --index-url https://download.pytorch.org/whl/cu128
ft_lab/.venv/Scripts/python.exe -m pip install -r ft_lab/requirements.txt
ft_lab/.venv/Scripts/python.exe -m ft_lab.fetch_models          # free open weights into the HF cache

ft_lab/.venv/Scripts/python.exe -m ft_lab.dataset               # ~40 s
ft_lab/.venv/Scripts/python.exe -m ft_lab.embed                 # ~1.5 min on the GPU
ft_lab/.venv/Scripts/python.exe -m ft_lab.baselines             # ~1 min, CPU
.venv/Scripts/python.exe -m ft_lab.deepseek_arm --n-train 2500 --n-test 1000   # PAID, ~$0.27
# the GPU stages, one at a time, launched detached with a log and a recorded PID:
#   Start-Process ft_lab\.venv\Scripts\python.exe -ArgumentList "-m","ft_lab.run_first" -RedirectStandardOutput ft_lab\runs\run_first.log ...
ft_lab/.venv/Scripts/python.exe -m ft_lab.analyze

# tests: synthetic data only, no GPU, no network
ft_lab/.venv/Scripts/python.exe -m pytest ft_lab/tests -q -p no:cacheprovider
```

To stop a training stage: create `ft_lab/runs/STOP` (checked every step). Kill only by the PID
written to `ft_lab/runs/<stage>.pid`, never by image name.

## Machine safety, as run

* A GPU stage refuses to START below 3 GB available RAM, or when another process holds >20% of VRAM.
* Mid-run it PAUSES (trims its own working set, waits) below 2 GB. This is a stated deviation
  from the 3 GB rule: the machine had only 2.7-4.8 GB available before any ft_lab process
  started, and a CUDA process holds ~1.3 GB after a trim, so a 3 GB mid-run floor could never
  be met (`config.RUN_FLOOR_RAM_GB`).
* VRAM capped at 78% of the card per process; bf16 LoRA (no bitsandbytes needed at these sizes).
* Training is time-boxed in awake minutes (35 + 45), checkpointed, and stoppable by file.

## Honest limits

* Extraction labels are DeepSeek's readings. Agreement with them measures mimicry, not truth.
* The target is open-to-close from the first open after publication; the overnight gap (where
  most of an after-hours reaction lives) is excluded by construction because it is not tradable
  from the news time. The at-open prior uses the gap as a feature, reported separately.
* The news panel starts in 2025, so "by year" is two folds (2025 H2 and 2026 May-Sep).
* The panel inherits the E1 survivorship caveat (symbols alive on 2026-09-01).
