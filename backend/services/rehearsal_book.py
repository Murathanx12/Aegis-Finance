"""The Bloomberg dress-rehearsal book and Murat's core-satellite, as testable logic.

    python -m scripts.bloomberg_rehearsal_book --freeze     # the caller

WHAT THIS IS (review 2026-09-27 §9, accepted by Fable as the dress rehearsal)
=============================================================================
The one skill this programme has measured is MAGNITUDE: the sigma-63 vol
prior beats the LLM at forecasting the SIZE of a move; direction is dead.
The Bloomberg Global Trading Challenge (2026-10-12 .. 11-13) is a rank
tournament on relative P&L vs WLS, so the declared bet is idiosyncratic
variance placed where the size of the move can be forecast -- small/mid names
with a Q3 print inside the window -- tilted by the only positive directional
estimate we have (fundamentals, +39 bps/month at k = 20, a tilt, not an edge).

Book A is frozen for the 2026-09-28 open as a $1M PAPER rehearsal under the
contest's rules so that on 2026-10-26 it has 21 sessions of evidence, two weeks
before the contest opens. The evidence on that date is NOT the return (a
21-session return is noise at ~12% sigma); it is the three checks in
`CHECKS_2026_10_26`, printed verbatim on the freeze record.

Book B is Murat's own money as a book: 80% SPY + a 20% fundamentals sleeve.

THE FUNDAMENTALS SCORE, SAID PLAINLY
====================================
The +39 bps/month was a walk-forward LightGBM over 25 JKP features on a panel
that ends 2024-12 (`xs_ranker/fundamental_amplitude_2026-09-22.json`). That
model is not fitted live. What IS live is `fundamental_features`: SEC facts
joined on `filed + 2d`. `fundamentals_composite` is the within-universe
percentile-rank average of five of those ratios, signs from the literature
(gross profitability +, operating ROE +, ROE +, asset growth -, leverage -),
a name needing at least `FUND_MIN_LEGS` of them. It is a PROXY for the measured
model and every receipt says so.

Nothing here places an order. PRODUCT_EXPERIMENT; nothing here is a claim.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Optional

import numpy as np
import pandas as pd

# ─────────────────────────────── constants ───────────────────────────────────

#: the rehearsal's grading window: 21 sessions from the 09-28 open = 10-26.
WINDOW_SESSIONS = 21
#: EDGAR 8-K item 2.02 cadence: the next print is estimated at last + this.
EARNINGS_CADENCE_DAYS = 91
#: an 8-K file whose last filing is older than this at the decision is stale.
EIGHTK_FILE_MAX_AGE_DAYS = 30
#: a last 2.02 older than this is not a quarterly cadence we can extrapolate.
LAST_202_MAX_AGE_DAYS = 150
#: same-quarter-last-year cross-check: last year's 2.02 nearest (estimate - 364d)
#: within this tolerance, rolled forward 364d. When it exists it must ALSO land in
#: the window: on 2026-09-27 the cadence alone put CNXC at 09-28 while its same
#: quarter last year printed 09-24 (inside the 8-K file's 09-03..09-27 gap), and
#: NVCR at 10-22 against 10-29 last year.
YOY_TOLERANCE_DAYS = 21

K = 10
WEIGHT = 0.10
MAX_SEMIS = 2
#: small/mid by market cap (latest SEC `shares` x last close): $300M .. $10B.
MCAP_BAND = (3e8, 1e10)
SHARES_MAX_AGE_DAYS = 200
SIGMA_WINDOW = 63            # forecast_reputation.VOL_PRIOR_WINDOW
SIGMA_MIN_OBS = 42           # forecast_reputation.VOL_PRIOR_MIN_OBS
BETA_WINDOW = 126
CORR_WINDOW = 63
PAIR_RHO_MAX = 0.80          # night_backtest_factory.GATE_CLUSTER_RHO
SMH_RHO_SEMI_PROXY = 0.60    # an unclassified name this correlated with SMH counts as semis
SEMIS_GIND = "453010"        # GICS: Semiconductors & Semiconductor Equipment
FUND_LEGS: tuple[tuple[str, float], ...] = (
    ("gp_at", 1.0), ("ope_be", 1.0), ("ni_be", 1.0), ("at_gr1", -1.0), ("debt_at", -1.0))
FUND_MIN_LEGS = 3
#: asset growth outside this band is read as a data defect, not a fact (on
#: 2026-09-27 BZ and FUTU -- foreign filers -- read -77% and -70%, a currency or
#: filing-sequence mix), and the leg is NaN for that name.
AT_GR1_PLAUSIBLE = (-0.5, 2.0)
FUND_MAX_AGE_DAYS = 460      # fundamental_features' staleness cut

STOP_Z = -2.0
CHECK_DATE = "2026-10-26"
MOVE_RANK_MIN = 0.30
EXPOSURE_TOL = 0.30

CORE_WEIGHT = 0.80
SLEEVE_K = 10
PERSONAL_HORIZON = 126

#: the three 10-26 checks, verbatim (the task's words), on the freeze record.
CHECKS_2026_10_26 = (
    "move-size rank correlation >= 0.3",
    "realised factor exposure within +/-0.3 of declared",
    "fills vs plan",
)
CHECKS_DETAIL = (
    "1. Magnitude calibration: Spearman(sigma63-predicted |21-session move|, realised |move|) "
    "over the book's and its rank-11-20 twin's names is >= 0.3.",
    "2. Declared = realised exposure: realised betas to SPY, IWM-SPY and SMH-SPY over the 21 "
    "sessions are each within +/-0.3 of the declared values.",
    "3. Implementation: holdings and fills match the plan (names, weights at entry, entry "
    "at the 2026-09-28 open).",
)
LICENCE_SENTENCE = "PRODUCT_EXPERIMENT; nothing here is a claim."


# ─────────────────────────────── calendar ────────────────────────────────────

def sessions_after(decision: Any, n: int) -> list[pd.Timestamp]:
    """The first `n` business days strictly after `decision` (US holidays are
    counted as sessions; there is none between 09-28 and 10-26)."""
    d = pd.Timestamp(decision).normalize()
    return list(pd.bdate_range(d + pd.Timedelta(days=1), periods=n))


# ─────────────────────────────── earnings ────────────────────────────────────

def earnings_estimates(eightk: pd.DataFrame, tickers: Iterable[str], decision: Any, *,
                       window_sessions: int = WINDOW_SESSIONS) -> dict[str, dict]:
    """ticker -> the next-print estimate and whether it lands in the window.

    Source: EDGAR 8-K item 2.02 filings (`ticker`, `filing_date`,
    `items_joined`) filed ON OR BEFORE the decision -- the freeze gate's own
    earnings source. estimate = last 2.02 + EARNINGS_CADENCE_DAYS.

    status IN_WINDOW (first session <= estimate <= the window's last session,
    and the same-quarter-last-year cross-check, when it exists, lands there
    too), OUTSIDE_WINDOW, or EARNINGS_UNKNOWN, which never qualifies: no 2.02
    history; the 8-K file ends more than EIGHTK_FILE_MAX_AGE_DAYS before the
    decision; the last 2.02 is older than LAST_202_MAX_AGE_DAYS; or the
    estimate or the cross-check falls before the window (a print that may
    already sit in the file's gap).
    """
    dec = pd.Timestamp(decision).normalize()
    sess = sessions_after(dec, window_sessions)
    w0, w1 = sess[0], sess[-1]
    tickers = [str(t).upper() for t in tickers]
    ek = eightk[["ticker", "filing_date", "items_joined"]].copy()
    ek["filing_date"] = pd.to_datetime(ek["filing_date"], errors="coerce")
    ek = ek[ek["filing_date"].notna() & (ek["filing_date"] <= dec)]
    file_end = ek["filing_date"].max() if len(ek) else None
    base = {"source": "EDGAR 8-K item 2.02 (edgar_8k/eightk_items.parquet)",
            "rule": f"last 2.02 + {EARNINGS_CADENCE_DAYS}d",
            "window": [str(w0.date()), str(w1.date())],
            "file_ends": str(file_end.date()) if file_end is not None else None}
    if file_end is None or (dec - file_end).days > EIGHTK_FILE_MAX_AGE_DAYS:
        return {t: {**base, "status": "EARNINGS_UNKNOWN",
                    "why": f"8-K file ends {base['file_ends']}"} for t in tickers}
    ek["t"] = ek["ticker"].astype(str).str.upper()
    ek = ek[ek["t"].isin(set(tickers))
            & ek["items_joined"].fillna("").astype(str).str.contains("2.02", regex=False)]
    hist = {t: g.sort_values() for t, g in ek.groupby("t")["filing_date"]}
    out = {}
    for t in tickers:
        h = hist.get(t)
        if h is None or not len(h):
            out[t] = {**base, "status": "EARNINGS_UNKNOWN", "why": "no 8-K 2.02 history"}
            continue
        last = pd.Timestamp(h.iloc[-1])
        est = last + pd.Timedelta(days=EARNINGS_CADENCE_DAYS)
        yoy_target = est - pd.Timedelta(days=364)
        near = h[(h - yoy_target).abs() <= pd.Timedelta(days=YOY_TOLERANCE_DAYS)]
        yoy = (pd.Timestamp(near.iloc[(near - yoy_target).abs().argmin()]) + pd.Timedelta(days=364)
               if len(near) else None)
        row = {**base, "last_202": str(last.date()), "estimate": str(est.date()),
               "yoy_cross_check": str(yoy.date()) if yoy is not None else None,
               "n_202_filings": int(len(h))}
        if (dec - last).days > LAST_202_MAX_AGE_DAYS:
            row.update(status="EARNINGS_UNKNOWN", why=f"last 2.02 is {(dec - last).days}d old")
        elif est < w0 or (yoy is not None and yoy < w0):
            row.update(status="EARNINGS_UNKNOWN",
                       why=(f"estimate {est.date()} / last-year cross-check "
                            f"{yoy.date() if yoy is not None else None} before the window "
                            f"{w0.date()}: it may have printed in the 8-K file's gap"))
        elif est <= w1 and (yoy is None or yoy <= w1):
            row.update(status="IN_WINDOW",
                       session=int(sum(1 for s in sess if s <= est)),
                       qualified_on="cadence and last-year cross-check" if yoy is not None
                       else "cadence only (no same-quarter 2.02 last year)")
        else:
            row.update(status="OUTSIDE_WINDOW",
                       why=("cadence estimate after the window" if est > w1
                            else f"last-year cross-check {yoy.date()} after the window"))
        out[t] = row
    return out


# ─────────────────────────────── prices ──────────────────────────────────────

def wide_closes(bars: pd.DataFrame, asof: Any, symbols: Optional[Iterable[str]] = None,
                n: int = BETA_WINDOW + 5) -> pd.DataFrame:
    b = bars[pd.to_datetime(bars["date"]) <= pd.Timestamp(asof)]
    if symbols is not None:
        b = b[b["symbol"].isin(set(symbols))]
    w = b.pivot_table(index="date", columns="symbol", values="close", aggfunc="last").sort_index()
    return w.iloc[-n:]


def sigma63(bars: pd.DataFrame, asof: Any, *, window: int = SIGMA_WINDOW,
            min_obs: int = SIGMA_MIN_OBS) -> pd.Series:
    """Daily log-return sigma over the `window` sessions up to `asof` -- the
    forecast_reputation vol prior, as of the freeze (the freeze happens after
    the last close, so the last bar is known)."""
    w = wide_closes(bars, asof, n=window + 1)
    lr = np.log(w.where(w > 0)).diff().iloc[1:]
    s = lr.std(ddof=1)
    return s[lr.notna().sum() >= min_obs].dropna()


def predicted_abs_move(sigma_daily: float, sessions: int = WINDOW_SESSIONS) -> float:
    """E|r| over `sessions` for a zero-mean normal: sigma sqrt(h) sqrt(2/pi)."""
    return float(sigma_daily) * math.sqrt(sessions) * math.sqrt(2.0 / math.pi)


def universe(bars: pd.DataFrame, asof: Any, *, exclude: Iterable[str] = ()) -> pd.DataFrame:
    """xs_ranker's eligibility on the freeze date: last bar within 5 days,
    MIN_PRICE <= close <= MAX_PRICE, median 63-session dollar volume >=
    MIN_MEDIAN_DOLLAR_VOL, >= MIN_HISTORY_SESSIONS bars, not an ETF/index."""
    from backend.services import llm_portfolio as LP
    from backend.services import xs_ranker as XR
    a = pd.Timestamp(asof)
    b = bars[pd.to_datetime(bars["date"]) <= a].sort_values(["symbol", "date"])
    g = b.groupby("symbol")
    last = g.tail(1).set_index("symbol")
    n = g.size()
    t63 = g.tail(63)
    mdv = (t63["close"] * t63["volume"]).groupby(t63["symbol"]).median()
    df = pd.DataFrame({"close": last["close"], "last_date": last["date"], "n_bars": n,
                       "mdv63": mdv})
    ex = {str(x).upper() for x in exclude}
    ok = ((df["last_date"] >= a - pd.Timedelta(days=5))
          & df["close"].between(XR.MIN_PRICE, XR.MAX_PRICE)
          & (df["mdv63"] >= XR.MIN_MEDIAN_DOLLAR_VOL)
          & (df["n_bars"] >= XR.MIN_HISTORY_SESSIONS))
    df = df[ok]
    keep = [s for s in df.index if s not in XR.INDEX_PROXIES and not LP.is_etf(s) and s not in ex]
    df = df.loc[keep].copy()
    df["band"] = [XR.liquidity_band(v) for v in df["mdv63"]]
    return df


# ─────────────────────────────── fundamentals ────────────────────────────────

def latest_shares(facts: pd.DataFrame, asof: Any, *, max_age_days: int = SHARES_MAX_AGE_DAYS) -> pd.Series:
    """ticker -> the latest SEC `shares` filed + 2d on or before `asof`."""
    a = pd.Timestamp(asof)
    f = facts[facts["fact"] == "shares"].copy()
    f["filed"] = pd.to_datetime(f["filed"])
    f = f[(f["filed"] + pd.Timedelta(days=2) <= a) & (f["filed"] >= a - pd.Timedelta(days=max_age_days))]
    f = f.sort_values(["ticker", "filed", "end"]).groupby("ticker").tail(1)
    s = pd.to_numeric(f.set_index(f["ticker"].astype(str).str.upper())["val"], errors="coerce")
    return s[s > 0]


def fundamentals_composite(facts: pd.DataFrame, asof: Any, symbols: Iterable[str]) -> pd.DataFrame:
    """Per symbol: the five legs as of `asof` (filed + 2d, <= FUND_MAX_AGE_DAYS
    old), their within-`symbols` percentile ranks and the composite (mean of
    the available leg ranks; NaN below FUND_MIN_LEGS)."""
    from backend.services import fundamental_features as FF
    a = pd.Timestamp(asof)
    syms = sorted({str(s).upper() for s in symbols})
    h = facts[facts["ticker"].astype(str).str.upper().isin(syms)].copy()
    h["ticker"] = h["ticker"].astype(str).str.upper()
    if not len(h):
        return pd.DataFrame(index=pd.Index([], name="symbol"))
    h["filed"] = pd.to_datetime(h["filed"])
    h = h[h["filed"] + pd.Timedelta(days=FF.LAG_DAYS) <= a]
    r = FF.ratios(FF.wide_by_filing(h))
    r = r.sort_values(["ticker", "filed"]).groupby("ticker").tail(1).set_index("ticker")
    r = r[(a - r["filed"]).dt.days <= FUND_MAX_AGE_DAYS]
    # a return on NEGATIVE equity is a loss-maker's ratio read upside down (STRO:
    # ni_be +2.2 on a deficit): no ROE leg without positive book equity
    neg = r["book_equity_log"].isna()
    r.loc[neg, ["ope_be", "ni_be"]] = np.nan
    lo, hi = AT_GR1_PLAUSIBLE
    r.loc[~r["at_gr1"].between(lo, hi), "at_gr1"] = np.nan
    out = pd.DataFrame(index=pd.Index(syms, name="symbol"))
    ranks = []
    for leg, sign in FUND_LEGS:
        v = r[leg].reindex(out.index) if leg in r.columns else pd.Series(np.nan, index=out.index)
        v = v.replace([np.inf, -np.inf], np.nan)
        out[leg] = v
        rk = (sign * v).rank(pct=True)
        out[f"{leg}_rank"] = rk
        ranks.append(rk)
    R = pd.concat(ranks, axis=1)
    out["n_legs"] = R.notna().sum(axis=1)
    out["fund_score"] = R.mean(axis=1).where(out["n_legs"] >= FUND_MIN_LEGS)
    out["fund_filed"] = r["filed"].reindex(out.index).dt.strftime("%Y-%m-%d")
    return out


# ─────────────────────────────── sector ──────────────────────────────────────

def semis_flags(symbols: Iterable[str], *, gind_by_symbol: dict[str, str],
                smh_corr: Optional[pd.Series] = None) -> pd.DataFrame:
    """is_semi per symbol: GICS industry 453010 when Compustat classifies the
    name; otherwise (unclassified, e.g. a post-2024 listing) the 63-session
    correlation with SMH >= SMH_RHO_SEMI_PROXY. Source is printed per name."""
    rows = []
    for s in symbols:
        g = gind_by_symbol.get(s)
        if g:
            rows.append({"symbol": s, "is_semi": str(g) == SEMIS_GIND, "sector_source": f"gics_gind:{g}"})
        else:
            c = None if smh_corr is None else smh_corr.get(s)
            semi = bool(c is not None and np.isfinite(c) and c >= SMH_RHO_SEMI_PROXY)
            rows.append({"symbol": s, "is_semi": semi,
                         "sector_source": (f"unclassified; rho(SMH,63)={c:.2f}"
                                           if c is not None and np.isfinite(c) else "unclassified")})
    return pd.DataFrame(rows).set_index("symbol") if rows else pd.DataFrame(
        columns=["is_semi", "sector_source"])


# ─────────────────────────────── selection ───────────────────────────────────

def rank_candidates(cands: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Filter and order the Book A universe. `cands` (index symbol) carries
    sigma63, fund_score, mcap, earnings_status. Returns (qualified, sorted by
    predicted move desc; the per-filter counts)."""
    c = cands.copy()
    counts = {"universe": int(len(c))}
    c = c[c["sigma63"].notna()]
    counts["with_sigma63"] = int(len(c))
    c = c[c["mcap"].between(*MCAP_BAND)]
    counts[f"small_mid_mcap_{MCAP_BAND[0]:.0e}_{MCAP_BAND[1]:.0e}"] = int(len(c))
    med = float(c["fund_score"].median()) if c["fund_score"].notna().any() else float("nan")
    counts["fund_score_median"] = round(med, 4) if np.isfinite(med) else None
    c = c[c["fund_score"] >= med]
    counts["fund_score_ge_median"] = int(len(c))
    c = c[c["earnings_status"] == "IN_WINDOW"]
    counts["earnings_in_window"] = int(len(c))
    c = c.assign(pred_move=[predicted_abs_move(s) for s in c["sigma63"]])
    c = c.sort_values(["pred_move", "fund_score"], ascending=[False, False], kind="mergesort")
    return c, counts


def pick(ranked: pd.DataFrame, corr: pd.DataFrame, *, k: int = K, max_semis: int = MAX_SEMIS,
         exclude: Iterable[str] = ()) -> tuple[list[str], list[dict]]:
    """Greedy in rank order: skip a name that would be the (max_semis+1)-th
    semiconductor or that correlates above PAIR_RHO_MAX with a name already
    picked (so the freeze gate's cluster check cannot fail). Returns (picks,
    the skip log)."""
    picks: list[str] = []
    skipped: list[dict] = []
    semis = 0
    ex = set(exclude)
    for s, r in ranked.iterrows():
        if len(picks) >= k:
            break
        if s in ex:
            continue
        if bool(r.get("is_semi")) and semis >= max_semis:
            skipped.append({"symbol": s, "why": f"SEMIS_CAP ({max_semis})"})
            continue
        hi = [p for p in picks if s in corr.index and p in corr.columns
              and np.isfinite(corr.loc[s, p]) and corr.loc[s, p] > PAIR_RHO_MAX]
        if hi:
            skipped.append({"symbol": s, "why": f"RHO>{PAIR_RHO_MAX} with {hi}"})
            continue
        picks.append(s)
        semis += int(bool(r.get("is_semi")))
    return picks, skipped


# ─────────────────────────────── declared numbers ────────────────────────────

def _rets(closes: pd.DataFrame) -> pd.DataFrame:
    return closes.pct_change(fill_method=None).iloc[1:]


def book_stats(weights: dict[str, float], closes: pd.DataFrame, *,
               sigma: Optional[pd.Series] = None, sessions: int = WINDOW_SESSIONS,
               corr_window: int = CORR_WINDOW, beta_window: int = BETA_WINDOW) -> dict:
    """The declared risk numbers of a weight vector.

    * sigma_daily: sqrt(w' D R D w), D = the names' sigma63, R = their realised
      `corr_window`-session correlation (pairwise-complete); *_21 = x sqrt(21).
    * rel_sigma vs SPY: the same construction with SPY as a -1 leg.
    * betas: OLS of the basket's daily return (current weights, `beta_window`
      sessions) on SPY, IWM-SPY, SMH-SPY (and MTUM-SPY when present), plus the
      univariate betas to SPY, IWM and SMH. `closes` must carry SPY, IWM, SMH
      (MTUM optional) beside the names.
    """
    names = [t for t in weights if weights[t] > 0 and t in closes.columns]
    w = np.array([weights[t] for t in names], dtype=float)
    R = _rets(closes)
    if sigma is None:
        sigma = np.log(closes).diff().iloc[-corr_window:].std(ddof=1)
    rc = R.iloc[-corr_window:]
    C = rc[names].corr(min_periods=40).fillna(0.0).to_numpy()
    np.fill_diagonal(C, 1.0)
    D = np.array([float(sigma.get(t, np.nan)) for t in names])
    cov = np.outer(D, D) * C
    s_d = float(np.sqrt(max(w @ cov @ w, 0.0)))
    iu = np.triu_indices(len(names), 1)
    avg_rho = float(np.nanmean(C[iu])) if len(names) > 1 else float("nan")
    out: dict = {"n_names": len(names), "gross": float(w.sum()),
                 "sigma_daily": s_d, "sigma_21": s_d * math.sqrt(sessions),
                 "avg_pairwise_rho_63": avg_rho,
                 "construction": (f"sqrt(w'DRD): D = sigma63 (daily log), R = realised "
                                  f"{corr_window}-session daily-return correlation")}
    if "SPY" in closes.columns:
        cols = names + ["SPY"]
        C2 = rc[cols].corr(min_periods=40).fillna(0.0).to_numpy()
        np.fill_diagonal(C2, 1.0)
        spy_sd = float(np.log(closes["SPY"]).diff().iloc[-corr_window:].std(ddof=1))
        D2 = np.append(D, spy_sd)
        w2 = np.append(w, -1.0)
        rel = float(np.sqrt(max(w2 @ (np.outer(D2, D2) * C2) @ w2, 0.0)))
        out.update(rel_sigma_daily_vs_spy=rel, rel_sigma_21_vs_spy=rel * math.sqrt(sessions),
                   spy_sigma_daily=spy_sd)
    rb = R.iloc[-beta_window:]
    basket = (rb[names].fillna(0.0) * w).sum(axis=1) / (w.sum() or 1.0)
    fac = {}
    if {"SPY", "IWM", "SMH"} <= set(rb.columns):
        X = pd.DataFrame({"SPY": rb["SPY"], "IWM-SPY": rb["IWM"] - rb["SPY"],
                          "SMH-SPY": rb["SMH"] - rb["SPY"]})
        if "MTUM" in rb.columns and rb["MTUM"].notna().sum() > 40:
            X["MTUM-SPY"] = rb["MTUM"] - rb["SPY"]
        d = pd.concat([basket.rename("y"), X], axis=1).dropna()
        A = np.column_stack([np.ones(len(d)), d[X.columns].to_numpy()])
        coef, *_ = np.linalg.lstsq(A, d["y"].to_numpy(), rcond=None)
        resid = d["y"].to_numpy() - A @ coef
        dof = max(len(d) - A.shape[1], 1)
        se = np.sqrt(np.diag(np.linalg.pinv(A.T @ A)) * float(resid @ resid) / dof)
        fac = {"window_sessions": int(len(d)),
               "multi": {c: {"beta": float(b), "se": float(e)}
                         for c, b, e in zip(["alpha_daily"] + list(X.columns), coef, se)}}
        uni = {}
        for e in ("SPY", "IWM", "SMH"):
            dd = pd.concat([basket.rename("y"), rb[e].rename("x")], axis=1).dropna()
            vx = float(dd["x"].var(ddof=1))
            uni[e] = float(dd["y"].cov(dd["x"]) / vx) if vx > 0 else None
        fac["univariate"] = uni
    out["factor_exposure"] = fac
    return out


def stop_rule_book(rel_sigma_daily: float, *, z: float = STOP_Z) -> dict:
    """The stop in sigma units: z(t) = cumulative relative P&L / (rel sigma_daily
    sqrt(t)); acted on only if z < -2. The per-session threshold is printed so a
    reader can see what -2 sigma means in percent, but the RULE is the z."""
    tbl = {str(t): round(z * rel_sigma_daily * math.sqrt(t), 4) for t in (1, 5, 10, 21)}
    return {"rule": (f"z(t) = cumulative relative P&L vs the benchmark at session t / "
                     f"(rel_sigma_daily x sqrt(t)); ACT only if z < {z:g} (2 sigma, not a percent)"),
            "rel_sigma_daily": rel_sigma_daily, "z": z,
            "threshold_as_return_by_session": tbl,
            "no_per_name_stop": ("no per-name stop inside the window: the print is the bet, and "
                                 "a -2% stop is ~0.5 daily sigma on these names (review §9)")}


def spearman(a: Iterable[float], b: Iterable[float]) -> Optional[float]:
    """Spearman rank correlation, NaN-pairs dropped; None below 3 pairs."""
    x = pd.Series(list(a), dtype=float)
    y = pd.Series(list(b), dtype=float)
    ok = x.notna() & y.notna()
    if ok.sum() < 3:
        return None
    return float(x[ok].rank().corr(y[ok].rank()))


# ─────────────────────────────── Book B helpers ──────────────────────────────

def sleeve_top(fund: pd.DataFrame, eligible: Iterable[str], *, k: int = SLEEVE_K) -> list[str]:
    """Fundamentals top-k over the eligible universe (all sizes; no cap)."""
    f = fund.reindex(sorted(set(eligible)))
    f = f[f["fund_score"].notna()]
    f = f.sort_values(["fund_score", "n_legs"], ascending=[False, False], kind="mergesort")
    return list(f.index[:k])


def core_satellite_te(sleeve: list[str], closes: pd.DataFrame, *, satellite: float = 1 - CORE_WEIGHT,
                      window: int = 252) -> dict:
    """Tracking error of (core SPY + satellite x EW sleeve) vs SPY = satellite x
    sigma(sleeve - SPY), annualised, from `window` realised sessions, printed
    beside the sleeve's own sigma and its correlation with SPY."""
    R = _rets(closes).iloc[-window:]
    names = [s for s in sleeve if s in R.columns]
    sl = R[names].mean(axis=1, skipna=True)
    d = pd.concat([sl.rename("s"), R["SPY"].rename("m")], axis=1).dropna()
    s_s = float(d["s"].std(ddof=1)) * math.sqrt(252)
    s_m = float(d["m"].std(ddof=1)) * math.sqrt(252)
    rho = float(d["s"].corr(d["m"]))
    te_sleeve = float((d["s"] - d["m"]).std(ddof=1)) * math.sqrt(252)
    beta = float(d["s"].cov(d["m"]) / d["m"].var(ddof=1))
    port = satellite * d["s"] + (1 - satellite) * d["m"]
    return {"window_sessions": int(len(d)), "sleeve_sigma_ann": s_s, "spy_sigma_ann": s_m,
            "sleeve_corr_spy": rho, "sleeve_beta_spy": beta,
            "sleeve_minus_spy_sigma_ann": te_sleeve,
            "tracking_error_ann": satellite * te_sleeve,
            "book_sigma_ann": float(port.std(ddof=1)) * math.sqrt(252),
            "book_beta_spy": satellite * beta + (1 - satellite),
            "formula": "TE = satellite x sigma_ann(sleeve - SPY); sigma(sleeve-SPY)^2 = "
                       "s_s^2 + s_m^2 - 2 rho s_s s_m"}
