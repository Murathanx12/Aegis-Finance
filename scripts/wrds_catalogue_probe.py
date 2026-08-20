"""WRDS-CATALOGUE-PROBE — what is actually there, and how big is it?

"Pull everything" needs a definition before it can be executed honestly.
The account can SELECT from 46 schemas holding several thousand tables,
and some of them (TAQ NBBO, per-year OptionMetrics quote tables, TRACE)
are individually larger than the disk. A script that tried to pull them
all would die partway and leave a substrate nobody could describe.

So this probe runs first and transfers no data. For every table in every
SELECT-OK schema it records name, column count, and an ESTIMATED row
count from `pg_class.reltuples` — the planner's own statistic, which
costs nothing, rather than `COUNT(*)`, which would scan.

The output is a catalogue that lets the pull be split into:
  - tractable and worth having            -> pull
  - enormous, or an intraday quote firehose -> SKIP, and record the row
    count so the decision is visible rather than silent

Canon: a refusal is a finding. Anything skipped is listed with its size,
so "we don't have it" is never confused with "it isn't there".

    python -m scripts.wrds_catalogue_probe
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config                        # noqa: E402
from scripts.wrds_training_pull import _conn                 # noqa: E402

OUT = _config.OPTIMUS_LEDGER_DIR / "wrds"
MAP = OUT / "entitlement_map_2026-08-19.json"
RECEIPT = OUT / "catalogue_probe_2026-08-20.json"


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass
    ent = json.loads(MAP.read_text(encoding="utf-8"))
    schemas = sorted(k for k, v in ent["candidates"].items()
                     if v.get("select_ok"))
    print(f"{len(schemas)} SELECT-OK schemas")

    conn = _conn()
    cur = conn.cursor()
    rows = []
    for sch in schemas:
        cur.execute(
            "SELECT c.relname, c.reltuples::bigint, "
            "       COUNT(a.attname)::int AS ncols "
            "FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "LEFT JOIN pg_attribute a ON a.attrelid = c.oid "
            "     AND a.attnum > 0 AND NOT a.attisdropped "
            "WHERE n.nspname = %s AND c.relkind IN ('r','v','m','f','p') "
            "GROUP BY c.relname, c.reltuples "
            "ORDER BY c.reltuples DESC", (sch,))
        got = cur.fetchall()
        for name, tup, ncols in got:
            rows.append({"schema": sch, "table": name,
                         "est_rows": int(tup) if tup and tup > 0 else 0,
                         "n_cols": int(ncols or 0)})
        print(f"  {sch:30s} {len(got):>5d} tables")
    conn.close()

    rows.sort(key=lambda r: -r["est_rows"])
    total = sum(r["est_rows"] for r in rows)
    buckets = {"le_1M": 0, "1M_10M": 0, "10M_100M": 0, "gt_100M": 0}
    for r in rows:
        n = r["est_rows"]
        if n <= 1_000_000:
            buckets["le_1M"] += 1
        elif n <= 10_000_000:
            buckets["1M_10M"] += 1
        elif n <= 100_000_000:
            buckets["10M_100M"] += 1
        else:
            buckets["gt_100M"] += 1

    res = {"probe": "WRDS-CATALOGUE-PROBE-1",
           "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "n_schemas": len(schemas), "n_tables": len(rows),
           "total_est_rows": total, "size_buckets": buckets,
           "note": "est_rows is pg_class.reltuples (planner statistic), "
                   "not COUNT(*) — approximate, and 0 means never "
                   "ANALYZEd rather than empty",
           "tables": rows}
    RECEIPT.write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(f"\n{len(rows):,} tables, {total:,} estimated rows total")
    print(f"buckets: {buckets}")
    print("\nlargest 15:")
    for r in rows[:15]:
        print(f"  {r['schema']}.{r['table']:<38s} "
              f"{r['est_rows']:>15,} rows  {r['n_cols']:>3d} cols")
    print(f"\nreceipt -> {RECEIPT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
