# LLM theories, measured fairly: size and conditional questions, blinded, post-cutoff (night of 2026-09-29)

Licence `PRODUCT_EXPERIMENT` (no claim). Code: `scripts/hyp_llm_theories.py`, tests
`backend/tests/test_hyp_llm_theories.py` (10 pass, offline). Receipts under
`backend/data/optimus/hyp_lab/`: declarations `job3_declaration_r1.json`, `job3_declaration_r3.json`,
`job3_declaration_q3_{r1,r2,r4,r5}.json` (each written before its calls, with a sha256); analyses
`job3_analysis_*.json`; the verdict table `job3_verdicts_r1-r5.json`; rows in `job3_r*/rows_*.jsonl`.
Every DeepSeek call went through `backend/services/hyp_llm.py` (central `call_named`, telemetry, a
per-night cap read from `hyp_lab/spend.jsonl` at peak list price). Paused early on the owner's order
(about 22:52 local); the unfinished parts are listed at the end.

## RESULTS SCOREBOARD

**RESULT IMPROVEMENT: NONE.** No LLM arm adds skill to the numbers it could be given for free.

| item | result |
|---|---|
| Does an LLM reading blinded post-cutoff news beat the numbers on SIZE? | **No.** Every arm that was also given the numbers, or was compared with them, lands at or below the numbers-only model (tables below). |
| Best LLM reading on its own | Q3 within-date ranking of *relative* surprise, DeepSeek text: rank IC **+0.042 (t 2.09, MDE 0.056)**, 600 groups, 21 weekly blocks. The numbers + TF-IDF model on the same groups: **+0.133**. The LLM's IC against the residual of that model: **+0.004 (t 0.22, MDE 0.049)**. |
| Forced single probability (Q1) | **Abstention**, both models: DeepSeek sd_p 0.0056 around the stated base rate, local 7B 237 of 240 answers exactly 0.45. |
| LLM given the numbers (b) | Q1: -0.0016 Brier vs numbers alone (t -1.36, MDE 0.0033). Stacked on the numbers (Platt fit on the val block): text -0.0005 (MDE 0.0011), numbers-prompt +0.0001 (MDE 0.0009). |
| Self-consistency (c) | Mean of 5 samples vs one: -0.0002 Brier (MDE 0.0028); within-item sd 0.004, so there was nothing to average. Q3 mean of 3: IC 0.010 vs 0.025 single. |
| Earnings, the one event type that moves more than vol predicts | Two folds disagree: test +0.035 (t 0.73), val **-0.068 (t -2.41)**. FAILED_VARIANT. |
| Leak (identified the blinded company) | DeepSeek 6.3% (Q1 items), 6.9% (Q3 items), 9.9% (earnings items); local 7B 1.7%. Dropping identified items changes no reading's sign. |
| Spend | DeepSeek **12,688 calls, $0.607 ledger / $1.503 at peak list price** (cap $2.40 of the night's $3.00). Local 7B: 620 calls, $0. |
| Selectors / books / forward paper | unchanged; nothing here trades. |

## 1. Design (why this is a fair test and not a repeat)

Closed rows NOT repeated (`docs/WHAT_WE_ALREADY_KNOW_LLM.md`): bare direction (AMNESIA-2, X2 blind),
headline size buckets (world digest 2026-09-29), zero-shot size buckets vs the vol prior (ft_lab
2026-09-29, where DeepSeek expected_move IC was 0.17 vs 0.40 and base Qwen-1.5B 0.064; the 1.5B was
therefore not re-run tonight).

- **Cells**: ft_lab's news cells, test block 2026-05-15..09-28 (after DeepSeek's measured 2025-12
  cutoff); the val block 2026-01-16..04-30 (also post-cutoff) only to fit stacking maps (Q1) or as a
  second fold (Q3 earnings). Tickers of 3+ letters with an SEC title; ticker and name aliases replaced
  by a code (`exp_llm_blind_gap_2026_09_28.name_aliases/blind_text`), and a cell whose blinded text
  still carries an alias is DROPPED, never repaired. Stratified by week. No tools, no dates in the prompt.
- **Target**: the next session's |open-to-close minus SPY| (ft_lab's `y`). Q1's event is
  y > the name's trailing 21-session mean |abnormal move| (train base rate 44.6%).
- **Baselines, fitted on the 2025 train block, never on the LLM sample**: base rate; `L_B1` logistic
  on trailing priors (the vol prior); `L_T2` logistic on trailing priors + news counts + the T2 TF-IDF
  forecast ("the numbers"); for pairs, a logistic on the T2 difference fitted on train-block pairs and
  the higher-trailing-vol heuristic.
- **Scoring**: Brier, BSS, AUC, ECE; paired per-row Brier difference with the SE over weekly blocks of
  entry dates; MDE = 2.8 SE; by month. Q3: within-group Spearman, same blocking.
