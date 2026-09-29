"""The library's momentum leads rebuilt on CRSP (2026-09-29): pure functions.

Licence: PRODUCT_EXPERIMENT diagnostics ($0, no LLM). The runner is
`scripts/momentum_on_crsp.py`; this module holds the parts a test can pin.

WHY. `mom_12_1_q` (12-1 momentum, top 20, held a quarter, one third on each
quarterly calendar) was the project's only surviving historical lead. On the
vendor panel it fell from +1.20%/mo over its matched twin (t 2.49) to +0.92%
(t 1.83) once 174,417 bars that were never trades were removed, and 17
CRSP-confirmed defects (spin-offs booked as price drops) are still in that
panel. The question is settled on a second source: CRSP daily total returns,
delisting returns included, survivorship-free (every permno of the PIT
universe files, dead or alive), for as long as CRSP on disk allows.

THE BRIDGE (the one design decision): the library's engine
(`night_backtest_factory.build_panel` -> `strategy_library.run_strategy` ->
`calendar_offsets.twin21`) reads a `load_wide` dict of (dates x symbols)
open/high/low/close/volume arrays. `wide_from_crsp` builds that dict from CRSP
so the SAME engine runs, unchanged:

* `close` is a TOTAL-RETURN index per permno (CRSP `ret`, dividends in),
  anchored at the permno's first |prc|. A missing `ret` on a priced row is
  filled from the `cfacpr`-adjusted price ratio (counted on the audit).
* `open` is CRSP `openprc` on the same index (openprc x close / |prc|); where
  CRSP has no open (none before 1992, ~3-13% of rows after) it is the previous
  session's index close, i.e. the period is close-to-close for that name. The
  receipt prints the share.
* `volume` is |prc| x vol / close, so `close x volume` is the TRUE dollar
  volume the engine's liquidity floor and cost bands read.
* `high` / `low` are the close (no rule here reads a 52-week feature).
* the DELISTING return is booked on the session after the last trade (CRSP
  `dlret`; a missing dlret with a 400-599 code takes the library's -30% fill);
  the engine is then run with `delist_return=0.0`, so the name's exit is the
  real delisting value. That session is never eligible.
* the market symbol (`SPY` in the engine) carries the Fama-French daily market
  total return (mktrf + rf), close-to-close. It is NOT SPY and every receipt
  says so; SPY does not exist before 1993 and is not a CRSP common stock.
* eligibility's price floor must read the ACTUAL price, not the index: the
  engine is run with the price band disabled and `apply_actual_price` puts it
  back on |prc| (xs_ranker MIN_PRICE..MAX_PRICE), leaving every other floor
  (dollar volume, history, vol_63/mom_63 defined) exactly as the engine
  computes it.
"""
from __future__ import annotations

import contextlib
import math
from typing import Iterable, Optional

import numpy as np
import pandas as pd

#: the engine's market symbol; on CRSP it carries the FF VW market total return
MARKET = "SPY"
#: the library's delisting fill, used only when CRSP has no dlret for a 400-599 code
MISSING_DLRET_FILL = -0.30
#: a delisting row is booked only if its date is within this many days of the last trade
DLRET_MAX_GAP_DAYS = 40
#: the factor verdict thresholds (the signal_structure vocabulary)
ALPHA_T = 2.0
BETA_T = 1.0


def permno_symbol(p) -> str:
    """Zero-padded permno: sorts before `SPY`, so the engine's searchsorted works."""
    return f"{int(p):06d}"


# ── the wide dict ────────────────────────────────────────────────────────────

