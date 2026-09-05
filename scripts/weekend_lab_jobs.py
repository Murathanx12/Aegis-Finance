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


def decay_reading(eras: dict) -> dict:
    """DID IT WORK AND THEN STOP? A 26-year panel can ask; a 12-year one cannot.

    The weekend's best cell -- analyst target-price revisions, +9.6%/yr at t 2.06
    over 308 months, the FIRST powered result of the run -- reads era by era:

        1999-2007  +1.51%/month  t 2.35
        2008-2015  +0.95%/month  t 1.81
        2016-2024  -0.02%/month  t -0.03

    Pooling those into one mean and calling the result NOISE (DSR 0.53) throws
    away the only thing worth knowing: it worked for seventeen years and has been
    dead for nine. That is not the same claim as "there was never anything here",
    and it is not the same DECISION either -- a decayed anomaly says look for
    what changed, a null says look somewhere else.

    On 2013-2024 alone this shows up as a weak positive and gets filed as noise.
    Dating the decay is what the extra fourteen years bought.
    """
    from learner import long_panel as LP
    names = [n for n, _lo, _hi in LP.ERAS]
    got = [eras.get(n) or {} for n in names]
    ts = [g.get("t") for g in got]
    if any(t is None for t in ts) or len(ts) < 3:
        return {"decayed": False, "why": "not every era has a usable t"}
    early_alive = sum(1 for t in ts[:-1] if isinstance(t, (int, float)) and t >= 1.5)
    last = ts[-1]
    dead_last = isinstance(last, (int, float)) and abs(last) < 1.0
    return {
        "decayed": bool(early_alive >= 1 and dead_last),
        "era_t": dict(zip(names, ts)),
        "eras_alive_before_the_last": early_alive,
        "last_era_t": last,
        "reading": (f"alive in {early_alive} of the {len(ts) - 1} earlier eras and flat in "
                    f"{names[-1]} (t {last}) -- a DECAYED effect, not an absent one"
                    if early_alive >= 1 and dead_last else
                    "no decay pattern: the last era is not the odd one out"),
    }


def screen_verdict(survivors, tested: int, eras: dict, power: dict | None = None,
                   *, corrected: str | None = None) -> str:
    """The verdict word for a FEATURE SCREEN -- which has no book and no Sharpe.

    WHY THIS EXISTS. `verdict_from` needs a DSR, an SPA p and a PBO, and a
    Fama-MacBeth coefficient series has none of them: there is no book, so there
    is no terminal wealth to deflate. Three jobs (W5c, W6, W7) therefore rolled
    their own `"NOVEL" if survivors else "NOISE"` on a bare |t| >= 2, and a code
    review counted the damage: **25 of 92 committed verdicts said NOVEL and not
    one of them had cleared the bar this module's docstring defines.** A
    vocabulary applied inconsistently is worse than no vocabulary, because the
    word still carries the weight of the definition.

    So a screen gets its own word and its own bar, and the word is never NOVEL:

      * `SCREEN_SURVIVOR`  -- cleared its controlled t AND a multiplicity
        correction (Holm/BH) AND held one sign across eras. It has earned a BOOK,
        which is the test that has killed five of these already.
      * `SCREEN_ONLY`      -- cleared the raw bar, not the correction.
      * `CANNOT DETERMINE` -- the instrument could not have seen an effect worth
        acting on.
      * `NOISE`            -- it could have, and there was nothing.

    NOVEL is reserved for something that survived a book, a family and a
    deflation. A screen cannot reach it, and pretending otherwise is how a
    coefficient becomes a claim.
    """
    n = len(survivors)
    if n and corrected:
        return f"SCREEN_SURVIVOR ({n} of {tested}, {corrected})"
    if n:
        return f"SCREEN_ONLY ({n} of {tested}, no multiplicity correction applied)"
    if power and power.get("powered") is False:
        mde = power.get("mde_annual_excess_at_t_target")
        return (f"CANNOT DETERMINE (underpowered; MDE "
                f"{mde:.1%}/yr)" if isinstance(mde, float)
                else "CANNOT DETERMINE (underpowered)")
    return "NOISE"


def verdict_from(inf: dict, eras: dict) -> str:
    """The bar, in one place. Every job calls this or explains why."""
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
    # `powered` is now computed against a PRE-SPECIFIED effect (3%/yr at the arm's
    # own volatility), not against its observed Sharpe. The first version used the
    # observed one, which reduces algebraically to `t >= 2` -- so this branch
    # fired for every arm with 0 < t < 2 and NOISE was unreachable. The MDE is
    # quoted because it says what the instrument could see, which is the useful
    # form of "underpowered".
    if pw.get("powered") is False:
        mde = pw.get("mde_annual_excess_at_t_target")
        return (f"CANNOT DETERMINE (underpowered; this arm could only have shown an "
                f"effect of {mde:.1%}/yr or larger)" if isinstance(mde, float)
                else "CANNOT DETERMINE (underpowered)")
    # DECAYED is not NOISE either, and it is the verdict only a long panel can
    # reach. See `decay_reading`.
    dec = decay_reading(eras)
    if dec.get("decayed") and pw.get("powered") is True:
        return "DECAYED (worked, then stopped)"
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
    "augmented",           # 5 -- the panel's 49 features PLUS everything W4/W5/W6 built
]


def _augmented_features(df):
    """Join the weekend's new feature families onto the panel and return
    (frame, extra feature columns, join notes).

    THE ROADMAP'S ACTUAL ASK, and the one thing the individual feature jobs
    cannot answer. W5 says the options surface carries an informed-trading
    signal; W6 says short-run reversal and 5-day attention survive their
    controls. Each was measured ALONE, in a Fama-MacBeth regression, against
    momentum/size/vol. None of that says whether a MODEL that already has 49
    features gets better when they are added -- which is the only form of the
    question that decides whether to carry the data.

    A feature that is real and redundant is worth knowing about, and it looks
    identical to a real and useful one until the model is fitted both ways.
    """
    notes = {}
    extra: list[str] = []
    try:
        from learner import features_price as FP
        if FP.available():
            df, n = FP.attach(df)
            notes["price"] = n.get("verdict")
            extra += [c for c in FP.FEATURES if c in df.columns]
    except Exception as exc:                                            # noqa: BLE001
        notes["price"] = f"{type(exc).__name__}: {exc}"
    try:
        from learner import features_options as FO
        if FO.available():
            df, n = FO.attach(df)
            notes["options"] = n.get("verdict")
            extra += [c for c in getattr(FO, "FEATURES", ()) if c in df.columns]
    except Exception as exc:                                            # noqa: BLE001
        notes["options"] = f"{type(exc).__name__}: {exc}"
    try:
        from learner import features_graph as FG
        if FG.available():
            df, n = FG.attach(df)
            notes["graph"] = n.get("verdict")
            extra += [c for c in getattr(FG, "FEATURES", ()) if c in df.columns]
    except Exception as exc:                                            # noqa: BLE001
        notes["graph"] = f"{type(exc).__name__}: {exc}"
    return df, sorted(set(extra)), notes


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

    if name == "augmented":
        # THE PAIRED COMPARISON IS THE EXPERIMENT. The augmented grid is run
        # beside the SAME grid on the panel's own features, over the SAME months,
        # so the difference is the features and not the window. Reporting the
        # augmented number alone would be a comparison to a remembered baseline.
        df2, extra_cols, notes = _augmented_features(df)
        if not extra_cols:
            return _deferred("W2_learner_long[augmented]",
                             "no weekend feature table is on disk to join")
        base_s, base_c = _w2_grid(df2, fc, ["lgbm"], ["raw"], [1, 3], costs,
                                  test_years=test_years, tag="aug_base")
        aug_s, aug_c = _w2_grid(df2, fc + extra_cols, ["lgbm"], ["raw"], [1, 3], costs,
                                test_years=test_years, tag="aug_plus")
        series, cells = {}, {}
        for k, v in base_s.items():
            series[f"panel_only|{k}"] = v
        for k, v in base_c.items():
            cells[f"panel_only|{k}"] = v
        for k, v in aug_s.items():
            series[f"augmented|{k}"] = v
        for k, v in aug_c.items():
            cells[f"augmented|{k}"] = v
        lifts = []
        for k in base_s:
            a, b = base_s.get(k), aug_s.get(k)
            if a is None or b is None:
                continue
            d = (b - a).dropna()
            if len(d) < 24 or d.std(ddof=1) == 0:
                continue
            lifts.append({
                "cell": k, "months": int(len(d)),
                "augmented_minus_panel_pct_per_month": round(float(d.mean()) * 100, 4),
                "t": round(float(d.mean() / (d.std(ddof=1) / np.sqrt(len(d)))), 3),
                "era_sign_table": era_sign_table(d),
            })
        meta = dict(extra)
        meta.update({
            "extra_features": extra_cols,
            "n_extra_features": len(extra_cols),
            "n_panel_features": len(fc),
            "join_notes": notes,
            "paired_lift_augmented_minus_panel_only": lifts,
            "why_paired": ("both grids are fitted on the SAME rows over the SAME months, "
                           "so the difference is the features and not the window. A "
                           "feature that is real and REDUNDANT looks identical to a real "
                           "and useful one until the model is fitted both ways."),
        })
        out = _w2_report(series, cells,
                         "does the learner get better when the weekend's new features "
                         "are added to the panel's own?",
                         "weekend-W2-augmented", meta)
        best_lift = max(lifts, key=lambda r: r["t"], default=None)
        out["headline"] = (
            f"{len(extra_cols)} weekend features added to the panel's {len(fc)}: best "
            f"paired lift "
            f"{best_lift['augmented_minus_panel_pct_per_month'] if best_lift else None}"
            f"%/month (t {best_lift['t'] if best_lift else None}) on "
            f"{best_lift['cell'] if best_lift else '--'}; "
            + str(out.get("headline", ""))[:110])
        return out

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
    """The GPU encoder on the long panel. Import inside the body, as W4/W5 do."""
    from learner.neural_long import job as _w3
    return _w3(variant)


def W4_graph_momentum(variant: int = 0) -> dict:
    """Customer / supplier / competitor momentum from MARKET-GRAPH-1.

    `features_graph.job` returns its own DEFERRED payload when the edge parquet
    is absent, so the runner's two-strike skip is preserved without this wrapper
    having to know how the module fails.
    """
    from learner import features_graph as FG
    return FG.job(variant)


