"""R1 stage two -- WHY the router did what it did, and what the ceiling was.

Stage one asked "does routing on predicted conditional skill beat always
trading?".  Stage two asks the four questions that make that answer readable
whichever way it came out:

  C  THE CEILING.  An ORACLE that abstains using the REALISED label -- future
     information, never tradable, reported only as a bound.  Without it, "no
     gain" cannot be told apart from "there was nothing to win": the mechanism
     might be sound and stage one merely weak, or the mechanism might be worth
     nothing even with perfect foresight.  The ceiling separates those two.

  D  THE DECILE TABLE.  Realised conditional IC by decile of PREDICTED skill,
     with a t across months.  This is the scientific claim -- "predictability is
     forecastable" -- stated without a book, without costs, and without the
     long-only truncation that turns any cell score into a return forecast.

  I  THE INVERSE ARM.  Abstain on the HIGHEST predicted skill.  If the router
     had no information the inverse is symmetric noise; if the inverse WINS, the
     router has real information carrying the wrong sign for a long-only top-k,
     which is a different (and more useful) finding than "it does not work".

  E  ENGINE ROUTING.  Pick, per name-month, the engine with the highest
     predicted skill, and score the book with that engine's rank.  Compared with
     each single engine and with the equal-weight rank ensemble of all four --
     because "better than the best engine chosen afterwards" is not a claim.

Licence: PRODUCT_EXPERIMENT.  Costs never zero.  Nothing here trades.
"""

from __future__ import annotations

import argparse
import json
import time

import numpy as np
import pandas as pd
from scipy import stats

from scripts.predictability_router_r1 import (
    BOOK_K, ENGINES, OUT, ROUTER_ERAS, SEED, TEST_START_YEAR, TRAP_COLS,
    _log, beta_first, bh_fdr, build_panel, era_slice, fit_router, holm,
    paired, routed_book,
)

SCORES = OUT / "router_scores_v1.parquet"


def _test_mask(series: pd.Series) -> np.ndarray:
    return np.asarray(series.index.astype(str) >= f"{TEST_START_YEAR}-01")


def get_scores(d: pd.DataFrame, force: bool = False) -> pd.DataFrame:
    """Out-of-sample router scores for every engine under FS_A, cached."""
    if SCORES.exists() and not force:
        _log(f"scores from cache {SCORES.name}")
        return pd.read_parquet(SCORES)
    cols = {}
    for e in ENGINES:
        _log(f"fitting FS_A router for {e} ...")
        dd = d.copy()
        dd["u_c"] = dd[f"_u_{e}"]
        dd["abs_u_c"] = dd["u_c"].abs()
        cols[f"score__{e}"] = fit_router(dd, e, "FS_A")
    out = pd.DataFrame(cols, index=d.index)
    out.to_parquet(SCORES, index=False)
    _log(f"scores cached -> {SCORES.name}")
    return out


