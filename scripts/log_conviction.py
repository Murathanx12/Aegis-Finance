#!/usr/bin/env python
"""
Log a conviction-lane decision from the terminal in <10s (P1 #6).

Writes to the immutable `personal_decisions` log (NOT the paper_nav track-record
path). timestamp is always now (never backdated); a past action → --late-entry;
corrections append via --amends-id (the table forbids update/delete).

Examples:
    python scripts/log_conviction.py --ticker SOC --action add --shares 100 \
        --price 6.80 --conviction 4 \
        --rationale "Adding on the pullback; offshore production ramp on track and the thesis is intact."

    python scripts/log_conviction.py -t DKNG -a trim -s -50 -p 31.20 -c 3 \
        -r "Trimming into strength to manage single-name concentration after the run." --late-entry
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

# Allow running from anywhere (repo root on sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    ap = argparse.ArgumentParser(description="Log a conviction-lane decision (immutable, forward-only).")
    ap.add_argument("-t", "--ticker", required=True)
    ap.add_argument("-a", "--action", required=True, choices=["enter", "add", "trim", "exit"])
    ap.add_argument("-s", "--shares", required=True, type=float, help="shares delta (negative to reduce)")
    ap.add_argument("-p", "--price", required=True, type=float)
    ap.add_argument("-c", "--conviction", required=True, type=int, choices=range(1, 6))
    ap.add_argument("-r", "--rationale", required=True, help=">= 50 chars (honest-record discipline)")
    ap.add_argument("--tags", nargs="*", default=[], help="thesis tags")
    ap.add_argument("--target", type=float, default=None)
    ap.add_argument("--stop", type=float, default=None)
    ap.add_argument("--amends-id", type=int, default=None, help="correct a prior decision (appends a new row)")
    ap.add_argument("--late-entry", action="store_true", help="the action already happened; logging after the fact")
    args = ap.parse_args()

    from backend.db import get_connection, init_db, insert_personal_decision

    init_db()
    conn = get_connection()
    try:
        ts = datetime.now().isoformat()  # never backdated
        rid = insert_personal_decision(
            conn, timestamp=ts, ticker=args.ticker.upper().strip(), action=args.action,
            shares_delta=args.shares, price=args.price, rationale=args.rationale,
            thesis_tags=args.tags, conviction=args.conviction, portfolio_snapshot={},
            target_price=args.target, stop_price=args.stop, amends_id=args.amends_id,
            late_entry=args.late_entry,
        )
    except ValueError as e:
        print(f"REJECTED: {e}", file=sys.stderr)
        return 2
    finally:
        conn.close()

    flag = " [late_entry]" if args.late_entry else ""
    print(f"logged decision #{rid}: {args.action} {args.shares:+g} {args.ticker.upper()} "
          f"@ {args.price} (conviction {args.conviction}){flag} at {ts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
