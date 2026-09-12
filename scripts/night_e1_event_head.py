"""E1 -- the typed-event TABULAR head, against LightGBM and against three controls.

THE QUESTION. N3 asked whether a frozen sentence embedding of the day's news
carries return-relevant information the panel's calendar does not. Twice, on
2026-09-10 and 2026-09-11, the answer was no: IC -0.0035 and -0.0032, neither
beating the SHUFFLED-TEXT control. E1 changes the REPRESENTATION, not the
panel: instead of 384 dense dimensions of "what this text is like", a sparse
table of "what KIND of thing happened, in which direction, how recently, how
often". If that also loses to SHUFFLE, the finding stops being about
embeddings and becomes about this panel's text.

TWO BARS, REPORTED SEPARATELY, NEVER COLLAPSED.

  beats SHUFFLE   is there anything in the events at all, or is it the calendar
  beats GBM       Lane M item M5, Gu-Kelly-Xiu 2020: trees are the standing bar
                  and no attention/memory architecture has cleared it on
                  cross-sectional returns. LightGBM is a CONTROL here, not a
                  competitor. `StockMixer_T1` losing to it is the expected
                  outcome and is reported as such; the feature table can still
                  be interesting under GBM while the architecture question fails.

THE TYPES ARE A PROXY. L2 (the LLM extraction) is not built. `learner/
event_head.py` says at length what stands in for it -- entity tags where they
exist plus a keyword proxy over the 39-id vocabulary -- and the receipt repeats
it in `design.typing`. A verdict from this run is a verdict about the proxy.

Licence: PRODUCT_EXPERIMENT. Nothing here claims alpha and nothing places an order.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from learner import event_head as eh                              # noqa: E402
from learner.evaluate import TRADABLE_DOLLAR_VOL                  # noqa: E402
from scripts import night_n3_frozen_embedding_head as n3          # noqa: E402
from scripts.night_checkpoint import atomic_write_json            # noqa: E402
from scripts.night_g3_evolve_v2 import COST_BPS                   # noqa: E402

JOB = "E1_event_head"
LICENCE = "PRODUCT_EXPERIMENT"
SEED = n3.SEED
ARMS = ("EVENT", "TFIDF", "SHUFFLE", "NOTEXT")
CONTROLS = ("TFIDF", "SHUFFLE", "NOTEXT")
MODELS = ("GBM", "StockMixer_T1")
HORIZONS = (5, 21)
OUT_DIR = n3.OUT_DIR


def _feature_matrices(cells: pd.DataFrame, ev: pd.DataFrame, seed: int):
    """The four arms' tables. Only the event block moves; price is shared."""
    Xev, meta = eh.build_features(cells, ev)
    Xpx = eh.price_columns(cells)
    rng = np.random.default_rng(seed)
    perm = rng.permutation(len(cells))
    shuffled = Xev.to_numpy()[perm]
    Xsh = pd.DataFrame(shuffled, columns=Xev.columns, index=Xev.index)
    mats = {
        "EVENT": pd.concat([Xev, Xpx], axis=1),
        "SHUFFLE": pd.concat([Xsh, Xpx], axis=1),
        "NOTEXT": Xpx,
        "TFIDF": None,                     # fit per fold on train rows only
    }
    meta["shuffle_control"] = {
        "kind": "global permutation of the EVENT block across (symbol, entry_date)",
        "seed": int(seed),
        "fixed_points": int((perm == np.arange(len(cells))).sum()),
        "note": ("labels, dates, universe, construction and the PIT price columns are "
                 "identical; only the event-to-cell link is cut"),
    }
    return mats, meta


def _predicted_spread(pred: np.ndarray, tradable: np.ndarray) -> float:
    """The head's OWN forecast of the book's gross return for that date.

    The same names, the same decile and the same tradability filter the book
    uses, so `pred_*` and `gross_*` in the daily file are a forecast and its
    realisation on one scale -- which is what E3's intervals need and what a
    trailing average of past returns would NOT be.
    """
    if int(tradable.sum()) < n3.MIN_NAMES_BOOK:
        return float("nan")
    p = pred[tradable]
    k = max(1, int(round(len(p) * n3.DECILE)))
    order = np.argsort(-p)
    return float(p[order[:k]].mean() - p[order[-k:]].mean())


