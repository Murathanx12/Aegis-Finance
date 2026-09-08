"""R1 -- THE PREDICTABILITY ROUTER.  Is this name predictable RIGHT NOW?

Every engine in this repo has been asked "what will this stock do?" and killed
when it failed universally.  This lane asks the inverted question: for each
(name, month), what is the CONDITIONAL SKILL of an engine -- and if that skill
is low, route the slot to the benchmark instead of forcing a pick.

Licence: PRODUCT_EXPERIMENT.  Costs are never zero (10 bps/side on measured
weight turnover, the house convention in `learner.evaluate`).  Nothing here
places an order, seals a lane, or touches the track record.

THE LABEL, AND WHAT IT IS NOT
=============================
For engine e, month m, name i:

    u = cross-sectional percentile rank of the engine's prediction   in (0,1)
    v = cross-sectional percentile rank of the realised excess return in (0,1)
    s_e(i,m) = 12 * (u - 1/2) * (v - 1/2)

The 12 is Var(U(0,1))^-1, so the CROSS-SECTIONAL MEAN of s over a month is that
month's Spearman rank IC (checked numerically by `_verify_label_identity`).  The
label is therefore a decomposition of the thing the house already grades on --
one cell's contribution to the month's IC -- not a new metric.

It is NOT: "this stock is easy to forecast in the absolute"; NOT "this stock
will go up"; NOT volatility; NOT a confidence the engine emitted.  It is a
realised, engine-specific, month-specific quantity that only exists after the
fact, which is exactly why stage one has to forecast it from state.

THE DIRECTION FIREWALL (why FS_A is the primary feature set)
============================================================
For a LONG-ONLY top-k book every selected name has u > 1/2, so s reduces to v --
and any cell-level score that improves the book is, mathematically, a return
forecast restricted to the top of the book.  A "router" built on signed
momentum and signed revisions would be an alpha model wearing a router's coat.

So the primary feature set FS_A is DIRECTION-NEUTRAL: magnitudes, dispersions,
volatilities, densities, and the routed engine's OWN centred rank (the router is
allowed to know what the engine said -- that is the question being asked).  No
feature in FS_A can, on its own, say which way a name is going.  FS_B adds the
signed features and is reported as the contrast: if FS_B wins where FS_A does
not, the finding is "we found more alpha", not "we found predictability".
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
OPT = ROOT / "backend" / "data" / "optimus"
LEARNER = OPT / "learner"
OUT = OPT / "predictability_router"

COST_BPS_PER_SIDE = 10.0          # learner.evaluate.COST_BPS_PER_SIDE
TIE_SEED = 20260902               # learner.evaluate.TIE_SEED
BOOK_K = 50
SEED = 20260908

#: The router's era grid.  `learner.evaluate.ERAS` is 2016-2018 / 2019-2021 /
#: 2022-2024 and its FIRST window cannot be tested here for a structural reason:
#: the engines' out-of-sample predictions begin 2016-01, so 2016 is the router's
#: only training data.  An era that can only ever be empty is a gate that cannot
#: go green, so the grid is DECLARED here under its own name rather than quoting
#: canonical names over a window they do not describe.
ROUTER_ERAS: dict[str, tuple[str, str]] = {
    "2017-2018": ("2017-01", "2018-12"),
    "2019-2021": ("2019-01", "2021-12"),
    "2022-2024": ("2022-01", "2024-12"),
}

TEST_START_YEAR = 2017
EMBARGO_MONTHS = 2      # fwd_1m matures ~1 month out; 2 leaves one spare month

ENGINES = ["lgbm_clf__1m", "encoder_clf__residual__1m", "mlp__raw__1m",
           "ridge__raw__1m"]

#: Direction-neutral state.  Nothing here can say WHICH WAY a name is going.
FS_A_STATE = [
    "log_coverage", "numest", "dispersion", "disagreement",
    "vol_20d", "vol_60d", "log_dollar_vol_20d", "log_market_cap",
    "amihud_21d", "attention_z", "attention_z_5d",
    "abs_ret_1m", "abs_ret_3m", "abs_mom_12_1", "abs_net_rev_4w",
    "abs_upside", "dd_60d_mag", "range_52w",
    "ins_activity_90d", "ins_buy_90d", "ins_sell_90d", "ins_opp_buy_90d",
    "ins_cluster_90d", "ins_any_90d",
    "engine_disagree", "abs_u_c", "sector_code",
]
#: The routed engine's own centred cross-sectional rank.  Signed, but it is the
#: engine's OUTPUT, not an independent view of direction.
FS_A_ENGINE = ["u_c"]

#: The contrast set: everything above PLUS signed direction.
FS_B_EXTRA = [
    "ret_1m", "ret_3m", "ret_6m", "mom_12_1", "net_rev_4w", "target_rev_1m",
    "consensus_rev_1m", "upside", "ratio", "drawdown_60d",
    "prox_52w_high", "prox_52w_low", "vwap_60d_gap", "ret_5d",
    "ins_net_buy_90d",
]

FEATURE_SETS: dict[str, list[str]] = {
    "FS_A": FS_A_STATE + FS_A_ENGINE,
    "FS_A0": FS_A_STATE,
    "FS_B": FS_A_STATE + FS_A_ENGINE + FS_B_EXTRA,
}

#: The three columns the trap check asks about: is "predictable" just "big",
#: "quiet" or "well covered" wearing a new name?
TRAP_COLS = ["log_market_cap", "vol_60d", "log_coverage", "log_dollar_vol_20d"]


def _log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ---------------------------------------------------------------- insider PIT

def insider_features(keys: pd.DataFrame) -> pd.DataFrame:
    """Trailing-90-day insider counts as of `entry_date`, PIT on the FILING day.

    `observed_at_utc` is the filing day's END (the parquet's own receipt says
    so) and formation happens ON `entry_date`, so a filing stamped that same day
    is NOT knowable at formation.  The window is the strict half-open interval
    [entry_date - 90d, entry_date).
    """
    cols = ["permno", "event_type", "observed_at_utc", "insider_cluster_buyers"]
    ev = pd.read_parquet(OPT / "sec_insider" / "insider_events_v1.parquet",
                         columns=cols)
    ev = ev[ev["permno"].notna()].copy()
    ev["permno"] = ev["permno"].astype("int64")
    day = pd.to_datetime(ev["observed_at_utc"])
    if getattr(day.dt, "tz", None) is not None:
        day = day.dt.tz_convert("UTC").dt.tz_localize(None)
    ev["day"] = day.dt.normalize()
    ev = ev[ev["day"] >= pd.Timestamp("2015-06-01")]

    ev["is_buy"] = (ev["event_type"] == "insider_open_market_buy").astype("int32")
    ev["is_sell"] = (ev["event_type"] == "insider_open_market_sell").astype("int32")
    ev["is_opp"] = (ev["event_type"] == "insider_opportunistic_buy").astype("int32")
    ev["is_clu"] = (ev["insider_cluster_buyers"].fillna(0) >= 3).astype("int32")
    ev["n"] = 1

    metrics = ["n", "is_buy", "is_sell", "is_opp", "is_clu"]
    daily = (ev.groupby(["permno", "day"], as_index=False)[metrics].sum()
               .sort_values(["permno", "day"]))
    for c in metrics:
        daily[f"cum_{c}"] = daily.groupby("permno")[c].cumsum()
    cum = daily[["permno", "day"] + [f"cum_{c}" for c in metrics]].sort_values(
        ["day", "permno"])

    k = (keys[["permno", "entry_date"]].drop_duplicates().copy())
    k["permno"] = k["permno"].astype("int64")
    k["_hi"] = k["entry_date"]
    k["_lo"] = k["entry_date"] - pd.Timedelta(days=90)

    def _asof(on_col: str, suffix: str) -> pd.DataFrame:
        left = k.sort_values([on_col, "permno"])
        res = pd.merge_asof(left, cum, left_on=on_col, right_on="day",
                            by="permno", direction="backward",
                            allow_exact_matches=False)
        res = res[["permno", "entry_date"] + [f"cum_{c}" for c in metrics]]
        return res.rename(columns={f"cum_{c}": f"{c}{suffix}" for c in metrics})

    j = _asof("_hi", "_hi").merge(_asof("_lo", "_lo"), on=["permno", "entry_date"],
                                  how="left")
    for c in metrics:
        j[c] = j[f"{c}_hi"].fillna(0.0) - j[f"{c}_lo"].fillna(0.0)
    out = j[["permno", "entry_date"] + metrics].rename(columns={
        "n": "ins_activity_90d", "is_buy": "ins_buy_90d",
        "is_sell": "ins_sell_90d", "is_opp": "ins_opp_buy_90d",
        "is_clu": "ins_cluster_90d"})
    out["ins_net_buy_90d"] = out["ins_buy_90d"] - out["ins_sell_90d"]
    out["ins_any_90d"] = (out["ins_activity_90d"] > 0).astype("float64")
    return out


# --------------------------------------------------------------- panel build

def build_panel(force: bool = False) -> pd.DataFrame:
    cache = OUT / "router_panel_v1.parquet"
    if cache.exists() and not force:
        _log(f"panel from cache {cache.name}")
        return pd.read_parquet(cache)

    keep = ["permno", "month", "entry_date", "era", "fwd_1m", "mkt_vw_1m",
            "excess_vw_1m", "resid_vw_1m", "market_cap", "log_market_cap",
            "log_dollar_vol_20d", "vol_20d", "vol_60d", "coverage",
            "log_coverage", "numest", "dispersion", "disagreement",
            "net_rev_4w", "target_rev_1m", "consensus_rev_1m", "upside",
            "ratio", "ret_1m", "ret_3m", "ret_6m", "mom_12_1", "drawdown_60d",
            "sector_code", "band_code"]
    _log("loading train_table_long ...")
    tt = pd.read_parquet(LEARNER / "train_table_long.parquet", columns=keep)
    tt = tt[tt["month"] >= "2016-01"].copy()

    _log("loading oos_predictions_v2 ...")
    oo = pd.read_parquet(LEARNER / "oos_predictions_v2.parquet",
                         columns=["permno", "month"] + ENGINES)
    d = oo.merge(tt, on=["permno", "month"], how="inner")
    d = d[d["fwd_1m"].notna()].copy()
    _log(f"joined {len(d):,} rows, months {d['month'].min()}..{d['month'].max()}")

    _log("merging features_price on exact entry_date ...")
    fp = pd.read_parquet(LEARNER / "features_price.parquet")
    d = d.merge(fp.rename(columns={"date": "entry_date"}),
                on=["permno", "entry_date"], how="left")

    _log("building insider PIT features ...")
    ins = insider_features(d[["permno", "entry_date"]])
    d = d.merge(ins, on=["permno", "entry_date"], how="left")
    for c in ["ins_activity_90d", "ins_buy_90d", "ins_sell_90d",
              "ins_opp_buy_90d", "ins_cluster_90d", "ins_net_buy_90d",
              "ins_any_90d"]:
        d[c] = d[c].fillna(0.0)

    d["abs_ret_1m"] = d["ret_1m"].abs()
    d["abs_ret_3m"] = d["ret_3m"].abs()
    d["abs_mom_12_1"] = d["mom_12_1"].abs()
    d["abs_net_rev_4w"] = d["net_rev_4w"].abs()
    d["abs_upside"] = d["upside"].abs()
    d["dd_60d_mag"] = d["drawdown_60d"].abs()
    d["range_52w"] = d["prox_52w_high"] - d["prox_52w_low"]

    _log("ranking engines cross-sectionally ...")
    g = d.groupby("month", observed=True)
    rank_cols = []
    for e in ENGINES:
        rc = f"_u_{e}"
        d[rc] = g[e].rank(pct=True) - 0.5
        rank_cols.append(rc)
    d["engine_disagree"] = d[rank_cols].std(axis=1)

    d["_v_c"] = g["excess_vw_1m"].rank(pct=True) - 0.5
    for e in ENGINES:
        d[f"lab__{e}"] = 12.0 * d[f"_u_{e}"] * d["_v_c"]

    OUT.mkdir(parents=True, exist_ok=True)
    d.to_parquet(cache, index=False)
    _log(f"panel cached -> {cache.name} ({len(d):,} rows, {d.shape[1]} cols)")
    return d


def _verify_label_identity(d: pd.DataFrame, engine: str) -> dict:
    """The cross-sectional mean of the cell label must reproduce Spearman rho."""
    rows = []
    for _m, ch in d.groupby("month", observed=True):
        sub = ch[[engine, "excess_vw_1m", f"lab__{engine}"]].dropna()
        if len(sub) < 20:
            continue
        rho = float(stats.spearmanr(sub[engine], sub["excess_vw_1m"]).statistic)
        rows.append((rho, float(sub[f"lab__{engine}"].mean())))
    a = np.asarray(rows, dtype="float64")
    return {"months": int(len(a)),
            "max_abs_gap": float(np.abs(a[:, 0] - a[:, 1]).max()),
            "corr": float(np.corrcoef(a[:, 0], a[:, 1])[0, 1])}


# ------------------------------------------------------- stage one, walk-fwd

def _month_to_int(m: pd.Series) -> pd.Series:
    s = m.astype(str)
    return s.str.slice(0, 4).astype(int) * 12 + s.str.slice(5, 7).astype(int) - 1


def fit_router(d: pd.DataFrame, engine: str, feature_set: str,
               shuffle_seed: int | None = None) -> pd.Series:
    """Expanding walk-forward, annual refit, EMBARGO_MONTHS purge.

    Returns a Series aligned to `d.index` holding the out-of-sample predicted
    conditional skill.  NaN outside the test window.

    `shuffle_seed` is the NULL arm: the TRAINING label is permuted within each
    month (the date block), everything else identical -- universe, features,
    splits, model, costs.
    """
    import lightgbm as lgb

    feats = [c for c in FEATURE_SETS[feature_set] if c in d.columns]
    lab = f"lab__{engine}"
    mi = _month_to_int(d["month"])
    d = d.assign(_mi=mi)

    y = d[lab]
    if shuffle_seed is not None:
        rng = np.random.default_rng(shuffle_seed)
        y = y.copy()
        for _m, idx in d.groupby("month", observed=True).groups.items():
            vals = y.loc[idx].to_numpy()
            y.loc[idx] = rng.permutation(vals)

    out = pd.Series(np.nan, index=d.index, dtype="float64")
    years = sorted({int(str(m)[:4]) for m in d["month"].unique()})
    for yr in years:
        if yr < TEST_START_YEAR:
            continue
        test_lo = yr * 12
        train_hi = test_lo - EMBARGO_MONTHS          # exclusive
        tr = d[(d["_mi"] < train_hi) & y.notna()]
        te = d[(d["_mi"] >= test_lo) & (d["_mi"] < test_lo + 12)]
        if len(tr) < 5000 or te.empty:
            continue
        model = lgb.LGBMRegressor(
            n_estimators=300, learning_rate=0.05, num_leaves=31,
            min_child_samples=200, subsample=0.8, subsample_freq=1,
            colsample_bytree=0.8, reg_lambda=1.0, random_state=SEED,
            n_jobs=4, verbose=-1)
        model.fit(tr[feats], y.loc[tr.index])
        out.loc[te.index] = model.predict(te[feats])
    return out


# ------------------------------------------------------------------- the book

def routed_book(d: pd.DataFrame, engine: str, score_col: str | None,
                n_abstain: int, k: int = BOOK_K, weight: str = "vw",
                cost_bps: float = COST_BPS_PER_SIDE,
                ret_col: str = "fwd_1m", mkt_col: str = "mkt_vw_1m",
                random_seed: int | None = None) -> dict:
    """Top-k book in which the WORST-ROUTED slots hold the benchmark instead.

    Mirrors `learner.evaluate.book` exactly -- seeded tie-break, value weights,
    measured WEIGHT turnover, cost on BOTH sides -- with one change: after the
    top-k is chosen, the `n_abstain` names with the lowest predicted conditional
    skill are replaced by the market.  The abstained weight is held as a single
    synthetic instrument (permno -1) so switching in and out of it PAYS THE
    SPREAD like anything else; abstention is not a free option.

    `n_abstain == 0` reproduces `learner.evaluate.book` byte for byte (pinned by
    `test_routed_book_reproduces_evaluate_book`).

    `random_seed` selects the abstained slots at random instead of by score --
    the matched-count null for "abstention itself, not the router, did it".
    """
    if n_abstain > 0 and score_col is None and random_seed is None:
        raise SystemExit(
            "REFUSED: n_abstain > 0 with neither a score column nor a random "
            "seed. There is no abstention RULE here, and silently abstaining on "
            "the bottom of the engine's own ranking would make the router look "
            "like it did something the engine did.")
    cols = ["month", "permno", engine, ret_col, mkt_col, "market_cap"]
    if score_col:
        cols.append(score_col)
    dd = d[[c for c in cols if c in d.columns]].dropna(
        subset=[engine, ret_col, mkt_col]).copy()
    if dd.empty:
        return {"months": 0, "note": "no rows"}

    mo = dd["month"].astype(str).str.replace("-", "", regex=False).astype("int64")
    dd["_tb"] = (dd["permno"].astype("int64") * 2_654_435_761 + mo * 97
                 + TIE_SEED) % 1_000_003
    rng = np.random.default_rng(random_seed) if random_seed is not None else None

    rets, mkts, wbm, n_abs = {}, {}, {}, {}
    for m, chunk in dd.groupby("month", sort=True, observed=True):
        sel = chunk.sort_values([engine, "_tb"], ascending=[False, True]).head(k)
        if sel.empty:
            continue
        if weight == "vw" and sel["market_cap"].notna().any():
            w = sel["market_cap"].fillna(sel["market_cap"].median()).clip(lower=0)
            w = w / w.sum() if w.sum() > 0 else pd.Series(1.0 / len(sel),
                                                          index=sel.index)
        else:
            w = pd.Series(1.0 / len(sel), index=sel.index)

        na = min(int(n_abstain), len(sel))
        if na > 0:
            if rng is not None:
                drop_pos = rng.choice(len(sel), size=na, replace=False)
                drop = sel.index[drop_pos]
            else:
                order = sel[score_col].rank(method="first", na_option="bottom")
                drop = order.sort_values().index[:na]
        else:
            drop = sel.index[:0]

        mkt_r = float(sel[mkt_col].iloc[0])
        keep = sel.index.difference(drop)
        w_mkt = float(w.loc[drop].sum())
        port = float((w.loc[keep] * sel.loc[keep, ret_col]).sum()) + w_mkt * mkt_r
        rets[m] = port
        mkts[m] = mkt_r
        wmap = {int(p): float(x) for p, x in
                zip(sel.loc[keep, "permno"], w.loc[keep])}
        if w_mkt > 0:
            wmap[-1] = w_mkt
        wbm[m] = wmap
        n_abs[m] = na

    if not rets:
        return {"months": 0, "note": "no month produced a book"}
    gross = pd.Series(rets).sort_index()
    market = pd.Series(mkts).sort_index()

    turn, prev = [], None
    for m in gross.index:
        cur = wbm[m]
        if prev is None:
            turn.append(1.0)
        else:
            keys = set(cur) | set(prev)
            turn.append(0.5 * sum(abs(cur.get(kk, 0.0) - prev.get(kk, 0.0))
                                  for kk in keys))
        prev = cur
    turnover = pd.Series(turn, index=gross.index)
    net = gross - turnover * (cost_bps / 10_000.0) * 2.0

    return {"months": int(len(net)), "k": k,
            "n_abstain_per_month": int(np.mean(list(n_abs.values()))),
            "cost_bps_per_side": cost_bps,
            "mean_turnover": round(float(turnover.mean()), 4),
            "_net": net, "_gross": gross, "_market": market,
            "_turnover": turnover}


# ------------------------------------------------------- grading, beta first

def beta_first(net: pd.Series, market: pd.Series) -> dict:
    """Beta on the market FIRST, then the intercept it leaves behind.

    S43's lesson: excess is a LOADING until it is shown not to be.  A book that
    holds the market in 30% of its slots has a MECHANICALLY different beta from
    one that does not, so a raw excess comparison between them is a comparison
    of exposures.
    """
    a = pd.Series(net).dropna()
    b = pd.Series(market).reindex(a.index).dropna()
    a = a.reindex(b.index)
    n = len(a)
    if n < 12:
        return {"months": n, "note": "too few months"}
    X = np.column_stack([np.ones(n), b.to_numpy()])
    coef, *_ = np.linalg.lstsq(X, a.to_numpy(), rcond=None)
    resid = a.to_numpy() - X @ coef
    dof = n - 2
    s2 = float(resid @ resid) / dof
    xtx_inv = np.linalg.inv(X.T @ X)
    se = np.sqrt(np.diag(xtx_inv) * s2)
    tw = float((1.0 + a).prod())
    twm = float((1.0 + b).prod())
    yrs = n / 12.0
    return {
        "months": n,
        "beta": round(float(coef[1]), 4),
        "beta_t": round(float(coef[1] / se[1]), 3),
        "alpha_monthly": round(float(coef[0]), 5),
        "alpha_annualised": round(float(coef[0]) * 12, 4),
        "alpha_t": round(float(coef[0] / se[0]), 3),
        "alpha_p_two_sided": round(float(2 * stats.t.sf(abs(coef[0] / se[0]), dof)), 5),
        "r2": round(float(1 - (resid @ resid) / float(((a - a.mean()) ** 2).sum())), 4),
        "terminal_wealth_net": round(tw, 4),
        "terminal_wealth_market_same_months": round(twm, 4),
        "cagr_net": round(tw ** (1 / yrs) - 1.0, 4) if tw > 0 else None,
        "cagr_market": round(twm ** (1 / yrs) - 1.0, 4) if twm > 0 else None,
        "max_drawdown_net": _mdd(a),
        "max_drawdown_market": _mdd(b),
        "monthly_sd": round(float(a.std(ddof=1)), 4),
    }


def _mdd(r: pd.Series) -> float | None:
    r = pd.Series(r).dropna()
    if len(r) < 2:
        return None
    wealth = (1.0 + r).cumprod()
    return round(float((wealth / wealth.cummax() - 1.0).min()), 4)


def paired(a: pd.Series, b: pd.Series, label: str) -> dict:
    """Two terminal wealths are ONE draw of a correlated pair (CANON §58)."""
    a, b = pd.Series(a).dropna(), pd.Series(b).dropna()
    common = a.index.intersection(b.index)
    if len(common) < 3:
        return {"months": int(len(common)), "note": "too few shared months"}
    diff = (a.loc[common] - b.loc[common]).astype(float)
    n = len(diff)
    sd = float(diff.std(ddof=1))
    t = float(diff.mean() / (sd / np.sqrt(n))) if sd > 0 else None
    return {
        "compared": label,
        "months": n,
        "mean_monthly_difference": round(float(diff.mean()), 5),
        "annualised_difference": round(float(diff.mean()) * 12, 4),
        "sd_monthly_difference": round(sd, 5),
        "t_stat_paired": round(t, 3) if t is not None else None,
        "p_two_sided": round(float(2 * stats.t.sf(abs(t), n - 1)), 5) if t else None,
        "share_months_ahead": round(float((diff > 0).mean()), 4),
        # POWER BEFORE CONFIRMATION (CANON §64): the smallest annualised
        # difference this many months could have separated at 80% power, 5%
        # two-sided.  2.802 = z(0.975) + z(0.80).
        "mde_annualised_80pct": round(float(2.802 * sd / np.sqrt(n) * 12), 4),
    }


def holm(pvals: dict[str, float]) -> dict[str, dict]:
    """Holm-Bonferroni: the EXPORT bar (CANON §63)."""
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    n = len(items)
    out, running = {}, 0.0
    for i, (name, p) in enumerate(items):
        adj = min(1.0, max(running, (n - i) * p))
        running = adj
        out[name] = {"p_raw": round(p, 6), "p_holm": round(adj, 6),
                     "survives_holm_05": bool(adj < 0.05)}
    return out


def bh_fdr(pvals: dict[str, float], q: float = 0.10) -> dict[str, dict]:
    """Benjamini-Hochberg: the SCREEN bar (CANON §63)."""
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    n = len(items)
    crit = [(i + 1) / n * q for i in range(n)]
    passed = [i for i, (_, p) in enumerate(items) if p <= crit[i]]
    cut = max(passed) if passed else -1
    return {name: {"p_raw": round(p, 6), "bh_crit": round(crit[i], 6),
                   "survives_bh_10": bool(i <= cut)}
            for i, (name, p) in enumerate(items)}


def deflated_sharpe(net: pd.Series, n_trials: int,
                    trial_sharpes: list[float] | None = None) -> dict:
    """Bailey-Lopez de Prado DSR.

    The benchmark SR0 is the EXPECTED MAXIMUM of `n_trials` Sharpes drawn from
    noise, and it is SCALED BY THE DISPERSION OF THE TRIALS THEMSELVES:

        SR0 = sqrt(V) * [ (1-g) Z(1 - 1/N) + g Z(1 - 1/(N e)) ]

    with V the variance of the family's Sharpes.  The first version of this
    function dropped the sqrt(V) factor, which reports SR0 in units of standard
    normals instead of monthly Sharpes -- an expected-max noise Sharpe of 2.15
    per MONTH, a bar no strategy in any universe clears, and therefore a gate
    that cannot go green.  V falls back to 1/(n-1) (the asymptotic variance of a
    Sharpe estimate) when the family's Sharpes are not supplied.
    """
    r = pd.Series(net).dropna().astype(float)
    n = len(r)
    if n < 12 or r.std(ddof=1) == 0:
        return {"note": "too few months"}
    sr = float(r.mean() / r.std(ddof=1))
    g3 = float(r.skew())
    g4 = float(r.kurtosis()) + 3.0
    e = 0.5772156649
    if trial_sharpes is not None and len(trial_sharpes) > 2:
        v = float(np.var(np.asarray(trial_sharpes, dtype="float64"), ddof=1))
        v_src = "variance of the family's own Sharpes"
    else:
        v = 1.0 / max(1, n - 1)
        v_src = "asymptotic 1/(n-1); the family's Sharpes were not supplied"
    if n_trials > 1:
        z1 = stats.norm.ppf(1 - 1.0 / n_trials)
        z2 = stats.norm.ppf(1 - 1.0 / (n_trials * np.e))
        sr0 = np.sqrt(v) * ((1 - e) * z1 + e * z2)
    else:
        sr0 = 0.0
    denom = np.sqrt(max(1e-12, 1 - g3 * sr + (g4 - 1) / 4.0 * sr ** 2))
    dsr = float(stats.norm.cdf((sr - sr0) * np.sqrt(n - 1) / denom))
    return {"sharpe_monthly": round(sr, 4), "n_trials": n_trials,
            "trial_sharpe_variance": round(v, 6), "variance_source": v_src,
            "expected_max_noise_sharpe": round(float(sr0), 4),
            "dsr": round(dsr, 4), "dsr_clears_0_95": bool(dsr > 0.95)}


def era_slice(series: pd.Series) -> dict[str, pd.Series]:
    out = {}
    idx = pd.Index([str(x) for x in series.index])
    for name, (lo, hi) in ROUTER_ERAS.items():
        mask = np.asarray((idx >= lo) & (idx <= hi))
        if mask.sum() >= 6:
            out[name] = series[mask]
    return out


def neutralise(d: pd.DataFrame, score_col: str, cols: list[str]) -> pd.Series:
    """Cross-sectional OLS residual of the router score on size/vol/coverage.

    "Is `predictable` just `large`, `quiet` or `well covered` wearing a new
    name?"  If the residual keeps the gain, no.
    """
    use = [c for c in cols if c in d.columns]
    out = pd.Series(np.nan, index=d.index, dtype="float64")
    r2s = []
    for _m, ch in d.groupby("month", sort=True, observed=True):
        sub = ch[[score_col] + use].dropna()
        if len(sub) < 100:
            continue
        y = sub[score_col].to_numpy()
        X = np.column_stack([np.ones(len(sub))] + [
            stats.zscore(sub[c].to_numpy(), nan_policy="omit") for c in use])
        X = np.nan_to_num(X)
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        res = y - X @ coef
        out.loc[sub.index] = res
        sst = float(((y - y.mean()) ** 2).sum())
        if sst > 0:
            r2s.append(1 - float(res @ res) / sst)
    return out, (round(float(np.mean(r2s)), 4) if r2s else None)


# ------------------------------------------------------------------ the run

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force-panel", action="store_true")
    ap.add_argument("--null-draws", type=int, default=200)
    ap.add_argument("--shuffle-draws", type=int, default=10)
    ap.add_argument("--quick", action="store_true",
                    help="primary cell only; skips the sweep")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    d = build_panel(force=args.force_panel)
    d["u_c"] = np.nan  # filled per engine below
    receipt: dict = {
        "lane": "R1_PREDICTABILITY_ROUTER",
        "licence": "PRODUCT_EXPERIMENT",
        "generated_utc": pd.Timestamp.utcnow().isoformat(),
        "panel": {"rows": int(len(d)),
                  "months": int(d["month"].nunique()),
                  "month_min": str(d["month"].min()),
                  "month_max": str(d["month"].max()),
                  "names_per_month_mean": round(float(d.groupby("month", observed=True).size().mean()), 1)},
        "design": {
            "label": "s = 12 * (u-1/2) * (v-1/2); u = xs pct rank of engine "
                     "prediction, v = xs pct rank of excess_vw_1m; the xs MEAN "
                     "of s is the month's Spearman rank IC",
            "walk_forward": f"expanding, annual refit, first test year "
                            f"{TEST_START_YEAR}, purge/embargo {EMBARGO_MONTHS} months",
            "eras": ROUTER_ERAS,
            "book": f"top-{BOOK_K} value-weighted, {COST_BPS_PER_SIDE} bps/side "
                    "on measured weight turnover, both sides",
            "abstention": "the n lowest-router-score slots of the top-k hold the "
                          "market instead; the market slot is a real instrument "
                          "and pays the spread on entry and exit",
            "n_effective": "DATE BLOCKS (months), never name-months",
        },
    }

    # engine choice on TRAINING months only -- 2016, the router's train window.
    train_only = d[d["month"] < f"{TEST_START_YEAR}-01"]
    ic_train = {}
    for e in ENGINES:
        ics = []
        for _m, ch in train_only.groupby("month", observed=True):
            sub = ch[[e, "excess_vw_1m"]].dropna()
            if len(sub) >= 20:
                ics.append(float(stats.spearmanr(sub[e], sub["excess_vw_1m"]).statistic))
        ic_train[e] = round(float(np.mean(ics)), 5) if ics else None
    primary_engine = max(ic_train, key=lambda k: (ic_train[k] is not None, ic_train[k]))
    receipt["engine_choice"] = {
        "rank_ic_on_training_months_only": ic_train,
        "training_months": sorted({str(m) for m in train_only["month"].unique()}),
        "primary_engine": primary_engine,
        "note": "chosen on the ROUTER'S TRAINING window only, so the primary "
                "cell does not inherit a full-sample look",
    }
    _log(f"primary engine (train-window IC): {primary_engine}")

    receipt["label_identity_check"] = {
        e: _verify_label_identity(d, e) for e in ENGINES}

    # ---------------- the declared family, enumerated BEFORE any result ------
    q_grid = [0.10, 0.20, 0.30, 0.50]
    fs_grid = ["FS_A", "FS_B"] if not args.quick else ["FS_A"]
    family = [(e, fs, q) for e in ENGINES for fs in fs_grid for q in q_grid]
    family += [(primary_engine, "FS_A0", q) for q in q_grid]
    receipt["family"] = {
        "cells_declared": len(family),
        "engines": ENGINES, "feature_sets": fs_grid + ["FS_A0 (primary engine only)"],
        "abstention_fractions": q_grid,
        "primary_cell": {"engine": primary_engine, "feature_set": "FS_A", "q": 0.30},
        "note": "every cell LOOKED AT is charged (invariant 16). Holm for export, "
                "BH-FDR at q=0.10 for screening.",
    }

    results: dict[str, dict] = {}
    series_cache: dict[str, pd.Series] = {}
    scores_cache: dict[tuple[str, str], pd.Series] = {}

    # ---------------- always-trade baselines, one per engine ----------------
    _log("baselines: always-trade books")
    for e in ENGINES:
        b = routed_book(d, e, None, 0)
        te = b["_net"].index.astype(str)
        mask = np.asarray(te >= f"{TEST_START_YEAR}-01")
        net, mkt = b["_net"][mask], b["_market"][mask]
        series_cache[f"ALWAYS::{e}"] = net
        series_cache["MARKET"] = mkt
        results[f"ALWAYS::{e}"] = {
            "arm": "always_trade", "engine": e,
            "grade": beta_first(net, mkt),
            "mean_turnover": b["mean_turnover"],
        }
        _log(f"  {e}: TW {results[f'ALWAYS::{e}']['grade']['terminal_wealth_net']} "
             f"beta {results[f'ALWAYS::{e}']['grade']['beta']}")

    mkt = series_cache["MARKET"]

    # ---------------- stage one: fit the routers ----------------------------
    for e in ENGINES:
        for fs in (fs_grid + (["FS_A0"] if e == primary_engine else [])):
            _log(f"fitting router {e} / {fs} ...")
            dd = d.copy()
            dd["u_c"] = dd[f"_u_{e}"]
            dd["abs_u_c"] = dd["u_c"].abs()
            scores_cache[(e, fs)] = fit_router(dd, e, fs)

    # stage-one honesty: does the router's OOS score correlate with the label?
    receipt["stage_one_skill"] = {}
    for (e, fs), sc in scores_cache.items():
        m = pd.DataFrame({"month": d["month"], "score": sc, "lab": d[f"lab__{e}"]}).dropna()
        cors = []
        for _mm, ch in m.groupby("month", observed=True):
            if len(ch) >= 50 and ch["score"].nunique() > 2:
                cors.append(float(stats.spearmanr(ch["score"], ch["lab"]).statistic))
        s = pd.Series(cors)
        receipt["stage_one_skill"][f"{e}::{fs}"] = {
            "months": int(len(s)),
            "mean_xs_spearman_score_vs_label": round(float(s.mean()), 5),
            "t_across_months": round(float(s.mean() / (s.std(ddof=1) / np.sqrt(len(s)))), 3)
            if len(s) > 2 and s.std() > 0 else None,
        }

    # ---------------- the sweep --------------------------------------------
    for (e, fs, q) in family:
        na = int(round(q * BOOK_K))
        dd = d.copy()
        dd["_score"] = scores_cache[(e, fs)]
        b = routed_book(dd, e, "_score", na)
        idx = b["_net"].index.astype(str)
        mask = np.asarray(idx >= f"{TEST_START_YEAR}-01")
        net = b["_net"][mask]
        key = f"ROUTE::{e}::{fs}::q{int(q*100)}"
        series_cache[key] = net
        always = series_cache[f"ALWAYS::{e}"]
        results[key] = {
            "arm": "route_and_abstain", "engine": e, "feature_set": fs,
            "abstain_fraction": q, "slots_abstained": na,
            "mean_turnover": b["mean_turnover"],
            "grade": beta_first(net, mkt),
            "vs_always_trade": paired(net, always, f"{key} minus ALWAYS::{e}"),
            "vs_market": paired(net, mkt, f"{key} minus MARKET"),
        }
        _log(f"  {key}: TW {results[key]['grade']['terminal_wealth_net']} "
             f"beta {results[key]['grade']['beta']} "
             f"dTW-t {results[key]['vs_always_trade'].get('t_stat_paired')}")

    receipt["results"] = {k: v for k, v in results.items()}

    # ---------------- multiplicity ------------------------------------------
    pv = {k: v["vs_always_trade"]["p_two_sided"] for k, v in results.items()
          if v.get("arm") == "route_and_abstain"
          and v["vs_always_trade"].get("p_two_sided") is not None}
    receipt["multiplicity"] = {
        "family_size": len(pv),
        "family_max_p": round(max(pv.values()), 5) if pv else None,
        "family_min_p": round(min(pv.values()), 5) if pv else None,
        "holm_export": holm(pv),
        "bh_fdr_screen_q10": bh_fdr(pv, 0.10),
    }

    # ---------------- the primary cell, in full -----------------------------
    pk = f"ROUTE::{primary_engine}::FS_A::q30"
    pnet = series_cache[pk]
    palways = series_cache[f"ALWAYS::{primary_engine}"]
    receipt["primary"] = {
        "key": pk,
        "grade": results[pk]["grade"],
        "always_trade_grade": results[f"ALWAYS::{primary_engine}"]["grade"],
        "vs_always_trade": results[pk]["vs_always_trade"],
        "vs_market": results[pk]["vs_market"],
        "dsr_vs_family": deflated_sharpe(
            pnet, n_trials=len(pv) if pv else 1,
            trial_sharpes=[float(s.mean() / s.std(ddof=1))
                           for k, s in series_cache.items()
                           if k.startswith("ROUTE::") and s.std(ddof=1) > 0]),
        "eras": {},
    }
    for name, seg in era_slice(pnet).items():
        a_seg = palways.reindex(seg.index)
        m_seg = mkt.reindex(seg.index)
        receipt["primary"]["eras"][name] = {
            "grade": beta_first(seg, m_seg),
            "vs_always_trade": paired(seg, a_seg, f"{name}: routed minus always"),
        }

    # ---------------- NULL 1: random abstention, matched count --------------
    _log(f"null 1: {args.null_draws} random-abstention draws ...")
    na = int(round(0.30 * BOOK_K))
    draws = []
    for i in range(args.null_draws):
        b = routed_book(d, primary_engine, None, na, random_seed=SEED + i)
        idx = b["_net"].index.astype(str)
        seg = b["_net"][np.asarray(idx >= f"{TEST_START_YEAR}-01")]
        diff = (seg - palways.reindex(seg.index)).dropna()
        draws.append(float(diff.mean()))
    draws = np.asarray(draws)
    obs = float((pnet - palways.reindex(pnet.index)).dropna().mean())
    receipt["null_random_abstention"] = {
        "draws": int(len(draws)),
        "observed_mean_monthly_gain": round(obs, 5),
        "null_mean": round(float(draws.mean()), 5),
        "null_sd": round(float(draws.std(ddof=1)), 5),
        "null_p_one_sided": round(float((draws >= obs).mean()), 4),
        "percentile_of_observed": round(float((draws < obs).mean() * 100), 2),
        "asks": "does moving 30% of the book to the market -- ANY 30% -- do this?",
    }

    # ---------------- NULL 2: shuffled predictability labels ---------------
    _log(f"null 2: {args.shuffle_draws} shuffled-label routers ...")
    sh = []
    dd = d.copy()
    dd["u_c"] = dd[f"_u_{primary_engine}"]
    dd["abs_u_c"] = dd["u_c"].abs()
    for i in range(args.shuffle_draws):
        sc = fit_router(dd, primary_engine, "FS_A", shuffle_seed=SEED + 1000 + i)
        d2 = d.copy()
        d2["_score"] = sc
        b = routed_book(d2, primary_engine, "_score", na)
        idx = b["_net"].index.astype(str)
        seg = b["_net"][np.asarray(idx >= f"{TEST_START_YEAR}-01")]
        diff = (seg - palways.reindex(seg.index)).dropna()
        sh.append(float(diff.mean()))
        _log(f"   shuffle {i}: {sh[-1]:+.5f}")
    sh = np.asarray(sh)
    receipt["null_shuffled_labels"] = {
        "draws": int(len(sh)),
        "observed_mean_monthly_gain": round(obs, 5),
        "null_mean": round(float(sh.mean()), 5),
        "null_sd": round(float(sh.std(ddof=1)), 5) if len(sh) > 2 else None,
        "null_p_one_sided": round(float((sh >= obs).mean()), 4),
        "asks": "a router trained on labels permuted within the date block must "
                "produce no gain",
    }

    # ---------------- the trap: size / vol / coverage ----------------------
    _log("trap check: is the router score size, vol and coverage in disguise?")
    dn = d.copy()
    dn["_score"] = scores_cache[(primary_engine, "FS_A")]
    resid, r2 = neutralise(dn, "_score", TRAP_COLS)
    dn["_resid"] = resid
    b = routed_book(dn, primary_engine, "_resid", na)
    idx = b["_net"].index.astype(str)
    rnet = b["_net"][np.asarray(idx >= f"{TEST_START_YEAR}-01")]
    corrs = {}
    for c in TRAP_COLS:
        sub = dn[["_score", c]].dropna()
        corrs[c] = round(float(stats.spearmanr(sub["_score"], sub[c]).statistic), 4)
    receipt["trap_size_vol_coverage"] = {
        "mean_monthly_r2_of_score_on_size_vol_coverage_dollarvol": r2,
        "pooled_spearman_score_vs": corrs,
        "residualised_router": {
            "grade": beta_first(rnet, mkt),
            "vs_always_trade": paired(rnet, palways, "residualised routed minus always"),
        },
        "asks": "regress the router score on size, volatility, coverage and "
                "dollar volume; what is left, and does it still route?",
    }

    # THE SERIES THEMSELVES.  A receipt that carries only summaries cannot be
    # re-graded, and every re-grade in this repo so far has changed a number.
    sp = OUT / "R1_arm_series.parquet"
    pd.DataFrame(series_cache).to_parquet(sp)
    receipt["arm_series_parquet"] = sp.name

    receipt["runtime_seconds"] = round(time.time() - t0, 1)
    path = OUT / "R1_router_receipt.json"
    path.write_text(json.dumps(receipt, indent=1, default=str), encoding="utf-8")
    _log(f"receipt -> {path}")


if __name__ == "__main__":
    main()
