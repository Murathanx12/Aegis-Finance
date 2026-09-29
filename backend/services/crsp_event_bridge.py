"""Point-in-time bridges from event data (IBES, Form 4) to the CRSP permno panel (2026-09-29).

WHY: 172 of the strategy library's 312 rules could not run on the survivor-free
CRSP panel (1991-2024) because their inputs -- analyst revision flow, rating
changes, target dispersion, insider buying, earnings events -- had no
point-in-time bridge to the CRSP era. The vendor panel's inputs start 2016.
This module builds those columns from WRDS IBES detail files and the SEC Form 4
event file already on disk, keyed to CRSP permno, with the library's own column
names and window conventions (`night_backtest_factory.attach_flow`,
`attach_ratings`, `attach_insider`, `attach_8k`).

THE TIMESTAMP RULE (the whole point of the module; pinned by tests):
* an IBES row is dated by max(anndats, actdats) -- the announcement date or the
  date it entered the IBES database, whichever is LATER -- never by a fiscal
  period;
* a Form 4 row is dated by its FILING date (`observed_at_utc`), never by the
  transaction date;
* every event is then lagged ONE trading day (`usable = event day + 1 BDay`) and
  counts at decision date d only if `usable <= d`. An event on d itself is not
  used; an event on d-1 is.
* the earnings-announcement return (e-1 .. e+1 around the reaction session e)
  is used only from the business day after e+1.
* the IBES ticker -> permno link is taken from `ibcrsphist` rows whose
  [sdate, edate] contains the EVENT date (lowest score wins); an event outside
  every link interval is dropped and counted, never mapped to today's permno.

Pure functions only; the heavy I/O lives in `scripts/analyst_insider_on_crsp.py`.
"""
from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd

LAG = pd.offsets.BDay(1)

#: columns this bridge produces, by source (library names)
FLOW_COLS = ["net_raises", "n_firms", "median_target_change", "n_events", "net_raises_30",
             "net_raises_180", "flow_rule_score", "flow_accel"]
RATING_COLS = ["rating_net_90", "rating_downgrades_90", "initiations_90", "target_cv_180"]
INSIDER_COLS = ["ins_buyers_90", "ins_sellers_90", "ins_officer_buyers_90", "ins_buy_value_90",
                "ins_opp_buyers_180", "ins_net_ratio_180"]
EARN_COLS = ["ear_last", "days_since_earn", "earn_next", "earn_following"]


def event_day(anndats, actdats=None) -> pd.Series:
    """The day an IBES row became public: max(anndats, actdats), normalised."""
    a = pd.to_datetime(pd.Series(anndats), errors="coerce").reset_index(drop=True)
    if actdats is None:
        return a.dt.normalize()
    b = pd.to_datetime(pd.Series(actdats), errors="coerce").reset_index(drop=True)
    return pd.concat([a, b], axis=1).max(axis=1).dt.normalize()


def usable_date(day) -> pd.Series:
    """Lag one trading day: the first decision date on which the event may be used."""
    d = pd.to_datetime(pd.Series(day)).dt.normalize()
    return d + LAG


def link_permno(events: pd.DataFrame, link: pd.DataFrame, *, ticker_col: str = "ticker",
                day_col: str = "day") -> tuple[pd.DataFrame, dict]:
    """Attach permno to each event through the link row active ON THE EVENT DATE.

    `link`: ticker, permno, sdate, edate, score (WRDS ibcrsphist). Lowest score wins
    among active rows. Events with no active row are dropped and counted.
    """
    ev = events.reset_index(drop=True).copy()
    ev["_eid"] = np.arange(len(ev))
    L = link[["ticker", "permno", "sdate", "edate", "score"]].copy()
    L["sdate"] = pd.to_datetime(L["sdate"])
    L["edate"] = pd.to_datetime(L["edate"]).fillna(pd.Timestamp("2099-12-31"))
    L = L.dropna(subset=["permno"]).rename(columns={"ticker": ticker_col})
    m = ev[[ticker_col, day_col, "_eid"]].merge(L, on=ticker_col, how="inner")
    m = m[(m[day_col] >= m["sdate"]) & (m[day_col] <= m["edate"])]
    m = m.sort_values(["_eid", "score"]).drop_duplicates("_eid", keep="first")
    out = ev.merge(m[["_eid", "permno"]], on="_eid", how="inner").drop(columns="_eid")
    out["permno"] = out["permno"].astype("int64")
    meta = {"events_in": int(len(ev)), "events_linked": int(len(out)),
            "link_rate": round(len(out) / max(1, len(ev)), 4)}
    return out, meta


