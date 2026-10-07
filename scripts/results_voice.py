"""CLI for `backend.services.results_voice`: lead with results, then the claim line.

    python -m scripts.results_voice                       # newest run id roi + book_dna share
    python -m scripts.results_voice --run-id 2026-10-06T235345Z
    python -m scripts.results_voice --json                # one JSON summary line

Writes `paper_accounts/results_voice_<run>.json` + `.md` beside the receipts and
prints the six-line headline block. rc 2 = REFUSED (no pair / no rows), with why.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import results_voice as RV  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="results_voice")
    ap.add_argument("--run-id", default=None, help="YYYY-MM-DDTHHMMSSZ; default: newest shared run id")
    ap.add_argument("--folder", default=None, help="paper_accounts folder (default: the ledger's)")
    ap.add_argument("--json", action="store_true", help="print a one-line JSON summary")
    a = ap.parse_args(argv)
    try:
        out = RV.run(a.run_id, Path(a.folder) if a.folder else RV.PA_DIR)
    except RV.ResultsVoiceRefused as exc:
        msg = {"status": "refused", "why": str(exc)}
        print(json.dumps(msg) if a.json else f"REFUSED results_voice: {exc}")
        return 2
    lines = out["voice"]["headline_lines"]
    if a.json:
        print(json.dumps({"status": "ok", "run_id": out["run_id"], "json": out["json"], "md": out["md"],
                          "headline_lines": lines}))
    else:
        print("\n".join(lines))
        print(f"wrote {out['json']} and {out['md']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
