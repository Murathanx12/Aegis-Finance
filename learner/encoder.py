"""LEARNER v2 -- ONE shared encoder, four horizons, two heads each.

WHY A SHARED TRUNK AT ALL
=========================
v1 fitted a separate model per (kind, arm, horizon). That is eight independent
views of the same 441k rows, each of which had to rediscover "what a cheap,
thinly-covered, recently-drawn-down name looks like" from scratch, and each of
which spent its capacity on a target whose noise dominates at 1 month and
recedes at 12. The v1 receipt shows exactly that shape: the engine prior's IC
rises monotonically with horizon (t 12.7 -> 20.2 -> 28.2 -> 34.5) while the 1m
money t stops at 1.49.

So v2 asks the obvious next question: does a representation LEARNED ACROSS ALL
FOUR HORIZONS AT ONCE -- where the 12m target, which is the least noisy, gets
to shape the trunk that the 1m head reads -- predict the 1m cross-section
better than a 1m-only model? That is the only architectural claim here. It is
a claim about SAMPLE EFFICIENCY, not about a new information source: the
feature matrix is byte-identical to v1's 49 columns.

TWO HEADS PER HORIZON
=====================
    reg_h   -> expected EXCESS return over h months (a return)
    clf_h   -> P(excess > 0) over h months          (a probability)

They are different objects and the code never adds one to the other. The
classifier exists because v1's champion WAS a classifier (`lgbm_clf`, IC .0954)
and yet v1 never scored a single calibration number for it -- so the shadow
book published `P(beat) = 0.494` with nothing on disk saying whether that is a
literal probability or an uncalibrated ranking score. `learner/calibrate.py`
answers it; this file produces the numbers it answers with.

THE PIT PROBLEM A MULTI-HORIZON MODEL CREATES, AND HOW IT IS CLOSED
===================================================================
v1's split rule is "train on rows whose TARGET HAD MATURED before the test year
opened". With four targets per row there are four different maturity dates, and
the naive multi-task fit -- admit a row if ANY target matured, then train every
head on it -- hands the 12m head eleven months of the test year. That is the
single leak this architecture invites, so it is closed structurally rather than
by care: a row is admitted if ANY horizon has matured, and then EVERY HORIZON'S
TARGET IS INDIVIDUALLY MASKED OUT unless that horizon's own `mat_date` is
strictly before the cutoff. A masked target contributes exactly zero gradient.
`backend/tests/test_learner_v2_pit.py` asserts the mask, not the intention.

THE TWO FORMS, PRESERVED FROM v1
================================
    raw       target_h = excess_h            trunk sees X + [prior_1m]
    residual  target_h = excess_h - prior_h  trunk sees X only;
              prediction_h = prior_h + f_h(X)

Only `prior_1m` is added in the raw form, not all four prior columns: the band
prior at horizon h is `(1 + a) ** (h/12) - 1` of the same annualised constant,
so `prior_3m`, `prior_6m` and `prior_12m` are strictly monotone functions of
`prior_1m` and carry no information the trunk cannot recover. Four copies of
one number would just be four chances to overfit it.

In the residual form the trunk NEVER sees the prior, which means the classifier
head in that form is predicting P(excess > 0) without the engine's belief. That
is a real handicap and it is stated here rather than repaired quietly, because
"a probability has no residual" (v1, models.py) is still true: `prior - P` is
not a quantity.

HYPERPARAMETERS ARE CHOSEN ONCE, ON THE EARLIEST INNER HOLDOUT
==============================================================
A three-point grid is searched on the inner temporal holdout (the last 12
months of the training window) of the FIRST test year only, then frozen for
every later year. That choice therefore uses only rows that had matured before
the first test year -- it is PIT-clean -- and it costs one grid instead of
nine. Re-searching every year would be defensible too and about three times
the compute; which was done is recorded in the receipt so no reader has to
guess.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

try:  # pragma: no cover - environment dependent
    import torch
    import torch.nn as nn
    _TORCH = True
except Exception:  # pragma: no cover
    _TORCH = False

SEED = 20260903
INNER_HOLDOUT_MONTHS = 12
WINSOR = (0.01, 0.99)
HORIZONS: tuple[int, ...] = (1, 3, 6, 12)

#: The grid, searched once on the earliest inner holdout.
GRID: tuple[dict, ...] = (
    {"hidden": (64, 32), "dropout": 0.1, "lr": 1e-3, "weight_decay": 1e-4},
    {"hidden": (128, 64), "dropout": 0.2, "lr": 1e-3, "weight_decay": 1e-4},
    {"hidden": (64, 32), "dropout": 0.1, "lr": 3e-4, "weight_decay": 1e-3},
)
MAX_EPOCHS = 40
PATIENCE = 5
BATCH = 4096
CLF_LOSS_WEIGHT = 1.0

ARMS = ("raw", "residual")


#: Standardised features are clipped to this many sd before they reach the net.
CLIP_SD = 5.0


def torch_available() -> bool:
    return _TORCH


class ClipSD(BaseEstimator, TransformerMixin):
    """Clip standardised features at +/- CLIP_SD. NOT cosmetic -- it is load-bearing.

    `ratio = target / close` is unbounded and the panel contains name-months
    with a ratio in the hundreds (S30b's +400% band has a MEDIAN of 44x). After
    StandardScaler those rows sit at z-scores of several hundred, a GELU MLP
    maps them to enormous activations, and the first version of this encoder
    returned regression heads with a standard deviation of **15.3** -- i.e. a
    predicted excess return of 1,533% -- and an inner validation loss of
    53,467. Rank IC hides that (a rank is immune to how far the outlier is);
    a top-50 book does not, because those exact rows sort to the top.

    Clipping is applied AFTER the scaler and is fitted on nothing, so it cannot
    leak. The clipped rows keep their ORDER at the boundary (they all land on
    it), which is exactly the information a bounded model should keep about a
    number it cannot represent.

    This is the one preprocessing difference from v1's MLP, which had no clip.
    It is stated here and in the receipt rather than buried, because it means
    `encoder vs v1 MLP` is not purely an architecture comparison.
    """

    def __init__(self, clip: float = CLIP_SD):
        self.clip = clip

    def fit(self, X, y=None):
        # A trailing-underscore attribute is what makes sklearn consider the
        # step -- and therefore the whole Pipeline -- fitted. Without it
        # `Pipeline.transform` raises NotFittedError after a successful
        # `fit_transform`, which is a confusing way to learn this.
        self.n_features_in_ = int(np.asarray(X).shape[1])
        return self

    def transform(self, X):
        return np.clip(np.asarray(X, dtype="float64"), -self.clip, self.clip)


# ------------------------------------------------------- PIT split machinery

def multi_horizon_splits(df: pd.DataFrame, test_years, horizons=HORIZONS,
                         benchmark: str = "vw", min_train_months: int = 24):
    """Expanding-window splits for a model with SEVERAL targets per row.

    Yields ``(year, train_index, test_index, masks)`` where ``masks[h]`` is a
    boolean array over ``train_index`` that is True only where horizon ``h``'s
    target had ALREADY MATURED before 1 Jan of the test year and is finite.

    The train set is the union over horizons; the masks are the intersection
    per horizon. A row dated Nov-2015 is therefore a legitimate 1m and 3m
    training example for test-year 2016 and is NOT a 12m one, and the same row
    carries both facts at once. Admitting it wholesale is the leak this
    function exists to prevent.

    Test rows are every row entered inside the test year -- no target filter,
    because the four horizons mature at four different times and the grader
    applies each horizon's own `notna` when it grades.
    """
    for y in test_years:
        cutoff = pd.Timestamp(f"{y}-01-01")
        nxt = pd.Timestamp(f"{y + 1}-01-01")
        matured = {}
        for h in horizons:
            ycol = f"excess_{benchmark}_{h}m"
            matured[h] = (df[f"mat_date_{h}m"].notna()
                          & (df[f"mat_date_{h}m"] < cutoff)
                          & df[ycol].notna()).to_numpy()
        any_matured = np.zeros(len(df), bool)
        for h in horizons:
            any_matured |= matured[h]
        tr = df.index[any_matured]
        te = df.index[(df["entry_date"] >= cutoff) & (df["entry_date"] < nxt)]
        if len(tr) == 0 or len(te) == 0:
            continue
        if df.loc[tr, "month"].nunique() < min_train_months:
            continue
        pos = np.flatnonzero(any_matured)
        masks = {h: matured[h][pos] for h in horizons}
        yield y, tr, te, masks


def _inner_split(months: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    """Last INNER_HOLDOUT_MONTHS months -> validation. Temporal, never random."""
    uniq = sorted(months.unique())
    if len(uniq) <= INNER_HOLDOUT_MONTHS + 6:
        cut = uniq[max(1, int(len(uniq) * 0.8))]
    else:
        cut = uniq[-INNER_HOLDOUT_MONTHS]
    fit = (months < cut).to_numpy()
    val = (months >= cut).to_numpy()
    if val.sum() == 0 or fit.sum() == 0:
        return np.ones(len(months), bool), np.zeros(len(months), bool)
    return fit, val


# ------------------------------------------------------------------ targets

def arm_feature_cols(feature_cols: list[str], arm: str) -> list[str]:
    """`raw` sees the prior as ONE column; `residual` never sees it at all."""
    if arm == "raw":
        return list(feature_cols) + ["prior_1m"]
    if arm == "residual":
        return list(feature_cols)
    raise ValueError(f"unknown arm {arm!r}")


def arm_target_col(arm: str, horizon: int, benchmark: str = "vw") -> str:
    return (f"excess_{benchmark}_{horizon}m" if arm == "raw"
            else f"resid_{benchmark}_{horizon}m")


def reconstruct(pred_arm: np.ndarray, df: pd.DataFrame, arm: str, horizon: int) -> np.ndarray:
    """Both forms back onto ONE scale: predicted excess return."""
    p = np.asarray(pred_arm, dtype="float64")
    if arm == "raw":
        return p
    return p + df[f"prior_{horizon}m"].to_numpy(dtype="float64")


# -------------------------------------------------------------- the network

def _build(n_in: int, cfg: dict, horizons):  # pragma: no cover - needs torch
    h1, h2 = cfg["hidden"]
    trunk = nn.Sequential(
        nn.Linear(n_in, h1), nn.GELU(), nn.Dropout(cfg["dropout"]),
        nn.Linear(h1, h2), nn.GELU(),
    )
    heads_reg = nn.ModuleDict({str(h): nn.Sequential(
        nn.Linear(h2, 16), nn.GELU(), nn.Linear(16, 1)) for h in horizons})
    heads_clf = nn.ModuleDict({str(h): nn.Sequential(
        nn.Linear(h2, 16), nn.GELU(), nn.Linear(16, 1)) for h in horizons})
    return nn.ModuleDict({"trunk": trunk, "reg": heads_reg, "clf": heads_clf})


def _forward(net, x, horizons):  # pragma: no cover - needs torch
    z = net["trunk"](x)
    return ({h: net["reg"][str(h)](z).squeeze(-1) for h in horizons},
            {h: net["clf"][str(h)](z).squeeze(-1) for h in horizons})


def _winsorise(y: np.ndarray, m: np.ndarray) -> tuple[np.ndarray, tuple[float, float]]:
    """Winsorise the TRAINING target at the train 1st/99th percentile.

    The evaluation target is never winsorised anywhere in this package -- the
    tail is the result, not an outlier.
    """
    if m.sum() == 0:
        return y, (float("nan"), float("nan"))
    lo, hi = np.nanquantile(y[m], WINSOR[0]), np.nanquantile(y[m], WINSOR[1])
    out = y.copy()
    out[m] = np.clip(y[m], lo, hi)
    return out, (float(lo), float(hi))


def _train_one(Zf, Yf, Mf, Bf, Zv, Yv, Mv, Bv, cfg, horizons, seed,
               max_epochs=MAX_EPOCHS):  # pragma: no cover - needs torch
    """One fit. Y is STANDARDISED per horizon; M masks; B are the 0/1 labels."""
    torch.manual_seed(seed)
    net = _build(Zf.shape[1], cfg, horizons)
    opt = torch.optim.AdamW(net.parameters(), lr=cfg["lr"],
                            weight_decay=cfg["weight_decay"])
    mse = nn.MSELoss(reduction="none")
    bce = nn.BCEWithLogitsLoss(reduction="none")

    tf = torch.tensor(Zf, dtype=torch.float32)
    ty = {h: torch.tensor(Yf[h], dtype=torch.float32) for h in horizons}
    tm = {h: torch.tensor(Mf[h].astype("float32")) for h in horizons}
    tb = {h: torch.tensor(Bf[h], dtype=torch.float32) for h in horizons}
    has_val = len(Zv) > 0
    if has_val:
        vf = torch.tensor(Zv, dtype=torch.float32)
        vy = {h: torch.tensor(Yv[h], dtype=torch.float32) for h in horizons}
        vm = {h: torch.tensor(Mv[h].astype("float32")) for h in horizons}
        vb = {h: torch.tensor(Bv[h], dtype=torch.float32) for h in horizons}

    def total(pred_r, pred_c, yy, mm, bb):
        loss = 0.0
        for h in horizons:
            w = mm[h]
            den = w.sum().clamp(min=1.0)
            loss = loss + (mse(pred_r[h], yy[h]) * w).sum() / den
            loss = loss + CLF_LOSS_WEIGHT * (bce(pred_c[h], bb[h]) * w).sum() / den
        return loss

    n = len(tf)
    g = torch.Generator().manual_seed(seed)
    best, best_state, bad, epochs_run = np.inf, None, 0, 0
    for _epoch in range(max_epochs):
        epochs_run += 1
        net.train(True)
        perm = torch.randperm(n, generator=g)
        for i in range(0, n, BATCH):
            idx = perm[i:i + BATCH]
            opt.zero_grad()
            pr, pc = _forward(net, tf[idx], horizons)
            total(pr, pc, {h: ty[h][idx] for h in horizons},
                  {h: tm[h][idx] for h in horizons},
                  {h: tb[h][idx] for h in horizons}).backward()
            opt.step()
        if not has_val:
            continue
        net.train(False)
        with torch.no_grad():
            pr, pc = _forward(net, vf, horizons)
            v = float(total(pr, pc, vy, vm, vb))
        if v < best - 1e-6:
            best, bad = v, 0
            best_state = {k: p.detach().clone() for k, p in net.state_dict().items()}
        else:
            bad += 1
            if bad >= PATIENCE:
                break
    if best_state is not None:
        net.load_state_dict(best_state)
    net.train(False)
    return net, {"inner_val_loss": (None if not np.isfinite(best) else round(best, 6)),
                 "epochs_run": epochs_run}


class MultiHorizonEncoder:
    """Fit once per (arm, test year); predict all four horizons, both heads.

    `predict(df)` returns ``{("reg", h): excess, ("clf", h): probability}``,
    every regression output already reconstructed onto the excess scale.
    """

    def __init__(self, arm: str, feature_cols: list[str], horizons=HORIZONS,
                 benchmark: str = "vw", cfg: dict | None = None, seed: int = SEED):
        if not _TORCH:
            raise RuntimeError("torch is not available; the v2 encoder REFUSES to "
                               "silently fall back to a different architecture")
        self.arm = arm
        self.horizons = tuple(horizons)
        self.benchmark = benchmark
        self.cols = arm_feature_cols(feature_cols, arm)
        self.cfg = dict(cfg or GRID[0])
        self.seed = seed
        self.pre: Pipeline | None = None
        self.net = None
        self.scale: dict[int, tuple[float, float]] = {}
        self.meta: dict = {}

    # -- internals -------------------------------------------------------
    def _prepare(self, train: pd.DataFrame, masks: dict, shuffle_target: bool = False):
        X = train[self.cols].to_numpy(dtype="float64")
        Y, M, B, bounds = {}, {}, {}, {}
        month = train["month"].to_numpy()
        rng = np.random.default_rng(self.seed)      # never np.random.seed
        for h in self.horizons:
            m = np.asarray(masks[h], bool)
            y = train[arm_target_col(self.arm, h, self.benchmark)].to_numpy(dtype="float64")
            b = train[f"pos_{self.benchmark}_{h}m"].to_numpy(dtype="float64")
            m = m & np.isfinite(y) & np.isfinite(b)
            if shuffle_target:
                y, b = _shuffle_within_month(y, b, m, month, rng)
            y, bnd = _winsorise(np.nan_to_num(y, nan=0.0), m)
            Y[h], M[h], B[h], bounds[h] = y, m, np.nan_to_num(b, nan=0.0), bnd
        return X, Y, M, B, bounds

    def _standardise(self, Y, M, fit_rows):
        out = {}
        for h in self.horizons:
            sel = M[h] & fit_rows
            mu = float(Y[h][sel].mean()) if sel.sum() else 0.0
            sd = float(Y[h][sel].std()) if sel.sum() else 1.0
            sd = sd if sd > 1e-12 else 1.0
            self.scale[h] = (mu, sd)
            out[h] = (Y[h] - mu) / sd
        return out

    # -- public ----------------------------------------------------------
    def fit(self, train: pd.DataFrame, masks: dict, search_grid: bool = False,
            max_epochs: int = MAX_EPOCHS, shuffle_target: bool = False):
        X, Y, M, B, bounds = self._prepare(train, masks, shuffle_target=shuffle_target)
        fit_rows, val_rows = _inner_split(train["month"])
        self.pre = Pipeline([("impute", SimpleImputer(strategy="median")),
                             ("scale", StandardScaler()),
                             ("clip", ClipSD())])                # never fillna(0)
        Zf = self.pre.fit_transform(X[fit_rows])
        Zv = self.pre.transform(X[val_rows]) if val_rows.sum() else X[:0]
        Ys = self._standardise(Y, M, fit_rows)

        def slice_(d, rows):
            return {h: d[h][rows] for h in self.horizons}

        candidates = GRID if search_grid else (self.cfg,)
        best_cfg, best_net, best_meta, best_loss = None, None, None, np.inf
        searched = []
        for cfg in candidates:
            net, meta = _train_one(
                Zf, slice_(Ys, fit_rows), slice_(M, fit_rows), slice_(B, fit_rows),
                Zv, slice_(Ys, val_rows), slice_(M, val_rows), slice_(B, val_rows),
                cfg, self.horizons, self.seed, max_epochs=max_epochs)
            loss = meta.get("inner_val_loss")
            searched.append({"cfg": {k: (list(v) if isinstance(v, tuple) else v)
                                     for k, v in cfg.items()},
                             "inner_val_loss": loss})
            if loss is not None and loss < best_loss:
                best_cfg, best_net, best_meta, best_loss = cfg, net, meta, loss
            elif best_net is None:
                best_cfg, best_net, best_meta = cfg, net, meta
        self.cfg, self.net = dict(best_cfg), best_net
        self.meta = {
            "arm": self.arm,
            "n_train": int(len(train)),
            "n_train_months": int(train["month"].nunique()),
            "n_features": len(self.cols),
            "rows_per_horizon": {str(h): int(M[h].sum()) for h in self.horizons},
            "winsor_bounds": {str(h): bounds[h] for h in self.horizons},
            "target_scale": {str(h): self.scale[h] for h in self.horizons},
            "cfg": {k: (list(v) if isinstance(v, tuple) else v) for k, v in self.cfg.items()},
            "grid_searched": searched if search_grid else None,
            "shuffled_null": bool(shuffle_target),
            **best_meta,
        }
        return self

    def predict(self, df: pd.DataFrame) -> dict:
        assert self.net is not None and self.pre is not None, "fit() first"
        Z = self.pre.transform(df[self.cols].to_numpy(dtype="float64"))
        with torch.no_grad():
            pr, pc = _forward(self.net, torch.tensor(Z, dtype=torch.float32), self.horizons)
        out: dict = {}
        for h in self.horizons:
            mu, sd = self.scale[h]
            reg = pr[h].numpy().astype("float64") * sd + mu
            out[("reg", h)] = reconstruct(reg, df, self.arm, h)
            out[("clf", h)] = torch.sigmoid(pc[h]).numpy().astype("float64")
        return out


def _shuffle_within_month(y: np.ndarray, b: np.ndarray, m: np.ndarray,
                          month: np.ndarray, rng) -> tuple[np.ndarray, np.ndarray]:
    """Permute the training target WITHIN each month, jointly for y and its label.

    S24's lesson: a shuffled-DATE null is a test of the calendar, not of the
    plumbing. The permutation must live inside the date block, and the return
    and its sign must move TOGETHER or the two heads would be trained against
    each other's nulls.
    """
    ys, bs = y.copy(), b.copy()
    order = np.argsort(month, kind="stable")
    mo = month[order]
    starts = np.flatnonzero(np.r_[True, mo[1:] != mo[:-1]])
    ends = np.r_[starts[1:], len(mo)]
    for s, e in zip(starts, ends):
        idx = order[s:e]
        idx = idx[m[idx]]
        if len(idx) < 2:
            continue
        perm = rng.permutation(len(idx))
        ys[idx] = y[idx][perm]
        bs[idx] = b[idx][perm]
    return ys, bs


def describe() -> dict:
    return {
        "architecture": "shared trunk -> per-horizon (regression, classifier) heads",
        "horizons": list(HORIZONS),
        "heads_per_horizon": ["reg: expected EXCESS return", "clf: P(excess > 0)"],
        "arms": list(ARMS),
        "arm_semantics": {
            "raw": "targets = excess_h; trunk sees X + [prior_1m] (ONE prior column: "
                   "prior_h is a monotone function of prior_1m)",
            "residual": "targets = excess_h - prior_h; trunk sees X only; "
                        "prediction = prior_h + f_h(X). The clf head in this form "
                        "never sees the prior -- a stated handicap, not an oversight.",
        },
        "pit_rule": ("a row is admitted to training if ANY horizon has matured before the "
                     "test year; EVERY horizon's target is then masked out unless that "
                     "horizon's own mat_date is strictly before the cutoff. A masked "
                     "target contributes zero gradient."),
        "loss": ("sum over horizons of masked MSE on the per-horizon STANDARDISED target "
                 f"+ {CLF_LOSS_WEIGHT} x masked BCEWithLogits. Standardising per horizon "
                 "stops the 12m head (sd ~4x the 1m head) from owning the gradient."),
        "hyperparameter_selection": (
            "a 3-point grid searched on the inner temporal holdout (last "
            f"{INNER_HOLDOUT_MONTHS} months of train) of the FIRST test year only, then "
            "frozen. That choice uses only rows matured before the first test year, so it "
            "is PIT-clean, and costs one grid rather than nine."),
        "grid": [{k: (list(v) if isinstance(v, tuple) else v) for k, v in c.items()}
                 for c in GRID],
        "max_epochs": MAX_EPOCHS, "early_stopping_patience": PATIENCE, "batch": BATCH,
        "winsorisation": {"train_target_quantiles": list(WINSOR),
                          "evaluation_target": "NEVER winsorised"},
        "missing_policy": "median impute + standardise INSIDE the pipeline, fitted on the "
                          "inner-fit rows only. fillna(0) is banned.",
        "feature_clip_sd": CLIP_SD,
        "feature_clip_note": (
            "standardised features are clipped at +/-5 sd. WITHOUT it the regression heads "
            "returned an sd of 15.3 in excess-return units (a predicted +1,533%) and an "
            "inner val loss of 53,467, because `ratio` is unbounded and the panel holds "
            "name-months with a ratio in the hundreds. This is the ONE preprocessing "
            "difference from v1's MLP, so `encoder vs v1 MLP` is architecture PLUS clip."),
        "features": "byte-identical to v1's 49 columns (+ prior_1m in the raw arm). The "
                    "architecture is the only thing that changed.",
        "seed": SEED,
        "torch_available": _TORCH,
    }


__all__ = ["HORIZONS", "ARMS", "GRID", "SEED", "MultiHorizonEncoder",
           "multi_horizon_splits", "arm_feature_cols", "arm_target_col",
           "reconstruct", "torch_available", "describe"]
