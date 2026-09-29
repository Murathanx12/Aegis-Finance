# Fiction backtest = AMNESIA-2, model-agnostic (2026-09-28)

Licence: `PRODUCT_EXPERIMENT` (no claim). Registration, written and linted (PASS) before the
first call: `docs/TRIALS/TRIAL-AMNESIA-2-event-reaction-model-agnostic.md`
(sha256 `eec1096c…` stamped into the plan). Code: `scripts/fiction_backtest.py`. Receipt:
`backend/data/optimus/fiction_backtest/fb_20260928/receipt_analyze.json`. Frozen rows:
`…/fb_20260928/rows/deepseek.jsonl`, `…/rows/nvidia_meta_llama-3.2-11b-vision-instruct.jsonl`.
Call ledger: `…/fb_20260928/calls.jsonl`.

## RESULTS SCOREBOARD

**RESULT IMPROVEMENT: NONE.** No arm beats a coin, 12-1 momentum or the free volatility
priors on dates after its knowledge cutoff. The fiction layer holds on DeepSeek: A3 identified
0 of 599 cases. The masked level with real headlines does not hold: 4 of 30 famous cases were
identified. Nothing here is actionable. DeepSeek spend was **$0.655** on the run's ledger and
**$0.67** on the provider's balance ($30.49 → $29.82, cent resolution), under the $2.00 cap.
NVIDIA is free. It served `meta/llama-3.2-11b-vision-instruct` and ran too slowly for a full
read tonight: the partial rows are in the receipt, not in the table below.

Clean part: 569 earnings events per level, decision dates 2026-07-01 … 2026-09-02, 10 weekly
blocks, all after DeepSeek's measured 2025-12 cutoff. Model served on every row:
`deepseek-flash`. Parse rate: 1,797 of 1,797 forecasts and 1,797 of 1,797 canaries.

| DeepSeek, CLEAN | hit 5d vs median stock [Wilson 95] | week-block t | 12-1 mom. hit (same rows) | AUC 5d | Brier 5d (base-rate) | 80% range coverage | interval score: model / vol prior / earnings prior | verdict: direction · magnitude |
|---|---|---|---|---|---|---|---|---|
| A0 named | 44.6% [40.6, 48.7] | -0.83 | 46.7% | 0.44 | 0.267 (0.249) | 63% | 48.5 / 48.3 / 49.0 | FAILED_VARIANT · CANNOT_DISTINGUISH |
| A2 masked | 43.1% [39.2, 47.3] | -1.47 | 46.7% | 0.43 | 0.268 (0.249) | 64% | 49.9 / 48.3 / 49.0 | FAILED_VARIANT · CANNOT_DISTINGUISH |
| A3 synthetic (fiction) | 43.9% [39.9, 48.0] | -0.71 | 46.7% | 0.43 | 0.272 (0.249) | 65% | 49.3 / 48.3 / 49.0 | FAILED_VARIANT · CANNOT_DISTINGUISH |

| DeepSeek, FAMOUS (leak test; 30 largest mega-liquid earnings moves 2018-10 … 2025-05) | hit 5d | AUC 5d | canary |
|---|---|---|---|
| A0 named | 58% | 0.61 | recall YES on **8/30**; direction right on 6 of the 8 (AMD, TSLA, UBER, UPST, NVDA, INTC; wrong on GME, MRNA) |
| A2 masked (real headlines, coded name) | 60% | 0.63 | identified **4/30** (SMCI, MRVL, UNH, COIN); year right 6/30 |
| A3 synthetic (fiction) | 62% | 0.58 | identified **0/30**; year 0/30 |

NVIDIA arm (`meta/llama-3.2-11b-vision-instruct`, free, cutoff 2023-12 per its model card),
FAMOUS part, complete: 90 canaries, all parsed; 90 forecasts, **30 refused** by the strict parse
(mostly `SCENARIO_FIELDS`, i.e. a range with low > high). Named recall says YES on **30 of 30**:
it claims to remember everything, which is confabulation, not memory. A2 and A3 identified
**0/30**. Hit 5d: A0 61% (n 23), A2 73% (n 11), A3 48% (n 25). All CANNOT_DISTINGUISH at these
n; its A3 magnitude is FAILED_VARIANT (worse than the vol prior). Not leaking by the declared
rule. Its clean part was still running at the time of writing (see Unfinished).

