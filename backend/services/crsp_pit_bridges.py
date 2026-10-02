"""Point-in-time bridges, round 2: short interest, 13F, 8-K, analyst timing/skill, Compustat (2026-09-30).

WHY: after `crsp_event_bridge` (IBES flow, ratings, Form 4, earnings) 96 of the
strategy library's 312 rules still could not run on the survivor-free CRSP
panel (1991-2024): their inputs had no point-in-time bridge to the CRSP era.
This module builds the remaining columns from files already on disk, keyed to
CRSP permno, with the library's column names and windows
(`night_backtest_factory.attach_ratings / attach_8k / attach_short_interest /
attach_fundamentals`, `strategy_library_ext`, `pit_features`).

THE TIMING RULE FOR EACH SOURCE (pinned by `test_crsp_pit_bridges.py`):

* SHORT INTEREST (Compustat `sec_shortint` via the permno panel
  `short_interest/comp_sec_shortint`): `datadate` is the SETTLEMENT date. The
  figure is usable from `datadate + SI_LAG_DAYS` (26 calendar days: the top of
  the 10-26 day publication lag measured on 2026-09-12, and the library's own
  constant). The panel on disk stamps +14 (the median); +14 would be a few
  days early for about half of the prints, so it is NOT used.
* 13F (Thomson s34): `fdate` is the vintage, `rdate` the holdings quarter.
  Neither is the SEC filing date. A quarter's holdings are usable from
  `rdate + F13_LAG_DAYS` (45 days, the filing deadline: the EARLIEST a full
  quarter can be known), then one business day. Only rows whose vintage is the
  quarter itself (fdate == rdate) are counted, so a stale carried-forward
  report never counts twice. CUSIP -> permno through CRSP `dsenames` rows
  whose name interval contains `rdate`.
* 8-K (EDGAR submissions, `edgar_8k/eightk_items.parquet`): the ACCEPTANCE
  timestamp in New York time; usable from the next business day (an 8-K
  accepted during a session is not used on that session's close).
* ANALYST TIMING (IBES targets): an event is dated by max(anndats, actdats)
  as in `crsp_event_bridge`, counted at d iff `usable = day + 1 BDay <= d`.
  LEAD / CHASE read the stock's return over the 10 sessions ENDING the
  session before the event day (strictly past prices). FIRST MOVER: a raise
  with no raise by ANY broker on the name in [day - 30, day); same-day raises
  do not disqualify each other (no ordering within a day is known).
  SKILL: a broker's raise is RESOLVED 63 sessions after its event session; a
  resolved raise counts in the broker's record at d only if its resolution
  session <= d. Skilled = >= 20 resolved raises with a mean 63-session excess
  return vs the market > 0 (`attach_ratings`' rule).
* COMPUSTAT QUARTERLY (`comp.fundq`, INDL/STD/C/D): usable from
  max(rdq, datadate + filing deadline) + 2 days, the deadline being 45 days
  for fiscal quarters 1-3 and 90 days for Q4 (the pre-2003 deadlines; later
  deadlines are shorter, so this is conservative in every era). A missing rdq
  falls back to the deadline. gvkey -> permno through the CCM link row active
  on `datadate` (LC/LU, primary P/C). Compustat stores the CURRENT vintage of
  each value, not the as-first-reported number: a second-order leak, named on
  every receipt.

Pure functions only; the heavy I/O lives in `scripts/bridges_on_crsp.py`.
"""
from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd

LAG = pd.offsets.BDay(1)

SI_LAG_DAYS = 26
SI_STALE_DAYS = 60                 # a print older than this (from availability) is stale
SI_PREV_DAYS = 91                  # si_chg_3m compares with the print known 91 days earlier
F13_LAG_DAYS = 45
F13_MAX_AGE_DAYS = 200
F13_CONC_MAX_HOLDINGS = 25         # a "concentrated" manager holds <= 25 names in the quarter
F13_CONC_MIN_HOLDINGS = 3
EIGHTK_DISTRESS_ITEMS = ("1.03", "2.04", "3.01", "4.02")
FIRST_MOVER_GAP_DAYS = 30
SKILL_MIN_RESOLVED = 20
EXC_SESSIONS = 63
LEAD_SESSIONS = 10
FUND_DEADLINE_Q = 45
FUND_DEADLINE_Q4 = 90
FUND_EXTRA_DAYS = 2
FUND_STALE_DAYS = 460

