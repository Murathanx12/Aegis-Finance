"""M4-SELECTOR: what 2006-2019 chose, and whether the reserved window can judge it.

    python -m scripts.m4_selector_prereg

THE SEQUENCE THIS IS TRYING NOT TO REPEAT
=========================================
N9 selected on a calendar, confirmed on the same calendar with different
securities, and produced a 1.271 that had to be withdrawn ten sessions later
when the split at the selection boundary showed 1.464 overlapping against 0.765
disjoint. The register had the wrong axis; the confirmation was never clean.

So this time the order is inverted. The selection window was registered EXPLORE
and the confirmation window reserved DISJOINT **before the first return was
computed**, and this script does the step that N9 never got: it asks whether
the reserved window can actually resolve what the selection produced, BEFORE
spending it.

WHY THAT QUESTION HAS TO COME FIRST
===================================
S19 says an arm below its own MDE is not detectable and never a kill. Run
forwards, that is a budgeting rule: a confirmation whose MDE exceeds the effect
it is testing cannot return anything except "not established", whatever the
world does. Spending an irreplaceable window on a test with that property is
strictly worse than not spending it, because afterwards the window is gone AND
nothing was learned.

The power computation here uses only the selection window's standard error and
the NUMBER OF MONTHS in the confirmation window. Both are free: a count of
months on a calendar is not an outcome, so nothing is consumed by asking.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from scripts.library_measure_2006_2019 import COST_BPS, OUT

# ── THE SELECTION RULE, DECLARED. ──────────────────────────────────────────
# Frozen before it was applied. Every clause is a policy statement rather than
# a threshold tuned to produce a non-empty answer, and the run below reports
# what it selects even when that is nothing.
RULE = {
    "1_survives_screen": "survives BH-FDR at q=0.10 over the 206 tests run",
    "2_positive_in_liquid": "net annual > 0 inside the LIQUID dollar-volume "
                            "tercile — S62: an effect that is not reachable "
                            "is not a strategy",
    "3_detectable_in_liquid": "|net annual| >= its own 80%-power MDE in that "
                              "tercile, tested on NET because net is the claim",
    "4_cost_margin": f"break-even >= 3x the assumed {COST_BPS:.0f}bp/crossing, "
                     f"so the choice does not hinge on the cost model being "
                     f"right",
    "5_sign_intact": "the sign agrees with the publication; an inverted sign "
                     "is a different hypothesis, not this one",
}

#: The reserved confirmation window and what is actually covered by PIT-clean
#: data today. The gap is a fact about our extraction, not about the calendar.
CONFIRM_START, CONFIRM_END = "2020-06-01", "2026-07-17"
MONTHS_RESERVED = 74
MONTHS_AVAILABLE_NOW = 55          # CRSP monthly panel currently ends 2024-12

REPORT = Path(r"C:\Users\mrthn\Aegis module\data\library\report_2006_2019.json")
DOC = Path("docs/M4_SELECTOR_PREREG_2026-08-17.md")


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                        # noqa: BLE001
            pass

    meas = json.loads(OUT.read_text(encoding="utf-8"))["results"]
    rep = json.loads(REPORT.read_text(encoding="utf-8"))
    terciles = {r["predictor"]: r for r in rep["terciles"]}

    print("=" * 74)
    print("M4-SELECTOR — the rule, then what it selected")
    print("=" * 74)
    for k, v in RULE.items():
        print(f"  {k:<24} {v}")

    selected, rejected = [], []
    for name, t in terciles.items():
        m = meas.get(name, {})
        why = []
        if not (t["liquid"] is not None and np.isfinite(t["liquid"])
                and t["liquid"] > 0):
            why.append("not positive in the liquid tercile")
        if not t["liquid_detectable"]:
            why.append("below its own MDE in the liquid tercile")
        be = m.get("breakeven_bps")
        if be is None or not np.isfinite(be) or be < 3 * COST_BPS:
            why.append(f"break-even {be:.1f}bp < 3x cost" if be is not None
                       else "no break-even")
        if (m.get("net_annual") or 0) < 0:
            why.append("sign inverted vs publication")
        (selected if not why else rejected).append((name, t, m, why))

    print(f"\n  candidates entering the rule   {len(terciles)}  "
          f"(the FDR survivors)")
    print(f"  SELECTED                       {len(selected)}")
    for name, t, m, _ in selected:
        print(f"    {name:<20} liquid net {100 * t['liquid']:+.2f}%  "
              f"MDE {100 * t['liquid_mde']:.2f}%  "
              f"break-even {m['breakeven_bps']:.0f}bp")
    print(f"  rejected                       {len(rejected)}")
    for name, t, m, why in rejected:
        print(f"    {name:<20} {'; '.join(why)}")

    # ── can the reserved window judge them? ────────────────────────────────
    print("\n" + "=" * 74)
    print("CAN THE RESERVED WINDOW RESOLVE THIS? (asked BEFORE spending it)")
    print("=" * 74)
    print(f"  reserved   {CONFIRM_START}..{CONFIRM_END}  "
          f"= {MONTHS_RESERVED} months")
    print(f"  PIT-clean data available today  = {MONTHS_AVAILABLE_NOW} months "
          f"(CRSP monthly ends 2024-12)")
    print(f"\n  {'candidate':<20} {'effect':>9} {'MDE@74':>9} {'MDE@55':>9}"
          f"   verdict")
    rows = []
    for name, t, m, _ in selected:
        eff = t["liquid"]
        mde_sel = t["liquid_mde"]
        n_sel = t["liquid_n_months"]
        # The SE scales as 1/sqrt(months); the MDE scales with it. Nothing here
        # touches the confirmation window's returns.
        mde74 = mde_sel * np.sqrt(n_sel / MONTHS_RESERVED)
        mde55 = mde_sel * np.sqrt(n_sel / MONTHS_AVAILABLE_NOW)
        ok74, ok55 = abs(eff) >= mde74, abs(eff) >= mde55
        verdict = ("SPEND — resolvable on the full reserved window"
                   if ok74 else
                   "DO NOT SPEND — the window cannot resolve this effect")
        rows.append({"candidate": name, "effect": eff, "mde_74m": mde74,
                     "mde_55m": mde55, "resolvable_74m": bool(ok74),
                     "resolvable_55m": bool(ok55), "verdict": verdict})
        print(f"  {name:<20} {100 * eff:+8.2f}% {100 * mde74:8.2f}% "
              f"{100 * mde55:8.2f}%   {verdict}")

    spend = [r for r in rows if r["resolvable_74m"]]
    print(f"\n  candidates worth a confirmation slot: {len(spend)} of "
          f"{len(rows)}")
    if not spend:
        print("\n  RULING: the confirmation window is NOT spent. A test whose")
        print("  MDE exceeds the effect it is testing returns 'not established'")
        print("  whatever the world does, and afterwards the window is gone AND")
        print("  nothing was learned. The reservation stays; what changes is")
        print("  the requirement — a candidate must clear the FORWARD MDE, not")
        print("  the backward one, before it is allowed to consume a slot.")

    payload = {"rule": RULE,
               "selection_window": "2006-01..2019-12 (EXPLORE, "
                                   "slc_c3246e5093c41c25)",
               "confirmation_window": f"{CONFIRM_START}..{CONFIRM_END}",
               "months_reserved": MONTHS_RESERVED,
               "months_available_now": MONTHS_AVAILABLE_NOW,
               "alpha_per_outcome": 0.025,
               "alpha_note": "calendar allocation, k_eff 2.00, shared with "
                             "IV-ORACLE-GAP-1 (Order 8)",
               "n_candidates": len(terciles), "selected": [s[0] for s in selected],
               "rejected": {n: w for n, _, _, w in rejected},
               "power": rows,
               "slots_to_spend": len(spend),
               "ruling": ("SPEND" if spend else
                          "DO_NOT_SPEND — window preserved, forward MDE "
                          "becomes the selection requirement")}
    out = REPORT.parent / "m4_selector_prereg.json"
    out.write_text(json.dumps(payload, indent=1, default=float),
                   encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