Leak rule (declared): the fiction leaks if A3 identification > 10% or A3 famous hit ≥ 0.70.
**NOT LEAKING** for DeepSeek: 0% and 0.62. The named-minus-fiction gap on famous moves is
**-3 pp** (58% vs 62%, n = 30). The model remembers some famous outcomes when asked directly,
but that memory does not reach its forecast.

## WHAT ALREADY EXISTED / WHAT I REUSED / WHAT IS NEW

| already existed (not rebuilt) | reused, how | new tonight |
|---|---|---|
| TRIAL-LLM-AMNESIA-1/1B (`Aegis module`, 08-08): named/instructed/masked/synthetic arms, canaries; masking held 0/240; synthetic ≈ masked; the 12-month task was unlearnable; it named AMNESIA-2 as the next step | **vendored** from `aegis_brain/llm/amnesia.py` (sha256 `ce07f685…`): `FAKE_PREFIX/SUFFIX`, the `fake_identity` rule (year +10, so a date one year earlier cannot read as 20xx), the A3 "[SIMULATED SCENARIO]" framing, both canary wordings (horizon 12 m → 5 sessions), and `parse_json` for canaries only. A1 (the "forget" instruction) is **not re-run**: measured at zero | AMNESIA-2 itself: 5-session reaction around 8-K item 2.02 filings, where a baseline has signal (the stock's own past earnings reactions) |
| `leakage_probe.masking_violations` (TRIAL-LEAK-1) | **imported** unchanged as the pre-call scan; a leaking A2/A3 prompt is refused, never repaired. 31 situations (93 cases) were refused and dropped at every level, so the levels stay paired | model-agnostic ARMS behind `answer(system, user, case_id)`: DeepSeek via `call_named` (own cap), NVIDIA NIM (any $0-listed model), local (never starts a server), **FILE arm** |
| `protocol_p16.ece`, `calibration.brier_decomposition` | **imported** for P4 ECE | the scenario answer: 3 scenarios, P(beat median) 5d/21d, central + 80% range, change-mind, 4 text features, strict parse |
| X2 today (`exp_llm_blind_gap_2026_09_28.py`): aliases, blinding, leak check, price summary, Wilson, date blocks, typed-event loader, DeepSeek cutoff 2025-12 | **imported** unchanged | A3 rescales every price by one random factor and every size by another, so ratios and ranks are unchanged, and shifts years by a constant. Split-basis repair: filed share counts are put on today's basis. Target levels are dropped, because bars are split-adjusted and targets are not |
| TRIAL-R2 / X_anon_gap text masking (`r7.mask_company`) | not used: it emits a token stream, and the case files need readable text | grading against live baselines (coin, 12-1 momentum, trailing-vol prior, past-earnings prior) by arm × level × part, with week-block SEs |

August's table beside tonight's (Brier / AUC; the tasks differ, so compare the shapes, not the
levels):

| arm | AMNESIA-1, 08-08 (12-month beat-market, 120 events) | AMNESIA-2, tonight (5-session beat-median, 569 clean events) |
|---|---|---|
| A0 named | 0.2495 / 0.550; recall 15.8% | 0.2671 / 0.44; recall 0.0% (post-cutoff) |
| A1 named + instruction | 0.2530 / 0.532 | not re-run (measured useless) |
| A2 masked | 0.2568 / 0.519; identified 0/120 | 0.2679 / 0.43; identified 24/569 (4.2%), famous 4/30 |
| A3 synthetic | 0.2564 / 0.521; identified 0/120 | 0.2718 / 0.43; identified 0/569, famous 0/30 |
| climatology / base rate | 0.2500 | 0.2494 |

## Design (as registered)

- **Event and decision point.** An 8-K with item 2.02. The decision session t is the last
  session strictly before the filing date, so the window t → t+5 contains the reaction
  whether the release came before or after the bell. The case states that a report is
  expected within two sessions.
- **Packet.** Every dated item is strictly before t's calendar date (`assert_pit` raises on a
  violation). It holds the price/volume summary, the past four 5-session earnings reactions,
  fundamentals by FILING date, analyst actions by their own dates (counts and objective
  changes in %, never levels), typed events, headlines (14 days, up to 8, 3 snippets), a
  coarse GICS sector and a size bucket.
