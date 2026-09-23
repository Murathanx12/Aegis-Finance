"""SEC filings -> ranker features, joined on WHEN THEY BECAME PUBLIC.

WHY THIS MODULE IS THE WHOLE POINT
==================================
`NEGATIVE_RESULTS.md` §59 closed price/volume at a 21-session horizon: the
ordering carries a real signal (IC +0.0227, t +7.56 over 122 month-blocks) worth
+0.28% gross, earned in names whose round trip costs ~35 bps. The edge is 28 bps
and the toll is 35.

The amplitude test the same day measured the alternative: fundamentals held
**38.4-39.5 bps/month** at every book size from k=20 to k=100, against a 20 bps
floor -- roughly triple the amplitude, and stable where price swung.

And `gap_audit` found the reason nothing had been done with that: the fundamental
panel ends **2024-12-31**, carries `permno` rather than a ticker, and had no
refresh path at all. `scripts/pull_sec_fundamentals` closed that gap. This module
is the join that was still missing between the two.

THE ONE RULE, AND THE BACKTEST IT SAVES
=======================================
**Join on `filed`, never on `end`.**

A 2026-Q2 balance sheet with `end = 2026-06-30` filed on **2026-08-05** was not
knowable on 2026-07-01. Joining on `end` would hand the model six weeks of
foresight on every quarter of every name, and the resulting backtest would look
superb and lose money live. `merge_asof(..., on="filed", direction="backward")`
is the whole defence, and `LAG_DAYS` adds a further margin for the gap between
EDGAR acceptance and practical availability.

This is the same distinction `web_events` draws between `observed_at` and
`evidence_date`, and `pull_sec_fundamentals` between `filed` and `end`. Three
modules, one rule, because it is the rule that decides whether any of this is
real.

WHAT IS AND IS NOT COMPUTED
===========================
Only ratios the amplitude test actually used, and only from facts that exist:

    gp_at     (revenue - cogs) / assets     gross profitability
    ope_be    operating_income / equity
    ni_be     net_income / equity
    at_gr1    year-over-year asset growth
    cash_at   cash / assets
    debt_at   debt / assets

A ratio whose numerator or denominator is absent is **NaN**, never zero.
LightGBM reads NaN natively (CLAUDE.md), and a zero where a number is missing is
a lie the model will happily fit. `coverage_by_sector()` exists because the
missingness is not random: banks file neither `CostOfRevenue` nor
`OperatingIncomeLoss`, so a naive dropna turns a cross-sectional strategy into a
bet against financials without anyone choosing that.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

from backend import config as _cfg

HISTORY_PATH = _cfg.OPTIMUS_LEDGER_DIR / "fundamentals_sec" / "sec_facts_history.parquet"

#: Extra days between `filed` and the date a feature may use the number. EDGAR
#: acceptance is not the same instant as practical availability, and a strategy
#: that needs the filing within hours of acceptance is one this account cannot
#: execute anyway. Cheap insurance against the only error that matters here.
LAG_DAYS = 2

#: The ratios, as (name, numerator fact, denominator fact). `gp_at`'s numerator
#: is a difference and is handled separately.
RATIOS: tuple[tuple[str, str, str], ...] = (
    ("ope_be", "operating_income", "equity"),
    ("ni_be", "net_income", "equity"),
    ("cash_at", "cash", "assets"),
    ("debt_at", "debt", "assets"),
)

FUNDAMENTAL_FEATURES: tuple[str, ...] = (
    "gp_at", "ope_be", "ni_be", "at_gr1", "cash_at", "debt_at", "book_equity_log",
)


class FundamentalsMissing(RuntimeError):
    """No filing history on disk. Refuses rather than ranking on nothing."""


def load_history(path: Path | None = None) -> pd.DataFrame:
    p = Path(path or HISTORY_PATH)
    if not p.exists():
        raise FundamentalsMissing(
            f"no SEC filing history at {p}. Build it with "
            f"`python -m scripts.pull_sec_fundamentals --universe-from-bars`.")
    df = pd.read_parquet(p)
    df["filed"] = pd.to_datetime(df["filed"])
    return df


#: A FLOW fact is only comparable across companies and across time if the
#: period it covers is the same length. SEC filings mix them freely: measured on
#: NVDA, `revenue` arrives as 90-day (62 rows), 181-day, 272-day and ~365-day
#: periods, and dividing whichever arrived last by total assets made `gp_at`
#: read 0.742, 0.236 and 0.225 across three consecutive filings of one company.
#: Keeping only annual periods makes the ratio mean one thing. Gross
#: profitability is slow-moving, so an annual refresh is not a real cost at a
#: 21-session horizon -- and it is what the JKP `gp_at` the amplitude test
#: measured was built from.
ANNUAL_DAYS = (350, 380)
FLOW_FACTS = ("revenue", "cogs", "operating_income", "net_income")


def annual_flows_only(hist: pd.DataFrame) -> pd.DataFrame:
    """Drop quarterly and part-year rows for FLOW facts; keep stock facts whole.

    A stock fact (assets, equity, cash, debt) is a balance at a date and carries
    no period, so it is never filtered. Mixing the two rules is how a filter
    silently deletes the balance sheet.
    """
    if "period_days" not in hist.columns:
        logger.warning("fundamental_features: history has no `period_days`; "
                       "flow facts cannot be made comparable and are kept as-is")
        return hist
    is_flow = hist["fact"].isin(FLOW_FACTS)
    lo, hi = ANNUAL_DAYS
    keep_flow = is_flow & hist["period_days"].between(lo, hi)
    return hist[(~is_flow) | keep_flow].copy()


def wide_by_filing(hist: pd.DataFrame) -> pd.DataFrame:
    """One row per (ticker, filed) with each fact in its own column.

    A filing usually reports several facts on the same date; a few report one.
    Forward-filling WITHIN a ticker is correct here and nowhere else: last
    quarter's assets remain the best known value until a new filing states
    otherwise, and that is exactly what a reader had at the time.
    """
    hist = annual_flows_only(hist)
    wide = (hist.pivot_table(index=["ticker", "filed"], columns="fact",
                             values="val", aggfunc="last")
            .sort_index())
    wide = wide.groupby(level="ticker").ffill()
    return wide.reset_index()


def ratios(wide: pd.DataFrame) -> pd.DataFrame:
    """Facts -> ratios. Missing stays missing."""
    d = wide.copy()

    def safe(num: pd.Series, den: pd.Series) -> pd.Series:
        den = den.replace(0.0, np.nan)
        return num / den

    have = set(d.columns)
    if {"revenue", "cogs", "assets"} <= have:
        d["gp_at"] = safe(d["revenue"] - d["cogs"], d["assets"])
    else:
        d["gp_at"] = np.nan
    for name, num, den in RATIOS:
        d[name] = safe(d[num], d[den]) if {num, den} <= have else np.nan

    if "assets" in have:
        # year-over-year asset growth, per ticker, on the FILING sequence --
        # roughly four filings back. Not a calendar year, because a filer that
        # skipped a quarter should not silently compare to a different span.
        prev = d.groupby("ticker")["assets"].shift(4)
        d["at_gr1"] = safe(d["assets"] - prev, prev)
    else:
        d["at_gr1"] = np.nan

    d["book_equity_log"] = (np.log(d["equity"].where(d["equity"] > 0))
                            if "equity" in have else np.nan)
    return d[["ticker", "filed", *FUNDAMENTAL_FEATURES]]


def attach(panel: pd.DataFrame, *, history: pd.DataFrame | None = None,
           lag_days: int = LAG_DAYS) -> pd.DataFrame:
    """Add fundamental features to a price panel, PIT-correctly.

    `panel` is `xs_ranker.build_panel`'s frame: one row per (symbol, date).
    Each row receives the most recent filing whose `filed + lag_days` is at or
    before that row's date — never a filing from the future, and never a value
    chosen by the period it describes.
    """
    hist = history if history is not None else load_history()
    feats = ratios(wide_by_filing(hist))
    feats["available"] = feats["filed"] + pd.Timedelta(days=lag_days)
    feats = feats.sort_values("available")

    left = panel.sort_values("date").copy()
    left["_sym"] = left["symbol"].astype(str)
    feats["_sym"] = feats["ticker"].astype(str)

    merged = pd.merge_asof(
        left, feats.drop(columns=["ticker"]),
        left_on="date", right_on="available", by="_sym",
        direction="backward", allow_exact_matches=True,
    )
    merged = merged.drop(columns=["_sym"])
    merged["fundamental_age_days"] = (
        (merged["date"] - merged["filed"]).dt.days.astype("float"))
    # A filing older than ~15 months is stale enough that its ratios describe a
    # different company. Reported, not dropped: the age is itself a feature and
    # a reader should see how much of the panel is carrying old numbers.
    merged.loc[merged["fundamental_age_days"] > 460, list(FUNDAMENTAL_FEATURES)] = np.nan
    return merged


def coverage(panel: pd.DataFrame, *, asof: str | date | None = None) -> dict:
    """How much of the cross-section actually carries each feature.

    The missingness is NOT random. Banks file neither `CostOfRevenue` nor
    `OperatingIncomeLoss`, so `gp_at` and `ope_be` are structurally absent for
    financials. A model trained only on rows that have them is a bet against
    that sector, chosen by nobody. This is the number to read before any return.
    """
    d = panel
    if asof is not None:
        d = d[d["date"] == pd.Timestamp(asof)]
    elif "date" in d:
        d = d[d["date"] == d["date"].max()]
    n = len(d)
    if not n:
        return {"n": 0, "why": "no rows on that date"}
    out = {"n": int(n), "asof": str(pd.Timestamp(d["date"].iloc[0]).date())}
    for f in FUNDAMENTAL_FEATURES:
        out[f] = round(float(d[f].notna().mean()), 4) if f in d else None
    out["any_fundamental"] = round(
        float(d[[f for f in FUNDAMENTAL_FEATURES if f in d]].notna().any(axis=1).mean()), 4)
    if "fundamental_age_days" in d:
        age = d["fundamental_age_days"].dropna()
        out["median_age_days"] = float(age.median()) if len(age) else None
    out["read_me_first"] = (
        "Missingness is structural, not random: banks file neither "
        "CostOfRevenue nor OperatingIncomeLoss, so dropping incomplete rows "
        "turns a cross-sectional strategy into a sector bet nobody chose.")
    return out