def run_folds(cells: pd.DataFrame, mats: dict, embargo: int, seed: int = SEED,
              verbose: bool = True, with_mixer: bool = True):
    """Purged expanding walk-forward by month, embargo = max(5, horizon)."""
    dates = cells["entry_date"].to_numpy()
    months = cells["entry_date"].dt.to_period("M").astype(str).to_numpy()
    y = cells["y"].to_numpy(dtype=float)
    syms = cells["symbol"].to_numpy()
    texts = cells["text"].to_numpy()
    tradable = cells["pit_dv_21"].to_numpy(dtype=float) >= TRADABLE_DOLLAR_VOL
    sessions = np.array(sorted(pd.unique(dates)))
    uniq_months = sorted(set(months))

    daily, fold_log = [], []
    models = MODELS if with_mixer else ("GBM",)
    for mi in range(n3.MIN_TRAIN_MONTHS, len(uniq_months)):
        mo = uniq_months[mi]
        te = months == mo
        if te.sum() < n3.MIN_NAMES_IC:
            continue
        cut_i = int(np.searchsorted(sessions, dates[te].min())) - int(embargo)
        if cut_i <= 0:
            continue
        tr = dates < sessions[cut_i]
        if tr.sum() < 500:
            continue

        preds, info = {}, {}
        for arm in ARMS:
            if arm == "TFIDF":
                Ztr, Zte, tf = n3._tfidf_svd(list(texts[tr]), list(texts[te]), seed + mi)
                cols = [f"svd_{i}" for i in range(Ztr.shape[1])]
                Xtr = pd.DataFrame(Ztr, columns=cols)
                Xte = pd.DataFrame(Zte, columns=cols)
                info["tfidf"] = tf
            else:
                Xtr = mats[arm].loc[tr].reset_index(drop=True)
                Xte = mats[arm].loc[te].reset_index(drop=True)
            for model in models:
                if model == "GBM":
                    p, mi_ = eh.fit_predict_gbm(Xtr, y[tr], Xte, seed=seed + mi)
                else:
                    p, mi_ = eh.fit_predict_stockmixer(Xtr, y[tr], dates[tr], Xte, dates[te],
                                                       seed=seed + mi,
                                                       min_names=n3.MIN_NAMES_BOOK)
                preds[(model, arm)] = p
                info.setdefault(model, mi_)

        d_te, y_te, s_te, t_te = dates[te], y[te], syms[te], tradable[te]
        for d in np.unique(d_te):
            k = d_te == d
            if k.sum() < n3.MIN_NAMES_IC:
                continue
            row = {"date": pd.Timestamp(d), "month": mo, "n": int(k.sum()),
                   "n_tradable": int(t_te[k].sum())}
            for (model, arm), p in preds.items():
                row[f"ic_{model}_{arm}"] = n3._spearman(p[k], y_te[k])
                g, w = n3._book_day(p[k], y_te[k], s_te[k], t_te[k])
                row[f"gross_{model}_{arm}"] = g
                row[f"pred_{model}_{arm}"] = _predicted_spread(p[k], t_te[k])
                row[f"w_{model}_{arm}"] = w
            daily.append(row)
        fold_log.append({"test_month": mo, "n_train": int(tr.sum()), "n_test": int(te.sum()),
                         "train_cut_session": str(pd.Timestamp(sessions[cut_i]).date()),
                         "models": {k: v for k, v in info.items() if k in MODELS},
                         "tfidf": info.get("tfidf")})
        if verbose:
            print(f"[fold] {mo}  train {int(tr.sum()):>7}  test {int(te.sum()):>6}", flush=True)

    if not daily:
        return pd.DataFrame(), fold_log
    dd = pd.DataFrame(daily).sort_values("date").reset_index(drop=True)
    for model in models:
        for arm in ARMS:
            key = f"{model}_{arm}"
            prev, to, net = {}, [], []
            for w, g in zip(dd[f"w_{key}"].to_numpy(), dd[f"gross_{key}"].to_numpy()):
                if not w:
                    to.append(float("nan"))
                    net.append(float("nan"))
                    continue
                t = n3._turnover(prev, w)
                to.append(t)
                net.append(g - t * COST_BPS / 1e4 if np.isfinite(g) else float("nan"))
                prev = w
            dd[f"turnover_{key}"] = to
            dd[f"net_{key}"] = net
            dd.drop(columns=[f"w_{key}"], inplace=True)
    return dd, fold_log


