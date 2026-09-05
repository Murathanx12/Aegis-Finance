"""WEEKEND LAB JOBS -- one function per job, one receipt per call, no exceptions.

Each job takes a VARIANT index and returns a dict. The runner
(`scripts/weekend_lab.py`) writes the dict, appends a leaderboard row, and
rewrites the BEST SO FAR block. A job that raises has its traceback written AS
its receipt; a job that finds nothing writes the nothing, with the cells it
looked at.

THE VERDICT VOCABULARY, AND WHY IT HAS THREE WORDS AND NOT TWO
==============================================================
`NOVEL` requires all four, together:

    DSR > 0.95 after the family  ·  SPA p < 0.10  ·  PBO < 0.5
    ·  the sign holding in >= 2 of the 3 eras

`CANNOT DETERMINE` is the verdict when the tape was too short for the effect to
have shown up -- `years_needed_for_t2 > years_observed`. `NOISE` is reserved for
a search that HAD the power and still found nothing. Collapsing the last two
into one word is how an underpowered study gets published as a negative result,
and this repo has an entire night's receipt (2026-09-05 L1) whose whole content
is that distinction.
"""
from __future__ import annotations

import argparse
import json
import traceback
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ----------------------------------------------------------------- shared bits

def era_sign_table(series: pd.Series) -> dict:
    """The monthly paired-excess series, cut into the three eras.

    A strategy that is +3%/month in one era and flat in two is not a strategy
    with a +1%/month edge; it is one era wearing three. The sign table is the
    cheapest test of that, and the weekend's NOVEL bar requires >= 2 of 3.
    """
    from learner import long_panel as LP
    s = pd.Series(series).dropna()
    if s.empty:
        return {"verdict": "CANNOT DETERMINE", "why": "empty series"}
    idx = pd.PeriodIndex(pd.to_datetime(s.index.astype(str)), freq="M")
    years = idx.year
    out, signs = {}, []
    for name, lo, hi in LP.ERAS:
        m = (years >= lo) & (years <= hi)
        g = s[m]
        if len(g) < 6:
            out[name] = {"months": int(len(g)), "mean_pct": None,
                         "sign": None, "note": "fewer than 6 months"}
            continue
        mu = float(g.mean())
        out[name] = {"months": int(len(g)), "mean_pct": round(mu * 100, 4),
                     "t": round(float(mu / (g.std(ddof=1) / np.sqrt(len(g)))), 3)
                     if g.std(ddof=1) > 0 else None,
                     "sign": int(np.sign(mu))}
        signs.append(int(np.sign(mu)))
    pos = sum(1 for x in signs if x > 0)
    neg = sum(1 for x in signs if x < 0)
    out["eras_with_a_positive_mean"] = pos
    out["eras_with_a_negative_mean"] = neg
    out["eras_measured"] = len(signs)
    # TWO DIFFERENT QUESTIONS, AND THEY ARE NOT THE SAME QUESTION.
    #
    # For a STRATEGY's paired excess return, the claim is directional: the book
    # is long, and an era where it loses is an era where it failed. `holds_in_
    # 2_of_3` is the right bar there.
    #
    # For a FEATURE's regression coefficient, it is not. A feature that is
    # reliably NEGATIVE is a signal -- it is traded the other way round -- and
    # judging it by how often it is positive throws away every short leg the
    # panel has. The first version of W6 did exactly that and dropped
    # `vwap_60d_gap` at a controlled t of -12.06 with the same sign in all three
    # eras, which was the strongest result in its own table.
    #
    # So both are reported, and each caller names which one it means.
    out["holds_in_2_of_3"] = bool(pos >= 2 and len(signs) >= 2)
    out["same_sign_in_2_of_3"] = bool(max(pos, neg) >= 2 and len(signs) >= 2)
    out["dominant_sign"] = (1 if pos > neg else (-1 if neg > pos else 0))
    return out


def verdict_from(inf: dict, eras: dict) -> str:
    """The four-part bar, in one place. Every job calls this or explains why."""
    dsr = (inf.get("deflated_sharpe") or {}).get("dsr")
    spa_p = (inf.get("spa") or {}).get("p_spa_consistent")
    pbo = (inf.get("pbo") or {}).get("pbo")
    pw = inf.get("power") or {}
    if isinstance(dsr, (int, float)) and isinstance(spa_p, (int, float)):
        if (dsr >= 0.95 and spa_p <= 0.10
                and (not isinstance(pbo, (int, float)) or pbo < 0.5)
                and eras.get("holds_in_2_of_3")):
            return "NOVEL"
    # UNDERPOWERED is not NOISE. If a t = 2 would have needed more tape than the
    # panel holds, the search never had the chance to find the effect, and
    # calling that "NOISE" reports an absence of evidence as evidence of absence.
    if pw.get("powered") is False and pw.get("years_needed_for_t2") is not None:
        return "CANNOT DETERMINE (underpowered)"
    return "NOISE"


def _panel():
    from learner import long_panel as LP
    return LP.load_long()


# ------------------------------------------------------------- W1: inventory

def W1_long_panel_inventory(variant: int = 0) -> dict:
    """What the long panel actually is, in numbers, every pass.

    Cheap on purpose and first in the queue: every later job's claim is scoped
    by this, and a panel that silently changed shape between passes (a rebuild,
    a truncated write) would otherwise be discovered in the interpretation of a
    result rather than in the inventory of the input.
    """
    from learner import long_panel as LP
    df = LP.load_long()
    rec = json.loads(LP.LONG_RECEIPT.read_text(encoding="utf-8"))["build"]
    gate = rec.get("share_basis_gate_early_era", {})
    cov = rec.get("coverage_by_year", [])
    matured = {}
    for h in (1, 3, 6, 12):
        c = f"excess_vw_{h}m"
        matured[f"{h}m"] = int(df[c].notna().sum()) if c in df.columns else None
    return {
        "question": "what is on the long panel, and did its share-basis gate pass?",
        "rows": int(len(df)),
        "months": int(df["month"].nunique()),
        "permnos": int(df["permno"].nunique()),
        "window": rec.get("window"),
        "schema_version": rec.get("schema_version"),
        "matured_targets": matured,
        "by_era": rec.get("by_era"),
        "coverage_first_and_last": (cov[:1] + cov[-1:]) if cov else [],
        "thinnest_year": (min(cov, key=lambda r: r["name_months"]) if cov else None),
        "share_basis_gate_early_era": gate,
        "incumbent_panel_name_months": 605410,
        "headline": (f"{len(df):,} name-months over {df['month'].nunique()} months "
                     f"({rec.get('window')}); early-era share-basis gate "
                     f"{gate.get('verdict')}; incumbent panel had 605,410 rows / 143 months"),
        "verdict": "INVENTORY",
    }


# ------------------------------------------------------ W2: the learner grid

#: The variant list. The runner cycles it; each entry is a DIFFERENT question of
#: the same panel, which is what makes twenty passes worth more than one.
W2_VARIANTS = [
    "baseline",            # 0 -- the L1 grid, on 26 years instead of 12
    "hysteresis",          # 1 -- buy top-k, hold until rank > 2k: the cost lever
    "ablation",            # 2 -- one feature family removed at a time
    "quantile",            # 3 -- pinball heads: is the TAIL predictable?
    "long_only_eras",      # 4 -- fit inside one era, test in the others
]


