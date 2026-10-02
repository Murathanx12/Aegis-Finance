# ft_lab first run: fine-tuning a small local LLM for text -> numbers (2026-09-29)

Licence: `PRODUCT_EXPERIMENT` (no claim). Code: `ft_lab/` (own venv, own README). Receipts:
`backend/data/optimus/ft_lab/receipts/` (`dataset.json`, `baselines.json`, `first_run.json`,
`deepseek_arm_runs.jsonl`, `infer_runs.jsonl`). Datasets and weights are gitignored under
`ft_lab/data/` and `ft_lab/models/`. Stopped early on a hard 13:00 deadline; the unfinished parts are
listed under CONTINUE FROM HERE.

## RESULTS SCOREBOARD

**RESULT IMPROVEMENT: NONE for returns. One capability result: a local extractor now works.**

| item | result |
|---|---|
| Best size predictor on the newest block (2026-05-15..09-28, 25,365 cells, 21 weekly blocks) | trailing priors + news counts + TF-IDF (T2): IC **0.4185** vs the free vol prior **0.3996** |
| What the text adds to the size prior | TF-IDF **+0.0069** IC (t 3.44, MDE 0.0056, 5 of 5 months positive; 2025 fold +0.0046, t 4.53). Real, small, and it comes from a bag of words |
| Fine-tuned Qwen2.5-0.5B size head | **+0.0024** over the prior (t 2.34, MDE 0.0029) and **-0.0045 below TF-IDF** (t -2.78, 0 of 5 months ahead): **FAILED_VARIANT** |
| Fine-tuned Qwen2.5-1.5B extractor (typed events), vs the DeepSeek teacher | event kappa **0.78** (base zero-shot 0.20), direction kappa 0.75, magnitude weighted kappa 0.71, 100% valid JSON, n 400 test docs |
| Do extracted fields predict size beyond the prior? | DeepSeek's own typed fields: **+0.0007** (t 0.21, MDE 0.0091). DeepSeek psychology fields: **-0.0106** (t -1.07, MDE 0.028). **CANNOT_DISTINGUISH** from zero |
| Zero-shot size buckets | DeepSeek expected_move IC 0.166 vs vol prior 0.397 on the same 1,006 cells; bucket accuracy 37% vs 39% majority class. Base Qwen-1.5B IC 0.064 (t 1.19) |
| Speed and cost | local student **586 pages/min** at $0; DeepSeek **$0.077 per 1,000 pages** on this short prompt ($0.315 on the typed-event prompt), ~460 pages/min with 6 threads |
| LLM spend | **$0.27** DeepSeek (ledger; $0.51 at peak list price), cap $0.90 |
| Independent selectors / books / forward paper | unchanged; nothing here trades |

## 1. Dataset (from what is on disk; no new collection)

- **Cells**: the E1 text-return panel (348,478 rows) collapsed to one row per (symbol, entry_date):
  **138,763 cells**, 3,029 symbols. Text = first document (title + body, 1,200 chars) + up to three
  more headlines. Target = |x_oc|: open to close of the first session whose open is after
  publication, minus SPY. Priors from `prices_deep` bars, all as of the session BEFORE entry
  (21-session mean |abnormal move|, 21/63-session sd, last move, 21-session dollar volume); the
  overnight gap is kept as a separate "at-open" feature.
- **Split by time**, 10-session embargo between blocks: train 2025-01-02..2025-12-31 (79,435),
  val 2026-01-16..04-30 (26,555), test 2026-05-15..09-28 (25,365). Median |move| 1.26% / 1.64% /
  1.62%. Realised buckets (test): NEGLIGIBLE 18%, SMALL 40%, MODERATE 29%, LARGE 10%, EXTREME 3%.
- **Leakage guards** (`dataset.assert_time_split`, `assert_features_pit`; 10 offline tests pass):
  a random or overlapping split refuses; a feature dated on/after entry refuses; the panel's
  `dollar_vol` is the ENTRY day's (realised during the target session) and is barred.
- **Extraction teacher**: 19,996 DeepSeek-typed panel documents (`typed_events/panel_2026-09-13.jsonl`),
  train 9,641 / val 4,422 / test 5,011; 72% `no_event` in train. Plus 3,500 new DeepSeek
  psychology rows (2,500 train cells as teacher labels, 1,000 test cells as the paid baseline),
  all parsed. **A teacher label is DeepSeek's reading, not ground truth.**

## 2. Size: baselines first, then the fine-tune (test block; IC = per-date Spearman, SE over weeks)

