"""UNIVERSE-SURVIVAL-STRESS-1 — the NET tournament's universe clause, run.

    python -m scripts.universe_survival_stress_1

The registered NET tournament (2026-08-19) carried a universe-limitation
clause: its 182 contemporary large caps under-represent the market the
conclusions get quoted against. This sensitivity rebuilds the same
QUESTION on the CRSP PIT panel (2013–2024, ~1,500–2,300 eligible names
monthly, delistings included): with identical features and frozen
architectures, does the ordering hold —

  - return ranking: does anything beat ridge? (tournament: NO arm
    established)
  - risk ranking: is vol strongly learnable and is ridge competitive?
    (tournament: ridge IC ~0.65, beat every NN)

SCREEN discipline under the parent prereg's declared clause. No
architecture tuning: hyperparameters are the tournament's, verbatim.
Walk-forward: train 2014..(y-1), test year y, y in 2017..2024.
Delistings: forward returns include the delisting month via
ret_incl_delist from the PIT monthly file.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config                        # noqa: E402
from backend.services.lane_factory_sim import load_panel     # noqa: E402
from backend.services.net_tournament import rank_ic_by_date  # noqa: E402

OUT = _config.OPTIMUS_LEDGER_DIR / "net_tournament"


def build_monthly_dataset() -> pd.DataFrame:
    panel = load_panel()
    px, ret = panel.px, panel.ret
    month_ends = px.groupby(px.index.to_period("M")).tail(1).index
    feats = {}
    for w in (21, 63, 126):
        feats[f"mom_{w}"] = px / px.shift(w) - 1.0
    feats["mom_252_21"] = px.shift(21) / px.shift(252) - 1.0
    for w in (21, 63):
        feats[f"vol_{w}"] = ret.rolling(w).std(ddof=1)
    feats["dd_252"] = px / px.rolling(252).max() - 1.0
    fwd_ret = px.shift(-21) / px - 1.0
    # reversed rolling = forward-looking window: at t, std of t+1..t+21
    fwd_vol = ret[::-1].rolling(21).std(ddof=1)[::-1].shift(-1)

    rows = []
    for d in month_ends:
        if d not in px.index:
            continue
        elig = panel.elig_by_month.get(d.to_period("M"), set())
        frame = pd.DataFrame({k: v.loc[d] for k, v in feats.items()})
        frame["fwd_ret"] = fwd_ret.loc[d]
        frame["fwd_vol"] = fwd_vol.loc[d]
        frame = frame.dropna()
        frame = frame[frame.index.isin(elig)]
        frame["date"] = d
        frame["permno"] = frame.index
        rows.append(frame)
    df = pd.concat(rows, ignore_index=True)
    return df


FEATURES = ("mom_21", "mom_63", "mom_126", "mom_252_21",
            "vol_21", "vol_63", "dd_252")


def walk_forward_ic(df: pd.DataFrame, target: str) -> dict:
    from lightgbm import LGBMRegressor
    from sklearn.linear_model import Ridge
    from sklearn.neural_network import MLPRegressor
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    arms = {
        "ridge": lambda: make_pipeline(StandardScaler(),
                                       Ridge(alpha=1.0)),
        "lgbm": lambda: LGBMRegressor(n_estimators=300, num_leaves=31,
                                      learning_rate=0.05,
                                      random_state=20260819, verbose=-1),
        "mlp_2x64": lambda: make_pipeline(
            StandardScaler(),
            MLPRegressor(hidden_layer_sizes=(64, 64), max_iter=200,
                         random_state=20260819)),
    }
    ics = {a: [] for a in arms}
    years = range(2017, 2025)
    for y in years:
        tr = df[df["date"].dt.year < y]
        te = df[df["date"].dt.year == y]
        if len(tr) < 5000 or len(te) < 1000:
            continue
        Xtr, ytr = tr[list(FEATURES)].to_numpy(), tr[target].to_numpy()
        Xte = te[list(FEATURES)].to_numpy()
        for a, mk in arms.items():
            m = mk()
            m.fit(Xtr, ytr)
            pred = m.predict(Xte)
            s = rank_ic_by_date(pred, te[target].to_numpy(),
                                te["date"].to_numpy())
            ics[a].extend(list(s.values))
    return {a: {"mean_ic": round(float(np.mean(v)), 4),
                "n_dates": len(v)} for a, v in ics.items()}


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass
    print("building monthly dataset from the PIT panel...")
    df = build_monthly_dataset()
    print(f"rows {len(df):,}  months {df['date'].nunique()}  "
          f"names {df['permno'].nunique():,}")
    out = {"sensitivity": "UNIVERSE-SURVIVAL-STRESS-1 (SCREEN, parent "
                          "= PREREG_AEGIS_NET_TOURNAMENT_1 universe "
                          "clause)",
           "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "n_rows": int(len(df)), "n_months": int(df["date"].nunique()),
           "n_names": int(df["permno"].nunique()),
           "features": list(FEATURES),
           "architectures": "tournament-frozen hyperparams, no tuning"}
    for target in ("fwd_ret", "fwd_vol"):
        print(f"walk-forward {target} ...")
        out[target] = walk_forward_ic(df, target)
        print(" ", json.dumps(out[target]))
    p = OUT / "universe_survival_stress_2026-08-19.json"
    p.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("receipt:", p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
