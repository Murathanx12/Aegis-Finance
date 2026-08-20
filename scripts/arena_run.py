"""ARENA driver.

    python -m scripts.arena_run --status          # what exists, seeds nothing
    python -m scripts.arena_run --seed            # write inceptions (idempotent)
    python -m scripts.arena_run --run             # one daily pass
    python -m scripts.arena_run --run --as-of 2026-08-20

Everything here is PRODUCT_EXPERIMENT / SIMULATION in the arena namespace:
no `paper_nav`, no lane YAML, no order path, no skill claims. Seeding
authorisation is recorded in `backend/data/arena/arena_books_v1.yaml`
(`seeding.authorised`) and in docs/ORDER_25_LIVE_ARENA_GEN1.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.services.arena import engine as E  # noqa: E402


def _utf8() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="arena_run")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--seed", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--as-of", default=None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    _utf8()

    if a.seed:
        done = E.seed_all()
        print("seeded:", json.dumps(done, indent=2, default=str))
    if a.run:
        summary = E.run_daily(a.as_of)
        print(json.dumps(summary, indent=2, default=str))
    if a.status or not (a.seed or a.run):
        st = E.status()
        print(json.dumps(st, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
