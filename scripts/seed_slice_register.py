"""Seed the slice register with what has already been read.

    python -m scripts.seed_slice_register [--force]

A register that starts empty is a register that says every spent slice is
clean, which is worse than not having one. This writes the consumptions that
already happened, from the trials' own committed receipts.

The two that matter: N9 consumed the six-security confirmation slice
(DIA XLV XLI XLP XLU XLB), and N9B consumed it again. The register is seeded
with N9 as CONFIRM and N9B as PAIRED, which is what it actually was — a
difference test designed after that slice had been seen.
"""

from __future__ import annotations

import argparse
import sys

from backend.services.research_gym.slice_register import (REGISTER_PATH,
                                                          SliceIdentity,
                                                          SliceRefusal,
                                                          SliceRegister)

EXPLORATION = ["SPY", "QQQ", "IWM", "XLF", "XLE", "XLK"]
CONFIRMATION = ["DIA", "XLV", "XLI", "XLP", "XLU", "XLB"]

#: (trial, securities, start, end, horizon, outcome, purpose, when, prereg,
#:  parents, note, declared_non_independent)
HISTORY = [
    ("N4", EXPLORATION, "1999-01-01", "2026-08-15", 20,
     "bottom/top decile of H-day forward return", "EXPLORE",
     "2026-08-16T00:00:00Z", "",
     [], "pooled coverage lift of the six-rule precursor library", False),

    ("N4B", EXPLORATION, "1999-01-01", "2026-08-15", 20,
     "bottom/top decile of H-day forward return", "REANALYSIS",
     "2026-08-16T02:00:00Z", "docs/TRIALS/PREREG_N4B_COVERAGE_EQUIVALENCE.md",
     ["N4"], "equivalence against an economically derived margin", True),

    ("N9", CONFIRMATION, "1999-01-01", "2026-08-15", 20,
     "exceptional move, precursor grammar", "CONFIRM",
     "2026-08-16T04:00:00Z", "",
     [], "13,728 candidates mined elsewhere; transfer confirmed here at "
         "lift 1.271, p=0.015. THIS IS THE CONSUMPTION.", False),

    ("N9B", CONFIRMATION, "1999-01-01", "2026-08-15", 20,
     "exceptional move, precursor grammar", "PAIRED",
     "2026-08-16T06:00:00Z", "",
     ["N9"], "vocabulary-width difference test. Arithmetic sound and the "
             "equivalence result stands, but it is a post-confirmation "
             "adaptive comparison on a slice N9 had already read — NOT a "
             "second independent confirmation.", True),

    ("N20", EXPLORATION, "1999-01-01", "2026-08-15", 20,
     "bottom/top decile of H-day forward return", "REANALYSIS",
     "2026-08-16T16:00:00Z", "docs/TRIALS/PREREG_N20_CONDITIONAL_MU_REST.md",
     ["N4B"], "conditional mu_rest|fire against N4B's unconditional estimand",
     True),
]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--force", action="store_true",
                    help="re-seed even if the register already has records")
    a = ap.parse_args(argv)

    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                        # noqa: BLE001
            pass

    reg = SliceRegister()
    if reg.records and not a.force:
        print(f"{REGISTER_PATH} already has {len(reg.records)} records; "
              f"--force to re-seed. Refusing to append duplicates.")
        return 0
    if a.force and REGISTER_PATH.exists():
        REGISTER_PATH.unlink()
        reg = SliceRegister()

    for (trial, secs, start, end, hz, outcome, purpose, when, prereg,
         parents, note, non_indep) in HISTORY:
        ident = SliceIdentity(
            securities=tuple(secs), start=start, end=end,
            outcome_horizon_days=hz, outcome_definition=outcome,
            information_cutoff=end)
        try:
            rec = reg.claim(ident, purpose, trial=trial, consumed_at=when,
                            prereg=prereg, parent_hypotheses=parents,
                            note=note, declared_non_independent=non_indep)
            print(f"  {rec.trial:<5s} {rec.purpose:<10s} {rec.slice_id}  "
                  f"{', '.join(ident.securities)}")
        except SliceRefusal as exc:
            print(f"  {trial:<5s} REFUSED: {exc}")
            return 1

    print(f"\nseeded {len(reg.records)} consumptions -> {REGISTER_PATH}")

    # ── the demonstration that matters ─────────────────────────────────────
    ident = SliceIdentity(
        securities=tuple(CONFIRMATION), start="1999-01-01", end="2026-08-15",
        outcome_horizon_days=20,
        outcome_definition="exceptional move, precursor grammar",
        information_cutoff="2026-08-15")
    v = reg.check(ident, "CONFIRM", trial="N21-hypothetical")
    print("\nA new CONFIRM on the six-security slice:")
    print(f"  allowed={v['allowed']}  prior readers: {v['prior_readers']}")

    # and the laundering attempt the four-tuple exists to catch
    shifted = SliceIdentity(
        securities=tuple(CONFIRMATION), start="1999-06-01", end="2026-08-15",
        outcome_horizon_days=20,
        outcome_definition="exceptional move, precursor grammar",
        information_cutoff="2026-08-15")
    v2 = reg.check(shifted, "CONFIRM", trial="N21-shifted-window")
    print("Same six securities, start shifted five months (a 'new slice'):")
    print(f"  allowed={v2['allowed']}  slice_id differs "
          f"({shifted.slice_id} vs {ident.slice_id}) but overlap is detected")

    pool = ["DIA", "XLV", "XLI", "XLP", "XLU", "XLB", "EFA", "EEM", "TLT",
            "GLD", "XLY", "XLRE", "IYR", "SLV", "HYG", "LQD"]
    free = reg.unread_candidates(pool, ident)
    print(f"\nUnread at 20d in that window, from a {len(pool)}-name pool: {free}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