SI_COLS = ["dtc", "si_chg_3m", "si_ratio"]
F13_COLS = ["inst_breadth_chg", "n_inst", "n_conc_init", "n_init"]
EIGHTK_COLS = ["n8k_90", "n101_90", "n701_90", "n502_180", "distress_365"]
ANALYST2_COLS = ["lead_raises_90", "chase_raises_90", "lead_minus_chase_90", "first_mover_raises_90",
                 "skill_net_raises_90", "unskilled_net_raises_90", "skill_first_mover_90"]
FUND_COLS = ["ope_be", "cash_at", "at_gr1", "gross_margin_q", "rev_gr", "gm_chg", "inflection", "rev_accel",
             "om_chg", "roa_chg", "debt_at_chg", "ni_turn", "gm_turn", "rev_turn", "rd_intensity",
             "org_capital"]
FUND_LEVEL_COLS = ["_ni_ttm", "_oi_ttm", "_debt", "_cash", "_ceq"]


# ── shared helpers ──────────────────────────────────────────────────────────

def dated_link(df: pd.DataFrame, link: pd.DataFrame, *, key: str, day_col: str,
               link_key: str | None = None, lo: str = "linkdt", hi: str = "linkenddt",
               rank_col: str | None = None) -> tuple[pd.DataFrame, dict]:
    """Attach `permno` through the link row whose [lo, hi] contains `day_col`.

    Rows outside every interval are dropped and counted (never mapped to a
    later permno). A tie is broken by `rank_col` ascending when given.
    """
    ev = df.reset_index(drop=True).copy()
    ev["_rid"] = np.arange(len(ev))
    L = link.copy()
    lk = link_key or key
    L[lo] = pd.to_datetime(L[lo], errors="coerce").fillna(pd.Timestamp("1900-01-01"))
    L[hi] = pd.to_datetime(L[hi], errors="coerce").fillna(pd.Timestamp("2099-12-31"))
    L = L.dropna(subset=["permno"])
    keep = [lk, "permno", lo, hi] + ([rank_col] if rank_col else [])
    L = L[keep].rename(columns={lk: key})
    m = ev[[key, day_col, "_rid"]].merge(L, on=key, how="inner")
    m = m[(m[day_col] >= m[lo]) & (m[day_col] <= m[hi])]
    m = m.sort_values(["_rid"] + ([rank_col] if rank_col else [])).drop_duplicates("_rid", keep="first")
    out = ev.merge(m[["_rid", "permno"]], on="_rid", how="inner").drop(columns="_rid")
    out["permno"] = pd.to_numeric(out["permno"], errors="coerce").astype("int64")
    return out, {"rows_in": int(len(ev)), "rows_linked": int(len(out)),
                 "link_rate": round(len(out) / max(1, len(ev)), 4)}


def ccm_rank(link: pd.DataFrame) -> pd.Series:
    """Tie order for CCM rows: primary P before C, LC before LU."""
    return (link["linkprim"].map({"P": 0, "C": 1}).fillna(2) * 10
            + link["linktype"].map({"LC": 0, "LU": 1}).fillna(2))


def asof_panel(keys: pd.DataFrame, feats: pd.DataFrame, cols: list, *, on: str,
               age_from: str | None = None, max_age_days: int | None = None) -> pd.DataFrame:
    """Backward as-of join of permno-keyed rows (`on` <= date) onto (date, permno) keys.

    Row order of `keys` is kept. A row whose `age_from` is older than
    `max_age_days` at the date is NaN (stale), never carried.
    """
    left = keys[["date", "permno"]].copy()
    left["_i"] = np.arange(len(left))
    left["date"] = pd.to_datetime(left["date"]).astype("datetime64[ns]")
    left["permno"] = pd.to_numeric(left["permno"], errors="coerce")
    ok = left["permno"].notna()
    lf = left[ok].copy()
    lf["permno"] = lf["permno"].astype("int64")
    r = feats.copy()
    r[on] = pd.to_datetime(r[on]).astype("datetime64[ns]")
    if age_from and age_from != on:
        r[age_from] = pd.to_datetime(r[age_from]).astype("datetime64[ns]")
    r["permno"] = r["permno"].astype("int64")
    r = r.dropna(subset=[on]).sort_values(on, kind="mergesort")
    keep = ["permno", on] + ([age_from] if age_from and age_from != on else []) + list(cols)
    m = pd.merge_asof(lf.sort_values("date", kind="mergesort"), r[keep], left_on="date", right_on=on,
                      by="permno", direction="backward", allow_exact_matches=True)
    if age_from and max_age_days is not None:
        stale = (m["date"] - m[age_from]).dt.days > max_age_days
        m.loc[stale, list(cols)] = np.nan
    out = pd.DataFrame(index=np.arange(len(left)), columns=list(cols), dtype="float64")
    m = m.sort_values("_i")
    out.loc[m["_i"].to_numpy(), list(cols)] = m[list(cols)].to_numpy(dtype="float64")
    return out


