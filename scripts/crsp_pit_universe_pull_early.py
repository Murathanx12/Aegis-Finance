"""CRSP PIT membership panel — the HELD-OUT EARLY ERA (1990–2012).

    python -m scripts.crsp_pit_universe_pull_early

Purpose: tonight's screen survivors (anti-chasing rules, the
value+winner-exempt lead) were generated on 2013–2024. Confirming them
on the generating sample would be §37 wearing a lab coat; this pulls
the 1990–2012 era — NEVER touched by any Aegis computation — as the
out-of-era confirmation slice (§60: held-out TIME).

Filters are BYTE-IDENTICAL to `crsp_pit_universe_pull.py` (frozen
there, prospectively). Disclosed limitation carried in the meta: the
$5 / $100M-month cuts are NOMINAL, so they are a stricter REAL screen
in 1990 than in 2024 — identical rule, drifting real meaning; any
confirmation read must carry this note.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OUT = REPO / "backend" / "data" / "optimus" / "crsp_pit"
START, END = "1990-01-01", "2012-12-31"
MIN_PRICE = 5.0
MIN_DOLLAR_VOL_MONTH = 100_000_000.0

SQL = f"""
SELECT m.permno, m.date, ABS(m.prc) AS prc, m.ret,
       ABS(m.prc) * m.vol * 100.0 AS dollar_vol,
       n.ticker, n.comnam,
       d.dlret, d.dlstcd
FROM crsp.msf m
JOIN crsp.stocknames n
  ON n.permno = m.permno AND m.date BETWEEN n.namedt AND n.nameenddt
LEFT JOIN crsp.msedelist d
  ON d.permno = m.permno
  AND date_trunc('month', d.dlstdt) = date_trunc('month', m.date)
WHERE m.date BETWEEN '{START}' AND '{END}'
  AND n.shrcd IN (10, 11)
  AND n.exchcd IN (1, 2, 3)
  AND m.prc IS NOT NULL
"""


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass
    os.environ.setdefault("PGPASSFILE", os.path.expandvars(
        r"%APPDATA%\postgresql\pgpass.conf"))
    import psycopg2

    OUT.mkdir(parents=True, exist_ok=True)
    conn = psycopg2.connect(host="wrds-pgdata.wharton.upenn.edu", port=9737,
                            dbname="wrds", user="murathan12",
                            sslmode="require", connect_timeout=15)
    print("pulling crsp.msf EARLY era (one query)...")
    df = pd.read_sql(SQL, conn)
    conn.close()
    print(f"raw rows: {len(df):,}  permnos: {df['permno'].nunique():,}")

    df["eligible"] = ((df["prc"] >= MIN_PRICE)
                      & (df["dollar_vol"] >= MIN_DOLLAR_VOL_MONTH))
    df["ret_incl_delist"] = df["ret"]
    has_dl = df["dlret"].notna()
    df.loc[has_dl, "ret_incl_delist"] = (
        (1 + df.loc[has_dl, "ret"].fillna(0))
        * (1 + df.loc[has_dl, "dlret"]) - 1)

    el = df[df["eligible"]]
    monthly = el.groupby(el["date"].astype(str).str[:7])["permno"].nunique()
    df.to_parquet(OUT / "crsp_pit_monthly_early.parquet", index=False)
    meta = {"dataset": "CRSP-PIT-MONTHLY-EARLY (held-out confirmation era)",
            "window": [START, END],
            "filters_frozen": "byte-identical to crsp_pit_monthly_v1; "
                              "NOMINAL cuts are a stricter real screen in "
                              "1990 — disclosed, never re-tuned",
            "purpose": "out-of-era confirmation slice for 2013-24-generated "
                       "screen survivors; untouched before this pull",
            "n_rows": int(len(df)),
            "ever_eligible_permnos": int(el["permno"].nunique()),
            "monthly_membership": {"min": int(monthly.min()),
                                   "median": float(monthly.median()),
                                   "max": int(monthly.max())},
            "delistings_of_eligible": int(
                df[has_dl]["permno"].nunique()),
            "generated_at": datetime.now(timezone.utc).isoformat(
                timespec="seconds")}
    (OUT / "crsp_pit_monthly_early.meta.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in meta.items()
                      if k not in ("filters_frozen",)}, indent=2,
                     default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