def wide_from_crsp(daily: pd.DataFrame, delist: Optional[pd.DataFrame],
                   market_ret: pd.Series, *,
                   missing_dlret_fill: float = MISSING_DLRET_FILL) -> dict:
    """CRSP daily rows -> the `load_wide` contract (+ `price`, `dl_mask`, `audit`).

    `daily`: permno, date, prc, ret, vol, openprc[, cfacpr].
    `delist`: permno, dlstdt, dlstcd, dlret (None = no delisting table).
    `market_ret`: daily market total return indexed by date; its dates are the
    calendar (a CRSP row on a date the market series lacks is dropped).
    """
    mr = pd.Series(market_ret, dtype=float).dropna()
    mr.index = pd.DatetimeIndex(mr.index)
    d = daily.copy()
    d["date"] = pd.to_datetime(d["date"])
    cal = pd.DatetimeIndex(np.sort(mr.index.intersection(pd.DatetimeIndex(d["date"].unique()))))
    if len(cal) < 2:
        raise ValueError("fewer than two sessions shared by CRSP and the market series")
    d = d[d["date"].isin(cal)]
    d["P"] = pd.to_numeric(d["prc"], errors="coerce").abs()
    d.loc[~(d["P"] > 0), "P"] = np.nan
    n_in = int(len(d))
    d = d[d["P"].notna()].sort_values(["permno", "date"], kind="mergesort").reset_index(drop=True)
    r = pd.to_numeric(d["ret"], errors="coerce").to_numpy(dtype=float)
    first = np.r_[True, d["permno"].to_numpy()[1:] != d["permno"].to_numpy()[:-1]]
    # a missing ret on a priced row: the split-adjusted price ratio to the previous row
    miss = ~np.isfinite(r) & ~first
    n_ratio = 0
    if miss.any():
        cf = (pd.to_numeric(d["cfacpr"], errors="coerce").to_numpy(dtype=float)
              if "cfacpr" in d.columns else np.ones(len(d)))
        cf = np.where(np.isfinite(cf) & (cf > 0), cf, 1.0)
        adj = d["P"].to_numpy(dtype=float) / cf
        prev = np.r_[np.nan, adj[:-1]]
        rr = adj / prev - 1.0
        fill = miss & np.isfinite(rr)
        r[fill] = rr[fill]
        n_ratio = int(fill.sum())
    n_zero = int((~np.isfinite(r) & ~first).sum())
    r[first | ~np.isfinite(r)] = 0.0
    r = np.clip(r, -0.9999, None)
    grp = np.cumsum(first) - 1
    lr = np.log1p(r)
    csum = np.cumsum(lr)
    base = csum[np.flatnonzero(first)][grp] - lr[np.flatnonzero(first)][grp]
    anchor = d["P"].to_numpy(dtype=float)[np.flatnonzero(first)][grp]
    Cl = anchor * np.exp(csum - base)
    op = pd.to_numeric(d["openprc"], errors="coerce").to_numpy(dtype=float) \
        if "openprc" in d.columns else np.full(len(d), np.nan)
    has_open = np.isfinite(op) & (op > 0)
    Ol = np.where(has_open, op * Cl / d["P"].to_numpy(dtype=float), np.nan)
    prevC = np.r_[np.nan, Cl[:-1]]
    prevC[first] = np.nan
    Ol = np.where(has_open, Ol, prevC)          # no CRSP open: yesterday's close
    Ol[first & ~has_open] = Cl[first & ~has_open]
    vol = pd.to_numeric(d["vol"], errors="coerce").to_numpy(dtype=float)
    vol = np.where(np.isfinite(vol) & (vol > 0), vol, 0.0)
    Vl = d["P"].to_numpy(dtype=float) * vol / Cl

    perms = np.sort(d["permno"].unique())
    symbols = np.array([permno_symbol(p) for p in perms] + [MARKET])
    T, N = len(cal), len(symbols)
    di = np.searchsorted(cal, d["date"].to_numpy())
    si = np.searchsorted(perms, d["permno"].to_numpy())
    C = np.full((T, N), np.nan)
    O = np.full((T, N), np.nan)
    V = np.zeros((T, N))
    P = np.full((T, N), np.nan)
    C[di, si] = Cl
    O[di, si] = Ol
    V[di, si] = Vl
    P[di, si] = d["P"].to_numpy(dtype=float)
    del d
    dl_mask = np.zeros((T, N), dtype=bool)
    n_dl = n_fill = n_dl_skipped = 0
    if delist is not None and len(delist):
        fin = np.isfinite(C[:, :-1])
        last = np.where(fin.any(axis=0), T - 1 - np.argmax(fin[::-1], axis=0), -1)
        dl = delist[delist["permno"].isin(perms)]
        for row in dl.itertuples(index=False):
            code = getattr(row, "dlstcd")
            code = float(code) if code is not None and np.isfinite(code) else np.nan
            if np.isfinite(code) and code < 200:
                continue                                  # 100s: still active
            j = int(np.searchsorted(perms, row.permno))
            lt = int(last[j])
            if lt < 0 or lt >= T - 1:
                continue                                  # traded to the calendar's end
            dt = pd.Timestamp(row.dlstdt) if pd.notna(row.dlstdt) else None
            if dt is None or dt < cal[lt] or dt > cal[lt] + pd.Timedelta(days=DLRET_MAX_GAP_DAYS):
                n_dl_skipped += 1
                continue
            rv = row.dlret
            rv = float(rv) if rv is not None and np.isfinite(rv) else np.nan
            if not np.isfinite(rv):
                if np.isfinite(code) and 400 <= code < 600:
                    rv, n_fill = float(missing_dlret_fill), n_fill + 1
                else:
                    n_dl_skipped += 1
                    continue
            C[lt + 1, j] = C[lt, j] * (1.0 + rv)
            O[lt + 1, j] = C[lt + 1, j]
            V[lt + 1, j] = 0.0
            dl_mask[lt + 1, j] = True
            n_dl += 1
    m = mr.reindex(cal).fillna(0.0).to_numpy()
    mc = np.cumprod(1.0 + m)
    C[:, -1] = mc
    O[:, -1] = np.r_[mc[0], mc[:-1]]
    V[:, -1] = 1e12
    audit = {"rows_in": n_in, "rows_priced": int(np.isfinite(P).sum()),
             "symbols": int(len(perms)), "sessions": int(T),
             "first": str(cal[0].date()), "last": str(cal[-1].date()),
             "ret_filled_from_price_ratio": n_ratio, "ret_missing_set_zero": n_zero,
             "open_share": float(has_open.mean()) if len(has_open) else None,
             "delisting_returns_booked": n_dl, "delisting_missing_dlret_filled": n_fill,
             "delisting_rows_not_booked": n_dl_skipped}
    return {"dates": cal, "symbols": symbols, "open": O, "high": C, "low": C, "close": C,
            "volume": V, "price": P, "dl_mask": dl_mask, "n_bar_rows": int(np.isfinite(P).sum()),
            "audit": audit}