| model | IC | t | MDE | IC vs move/vol | tercile acc. |
|---|---|---|---|---|---|
| B0 vol prior (no fit) | 0.3996 | 31.8 | 0.035 | -0.074 | 0.460 |
| B2 trailing priors + news counts | 0.4116 | 36.9 | 0.031 | -0.022 | 0.462 |
| B3 + overnight gap (at-open) | 0.4225 | 39.3 | 0.030 | +0.007 | 0.469 |
| T1 TF-IDF alone | 0.2625 | 18.4 | 0.040 | +0.066 | 0.412 |
| **T2 B2 + TF-IDF** | **0.4185** | 37.0 | 0.032 | -0.003 | 0.466 |
| T3 B3 + TF-IDF | 0.4255 | 39.3 | 0.030 | +0.019 | 0.471 |
| E1 B2 + frozen bge-small | 0.4162 | 37.8 | 0.031 | -0.005 | 0.463 |
| Qwen-0.5B LoRA head alone | 0.1191 | 8.8 | 0.038 | +0.063 | 0.368 |
| B2 + Qwen-0.5B LoRA head | 0.4140 | 36.8 | 0.032 | -0.011 | 0.461 |

Increments (paired per date): T2 over B2 **+0.0069 (t 3.44, MDE 0.0056)**; bge over B2 +0.0046
(t 2.94, MDE 0.0044); Qwen head over B2 +0.0024 (t 2.34, MDE 0.0029); **Qwen head minus TF-IDF
-0.0045 (t -2.78)**. By month the fine-tune's total IC runs 0.452 -> 0.363 (May..Sep), leave-one-month-out
worst 0.409. Absolute-bucket accuracy is ~42-43% for every numeric model against a 40% majority
class: bucket accuracy is a weak metric here; the rank IC is the one that moves.

Fine-tune details: 52,000 train cells, one epoch, target = residual of B2 (the model is asked only
for what the prior cannot see), best checkpoint by validation IC (step 2,400 of 3,250), mix weight
fitted on validation, graded once on test. Run timings and machine detail:
`backend/data/optimus/local_pc/ft_lab_machine_notes_2026-09-29.md`.

## 3. Extraction: base zero-shot vs the fine-tuned student (agreement with DeepSeek on held-out test documents)

| typed events (n 400 test docs, 62% teacher `no_event`) | base Qwen-1.5B zero-shot | **student (LoRA, 11,392 examples, 29 min)** |
|---|---|---|
| valid JSON | 99.3% | **100%** |
| event type accuracy / kappa | 30.7% / 0.20 | **87.0% / 0.78** |
| event-vs-no-event accuracy | 49.4% | 88.5% |
| accuracy on the teacher's real events | 45.3% | 77.6% |
| direction kappa | 0.29 | 0.75 |
| magnitude weighted kappa | 0.21 | 0.71 |

For scale: the project's earlier L2 inter-prompt kappa for DeepSeek against itself was 0.67-0.87.

| psychology (n 400 test cells) | base zero-shot | student |
|---|---|---|
| valid JSON | 99% | **67%** (off-schema replies; see below) |
| Spearman with DeepSeek: tone / uncertainty / surprise / novelty / attention | 0.64 / 0.08 / 0.30 / 0.23 / -0.14 | 0.75 / 0.62 / 0.58 / 0.59 / 0.60 |
| emotion kappa | 0.43 | 0.51 |
| expected_move weighted kappa | 0.04 | 0.42 |

The psychology student saw only 2,500 teacher rows (a fifth of the examples) and one third of its
replies failed the strict parser; it is not ready. The typed-event student is.

## 4. Do the extracted numbers predict size beyond the prior?

- **DeepSeek's typed fields** (event, magnitude, confidence, |direction|; 16,538 train cells ->
  5,958 test cells): increment over B2 **+0.0007, t 0.21, MDE 0.0091**. DeepSeek's magnitude bucket
  alone: IC 0.055; exact bucket 22.7% vs 38.6% majority.
- **DeepSeek's psychology fields** (fit 2,500 train cells, grade 1,006 test cells): increment
  **-0.0106, t -1.07, MDE 0.028**. Single fields against move/vol: attention +0.069 (t 2.24, MDE
  0.087), the only |t| > 2 of six, not corrected for the six looks.
- Consistent with the E1 event head (+0.0037, t 0.81) and the 09-26 finding that the vol prior
  beats the investigator on magnitude. The words carry a little size information (TF-IDF +0.007);
  the LLM's summary of the words, as typed fields, carries none that we can detect.

## 5. Speed and cost

| reader | pages/min | $ per 1,000 pages |
|---|---|---|
| student Qwen-1.5B + LoRA, local GPU, batch 16, typed events | **586** | 0 (electricity) |
| base Qwen-1.5B zero-shot, long schema prompt | 344 | 0 |
| student, psychology (longer answer) | 232 | 0 |
| DeepSeek, short psychology prompt (~208 tokens in), 6 threads | ~460 | 0.077 ledger / 0.145 peak list |
| DeepSeek, typed-event prompt (1,483 tokens in; measured 09-13) | 57 serial | 0.315 |
| local Qwen-7B via llama-server, typed events (earlier supervised figure) | 20 per worker | 0 |

