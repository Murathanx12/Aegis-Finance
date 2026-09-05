"""THE LONG PANEL -- the same point-in-time table, 1999-2024 instead of 2013-2024.

WHY THIS FILE EXISTS, AND WHY IT IS NOT A NEW PANEL
===================================================
The night lab of 2026-09-05 produced the one number that decides the weekend:
the best learner cell on 2013-2024 is +14.4%/yr ahead of the market and is
NOISE by every honest test -- DSR 0.197 against a 0.2305 noise bar, SPA p 0.29,
PBO 0.29 -- and at that Sharpe **t = 2 needs 16.1 years of out-of-sample months
against the 7.0 the panel has.**

That is a STATISTICAL ceiling, not a modelling one. No amount of extra training,
width, or cleverness moves it, because the quantity that is short is not
capacity, it is INDEPENDENT MONTHS. So the largest lever available this weekend
is not a better model. It is a longer tape, and the tape is already on disk:

* `ibes__ptgsumu` (the UNADJUSTED consensus -- the numerator the share-basis fix
  of 2026-09-04 made mandatory) starts **1999-03-18**, with 22,377 US PTG rows
  in the stub of 1999 and 40,000-56,000 in every full year after it. IBES
  coverage pre-2004 is thinner than today but it is NOT sparse, and the receipt
  prints the per-year count rather than asserting a characterisation.
* `crsp_dsf_*.parquet` is on disk from **1990**, so the one-year lookback every
  price feature needs (`ret_12m`, `mom_12_1`, `split_prior_year`) is available
  for a panel that starts in 1999 -- 1998 is read and never scored.

1999-2024 is ~26 calendar years. After a five-year walk-forward warm-up that is
**~19 out-of-sample years against 7**, which is the difference between a
question that cannot be answered and one that can.

WHAT IS DELIBERATELY IDENTICAL
==============================
Everything. `build_long` calls `dataset.build(start, end)` -- the SAME loaders,
the SAME share-basis rule (unadjusted target over raw close), the SAME hygiene,
the SAME delisting treatment with the Shumway fill, the SAME value-weighted
market leg from `learner.benchmark`. A second implementation of the panel would
be a second panel, and the whole point of the exercise is that the 26-year and
the 12-year results are comparable line for line.

What this module ADDS is three things the long window makes necessary:

1. **COVERAGE BY YEAR, printed, not characterised.** A panel whose early years
   are thin is not the same instrument as its late years, and "IBES coverage is
   thinner pre-2004" is a sentence, not a number. The receipt carries
   name-months, distinct permnos, and the hygiene-pass rate for EVERY year, so
   any later claim about an era can be checked against how much tape that era
   actually had.

2. **THE ERA LABEL.** 1999-2007 / 2008-2015 / 2016-2024, as a column. The
   weekend's verdict rule requires the sign to hold in >= 2 of 3 eras, and an
   era boundary that each job re-derives is an era boundary each job can get
   subtly different. One definition, here.

3. **A SECOND SHARE-BASIS GATE, IN THE 1999 ERA.** The AAPL 2013-06 case pins
   the fix on the window that discovered it; it says nothing about 2000. The
   split-era gate is DERIVED, not hardcoded to a ticker: it finds names whose
   share basis moved inside the early window, and asserts the PIT ratio
   `mean_target / close` stays inside a sane band for them at the same rate as
   for everyone else. A fixture that names a permno and a date would rot; a
   fixture that names a PROPERTY does not (CLAUDE.md, session protocol #5).

WHAT THIS MODULE DOES NOT DO
============================
It does not overwrite `train_table.parquet`. The 12-year panel is the incumbent
and every published number was measured on it; the long panel earns its place by
being compared to it, not by replacing it silently. `learner-train-table-3` is a
WINDOW extension of `learner-train-table-2`, not a schema change: the columns
are the same columns, which is exactly what makes the comparison legal.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from learner import dataset as DS
from learner import prior as P

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = DS.OUT_DIR
LONG_TABLE = OUT_DIR / "train_table_long.parquet"
LONG_RECEIPT = OUT_DIR / "train_table_long_schema.json"

#: A WINDOW extension of `learner-train-table-2`, not a new schema. The columns
#: are identical; only the window and the `era` column differ.
SCHEMA_VERSION = "learner-train-table-3"

LONG_START = 1999
LONG_END = 2024

#: The three eras the weekend's verdict rule counts signs in. Inclusive years.
#: They are not equal in length and they are not meant to be: the boundaries are
#: the GFC and the post-2015 regime, which is where a strategy's world changes,
#: not where the row count divides evenly.
ERAS: tuple[tuple[str, int, int], ...] = (
    ("1999-2007", 1999, 2007),
    ("2008-2015", 2008, 2015),
    ("2016-2024", 2016, 2024),
)

#: The walk-forward warm-up. Five years of matured targets before the first test
#: year, so the earliest scored year is 2004 and the out-of-sample window runs
#: 2004-2024 -- 21 years, against the 7 the 12-year panel could offer.
WARMUP_YEARS = 5
FIRST_TEST_YEAR = LONG_START + WARMUP_YEARS


def era_of(year) -> str:
    y = int(year)
    for name, lo, hi in ERAS:
        if lo <= y <= hi:
            return name
    return "out_of_eras"


def add_era(df: pd.DataFrame) -> pd.DataFrame:
    """The era column, from `entry_date` -- the date the money moved, not the
    vintage. A row whose consensus is dated 2007-12 but which trades on
    2008-01-02 belongs to the era it was EXPOSED in."""
    df = df.copy()
    df["era"] = pd.to_datetime(df["entry_date"]).dt.year.map(era_of).astype("category")
    return df


# ------------------------------------------------------------ coverage receipt

def coverage_by_year(df: pd.DataFrame) -> list[dict]:
    """One row per calendar year: how much tape that year actually had.

    Printed rather than characterised. The sentence "IBES coverage is thinner
    pre-2004" is true and useless; `name_months` and `hygiene_pass_rate` per
    year are what a later claim about an era has to be checked against.
    """
    d = df.copy()
    d["_y"] = pd.to_datetime(d["entry_date"]).dt.year
    rows = []
    for y, g in d.groupby("_y", sort=True):
        rows.append({
            "year": int(y),
            "era": era_of(y),
            "name_months": int(len(g)),
            "permnos": int(g["permno"].nunique()),
            "months": int(g["month"].nunique()),
            "hygiene_ok": int(g["hygiene_ok"].sum()) if "hygiene_ok" in g else None,
            "hygiene_pass_rate": (round(float(g["hygiene_ok"].mean()), 4)
                                  if "hygiene_ok" in g else None),
            "median_coverage": (float(g["coverage"].median())
                                if "coverage" in g and g["coverage"].notna().any() else None),
            "median_close": (round(float(g["close"].median()), 2)
                             if "close" in g else None),
            "matured_1m": int(g["excess_vw_1m"].notna().sum()) if "excess_vw_1m" in g else None,
            "matured_12m": int(g["excess_vw_12m"].notna().sum()) if "excess_vw_12m" in g else None,
        })
    return rows


# --------------------------------------------------------- the share-basis gate

def pit_ratio(df: pd.DataFrame) -> pd.Series:
    """The RAW point-in-time ratio `mean_target / close`, hygiene or no hygiene.

    THE COLUMN THE FIRST VERSION OF THIS GATE ASKED FOR DID NOT EXIST, BY
    CONSTRUCTION. `dataset.hygiene` defines
    `target_readable = ... & ~split_prior_year`, and `build` then NULLS `ratio`
    wherever `hygiene_ok` is False. So every row whose share basis moved in the
    prior year -- which is *exactly* the population a share-basis gate has to
    look at -- carries `ratio = NaN` on purpose. A gate written against `ratio`
    could only ever see zero rows, produce `nan`, and fail: a permanent red line
    that says nothing about the data (CLAUDE.md: a gate that cannot go green is
    a BROKEN gate, not a strict one).

    `ratio_unhygienic` is the raw ratio kept for audit on precisely those rows.
    Coalescing the two gives the ratio a desk actually saw, for every row, which
    is what an audit of the share basis needs and what a FEATURE must never be.
    """
    r = df["ratio"] if "ratio" in df.columns else pd.Series(np.nan, index=df.index)
    if "ratio_unhygienic" in df.columns:
        r = r.where(r.notna(), df["ratio_unhygienic"])
    return pd.to_numeric(r, errors="coerce")


def split_era_share_basis_gate(df: pd.DataFrame, era_end: int = 2004,
                               band: tuple[float, float] = (0.3, 4.0),
                               min_names: int = 20) -> dict:
    """DOES THE UNADJUSTED-TARGET-OVER-RAW-CLOSE RULE HOLD IN THE 1999 ERA?

    The AAPL 2013-06 case (in `dataset.build`'s receipt) pins the share-basis fix
    on the window that discovered it. This gate asks the same question of the
    window the fix was never tested on, and it asks it of a PROPERTY rather than
    of a named ticker so it cannot rot:

      take every row in the early window whose own panel flag says the share
      basis moved in the prior year (`split_prior_year`), and check that the raw
      PIT ratio `mean_target / close` sits inside a sane band at the SAME RATE as
      MATCHED rows that had no share-basis change.

    If the numerator were split-ADJUSTED and the denominator raw (the bug of
    2026-09-04), a 2:1 split would move the ratio by a factor of two across the
    boundary and the split names would fall out of the band far more often than
    everybody else. They should not, because `load_ibes_ext` reads
    `ibes__ptgsumu`.

    THE CONTROL IS MATCHED, NOT "EVERYONE ELSE". Split-flagged rows are, by
    construction, hygiene failures; comparing them to the whole rest of the era
    would compare "share basis moved" against "passed every admission rule",
    and the gap would be about the $2 floor and the coverage floor, not about
    the share basis. So both sides here are restricted to rows that clear
    `has_opinion` and carry a readable positive ratio -- and the ONLY remaining
    difference between treatment and control is the split flag itself.

    REFUSES to call itself a test if either side is empty or the case count is
    too small: a check that did not run is not a check that passed.
    """
    d = df[pd.to_datetime(df["entry_date"]).dt.year <= era_end].copy()
    if "split_prior_year" not in d.columns:
        return {"verdict": "CANNOT DETERMINE",
                "why": "split_prior_year absent from the panel"}
    d["_split"] = d["split_prior_year"].fillna(False).astype(bool)
    d["_r"] = pit_ratio(d)
    # The match: everything hygiene asks for EXCEPT the split flag itself.
    opin = (d["has_opinion"].fillna(False).astype(bool) if "has_opinion" in d.columns
            else pd.Series(True, index=d.index))
    eligible = opin & d["_r"].notna() & (d["_r"] > 0) & (d["_r"] < DS.RATIO_UNREADABLE_AT)
    sub = d[eligible & d["_split"]]
    other = d[eligible & ~d["_split"]]
    names = sorted(sub["permno"].unique().tolist())
    if len(names) < min_names or not len(other):
        return {"verdict": "CANNOT DETERMINE",
                "matched_permnos_with_a_share_basis_change": len(names),
                "matched_control_rows": int(len(other)),
                "min_names": min_names,
                "why": (f"only {len(names)} permnos clear the match AND carry a share-basis "
                        f"change on or before {era_end} (control rows {len(other):,}); "
                        f"below the {min_names} this gate needs to be a test rather than "
                        "an anecdote")}
    lo, hi = band
    rate_split = float(sub["_r"].between(lo, hi).mean())
    rate_other = float(other["_r"].between(lo, hi).mean())
    gap = rate_other - rate_split
    out = {
        "window": f"{int(pd.to_datetime(d['entry_date']).dt.year.min())}-{era_end}",
        "band": list(band),
        "ratio_source": "ratio, coalesced with ratio_unhygienic (raw PIT ratio, audit column)",
        "match": ("has_opinion and 0 < raw ratio < RATIO_UNREADABLE_AT on BOTH sides; "
                  "the split flag is the only difference"),
        "permnos_with_a_share_basis_change": len(names),
        "rows_around_a_change": int(len(sub)),
        "ratio_in_band_rate_split_names": round(rate_split, 4),
        "rows_without_a_change": int(len(other)),
        "ratio_in_band_rate_other_names": round(rate_other, 4),
        "gap": round(float(gap), 4),
        "median_ratio_split_names": round(float(sub["_r"].median()), 4),
        "median_ratio_other_names": round(float(other["_r"].median()), 4),
        "what_would_fail": ("a split-adjusted numerator over a raw denominator would push "
                            "the post-change rows out of the band by roughly the split "
                            "factor, so the split-name in-band rate would collapse "
                            "relative to the matched control"),
    }
    # A 10-point gap is the alarm. A split-adjusted numerator would open a gap of
    # tens of points, not one point; this is a loose bar on purpose, because the
    # thing it is looking for is enormous when it is present.
    out["verdict"] = "PASS" if gap < 0.10 else "FAIL"
    return out


def hand_checked_split_rows(df: pd.DataFrame, era_end: int = 2004,
                            n: int = 5) -> list[dict]:
    """The receipt's worked examples: n real (permno, month) pairs straddling a
    share-basis change in the early era, with the numbers a human can check by
    hand. A rate is a summary; these are the rows the summary is made of."""
    d = df[pd.to_datetime(df["entry_date"]).dt.year <= era_end].copy()
    d["_r"] = pit_ratio(d)
    flagged = d[d["split_prior_year"].fillna(False).astype(bool)
                & d["_r"].notna() & (d["_r"] > 0)]
    if not len(flagged):
        return []
    take = flagged.sort_values(["permno", "vintage"]).drop_duplicates("permno").head(n)
    rows = []
    for _, r in take.iterrows():
        def _f(col):
            v = r.get(col, np.nan)
            return round(float(v), 4) if pd.notna(v) else None
        rows.append({
            "permno": int(r["permno"]),
            "vintage": str(pd.to_datetime(r["vintage"]).date()),
            "entry_date": str(pd.to_datetime(r["entry_date"]).date()),
            "mean_target_unadjusted": _f("mean_target"),
            "close_raw": _f("close"),
            "cfacpr_at_t": _f("cfacpr"),
            "raw_pit_ratio": round(float(r["_r"]), 4),
            "ratio_after_hygiene": _f("ratio"),
            "ratio_adj_check": _f("ratio_adj_check"),
            "check_agrees": bool(r.get("ratio_check_agrees", False)),
        })
    return rows


# ------------------------------------------------------------------ build/save

def build_long(start: int = LONG_START, end: int = LONG_END,
               verbose: bool = True) -> tuple[pd.DataFrame, dict]:
    """The long panel. Same build, longer window, three extra receipt sections."""
    log = (lambda *a: print(*a, flush=True)) if verbose else (lambda *a: None)
    log(f"BUILD LONG PANEL {start}-{end} (schema {SCHEMA_VERSION})")
    t0 = datetime.now(timezone.utc)
    df, receipt = DS.build(start=start, end=end, verbose=verbose)
    df = add_era(df)

    receipt["schema_version"] = SCHEMA_VERSION
    receipt["window_of_the_incumbent"] = "2013-2024 (learner-train-table-2, still on disk)"
    receipt["eras"] = [{"era": n, "from": lo, "to": hi} for n, lo, hi in ERAS]
    receipt["warmup_years"] = WARMUP_YEARS
    receipt["first_test_year"] = FIRST_TEST_YEAR
    receipt["coverage_by_year"] = coverage_by_year(df)
    receipt["share_basis_gate_early_era"] = split_era_share_basis_gate(df)
    receipt["share_basis_hand_rows_early_era"] = hand_checked_split_rows(df)
    receipt["build_seconds"] = round((datetime.now(timezone.utc) - t0).total_seconds(), 1)

    by_era = []
    for name, lo, hi in ERAS:
        g = df[df["era"] == name]
        by_era.append({"era": name, "name_months": int(len(g)),
                       "months": int(g["month"].nunique()) if len(g) else 0,
                       "permnos": int(g["permno"].nunique()) if len(g) else 0})
    receipt["by_era"] = by_era

    log("  eras: " + "; ".join(f"{e['era']} {e['name_months']:,} rows / {e['months']} months"
                               for e in by_era))
    g = receipt["share_basis_gate_early_era"]
    log(f"  early-era share-basis gate: {g.get('verdict')} "
        f"(split names in band {g.get('ratio_in_band_rate_split_names')} vs "
        f"others {g.get('ratio_in_band_rate_other_names')})")
    return df, receipt


def save_long(df: pd.DataFrame, receipt: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(LONG_TABLE, index=False)
    payload = {"build": receipt,
               "schema": DS.feature_schema(),
               "schema_shadow": DS.feature_schema(shadow_only=True),
               "prior": P.describe(),
               "table": str(LONG_TABLE),
               "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    LONG_RECEIPT.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def regate() -> dict:
    """Recompute the receipt's DERIVED sections from the table already on disk.

    The gate sections are functions of the panel, not of the build, so a gate
    that was wrong does not cost a rebuild -- and a rebuild would be the WORSE
    option, because re-running the pipeline to fix a receipt makes it impossible
    to tell whether the numbers moved because the gate changed or because the
    build did. Only `coverage_by_year`, the share-basis sections and `by_era`
    are recomputed; everything the build itself measured is left untouched, and
    the receipt records that a regate happened and when.
    """
    if not LONG_RECEIPT.exists() or not LONG_TABLE.exists():
        raise SystemExit("REFUSED: no long panel + receipt on disk to re-gate.")
    payload = json.loads(LONG_RECEIPT.read_text(encoding="utf-8"))
    df = load_long()
    r = payload["build"]
    r["coverage_by_year"] = coverage_by_year(df)
    r["share_basis_gate_early_era"] = split_era_share_basis_gate(df)
    r["share_basis_hand_rows_early_era"] = hand_checked_split_rows(df)
    r["by_era"] = [{"era": n,
                    "name_months": int((df["era"] == n).sum()),
                    "months": int(df.loc[df["era"] == n, "month"].nunique()),
                    "permnos": int(df.loc[df["era"] == n, "permno"].nunique())}
                   for n, _lo, _hi in ERAS]
    r.setdefault("regated", []).append({
        "utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sections": ["coverage_by_year", "share_basis_gate_early_era",
                     "share_basis_hand_rows_early_era", "by_era"],
        "why": ("the first early-era gate read `ratio`, which `hygiene` NULLS on exactly "
                "the split-flagged rows the gate exists to inspect, so it could only ever "
                "return nan and FAIL"),
    })
    LONG_RECEIPT.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return r["share_basis_gate_early_era"]


def load_long() -> pd.DataFrame:
    if not LONG_TABLE.exists():
        raise SystemExit(
            f"REFUSED: {LONG_TABLE} does not exist. Build it first: "
            "python -m learner.long_panel --build")
    return pd.read_parquet(LONG_TABLE)


def available() -> bool:
    return LONG_TABLE.exists()


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="build or describe the long panel")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--start", type=int, default=LONG_START)
    ap.add_argument("--end", type=int, default=LONG_END)
    ap.add_argument("--describe", action="store_true")
    ap.add_argument("--regate", action="store_true",
                    help="recompute the derived receipt sections from the table on disk")
    a = ap.parse_args(argv)
    if a.regate:
        g = regate()
        print(json.dumps(g, indent=1))
        return 0 if g.get("verdict") == "PASS" else 1
    if a.describe:
        if not LONG_RECEIPT.exists():
            print("no long-panel receipt on disk")
            return 1
        r = json.loads(LONG_RECEIPT.read_text(encoding="utf-8"))["build"]
        print(f"window {r.get('window')}  rows {r.get('rows')}  months {r.get('months')}")
        for row in r.get("coverage_by_year", []):
            print(f"  {row['year']}  {row['name_months']:>7,} name-months  "
                  f"{row['permnos']:>5,} names  hygiene {row['hygiene_pass_rate']}")
        return 0
    if a.build:
        df, receipt = build_long(a.start, a.end)
        save_long(df, receipt)
        print(f"WROTE {LONG_TABLE} ({len(df):,} rows)")
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
