# TRIAL-OWNER-CALL-C: after a day of election-and-policy headlines, does SPY move 2% or more over the next 5 sessions?

## RESULTS SCOREBOARD

**Nothing has been graded forward.** The first forward day is 2026-11-12 (UTC). The rows below are a
descriptive paper log. No account holds a position because of it.

| item | value |
|---|---|
| forward events graded | 0 |
| seen before the freeze (listed, never counted) | 5 TRIGGER days (2 absorbed by an open event), 39 QUIET, 17 UNKNOWN |
| twin (unconditional 5-session blocks, 2016-01-04 → 2026-11-10) | claim true on **0.2716** of 545 blocks; mean +0.30%, sd 2.28% |
| independent selector count | unchanged. This is a log, not a book |
| farm candidates tested / promoted | 0 / 0 |
| external execution drag | none. No order is sent |
| LLM spend / cost per gradeable output | $0.00 / $0.00. No LLM is used anywhere |

**`CLAIMS PROMOTED: none`**

- **Contract:** `docs/TRIALS/OWNER-CALLS-CONTRACT-v1.json`, theme `election_policy`, version `owner-calls/1`,
  **sha256 `8d4428d0fce6e6f99f87a23629736823a9f97e5541f6d255fa857efd5a9543ce`**.
- **Code:** `backend/services/owner_calls.py`; CLI `python -m scripts.owner_calls`.
- **Inception:** 2026-11-12 (the first UTC day whose headlines count). The commit that froze the
  contract was pushed before that day began.
- **First possible event:** trigger day 2026-11-12 → entry at the 2026-11-13 close → exit at the
  2026-11-20 close.
- **Formal reads:** at 12 and 24 counted forward events. The final read is at 24 events or on
  2029-11-12, whichever comes first.
- **Owner signature: PENDING.** The trial is not in the trial registry until the owner signs
  (`python -m scripts.owner_calls register`, attended).

Licence: `PRODUCT_EXPERIMENT`. It is a paper log: no broker, no orders and no money. It licenses no
claim. Until this trial passes, the rule's output is labelled descriptive context wherever it is shown.

## Hypothesis

After a UTC day whose headlines meet the frozen election-and-policy rule, SPY's 5-session return from the next session's close is at least 2% in absolute value more often than on ordinary 5-session blocks.

**Honest prior.** **Unknown, and the twin is regime-dependent.** The share of 5-session blocks with a 2% move was 0.02 in 2017 and 0.62 in 2022. A high event rate in a volatile year says nothing about headlines, which is why the rule must also beat the forward period's own block rate. The midterm election (2026-11-03) has already passed, so the trigger rate will probably fall. The expected verdict is `CANNOT_DISTINGUISH`.

## Where this comes from

- `docs/ROADMAP.md` CH-01: "the midterm path". The owner's exact wording of the midterm call is not on record, so this trial tests the plain version: heavy election-and-policy news days are followed by larger market moves, in either direction.
- `docs/ASKED_VS_DELIVERED_2026-11-09.md`: the owner's market calls are "measurements to run, not claims".
- **Instrument.** SPY alone, absolute 5-session return against a 2% line. The claim is about the size of the move, not its direction.

## The design (frozen in the contract)

**Rule.** One UTC day of headlines is read from seven corpus sources: `google_news_rss_en_us`, `google_news_rss_en_gb`, `wsj_markets`, `wsj_business`, `wsj_tech`, `wsj_world`, `mw_topstories`.
Titles are lower-cased and counted once per day across the sources. A title is a hit when the pattern below matches it
(case-insensitive):

```
\b(midterms?|mid-term|election|congress|shutdown|house majority|senate majority|impeach\w*)\b
```

**State of a day.**
- `UNKNOWN` when the day has fewer than 100 deduplicated titles. A reader outage is not a quiet news
  day.
- `TRIGGER` when hits ≥ 9 **and** hits / titles ≥ 5.3%.
- `QUIET` otherwise.

**Event.** A TRIGGER on day D opens one event. Entry is the close of the first XNYS session on or after
D+1. Exit is the close 5 sessions later. Events never overlap: a TRIGGER whose entry falls inside an
open event is counted as absorbed and opens nothing.

**Outcome.** SPY's simple return from the entry close to the exit close. The claim is true when its
absolute value is at least 2%.

**Twin.** The same outcome on every non-overlapping 5-session block from 2016-01-04 that ended before
inception. Blocks are counted, never days. The claim was true on 0.2716 of 545 blocks. By year:
2016 0.16 · 2017 0.02 · 2018 0.40 · 2019 0.14 · 2020 0.40 · 2021 0.18 · 2022 0.62 · 2023 0.32 · 2024 0.26 · 2025 0.28 · 2026 0.21.

**Pinning.** Corpus day files can be rewritten. `python -m scripts.owner_calls record` pins every ended
forward day once in a hash-chained ledger (`owner_calls/states.jsonl`): the state of each theme and the
SHA-256 of each source file. The pinned state stands if a file changes later, and the change is
reported as drift. **A forward event counts at a formal read only when its trigger day was pinned on or
before its entry date (UTC).** An unpinned or late-pinned event is listed as NOT COUNTED.

