"""The IBES EPS consensus AS QUOTED at `statpers` -- the only honest source of LEVELS.

WHY THIS MODULE EXISTS (2026-11-11)
===================================
`backend/data/optimus/wrds/ibes_consensus_monthly[_early].parquet` was pulled from
`ibes.statsum_epsus`, the SPLIT-ADJUSTED summary: every historical value is restated
in today's share terms and rounded to cents. Apple's FY1 consensus on 2004-01-15 was
0.46 with stdev 0.03 over 17 estimates (`statsumu_epsus`, unadjusted); the adjusted
file reads 0.01 / 0.00, because Apple later split 56x. A firm that splits many times
LATER is, disproportionately, a firm that went up -- so a near-zero level and a zero
spread in the adjusted file are a forecast of future returns that nobody could see at
the time. "Low analyst dispersion" built on it looked like the best signal ever
measured here (farm +0.94%/mo vs twin, t 6.3; Book G Amendment 1 +1.19%/mo, t 6.07)
and is a look-ahead leak (`night-backtests` report, PR #94).

Ratios of two adjusted values (a revision, a CV) cancel the share basis but NOT the
rounding: 0.01 -> 0.02 reads as +100%. Breadth counts (numest/numup/numdown) are
unaffected by either. So every consumer of a consensus LEVEL or DISPERSION reads this
module, which loads the unadjusted `statsumu_epsus` pull and

* keys it to CRSP permno with the same link rule the adjusted pull used
  (`ibcrsphist`, score <= IBES_LINK_MAX_SCORE, statpers inside the link window);
* stamps every row `share_basis = AS_QUOTED`, which `book_signals.forecast_dispersion`
  requires, so a frame from the adjusted file is REFUSED rather than ranked;
* attaches `adj_factor`, IBES's own split factor in effect on `statpers`
  (`ibes.adj`), so a revision across a split can be put on one basis
  (`rebased_revision`). The factor of an earlier date relative to a later one is the
  split that HAPPENED between them -- known at the later date -- never a future one.

It refuses (raises `IbesUnadjustedUnavailable`) when the unadjusted file is absent, and
there is no fallback to the adjusted file: a silent fallback is how the leak would come
back. The file is licensed WRDS data and lives outside the repo (config
`IBES_STATSUMU_EPSUS_PATH`); CI exercises this module on synthetic fixtures only.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from backend import config as _config

#: The value every row loaded here carries in `share_basis`.
AS_QUOTED = "as_quoted_at_statpers"

#: Columns read from the unadjusted summary.
CONSENSUS_COLUMNS = ("ticker", "statpers", "fpi", "measure", "numest", "numup",
                     "numdown", "meanest", "medest", "stdev", "fpedats")


class IbesUnadjustedUnavailable(FileNotFoundError):
    """The unadjusted IBES summary (or its link file) is not on this machine."""


def statsumu_path() -> Path:
    return Path(_config.IBES_STATSUMU_EPSUS_PATH)


def link_path() -> Path:
    return Path(_config.IBES_STATSUMU_LINK_PATH)


def adj_factors_path() -> Path:
    return Path(_config.IBES_ADJ_FACTORS_PATH)


def _require(p: Path, what: str) -> Path:
    if not p.is_file():
        raise IbesUnadjustedUnavailable(
            f"{what} not found at {p}. Consensus LEVELS are read only from the "
            f"UNADJUSTED IBES summary; the split-adjusted ibes_consensus_monthly file "
            f"is a look-ahead leak for levels and dispersion and is never substituted.")
    return p


def link_to_permno(frame: pd.DataFrame, link: pd.DataFrame, *,
                   max_score: int | None = None) -> pd.DataFrame:
    """Attach `permno` by IBES ticker inside the link's validity window.

    The rule of the adjusted pull (`statpers BETWEEN sdate AND COALESCE(edate, end)`,
    `score <= 2`). A (permno, statpers) claimed by two tickers keeps the better score.
    """
    ms = _config.IBES_LINK_MAX_SCORE if max_score is None else int(max_score)
    lk = link[["ticker", "permno", "sdate", "edate", "score"]].copy()
    lk = lk[pd.to_numeric(lk["score"], errors="coerce") <= ms].dropna(subset=["permno"])
    lk["sdate"] = pd.to_datetime(lk["sdate"])
    lk["edate"] = pd.to_datetime(lk["edate"]).fillna(pd.Timestamp("2262-01-01"))
    m = frame.merge(lk, on="ticker", how="inner")
    m = m[(m["statpers"] >= m["sdate"]) & (m["statpers"] <= m["edate"])]
    m = m.sort_values(["permno", "statpers", "score"], kind="mergesort")
    m = m.drop_duplicates(subset=["permno", "statpers", "fpi"], keep="first")
    m["permno"] = m["permno"].astype("int64")
    return m.drop(columns=["sdate", "edate", "score"]).reset_index(drop=True)


def attach_adj_factor(frame: pd.DataFrame, adj: pd.DataFrame | None) -> pd.DataFrame:
    """`adj_factor`: IBES's cumulative split factor in effect on each row's statpers.

    `ibes.adj` holds, per ticker, step changes stamped `spdates`; the factor in effect
    on a date is the last step at or before it (1.0 for a ticker with no step). Only
    RATIOS of two factors are used downstream (the split between two dates), and the
    later date of every ratio is the decision date -- so no future split is read.
    """
    out = frame.copy()
    if adj is None or not len(adj):
        out["adj_factor"] = np.nan
        return out
    a = adj[["ticker", "spdates", "adj"]].dropna().copy()
    a["spdates"] = pd.to_datetime(a["spdates"])
    a["adj"] = pd.to_numeric(a["adj"], errors="coerce")
    a = a.dropna().sort_values("spdates", kind="mergesort")
    out = out.sort_values("statpers", kind="mergesort")
    out = pd.merge_asof(out, a.rename(columns={"spdates": "statpers", "adj": "adj_factor"}),
                        on="statpers", by="ticker", direction="backward")
    # a ticker IBES never adjusted is on one basis throughout
    has = out["ticker"].isin(set(a["ticker"]))
    out.loc[~has & out["adj_factor"].isna(), "adj_factor"] = 1.0
    return out


def from_frames(statsumu: pd.DataFrame, link: pd.DataFrame,
                adj: pd.DataFrame | None = None, *, fpi: str = "1",
                start_year: int | None = None,
                end_year: int | None = None) -> pd.DataFrame:
    """The PIT consensus panel from in-memory frames (the loader and tests share it)."""
    s = statsumu.copy()
    s = s[(s["measure"].astype(str) == "EPS") & (s["fpi"].astype(str) == str(fpi))]
    s["statpers"] = pd.to_datetime(s["statpers"])
    if start_year is not None:
        s = s[s["statpers"].dt.year >= int(start_year)]
    if end_year is not None:
        s = s[s["statpers"].dt.year <= int(end_year)]
    for c in ("numest", "numup", "numdown", "meanest", "medest", "stdev"):
        if c in s.columns:
            s[c] = pd.to_numeric(s[c], errors="coerce").astype("float64")
    m = link_to_permno(s, link)
    m = attach_adj_factor(m, adj)
    m["share_basis"] = AS_QUOTED
    return m.sort_values(["permno", "statpers"], kind="mergesort").reset_index(drop=True)


def load_consensus(*, fpi: str = "1", start_year: int | None = None,
                   end_year: int | None = None, with_adj: bool = True) -> pd.DataFrame:
    """permno, ticker, statpers, numest, numup, numdown, meanest, medest, stdev,
    fpedats, adj_factor, share_basis -- the consensus as quoted at statpers.

    Raises `IbesUnadjustedUnavailable` when the unadjusted file or its link is absent.
    `adj_factor` is NaN when `ibes.adj` is absent (levels do not need it; a revision
    does, and `rebased_revision` refuses without it).
    """
    s = pd.read_parquet(_require(statsumu_path(), "unadjusted IBES summary (statsumu_epsus)"),
                        columns=list(CONSENSUS_COLUMNS))
    lk = pd.read_parquet(_require(link_path(), "IBES-CRSP link (ibcrsphist)"))
    adj = None
    if with_adj and adj_factors_path().is_file():
        adj = pd.read_parquet(adj_factors_path(), columns=["ticker", "spdates", "adj"])
    return from_frames(s, lk, adj, fpi=fpi, start_year=start_year, end_year=end_year)


def require_as_quoted(frame, *, who: str) -> None:
    """Refuse a consensus frame that does not declare the as-quoted share basis."""
    col = getattr(frame, "columns", ())
    if "share_basis" not in col:
        raise ValueError(
            f"{who}: the IBES consensus frame declares no `share_basis`. Levels and "
            f"dispersion are read only from `ibes_pit_consensus` (unadjusted, "
            f"{AS_QUOTED}); the split-adjusted file restates history in today's share "
            f"terms and rounds it to cents, which turns a future split into a zero spread.")
    bad = frame["share_basis"].astype(str) != AS_QUOTED
    if bool(bad.any()):
        raise ValueError(
            f"{who}: {int(bad.sum())} row(s) carry share_basis other than {AS_QUOTED}")


def rebased_revision(frame: pd.DataFrame, *, min_abs_prev: float = 0.01) -> pd.Series:
    """(meanest_t - meanest_{t-1}) / |meanest_{t-1}| per permno, on ONE share basis.

    Both values are as quoted; when a split falls between the two statpers, the
    earlier value is restated in the later date's shares with the ratio of IBES's own
    factors (adj_{t-1} / adj_t is the split that happened in between). A row whose
    factor is unknown is NaN, never a basis-mixed number.
    """
    require_as_quoted(frame, who="rebased_revision")
    f = frame.sort_values(["permno", "statpers"], kind="mergesort")
    g = f.groupby("permno", sort=False)
    prev = g["meanest"].shift(1)
    a_prev = g["adj_factor"].shift(1)
    a_now = f["adj_factor"]
    with np.errstate(invalid="ignore", divide="ignore"):
        prev_on_now = prev * (a_now / a_prev)
        rev = np.where(np.isfinite(prev_on_now) & (prev_on_now.abs() >= float(min_abs_prev)),
                       (f["meanest"] - prev_on_now) / prev_on_now.abs(), np.nan)
    return pd.Series(rev, index=f.index).reindex(frame.index)


__all__ = ["AS_QUOTED", "CONSENSUS_COLUMNS", "IbesUnadjustedUnavailable",
           "adj_factors_path", "attach_adj_factor", "from_frames", "link_path",
           "link_to_permno", "load_consensus", "rebased_revision", "require_as_quoted",
           "statsumu_path"]
