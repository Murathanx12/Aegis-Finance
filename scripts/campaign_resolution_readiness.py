"""What the 2026-08-16 campaign resolution WOULD do, without touching anything.

    python -m scripts.campaign_resolution_readiness

WHY THIS EXISTS SEPARATELY FROM `--dry-run`
============================================
`resolve_campaign_ledger --dry-run` stops before fetching prices, so it answers
"how many are due" and not "how many can actually be graded". The order asks
for source availability as well: **due / resolvable / unresolved**. That
requires running the resolver, and the resolver rewrites the file it is given.

So this runs it against a **byte-identical COPY** in a scratch directory, and
verifies the real ledger's SHA-256 before and after. The production ledger is
never opened for writing, and the check proves it rather than promising it.

It is READ-ONLY BY CONSTRUCTION, which is why it is safe to run unattended.
The irreversible step — `--commit` on the real file — stays attended.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path

from backend.services import evidence_population as EP
from backend.services.ledger_resolver import resolve_due

POPULATION = EP.EvidencePopulation.CAMPAIGN_FORWARD


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--as-of", default=None,
                    help="grade as of this date (default: today)")
    a = ap.parse_args(argv)

    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                        # noqa: BLE001
            pass

    real = EP.ledger_path(POPULATION)
    today = date.fromisoformat(a.as_of) if a.as_of else date.today()
    before = _sha256(real)
    print("=" * 70)
    print("CAMPAIGN RESOLUTION READINESS — read-only, run against a copy")
    print("=" * 70)
    print(f"\nreal ledger        {real}")
    print(f"  sha256 BEFORE    {before}")
    print(f"  as of            {today}")

    with tempfile.TemporaryDirectory(prefix="aegis-resolution-readiness-") as td:
        copy = Path(td) / real.name
        shutil.copy2(real, copy)
        assert _sha256(copy) == before, "the copy is not byte-identical"
        print(f"  copy             {copy}")
        print(f"  sha256 of copy   MATCHES\n")

        # No `population=` here on purpose: passing it would resolve the path
        # from the registry and point the resolver back at the real file.
        rep = resolve_due(copy, today=today)

        print(f"due                {rep['due']}")
        print(f"  would resolve    {rep['newly_resolved']}")
        print(f"  still pending    {rep['pending']}")
        print(f"  overdue after    {rep['overdue']}")
        print(f"  priced from      {rep.get('priced_from')}")
        unp = rep.get("unpriceable") or []
        print(f"  UNPRICEABLE      {len(unp)}"
              + (f"  {sorted(unp)[:12]}" if unp else ""))
        h = rep.get("health") or {}
        print(f"  health after     {h.get('status')}  {h.get('problems')}")

        rr = rep.get("resolve_report") or {}
        if rr:
            print(f"\n  resolve report   {json.dumps(rr, default=str)[:400]}")

    after = _sha256(real)
    print(f"\nreal ledger sha256 AFTER  {after}")
    if after == before:
        print("  UNCHANGED — the production ledger was never written to.")
    else:
        print("  *** THE REAL LEDGER CHANGED. This script is broken; "
              "investigate before running anything else.")
        return 1

    print("\nNothing was graded. The irreversible step is attended:")
    print("    python -m scripts.resolve_campaign_ledger --commit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
