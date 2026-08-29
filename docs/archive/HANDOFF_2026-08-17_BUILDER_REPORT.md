# BUILDER REPORT — against Order 5 and its review

```
written_at:     2026-08-16
target_session: 2026-08-17
spend:          $0.00 (no paid API calls)
tests:          4370 passed, 14 skipped, 0 failed (fast suite)
pushed:         NO — a push redeploys; that is Murat's call
```

Results first, plumbing after.

---

## 1. Two registered priors, both refuted by the data

This is the headline, because both were written down before the run and both
were wrong in a direction I would not have conceded afterwards.

### N20 — the conditional `μ_rest` lever is closed, and it moved the wrong way

Order 5 named `μ_rest | fire` "the most decision-relevant unmeasured number in
the programme". It is now measured.

| | 20d | 60d |
|---|---|---|
| `μ_rest` unconditional (what N4B used) | +2.158% | +4.742% |
| **`μ_rest \| fire`** | **+2.356%** | **+5.001%** |
| difference | **+0.198pp** | **+0.259pp** |
| `L_min` | 1.6906 → **1.8121** | 2.1065 → **2.1945** |

**I predicted the difference would be negative.** The rescue needed −0.642pp at
20d; it measured +0.198pp. `L_min` moves **away** from N9's 1.271, not toward it.

Economically this reads cleanly: the precursors fire in high-volatility states,
and high-volatility states that do **not** produce a tail are the ones that
rebound hardest. De-risking on a firing day forgoes *more* than an average day,
not less.

**Registered verdict: `NOT_DETECTABLE_IN_SCOPE`** in every cell — the slice
cannot resolve 0.642pp (honest MDE 0.895–1.306pp). So this is "no support, and
the wrong sign", not a refutation. I did **not** substitute the more flattering
registered three-way rule (which would have read `REFUTED_IN_SCOPE` /
`NOT_RESOLVED` per cell) after seeing the answer.

**Consequence for Order 5 §1:** of the three levers that could rescue N4B as a
de-risking trigger, the estimand lever is closed. **Hedging (convex payoff) and
the objective survive.**

### WM0/WM0B — the world model is worse than cheap volatility scaling

G5's first training receipt. 92,988 out-of-sample observations, 21 annual
walk-forward folds, 40-day embargo, 18 ETFs.

| model | mean pinball | vs comparator |
|---|---|---|
| **WM0** (level space) | 1.22617 | **−6.17%** |
| **WM0B** (standardised) | 1.25235 | **−8.44%** |
| climatology | 1.18958 | −3.00% |
| gaussian_vol | 1.15895 | −0.35% |
| `scaled_empirical` *(comparator of record)* | 1.15492 | — |

Both are powered negatives: WM0 CI [+0.055, +0.089] with MDE 2.48%; WM0B CI
[+0.077, +0.119] with MDE 3.06%. Both are beaten by climatology, which knows
nothing about today.

**I predicted WM0B would beat WM0 substantially.** It was worse. And the reason
that matters is the diagnostic that came free:

```
tau      0.05   0.10   0.25   0.50   0.75   0.90   0.95
WM0     0.087  0.139  0.271  0.476  0.691  0.839  0.900
WM0B    0.091  0.144  0.272  0.478  0.692  0.842  0.901
target  0.050  0.100  0.250  0.500  0.750  0.900  0.950
```

Two radically different parameterisations — one re-deriving scale from
features, one handed scale for free — miss by the same amount in the same
direction, to within 0.005 at every quantile. **The fault was never the target
space.** WM0's committed explanation ("cannot extrapolate to volatility outside
its training range") is dead: WM0B removed exactly that handicap and got worse.

The remaining shared component is the estimator: LightGBM quantile regression
at `min_child_samples=200` on a low signal-to-noise target shrinks extreme
quantile fits toward the conditional median, so both distributions come out
**too narrow at both ends**.

**Kept apart deliberately:**

- **Established, twice, powered:** learned quantile regression *as configured*
  does not beat cheap volatility scaling.
- **NOT established:** that conditional shape does not exist. Both arms share
  one estimator and one regularisation, and the calibration signature points at
  that shared component rather than at the world.

**No WM0C.** The prereg budgeted two attempts and said a third without a new
reason derived from measurement is fishing. There is now a new reason — the
estimator confound — so it is the next session's registered trial, named, not a
third fit tonight.

---

## 2. The instrument finding: R13 passed a design its own data cannot resolve

Worth more than N20 itself.

R13's linter passed N20 at a claimed floor of **0.46pp** against a declared
effect of 0.642pp. The block bootstrap's honest MDE was **0.895–1.306pp**. The
declared effect sat *between* them, which is exactly how an underpowered design
was registered as powered.

The first error was mine: R13's docstring asks for `event_frequency_per_year`
"counted as INDEPENDENT episodes, not days", and I declared 40.3 — the rate the
precursor fires on **days**. But a field whose correctness is entirely on the
honour system, inside a gate whose purpose is to stop an author fooling
themselves, is not a guard. It fooled its own author.

**R13b** (`Aegis module` @ `a0ef261`) is the arithmetic that catches it without
touching data: at a 20-day outcome only `252/20 = 12.6` non-overlapping episodes
fit in a year, so a declared 40.3 is *proof* the episodes overlap.

| | before | after |
|---|---|---|
| n_available | 1451 | **454** (capped) |
| resolvable floor | 0.46pp | **0.816pp** |
| verdict | RESOLVABLE | **UNPOWERED_AT_REGISTRATION** |

The cheap registration-time number (0.816pp) lands next to the expensive
after-the-fact bootstrap (0.895pp at the tightest block), which is the only
reason to trust it.