def coverage_by_year(frame: pd.DataFrame, col: str) -> dict:
    """Names per month with a non-null `col`, averaged within each calendar year."""
    f = frame[frame[col].notna()]
    if f.empty:
        return {}
    per = f.groupby("date")["permno"].nunique()
    return {str(y): int(round(v)) for y, v in per.groupby(pd.DatetimeIndex(per.index).year).mean().items()}


# ── 1. short interest ───────────────────────────────────────────────────────

def si_prints(si: pd.DataFrame, *, lag_days: int = SI_LAG_DAYS) -> pd.DataFrame:
    """Short-interest prints -> permno, datadate, available, dtc, si_ratio, siadj.

    `si`: permno, datadate, shortint (shares on the datadate basis), shortintadj,
    shares_outstanding (shares), turnover_21d (21-session share volume /
    shares outstanding, window ending at the datadate session). Days to cover
    = shortint / average daily share volume over those 21 sessions: numerator
    and denominator on the SAME (datadate) share basis, so a later split cannot
    leak into the ratio.
    """
    s = si.copy()
    s["datadate"] = pd.to_datetime(s["datadate"]).dt.normalize()
    s["available"] = s["datadate"] + pd.Timedelta(days=lag_days)
    dvol = s["turnover_21d"].astype(float) * s["shares_outstanding"].astype(float) / 21.0
    s["dtc"] = (s["shortint"].astype(float) / dvol.where(dvol > 0)).replace([np.inf, -np.inf], np.nan)
    so = s["shares_outstanding"].astype(float)
    s["si_ratio"] = s["shortint"].astype(float) / so.where(so > 0)
    s["siadj"] = s["shortintadj"].astype(float)
    s = s.sort_values(["permno", "datadate"]).drop_duplicates(["permno", "datadate"], keep="last")
    return s[["permno", "datadate", "available", "dtc", "si_ratio", "siadj"]].reset_index(drop=True)


def si_panel(keys: pd.DataFrame, prints: pd.DataFrame) -> pd.DataFrame:
    """dtc, si_chg_3m, si_ratio on (date, permno) keys; the latest print with
    available <= d and <= SI_STALE_DAYS old; si_chg_3m = log((si+1)/(si_prev+1))
    against the print known SI_PREV_DAYS earlier (split-adjusted counts)."""
    now = asof_panel(keys, prints, ["dtc", "si_ratio", "siadj"], on="available", age_from="available",
                     max_age_days=SI_STALE_DAYS)
    k2 = keys[["date", "permno"]].copy()
    k2["date"] = pd.to_datetime(k2["date"]) - pd.Timedelta(days=SI_PREV_DAYS)
    prev = asof_panel(k2, prints, ["siadj"], on="available", age_from="available",
                      max_age_days=SI_STALE_DAYS)
    with np.errstate(divide="ignore", invalid="ignore"):
        chg = np.log((now["siadj"].to_numpy(dtype=float) + 1.0) / (prev["siadj"].to_numpy(dtype=float) + 1.0))
    return pd.DataFrame({"dtc": now["dtc"].to_numpy(dtype=float), "si_chg_3m": chg,
                         "si_ratio": now["si_ratio"].to_numpy(dtype=float)})


# ── 2. 13F ──────────────────────────────────────────────────────────────────

def f13_fresh(rows: pd.DataFrame) -> pd.DataFrame:
    """Keep holdings reported FOR the vintage quarter (fdate == rdate), one row per
    (mgrno, cusip, rdate), positive shares."""
    r = rows.copy()
    r["fdate"] = pd.to_datetime(r["fdate"])
    r["rdate"] = pd.to_datetime(r["rdate"])
    r = r[(r["fdate"] == r["rdate"]) & (pd.to_numeric(r["shares"], errors="coerce") > 0)]
    r = r.dropna(subset=["mgrno", "cusip"])
    r["mgrno"] = r["mgrno"].astype("int64")
    r["cusip"] = r["cusip"].astype(str).str.slice(0, 8)
    return r.drop_duplicates(["mgrno", "cusip", "rdate"])[["mgrno", "cusip", "rdate"]].reset_index(drop=True)


