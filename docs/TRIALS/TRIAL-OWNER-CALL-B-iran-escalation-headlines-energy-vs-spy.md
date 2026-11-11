# TRIAL-OWNER-CALL-B: after a day of Iran-escalation headlines, do large US energy names beat SPY over the next 5 sessions?

## RESULTS SCOREBOARD

**Nothing has been graded forward.** The first forward day is 2026-11-12 (UTC). The rows below are a
descriptive paper log. No account holds a position because of it.

| item | value |
|---|---|
| forward events graded | 0 |
| seen before the freeze (listed, never counted) | 3 TRIGGER days (none absorbed), 41 QUIET, 17 UNKNOWN |
| twin (unconditional 5-session blocks, 2016-01-04 → 2026-11-10) | claim true on **0.4734** of 545 blocks; mean +0.03%, sd 3.38% |
| independent selector count | unchanged. This is a log, not a book |
| farm candidates tested / promoted | 0 / 0 |
| external execution drag | none. No order is sent |
| LLM spend / cost per gradeable output | $0.00 / $0.00. No LLM is used anywhere |

**`CLAIMS PROMOTED: none`**

- **Contract:** `docs/TRIALS/OWNER-CALLS-CONTRACT-v1.json`, theme `iran_escalation`, version `owner-calls/1`,
  **sha256 `f5b8a818b57a42a4458cdc3b55c2615ce7a885f9dcde2bcbfaeabb4db3ea4836`**.
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

After a UTC day whose headlines meet the frozen Iran-escalation rule, an equal-weight XOM/CVX/COP basket returns more than SPY over the 5 sessions that start at the next session's close, more often and by more than on ordinary 5-session blocks.

**Honest prior.** **Zero or negative.** `NEGATIVE_RESULTS.md` §15 found that after geopolitical-risk spikes oil FADES (−2.5% excess) and SPY is not hurt. The two graded triggers seen before the freeze split: −2.98pp and +4.99pp. The expected verdict at every read is `CANNOT_DISTINGUISH`, and `FAILED_VARIANT` is a live possibility.

## Where this comes from

- `docs/ROADMAP.md` CH-01: "Iran escalation → Brent/QQQ".
- `docs/ASKED_VS_DELIVERED_2026-11-09.md`: the owner's market calls are "measurements to run, not claims".
- **Instrument.** Brent, BNO and USO are absent from the bars panel. The equal-weight XOM/CVX/COP basket minus SPY is the energy exposure that has a 2016+ history on disk. Energy equities are not crude: they carry equity beta and refining margins.
- `docs/research_notes/2026-11-05/macro_stations_inactive.md` says a new oil/market strategy "would require a preregistered trial with matched controls". This is that trial, in descriptive form, with the unconditional block rate as the control.
- `NEGATIVE_RESULTS.md` §15: "GPR spikes are also not a sell signal (SPY CAR(0,+30) +0.61%, 64% positive; oil FADES −2.5% excess)". That result used a monthly geopolitical-risk index and SPY/oil. This trial uses typed daily headlines and an energy-equity pair, forward only.

## The design (frozen in the contract)

**Rule.** One UTC day of headlines is read from seven corpus sources: `google_news_rss_en_us`, `google_news_rss_en_gb`, `wsj_markets`, `wsj_business`, `wsj_tech`, `wsj_world`, `mw_topstories`.
Titles are lower-cased and counted once per day across the sources. A title is a hit when both patterns below match it
(case-insensitive):

```
\b(iran|iranian|tehran|hormuz|irgc)\b
\b(strikes?|struck|attacks?|attacked|missiles?|drones?|war|escalat\w*|blockade|seiz\w+|retaliat\w*|bomb\w*|tanker|closure|clos(e|es|ed|ing)|troops|invasion|killed)\b
```

**State of a day.**
- `UNKNOWN` when the day has fewer than 100 deduplicated titles. A reader outage is not a quiet news
  day.
- `TRIGGER` when hits ≥ 6 **and** hits / titles ≥ 2.5%.
- `QUIET` otherwise.

**Event.** A TRIGGER on day D opens one event. Entry is the close of the first XNYS session on or after
D+1. Exit is the close 5 sessions later. Events never overlap: a TRIGGER whose entry falls inside an
open event is counted as absorbed and opens nothing.

**Outcome.** The simple return of XOM / CVX / COP minus SPY from the entry close to the exit close (the basket is
equal-weight, bought once and held). The claim is true when the outcome is
above 0.

**Twin.** The same outcome on every non-overlapping 5-session block from 2016-01-04 that ended before
inception. Blocks are counted, never days. The claim was true on 0.4734 of 545 blocks. By year:
2016 0.55 · 2017 0.36 · 2018 0.50 · 2019 0.41 · 2020 0.36 · 2021 0.51 · 2022 0.62 · 2023 0.42 · 2024 0.48 · 2025 0.44 · 2026 0.57.

**Pinning.** Corpus day files can be rewritten. `python -m scripts.owner_calls record` pins every ended
forward day once in a hash-chained ledger (`owner_calls/states.jsonl`): the state of each theme and the
SHA-256 of each source file. The pinned state stands if a file changes later, and the change is
reported as drift. **A forward event counts at a formal read only when its trigger day was pinned on or
before its entry date (UTC).** An unpinned or late-pinned event is listed as NOT COUNTED.

## What was seen before the freeze

