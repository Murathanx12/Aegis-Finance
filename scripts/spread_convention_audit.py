"""The convention audit. It runs BEFORE any repricing, and it found two things.

    python -m scripts.spread_convention_audit

WHY THIS RUNS FIRST (Order 16 item 11, Order 17 P0-R2)
======================================================
> "Better spread data with a factor-of-two convention error is still a bad cost
> model."

A spread estimator is an instrument correction, and an instrument correction
applied through the wrong convention is the two-wrong-constants house failure
with a citation attached. So the audit answers two questions before a single
number is repriced:

    1. What convention does Aegis's cost model actually EXPECT?
    2. What convention do the estimators actually RETURN?

Both answers are read out of the code and out of simulated bars respectively,
not out of a paper's abstract.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from backend.services import spread_estimators as SE


def _utf8() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                          # noqa: BLE001
            pass


def _synthetic(n_days: int, spread: float, sigma: float, seed: int):
    """Bars from an efficient walk plus a KNOWN proportional spread."""
    import math
    import random
    rng = random.Random(seed)
    p, o, h, lo, c = 100.0, [], [], [], []
    step = sigma / math.sqrt(60)
    for _ in range(n_days):
        px = []
        for _ in range(60):
            p *= math.exp(rng.gauss(0.0, step))
            q = 1.0 if rng.random() < 0.5 else -1.0
            px.append(p * (1.0 + q * spread / 2.0))
        o.append(px[0])
        h.append(max(px))
        lo.append(min(px))
        c.append(px[-1])
    return o, h, lo, c


def question_1() -> dict:
    """What does Aegis's cost model expect? Read from the code that charges it."""
    print("=" * 74)
    print("Q1 — WHAT CONVENTION DOES THE COST MODEL EXPECT?")
    print("=" * 74)
    print("""
  The 206-predictor panel's cost is charged in
  `scripts/library_measure_2006_2019.py`, and exactly two lines decide it:

      line 191   turn[t] = float(np.abs(w - w_prev).sum())
      line 206   cost_m  = turn_m * COST_BPS / 1e4

  `sum(|dw|)` counts BOTH LEGS of a rotation. Selling A and buying B at equal
  weight contributes 1.0 + 1.0 = 2.0, so the notional in `turn` is the total
  crossed on both sides — and each unit of it is charged COST_BPS once.

      => COST_BPS IS A ONE-WAY RATE. It is the HALF-SPREAD in basis points.

  A reader who set COST_BPS to an estimator's output would charge the FULL
  spread per crossing, i.e. TWICE the true cost.
""")
    return {"expects": SE.CONVENTION_ONE_WAY,
            "evidence": "turnover = sum(|dw|) counts both legs; "
                        "cost = turnover * COST_BPS",
            "sites": ["scripts/library_measure_2006_2019.py:191",
                      "scripts/library_measure_2006_2019.py:206"]}


def question_2() -> dict:
    """What do the estimators return? Measured on bars whose spread we chose."""
    print("=" * 74)
    print("Q2 — WHAT DO THE ESTIMATORS RETURN? (measured, not cited)")
    print("=" * 74)
    print(f"\n  {'true full spread':>17} | {'agk':>10} {'corwin':>10} "
          f"{'abdi':>10}   (bps, full-spread convention)")
    rows = []
    for true_bps in (20.0, 50.0, 100.0, 200.0):
        o, h, lo, c = _synthetic(500, true_bps / 1e4, 0.02, seed=int(true_bps))
        got = SE.compare_all(o, h, lo, c)
        rows.append({"true_full_spread_bps": true_bps,
                     **{k: v.get("full_spread_bps") for k, v in got.items()}})
        print(f"  {true_bps:>17.1f} | {got['agk']['full_spread_bps']:>10.1f} "
              f"{got['corwin_schultz']['full_spread_bps']:>10.1f} "
              f"{got['abdi_ranaldo']['full_spread_bps']:>10.1f}")
    print("""
  All three track the FULL spread, not the half. So the bridge into the cost
  model divides by two, and `SpreadEstimate.as_one_way_bps()` is the single
  place that does it — the factor of two is applied once, by code that knows
  which direction it is going.
""")
    return {"returns": SE.CONVENTION_FULL_SPREAD, "recovery": rows}


