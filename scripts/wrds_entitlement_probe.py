"""Probe what this WRDS account can actually SELECT — catalogue != entitlement.

    python -m scripts.wrds_entitlement_probe

For every schema on the server: does the account hold USAGE, and does a
1-row SELECT on a representative table succeed? Receipt lands in
backend/data/optimus/wrds/entitlement_map_<date>.json and is the ONLY
authority future pull scripts may cite for "we have this data".
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config                        # noqa: E402

OUT = _config.OPTIMUS_LEDGER_DIR / "wrds"

#: Schemas worth probing for the NN training-data programme, with one
#: representative table each. Names from WRDS's own postgres catalog
#: conventions; a missing table is reported, not fatal.
CANDIDATES = {
    # core, believed entitled (reference_wrds_access)
    "crsp": "dsf",
    "crsp_a_stock": "dsf",
    "comp": "fundq",
    "comp_na_daily_all": "fundq",
    "tr_ibes": "statsum_epsus",
    "ibes": "statsum_epsus",
    "optionm": "secprd1996",
    "optionm_all": "secprd1996",
    "taqm_2024": "wct_20240102",
    # WRDS analytics products (Murat's 2026-08-19 list)
    "wrdsapps_finratio": "firm_ratio",
    "wrdsapps_finratio_ibes": "firm_ratio_ibes",
    "wrdsapps": "firm_ratio",
    "wrdsapps_link_crsp_ibes": "ibcrsphist",
    "wrdsapps_link_crsp_optionm": "opcrsphist",
    "wrdsapps_link_crsp_taq": "taqmclink",
    "wrdsapps_link_crsp_bond": "bondcrsp_link",
    "wrdsapps_eushort": "eushort",
    "wrdsapps_patents": "patents_long",
    "wrdsapps_subsidiary": "wrds_subsidiary",
    "wrdsapps_evtstudy": "long_run",
    "wrds_lib_internal": "cosine_sim",
    "wrdssec": "wrds_forms",           # SEC filings / bag of words family
    "wrdssec_all": "wrds_forms",
    "wrds_insiders": "form345_table1",
    "wrds_sec_bow": "bow10k",
    "taqmsec": "cqm_20240102",
    "taq": "cq_20141231",
    "wrds_taq_iid": "iid_2024",        # intraday indicators
    "betasuite": "ff3_daily",
    "wrdsapps_betasuite": "ff3_daily",
    "factors_wrds": "signals",
    "wrdsapps_factors": "signals",
    "bondret": "bondret",
    "wrdsapps_bondret": "bondret",
    "ff": "factors_daily",             # Fama-French
    "ff_all": "factors_daily",
    "fisd": "fisd_mergedissue",        # Mergent FISD
    "trace": "trace_enhanced",
    "boardex": "na_wrds_company_profile",
    "audit": "auditnonreli",
    "issm": "nyam_1990",
    "phlx": "phlx_1980",
    "otc": "endofday",
    "msrb": "msrb",
    "world_indices": "worldindices",
    "wrdsapps_windices": "worldindices",
    "iri": "iri",
    "dmef": "dmef",
    "sp_indices": "idx_ann",
    "spgi": "idx_ann",
    "comph": "funda",                  # Compustat historical
    "compg": "g_funda",                # Compustat Global
    "compseg": "wrds_segmerged",       # segments
    "compa": "funda",
    "ciq": "wrds_keydev",              # Capital IQ Key Developments
    "ciq_keydev": "wrds_keydev",
    "tfn": "s34",                      # Thomson 13F
    "tr_13f": "s34",
    "wrds_13f": "wrds_13f_holdings",
    "lseg_esg": "esg_scores",
    "trucost": "trucost",
    "ravenpack_sample": "rp_equities",
    "eventus": "eventus",
    "fjc": "civil_terminations",
    "frb": "rates_daily",
    "phil_fed": "spf",
    "public": "msf",
    "macrofin": "cross_section",
    "contrib": "contrib",
    "contrib_general": "kfrench_factors",
    "pwt": "pwt",
    "zacks_sample": "zacks_prices",
    "hfr_sample": "hfr",
}


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass
    os.environ.setdefault("PGPASSFILE", os.path.expandvars(
        r"%APPDATA%\postgresql\pgpass.conf"))
    import psycopg2

    conn = psycopg2.connect(host="wrds-pgdata.wharton.upenn.edu", port=9737,
                            dbname="wrds", user="murathan12",
                            sslmode="require", connect_timeout=15)
    conn.set_session(readonly=True, autocommit=True)
    cur = conn.cursor()

    # 1) every schema the server has, with USAGE flag
    cur.execute("""
        SELECT nspname, has_schema_privilege(current_user, nspname, 'USAGE')
        FROM pg_namespace
        WHERE nspname NOT LIKE 'pg_%%' AND nspname <> 'information_schema'
        ORDER BY nspname
    """)
    schemas = {r[0]: bool(r[1]) for r in cur.fetchall()}
    usable = sorted(k for k, v in schemas.items() if v)
    print(f"server schemas: {len(schemas)}, USAGE granted: {len(usable)}")

    # 2) representative-table SELECT probe on candidates whose schema exists
    results = {}
    for schema, table in CANDIDATES.items():
        if schema not in schemas:
            results[schema] = {"exists": False}
            continue
        entry: dict = {"exists": True, "usage": schemas[schema]}
        if schemas[schema]:
            # find the actual table if the representative guess is off
            cur.execute("""
                SELECT tablename FROM pg_tables WHERE schemaname = %s
                UNION SELECT viewname FROM pg_views WHERE schemaname = %s
                LIMIT 400
            """, (schema, schema))
            tables = sorted(r[0] for r in cur.fetchall())
            entry["n_tables_visible"] = len(tables)
            entry["sample_tables"] = tables[:12]
            probe = table if table in tables else (tables[0] if tables
                                                   else None)
            if probe:
                try:
                    cur.execute(
                        f'SELECT * FROM "{schema}"."{probe}" LIMIT 1')
                    cur.fetchall()
                    entry["select_ok"] = probe
                except Exception as e:                         # noqa: BLE001
                    conn.rollback()
                    entry["select_denied"] = f"{probe}: " + str(e).split(
                        chr(10))[0][:120]
        results[schema] = entry
        tag = ("SELECT-OK" if entry.get("select_ok")
               else "DENIED" if entry.get("select_denied")
               else "no-usage" if entry["exists"] else "absent")
        print(f"  {schema:<28} {tag}")

    OUT.mkdir(parents=True, exist_ok=True)
    receipt = {
        "probe": "WRDS-ENTITLEMENT-MAP-1",
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "user": "murathan12",
        "n_schemas_on_server": len(schemas),
        "n_usage": len(usable),
        "usage_schemas": usable,
        "candidates": results,
        "rule": "catalogue is not entitlement; only select_ok rows may be "
                "cited by pull scripts",
    }
    p = OUT / f"entitlement_map_{date.today().isoformat()}.json"
    p.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(f"receipt: {p}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
