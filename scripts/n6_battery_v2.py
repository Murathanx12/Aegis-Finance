"""N6.1 -- KNOWN-ANSWER BATTERY v2: through the NEW construction, and DOWN TO
THE MACHINE'S OWN FLOOR.

WHAT v1 PROVED, AND THE TWO HOLES FABLE NAMED
=============================================
B1 (labor-day lane) planted three worlds -- linear, regime, graph -- and the
machine recovered 3 of 3 with the correct sign at Holm p 0.0000, returning
NOISE + REFUTED on the matched null. ALL_PASS. Two objections stand against it,
and both are the reason this file exists:

* **Attack #5: "B1 passes because its worlds are generous."** The planted
  effects are 6-11x the machine's own MDE. A battery that only plants edges the
  machine cannot miss proves the WIRING, not the SENSITIVITY. So v2 runs a
  LADDER: the same world at 1.0x, 0.5x, 0.25x and 0.125x of B1's planted scale,
  and reports the smallest planted edge still recovered.
* **The construction changed underneath it.** v1 books every world at top-50
  equal-weight. N1 has since shown that construction is a third of the story
  and that the transfer coefficient moves from ~0.13 to ~0.6 between the
  incumbent and a broad book. A battery that certifies a pipeline the books no
  longer use certifies nothing. So every world is recovered through **N1's
  control construction AND N1's broad construction**, and through **N2's
  selection-free rank ensemble** of the same three model kinds.

A FOURTH WORLD: THE EVENT
=========================
Linear, regime and graph all plant an edge that is present on EVERY row. Most
of what N4 is building is not like that: an earnings surprise, an 8-K, a stake
filing exist on a handful of rows a month and nowhere else. The event world
plants the alpha on the top decile of an event carrier and ZERO elsewhere -- a
shape a cross-sectional ranker can miss even when the total effect is large,
because 90% of its training rows carry no information at all.

The event alpha is CROSS-SECTIONALLY DEMEANED before it is added, so the
equal-weighted market leg is unchanged by construction and the value-weighted
leg moves only by `w . alpha`, which the receipt prints. Without that the world
would plant a market effect and call it a stock-selection effect.

ANY MISS IS A MACHINE DEFECT, NOT A RESULT
==========================================
Nothing here is evidence about markets. Every number is synthetic. The battery
answers one question -- *would this machine see the thing if it were there?* --
and a world it fails is a bug report.

    python -m scripts.n6_battery_v2 --fast
    python -m scripts.n6_battery_v2
"""

from __future__ import annotations

import argparse
import gc
import json
import math
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import receipt_provenance as RP           # noqa: E402

OUT_DIR = REPO / "backend" / "data" / "optimus" / "night_lab_2026-09-07"
RECEIPT = OUT_DIR / "N6_battery_v2.json"
FAST_RECEIPT = OUT_DIR / "N6_battery_v2_fast.json"

#: The event carrier. Deliberately NOT B1's `mom_12_1`, so a recovery in the
#: event world cannot be the linear world's carrier leaking through.
EVENT_CARRIER = "net_rev_4w"
EVENT_TOP_SHARE = 0.10

#: The sensitivity ladder, as multiples of B1's planted scale.
LADDER: tuple[float, ...] = (1.0, 0.5, 0.25, 0.125)

WORLDS_FULL = ("linear", "regime", "graph", "event", "null")
WORLDS_FAST = ("linear", "event", "null")
KINDS = ("ridge", "lgbm", "lgbm_clf")


def _r(v, nd: int = 5):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return round(f, nd) if math.isfinite(f) else None


def _t(series) -> float | None:
    s = pd.Series(series).dropna().astype("float64")
    if len(s) < 3:
        return None
    sd = float(s.std(ddof=1))
    scale = float(np.max(np.abs(s.to_numpy()))) if len(s) else 0.0
    if not math.isfinite(sd) or sd <= max(1e-9 * scale, 0.0) or sd <= 0:
        return None
    return float(s.mean() / (sd / math.sqrt(len(s))))


