# LLM text-to-data, blinding, and scenario generation — what exists, what the literature says, five experiments

**2026-09-28. RESEARCH ONLY — no code changed.** Licence of everything below: read as
`PRODUCT_EXPERIMENT` research; nothing here is a `RESEARCH_CLAIM`. Written after
`CLAUDE.md`, `docs/INDEX.md` TIER 0, `docs/AEGIS_VISION_2026-08-28_MURAT_IN_HIS_OWN_WORDS.md`,
and `docs/ROADMAP_2026-09-28_MEASURE_BEFORE_YOU_ADD.md`, and after the check-the-trials-folder
pass required by this project's own house rule.

**Owner's framing (2026-09-28), kept verbatim because it is the brief:** *"the idea is to
learn. reason and logic, converting non numerical data such as human emotions, news
psychology to data with llm is important. i think our fine tuning of LLM usage, making up
scenarios, blinding is something promising we are not leaning on."* And: *"making a
profitable engine is my goal ... dont be afraid to test things, see if it works or not."*

---

## PART 1 — WHAT ALREADY EXISTS HERE

This project's own rule: "check the trials folder before calling an idea new." All three
topics in the brief (blinding, scenarios, text-to-numbers) turn out to have real, measured,
receipted prior art — in `Aegis module` (the earlier-phase sibling repo) and in
`aegis-finance/backend/data/optimus/night_factory_*`. Nothing below is newly discovered by
this note; it is inventoried.

### 1(a) BLINDING / AMNESIA

**TRIAL-LLM-AMNESIA-1 / -1B — `C:\Users\mrthn\Aegis module`, measured 2026-08-08.**
Files: `TRIALS/PREREG_LLM_AMNESIA_1.md` (pre-registration), `docs/AMNESIA_VERDICT_2026-08-08.md`
(verdict), `aegis_brain/llm/amnesia.py` (the masking + synthetic-scenario generator, now the
standing input path), `runs/AMNESIA/AMNESIA_1.json`, `runs/AMNESIA/AMNESIA_1B.json`.

Murat's original question: *"Can we force DeepSeek not to remember? We put guidelines
saying don't use historical data."* Design: **120 real situations**, US large/mid stocks,
formation months 2005-01..2021-12, outcome-balanced 60/60 on "beat the market over the next
12 months," identical point-in-time percentile facts across four arms that differ only in
disclosure: A0 named-raw, A1 named + a strong "you are standing in {date}, do not use later
knowledge" instruction, A2 masked (no name, no date), A3 synthetic (fabricated name/date,
jittered facts). `deepseek-chat`, temperature 0, **1,080 calls total**, every prompt/response
cached and hashed before any call was made.

Results (Brier / AUC / canary-identification or canary-recall rate):

| Arm | Brier | AUC | canary |
|---|---|---|---|
| A0 named, no instruction | 0.2495 | 0.550 | recalls outcome on **15.8%** |
| A1 named + suppression instruction | 0.2530 | 0.532 | recalls on **15.8%** (identical to 3 dp) |
| A2 masked | 0.2568 | 0.519 | identified **0/120** |
| A3 synthetic | 0.2564 | 0.521 | identified **0/120** |
| logistic regression, 5 features, OOS | 0.2538 | 0.511 | — |
| climatology (always 0.5) | 0.2500 | — | — |

Six pre-registered predictions, four hit / two miss (full table in the verdict doc). The
load-bearing findings:

1. **The instruction did nothing** — 15.8% vs 15.8% recall, ΔBrier +0.0035 (instructed arm
   slightly *worse*). "Don't use historical data" is not a control; it changes what the
   model says, not what it does.
2. **Masking works, and is verifiable** — 0/240 identifications across masked+synthetic
   arms. The canary (a separate, pre-forecast call asking the model to identify the company
   and year, or say UNKNOWN) is how you *know* masking held rather than assume it.
3. **Aggregate metrics hide contamination.** Removing identity cost only 0.007 Brier
   overall — but the positive control (AMNESIA-1B, same 120 names, no suppression framing,
   asked directly "what happened to this stock") answered only **5 of 120 (4.2%)**, and was
   **5 for 5 correct on direction** on the ones it answered — all five famous collapses
   (PYPL −64%, CHK −71%, GOEV −81%, THQI −41%, BTU −16%). Numeric magnitude was still
   confabulated (median absolute error 43.6 pp) even when direction was right. **Contamination
   is real, sparse (~4%), self-selecting toward dramatic/catastrophic outcomes, and invisible
   in an aggregate score** — it must be measured per-case with a canary, never inferred from
   an average.
4. **Synthetic scenarios validated as a substitute for real ones**: A3 scored within 0.0004
   Brier of A2, meaning a scenario fabricated from real panel data with name/date replaced is
   treated the same as a masked real one — this is the scenario-generation machinery's own
   validation study, done as a byproduct.
5. **The task itself was retired for LLM evaluation**: 12-month relative return from five
   percentiles is unlearnable for the LLM *and* the 5-feature logistic baseline (both at
   climatology). AMNESIA-2 (5-day abnormal reaction around earnings/FDA events, where the
   baseline bank has measurable signal) was the stated next step. **No evidence was found
   that AMNESIA-2 has run** — this is open.

**TRIAL-R2 (monthly news-digest read) — `aegis-finance`, registered 2026-09-10,
`docs/TRIALS/TRIAL-R2-monthly-news-digest-read.md`.** This is the direct successor: does a
local 7B reading an *anonymised* one-month news digest call next-month market-adjusted
direction better than the same pipeline reading a random other month's digest — imports the
AMNESIA canary as a gate rather than re-deriving it.

- **PANEL-A** (reported, never deciding): 2015-2024, 135 names, 112 monthly blocks. Arm
  **+21.845%/yr vs shuffled-control +5.656%/yr** — a **+16.189%/yr difference, t=3.922**,
  sign accuracy 0.542 vs 0.4911, AMNESIA canary **passed** (gap **−0.0041**: masked read
  slightly *beats* named read, i.e. the model reads rather than recalls). Declared
  CONDITIONAL, not a claim, for three named reasons: gross of costs, a 135-name panel
  dominated by NVDA/SPY/AMD document counts (mega-cap skew), and a prompt that was not
  registered when PANEL-A ran.
- **PANEL-B is the pre-registered decisive test**: the E1 panel
  (`backend/data/optimus/text_return_panel/`), 2025-01..2026-07, up to **3,060 symbols**,
  19 monthly blocks, built from `prices_2025_26/bars.parquet` (1,287,668 rows, 2025-01-02 to
  2026-09-25). A frozen 300-cell draw exists (seed 20260909, sha
  `10480a8e97e3e1af...`, stratified by month block), the masking pipeline is built
  (`night_x_anonymisation_gap.py` / `scripts/night_factory_jobs.py: "X_anon_gap"`), and the
  full **P1-P6 protocol** (`backend/services/protocol_p16.py`) is enforced on every receipt:
  P1 temporal integrity (anonymisation + date-shift placebo + stated model cutoff), P2
  dynamic-universe/delisting handling, P3 direction-flip counterfactual, P4 calibration/ECE,
  P5 full frictions (25 bps/side costed), P6 disaggregation/field provenance.
  **Corrected status, reconciled from two independent verification passes (an initial pass at
  this note under-read the record and called PANEL-B "never read"; it has in fact been read,
  and decided):** two distinct, separately-registered questions were run on this panel, and
  they must not be conflated.

  1. **TRIAL-R2's own primary, pre-registered hypothesis** (masked read vs. shuffled control,
     the actual "does anonymised news reading predict next-month return" question) —
     `night_factory_2026-09-13/R2_widened_panelB_run02.json`: **`verdict: "REJECT (registered
     clause): net difference -0.26%/yr, t -0.097, arm net -3.513%/yr vs control net
     -3.253%/yr"`**. Both arms lose money net of costs on this panel and are statistically
     indistinguishable from each other. **PANEL-A's conditional +16.19%/yr did not replicate
     on the pre-registered decisive panel — the honest reading of TRIAL-R2 as of today is a
     completed, negative result**, not an unread one.
  2. **`X_anon_gap`'s separate, secondary question** (does raw/named text beat masked text —
     i.e. does identity leak matter, independent of whether either arm makes money):

     | Date | Verdict | Raw vs masked | Gap | Canary |
     |---|---|---|---|---|
     | 09-14, 09-19 | `ADOPTED_ARM=MASKED` | raw −18.886%/yr net vs masked −16.87%/yr net | **−2.016pp/yr, t −0.543** | 0.0027 |
     | 09-22 | `ADOPTED_ARM=MASKED` | raw +1.445%/yr vs masked +3.029%/yr | **−1.584pp/yr, t −0.212** | 0.0027 |
     | 09-26 | `PENDING_MODEL` | `llama-server` unreachable, no call made | — | — |
     | 09-27 | `FAILED` | exited 1, no receipt | — | — |

     In every run that completed, raw (named) text did not beat masked text — the adoption
     rule defaults to MASKED every time, at statistically-indistinguishable-from-zero
     t-stats. Identity carries no measured information advantage on this design, which is
     itself a clean (if secondary) answer.

  **What is genuinely still open**: (a) the two `X_anon_gap` runs disagree in *sign* of the
  raw arm's level (−18.9%/yr in 09-14/19 vs +1.4%/yr in 09-22) on what should be overlapping
  data — not yet reconciled, possibly different cell draws between runs; (b) the instrument
  has since broken (09-26 `PENDING_MODEL`, 09-27 `FAILED`, no receipt) and needs repair before
  any new block can be added; (c) with the primary hypothesis already `REJECT`ed, the
  remaining live question on this exact design is not "does it work" but "was PANEL-A's
  result the 2015-2024 era, the mega-cap skew, or the unregistered prompt" — the three
  alternatives TRIAL-R2's own registration named and PANEL-B was supposed to separate; that
  attribution has not been done.
