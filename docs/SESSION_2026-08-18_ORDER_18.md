# SESSION 2026-08-18 — Order 18: the cost ruling, and the afternoon until the night

Five items, all delivered. Commits `2f4a048` · `c2a85f2` · `915d8b9` ·
`f4fc6fc`, plus `a2de98b` in the `Aegis module` sibling.

---

## §1 — the cost ruling, implemented as a type

`backend/services/cost_model.py`. A name is segmented by whether AGK clears its
OWN measured floor:

| branch | what the caller gets |
|---|---|
| AGK resolves (illiquid / small) | `OneWayBps(..., MEASURED_AGK)` |
| AGK cannot resolve (liquid) | a `CostBand` of 1–5bp, `DECLARED_CONSERVATIVE` |

The estimate is **absent, not the floor**. A verdict that survives both ends of
the band is a verdict; one that flips inside it is `COST_MODEL_SENSITIVE`,
which is a reportable result — it says the data cannot answer the question at
this cost resolution.

Three things make that stick rather than being a convention:

- `CostBand` has **no `.value` and no `__float__`**, so it cannot be collapsed
  to a number by accident.
- `resolve_band_by_picking()` exists as a **named refusal**, in the obvious
  place, so its absence cannot read as an oversight to the next person who
  goes looking for it.
- `verdict_across_band()` **refuses a bare float** — a float carries no
  provenance, and one call downstream a declared number and a measured one are
  the same object.

**TAQ is `UNVERIFIED`, not absent.** It is not on the WRDS entitlement record
and nobody has tried. `calibrate_agk_against_taq()` refuses on the ground that
*the check has not run*, which is a different statement from "we do not have
it" — the WRDS route was declared dead for weeks when the real blocker was port
filtering. Ten-minute attended item; if it resolves, AGK calibrates on the
overlap and the band retires.

`COST_BPS` → **`COST_BPS_ONE_WAY`** across the 12 files that declare it.

---

## §2 — INSTRUMENT-FLOOR-SWEEP-1 (the afternoon's novel method)

`backend/services/instrument_floor.py`, `scripts/instrument_floor_sweep.py`,
`docs/INSTRUMENT_FLOORS.md`. Ten instruments, each handed synthetic data whose
answer is declared, then asked four questions: what does it read when the
quantity is ABSENT · what is the smallest truth that escapes that null band ·
what is the bias inside the range · how much data before it stabilises.

**The shelf is worse than the finding that started it.**

| | detection floor | resolves from |
|---|---:|---:|
| `agk_edge_spread` | 32bp | 50bp |
| `abdi_ranaldo_spread` | 66bp | 100bp |
| `corwin_schultz_spread` | 79bp | 50bp, at **1.74× truth** |
| `roll_spread` | **280bp** | **400bp** |

- **Roll cannot resolve any spread below 400bp**, and it feeds the liquidity
  score. The spread estimators differ by **9×** in what they can see, so the
  AGK supersession is now *measured* rather than cited.
- **The absorption ratio reads 0.42 on completely independent assets.** Its
  null is k/n plus sampling bias, so the LEVEL carries no information about
  coupling — a report saying "absorption 0.42, markets tightly coupled" is
  reading noise. Its *changes* resolve from a 0.05 factor share, so the usable
  statistic is the movement, never the level.
- **`realized_vol` is the control**, with no floor. Without one, a sweep that
  finds a floor everywhere cannot be told from a harness that manufactures
  them.

`guard_reading()` refuses with `UNRESOLVABLE_FOR_INPUT` rather than returning
the floor, and refuses a profile measured at a different `n` rather than
interpolating.

**The harness corrected me while it was being built.** I wrote a test asserting
that an instrument reading `truth + 3` has a detection floor of 3. It does not:
a deterministic offset is **bias**, which you can subtract. A floor comes from
the **variance** of the null reading. Both are now controls in the test file,
because the two need opposite remedies — recalibrate versus replace — and AGK's
is the second kind, which is why it cannot be calibrated away.