- **Q3 was added after the first reads** (Q1 answers hugged the stated base rate). It was declared in
  its own receipt before any Q3 call: eight blinded items from the SAME entry date in one prompt, each
  scored 0-100 for being unusually large *relative to its own normal move*; no anchor, so the model
  must discriminate. The residual metric (IC against log|move| minus the T2 forecast) was declared with
  the 600-group scale-up (r2) before its calls.

## 2. Skill table

Q1: P(move > own typical move). BSS = 1 - Brier/Brier_ref. Differences are ref minus arm (positive = arm better).

| arm | n | Brier | BSS vs base | BSS vs vol prior L_B1 | BSS vs numbers L_T2 | diff vs L_T2 (t, MDE) | AUC | identified |
|---|---|---|---|---|---|---|---|---|
| DeepSeek text (r3) | 960 | 0.2442 | +0.0002 | -0.0031 | -0.0005 | -0.0001 (-0.03, 0.010) | 0.504 | 6.3% |
| DeepSeek numbers+text (r3) | 960 | 0.2457 | -0.0058 | -0.0092 | -0.0066 | -0.0016 (-1.36, 0.0033) | 0.552 | 6.3% |
| local 7B text (r1) | 240 | 0.2473 | -0.0046 | +0.0016 | +0.0142 | +0.0036 (0.48, 0.021) | 0.489 | 1.7% |
| numbers alone L_T2 (r1 sample) | 240 | 0.2508 | -0.019 | -0.013 | - | - | 0.519 | - |

The relative-size event is hard for everything: the numbers model's AUC on these samples is ~0.52-0.55.
The two text arms are constant forecasts (sd_p 0.006-0.010), which is why their Brier sits at the base
rate: they abstained.

(b) Does the LLM add to the numbers? Platt/stack maps fitted on 960 val cells, graded on 960 test cells:

| stack | diff vs L_T2 recalibrated (t, MDE) | verdict |
|---|---|---|
| L_T2 + DeepSeek(text) | -0.0005 (-1.28, 0.0011) | FAILED_VARIANT |
| L_T2 + DeepSeek(numbers prompt) | +0.0001 (0.42, 0.0009) | CANNOT_DISTINGUISH; bounded under ~0.001 Brier |

Q2: which of two blinded companies (same entry date) moves more in absolute terms.

| arm | pairs | accuracy (t vs 0.5) | vol heuristic | pair-numbers model | Brier diff vs pair-numbers (t, MDE) | AUC |
|---|---|---|---|---|---|---|
| DeepSeek text (r3) | 400 | 55.9% (2.67) | 62.3% | 61.5% | -0.041 (-2.64, 0.043) | 0.582 |
| DeepSeek numbers+text (r3) | 400 | 64.6% (5.49) | 62.3% | 61.5% | -0.004 (-0.76, 0.016) | 0.692 |
| local 7B text (r1) | 200 | 52.0% (0.53) | 68.0% | 67.5% | -0.069 (-3.46, 0.056) | 0.500 |

DeepSeek's text-only pairwise call beats a coin because the text tells it what kind of company it is
(a small biotech vs a utility), but it is 6.4 pp below just picking the higher-volatility name
(t -2.05). With the numbers it matches them (+2.4 pp, t 1.38, MDE 4.8 pp). The local 7B has a position
bias (mean p(A) 0.68) and no discrimination.

Q3: within-date ranking of relative surprise (IC = within-group Spearman vs log(move / own normal)).

| arm | groups | IC rel (t, MDE) | IC vs \|move\| | numbers L_T2 IC rel | rank-avg minus L_T2 (t) | IC vs T2 residual (t, MDE) |
|---|---|---|---|---|---|---|
| DeepSeek text (r2) | 600 | **+0.042 (2.09, 0.056)** | +0.120 | +0.133 | -0.035 (-2.03) | +0.004 (0.22, 0.049) |
| DeepSeek numbers+text (r2) | 600 | +0.058 (3.76, 0.043) | +0.143 | +0.133 | -0.028 (-1.94) | -0.021 (-1.34, 0.045) |
| local 7B text (r2 subset) | 60 | +0.017 (0.44, 0.11) | +0.020 | +0.152 | -0.040 (-1.76) | -0.010 (-0.21, 0.13) |
| DeepSeek text, earnings only, test (r4) | 129 | +0.035 (0.73, 0.13) | +0.107 | +0.177 | -0.041 (-0.88) | +0.030 (0.58, 0.15) |
| DeepSeek text, earnings only, val fold (r5) | 112 | **-0.068 (-2.41, 0.079)** | +0.040 | +0.163 | -0.088 (-3.49) | -0.038 (-1.39, 0.077) |
| DeepSeek text, k=3 mean (r1) | 150 | +0.010 (0.28, 0.10) | +0.116 | +0.120 | -0.043 (-1.83) | -0.023 (-0.69) |

