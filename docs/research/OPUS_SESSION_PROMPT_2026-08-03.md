# Opus execution session #3 — kickoff prompt (prepared 2026-08-02)

Copy everything below the line into a fresh `/model opus` session started in
`C:\Users\mrthn\aegis-finance`. **Plug the laptop in first** — session #2
measured Windows battery mode throttling unattended compute to ~5% of a core
(4 hours for a 30-minute run).

---

You are running the third pre-planned execution session for the Aegis
program. Same discipline as the first two (OPUS_SESSION_PROMPT_2026-08-01.md —
re-read its "House rules that bind you absolutely" section verbatim). Both of
today's runs are already frozen at module commit `98c99e2` — go straight to
build for each. Read first:

1. `C:\Users\mrthn\Aegis module\TRIALS\INSTR-RANK-DEAD.md` (candidate 174)
2. `C:\Users\mrthn\Aegis module\TRIALS\TRIAL-EVENT-13DG.md` (candidates 175-177)
3. `NEGATIVE_RESULTS.md` §20, §26, §27

## Task 1 — run INSTR-RANK-DEAD (the replication bridge)

This instrument answers the program's standing methodological challenge
(Murat, 2026-08-02: "are we testing strategies wrong?"), so execution
fidelity matters more than usual.

Build `scripts/run_instr_rank_dead.py`: rebuild `io_level` (small) and
`skew_25d` (optionable small) from their frozen trial builders UNCHANGED,
explore 2004-2018, all gross. Ladder per the frozen doc: L1 D10−D1 spread EW
and VW; L2 top-minus-universe vs universe-minus-bottom EW; L3 rank-IC in
upper vs lower dollar-volume halves. Score the four pre-declared readings
R1-R4 independently and record which fire.

Spec tests first (minimum): the rebuilt signals reproduce their banked
explore IC t (11.29 / 8.34) to within rounding — this is the guard that the
builders really are unchanged; VW weights come from lagged market cap; L2's
top leg equals the banked book's gross leg.

**If R4 fires (L1 dead both weightings): STOP after writing results.** The
frozen doc commits the program to a harness audit in that branch — that audit
is a new attended decision, not something this session improvises.

## Task 2 — run TRIAL-EVENT-13DG

Build `scripts/run_trial_event_13dg.py` on `daily_events.py` + the harvested
`data/events/edgar_13dg_events.parquet`. Frozen spec exactly: initial filings
only, three arms, matched controls mandatory, differenced CAR the only
deciding number, clustered t, era split reported, −1..0 reported never
deciding. The −1..0 window doubles as the live sanity check that event dates
are real — if 13D shows no announcement-window action at all, suspect the
pipeline before believing the nulls, and say so.

One shot per arm. If any arm passes its CAR gate: **STOP before the
portfolio/scan_signal step** and flag — that step plus confirm are attended.

## Task 3 — write-ups

Results into both trial docs + NEGATIVE_RESULTS sections (or pass notes),
house predictions scored, ledger updated if anything becomes scoreable.
Module tests green, module pushed, prod untouched and verified healthy.
Candidate count after this session: **177** (nothing new may be registered
this session — zero exceptions).

Summary must state: which pre-declared readings fired on RANK-DEAD (this is
the answer Murat is waiting for), both 13DG verdicts as frozen, repairs
disclosed, and what if anything now needs an attended decision.