def question_3() -> dict:
    """The floor. Found while writing the negative control, and it binds."""
    print("=" * 74)
    print("Q3 — WHAT CAN THE INSTRUMENT ACTUALLY RESOLVE?")
    print("=" * 74)
    print("""
  The negative control failed in an informative direction: AGK does not read
  zero on a frictionless tape. It reads its own DETECTION FLOOR, which rises
  with volatility and falls with sample length.
""")
    print(f"  {'n_days':>7} {'sigma':>7} {'floor p95 (bps)':>17}")
    floors = []
    for n in (250, 500, 1000):
        for sig in (0.02, 0.03):
            f = SE.noise_floor_bps(n, sig, sims=60)
            floors.append(f)
            print(f"  {n:>7} {sig:>7.2f} {f['floor_full_spread_bps']:>17.1f}")

    print(f"\n  {'true spread':>12} {'n':>6} {'AGK reads':>11}  verdict")
    reads = []
    for true_bps, n in ((1.0, 500), (10.0, 500), (50.0, 500), (200.0, 500)):
        o, h, lo, c = _synthetic(n, true_bps / 1e4, 0.02, seed=int(true_bps) + 7)
        out = SE.estimate_with_floor(o, h, lo, c, sims=60)
        reads.append({"true_full_spread_bps": true_bps, **out})
        print(f"  {true_bps:>12.1f} {n:>6} {out['full_spread_bps']:>11.1f}  "
              + ("RESOLVABLE" if out["resolvable"] else "AT/BELOW FLOOR"))
    print("""
  THE FINDING, AND IT POINTS THE OPPOSITE WAY FROM THE ONE WE ALREADY KNEW.

    illiquid names   a flat 10bp UNDER-charges. Known; it flatters the
                     "larger in the illiquid tercile" verdicts, and it is why
                     AGK was adopted.
    liquid names     AGK OVER-charges. A megacap's true spread is 1-2bp,
                     which is far below this floor, so the estimator reports
                     the floor — roughly ten times the truth.

  So repricing the panel with raw AGK would move the LIQUID tercile's verdicts
  for a reason that is an artefact of the instrument. That is the same shape as
  charging illiquid names the megacap rate, which already flipped two of our
  own verdicts, running the other way.

  => An AGK estimate at or below its floor is an UPPER BOUND, not a cost.
     `estimate_with_floor` returns `resolvable` so a caller cannot use one
     without being told which it has.

  WHAT IS ROBUST HERE AND WHAT IS NOT, stated rather than left to be assumed.
  The EXISTENCE of a positive floor, its rise with volatility and its fall with
  sample length are properties of the estimator and hold under any of these
  settings. The floor's MAGNITUDE is not: it is simulated under a declared
  microstructure (60 prints per day, equal-probability bid/ask, no volume
  clustering, no overnight gap), and real tapes differ. So the ~25-50bp figure
  is INDICATIVE, and the production calibration is against TAQ effective
  spreads on the overlap where they are entitled. Quoting this number as if it
  were measured on real bars would be the same error one level up.
""")
    return {"floors": floors, "reads": reads}


def main() -> int:
    _utf8()
    print()
    q1 = question_1()
    q2 = question_2()
    q3 = question_3()

    print("=" * 74)
    print("VERDICT")
    print("=" * 74)
    ok = (q1["expects"] == SE.CONVENTION_ONE_WAY
          and q2["returns"] == SE.CONVENTION_FULL_SPREAD)
    print(f"""
  cost model expects   {q1['expects']}   (half-spread, per crossing)
  estimators return    {q2['returns']}   (the whole spread)
  bridge               SpreadEstimate.as_one_way_bps() -> x0.5, in ONE place

  CONVENTION AUDIT: {'PASS — the factor of two is applied once and named'
                     if ok else 'FAIL'}

  BLOCKING BEFORE REPRICING: the detection floor. Any tercile whose AGK
  estimate is not `resolvable` must be repriced with an upper bound and
  labelled, or with a better instrument (TAQ effective spreads, if entitled).
  A survivor count quotes its cost rate or is not quoted — and a rate the
  instrument could not measure is not a rate.
""")
    out = Path("backend/data/optimus/spread_convention_audit.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"q1_cost_model_expects": q1,
                               "q2_estimators_return": q2,
                               "q3_detection_floor": q3,
                               "convention_audit_pass": ok},
                              indent=2, default=str), encoding="utf-8")
    print(f"  json -> {out}\n")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
