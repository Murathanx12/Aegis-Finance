"""The ranker bake-off — which way of ordering the cross-section actually works.

WHY A BAKE-OFF AND NOT A MODEL
==============================
The first `xs_ranker` fit (2026-09-22) came back with OOS IC **-0.0316, t -3.02**
and a top-20 book at **-4.30% relative per 21 sessions net**. Monotonically
backwards: the lowest-scored decile earned +1.44%, the highest -1.75%.

The univariate diagnostic said why. Of twenty-four features, exactly three carry
a sign worth anything over the 2025-26 panel:

    dollar_vol_log  IC -0.0341  t -2.90   (small beats large)
    amihud          IC +0.0292  t +2.37   (illiquid beats liquid - the same effect)
    skew_63         IC -0.0223  t -2.20   (low skew beats lottery tickets)

and every momentum feature is dead (t between -0.18 and +0.30), which
independently reproduces this repo's own standing verdict that `momentum_12_1`
is CLOSED.

A 350-tree GBM on twenty-four features, fitted over seven month-blocks, will
find whatever those three signals are doing in the training fold and mistake the
other twenty-one for information. That is not a model failure, it is a sample
size failure, and the correct response is to make the hypothesis space smaller
before making the model bigger.

WHAT IS COMPARED
================
* ``benchmark``  equal-weight of the eligible cross-section. The thing to beat.
* ``composite``  a signed z-score sum of the features that carry a univariate
                 sign, with the signs chosen ON THE TRAINING FOLD ONLY. No
                 fitted parameters at all, so there is nothing to overfit.
* ``lgbm_full``  every feature. The incumbent.
* ``lgbm_small`` only features whose training-fold |t| clears a bar.

THE RULE THAT MAKES THIS HONEST
===============================
Every choice a challenger makes - which features, which signs - is made inside
the training fold and then frozen before the test fold is touched. Choosing the
three features from the FULL-sample diagnostic above and then testing on the
same sample would be selection on the test set, and it would manufacture a
positive result out of nothing. `_train_fold_signs` therefore recomputes the
signs on each fold's own training rows, and the receipt prints them per fold so
a reader can see them move.

A negative bake-off is a RESULT, not a failure. `NEGATIVE_RESULTS.md` is where it
goes, and the live loop refuses to trade a measured-negative ranking on purpose.
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

from backend.services import xs_ranker as XR      # noqa: E402
from backend.services import fundamental_features as FF   # noqa: E402

OUT = REPO / "backend" / "data" / "optimus" / "xs_ranker"

#: A feature joins the composite only if its training-fold |t| across month
#: blocks clears this. Deliberately modest: the point is to exclude noise, not
#: to pass a significance test — this is a PRODUCT_EXPERIMENT.
COMPOSITE_MIN_T = 1.5

#: Book sizes swept on every model, so "does this signal pay?" is never answered
#: only at the one k somebody happened to pick.
BREADTH_K = (10, 20, 50, 100, 200, 300, 500)

#: A composite whose signs come from OUTSIDE this sample. On 2026-09-22 the
#: discovered composite chose nothing on any training fold — no feature cleared
#: COMPOSITE_MIN_T within a fold, even though three cleared it on the full
#: sample. That gap is the selection effect, and lowering the bar until a result
#: appears is how a programme fits its own test set.
#:
#: So this variant declares its signs from the published cross-sectional
#: literature BEFORE seeing any fold, and is tested as a stated hypothesis:
#:   - size: smaller names carry a higher expected return (so LOW dollar volume,
#:     HIGH Amihud illiquidity) — the oldest documented cross-sectional effect;
#:   - lottery/skew: high positively-skewed names are overpriced, so LOW skew
#:     carries the premium (the MAX effect);
#:   - short reversal: last week's winners give some back at a monthly horizon.
#: Each is a PRIOR, not a finding. If they fail here, that is a real negative
#: about this universe and it belongs in NEGATIVE_RESULTS.md.
PRIOR_SIGNS: dict[str, float] = {
    "dollar_vol_log": -1.0,
    "amihud": +1.0,
    "skew_63": -1.0,
    "rev_5": -1.0,
}


def _block(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s).dt.to_period("M").astype(str)


def _feature_t(d: pd.DataFrame, feat: str) -> tuple[float, float]:
    """Spearman IC per date, then a t across MONTH BLOCKS (CANON §58)."""
    per_date = (d.groupby("date")
                .apply(lambda g: g[feat].corr(g["fwd_rel"], method="spearman"),
                       include_groups=False)
                .dropna())
    if len(per_date) < 20:
        return float("nan"), float("nan")
    bm = per_date.groupby(_block(pd.Series(per_date.index))).mean()
    if len(bm) < 3:
        return float(per_date.mean()), float("nan")
    se = bm.std(ddof=1) / math.sqrt(len(bm))
    return float(per_date.mean()), (float(bm.mean() / se) if se > 0 else float("nan"))


def _train_fold_signs(train: pd.DataFrame, features) -> dict[str, dict]:
    """Which features carry a sign, decided on TRAINING rows only."""
    out = {}
    for f in features:
        ic, t = _feature_t(train, f)
        if np.isfinite(t) and abs(t) >= COMPOSITE_MIN_T:
            out[f] = {"sign": 1.0 if t > 0 else -1.0, "train_ic": ic, "train_t": t}
    return out


def _zscore_by_date(d: pd.DataFrame, feat: str) -> pd.Series:
    g = d.groupby("date")[feat]
    z = (d[feat] - g.transform("mean")) / g.transform("std")
    return z.clip(-3, 3)


def composite_score(test: pd.DataFrame, signs: dict[str, dict]) -> pd.Series:
    if not signs:
        return pd.Series(np.nan, index=test.index)
    parts = [ _zscore_by_date(test, f) * spec["sign"] for f, spec in signs.items() ]
    return pd.concat(parts, axis=1).mean(axis=1)


def run(panel: pd.DataFrame, *, n_folds: int = 4, book_size: int = 20) -> dict:
    import lightgbm as lgb

    fit = panel[panel["eligible"] & panel["y"].notna()].copy()
    folds = XR.make_folds(fit["date"].values, n_folds=n_folds)
    feats = list(XR.FEATURES)

    have_fund = [f for f in FF.FUNDAMENTAL_FEATURES if f in fit.columns]
    sets: dict[str, list[str]] = {}
    if have_fund:
        # The comparison the 2026-09-22 amplitude test authorised, run on OUR
        # universe and OUR horizon rather than on JKP's. `price` is the control
        # and is not optional: without it a positive `fundamental` number would
        # be unreadable, because the panel, horizon and period all differ from
        # the run that produced the 39 bps.
        sets["fundamental"] = have_fund
        sets["price_plus_fundamental"] = feats + have_fund
    preds: dict[str, list[pd.DataFrame]] = {"composite_prior": [], "composite": [],
                                            "lgbm_full": [], "lgbm_small": [],
                                            **{k: [] for k in sets}}
    fold_log = []

    for tr_end, te_start, te_end in folds:
        tr = fit[fit["date"] <= tr_end]
        te = fit[(fit["date"] >= te_start) & (fit["date"] <= te_end)]
        if len(tr) < XR.MIN_TRAIN_ROWS or te.empty:
            fold_log.append({"train_end": str(tr_end.date()), "refused":
                             f"train {len(tr):,} rows / test {len(te):,} rows"})
            continue

        signs = _train_fold_signs(tr, feats)
        base = te[["symbol", "date", "fwd_rel", "median_dollar_vol"]].copy()

        c = base.copy()
        c["score"] = composite_score(te, signs).values
        preds["composite"].append(c.dropna(subset=["score"]))

        # signs declared before the fold, from the literature, never from `tr`
        cp = base.copy()
        cp["score"] = composite_score(
            te, {f: {"sign": s_} for f, s_ in PRIOR_SIGNS.items()}).values
        preds["composite_prior"].append(cp.dropna(subset=["score"]))

        m_full = lgb.LGBMRegressor(**XR.LGB_PARAMS)
        m_full.fit(tr[feats], tr["y"])
        f_ = base.copy(); f_["score"] = m_full.predict(te[feats])
        preds["lgbm_full"].append(f_)

        # When no feature clears the bar inside the fold, fall back to the
        # PRIOR features rather than `feats[:3]` — which is alphabetical
        # accident (mom_21, mom_63, mom_126) and happens to be the momentum
        # block this repo has already closed.
        small = list(signs) or list(PRIOR_SIGNS)
        p_small = {**XR.LGB_PARAMS, "num_leaves": 15, "n_estimators": 200,
                   "min_child_samples": 400}
        m_small = lgb.LGBMRegressor(**p_small)
        m_small.fit(tr[small], tr["y"])
        s_ = base.copy(); s_["score"] = m_small.predict(te[small])
        preds["lgbm_small"].append(s_)

        for name, cols in sets.items():
            # A row with NO fundamental at all cannot be ranked by a
            # fundamental model. Dropping it here rather than imputing keeps
            # the missingness visible -- and `coverage` on the receipt says how
            # much of the cross-section that removed, because banks file
            # neither CostOfRevenue nor OperatingIncomeLoss and a silent drop
            # turns this into a bet against financials.
            tr_f = tr.dropna(subset=have_fund, how="all")
            te_f = te.dropna(subset=have_fund, how="all")
            if len(tr_f) < XR.MIN_TRAIN_ROWS or te_f.empty:
                continue
            m = lgb.LGBMRegressor(**XR.LGB_PARAMS)
            m.fit(tr_f[cols], tr_f["y"])
            f2 = te_f[["symbol", "date", "fwd_rel", "median_dollar_vol"]].copy()
            f2["score"] = m.predict(te_f[cols])
            preds[name].append(f2)

        fold_log.append({
            "train_end": str(tr_end.date()),
            "test": f"{te_start.date()}..{te_end.date()}",
            "n_train": int(len(tr)), "n_test": int(len(te)),
            "signs_chosen_on_train": {f: {"sign": v["sign"], "t": round(v["train_t"], 2)}
                                      for f, v in signs.items()},
        })

    results = {}
    for name, frames in preds.items():
        if not frames:
            results[name] = {"status": "REFUSED", "why": "no fold produced predictions"}
            continue
        oos = pd.concat(frames, ignore_index=True)
        if oos.empty:
            results[name] = {"status": "REFUSED", "why": (
                "no scored rows. For `composite` this means no feature cleared "
                f"COMPOSITE_MIN_T={COMPOSITE_MIN_T} on ANY training fold, so the "
                "composite had nothing to compose. That is a finding, not a bug: "
                "the features that look signed on the full sample do not survive "
                "being chosen inside a fold.")}
            continue
        oos["decile"] = oos.groupby("date")["score"].rank(pct=True).mul(10).astype(int).clip(0, 9)
        bt = XR.top_k_backtest(oos, k=book_size)
        ic = XR._information_coefficient(oos)
        dec = (oos.groupby("decile")["fwd_rel"].mean() * 100).round(2).to_dict()
        # BREADTH. A weak-but-real IC lives in the whole ordering, not in its
        # extreme tail: the top 20 of ~2,900 names is the 0.7% tail, where what
        # makes a name extreme is usually that it is tiny, volatile and thin.
        # 2026-09-22: lgbm_full carried IC +0.0198 (t +6.29) and a top-20 book
        # that LOST 0.42%. Sweeping k is how that contradiction is resolved.
        breadth = {}
        for k in BREADTH_K:
            b = XR.top_k_backtest(oos, k=k)
            if b.get("mean_net_rel_21d") is not None:
                breadth[k] = {"net": b["mean_net_rel_21d"], "gross": b["mean_gross_rel_21d"],
                              "t": b.get("t_across_blocks"), "hit": b["hit_rate_dates"],
                              "cost_bps": b["mean_cost_bps"], "n_dates": b["n_dates"]}
        results[name] = {**bt, **ic, "decile_mean_rel_pct": dec,
                         "breadth": breadth, "n_oos_rows": int(len(oos))}

    ranked = sorted(
        [(n, r) for n, r in results.items() if r.get("mean_net_rel_21d") is not None],
        key=lambda kv: -kv[1]["mean_net_rel_21d"])
    winner = ranked[0] if ranked else None

    return {
        "receipt": "xs_rank_bakeoff",
        "licence": "PRODUCT_EXPERIMENT",
        "llm_spend_usd": 0.0,
        "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "panel": {
            "rows": int(len(fit)),
            "decision_dates": int(fit["date"].nunique()),
            "month_blocks": int(_block(fit["date"]).nunique()),
            "first": str(fit["date"].min().date()), "last": str(fit["date"].max().date()),
            "symbols": int(fit["symbol"].nunique()),
        },
        "book_size": book_size,
        "folds": fold_log,
        "results": results,
        "winner": ({"model": winner[0],
                    "mean_net_rel_21d": winner[1]["mean_net_rel_21d"],
                    "t_across_blocks": winner[1].get("t_across_blocks")}
                   if winner else None),
        "verdict": _verdict(winner, results),
        "read_me_first": (
            "PRODUCT_EXPERIMENT. Feature signs are chosen on each fold's TRAINING "
            "rows and frozen before its test rows are scored. t is across month "
            "blocks, and overlapping 21-session windows still make it optimistic. "
            "This selects a ranker for PAPER deployment; it is not an alpha claim."),
    }


def _verdict(winner, results: dict) -> str:
    if not winner:
        return "CANNOT DETERMINE: no model produced an out-of-sample book"
    name, r = winner
    net = r["mean_net_rel_21d"]
    if net <= 0:
        # The breadth sweep usually carries the more useful sentence: whether
        # the signal is ABSENT or merely too small to pay its own costs. Those
        # are different findings and they point at different next moves.
        cells = [(n_, int(k), v["net"], v["gross"])
                 for n_, rr in results.items()
                 for k, v in (rr.get("breadth") or {}).items()]
        extra = ""
        if cells:
            bn, bk, bnet, bgross = max(cells, key=lambda x: x[2])
            bg_name, bg_k, _, bg = max(cells, key=lambda x: x[3])
            extra = (f" Widest read: {bn} at k={bk} nets {bnet*100:+.2f}%; the best GROSS "
                     f"cell is {bg_name} at k={bg_k} at {bg*100:+.2f}% before costs of "
                     f"~{r.get('mean_cost_bps', 0):.0f} bps. "
                     + ("The ordering carries a real but TINY edge that its own "
                        "transaction costs consume — so the next move is a signal with "
                        "more amplitude, not a cheaper execution."
                        if bg > 0 else
                        "Gross is negative at every book size, so there is no edge to "
                        "cheapen execution for."))
        return (f"ALL NEGATIVE: the best of {len(results)} rankers ({name}) still earned "
                f"{net*100:+.2f}% relative per 21 sessions net over {r.get('n_blocks')} "
                f"month-blocks. Price/volume alone does not rank this cross-section at "
                f"this horizon.{extra} The live loop must stay in observe; the next move "
                f"is another INPUT (fundamentals, revisions, typed news), not another model.")
    return (f"{name} earned {net*100:+.2f}% relative per 21 sessions net over "
            f"{r.get('n_blocks')} month-blocks (t {r.get('t_across_blocks')}, "
            f"IC {r.get('ic_mean')}). Tradeable under PRODUCT_EXPERIMENT.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bars", default=None, help="parquet to rank over (default: the 2025-26 panel)")
    ap.add_argument("--min-dollar-vol", type=float, default=None,
                    help="raise xs_ranker's liquidity floor. The 2026-09-22 "
                         "survivorship-free run found a real +0.28%/21d GROSS "
                         "edge that its own ~35bps small-cap round trip ate. "
                         "This asks the next question: does the ordering carry "
                         "anything in names that cost 6-10bps instead?")
    ap.add_argument("--with-fundamentals", action="store_true",
                    help="join the SEC PIT filing history onto the panel and add "
                         "the `fundamental` and `price_plus_fundamental` "
                         "challengers. The 2026-09-22 amplitude test measured "
                         "38.4-39.5 bps/month for this input class against a "
                         "20 bps floor; this is that test on OUR universe.")
    ap.add_argument("--survivorship-free", action="store_true",
                    help="rank over the deep panel PLUS the delisted names "
                         "(xs_ranker.survivorship_free_paths). The only honest "
                         "universe for a size/illiquidity ranking.")
    ap.add_argument("--folds", type=int, default=4)
    ap.add_argument("--book-size", type=int, default=20)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)

    if a.survivorship_free:
        paths = XR.survivorship_free_paths()
        print("panels: " + ", ".join(p.name for p in paths))
        bars = XR.load_bars(paths)
    else:
        bars = XR.load_bars(Path(a.bars) if a.bars else None)
    if a.min_dollar_vol:
        XR.MIN_MEDIAN_DOLLAR_VOL = a.min_dollar_vol
        print(f"liquidity floor raised to ${a.min_dollar_vol:,.0f} median daily dollar volume")
    audit = XR.survivorship_audit(bars)
    print(f"survivorship: {audit['verdict']}")
    panel = XR.build_panel(bars)
    cov = None
    if a.with_fundamentals:
        panel = FF.attach(panel)
        cov = FF.coverage(panel)
        print(f"fundamentals: any feature on {cov.get('any_fundamental', 0):.1%} of the "
              f"latest cross-section ({cov['n']:,} names), median filing age "
              f"{cov.get('median_age_days')} days")
        print(f"  gp_at {cov.get('gp_at', 0):.1%} · ope_be {cov.get('ope_be', 0):.1%} "
              f"· at_gr1 {cov.get('at_gr1', 0):.1%}")
    res = run(panel, n_folds=a.folds, book_size=a.book_size)
    res["survivorship"] = audit
    if cov is not None:
        res["fundamental_coverage"] = cov
    res["min_median_dollar_vol"] = XR.MIN_MEDIAN_DOLLAR_VOL

    OUT.mkdir(parents=True, exist_ok=True)
    out = Path(a.out) if a.out else OUT / f"bakeoff_{datetime.now().date()}.json"
    out.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")

    p = res["panel"]
    print(f"\npanel: {p['rows']:,} rows, {p['symbols']:,} symbols, "
          f"{p['decision_dates']} dates, {p['month_blocks']} month-blocks "
          f"({p['first']}..{p['last']})\n")
    print(f"{'model':>12} {'net/21d':>9} {'gross':>8} {'t(blk)':>7} {'IC':>8} {'ICt':>7} {'hit':>6}")
    print("-" * 62)
    for name, r in res["results"].items():
        if r.get("mean_net_rel_21d") is None:
            print(f"{name:>12}  {r.get('status')}: {r.get('why')}"); continue
        print(f"{name:>12} {r['mean_net_rel_21d']*100:+8.2f}% {r['mean_gross_rel_21d']*100:+7.2f}% "
              f"{(r.get('t_across_blocks') or float('nan')):+7.2f} {r['ic_mean']:+8.4f} "
              f"{(r.get('ic_t') or float('nan')):+7.2f} {r['hit_rate_dates']*100:5.0f}%")
    print("\nBREADTH — net relative % per 21 sessions by book size")
    ks = sorted({int(k) for r in res["results"].values()
                 for k in (r.get("breadth") or {})})
    if ks:
        print(f"{'model':>16} " + " ".join(f"  k={k:<5}" for k in ks))
        print("-" * (17 + 9 * len(ks)))
        for name, r in res["results"].items():
            b = {int(k): v for k, v in (r.get("breadth") or {}).items()}
            if not b:
                continue
            print(f"{name:>16} " + " ".join(
                f"{b[k]['net']*100:+7.2f}%" if k in b else "    --  " for k in ks))
            print(f"{'  (gross)':>16} " + " ".join(
                f"{b[k]['gross']*100:+7.2f}%" if k in b else "    --  " for k in ks))
        cells = [(n, k, v["net"], v["gross"], v.get("t"))
                 for n, r in res["results"].items()
                 for k, v in {int(k): v for k, v in (r.get("breadth") or {}).items()}.items()]
        best = max(cells, key=lambda x: x[2])
        res["best_breadth"] = {"model": best[0], "k": best[1], "net": best[2],
                               "gross": best[3], "t": best[4]}
        print(f"\nbest cell: {best[0]} at k={best[1]}: net {best[2]*100:+.2f}% "
              f"(gross {best[3]*100:+.2f}%), t {best[4]:+.2f}")
    print(f"\nVERDICT: {res['verdict']}")
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
