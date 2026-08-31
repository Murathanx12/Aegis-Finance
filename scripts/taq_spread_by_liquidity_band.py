"""WHAT DOES A THIN NAME ACTUALLY COST TO TOUCH? Quoted spread by dollar-volume band.

THE QUESTION THIS SETTLES
=========================
The IBES+CRSP 2013-24 test found the analyst-upside edge concentrated in a
LIQUIDITY BAND -- roughly $100k to $10m/day -- at +6.98%/yr (t 2.22). The
backtest charged 10-50 bps a side. Nobody has ever checked what those names
actually cost, and two decisions hang on the answer:

  * `universe.MIN_DOLLAR_VOLUME = 3_000_000` currently makes the thinnest part
    of that band UNOBSERVABLE, not merely unbought -- the tracker has zero names
    below $3.0m/day. Widening it is only worth doing if the edge survives the
    spread.
  * A forward "log spread_bps daily and decide after the contest" lane was
    proposed. It would take months and, on the current universe, has no names to
    measure. TAQ answers the same question from history, today.

METHOD, AND ITS HONEST LIMITS
=============================
1. `crsp.dsf` over one month defines each name's median dollar volume and its
   ticker. Bands are cut on that.
2. A stratified sample per band is measured against TAQ millisecond NBBO on
   several trading days, aggregated SERVER-SIDE: pulling raw quotes would move
   hundreds of millions of rows for no extra information.
3. The statistic is the QUOTED spread, `(ask - bid) / mid`, in bps, over regular
   hours only.

Limits, stated rather than discovered later:

  * A quoted spread is not an EFFECTIVE spread. Marketable orders often execute
    inside the quote, so this is an UPPER bound on the touch cost -- and for a
    thin name it is the relevant one, because size walks the book rather than
    improving on it.
  * It ignores market impact, which for a $500k/day name at our $6-8k ticket is
    1-2% of a day's volume and is NOT negligible.
  * CRSP ends 2024-12-31 and TAQ runs to 2026, so BOTH legs use 2024. The
    question is structural, not about this week.
  * Equal-weighting quotes over-weights quiet periods; the median is reported
    beside the mean so a skewed name is visible rather than averaged away.

So: if the edge dies at the QUOTED spread it is dead, because the real cost is
strictly worse. If it survives, that is a licence to measure effective spreads,
not a licence to trade.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "backend" / "data" / "optimus" / "wrds"
HOST, PORT, DB, USER = "wrds-pgdata.wharton.upenn.edu", 9737, "wrds", "murathan12"

#: Bands in median dollar volume per day. The first two are the ones the
#: eleven-year test liked and the tracker cannot currently see.
BANDS: tuple[tuple[str, float, float], ...] = (
    ("100k-1m", 1e5, 1e6),
    ("1m-5m", 1e6, 5e6),
    ("5m-10m", 5e6, 1e7),
    ("10m-50m", 1e7, 5e7),
    ("50m+", 5e7, 1e15),
)
PER_BAND = 30
MONTH_START, MONTH_END = "2024-06-01", "2024-06-28"
#: Measurement days. Several, because one day is a market condition, not a cost.
DAYS = ("20240610", "20240618", "20240625")

UNIVERSE_SQL = f"""
SELECT d.permno,
       MAX(n.ticker)                             AS ticker,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ABS(d.prc) * d.vol) AS mdv,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ABS(d.prc))         AS px
FROM crsp.dsf d
JOIN crsp.dsenames n
  ON n.permno = d.permno AND d.date BETWEEN n.namedt AND n.nameendt
WHERE d.date BETWEEN '{MONTH_START}' AND '{MONTH_END}'
  AND n.shrcd IN (10, 11) AND n.exchcd IN (1, 2, 3)
  AND d.prc IS NOT NULL AND d.vol IS NOT NULL AND ABS(d.prc) >= 1.0
GROUP BY d.permno
HAVING PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ABS(d.prc) * d.vol) >= 1e5
"""

#: Aggregated in the database. `natbbo_ind` keeps the national best quote, and
#: crossed/locked books (ask <= bid) are excluded rather than clamped -- a
#: negative spread is a data condition, not a cheap trade.
SPREAD_SQL = """
SELECT COUNT(*)                                                              AS n_q,
       AVG((best_ask - best_bid) / ((best_ask + best_bid) / 2.0)) * 10000    AS mean_bps,
       PERCENTILE_CONT(0.5) WITHIN GROUP (
           ORDER BY (best_ask - best_bid) / ((best_ask + best_bid) / 2.0)) * 10000 AS med_bps
FROM taqm_2024.complete_nbbo_{day}
WHERE sym_root = %s
  AND time_m BETWEEN '09:30:00' AND '16:00:00'
  AND best_bid > 0 AND best_ask > best_bid