def f13_quarter_stats(cur: pd.DataFrame, prev: pd.DataFrame | None) -> pd.DataFrame:
    """Per (cusip, rdate) of `cur`: n_inst (distinct managers), n_init (managers who
    reported last quarter and did NOT hold the name then), n_conc_init (the same,
    among managers holding <= F13_CONC_MAX_HOLDINGS names this quarter).

    `cur`/`prev`: fresh rows (mgrno, cusip, rdate) of two consecutive quarters.
    """
    n_inst = cur.groupby("cusip")["mgrno"].nunique().rename("n_inst")
    out = n_inst.to_frame()
    if prev is None or prev.empty:
        out["n_init"] = np.nan
        out["n_conc_init"] = np.nan
    else:
        reporters = set(prev["mgrno"].unique())
        held_prev = set(zip(prev["mgrno"].to_numpy(), prev["cusip"].to_numpy()))
        c = cur[cur["mgrno"].isin(reporters)].copy()
        c["new"] = [(m, u) not in held_prev for m, u in zip(c["mgrno"].to_numpy(), c["cusip"].to_numpy())]
        nh = cur.groupby("mgrno")["cusip"].nunique()
        c["conc"] = c["mgrno"].map(nh).between(F13_CONC_MIN_HOLDINGS, F13_CONC_MAX_HOLDINGS)
        out["n_init"] = c[c["new"]].groupby("cusip")["mgrno"].nunique()
        out["n_conc_init"] = c[c["new"] & c["conc"]].groupby("cusip")["mgrno"].nunique()
        out[["n_init", "n_conc_init"]] = out[["n_init", "n_conc_init"]].fillna(0.0)
    out["rdate"] = cur["rdate"].iloc[0] if len(cur) else pd.NaT
    return out.reset_index()


def f13_breadth(q: pd.DataFrame) -> pd.DataFrame:
    """inst_breadth_chg = log(n_inst / n_inst of the previous quarter) per permno,
    only when the two quarters are consecutive (80-100 days apart); `available`
    = rdate + F13_LAG_DAYS + 1 business day."""
    d = q.groupby(["permno", "rdate"], as_index=False).agg(n_inst=("n_inst", "max"), n_init=("n_init", "max"),
                                                           n_conc_init=("n_conc_init", "max"))
    d = d.sort_values(["permno", "rdate"], kind="mergesort")
    g = d.groupby("permno")
    pn, pdt = g["n_inst"].shift(1), g["rdate"].shift(1)
    consec = (d["rdate"] - pdt).dt.days.between(80, 100)
    with np.errstate(divide="ignore", invalid="ignore"):
        d["inst_breadth_chg"] = np.log(d["n_inst"].astype(float) / pn.astype(float)).where(consec)
    d["available"] = (d["rdate"] + pd.Timedelta(days=F13_LAG_DAYS)) + LAG
    return d.reset_index(drop=True)


# ── 3. 8-K items ────────────────────────────────────────────────────────────

def eightk_events(ek: pd.DataFrame) -> pd.DataFrame:
    """EDGAR 8-K rows -> permno, day (acceptance day, New York), usable, item flags.

    `ek`: permno, acceptance_datetime (UTC), filing_date, items_joined. A missing
    acceptance time falls back to the filing date. usable = day + 1 BDay.
    """
    e = ek.copy()
    acc = pd.to_datetime(e["acceptance_datetime"], errors="coerce", utc=True)
    day = acc.dt.tz_convert("America/New_York").dt.tz_localize(None).dt.normalize()
    day = day.fillna(pd.to_datetime(e["filing_date"], errors="coerce").dt.normalize())
    e["day"] = day
    e = e[e["day"].notna() & e["permno"].notna()].copy()
    e["permno"] = pd.to_numeric(e["permno"], errors="coerce").astype("int64")
    e["usable"] = e["day"] + LAG
    it = e["items_joined"].fillna("").astype(str)
    e["i101"] = it.str.contains("1.01", regex=False)
    e["i502"] = it.str.contains("5.02", regex=False)
    e["i701"] = it.str.contains("7.01", regex=False)
    e["dist"] = np.logical_or.reduce([it.str.contains(x, regex=False) for x in EIGHTK_DISTRESS_ITEMS])
    return e[["permno", "day", "usable", "i101", "i502", "i701", "dist"]].reset_index(drop=True)


def _slice(times: np.ndarray, d: pd.Timestamp, days: int) -> tuple[int, int]:
    lo = int(np.searchsorted(times, np.datetime64(d - pd.Timedelta(days=days)), "right"))
    hi = int(np.searchsorted(times, np.datetime64(d), "right"))
    return lo, hi


