"""WRDS phase-2 pull — linkage + D2/D3-critical tables, fresh and count-verified.

Why this exists (2026-08-04): Gate D2 (PIT linkage) and D3 (known-answer
replication) need CRSP stocknames/msf/msenames/msedelist, CCM link history,
Compustat funda/company — but the local copies of those are legacy-era pulls
that predate the count-at-source discipline. Rather than certify legacy files,
re-pull them fresh with exact count verification. Also pulls the
wrdsapps_plink_exec_boardex library (WRDS's professionally maintained
BoardEx<->CRSP/Compustat link) which the phase-1 pull listed but never fetched.

Same design rules as WRDS_PULL_ALL.py:
 - no bare LIMIT anywhere; count at source before and after every pull
 - resume-safe (skip complete parquets via metadata row count, never a full read)
 - big pulls chunked on mod(id) with per-chunk checkpoints
 - a failed query poisons the SQLAlchemy session -> reconnect with a fresh one

Run:  .venv/Scripts/python.exe scripts/wrds_pull_linkage.py
Output: C:/Users/mrthn/Aegis module/data/wrds_raw/full/  (same dir + log as phase 1)
"""
import time
import traceback
from datetime import datetime
from pathlib import Path

OUTDIR = Path(r"C:\Users\mrthn\Aegis module\data\wrds_raw\full")
OUTDIR.mkdir(parents=True, exist_ok=True)
LOG = OUTDIR / "pull_log.txt"


def log(msg):
    line = f"[{datetime.now():%H:%M:%S}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


log("=" * 70)
log("WRDS phase-2 pull starting (linkage + D2/D3 tables)")

import pandas as pd
import pyarrow.parquet as pq
import wrds


def connect():
    # pgpass.conf supplies the password; username must still be explicit or the
    # package prompts (EOFError in a null-stdin background shell).
    return wrds.Connection(wrds_username="murathan12")


db = connect()
log("connected")


def reconnect():
    global db
    try:
        db.close()
    except Exception:
        pass
    db = connect()
    log("  (reconnected)")


N_CHUNKS = 8


def pull(lib, tab, outname, cols="*", where="", chunk_id=None):
    """Pull lib.tab (column-scoped, optional WHERE), verify exact count.

    chunk_id: integer column to chunk on via mod() when the row count is large.
    Unlike phase 1, the WHERE clause is applied to the source count too, so
    filtered pulls get exact verification instead of a lenient flag.
    """
    out = OUTDIR / f"{outname}.parquet"
    wsql = f" where {where}" if where else ""
    try:
        n_src = int(db.raw_sql(f"select count(*) as n from {lib}.{tab}{wsql}")["n"][0])
    except Exception as e:
        log(f"  SKIP {lib}.{tab}: count failed {str(e)[:120]}")
        reconnect()
        return
    log(f"  {lib}.{tab}{' [' + where + ']' if where else ''}: source rows = {n_src:,}")
    if out.exists():
        n_have = pq.ParquetFile(out).metadata.num_rows
        if n_have == n_src:
            log(f"  SKIP {outname}: already complete ({n_have:,} rows)")
            return
        log(f"  {outname}: exists with {n_have:,} rows vs source {n_src:,}, re-pulling")
    t0 = time.time()
    if chunk_id and n_src > 1_000_000:
        parts = []
        for k in range(N_CHUNKS):
            ck = OUTDIR / f"{outname}._chunk_{k}.parquet"
            if ck.exists():
                d = pd.read_parquet(ck)
                log(f"    chunk {k + 1}/{N_CHUNKS}: {len(d):,} rows (cached)")
            else:
                q = (f"select {cols} from {lib}.{tab} "
                     f"where mod(cast({chunk_id} as bigint), {N_CHUNKS}) = {k}")
                if where:
                    q += f" and ({where})"
                d = db.raw_sql(q)
                d.to_parquet(ck, index=False)
                log(f"    chunk {k + 1}/{N_CHUNKS}: {len(d):,} rows "
                    f"({time.time() - t0:.0f}s elapsed)")
            parts.append(d)
        df = pd.concat(parts, ignore_index=True)
        for k in range(N_CHUNKS):
            (OUTDIR / f"{outname}._chunk_{k}.parquet").unlink(missing_ok=True)
    else:
        df = db.raw_sql(f"select {cols} from {lib}.{tab}{wsql}")
    df.to_parquet(out, index=False)
    flag = "OK" if len(df) == n_src else "!! MISMATCH"
    log(f"  WROTE {outname}: {len(df):,} rows in {time.time() - t0:.0f}s "
        f"(source {n_src:,}) {flag}")


# ------------------------------------------------------- 1. BoardEx link suite
log("-" * 70)
log("1. wrdsapps_plink_exec_boardex — WRDS-maintained BoardEx link tables")
try:
    link_tabs = db.list_tables(library="wrdsapps_plink_exec_boardex")
    log(f"  tables: {sorted(link_tabs)}")
    for t in sorted(link_tabs):
        try:
            pull("wrdsapps_plink_exec_boardex", t, f"link_boardex_{t}")
        except Exception:
            log(f"  ERROR {t}:\n{traceback.format_exc()[-300:]}")
            reconnect()
except Exception:
    log(f"  list failed:\n{traceback.format_exc()[-300:]}")
    reconnect()

# ------------------------------------------------------- 2. CRSP identity/name
log("-" * 70)
log("2. CRSP names, delistings, link history (small, full)")
for lib, tab, outname in (
    ("crsp", "stocknames", "crsp_stocknames_full"),
    ("crsp", "msenames", "crsp_msenames_full"),
    ("crsp", "msedelist", "crsp_msedelist_full"),
    ("crsp", "ccmxpf_lnkhist", "crsp_ccmxpf_lnkhist_full"),
):
    try:
        pull(lib, tab, outname)
    except Exception:
        log(f"  ERROR {lib}.{tab}:\n{traceback.format_exc()[-300:]}")
        reconnect()

# ------------------------------------------------------- 3. CRSP monthly stock
log("-" * 70)
log("3. CRSP msf — monthly prices/returns/shares (chunked on permno)")
try:
    pull(
        "crsp", "msf", "crsp_msf_full",
        cols=("permno, permco, date, prc, ret, retx, shrout, vol, "
              "cfacpr, cfacshr, altprc, spread"),
        chunk_id="permno",
    )
except Exception:
    log(f"  ERROR crsp.msf:\n{traceback.format_exc()[-300:]}")
    reconnect()

# ------------------------------------------------------- 4. Compustat
log("-" * 70)
log("4. Compustat company + funda (standard INDL/STD/D/C screens)")
try:
    pull("comp", "company", "comp_company_full")
except Exception:
    log(f"  ERROR comp.company:\n{traceback.format_exc()[-300:]}")
    reconnect()
try:
    pull(
        "comp", "funda", "comp_funda_full",
        cols=("gvkey, datadate, fyear, tic, cusip, cik, conm, "
              "at, revt, cogs, sale, ib, ceq, seq, pstk, txditc, "
              "csho, prcc_f, dltt, dlc, oibdp, xsga"),
        where=("indfmt = 'INDL' and datafmt = 'STD' and popsrc = 'D' "
               "and consol = 'C'"),
    )
except Exception:
    log(f"  ERROR comp.funda:\n{traceback.format_exc()[-300:]}")
    reconnect()

db.close()
log("=" * 70)
log("PHASE2 DONE. Verify: no '!! MISMATCH' above; then run gate_d1_verify.py "
    "and proceed to D2 linkage certification.")