"""


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                           # noqa: BLE001
            pass
    os.environ.setdefault("PGPASSFILE",
                          os.path.expandvars(r"%APPDATA%\postgresql\pgpass.conf"))
    import statistics as st

    import psycopg2

    conn = psycopg2.connect(host=HOST, port=PORT, dbname=DB, user=USER,
                            sslmode="require", connect_timeout=25)
    cur = conn.cursor()
    cur.execute("SET statement_timeout = 900000")

    print(f"universe: crsp.dsf {MONTH_START}..{MONTH_END}", flush=True)
    cur.execute(UNIVERSE_SQL)
    rows = [{"permno": r[0], "ticker": (r[1] or "").strip().upper(),
             "mdv": float(r[2]), "px": float(r[3])} for r in cur.fetchall()]
    rows = [r for r in rows if r["ticker"] and r["ticker"].isalpha()]
    print(f"  {len(rows):,} names with mdv >= $100k/day", flush=True)

    sample: dict[str, list[dict]] = {}
    for name, lo, hi in BANDS:
        inband = sorted((r for r in rows if lo <= r["mdv"] < hi),
                        key=lambda r: r["mdv"])
        # Even spacing across the band, not the top N: taking the most liquid
        # members of a band measures the band's easiest corner and calls it the
        # band. That is the survivorship error one level down.
        step = max(1, len(inband) // PER_BAND)
        sample[name] = inband[::step][:PER_BAND]
        print(f"  band {name:>8}: {len(inband):5,} names -> sampled {len(sample[name])}",
              flush=True)

    results = []
    for band, names in sample.items():
        print(f"\nmeasuring {band} ...", flush=True)
        for r in names:
            per_day = []
            for day in DAYS:
                try:
                    cur.execute(SPREAD_SQL.format(day=day), (r["ticker"],))
                    n_q, mean_bps, med_bps = cur.fetchone()
                except Exception as exc:                            # noqa: BLE001
                    conn.rollback()
                    cur = conn.cursor()
                    cur.execute("SET statement_timeout = 900000")
                    per_day.append({"day": day, "error": str(exc)[:90]})
                    continue
                if n_q and n_q > 0:
                    per_day.append({"day": day, "n_quotes": int(n_q),
                                    "mean_bps": float(mean_bps),
                                    "median_bps": float(med_bps)})
                else:
                    # NOT a zero spread. A name with no NBBO row that day did
                    # not trade tight, it did not quote -- recorded as absent.
                    per_day.append({"day": day, "n_quotes": 0, "no_quotes": True})
            got = [d for d in per_day if d.get("n_quotes")]
            row = {"band": band, "ticker": r["ticker"], "permno": r["permno"],
                   "mdv": round(r["mdv"], 0), "px": round(r["px"], 2),
                   "days_measured": len(got), "days_requested": len(DAYS),
                   "per_day": per_day}
            if got:
                row["median_bps"] = round(st.median([d["median_bps"] for d in got]), 2)
                row["mean_bps"] = round(st.mean([d["mean_bps"] for d in got]), 2)
            results.append(row)
            if row.get("median_bps") is not None:
                print(f"  {r['ticker']:<6} mdv ${r['mdv']/1e6:8.2f}m  "
                      f"median {row['median_bps']:8.1f} bps  "
                      f"mean {row['mean_bps']:8.1f} bps", flush=True)
            else:
                print(f"  {r['ticker']:<6} mdv ${r['mdv']/1e6:8.2f}m  NO QUOTES",
                      flush=True)

    conn.close()

    summary = {}
    for band, _lo, _hi in BANDS:
        vals = [r["median_bps"] for r in results
                if r["band"] == band and r.get("median_bps") is not None]
        miss = sum(1 for r in results if r["band"] == band and r.get("median_bps") is None)
        if vals:
            summary[band] = {
                "n_measured": len(vals), "n_no_quotes": miss,
                "median_of_median_bps": round(st.median(vals), 1),
                "p25_bps": round(sorted(vals)[len(vals) // 4], 1),
                "p75_bps": round(sorted(vals)[3 * len(vals) // 4], 1),
                "round_trip_bps": round(2 * st.median(vals), 1),
                "monthly_cost_pct_if_full_turnover":
                    round(2 * st.median(vals) / 100.0, 2),
            }
        else:
            summary[band] = {"n_measured": 0, "n_no_quotes": miss,
                             "note": "no name in this band quoted on any sampled day"}

    payload = {
        "receipt": "TAQ-SPREAD-BY-LIQUIDITY-BAND-1",
        "at": datetime.now(timezone.utc).isoformat(),
        "question": ("what does a name in each dollar-volume band cost to touch, "
                     "and does the +6.98%/yr thin-coverage edge survive it"),
        "statistic": "QUOTED spread (ask-bid)/mid in bps, regular hours, per name "
                     "per day, aggregated server-side; an UPPER bound on touch cost",
        "limits": ["quoted, not effective -- marketable orders can execute inside",
                   "excludes market impact, which binds hardest in the thin bands",
                   "CRSP ends 2024-12-31 so both legs use 2024",
                   "equal-weighted over quotes; median reported beside mean"],
        "universe_month": [MONTH_START, MONTH_END],
        "days": list(DAYS),
        "per_band": PER_BAND,
        "summary": summary,
        "rows": results,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    dst = OUT / "taq_spread_by_liquidity_band.json"
    dst.write_text(json.dumps(payload, indent=1), encoding="utf-8")

    print("\n" + "=" * 72)
    print("QUOTED SPREAD BY DOLLAR-VOLUME BAND (2024, regular hours)")
    print("=" * 72)
    print(f"{'band':>10}  {'n':>4}  {'median bps':>11}  {'round-trip':>11}  "
          f"{'p25-p75':>16}  {'no quotes':>9}")
    for band, _lo, _hi in BANDS:
        s = summary[band]
        if s.get("n_measured"):
            print(f"{band:>10}  {s['n_measured']:>4}  {s['median_of_median_bps']:>11.1f}  "
                  f"{s['round_trip_bps']:>11.1f}  "
                  f"{s['p25_bps']:>7.1f}-{s['p75_bps']:<8.1f}  {s['n_no_quotes']:>9}")
        else:
            print(f"{band:>10}  {'--':>4}  {'no quotes':>11}")
    print(f"\nreceipt -> {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