def target_signs(ptg: pd.DataFrame, *, max_gap_days: int = 365) -> pd.DataFrame:
    """Per (permno, broker) target sequence -> sign (+1 raise / -1 lower / 0) and change.

    `ptg`: permno, broker, day, value. The prior target is the same broker's
    previous target on the same permno, used only when it is <= max_gap_days old
    (an older one is a re-initiation: sign 0, change NaN).
    """
    p = ptg.sort_values(["permno", "broker", "day"], kind="mergesort").copy()
    g = p.groupby(["permno", "broker"], sort=False)
    prev_v = g["value"].shift(1)
    prev_d = g["day"].shift(1)
    fresh = (p["day"] - prev_d).dt.days <= max_gap_days
    ok = fresh & (prev_v > 0) & (p["value"] > 0)
    p["sign"] = np.where(ok & (p["value"] > prev_v), 1, np.where(ok & (p["value"] < prev_v), -1, 0))
    p["chg"] = (p["value"] / prev_v - 1.0).where(ok)
    return p


def rec_actions(rec: pd.DataFrame, *, max_gap_days: int = 365) -> pd.DataFrame:
    """IBES recommendation detail -> up / down / init / same per (permno, broker).

    `ireccd` 1 = strong buy ... 5 = sell: a LOWER code is an upgrade. The first
    code of a broker on a permno (or one after a > max_gap_days silence) is an init.
    """
    r = rec.sort_values(["permno", "broker", "day"], kind="mergesort").copy()
    r["code"] = pd.to_numeric(r["code"], errors="coerce").astype("float64")
    r = r[r["code"].notna()]
    g = r.groupby(["permno", "broker"], sort=False)
    pc = g["code"].shift(1).astype("float64")
    pdy = g["day"].shift(1)
    init = pc.isna() | ((r["day"] - pdy).dt.days > max_gap_days)
    r["action"] = np.where(init, "init", np.where(r["code"] < pc, "up",
                                                  np.where(r["code"] > pc, "down", "same")))
    return r


def _slice(times: np.ndarray, d: pd.Timestamp, days: int) -> tuple[int, int]:
    """Index range of events with usable in (d - days, d]."""
    lo = int(np.searchsorted(times, np.datetime64(d - pd.Timedelta(days=days)), "right"))
    hi = int(np.searchsorted(times, np.datetime64(d), "right"))
    return lo, hi


def flow_panel(events: pd.DataFrame, dates: Iterable) -> pd.DataFrame:
    """Library revision flow on each decision date from events with `usable` <= d.

    `events`: permno, usable, broker, sign (+1/-1/0), chg (target change or NaN).
    Windows (d - W, d] on the USABLE date, W in 30/90/180. Coverage: a permno
    with any event usable in (d-365, d] is covered and its counts are 0 when the
    window is empty; an uncovered permno is absent (NaN after the merge).
    """
    e = events.sort_values("usable", kind="mergesort").reset_index(drop=True)
    tt = e["usable"].to_numpy(dtype="datetime64[ns]")
    rows = []
    for d in sorted({pd.Timestamp(x) for x in dates}):
        lo365, hi = _slice(tt, d, 365)
        if hi <= lo365:
            continue
        f = pd.DataFrame(index=pd.Index(e["permno"].iloc[lo365:hi].unique(), name="permno"))
        for W, suf in ((90, ""), (30, "_30"), (180, "_180")):
            lo, _ = _slice(tt, d, W)
            w = e.iloc[lo:hi]
            gg = w.groupby("permno")
            f["net_raises" + suf] = gg["sign"].sum().astype(float)
            if not suf:
                f["n_firms"] = gg["broker"].nunique().astype(float)
                f["median_target_change"] = gg["chg"].median()
                f["n_events"] = gg.size().astype(float)
        for c in ("net_raises", "n_firms", "n_events", "net_raises_30", "net_raises_180"):
            f[c] = f[c].fillna(0.0)
        f["date"] = d
        rows.append(f.reset_index())
    if not rows:
        return pd.DataFrame(columns=["date", "permno", *FLOW_COLS])
    out = pd.concat(rows, ignore_index=True)
    out["flow_rule_score"] = out["net_raises"] * out["n_firms"]
    out["flow_accel"] = out["net_raises_30"] - out["net_raises"] / 3.0
    return out[["date", "permno", *FLOW_COLS]]


