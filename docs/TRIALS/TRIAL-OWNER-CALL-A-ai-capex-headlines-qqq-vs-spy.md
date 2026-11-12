# TRIAL-OWNER-CALL-A: after a day of AI-capex-stress headlines, does QQQ lag SPY over the next 5 sessions?

## RESULTS SCOREBOARD

**Nothing has been graded forward.** The first forward day is 2026-11-12 (UTC). The rows below are a
descriptive paper log. No account holds a position because of it.

| item | value |
|---|---|
| forward events graded | 0 |
| seen before the freeze (listed, never counted) | 3 TRIGGER days (1 absorbed by an open event), 41 QUIET, 17 UNKNOWN |
| twin (unconditional 5-session blocks, 2016-01-04 → 2026-11-10) | claim true on **0.4367** of 545 blocks; mean +0.09%, sd 1.17% |
| independent selector count | unchanged. This is a log, not a book |
| farm candidates tested / promoted | 0 / 0 |
| external execution drag | none. No order is sent |
| LLM spend / cost per gradeable output | $0.00 / $0.00. No LLM is used anywhere |

**`CLAIMS PROMOTED: none`**

- **Contract:** `docs/TRIALS/OWNER-CALLS-CONTRACT-v1.json`, theme `ai_capex`, version `owner-calls/1`,
  **sha256 `ba99aa2eede5aa45e8cf26dded0cf8a724f7532fb66a488006ff58ddd32fd9e5`**.
- **Code:** `backend/services/owner_calls.py`; CLI `python -m scripts.owner_calls`.
- **Inception:** 2026-11-12 (the first UTC day whose headlines count). The commit that froze the
  contract was pushed before that day began.
- **First possible event:** trigger day 2026-11-12 → entry at the 2026-11-13 close → exit at the
  2026-11-20 close.
- **Formal reads:** at 12, 24 and 36 counted forward events. The final read is at 36 events or on
  2029-11-12, whichever comes first.
- **Owner signature: PENDING.** The trial is not in the trial registry until the owner signs
  (`python -m scripts.owner_calls register`, attended).

Licence: `PRODUCT_EXPERIMENT`. It is a paper log: no broker, no orders and no money. It licenses no
claim. Until this trial passes, the rule's output is labelled descriptive context wherever it is shown.

## Hypothesis

After a UTC day whose headlines meet the frozen AI-capex-stress rule, QQQ returns less than SPY over the 5 sessions that start at the next session's close, more often and by more than on ordinary 5-session blocks.

**Honest prior.** **Small or zero.** The two triggers seen before the freeze were both followed by QQQ − SPY of −0.33pp. An effect of that size needs about 100 events (about 8 years at the seen rate) to resolve. The expected verdict at every read is `CANNOT_DISTINGUISH`.

## Where this comes from

- `docs/ROADMAP.md` CH-01: "Meta-capex/AI-spend stress → AI-peer drawdown". The owner's call is that heavy AI capital spending by the largest buyers is a stress for AI-linked equities.
- `docs/ASKED_VS_DELIVERED_2026-11-09.md`: the owner's market calls are "measurements to run, not claims" and need "a typed, pre-registered path (thesis → falsifier → grading date)".
- **Instrument.** SMH and other semiconductor ETFs are absent from the bars panel. QQQ − SPY is the pair that has a 2016+ history on disk. It is a weaker instrument than an AI-peer basket: QQQ and SPY share most of their largest holdings.
- **The NVIDIA date was verified first**, as CH-01 asks. NVIDIA's investor-relations release of 2026-10-28 puts the call on Tuesday 2026-11-17 at 2 p.m. PT, with results at about 1:20 p.m. PT, after the XNYS close.

## The design (frozen in the contract)

**Rule.** One UTC day of headlines is read from seven corpus sources: `google_news_rss_en_us`, `google_news_rss_en_gb`, `wsj_markets`, `wsj_business`, `wsj_tech`, `wsj_world`, `mw_topstories`.
Titles are lower-cased and counted once per day across the sources. A title is a hit when the pattern below matches it
(case-insensitive):

```
\b(capex|capital (spending|expenditures?)|ai (spending|bubble|spend|debt|bonds?)|data[- ]cent(er|re)s? (spending|debt|bonds?|costs?)|spending (spree|forecast|binge)|ai[- ]trade)\b
```

**State of a day.**
- `UNKNOWN` when the day has fewer than 100 deduplicated titles. A reader outage is not a quiet news
  day.
- `TRIGGER` when hits ≥ 3 **and** hits / titles ≥ 1.0%.
- `QUIET` otherwise.

