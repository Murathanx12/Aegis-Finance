"""UNIVERSE-SURVIVAL-STRESS-1 — the CRSP PIT membership panel (construction).

P-grind-2026-08-19a, approved. The NET panel's universe is a 2026 selection
applied back to 2013; this pulls the point-in-time alternative from CRSP so
the selection effect becomes measurable instead of argued about.

WHAT THIS BUILDS (construction only — no tournament, no verdicts):
- monthly PIT-eligible membership 2013-01..2024-11 (the entitled vintage
  ends 2024-12-31): common stock (shrcd 10/11), NYSE/AMEX/NASDAQ, price
  ≥ $5, monthly dollar volume ≥ $100M (CRSP msf.vol is in HUNDREDS of
  shares — the unit that silently shrank the first scope probe 100×);
- monthly returns INCLUDING delisting returns (dlret merged into the
  delisting month — the rows survivorship-tilted panels never have);
- the comparison block vs the 2026-selected 182 panel: membership counts,
  entry/exit/delist incidence, overlap, return dispersion.

Filters are FROZEN here, prospectively; changing them after the tournament
sensitivity runs would be selection wearing a robustness check.
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
START, END = "2013-01-01", "2024-11-30"
MIN_PRICE = 5.0
MIN_DOLLAR_VOL_MONTH = 100_000_000.0    # $100M/month ≈ $5M/day

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
    print("pulling crsp.msf universe (one query)...")
    df = pd.read_sql(SQL, conn)
    conn.close()
    print(f"raw rows: {len(df):,}  permnos: {df['permno'].nunique():,}")

    # PIT eligibility decided from month-t information only
    df["eligible"] = ((df["prc"] >= MIN_PRICE)
                      & (df["dollar_vol"] >= MIN_DOLLAR_VOL_MONTH))
    # delist-inclusive return: the delisting month compounds dlret
    df["ret_incl_delist"] = df["ret"]
    has_dl = df["dlret"].notna()
    df.loc[has_dl, "ret_incl_delist"] = (
        (1 + df.loc[has_dl, "ret"].fillna(0))
        * (1 + df.loc[has_dl, "dlret"]) - 1)

    el = df[df["eligible"]]
    monthly = el.groupby(el["date"].astype(str).str[:7])["permno"].nunique()

    # the 2026-selected 182, for the overlap block
    cal = json.load(open(REPO / "backend" / "data" / "optimus"
                         / "taq_cost_calibration.json", encoding="utf-8"))
    panel_tickers = {r["ticker"] for r in cal["rows"]}
    el_tickers_ever = set(el["ticker"].unique())

    delist_months = df[has_dl & df["eligible"].groupby(
        df["permno"]).transform("any")]
    comparison = {
        "pit_permnos_ever_eligible": int(el["permno"].nunique()),
        "monthly_membership": {"min": int(monthly.min()),
                               "median": float(monthly.median()),
                               "max": int(monthly.max())},
        "delistings_of_ever_eligible_names": int(
            delist_months["permno"].nunique()),
        "panel_182_tickers_seen_in_pit": len(
            panel_tickers & el_tickers_ever),
        "panel_182_total": len(panel_tickers),
        "monthly_ret_dispersion_pit": round(float(
            el.groupby(el["date"].astype(str).str[:7])["ret_incl_delist"]
            .std().median()), 5),
        "note": ("the 2026 panel names appear under their HISTORICAL "
                 "tickers in CRSP (MRSH was MMC, XYZ was SQ) — the overlap "
                 "count via ticker alone UNDERSTATES; PERMNO join is the "
                 "tournament-sensitivity build's job"),
    }

    df.to_parquet(OUT / "crsp_pit_monthly_v1.parquet", index=False)
    meta = {"dataset": "CRSP-PIT-MONTHLY-1 (construction)",
            "window": [START, END],
            "filters_frozen": {"shrcd": [10, 11], "exchcd": [1, 2, 3],
                               "min_price": MIN_PRICE,
                               "min_dollar_vol_month": MIN_DOLLAR_VOL_MONTH,
                               "vol_units": "CRSP msf.vol is HUNDREDS of "
                                            "shares; dollar_vol = prc*vol*100"},
            "delist_returns": "dlret compounded into the delisting month",
            "vintage_limit": "entitled crsp vintage ends 2024-12-31",
            "n_rows": int(len(df)),
            "comparison_vs_2026_panel": comparison,
            "no_verdicts_note": "membership + returns construction only; "
                                "the tournament sensitivity runs under "
                                "UNIVERSE-SURVIVAL-STRESS-1's own protocol",
            "generated_at": datetime.now(timezone.utc).isoformat(
                timespec="seconds")}
    (OUT / "crsp_pit_monthly_v1.meta.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(comparison, indent=2))
    print(f"wrote {OUT / 'crsp_pit_monthly_v1.parquet'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