def rating_panel(rec: pd.DataFrame, ptg: pd.DataFrame, dates: Iterable) -> pd.DataFrame:
    """rating_net_90 / rating_downgrades_90 / initiations_90 from rec actions (covered =
    any rec usable in (d-365, d]); target_cv_180 from each broker's latest target
    usable in (d-180, d], >= 3 brokers."""
    r = rec.sort_values("usable", kind="mergesort").reset_index(drop=True)
    p = ptg[ptg["value"] > 0].sort_values("usable", kind="mergesort").reset_index(drop=True)
    tr = r["usable"].to_numpy(dtype="datetime64[ns]")
    tp = p["usable"].to_numpy(dtype="datetime64[ns]")
    rows = []
    for d in sorted({pd.Timestamp(x) for x in dates}):
        lo365, hi = _slice(tr, d, 365)
        lo90, _ = _slice(tr, d, 90)
        f = pd.DataFrame(index=pd.Index(r["permno"].iloc[lo365:hi].unique(), name="permno"))
        w = r.iloc[lo90:hi]
        a = w["action"]
        for nm in ("up", "down", "init"):
            f[nm] = (a == nm).groupby(w["permno"]).sum().astype(float)
            f[nm] = f[nm].fillna(0.0)
        plo, phi = _slice(tp, d, 180)
        last = p.iloc[plo:phi].drop_duplicates(["permno", "broker"], keep="last")
        cvg = last.groupby("permno")["value"].agg(["std", "mean", "count"])
        cv = (cvg["std"] / cvg["mean"]).where(cvg["count"] >= 3).rename("target_cv_180")
        f = f.join(cv, how="outer")
        if not len(f):
            continue
        f["rating_net_90"] = f["up"] - f["down"]
        f["rating_downgrades_90"] = f["down"]
        f["initiations_90"] = f["init"]
        f.index.name = "permno"
        f = f.reset_index()
        f["date"] = d
        rows.append(f[["date", "permno", *RATING_COLS]])
    if not rows:
        return pd.DataFrame(columns=["date", "permno", *RATING_COLS])
    return pd.concat(rows, ignore_index=True)


BUY, SELL, OPP = "insider_open_market_buy", "insider_open_market_sell", "insider_opportunistic_buy"


def insider_panel(ev: pd.DataFrame, dates: Iterable) -> pd.DataFrame:
    """The library's insider columns (`attach_insider` semantics) keyed on permno.

    `ev`: permno, usable (filing day + 1 BDay), event_type, insider_cik,
    insider_is_officer, insider_dollar_value. Distinct insiders per window.
    Coverage: any Form 4 event usable in (d-180, d] (the vendor's rule).
    """
    e = ev.sort_values("usable", kind="mergesort").reset_index(drop=True)
    tt = e["usable"].to_numpy(dtype="datetime64[ns]")
    rows = []

    def nun(w, mask):
        x = w.loc[mask, ["permno", "insider_cik"]].drop_duplicates()
        return x.groupby("permno").size()

    for d in sorted({pd.Timestamp(x) for x in dates}):
        lo180, hi = _slice(tt, d, 180)
        lo90, _ = _slice(tt, d, 90)
        w9, w18 = e.iloc[lo90:hi], e.iloc[lo180:hi]
        if not len(w18):
            continue
        b9 = w9["event_type"] == BUY
        f = pd.DataFrame(index=pd.Index(w18["permno"].unique(), name="permno"))
        f["b90"] = nun(w9, b9)
        f["s90"] = nun(w9, w9["event_type"] == SELL)
        f["o90"] = nun(w9, b9 & w9["insider_is_officer"].fillna(False).astype(bool))
        f["v90"] = w9[b9].groupby("permno")["insider_dollar_value"].sum()
        f["b180"] = nun(w18, w18["event_type"] == BUY)
        f["s180"] = nun(w18, w18["event_type"] == SELL)
        f["p180"] = nun(w18, w18["event_type"] == OPP)
        f = f.fillna(0.0)
        tot = f["b180"] + f["s180"]
        rows.append(pd.DataFrame({
            "date": d, "permno": f.index.to_numpy(),
            "ins_buyers_90": f["b90"].to_numpy(), "ins_sellers_90": f["s90"].to_numpy(),
            "ins_officer_buyers_90": f["o90"].to_numpy(), "ins_buy_value_90": f["v90"].to_numpy(),
            "ins_opp_buyers_180": f["p180"].to_numpy(),
            "ins_net_ratio_180": ((f["b180"] - f["s180"]) / tot.where(tot > 0)).to_numpy()}))
    if not rows:
        return pd.DataFrame(columns=["date", "permno", *INSIDER_COLS])
    return pd.concat(rows, ignore_index=True)


