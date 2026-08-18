"""EFFECTIVE spreads from WRDS computed trades (wct) — the daemon's top job, v1.

    python -m scripts.wrds_taq_effective_pull            # up to --max-days
    python -m scripts.wrds_taq_effective_pull --max-days 6

Writes per-(ticker, day) rows to
`backend/data/optimus/taq_effective_spreads_v1.jsonl`, one JSON per line,
RESUMABLE: days already present are skipped, so repeated invocations converge
and a killed run loses at most one day.

WHAT THIS IS AND IS NOT (v1, stated so the verdict waits properly)
==================================================================
`taqm_2026.wct_*` carries every trade with the PREVAILING NBBO already
matched by WRDS (qtime, nbo, nbb) — the trade-quote alignment that makes
effective spreads computable without a hand-rolled join. v1 computes, per
name-day, over 09:45–15:45 with valid quotes (nbo > nbb > 0) and
eff <= 2000bp:

    effective_bps = 2 * |price - mid| / mid       (FULL spread, bps)
    quoted_at_trade_bps = (nbo - nbb) / mid

as median, plus dollar-weighted effective, plus the median-basis ratio.

DELIBERATELY NOT DONE in v1 — the daemon job's verdict (HJ-EFFECTIVE-
SPREAD-1: 'ratio materially below 1') is NOT recorded from this dataset:
no trade-condition (tr_scond) filtering, no odd-lot treatment, no
opening/closing auction exclusion beyond the time band, no Lee-Ready
signing. Those conventions are exactly what external review Q3 is out
asking about; the verdict waits for them. This file is the DATASET the
refined computation will re-derive or correct — and if the refinement
moves the numbers, that difference is itself a finding about the
conventions, which is why v1 is kept rather than overwritten.

Probe receipts (2026-08-18 night): AAPL 08-14 — 507,674 trades,
effective median 0.471bp full vs quoted-at-trade 0.656bp: ratio 0.719,
inside the documented 0.5–0.9. One day, one name; the panel decides.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

PANEL = REPO / "backend" / "data" / "optimus" / "taq_quoted_spreads_calibration.csv"
OUT = REPO / "backend" / "data" / "optimus" / "taq_effective_spreads_v1.jsonl"

DAYS = ["20260715", "20260716", "20260717", "20260720", "20260721",
        "20260722", "20260723", "20260724", "20260727", "20260728",
        "20260729", "20260730", "20260731", "20260803", "20260804",
        "20260805", "20260806", "20260807", "20260810", "20260811",
        "20260812", "20260813", "20260814"]

SQL = """
WITH t AS (
  SELECT sym_root, COALESCE(sym_suffix, '') AS sfx, price, size,
         (nbo + nbb)/2.0 AS mid, (nbo - nbb) AS qsp
  FROM taqm_2026.wct_{day}
  WHERE sym_root = ANY(%s)
    AND time_m BETWEEN '09:45:00' AND '15:45:00'
    AND nbo > nbb AND nbb > 0
), m AS (
  SELECT sym_root, sfx,
         2.0 * abs(price - mid) / mid * 1e4 AS eff_bps,
         qsp / mid * 1e4 AS quoted_bps, size * price AS dollars
  FROM t
)
SELECT sym_root, sfx, count(*),
       percentile_cont(0.5) WITHIN GROUP (ORDER BY eff_bps),
       sum(eff_bps * dollars) / NULLIF(sum(dollars), 0),
       percentile_cont(0.5) WITHIN GROUP (ORDER BY quoted_bps)
FROM m WHERE eff_bps <= 2000
GROUP BY sym_root, sfx
"""


def _universe() -> dict[tuple[str, str], str]:
    """(sym_root, sym_suffix) -> universe ticker, from the calibration panel.

    The exact pair, not the root alone: a root can carry several suffixed
    listings (preferred shares, share classes) and folding them together
    would blend different instruments into one 'name'.
    """
    out: dict[tuple[str, str], str] = {}
    with PANEL.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out[(r["sym_root"], r["sym_suffix"] or "")] = r["ticker"]
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="wrds_taq_effective_pull")
    ap.add_argument("--max-days", type=int, default=6,
                    help="days per invocation (resume handles the rest)")
    a = ap.parse_args(argv)
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass

    os.environ.setdefault("PGPASSFILE", os.path.expandvars(
        r"%APPDATA%\postgresql\pgpass.conf"))
    import psycopg2

    pair_to_ticker = _universe()
    roots = sorted({r for r, _ in pair_to_ticker})

    done: set[str] = set()
    if OUT.exists():
        for line in OUT.read_text(encoding="utf-8").splitlines():
            if line.strip():
                done.add(json.loads(line)["date"])
    todo = [d for d in DAYS if d not in done][:a.max_days]
    remaining = len([d for d in DAYS if d not in done])
    if not todo:
        print(f"COMPLETE: all {len(DAYS)} days present in {OUT.name}")
        return 0
    print(f"{len(done)} day(s) done, {remaining} remaining; this run takes "
          f"{len(todo)}")

    conn = psycopg2.connect(host="wrds-pgdata.wharton.upenn.edu", port=9737,
                            dbname="wrds", user="murathan12",
                            sslmode="require", connect_timeout=15)
    cur = conn.cursor()
    for day in todo:
        t0 = time.time()
        cur.execute(SQL.format(day=day), (roots,))
        rows = []
        for root, sfx, n, eff_med, eff_dw, q_med in cur.fetchall():
            ticker = pair_to_ticker.get((root, sfx or ""))
            if ticker is None:
                continue          # a listing sharing the root, not our name
            rows.append({
                "date": day, "ticker": ticker, "sym_root": root,
                "sym_suffix": sfx or "", "n_trades": int(n),
                "effective_full_bps_median": round(float(eff_med), 6),
                "effective_full_bps_dollar_weighted": round(float(eff_dw), 6),
                "quoted_at_trade_full_bps_median": round(float(q_med), 6),
                "pulled_at": datetime.now(timezone.utc).isoformat(
                    timespec="seconds"),
                "basis": "wct prevailing-NBBO; 09:45-15:45; nbo>nbb>0; "
                         "eff<=2000bp; NO tr_scond/odd-lot filtering (v1)",
            })
        with OUT.open("a", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        print(f"  {day}: {len(rows)} names in {time.time()-t0:.0f}s")
    conn.close()
    left = remaining - len(todo)
    print(f"REMAINING: {left}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
