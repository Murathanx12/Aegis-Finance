"""Bounded pull of ATM OptionMetrics around the 52,604 earnings events.

    python -m scripts.wrds_pull_stdopd_events --plan
    python -m scripts.wrds_pull_stdopd_events --pull 2006 2019

THE CONSUMER, NAMED FIRST
=========================
`docs/FINDING_2026-08-24_EVENT_RESPONSE.md` returned STOP: post-earnings drift
is real (+7bps) and nothing ranks WHICH events drift. Its own diagnosis names
the most likely reason — `options_implied_move` is `None` through the entire g4
corpus, so "surprise" was measured against analyst consensus alone when the
tradable quantity is `surprise MINUS what was already priced`.

This pull is that missing feature and nothing else. A named consumer is the rule
for un-deferring an OptionMetrics extraction, and it has one.

WHY THIS IS SMALL, AND WHY THAT IS NOT AN OPTIMISATION
======================================================
`optionm.stdopd2015` alone is 15.9M rows; the family across 1996-2024 is roughly
450M. The deferral in the substrate receipt was never "OptionMetrics is big" —
it was pulling a family blind, with no consumer to bound it. Bounded by the
consumer's actual event set this is:

    2,418 secids          every secid a linked earnings event needs
    days IN (30, 60)      the implied move, and one point of term structure
    both cp_flags         a move is the average of the two sides
    2006-2019             the g4 corpus's own extent

which is ~4 of the 14 rows per secid-date that `stdopd` carries.

THE BOUND IS DECLARED IN THE MANIFEST so a later reader cannot mistake a narrow
extraction for missing data. That is the specific error this dataset has already
caused twice: `wrds_pull_vsurfd_daily`'s docstring records month-end coverage
being reported as a property of OptionMetrics when it was a property of our own
WHERE clause. **A property of your extraction is not a property of the data.**

WHAT THIS CANNOT GIVE YOU
=========================
**Skew.** Measured 2026-08-24 against `stdopd1996`: it holds one row per
(secid, date, maturity, side) and delta is not a coordinate — 30-day calls sit
at a median delta of +0.523 and puts at -0.482. Both on the money, no OTM wings,
so no 25-delta, no risk reversal, no butterfly. Skew needs `vsurfd`. A "skew"
computed from this pull would be code running green and measuring something
else.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "backend" / "data" / "optimus" / "wrds" / "stdopd_events"
MANIFEST = OUT / "manifest.json"

#: Declared bound. Every one of these is in the manifest.
MATURITIES = (30, 60)
FIRST_YEAR, LAST_YEAR = 2006, 2019

SQL = """
select secid, date, days, cp_flag, impl_volatility, delta, vega,
       forward_price, strike_price, premium
from optionm.stdopd{year}
where days in ({maturities})
  and secid in ({secids})
