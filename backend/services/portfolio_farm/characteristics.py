"""The farm's FIRST non-price data source, joined PIT to the daily panel.

WHY THIS IS THE BOTTLENECK AND NOT "ANOTHER SIGNAL"
===================================================
`CLAUDE.md` states the bottleneck as *all ten arena books select on ONE signal
— they differ in portfolio treatment, not in alpha source*. That is true and it
understates the problem by one level. Audited 2026-08-25, every one of the
thirteen non-null signals in `signals.py` reads from exactly three quantities:

    past returns (tri/ret)   mom_12_1, mom_6_1, mom_3_1, mom_12_0,
                             reversal_1m, reversal_1w, low_vol, high_vol,
                             trend_200
    market cap (prc*shrout)  size_small, size_large
    dollar volume (prc*vol)  liquid, illiquid   (+ illiquid uses ret)

**Thirteen signals are thirteen transformations of one file.** A library like
that cannot produce an INDEPENDENT selector however many entries it gains,
because independence is a property of the data and not of the formula. Adding a
fourteenth price transformation is the expensive way to do nothing — which the
2013-2024 grid already demonstrated, with zero of thirteen resolvable and a
reality-check p of 0.358.

WHAT THIS ADDS, AND WHY THESE TWO
==================================
`finratio_monthly_early` (1990-2012) and `finratio_monthly` (2013-2024) are on
disk, PIT-stamped by WRDS's own `public_date`, and between them they cover the
whole replayable window. The early file was pulled with exactly two columns —
`bm` and `roe` — so those two are what BOTH eras can support, and a
characteristic that exists in only one era would silently change what a
1993-2024 run is measuring at the 2013 boundary.

  * **`bm`** — book-to-market. Value. Fama-French's HML, the most replicated
    cross-sectional anomaly there is after size.
  * **`roe`** — return on equity. Profitability. The RMW leg of FF5, and the
    one characteristic that has held up best out of sample since 2015.

Neither is a price transformation. `bm` does carry a price in its denominator,
so it is not fully orthogonal to the momentum family — that is a real caveat and
it is the reason `roe`, which has no price in it at all, is the cleaner test of
the proposition.

THE PIT RULE, WHICH IS THE ONLY HARD PART
==========================================
`public_date` is WRDS's own availability stamp: the date the ratio could first
have been computed by somebody outside the firm. So a value stamped
`public_date = d` may be used on a decision day **strictly after** `d`, never
on `d` itself, and never before.

The join is therefore: forward-fill each permno's monthly value onto the daily
grid with a **strict** inequality, plus a declared `LAG_SESSIONS` safety margin
on top. Both are enforced by construction — the matrix is built by searching
the sorted `public_date` list for each session and taking the last entry
STRICTLY before it — and `test_portfolio_farm_characteristics.py` plants a
value that jumps on a known date and asserts the panel cannot see it early.

`STALE_MAX_DAYS` bounds how long a value may be carried, in CALENDAR days. A
ratio from a filing eighteen months ago is not a current characteristic, and
forward-filling without a bound quietly turns a delisted-in-spirit company into
an eternal value stock. Calendar days rather than panel rows because measuring
age by row index clamps at the panel's left edge — exactly where a run's first
decisions are taken.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from backend.config import DATA_DIR

logger = logging.getLogger(__name__)

WRDS_DIR = DATA_DIR / "optimus" / "wrds"

#: The two files, and the era each covers. Both are read and concatenated: a
#: 1993-2024 run spans the boundary, and a characteristic that appears only
#: after 2013 would change what the run measures halfway through it.
SOURCES = ("finratio_monthly_early", "finratio_monthly")

#: What both eras can support. The early pull requested exactly these two, so
#: this list is a fact about the data on disk and not a modelling preference.
AVAILABLE = ("bm", "roe")

#: Extra sessions beyond the strict `public_date` inequality. `public_date` is
#: already a conservative availability stamp, so this is margin on margin — it
#: is here because the cost of being a day late is a slightly worse signal and
#: the cost of being a day early is a result that cannot be believed.
LAG_SESSIONS = 1

#: Plausibility bounds. A value outside these is dropped to NaN, not clipped.
#:
#: Both ratios have a balance-sheet quantity in the denominator, and a
#: denominator near zero produces arithmetic rather than economics. Measured on
#: `finratio_monthly` (501,601 bm values, 492,654 roe):
#:
#:     bm    median 0.50   99.9th pct  11.7   MAX  89,351
#:     roe   median 0.056  99.9th pct   8.9   MIN -21,992,  MAX 5,304
#:
#: A top-`k` book ranks by the characteristic and takes the EXTREME end, so it
#: does not merely tolerate those values — it selects them, every date, in
#: preference to every real firm. Book-to-market of 89,351 is not a company
#: trading at a thousandth of book; it is a book equity of approximately zero.
#:
#: DROPPED, not winsorised. Clipping at a percentile makes every extreme value
#: TIE at the cap, and `top_k` then falls through to the stable sort's
#: tie-break, which is permno order — so winsorising would replace "the most
#: extreme accounting artefacts" with "the oldest listings among them", which
#: is worse because it looks deliberate.
#:
#: The bounds are economic, not percentile-fitted: 20x book is deep distress
#: and 1,000% return on equity is not a business. They sit well outside the
#: 99.9th percentile of both series, so they remove the tail that is arithmetic
#: and leave the tail that is a real value or quality signal. `n_implausible`
#: is logged so the cost is visible rather than assumed.
PLAUSIBLE = {"bm": (0.0, 20.0), "roe": (-10.0, 10.0)}

#: Characteristics whose lower bound is STRICT. `bm` must be positive: zero or
#: negative book equity is a distressed accounting state, not a cheap stock,
#: and a bm of exactly 0 would sort as the most expensive name in the universe
#: rather than the most broken. Fama-French exclude negative book equity for
#: the same reason.
STRICT_LOWER = frozenset({"bm"})

#: How long a monthly value may be carried forward, in CALENDAR DAYS. Fourteen
#: months covers an annual filing plus a late quarter; beyond that the
#: "characteristic" is a memory. Without a bound, a company that stopped
#: reporting stays a value stock forever, and the names that stop reporting are
#: not a random sample.
#:
#: CALENDAR days, not panel rows. Measuring age as `row - searchsorted(stamp)`
#: silently clamps at the panel's left edge: a value published five years
#: before the window starts lands at row 0, so at row 300 it reads as 300
#: sessions old instead of ~1,560. Every panel begins with a warmup, so that
#: edge is exactly where a run's first decisions are taken.
STALE_MAX_DAYS = 425              # ~14 months


class CharacteristicUnavailable(RuntimeError):
    """The finratio parquets this join needs are not on disk."""


def available_characteristics(dir_=None) -> tuple[str, ...]:
    """Which of `AVAILABLE` are actually present in BOTH era files."""
    d = dir_ or WRDS_DIR
    have: list[set] = []
    for src in SOURCES:
        p = d / f"{src}.parquet"
        if not p.exists():
            return ()
        try:
            import pyarrow.parquet as pq
            have.append(set(pq.ParquetFile(p).schema_arrow.names))
        except Exception:                                      # noqa: BLE001
            return ()
    common = set.intersection(*have) if have else set()
    return tuple(c for c in AVAILABLE if c in common)


def load_characteristic(name: str, dates: np.ndarray, permnos: np.ndarray, *,
                        dir_=None, lag_sessions: int = LAG_SESSIONS,
                        stale_max_days: int = STALE_MAX_DAYS) -> np.ndarray:
    """(T, N) matrix of `name`, forward-filled PIT onto the panel's grid.

    NaN wherever no value was public strictly before the session, or where the
    last public value is older than `stale_max_days` CALENDAR days.
    """
    if name not in AVAILABLE:
        raise CharacteristicUnavailable(
            f"unknown characteristic {name!r}; both era files support only "
            f"{list(AVAILABLE)} (the 1990-2012 pull requested exactly those "
            f"two columns, so anything else would exist in one era and not the "
            f"other)")
    d = dir_ or WRDS_DIR
    frames = []
    for src in SOURCES:
        p = d / f"{src}.parquet"
        if not p.exists():
            raise CharacteristicUnavailable(
                f"{p} is absent, so the {name} join cannot be made PIT. This "
                f"is a REFUSAL and not a fallback to price-only: a run that "
                f"silently dropped its only non-price signal would look like a "
                f"result about that signal.")
        frames.append(pd.read_parquet(p, columns=["permno", "public_date",
                                                  name]))
    df = pd.concat(frames, ignore_index=True)
    df = df.dropna(subset=["permno", "public_date", name])
    lo, hi = PLAUSIBLE[name]
    n_before = len(df)
    low_ok = (df[name] > lo) if name in STRICT_LOWER else (df[name] >= lo)
    df = df[low_ok & (df[name] <= hi)]
    n_dropped = n_before - len(df)
    df["public_date"] = pd.to_datetime(df["public_date"]).dt.strftime("%Y-%m-%d")
    df = df.sort_values(["permno", "public_date"])
    # last value per (permno, public_date) — a duplicated stamp is a restated
    # figure, and the later row is the one that was public at that stamp
    df = df.drop_duplicates(["permno", "public_date"], keep="last")

    df["_day"] = (pd.to_datetime(df["public_date"]).astype("int64")
                  // 86_400_000_000_000)

    T, N = len(dates), len(permnos)
    out = np.full((T, N), np.nan, dtype=np.float32)
    dstr = np.asarray([str(x) for x in dates])
    # Session dates as day numbers, for the calendar-age comparison. A panel
    # date that is not parseable (the synthetic test grids use markers, not
    # dates) falls back to its row index, which makes the staleness bound inert
    # rather than wrong — the alternative is refusing to build a test panel.
    _sd = pd.to_datetime(pd.Series(dstr), errors="coerce")
    sess_days = np.where(
        _sd.notna().to_numpy(),
        (_sd.astype("int64") // 86_400_000_000_000).to_numpy(),
        np.arange(T, dtype=np.int64))
    col_of = {int(p): j for j, p in enumerate(permnos)}

    n_names = n_cells = 0
    for permno, g in df.groupby("permno", sort=False):
        j = col_of.get(int(permno))
        if j is None:
            continue
        pd_dates = g["public_date"].to_numpy()
        stamp_days = g["_day"].to_numpy(dtype=np.int64)
        vals = g[name].to_numpy(dtype=np.float64)
        # STRICTLY before: `searchsorted(..., side="left")` returns the count of
        # stamps < the session, so index-1 is the last one PUBLIC BEFORE it.
        # `side="right"` would include a stamp equal to the session date, which
        # is the off-by-one that turns a PIT join into a lookahead.
        idx = np.searchsorted(pd_dates, dstr, side="left") - 1
        ok = idx >= 0
        if not ok.any():
            continue
        rows = np.flatnonzero(ok)
        if lag_sessions:
            rows = rows[rows >= lag_sessions]
            if rows.size == 0:
                continue
            take = idx[rows - lag_sessions]
            keep = take >= 0
            rows, take = rows[keep], take[keep]
        else:
            take = idx[rows]
        if rows.size == 0:
            continue
        # staleness in CALENDAR days between the stamp and the session
        age = (sess_days[rows] - stamp_days[take])
        fresh = age <= stale_max_days
        rows, take = rows[fresh], take[fresh]
        if rows.size == 0:
            continue
        out[rows, j] = vals[take]
        n_names += 1
        n_cells += rows.size

    logger.info("portfolio_farm.characteristics: %s joined for %d of %d "
                "permnos, %.1f%% of cells populated; %d of %d source rows "
                "(%.3f%%) dropped as implausible (outside [%s, %s])",
                name, n_names, N, 100.0 * n_cells / max(1, T * N),
                n_dropped, n_before, 100.0 * n_dropped / max(1, n_before),
                lo, hi)
    return out


def coverage(mat: np.ndarray, traded: np.ndarray | None = None) -> dict:
    """How much of the panel this characteristic actually reaches.

    A signal present on 8% of traded cells is not a signal, it is a small
    sub-universe wearing one — and the farm would silently be comparing a
    500-name momentum book against a 40-name value book. Reported so the
    comparison can be made honest rather than assumed.
    """
    fin = np.isfinite(mat)
    d = {"share_of_all_cells": round(float(fin.mean()), 4)}
    if traded is not None:
        t = traded.astype(bool)
        d["share_of_traded_cells"] = round(
            float(fin[t].sum()) / max(1, int(t.sum())), 4)
        per_row = np.where(t.sum(axis=1) > 0,
                           (fin & t).sum(axis=1) / np.maximum(1, t.sum(axis=1)),
                           np.nan)
        d["min_row_share"] = round(float(np.nanmin(per_row)), 4)
        d["median_row_share"] = round(float(np.nanmedian(per_row)), 4)
    return d
