"""The CRSP half of the sizing lab (2026-09-29): experiments 2 and 4, and a foreign-slice
replication of experiments 1 and 3, on a survivorship-free CRSP 2013-2024 world.

Called by `python -m scripts.sizing_lab --part crsp`; not a CLI of its own.

INPUTS (all local, already licensed, read-only; nothing is pulled):
* `wrds/crsp_dsf_<y>.parquet` 2012-2024 (permno, date, ret, prc, vol), restricted to the
  permnos EVER eligible in `crsp_pit/crsp_pit_monthly_v1.parquet` (price >= $5, >= $100M
  dollar volume in the month; the monthly `eligible` flag decides selectability).
* `wrds/bulk/crsp__dsedelist.parquet`: the delisting return is booked on the session after
  the last trade (a missing dlret with a performance code 400-599 takes -30%, the library's
  fill); the name is cash afterwards.
* `wrds/compustat_fundq.parquet` rdq (the report date) via `wrds/link_ccm.parquet`
  (LU/LC, P/C, date-valid): the earnings calendar. ASSUMPTION stated on the receipt: a
  report date is treated as known the session before (scheduled dates are public weeks
  ahead; a minority move -- not modelled).
* `wrds/optionm_surface30d_<y>.parquet`: 30-day, |delta| = 50 implied vol; ATM IV = the mean
  of the call (+50) and put (-50). Linked by `wrds/link_optionm_crsp.parquet` (score 1-2,
  date-valid). The surface is end-of-day: the signal uses the decision date's IV, the
  straddle is PRICED at the next session's IV (entry), never the same close.
* `wrds/ff_factors_daily.parquet`: the market (mktrf + rf).
"""
from __future__ import annotations

import math
import time
import warnings

import numpy as np
import pandas as pd

from backend.services import move_size_sizing as MS
from scripts import sizing_lab as L

W = L.OPT / "wrds"
YEARS = range(2012, 2025)
STRADDLE_T = 30.0 / 365.0
ATM_STRADDLE_FACTOR = math.sqrt(2.0 / math.pi)       # E|Z| : ATM straddle ~ 0.798 sigma sqrt(T) S
STRADDLE_COST_OF_PREMIUM = 0.10                       # round trip, declared; sensitivity 0.05 / 0.20
STRADDLE_BUDGET = 0.02                                # premium per leg as a share of equity (utility read)
H = 21                                                # the straddle / size horizon in sessions

CRSP_SPEC_PX = {"vol_21": "log", "vol_63": "log", "vol_252": "log", "maxabs_21": "log",
                "absret_21": "abs", "absret_252": "abslog", "dv_log": "raw", "px_log": "raw"}
CRSP_SPEC_EARN = CRSP_SPEC_PX | {"ems4": "log", "earn_next": "raw", "earn_x_ems": "raw"}
#: the point-in-time earnings flag: next date projected from the last KNOWN report date
CRSP_SPEC_EARN_PIT = CRSP_SPEC_PX | {"ems4": "log", "earn_next_pit": "raw", "earn_x_ems_pit": "raw"}
PIT_STEP = pd.Timedelta(days=91)


def load_daily() -> dict:
    pit = pd.read_parquet(L.OPT / "crsp_pit" / "crsp_pit_monthly_v1.parquet",
                          columns=["permno", "date", "eligible", "dollar_vol", "ticker"])
    pit["date"] = pd.to_datetime(pit["date"])
    ever = np.sort(pit.loc[pit["eligible"], "permno"].unique())
    frames = []
    for y in YEARS:
        f = pd.read_parquet(W / f"crsp_dsf_{y}.parquet", columns=["permno", "date", "ret", "prc", "vol"])
        f = f[f["permno"].isin(ever)]
        frames.append(f)
    d = pd.concat(frames, ignore_index=True)
    del frames
    d["date"] = pd.to_datetime(d["date"])
    dates = pd.DatetimeIndex(np.sort(d["date"].unique()))
    perms = ever
    di = np.searchsorted(dates, d["date"].to_numpy())
    pi = np.searchsorted(perms, d["permno"].to_numpy())
    T, N = len(dates), len(perms)
    R = np.full((T, N), np.nan, dtype=np.float64)
    P = np.full((T, N), np.nan, dtype=np.float32)
    DV = np.full((T, N), np.nan, dtype=np.float32)
    R[di, pi] = pd.to_numeric(d["ret"], errors="coerce").to_numpy()
    prc = np.abs(pd.to_numeric(d["prc"], errors="coerce").to_numpy())
    P[di, pi] = prc
    DV[di, pi] = prc * pd.to_numeric(d["vol"], errors="coerce").to_numpy()
    n_rows = len(d)
    del d
    # delisting returns on the session after the last trade
    dl = pd.read_parquet(W / "bulk" / "crsp__dsedelist.parquet", columns=["permno", "dlstdt", "dlstcd", "dlret"])
    dl = dl[dl["permno"].isin(perms)]
    fin = np.isfinite(R)
    last = np.where(fin.any(axis=0), T - 1 - np.argmax(fin[::-1], axis=0), -1)
    n_dl, n_fill = 0, 0
    for _, row in dl.iterrows():
        j = int(np.searchsorted(perms, row["permno"]))
        lt = last[j]
        if lt < 0 or lt >= T - 1:
            continue
        dt = pd.Timestamp(row["dlstdt"]) if pd.notna(row["dlstdt"]) else None
        if dt is None or dt < dates[0] or dt > dates[-1] + pd.Timedelta(days=40):
            continue
        code = row["dlstcd"]
        r = row["dlret"]
        if not np.isfinite(r if r is not None else np.nan):
            if code is not None and np.isfinite(code) and 400 <= code < 600:
                r, n_fill = -0.30, n_fill + 1
            else:
                continue
        if code is not None and np.isfinite(code) and code < 200:
            continue                       # 100s = still active
        R[lt + 1, j] = r
        n_dl += 1
    ff = pd.read_parquet(W / "ff_factors_daily.parquet")
    ff["date"] = pd.to_datetime(ff["date"])
    mk = (ff.set_index("date")["mktrf"] + ff.set_index("date")["rf"]).reindex(dates).to_numpy()
    return {"dates": dates, "perms": perms, "R": R, "P": P, "DV": DV, "mkt": mk, "pit": pit,
            "n_rows": n_rows, "n_delist_booked": n_dl, "n_delist_filled_minus30": n_fill}


