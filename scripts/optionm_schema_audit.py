"""Measure what the OptionMetrics vsurf_me dataset ACTUALLY is.

The Order-5 handoff inferred "not daily" from ~87 rows/secid-year. Row count
cannot identify sampling frequency when each (secid, date) carries many surface
coordinates. This measures the identity directly:

  unique observation dates / secid-year, rows / date, median+max date gap,
  surface coordinates / date, first/last date, coverage by security,
  and whether the timestamps are PIT-safe.

Writes a JSON receipt. Read-only against data/wrds_raw/optionm_vsurf_me/.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve()
DATA = Path(r"C:\Users\mrthn\Aegis module\data\wrds_raw\optionm_vsurf_me")
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("optionm_schema_audit.json")

# Sampled years rather than all 23: enough to establish frequency and detect a
# regime change in sampling, without reading 183 MB.
PROBE_YEARS = [2002, 2008, 2015, 2020, 2024]


def audit_year(path: Path) -> dict:
    df = pd.read_parquet(path)
    df["date"] = pd.to_datetime(df["date"])

    dates = np.sort(df["date"].unique())
    n_dates = len(dates)
    gaps = np.diff(dates).astype("timedelta64[D]").astype(int) if n_dates > 1 else np.array([])

    # dates per secid — the number that actually answers "is it daily?"
    per_secid_dates = df.groupby("secid")["date"].nunique()
    rows_per_date = df.groupby("date").size()

    # surface coordinates present on a representative date
    probe_date = dates[len(dates) // 2]
    day = df[df["date"] == probe_date]
    coords = day.groupby("secid").size()

    # is the grid rectangular? (days x delta x cp_flag)
    grid = (
        day["days"].nunique() * day["delta"].nunique() * day["cp_flag"].nunique()
    )

    return {
        "file": path.name,
        "rows": int(len(df)),
        "n_secids": int(df["secid"].nunique()),
        "n_unique_dates": int(n_dates),
        "first_date": str(pd.Timestamp(dates[0]).date()),
        "last_date": str(pd.Timestamp(dates[-1]).date()),
        "gap_days_median": float(np.median(gaps)) if gaps.size else None,
        "gap_days_max": int(gaps.max()) if gaps.size else None,
        "gap_days_min": int(gaps.min()) if gaps.size else None,
        "dates_per_secid_median": float(per_secid_dates.median()),
        "dates_per_secid_max": int(per_secid_dates.max()),
        "rows_per_date_median": float(rows_per_date.median()),
        "rows_per_secid_year_median": float(
            (df.groupby("secid").size()).median()
        ),
        "probe_date": str(pd.Timestamp(probe_date).date()),
        "coords_per_secid_on_probe_date_median": float(coords.median()),
        "coords_per_secid_on_probe_date_max": int(coords.max()),
        "distinct_days_to_expiry": sorted(
            float(x) for x in day["days"].dropna().unique()
        )[:20],
        "distinct_deltas": sorted(float(x) for x in day["delta"].dropna().unique())[:30],
        "distinct_cp_flags": sorted(str(x) for x in day["cp_flag"].dropna().unique()),
        "rectangular_grid_size": int(grid),
        "impl_vol_null_frac": float(df["impl_volatility"].isna().mean()),
        "impl_vol_median": float(df["impl_volatility"].median()),
        # PIT check: the surface for date d is computed from options quoted on
        # date d. A file whose max date exceeds the calendar year would signal
        # restatement/lookahead in the extraction.
        "max_date_exceeds_file_year": bool(
            pd.Timestamp(dates[-1]).year > int(path.stem.split("_")[-1])
        ),
    }


def main() -> int:
    if not DATA.is_dir():
        print(f"MISSING: {DATA}")
        return 2

    files = sorted(DATA.glob("vsurf_me_*.parquet"))
    print(f"{len(files)} files, {sum(f.stat().st_size for f in files)/1e6:.1f} MB")

    results = []
    for y in PROBE_YEARS:
        p = DATA / f"vsurf_me_{y}.parquet"
        if not p.exists():
            print(f"  skip {y} (absent)")
            continue
        print(f"  auditing {p.name} ...", flush=True)
        results.append(audit_year(p))

    payload = {
        "dataset": "OptionMetrics standardized volatility surface (vsurf_me)",
        "path": str(DATA),
        "n_files": len(files),
        "total_mb": round(sum(f.stat().st_size for f in files) / 1e6, 1),
        "years_present": [int(f.stem.split("_")[-1]) for f in files],
        "probe_years": results,
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print("\n=== VERDICT INPUTS ===")
    for r in results:
        print(
            f"{r['file']}: {r['n_unique_dates']:>4} unique dates | "
            f"gap med {r['gap_days_median']} max {r['gap_days_max']} | "
            f"dates/secid med {r['dates_per_secid_median']:>5} | "
            f"coords/secid/date med {r['coords_per_secid_on_probe_date_median']} | "
            f"secids {r['n_secids']}"
        )
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