def grade(dd: pd.DataFrame, models=MODELS) -> dict:
    """Per era and per model. Six control comparisons, Holm inside the family."""
    dd = dd.copy()
    dd["era"] = dd["date"].dt.to_period("Q").astype(str)
    out = {"eras": {}}
    for era in ["ALL"] + sorted(dd["era"].unique()):
        sl = dd if era == "ALL" else dd[dd["era"] == era]
        cell = {"n_dates": int(len(sl)),
                "dates": [str(sl["date"].min().date()), str(sl["date"].max().date())],
                "median_names_per_date": int(sl["n"].median()),
                "median_tradable_per_date": int(sl["n_tradable"].median()),
                "arms": {}, "vs_controls": {}}
        for model in models:
            cell["arms"][model] = {}
            for arm in ARMS:
                key = f"{model}_{arm}"
                cell["arms"][model][arm] = {
                    "ic": n3._cell(sl[f"ic_{key}"].to_numpy(dtype=float), False),
                    "gross": n3._cell(sl[f"gross_{key}"].to_numpy(dtype=float), True),
                    "net": n3._cell(sl[f"net_{key}"].to_numpy(dtype=float), True),
                    "mean_daily_turnover": round(float(np.nanmean(
                        sl[f"turnover_{key}"].to_numpy(dtype=float))), 4),
                    "cost_bps_per_unit_turnover": COST_BPS,
                }
            for c in CONTROLS:
                cell["vs_controls"][f"{model}:EVENT_minus_{c}"] = {
                    "ic": n3._cell((sl[f"ic_{model}_EVENT"] - sl[f"ic_{model}_{c}"])
                                   .to_numpy(dtype=float), False),
                    "net": n3._cell((sl[f"net_{model}_EVENT"] - sl[f"net_{model}_{c}"])
                                    .to_numpy(dtype=float), True),
                }
        if "StockMixer_T1" in models and "GBM" in models:
            cell["vs_controls"]["StockMixer_T1_minus_GBM_on_EVENT"] = {
                "ic": n3._cell((sl["ic_StockMixer_T1_EVENT"] - sl["ic_GBM_EVENT"])
                               .to_numpy(dtype=float), False),
                "net": n3._cell((sl["net_StockMixer_T1_EVENT"] - sl["net_GBM_EVENT"])
                                .to_numpy(dtype=float), True),
            }
        out["eras"][era] = cell

    # The Holm family is the SIX EVENT-vs-control comparisons. The architecture
    # comparison (StockMixer_T1 vs GBM) is a different question with a different
    # decision attached, and sweeping it into the same family would both inflate
    # the correction on the controls and hide the M5 bar inside a multiplicity
    # adjustment it was never part of.
    fam = {k: v for k, v in out["eras"]["ALL"]["vs_controls"].items() if ":EVENT_minus_" in k}
    ps = sorted(((k, v["ic"]["p"]) for k, v in fam.items() if v["ic"]["p"] is not None),
                key=lambda kv: kv[1])
    holm, mx = {}, None
    for i, (k, p) in enumerate(ps):
        adj = min(1.0, p * (len(ps) - i))
        adj = max(adj, max(list(holm.values()) or [0.0]))
        holm[k] = round(adj, 4)
        mx = adj if mx is None else max(mx, adj)
    out["holm_adjusted_p_all_era_ic"] = holm
    out["holm_family_size"] = len(ps)
    out["family_max_p"] = round(float(mx), 4) if mx is not None else None
    return out


