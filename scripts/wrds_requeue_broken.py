"""Requeue substrate-verification failures for re-pull.

Reads substrate_verification.json, and for every table whose verdict says the
FILE is wrong (TRUNCATED / SHORT_MAJOR — not the minor server-vintage drift
verdicts) it: deletes the parquet (a truncated file left in place would be
read forever as a completed table — the resumability contract), drops the
table's `pulled` row from the manifest, and appends a `failed` row whose
error names WHY, so `wrds_pull_catchup` re-pulls it with all of its guards.

Never touches EXTRA (file > server = the server lost rows to vintage drift;
our file is the better artifact) or UNVERIFIED (status unknown — deleting an
unverified file would destroy possibly-good data on no evidence; re-VERIFY
it instead).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WRDS = ROOT / "backend" / "data" / "optimus" / "wrds"
BULK = WRDS / "bulk"
MANIFEST = WRDS / "pull_everything_manifest.json"
VERIFICATION = WRDS / "substrate_verification.json"

REQUEUE_VERDICTS = {"TRUNCATED", "SHORT_MAJOR"}

#: Keep in lockstep with wrds_pull_everything/catchup. A file holding EXACTLY
#: this many rows is truncated by construction — the old pull code wrote the
#: capped result instead of refusing (boardex.na_wrds_individual_networks sat
#: at exactly 8,000,000 labeled UNVERIFIED because the server-side COUNT
#: timed out; the file's own row count already answered the question).
MAX_ROWS = 8_000_000


def _is_requeueable(v: dict) -> bool:
    if v.get("verdict") in REQUEUE_VERDICTS:
        return True
    return (v.get("verdict") == "UNVERIFIED"
            and v.get("rows_in_file") == MAX_ROWS)


def main() -> int:
    ver = json.loads(VERIFICATION.read_text(encoding="utf-8"))
    tables = ver.get("tables") or ver.get("files") or {}
    items = (tables.items() if isinstance(tables, dict)
             else [(t.get("name"), t) for t in tables])
    bad = {name: v for name, v in items
           if isinstance(v, dict) and _is_requeueable(v)}
    if not bad:
        print("nothing to requeue — no TRUNCATED/SHORT_MAJOR verdicts")
        return 0

    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    pulled = man.get("pulled") or []
    by_name = {p.get("name"): p for p in pulled if isinstance(p, dict)}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    requeued = []
    for name, v in sorted(bad.items()):
        row = by_name.get(name)
        if row is None:
            print(f"  SKIP {name}: no pulled row in the manifest — cannot "
                  f"reconstruct its plan metadata; requeue by re-running "
                  f"the planner instead")
            continue
        schema, table = row.get("schema"), row.get("table")
        fn = BULK / f"{schema}__{table}.parquet"
        if fn.exists():
            fn.unlink()
        failed_row = {k: row[k] for k in
                      ("schema", "table", "name", "est_rows", "n_cols",
                       "id_col", "date_col", "tier") if k in row}
        failed_row["error"] = (
            f"REQUEUED {now}: substrate verification verdict "
            f"{v.get('verdict')} — file deleted, must re-pull")
        man.setdefault("failed", []).append(failed_row)
        requeued.append(name)
        print(f"  REQUEUED {name} ({v.get('verdict')}) — parquet deleted")

    man["pulled"] = [p for p in pulled if p.get("name") not in set(requeued)]
    # The pull is no longer complete: say so, the same honesty rule the
    # catchup itself follows.
    if requeued:
        man.pop("completed_at", None)
        man["partial_at"] = now
        man["incomplete_reason"] = (
            f"{len(requeued)} table(s) requeued by substrate verification")
    MANIFEST.write_text(json.dumps(man, indent=2, default=str),
                        encoding="utf-8")
    print(f"\n{len(requeued)} requeued -> run scripts/wrds_pull_catchup.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
