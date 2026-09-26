"""Probe every subsystem once and print the table, DEAD/STALE/UNKNOWN first.

    python -m scripts.health_probe                 # table + receipt
    python -m scripts.health_probe --json          # the receipt on stdout
    python -m scripts.health_probe --only bars_panel,telegram_agent
    python -m scripts.health_probe --no-proc       # file-derived probes only

Writes `backend/data/optimus/health/health_<YYYYmmddTHHMMSSZ>.json` (never
overwritten), `HEALTH.md` (the latest table), one line in
`health_index.jsonl`, and `_state.json` (the previous counts the delta probes
diff against). Exit code: 1 if any DEAD, 2 if any STALE, 3 if every row is
UNKNOWN, else 0. Read-only everywhere else: no order, no model, no kill.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import system_health as SH            # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="derived-evidence health probes")
    ap.add_argument("--json", action="store_true", help="print the receipt as JSON")
    ap.add_argument("--only", default="", help="comma-separated probe names")
    ap.add_argument("--no-proc", action="store_true",
                    help="skip probes that shell out or open a socket")
    ap.add_argument("--no-write", action="store_true", help="do not write the receipt")
    a = ap.parse_args(argv)
    only = {x.strip() for x in a.only.split(",") if x.strip()} or None
    out = SH.run(ctx=SH.make_ctx(allow_proc=not a.no_proc), only=only,
                 persist=not a.no_write)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # type: ignore[attr-defined]
    except Exception:                                                # noqa: BLE001
        pass
    if a.json:
        print(json.dumps(out, indent=1, default=str))
    else:
        print(SH.render_table(out))
        if out.get("path"):
            print(f"-> {out['path']}")
    return int(out["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
