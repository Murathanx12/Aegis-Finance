# REVIEW 2026-09-29: the fiction backtest / AMNESIA-2 (Opus arm), attacked by a sceptical investor

Reviewer: a second Opus acting as an adversarial investor. No production code changed.
Scope: `scripts/fiction_backtest.py`, `docs/TRIALS/TRIAL-AMNESIA-2-event-reaction-model-agnostic.md`,
`docs/research_notes/2026-09-28/fiction_backtest_2026-09-28.md`, `docs/WHAT_WE_ALREADY_KNOW_LLM.md`,
the receipt `backend/data/optimus/fiction_backtest/fb_20260928/receipt_analyze.json` (committed in
`c0ac5310`), and the frozen rows, sealed plan and answer files in the same run folder (on disk, not
committed). Every number below was recomputed from those rows unless it is marked as quoted.
Nothing here repeats `REVIEW_2026-09-29_NN_LAB.md` or the 2026-09-28 reviews.

## RESULTS SCOREBOARD

| item | value |
|---|---|
| RESULT IMPROVEMENT | **NONE.** No arm and no level beats a coin, 12-1 momentum or the free priors. |
| What the commit headline says | "Claude Opus 5.5 44.6% (n 120, Brier 0.2528) on fully fictional cases: no direction skill." |
| What the rows say | Opus **declined to forecast**. `p_beat_median_5d` has sd 0.019 and runs from 0.44 to 0.53. **37 of 120 are exactly 0.50** and 67 are below 0.50. Brier is 0.2528 vs 0.2500 for a coin (t +1.38); AUC is 0.461. That is an abstention with a 5 pp bearish lean, not a measured lack of skill. |
| Constant "always beats the median", same 120 rows | **54.2%**. 12-1 momentum: 52.5%. Mean of the past four earnings reactions: 47.5%. |
| Opus vs DeepSeek on the same 120 rows, paired Brier | Opus is better by 0.019 (row t -2.65). Humility beats DeepSeek's confident wrongness. Neither beats a coin. |
| Power at n 120 | Row MDE is 12.8 pp of hit rate (receipt `mde_note`); AUC MDE is about 0.15. A realistic edge (2-4 pp, AUC 0.52-0.55) cannot be seen. |
| Week-block reading | 9 weeks of **2, 4, 21, 39, 43, 5, 2, 3, 1** rows, weighted equally. Its sign is the opposite of the row mean's on 2 of the 3 Opus comparisons. |
| Fiction leak, Opus | A3 famous: 7 of 30 identified (23%, against a registered line of 10%). **By the registered rule, the fiction LEAKS for Opus.** The receipt's `leak_test` has no Opus entry, because Opus never answered the famous forecasts. |
| Where the leak comes from | 5 of the 7 famous cases with headlines were identified, against 2 of the 23 without. The text is the leak: names of third parties survive the mask. |
| Clean 5/180 | These are not false positives. All 5 are correct (FAST, MMM, ALKT, BIIB, HOOD). The one wrong guess (MNKD named as SCPH) is correctly not counted. |
| Downstream use | The night report cites "Claude Opus 44.6%" to justify a zero weight on LLM direction calls in the shadow book. |
| Cost | Opus arm $0 (file arm). DeepSeek $0.655 on the run's ledger (quoted). |
| Score | **52 / 100** |

## Findings, ranked by money and decision impact

### 1. The Opus "44.6%" measures an abstention, and it is already being used as a verdict on LLMs

**Claim.** The commit `c0ac5310` message and `docs/research_notes/2026-09-29/night_report_2026-09-29.md:117-119`
say: "DeepSeek scored 43-45% and Claude Opus 44.6% on post-cutoff cases, where a coin scores 50%".
The shadow book's rule gives LLM direction calls a weight of zero on that basis.

