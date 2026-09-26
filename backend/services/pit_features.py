"""Six point-in-time columns from the 2026-09-26 research families (chunk C).

Spec: `docs/research_notes/2026-09-26/research_families_to_pit_features.md`
§3 ("six to build first") and §5 (the analyst trio). Session-order rule 4:
*every concept becomes a PIT column; a family that cannot name its observable,
its PIT rule and its source file is not registered.* Each column below names
all three.

THE ONE PIT RULE, UNIFORM ACROSS ALL SIX COLUMNS
================================================
A row dated `d` uses ONLY input rows dated STRICTLY BEFORE `d`:

    bars          date            < d      (so it is acted on at d's open)
    revisions     event_date      < d      (revision_flow's own convention)
    news          first_seen_utc  < d      (NEVER published_utc -- see below)
    actor claims  resolved_at     < d      (public_at + RESOLVE_DAYS)
    filings       filed + LAG     < d      (fundamental_features' join rule)

That is one session more conservative than `xs_ranker.build_features` (whose
row `t` includes `t`'s close). Joining these columns onto an xs_ranker panel
therefore only ever ADDS a day of delay; it can never add foresight.

Each column carries a `<col>_n` support count, and the column is NaN -- never
0 -- when its support is below the declared minimum (`MIN_SUPPORT`). Two
columns are interactions whose value may legitimately be 0 (the conditioning
event is observed and absent); they are NaN only when an input is unavailable.

THE COLUMNS
===========
analyst_skill_weight   net target raises minus lowers over 90 days, each
                       revision weighted by its broker's HELD-OUT reliability
                       from the IBES actor corpus (`ibes_graded.parquet`,
                       FINDING 2026-08-23 RELIABILITY_PERSISTS). Reliability is
                       re-estimated walk-forward at every date from claims whose
                       63-session outcome had resolved before that date; an
                       unmapped or unmeasured broker gets the prior weight 1.0.
max_21                 lottery: max daily return over the trailing 21 sessions
                       (Bali, Cakici & Whitelaw 2011).
attention_z            news count over the last 5 sessions vs the name's own
                       126-session baseline, bucketed by `first_seen_utc`.
                       The corpus stamps `first_seen_utc` at PULL time and began
                       2026-09-11, so this column has NO history: forward-only.
fomo_reversal          rev_5 x 1{attention_z > 2}: the 5-session move, kept
                       only when it co-occurred with an attention spike (note
                       §3.4: REV-02 conditioned on z > 2). 0 = no spike.
first_mover_rank       for the most recent revision CLUSTER on the name (a
                       same-direction revision with no other firm's same-
                       direction revision in the 7 days before it), sign x the
                       first mover's percentile of historical LEADERSHIP
                       (mean number of distinct firms that followed its
                       first-mover revisions within 7 days; Cooper, Day &
                       Lewis 2001). Leadership is measured only from clusters
                       whose follow window closed before `d`.
pricing_power_cost_pressure
                       annual gross-margin change x cost-pressure excess, where
                       cost pressure is the market-wide median annual COGS
                       growth over filings public in the last 365 days minus
                       its own trailing-3-year median. NaN when cost pressure
                       is not ON (<= 0): pricing power under cost pressure is
                       unobservable when there is no pressure. The note asks
                       for NAICS PPI from FRED; that series is NOT on disk, so
                       the default is this in-house proxy and the receipt says
                       so. A PPI series can be passed as `cost_pressure=`.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

FEATURE_COLUMNS: tuple[str, ...] = (
    "analyst_skill_weight", "max_21", "attention_z", "fomo_reversal",
    "first_mover_rank", "pricing_power_cost_pressure",
)
SUPPORT_COLUMNS: tuple[str, ...] = tuple(f"{c}_n" for c in FEATURE_COLUMNS)

#: Declared minimum support per column. Below it the column is NaN.
MIN_SUPPORT: dict[str, int] = {
    "analyst_skill_weight": 2,        # revision events in the 90-day window
    "max_21": 15,                     # valid daily returns in the 21-session window
    "attention_z": 60,                # covered baseline sessions (of 126)
    "fomo_reversal": 60,              # inherits attention_z's baseline
    "first_mover_rank": 10,           # the first mover's resolved first-mover clusters
    "pricing_power_cost_pressure": 2,  # annual gross-margin observations (need a change)
}

# ── parameters (declared once, not swept) ────────────────────────────────────
SKILL_WINDOW_DAYS = 90
RESOLVE_DAYS = 92            # 63 sessions ~ 91 calendar days, +1 margin
SKILL_SHRINK_K = 20          # w = n / (n + K), the prereg family's convention
SKILL_SLOPE = 10.0           # weight = 1 + 10 * shrunk edge  (edge +0.05 -> 1.5)
SKILL_CLIP = (0.5, 1.5)
SKILL_PRIOR = 1.0
MAX_WINDOW = 21
REV_WINDOW = 5
ATT_RECENT = 5
ATT_BASELINE = 126
ATT_MIN_RECENT_COVERED = 3
ATT_SPIKE_Z = 2.0
CLUSTER_GAP_DAYS = 7
FIRST_MOVER_LOOKBACK_DAYS = 30
FUND_LAG_DAYS = 2
FUND_STALE_DAYS = 460
ANNUAL_DAYS = (350, 380)
YOY_END_GAP = (330, 400)
COST_WINDOW_DAYS = 365
COST_BASE_YEARS = 3
COST_BASE_MIN_POINTS = 12
COST_MIN_FILERS = 100
BAR_STALE_DAYS = 10

_TICKER_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9.\-]*")


def _optimus() -> Path:
    from backend import config as _cfg
    return Path(_cfg.OPTIMUS_LEDGER_DIR)


# ── small helpers ────────────────────────────────────────────────────────────

def _dates(panel_dates: Iterable) -> pd.DatetimeIndex:
    d = pd.DatetimeIndex(sorted({pd.Timestamp(x).normalize() for x in panel_dates}))
    if d.tz is not None:
        d = d.tz_localize(None)
    return d


def _naive(s: pd.Series) -> pd.Series:
    s = pd.to_datetime(s, utc=True, errors="coerce")
    return s.dt.tz_convert("UTC").dt.tz_localize(None)


def _empty(tickers: Iterable[str], dates: pd.DatetimeIndex) -> pd.DataFrame:
    idx = pd.MultiIndex.from_product([sorted(set(tickers)), dates], names=["ticker", "date"])
    out = pd.DataFrame(index=idx)
    for c in FEATURE_COLUMNS:
        out[c] = np.nan
        out[f"{c}_n"] = 0
    return out


def _merge_asof_strict(left: pd.DataFrame, right: pd.DataFrame, *, by: str,
                       left_on: str, right_on: str, tolerance_days: int | None = None
                       ) -> pd.DataFrame:
    """For each left row, the last right row with right_on STRICTLY < left_on."""
    kw: dict[str, Any] = {}
    if tolerance_days is not None:
        kw["tolerance"] = pd.Timedelta(days=tolerance_days)
    return pd.merge_asof(left.sort_values(left_on), right.sort_values(right_on),
                         left_on=left_on, right_on=right_on, by=by,
                         direction="backward", allow_exact_matches=False, **kw)


def _grid(tickers: Iterable[str], dates: pd.DatetimeIndex) -> pd.DataFrame:
    t = sorted(set(tickers))
    return pd.DataFrame({"ticker": np.repeat(t, len(dates)),
                         "date": np.tile(dates.values, len(t))})


# ── 1. bars: max_21 and the rev_5 leg of fomo_reversal ───────────────────────

def bar_features(bars: pd.DataFrame, dates: pd.DatetimeIndex) -> pd.DataFrame:
    """(ticker, date) -> max_21, max_21_n, rev_5 from bars dated < date."""
    b = bars[["symbol", "date", "close"]].copy()
    b["date"] = pd.to_datetime(b["date"])
    b = b.sort_values(["symbol", "date"], kind="mergesort").reset_index(drop=True)
    g = b.groupby("symbol", sort=False)["close"]
    ret = g.pct_change(fill_method=None)
    b["ret"] = ret.where(np.isfinite(ret))
    gr = b.groupby("symbol", sort=False)["ret"]
    b["max_21"] = gr.rolling(MAX_WINDOW, min_periods=1).max().reset_index(level=0, drop=True)
    b["max_21_n"] = gr.rolling(MAX_WINDOW, min_periods=1).count().reset_index(level=0, drop=True)
    b["rev_5"] = g.pct_change(REV_WINDOW, fill_method=None)
    b = b.rename(columns={"symbol": "ticker", "date": "bar_date"})
    left = _grid(b["ticker"].unique(), dates)
    if left.empty:
        return pd.DataFrame(columns=["ticker", "date", "max_21", "max_21_n", "rev_5"])
    m = _merge_asof_strict(left, b[["ticker", "bar_date", "max_21", "max_21_n", "rev_5"]],
                           by="ticker", left_on="date", right_on="bar_date",
                           tolerance_days=BAR_STALE_DAYS)
    m["max_21_n"] = m["max_21_n"].fillna(0).astype(int)
    m.loc[m["max_21_n"] < MIN_SUPPORT["max_21"], "max_21"] = np.nan
    return m[["ticker", "date", "max_21", "max_21_n", "rev_5"]]


# ── 2. news: attention_z by first_seen_utc ───────────────────────────────────

def _parse_tickers(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, (list, tuple, np.ndarray)):
        return [str(x).strip().upper() for x in v if str(x).strip()]
    return [t.upper() for t in _TICKER_TOKEN.findall(str(v))]


def news_frame(news_rows: Iterable[dict] | pd.DataFrame) -> pd.DataFrame:
    """Rows -> (ticker, first_seen) long frame. ONLY `first_seen_utc` is read.

    `published_utc` is ignored on purpose: the corpus backfills Benzinga items
    published in 2015 with a first-seen stamp of 2026-09, and the published
    stamp of an `index_state` feed can move after the fact (invariant 20).
    """
    recs = news_rows.to_dict("records") if isinstance(news_rows, pd.DataFrame) else list(news_rows)
    out = []
    stamps = []
    for r in recs:
        fs = r.get("first_seen_utc")
        if not fs:
            continue
        stamps.append(fs)
        for t in _parse_tickers(r.get("tickers")):
            out.append((t, fs))
    df = pd.DataFrame(out, columns=["ticker", "first_seen"])
    df["first_seen"] = _naive(df["first_seen"])
    # every row's own stamp, ticker-less ones included, marks its session COVERED
    df.attrs["coverage_stamps"] = stamps
    return df


def _session_of(ts: pd.Series, sessions: pd.DatetimeIndex) -> pd.Series:
    """Map a timestamp to the first session whose DATE >= the stamp's UTC date."""
    day = ts.dt.normalize().values.astype("datetime64[ns]")
    pos = np.searchsorted(sessions.values.astype("datetime64[ns]"), day, side="left")
    ok = pos < len(sessions)
    vals = np.full(len(ts), np.datetime64("NaT"), dtype="datetime64[ns]")
    vals[ok] = sessions.values[pos[ok]]
    return pd.Series(vals, index=ts.index)


