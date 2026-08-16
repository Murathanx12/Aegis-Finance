"""M4 and IV-ORACLE-GAP-1 confirm on the same six years. Price that.

    python -m scripts.declare_shared_calendar --commit

Two EXPORT budgets already sit on 2020-06-01..2026-07-17 — `crsp_us` with a
portfolio-utility outcome, `wm0_18_etfs` with a tail-pinball outcome. Different
universes, different outcomes, same dates: the same COVID crash and the same
2023-25 rally move both, so their test statistics are correlated and two
budgets of five do not deliver FWER 0.05 twice.

Full sharing would be the other error. Six years supporting five tests forever
is a gate that gets deleted within the month, and a gate that gets deleted
protects nothing — the same lesson the one-day sweep taught.

So the calendar is declared with rho_bar from the DECLARED_CONSERVATIVE path,
which forces it to zero and charges the maximum: k_eff = 2, alpha 0.025 each.
Not because independence is believed — the two outcomes are visibly related
through the same market — but because nothing has been MEASURED yet, and the
strict direction is the only honest default. When both outcome series exist,
`declare_calendar(..., rho_source=MEASURED, rho_evidence=...)` on a FRESH
calendar can buy the power back with evidence. It cannot be bought back here,
because re-declaring after results exist is choosing the error rate afterwards.
"""

from __future__ import annotations

import argparse
import sys

from backend.services.research_gym.multiplicity import (
    RHO_DECLARED_CONSERVATIVE, ConfirmationBudget, MultiplicityRefusal,
    calendar_of)

PERIOD = "2020-06-01..2026-07-17"
OUTCOMES = ["portfolio_utility_net", "tail_pinball_h20"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true")
    a = ap.parse_args()
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                        # noqa: BLE001
            pass

    cb = ConfirmationBudget()
    existing = cb.windows_on(PERIOD)
    print(f"calendar {PERIOD}")
    print(f"  windows already budgeted on it: {len(existing)}")
    for w in existing:
        print(f"    {w}")
    prior = cb.calendar_declaration(PERIOD)
    if prior is not None:
        print(f"\nalready declared at {prior.declared_at}: k_eff "
              f"{prior.k_eff:.2f}, alpha/outcome {prior.alpha_per_outcome:.4f}")
        return 0

    print(f"\nwould declare: outcomes={OUTCOMES} rho_source="
          f"{RHO_DECLARED_CONSERVATIVE} (forces rho_bar=0) alpha=0.05")
    print("  -> k_eff 2.00, alpha per outcome 0.025")
    print("  -> Holm at a budget of 5 gives a first threshold of 0.005, "
          "not 0.010")
    if not a.commit:
        print("\nDRY RUN. Re-run with --commit to write the declaration.")
        return 0

    try:
        c = cb.declare_calendar(
            PERIOD, outcomes=OUTCOMES,
            rho_source=RHO_DECLARED_CONSERVATIVE, declared_by="order-8",
            note=("M4-SELECTOR and IV-ORACLE-GAP-1 share this calendar. "
                  "rho_bar is conservative because neither outcome series "
                  "exists yet; a MEASURED value would need both."))
    except MultiplicityRefusal as e:
        print(f"\nREFUSED: {e}")
        return 1

    print(f"\ndeclared. k_eff {c.k_eff:.2f}, alpha per outcome "
          f"{c.alpha_per_outcome:.4f}")
    for w in existing:
        alpha, why = cb.alpha_for(w)
        print(f"  {w}\n    alpha now {alpha:.4f} — {why}")
        assert calendar_of(w) == PERIOD
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
