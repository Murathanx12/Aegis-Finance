"""The replay substrate: CRSP daily bars as aligned (date x permno) matrices.

SOURCE. `backend/data/optimus/wrds/crsp_dsf_<year>.parquet`, pulled 2026-08-19,
1990-2024, columns permno/date/prc/ret/retx/vol/shrout/openprc/cfacpr/cfacshr.
This is the survivorship-bias-free CRSP daily file over the 6,894-PERMNO
screened superset, and it is the only local source with an OPEN PRICE — which
is what makes a next-open fill convention executable rather than assumed.

THREE CONVENTIONS THAT ARE EASY TO GET WRONG, AND ARE WRITTEN DOWN HERE
=======================================================================

**1. `prc < 0` means NO TRADE.** CRSP stores the negated bid/ask midpoint when
a security did not trade that day. `abs(prc)` is the right price for MARKING a
position; it is the wrong price for DECIDING to buy one, because there was no
trade to join. So `close` carries `abs(prc)` and a separate `traded` mask
carries `prc > 0`, and eligibility uses the mask. Roughly 1.2% of 2020 rows.

**2. `vol` on dsf is in SHARES.** On the MONTHLY file it is in hundreds. Using
the monthly convention here would overstate dollar volume 100x and let an
illiquid name into a liquidity-screened universe.

**3. `ret` includes dividends; `retx` does not.** The difference is the cash a
holder actually received, and the simulator credits it as cash rather than
assuming reinvestment. Free reinvestment at the close is a small free lunch,
and small free lunches are how a backtest gets to a Sharpe nobody can trade.

DELISTING — THE BIAS THIS FILE CANNOT REMOVE, DECLARED
======================================================
`crsp.dsf` does not carry delisting returns (`crsp.dsedelist` does, and was not
pulled). A name that is delisted simply stops appearing. A simulator that
liquidates at the last observed close therefore books the failure at its
pre-failure price and is optimistic — the classic upward bias.

The panel does NOT paper over this. It reports `last_seen` per permno so the
simulator can detect a disappearance, and `replay.py` applies an explicit,
declared `delisting_return` (default -0.30, the Shumway (1997) order of
magnitude for performance-related NYSE/AMEX delists) to any holding that
vanishes before the end of the sample. That number is a POLICY PARAMETER, it
appears in the receipt, and a run may be repeated at 0.0 and -1.0 to bound the
sensitivity. An assumption that is visible and variable is a different object
from one that is silent.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from backend.config import DATA_DIR

logger = logging.getLogger(__name__)

WRDS_DIR = DATA_DIR / "optimus" / "wrds"
FF_DAILY = DATA_DIR.parent / "data" / "ff_daily_pinned.csv.gz"

_COLUMNS = ["permno", "date", "prc", "ret", "retx", "vol", "shrout", "openprc"]

#: Without ALL of these the simulator is a different simulator. See
#: `replayable_years` for what each one buys.
REQUIRED_COLUMNS = frozenset(_COLUMNS)


class PanelUnavailable(RuntimeError):
    """The CRSP parquet years this replay needs are not on disk."""


@dataclass(frozen=True)
class Panel:
    """Aligned matrices. Every one is (n_dates, n_permnos), float32 with NaN.

    `dates` is ISO strings, ascending. `permnos` is int64, ascending. Rows and
    columns are shared by every matrix, so `i` and `j` mean the same thing
    everywhere and no matrix needs its own index.
    """
    dates: np.ndarray            # (T,) object, ISO date strings
    permnos: np.ndarray          # (N,) int64
    close: np.ndarray            # abs(prc) — for MARKING
    open_: np.ndarray            # openprc — for FILLING
    ret: np.ndarray              # total return (incl. dividends)
    retx: np.ndarray             # capital-appreciation-only return
    traded: np.ndarray           # bool: prc > 0, i.e. a real trade happened
    dolvol: np.ndarray           # abs(prc) * vol, in dollars
    mktcap: np.ndarray           # abs(prc) * shrout * 1000, in dollars
    tri: np.ndarray              # total-return index, base 1.0 at first obs
    source: str = "crsp_dsf"

    @property
    def shape(self) -> tuple[int, int]:
        return self.close.shape

    def last_seen(self) -> np.ndarray:
        """Index of each permno's final observation. Used to tell a DELISTING
        from a data gap: a name whose last bar is before the sample end has
        left the file, and a holding in it must be resolved, not carried."""
        seen = np.where(np.isfinite(self.close), np.arange(len(self.dates))[:, None], -1)
        return seen.max(axis=0)


def available_years(dir_: Path | None = None) -> list[int]:
    """Years with a CRSP daily parquet on disk — REGARDLESS of its columns."""
    d = dir_ or WRDS_DIR
    if not d.exists():
        return []
    out = []
    for p in d.glob("crsp_dsf_*.parquet"):
        try:
            out.append(int(p.stem.rsplit("_", 1)[1]))
        except (IndexError, ValueError):
            continue
    return sorted(out)


def year_columns(year: int, dir_: Path | None = None) -> set[str]:
    """The columns one year's parquet actually contains.

    `pyarrow` is deliberately imported HERE and not at module scope: it is not
    in `backend/requirements.txt` (pandas is), so a deploy that never runs the
    farm must not fail to import a module that merely sits beside one that
    does. And the ImportError becomes a NAMED refusal rather than a guess — a
    fallback that assumed the full schema would silently run the simulator on
    a year with no open prices, which is the one thing this function exists to
    prevent.
    """
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:                                 # noqa: BLE001
        raise PanelUnavailable(
            f"pyarrow is not installed, so the CRSP parquet schema cannot be "
            f"read and no year can be certified replayable ({exc}). Install "
            f"pyarrow. This is NOT assumed-good: a year missing `openprc` "
            f"would silently change the fill convention.") from exc
    p = (dir_ or WRDS_DIR) / f"crsp_dsf_{year}.parquet"
    return set(pq.ParquetFile(p).schema_arrow.names)


def replayable_years(dir_: Path | None = None) -> list[int]:
    """Years the SIMULATOR can actually use.

    A file on disk is not a usable year. Measured 2026-08-24: the 1990-2012
    pulls carry only `permno/date/prc/ret/vol`, while 2013-2024 also carry
    `openprc`, `retx` and `shrout`. Those three are not decorations —

      * `openprc` IS the next-open fill convention. Without it the only
        executable convention is close-to-close, which books the overnight gap
        that follows the signal and flatters exactly the strategies the farm
        is searching for;
      * `retx` is what separates a dividend from a price move, and without it
        dividends are either dropped or silently reinvested for free;
      * `shrout` is market cap, so `cap_weight` sizing and any size signal
        cannot be computed.

    So a pre-2013 window is REFUSED with the missing columns named, rather
    than run on a quietly different simulator. Widening the window is a WRDS
    re-pull of those three columns, not a code change.
    """
    return [y for y in available_years(dir_)
            if REQUIRED_COLUMNS <= year_columns(y, dir_)]


def load_panel(start_year: int, end_year: int, *,
               dir_: Path | None = None) -> Panel:
    """Build the aligned panel for [start_year, end_year] inclusive.

    Refuses on a missing year rather than quietly replaying a shorter history:
    a run whose window silently shrank would produce a CAGR over a period
    nobody declared, and the receipt would name the period that was asked for.
    """
    d = dir_ or WRDS_DIR
    have = set(available_years(d))
    want = list(range(int(start_year), int(end_year) + 1))
    missing = [y for y in want if y not in have]
    if missing:
        raise PanelUnavailable(
            f"CRSP daily years absent from {d}: {missing}. Available: "
            f"{sorted(have) or 'none'}. The window is not silently shortened — "
            f"pull the years or ask for a window that exists.")
    thin = {y: sorted(REQUIRED_COLUMNS - year_columns(y, d))
            for y in want if not REQUIRED_COLUMNS <= year_columns(y, d)}
    if thin:
        usable = replayable_years(d)
        raise PanelUnavailable(
            f"these years are on disk but NOT REPLAYABLE — the pull is missing "
            f"columns the simulator's conventions depend on: {thin}. "
            f"Replayable window: {usable[0] if usable else '-'}-"
            f"{usable[-1] if usable else '-'}. Without `openprc` the fill "
            f"convention silently becomes close-to-close (which books the "
            f"overnight gap that follows the signal); without `retx` a dividend "
            f"cannot be told from a price move; without `shrout` there is no "
            f"market cap. Re-pull those columns for the missing years, or ask "
            f"for a window inside the replayable one.")

    frames = [pd.read_parquet(d / f"crsp_dsf_{y}.parquet", columns=_COLUMNS)
              for y in want]
    df = pd.concat(frames, ignore_index=True)
    del frames
    df["date"] = df["date"].astype(str)

    dates = np.array(sorted(df["date"].unique()), dtype=object)
    permnos = np.array(sorted(df["permno"].unique()), dtype=np.int64)
    di = pd.Series(np.arange(len(dates)), index=dates)
    pi = pd.Series(np.arange(len(permnos)), index=permnos)
    r = di.reindex(df["date"]).to_numpy()
    c = pi.reindex(df["permno"]).to_numpy()
    shape = (len(dates), len(permnos))

    def _mat(values, dtype=np.float32):
        m = np.full(shape, np.nan, dtype=dtype)
        m[r, c] = values
        return m

    prc = df["prc"].to_numpy(dtype=np.float64)
    close = _mat(np.abs(prc))
    traded = np.zeros(shape, dtype=bool)
    traded[r, c] = prc > 0
    open_ = _mat(df["openprc"].to_numpy(dtype=np.float64))
    ret = _mat(df["ret"].to_numpy(dtype=np.float64))
    retx = _mat(df["retx"].to_numpy(dtype=np.float64))
    dolvol = _mat(np.abs(prc) * df["vol"].to_numpy(dtype=np.float64))
    mktcap = _mat(np.abs(prc) * df["shrout"].to_numpy(dtype=np.float64) * 1000.0)

    # Total-return index. Built from `ret`, forward-filled through gaps so a
    # missing bar does not reset a momentum window to NaN — but NOT filled
    # BEFORE a name's first observation, which would invent a price history.
    r1 = np.where(np.isfinite(ret), ret, 0.0)
    tri = np.cumprod(1.0 + r1, axis=0, dtype=np.float64)
    alive = np.isfinite(close)
    first = np.argmax(alive, axis=0)
    has_any = alive.any(axis=0)
    rows = np.arange(len(dates))[:, None]
    before_birth = (rows < first[None, :]) | (~has_any[None, :])
    tri = np.where(before_birth, np.nan, tri).astype(np.float32)

    logger.info("portfolio_farm.panel: %d dates x %d permnos (%d-%d), "
                "%.0f MB", len(dates), len(permnos), start_year, end_year,
                (close.nbytes * 6) / 1e6)
    return Panel(dates=dates, permnos=permnos, close=close, open_=open_,
                 ret=ret, retx=retx, traded=traded, dolvol=dolvol,
                 mktcap=mktcap, tri=tri)


def market_benchmark(dates: np.ndarray, path: Path | None = None) -> np.ndarray:
    """CRSP value-weighted market TOTAL return per date, from the pinned FF file.

    `Mkt-RF + RF` is the market's total return. Using the PINNED copy rather
    than a live download is deliberate: a benchmark that changes when Kenneth
    French re-posts is a benchmark that re-scores every past run.

    Returns NaN for a date the file does not cover, and never 0.0 — a missing
    benchmark day must not read as a flat market.
    """
    p = path or FF_DAILY
    if not p.exists():
        return np.full(len(dates), np.nan, dtype=np.float64)
    ff = pd.read_csv(p)
    ff["Date"] = ff["Date"].astype(str)
    mkt = (ff["Mkt-RF"].astype(float) + ff["RF"].astype(float))
    s = pd.Series(mkt.to_numpy(), index=ff["Date"].to_numpy())
    s = s[~s.index.duplicated(keep="last")]
    return s.reindex(list(dates)).to_numpy(dtype=np.float64)
