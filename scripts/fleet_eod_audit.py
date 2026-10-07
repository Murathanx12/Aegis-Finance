"""The fleet's end-of-day audit, alone (read-only; places and cancels nothing).

    python -m scripts.fleet_eod_audit                       # every fleet role
    python -m scripts.fleet_eod_audit --trigger daily_check  # what the 06:45 HKT check passes

The Preclose pass (`scripts/fleet_manager_run.py --pass preclose`) runs the same
audit as its LAST step with trigger `preclose_pass`; this entry point is what the
read-only daily check (`aegis-alpha-terminal/scripts/fleet_daily_check.py`)
reuses, and what an operator runs by hand. Rows go to
`backend/data/optimus/paper_accounts/fleet_manager/eod_audit/audit.jsonl`.
Exit 1 when any non-retired account is not OK, so a scheduler sees red.
"""
from __future__ import annotations

import argparse
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _cfg                          # noqa: E402
from backend.services import fleet_eod_audit as EOD         # noqa: E402
from scripts.fleet_manager_run import TERMINAL_ENV, read_env_file   # noqa: E402


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--roles", default=",".join(_cfg.FLEET_MANAGER_ROLES))
    ap.add_argument("--trigger", default="manual")
    a = ap.parse_args(argv)
    run_id = "eod-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
    env = read_env_file(TERMINAL_ENV)
    rows = EOD.run_audit([r.strip() for r in a.roles.split(",") if r.strip()], env,
                         run_id=run_id, trigger=a.trigger)
    retired = set(getattr(_cfg, "PAPER_ACCOUNTS_RETIRED_UNREADABLE", ()) or ())
    bad = 0
    for r in rows:
        wc = r.get("worst_case") or {}
        print(f"{r['role']:6s} {r['status']:18s} equity {r.get('equity')} stops "
              f"{(r.get('stops') or {}).get('n_protected')}/{(r.get('stops') or {}).get('n_held_long')} "
              f"mismatches {r.get('n_mismatches')} worst ${wc.get('usd_at_stops')} "
              f"gross/eq {wc.get('gross_over_equity')}  {str(r.get('why') or '')[:120]}")
        if r["status"] != "OK" and r["role"] not in retired:
            bad += 1
    print(f"\n{len(rows)} row(s) -> {EOD.audit_path()}  run_id {run_id}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
