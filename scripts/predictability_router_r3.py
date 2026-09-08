"""R1 stage three -- WHERE the forecastable predictability actually lives.

Stage two found the two halves of the result pointing opposite ways:

  * the router's decile table is strongly monotone (top-minus-bottom realised IC
    contribution +0.374, t 9.5, in all three eras) -- predictability IS
    forecastable;
  * routing a long-only top-50 book on it does not beat always trading, in 36
    cells out of 36.

There is a mechanical explanation for both at once, and it has to be tested
rather than asserted.  The cell label is `12 * u_c * v_c`, so a name at the very
top or very bottom of the engine's ranking contributes a LARGE label whichever
way it goes, purely because |u_c| is large.  `abs_u_c` is the router's top
feature (split importance 740) and the router score's Spearman with `abs_u_c` is
+0.52.  If the forecastable part of the label is mostly that |u_c| term, then:

  - the decile table is real and means "extreme ranks carry more IC", and
  - it carries NO DECISION inside a top-50 book, because every name there is
    already at the extreme and |u_c| barely varies.

Three tests separate that from a genuine state-conditional skill:

  A  WITHIN-DECILE RANK IC.  Inside each predicted-skill decile, the ordinary
     Spearman of the engine's prediction against the realised excess return.
     This is scale-free: it cannot be inflated by |u_c|.  If the top decile
     still has the higher IC, the router found skill; if the table flattens, the
     router found rank extremity.

  B  THE TRADED REGION.  The same decile table computed only over the cells the
     book can actually buy (the top 50 by engine rank each month), where |u_c|
     is nearly constant.  This is the question the book asks.

  C  A STATE-ONLY ROUTER.  FS_S drops `u_c` AND `abs_u_c`, so no rank term can
     enter at all.  Whatever skill survives there is state, by construction.

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
    BOOK_K, ENGINES, FEATURE_SETS, FS_A_STATE, OUT, ROUTER_ERAS,
    TEST_START_YEAR, _log, beta_first, bh_fdr, build_panel, era_slice,
    fit_router, holm, paired, routed_book,
)
from scripts.predictability_router_r2 import decile_table, get_scores, _test_mask

#: State only.  No `u_c`, no `abs_u_c`: no rank term can enter.
FS_S = [c for c in FS_A_STATE if c != "abs_u_c"]
#: And without the cross-engine rank dispersion either, which is still a
#: statement about rankings rather than about the world.
FS_S0 = [c for c in FS_S if c != "engine_disagree"]
FEATURE_SETS["FS_S"] = FS_S
FEATURE_SETS["FS_S0"] = FS_S0


def within_decile_ic(d: pd.DataFrame, engine: str, score_col: str,
                     n_bins: int = 10, min_names: int = 40) -> dict:
    """Ordinary Spearman IC INSIDE each decile of predicted skill.

    Scale-free, so `|u_c|` cannot inflate it.  n is MONTHS.
    """
    sub = d[["month", engine, score_col, "excess_vw_1m"]].dropna()
    per: dict[int, list[float]] = {i: [] for i in range(n_bins)}
    spread = []
    for _m, ch in sub.groupby("month", observed=True):
        if len(ch) < n_bins * min_names:
            continue
        q = pd.qcut(ch[score_col].rank(method="first"), n_bins, labels=False)
        vals = {}
        for i in range(n_bins):
            g = ch[q == i]
            if len(g) < min_names or g[engine].nunique() < 2:
                continue
            rho = stats.spearmanr(g[engine], g["excess_vw_1m"]).statistic
            if np.isfinite(rho):
                per[i].append(float(rho))
                vals[i] = float(rho)
        if 0 in vals and n_bins - 1 in vals:
            spread.append(vals[n_bins - 1] - vals[0])
    rows = []
    for i in range(n_bins):
        s = pd.Series(per[i])
        t = (float(s.mean() / (s.std(ddof=1) / np.sqrt(len(s))))
             if len(s) > 2 and s.std() > 0 else None)
        rows.append({"decile": i + 1, "months": int(len(s)),
                     "mean_within_group_rank_ic": round(float(s.mean()), 5),
                     "t_across_months": round(t, 3) if t is not None else None})
    sp = pd.Series(spread)
    t_sp = (float(sp.mean() / (sp.std(ddof=1) / np.sqrt(len(sp))))
            if len(sp) > 2 and sp.std() > 0 else None)
    means = [r["mean_within_group_rank_ic"] for r in rows]
    return {
        "n_bins": n_bins, "months": int(len(sp)), "deciles": rows,
        "top_minus_bottom": round(float(sp.mean()), 5),
        "top_minus_bottom_t": round(t_sp, 3) if t_sp is not None else None,
        "top_minus_bottom_p_two_sided":
            round(float(2 * stats.t.sf(abs(t_sp), len(sp) - 1)), 5) if t_sp else None,
        "mde_top_minus_bottom_80pct": round(
            float(2.802 * sp.std(ddof=1) / np.sqrt(len(sp))), 5) if len(sp) > 2 else None,
        "spearman_decile_vs_realised": round(
            float(stats.spearmanr(np.arange(n_bins), means).statistic), 4),
    }


def traded_region(d: pd.DataFrame, engine: str, k: int = BOOK_K) -> pd.DataFrame:
    """The cells the long-only book can actually buy: top k by engine rank."""
    keep = []
    for _m, ch in d.groupby("month", sort=True, observed=True):
        keep.append(ch.nlargest(k, engine).index)
    return d.loc[np.concatenate([np.asarray(x) for x in keep])]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bins-traded", type=int, default=5,
                    help="the traded region is 50 names a month; 10 bins would "
                         "be 5 names a bin and the IC would be noise")
    ap.parse_args()
    t0 = time.time()
    d = build_panel()
    sc = get_scores(d)
    for c in sc.columns:
        d[c] = sc[c].to_numpy()

    primary = "lgbm_clf__1m"
    r: dict = {
        "lane": "R1_PREDICTABILITY_ROUTER_STAGE_3",
        "licence": "PRODUCT_EXPERIMENT",
        "generated_utc": pd.Timestamp.utcnow().isoformat(),
        "primary_engine": primary,
        "asks": "is the forecastable part of the label the mechanical rank-"
                "extremity term |u_c|, and does anything survive inside the "
                "region a long-only book can buy?",
        "eras_declared": ROUTER_ERAS,
    }

    # ---- A: within-decile rank IC over the whole cross-section -----------
    _log("A: within-decile rank IC (scale-free) ...")
    r["A_within_decile_rank_ic_full_cross_section"] = {
        e: within_decile_ic(d, e, f"score__{e}") for e in ENGINES}

    # ---- the same table for |u_c| ALONE, the mechanical comparator -------
    _log("A2: the same table scored by |u_c| alone ...")
    r["A2_scored_by_abs_rank_alone"] = {}
    for e in ENGINES:
        dd = d.copy()
        dd["_absu"] = dd[f"_u_{e}"].abs()
        r["A2_scored_by_abs_rank_alone"][e] = {
            "label_decile_table": decile_table(dd, e, "_absu"),
            "within_decile_rank_ic": within_decile_ic(dd, e, "_absu"),
        }

    # ---- B: the traded region --------------------------------------------
    _log("B: the traded region (top-50 by engine) ...")
    r["B_traded_region"] = {}
    for e in ENGINES:
        tr = traded_region(d, e)
        nb = 5
        lab = f"lab__{e}"
        sub = tr[["month", f"score__{e}", lab, e, "excess_vw_1m"]].dropna()
        per: dict[int, list[float]] = {i: [] for i in range(nb)}
        spread, ex_spread = [], []
        per_ex: dict[int, list[float]] = {i: [] for i in range(nb)}
        for _m, ch in sub.groupby("month", observed=True):
            if len(ch) < nb * 5:
                continue
            q = pd.qcut(ch[f"score__{e}"].rank(method="first"), nb, labels=False)
            m_lab = ch.groupby(q)[lab].mean()
            m_ex = ch.groupby(q)["excess_vw_1m"].mean()
            for i in range(nb):
                if i in m_lab.index:
                    per[i].append(float(m_lab.loc[i]))
                    per_ex[i].append(float(m_ex.loc[i]))
            if 0 in m_lab.index and nb - 1 in m_lab.index:
                spread.append(float(m_lab.loc[nb - 1] - m_lab.loc[0]))
                ex_spread.append(float(m_ex.loc[nb - 1] - m_ex.loc[0]))
        rows = []
        for i in range(nb):
            s, sx = pd.Series(per[i]), pd.Series(per_ex[i])
            rows.append({
                "bin": i + 1, "months": int(len(s)),
                "mean_realised_ic_contribution": round(float(s.mean()), 5),
                "mean_realised_excess_return": round(float(sx.mean()), 5),
                "t_excess_across_months": round(
                    float(sx.mean() / (sx.std(ddof=1) / np.sqrt(len(sx)))), 3)
                if len(sx) > 2 and sx.std() > 0 else None,
            })
        sp, spx = pd.Series(spread), pd.Series(ex_spread)
        t_sp = float(sp.mean() / (sp.std(ddof=1) / np.sqrt(len(sp)))) if len(sp) > 2 else None
        t_x = float(spx.mean() / (spx.std(ddof=1) / np.sqrt(len(spx)))) if len(spx) > 2 else None
        r["B_traded_region"][e] = {
            "bins": nb, "months": int(len(sp)),
            "names_per_month": BOOK_K,
            "abs_u_c_sd_inside_region": round(
                float(tr[f"_u_{e}"].abs().std()), 5),
            "abs_u_c_sd_full_cross_section": round(
                float(d[f"_u_{e}"].abs().std()), 5),
            "table": rows,
            "top_minus_bottom_label": round(float(sp.mean()), 5),
            "top_minus_bottom_label_t": round(t_sp, 3) if t_sp else None,
            "top_minus_bottom_excess_return": round(float(spx.mean()), 5),
            "top_minus_bottom_excess_return_t": round(t_x, 3) if t_x else None,
            "top_minus_bottom_excess_return_p":
                round(float(2 * stats.t.sf(abs(t_x), len(spx) - 1)), 5) if t_x else None,
            "mde_excess_return_80pct": round(
                float(2.802 * spx.std(ddof=1) / np.sqrt(len(spx))), 5) if len(spx) > 2 else None,
            "note": "the EXCESS RETURN column is the one the book spends: a "
                    "monotone label column with a flat excess column means the "
                    "router sorted rank extremity, not money",
        }

    # ---- C: the state-only router ----------------------------------------
    _log("C: state-only routers (no u_c, no abs_u_c) ...")
    r["C_state_only"] = {}
    dd = d.copy()
    dd["u_c"] = dd[f"_u_{primary}"]
    dd["abs_u_c"] = dd["u_c"].abs()
    for fs in ["FS_S", "FS_S0"]:
        _log(f"  fitting {fs} ...")
        s = fit_router(dd, primary, fs)
        col = f"_score_{fs}"
        d2 = d.copy()
        d2[col] = s.to_numpy()
        cors = []
        mm = d2[["month", col, f"lab__{primary}"]].dropna()
        for _m, ch in mm.groupby("month", observed=True):
            if len(ch) >= 50 and ch[col].nunique() > 2:
                cors.append(float(stats.spearmanr(ch[col], ch[f"lab__{primary}"]).statistic))
        cs = pd.Series(cors)
        b = routed_book(d2, primary, col, int(round(0.30 * BOOK_K)))
        m = _test_mask(b["_net"])
        net = b["_net"][m]
        base = routed_book(d2, primary, None, 0)
        mb = _test_mask(base["_net"])
        always, mkt = base["_net"][mb], base["_market"][mb]
        sub = d2[[col]].assign(abs_u_c=d2[f"_u_{primary}"].abs()).dropna()
        r["C_state_only"][fs] = {
            "features": FEATURE_SETS[fs],
            "months": int(len(cs)),
            "mean_xs_spearman_score_vs_label": round(float(cs.mean()), 5),
            "t_across_months": round(float(cs.mean() / (cs.std(ddof=1) / np.sqrt(len(cs)))), 3)
            if len(cs) > 2 and cs.std() > 0 else None,
            "spearman_score_vs_abs_u_c": round(float(stats.spearmanr(
                sub[col], sub["abs_u_c"]).statistic), 4),
            "label_decile_table": decile_table(d2, primary, col),
            "within_decile_rank_ic": within_decile_ic(d2, primary, col),
            "abstention_book_q30": {
                "grade": beta_first(net, mkt),
                "vs_always_trade": paired(net, always, f"{fs} routed q30 minus always"),
            },
        }

    # ---- the family charged here ------------------------------------------
    pv = {}
    for e in ENGINES:
        p = r["A_within_decile_rank_ic_full_cross_section"][e]["top_minus_bottom_p_two_sided"]
        if p is not None:
            pv[f"A_WITHIN_IC::{e}"] = p
        p = r["B_traded_region"][e]["top_minus_bottom_excess_return_p"]
        if p is not None:
            pv[f"B_TRADED_EXCESS::{e}"] = p
    for fs in ["FS_S", "FS_S0"]:
        p = r["C_state_only"][fs]["abstention_book_q30"]["vs_always_trade"].get("p_two_sided")
        if p is not None:
            pv[f"C_BOOK::{fs}"] = p
    r["stage3_multiplicity"] = {
        "cells_charged_here": len(pv),
        "family_max_p": round(max(pv.values()), 5) if pv else None,
        "holm_export": holm(pv), "bh_fdr_screen_q10": bh_fdr(pv, 0.10)}

    # ---- eras on the decisive number: traded-region excess spread ---------
    _log("eras on the traded-region excess spread ...")
    tr = traded_region(d, primary)
    nb = 5
    per_m = {}
    for m, ch in tr.groupby("month", observed=True):
        sub = ch[[f"score__{primary}", "excess_vw_1m"]].dropna()
        if len(sub) < nb * 5:
            continue
        q = pd.qcut(sub[f"score__{primary}"].rank(method="first"), nb, labels=False)
        mm = sub.groupby(q)["excess_vw_1m"].mean()
        if 0 in mm.index and nb - 1 in mm.index:
            per_m[str(m)] = float(mm.loc[nb - 1] - mm.loc[0])
    ser = pd.Series(per_m).sort_index()
    r["traded_region_excess_spread_by_era"] = {}
    for name, seg in era_slice(ser).items():
        t = float(seg.mean() / (seg.std(ddof=1) / np.sqrt(len(seg)))) if seg.std() > 0 else None
        r["traded_region_excess_spread_by_era"][name] = {
            "months": int(len(seg)), "mean_monthly": round(float(seg.mean()), 5),
            "annualised": round(float(seg.mean()) * 12, 4),
            "t": round(t, 3) if t is not None else None,
            "mde_annualised_80pct": round(
                float(2.802 * seg.std(ddof=1) / np.sqrt(len(seg)) * 12), 4)}

    r["runtime_seconds"] = round(time.time() - t0, 1)
    p3 = OUT / "R1_router_stage3_receipt.json"
    p3.write_text(json.dumps(r, indent=1, default=str), encoding="utf-8")
    _log(f"receipt -> {p3}")


if __name__ == "__main__":
    main()