@contextlib.contextmanager
def price_band_disabled(xr_module):
    """Run the engine with xs_ranker's price band open (the index is not a price)."""
    lo, hi = xr_module.MIN_PRICE, xr_module.MAX_PRICE
    xr_module.MIN_PRICE, xr_module.MAX_PRICE = 0.0, float("inf")
    try:
        yield (lo, hi)
    finally:
        xr_module.MIN_PRICE, xr_module.MAX_PRICE = lo, hi


def apply_actual_price(panel: pd.DataFrame, W: dict, *, min_price: float,
                       max_price: float) -> pd.DataFrame:
    """`close` := the actual |prc|; `eligible` &= min_price <= |prc| <= max_price and
    not a delisting-return session. Every other eligibility floor is the engine's."""
    di = np.searchsorted(W["dates"], pd.DatetimeIndex(panel["date"]).to_numpy())
    si = np.searchsorted(W["symbols"], panel["symbol"].to_numpy())
    px = W["price"][di, si]
    dl = W["dl_mask"][di, si]
    out = panel.copy()
    out["close"] = px
    ok = np.isfinite(px) & (px >= min_price) & (px <= max_price) & ~dl
    out["eligible"] = out["eligible"].astype(bool).to_numpy() & ok
    return out


# ── analyst price-target dispersion (the `target_cv_180` analogue) ────────────

def target_cv(targets: pd.DataFrame, decision_dates: Iterable, *, window_days: int = 180,
              min_firms: int = 3) -> pd.DataFrame:
    """At each decision date d: each firm's LATEST target on a name in
    [d - window, d) (strictly before d), then std / mean across firms with at
    least `min_firms` -- `night_backtest_factory.attach_ratings`' definition.

    `targets`: permno, estimid, anndats, value (split-adjusted to a common basis).
    Returns date, symbol, target_cv_180."""
    t = targets[["permno", "estimid", "anndats", "value"]].dropna()
    t = t[t["value"] > 0].sort_values("anndats", kind="mergesort").reset_index(drop=True)
    tt = pd.DatetimeIndex(t["anndats"]).to_numpy()
    rows = []
    for d in pd.DatetimeIndex(decision_dates):
        lo = np.searchsorted(tt, np.datetime64(d - pd.Timedelta(days=window_days)), "left")
        hi = np.searchsorted(tt, np.datetime64(d), "left")
        w = t.iloc[lo:hi]
        if not len(w):
            continue
        last = w.drop_duplicates(["permno", "estimid"], keep="last")
        g = last.groupby("permno")["value"].agg(["std", "mean", "count"])
        g = g[g["count"] >= min_firms]
        if not len(g):
            continue
        cv = g["std"] / g["mean"]
        rows.append(pd.DataFrame({"date": d, "symbol": [permno_symbol(p) for p in g.index],
                                  "target_cv_180": cv.to_numpy(dtype=float)}))
    if not rows:
        return pd.DataFrame(columns=["date", "symbol", "target_cv_180"])
    return pd.concat(rows, ignore_index=True)


