"""THE SIGNALS THE FIRST FOUR NIGHT-JOB BOOKS DECLARE, as pure functions.

WHY THIS FILE EXISTS
====================
`book_cadence.decide_weights` is faithful to the contract or it refuses: a
selector that substitutes a ranking it can compute for the one the book
declares produces a NAV series belonging to a strategy nobody wrote down. Its
own `SUPPORTED_SIGNALS` tuple covers what is computable from a daily bar panel
and nothing else, so the four books of
`docs/research_notes/2026-09-12/spec_first_books.md` — whose signals need a
short-interest panel, a Form-4 tape, a capital-gains overhang and a confidence
threshold — would every one of them be a permanent named refusal.

This module is where those four signals are COMPUTED, and `REGISTRY` is how
`decide_weights` reaches them. Everything else stays a refusal by name.

TWO LAYERS, ON PURPOSE
======================
Each signal is a **pure core** over a DataFrame (`si_turnover_composite`,
`cluster_lengths`, `capital_gains_overhang`, `confidence_z`) and a thin
**adapter** that finds the panel on disk and calls the core. The core is what
the tests exercise on synthetic frames; the adapter is what fails on a machine
without the panel, and it fails BY NAME rather than by returning an empty dict
that would read as "no name qualified this period".

THE PIT RULE IS PER SIGNAL AND IT IS THE POINT
==============================================
* short interest — `observed_at` (settlement + the measured publication lag),
  **never `datadate`**. `scripts/short_interest_panel.py` writes the column;
  using `datadate` would trade on a figure nobody could see for two weeks.
* insider clusters — `observed_at_utc` (FILING date, end of day), never
  `event_time_utc` (the transaction date). The transaction dates define the
  cluster's SHAPE; the latest filing date defines when the cluster is VISIBLE,
  and a cluster is entered on the later of the two by construction.
* overhang — price and turnover strictly before the decision close. There is
  no vendor lag to get wrong here and therefore no excuse for getting it wrong.
* confidence — a cross-sectional z of a trailing return, computed on bars that
  end at the decision close.

WHAT THIS MODULE MAY NOT DO
===========================
It ranks. It never sizes, never places an order, and never asks an LLM
anything: *no LLM output ever sizes or ranks*. Four of the five functions here
would be a natural place to put a model and none of them has one.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Callable, Sequence

logger = logging.getLogger(__name__)


class SignalUnavailable(ValueError):
    """The panel this signal needs does not cover the decision date.

    Raised, not swallowed. `book_cadence` catches it as an `UnsupportedSignal`
    and the book is MARKED but does not DECIDE, with the reason on the receipt:
    a book that quietly held nothing because its panel ran out looks exactly
    like a book that decided to hold nothing.
    """


# --------------------------------------------------------------------------
# BOOK A — low short interest x high turnover
#
# Boehmer-Huszar-Jordan (JFE 2010): the informative side of short interest is
# the side nobody trades. The variable is a LEVEL x LEVEL double sort, which is
# the distinction NEGATIVE_RESULTS §24 turns on -- §24 tested a short-interest
# CHANGE (`si_chg_low`, net-dead from turnover) and a days-to-cover LEVEL on the
# SHORT leg. Neither is this.


def si_turnover_composite(panel, asof, *, min_names: int = 20) -> dict:
    """{permno: z(turnover) - z(si_ratio)} from rows PUBLISHED on or before `asof`.

    The double sort is collapsed to one composite z so that `Construction.top_k`
    applies unchanged; the raw quintile x quintile table is a diagnostic the
    replay prints beside it, never the thing the book trades.

    `panel` is `scripts.short_interest_panel`'s output: one row per
    (permno, datadate) with `observed_at`, `si_ratio` and `turnover_21d_w`.
    Only the LATEST published print per permno is used, and it is never
    interpolated forward across a gap — a stale print is still the last thing
    that was public, which is exactly what a trader would have had.
    """
    import numpy as np
    import pandas as pd

    ts = pd.Timestamp(asof)
    seen = panel[pd.to_datetime(panel["observed_at"]) <= ts]
    if seen.empty:
        raise SignalUnavailable(
            f"no short-interest print had been PUBLISHED on or before {asof} "
            f"(the panel's earliest `observed_at` is "
            f"{pd.to_datetime(panel['observed_at']).min() if len(panel) else 'n/a'}). "
            f"`datadate` is the settlement date and is not a substitute.")
    seen = seen.sort_values(["permno", "observed_at"], kind="mergesort")
    latest = seen.drop_duplicates(subset=["permno"], keep="last")
    latest = latest[np.isfinite(latest["si_ratio"])
                    & np.isfinite(latest["turnover_21d_w"])]
    if len(latest) < int(min_names):
        raise SignalUnavailable(
            f"only {len(latest)} name(s) carried a published short-interest "
            f"print at {asof}; a cross-sectional z over fewer than "
            f"{min_names} is a rank of the survivors, not of the market")
    z_to = _zscore(latest["turnover_21d_w"].astype(float))
    z_si = _zscore(latest["si_ratio"].astype(float))
    composite = z_to - z_si
    return {int(p): float(v) for p, v in zip(latest["permno"], composite)
            if np.isfinite(v)}


def _zscore(s):
    import numpy as np
    x = s.to_numpy(dtype=float)
    sd = float(np.nanstd(x))
    if not np.isfinite(sd) or sd <= 0:
        return np.zeros_like(x)
    return (x - float(np.nanmean(x))) / sd


def short_interest_panel_dir() -> Path:
    from backend.config import OPTIMUS_LEDGER_DIR
    return OPTIMUS_LEDGER_DIR / "short_interest" / "comp_sec_shortint"


def load_short_interest(asof, *, lookback_years: int = 2, panel_dir=None):
    """The published short-interest rows that could matter at `asof`."""
    import pandas as pd

    d = Path(panel_dir) if panel_dir is not None else short_interest_panel_dir()
    ts = pd.Timestamp(asof)
    frames = []
    for y in range(ts.year - int(lookback_years), ts.year + 1):
        p = d / f"{y}.parquet"
        if p.is_file():
            frames.append(pd.read_parquet(p))
    if not frames:
        raise SignalUnavailable(
            f"no short-interest panel file for {ts.year - lookback_years}..{ts.year} "
            f"under {d}. The panel is built by "
            f"`python -m scripts.short_interest_panel` from the WRDS bulk tables "
            f"and covers 1990-2024; the 2025-26 forward leg is FINRA's free CDN "
            f"and is not ingested yet, so a 2025-26 decision is a REFUSAL and "
            f"not an empty book.")
    return pd.concat(frames, ignore_index=True)


# --------------------------------------------------------------------------
# BOOK B — insider cluster buys, split by CLUSTER LENGTH
#
# Kang-Kim-Wang (working paper, unpublished -- flagged): clusters spread over
# 4-5 consecutive days are followed by >5% higher BHAR(22,90) than non-cluster
# purchases, while SAME-DAY clusters yield 0.72% LOWER. The same-day arm is the
# falsifier: if it wins, the length-conditioning claim is dead before the family
# read, which is the whole reason it is built alongside rather than afterwards.

#: A cluster needs at least this many DISTINCT insiders (by CIK). Two people
#: buying is the smallest thing the word "cluster" can honestly mean.
MIN_CLUSTER_INSIDERS = 2

#: The frontier bucket, frozen at registration: clusters whose transaction dates
#: span 4 or 5 consecutive TRADING days. `0` (same day) is the falsifier arm and
#: 1-3 is reported but not traded (KKW gives it no clean sign).
FRONTIER_SPAN_DAYS = (4, 5)
SAME_DAY_SPAN = 0


def cluster_lengths(buys, *, sessions=None, max_span_days: int = 10):
    """One row per (issuer, cluster): span, n insiders, entry date.

    `buys` needs `symbol`, `insider_cik`, `event_time_utc` (the TRANSACTION
    date, which is what clustering is a fact about) and `observed_at_utc` (the
    FILING date, which is what the market can see).

    A cluster is a maximal run of an issuer's purchase transaction dates whose
    consecutive gaps are at most one SESSION apart, with >= MIN_CLUSTER_INSIDERS
    distinct CIKs. Its **entry date is the LATEST `observed_at_utc` among its
    constituents**: before that filing, the market can see a subset of the
    cluster, not the cluster. Entering on the first filing would be reading a
    fact from documents that had not been filed.
    """
    import pandas as pd

    if buys.empty:
        return pd.DataFrame(columns=["symbol", "span_days", "n_insiders",
                                     "n_trades", "entry_date", "first_trans",
                                     "last_trans"])
    d = buys.copy()
    d["trans_date"] = pd.to_datetime(d["event_time_utc"], utc=True).dt.tz_localize(None).dt.normalize()
    d["filing_date"] = pd.to_datetime(d["observed_at_utc"], utc=True).dt.tz_localize(None).dt.normalize()
    d = d.dropna(subset=["symbol", "insider_cik", "trans_date", "filing_date"])
    if d.empty:
        return pd.DataFrame(columns=["symbol", "span_days", "n_insiders",
                                     "n_trades", "entry_date", "first_trans",
                                     "last_trans"])

    # Session index: the gap between two transaction dates is counted in
    # SESSIONS, not calendar days, so a Friday/Monday pair is one day apart and
    # a Friday/Tuesday pair is two. Without a session calendar the run is
    # measured on business days, which is the same thing except across a
    # holiday and says so.
    idx = _session_index(sessions, d["trans_date"])

    out = []
    for sym, grp in d.groupby("symbol", sort=True):
        grp = grp.sort_values("trans_date", kind="mergesort")
        pos = grp["trans_date"].map(idx)
        if pos.isna().any():
            grp = grp[pos.notna()]
            pos = pos[pos.notna()]
            if grp.empty:
                continue
        run_id = (pos.diff().fillna(0) > 1).cumsum()
        for _, run in grp.groupby(run_id):
            n_insiders = int(run["insider_cik"].nunique())
            if n_insiders < MIN_CLUSTER_INSIDERS:
                continue
            first, last = run["trans_date"].min(), run["trans_date"].max()
            span = int(idx[last] - idx[first])
            if span > int(max_span_days):
                continue
            out.append({
                "symbol": str(sym), "span_days": span, "n_insiders": n_insiders,
                "n_trades": int(len(run)),
                "entry_date": run["filing_date"].max(),
                "first_trans": first, "last_trans": last,
                "n_officers": int(run["insider_is_officer"].sum())
                if "insider_is_officer" in run else 0,
                "dollar_value": float(run["insider_dollar_value"].sum())
                if "insider_dollar_value" in run else 0.0,
            })
    return pd.DataFrame(out)


def _session_index(sessions, trans_dates) -> dict:
    import pandas as pd

    if sessions is not None and len(sessions):
        days = pd.DatetimeIndex(pd.to_datetime(list(sessions))).normalize().unique().sort_values()
    else:
        lo, hi = trans_dates.min(), trans_dates.max()
        days = pd.bdate_range(lo, hi)
    base = {d: i for i, d in enumerate(days)}
    out = dict(base)
    # A transaction stamped on a non-session day (a weekend filing of a Friday
    # trade, a holiday) is snapped to the NEXT session rather than dropped: the
    # cluster it belongs to is a fact, and dropping one leg would shorten the
    # span and move the cluster into a different bucket.
    for d in pd.DatetimeIndex(trans_dates.unique()).sort_values():
        if d in out:
            continue
        later = days[days >= d]
        out[d] = int(base[later[0]]) if len(later) else (len(days) + 1)
    return out


def cluster_eligibility(clusters, asof, *, spans=FRONTIER_SPAN_DAYS,
                        window_days: int = 31) -> dict:
    """{symbol: 1.0} for clusters in `spans` whose ENTRY DATE is in the window.

    An eligibility gate, not a continuous rank: `Construction(rule=
    "passthrough")` owns every name that qualifies. The window ends on `asof`
    inclusive and is the book's own rebalance period, so a cluster is entered
    once, in the month its last constituent filing lands.
    """
    import pandas as pd

    if clusters is None or len(clusters) == 0:
        return {}
    ts = pd.Timestamp(asof).normalize()
    lo = ts - pd.Timedelta(days=int(window_days) - 1)
    e = pd.to_datetime(clusters["entry_date"]).dt.normalize()
    hit = clusters[(e >= lo) & (e <= ts)
                   & clusters["span_days"].isin(list(spans))]
    return {str(s): 1.0 for s in sorted(set(hit["symbol"]))}


def insider_events_path() -> Path:
    from backend.config import OPTIMUS_LEDGER_DIR
    return OPTIMUS_LEDGER_DIR / "sec_insider" / "insider_events_v1.parquet"


def load_insider_buys(asof, *, lookback_days: int = 400, path=None):
    """Open-market purchase rows FILED on or before `asof`.

    The `observed_at_utc` cut is applied HERE, once, on the way in — so no
    caller can compute a cluster from a filing that had not happened. The
    transaction-date column is deliberately not used for the cut.
    """
    import pandas as pd

    p = Path(path) if path is not None else insider_events_path()
    if not p.is_file():
        raise SignalUnavailable(
            f"the Form-4 event table is not on this machine: {p}. It is built "
            f"by `python -m scripts.sec_insider_bulk_load` "
            f"(docs/BUILD_2026-09-07b_I1_SEC_INSIDER.md).")
    ts = pd.Timestamp(asof).normalize()
    lo = ts - pd.Timedelta(days=int(lookback_days))
    df = pd.read_parquet(p, columns=["symbol", "event_type", "event_time_utc",
                                     "observed_at_utc", "insider_cik",
                                     "insider_is_officer", "insider_dollar_value",
                                     "year"])
    df = df[df["event_type"] == "insider_open_market_buy"]
    filed = pd.to_datetime(df["observed_at_utc"], utc=True).dt.tz_localize(None)
    df = df[(filed <= ts + pd.Timedelta(hours=23, minutes=59)) & (filed >= lo)]
    return df


# --------------------------------------------------------------------------
# BOOK C — the disposition-overhang conditioner
#
# Grinblatt-Han (JFE 2005), verbatim, because Frazzini's own reference price is
# built from mutual-fund holdings and no 13F/holdings panel exists here:
#
#   RP_t  = (1/k) * sum_{n=1..T} [ V_{t-n} * prod_{tau=1..n-1}(1 - V_{t-n+tau}) * P_{t-n} ]
#   CGO_t = (P_{t-1} - RP_t) / P_{t-1}
#
# PIT by construction: every input is the name's own past price and turnover.


def capital_gains_overhang(prices, turnover, *, lookback: int = 1260) -> float:
    """CGO for ONE name from its own price and turnover history.

    `prices` and `turnover` are aligned, oldest first, and BOTH END STRICTLY
    BEFORE the decision close — the caller slices, this function does not, so
    that a leak is a visible slicing bug rather than an off-by-one inside a
    weighted sum nobody re-derives.
    """
    import numpy as np

    p = np.asarray(prices, dtype=float)
    v = np.clip(np.asarray(turnover, dtype=float), 0.0, 1.0)
    if p.size != v.size:
        raise ValueError("prices and turnover must be the same length")
    if p.size < 2:
        raise SignalUnavailable("CGO needs at least two sessions of history")
    p, v = p[-int(lookback):], v[-int(lookback):]
    n = p.size
    # weight_i = V_i * prod_{j>i} (1 - V_j), i.e. the chance the share bought at
    # i has not turned over since. Computed as a reverse cumulative product so
    # the whole lookback is one pass instead of T nested products.
    surv = np.concatenate([np.cumprod((1.0 - v)[::-1])[::-1][1:], [1.0]])
    w = v * surv
    k = float(w.sum())
    if not np.isfinite(k) or k <= 0:
        raise SignalUnavailable(
            "the turnover history sums to zero weight, so there is no reference "
            "price: the name did not trade over the lookback")
    rp = float((w * p).sum() / k)
    last = float(p[n - 1])
    if not np.isfinite(last) or last <= 0:
        raise SignalUnavailable("the last price is not usable")
    return (last - rp) / last


def overhang_conditioned_ranks(cgo: dict, event_sign: dict, *,
                               tercile: float = 2.0 / 3.0,
                               side: str = "top") -> dict:
    """{name: CGO} for GOOD-NEWS names in the top overhang tercile.

    The eligible set is gated on the EVENT SIGN first and ranked on overhang
    inside it. That order is the mechanism: this is a conditioner, not a
    two-factor blend, and a blend would be a different book.

    `side="bottom"` returns the BOTTOM tercile instead, and exists for exactly
    one caller: TRIAL-DRAFT-C's registered sign-flip placebo
    (`scripts/night_c_falsifiers.py`), which is the same construction with the
    conditioning sign flipped. The book's own call does not pass it, so the
    book cannot change by this argument existing — and the placebo cutting its
    tercile with a second implementation of this quantile is exactly the way a
    placebo stops being a placebo.
    """
    import numpy as np

    if side not in ("top", "bottom"):
        raise ValueError(f"side must be 'top' or 'bottom', not {side!r}")
    good = {k: float(v) for k, v in cgo.items()
            if float(event_sign.get(k, 0.0)) > 0 and np.isfinite(v)}
    if not good:
        raise SignalUnavailable(
            "no name carried BOTH a positive event sign and a computable "
            "overhang this period; the conditioner has an empty eligible set "
            "rather than a weak one")
    return _tercile_side(good, side=side, tercile=tercile)


# --------------------------------------------------------------------------
# BOOKS E, F, G — the three characteristics that were already on disk
#
# All three read a column this repository has PAID FOR AND NEVER READ, and all
# three are PIT by the panel's own stamp rather than by a lag we chose:
#
#   E  qmj_rank            JKP `qmj`, stamped `eom`            TRIAL-DRAFT-E
#   F  seasonality_score   JKP `seas_*an`, stamped `eom`       TRIAL-DRAFT-F
#   G  forecast_dispersion IBES `stdev`/`meanest`, `statpers`  TRIAL-DRAFT-G
#
# THE STAMP IS THE WHOLE PIT ARGUMENT AND IT IS NOT OURS TO INVENT. JKP's panel
# is formation-date stamped on `eom` and its own meta.json says each
# characteristic derives from data public by then; the IBES consensus row is
# stamped `statpers`, the snapshot date. The caller slices to rows at or before
# the decision close -- these functions do not, exactly as
# `capital_gains_overhang` does not, so a leak is a visible slicing bug in the
# caller rather than an off-by-one buried inside a quantile.
#
# NONE of them sorts. Each returns {permno: the characteristic's own value} for
# the requested side of the tercile cut, and the SELECTOR decides which
# direction to rank in -- because "low dispersion is the held leg" is a fact
# about Book G's registration and not about the arithmetic of a ratio.

#: A cross-sectional tercile over fewer names than this is a cut of the
#: survivors, not of the market. Same spirit and the same number as
#: `si_turnover_composite`'s own `min_names`.
MIN_CHARACTERISTIC_NAMES = 20

#: TRIAL-DRAFT-F section 6 freezes BOTH columns and the requirement that both be
#: present: `seas_11_15an` and `seas_16_20an`, JKP's own same-calendar-month
#: averages at lags of 11-15 and 16-20 YEARS. The lag structure is Heston-Sadka's
#: and it is chosen to be mechanically disjoint from the 12-1 momentum window
#: the arena's ten books already price.
SEASONALITY_COLUMNS = ("seas_11_15an", "seas_16_20an")

#: The years-2-5 variant. A REPORTED DIAGNOSTIC ONLY (TRIAL-DRAFT-F section 8):
#: reading it for a better number would be two books wearing one registration,
#: so it may never become the primary.
SEASONALITY_COLUMNS_NEAR = ("seas_2_5an",)

#: TRIAL-DRAFT-G section 6 freezes `numest >= 3`, not 2: a two-analyst standard
#: deviation is ONE pairwise difference, and a "disagreement" built on one
#: disagreement is a noise measurement.
MIN_ESTIMATES_FOR_DISPERSION = 3


def _tercile_side(values: dict, *, side: str, tercile: float) -> dict:
    """The requested side of a tercile cut over `values`. ONE implementation.

    `side="top"` keeps values at or above the `tercile` quantile; `side="bottom"`
    keeps values at or below the `1 - tercile` quantile, which is the mirror
    image and NOT a second threshold to tune. `overhang_conditioned_ranks` calls
    this too, so the frozen Book C cut and the three new books' cuts cannot
    drift apart -- a placebo or a control that cuts its tercile with a second
    implementation of the quantile is not cutting the same tercile.
    """
    import numpy as np

    if side not in ("top", "bottom"):
        raise ValueError(f"side must be 'top' or 'bottom', not {side!r}")
    vals = list(values.values())
    if side == "bottom":
        cut = float(np.quantile(vals, 1.0 - float(tercile)))
        return {k: v for k, v in values.items() if v <= cut}
    cut = float(np.quantile(vals, float(tercile)))
    return {k: v for k, v in values.items() if v >= cut}


def _finite_by_permno(frame, column: str) -> dict:
    """{permno: float} for the rows of `frame` carrying a finite `column`."""
    import numpy as np

    if column not in getattr(frame, "columns", ()):
        raise SignalUnavailable(
            f"the panel carries no {column!r} column; the columns present are "
            f"{sorted(getattr(frame, 'columns', []))[:12]}. This is a REFUSAL "
            f"and not an empty cross-section: a book whose characteristic is "
            f"absent has not decided to hold nothing.")
    out = {}
    for pn, v in zip(frame["permno"], frame[column]):
        try:
            x = float(v)
        except (TypeError, ValueError):
            continue
        if np.isfinite(x):
            out[int(pn)] = x
    return out


def qmj_rank(frame, *, column: str = "qmj", side: str = "top",
             tercile: float = 2.0 / 3.0,
             min_names: int = MIN_CHARACTERISTIC_NAMES) -> dict:
    """BOOK E. {permno: qmj} for the requested tercile of JKP's own composite.

    `frame` is one month of the JKP characteristic panel, already sliced to the
    rows stamped at or before the decision close and already intersected with
    the eligible band. Higher `qmj` is more quality, so the book's selector
    ranks DESCENDING and the junk falsifier (`side="bottom"`, TRIAL-DRAFT-E
    section 5 clause 2) ranks ASCENDING.

    `column` exists for ONE registered purpose: the `qmj_prof`-only diagnostic
    TRIAL-DRAFT-E section 3 lists as reported-never-deciding. The book's own
    call does not pass it, so the book cannot change by this argument existing
    -- and section 8 forbids the diagnostic from becoming the primary.
    """
    vals = _finite_by_permno(frame, column)
    if len(vals) < int(min_names):
        raise SignalUnavailable(
            f"only {len(vals)} name(s) carried a finite {column!r} this month; "
            f"a cross-sectional tercile over fewer than {min_names} is a cut of "
            f"the survivors, not of the market")
    return _tercile_side(vals, side=side, tercile=tercile)


def seasonality_score(frame, *, columns=SEASONALITY_COLUMNS, side: str = "top",
                      tercile: float = 2.0 / 3.0,
                      min_names: int = MIN_CHARACTERISTIC_NAMES) -> dict:
    """BOOK F. {permno: composite z} for the requested tercile.

    The composite is the equal-weight mean of the WITHIN-FRAME cross-sectional
    z-scores of the named columns, computed only for names carrying EVERY named
    column. Requiring all of them is the registered construction and it is not a
    convenience: averaging a two-column z with a one-column z would make the
    signal mean a different thing for old and young names, and the age of a
    listing is exactly what a twenty-year seasonality lag selects on.

    The columns are JKP's own same-calendar-month averages. Their alignment was
    MEASURED before the book was registered (TRIAL-DRAFT-F section 2):
    `seas_2_5an` at `eom = t` correlates 0.99999 with the name's own mean excess
    return at months `t + 1 - 12k`, so the column stamped at the formation close
    refers to the calendar month the book is about to EARN, which is what a
    seasonality signal has to do to be a signal at all.

    `columns` defaults to the frozen 11-15 / 16-20 pair.
    `SEASONALITY_COLUMNS_NEAR` is the years-2-5 diagnostic and TRIAL-DRAFT-F
    section 8 forbids it becoming primary.
    """
    import numpy as np

    cols = tuple(columns)
    if not cols:
        raise SignalUnavailable("seasonality_score was given no columns to read")
    per_col = {c: _finite_by_permno(frame, c) for c in cols}
    shared = set.intersection(*(set(v) for v in per_col.values()))
    if len(shared) < int(min_names):
        counts = {c: len(v) for c, v in per_col.items()}
        raise SignalUnavailable(
            f"only {len(shared)} name(s) carried ALL of {list(cols)} this month "
            f"(per column: {counts}); a cross-sectional tercile over fewer than "
            f"{min_names} is a cut of the survivors. A name needs roughly twenty "
            f"years of tape to carry the 16-20 lag, so a thin month here is a "
            f"coverage fact and not a market fact.")
    names = sorted(shared)
    zs = []
    for c in cols:
        x = np.asarray([per_col[c][n] for n in names], dtype=float)
        sd = float(np.nanstd(x))
        zs.append(np.zeros_like(x) if not np.isfinite(sd) or sd <= 0
                  else (x - float(np.nanmean(x))) / sd)
    composite = np.mean(np.vstack(zs), axis=0)
    vals = {int(n): float(v) for n, v in zip(names, composite) if np.isfinite(v)}
    if len(vals) < int(min_names):
        raise SignalUnavailable(
            f"the seasonality composite resolved {len(vals)} finite score(s) "
            f"from {len(names)} covered name(s)")
    return _tercile_side(vals, side=side, tercile=tercile)


#: The denominators Book G may divide the forecast standard deviation by.
#: `meanest` is v0 (the coefficient of variation, Diether-Malloy-Scherbina's own
#: construction); `price` is TRIAL-DRAFT-G Amendment 1. Anything else is refused
#: rather than defaulted -- see `forecast_dispersion`.
DISPERSION_SCALES = ("meanest", "price")


def forecast_dispersion(frame, *,
                        min_numest: int = MIN_ESTIMATES_FOR_DISPERSION,
                        side: str = "bottom", tercile: float = 2.0 / 3.0,
                        min_names: int = MIN_CHARACTERISTIC_NAMES,
                        scale: str = "meanest") -> dict:
    """BOOK G. {permno: |stdev / <scale>|} for the requested tercile.

    `frame` is one month of the IBES consensus panel, already filtered to
    `measure == 'EPS'` and `fpi == '1'` by the caller and already sliced to rows
    stamped at or before the decision close.

    The default `side="bottom"` is the LOW-disagreement leg, which is the leg
    TRIAL-DRAFT-G registers as held; the top tercile is the leg the book AVOIDS
    and section 8 forbids shorting it, because the borrow cost that took 162
    anomalies from +0.14%/month to -0.01%/month is not in this repository's cost
    ruler. The book's selector therefore ranks the returned values ASCENDING: a
    smaller ratio is a stronger hold.

    Rows with a non-finite or ZERO `meanest` are dropped rather than clipped. A
    consensus of zero makes the coefficient of variation infinite for a reason
    that is about the denominator and not about disagreement, and a book that
    quietly winsorised it would be holding names for an arithmetic accident.

    THE DENOMINATOR IS A PARAMETER, AND THE AMENDMENT THAT MADE IT ONE
    ==================================================================
    `scale="meanest"` is v0 and the default, and the default path is
    byte-identical to the code that produced `B_books_efg_replay_run01`.

    `scale="price"` is TRIAL-DRAFT-G Amendment 1: `|stdev / price|`, the
    forecast standard deviation per dollar of share price, with `price` the
    PIT CRSP close of the selection month carried on the caller's own frame.
    The reason is in the run-01 receipt rather than in a preference: v0's
    +0.89%/month at the $3M floor EXCEEDS Diether-Malloy-Scherbina's published
    0.79%/month LONG-SHORT spread, which a long-only-avoid half of that spread
    cannot honestly do. `|stdev / meanest|` divides by forecast EPS, so the
    score is large wherever consensus EPS is near zero -- an earnings-LEVEL
    tilt riding along inside a disagreement measure. Scaling by price removes
    that channel: price is never near zero in a band with a $5 minimum.

    `stdev` may be zero (unanimous analysts) and that is a legitimate score of
    zero, not a dropped row -- under either denominator. What is dropped is a
    denominator that is zero or non-finite, and under `price` the eligible
    band's own $5 minimum means no row in a real pool is dropped for it.
    Section 8 of the registration forbids swapping the denominator INSIDE the
    v0 registration; this parameter exists so the amendment is a separate,
    named read and never a silent change to v0's own number.
    """
    import numpy as np

    if scale not in DISPERSION_SCALES:
        raise SignalUnavailable(
            f"unknown dispersion scale {scale!r}; expected one of "
            f"{DISPERSION_SCALES}. A denominator this function does not know is "
            f"refused rather than defaulted, because a silent fallback to "
            f"`meanest` would publish v0's number under the amendment's name")
    needed = ["permno", "stdev", "meanest", "numest"]
    if scale == "price":
        needed.append("price")
    for c in needed:
        if c not in getattr(frame, "columns", ()):
            raise SignalUnavailable(
                f"the IBES consensus frame carries no {c!r} column; forecast "
                f"dispersion at scale={scale!r} needs {', '.join(needed)} and "
                f"does not substitute another measure of disagreement")
    denom_col = frame["price"] if scale == "price" else frame["meanest"]
    vals = {}
    for pn, sd, mean, n, den in zip(frame["permno"], frame["stdev"],
                                    frame["meanest"], frame["numest"],
                                    denom_col):
        try:
            sd_f, mean_f, n_f, den_f = float(sd), float(mean), float(n), float(den)
        except (TypeError, ValueError):
            continue
        if not (np.isfinite(sd_f) and np.isfinite(mean_f) and np.isfinite(n_f)
                and np.isfinite(den_f)):
            continue
        # THE COVERED BAND IS v0's UNDER BOTH SCALES. `meanest != 0` stays a
        # membership test even when `meanest` is not the denominator, so the
        # amendment ranks exactly the names v0 ranked and the twin is drawn from
        # exactly the same pool. Only the SCORE changes -- which is what "the
        # amendment names only the input" has to mean arithmetically, or the two
        # reads would differ by coverage as well as by construction.
        if n_f < int(min_numest) or mean_f == 0.0 or sd_f < 0.0 or den_f == 0.0:
            continue
        vals[int(pn)] = abs(sd_f / den_f)
    if len(vals) < int(min_names):
        raise SignalUnavailable(
            f"only {len(vals)} name(s) carried an IBES consensus with "
            f"numest >= {min_numest}, a non-zero meanest and a usable "
            f"{scale!r} denominator this month; a cross-sectional tercile over "
            f"fewer than {min_names} is a cut of the survivors, not of the "
            f"market")
    return _tercile_side(vals, side=side, tercile=tercile)


# --------------------------------------------------------------------------
# BOOK H — executive option-grant opportunistic timing
#
# TRIAL-DRAFT-H (UNSIGNED, 2026-09-14). `trans_code == 'A'` with
# `table == 'DERIV'`: the derivative GRANT AWARD rows that
# `scripts/sec_insider_bulk_load.py` discards when it distils
# `insider_events_v1.parquet` down to open-market purchases and sales. This is
# the first signal in this repository on that code, and the distinction from
# `TRIAL-INSIDER-IC` / `TRIAL-CMP-INSIDER-IC` / `TRIAL-BRAIN-003` -- all of them
# `trans_code == 'P'` -- is the code, not a re-cut of one.
#
# THE PRECURSOR IS THE HISTORY, NEVER THE GRANT BEING PRICED. Each (issuer,
# insider) pair is scored on grants FILED strictly before the month of
# selection; the grant currently being priced contributes nothing to its own
# score. That is invariant 2 of the mission section, and here it is the whole
# construction rather than a caveat on it.


#: TRIAL-DRAFT-H section 6 freezes THREE strictly-prior grants per (issuer,
#: insider) pair. Fewer is not a "history": a mean over two grants whose sign
#: pattern is the qualifying condition is one coin flip wearing a statistic's
#: clothes.
MIN_PRIOR_GRANTS = 3

#: The pair-level columns `option_grant_timing_score` reads. Named here so a
#: caller can be checked against them without running anything.
GRANT_TIMING_COLUMNS = ("permno", "owner_cik", "mean_pre", "mean_post",
                        "n_prior_grants")


def _rank_scores(order) -> dict:
    """{permno: float} descending, from an ALREADY-ORDERED sequence of permnos.

    The books here rank on a LEXICOGRAPHIC key (a cut variable, then a declared
    tie-break) and `run_monthly`'s selector contract is a list ordered
    best-first, which it builds by sorting a `{permno: score}` mapping. A single
    float cannot carry two keys without an epsilon that silently reorders when
    the first key's values happen to be close, so the order is computed once,
    here, and the returned score is the POSITION -- exact, and impossible to
    reorder by accident.
    """
    n = len(order)
    return {int(p): float(n - i) for i, p in enumerate(order)}


def option_grant_timing_score(frame, *, side: str = "top",
                              tercile: float = 2.0 / 3.0,
                              min_prior: int = MIN_PRIOR_GRANTS,
                              min_names: int = MIN_CHARACTERISTIC_NAMES) -> dict:
    """BOOK H. {permno: score} for the requested tercile of the grant-timing history.

    `frame` is ONE month of PAIR-level rows -- one row per (issuer, insider) --
    each carrying the mean market-adjusted 20-session return BEFORE and AFTER
    that pair's strictly-prior derivative grants, and how many such grants the
    means were taken over. The caller computes those means from grants whose
    `filing_date` is strictly earlier than the selection close; this function
    does the qualification, the aggregation and the cut, and nothing else.

    Three frozen steps, in this order (TRIAL-DRAFT-H section 6):

      1. a pair needs `n_prior_grants >= min_prior` (three) or it is dropped --
         not defaulted, not imputed;
      2. a pair QUALIFIES only where `mean_pre < 0 AND mean_post > 0`. That
         conjunction is the Daines mechanism written down: a price depressed
         into the grant and recovering out of it. A pair with a large
         `mean_post - mean_pre` built from two POSITIVE means is a momentum
         name, not an opportunistically timed grant, and excluding it here is
         what keeps the two apart;
      3. the issuer's statistic is the MEDIAN of its qualifying pairs'
         `mean_post - mean_pre`. The book trades `permno` and not `owner_cik`,
         and a median rather than a mean so that one insider with one extreme
         pair cannot carry an issuer into the tercile.

    An issuer with no qualifying pair carries NO SCORE and is absent from the
    result -- which is different from scoring zero, and the difference is the
    reason the replay's `pool_filter` and this function are separate things.

    The returned value is the issuer's RAW statistic, exactly as `qmj_rank`
    returns a raw `qmj`: Book H orders on one continuous variable and needs no
    tie-break beyond a deterministic one, so the caller sorts descending. Book I
    is the book with a lexicographic key, and `_rank_scores` is there for it.

    `side="bottom"` is the REPORTED bottom tercile; TRIAL-DRAFT-H section 8
    forbids trading it.
    """
    import numpy as np

    for c in GRANT_TIMING_COLUMNS:
        if c not in getattr(frame, "columns", ()):
            raise SignalUnavailable(
                f"the grant-history frame carries no {c!r} column; "
                f"option_grant_timing_score needs "
                f"{', '.join(GRANT_TIMING_COLUMNS)} and does not substitute a "
                f"different measure of grant timing. This is a REFUSAL and not "
                f"an empty cross-section: a book whose history table is absent "
                f"has not decided to hold nothing.")
    # Vectorised deliberately. The replay calls this once per month per cell
    # over a pair-level frame of tens of thousands of rows, and a Python loop
    # over those rows costs more than every other part of the job put together.
    pre = frame["mean_pre"].to_numpy(dtype=float, na_value=np.nan)
    post = frame["mean_post"].to_numpy(dtype=float, na_value=np.nan)
    n = frame["n_prior_grants"].to_numpy(dtype=float, na_value=np.nan)
    pn = frame["permno"].to_numpy(dtype="int64")
    ok = (np.isfinite(pre) & np.isfinite(post) & np.isfinite(n)
          & (n >= float(min_prior)) & (pre < 0.0) & (post > 0.0))
    if not ok.any():
        raise SignalUnavailable(
            f"no (issuer, insider) pair in this month carried a qualifying "
            f"grant history (>= {min_prior} strictly-prior DERIV grants with "
            f"mean pre-grant return < 0 and mean post-grant return > 0) out of "
            f"{len(frame)} pair-row(s)")
    stat = (post - pre)[ok]
    keys = pn[ok]
    order = np.argsort(keys, kind="mergesort")
    keys, stat = keys[order], stat[order]
    edges = np.flatnonzero(np.r_[True, keys[1:] != keys[:-1]])
    vals = {int(keys[a]): float(np.median(stat[a:b]))
            for a, b in zip(edges, np.r_[edges[1:], len(keys)])}
    if len(vals) < int(min_names):
        raise SignalUnavailable(
            f"only {len(vals)} issuer(s) carried a qualifying grant history "
            f"(>= {min_prior} strictly-prior DERIV grants with mean pre-grant "
            f"return < 0 and mean post-grant return > 0) this month; a "
            f"cross-sectional tercile over fewer than {min_names} is a cut of "
            f"the survivors, not of the market")
    return _tercile_side(vals, side=side, tercile=tercile)


# --------------------------------------------------------------------------
# BOOK I — buyback versus insider selling
#
# TRIAL-DRAFT-I (UNSIGNED, 2026-09-14). `comp__funda.prstkc` joined through
# `link_ccm` to `trans_code == 'S'` Form-4 sales. The claim is the CONJUNCTION:
# a repurchase while insiders are NOT selling is confirmation, a repurchase
# while they sell heavily is the agency-conflict cell. Both single legs are
# computed by this same function so that the falsifier ("the divergence must
# beat either leg alone") cannot differ from the book by which code path ran it.


#: The legs TRIAL-DRAFT-I declares. `divergence` is the PRIMARY and the only one
#: that may be traded. `bearish_divergence` is the reported agency-conflict cell
#: and section 8 forbids shorting it. The two `*_only` legs exist for section 5
#: clause 2 and are controls, never books.
BUYBACK_DIVERGENCE_LEGS = ("divergence", "bearish_divergence",
                           "buyback_only", "low_selling_only")

#: The per-name columns `buyback_insider_divergence` reads.
BUYBACK_DIVERGENCE_COLUMNS = ("permno", "buyback_flag", "buyback_intensity",
                              "sell_intensity")


def buyback_insider_divergence(frame, *, leg: str = "divergence",
                               tercile: float = 2.0 / 3.0,
                               min_names: int = MIN_CHARACTERISTIC_NAMES,
                               seed: int = 0) -> dict:
    """BOOK I. {permno: score} for one declared leg of the divergence.

    `frame` is ONE quarter of per-name rows already restricted to the covered
    band (a CCM-linked `prstkc` observation available within the trailing 18
    months AND Form-4 coverage in the trailing 12), carrying:

      `buyback_flag`        `prstkc > 0` on the most recent AVAILABLE annual row
      `buyback_intensity`   `prstkc / (csho * prcc_f)` from that SAME row
      `sell_intensity`      shares sold in the trailing 90 days as a share of
                            (sold + still held), from Form-4 `filing_date` rows

    A name with no sale in the window has `sell_intensity == 0`, and that is the
    SIGNAL and not a missing value -- which is why the caller must pass a zero
    and never a NaN for it. A NaN here is dropped, so a caller that confused the
    two would silently trade a different universe.

    The four legs, each frozen by TRIAL-DRAFT-I section 6:

      `divergence`         buyback_flag AND the BOTTOM tercile of
                           `sell_intensity`; ordered by `sell_intensity`
                           ascending, ties broken by `buyback_intensity`
                           DESCENDING -- the purest instance of the conjunction
                           first. THE PRIMARY.
      `bearish_divergence` buyback_flag AND the TOP tercile; REPORTED only.
      `buyback_only`       buyback_flag, the TOP tercile of `buyback_intensity`,
                           insider selling ignored.
      `low_selling_only`   the BOTTOM tercile of `sell_intensity` over the whole
                           covered band, the buyback flag ignored.

    `low_selling_only`'s tie-break is a SEEDED SHUFFLE and not `permno`, and the
    reason is arithmetic rather than stylistic: most covered names sell nothing
    in a 90-day window, so `sell_intensity` is exactly 0 for a large majority
    and a `permno` tie-break would return the same thirty low-numbered listings
    every quarter -- a near-zero-turnover portfolio of the oldest names in CRSP,
    which is a size-and-age bet and not a test of "does low insider selling
    alone pay". The shuffle makes it what section 5 clause 2 needs: a draw from
    the low-selling band. The other three legs order on a continuous variable
    and need no such device.
    """
    import numpy as np

    if leg not in BUYBACK_DIVERGENCE_LEGS:
        raise SignalUnavailable(
            f"unknown leg {leg!r}; expected one of {BUYBACK_DIVERGENCE_LEGS}. A "
            f"leg this function does not know is refused rather than defaulted "
            f"to the primary, because a silent fallback would publish the "
            f"book's own number under a control's name")
    for c in BUYBACK_DIVERGENCE_COLUMNS:
        if c not in getattr(frame, "columns", ()):
            raise SignalUnavailable(
                f"the divergence frame carries no {c!r} column; "
                f"buyback_insider_divergence needs "
                f"{', '.join(BUYBACK_DIVERGENCE_COLUMNS)} and does not "
                f"substitute a different measure of either leg")

    rows = []
    for pn, flag, bi, si in zip(frame["permno"], frame["buyback_flag"],
                                frame["buyback_intensity"],
                                frame["sell_intensity"]):
        try:
            pn_i, si_f = int(pn), float(si)
        except (TypeError, ValueError):
            continue
        if not np.isfinite(si_f):
            continue
        try:
            bi_f = float(bi)
        except (TypeError, ValueError):
            bi_f = float("nan")
        rows.append((pn_i, bool(flag), (bi_f if np.isfinite(bi_f) else 0.0), si_f))

    if leg in ("divergence", "bearish_divergence", "buyback_only"):
        rows = [r for r in rows if r[1]]
    if not rows:
        raise SignalUnavailable(
            f"no name in this block carried the {leg!r} leg's requirements; the "
            f"covered band was passed in with {len(frame)} row(s)")

    if leg == "buyback_only":
        vals = {pn: bi for pn, _f, bi, _si in rows}
        side = "top"
    else:
        vals = {pn: si for pn, _f, _bi, si in rows}
        side = "top" if leg == "bearish_divergence" else "bottom"
    if len(vals) < int(min_names):
        raise SignalUnavailable(
            f"only {len(vals)} name(s) carried the {leg!r} leg this block; a "
            f"cross-sectional tercile over fewer than {min_names} is a cut of "
            f"the survivors, not of the market")
    cut = _tercile_side(vals, side=side, tercile=tercile)
    keep = set(cut)
    sub = [r for r in rows if r[0] in keep]

    if leg == "buyback_only":
        order = [r[0] for r in sorted(sub, key=lambda r: (-r[2], r[0]))]
    elif leg == "bearish_divergence":
        order = [r[0] for r in sorted(sub, key=lambda r: (-r[3], -r[2], r[0]))]
    elif leg == "divergence":
        order = [r[0] for r in sorted(sub, key=lambda r: (r[3], -r[2], r[0]))]
    else:  # low_selling_only
        rng = np.random.default_rng(int(seed))
        ordered = sorted(sub, key=lambda r: r[0])
        jitter = {r[0]: float(x) for r, x in zip(ordered, rng.random(len(ordered)))}
        order = [r[0] for r in sorted(sub, key=lambda r: (r[3], jitter[r[0]],
                                                          r[0]))]
    return _rank_scores(order)


# --------------------------------------------------------------------------
# BOOK D (lane B) — the abstention book's confidence
#
# spec_first_books.md §D.2 names two triggers and says not to block on L2: v0 is
# R2's own digest CONFIDENCE, v1 is the arena composite's cross-sectional
# extremity. v1 is what is wired, because R2's digest covers a handful of names
# a month and an abstention book needs a number for every name it might hold.
# `COMPOSITE_WEIGHTS` is 99.5% 12-1 momentum for one-factor names (CLAUDE.md
# THE BOTTLENECK), so the cross-sectional z of `mom_12_1` IS the composite's
# extremity for almost every name, and saying that out loud is cheaper than
# pretending a six-weight blend is being computed.


def confidence_z(values: dict) -> dict:
    """{name: cross-sectional z} of a trailing statistic.

    Signed, not absolute: an abstention book that deviated into a name because
    its momentum was extremely NEGATIVE would be an abstention book buying the
    worst names in the market with high confidence.
    """
    import numpy as np
    import pandas as pd

    if len(values) < 2:
        raise SignalUnavailable(
            f"a cross-sectional z needs at least two names; got {len(values)}")
    s = pd.Series(values, dtype=float)
    z = _zscore(s)
    return {str(k): float(v) for k, v in zip(s.index, z) if np.isfinite(v)}


# --------------------------------------------------------------------------
# LANE D — the first-hour typed-event placeholder
#
# L2's typed-event vocabulary is not built (gate order N-C -> N-D -> N-F -> L2),
# and the roadmap says do not wait for it. The placeholder is the OBSERVABLE
# half of the same statement: a headline whose stamp is the venue's own
# (`pit_grade: native_stamp`) and whose `first_seen_utc` falls inside the first
# trading hour. When L2 lands, the TYPE is added to this gate; the window and
# the PIT grade do not move.

FIRST_HOUR_START = time(9, 30)
FIRST_HOUR_END = time(10, 30)
NEWS_SOURCE = "alpaca_benzinga_news"


def news_corpus_dir() -> Path:
    from backend.config import OPTIMUS_LEDGER_DIR
    return OPTIMUS_LEDGER_DIR / "news_corpus" / NEWS_SOURCE


def first_hour_headlines(rows, session: date) -> dict:
    """{symbol: n headlines} natively stamped inside 09:30-10:30 ET on `session`.

    `rows` are corpus records as written by the N-A writer. Two gates, both
    named on the receipt: `pit_grade == "native_stamp"` (a scraped or inferred
    stamp is not a time we may act on) and `first_seen_utc` inside the window
    (the time WE could first have seen it, which is what an intraday book is
    allowed to use — `published_utc` is the venue's claim about itself).
    """
    from zoneinfo import ZoneInfo

    et = ZoneInfo("America/New_York")
    lo = datetime.combine(session, FIRST_HOUR_START, tzinfo=et)
    hi = datetime.combine(session, FIRST_HOUR_END, tzinfo=et)
    out: dict[str, float] = {}
    for r in rows:
        if str(r.get("pit_grade") or "") != "native_stamp":
            continue
        raw = str(r.get("first_seen_utc") or "")
        if not raw:
            continue
        try:
            seen = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        if seen.tzinfo is None:
            seen = seen.replace(tzinfo=timezone.utc)
        if not (lo <= seen <= hi):
            continue
        for t in (r.get("tickers") or []):
            sym = str(t).upper().strip()
            if sym:
                out[sym] = out.get(sym, 0.0) + 1.0
    return out


def load_news_rows(session: date, *, corpus_dir=None) -> list[dict]:
    """The corpus file for one day, or an empty list when the day is absent.

    Each row is PIT-graded at read time (`news_registry.grade_row`).
    """
    import json

    d = Path(corpus_dir) if corpus_dir is not None else news_corpus_dir()
    p = d / f"{session.isoformat()}.jsonl"
    if not p.is_file():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    # Graded at READ time (wave-1 row 12): a row published > 30 days before we
    # first saw it is `pit_grade: archive`, so the `native_stamp` gate below
    # can never read a 2015 headline stamped with its 2026 ingest time.
    from backend.services.news_registry import grade_row
    return [grade_row(r) for r in rows]


# --------------------------------------------------------------------------
# THE REGISTRY — how `book_cadence.decide_weights` reaches all of the above
#
# Every adapter takes the same four keywords and returns {symbol: value} or
# raises `SignalUnavailable`. A book whose signal is not in here and not in
# `book_cadence.SUPPORTED_SIGNALS` is refused by name, unchanged.


def _trailing_returns(bars, symbols: Sequence[str], asof: date, *,
                      lookback: int, skip: int = 0) -> dict:
    import pandas as pd

    ts = pd.Timestamp(asof)
    sub = bars[(bars["date"] <= ts) & (bars["symbol"].isin(list(symbols)))]
    if sub.empty:
        raise SignalUnavailable(f"the local bars hold no session on or before {asof}")
    wide = sub.pivot_table(index="date", columns="symbol", values="close",
                           aggfunc="last").sort_index()
    need = int(lookback) + int(skip) + 1
    if len(wide) < need:
        raise SignalUnavailable(
            f"this signal needs {need} sessions ending {asof}; the local bars "
            f"hold {len(wide)}")
    w = wide.iloc[-need:]
    end = w.iloc[-1 - int(skip)]
    ratio = end / w.iloc[0] - 1.0
    return {str(k): float(v) for k, v in ratio.items() if pd.notna(v)}


def _adapter_si_turnover(*, book, bars, symbols, asof, **_) -> dict:
    """Book A. Refuses outside the built panel rather than holding nothing."""
    panel = load_short_interest(asof)
    scores = si_turnover_composite(panel, asof)
    # The panel is keyed on CRSP permno and the local bars are keyed on ticker.
    # No permno<->ticker map exists for the 2025-26 bar vintage (CRSP ends
    # 2024-12-31), so a FORWARD decision on this book is a refusal, by name.
    # The historical replication is `scripts/night_first_books_replay.py`, which
    # works in permno space and needs no map.
    raise SignalUnavailable(
        f"the short-interest composite resolved {len(scores)} CRSP permno(s) at "
        f"{asof}, and the local bars are keyed on ticker with no permno map for "
        f"the 2025-26 vintage (CRSP ends 2024-12-31). This book MARKS but does "
        f"not DECIDE forward until the FINRA forward leg is ingested; its "
        f"1990-2024 evidence comes from the replay job, in permno space.")


def _adapter_insider_cluster(*, book, bars, symbols, asof, **_) -> dict:
    """Book B. The one panel of the four that reaches 2026 on TICKERS."""
    import pandas as pd

    buys = load_insider_buys(asof)
    sessions = sorted(pd.to_datetime(bars["date"].unique()))
    clusters = cluster_lengths(buys, sessions=sessions)
    params = dict((book.strategy.engine_params or {}).get("cluster") or {})
    spans = tuple(params.get("spans") or FRONTIER_SPAN_DAYS)
    window = int(params.get("window_days", 31))
    hit = cluster_eligibility(clusters, asof, spans=spans, window_days=window)
    eligible = {s: v for s, v in hit.items() if s in set(symbols)}
    if not eligible:
        raise SignalUnavailable(
            f"no {list(spans)}-day insider cluster filed in the {window} day(s) "
            f"ending {asof} landed on a name inside the book's universe "
            f"({len(hit)} cluster name(s) found, {len(symbols)} in universe). "
            f"The book holds nothing rather than holding something else.")
    return eligible


def _adapter_overhang(*, book, bars, symbols, asof, **_) -> dict:
    """Book C. Needs shares outstanding, which ticker bars do not carry."""
    raise SignalUnavailable(
        "the Grinblatt-Han reference price weights past prices by TURNOVER, and "
        "turnover needs shares outstanding, which the 2025-26 ticker bars do "
        "not carry and no offline panel supplies for that vintage. This book "
        "MARKS but does not DECIDE forward; its evidence comes from the replay "
        "job on CRSP, where `shrout` exists.")


def _adapter_confidence_z(*, book, bars, symbols, asof, **_) -> dict:
    """Book D (abstention). Bars-only, so it decides from the first pass."""
    mom = _trailing_returns(bars, symbols, asof, lookback=231, skip=21)
    return confidence_z(mom)


def _adapter_first_hour_news(*, book, bars, symbols, asof, **_) -> dict:
    """Lane D's placeholder for L2's typed event."""
    rows = load_news_rows(asof)
    if not rows:
        raise SignalUnavailable(
            f"no `{NEWS_SOURCE}` corpus file for {asof}. The N-A writer fills it; "
            f"a day with no file is a day the pull did not run, which is not the "
            f"same fact as a day with no headlines.")
    counts = first_hour_headlines(rows, asof)
    hit = {s: v for s, v in counts.items() if s in set(symbols)}
    if not hit:
        raise SignalUnavailable(
            f"no natively-stamped headline was first seen inside "
            f"{FIRST_HOUR_START}-{FIRST_HOUR_END} ET on {asof} for any name in "
            f"the book's universe ({len(rows)} corpus row(s) read). A backfilled "
            f"corpus stamps `first_seen_utc` at PULL time, so this gate is empty "
            f"by construction on backfilled days and only fires on days the "
            f"puller ran live during the session.")
    return hit


REGISTRY: dict[str, Callable[..., dict]] = {
    "short_interest_low_x_turnover_high": _adapter_si_turnover,
    "insider_cluster_len": _adapter_insider_cluster,
    "overhang_conditioned_reaction": _adapter_overhang,
    "abstention_confidence_z": _adapter_confidence_z,
    "native_stamped_headline_in_first_hour": _adapter_first_hour_news,
}


def compute(name: str, **kw) -> dict:
    """Dispatch by declared signal name, or refuse by name."""
    fn = REGISTRY.get(str(name))
    if fn is None:
        raise SignalUnavailable(
            f"{name!r} is not a registered book signal; registered: "
            f"{sorted(REGISTRY)}")
    return fn(**kw)


__all__ = ["FIRST_HOUR_END", "FIRST_HOUR_START", "FRONTIER_SPAN_DAYS",
           "MIN_CHARACTERISTIC_NAMES", "MIN_CLUSTER_INSIDERS",
           "MIN_ESTIMATES_FOR_DISPERSION", "REGISTRY", "SAME_DAY_SPAN",
           "SEASONALITY_COLUMNS", "SEASONALITY_COLUMNS_NEAR",
           "SignalUnavailable", "capital_gains_overhang", "cluster_eligibility",
           "cluster_lengths", "compute", "confidence_z", "first_hour_headlines",
           "forecast_dispersion", "load_insider_buys", "load_news_rows",
           "load_short_interest", "overhang_conditioned_ranks", "qmj_rank",
           "seasonality_score", "si_turnover_composite"]
