"""Full table rebuild with a backup and an atomic swap (2026-09-30).

`python -m nn_lab.table` writes straight over the live table and its calendar. This builds into
`table/rebuild_<stamp>/`, checks the PIT audit and that no stored LABELLED grid date disappears
(names may leave: ETFs are excluded on purpose), keeps the old table as
`table/train_table_before_<stamp>.parquet`, then swaps. The live calendar is kept as the union
of both (the nightly append had extended it past the bar files' end).

    python -m nn_lab.rebuild
"""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone

import pandas as pd

from nn_lab import config as C
from nn_lab import table as T


def main() -> dict:
    stamp = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    d = C.TABLE_DIR / f"rebuild_{stamp}"
    d.mkdir(parents=True, exist_ok=True)
    new_path = d / "train_table.parquet"
    # the same files the nightly append reads (the refresh extends living names past the deep
    # pull), plus the CRSP-recovered deaths
    paths = [C.BARS_DEEP, C.BARS_RECENT, C.BARS_DELISTED]
    if C.USE_CRSP_DEATHS and C.BARS_DELISTED_CRSP.exists():
        paths.append(C.BARS_DELISTED_CRSP)
    rec = T.build(out=new_path, bars_paths=paths, extend_only=[C.BARS_RECENT])
    old = pd.read_parquet(C.TABLE_PATH, columns=["date", "symbol", "on_grid", "y_21"])
    new = pd.read_parquet(new_path, columns=["date", "symbol", "on_grid", "y_21"])
    old_lab = set(old.loc[old["on_grid"] & old["y_21"].notna(), "date"])
    new_dates = set(new.loc[new["on_grid"], "date"])
    lost = sorted(old_lab - new_dates)
    lost_after_bars_end = [x for x in lost if x > new["date"].max()]
    lost_inside = [x for x in lost if x <= new["date"].max()]
    rec["swap_check"] = {"old_rows": int(len(old)), "new_rows": int(len(new)),
                         "old_symbols": int(old["symbol"].nunique()), "new_symbols": int(new["symbol"].nunique()),
                         "labelled_grid_dates_lost_inside_new_range": [str(x.date()) for x in lost_inside],
                         "labelled_grid_dates_after_new_end (the nightly append re-adds them)":
                             [str(x.date()) for x in lost_after_bars_end]}
    if lost_inside:
        rec["swap"] = "REFUSED: labelled grid dates would disappear inside the rebuilt range"
    else:
        backup = C.TABLE_DIR / f"train_table_before_{stamp}.parquet"
        shutil.copy2(C.TABLE_PATH, backup)
        cal_old = pd.read_parquet(C.TABLE_DIR / "calendar.parquet")["date"]
        cal_new = pd.read_parquet(d / "calendar.parquet")["date"]
        cal = pd.DataFrame({"date": sorted(set(pd.to_datetime(cal_old)) | set(pd.to_datetime(cal_new)))})
        tmp = C.TABLE_PATH.with_suffix(".swap.parquet")
        shutil.copy2(new_path, tmp)
        os.replace(tmp, C.TABLE_PATH)
        cal.to_parquet(C.TABLE_DIR / "calendar.parquet", index=False)
        rec["swap"] = {"status": "SWAPPED", "backup": str(backup),
                       "table_sha256": __import__("nn_lab.loop", fromlist=["sha256_file"]).sha256_file(C.TABLE_PATH)}
        shutil.rmtree(d, ignore_errors=True)
    C.RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
    (C.RECEIPT_DIR / f"table_{stamp}.json").write_text(json.dumps(rec, indent=1, default=str))
    return rec


if __name__ == "__main__":
    r = main()
    print(json.dumps({k: r[k] for k in ("rows", "grid_rows", "survivorship", "swap_check", "swap",
                                        "dead_names_by_last_year", "etf_exclusions",
                                        "dead_symbols_renamed_as_reused_tickers", "close_raw") if k in r},
                     indent=1, default=str))