def earnings_events(D: dict) -> pd.DataFrame:
    fq = pd.read_parquet(W / "compustat_fundq.parquet", columns=["gvkey", "datadate", "rdq"]).dropna(subset=["rdq"])
    fq["rdq"] = pd.to_datetime(fq["rdq"])
    fq = fq.drop_duplicates(["gvkey", "rdq"])
    lk = pd.read_parquet(W / "link_ccm.parquet")
    lk = lk[lk["linktype"].isin(["LU", "LC"]) & lk["linkprim"].isin(["P", "C"])].dropna(subset=["permno"])
    lk["linkdt"] = pd.to_datetime(lk["linkdt"])
    lk["linkenddt"] = pd.to_datetime(lk["linkenddt"]).fillna(pd.Timestamp("2099-12-31"))
    e = fq.merge(lk[["gvkey", "permno", "linkdt", "linkenddt"]], on="gvkey")
    e = e[(e["rdq"] >= e["linkdt"]) & (e["rdq"] <= e["linkenddt"])]
    e["permno"] = e["permno"].astype(np.int64)
    e = e[e["permno"].isin(D["perms"])].drop_duplicates(["permno", "rdq"])
    dates = D["dates"]
    e["d0"] = np.searchsorted(dates, e["rdq"].to_numpy())          # first session >= rdq
    e = e[(e["d0"] >= 1) & (e["d0"] + 1 < len(dates))].copy()
    e["j"] = np.searchsorted(D["perms"], e["permno"].to_numpy())
    R, mk = D["R"], D["mkt"]
    r0, r1 = R[e["d0"], e["j"]], R[e["d0"] + 1, e["j"]]
    m0, m1 = mk[e["d0"]], mk[e["d0"] + 1]
    e["ret2"] = (1 + r0) * (1 + r1) - 1
    e["abn2"] = e["ret2"] - ((1 + m0) * (1 + m1) - 1)
    e = e[np.isfinite(e["abn2"])].sort_values(["permno", "d0"]).reset_index(drop=True)
    e["abs_abn2"] = e["abn2"].abs()
    # past-4 mean |abn| known BEFORE this event (previous events' windows closed at d0' + 1 < d0 - 1)
    e["ems4_prior"] = (e.groupby("permno")["abs_abn2"].transform(lambda s: s.shift(1).rolling(4, min_periods=2).mean()))
    e["n_prior"] = e.groupby("permno").cumcount()
    return e[["permno", "j", "rdq", "d0", "ret2", "abn2", "abs_abn2", "ems4_prior", "n_prior"]]


def trailing_vol(R: np.ndarray, i: int, n: int, need: int) -> np.ndarray:
    x = R[max(0, i - n + 1): i + 1]
    ok = np.isfinite(x).sum(axis=0) >= need
    with warnings.catch_warnings(), np.errstate(invalid="ignore"):
        warnings.simplefilter("ignore", RuntimeWarning)       # columns with < 2 obs -> NaN, masked below
        v = np.nanstd(x, axis=0, ddof=1) * math.sqrt(252)
    return np.where(ok, v, np.nan)


def atm_iv(dates_needed: pd.DatetimeIndex, perms: np.ndarray) -> pd.DataFrame:
    """ATM 30-day IV (mean of call +50 and put -50) on the needed dates, keyed by permno."""
    lk = pd.read_parquet(W / "link_optionm_crsp.parquet").dropna(subset=["permno"])
    lk = lk[lk["score"] <= 2]
    lk["sdate"] = pd.to_datetime(lk["sdate"])
    lk["edate"] = pd.to_datetime(lk["edate"])
    lk["permno"] = lk["permno"].astype(np.int64)
    lk = lk[lk["permno"].isin(perms)]
    need = set(pd.DatetimeIndex(dates_needed).strftime("%Y-%m-%d"))
    out = []
    for y in range(2013, 2025):
        p = W / f"optionm_surface30d_{y}.parquet"
        if not p.exists():
            continue
        s = pd.read_parquet(p, columns=["secid", "date", "delta", "impl_volatility"])
        s = s[s["delta"].abs() == 50]
        s = s[s["date"].astype(str).isin(need)]
        g = s.groupby(["secid", "date"])["impl_volatility"].mean().reset_index()
        out.append(g)
    iv = pd.concat(out, ignore_index=True)
    iv["date"] = pd.to_datetime(iv["date"])
    m = iv.merge(lk[["secid", "permno", "sdate", "edate"]], on="secid")
    m = m[(m["date"] >= m["sdate"]) & (m["date"] <= m["edate"])]
    m = m.groupby(["permno", "date"])["impl_volatility"].mean().rename("iv").reset_index()
    return m