Every floor is a **lower bound**: the synthetic microstructure omits volume
clustering, gaps, time-varying spreads and informed flow, and each omission
flatters the instrument.

---

## §3.1 — the minimum-meaningful-Brier declaration (DRAFT, awaiting signature)

`docs/DECLARATION_IIF1_MINIMUM_MEANINGFUL_BRIER.md`.

The bar is a fraction of each cell's **own** uncertainty `p(1-p)`, because the
two registered cells have base rates 9.7% and 19.6%; one raw-Brier bar across
both would silently be 80% stricter in the first. The same argument that
forbids one pooled MDE forbids one pooled bar.

Running §64 forwards produced the finding the declaration exists to surface:

> **At `BAR = 0.10`, the `h=1 | thr=0.03` cell needs 58 nights. The 40-night
> read CANNOT detect the smallest difference that would matter.** It resolves
> at 80. The `h=5 | thr=0.05` cell needs 38 and resolves at 40.

Declared now, that cell returns a clean **NOT ESTABLISHED** at 40. Discovered
after the read, it is an argument. The recommendation is 0.10, argued against
the alternatives: 15% and 20% are detectable *because they are large*, which is
a bar chosen so the instrument can clear it; 5% needs 152–231 nights, which
pre-announces a null.

MDEs are quoted at the **measured** ρ (0.0737 / 0.0613, design effect 3.88 /
3.39), not the ρ=0 floor the power report prints — the floor would have made
both cells look answerable at 40.

---

## §3.2 — the Thursday dress rehearsal (RAN, exit 0)

`scripts/dress_rehearsal_0821.py`. Four stages that had each been tested and
had never met: resolve → receipt → grader → paired read with BSS and Murphy.

- **396 records come due on 08-21.** A dry run today says 201, so Thursday's
  load is nearly double what today would suggest.
- 0 unpriceable, 0 overdue on synthetic prices.
- The rehearsal receipt goes to a workdir and **not** `docs/receipts/` — a
  rehearsal receipt filed with the real ones is a future misreading.
- **The safety property is checked, not promised**: the real ledger is hashed
  before and after and the rehearsal fails if they differ. "It used a copy" is
  a claim about what the code does; the hash is a claim about what happened.

**What it does not prove:** that Thursday's prices will be fetchable. Synthetic
prices cannot fail to fetch.

---

## §3.3 — LANE-AUTOPSY-1++: the gap is weights, and it is not HRP

`backend/services/lane_autopsy.py`, `scripts/lane_autopsy_run.py`. The replay
reconstructs a **+14.99%** gap (mirror +14.08%, conviction −0.91%) — within a
point of the reported 14.

| mechanism | marginal | leave-one-out | interaction | separable |
|---|---:|---:|---:|:--:|
| weights | +10.65% | +15.08% | +4.43% | NO |
| cadence | +1.63% | −0.25% | −1.88% | NO |
| drift_trigger | +0.43% | +3.06% | +2.63% | NO |
| caps | +0.00% | +0.00% | +0.00% | **INERT** |
| sum of marginals | +12.71% | | residual **+2.28%** (15% of the gap) | |

1. **The gap is weights, and the weights are not HRP.** The mirror lane's HRP
   gate needs 252 observations; this window has 48, so every rebalance ran the
   lane's own loud fallback to **equal weight**. The finding is therefore not
   "HRP works" — it is *"equal-weighting these twelve names beat the actual
   share counts by 11–15 points in ten weeks"*, which is a statement about
   concentration in the conviction book, not about an optimiser.
2. **The 25% cap is a dead branch.** Max seed weight is 22.89% and equal weight
   over 12 names is 8.3%, so it cannot bind on either side. Flagged `INERT`,
   because "tested and immaterial" is a much stronger claim than "never ran".