**Evidence.**
- Distribution. Of the 120 clean A3 forecasts in `rows/file_opus.jsonl`, 37 are exactly 0.50, 21 are 0.48 and 19 are 0.49; the range is 0.44 to 0.53. The receipt agrees: `mean_p` 0.488, `sd_p` 0.019 (cell `file:opus|clean|A3_SYNTHETIC`).
- Reliability table. It has two bins, and both sit at the 54.2% base rate: p in 0.4-0.5 → 55.2% beat the median; p in 0.5-0.6 → 52.8% beat it.
- Scoring. `fiction_backtest.py:1524-1525` scores a p of exactly 0.50 as half a hit, so 18.5 of the 53.5 "hits" come from ties. On the 83 rows where Opus took a side, the hit rate is 42.2%.
- Mechanism. Each of those 83 calls is the sign of a tilt of at most 6 pp away from 0.5. With a 54.2% base rate, a model that leans bearish on nearly every row scores below 50% mechanically. **The below-coin number comes from a calibration offset, not from discrimination.** AUC is 0.461, and at n 120 its 95% band is about ±0.10.

**Consequence.** A single abstaining run of 120 rows now justifies a standing zero weight on "LLM
direction" in a book. Worded as "no direction skill", it will be read as a closed question. CLAUDE.md's
"stop over-closing ideas" rule warns against exactly that. The same number will also feed tables like
`WHAT_WE_ALREADY_KNOW_LLM.md` in later sessions.

**Fix.**
- Report Opus as `CANNOT_DISTINGUISH (model abstained; sd_p 0.019)`. The registered rule does return `FAILED_VARIANT`, because the Wilson high of 0.539 is below 0.55 (`TRIAL-AMNESIA-2...md:90`), so print the formal verdict and the abstention together.
- Add `sd_p` and the share of exact 0.50s to the verdict line.
- The shadow book's zero weight can stay, since there is no evidence FOR a weight. Its stated reason should be "no evidence yet", not "measured below a coin".

**Decides:** the builder for the wording; the owner for whether the shadow rule's rationale changes.

### 2. The Opus arm ran at the level that removes most of what a strong model could contribute

**Claim.** The note's section "The owner's hypothesis" says the file arm tests "the owner's hypothesis
on the exact same 569 post-cutoff events."

**Evidence.**
- What Opus answered: the famous canaries (batches 001-006), 180 clean A3 canaries (042-050) and 120 clean A3 forecasts (100-105).
- What it did not answer: any A0 or A2 clean forecast, and **any famous forecast (batches 007-012 have 0 of 30 answer files)**.
- On clean dates (2026-07-01 onward, after the stated June 2026 cutoff) there is no outcome to remember. The only thing the fiction removes there is **legitimate company knowledge**: the business model, seasonality, how the stock usually trades its prints, the company's guidance habit. That knowledge is the only plausible source of an LLM edge on a call made before the announcement.
- The A3 case also tells the model that "no real-world facts about them exist" (`SIM_HEADER`, `fiction_backtest.py:149`), and the answering instructions add "Do not try to identify the real company" (`ANSWERING_INSTRUCTIONS.md`, rule 4).

**Consequence.** On clean dates the test asks the strong model to forecast with its strongest input
switched off, and its answer (about 0.49, "I don't know") is the rational one. The owner's hypothesis
concerns fictionalised PAST situations, i.e. a backtest. Before that, there is a prior question: does
the model show skill when nothing is hidden and nothing can be remembered? That question, the A0 clean
run, was never asked of Opus.

**Fix.** Run Opus at A0 on the clean part: the same 569 events, named. First verify the cutoff with a
probe of the kind used for DeepSeek; `arm_cutoffs["file:opus"]` says "unverified by probe"
(`fiction_backtest.py:138`).

**Decides:** builder.

### 3. The week-block estimator weights a 1-row week like a 43-row week, and it reverses signs

**Evidence.** `_block` (`fiction_backtest.py:1469-1471`) averages each week, then treats the week means
as equal observations. The Opus rows fall in weeks of 2, 4, 21, 39, 43, 5, 2, 3 and 1 rows, so 103 of
the 120 rows sit in three weeks. On the receipt, the row-level reading and the block reading disagree:

