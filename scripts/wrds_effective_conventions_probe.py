"""Effective-spread CONVENTIONS PROBE — the grid, on three liquidity tiers.

External review Q3 (and the deferred HJ-EFFECTIVE-SPREAD-1 verdict) turn on
trade-condition conventions. v1 measured everything unfiltered and deferred.
This probe measures how much each convention MOVES the number, per liquidity
tier, on one session — a SENSITIVITY receipt, explicitly not a verdict:
the daemon job's verdict still waits for the conventions ruling, and this
receipt is evidence FOR that ruling rather than a bypass of it.

Names (from the calibration's own tiers): NVDA (sub-1bp), DXCM (~5bp),
PLUG (~47bp). Session: 2026-08-14 (the v1 probe day). All aggregation is
server-side (percentile_cont in one GROUP BY per name) — no raw prints
leave WRDS.

Conventions measured (each a DECLARED flag, composable):
- midpoint prints excluded (eff > 0)             — the ratio-drag term
- HJ-style condition filter (tr_scond has none of O,Z,B,T,L,G,W,K,J)
- odd lots excluded (size >= 100)
- venue: all | exchange-only | TRF-only (ex = 'D')
- quote-lag buckets: time_m − qtime ≤ 50ms | 50ms–500ms | > 500ms
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

DAY = os.environ.get("PROBE_DAY", "20260814")
#: Three names per tier when PROBE_WIDE=1; the original trio otherwise.
NAMES = {"NVDA": "liquid_sub1bp", "DXCM": "mid_5bp", "PLUG": "illiquid_47bp"}
if os.environ.get("PROBE_WIDE"):
    NAMES = {"NVDA": "liquid", "AAPL": "liquid", "MSFT": "liquid",
             "DXCM": "mid", "WEC": "mid", "ZBH": "mid",
             "PLUG": "illiquid", "SOC": "illiquid", "FSLR": "illiquid"}
_TAG = "_wide" if os.environ.get("PROBE_WIDE") else ""
OUT = REPO / "backend" / "data" / "optimus" / \
    f"effective_conventions_probe_{DAY}{_TAG}.json"

#: Holden–Jacobsen-style exclusion set, declared here once.
HJ_EXCLUDE = "OZBTLGWKJ"

SQL = """
WITH prints AS (
  SELECT price, size, ex, COALESCE(tr_scond, '') AS cond,
         (nbo + nbb) / 2.0 AS mid,
         (nbo - nbb) AS spread,
         EXTRACT(EPOCH FROM (time_m - qtime)) * 1000.0 AS lag_ms
  FROM taqm_2026.wct_{day}
  WHERE sym_root = %(root)s
    AND (sym_suffix IS NULL OR sym_suffix = '')
    AND time_m BETWEEN '09:45:00' AND '15:45:00'
    AND nbo > nbb AND nbb > 0
    AND price > 0
), m AS (
  SELECT price, size, ex, cond, mid, lag_ms,
         2.0 * ABS(price - mid) / mid * 10000.0 AS eff_bps,
         spread / mid * 10000.0 AS quoted_bps,
         (ABS(price - mid) < 1e-9)                   AS is_mid_print,
         (cond ~ '[{hj}]')                           AS hj_excluded,
         (size < 100)                                AS odd_lot,
         (ex = 'D')                                  AS is_trf
  FROM prints
  WHERE 2.0 * ABS(price - mid) / mid * 10000.0 <= 2000.0
)
SELECT convention, n_prints,
       ROUND(med_eff::numeric, 4)  AS med_eff_bps,
       ROUND(med_q::numeric, 4)    AS med_quoted_bps,
       ROUND((med_eff / NULLIF(med_q, 0))::numeric, 4) AS ratio
FROM (
  SELECT 'v1_all' AS convention, COUNT(*) AS n_prints,
         PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY eff_bps) AS med_eff,
         PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY quoted_bps) AS med_q
  FROM m
  UNION ALL
  SELECT 'no_midpoint', COUNT(*),
         PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY eff_bps),
         PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY quoted_bps)
  FROM m WHERE NOT is_mid_print
  UNION ALL
  SELECT 'hj_conditions', COUNT(*),
         PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY eff_bps),
         PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY quoted_bps)
  FROM m WHERE NOT hj_excluded
  UNION ALL
  SELECT 'round_lots_only', COUNT(*),
         PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY eff_bps),
         PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY quoted_bps)
  FROM m WHERE NOT odd_lot
  UNION ALL
  SELECT 'exchange_only', COUNT(*),
         PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY eff_bps),
         PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY quoted_bps)
  FROM m WHERE NOT is_trf
  UNION ALL
  SELECT 'trf_only', COUNT(*),
         PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY eff_bps),
         PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY quoted_bps)
  FROM m WHERE is_trf
  UNION ALL
  SELECT 'lag_le_50ms', COUNT(*),
         PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY eff_bps),
         PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY quoted_bps)
  FROM m WHERE lag_ms <= 50
  UNION ALL
  SELECT 'lag_50_500ms', COUNT(*),
         PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY eff_bps),
         PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY quoted_bps)
  FROM m WHERE lag_ms > 50 AND lag_ms <= 500
  UNION ALL
  SELECT 'lag_gt_500ms', COUNT(*),
         PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY eff_bps),
         PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY quoted_bps)
  FROM m WHERE lag_ms > 500
  UNION ALL
  SELECT 'composed_hj_rounds_nomid', COUNT(*),
         PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY eff_bps),
         PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY quoted_bps)
  FROM m WHERE NOT hj_excluded AND NOT odd_lot AND NOT is_mid_print
) g
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

    conn = psycopg2.connect(host="wrds-pgdata.wharton.upenn.edu", port=9737,
                            dbname="wrds", user="murathan12",
                            sslmode="require", connect_timeout=15)
    cur = conn.cursor()
    results: dict = {"day": DAY, "hj_exclude_set": HJ_EXCLUDE,
                     "generated_at": datetime.now(timezone.utc).isoformat(
                         timespec="seconds"),
                     "status": "SENSITIVITY — not a verdict; evidence for "
                               "the conventions ruling (review Q3)",
                     "names": {}}
    q = SQL.format(day=DAY, hj=HJ_EXCLUDE)
    for root, tier in NAMES.items():
        cur.execute(q, {"root": root})
        rows = [{"convention": r[0], "n_prints": int(r[1]),
                 "med_eff_bps": float(r[2]) if r[2] is not None else None,
                 "med_quoted_bps": float(r[3]) if r[3] is not None else None,
                 "ratio": float(r[4]) if r[4] is not None else None}
                for r in cur.fetchall()]
        results["names"][root] = {"tier": tier, "grid": rows}
        print(f"\n{root} ({tier}):")
        for r in rows:
            if r["n_prints"] == 0:
                print(f"  {r['convention']:<26} n=        0 (empty cell — "
                      f"reported, not defaulted)")
                continue
            print(f"  {r['convention']:<26} n={r['n_prints']:>9,} "
                  f"eff {r['med_eff_bps']:>8.3f}bp  "
                  f"quoted {r['med_quoted_bps']:>8.3f}bp  "
                  f"ratio {r['ratio']}")
    conn.close()
    OUT.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nreceipt: {OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
