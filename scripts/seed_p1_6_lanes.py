"""
Seed the P1 #6 book lanes (mirror + conviction) — ATTENDED write-path.

Inception = TODAY at CURRENT market-value weights normalized to $100k. NO
historical prices, NO reconstructed past inception. Idempotent: re-running never
double-seeds. After seeding it marks the lanes to market so the freshness canary
is green immediately.

  python -m scripts.seed_p1_6_lanes --dry-run   # show live weights, write nothing
  python -m scripts.seed_p1_6_lanes             # seed + MTM against the local DB

PRODUCTION seeding does NOT use this script directly (the prod DB lives on the
Railway volume, only reachable inside the container). Instead set
AEGIS_SEED_BOOK_LANES=1 on Railway for ONE boot — the env-gated startup hook in
main.py runs seed_all_book_lanes() in-container — then unset the flag.
"""

import argparse

from backend.config import book_lanes
from backend.services.portfolio_intelligence.reference_engine import (
    _get_current_prices,
    seed_all_book_lanes,
)
from backend.services.portfolio_intelligence.rules import compute_book_mv_weights


def main() -> None:
    ap = argparse.ArgumentParser(description="Seed P1 #6 book lanes (attended).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print live MV weights and exit without writing.")
    args = ap.parse_args()

    holdings = book_lanes.get("holdings") or {}
    prices = _get_current_prices(list(holdings.keys()))
    # Fail loud BEFORE any write if the book can't be fully priced.
    weights = compute_book_mv_weights(holdings, prices)

    print("Book current-market-value weights (live prices):")
    for t, w in sorted(weights.items(), key=lambda kv: -kv[1]):
        print(f"  {t:6s} {w * 100:6.2f}%   @ ${prices[t]:,.2f}")
    print(f"  ({len(weights)} names → $100,000 notional)")

    if args.dry_run:
        print("\n--dry-run: nothing written.")
        return

    print("\nSeeding + marking to market...")
    res = seed_all_book_lanes(prices=prices)
    for lane, r in res["seeded"].items():
        print(f"  seed {lane:11s}: seeded={r.get('seeded')} ({r.get('reason', 'ok')})")
    for lane, nav in res["mtm"].items():
        print(f"  mtm  {lane:11s}: NAV={nav}")
    print("Done. Confirm at /api/health/full (nav block, all_fresh) "
          "and /api/pi/registry (cumulative_trials).")


if __name__ == "__main__":
    main()
