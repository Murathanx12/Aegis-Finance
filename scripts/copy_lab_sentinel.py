"""Report whether each copy-lab lane is WORKING, REFUSING, or DEAD.

    python -m scripts.copy_lab_sentinel
    python -m scripts.copy_lab_sentinel --json out.json

Exit code is 1 when any ACTIVE lane is FAIL, so this can gate a scheduled run.
Dormant lanes never affect the exit code -- a check that can only ever be red is
not a check (`reference_gate_that_cannot_go_green`).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services.copy_lab import sentinel  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    healths = sentinel.sweep()
    print("COPY-LAB SILENT CASH SENTINEL")
    print("=" * 78)
    print(sentinel.report(healths))

    if args.json:
        Path(args.json).write_text(
            json.dumps([asdict(h) for h in healths], indent=2, default=str),
            encoding="utf-8")
        print(f"\nreceipt -> {args.json}")

    failed = [h.lane_id for h in healths if h.status == sentinel.FAIL]
    if failed:
        print(f"\nFAIL: {failed}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