def attention_features(news: pd.DataFrame, dates: pd.DatetimeIndex,
                       sessions: pd.DatetimeIndex, tickers: Iterable[str]) -> pd.DataFrame:
    """(ticker, date) -> attention_z, attention_z_n from items first seen < date.

    A session with NO corpus row at all is UNCOVERED and leaves the baseline:
    a day the puller did not run is not a day with zero headlines.
    """
    cov_stamps = pd.Series(news.attrs.get("coverage_stamps", []), dtype=object)
    covered = (pd.DatetimeIndex(sorted(set(_session_of(_naive(cov_stamps), sessions).dropna())))
               if len(cov_stamps) else pd.DatetimeIndex([]))
    counts: dict[str, pd.Series] = {}
    if len(news):
        n = news.assign(session=_session_of(news["first_seen"], sessions)).dropna(subset=["session"])
        for t, g in n.groupby("ticker"):
            counts[t] = g.groupby("session").size().astype(float)
    tick = sorted(set(tickers))
    svals = sessions.values.astype("datetime64[ns]")
    rows = []
    for d in dates:
        # an item bucketed to session s was first seen on or before s's
        # calendar date, so sessions strictly before d keep it strictly past.
        j = int(np.searchsorted(svals, np.datetime64(d, "ns"), side="left"))
        recent = sessions[max(0, j - ATT_RECENT):j]
        base = sessions[max(0, j - ATT_RECENT - ATT_BASELINE):max(0, j - ATT_RECENT)]
        rec_c = recent[recent.isin(covered)]
        base_c = base[base.isin(covered)]
        nb = len(base_c)
        if nb < MIN_SUPPORT["attention_z"] or len(rec_c) < ATT_MIN_RECENT_COVERED:
            rows.extend((t, d, np.nan, nb) for t in tick)
            continue
        for t in tick:
            ct = counts.get(t, pd.Series(dtype=float))
            bvec = ct.reindex(base_c, fill_value=0.0).to_numpy()
            rvec = ct.reindex(rec_c, fill_value=0.0).to_numpy()
            mu = bvec.mean()
            sd = max(bvec.std(ddof=1) if nb > 1 else 0.0, float(np.sqrt(max(mu, 1.0 / nb))))
            k = len(rvec)
            rows.append((t, d, float((rvec.sum() - k * mu) / (np.sqrt(k) * sd)), nb))
    return pd.DataFrame(rows, columns=["ticker", "date", "attention_z", "attention_z_n"])


