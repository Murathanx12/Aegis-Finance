"""Find and quarantine parquets that are an ARBITRARY subset of their table.

`wrds_pull_everything` and the first version of `wrds_pull_catchup` both ran
`SELECT * FROM t LIMIT 8000000` with **no ORDER BY**. When the table has more
rows than the cap, that returns an unspecified 8,000,000 of them — not a
prefix, not a defined sample, and not the same set on a re-run.

The original pull never hit this, because every table large enough to hit the
cap died on its 90-second timeout first. Fixing the timeout made the big
tables succeed for the first time and exposed it. Measured 2026-08-20:

    crsp.daily_nav_ret  186,442,964 true rows -> 8,000,000 kept =  4.3%
    comp.aco_transa      47,158,539 true rows -> 8,000,000 kept = 17.0%
    optionm.hvold2013    12,853,308 true rows -> 8,000,000 kept = 62.2%
    crsp.monthly_tna     10,011,987 true rows -> 8,000,000 kept = 79.9%

A file called `crsp__daily_nav_ret.parquet` holding 4.3% of the table, with
nothing recording that, is worse than an absent file: it joins cleanly and
silently drops 96% of the data. That is the house failure mode with a parquet
extension.

This moves every such file to `bulk/_quarantine_truncated/` and writes a
record naming the true size, so the cap becomes a DECLARED decision (raise it,
partition the table, or do without) instead of a hole nobody knows about.

    python -m scripts.wrds_quarantine_truncated --dry-run
    python -m scripts.wrds_quarantine_truncated
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

warnings.filterwarnings("ignore")

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.wrds_pull_everything import BULK, MANIFEST, MAX_ROWS  # noqa: E402
from scripts.wrds_training_pull import OUT, _conn                  # noqa: E402

QUARANTINE = BULK / "_quarantine_truncated"
RECORD = OUT / "truncated_quarantine.json"

#: A parquet being STREAMED has no footer until the writer closes it, so it
#: reads as corrupt while it is being written. This tool DELETES files it
#: judges corrupt — so run against a live pull, it would destroy the table
#: currently landing. Caught 2026-08-21: `tr_ibes__pansum.parquet` and
#: `comp__sec_mshare.parquet` both read as unreadable and both had been
#: touched within 15 seconds; one had logged `pulled` 13 seconds earlier.
#:
#: Files modified inside this window are SKIPPED, not judged. The earlier
#: deletions were safe only because the pull had been killed first — which
#: was luck, not a property of the tool.
IN_FLIGHT_SECONDS = 900


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    import pyarrow.parquet as pq

    import time as _time
    now = _time.time()
    suspects, corrupt, in_flight = [], [], []
    for f in sorted(BULK.glob("*.parquet")):
        if now - f.stat().st_mtime < IN_FLIGHT_SECONDS:
            # Possibly being written RIGHT NOW. Never judged, never deleted.
            in_flight.append(f.name)
            continue
        try:
            n = pq.ParquetFile(f).metadata.num_rows
        except Exception as exc:                                # noqa: BLE001
            # A half-written parquet from a killed run. The streaming writer
            # only deletes on EXCEPTION, and SIGKILL is not an exception — so
            # the file survives, and resumability (which keys off existence)
            # treats it as a completed table forever. Same failure class as
            # the truncation below: a file that reads as done and is not.
            corrupt.append((f, str(exc)[:80]))
            continue
        if n == MAX_ROWS:
            suspects.append((f, n))

    print(f"{len(suspects)} parquet(s) sit exactly at the {MAX_ROWS:,} cap")
    print(f"{len(corrupt)} parquet(s) are UNREADABLE (killed mid-write)")
    if in_flight:
        print(f"{len(in_flight)} parquet(s) SKIPPED — modified in the last "
              f"{IN_FLIGHT_SECONDS}s, possibly being written by a running "
              f"pull. Re-run when no pull is active to judge them.")
        for x in in_flight[:8]:
            print(f"  IN-FLIGHT {x}")
    for f, why in corrupt:
        print(f"  CORRUPT   {f.name}: {why}")
    if not a.dry_run:
        for f, _ in corrupt:
            f.unlink()          # deleted, not quarantined: there is nothing
            #                     in it to keep, and it must be re-pulled
        if corrupt:
            print(f"deleted {len(corrupt)} unreadable file(s) — they will be "
                  f"re-pulled on the next catch-up run")
    if not suspects:
        return 0

    conn = _conn()
    cur = conn.cursor()
    cur.execute("SET statement_timeout = 180000")
    rows = []
    for f, n in suspects:
        schema, _, table = f.stem.partition("__")
        try:
            cur.execute(f"SELECT count(*) FROM {schema}.{table}")
            true_n = int(cur.fetchone()[0])
        except Exception as exc:                                # noqa: BLE001
            conn.rollback()
            # Cannot confirm: treat as TRUNCATED anyway. An unverifiable file
            # at exactly the cap is not evidence of a table with exactly
            # 8,000,000 rows.
            true_n = None
            print(f"  {schema}.{table}: count failed ({str(exc)[:60]})")
        complete = (true_n is not None and true_n <= MAX_ROWS)
        rows.append({"name": f"{schema}.{table}", "file": f.name,
                     "rows_in_file": n, "true_rows": true_n,
                     "complete": complete,
                     "kept_pct": (round(100.0 * n / true_n, 2)
                                  if true_n else None)})
        flag = "COMPLETE" if complete else "TRUNCATED"
        print(f"  {flag:<9s} {schema}.{table:<28s} file={n:>10,} "
              f"true={true_n if true_n is not None else '?':>13} "
              f"kept={rows[-1]['kept_pct']}%")
    conn.close()

    truncated = [r for r in rows if not r["complete"]]
    print(f"\n{len(truncated)} truncated, {len(rows) - len(truncated)} "
          f"genuinely complete at the cap")
    if a.dry_run:
        print("dry run — nothing moved")
        return 0

    QUARANTINE.mkdir(parents=True, exist_ok=True)
    for r in truncated:
        src = BULK / r["file"]
        if src.exists():
            src.rename(QUARANTINE / r["file"])
    RECORD.write_text(json.dumps({
        "quarantined_at": datetime.now(timezone.utc).isoformat(
            timespec="seconds"),
        "cap": MAX_ROWS,
        "why": ("SELECT * ... LIMIT cap with no ORDER BY returns an arbitrary "
                "subset. These files are not samples with a definition and "
                "must not be joined as if they were the table."),
        "n_quarantined": len(truncated),
        "n_corrupt_deleted": len(corrupt),
        "n_skipped_in_flight": len(in_flight),
        "skipped_in_flight": in_flight,
        "corrupt_deleted": [f.name for f, _ in corrupt],
        "tables": rows,
    }, indent=2), encoding="utf-8")
    print(f"moved {len(truncated)} file(s) -> {QUARANTINE}")
    print(f"record -> {RECORD}")

    # Drop them from the manifest's `pulled` list too: a table sitting in
    # `pulled` is a table nothing will ever retry.
    if MANIFEST.exists():
        man = json.loads(MANIFEST.read_text(encoding="utf-8"))
        names = {r["name"] for r in truncated}
        names |= {f.stem.replace("__", ".", 1) for f, _ in corrupt}
        before = len(man.get("pulled", []))
        man["pulled"] = [p for p in man.get("pulled", [])
                         if p.get("name") not in names]
        man["truncated_quarantined"] = rows
        MANIFEST.write_text(json.dumps(man, indent=2, default=str),
                            encoding="utf-8")
        print(f"manifest pulled: {before} -> {len(man['pulled'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