def build_panel(D: dict, ev: pd.DataFrame) -> pd.DataFrame:
    dates, perms, R, P, DV = D["dates"], D["perms"], D["R"], D["P"], D["DV"]
    T, N = R.shape
    Rf = np.where(np.isfinite(R), R, 0.0)
    G = np.cumprod(1.0 + Rf, axis=0)                       # dead / halted -> flat (cash)
    s = pd.Series(np.arange(T), index=dates)
    me = s.groupby(dates.to_period("M")).max().to_numpy()
    me = me[(dates[me] >= pd.Timestamp("2013-01-01")) & (dates[me] <= pd.Timestamp("2024-11-30"))]
    pit = D["pit"]
    pit_key = pit.assign(ym=pit["date"].dt.to_period("M"))
    elig_map = {(int(p), ym): bool(e) for p, ym, e in zip(pit_key["permno"], pit_key["ym"], pit_key["eligible"])}
    # earnings: per permno sorted d0 and |abn| history
    ev_by = {j: g for j, g in ev.groupby("j")}
    frames = []
    for pos, i in enumerate(me):
        ym = dates[i].to_period("M")
        elig = np.array([elig_map.get((int(p), ym), False) for p in perms])
        trade = np.isfinite(R[i]) & np.isfinite(P[i])
        rows = np.where(trade & elig)[0]
        if not len(rows):
            continue
        f = {}
        f["vol_21"] = trailing_vol(R, i, 21, 15)[rows]
        f["vol_63"] = trailing_vol(R, i, 63, 40)[rows]
        f["vol_252"] = trailing_vol(R, i, 252, 120)[rows]
        x21 = R[max(0, i - 20): i + 1][:, rows]
        with np.errstate(invalid="ignore", all="ignore"):
            f["maxabs_21"] = np.nanmax(np.abs(x21), axis=0)
        f["absret_21"] = G[i, rows] / G[max(0, i - 21), rows] - 1.0
        f["absret_252"] = G[i, rows] / G[max(0, i - 252), rows] - 1.0
        f["mom_252_21"] = G[max(0, i - 21), rows] / G[max(0, i - 252), rows] - 1.0
        if i < 252:
            f["mom_252_21"] = np.full(len(rows), np.nan)
        dvw = DV[max(0, i - 62): i + 1][:, rows]
        with np.errstate(all="ignore"):
            mdv = np.nanmedian(dvw, axis=0)
        f["median_dollar_vol"] = mdv
        f["dv_log"] = np.log1p(mdv)
        f["px_log"] = np.log(P[i, rows].astype(float))
        # earnings: past-4 |abn| known at i; next event inside (i+1, i+1+H]
        ems = np.full(len(rows), np.nan)
        nxt = np.zeros(len(rows))
        nxt_pit = np.zeros(len(rows))
        nxt_d0 = np.full(len(rows), -1)
        t_entry = dates[min(i + 1, T - 1)]
        t_exit = dates[min(i + 1 + H, T - 1)]
        for k, j in enumerate(rows):
            g = ev_by.get(j)
            if g is None:
                continue
            d0 = g["d0"].to_numpy()
            done = d0 + 1 <= i
            if done.sum() >= 2:
                ems[k] = float(g["abs_abn2"].to_numpy()[done][-4:].mean())
                # PIT projection: the last KNOWN report date + 91-day steps (no future rdq read)
                nd = pd.Timestamp(g["rdq"].to_numpy()[done][-1]) + PIT_STEP
                while nd <= t_entry:
                    nd += PIT_STEP
                nxt_pit[k] = 1.0 if nd <= t_exit else 0.0
            fut = (d0 >= i + 2) & (d0 + 1 <= i + 1 + H)
            if fut.any():
                nxt[k] = 1.0
                nxt_d0[k] = int(d0[fut][0])
        f["ems4"] = ems
        f["earn_next"] = nxt
        f["earn_x_ems"] = nxt * ems
        f["earn_next_pit"] = nxt_pit
        f["earn_x_ems_pit"] = nxt_pit * ems
        f["next_d0"] = nxt_d0
        # forward: entry at close i+1, exit at close of the next decision + 1
        fwd = np.full(len(rows), np.nan)
        r21 = np.full(len(rows), np.nan)
        dead = np.zeros(len(rows), dtype=bool)
        if pos + 1 < len(me) and me[pos + 1] + 1 < T:
            e0, e1 = i + 1, me[pos + 1] + 1
            fwd = G[e1, rows] / G[e0, rows] - 1.0
            fin = np.isfinite(R[e0: e1 + 1][:, rows])
            dead = ~fin[-1]
        oracle = np.full(len(rows), np.nan)
        if i + 1 + H < T:
            r21 = G[i + 1 + H, rows] / G[i + 1, rows] - 1.0
            oracle = trailing_vol(R, i + 1 + H, H, 15)[rows]     # realised vol OVER the hold: look-ahead
        f["size_oracle"] = oracle
        f["fwd_ret"] = fwd
        f["r21"] = r21
        f["dead_by_exit"] = dead
        fr = pd.DataFrame(f)
        fr.insert(0, "j", rows)
        fr.insert(0, "symbol", perms[rows].astype(str))
        fr.insert(0, "date", dates[i])
        fr["i"] = i
        frames.append(fr)
    panel = pd.concat(frames, ignore_index=True)
    panel["eligible"] = True
    return panel, G


def avoid_returns(panel: pd.DataFrame, D: dict, G: np.ndarray, costs: dict) -> np.ndarray:
    """The name's forward return with its earnings window (d0, d0+1) sat out in cash, minus
    one extra band round trip on the avoided weight."""
    R = D["R"]
    out = panel["fwd_ret"].to_numpy(dtype=float).copy()
    d0 = panel["next_d0"].to_numpy()
    j = panel["j"].to_numpy()
    mdv = panel["median_dollar_vol"].to_numpy(dtype=float)
    has = (d0 >= 0) & np.isfinite(out)
    for k in np.where(has)[0]:
        a = R[d0[k], j[k]]
        b = R[d0[k] + 1, j[k]]
        g2 = (1 + (a if np.isfinite(a) else 0.0)) * (1 + (b if np.isfinite(b) else 0.0))
        rt = MS.band_round_trip_bps(mdv[k], costs) / 1e4
        out[k] = (1 + out[k]) / g2 - 1 - rt
    return out