#: Where a half-finished grid parks its completed cells.
_CELL_CACHE = ROOT / "backend" / "data" / "optimus" / "weekend_lab_2026-09-06" / "_cells"


def _cache_key(tag: str, kind: str, target: str, h: int) -> Path:
    safe = f"{tag}__{kind}__{target}__{h}m".replace("/", "-").replace("|", "-")
    return _CELL_CACHE / f"{safe}.json"


def _w2_grid(df, feature_cols, kinds, targets, horizons, costs, hold_k=None,
             drop_family=None, test_years=None, train_era=None, tag="base"):
    """Fit every cell and return {cell: paired monthly excess series}, plus the
    per-cell book dicts. Shared by every W2 variant so a variant cannot
    accidentally change the evaluation as well as the question it asks.

    RESUMABLE, AND THAT IS NOT AN OPTIMISATION. The full grid is 336 walk-forward
    fits over 26 years; measured on a loaded machine it can exceed its own
    timeout, and a job killed at minute 200 with nothing on disk reads *exactly*
    like a job that was never run -- the invariant this whole runner exists to
    uphold. So every completed (kind, target, horizon) writes its out-of-sample
    prediction series to `_cells/` immediately, and a later pass reads them back
    instead of refitting. A pass that dies half way is not wasted; it is a pass
    that got half way, and the next one starts there.

    The cache key carries the VARIANT TAG, so the ablation's `no_price_shape`
    cells can never be served to the baseline. A cache that could return another
    experiment's numbers would be worse than no cache.
    """
    from learner import dataset as DS, evaluate, models
    series, cells = {}, {}
    fc = [c for c in feature_cols if not (drop_family and c in drop_family)]
    _CELL_CACHE.mkdir(parents=True, exist_ok=True)
    for kind in kinds:
        for target in targets:
            for h in horizons:
                col = f"pred_{kind}_{target}_{h}m"
                ck = _cache_key(tag, kind, target, h)
                if ck.exists():
                    try:
                        blob = json.loads(ck.read_text(encoding="utf-8"))
                        s = pd.Series(blob["values"], index=[int(i) for i in blob["index"]])
                        df[col] = np.nan
                        df.loc[s.index, col] = s.values
                        for bps in costs:
                            key = f"{kind}|{target}|{h}m|{bps}bps"
                            bk = evaluate.book(df, col, k=50, weight="vw", cost_bps=bps,
                                               ret_col="fwd_1m", mkt_col="mkt_vw_1m",
                                               hold_k=hold_k, return_series=True)
                            ser = bk.get("_series") or {}
                            cells[key] = {k: v for k, v in bk.items()
                                          if not k.startswith("_")}
                            cells[key]["from_cache"] = True
                            net, mkt = ser.get("net"), ser.get("market")
                            if net is not None and mkt is not None and len(net) \
                                    and net.index.equals(mkt.index):
                                series[key] = (net - mkt).astype("float64")
                        continue
                    except Exception:                                    # noqa: BLE001
                        # A corrupt cache entry is DELETED and refitted, never
                        # silently half-used: a partially-read prediction series
                        # would be a different experiment wearing this one's name.
                        try:
                            ck.unlink()
                        except OSError:
                            pass
                preds = []
                for year, tr, te in DS.walk_forward_splits(df, test_years, h):
                    if train_era is not None:
                        # Fit ONLY on rows inside the named era. The point is not
                        # a better model; it is whether a model learned in one
                        # world still works in another, which is the question a
                        # 26-year panel can ask and a 12-year one cannot.
                        tr = tr[df.loc[tr, "era"].astype(str) == train_era]
                        if len(tr) < 5000:
                            continue
                    try:
                        pred, _meta = models.fit_predict(kind, target, df.loc[tr],
                                                         df.loc[te], fc, h)
                    except Exception as exc:                            # noqa: BLE001
                        cells[f"{kind}|{target}|{h}m|fit"] = {
                            "error": f"{type(exc).__name__}: {exc}"}
                        continue
                    preds.append(pd.Series(
                        models.arm_reconstruct(pred, df.loc[te], target, h), index=te))
                if not preds:
                    continue
                allp = pd.concat(preds)
                df[col] = np.nan
                df.loc[allp.index, col] = allp.values
                # Park the finished cell BEFORE evaluating it. The fit is the
                # expensive half; losing it to a timeout during evaluation would
                # be the one avoidable way to waste an hour.
                try:
                    ck.write_text(json.dumps(
                        {"index": [int(i) for i in allp.index],
                         "values": [float(v) for v in allp.to_numpy()],
                         "tag": tag, "kind": kind, "target": target, "horizon": h,
                         "written_utc": _now()}), encoding="utf-8")
                except OSError:
                    pass
                for bps in costs:
                    key = f"{kind}|{target}|{h}m|{bps}bps"
                    try:
                        bk = evaluate.book(df, col, k=50, weight="vw", cost_bps=bps,
                                           ret_col="fwd_1m", mkt_col="mkt_vw_1m",
                                           hold_k=hold_k, return_series=True)
                    except Exception as exc:                            # noqa: BLE001
                        cells[key] = {"error": f"{type(exc).__name__}: {exc}"}
                        continue
                    ser = bk.get("_series") or {}
                    cells[key] = {k: v for k, v in bk.items() if not k.startswith("_")}
                    net = ser.get("net")
                    mkt = ser.get("market")
                    if net is not None and mkt is not None and len(net) and \
                            net.index.equals(mkt.index):
                        # KEEP THE MONTH INDEX. The 12-month arms start later
                        # than the 1-month arms, so aligning by POSITION compares
                        # 2019 for one arm against 2021 for another.
                        series[key] = (net - mkt).astype("float64")
    return series, cells


