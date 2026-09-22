"""Do FUNDAMENTALS carry more amplitude than price/volume? The night's one question.

WHY THIS JOB EXISTS
===================
`NEGATIVE_RESULTS.md` §59 (2026-09-22) closed the price/volume feature family at
a 21-session horizon, and closed it with an unusually precise sentence:

    The ordering carries a REAL signal -- IC +0.0227 at t +7.56 over 122
    month-blocks -- worth about +0.28% gross per 21 sessions, earned in names
    whose round trip costs ~35 bps. The edge is 28 bps and the toll is 35.
    Raising the liquidity floor to $50M collapses it to gross -0.18%, because
    the edge IS the illiquidity.

So the next move is an input with more AMPLITUDE, not a cheaper execution or a
bigger model. The obvious candidate is fundamentals: this repo's one near-miss
picker, `profitability_small`, is fundamental (net +5.11%, t 2.78, Holm 0.065 at
126 sessions).

But building a CURRENT fundamental vintage is a real data job -- FMP, ticker
mapping, PIT discipline, several days. **This job decides whether that job is
worth doing, using data already on disk**, and it is the cheapest possible way
to find out.

THE PANEL, AND WHY IT ANSWERS THE QUESTION WITHOUT A TICKER
===========================================================
`backend/data/optimus/aegis_panel/aegis_panel_v2.parquet` -- 4,157,680 rows,
444 columns, 1926-2024, one row per (permno, month-end). It carries
`ret_exc_lead1m`, the forward one-month excess return, ALREADY COMPUTED, plus
both price-derived factors (`ret_12_1`, `rvol_252d`, ...) and fundamental ones
(`gp_at`, `ope_be`, `be_me`, `at_gr1`, ...).

It has **no ticker column**, so it cannot be joined to the live Alpaca book and
cannot itself trade. That does not matter here. The question is not "what do I
buy tonight" but "is there enough amplitude in fundamentals to justify buying a
current vintage", and a self-contained panel answers that perfectly.

WHAT IS COMPARED, AND THE ONE RULE
==================================
Three feature sets, same model, same folds, same purge:

    price        what §59 already measured, reproduced here at 1m so the
                 comparison is like-for-like
    fundamental  accounting only
    both         the actual question: does adding fundamentals RAISE the gross
                 edge above the cost floor price/volume could not clear?

`price` is the CONTROL and it is not optional. Without it a positive
`fundamental` number would be unreadable: this panel, this horizon and this
period are all different from §59's, so an improvement must be measured against
price-only ON THE SAME PANEL or it measures the panel change instead.

THE BAR
=======
A monthly strategy pays its round trip every month. §59's measured costs run
6-35 bps depending on liquidity band. `COST_FLOOR_BPS` is the bar the combined
gross spread must clear to make the FMP vintage worth building -- and clearing
it here is NOT a claim that it will clear it live. Different universe, monthly
rebalance, no live fills. This job answers one question: GO or NO-GO on the
data work.

Licence: `PRODUCT_EXPERIMENT`. No significance gate. $0.00 -- no model is called.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _cfg                      # noqa: E402

PANEL = _cfg.OPTIMUS_LEDGER_DIR / "aegis_panel" / "aegis_panel_v2.parquet"
OUT = _cfg.OPTIMUS_LEDGER_DIR / "xs_ranker"

TARGET = "ret_exc_lead1m"
#: One month of purge between train and test. The target is non-overlapping at
#: monthly frequency, so one month is the whole overlap -- unlike the 21-session
#: daily case, where 21 sessions of labels overlap and the purge had to match.
PURGE_MONTHS = 1

#: Below this the names are not investable at any size a retail paper account
#: would take, and including them is how a factor study reports a return nobody
#: could have earned. JKP's own size groups; `nano` and `micro` are excluded.
KEEP_SIZE_GROUPS = ("mega", "large", "small")

#: The bar the combined gross monthly spread must clear for the FMP data work to
#: be worth doing. §59 measured 6-35 bps round trip by liquidity band; 20 bps is
#: the mid-band figure and a deliberately unkind bar for a MONTHLY rebalance.
COST_FLOOR_BPS = 20.0

PRICE_FEATURES = (
    "ret_1_0", "ret_3_1", "ret_6_1", "ret_12_1", "ret_12_7",
    "rvol_252d", "rvol_21d", "rmax5_rvol_21d", "rvolhl_21d",
    "turnover_126d", "dolvol_126d", "market_equity", "beta_60m",
    "prc_highprc_252d", "ivol_capm_252d",
)
FUNDAMENTAL_FEATURES = (
    "gp_at", "cop_at", "ope_be", "ni_be", "ebit_sale", "at_gr1", "sale_gr1",
    "be_me", "at_me", "sale_me", "debt_at", "netdebt_me", "noa_at",
    "cash_at", "ocf_at", "capx_gr1", "inv_gr1a", "eqnpo_12m", "ni_inc8q",
    "f_score", "o_score", "z_score", "qmj", "qmj_prof", "qmj_growth",
)

LGB_PARAMS = {
    "objective": "regression", "metric": "l2", "learning_rate": 0.04,
    "num_leaves": 31, "min_child_samples": 200, "feature_fraction": 0.8,
    "bagging_fraction": 0.8, "bagging_freq": 1, "lambda_l2": 5.0,
    "n_estimators": 300, "verbose": -1,
}


def load(start: str = "2005-01-01") -> tuple[pd.DataFrame, dict]:
    """US common stock, investable size groups, from `start`. Reports what it dropped."""
    import pyarrow.parquet as pq
    f = pq.ParquetFile(PANEL)
    have = set(f.schema.names)
    want = (["eom", "permno", "excntry", "size_grp", TARGET]
            + [c for c in PRICE_FEATURES + FUNDAMENTAL_FEATURES if c in have])
    missing = [c for c in PRICE_FEATURES + FUNDAMENTAL_FEATURES if c not in have]
    df = pd.read_parquet(PANEL, columns=sorted(set(want)))
    n0 = len(df)
    df = df[(df["excntry"] == "USA") & (df["eom"] >= pd.Timestamp(start))]
    df = df[df["size_grp"].isin(KEEP_SIZE_GROUPS)]
    df = df[df[TARGET].notna()]
    meta = {
        "panel": str(PANEL), "rows_total": int(n0), "rows_kept": int(len(df)),
        "start": start, "size_groups_kept": list(KEEP_SIZE_GROUPS),
        "months": int(df["eom"].nunique()),
        "first": str(df["eom"].min().date()), "last": str(df["eom"].max().date()),
        "features_absent_from_this_vintage": missing,
    }
    return df, meta


def folds(months: np.ndarray, n_folds: int = 5, min_train_frac: float = 0.45):
    m = np.sort(np.unique(months))
    start = int(len(m) * min_train_frac)
    span = (len(m) - start) // n_folds
    out = []
    for k in range(n_folds):
        tr_end = start + k * span
        te_start = tr_end + PURGE_MONTHS
        te_end = start + (k + 1) * span if k < n_folds - 1 else len(m) - 1
        if te_start < te_end:
            out.append((m[tr_end], m[te_start], m[te_end]))
    return out


def _spread(oos: pd.DataFrame, k: int) -> dict:
    """Top-k equal-weight vs the month's cross-section, per month, GROSS."""
    rows = []
    for d, g in oos.groupby("eom"):
        if len(g) < k * 3:
            continue
        top = g.nlargest(k, "score")
        rows.append({"eom": d, "spread": float(top[TARGET].mean() - g[TARGET].mean())})
    if not rows:
        return {"status": "REFUSED", "why": f"no month carried {k*3} names"}
    s = pd.Series([r["spread"] for r in rows])
    se = s.std(ddof=1) / math.sqrt(len(s))
    return {"k": k, "n_months": len(s), "gross_spread_pct": float(s.mean() * 100),
            "t": float(s.mean() / se) if se > 0 else None,
            "hit_rate": float((s > 0).mean()),
            "gross_spread_bps": float(s.mean() * 10_000)}