# ── the academic benchmark on the same panel ─────────────────────────────────

def decile_returns(panel: pd.DataFrame, *, score: str = "mom_252_21",
                   n_bins: int = 10) -> pd.DataFrame:
    """Monthly EQUAL-WEIGHT decile returns on each decision date's eligible names
    (gross, no costs: the academic convention), plus the eligible-universe mean.

    Returns one row per decision date: d1..d10, ew, n. The next period's
    `fwd_ret` is the engine's (entry the session after the decision)."""
    p = panel[panel["eligible"].astype(bool) & panel[score].notna() & panel["fwd_ret"].notna()]
    out = []
    for d, g in p.groupby("date", sort=True):
        if len(g) < n_bins * 5:
            continue
        rk = g[score].rank(method="first").to_numpy(dtype=np.int64)     # 1..n
        b = ((rk - 1) * n_bins) // len(g) + 1
        f = g["fwd_ret"].to_numpy(dtype=float)
        row = {"date": d, "n": int(len(g)), "ew": float(f.mean())}
        for k in range(1, n_bins + 1):
            row[f"d{k}"] = float(f[b == k].mean())
        out.append(row)
    return pd.DataFrame(out).set_index("date") if out else pd.DataFrame()


def jt_overlap(top_sets: dict, fwd: dict, dates: list, hold: int = 3) -> pd.Series:
    """Jegadeesh-Titman overlapping book: in month t, the mean of the last `hold`
    cohorts' equal-weight returns (a cohort's missing name earns 0 = cash)."""
    vals = {}
    for i, d in enumerate(dates):
        rs = []
        for j in range(hold):
            if i - j < 0:
                break
            coh = top_sets.get(dates[i - j]) or []
            if not coh:
                continue
            fm = fwd.get(d) or {}
            rs.append(float(np.mean([fm.get(s, 0.0) for s in coh])))
        if len(rs) == hold:
            vals[d] = float(np.mean(rs))
    return pd.Series(vals, dtype=float)


# ── statistics the brief asks for beside every number ────────────────────────

def share_of_total_by_date(x: pd.Series) -> dict:
    """Fraction of the summed series carried by its top 1 / 5 / 10% of months by
    |value|, and the months that make the top 1%."""
    v = pd.Series(x, dtype=float).dropna()
    tot = float(v.sum())
    if not len(v) or tot == 0:
        return {"total": tot, "n": int(len(v))}
    order = v.abs().sort_values(ascending=False, kind="mergesort").index
    out = {"total": tot, "n": int(len(v))}
    for frac in (0.01, 0.05, 0.10):
        n_top = max(1, int(len(v) * frac))
        out[f"top_{int(frac * 100)}pct_of_months"] = float(v[order[:n_top]].sum() / tot)
    n1 = max(1, int(len(v) * 0.01))
    out["top_1pct_months"] = [str(pd.Timestamp(i).date()) for i in order[:n1]]
    return out