| comparison | row-level reading | block mean |
|---|---|---|
| `dir5`: hit rate minus 0.5 | **-0.054** (hit 0.446) | **+0.022** |
| `model_minus_momentum` | **-0.079** (0.446 - 0.525) | **+0.110** |
| `range5.diff_vs_vol_prior` (interval score, model minus prior; negative = model better) | **-1.40** (48.99 vs 50.39) | **+2.08** |

The registered power fields assume about 60 cases a week with rho 0.05 (`TRIAL...md:106-120`). The
estimator does not implement that dependence model; it implements "each week is one observation".

**Consequence.** The DIR verdict needs a week t of at least 2, from an estimator whose sign is driven by
weeks of 1 to 5 rows. For DeepSeek at n 569 the weeks are fuller and the damage is smaller. But the
"MDE 16-22 pp" quoted in the note is this estimator's MDE, not the design's.

**Fix.**
- Use a size-weighted block mean, or a cluster-robust SE by week (or by decision date) on the row-level hit.
- Drop weeks with fewer than 10 rows from the block reading, and print how many were dropped.
- Print the row mean and the block mean side by side, and flag any sign disagreement.

**Decides:** builder.

### 4. The fiction leaks for a strong model through the text, and the leak scan cannot see it

**Evidence.**
- Opus identified 7 of 30 A3 famous canaries: MRNA, AMZN, SMCI, APP, MRVL, UNH, COIN.
- Headlines drive it. Seven famous cases have headlines (SMCI, APP, CRWD, MRVL, UNH, NOW, COIN), and **5 of those 7 were identified**. Of the 23 without headlines, 2 were.
- Example: the clean HOOD A3 case (`04a31bed4238`). Its "fictional" headlines still name *SpaceX, Tesla, Cathie Wood, Ark Invest, X Money, Venmo, Apple Pay, Hyperliquid, Matthew Sigel* and *Spotify*, and the company's own chain survives, renamed "Fennick Holdings Chain".
- `scan_case` (`fiction_backtest.py:696-706`) checks only the target's own ticker, name and aliases.
- `fmt_date` (`:509-517`) keeps the real day and month. The four past report dates (for FAST: 11 Jul, 13 Oct, 16 Jan, 10 Apr) are a reporting-calendar fingerprint.
- The ratios (margins, growth, leverage) are kept by design. The two hits without headlines (MRNA, AMZN) probably came from the dates and ratios.

**Consequence.**
- The note's WHAT WORKS line, "The fiction level holds and is now testable on any model" (`fiction_backtest_2026-09-28.md:199-201`), is false for the strong model it was built for.
- By the registered rule (`TRIAL...md:94-95`), every BACKTEST reading for Opus is void.
- The receipt does not print that verdict. The Opus famous forecasts were never answered, so `leak_test` has only `deepseek` and `nvidia`, and the rule's second clause was never evaluated.

**Fix.** Before any pre-cutoff Opus backtest:
- (a) mask every proper noun in the headlines, not only the target's, or drop headlines at A3;
- (b) jitter the day of the month and remove the regularity of the reporting calendar;
- (c) answer batches 007-012, so the registered leak verdict is computed and printed.

A fiction that removes every fingerprint also removes most of the information. After the cutoff,
identity is not a leak; before it, a strong model will find the identity.

**Decides:** the builder for (a)-(c); the owner for whether a pre-cutoff LLM backtest is worth pursuing
at all (see the highest-EV experiment).

### 5. Identification is measured soundly for this sample but fragile in general; "5 of 180" is a true-positive rate