def eightk_panel(ev: pd.DataFrame, dates: Iterable) -> pd.DataFrame:
    """Counts of 8-Ks usable in (d-W, d]; a permno with any 8-K usable in (d-365, d]
    is covered (zeros), otherwise absent."""
    e = ev.sort_values("usable", kind="mergesort").reset_index(drop=True)
    tt = e["usable"].to_numpy(dtype="datetime64[ns]")
    rows = []
    for d in sorted({pd.Timestamp(x) for x in dates}):
        lo365, hi = _slice(tt, d, 365)
        if hi <= lo365:
            continue
        w365 = e.iloc[lo365:hi]
        w90 = e.iloc[_slice(tt, d, 90)[0]:hi]
        w180 = e.iloc[_slice(tt, d, 180)[0]:hi]
        f = pd.DataFrame(index=pd.Index(w365["permno"].unique(), name="permno"))
        f["n8k_90"] = w90.groupby("permno").size()
        f["n101_90"] = w90[w90["i101"]].groupby("permno").size()
        f["n701_90"] = w90[w90["i701"]].groupby("permno").size()
        f["n502_180"] = w180[w180["i502"]].groupby("permno").size()
        f["distress_365"] = w365[w365["dist"]].groupby("permno").size()
        f = f.fillna(0.0).astype(float).reset_index()
        f["date"] = d
        rows.append(f)
    if not rows:
        return pd.DataFrame(columns=["date", "permno", *EIGHTK_COLS])
    return pd.concat(rows, ignore_index=True)[["date", "permno", *EIGHTK_COLS]]


# ── 4. analyst timing and skill (IBES targets) ──────────────────────────────

def first_movers(raises: pd.DataFrame, *, gap_days: int = FIRST_MOVER_GAP_DAYS) -> np.ndarray:
    """True where no raise by ANY broker on the same permno fell in [day - gap, day).

    `raises`: permno, day. Uses only strictly earlier days (a same-day raise by
    another broker does not disqualify: no within-day order is known).
    """
    r = raises[["permno", "day"]].reset_index(drop=True).copy()
    r["_i"] = np.arange(len(r))
    days = r.drop_duplicates(["permno", "day"]).sort_values(["permno", "day"])
    prev = days.groupby("permno")["day"].shift(1)
    days["fm"] = prev.isna() | ((days["day"] - prev).dt.days > gap_days)
    m = r.merge(days[["permno", "day", "fm"]], on=["permno", "day"], how="left").sort_values("_i")
    return m["fm"].to_numpy(dtype=bool)


def price_context(ev: pd.DataFrame, daily: pd.DataFrame, mkt: pd.Series) -> pd.DataFrame:
    """For each event (permno, day): ret10 over the 10 sessions ending the session
    BEFORE `day`, sig10 (63-session daily sd before `day` x sqrt 10, >= 40 obs),
    exc63 = stock minus market compounded return from the close of the event
    session (first session >= day) to 63 sessions later, and `res_day` = that
    later session (NaT when it is beyond the data).
    """
    dly = daily.sort_values(["permno", "date"]).reset_index(drop=True).copy()
    r = pd.to_numeric(dly["ret"], errors="coerce").astype(float)
    dly["lr"] = np.log1p(r.fillna(0.0))
    dly["r"] = r
    dly["cum"] = dly.groupby("permno")["lr"].cumsum()
    dly["pos"] = dly.groupby("permno").cumcount()
    g = dly.groupby("permno")["r"]
    dly["sd63"] = g.transform(lambda s: s.rolling(63, min_periods=40).std())
    mk = np.log1p(mkt.astype(float).fillna(0.0)).cumsum()
    e = ev.reset_index(drop=True).copy()
    e["_i"] = np.arange(len(e))
    m = pd.merge_asof(e.sort_values("day"), dly[["date", "permno", "pos"]].sort_values("date"),
                      left_on="day", right_on="date", by="permno", direction="forward",
                      tolerance=pd.Timedelta(days=7))
    m = m.sort_values("_i").reset_index(drop=True)
    ok = m["pos"].notna().to_numpy()
    pos = np.where(ok, m["pos"].fillna(0).astype(int).to_numpy(), 0)
    key = dly.set_index(["permno", "pos"])[["date", "cum", "sd63"]]
    pm = m["permno"].to_numpy()

    def at(off):
        return key.reindex(pd.MultiIndex.from_arrays([pm, pos + off]))

    b1, b11, e0, e63 = at(-1), at(-11), at(0), at(EXC_SESSIONS)
    ret10 = np.expm1(b1["cum"].to_numpy() - b11["cum"].to_numpy())
    sig10 = b1["sd63"].to_numpy() * np.sqrt(LEAD_SESSIONS)
    stock = np.expm1(e63["cum"].to_numpy() - e0["cum"].to_numpy())
    mret = np.expm1(mk.reindex(e63["date"].to_numpy()).to_numpy() - mk.reindex(e0["date"].to_numpy()).to_numpy())
    out = e.copy()
    out["ret10"] = np.where(ok, ret10, np.nan)
    out["sig10"] = np.where(ok, sig10, np.nan)
    out["exc63"] = np.where(ok, stock - mret, np.nan)
    out["res_day"] = pd.to_datetime(np.where(ok & np.isfinite(stock), e63["date"].to_numpy(), np.datetime64("NaT")))
    return out.drop(columns="_i")