## What was seen before the freeze

The thresholds were chosen on 2026-11-11 **after** reading the corpus from 2026-09-11 to 2026-11-10, with
prices for that period on disk. Every day before inception is labelled `SEEN_BEFORE_FREEZE`. Those days are
never forward evidence and never enter a read. Over those 61 days: 5 TRIGGER days (2 absorbed by an open event), 39 QUIET, 17 UNKNOWN.

| trigger day | hits / titles | entry → exit | outcome | claim true |
|---|---|---|---|---|
| 2026-09-14 | 9 / 153 | 2026-09-15 → 2026-09-22 | SPY +2.37% | true |
| 2026-10-26 | 9 / 152 | 2026-10-27 → 2026-11-03 | SPY −1.99% | false |
| 2026-11-03 | 12 / 162 | 2026-11-04 → 2026-11-11 | PENDING | — |

A forward event may share sessions with a pending seen event. The two chains never mix: a seen trigger
does not absorb a forward one.

## Statistics and power

One observation per **event**. Events never overlap, so no two observations share a session.

- **Primary metric:** h, the share of counted, graded forward events where the claim is true.
  t = (h − p) / √(p(1 − p) / n), computed against two references p: the frozen twin (0.2716) and
  the forward period's own block rate (below).
- **Dispersion:** 44.5pp, the sd of a yes/no outcome at the twin rate, √(0.2716 × 0.7284).
- **Event rate:** 3 non-overlapping events in the 44 known days seen before the freeze came in the weeks around a midterm election; 8 a year is declared.

| counted events | smallest effect the read can resolve (2.8 SE) |
|---|---|
| 12 | 35.97pp |
| 24 | 25.44pp |

So in three years this design resolves only an effect of about 26pp or more. That number is the
floor of the instrument. It is **not** the effect anyone expects.

### Power declaration

- event_frequency_per_year: 8
- declared_effect_size: 26pp
- outcome_dispersion: 44.5pp
- outcome_horizon_days: 5
- dependence_unit: one non-overlapping 5-session event window; no two events share a session
- cluster_size: 1
- corpus_years: 3

### Slice declaration

- slice_purpose: EXPLORE
- slice_period: 2026-11-12 .. 2029-11-12
- selection_period: 2026-09-11 .. 2026-11-10
- hypothesis_source: the owner's midterm call as recorded in docs/ROADMAP.md CH-01, and the news corpus headlines read to set the thresholds
- hypothesis_source_period: 2026-09-11 .. 2026-11-10

EXPLORE, not CONFIRM: the patterns and thresholds were fitted by eye on two months of headlines, and one
forward record cannot confirm a rule that was shaped that way.

## Decision rule

Read only at 12 and 24 counted, graded forward events (final read as above). Each read prints the
event list, the outcomes by year, and the leave-one-event-out range.

**Forward block reference.** Non-overlapping 5-session blocks of the same outcome, starting at the first
session on or after 2026-11-12 and stepping 5 sessions, through the read date. It is what the forward period
did with no rule at all.

`SUPPORTED_SO_FAR` needs **all** of:
- n ≥ 12 and t ≥ 2 against the frozen twin (0.2716); at 12 events that is 7 or more true;
- t ≥ 2 against the forward block reference's own rate;
- the worst leave-one-event-out rate is still above the frozen twin.

`FAILED_VARIANT`: from 6 events on, at any grade, h ≤ the frozen twin and t ≤ −1 against it (at 6 events:
0 of 6 true). The rule is then `RETIRED_FROM_CURRENT_SEARCH`. On a true zero this fires about 15% of the
time at 6 events. It is a reversal detector and cannot confirm anything.

`CANNOT_DISTINGUISH`: everything else.

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

## The dated question (C-MIDTERM-35)

> SPY is higher 35 sessions after the 2026-11-13 close.

- **Window:** entry at the 2026-11-13 close, exit at the 2027-01-06 close (35 sessions).
- **Twin:** the claim was true on **0.7403** of 77 non-overlapping 35-session blocks since 2016
  (mean +2.06%, sd 4.22%). By year: 2016 0.62 · 2017 1.00 · 2018 0.57 · 2019 0.86 · 2020 0.57 · 2021 0.88 · 2022 0.57 · 2023 0.71 · 2024 1.00 · 2025 0.71 · 2026 0.60.
- **Owner's probability that the claim is true:** not given yet. It is accepted until the 2026-11-13 close (21:00 UTC)
  and never revised: `python -m scripts.owner_calls log --who owner --question C-MIDTERM-35 --p <x>`.
- The frozen rule does not answer this question: it is a direction question at 35 sessions, and the rule is about move size at 5.
- **Grading:** Brier score of the owner's probability against the twin's, on the bars on disk
  (`python -m scripts.owner_calls grade`). One question is one observation. It starts a calibration
  record; it shows no skill either way.

## Signature

- Design frozen: 2026-11-11 (the commit that adds this file).
- **Owner signature: PENDING**
