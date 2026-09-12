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
                               tercile: float = 2.0 / 3.0) -> dict:
    """{name: CGO} for GOOD-NEWS names in the top overhang tercile.

    The eligible set is gated on the EVENT SIGN first and ranked on overhang
    inside it. That order is the mechanism: this is a conditioner, not a
    two-factor blend, and a blend would be a different book.
    """
    import numpy as np

    good = {k: float(v) for k, v in cgo.items()
            if float(event_sign.get(k, 0.0)) > 0 and np.isfinite(v)}
    if not good:
        raise SignalUnavailable(
            "no name carried BOTH a positive event sign and a computable "
            "overhang this period; the conditioner has an empty eligible set "
            "rather than a weak one")
    cut = float(np.quantile(list(good.values()), tercile))
    return {k: v for k, v in good.items() if v >= cut}


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
    """The corpus file for one day, or an empty list when the day is absent."""
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
    return rows


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
           "MIN_CLUSTER_INSIDERS", "REGISTRY", "SAME_DAY_SPAN",
           "SignalUnavailable", "capital_gains_overhang", "cluster_eligibility",
           "cluster_lengths", "compute", "confidence_z", "first_hour_headlines",
           "load_insider_buys", "load_news_rows", "load_short_interest",
           "overhang_conditioned_ranks", "si_turnover_composite"]
