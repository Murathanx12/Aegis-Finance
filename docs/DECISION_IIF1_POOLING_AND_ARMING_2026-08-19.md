# DECISION RECORD — IIF-1 pooling under Amendment 1, and the arming flip

Decided 2026-08-19 evening, **before any licensed read exists** (first
read at 40 graded nights). Murat delegated both decisions in-session
("with these decisions I want you to choose the best option"); recorded
by the working session. This document does not edit the frozen surface
or the signed Brier declaration — it records how their outputs will be
assembled, chosen while no outcome could influence the choice.

## 1. N1–N2 pool with N3+ (intention-to-treat across the amendment)

**Decision: POOL.** All graded nights count toward the 40-night clock
and enter the primary paired-Brier read together.

Why this is the honest choice, not the convenient one:

- Amendment 1 (continuous-component trigger eligibility) changed which
  ROWS exist, never how any row is scored: deciding metric, BAR (0.10,
  signed), horizons, thresholds, `prereg_hash`, `frozen_surface` and
  `arm_implementation_fingerprint` (19461700cec485a6) are identical
  across N1–N3. The receipts' `amendment` block records which rule
  produced each night, so the pooled set is fully decomposable.
- The estimand of the forward test is "the investigator as operated
  under its registered protocol, amendments included" — the
  intention-to-treat estimand. Excluding pre-amendment nights would
  discard two clean, honestly-produced nights from a 40-night clock and
  create the precedent that any registered amendment resets the
  evidence, which would make amendments (a disclosed, attended
  mechanism) behave like kills.
- The §37 hazard is not pooling; it is choosing pooled-vs-split AFTER a
  read. This record forecloses that: the choice is made at n_reads = 0.

**Pre-declared sensitivity (SCREEN, never deciding):** at every licensed
read, the paired contrast is also reported for the post-amendment subset
alone. A sign flip between pooled and post-amendment is a finding to
investigate, not a licence to re-choose the primary.

## 2. The arming flip is mechanical once earned

**Decision: the working session arms the schtask without further
sign-off** on the first day after the acceptance condition is met,
subject to a pre-flight that verifies rather than trusts:

1. 3/3 consecutive SCHEDULED receipts with `contradicted: false`
   (clock starts at the 2026-08-20 17:00 firing — the `< NUL` era's
   receipts are void; see the falsification note in memory).
2. Task state Ready, NOT re-registered (LogonType unchanged), TR
   pointing at the tracked `empty_stdin.txt` redirect.
3. A clean-tree rehearsal manifest newer than the last night-module
   change, so `--require-rehearsal` is active for the armed run.
4. `git_dirty: false` on the pre-flight (code sense, per the 08-19
   provenance fix).

Earliest possible arming under this rule: after the third clean firing
(2026-08-22 if nights fire daily; the pre-flight, not the calendar, is
the gate). A failed pre-flight item defers arming by exactly one clean
firing — no partial credit, no half-arming (O20 §9).

## 3. Already in motion

Clean-tree rehearsal queued behind N3's exit (waiter on PID 29344);
its manifest re-baselines the six drifted module hashes and makes
`--require-rehearsal` usable from Night 4.

— recorded 2026-08-19 ~17:30 HKT, N3 in flight, zero reads taken