def analyst2_panel(ev: pd.DataFrame, dates: Iterable) -> pd.DataFrame:
    """The library's lead/chase, first-mover and skill columns on each decision date.

    `ev`: permno, broker, usable, sign (+1 raise / -1 lower / 0), ret10, sig10,
    exc63, res_day, first_mover. Window (d-90, d] on `usable`; skill from raises
    with res_day <= d. Covered = any event usable in (d-365, d] (zeros);
    otherwise absent.
    """
    e = ev.sort_values("usable", kind="mergesort").reset_index(drop=True).copy()
    e["raise"] = e["sign"] > 0
    e["lower"] = e["sign"] < 0
    e["lead"] = e["raise"] & (e["ret10"] <= 0)
    e["chase"] = e["raise"] & (e["ret10"] > e["sig10"])
    e["fm"] = e["raise"] & e["first_mover"].astype(bool)
    tt = e["usable"].to_numpy(dtype="datetime64[ns]")
    rr = e[e["raise"] & e["exc63"].notna() & e["res_day"].notna()].sort_values("res_day", kind="mergesort")
    rt = rr["res_day"].to_numpy(dtype="datetime64[ns]")
    # running per-broker sums over resolved raises, evaluated at each date
    rows = []
    for d in sorted({pd.Timestamp(x) for x in dates}):
        lo365, hi = _slice(tt, d, 365)
        if hi <= lo365:
            continue
        lo90, _ = _slice(tt, d, 90)
        w = e.iloc[lo90:hi]
        k = int(np.searchsorted(rt, np.datetime64(d), "right"))
        sk = rr.iloc[:k].groupby("broker")["exc63"].agg(["mean", "count"])
        skilled = set(sk.index[(sk["count"] >= SKILL_MIN_RESOLVED) & (sk["mean"] > 0)])
        wf = w["broker"].isin(skilled)
        g = pd.DataFrame({
            "permno": w["permno"].to_numpy(),
            "lead": w["lead"].to_numpy(float), "chase": w["chase"].to_numpy(float),
            "fm": w["fm"].to_numpy(float), "sfm": (w["fm"] & wf).to_numpy(float),
            "skill": (w["raise"] & wf).to_numpy(float) - (w["lower"] & wf).to_numpy(float),
            "unskill": (w["raise"] & ~wf).to_numpy(float) - (w["lower"] & ~wf).to_numpy(float),
        }).groupby("permno").sum()
        f = pd.DataFrame(index=pd.Index(e["permno"].iloc[lo365:hi].unique(), name="permno")).join(g)
        f = f.fillna(0.0)
        rows.append(pd.DataFrame({
            "date": d, "permno": f.index.to_numpy(),
            "lead_raises_90": f["lead"].to_numpy(), "chase_raises_90": f["chase"].to_numpy(),
            "lead_minus_chase_90": (f["lead"] - f["chase"]).to_numpy(),
            "first_mover_raises_90": f["fm"].to_numpy(), "skill_net_raises_90": f["skill"].to_numpy(),
            "unskilled_net_raises_90": f["unskill"].to_numpy(), "skill_first_mover_90": f["sfm"].to_numpy(),
            "_n_skilled": len(skilled), "_n_active": int(w["broker"].nunique()),
            "_n_active_skilled": int(w.loc[wf, "broker"].nunique())}))
    if not rows:
        return pd.DataFrame(columns=["date", "permno", *ANALYST2_COLS])
    return pd.concat(rows, ignore_index=True)


