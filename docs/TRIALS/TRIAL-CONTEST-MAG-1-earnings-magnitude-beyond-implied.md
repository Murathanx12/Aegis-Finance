# TRIAL-CONTEST-MAG-1 — does the size of past earnings moves predict the size of the next one beyond the options-implied move? (pre-registered decision rule)

> Pre-registered 2026-09-29, **before the first report in the window** (the window's first
> reaction session is 2026-10-12). This file is the tamper-evident commitment only once it is
> committed; if it is committed after 2026-10-12 13:30Z, every report reacting before the
> commit is excluded, never grandfathered. Proposed in `docs/reviews/REVIEW_2026-09-28_CONTEST_BOOK.md`
> §9; built by the contest desk (`scripts/contest_desk.py`, `scripts/contest_calendar.py`).
>
> **This trial trades nothing and creates no book.** It grades a measurement over every
> eligible US report in the contest window, whether or not the contest book held it, so the
> five weeks of the Bloomberg challenge produce a graded dataset whatever the rank.
> Licence of any reading: `RESEARCH_CLAIM` candidate only if it passes; the contest book itself
> stays `PRODUCT_EXPERIMENT`, family of one, and its P&L is never evidence for or against this.

## Hypothesis

Among liquid US companies reporting between 2026-10-12 and 2026-11-13, the trailing mean
absolute earnings reaction (last 8 on-cadence reactions, at least 3) carries information about
the size of the next reaction that is NOT already in the option market's implied earnings move
or in trailing volatility.

**Honest prior: modest, and the implied move is the reason.** Without the implied move, on
disk, the rank-regression coefficient of trailing |reaction| on next |reaction|, controlling
for sigma63 only, was 0.21–0.39 in every Oct 12 – Nov 13 window 2017–2025 (n = 504–1,483 a
year, cluster-by-date bootstrap SE 0.02–0.06; receipt
`backend/data/optimus/contest/prereg_prior_us_oct_windows.json`; Spearman 0.30–0.43). Option
market makers see the same history, so most of that is expected to be priced. A coefficient
near zero here is a plausible, informative outcome, not a failure of the measurement.

## Data (frozen definitions)

| item | definition |
|---|---|
| universe | US-listed common stocks in the desk's calendar with a reaction session in [2026-10-12, 2026-11-13]; median 63-session $ volume >= $10M and price >= $1 at the buy session; >= 3 prior on-cadence reactions |
| report timing | SEC 8-K item 2.02 acceptance time when filed by the read date; else the desk calendar's timing (Nasdaq / company); a report without a time is held two sessions (`contest_calendar.event_sessions`, UNKNOWN) |
| realised reaction (y) | \|close of the reaction session / close of the last session before the report − 1\| (`contest_desk.build_events`, `r_c2c`) |
| trailing magnitude (x) | mean \|r_c2c\| over the name's previous 8 on-cadence reactions (>= 3), from bars and 8-K stamps dated before the report |
| implied move (control 1) | ATM straddle mid / spot, first listed expiry on/after the reaction session, snapshot by the desk (`contest_desk.snapshot_implied`, `contest/implied/implied_moves.parquet`) BEFORE the report; the last snapshot before the report is used. If the owner exports the Terminal's implied move (`EE`/`EVTS`/`OVDV`), it is a SECONDARY control only |
| trailing volatility (control 2) | std of daily log returns over the 63 sessions before the buy session (`sig63`) |

## Primary metric (the only deciding number)

b = the coefficient on rank(x) in the OLS of rank(y) on [1, rank(x), rank(implied), rank(sig63)],
ranks scaled to (0, 1) within the sample. 95% CI from a cluster bootstrap by reaction date,
2,000 draws, `numpy.random.default_rng(20261012)`.

## Decision rule

| outcome | verdict | what follows |
|---|---|---|
| n >= 500 and b >= 0.05 and CI lower bound > 0 | `MAGNITUDE_BEYOND_IMPLIED` | owed: a straddle-cost test (`PRODUCT_EXPERIMENT`) before any claim; a RESEARCH_CLAIM needs a second season |
| n >= 500 and CI excludes 0 but b < 0.05 | `SMALL_BEYOND_IMPLIED` | recorded; no follow-up |
| n >= 500 and CI includes 0 | `FAILED_VARIANT` — the implied move contains it | the contest ranking may still use x as a free proxy for the implied move; no claim |
| n < 500 events with an implied move | `UNDERPOWERED` — no verdict, not a null | the rule is NOT re-run on a longer window without a new registration |

