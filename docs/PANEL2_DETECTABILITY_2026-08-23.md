# AEGIS-PANEL-2 detectability — the gate on TOURNAMENT-2, measured

**Date:** 2026-08-23 · **Receipts:** `backend/data/optimus/aegis_panel/panel2_detectability/`
· **Panel hash** `2812090a3ecbd1f5` · **Instrument hash** `d58b6d0310008713`

Queue item 3 of the builder handoff: *"Detectability FIRST, registration
SECOND."* This is that measurement. The headline in one line:

> **At panel-2 scale the instrument is no longer blind — every planted world's
> best arm now excludes zero, where every panel-1 world's crossed it. But it
> recovers only ~13% of a DIFFUSE planted effect, so a null verdict on diffuse
> signal would bound the truth at ~0.042 IC — four times the economic bar.**

## 1. The floor had to be declared first, and was declared blind

The panel-2 builder deliberately did not recompute panel-1's seven price-floor
features, deferring them to "the TOURNAMENT-2 prereg". That deferral sat on a
circular path: the prereg is blocked on this gate, this gate needs planted
worlds, and every planted world contrasts its arms *against the floor*.

So the floor is declared in `backend/services/aegis_panel2_spec.py`, ahead of
the prereg, under the only condition that makes a pre-declaration honest: each
column is the JKP column that **computes the same quantity** as its panel-1
counterpart. No return, IC or contrast was consulted. One substitution is
inexact and is named rather than buried — JKP publishes no 63-day realised
volatility, so `vol_63 → rvol_252d`. The set is frozen with a `spec_hash`; the
prereg must **cite** that hash, not restate the set.

Declaring it surfaced a real defect: on panel-2 the floor columns *are*
characteristics (unlike panel-1, where the floor was own-construction and
disjoint from JKP). Concatenating floor + characteristics therefore handed the
full arm **seven duplicated columns**. The full arm would have been trained on
something other than what its name said, in every fold, silently.

It also sharpens the question. Panel-2's contrast is exactly nested: *do the
other 405 characteristics add anything beyond these 7 price columns?*

## 2. What was measured

Three worlds required by `detectability_gate.REQUIRED_WORLDS`, planted at
IC 0.03 with panel-1's carriers, nine folds (2016–2024), training back to 1926
(~4.1M rows per fold). Arms: `floor_lgbm`, `full_lgbm`, and the `_zlabel` pair
that trains on the per-date z-scored label.

| world | arm | dIC vs floor | 95% CI | recovery |
|---|---|---|---|---|
| linear (sparse) | full_lgbm | **+0.01363** | [+0.0106, +0.0166] | **45.4%** |
| | full_lgbm_zlabel | +0.01312 | [+0.0103, +0.0161] | 43.7% |
| linear_dense | full_lgbm | +0.00339 | [+0.0004, +0.0062] | 11.3% |
| | full_lgbm_zlabel | **+0.00379** | [+0.0005, +0.0068] | **12.6%** |
| linear_hetero | full_lgbm | +0.00145 | [−0.0019, +0.0042] | 4.8% |
| | full_lgbm_zlabel | **+0.00379** | [+0.0005, +0.0068] | **12.6%** |

Against panel-1, on the arm both panels ran (`full_lgbm`):

| world | panel-1 | panel-2 | panel-1 best arm |
|---|---|---|---|
| linear | +0.00180 (ci_lo −0.0039) | +0.01363 | full_lgbm, 6.0% |
| linear_dense | +0.00097 (ci_lo −0.0043) | +0.00339 | full_ridge, 9.9% |
| linear_hetero | +0.00205 (ci_lo −0.0029) | +0.00145 | full_ridge, 12.4% |

**Every panel-1 interval contained zero. Every panel-2 best-arm interval
excludes it.** That is the change scale bought.

## 3. Z-labelling collapses the heteroskedastic world onto the dense one — exactly

The `linear_dense` and `linear_hetero` z-label rows above are not a copy-paste
error and not a duplicated run. They are **bit-identical across all 18 cached
fold series**, and necessarily so:

the hetero label is `sd_month × (0.03·zc + noise)`; per-date z-scoring divides
by that same within-month `sd`, so `z(y_hetero) ≡ z(y_dense)`. Identical
training target → identical model; and per-date Spearman is invariant to a
positive within-date scalar, so the scored IC coincides too. Meanwhile the RAW
arms differ sharply (hetero pooled full IC 0.0070 vs dense 0.0154), which is
what makes the identity meaningful rather than a sign the runs were the same.

The consequence is the finding: **every bit of the hetero world's extra
difficulty lives in the training objective, and z-labelling removes it
exactly** — recovery 4.8% → 12.6%, with the interval moving off zero.

