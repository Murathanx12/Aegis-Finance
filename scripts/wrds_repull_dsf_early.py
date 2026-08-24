"""Re-pull `crsp.dsf` 1990-2012 with the columns the farm actually needs.

    python -m scripts.wrds_repull_dsf_early --dry-run
    python -m scripts.wrds_repull_dsf_early
    python -m scripts.wrds_repull_dsf_early --years 1990 1995

WHY THIS SCRIPT EXISTS AND `wrds_pull_catchup` CANNOT DO IT
===========================================================
Every WRDS puller in this repo skips "a table whose parquet exists". That is
the right rule for a pull that either happened or did not, and the WRONG rule
for a pull that happened with a NARROWER COLUMN LIST than a later consumer
needs. `crsp_dsf_1990..2012` exist, therefore they are skipped, therefore they
can never gain `openprc`/`retx`/`shrout` no matter how many catch-up nights run.

The gap is structurally invisible to an existence-keyed queue. This is the
sibling of a failure already in the ledger — *"a failure-driven queue cannot
see a NEVER-ATTEMPTED item"* (2026-08-23) — one level in: **an existence-keyed
queue cannot see a PARTIALLY-PULLED item.**

So this script keys its resume rule on **COLUMNS**, not on existence. A year is
skipped only when its parquet already carries every column `REQUIRED` names.
That rule is the actual fix; the pull is just what follows from it.

WHY IT IS WORTH A CREDENTIALED SESSION
======================================
`power_check` on the leading farm candidate, measured 2026-08-24:

    tracking error  35.7%/yr    implied t          1.54
    observed excess 16.6%/yr    MDE at 80% power  30.3%/yr
    years available   10.9      YEARS NEEDED        36

Twelve years cannot resolve a 16.6%/yr effect at a 35.7% tracking error — not
for momentum, and not for any of the mechanisms queued behind it, because the
arithmetic is a fact about the SAMPLE and not about the strategy. The 3.75x
rebalance-phase spread, the 1.01x-vs-1.75x sub-period disagreement, the
bootstrap CI containing zero and the reality-check p of 0.126 are four faces of
that one variance.

This pull is therefore not "more data would be nice". It is very close to the
precise amount of history the question needs, and until it exists every further
mechanism tested on 2013-2024 arrives pre-doomed to the same t ~ 1.5.

WHAT THE EXTRA COLUMNS BUY, ONE BY ONE
======================================
  * `openprc` IS the next-open fill convention. Without it the only executable
    convention is close-to-close, which books the overnight gap that FOLLOWS
    the signal — a systematic gift to exactly the strategies being searched
    for. This single column is why `panel.py` refuses these years by name;
  * `retx` is the only way to separate a dividend from a price move;
  * `shrout` is market cap, so cap-weighting and every size signal;
  * `askhi`/`bidlo`/`cfacpr`/`cfacshr` come free in the same scan and match
    what 2013-2024 already carries — a panel whose two halves have different
    columns is a panel with a seam in it.

WHAT THIS PULL DOES **NOT** FIX, AND IT MATTERS
===============================================
The early universe is screened by the same NOMINAL cuts as the modern one
($5 price, $100M dollar volume per month), and a nominal bar in 1990 is a much
stricter real bar. Measured on `crsp_pit_monthly_early`:

    eligible names per month   min 243   median 1,332   max 2,149
    months with < 500 eligible    32 of 276, ALL of them 1990-01 .. 1992-10

The farm's default universe is the top 500 by trailing dollar volume. In those
32 months the cut IS the boundary — the universe is not a selection from a
wider set, it is whatever survived the screen — and `portfolio_farm_universe_audit`
refuses to clear exactly that condition. **So 1990-1992 is pulled but must not
be replayed at `universe_n=500`.** From 1993 the membership clears the cut in
every month, which is 32 clean years against the 36 the effect needs.

Delisting is NOT a second gap: `crsp__dsedelist.parquet` already spans
1990-01-31 .. 2024-12-31 (18,691 events, 5,821 of them in the 1990s), so the
early era resolves its exits from MEASURED returns exactly as the modern era
does.

PATCHING THIS FILE DOES NOT CHANGE A RUN ALREADY IN FLIGHT
==========================================================
Obvious, and it still cost something on 2026-08-25. The backup destination was
changed from a sibling file to `superseded/` at 00:44, while the pull was on
its fifth year — and the running interpreter kept the module it had already
imported, so the remaining nineteen years wrote their backups beside the real
files anyway. `wrds_column_completeness` then reported "54 files, 19 PARTIAL",
which is true and is about the backups, not the pull.

If a fix to this script matters for the run in progress, the run has to be
restarted. It is resumable and safe to kill, which is why that is cheap.

SAFETY
======
The narrow file is MOVED to `<name>.narrow-5col.parquet`, never deleted, and
only after the replacement has been written and read back. Killing this script
at any point leaves either the old file or a verified new one.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config                          # noqa: E402
from scripts.wrds_training_pull import _conn, _date_ranges     # noqa: E402

OUT = _config.OPTIMUS_LEDGER_DIR / "wrds"
SUPERSEDED = OUT / "superseded"
EARLY_UNIVERSE_PATH = (_config.OPTIMUS_LEDGER_DIR / "crsp_pit" /
                       "crsp_pit_monthly_early.parquet")

#: Byte-identical to what `pull_dsf` requests for 2013-2024. Written out rather
#: than imported because the point of this script is that the two halves of the
#: panel must agree, and a shared constant that later drifts would hide it.
COLUMNS = ["permno", "date", "prc", "ret", "retx", "vol", "shrout",
           "askhi", "bidlo", "openprc", "cfacpr", "cfacshr"]

#: The resume key. A year is done when it has these; existence is not enough,
#: and that distinction is the whole reason this file exists.
REQUIRED = set(COLUMNS)

YEARS = range(1990, 2013)

#: Below this, a year is replayable only at a smaller `universe_n`. Measured on
#: the early PIT screen: 1990-01 .. 1992-10 fall short, 1993 onward do not.
FIRST_FULL_UNIVERSE_YEAR = 1993


def existing_columns(path: Path) -> set[str]:
    try:
        import pyarrow.parquet as pq
        return set(pq.ParquetFile(path).schema_arrow.names)
    except Exception:                                          # noqa: BLE001
        return set()


def needs_pull(year: int) -> tuple[bool, str]:
    p = OUT / f"crsp_dsf_{year}.parquet"
    if not p.exists():
        return True, "absent"
    have = existing_columns(p)
    missing = sorted(REQUIRED - have)
    if missing:
        return True, f"PARTIAL, missing {missing}"
    return False, "complete"


def early_permnos() -> list[int]:
    u = pd.read_parquet(EARLY_UNIVERSE_PATH, columns=["permno"])
    return sorted(int(x) for x in u["permno"].unique())


def pull_year(conn, year: int, permnos: list[int]) -> dict:
    sql = (f"SELECT {', '.join(COLUMNS)} "
           "FROM crsp.dsf WHERE permno = ANY(%(p)s) "
           "AND date BETWEEN %(s)s AND %(e)s")
    t0 = time.time()
    df = pd.read_sql(sql, conn, params={"p": permnos, "s": f"{year}-01-01",
                                        "e": f"{year}-12-31"})
    secs = time.time() - t0

    final = OUT / f"crsp_dsf_{year}.parquet"
    tmp = OUT / f"crsp_dsf_{year}.repull-tmp.parquet"
    df.to_parquet(tmp, index=False)

    # read back BEFORE displacing anything on disk — a parquet that wrote
    # without raising can still be unreadable, and the old file is the only
    # copy of these years that exists locally.
    back = existing_columns(tmp)
    if not REQUIRED <= back:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"{year}: readback missing {sorted(REQUIRED-back)}")

    if final.exists():
        # A SUBDIRECTORY, not a sibling. `panel.available_years` and
        # `wrds_column_completeness` both glob `crsp_dsf_*.parquet` in this
        # directory, so a superseded copy left beside the real file is counted
        # as a 24th partial year forever — the audit reported exactly that
        # before this moved.
        SUPERSEDED.mkdir(parents=True, exist_ok=True)
        keep = SUPERSEDED / f"crsp_dsf_{year}.narrow-5col.parquet"
        keep.unlink(missing_ok=True)
        final.rename(keep)
    tmp.rename(final)

    ranges = _date_ranges(df)
    meta = {
        "dataset": f"crsp_dsf_{year}",
        "pulled_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rows": int(len(df)), "cols": list(df.columns),
        "window": ranges.get("date"), "window_source": "date",
        "date_ranges_observed": ranges,
        "universe": ("crsp_pit_monthly_early ALL screened PERMNOs — the "
                     "early-era universe file, NOT crsp_pit_monthly_v1"),
        "pit_knowledge_column": ("date (daily bar, public at close); |prc| "
                                 "convention: negative = bid/ask midpoint on "
                                 "no-trade days; vol in SHARES on dsf"),
        "sql_note": sql,
        "repull_reason": ("the original 1990-2012 pull requested 5 columns; "
                          "openprc/retx/shrout are what portfolio_farm.panel "
                          "requires, and an existence-keyed catch-up queue "
                          "could never have noticed they were absent"),
        "supersedes": f"superseded/crsp_dsf_{year}.narrow-5col.parquet",
        "universe_caveat": (
            "1990-01..1992-10 carry fewer than 500 eligible names per month "
            "(min 243); at universe_n=500 the farm's cut IS the screen "
            "boundary there. Replay these years only at a smaller universe, "
            f"or start at {FIRST_FULL_UNIVERSE_YEAR}."
            if year < FIRST_FULL_UNIVERSE_YEAR else
            "membership clears universe_n=500 in every month of this year"),
        "pull_seconds": round(secs, 1),
    }
    (OUT / f"crsp_dsf_{year}.meta.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8")
    return {"year": year, "rows": len(df), "seconds": round(secs, 1),
            "mb": round(final.stat().st_size / 1e6, 1)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--years", type=int, nargs=2, metavar=("FIRST", "LAST"))
    a = ap.parse_args(argv)

    years = (range(a.years[0], a.years[1] + 1) if a.years else YEARS)
    plan = [(y, why) for y in years for need, why in [needs_pull(y)] if need]
    done = [y for y in years if not needs_pull(y)[0]]

    print("CRSP dsf RE-PULL - resume key is COLUMNS, not existence")
    print(f"  required : {', '.join(COLUMNS)}")
    print(f"  complete : {len(done)} year(s) {done[:3]}{'...' if len(done)>3 else ''}")
    print(f"  to pull  : {len(plan)} year(s)")
    for y, why in plan[:5]:
        print(f"     {y}: {why}")
    if len(plan) > 5:
        print(f"     ... and {len(plan)-5} more")
    if a.dry_run or not plan:
        return 0

    pn = early_permnos()
    print(f"  universe : {len(pn):,} permnos from {EARLY_UNIVERSE_PATH.name}\n")
    conn = _conn()
    rows = []
    try:
        for y, why in plan:
            try:
                r = pull_year(conn, y, pn)
            except Exception as exc:                           # noqa: BLE001
                print(f"  {y}: FAILED {type(exc).__name__}: {exc}")
                conn = _conn()          # a dropped link is not a missing year
                continue
            rows.append(r)
            print(f"  {y}: {r['rows']:>10,} rows  {r['mb']:>6.1f} MB  "
                  f"{r['seconds']:>6.1f}s")
    finally:
        try:
            conn.close()
        except Exception:                                      # noqa: BLE001
            pass

    still = [y for y, _ in plan if needs_pull(y)[0]]
    print(f"\n  pulled {len(rows)} of {len(plan)}; "
          f"{len(still)} still incomplete: {still}")
    return 1 if still else 0


if __name__ == "__main__":
    raise SystemExit(main())
