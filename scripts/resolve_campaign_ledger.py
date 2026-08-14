"""Resolve the CAMPAIGN_FORWARD ledger — locally, attended, with a receipt.

    python -m scripts.resolve_campaign_ledger --dry-run     # what would grade
    python -m scripts.resolve_campaign_ledger --commit      # grade and receipt

WHY THIS IS NOT A SCHEDULER JOB
===============================
The campaign's forward ledger holds ~20,073 records and is the evidence
ABLATION_FWD certifies against. Writing outcomes into it is the most
consequential write in the programme: a record graded on the wrong price panel,
or graded twice, or graded against a window that had not closed, cannot be
un-graded — and the campaign's verdicts are downstream of every one of them.

So it runs attended, on a machine where the frozen artifacts are readable, and
every run leaves a dated receipt in `docs/receipts/` that says what it graded
and against what. The production ledger is a different population with a
different resolver (`pi_ledger_resolve`), and neither may touch the other.

WHAT IT REFUSES
===============
* to run against the LIVE_FORWARD ledger, ever;
* to run against a file holding more than one population — resolution rewrites
  the whole file, so grading a mixed ledger grades the other population too;
* to write anything without `--commit`. The default is a dry run, because the
  expensive mistake here is an accidental one.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.services import evidence_population as EP           # noqa: E402
from backend.services.ledger_resolver import (assert_single_population,  # noqa: E402
                                              resolve_due)

POPULATION = EP.EvidencePopulation.CAMPAIGN_FORWARD
RECEIPTS_DIR = Path(__file__).resolve().parents[1] / "docs" / "receipts"


def _print_lineage(lin: dict) -> None:
    print(f"\npopulation        {lin['evidence_population']}")
    print(f"  ledger_id       {lin['ledger_id']}")
    print(f"  path            {lin['ledger_path']}")
    print(f"  records         {lin['record_count']}")
    print(f"  first / last    {lin['first_record_at']} / {lin['last_record_at']}")
    print(f"  provenance      {lin['provenance_sha256']}")
    print(f"  source_commit   {lin['source_commit']}")
    print(f"  paths coincide  {lin['paths_coincide']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="resolve_campaign_ledger")
    ap.add_argument("--commit", action="store_true",
                    help="actually grade and write the receipt")
    ap.add_argument("--dry-run", action="store_true",
                    help="the default; report what is due and stop")
    ap.add_argument("--as-of", default=None, help="grade as of this date")
    a = ap.parse_args(argv)

    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass

    today = date.fromisoformat(a.as_of) if a.as_of else date.today()
    path = EP.ledger_path(POPULATION)

    print("=" * 70)
    print("CAMPAIGN_FORWARD RESOLUTION — attended, local, receipted")
    print("=" * 70)
    lin = EP.lineage(POPULATION)
    _print_lineage(lin)

    try:
        found = assert_single_population(path, POPULATION.value)
    except EP.PopulationCrossWrite as exc:
        print(f"\nREFUSED: {exc}")
        return 2
    print(f"\nsingle population confirmed: {found}")

    due = [r for r in EP.read_population(POPULATION)
           if r.get("outcome") is None and not r.get("void_reason")
           and r.get("resolves_after")
           and date.fromisoformat(str(r["resolves_after"])[:10]) <= today]
    print(f"due as of {today}: {len(due)} record(s)")

    if not a.commit:
        print("\nDRY RUN — nothing was graded and nothing was written. "
              "Re-run with --commit to resolve.")
        return 0

    report = resolve_due(today=today, population=POPULATION.value)
    print(f"\nnewly_resolved   {report['newly_resolved']}")
    print(f"pending          {report['pending']}")
    print(f"overdue          {report['overdue']}")
    print(f"unpriceable      {len(report['unpriceable'])}")
    print(f"priced_from      {report['priced_from']}")

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RECEIPTS_DIR / f"campaign_resolution_{stamp}.json"
    out.write_text(json.dumps({
        "receipt": "CAMPAIGN_FORWARD resolution",
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "as_of": str(today),
        "lineage_before": lin,
        "lineage_after": EP.lineage(POPULATION),
        "report": report,
        "note": ("The campaign ledger is resolved attended and locally. The "
                 "production LIVE_FORWARD ledger was neither read nor written "
                 "by this run."),
    }, indent=2, default=str), encoding="utf-8")
    print(f"\nreceipt          {out}")
    print("COMMIT THIS RECEIPT alongside the ledger change.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