Panel-1 asked precisely this question and could not answer it. Its own text:
*"if pooled raw-MSE is the binding constraint, the zlabel arms recover
materially more than the raw arms; if not, scale is the whole story."* At
panel-1's scale the z-label arms measured **+0.00008** — nothing. At panel-2's,
with the 1930s in the training window, they more than double the recovery.
**It was not "scale is the whole story". The objective was doing real damage,
and panel-1's window was too short to see it.**

## 4. What this licenses — and the trap in declaring it

The gate passes a world when the best full arm reaches `min_recovery × 0.03`
**and** its CI excludes zero. All three worlds now clear the second condition,
so the verdict reduces to one declared number:

> **PASS if and only if the prereg declares `min_recovery ≤ 0.126.`**

**That number must not be chosen because it passes.** It is being set after the
recovery is known, which is exactly the direction a bar drifts. The defensible
way to declare it is from what a null must be able to rule out: if the
instrument recovers fraction *f* of a planted effect and the trial's MDE is
*m*, a null bounds the true effect at roughly *m/f*.

| world | MDE | recovery | a null verdict bounds the truth at |
|---|---|---|---|
| linear (sparse) | 0.0050 | 45.4% | **0.011** — at the 0.01 economic bar |
| dense / hetero | 0.0053 | 12.6% | **0.042** — 4× the economic bar |

So: a TOURNAMENT-2 null would be **meaningful against a sparse effect and
close to vacuous against a diffuse one.** Real factor signal is diffuse. The
honest options are to declare that the trial only bounds sparse effects, or to
restore power against diffuse signal before registering.

**The concrete way to restore it is known.** Panel-1's best arm in *both* dense
worlds was `full_ridge` — a linear model, which is what a diffuse linear
carrier calls for and what a tree is worst at. Panel-2 omits it: a
4.16M × 412 float64 matrix does not fit beside a 6.9 GB panel on a 31 GB
machine. Panel-2's best-of-arms is therefore a **conservative floor** on the
instrument, and closing that gap (a memory-feasible linear arm, e.g. ridge by
normal equations on a 412×412 Gram matrix accumulated in chunks) is the
highest-value work before TOURNAMENT-2 is registered.

## 5. Caveats that travel with these numbers

- **Panel-2 changes four things at once** vs panel-1: scale (18×), universe
  (floored → all-cap), training era (2013+ → 1926+), and floor construction.
  The improvement belongs to the bundle, not to scale alone. Recorded in every
  receipt as `differs_from_panel1_by`.
- **`linear_hetero` is not the same world across panels.** It scales by the
  panel's *own* realised dispersion, so panel-2's version contains the 1930s
  and is genuinely **harder**. Its raw arm recovering less than panel-1's is
  therefore *not* evidence that scale hurt — the two numbers describe
  different worlds. The test suite excludes that pair from the like-for-like
  comparison and says why.
- Nothing here is market evidence. Every receipt is stamped
  `SENSITIVITY_WORLD`; the real label is destroyed before any arm sees it (the
  hetero world reads it only as a per-month volatility).

## 6. Engineering notes (paid for this session)

- **PS 5.1:** `2>&1` on a native exe wraps stderr lines as `NativeCommandError`;
  with `$ErrorActionPreference = "Stop"` python's first *warning* killed the
  detached run — silently, no traceback, no exit marker. Streams are now
  separated by `Start-Process -RedirectStandardOutput/-Error`.
- **Memory shaped the design.** Boolean-mask fold slicing copied 6.4 GB per
  fold beside a 6.9 GB panel; the machine paged and a 75 s fold took 15 min.
  The panel is sorted by `eom`, so folds are contiguous **views** — RAM
  14.4 → 9.75 GB, folds back to ~65 s. Verified **bit-identical** to the
  cached folds (`max|diff| = 0`) before reusing them.
- **A resumed run must be the same computation.** Fresh IC series carried
  `datetime.date` indices and cached ones `Timestamp`; a resumed run would
  have intersected them to *zero* dates and still written a receipt. Indices
  are normalised at the single point of creation, and `contrast()` refuses an
  empty overlap.
- Bash background waiters silently die above the 600 s timeout cap; use
  `Monitor` for longer waits.

## 7. State and next

Built: `aegis_panel2_spec.py` (instrument + `Panel2SpecRefused`, guard-contract
enrolled), `scripts/panel2_planted_worlds.py`, three committed receipts, 25
tests (`test_panel2_detectability.py`, `test_aegis_panel2_spec.py`) that are
CI-complete — they read the committed JSON and take the panel hash *from the
receipt*, because the 4.18 GB panel is gitignored.

Next, in order: **(a)** a memory-feasible linear arm, to stop panel-2's
best-of-arms understating the instrument in exactly the worlds that matter;
**(b)** TOURNAMENT-2's prereg, declaring `min_recovery` on the *m/f* reasoning
above rather than on what passes, and citing `spec_hash d58b6d0310008713`;
**(c)** the registered run, whose runner calls `assert_detectable` as its
opening act.