- **Levels.** A0 carries real identity and levels. A2 carries no name, dates as "day -n", the
  close rebased to 100, no money levels in the structured blocks, rescaled amounts in text,
  and no years. A3 carries a fabricated name, ticker and year (2110-2149), and rescaled
  levels. Canary before forecast on every case.
- **Samples, never pooled.** CLEAN: 600 events drawn over 3 × 3 size × volatility terciles,
  569 after leak refusals. FAMOUS: 30. BACKTEST: 1,200 events in 20 weekly blocks,
  2018-02 … 2025-05, planned and leak-scanned (3,468 of 3,600 cases pass) and **not run**.
  None of the samples contains a delisted name, because the 8-K event file only covers
  issuers in today's SEC ticker map. That survivorship sits in the event source, not in the
  bars.
- **MDE.** The row-level 80%-power MDE is 5.9 pp at n = 569. With 10 weekly blocks the
  week-block MDE is 16-22 pp (printed per cell), so the block reading can see only a large
  edge.

## What the numbers say

1. **Direction: the model is inverted, not merely uninformed.** AUC is 0.43-0.44 at every
   level. The reliability table runs backwards: rows it gave p < 0.5 beat the median 53-65%
   of the time, rows it gave p > 0.5 did so 30-48%. It leans bearish into earnings (mean p
   0.46-0.48, 58-65% of calls below 0.5) while 52.4% of these stocks beat the median. Flipped,
   the calls would hit 55-56%, but the flipped week-block t is **0.83** over 10 blocks. This is
   a post-hoc observation to test on the next season, not a signal. The declared verdict is
   **FAILED_VARIANT** at all three levels: the Wilson high is 0.47-0.49, below a coin.
2. **Blinding changes nothing after the cutoff.** A0, A2 and A3 agree to within 1.5 pp. This
   matches X2, AMNESIA-1 and X_anon_gap: when there is nothing to remember, the name does not
   matter.
3. **Magnitude ties the free priors.** The interval score is 48.5-49.9 for the model, 48.3
   for the trailing-vol prior and 49.0 for the past-earnings prior. The week-block t against
   the vol prior is +0.5 to +1.5, i.e. no better. The model's 80% ranges cover 63-65% of
   outcomes, the vol prior's 59%, and the earnings prior's **77%**: the stock's own past
   earnings moves are the best-calibrated range here, and the model does not beat it. On the
   famous moves the earnings prior beats the model with t +3.4 to +4.2.
4. **Scenario calibration.** Scenarios given 0.2-0.4 contained the outcome 25% of the time,
   which is roughly fair. The main scenario, given 0.4-0.6, contained it only 27-31% of the
   time, so the model is overconfident in its base case. Only 27% of probability mass sat on
   scenarios whose range contained the realised return: the ranges are narrow and leave gaps.