# ── 3. revisions: analyst_skill_weight and first_mover_rank ─────────────────

def firm_reliability(actor_corpus: pd.DataFrame, asof: pd.Timestamp,
                     firm_col: str = "estimid") -> pd.DataFrame:
    """Per-broker held-out edge from claims RESOLVED before `asof`.

    edge = hit rate - the hit rate expected from the broker's own direction mix
    (FINDING 2026-08-23 §3: buy and sell claims resolve at different base
    rates, so a blended null credits a pure-buy broker with the gap).
    """
    res = _naive(actor_corpus["public_at"]) + pd.Timedelta(days=RESOLVE_DAYS)
    a = actor_corpus.loc[(res < asof).values, [firm_col, "direction", "outcome"]].dropna()
    if a.empty:
        return pd.DataFrame(columns=["n", "edge", "shrunk", "weight"])
    a = a.assign(outcome=a["outcome"].astype(float))
    base = a.groupby("direction")["outcome"].mean()
    a = a.assign(expected=a["direction"].map(base).astype(float))
    g = a.groupby(firm_col)
    out = pd.DataFrame({"n": g.size(), "edge": g["outcome"].mean() - g["expected"].mean()})
    out["shrunk"] = out["edge"] * out["n"] / (out["n"] + SKILL_SHRINK_K)
    out["weight"] = (1.0 + SKILL_SLOPE * out["shrunk"]).clip(*SKILL_CLIP)
    return out


