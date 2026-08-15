"""N8 — how many independent affected episodes would resolve these mechanisms?

    python -m scripts.n8_required_corpus_size

WHY THIS COMES FIRST
====================
Every mechanism in the library is `NOT_DETECTABLE_IN_SCOPE` or
`UNPOWERED_IN_SCOPE`, and the honest reading of that is a statement about the
CORPUS rather than about de-risking. But "the corpus is too small" is not
actionable until it carries a number, and TRANSFER_ATLAS_V1 has been an
ambition rather than a specification for exactly that reason.

This turns the complaint into a target: given the effect actually observed and
the dispersion actually measured, how many INDEPENDENT affected episodes are
needed to see it at 80% power?

    n_required = ((Z_alpha + Z_power) * sd / d)^2

THE HEADLINE IS THE MEDIAN, DECLARED BEFORE RUNNING
====================================================
Taking the minimum across mechanisms would select the one with the largest
observed effect, which on `n_effective` between 1 and 12 is a maximum over
noisy draws — G1 one dimension along. The protocol fixes the median.

AND THE KILL CONDITION IS AIMED AT THE RESEARCH DESIGN
=======================================================
If the median exceeds 200 independent affected episodes, the conclusion is not
"collect harder". Roughly a dozen genuine US stress episodes exist in the
modern era; a handful more can be had internationally, and 2008 is in all of
them. A requirement of 200 would mean these mechanisms are **not resolvable by
episode collection at all**, and the question has to become cross-sectional —
where the sample is names rather than crises. That finding would outrank every
mechanism in the library, which is why it is declared in advance rather than
concluded reluctantly afterwards.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

from backend import config as _config
from backend.services.research_gym import power as PW

AUTOPSIES = _config.OPTIMUS_LEDGER_DIR / "research_gym"
OUT = AUTOPSIES / "n8_required_corpus.json"

#: Declared in the protocol. Above this, the answer is "change the question".
DESIGN_KILL_THRESHOLD = 200


def _latest_autopsy_file() -> Path | None:
    files = sorted(AUTOPSIES.glob("autopsies_*.jsonl"))
    return files[-1] if files else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--autopsies", default=None)
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args(argv)

    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                        # noqa: BLE001
            pass

    path = Path(a.autopsies) if a.autopsies else _latest_autopsy_file()
    if path is None or not path.exists():
        print("no autopsy file found")
        return 1
    print(f"reading {path.name}")

    rows = [json.loads(ln) for ln in
            path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    print(f"mechanisms: {len(rows)}")

    Z = PW.Z_ALPHA_TWO_SIDED_05 + PW.Z_POWER_80
    print(f"Z_alpha + Z_power = {Z:.4f}\n")

    per_cell: list[dict] = []
    for r in rows:
        sc = (r.get("adjudication") or {}).get("scoped") or {}
        mech = (sc.get("mechanism") or "")[:60]
        for slice_name, scopes in (sc.get("cells") or {}).items():
            aff = (scopes or {}).get("AFFECTED") or {}
            if not aff.get("ran"):
                continue
            n = aff.get("n") or 0
            d = aff.get("mean_pp")
            se = aff.get("se_pp")
            n_eff = aff.get("n_effective")
            if d is None or se is None or not n_eff or n_eff < 1:
                continue
            # sd implied by the SE that was actually used, so the requirement is
            # in the same units as the MDE the cell printed.
            sd = float(se) * (float(n_eff) ** 0.5)
            if abs(d) < 1e-9 or sd <= 0:
                continue
            need = (Z * sd / abs(d)) ** 2
            # ── THE REQUIREMENT'S OWN UNCERTAINTY (§37, applied to the kill) ─
            # `n_required` scales with 1/d^2, and `d` here is measured on
            # n_effective ~ 2. So the requirement inherits ALL of the effect's
            # uncertainty, squared and inverted. Reporting a single number
            # would be the same error as reporting an effect without an MDE:
            # a quantity with the shape of a bound and none of its meaning.
            #
            # `d_hi` is the optimistic edge of the effect's own 95% interval —
            # the largest effect this sample is consistent with — and gives the
            # SMALLEST corpus that could conceivably suffice.
            se_f = float(se)
            d_hi = abs(float(d)) + 1.96 * se_f
            need_lo = (Z * sd / d_hi) ** 2 if d_hi > 0 else None
            per_cell.append({
                "mechanism": mech, "slice": slice_name,
                "n": n, "n_effective": round(float(n_eff), 2),
                "effect_pp": round(float(d), 3), "sd_pp": round(sd, 3),
                "mde_pp": aff.get("mde_pp"),
                "n_required": round(need, 1),
                "n_required_optimistic": (None if need_lo is None
                                          else round(need_lo, 1)),
                "effect_upper_95_pp": round(d_hi, 3),
                "shortfall": round(need - float(n_eff), 1),
            })

    if not per_cell:
        print("no affected cells with a measured effect and dispersion")
        return 1

    print(f"{'slice':<22s} {'n':>4s} {'n_eff':>6s} {'effect':>8s} "
          f"{'d_hi95':>8s} {'sd':>8s} {'n_REQ':>9s} {'n_REQ@d_hi':>11s}")
    for c in sorted(per_cell, key=lambda x: x["n_required"]):
        lo = ("-" if c["n_required_optimistic"] is None
              else f"{c['n_required_optimistic']:11.1f}")
        print(f"{c['slice']:<22s} {c['n']:>4d} {c['n_effective']:>6.1f} "
              f"{c['effect_pp']:>8.2f} {c['effect_upper_95_pp']:>8.2f} "
              f"{c['sd_pp']:>8.2f} {c['n_required']:>9.1f} {lo:>11s}")

    reqs = sorted(c["n_required"] for c in per_cell)
    med = statistics.median(reqs)
    print(f"\ncells with a measurable requirement : {len(reqs)}")
    print(f"  min      {min(reqs):10.1f}")
    print(f"  median   {med:10.1f}   <-- the declared headline")
    print(f"  max      {max(reqs):10.1f}")
    print(f"  observed n_effective, median: "
          f"{statistics.median(c['n_effective'] for c in per_cell):.1f}")

    # ── THE RESTRICTION, AND WHY IT IS NOT RESULTS-DRIVEN ───────────────────
    # `n_required` is (Z * sd / d)^2, and BOTH sd and d are estimated from the
    # same handful of observations. On n_effective = 3 that ratio is not a
    # requirement, it is a coin: a cell that happened to draw a large effect
    # and a small dispersion reports that ONE episode would have sufficed,
    # which is arithmetic rather than statistics.
    #
    # The restriction is a-priori (you cannot estimate a dispersion from three
    # points) and not chosen from the answers, but it was NOT in the protocol,
    # so it is reported as a second number beside the declared one rather than
    # replacing it. Both are shown; neither is hidden.
    POWERED_MIN_N_EFF = 10.0
    powered = [c for c in per_cell if c["n_effective"] >= POWERED_MIN_N_EFF]
    if powered:
        p_reqs = sorted(c["n_required"] for c in powered)
        print(f"\nrestricted to cells that could ESTIMATE a dispersion "
              f"(n_effective >= {POWERED_MIN_N_EFF:g}): {len(powered)} cells")
        print(f"  min      {min(p_reqs):10.1f}")
        print(f"  median   {statistics.median(p_reqs):10.1f}   <-- post-hoc, "
              f"stated beside the declared number rather than replacing it")
        print(f"  max      {max(p_reqs):10.1f}")
    else:
        p_reqs = []
        print(f"\nNO cell reaches n_effective {POWERED_MIN_N_EFF:g}. Every "
              f"requirement above is computed from a dispersion estimated on "
              f"fewer than ten observations, in both directions.")

    # ── §37 APPLIED TO THE KILL ITSELF ─────────────────────────────────────
    opt = [c["n_required_optimistic"] for c in per_cell
           if c["n_required_optimistic"] is not None]
    med_opt = statistics.median(opt) if opt else None
    if med_opt is not None:
        print(f"\nIF the true effect sat at the OPTIMISTIC edge of its own 95% "
              f"interval, the\n  median requirement would be {med_opt:.1f} "
              f"episodes instead of {med:.1f}.")
        print(f"  Across cells the requirement spans {min(opt):.0f} to "
              f"{max(reqs):.0f} — a factor of "
              f"{max(reqs) / max(min(opt), 0.1):.0f}.")
        print("  n_required scales with 1/d^2 and d is measured on "
              "n_effective ~ 2, so the\n  requirement inherits the effect's "
              "whole uncertainty, squared and inverted.")

    # ── THE REFRAME THAT MAKES N8 ACTIONABLE ───────────────────────────────
    # Sizing a corpus from the effect you happened to measure is circular when
    # that effect is measured on two observations. The sizeable question is a
    # DECISION, not a measurement: how big an edge would we act on? Dispersion,
    # unlike the effect, IS estimated from all the data and is stable.
    print("\nDESIGN CURVE — corpus size implied by a DECLARED minimum effect "
          "of interest\n  (the honest way to size an atlas: the smallest edge "
          "worth acting on, not the\n   edge this sample happened to draw)")
    crisis_sds = sorted(c["sd_pp"] for c in per_cell if c["sd_pp"] > 5.0)
    calm_sds = sorted(c["sd_pp"] for c in per_cell if c["sd_pp"] <= 5.0)
    for label, sds in (("crisis slices", crisis_sds), ("calm slices", calm_sds)):
        if not sds:
            continue
        sd_med = statistics.median(sds)
        print(f"\n  {label}: median dispersion {sd_med:.2f}pp")
        print(f"    {'min effect of interest':>24s}   {'episodes needed':>15s}")
        for moi in (1.0, 2.0, 3.0, 5.0, 10.0, 20.0):
            print(f"    {moi:>21.1f}pp   {(Z * sd_med / moi) ** 2:>15.0f}")

    print(f"\nDECLARED KILL CONDITION: median > {DESIGN_KILL_THRESHOLD} "
          f"independent affected episodes")
    if med > DESIGN_KILL_THRESHOLD:
        print(f"  *** TRIGGERED at {med:.0f}. These mechanisms are NOT "
              f"resolvable by episode collection.")
        print("      Roughly a dozen genuine US stress episodes exist in the")
        print("      modern era and 2008 is in every other market too. The")
        print("      question has to become CROSS-SECTIONAL — sample = names,")
        print("      not crises. That is a finding about the research design.")
        verdict = "CHANGE_THE_QUESTION"
    else:
        print(f"  not triggered at {med:.0f}. A corpus of about "
              f"{med:.0f} independent affected episodes would resolve the")
        print("      median mechanism. That is TRANSFER_ATLAS_V1's target.")
        verdict = "COLLECTABLE"

    out = {"z_sum": Z, "cells": per_cell,
           "median_n_required": med, "min": min(reqs), "max": max(reqs),
           "powered_only_min_n_eff": POWERED_MIN_N_EFF,
           "powered_only_n_cells": len(powered),
           "powered_only_median": (statistics.median(p_reqs) if p_reqs
                                   else None),
           "median_n_required_optimistic": med_opt,
           "design_kill_threshold": DESIGN_KILL_THRESHOLD,
           "verdict": verdict}
    p = Path(a.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nwritten  {p}")
    print("Gym output. Cells are hypotheses, never claims (R2 wall 1).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
