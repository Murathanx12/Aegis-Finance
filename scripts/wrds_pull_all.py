"""
WRDS FULL PULL — BoardEx (no row caps) + IBES coverage counts.
Run:   python C:\\Users\\mrthn\\Downloads\\WRDS_PULL_ALL.py
First run: prompts username/password, sends ONE Duo push, offers to create
~/.pgpass -> answer YES (makes all future pulls non-interactive).

Design rules (from the 2026-08-02 audit):
 - NO bare LIMIT anywhere. The truncated local extracts (exactly 500k/1M/1M
   rows) are the defect this script replaces.
 - Row counts logged BEFORE and AFTER each pull so truncation is detectable.
 - Resume-safe: a table whose parquet exists with >= the counted rows is skipped.
 - Big tables pulled in year chunks, concatenated once, verified once.

Output: C:\\Users\\mrthn\\Aegis module\\data\\wrds_raw\\full\\
Log:    same dir, pull_log.txt (tail it to watch progress).
"""
import os, sys, time, traceback
from pathlib import Path
from datetime import datetime

OUTDIR = Path(r"C:\Users\mrthn\Aegis module\data\wrds_raw\full")
OUTDIR.mkdir(parents=True, exist_ok=True)
LOG = OUTDIR / "pull_log.txt"

def log(msg):
    line = f"[{datetime.now():%H:%M:%S}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")

log("=" * 70)
log("WRDS full pull starting")

import pandas as pd
import wrds

# wrds_username must be explicit: pgpass.conf supplies the password, but the
# package still prompts for the username otherwise (EOFError in a null-stdin shell).
def connect():
    return wrds.Connection(wrds_username="murathan12")

db = connect()
log("connected")

def reconnect():
    """A failed query leaves SQLAlchemy in an invalid-transaction state that
    poisons every later call ('Can't reconnect until invalid transaction is
    rolled back'). Cheapest reliable cure: fresh connection."""
    global db
    try:
        db.close()
    except Exception:
        pass
    db = connect()
    log("  (reconnected)")

# Tables above this size get pulled in modulo chunks on an integer id column —
# a single `select *` on 17M rows made the WRDS server drop the connection.
CHUNK_THRESHOLD = 4_000_000
ID_CANDIDATES = ("directorid", "boardid", "companyid", "rowid")
N_CHUNKS = 16

# ---------------------------------------------------------------- helpers
def table_count(lib, tab):
    try:
        return int(db.raw_sql(f"select count(*) as n from {lib}.{tab}")["n"][0])
    except Exception as e:
        log(f"  count failed {lib}.{tab}: {str(e)[:100]}")
        reconnect()
        return None

def pull_table(lib, tab, outname, where="", chunk_col=None, chunk_vals=None):
    """Pull lib.tab fully (optionally WHERE-scoped / chunked), verify count."""
    out = OUTDIR / f"{outname}.parquet"
    n_src = table_count(lib, tab)
    if n_src is None:
        log(f"  SKIP {lib}.{tab}: not countable (entitlement?)")
        return
    log(f"  {lib}.{tab}: source rows = {n_src:,}")
    if out.exists():
        try:
            # Metadata-only row count — never load the file to count it
            # (a 10.7M-row read_parquet here was killing resume runs).
            import pyarrow.parquet as pq
            n_have = pq.ParquetFile(out).metadata.num_rows
            if where == "" and n_have >= n_src:
                log(f"  SKIP {outname}: already complete ({n_have:,} rows)")
                return
            log(f"  {outname}: exists with {n_have:,} rows, re-pulling")
        except Exception:
            pass
    t0 = time.time()
    if chunk_col and chunk_vals:
        parts = []
        for v in chunk_vals:
            q = f"select * from {lib}.{tab} where {chunk_col} = '{v}'"
            if where:
                q += f" and ({where})"
            d = db.raw_sql(q)
            parts.append(d)
            log(f"    chunk {chunk_col}={v}: {len(d):,} rows "
                f"({time.time()-t0:.0f}s elapsed)")
        df = pd.concat(parts, ignore_index=True)
    elif n_src > CHUNK_THRESHOLD and not where:
        cols = list(db.raw_sql(f"select * from {lib}.{tab} limit 0").columns)
        id_col = next((c for c in ID_CANDIDATES if c in cols), None)
        if id_col is None:
            log(f"  !! {lib}.{tab}: {n_src:,} rows but no id column to chunk "
                f"on (cols: {cols[:12]}) — attempting single pull")
            df = db.raw_sql(f"select * from {lib}.{tab}")
        else:
            log(f"  chunking on {id_col} % {N_CHUNKS} ({n_src:,} rows)")
            # Checkpoint each chunk to disk — a killed process resumes at the
            # first missing chunk instead of redoing hours of work.
            parts = []
            for k in range(N_CHUNKS):
                ck = OUTDIR / f"{outname}._chunk_{k}.parquet"
                if ck.exists():
                    d = pd.read_parquet(ck)
                    log(f"    chunk {k+1}/{N_CHUNKS}: {len(d):,} rows (cached)")
                else:
                    # mod(cast(...)) — BoardEx ids are sometimes double
                    # precision, where Postgres has no % operator
                    d = db.raw_sql(
                        f"select * from {lib}.{tab} "
                        f"where mod(cast({id_col} as bigint), {N_CHUNKS}) = {k}"
                    )
                    d.to_parquet(ck, index=False)
                    log(f"    chunk {k+1}/{N_CHUNKS}: {len(d):,} rows "
                        f"({time.time()-t0:.0f}s elapsed)")
                parts.append(d)
            df = pd.concat(parts, ignore_index=True)
            for k in range(N_CHUNKS):
                (OUTDIR / f"{outname}._chunk_{k}.parquet").unlink(missing_ok=True)
    else:
        q = f"select * from {lib}.{tab}"
        if where:
            q += f" where {where}"
        df = db.raw_sql(q)
    df.to_parquet(out, index=False)
    flag = "OK" if (where or len(df) == n_src) else "!! MISMATCH"
    log(f"  WROTE {outname}: {len(df):,} rows in {time.time()-t0:.0f}s "
        f"(source {n_src:,}) {flag}")