def _prep_revisions(revisions: pd.DataFrame, firm_map: dict | None) -> pd.DataFrame:
    from backend.services.revision_flow import prepare
    p = prepare(revisions)
    p = p[p["sign"] != 0].copy()
    p["estimid"] = p["firm"].map(firm_map or {})
    return p.reset_index(drop=True)


def skill_features(prep: pd.DataFrame, actor_corpus: pd.DataFrame | None,
                   dates: pd.DatetimeIndex) -> pd.DataFrame:
    rows = []
    times = prep["t"].values.astype("datetime64[ns]")
    for d in dates:
        lo = np.searchsorted(times, np.datetime64(d - pd.Timedelta(days=SKILL_WINDOW_DAYS), "ns"), "left")
        hi = np.searchsorted(times, np.datetime64(d, "ns"), "left")        # t < d strict
        win = prep.iloc[lo:hi]
        if win.empty:
            continue
        if actor_corpus is not None and len(actor_corpus):
            rel = firm_reliability(actor_corpus, d)["weight"]
            w = win["estimid"].map(rel).astype(float).fillna(SKILL_PRIOR)
        else:
            w = pd.Series(SKILL_PRIOR, index=win.index)
        f = pd.DataFrame({"analyst_skill_weight": (win["sign"] * w).groupby(win["ticker"]).sum(),
                          "analyst_skill_weight_n": win.groupby("ticker").size()})
        f.index.name = "ticker"
        rows.append(f.reset_index().assign(date=d))
    if not rows:
        return pd.DataFrame(columns=["ticker", "date", "analyst_skill_weight",
                                     "analyst_skill_weight_n"])
    out = pd.concat(rows, ignore_index=True)
    out.loc[out["analyst_skill_weight_n"] < MIN_SUPPORT["analyst_skill_weight"],
            "analyst_skill_weight"] = np.nan
    return out


def revision_clusters(prep: pd.DataFrame) -> pd.DataFrame:
    """Flag first movers and count their distinct followers within 7 days.

    First mover: no OTHER firm revised the same name in the same direction in
    `[t-7d, t)`. Followers: distinct other firms revising the same name in the
    same direction in `(t, t+7d]`, knowable only at `resolved_at = t + 7d`.
    """
    gap = np.timedelta64(CLUSTER_GAP_DAYS, "D")
    first = np.ones(len(prep), dtype=bool)
    foll = np.zeros(len(prep), dtype=float)
    for _key, idx in prep.groupby(["ticker", "sign"], sort=False).indices.items():
        t = prep["t"].values[idx].astype("datetime64[ns]")
        f = prep["firm"].values[idx]
        lo = np.searchsorted(t, t - gap, "left")
        hi = np.searchsorted(t, t + gap, "right")
        for k in range(len(idx)):
            prev_mask = t[lo[k]:k] < t[k]
            prev = f[lo[k]:k][prev_mask]
            if len(prev) and np.any(prev != f[k]):
                first[idx[k]] = False
            nxt = f[k + 1:hi[k]][t[k + 1:hi[k]] > t[k]]
            foll[idx[k]] = len(set(nxt) - {f[k]})
    return prep.assign(first_mover=first, followers=foll,
                       resolved_at=prep["t"] + pd.Timedelta(days=CLUSTER_GAP_DAYS))


