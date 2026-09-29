"""Feature preparation and the baselines that must be alive before a network is read.

Baselines:
  zero      -- the cross-sectional median: predicts 0 excess, P(beat) = 0.5
  momentum  -- 12-1 momentum as the score
  trailing vol -- the MAGNITUDE baseline: sigma = vol_63 * sqrt(h/252)
  ridge     -- on per-date ranked features (median-imputed + missing flags)
  lightgbm  -- on raw features (NaN native), library defaults, no monotone constraints

Every model's probability of beating the median comes from a logistic map of its
score fitted on the VALIDATION block (strictly earlier than test).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from nn_lab import config as C
from nn_lab.table import GROUPS

LGB_PARAMS = {  # copied from backend/services/xs_ranker.LGB_PARAMS (library defaults)
    "objective": "regression", "learning_rate": 0.04, "num_leaves": 31,
    "min_child_samples": 200, "feature_fraction": 0.75, "bagging_fraction": 0.8,
    "bagging_freq": 1, "lambda_l2": 5.0, "n_estimators": 350, "verbose": -1,
}


def active_groups(train: pd.DataFrame, groups=None) -> list[str]:
    """Groups whose non-null share of TRAINING rows clears MIN_GROUP_COVERAGE."""
    out = []
    for g in (groups or GROUPS):
        cols = [c for c in GROUPS[g] if c in train.columns]
        if cols and float(train[cols].notna().any(axis=1).mean()) >= C.MIN_GROUP_COVERAGE:
            out.append(g)
    return out


def feature_list(groups: list[str]) -> list[str]:
    return [c for g in groups for c in GROUPS[g]]


def rank_gauss(df: pd.DataFrame, feats: list[str]) -> np.ndarray:
    """Per-date percentile rank mapped to [-1, 1]; NaN stays NaN. Uses only date-t rows."""
    r = df.groupby("date")[feats].rank(pct=True)
    return ((r.values - 0.5) * 2.0).astype("float32")


def flagged_groups(groups) -> list[str]:
    """Groups allowed a missing-indicator: only those whose coverage was decided AT THE
    TIME. F2 (review 2026-09-29): `missing_analyst` was 100% on names that later died and
    10.8% on survivors, because the source is a 2026 snapshot. A flag whose value was set
    by a later pull is a label, not a feature."""
    return [g for g in groups if C.GROUP_COVERAGE.get(g) == "AT_THE_TIME" and g != "price"]


def design_matrix(df: pd.DataFrame, groups: list[str]) -> tuple[np.ndarray, list[str]]:
    """Ranked features, imputed at the cross-sectional median (0 after ranking), plus a
    missing-indicator for each group in `flagged_groups` (never for a later-pull group).
    This is SimpleImputer(median) done per date."""
    feats = feature_list(groups)
    X = rank_gauss(df, feats)
    miss = np.isnan(X)
    names = list(feats)
    flags = []
    for g in flagged_groups(groups):
        idx = [feats.index(c) for c in GROUPS[g]]
        flags.append(miss[:, idx].all(axis=1).astype("float32")[:, None])
        names.append(f"missing_{g}")
    X = np.where(miss, 0.0, X).astype("float32")
    return np.hstack([X] + flags), names


def winsorize_by_date(df: pd.DataFrame, col: str, lo=0.01, hi=0.99) -> np.ndarray:
    g = df.groupby("date")[col]
    a, b = g.transform(lambda s: s.quantile(lo)), g.transform(lambda s: s.quantile(hi))
    return df[col].clip(a, b).values.astype("float32")


def platt(score_val: np.ndarray, y_val: np.ndarray):
    """Logistic map score -> P(y > 0), fitted on the validation block only."""
    from sklearn.linear_model import LogisticRegression
    m = np.isfinite(score_val) & np.isfinite(y_val)
    s = score_val[m].reshape(-1, 1)
    mu, sd = float(np.mean(s)), float(np.std(s) or 1.0)
    lr = LogisticRegression(C=1.0)
    lr.fit((s - mu) / sd, (y_val[m] > 0).astype(int))
    return lambda x: lr.predict_proba(((np.asarray(x).reshape(-1, 1)) - mu) / sd)[:, 1]


def per_date_rank(df: pd.DataFrame, col: str) -> np.ndarray:
    return df.groupby("date")[col].rank(pct=True).values


def fit_ridge(Xtr, ytr, alpha: float = 10.0):
    from sklearn.linear_model import Ridge
    m = np.isfinite(ytr)
    return Ridge(alpha=alpha).fit(Xtr[m], ytr[m])


def fit_lgbm(Xtr: pd.DataFrame, ytr: np.ndarray, seed: int):
    import lightgbm as lgb
    m = np.isfinite(ytr)
    model = lgb.LGBMRegressor(**LGB_PARAMS, random_state=seed, n_jobs=4)
    model.fit(Xtr[m], ytr[m])
    return model
