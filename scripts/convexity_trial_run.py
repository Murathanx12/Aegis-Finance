"""CONVEXITY-PRESERVATION-1 runner — refuses the registered basis unsigned.

    python -m scripts.convexity_trial_run --rehearsal   # synthetic, no gate
    python -m scripts.convexity_trial_run               # REFUSES unsigned

Everything deciding lives in `docs/TRIALS/PREREG_CONVEXITY_PRESERVATION_1.md`;
this runner is the mechanical arm. Primary: trail_stop_20 − hold at the
+40 threshold, paired per episode, date-block bootstrap over crossing
months, three-way verdict at the declared 0.005 margin. Everything else is
SCREEN and says so on the receipt.
"""

from __future__ import annotations

import argparse
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
from backend.services.convexity_episodes import ARMS         # noqa: E402
from backend.services.net_tournament import (assert_signed,  # noqa: E402
                                             head_verdicts)
from backend.services.world_model import (block_bootstrap_paired,  # noqa: E402
                                          )

PREREG = REPO / "docs" / "TRIALS" / "PREREG_CONVEXITY_PRESERVATION_1.md"
EPISODES = _config.OPTIMUS_LEDGER_DIR / "convexity" / "episodes_v2.parquet"
OUT_DIR = _config.OPTIMUS_LEDGER_DIR / "convexity"

PRIMARY_ARM = "trail_stop_20"
PRIMARY_THRESHOLD = 0.4
ECONOMIC_MARGIN = 0.005          # terminal-wealth fraction over the window
NON_HOLD = tuple(a for a in ARMS if a != "hold")


def paired_contrast(df: pd.DataFrame, arm: str) -> dict:
    d = (df[f"tw_{arm}"] - df["tw_hold"]).to_numpy(float)
    dates = pd.to_datetime(df["crossing_date"]).to_numpy(
        dtype="datetime64[D]")
    # crossing months are the §58 unit; a block of ~21 calendar days of
    # crossings covers the within-month clustering
    return block_bootstrap_paired(d, dates, block_days=21,
                                  seed=20260819).as_dict()


def run(df: pd.DataFrame, *, tag: str) -> dict:
    out = {"trial": "CONVEXITY-PRESERVATION-1", "mode": tag,
           "started_at": datetime.now(timezone.utc).isoformat(
               timespec="seconds"),
           "n_episodes": int(len(df)),
           "cost_basis": "per-name measured TAQ one-way where retired; "
                         "3bp band midpoint else (baked at materialize)"}

    # PRIMARY: declared cell only
    prim_df = df[df["threshold"] == PRIMARY_THRESHOLD]
    contrasts = {}
    for arm in NON_HOLD:
        contrasts[arm] = paired_contrast(prim_df, arm)
    # verdict signs: the hypothesis is DESTRUCTION (mean < 0). head_verdicts
    # tests mean > 0, so feed the NEGATED contrast: positive = destroys.
    neg = {a: {**c, "mean": -c["mean"], "ci_lo": -c["ci_hi"],
               "ci_hi": -c["ci_lo"]} for a, c in contrasts.items()}
    verdicts = head_verdicts(neg, economic_bar=ECONOMIC_MARGIN)
    relabel = {"COMPLEX_WINS": "STOP_DESTROYS",
               "LINEAR_NONINFERIOR": "STOP_NONINFERIOR",
               "NOT_ESTABLISHED": "NOT_ESTABLISHED"}
    for a in verdicts:
        verdicts[a]["verdict"] = relabel[verdicts[a]["verdict"]]
        verdicts[a]["mean_tw_diff_arm_minus_hold"] = contrasts[a]["mean"]
    out["primary"] = {"cell": f"{PRIMARY_ARM} vs hold @ +40",
                      "n_episodes": int(len(prim_df)),
                      "contrasts_arm_minus_hold": contrasts,
                      "verdicts": verdicts,
                      "deciding_arm": PRIMARY_ARM}

    # SCREEN: full grid + capture family + §16 leg
    grid = {}
    for thr in sorted(df["threshold"].unique()):
        sub = df[df["threshold"] == thr]
        grid[f"thr_{thr}"] = {
            "n": int(len(sub)),
            **{arm: {"mean_tw_diff": round(float(
                (sub[f"tw_{arm}"] - sub["tw_hold"]).mean()), 5),
                "median_mfe_captured": (round(float(
                    sub[f"mfe_captured_{arm}"].median()), 4)
                    if sub[f"mfe_captured_{arm}"].notna().any() else None)}
               for arm in ARMS},
        }
    out["screen_grid"] = grid
    matched = df[df["control_tw_hold"].notna()]
    out["screen_winner_vs_control"] = {
        "n_matched": int(len(matched)),
        "mean_tw_hold": round(float(matched["tw_hold"].mean()), 5),
        "mean_control_tw_hold": round(float(
            matched["control_tw_hold"].mean()), 5),
        "note": "§16 leg — crossers vs matched non-winners, SCREEN only",
    }
    out["capture_family_hold"] = {
        "median_mfe": round(float(df["mfe"].median()), 4),
        "median_peak_giveback_hold": round(float(
            df["peak_giveback_hold"].median()), 4),
        "near_peak_at_end_rate": round(float(
            df["near_peak_at_end"].mean()), 4),
    }
    return out


def synthetic(seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = 4000
    dates = pd.to_datetime("2015-01-15") + pd.to_timedelta(
        rng.integers(0, 3600, n), unit="D")
    df = pd.DataFrame({"crossing_date": dates.astype(str),
                       "threshold": rng.choice([0.2, 0.4, 0.75, 1.0], n),
                       "tw_hold": rng.lognormal(0.01, 0.15, n)})
    for arm in NON_HOLD:
        df[f"tw_{arm}"] = df["tw_hold"] * (1 - 0.01) + rng.normal(
            0, 0.02, n)                       # planted: arms destroy ~1%
        df[f"mfe_captured_{arm}"] = rng.uniform(0, 1, n)
    df["mfe_captured_hold"] = rng.uniform(0, 1, n)
    df["control_tw_hold"] = df["tw_hold"] * rng.normal(0.98, 0.05, n)
    df["mfe"] = np.abs(rng.normal(0.1, 0.05, n))
    df["peak_giveback_hold"] = rng.uniform(0, 0.5, n)
    df["near_peak_at_end"] = rng.random(n) < 0.3
    return df


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="convexity_trial_run")
    ap.add_argument("--rehearsal", action="store_true")
    a = ap.parse_args(argv)
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")

    if a.rehearsal:
        print("REHEARSAL — synthetic episodes, planted 1% destruction. "
              "Nothing here is evidence about the world.")
        out = run(synthetic(), tag="REHEARSAL_SYNTHETIC")
        p = OUT_DIR / f"REHEARSAL_trial_{stamp}.json"
    else:
        signer = assert_signed(PREREG)      # raises while unsigned
        print(f"signed by: {signer}")
        df = pd.read_parquet(EPISODES)
        out = run(df, tag="REGISTERED")
        out["signed_by"] = signer
        p = OUT_DIR / f"trial_{stamp}.json"

    for arm, v in out["primary"]["verdicts"].items():
        star = "  <-- DECIDING" if arm == PRIMARY_ARM else ""
        print(f"  {arm:<16} tw_diff {v['mean_tw_diff_arm_minus_hold']:+.5f}"
              f"  mde {v['mde']:.5f}  -> {v['verdict']}{star}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"receipt: {p.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