The student is ~29x the per-worker rate of the 7B currently used for local typing, because the
schema lives in the weights rather than in a 1,500-token prompt.

## 6. Verdicts

- **Size, fine-tuned LLM head: FAILED_VARIANT.** It adds +0.0024 over the prior but loses to a
  TF-IDF ridge by 0.0045 (t -2.78, every month). One configuration, one epoch; closes this
  implementation, not text-for-size.
- **Size, text over the prior (TF-IDF): a small conditional positive**, +0.0069 IC (t 3.44 vs MDE
  0.0056), 5/5 months, replicated on the 2025 fold. Not ALPHA_DETECTED: it is a size (risk) feature,
  not a return, and nobody has shown it changes a portfolio outcome.
- **Extracted fields -> size: CANNOT_DISTINGUISH** (DeepSeek typed +0.0007, MDE 0.0091; psychology
  -0.0106, MDE 0.028). The psychology test is underpowered; the typed-field test is not.
- **Extraction capability: the student works** (kappa 0.78 against its teacher, 586 pages/min, $0).
  Agreement measures mimicry, not truth.

Adapter: `ft_lab/models/extract_qwen15_lora/last` (gitignored; 94% of one epoch, stopped by the
STOP file at the deadline). Loader: `ft_lab.loader.load_extractor()`. Not wired into anything live.

## Machine notes (what happened, no hardware detail)

Both training stages completed or stopped cleanly, with checkpoints; nothing is left running on
the GPU. The free-RAM rule is enforced at START and the job PAUSES mid-run under a lower floor
(a stated deviation, `config.RUN_FLOOR_RAM_GB`; figures in the local_pc note). Everything launched through `Start-Process` with logs and recorded PIDs; the one
intentional stop used the recorded PIDs.

## CONTINUE FROM HERE

```powershell
# from the repo root ; everything below reuses the saved data and adapters
# 1. the full-size agreement numbers (the 400-row reads above were cut by the deadline)
ft_lab\.venv\Scripts\python.exe -m ft_lab.run_first base_events student_events base_psych student_psych
# 2. student psychology -> size at scale (fit on val, grade on test)
ft_lab\.venv\Scripts\python.exe -m ft_lab.run_first student_psych_val student_psych_testall
# 3. re-grade everything into receipts/first_run.json
ft_lab\.venv\Scripts\python.exe -m ft_lab.analyze
# tests (offline)
ft_lab\.venv\Scripts\python.exe -m pytest ft_lab/tests -q -p no:cacheprovider
```

Launch 1-2 with `Start-Process ... -RedirectStandardOutput ft_lab\runs\run_first.log` and record the PID;
stop with `ft_lab\runs\STOP`. Before the psychology student is used anywhere, retrain it with more
teacher rows (step below) and fix its 33% off-schema rate.

## WHAT WORKS

- A 1.5B student distilled from ~9.6k DeepSeek typed-event rows reproduces the teacher at kappa 0.78
  (base 0.20), always emits valid JSON, and reads 586 pages/min locally for $0. It can convert the
  reader's backlog without an API bill.
- A bag-of-words ridge on the news text adds a small, stable +0.007 to the size-of-move rank IC over
  trailing volatility, in both 2025 and 2026.
- The environment: CUDA torch + bf16 LoRA, no bitsandbytes needed at 0.5-1.5B.

## WHAT DOES NOT

- Fine-tuning a small LLM to predict size: beaten by TF-IDF.
- LLM-extracted fields (typed events, psychology) as size predictors: no detectable increment over
  the numeric prior, with DeepSeek's own labels.
- Zero-shot size buckets from any LLM: far below the free vol prior (DeepSeek IC 0.17 vs 0.40).
- The psychology student as trained (67% valid).

## HIGHEST-EV EXPERIMENT

Stop asking the LLM to predict and use it only as a cheap, fast converter: run the typed-event
student over the full reader corpus and the 348k-row panel (~10 hours of local GPU at 586
pages/min, $0) and grade the ONE question the fields have not yet been asked at scale -- whether
event TYPES condition the size prior (e.g. earnings vs no_event cells get different vol
multipliers, a scope-aware test), against TF-IDF as the bar to beat. Information per dollar is
high because the conversion is free and the negative (fields add nothing) is already cheap to
confirm or overturn with 100x more rows than today's 5,958 test cells.

---

# 2026-09-29 afternoon: the student at scale, against truth, and wired OFF

Licence `PRODUCT_EXPERIMENT`. Receipts (all under `backend/data/optimus/ft_lab/receipts/`):
`bulk_events_progress.json`, `bulk_analysis.json`, `truth_eval.json`, `infer_runs.jsonl`,
`deepseek_arm_runs.jsonl`. Code: `ft_lab/bulk_events.py`, `analyze_bulk.py`, `truth_eval.py`,
`local_extract.py`. Machine detail: `backend/data/optimus/local_pc/ft_lab_machine_notes_2026-09-29.md`.

