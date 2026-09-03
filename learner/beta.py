"""PRE-PERIOD MARKET BETA, for the band-horizon decomposition.

WHY THIS FILE EXISTS
====================
`learner/dataset.py` builds every feature knowable at a vintage and the forward
excess returns at 1/3/6/12 months -- but it does not build a BETA, and without
one there is no way to answer whether the band overlay's excess is selection or
a leverage tilt riding the market leg. TRIAL-BAND-IS-BETA-1 declares the
estimator in advance and this file implements exactly that estimator and no
other:

    ordinary least squares of daily return on the daily value-weighted market
    return over the 120 sessions ending on the last session BEFORE the holding
    month begins, a minimum of 60 usable sessions, winsorised at the 1st and
    99th percentile of daily return.

THE ESTIMATION WINDOW ENDS BEFORE THE HOLDING MONTH STARTS
==========================================================
The window ends at the last trading session strictly earlier than the row's
`entry_date`. No beta is ever fitted on a return it is later used to explain.
A name without 60 usable sessions gets NaN and is dropped from BOTH arms of
every comparison downstream -- never from one.

RISK-FREE
=========
The prereg says "daily excess return on daily market excess". The daily
risk-free rate is common to both sides of the regression and cancels out of the
slope to within a rounding error at a daily frequency, and there is no daily
Fama-French file on disk in this repo. `rf = 0` is therefore used and DECLARED,
rather than a rate being invented. The slope is unaffected; only an alpha
intercept would be, and no alpha intercept is read from this regression.

THE MARKET IS THE SAME MARKET
=============================
The value-weighted index is rebuilt with `learner.dataset.market_indices`'s
rule -- CRSP common stock on the main exchanges, membership resolved per
(permno, date) against the stocknames validity windows, weighted on YESTERDAY's
capitalisation -- so the beta's market and the panel's `mkt_vw_*` benchmark are
the same object and not two nearly-identical ones.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts import tracker_ibes_backtest as tib          # noqa: E402

OUT_DIR = REPO / "backend" / "data" / "optimus" / "learner"
BETA_PANEL = OUT_DIR / "beta_panel.parquet"
MARKET_DAILY = OUT_DIR / "market_daily_vw.parquet"

#: Frozen by PREREG_BAND_IS_BETA_1.
BETA_WINDOW = 120
BETA_MIN_OBS = 60
WINSOR_LO, WINSOR_HI = 0.01, 0.99


def _year_frame(year: int) -> pd.DataFrame | None:
    f = tib.WRDS / f"crsp_dsf_{year}.parquet"
    if not f.exists():
        return None
    d = pd.read_parquet(f, columns=["permno", "date", "prc", "ret", "shrout"])
    d["date"] = pd.to_datetime(d["date"])
    d["prc"] = d["prc"].abs()
    d["ret"] = pd.to_numeric(d["ret"], errors="coerce")
    d["market_cap"] = d["prc"] * d["shrout"] * 1_000.0
    return d[["permno", "date", "ret", "market_cap"]]


def build_market_daily(start: int, end: int, verbose: bool = True) -> pd.DataFrame:
    """Daily VW market total return over the CRSP common-stock main-exchange
    universe, weighted on the PREVIOUS session's capitalisation.

    Built one year at a time with the previous December carried in, so the
    first session of each January is weighted on December's caps rather than
    on its own (which would put today's return inside today's weight).
    """
    names = tib.load_names()[["permno", "namedt", "nameenddt"]].sort_values("namedt")
    out = []
    for year in range(start, end + 1):
        cur = _year_frame(year)
        if cur is None:
            continue
        prev = _year_frame(year - 1)
        if prev is not None:
            prev = prev[prev["date"] >= pd.Timestamp(f"{year - 1}-12-01")]
            u = pd.concat([prev, cur], ignore_index=True)
        else:
            u = cur
        u = u.sort_values("date")
        u = pd.merge_asof(u, names, left_on="date", right_on="namedt",
                          by="permno", direction="backward")
        u = u[u["namedt"].notna() & (u["date"] <= u["nameenddt"])]
        u = u.sort_values(["permno", "date"])
        u["w"] = u.groupby("permno", sort=False)["market_cap"].shift(1)
        u = u[u["ret"].notna() & u["w"].notna() & (u["w"] > 0)]
        u = u[u["date"] >= pd.Timestamp(f"{year}-01-01")]
        num = u.assign(_wr=u["w"] * u["ret"]).groupby("date")["_wr"].sum()
        den = u.groupby("date")["w"].sum()
        out.append((num / den).rename("vw_ret"))
        if verbose:
            print(f"    {year}: {len(num)} sessions")
    idx = pd.concat(out).sort_index()
    return idx.reset_index().rename(columns={"index": "date"})


def _rolling_ols_beta(Y: np.ndarray, x: np.ndarray, window: int,
                      min_obs: int) -> np.ndarray:
    """Rolling OLS slope of each column of `Y` on `x`, window ending at t.

    NaNs in Y are excluded pairwise. Implemented with cumulative sums rather
    than a groupby-rolling-cov so that 5,700 names over 3,200 sessions is
    seconds and not an hour.
    """
    T, N = Y.shape
    M = np.isfinite(Y)
    Yz = np.where(M, Y, 0.0)
    xcol = x[:, None]
    sY = np.where(M, Yz, 0.0)
    sX = np.where(M, xcol, 0.0)
    sXX = np.where(M, xcol ** 2, 0.0)
    sXY = np.where(M, xcol * Yz, 0.0)
    n = M.astype(np.float64)

    def roll(a: np.ndarray) -> np.ndarray:
        c = np.cumsum(a, axis=0)
        c = np.vstack([np.zeros((1, N)), c])
        lo = np.maximum(np.arange(T + 1) - window, 0)
        return c[1:] - c[lo[1:]]

    rn, rY, rX, rXX, rXY = (roll(a) for a in (n, sY, sX, sXX, sXY))
    den = rn * rXX - rX ** 2
    num = rn * rXY - rX * rY
    with np.errstate(invalid="ignore", divide="ignore"):
        beta = num / den
    beta[(rn < min_obs) | (den <= 0)] = np.nan
    return beta


def build(permnos, start: int, end: int, verbose: bool = True) -> tuple[pd.DataFrame, dict]:
    """(permno, date, beta_pre) where `beta_pre` is the OLS slope over the 120
    sessions ENDING at `date`. A consumer takes the value at the last session
    strictly before its entry date."""
    log = (lambda *a: print(*a)) if verbose else (lambda *a: None)
    log("  building the daily VW market ...")
    mkt = build_market_daily(start, end, verbose=verbose)

    log("  loading daily returns for the panel's names ...")
    keep = set(int(p) for p in permnos)
    frames = []
    for year in range(start, end + 1):
        d = _year_frame(year)
        if d is None:
            continue
        d = d[d["permno"].isin(keep)][["permno", "date", "ret"]]
        frames.append(d[d["ret"].notna()])
    px = pd.concat(frames, ignore_index=True)
    log(f"    {len(px):,} daily rows, {px['permno'].nunique():,} names")

    lo = float(px["ret"].quantile(WINSOR_LO))
    hi = float(px["ret"].quantile(WINSOR_HI))
    px["ret"] = px["ret"].clip(lo, hi)
    mkt["vw_ret"] = mkt["vw_ret"].clip(lo, hi)

    wide = px.pivot_table(index="date", columns="permno", values="ret", aggfunc="last")
    wide = wide.reindex(mkt.set_index("date").index)
    x = mkt.set_index("date")["vw_ret"].to_numpy(dtype="float64")
    log(f"    matrix {wide.shape[0]} sessions x {wide.shape[1]} names")

    beta = _rolling_ols_beta(wide.to_numpy(dtype="float64"), x,
                             BETA_WINDOW, BETA_MIN_OBS)
    bp = pd.DataFrame(beta, index=wide.index, columns=wide.columns)
    long = bp.stack().rename("beta_pre").reset_index()
    long.columns = ["date", "permno", "beta_pre"]
    long = long[long["beta_pre"].notna()]

    receipt = {
        "estimator": "OLS slope of daily return on daily VW market return",
        "window_sessions": BETA_WINDOW,
        "min_obs": BETA_MIN_OBS,
        "winsor": {"quantiles": [WINSOR_LO, WINSOR_HI],
                   "daily_return_bounds": [round(lo, 6), round(hi, 6)],
                   "note": "pooled over the whole daily panel; a dispersion control, not a signal"},
        "risk_free": "0.0 -- cancels from the slope at a daily frequency; DECLARED, not invented",
        "market": "VW CRSP common-stock main-exchange, weighted on the previous session's cap",
        "sessions": int(len(mkt)),
        "name_date_betas": int(len(long)),
        "names": int(long["permno"].nunique()),
        "window_ends": "at the row's date; consumers read the last session STRICTLY BEFORE entry_date",
    }
    return long, receipt


def save(panel: pd.DataFrame) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(BETA_PANEL, index=False)


def load() -> pd.DataFrame:
    if not BETA_PANEL.exists():
        raise SystemExit(f"REFUSED: {BETA_PANEL} does not exist. Build it first: "
                         "python -m scripts.band_horizon_run --build-betas")
    return pd.read_parquet(BETA_PANEL)


def attach(df: pd.DataFrame, panel: pd.DataFrame) -> pd.Series:
    """`beta_pre` for each row of `df`, read at the last session STRICTLY
    BEFORE that row's `entry_date`. Never on or after it."""
    left = df[["permno", "entry_date"]].copy()
    left["_row"] = np.arange(len(left))
    left["_key"] = left["entry_date"] - pd.Timedelta(days=1)
    left = left.sort_values("_key")
    right = panel.sort_values("date")
    merged = pd.merge_asof(left, right, left_on="_key", right_on="date",
                           by="permno", direction="backward",
                           tolerance=pd.Timedelta(days=15))
    out = merged.set_index("_row")["beta_pre"].sort_index()
    out.index = df.index
    return out


__all__ = ["BETA_WINDOW", "BETA_MIN_OBS", "BETA_PANEL", "build", "save", "load",
           "attach", "build_market_daily"]