- Qwen2.5-7B-Instruct's stated cutoff is recorded in the receipts as **2024-06-30**
  (community trackers + provider pages, confidence MEDIUM, not an official Alibaba page).
  Because PANEL-B's dates (2025-01 onward) are entirely after that cutoff, contamination in
  the AMNESIA-1 sense is structurally impossible there — which is exactly why PANEL-B cannot
  answer a *memorization* question and its `REJECT` above should be read purely as "no
  reasoning-over-text signal found," not as evidence about leakage one way or the other.
- **L3** (`scripts/night_l3_lookahead.py`, job `L3_lookahead`) implements the external
  Lookahead-Propensity design (Gao/Jiang/Yan, arXiv:2512.23847: a date-recall probe scored
  against forecast accuracy, split at the model's training cutoff — see Part 2.1).
  `night_factory_2026-09-12/L3_lookahead_run01.json` did produce a partial number — 435
  gradeable cells over 18 blocks, **post-cutoff sign accuracy 0.4713**, but "the PRE-cutoff
  arm is EMPTY" (PANEL-B alone cannot straddle the cutoff, confirming the point above); a
  later run (`night_factory_2026-09-13/L3_lookahead_deepseek_run02.json`) is fully `REFUSED`
  ("PANEL-A carries no persisted per-cell answers... L3 cannot read what was not written").
  **The cheap version that CAN straddle the real cutoff — LAP on PANEL-A (2015-2024) — is
  named as "unbuilt" and "owed" in
  `docs/research_notes/2026-09-21/research_multi_role_llm_forecasting.md` and has not been
  run**, because PANEL-A's per-cell answers were never persisted (only a summary was written
  when it ran on 2026-09-08). L4 (`night factory L4_qwen3_measure*`) is separately the
  Qwen3-30B hardware measurement track; its latest receipt is **REFUSED** (reader had the
  wrong model loaded).
- A third, distinct trial, **`TRIAL-LEAK-1`** (`docs/TRIALS/TRIAL-LEAK-1-identified-vs-
  masked.md`, registered 2026-08-12, status `ACCRUING`/class `ARCHITECTURE_RESULT_ONLY`),
  adds an era stratum (pre-cutoff 2015-2023 vs. recent 2025-03..2026-05, 2024 excluded as
  ambiguous) via a difference-in-differences design, specifically to separate memory from "a
  stripped prompt is just harder to read." Its honest prior explicitly **expects the leakage
  arm to come back NOT DETECTABLE**, consistent with AMNESIA-1's 4%-prevalence recall
  finding. A planned model-diversity arm (H5) was voided mid-trial when `deepseek-chat` and
  `deepseek-reasoner` were found to alias to the same underlying `deepseek-v4-flash` model.
  On disk: a "canary" wave ran 2026-08-12 (1,600 calls: 703 identifications, 97 refused-mask,
  800 recalls), and `backend/data/optimus/leakage_probe_predictions.jsonl` holds ~186 rows —
  but **no verdict document and no computed difference-in-differences was found**; the
  primary question this trial exists to answer is unanswered on disk.

**Event-vocabulary drift (a smaller, text-to-numbers-adjacent blinding-relevant defect,
self-flagged in code):** `backend/services/event_vocabulary.py` — the spec's closing
sentence says "38 substantive + `no_event` = 39," its own table has 39 substantive ids (40
with `no_event`), and comment at line 98 records "v2 made the table 43 ids and the protocol
went on saying 40" — a live drift the code calls out rather than hides.

**Open under 1(a):** TRIAL-R2's primary hypothesis is **decided (`REJECT`)** on PANEL-B, so
this is not an unread test — but the three-way attribution (era / mega-cap skew / unregistered
prompt) that would explain why PANEL-A looked promising and PANEL-B did not has never been
done. The `X_anon_gap` instrument is currently broken (09-26 `PENDING_MODEL`, 09-27 `FAILED`,
no receipt) and its two completed runs disagree in sign on the raw arm's level, unreconciled.
LAP-on-PANEL-A (the one cheap version of the lookahead-propensity test that can actually
straddle the real cutoff) is named as owed and has not been run, because PANEL-A's per-cell
answers were never persisted. TRIAL-LEAK-1 ran a canary wave (1,600 calls) but has no
completed verdict or computed difference-in-differences. AMNESIA-2 (short-horizon event
reactions) was specified and not found to have run. A time-locked control model
(ChronoGPT-style, see Part 2) is explicitly out of scope for this project ("not distributed
as GGUF," per the X_anon_gap receipt) — the strongest literature-grade contamination check is
known and deliberately not attempted here.

### 1(b) SCENARIOS / PERSONAS / COUNTERFACTUALS

**S2_scenario_gym — `scripts/night_scenario_gym.py`, job `S2_scenario_gym`, spec
`docs/research_notes/2026-09-20/spec_decision_engine_and_scenario_gym.md` Part C.** Murat's
framing, quoted in the spec: *"a gut feeling, tested against good and bad made-up scenarios
built from our own data."* Design: for each of 300 frozen cells (same E1 panel, seed
20260920, 19 month blocks), a committed decision is made, then a byte-identical scenario has
one favourable or one adverse development appended (from a hashed counterfactual library,
frozen `counterfactual_library_hash`), plus an unrelated-sentence control appended, and the
gym measures whether and how far the decision *moves*.

Measured (`night_factory_2026-09-21/S2_scenario_gym_run01.json`, 300 cells × 6 arms, 1,800
calls, $0, local Qwen2.5-7B):

- **The decision DOES move with the story**: good-twin lift vs its shuffled control t=4.914,
  bad-twin lift t=2.158 — the model is responsive to the appended development, not inert.
- **But sign accuracy on the real arm is 0.4219** (worse than the base rate 0.4219... i.e.
  at chance on this panel) and **calibration is badly overconfident**: ECE 0.3154, mean
  stated confidence 0.7373 vs realized base rate 0.4219, ~31 pp of pure overconfidence in
  every decile bucket reported.
- **Net economics: the real (story-driven) book returns −8.27%/yr gross / −14.11%/yr net;
  the SHUFFLED-DIGEST CONTROL returns +15.37%/yr gross / +9.53%/yr net** — the placebo beats
  the story by ~24 points annualized, t=−1.57 on the difference. The gym's own receipt
  states the caution explicitly: *"X_anon_gap's 09-19 run found BOTH of its arms lose money
  net on this panel... this block is reported, never deciding."*
- **Verdict: `NOT_ADOPTED (reliability_weight 0)`** — the stated adoption gate is
  N≥300 over ≥12 independent month blocks **and a forward record**; the N/block gate is
  met (300 cells, 19 blocks) but no forward record exists yet, so it stays at weight zero by
  construction, not by a failed statistical test.
- Only **27 of 300 cells (9%)** carried a typed-event row from the 39/43-id vocabulary; the
  rest fell to a generic development pair — most "twins" here are generic, not
  event-specific, which bounds how much of this result can be attributed to a specific
  causal mechanism versus a generic positive/negative frame.

