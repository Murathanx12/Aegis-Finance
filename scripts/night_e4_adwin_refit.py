"""E4 -- refit when the error stream says to, or refit every month regardless.

THE COMPARISON, on IDENTICAL test dates:

  FIXED   refit at the start of every test month. This is what E1/E2/N3 already
          do by construction, so the existing walk-forward IS the control and no
          separate control run is invented.
  ADWIN   refit only when ADWIN (Bifet & Gavalda 2007) signals a change on the
          head's own rolling per-date error since the last refit. On a month it
          does not refit, the STALE model makes the predictions -- and every
          date says which, and how old the model was, so a reviewer can see the
          staleness rather than infer it.

WHAT WOULD MAKE ADWIN WORTH IT. Not "fewer refits": a refit here costs seconds.
It is worth it if the stale-model months are NOT worse, because that is
evidence the monthly cadence is arbitrary -- and if they ARE worse, that is
evidence the head decays fast enough that the cadence is load-bearing, which is
a fact about the head worth knowing either way. The receipt reports both arms'
IC and net on the same dates plus the refit timeline; it does not pick a winner
on refit count.

The head is LightGBM on E1's typed-event table -- the M5 mandatory control, and
the same object E3 puts intervals on, so E3 and E4 are graded on one head and
not two arbitrary ones.

Licence: PRODUCT_EXPERIMENT.
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

from backend.services.adwin import ADWIN, declaration, to_unit, unit_scale   # noqa: E402
from learner import event_head as eh                               # noqa: E402
from learner.evaluate import TRADABLE_DOLLAR_VOL                   # noqa: E402
from scripts import night_e1_event_head as e1                      # noqa: E402
from scripts import night_n3_frozen_embedding_head as n3           # noqa: E402
from scripts.night_checkpoint import atomic_write_json             # noqa: E402
from scripts.night_g3_evolve_v2 import COST_BPS                    # noqa: E402

JOB = "E4_adwin_gated_refit"
LICENCE = "PRODUCT_EXPERIMENT"
SEED = n3.SEED
#: swept in `known_answer` and reported; 0.05 is what the real run uses because
#: it is the smallest value in the sweep that detects the planted step inside
#: one detection clock, at zero false alarms over 2,000 stationary steps.
DELTA = 0.05
DELTA_GRID = (0.002, 0.01, 0.05, 0.2)
OUT_DIR = n3.OUT_DIR
ARM = "EVENT"


def synthetic_drift(n_stable: int = 200, n_drifted: int = 200, seed: int = SEED,
                    stable=(0.10, 0.02), drifted=(0.35, 0.08)):
    """A manufactured concept drift: a stable error level, then a step up.

    The levels are already inside [0, 1] because ADWIN's bound requires it (see
    `backend/services/adwin.py`). An unscaled version of this same step -- 0.008
    to 0.052 -- produced zero detections, which is the measurement that put the
    scaling rule in the module's docstring.
    """
    rng = np.random.default_rng(seed)
    a = rng.normal(stable[0], stable[1], n_stable)
    b = rng.normal(drifted[0], drifted[1], n_drifted)
    return np.clip(np.concatenate([a, b]), 0.0, 1.0)


def known_answer(delta: float = DELTA) -> dict:
    """Does it fire after the planted change, and stay quiet before it?

    `delta` is SWEPT rather than asserted: the detection lag and the
    false-alarm count are the two numbers that decide it, and picking one value
    and reporting only its lag would hide the trade the parameter makes.
    """
    change_at = 200
    sweep = {}
    for d in DELTA_GRID:
        stream = synthetic_drift()
        det = ADWIN(delta=d)
        fired = [i for i, x in enumerate(stream) if det.update(float(x))]
        after = [i for i in fired if i >= change_at]
        quiet = ADWIN(delta=d)
        rng = np.random.default_rng(SEED + 1)
        false_alarms = sum(1 for _ in range(2000)
                           if quiet.update(float(np.clip(rng.normal(0.10, 0.02), 0, 1))))
        sweep[str(d)] = {
            "fired_at": fired,
            "first_detection_after_change": (after[0] - change_at) if after else None,
            "false_alarms_before_the_change": len([i for i in fired if i < change_at]),
            "false_alarms_on_2000_stationary_steps": false_alarms,
        }
    chosen = sweep[str(delta)]
    return {
        "stream": {"n_stable": 200, "n_drifted": 200, "change_at": change_at,
                   "stable_mean": 0.10, "drifted_mean": 0.35,
                   "domain": "[0, 1] -- required by the bound, see adwin.declaration()"},
        "delta_sweep": sweep,
        "delta_used_in_the_real_run": delta,
        "first_detection_after_change": chosen["first_detection_after_change"],
        "false_alarms_on_2000_stationary_steps": chosen["false_alarms_on_2000_stationary_steps"],
        "detection_granularity_steps": ADWIN().min_clock,
        "unscaled_stream_finding": ("the same step at the scale a real mean-absolute-error "
                                    "stream lives on (0.008 -> 0.052) fires ZERO times: the "
                                    "bound's additive term does not scale with the data. "
                                    "`to_unit` with a frozen `unit_scale` is why the real run "
                                    "can detect anything at all."),
        "note": ("the test runs on a clock of min_clock steps -- the paper's own cost "
                 "reduction -- so a detection lag below that number is not resolvable"),
    }


def run(cells: pd.DataFrame, mats: dict, embargo: int, delta: float = DELTA,
        verbose: bool = True) -> tuple[pd.DataFrame, list[dict], dict]:
    """One walk-forward, two refit policies, identical test dates."""
    dates = cells["entry_date"].to_numpy()
    months = cells["entry_date"].dt.to_period("M").astype(str).to_numpy()
    y = cells["y"].to_numpy(dtype=float)
    syms = cells["symbol"].to_numpy()
    tradable = cells["pit_dv_21"].to_numpy(dtype=float) >= TRADABLE_DOLLAR_VOL
    sessions = np.array(sorted(pd.unique(dates)))
    uniq_months = sorted(set(months))
    X = mats[ARM]

    det = ADWIN(delta=delta)
    err_scale = None            # frozen after the first month; never re-estimated
    stale_model = None
    stale_since = None
    refits = {"FIXED": 0, "ADWIN": 0}
    fit_seconds = {"FIXED": 0.0, "ADWIN": 0.0}
    timeline, daily = [], []

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
        Xtr = X.loc[tr].reset_index(drop=True)
        Xte = X.loc[te].reset_index(drop=True)

        t0 = time.time()
        p_fixed, _ = eh.fit_predict_gbm(Xtr, y[tr], Xte, seed=SEED + mi)
        fit_seconds["FIXED"] += time.time() - t0
        refits["FIXED"] += 1

        # `det` is reset at every refit, so a non-None detection means it fired
        # SINCE the model currently in hand was fitted -- which is the question,
        # not whether it ever fired.
        fired = det.last_detection_at is not None
        must_refit = stale_model is None or fired
        if must_refit:
            t0 = time.time()
            import lightgbm as lgb
            from learner.models import LGBM_PARAMS
            params = dict(LGBM_PARAMS)
            params["random_state"] = SEED + mi
            model = lgb.LGBMRegressor(**params)
            model.fit(Xtr, y[tr])
            fit_seconds["ADWIN"] += time.time() - t0
            refits["ADWIN"] += 1
            stale_model = (model, list(Xtr.columns))
            stale_since = mo
            det = ADWIN(delta=delta)            # the window restarts with the model
            reason = "first fit" if len(timeline) == 0 else "ADWIN signalled a change"
        else:
            reason = "no change signalled -- the STALE model predicts this month"
        model, cols = stale_model
        p_adwin = np.asarray(model.predict(Xte[cols]), dtype=float)

        d_te, y_te, s_te, t_te = dates[te], y[te], syms[te], tradable[te]
        month_err = []
        for d in np.unique(d_te):
            k = d_te == d
            if k.sum() < n3.MIN_NAMES_IC:
                continue
            row = {"date": pd.Timestamp(d), "month": mo, "n": int(k.sum()),
                   "n_tradable": int(t_te[k].sum()),
                   "adwin_model_fitted_for_month": stale_since,
                   "adwin_model_is_stale": bool(stale_since != mo),
                   "adwin_model_age_months": int(uniq_months.index(mo)
                                                 - uniq_months.index(stale_since))}
            for name, p in (("FIXED", p_fixed), ("ADWIN", p_adwin)):
                row[f"ic_{name}"] = n3._spearman(p[k], y_te[k])
                g, w = n3._book_day(p[k], y_te[k], s_te[k], t_te[k])
                row[f"gross_{name}"] = g
                row[f"w_{name}"] = w
            err = float(np.mean(np.abs(y_te[k] - p_adwin[k])))
            row["adwin_mean_abs_error"] = err
            month_err.append(err)
            daily.append(row)

        # ADWIN's bound needs [0, 1]. The divisor is computed ONCE from the first
        # graded month and frozen: a scale that tracked the stream would absorb
        # exactly the drift the detector is looking for.
        if err_scale is None and month_err:
            err_scale = unit_scale(month_err)
        for e in month_err:
            det.update(to_unit(e, err_scale))
        timeline.append({"test_month": mo, "adwin_refit": bool(must_refit), "reason": reason,
                         "model_fitted_for": stale_since,
                         "adwin_state": det.state(),
                         "mean_abs_error": round(float(np.mean(month_err)), 6) if month_err else None})
        if verbose:
            print(f"[e4] {mo}  adwin_refit={must_refit}  {reason}", flush=True)

    if not daily:
        return pd.DataFrame(), timeline, {"refits": refits, "fit_seconds": fit_seconds}
    dd = pd.DataFrame(daily).sort_values("date").reset_index(drop=True)
    for name in ("FIXED", "ADWIN"):
        prev, to, net = {}, [], []
        for w, g in zip(dd[f"w_{name}"].to_numpy(), dd[f"gross_{name}"].to_numpy()):
            if not w:
                to.append(float("nan"))
                net.append(float("nan"))
                continue
            t = n3._turnover(prev, w)
            to.append(t)
            net.append(g - t * COST_BPS / 1e4 if np.isfinite(g) else float("nan"))
            prev = w
        dd[f"turnover_{name}"] = to
        dd[f"net_{name}"] = net
        dd.drop(columns=[f"w_{name}"], inplace=True)
    cost = {"refits": refits, "fit_seconds": {k: round(v, 2) for k, v in fit_seconds.items()},
            "error_unit_scale": round(float(err_scale), 8) if err_scale else None,
            "error_unit_scale_note": ("4 x the median mean-absolute-error of the FIRST graded "
                                      "month, frozen -- ADWIN's bound requires a [0, 1] stream")}
    return dd, timeline, cost


def grade(dd: pd.DataFrame, horizon: int = 1) -> dict:
    out = {"arms": {}, "vs": {},
           "horizon_caveats": n3.horizon_caveats(horizon, int(len(dd)))}
    for name in ("FIXED", "ADWIN"):
        out["arms"][name] = {
            "ic": n3._cell(dd[f"ic_{name}"].to_numpy(dtype=float), False),
            "gross": n3._cell(dd[f"gross_{name}"].to_numpy(dtype=float), True),
            "net": n3._cell(dd[f"net_{name}"].to_numpy(dtype=float), True),
            "mean_daily_turnover": round(float(np.nanmean(
                dd[f"turnover_{name}"].to_numpy(dtype=float))), 4),
            "cost_bps_per_unit_turnover": COST_BPS,
        }
    out["vs"]["ADWIN_minus_FIXED"] = {
        "ic": n3._cell((dd["ic_ADWIN"] - dd["ic_FIXED"]).to_numpy(dtype=float), False),
        "net": n3._cell((dd["net_ADWIN"] - dd["net_FIXED"]).to_numpy(dtype=float), True),
    }
    stale = dd["adwin_model_is_stale"].to_numpy(dtype=bool)
    out["stale_vs_fresh"] = {
        "n_dates_on_a_stale_model": int(stale.sum()),
        "n_dates_on_a_fresh_model": int((~stale).sum()),
        "ic_on_stale_dates": n3._cell(dd.loc[stale, "ic_ADWIN"].to_numpy(dtype=float), False),
        "ic_on_fresh_dates": n3._cell(dd.loc[~stale, "ic_ADWIN"].to_numpy(dtype=float), False),
        "max_model_age_months": int(dd["adwin_model_age_months"].max()),
    }
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="E4 ADWIN-gated refit vs fixed monthly refit")
    ap.add_argument("--out", default=None)
    ap.add_argument("--run", type=int, default=1)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--horizon", type=int, default=5, choices=[5, 21])
    ap.add_argument("--delta", type=float, default=DELTA)
    ap.add_argument("--stage", default="signal")
    args = ap.parse_args(argv)

    t0 = time.time()
    horizon = int(args.horizon)
    embargo = n3.embargo_for(horizon)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = Path(args.out) if args.out else (
        OUT_DIR / f"{JOB}_run{args.run:02d}{'_smoke' if args.smoke else ''}.json")

    receipt = {
        "job": JOB, "licence": LICENCE, "run": args.run, "smoke": bool(args.smoke),
        "stage": args.stage, "llm_spend_usd": 0.0,
        "question": ("Does refitting only when ADWIN signals a change on the head's own error "
                     "stream cost anything against refitting every month, on identical test "
                     "dates?"),
        "method": declaration(),
        "design": {"head": "LightGBM on E1's typed-event table (the M5 mandatory control)",
                   "arm": ARM, "horizon_sessions": horizon, "embargo_sessions": embargo,
                   "delta": args.delta, "seed": SEED,
                   "fixed_control": ("refit every test month -- this IS E1/E2/N3's existing "
                                     "walk-forward, not a separate control run"),
                   "cost_bps_per_side": COST_BPS,
                   "cost_source": "scripts.night_g3_evolve_v2.COST_BPS (imported, not retyped)"},
        "inputs": [n3.PANEL.name, n3.BARS.name],
        "status": "running", "written_utc": n3._now(),
    }
    atomic_write_json(out, receipt, indent=1)

    print("[e4] known-answer: a planted concept drift", flush=True)
    receipt["known_answer"] = known_answer(args.delta)
    atomic_write_json(out, receipt, indent=1)

    print(f"[e4] loading the panel (horizon {horizon}, embargo {embargo})", flush=True)
    cells, _corpus, meta = n3.load_cells(smoke=args.smoke, horizon=horizon)
    ev = eh.extract_events(cells[["symbol", "entry_date", "text"]])
    mats, fmeta = e1._feature_matrices(cells, ev, SEED)
    receipt["panel"] = meta
    receipt["features"] = {k: fmeta[k] for k in
                           ("kept_types", "dropped_sparse_types", "n_feature_columns", "proxy")}
    atomic_write_json(out, receipt, indent=1)

    dd, timeline, cost = run(cells, mats, embargo=embargo, delta=args.delta)
    if dd.empty:
        receipt["status"] = "REFUSED"
        receipt["verdict"] = "REFUSED: no gradable test date at this horizon"
        receipt["written_utc"] = n3._now()
        atomic_write_json(out, receipt, indent=1)
        return 2

    g = grade(dd, horizon=horizon)
    daily_path = out.with_name(out.stem + "_daily.csv")
    dd.to_csv(daily_path, index=False)
    d = g["vs"]["ADWIN_minus_FIXED"]["ic"]
    head = (f"ADWIN refit {cost['refits']['ADWIN']} times vs FIXED {cost['refits']['FIXED']} on "
            f"{len(dd)} identical test dates; ADWIN - FIXED IC {d['mean']:+.4f} (t {d['t']}, "
            f"p {d['p']}); {g['stale_vs_fresh']['n_dates_on_a_stale_model']} dates ran on a "
            f"stale model, max age {g['stale_vs_fresh']['max_model_age_months']} months; "
            f"fit seconds {cost['fit_seconds']['ADWIN']} vs {cost['fit_seconds']['FIXED']}")
    if cost["refits"]["ADWIN"] <= 1:
        v = ("ADWIN NEVER FIRED after the mandatory first fit, so the ADWIN arm is one model "
             f"carried across every test month (max age "
             f"{g['stale_vs_fresh']['max_model_age_months']} months). That is a fact about the "
             "ERROR STREAM -- at this scale it is stationary to the detector -- and only "
             "secondarily about the cadence. Read the stale-vs-fresh IC split, not the refit "
             "count: a monthly refit that changes nothing is ceremony, and a detector that "
             "cannot see the drift is not evidence there is none.")
    elif cost["refits"]["ADWIN"] >= cost["refits"]["FIXED"]:
        v = ("ADWIN did not save a refit on this panel -- it signalled a change at least as "
             "often as the calendar did, so the monthly cadence is not the thing being "
             "questioned here.")
    elif (d["t"] is not None and d["t"] < -2.0):
        v = ("FIXED wins: the stale-model months are materially worse, so the monthly cadence "
             "is load-bearing on this head and refit-on-fire costs return.")
    else:
        v = ("NO DETECTABLE COST to gating the refit: fewer refits, and the difference on "
             "identical dates is not distinguishable from zero. One era, 2025-26, one head.")
    receipt["timeline"] = timeline
    receipt["cost"] = cost
    receipt["results"] = g
    receipt["headline"] = head
    receipt["verdict"] = v
    receipt["next_test"] = ("feed E3's realised coverage the same stale/fresh split -- a stale "
                            "model should show up as a coverage cost before it shows up as an "
                            "IC cost, because risk resolves faster than return")
    receipt["daily_csv"] = str(daily_path)
    receipt["status"] = "done"
    receipt["elapsed_s"] = round(time.time() - t0, 1)
    receipt["written_utc"] = n3._now()
    atomic_write_json(out, receipt, indent=1)
    print("\n" + head)
    print(v)
    print(f"receipt: {out}")
    return 0


def E4_adwin_gated_refit(smoke: bool = False, run: int = 1) -> dict:
    out = OUT_DIR / f"{JOB}_run{run:02d}{'_smoke' if smoke else ''}.json"
    argv = ["--run", str(run), "--out", str(out)] + (["--smoke"] if smoke else [])
    rc = main(argv)
    payload = json.loads(out.read_text(encoding="utf-8"))
    if rc != 0:
        payload.setdefault("status", "REFUSED")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