# ---------------------------------------------------------------- 1. discover
log("-" * 70)
log("1. Library discovery")
libs = set(db.list_libraries())
bx_libs = sorted(L for L in libs if "boardex" in L.lower())
log(f"BoardEx libraries: {bx_libs}")
for probe in ("ibes", "optionm", "ravenpack", "audit", "tfn"):
    hit = sorted(L for L in libs if L.lower().startswith(probe))
    log(f"  {probe}: {hit if hit else 'NOT ENTITLED'}")

# ---------------------------------------------------------------- 2. boardex
log("-" * 70)
log("2. BoardEx — full, uncapped")
TARGETS = ("org_summary", "company_network", "dir_profile", "company_profile",
           "org_composition", "board_char")
done = set()
for lib in bx_libs:
    try:
        tabs = db.list_tables(library=lib)
    except Exception as e:
        log(f"  {lib}: list failed {e}")
        continue
    log(f"  {lib}: {len(tabs)} tables")
    for t in sorted(tabs):
        # HKU licence = BoardEx North America only; eur_/uk_/row_ schemas denied
        if t.lower().startswith(("eur_", "uk_", "row_")):
            continue
        if any(k in t.lower() for k in TARGETS) and t not in done:
            done.add(t)
            try:
                pull_table(lib, t, f"boardex_{t}")
            except Exception:
                log(f"  ERROR {lib}.{t}:\n{traceback.format_exc()[-400:]}")
                reconnect()
if not done:
    log("  !! no BoardEx target tables found — check the table list above")

# ---------------------------------------------------------------- 3. ibes
log("-" * 70)
log("3. IBES — coverage counts (numest = the neglect proxy)")
try:
    ibes_tabs = set(db.list_tables(library="ibes"))
    # statsum_epsus: US summary stats; numest = analyst count per stat period
    for t in ("statsum_epsus",):
        if t in ibes_tabs:
            # only the columns the neglect signal needs; FY1 only; keeps it small
            q = ("select ticker, cusip, statpers, fpi, numest, meanest, "
                 "medest, stdev, fpedats from ibes.statsum_epsus "
                 "where fpi = '1'")
            t0 = time.time()
            df = db.raw_sql(q)
            df.to_parquet(OUTDIR / "ibes_statsum_fy1.parquet", index=False)
            log(f"  WROTE ibes_statsum_fy1: {len(df):,} rows "
                f"in {time.time()-t0:.0f}s")
        else:
            log(f"  ibes.{t} not present; tables: {sorted(ibes_tabs)[:30]}")
except Exception:
    log(f"  IBES failed:\n{traceback.format_exc()[-400:]}")
    reconnect()

# ---------------------------------------------------------------- 4. crsp daily (top-up)
log("-" * 70)
log("4. CRSP dsedelist refresh (cheap, keeps delisting file current)")
try:
    pull_table("crsp", "dsedelist", "crsp_dsedelist_full")
except Exception:
    log(f"  dsedelist failed:\n{traceback.format_exc()[-300:]}")

db.close()
log("=" * 70)
log("DONE. Verify: no '!! MISMATCH' lines above; BoardEx row counts should "
    "NOT be round numbers like 500,000 / 1,000,000.")