3. **Not additive.** Marginals sum to 12.71% against a 14.99% gap. The residual
   and every marginal-vs-leave-one-out disagreement are printed rather than
   forced to add up; forcing them would be the Brinson interaction error.

**The tests found a real bug in the cap code.** `n` names capped at `c` with
`n*c < 1` has no feasible weight vector, and the naive iteration does not fail
— it **oscillates** and returns whichever violating vector it stopped on, which
looks exactly like a converged answer. It now refuses. The live lane is
feasible (12 × 25% = 3.0), which is precisely why it would have gone unnoticed
until a lane with fewer names met it.

**Descriptive only.** Nothing seeded, no flag flipped, no `paper_nav` row,
nothing annualised. The replayed NAV is a **reconstruction**; the recorded
`paper_nav` in production is the authority, and reconciling them is an attended
lane-integrity item.

---

## §3.4 — AEGIS-NET-TOURNAMENT-1 pre-registration (DRAFT, awaiting signature)

`Aegis module/TRIALS/PREREG_AEGIS_NET_TOURNAMENT_1.md` @ `a2de98b`.
`lint_prereg`: **PASS** vs 342 prior experiments.

**The corpse is named: G5** — a learned conditional *shape* adds nothing even
given an oracle scale, three receipts, all negative. **The new instrument is
the OUTCOME, not the model.** Every G5 receipt graded against a directional
target where this engine measures AUC 0.497–0.509. Run on a sign target this is
G5 for a fourth time and the answer is already known. The heads here are rank,
quantile, magnitude, drawdown and competing barriers, none of which reduce to
sign.

Honest prior on H1: **LOW**. The second declared outcome is *"the shape is
linear; spend the next dollar on scale, coverage and cost"*, in those words.

The linter refused twice before passing, and both refusals were right:
`MISSING_POWER_FIELDS` (R13), then `UNDECLARED_SLICE_PURPOSE`. Adding the power
block produced a number worth having before any model is fitted —
**n_required 196, n_available 454, smallest resolvable effect 0.66pp** against a
declared 1.0pp bar, i.e. the panel must span ~16 years or the trial returns NOT
ESTABLISHED by construction.

---

## §3.5 — write-only telemetry: 167 fields written and read by nothing

`scripts/write_only_telemetry_audit.py`, `docs/WRITE_ONLY_TELEMETRY.md`.

806 record fields examined. **167 WRITE_ONLY**, **31 TEST_ONLY** (only the test
that asserts they were written reads them — which proves the writer works, not
that anything consumes it). **19 write-only on the live IIF-1 surface**,
including `actual_finish_utc` (a clock) and `finished_before_open` (a safety
property recorded and checked by nothing).

**The audit hid its own motivating case on the first run.** At
`--min-occurrences 2`, `decision_lag_minutes` was silently excluded — it
appears on exactly one receipt. A threshold that excludes the case the tool was
built for is a threshold chosen against the wrong world. Default is now 1,
every exclusion is named rather than dropped, and the field is pinned as a
**canary**: the run exits 2 if the audit can no longer see it.

The canary validates the read side too: `decision_lag_minutes` now reports
`read` at 16 production mentions, because the launcher wires it into
`derive_assembly_allowance_minutes`. The audit can tell a wired field from an
inert one, which is the only reason to believe the other 167.

---

## Owed, and by whom

**Murat, attended:**
- Sign the Brier declaration (before Thursday).
- Sign or amend the NET tournament pre-registration.
- **The TAQ entitlement check** — ten minutes; it decides whether the declared
  cost band retires.
- Launch Night 2 at 17:00 today; `--dry-run` immediately before.
- Thursday: the real resolve run, ~396 records.
- Friday: arm the launcher after 3/3 scheduled receipts.

**Still open in code:**
- The 167 write-only fields each need wire-up-or-delete.
- Roll's 280bp floor is not yet wired to a refusal at its call sites in
  `liquidity_risk`; the sweep names it, the guard is not yet installed there.
- The lane replay has not been reconciled against production `paper_nav`.
