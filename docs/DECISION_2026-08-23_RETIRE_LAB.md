# DECISION — 2026-08-23: retire the autonomous R&D lab

**Status: DECIDED.** Murat delegated this ("what is best for lab do that too").
**Reversible:** nothing is deleted. The lab code stays on `main`; the abandoned
v5 rewrite is preserved on branch `lab-v5-abandoned`.

---

## The decision

`lab/rd_loop.py` is **retired**. It is not scheduled, not run, and not
maintained. The directory stays in the repository as history.

## Why

**1. It has not run in four months.** Last real run 2026-04-17. A subsystem
nobody starts is not a capability; it is a maintenance liability that reads
like a capability on the README.

**2. The arena supersedes it, completely.** The lab's purpose was "run
autonomous sessions overnight to improve the engine." The arena does the same
job and does it better on every axis that matters:

| | `rd_loop` | the arena |
|---|---|---|
| runs | manually, last 2026-04-17 | daily, 17:45 ET, in production |
| grades itself | no | yes — matured outcomes into reliability cells |
| licence | none | `PRODUCT_EXPERIMENT` |
| identity | none | seeded, fingerprinted, drift-refusing |
| output | code commits | NAV series + decisions + graded forecasts |

The arena also *learns from being wrong*, which was the lab's whole ambition
and which the lab never implemented.

**3. Its working tree was a half-finished rewrite.** The uncommitted v5 removed
**23 of 27 collectors** and broke 14 tests by deleting a function they cover.
That is not a stale-test problem; the rewrite dropped wired functionality. Any
session picking up this repo would have had to decide what to do with it before
doing anything else.

**4. The risk profile is wrong for what it returns.** `rd_loop` launches
autonomous sessions that **auto-commit to a branch**. That is a reasonable
trade when it is producing results. It has produced none since April.

## What this does NOT mean

- **Not "autonomous research is a bad idea."** It is the mission. The arena is
  the autonomous researcher now, and it is a disciplined one.
- **Not a deletion.** `lab/` stays. `lab-v5-abandoned` holds the rewrite. Any
  of it can be resurrected.
- **Not a judgement on the concept of a nightly improvement loop.** The
  nightly critic loop in the profit-first roadmap (§P1) is exactly that idea,
  done against graded outcomes instead of against vibes.

## What replaces it, concretely

The roadmap's nightly critic loop: for each decision and each meaningful
*rejected* alternative, record what was believed, what was held, what happened,
and which of selection / timing / sizing / event-interpretation / source-trust /
regime / cost / randomness explains the gap — then feed matured outcomes into
the learners that are allowed to update automatically (source reliability,
calibration, statistical parameters).

Code changes remain **versioned challengers with tests**, never an LLM
rewriting production and declaring itself improved from the same data that
motivated the rewrite.

## Reversal

`git checkout lab-v5-abandoned` restores the rewrite. Re-authorising the loop
means finishing v5 (or reverting it), restoring the 23 collectors or declaring
why they are not needed, and getting the 14 tests green — after which it is a
normal decision, not this one.
