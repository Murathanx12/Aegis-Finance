"""Re-append forecasts that a `git reset --hard` destroyed.

WHAT HAPPENED, 2026-09-24
=========================
`predictions.jsonl` is a TRACKED file that accumulates rows continuously. A
force-push was rejected by branch protection (correctly), and the local branch
was realigned with `git reset --hard origin/main` -- which discarded every
uncommitted working-tree change to tracked files, including ~1,200 ledger rows:
40 forecasts written this session, and roughly 600 written by other processes
between 2026-09-11 and 2026-09-22 that had never been committed.

`reset --hard` was used to fix a COMMIT MESSAGE. It should never have touched
the working tree at all; `git reset --soft` or simply leaving the message
mangled were both correct and non-destructive.

WHAT THIS RESTORES, AND WHAT IT CANNOT
======================================
The 40 forecasts survive in `investigator/forecasts_<date>.json`, written by the
forecaster BEFORE the ledger append, with ticker, both probabilities, the cited
evidence and the falsifier. They are re-appended under their original
`made_at`, because that is when they were actually made and backdating is not
what is happening here -- the record simply exists twice, once in a receipt and
once in the ledger.

The ~600 rows from other processes are NOT recoverable from this repo. They
existed only in the working tree. They are reported, not quietly forgotten.

`input_snapshot` is the receipt reference rather than the original evidence
packet, and every restored row says so. A restored record that pretended to
carry its original inputs would be a worse artefact than a missing one.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def main(argv=None) -> int:
    from backend.services import belief_state as B

    src = (REPO / "backend" / "data" / "optimus" / "investigator"
           / f"forecasts_{date.today()}.json")
    if not src.exists():
        print(f"no receipt at {src}")
        return 2
    d = json.loads(src.read_text(encoding="utf-8"))
    made_at = d["written_utc"]

    have = {(r.get("ticker"), r.get("specialist"))
            for r in B.read_predictions()
            if r.get("specialist") == d["specialist"]}

    recs, skipped = [], 0
    for r in d["rows"]:
        if "probability" not in r:
            continue
        if (r["ticker"], d["specialist"]) in have:
            skipped += 1
            continue
        recs.append(B.make_prediction(
            ticker=r["ticker"], specialist=d["specialist"],
            observable=B.Observable.BEATS_BENCHMARK,
            horizon_days=int(d["horizon_days"]),
            probability=float(r["probability"]), benchmark="SPY",
            thesis=json.dumps(r.get("facts_used"))[:1200],
            counter_thesis=str(r.get("falsifier"))[:800],
            next_observable=json.dumps(r.get("what_is_missing"))[:300],
            model=str(d["model"]), model_version="evidence_v2",
            prompt="see receipt", made_at=made_at,
            input_snapshot={"restored_from": str(src.name),
                            "note": "the original evidence packet was not "
                                    "preserved in the receipt; this row is a "
                                    "restoration and says so"},
            licence="PRODUCT_EXPERIMENT",
            notes_text=(f"RESTORED from {src.name} after a `git reset --hard` "
                        f"discarded uncommitted ledger rows. raw "
                        f"{r.get('raw_probability')} shrunk to {r['probability']}")))
    if recs:
        B.append(recs)
    print(f"restored {len(recs)}, already present {skipped}")
    print(f"ledger now {len(B.read_predictions()):,} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