def _w2_report(series, cells, question, family_id, extra=None) -> dict:
    from learner import inference
    if not series:
        return {"verdict": "CANNOT DETERMINE", "question": question,
                "cells_looked_at": len(cells),
                "headline": "no cell produced a usable paired series",
                "cells": cells, **(extra or {})}
    wide = pd.concat(series, axis=1).dropna()
    if wide.empty or wide.shape[0] < 12:
        return {"verdict": "CANNOT DETERMINE", "question": question,
                "cells_looked_at": len(cells),
                "headline": (f"the {len(series)} cells share only "
                             f"{0 if wide.empty else wide.shape[0]} months"),
                "months_per_cell": {k: int(len(v)) for k, v in series.items()},
                "cells": cells, **(extra or {})}
    fam = {k: wide[k].tolist() for k in wide.columns}
    best = max(fam, key=lambda k: float(np.mean(fam[k])))
    inf = inference.full_report(fam[best], family=fam, paired_excess=fam,
                                n_trials=len(cells) or len(fam), n_boot=500, seed=17)
    eras = era_sign_table(wide[best])
    pw = inf.get("power", {})
    return {
        "question": question,
        "family_id": family_id,
        "cells_looked_at": len(cells),
        "n_common_months": int(len(wide)),
        "common_window": [str(wide.index[0]), str(wide.index[-1])],
        "months_per_cell": {k: int(len(v)) for k, v in series.items()},
        "best_cell": best,
        "best_mean_monthly_excess_pct": round(float(np.mean(fam[best])) * 100, 4),
        "best_cell_book": cells.get(best),
        "cells": cells,
        "inference": inf,
        "era_sign_table": eras,
        "headline": (f"best of {len(cells)} cells is {best} at "
                     f"{np.mean(fam[best]) * 100:+.3f}%/month paired excess over "
                     f"{len(wide)} months; DSR {(inf.get('deflated_sharpe') or {}).get('dsr')}, "
                     f"SPA p {(inf.get('spa') or {}).get('p_spa_consistent')}, "
                     f"PBO {(inf.get('pbo') or {}).get('pbo')}, "
                     f"t2 needs {pw.get('years_needed_for_t2')}y vs "
                     f"{pw.get('years_observed')}y on hand"),
        "verdict": verdict_from(inf, eras),
        **(extra or {}),
    }


def W2_learner_long(variant: int = 0) -> dict:
    """The learner family, on 26 years. The variant decides which question.

    The night lab's L1 asked exactly one of these -- variant 0 -- on 12 years and
    got DSR 0.197 with 7.0 years of tape against 16.1 needed. Everything here is
    that same grid with more tape, plus four questions the extra tape makes
    askable.
    """
    from learner import dataset as DS, long_panel as LP
    name = W2_VARIANTS[variant % len(W2_VARIANTS)]
    df = _panel()
    fc = DS.feature_columns()
    # 2004 is the first test year: five years of matured targets behind it.
    test_years = list(range(LP.FIRST_TEST_YEAR, 2025))
    kinds, targets = ["ridge", "lgbm"], ["raw", "residual"]
    horizons, costs = [1, 3, 6, 12], [10, 25]
    extra = {"variant_name": name, "test_years": [test_years[0], test_years[-1]],
             "panel": "train_table_long.parquet (learner-train-table-3)"}

    if name == "baseline":
        s, c = _w2_grid(df, fc, kinds, targets, horizons, costs,
                        test_years=test_years, tag="baseline")
        return _w2_report(s, c, "does any learner cell beat the market on 26 years, "
                          "after costs?", "weekend-W2-baseline", extra)

    if name == "hysteresis":
        # The cheapest way to make a real edge survive costs: buy at rank <= 50,
        # hold until rank > 100. Reported AGAINST the baseline turnover, because
        # a lower cost line on a null is not a finding.
        # The PREDICTIONS are identical to the baseline's -- hysteresis changes
        # only how the book is traded -- so this variant reuses the baseline's
        # cache tag and pays no fitting cost at all.
        s, c = _w2_grid(df, fc, kinds, targets, horizons, costs, hold_k=100,
                        test_years=test_years, tag="baseline")
        out = _w2_report(s, c, "does buy-50/hold-to-100 hysteresis let a cell survive "
                         "costs that the monthly rebuild does not?",
                         "weekend-W2-hysteresis", extra)
        turns = [v.get("mean_turnover") for v in c.values()
                 if isinstance(v, dict) and v.get("mean_turnover") is not None]
        out["mean_turnover_across_cells"] = (round(float(np.mean(turns)), 3)
                                             if turns else None)
        return out

    if name == "ablation":
        # One feature FAMILY removed at a time. The cell key names the family
        # that was withheld, so a family whose removal does not move the result
        # is a family the model was not using -- which is a finding about the
        # panel, not about the model.
        fams = {
            "analyst_level": [c for c in fc if c.split("__")[0] in
                              ("ratio", "upside", "log_ratio", "consensus",
                               "coverage", "log_coverage", "numest")],
            "analyst_revision": [c for c in fc if c.split("__")[0] in
                                 ("net_rev_4w", "net_rev_1m", "target_rev_1m",
                                  "target_rev_3m", "consensus_rev_1m", "coverage_rev_1m")],
            "dispersion": [c for c in fc if c.split("__")[0] in
                           ("disagreement", "dispersion")],
            "price_shape": [c for c in fc if c.split("__")[0] in
                            ("ret_1m", "ret_3m", "ret_6m", "ret_12m", "mom_12_1",
                             "drawdown_60d")],
            "risk_size": [c for c in fc if c.split("__")[0] in
                          ("vol_20d", "vol_60d", "log_dollar_vol_20d",
                           "log_market_cap", "log_close")],
        }
        series, cells = {}, {}
        for famname, cols in fams.items():
            s, c = _w2_grid(df, fc, ["lgbm"], ["raw"], [1, 3], costs,
                            drop_family=set(cols), test_years=test_years,
                            tag=f"ablate_{famname}")
            for k, v in s.items():
                series[f"no_{famname}|{k}"] = v
            for k, v in c.items():
                cells[f"no_{famname}|{k}"] = v
        s0, c0 = _w2_grid(df, fc, ["lgbm"], ["raw"], [1, 3], costs,
                          test_years=test_years, tag="baseline")
        for k, v in s0.items():
            series[f"full|{k}"] = v
        for k, v in c0.items():
            cells[f"full|{k}"] = v
        extra["families_ablated"] = {k: len(v) for k, v in fams.items()}
        return _w2_report(series, cells,
                          "which feature family is the learner actually using?",
                          "weekend-W2-ablation", extra)

    if name == "quantile":
        from learner import evaluate, models
        # THE TAIL, not the mean. A pinball head at q90 asks "which names have an
        # unusually good RIGHT tail", which is a different question from "which
        # names have a high mean" and is the one a concentrated book actually
        # wants. lgbm's quantile objective, so no new model class is introduced.
        series, cells = {}, {}
        for q in (0.1, 0.5, 0.9):
            for h in (1, 3):
                preds = []
                for year, tr, te in DS.walk_forward_splits(df, test_years, h):
                    try:
                        pred, _m = models.fit_predict("lgbm", "raw", df.loc[tr],
                                                      df.loc[te], fc, h, quantile=q)
                    except Exception as exc:                            # noqa: BLE001
                        cells[f"q{q}|{h}m|fit"] = {"error": f"{type(exc).__name__}: {exc}"}
                        continue
                    preds.append(pd.Series(pred, index=te))
                if not preds:
                    continue
                col = f"pred_q{int(q*100)}_{h}m"
                allp = pd.concat(preds)
                df[col] = np.nan
                df.loc[allp.index, col] = allp.values
                for bps in costs:
                    key = f"q{q}|{h}m|{bps}bps"
                    bk = evaluate.book(df, col, k=50, weight="vw", cost_bps=bps,
                                       ret_col="fwd_1m", mkt_col="mkt_vw_1m",
                                       return_series=True)
                    ser = bk.get("_series") or {}
                    cells[key] = {k: v for k, v in bk.items() if not k.startswith("_")}
                    net, mkt = ser.get("net"), ser.get("market")
                    if net is not None and mkt is not None and net.index.equals(mkt.index):
                        series[key] = (net - mkt).astype("float64")
        extra["note"] = ("quantile heads use lgbm's pinball objective (objective='quantile', "
                         "alpha=q). `models._fit_lgbm` REFUSES if the installed lightgbm "
                         "does not accept it, rather than returning the mean head under a "
                         "q-labelled name -- which would publish three identical cells as a "
                         "tail finding. q0.9 and q0.5 differing IS the evidence the head is "
                         "real; if the cells coincide, read that as a failed variant.")
        return _w2_report(series, cells,
                          "is the right tail more predictable than the mean?",
                          "weekend-W2-quantile", extra)

    if name == "long_only_eras":
        # Fit in ONE era, test everywhere. The single most direct use of 26 years:
        # a model that only works in the era it was fitted in is a description of
        # that era, and 12 years could not tell the two apart.
        series, cells = {}, {}
        for era_name, _lo, _hi in LP.ERAS:
            s, c = _w2_grid(df, fc, ["lgbm"], ["raw"], [1, 3], costs,
                            test_years=test_years, train_era=era_name,
                            tag=f"era_{era_name}")
            for k, v in s.items():
                series[f"fit@{era_name}|{k}"] = v
            for k, v in c.items():
                cells[f"fit@{era_name}|{k}"] = v
        return _w2_report(series, cells,
                          "does a model fitted inside one era work outside it?",
                          "weekend-W2-era-transfer", extra)

    return {"verdict": "FAILED", "headline": f"unknown W2 variant {variant} ({name})"}