**Evidence.**
- How it is graded. The code grades identification automatically (`fiction_backtest.py:1645-1646`). A case counts as identified if the returned ticker equals the symbol, or if any alias of 4 or more characters appears as a substring of the returned company name. Stated confidence is ignored.
- What I checked. I compared every Opus canary answer other than UNKNOWN against the sealed plan. All 5 clean hits are correct, and the one wrong clean guess (MNKD → scPharmaceuticals) is correctly not counted.
- Where the rule is fragile. The substring rule would count "Breakfast Co" as FAST, or "Super League" as SMCI (alias `Super`). No such false positive occurs in these rows.
- Selection. The 30 famous cases follow a rule declared before the run, "30 largest mega-liquid earnings moves" (`TRIAL...md:71-72`), so they are not chosen post hoc.
- Coverage. The canary runs in a different agent from the forecast, so it is a lower bound on what the forecasting agent silently recognised. Only 41 of the 120 Opus forecast situations have an Opus canary at all.

**Consequence.** "5/180 clean" is not the grader's false-positive rate. It shows that a strong model can
name about 3% of anonymised post-cutoff companies from their numbers alone. That matters for outcome
memory only before the cutoff. No accuracy figure excludes the identified cases. On clean dates that is
harmless; on a famous or backtest reading it would contaminate the result.

**Fix.**
- Match on word boundaries: require an exact ticker match or an alias of at least 6 characters.
- Print each hit for manual confirmation (fewer than 30 per run).
- Give every forecast situation a canary at the same level.
- Report every accuracy number with and without the identified situations.

**Decides:** builder.

### 6. The file arm confines the harness, not the answering model

**Evidence.**
- `test_file_arm_is_confined_to_its_answers_folder` (`backend/tests/test_fiction_backtest.py:219-232`) proves only that the harness READER cannot walk out of `answers/`. The note cites it as "file-arm confinement ... pinned by 20 tests" (`:199-201`).
- The answering agents were full coding sub-agents with file, shell and web tools. Their confinement is rule 3 of `ANSWERING_INSTRUCTIONS.md`, which is an instruction.
- `sealed/plan_clean.json` (symbols and dates) and the local price bars sit one directory away. No tool-call log of the answering agents is kept.
- Their context was not clean either: 4 of the 5 clean identifications give the year as 2026, while the case says 21xx. That year came from the agent's environment, not from the case.

**Consequence.** Tonight this does no harm, because a model that cheated would not score 44.6%. It becomes
harmful the day an Opus arm scores 58%: nothing on disk could then rule out a lookup.

**Fix.**
- Answer through a tool-less call: one request per case, with only the case text and no tools. Or use a sub-agent type whose tools are limited to reading its batch's cases and writing answers.
- Store each agent's tool-call log beside the answers.
- Run the answering agents from a directory that does not contain `sealed/`.

**Decides:** builder.

### 7. The task cannot show a realistic LLM edge, and the packet leaves out the inputs that would carry one

**Evidence.**
- The target is the sign of a 5-session return relative to the median stock, decided before the report. The decision close is the session before the 8-K.
- The price reaction is not already in the decision close: an outsized move on the decision day occurs in 4.6% of cases, which is the normal rate.
- The surprise is unknown by construction.
- The packet has no structured consensus EPS or revenue (it appears only when a headline happens to carry it). It also has no estimate-revision trend, no options implied move, no short interest and no prior-quarter surprise. The repo already holds 392k dated analyst revisions (MEMORY S55) and implied moves (the contest desk).
- What predicts direction before an announcement, according to the literature, is small and worth a few pp: the announcement premium (visible here as the 52-54% base rate), revision drift before the announcement, and drift after the prior quarter's surprise.
- The design's floor is an MDE of 5.9 pp at n 569 and 12.8 pp at n 120.

**Consequence.** An edge of 2-3 pp, the most a pre-announcement call plausibly has, cannot be seen at n 569,
and certainly not at n 120. A null here says nothing about any edge that could matter.

**Fix.** See the highest-EV experiment.

**Decides:** the owner, since it spends a season.

### 8. Smaller defects