def earnings_events(act: pd.DataFrame, *, max_report_lag_days: int = 120) -> pd.DataFrame:
    """IBES actuals (EPS, quarterly) -> one announcement per (permno, fiscal period end).

    Keeps the FIRST announcement of each period and only when it came within
    `max_report_lag_days` of the period end (a late restatement row is not an
    earnings event). The reaction day is the announcement day, or the next
    business day when `anntims` is at or after 16:00; a weekend rolls forward.
    """
    a = act.copy()
    a["pends"] = pd.to_datetime(a["pends"], errors="coerce")
    a["anndats"] = pd.to_datetime(a["anndats"], errors="coerce").dt.normalize()
    a = a.dropna(subset=["pends", "anndats", "permno"])
    lag = (a["anndats"] - a["pends"]).dt.days
    a = a[(lag >= 0) & (lag <= max_report_lag_days)]
    a = a.sort_values(["permno", "pends", "anndats"]).drop_duplicates(["permno", "pends"], keep="first")
    if "anntims" in a:
        hh = pd.to_numeric(a["anntims"].astype(str).str.slice(0, 2), errors="coerce")
        after = (hh >= 16).fillna(False).to_numpy()
    else:
        after = np.zeros(len(a), dtype=bool)
    rd = a["anndats"].where(~after, a["anndats"] + LAG)
    rd = pd.to_datetime([x if x.dayofweek < 5 else (x + pd.offsets.BDay(1)).normalize() for x in rd])
    a["reaction_day"] = rd
    return a[["permno", "pends", "anndats", "reaction_day"]].reset_index(drop=True)


def three_day_car(daily: pd.DataFrame, mkt: pd.Series, events: pd.DataFrame) -> pd.DataFrame:
    """3-session abnormal return [e-1, e+1] around the reaction session e.

    `daily`: permno, date, ret; `mkt`: market daily return indexed by date;
    `events`: permno, reaction_day (+ any columns, carried). Returns the events
    with `ear` and `known` (the business day after the close of e+1).
    """
    dly = daily.sort_values(["permno", "date"]).reset_index(drop=True)
    dly["lr"] = np.log1p(pd.to_numeric(dly["ret"], errors="coerce").astype(float).fillna(0.0))
    dly["cum"] = dly.groupby("permno")["lr"].cumsum()
    dly["pos"] = dly.groupby("permno").cumcount()
    mk = np.log1p(mkt.astype(float).fillna(0.0)).cumsum()
    ev = events.sort_values("reaction_day").reset_index(drop=True)
    m = pd.merge_asof(ev, dly[["date", "permno", "pos"]].sort_values("date"), left_on="reaction_day",
                      right_on="date", by="permno", direction="forward", tolerance=pd.Timedelta(days=5))
    m = m.dropna(subset=["pos"]).reset_index(drop=True)
    pos = m["pos"].astype(int).to_numpy()
    key = dly.set_index(["permno", "pos"])[["date", "cum"]]
    pa = key.reindex(pd.MultiIndex.from_arrays([m["permno"].to_numpy(), pos - 2]))   # close of e-2
    pb = key.reindex(pd.MultiIndex.from_arrays([m["permno"].to_numpy(), pos + 1]))   # close of e+1
    ok = pa["cum"].notna().to_numpy() & pb["cum"].notna().to_numpy()
    stock = np.expm1(pb["cum"].to_numpy() - pa["cum"].to_numpy())
    mret = np.expm1(mk.reindex(pb["date"].to_numpy()).to_numpy() - mk.reindex(pa["date"].to_numpy()).to_numpy())
    m["ear"] = np.where(ok, stock - mret, np.nan)
    m["known"] = pd.to_datetime(pb["date"].to_numpy()) + LAG
    return m.drop(columns=["date", "pos"])