5. **Text features as numbers (the owner's "emotion to data").** Controlling for trailing
   volatility, no feature carries rank information about |5-session move|. Pooled partial
   Spearman is between -0.08 and +0.06. The best week-block t is crowdedness at +1.7 and the
   worst is novelty at -1.8; none reaches 2. Emotional intensity correlates raw with the
   move's size (0.12-0.17), but that correlation vanishes once volatility is controlled.
   Emotion here re-encodes volatility (BETA_EXPLAINS in spirit). Management confidence is a
   constant 0.50 (sd 0.01), because the packet has no management voice (no call transcripts).
   Headlines exist for 167 of the 569 clean events (analyst actions or events for 565), so the
   text leg is thin. Only 7 of 30 famous cases have headlines, too few for a feature read.
6. **Leakage, per case, by canary.** A3 fiction: 0 identified out of 599. A2 with real
   headlines: 4.2% on clean dates and 13% on famous dates. That breaks the 10% line, and the
   leak comes through the text (products, people, deal names) that AMNESIA-1's numbers-only
   mask never carried. Named recall: 8/30 on famous cases, 6 of 8 right. Recall is real and
   sparse, and so far it lives in dramatic cases, as AMNESIA-1B found. **It did not raise the
   named forecast.**

## The owner's hypothesis, and what this can and cannot see

"A stronger model given a fictionalised past situation calls it better." Tonight tests the
WEAK model only: DeepSeek fails, as X2 did. The strong-model test is set up and waiting in
the file arm. The design can see an edge of about 6 pp at the row level, and about 16-22 pp
at the week-block level, on one earnings season. It cannot see a smaller edge, a different
season, other event types, or a model with memory across cases.

## Combining with the engine (specified, not wired)

`docs/research_notes/2026-09-28/how_the_engine_decides_2026-09-28.md` does not exist; no file
by that name is in either repo. The rows already carry the fields the forecast ledger uses
(`raw_probability`, `shrink_basis`, `arm`, `model_served`, `level`, `case_id`, `licence`,
`no_capital_authority`). The rule:

- Each arm × level is one component.
- Its reliability is a walk-forward logistic recalibration `a + b·logit(p)`, fitted on the
  arm's graded rows by week block, with **b floored at 0**. This is the rule §64 applied to
  the personas: negative discrimination gets zero weight.
- Components combine as a weighted average of recalibrated logits, weights ∝ b / SE(b).

On tonight's rows DeepSeek's b is negative (AUC 0.43), so its weight is 0. No row enters
`predictions.jsonl`, a book or an order.

## THE FILE ARM: how the orchestrator runs a strong model (not answered by me: I saw the mapping)

- Run folder: `C:\Users\mrthn\aegis-finance\backend\data\optimus\fiction_backtest\fb_20260928\`.
- Instructions: `…\fb_20260928\ANSWERING_INSTRUCTIONS.md`.
- Cases: `…\fb_20260928\cases\<case_id>.txt`. There are **2,456** files: 1,228 forecast cases
  and 1,228 canaries, each a separate file. Clean covers A2 and A3 (569 + 569 forecasts); famous
  covers A0, A2 and A3 (90 forecasts).
- Batches: `…\fb_20260928\batches\batch_001.txt` … `batch_128.txt`, 20 case ids each. A batch
  never mixes level, kind or part. In order:
  - 001-006: famous canaries (A0, A2, A3)
  - 007-012: famous forecasts
  - 013-041: clean A2 canaries
  - 042-070: clean A3 canaries
  - 071-099: clean A2 forecasts
  - 100-128: clean A3 forecasts
- **Run rule:** one fresh answering agent per batch. The same agent must never see a canary
  and its forecast, or two levels of one situation. Give each agent only:
  - the path of `ANSWERING_INSTRUCTIONS.md`;
  - its batch file;
  - the arm name, e.g. `opus`.

  It writes `answers\opus\<case_id>.txt`. It must never open `sealed\`, `rows\` or the
  receipts.
- **Minimum useful subset:** batches 001-012, the leak test (180 files), then 042-070 and
  100-128 (A3 clean, 1,138 files).
- **Ingest and grade:** `python -m scripts.fiction_backtest ingest --run fb_20260928 --arm
  file:opus --model-id <exact model id>`, then `python -m scripts.fiction_backtest analyze
  --run fb_20260928`. Opus's cutoff (June 2026, stated, not probed) is before every clean
  decision date (2026-07-01 onward).

## Unfinished

- NVIDIA (`meta/llama-3.2-11b-vision-instruct`, free; ~10 rows/min under rate limits) is still
  running detached: famous first, then clean. PID file `…/fb_20260928/run_nvidia.pid`. Its
  rows so far are in the receipt. Re-run `analyze` when it ends.
- The 21-session direction for the last clean week matures by about 2026-10-01. Re-run
  `analyze`; outcomes are computed at analysis time and are never stored in the plan.
- BACKTEST (1,200 events) is planned but not run. Run it only on a model whose FAMOUS leak
  test passes.
- The trial doc is uncommitted (no commits by rule). Its sha256 stands in until the owner
  commits it.

**WHAT WORKS:** The fiction level holds and is now testable on any model. A3 synthetic cases
were identified 0 times in 599 canaries, including the 30 most famous earnings moves, and
the strict parse, cap, file-arm confinement and PIT guard are pinned by 20 tests.
**WHAT DOES NOT:** DeepSeek-flash after its cutoff is worse than a coin on 5-session earnings
direction (AUC 0.43-0.44 at every level). Its ranges tie the free volatility prior and lose
to the stock's own past earnings reactions, and its text "emotion" scores carry nothing
beyond volatility. Masking with real headlines leaks: 13% of famous cases were identified.
**HIGHEST-EV EXPERIMENT:** have Opus sub-agents answer batches 001-012 and the A3 clean
batches through the file arm tonight. That is the owner's hypothesis on the exact same 569
post-cutoff events, graded by the same code in minutes. Tonight's 5.9 pp row-level MDE
bounds what a win would have to show.


## Amendment 2026-09-29: the Opus arm is CANNOT_DISTINGUISH, and by the registered rule its fiction LEAKS

Dated amendment, written after `docs/reviews/REVIEW_2026-09-29_FICTION_BACKTEST.md`. Nothing
above is edited, `receipt_analyze.json` is not rewritten, and no new Opus batch was run. The
numbers below come from a NEW receipt that calls no model:
`backend/data/optimus/fiction_backtest/fb_20260928/receipt_amendment_20260929T032126Z.json`
(`python -m scripts.fiction_backtest amend --run fb_20260928`).

**1. Opus direction, clean A3, n = 120: relabelled `CANNOT_DISTINGUISH (model abstained)`.**

- The formal rule still returns `FAILED_VARIANT`: hit 44.6%, and the Wilson 95% upper bound of
  0.539 is below 0.55. That verdict is printed unchanged.
- The reading changes, because the model declined to forecast:
  - the sd of p is 0.019, and p runs from 0.44 to 0.53;
  - 37 of 120 answers (30.8%) are exactly 0.50;
  - the AUC is 0.461;
  - on the 83 rows where it took a side, it was right 42.2% of the time.
- The below-coin hit rate is a calibration offset, not discrimination. The model leaned
  bearish by a few points on a sample where 54.2% of names beat the median.
- "Opus 44.6%, no direction skill" is withdrawn as a verdict on LLMs. It measured an
  abstention, at n = 120 (row MDE 12.8 pp), at the level that removes the model's legitimate
  knowledge of the company.
- `grade_cell` and `verdicts` now print `share_p_exactly_half`, `hit_when_took_a_side`, the
  AUC and a `direction_reading` beside the formal verdict whenever sd(p) < 0.03.

**2. The registered leak rule, computed for Opus: THE FICTION LEAKS.**

- The rule: "the fiction LEAKS if A3 identifies the company on > 10% of canaries or the A3
  famous hit rate is >= 0.70".
- Opus identified **7 of 30** A3 famous canaries (23.3%): MRNA, AMZN, SMCI, APP, MRVL, UNH and
  COIN. The first clause fires.
- The second clause is `NOT_EVALUATED`, because the Opus famous forecasts (batches 007-012)
  were never answered.
- By the registered rule, every future BACKTEST reading for Opus at this fiction level is
  void. "The fiction level holds and is now testable on any model" is false for Opus.
- The original receipt had no Opus leak verdict, because `leak_test` iterated only the arms
  that had answered famous forecasts. `leak_table` now covers every arm that has famous A3
  canaries, and marks an unevaluated clause as such.

**3. Provenance of the file-arm answers.**

- The answering agents were full coding sub-agents, with file, shell and web tools.
- Their confinement was an instruction (`ANSWERING_INSTRUCTIONS.md` rule 3). The sealed plan
  sat one directory away, and **no tool-call log was kept**.
- The confinement test pins only the harness reader.
- Nothing suggests a lookup tonight: a model that looked would not score 44.6%. But no file
  on disk could rule one out, and any future file-arm score must carry its own tool log.

**4. Where the number had been used as grounds for a rule.**

- `docs/research_notes/2026-09-29/night_report_2026-09-29.md` §5 cited "Claude Opus 44.6%" as
  the reason for a zero weight on LLM direction calls in the shadow book. It is amended there.
- The zero weight stays, because there is no evidence FOR a weight. It is not "measured below
  a coin".
- `scripts/shadow_bayes_rule.py` v0 never cited the number: its `investigator_dir` entry
  cites lane X and §64. The v1 successor's `llm_direction` entry states the honest reason.