def decile_table(d: pd.DataFrame, engine: str, score_col: str,
                 n_bins: int = 10) -> dict:
    """Realised conditional IC contribution by decile of PREDICTED skill.

    n is MONTHS.  The label's cross-sectional mean is the month's rank IC, so a
    decile's mean label is that decile's share of the month's IC -- if the
    router works, the table is monotone and the top-minus-bottom t clears.
    """
    lab = f"lab__{engine}"
    sub = d[["month", score_col, lab]].dropna()
    per_month: dict[int, list[float]] = {i: [] for i in range(n_bins)}
    tb_series = []
    for _m, ch in sub.groupby("month", observed=True):
        if len(ch) < 200 or ch[score_col].nunique() < n_bins:
            continue
        q = pd.qcut(ch[score_col].rank(method="first"), n_bins, labels=False)
        means = ch.groupby(q)[lab].mean()
        for i in range(n_bins):
            if i in means.index:
                per_month[i].append(float(means.loc[i]))
        if 0 in means.index and (n_bins - 1) in means.index:
            tb_series.append(float(means.loc[n_bins - 1] - means.loc[0]))
    tb = pd.Series(tb_series)
    rows = []
    for i in range(n_bins):
        s = pd.Series(per_month[i])
        t = float(s.mean() / (s.std(ddof=1) / np.sqrt(len(s)))) if len(s) > 2 and s.std() > 0 else None
        rows.append({"decile": i + 1, "months": int(len(s)),
                     "mean_realised_ic_contribution": round(float(s.mean()), 5),
                     "t_across_months": round(t, 3) if t is not None else None})
    t_tb = float(tb.mean() / (tb.std(ddof=1) / np.sqrt(len(tb)))) if len(tb) > 2 else None
    ranks = [r["mean_realised_ic_contribution"] for r in rows]
    return {
        "n_bins": n_bins, "months": int(len(tb)), "deciles": rows,
        "top_minus_bottom": round(float(tb.mean()), 5),
        "top_minus_bottom_t": round(t_tb, 3) if t_tb is not None else None,
        "top_minus_bottom_p_two_sided":
            round(float(2 * stats.t.sf(abs(t_tb), len(tb) - 1)), 5) if t_tb else None,
        "spearman_decile_vs_realised": round(
            float(stats.spearmanr(np.arange(n_bins), ranks).statistic), 4),
        "mde_annualised_na": "this table is an IC table; the MDE below is on the "
                             "top-minus-bottom monthly series",
        "mde_top_minus_bottom_80pct": round(
            float(2.802 * tb.std(ddof=1) / np.sqrt(len(tb))), 5) if len(tb) > 2 else None,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force-scores", action="store_true")
    args = ap.parse_args()
    t0 = time.time()
    d = build_panel()
    sc = get_scores(d, force=args.force_scores)
    for c in sc.columns:
        d[c] = sc[c].to_numpy()

    primary = "lgbm_clf__1m"
    na30 = int(round(0.30 * BOOK_K))
    r: dict = {
        "lane": "R1_PREDICTABILITY_ROUTER_STAGE_2",
        "licence": "PRODUCT_EXPERIMENT",
        "generated_utc": pd.Timestamp.utcnow().isoformat(),
        "primary_engine": primary,
        "reads": "R1_router_receipt.json",
    }

    base = {}
    for e in ENGINES:
        b = routed_book(d, e, None, 0)
        m = _test_mask(b["_net"])
        base[e] = {"net": b["_net"][m], "market": b["_market"][m]}
    mkt = base[primary]["market"]

    # ---- D: the decile table, per engine (no book, no costs, no truncation)
    _log("D: decile tables ...")
    r["decile_tables"] = {
        e: decile_table(d, e, f"score__{e}") for e in ENGINES}

    # ---- C: the oracle ceiling ------------------------------------------
    _log("C: oracle ceiling ...")
    r["oracle_ceiling"] = {}
    for e in ENGINES:
        dd = d.copy()
        dd["_oracle"] = dd[f"lab__{e}"]          # FUTURE INFORMATION. Not tradable.
        b = routed_book(dd, e, "_oracle", na30)
        m = _test_mask(b["_net"])
        net = b["_net"][m]
        r["oracle_ceiling"][e] = {
            "grade": beta_first(net, mkt),
            "vs_always_trade": paired(net, base[e]["net"], f"ORACLE({e}) minus ALWAYS({e})"),
            "warning": "uses the REALISED label; a bound on what perfect "
                       "abstention could have bought, never a strategy",
        }

    # ---- I: the inverse arm ---------------------------------------------
    _log("I: inverse arm ...")
    r["inverse_arm"] = {}
    for e in ENGINES:
        dd = d.copy()
        dd["_inv"] = -dd[f"score__{e}"]
        b = routed_book(dd, e, "_inv", na30)
        m = _test_mask(b["_net"])
        net = b["_net"][m]
        r["inverse_arm"][e] = {
            "grade": beta_first(net, mkt),
            "vs_always_trade": paired(net, base[e]["net"],
                                      f"INVERSE({e}) minus ALWAYS({e})"),
        }

    # ---- E: engine routing ----------------------------------------------
    _log("E: engine routing ...")
    score_cols = [f"score__{e}" for e in ENGINES]
    rank_cols = [f"_u_{e}" for e in ENGINES]
    S = d[score_cols].to_numpy()
    U = d[rank_cols].to_numpy()
    pick = np.full(len(d), np.nan)
    ok = ~np.isnan(S).all(axis=1)
    arg = np.nanargmax(np.where(np.isnan(S), -np.inf, S)[ok], axis=1)
    pick[ok] = U[ok, arg]
    d["_routed_engine_rank"] = pick
    d["_engine_choice"] = np.nan
    d.loc[ok, "_engine_choice"] = arg
    d["_ew_ensemble_rank"] = np.nanmean(U, axis=1)

    arms = {}
    for name, col in [("ROUTED_ENGINE", "_routed_engine_rank"),
                      ("EW_ENSEMBLE", "_ew_ensemble_rank")]:
        b = routed_book(d, col, None, 0)
        m = _test_mask(b["_net"])
        arms[name] = b["_net"][m]
    r["engine_routing"] = {
        "engine_choice_share": {
            ENGINES[i]: round(float((d.loc[ok, "_engine_choice"] == i).mean()), 4)
            for i in range(len(ENGINES))},
        "arms": {name: {"grade": beta_first(s, mkt)} for name, s in arms.items()},
        "single_engines": {e: {"grade": beta_first(base[e]["net"], mkt)} for e in ENGINES},
        "routed_vs_ew_ensemble": paired(arms["ROUTED_ENGINE"], arms["EW_ENSEMBLE"],
                                        "routed-engine minus EW rank ensemble"),
        "routed_vs_each_engine": {
            e: paired(arms["ROUTED_ENGINE"], base[e]["net"],
                      f"routed-engine minus {e}") for e in ENGINES},
        "note": "'better than the best engine picked afterwards' is not a claim; "
                "the EW rank ensemble is the honest comparator because it needs "
                "no choice at all",
    }

    # ---- what the router learned ----------------------------------------
    _log("feature importances of the primary router ...")
    import lightgbm as lgb
    from scripts.predictability_router_r1 import FEATURE_SETS, _month_to_int
    dd = d.copy()
    dd["u_c"] = dd[f"_u_{primary}"]
    dd["abs_u_c"] = dd["u_c"].abs()
    feats = [c for c in FEATURE_SETS["FS_A"] if c in dd.columns]
    mi = _month_to_int(dd["month"])
    tr = dd[(mi < 2024 * 12 - 2) & dd[f"lab__{primary}"].notna()]
    mdl = lgb.LGBMRegressor(n_estimators=300, learning_rate=0.05, num_leaves=31,
                            min_child_samples=200, subsample=0.8, subsample_freq=1,
                            colsample_bytree=0.8, reg_lambda=1.0,
                            random_state=SEED, n_jobs=4, verbose=-1)
    mdl.fit(tr[feats], tr[f"lab__{primary}"])
    imp = sorted(zip(feats, mdl.feature_importances_.tolist()),
                 key=lambda kv: -kv[1])
    r["primary_router_gain_importance_last_fold"] = [
        {"feature": f, "split_importance": int(v)} for f, v in imp]

    # ---- the trap, from the other direction ------------------------------
    _log("trap: what the router score IS ...")
    corr = {}
    for c in TRAP_COLS + ["abs_u_c", "engine_disagree", "ins_activity_90d",
                          "attention_z", "dispersion"]:
        if c not in dd.columns:
            continue
        sub = dd[[f"score__{primary}", c]].dropna()
        if len(sub) > 1000:
            corr[c] = round(float(stats.spearmanr(
                sub[f"score__{primary}"], sub[c]).statistic), 4)
    r["router_score_is"] = corr

    # ---- the family, restated with stage two's cells charged --------------
    pv = {}
    for e in ENGINES:
        p = r["inverse_arm"][e]["vs_always_trade"].get("p_two_sided")
        if p is not None:
            pv[f"INVERSE::{e}"] = p
    p = r["engine_routing"]["routed_vs_ew_ensemble"].get("p_two_sided")
    if p is not None:
        pv["ROUTED_ENGINE_vs_EW"] = p
    for e in ENGINES:
        p = r["decile_tables"][e].get("top_minus_bottom_p_two_sided")
        if p is not None:
            pv[f"DECILE_TB::{e}"] = p
    r["stage2_multiplicity"] = {
        "cells_charged_here": len(pv),
        "family_max_p": round(max(pv.values()), 5) if pv else None,
        "holm_export": holm(pv),
        "bh_fdr_screen_q10": bh_fdr(pv, 0.10),
        "note": "stage two's cells are charged separately and the report adds "
                "both counts; the roadmap's invariant 16 charges every cell "
                "LOOKED AT, not every cell published",
    }

    # ---- three eras on the decile top-minus-bottom of the primary --------
    _log("eras on the primary decile spread ...")
    lab = f"lab__{primary}"
    sub = d[["month", f"score__{primary}", lab]].dropna()
    tb = {}
    for m, ch in sub.groupby("month", observed=True):
        if len(ch) < 200:
            continue
        q = pd.qcut(ch[f"score__{primary}"].rank(method="first"), 10, labels=False)
        mm = ch.groupby(q)[lab].mean()
        if 0 in mm.index and 9 in mm.index:
            tb[str(m)] = float(mm.loc[9] - mm.loc[0])
    tbs = pd.Series(tb).sort_index()
    r["primary_decile_spread_by_era"] = {}
    for name, seg in era_slice(tbs).items():
        t = float(seg.mean() / (seg.std(ddof=1) / np.sqrt(len(seg)))) if seg.std() > 0 else None
        r["primary_decile_spread_by_era"][name] = {
            "months": int(len(seg)), "mean": round(float(seg.mean()), 5),
            "t": round(t, 3) if t is not None else None,
            "mde_80pct": round(float(2.802 * seg.std(ddof=1) / np.sqrt(len(seg))), 5),
        }
    r["eras_declared"] = ROUTER_ERAS

    r["runtime_seconds"] = round(time.time() - t0, 1)
    p2 = OUT / "R1_router_stage2_receipt.json"
    p2.write_text(json.dumps(r, indent=1, default=str), encoding="utf-8")
    _log(f"receipt -> {p2}")


if __name__ == "__main__":
    main()
