"""The learner's model arms. Every one predicts EXCESS return, on one scale.

THE TWO ARMS, AND WHY THE COMPARISON IS THE EXPERIMENT
=====================================================
Each learnable model is fitted twice against the same rows:

    raw       target = excess_h                 features = X + [prior_h]
    residual  target = excess_h - prior_h       features = X
              prediction = prior_h + f(X)

Both arms see the same information -- the prior is a column in one and the
offset in the other -- so the difference between them is purely *how the
engine's belief enters*, which is the architectural question this session was
built to answer. The residual arm cannot be beaten by the prior on its own
region structure; it can only lose by adding noise on top of it.

The prior is DELIBERATELY EXCLUDED from the residual arm's feature matrix. If
it were a feature there too, the residual arm would be the raw arm wearing a
different target and the comparison would measure nothing.

WHAT DOES NOT RELAX
===================
* `fillna(0)` is banned. Missing stays missing: LightGBM consumes NaN natively;
  ridge and the MLP median-impute INSIDE their pipeline, fitted on train only.
* Hyper-parameters are chosen on an INNER TEMPORAL HOLDOUT -- the last
  `INNER_HOLDOUT_MONTHS` months of the training window -- never by random
  k-fold, which on a panel hands a model its own neighbours' futures.
* The training target is winsorised at the 1st/99th train percentile because a
  single +900% name-month otherwise owns the squared-error gradient. The
  EVALUATION target is never winsorised: the tail is the result.
* Seeds are `np.random.default_rng` / `torch.manual_seed`, never
  `np.random.seed`.

THE NEURAL ARM
==============
torch 2.11 (CPU) is present in this environment, so the MLP is a small torch
network (n -> 64 -> 32 -> 1, GELU, dropout 0.1, AdamW, early stopping on the
inner temporal holdout). `sklearn.neural_network.MLPRegressor` is the declared
fallback and is used automatically if the torch import fails, with
`impl="sklearn_mlp"` recorded so no reader has to guess which one ran.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

try:  # pragma: no cover - environment dependent
    import torch
    import torch.nn as nn
    _TORCH = True
except Exception:  # pragma: no cover
    _TORCH = False

try:  # pragma: no cover
    import lightgbm as lgb
    _LGBM = True
except Exception:  # pragma: no cover
    _LGBM = False

SEED = 20260902
INNER_HOLDOUT_MONTHS = 12
WINSOR = (0.01, 0.99)

RIDGE_ALPHAS = (1.0, 10.0, 100.0, 1000.0, 10000.0)

LGBM_PARAMS = dict(
    n_estimators=400, learning_rate=0.05, num_leaves=31, max_depth=-1,
    min_child_samples=200, subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
    reg_lambda=5.0, n_jobs=4, verbose=-1, random_state=SEED,
)

#: model kinds with two meaningful arms
LEARNABLE = ("ridge", "lgbm", "mlp")
CLASSIFIER = "lgbm_clf"
ARMS = ("raw", "residual")


def mlp_impl() -> str:
    return "torch_mlp" if _TORCH else "sklearn_mlp"


# ------------------------------------------------------------------ helpers

def _inner_split(train: pd.DataFrame):
    """Last INNER_HOLDOUT_MONTHS months of train -> validation. Temporal."""
    months = sorted(train["month"].unique())
    if len(months) <= INNER_HOLDOUT_MONTHS + 6:
        cut = months[max(1, int(len(months) * 0.8))]
    else:
        cut = months[-INNER_HOLDOUT_MONTHS]
    fit = (train["month"] < cut).to_numpy()
    val = (train["month"] >= cut).to_numpy()
    if val.sum() == 0 or fit.sum() == 0:
        return np.ones(len(train), bool), np.zeros(len(train), bool)
    return fit, val


def _winsorise(y: np.ndarray) -> tuple[np.ndarray, tuple[float, float]]:
    lo, hi = np.nanquantile(y, WINSOR[0]), np.nanquantile(y, WINSOR[1])
    return np.clip(y, lo, hi), (float(lo), float(hi))


def arm_target(df: pd.DataFrame, arm: str, horizon_months: int,
               benchmark: str = "vw") -> np.ndarray:
    h = horizon_months
    if arm == "raw":
        return df[f"excess_{benchmark}_{h}m"].to_numpy(dtype="float64")
    if arm == "residual":
        return df[f"resid_{benchmark}_{h}m"].to_numpy(dtype="float64")
    raise ValueError(f"unknown arm {arm!r}")


def arm_features(feature_cols: list[str], arm: str, horizon_months: int) -> list[str]:
    """The raw arm sees the prior as a COLUMN; the residual arm sees it as the
    offset and must not also see it as a feature."""
    if arm == "raw":
        return list(feature_cols) + [f"prior_{horizon_months}m"]
    return list(feature_cols)


def arm_reconstruct(pred_arm: np.ndarray, df: pd.DataFrame, arm: str,
                    horizon_months: int) -> np.ndarray:
    """Put both arms on the SAME scale: predicted excess return.

    The residual arm's identity -- prediction = prior + residual -- is pinned
    by `backend/tests/test_learner_pit.py`.
    """
    if arm == "raw":
        return np.asarray(pred_arm, dtype="float64")
    return np.asarray(pred_arm, dtype="float64") + \
        df[f"prior_{horizon_months}m"].to_numpy(dtype="float64")


# ------------------------------------------------------------------- models

def _fit_ridge(Xf, yf, Xv, yv):
    best, best_mse, best_alpha = None, np.inf, None
    for a in RIDGE_ALPHAS:
        pipe = Pipeline([
            ("impute", SimpleImputer(strategy="median")),   # never fillna(0)
            ("scale", StandardScaler()),
            ("model", Ridge(alpha=a)),
        ])
        pipe.fit(Xf, yf)
        mse = float(np.mean((pipe.predict(Xv) - yv) ** 2)) if len(yv) else np.inf
        if mse < best_mse:
            best, best_mse, best_alpha = pipe, mse, a
    return best, {"alpha": best_alpha, "inner_val_mse": best_mse}


def _fit_lgbm(Xf, yf, Xv, yv, classifier: bool = False):
    if not _LGBM:
        raise RuntimeError("lightgbm is not installed")
    Model = lgb.LGBMClassifier if classifier else lgb.LGBMRegressor
    m = Model(**LGBM_PARAMS)
    cb = [lgb.early_stopping(40, verbose=False), lgb.log_evaluation(0)]
    if len(yv):
        m.fit(Xf, yf, eval_set=[(Xv, yv)], callbacks=cb)
        best_it = int(getattr(m, "best_iteration_", 0) or LGBM_PARAMS["n_estimators"])
    else:
        m.fit(Xf, yf)
        best_it = LGBM_PARAMS["n_estimators"]
    return m, {"best_iteration": best_it}


def _fit_mlp(Xf, yf, Xv, yv):
    """MLP with an early stop on the inner temporal holdout."""
    pre = Pipeline([("impute", SimpleImputer(strategy="median")),
                    ("scale", StandardScaler())])
    Zf = pre.fit_transform(Xf)
    Zv = pre.transform(Xv) if len(yv) else Zf[:0]
    if not _TORCH:
        from sklearn.neural_network import MLPRegressor
        net = MLPRegressor(hidden_layer_sizes=(64, 32), alpha=1e-3, max_iter=60,
                           early_stopping=False, random_state=SEED)
        # The target is scaled up so the optimiser sees gradients of a sane
        # magnitude; predictions are scaled back on the way out.
        net.fit(Zf, yf * 100.0)
        return (pre, net, "sklearn_mlp"), {"impl": "sklearn_mlp"}

    torch.manual_seed(SEED)
    torch.set_num_threads(4)
    n_in = Zf.shape[1]
    net = nn.Sequential(nn.Linear(n_in, 64), nn.GELU(), nn.Dropout(0.1),
                        nn.Linear(64, 32), nn.GELU(), nn.Linear(32, 1))
    opt = torch.optim.AdamW(net.parameters(), lr=1e-3, weight_decay=1e-4)
    lossf = nn.MSELoss()
    tf = torch.tensor(Zf, dtype=torch.float32)
    # x100 so the loss is not 1e-6 and Adam's epsilon is not the whole story.
    ty = torch.tensor(yf * 100.0, dtype=torch.float32).view(-1, 1)
    tv = torch.tensor(Zv, dtype=torch.float32) if len(yv) else None
    tvy = torch.tensor(yv * 100.0, dtype=torch.float32).view(-1, 1) if len(yv) else None

    n, bs, best, best_state, bad = len(tf), 4096, np.inf, None, 0
    g = torch.Generator().manual_seed(SEED)
    for _epoch in range(30):
        net.train(True)
        perm = torch.randperm(n, generator=g)
        for i in range(0, n, bs):
            idx = perm[i:i + bs]
            opt.zero_grad()
            lossf(net(tf[idx]), ty[idx]).backward()
            opt.step()
        if tv is None:
            continue
        net.train(False)
        with torch.no_grad():
            v = float(lossf(net(tv), tvy))
        if v < best - 1e-6:
            best, bad = v, 0
            best_state = {k: p.detach().clone() for k, p in net.state_dict().items()}
        else:
            bad += 1
            if bad >= 4:
                break
    if best_state is not None:
        net.load_state_dict(best_state)
    net.train(False)
    return (pre, net, "torch_mlp"), {"impl": "torch_mlp", "inner_val_mse": best}


def _predict_mlp(fitted, X):
    pre, net, impl = fitted
    Z = pre.transform(X)
    if impl == "sklearn_mlp":
        return net.predict(Z) / 100.0
    with torch.no_grad():
        return net(torch.tensor(Z, dtype=torch.float32)).numpy().ravel() / 100.0


# ------------------------------------------------------------ the public API

def fit_predict(kind: str, arm: str, train: pd.DataFrame, test: pd.DataFrame,
                feature_cols: list[str], horizon_months: int,
                benchmark: str = "vw", return_model: bool = False,
                shuffle_target: bool = False, shuffle_seed: int | None = None):
    """Fit one arm on `train`, predict EXCESS return on `test`.

    Returns (predicted excess, fit metadata) -- or (pred, meta, fitted) when
    `return_model`. Both arms come back on the excess scale so the evaluator
    never has to know which arm produced a number.

    `shuffle_target=True` permutes the TRAINING target WITHIN EACH MONTH, so
    the cross-sectional pairing between features and outcome is destroyed while
    the month structure, the market factor and the whole pipeline are left
    exactly as they were. Any OOS rank IC that survives that is a leak in the
    plumbing, not a signal. (S24: a shuffled-DATE null was the calendar; the
    shuffle must be WITHIN the date block, or it tests the wrong thing.)

    ONE shuffled draw is a LEAK check and nothing more. S36: a model fitted on
    noise holds one persistent tilt, so a single draw's naive t spans -9..+12
    across seeds and `|t| < 2` on one draw is close to a coin flip. A SKILL
    claim owes the model-null percentile -- fit this same pipeline with >= 64
    distinct `shuffle_seed`s and quote the percentile (learner/nullbar.py).
    `shuffle_seed=None` keeps the historical fixed seed, so v1's single null
    arm stays reproducible.
    """
    cols = arm_features(feature_cols, arm, horizon_months)
    y = arm_target(train, arm, horizon_months, benchmark)
    keep = np.isfinite(y)
    tr = train.loc[keep]
    y = y[keep]
    if shuffle_target:
        rng = np.random.default_rng(SEED if shuffle_seed is None
                                    else shuffle_seed)     # never np.random.seed
        y = pd.Series(y, index=tr.index).groupby(tr["month"]).transform(
            lambda s: s.to_numpy()[rng.permutation(len(s))]).to_numpy()
    yw, bounds = _winsorise(y)

    fit_m, val_m = _inner_split(tr)
    Xall = tr[cols].to_numpy(dtype="float64")
    Xf, yf = Xall[fit_m], yw[fit_m]
    Xv, yv = Xall[val_m], yw[val_m]
    Xte = test[cols].to_numpy(dtype="float64")

    if kind == "ridge":
        model, meta = _fit_ridge(Xf, yf, Xv, yv)
        raw = model.predict(Xte)
    elif kind == "lgbm":
        model, meta = _fit_lgbm(Xf, yf, Xv, yv)
        raw = model.predict(Xte)
    elif kind == "mlp":
        model, meta = _fit_mlp(Xf, yf, Xv, yv)
        raw = _predict_mlp(model, Xte)
    else:
        raise ValueError(f"unknown model kind {kind!r}")

    meta = dict(meta)
    meta.update({"kind": kind, "arm": arm, "n_train": int(len(tr)),
                 "n_train_months": int(tr["month"].nunique()),
                 "winsor_bounds": bounds, "n_features": len(cols),
                 "shuffled_null": bool(shuffle_target), "feature_cols": cols})
    if shuffle_target:
        # which draw this was -- a null distribution is only auditable if every
        # draw names its seed (learner/nullbar.py wants >= 64 of these)
        meta["shuffle_seed"] = int(SEED if shuffle_seed is None else shuffle_seed)
    pred = arm_reconstruct(raw, test, arm, horizon_months)
    if return_model:
        return pred, meta, model
    return pred, meta


def predict_with(kind: str, model, arm: str, df: pd.DataFrame, cols: list[str],
                 horizon_months: int) -> np.ndarray:
    """Score an already-fitted model. Used by the daily shadow.

    The classifier is NOT put through `arm_reconstruct`: its output is a
    probability, and adding a return to a probability would produce a number
    with no unit that still sorts.
    """
    X = df[cols].to_numpy(dtype="float64")
    if kind == CLASSIFIER:
        return model.predict_proba(X)[:, 1]
    raw = _predict_mlp(model, X) if kind == "mlp" else model.predict(X)
    return arm_reconstruct(raw, df, arm, horizon_months)


def prediction_unit(kind: str) -> str:
    return ("P(excess > 0) over the horizon -- a probability, NOT a return"
            if kind == CLASSIFIER else "expected EXCESS return over the horizon")


def fit_classifier(train: pd.DataFrame, feature_cols: list[str], horizon_months: int,
                   benchmark: str = "vw"):
    """Fit the classifier head and hand back the model itself, for sealing."""
    h = horizon_months
    cols = list(feature_cols) + [f"prior_{h}m"]
    y = train[f"pos_{benchmark}_{h}m"].to_numpy(dtype="float64")
    keep = np.isfinite(y)
    tr, y = train.loc[keep], y[keep]
    fit_m, val_m = _inner_split(tr)
    X = tr[cols].to_numpy(dtype="float64")
    model, meta = _fit_lgbm(X[fit_m], y[fit_m], X[val_m], y[val_m], classifier=True)
    meta = dict(meta)
    meta.update({"kind": CLASSIFIER, "arm": "engine_feature", "n_train": int(len(tr)),
                 "n_train_months": int(tr["month"].nunique()), "n_features": len(cols)})
    return model, cols, meta


def fit_predict_proba(train: pd.DataFrame, test: pd.DataFrame,
                      feature_cols: list[str], horizon_months: int,
                      benchmark: str = "vw") -> tuple[np.ndarray, dict]:
    """The classifier head: P(excess > 0) at the horizon.

    There is ONE arm. A probability has no residual -- `prior - P` is not a
    quantity -- so the engine's belief enters the only way it can, as a feature.
    """
    h = horizon_months
    cols = list(feature_cols) + [f"prior_{h}m"]
    y = train[f"pos_{benchmark}_{h}m"].to_numpy(dtype="float64")
    keep = np.isfinite(y)
    tr, y = train.loc[keep], y[keep]
    fit_m, val_m = _inner_split(tr)
    Xall = tr[cols].to_numpy(dtype="float64")
    model, meta = _fit_lgbm(Xall[fit_m], y[fit_m], Xall[val_m], y[val_m], classifier=True)
    p = model.predict_proba(test[cols].to_numpy(dtype="float64"))[:, 1]
    meta = dict(meta)
    meta.update({"kind": CLASSIFIER, "arm": "engine_feature", "n_train": int(len(tr))})
    return p, meta


def gain_importance(model, cols: list[str], top: int = 25) -> dict:
    """LightGBM gain importance, normalised. Used to decide whether the shadow
    can score honestly -- not to claim a mechanism."""
    try:
        imp = pd.Series(model.booster_.feature_importance("gain"), index=cols)
    except Exception:
        return {}
    tot = float(imp.sum()) or 1.0
    return (imp / tot).sort_values(ascending=False).head(top).round(4).to_dict()


def describe() -> dict:
    return {
        "arms": list(ARMS),
        "arm_semantics": {
            "raw": "target = excess; features = X + prior column",
            "residual": "target = excess - prior; features = X (prior is the OFFSET, "
                        "never also a feature); prediction = prior + f(X)",
        },
        "kinds": list(LEARNABLE) + [CLASSIFIER],
        "mlp_impl": mlp_impl(),
        "lightgbm_available": _LGBM,
        "torch_available": _TORCH,
        "seed": SEED,
        "hyperparameter_selection": (
            f"inner TEMPORAL holdout -- the last {INNER_HOLDOUT_MONTHS} months of the "
            "training window. Never random k-fold."),
        "winsorisation": {"train_target_quantiles": list(WINSOR),
                          "evaluation_target": "NEVER winsorised"},
        "missing_policy": "LightGBM consumes NaN; ridge/MLP median-impute inside the "
                          "pipeline fitted on train only. fillna(0) is banned.",
        "lgbm_params": dict(LGBM_PARAMS),
        "ridge_alphas": list(RIDGE_ALPHAS),
    }


__all__ = ["LEARNABLE", "CLASSIFIER", "ARMS", "SEED", "fit_predict", "fit_predict_proba",
           "predict_with", "fit_classifier", "prediction_unit", "arm_target", "arm_features", "arm_reconstruct",
           "gain_importance", "mlp_impl", "describe"]
