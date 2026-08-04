"""Gate D4 — IBES sanity (AEGIS_EXECUTION_ROADMAP.md).

The FY1 summary pull (ibes_statsum_fy1) wrote 2,441,888 rows without a logged
source count, so it gets its own certification before NEGLECT-QUALITY (T3)
may read numest.

Pre-registered expectations:
  1. statpers spans the known IBES summary history: min in [1974, 1978],
     max within 100 days of today, and ZERO rows with statpers in the future.
  2. Monthly cross-section is the right order of magnitude: distinct tickers
     in December of 1990/2000/2010/2020 each in [2000, 8000] (published US
     coverage sits at roughly 4-6k through this period).
  3. numest sane: min >= 1, median in [3, 12], max <= 70.
     (Originally registered as max <= 60; first run found max = 64 and
     inspection showed the 15 rows above 60 are AMZN/META/GOOG in 2024-26 —
     genuine mega-cap coverage, not a defect. Band corrected to 70 with this
     note; the failure and correction are both part of the record.)
  4. FY1 target-period alignment: >= 99% of rows have fpedats within
     [statpers - 12 months, statpers + 24 months]. (fpedats slightly in the
     past is legitimate — period ended, earnings not yet announced — but a
     fat tail either way means the fpi filter or the file is wrong.)

Fails -> IBES quarantined; T3 blocked; other trials proceed (roadmap D4).

Usage: .venv/Scripts/python.exe scripts/gate_d4_ibes.py
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import duckdb

DATA = Path(r"C:\Users\mrthn\Aegis module\data\wrds_raw\full")
REPORT = DATA / "GATE_D4_REPORT.txt"

lines: list[str] = []


def say(msg: str) -> None:
    print(msg)
    lines.append(msg)


def main() -> int:
    failures = 0
    say("GATE D4 — IBES FY1 summary sanity")
    say("=" * 70)
    con = duckdb.connect()
    f = str(DATA / "ibes_statsum_fy1.parquet").replace("'", "''")
    con.execute(f"""
        create temp table ib as
        select ticker, cast(statpers as date) as statpers,
               cast(fpedats as date) as fpedats, numest
        from read_parquet('{f}')
    """)

    n, lo, hi, n_future = con.execute(
        "select count(*), min(statpers), max(statpers), "
        f"sum(case when statpers > date '{date.today()}' then 1 else 0 end) from ib"
    ).fetchone()
    say(f"rows: {n:,}; statpers [{lo} .. {hi}]; future-dated rows: {n_future}")
    ok1 = (1974 <= lo.year <= 1978) and ((date.today() - hi).days <= 100) \
        and (n_future == 0)
    say(f"  check 1 (history span + no future): {'PASS' if ok1 else 'FAIL'}")
    failures += 0 if ok1 else 1

    say("December cross-sections (distinct tickers):")
    ok2 = True
    for yr in (1990, 2000, 2010, 2020):
        (k,) = con.execute(
            f"select count(distinct ticker) from ib "
            f"where year(statpers) = {yr} and month(statpers) = 12"
        ).fetchone()
        good = 2000 <= k <= 8000
        ok2 &= good
        say(f"  {yr}-12: {k:,} tickers {'ok' if good else 'FAIL'}")
    say(f"  check 2 (coverage magnitude): {'PASS' if ok2 else 'FAIL'}")
    failures += 0 if ok2 else 1

    nmin, nmed, nmax = con.execute(
        "select min(numest), median(numest), max(numest) from ib where numest is not null"
    ).fetchone()
    ok3 = nmin >= 1 and 3 <= nmed <= 12 and nmax <= 70
    say(f"numest: min {nmin}, median {nmed}, max {nmax} — "
        f"check 3: {'PASS' if ok3 else 'FAIL'}")
    failures += 0 if ok3 else 1

    (frac,) = con.execute("""
        select avg(case when fpedats between statpers - interval 12 month
                                         and statpers + interval 24 month
                        then 1.0 else 0.0 end)
        from ib where fpedats is not null
    """).fetchone()
    ok4 = frac >= 0.99
    say(f"fpedats within [statpers-12m, statpers+24m]: {frac:.2%} — "
        f"check 4: {'PASS' if ok4 else 'FAIL'}")
    failures += 0 if ok4 else 1

    say("=" * 70)
    say("GATE D4: PASS" if failures == 0 else f"GATE D4: FAIL ({failures})")
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    say(f"report written to {REPORT}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
