"""One-shot fleet late-fill stop check. DRY by default; no other order kinds.

    python -m scripts.fleet_protect_only --role hack6 --symbol CCI
    python -m scripts.fleet_protect_only --role hack6 --symbol CCI --live

The live form requires a separately reviewed source/integration and the
existing maintenance LIVE mode. It does not run entries, exits or cancels.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta

from backend.services import fleet_manager as FM
from backend.services import fleet_protect_only as FP
from scripts import fleet_manager_run as RUN


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", required=True, choices=tuple(FM._cfg.FLEET_MANAGER_ROLES))
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args(argv)
    env = RUN.read_env_file(RUN.TERMINAL_ENV)
    modes_path = FM.modes_path()
    if not modes_path.exists():
        raise FM.FleetRefusal("fleet modes file absent; no default may be written here")
    modes = json.loads(modes_path.read_text(encoding="utf-8"))
    key = env.get(f"AAT_{args.role.upper()}_KEY_ID")
    secret = env.get(f"AAT_{args.role.upper()}_SECRET_KEY")
    if not key or not secret:
        raise FM.FleetRefusal("owning paper credential absent")
    venue = FM.Venue(key, secret)
    sigma, _, _ = RUN.panel_sigma_and_screen([args.symbol])
    if args.symbol not in sigma:
        bars = venue.daily_closes([args.symbol], (date.today() - timedelta(days=130)).isoformat())
        value = FM.sigma_from_closes([c for _, c in sorted(bars.get(args.symbol) or [])])
        if value:
            sigma[args.symbol] = value
    result = FP.protect_once(args.role, args.symbol, venue, modes, sigma,
                             live=args.live)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result["status"] in {"ALREADY_COVERED", "DRY_PLAN", "PROTECTED"} else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except FM.FleetRefusal as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        sys.exit(3)
