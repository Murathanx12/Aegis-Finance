"""CLI for `backend.services.results_voice`: lead with results, then the claim line.

    python -m scripts.results_voice                       # newest run id roi + book_dna share
    python -m scripts.results_voice --run-id 2026-10-06T235345Z
    python -m scripts.results_voice --json                # one JSON summary line

Writes `paper_accounts/results_voice_<run>.json` + `.md` beside the receipts and
prints the headline block (the six lines of 2026-10-07, the BETA-ADJUSTED line and the LABEL
FALSE-FIRE RATES line (CH-55, 2026-11-16: how many accounts are ahead after removing beta x SPY
session by session, and how often each label fires on a random book -- also printed in brackets
beside every label), the "Distinct bets ahead of SPY" line, a
LABELS LOWERED line when a label fell, and CLAIMS PROMOTED last: "none" until a label rises
against the previous run's book_dna receipt). rc 2 = REFUSED (no pair / no rows), with why.
The family view of the same receipts: `python -m scripts.family_scorecard`.
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
    ap.add_argument("--out", default=None, help="write the voice (and a rebuilt book_dna) here, not beside "
                                                 "the receipts")
    ap.add_argument("--rebuild-dna", action="store_true",
                    help="re-run book_dna on the ROI receipt into --out (lanes not fetched, database "
                         "opened mode=ro); for receipts written before a book_dna field existed. mode=ro "
                         "opens immutable=1 when the WAL is empty (mode=ro created -wal/-shm beside the "
                         "live database) and mode=ro when the WAL holds rows (only the -shm mtime moves)")
    a = ap.parse_args(argv)
    try:                       # a cp1252 console must not crash the run AFTER the receipts are written
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    try:
        out = RV.run(a.run_id, Path(a.folder) if a.folder else RV.PA_DIR,
                     out_dir=Path(a.out) if a.out else None, rebuild_dna=a.rebuild_dna)
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