**This is §41 (`n_effective = n`) recurring inside the gate built to prevent
§41, and inverted** — there it manufactured false kills, here false passes.
**Every R13 pass on an overlapping or cross-sectionally pooled outcome since
the gate shipped is suspect.**

WM0's prereg is the first to declare `outcome_horizon_days`, so R13 scored it on
265 independent windows rather than 92,988 overlapping rows.

---

## 3. The four review corrections, applied

Order 5 amended in place at `acf6212`, with a §0 recording each weakening so it
is visible rather than silent.

1. **"δ cancels" scoped** to linear exposure + proportional cost. Decisive
   against Order 4 §3 as written; it does **not** show partial sizing is
   equivalent under compounding, non-linear impact, leverage limits, utility
   curvature or option hedges. The conclusion is not "sizing is irrelevant" but
   **"the tail-coverage algebra cannot tell you whether sizing helps."**
2. **OptionMetrics reworded and measured** — see §4.
3. **N9B labelled** a post-confirmation adaptive comparison on a spent slice.
   Its paired differences and equivalence result stand as evidence; the
   independent-confirmation status does not.
4. **The log-growth/N12 causal claim withdrawn** — an explanation formed after
   seeing N12, whose own matched-vol log-wealth comparison was
   `NOT_DETECTABLE_IN_SCOPE`, so it cannot support a causal claim about itself.

Provenance (`written_at` / `target_session`) is now explicit in the header.

---

## 4. OptionMetrics: measured, and the scope limit is real

Entitlement and acquisition were **never** the blocker — 23 files, 191.7 MB,
on disk since 2026-08-01. The registry line saying otherwise was false and is
corrected (`8d8e915`).

The earlier caveat inferred "not daily" from ~87 rows/secid-year. That route is
invalid — **row count cannot identify sampling frequency** when each date
carries many surface coordinates. Measured instead:

| property | measurement |
|---|---|
| dates/year | **exactly 12**, every year 2002–2024 |
| median gap | **31 days** — every date a month end |
| coordinates per secid-date | **8**: `days ∈ {30,91}` × `delta ∈ {±25,±50}` × `cp ∈ {C,P}` |
| rows/secid-year | 96 = 12 × 8, *not* 96 observations |
| IV nulls | 4.4% → 6.5% |

`vsurf_me` is a **month-end** standardised surface, complete at every date.

**The consequence changes §3's plan:** it cannot be the forward rung of the
*daily* ladder — N11's rv20/EWMA/HAR update daily and a month-end reading
cannot meet them at daily decision points. It defines its **own monthly
ladder**. 276 month-ends per security across thousands of securities is ample
for the level-accuracy metrics §3 demands, `days ∈ {30, 91}` maps onto the
20d/60d horizons already in use, and the ±25/±50 deltas give the skew rung free.

**PIT is NOT cleared** and is recorded as not cleared.

---

## 5. Three corrections that had to be code

`8d8e915`, `4c16fdf`.

- **The ex-post guard.** `ExPostScale` is deliberately **not a number** — no
  `__mul__`, no `__float__`, no `__array__` — so `exposures * scale` raises
  from numpy at the point of use. It immediately found two leaks I had not
  looked for: the print format and the `vol_match_scale` ledger field, both
  handing the hindsight number onward as an ordinary float. 10 tests, including
  a repo-wide check that no other script recomputes `ref_vol / pv` inline.
- **The G3 units mismatch, fixed.** Selection and measurement now take the same
  argument and cannot diverge; `regret_units()` prints beside the number. Note
  the review was right that "silently sorts" was too strong — the default was
  documented and named. The accurate remaining defect is that **raw return is
  still the operational default**, and that one is open.
- **The four personalities exist.** `PRESERVATION / BALANCED / AGGRESSIVE /
  EXTREME_GROWTH`, one function, exported as `PERSONALITIES`. Declared honestly
  as a preference **ladder**, not elicited: the ordering is the content, the
  lambdas are conventions awaiting Murat's actual risk preference.
- **The slice register.** Identity is universe × period × outcome × cutoff, and
  reuse is caught by **overlap** — nudging the window five months mints a new
  `slice_id` and is still refused. `CONFIRM` on touched data requires a
  `REANALYSIS`/`PAIRED` declaration that **costs the confirmation claim**.
  Seeded from real history (N9 CONFIRM, N9B PAIRED). `unread_candidates` names
  10 untouched names from a 16-name pool.

---

## 6. What I did not do

- **Not pushed.** Everything is committed locally.
- **The direct policy-utility test** `U(precursor sizing) − U(baseline)` did
  **not** run. It needs a fresh slice, and the register now proves the
  confirmation slice is spent twice. It is the top of the next session and the
  register names where it can run cleanly.
- **The prereg linter does not yet require a declared slice**, so the register
  still depends on a trial choosing to call it. WM0 calls it; nothing forces it.
- **The vol ladder's loss metrics** (QLIKE / MZ / tail error) are not added.
  WM0/WM0B partly pre-empt this — pinball loss and PIT calibration are level
  metrics on the same question — but the rungs N11 compared have not been
  rescored.

---

## 7. Recommended order for the next session

1. **Direct policy utility on a fresh registered slice.** The algebra has now
   said everything it can; N20 closed its last estimand lever.
2. **WM0C with the estimator confound named** — the calibration signature is a
   specific, falsifiable hypothesis about shrinkage, not a fishing licence.
   Vary regularisation and a distributional head; keep metric and comparator
   frozen so all three runs stay comparable.
3. **The monthly implied-vol ladder**, at its true frequency, with level losses.
4. **Make the slice claim mandatory at registration**, so the register is a gate
   rather than a courtesy.
5. **Re-check R13 passes granted before `a0ef261`** — any trial with an
   overlapping or pooled outcome may have been registered on an optimistic floor.
