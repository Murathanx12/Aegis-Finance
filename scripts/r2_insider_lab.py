"""R2 -- THE INSIDER LAB. What is actually in the 20-year Form 4 tape.

PRODUCT_EXPERIMENT. Explore dirty, promote clean. NO alpha claim is made here;
what is produced is a MEASUREMENT with its family correction, its beta printed
first, and its execution floor applied before the book is believed.

Substrate: the I1 lane's `insider_events_v1.parquet` (3,127,624 rows,
2006q1-2026q2) and its 82 parsed quarters. Every caveat in
`docs/BUILD_2026-09-07b_I1_SEC_INSIDER.md` is INHERITED, not rediscovered:

  * `observed_at_utc` is the FILING DATE end-of-day. There is no acceptance
    timestamp in SUBMISSION.tsv. Entry is the NEXT session's open, which at
    monthly frequency means: a filing observed inside month t may only be acted
    on from month t+1.
  * 78.1% of open-market buys are CMP-UNCLASSIFIABLE, and 2006-2008 is a
    WARM-UP window where the three-strictly-prior-years rule cannot classify at
    all. Every CMP number here is 2009+.
  * `plan_10b5_1 == UNKNOWN` on 8.36M rows (the checkbox begins 2023q2).
    UNKNOWN is missing data, never "no".
  * CRSP's entitled vintage ends 2024-12-31, so 2025-26 rows carry no permno
    (`REFUSED_OUTSIDE_CRSP_VINTAGE`). The book window is 2006-2024.

Stages (each writes its own receipt, each resumable):

    python -m scripts.r2_insider_lab base       # stage 1: base rates
    python -m scripts.r2_insider_lab spine      # stage 2: monthly spine
    python -m scripts.r2_insider_lab cmp        # stage 3: the CMP replication
    python -m scripts.r2_insider_lab cluster    # stage 4: clusters
    python -m scripts.r2_insider_lab matched    # stage 5: matched controls
    python -m scripts.r2_insider_lab traps      # stage 6: size/illiq/PEAD/floor
    python -m scripts.r2_insider_lab adjudicate # stage 7: family correction
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
INSIDER = ROOT / "backend" / "data" / "optimus" / "sec_insider"
EVENTS = INSIDER / "insider_events_v1.parquet"
PARSED = INSIDER / "parsed"
PANEL = ROOT / "backend" / "data" / "optimus" / "aegis_panel" / "aegis_panel_v2.parquet"
OUT = ROOT / "backend" / "data" / "optimus" / "insider_lab"
OUT.mkdir(parents=True, exist_ok=True)

#: The tape's own limits, declared once so no stage re-derives them.
CMP_FIRST_YEAR = 2009        # three strictly-prior years of purchase history
CRSP_LAST_YEAR = 2024        # entitled vintage ends 2024-12-31
BOOK_YEARS = (CMP_FIRST_YEAR, CRSP_LAST_YEAR)


def _write(name: str, obj: dict) -> Path:
    p = OUT / f"{name}.json"
    p.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")
    print(f"  -> {p.relative_to(ROOT)}")
    return p


def _q(s: pd.Series, qs=(0.01, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99)) -> dict:
    s = pd.Series(s).dropna()
    if s.empty:
        return {"n": 0}
    out = {"n": int(len(s)), "mean": float(s.mean()), "std": float(s.std())}
    for x in qs:
        out[f"p{int(x*100)}"] = float(s.quantile(x))
    return out


# =========================================================== STAGE 1: BASE RATES

def stage_base() -> dict:
    """Base rates BEFORE any signal. Counts, sizes, lags, concentration.

    A signal built without knowing the base rate is how a 20-year tape becomes a
    5-month artefact ([[feedback-the-learner-edge-was-six-rebound-months]]).
    """
    print("stage 1: base rates")
    ev = pd.read_parquet(EVENTS, columns=[
        "permno", "symbol", "event_type", "event_time_utc", "observed_at_utc",
        "insider_cik", "insider_is_officer", "insider_is_director",
        "insider_is_tenpercent", "insider_cmp_class", "insider_shares",
        "insider_price", "insider_dollar_value", "insider_plan_10b5_1",
        "insider_cluster_buyers", "year"])
    print(f"  events {len(ev):,}")

    ev["filing_date"] = pd.to_datetime(ev["observed_at_utc"]).dt.tz_convert(None).dt.normalize()
    ev["trans_date"] = pd.to_datetime(ev["event_time_utc"]).dt.tz_convert(None).dt.normalize()
    ev["lag_days"] = (ev["filing_date"] - ev["trans_date"]).dt.days
    ev["month"] = ev["filing_date"].values.astype("datetime64[M]")

    out: dict = {
        "stage": "base_rates",
        "source": str(EVENTS.relative_to(ROOT)),
        "rows": int(len(ev)),
        "window": [str(ev["filing_date"].min().date()), str(ev["filing_date"].max().date())],
        "families": ev["event_type"].value_counts().to_dict(),
    }

    # ---- per-year, per-family
    per_year = (ev.groupby(["year", "event_type"]).size()
                  .unstack(fill_value=0).sort_index())
    out["per_year_family"] = {int(y): {k: int(v) for k, v in r.items()}
                              for y, r in per_year.iterrows()}

    # ---- per-issuer concentration (buys, book window only)
    buys = ev[ev["event_type"].str.contains("buy")]
    bw = buys[(buys["year"] >= BOOK_YEARS[0]) & (buys["year"] <= BOOK_YEARS[1])]
    per_iss = bw.groupby(["year", "symbol"]).size()
    out["buys_per_issuer_year"] = _q(per_iss)
    out["buys_per_issuer_year"]["issuers_with_any_buy_median_per_year"] = float(
        bw.groupby("year")["symbol"].nunique().median())
    out["buy_rows_in_book_window"] = int(len(bw))

    # ---- how many DISTINCT issuer-months carry a buy (the real breadth)
    im = bw.groupby("month")["permno"].nunique()
    out["distinct_permnos_with_buy_per_month"] = _q(im)
    im_all = bw.groupby("month")["symbol"].nunique()
    out["distinct_symbols_with_buy_per_month"] = _q(im_all)

    # ---- size in dollars
    for fam, sub in bw.groupby("event_type"):
        out.setdefault("dollar_value_by_family", {})[fam] = _q(sub["insider_dollar_value"])
    sells = ev[(ev["event_type"] == "insider_open_market_sell")
               & (ev["year"] >= BOOK_YEARS[0]) & (ev["year"] <= BOOK_YEARS[1])]
    out.setdefault("dollar_value_by_family", {})["insider_open_market_sell"] = _q(
        sells["insider_dollar_value"])

    # ---- filing lag
    out["filing_lag_days_all"] = _q(ev["lag_days"])
    out["filing_lag_days_by_family"] = {
        f: _q(s["lag_days"]) for f, s in ev.groupby("event_type")}
    out["filing_lag_days_by_year"] = {
        int(y): _q(s["lag_days"], qs=(0.5, 0.9, 0.99)) for y, s in ev.groupby("year")}
    out["negative_lag_rows"] = int((ev["lag_days"] < 0).sum())

    # ---- who
    out["role_share_buys"] = {
        "officer": float(bw["insider_is_officer"].mean()),
        "director": float(bw["insider_is_director"].mean()),
        "tenpercent": float(bw["insider_is_tenpercent"].mean()),
    }
    out["cmp_class_counts_book_window"] = bw["insider_cmp_class"].value_counts(dropna=False).to_dict()
    out["plan_10b5_1_counts"] = ev["insider_plan_10b5_1"].value_counts(dropna=False).to_dict()
    out["cluster_buyers_dist"] = _q(bw["insider_cluster_buyers"])
    out["cluster_ge3_buy_rows_book_window"] = int((bw["insider_cluster_buyers"] >= 3).sum())

    # ---- permno link within the book window
    out["permno_link_rate_book_window"] = float(bw["permno"].notna().mean())

    _write("r2_base_rates", {k: v for k, v in out.items()})
    return out


# ------- percent-of-holdings needs the PARSED quarters (event table drops it)

def stage_base_holdings() -> dict:
    """Trade size as a share of the insider's own post-trade holding.

    `shares_owned_following` exists in the PARSED quarters and NOT in the event
    table, so this is read from `parsed/*.parquet` -- a declared second source,
    not a re-derivation.
    """
    print("stage 1b: percent-of-holdings from the parsed quarters")
    frames = []
    for p in sorted(PARSED.glob("*.parquet")):
        yr = int(p.stem[:4])
        if yr < BOOK_YEARS[0] or yr > BOOK_YEARS[1]:
            continue
        df = pd.read_parquet(p, columns=[
            "quarter", "is_open_market_purchase", "shares", "shares_owned_following",
            "dollar_value", "trans_code", "table", "acquired_disposed"])
        frames.append(df[df["is_open_market_purchase"]])
    buys = pd.concat(frames, ignore_index=True)
    sh = pd.to_numeric(buys["shares"], errors="coerce")
    own = pd.to_numeric(buys["shares_owned_following"], errors="coerce")
    frac = np.where((own > 0) & (sh > 0), sh / own, np.nan)
    out = {
        "stage": "base_rates_holdings",
        "source": "backend/data/optimus/sec_insider/parsed/*.parquet",
        "open_market_purchase_rows": int(len(buys)),
        "rows_with_usable_holding": int(np.isfinite(frac).sum()),
        "share_missing_or_zero_holding": float(1 - np.isfinite(frac).mean()),
        "trade_as_pct_of_post_trade_holding": _q(pd.Series(frac)),
        "note": ("shares_owned_following is the reported holding AFTER the trade, "
                 "so shares/owned_following is the share of the resulting stake "
                 "that this trade bought. It is NOT a percent of net worth and "
                 "it is missing or zero on the rows counted above."),
    }
    _write("r2_base_rates_holdings", out)
    return out


# ======================================================= STAGE 2: MONTHLY SPINE

#: The house universe rules, verbatim from `scripts/era_replay_v2.py` and
#: `learner/evaluate.py`: average DAILY dollar volume >= $3m and a $5 price
#: floor. Applied BEFORE any book is believed, never at grading time.
TRADABLE_DOLLAR_VOL = 3_000_000.0
PRICE_FLOOR = 5.0

PANEL_COLS = ["permno", "eom", "me", "prc", "ret", "ret_exc", "ret_exc_lead1m",
              "sic", "ff49", "size_grp", "common", "primary_sec", "exch_main",
              "excntry", "obs_main", "ret_12_1", "ret_1_0", "ivol_capm_252d",
              "rvol_252d", "beta_60m", "dolvol_126d", "turnover_126d", "be_me"]


def _ff_monthly() -> pd.DataFrame:
    """Fama-French 5 + Mom, compounded from the PINNED daily vintage.

    `learner.benchmark` is THE ONE RULER and owns the hash gate; this function
    never refetches and never substitutes. Daily -> monthly by compounding
    (1+r), which is the only correct aggregation for a return series.
    """
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from learner import benchmark as B
    ff = B._load_pinned_ff().copy()
    ff["eom"] = ff.index.values.astype("datetime64[M]")
    cols = [c for c in ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "Mom", "RF"]
            if c in ff.columns]
    m = ff.groupby("eom")[cols].apply(
        lambda g: pd.Series({c: float(np.prod(1 + g[c].dropna()) - 1) for c in cols}))
    m.index = pd.to_datetime(m.index) + pd.offsets.MonthEnd(0)
    m.index.name = "eom"
    return m


def stage_spine() -> dict:
    """(permno, month) insider aggregates joined onto the JKP US monthly panel.

    THE PIT RULE, stated once. A filing whose `observed_at_utc` falls anywhere
    inside calendar month t is knowable by the close of month t. The portfolio
    is formed at eom(t) and earns `ret_exc_lead1m`, which is month t+1. That is
    STRICTLY more conservative than "the next session's open" -- a filing on the
    3rd of the month waits 28 days before it is acted on -- and it is the
    convention CMP's monthly calendar-time portfolios use.
    """
    print("stage 2: monthly spine")
    ev = pd.read_parquet(EVENTS, columns=[
        "permno", "event_type", "observed_at_utc", "insider_cik",
        "insider_is_officer", "insider_is_director", "insider_is_tenpercent",
        "insider_cmp_class", "insider_shares", "insider_price",
        "insider_dollar_value", "insider_cluster_buyers", "year"])
    ev = ev[ev["permno"].notna()].copy()
    eom = pd.to_datetime(ev["observed_at_utc"]).dt.tz_convert(None).values.astype("datetime64[M]")
    ev["eom"] = pd.to_datetime(eom) + pd.offsets.MonthEnd(0)
    ev["permno"] = ev["permno"].astype("int64")

    buys = ev[ev["event_type"].str.contains("buy")].copy()
    sells = ev[ev["event_type"] == "insider_open_market_sell"].copy()

    def agg(df: pd.DataFrame, tag: str) -> pd.DataFrame:
        g = df.groupby(["permno", "eom"])
        return pd.DataFrame({
            tag + "_rows": g.size(),
            tag + "_insiders": g["insider_cik"].nunique(),
            tag + "_dollars_raw": g["insider_dollar_value"].sum(),
            tag + "_shares": g["insider_shares"].sum(),
        })

    spine = agg(buys, "buy").join(agg(sells, "sell"), how="outer")
    for cls in ["opportunistic", "routine", "unclassifiable"]:
        spine = spine.join(agg(buys[buys["insider_cmp_class"] == cls],
                               "buy_" + cls), how="outer")
    # cluster: >=3 distinct insiders of one issuer on the same FILING DAY. The
    # flag is precomputed per row by I1; a month is a cluster month if any of
    # its buy rows carried it.
    gb = buys.groupby(["permno", "eom"])
    spine = spine.join((gb["insider_cluster_buyers"].max() >= 3)
                       .rename("buy_cluster_day"), how="left")
    spine = spine.join(gb["insider_cluster_buyers"].max()
                       .rename("buy_max_cluster_buyers"), how="left")
    for col, tag in [("insider_is_officer", "officer"),
                     ("insider_is_director", "director"),
                     ("insider_is_tenpercent", "tenpct")]:
        spine = spine.join(gb[col].max().rename("buy_by_" + tag), how="left")
    spine = spine.reset_index()
    print("  insider (permno, month) cells: {:,}".format(len(spine)))

    pan = pd.read_parquet(PANEL, columns=PANEL_COLS)
    pan = pan[(pan["excntry"] == "USA") & (pan["common"] == 1)
              & (pan["primary_sec"] == 1) & (pan["exch_main"] == 1)
              & (pan["obs_main"] == 1)].copy()
    # A panel row with no permno cannot be joined to a Form 4 and is a COUNTED
    # refusal, not a silent drop.
    _no_permno = int(pan["permno"].isna().sum())
    pan = pan[pan["permno"].notna()]
    print("  panel rows dropped for a missing permno: {:,}".format(_no_permno))
    pan["permno"] = pan["permno"].astype("int64")
    pan = pan[pan["eom"] >= pd.Timestamp("2005-12-31")]
    print("  panel rows (US common primary main, 2006+): {:,}".format(len(pan)))

    df = pan.merge(spine, on=["permno", "eom"], how="left")
    for c in [c for c in df.columns
              if c.endswith(("_rows", "_insiders", "_dollars_raw", "_shares"))]:
        df[c] = df[c].fillna(0.0)
    for c in ["buy_cluster_day", "buy_by_officer", "buy_by_director", "buy_by_tenpct"]:
        df[c] = df[c].fillna(False).astype(bool)
    df["buy_max_cluster_buyers"] = df["buy_max_cluster_buyers"].fillna(0.0)

    # ---- the filer-error tail in `insider_dollar_value`, handled not hidden.
    # 2,734 of 761,453 book-window buy rows carry a value above $100m and 448
    # above $100bn, because filers put the TOTAL in the price field (ASTI:
    # 666,666,672 shares at "$10,000,000"). A value-weighted book built on the
    # raw column is a book about a dozen typos. The cap is the issuer's own
    # market cap -- an insider cannot buy more of a company than it is worth.
    # Rows above it are COUNTED and set to NaN, never silently clipped.
    me_usd = df["me"].astype("float64") * 1e6
    bad = (df["buy_dollars_raw"] > me_usd) & (df["buy_dollars_raw"] > 0)
    df["buy_dollars"] = df["buy_dollars_raw"].where(~bad, np.nan)
    df["buy_dollar_pct_me"] = df["buy_dollars"] / me_usd

    df["tradable"] = ((pd.to_numeric(df["dolvol_126d"], errors="coerce") >= TRADABLE_DOLLAR_VOL)
                      & (pd.to_numeric(df["prc"], errors="coerce").abs() >= PRICE_FLOOR))
    df["year"] = df["eom"].dt.year
    df = df.merge(_ff_monthly(), left_on="eom", right_index=True, how="left")

    out_path = OUT / "r2_spine.parquet"
    df.to_parquet(out_path, index=False)
    rec = {
        "stage": "spine",
        "rows": int(len(df)),
        "months": int(df["eom"].nunique()),
        "permnos": int(df["permno"].nunique()),
        "window": [str(df["eom"].min().date()), str(df["eom"].max().date())],
        "rows_with_any_buy": int((df["buy_rows"] > 0).sum()),
        "rows_with_any_sell": int((df["sell_rows"] > 0).sum()),
        "rows_with_opportunistic_buy": int((df["buy_opportunistic_rows"] > 0).sum()),
        "rows_with_routine_buy": int((df["buy_routine_rows"] > 0).sum()),
        "rows_with_cluster_buy": int(df["buy_cluster_day"].sum()),
        "tradable_share": float(df["tradable"].mean()),
        "tradable_share_of_buy_rows": float(df.loc[df["buy_rows"] > 0, "tradable"].mean()),
        "filer_error_cells_dropped": int(bad.sum()),
        "filer_error_rule": "buy_dollars_raw > market cap -> NaN, counted",
        "panel_rows_dropped_no_permno": int(_no_permno),
        "label": "ret_exc_lead1m (JKP delisting-aware excess return, month t+1)",
        "pit": ("filing observed inside month t -> portfolio formed at eom(t) -> "
                "earns month t+1. Strictly more conservative than next-session open."),
        "universe_filters": "excntry=USA, common=1, primary_sec=1, exch_main=1, obs_main=1",
        "execution_floor": {"dolvol_126d_usd_per_day": TRADABLE_DOLLAR_VOL,
                            "price_floor_usd": PRICE_FLOOR},
        "factors": "FF5+Mom+RF compounded from learner.benchmark pinned daily vintage",
        "path": str(out_path.relative_to(ROOT)),
    }
    _write("r2_spine_receipt", rec)
    print(json.dumps(rec, indent=2))
    return rec


# ================================================ THE GRADER (beta printed FIRST)

#: The three eras. `learner.evaluate.long_eras()` is 1999-2007 / 2008-2015 /
#: 2016-2024 and it CANNOT be applied here: the CMP split needs three strictly
#: prior years of purchase history and the tape starts 2006q1, so nothing before
#: 2009 is classifiable. Rather than silently re-use a grid that does not
#: describe this window (the exact failure `evaluate.ERAS` was fixed for on
#: 2026-09-07), the window is cut into three near-equal blocks and the deviation
#: from the house grid is DECLARED here.
ERAS_R2: dict[str, tuple[str, str]] = {
    "2009-2014": ("2009-01-01", "2014-12-31"),
    "2015-2019": ("2015-01-01", "2019-12-31"),
    "2020-2024": ("2020-01-01", "2024-12-31"),
}


def _nw_t(y: np.ndarray, X: np.ndarray, lags: int = 6) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """OLS with Newey-West standard errors. Returns (beta, se_ols, se_nw)."""
    XtX_inv = np.linalg.pinv(X.T @ X)
    b = XtX_inv @ (X.T @ y)
    resid = y - X @ b
    n, k = X.shape
    s2 = float(resid @ resid) / max(n - k, 1)
    se_ols = np.sqrt(np.diag(XtX_inv) * s2)
    S = (X * resid[:, None]).T @ (X * resid[:, None])
    for L in range(1, lags + 1):
        w = 1.0 - L / (lags + 1.0)
        u = X * resid[:, None]
        G = u[L:].T @ u[:-L]
        S = S + w * (G + G.T)
    cov_nw = XtX_inv @ S @ XtX_inv
    se_nw = np.sqrt(np.clip(np.diag(cov_nw), 0, None))
    return b, se_ols, se_nw


def grade_series(r: pd.Series, ff: pd.DataFrame, label: str,
                 eras: dict | None = None) -> dict:
    """Grade ONE monthly excess-return series. BETA IS THE FIRST FIELD.

    `r` is indexed by the month the return was EARNED and is already in excess
    of the risk-free rate (the panel's `ret_exc_lead1m` is an excess return), so
    the CAPM regression is r = alpha + beta*(Mkt-RF) + e with no further
    subtraction. n_effective is the number of MONTHS -- date blocks, never
    name-days ([[feedback-name-days-are-not-periods]]).
    """
    r = pd.Series(r).dropna().sort_index()
    j = pd.concat([r.rename("r"), ff], axis=1, join="inner").dropna(
        subset=["r", "Mkt-RF"])
    n = len(j)
    if n < 24:
        return {"label": label, "n_months": n, "verdict": "CANNOT_DETERMINE",
                "reason": "fewer than 24 months"}
    y = j["r"].to_numpy(float)
    ones = np.ones(n)

    Xc = np.column_stack([ones, j["Mkt-RF"].to_numpy(float)])
    bc, se_c, senw_c = _nw_t(y, Xc)
    ff6 = [c for c in ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "Mom"] if c in j]
    X6 = np.column_stack([ones] + [j[c].to_numpy(float) for c in ff6])
    b6, se_6, senw_6 = _nw_t(y, X6)

    mu, sd = float(y.mean()), float(y.std(ddof=1))
    t_raw = mu / (sd / np.sqrt(n))
    sharpe_m = mu / sd if sd else np.nan
    out = {
        "label": label,
        # --- BETA FIRST. Everything below is read through it.
        "capm_beta": float(bc[1]),
        "capm_beta_t": float(bc[1] / senw_c[1]) if senw_c[1] else None,
        "capm_alpha_bp_per_month": float(bc[0] * 1e4),
        "capm_alpha_t_ols": float(bc[0] / se_c[0]) if se_c[0] else None,
        "capm_alpha_t_nw6": float(bc[0] / senw_c[0]) if senw_c[0] else None,
        "capm_r2": float(1 - np.var(y - Xc @ bc) / np.var(y)) if np.var(y) else None,
        "ff6_alpha_bp_per_month": float(b6[0] * 1e4),
        "ff6_alpha_t_nw6": float(b6[0] / senw_6[0]) if senw_6[0] else None,
        "ff6_loadings": {c: float(v) for c, v in zip(ff6, b6[1:])},
        "ff6_loading_t_nw6": {c: (float(v / s) if s else None)
                              for c, v, s in zip(ff6, b6[1:], senw_6[1:])},
        # --- only then the raw number
        "mean_excess_bp_per_month": float(mu * 1e4),
        "t_raw": float(t_raw),
        "n_months": int(n),
        "n_effective": int(n),
        "n_effective_unit": "MONTHS (date blocks), never name-days",
        "sd_monthly": float(sd),
        "sharpe_annual": float(sharpe_m * np.sqrt(12)) if sd else None,
        "ann_excess_pct": float(((1 + mu) ** 12 - 1) * 100),
        # 80% power, two-sided 5%: |mu| must exceed 2.802 * sd / sqrt(n)
        "mde_bp_per_month_80pct_power": float(2.802 * sd / np.sqrt(n) * 1e4),
        "powered_for_observed_effect": bool(abs(mu) >= 2.802 * sd / np.sqrt(n)),
        "window": [str(j.index.min().date()), str(j.index.max().date())],
    }
    if eras:
        er = {}
        for name, (lo, hi) in eras.items():
            sub = j.loc[(j.index >= lo) & (j.index <= hi)]
            if len(sub) < 12:
                er[name] = {"n_months": len(sub), "verdict": "CANNOT_DETERMINE"}
                continue
            ys = sub["r"].to_numpy(float)
            Xs = np.column_stack([np.ones(len(sub)), sub["Mkt-RF"].to_numpy(float)])
            bs, ses, senws = _nw_t(ys, Xs, lags=4)
            er[name] = {
                "n_months": int(len(sub)),
                "capm_beta": float(bs[1]),
                "capm_alpha_bp_per_month": float(bs[0] * 1e4),
                "capm_alpha_t_nw4": float(bs[0] / senws[0]) if senws[0] else None,
                "mean_excess_bp_per_month": float(ys.mean() * 1e4),
                "t_raw": float(ys.mean() / (ys.std(ddof=1) / np.sqrt(len(ys)))),
            }
        out["eras"] = er
        signs = [v.get("capm_alpha_bp_per_month") for v in er.values()
                 if v.get("capm_alpha_bp_per_month") is not None]
        out["eras_same_sign"] = (len(signs) > 0
                                 and all(np.sign(s) == np.sign(signs[0]) for s in signs))
    return out


def portfolio(df: pd.DataFrame, mask: pd.Series, weight: str = "vw",
              ret_col: str = "ret_exc_lead1m", min_names: int = 5
              ) -> tuple[pd.Series, pd.Series]:
    """Calendar-time portfolio return, indexed by the month it was EARNED.

    A month with fewer than `min_names` admissible names is a REFUSAL (dropped
    with its count reported), not a one-name portfolio wearing a portfolio's
    name -- [[feedback-a-min-names-filter-selects-the-regime]] is the reason the
    count is returned beside the series.
    """
    sub = df.loc[mask & df[ret_col].notna()]
    if weight == "vw":
        sub = sub.loc[sub["me"].notna() & (sub["me"] > 0)]
    rows = []
    for eom, g in sub.groupby("eom", sort=True):
        if len(g) < min_names:
            continue
        r = g[ret_col].to_numpy(float)
        w = (g["me"].to_numpy(float) if weight == "vw" else np.ones(len(g)))
        w = w / w.sum()
        rows.append((eom, float((w * r).sum()), len(g)))
    if not rows:
        return pd.Series(dtype=float), pd.Series(dtype=float)
    idx = pd.DatetimeIndex([x[0] for x in rows]) + pd.offsets.MonthEnd(1)
    return (pd.Series([x[1] for x in rows], index=idx),
            pd.Series([x[2] for x in rows], index=idx))


def _load_spine() -> tuple[pd.DataFrame, pd.DataFrame]:
    df = pd.read_parquet(OUT / "r2_spine.parquet")
    ff = _ff_monthly()
    return df, ff


# ============================================== STAGE 3: THE CMP REPLICATION

def stage_cmp() -> dict:
    """Opportunistic buys minus routine buys, value-weighted, monthly.

    CMP 2012 ("Decoding Inside Information", RFS) report 82 bp/month
    value-weighted on 1989-2007. THAT IS THE PRIOR, NOT THE CLAIM. This is a
    DIFFERENT tape (SEC bulk Form 4, not Thomson), a DIFFERENT window
    (2009-2024) and a stricter entry convention. A number that differs is not a
    replication failure; it is a different measurement, and both are printed.
    """
    print("stage 3: the CMP replication")
    df, ff = _load_spine()
    df = df[(df["year"] >= CMP_FIRST_YEAR) & (df["year"] <= CRSP_LAST_YEAR)]
    print("  rows in the 2009-2024 book window: {:,}".format(len(df)))

    arms = {
        "opportunistic_buy": df["buy_opportunistic_rows"] > 0,
        "routine_buy": df["buy_routine_rows"] > 0,
        "unclassifiable_buy": df["buy_unclassifiable_rows"] > 0,
        "any_buy": df["buy_rows"] > 0,
        "any_sell": df["sell_rows"] > 0,
        "no_insider_activity": (df["buy_rows"] == 0) & (df["sell_rows"] == 0),
    }
    res: dict = {"stage": "cmp_replication",
                 "prior": "CMP 2012: 82 bp/month VW long-short, 1989-2007, Thomson tape",
                 "window": [CMP_FIRST_YEAR, CRSP_LAST_YEAR],
                 "eras": ERAS_R2,
                 "arms": {}}
    series: dict[str, pd.Series] = {}
    for weight in ("vw", "ew"):
        for name, m in arms.items():
            r, n = portfolio(df, m, weight=weight)
            if r.empty:
                continue
            key = f"{name}__{weight}"
            series[key] = r
            g = grade_series(r, ff, key, eras=ERAS_R2)
            g["names_per_month"] = _q(n, qs=(0.1, 0.5, 0.9))
            res["arms"][key] = g

    # ---- the long-short legs, formed on the SAME months only
    for weight in ("vw", "ew"):
        for a, b, tag in [("opportunistic_buy", "routine_buy", "opp_minus_routine"),
                          ("opportunistic_buy", "no_insider_activity", "opp_minus_noactivity"),
                          ("any_buy", "any_sell", "buy_minus_sell"),
                          ("any_buy", "no_insider_activity", "buy_minus_noactivity")]:
            ka, kb = f"{a}__{weight}", f"{b}__{weight}"
            if ka not in series or kb not in series:
                continue
            ls = (series[ka] - series[kb]).dropna()
            key = f"{tag}__{weight}"
            series[key] = ls
            res["arms"][key] = grade_series(ls, ff, key, eras=ERAS_R2)

    # ---- the same thing with the execution floor ON (the honest book)
    dft = df[df["tradable"]]
    res["tradable_only"] = {}
    tser: dict[str, pd.Series] = {}
    for weight in ("vw", "ew"):
        for name, m in arms.items():
            r, n = portfolio(dft, m.loc[dft.index], weight=weight)
            if r.empty:
                continue
            key = f"{name}__{weight}"
            tser[key] = r
            g = grade_series(r, ff, key + "__tradable", eras=ERAS_R2)
            g["names_per_month"] = _q(n, qs=(0.1, 0.5, 0.9))
            res["tradable_only"][key] = g
        for a, b, tag in [("opportunistic_buy", "routine_buy", "opp_minus_routine"),
                          ("any_buy", "any_sell", "buy_minus_sell"),
                          ("any_buy", "no_insider_activity", "buy_minus_noactivity")]:
            ka, kb = f"{a}__{weight}", f"{b}__{weight}"
            if ka in tser and kb in tser:
                ls = (tser[ka] - tser[kb]).dropna()
                key = f"{tag}__{weight}"
                tser[key] = ls
                res["tradable_only"][key] = grade_series(ls, ff, key + "__tradable",
                                                         eras=ERAS_R2)

    pd.DataFrame(series).to_parquet(OUT / "r2_cmp_series.parquet")
    pd.DataFrame(tser).to_parquet(OUT / "r2_cmp_series_tradable.parquet")
    _write("r2_cmp", res)
    for k in ["opportunistic_buy__vw", "routine_buy__vw", "opp_minus_routine__vw",
              "opp_minus_routine__ew", "buy_minus_sell__vw"]:
        if k in res["arms"]:
            g = res["arms"][k]
            print("  {:<32} beta {:+.3f}  capm_a {:+7.1f}bp t_nw {:+.2f}  raw {:+7.1f}bp t {:+.2f}  n={}".format(
                k, g["capm_beta"], g["capm_alpha_bp_per_month"],
                g["capm_alpha_t_nw6"] or float("nan"),
                g["mean_excess_bp_per_month"], g["t_raw"], g["n_months"]))
    return res


# ============================ STAGE 4: THE DECLARED ENTRY CONVENTION, DAILY

WRDS_DAILY = ROOT / "backend" / "data" / "optimus" / "wrds"

#: Holding windows in SESSIONS, measured from the entry session (the session
#: after the filing day). h=21 is the closest daily analogue of the monthly
#: book; h=1 and h=5 exist because the insider literature puts most of the
#: reaction in the first week, and a monthly-formed book cannot see it.
DAILY_HORIZONS = (1, 5, 21, 63)

#: `learner.evaluate.COST_BPS_PER_SIDE` is the house rate. 25 bps is the second
#: rate the construction-tax table uses, and it is the honest one for a book
#: whose median name trades $3-10m a day: 10 bps one-way is a mega-cap number.
COST_BPS = (10.0, 25.0)


def _daily_returns(permnos: set[int], y0: int, y1: int) -> tuple[pd.DataFrame, dict]:
    """CRSP daily close-to-close return plus the entry-session OPEN return.

    The I1 lane's `next_tradable_session_bound()` says the earliest tradable
    moment is the NEXT session's open, so the first session of every holding
    window is priced OPEN-to-CLOSE and every later session close-to-close.
    Skipping the first session instead would be a different (and quietly
    friendlier) convention, so it is computed rather than assumed away.
    """
    frames = []
    for y in range(y0, y1 + 1):
        p = WRDS_DAILY / f"crsp_dsf_{y}.parquet"
        if not p.exists():
            raise FileNotFoundError(str(p))
        d = pd.read_parquet(p, columns=["permno", "date", "prc", "ret", "openprc"])
        frames.append(d[d["permno"].isin(permnos)])
    d = pd.concat(frames, ignore_index=True)
    d["permno"] = d["permno"].astype("int64")
    d["date"] = pd.to_datetime(d["date"])
    d["ret"] = pd.to_numeric(d["ret"], errors="coerce")
    px, op = d["prc"].abs(), d["openprc"].abs()
    d["ret_open"] = np.where((op > 0) & px.notna(), px / op - 1.0, np.nan)
    # A missing open is a REFUSAL that falls back to the close-to-close return
    # of the same session; the fallback rate is reported, never assumed small.
    d["ret_entry"] = d["ret_open"].where(d["ret_open"].notna(), d["ret"])
    prov = {"rows": int(len(d)),
            "open_missing_share": float(d["ret_open"].isna().mean()),
            "ret_missing_share": float(d["ret"].isna().mean())}
    return d[["permno", "date", "ret", "ret_entry"]].sort_values(["permno", "date"]), prov


def _turnover_monthly(hold: pd.DataFrame, weight: str) -> pd.Series:
    """EXACT one-way turnover per month: sum over days of sum_i |w_s(i)-w_{s-1}(i)|.

    Computed rather than assumed. The closed form (200% per h sessions) is an
    UPPER bound because same-day entries and exits partly offset, and a name
    that is re-bought inside its own window is never sold; a book graded on the
    bound would be charged for trades it does not make.
    """
    h = hold[["permno", "si", "w"]].copy()
    tot = h.groupby("si")["w"].sum()
    h["wn"] = h["w"] / h["si"].map(tot)
    piv = h.pivot_table(index="si", columns="permno", values="wn", aggfunc="sum")
    piv = piv.reindex(range(int(piv.index.min()), int(piv.index.max()) + 1)).fillna(0.0)
    d = piv.diff().abs().sum(axis=1)
    d.iloc[0] = piv.iloc[0].abs().sum()
    return d


def _concentration(r: pd.Series, k: int = 5) -> dict:
    """How much of the total excess comes from the best k months.

    The house has been burned twice by an edge that was five rebound months
    ([[feedback-the-learner-edge-was-six-rebound-months]]). A book whose top-5
    share is near 1.0 is a description of five months, whatever its t says.
    """
    r = pd.Series(r).dropna()
    if r.empty or r.sum() == 0:
        return {"top_k": k, "share": None}
    # A share of a near-zero total is not a concentration, it is a division by
    # noise: a long-short difference series that sums to ~0 produces shares of
    # -508 and +11 and they mean nothing. The guard is DECLARED rather than
    # letting the reader discover it in the table.
    if abs(float(r.sum())) < 0.2 * float(r.abs().sum()):
        return {"top_k": k, "share": None,
                "refused": "TOTAL_NEAR_ZERO -- a top-k share of a series that "
                           "sums to ~0 is undefined",
                "total_sum": float(r.sum()),
                "sum_abs": float(r.abs().sum())}
    top = r.nlargest(k)
    return {"top_k": k, "share": float(top.sum() / r.sum()),
            "months": [str(pd.Timestamp(i).date()) for i in top.index],
            "total_sum": float(r.sum()),
            "sum_without_top_k": float(r.sum() - top.sum()),
            "mean_bp_without_top_k": float(r.drop(top.index).mean() * 1e4)}


def stage_daily() -> dict:
    """Calendar-time daily portfolios at the DECLARED entry convention.

    On every session s a name is held if a qualifying filing was observed on a
    session in [s-h, s-1]; the first session of its window is priced open-to-
    close. The daily portfolio return is compounded to MONTHS before it is
    graded, because n_effective counts date blocks and 4,000 overlapping
    name-days is not 4,000 observations ([[feedback-name-days-are-not-periods]]).

    Costs are never omitted: exact one-way turnover is measured per month and
    charged at 10 and 25 bps per side, and BOTH the gross and the net series are
    graded.
    """
    print("stage 4: the declared entry convention, daily")
    df, ffm = _load_spine()
    ev = pd.read_parquet(EVENTS, columns=[
        "permno", "event_type", "observed_at_utc", "insider_cmp_class",
        "insider_cluster_buyers", "year"])
    ev = ev[ev["permno"].notna() & ev["year"].between(CMP_FIRST_YEAR, CRSP_LAST_YEAR)].copy()
    ev["permno"] = ev["permno"].astype("int64")
    ev["fdate"] = pd.to_datetime(ev["observed_at_utc"]).dt.tz_convert(None).dt.normalize()

    univ = df[["permno", "eom", "me", "tradable"]].copy()
    univ["ym"] = univ["eom"].dt.to_period("M")
    ev = ev[ev["permno"].isin(set(univ["permno"].unique()))]
    print("  events in the admissible universe: {:,}".format(len(ev)))

    need = set(ev["permno"].unique())
    print("  loading daily CRSP for {:,} permnos".format(len(need)))
    dly, dprov = _daily_returns(need, CMP_FIRST_YEAR, CRSP_LAST_YEAR)
    print("  daily rows: {:,}  (open missing {:.2%})".format(
        len(dly), dprov["open_missing_share"]))

    sessions = np.sort(dly["date"].unique())
    sidx = pd.Series(np.arange(len(sessions)), index=pd.DatetimeIndex(sessions))
    dly["si"] = sidx.reindex(dly["date"]).to_numpy()
    dret = dly.set_index(["permno", "si"])[["ret", "ret_entry"]]

    from learner import benchmark as B
    ffd = B._load_pinned_ff()
    ffd.index = pd.to_datetime(ffd.index)

    arms = {
        "opportunistic_buy": ev["insider_cmp_class"] == "opportunistic",
        "routine_buy": ev["insider_cmp_class"] == "routine",
        "any_buy": ev["event_type"].str.contains("buy"),
        "cluster_buy": (ev["event_type"].str.contains("buy")
                        & (ev["insider_cluster_buyers"] >= 3)),
        "solo_buy": (ev["event_type"].str.contains("buy")
                     & (ev["insider_cluster_buyers"] < 3)),
        "any_sell": ev["event_type"] == "insider_open_market_sell",
    }
    me_map = univ.set_index(["permno", "ym"])["me"]
    tr_map = univ.set_index(["permno", "ym"])["tradable"]

    res: dict = {"stage": "daily_entry_convention",
                 "entry": "next session's OPEN after the filing day (open-to-close on day 1)",
                 "horizons_sessions": list(DAILY_HORIZONS),
                 "cost_bps_per_side": list(COST_BPS),
                 "cost_model": "EXACT measured one-way turnover x bps, charged monthly",
                 "events_in_universe": int(len(ev)),
                 "daily_provenance": dprov,
                 "arms": {}}
    series: dict[str, pd.Series] = {}
    turn: dict[str, pd.Series] = {}

    for arm, m in arms.items():
        e = ev.loc[m, ["permno", "fdate"]].drop_duplicates()
        pos = np.searchsorted(sessions, e["fdate"].to_numpy("datetime64[ns]"), side="right")
        e = e.assign(entry_si=pos)
        e = e[e["entry_si"] < len(sessions) - max(DAILY_HORIZONS)]
        for h in DAILY_HORIZONS:
            hold = pd.concat(
                [pd.DataFrame({"permno": e["permno"].to_numpy(),
                               "si": e["entry_si"].to_numpy() + k, "leg": k})
                 for k in range(h)], ignore_index=True)
            hold = hold.sort_values("leg").drop_duplicates(["permno", "si"], keep="first")
            hold = hold.join(dret, on=["permno", "si"])
            hold["r"] = np.where(hold["leg"] == 0, hold["ret_entry"], hold["ret"])
            hold = hold[hold["r"].notna()].copy()
            hold["date"] = sessions[hold["si"].to_numpy()]
            ymi = pd.DatetimeIndex(hold["date"]).to_period("M")
            mi = pd.MultiIndex.from_arrays([hold["permno"], ymi])
            hold["me"] = me_map.reindex(mi).to_numpy()
            hold["tradable"] = tr_map.reindex(mi).to_numpy()
            for weight, tradable_only in [("ew", False), ("vw", False),
                                          ("ew", True), ("vw", True)]:
                hh = hold[hold["tradable"] == True] if tradable_only else hold  # noqa: E712
                if weight == "vw":
                    hh = hh[hh["me"].notna() & (hh["me"] > 0)]
                if hh.empty:
                    continue
                hh = hh.assign(w=(hh["me"].to_numpy(float) if weight == "vw"
                                  else np.ones(len(hh))))
                gsum = hh.assign(wr=hh["w"] * hh["r"]).groupby("si")[["wr", "w"]].sum()
                gsum["n"] = hh.groupby("si").size()
                agg = gsum[(gsum["n"] >= 5) & (gsum["w"] > 0)]
                if len(agg) < 250:
                    continue
                dates = pd.DatetimeIndex(sessions[agg.index.to_numpy().astype(int)])
                daily = pd.Series((agg["wr"] / agg["w"]).to_numpy(), index=dates)
                rf = ffd["RF"].reindex(daily.index).fillna(0.0)
                exc = daily - rf
                per = pd.DatetimeIndex(exc.index).to_period("M")
                monthly = (1 + exc).groupby(per).prod() - 1
                monthly.index = (monthly.index.to_timestamp(how="start")
                                 + pd.offsets.MonthEnd(0))
                # ---- exact turnover, same admissible rows, same day filter
                tmo = _turnover_monthly(hh[hh["si"].isin(agg.index)], weight)
                tdates = pd.DatetimeIndex(sessions[np.clip(tmo.index.to_numpy().astype(int),
                                                           0, len(sessions) - 1)])
                tser = pd.Series(tmo.to_numpy(), index=tdates)
                tmon = tser.groupby(pd.DatetimeIndex(tser.index).to_period("M")).sum()
                tmon.index = (tmon.index.to_timestamp(how="start")
                              + pd.offsets.MonthEnd(0))
                tmon = tmon.reindex(monthly.index).fillna(0.0)

                key = f"{arm}__h{h}__{weight}" + ("__tradable" if tradable_only else "")
                series[key] = monthly
                turn[key] = tmon
                gr = grade_series(monthly, ffm, key, eras=ERAS_R2)
                gr["name_days"] = int(len(hh))
                gr["sessions"] = int(len(agg))
                gr["median_names_per_session"] = float(agg["n"].median())
                gr["turnover_one_way_per_month"] = float(tmon.mean())
                gr["concentration_top5"] = _concentration(monthly, 5)
                for bps in COST_BPS:
                    net = monthly - tmon * bps / 1e4
                    gn = grade_series(net, ffm, key + f"__net{int(bps)}", eras=ERAS_R2)
                    gr[f"net{int(bps)}"] = {
                        "capm_beta": gn.get("capm_beta"),
                        "capm_alpha_bp_per_month": gn.get("capm_alpha_bp_per_month"),
                        "capm_alpha_t_nw6": gn.get("capm_alpha_t_nw6"),
                        "mean_excess_bp_per_month": gn.get("mean_excess_bp_per_month"),
                        "t_raw": gn.get("t_raw"),
                        "ann_excess_pct": gn.get("ann_excess_pct"),
                        "eras": gn.get("eras"),
                        "eras_same_sign": gn.get("eras_same_sign"),
                    }
                    series[key + f"__net{int(bps)}"] = net
                res["arms"][key] = gr
        print("  {} done".format(arm))

    # ---- the long-short legs, gross and net (both legs pay)
    for h in DAILY_HORIZONS:
        for weight in ("ew", "vw"):
            for suffix in ("", "__tradable"):
                for a, b, tag in [("opportunistic_buy", "routine_buy", "opp_minus_routine"),
                                  ("cluster_buy", "solo_buy", "cluster_minus_solo"),
                                  ("any_buy", "any_sell", "buy_minus_sell")]:
                    ka = f"{a}__h{h}__{weight}{suffix}"
                    kb = f"{b}__h{h}__{weight}{suffix}"
                    if ka not in series or kb not in series:
                        continue
                    ls = (series[ka] - series[kb]).dropna()
                    key = f"{tag}__h{h}__{weight}{suffix}"
                    series[key] = ls
                    gr = grade_series(ls, ffm, key, eras=ERAS_R2)
                    gr["concentration_top5"] = _concentration(ls, 5)
                    tt = (turn[ka].reindex(ls.index).fillna(0.0)
                          + turn[kb].reindex(ls.index).fillna(0.0))
                    gr["turnover_one_way_per_month"] = float(tt.mean())
                    for bps in COST_BPS:
                        net = ls - tt * bps / 1e4
                        gn = grade_series(net, ffm, key + f"__net{int(bps)}", eras=ERAS_R2)
                        gr[f"net{int(bps)}"] = {
                            "capm_beta": gn.get("capm_beta"),
                            "capm_alpha_bp_per_month": gn.get("capm_alpha_bp_per_month"),
                            "capm_alpha_t_nw6": gn.get("capm_alpha_t_nw6"),
                            "mean_excess_bp_per_month": gn.get("mean_excess_bp_per_month"),
                            "t_raw": gn.get("t_raw"),
                            "eras": gn.get("eras"),
                            "eras_same_sign": gn.get("eras_same_sign"),
                        }
                        series[key + f"__net{int(bps)}"] = net
                    res["arms"][key] = gr

    pd.DataFrame(series).to_parquet(OUT / "r2_daily_series.parquet")
    pd.DataFrame(turn).to_parquet(OUT / "r2_daily_turnover.parquet")
    _write("r2_daily", res)
    print("  arms graded: {}".format(len(res["arms"])))
    return res


# =================== STAGE 5: WINNER vs MATCHED LOSER, AND THE FOUR TRAPS

WRDS_BULK = ROOT / "backend" / "data" / "optimus" / "wrds" / "bulk"

#: Every matching variable is measured at the FORMATION month-end and is
#: therefore knowable before the outcome exists. Nothing realised after the
#: event may enter this list -- picking a control on the outcome is a documented
#: past failure of this programme
#: ([[feedback-a-matched-control-must-not-be-picked-on-the-outcome]]), and the
#: test below re-runs the match with the outcome ADDED to prove the design would
#: have caught it.
MATCH_KEYS = ["eom", "ff49", "size_q", "vol_q", "mom_q"]


def _quintile(s: pd.Series, q: int = 5) -> pd.Series:
    try:
        return pd.qcut(s, q, labels=False, duplicates="drop")
    except Exception:
        return pd.Series(np.nan, index=s.index)


def _earnings_months() -> set:
    """(permno, Period[M]) cells with a Compustat earnings announcement.

    PEAD is the obvious confound: an insider buying a week after a strong print
    is a post-earnings-drift trade wearing a Form 4 badge. `rdq` is the
    announcement DATE, so a cell is flagged if the announcement fell in that
    month or the month before -- the window a one-month drift would live in.
    """
    fq = pd.read_parquet(WRDS_BULK / "comp__fundq.parquet", columns=["gvkey", "rdq"])
    fq = fq[fq["rdq"].notna()].drop_duplicates()
    lh = pd.read_parquet(WRDS_BULK / "crsp__ccmxpf_lnkhist.parquet")
    lh = lh[lh["linktype"].isin(["LC", "LU", "LS"]) & lh["lpermno"].notna()].copy()
    lh["linkdt"] = pd.to_datetime(lh["linkdt"], errors="coerce")
    lh["linkenddt"] = pd.to_datetime(lh["linkenddt"], errors="coerce").fillna(
        pd.Timestamp("2099-12-31"))
    fq["rdq"] = pd.to_datetime(fq["rdq"], errors="coerce")
    m = fq.merge(lh[["gvkey", "lpermno", "linkdt", "linkenddt"]], on="gvkey", how="inner")
    m = m[(m["rdq"] >= m["linkdt"]) & (m["rdq"] <= m["linkenddt"])]
    m["permno"] = m["lpermno"].astype("int64")
    p = pd.PeriodIndex(m["rdq"], freq="M")
    cells = set(zip(m["permno"], p)) | set(zip(m["permno"], p + 1))
    return cells


def stage_matched() -> dict:
    """Coarsened exact matching: same month, sector, size, volatility, momentum.

    The informative unit is winner vs MATCHED LOSER (CLAUDE.md rule 4), and the
    long legs of stage 4 show exactly why: the `any_sell` leg carries a CAPM
    alpha of +68 bp/month with t 6.43, which is not a statement about insider
    selling -- it is a statement that the FF market is the wrong control for a
    filtered, tradable, value-weighted slice of 2009-2024. A control drawn from
    the same universe, the same month and the same cell answers the question the
    CAPM cannot.

    The estimate is a monthly series of treated-minus-control differences, so
    n_effective is MONTHS. The difference is computed cell by cell and pooled
    with treated-count weights, which is what makes it a matched estimate and
    not a regression with dummies.
    """
    print("stage 5: winner vs matched loser")
    df, ffm = _load_spine()
    df = df[df["year"].between(CMP_FIRST_YEAR, CRSP_LAST_YEAR)].copy()

    # ---- forward returns beyond one month, built by rolling `ret_exc` forward.
    df = df.sort_values(["permno", "eom"])
    g = df.groupby("permno")["ret_exc"]
    for h in (3, 12):
        fwd = np.ones(len(df))
        ok = np.ones(len(df), dtype=bool)
        for k in range(1, h + 1):
            s = g.shift(-k)
            ok &= s.notna().to_numpy()
            fwd = fwd * (1 + s.fillna(0).to_numpy())
        df[f"fwd_exc_{h}m"] = np.where(ok, fwd - 1.0, np.nan)

    df["size_q"] = df.groupby("eom")["me"].transform(lambda s: _quintile(s, 5))
    df["vol_q"] = df.groupby("eom")["rvol_252d"].transform(lambda s: _quintile(s, 5))
    df["mom_q"] = df.groupby("eom")["ret_12_1"].transform(lambda s: _quintile(s, 5))
    df["ff49"] = df["ff49"].fillna(-1).astype(int)

    ecells = _earnings_months()
    df["ym"] = df["eom"].dt.to_period("M")
    df["near_earnings"] = [(p, y) in ecells for p, y in zip(df["permno"], df["ym"])]
    print("  cells within one month of an earnings date: {:.1%}".format(
        df["near_earnings"].mean()))

    treatments = {
        "any_buy": df["buy_rows"] > 0,
        "opportunistic_buy": df["buy_opportunistic_rows"] > 0,
        "routine_buy": df["buy_routine_rows"] > 0,
        "cluster_buy": df["buy_cluster_day"],
        "solo_buy": (df["buy_rows"] > 0) & (~df["buy_cluster_day"]),
        "any_sell": df["sell_rows"] > 0,
    }

    def cem(d: pd.DataFrame, treat: pd.Series, ycol: str, keys: list[str],
            control_pool: pd.Series | None = None) -> tuple[pd.Series, dict]:
        """Cell-by-cell treated-minus-control mean, pooled to ONE number a month."""
        pool = control_pool if control_pool is not None else (~treat)
        d = d.assign(_t=treat.to_numpy(), _c=pool.to_numpy())
        d = d[d[ycol].notna() & d[keys].notna().all(axis=1) & (d["_t"] | d["_c"])]
        # Vectorised: the cell means are group SUMS over indicator-weighted
        # columns. A `groupby(...).apply` here is 1.2M python callbacks and the
        # first version of this function did not finish.
        d = d.assign(_yt=np.where(d["_t"], d[ycol], 0.0),
                     _yc=np.where(d["_c"], d[ycol], 0.0),
                     _nt=d["_t"].astype(float), _nc=d["_c"].astype(float))
        agg = (d.groupby(keys, observed=True)[["_yt", "_yc", "_nt", "_nc"]]
                 .sum().reset_index())
        agg = agg[(agg["_nt"] > 0) & (agg["_nc"] > 0)]
        if agg.empty:
            return pd.Series(dtype=float), {"cells_used": 0, "treated_matched": 0,
                                            "controls_matched": 0, "months": 0}
        agg["d"] = agg["_yt"] / agg["_nt"] - agg["_yc"] / agg["_nc"]
        agg = agg.rename(columns={"_nt": "nt", "_nc": "nc"})
        agg = agg.assign(_wd=agg["d"] * agg["nt"])
        mm = agg.groupby("eom")[["_wd", "nt"]].sum()
        by_month = (mm["_wd"] / mm["nt"])
        by_month.index = pd.DatetimeIndex(by_month.index)
        info = {"cells_used": int(len(agg)),
                "treated_matched": int(agg["nt"].sum()),
                "controls_matched": int(agg["nc"].sum()),
                "months": int(by_month.notna().sum())}
        return by_month.dropna(), info

    res: dict = {"stage": "matched_control",
                 "match_keys": MATCH_KEYS,
                 "outcome_never_in_the_match": True,
                 "designs": {}}
    series: dict[str, pd.Series] = {}

    variants = [
        ("full", MATCH_KEYS, None, df),
        ("no_sector", ["eom", "size_q", "vol_q", "mom_q"], None, df),
        ("tradable_only", MATCH_KEYS, None, df[df["tradable"]]),
        ("plus_earnings_flag", MATCH_KEYS + ["near_earnings"], None, df),
        ("no_earnings_months", MATCH_KEYS, None, df[~df["near_earnings"]]),
    ]
    for ycol in ("ret_exc_lead1m", "fwd_exc_3m", "fwd_exc_12m"):
        for vname, keys, pool, d in variants:
            for tname, tmask in treatments.items():
                tm = tmask.loc[d.index]
                s, info = cem(d, tm, ycol, keys)
                if len(s) < 24:
                    continue
                key = f"{tname}__{ycol}__{vname}"
                # months, not name-months: the difference series IS the estimate
                mu, sd, n = float(s.mean()), float(s.std(ddof=1)), len(s)
                series[key] = s
                # THE OVERLAP CORRECTION. `fwd_exc_3m` and `fwd_exc_12m` are
                # CUMULATIVE returns sampled monthly, so consecutive months
                # share 2 and 11 months of the same tape. A plain t across
                # months is inflated by roughly sqrt(h); the honest t is
                # Newey-West with h-1 lags. This is the same arithmetic that
                # turned +740% into +96.7% -- compounding overlapping windows as
                # if they were independent (learner/benchmark.py).
                h_out = {"ret_exc_lead1m": 1, "fwd_exc_3m": 3, "fwd_exc_12m": 12}[ycol]
                yv = s.to_numpy(float)
                _b, _seo, _senw = _nw_t(yv, np.ones((n, 1)), lags=max(1, h_out - 1))
                t_nw = float(_b[0] / _senw[0]) if _senw[0] else None
                res["designs"][key] = {
                    "horizon_months": h_out,
                    "units": ("bp of CUMULATIVE excess return over the horizon"
                              if h_out > 1 else "bp of one-month excess return"),
                    "mean_diff_bp": float(mu * 1e4),
                    "mean_diff_bp_per_month_equiv": float(mu * 1e4 / h_out),
                    "t_across_months_naive": float(mu / (sd / np.sqrt(n))),
                    "t_across_months": (t_nw if t_nw is not None
                                        else float(mu / (sd / np.sqrt(n)))),
                    "t_rule": ("Newey-West, h-1 lags -- overlapping windows"
                               if h_out > 1 else "OLS, non-overlapping"),
                    "n_effective_months": int(n),
                    "n_effective_unit": "MONTHS, never name-months",
                    "sd_monthly": sd,
                    "mde_bp_80pct_power": float(2.802 * sd / np.sqrt(n)
                                                 * np.sqrt(h_out) * 1e4),
                    "powered": bool(abs(mu) >= 2.802 * sd / np.sqrt(n)
                                    * np.sqrt(h_out)),
                    "concentration_top5": _concentration(s, 5),
                    **info,
                }
                if ycol == "ret_exc_lead1m" and vname == "full":
                    er = {}
                    for ename, (lo, hi) in ERAS_R2.items():
                        sub = s.loc[(s.index >= lo) & (s.index <= hi)]
                        er[ename] = ({"n": len(sub), "verdict": "CANNOT_DETERMINE"}
                                     if len(sub) < 12 else
                                     {"n": len(sub),
                                      "mean_diff_bp": float(sub.mean() * 1e4),
                                      "t": float(sub.mean() / (sub.std(ddof=1) / np.sqrt(len(sub))))})
                    res["designs"][key]["eras"] = er

    # ---- the leak canary: add the OUTCOME to the match keys. A design that
    # cannot be broken by matching on the outcome is not testing anything, so a
    # LARGE swing here is the design working, not a failure.
    d = df.copy()
    d["y_q"] = d.groupby("eom")["ret_exc_lead1m"].transform(lambda s: _quintile(s, 5))
    s_leak, info_leak = cem(d, treatments["any_buy"].loc[d.index], "ret_exc_lead1m",
                            MATCH_KEYS + ["y_q"])
    res["leak_canary"] = {
        "what": "the same match with the OUTCOME quintile added as a match key",
        "expectation": "the difference must collapse toward zero; if it does not, "
                       "the matching is not binding and the estimate is not matched",
        "mean_diff_bp": float(s_leak.mean() * 1e4) if len(s_leak) else None,
        "t": (float(s_leak.mean() / (s_leak.std(ddof=1) / np.sqrt(len(s_leak))))
              if len(s_leak) > 2 else None),
        **info_leak,
    }

    pd.DataFrame(series).to_parquet(OUT / "r2_matched_series.parquet")
    _write("r2_matched", res)
    for k, v in sorted(res["designs"].items()):
        if "lead1m" in k:
            print("  {:<52} {:+7.1f}bp t{:+6.2f} n{:>4} cells{:>7} top5 {}".format(
                k, v["mean_diff_bp"], v["t_across_months"],
                v["n_effective_months"], v["cells_used"],
                v["concentration_top5"].get("share")))
    print("  LEAK CANARY: {}".format(json.dumps(res["leak_canary"])))
    return res


def stage_traps() -> dict:
    """The four traps, each tested explicitly rather than argued away."""
    print("stage 6: the traps")
    df, ffm = _load_spine()
    df = df[df["year"].between(CMP_FIRST_YEAR, CRSP_LAST_YEAR)].copy()
    df["dv"] = pd.to_numeric(df["dolvol_126d"], errors="coerce")
    res: dict = {"stage": "traps", "traps": {}}

    # ---- trap 1 and 2: is it size? is it illiquidity? Where do buys LIVE.
    prof = {}
    for name, m in [("any_buy", df["buy_rows"] > 0),
                    ("opportunistic_buy", df["buy_opportunistic_rows"] > 0),
                    ("routine_buy", df["buy_routine_rows"] > 0),
                    ("cluster_buy", df["buy_cluster_day"]),
                    ("any_sell", df["sell_rows"] > 0),
                    ("universe", pd.Series(True, index=df.index))]:
        sub = df[m]
        prof[name] = {
            "n_cells": int(len(sub)),
            "size_grp_share": (sub["size_grp"].value_counts(normalize=True)
                               .round(4).to_dict()),
            "median_me_musd": float(sub["me"].median()),
            "median_dolvol_126d_usd": float(sub["dv"].median()),
            "share_above_3m_per_day": float((sub["dv"] >= TRADABLE_DOLLAR_VOL).mean()),
            "share_above_20m_per_day": float((sub["dv"] >= 20e6).mean()),
            "share_above_100m_per_day": float((sub["dv"] >= 100e6).mean()),
        }
    res["traps"]["where_the_events_live"] = prof

    # ---- the same book at three institutional sizes
    floors = {"none": 0.0, "3m_house_floor": TRADABLE_DOLLAR_VOL,
              "20m": 20e6, "100m": 100e6}
    ladder = {}
    for fname, floor in floors.items():
        d = df[(df["dv"] >= floor) & (df["prc"].abs() >= PRICE_FLOOR)] if floor else df
        arms = {"opportunistic_buy": d["buy_opportunistic_rows"] > 0,
                "routine_buy": d["buy_routine_rows"] > 0,
                "any_buy": d["buy_rows"] > 0,
                "any_sell": d["sell_rows"] > 0}
        ser = {}
        for a, m in arms.items():
            r, n = portfolio(d, m, weight="vw")
            if not r.empty:
                ser[a] = r
        cell = {}
        for a, r in ser.items():
            g = grade_series(r, ffm, a)
            cell[a] = {k: g.get(k) for k in
                       ("capm_beta", "capm_alpha_bp_per_month", "capm_alpha_t_nw6",
                        "mean_excess_bp_per_month", "t_raw", "n_months")}
        if "opportunistic_buy" in ser and "routine_buy" in ser:
            ls = (ser["opportunistic_buy"] - ser["routine_buy"]).dropna()
            g = grade_series(ls, ffm, "opp_minus_routine")
            cell["opp_minus_routine"] = {k: g.get(k) for k in
                                         ("capm_beta", "capm_alpha_bp_per_month",
                                          "capm_alpha_t_nw6", "mean_excess_bp_per_month",
                                          "t_raw", "n_months")}
        cell["universe_cells"] = int(len(d))
        ladder[fname] = cell
    res["traps"]["institutional_size_ladder"] = ladder

    # ---- trap 3: is it PEAD wearing a Form 4 badge?
    ecells = _earnings_months()
    df["ym"] = df["eom"].dt.to_period("M")
    df["near_earnings"] = [(p, y) in ecells for p, y in zip(df["permno"], df["ym"])]
    pead = {"share_of_universe_near_earnings": float(df["near_earnings"].mean()),
            "share_of_buy_cells_near_earnings":
                float(df.loc[df["buy_rows"] > 0, "near_earnings"].mean()),
            "share_of_sell_cells_near_earnings":
                float(df.loc[df["sell_rows"] > 0, "near_earnings"].mean()),
            "splits": {}}
    for tag, sub in [("near_earnings", df[df["near_earnings"]]),
                     ("away_from_earnings", df[~df["near_earnings"]])]:
        ser = {}
        for a, m in [("opportunistic_buy", sub["buy_opportunistic_rows"] > 0),
                     ("routine_buy", sub["buy_routine_rows"] > 0),
                     ("any_buy", sub["buy_rows"] > 0)]:
            r, n = portfolio(sub, m, weight="vw")
            if not r.empty:
                ser[a] = r
        cell = {a: {k: grade_series(r, ffm, a).get(k) for k in
                    ("capm_beta", "capm_alpha_bp_per_month", "capm_alpha_t_nw6",
                     "mean_excess_bp_per_month", "t_raw", "n_months")}
                for a, r in ser.items()}
        if "opportunistic_buy" in ser and "routine_buy" in ser:
            g = grade_series((ser["opportunistic_buy"] - ser["routine_buy"]).dropna(),
                             ffm, "ls")
            cell["opp_minus_routine"] = {k: g.get(k) for k in
                                         ("capm_beta", "capm_alpha_bp_per_month",
                                          "capm_alpha_t_nw6", "t_raw", "n_months")}
        pead["splits"][tag] = cell
    res["traps"]["pead"] = pead

    # ---- trap 4: the size-group slice of the monthly book
    bysize = {}
    for sg, sub in df.groupby("size_grp"):
        ser = {}
        for a, m in [("opportunistic_buy", sub["buy_opportunistic_rows"] > 0),
                     ("routine_buy", sub["buy_routine_rows"] > 0)]:
            r, n = portfolio(sub, m, weight="ew")
            if not r.empty:
                ser[a] = r
        if len(ser) == 2:
            g = grade_series((ser["opportunistic_buy"] - ser["routine_buy"]).dropna(),
                             ffm, f"opp_minus_routine__{sg}")
            bysize[str(sg)] = {k: g.get(k) for k in
                               ("capm_beta", "capm_alpha_bp_per_month",
                                "capm_alpha_t_nw6", "mean_excess_bp_per_month",
                                "t_raw", "n_months")}
    res["traps"]["by_size_group_ew"] = bysize

    _write("r2_traps", res)
    print(json.dumps(res["traps"]["where_the_events_live"], indent=2)[:1200])
    return res


# ==================== STAGE 7: THE FAMILY CORRECTION AND THE VERDICT

def _holm(pvals: dict) -> dict:
    """Holm-Bonferroni. The EXPORT rule (canon §63): what may be claimed."""
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m, out, running = len(items), {}, 0.0
    for i, (k, p) in enumerate(items):
        adj = min(1.0, (m - i) * p)
        running = max(running, adj)
        out[k] = running
    return out


def _bh(pvals: dict) -> dict:
    """Benjamini-Hochberg FDR. The SCREEN rule (canon §63): what may be looked at."""
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m, out, prev = len(items), {}, 1.0
    for i in range(m - 1, -1, -1):
        k, p = items[i]
        prev = min(prev, p * m / (i + 1))
        out[k] = min(1.0, prev)
    return out


def _dsr(sr_monthly: float, n: int, skew: float, kurt: float,
         n_trials: int, sr_var: float) -> float:
    """Deflated Sharpe ratio (Bailey & Lopez de Prado).

    The benchmark is the Sharpe a researcher would expect to find by chance
    after `n_trials` independent-ish attempts on a series of this length. The
    trial count is the FAMILY SIZE this lane actually searched, printed beside
    it, because a DSR quoted without its N is a Sharpe with extra steps.
    """
    from scipy import stats as _st
    if n_trials < 2 or n < 4 or sr_var <= 0:
        return float("nan")
    g = 0.5772156649
    z1 = _st.norm.ppf(1 - 1.0 / n_trials)
    z2 = _st.norm.ppf(1 - 1.0 / (n_trials * np.e))
    sr_star = np.sqrt(sr_var) * ((1 - g) * z1 + g * z2)
    denom = np.sqrt(max(1e-12, 1 - skew * sr_monthly
                        + (kurt - 1) / 4.0 * sr_monthly ** 2))
    return float(_st.norm.cdf((sr_monthly - sr_star) * np.sqrt(n - 1) / denom))


def stage_adjudicate() -> dict:
    """Every long-short cell this lane computed, corrected as ONE family.

    The family is not the cell that won. It is every long-short book that was
    graded on the way to it -- horizons, weightings, floors, monthly and daily
    conventions, gross and net -- because that is what was searched. Screening
    is BH-FDR, export is Holm (canon §63), and the power check comes BEFORE the
    confirmation (canon §64): a cell whose MDE exceeds its own effect is
    UNDERPOWERED, and an underpowered null is CANNOT_DETERMINE, not a negative.
    """
    from scipy import stats as _st
    print("stage 7: family correction")
    daily = json.loads((OUT / "r2_daily.json").read_text(encoding="utf-8"))
    cmpj = json.loads((OUT / "r2_cmp.json").read_text(encoding="utf-8"))
    matched = json.loads((OUT / "r2_matched.json").read_text(encoding="utf-8"))
    dser = pd.read_parquet(OUT / "r2_daily_series.parquet")
    mser = pd.read_parquet(OUT / "r2_matched_series.parquet")

    fam: dict[str, dict] = {}

    def add(key: str, series: pd.Series, source: str, kind: str,
            beta: float | None, alpha_bp: float | None, alpha_t: float | None,
            horizon_months: int = 1):
        """`horizon_months` > 1 means the outcome OVERLAPS across rows, and the
        t must be Newey-West at h-1 lags. Carrying the naive t into the family
        correction would let an overlap artefact clear Holm."""
        s = pd.Series(series).dropna()
        n = len(s)
        if n < 24:
            return
        mu, sd = float(s.mean()), float(s.std(ddof=1))
        if sd <= 0:
            return
        if horizon_months > 1:
            _b, _so, _sn = _nw_t(s.to_numpy(float), np.ones((n, 1)),
                                 lags=horizon_months - 1)
            t = float(_b[0] / _sn[0]) if _sn[0] else mu / (sd / np.sqrt(n))
        else:
            t = mu / (sd / np.sqrt(n))
        fam[key] = {
            "source": source, "kind": kind, "n_months": n,
            "capm_beta": beta, "capm_alpha_bp_per_month": alpha_bp,
            "capm_alpha_t_nw6": alpha_t,
            "mean_bp_per_month": mu * 1e4, "t": t,
            "p_two_sided": float(2 * (1 - _st.t.cdf(abs(t), n - 1))),
            "sharpe_monthly": mu / sd,
            "horizon_months": horizon_months,
            "t_rule": ("Newey-West h-1 (overlapping outcome)" if horizon_months > 1
                       else "OLS (non-overlapping)"),
            "skew": float(_st.skew(s)), "kurt": float(_st.kurtosis(s, fisher=False)),
            "mde_bp_80pct": float(2.802 * sd / np.sqrt(n) * 1e4),
            "powered": bool(abs(mu) >= 2.802 * sd / np.sqrt(n)),
            "top5_share": _concentration(s, 5).get("share"),
        }

    # ---- monthly-convention long-shorts
    for scope, blob in (("cmp_all_names", cmpj["arms"]),
                        ("cmp_tradable", cmpj["tradable_only"])):
        for k, g in blob.items():
            if "_minus_" not in k:
                continue
            fam_key = f"monthly::{scope}::{k}"
            fam[fam_key] = {
                "source": "stage3 monthly (formation at eom)", "kind": "long_short",
                "n_months": g["n_months"], "capm_beta": g["capm_beta"],
                "capm_alpha_bp_per_month": g["capm_alpha_bp_per_month"],
                "capm_alpha_t_nw6": g["capm_alpha_t_nw6"],
                "mean_bp_per_month": g["mean_excess_bp_per_month"], "t": g["t_raw"],
                "p_two_sided": float(2 * (1 - _st.t.cdf(abs(g["t_raw"]),
                                                        g["n_months"] - 1))),
                "sharpe_monthly": (g["sharpe_annual"] / np.sqrt(12)
                                   if g.get("sharpe_annual") else None),
                "skew": None, "kurt": None,
                "mde_bp_80pct": g["mde_bp_per_month_80pct_power"],
                "powered": g["powered_for_observed_effect"],
                "top5_share": None,
                "costs_applied": False,
            }

    # ---- daily-convention long-shorts, GROSS and NET at both rates
    for k, g in daily["arms"].items():
        if "_minus_" not in k:
            continue
        add(f"daily::gross::{k}", dser[k] if k in dser else pd.Series(dtype=float),
            "stage4 daily (next-session open)", "long_short",
            g.get("capm_beta"), g.get("capm_alpha_bp_per_month"),
            g.get("capm_alpha_t_nw6"))
        for bps in (10, 25):
            kk = f"{k}__net{bps}"
            if kk in dser:
                nb = g.get(f"net{bps}", {})
                add(f"daily::net{bps}::{k}", dser[kk],
                    "stage4 daily, net of measured turnover", "long_short_net",
                    nb.get("capm_beta"), nb.get("capm_alpha_bp_per_month"),
                    nb.get("capm_alpha_t_nw6"))

    # ---- matched-control differences
    for k in mser.columns:
        d = matched["designs"].get(k, {})
        add(f"matched::{k}", mser[k], "stage5 coarsened exact matching",
            "matched_difference", None, None, None,
            horizon_months=int(d.get("horizon_months", 1)))
        if f"matched::{k}" in fam:
            fam[f"matched::{k}"]["cells_used"] = d.get("cells_used")

    pv = {k: v["p_two_sided"] for k, v in fam.items()
          if v.get("p_two_sided") is not None}
    holm, bh = _holm(pv), _bh(pv)
    srs = [v["sharpe_monthly"] for v in fam.values()
           if v.get("sharpe_monthly") is not None]
    sr_var = float(np.var(srs, ddof=1)) if len(srs) > 2 else 0.0
    n_trials = len(pv)
    # THE DSR TRIAL SET, declared rather than assumed. `sr_var` over the WHOLE
    # family is inflated by books that lose 12%/month by cost arithmetic
    # (h=1 at 25 bps a side turns over 60x a month): those are not trials a
    # researcher would have selected among, and including them sets the
    # expected-max-Sharpe hurdle so high that every cell reports DSR 0.000,
    # which is a statement about the denominator and not about any book. The
    # CANDIDATE set is the cells that could ever be promoted -- net-of-cost
    # books and matched differences -- and both DSRs are printed.
    # A specification searched ONCE and then re-priced at two cost rates is one
    # trial, not three: `net10` and `net25` are the same book with a different
    # assumption, and counting them as separate searches both inflates N and
    # poisons `sr_var` with books that lose 12%/month by cost arithmetic alone.
    # The trial set is therefore the DISTINCT SPECIFICATIONS: every gross
    # long-short and every matched difference.
    cand = {k: v for k, v in fam.items()
            if "::net" not in k and v.get("sharpe_monthly") is not None}
    csrs = [v["sharpe_monthly"] for v in cand.values()]
    sr_var_c = float(np.var(csrs, ddof=1)) if len(csrs) > 2 else 0.0
    n_trials_c = len(cand)
    for k, v in fam.items():
        v["p_holm"] = holm.get(k)
        v["p_bh_fdr"] = bh.get(k)
        if all(v.get(x) is not None for x in ("sharpe_monthly", "skew", "kurt")):
            v["dsr_full_family"] = _dsr(v["sharpe_monthly"], v["n_months"],
                                        v["skew"], v["kurt"], n_trials, sr_var)
            v["dsr"] = _dsr(v["sharpe_monthly"], v["n_months"], v["skew"],
                            v["kurt"], n_trials_c, sr_var_c)
        # canon: the power check comes BEFORE the confirmation
        if not v.get("powered"):
            v["verdict"] = ("CANNOT_DETERMINE_UNDERPOWERED"
                            if v["p_two_sided"] > 0.05 else "POWER_FLAG_CHECK")
        elif v.get("p_holm", 1.0) <= 0.05:
            v["verdict"] = "SURVIVES_HOLM"
        elif v.get("p_bh_fdr", 1.0) <= 0.10:
            v["verdict"] = "SCREEN_ONLY_BH"
        elif v["p_two_sided"] <= 0.05:
            v["verdict"] = "SEPARATED_NOT_SURVIVING"
        else:
            v["verdict"] = "NOT_SEPARATED"

    res = {
        "stage": "adjudication",
        "family_size": n_trials,
        "family_definition": ("every long-short book and matched difference this "
                              "lane graded -- monthly and daily conventions, four "
                              "horizons, two weightings, two floors, gross and net "
                              "at two cost rates. The family is what was searched, "
                              "not what won."),
        "screen_rule": "BH-FDR q<=0.10", "export_rule": "Holm p<=0.05",
        "dsr_trials_full_family": n_trials, "dsr_sr_variance_full_family": sr_var,
        "dsr_trials_candidates": n_trials_c, "dsr_sr_variance_candidates": sr_var_c,
        "dsr_candidate_set": ("distinct specifications: gross long-shorts + "
                              "matched differences (net10/net25 are the SAME "
                              "specification re-priced, not new searches)"),
        "family_max_p": float(max(pv.values())) if pv else None,
        "family_min_p": float(min(pv.values())) if pv else None,
        "n_survives_holm": sum(1 for v in fam.values() if v["verdict"] == "SURVIVES_HOLM"),
        "n_screen_only": sum(1 for v in fam.values() if v["verdict"] == "SCREEN_ONLY_BH"),
        "n_underpowered": sum(1 for v in fam.values()
                              if v["verdict"].startswith("CANNOT_DETERMINE")),
        "cells": fam,
    }
    _write("r2_adjudication", res)
    print("  family size {}  Holm survivors {}  BH screen {}  underpowered {}".format(
        n_trials, res["n_survives_holm"], res["n_screen_only"], res["n_underpowered"]))
    surv = sorted([(v["p_holm"], k, v) for k, v in fam.items()
                   if v["verdict"] in ("SURVIVES_HOLM", "SCREEN_ONLY_BH")])
    for p, k, v in surv[:30]:
        print("  {:<62} bp{:+7.1f} t{:+6.2f} holm{:8.4f} bh{:8.4f} dsr{} n{}".format(
            k[:62], v["mean_bp_per_month"], v["t"], v["p_holm"], v["p_bh_fdr"],
            ("{:6.3f}".format(v["dsr"]) if v.get("dsr") == v.get("dsr") and v.get("dsr") is not None else "   n/a"),
            v["n_months"]))
    return res

# ============================================================ CLI

_STAGES = {
    "base": lambda: (stage_base(), stage_base_holdings()),
    "adjudicate": stage_adjudicate,
    "matched": stage_matched,
    "traps": stage_traps,
    "daily": stage_daily,
    "cmp": stage_cmp,
    "spine": stage_spine,
}


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] not in _STAGES:
        print(__doc__)
        print("stages:", ", ".join(_STAGES))
        return 2
    _STAGES[argv[1]]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
