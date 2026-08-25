"""Re-pull `wrdsapps_finratio.firm_ratio` 1990-2012 with the FULL column set.

    python -m scripts.wrds_repull_finratio_early --dry-run
    python -m scripts.wrds_repull_finratio_early

THE SAME TRAP, ONE TABLE ALONG
==============================
`finratio_monthly_early.parquet` exists, so every existence-keyed puller in this
repo skips it forever. It was pulled 2026-08-19 with exactly five columns:

    gvkey, permno, public_date, bm, roe

and its own metadata says why — *"columns limited to the two signals the frozen
grammar uses"*. That was correct for the grammar of 2026-08-19. It is the
binding constraint of 2026-08-25, because the modern file
(`finratio_monthly`, 2013-2024) carries **~100 columns** including every
profitability, safety, growth and accrual measure a quality composite needs,
plus `gsector` / `ffi48` / `ffi49` industry codes and `mktcap`.

So `characteristics.AVAILABLE` is `("bm", "roe")` NOT because that is what
WRDS serves, but because that is what the early parquet happens to hold, and a
characteristic present in only one era would silently change what a 1993-2024
run measures at the 2013 boundary.

This is the third appearance of one failure shape, and the ledger already names
the first two:

  * *"a failure-driven queue cannot see a NEVER-ATTEMPTED item"* (2026-08-23)
  * *"an existence-keyed queue cannot see a PARTIALLY-PULLED item"*
    (`wrds_repull_dsf_early`, 2026-08-25)

The resume rule here is therefore keyed on **COLUMNS**, exactly as the dsf
re-pull is: the file is skipped only when it already carries everything
`REQUIRED` names. That rule is the fix; the pull is what follows from it.

WHAT IT BUYS, AND WHY IT IS THE ENABLING PULL
==============================================
The 2026-08-25 farm result is that raw `profit_roe` at k=100 beats an
age-matched control by +1.53%/yr and needs 126 years to resolve that. The
diagnosis was NOT "ROE is dead" — it was **ROE is confounded by listing age**,
because high-ROE large caps ARE old listings.

The response is to neutralise, and neutralising needs columns this file does
not have:

    industry     gsector, ffi48, ffi49   <- rank WITHIN industry
    size         mktcap                  <- the other half of the confound
    profitability roa, gprof, gpm, npm, opmad, cfm, ptpm
    safety       de_ratio, debt_at, curr_ratio, intcov_ratio, cash_ratio
    accruals     accrual                 <- the leg that separates quality
                                            from earnings management
    growth       at_turn, sale_equity

Without this pull, `QUALITY_RESIDUAL_v1` can only be tested on 2013-2024 — the
window the project has already established cannot resolve anything (0 of 15
signals, and a mega-cap decade whose breadth verdict REVERSED on 32 years).
With it, the composite is testable on the full replayable window.

STATUS 2026-08-25: **THIS PULL HAS NOT COMPLETED.** Run it again.

It was attempted three times and landed nothing. What was measured, so the next
attempt does not re-derive it:

  * one `SELECT *` over 15,519 permnos x 23 years ran **1h40m and wrote zero
    bytes** before being killed. An un-resumable query producing no partial
    output is worth exactly as much as no query, and the cost of learning that
    is the whole 1h40m;
  * chunked to one query per year, still no year landed in ~9 minutes;
  * narrowed to 36 columns, still none;
  * **without the permno predicate at all**, a single year did not return in
    4.5 minutes — so the constraint is WRDS-side throughput, not the query
    shape. The 2026-08-19 five-column pull DID succeed, and 36 columns is
    roughly seven times the payload.

The script is now resumable by year: each year is a part file under
`_finratio_early_parts/`, a kill costs one year rather than all of them, and a
re-run skips what already landed. **Run it attended, with hours available, and
check the part count rather than watching for a final file.** Nothing it has
done so far has touched the existing 5-column parquet.

WHAT IT DOES NOT FIX
====================
Nothing here touches the 1990-1992 problem. `panel.py` still refuses those
years for want of `openprc`, and the early PIT universe is still too thin to
screen a top-500 cut. The replayable window stays **1993-2024** and this pull
does not extend it by a day — it widens the panel, not the window.

Nor does a wider column list make a characteristic PIT-safe by itself.
`public_date` remains the availability stamp and `characteristics.py` remains
the only place allowed to do the join, with its strict inequality intact.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

import pandas as pd

from backend import config as _config

DATASET = "finratio_monthly_early"
START, END = "1990-01-01", "2012-12-31"

#: The re-pull is warranted only if it lands these. Keyed on COLUMNS: the file
#: is skipped when it already carries every one of them, and re-pulled when it
#: carries the parquet but not the columns — the state an existence check calls
#: "done".
#:
#: This is the intersection of what `QUALITY_RESIDUAL_v1` needs with what the
#: modern file demonstrably serves, so a successful pull makes the two eras
#: column-compatible rather than merely both-present.
REQUIRED = (
    "gvkey", "permno", "public_date",
    # already there — kept so the skip rule stays a superset check
    "bm", "roe",
    # profitability
    "roa", "gprof", "gpm", "npm", "opmad", "ptpm", "cfm", "aftret_eq",
    # safety / leverage
    "de_ratio", "debt_at", "curr_ratio", "quick_ratio", "intcov_ratio",
    "cash_ratio", "lt_debt", "debt_ebitda",
    # accruals and turnover
    "accrual", "at_turn", "inv_turn", "sale_equity", "ocf_lct",
    # the neutralisation axes — the entire point of the pull
    "mktcap", "price", "ptb", "divyield",
    "gsector", "ffi48", "ffi49", "ffi12",
    "ticker", "cusip",
)


def _path():
    from backend.services.portfolio_farm.characteristics import WRDS_DIR
    return WRDS_DIR / f"{DATASET}.parquet"


def existing_columns() -> set[str]:
    p = _path()
    if not p.exists():
        return set()
    try:
        import pyarrow.parquet as pq
        return set(pq.ParquetFile(p).schema_arrow.names)
    except Exception as exc:                                   # noqa: BLE001
        print(f"  ! cannot read schema of {p.name}: {exc}")
        return set()


def missing_columns() -> list[str]:
    have = existing_columns()
    if not have:
        return list(REQUIRED)
    return [c for c in REQUIRED if c not in have]


def _connect():
    """The SAME read-only psycopg2 connection every other puller here uses.

    NOT `wrds.Connection`: that wrapper is not a DBAPI connection, so
    `pd.read_sql` cannot take a cursor from it and dies with
    `'Connection' object has no attribute 'cursor'` AFTER the slow library
    listing has already run. Measured 2026-08-25.
    """
    import os
    os.environ.setdefault("PGPASSFILE", os.path.expandvars(
        r"%APPDATA%\postgresql\pgpass.conf"))
    import psycopg2
    c = psycopg2.connect(host="wrds-pgdata.wharton.upenn.edu", port=9737,
                         dbname="wrds", user="murathan12",
                         sslmode="require", connect_timeout=15)
    c.set_session(readonly=True, autocommit=True)
    return c


def _universe() -> list[int]:
    """The SAME early screened universe the first pull used.

    Read from the PIT universe file rather than re-derived, so this re-pull
    cannot silently widen or narrow what the original covered — a re-pull that
    changes the population is a different dataset wearing the same filename.
    """
    early = pd.read_parquet(
        _config.OPTIMUS_LEDGER_DIR / "crsp_pit" / "crsp_pit_monthly_early.parquet",
        columns=["permno"])
    return sorted(int(p) for p in early["permno"].unique())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="re-pull even if every REQUIRED column is present")
    args = ap.parse_args()

    miss = missing_columns()
    have = existing_columns()
    print(f"{DATASET}: {len(have)} columns on disk, "
          f"{len(REQUIRED)} required, {len(miss)} missing")
    if miss:
        print(f"  missing: {', '.join(miss[:14])}"
              f"{' ...' if len(miss) > 14 else ''}")
    if not miss and not args.force:
        print("  nothing to do — every required column is present")
        return 0

    if args.dry_run:
        pn = _universe()
        print(f"  would pull {len(pn)} permnos, {START}..{END}, {len(REQUIRED)} columns, one query per year")
        return 0

    pn = _universe()
    print(f"  connecting; universe = {len(pn)} permnos")
    conn = _connect()

    # ONE QUERY PER YEAR, WRITTEN AS IT LANDS.
    #
    # MEASURED 2026-08-25: the single-query version ran 1h40m over 15,519
    # permnos x 23 years x ~100 columns, wrote NOTHING, and was killed. An
    # un-resumable query that produces no partial output has the same value as
    # no query at all, and the cost of finding that out is the whole 1h40m.
    #
    # `wrds_repull_dsf_early` already chunks by year for exactly this reason;
    # this is the same shape. Each year is a part file, so a kill costs one
    # year rather than all of them, and a re-run skips what already landed.
    #
    # AN EXPLICIT COLUMN LIST, NOT `SELECT *`.
    #
    # I first wrote this as `SELECT *`, reasoning that matching the modern
    # file exactly was the only way to guarantee the two eras have no seam.
    # That reasoning was wrong in its practical consequence, and the cost of
    # believing it was measured: `SELECT *` did not land a SINGLE YEAR in nine
    # minutes. `firm_ratio` carries 98 columns of which 13 are text, including
    # EIGHT industry description strings (`ffi5_desc` ... `ffi49_desc`) that
    # duplicate the compact numeric codes this pull actually needs.
    #
    # The seam it was guarding against cannot happen anyway:
    # `characteristics.available_characteristics()` takes the INTERSECTION of
    # the columns present in both era files, so a column that exists only in
    # the modern file is already excluded from every run. Narrowing here makes
    # the pull feasible and changes nothing about which characteristics a
    # 1993-2024 run may use.
    cols = ", ".join(REQUIRED)
    parts_dir = _path().parent / "_finratio_early_parts"
    parts_dir.mkdir(parents=True, exist_ok=True)
    sql = (f"SELECT {cols} FROM wrdsapps_finratio.firm_ratio "
           "WHERE permno = ANY(%(p)s) "
           "AND public_date BETWEEN %(s)s AND %(e)s")

    years = list(range(int(START[:4]), int(END[:4]) + 1))
    for yr in years:
        part = parts_dir / f"{yr}.parquet"
        if part.exists():
            print(f"  {yr}: already pulled, skipping")
            continue
        t0 = datetime.now(timezone.utc)
        chunk = pd.read_sql(sql, conn, params={
            "p": pn, "s": f"{yr}-01-01", "e": f"{yr}-12-31"})
        chunk.to_parquet(part, index=False)
        secs = (datetime.now(timezone.utc) - t0).total_seconds()
        print(f"  {yr}: {len(chunk):,} rows, {len(chunk.columns)} cols "
              f"({secs:.0f}s)")

    frames = [pd.read_parquet(parts_dir / f"{yr}.parquet") for yr in years
              if (parts_dir / f"{yr}.parquet").exists()]
    if not frames:
        print("  ! no year landed; nothing to write")
        return 2
    df = pd.concat(frames, ignore_index=True)
    print(f"  {len(df):,} rows, {len(df.columns)} columns across "
          f"{len(frames)} year(s)")

    still = [c for c in REQUIRED if c not in set(df.columns)]
    if still:
        # A pull that lands without the columns it was run FOR is a failure that
        # would otherwise look like a success, which is this repo's house shape.
        print(f"  ! REFUSING to write: {len(still)} required column(s) absent "
              f"from the result: {still}")
        return 2

    p = _path()
    backup = p.with_suffix(".parquet.5col_backup")
    if p.exists() and not backup.exists():
        p.replace(backup)
        print(f"  previous 5-column file preserved at {backup.name}")

    df.to_parquet(p, index=False)
    meta = {
        "dataset": DATASET,
        "pulled_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rows": int(len(df)),
        "cols": list(df.columns),
        "window": [START, END],
        "universe": "crsp_pit_monthly_early screened PERMNOs (unchanged from "
                    "the 2026-08-19 pull — a re-pull that changes the "
                    "population is a different dataset)",
        "pit_knowledge_column": "public_date",
        "sql_note": sql,
        "supersedes": {
            "reason": "the 2026-08-19 pull requested 5 columns, so the early "
                      "era could support only bm/roe and no quality composite, "
                      "industry neutralisation or size control was testable "
                      "before 2013",
            "previous_cols": ["gvkey", "permno", "public_date", "bm", "roe"],
            "resume_key": "COLUMNS, not file existence",
        },
    }
    p.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2),
                                           encoding="utf-8")
    print(f"  wrote {p.name} ({p.stat().st_size / 1e6:.0f} MB)")
    print("  NOTE: characteristics.AVAILABLE must be widened separately — "
          "this script pulls data, it does not register signals")
    return 0


if __name__ == "__main__":
    sys.exit(main())
