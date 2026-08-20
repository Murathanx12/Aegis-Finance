"""COPY-LAB: seed the authorised lanes, then run one engine pass.

    python -m scripts.copy_lab_run --status          # what exists, seeds nothing
    python -m scripts.copy_lab_run --seed            # attended: write inceptions
    python -m scripts.copy_lab_run --run             # one pass over live events

SEEDING IS ATTENDED
===================
`--seed` writes an inception timestamp and the configuration hash in force. It
is idempotent and refuses to move an existing inception; a changed configuration
is a NEW lane, never a new start date for an old one.

The authorisation is recorded in the configuration file itself
(`seeding.authorised`), with who granted it and where — so a seed can always be
traced to a decision rather than to a session that felt confident.

WHAT A PASS DOES NOT DO
=======================
It does not backfill. Events public before a lane's inception are ineligible
forever, and there is no flag that changes that. A new lane's NAV is flat and
boring for a while, which is what an honest one looks like.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.services.copy_lab import engine as E                # noqa: E402
from backend.services.copy_lab import lanes as L                 # noqa: E402
from backend.services.copy_lab import store as S                 # noqa: E402
from backend.services.copy_lab.prices import YFinancePanel       # noqa: E402
from backend.services.teacher_library import ledger as TL        # noqa: E402


def _utf8() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass


def status() -> dict:
    lanes = L.load_lanes()
    out = L.summary()
    out["seeded"] = {k: (S.read_seed(k) or {}).get("seeded_at")
                     for k in sorted(lanes)}
    return out


def seed(authorised_only: bool = True) -> dict:
    import yaml
    raw = yaml.safe_load(L.config_bytes().decode("utf-8"))
    auth = bool((raw.get("seeding") or {}).get("authorised"))
    if authorised_only and not auth:
        raise SystemExit(
            "REFUSED: the configuration does not record an authorisation for "
            "seeding. Seeding is attended; it is not a session's decision.")
    done = {}
    for name, spec in L.load_lanes().items():
        if not spec.seedable:
            continue
        rec = S.seed_lane(spec)
        done[name] = rec["seeded_at"]
    return done


def run(as_of: str | None = None, lookback_days: int = 180) -> list[dict]:
    # The pass itself lives in backend.services.copy_lab.runner so the
    # scheduler job `pi_copy_lab_run` and this script execute the SAME code.
    from backend.services.copy_lab.runner import run_active_lanes

    receipts = run_active_lanes(as_of, lookback_days=lookback_days)
    if not receipts:
        print("no seeded active lane — nothing to run")
        return []
    for r in receipts:
        if r.get("status") == "error":
            print(f"\n{r.get('lane_id')}\n  ERROR  {r.get('error')}")
            continue
        print(f"\n{r.get('lane_id', '?')}")
        print(f"  events considered  {r['events_considered']}")
        print(f"  new signals        {r['signals_new']} "
              f"({r['signals_ineligible']} ineligible)")
        print(f"  fills              {r['fills']}")
        print(f"  open positions     {r['open_positions']}")
        print(f"  nav                {r['nav']}")
        for reason, n in list(r["ineligible_reasons"].items())[:5]:
            print(f"    {n:>4}  {reason}")
    return receipts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="copy_lab_run")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--seed", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--as-of", default=None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    _utf8()

    if a.seed:
        done = seed()
        print("seeded:", json.dumps(done, indent=2))
    if a.run:
        run(a.as_of)
    if a.status or not (a.seed or a.run):
        st = status()
        print(json.dumps(st, indent=2) if a.json else
              "\n".join([
                  "COPY-LAB — PRODUCT_EXPERIMENT / NOT VALIDATED ALPHA",
                  f"config      {st['config_path']}",
                  f"hash        {st['config_hash'][:16]}",
                  f"lanes       {st['n_lanes']}  "
                  f"active {len(st['active'])}  inactive {len(st['inactive'])}",
                  f"active      {', '.join(st['active'])}",
                  "seeded      " + ", ".join(
                      f"{k}={v}" for k, v in st["seeded"].items() if v) or
                  "seeded      (none)",
              ]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