def event_level(ev: pd.DataFrame, D: dict) -> dict:
    """Does past earnings-move size predict the next one beyond trailing vol? Per calendar
    month of the event: Spearman of each predictor with |abn 2-day|, and the rank
    regression b of |abn| on rank(ems4) + rank(vol_63)."""
    R = D["R"]
    e = ev[(ev["rdq"] >= "2014-01-01") & ev["ems4_prior"].notna()].copy()
    vols = np.full(len(e), np.nan)
    for k, (d0, j) in enumerate(zip(e["d0"].to_numpy(), e["j"].to_numpy())):
        x = R[max(0, d0 - 64): d0 - 1, j]
        x = x[np.isfinite(x)]
        if len(x) >= 40:
            vols[k] = x.std(ddof=1)
    e["vol63_pre"] = vols
    e = e.dropna(subset=["vol63_pre"])
    e["ym"] = pd.to_datetime(e["rdq"]).dt.to_period("M").dt.to_timestamp("M")
    rows = []
    for ym, g in e.groupby("ym"):
        if len(g) < 30:
            continue
        ic_e = MS.spearman(g["ems4_prior"], g["abs_abn2"])
        ic_v = MS.spearman(g["vol63_pre"], g["abs_abn2"])
        zr = lambda s: (s.rank() - s.rank().mean()) / s.rank().std()          # noqa: E731
        X = np.c_[np.ones(len(g)), zr(g["ems4_prior"]), zr(g["vol63_pre"])]
        b, *_ = np.linalg.lstsq(X, zr(g["abs_abn2"]).to_numpy(), rcond=None)
        rows.append({"ym": ym, "n": len(g), "ic_ems": ic_e, "ic_vol": ic_v, "b_ems": b[1], "b_vol": b[2]})
    M = pd.DataFrame(rows).set_index("ym")
    return {"n_events": int(len(e)), "n_months": int(len(M)), "ic_ems_mean": float(M["ic_ems"].mean()),
            "ic_vol_mean": float(M["ic_vol"].mean()),
            "ic_ems_minus_vol": MS.block_stats(M["ic_ems"] - M["ic_vol"], 3),
            "b_ems": MS.block_stats(M["b_ems"], 3), "b_vol": MS.block_stats(M["b_vol"], 3),
            "b_ems_by_year": {str(y): float(v) for y, v in M["b_ems"].groupby(M.index.year).mean().items()},
            "note": "event-level, 2-day abnormal (vs mktrf+rf) return around the Compustat rdq; ems4 = mean "
                    "|abn| of the previous 2-4 events; vol63 = daily sd over the 63 sessions ending two sessions "
                    "before the event; blocks = 3 calendar months"}


