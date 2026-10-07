"""Split `predictions.jsonl` into sealed monthly forecast/resolution streams (attended).

    python -m scripts.ledger_split --plan                         # the plan, human-readable; writes nothing
    python -m scripts.ledger_split --plan --history               # + replay every committed version (git)
    python -m scripts.ledger_split --plan --json > plan.json      # machine-readable plan
    python -m scripts.ledger_split --apply --expect-sha256 <sha>  # migrate what the plan fingerprinted
    python -m scripts.ledger_split --apply --plan-file plan.json  # ... or against the saved plan
    python -m scripts.ledger_split --status                       # which backend answers, and its seals
    python -m scripts.ledger_split --discard-partial              # clean up an interrupted --apply
    python -m scripts.ledger_split --quarantine-torn-tail         # move a crash's torn tail aside (attended)

THE ONE ATTENDED LOCAL OPERATION
================================
1. Stop the writers (the scheduled sim owner, the grader, any night job) and
   restart nothing until step 4: a process running code from BEFORE this change
   does not take the ledger lock.
2. `python -m scripts.ledger_split --plan --history` -- read it; it ends with the
   exact `--apply` command, carrying the legacy file's sha256.
3. Run that command. It re-hashes the file, refuses if one byte moved since the
   plan, writes and verifies the streams, re-hashes the legacy file again,
   writes the marker (the switch), seals the closed months, and verifies the
   result through the real reader.
4. Commit what it names, restart the writers.

Rollback before the switch is automatic (the run removes what it wrote). After
the switch the legacy file is still byte-for-byte the one planned: deleting the
marker returns every reader to it, at the cost of any forecast written to the
streams since -- which `--status` would list, so do it only immediately.

Exit codes: 0 done (or already applied), 2 refused, 1 unexpected error.
The design and the migration semantics: `backend/services/forecast_ledger.py`,
`backend/services/forecast_ledger_migration.py`,
`docs/research_notes/2026-10-07/ledger_split_cloud_2026-10-07.md`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def main(argv: list[str] | None = None) -> int:
    from backend.services import forecast_ledger as FL
    from backend.services import forecast_ledger_migration as MIG

    ap = argparse.ArgumentParser(prog="ledger_split", description=__doc__.split("\n\n")[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true", help="print the plan; write nothing")
    mode.add_argument("--apply", action="store_true", help="migrate (attended)")
    mode.add_argument("--status", action="store_true", help="backend, files, chain")
    mode.add_argument("--discard-partial", action="store_true",
                      help="remove an interrupted apply's files (refused after the switch)")
    mode.add_argument("--quarantine-torn-tail", action="store_true",
                      help="move a torn tail in an open stream file to a dated .fragment file "
                           "(attended; refused when the fragment is a complete JSON row)")
    ap.add_argument("--legacy", default=None, help="legacy ledger path (default: config)")
    ap.add_argument("--expect-sha256", default=None, help="the source sha256 --plan printed")
    ap.add_argument("--plan-file", default=None, help="a saved `--plan --json` output")
    ap.add_argument("--history", action="store_true",
                    help="with --plan: replay every committed version through git")
    ap.add_argument("--no-history", action="store_true",
                    help="with --apply: skip the git replay on the genesis record")
    ap.add_argument("--json", action="store_true", help="print JSON instead of text")
    a = ap.parse_args(argv)
    legacy = Path(a.legacy) if a.legacy else None
    try:
        if a.plan:
            p = MIG.plan(legacy, history=a.history)
            print(json.dumps(p, indent=1, ensure_ascii=False, default=str) if a.json
                  else MIG.render_plan(p))
            return 0 if p.get("status") in ("READY", "ALREADY_APPLIED") else 2
        if a.apply:
            r = MIG.apply(legacy, expect_sha256=a.expect_sha256,
                          plan_file=Path(a.plan_file) if a.plan_file else None,
                          history=not a.no_history)
            print(json.dumps(r, indent=1, ensure_ascii=False, default=str))
            return 0 if r["status"] in ("APPLIED", "ALREADY_APPLIED") else 1
        if a.quarantine_torn_tail:
            print(json.dumps(FL.quarantine_torn_tail(legacy), indent=1, ensure_ascii=False))
            return 0
        if a.discard_partial:
            print(json.dumps(MIG.discard_partial(legacy), indent=1))
            return 0
        s = FL.status(legacy, rehash=True)
        print(json.dumps(s, indent=1, ensure_ascii=False, default=str))
        return 0 if s["status"] == "ok" else 1
    except FL.ForecastLedgerError as exc:
        print(f"REFUSED: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
