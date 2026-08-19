# PREREG — STREAK-EVIDENCE-1

SIGNED-BY: Murat Abdullaev — recorded overnight handoff approval
2026-08-19 ("come up with novel tests if data approves ... I handoff to
you"), given before any outcome existed; recorded by the working
session.

**Status: SIGNED. Design registered 2026-08-19 night (Murat's coin-flip
directive: "99 heads in a row is evidence about the coin, not a reason
to recite 50-50").**

**§64 power (mean-masked, receipt `streak/power_audit_2026-08-19.json`,
run before any mean was seen):** 19,726 matched events on 2,155 event
dates, 72 effective 30-date blocks, MDE 0.00407 per 21 days. The
0.0025 bar is BELOW the MDE ⇒ declared prospectively:
**STREAK_UNINFORMATIVE is NOT_ANSWERABLE_AT_N** — reachable verdicts
are STREAK_INFORMATIVE (|effect| ≥ run-time MDE, either declared
direction, Holm m=2) and NOT_ESTABLISHED. Bar not shrunk. Rehearsal
gate passed pre-run: persistence/reversal/null all recovered. Dropped
events disclosed on the receipt (11,283 not-PIT-eligible is the large
bucket — small-cap streaks outside the eligible universe).**

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

---

## RESULTS (registered run 2026-08-19 night, appended post-run)

Receipt `streak/trial_2026-08-19.json`. 19,726 matched events, 72
effective blocks.

**Verdict: NOT_ESTABLISHED.** Streak names minus matched controls =
**−0.254% per 21 days** (90% CI [−0.42%, +0.05%]) vs MDE 0.41%. The
lean is REVERSAL — the opposite of the naive biased-coin reading:
after ≥7 up-closes, large-cap-eligible names tended to give a little
back relative to momentum/vol-matched twins, consistent with the
short-term-reversal and lottery literatures, but below establishment.
STREAK_UNINFORMATIVE was NOT_ANSWERABLE_AT_N by prior declaration.
Nothing licenses a signal. The CRSP full-history re-run (more eras,
more names) is the declared descendant; the screen grid (lengths 5/10,
down-streaks, volume confirmation) remains unrun and unpeeked.