def _xs_z(v: np.ndarray) -> np.ndarray:
    sd = float(np.std(v))
    return (v - float(np.mean(v))) / (sd if sd > 0 else 1.0)


# ------------------------------------------------------------- the new world

def plant_event(df: pd.DataFrame, cfg, *, carrier: str = EVENT_CARRIER,
                top_share: float = EVENT_TOP_SHARE) -> tuple[pd.DataFrame, dict]:
    """Turn B1's NULL panel into the EVENT world, in place, auditably.

    Every column that carries the alpha is named here rather than derived, so a
    reader can check that the market legs were not moved and that the alpha did
    not leak into a feature. The alpha is demeaned within the month before it
    is added.
    """
    d = df.copy()
    if carrier not in d.columns:
        raise SystemExit(f"REFUSED: the event carrier {carrier!r} is not a column of "
                         "the synthetic panel; planting on a column that does not "
                         "exist would produce a null world wearing an event world's "
                         "name")
    scale = float(cfg.alpha_scale) / max(top_share, 1e-9) * 0.5
    alpha = np.zeros(len(d), dtype="float64")
    vw_shift = []
    for _, idx in d.groupby("month", sort=True).indices.items():
        v = d[carrier].to_numpy()[idx]
        cut = np.quantile(v, 1.0 - top_share)
        flag = (v >= cut).astype("float64")
        a = scale * (flag - flag.mean())          # demeaned WITHIN the month
        alpha[idx] = a
        w = d["market_cap"].to_numpy()[idx]
        vw_shift.append(float((w / w.sum() * a).sum()))
    d["__event_flag"] = (alpha > 0).astype(float)
    for col in ("fwd_1m", "excess_vw_1m", "excess_ew_1m"):
        if col in d.columns:
            d[col] = d[col].to_numpy() + alpha
    for col in ("resid_vw_1m", "resid_ew_1m"):
        if col in d.columns:
            d[col] = d[col].to_numpy() + alpha
    if "pos_vw_1m" in d.columns:
        d["pos_vw_1m"] = (d["excess_vw_1m"] > 0).astype(float)
    d["__true_alpha"] = alpha
    return d, {
        "world": "event",
        "planted": (f"excess[j+1] += {scale:.4f} on the top {top_share:.0%} of "
                    f"{carrier} in month j, and 0 on the other {1 - top_share:.0%}; "
                    "demeaned within the month"),
        "carrier": carrier,
        "share_of_rows_carrying_the_edge": _r(top_share, 4),
        "alpha_scale_on_the_carrying_rows": _r(scale, 5),
        "vw_market_leg_shift_bps_mean": _r(float(np.mean(vw_shift)) * 10_000, 3),
        "vw_market_leg_shift_bps_max": _r(float(np.max(np.abs(vw_shift))) * 10_000, 3),
        "ew_market_leg_shift": 0.0,
        "note": ("the alpha is demeaned inside each month, so the EW market leg is "
                 "unchanged by construction and the VW leg moves only by w . alpha, "
                 "printed above. A world that moved the market and called it "
                 "selection would pass its own test for the wrong reason."),
    }


# --------------------------------------------------------------- the two books