def cluster_age_panel(raises: pd.DataFrame, keys: pd.DataFrame, *, gap_days: int = 30,
                      active_days: int = 30) -> np.ndarray:
    """cluster_age_days (`strategy_library_ext.cluster_age_days` on permno): days since
    the active raise chain began, from raises USABLE on or before the date; NaN when
    the last raise is more than `active_days` old."""
    r = raises[["permno", "usable"]].drop_duplicates().sort_values(["permno", "usable"], kind="mergesort")
    gap = r.groupby("permno")["usable"].diff().dt.days
    r = r.assign(cid=(gap.isna() | (gap > gap_days)).cumsum())
    r["start"] = r.groupby("cid")["usable"].transform("min")
    f = asof_panel(keys, r.rename(columns={"usable": "u"}).assign(
        start_f=lambda x: x["start"].astype("int64").astype(float),
        u_f=lambda x: x["u"].astype("int64").astype(float)), ["start_f", "u_f"], on="u")
    d = pd.to_datetime(keys["date"]).astype("datetime64[ns]").astype("int64").to_numpy().astype(float)
    ns = 86400e9
    since_last = (d - f["u_f"].to_numpy(dtype=float)) / ns
    age = (d - f["start_f"].to_numpy(dtype=float)) / ns
    return np.where(since_last <= active_days, age, np.nan)


def reliability_claims(ev: pd.DataFrame) -> pd.DataFrame:
    """IBES revisions as resolved claims for `pit_features.firm_reliability`:
    estimid, direction (+1/-1), outcome (1 if sign x exc63 > 0), public_at. The
    resolution check there is public_at + 92 days < d; here public_at is SHIFTED
    so that public_at + 92 days == res_day + 1 day (the claim counts only after
    its 63rd session has closed)."""
    c = ev[(ev["sign"] != 0) & ev["exc63"].notna() & ev["res_day"].notna()].copy()
    return pd.DataFrame({"estimid": c["broker"].to_numpy(), "direction": c["sign"].to_numpy(),
                         "outcome": (c["sign"] * c["exc63"] > 0).astype(float).to_numpy(),
                         "public_at": (pd.to_datetime(c["res_day"]) + pd.Timedelta(days=1)
                                       - pd.Timedelta(days=92)).to_numpy()})


# ── 5. Compustat quarterly ──────────────────────────────────────────────────

def fund_available(q: pd.DataFrame) -> pd.Series:
    """max(rdq, datadate + deadline) + FUND_EXTRA_DAYS; deadline 45 days (fqtr 1-3)
    or 90 days (fqtr 4 / unknown)."""
    dd = pd.to_datetime(q["datadate"])
    rdq = pd.to_datetime(q["rdq"], errors="coerce")
    fq = pd.to_numeric(q["fqtr"], errors="coerce")
    dl = np.where(fq.isin([1, 2, 3]).to_numpy(), FUND_DEADLINE_Q, FUND_DEADLINE_Q4)
    deadline = dd + pd.to_timedelta(dl, unit="D")
    av = pd.concat([rdq.where(rdq >= dd), deadline], axis=1).max(axis=1)
    return (av + pd.Timedelta(days=FUND_EXTRA_DAYS)).dt.normalize()


def _ttm(g, col: str) -> pd.Series:
    return g[col].transform(lambda s: s.rolling(4, min_periods=4).sum())


