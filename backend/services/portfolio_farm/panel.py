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

import json
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

#: Minimum share of a year's CRSP rows that must carry a non-null `openprc`
#: before that year is certified replayable.
#:
#: A COLUMN IS NOT DATA. The 2026-08-25 re-pull gave 1990-2012 the full schema,
#: and that alone would have flipped `replayable_years` to certify all of them
#: — while CRSP simply has no open prices before mid-1992. Measured on
#: `crsp.dsf` at the source:
#:
#:     1990   0.0%      1993  82.6%      2013  93.2%
#:     1991   0.0%      1994  82.9%      2018  97.4%
#:     1992  41.6%      1996  86.4%      2024  99.4%
#:
#: CRSP began collecting opens in mid-1992, which is why 1992 is a half-year
#: and 1990-91 are empty. The floor sits in the EMPTY GAP between 41.6% and
#: 82.6% — no year in CRSP lands between them — so its exact placement inside
#: that gap cannot change any verdict. It is declared, not fitted.
#:
#: The floor is measured over ALL rows in the file, which is deliberately
#: harsher than the population that matters: coverage inside the liquid
#: universe the farm actually trades is 100.00% in every year 2013-2024
#: (measured 2026-08-25 over the top-500-by-dollar-volume cut). Big liquid
#: names are exactly the ones CRSP has opens for. `Panel.open_coverage`
#: reports the figure that governs a given run.
OPEN_COVERAGE_FLOOR = 0.60

#: How deep the liquidity reduction keeps names, as a multiple of the trading
#: universe. The farm trades the top 500 by trailing dollar volume; keeping the
#: top 1,000 leaves a full spare universe above anything it selects.
UNIVERSE_KEEP_MULTIPLE = 2

#: The `min_price` floors the reduction is computed for. A price floor SHRINKS
#: the eligible set, so the top-500 of the survivors reaches DEEPER into the
#: dollar-volume ranking than the top-500 of everything — a reduction computed
#: at one floor is NOT valid at another, in either direction.
#:
#: Every `Policy` in the repo uses the 5.00 default and none of the presets
#: override it, so that is what is computed. Adding 0.00 "for generality" was
#: measured and dropped: it drags in penny stocks whose SHARE volume is huge
#: and whose dollar volume is not, and it cost 31% of the saving while
#: protecting a configuration nothing uses. A policy with any other floor is
#: REFUSED by `replay` rather than replayed on the wrong universe — the
#: assumption is enforced, not documented.
REDUCTION_MIN_PRICES = (5.0,)


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
    #: (N,) MEASURED delisting return per permno from `crsp.dsedelist`, NaN
    #: where CRSP has no event or no `dlret`. Applied by `replay` at the moment
    #: a holding is resolved; the declared `policy.delisting_return` is the
    #: fallback for the NaNs, and the split is counted on every receipt.
    delist_ret: np.ndarray | None = None
    #: (N,) the delisting CODE, for auditing which population a run resolved.
    delist_code: np.ndarray | None = None
    #: MEASURED share of tradeable cells (a real trade at the close) that also
    #: carry a usable positive open. This is the fill convention's own coverage
    #: on THIS window, and it belongs on the receipt: a run whose decisions
    #: cannot be executed is not the strategy that was declared, it is
    #: "hold whatever could not be sold". Negative opens count as MISSING —
    #: CRSP's sign convention marks a bid/ask midpoint on a no-trade day, and
    #: `replay` refuses to fill at one.
    open_coverage: float = float("nan")
    #: When the panel was built from a LIQUIDITY-REDUCED permno set, the
    #: universe depth that reduction is valid for, and the price floors it was
    #: computed at. None means every permno in the files is present.
    universe_reduced_to: int | None = None
    reduction_min_prices: tuple = ()
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


