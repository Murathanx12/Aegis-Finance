"""Publish the public pages' receipts into the TRACKED `backend/data/public_receipts/` (C15).

    python -m scripts.publish_receipts            # build, sanitise, verify, write + MANIFEST.json
    python -m scripts.publish_receipts --dry-run  # print the manifest, write nothing
    python -m scripts.publish_receipts --commit   # publish, then commit ONLY the folder on `main`
                                                  # and push (refuses on any other branch; C15 H1)

Every copy passes the routers' deny-by-default sanitiser at COPY time (a tracked folder
in a public repo is a second publication channel). The daily commit of the folder is what
makes the pages public. Exit 0 = OK, 1 = DEGRADED (some pages kept their previous copy),
2 = REFUSED (over the size budget, or nothing could be published; nothing written).
See `backend/services/publish_receipts.py`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import publish_receipts as PR  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="publish_receipts")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--commit", action="store_true",
                    help="after publishing, commit ONLY backend/data/public_receipts/ and push main")
    a = ap.parse_args(argv)
    if a.commit and a.dry_run:
        print("REFUSED: --commit and --dry-run together make no sense")
        return 2
    out = PR.publish(dry_run=a.dry_run)
    for name, e in out["kinds"].items():
        print(f"{name:<20} {e.get('status'):<9} {e.get('bytes') or 0:>10,} B  "
              f"{e.get('why') or ''}{' (kept previous copy)' if e.get('kept_previous') else ''}")
    print(f"{out['status']}: {out['total_bytes']:,} / {out['max_bytes']:,} bytes; written={out['written']}"
          + (f"; {out['why']}" if out.get("why") else ""))
    rc = {"OK": 0, "DEGRADED": 1}.get(out["status"], 2)
    if a.commit:
        c = PR.commit_public_receipts()
        line = f"commit: {c['status']}"
        if c["status"] == "COMMITTED":
            line += f" {c.get('commit')} pushed={c.get('pushed')}"
            if c.get("push_refused"):
                line += f" ({c['push_refused']})"
        print(line)
        for r in c.get("reasons") or []:
            print(f"  REFUSED: {r}")
        if c["status"] != "COMMITTED" or c.get("pushed") is False:
            rc = 2
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
