"""Sell-side analyst state: the farm's THIRD data source, and its first about
what people SAID rather than what prices did.

WHY THIS IS THE HIGHEST-VALUE JOIN AVAILABLE
============================================
The stated bottleneck is `independent selector count = 1`. Thirteen of the
farm's signals were thirteen transformations of `crsp.dsf` (past returns,
market cap, dollar volume); `characteristics.py` added accounting ratios as the
second source. This is the third, and it is different in kind from both: it is
a record of ANALYST BEHAVIOUR, which is neither a price nor a filing.

The unadjusted `statsumu_epsus` pull (1985-2026, US firms) covers the whole
1993-2024 replayable window; `ibes_pit_consensus` links it to permno with the
same rule the old adjusted pull used. See THE SHARE BASIS below.

WHAT IT MEASURES, AND WHY NOT JUST `numup - numdown`
====================================================
The obvious signal is revision breadth, and it is a good one. It is also not
the whole state, and the literature is clear that combining revision channels
carries more than any single channel does. So this module registers the
components SEPARATELY and a composite on top of them, because a composite whose
parts are invisible is the `arena_composite` mistake — that book declared six
weights and turned out to be 12-1 momentum for 99.5% of names, and nobody could
see it because only the composite was ever reported.

    rev_breadth     (numup - numdown) / numest
                    Direction and intensity in one number. No denominator
                    pathology: numest >= MIN_ESTIMATES by construction.

                    IT IS NOT BOUNDED BY 1. `numup`/`numdown` are a FLOW —
                    revisions filed during the period — and `numest` is a
                    STOCK, the estimates standing now. An analyst may revise
                    twice, and revising analysts may since have dropped
                    coverage, so 12 up-revisions against 7 standing estimates
                    is real data and not an error. Assuming otherwise cost
                    16,024 of the most-revised observations before
                    `portfolio_farm_calibrate` measured it.

    rev_magnitude   (meanest - meanest_prev) / max(|meanest_prev|, FLOOR)
                    HOW MUCH the consensus moved, not merely which way. Two
                    analysts nudging by a cent is not one analyst cutting by
                    half, and breadth scores them identically.

    rev_dispersion  -stdev / max(|meanest|, FLOOR)
                    NEGATED, so high = agreement. Disagreement among analysts
                    is a well-documented NEGATIVE predictor, so the sign is
                    declared here rather than discovered later.

    sell_side_state z(breadth) + z(magnitude) + z(dispersion), equal-weighted
                    cross-sectionally each date.

THE PIT RULE
============
`statpers` is IBES's statistical-period stamp: the cut-off at which that
month's consensus was compiled. A value stamped `statpers = d` may be used on a
session STRICTLY AFTER `d`, never on `d` itself. That is enforced by
`characteristics.join_pit_series`, which is imported rather than reimplemented
precisely so this module cannot get `side="left"` wrong — one lookahead
character would improve every number here and raise nothing.

`LAG_SESSIONS` adds margin on top. IBES compiles at `statpers` and distributes
shortly after, so a same-week decision is the one plausible place to be too
early.

THE SHARE BASIS (rewritten 2026-11-11 -- this was a look-ahead leak)
=====================================================================
Until 2026-11-11 this module read `ibes_consensus_monthly{,_early}`, the
SPLIT-ADJUSTED summary: every historical value restated in today's shares and
rounded to cents. A firm that later split 56x read meanest 0.01 / stdev 0.00
years earlier, so `rev_dispersion` scored future splitters -- future winners --
as unanimous and became the best signal ever measured here (+0.94%/mo vs twin,
t 6.3; farm $193k vs a $24.6k market) on a leak. A first fix (PR #94) dropped
rows whose ADJUSTED level was below $0.25; review 3 showed that guard is itself
chosen on a future quantity (the later split factor) and selects against future
splitters. Both are gone.

The consensus is now read AS QUOTED at `statpers` from the unadjusted
`statsumu_epsus` pull through `backend.services.ibes_pit_consensus`, so
`stdev`, `meanest` and their ratio are what a reader saw that month, on that
month's share basis. `rev_magnitude` compares two months on ONE basis: the
earlier value is restated in the later month's shares with IBES's own split
factors (the split that HAPPENED in between, known at the later date). The
definitions and the `FLOOR` are the original ones; only the input changed.
`rev_breadth` counts analysts and was never affected.

Still declared, not repaired: `meanest_prev` may describe the previous fiscal
year across a FY1 roll (the module has always compared consecutive FY1 rows).
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from backend.config import DATA_DIR

from .characteristics import join_pit_series

logger = logging.getLogger(__name__)

WRDS_DIR = DATA_DIR / "optimus" / "wrds"

#: The split-ADJUSTED files this module read until 2026-11-11. Kept only so
#: `_load_adjusted_diagnostic` can reproduce the leak on purpose; `derive`
#: refuses their rows (no `share_basis`).
SOURCES = ("ibes_consensus_monthly_early", "ibes_consensus_monthly")

#: FY1 annual EPS consensus. `fpi='1'` is the twelve-month-forward fiscal year,
#: which is the horizon the revision literature uses and the one with the most
#: analyst coverage. `'2'` is FY2, `'6'` the next quarter, `'0'` long-term
#: growth — all present on disk, none of them this signal.
MEASURE, FPI = "EPS", "1"

#: Derived quantities this module can serve, and the SIGN each is registered
#: with. Declared here so the direction is a decision on the record rather
#: than something read off a result afterwards.
AVAILABLE = ("rev_breadth", "rev_magnitude", "rev_dispersion")

#: Extra sessions beyond the strict `statpers` inequality.
LAG_SESSIONS = 1

#: Denominator floor, in dollars per share. Summary EPS estimates are ROUNDED,
#: so a consensus of $0.02 moving to $0.03 is a 50% "revision" that is mostly
#: rounding. Ten cents is well below the 25th percentile of |meanest| (~$0.20)
#: and well above the rounding grid.
FLOOR = 0.10

#: Plausibility bounds, DROPPED not clipped — the same rule and the same
#: reason as `characteristics.PLAUSIBLE`. A top-k book ranks by the value and
#: takes the extreme end, so it does not merely tolerate an artefact, it
#: selects one every date in preference to every real firm.
#:
#: `meanest` on the early file runs from -9.75e8 to +4.8e9 against a median of
#: $0.73 — currency-unit and data errors, not companies.
PLAUSIBLE = {
    # NOT (-1, 1). `numup`/`numdown` are a FLOW — revisions filed during the
    # period — while `numest` is a STOCK, the estimates standing now. An
    # analyst may revise twice, and analysts who revised may since have dropped
    # coverage, so the ratio legitimately exceeds 1.
    #
    # MEASURED 2026-08-25 over 1,051,457 rows: 1.52% exceed |1|, 0.025% exceed
    # |2|, and NOTHING exceeds |5|. A (-1, 1) bound therefore dropped 16,024
    # rows — and not a random 1.5%, but precisely the names with the most
    # revision activity, which are the most informative observations the signal
    # has. Caught by `portfolio_farm_calibrate` on its first run; it was my own
    # bug, asserted from the formula rather than measured from the data.
    #
    # 5.0 is a genuine implausibility bound (zero rows) rather than a data cut.
    "rev_breadth": (-5.0, 5.0),
    "rev_magnitude": (-2.0, 2.0),      # a consensus that moved 200% in a month
    "rev_dispersion": (-10.0, 0.0),    # negated, so at most 0
}

#: How long a monthly value may be carried, in CALENDAR days. IBES compiles
#: monthly, so anything older than ~10 weeks means coverage was dropped — and
#: a company analysts stopped covering is not a company with a stale revision,
#: it is a company with no analyst state at all.
STALE_MAX_DAYS = 75

#: A name needs at least this many estimates for a consensus to mean anything.
#: One analyst's revision is not a consensus revision, and `numest=1` is the
#: 25th percentile of the file.
MIN_ESTIMATES = 3


class RevisionsUnavailable(RuntimeError):
    """The IBES consensus parquets this join needs are not on disk."""


def _pit_paths(dir_=None):
    """(statsumu, link, adj). `dir_`, when given, holds `statsumu_epsus.parquet`,
    `ibcrsphist.parquet` and `ibes__adj.parquet` (tests and audits); otherwise
    the config paths."""
    from pathlib import Path

    from backend.services import ibes_pit_consensus as PIT
    if dir_ is not None:
        d = Path(dir_)
        return d / "statsumu_epsus.parquet", d / "ibcrsphist.parquet", d / "ibes__adj.parquet"
    return PIT.statsumu_path(), PIT.link_path(), PIT.adj_factors_path()


def available(dir_=None) -> tuple[str, ...]:
    """Whether the as-quoted consensus, its link and the split factors are all
    present. Empty tuple when any is not (no fallback to the adjusted file)."""
    need = {"ticker", "statpers", "measure", "fpi", "numest", "numup",
            "numdown", "meanest", "stdev"}
    s, lk, adj = _pit_paths(dir_)
    if not (s.exists() and lk.exists() and adj.exists()):
        return ()
    try:
        import pyarrow.parquet as pq
        if not need <= set(pq.ParquetFile(s).schema_arrow.names):
            return ()
    except Exception:                                          # noqa: BLE001
        return ()
    return AVAILABLE


def _finish(df: pd.DataFrame) -> pd.DataFrame:
    df = df[(df["measure"].astype(str) == MEASURE) & (df["fpi"].astype(str) == FPI)]
    df = df.dropna(subset=["permno", "statpers", "numest"])
    df = df[df["numest"] >= MIN_ESTIMATES].copy()
    df["statpers"] = pd.to_datetime(df["statpers"]).dt.strftime("%Y-%m-%d")
    df = df.sort_values(["permno", "statpers"], kind="mergesort")
    # A duplicated (permno, statpers) is a restatement; the later row is what
    # was on the tape at that stamp.
    return df.drop_duplicates(["permno", "statpers"], keep="last")


def _load_raw(dir_=None) -> pd.DataFrame:
    """The FY1 EPS consensus AS QUOTED at statpers, with `adj_factor` and
    `share_basis`. Refuses when the unadjusted file, its link or the split
    factors are absent -- never a fallback to the split-adjusted file."""
    from backend.services import ibes_pit_consensus as PIT
    s, lk, adj = _pit_paths(dir_)
    for p, what in ((s, "unadjusted IBES summary"), (lk, "IBES-CRSP link"),
                    (adj, "IBES split factors (ibes.adj)")):
        if not p.exists():
            raise RevisionsUnavailable(
                f"{what} is absent at {p}, so the analyst-revision join cannot be "
                f"made PIT. This is a REFUSAL and not a fallback: the split-adjusted "
                f"file is a look-ahead leak for levels and dispersion, and a run that "
                f"silently dropped its only behavioural signal would look like a "
                f"result about that signal.")
    raw = pd.read_parquet(s, columns=list(PIT.CONSENSUS_COLUMNS))
    link = pd.read_parquet(lk)
    factors = pd.read_parquet(adj, columns=["ticker", "spdates", "adj"])
    return _finish(PIT.from_frames(raw, link, factors, fpi=FPI))


def _load_adjusted_diagnostic(dir_=None) -> pd.DataFrame:
    """The PRE-2026-11-11 loader (split-adjusted, cents). For reproducing the
    leak only: its rows carry no `share_basis`, so `derive` refuses them."""
    d = dir_ or WRDS_DIR
    cols = ["permno", "statpers", "measure", "fpi", "numest", "numup",
            "numdown", "meanest", "stdev"]
    frames = []
    for src in SOURCES:
        p = d / f"{src}.parquet"
        if not p.exists():
            raise RevisionsUnavailable(f"{p} is absent")
        frames.append(pd.read_parquet(p, columns=cols))
    return _finish(pd.concat(frames, ignore_index=True))


def derive(df: pd.DataFrame) -> pd.DataFrame:
    """Add the three derived columns. Pure, so it is testable without WRDS.

    `df` must be AS QUOTED (`share_basis` stamped by `ibes_pit_consensus`) and
    carry `adj_factor`; anything else is refused (ValueError). A frame whose
    split factors are ALL unknown refuses too (RevisionsUnavailable): a
    magnitude across an unknown split is basis-mixed, never a number.
    """
    from backend.services.ibes_pit_consensus import require_as_quoted
    require_as_quoted(df, who="portfolio_farm.revisions.derive")
    if "adj_factor" not in df.columns:
        raise RevisionsUnavailable("derive: no `adj_factor` column; a revision "
                                   "across a split cannot be put on one basis")
    out = df.copy()
    numest = out["numest"].to_numpy(dtype=np.float64)
    up = out["numup"].to_numpy(dtype=np.float64)
    dn = out["numdown"].to_numpy(dtype=np.float64)
    with np.errstate(invalid="ignore", divide="ignore"):
        out["rev_breadth"] = (up - dn) / np.maximum(numest, 1.0)

    # PREVIOUS value per permno. `groupby.shift` respects the sort and never
    # reaches across names — a plain `.shift()` here would carry the last
    # company's consensus onto the first row of the next one.
    g = out.groupby("permno", sort=False)
    prev = g["meanest"].shift(1).to_numpy(dtype=np.float64)
    a_prev = g["adj_factor"].shift(1).to_numpy(dtype=np.float64)
    a_now = out["adj_factor"].to_numpy(dtype=np.float64)
    if len(out) and not np.isfinite(a_now).any():
        raise RevisionsUnavailable(
            "derive: every split factor is unknown (ibes.adj absent or unmatched); "
            "rev_magnitude would mix share bases across splits")
    me = out["meanest"].to_numpy(dtype=np.float64)
    sd = out["stdev"].to_numpy(dtype=np.float64)
    with np.errstate(invalid="ignore", divide="ignore"):
        # the earlier month restated in THIS month's shares (the split between them)
        pv = prev * (a_now / a_prev)
        out["rev_magnitude"] = (me - pv) / np.maximum(np.abs(pv), FLOOR)
        out["rev_dispersion"] = -(sd / np.maximum(np.abs(me), FLOOR))
    return out


def load_revision(name: str, dates: np.ndarray, permnos: np.ndarray, *,
                  dir_=None, lag_sessions: int = LAG_SESSIONS,
                  stale_max_days: int = STALE_MAX_DAYS,
                  df: pd.DataFrame | None = None) -> np.ndarray:
    """(T, N) matrix of `name`, forward-filled PIT onto the panel's grid."""
    if name not in AVAILABLE:
        raise RevisionsUnavailable(
            f"unknown revision signal {name!r}; this module serves "
            f"{list(AVAILABLE)}")
    d = derive(_load_raw(dir_)) if df is None else df
    sub = d.dropna(subset=[name])
    lo, hi = PLAUSIBLE[name]
    n_before = len(sub)
    sub = sub[(sub[name] >= lo) & (sub[name] <= hi)]
    n_dropped = n_before - len(sub)

    mat, rcpt = join_pit_series(sub, name, "statpers", dates, permnos,
                                lag_sessions=lag_sessions,
                                stale_max_days=stale_max_days)
    logger.info("portfolio_farm.revisions: %s joined for %d of %d permnos, "
                "%.1f%% of cells populated; %d of %d source rows (%.3f%%) "
                "dropped as implausible (outside [%s, %s])",
                name, rcpt["n_names"], len(permnos),
                100.0 * rcpt["share_of_cells"], n_dropped, n_before,
                100.0 * n_dropped / max(1, n_before), lo, hi)
    return mat


def load_all(dates: np.ndarray, permnos: np.ndarray, *, dir_=None,
             **kw) -> dict:
    """Every derived revision matrix, from ONE read of the source files.

    `load_revision` re-reads 5M rows per call; a panel build that wants all
    three would pay that three times. The farm builds panels inside sweeps, so
    that cost is the difference between a runnable battery and an unrunnable
    one — the same reason `characteristics` joins once at panel-build time.
    """
    d = derive(_load_raw(dir_))
    return {n: load_revision(n, dates, permnos, dir_=dir_, df=d, **kw)
            for n in AVAILABLE}
