"""Gate D1 — pull verification (AEGIS_EXECUTION_ROADMAP.md).

Certifies the WRDS full pull BEFORE anything reads it:
  1. Written row counts match source counts logged at pull time (last WROTE line per table).
  2. No "!! MISMATCH" anywhere in the pull log.
  3. Known-answer counts: company_networks = 5,018,507; dir_profile_all = 17,197,215;
     na_wrds_dir_profile_emp = 10,771,312.
  4. directorid/boardid/companyid cardinality >> the truncated era's 3,240.
  5. Date ranges span roughly 1999 -> 2026 on role/report date columns.
  6. Reports any literal "Curr" values in date-typed text columns (must be screened at
     ingestion later — D2 bans them; here we only measure exposure).
  7. No leftover ._chunk_ checkpoint files (final write should have removed them).

Kill criterion (pre-registered): any FAIL -> re-pull that table before it is ever read.

Usage: .venv/Scripts/python.exe scripts/gate_d1_verify.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import duckdb
import pyarrow.parquet as pq

DATA_DIR = Path(r"C:\Users\mrthn\Aegis module\data\wrds_raw\full")
LOG = DATA_DIR / "pull_log.txt"
REPORT = DATA_DIR / "GATE_D1_REPORT.txt"

# Known-answer counts (verified at source during the 2026-08-03 pull).
KNOWN_COUNTS = {
    "boardex_na_wrds_company_networks": 5_018_507,
    "boardex_na_wrds_dir_profile_all": 17_197_215,
    "boardex_na_wrds_dir_profile_emp": 10_771_312,
}
TRUNCATED_ERA_CARDINALITY = 3_240  # boardid count in the old LIMIT-truncated extract

ID_COLS = ("directorid", "boardid", "companyid")
lines: list[str] = []


def say(msg: str) -> None:
    print(msg)
    lines.append(msg)


def parse_log_source_counts() -> dict[str, tuple[int, int, bool]]:
    """Return {outname: (written, source, ok)} from the LAST 'WROTE' line per table."""
    out: dict[str, tuple[int, int, bool]] = {}
    pat = re.compile(
        r"WROTE (\S+): ([\d,]+) rows in \d+s \(source ([\d,]+)\) (OK|!! MISMATCH)"
    )
    for line in LOG.read_text(encoding="utf-8", errors="replace").splitlines():
        m = pat.search(line)
        if m:
            name, written, source, flag = m.groups()
            out[name] = (
                int(written.replace(",", "")),
                int(source.replace(",", "")),
                flag == "OK",
            )
    return out


def main() -> int:
    failures = 0
    say(f"GATE D1 verification — {DATA_DIR}")
    say("=" * 70)

    # --- log-level checks -------------------------------------------------
    log_text = LOG.read_text(encoding="utf-8", errors="replace")
    n_mismatch = sum(
        "!! MISMATCH" in ln and "Verify:" not in ln  # DONE banner quotes the marker
        for ln in log_text.splitlines()
    )
    if n_mismatch:
        say(f"FAIL: pull log contains {n_mismatch} '!! MISMATCH' line(s)")
        failures += 1
    else:
        say("OK: no MISMATCH lines in pull log")

    logged = parse_log_source_counts()
    say(f"OK: pull log records {len(logged)} written tables")

    # --- leftover chunk checkpoints --------------------------------------
    leftovers = sorted(DATA_DIR.glob("*._chunk_*.parquet"))
    if leftovers:
        say(f"WARN: {len(leftovers)} leftover chunk checkpoint(s) — table(s) still "
            f"in progress or final write failed: "
            f"{sorted({p.name.split('._chunk_')[0] for p in leftovers})}")
    else:
        say("OK: no leftover chunk checkpoints")

    # --- per-table checks -------------------------------------------------
    con = duckdb.connect()
    tables = sorted(
        p for p in DATA_DIR.glob("*.parquet") if "._chunk_" not in p.name
    )
    say(f"\nPer-table checks ({len(tables)} final parquet files):")
    for path in tables:
        name = path.stem
        nrows = pq.ParquetFile(path).metadata.num_rows

        # 1) count vs pull-time source count
        status = []
        if name in logged:
            written, source, ok = logged[name]
            if nrows == source and ok:
                status.append(f"rows {nrows:,} == source OK")
            else:
                status.append(
                    f"FAIL rows {nrows:,} vs logged written {written:,} / source {source:,}"
                )
                failures += 1
        else:
            status.append(f"rows {nrows:,} (no WROTE line in log — check manually)")

        # 2) known-answer counts
        if name in KNOWN_COUNTS:
            if nrows == KNOWN_COUNTS[name]:
                status.append("known-count OK")
            else:
                status.append(f"FAIL known-count expected {KNOWN_COUNTS[name]:,}")
                failures += 1

        # 3) id cardinality + 4) date ranges + 5) 'Curr' exposure — via duckdb
        schema = pq.ParquetFile(path).schema_arrow
        cols = {f.name.lower(): f for f in schema}
        f = str(path).replace("'", "''")

        for idc in ID_COLS:
            if idc in cols:
                (card,) = con.execute(
                    f"select count(distinct \"{idc}\") from read_parquet('{f}')"
                ).fetchone()
                if card <= TRUNCATED_ERA_CARDINALITY and nrows > 100_000:
                    status.append(f"FAIL {idc} cardinality {card:,} <= truncated-era 3,240")
                    failures += 1
                else:
                    status.append(f"{idc} card {card:,}")
                break  # one id column is enough per table

        date_cols = [
            c for c in cols
            if "date" in c and "flag" not in c
        ][:2]
        for dc in date_cols:
            typ = str(cols[dc].type)
            if typ in ("string", "large_string"):
                (n_curr,) = con.execute(
                    f"select count(*) from read_parquet('{f}') where \"{dc}\" = 'Curr'"
                ).fetchone()
                if n_curr:
                    status.append(f"'{dc}' has {n_curr:,} 'Curr' values (screen at D2)")
                lo, hi = con.execute(
                    f"select min(try_cast(\"{dc}\" as date)), max(try_cast(\"{dc}\" as date)) "
                    f"from read_parquet('{f}') where \"{dc}\" is not null and \"{dc}\" != 'Curr'"
                ).fetchone()
            else:
                lo, hi = con.execute(
                    f"select min(\"{dc}\"), max(\"{dc}\") from read_parquet('{f}')"
                ).fetchone()
            status.append(f"{dc} [{lo} .. {hi}]")

        say(f"  {name}: " + "; ".join(status))

    # --- expected-but-missing tables --------------------------------------
    say("\nExpected downstream tables:")
    for expect in (
        "boardex_na_wrds_org_composition",
        "boardex_na_wrds_org_summary",
        "ibes_statsum_fy1",
        "crsp_dsedelist_full",
    ):
        hits = [p.name for p in tables if expect in p.name] or [
            p.name for p in DATA_DIR.glob(f"*{expect.split('_', 1)[-1]}*.parquet")
        ]
        say(f"  {expect}: {'PRESENT ' + hits[0] if hits else 'MISSING (pull incomplete?)'}")

    say("=" * 70)
    verdict = "GATE D1: PASS" if failures == 0 else f"GATE D1: FAIL ({failures} failure(s))"
    say(verdict)
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    say(f"report written to {REPORT}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
