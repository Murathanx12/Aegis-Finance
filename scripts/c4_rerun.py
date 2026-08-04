"""C4 — before/after rerun: FRED publication-lag fix + FS-1 selection fix.

Three configurations, identical data and trainer (CrashPredictor):

  A  baseline (pre-fix):    reference-date FRED alignment, RECPROUSM156N in,
                            feature selection on the FULL sample
  B  +publication lags:     lag-shifted FRED (recession_prob excluded),
                            selection still full-sample  -> isolates C4
  C  +selection window:     lag-shifted FRED, selection on first 60% only
                            -> isolates FS-1; C is the honest pipeline

Reported: per-horizon validation AUC and Brier from the same purged
end-of-sample split. The A->C delta is the honest cost of the two leaks —
a paper exhibit either way (roadmap M4).

Run: .venv/Scripts/python.exe scripts/c4_rerun.py   (needs network + FRED key)
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.config import config
from backend.services.data_fetcher import DataFetcher
from engine.autoresearch.aegis_train import train_and_evaluate
from engine.training.feature_selection import SELECTED_FEATURES, select_features
from engine.training.features import build_feature_matrix, build_target_crash_multi
from engine.validation.purged_cv import HORIZON_DAYS, PurgedKFold, compute_eval_times

OUT_MD = Path(__file__).resolve().parents[1] / "docs" / "C4_FRED_LAG_RERUN_2026-08-04.md"
OUT_JSON = Path(__file__).resolve().parents[1] / "docs" / "c4_rerun_metrics.json"
HORIZONS = ("3m", "6m", "12m")

# Note on harness choice: an earlier draft used CrashPredictor's end-of-sample
# validation split, whose 2022-2026 window holds ~no crash labels — AUC was
# undefined in every cell. The purged 5-fold harness pools predictions across
# the whole 1990-2026 timeline (crash-rich eras included), which is also where
# the historically quoted AUC/Brier numbers come from.


def build_splits(features_sel, targets) -> dict:
    """Exactly aegis_prepare's split construction, per horizon."""
    splits = {}
    for horizon in HORIZONS:
        target = targets[horizon]
        valid = target.notna() & features_sel.notna().any(axis=1)
        X_valid = features_sel[valid]
        y_valid = target[valid]
        cv = PurgedKFold(n_splits=5, embargo_pct=0.01)
        eval_times = compute_eval_times(X_valid.index, HORIZON_DAYS.get(horizon, 63))
        folds = [
            {"fold": i, "train_idx": tr, "test_idx": te,
             "n_train": len(tr), "n_test": len(te)}
            for i, (tr, te) in enumerate(cv.split(X_valid, eval_times=eval_times))
        ]
        splits[horizon] = {"folds": folds, "X": X_valid, "y": y_valid}
    return splits


def run_config(name: str, features, targets, selection_frac: float) -> dict:
    sel_end = int(len(features) * selection_frac)
    try:
        selected = select_features(
            features.iloc[:sel_end], targets["3m"].iloc[:sel_end],
            max_features=30, min_features=20,
        )
    except Exception as e:
        print(f"  [{name}] selection failed ({e}); default list")
        selected = [f for f in SELECTED_FEATURES if f in features.columns]
    if len(selected) < 10:
        selected = [f for f in SELECTED_FEATURES if f in features.columns]

    data = {"splits": build_splits(features[selected], targets)}
    out = {"config": name, "n_features": len(selected), "features": selected}
    for h in HORIZONS:
        r = train_and_evaluate(data, horizon=h)
        out[h] = ({"auc": r.get("auc_roc"), "brier": r.get("brier_score"),
                   "n_folds": r.get("n_folds")} if r.get("success")
                  else {"auc": None, "brier": None,
                        "fail": r.get("reason", "unknown")})
        print(f"  [{name}] {h}: AUC={out[h].get('auc')} Brier={out[h].get('brier')}")
    return out


def main() -> None:
    print("C4 rerun — fetching data once...")
    fetcher = DataFetcher()
    data, _sector = fetcher.fetch_market_data()
    fred = fetcher.fetch_fred_data()
    threshold = -config["risk"]["crash_threshold"]
    targets = build_target_crash_multi(data, threshold=threshold)

    print("building features (A: reference-date alignment)...")
    feats_ref = build_feature_matrix(data, fred_data=fred,
                                     apply_publication_lags=False)
    print("building features (B/C: publication-lag alignment)...")
    feats_lag = build_feature_matrix(data, fred_data=fred,
                                     apply_publication_lags=True)

    rows = [
        run_config("A baseline (ref-date, full-sample selection)",
                   feats_ref, targets, 1.0),
        run_config("B +publication lags", feats_lag, targets, 1.0),
        run_config("C +selection window (honest pipeline)",
                   feats_lag, targets, 0.60),
    ]

    lines = [
        "# C4 — FRED publication-lag + FS-1 selection rerun",
        f"**Run:** {datetime.now(timezone.utc).isoformat(timespec='seconds')} · "
        "harness: purged 5-fold CV, predictions pooled across folds "
        "(`aegis_train.train_and_evaluate`, LGB+LR blend, isotonic, seed 42) · "
        "same data snapshot for all three configs",
        "",
        "A = pre-fix behavior (reference-date FRED, RECPROUSM156N included, "
        "full-sample LASSO selection). B adds publication-lag alignment "
        "(recession_prob excluded). C additionally restricts selection to the "
        "first 60% of the sample. **C is the honest pipeline; A-vs-C is the "
        "measured cost of the two leaks.**",
        "",
        "| Config | features | 3m AUC | 3m Brier | 6m AUC | 6m Brier | 12m AUC | 12m Brier |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        def fmt(h, k):
            v = r[h].get(k)
            return f"{v:.3f}" if isinstance(v, float) else "—"
        lines.append(
            f"| {r['config']} | {r['n_features']} | "
            + " | ".join(fmt(h, k) for h in HORIZONS for k in ("auc", "brier"))
            + " |"
        )
    lines += [
        "",
        "Notes: the deltas are the exhibit — if A > C, the historical numbers "
        "were flattered by look-ahead exactly as filed in "
        "`FULL_SAMPLE_FIT_AUDIT_2026-08-04.md`; if A ≈ C, the leaks were "
        "present but not load-bearing, which is also worth knowing. "
        "Validation split, trainer, seed and data snapshot are identical "
        "across rows; only alignment and selection window differ.",
    ]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    OUT_JSON.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    print(f"wrote {OUT_MD}")


if __name__ == "__main__":
    main()