def year_open_coverage(year: int, dir_: Path | None = None) -> float:
    """Share of a year's rows carrying a non-null `openprc`, from PARQUET
    STATISTICS rather than from the data.

    Row-group `null_count` is exact and costs one metadata read, so this can
    gate every year on every call without loading a column. It cannot see the
    SIGN (CRSP writes a negative open for a bid/ask midpoint on a no-trade
    day), so it is an upper bound on usable coverage — which is the right
    direction for a gate whose job is to catch an EMPTY column, and why
    `Panel.open_coverage` measures the signed truth on the loaded window.
    """
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:                                 # noqa: BLE001
        raise PanelUnavailable(
            f"pyarrow is not installed, so `openprc` coverage cannot be "
            f"measured and no year can be certified replayable ({exc})."
        ) from exc
    f = pq.ParquetFile((dir_ or WRDS_DIR) / f"crsp_dsf_{year}.parquet")
    names = f.schema_arrow.names
    if "openprc" not in names:
        return 0.0
    j = names.index("openprc")
    total = nulls = 0
    md = f.metadata
    for g in range(md.num_row_groups):
        col = md.row_group(g).column(j)
        if not col.is_stats_set:
            # No statistics is NOT "no nulls". Fall back to reading the one
            # column rather than certifying a year on absent evidence.
            arr = f.read(columns=["openprc"]).column("openprc")
            return 1.0 - (arr.null_count / max(1, len(arr)))
        # `num_values` on a column chunk ALREADY counts nulls. Adding
        # null_count to it inflated the denominator and reported 66.7% for a
        # column that was half empty — caught by this module's own test before
        # it could certify a year it should have refused.
        total += col.num_values
        nulls += col.statistics.null_count
    return 1.0 - (nulls / max(1, total))


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
            if REQUIRED_COLUMNS <= year_columns(y, dir_)
            and year_open_coverage(y, dir_) >= OPEN_COVERAGE_FLOOR]


def liquid_permnos(start_year: int, end_year: int, *,
                   universe_n: int = 500,
                   keep_multiple: int = UNIVERSE_KEEP_MULTIPLE,
                   dir_: Path | None = None,
                   cache: bool = True) -> tuple[np.ndarray, dict]:
    """PERMNOs that could ever enter a `universe_n` book, and the receipt.

    WHY THIS EXISTS
    ===============
    The panel is dense: every matrix is (dates x permnos), so a permno that is
    never traded still costs a full column. Over 2013-2024 that was tolerable.
    Over 1993-2024 it is not — the two PIT universe files union to 18,691
    permnos across 8,064 sessions, which is 0.6 GB per float32 matrix and
    ~4.8 GB for the eight the `Panel` carries, before the pandas frame that
    builds them.

    And it is nearly all waste. Measured 2026-08-25 over 2013-2024: only
    **1,967 of 6,894 permnos (28.5%) ever reach the top 500** by trailing
    dollar volume, and 3,323 (48.2%) ever reach the top 1,000. The farm cannot
    hold a name it never selects, so those columns are arithmetic on NaN.

    WHY IT DOES NOT CHANGE AN ANSWER
    ================================
    The kept set is computed with the SAME criterion `replay` uses to build its
    eligible set — `traded & finite(close) & close >= min_price & finite(
    trailing 21-day mean dollar volume)`, ranked by that mean — at each
    `REDUCTION_MIN_PRICES` floor, and kept to `universe_n * keep_multiple`
    deep. A name outside it was never in the top `universe_n` on any date at
    any of those floors, so no book could have contained it.

    This is the same restriction `portfolio_farm_universe_audit` already
    cleared, one step tighter and now EXACT rather than argued: that audit
    showed the PIT superset's $100M/month bar could not bind because the
    farm's 500th name trades 15.4x it. Here the cut is measured against the
    farm's own criterion instead of a proxy for it.

    WHAT IT IS NOT
    ==============
    It is not point-in-time. Deciding which columns to materialise uses the
    whole window, exactly as the PIT superset's construction does. That is
    sound for a MEMBERSHIP question and would not be sound for a signal: the
    reduction can only ever remove names the policy provably would not have
    held, and `universe_reduced_to` makes the assumption refuse rather than
    hide when a later policy asks for a deeper universe.

    Returns `(permnos, receipt)`. The receipt carries the deepest rank any
    date's selection actually reached, which is the number that proves the
    headroom was real rather than assumed.
    """
    d = dir_ or WRDS_DIR
    keep_n = int(universe_n * keep_multiple)
    tag = f"{start_year}_{end_year}_u{universe_n}x{keep_multiple}"
    cache_path = d / f"farm_universe_{tag}.json"
    if cache and cache_path.exists():
        try:
            blob = json.loads(cache_path.read_text(encoding="utf-8"))
            return np.array(blob["permnos"], dtype=np.int64), blob["receipt"]
        except Exception:                                      # noqa: BLE001
            pass

    from backend.services.portfolio_farm import signals as SIG

    keep: set[int] = set()
    deepest = 0
    n_dates = 0
    # One year at a time, with the PRIOR year's tail for the trailing window —
    # a rolling mean computed per calendar year would reset every January and
    # rank names by a partial window for the first month of each.
    for y in range(int(start_year), int(end_year) + 1):
        years = [y - 1, y] if (d / f"crsp_dsf_{y-1}.parquet").exists() else [y]
        fr = [pd.read_parquet(d / f"crsp_dsf_{yy}.parquet",
                              columns=["permno", "date", "prc", "vol"])
              for yy in years]
        df = pd.concat(fr, ignore_index=True)
        df["date"] = df["date"].astype(str)
        dates = np.array(sorted(df["date"].unique()), dtype=object)
        permnos = np.array(sorted(df["permno"].unique()), dtype=np.int64)
        di = pd.Series(np.arange(len(dates)), index=dates)
        pi = pd.Series(np.arange(len(permnos)), index=permnos)
        r = di.reindex(df["date"]).to_numpy()
        c = pi.reindex(df["permno"]).to_numpy()
        shape = (len(dates), len(permnos))
        prc = df["prc"].to_numpy(dtype=np.float64)
        close = np.full(shape, np.nan, dtype=np.float64)
        close[r, c] = np.abs(prc)
        traded = np.zeros(shape, dtype=bool)
        traded[r, c] = prc > 0
        dv = np.full(shape, np.nan, dtype=np.float64)
        dv[r, c] = np.abs(prc) * df["vol"].to_numpy(dtype=np.float64)
        del df, fr
        liq = SIG._roll_mean(dv, SIG.MONTH, 5)

        in_year = np.array([str(x)[:4] == str(y) for x in dates])
        for i in np.flatnonzero(in_year):
            n_dates += 1
            for floor in REDUCTION_MIN_PRICES:
                elig = (traded[i] & np.isfinite(close[i])
                        & (close[i] >= floor) & np.isfinite(liq[i]))
                cand = np.flatnonzero(elig)
                if cand.size == 0:
                    continue
                order = cand[np.argsort(-liq[i][cand], kind="stable")]
                keep.update(int(x) for x in permnos[order[:keep_n]])
                deepest = max(deepest, min(cand.size, universe_n))
        del close, traded, dv, liq

    out = np.array(sorted(keep), dtype=np.int64)
    receipt = {
        "window": [int(start_year), int(end_year)],
        "universe_n": int(universe_n),
        "keep_multiple": int(keep_multiple),
        "kept_to_rank": keep_n,
        "deepest_selection_rank_observed": int(deepest),
        "min_prices": list(REDUCTION_MIN_PRICES),
        "n_permnos_kept": int(out.size),
        "n_dates_scanned": int(n_dates),
        "headroom": (f"selection never went deeper than rank {deepest}; the "
                     f"panel keeps to rank {keep_n}"),
    }
    if cache:
        try:
            cache_path.write_text(json.dumps(
                {"permnos": [int(x) for x in out], "receipt": receipt},
                indent=1), encoding="utf-8")
        except Exception:                                      # noqa: BLE001
            pass
    return out, receipt