def window_stats(diff: pd.Series, lo: Optional[str] = None, hi: Optional[str] = None,
                 *, block: int = 3, mde_z: float = 2.8) -> dict:
    """Mean monthly difference over [lo, hi] (keyed on the HOLD month = decision
    + 1 business day), its t on non-overlapping `block`-month blocks, SE and MDE
    in %/month. Blocks are counted from the window's first month."""
    s = pd.Series(diff, dtype=float).dropna()
    hold = pd.DatetimeIndex(s.index) + pd.offsets.BDay(1)
    mk = np.ones(len(s), dtype=bool)
    if lo:
        mk &= hold >= pd.Timestamp(lo)
    if hi:
        mk &= hold <= pd.Timestamp(hi)
    s = s[mk]
    n = int(len(s))
    out = {"window": [lo, hi], "n_months": n, "mean_monthly": float(s.mean()) if n else None,
           "n_blocks": 0, "t_blocks": None, "se_monthly": None, "mde_monthly": None}
    if n < block * 3:
        return out
    b = np.arange(n) // block
    sums = s.groupby(b).sum()
    lens = s.groupby(b).size()
    nb = int(len(sums))
    out["n_blocks"] = nb
    sd = float(sums.std(ddof=1))
    if nb > 2 and sd > 0:
        se_b = sd / math.sqrt(nb)
        out["t_blocks"] = float(sums.mean() / se_b)
        out["se_monthly"] = se_b / float(lens.mean())
        out["mde_monthly"] = mde_z * out["se_monthly"]
    return out


def factor_verdict(t: Optional[float], mde: Optional[float], observed: Optional[float]) -> str:
    """signal_structure.verdict's rule: ALPHA_DETECTED |t| >= 2; BETA_EXPLAINS
    |t| < 1 AND the MDE is below |observed|; else CANNOT_DISTINGUISH."""
    if t is None or not np.isfinite(t):
        return "CANNOT_DISTINGUISH"
    if abs(t) >= ALPHA_T:
        return "ALPHA_DETECTED"
    if (abs(t) < BETA_T and mde is not None and np.isfinite(mde) and observed is not None
            and np.isfinite(observed) and mde < abs(observed)):
        return "BETA_EXPLAINS"
    return "CANNOT_DISTINGUISH"


def twin_verdict(stats: dict) -> str:
    """The rule-vs-twin read on one window: FAILED_VARIANT when the mean is <= 0
    (the selection adds nothing over its characteristics), ALPHA_DETECTED at
    t >= 2, CANNOT_DISTINGUISH otherwise (a positive mean without power)."""
    m, t = stats.get("mean_monthly"), stats.get("t_blocks")
    if m is None:
        return "NOT_COMPUTED"
    if m <= 0:
        return "FAILED_VARIANT"
    if t is not None and t >= ALPHA_T:
        return "ALPHA_DETECTED"
    return "CANNOT_DISTINGUISH"


# ── vendor vs CRSP slot comparison ───────────────────────────────────────────

def ticker_map(stocknames: pd.DataFrame) -> pd.DataFrame:
    """CRSP names -> (ticker, shrcls, permno, namedt, nameenddt, shrcd, exchcd)."""
    s = stocknames[["permno", "ticker", "shrcls", "namedt", "nameenddt", "shrcd", "exchcd"]].copy()
    s = s[s["ticker"].notna()]
    s["namedt"] = pd.to_datetime(s["namedt"])
    s["nameenddt"] = pd.to_datetime(s["nameenddt"]).fillna(pd.Timestamp("2099-12-31"))
    s["ticker"] = s["ticker"].astype(str).str.upper().str.strip()
    s["shrcls"] = s["shrcls"].fillna("").astype(str).str.upper().str.strip()
    return s


def names_by_ticker(names: pd.DataFrame) -> dict:
    """ticker -> the CRSP name rows that ever used it, sorted by namedt."""
    out = {}
    for tk, g in names.sort_values("namedt", kind="mergesort").groupby("ticker", sort=False):
        out[tk] = g[["permno", "shrcls", "namedt", "nameenddt", "shrcd", "exchcd"]].to_dict("records")
    return out


def _split_symbol(symbol: str) -> tuple[str, str]:
    base = str(symbol).split("#", 1)[0].upper()
    for sep in (".", "-", "/"):
        if sep in base:
            b, c = base.split(sep, 1)
            return b, c
    return base, ""


