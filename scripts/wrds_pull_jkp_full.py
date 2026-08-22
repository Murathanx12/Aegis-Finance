"""JKP named-consumer pulls — the two datasets today's receipts license.

    python -m scripts.wrds_pull_jkp_full --max-seconds 480

Over-cap/expansion rule: a large table earns ingestion through a NAMED
CONSUMER. Two are named by today's registered results:

  1. **USA full history (1926–2012, all columns)** — consumer:
     AEGIS-PANEL-2. The sensitivity worlds measured the v1 tournament
     blind below planted IC 0.03 (R² ~0.001 vs 419 features on ~10^5
     rows); the successor instrument is SCALE, and the GKX-class panel
     that provides it is this pull + the 2013–2024 file already on disk.
  2. **13 developed markets, 2013–2024, risk-family column subset** —
     consumer: RISK-PRICE-FOREIGN-CONFIRM-1. RISK-PRICE-EARLY-1 found
     the risk-price return lead is modern-era-only (early US = tight
     zero); the licensed confirm is the SAME era in FOREIGN
     cross-sections, which this subset serves.

Design: chunked (5-year × country), resumable (existing chunk parquet =
skipped), time-budgeted (`--max-seconds` stops BETWEEN chunks so a
wall-clock-capped shell converges over repeated invocations), at-cap
guarded (a chunk that fills its LIMIT is deleted and recorded, never
kept truncated — the na_wrds_individual_networks lesson).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore", message="pandas only supports SQLAlchemy")

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config                        # noqa: E402
from scripts.wrds_training_pull import _conn                 # noqa: E402

OUT = _config.OPTIMUS_LEDGER_DIR / "wrds" / "jkp_full"
CHUNK_CAP = 2_000_000
TABLE = "contrib_global_factor.global_factor"

#: 5-year chunks through 1965 (thin decades), then 2-year: the 1961-65
#: chunk measured 600s at 130k rows — a 5-year 1990s chunk would blow
#: even a generous statement timeout. Filenames are the resume key, so
#: the already-pulled 5-year files keep their names.
USA_CHUNKS = ([(a, a + 4) for a in range(1926, 1966, 5)]
              + [(a, min(a + 1, 2012)) for a in range(1966, 2013, 2)])

FOREIGN = ("AUS", "CAN", "CHE", "DEU", "ESP", "FRA", "GBR",
           "ITA", "JPN", "KOR", "NLD", "SWE", "TWN")

#: risk-price confirm subset: ids/returns/size + the RISK_PRICE family +
#: momentum controls. Kept small on purpose — the consumer's question is
#: the risk family, not a second full panel.
FOREIGN_COLS = (
    "id", "gvkey", "excntry", "eom", "common", "obs_main", "exch_main",
    "primary_sec", "size_grp", "ret", "ret_exc", "ret_exc_lead1m", "me",
    "market_equity", "dolvol_126d", "prc",
    "beta_60m", "beta_21d", "beta_252d", "beta_dimson_21d",
    "betabab_1260d", "betadown_252d", "corr_1260d",
    "ivol_capm_21d", "ivol_capm_60m", "ivol_capm_252d", "ivol_ff3_21d",
    "ivol_hxz4_21d", "iskew_capm_21d", "iskew_ff3_21d", "iskew_hxz4_21d",
    "coskew_21d", "rvol_21d", "rvol_252d", "rskew_21d",
    "rmax1_21d", "rmax5_21d", "rmax5_rvol_21d",
    "mispricing_perf", "mispricing_mgmt",
    "ret_1_0", "ret_12_1", "ret_12_7", "zero_trades_21d", "ami_126d",
    "turnover_126d",
)


def _pull(conn, sql: str, params: dict, dest: Path, meta: dict) -> int:
    df = pd.read_sql(sql, conn, params=params)
    if len(df) >= CHUNK_CAP:
        raise SystemExit(
            f"REFUSED: chunk {dest.name} filled its {CHUNK_CAP:,} cap — "
            f"truncated by construction; shrink the chunk, keep nothing.")
    df.to_parquet(dest, index=False)
    meta.update({"rows": int(len(df)),
                 "pulled_at": datetime.now(timezone.utc).isoformat(
                     timespec="seconds")})
    dest.with_suffix("").with_suffix(".meta.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8")
    return len(df)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="wrds_pull_jkp_full")
    ap.add_argument("--max-seconds", type=int, default=480)
    a = ap.parse_args(argv)
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass

    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    conn = _conn()
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = 3600000")
    done = pending = 0

    for lo, hi in USA_CHUNKS:
        dest = OUT / f"jkp_usa_{lo}_{hi}.parquet"
        if dest.exists():
            done += 1
            continue
        if time.time() - t0 > a.max_seconds:
            pending += 1
            continue
        n = _pull(conn,
                  f"SELECT * FROM {TABLE} WHERE excntry = 'USA' "
                  f"AND eom BETWEEN %(s)s AND %(e)s LIMIT {CHUNK_CAP}",
                  {"s": f"{lo}-01-01", "e": f"{hi}-12-31"}, dest,
                  {"dataset": dest.stem, "consumer": "AEGIS-PANEL-2",
                   "universe": "ALL US securities in contrib_global_factor "
                               "(no permno filter — full-cap panel is the "
                               "point; common/obs_main filtered downstream)",
                   "window": [f"{lo}-01-01", f"{hi}-12-31"],
                   "pit_knowledge_column": "eom (JKP formation stamping; "
                                           "spot-audit PASS 2026-08-22)",
                   "sql_note": "SELECT * WHERE excntry='USA' AND eom "
                               "BETWEEN chunk bounds"})
        done += 1
        print(f"  usa {lo}-{hi}: {n:,} rows "
              f"({time.time() - t0:5.0f}s elapsed)", flush=True)

    for ctry in FOREIGN:
        dest = OUT / f"jkp_risk_{ctry.lower()}_2013_2024.parquet"
        if dest.exists():
            done += 1
            continue
        if time.time() - t0 > a.max_seconds:
            pending += 1
            continue
        cols = ", ".join(FOREIGN_COLS)
        n = _pull(conn,
                  f"SELECT {cols} FROM {TABLE} WHERE excntry = %(c)s "
                  f"AND eom BETWEEN %(s)s AND %(e)s LIMIT {CHUNK_CAP}",
                  {"c": ctry, "s": "2013-01-01", "e": "2024-12-31"}, dest,
                  {"dataset": dest.stem,
                   "consumer": "RISK-PRICE-FOREIGN-CONFIRM-1",
                   "universe": f"ALL {ctry} securities (filtered "
                               f"downstream)",
                   "window": ["2013-01-01", "2024-12-31"],
                   "pit_knowledge_column": "eom",
                   "sql_note": "risk-family column subset, see "
                               "FOREIGN_COLS in the puller"})
        done += 1
        print(f"  {ctry}: {n:,} rows ({time.time() - t0:5.0f}s)",
              flush=True)

    conn.close()
    total = len(USA_CHUNKS) + len(FOREIGN)
    print(f"\n{done}/{total} chunks on disk, {pending} deferred by the "
          f"time budget — re-invoke to continue." if pending
          else f"\nALL {total} chunks on disk.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