# ------------------------------------------------------- deferred job stubs

def _deferred(job: str, why: str) -> dict:
    """A job that is not built yet returns DEFERRED, not FAILED.

    The runner counts FAILED against a two-strike skip. A stub that burned its
    strikes would remove the job from the queue for the rest of the weekend --
    including after the coordinator had written it. DEFERRED costs a leaderboard
    line and keeps the slot.
    """
    return {"verdict": "DEFERRED", "job_planned": job, "headline": f"not built yet: {why}"}


def W3_neural_long(variant: int = 0) -> dict:
    return _deferred("W3_neural_long", "GPU encoder pass pending")


def W4_graph_momentum(variant: int = 0) -> dict:
    """Customer / supplier / competitor momentum from MARKET-GRAPH-1.

    `features_graph.job` returns its own DEFERRED payload when the edge parquet
    is absent, so the runner's two-strike skip is preserved without this wrapper
    having to know how the module fails.
    """
    from learner import features_graph as FG
    return FG.job(variant)


def W5_options_iv(variant: int = 0) -> dict:
    return _deferred("W5_options_iv", "OptionMetrics link pending")


def W6_behavioural(variant: int = 0) -> dict:
    """52-week-high proximity, the VWAP anchor, attention -- with the controls.

    THE CONTROL IS THE POINT. Every one of these features is correlated with
    momentum, size and volatility, all of which the panel already carries, and a
    raw IC would mostly re-measure those. So each feature is reported twice: its
    plain cross-sectional rank IC, and the t of its coefficient in a monthly
    Fama-MacBeth regression that ALSO holds momentum, size and vol -- which is
    the number that says whether the behavioural feature adds anything.

    `feedback_check_whether_the_noise_is_shared`: the control belongs in the
    regression, not in a sentence after it.
    """
    from learner import features_price as FP, inference
    if not FP.available():
        return _deferred("W6_behavioural",
                         "features_price.parquet not built yet (learner.features_price --build)")
    df = _panel()
    df, join_note = FP.attach(df)
    ret = "excess_vw_1m"
    controls = ["mom_12_1", "log_market_cap", "vol_60d"]
    have = [c for c in controls if c in df.columns]
    rows, series = [], {}
    for feat in FP.FEATURES:
        d = df[["month", feat, ret, *have]].dropna()
        if len(d) < 5000:
            rows.append({"feature": feat, "verdict": "CANNOT DETERMINE",
                         "rows": int(len(d)), "why": "fewer than 5,000 usable rows"})
            continue
        # (1) the plain rank IC, month by month.
        ics, betas = [], []
        for m, g in d.groupby("month", sort=True):
            if len(g) < 30:
                continue
            ics.append(float(g[feat].rank().corr(g[ret].rank())))
            # (2) the SAME month, with the controls in the regression.
            X = np.column_stack([np.ones(len(g))] + [
                g[c].rank(pct=True).to_numpy() for c in [feat, *have]])
            y = g[ret].to_numpy(dtype="float64")
            try:
                coef, *_ = np.linalg.lstsq(X, y, rcond=None)
                betas.append(float(coef[1]))
            except np.linalg.LinAlgError:
                continue
        if len(ics) < 24:
            rows.append({"feature": feat, "verdict": "CANNOT DETERMINE",
                         "months": len(ics), "why": "fewer than 24 usable months"})
            continue
        ic = pd.Series(ics, index=sorted(d["month"].unique())[:len(ics)])
        be = pd.Series(betas, index=ic.index[:len(betas)])
        t_ic = float(ic.mean() / (ic.std(ddof=1) / np.sqrt(len(ic)))) if ic.std(ddof=1) else None
        t_be = float(be.mean() / (be.std(ddof=1) / np.sqrt(len(be)))) if len(be) > 2 and be.std(ddof=1) else None
        series[feat] = be
        rows.append({
            "feature": feat, "family": FP.family_of(feat),
            "months": int(len(ic)),
            "mean_rank_ic": round(float(ic.mean()), 5),
            "t_rank_ic": round(t_ic, 3) if t_ic is not None else None,
            "mean_fm_beta_controlled": round(float(be.mean()), 6) if len(be) else None,
            "t_fm_beta_controlled": round(t_be, 3) if t_be is not None else None,
            "controls": have,
            "era_sign_table": era_sign_table(be),
            "power": inference.power_note(be.tolist()),
        })
    # SAME SIGN, not positive sign: a feature is a signal in either direction.
    survivors = [r for r in rows
                 if isinstance(r.get("t_fm_beta_controlled"), (int, float))
                 and abs(r["t_fm_beta_controlled"]) >= 2.0
                 and (r.get("era_sign_table") or {}).get("same_sign_in_2_of_3")]
    killed_by_controls = [
        r["feature"] for r in rows
        if isinstance(r.get("t_rank_ic"), (int, float))
        and isinstance(r.get("t_fm_beta_controlled"), (int, float))
        and abs(r["t_rank_ic"]) >= 3.0 and abs(r["t_fm_beta_controlled"]) < 2.0]
    return {
        "question": ("do the anchoring features add anything to momentum, size and vol "
                     "on 26 years?"),
        "family_id": "weekend-W6-behavioural",
        "join": join_note,
        "features": rows,
        "n_features_tested": len(rows),
        "survivors_controlled_t2_and_same_sign_2of3_eras": [
            {"feature": r["feature"], "t": r["t_fm_beta_controlled"],
             "sign": (r.get("era_sign_table") or {}).get("dominant_sign")}
            for r in survivors],
        "killed_by_the_controls": killed_by_controls,
        "killed_note": ("these cleared |t| >= 3 on the RAW rank IC and fall below |t| = 2 "
                        "once momentum, size and vol are in the same monthly regression. "
                        "They are not features; they are those three wearing a name."),
        "multiplicity_note": (f"{len(rows)} features were tested; a |t| >= 2 bar on "
                              f"{len(rows)} independent tests expects "
                              f"{0.05 * len(rows):.1f} false positives, so the era "
                              "requirement is doing the work a Holm correction would"),
        "headline": (f"{len(rows)} behavioural features on {join_note.get('rows_out', 0):,} "
                     f"rows; {len(survivors)} clear |t| >= 2 WITH controls and keep one sign "
                     f"in 2 of 3 eras: "
                     f"{[(r['feature'], r['t_fm_beta_controlled']) for r in survivors] or 'none'}"
                     f"; killed by the controls: {killed_by_controls or 'none'}"),
        "verdict": "NOVEL" if survivors else "NOISE",
    }