def part_crsp(run_id: str) -> dict:
    t0 = time.time()
    costs = L.band_costs()
    D = load_daily()
    L.say(f"  CRSP daily {D['R'].shape} ({D['n_rows']:,} rows), delisting returns booked {D['n_delist_booked']} "
          f"(-30% fills {D['n_delist_filled_minus30']}); {time.time()-t0:.0f}s peak {L.peak_rss_mb()} MB")
    ev = earnings_events(D)
    L.say(f"  earnings events {len(ev):,} ({ev['permno'].nunique()} permnos); {time.time()-t0:.0f}s")
    ev_read = event_level(ev, D)
    L.say(f"  EVENT LEVEL: IC ems {ev_read['ic_ems_mean']:.3f} vs vol {ev_read['ic_vol_mean']:.3f}; "
          f"b_ems {ev_read['b_ems']['mean_monthly']:.3f} t {ev_read['b_ems']['t_blocks']}")
    panel, G = build_panel(D, ev)
    L.say(f"  panel {len(panel):,} rows, {panel['date'].nunique()} dates; {time.time()-t0:.0f}s peak {L.peak_rss_mb()} MB")
    from backend.services import strategy_library as SL
    panel["tiebreak"] = SL._tiebreak(panel)
    elig = np.ones(len(panel), dtype=bool)
    panel["abs_x"] = MS.abs_excess(panel)
    panel["abs_r21"] = panel["r21"].abs()
    panel["size_vol"] = panel["vol_63"]
    panel["size_ridge"], log_px = MS.walk_forward_size(panel, CRSP_SPEC_PX, target="abs_x", gap=2, min_train_dates=12)
    panel["size_ridge_earn"], log_e = MS.walk_forward_size(panel, CRSP_SPEC_EARN, target="abs_x", gap=2,
                                                           min_train_dates=12)
    panel["s21_ridge_earn"], _ = MS.walk_forward_size(panel, CRSP_SPEC_EARN, target="abs_r21", gap=2,
                                                      min_train_dates=12)
    panel["s21_ridge"], _ = MS.walk_forward_size(panel, CRSP_SPEC_PX, target="abs_r21", gap=2, min_train_dates=12)
    panel["size_ridge_pit"], _ = MS.walk_forward_size(panel, CRSP_SPEC_EARN_PIT, target="abs_x", gap=2,
                                                      min_train_dates=12)
    panel["s21_ridge_pit"], _ = MS.walk_forward_size(panel, CRSP_SPEC_EARN_PIT, target="abs_r21", gap=2,
                                                     min_train_dates=12)
    pit_flag_agreement = float((panel["earn_next_pit"] == panel["earn_next"]).mean())
    first = panel.loc[panel["size_ridge_earn"].notna(), "date"].min()
    ok = panel["size_ridge_earn"].notna().to_numpy() & panel["abs_x"].notna().to_numpy()
    qual = {}
    for c in ("size_vol", "size_ridge", "size_ridge_earn", "size_ridge_pit", "size_oracle"):
        qual[c] = MS.per_date_ic(panel, c, "abs_x", mask=ok)
    quality = {"ic_mean": {c: float(v.mean()) for c, v in qual.items()},
               "ridge_minus_vol": MS.block_stats(qual["size_ridge"] - qual["size_vol"], 1),
               "ridge_earn_minus_vol": MS.block_stats(qual["size_ridge_earn"] - qual["size_vol"], 1),
               "ridge_earn_minus_ridge": MS.block_stats(qual["size_ridge_earn"] - qual["size_ridge"], 1),
               "ridge_pit_minus_vol": MS.block_stats(qual["size_ridge_pit"] - qual["size_vol"], 1),
               "ridge_pit_minus_ridge_earn": MS.block_stats(qual["size_ridge_pit"] - qual["size_ridge_earn"], 1),
               "pit_flag_agrees_with_actual_rdq_flag": pit_flag_agreement,
               "oracle_note": "size_oracle = realised daily vol OVER the hold (look-ahead): a ceiling, never a strategy",
               "ridge_earn_minus_vol_by_hold_year": MS.by_hold_year(qual["size_ridge_earn"] - qual["size_vol"])}
    L.say(f"  size IC: {quality['ic_mean']}")
    # ── experiments 1 + 3, foreign slice ──
    panel["size_ridgeqm"] = MS.quantile_map(panel, "size_ridge_earn", "size_vol",
                                            panel["size_ridge_earn"].notna().to_numpy())
    panel["size_ridgepitqm"] = MS.quantile_map(panel, "size_ridge_pit", "size_vol",
                                               panel["size_ridge_pit"].notna().to_numpy())
    for c in ("size_vol", "size_ridge", "size_ridge_earn", "size_ridgeqm", "size_ridgepitqm"):
        panel[f"kap_{c}"] = L.per_date_kappa(panel, c, "fwd_ret", elig)
        panel[f"sig_{c}"] = panel[f"kap_{c}"] * panel[c]
    start = pd.Timestamp(first)
    sel = panel["size_ridge_earn"].notna().to_numpy()
    mom = np.where(sel, panel["mom_252_21"].to_numpy(dtype=float), np.nan)
    size_cols = {"vol": "size_vol", "ridge": "size_ridge_earn", "ridgepx": "size_ridge",
                 "ridgeqm": "size_ridgeqm", "ridgepitqm": "size_ridgepitqm", "oracle": "size_oracle"}
    sigma_cols = {"vol": "sig_size_vol", "ridge": "sig_size_ridge_earn", "ridgeqm": "sig_size_ridgeqm",
                  "ridgepitqm": "sig_size_ridgepitqm"}
    fam = L.book_family(panel, mom, costs=costs, size_cols=size_cols, sigma_cols=sigma_cols, start_date=start)
    rand = {}
    for sd in range(L.N_RANDOM_SEEDS):
        sc = np.where(sel, SL.seeded_noise(2000 + sd)(panel).to_numpy(dtype=float), np.nan)
        rand[sd] = L.family_tranche(L.book_family(panel, sc, costs=costs, size_cols=size_cols,
                                                  sigma_cols=sigma_cols, start_date=start))
    tr_rule = L.family_tranche(fam)
    mkt_m = monthly_market(panel, D, tr_rule["equal"].index)
    ex1 = L.read_family(tr_rule, rand, mkt_m, extra_cmp=(
        ("inv_ridgepx", "inv_vol", "Q1 foreign slice: price-only ridge vs trailing vol"),
        ("inv_ridgepitqm", "inv_vol", "Q1 PRIMARY PIT: point-in-time earnings ridge, dispersion held equal"),
        ("kelly_ridgepitqm", "kelly_vol", "Q3 PRIMARY PIT: half-Kelly, point-in-time earnings ridge"),
        ("vt_ridgepitqm", "vt_vol", "Q3 PIT vol target"),
        ("inv_oracle", "inv_vol", "ORACLE CEILING (look-ahead, diagnostic only): realised hold vol vs trailing vol"),
        ("inv_oracle", "equal", "ORACLE CEILING vs equal weight")))
    L.say(f"  foreign-slice families done {time.time()-t0:.0f}s")
    # ── experiment 2: earnings avoidance / seeking (monthly random-20 books) ──
    ex2 = exp2(panel, D, G, costs, start, mkt_m)
    L.say(f"  exp 2 done {time.time()-t0:.0f}s")
    # ── experiment 4: straddles ──
    ex4 = exp4(panel, D, start)
    L.say(f"  exp 4 done {time.time()-t0:.0f}s peak {L.peak_rss_mb()} MB")
    series = pd.DataFrame({f"rule_{k}": v for k, v in tr_rule.items()} | {"mkt": mkt_m})
    return {"meta": {"daily_shape": list(D["R"].shape), "daily_rows": D["n_rows"],
                     "delisting_returns_booked": D["n_delist_booked"],
                     "delisting_minus30_fills": D["n_delist_filled_minus30"],
                     "earnings_events": int(len(ev)), "earnings_assumption":
                         "rdq treated as known the session before (scheduled); 2-day window d0, d0+1",
                     "universe": "crsp_pit_monthly_v1 eligible (price >= $5, >= $100M/month dollar volume)"},
            "panel": {"rows": int(len(panel)), "dates": int(panel["date"].nunique()),
                      "permnos": int(panel["symbol"].nunique()), "first": str(panel["date"].min().date()),
                      "last": str(panel["date"].max().date()),
                      "rows_dead_by_exit": int(panel["dead_by_exit"].sum())},
            "size_model": {"spec_px": CRSP_SPEC_PX, "spec_earn": CRSP_SPEC_EARN, "gap_dates": 2,
                           "n_fits": len(log_e), "first_forecast": str(start.date()),
                           "last_fit_earn": log_e[-1] if log_e else None},
            "forecast_quality": quality, "exp2_event_level": ev_read,
            "exp1_exp3_books": L.book_table(tr_rule, rand), "exp1_exp3_comparisons": ex1,
            "exp2": ex2, "exp4": ex4, "_series": series, "elapsed_s": round(time.time() - t0, 1)}


def monthly_market(panel: pd.DataFrame, D: dict, index) -> pd.Series:
    """The market over each decision period (entry close i+1 to the next decision + 1)."""
    mk = np.where(np.isfinite(D["mkt"]), D["mkt"], 0.0)
    Gm = np.cumprod(1.0 + mk)
    di = panel.groupby("date")["i"].first().sort_index()
    ii = di.to_numpy()
    out = {}
    for a in range(len(ii) - 1):
        e0, e1 = ii[a] + 1, ii[a + 1] + 1
        if e1 < len(Gm):
            out[di.index[a]] = Gm[e1] / Gm[e0] - 1.0
    return pd.Series(out).reindex(pd.DatetimeIndex(index))