def run(df: pd.DataFrame, *, n_folds: int = 5, ks=(20, 50, 100)) -> dict:
    import lightgbm as lgb

    have = set(df.columns)
    sets = {
        "price": [c for c in PRICE_FEATURES if c in have],
        "fundamental": [c for c in FUNDAMENTAL_FEATURES if c in have],
        "both": [c for c in PRICE_FEATURES + FUNDAMENTAL_FEATURES if c in have],
    }
    df = df.copy()
    df["y"] = df.groupby("eom")[TARGET].rank(pct=True)

    fl = folds(df["eom"].values, n_folds=n_folds)
    results, fold_log = {}, []
    preds = {name: [] for name in sets}

    for tr_end, te_start, te_end in fl:
        tr = df[df["eom"] <= tr_end]
        te = df[(df["eom"] >= te_start) & (df["eom"] <= te_end)]
        if len(tr) < 20_000 or te.empty:
            fold_log.append({"train_end": str(pd.Timestamp(tr_end).date()),
                             "refused": f"train {len(tr):,} / test {len(te):,}"})
            continue
        fold_log.append({"train_end": str(pd.Timestamp(tr_end).date()),
                         "test": f"{pd.Timestamp(te_start).date()}..{pd.Timestamp(te_end).date()}",
                         "n_train": int(len(tr)), "n_test": int(len(te))})
        for name, feats in sets.items():
            m = lgb.LGBMRegressor(**LGB_PARAMS)
            m.fit(tr[feats], tr["y"])
            p = te[["eom", "permno", TARGET]].copy()
            p["score"] = m.predict(te[feats])
            preds[name].append(p)

    for name, frames in preds.items():
        if not frames:
            results[name] = {"status": "REFUSED", "why": "no fold produced predictions"}
            continue
        oos = pd.concat(frames, ignore_index=True)
        per_month = (oos.groupby("eom")
                     .apply(lambda g: g["score"].corr(g[TARGET], method="spearman"),
                            include_groups=False).dropna())
        se = per_month.std(ddof=1) / math.sqrt(len(per_month)) if len(per_month) > 1 else float("nan")
        results[name] = {
            "n_features": len(sets[name]), "features": sets[name],
            "ic_mean": float(per_month.mean()),
            "ic_t": float(per_month.mean() / se) if se and se > 0 else None,
            "ic_n_months": int(len(per_month)),
            "by_k": {k: _spread(oos, k) for k in ks},
        }

    return {"receipt": "fundamental_amplitude", "licence": "PRODUCT_EXPERIMENT",
            "llm_spend_usd": 0.0, "target": TARGET, "purge_months": PURGE_MONTHS,
            "cost_floor_bps": COST_FLOOR_BPS, "folds": fold_log, "results": results,
            "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def verdict(res: dict) -> str:
    r = res["results"]
    if any(v.get("status") == "REFUSED" for v in r.values()):
        return "CANNOT DETERMINE: a feature set produced no out-of-sample months"
    # Read the WEAKEST cell of each set, not its best. A set whose edge depends
    # on which k you picked has not shown an edge -- it has shown a spread of
    # outcomes with a flattering maximum. This function's first version took
    # max() over `both` alone and returned NO-GO on a run where `fundamental`
    # cleared the bar by 2x at every single k.
    def cells(n):
        return [c.get("gross_spread_bps") for c in r[n]["by_k"].values()
                if isinstance(c, dict) and c.get("gross_spread_bps") is not None]

    worst = {n: min(cells(n)) for n in r}
    best = {n: max(cells(n)) for n in r}
    champ = max(worst, key=worst.get)
    w, b = worst[champ], best[champ]
    spread_note = (f"{champ} holds {w:.1f}-{b:.1f} bps across k=20/50/100 "
                   f"(IC {r[champ]['ic_mean']:+.4f}, t {r[champ]['ic_t']:+.2f}, "
                   f"{r[champ]['ic_n_months']} OOS months)")

    if w < COST_FLOOR_BPS:
        return (f"NO-GO: no feature set holds above the {COST_FLOOR_BPS:.0f} bps cost floor at "
                f"every book size. Best is {spread_note}. Look for a different input class.")

    lift = w - worst["price"]
    tail = ""
    if champ != "both" and worst["both"] < w:
        tail = (f" Note that `both` is WORSE ({worst['both']:.1f}-{best['both']:.1f} bps): "
                f"adding the price features DILUTES the fundamental signal, the same way "
                f"lgbm_full lost to lgbm_small in NEGATIVE_RESULTS.md §59. Ship the smaller "
                f"feature set.")
    return (f"GO: {spread_note}, clearing the {COST_FLOOR_BPS:.0f} bps floor at every k and "
            f"beating price-only ({worst['price']:.1f} bps worst-cell) by {lift:+.1f} bps on "
            f"the SAME panel.{tail} This is a GO on the DATA WORK -- building a current "
            f"fundamental vintage -- and NOT a claim the edge survives live: different "
            f"universe, monthly rebalance, no fills, and this panel ends 2024-12.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2005-01-01")
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)

    if not PANEL.exists():
        print(f"REFUSED: no factor panel at {PANEL}")
        return 2

    df, meta = load(a.start)
    print(f"panel: {meta['rows_kept']:,} rows, {meta['months']} months "
          f"({meta['first']}..{meta['last']}), size groups {meta['size_groups_kept']}")
    if meta["features_absent_from_this_vintage"]:
        print(f"absent from this vintage: {meta['features_absent_from_this_vintage']}")

    res = run(df, n_folds=a.folds)
    res["panel"] = meta
    res["verdict"] = verdict(res)

    OUT.mkdir(parents=True, exist_ok=True)
    out = Path(a.out) if a.out else OUT / f"fundamental_amplitude_{datetime.now().date()}.json"
    out.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")

    print(f"\n{'feature set':>12} {'nfeat':>6} {'IC':>8} {'IC t':>7}   "
          + "  ".join(f"k={k} bps" for k in (20, 50, 100)))
    print("-" * 72)
    for name, v in res["results"].items():
        if v.get("status"):
            print(f"{name:>12}  {v['status']}: {v.get('why')}"); continue
        cells = "  ".join(
            f"{(v['by_k'][k].get('gross_spread_bps') or float('nan')):>8.1f}"
            for k in (20, 50, 100))
        print(f"{name:>12} {v['n_features']:>6} {v['ic_mean']:+8.4f} "
              f"{(v['ic_t'] or float('nan')):+7.2f}  {cells}")
    print(f"\nVERDICT: {res['verdict']}")
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