def vendor_to_permno(symbol: str, date, names) -> dict:
    """A vendor symbol on a date -> the CRSP permno whose history it carries.

    Vendor bars are keyed by the ticker a listing holds at the END of its
    history (a renamed company's whole history sits under its NEW ticker:
    2017's FB is `META` in the vendor file). So: the CRSP name valid on the date
    if one exists (`how: on_date`); else the permno that took the ticker
    LATER, earliest first (`later_ticker`: the rename); else the last permno
    that used it before the date (`earlier_ticker`). `names` is a
    `ticker_map` frame or a `names_by_ticker` dict."""
    base, cls = _split_symbol(symbol)
    rows = (names.get(base) if isinstance(names, dict)
            else names[names["ticker"] == base].sort_values("namedt").to_dict("records"))
    if not rows:
        return {"permno": None, "why": "no CRSP name ever used the ticker"}
    if cls:
        rc = [r for r in rows if r["shrcls"] == cls]
        rows = rc or rows
    d = pd.Timestamp(date)
    on = [r for r in rows if r["namedt"] <= d <= r["nameenddt"]]
    how = "on_date"
    if on:
        r = on[0]
    else:
        later = [r for r in rows if r["namedt"] > d]
        if later:
            r, how = later[0], "later_ticker"
        else:
            r, how = rows[-1], "earlier_ticker"
    return {"permno": int(r["permno"]), "how": how,
            "shrcd": int(r["shrcd"]) if pd.notna(r["shrcd"]) else None,
            "exchcd": int(r["exchcd"]) if pd.notna(r["exchcd"]) else None}


def classify_vendor_slot(info: dict, crsp_row: Optional[dict], vendor_score: float, *,
                         score_tol: float = 0.10) -> str:
    """Why a vendor top-20 name is not in the CRSP top-20 on the same date."""
    if info.get("permno") is None:
        return "V1_no_crsp_permno"
    if info.get("shrcd") not in (10, 11) or info.get("exchcd") not in (1, 2, 3):
        return "V2_not_a_crsp_common_stock_on_nyse_amex_nasdaq"
    if crsp_row is None:
        return "V3_no_crsp_row_on_date"
    if not crsp_row.get("eligible"):
        return "V4_ineligible_on_crsp"
    cs = crsp_row.get("score")
    if cs is None or not np.isfinite(cs) or not np.isfinite(vendor_score):
        return "V5_score_missing_on_one_side"
    if abs(math.log1p(max(vendor_score, -0.99)) - math.log1p(max(cs, -0.99))) > score_tol:
        return "V6_score_differs_data"
    return "V7_rank_margin_same_score"


def classify_crsp_slot(vendor_row: Optional[dict], crsp_score: float, *,
                       score_tol: float = 0.10) -> str:
    """Why a CRSP top-20 permno is not in the vendor top-20 on the same date."""
    if vendor_row is None:
        return "C1_absent_from_vendor_panel"
    if not vendor_row.get("eligible"):
        return "C2_ineligible_on_vendor"
    vs = vendor_row.get("score")
    if vs is None or not np.isfinite(vs) or not np.isfinite(crsp_score):
        return "C3_score_missing_on_one_side"
    if abs(math.log1p(max(vs, -0.99)) - math.log1p(max(crsp_score, -0.99))) > score_tol:
        return "C4_score_differs_data"
    return "C5_rank_margin_same_score"


# ── the vendor universe rule, emulated on CRSP ───────────────────────────────

def end_screen_universe(panel: pd.DataFrame, *, asof, min_median_dollar_vol: float,
                        dead_before_days: int = 31) -> dict:
    """The vendor panel's membership rule, applied to CRSP.

    The vendor's living panel is a universe file dated 2026-09-01 floored at a
    median dollar volume measured THEN (`prices_deep/pull_receipt.json`); the
    delisted pull adds names that STOPPED trading. A name that was alive at the
    end but had shrunk below the floor is in neither. Emulation on a panel that
    ends at `asof`: keep every symbol whose last row is more than
    `dead_before_days` before `asof` (it died: the delisted pull), and every
    symbol alive on the last decision date with median_dollar_vol >= the floor
    there; drop the rest (alive but shrunk)."""
    last = panel.groupby("symbol")["date"].max()
    cut = pd.Timestamp(asof) - pd.Timedelta(days=dead_before_days)
    dead = set(last.index[last < cut])
    end = panel[panel["date"] == panel["date"].max()]
    liquid = set(end.loc[end["median_dollar_vol"] >= float(min_median_dollar_vol), "symbol"])
    alive = set(last.index[last >= cut])
    return {"keep": dead | (alive & liquid), "dead": dead, "alive_liquid": alive & liquid,
            "alive_shrunk": alive - liquid}