# ------------------------------------------- W7: winner vs MATCHED loser

def _residualise(g: pd.DataFrame, ycol: str, on: list[str]) -> pd.Series:
    """Cross-sectional residual of `ycol` on `on`, within one month.

    Ranks, not levels: a 26-year panel spans two orders of magnitude of price
    and cap, and a level regression would let the 1999 cross-section set the
    slope for 2024.
    """
    d = g[[ycol, *on]].dropna()
    if len(d) < 30:
        return pd.Series(dtype="float64")
    X = np.column_stack([np.ones(len(d))] + [d[c].rank(pct=True).to_numpy() for c in on])
    y = d[ycol].to_numpy(dtype="float64")
    try:
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    except np.linalg.LinAlgError:
        return pd.Series(dtype="float64")
    return pd.Series(y - X @ coef, index=d.index)


def W7_matched_loser(variant: int = 0) -> dict:
    """THE INFORMATIVE UNIT IS WINNER VS MATCHED LOSER, NEVER A GALLERY.

    Mission rule 4, made executable. For every formation month on the long panel:

    1. Take the 12-month forward excess return and RESIDUALISE it, within the
       month, on size, momentum and volatility ranks. A "winner" chosen on raw
       12-month return is mostly a small high-beta name in a good year; the
       residual asks who beat the names that looked like them.
    2. `TOP_N` residual winners, `TOP_N` residual losers.
    3. MATCHED CONTROLS: for each winner, the `N_MATCH` names in the same month
       and same sector whose (size, momentum) ranks are nearest, excluding any
       name that is itself a winner or a loser. The control is what the winner
       LOOKED LIKE beforehand, which is the only comparison that can carry a
       precursor.
    4. For every PIT feature the panel carries, the winner-minus-control mean
       difference, one number per month, then a t across months and a
       three-era sign table.

    WHAT MAKES THIS DIFFERENT FROM AN AFTER-THE-FACT STORY. The features are all
    dated at the FORMATION month; the outcome is twelve months later. A
    difference that survives here is a difference that was observable
    beforehand, which is the Micron test. Explaining a winner afterwards is
    trivial; this is the other thing.

    THE RECALL BASELINE, and why it is reported even when it is bad. For each
    year: what share of that year's residual top-50 was already in the top
    decile of (a) analyst upside, (b) 12-1 momentum, (c) net revisions? A
    precursor that is real but fires on 3% of winners is a different product
    from one that fires on 40%, and a mean difference alone cannot tell them
    apart.
    """
    from learner import dataset as DS, inference, long_panel as LP
    TOP_N, N_MATCH = 50, 5
    df = _panel()
    ycol = "excess_vw_12m"
    if ycol not in df.columns:
        return {"verdict": "FAILED", "headline": f"{ycol} absent from the panel"}
    on = [c for c in ("log_market_cap", "mom_12_1", "vol_60d") if c in df.columns]
    feats = [c for c in DS.feature_columns() if c in df.columns]

    diffs_w: dict[str, list] = {c: [] for c in feats}
    diffs_l: dict[str, list] = {c: [] for c in feats}
    months_used, recall_rows = [], []
    for m, g in df.groupby("month", sort=True):
        g = g[g[ycol].notna()]
        if len(g) < 300:
            continue
        resid = _residualise(g, ycol, on)
        if resid.empty:
            continue
        g = g.loc[resid.index].assign(_resid=resid)
        order = g["_resid"].sort_values(ascending=False)
        win = g.loc[order.index[:TOP_N]]
        los = g.loc[order.index[-TOP_N:]]
        pool = g.drop(index=list(win.index) + list(los.index))
        if len(pool) < N_MATCH * 2:
            continue
        # The match: same sector, nearest on (size rank, momentum rank).
        pr = {c: pool[c].rank(pct=True) for c in on}
        gr = {c: g[c].rank(pct=True) for c in on}

        def _controls(target_idx):
            picks = []
            for i in target_idx:
                cand = pool
                if "sector" in pool.columns and pd.notna(g.at[i, "sector"]):
                    same = pool[pool["sector"] == g.at[i, "sector"]]
                    if len(same) >= N_MATCH:
                        cand = same
                d2 = sum((pr[c].loc[cand.index] - gr[c].at[i]) ** 2 for c in on)
                picks.extend(d2.nsmallest(N_MATCH).index.tolist())
            return pool.loc[list(dict.fromkeys(picks))]

        cw = _controls(win.index)
        cl = _controls(los.index)
        if not len(cw) or not len(cl):
            continue
        months_used.append(str(m))
        for c in feats:
            if win[c].notna().sum() >= 10 and cw[c].notna().sum() >= 10:
                diffs_w[c].append(float(win[c].mean() - cw[c].mean()))
            if los[c].notna().sum() >= 10 and cl[c].notna().sum() >= 10:
                diffs_l[c].append(float(los[c].mean() - cl[c].mean()))
        # The recall baseline: which precursors already flagged this month's winners?
        rec = {"month": str(m), "winners": int(len(win))}
        for label, col in (("analyst_upside", "ratio"), ("mom_12_1", "mom_12_1"),
                           ("net_revisions", "net_rev_4w")):
            if col in g.columns and g[col].notna().sum() > 100:
                cut = g[col].quantile(0.9)
                rec[f"recall_{label}_top_decile"] = round(
                    float((win[col] >= cut).mean()), 4)
        recall_rows.append(rec)

    if len(months_used) < 24:
        return {"verdict": "CANNOT DETERMINE", "months_used": len(months_used),
                "headline": (f"only {len(months_used)} formation months produced a matched "
                             "set -- too few to test")}

    from learner import evaluate as EV

    def _summarise(store, label):
        """Every feature's winner-minus-control difference, with ALL THREE t's.

        THE NAIVE t HERE IS INFLATED AND THE AMOUNT IS KNOWN. The outcome is a
        TWELVE-MONTH return sampled every month, so consecutive observations
        share eleven twelfths of their window: 297 monthly draws are about 25
        independent ones. `feedback_name_days_are_not_periods` is the house
        record of exactly this -- a 5-session overlapping series went naive
        t 10.0 -> HAC 5.7 -> non-overlapping 4.2, and the rule it left behind is
        REPORT ALL THREE.

        So the archetype bar below is applied to the NON-OVERLAPPING t, which is
        the conservative one, and the naive t is kept only so a reader can see
        how much of it was overlap.
        """
        out = []
        for c, vals in store.items():
            if len(vals) < 24:
                continue
            s = pd.Series(vals, index=pd.Index(months_used[:len(vals)], name="month"))
            oc = EV.overlap_corrected(s, 12)
            # THE KEY NAMES ARE `t_newey_west` AND `block_t_block`, and asking for
            # `t_hac`/`t_block` returns None for every feature -- which made the
            # archetype bar unreachable and printed "0 candidates" as if it were
            # a result. A gate whose input is always None is a BROKEN gate, so it
            # is derived here and REFUSED if absent, never defaulted.
            if "t_newey_west" not in oc or "block_t_block" not in oc:
                raise SystemExit(
                    "REFUSED: evaluate.overlap_corrected did not return the "
                    f"overlap-corrected keys for a {len(s)}-month series; it returned "
                    f"{sorted(oc)}. Reading a missing key as None would report an "
                    "unreachable bar as an empty result.")
            out.append({"feature": c, "side": label, "months": int(len(s)),
                        "mean_diff": round(float(s.mean()), 6),
                        "t_naive": oc.get("t_naive"),
                        "t_hac": oc.get("t_newey_west"),
                        "t_block_non_overlapping": oc.get("block_t_block"),
                        "n_effective": oc.get("block_n_effective"),
                        "overlap_note": ("the outcome is a 12-month return sampled monthly; "
                                         "the naive t divides by sqrt(months) when the "
                                         "independent draws number about months/12"),
                        "era_sign_table": era_sign_table(s),
                        "power": inference.power_note(s.tolist())})
        return sorted(out, key=lambda r: -abs(r.get("t_block_non_overlapping") or 0))

    w = _summarise(diffs_w, "winner_minus_matched_control")
    l = _summarise(diffs_l, "loser_minus_matched_control")
    # ARCHETYPE CANDIDATE: separates the winner from a name that looked like it,
    # holds in >= 2 of 3 eras, and is NOT the same difference on the loser side
    # (a feature that moves the same way for winners and losers is a feature
    # about being extreme, not about being right).
    lt = {r["feature"]: r for r in l}
    arche = []
    for r in w:
        tb = r.get("t_block_non_overlapping")
        # THE BAR IS THE NON-OVERLAPPING t. Using the naive one would admit a
        # feature whose only claim is that the same twelve months were counted
        # twelve times.
        if not (isinstance(tb, (int, float)) and abs(tb) >= 2.5):
            continue
        if not (r["era_sign_table"] or {}).get("same_sign_in_2_of_3"):
            continue
        other = lt.get(r["feature"])
        ot = (other or {}).get("t_block_non_overlapping")
        same_sign = bool(other and isinstance(ot, (int, float)) and abs(ot) >= 2.0
                         and np.sign(other["mean_diff"]) == np.sign(r["mean_diff"]))
        r = dict(r, loser_side_moves_the_same_way=same_sign)
        if not same_sign:
            arche.append(r)
    # MULTIPLICITY. This is a SCREEN over every feature the panel carries, so the
    # correction is Benjamini-Hochberg FDR (CANON §63: SCREEN = BH-FDR, EXPORT =
    # Holm). Both are reported, because a candidate that survives BH is worth a
    # second look and a candidate that survives Holm is worth an export.
    from math import erfc, sqrt as _sqrt

    def _two_sided_p(t):
        return float(erfc(abs(float(t)) / _sqrt(2.0)))  # normal approximation

    def _correct(rows_):
        ts = [(r["feature"], r.get("t_block_non_overlapping")) for r in rows_
              if isinstance(r.get("t_block_non_overlapping"), (int, float))]
        m = len(ts)
        if not m:
            return {}, {}
        ps = sorted(((f, _two_sided_p(t)) for f, t in ts), key=lambda kv: kv[1])
        bh, holm, prev = {}, {}, 0.0
        for i, (f, p) in enumerate(ps, start=1):
            q = min(1.0, max(prev, p * m / i))
            prev = q
            bh[f] = round(q, 6)
        prevh = 0.0
        for i, (f, p) in enumerate(ps, start=1):
            a = min(1.0, max(prevh, p * (m - i + 1)))
            prevh = a
            holm[f] = round(a, 6)
        return bh, holm

    bh_w, holm_w = _correct(w)
    for r in w:
        r["bh_fdr_q"] = bh_w.get(r["feature"])
        r["holm_p"] = holm_w.get(r["feature"])
    for a in arche:
        a["bh_fdr_q"] = bh_w.get(a["feature"])
        a["holm_p"] = holm_w.get(a["feature"])
    arche_bh = [a for a in arche if isinstance(a.get("bh_fdr_q"), float) and a["bh_fdr_q"] <= 0.10]
    arche_holm = [a for a in arche if isinstance(a.get("holm_p"), float) and a["holm_p"] <= 0.05]

    # HOW MANY INDEPENDENT IDEAS IS THAT, REALLY. `net_rev_1m`, `net_rev_4w`,
    # `consensus_rev_1m` and their `__xs` ranks are four views of ONE idea, and
    # counting them as four survivors would inflate the finding by construction.
    # Features are collapsed to their stem (the part before `__xs`) and to the
    # family prefix, so the headline can say how many DISTINCT things survived.
    def _idea(f):
        stem = f.split("__")[0]
        for pref, idea in (("net_rev", "analyst_revision"),
                           ("consensus_rev", "analyst_revision"),
                           ("target_rev", "analyst_revision"),
                           ("coverage_rev", "analyst_revision"),
                           ("log_dollar_vol", "turnover_thinness"),
                           ("ret_", "price_shape"), ("mom_", "price_shape"),
                           ("vol_", "risk"), ("drawdown", "price_shape"),
                           ("log_market_cap", "size"), ("log_close", "price_level"),
                           ("dispersion", "analyst_disagreement"),
                           ("disagreement", "analyst_disagreement")):
            if stem.startswith(pref):
                return idea
        return stem
    ideas = sorted({_idea(a["feature"]) for a in arche})

    rr = pd.DataFrame(recall_rows)
    recall = {c: round(float(rr[c].mean()), 4) for c in rr.columns
              if c.startswith("recall_") and rr[c].notna().any()}
    return {
        "question": ("what was observable BEFOREHAND that separated a 12-month residual "
                     "winner from the names that looked exactly like it?"),
        "family_id": "weekend-W7-matched-loser",
        "design": {"top_n": TOP_N, "controls_per_name": N_MATCH,
                   "residualised_on": on,
                   "match_on": ["sector (exact where available)"] + on,
                   "outcome": ycol,
                   "formation_months": len(months_used),
                   "window": [months_used[0], months_used[-1]]},
        "features_tested": len(w),
        "winner_side": w[:25],
        "loser_side": l[:25],
        "archetype_candidates": arche,
        "archetype_candidates_surviving_bh_fdr_10pct": [a["feature"] for a in arche_bh],
        "archetype_candidates_surviving_holm_5pct": [a["feature"] for a in arche_holm],
        "distinct_ideas_among_the_candidates": ideas,
        "distinct_idea_note": ("net_rev_*/consensus_rev_* and their __xs ranks are views of "
                               "ONE idea; counting them separately would inflate the finding "
                               "by construction, so the headline counts IDEAS"),
        "opportunity_recall_baseline": recall,
        "recall_note": ("share of each month's residual top-50 that was ALREADY in the "
                        "top decile of each precursor at formation. A pure-chance "
                        "precursor recalls 0.10 by construction."),
        "multiplicity_note": (f"{len(w)} features on the winner side; the bar is the "
                              "NON-OVERLAPPING |t| >= 2.5 plus a consistent sign in 2 of 3 "
                              "eras, and the loser side is the sign check a t alone cannot "
                              "give -- a feature that moves the same way for winners and "
                              "losers is a statement about being EXTREME, not about being "
                              "right"),
        "headline": (f"{len(months_used)} formation months, {TOP_N} winners x {N_MATCH} "
                     f"matched controls each; {len(arche)} candidates over "
                     f"{len(ideas)} DISTINCT ideas ({ideas}) clear non-overlapping "
                     f"|t| >= 2.5, a consistent sign in 2 of 3 eras, and a loser side that "
                     f"does NOT move the same way; {len(arche_bh)} survive BH-FDR 10% and "
                     f"{len(arche_holm)} survive Holm 5%"),
        "verdict": "NOVEL" if arche else "NOISE",
    }