## RESULTS SCOREBOARD

**RESULT IMPROVEMENT: NONE for returns or size. The student is now a cheap, ~91%-right event
typer, and the psychology student's invalid replies were a token budget, not a schema problem.**

| item | result |
|---|---|
| Rows converted by the student, $0 | **67,584** (every test and val cell's first document, all 2,056 reader pages, 13,608 of 79,435 train cells); 99.95% valid JSON; ~800-900 pages/min |
| Student fields -> size, over T2 (priors + TF-IDF) | **-0.0012 IC (t -1.94, MDE 0.0017)**, 1 of 5 months positive: **FAILED_VARIANT** |
| Student fields -> size, over B2 (priors only) | +0.0003 (t 0.19, MDE 0.0038): **CANNOT_DISTINGUISH**; TF-IDF on the same cells +0.0069 (t 3.46) |
| Largest relative moves by type (test, log move/trailing vol vs no_event) | **earnings_report +0.24 (t 3.74, MDE 0.18, 5/5 months)**; nothing else clears its MDE |
| Post-event drift after 20 bps, selected on val, graded on test | no type CONDITIONAL_POSITIVE at 1 or 5 sessions; pooled selected: 1d -0.05% (t -0.33, MDE 0.43%), 5d -0.33% (t -0.76, MDE 1.2%) |
| Student vs truth (150 held-out docs, blind DeepSeek judge) | event type right **90.7%** vs fresh DeepSeek **94.0%**; material errors **17 vs 9**; on real-event documents 86.7% vs 93.3% |
| Psychology student validity | **67% -> 99.75%** by raising the token budget 110 -> 200 (no retrain); agreement unchanged (tone rho 0.75, emotion kappa 0.51) |
| LLM spend this afternoon | **$0.029** ledger ($0.057 at peak list), 300 DeepSeek calls, cap $0.60 |
| Wired | world digest optional local first stage, `WORLD_DIGEST_LOCAL_EXTRACT = False`; annotates only; ledger rows unchanged |

## 1. Bulk conversion

Queue (`ft_lab/data/bulk_queue.parquet`, 343,126 rows after dropping `archive` rows): test
cells (first document per (symbol, entry_date)), val cells, reader pages (1,742 stored pages +
314 social rows), train cells, then the other 209,715 panel documents newest-first. Done:
test 25,365/25,365, val 26,555/26,555, reader 2,056/2,056, train 13,608/79,435, rest 0.
Every row carries `model = qwen2.5-1.5b-instruct+ft_lab/extract_qwen15_lora/last`. Length-sorted
batches of 32 lifted throughput from 586 to ~800-900 pages/min; the remaining 275,542 rows are
~5.5 hours of GPU at $0. On the reader's pages the student says `no_event` for 83%.

A defect caught in the first minutes: the awake clock ticked once per 2,048-row chunk (~2.7
min), and the sleep-gap rule counts any gap > 60 s as sleep, so the 80-minute box would never
have fired. Stopped with the STOP file, fixed (tick per batch), resumed with no lost rows.

## 2. Size: do the student's fields add anything? (fit val 2026-01-16..04-30, grade test 2026-05-15..09-28, 10-session embargo; 21 weekly blocks)

Features: event-type dummies (20 types with >= 30 val cells), magnitude ordinal, |direction|,
confidence, event flag, magnitude x event. Ridge on the residual of the base, alpha chosen on a
time split inside val.

| model (test, 25,353 cells) | IC | increment | t | MDE | months + |
|---|---|---|---|---|---|
| T2 priors + TF-IDF (base) | 0.4188 | | | | |
| T2 + student fields | 0.4176 | **-0.0012** | -1.94 | 0.0017 | 1 / 5 |
| B2 priors (base) | 0.4119 | | | | |
| B2 + student fields | 0.4121 | +0.0003 | 0.19 | 0.0038 | 2 / 5 |
| B2 + TF-IDF, same cells | | +0.0069 | 3.46 | 0.0056 | 5 / 5 |
| B2 + student minus B2 + TF-IDF | | -0.0067 | -3.73 | 0.0050 | 1 / 5 |

With 25,000 test cells (4x the morning's DeepSeek-field test) the MDE is 0.0017-0.0038, and the
fields still add nothing: the typed fields are a coarser reading of what the bag of words already
carries. **FAILED_VARIANT** for "event types as size features"; it does not close text-for-size
(TF-IDF still +0.007).

## 3. Conditional questions (test block; 5-session = entry open to 5th close, minus SPY)

Move size by event type (types with >= 30 test cells), sorted by median |1-session move|. "rel"
is log(|move| / trailing typical move) minus the no_event cells' mean; SE over weekly blocks.

| event type | n | median 1d | median 5d | rel vs no_event | t | MDE | months + |
|---|---|---|---|---|---|---|---|
| equity_issuance_dilution | 71 | 2.76% | 7.17% | -0.01 | -0.08 | 0.44 | 3/5 |
| litigation_filed | 64 | 1.96% | 3.84% | +0.01 | 0.06 | 0.70 | 3/5 |
| **earnings_report** | 1,511 | 1.95% | 4.52% | **+0.24** | **3.74** | 0.18 | **5/5** |
| guidance_change | 157 | 1.94% | 3.94% | +0.16 | 1.38 | 0.32 | 5/5 |
| new_contract_or_partnership | 615 | 1.94% | 4.99% | +0.01 | 0.06 | 0.21 | 3/5 |
| regulatory_approval | 142 | 1.84% | 4.04% | +0.13 | 0.97 | 0.39 | 5/5 |
| clinical_trial_result | 149 | 1.64% | 4.88% | +0.14 | 1.38 | 0.28 | 4/5 |
| no_event | 19,943 | 1.59% | 4.23% | (ref) | | | |
| insider_or_institutional_ownership_change | 320 | 1.42% | 3.89% | -0.20 | -1.49 | 0.37 | 1/5 |
| management_change_departure | 60 | 1.09% | 4.58% | -0.31 | -1.64 | 0.52 | 2/5 |

(full table, 19 types, in `bulk_analysis.json`). Dilution names move most in raw terms but not
relative to their own (already high) volatility; **earnings is the one type whose move is larger
than its own trailing volatility predicts** (about +27% in ratio terms), in every month. That is
already in T2 through the words, which is why the fields add nothing.

**Post-event drift** (signed return in the student's direction, directional rows only, minus 20
bps round trip; a type is SELECTED if its val mean is > 0, then graded once on test):

| horizon | selected on val | test result | verdict |
|---|---|---|---|
| 1 session | 8 types (earnings, guidance, initiations, dilution, divestiture, litigation, departures, tariffs) | best: analyst_initiation +0.94% (t 1.41, MDE 1.88%, 2/5 months), litigation_filed +0.51% (t 0.80, 4/5 months); earnings -0.16%, guidance -0.46%; pooled -0.05% (t -0.33, MDE 0.43%), 2/5 months | no type is positive, significant AND positive in most months: CANNOT_DISTINGUISH (4 types) / FAILED_VARIANT (4 types) |
| 5 sessions | 9 types | pooled -0.33% (t -0.76, MDE 1.2%), 1/5 months; best equity_issuance +0.46% (t 0.32) | **FAILED_VARIANT** (pooled); no type passes |

Not selected, but worth a registered look: `analyst_target_change` at 1 session is **-0.54% net
(t -2.74, MDE 0.55%, 0 of 5 months positive; gross -0.34%)**: the student's direction on
price-target changes is followed by a move the OTHER way the next session. Seen after looking at
19 types x 2 horizons, so it is a hypothesis, not a finding.

## 4. The student against truth, not its teacher

150 held-out test documents (75 where the 09-13 teacher saw an event, 75 no_event). Each got the
student's label, a FRESH DeepSeek label with the production L2 prompt (`event_extraction`,
variant A; 0 refusals; agrees with the 09-13 teacher on 96%), and a blind DeepSeek JUDGE that saw
the text, an explicit rubric and the two labels as A/B in random order. $0.029 (ledger).

| | student | DeepSeek |
|---|---|---|
| event type right (all 150) | 90.7% | 94.0% |
| direction right | 90.7% | 93.3% |
| magnitude right | 87.3% | 90.7% |
| event type right, teacher-event docs (75) | 86.7% | 93.3% |
| event type right, teacher-no_event docs (75) | 94.7% | 94.7% |
| judged MATERIAL errors | **17** | 9 |
| event-type disagreements (21): judge sided with | student 6 | DeepSeek 11 (neither 3, both 1) |

Where the student is wrong in a way that matters (17): **7 real events read as no_event** (a
$28.6B buyback, earnings beats behind +22-67% moves, a special dividend, a strategic review),
**5 wrong signs** (tariffs that help a domestic producer read as bad, a settlement read as bad),
**3 events about the wrong entity** (a rival's trial or earnings attached to the named ticker),
2 wrong types. Its failure is omission and entity confusion, not broken schema. Caveats: the
judge is DeepSeek, so it leans to DeepSeek's reading; when the two agree it almost never says
"neither", so both accuracies are upper bounds and only the disagreements are informative.

**Verdict: holds up as a free first pass** (about 1 material error in 9 documents vs 1 in 17),
**not as a replacement** where a missed earnings beat matters.

## 5. Wired, default OFF

`backend/services/world_digest.py`: `local_event_stage()` + `_local_student_runner()` and an
optional `local_runner` argument on `extract_items`. `backend/config.py`:
`WORLD_DIGEST_LOCAL_EXTRACT = False`, `WORLD_DIGEST_LOCAL_MIN_FREE_RAM_GB` (a memory floor; value in the local_pc record),
`WORLD_DIGEST_LOCAL_TIMEOUT_S = 900`.

- ON: new single items (never headline batches) go to `ft_lab.local_extract` as a SUBPROCESS
  with the ft_lab interpreter (the backend never imports torch). The reading rides on the row as
  `local_event` {event_type, direction, magnitude, confidence, model}.
- It ANNOTATES. DeepSeek still types every row (the student knows 4 of the digest's ~14 fields),
  so themes, implications and the forecast-ledger rows are unchanged.
- Fallback to DeepSeek alone, with the reason in `extract_items(...)["local_stage"]`, when the
  flag is off, the interpreter or adapter is missing, free RAM is under the floor, the GPU is
  held by another process, or the child crashes or times out.
- Every new row now records `extract_model` (`deepseek:<served model>`).
- Tests: `backend/tests/test_world_digest_local_stage.py` (6) + `test_world_digest.py` (18) pass;
  guard / reachability / provider / network tests pass (158). `ft_lab/tests` 18 pass. Full suite
  NOT run (per instruction).

## 6. Psychology extractor: the 33% invalid was a token budget

All 131 invalid replies of the first run were TRUNCATED, not off-schema: the student had been
trained on targets like `0.7000000000000001` and `NaN` (float noise in `psych_target`), learned to
emit them, and ran out of its 110-token budget mid-object. Fixes: `prompts.psych_target` rounds to
2 dp and writes NaN as null (for the next retrain); `valid_psych` maps NaN to null;
`PSYCH_MAX_NEW_TOKENS = 200` in `infer.py` and `loader.py`. Re-run on the same 400 test cells:
**399/400 valid (99.75%)**, agreement with DeepSeek unchanged (tone rho 0.753, uncertainty 0.58,
surprise 0.54, novelty 0.58, attention 0.56, emotion kappa 0.51), 125 pages/min (longer replies).
The first run's file is kept as `ft_lab/data/gen_student_psych_psych_test_run1_110tok.jsonl`.
A retrain on the cleaned targets would shorten replies and roughly double that speed.

## Verdicts (afternoon)

- **Student event fields -> size: FAILED_VARIANT** (-0.0012 over T2, MDE 0.0017, 25k test cells).
- **Event type conditions size: CONDITIONAL_POSITIVE for earnings only** (+0.24 log ratio, t 3.74,
  5/5 months), already captured by TF-IDF; a size (risk) fact, not alpha.
- **Post-event drift by event type: no type survives** val selection -> test after 20 bps
  (CANNOT_DISTINGUISH at best; pooled FAILED_VARIANT at 5 sessions). One unselected sign flip
  (price-target changes, t -2.74) to pre-register before anyone trades it.
- **Student vs truth: usable first pass, ~3 points below DeepSeek, 2x the material errors.**

## CONTINUE FROM HERE (afternoon)

```powershell
# from the repo root
# 1. finish the conversion (275,542 rows left, ~5.5 GPU hours, $0; resumable, checkpoints every 2,048 rows)
Start-Process ft_lab\.venv\Scripts\python.exe -ArgumentList "-m","ft_lab.bulk_events","--minutes","80" -RedirectStandardOutput ft_lab\runs\bulk_events.log -RedirectStandardError ft_lab\runs\bulk_events.log.err -WindowStyle Hidden -PassThru
#    record the CHILD python PID (the venv exe is a launcher); stop with New-Item ft_lab\runs\STOP
#    progress: backend\data\optimus\ft_lab\receipts\bulk_events_progress.json
# 2. re-grade (fit val, grade test) -> receipts\bulk_analysis.json
ft_lab\.venv\Scripts\python.exe -m ft_lab.analyze_bulk
# 3. truth summary -> receipts\truth_eval.json (the paid part is done)
ft_lab\.venv\Scripts\python.exe -c "from ft_lab.truth_eval import summarize; summarize()"
# tests
ft_lab\.venv\Scripts\python.exe -m pytest ft_lab/tests -q -p no:cacheprovider
$env:AEGIS_IGNORE_DOTENV="1"; $env:AEGIS_PERSONAL_MODE="0"; .venv\Scripts\python.exe -m pytest backend/tests/test_world_digest_local_stage.py backend/tests/test_world_digest.py -q
```

Next, by information per dollar: (a) pre-register the analyst_target_change reversal and test it
on the 2025 train cells once converted (they are outside this look); (b) retrain the psychology
student on the cleaned targets with more teacher rows; (c) turn `WORLD_DIGEST_LOCAL_EXTRACT` on for
a week only if someone will grade `local_event` against the digest's DeepSeek rows. Uncommitted.

---

# 2026-09-29 evening: the price-target reversal, registered and read once on 2025

Licence `PRODUCT_EXPERIMENT`. Trial: `docs/TRIALS/TRIAL-PT-REVERSAL-1-price-target-next-session-fade.md`
(left byte-identical after the read; the result lives in the receipt and here). Receipts under
`backend/data/optimus/ft_lab/receipts/`: `pt_reversal_registration.json`, `pt_reversal_read.json`,
`bulk_events_pt2025_progress.json`, `psych_v2_agreement.json`, `infer_runs.jsonl`. Code (new
files only): `ft_lab/bulk_pt_priority.py`, `ft_lab/pt_reversal_read.py`, `ft_lab/retrain_v2.py`,
`ft_lab/tests/test_bulk_pt_priority.py`.

## RESULTS SCOREBOARD

**RESULT IMPROVEMENT: NONE. The afternoon's one lead failed its registered read.**

| item | result |
|---|---|
| Registration | sha256 `7a292db967543fef9db1923721f5b32653190cf8f9f4c93e8984a241c0b1b246`, 2026-09-29T10:39:19Z (18:39 local), before any further 2025 conversion |
| Rows converted by the student this evening, $0 | **65,827** (every remaining 2025 cell; the train block is now 79,435 of 79,435 converted, 79,412 valid), ~1,190 pages/min, 55 awake minutes |
| **TRIAL-PT-REVERSAL-1, 2025 read (723 cells, 206 dates, 52 weekly blocks)** | gross fade **-0.14% (t -0.91, MDE 0.44%)**, 6 of 12 months positive, leave-one-month-out worst -0.21%; net of 20 bps -0.34% (t -2.18) |
| Verdict | **FAILED_VARIANT** (registered rule: gross mean <= 0); lead `RETIRED_FROM_CURRENT_SEARCH`; no forward log |
| Psychology student retrained on cleaned targets (new adapter; the old one is untouched) | 99.8% valid, **410 pages/min (vs 125)**; agreement with DeepSeek the same or slightly better (same 400 cells: tone rho 0.76 vs 0.75, emotion kappa 0.55 vs 0.51) |
| LLM spend | $0.00 |

## 1. Registration (before anything was converted or read)

- Hypothesis: after the student reads an analyst price-target change with a direction, the next
  session (entry open to close, minus SPY) moves against it. Traded as a FADE,
  `R = -direction * x_oc`, 20 bps round trip, with 40 and 60 bps sensitivity lines.
- What the afternoon's number actually was: the "follow" trade lost -0.54% net. The FADE was
  **+0.34% gross, +0.14% net** on the test block. September 2026 carried much of it, and the
  validation block showed about zero. It was found after **38 looks**, and the test block was
  declared spent.
- Untouched sample: the 2025 block (79,435 cells, of which 13,608 were converted at
  registration). I confirmed it was unused for this question: 2025 had fed only SIZE (|move|)
  models and type shares, and no signed return had been joined to a direction label there.
- Primary: the mean over dates of the per-date mean gross fade, SE on weekly blocks,
  MDE = 2.8 x SE. The rules:
  - `CONDITIONAL_POSITIVE` needs m > 0, t >= 2, positive in at least 7 of 12 months, and a
    leave-one-month-out worst above 0.
  - A forward paper log also needs net20 >= +0.10% with t >= 2, and net40 > 0.
  - `FAILED_VARIANT` if m <= 0, or if t < 2 and MDE <= 0.34%.
  - Otherwise `CANNOT_DISTINGUISH`.
- The corpse-check linter returned **`UNPOWERED_AT_REGISTRATION`**. It says the smallest effect
  it can resolve is 0.58pp, assuming 252 independent days a year, against the declared 0.34pp.
  Going ahead anyway was a stated deviation, recorded in the trial and the receipt. It was
  allowed only because the read cost $0 and an underpowered positive could not advance.
- The registration also got the sample size wrong, which only the label count (no outcomes)
  showed. It expected about 1,700 directional PT cells, from the test-block share (2.1%); 2025
  has **723 (0.91%)**. The student finds fewer price-target stories in 2025 than in 2026 because
  the wire mix differs. The realised MDE was therefore 0.44%, not 0.35-0.40%.

## 2. Conversion (text-only prioritisation)

`ft_lab/bulk_pt_priority.py` reordered the remaining 2025 cells:
- first the 1,061 cells whose first document matches a price-target regex, then the rest;
- output was appended to the same `bulk_events.jsonl`, with the same keys and the same frozen
  adapter tag;
- the regex only ordered the queue, and the event is the student's label.

The run converted the whole block and stopped at the end of the queue at 19:37 local, so the
prioritisation made no difference in the end. Free memory fell below the measured memory floor for about a minute, while
the model loaded next to my label count and the test suite. The job paused itself
(`safety.wait_for_ram`) and resumed, and no stop was needed.

## 3. The single read (2025, `pt_reversal_read.json`)

| line | mean | t | MDE | months + |
|---|---|---|---|---|
| **gross fade (primary)** | **-0.14%** | **-0.91** | **0.44%** | 6 / 12 |
| net of 20 bps | -0.34% | -2.18 | 0.44% | 5 / 12 |
| net of 40 bps | -0.54% | -3.45 | 0.44% | 2 / 12 |
| net of 60 bps | -0.74% | -4.71 | 0.44% | 1 / 12 |
| raises only, gross (reported) | -0.23% | -1.18 | 0.56% | 5 / 12 |
| cuts only, gross (reported) | -0.13% | -0.57 | 0.62% | 5 / 12 |
| 5-session fade, gross (reported) | -0.08% | -0.29 | 0.80% | 6 / 12 |

By month (gross fade): Jan -0.94%, Feb +0.05%, Mar +0.66%, Apr +0.23%, May -0.43%, Jun +0.36%,
Jul +0.60%, Aug -0.69%, Sep -0.47%, Oct -0.55%, Nov -0.55%, Dec +0.22%.
(`top5_dates_share_of_total` in the receipt is negative because the total is negative; it is
not meaningful here.)

**Verdict: FAILED_VARIANT.**
- In 2025 the sign is the opposite of the fade: if anything a slight continuation (t 0.91,
  cannot be told from zero), for both raises and cuts.
- The test-block result is what 38 looks produce: one tail.
- This closes the student's price-target reading on the first document at the next session. It
  does not close price-target information in general.
- The MDE (0.44%) is above the 0.34% the lead was found at, so a small true reversal is not
  excluded; there is no evidence for one either.
- No forward log.

## 4. Psychology student, retrained on cleaned targets

The setup:
- the same data (9,641 event and 2,500 psychology teacher rows), hyper-parameters and seed;
- targets rounded to 2 dp, with NaN written as null;
- written to `ft_lab/models/extract_qwen15_lora_v2/last`. The frozen `extract_qwen15_lora/last`,
  which every bulk row and the trial refer to, is untouched;
- one epoch, 22 awake minutes.

Graded on the DeepSeek psychology test cells:

| | v1 (200-token budget) | v2 same 400 cells | v2 all 1,006 cells |
|---|---|---|---|
| valid JSON | 99.75% | 100% | 99.8% |
| pages/min | 125 | 410 (1,006-cell run) | 410 |
| Spearman tone / uncertainty / surprise / novelty / attention | 0.75 / 0.58 / 0.54 / 0.58 / 0.56 | 0.76 / 0.54 / 0.57 / 0.58 / 0.61 | 0.78 / 0.60 / 0.56 / 0.60 / 0.64 |
| emotion kappa / expected_move weighted kappa | 0.51 / 0.39 | 0.55 / 0.39 | 0.57 / 0.41 |

- Shorter answers made it 3.3x faster at the same agreement.
- The v2 adapter's EVENT half has not been re-graded and is not used anywhere; the typed-event
  student is still v1.
- The first eval attempt was refused because the training process still held its own graphics memory when
  it called `infer.preflight`. The eval was rerun in a fresh process.

## Verdicts (evening)

- **TRIAL-PT-REVERSAL-1: FAILED_VARIANT** (gross -0.14%, t -0.91, MDE 0.44%, 723 cells, 52 blocks).
  The lead is retired from the current search.
- **Psychology student v2: fixed** for speed and validity; agreement unchanged. Not wired.

## CONTINUE FROM HERE (evening)

```powershell
# from the repo root
# 1. the remaining panel documents (panel_other_doc: 209,715 rows, ~3 GPU hours at ~1,190/min, $0; resumable)
Start-Process ft_lab\.venv\Scripts\python.exe -ArgumentList "-m","ft_lab.bulk_events","--minutes","80" -RedirectStandardOutput ft_lab\runs\bulk_events.log -RedirectStandardError ft_lab\runs\bulk_events.log.err -WindowStyle Hidden -PassThru
#    record the CHILD python PID; stop with New-Item ft_lab\runs\STOP
# 2. the PT trial is spent: `-m ft_lab.pt_reversal_read --read` now refuses (receipt exists); --count still works
# 3. psychology v2 eval only (adapter already trained):
ft_lab\.venv\Scripts\python.exe -m ft_lab.retrain_v2 --skip-train --until 23:59
# tests
ft_lab\.venv\Scripts\python.exe -m pytest ft_lab/tests -q -p no:cacheprovider   # 20 pass
```

Still owed:
- Commit the trial file together with this note. Until then, the hash in
  `pt_reversal_registration.json` is the tamper evidence.
- Register the row in `rule_experiments` as FAILED_VARIANT so the cumulative trial count
  includes it.

With the 2025 block fully typed, the highest-EV next step is the afternoon's item (a): the
event-type-conditioned size prior on 2025 as a second fold, against TF-IDF. Uncommitted.