def fund_features(q: pd.DataFrame) -> pd.DataFrame:
    """Compustat fundq (one company) -> the library's SEC-facts columns on TTM flows.

    `q`: permno, gvkey, datadate, fqtr, rdq, saleq, cogsq, oiadpq, niq, atq, cheq,
    dlttq, dlcq, ceqq, xrdq, xsgaq. Rows must be consecutive quarters for the
    TTM sums; a gap breaks the chain (NaN). "One year earlier" is four quarters
    back (the vendor's four-filings-back convention).
    """
    d = q.sort_values(["gvkey", "datadate"]).reset_index(drop=True).copy()
    d["datadate"] = pd.to_datetime(d["datadate"])
    g = d.groupby("gvkey", sort=False)
    gap = (d["datadate"] - g["datadate"].shift(1)).dt.days
    d["_seg"] = (gap.isna() | ~gap.between(80, 100)).cumsum()
    g = d.groupby("_seg", sort=False)
    for c in ("saleq", "cogsq", "oiadpq", "niq", "xrdq", "xsgaq"):
        d[c] = pd.to_numeric(d[c], errors="coerce").astype(float)
    rev, cogs, oi, ni = _ttm(g, "saleq"), _ttm(g, "cogsq"), _ttm(g, "oiadpq"), _ttm(g, "niq")
    at = pd.to_numeric(d["atq"], errors="coerce").astype(float)
    ceq = pd.to_numeric(d["ceqq"], errors="coerce").astype(float)
    debt = (pd.to_numeric(d["dlttq"], errors="coerce").fillna(0.0)
            + pd.to_numeric(d["dlcq"], errors="coerce").fillna(0.0)).where(at.notna())
    cash = pd.to_numeric(d["cheq"], errors="coerce").astype(float)
    ats = at.where(at > 0)
    d["gross_margin_q"] = (rev - cogs) / rev.where(rev > 0)
    d["_om"] = oi / rev.where(rev > 0)
    d["_roa"] = ni / ats
    d["_dat"] = debt / ats
    d["ope_be"] = oi / ceq.where(ceq > 0)
    d["cash_at"] = cash / ats
    d["_rev"] = rev
    d["_ni"] = ni
    d["_at"] = at
    g = d.groupby("_seg", sort=False)
    p4 = lambda c: g[c].shift(4)                                     # noqa: E731
    d["at_gr1"] = (d["_at"] - p4("_at")) / p4("_at").where(p4("_at") > 0)
    d["rev_gr"] = (d["_rev"] - p4("_rev")) / p4("_rev").where(p4("_rev") > 0)
    d["gm_chg"] = d["gross_margin_q"] - p4("gross_margin_q")
    d["inflection"] = d["rev_gr"] * d["gm_chg"]
    g = d.groupby("_seg", sort=False)
    d["rev_accel"] = d["rev_gr"] - g["rev_gr"].shift(4)
    d["om_chg"] = d["_om"] - g["_om"].shift(4)
    d["roa_chg"] = d["_roa"] - g["_roa"].shift(4)
    d["debt_at_chg"] = d["_dat"] - g["_dat"].shift(4)
    pni, pgm, prg = g["_ni"].shift(4), g["gm_chg"].shift(4), g["rev_gr"].shift(4)
    d["ni_turn"] = ((d["_ni"] > 0) & (pni <= 0)).astype(float).where(pni.notna() & d["_ni"].notna())
    d["gm_turn"] = ((d["gm_chg"] > 0) & (pgm <= 0)).astype(float).where(pgm.notna() & d["gm_chg"].notna())
    d["rev_turn"] = ((d["rev_gr"] > 0) & (prg <= 0)).astype(float).where(prg.notna() & d["rev_gr"].notna())
    d["rd_intensity"] = _ttm(g, "xrdq") / ats
    # organisation capital: perpetual inventory on TTM SG&A at each fiscal Q4
    # (Eisfeldt-Papanikolaou; 15% depreciation, g + delta = 25% for the seed),
    # carried to the next three quarters (ffill within the chain)
    sga = _ttm(g, "xsgaq")
    oc = np.full(len(d), np.nan)
    is_q4 = pd.to_numeric(d["fqtr"], errors="coerce").to_numpy() == 4
    seg = d["_seg"].to_numpy()
    prev_seg, prev_oc = None, np.nan
    for i in np.flatnonzero(is_q4):
        s = sga.iat[i]
        if not np.isfinite(s):
            prev_seg, prev_oc = seg[i], np.nan
            continue
        oc[i] = (0.85 * prev_oc + s) if (seg[i] == prev_seg and np.isfinite(prev_oc)) else s / 0.25
        prev_seg, prev_oc = seg[i], oc[i]
    d["_oc"] = oc
    d["_oc"] = d.groupby("_seg", sort=False)["_oc"].ffill(limit=3)
    d["org_capital"] = d["_oc"] / ats
    d["_ni_ttm"], d["_oi_ttm"], d["_debt"], d["_cash"], d["_ceq"] = ni, oi, debt, cash, ceq
    d["available"] = fund_available(d)
    for c in FUND_COLS + FUND_LEVEL_COLS:
        d[c] = d[c].replace([np.inf, -np.inf], np.nan)
    return d[["permno", "gvkey", "datadate", "available", *FUND_COLS, *FUND_LEVEL_COLS]]


def value_columns(mv: np.ndarray, ni_ttm, oi_ttm, debt, cash, ceq) -> dict:
    """earnings_yield, ebit_ev, ebit_ic (`strategy_library_ext` definitions); the
    Compustat flows and balances are in $ millions, `mv` in $."""
    mv = np.asarray(mv, dtype=float)
    ni, oi, de, ca, eq = (np.asarray(x, dtype=float) * 1e6 for x in (ni_ttm, oi_ttm, debt, cash, ceq))
    with np.errstate(divide="ignore", invalid="ignore"):
        ey = np.where(mv > 0, ni / mv, np.nan)
        ev = mv + de - ca
        ebit_ev = np.where(ev > 0, oi / ev, np.nan)
        ic = eq + de - ca
        ebit_ic = np.where(ic > 0, oi / ic, np.nan)
    return {"earnings_yield": ey, "ebit_ev": ebit_ev, "ebit_ic": ebit_ic}