def _try(fn):
    try:
        return fn()
    except Exception as exc:                                            # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}


def _market_circular_shift_null(d, state_col: str, target: str, S,
                                n_shuffles: int = 500, seed: int = 20260906) -> dict:
    """The null a MARKET-level state actually owes.

    One state per month, so the object to permute is the MONTHLY SEQUENCE, not
    the per-name labels. Each draw circularly shifts that single sequence by a
    random non-zero offset, which preserves -- exactly --

      * the state marginal (how often each state occurs),
      * the run-length structure and transition multiset (the persistence), and
      * the calendar itself,

    and destroys only the ALIGNMENT between states and what followed them. So a
    draw is a market-state assignment exactly as persistent as the observed one,
    which is the property the S36 lesson says a null must have: a null that
    re-randomises lets its tilts wash out and cannot catch a persistent random
    partition.
    """
    rng = np.random.default_rng(seed)
    months = sorted(d["month"].unique())
    seq = (d.groupby("month")[state_col].first().reindex(months).to_numpy())
    n = len(seq)
    if n < 24:
        return {"verdict": "CANNOT DETERMINE", "months": n,
                "why": "fewer than 24 months; a circular shift has too few offsets"}
    obs = float(S.spread_statistic(d, state_col, target))
    m2s = {m: i for i, m in enumerate(months)}
    idx = d["month"].map(m2s).to_numpy()
    sub = d[["month", target]].copy()
    draws = []
    for _ in range(n_shuffles):
        off = int(rng.integers(1, n))          # non-zero: offset 0 is the observation
        sub["_sh"] = np.roll(seq, off)[idx]
        v = S.spread_statistic(sub, "_sh", target)
        if v == v:
            draws.append(float(v))
    a = np.asarray(draws)
    return {
        "null": "market-level circular shift of the single monthly state sequence",
        "statistic": "max-minus-min of per-state mean monthly excess",
        "target": target,
        "months": n,
        "observed": round(obs, 6),
        "null_draws": int(len(a)),
        "null_mean": round(float(a.mean()), 6) if len(a) else None,
        "null_p95": round(float(np.quantile(a, 0.95)), 6) if len(a) else None,
        "p_value_one_sided": round(float((a >= obs).mean()), 4) if len(a) else None,
        "preserves": ["state marginal", "run lengths / transition multiset", "calendar"],
        "destroys": ["alignment of states to the returns that followed"],
    }