def load_panel(start_year: int, end_year: int, *,
               dir_: Path | None = None,
               restrict_to: np.ndarray | None = None,
               reduce_for_universe_n: int | None = None) -> Panel:
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

    # A column that exists and is empty is the failure the re-pull created and
    # the schema check cannot see. Reported as its own refusal because the fix
    # is different: an absent column is a re-pull, an empty one is a year CRSP
    # does not have and never will.
    empty = {y: round(c, 4) for y in want
             for c in [year_open_coverage(y, d)] if c < OPEN_COVERAGE_FLOOR}
    if empty:
        raise PanelUnavailable(
            f"these years carry an `openprc` COLUMN that is (nearly) empty, so "
            f"the next-open fill convention is not executable in them: "
            f"{empty} (floor {OPEN_COVERAGE_FLOOR:.0%}). CRSP began collecting "
            f"open prices in mid-1992 — 1990 and 1991 have none at all and no "
            f"pull can produce them. This is NOT the same refusal as a missing "
            f"column: there is nothing to re-pull. Ask for a window starting "
            f"at {min(replayable_years(d)) if replayable_years(d) else 1993}.")

    reduced_to = None
    if reduce_for_universe_n is not None and restrict_to is None:
        restrict_to, _rec = liquid_permnos(
            start_year, end_year, universe_n=reduce_for_universe_n, dir_=d)
        reduced_to = _rec["kept_to_rank"]
        logger.info("portfolio_farm.panel: liquidity reduction keeps %d "
                    "permnos to rank %d (deepest selection observed: %d)",
                    _rec["n_permnos_kept"], reduced_to,
                    _rec["deepest_selection_rank_observed"])

    keep = None if restrict_to is None else set(int(x) for x in restrict_to)
    frames = []
    for y in want:
        f = pd.read_parquet(d / f"crsp_dsf_{y}.parquet", columns=_COLUMNS)
        if keep is not None:
            f = f[f["permno"].isin(keep)]
        frames.append(f)
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
    # The fill convention's coverage on THIS window, over cells where a trade
    # actually happened — the only population whose decisions could be filled.
    _fillable = np.isfinite(open_) & (open_ > 0)
    _n_trade = int(traded.sum())
    open_cov = float(_fillable[traded].sum()) / max(1, _n_trade)
    logger.info("portfolio_farm.panel: openprc usable on %.2f%% of traded "
                "cells (%d-%d)", 100.0 * open_cov, start_year, end_year)

    dl_ret, dl_code = load_delisting(permnos)
    n_known = int(np.isfinite(dl_ret).sum())
    logger.info("portfolio_farm.panel: measured delisting returns for %d of %d "
                "permnos (%.1f%%); the rest fall back to the declared "
                "assumption", n_known, len(permnos),
                100.0 * n_known / max(1, len(permnos)))
    return Panel(dates=dates, permnos=permnos, close=close, open_=open_,
                 ret=ret, retx=retx, traded=traded, dolvol=dolvol,
                 mktcap=mktcap, tri=tri, delist_ret=dl_ret,
                 delist_code=dl_code, open_coverage=open_cov,
                 universe_reduced_to=reduced_to,
                 reduction_min_prices=(REDUCTION_MIN_PRICES
                                       if reduced_to else ()))


