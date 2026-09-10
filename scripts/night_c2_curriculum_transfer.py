"""C2 -- DOES MADE-UP NEWS TEACH A NET ANYTHING ABOUT REAL RETURNS?

    python -m scripts.night_c2_curriculum_transfer --smoke
    python -m scripts.night_c2_curriculum_transfer

THE QUESTION, AND WHY IT IS ASKABLE FOR THE FIRST TIME TONIGHT
==============================================================
C1 spent the night of 09-08 generating a curriculum at $0: 4,669 anonymised
real headlines, each with three counterfactuals that change exactly ONE causal
element (the sign, the magnitude, the actor/timing) and carry the direction
that change implies. ~18.7k texts. Nothing has ever read it -- a grep for
`C1_counterfactual_news` across scripts/ and backend/ returns the generator and
nothing else. It was written and left on disk.

E1 has just built the other half: real 2025-26 headlines joined to the Alpaca
bar of the first session that opens after publication.

So: pretrain a net on INVENTED text whose labels are what a careful reader
would infer, then ask whether that pretraining helps it predict what the market
ACTUALLY did on REAL text it has never seen. That is the whole of Murat's
"made-up news so it can find logic, reason and learn", stated as something that
can come back FALSE.

WHAT THE CURRICULUM CAN AND CANNOT TEACH
========================================
Its `direction` is declared by the generator, so it can only ever teach the map
    text -> what a reader would infer
and never
    text -> what the market did.
The money labels are ALWAYS E1's realised excess returns. We never tell a
network that an invented story caused +8%; that would teach it our imagination.

THE CONTROL IS THE POINT (three arms, one capacity)
===================================================
    BASELINE   head fit on the panel from the shared text features alone
    TRANSFER   head fit on the hidden layer of a net pretrained on the curriculum
    CONTROL    identical net, identical capacity, pretrained on the SAME
               curriculum with its direction labels SHUFFLED

CONTROL exists because of N2, four days ago: eight real event columns were
worth +2.267%/yr and eight DATELESS columns were worth +2.780 -- the gain was
matrix capacity, not the earnings print ([[feedback-a-control-that-shares-the-
construction-can-win]]). A transfer arm that beats BASELINE but not CONTROL has
demonstrated that 256 extra hidden units help, which we already knew.

MEASUREMENT
===========
Walk-forward by date: fold k trains on every session before the fold and is read
on the fold itself; no fold is ever revisited. The unit is a DATE, not a
name-day -- pooling name-days printed t -65 where the honest portfolio series
printed t -16.6 ([[feedback-name-days-are-not-periods]]). Each date yields ONE
return: equal-weight long the top predicted decile, short the bottom, from names
above the $3m/day dollar-volume floor ([[feedback-apply-the-execution-floor-
before-believing-the-book]]). Costs are charged at 25 bps per side of turnover;
`zero_cost_diagnostic` is not available here on purpose.

THE COST MODEL (amended 2026-09-10 -- run01's net line was an artefact)
======================================================================
run01 charged a FLAT 100 bps on every date: `2 * 25bps * 2`, i.e. the whole
book sold and a whole new book bought every single session, whatever the book
actually held. Gross +30.6/+19.5/+15.0 %/yr became net -221/-233/-237 %/yr,
and -237%/yr is not a number a book produces -- it is 25 bps x 2 sides x 2 legs
x 252 sessions with the trading assumption never checked against the book.
The flat charge is the CEILING of this book's cost, not its cost: it is what
`turnover_costs` returns when every name in both legs is replaced.

Costs are now charged on REALISED decile-membership turnover:
`sum |w_t - w_{t-1}| x cost_bps_per_side`, over the union of names, with the
first date paying entry and the last date paying the liquidation. A name that
is in the same leg on two consecutive sessions is CARRIED and pays nothing.
`turnover_per_rebalance` (1.0 = the whole book replaced = the old flat charge)
and `cost_bps_per_side` sit in the receipt next to every net number, and
`net_daily_liquidation` keeps the old convention so run01 stays comparable.

The label caveat, stated rather than hidden: `x_oc` is open-to-close, so a
carried name is modelled as held overnight while its return is measured only
inside the session. The realised-turnover net is therefore the LOWER cost bound
and the flat net the UPPER one; both are printed, and the verdict is read on a
difference between arms that share the construction either way.

$0. Local features, local fit, no LLM call.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import Ridge
from sklearn.neural_network import MLPClassifier

ROOT = Path(__file__).resolve().parent.parent
CURRICULUM = ROOT / "backend" / "data" / "optimus" / "night_factory_2026-09-08" / "C1_counterfactual_news.jsonl"
PANEL = ROOT / "backend" / "data" / "optimus" / "text_return_panel" / "news_returns_2025_26.parquet"
OUT = ROOT / "backend" / "data" / "optimus" / "text_return_panel"

SEED = 20260909
DOLLAR_VOL_FLOOR = 3_000_000.0        # TRADABLE_DOLLAR_VOL, the standing floor
COST_BPS_PER_SIDE = 25.0
SVD_DIM = 256
HIDDEN = (256, 128)
DIR3 = {"POSITIVE": 2, "NEUTRAL": 1, "UNCLEAR": 1, "NEGATIVE": 0}


# ----------------------------------------------------------------- curriculum
def load_curriculum(max_docs=None):
    texts, labels, kinds = [], [], []
    if not CURRICULUM.exists():
        return texts, labels, kinds
    for i, line in enumerate(CURRICULUM.open(encoding="utf-8")):
        if max_docs and i >= max_docs:
            break
        try:
            d = json.loads(line)
        except Exception:                                            # noqa: BLE001
            continue
        if d.get("status") != "OK":
            continue
        if d.get("anon") and d.get("direction") in DIR3:
            texts.append(d["anon"]); labels.append(DIR3[d["direction"]]); kinds.append("anon")
        for cf in d.get("counterfactuals") or []:
            if cf.get("text") and cf.get("direction") in DIR3:
                texts.append(cf["text"]); labels.append(DIR3[cf["direction"]])
                kinds.append(cf.get("kind") or "cf")
    return texts, labels, kinds


# ---------------------------------------------------------------------- panel
def load_panel(label="x_oc", max_rows=None):
    df = pd.read_parquet(PANEL)
    df = df[np.isfinite(df[label])]
    df = df[df["dollar_vol"].fillna(0.0) >= DOLLAR_VOL_FLOOR]
    df["text"] = (df["title"].fillna("") + ". " + df["body"].fillna("")).str.slice(0, 1200)
    df = df[df["text"].str.len() > 30]
    df = df.sort_values("entry_date").reset_index(drop=True)
    if max_rows:
        df = df.iloc[:max_rows].reset_index(drop=True)
    return df


# --------------------------------------------------------------- the three arms
def _hidden(mlp, X):
    """Forward pass to the LAST hidden layer of a fitted sklearn MLP."""
    A = X
    for W, b in zip(mlp.coefs_[:-1], mlp.intercepts_[:-1]):
        A = np.maximum(A @ W + b, 0.0)               # the MLP is relu
    return A


def _pretrain(Xc, yc, seed):
    mlp = MLPClassifier(hidden_layer_sizes=HIDDEN, max_iter=60, random_state=seed,
                        early_stopping=True, n_iter_no_change=6)
    mlp.fit(Xc, yc)
    return mlp


def _folds(dates, n_folds):
    uniq = np.array(sorted(pd.unique(dates)))
    if len(uniq) < n_folds * 4:
        n_folds = max(2, len(uniq) // 4)
    edges = np.array_split(uniq, n_folds + 1)
    for k in range(1, len(edges)):
        yield set(np.concatenate(edges[:k]).tolist()), set(edges[k].tolist())


def _daily_returns(df_te, pred, label):
    """One portfolio return per DATE: EW long top decile, short bottom decile.

    Returns the gross series AND the weight book that produced it -- the
    weights are what a cost model has to see. `+1/k` on each long name and
    `-1/k` on each short, so gross exposure is 2.0 (one unit a leg).
    """
    out, weights = [], {}
    t = df_te.assign(_p=pred)
    for day, g in t.groupby("entry_date", sort=True):
        if len(g) < 10:
            continue
        k = max(1, len(g) // 10)
        g = g.sort_values("_p")
        short, long_ = g.iloc[:k], g.iloc[-k:]
        gross = float(long_[label].mean() - short[label].mean())
        w = {}
        for nm in long_["symbol"].tolist():
            w[nm] = w.get(nm, 0.0) + 1.0 / k
        for nm in short["symbol"].tolist():
            w[nm] = w.get(nm, 0.0) - 1.0 / k
        weights[day] = w
        out.append({"date": day, "gross": gross, "n": len(g)})
    return pd.DataFrame(out), weights


# ------------------------------------------------------------- the cost model
def turnover_costs(weights_by_date, cost_bps_per_side: float = COST_BPS_PER_SIDE,
                   *, charge_entry: bool = True, charge_exit: bool = True) -> pd.DataFrame:
    """Cost of a book that CHAINS: only the CHANGE in weights is ever traded.

        traded_t   = sum over names of |w_t - w_{t-1}|
        cost_t     = traded_t * cost_bps_per_side / 1e4
        turnover_t = traded_t / (2 * gross exposure on t)

    so `turnover == 1.0` means the entire book was sold and an entirely new one
    bought -- which is the flat charge run01 applied unconditionally -- and
    `turnover == 0.0` means the book did not trade and pays NOTHING. A book
    that holds the same names forever must cost zero after entry; if this
    function ever returns a positive cost for an unchanged book, the flat
    charge has come back and `test_c2_cost_model.py` fails.

    `weights_by_date` is an ordered sequence of `(date, {name: weight})`.
    `charge_entry` charges the first date's build; `charge_exit` charges the
    final liquidation onto the last date. Both default ON because a book that
    is never bought and never sold is not a book.
    """
    rows = []
    prev: dict = {}
    items = list(weights_by_date)
    c = float(cost_bps_per_side) / 1e4
    for i, (day, w) in enumerate(items):
        if i == 0 and not charge_entry:
            traded = 0.0
        else:
            traded = sum(abs(w.get(nm, 0.0) - prev.get(nm, 0.0))
                         for nm in set(w) | set(prev))
        gross_exp = sum(abs(v) for v in w.values())
        if i == len(items) - 1 and charge_exit:
            traded += gross_exp
        rows.append({"date": day, "traded": traded,
                     "gross_exposure": gross_exp,
                     "turnover": traded / (2.0 * gross_exp) if gross_exp > 0 else 0.0,
                     "cost": traded * c})
        prev = w
    return pd.DataFrame(rows)


FLAT_LIQUIDATION_COST = 2.0 * (COST_BPS_PER_SIDE / 1e4) * 2.0   # run01's charge


def _stat(s):
    s = pd.Series(s).replace([np.inf, -np.inf], np.nan).dropna()
    if s.size < 3:
        return {"n_dates": int(s.size)}
    t = float(s.mean() / (s.std(ddof=1) / np.sqrt(s.size)))
    return {"n_dates": int(s.size), "mean_bps": round(float(s.mean()) * 1e4, 2),
            "ann_pct": round(float(s.mean()) * 252 * 100, 3), "t": round(t, 3)}


def run(smoke=False, label="x_oc", n_folds=5, max_cur_docs=None) -> dict:
    t0 = time.time()
    rng = np.random.default_rng(SEED)
    # `max_cur_docs` exists so a run can be REPRODUCED: C1 kept appending to the
    # curriculum after 09-09, so reading the whole file no longer reproduces
    # run01's inputs (18,116 texts then, 25,978 now). max_cur_docs=4851 restores
    # run01 exactly, which is how the cost-model amendment isolates the cost.
    cur_texts, cur_y, cur_kind = load_curriculum(
        max_docs=400 if smoke else max_cur_docs)
    panel = load_panel(label=label, max_rows=8000 if smoke else None)
    if not cur_texts or panel.empty:
        return {"job": "C2_curriculum_transfer", "status": "REFUSED",
                "why": f"curriculum rows {len(cur_texts)}, panel rows {len(panel)}"}

    # ONE unsupervised representation, fit on the union. Unsupervised on text
    # only -- no label of either kind touches it, so sharing it across arms is
    # what makes the three arms comparable rather than a leak.
    vec = TfidfVectorizer(min_df=3, max_features=60000, ngram_range=(1, 2),
                          strip_accents="unicode", sublinear_tf=True)
    allt = list(cur_texts) + panel["text"].tolist()
    V = vec.fit_transform(allt)
    svd = TruncatedSVD(n_components=min(SVD_DIM, V.shape[1] - 1), random_state=SEED)
    Z = svd.fit_transform(V)
    Zc, Zp = Z[:len(cur_texts)], Z[len(cur_texts):]
    yc = np.array(cur_y)

    net_true = _pretrain(Zc, yc, SEED)
    yc_shuf = yc.copy(); rng.shuffle(yc_shuf)
    net_ctrl = _pretrain(Zc, yc_shuf, SEED)
    cur_acc = float((net_true.predict(Zc) == yc).mean())
    ctrl_acc = float((net_ctrl.predict(Zc) == yc_shuf).mean())

    feats = {"BASELINE": Zp,
             "TRANSFER": _hidden(net_true, Zp),
             "CONTROL": _hidden(net_ctrl, Zp)}
    y = panel[label].to_numpy()
    dates = panel["entry_date"].to_numpy()
    series = {k: [] for k in feats}
    books = {k: {} for k in feats}
    for tr_days, te_days in _folds(dates, n_folds):
        tr = np.isin(dates, list(tr_days)); te = np.isin(dates, list(te_days))
        if tr.sum() < 200 or te.sum() < 50:
            continue
        for arm, X in feats.items():
            head = Ridge(alpha=5.0, random_state=SEED)
            head.fit(X[tr], y[tr])
            part, w = _daily_returns(panel[te], head.predict(X[te]), label)
            series[arm].append(part)
            books[arm].update(w)          # folds are disjoint blocks of dates

    per_arm = {}
    for arm, parts in series.items():
        if not parts:
            per_arm[arm] = {"n_dates": 0}
            continue
        d = pd.concat(parts, ignore_index=True).sort_values("date").reset_index(drop=True)
        # REALISED turnover, not a flat charge. The folds are consecutive blocks
        # of dates, so the concatenated book is ONE chain and a name that stays
        # in its leg across the seam is carried, not re-bought.
        costs = turnover_costs([(dt, books[arm][dt]) for dt in d["date"].tolist()],
                               COST_BPS_PER_SIDE)
        d = d.merge(costs, on="date", how="left", validate="one_to_one")
        d["net"] = d["gross"] - d["cost"]
        d["net_daily_liquidation"] = d["gross"] - FLAT_LIQUIDATION_COST
        per_arm[arm] = {
            "gross": _stat(d["gross"]), "net": _stat(d["net"]),
            "net_daily_liquidation": _stat(d["net_daily_liquidation"]),
            "cost_bps_per_side": COST_BPS_PER_SIDE,
            # AGGREGATE, not a mean of ratios: gross exposure is 2.0 only when no
            # symbol lands in both legs on the same date (two headlines, opposite
            # predictions net out), and dividing each date by its own smaller
            # denominator would print a turnover the cost line does not support.
            "turnover_per_rebalance": round(float(d["traded"].sum()
                                                  / (2.0 * d["gross_exposure"].sum())), 4),
            "turnover_per_day": round(float(d["traded"].sum()
                                            / (2.0 * d["gross_exposure"].sum())), 4),
            "mean_turnover_ratio_per_date": round(float(d["turnover"].mean()), 4),
            "traded_notional_per_date": round(float(d["traded"].mean()), 4),
            "mean_gross_exposure": round(float(d["gross_exposure"].mean()), 4),
            "mean_cost_bps_per_date": round(float(d["cost"].mean()) * 1e4, 2),
            "flat_cost_bps_per_date_run01": round(FLAT_LIQUIDATION_COST * 1e4, 2),
            "median_names_per_date": int(d["n"].median())}

    def _net_ann(a):
        return (per_arm.get(a, {}).get("net") or {}).get("ann_pct")

    tr_a, ct_a, bl_a = _net_ann("TRANSFER"), _net_ann("CONTROL"), _net_ann("BASELINE")
    if None in (tr_a, ct_a, bl_a):
        verdict = "CANNOT_DETERMINE: an arm produced no dates"
    elif tr_a <= ct_a:
        verdict = (f"CURRICULUM_NOT_EARNED: TRANSFER {tr_a}%/yr does not beat its own "
                   f"shuffled-label CONTROL {ct_a}%/yr -- the hidden layer is capacity, "
                   f"not the counterfactuals")
    elif tr_a <= bl_a:
        verdict = (f"CURRICULUM_NOT_EARNED: TRANSFER {tr_a}%/yr does not beat BASELINE "
                   f"{bl_a}%/yr, which has no pretraining at all")
    else:
        verdict = (f"CURRICULUM_HELPS (conditional, gross of borrow, one 20-month window): "
                   f"TRANSFER {tr_a}%/yr > CONTROL {ct_a} and BASELINE {bl_a}")

    receipt = {
        "job": "C2_curriculum_transfer", "licence": "PRODUCT_EXPERIMENT",
        "llm_spend_usd": 0.0, "label": label,
        "question": "does pretraining on INVENTED counterfactual news help predict REAL "
                    "excess returns, beyond an identical net pretrained on the same "
                    "curriculum with shuffled labels?",
        "curriculum": {"texts": len(cur_texts), "path": str(CURRICULUM),
                       "max_docs": max_cur_docs,
                       "kinds": pd.Series(cur_kind).value_counts().to_dict(),
                       "class_balance": pd.Series(cur_y).value_counts().to_dict(),
                       "fit_acc_true": round(cur_acc, 4),
                       "fit_acc_shuffled": round(ctrl_acc, 4)},
        "panel": {"rows": int(len(panel)), "symbols": int(panel["symbol"].nunique()),
                  "dates": int(panel["entry_date"].nunique()),
                  "range": [str(panel["entry_date"].min()), str(panel["entry_date"].max())],
                  "dollar_vol_floor": DOLLAR_VOL_FLOOR},
        "construction": {"decile_long_short_equal_weight": True,
                         "cost_bps_per_side": COST_BPS_PER_SIDE,
                         "cost_note": "sum|w_t - w_{t-1}| x 25 bps on REALISED decile-membership "
                                      "turnover: a name in the same leg on two consecutive "
                                      "sessions is carried and pays nothing. Entry on the first "
                                      "date and liquidation on the last are charged. "
                                      "`turnover_per_rebalance` = 1.0 would mean the whole book "
                                      "replaced, which is the flat 100 bps/date run01 charged "
                                      "unconditionally and is kept as `net_daily_liquidation`.",
                         "cost_model": "realised_weight_turnover",
                         "turnover_definition": "traded / (2 x gross exposure); 1.0 = the entire "
                                                "book sold and an entirely new one bought",
                         "label_caveat": "x_oc is open-to-close, so a carried name is modelled "
                                         "as held overnight while its return is measured inside "
                                         "the session only. `net` is therefore the LOWER cost "
                                         "bound and `net_daily_liquidation` the UPPER one.",
                         "amended_utc": "2026-09-10",
                         "unit": "one portfolio return per DATE", "folds": n_folds,
                         "walk_forward": "train on all earlier dates, read the next block once"},
        "arms": per_arm, "verdict": verdict,
        "headline": (f"TRANSFER {tr_a}%/yr net vs shuffled-label CONTROL {ct_a} vs "
                     f"no-pretrain BASELINE {bl_a}, on {len(panel):,} cells / "
                     f"{panel['entry_date'].nunique()} dates, at "
                     f"{(per_arm.get('TRANSFER') or {}).get('turnover_per_rebalance')} "
                     f"realised turnover a rebalance and {COST_BPS_PER_SIDE:.0f} bps a side"
                     if None not in (tr_a, ct_a, bl_a) else "an arm produced no dates"),
        "wall_s": round(time.time() - t0, 1),
        "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "C2_receipt.json").write_text(json.dumps(receipt, indent=1, default=str),
                                         encoding="utf-8")
    return receipt


def C2_curriculum_transfer(smoke: bool = False) -> dict:
    return run(smoke=smoke)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--label", default="x_oc", choices=["x_oc", "x_oo", "r_oc", "r_oo"])
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--max-curriculum-docs", type=int, default=None,
                    help="read only the first N source rows of the curriculum "
                         "(4851 reproduces run01's 18,116 texts)")
    a = ap.parse_args()
    print(json.dumps(run(smoke=a.smoke, label=a.label, n_folds=a.folds,
                         max_cur_docs=a.max_curriculum_docs), indent=1, default=str))