**Event.** A TRIGGER on day D opens one event. Entry is the close of the first XNYS session on or after
D+1. Exit is the close 5 sessions later. Events never overlap: a TRIGGER whose entry falls inside an
open event is counted as absorbed and opens nothing.

**Outcome.** The simple return of QQQ minus SPY from the entry close to the exit close. The claim is true when the outcome is
below 0.

**Twin.** The same outcome on every non-overlapping 5-session block from 2016-01-04 that ended before
inception. Blocks are counted, never days. The claim was true on 0.4367 of 545 blocks. By year:
2016 0.41 · 2017 0.36 · 2018 0.44 · 2019 0.41 · 2020 0.36 · 2021 0.41 · 2022 0.60 · 2023 0.38 · 2024 0.52 · 2025 0.48 · 2026 0.43.

**Pinning.** Corpus day files can be rewritten. `python -m scripts.owner_calls record` pins every ended
forward day once in a hash-chained ledger (`owner_calls/states.jsonl`): the state of each theme and the
SHA-256 of each source file. The pinned state stands if a file changes later, and the change is
reported as drift. **A forward event counts at a formal read only when its trigger day was pinned on or
before its entry date (UTC).** An unpinned or late-pinned event is listed as NOT COUNTED.

## What was seen before the freeze

The thresholds were chosen on 2026-11-11 **after** reading the corpus from 2026-09-11 to 2026-11-10, with
prices for that period on disk. Every day before inception is labelled `SEEN_BEFORE_FREEZE`. Those days are
never forward evidence and never enter a read. Over those 61 days: 3 TRIGGER days (1 absorbed by an open event), 41 QUIET, 17 UNKNOWN.

| trigger day | hits / titles | entry → exit | outcome | claim true |
|---|---|---|---|---|
| 2026-10-15 | 3 / 163 | 2026-10-16 → 2026-10-23 | QQQ − SPY −0.33% | true |
| 2026-10-31 | 3 / 247 | 2026-11-02 → 2026-11-09 | QQQ − SPY −0.33% | true |

A forward event may share sessions with a pending seen event. The two chains never mix: a seen trigger
does not absorb a forward one.

## Statistics and power

One observation per **event**. Events never overlap, so no two observations share a session.

- **Primary metric:** the mean of `−(QQQ − SPY)` over counted, graded forward events (positive supports
  the hypothesis). t = mean / (sd / √n).
- **Dispersion:** 1.175pp, the sd of the pair's 5-session outcome over the 545 twin blocks. It is
  measured on unconditional blocks, not in the trigger state, where it may be larger.
- **Event rate:** 2 non-overlapping events in the 44 known days seen before the freeze is 12 to 17 a year; 12 is declared.

| counted events | smallest effect the read can resolve (2.8 SE) |
|---|---|
| 12 | 0.95pp |
| 24 | 0.67pp |
| 36 | 0.55pp |

So in three years this design resolves only an effect of about 0.55pp or more. That number is the
floor of the instrument. It is **not** the effect anyone expects.

### Power declaration

- event_frequency_per_year: 12
- declared_effect_size: 0.55pp
- outcome_dispersion: 1.175pp
- outcome_horizon_days: 5
- dependence_unit: one non-overlapping 5-session event window; no two events share a session
- cluster_size: 1
- corpus_years: 3

### Slice declaration

- slice_purpose: EXPLORE
- slice_period: 2026-11-12 .. 2029-11-12
- selection_period: 2026-09-11 .. 2026-11-10
- hypothesis_source: the owner's AI-capex call as recorded in docs/ROADMAP.md CH-01, and the news corpus headlines read to set the thresholds
- hypothesis_source_period: 2026-09-11 .. 2026-11-10

EXPLORE, not CONFIRM: the patterns and thresholds were fitted by eye on two months of headlines, and one
forward record cannot confirm a rule that was shaped that way.

## Decision rule

Read only at 12, 24 and 36 counted, graded forward events (final read as above). Each read prints the
event list, the outcomes by year, and the leave-one-event-out range.

**Forward block reference.** Non-overlapping 5-session blocks of the same outcome, starting at the first
session on or after 2026-11-12 and stepping 5 sessions, through the read date. It is what the forward period
did with no rule at all.

`SUPPORTED_SO_FAR` needs **all** of:
- mean > 0 and t ≥ 2;
- the worst leave-one-event-out mean is still > 0;
- the hit rate is above the frozen twin (0.4367);
- the event mean is above the forward block reference's mean (same sign convention).

