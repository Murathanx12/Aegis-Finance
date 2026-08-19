# PREREG — FACTOR-CHASE-FOREIGN-1 (frozen before any foreign byte
# was downloaded)

SIGNED-BY: Murat Abdullaev — recorded overnight order 2026-08-19
("don't wait, do the tests overnight till 8am"), recorded by the
working session.

**Status: SIGNED under the recorded blanket. Gate: `assert_signed` +
mean-masked §64 audit on disk before any verdict.**

## The confirmation logic (canon rule 2: foreign slices, parent barred)

The US screen found last-month factor-chasing HARMFUL: form1 tercile
−2.1%/yr net, p 0.00091, BH-surviving (registered_screens receipt).
The US series is the parent and is BARRED here. The confirmation
slice is GEOGRAPHY: five largest developed non-US markets —
**jpn, gbr, deu, fra, can** — whose JKP factor series have never been
downloaded by this program (this file is committed before the S3
fetch runs).

## Primary (ONE deciding cell)

- Per country: the SAME machinery as FACTOR-MOMENTUM-1's screen cell
  (formation = 1 month, skip = 1 is impossible at formation 1 — the
  US screen's form1 used months t−2..t−2? No: `build_books` with
  formation=1, skip=1 forms on month t−2 exactly; identical call
  here, byte-for-byte) — momentum tercile book minus static
  all-factors book, monthly, 20bp effective one-way, min 60 eligible
  factors per month (smaller markets; declared here, not tuned).
- **Deciding number: the POOLED paired monthly difference** across the
  five countries (country-month rows; date-block bootstrap blocks by
  MONTH so same-month rows across countries travel together — the
  cross-country correlation ride).
- Declared direction: NEGATIVE. Economic bar: 0.5%/yr (0.000417/mo).
- Verdicts: CHASING_HARMFUL_CONFIRMED (negative, |mean| ≥ run-time
  MDE) / CHASING_HARMLESS (one-sided: harm bounded under the bar) /
  NOT_ESTABLISHED. §64 mean-masked audit first, limbs declared.

## SCREEN

Per-country contrasts (5 rows, BH-FDR 0.10) and form-3/form-12
variants per country — reported, never deciding.

## May NOT

Touch the US series in any statistic here; add/substitute countries
after this commit; promote a screen cell; feed any lane. §61 cap.
Backfill-methodology note carried as in FACTOR-MOMENTUM-1.

— frozen 2026-08-19 night, pre-download

---

## RESULTS (registered run 2026-08-19 night, appended post-run)

Receipt `jkp/foreign_chase_trial_2026-08-19.json`; §64 audit written
first. 2,332 country-months over 524 unique months.

**Verdict: CHASING_HARMFUL_CONFIRMED.** Pooled momentum-tercile book −
static book = **−2.43%/yr net** (p 0.00022, |mean| ≥ run-time MDE).
Per-country screen: jpn −2.6%, gbr −2.0%, deu −2.7%, fra −3.6%, can
−1.5% — **negative in all five**, matching the barred US parent
(−2.1%/yr). CHASING_HARMLESS was not answerable at this n (declared
at audit). Combined with the US screen: chasing last-month factor
winners is harmful in six markets independently. §61 cap — this
licenses a NEGATIVE rule candidate (never reallocate toward
last-month strategy winners), to be transported through its own
prereg; it is not a trading signal.
