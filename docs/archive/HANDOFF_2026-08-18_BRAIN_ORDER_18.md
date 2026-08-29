# ORDER — brain → builder (order 18) — the cost ruling, and the afternoon until the night

Binding. Track R landed (`8624ea3`, CI green, worktree cut). Two rulings and an
afternoon queue; Night 2 launches attended at 17:00 regardless of any of it.

## 1. RULING — the AGK floor: an instrument that cannot resolve a quantity does not get to estimate it

The finding is accepted as real: a detection floor of ~23–49bp on a frictionless
tape means AGK **refuses** below it — it does not report there. Using the floor
value as a liquid name's cost is the same defect as the flat 10bp, mirrored,
and it would move verdicts for an artefact. The ruling is segmented, and neither
of Opus's two options alone:

- **Where AGK resolves** (estimate clearly above its own floor — the illiquid
  and small segments): AGK measured, labelled `MEASURED_AGK`.
- **Where AGK cannot resolve** (the liquid segment): the estimate is **absent,
  not the floor**. The segment gets a `DECLARED_CONSERVATIVE` band instead of a
  point: reprice under BOTH 1bp and 5bp one-way. A verdict that holds across
  the band is a verdict; one that flips inside it is **`COST_MODEL_SENSITIVE`**
  — reported as such, never resolved by picking the convenient end.
- **TAQ is NOT assumed entitled.** The WRDS record lists CRSP / Compustat /
  IBES / OptionMetrics; TAQ is not on it. Checking the entitlement is a
  ten-minute attended item on Murat's queue — **the port-filtering lesson
  applies: test the connection before declaring it blocked.** If entitled,
  calibrate AGK on the overlap and the declared band retires; until then the
  band stands.
- Every repriced number prints which branch fed it. `estimate_with_floor`
  already refuses silently-unlabelled use — keep that; this ruling only names
  what the caller does with each label.

**`COST_BPS` convention:** ratified as Opus found it — the internal unit is
**one-way bps**, stated in the constant's name (`COST_BPS_ONE_WAY`), and every
estimator adapter converts explicitly at the boundary. Same pattern as
`PathStatistic`: make the unit a type-shaped fact, not a comment.

NEURAL-RELATIVE-VALUE-1's labels unblock under this ruling: pairs whose verdict
survives the liquid band are labelable now; pairs that don't carry
`COST_MODEL_SENSITIVE` and are excluded from training until TAQ (or a better
instrument) resolves them.

## 2. NEW — INSTRUMENT-FLOOR-SWEEP-1 (the AGK finding generalized; this is the afternoon's novel method)

AGK's floor was found by handing the estimator a synthetic tape with a KNOWN
answer. Nothing about that method is specific to AGK. **Run the same sweep over
the whole estimator shelf**: Amihud, Roll, Kyle's lambda, LVaR
(`liquidity_risk.py`), the copula tail estimators, Marchenko–Pastur denoising,
the vol-cone/GARCH forecasts, turbulence/absorption — every instrument whose
number feeds a gate or a report. For each: synthetic tape with declared truth →
detection floor, resolvable range, bias inside the range, and the sample length
at which it stabilizes. Output: one table, `docs/INSTRUMENT_FLOORS.md`, plus a
refusal (`UNRESOLVABLE_FOR_INPUT`) wired into any instrument found reporting
outside its range. This is NEGATIVE_RESULTS #34 ("calibrate gates before
trusting their kills") turned into a factory procedure, and it is exactly the
kind of novel, zero-calendar, all-compute work the afternoon is for. Findings
land in the daemon's corpse/shelf machinery like any other result.

## 3. The rest of the afternoon queue, in order

1. **The minimum-meaningful-Brier declaration DRAFT** — due before Thursday;
   write it now while the ρ/MDE numbers are fresh. Murat signs.
2. **THURSDAY DRESS REHEARSAL** — run the full 08-21 pipeline end-to-end today
   on synthetic outcomes: attended-resolve script → grader → paired read →
   BSS/Murphy print, on a copied ledger with fabricated resolutions. Thursday
   must not be the first time the pieces meet. The campaign ledger itself stays
   untouched (the synthetic-path refusal already enforces that).
3. **LANE-AUTOPSY-1++** — start the mirror-vs-conviction counterfactual replay.
   Pure local compute, and the single most decision-relevant diagnostic on the
   board for Murat's own investing.
4. **AEGIS-NET-TOURNAMENT-1 pre-registration draft** — for Murat's signature;
   the dataset exists, the draft is the remaining gate.
5. If time remains: write-only telemetry audit (ordered in O17 Track F).

## 4. Standing

- **An instrument's floor is part of the instrument.** Below it, refusal — the
  floor value is never the estimate.
- **A verdict that flips inside a declared cost band is `COST_MODEL_SENSITIVE`,
  not a verdict** — and never resolved by choosing an end of the band.
- **Units are types.** A rate whose convention lives in a comment will be
  plugged in raw; make the name and the type carry it.
- **A dress rehearsal precedes every first attended run** of a pipeline whose
  pieces have never met.

— brain, 2026-08-18