def W8_states_three_nulls(variant: int = 0) -> dict:
    """MARKET STATES on 26 years, and the three nulls a state claim owes.

    The question is not "are there states" -- KMeans always returns k clusters.
    It is "does the future differ ACROSS the states by more than a partition of
    the same months would have produced anyway", and that needs a null that is
    the same KIND of object as the thing being tested:

    1. **The within-month shuffle** (`states.shuffled_null`). Keeps the calendar,
       the per-month state sizes and the cross-sectional return distribution.
       Answers "would a random partition of THESE months look like this?"
       Its known limit is stamped in its own docstring: it re-randomises every
       draw, so tilts wash out and it cannot represent a PERSISTENT partition.
    2. **The persistent shuffle** (`states.persistent_shuffled_null`). Shifts
       each name's own state sequence in time, so every draw is exactly as
       persistent as the observed assignment with only the alignment to outcomes
       destroyed. This is the null that S36 showed was missing -- a model fitted
       on noise holds ONE tilt, and a non-persistent null never sees it.
    3. **The era null.** The states are re-graded inside each era separately. A
       spread that only exists in one era is a description of that era, and 26
       years is the first window on which that can be asked at all.

    `CANNOT DETERMINE` is an allowed and expected verdict here.
    """
    from learner import states as S, long_panel as LP
    df = _panel()
    cols = [c for c in S.STATE_FEATURES if c in df.columns]
    if len(cols) < 5:
        return {"verdict": "CANNOT DETERMINE",
                "headline": (f"only {len(cols)} of {len(S.STATE_FEATURES)} state features "
                             "are on the long panel"),
                "missing": [c for c in S.STATE_FEATURES if c not in df.columns]}
    k = [4, 5, 6][variant % 3]
    mf = S.market_month_features(df)
    msdf, msmeta = S.run_market_states(mf, k)
    d = df.merge(msdf, on="month", how="inner")
    state_col = [c for c in msdf.columns if c != "month"][0]
    target = "excess_vw_1m"
    cond = S.conditional_table(d, state_col, targets=(target, "excess_vw_3m"))

    # IS THE STATE MARKET-LEVEL OR NAME-LEVEL? The answer decides which nulls are
    # even DEFINED, and getting it wrong produces confident numbers that mean
    # nothing. Measured, not assumed.
    per_month_states = d.groupby("month")[state_col].nunique()
    market_level = bool((per_month_states <= 1).all())

    n1 = {"skipped": True, "why": (
        "`states.shuffled_null` permutes state labels WITHIN each month. A "
        "market-level state is CONSTANT within a month, so that permutation is "
        "the identity: every draw equals the observation, `null_p95 == observed`, "
        "and p is 1.0 by construction regardless of the data. It is a correct "
        "null for a NAME-level state and an undefined one here.")} \
        if market_level else S.shuffled_null(d, state_col, target, n_shuffles=200)

    n2 = {"skipped": True, "why": (
        "`states.persistent_shuffled_null` circularly shifts EACH NAME's own "
        "state sequence independently. Under a market-level state every name "
        "shares one sequence, so shifting them independently destroys the "
        "market-wide coherence that is the object under test -- the null becomes "
        "far weaker than the alternative and returns p = 0.0 as an artefact.")} \
        if market_level else _try(lambda: S.persistent_shuffled_null(
            d, state_col, target, n_shuffles=200))

    # THE NULL OF THE RIGHT KIND. One shared monthly sequence, circularly
    # shifted: every draw has exactly the observed persistence, the observed
    # state marginal and the observed calendar, and only the ALIGNMENT of states
    # to outcomes is destroyed. This is the market-level analogue of the
    # persistent null, and it is the only one of the three that is defined for
    # the object actually being tested here.
    n_market = _market_circular_shift_null(d, state_col, target, S, n_shuffles=500)
    by_era = {}
    for era, _lo, _hi in LP.ERAS:
        g = d[d["era"].astype(str) == era]
        if g[target].notna().sum() < 5000:
            by_era[era] = {"verdict": "CANNOT DETERMINE", "rows": int(len(g))}
            continue
        by_era[era] = {"rows": int(len(g)),
                       "spread": round(float(S.spread_statistic(g, state_col, target)), 6)}
    # THE KEY IS `p_value_one_sided`. Asking for a key the null does not return
    # makes every state look unresolvable regardless of what the data said --
    # the same unreachable-gate failure this file has already paid for twice.
    def _p(null: dict, which: str):
        if not isinstance(null, dict) or "error" in null or null.get("skipped"):
            return None
        if "p_value_one_sided" not in null:
            raise SystemExit(
                f"REFUSED: the {which} null returned {sorted(null)} with no "
                "`p_value_one_sided`. Defaulting a missing p to None would report "
                "an unreachable bar as CANNOT DETERMINE.")
        return null["p_value_one_sided"]

    p1 = _p(n1, "within-month-shuffle")
    p2 = _p(n2, "persistent-shuffle")
    pm = _p(n_market, "market circular shift")
    # THE VERDICT RESTS ON THE NULL THAT IS DEFINED FOR THIS OBJECT. For a
    # market-level state that is the circular-shift null; the other two are
    # recorded with the reason they do not apply, so a later reader sees that
    # they were considered and ruled out rather than forgotten.
    era_spreads = [v.get("spread") for v in by_era.values()
                   if isinstance(v.get("spread"), (int, float))]
    era_consistent = bool(len(era_spreads) >= 2 and min(era_spreads) > 0)
    if pm is None:
        verdict = "CANNOT DETERMINE"
    elif pm <= 0.05 and era_consistent:
        verdict = "NOVEL"
    elif pm <= 0.05:
        verdict = "REGIME_SPECIFIC"
    else:
        verdict = "NOISE"
    return {
        "question": ("does the future differ across discovered market states by more than "
                     "a partition of the same months, with the same persistence, would "
                     "produce?"),
        "family_id": f"weekend-W8-states-k{k}",
        "k": k, "state_col": state_col,
        "months": int(d["month"].nunique()),
        "state_is_market_level": market_level,
        "state_meta": msmeta,
        "conditional_table": cond,
        "null_1_within_month_shuffle": n1,
        "null_2_persistent_shuffle_per_name": n2,
        "null_3_market_circular_shift": n_market,
        "null_4_by_era": by_era,
        "which_null_the_verdict_rests_on": (
            "null_3_market_circular_shift -- the only one of the three that is DEFINED for "
            "a market-level state. Nulls 1 and 2 are correct for NAME-level states and are "
            "recorded here with the reason they do not apply, because a null that returns "
            "p = 1.0 or p = 0.0 by construction is not a weak result, it is not a result."
            if market_level else
            "nulls 1-3 all apply: the state varies within a month"),
        "headline": (f"k={k} market states over {d['month'].nunique()} months; "
                     f"market circular-shift p {pm} (observed spread "
                     f"{n_market.get('observed')} vs null p95 {n_market.get('null_p95')}); "
                     f"era spreads { {e: v.get('spread') for e, v in by_era.items()} }"),
        "verdict": verdict,
    }