def verdict(g: dict, models=MODELS) -> tuple[str, dict]:
    """TWO lines, never one. `beats GBM` and `beats shuffle` are different facts."""
    a = g["eras"]["ALL"]
    holm = g["holm_adjusted_p_all_era_ic"]
    lines, beats_shuffle = {}, {}
    for model in models:
        s = a["vs_controls"][f"{model}:EVENT_minus_SHUFFLE"]["ic"]
        key = f"{model}:EVENT_minus_SHUFFLE"
        ok = ((s["mean"] or 0) > 0 and holm.get(key) is not None and holm[key] < 0.05)
        beats_shuffle[model] = bool(ok)
        lines[f"beats_shuffle_{model}"] = (
            f"{model}: EVENT - SHUFFLE IC {s['mean']:+.4f} (t {s['t']}, Holm p "
            f"{holm.get(key)}) over {s['n_date_blocks']} date blocks -> "
            f"{'YES' if ok else 'NO'}")
    if "StockMixer_T1" in models and "GBM" in models:
        m = a["vs_controls"]["StockMixer_T1_minus_GBM_on_EVENT"]["ic"]
        beats_gbm = (m["mean"] or 0) > 0 and (m["t"] or 0) > 2.0
        lines["beats_gbm"] = (
            f"StockMixer_T1 - GBM on the identical table: IC {m['mean']:+.4f} (t {m['t']}, "
            f"p {m['p']}) -> {'YES' if beats_gbm else 'NO'}")
    else:
        beats_gbm = False
        lines["beats_gbm"] = "StockMixer_T1 did not run, so the architecture question is CANNOT DETERMINE"

    if not any(beats_shuffle.values()):
        v = ("FAILED_VARIANT: no model's typed-event arm beats the SHUFFLED-EVENT control, so "
             "what either earns is the panel's calendar and universe, not the events. This "
             "closes the KEYWORD PROXY, not typed events -- L2's LLM extraction has not run.")
    elif not beats_gbm:
        v = ("FAILED_VARIANT for the ARCHITECTURE (StockMixer_T1 does not beat LightGBM on the "
             "identical table, which is the Gu-Kelly-Xiu prior holding) -- AND "
             "PRODUCT_PROMISING (CONDITIONAL) for the FEATURE TABLE under GBM, which beats "
             "shuffled events. One era, 2025-26, no forward evidence.")
    else:
        v = ("PRODUCT_PROMISING (CONDITIONAL): the typed-event table beats shuffled events AND "
             "StockMixer_T1 beats LightGBM on the identical table and splits. One era, "
             "2025-26: a hypothesis, not a book.")
    lines["verdict"] = v
    head = " | ".join(lines[k] for k in lines if k.startswith("beats"))
    return head, lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="E1 typed-event tabular head vs GBM and three controls")
    ap.add_argument("--out", default=None)
    ap.add_argument("--run", type=int, default=1)
    ap.add_argument("--smoke", action="store_true", help="120 symbols")
    ap.add_argument("--horizon", type=int, default=5, choices=list(HORIZONS))
    ap.add_argument("--no-mixer", action="store_true",
                    help="GBM only (torch absent, or a cheap re-grade)")
    ap.add_argument("--stage", default="signal")
    args = ap.parse_args(argv)

    t0 = time.time()
    horizon = int(args.horizon)
    embargo = n3.embargo_for(horizon)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = Path(args.out) if args.out else (
        OUT_DIR / f"{JOB}_h{horizon}_run{args.run:02d}{'_smoke' if args.smoke else ''}.json")

    with_mixer = (not args.no_mixer) and eh.stockmixer_available()
    receipt = {
        "job": JOB, "licence": LICENCE, "run": args.run, "smoke": bool(args.smoke),
        "stage": args.stage, "llm_spend_usd": 0.0,
        "question": ("Does a TYPED-EVENT table -- one-hot type x direction, counts over 1/5/21 "
                     "sessions, magnitude, confidence and recency, plus N3's three PIT price "
                     "columns -- beat shuffled events, TF-IDF and no text, under LightGBM and "
                     "under a StockMixer-class head, on purged walk-forward splits?"),
        "design": {
            "horizon_sessions": horizon,
            "embargo_sessions": embargo,
            "unit": "(symbol, entry_date) cell -- one label per session, not one per headline",
            "target": n3.design_block(horizon)["target"],
            "feature_family": ("typed_event_onehot_x_direction + magnitude + confidence + "
                               "counts_1_5_21 + recency(+censored) + pit_price"),
            "models": list(MODELS) if with_mixer else ["GBM"],
            "arms": {"EVENT": "typed-event block + the three PIT price columns",
                     "TFIDF": (f"TF-IDF(1-2gram) -> {n3.SVD_COMPONENTS}-d SVD of the same text, "
                               "fit on TRAIN rows only, per fold"),
                     "SHUFFLE": "the EVENT block globally permuted across cells; price held fixed",
                     "NOTEXT": "log10 PIT 21-session median dollar volume, mom_21, mom_5"},
            "splits": (f"expanding walk-forward by month, {embargo}-session embargo, "
                       f"first test month is month {n3.MIN_TRAIN_MONTHS + 1}"),
            "book": (f"decile long-short, EW, gross exposure 1.0, {TRADABLE_DOLLAR_VOL:,.0f} PIT "
                     f"dollar-volume floor, charged on REALISED turnover sum|dw| x {COST_BPS} bps"),
            "cost_bps_per_side": COST_BPS,
            "cost_source": "scripts.night_g3_evolve_v2.COST_BPS (imported, not retyped)",
            "tradable_floor_usd": TRADABLE_DOLLAR_VOL,
            "seed": SEED,
            "gbm_is_a_control": ("Lane M item M5 / Gu-Kelly-Xiu 2020. LightGBM is the bar the "
                                 "architecture must clear, not a competitor it may lose to quietly"),
            "typing": ("PROXY -- L2's LLM extraction is NOT built. Types come from entity_tags "
                       "where present and otherwise from a keyword proxy over the 39-id "
                       "vocabulary of docs/research_notes/2026-09-11/spec_events_and_"
                       "calibration.md section 1.2. A verdict here is a verdict about the proxy."),
        },
        "inputs": [n3.PANEL.name, n3.BARS.name],
        "status": "running", "written_utc": n3._now(),
    }
    atomic_write_json(out, receipt, indent=1)

    print(f"[e1] loading the panel (horizon {horizon}, embargo {embargo})", flush=True)
    cells, _corpus, meta = n3.load_cells(smoke=args.smoke, horizon=horizon)
    receipt["panel"] = meta
    atomic_write_json(out, receipt, indent=1)

    print("[e1] typing the corpus with the proxy", flush=True)
    ev = eh.extract_events(cells[["symbol", "entry_date", "text"]])
    mats, fmeta = _feature_matrices(cells, ev, SEED)
    tagged = int((ev["basis"] == "entity_tag").sum()) if len(ev) else 0
    fmeta["typing_coverage"] = {
        "cells": int(len(cells)),
        "cells_with_at_least_one_event": int(ev.groupby(["symbol", "entry_date"]).ngroups) if len(ev) else 0,
        "event_rows": int(len(ev)),
        "event_rows_from_entity_tags": tagged,
        "event_rows_from_keyword_proxy": int(len(ev)) - tagged,
        "note": ("entity_tags contribute 0 on the 2025-26 panel: the tagged corpus starts "
                 "2026-09-11 and this panel predates it. The path is live and will show a "
                 "number the day the corpus reaches back."),
    }
    receipt["features"] = fmeta
    atomic_write_json(out, receipt, indent=1)
    print(f"[e1] {len(ev):,} event rows, {fmeta['n_feature_columns']} feature columns, "
          f"{len(fmeta['kept_types'])} types kept, {len(fmeta['dropped_sparse_types'])} dropped",
          flush=True)

    dd, folds = run_folds(cells, mats, embargo=embargo, with_mixer=with_mixer)
    if dd.empty:
        receipt["status"] = "REFUSED"
        receipt["verdict"] = ("REFUSED: no gradable test date -- the panel is too short for the "
                              "split schedule at this horizon")
        receipt["written_utc"] = n3._now()
        atomic_write_json(out, receipt, indent=1)
        print(receipt["verdict"])
        return 2

    models = MODELS if with_mixer else ("GBM",)
    g = grade(dd, models=models)
    head, lines = verdict(g, models=models)
    daily_path = out.with_name(out.stem + "_daily.csv")
    dd.to_csv(daily_path, index=False)

    receipt["folds"] = folds
    receipt["results"] = g
    receipt["family_max_p"] = g["family_max_p"]
    receipt["beats_shuffle"] = {k: v for k, v in lines.items() if k.startswith("beats_shuffle")}
    receipt["beats_gbm"] = lines["beats_gbm"]
    receipt["headline"] = head
    receipt["verdict"] = lines["verdict"]
    receipt["next_test"] = (
        "L2's LLM extraction over the same cells, graded through this identical table, splits, "
        "book and controls -- the ONLY difference being how the events were typed. That is what "
        "separates 'typed events do not work here' from 'a keyword proxy does not work here'.")
    receipt["daily_csv"] = str(daily_path)
    receipt["status"] = "done"
    receipt["elapsed_s"] = round(time.time() - t0, 1)
    receipt["written_utc"] = n3._now()
    atomic_write_json(out, receipt, indent=1)

    print("\n" + head)
    print(lines["verdict"])
    print(f"receipt: {out}")
    return 0


def E1_event_head(smoke: bool = False, run: int = 1, horizon: int = 5) -> dict:
    """Adapter for `scripts.night_factory_jobs.JOBS`."""
    import os
    horizon = int(os.getenv("AEGIS_E1_HORIZON", str(horizon)))
    out = OUT_DIR / f"{JOB}_h{horizon}_run{run:02d}{'_smoke' if smoke else ''}.json"
    argv = ["--run", str(run), "--out", str(out), "--horizon", str(horizon)]
    if smoke:
        argv.append("--smoke")
    rc = main(argv)
    payload = json.loads(out.read_text(encoding="utf-8"))
    if rc != 0:
        payload.setdefault("status", "REFUSED")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
