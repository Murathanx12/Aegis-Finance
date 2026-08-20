"""WRDS-PULL-EVERYTHING — the whole entitled catalogue, minus what cannot
join and what cannot fit.

Ordered 2026-08-20: pull everything, so that cross-source structure can be
looked for rather than assumed absent.

"Everything" needs a definition that survives contact with the catalogue.
WRDS-CATALOGUE-PROBE-1 found **42,167 tables across the 46 SELECT-OK
schemas, ~2 x 10^15 estimated rows**. A single day of TAQ quotes is larger
than the disk. So the literal reading is not executable, and pretending
otherwise would produce a half-finished substrate nobody could describe.

The executable reading, and the reason each exclusion is principled
rather than convenient:

  EXCLUDE the intraday firehoses (taqm_*, taqmsec, issm, otc, phlx,
    msrb, trace). Per-day quote and trade tables, thousands of them.
    Already represented in the substrate by `taq_iid` (server-side
    aggregated liquidity indicators), which is the usable form.

  EXCLUDE date-partitioned siblings when a merged parent exists — a
    per-year copy adds no information, only round trips.

  EXCLUDE tables with no ENTITY ID or no DATE. This is the filter that
    matters and it is not a size heuristic: a table with no security or
    firm identifier, or no time column, cannot be joined to the panel and
    therefore cannot participate in any cross-source correlation. Federal
    court dockets and 1983 retail scanner panels are entitled, and they
    cannot correlate with a stock return. Keeping them would inflate the
    corpus and inform nothing.

  CAP each table at MAX_ROWS and the run at DISK_BUDGET_GB.

Everything excluded is written to the manifest WITH its reason and its
estimated size, so "we do not have it" is never confused with "it is not
there" (canon: a refusal is a finding).

Resumable: a table whose parquet exists is skipped. Safe to kill.

    python -m scripts.wrds_pull_everything --probe-only
    python -m scripts.wrds_pull_everything
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config                        # noqa: E402
from scripts.wrds_training_pull import (OUT, _conn,          # noqa: E402
                                        _date_ranges, _all_permnos)

CAT = OUT / "catalogue_probe_2026-08-20.json"
MANIFEST = OUT / "pull_everything_manifest.json"
BULK = OUT / "bulk"

FIREHOSE = ("taqm_", "taqmsec", "issm", "otc", "phlx", "msrb", "trace")
DATEPART = re.compile(r"(_(19|20)\d{2}(\d{2}\d{2})?$)|(\d{8}$)")

ID_COLS = ("permno", "permco", "lpermno", "gvkey", "cusip", "ncusip",
           "cusip8", "cusip9", "secid", "ticker", "tic", "issuer_cusip",
           "companyid", "boardid", "mgrno", "fundno", "crsp_fundno",
           "complete_cusip", "issue_id", "isin", "sedol")
DATE_HINTS = ("date", "dat", "eom", "public", "statpers", "rdq", "year",
              "month", "period", "time", "dt", "announce", "filing",
              "effective", "start", "end", "asof", "as_of")

MAX_ROWS = 8_000_000
DISK_BUDGET_GB = 60.0
PER_TABLE_TIMEOUT_S = 900


def _classify(cols: list[str]) -> tuple[str | None, str | None]:
    low = [c.lower() for c in cols]
    idc = next((c for c in ID_COLS if c in low), None)
    dtc = next((c for c in low
                if any(h in c for h in DATE_HINTS)), None)
    return idc, dtc


def build_plan(conn) -> tuple[list[dict], list[dict]]:
    cat = json.loads(CAT.read_text(encoding="utf-8"))
    cur = conn.cursor()
    # one column query per schema, not per table
    schemas = sorted({r["schema"] for r in cat["tables"]})
    colmap: dict[tuple[str, str], list[str]] = {}
    for sch in schemas:
        if any(sch.startswith(f) for f in FIREHOSE):
            continue
        cur.execute(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = %s ORDER BY table_name, ordinal_position",
            (sch,))
        for t, c in cur.fetchall():
            colmap.setdefault((sch, t), []).append(c)

    plan, skipped = [], []
    for r in cat["tables"]:
        sch, tab, n = r["schema"], r["table"], r["est_rows"]
        key = f"{sch}.{tab}"
        if any(sch.startswith(f) for f in FIREHOSE):
            skipped.append({**r, "reason": "intraday firehose schema; "
                                           "represented by taq_iid"})
            continue
        if DATEPART.search(tab):
            skipped.append({**r, "reason": "date-partitioned sibling"})
            continue
        if n > MAX_ROWS:
            skipped.append({**r, "reason": f"est_rows > cap {MAX_ROWS:,}"})
            continue
        cols = colmap.get((sch, tab))
        if not cols:
            skipped.append({**r, "reason": "no columns visible"})
            continue
        idc, dtc = _classify(cols)
        if not idc or not dtc:
            skipped.append({**r, "reason": f"not joinable (id={idc}, "
                                           f"date={dtc}) — cannot "
                                           f"correlate with the panel"})
            continue
        plan.append({"schema": sch, "table": tab, "name": key,
                     "est_rows": n, "n_cols": len(cols),
                     "id_col": idc, "date_col": dtc})
    plan.sort(key=lambda p: p["est_rows"])
    return plan, skipped


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe-only", action="store_true")
    ap.add_argument("--max-tables", type=int, default=100000)
    a = ap.parse_args()

    BULK.mkdir(parents=True, exist_ok=True)
    conn = _conn()
    print("building plan...")
    plan, skipped = build_plan(conn)
    print(f"plan: {len(plan):,} joinable tables   "
          f"skipped: {len(skipped):,}")
    reasons = {}
    for s_ in skipped:
        reasons[s_["reason"].split("—")[0].strip()[:48]] = \
            reasons.get(s_["reason"].split("—")[0].strip()[:48], 0) + 1
    for k, v in sorted(reasons.items(), key=lambda kv: -kv[1]):
        print(f"  skip: {k:52s} {v:>6,}")

    man = {"pull": "WRDS-PULL-EVERYTHING",
           "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "catalogue": {"n_tables_total": len(plan) + len(skipped),
                         "n_planned": len(plan), "n_skipped": len(skipped)},
           "caps": {"max_rows_per_table": MAX_ROWS,
                    "disk_budget_gb": DISK_BUDGET_GB},
           "skipped": skipped, "pulled": [], "failed": []}
    MANIFEST.write_text(json.dumps(man, indent=2), encoding="utf-8")
    if a.probe_only:
        print(f"\nprobe only -> {MANIFEST}")
        return 0

    permnos = set(_all_permnos())
    used_gb = sum(f.stat().st_size for f in BULK.rglob("*.parquet")) / 2**30
    done = 0
    for p in plan[:a.max_tables]:
        fn = BULK / f"{p['schema']}__{p['table']}.parquet"
        if fn.exists():
            continue
        if used_gb >= DISK_BUDGET_GB:
            man["failed"].append({**p, "error": "disk budget reached"})
            print(f"DISK BUDGET {DISK_BUDGET_GB} GB reached — stopping")
            break
        # universe filter only where the id is one we hold a universe for
        where, params = "", {}
        if p["id_col"] in ("permno", "lpermno", "permco"):
            where = f' WHERE "{p["id_col"]}" = ANY(%(p)s)'
            params = {"p": sorted(permnos)}
        sql = (f'SELECT * FROM {p["schema"]}.{p["table"]}{where} '
               f'LIMIT {MAX_ROWS}')
        t0 = time.time()
        try:
            conn.cursor().execute(f"SET statement_timeout = "
                                  f"{PER_TABLE_TIMEOUT_S * 1000}")
            df = pd.read_sql(sql, conn, params=params or None)
        except Exception as e:                                 # noqa: BLE001
            man["failed"].append({**p, "error":
                                  f"{type(e).__name__}: {str(e)[:200]}"})
            try:
                conn.close()
            except Exception:                                  # noqa: BLE001
                pass
            conn = _conn()
            print(f"  FAIL {p['name']}: {type(e).__name__}")
            MANIFEST.write_text(json.dumps(man, indent=2), encoding="utf-8")
            continue
        if not len(df):
            man["skipped"].append({**p, "reason": "returned 0 rows "
                                                  "(empty or filtered out)"})
            continue
        df.to_parquet(fn, index=False)
        sz = fn.stat().st_size / 2**30
        used_gb += sz
        rec = {**p, "rows": int(len(df)), "gb": round(sz, 4),
               "date_ranges": _date_ranges(df),
               "seconds": round(time.time() - t0, 1),
               "universe_filtered": bool(where)}
        man["pulled"].append(rec)
        done += 1
        if done % 10 == 0:
            MANIFEST.write_text(json.dumps(man, indent=2, default=str),
                                encoding="utf-8")
            print(f"  [{done}] {p['name']:<52s} {len(df):>10,} rows  "
                  f"{used_gb:.1f} GB used")
    conn.close()
    man["completed_at"] = datetime.now(timezone.utc).isoformat(
        timespec="seconds")
    man["disk_used_gb"] = round(used_gb, 3)
    MANIFEST.write_text(json.dumps(man, indent=2, default=str),
                        encoding="utf-8")
    print(f"\npulled {len(man['pulled']):,} tables, "
          f"{used_gb:.1f} GB, {len(man['failed']):,} failed")
    print(f"manifest -> {MANIFEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