**`backend/services/scenario_forecasts.py` (chunk X3) — the graded probabilistic-scenario
contract, explicitly NOT WIRED.** Its own module docstring: *"THIS MODULE IS THE CONTRACT
ONLY. IT IS NOT WIRED INTO THE MORNING."* Design (Murat's framing, quoted in the file): the
model writes k plausible next-session headlines with probabilities, the deterministic engine
prices each by a historical `(event_type, era)` base-rate lookup (`pricer` is a pure lookup
and REFUSES on a missing cell rather than defaulting to zero — "a missing base rate is not
a base rate of zero"), and the ledger grades which scenario reality picked plus the Brier of
the whole set. `backend/services/signal_reachability.py` classifies it: **`AWAITS`** — it is
"shipped BEFORE its two inputs exist": L2's typed-event extraction over the daily corpus, and
E1's `(event_type, era)` base-rate table. Exercised only by `test_scenario_forecasts.py`;
`declaration()["wired"] is False` in its own code.

**Personas vs. process — the strongest single finding under this topic
(§64, 2026-09-24 ledger grading; corroborated 2026-09-28).**
`backend/services/investigator_agent.py` documents the design rationale directly: an
earlier scheme ("NIGHT-14") gave 14 "personas" one large common contract (scenario + thesis
+ counter-thesis + forecast in one call) and measured **0.49 effective distinct ideas versus
0.85 for one generic agent at one-fifth the calls** — "the personas were one forecaster
wearing hats, and the schema was doing the wearing." The replacement is division of
*cognition*, not persona: five small, separately-gradeable microtask contracts
(gather → event → expectations → forecast → critic).

Held-out grading of the forecast ledger — the primary source is **`NEGATIVE_RESULTS.md` §64**
("Fourteen LLM specialists, 14,703 graded forecasts: −17% skill. The five that WORK are a
process, not a personality"), scored by `scripts/night_specialist_scoreboard.py`, receipt
`backend/data/optimus/specialists/scoreboard_2026-09-24.json`; the table is reproduced in
`docs/HANDOFF_2026-09-24_THE_LEDGER_WAS_THE_ANSWER.md`,
`docs/ROADMAP_2026-09-28_MEASURE_BEFORE_YOU_ADD.md` and
`docs/reviews/REVIEW_2026-09-28_ADVERSARIAL_INVESTOR_ON_THE_PROJECT_AND_ITS_REVIEWER.md`.
Overall ledger skill at the time: Brier 0.2625 vs. climatology 0.2244, i.e. **−17.01%**
(later, on more data the same session, 14,703→17,484 rows, this deepened to **−19.35%**, same
split pattern). The nine named thematic personas are `geopolitical, behavioral_narrative,
ownership_flow, event_news, company_fundamental, biotech_pharma, semis_technology,
accounting_forensics, options_volatility` — each a "you are the X analyst" mega-schema call:

| family | n test | raw skill | recalibrated skill | weight | discrimination |
|---|---:|---:|---:|---:|---:|
| `investigator:*` (structured 5-stage process) | 2,325 | **+4.38%** | **+8.97%** | 0.65 | **+16.7** |
| thematic personas (9 arms) | 5,027 | **−27.98%** | −0.00% | **0.00** | −2.0 |

Skill lives at h=1 (+5.75%, discrimination +17.8) and is **gone by h=5** (+0.09%).
**"A structured evidence procedure forecasts. A persona does not."** The nine personas are
now named in a `RETIRED_WEIGHT_ZERO` tuple in `scripts/night_investigator_forecast.py`
(~line 216), citing §64 verbatim — their code is kept (`backend/services/llm_swarm.py`) for
other research uses but is no longer weighted in production forecasting.

Two caveats measured the same week, both changing the reading of the headline number:

1. **The investigator's skill is magnitude-only. On direction it is −8.7%.** Found
   independently three times the same week
   (`docs/reviews/REVIEW_2026-09-25_CHUNK0_THE_DAYS_BUILD.md`;
   `docs/reviews/ADJUDICATION_2026-09-26_AUDIT_SINCE_AUGUST.md` row 2;
   `REVIEW_2026-09-28_ADVERSARIAL_INVESTOR...md`). The first of these shows *why* concretely:
   on `return_sign` h=5, realized up-rate across stated-probability bins is flat-to-inverted
   (0.43→0.40, 0.50→0.42, 0.55→0.41, 0.59→0.39, 0.66→**0.355**) — the two *highest*-confidence
   bins have the *worst* mean returns. The fix ordered by the 09-26 adjudication: store
   `raw_probability` separately and stop applying the magnitude-earned 0.65 shrink to
   direction rows, which it had been mis-applied to.
2. **A free trailing-63-day-volatility formula beats the investigator on the same magnitude
   questions**: +10.2% vs +5.7%, **winning 7 of 8 days**
   (`docs/reviews/ADJUDICATION_2026-09-26_WAVE1.md` row 3: "the LLM lowers skill from the
   vol prior"). The TIER 0 pitch (`AEGIS_STRATEGY_2026-09-26_ONE_PIPELINE.md` §8) had quoted
   +8.97% vs −27.98% without this comparator; the adversarial review of 2026-09-28 flags that
   the pitch "has not been corrected."
3. **Few independent observations sold as many rows**: the 468 investigator rows are 5 arms
   answering the same questions on 8 dates; arm correlation 0.70–0.93 → about **1.5
   independent forecasters**, not 5. "17,484 graded" is a row count, not an information
   count. 9,011 of 26,631 forecasts in the ledger are not yet due.

**Open under 1(b):** whether a genuinely event-specific (not generic) scenario twin, graded
on calibration rather than sign, beats the trailing-vol prior — nobody has run that
comparison (S2_scenario_gym grades movement/sign, not a proper scoring rule over a
distribution); scenario_forecasts.py's Brier-graded probabilistic design has never executed
once end to end.

**Precedent worth carrying forward: the false-discovery ceiling.** The earlier-phase
`Aegis module/docs/ARENA1_REPORT_2026-08-11.md` scored 384 portfolio genomes on 2002-2022
CRSP plus 11 synthetic ("made-up") worlds with planted effects specifically to calibrate a
**noise ceiling**: the best noise-genome CAGR excess was **+4.87%/yr**, and the random-score
control ranked 4th of 384. Nothing from that arena graduated. Any future scenario/persona
sweep that reports a "best of N" number should be read against a noise ceiling of this shape
before it is treated as a finding — see Part 4.

### 1(c) TEXT TO NUMBERS

- **Typed events, extracted and graded against forward returns**: `event_vocabulary.py`, 39
  substantive ids + `no_event` (v1) / 43 ids (v2, with the drift noted above). Extraction
  itself (`scripts/night_l2_typed_events.py`, job `L2_typed_events`) is measured: a 09-13 run
  typed 6,007 of 6,020 rows with kappa 0.870 on 50 re-prompted cells (53.0% `no_event`); a
  09-22 run typed 3,478 of 3,576, kappa 0.845 — extraction agreement is genuinely good.
  Coverage of the wider E1 panel is uneven: 9% of cells in S2_scenario_gym's frozen 300-cell
  draw carried a typed row, but a larger dedicated run (`E1_event_head`) reached 24.8%
  coverage (32,384 of 130,719 cells). **This typed-event → return pipeline has actually been
  graded end to end**: `night_factory_2026-09-22..26/E1_event_head*_run01.json` tests both a
  43-way one-hot and a direction×confidence scalar against forward returns with a
  capacity-matched shuffled control over 280 date blocks — **`FAILED_VARIANT`**: EVENT minus
  SHUFFLE IC **+0.0037, t=0.808, Holm p=1.0**. Extraction quality is real; the extracted
  events carry no measured forward-return information over a shuffled placebo of the same
  size.
- **Thesis cards / promise tracking**: `backend/services/thesis_card.py`,
  `scripts/thesis_cards.py`, `backend/data/optimus/thesis_cards/`. A card is three
  separably-gradeable parts: evidence, thesis, promise. **The thesis/direction leg is graded
  and negative**: `docs/reviews/ADJUDICATION_2026-09-26_AUDIT_SINCE_AUGUST.md` row 4 finds
  **112 of 166 `thesis_card:v1` rows sit at p=0.50** (uninformative by construction — "a
  neutral card / HOLD label IS 'no view'"), and the 2026-09-28 adversarial review states LLM
  direction skill from cards is **−7.9%**; the related `review:v0` (post-hoc daily review
  labels) is worse still, **383 of 385 rows at p=0.50**. **The promise leg is graded
  differently and more usefully**: a promise with a **numbered target** is graded by a
  *deterministic* parser over the company's own 8-K EX-99 earnings release
  (`grade_numeric_promises`), **never by an LLM** — the target is declared before the due
  date, the grade is parsed arithmetic after it (`source_reads.py::run_grade_promises`,
  scheduled daily via `daily_pass.py`; example: a TER Q2-26 revenue promise of
  $1.15-1.25B graded `DELIVERED` against $1,329M actually reported). Separately, the
  fixed-probability `promise:v1` *forecast* arm (P(beats SPY)=0.50 regardless of content) was
  retired on 2026-09-26 because "every outcome scores Brier 0.25, so they grade nothing and
  dilute the one skilled population in `predictions.jsonl`" — a text-to-number pipeline
  measured to carry literally zero information and removed rather than kept for appearances.
- **Claim extraction**: `backend/data/optimus/sources/claims.jsonl` — 53 rows as of this
  session, X/Twitter industry-specialist claims (`x:dylan522p`, `x:semianalysis_`) with a
  `direction` field mostly null. Small-N, early-stage; not yet graded at scale on its own
  (project memory records a much larger "39,768 corpus rows" archive behind the broader news
  pipeline, which is a different, larger object than this claims file).
- **Source scorecard (WSJ / Barron's / MarketWatch text vs. what happened)**: per the commit
  log (`129be6ed`) and `docs/research_notes/2026-09-27/source_scorecard_2026-09-27.md` /
  `backend/data/optimus/.../source_scorecard_2026-09-28_000228.json` — **this IS graded**,
  and the result is negative: **0 of 60 cells earn a weight**; every Dow Jones cell is
  `TOO_FEW` (9 publication dates out of ~110 needed). A text-to-number grading pipeline that
  ran, produced a receipt, and returned "cannot distinguish," honestly reported rather than
  discarded.
- **Analyst revision text / IBES**: 393,369+ dated analyst revisions banked
  (`actor_corpus/ibes_graded.parquet`, 98,772 records, 5,793 analysts, `RELIABILITY_PERSISTS`).
  As of the 2026-09-25 audit (`docs/research_notes/2026-09-26/audit_forecasts_and_learning_
  since_august.md`), **ANALYST-SKILL-1 was "registered 08-31 and never run."** It has since
  run (`backend/data/optimus/analyst/analyst_skill_1_receipt.json`, started
  2026-09-26T08:46:55Z; 364 brokers measured, 467,221 estimation targets graded, grand median
  broker skill −0.21311, persistence Spearman 0.7631 between 2013-15 and 2016-18 cohorts) —
  but the honest reading is more qualified than a bare "ADOPT": the receipt's own verdict
  string is `ADOPT` (ΔIC +0.00084, t=2.52, 71 months, the registered clause's threshold), and
  the separate write-up `docs/ANALYST_SKILL_1_VERDICT_2026-09-26.md` states this is **~1/12
  of the declared worth-building effect and is mechanically attenuation of an anti-signal**
  (raw consensus-upside IC is −0.068) rather than new information, and recommends **not
  funding it**. Registered-word `ADOPT` and "don't fund" are both true at once here — a good
  example of why the registered clause and the economic-materiality read must both be printed,
  never just the pass/fail word. A companion earlier-phase result,
  **ANALYST-IBES-1** (`Aegis module/docs/ANALYST_IBES_1_VERDICT_2026-08-11.md`): analyst
  target *revisions* are real gross and dead net, target *levels* lose money outright
  (−8.6% to −17.6%/yr net in all 8 cells tested; best accruing cell +5.29% net, t=1.66).
  A related revision-flow sweep on the wider yfinance panel (392,201 rows,
  `sim_run.u_analyst`) found a near-null +0.32%/hold at k=20 falling to +0.04% at k=50, worst
  leave-one-year-out +0.02% once 2020 is dropped.
- **Emotion/sentiment/attention as a first-class extracted number**: **not found as a
  standalone, graded pipeline.** The closest live object is S2_scenario_gym's confidence
  field (graded, and found badly overconfident) and the source scorecard (graded, and found
  `TOO_FEW`). No dedicated "fear/novelty/attention_z" extraction-and-grading pipeline exists
  yet in this repo under that name — this is a genuine gap, not a rediscovery risk, and Part
  3 experiment 2 is designed against it.

### 1(d) SCHEDULED CALLER vs. UNREAD

`scripts/sim_run.py` is the actual nightly production cycle, wired in a fixed unit order:
`reconcile → funnel → analyst → rank → forecast → review → plan → learn`.

| Mechanism | Status |
|---|---|
| `investigator` 5-stage process | **Scheduled and hardened.** `sim_run.u_forecast` (line ~476) explicitly documents itself as "the scheduled caller" — written after a 2026-09-11→09-24 gap where the ledger gained zero investigator rows because running it was "a script somebody had to remember." Calls `scripts/night_investigator_forecast.py`. |
| Promise-vs-delivery grading | **Scheduled.** `scripts/daily_pass.py` step `grade_promises` runs `source_reads.py --grade-promises` once per UTC day, comparing numbered management promises against actual 8-K EX-99 figures (e.g. a TER Q2-26 revenue promise graded `DELIVERED` against the actual filed number). This was itself a 09-xx fix — an earlier adjudication found "nothing called `source_reads --grade-promises`" before it was wired into `daily_pass.py`. |
| `analyst_skill_1.py` | Attended CLI (`python -m scripts.analyst_skill_1 --run`); ran once 2026-09-26 (`ADOPT` on the registered rule, but the verdict doc itself says don't fund it — effect is ~1/12 the declared worth-building bar and largely attenuation of an anti-signal). Analyst revision *text* more broadly is wired as `sim_run.u_analyst` (392,201 yfinance revision rows). No recurring schedule found for `analyst_skill_1.py` itself. |
| `scenario_forecasts.py` (X3) | **No caller anywhere.** `signal_reachability.py`: `AWAITS`. |
| Thesis cards (`scripts/thesis_cards.py`) | **Manual only.** Triggered from a session (`--trigger`); not present in `daily_pass.py`'s STEPS dict (`bars_refresh, grade_promises, news_pull, analyst_snapshot, book_cadence, decision_contract, grade_forecasts, grade_books, paper_accounts, bridge_report, coverage, scoreboard, health`). |
| Source scorecard (`scripts/source_scorecard.py`) | **Manual only** — its own write-up says "re-run it with `python -m scripts.source_scorecard`"; not in `daily_pass.py`. |
| `X_anon_gap`, `S2_scenario_gym`, `L3_lookahead`, `L4_qwen3_measure`, `X2_elasticity`, `X4_regime_route` | Registered as dispatchable entries in `scripts/night_factory_jobs.py`'s `JOBS` dict, but their actual caller is **`scripts/always_on_lab.py`** — a separate, unattended overnight research lab, not `sim_run.py`'s production cycle. This caller exists but is fragile: the 09-26 run returned `PENDING_MODEL` (reader down) and 09-27 `FAILED` with no receipt, and the project's own 2026-09-28 adversarial review lists `always_on_lab.py` on its ten-module **delete-or-freeze-read-only** list, citing ~$2.6/day of unwatched spend and at least one job that "waited 8.5h for a model nothing started." A registered job with a fragile, review-flagged-for-deletion caller is functionally closer to unscheduled than scheduled. |
| `TRIAL-LEAK-1` | Ledger exists (`backend/data/optimus/leakage_probe_predictions.jsonl`); invoked via `scripts/run_leakage_probe_1.py`, no cron found. |

---

## PART 2 — THE LITERATURE (2023–2026, primary sources)

Full per-paper detail (effect sizes, samples, cutoff/look-ahead status, cost treatment) is
below; the short version: **design (post-cutoff by construction, or an explicit leakage
audit) predicts trustworthiness far better than headline effect size does, and almost none
of this literature reports returns net of realistic transaction costs.**

### 2.1 LLM sentiment/news scoring and next-day returns

- **Lopez-Lira & Tang, "Can ChatGPT Forecast Stock Price Movements?"** (arXiv:2304.07619,
  2023, →*Journal of Finance*). GPT-4-score long-short, next-day, **Sharpe 3.28** (no costs),
  regression coefficient 0.173 (t=7.13). Sample: NYSE/NASDAQ/AMEX with RavenPack news, Oct
  2021–Dec 2022 (67,586 headlines / 4,138 firms in the earlier draft). Explicitly designed to
  start just after GPT-3.5/4's stated cutoff (Sep 2021) — real post-cutoff by construction,
  but **no transaction costs anywhere**, and predictability concentrates in small/illiquid
  names, exactly where costs bite hardest. Treat the Sharpe as an upper bound.
- **Glasserman & Lin, "Assessing Look-Ahead Bias..."** (arXiv:2309.17322, 2023). Directly
  replicates the above with entity-anonymized vs. original headlines. **In-sample,
  anonymized headlines outperform originals** — a negative "distraction effect" from
  company-specific knowledge, not a pure look-ahead inflation. Out-of-sample the advantage
  weakens but persists for large caps. **This is the direct critique/extension the brief
  asked for**, and its conclusion is more nuanced than "the original result is inflated":
  identity can hurt as much as it helps.
- **Lopez-Lira, Tang & Zhu, "The Memorization Problem: Can We Trust LLMs' Economic
  Forecasts?"** (arXiv:2504.14765, 2025). The *same authors* turning the lens on their own
  method: GPT-4o direct-elicitation MAPE 0.61% pre-cutoff vs. 13-20% post-cutoff on S&P 500
  levels; directional accuracy 69-87% pre-cutoff vs. 44-49% (chance) post-cutoff. Formal
  result: **with small post-cutoff samples, genuine skill and undetected memorization are
  statistically indistinguishable.** This is the load-bearing methodological warning for
  this entire topic.
- **"Detecting Lookahead Bias in LLM Forecasts"** (arXiv:2512.23847v2, 2026): builds a
  Lookahead-Propensity (LAP) test on Llama-3.3-70B; the LLM-signal coefficient is amplified
  on high-recall firm-days in-sample (interaction t=3.64) and the interaction **vanishes**
  out-of-sample (t=1.06), while a smaller genuine signal (coefficient 0.436, t=6.47) survives
  strict post-cutoff testing. Directly parallel to this project's own `protocol_p16.py` LAP
  stanza — external confirmation the same construct is worth measuring.

### 2.2 Look-ahead bias / memorization — chronologically-consistent evaluation

- **He, Lv, Manela & Wu, "Chronologically Consistent Large Language Models"**
  (ChronoBERT/ChronoGPT, arXiv:2502.21206). Models trained ONLY on data available at each
  historical vintage. Real-time news→return long-short Sharpe **4.80 (ChronoBERT) / 4.48
  (ChronoGPT)**, statistically indistinguishable from Llama-3.1-8B (p=0.315). Masked
  president/event leakage test: 0/N correct post-cutoff. Gold-standard "by construction"
  design — no costs applied.
- **He, Lv, Manela & Wu, "Instruction Tuning Chronologically Consistent Language Models"**
  (arXiv:2510.11677). Leakage-free ChronoGPT-Instruct: Sharpe **0.95** vs. leakage-possible
  Qwen-1.5-1.8B-Chat **1.53** / Llama-3.2-3B-Instruct **1.76** on the identical task. Authors'
  own reading: **54-62% of the "apparent" predictability survives with leakage
  architecturally impossible** — a genuine, non-trivial, but smaller-than-headline effect.
  This is the single best available "how much of the effect is real" decomposition in the
  literature. **This project explicitly does not build a ChronoGPT-class control** (its own
  receipt: "not distributed as GGUF... spec section 1.6 optional") — a known, accepted gap.
- **ExAnte benchmark** (EACL 2026 Findings, aclanthology.org/2026.eacl-long.72). Quantifies a
  leakage rate across GPT/Gemini/Claude on Magnificent-7 prediction; leakage worse at shorter
  cutoff gaps, persists across all prompting strategies tested. Confirms the problem is
  vendor-general, not OpenAI-specific.

### 2.3 LLM-extracted features from filings/calls

- **Yi & Wu, "Dodging the Question"** (managerial evasiveness, 2026 working paper).
  Evasiveness → regulatory sanction within a year: +0.097 (t=5.2). 573,835 Q&A threads,
  25,894 Chinese-listed-firm briefings, open-weight Qwen3-32B extraction. **The price/
  crash-risk channel is explicitly flagged by the authors as fragile** (loses significance
  under standard weekly-residual reconstruction) — treat the regulatory-outcome result as
  the credible part, not any return claim.
- **Majzoubi, Murray & Mayew, CEO promises** (*Strategic Management Journal*, 2026). 74,017
  GPT-extracted CEO promises, 69,248 transcripts. Broken promises → higher CEO-dismissal
  likelihood. **No return or volatility coefficient in the available materials** — directly
  analogous to this project's own `promise:v1` mechanism, but this external paper answers a
  turnover question, not a returns question.
- **"Same Company, Same Signal" (DEC dataset)** (ACL 2025 Findings). A **training-free
  same-ticker-historical-volatility baseline beats every transcript-embedding and LLM
  direct-prediction model** on post-earnings volatility MSE; transcript-model predictions
  correlate 0.847 with the naive identity baseline. **This is the strongest "your LLM feature
  is secretly re-deriving a trivial baseline" warning in the whole review** — treat any
  "LLM reads earnings calls and predicts volatility" claim as suspect unless benchmarked
  against this control.
- A companion paper on FLS/tone readability and GPT-based one-year earnings forecasts found
  a **post-cutoff indicator itself raises forecast error (+0.010, t=3.10)** — a clean,
  self-administered contamination check most sentiment papers skip.

### 2.4 Narrative/emotion measures — magnitude/attention vs. direction

- **El Haddad, Achchab & Lahrichi, "A Leakage-Audited, Regime-Robust Protocol for Evaluating
  Stock-Movement Prediction from Affective Text"** (IEEE Access, forthcoming 2026). Daily
  direction AUC ≈0.51 (chance). 10-day direction never beats the majority-class baseline.
  Sentiment "lift" by regime: +2.68% (2021) / −0.01% (2022 bear) / +3.37% (2023 bull), and
  **a noise placebo collapses the 2023 lift from +3.37% to +0.58%.** Random vs. chronological
  split gap = 0.285 AUC — pure look-ahead leakage when the split is done wrong. **This is the
  strongest negative, most rigorously designed result in the entire literature review**, and
  the template this project's own emotion-to-number experiment (Part 3.2) should copy:
  leakage audit + regime stratification + noise placebo + chronological-only split.
- Non-LLM context confirming the magnitude/direction split is where narrative content lives:
  a CNN Fear & Greed replication finds Granger-causal power on returns concentrated
  pre-2014 and decaying since (explicitly caveated as unlikely to be profitable net of
  frictions); a sentiment×uncertainty replication finds the sentiment-reversal effect
  **triples under high idiosyncratic volatility** — consistent with this project's own
  measured pattern (investigator: negative on direction, positive on magnitude).

### 2.5 Scenario generation, superforecasting, calibration, tournaments

- **ForecastBench** (ICLR 2025, arXiv:2409.19839). Contamination-proof by construction
  ("questions about future events that have no known answer at the time of submission").
  Superforecasters Brier **0.096**; general public 0.121; best LLM (Claude 3.5 Sonnet)
  **0.122**, significantly worse than superforecasters (p<0.001); best LLM without
  crowd-forecast context 0.136 (worse still).
- **Schoenegger et al., "Large Language Model Prediction Capabilities..."**
  (arXiv:2310.13014). Real Metaculus tournament, Jul–Oct 2023. GPT-4 Brier **0.20**, not
  significantly different from the no-information baseline (0.25); human-crowd median
  **0.07**, significantly better than baseline. GPT-4 is at chance; humans are not.
  Human-vs-GPT-4 gap Cohen's d=0.94.
- Ensembling: the same authors' 12-LLM ensemble "rivaling" human forecasts is flagged by
  ForecastBench's own literature review as **run once, never repeated, underpowered** — treat
  "LLM ensembles match superforecasters" as provisional, unreplicated.
- **Net-net for this project's ambition of calibrated scenario probabilities**: the
  cleanest available external benchmark says current LLMs, even the best available in
  2024/2025 snapshots, are *worse-calibrated* than human superforecasters and roughly
  comparable to or worse than a well-informed public median. Part 3.3's design should expect
  to beat a trailing-volatility prior only on a narrow slice, if at all, and should be built
  to detect that honestly.

### 2.6 Fine-tuning/LoRA of small open models vs. prompting large ones

- **FinLoRA** (arXiv:2412.11378 and the expanded arXiv:2505.19819/2025). QLoRA on
  Llama-3.1-8B: up to **48% average accuracy increase** over base on financial-NLP tasks; 4-bit
  inference **5.6 GB VRAM** (fits an 8 GB card comfortably). Expanded benchmark: LoRA methods
  average **+36% accuracy** over base across 19 datasets; best config aggregate score
  **74.74 vs. base 37.05**; **fine-tuning cost $14.66-$16.54** (4×A5000, ~15 GPU-hours) vs.
  Gemini 2.0 Flash-Lite cloud fine-tuning $162, GPT-4o-mini $312, BloombergGPT-from-scratch
  $2.7M/53 days/512×A100 as the extreme anchor. LoRA-tuned 8B **beats GPT-4o and DeepSeek-V3
  base prompting on most of the 19 tasks.**
- **FinGPT v3.3** (Llama2-13B+LoRA, practitioner-grade, widely cited): beats GPT-4 zero-shot
  on FPB/FiQA-SA/TFNS sentiment benchmarks, trained on **1×RTX 3090 in 17.25 hours for
  ~$17.25.** Directly answers the "single consumer GPU, tens of dollars" feasibility
  question this project's laptop (RTX 5060, 8 GB) sits just below (a 13B model in this
  configuration needs a bigger card than what's on hand locally; the 8B-class FinLoRA numbers
  are the ones that transfer to this laptop).
- **Predibase "LoRA Land"** (non-finance, corroborating): 25/27 task LoRAs on Mistral-7B
  match/beat GPT-4 at <$8/adapter average.
- **Verdict for this project**: fine-tuning a small open model on financial-text
  *extraction/classification* tasks is real, cheap ($15-20 range), and reproducible — this is
  squarely the thing Murat named as "promising, not leaned on." The evidence is much weaker
  for fine-tuning improving *forecasting/trading* performance specifically (none of the
  LoRA papers above are trading-return studies); treat the extraction-task evidence as solid
  and the implied jump to "therefore fine-tune for alpha" as unproven.

**Cross-cutting summary**: (1) design beats headline number — only strictly post-cutoff or
leakage-audited studies should be quoted without a large discount; (2) transaction costs are
essentially absent from the entire directional-prediction literature (every Sharpe/AUC
headline above is gross); this project's own `Policy` object already refuses zero-cost
results by default, which is stricter practice than most of the papers it is being compared
against.

---

## PART 3 — FIVE EXPERIMENTS, RANKED BY EXPECTED INFORMATION PER DOLLAR AND PER DAY

All five satisfy: `PRODUCT_EXPERIMENT` licence, no LLM authority over capital, costs never
omitted, frozen versions once forward, runnable on this laptop with data already on disk.
Verdict vocabulary throughout: `ALPHA_DETECTED / CANNOT_DISTINGUISH / BETA_EXPLAINS /
FAILED_VARIANT`.

### Experiment 1 — Finish the one measurement this project's own docs call "owed": Lookahead-Propensity on PANEL-A, the panel that actually straddles the cutoff (rank 1, highest info/$ and info/day)

**Correction driving this design.** An earlier draft of this experiment proposed "read
PANEL-B" — but PANEL-B has, in fact, already been read and decided: TRIAL-R2's pre-registered
primary hypothesis on PANEL-B came back **`REJECT`**
(`night_factory_2026-09-13/R2_widened_panelB_run02.json`: net diff −0.26%/yr, t=−0.097, both
arms losing money net of costs). Re-running an already-rejected test is not the highest-value
use of the next dollar. The genuinely open, cheapest, most-repeatedly-flagged-as-owed item is
different: **`L3_lookahead`'s Lookahead-Propensity design cannot run on PANEL-B at all**
(dates are entirely post-cutoff, so the pre-cutoff arm is structurally empty —
`night_factory_2026-09-12/L3_lookahead_run01.json` confirms this directly, reporting a
partial post-cutoff sign accuracy of 0.4713 with an empty pre-cutoff arm), and **PANEL-A
(2015-2024, the panel that does straddle Qwen2.5-7B's ~2024-06 cutoff) has never had this
test run on it, because its per-cell answers were only summarized, not persisted, when it ran
on 2026-09-08.** This is named "unbuilt" and "owed" in this project's own
`docs/research_notes/2026-09-21/research_multi_role_llm_forecasting.md`.

**Hypothesis (one sentence).** On PANEL-A (135 names, 2015-2024, straddling the model's real
training cutoff), forecast accuracy is higher on pre-cutoff cells than on post-cutoff cells
by an amount that tracks the model's own date-recall propensity (the Lookahead-Propensity
interaction) — replicating, on this project's own data and model, the pattern the external
LAP paper (arXiv:2512.23847, Part 2.1) found on Llama-3.3-70B: an in-sample-only interaction
that should vanish out-of-sample.

**Separation from ordinary factor exposure.** The LAP design's own logic *is* the
separation test: regress forecast accuracy (or Brier) on a per-cell recall-propensity score
(from a canary asking the model to identify/date the cell) and on an era dummy
(pre/post-cutoff); the interaction term, not the main effect, is what would indicate
memorization rather than genuine reasoning. A significant interaction that is *absent* on
PANEL-B-style post-cutoff cells (already partially confirmed — sign accuracy 0.4713 with no
comparison arm) is the structurally clean way to bound how much of PANEL-A's earlier
+16.19%/yr conditional result could have been memorization rather than reading, addressing
the alternative TRIAL-R2 itself named and never resolved.

**Inputs (exact files).** `backend/data/optimus/r7_news_representation/panel.parquet` +
`docs_masked.parquet` (PANEL-A's 135-name, 112-block source), the R2 prompt/frozen hashes
from `docs/TRIALS/TRIAL-R2-monthly-news-digest-read.md`, `backend/services/leakage_probe.py`
and `scripts/night_l3_lookahead.py` (already built), and TRIAL-LEAK-1's era stratification
(pre-cutoff 2015-2023 / recent 2025-2026, 2024 excluded as ambiguous) as the template for
which cells count as which era.

**LLM prompt / blinding protocol.** Reuse the exact frozen TRIAL-R2 prompt (no new prompt —
this is a new *reading target*, not a new trial). Persist per-cell forecast answers this time
(the 09-08 run's defect was writing only a summary). Run the AMNESIA-style canary
(company/date identification) on every PANEL-A cell *before* the forecast call, exactly as
AMNESIA-1 and TRIAL-LEAK-1 do, to get a genuine per-cell recall-propensity score rather than
an aggregate one — this is the single most important discipline from Part 4 item 2 (don't
grade contamination in aggregate).

**Numeric features produced.** Per-cell: forecast (direction + confidence), canary
recall/identification score, era dummy, LAP interaction term.

**Outcome / horizon.** Forecast Brier/accuracy, regressed on recall propensity × era.

**Control.** The masked arm as the baseline (already the registered default per every
completed `X_anon_gap` run), and TRIAL-LEAK-1's own DiD design as the confirmatory
cross-check (it is accruing the same underlying question from a different angle and has a
canary wave already on disk).

**Sample size / MDE.** PANEL-A has 112 monthly blocks (far more than PANEL-B's 19), so this
is the best-powered blinding test this project can run without collecting new data —
answering the "is 19 blocks the ceiling" concern that limits Experiments 2-3 below.

**Cost.** **$0** (local Qwen2.5-7B; the work is re-reading a panel already read once, this
time persisting answers and adding the canary).

**Stop condition.** One run, frozen PANEL-A cells, no second prompt variant.

**Verdict mapping.** `ALPHA_DETECTED` does not apply (this is a contamination test, not an
alpha claim). `CANNOT_DISTINGUISH` if the interaction term is not significant at 112 blocks'
power (a real, informative negative, closing the "was PANEL-A memorization" question this
project has left open since 09-10). A significant, positive interaction that is absent
post-cutoff is the closest this project can get to `BETA_EXPLAINS` for the word "beta" in its
memorization sense — i.e. PANEL-A's earlier result was recall, not reading. A null
interaction with PANEL-A's accuracy still elevated pre-cutoff supports treating PANEL-A's
original +16.19%/yr as more plausibly genuine (though still not `ALPHA_DETECTED`, since
PANEL-B already rejected the live-money version of the same idea).

### Experiment 2 — Emotion-to-number tested against attention and volatility, not direction (rank 2)

**Hypothesis.** An LLM-extracted "narrative shock" score (novelty × emotional intensity ×
deviation from the name's own baseline tone), computed per document, predicts next-day
realized volatility and abnormal dollar volume for the named stock better than it predicts
the next-day sign of its SPY-relative return.

**Separation from ordinary factor exposure.** The score must show incremental predictive
lift over trailing 63-day realized volatility *alone* — the same free formula this project
already measured beating the investigator on magnitude (+10.2% vs +5.7%). Compute the score's
partial correlation with next-day realized vol/volume *after* controlling for trailing 63-day
vol; if the partial correlation collapses to ~0, the score is BETA_EXPLAINS (a relabelling of
volatility clustering, not new information).

**Inputs.** `backend/data/optimus/sources/claims.jsonl` and the wider E1 news corpus (same
documents underlying the R2/S2 jobs), `prices_2025_26/bars.parquet` for realized
vol/volume, `event_vocabulary` typed ids for stratification (acknowledging ~9% coverage —
report the typed and generic buckets separately rather than pooling them).

**LLM prompt / blinding.** Score each document 0-1 on {novelty, fear/uncertainty, surprise}
under the entity-masked text (same masking pipeline as Experiment 1 — reuse, don't rebuild).
Follow El Haddad et al. (2026)'s leakage-audited protocol exactly: chronological-only
train/val/test split (no random split — that is where the literature's own 0.285-AUC leakage
gap came from), a noise placebo (randomly-selected unrelated sentences scored the same way),
and regime-stratified reporting (bull/bear/flat months, not pooled). Named-vs-masked gap
measured on a subsample the model plausibly knows (large, famous names, pre-2024 dates
spliced in as a leakage canary batch) to confirm the masking holds before trusting the
post-cutoff 2025-26 batch.

**Numeric features.** Daily aggregated narrative-shock score per symbol; separately, its
cross-sectional z-score.

**Outcome / horizon.** Next 1/5/21-day realized volatility (CRPS/pinball loss) and dollar
volume z-score, graded head-to-head against next 1/5/21-day sign of SPY-relative return
(Brier) — the explicit magnitude-vs-direction test the brief asks for.

**Control.** Matched control stock (same sector/size decile, no qualifying document that
day), shuffled-text placebo, and the trailing-63-day-vol prior as the walk-forward baseline
that must be beaten, not just correlated with.

**Sample / MDE.** E1 already has ~340k news rows / ~59k labelled rows across 3,060 symbols,
19 month blocks — same block-count ceiling as Experiment 1, so the same ~3.5-4 pp/month MDE
applies to any monthly-aggregated version of this test; the daily-frequency vol/volume
target has many more effective observations and is the more powerful leg.

**Cost.** ~$0 local (Qwen2.5-7B) or a few dollars on DeepSeek for a stratified sample (per
`calibration_2026-09-27.json`: ~$0.10/Mtok in, ~$0.79/Mtok out cached-adjusted — a few
thousand documents is single-digit dollars).

**Stop condition.** One pre-registered read, no second prompt variant.

**Verdict mapping.** `ALPHA_DETECTED` (on the magnitude/attention leg specifically) only if
the score beats the trailing-vol prior net of the partial-correlation check. Expect, and
explicitly report as a *prediction*, that the direction leg reproduces the project's own
prior finding of negative-to-zero direction skill — a null result there is not a failure of
this experiment, it is confirmation of a standing finding. `BETA_EXPLAINS` if the partial
correlation with trailing vol collapses to zero. `FAILED_VARIANT` if it loses to the vol
prior on both magnitude and volume.

### Experiment 3 — Scenario-generated calibrated probability ranges, graded by a proper scoring rule, against the trailing-vol prior (rank 3)

**Hypothesis.** k=5 LLM-generated plausible next-21-session scenarios per name, each with a
stated probability and an analogue-priced return range (via `scenario_forecasts.py`'s
existing `pricer` contract), produce a better-calibrated forecast distribution (lower CRPS /
pinball loss, lower ECE) than a trailing-63-day-volatility-implied normal distribution — even
though S2_scenario_gym already measured this project's point-forecast confidence to be badly
overconfident (ECE 0.315).

**Separation from ordinary factor exposure.** Grade with a proper scoring rule over the full
distribution (CRPS, or pinball loss at the 10/25/50/75/90th percentiles), not sign accuracy —
a model can be useless on direction and still valuable if its *spread* across the k scenarios
tracks realized volatility (test: regress realized 21-day vol on the scenario spread; a
non-zero, out-of-sample coefficient is the separating observation from "it's just noise with
extra steps").

**Inputs.** `backend/services/scenario_forecasts.py` (the contract, already built and
tested) with its `pricer` argument populated by base rates computed *directly* from E1's own
labelled panel — bypassing the missing L2 dependency by computing `(event_type, era)` base
rates from the 59k-row E1 label set for the 27/300 cells (9%) that carry a typed event, and
an explicit `no_event` bucket for the rest (report the two separately; do not pool a 9%-typed
sample with a 91%-generic one and call it one number). Reuse the frozen 300-cell draw (seed
20260920) for comparability with the existing S2 receipt.

**LLM prompt / blinding.** Entity-masked text, same pipeline as Experiments 1-2. Consider
running this on the never-idle-measured Qwen3-30B-A3B (`--n-cpu-moe 48`, ~1.85 GB VRAM,
~19.8 tok/s per the 2026-09-10 measurement) as a second arm at $0 marginal cost, both to
finally answer the standing "measure Qwen3-30B idle" item (`HANDOFF_2026-09-28` item 7) and
to get a model-diversity check on calibration for free.

**Numeric features.** Per-name, per-date: 5 scenario probabilities + priced return ranges;
collapsed to a mean and a spread (the CRPS-relevant statistics).

**Outcome / horizon.** Realized 21-session SPY-relative return, scored by CRPS against the
implied distribution; realized 21-session volatility, scored against the spread.

**Control.** The trailing-63-day-vol-implied normal distribution (the same free formula that
already beat the investigator) as the mandatory null; a shuffled-scenario placebo (permute
which scenario/probability set attaches to which name-date) as the second control.

**Sample / MDE.** Same 300-cell / 19-block ceiling; calibration metrics (ECE, CRPS) are
generally more sample-efficient than a return t-test, so this is likely to produce a usable
answer even where Experiments 1-2's return tests are underpowered — this is part of why it
ranks above a naive reading of "it needs new code."

**Cost.** $0-few dollars (local models; optionally a NVIDIA NIM free-tier model, per
`config.py`'s already-wired `nvidia/nemotron-*` free-tier rows, as a third zero-cost arm).

**Stop condition.** One pre-registered CRPS/pinball comparison against the vol prior; no
second scenario-count (k) sweep in the same trial.

**Verdict mapping.** `ALPHA_DETECTED` only if calibration beats the vol prior **and** the
scenario spread predicts realized vol out-of-sample. Given the external literature's own
finding that even top 2024/2025 LLMs are worse-calibrated than human superforecasters
(ForecastBench), the honestly expected outcome is `CANNOT_DISTINGUISH` or `FAILED_VARIANT`;
this experiment is ranked third rather than first precisely because it is the one most
likely, on outside evidence, to close a door rather than open one — which is still real
information, cheaply bought.

### Experiment 4 — Forward-only replication of the investigator's magnitude skill, on dates that do not exist yet (rank 4; the required strictly-post-cutoff design)

**Hypothesis.** The investigator process's measured +8.97% recalibrated magnitude skill
(§64, on 2,325 rows through 2026-09-24) replicates on a fresh forward batch issued from
2026-09-29 onward, graded only after the horizon elapses, and — the sharper question —
whether it still loses to the trailing-63-day-vol control on those same forward dates
(replicating the 2026-09-28 +5.7%-vs-+10.2% finding prospectively rather than off a ledger
that already existed when the comparison was made).

**Separation from ordinary factor exposure.** Regress the investigator's forward magnitude
forecast error on trailing-63-day realized vol as a covariate; if the coefficient on the
investigator's own signal is not significant once vol is included, the investigator's skill
is a re-encoding of volatility persistence (`BETA_EXPLAINS`), matching the DEC/STPEV warning
in Part 2.3 almost exactly.

**Inputs.** `backend/data/optimus/predictions.jsonl` (append-only ledger; `LAP_score` and
`anonymization_gap` fields already exist in the schema and are unpopulated for investigator
rows — populate them for this batch), `scripts/sim_run.py`'s already-scheduled
`night_investigator_forecast` (no new code needed to generate the forward rows — only to
grade them against the vol control on the same dates, which per the adjudication note has
so far only been done retrospectively).

**LLM prompt / blinding.** None needed for the "is this post-cutoff" requirement — the
dates are, by construction, in the future relative to any model's training cutoff. Run the
existing 5-stage investigator prompts unmodified (changing them mid-trial would be a new
trial).

**Numeric features.** Prior/posterior/belief_change and forecast probability per
(observable, horizon), as already schema'd.

**Outcome / horizon.** h=1 and h=5 session magnitude/direction, exactly as the ledger already
grades.

**Control.** The trailing-63-day-vol formula, computed on the identical forward dates —
reuse the exact implementation from the 2026-09-26 adjudication, do not re-derive it.

**Sample / MDE.** This is explicitly the "time-dependent, cannot be parallelised" evidence
CLAUDE.md flags — the stop condition is calendar (first read at 21 trading sessions forward,
per the session protocol's own convention), not compute. A batch comparable in size to the
2,325-row existing sample needs on the order of 60-90 calendar days at current throughput;
report the 21-session read as an interim, likely-underpowered checkpoint, not a final
verdict.

**Cost.** ~$0 marginal (the forecast generation is already running and budgeted; the new
work is the grading comparison, which is arithmetic).

**Stop condition.** Pre-register the 21-session interim read and the ~90-day full read now;
no re-running of history to manufacture a bigger N.

**Verdict mapping.** `ALPHA_DETECTED` only if the forward-only recalibrated skill beats both
zero and the vol control at the pre-registered MDE. `CANNOT_DISTINGUISH` is the likely
21-session outcome given known power constraints — say so in advance rather than after.
`BETA_EXPLAINS` if the vol-covariate regression zeroes out the investigator's own
coefficient.

### Experiment 5 — LoRA-tune a small local model on the extraction task Murat named, and measure it against a real holdout (rank 5; lowest info/$ toward alpha, but directly answers the stated interest and is the cheapest in absolute dollars)

**Hypothesis.** A LoRA-tuned Qwen2.5-7B, fine-tuned on this project's own labelled typed-event
and evasiveness examples, matches DeepSeek-chat's zero-shot extraction accuracy on a
held-out, independently-checked sample, at zero marginal cost per call thereafter.

**Separation from ordinary factor exposure.** N/A in the alpha sense — this experiment is
about extraction accuracy, not returns, and should not be graded against DeepSeek's own
labels (circular: DeepSeek is the thing being replaced, so agreement with it only measures
mimicry). Grade against a small Murat-checked or filing-verifiable holdout instead (for typed
events: did the labelled event type actually occur, checkable against the 8-K/press record;
for evasiveness: inter-rater agreement against a manually read sample).

**Inputs.** `backend/data/optimus/thesis_cards/`, `sources/claims.jsonl` plus the broader
news corpus behind it, the 39/43-id `event_vocabulary` table (first resolve the drift noted
in 1(c) — training on a table whose own protocol text disagrees with itself is a bug to fix
before, not during, the fine-tune).

**LLM prompt design / blinding.** Not applicable in the AMNESIA sense (this is a
capability/accuracy task on contemporaneous text, not a forecast that could be contaminated
by memorized outcomes) — the relevant control is a clean train/holdout split by date so the
holdout postdates every training example.

**Numeric features.** Typed-event id + confidence; evasiveness score 0-1; both already
schema'd elsewhere in the project.

**Outcome / horizon.** N/A (accuracy task, not a return horizon).

**Control.** DeepSeek-chat zero-shot on the same holdout (the cost/accuracy comparator, not
the ground truth), and the current unlabelled baseline (nothing) as the floor.

**Sample size / MDE.** FinLoRA's own precedent used a few hundred to a few thousand labelled
examples per task; this project's own labelled pool (53 claims rows, ~65 thesis cards per
memory, plus whatever the typed-event corpus yields once coverage is measured) is likely
below that — the experiment's first deliverable is simply counting how many labelled examples
exist today, since "how many" was not found anywhere in this session's search.

**Cost.** $5-20 in GPU-hours on the laptop's own RTX 5060 (per FinGPT/FinLoRA precedent,
tens of dollars is the going rate for an 8B-class LoRA run); $0 cloud cost.

**Stop condition.** One LoRA configuration, one holdout comparison; no hyperparameter sweep
in the same trial.

**Verdict mapping.** `ALPHA_DETECTED` does not apply (not an alpha claim). Report
`FAILED_VARIANT` if Cohen's kappa against the holdout does not clear a pre-registered bar
(e.g. ≥0.6) or does not match DeepSeek zero-shot at equal-or-lower cost; otherwise this frees
a small, steady DeepSeek-cost line and directly answers Murat's own "we are not leaning on
fine-tuning" observation — ranked last because it improves cost and capability, not the
demonstrated-edge scoreboard this project's own roadmap says is still at zero.

---

## PART 4 — WHAT NOT TO DO (this project's own receipts)

1. **Do not accept an instruction as a blinding control.** AMNESIA-1 measured "you are
   standing in {date}, do not use later knowledge" as producing an *identical* recall rate
   (15.8% vs 15.8%) and a slightly *worse* Brier than no instruction at all. Masking + a
   canary is the only measured-effective control; an instruction is decoration.
2. **Do not grade contamination in aggregate.** The same trial found masking cost only 0.007
   Brier in aggregate while concealing a ~4%-of-cases near-perfect-memory subgroup
   concentrated in dramatic outcomes (bankruptcies, collapses). Any future contamination
   check needs a per-case canary; an average will hide exactly the cases that matter.
3. **Do not build a mega-schema "persona" and call it division of labour.** NIGHT-14
   measured 14 personas as 0.49 effective distinct ideas versus 0.85 for one generic agent
   at one-fifth the calls; §64 measured nine thematic personas at −27.98% held-out skill,
   optimal weight zero. The fix that worked was dividing *cognition* (gather/event/
   expectations/forecast/critic), not adding more characters.
4. **Do not ship a grading contract before its inputs exist, and do not let it sit
   unflagged.** `scenario_forecasts.py` is complete, tested, and has been `NOT_WIRED` for
   weeks waiting on two named prerequisites — which is fine, *because* the module says so in
   its own code and is classified `AWAITS` by `signal_reachability.py`. The failure mode this
   avoids is `event_intel.py` becoming "the 17th collector feeding nobody" silently; do the
   same self-declaration for any new contract shipped ahead of its inputs.
5. **Do not trust a row count as an information count.** The investigator's "17,484 graded"
   collapses to roughly 1.5 independent forecasters once 0.70-0.93 arm correlation is
   accounted for, and over a third of the ledger's forecasts are not yet due. Report
   effective independent observations (blocks/arms after correlation), not raw rows — the
   same discipline canon §58 already requires for date blocks.
6. **Do not assume a registered job dict entry means a running pipeline.** `X_anon_gap` and
   `S2_scenario_gym` are dispatchable by name in `night_factory_jobs.py`, but the factory has
   no scheduled caller as of this session, and even attended runs have repeatedly returned
   `PENDING_MODEL` because the local reader was not listening. Check whether a mechanism ran
   today, not whether it is registered to be able to run.
7. **Do not validate an LLM text feature only against its own agreement, and do not skip the
   trivial-baseline control.** The external DEC/STPEV result shows most "LLM reads earnings
   calls, predicts volatility" claims are the model relearning ticker identity / historical
   volatility level (0.847 correlation with the naive baseline). Every feature in Part 3
   above is designed with a trailing-volatility or matched-control comparator for exactly
   this reason — keep that discipline for anything built later.
8. **Do not quote a Sharpe without the cost line, and do not adopt a framework whose core
   mechanic violates canon regardless of its evidence.** Every headline number in the outside
   sentiment/scenario literature (3.28, 4.80, 4.48, 0.95-1.76) is gross of costs; this
   project's own `Policy` object already refuses zero-cost results by default, which is
   stricter than most of the literature it is being measured against — do not relax that to
   match a paper. Separately: TradingAgents' flagship Sharpe 6-8 traces to a confirmed
   look-ahead leak (issue #203), and its core mechanic (the LLM places the trade) is exactly
   what this project's three-licence canon forbids independent of the leak — not a framework
   to adopt even if the number were clean.
9. **Do not read a magnitude result as a direction result.** The investigator is +8.97% on
   magnitude and −8.7% on direction; a book that acted on the magnitude number as if it were
   a buy/sell signal would be trading on the wrong half of the same finding.
