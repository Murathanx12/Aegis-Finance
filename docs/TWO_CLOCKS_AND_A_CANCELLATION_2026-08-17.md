# Two clocks, and a guard that was safe by cancellation

**2026-08-17, acting on the review's P0/P1 order. This corrects two claims this
repo made earlier today, both of them mine, and moves the timing decision off a
basis that only looked conservative.**

---

## 1. The two clocks, named

The review caught that Night 1's receipt says **115.4 elapsed minutes** while the
new timing code calibrated against a **133-minute wall clock**. Both numbers are
real. Reconciled from the receipt's own fields:

```
CLOCK_RUN_ELAPSED         115.4 min   elapsed_s 6921.8 / 60  ==  timing.actual_minutes
CLOCK_DECISION_TO_FINISH  133.6 min   decision_lag_minutes_at_end
difference                 18.2 min   decision_lag_minutes  (snapshot assembly)
```

`133.6 − 115.4 = 18.2`, exactly the assembly lag. So 133.6 is
**snapshot-to-finish**, not the run.

**The guard forecasts `CLOCK_RUN_ELAPSED`**, declared in code as
`DURATION_FORECAST_CLOCK`. The question is "will the run finish before the bell",
and the run starts when the run starts. The snapshot lag is separately guarded by
`assert_decision_time_fresh`; folding it in here would double-count it, because
the guard is invoked *before* the run, when the lag is already spent and already
checked.

### What was wrong because of it

* **199.5 s/cell was an artefact.** It is `133.6 × 60 / 40`. The receipt measures
  `mean_cell_wall_seconds = 173.0` directly, and `173.0 × 40 = 115.3 min`, which
  is `CLOCK_RUN_ELAPSED`. Every figure derived from 199.5 was wrong.
* **"The 3.529 counts calls in flight, not wall-clock speedup" was false.** The
  receipt shows `measured_efficiency = mean_cell_serial_seconds /
  mean_cell_wall_seconds = 610.572 / 173.002 = 3.529` — a genuine per-cell
  wall-clock speedup. I asserted the opposite in a commit message and a doc.

Both are pinned against the real receipt in
`backend/tests/test_the_two_night_clocks.py`, so a future reader working from a
summary instead of the file cannot re-conflate them.

---

## 2. The serial branch was safe by cancellation

This is the more serious finding, and it is a defect in the fix I shipped this
morning. The serial branch was adopted on the grounds that *"a verdict that holds
serially does not depend on an input the guard cannot verify."* It depends on
`MEASURED_CALL_SECONDS`, and Night 1 shows that constant is **1.98× low**:

```
implied per-call latency   610.572 / (5 arms × 7.085 calls)  =  17.24 s
MEASURED_CALL_SECONDS                                            8.70 s
```

So:

| quantity | minutes | |
|---|---|---|
| modelled serial (what the guard used) | **205.5** | |
| TRUE serial (measured, 610.572 s/cell × 40) | **407.0** | modelled is **0.50×** of it |
| actual run (`CLOCK_RUN_ELAPSED`) | **115.4** | modelled is **1.78×** of it |

The modelled serial is **half the true serial cost**, and conservative against the
real run only because ignoring a measured 3.529× concurrency speedup roughly
cancels the 1.98× latency understatement:

```
3.529 / 1.98  =  1.78   ==  205.5 / 115.4
```

That identity is asserted as a test. **This project's signature failure mode — two
wrong constants cancelling and looking like a margin — reproduced inside the fix
written to eliminate it.** I wrote that lesson into the canon this morning and
then shipped an instance of it eight hours later.

### Why the obvious repair is wrong

Raising `MEASURED_CALL_SECONDS` to the measured 17.24 s makes the modelled serial
**407 min**, which refuses every start time that has ever worked — including
15:00 local — on the strength of a fully serial night this runner never performs.
So the constant is deliberately left at 8.7 with the discrepancy documented at
the definition, and the decision moved off it.

### What the decision rests on now

`derive_night_duration_bound()` bounds the quantity actually at risk — how long
the run *takes* — from completed nights:

**worst completed night's measured duration × `DECLARED_DURATION_SAFETY_FACTOR`**

Same three rules as `derive_calls_per_cell`, for the same reasons: void and
sandbox nights excluded, the maximum rather than the mean, and the caller takes
`max(modelled_serial, duration_bound)` so **a measurement can only ever tighten
this guard, never license a start the previous basis refused.**

