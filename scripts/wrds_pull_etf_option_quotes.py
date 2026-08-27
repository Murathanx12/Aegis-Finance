"""ACTUAL listed option quotes for SPY/QQQ/IWM -- the input the core replay needs.

    python -m scripts.wrds_pull_etf_option_quotes --probe
    python -m scripts.wrds_pull_etf_option_quotes --pull 1996 2025

WHY THIS EXISTS
===============
`scripts/competition_book.price_spreads` priced the entire 70% core as

    width  = 5% of spot          (a guess at the listed strike grid)
    credit = width * 0.30        (a guess at the premium)

A simulated credit cannot answer whether SELLING a PRICED option spread makes
money, because the price is the thing under test. The seller is paid for
variance the underlying goes on to realise; the whole question is whether the
payment exceeded it. Only real quotes answer that.

Source: `optionm.opprcd{year}` (best bid / best offer per listed contract per
day) joined to `optionm.secprd{year}` for the underlying close.

SECIDS ARE VERIFIED, NOT ASSUMED
--------------------------------
`optionm.securd` returns FOUR rows for ticker 'SPY'. Three carry almost no
option rows; picking by eye would have replayed an empty book and reported it as
a flat result. Chosen by COUNTING rows in `opprcd2024`:

    109820 SPY  2,292,450      107899 QQQ  1,941,114
    106445 IWM  1,193,704      151720 SMH    635,168

THE FILTER IS ON MONEYNESS, NOT DELTA -- AND THAT IS THE WHOLE POINT
====================================================================
The first version of this file filtered `abs(delta) between 0.03 and 0.62`. It
produced a clean-looking dataset and a SILENTLY BIASED replay, because delta is
not a fixed property of a contract: it moves with the underlying.

A short put sold at delta -0.25 that goes badly wrong has a delta of -0.85 five
sessions later. The entry quote passed the filter; the EXIT quote did not, so
the block was dropped as "contract not quoted at exit". The filter was
therefore discarding precisely the losing outcomes, and it discarded 117 of 409
SPY blocks that way -- while the surviving sample still showed a loss.

Moneyness relative to the underlying close is invariant to how the trade went:
a strike is a strike. `strike between 0.55 and 1.45 x close` spans everything a
21-45 DTE vertical can reach, both rights, in either direction.

`(exdate - date) between 14 and 45` -- the low end is 14, not 21, because a
contract entered at 30 DTE must still be quoted when the position is marked
five sessions later at ~25 DTE, and a 21-day floor would drop those exits too.
That is the same bug in a different coordinate.

WHAT IS STILL EXCLUDED, ON PURPOSE
----------------------------------
`best_bid > 0` keeps only contracts that could actually be sold. This biases
TOWARD tradeability: including zero-bid options would let a replay collect
premium nobody would have paid. Recorded because a filter whose effect is not
written down becomes an assumption.

`delta` is KEPT AS A COLUMN (it is how the entry leg is chosen) but is never
used to decide which rows exist.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts import wrds_pull_vsurfd_daily as W  # noqa: E402  (connection helper)

OUT_DIR = REPO / "backend" / "data" / "optimus" / "wrds" / "optionm_etf_quotes"

#: ticker -> secid, each verified by row count in opprcd2024 (see docstring).
SECIDS = {"SPY": 109820, "QQQ": 107899, "IWM": 106445, "SMH": 151720}

MIN_DTE, MAX_DTE = 14, 45
MIN_MONEYNESS, MAX_MONEYNESS = 0.55, 1.45

QUOTES_SQL = """
select o.secid, o.date, o.exdate, o.cp_flag, o.strike_price,
       o.best_bid, o.best_offer, o.volume, o.open_interest,
       o.impl_volatility, o.delta, o.vega, o.theta,
       o.ss_flag, o.cfadj, o.optionid,
       s.close as under_close
from optionm.opprcd{year} o
join optionm.secprd{year} s on s.secid = o.secid and s.date = o.date
where o.secid = any(%(secids)s)
  and (o.exdate - o.date) between %(min_dte)s and %(max_dte)s
  and o.best_bid > 0
  and o.strike_price / 1000.0
      between %(min_m)s * s.close and %(max_m)s * s.close