def book_pair(oos: pd.DataFrame, pred_col: str, n_names: int, cost_bps: float
              ) -> dict:
    """The incumbent construction and N1's broad one, on the same predictions."""
    from learner import evaluate as E
    from learner import fundamental_law as FL
    k_ctrl = max(5, int(round(n_names * 0.10)))
    k_broad = max(10, int(round(n_names * 0.40)))
    out = {}
    for tag, (k, wgt, hk) in (("control_top10pct_vw", (k_ctrl, "vw", None)),
                              ("broad_top40pct_ew_hysteresis",
                               (k_broad, "ew", min(2 * k_broad, n_names)))):
        if hk is not None and hk <= k:
            hk = None
        bk = E.book(oos, pred_col, k=k, weight=wgt, cost_bps=cost_bps,
                    ret_col="fwd_1m", mkt_col="mkt_vw_1m", hold_k=hk,
                    return_series=True, return_weights=True)
        ser = bk.get("_series")
        if ser is None or not len(ser.get("net", [])):
            out[tag] = {"verdict": "CANNOT DETERMINE", "why": "no month"}
            continue
        spread = (ser["net"] - ser["market"]).dropna()
        law = FL.receipt(oos[["month", "permno", pred_col, "fwd_1m"]]
                         .dropna(subset=[pred_col]), pred_col, bk["_weights"],
                         net=ser["net"], benchmark=ser["market"])
        out[tag] = {
            "k": k, "weight": wgt, "hold_k": hk,
            "months": int(len(spread)),
            "annualised_excess_pct": _r(float(spread.mean()) * 12 * 100, 3),
            "t_paired_vs_market": _r(_t(spread), 3),
            "terminal_wealth_net": bk.get("terminal_wealth_net"),
            "transfer_coefficient": (law.get("transfer_coefficient") or {}).get("tc"),
            "effective_names": (law.get("effective_breadth") or {}).get(
                "mean_effective_names_per_month"),
            "_spread": spread,
        }
    return out


def run_world(cfg, world: str, *, cost_bps: float, log) -> dict:
    """Build one world, fit every kind, book both constructions plus the
    ensemble, and report what was recovered."""
    from learner import dataset as D
    from learner import evaluate as EV
    from learner import models as M
    from scripts import labor_b1_known_answer_battery as B1

    base_world = "null" if world == "event" else world
    df, built = B1.build_world(cfg, base_world)
    meta = built["meta"]
    if world == "event":
        df, meta = plant_event(df, cfg)
    feature_cols = [c for c in D.feature_columns() if c in df.columns]
    if world == "graph":
        # B1's graph world carries its edge only through features_graph's own
        # columns, and its own attach step is what puts them on the frame.
        import tempfile
        scratch = Path(tempfile.mkdtemp(prefix="n6b_"))
        try:
            extra = built["extra"]
            B1.synthetic_edges(cfg, extra["cust_of"], extra["permnos"],
                               extra["months"], scratch)
            df, gcols = B1.attach_graph_features(cfg, df, extra, scratch)
            feature_cols = [c for c in feature_cols + list(gcols) if c in df.columns]
        except Exception as exc:                                    # noqa: BLE001
            return {"world": world, "status": "REFUSED",
                    "why": f"graph features unavailable: {type(exc).__name__}: {exc}"}

    preds_by_kind, cells = {}, {}
    for kind in cfg.kinds:
        rows, idxs = [], []
        for year, tr, te in D.walk_forward_splits(df, cfg.test_years, 1,
                                                  min_train_months=24):
            if kind == M.CLASSIFIER:
                p, _ = M.fit_predict_proba(df.loc[tr], df.loc[te], feature_cols, 1)
            else:
                p, _ = M.fit_predict(kind, "raw", df.loc[tr], df.loc[te],
                                     feature_cols, 1)
            rows.append(np.asarray(p, dtype="float64"))
            idxs.append(te)
        if not rows:
            continue
        idx = np.concatenate(idxs)
        preds_by_kind[kind] = pd.Series(np.concatenate(rows), index=idx)
        gc.collect()
    if not preds_by_kind:
        return {"world": world, "status": "REFUSED", "why": "no fold produced a fit"}

    oos = df.loc[sorted(set().union(*[set(s.index) for s in preds_by_kind.values()]))].copy()
    for kind, s in preds_by_kind.items():
        oos[kind] = s.reindex(oos.index)
    # N2's construction, on this world: the equal-weight average of the kinds'
    # within-month percentile ranks. No kind is chosen.
    R = pd.DataFrame({k: oos.groupby("month")[k].rank(pct=True)
                      for k in preds_by_kind}, index=oos.index)
    oos["ENSEMBLE"] = R.mean(axis=1, skipna=True)

    for col in list(preds_by_kind) + ["ENSEMBLE"]:
        cells[col] = {
            "rank_ic": EV.rank_ic(oos, col, "excess_vw_1m"),
            "books": book_pair(oos, col, cfg.n_names, cost_bps),
        }
    oracle = B1.oracle_effect(cfg, df, world_is_null=(world == "null"))
    return {"world": world, "meta": meta, "n_features": len(feature_cols),
            "oracle": oracle, "cells": cells, "n_oos_rows": int(len(oos))}