`FAILED_VARIANT`: from 6 events on, at any grade, mean ≤ 0 and t ≤ −1. The rule is then
`RETIRED_FROM_CURRENT_SEARCH`. On a true zero this fires about 18% of the time per look at 6 events, and
about 2% of the time if the true effect were 0.55pp. It is a reversal detector and cannot confirm
anything.

`CANNOT_DISTINGUISH`: everything else.

Three looks at t ≥ 2 give roughly a 10% chance of one false `SUPPORTED_SO_FAR` on a true zero. The other
three conditions lower that, by an amount that is not computed here.

**Crash override.** If SPY closes 20% or more below its prior peak during the trial, no read is taken
until 6 months after the trough.

**Promotion.** None from this contract. A `SUPPORTED_SO_FAR` read makes the rule a candidate input for the
separate news-risk-overlay paper book (audit item 5), with owner approval and its own frozen contract.
It never becomes a `RESEARCH_CLAIM` from this trial.

## Frozen parameters

The patterns, the two thresholds, the seven sources, the 100-title floor, the dedup rule, the entry and
exit convention, the pair, the horizon, the claim, the twin and the inception date. Any change changes the
contract sha256: this trial is then recorded as abandoned and a successor is registered with a new
inception.

## Contamination clauses

- A day with fewer than 100 titles is UNKNOWN and opens nothing. 17 of the 61 days seen before the freeze
  were UNKNOWN, so a missed trigger is likely and is not repaired afterwards.
- If a source is retired or its feed changes shape, the rule keeps reading what is there. A sustained
  fall below the title floor ends the trial as `CANNOT_GRADE`; it is not patched by adding a source.
- An event whose entry or exit close is missing from the bars panel is `CANNOT_GRADE` and is excluded,
  with the count printed.
- A pinned state stands when a day file drifts. Drift days are printed at every read.
- The read script does not exist yet. It will compute the read from `theme_events` rows that are GRADED
  and `counts_at_read`, and it may not change anything in this document.

## Worst case in dollars (protocol item 4)

**$0.** There is no book, no position and no order. n names × notional% × stop% = 0, and Σ|notional| /
equity = 0. If a later contract ever sizes a position from this rule, that contract owes its own worst
case.

## What this rule may NOT do

- Place, size or cancel any order, or feed any book, ranking, alert or message.
- Be described as a signal, or as forecasting anything, anywhere it is shown. It is descriptive context.
- Count a day before 2026-11-12, an unpinned or late-pinned event, or an event it cannot grade.
- Be read early or more often than the reads named above.
- Have its metric, thresholds, window or twin changed after data accrues.
- Carry an owner answer that the owner did not write themselves.

## Scheduling

**None yet.** `python -m scripts.owner_calls record` has to run once a day after 00:00 UTC so that each
day is pinned before the next session ends. Until a later release gives it a scheduled caller it is run
by hand, and every gap shows up as NOT COUNTED events, not as silence. `python -m scripts.owner_calls
status` prints the states, the events and their pin times, and writes nothing.

## The dated question (A-NVDA-CLUSTER)

> QQQ returns less than SPY from the 2026-11-17 close (NVIDIA reports after it) over the next 5 sessions.

- **Window:** entry at the 2026-11-17 close, exit at the 2026-11-24 close (5 sessions).
- **Twin:** the claim was true on **0.4367** of 545 non-overlapping 5-session blocks since 2016
  (mean +0.09%, sd 1.17%). By year: 2016 0.41 · 2017 0.36 · 2018 0.44 · 2019 0.41 · 2020 0.36 · 2021 0.41 · 2022 0.60 · 2023 0.38 · 2024 0.52 · 2025 0.48 · 2026 0.43.
- **Owner's probability that the claim is true:** not given yet. It is accepted until the 2026-11-17 close (21:00 UTC)
  and never revised: `python -m scripts.owner_calls log --who owner --question A-NVDA-CLUSTER --p <x>`.
- The frozen rule answers too, from the UTC days 2026-11-12 to 2026-11-16: YES when any of them is TRIGGER, UNKNOWN when one is UNKNOWN or has not ended, otherwise ABSTAIN. A YES is logged as a direction-only call with no probability (`python -m scripts.owner_calls rule --question A-NVDA-CLUSTER --log`). On 2026-11-11 the answer is UNKNOWN, because the window has not begun.
- **Grading:** Brier score of the owner's probability against the twin's, on the bars on disk
  (`python -m scripts.owner_calls grade`). One question is one observation. It starts a calibration
  record; it shows no skill either way.

## Signature

- Design frozen: 2026-11-11 (the commit that adds this file).
- **Owner signature: PENDING**
