"""Analyst revision FLOW -- the net direction of target changes, point in time.

WHY THIS IS A DIFFERENT OBJECT FROM THE ONE THAT DIED
====================================================
`analyst_target_upside_xs` is CLOSED/PERVERSE as a LEVEL (target / price: t -3.6
large/mid, -7.2 small). A level is a stock of opinion; the FLOW is how that
opinion is moving -- raises minus lowers, how many distinct firms are acting,
and by how much. Q-4 / Q-10 in `docs/RESEARCH_QUEUE.md` ask whether the flow
ranks the cross-section, and this module is the feature both the sweep
(`scripts/revision_flow_sweep.py`) and the frozen book `revision_flow_v0` read.

It lives here and not in `analyst_ledger` because `analyst_ledger` reads its own
store (`backend/data/analyst_snapshots.jsonl`, snapshot deltas); this reads the
dated revision events in `<OPTIMUS_LEDGER_DIR>/analyst/target_revisions.parquet`
(393k rows, yfinance upgrades/downgrades, pulled 2026-09-24/25).

POINT IN TIME, AND WHAT IT CANNOT FIX
=====================================
* Only events with `event_date < asof` (STRICT) count. A same-day event is
  excluded even when it printed before the close: the conservative side of a
  timestamp whose timezone the vendor does not state.
* A row with `pit_safe == False` -- or a frame with no `pit_safe` column --
  REFUSES the whole call with ValueError. Dropping it silently would be the
  guard that reports green while doing nothing.
* What this cannot fix: the parquet was pulled in September 2026 for the names
  alive then. Of the 1,784 delisted symbols in the survivorship-free bar panel
  only 64 carry any revision history, so "has flow data" is very nearly "was
  alive in 2026-09". A model that sees NaN flow can learn "this name dies". The
  sweep therefore compares arms ONLY on the covered universe; see its docstring.
"""

from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd

#: Output columns, in order. The sweep and the book read these names.
FLOW_COLUMNS: tuple[str, ...] = ("net_raises", "n_firms", "median_target_change",
                                 "days_since_last", "n_events")

#: Default look-back. 90 calendar days = one quarter of revisions.
WINDOW_DAYS = 90

_RAISE = "raises"
_LOWER = "lowers"
_REQUIRED = ("ticker", "event_date", "firm", "target_action",
             "prior_target", "current_target")


def _normalise_action(s: pd.Series) -> pd.Series:
    a = s.fillna("").astype(str).str.strip().str.lower()
    # C2's fixture spells the verb "raise"/"lower"; the parquet "Raises"/"Lowers"
    # (and, twice, "LOwers").
    return a.replace({"raise": _RAISE, "lower": _LOWER})


def prepare(revisions: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalise ONCE; sorted by event time. Refuses, never drops."""
    if "pit_safe" not in revisions.columns:
        raise ValueError("revisions carry no `pit_safe` column: refusing -- a frame "
                         "that cannot say it is point-in-time is not one")
    bad = ~revisions["pit_safe"].astype("boolean").fillna(False).astype(bool)
    if bad.any():
        raise ValueError(f"{int(bad.sum())} revision row(s) have pit_safe=False "
                         f"(e.g. {revisions.loc[bad, 'ticker'].head(3).tolist()}); "
                         f"refusing rather than dropping them silently")
    missing = [c for c in _REQUIRED if c not in revisions.columns]
    if missing:
        raise ValueError(f"revisions missing columns {missing}")
    act = _normalise_action(revisions["target_action"])
    prior = pd.to_numeric(revisions["prior_target"], errors="coerce")
    cur = pd.to_numeric(revisions["current_target"], errors="coerce")
    chg = (cur / prior) - 1.0
    chg = chg.where((prior > 0) & (cur > 0) & np.isfinite(chg))
    out = pd.DataFrame({
        "ticker": revisions["ticker"].astype(str).str.upper().values,
        "t": pd.to_datetime(revisions["event_date"]).values,
        "firm": revisions["firm"].fillna("").astype(str).values,
        "sign": np.where(act == _RAISE, 1, np.where(act == _LOWER, -1, 0)).astype(np.int64),
        "chg": chg.astype(float).values,
    })
    out = out[out["t"].notna()]
    return out.sort_values("t", kind="mergesort").reset_index(drop=True)


def _stats(win: pd.DataFrame, asof: pd.Timestamp) -> pd.DataFrame:
    if win.empty:
        return pd.DataFrame(columns=list(FLOW_COLUMNS),
                            index=pd.Index([], name="ticker"), dtype=float)
    g = win.groupby("ticker", sort=True)
    out = pd.DataFrame({
        "net_raises": g["sign"].sum().astype(float),
        "n_firms": g["firm"].nunique().astype(float),
        "median_target_change": g["chg"].median(),
        "days_since_last": (asof - g["t"].max()).dt.total_seconds() / 86400.0,
        "n_events": g.size().astype(float),
    })
    out.index.name = "ticker"
    return out[list(FLOW_COLUMNS)]


def _window(prep: pd.DataFrame, times: np.ndarray, asof: pd.Timestamp,
            window_days: int) -> pd.DataFrame:
    lo = np.datetime64(asof - pd.Timedelta(days=window_days), "ns")
    hi = np.datetime64(asof, "ns")
    i = int(np.searchsorted(times, lo, side="left"))     # t >= asof - window
    j = int(np.searchsorted(times, hi, side="left"))     # t <  asof (strict)
    return prep.iloc[i:j]


def compute(revisions: pd.DataFrame, *, asof, window_days: int = WINDOW_DAYS) -> pd.DataFrame:
    """Flow per ticker from events in [asof - window_days, asof). Indexed by ticker.

    Columns: `net_raises` (raises - lowers), `n_firms` (distinct firms acting,
    any action), `median_target_change` (median of current/prior - 1),
    `days_since_last` (fractional days from the last event to `asof`),
    `n_events`. A ticker with no event in the window is ABSENT, not zero.
    """
    asof = pd.Timestamp(asof)
    prep = prepare(revisions)
    times = prep["t"].values.astype("datetime64[ns]")
    return _stats(_window(prep, times, asof, window_days), asof)


def compute_panel(revisions: pd.DataFrame, dates: Iterable, *,
                  window_days: int = WINDOW_DAYS) -> pd.DataFrame:
    """Long frame (ticker, date, *FLOW_COLUMNS) for many decision dates.

    Sorts once and slices the time-ordered events by `searchsorted`, so each
    date costs one groupby over ~one quarter of events rather than a scan of
    the whole history. Identical, row for row, to `compute` at each date
    (pinned by `test_panel_matches_pointwise_compute`).
    """
    prep = prepare(revisions)
    times = prep["t"].values.astype("datetime64[ns]")
    frames = []
    for d in sorted({pd.Timestamp(x) for x in dates}):
        s = _stats(_window(prep, times, d, window_days), d)
        if s.empty:
            continue
        s = s.reset_index()
        s["date"] = d
        frames.append(s)
    if not frames:
        return pd.DataFrame(columns=["ticker", "date", *FLOW_COLUMNS])
    return pd.concat(frames, ignore_index=True)[["ticker", "date", *FLOW_COLUMNS]]


def rule_score(flow: pd.DataFrame, *, min_firms: int = 3) -> pd.Series:
    """Murat's simple rule: `net_raises * n_firms`, only where >= `min_firms` acted."""
    f = flow[flow["n_firms"] >= min_firms]
    return (f["net_raises"] * f["n_firms"]).rename("rule_score")