def adjudicate(worlds: dict) -> dict:
    """Did each world come back the way it was planted? PASS is not optional."""
    verdicts, pvals = {}, {}
    for name, w in worlds.items():
        if w.get("status") == "REFUSED":
            verdicts[name] = {"verdict": "REFUSED", "why": w.get("why")}
            continue
        best_t, best_key = None, None
        for col, c in (w.get("cells") or {}).items():
            for tag, b in (c.get("books") or {}).items():
                t = b.get("t_paired_vs_market")
                if t is None:
                    continue
                pvals[f"{name}|{col}|{tag}"] = float(
                    1.0 - 0.5 * math.erfc(-(-t) / math.sqrt(2.0)))
                if best_t is None or t > best_t:
                    best_t, best_key = t, f"{col}|{tag}"
        planted = name != "null"
        recovered = best_t is not None and best_t >= 2.0
        verdicts[name] = {
            "planted": planted,
            "best_t": _r(best_t, 3), "best_cell": best_key,
            "recovered_at_t2": bool(recovered),
            "verdict": ("PASS (planted edge recovered)" if planted and recovered else
                        "FAIL (planted edge MISSED -- machine defect)" if planted else
                        "PASS (null reads NOISE)" if not recovered else
                        "FAIL (the NULL world produced a t >= 2 -- machine defect)"),
        }
    n_pass = sum(1 for v in verdicts.values() if str(v.get("verdict", "")).startswith("PASS"))
    return {"per_world": verdicts, "n_pass": n_pass, "n_worlds": len(verdicts),
            "ALL_PASS": n_pass == len(verdicts) and len(verdicts) > 0}