**MDE.** With SE ≈ 0.025–0.03 (the historical cluster SE at n ≈ 1,000–1,500, assumed to hold with
one more regressor), the 80%-power detectable effect is ≈ 2.8 × SE ≈ **0.07–0.08**. An effect
between 0.05 and 0.07 can pass the rule by luck of the draw or fail it; that is stated now.

**Earliest decision date: 2026-11-20** (the last reaction is 2026-11-13; one week for bars and
8-K stamps to land). Reported, never deciding: the same regression on open-to-open reactions;
Spearman(x, y) alone; the global (non-US) names without an implied move; by-week coefficients;
the top-decile mean |y| vs the sample mean.

## Secondary measurement (registered with its own rule, 2026-09-29, before any reading)

The contest desk's brief asks the narrower question first: **does past earnings-move size
predict the next move's size beyond trailing volatility alone?** It is registered here so the
five weeks answer it too, on a wider sample, without touching the primary rule above.

| item | definition |
|---|---|
| sample | every name the desk can see with a reaction session in [2026-10-12, 2026-11-13]: US and non-US (Hong Kong, China A, Japan, Korea, Taiwan, India, Indonesia, Europe), same liquidity / price / history filters; a reused ticker's history before its new company's first bar is refused (`contest_calendar.cut_stitched`) |
| y, x, sig63 | as in the primary table (non-US report times from the Yahoo earnings-date stamps, vendor; an untimed report is held two sessions) |
| metric | b_vol = the coefficient on rank(x) in the OLS of rank(y) on [1, rank(x), rank(sig63)], ranks scaled to (0, 1); cluster bootstrap by reaction date, 2,000 draws, `default_rng(20261013)` |

| outcome | verdict |
|---|---|
| n >= 500 and b_vol >= 0.10 and CI lower bound > 0 | `MAGNITUDE_BEYOND_VOL_REPLICATED` (a replication of the 2017-2025 prior 0.21-0.39, not a discovery) |
| n >= 500 and CI excludes 0 but b_vol < 0.10 | `WEAKER_THAN_PRIOR` — recorded; the desk's ranking is then no better than sorting by sig63 |
| n >= 500 and CI includes 0 | `FAILED_VARIANT` — the ranking column is dropped from the desk for the next season |
| n < 500 | `UNDERPOWERED` — no verdict |

Reported, never deciding: b_vol by market (US / Asia / Europe); the same regression with
rank(nn_size_5d), nn_lab's frozen size-of-move forecast read from
`backend/data/optimus/nn_lab/size_forecast/size_<date>.parquet` (US names only), added as a
third regressor. That forecast is for a 5-session excess move, not the earnings reaction; it
is a comparator, and no verdict here grades nn_lab.

## Power fields (lint R13)

- declared_effect_size: 0.07 (rank-regression coefficient on rank(x), the MDE above)
- event_frequency_per_year: 6000 (US on-cadence liquid reports a year; about 1,000-1,500 fall in this window)
- outcome_dispersion: 0.03 (cluster-by-date bootstrap SE of b at n ~ 1,000-1,500, measured 2021-2025 Oct windows without the implied move)
- slice_purpose: EXPLORE

slice_securities: US common stocks reporting in the window that pass the liquidity and history filters
slice_period: 2026-10-12 to 2026-11-13 (reaction sessions)
information_cutoff: each report's last session before the report (features), the last pre-report snapshot (implied move)

Why EXPLORE: the prior (0.21-0.39 without the implied move) was measured on the same kind of
data the builder looked at before writing this rule; the new ingredient is the implied-move
control, which has never been measured here. A pass licenses a second season, not a claim.

## Frozen parameters

TRAIL_N = 8, MIN_PRIOR = 3, liquidity floor $10M, the reaction definition above, the rank
regression, the bootstrap seed and draw count, the window, the 500 floor, the 0.05 threshold.

## Contamination clauses

- A reaction whose |r_c2c| > 200% or r_c2c < −80% is a data fault (split) and is dropped, as in
  the builder code; the count dropped is printed.