#: `crsp.dsedelist`, already on disk in the WRDS bulk pull. Nobody had joined
#: it: the farm's first three presets ran with a DECLARED -30% for every exit,
#: and the sensitivity sweep showed that assumption was worth an 18x swing in
#: terminal wealth. It did not need a pull. It needed somebody to look.
DELIST_PATH = DATA_DIR / "optimus" / "wrds" / "bulk" / "crsp__dsedelist.parquet"

#: `dlstcd` 100 means the security is STILL ACTIVE — those rows are not
#: delistings and joining them would resolve live positions. 2013-2024 holds
#: 3,866 of them against 3,089 real events, so this filter is not a detail.
DELIST_MIN_CODE = 200


def load_delisting(permnos: np.ndarray, *, path: Path | None = None) -> tuple:
    """(delist_ret, delist_code) aligned to `permnos`. NaN where CRSP is silent.

    WHAT THE DATA SAYS, measured 2013-2024 over 3,089 real events:

      * `2xx` MERGERS, 1,962 events — `dlret` median **+0.0004**, mean +0.0089.
        A merged shareholder receives the deal consideration, so the return
        from the last trade is ~zero. Applying -30% to these is simply wrong.
      * `5xx` DROPPED / performance, 891 events — median **-0.20**, mean -0.244.
        This is the population the -30% convention comes from.
      * `4xx` liquidations, 223 — median +0.0005.
      * Overall: median **0.0000**, mean **-0.0636**, 60.5% at or above zero.

    So the blanket -30% default was far too harsh, and the correction is not a
    tweak: it moves the same rule across the market benchmark.

    NOT LOOKAHEAD. The value is keyed by permno and consumed only at the moment
    a holding is resolved, which is at or after `dlstdt`. It is what the holder
    receives, on the day they receive it.
    """
    n = len(permnos)
    ret = np.full(n, np.nan, dtype=np.float64)
    code = np.full(n, np.nan, dtype=np.float64)
    p = path or DELIST_PATH
    if not p.exists():
        logger.warning(
            "portfolio_farm.panel: %s absent — every exit will fall back to the "
            "DECLARED policy.delisting_return, which the sensitivity sweep "
            "showed is worth an 18x swing in terminal wealth. This is a lower "
            "bound on fidelity, not a detail.", p)
        return ret, code
    df = pd.read_parquet(p, columns=["permno", "dlstcd", "dlret"])
    df = df[df["dlstcd"] >= DELIST_MIN_CODE]
    # A permno can appear more than once; keep the LAST event, which is the one
    # that ends its life in the file.
    df = df.drop_duplicates(subset="permno", keep="last").set_index("permno")
    idx = pd.Index(permnos)
    ret[:] = df["dlret"].reindex(idx).to_numpy(dtype=np.float64)
    code[:] = df["dlstcd"].reindex(idx).to_numpy(dtype=np.float64)
    return ret, code


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
