"""Seed the slice register with what has already been read.

    python -m scripts.seed_slice_register [--force]

A register that starts empty is a register that says every spent slice is
clean, which is worse than not having one. This writes the consumptions that
already happened, from the trials' own committed receipts.

The two that matter: N9 consumed the six-security confirmation slice
(DIA XLV XLI XLP XLU XLB), and N9B consumed it again. The register is seeded
with N9 as CONFIRM and N9B as PAIRED, which is what it actually was — a
difference test designed after that slice had been seen.

R13e amendment (2026-08-16). The first seeding recorded what was READ and not
what SELECTED, so N9's own mining slice — SPY/XLF/XLE through TRAIN_END —
was absent, and with it the calendar that later turned out to be the binding
coordinate. It is seeded now, at both horizons, which makes the register able
to reproduce the refusal on its own history: N9's confirmation is recorded as
non-independent RETROSPECTIVELY, since its pre-registration claimed the
opposite and the claim was withdrawn.
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
#: N9's own coordinates, from `scripts/n9_mine_the_85.py` rather than prose.
N9_TRAIN = ["SPY", "XLF", "XLE"]
N9_FOREIGN = ["QQQ", "IWM", "XLK"]
N9_TRAIN_END = "2015-12-31"
N9_FOREIGN_START = "2016-01-01"

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

    # ── N9's SELECTION, absent from the first seeding ──────────────────────
    # The register recorded what N9 read and not what chose N9's rules, so the
    # coordinate that turned out to be binding was not in it. Both horizons:
    # the purge is per horizon, so the spent calendar is too.
    ("N9", N9_TRAIN, "1999-01-01", N9_TRAIN_END, 20,
     "exceptional move, precursor grammar", "EXPLORE",
     "2026-08-16T03:00:00Z", "",
     [], "SELECTION. 13,728 candidates mined on three securities through "
         "TRAIN_END. This is the calendar every N9 descendant inherits.", False),

    ("N9", N9_TRAIN, "1999-01-01", N9_TRAIN_END, 60,
     "exceptional move, precursor grammar", "EXPLORE",
     "2026-08-16T03:00:01Z", "",
     [], "SELECTION, H=60.", False),

    ("N9", N9_FOREIGN, N9_FOREIGN_START, "2026-08-15", 20,
     "exceptional move, precursor grammar", "FOREIGN",
     "2026-08-16T03:30:00Z", "",
     [], "the foreign slice — 1.412, p=0.040 at H=20. Calendar-disjoint from "
         "selection, and by luck rather than by design: nothing in the "
         "register or the prereg required it to be.", False),

    ("N9", CONFIRMATION, "1999-01-01", "2026-08-15", 20,
     "exceptional move, precursor grammar", "CONFIRM",
     "2026-08-16T04:00:00Z", "",
     ["N9"], "13,728 candidates mined elsewhere; transfer confirmed here at "
         "lift 1.271, p=0.015. THIS IS THE CONSUMPTION — and it runs over "
         "1999-2026, seventeen years of which N9 selected on. Recorded "
         "non-independent RETROSPECTIVELY: the prereg claimed independence, "
         "R13e refuses this design, and the claim was withdrawn 2026-08-16 as "
         "TRANSFER_NOT_ESTABLISHED_CALENDAR_CONFOUNDED.", True),

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
    v = reg.check(ident, "CONFIRM", trial="N21-hypothetical", parents=())
    print("\nA new CONFIRM on the six-security slice:")
    print(f"  allowed={v['allowed']}  prior readers: {v['prior_readers']}")

    # ── R13e: the axis that was missing, on N9's own history ───────────────
    fresh = SliceIdentity(
        securities=("EFA", "EEM", "TLT"), start="1999-01-01", end="2026-08-15",
        outcome_horizon_days=20,
        outcome_definition="exceptional move, precursor grammar",
        information_cutoff="2026-08-15")
    print("\nN9's design, replayed: THREE UNREAD securities, full calendar.")
    print(f"  securities axis — prior readers: "
          f"{[r.trial for r in reg.prior_readers(fresh)]}  (clean)")
    vc = reg.check(fresh, "CONFIRM", trial="N9-replay", parents=("N9",))
    print(f"  calendar axis   — allowed={vc['allowed']}  "
          f"{vc.get('verdict', '')}  confounds={vc.get('calendar_confounds')}")
    print(f"  clean window starts: {vc.get('clean_from')}")

    und = reg.check(fresh, "CONFIRM", trial="N9-replay")
    print(f"  and with the lineage undeclared: allowed={und['allowed']}  "
          f"{und.get('verdict', '')}")

    rep = reg.clean_confirmation_windows(
        ["EFA", "EEM", "TLT", "GLD", "SPY"], fresh, lineage=("N9",))
    print(f"  both axes: unread={rep['securities_axis']['unread']}  "
          f"usable window={rep['calendar_axis']['usable_window']}")

    # and the laundering attempt the four-tuple exists to catch
    shifted = SliceIdentity(
        securities=tuple(CONFIRMATION), start="1999-06-01", end="2026-08-15",
        outcome_horizon_days=20,
        outcome_definition="exceptional move, precursor grammar",
        information_cutoff="2026-08-15")
    v2 = reg.check(shifted, "CONFIRM", trial="N21-shifted-window",
                   parents=())
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
