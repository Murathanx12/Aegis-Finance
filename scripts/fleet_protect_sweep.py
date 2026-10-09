"""Bounded late-fill stop sweep; DRY unless --live is explicitly supplied.

This is not a fleet-manager pass. It cannot enter, exit, cancel or rebaseline.
No scheduled task is installed by this module.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

from backend.services import fleet_manager as FM
from backend.services import fleet_protect_only as FP
from scripts import fleet_manager_run as RUN


def _transport_with_deadline(budget: FP.SweepBudget, upstream=None):
    def send(method: str, url: str, headers: dict, body: bytes | None):
        budget.charge_http()
        if upstream is not None:
            result = upstream(method, url, headers, body)
        else:
            remaining = budget.until - FP.time.monotonic()
            if remaining <= 0:
                raise FM.FleetRefusal("sweep deadline before broker request")
            request = urllib.request.Request(url, data=body, headers=headers, method=method)
            try:
                with urllib.request.urlopen(request, timeout=min(30, remaining)) as response:
                    result = response.status, response.read()
            except urllib.error.HTTPError as exc:
                result = exc.code, exc.read()
        budget.charge(0)
        return result
    return send


def main(argv: list[str] | None = None, *, transport=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="permit reviewed protection-only LIVE authority")
    args = ap.parse_args(argv)
    started = datetime.now(timezone.utc)
    budget = FP.SweepBudget()
    receipt: dict = {"schema": "fleet_protect_sweep/1", "started_utc": started.isoformat(),
                     "live_flag": args.live, "status": "REFUSED"}
    try:
        modes_path = FM.modes_path()
        if not modes_path.exists():
            raise FM.FleetRefusal("fleet modes absent")
        modes = json.loads(modes_path.read_text(encoding="utf-8"))
        if any(r not in modes for r in FM._cfg.FLEET_MANAGER_ROLES):
            raise FM.FleetRefusal("fleet role modes inventory incomplete")
        active = [r for r in FM._cfg.FLEET_MANAGER_ROLES if not (modes.get(r) or {}).get("skip")]
        if not active or len(active) > 5:
            raise FM.FleetRefusal("active fleet role inventory absent or exceeds five")
        env = RUN.read_env_file(RUN.TERMINAL_ENV)
        send = _transport_with_deadline(budget, transport)
        venues = {}
        for role in active:
            key, secret = env.get(f"AAT_{role.upper()}_KEY_ID"), env.get(f"AAT_{role.upper()}_SECRET_KEY")
            if not key or not secret:
                raise FM.FleetRefusal(f"{role}: owning paper credential absent")
            venues[role] = FM.Venue(key, secret, transport=send)

        def sigma_for(role: str, symbol: str, venue) -> dict:
            sigma, _, _ = RUN.panel_sigma_and_screen([symbol])
            if symbol not in sigma:
                bars = venue.daily_closes([symbol], (date.today() - timedelta(days=130)).isoformat())
                value = FM.sigma_from_closes([c for _, c in sorted(bars.get(symbol) or [])])
                if value:
                    sigma[symbol] = value
            if symbol not in sigma:
                raise FM.FleetRefusal("volatility evidence absent for late-fill stop")
            return {symbol: sigma[symbol]}

        receipt.update(FP.sweep_once(venues, modes, sigma_for, live=args.live, budget=budget))
    except (FM.FleetRefusal, OSError, ValueError, KeyError) as exc:
        receipt.update(status="REFUSED", why=f"{type(exc).__name__}: {str(exc)[:180]}")
    except Exception as exc:  # noqa: BLE001 -- an unexpected failure must leave a refusal receipt
        receipt.update(status="REFUSED", why=f"unexpected {type(exc).__name__}; manual review required")
    receipt["finished_utc"] = datetime.now(timezone.utc).isoformat()
    receipt["requests_upper_bound"] = budget.used
    receipt["http_requests"] = budget.http_total
    path = FM.root() / "sweeps" / f"sweep_{started:%Y%m%dT%H%M%S%fZ}.json"
    FM.atomic_write_json(path, receipt)
    print(json.dumps(receipt, indent=2))
    return 0 if receipt["status"] in {"ALREADY_COVERED", "DRY_PLAN", "PROTECTED"} else 2


if __name__ == "__main__":
    sys.exit(main())