"""


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def event_secids() -> tuple[list[int], pd.DataFrame]:
    """The secids the consumer actually needs, via the CRSP-OptionMetrics link."""
    from scripts.event_response_v1 import link_permno, load_events

    ev = link_permno(load_events())[["event_id", "permno", "event_date"]]
    lk = pd.read_parquet(REPO / "backend" / "data" / "optimus" / "wrds" /
                         "bulk" / "wrdsapps__opcrsphist.parquet")
    lk["permno"] = pd.to_numeric(lk["permno"], errors="coerce").astype("Int64")
    lk["sdate"] = pd.to_datetime(lk["sdate"])
    lk["edate"] = pd.to_datetime(lk["edate"])
    lk = lk.dropna(subset=["permno", "secid"])
    m = ev.merge(lk, on="permno", how="left")
    ok = m[(m["event_date"] >= m["sdate"]) & (m["event_date"] <= m["edate"])]
    ok = ok.drop_duplicates(subset=["event_id"])
    if len(ok) < 0.9 * len(ev):
        sys.exit(f"REFUSED: only {len(ok)}/{len(ev)} events link to a secid. "
                 f"A pull bounded by a broken link is bounded by the wrong set.")
    return sorted({int(s) for s in ok["secid"].dropna()}), ok


def plan() -> dict:
    secids, ok = event_secids()
    return {
        "consumer": "EVENT-RESPONSE-1 successor (surprise - implied move)",
        "n_events_linked": int(len(ok)),
        "n_secids": len(secids),
        "maturities_days": list(MATURITIES),
        "cp_flags": ["C", "P"],
        "years": [FIRST_YEAR, LAST_YEAR],
        "bound_rationale": ("bounded by the consumer's event set, not by a "
                            "table family; the bound is declared so a narrow "
                            "extraction is never mistaken for missing data"),
        "cannot_provide": ("skew / 25-delta / risk reversal / butterfly — "
                           "stdopd is ATM-only (median 30d call delta +0.523, "
                           "put -0.482). Those need vsurfd."),
    }


def pull(y0: int, y1: int) -> dict:
    os.environ.setdefault(
        "PGPASSFILE", str(Path.home() / "AppData/Roaming/postgresql/pgpass.conf"))
    from scripts.wrds_pull_vsurfd_daily import _engine

    OUT.mkdir(parents=True, exist_ok=True)
    secids, _ = event_secids()
    sec_sql = ",".join(str(s) for s in secids)
    mat_sql = ",".join(str(m) for m in MATURITIES)
    eng = _engine()

    man = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {
        "dataset": "optionm/stdopd_events_v1", "plan": plan(), "years": {}}

    for yr in range(y0, y1 + 1):
        p = OUT / f"stdopd_events_{yr}.parquet"
        if p.exists() and str(yr) in man.get("years", {}):
            print(f"  {yr}: already on disk, skipping", flush=True)
            continue
        sql = SQL.format(year=yr, maturities=mat_sql, secids=sec_sql)
        t0 = datetime.now(timezone.utc)
        print(f"  {yr}: querying...", flush=True)
        try:
            d = pd.read_sql(sql, eng)
        except Exception as e:                                  # noqa: BLE001
            print(f"  {yr}: FAILED {type(e).__name__}: {str(e)[:160]}",
                  flush=True)
            man.setdefault("years", {})[str(yr)] = {
                "status": "FAILED", "error": f"{type(e).__name__}: {e}"[:300]}
            MANIFEST.write_text(json.dumps(man, indent=2, default=str))
            continue
        if d.empty:
            # An empty year is a FINDING, not a quiet skip: these secids
            # demonstrably had earnings that year.
            print(f"  {yr}: EMPTY — recorded as a finding", flush=True)
            man.setdefault("years", {})[str(yr)] = {
                "status": "EMPTY",
                "note": ("returned zero rows for secids that demonstrably had "
                         "earnings events this year — investigate before "
                         "treating this year as having no options data")}
            MANIFEST.write_text(json.dumps(man, indent=2, default=str))
            continue
        d.to_parquet(p, index=False)
        man.setdefault("years", {})[str(yr)] = {
            "status": "ok",
            "rows": int(len(d)),
            "secids_returned": int(d["secid"].nunique()),
            "dates": int(d["date"].nunique()),
            "impl_vol_non_null": round(float(d["impl_volatility"].notna().mean()), 4),
            "sha256": _sha256(p),
            "queried_at": t0.isoformat(timespec="seconds"),
            "seconds": round((datetime.now(timezone.utc) - t0).total_seconds(), 1),
            "sql": " ".join(sql.split())[:400] + f" -- [{len(secids)} secids]",
        }
        MANIFEST.write_text(json.dumps(man, indent=2, default=str))
        print(f"  {yr}: {len(d):,} rows, {d['secid'].nunique()} secids, "
              f"IV non-null {d['impl_volatility'].notna().mean():.1%}", flush=True)
    return man


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="wrds_pull_stdopd_events")
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--pull", nargs=2, type=int, metavar=("Y0", "Y1"))
    a = ap.parse_args(argv)
    if a.plan:
        print(json.dumps(plan(), indent=2))
        return 0
    if a.pull:
        man = pull(*a.pull)
        tot = sum(v.get("rows", 0) for v in man.get("years", {}).values())
        print(f"\nTOTAL {tot:,} rows across "
              f"{sum(1 for v in man['years'].values() if v.get('status') == 'ok')} years")
        return 0
    ap.error("pass --plan or --pull Y0 Y1")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