def exp2(panel, D, G, costs, start, mkt) -> dict:
    """Random-20 monthly books among eligible names. HOLD = hold through every earnings
    window. AVOID_ALL = sit out every window. AVOID_TOP_EMS = sit out the third of event
    names with the largest past earnings-move size. AVOID_TOP_VOL = sit out the same count
    chosen by trailing vol (the twin). AVOID_TOP_RATIO = the third with the largest
    ems4 / 2-day trailing sigma (event risk the normal vol misses).
    SEEK_* = random 20 among event names in the top (bottom) third of ems4 / of vol."""
    from backend.services import strategy_library as SL
    fwd_hold = panel["fwd_ret"].to_numpy(dtype=float)
    fwd_avoid = avoid_returns(panel, D, G, costs)
    ev = panel["next_d0"].to_numpy() >= 0
    ems = panel["ems4"].to_numpy(dtype=float)
    vol = panel["vol_63"].to_numpy(dtype=float)
    ratio = ems / (vol / math.sqrt(252) * math.sqrt(2))
    dates = panel["date"].to_numpy()

    def top_third(x):
        s = pd.Series(np.where(ev, x, np.nan)).groupby(dates)
        q = s.transform(lambda v: v.quantile(2 / 3))
        return ev & np.isfinite(x) & (x >= q.to_numpy())

    def bottom_third(x):
        s = pd.Series(np.where(ev, x, np.nan)).groupby(dates)
        q = s.transform(lambda v: v.quantile(1 / 3))
        return ev & np.isfinite(x) & (x <= q.to_numpy())

    t_ems, t_vol, t_ratio = top_third(ems), top_third(vol), top_third(ratio)
    policies = {"HOLD": np.zeros(len(panel), bool), "AVOID_ALL": ev & np.isfinite(ems),
                "AVOID_TOP_EMS": t_ems, "AVOID_TOP_VOL": t_vol, "AVOID_TOP_RATIO": t_ratio}
    sel = panel["size_ridge_earn"].notna().to_numpy() & np.isfinite(fwd_hold)
    books = {p: {} for p in policies}
    pol_fwd = {p: np.where(mask, fwd_avoid, fwd_hold) for p, mask in policies.items()}
    for sd in range(L.N_RANDOM_SEEDS):
        sc = np.where(sel, SL.seeded_noise(3000 + sd)(panel).to_numpy(dtype=float), np.nan)
        for p, mask in policies.items():
            books[p][sd] = MS.run_book(panel, sc, k=L.K, costs=costs, hold_months=1, start_date=start,
                                       fwd=pol_fwd[p]).set_index("date")["net"]
    cmp = {}
    for v, t in (("AVOID_ALL", "HOLD"), ("AVOID_TOP_EMS", "HOLD"), ("AVOID_TOP_VOL", "HOLD"),
                 ("AVOID_TOP_EMS", "AVOID_TOP_VOL"), ("AVOID_TOP_RATIO", "HOLD"),
                 ("AVOID_TOP_RATIO", "AVOID_TOP_VOL")):
        cmp[f"{v}_minus_{t}"] = MS.seed_diff_report(books[v], books[t], mkt.reindex(books[v][0].index), block_len=3)
    # seeking: random 20 inside the named subsets, hold through
    subsets = {"SEEK_TOP_EMS": t_ems, "SEEK_BOTTOM_EMS": bottom_third(ems), "SEEK_TOP_VOL": t_vol,
               "ANY_EVENT": ev & np.isfinite(ems), "ALL": np.ones(len(panel), bool)}
    sb = {p: {} for p in subsets}
    for sd in range(L.N_RANDOM_SEEDS):
        base = SL.seeded_noise(4000 + sd)(panel).to_numpy(dtype=float)
        for p, mask in subsets.items():
            sc = np.where(sel & mask, base, np.nan)
            sb[p][sd] = MS.run_book(panel, sc, k=L.K, costs=costs, hold_months=1, start_date=start
                                    ).set_index("date")["net"]
    for v, t in (("SEEK_TOP_EMS", "SEEK_BOTTOM_EMS"), ("SEEK_TOP_EMS", "SEEK_TOP_VOL"),
                 ("SEEK_TOP_EMS", "ALL"), ("ANY_EVENT", "ALL")):
        cmp[f"{v}_minus_{t}"] = MS.seed_diff_report(sb[v], sb[t], mkt.reindex(sb[v][0].index), block_len=3)
    counts = {p: int(m.sum()) for p, m in policies.items()} | {p: int(m.sum()) for p, m in subsets.items()}
    books_tbl = {}
    for p, d in list(books.items()) + list(sb.items()):
        per = [MS.book_metrics(s) for s in d.values()]
        books_tbl[p] = {k: float(np.median([x[k] for x in per if x.get(k) is not None]))
                        for k in ("cagr", "vol_annual", "sharpe", "max_dd", "terminal_wealth", "log_utility_monthly")}
    return {"rows_flagged": counts, "books_median_over_seeds": books_tbl, "comparisons": cmp,
            "construction": "random-20 among eligible names each month-end (20 seeds), held one month, band "
                            "costs; avoiding a window = the name's return with sessions d0 and d0+1 removed "
                            "(cash, 0) minus one extra band round trip on that weight"}


def market_abs21(panel: pd.DataFrame, D: dict) -> pd.Series:
    """|market return| over each straddle window (close i+1 to close i+1+21): the
    volatility shock a straddle book loads on, used as the regressor of its diff."""
    mk = np.where(np.isfinite(D["mkt"]), D["mkt"], 0.0)
    Gm = np.cumprod(1.0 + mk)
    di = panel.groupby("date")["i"].first().sort_index()
    out = {}
    for d, i in di.items():
        if i + 1 + H < len(Gm):
            out[d] = abs(Gm[i + 1 + H] / Gm[i + 1] - 1.0)
    return pd.Series(out)