The factor is **2.0** — declared, and chosen before looking at what start time it
permits, precisely so it cannot be tuned to bless a preferred schedule. Fitting it
to 1.78 to reproduce the previously-published 205.5 would have been exactly that
move. A test asserts `115.36 × 2.0 > 205.5`, i.e. that the declared factor is
**tighter** than the basis it replaces.

### The boundary moved, as the review said it would

```
decision        230.7 min   MEASURED_DURATION_BOUND (worst 115.36 × 2.0, n=1)
latest safe start  09:39Z = 17:39 local     (was 10:04Z = 18:04)
```

**Night 2's approved 17:00 start passes with 39 minutes of headroom.** Per the
review's ruling, 18:04 was never permanent — it was the derived boundary under the
then-current measured state, and it has now moved. Nothing is hard-coded: verified
that `9.3` and `18:04` appear nowhere in Python as thresholds (only `10:04Z` in a
test assertion on printed output, and an unrelated `10:04` in a `copy_lab`
docstring).

---

## 3. Calibration is now consumed, not just logged

The review noted the receipts already store projection and realization, and that
what was missing was **consumption**. The duration bound consumes measured
durations directly, and the per-night history carries the error beside it:

```
2026-08-17   projected 70 -> took 115 min  (1.66x, error +46 min)
```

**Night 1's guard projected 69.6 minutes for a night that took 115.4** — 1.66×
optimistic on the very night it certified. The readiness report prints this above
the decision, with the instruction not to plan from either projection row.

Also added, per the review: `planned_start_utc`, `actual_start_utc`, and a
**derived** `start_delay_minutes`. Night 1 launched 39 minutes late unattended and
nothing recorded it, so the slip had to be reconstructed from log timestamps. A
late start spends margin the guard certified *at the planned time*, so a positive
delay now logs a warning. With no plan supplied the delay is `None`, never `0` —
zero would claim a punctuality nobody measured.

---

## 4. Ledger health semantics

**`DEGRADED` = actionable overdue OR excessive quiet OR persistence failure.**

The earlier split moved the quarantine out of a bare overdue count but left the
message in `problems` — and `problems` is what computes `DEGRADED`, so 25
deliberately ungradeable rows would have held the canary red indefinitely. A
permanently red canary is alarm fatigue with extra steps: the next genuinely
actionable overdue record would arrive on a page that had said `DEGRADED` for
months.

The review's refinement is the part that keeps it honest, and it is now a test:
**quiet and persistence still degrade.** "Make health depend only on actionable
overdue" would paint a dead or unpersisted ledger green, which is the failure this
row exists to catch. Quarantine information moved to a non-degrading `notices`
field, with `n_overdue_quarantined` still reported prominently. The 25 rows are
untouched.

One consequence worth stating: prod's ledger will read `ok` with a notice until
**2026-08-19**, when `days_quiet` crosses 7 and it degrades on quiet — which is
correct, because nothing is writing forecasts to that volume.

---

## 5. Provenance is four-dimensional

```
implementation_version          what we BELIEVE changed          (declared)
arm_implementation_fingerprint  what the arm module's bytes ARE   (derived)
git_commit                      which tree it came from
git_dirty                       whether the tree matched it
```

The fingerprint is **not** replaced by the commit SHA, per the review: it is
derived from the source bytes defining arm behaviour, so it differs on an
uncommitted edit that a SHA cannot see. The SHA adds what the fingerprint cannot —
where to find that code again.

`git_dirty` is `None` when undeterminable, **never `False`**. A guard reporting
"clean" because it failed to look would certify a night as reproducible from a
commit that does not contain the code that ran. Both the exception path and a
nonzero `git status` exit are tested to yield `None`.

---

## What is NOT done here, and why

* **Night 2 itself** — approved for 2026-08-18 17:00 local, not runnable tonight.
  Readiness must be recomputed immediately before launch; the derived boundary
  (currently 17:39 local) governs, not a remembered clock time.
* **`iif1_read_gate.check_read` enrolment** and the **frozen-loss / Patton
  classification** — both live in the `Aegis module` sibling, which this repo
  deliberately does not carry. Cannot be done from here.
* **Track E preregistration, the PTR delay instrument, N25 estimator
  preregistration** — P2, and registration is attended by ruling.
* **`DECLARED_CONCURRENCY_EFFICIENCY`** stays 2.0. It is frozen pre-registration;
  amending it is attended, and nothing operational waits on it now that the
  decision does not read it.