def first_mover_features(clus: pd.DataFrame, dates: pd.DatetimeIndex) -> pd.DataFrame:
    fm = clus[clus["first_mover"]].sort_values("t", kind="mergesort")
    rows = []
    for d in dates:
        hist = fm[fm["resolved_at"] < d]
        recent = fm[(fm["t"] < d) & (fm["t"] >= d - pd.Timedelta(days=FIRST_MOVER_LOOKBACK_DAYS))]
        if hist.empty or recent.empty:
            continue
        lead = hist.groupby("firm")["followers"].agg(["mean", "size"])
        pct = lead.loc[lead["size"] >= MIN_SUPPORT["first_mover_rank"], "mean"].rank(pct=True)
        last = recent.groupby("ticker").tail(1)            # sorted by t: the latest cluster
        n = last["firm"].map(lead["size"]).fillna(0).astype(int)
        val = last["sign"].astype(float) * last["firm"].map(pct).astype(float)
        rows.append(pd.DataFrame({"ticker": last["ticker"].values, "date": d,
                                  "first_mover_rank": val.values,
                                  "first_mover_rank_n": n.values}))
    if not rows:
        return pd.DataFrame(columns=["ticker", "date", "first_mover_rank", "first_mover_rank_n"])
    out = pd.concat(rows, ignore_index=True)
    out.loc[out["first_mover_rank_n"] < MIN_SUPPORT["first_mover_rank"], "first_mover_rank"] = np.nan
    return out


# ── 4. fundamentals: pricing_power_cost_pressure ────────────────────────────

def annual_margins(facts: pd.DataFrame) -> pd.DataFrame:
    """(ticker, end) annual revenue/cogs at FIRST filing; gm, gm_chg, cogs_growth."""
    cols = ["ticker", "end", "filed", "gm", "gm_chg", "cogs_growth", "n_years"]
    f = facts[facts["fact"].isin(["revenue", "cogs"])].copy()
    f = f[f["period_days"].between(*ANNUAL_DAYS)]
    if f.empty:
        return pd.DataFrame(columns=cols)
    f["filed"] = pd.to_datetime(f["filed"])
    f["end"] = pd.to_datetime(f["end"])
    # the FIRST filing that stated this (ticker, fact, end): a later 10-K's
    # comparative column restates it with a later `filed`, which is not when
    # the number became public.
    f = f.sort_values("filed", kind="mergesort").drop_duplicates(["ticker", "fact", "end"], keep="first")
    w = f.pivot_table(index=["ticker", "end"], columns="fact", values="val", aggfunc="first")
    if not {"revenue", "cogs"} <= set(w.columns):
        return pd.DataFrame(columns=cols)
    w = w.join(f.groupby(["ticker", "end"])["filed"].max()).reset_index()   # both facts public
    w = w.dropna(subset=["revenue", "cogs"])
    w = w[w["revenue"] > 0].sort_values(["ticker", "end"]).reset_index(drop=True)
    w["gm"] = (w["revenue"] - w["cogs"]) / w["revenue"]
    g = w.groupby("ticker")
    yoy = (w["end"] - g["end"].shift(1)).dt.days.between(*YOY_END_GAP)
    w["gm_chg"] = (w["gm"] - g["gm"].shift(1)).where(yoy)
    pc = g["cogs"].shift(1)
    w["cogs_growth"] = ((w["cogs"] / pc) - 1.0).where(yoy & (pc > 0))
    w["n_years"] = g.cumcount() + 1
    return w[cols]