def W5_options_iv(variant: int = 0) -> dict:
    """Implied-vol surface features. The import stays INSIDE the body.

    `features_options.job` imports `era_sign_table` from this module -- the era
    boundaries are imported, never re-derived -- so a module-level import on this
    side would close the cycle.
    """
    from learner.features_options import job as _w5
    return _w5(variant)


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
        "verdict": screen_verdict(
            survivors, len(rows),
            (survivors[0].get("era_sign_table") if survivors else {}) or {},
            (survivors[0].get("power") if survivors else None),
            corrected=("controlled |t| >= 2 AND one sign in 2 of 3 eras; no formal "
                       "multiplicity correction on 7 features" if survivors else None)),
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


def W5b_options_book(variant: int = 0) -> dict:
    """DOES THE OPTIONS COEFFICIENT SURVIVE BECOMING MONEY?

    W5 reports two survivors on 26 years with controls in the same monthly
    regression: the call-minus-put IV spread (Cremers-Weinbaum, HAC t +4.15,
    positive in 3 of 3 eras) and the 25-delta skew (Xing-Zhang-Zhao, HAC t -5.37,
    negative in 3 of 3). Both carry the literature's sign.

    A Fama-MacBeth coefficient is NOT a strategy. It has no k, no weighting, no
    turnover and no spread, and this repo has watched several coefficients die
    between 10 and 25 bps. So this job does the only thing that settles it:
    builds the actual top-50 value-weighted book, pays the measured turnover, and
    puts the result through the same DSR / SPA / PBO / power machinery every
    other cell here goes through.

    "BETTER THAN WHAT?" -- AND WHY THE OBVIOUS BENCHMARK IS THE WRONG ONE.
    Only 72.9% of panel rows carry a listed 30-day surface, and the missing 27%
    are systematically the small and the illiquid. So a book drawn from the
    option-covered subuniverse and measured against the FULL CRSP market is
    partly measuring *having listed options*, which is a size and liquidity
    statement, not a skill one. The book is therefore scored against BOTH:

      * `mkt_vw_1m`  -- the full CRSP common-stock value-weighted market, and
      * the value-weighted return of the OPTION-COVERED universe itself,

    and the second is the one that can be believed. If a cell beats the market
    and does not beat its own universe, the edge is coverage.
    """
    from learner import evaluate, inference, features_options as FO
    if not FO.available():
        return _deferred("W5b_options_book", "features_options.parquet not built")
    df = _panel()
    df, join_note = FO.attach(df)
    sigs = {
        "cp_iv_spread_30d": +1.0,      # calls rich -> long
        "skew_25d_30d": -1.0,          # dear crash insurance -> avoid
    }
    have = {s: k for s, k in sigs.items() if s in df.columns}
    if not have:
        return {"verdict": "FAILED", "headline": "neither options signal is on the joined panel"}
    for s, k in have.items():
        df[f"sig_{s}"] = df[s] * k
    if len(have) == 2:
        # The combination, as RANKS: the two features are on different scales
        # (an IV difference and an IV difference) but with different dispersions,
        # and a raw sum would silently weight by variance.
        z = None
        for s in have:
            r = df.groupby("month")[f"sig_{s}"].rank(pct=True)
            z = r if z is None else z + r
        df["sig_combined"] = z

    # THE UNIVERSE'S OWN MARKET LEG. Value-weighted over exactly the rows that
    # carry a surface in that month -- the "better than what?" control.
    cov = df[df[list(have)[0]].notna() & df["fwd_1m"].notna() & df["market_cap"].notna()]
    uni = (cov.assign(_w=cov["market_cap"].clip(lower=0))
              .groupby("month")
              .apply(lambda g: float((g["_w"] * g["fwd_1m"]).sum() / g["_w"].sum())
                     if g["_w"].sum() > 0 else np.nan, include_groups=False))
    uni.name = "mkt_covered_1m"
    df = df.merge(uni.reset_index(), on="month", how="left")

    series, cells = {}, {}
    cols = [f"sig_{s}" for s in have] + (["sig_combined"] if len(have) == 2 else [])
    for col in cols:
        for bps in (10, 25):
            for hold in (None, 100):
                for mkt in ("mkt_vw_1m", "mkt_covered_1m"):
                    key = (f"{col}|{bps}bps|{'hyst' if hold else 'rebuild'}|"
                           f"{'full_mkt' if mkt == 'mkt_vw_1m' else 'covered_univ'}")
                    try:
                        bk = evaluate.book(df, col, k=50, weight="vw", cost_bps=bps,
                                           ret_col="fwd_1m", mkt_col=mkt,
                                           hold_k=hold, return_series=True)
                    except Exception as exc:                            # noqa: BLE001
                        cells[key] = {"error": f"{type(exc).__name__}: {exc}"}
                        continue
                    ser = bk.get("_series") or {}
                    cells[key] = {k: v for k, v in bk.items() if not k.startswith("_")}
                    net, m = ser.get("net"), ser.get("market")
                    if net is not None and m is not None and len(net) and net.index.equals(m.index):
                        series[key] = (net - m).astype("float64")
    if not series:
        return {"verdict": "CANNOT DETERMINE", "cells": cells,
                "headline": "no options cell produced a usable paired series"}

    # THE SHAPE, because a losing book with a winning coefficient is a question,
    # not an answer. A Fama-MacBeth beta is the average slope across the WHOLE
    # cross-section with every name weighted equally inside the month; a top-50
    # value-weighted book is the extreme tail with the weight on the largest
    # names. A signal that is monotone through the middle and flat or REVERSED
    # in its top decile produces exactly that pair of results, and the decile
    # table is the only thing that tells the two apart. This repo's own
    # `feedback_ask_the_cross_section_first` says it in one line: the quantile
    # SHAPE decides the construction.
    shape = {}
    for col in cols:
        tbl = evaluate.decile_table(df, col, "excess_vw_1m")
        if not tbl:
            continue
        top, bot = tbl[-1], tbl[0]
        mono = all(tbl[i]["mean_realized"] <= tbl[i + 1]["mean_realized"]
                   for i in range(len(tbl) - 1))
        # Is the TOP decile still going the right way, or has it turned over?
        turn = (len(tbl) >= 3
                and tbl[-1]["mean_realized"] < tbl[-2]["mean_realized"])
        shape[col] = {
            "deciles": [{"d": r["decile"], "n": r["n"],
                         "mean_realized_pct": round(r["mean_realized"] * 100, 4)}
                        for r in tbl],
            "top_minus_bottom_pct": round((top["mean_realized"] - bot["mean_realized"]) * 100, 4),
            "monotone_increasing": bool(mono),
            "top_decile_turns_over": bool(turn),
            "reading": ("the top decile is NOT the best decile -- a book that holds only "
                        "the top will underperform a regression that used all of them"
                        if turn else
                        "the top decile is the best decile; the book's loss is not a "
                        "shape problem"),
        }

    wide = pd.concat(series, axis=1).dropna()
    fam = {k: wide[k].tolist() for k in wide.columns}
    # THE CHAMPION IS CHOSEN AMONG THE CELLS MEASURED AGAINST THE COVERED
    # UNIVERSE. Ranking over both benchmarks would let a coverage artefact win.
    covered = {k: v for k, v in fam.items() if k.endswith("covered_univ")}
    pool = covered or fam
    best = max(pool, key=lambda k: float(np.mean(pool[k])))
    inf = inference.full_report(fam[best], family=fam, paired_excess=fam,
                                n_trials=len(cells) or len(fam), n_boot=500, seed=17)
    eras = era_sign_table(wide[best])
    twin = best.replace("covered_univ", "full_mkt")
    pw = inf.get("power", {})
    return {
        "question": ("do the two surviving options coefficients survive becoming a "
                     "cost-bearing top-50 book, against their OWN universe?"),
        "family_id": "weekend-W5b-options-book",
        "join": join_note,
        "signals": {s: ("long high" if k > 0 else "long low") for s, k in have.items()},
        "benchmarks": {
            "mkt_vw_1m": "full CRSP common-stock value-weighted market",
            "mkt_covered_1m": ("value-weighted return of the option-covered universe -- "
                               "the honest comparison, because only 72.9% of panel rows "
                               "carry a surface and the missing 27% are the small and "
                               "illiquid"),
        },
        "cells_looked_at": len(cells),
        "cells": cells,
        "cross_section_shape": shape,
        "why_a_winning_coefficient_can_lose_money": (
            "the Fama-MacBeth t is the average slope over the WHOLE cross-section with "
            "every name weighted equally inside the month; this book is the top 50 only, "
            "value-weighted. If a cell loses GROSS -- before a penny of cost -- the "
            "spread is not the problem and `cross_section_shape` is where the answer is."),
        "n_common_months": int(len(wide)),
        "best_cell": best,
        "best_vs_full_market_twin": {"cell": twin,
                                     "mean_monthly_excess_pct": (
                                         round(float(np.mean(fam[twin])) * 100, 4)
                                         if twin in fam else None)},
        "best_mean_monthly_excess_pct": round(float(np.mean(fam[best])) * 100, 4),
        "inference": inf,
        "era_sign_table": eras,
        "headline": (f"best of {len(cells)} options-book cells is {best} at "
                     f"{np.mean(fam[best]) * 100:+.3f}%/month over {len(wide)} months; "
                     f"DSR {(inf.get('deflated_sharpe') or {}).get('dsr')}, "
                     f"SPA p {(inf.get('spa') or {}).get('p_spa_consistent')}, "
                     f"PBO {(inf.get('pbo') or {}).get('pbo')}, t2 needs "
                     f"{pw.get('years_needed_for_t2')}y vs {pw.get('years_observed')}y"),
        "verdict": verdict_from(inf, eras),
    }