- A report whose date moved after the last implied-move snapshot (so the snapshot's expiry
  precedes the reaction) is dropped and counted.
- If the Yahoo option source fails on more than half the window's days, the verdict is
  `UNDERPOWERED`, never a null.
- The desk's contest trading does not enter this trial in any way.

## What this rule may NOT do

- It may not say anything about DIRECTION. The review measured the signed mean of the
  top-decile names at ≈ 0.
- It may not be quoted as evidence for the contest book, and the contest book's rank may not be
  quoted as evidence for it.
- No buy/sell language may be attached to x until a `MAGNITUDE_BEYOND_IMPLIED` verdict AND a
  cost test exist.


## Amendment 2026-09-29: which report stamps count as untimed (before any data in the window)

This amendment is dated 2026-09-29, before the window's first reaction session (2026-10-12). No
data from the window existed when it was written. The hypothesis, the primary metric, the
decision rule, the MDE and every frozen parameter are unchanged.

**What changed: which stamps are untimed.** The registered text says "a report without a time is
held two sessions (`contest_calendar.event_sessions`, UNKNOWN)", and that still holds. What
changed is which stamps count as "without a time":

- Until now only a stamp at local midnight counted.
- Yahoo writes "time not supplied" as **exactly 00:00:00 UTC**, which is 09:00 in Tokyo and
  08:00 in Hong Kong.
- `event_sessions` had read those stamps as INTRA or BMO. The reaction window it measured was
  therefore the day BEFORE the print (`REVIEW_2026-09-29_CONTEST_DESK.md` finding 1).
- From this amendment on, a stamp at 00:00:00 UTC is UNKNOWN (`contest_calendar.is_untimed_stamp`).
  Its report day is the UTC date.
- In the history this reclassifies 17,281 of 80,922 non-US stamps, 13,298 of them Japanese.

**Effect on the primary measurement (US):** none.

- US report times come from the SEC 8-K acceptance time.
- Where the desk's calendar supplies a US time, Yahoo's 00:00 UTC placeholders are 0.3% of the
  stamps.

**Effect on the secondary measurement (global):**

- Its non-US y is graded with the corrected `event_sessions`.
- The prior quoted for it (b 0.21-0.26 for Asia) was measured on the old windows.
- It was re-measured with the corrected timing as a NEW receipt:
  `backend/data/optimus/contest/compare/prior_by_market_timingfix_20260929T032407Z.json`.
  - Asia excluding India: b 0.20-0.28.
  - India: 0.14-0.19. The original pooled India into Asia.
  - Europe: 0.18-0.33.
  - US: unchanged.
- The original receipt is not modified. The secondary decision rule's 0.10 threshold is
  unchanged.


## Amendment 2026-09-29 (night): future sessions from exchange calendars; book-level refusals (before any data in the window)

Dated 2026-09-29, before the window's first reaction session (2026-10-12). No data from the window
existed when it was written. The hypothesis, the primary metric, the decision rule, the MDE and every
frozen parameter are unchanged.

**What changed.**

- `contest_desk.extend_future_sessions` assigned a future report's buy and reaction sessions by
  WEEKDAY. It now uses the listing's exchange calendar (`exchange_calendars`; weekdays only where no
  calendar exists, labelled). Before the change a Japanese report on the morning after Sports Day
  (the second Monday of October, the contest's first day) would have been given the holiday as its
  buy session, and Chinese reports in Golden Week the same.
- The contest BOOK (the order sheet, `scripts/contest_orders.py` + `contest_rehearsal.build_tickets`)
  now refuses, before sizing: a second listing of an issuer already on the sheet; a name whose US bars
  carry a `bar_defects` flag inside the trailing window; a date whose only source is
  ESTIMATED_PATTERN (the pattern estimator was exact on 27.7% of 19,210 past US prints, 14 days
  ahead). It also never holds more than five positions at any open (a two-session hold keeps its
  slot).

**Effect on the measurements:** none on what is graded.

- The trial grades EVERY eligible report in the window on realised bars, held or not. The book-level
  refusals change what is held, not what is measured.
- Realised reaction sessions come from bars, which never contain a holiday; the calendar change only
  moves the desk's forward guess of them.