def earnings_panel(er: pd.DataFrame, dates: Iterable, next_date: dict) -> pd.DataFrame:
    """ear_last / days_since_earn (last KNOWN print <= 100 days old) and earn_next /
    earn_following (expected print from a year-ago print + 364d or last print + 91d).

    `er`: permno, anndats, ear, known (first decision date on which `ear` may be used).
    Announcement dates are scheduled-calendar facts; only PAST announcements
    (anndats < d) feed the expectation.
    """
    e = er.sort_values("anndats", kind="mergesort").reset_index(drop=True)
    ta = e["anndats"].to_numpy(dtype="datetime64[ns]")
    rows = []
    for d in sorted({pd.Timestamp(x) for x in dates}):
        hi = int(np.searchsorted(ta, np.datetime64(d), "left"))
        lo = int(np.searchsorted(ta, np.datetime64(d - pd.Timedelta(days=400)), "left"))
        past = e.iloc[lo:hi]
        known = past[past["known"] <= d]
        lastk = known.drop_duplicates("permno", keep="last").set_index("permno")
        age = (d - lastk["anndats"]).dt.days
        f = pd.DataFrame({"ear_last": lastk["ear"].where(age <= 100),
                          "days_since_earn": age.where(age <= 100).astype(float)})
        dn = next_date[d]
        lastp = past.drop_duplicates("permno", keep="last").set_index("permno")
        y0 = int(np.searchsorted(ta, np.datetime64(d - pd.Timedelta(days=364)), "right"))
        y1 = int(np.searchsorted(ta, np.datetime64(dn - pd.Timedelta(days=364)), "right"))
        y2 = int(np.searchsorted(ta, np.datetime64(dn + pd.Timedelta(days=21) - pd.Timedelta(days=364)), "right"))
        nxt = set(e["permno"].iloc[y0:y1])
        fol = set(e["permno"].iloc[y1:y2])
        q = lastp["anndats"] + pd.Timedelta(days=91)
        nxt |= set(q.index[(q > d) & (q <= dn)])
        fol |= set(q.index[(q > dn) & (q <= dn + pd.Timedelta(days=21))])
        fol -= nxt
        idx = sorted(set(f.index) | nxt | fol | set(lastp.index))
        f = f.reindex(idx)
        f["earn_next"] = [1.0 if x in nxt else 0.0 for x in f.index]
        f["earn_following"] = [1.0 if x in fol else 0.0 for x in f.index]
        f.index.name = "permno"
        f = f.reset_index()
        f["date"] = d
        rows.append(f[["date", "permno", *EARN_COLS]])
    if not rows:
        return pd.DataFrame(columns=["date", "permno", *EARN_COLS])
    return pd.concat(rows, ignore_index=True)


def next_decision(dates: Iterable) -> dict:
    ds = sorted({pd.Timestamp(x) for x in dates})
    return {d: (ds[i + 1] if i + 1 < len(ds) else d + pd.Timedelta(days=31)) for i, d in enumerate(ds)}


def coverage_by_year(feat: pd.DataFrame, col: str) -> dict:
    """Names per month with a non-null `col`, averaged within each calendar year."""
    f = feat[feat[col].notna()]
    if f.empty:
        return {}
    per = f.groupby("date")["permno"].nunique()
    return {str(y): int(round(v)) for y, v in per.groupby(pd.DatetimeIndex(per.index).year).mean().items()}
