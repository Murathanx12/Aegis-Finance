"""WRDS ENTITLEMENT PROBE — what we can actually READ, not what the catalogue lists.

WHY THIS EXISTS, AND WHY THE OBVIOUS PROBE IS WRONG
===================================================
On 2026-08-31 three checks disagreed about whether HKU's WRDS subscription
includes RavenPack (the historical-news archive the roadmap wants, 2000-2026):

  1. `catalogue_probe_2026-08-20.json` listed 46 schemas, no `ravenpack`.
     -> read as NOT entitled.
  2. A live `pg_namespace` query listed **1,316** schemas INCLUDING
     `ravenpack_full`, `ravenpack_dj`, `ravenpack_web`, `rpna`.
     -> read as entitled. The old probe looked partial.
  3. `select * from ravenpack_full.rpa_full_equities_2024 limit 2`
     -> **permission denied for schema ravenpack_full.**

Check 3 is the only one that answers the question. WRDS shows every subscriber
the FULL catalogue -- schema names, table names and even column definitions --
regardless of entitlement, because the catalogue is documentation. Visibility is
not access, and `information_schema` will happily describe 52 columns of a table
you may not read a single row of.

So this probe attempts an actual bounded SELECT against one table per schema
family and records the grant. It is the same lesson as the artery: **verify a
link at its FAR end.** A schema listing is the near end.

`LIMIT 1` on an unqualified table can still plan a scan on a partitioned parent,
so each probe runs under a statement timeout and its failure is recorded rather
than raised -- a probe that dies on the first denial tells you about one schema.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "backend" / "data" / "optimus" / "wrds"

HOST, PORT, DB, USER = "wrds-pgdata.wharton.upenn.edu", 9737, "wrds", "murathan12"

#: (family, schema, table, why we care). One representative table per family --
#: the grant is per SCHEMA, so a single readable table settles the family.
TARGETS: tuple[tuple[str, str, str, str], ...] = (
    ("ravenpack-full", "ravenpack_full", "rpa_full_equities_2024",
     "the historical news archive the roadmap wants: 2000-2026, entity-tagged"),
    ("ravenpack-dj", "ravenpack_dj", "rpa_djpr_equities_2024",
     "Dow Jones press-release edition"),
    ("ravenpack-web", "ravenpack_web", "rpa_web_equities_2024",
     "web edition"),
    ("ravenpack-common", "ravenpack_common", "rpa_taxonomy",
     "event taxonomy + entity mappings; useless without a data edition"),
    ("crsp-daily", "crsp", "dsf", "prices; already pulled 1993-2024"),
    ("ibes", "ibes", "actu_epsus", "analyst actuals; the revision-velocity test"),
    ("ibes-detail", "tr_ibes", "detu_epsus",
     "per-analyst detail -- what revision VELOCITY needs"),
    ("ibes-guidance", "tr_ibes_guidance", "guidance",
     "company guidance events"),
    # NOTE: these four table names were GUESSED in the first run and came back
    # NO_SUCH_TABLE, which is NOT the same answer as NOT_ENTITLED and must never
    # be recorded as one. Resolved against pg_tables and re-probed.
    ("taq-ms", "taqm_2024", "complete_nbbo_20240102",
     "millisecond NBBO: REAL quoted spreads, one day per table"),
    ("taq-liquidity", "contrib_liquidity_taq", "ilc",
     "PRE-COMPUTED intraday liquidity measures -- answers the thin-name cost "
     "question without touching raw TAQ"),
    ("patents", "wrdsapps_patents", "uspatents_meta", "innovation events"),
    ("boardex", "boardex_na", "na_wrds_company_profile", "people/board network"),
    ("13f", "tr_13f", "s34", "institutional holdings"),
    ("audit", "audit_audit_comp", "f01_auditor_event",
     "auditor changes: a distress event"),
    ("compustat", "comp", "funda", "fundamentals"),
    ("optionmetrics", "optionm", "opprcd2023", "option chains"),
)


def probe(cur, schema: str, table: str) -> dict:
    """Attempt a bounded read. Returns the grant, never raises."""
    try:
        cur.execute("SET LOCAL statement_timeout = 20000")
        cur.execute(f'SELECT 1 FROM "{schema}"."{table}" LIMIT 1')
        cur.fetchall()
        return {"readable": True, "detail": "SELECT returned"}
    except Exception as exc:                                        # noqa: BLE001
        msg = str(exc).strip().splitlines()[0][:200]
        if "permission denied" in msg.lower():
            kind = "NOT_ENTITLED"
        elif "does not exist" in msg.lower():
            kind = "NO_SUCH_TABLE"
        elif "timeout" in msg.lower() or "canceling" in msg.lower():
            kind = "TIMEOUT"
        else:
            kind = "ERROR"
        return {"readable": False, "denial": kind, "detail": msg}


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                           # noqa: BLE001
            pass
    os.environ.setdefault("PGPASSFILE",
                          os.path.expandvars(r"%APPDATA%\postgresql\pgpass.conf"))
    import psycopg2

    conn = psycopg2.connect(host=HOST, port=PORT, dbname=DB, user=USER,
                            sslmode="require", connect_timeout=20)
    conn.autocommit = False
    rows = []
    print(f"WRDS entitlement probe -- {len(TARGETS)} families, bounded SELECT each\n")
    for family, schema, table, why in TARGETS:
        cur = conn.cursor()
        r = probe(cur, schema, table)
        conn.rollback()                 # a denial aborts the tx; clear it
        cur.close()
        mark = "READ " if r["readable"] else f"{r.get('denial', 'FAIL'):<12}"
        print(f"  {mark}  {family:<16} {schema}.{table}")
        if not r["readable"]:
            print(f"                 {r['detail'][:110]}")
        rows.append({"family": family, "schema": schema, "table": table,
                     "why": why, **r})

    # Which schemas the CATALOGUE lists, for the contrast that matters.
    cur = conn.cursor()
    cur.execute("select nspname from pg_namespace where nspname !~ '^pg_' "
                "and nspname <> 'information_schema'")
    listed = sorted(r[0] for r in cur.fetchall())
    cur.close()
    conn.close()

    readable = [r["family"] for r in rows if r["readable"]]
    denied = [r["family"] for r in rows if not r["readable"]]
    payload = {
        "probe": "WRDS-ENTITLEMENT-PROBE-1",
        "at": datetime.now(timezone.utc).isoformat(),
        "method": ("bounded SELECT per schema family. The catalogue lists every "
                   "schema to every subscriber regardless of entitlement, and "
                   "information_schema will describe columns of tables you may "
                   "not read -- so a schema listing CANNOT answer this and the "
                   "2026-08-20 catalogue probe did not."),
        "schemas_listed_by_catalogue": len(listed),
        "readable_families": readable,
        "denied_families": denied,
        "results": rows,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    dst = OUT / "entitlement_probe.json"
    dst.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"\ncatalogue lists {len(listed)} schemas; "
          f"{len(readable)} of {len(rows)} probed families are READABLE")
    print(f"  readable: {', '.join(readable) or 'none'}")
    print(f"  denied:   {', '.join(denied) or 'none'}")
    print(f"\nreceipt -> {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
