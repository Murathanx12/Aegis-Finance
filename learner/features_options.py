"""OPTION-SURFACE FEATURES -- what the options market believed about a name at t.

WHAT THIS ADDS THAT THE PANEL DOES NOT ALREADY HAVE
===================================================
Every risk column the long panel carries is BACKWARD-LOOKING: `vol_20d`,
`vol_60d`, `drawdown_60d` are all functions of bars that already printed. The
implied-volatility surface is the only series on this disk that is a PRICE OF A
FORWARD-LOOKING CLAIM -- somebody paid money at t for a payoff that depends on
what happens after t, and the number that clears that market is a forecast with
a P&L attached to being wrong. That is a genuinely different information source
from anything in `learner/dataset.py`, which is the whole reason W5 exists: the
bottleneck (`CLAUDE.md`) is that ten books select on one signal, and a second
signal has to come from a second kind of observation, not a second transform of
the first.

Four claims, one column each, and each one is a claim about a DIFFERENT part of
the surface rather than four views of its level:

* **`atm_iv_30d`** -- the 1-month at-the-money implied vol, the average of the
  50-delta call and the 50-delta put. This is the level, and it is included
  precisely BECAUSE it is nearly a restatement of realised vol. It is the
  control the other three need: if `skew` predicts and `atm_iv_30d` predicts
  identically, skew is volatility wearing a name.
* **`atm_iv_chg_1m`** -- the 21-session change in that level. A level says which
  names are risky; a CHANGE says where the options market just revised. The
  distinction is the same one `mom_12_1` draws against `log_close`.
* **`cp_iv_spread_30d`** -- 50-delta call IV minus 50-delta put IV, the
  Cremers-Weinbaum volatility spread. Under put-call parity two options on the
  same strike and expiry must carry the same implied vol; the spread is
  therefore not a vol measure at all but a measure of DEVIATION FROM PARITY, and
  the standard reading is that it is where directional information shows up
  first, because an informed buyer lifts one side and not the other.
* **`skew_25d_30d`** -- 25-delta put IV minus 25-delta call IV. The price of
  crash insurance relative to the price of upside. It is reported separately
  from the parity spread because the two are about different parts of the
  distribution -- one is the tail, the other is the middle -- and averaging them
  into a single "options signal" would hide which one, if either, carried it.
* **`iv_minus_rv_21d`** -- the same ATM implied vol minus the trailing 21-session
  realised vol of the underlying, annualised from CRSP daily returns. The
  variance risk premium proxy: what the market charges for variance over what
  variance has actually cost lately.

THE CONTROL IS NOT OPTIONAL AND IT DOES NOT GO IN A SENTENCE
============================================================
Implied vol correlates hard with realised vol, and both correlate with size --
the names with a liquid 30-day surface at all are not a random draw from CRSP.
A raw rank IC on any column here would therefore mostly re-measure `vol_60d` and
`log_market_cap`, both of which the panel already has. So `job()` reports every
feature TWICE: the plain cross-sectional rank IC, and the t of its coefficient
in a monthly Fama-MacBeth regression that holds momentum, size and vol in the
SAME regression (`feedback_check_whether_the_noise_is_shared`). The second
number is the one that says whether the surface adds anything; the gap between
the two is the receipt of how much of the first was borrowed.

WHERE THE DATA IS, AND THE ONE THING THAT WOULD HAVE BEEN EASY TO GET WRONG
===========================================================================
`backend/data/optimus/wrds/optionm_surface30d_<year>.parquet`, 1996-2024, 853 MB
across 29 files. It is the DAILY standardised surface (`optionm.vsurfd<year>`)
already narrowed at pull time to `days = 30` and `abs(delta) IN (25, 50)`, which
is exactly the four coordinates these five columns need and nothing else.

There is a SECOND OptionMetrics surface extraction on this machine, at
`Aegis module/data/wrds_raw/optionm_vsurf_me/`, 2002-2024. It is MONTH-END: 2015
holds exactly twelve observation dates. It is not used here, and the reason is
recorded in `scripts/wrds_pull_vsurfd_daily.py`: month-end is a property of that
extraction's `WHERE` clause, not of OptionMetrics. Reading the narrow file and
concluding the data is monthly is the house error, and it was already made twice
on this dataset. The daily file is the one on this repo's own disk; the
month-end one is a different repo's narrower cut of the same table.

THE LINK IS REUSED, NOT RE-DERIVED
==================================
OptionMetrics is keyed on `secid`, CRSP on `permno`, and
`backend/data/optimus/wrds/link_optionm_crsp.parquet` already holds
`wrdsapps_link_crsp_optionm.opcrsphist` -- 121,773 rows of
`(secid, permno, sdate, edate, score)`, of which 34,881 carry a permno at all
(`score = 6` is WRDS's no-match code). A second copy of that mapping derived
here would drift from the one every other module uses, so this reads it and
applies its INTERVAL validity: a row is linked only where
`sdate <= date <= edate`. A secid that was reassigned mid-history therefore
changes permno on the right day instead of being stamped with whichever permno
happened to be first in the file.

The match rate comes out near 100%, and that is not a triumph -- it is a
consequence. The surface was pulled with `WHERE secid = ANY(...)` over exactly
the secids this link resolves to screened CRSP permnos, so the file on disk was
already bounded by the link. The receipt says so, because a 99% match rate that
is really a restatement of the pull filter reads exactly like a 99% match rate
that is evidence about the link, and they are different facts.

POINT-IN-TIME
=============
The surface at date `t` is an END-OF-DAY object; the pull manifest's own
`pit_knowledge_column` says to treat it as known at `t+1` open to be
conservative. So `attach` joins BACKWARD onto `entry_date` with
`allow_exact_matches=False`: a surface dated the same day the money moved is
REFUSED, not used. Tolerance is 7 calendar days, so a name whose surface went
stale gets NaN rather than a value carried forward from a month ago.

The 21-session lag inside `atm_iv_chg_1m` carries the same discipline from the
other end: `shift(21)` alone would happily span a two-year gap in a thinly
covered name and call the result a one-month change, so the lagged DATE is
shifted alongside the value and the difference is voided where the two dates are
more than `MAX_LAG_GAP_DAYS` apart.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
WRDS = REPO / "backend" / "data" / "optimus" / "wrds"
OUT_DIR = REPO / "backend" / "data" / "optimus" / "learner"
OPTION_FEATURES = OUT_DIR / "features_options.parquet"
OPTION_RECEIPT = OUT_DIR / "features_options_receipt.json"

#: The DAILY surface, already narrowed at pull time to days=30, |delta| in {25,50}.
SURFACE_STEM = "optionm_surface30d_"
#: `wrdsapps_link_crsp_optionm.opcrsphist`, pulled 2026-08-19. Reused, never rebuilt.
LINK_FILE = WRDS / "link_optionm_crsp.parquet"

VERSION = "features-options-1"

#: Trading sessions in the "one month" of `atm_iv_chg_1m`.
LAG_SESSIONS = 21
#: ...and the calendar bound that stops that lag spanning a hole in coverage.
#: 21 sessions is ~31 calendar days; 45 admits a holiday-heavy month and refuses
#: a name that simply stopped having a surface for a quarter.
MAX_LAG_GAP_DAYS = 45
#: The realised-vol window, in sessions, and the annualisation factor. 21 to
#: match the horizon of the implied number it is subtracted from -- a 60-day
#: realised vol against a 30-day implied vol would put a term-structure slope
#: into a column labelled "risk premium".
RV_SESSIONS = 21
RV_MIN_SESSIONS = 15
TRADING_DAYS = 252

#: The columns this module produces, and the family each belongs to. The family
#: is what an ablation removes -- one CLAIM at a time. `atm_iv_30d` and
#: `iv_minus_rv_21d` are deliberately in different families even though one is
#: built from the other: the level is a risk proxy and the difference is a
#: price, and an ablation that removed both at once could not tell which lost.
FAMILIES: dict[str, tuple[str, ...]] = {
    "iv_level": ("atm_iv_30d",),
    "iv_dynamics": ("atm_iv_chg_1m",),
    "informed_flow": ("cp_iv_spread_30d",),
    "tail_skew": ("skew_25d_30d",),
    "variance_premium": ("iv_minus_rv_21d",),
}

FEATURES: tuple[str, ...] = tuple(c for cols in FAMILIES.values() for c in cols)

#: What each column is, in the receipt, so a reader never has to reconstruct the
#: sign convention from the code. A skew whose sign is guessed is a skew whose
#: verdict is guessed.
DEFINITIONS: dict[str, str] = {
    "atm_iv_30d": "mean(IV[30d, 50-delta call], IV[30d, 50-delta put])",
    "atm_iv_chg_1m": f"atm_iv_30d(t) - atm_iv_30d(t-{LAG_SESSIONS} sessions), voided across a "
                     f"gap of more than {MAX_LAG_GAP_DAYS} calendar days",
    "cp_iv_spread_30d": "IV[30d, 50-delta CALL] - IV[30d, 50-delta PUT]; positive = calls "
                        "richer than puts (put-call parity violated on the call side)",
    "skew_25d_30d": "IV[30d, 25-delta PUT] - IV[30d, 25-delta CALL]; positive = crash "
                    "insurance dearer than upside, the usual sign for equities",
    "iv_minus_rv_21d": f"atm_iv_30d - annualised {RV_SESSIONS}-session realised vol of the "
                       "underlying from CRSP daily returns",
}


def family_of(col: str) -> str | None:
    for fam, cols in FAMILIES.items():
        if col in cols:
            return fam
    return None


# ------------------------------------------------------- what is actually there

def surface_files() -> dict[int, Path]:
    """Every daily-surface parquet on disk, keyed by year. No data is read."""
    out = {}
    for f in sorted(WRDS.glob(f"{SURFACE_STEM}*.parquet")):
        stem = f.stem[len(SURFACE_STEM):]
        if stem.isdigit():
            out[int(stem)] = f
    return out


def coverage_on_disk() -> dict:
    """The REAL window, measured from parquet row-group statistics, not asserted.

    "OptionMetrics is 1996-2024" is a sentence. `pyarrow` will hand back the min
    and max of the `date` column of every row group without decoding a single
    value, so the window in the receipt is the window of the bytes rather than
    the window of a docstring somebody copied. It costs milliseconds; a wrong
    coverage claim costs a re-run.
    """
    import pyarrow.parquet as pq
    files = surface_files()
    if not files:
        raise SystemExit(
            f"REFUSED: no {SURFACE_STEM}*.parquet under {WRDS}. The daily OptionMetrics "
            "surface is what this module is built on; without it there is nothing to "
            "measure and a silently empty frame would be the worst possible output.")
    years, total_rows, lo_all, hi_all = [], 0, None, None
    for year, path in files.items():
        md = pq.ParquetFile(path).metadata
        names = [md.schema.column(i).name for i in range(md.num_columns)]
        j = names.index("date")
        lo = hi = None
        for rg in range(md.num_row_groups):
            st = md.row_group(rg).column(j).statistics
            if st is not None and st.has_min_max:
                lo = st.min if lo is None or st.min < lo else lo
                hi = st.max if hi is None or st.max > hi else hi
        years.append({"year": year, "rows": int(md.num_rows),
                      "first_date": str(lo), "last_date": str(hi),
                      "mb": round(path.stat().st_size / 1e6, 1)})
        total_rows += int(md.num_rows)
        lo_all = lo if lo_all is None or (lo is not None and lo < lo_all) else lo_all
        hi_all = hi if hi_all is None or (hi is not None and hi > hi_all) else hi_all
    return {
        "source": "optionm.vsurfd<year>, days=30, abs(delta) in {25,50} (pull-time filter)",
        "dir": str(WRDS),
        "n_files": len(files),
        "total_rows": total_rows,
        "total_mb": round(sum(y["mb"] for y in years), 1),
        "measured_window": [str(lo_all), str(hi_all)],
        "years_present": sorted(files),
        "missing_years_inside_window": [y for y in range(min(files), max(files) + 1)
                                        if y not in files],
        "by_year": years,
        "measured_how": "pyarrow row-group statistics on the `date` column; no rows decoded",
    }


# -------------------------------------------------------------------- the link

def load_link() -> pd.DataFrame:
    """`opcrsphist`, filtered to rows that actually carry a permno.

    Reused, not re-derived: `link_optionm_crsp.parquet` is the copy every other
    OptionMetrics consumer in this repo reads, and a second derivation here would
    be a second mapping that drifts. `score = 6` is WRDS's no-match code and
    those rows carry a null permno; they are dropped here and COUNTED in the
    receipt, because "86,892 secids have no CRSP counterpart" is a fact about
    OptionMetrics' index-and-ETF coverage, not a defect to hide.
    """
    if not LINK_FILE.exists():
        raise SystemExit(
            f"REFUSED: {LINK_FILE} does not exist. secid has no meaning to CRSP without "
            "it, and inventing a link here would create a second mapping that drifts "
            "from the one the rest of the repo joins on.")
    link = pd.read_parquet(LINK_FILE)
    link = link[link["permno"].notna()].copy()
    link["sdate"] = pd.to_datetime(link["sdate"])
    link["edate"] = pd.to_datetime(link["edate"])
    link["secid"] = link["secid"].astype("int64")
    link["permno"] = link["permno"].astype("int64")
    return link[["secid", "permno", "sdate", "edate", "score"]]


# -------------------------------------------------------------- the ingredients

def _surface_year(path: Path) -> pd.DataFrame:
    """One year of the daily surface, pivoted to one row per (secid, date).

    The four coordinates become four columns named by side and |delta|. A
    (secid, date) whose surface OptionMetrics could not fit carries NaN in the
    coordinate it failed on rather than vanishing, which is what lets the
    coverage line below be a measurement instead of a tautology.
    """
    d = pd.read_parquet(path, columns=["secid", "date", "delta",
                                       "impl_volatility", "cp_flag"])
    d = d[d["impl_volatility"].notna()]
    if d.empty:
        return pd.DataFrame(columns=["secid", "date", "C25", "C50", "P25", "P50"])
    coord = d["cp_flag"].astype(str) + d["delta"].abs().round().astype("int64").astype(str)
    d = d.assign(coord=coord)
    w = d.pivot_table(index=["secid", "date"], columns="coord",
                      values="impl_volatility", aggfunc="first")
    for c in ("C25", "C50", "P25", "P50"):
        if c not in w.columns:
            w[c] = np.nan
    w = w[["C25", "C50", "P25", "P50"]].reset_index()
    w["date"] = pd.to_datetime(w["date"])
    w["secid"] = w["secid"].astype("int64")
    for c in ("C25", "C50", "P25", "P50"):
        w[c] = w[c].astype("float32")
    return w


def lagged_change(df: pd.DataFrame, value_col: str, by: str = "secid",
                  date_col: str = "date", sessions: int = LAG_SESSIONS,
                  max_gap_days: int = MAX_LAG_GAP_DAYS) -> tuple[pd.Series, int]:
    """`value(t) - value(t - sessions)`, VOIDED where the two dates are far apart.

    A module-level function rather than four lines inside `build` because it is
    the one piece of arithmetic here that can be wrong without looking wrong:
    `shift(21)` on a name that stopped having a surface for two years returns a
    perfectly finite number and calls it a one-month change. The lagged DATE is
    shifted alongside the lagged VALUE and the difference is voided -- not
    interpolated, not forward-filled -- where the gap exceeds `max_gap_days`,
    because a repaired gap is an invented observation.

    Expects `df` already sorted by (`by`, `date_col`). Returns the series and the
    COUNT of lags voided, so the receipt can carry the number rather than the
    intention.
    """
    g = df.groupby(by, sort=False)
    lag_v = g[value_col].shift(sessions)
    lag_d = g[date_col].shift(sessions)
    within = (df[date_col] - lag_d).dt.days <= max_gap_days
    voided = int((lag_v.notna() & ~within).sum())
    return (df[value_col] - lag_v).where(within), voided


def _realised_vol(permnos: set[int], start: int, end: int,
                  log=lambda *a: None) -> pd.DataFrame:
    """Annualised trailing realised vol per (permno, date) from CRSP daily returns.

    `start - 1` is read so the first scored session of `start` already has a full
    window behind it -- the same warm-up rule `features_price` uses, for the same
    reason: a rolling column whose first months are computed on half a window is
    a different column from the one the rest of the panel carries.
    """
    frames = []
    for year in range(start - 1, end + 1):
        f = WRDS / f"crsp_dsf_{year}.parquet"
        if not f.exists():
            continue
        d = pd.read_parquet(f, columns=["permno", "date", "ret"])
        d["permno"] = d["permno"].astype("int64")
        d = d[d["permno"].isin(permnos)]
        d["ret"] = pd.to_numeric(d["ret"], errors="coerce").astype("float32")
        frames.append(d)
    if not frames:
        raise SystemExit(
            f"REFUSED: no crsp_dsf_*.parquet in {start - 1}-{end}. Without the underlying's "
            "own return history there is no realised vol, and `iv_minus_rv_21d` would be a "
            "column of NaN wearing the name of a risk premium.")
    px = pd.concat(frames, ignore_index=True)
    del frames
    px["date"] = pd.to_datetime(px["date"])
    px = px.sort_values(["permno", "date"]).reset_index(drop=True)
    log(f"  crsp daily rows for the option universe: {len(px):,}")
    rv = px.groupby("permno", sort=False)["ret"].transform(
        lambda s: s.rolling(RV_SESSIONS, min_periods=RV_MIN_SESSIONS).std())
    px["rv_21d_ann"] = (rv * np.sqrt(TRADING_DAYS)).astype("float32")
    return px[["permno", "date", "rv_21d_ann"]]


# ------------------------------------------------------------------------ build

def build(start: int = 1998, end: int = 2024, verbose: bool = True) -> tuple[pd.DataFrame, dict]:
    """One row per (permno, date) with the five surface columns, plus a receipt.

    1998 by default so a panel that starts in 1999-03 has a full 21-session lag
    behind its first observation.
    """
    log = (lambda *a: print(*a, flush=True)) if verbose else (lambda *a: None)
    disk = coverage_on_disk()
    files = surface_files()
    wanted = [y for y in sorted(files) if start <= y <= end]
    if not wanted:
        raise SystemExit(
            f"REFUSED: no daily surface file inside {start}-{end}; disk holds "
            f"{disk['years_present']}. Building an empty frame here would join cleanly "
            "onto the panel and add five columns of nothing.")
    log(f"BUILD OPTION-SURFACE FEATURES {wanted[0]}-{wanted[-1]} (version {VERSION})")
    log(f"  disk coverage measured: {disk['measured_window'][0]} .. "
        f"{disk['measured_window'][1]} over {disk['n_files']} files, "
        f"{disk['total_rows']:,} raw rows")

    frames = []
    for year in wanted:
        w = _surface_year(files[year])
        log(f"  {year}: {len(w):,} (secid,date) rows, {w['secid'].nunique():,} secids")
        frames.append(w)
    surf = pd.concat(frames, ignore_index=True)
    del frames
    surf = surf.sort_values(["secid", "date"]).reset_index(drop=True)
    raw_rows = len(surf)
    raw_secids = int(surf["secid"].nunique())
    coord_cov = {c: round(float(surf[c].notna().mean()), 4)
                 for c in ("C25", "C50", "P25", "P50")}
    log(f"  surface: {raw_rows:,} (secid,date) rows, {raw_secids:,} secids; "
        f"coordinate coverage {coord_cov}")

    # ------------------------------------------------ the four surface columns
    surf["atm_iv_30d"] = ((surf["C50"] + surf["P50"]) / 2.0).astype("float32")
    surf["cp_iv_spread_30d"] = (surf["C50"] - surf["P50"]).astype("float32")
    surf["skew_25d_30d"] = (surf["P25"] - surf["C25"]).astype("float32")

    # The 21-session change, with the lagged DATE carried alongside the lagged
    # VALUE. `shift(21)` on its own cannot tell a one-month change from a
    # two-year hole in a thinly covered name; the date guard can, and it voids
    # rather than repairs, because a repaired gap is an invented observation.
    chg, voided = lagged_change(surf, "atm_iv_30d")
    surf["atm_iv_chg_1m"] = chg.astype("float32")
    log(f"  atm_iv_chg_1m: {voided:,} lags voided by the {MAX_LAG_GAP_DAYS}-day gap guard")

    surf = surf.drop(columns=["C25", "C50", "P25", "P50"])

    # --------------------------------------------------------- secid -> permno
    link = load_link()
    merged = surf.merge(link, on="secid", how="left")
    valid = (merged["permno"].notna() & (merged["date"] >= merged["sdate"])
             & (merged["date"] <= merged["edate"]))
    linked = merged[valid].copy()
    del merged
    # A permno reached by two secids on one day is a real possibility (a name
    # with an ordinary and a when-issued option class). Deterministic tie-break:
    # the lowest opcrsphist `score` -- WRDS's own confidence order, 1 best -- and
    # the lower secid to break a tie in the score. Counted, never silent.
    linked = linked.sort_values(["permno", "date", "score", "secid"])
    dup = int(linked.duplicated(["permno", "date"]).sum())
    linked = linked.drop_duplicates(["permno", "date"], keep="first")
    linked["permno"] = linked["permno"].astype("int64")

    matched_pairs = int(len(linked))
    match_rate = round(matched_pairs / raw_rows, 4) if raw_rows else 0.0
    matched_secids = int(linked["secid"].nunique())
    log(f"  link: {matched_pairs:,}/{raw_rows:,} surface rows carry a permno "
        f"({match_rate:.2%}); {matched_secids:,}/{raw_secids:,} secids; "
        f"{dup:,} (permno,date) collisions de-duplicated")
    if match_rate == 0.0:
        raise SystemExit(
            "REFUSED: the secid->permno link matched ZERO surface rows. Either the link "
            "file is for a different universe or the date intervals do not overlap the "
            "surface; joining an empty frame onto the panel would be silent.")

    # ------------------------------------------------- the variance risk premium
    permnos = set(linked["permno"].unique().tolist())
    rv = _realised_vol(permnos, wanted[0], wanted[-1], log=log)
    before = len(linked)
    linked = linked.merge(rv, on=["permno", "date"], how="left")
    rv_rate = round(float(linked["rv_21d_ann"].notna().mean()), 4)
    log(f"  realised vol matched on {rv_rate:.2%} of {before:,} linked rows "
        "(exact (permno,date), no asof)")
    linked["iv_minus_rv_21d"] = (linked["atm_iv_30d"] - linked["rv_21d_ann"]).astype("float32")

    out = linked[["permno", "date", *FEATURES]].copy()
    out = out[out[list(FEATURES)].notna().any(axis=1)]
    out = out.sort_values(["permno", "date"]).reset_index(drop=True)

    cov = {c: round(float(out[c].notna().mean()), 4) for c in FEATURES}
    empty = [c for c, v in cov.items() if v == 0.0]
    if empty:
        raise SystemExit(
            f"REFUSED: {empty} are NaN on every row of {len(out):,}. A column that is empty "
            "everywhere is a column that was never built, and joining it to the panel would "
            "add a feature the model silently ignores.")

    # Hand-checkable summary statistics. The SIGN of `skew_25d_30d` is the one a
    # reader can falsify from memory: equity index and single-name skew is
    # normally positive (crash insurance is dear), so a negative median here
    # would mean the two legs were subtracted the wrong way round. Printed, not
    # asserted, because a hardcoded sign assertion would be a fixture that rots.
    stats = {c: {"median": round(float(out[c].median()), 6),
                 "p05": round(float(out[c].quantile(0.05)), 6),
                 "p95": round(float(out[c].quantile(0.95)), 6)} for c in FEATURES}

    receipt = {
        "version": VERSION,
        "window_requested": f"{start}-{end}",
        "window_built": f"{wanted[0]}-{wanted[-1]}",
        "rows": int(len(out)),
        "permnos": int(out["permno"].nunique()),
        "first_date": str(out["date"].min().date()),
        "last_date": str(out["date"].max().date()),
        "families": {k: list(v) for k, v in FAMILIES.items()},
        "definitions": DEFINITIONS,
        "non_null_rate": cov,
        "summary_stats": stats,
        "disk_coverage": disk,
        "surface_coordinate_coverage": coord_cov,
        "surface_rows_before_link": raw_rows,
        "surface_secids_before_link": raw_secids,
        "link": {
            "file": str(LINK_FILE),
            "table": "wrdsapps_link_crsp_optionm.opcrsphist",
            "rule": "sdate <= date <= edate, interval validity applied per row",
            "matched_rows": matched_pairs,
            "match_rate": match_rate,
            "matched_secids": matched_secids,
            "secids_on_the_surface": raw_secids,
            "permno_date_collisions_deduped": dup,
            "tie_break": "lowest opcrsphist score, then lowest secid",
            "why_the_rate_is_high": (
                "the surface was pulled with WHERE secid = ANY(<secids of screened CRSP "
                "permnos>), so the file on disk was ALREADY bounded by this same link. A "
                "high match rate here restates the pull filter; it is not independent "
                "evidence that the link is good."),
        },
        "realised_vol": {
            "source": "crsp_dsf_<year>.parquet ret column",
            "window_sessions": RV_SESSIONS,
            "min_sessions": RV_MIN_SESSIONS,
            "annualisation": TRADING_DAYS,
            "match_rate_on_linked_rows": rv_rate,
            "join": "exact (permno, date); no asof, so a missing bar is NaN not a stale vol",
        },
        "lag_guard": {"sessions": LAG_SESSIONS, "max_gap_days": MAX_LAG_GAP_DAYS,
                      "lags_voided": voided},
        "pit_note": (
            "the surface at date t is an END-OF-DAY object (the pull manifest says treat it "
            "as known at t+1 open); `attach` therefore joins BACKWARD with "
            "allow_exact_matches=False, so a surface dated the same day the money moved is "
            "refused rather than used"),
        "not_used_note": (
            "the month-end extraction at 'Aegis module/data/wrds_raw/optionm_vsurf_me' "
            "(2002-2024, 12 dates a year) is NOT the source here; month-end is a property "
            "of that pull's WHERE clause, not of OptionMetrics"),
        "built_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    log("  coverage: " + ", ".join(f"{c} {v:.3f}" for c, v in cov.items()))
    log("  medians:  " + ", ".join(f"{c} {stats[c]['median']:+.4f}" for c in FEATURES))
    return out, receipt


def save(df: pd.DataFrame, receipt: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OPTION_FEATURES, index=False)
    OPTION_RECEIPT.write_text(json.dumps(receipt, indent=2, default=str), encoding="utf-8")


def load() -> pd.DataFrame:
    if not OPTION_FEATURES.exists():
        raise SystemExit(f"REFUSED: {OPTION_FEATURES} does not exist. Build it: "
                         "python -m learner.features_options --build")
    return pd.read_parquet(OPTION_FEATURES)


def available() -> bool:
    return OPTION_FEATURES.exists()


def attach(panel: pd.DataFrame, feats: pd.DataFrame | None = None,
           tolerance_days: int = 7,
           allow_same_day: bool = False) -> tuple[pd.DataFrame, dict]:
    """BACKWARD merge_asof onto `entry_date`, with the same-day surface REFUSED.

    Backward, not nearest: a forward join would hand the panel a surface dated
    after the trade. `allow_exact_matches=False` goes one step further and
    refuses the surface dated ON the trade date too, because that surface is an
    end-of-day object and the trade is not -- the pull's own manifest says to
    treat it as known at t+1. `allow_same_day=True` exists only so a caller can
    MEASURE what that costs; it is not the default and it is not PIT.

    The note carries the per-column MATCH RATE, because a join that silently
    matched 3% of rows and a join that matched 97% produce the same shaped frame.
    """
    if feats is None:
        feats = load()
    p = panel.copy()
    p["entry_date"] = pd.to_datetime(p["entry_date"])
    f = feats.copy()
    f["date"] = pd.to_datetime(f["date"])
    p["permno"] = p["permno"].astype("int64")
    f["permno"] = f["permno"].astype("int64")
    p = p.sort_values("entry_date")
    f = f.sort_values("date")
    before = len(p)
    p = pd.merge_asof(p, f, left_on="entry_date", right_on="date", by="permno",
                      direction="backward", allow_exact_matches=allow_same_day,
                      tolerance=pd.Timedelta(days=tolerance_days),
                      suffixes=("", "_optfeat"))
    rates = {c: round(float(p[c].notna().mean()), 4) for c in FEATURES}
    lag = (p["entry_date"] - p["date"]).dt.days if "date" in p.columns else None
    note = {
        "rows_in": before, "rows_out": int(len(p)),
        "match_rate": rates,
        "tolerance_days": tolerance_days,
        "allow_same_day": bool(allow_same_day),
        "direction": ("backward, exact matches EXCLUDED -- the surface is end-of-day and "
                      "the trade is not" if not allow_same_day else
                      "backward, exact matches ALLOWED (diagnostic only, not PIT)"),
        "median_lag_days": (round(float(lag.dropna().median()), 1)
                            if lag is not None and lag.notna().any() else None),
        "note": ("the ceiling here is not the join, it is OPTION COVERAGE: only names with a "
                 "listed and liquid 30-day surface have a row at all, which is a size and "
                 "liquidity filter on top of the panel's own"),
    }
    worst = min(rates.values()) if rates else 0.0
    note["verdict"] = ("JOINED" if worst > 0.5 else
                       f"THIN -- worst column matches {worst:.1%} of rows")
    return p.drop(columns=[c for c in p.columns if c.endswith("_optfeat")]), note


# -------------------------------------------------------------------- the job

#: `variant` selects the horizon the features are scored against. One month is
#: the horizon the informed-trading literature claims for the volatility spread;
#: three months is the honest robustness check, and disagreeing horizons are
#: information rather than an inconvenience.
VARIANTS: tuple[str, ...] = ("excess_vw_1m", "excess_vw_3m")

#: How many months of forward return each target spans -- which is how many
#: months of OVERLAP a monthly series of it carries. A monthly series of
#: 3-month forward returns is the same history counted three times, and its
#: naive t rises with horizon for a purely mechanical reason
#: (`feedback_name_days_are_not_periods`; CANON §58). So the Fama-MacBeth t is
#: reported BOTH ways and the survivor bar is set on the Newey-West one.
HORIZON_MONTHS: dict[str, int] = {"excess_vw_1m": 1, "excess_vw_3m": 3}


def job(variant: int = 0) -> dict:
    """W5 -- does the option surface add anything to momentum, size and vol?

    Same shape as `W6_behavioural`, and deliberately so: two independent feature
    families judged by one ruler is the only way their numbers are comparable
    (`B1`, 2026-09-05: one ruler, one tape). Every feature is reported twice --
    the plain monthly rank IC, and the t of its coefficient in a Fama-MacBeth
    regression that holds momentum, size and vol IN THE SAME monthly regression.

    The controlled number is the verdict. The raw IC is kept because the GAP
    between the two is itself the finding: an option column with a big raw IC and
    a dead controlled t is realised volatility with a forward-looking label on
    it, and that is the single most likely way this family fools somebody.
    """
    from learner import long_panel as LP, inference
    # Reused, not re-derived: `evaluate.hac_t` is the repo's one Newey-West.
    from learner.evaluate import hac_t
    # The era table is imported, never re-derived. Its own docstring records why:
    # an era boundary each job re-derives is an era boundary each job can get
    # subtly different, and the weekend's verdict rule counts signs across eras.
    from scripts.weekend_lab_jobs import era_sign_table

    if not available():
        return {"verdict": "DEFERRED", "job_planned": "W5_options_iv",
                "headline": ("features_options.parquet not built yet "
                             "(python -m learner.features_options --build)")}
    ret = VARIANTS[variant % len(VARIANTS)]
    nw_lags = HORIZON_MONTHS[ret] - 1
    df = LP.load_long()
    df, join_note = attach(df)
    controls = ["mom_12_1", "log_market_cap", "vol_60d"]
    have = [c for c in controls if c in df.columns]

    rows, series = [], {}
    for feat in FEATURES:
        d = df[["month", feat, ret, *have]].dropna()
        if len(d) < 5000:
            rows.append({"feature": feat, "family": family_of(feat),
                         "verdict": "CANNOT DETERMINE", "rows": int(len(d)),
                         "why": "fewer than 5,000 usable rows"})
            continue
        ics, betas, months = [], [], []
        for m, g in d.groupby("month", sort=True):
            if len(g) < 30:
                continue
            months.append(m)
            ics.append(float(g[feat].rank().corr(g[ret].rank())))
            X = np.column_stack([np.ones(len(g))] + [
                g[c].rank(pct=True).to_numpy() for c in [feat, *have]])
            y = g[ret].to_numpy(dtype="float64")
            try:
                coef, *_ = np.linalg.lstsq(X, y, rcond=None)
                betas.append(float(coef[1]))
            except np.linalg.LinAlgError:
                betas.append(np.nan)
        if len(ics) < 24:
            rows.append({"feature": feat, "family": family_of(feat),
                         "verdict": "CANNOT DETERMINE", "months": len(ics),
                         "why": "fewer than 24 usable months"})
            continue
        ic = pd.Series(ics, index=months)
        be = pd.Series(betas, index=months).dropna()
        t_ic = (float(ic.mean() / (ic.std(ddof=1) / np.sqrt(len(ic))))
                if ic.std(ddof=1) else None)
        t_be = (float(be.mean() / (be.std(ddof=1) / np.sqrt(len(be))))
                if len(be) > 2 and be.std(ddof=1) else None)
        t_nw = hac_t(be, nw_lags) if len(be) > 4 else None
        series[feat] = be
        rows.append({
            "feature": feat, "family": family_of(feat),
            "definition": DEFINITIONS[feat],
            "rows": int(len(d)), "months": int(len(ic)),
            "names_per_month_median": int(d.groupby("month").size().median()),
            "mean_rank_ic": round(float(ic.mean()), 5),
            "t_rank_ic": round(t_ic, 3) if t_ic is not None else None,
            "mean_fm_beta_controlled": round(float(be.mean()), 6) if len(be) else None,
            "t_fm_beta_controlled": round(t_be, 3) if t_be is not None else None,
            "t_fm_beta_controlled_hac": round(t_nw, 3) if t_nw is not None else None,
            "newey_west_lags": nw_lags,
            "overlap_note": ("the target spans "
                             f"{HORIZON_MONTHS[ret]} month(s), so a monthly series of it "
                             f"overlaps {nw_lags} month(s); the HAC t is the one the "
                             "survivor bar uses"),
            "controls": have,
            "era_sign_table": era_sign_table(be),
            "power": inference.power_note(be.tolist()),
        })

    # SAME sign, not positive sign: a feature that is reliably negative is traded
    # the other way round and is just as much a signal (W6's own correction).
    def _t(r):
        v = r.get("t_fm_beta_controlled_hac")
        return v if isinstance(v, (int, float)) else r.get("t_fm_beta_controlled")

    survivors = [r for r in rows
                 if isinstance(_t(r), (int, float)) and abs(_t(r)) >= 2.0
                 and (r.get("era_sign_table") or {}).get("same_sign_in_2_of_3")]
    killed_by_controls = [
        r["feature"] for r in rows
        if isinstance(r.get("t_rank_ic"), (int, float)) and isinstance(_t(r), (int, float))
        and abs(r["t_rank_ic"]) >= 3.0 and abs(_t(r)) < 2.0]
    tested = [r for r in rows if "t_fm_beta_controlled" in r]

    return {
        "question": ("does the 30-day implied-volatility surface -- level, one-month change, "
                     "call-put parity spread, 25-delta skew and the variance risk premium -- "
                     f"add anything to momentum, size and vol for {ret} on the 1999-2024 "
                     "panel?"),
        "family_id": "weekend-W5-options-iv",
        "variant": variant, "target": ret,
        "surface_coverage": (json.loads(OPTION_RECEIPT.read_text(encoding="utf-8"))
                             .get("disk_coverage", {}).get("measured_window")
                             if OPTION_RECEIPT.exists() else None),
        "join": join_note,
        "features": rows,
        "n_features_tested": len(rows),
        "newey_west_lags": nw_lags,
        "survivors_controlled_t2_and_same_sign_2of3_eras": [
            {"feature": r["feature"], "t": _t(r),
             "t_naive": r["t_fm_beta_controlled"],
             "sign": (r.get("era_sign_table") or {}).get("dominant_sign")}
            for r in survivors],
        "killed_by_the_controls": killed_by_controls,
        "killed_note": ("these cleared |t| >= 3 on the RAW rank IC and fall below |t| = 2 "
                        "once momentum, size and vol are in the same monthly regression. "
                        "For an option column that specifically means realised volatility "
                        "wearing a forward-looking label."),
        "coverage_caveat": ("the option universe is NOT the panel universe: a name only has "
                            "a row here if it had a listed 30-day surface, which is a size "
                            "and liquidity screen on top of the panel's own. Every number "
                            "above is conditional on that screen and says nothing about the "
                            "names it excludes."),
        "multiplicity_note": (f"{len(tested)} features were scored; a |t| >= 2 bar on "
                              f"{len(tested)} independent tests expects "
                              f"{0.05 * max(len(tested), 1):.1f} false positives, so the "
                              "era requirement is doing the work a Holm correction would"),
        "headline": (f"{len(tested)} option-surface features on "
                     f"{join_note.get('rows_out', 0):,} panel rows "
                     f"(worst column matches {min(join_note.get('match_rate', {0: 0}).values()):.1%} "
                     f"of them); {len(survivors)} clear |t| >= 2 WITH momentum, size and vol "
                     f"in the regression and keep one sign in 2 of 3 eras: "
                     f"{[(r['feature'], _t(r)) for r in survivors] or 'none'}"
                     f"; killed by the controls: {killed_by_controls or 'none'}"),
        "verdict": "NOVEL" if survivors else "NOISE",
    }


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="option implied-volatility surface features")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--coverage", action="store_true",
                    help="measure what is on disk and print it; reads no rows")
    ap.add_argument("--job", action="store_true")
    ap.add_argument("--variant", type=int, default=0)
    ap.add_argument("--start", type=int, default=1998)
    ap.add_argument("--end", type=int, default=2024)
    a = ap.parse_args(argv)
    if a.coverage:
        print(json.dumps(coverage_on_disk(), indent=2, default=str))
        return 0
    if a.build:
        df, rec = build(a.start, a.end)
        save(df, rec)
        print(f"WROTE {OPTION_FEATURES} ({len(df):,} rows)")
        return 0
    if a.job:
        print(json.dumps(job(a.variant), indent=2, default=str))
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