def run(*, fast: bool = False, ladder: bool = True, verbose: bool = True) -> dict:
    from scripts import labor_b1_known_answer_battery as B1
    from scripts import w3_neural_floored as W3B

    log = (lambda *a: print(*a, flush=True)) if verbose else (lambda *a: None)
    t0 = time.perf_counter()
    tracker = RP.InputTracker()
    cfg = B1.Cfg(fast=fast)
    cfg.kinds = KINDS
    worlds_to_run = WORLDS_FAST if fast else WORLDS_FULL
    out: dict = {
        "job": "N6_battery_v2",
        "lane": "N6",
        "question": ("does the machine still recover a planted edge through N1's "
                     "constructions and N2's ensemble -- and how SMALL an edge can "
                     "it still see?"),
        "licence": "PRODUCT_EXPERIMENT",
        "what_is_synthetic": ("EVERYTHING. No number here is evidence about markets. "
                              "A world this battery fails is a bug report."),
        "config": cfg.as_dict(),
        "worlds": list(worlds_to_run),
        "llm_spend_usd": 0.0, "llm_calls": 0, "network_calls": 0,
        "memory_free_gb_before": W3B.free_gb(),
        "fast": bool(fast),
    }
    results = {}
    for w in worlds_to_run:
        log(f"  world {w} ...")
        try:
            results[w] = run_world(cfg, w, cost_bps=10.0, log=log)
        except Exception as exc:                                    # noqa: BLE001
            results[w] = {"world": w, "status": "REFUSED",
                          "why": f"{type(exc).__name__}: {exc}",
                          "traceback": traceback.format_exc()}
        gc.collect()

    # strip the series before the receipt is serialised
    def _strip(node):
        if isinstance(node, dict):
            return {k: _strip(v) for k, v in node.items() if k != "_spread"}
        return node
    out["results"] = _strip(results)
    out["adjudication"] = adjudicate(results)

    # ---- THE LADDER: how small an edge can this machine still see?
    if ladder:
        log("  sensitivity ladder ...")
        rungs = {}
        base_scale = B1.Cfg(fast=fast).alpha_scale
        for mult in LADDER:
            c = B1.Cfg(fast=True)          # the ladder is always the fast panel:
            c.kinds = ("lgbm_clf",)        # it is a sensitivity curve, not a claim
            c.n_names = 120
            c.end_year = 2014
            c.test_years = list(range(2006, 2015))
            c.alpha_scale = base_scale * mult
            try:
                r = run_world(c, "linear", cost_bps=10.0, log=log)
            except Exception as exc:                                # noqa: BLE001
                rungs[f"{mult}x"] = {"status": "REFUSED",
                                     "why": f"{type(exc).__name__}: {exc}"}
                continue
            books = ((r.get("cells") or {}).get("lgbm_clf") or {}).get("books") or {}
            broad = books.get("broad_top40pct_ew_hysteresis") or {}
            rungs[f"{mult}x"] = {
                "alpha_scale": _r(c.alpha_scale, 6),
                "oracle_annualised_excess": (r.get("oracle") or {}).get("annualised_excess"),
                "broad_book_annualised_pct": broad.get("annualised_excess_pct"),
                "broad_book_t": broad.get("t_paired_vs_market"),
                "recovered_at_t2": bool((broad.get("t_paired_vs_market") or 0) >= 2.0),
                "rank_ic": ((r.get("cells") or {}).get("lgbm_clf") or {}).get("rank_ic"),
            }
            gc.collect()
        found = [m for m in LADDER if (rungs.get(f"{m}x") or {}).get("recovered_at_t2")]
        out["sensitivity_ladder"] = {
            "rungs": rungs,
            "smallest_multiple_recovered": min(found) if found else None,
            "answers": ("Fable's attack #5 on B1: a battery that only plants edges "
                        "6-11x the MDE proves the wiring, not the sensitivity"),
            "reading": ("`smallest_multiple_recovered` is the smallest fraction of "
                        "B1's planted scale this machine still separates from zero at "
                        "t = 2 on a 9-year 120-name panel. None recovered means the "
                        "floor is ABOVE 1.0x on this panel, which is a statement "
                        "about the panel's length as much as the machine."),
        }

    a = out["adjudication"]
    lad = (out.get("sensitivity_ladder") or {}).get("smallest_multiple_recovered")
    out["headline"] = (
        f"{a['n_pass']} of {a['n_worlds']} worlds adjudicated correctly "
        f"({'ALL_PASS' if a['ALL_PASS'] else 'NOT ALL_PASS'}); smallest planted edge "
        f"still recovered: {lad if lad is not None else 'none of the ladder'}"
        f"x B1's scale")
    out["memory_free_gb_after"] = W3B.free_gb()
    out["wall_seconds"] = round(time.perf_counter() - t0, 1)
    RP.attach(out, sys.argv,
              {"fast": bool(fast), "ladder": bool(ladder), "kinds": list(KINDS),
               "event_carrier": EVENT_CARRIER, "event_top_share": EVENT_TOP_SHARE,
               "ladder_multiples": list(LADDER)}, tracker)
    return out


def write(rec: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    rec["generated_utc"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
    return path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fast", action="store_true")
    ap.add_argument("--no-ladder", action="store_true")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    path = Path(a.out) if a.out else (FAST_RECEIPT if a.fast else RECEIPT)
    try:
        rec = run(fast=a.fast, ladder=not a.no_ladder)
    except Exception:                                               # noqa: BLE001
        rec = {"job": "N6_battery_v2", "status": "FAILED",
               "traceback": traceback.format_exc(),
               "headline": "FAILED -- see traceback"}
        write(rec, path)
        print(rec["traceback"], flush=True)
        return 1
    write(rec, path)
    print(rec.get("headline"), flush=True)
    print(f"-> {path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
