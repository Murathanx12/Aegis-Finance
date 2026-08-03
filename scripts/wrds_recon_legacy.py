"""
WRDS RECONNAISSANCE — run tonight, ~15-20 min, mostly auth wait.
Goal: NOT to pull data. Only to find out what we're entitled to and how big it is.
Output: wrds_recon_report.txt next to this file.

Run:  pip install wrds
      python WRDS_RECON_TONIGHT.py
First run prompts for username + password, then asks to create ~/.pgpass -> say YES.
"""
import sys, traceback
from datetime import datetime

OUT = []
def log(s=""):
    print(s)
    OUT.append(str(s))

def flush():
    with open("wrds_recon_report.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(OUT))
    print("\n>>> wrote wrds_recon_report.txt")

log(f"WRDS recon {datetime.now():%Y-%m-%d %H:%M}")

try:
    import wrds
except ImportError:
    log("!! wrds not installed. Run:  pip install wrds")
    flush(); sys.exit(1)

try:
    db = wrds.Connection()          # prompts user/pass; say YES to .pgpass
except Exception as e:
    log(f"!! connection failed: {e}")
    flush(); sys.exit(1)

log("connected OK\n")

# ---- 1. What libraries are we entitled to? -------------------------------
log("=" * 60)
log("1. ENTITLED LIBRARIES")
log("=" * 60)
try:
    libs = sorted(db.list_libraries())
    log(f"total: {len(libs)}")
    KEY = ("boardex", "ibes", "crsp", "comp", "optionm", "ravenpack",
           "audit", "tfn", "thomson", "markit", "msci", "issrs")
    for L in libs:
        if any(k in L.lower() for k in KEY):
            log(f"  * {L}")
    log("\n  (full list at end)")
except Exception as e:
    log(f"  ERR {e}")

# ---- 2. BoardEx tables + TRUE row counts ---------------------------------
log("\n" + "=" * 60)
log("2. BOARDEX — table list + row counts  [THE KEY QUESTION]")
log("=" * 60)
for lib in ("boardex", "boardex_na", "boardex_trial"):
    try:
        tabs = sorted(db.list_tables(library=lib))
    except Exception as e:
        log(f"  {lib}: not entitled / {e}")
        continue
    log(f"\n  {lib}: {len(tabs)} tables")
    for t in tabs:
        log(f"    - {t}")
    # count only the ones we actually care about
    for t in tabs:
        if any(k in t for k in ("org_summary", "company_networks",
                                "dir_profile", "org_composition",
                                "company_profile")):
            try:
                n = db.raw_sql(f"select count(*) as n from {lib}.{t}")["n"][0]
                log(f"    >> {lib}.{t}: {int(n):,} rows")
            except Exception as e:
                log(f"    >> {lib}.{t}: count failed ({str(e)[:80]})")

# ---- 3. IBES — analyst coverage counts (the neglect proxy) ---------------
log("\n" + "=" * 60)
log("3. IBES — coverage counts for the neglect x quality signal")
log("=" * 60)
try:
    tabs = sorted(db.list_tables(library="ibes"))
    log(f"  ibes: {len(tabs)} tables")
    for t in tabs[:40]:
        log(f"    - {t}")
    for t in ("statsum_epsus", "statsumu_epsus"):
        if t in tabs:
            try:
                n = db.raw_sql(f"select count(*) as n from ibes.{t}")["n"][0]
                log(f"    >> ibes.{t}: {int(n):,} rows")
                d = db.raw_sql(f"select * from ibes.{t} limit 3")
                log(f"       cols: {list(d.columns)}")
            except Exception as e:
                log(f"    >> {t}: {str(e)[:80]}")
except Exception as e:
    log(f"  ERR {e}")

# ---- 4. Anything else worth knowing -------------------------------------
log("\n" + "=" * 60)
log("4. OTHER ENTITLEMENTS WORTH CHECKING")
log("=" * 60)
for lib, why in [("optionm", "OptionMetrics - option-implied borrow fee"),
                 ("ravenpack", "news novelty / event similarity gap"),
                 ("audit", "Audit Analytics - restatements"),
                 ("tfn", "Thomson 13F institutional holdings")]:
    try:
        tabs = db.list_tables(library=lib)
        log(f"  {lib}: ENTITLED ({len(tabs)} tables) - {why}")
    except Exception:
        log(f"  {lib}: not entitled - {why}")

log("\n" + "=" * 60)
log("FULL LIBRARY LIST")
log("=" * 60)
try:
    for L in sorted(db.list_libraries()):
        log(f"  {L}")
except Exception:
    pass

try:
    db.close()
except Exception:
    pass
flush()
