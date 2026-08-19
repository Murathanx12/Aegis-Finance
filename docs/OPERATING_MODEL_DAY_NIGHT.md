# OPERATING MODEL — day factory, night simulation (adopted 2026-08-19)

Murat's directive, 2026-08-19: *"rather than waiting everyday for nights we
should work in the days and at nights the simulation happens."* External
review round 3 said the same thing in one line: **IIF is a clock. It is not
the project schedule.** This document makes the cadence operational.

## The three-phase day

**DAY (working hours → 16:15 HKT)** — build, mine, falsify, train, autopsy,
collect PIT data, run historical screens. Multiple parallel shells on
independent work; heavy CPU/network/WRDS allowed. Everything lands on
`lab/autonomous-rd` (or the working branch of the day); main moves only by
attended merge. The day is where the research engine advances — nothing in
it waits on a night having happened.

**QUIESCE (16:15–17:00 HKT)** — heavy jobs checkpoint or stop; targeted
tests, fast suite, push; the checkout is left stable so the forward lane
gets clean machine/network headroom. Nothing that competes for the machine
runs past 16:15.

**NIGHT (17:00 HKT →)** — the simulation accrues:
- **IIF-1 night** (17:00 launch; attended until the launcher arms at 3/3
  clean SCHEDULED receipts, then unattended by design). One night = one
  graded forward observation. Nobody reads before the 40-night gate.
- **Research daemon background queue** (Order 20 §1 admissibility:
  historical/offline, no reserved windows, not on the IIF frozen surface,
  enters through `submit()` with priors declared). The executor
  (`scripts/research_executor_run.py --execute`) runs what is RUNNABLE and
  receipts what is BLOCKED, with reasons.
- **Overnight rd_loop** (`python lab/rd_loop.py`) when Murat wants
  model-driven improvement cycles on top.

**MORNING** — ingest receipts: executor receipt, night receipt, prod
warnings. Legally-readable outcomes (mechanics only before licensed reads)
reprioritize nothing by hand — new jobs enter through `submit()` so the
m-ledger stays honest.

## What the night may never do

- Read a reserved confirmation window (derived from
  `confirmation_budget.jsonl`; the guard refuses absent inputs).
- Touch the frozen IIF surface or the paper_nav write path.
- Record a verdict for a signature-gated trial (the tournament refuses
  unsigned; the executor classifies those BLOCKED with the reason).
- Spend API dollars to look busy (mission rule 5 — resolved information
  per dollar, not utilization).

## What the day should never do

- Wait for a night. The 40-night clock runs by itself; day sessions that
  idle "until resolutions" are the anti-pattern this document retires.
- Compete with the night: no heavy local jobs past 16:15 HKT.
- Half-arm, half-sign, or half-read anything attended. Attended items
  queue for Murat; everything around them gets built to one-command
  readiness (the positions endpoint and the amended prereg are the
  pattern: the attended act shrinks to minutes).

## Standing day-session shape (what /grind runs by default)

1. VERIFY: fast suite green, `session_briefing` + `aegis_verified_state`.
2. Cycles: SELECT → WORK → PROVE → COMMIT → LOG, 30–60 min each,
   parallel shells where independent.
3. Every session report opens RESULTS PRODUCED, then infrastructure
   (Order 20 §1). A night's operational health is one line.
4. Quiesce boundary respected; push before it; leave the tree green.

## Attended calendar anchor (as of 2026-08-19)

Wed Night 3 · Thu Night 4 · Fri 08-21 first 396 resolutions (mechanics
only) · ~Sun/Mon arm the launcher after 3/3 clean receipts (blocked on the
schtask `< NUL` fix) · signatures when handed: amended NET prereg,
Brier bar, LOSS amendment, Track E.
