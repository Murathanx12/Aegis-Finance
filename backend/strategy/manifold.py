"""`do_predict` -- THE IN-MANIFOLD TRUST FLAG BESIDE EVERY SCORE (S4).

A model asked to score a feature vector unlike anything it was trained on will
answer, confidently, with an extrapolation. Nothing in Aegis has ever refused
that question. This module is the refusal: a per-row integer carried in the
same frame as the prediction, whose decrements NAME which detector objected.

    +2  the model is EXPIRED -- null prediction, by declaration
    +1  trustworthy: inside the training manifold on all three tests
     0  one detector rejected the row
    -1  two detectors rejected it
    -2  all three rejected it

Books gate entries on `do_predict == 1`. A score with `do_predict <= 0` is not
a weaker score; it is a score about a regime the model has never seen, and the
right action is to hold no position rather than a small one.

PROVENANCE AND LICENCE
=====================
The DESIGN is freqtrade's FreqAI (`freqai/freqai_interface.py::define_data_pipeline`,
semantics documented at `docs/freqai-configuration.md:166`), which is
**GPL-3.0**. No freqtrade code is copied, imported or adapted. The three
detectors themselves are stock scikit-learn estimators (BSD-3) that this module
CALLS; the spec below was written in English before this file existed and is
reproduced in `docs/BUILD_2026-09-08_R5_STRATEGY_PORTS.md` section S4.

THE SPEC (written first)
========================
1.  FIT on the training feature matrix, in a fixed pipeline order:
      VarianceThreshold(0)  ->  MinMaxScaler(-1, 1)  ->  three detectors.
    The scaler is fitted on TRAIN ONLY and the same fitted object transforms
    inference rows. Re-fitting the scaler on inference is how a scaled-outlier
    check silently becomes a no-op.
2.  DETECTORS, each independent, each contributing at most -1:
    (a) DISSIMILARITY INDEX. Compute the mean pairwise distance inside the
        training set, `d_train`. For an inference row, `d_i` is its distance to
        the NEAREST training row. Reject when `d_i / d_train > di_threshold`.
    (b) ONE-CLASS SVM with an RBF kernel, nu=0.01. Reject where the decision
        function falls below the `nu` QUANTILE of the training set's own
        decision function. THREE DELIBERATE DEVIATIONS FROM FREQTRADE, each
        made because the upstream choice FAILED the planted-fault test:
          i.   RBF, not the linear `SGDOneClassSVM`. A linear one-class SVM
               cannot bound a blob -- its decision function is `w.x - rho`, so
               a point arbitrarily far out along `+w` scores arbitrarily HIGH
               and is called an inlier. Fitted on a 3-d Gaussian blob it
               ACCEPTED (50, 50, 50), which is exactly the row this flag
               exists to refuse. An RBF kernel bounds in every direction.
          ii.  The threshold is the training `nu` quantile, not
               `predict() == -1`. At nu=0.01 `predict()` rejected 6.7% of its
               own 300-row training set and placed the blob's own CENTRE 7e-4
               below its boundary -- the most inlying point available was
               called an outlier. The quantile makes the self-rejection rate
               exactly `nu`, which is what `nu` is supposed to mean and what
               makes the outlier-protection guard comparable across the three
               detectors.
          iii. The bandwidth is the MEDIAN HEURISTIC,
               `gamma = 1 / (2 * median pairwise distance^2)`, derived from
               the training set, not sklearn's `gamma="scale"`. `"scale"` is
               `1 / (n_features * var(X))` and is calibrated for STANDARDISED
               data; on the MinMax(-1, 1) data this pipeline produces it came
               out near 3.0, far too narrow, and the decision function
               ANTI-correlated with distance from the centre
               (corr(df, -radius) = -0.16; the centre landed in the 0th
               percentile). At the median-heuristic bandwidth the same fit
               gives corr(df, -radius) = +0.94 and puts the centre at the 96th
               percentile, which is what a density-like score should do.
        Training rows are subsampled to `svm_max_rows` because RBF OCSVM is
        O(n^2).
    (c) DBSCAN. Fit on train; `eps` defaults to the training set's own median
        nearest-neighbour distance so it is DERIVED, not guessed. An inference
        row further than `eps` from every training CORE sample is rejected.
3.  OUTLIER PROTECTION. If a detector would reject more than
    `outlier_protection_percentage` (default 30%) of the TRAINING set, that
    detector is DISABLED with a stated reason and contributes nothing. Training
    on -- or gating with -- a detector that thinks a third of reality is an
    outlier is a broken detector, not a strict one. This is a refusal, not a
    silent shrink.
4.  REFUSAL. If NO detector could be fitted (too few rows, zero-variance
    features, sklearn absent), `score()` RAISES `ManifoldRefusal`. It does not
    return 1. An ungated flag that reads `1` is worse than no flag: every
    downstream book would treat it as "checked and trusted".
5.  EXPIRY. `expired_flags(n)` returns all-2 with null predictions and a
    reason. A stale model does not keep scoring silently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

CANNOT_DETERMINE = "CANNOT DETERMINE"

#: The trustworthy value. Books gate on this and only this.
DO_PREDICT_TRUSTWORTHY = 1
#: The model-expired sentinel. Predictions are NULL, not stale.
DO_PREDICT_EXPIRED = 2

DEFAULT_DI_THRESHOLD = 1.0
DEFAULT_SVM_NU = 0.01
DEFAULT_OUTLIER_PROTECTION_PCT = 30.0
MIN_TRAIN_ROWS = 20

DETECTORS = ("dissimilarity_index", "one_class_svm", "dbscan")


class ManifoldRefusal(RuntimeError):
    """No detector could be fitted, so no row can be called trustworthy."""


@dataclass
class ManifoldGate:
    """A fitted in-manifold gate. Built by `fit_manifold`, never by hand."""

    feature_names: tuple[str, ...]
    kept_features: tuple[str, ...]
    _scaler: Any = field(repr=False, default=None)
    _selector: Any = field(repr=False, default=None)
    _train_scaled: Any = field(repr=False, default=None)
    _d_train: float | None = None
    _di_threshold: float = DEFAULT_DI_THRESHOLD
    _svm: Any = field(repr=False, default=None)
    _svm_threshold: float | None = None
    _svm_gamma: float | None = None
    _dbscan_cores: Any = field(repr=False, default=None)
    _dbscan_eps: float | None = None
    enabled: tuple[str, ...] = ()
    disabled: Mapping[str, str] = field(default_factory=dict)
    n_train: int = 0
    outlier_protection_pct: float = DEFAULT_OUTLIER_PROTECTION_PCT

    # ----------------------------------------------------------------- scoring

    def _prepare(self, X: pd.DataFrame) -> np.ndarray:
        missing = [c for c in self.feature_names if c not in X.columns]
        if missing:
            raise ManifoldRefusal(
                f"REFUSED: inference frame is missing training features "
                f"{missing}. A gate fitted on one feature set cannot judge "
                f"another; imputing them would invent the manifold.")
        arr = X.loc[:, list(self.feature_names)].to_numpy(dtype=float)
        arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
        if self._selector is not None:
            arr = self._selector.transform(arr)
        return self._scaler.transform(arr)

    def _reject_di(self, Z: np.ndarray) -> np.ndarray:
        d = _nearest_distance(Z, self._train_scaled)
        if not self._d_train:
            return np.zeros(len(Z), dtype=bool)
        return (d / self._d_train) > self._di_threshold

    def _reject_svm(self, Z: np.ndarray) -> np.ndarray:
        return self._svm.decision_function(Z) < float(self._svm_threshold)

    def _reject_dbscan(self, Z: np.ndarray) -> np.ndarray:
        d = _nearest_distance(Z, self._dbscan_cores)
        return d > float(self._dbscan_eps)

    def rejections(self, X: pd.DataFrame) -> dict[str, np.ndarray]:
        """Which detector objected to which row. The decomposable cause."""
        if not self.enabled:
            raise ManifoldRefusal(
                f"REFUSED: no in-manifold detector is enabled, so no row can "
                f"be called trustworthy. Disabled: {dict(self.disabled)}. "
                f"Returning 1 here would tell every downstream book the row "
                f"was checked, which is the failure this flag exists to stop.")
        Z = self._prepare(X)
        out: dict[str, np.ndarray] = {}
        if "dissimilarity_index" in self.enabled:
            out["dissimilarity_index"] = self._reject_di(Z)
        if "one_class_svm" in self.enabled:
            out["one_class_svm"] = self._reject_svm(Z)
        if "dbscan" in self.enabled:
            out["dbscan"] = self._reject_dbscan(Z)
        return out

    def do_predict(self, X: pd.DataFrame) -> pd.Series:
        """The integer flag, one per row, index preserved."""
        rej = self.rejections(X)
        flag = np.full(len(X), DO_PREDICT_TRUSTWORTHY, dtype=int)
        for mask in rej.values():
            flag -= mask.astype(int)
        return pd.Series(flag, index=X.index, name="do_predict")

    def attach(self, scores: pd.DataFrame, *, score_col: str = "score"
               ) -> pd.DataFrame:
        """`do_predict` BESIDE the score, plus the per-detector reasons.

        The gated score is NULL, not zero and not shrunk: a name outside the
        manifold has no score, and a zero would rank it above every genuine
        negative.
        """
        out = scores.copy()
        rej = self.rejections(out)
        out["do_predict"] = self.do_predict(out)
        for name in DETECTORS:
            out[f"rejected_by_{name}"] = (
                rej[name] if name in rej else pd.Series(
                    [None] * len(out), index=out.index))
        if score_col in out.columns:
            out[f"{score_col}_gated"] = out[score_col].where(
                out["do_predict"] == DO_PREDICT_TRUSTWORTHY)
        return out

    def report(self) -> dict:
        return {
            "n_train": self.n_train,
            "features": list(self.feature_names),
            "features_kept_after_variance_threshold": list(self.kept_features),
            "detectors_enabled": list(self.enabled),
            "detectors_disabled": dict(self.disabled),
            "outlier_protection_percentage": self.outlier_protection_pct,
            "di_threshold": self._di_threshold,
            "svm_decision_threshold": self._svm_threshold,
            "svm_gamma_median_heuristic": self._svm_gamma,
            "dbscan_eps": self._dbscan_eps,
            "gate": "books admit a name only when do_predict == 1",
            "note": ("each rejecting detector subtracts one, so the flag's "
                     "value names how many objected and the per-detector "
                     "columns name which"),
        }


def expired_flags(index: Sequence[Any], *, reason: str) -> pd.DataFrame:
    """A stale model emits NULL predictions with `do_predict == 2`, not scores.

    freqtrade's rule, and the right one: an expired model that keeps scoring is
    indistinguishable from a live one at the point of use.
    """
    idx = pd.Index(list(index))
    return pd.DataFrame({"do_predict": DO_PREDICT_EXPIRED,
                         "score": [None] * len(idx),
                         "expiry_reason": reason}, index=idx)


# --------------------------------------------------------------------------


def _nearest_distance(Z: np.ndarray, ref: np.ndarray) -> np.ndarray:
    """Euclidean distance from each row of Z to the nearest row of ref."""
    if ref is None or len(ref) == 0:
        return np.full(len(Z), np.inf)
    out = np.empty(len(Z), dtype=float)
    step = max(1, int(2_000_000 // max(1, ref.shape[0])))
    for i in range(0, len(Z), step):
        block = Z[i:i + step]
        d = np.sqrt(((block[:, None, :] - ref[None, :, :]) ** 2).sum(axis=2))
        out[i:i + step] = d.min(axis=1)
    return out


def _mean_pairwise_distance(Z: np.ndarray, *, cap: int = 400,
                            seed: int = 20260908) -> float:
    rng = np.random.default_rng(seed)
    if len(Z) > cap:
        Z = Z[rng.choice(len(Z), cap, replace=False)]
    if len(Z) < 2:
        return 0.0
    d = np.sqrt(((Z[:, None, :] - Z[None, :, :]) ** 2).sum(axis=2))
    iu = np.triu_indices(len(Z), k=1)
    return float(np.mean(d[iu]))


def _median_heuristic_gamma(Z: np.ndarray, *, cap: int = 400,
                            seed: int = 20260908) -> float:
    """`1 / (2 * median pairwise distance^2)`. DERIVED from the data, so the
    kernel's width scales with the manifold instead of with a constant that
    assumed a different scaler."""
    rng = np.random.default_rng(seed)
    S = Z[rng.choice(len(Z), cap, replace=False)] if len(Z) > cap else Z
    if len(S) < 2:
        return 1.0
    d = np.sqrt(((S[:, None, :] - S[None, :, :]) ** 2).sum(axis=2))
    med = float(np.median(d[np.triu_indices(len(S), k=1)]))
    return 1.0 / (2.0 * med ** 2) if med > 0 else 1.0


def _median_nn_distance(Z: np.ndarray) -> float:
    if len(Z) < 2:
        return 0.0
    d = np.sqrt(((Z[:, None, :] - Z[None, :, :]) ** 2).sum(axis=2))
    np.fill_diagonal(d, np.inf)
    return float(np.median(d.min(axis=1)))


def fit_manifold(X_train: pd.DataFrame,
                 *,
                 di_threshold: float = DEFAULT_DI_THRESHOLD,
                 svm_nu: float = DEFAULT_SVM_NU,
                 dbscan_eps: float | None = None,
                 dbscan_min_samples: int | None = None,
                 svm_max_rows: int = 4000,
                 outlier_protection_percentage: float = DEFAULT_OUTLIER_PROTECTION_PCT,
                 use: Sequence[str] = DETECTORS,
                 seed: int = 20260908) -> ManifoldGate:
    """Fit the three detectors on the training manifold. See the module spec."""
    if X_train is None or len(X_train) < MIN_TRAIN_ROWS:
        raise ManifoldRefusal(
            f"REFUSED: {0 if X_train is None else len(X_train)} training rows, "
            f"minimum {MIN_TRAIN_ROWS}. A manifold estimated from a handful of "
            f"points would reject or accept on noise.")
    try:
        from sklearn.cluster import DBSCAN
        from sklearn.feature_selection import VarianceThreshold
        from sklearn.preprocessing import MinMaxScaler
        from sklearn.svm import OneClassSVM
    except ImportError as exc:                                   # pragma: no cover
        raise ManifoldRefusal(
            f"REFUSED: scikit-learn is not importable ({exc}). The gate cannot "
            f"be fitted, so no row may be called trustworthy.") from exc

    names = tuple(str(c) for c in X_train.columns)
    arr = np.nan_to_num(X_train.to_numpy(dtype=float), nan=0.0,
                        posinf=0.0, neginf=0.0)

    if not bool(np.any(np.nanvar(arr, axis=0) > 0.0)):
        raise ManifoldRefusal(
            "REFUSED: every training feature has zero variance. There is no "
            "manifold to be inside of, so nothing can be outside it either.")
    selector = VarianceThreshold(threshold=0.0)
    arr2 = selector.fit_transform(arr)
    kept = tuple(n for n, m in zip(names, selector.get_support()) if m)

    scaler = MinMaxScaler(feature_range=(-1.0, 1.0)).fit(arr2)
    Z = scaler.transform(arr2)

    gate = ManifoldGate(feature_names=names, kept_features=kept,
                        _scaler=scaler, _selector=selector, _train_scaled=Z,
                        n_train=int(len(Z)),
                        outlier_protection_pct=float(outlier_protection_percentage))

    enabled: list[str] = []
    disabled: dict[str, str] = {}
    limit = float(outlier_protection_percentage) / 100.0

    def _guard(name: str, self_reject_rate: float) -> bool:
        if self_reject_rate > limit:
            disabled[name] = (
                f"DISABLED: would reject {self_reject_rate:.1%} of its OWN "
                f"training set, above outlier_protection_percentage "
                f"{outlier_protection_percentage:.0f}%. A detector that thinks "
                f"a third of the data it was fitted on is an outlier is broken, "
                f"not strict; it is refused rather than applied to a decimated "
                f"set.")
            return False
        enabled.append(name)
        return True

    if "dissimilarity_index" in use:
        gate._d_train = _mean_pairwise_distance(Z, seed=seed)
        gate._di_threshold = float(di_threshold)
        if not gate._d_train:
            disabled["dissimilarity_index"] = (
                "DISABLED: the training rows are identical, so the mean "
                "pairwise distance is 0 and every ratio would be undefined.")
        else:
            # leave-one-out self-check: the nearest OTHER training row
            d = np.sqrt(((Z[:, None, :] - Z[None, :, :]) ** 2).sum(axis=2))
            np.fill_diagonal(d, np.inf)
            rate = float(np.mean((d.min(axis=1) / gate._d_train) > di_threshold))
            _guard("dissimilarity_index", rate)

    if "one_class_svm" in use:
        rng = np.random.default_rng(seed)
        Zs = (Z[rng.choice(len(Z), int(svm_max_rows), replace=False)]
              if len(Z) > int(svm_max_rows) else Z)
        gamma = _median_heuristic_gamma(Zs, seed=seed)
        svm = OneClassSVM(kernel="rbf", nu=float(svm_nu), gamma=gamma)
        svm.fit(Zs)
        gate._svm_gamma = float(gamma)
        gate._svm = svm
        df = svm.decision_function(Z)
        gate._svm_threshold = float(np.quantile(df, min(0.99, float(svm_nu))))
        _guard("one_class_svm", float(np.mean(df < gate._svm_threshold)))

    if "dbscan" in use:
        eps = float(dbscan_eps) if dbscan_eps else _median_nn_distance(Z) * 3.0
        if eps <= 0:
            disabled["dbscan"] = (
                "DISABLED: the derived eps is 0 (identical training rows).")
        else:
            ms = int(dbscan_min_samples or max(2, min(10, len(Z) // 20)))
            db = DBSCAN(eps=eps, min_samples=ms).fit(Z)
            cores = Z[db.core_sample_indices_] if len(
                db.core_sample_indices_) else np.empty((0, Z.shape[1]))
            gate._dbscan_cores = cores
            gate._dbscan_eps = eps
            if len(cores) == 0:
                disabled["dbscan"] = (
                    "DISABLED: DBSCAN found no core samples at the derived eps, "
                    "so every inference row would be rejected.")
            else:
                _guard("dbscan", float(np.mean(_nearest_distance(Z, cores) > eps)))

    gate.enabled = tuple(enabled)
    gate.disabled = disabled
    if not enabled:
        raise ManifoldRefusal(
            f"REFUSED: all three in-manifold detectors were disabled. "
            f"{disabled}. `do_predict` would be 1 for every row, which reads "
            f"as 'checked and trusted' -- so it refuses instead.")
    return gate


__all__ = ["CANNOT_DETERMINE", "DETECTORS", "DEFAULT_DI_THRESHOLD",
           "DEFAULT_OUTLIER_PROTECTION_PCT", "DEFAULT_SVM_NU",
           "DO_PREDICT_EXPIRED", "DO_PREDICT_TRUSTWORTHY", "ManifoldGate",
           "ManifoldRefusal", "MIN_TRAIN_ROWS", "expired_flags", "fit_manifold"]
