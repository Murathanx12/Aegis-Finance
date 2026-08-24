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

`STALE_MAX_SESSIONS` bounds how long a value may be carried. A ratio from a
filing eighteen months ago is not a current characteristic, and forward-filling
without a bound quietly turns a delisted-in-spirit company into an eternal
value stock.
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

#: How long a monthly value may be carried forward. Fourteen months covers an
#: annual filing plus a late quarter; beyond that the "characteristic" is a
#: memory. Without a bound, a company that stopped reporting stays a value
#: stock forever, and the names that stop reporting are not a random sample.
STALE_MAX_SESSIONS = 294          # ~14 months of sessions


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
                        stale_max: int = STALE_MAX_SESSIONS) -> np.ndarray:
    """(T, N) matrix of `name`, forward-filled PIT onto the panel's grid.

    NaN wherever no value was public strictly before the session, or where the
    last public value is older than `stale_max` sessions.
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
    df["public_date"] = pd.to_datetime(df["public_date"]).dt.strftime("%Y-%m-%d")
    df = df.sort_values(["permno", "public_date"])
    # last value per (permno, public_date) — a duplicated stamp is a restated
    # figure, and the later row is the one that was public at that stamp
    df = df.drop_duplicates(["permno", "public_date"], keep="last")

    T, N = len(dates), len(permnos)
    out = np.full((T, N), np.nan, dtype=np.float32)
    dstr = np.asarray([str(x) for x in dates])
    col_of = {int(p): j for j, p in enumerate(permnos)}

    n_names = n_cells = 0
    for permno, g in df.groupby("permno", sort=False):
        j = col_of.get(int(permno))
        if j is None:
            continue
        pd_dates = g["public_date"].to_numpy()
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
        # staleness, measured in SESSIONS of this panel
        stamp_row = np.searchsorted(dstr, pd_dates[take], side="left")
        fresh = (rows - stamp_row) <= stale_max
        rows, take = rows[fresh], take[fresh]
        if rows.size == 0:
            continue
        out[rows, j] = vals[take]
        n_names += 1
        n_cells += rows.size

    logger.info("portfolio_farm.characteristics: %s joined for %d of %d "
                "permnos, %.1f%% of cells populated", name, n_names, N,
                100.0 * n_cells / max(1, T * N))
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