By month (DeepSeek text r2, IC rel): May -0.038, Jun +0.036, Jul +0.025, Aug +0.104, Sep +0.037.
The model reads "unusually large for this company" mostly as "large", i.e. volatile: its IC against
|move| (+0.12) is three times its IC against the relative move, and both are far below the free T2
forecast (+0.376 against |move| on the same groups).

Leak: 1,600 (r2), 1,032 (r4) and 896 (r5) Q3 items were each shown alone with "name the company or
UNKNOWN": identified 6.9%, 9.9%, 9.8%. Dropping them: r2 text IC rel 0.059 -> 0.056 and residual 0.017 ->
0.009 on the checked groups; r4/r5 unchanged in sign. Nothing is carried by identified rows.

## 3. Verdicts

- **Forced single probability (Q1): FAILED_VARIANT as a design.** Both models return the stated base rate.
  A prompt that states a base rate and asks for one probability measures the prompt, not the model.
- **(b) LLM + numbers: FAILED_VARIANT / bounded.** Given the numbers, DeepSeek is slightly worse than the
  numbers; stacked on them it adds at most ~0.001 Brier (MDE 0.0009-0.0011).
- **(c) Self-consistency: no gain.** With a near-deterministic model there is nothing to average; with
  forced ranking (Q3) the mean of three T=0.7 samples was worse than one T=0 sample.
- **Q2 pairwise: text alone loses to trailing volatility; with numbers CANNOT_DISTINGUISH from them.**
- **Q3 relative-surprise ranking: a weak standalone signal (t 2.09) that is entirely inside the numbers +
  TF-IDF model** (residual IC +0.004, MDE 0.049). Scope: this closes "DeepSeek ranks next-session size
  surprise from one blinded first document"; it does not close multi-document synthesis (the world
  digest's forward rows, first grades 2026-10-09).
- **Earnings-only surprise reading: FAILED_VARIANT** (second fold t -2.41).
- **Local Qwen2.5-7B: no discrimination on any question** (Q1 constant, Q2 AUC 0.50, Q3 IC +0.017).

## Unfinished (paused by the owner's order)

- Local 7B Q1 val and numbers arms, and local Q3 beyond 60 groups: not run (the 7B abstained on Q1 and
  had AUC 0.50 on Q2, so these were low value).
- Qwen2.5-1.5B base: not run; ft_lab already measured it at IC 0.064 on zero-shot size.
- The DeepSeek+local mean for (c): not meaningful (local Q1 is a constant 0.45); reported as such.

Resume commands (from the repo root, project interpreter, `AEGIS_PERSONAL_MODE=0`; delete
`backend/data/optimus/hyp_lab/job3_r1/STOP` first; take the local graphics-card lock file in `hyp_lab/` before any local arm):

```
.venv/Scripts/python.exe -m scripts.hyp_llm_theories run --run r1 --provider local --q q1 --arm text --split val --workers 2
.venv/Scripts/python.exe -m scripts.hyp_llm_theories run --run r1 --provider local --q q1 --arm num --limit 120 --workers 2
.venv/Scripts/python.exe -m scripts.hyp_llm_theories q3 run --run r2 --provider local --workers 2 --limit 200
.venv/Scripts/python.exe -m scripts.hyp_llm_theories analyze --run r1
.venv/Scripts/python.exe -m scripts.hyp_llm_theories q3 analyze --run r2
AEGIS_IGNORE_DOTENV=1 AEGIS_PERSONAL_MODE=0 .venv/Scripts/python.exe -m pytest backend/tests/test_hyp_llm_theories.py -q -p no:cacheprovider
```

Runs are resumable (rows keyed by item and sample). Stop the local model afterwards with
`llama_server.stop(stop_reason="operator")` (by its recorded process id).

## WHAT WORKS

- The fair-test harness: blinded, leak-checked per item, post-cutoff, proper scores against baselines
  fitted on a different year, weekly-block SEs, every design declared before its calls, $0.61 ledger for
  12,688 calls.
- Forcing discrimination inside a same-date group (Q3) gets a real ranking out of DeepSeek where a single
  probability gets an abstention.

## WHAT DOES NOT

- Any LLM arm as an addition to the numbers for next-session size: at best +0.0001 Brier, residual IC
  +0.004.
- Asking for one probability with a stated base rate (both models abstain).
- Self-consistency on this task; the local 7B on any question here; DeepSeek on earnings surprise size.

## HIGHEST-EV EXPERIMENT

Stop spending LLM calls on single-document next-session size. The one untested LLM job left in this area
is synthesis across many documents and names, which is what the world digest's frozen rows do: grade
its 5-session size rows against `vol_prior_p` from 2026-10-09, split by order (1 vs 2) and
mentioned vs not-mentioned. It costs $0 to read and it is the only arm whose information set the
numbers model does not already contain.
