"""Freeze the size model the straddle forward log applies (TRIAL-STRADDLE-FWD-1).

    python -m scripts.straddle_model_fit            # fit + write model_ridge_pit_v1.json (refuses to overwrite)

WHAT IT FITS. Exactly the forecast that carried the 2014-2024 straddle result in
`docs/research_notes/2026-09-29/sizing_on_move_size_2026-09-29.md` §5: the ridge on
|r21| (target `abs_r21`) with the point-in-time earnings spec `CRSP_SPEC_EARN_PIT`
(8 price columns + past earnings-move size + the projected earnings-in-window flag),
alpha 10, target winsorised at the 99th percentile, forecasts floored at the target's
1st percentile -- the same `move_size_sizing` pieces the walk-forward used, fitted
ONCE on every CRSP decision date whose 21-session target had closed (2013-2024).

The walk-forward refit every month; the forward log cannot (CRSP ends 2024-12 and the
live bars are 20 months deep), so the coefficients are FROZEN here, hashed, and the
hash goes into the strategy contract. The last walk-forward fit's coefficients are
printed beside the frozen ones so a drift between the two is visible.

$0: local licensed files only, nothing pulled, no LLM.
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import move_size_sizing as MS            # noqa: E402
from backend.services import straddle_forward as SF            # noqa: E402
from scripts import sizing_lab_crsp as C                       # noqa: E402


def fit() -> dict:
    t0 = time.time()
    D = C.load_daily()
    ev = C.earnings_events(D)
    panel, _ = C.build_panel(D, ev)
    panel["abs_r21"] = panel["r21"].abs()
    spec = dict(C.CRSP_SPEC_EARN_PIT)
    X = MS._transform(panel, spec)
    y = panel["abs_r21"].to_numpy(dtype=float)
    ok = np.isfinite(y) & np.isfinite(X).any(axis=1)
    Xt, yt = X[ok], y[ok]
    cap = float(np.quantile(yt, 0.99))
    yt = np.minimum(yt, cap)
    mu, sd, b, ym = MS._fit_ridge(Xt, yt, 10.0)
    floor = max(float(np.quantile(yt, 0.01)), 1e-6)
    # in-sample per-date IC (diagnostic only; the out-of-sample evidence is the walk-forward receipt)
    pred = np.maximum(MS._predict_ridge((mu, sd, b, ym), X), floor)
    panel["_f"] = pred
    ic = MS.per_date_ic(panel.loc[ok], "_f", "abs_r21")
    # the last walk-forward fit, for a drift print
    wf, log = MS.walk_forward_size(panel, spec, target="abs_r21", gap=2, min_train_dates=12)
    body = {"schema": "straddle_size_model_v1", "target": "abs_r21 = |close(entry+21 sessions)/close(entry) - 1|",
            "spec": spec, "feature_order": list(spec), "alpha": 10.0, "winsor_q": 0.99, "winsor_cap": cap,
            "floor_q": 0.01, "floor": floor,
            "mu": [float(v) for v in mu], "sd": [float(v) for v in sd], "coef": [float(v) for v in b],
            "intercept": float(ym),
            "n_train": int(len(yt)), "train_span": [str(panel.loc[ok, "date"].min().date()),
                                                    str(panel.loc[ok, "date"].max().date())],
            "n_dates": int(panel.loc[ok, "date"].nunique()),
            "source": "CRSP daily 2012-2024 (crsp_pit_monthly_v1 eligible), Compustat rdq via CCM, "
                      "point-in-time earnings flag (last known report + 91-day steps)",
            "in_sample_ic_mean": float(ic.mean()),
            "walk_forward_last_fit": log[-1] if log else None,
            "walk_forward_oos_ic_mean": float(MS.per_date_ic(panel.assign(_w=wf).loc[ok & wf.notna().to_numpy()],
                                                             "_w", "abs_r21").mean()),
            "fitted_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "fit_seconds": round(time.time() - t0, 1)}
    body["model_sha"] = SF.model_hash(body)
    return body


def main() -> int:
    out = SF.MODEL_PATH
    if out.exists():
        print(f"REFUSED: {out} exists (frozen model; a new fit is a new version file)")
        return 2
    body = fit()
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(body, indent=1), encoding="utf-8")
    tmp.replace(out)
    print(json.dumps({k: body[k] for k in ("model_sha", "n_train", "train_span", "in_sample_ic_mean",
                                           "walk_forward_oos_ic_mean", "coef", "fit_seconds")}, indent=1))
    print("walk-forward last fit:", body["walk_forward_last_fit"])
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