def cost_pressure_proxy(margins: pd.DataFrame, dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Market-wide median annual COGS growth over filings public in the last
    365 days, minus its own trailing-3-year median (on a month-end grid)."""
    m = margins.dropna(subset=["cogs_growth"]).copy()
    if m.empty or not len(dates):
        return pd.DataFrame({"date": dates, "cost_pressure": np.nan, "n_filers": 0})
    m["avail"] = m["filed"] + pd.Timedelta(days=FUND_LAG_DAYS)
    m = m.sort_values("avail")
    av = m["avail"].values.astype("datetime64[ns]")
    cg = m["cogs_growth"].clip(-0.9, 5.0).values

    def level(d: pd.Timestamp) -> tuple[float, int]:
        lo = np.searchsorted(av, np.datetime64(d - pd.Timedelta(days=COST_WINDOW_DAYS), "ns"), "left")
        hi = np.searchsorted(av, np.datetime64(d, "ns"), "left")          # avail < d strict
        n = int(hi - lo)
        return (float(np.median(cg[lo:hi])) if n >= COST_MIN_FILERS else np.nan), n

    grid = pd.date_range(m["avail"].min() + pd.offsets.MonthEnd(0), dates.max(), freq="ME")
    series = pd.Series({d: level(d)[0] for d in grid}, dtype=float)
    out = []
    for d in dates:
        cur, n = level(d)
        past = series[(series.index < d) &
                      (series.index >= d - pd.DateOffset(years=COST_BASE_YEARS))].dropna()
        base = past.median() if len(past) >= COST_BASE_MIN_POINTS else np.nan
        out.append((d, cur - base if np.isfinite(cur) and np.isfinite(base) else np.nan, n))
    return pd.DataFrame(out, columns=["date", "cost_pressure", "n_filers"])


def pricing_power_features(facts: pd.DataFrame, dates: pd.DatetimeIndex,
                           tickers: Iterable[str],
                           cost_pressure: pd.Series | None = None) -> tuple[pd.DataFrame, dict]:
    mg = annual_margins(facts)
    mg = mg.assign(avail=mg["filed"] + pd.Timedelta(days=FUND_LAG_DAYS))
    left = _grid(tickers, dates)
    m = _merge_asof_strict(left, mg[["ticker", "avail", "gm_chg", "n_years"]],
                           by="ticker", left_on="date", right_on="avail",
                           tolerance_days=FUND_STALE_DAYS)
    if cost_pressure is not None:
        cp = cost_pressure.sort_index()
        cpd = pd.DataFrame({"date": dates, "cost_pressure": [
            float(cp[cp.index < d].iloc[-1]) if (cp.index < d).any() else np.nan for d in dates],
            "n_filers": np.nan})
        source = "caller-supplied series (asof strictly before each date)"
    else:
        cpd = cost_pressure_proxy(mg, dates)
        source = ("IN-HOUSE PROXY: market-wide median annual COGS growth (SEC facts, "
                  "filed+2d, last 365d) minus its trailing-3y median. The note's NAICS "
                  "PPI (FRED) is NOT on disk; this is not the note's instrument.")
    m = m.merge(cpd, on="date", how="left")
    m["pricing_power_cost_pressure_n"] = m["n_years"].fillna(0).astype(int)
    val = m["gm_chg"] * m["cost_pressure"].where(m["cost_pressure"] > 0)
    val[m["pricing_power_cost_pressure_n"] < MIN_SUPPORT["pricing_power_cost_pressure"]] = np.nan
    m["pricing_power_cost_pressure"] = val
    meta = {"cost_pressure_source": source,
            "cost_pressure_by_date": {str(pd.Timestamp(r.date).date()):
                                      (None if pd.isna(r.cost_pressure) else round(float(r.cost_pressure), 5))
                                      for r in cpd.itertuples()}}
    return m[["ticker", "date", "pricing_power_cost_pressure",
              "pricing_power_cost_pressure_n"]], meta


# ── the one call ─────────────────────────────────────────────────────────────

def compute(panel_dates: Iterable, *, bars: pd.DataFrame | None = None,
            revisions: pd.DataFrame | None = None,
            news_rows: Iterable[dict] | pd.DataFrame | None = None,
            actor_corpus: pd.DataFrame | None = None,
            fundamentals: pd.DataFrame | None = None,
            firm_map: dict | None = None,
            cost_pressure: pd.Series | None = None,
            tickers: Iterable[str] | None = None,
            sessions: Iterable | None = None,
            meta: dict | None = None) -> pd.DataFrame:
    """(ticker, date)-indexed frame of the six columns and their `_n` supports.

    Any input left as None makes its columns NaN with support 0 -- a missing
    source is visible as missing, never as a zero signal. `firm_map` maps a
    revision `firm` name to an IBES `estimid`; an unmapped firm gets the prior
    weight. `sessions` is the trading calendar for news bucketing (defaults to
    the bars' dates, else business days).
    """
    dates = _dates(panel_dates)
    tk: set[str] = set(tickers) if tickers is not None else set()
    if tickers is None:
        if bars is not None:
            tk |= set(bars["symbol"].astype(str))
        if revisions is not None:
            tk |= set(revisions["ticker"].astype(str).str.upper())
        if fundamentals is not None:
            tk |= set(fundamentals["ticker"].astype(str))
    out = _empty(tk, dates)
    if not len(out):
        return out

    def put(frame: pd.DataFrame, cols: list[str]) -> None:
        if frame is None or frame.empty:
            return
        f = frame[frame["ticker"].isin(tk)].set_index(["ticker", "date"])[cols]
        f = f[~f.index.duplicated(keep="last")]
        common = out.index.intersection(f.index)
        for c in cols:
            out.loc[common, c] = f.loc[common, c].values

    rev5 = None
    if bars is not None and len(bars):
        bf = bar_features(bars, dates)
        put(bf, ["max_21", "max_21_n"])
        rev5 = bf.set_index(["ticker", "date"])["rev_5"]
        rev5 = rev5[~rev5.index.duplicated(keep="last")]
    if sessions is not None:
        sess = _dates(sessions)
    elif bars is not None and len(bars):
        sess = _dates(pd.to_datetime(bars["date"]).unique())
    else:
        sess = pd.bdate_range(dates.min() - pd.Timedelta(days=400), dates.max())
    if news_rows is not None:
        put(attention_features(news_frame(news_rows), dates, sess, tk),
            ["attention_z", "attention_z_n"])
    if revisions is not None and len(revisions):
        prep = _prep_revisions(revisions, firm_map)
        put(skill_features(prep, actor_corpus, dates),
            ["analyst_skill_weight", "analyst_skill_weight_n"])
        put(first_mover_features(revision_clusters(prep), dates),
            ["first_mover_rank", "first_mover_rank_n"])
    if fundamentals is not None and len(fundamentals):
        pf, pmeta = pricing_power_features(fundamentals, dates, tk, cost_pressure)
        put(pf, ["pricing_power_cost_pressure", "pricing_power_cost_pressure_n"])
        if meta is not None:
            meta.update(pmeta)

    # fomo_reversal: rev_5 x 1{attention_z > 2}; NaN when either leg is unavailable
    z = out["attention_z"].astype(float)
    r5 = (rev5.reindex(out.index) if rev5 is not None
          else pd.Series(np.nan, index=out.index)).astype(float)
    fomo = r5 * (z > ATT_SPIKE_Z).astype(float)
    fomo[z.isna() | r5.isna()] = np.nan
    out["fomo_reversal"] = fomo
    out["fomo_reversal_n"] = out["attention_z_n"]
    for c in FEATURE_COLUMNS:
        out[c] = out[c].astype(float)
        out[f"{c}_n"] = out[f"{c}_n"].fillna(0).astype(int)
    return out[[x for c in FEATURE_COLUMNS for x in (c, f"{c}_n")]]


def support_summary(frame: pd.DataFrame) -> dict:
    """Non-NaN counts per column, overall and by year -- the receipt's first table."""
    yrs = frame.index.get_level_values("date").year
    return {c: {"non_nan": int(frame[c].notna().sum()),
                "rows": int(len(frame)),
                "by_year": {int(y): int(v) for y, v in frame[c].notna().groupby(yrs).sum().items()},
                "tickers_with_any": int(frame[c].notna().groupby(level="ticker").any().sum())}
            for c in FEATURE_COLUMNS}


# ── firm name -> IBES estimid, measured, not guessed ────────────────────────

def map_firms_to_estimid(revisions: pd.DataFrame, ibes_targets: pd.DataFrame, *,
                         min_matches: int = 20, min_share: float = 0.5) -> tuple[dict, pd.DataFrame]:
    """Match yfinance `firm` names to IBES `estimid` codes by co-occurrence.

    A yfinance revision and an IBES target MATCH when they are on the same
    official ticker (`oftic`), within one calendar day, with the same target
    value (within 1%). A firm maps to its modal estimid when that code holds
    >= `min_share` of >= `min_matches` matches. Identity only -- no outcome is
    read -- so estimating it on the whole history is not a look-ahead.
    """
    r = revisions[["ticker", "event_date", "firm", "current_target"]].copy()
    r["ticker"] = r["ticker"].astype(str).str.upper()
    r["day"] = pd.to_datetime(r["event_date"]).dt.normalize()
    r["tgt"] = pd.to_numeric(r["current_target"], errors="coerce")
    r = r.dropna(subset=["tgt"])[["ticker", "day", "firm", "tgt"]]
    t = ibes_targets[["oftic", "anndats", "estimid", "value"]].dropna().copy()
    t["oftic"] = t["oftic"].astype(str).str.upper()
    t["anndats"] = pd.to_datetime(t["anndats"]).dt.normalize()
    hits = []
    for lag in (-1, 0, 1):
        tt = t.assign(day=t["anndats"] + pd.Timedelta(days=lag)).drop(columns=["anndats"])
        m = r.merge(tt, left_on=["ticker", "day"], right_on=["oftic", "day"], how="inner")
        m = m[(m["value"].astype(float) - m["tgt"]).abs() <= 0.01 * m["tgt"]]
        hits.append(m[["firm", "estimid"]])
    h = pd.concat(hits, ignore_index=True)
    if h.empty:
        return {}, pd.DataFrame(columns=["firm", "estimid", "matches", "share", "firm_total"])
    c = h.groupby(["firm", "estimid"]).size().rename("matches").reset_index()
    c["firm_total"] = c.groupby("firm")["matches"].transform("sum")
    c["share"] = c["matches"] / c["firm_total"]
    best = c.sort_values("matches", ascending=False).drop_duplicates("firm")
    ok = best[(best["firm_total"] >= min_matches) & (best["share"] >= min_share)]
    return dict(zip(ok["firm"], ok["estimid"])), best.reset_index(drop=True)


# ── the real-panel run: support counts + receipt ────────────────────────────

def load_news_corpus(root: Path | None = None) -> list[dict]:
    root = Path(root or _optimus() / "news_corpus")
    rows: list[dict] = []
    for src in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("_")):
        for f in sorted(src.glob("*.jsonl")):
            with f.open(encoding="utf-8") as fh:
                for line in fh:
                    try:
                        r = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    rows.append({"first_seen_utc": r.get("first_seen_utc"),
                                 "tickers": r.get("tickers")})
    return rows


def main(argv: list[str] | None = None) -> int:
    import argparse
    import hashlib
    from datetime import datetime, timezone
    ap = argparse.ArgumentParser(description="pit_features over the real panel -> receipt")
    ap.add_argument("--start", default="2013-01-01")
    a = ap.parse_args(argv)
    opt = _optimus()
    from backend.services import xs_ranker
    paths = xs_ranker.survivorship_free_paths()
    bars = pd.concat([pd.read_parquet(p, columns=["symbol", "date", "close"]) for p in paths],
                     ignore_index=True)
    bars["date"] = pd.to_datetime(bars["date"])
    bars = bars.drop_duplicates(["symbol", "date"], keep="first")
    sess = pd.DatetimeIndex(sorted(bars["date"].unique()))
    run_date = sess.max() + pd.Timedelta(days=1)
    s = pd.Series(sess[sess >= pd.Timestamp(a.start)])
    # decision dates: the first session of each month, plus the run date
    dates = list(s.groupby(s.dt.to_period("M")).min()) + [run_date]
    rev = pd.read_parquet(opt / "analyst" / "target_revisions.parquet")
    n_future = int((pd.to_datetime(rev["event_date"]) > pd.Timestamp.now()).sum())
    actor = pd.read_parquet(opt / "actor_corpus" / "ibes_graded.parquet",
                            columns=["estimid", "direction", "outcome", "public_at"])
    ibes = pd.read_parquet(opt / "wrds" / "bulk" / "tr_ibes__ptgdetu.parquet",
                           columns=["oftic", "anndats", "estimid", "value", "horizon", "usfirm"],
                           filters=[("usfirm", "==", 1), ("horizon", "==", "12")])
    ibes = ibes[pd.to_datetime(ibes["anndats"]) >= "2011-01-01"]
    fmap, fmap_table = map_firms_to_estimid(rev, ibes)
    del ibes
    facts = pd.read_parquet(opt / "fundamentals_sec" / "sec_facts_history.parquet")
    news = load_news_corpus()
    meta: dict = {}
    frame = compute(dates, bars=bars, revisions=rev, news_rows=news, actor_corpus=actor,
                    fundamentals=facts, firm_map=fmap, sessions=sess, meta=meta)
    out_dir = opt / "pit_features"
    out_dir.mkdir(parents=True, exist_ok=True)
    frame.reset_index().to_parquet(out_dir / "pit_features_monthly.parquet", index=False)
    stamps = [r["first_seen_utc"] for r in news if r["first_seen_utc"]]
    receipt = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "module": "backend/services/pit_features.py",
        "pit_rule": "every input row dated STRICTLY before the decision date",
        "decision_dates": {"n": len(dates), "first": str(dates[0].date()),
                           "last": str(dates[-1].date()),
                           "rule": "first session of each month + one run-date row"},
        "universe": {"bars_paths": [str(p) for p in paths],
                     "n_symbols": int(bars["symbol"].nunique()), "rows": int(len(frame))},
        "min_support": MIN_SUPPORT,
        "support": support_summary(frame),
        "firm_map": {"mapped_firms": len(fmap), "firms_total": int(rev["firm"].nunique()),
                     "share_of_revision_events_mapped": round(float(rev["firm"].map(fmap).notna().mean()), 4),
                     "rule": "same oftic, +-1 day, target within 1%, modal estimid >= 50% of >= 20 matches",
                     "top": fmap_table.head(40).to_dict("records")},
        "revisions_future_dated_rows": n_future,
        "news_corpus": {"rows": len(news), "first_seen_min": min(stamps) if stamps else None,
                        "note": "first_seen_utc is PULL time; attention_z has no history before the corpus began"},
        **meta,
        "forward_only": ["attention_z", "fomo_reversal"],
        "history_note": {"analyst_skill_weight": ("actor-corpus claims resolve from 2013-04; before "
                                                  "that every broker carries the prior weight 1.0")},
    }
    receipt["fingerprint"] = hashlib.sha256(
        json.dumps(receipt["support"], sort_keys=True).encode()).hexdigest()[:16]
    (out_dir / "pit_features_receipt.json").write_text(json.dumps(receipt, indent=2, default=str))
    (out_dir / "firm_estimid_map.json").write_text(json.dumps(fmap, indent=1, sort_keys=True))
    print(json.dumps({c: receipt["support"][c]["non_nan"] for c in FEATURE_COLUMNS}, indent=1))
    print("firm map:", receipt["firm_map"]["mapped_firms"], "firms,",
          receipt["firm_map"]["share_of_revision_events_mapped"], "of events")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