- **Two tie conventions.** The famous hit in the leak test (`fiction_backtest.py:1737`) counts p = 0.50 as a down call, while `grade_cell` counts it as half a hit. That is why DeepSeek's famous hits read 0.60/0.60/0.60 in `leak_test` but 58/60/62% in the note. Use one convention.
- **Contradictory canary framing.** The canary header says "a real US-listed company ... identity and date removed", and the case inside says "fictional; no real-world facts exist" (`fiction_backtest.py:192-193` and `:149`). This is inherited from AMNESIA-1. It may suppress identification in a model that follows instructions, which would make the canary an even weaker lower bound.
- **Stale docs.** The 2026-09-28 note and `docs/WHAT_WE_ALREADY_KNOW_LLM.md:15` still say "file arm (Opus) cases written, unanswered" and "A3 fiction identified 0/599". The Opus rows (A3 famous 7/30, A2 famous 12/30, named recall 26/30) appear only in the receipt and the commit message.
- **Noisy earnings prior.** The past-reaction rows sometimes include two item-2.02 filings 11 days apart (HOOD: 29 Jan and 9 Feb). Item 2.02 is not always a quarterly print, so the "past four earnings reactions" prior carries some noise.

## Score: 52 / 100

The instrument is careful where it counts: packets are strictly point-in-time, levels are paired, the
parse is strict, no outcome is stored, and the DeepSeek numbers are reported honestly. Against that, the
Opus headline reads a 120-row abstention as a skill verdict, the block statistic reverses signs, the
leak rule was never evaluated for the model it was built to test, and the result is already steering a
book's rule.

## WHAT WORKS

- Point-in-time discipline: `assert_pit`, outcomes computed only at analysis time, and a sealed plan whose sha256 is stamped before the first call.
- Levels are paired case for case, and a leak refusal drops the case at every level, so comparisons stay paired.
- A model-agnostic arm interface, and a file arm that makes a strong-model run cost $0.
- The DeepSeek result at n 569 is an honest FAILED_VARIANT, and its inversion is flagged as post hoc.
- The canary-per-case design, graded by code, caught that the fiction leaks for Opus. The leak rule worked as a detector, even though the receipt never computed its verdict.

## WHAT DOES NOT

- Opus "44.6%, no direction skill": an abstention (sd_p 0.019, 31% exact 0.50s) graded by a hit rate, at n 120, at the level that switches off the model's knowledge.
- The week-block t: it weights 1-row weeks like full weeks, and its sign is reversed on 2 of the 3 Opus comparisons.
- The fiction, for a strong model: third-party names and reporting-calendar dates survive, and 5 of the 7 famous headline cases were identified.
- Confinement of the answering model rests on an instruction, and no tool log is kept.
- The receipt, the note and the canon table disagree about what Opus did.

## HIGHEST-EV EXPERIMENT

**A prospective, named, full-information earnings-season test.** The Q3 2026 reporting season runs
through October and November, inside the contest window. It needs no fiction, because nothing in it can
be remembered.

1. **Pre-register before the first October print.** About 1,500-2,000 US events with 8-K item 2.02: enough for a hit-rate MDE of about 3 pp and an AUC MDE against the baseline of about 0.03. The decision is at the close before the scheduled report date.
2. **The packet.** The real name, plus what the fiction removed: structured consensus EPS and revenue with their 30- and 90-day revision trend (from the analyst revision table), the options implied move, the prior quarter's surprise and reaction, short interest, and the last call's guidance where available.
3. **The arms and the grading.**
   - Arms: Opus with no tools and one request per case; DeepSeek; and a **numeric baseline**, a logistic on the same fields fitted on 2018-2025 events.
   - The LLM's claim is **incremental**: its logit must add to the baseline's in a paired regression, clustered by date.
   - Grade discrimination (AUC or rank IC) and Brier skill against the base rate, not the raw hit rate.
   - Recalibrate each arm's intercept out of sample, so a bearish tilt cannot decide the result.
4. **A second target that is more plausibly learnable:** the size of the move against the implied move. TRIAL-CONTEST-MAG-1 needs the same quantity, so one run also serves the contest desk.

Cost: DeepSeek about $1-2; Opus through a tool-less path at session cost. Value: it is the only design
here that can tell "LLMs add nothing on earnings" apart from "we never asked with the information on the
table". It answers the owner's question for the model he cares about, on events no model has seen.