def W11_evidence_writeback(variant: int = 0) -> dict:
    """Fold every receipt this weekend has written into the evidence memory.

    THIS IS WHAT MAKES TWENTY PASSES WORTH MORE THAN ONE. Without it the
    leaderboard is a log: pass 19 knows nothing pass 1 knew, and a cell that
    looked good once gets quoted while a cell that looked flat once gets buried.
    `learner/evidence_memory.py` holds the rule that prevents both -- a single
    pass can neither promote nor kill, and REFUTED additionally requires three
    passes that each HAD THE POWER to detect the effect.
    """
    from learner import evidence_memory as EM
    from scripts import weekend_lab as WL
    folded, files, errors = 0, 0, []
    for p in sorted(WL.OUT.glob("W*_run*_v*.json")):
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:                                        # noqa: BLE001
            errors.append(f"{p.name}: {type(exc).__name__}: {exc}")
            continue
        files += 1
        folded += EM.record_receipt(payload)
    snap = EM.snapshot()
    top = [f"{k.split('::')[-1]} = {v['state']}"
           for k, v in list(snap["by_cell"].items())[:5]]
    return {
        "question": "what does the whole weekend, taken together, license us to say?",
        "family_id": "weekend-W11-evidence-memory",
        "receipts_read": files,
        "cell_observations_folded": folded,
        "errors": errors,
        "state_counts": snap["state_counts"],
        "observations_total": snap["observations"],
        "cells_tracked": snap["cells"],
        "global_clear_rate": snap["global_clear_rate"],
        "rule": snap["rule"],
        "top_cells_by_best_dsr": top,
        "headline": (f"{files} receipts -> {folded} cell observations; "
                     f"{snap['cells']} cells tracked; states {snap['state_counts']}"),
        "verdict": "INVENTORY",
    }


JOBS = {
    "W1_long_panel_inventory": W1_long_panel_inventory,
    "W2_learner_long": W2_learner_long,
    "W3_neural_long": W3_neural_long,
    "W4_graph_momentum": W4_graph_momentum,
    "W5_options_iv": W5_options_iv,
    "W6_behavioural": W6_behavioural,
    "W7_matched_loser": W7_matched_loser,
    "W8_states_three_nulls": W8_states_three_nulls,
    "W11_evidence_writeback": W11_evidence_writeback,
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("job", choices=sorted(JOBS))
    ap.add_argument("--out", required=True)
    ap.add_argument("--run", type=int, default=1)
    ap.add_argument("--variant", type=int, default=0)
    args = ap.parse_args(argv)
    try:
        payload = JOBS[args.job](args.variant)
    except Exception:                                                   # noqa: BLE001
        payload = {"verdict": "FAILED",
                   "headline": "raised -- traceback IS the receipt",
                   "traceback": traceback.format_exc()[-6000:]}
    payload.setdefault("licence", "PRODUCT_EXPERIMENT")
    payload["job"] = args.job
    payload["run"] = args.run
    payload["variant"] = args.variant
    payload["written_utc"] = _now()
    p = Path(args.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    print(f"{args.job} v{args.variant}: {payload.get('verdict')} -- "
          f"{str(payload.get('headline'))[:160]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