The thresholds were chosen on 2026-11-11 **after** reading the corpus from 2026-09-11 to 2026-11-10, with
prices for that period on disk. Every day before inception is labelled `SEEN_BEFORE_FREEZE`. Those days are
never forward evidence and never enter a read. Over those 61 days: 3 TRIGGER days (none absorbed), 41 QUIET, 17 UNKNOWN.

| trigger day | hits / titles | entry → exit | outcome | claim true |
|---|---|---|---|---|
| 2026-09-16 | 9 / 323 | 2026-09-17 → 2026-09-24 | basket − SPY −2.98% | false |
| 2026-10-02 | 10 / 292 | 2026-10-05 → 2026-10-12 | basket − SPY +4.99% | true |
| 2026-11-10 | 10 / 318 | 2026-11-11 → 2026-11-18 | PENDING | — |

A forward event may share sessions with a pending seen event. The two chains never mix: a seen trigger
does not absorb a forward one.

## Statistics and power

One observation per **event**. Events never overlap, so no two observations share a session.

- **Primary metric:** the mean of `+(basket − SPY)` over counted, graded forward events (positive supports
  the hypothesis). t = mean / (sd / √n).
- **Dispersion:** 3.377pp, the sd of the pair's 5-session outcome over the 545 twin blocks. It is
  measured on unconditional blocks, not in the trigger state, where it may be larger.
- **Event rate:** 3 non-overlapping events in the 44 known days seen before the freeze is about 18 to 25 a year in an active period; 12 is declared, because a quiet year would have fewer.

| counted events | smallest effect the read can resolve (2.8 SE) |
|---|---|
| 12 | 2.73pp |
| 24 | 1.93pp |
| 36 | 1.58pp |

So in three years this design resolves only an effect of about 1.6pp or more. That number is the
floor of the instrument. It is **not** the effect anyone expects.

### Power declaration

- event_frequency_per_year: 12
- declared_effect_size: 1.6pp
- outcome_dispersion: 3.377pp
- outcome_horizon_days: 5
- dependence_unit: one non-overlapping 5-session event window; no two events share a session
- cluster_size: 1
- corpus_years: 3

### Slice declaration

- slice_purpose: EXPLORE
- slice_period: 2026-11-12 .. 2029-11-12
- selection_period: 2026-09-11 .. 2026-11-10
- hypothesis_source: the owner's Iran call as recorded in docs/ROADMAP.md CH-01, NEGATIVE_RESULTS §15, and the news corpus headlines read to set the thresholds
- hypothesis_source_period: 2026-09-11 .. 2026-11-10

EXPLORE, not CONFIRM: the patterns and thresholds were fitted by eye on two months of headlines, and one
forward record cannot confirm a rule that was shaped that way.

Resurrects: INSTR-MACRO-BATCH4 GPR spike (NEGATIVE_RESULTS §15) — new instrument: typed daily Iran-escalation headlines from a pinned news corpus replace the monthly GPR index, the outcome is an energy-equity basket minus SPY over 5 sessions instead of SPY or crude over 30 days, and every observation is forward of a frozen contract

## Decision rule

Read only at 12, 24 and 36 counted, graded forward events (final read as above). Each read prints the
event list, the outcomes by year, and the leave-one-event-out range.

**Forward block reference.** Non-overlapping 5-session blocks of the same outcome, starting at the first
session on or after 2026-11-12 and stepping 5 sessions, through the read date. It is what the forward period
did with no rule at all.

`SUPPORTED_SO_FAR` needs **all** of:
- mean > 0 and t ≥ 2;
- the worst leave-one-event-out mean is still > 0;
- the hit rate is above the frozen twin (0.4734);
- the event mean is above the forward block reference's mean (same sign convention).

`FAILED_VARIANT`: from 6 events on, at any grade, mean ≤ 0 and t ≤ −1. The rule is then
`RETIRED_FROM_CURRENT_SEARCH`. On a true zero this fires about 18% of the time per look at 6 events, and
about 2% of the time if the true effect were 1.6pp. It is a reversal detector and cannot confirm
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

## The dated question (B-ENERGY-42)

> An equal-weight XOM/CVX/COP basket returns more than SPY from the 2026-11-13 close over the next 42 sessions.

- **Window:** entry at the 2026-11-13 close, exit at the 2027-01-15 close (42 sessions).
- **Twin:** the claim was true on **0.4062** of 64 non-overlapping 42-session blocks since 2016
  (mean +0.26%, sd 12.34%). By year: 2016 0.67 · 2017 0.33 · 2018 0.67 · 2019 0.33 · 2020 0.17 · 2021 0.50 · 2022 0.67 · 2023 0.17 · 2024 0.17 · 2025 0.33 · 2026 0.50.
- **Owner's probability that the claim is true:** not given yet. It is accepted until the 2026-11-13 close (21:00 UTC)
  and never revised: `python -m scripts.owner_calls log --who owner --question B-ENERGY-42 --p <x>`.
- The frozen rule does not answer this question: its horizon is 5 sessions and this one is 42.
- **Grading:** Brier score of the owner's probability against the twin's, on the bars on disk
  (`python -m scripts.owner_calls grade`). One question is one observation. It starts a calibration
  record; it shows no skill either way.

## Signature

- Design frozen: 2026-11-11 (the commit that adds this file).
- **Owner signature: PENDING**
