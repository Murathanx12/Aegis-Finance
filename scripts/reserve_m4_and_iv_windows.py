"""Reserve the confirmation windows BEFORE the first return is computed.

    python -m scripts.reserve_m4_and_iv_windows --dry-run
    python -m scripts.reserve_m4_and_iv_windows --commit

WHY THE ORDER MATTERS AND WHY THIS RUNS FIRST
=============================================
The next task is to measure ten known strategies — momentum, value, quality,
trend, low-vol and the rest — over 2006-2019, so that the factory's output has
a benchmark to beat.

That measurement is harmless right up until the moment somebody uses it to
decide WHICH strategies to deploy. At that instant 2006-2019 stops being a
description and becomes the **selection window for M4, the selector**, and any
later evaluation of the chosen set on those same dates is N9's error again:

    N9 held out six untouched securities over a calendar that had already
    chosen the rule. 1.464 inside the selection window, 0.765 outside it.

The difference this time is that the sequence is being caught **one step before
it starts** rather than four days after the headline. Nothing has been measured
yet, so the declaration costs nothing and can still be honest.

WHAT IS DECLARED HERE
=====================
1. `M4-SELECTOR` consumes **2006-2019 as EXPLORE**. Not CONFIRM, not TRANSFER —
   the library measurement is exploratory by construction and must never later
   be described as a validation of the strategies it ranks.
2. Its confirmation window is reserved on **2020-06-01 .. 2026-07-17**, disjoint
   from the selection window by 153 days, which clears R13e at every horizon
   this programme uses.
3. `IV-ORACLE-GAP-1` Phase B takes its slot on the same calendar. It was
   described as reserved in the pre-registration and was never actually
   recorded anywhere a machine could refuse against — a reservation that exists
   only in prose is the honour system with better formatting.

AND THE THING THIS SURFACES
===========================
M4 and IV Phase B want the same DATES with different OUTCOMES. By the declared
slice identity those are different windows, and that is defensible: tail pinball
on a volatility forecast and portfolio utility on a strategy set are different
measurements with different power.

It is also not free. The same six years of market history is answering both, so
the union is closer to two families than to two independent experiments, and a
reader who adds up their error rates as if independent will be wrong in the
optimistic direction. Printed here rather than left for someone to discover.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

from backend.services.research_gym import multiplicity as MP
from backend.services.research_gym.slice_register import (SliceIdentity,
                                                          SliceRefusal,
                                                          SliceRegister)

SELECTION = ("2006-01-03", "2019-12-31")
CONFIRMATION = ("2020-06-01", "2026-07-17")

#: The strategy-library universe. Recorded as a NAME rather than a ticker list:
#: the library is measured on the whole CRSP cross-section, which is not
#: enumerable here and would be a lie if truncated to a sample.
UNIVERSE_TAG = "CRSP_US_COMMON_SHARES"


def _identity(start: str, end: str, *, horizon: int, outcome: str,
              cutoff: str) -> SliceIdentity:
    return SliceIdentity(securities=(UNIVERSE_TAG,), start=start, end=end,
                         outcome_horizon_days=horizon,
                         outcome_definition=outcome,
                         information_cutoff=cutoff)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--commit", action="store_true")
    a = ap.parse_args(argv)
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                        # noqa: BLE001
            pass

    today = str(date.today())
    reg = SliceRegister()
    cb = MP.ConfirmationBudget()

    sel = _identity(*SELECTION, horizon=21, outcome="monthly_excess_return",
                    cutoff="close of the rebalance date")
    con = _identity(*CONFIRMATION, horizon=21, outcome="monthly_excess_return",
                    cutoff="close of the rebalance date")

    print("M4-SELECTOR — the strategy library measurement")
    print(f"  selection    {SELECTION[0]} .. {SELECTION[1]}   EXPLORE")
    print(f"  confirmation {CONFIRMATION[0]} .. {CONFIRMATION[1]}   RESERVED")
    print(f"  slice_id sel {sel.slice_id}")
    print(f"  slice_id con {con.slice_id}")

    # `con` is the window being CHECKED; `sel` is the one already spent, so the
    # call goes con.calendar_overlaps(sel) — the spent window is the one whose
    # labels reach forward, and getting the direction wrong here would extend
    # the wrong end and pass a confirmation that abuts its own selection.
    ov = con.calendar_overlaps(sel)
    print(f"  calendar disjoint: {not ov['calendar_overlaps']}   "
          f"required gap {ov['gap_days']}d at H={sel.outcome_horizon_days}")
    if ov["calendar_overlaps"]:
        print(f"  REFUSED: overlap {ov['overlap_start']}..{ov['overlap_end']}")
        return 2

    # The two windows that will compete for the same six years.
    w_m4 = MP.window_id(universe="crsp_us",
                        period=f"{CONFIRMATION[0]}..{CONFIRMATION[1]}",
                        outcome="portfolio_utility_net")
    w_iv = MP.window_id(universe="wm0_18_etfs",
                        period=f"{CONFIRMATION[0]}..{CONFIRMATION[1]}",
                        outcome="tail_pinball_h20")
    print(f"\nEXPORT windows on the same calendar:")
    print(f"  {w_m4}")
    print(f"  {w_iv}")
    print("  -> DIFFERENT windows by the declared identity (different outcome),")
    print("     and the SAME six years of market history is answering both.")
    print("     Their error rates do NOT add as if independent; a reader who")
    print("     treats them that way will be wrong optimistically.")

    if a.dry_run:
        print("\n--dry-run: nothing written. Re-run with --commit.")
        return 0

    # ── 1. the selection consumption ───────────────────────────────────────
    try:
        reg.claim(sel, "EXPLORE", trial="M4-SELECTOR", consumed_at=today,
                  prereg="docs/TRIALS/PREREG_M4_STRATEGY_LIBRARY.md",
                  parent_hypotheses=[],
                  note=("Measuring 10 published/practitioner strategies on this "
                        "window. EXPLORE: if the deployed set is later chosen "
                        "from these numbers, this window SELECTED it and cannot "
                        "also validate it."))
        print(f"\n  claimed EXPLORE {sel.slice_id} for M4-SELECTOR")
    except SliceRefusal as exc:
        print(f"\n  REFUSED: {exc}")
        return 2

    # ── 2. the two confirmation budgets ────────────────────────────────────
    for wid, who, note in (
        (w_m4, "M4-SELECTOR",
         "Confirmation of the strategy SELECTION made on 2006-2019. Five "
         "slots, Holm at FWER 0.05."),
        (w_iv, "IV-ORACLE-GAP-1",
         "Phase B. Registered as reserved in the prereg and never recorded "
         "anywhere a machine could refuse against, until now. Under R13f this "
         "window yields ADAPTIVE_HISTORICAL_VALIDATION rather than independent "
         "confirmation, because WM0 read these dates."),
    ):
        if cb.budget_of(wid) is None:
            b = cb.declare_budget(wid, budget=MP.RECOMMENDED_BUDGET,
                                  declared_by=who, purpose=MP.EXPORT,
                                  note=note)
            print(f"  declared EXPORT budget {b.budget} @ FWER {b.rate} "
                  f"on {wid}")
        else:
            print(f"  budget already declared on {wid} — left alone")

    # IV Phase B takes its slot now, because the prereg already committed to
    # running it and a slot claimed later is a slot claimed after seeing what
    # else the window gave up.
    try:
        cb.reserve(w_iv, trial="IV-ORACLE-GAP-1", hypothesis="H1-phase-B",
                   note="reserved at registration, not at run time")
        print(f"  reserved IV-ORACLE-GAP-1/H1-phase-B  "
              f"({cb.remaining(w_iv)} slots left)")
    except MP.MultiplicityRefusal as exc:
        print(f"  IV reservation not taken: {exc}")

    print("\nRecorded. The strategy-library measurement may now run: its "
          "window is declared EXPLORE and its confirmation calendar is "
          "reserved and disjoint.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