"""

UNDER_SQL = """
select secid, date, open, high, low, close, volume, cfadj, return
from optionm.secprd{year}
where secid = any(%(secids)s)
"""


def _read(engine, sql: str, params: dict):
    import pandas as pd
    return pd.read_sql(sql, engine, params=params)


def pull_year(engine, year: int) -> dict:
    """One year of quotes plus that year's underlying prices."""
    import pandas as pd

    secids = [int(v) for v in SECIDS.values()]
    q = _read(engine, QUOTES_SQL.format(year=year),
              {"secids": secids, "min_dte": MIN_DTE, "max_dte": MAX_DTE,
               "min_m": MIN_MONEYNESS, "max_m": MAX_MONEYNESS})
    u = _read(engine, UNDER_SQL.format(year=year), {"secids": secids})
    if q.empty:
        return {"year": year, "rows": 0, "note": "no rows -- table exists but "
                "the filter matched nothing; NOT the same as a missing table"}

    # OptionMetrics stores the strike times 1000. Dividing HERE, once, keeps a
    # units bug from propagating into every downstream comparison.
    q["strike"] = q["strike_price"].astype(float) / 1000.0
    q["dte"] = (pd.to_datetime(q["exdate"]) - pd.to_datetime(q["date"])).dt.days
    q["mid"] = (q["best_bid"].astype(float) + q["best_offer"].astype(float)) / 2.0
    q["moneyness"] = q["strike"] / q["under_close"].astype(float)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    q.to_parquet(OUT_DIR / f"quotes_{year}.parquet", index=False)
    u.to_parquet(OUT_DIR / f"under_{year}.parquet", index=False)

    meta = {
        "year": year, "rows": int(len(q)), "under_rows": int(len(u)),
        "secids": SECIDS,
        "filter": {
            "dte": [MIN_DTE, MAX_DTE],
            "moneyness": [MIN_MONEYNESS, MAX_MONEYNESS],
            "why_not_delta": "delta moves with the underlying, so a delta filter "
                             "drops the EXIT quotes of trades that went wrong and "
                             "silently deletes the losing tail",
            "best_bid": "> 0 -- excludes untradeable zero-bid options, which "
                        "biases TOWARD tradeability by design",
        },
        "strike_units": "opprcd stores strike_price x1000; divided once here",
        "pulled_at": datetime.now(timezone.utc).isoformat(),
        "dates": [str(q["date"].min()), str(q["date"].max())],
        "by_secid": {k: int((q["secid"] == v).sum()) for k, v in SECIDS.items()},
        "delta_null_frac": float(q["delta"].isna().mean()),
    }
    (OUT_DIR / f"quotes_{year}.meta.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--pull", nargs=2, type=int, metavar=("START", "END"))
    args = ap.parse_args()

    ok, why = W._reachable()
    print(f"WRDS reachable: {ok} ({why})")
    if not ok:
        print("REFUSING: no connection. An empty pull and an unreachable server "
              "must not print the same thing.")
        return 1
    engine = W._engine()

    if args.probe:
        from sqlalchemy import text
        with engine.connect() as c:
            for y in (2005, 2013, 2024):
                n = c.execute(text(
                    QUOTES_SQL.replace("%(secids)s", ":s")
                    .replace("%(min_dte)s", str(MIN_DTE))
                    .replace("%(max_dte)s", str(MAX_DTE))
                    .replace("%(min_m)s", str(MIN_MONEYNESS))
                    .replace("%(max_m)s", str(MAX_MONEYNESS))
                    .format(year=y)
                    .replace("select o.secid, o.date, o.exdate, o.cp_flag, "
                             "o.strike_price,", "select count(*) from (select 1,")
                    ), {"s": [int(v) for v in SECIDS.values()]})
                print(f"  {y}: probe issued")
        return 0

    if args.pull:
        a, b = args.pull
        total = 0
        for y in range(a, b + 1):
            try:
                m = pull_year(engine, y)
            except Exception as exc:                       # noqa: BLE001
                print(f"  {y}: FAILED {type(exc).__name__}: {exc}", flush=True)
                continue
            total += m.get("rows", 0)
            print(f"  {y}: {m.get('rows', 0):>9,} rows  {m.get('by_secid', {})}",
                  flush=True)
        print(f"TOTAL {total:,} rows -> {OUT_DIR}")
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