def beyond_implied(p: pd.DataFrame) -> dict:
    """Per date: rank(|r21|) ~ rank(implied) + rank(forecast). The forecast's coefficient is
    the size information it carries BEYOND the option market's own forecast."""
    out = {}
    for c in ("f_vol", "f_ridge", "f_ridge_pit", "f_ridge_earn"):
        rows = {}
        for d, g in p.groupby("date"):
            g = g[["abs_r21", "imp_sig", c]].dropna()
            if len(g) < 100:
                continue
            z = [(g[k].rank() - g[k].rank().mean()) / g[k].rank().std() for k in ("abs_r21", "imp_sig", c)]
            X = np.c_[np.ones(len(g)), z[1].to_numpy(), z[2].to_numpy()]
            b, *_ = np.linalg.lstsq(X, z[0].to_numpy(), rcond=None)
            rows[pd.Timestamp(d)] = (b[1], b[2])
        B = pd.DataFrame(rows, index=["b_implied", "b_forecast"]).T.sort_index()
        out[c] = {"b_implied": MS.block_stats(B["b_implied"], 3), "b_forecast": MS.block_stats(B["b_forecast"], 3),
                  "b_forecast_by_hold_year": MS.by_hold_year(B["b_forecast"]),
                  "b_forecast_loo": MS.loo_worst(B["b_forecast"])}
    return out


BREADTHS = (20, 100, "q5")


