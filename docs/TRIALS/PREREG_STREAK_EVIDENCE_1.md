# PREREG — STREAK-EVIDENCE-1 (DRAFT — design registered, not signed)

**Status: DESIGN registered 2026-08-19 night (Murat's coin-flip
directive: "99 heads in a row is evidence about the coin, not a reason
to recite 50-50"). No outcome evaluated. §64 mean-masked power audit
before signature; `assert_signed` against this path before any
registered run.**

## The question, stated the way the parable states it

After a stock closes up N days in a row, is the next period's return
distribution measurably different from what its ORDINARY
characteristics (momentum, vol, size) already predict? I.e., does the
STREAK itself — the run-length, the pure coin-flip pattern — carry
incremental information, or is a streak just momentum wearing a costume?

The honest twist the parable demands: we do not presume the direction.
Persistence (biased coin ⇒ more heads) and reversal (lottery
demand/overextension ⇒ snap-back) are both live priors in the
literature. Direction is measured, not assumed.

## Data

`crsp_dsf_*` daily panel 2013–2024 (pulled 2026-08-19), PIT-eligible
names at formation, delisting-inclusive forward returns.

## Primary (ONE deciding cell)

- Event: close-to-close up-streak of length >= 7 trading days
  (P(>=7 | fair coin) ~ 0.8% per start — rare enough to mean something,
  common enough to power).
- Deciding number: mean 21-day forward abnormal return of streak names
  vs their MATCHED CONTROLS (§16): same month, nearest neighbour on
  mom_12_1 and vol_63 WITHOUT a >=7 streak — the control is what makes
  this "beyond momentum".
- Paired difference, date-block bootstrap
  (`bootstrap_block_dates(dates, 21)`), three-way verdict:
  STREAK_INFORMATIVE (either sign, |mean| >= MDE, Holm across the m = 2
  declared directions) / STREAK_UNINFORMATIVE (one-sided bounds inside
  the economic bar) / NOT_ESTABLISHED.
- Economic bar: 0.25% per 21 days (~3%/yr) — below that a streak signal
  cannot clear costs.

## SCREEN (BH-FDR 0.10, m = cells run)

Streak lengths 5/7/10; down-streaks (mirror); volume-confirmed streaks;
interaction with the JKP short-term-reversal char; streak survival
curves (does day N+1 continue conditional on N).

## Corpse confrontation

- §15-adjacent: streaks selected at day N are conditioned on having
  survived N days — forward window starts strictly AFTER formation,
  controls matched at the same date, so the selection is symmetric.
- MAX-lottery literature: extreme recent runs may select lottery
  stocks; the vol-matched control carries that; the SCREEN reports the
  MAX interaction explicitly.

## May NOT

Promote a screen cell (§37); claim market-level regularity from a
2013–2024 large-cap-skewed panel (§60 — the CRSP full-history re-run is
the descendant); feed any lane before a generation prereg transports it.

— registered 2026-08-19 night; prior: GENUINELY UNKNOWN direction,
which is the point
