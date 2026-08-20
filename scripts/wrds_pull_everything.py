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
#: Measured 2026-08-20: boardex.na_board_characteristics took 374s for
#: 515k rows. At that throughput 1,380 tables is 3-6 DAYS on one
#: connection, so the plan is not executable serially. Two changes make
#: it executable: a worker pool, and a per-table timeout short enough
#: that one pathological table cannot eat an hour.
PER_TABLE_TIMEOUT_S = 300
N_WORKERS = 6

#: Research priority. The catalogue is entitled but not equally useful:
#: a table keyed to our securities beats a Canadian audit-fee feed, and
#: at ~1 table/minute the ordering decides what actually lands. Ranked
#: rather than filtered, so nothing is silently excluded — a lower tier
#: is pulled too if the run gets that far.
PRIORITY = (
    ("crsp", "comp", "comp_na_daily_all", "ibes", "tr_ibes", "optionm",
     "optionm_all", "tr_13f", "tfn", "crsp_a_stock"),          # tier 0
    ("wrdsapps", "wrdsapps_finratio", "wrdsapps_finratio_ibes",
     "wrdsapps_bondret", "wrdsapps_windices", "wrdsapps_subsidiary",
     "wrdsapps_patents", "ff", "ff_all", "frb", "macrofin",
     "contrib", "contrib_general", "compseg", "comph"),        # tier 1
    ("fisd", "boardex", "eventus", "audit", "compsamp", "public"),
)                                                              # tier 2


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
        tier = next((i for i, t in enumerate(PRIORITY) if sch in t),
                    len(PRIORITY))
        plan.append({"schema": sch, "table": tab, "name": key,
                     "est_rows": n, "n_cols": len(cols),
                     "id_col": idc, "date_col": dtc, "tier": tier})
    # priority tier first, then small-to-large inside a tier so the run
    # banks many cheap tables before risking an expensive one
    plan.sort(key=lambda p: (p["tier"], p["est_rows"]))
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
    ap.add_argument("--workers", type=int, default=N_WORKERS)
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

    conn.close()
    permnos = sorted(_all_permnos())
    todo = [p for p in plan[:a.max_tables]
            if not (BULK / f"{p['schema']}__{p['table']}.parquet").exists()]
    print(f"\n{len(todo):,} tables to pull with {a.workers} workers "
          f"(tiers: "
          f"{ {t: sum(1 for p in todo if p['tier'] == t) for t in sorted({q['tier'] for q in todo})} })")

    import queue
    import threading
    work: "queue.Queue[dict]" = queue.Queue()
    for p in todo:
        work.put(p)
    lock = threading.Lock()
    state = {"gb": sum(f.stat().st_size
                       for f in BULK.rglob("*.parquet")) / 2**30,
             "done": 0, "stop": False}

    def worker(wid: int):
        c = None
        while not state["stop"]:
            try:
                p = work.get_nowait()
            except queue.Empty:
                break
            fn = BULK / f"{p['schema']}__{p['table']}.parquet"
            if fn.exists():
                continue
            with lock:
                if state["gb"] >= DISK_BUDGET_GB:
                    state["stop"] = True
                    return
            where, params = "", {}
            if p["id_col"] in ("permno", "lpermno", "permco"):
                where = f' WHERE "{p["id_col"]}" = ANY(%(p)s)'
                params = {"p": permnos}
            sql = (f'SELECT * FROM {p["schema"]}.{p["table"]}{where} '
                   f'LIMIT {MAX_ROWS}')
            t0 = time.time()
            try:
                if c is None:
                    c = _conn()
                cur = c.cursor()
                cur.execute(f"SET statement_timeout = "
                            f"{PER_TABLE_TIMEOUT_S * 1000}")
                df = pd.read_sql(sql, c, params=params or None)
            except Exception as e:                             # noqa: BLE001
                msg = f"{type(e).__name__}: {str(e)[:180]}"
                with lock:
                    man["failed"].append({**p, "error": msg})
                # a permission or timeout error leaves the transaction
                # aborted; roll back rather than paying for a reconnect
                try:
                    c.rollback()
                except Exception:                              # noqa: BLE001
                    try:
                        c.close()
                    except Exception:                          # noqa: BLE001
                        pass
                    c = None
                continue
            if not len(df):
                with lock:
                    man["skipped"].append({**p, "reason": "0 rows"})
                continue
            try:
                df.to_parquet(fn, index=False)
            except Exception as e:                             # noqa: BLE001
                with lock:
                    man["failed"].append({**p, "error": f"write: {e}"})
                continue
            sz = fn.stat().st_size / 2**30
            with lock:
                state["gb"] += sz
                state["done"] += 1
                man["pulled"].append({
                    **p, "rows": int(len(df)), "gb": round(sz, 4),
                    "date_ranges": _date_ranges(df),
                    "seconds": round(time.time() - t0, 1),
                    "universe_filtered": bool(where)})
                d = state["done"]
                if d % 10 == 0:
                    MANIFEST.write_text(
                        json.dumps(man, indent=2, default=str),
                        encoding="utf-8")
                    print(f"  [{d}/{len(todo)}] {p['name']:<46s} "
                          f"{len(df):>9,} rows  {state['gb']:.1f} GB  "
                          f"({len(man['failed'])} failed)", flush=True)
        if c is not None:
            try:
                c.close()
            except Exception:                                  # noqa: BLE001
                pass

    threads = [threading.Thread(target=worker, args=(i,), daemon=True)
               for i in range(a.workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    used_gb = state["gb"]
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