def _legs(p: pd.DataFrame, c: str, k, cost: float) -> pd.DataFrame:
    rows = []
    for d, g in p.groupby("date"):
        n = len(g)
        kk = max(1, n // 5) if k == "q5" else int(k)
        if n < 2 * kk + 10:
            continue
        r = (g[c] / g["imp_sig"]).to_numpy()
        o = np.argsort(r, kind="mergesort")
        lo, hi = g.iloc[o[:kk]], g.iloc[o[-kk:]]
        long_r = float(hi["payoff_ret"].mean()) - cost
        short_r = -float(lo["payoff_ret"].mean()) - cost
        rows.append({"date": d, "long": long_r, "short": short_r, "ls": 0.5 * (long_r + short_r), "k": kk})
    return pd.DataFrame(rows).set_index("date")


def breadth_sweep(p: pd.DataFrame, mkt_abs: pd.Series) -> dict:
    """DECLARED after the top/bottom-20 read (2026-09-29): the ridge ranks payoff/premium
    better than trailing vol (IC diff t 5.6) but the 20-name P&L diff was t 1.45. The same
    L/S at 20, 100 and a quintile of names; READ AT ITS WORST CELL. Cost 10% of premium;
    the forecast-vs-forecast diff is cost-invariant (same trade count)."""
    out = {}
    worst = None
    for k in BREADTHS:
        legs = {c: _legs(p, c, k, STRADDLE_COST_OF_PREMIUM) for c in ("f_vol", "f_ridge_pit")}
        eq = {c: STRADDLE_BUDGET * df["ls"] for c, df in legs.items()}
        rep = MS.diff_report(eq["f_ridge_pit"], eq["f_vol"], mkt_abs.reindex(eq["f_vol"].index))
        out[str(k)] = {"median_names_per_leg": float(legs["f_vol"]["k"].median()),
                       "ridge_pit_ls_mean": float(legs["f_ridge_pit"]["ls"].mean()),
                       "vol_ls_mean": float(legs["f_vol"]["ls"].mean()),
                       "ridge_pit_minus_vol_equity": rep,
                       "ridge_pit_ls_vs_cash": MS.report_from_diffs(np.log1p(eq["f_ridge_pit"]), eq["f_ridge_pit"],
                                                                    mkt_abs.reindex(eq["f_vol"].index))}
        t = rep["log_utility_diff"]["t_blocks"]
        if worst is None or (t is not None and t < worst[1]):
            worst = (str(k), t)
    out["worst_cell"] = {"breadth": worst[0], "t": worst[1]}
    return out


def exp4(panel, D, start) -> dict:
    """Straddle selection, paper only. Signal at the decision close i: forecast E|r21| / the
    implied E|r| (IV_i * sqrt(30/365) * 0.798). Priced at IV_{i+1} (the entry session's
    close surface), payoff |r21| from close i+1 to close i+1+21. Return on premium
    R = |r21| / premium - 1 - cost. Long the 20 cheapest, short the 20 richest."""
    dates = D["dates"]
    need = pd.DatetimeIndex(sorted(set(dates[panel["i"].unique()]) | set(dates[np.minimum(panel["i"].unique() + 1,
                                                                                           len(dates) - 1)])))
    iv = atm_iv(need, D["perms"])
    mkt_abs = market_abs21(panel, D)
    p = panel[panel["date"] >= start].copy()
    p["permno"] = p["symbol"].astype(np.int64)
    p["entry_date"] = dates[np.minimum(p["i"].to_numpy() + 1, len(dates) - 1)]
    iv_sig = iv.rename(columns={"iv": "iv_sig"})
    iv_ent = iv.rename(columns={"iv": "iv_entry", "date": "entry_date"})
    p = p.merge(iv_sig, on=["permno", "date"], how="left").merge(iv_ent, on=["permno", "entry_date"], how="left")
    p = p[np.isfinite(p["iv_sig"]) & np.isfinite(p["iv_entry"]) & np.isfinite(p["r21"]) & (p["iv_entry"] > 0.02)]
    sq = math.sqrt(STRADDLE_T) * ATM_STRADDLE_FACTOR
    p["imp_sig"] = p["iv_sig"] * sq
    p["prem"] = p["iv_entry"] * sq
    p["payoff_ret"] = p["r21"].abs() / p["prem"] - 1.0
    # forecasts of E|r21| in return units: trailing vol and the ridges (walk-forward, abs_r21 target)
    p["f_vol"] = p["vol_63"] * math.sqrt(H / 252.0) * ATM_STRADDLE_FACTOR
    p["f_ridge"] = p["s21_ridge"]
    p["f_ridge_earn"] = p["s21_ridge_earn"]
    p["f_ridge_pit"] = p["s21_ridge_pit"]
    ic = {}
    for c in ("f_vol", "f_ridge", "f_ridge_earn", "f_ridge_pit", "imp_sig"):
        ic[c] = MS.per_date_ic(p, c, "abs_r21")
    ic_ratio = {c: MS.per_date_ic(p.assign(_x=p[c] / p["imp_sig"], _y=p["abs_r21"] / p["prem"]), "_x", "_y")
                for c in ("f_vol", "f_ridge", "f_ridge_earn", "f_ridge_pit")}
    out = {"n_rows": int(len(p)), "n_dates": int(p["date"].nunique()),
           "median_names_per_date": float(p.groupby("date").size().median()),
           "mean_payoff_ret_all": float(p.groupby("date")["payoff_ret"].mean().mean()),
           "ic_with_abs_r21": {c: float(v.mean()) for c, v in ic.items()},
           "ic_forecast_minus_implied": {c: MS.block_stats(ic[c] - ic["imp_sig"], 3)
                                         for c in ("f_vol", "f_ridge", "f_ridge_earn", "f_ridge_pit")},
           "ic_forecast_minus_implied_by_hold_year": {c: MS.by_hold_year(ic[c] - ic["imp_sig"])
                                                      for c in ("f_ridge_earn", "f_ridge_pit")},
           "ic_ratio_with_realised_over_premium": {c: float(v.mean()) for c, v in ic_ratio.items()},
           "ic_ratio_ridge_earn_minus_vol": MS.block_stats(ic_ratio["f_ridge_earn"] - ic_ratio["f_vol"], 3),
           "ic_ratio_ridge_pit_minus_vol": MS.block_stats(ic_ratio["f_ridge_pit"] - ic_ratio["f_vol"], 3),
           "conventions": {"premium": "ATM straddle ~ IV_entry * sqrt(30/365) * sqrt(2/pi) per $ of spot",
                           "payoff": "|close(i+1+21)/close(i+1) - 1| (European-at-horizon, no early exercise, "
                                     "no dividends, no discounting, 21 sessions vs 30 calendar days)",
                           "cost": f"{STRADDLE_COST_OF_PREMIUM:.0%} of premium round trip (declared; no bid/ask on "
                                   "disk); sensitivity 5% / 20%",
                           "utility": f"log utility of equity with {STRADDLE_BUDGET:.0%} of equity in premium per leg",
                           "twin": "the SAME universe and month, selected by trailing vol instead of the ridge",
                           "regressor": "the diff's alpha is read after regressing on |market return| over the "
                                        "straddle window (a volatility shock), not the signed market"}}
    out["beyond_implied"] = beyond_implied(p)
    out["breadth_sweep"] = breadth_sweep(p, mkt_abs)
    for cost in (0.05, STRADDLE_COST_OF_PREMIUM, 0.20):
        legs = {}
        for c in ("f_vol", "f_ridge", "f_ridge_earn", "f_ridge_pit"):
            rows = []
            for d, g in p.groupby("date"):
                if len(g) < 2 * L.K + 10:
                    continue
                r = (g[c] / g["imp_sig"]).to_numpy()
                o = np.argsort(r, kind="mergesort")
                lo, hi = g.iloc[o[:L.K]], g.iloc[o[-L.K:]]
                long_r = float(hi["payoff_ret"].mean()) - cost
                short_r = -float(lo["payoff_ret"].mean()) - cost
                rows.append({"date": d, "long": long_r, "short": short_r, "ls": 0.5 * (long_r + short_r)})
            legs[c] = pd.DataFrame(rows).set_index("date")
        res = {}
        for c, df in legs.items():
            res[c] = {leg: {"mean": float(df[leg].mean()), "stats": MS.block_stats(df[leg], 3),
                            "by_hold_year": MS.by_hold_year(df[leg]), "loo": MS.loo_worst(df[leg]),
                            "carried_by": MS.carried_by(df[leg])} for leg in ("long", "short", "ls")}
        eq = {c: STRADDLE_BUDGET * df["ls"] for c, df in legs.items()}
        mabs = mkt_abs.reindex(eq["f_vol"].index)
        res["ridge_earn_minus_vol_equity"] = MS.diff_report(eq["f_ridge_earn"], eq["f_vol"], mabs)
        res["ridge_pit_minus_vol_equity"] = MS.diff_report(eq["f_ridge_pit"], eq["f_vol"], mabs)
        res["ridge_pit_minus_ridge_px_equity"] = MS.diff_report(eq["f_ridge_pit"], eq["f_ridge"], mabs)
        res["ridge_px_minus_vol_equity"] = MS.diff_report(eq["f_ridge"], eq["f_vol"], mabs)
        res["ridge_pit_ls_equity"] = {"metrics": MS.book_metrics(eq["f_ridge_pit"]),
                                      "log_utility_vs_cash": MS.report_from_diffs(
                                          np.log1p(eq["f_ridge_pit"]), eq["f_ridge_pit"], mabs)}
        res["ridge_earn_ls_equity"] = {"metrics": MS.book_metrics(eq["f_ridge_earn"]),
                                       "log_utility_vs_cash": MS.report_from_diffs(
                                           np.log1p(eq["f_ridge_earn"]), eq["f_ridge_earn"], None)}
        res["vol_ls_equity"] = {"metrics": MS.book_metrics(eq["f_vol"]),
                                "log_utility_vs_cash": MS.report_from_diffs(np.log1p(eq["f_vol"]), eq["f_vol"], None)}
        out[f"cost_{int(cost*100)}pct"] = res
    return out