def W5c_options_exclusion(variant: int = 0) -> dict:
    """THE OPTIONS SIGNAL IS A BOTTOM-DECILE OBJECT. Use it as an EXCLUSION.

    W5b settled the shape question. Both surviving options features carry their
    whole effect in decile 1 and are flat above it:

        cp_iv_spread_30d, mean realised excess by signal decile (%/month)
        d1     d2     d3     d4     d5     d6     d7     d8     d9     d10
        -0.619 -0.047 +0.179 +0.089 +0.171 +0.182 +0.104 +0.089 +0.061 -0.032

    The Fama-MacBeth t of +4.15 is that -0.619 in d1. Deciles 3-10 span 0.2
    percentage points and d10 is WORSE than d3-d9. So a long-only top-50 book --
    which lives entirely in d10 -- is drawn from the one region where the signal
    says nothing, which is why W5b lost GROSS.

    A signal that only marks losers has an obvious instrument that needs no short
    book and no borrow: DO NOT HOLD THEM. This job asks whether removing the
    bottom decile from an ordinary long book improves it, and it asks the
    question the honest way -- against a RANDOM exclusion of the same size, in
    the same months, on the same universe.

    THE RANDOM CONTROL IS THE POINT. Removing 10% of any universe changes a
    book: it shifts the size mix, the sector mix, and the number of names
    competing for 50 slots. An improvement that a random 10% exclusion also
    produces is not a finding about implied volatility. `feedback_run_the_control
    _you_would_not_have_chosen` is in this repo for exactly this shape.
    """
    from learner import evaluate, inference, features_options as FO
    if not FO.available():
        return _deferred("W5c_options_exclusion", "features_options.parquet not built")
    df = _panel()
    df, join_note = FO.attach(df)
    screen = "cp_iv_spread_30d"
    if screen not in df.columns:
        return {"verdict": "FAILED", "headline": f"{screen} not on the joined panel"}

    # The base books. Deliberately ORDINARY signals the house already trades on:
    # the point is whether the screen improves something real, not whether some
    # bespoke pairing can be made to look good.
    bases = {b: b for b in ("mom_12_1", "ratio", "net_rev_4w") if b in df.columns}
    if not bases:
        return {"verdict": "FAILED", "headline": "no base signal on the panel"}

    rng = np.random.default_rng(20260906)
    # The screen: bottom decile WITHIN each month, so it is a PIT cross-sectional
    # rule and never a full-sample quantile.
    q = df.groupby("month")[screen].rank(pct=True)
    df["_excluded"] = (q <= 0.10)
    # Only rows that HAVE a surface can be screened; a name with no options is
    # not "clean", it is unmeasured, and dropping it would make the screen a
    # coverage filter.
    df["_screenable"] = df[screen].notna()
    # The random control: the same COUNT of exclusions per month, drawn from the
    # same screenable rows.
    df["_rand_excluded"] = False
    for m, g in df.groupby("month"):
        elig = g.index[g["_screenable"]]
        k = int(df.loc[g.index, "_excluded"].sum())
        if k and len(elig) >= k:
            df.loc[rng.choice(elig, size=k, replace=False), "_rand_excluded"] = True

    cells, series = {}, {}
    for base in bases:
        for bps in (10, 25):
            for arm, mask in (("all", None),
                              ("minus_iv_bottom_decile", ~df["_excluded"]),
                              ("minus_RANDOM_decile", ~df["_rand_excluded"])):
                sub = df if mask is None else df[mask]
                key = f"{base}|{arm}|{bps}bps"
                try:
                    bk = evaluate.book(sub, base, k=50, weight="vw", cost_bps=bps,
                                       ret_col="fwd_1m", mkt_col="mkt_vw_1m",
                                       return_series=True)
                except Exception as exc:                                # noqa: BLE001
                    cells[key] = {"error": f"{type(exc).__name__}: {exc}"}
                    continue
                ser = bk.get("_series") or {}
                cells[key] = {k2: v for k2, v in bk.items() if not k2.startswith("_")}
                net, mkt = ser.get("net"), ser.get("market")
                if net is not None and mkt is not None and len(net) and net.index.equals(mkt.index):
                    series[key] = (net - mkt).astype("float64")

    # THE PAIRED COMPARISON. Two terminal wealths are ONE draw of a correlated
    # pair; the difference has to be tested on the SAME months.
    lifts = []
    for base in bases:
        for bps in (10, 25):
            a = series.get(f"{base}|all|{bps}bps")
            s = series.get(f"{base}|minus_iv_bottom_decile|{bps}bps")
            r = series.get(f"{base}|minus_RANDOM_decile|{bps}bps")
            if a is None or s is None:
                continue
            d_screen = (s - a).dropna()
            d_rand = (r - a).dropna() if r is not None else pd.Series(dtype="float64")
            row = {
                "base": base, "cost_bps": bps,
                "months": int(len(d_screen)),
                "screen_lift_pct_per_month": round(float(d_screen.mean()) * 100, 4),
                "screen_lift_t": (round(float(d_screen.mean() /
                                              (d_screen.std(ddof=1) / np.sqrt(len(d_screen)))), 3)
                                  if d_screen.std(ddof=1) else None),
                "random_lift_pct_per_month": (round(float(d_rand.mean()) * 100, 4)
                                              if len(d_rand) else None),
                "random_lift_t": (round(float(d_rand.mean() /
                                              (d_rand.std(ddof=1) / np.sqrt(len(d_rand)))), 3)
                                  if len(d_rand) > 2 and d_rand.std(ddof=1) else None),
                "era_sign_table": era_sign_table(d_screen),
                "power": inference.power_note(d_screen.tolist()),
            }
            # The lift OVER the random control -- the only number that is about
            # implied volatility rather than about removing 10% of a universe.
            if len(d_rand):
                dd = (d_screen - d_rand).dropna()
                row["screen_minus_random_pct_per_month"] = round(float(dd.mean()) * 100, 4)
                row["screen_minus_random_t"] = (
                    round(float(dd.mean() / (dd.std(ddof=1) / np.sqrt(len(dd)))), 3)
                    if len(dd) > 2 and dd.std(ddof=1) else None)
            lifts.append(row)

    real = [r for r in lifts
            if isinstance(r.get("screen_minus_random_t"), (int, float))
            and r["screen_minus_random_t"] >= 2.0
            and (r.get("era_sign_table") or {}).get("same_sign_in_2_of_3")]
    best = max(lifts, key=lambda r: r.get("screen_minus_random_t") or -99, default=None)
    return {
        "question": ("does removing the bottom decile of the call-put IV spread improve an "
                     "ordinary long book by MORE than removing a random decile does?"),
        "family_id": "weekend-W5c-options-exclusion",
        "screen": screen,
        "screen_rule": "drop the bottom decile WITHIN each month (PIT, never a full-sample cut)",
        "join": join_note,
        "base_signals": sorted(bases),
        "cells": cells,
        "lifts": lifts,
        "cells_where_the_screen_beats_a_RANDOM_decile": [
            f"{r['base']}@{r['cost_bps']}bps" for r in real],
        "control_note": ("removing 10% of any universe changes the size mix, the sector mix "
                         "and the number of names competing for 50 slots. The random-decile "
                         "arm is drawn from the SAME screenable rows in the SAME months, so "
                         "`screen_minus_random` is the only column that is about implied "
                         "volatility rather than about removing a tenth of a universe."),
        "headline": (f"{len(lifts)} base x cost cells; best screen-minus-random is "
                     f"{best['screen_minus_random_pct_per_month'] if best else None}%/month "
                     f"(t {best.get('screen_minus_random_t') if best else None}) on "
                     f"{best['base'] if best else '--'}@{best['cost_bps'] if best else '--'}bps; "
                     f"{len(real)} of {len(lifts)} cells beat a random decile at t >= 2 with a "
                     f"consistent era sign; best needs "
                     f"{(best.get('power') or {}).get('years_needed_for_t2') if best else None} "
                     f"years of tape for t = 2 against "
                     f"{(best.get('power') or {}).get('years_observed') if best else None} on hand"),
        # NOT "NOVEL if real else NOISE". The best cell here is +0.17%/month in
        # the right direction against a RANDOM decile and needs 64 years of tape
        # to resolve; calling that NOISE reports an absence of evidence as
        # evidence of absence, which is the single error this whole weekend was
        # built to stop making. A search only earns the word NOISE when it HAD
        # the power and still found nothing.
        "verdict": screen_verdict(
            real, len(lifts),
            (best or {}).get("era_sign_table") or {}, (best or {}).get("power"),
            corrected=("beats a RANDOM decile of the same size at t >= 2 with a "
                       "consistent era sign" if real else None)),
        "power_of_the_best_cell": (best or {}).get("power"),
    }


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
    # THE VARIANTS ARE A ROBUSTNESS TEST, NOT FOUR CHANCES TO FIND SOMETHING.
    # An archetype that only exists at top-50 on a 12-month outcome is an
    # artefact of two arbitrary constants. The same three ideas surviving a
    # doubled winner set, a halved control count and a different horizon is the
    # nearest thing this panel offers to a replication -- and the evidence
    # memory needs a SECOND agreeing pass before it will promote anything.
    W7_VARIANTS = [
        {"top_n": 50, "n_match": 5, "outcome": "excess_vw_12m"},   # 0 -- the reference
        {"top_n": 100, "n_match": 3, "outcome": "excess_vw_12m"},  # 1 -- wider tail
        {"top_n": 50, "n_match": 5, "outcome": "excess_vw_6m"},    # 2 -- shorter horizon
        {"top_n": 25, "n_match": 8, "outcome": "excess_vw_12m"},   # 3 -- narrower tail
    ]
    cfg = W7_VARIANTS[variant % len(W7_VARIANTS)]
    TOP_N, N_MATCH = cfg["top_n"], cfg["n_match"]
    df = _panel()
    ycol = cfg["outcome"]
    horizon_months = int(ycol.rsplit("_", 1)[-1].rstrip("m"))
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
        # THE CONTROL POOL MUST NOT BE CONDITIONED ON THE OUTCOME, and the first
        # version of this line was. It read
        #     pool = g.drop(index=list(win.index) + list(los.index))
        # which makes "being eligible as a control" a statement about the FUTURE:
        # a control was required to be a name whose 12-month outcome landed in
        # neither tail. Any formation feature that predicts outcome DISPERSION --
        # volatility, thinness, analyst disagreement -- then differs from the
        # winners by construction, because the winners are drawn from the tail and
        # the controls are drawn from the middle *of the outcome*. The published
        # top archetype was `log_dollar_vol_20d`, a thinness measure, i.e.
        # precisely a dispersion proxy. Found by an adversarial review, 2026-09-06.
        #
        # Dropping the WINNERS is necessary (a winner cannot be its own control).
        # Dropping the LOSERS is the leak. So each side excludes only its own tail:
        # a future loser is a perfectly good control for a winner -- in fact the
        # most informative one, since it looked the same and did not become one.
        pool_w = g.drop(index=list(win.index))
        pool_l = g.drop(index=list(los.index))
        if min(len(pool_w), len(pool_l)) < N_MATCH * 2:
            continue
        # ONE RANK SCALE FOR BOTH SIDES. The first version ranked candidates
        # within the reduced pool and targets within the full month, so a
        # percentile meant different things on the two sides of the same distance
        # calculation -- and because the removed names skew small, a winner was
        # matched to a systematically smaller name, biasing exactly the dimension
        # the match exists to neutralise.
        gr = {c: g[c].rank(pct=True) for c in on}

        def _controls(target_idx, pool):
            picks = []
            for i in target_idx:
                cand = pool
                if "sector" in pool.columns and pd.notna(g.at[i, "sector"]):
                    same = pool[pool["sector"] == g.at[i, "sector"]]
                    if len(same) >= N_MATCH:
                        cand = same
                d2 = sum((gr[c].loc[cand.index] - gr[c].at[i]) ** 2 for c in on)
                picks.extend(d2.nsmallest(N_MATCH).index.tolist())
            return pool.loc[list(dict.fromkeys(picks))]

        cw = _controls(win.index, pool_w)
        cl = _controls(los.index, pool_l)
        if not len(cw) or not len(cl):
            continue
        months_used.append(str(m))
        # (month, value) PAIRS, not a bare list. A feature with incomplete
        # coverage contributes on a SCATTERED subset of months, and appending
        # bare values then zipping them against `months_used[:len(vals)]` stamps
        # them onto the FIRST n months instead of the ones they came from -- a
        # clean, wrong era table. Live on this panel: `ratio` has 292 values
        # against 297 formation months. Found by a code review, 2026-09-06.
        for c in feats:
            if win[c].notna().sum() >= 10 and cw[c].notna().sum() >= 10:
                diffs_w[c].append((str(m), float(win[c].mean() - cw[c].mean())))
            if los[c].notna().sum() >= 10 and cl[c].notna().sum() >= 10:
                diffs_l[c].append((str(m), float(los[c].mean() - cl[c].mean())))
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
            s = pd.Series({m: v for m, v in vals}).sort_index()
            s.index.name = "month"
            oc = EV.overlap_corrected(s, horizon_months)
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
                        "overlap_note": (f"the outcome is a {horizon_months}-month return "
                                         "sampled monthly; "
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
        "variant_config": cfg,
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
        "verdict": screen_verdict(
            arche_holm or arche, len(w),
            (arche[0].get("era_sign_table") if arche else {}) or {},
            (arche[0].get("power") if arche else None),
            corrected=(f"Holm <= 0.05 on the non-overlapping t, {len(arche_holm)} of "
                       f"{len(arche)} candidates" if arche_holm else None)),
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


def _oos_t(s):
    """t on the 1999-2012 half only -- the years the S28 claim never saw."""
    o = s[[i for i in s.index if str(i) < "2013-01"]]
    if len(o) < 3 or o.std(ddof=1) == 0:
        return None
    return round(float(o.mean() / (o.std(ddof=1) / np.sqrt(len(o)))), 3)


def W6b_liquidity_band(variant: int = 0) -> dict:
    """S28's LIQUIDITY BAND, tested out of sample on 26 years.

    WHY THIS IS A REPLICATION AND NOT A POST-HOC FIT -- the distinction is the
    whole value of the job. On 2026-08-30, session 28 reported an edge inside a
    liquidity BAND of roughly $100k-$10m of dollar volume a day (+6.98%, t 2.22),
    on the 2013-2024 window. That is a PRIOR claim, made on a different window,
    with a stated direction and stated edges.

    W7b then re-derived the same shape from a completely different direction: the
    `thin_for_size` leg of the winner/matched-loser archetype is an INVERTED U --
    moderately thin is +0.20%/month, extremely thin is -0.11%/month, and
    top-minus-bottom is NEGATIVE. Choosing the middle deciles after seeing that
    would be fitting the sample. Testing S28's already-published edges on
    1999-2024 is not: 1999-2012 is fourteen years the original claim never saw.

    So the receipt reports THREE things and refuses to collapse them:
      * the band's excess on the FULL 26 years,
      * the band's excess on 1999-2012 ONLY -- the genuinely out-of-sample half, and
      * the same band with the edges moved, so a reader can see whether the
        result is about these edges or about any middle.

    A replication that only reports the pooled number has hidden the one column
    that makes it a replication.
    """
    from learner import evaluate, inference
    df = _panel()
    col = "log_dollar_vol_20d"
    if col not in df.columns:
        return {"verdict": "FAILED", "headline": f"{col} not on the panel"}
    dv = np.expm1(df[col])                       # back to dollars/day
    # S28's published edges. NOT tuned here; quoted.
    BANDS = {
        "S28_100k_10m": (1e5, 1e7),
        "wider_50k_50m": (5e4, 5e7),
        "narrower_500k_5m": (5e5, 5e6),
        "below_the_band": (0.0, 1e5),
        "above_the_band": (1e7, np.inf),
    }
    # THE BENCHMARK THIS TEST ACTUALLY NEEDS, and the trap it was built with.
    #
    # `excess_vw_1m` is a name's return minus the VALUE-WEIGHTED market. Average
    # it EQUAL-WEIGHT over any broad set of names and 1999-2012 comes out
    # strongly positive -- not because those names were special, but because EW
    # beat VW enormously in that decade. The first version of this job did
    # exactly that and made every band look like a replication, INCLUDING the
    # `above_the_band` control at t 2.06. `learner/dataset.py` states the rule it
    # broke: an EW benchmark is a SIZE ARTEFACT, a small-cap portfolio wearing a
    # market's name.
    #
    # So the band is measured against the EQUAL-WEIGHTED REST OF THE UNIVERSE in
    # the same months -- same weighting on both legs, so the EW-vs-VW regime
    # cancels and what is left is whether BEING IN THE BAND pays.
    ew_all = (df[df["excess_vw_1m"].notna()]
              .groupby("month")["excess_vw_1m"].mean().sort_index())

    rows, series = [], {}
    for name, (lo, hi) in BANDS.items():
        m = dv.between(lo, hi)
        sub = df[m & df["excess_vw_1m"].notna()]
        if sub["month"].nunique() < 24:
            rows.append({"band": name, "verdict": "CANNOT DETERMINE",
                         "months": int(sub["month"].nunique())})
            continue
        # The band's own EQUAL-WEIGHT monthly excess: the question is whether
        # BEING in the band pays, not whether some signal inside it pays.
        s = sub.groupby("month")["excess_vw_1m"].mean().sort_index()
        # vs the equal-weighted rest of the universe, on exactly the same months.
        rest = (df[~m & df["excess_vw_1m"].notna()]
                .groupby("month")["excess_vw_1m"].mean().sort_index())
        vs_rest = (s - rest).dropna()
        vs_all = (s - ew_all.reindex(s.index)).dropna()
        series[name] = s
        oos = s[[str(i) for i in s.index if str(i) < "2013-01"]]
        pw = inference.power_note(s.tolist())
        rows.append({
            "band": name, "dollar_vol_per_day": [lo, None if hi == np.inf else hi],
            "months": int(len(s)),
            "name_months": int(len(sub)),
            "mean_monthly_excess_pct": round(float(s.mean()) * 100, 4),
            "annualised_excess_pct": round(float(s.mean()) * 12 * 100, 3),
            "t": (round(float(s.mean() / (s.std(ddof=1) / np.sqrt(len(s)))), 3)
                  if s.std(ddof=1) else None),
            # THE NUMBER THAT IS ABOUT THE BAND. Same weighting on both legs, so
            # the EW-vs-VW regime cancels instead of being counted as an edge.
            "VS_EW_REST_OF_UNIVERSE": {
                "months": int(len(vs_rest)),
                "annualised_excess_pct": (round(float(vs_rest.mean()) * 12 * 100, 3)
                                          if len(vs_rest) else None),
                "t": (round(float(vs_rest.mean() /
                                  (vs_rest.std(ddof=1) / np.sqrt(len(vs_rest)))), 3)
                      if len(vs_rest) > 2 and vs_rest.std(ddof=1) else None),
                "oos_1999_2012_t": _oos_t(vs_rest),
                "era_sign_table": era_sign_table(vs_rest),
                "power": inference.power_note(vs_rest.tolist()),
            },
            "vs_ew_whole_universe_t": (
                round(float(vs_all.mean() / (vs_all.std(ddof=1) / np.sqrt(len(vs_all)))), 3)
                if len(vs_all) > 2 and vs_all.std(ddof=1) else None),
            "OUT_OF_SAMPLE_1999_2012": {
                "months": int(len(oos)),
                "mean_monthly_excess_pct": (round(float(oos.mean()) * 100, 4)
                                            if len(oos) else None),
                "t": (round(float(oos.mean() / (oos.std(ddof=1) / np.sqrt(len(oos)))), 3)
                      if len(oos) > 2 and oos.std(ddof=1) else None),
                "note": ("fourteen years the S28 claim never saw -- this column is what "
                         "makes the job a replication rather than a re-fit"),
            },
            "era_sign_table": era_sign_table(s),
            "power": pw,
        })
    band = next((r for r in rows if r["band"] == "S28_100k_10m"), None)
    above = next((r for r in rows if r["band"] == "above_the_band"), None)
    # THE VERDICT RESTS ON `VS_EW_REST_OF_UNIVERSE`, never on the vs-VW-market
    # column. The latter is positive for EVERY band out of sample -- including
    # the above-band control at t 2.06 -- because it compares an equal-weighted
    # average to a value-weighted market across the decade EW won.
    vr = (band or {}).get("VS_EW_REST_OF_UNIVERSE") or {}
    oos_t = vr.get("oos_1999_2012_t")
    full_t = vr.get("t")
    replicated = bool(isinstance(full_t, (int, float)) and full_t >= 2.0
                      and isinstance(oos_t, (int, float)) and oos_t >= 2.0
                      and (vr.get("era_sign_table") or {}).get("holds_in_2_of_3"))
    pw = vr.get("power") or {}
    return {
        "question": ("does S28's $100k-$10m/day liquidity band survive on 1999-2024, and "
                     "in particular on the fourteen years it was never fitted to?"),
        "family_id": "weekend-W6b-liquidity-band",
        "prior_claim": ("S28, 2026-08-30: +6.98%, t 2.22, in a $100k-$10m/day dollar-volume "
                        "band on 2013-2024"),
        "why_this_is_a_replication": (
            "the band edges are QUOTED from the prior claim, not chosen here. W7b "
            "independently re-derived the same inverted-U shape from the winner/matched-"
            "loser archetype, and picking the middle deciles after seeing that would be "
            "fitting the sample. 1999-2012 is out of sample for the original claim."),
        "bands": rows,
        "the_benchmark_trap_this_job_fell_into_first": (
            "measured against the VALUE-WEIGHTED market, every band -- including the "
            "above-$10m control -- is positive out of sample at t ~2, because an "
            "equal-weighted average of names beat a value-weighted market across "
            "1999-2012. That is the EW-vs-VW regime, not the band. The verdict rests on "
            "`VS_EW_REST_OF_UNIVERSE`, which puts the same weighting on both legs."),
        "control_above_the_band_vs_rest_t": (
            ((above or {}).get("VS_EW_REST_OF_UNIVERSE") or {}).get("t")),
        "headline": (f"S28 band vs the EW REST of the universe on 26 years: "
                     f"{vr.get('annualised_excess_pct')}%/yr t {full_t}; out-of-sample "
                     f"1999-2012 t {oos_t}; (against the VW market it reads "
                     f"{(band or {}).get('annualised_excess_pct')}%/yr t "
                     f"{(band or {}).get('t')}, but so does every band); "
                     f"below-band {next((r.get('annualised_excess_pct') for r in rows if r['band'] == 'below_the_band'), None)}%/yr, "
                     f"above-band {next((r.get('annualised_excess_pct') for r in rows if r['band'] == 'above_the_band'), None)}%/yr; "
                     f"t = 2 would need {pw.get('years_needed_for_t2')}y vs "
                     f"{pw.get('years_observed')}y"),
        "verdict": ("REPLICATED" if replicated else
                    ("CANNOT DETERMINE (underpowered)"
                     if pw.get("powered") is False and pw.get("years_needed_for_t2") is not None
                     else "NOT REPLICATED")),
        "verdict_rests_on": "VS_EW_REST_OF_UNIVERSE (same weighting on both legs)",
    }


def W7b_archetype_book(variant: int = 0) -> dict:
    """THE ARCHETYPE AS A BOOK -- with the decile shape printed BEFORE the verdict.

    W7 found, on 297 formation months and against sector/size/momentum/vol-matched
    controls, that a future 12-month residual winner was: thinly traded FOR ITS
    SIZE (Holm p 0.00018, same sign in 3 of 3 eras), being UPGRADED by analysts
    (Holm p 0.0062, 3 of 3), and RATED LOWER than its twin to begin with
    (BH q 0.012, 3 of 3). Unloved, illiquid for its size, improving from a low
    base.

    That is a t-statistic, not a strategy, and W5b is this weekend's expensive
    demonstration of the difference: two options features at Fama-MacBeth t +4.15
    and -5.37 produced twenty-four book cells that all lost GROSS, because their
    whole effect lived in decile 1 and a long-only top-50 book lives in decile 10.
    So the shape is computed and reported FIRST here, before any terminal wealth,
    and the receipt is readable as a diagnosis whichever way the verdict goes.

    THE SIZE NEUTRALISATION IS NOT OPTIONAL. The archetype was DISCOVERED against
    controls matched on size; "thin dollar volume" without holding size is just a
    small-cap book, and this repo has an entire farm receipt saying a small-cap
    book is a size artefact wearing a signal's name. So the composite is
    residualised on the log-market-cap rank within each month, and an
    un-neutralised arm is run beside it so the difference is visible rather than
    asserted.
    """
    from learner import evaluate, inference
    df = _panel()
    legs = {
        "thin_for_size": ("log_dollar_vol_20d", -1.0),
        "being_upgraded": ("consensus_rev_1m", +1.0),
        "rated_low": ("consensus", -1.0),
    }
    have = {k: v for k, v in legs.items() if v[0] in df.columns}
    if len(have) < 2:
        return {"verdict": "FAILED",
                "headline": f"only {len(have)} archetype legs are on the panel"}
    # Ranks within the month: three columns on three different scales, and a raw
    # sum would silently weight by whichever has the largest dispersion.
    parts = []
    for name, (col, sign) in have.items():
        r = df.groupby("month")[col].rank(pct=True)
        df[f"_leg_{name}"] = r if sign > 0 else (1.0 - r)
        parts.append(df[f"_leg_{name}"])
    df["arch_raw"] = sum(parts) / len(parts)

    # SIZE-NEUTRAL: the residual of the composite on the size rank, within month.
    def _resid_on_size(g):
        d = g[["arch_raw", "log_market_cap"]].dropna()
        if len(d) < 30:
            return pd.Series(np.nan, index=g.index)
        X = np.column_stack([np.ones(len(d)), d["log_market_cap"].rank(pct=True).to_numpy()])
        y = d["arch_raw"].to_numpy()
        try:
            coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        except np.linalg.LinAlgError:
            return pd.Series(np.nan, index=g.index)
        out = pd.Series(np.nan, index=g.index)
        out.loc[d.index] = y - X @ coef
        return out
    df["arch_size_neutral"] = (df.groupby("month", group_keys=False)
                               .apply(_resid_on_size, include_groups=False))

    sigs = ["arch_raw", "arch_size_neutral"] + [f"_leg_{k}" for k in have]

    # THE SHAPE FIRST. W5b's lesson: a decile table would have told us in one
    # glance what twenty-four book cells took an hour to say.
    shape = {}
    for col in sigs:
        tbl = evaluate.decile_table(df, col, "excess_vw_1m")
        if not tbl:
            continue
        turn = len(tbl) >= 3 and tbl[-1]["mean_realized"] < tbl[-2]["mean_realized"]
        shape[col] = {
            "deciles_pct": [round(r["mean_realized"] * 100, 4) for r in tbl],
            "top_minus_bottom_pct": round(
                (tbl[-1]["mean_realized"] - tbl[0]["mean_realized"]) * 100, 4),
            "top_decile_turns_over": bool(turn),
            "where_the_effect_lives": ("the BOTTOM decile -- this is a short-side / "
                                       "exclusion signal, not a long one"
                                       if abs(tbl[0]["mean_realized"]) >
                                       abs(tbl[-1]["mean_realized"]) else
                                       "the TOP decile -- a long book is the right "
                                       "instrument"),
        }

    cells, series = {}, {}
    for col in sigs:
        for bps in (10, 25):
            for hold in (None, 100):
                key = f"{col}|{bps}bps|{'hyst' if hold else 'rebuild'}"
                try:
                    bk = evaluate.book(df, col, k=50, weight="vw", cost_bps=bps,
                                       ret_col="fwd_1m", mkt_col="mkt_vw_1m",
                                       hold_k=hold, return_series=True)
                except Exception as exc:                                # noqa: BLE001
                    cells[key] = {"error": f"{type(exc).__name__}: {exc}"}
                    continue
                ser = bk.get("_series") or {}
                cells[key] = {k2: v for k2, v in bk.items() if not k2.startswith("_")}
                net, mkt = ser.get("net"), ser.get("market")
                if net is not None and mkt is not None and len(net) and net.index.equals(mkt.index):
                    series[key] = (net - mkt).astype("float64")
    if not series:
        return {"verdict": "CANNOT DETERMINE", "cells": cells,
                "cross_section_shape": shape,
                "headline": "no archetype cell produced a usable paired series"}
    wide = pd.concat(series, axis=1).dropna()
    fam = {k: wide[k].tolist() for k in wide.columns}
    best = max(fam, key=lambda k: float(np.mean(fam[k])))
    inf = inference.full_report(fam[best], family=fam, paired_excess=fam,
                                n_trials=len(cells) or len(fam), n_boot=500, seed=17)
    eras = era_sign_table(wide[best])
    pw = inf.get("power", {})
    neutral = {k: v for k, v in fam.items() if k.startswith("arch_size_neutral")}
    best_neutral = (max(neutral, key=lambda k: float(np.mean(neutral[k])))
                    if neutral else None)
    return {
        "question": ("does the W7 archetype -- thin for its size, being upgraded, rated "
                     "low -- make money as a book, and is it size or is it the archetype?"),
        "family_id": "weekend-W7b-archetype-book",
        "legs": {k: {"column": v[0], "direction": "low is good" if v[1] < 0 else "high is good"}
                 for k, v in have.items()},
        "cross_section_shape": shape,
        "cells_looked_at": len(cells),
        "cells": cells,
        "best_cell": best,
        "best_mean_monthly_excess_pct": round(float(np.mean(fam[best])) * 100, 4),
        "best_SIZE_NEUTRAL_cell": best_neutral,
        "best_size_neutral_mean_monthly_excess_pct": (
            round(float(np.mean(fam[best_neutral])) * 100, 4) if best_neutral else None),
        "size_note": ("`arch_raw` vs `arch_size_neutral` is the whole question. The "
                      "archetype was DISCOVERED against size-matched controls, so an "
                      "un-neutralised book that works is a small-cap book, and the farm "
                      "has already shown a small-cap book is a size artefact wearing a "
                      "signal's name."),
        "inference": inf,
        "era_sign_table": eras,
        "headline": (f"best of {len(cells)} archetype cells is {best} at "
                     f"{np.mean(fam[best]) * 100:+.3f}%/month over {len(wide)} months "
                     f"(size-neutral best: {best_neutral} at "
                     f"{round(float(np.mean(fam[best_neutral])) * 100, 3) if best_neutral else None}"
                     f"%/month); DSR {(inf.get('deflated_sharpe') or {}).get('dsr')}, "
                     f"SPA p {(inf.get('spa') or {}).get('p_spa_consistent')}, "
                     f"t2 needs {pw.get('years_needed_for_t2')}y vs "
                     f"{pw.get('years_observed')}y"),
        "verdict": verdict_from(inf, eras),
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


def W9_survivor_books(variant: int = 0) -> dict:
    """EVERY FEATURE THAT SURVIVED ANY SCREEN THIS WEEKEND, AS A BOOK.

    The weekend's most expensive lesson (W5b) is that a feature surviving a
    Fama-MacBeth screen tells you almost nothing about whether a book built on it
    makes money: `cp_iv_spread_30d` cleared at HAC t +4.15 in 3 of 3 eras and its
    twenty-four book cells all lost GROSS, because the whole effect lived in
    decile 1 while a long top-50 book lives in decile 10.

    So this job closes the loop mechanically rather than one bespoke job at a
    time. It READS THE RECEIPTS the lab has already written, collects every
    feature any screen marked as a survivor, and books all of them in ONE family
    -- which also fixes a multiplicity problem that per-job testing hides: five
    jobs each reporting "my best cell" is a five-fold search whose deflation
    nobody was computing.

    DIRECTION IS TAKEN FROM THE SCREEN, NOT SEARCHED. A feature whose controlled
    coefficient was negative is booked LOW-first. Trying both directions and
    keeping the better one would double the family and hand the search a free
    sign, which is how a coin flip becomes a signal.

    The decile shape is computed for every survivor and reported BEFORE the
    verdict, because it is the diagnosis and the terminal wealth is only the
    symptom.
    """
    from learner import evaluate, inference, features_price as FP
    from scripts import weekend_lab as WL

    # ---- harvest the survivors the lab has already found
    #
    # AND COUNT THE SEARCH THAT PRODUCED THEM. `n_trials = len(cells)` counts the
    # BOOKS and not the screening that chose which features to book, and those
    # are not the same search. Measured on this weekend's own receipts: W6 tested
    # 7 features, W5 tested 5, and W7 tested ~49 features on each of 4 variants.
    # `target_rev_1m__xs` -- the headline -- survived in ONE of those four
    # variants, while `log_dollar_vol_20d` survived in all four. A DSR computed
    # over 24 book cells prices the second search and ignores the first, which
    # flatters exactly the thin-path survivor most.
    #
    # So the breadth is DERIVED from the receipts: every distinct
    # (feature, job, variant) that was ever examined. Deriving it beats asserting
    # a constant, and it grows automatically as the lab tries more things.
    survivors: dict[str, dict] = {}
    examined: set[tuple] = set()
    for p in sorted(WL.OUT.glob("W*_run*_v*.json")):
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except Exception:                                               # noqa: BLE001
            continue
        _jv = (r.get("job"), r.get("variant"))
        for _k in ("features", "winner_side", "loser_side", "archetype_candidates"):
            for _row in r.get(_k) or []:
                if isinstance(_row, dict) and "feature" in _row:
                    examined.add((_row["feature"], *_jv, _k))
        for row in r.get("features") or []:
            t = row.get("t_fm_beta_controlled")
            eras = row.get("era_sign_table") or {}
            if (isinstance(t, (int, float)) and abs(t) >= 2.0
                    and eras.get("same_sign_in_2_of_3")):
                survivors.setdefault(row["feature"], {
                    "from": r.get("job"), "controlled_t": t,
                    "direction": "low" if t < 0 else "high"})
        for a in r.get("archetype_candidates") or []:
            holm = a.get("holm_p")
            if isinstance(holm, (int, float)) and holm <= 0.05:
                tb = a.get("t_block_non_overlapping")
                survivors.setdefault(a["feature"], {
                    "from": r.get("job"), "controlled_t": tb,
                    "direction": "low" if isinstance(tb, (int, float)) and tb < 0 else "high"})
    if not survivors:
        return {"verdict": "CANNOT DETERMINE",
                "headline": ("no receipt in the lab directory yet declares a survivor -- "
                             "this job reads what the screens found and books it, so it "
                             "has nothing to do until they have run")}

    df = _panel()
    if FP.available():
        df, _note = FP.attach(df)
    try:
        from learner import features_options as FO
        if FO.available():
            df, _n2 = FO.attach(df)
    except Exception:                                                   # noqa: BLE001
        pass

    usable = {f: m for f, m in survivors.items() if f in df.columns}
    missing = sorted(set(survivors) - set(usable))
    if not usable:
        return {"verdict": "CANNOT DETERMINE", "survivors_declared": sorted(survivors),
                "not_on_the_joined_panel": missing,
                "headline": f"none of the {len(survivors)} declared survivors is a panel column"}

    shape, cells, series = {}, {}, {}
    for feat, meta in usable.items():
        sign = -1.0 if meta["direction"] == "low" else +1.0
        col = f"book_{feat}"
        df[col] = df[feat] * sign
        tbl = evaluate.decile_table(df, col, "excess_vw_1m")
        if tbl:
            lo, hi = tbl[0]["mean_realized"], tbl[-1]["mean_realized"]
            shape[feat] = {
                "booked_direction": meta["direction"],
                "controlled_t_from_the_screen": meta["controlled_t"],
                "deciles_pct": [round(r["mean_realized"] * 100, 4) for r in tbl],
                "top_minus_bottom_pct": round((hi - lo) * 100, 4),
                "top_decile_turns_over": bool(len(tbl) >= 3
                                              and tbl[-1]["mean_realized"] < tbl[-2]["mean_realized"]),
                "effect_lives_in": ("the BOTTOM decile -- an EXCLUSION or short leg is the "
                                    "instrument, not a long top-k book"
                                    if abs(lo) > abs(hi) else "the TOP decile"),
            }
        for bps in (10, 25):
            key = f"{feat}|{meta['direction']}|{bps}bps"
            try:
                bk = evaluate.book(df, col, k=50, weight="vw", cost_bps=bps,
                                   ret_col="fwd_1m", mkt_col="mkt_vw_1m",
                                   return_series=True)
            except Exception as exc:                                    # noqa: BLE001
                cells[key] = {"error": f"{type(exc).__name__}: {exc}"}
                continue
            ser = bk.get("_series") or {}
            cells[key] = {k: v for k, v in bk.items() if not k.startswith("_")}
            net, mkt = ser.get("net"), ser.get("market")
            if net is not None and mkt is not None and len(net) and net.index.equals(mkt.index):
                series[key] = (net - mkt).astype("float64")

    if not series:
        return {"verdict": "CANNOT DETERMINE", "cells": cells,
                "cross_section_shape": shape,
                "headline": "no survivor produced a usable paired series"}
    wide = pd.concat(series, axis=1).dropna()
    fam = {k: wide[k].tolist() for k in wide.columns}
    best = max(fam, key=lambda k: float(np.mean(fam[k])))
    # THE FAMILY IS THE WHOLE SEARCH, not just the books. See the harvest block.
    n_trials = len(examined) + len(cells)
    inf = inference.full_report(fam[best], family=fam, paired_excess=fam,
                                n_trials=n_trials, n_boot=500, seed=17)
    # What the DSR would have said had only the books been counted -- printed so
    # the correction is visible rather than asserted.
    inf_books_only = inference.deflated_sharpe(fam[best], n_trials=len(cells) or len(fam))
    eras = era_sign_table(wide[best])
    pw = inf.get("power", {})
    beat = [k for k, v in cells.items()
            if isinstance(v, dict) and "error" not in v
            and v.get("terminal_wealth_net") is not None
            and v.get("terminal_wealth_market_same_months") is not None
            and v["terminal_wealth_net"] > v["terminal_wealth_market_same_months"]]
    beat_gross = [k for k, v in cells.items()
                  if isinstance(v, dict) and "error" not in v
                  and v.get("terminal_wealth_gross") is not None
                  and v.get("terminal_wealth_market_same_months") is not None
                  and v["terminal_wealth_gross"] > v["terminal_wealth_market_same_months"]]
    bottom = [f for f, s in shape.items() if "BOTTOM" in s.get("effect_lives_in", "")]
    return {
        "question": ("does ANY feature that survived a screen this weekend make money as a "
                     "top-50 value-weighted book?"),
        "family_id": "weekend-W9-survivor-books",
        "survivors_harvested": {f: m for f, m in survivors.items()},
        "not_on_the_joined_panel": missing,
        "cross_section_shape": shape,
        "features_whose_effect_is_in_the_BOTTOM_decile": bottom,
        "cells_looked_at": len(cells),
        "search_breadth_feature_job_variant_rows": len(examined),
        "n_trials_used_for_the_DSR": n_trials,
        "dsr_if_only_the_books_were_counted": inf_books_only.get("dsr"),
        "why_the_bigger_family": (
            "n_trials counts the SCREENING that chose which features to book as well as the "
            "books themselves. Measured on this weekend's receipts, `target_rev_1m__xs` -- "
            "the best cell -- survived in ONE of W7's four variants while "
            "`log_dollar_vol_20d` survived in all four. A DSR over the book cells alone "
            "prices the second search and ignores the first, which flatters the thin-path "
            "survivor most."),
        "cells": cells,
        "cells_beating_the_market_NET": beat,
        "cells_beating_the_market_GROSS": beat_gross,
        "best_cell": best,
        "best_mean_monthly_excess_pct": round(float(np.mean(fam[best])) * 100, 4),
        "inference": inf,
        "era_sign_table": eras,
        "decay_reading": decay_reading(eras),
        "multiplicity_note": (f"booking all {len(usable)} survivors in ONE family is also the "
                              "multiplicity fix: five screens each reporting 'my best cell' is "
                              "a five-fold search whose deflation nobody was computing, and "
                              "the DSR here is over the whole weekend's search, not one job's"),
        "direction_note": ("each feature is booked in the direction its SCREEN found. Trying "
                           "both and keeping the better would double the family and hand the "
                           "search a free sign."),
        "headline": (f"{len(usable)} weekend survivors booked ({len(cells)} cells): "
                     f"{len(beat)} beat the market NET, {len(beat_gross)} beat it GROSS; "
                     f"{len(bottom)} of them have their effect in the BOTTOM decile "
                     f"({bottom or 'none'}), where a long top-50 book cannot reach it. "
                     f"Best {best} at {np.mean(fam[best]) * 100:+.3f}%/month, DSR "
                     f"{(inf.get('deflated_sharpe') or {}).get('dsr')}, t2 needs "
                     f"{pw.get('years_needed_for_t2')}y vs {pw.get('years_observed')}y"),
        "verdict": verdict_from(inf, eras),
    }


def W10_decay_autopsy(variant: int = 0) -> dict:
    """WHAT CHANGED IN 2016? The autopsy on the weekend's one powered result.

    W9 found the first POWERED cell of the run -- analyst target-price revisions,
    +9.64%/yr at t 2.06 over 308 months, terminal wealth 56.66 against a market
    at 13.03 -- and then found that it is over:

        1999-2007  +1.51%/month  t  2.35
        2008-2015  +0.95%/month  t  1.81
        2016-2024  -0.02%/month  t -0.03

    "It stopped working" is where most research stops. It is not an explanation
    and it does not tell anyone what to do next. This job asks which of the
    candidate mechanisms actually moved, and it reports every one of them
    including the ones that did not, because a mechanism that did NOT change is
    what rules out an explanation.

    THE CANDIDATES, each with a number attached:

    1. **The alpha was arbitraged.** Then the GROSS spread should shrink between
       eras, not just the net. If gross is intact and only net died, the story is
       costs or turnover, not crowding.
    2. **It moved to smaller names.** A value-weighted book cannot hold what a
       cap-weighted portfolio underweights. An EQUAL-WEIGHTED arm that still
       works in 2016-2024 says the effect migrated rather than died.
    3. **The signal itself changed shape.** If the cross-sectional dispersion of
       target revisions collapsed, there is simply less to sort on -- an
       information-supply story, not an arbitrage one.
    4. **Coverage changed.** More analysts per name means faster dissemination.
    5. **The horizon moved.** If a monthly rebalance is now too slow, the 1-month
       forward is the wrong target and a shorter one would still pay.

    A decayed anomaly is a lead. This is the file that says which lead.
    """
    from learner import evaluate, long_panel as LP
    df = _panel()
    sig = "target_rev_1m__xs"
    if sig not in df.columns:
        return {"verdict": "FAILED", "headline": f"{sig} is not on the panel"}
    df["_y"] = pd.to_datetime(df["entry_date"]).dt.year
    rows = []
    for era, lo, hi in LP.ERAS:
        g = df[(df["_y"] >= lo) & (df["_y"] <= hi)].copy()
        if g["month"].nunique() < 24:
            rows.append({"era": era, "note": "too few months"})
            continue
        row = {"era": era, "months": int(g["month"].nunique()),
               "name_months": int(len(g))}
        # (1) gross vs net, VW -- is the alpha gone or only the profit?
        for weight in ("vw", "ew"):
            try:
                bk = evaluate.book(g, sig, k=50, weight=weight, cost_bps=10,
                                   ret_col="fwd_1m", mkt_col="mkt_vw_1m")
            except Exception as exc:                                    # noqa: BLE001
                row[f"book_{weight}"] = {"error": f"{type(exc).__name__}: {exc}"}
                continue
            row[f"book_{weight}"] = {
                "tw_net": bk.get("terminal_wealth_net"),
                "tw_gross": bk.get("terminal_wealth_gross"),
                "tw_market": bk.get("terminal_wealth_market_same_months"),
                "annualised_excess": bk.get("annualised_excess"),
                "t": bk.get("t_stat_paired_vs_market"),
                "turnover": bk.get("mean_turnover"),
            }
        # (3) the SIGNAL's own shape: is there still anything to sort on?
        raw = "target_rev_1m"
        if raw in g.columns:
            per_month = g.groupby("month")[raw]
            row["signal_dispersion"] = {
                "median_within_month_sd": round(float(per_month.std().median()), 6),
                "median_within_month_iqr": round(float(
                    (per_month.quantile(0.75) - per_month.quantile(0.25)).median()), 6),
                "share_nonzero": round(float((g[raw].fillna(0) != 0).mean()), 4),
            }
        # (4) coverage
        if "coverage" in g.columns:
            row["coverage"] = {
                "median": float(g["coverage"].median()),
                "mean": round(float(g["coverage"].mean()), 3),
            }
        # (5) horizon: the decile spread at 1m vs 3m
        row["decile_spread"] = {}
        for h in (1, 3):
            tcol = f"excess_vw_{h}m"
            if tcol not in g.columns:
                continue
            tb = evaluate.top_minus_bottom(g, sig, tcol)
            row["decile_spread"][f"{h}m"] = {
                "mean_monthly_spread": tb.get("mean_monthly_spread"),
                "t": tb.get("t_stat"), "months": tb.get("months")}
        rows.append(row)

    def _get(era, *path):
        r = next((x for x in rows if x.get("era") == era), {})
        for k in path:
            if not isinstance(r, dict):
                return None
            r = r.get(k)
        return r

    first, last = LP.ERAS[0][0], LP.ERAS[-1][0]
    gross_then = _get(first, "book_vw", "tw_gross")
    gross_now = _get(last, "book_vw", "tw_gross")
    mkt_now = _get(last, "book_vw", "tw_market")
    ew_now_t = _get(last, "book_ew", "t")
    disp_then = _get(first, "signal_dispersion", "median_within_month_sd")
    disp_now = _get(last, "signal_dispersion", "median_within_month_sd")
    cov_then = _get(first, "coverage", "mean")
    cov_now = _get(last, "coverage", "mean")
    spread3_now = _get(last, "decile_spread", "3m", "t")

    verdicts = []
    if isinstance(gross_now, (int, float)) and isinstance(mkt_now, (int, float)):
        verdicts.append(("arbitraged_away"
                         if gross_now <= mkt_now else "gross_alpha_survives",
                         f"gross TW {gross_now} vs market {mkt_now} in {last}"))
    if isinstance(ew_now_t, (int, float)):
        verdicts.append(("migrated_to_smaller_names" if ew_now_t >= 2.0
                         else "not_a_size_migration",
                         f"equal-weighted t {ew_now_t} in {last}"))
    if isinstance(disp_then, (int, float)) and isinstance(disp_now, (int, float)) and disp_then:
        ratio = disp_now / disp_then
        verdicts.append(("signal_dispersion_collapsed" if ratio < 0.7
                         else "dispersion_intact",
                         f"within-month sd {disp_now} vs {disp_then} ({ratio:.2f}x)"))
    if isinstance(spread3_now, (int, float)):
        verdicts.append(("still_alive_at_3m" if abs(spread3_now) >= 2.0
                         else "dead_at_3m_too",
                         f"3-month decile-spread t {spread3_now} in {last}"))
    # ---- THE LEAD THE AUTOPSY OPENS. If the 1-month effect is gone and the
    # 3-month decile spread is not, the effect did not die -- it SLOWED. The
    # decile spread is not a book, so it is built here: the signal is refreshed
    # only every `hold` months and held in between, which is the same portfolio
    # a quarterly rebalance produces and cuts turnover by roughly `hold`.
    slow = {}
    for hold in (1, 3, 6):
        col = f"_slow{hold}"
        months = sorted(df["month"].unique())
        keep = {m: months[(i // hold) * hold] for i, m in enumerate(months)}
        # The signal a desk would still be holding: the value from the month the
        # book last rebalanced. Never a future month -- `keep` maps forward only
        # from an EARLIER index, so this is a carry, not a peek.
        src = df.set_index(["month", "permno"])[sig]
        asof = df["month"].map(keep)
        idx = pd.MultiIndex.from_arrays([asof, df["permno"]])
        df[col] = src.reindex(idx).to_numpy()
        for era, lo, hi in LP.ERAS:
            g = df[(df["_y"] >= lo) & (df["_y"] <= hi)]
            for bps in (10, 25):
                try:
                    bk = evaluate.book(g, col, k=50, weight="vw", cost_bps=bps,
                                       ret_col="fwd_1m", mkt_col="mkt_vw_1m")
                except Exception as exc:                                # noqa: BLE001
                    slow[f"hold{hold}m|{era}|{bps}bps"] = {
                        "error": f"{type(exc).__name__}: {exc}"}
                    continue
                slow[f"hold{hold}m|{era}|{bps}bps"] = {
                    "tw_net": bk.get("terminal_wealth_net"),
                    "tw_gross": bk.get("terminal_wealth_gross"),
                    "tw_market": bk.get("terminal_wealth_market_same_months"),
                    "annualised_excess": bk.get("annualised_excess"),
                    "t": bk.get("t_stat_paired_vs_market"),
                    "turnover": bk.get("mean_turnover"),
                }
    revived = [k for k, v in slow.items()
               if isinstance(v, dict) and "error" not in v
               and k.split("|")[1] == last
               and isinstance(v.get("t"), (int, float)) and v["t"] >= 2.0]

    # THE TEMPTING CELL, NAMED ON PURPOSE. Somebody reading this table will find
    # `hold6m` in the last era, see a terminal wealth well above the market, and
    # want it. It is written out here WITH the two numbers that kill it -- its
    # own t, and what the identical construction did in the FIRST era -- so the
    # discovery happens here rather than in three weeks with a book attached.
    tempting = []
    for k, v in slow.items():
        if not isinstance(v, dict) or "error" in v or k.split("|")[1] != last:
            continue
        tw, tm = v.get("tw_net"), v.get("tw_market")
        if not (isinstance(tw, (int, float)) and isinstance(tm, (int, float)) and tw > tm * 1.2):
            continue
        twin = k.replace(last, first)
        tv = slow.get(twin, {})
        tempting.append({
            "cell": k,
            "terminal_wealth_net": tw, "market": tm,
            "annualised_excess": v.get("annualised_excess"),
            "t": v.get("t"),
            "same_construction_in_the_first_era": {
                "cell": twin, "tw_net": tv.get("tw_net"), "market": tv.get("tw_market"),
                "t": tv.get("t")},
            "why_it_is_not_promoted": (
                f"t = {v.get('t')} on one era of a {len(slow)}-cell search, and the "
                f"identical rule returns tw_net {tv.get('tw_net')} against a market of "
                f"{tv.get('tw_market')} in {first}. A rule that only works in the era it "
                "was found in is a description of that era."),
        })

    return {
        "question": f"what changed for {sig} between {first} and {last}?",
        "family_id": "weekend-W10-decay-autopsy",
        "signal": sig,
        "by_era": rows,
        "slower_rebalance_books": slow,
        "cells_alive_in_the_LAST_era_at_t2": revived,
        "tempting_cells_that_are_NOT_promoted": tempting,
        "the_decile_spread_is_not_a_book": (
            "the 3-month DECILE SPREAD is alive in the last era at t 3.479, and the "
            "3-month BOOK is not (tw_net 4.511 vs a market of 4.864). A spread is "
            "top-decile MINUS bottom-decile, equal-weighted inside each decile; the book "
            "is the top 50 only, value-weighted. Third appearance of the same lesson this "
            "weekend -- see W5b."),
        "slow_book_note": ("the signal is refreshed every `hold` months and carried in "
                           "between -- the portfolio a quarterly rebalance produces. If the "
                           "3-month decile spread is alive while the 1-month book is dead, "
                           "the effect SLOWED rather than died, and this is where that shows "
                           "up as money or fails to."),
        "candidate_mechanisms": [{"finding": v, "evidence": e} for v, e in verdicts],
        "coverage_then_vs_now": {"mean_analysts_then": cov_then, "mean_analysts_now": cov_now},
        "why_the_negatives_matter": ("a mechanism that did NOT change is what rules an "
                                     "explanation out. All five candidates are reported, "
                                     "including the ones that moved nothing."),
        "headline": (f"{sig} decay autopsy: "
                     + "; ".join(f"{v} ({e})" for v, e in verdicts)
                     + f"; slower-rebalance cells alive in {last} at t>=2: "
                     + (", ".join(revived) if revived else "none")),
        "verdict": ("SLOWED_NOT_DEAD" if revived else "AUTOPSY"),
    }


def _long_short(df, col, k=50, cost_bps=10.0, borrow_bps_per_year=50.0,
                ret_col="fwd_1m", mkt_col="mkt_vw_1m", month_col="month"):
    """Long top-k, short bottom-k, value-weighted inside each leg.

    THE SHORT LEG IS NOT A SIGN FLIP. Three things make it a different object and
    all three are charged here:

    * **Borrow.** A short pays a fee for the locate, every day it is on. Charged
      as `borrow_bps_per_year / 12` on the short notional each month. Omitting it
      is the single most common way a paper short book invents money.
    * **Costs on BOTH legs.** Turnover is measured per leg and paid per leg.
    * **The benchmark is CASH, not the market.** A dollar-neutral book has no
      market exposure to beat, and scoring it against an index that rose 13x
      would be scoring it against a risk it does not carry.

    Returns the monthly net series and a summary. Gross is reported beside net
    and the borrow line is reported separately, because the whole question is
    which of the three -- alpha, spread, borrow -- decides the answer.
    """
    d = df[[month_col, "permno", col, ret_col, mkt_col, "market_cap",
            "log_dollar_vol_20d"]].dropna(subset=[col, ret_col, mkt_col]).copy()
    if d.empty:
        return None, {"months": 0, "note": "no rows"}
    mo = d[month_col].astype(str).str.replace("-", "", regex=False).astype("int64")
    d["_tb"] = (d["permno"].astype("int64") * 2_654_435_761 + mo * 97 + 20260902) % 1_000_003

    def _w(sel):
        w = sel["market_cap"].fillna(sel["market_cap"].median()).clip(lower=0)
        return (w / w.sum()) if w.sum() > 0 else pd.Series(1.0 / len(sel), index=sel.index)

    rows, prevL, prevS, short_dv = {}, None, None, []
    for m, chunk in d.groupby(month_col, sort=True):
        if len(chunk) < 2 * k:
            continue
        srt = chunk.sort_values([col, "_tb"], ascending=[False, True])
        L, S = srt.head(k), srt.tail(k)
        wl, ws = _w(L), _w(S)
        rl = float((wl * L[ret_col]).sum())
        rs = float((ws * S[ret_col]).sum())
        dl = dict(zip(L["permno"].astype(int), wl.to_numpy()))
        ds = dict(zip(S["permno"].astype(int), ws.to_numpy()))
        tl = 1.0 if prevL is None else 0.5 * sum(
            abs(dl.get(x, 0.0) - prevL.get(x, 0.0)) for x in set(dl) | set(prevL))
        ts = 1.0 if prevS is None else 0.5 * sum(
            abs(ds.get(x, 0.0) - prevS.get(x, 0.0)) for x in set(ds) | set(prevS))
        prevL, prevS = dl, ds
        short_dv.append(float(np.expm1(S["log_dollar_vol_20d"]).median())
                        if S["log_dollar_vol_20d"].notna().any() else np.nan)
        cost = (tl + ts) * (cost_bps / 10_000.0) * 2.0
        borrow = (borrow_bps_per_year / 10_000.0) / 12.0
        rows[m] = {
            "gross": 0.5 * (rl - rs),
            "net": 0.5 * (rl - rs) - 0.5 * cost - 0.5 * borrow,
            "long": rl, "short": rs, "turn": 0.5 * (tl + ts),
            "cost": 0.5 * cost, "borrow": 0.5 * borrow,
            "market": float(S[mkt_col].iloc[0]),
        }
    if not rows:
        return None, {"months": 0, "note": "no month produced both legs"}
    f = pd.DataFrame(rows).T.sort_index()
    net = f["net"].astype(float)
    t = float(net.mean() / (net.std(ddof=1) / np.sqrt(len(net)))) if net.std(ddof=1) else None
    yrs = len(net) / 12.0
    tw = float((1.0 + net).prod())
    return net, {
        "months": int(len(net)),
        "k": k, "cost_bps_per_side": cost_bps,
        "borrow_bps_per_year": borrow_bps_per_year,
        "terminal_wealth_net": round(tw, 4),
        "terminal_wealth_gross": round(float((1.0 + f["gross"]).prod()), 4),
        "cagr_net": round(tw ** (1 / yrs) - 1.0, 4) if yrs > 0 and tw > 0 else None,
        "mean_monthly_net": round(float(net.mean()), 5),
        "annualised_net": round(float(net.mean()) * 12, 4),
        "t_vs_cash": round(t, 3) if t is not None else None,
        "mean_turnover_per_leg": round(float(f["turn"].mean()), 3),
        "annual_cost_drag": round(float(f["cost"].mean()) * 12, 4),
        "annual_borrow_drag": round(float(f["borrow"].mean()) * 12, 4),
        "long_leg_annualised": round(float(f["long"].astype(float).mean()) * 12, 4),
        "short_leg_annualised": round(float(f["short"].astype(float).mean()) * 12, 4),
        "median_dollar_vol_of_the_SHORT_leg": (round(float(np.nanmedian(short_dv)), 0)
                                               if short_dv else None),
        "benchmark": "CASH -- a dollar-neutral book carries no market exposure to beat",
    }


def W12_short_side(variant: int = 0) -> dict:
    """THE WEEKEND'S SHAPES ALL POINT AT THE SHORT SIDE. Measure it.

    Five of the twelve survivors have their entire effect in decile 1:
    `cp_iv_spread_30d`, `skew_25d_30d`, `attention_z_5d`, `amihud_21d`, `ret_5d`.
    W5b, W7b and W10 each concluded, independently, that a long top-50 book
    cannot reach an effect that lives in the bottom decile. Nobody has measured
    the book that CAN.

    So: long the top 50, short the bottom 50, value-weighted inside each leg,
    dollar-neutral, benchmarked against CASH -- and with the two charges that
    decide whether a paper short book is real.

    THE BORROW IS CHARGED, AND ITS SENSITIVITY IS REPORTED. Omitting the locate
    fee is the commonest way a short book invents money. 50 bps/yr is general
    collateral; the bottom decile of an illiquidity or attention sort is
    precisely where names are hard to borrow, so 200 and 500 bps/yr are run as
    well and `median_dollar_vol_of_the_SHORT_leg` is printed so a reader can see
    what is actually being shorted.

    THIS IS RESEARCH, NOT A PROPOSAL. `Mandate.allow_short` gates naked shorts on
    the live books and this job places no order, changes no mandate and proposes
    no seal. What it settles is whether the shapes were pointing at money or at
    an artefact.
    """
    from learner import inference, features_price as FP
    df = _panel()
    if FP.available():
        df, _ = FP.attach(df)
    try:
        from learner import features_options as FO
        if FO.available():
            df, _ = FO.attach(df)
    except Exception:                                                   # noqa: BLE001
        pass
    # Direction from the screens, never searched.
    sigs = {"cp_iv_spread_30d": +1.0, "skew_25d_30d": -1.0,
            "attention_z_5d": +1.0, "amihud_21d": -1.0, "ret_5d": -1.0}
    have = {s: k for s, k in sigs.items() if s in df.columns}
    if not have:
        return _deferred("W12_short_side", "no bottom-decile survivor is on the panel")
    for s, k in have.items():
        df[f"ls_{s}"] = df[s] * k

    cells, series = {}, {}
    for s in have:
        for bps in (10, 25):
            for borrow in (50.0, 200.0, 500.0):
                key = f"{s}|{bps}bps|borrow{int(borrow)}"
                net, summ = _long_short(df, f"ls_{s}", k=50, cost_bps=bps,
                                        borrow_bps_per_year=borrow)
                cells[key] = summ
                if net is not None and len(net) >= 24:
                    series[key] = net.astype("float64")
    if not series:
        return {"verdict": "CANNOT DETERMINE", "cells": cells,
                "headline": "no long-short cell produced a usable series"}
    wide = pd.concat(series, axis=1).dropna()
    fam = {k: wide[k].tolist() for k in wide.columns}
    best = max(fam, key=lambda k: float(np.mean(fam[k])))
    inf = inference.full_report(fam[best], family=fam, paired_excess=fam,
                                n_trials=len(cells), n_boot=500, seed=17)
    eras = era_sign_table(wide[best])
    pw = inf.get("power", {})
    # Does it survive the EXPENSIVE borrow? A long-short that only works at
    # general collateral is a long-short that only works on names nobody will
    # lend cheaply -- which is the same names.
    hard = {k: v for k, v in cells.items()
            if k.endswith("borrow500") and isinstance(v, dict)
            and isinstance(v.get("t_vs_cash"), (int, float))}
    survives_hard = [k for k, v in hard.items() if v["t_vs_cash"] >= 2.0]
    return {
        "question": ("the five bottom-decile survivors as a DOLLAR-NEUTRAL long-short "
                     "book -- do the shapes point at money once borrow is paid?"),
        "family_id": "weekend-W12-short-side",
        "signals": sorted(have),
        "construction": ("long top-50, short bottom-50, value-weighted inside each leg, "
                         "costs charged on BOTH legs' measured turnover, borrow charged "
                         "monthly on the short notional, benchmarked against CASH"),
        "cells_looked_at": len(cells),
        "cells": cells,
        "best_cell": best,
        "best_annualised_net_pct": round(float(np.mean(fam[best])) * 12 * 100, 3),
        "cells_surviving_500bps_borrow_at_t2": survives_hard,
        "borrow_note": ("50 bps/yr is general collateral. The bottom decile of an "
                        "illiquidity or attention sort is exactly where names are hard to "
                        "borrow, so 200 and 500 bps are run too and the short leg's median "
                        "dollar volume is printed. A long-short that only works at general "
                        "collateral only works on names nobody lends cheaply."),
        "not_a_proposal": ("Mandate.allow_short gates naked shorts on the live books. This "
                           "job places no order, changes no mandate and proposes no seal."),
        "inference": inf,
        "era_sign_table": eras,
        "headline": (f"{len(have)} bottom-decile signals as dollar-neutral long-short "
                     f"({len(cells)} cells): best {best} at "
                     f"{np.mean(fam[best]) * 12 * 100:+.2f}%/yr net vs cash, "
                     f"t {(cells.get(best) or {}).get('t_vs_cash')}; "
                     f"{len(survives_hard)} cells survive a 500bps borrow at t>=2; "
                     f"DSR {(inf.get('deflated_sharpe') or {}).get('dsr')}, t2 needs "
                     f"{pw.get('years_needed_for_t2')}y vs {pw.get('years_observed')}y"),
        "verdict": verdict_from(inf, eras),
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
    "W5b_options_book": W5b_options_book,
    "W5c_options_exclusion": W5c_options_exclusion,
    "W6_behavioural": W6_behavioural,
    "W6b_liquidity_band": W6b_liquidity_band,
    "W7_matched_loser": W7_matched_loser,
    "W7b_archetype_book": W7b_archetype_book,
    "W8_states_three_nulls": W8_states_three_nulls,
    "W9_survivor_books": W9_survivor_books,
    "W10_decay_autopsy": W10_decay_autopsy,
    "W12_short_side": W12_short_side,
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
