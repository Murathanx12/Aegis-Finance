"""UNSUPERVISED MARKET STATES -- what world are we in, learned without the answer.

WHAT THIS IS
============
Every learner in `learner/models.py` is a SUPERVISED map from features to a
forward excess return. This file is the other half: it learns a *representation*
of the cross-section using **no future information at all**, labels each
(permno, vintage) with a discovered state, and only THEN asks the graded
question -- does model reliability depend on the state?

That ordering is the whole point and it is enforced structurally:

    FITTING SIDE  (this module's `fit_block` / `assign_block`)
        sees:     the PIT feature columns of `learner/dataset.py`
        never sees: fwd_*, excess_*, resid_*, prior_*, mat_date_*
        -- `assert_no_target_columns` refuses a frame that carries them into
           the fit, so "I was careful" is replaced by "it cannot".

    GRADING SIDE  (`conditional_table`, `state_ic_table`, `shuffled_null`)
        MAY see matured future returns. That is what grading is.

If the representation could see the target, "states condition model
reliability" would be a tautology dressed as a discovery.

THE OOS PROTOCOL, AND WHY IT IS BLOCKED RATHER THAN MONTHLY
===========================================================
For month M the representation must be fitted on data strictly before M. A
literal per-month refit of scaler+PCA+KMeans+GMM+IsolationForest over 144
months x 5 values of k is ~700 fits for a representation that moves at the
speed of the business cycle. So the fit is BLOCKED: every `refit_every_months`
the representation is refitted on everything strictly before the block's first
day, and every month inside the block is assigned by that fit.

That is *more* conservative than a monthly refit, never less: a month in the
middle of a block is scored by a representation that saw even less of the
recent past than a monthly refit would have allowed. `assert_block_ordering`
prints, per block, the last training `entry_date` and the first assigned
`entry_date`, and refuses if they ever cross.

STATE IDENTITY IS NOT KMEANS' LABEL
===================================
KMeans label 3 in the 2019 block and label 3 in the 2020 block are unrelated
integers. Reading a transition matrix built on raw labels would be reading
relabelling noise as regime change. Every block's centroids are therefore
projected back into a FIXED reference space (block 0's scaler) and matched to
the previous block's centroids by Hungarian assignment; the matched permutation
is applied before anything is stored. The drift statistic reports how far a
matched centroid moved relative to the typical distance BETWEEN centroids --
which is the honest way to say whether a state is the same state.

THE LADDER, IN ORDER
====================
    RobustScaler (train median/IQR)  ->  clip +-5 sd  ->  PCA
      ->  KMeans          the primary state label
      ->  GaussianMixture a second opinion; ARI(KMeans, GMM) is a stability read
      ->  IsolationForest an anomaly score, orthogonal to the cluster label
      ->  NearestNeighbours per company-vintage: the k closest historical
          analogues, their ids, their distances, and the mean excess return
          THEY went on to realise -- a retrieval predictor that is PIT because
          the reference pool is restricted to rows whose own target had already
          matured before the assigned month began.

An autoencoder embedder is available (`embedder="ae"`, torch CPU) and is kept
only if it beats PCA on the same graded tables. It is not the default.

k IS CHOSEN WITHOUT THE TARGET
==============================
Silhouette on a train-only subsample of the FIRST block. Choosing k by which
value made the downstream return table look best would be fitting the answer
through the back door; the ladder's other k values are still assigned and
stored so a reader can see the choice was not load-bearing.

THE NULL
========
A partition of anything into five parts produces five different-looking mean
returns. `shuffled_null` permutes the state labels WITHIN each month --
preserving the month, the per-month state sizes and therefore the calendar --
and recomputes the same spread statistic. The observed spread is reported as a
percentile of that null. A state structure that does not clear its own shuffle
has discovered nothing, and the receipt says so in those words.

S36 amendment: that shuffle re-randomises every draw, so it cannot represent
a PERSISTENT random partition -- and the real assignments are persistent by
construction. `persistent_shuffled_null` is the honest bar: it circularly
shifts each name's own state sequence in time, so every draw keeps the
observed partition's persistence and only the alignment with returns is
destroyed. `shuffled_null` stays for leak-checking and for comparability
with sealed receipts, stamped LEGACY in its own output.
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from learner import nullbar as NB                                     # noqa: E402
from sklearn.cluster import KMeans                                    # noqa: E402
from sklearn.ensemble import IsolationForest                          # noqa: E402
from sklearn.decomposition import PCA                                 # noqa: E402
from sklearn.impute import SimpleImputer                              # noqa: E402
from sklearn.mixture import GaussianMixture                           # noqa: E402
from sklearn.neighbors import NearestNeighbors                        # noqa: E402
from sklearn.preprocessing import RobustScaler                        # noqa: E402
from scipy.optimize import linear_sum_assignment                      # noqa: E402

STATES_DIR = REPO / "backend" / "data" / "optimus" / "learner" / "states"

SCHEMA_VERSION = "learner-unsupervised-states-1"
SEED = 20260903

# ------------------------------------------------------------ the feature set

#: The representation's inputs. Every one is a PIT feature of
#: `learner/dataset.py`; NOT ONE is a target, a prior, or a maturity date.
#: Levels rather than within-month percentiles on purpose: a percentile is
#: normalised against its own month and would erase exactly the market-level
#: variation a "what world are we in" question is asking about.
STATE_FEATURES: tuple[str, ...] = (
    "log_ratio", "consensus", "log_coverage", "disagreement", "dispersion",
    "net_rev_4w", "target_rev_1m", "consensus_rev_1m",
    "ret_1m", "ret_3m", "ret_12m", "mom_12_1", "drawdown_60d",
    "vol_20d", "vol_60d",
    "log_dollar_vol_20d", "log_market_cap", "log_close",
)

#: Any column matching one of these prefixes is FUTURE INFORMATION and is
#: refused on the fitting side. `prior_` is included even though the band
#: constants are not a realised return: they were fitted on the full window,
#: so letting them shape the representation would import the test years.
TARGET_PREFIXES: tuple[str, ...] = (
    "fwd_", "excess_", "resid_", "mkt_", "prior_", "mat_date_", "pos_",
    "delisting_filled_",
)

#: Market-level monthly features, all derived from TRAILING cross-sectional
#: quantities. `mkt_vw_1m` and friends are FORWARD market returns in the train
#: table and are deliberately absent.
MARKET_FEATURES: tuple[str, ...] = (
    "xs_disp_ret_1m", "xs_disp_ret_12m",
    "breadth_pos_1m", "breadth_pos_12m",
    "med_ret_1m", "med_ret_12m",
    "med_vol_20d", "p90_vol_20d",
    "med_drawdown_60d",
    "med_ratio", "share_toxic_ge_5", "share_b_3_5",
    "med_disagreement", "med_net_rev_4w",
    "log_n_names",
)

K_LADDER: tuple[int, ...] = (3, 4, 5, 6, 8)
MARKET_K_LADDER: tuple[int, ...] = (2, 3, 4)

REFIT_EVERY_MONTHS = 6
MIN_TRAIN_MONTHS = 24
N_PCA = 8
N_NEIGHBOURS = 3
NN_POOL_CAP = 60_000
GMM_FIT_CAP = 80_000
SILHOUETTE_SAMPLE = 20_000
CLIP_SD = 5.0

#: A state is STABLE if, after Hungarian matching, its centroid never moves
#: further between consecutive refits than this fraction of the typical
#: distance between two different centroids -- and it never shrinks below
#: `MIN_STATE_SHARE` of a block.
MAX_DRIFT_RATIO = 0.5
MIN_STATE_SHARE = 0.02


def schema() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "state_features": list(STATE_FEATURES),
        "market_features": list(MARKET_FEATURES),
        "k_ladder": list(K_LADDER),
        "market_k_ladder": list(MARKET_K_LADDER),
        "refit_every_months": REFIT_EVERY_MONTHS,
        "min_train_months": MIN_TRAIN_MONTHS,
        "n_pca": N_PCA,
        "n_neighbours": N_NEIGHBOURS,
        "clip_sd": CLIP_SD,
        "seed": SEED,
        "target_prefixes_refused_on_the_fitting_side": list(TARGET_PREFIXES),
        "k_selection": "silhouette on a train-only subsample of the FIRST block; never the target",
        "missing_policy": "median imputation fitted on TRAIN only (SimpleImputer). fillna(0) is banned.",
    }


def schema_hash() -> str:
    return hashlib.sha256(json.dumps(schema(), sort_keys=True).encode()).hexdigest()[:16]


# ---------------------------------------------------------------- the guards

def assert_no_target_columns(cols: Iterable[str]) -> None:
    """REFUSE a fitting matrix that carries future information.

    This is the structural version of the promise in the module docstring. It
    is called by `fit_block` on the actual column list handed to the scaler,
    not on an intention stated in a comment.
    """
    bad = [c for c in cols if any(str(c).startswith(p) for p in TARGET_PREFIXES)]
    if bad:
        raise ValueError(
            "REFUSED: the representation was handed future information: "
            f"{sorted(bad)[:8]}. The fitting side sees PIT features only.")


def assert_block_ordering(blocks: Sequence["Block"]) -> dict:
    """REFUSE if any block's training data reaches into its assigned months.

    Returns the receipt row rather than a bare True, because a guard that
    prints nothing teaches a reader to stop looking at it.
    """
    rows = []
    for b in blocks:
        if b.train_last_date is not None and b.assign_first_date is not None:
            if not (b.train_last_date < b.assign_first_date):
                raise ValueError(
                    f"REFUSED: block {b.block_id} trained through "
                    f"{b.train_last_date} but assigns from {b.assign_first_date}.")
        rows.append({
            "block_id": b.block_id,
            "train_months": b.n_train_months,
            "train_rows": b.n_train_rows,
            "train_last_entry_date": str(b.train_last_date),
            "assign_first_entry_date": str(b.assign_first_date),
            "assign_months": b.assign_months,
            "assign_rows": b.n_assign_rows,
        })
    return {"rule": "every block's last training entry_date is STRICTLY before its "
                    "first assigned entry_date", "blocks": rows}


# ------------------------------------------------------------------ the block

@dataclass
class Block:
    """One refit of the representation, plus the months it labels."""
    block_id: int
    train_last_date: pd.Timestamp | None = None
    assign_first_date: pd.Timestamp | None = None
    assign_months: list = field(default_factory=list)
    n_train_rows: int = 0
    n_train_months: int = 0
    n_assign_rows: int = 0
    fitted: dict = field(default_factory=dict)


def month_blocks(months: Sequence[str], refit_every: int = REFIT_EVERY_MONTHS,
                 min_train_months: int = MIN_TRAIN_MONTHS) -> list:
    """Partition the assignable months into refit blocks.

    The first `min_train_months` months are burn-in: they are training data and
    are never assigned a state. Not-yet-learnable is not a state.
    """
    ms = sorted(set(months))
    tail = ms[min_train_months:]
    return [tail[i:i + refit_every] for i in range(0, len(tail), refit_every)]


# ------------------------------------------------------------- the embedders

class _PCAEmbedder:
    """RobustScaler -> clip -> PCA. The baseline, and the thing the AE must beat."""

    kind = "pca"

    def __init__(self, n_components: int = N_PCA, seed: int = SEED):
        self.n_components = n_components
        self.seed = seed

    def fit(self, X: np.ndarray):
        self.imputer_ = SimpleImputer(strategy="median").fit(X)
        Xi = self.imputer_.transform(X)
        self.scaler_ = RobustScaler().fit(Xi)
        Xs = np.clip(self.scaler_.transform(Xi), -CLIP_SD, CLIP_SD)
        self.pca_ = PCA(n_components=min(self.n_components, Xs.shape[1]),
                        random_state=self.seed).fit(Xs)
        self.explained_ = self.pca_.explained_variance_ratio_.tolist()
        return self

    def scaled(self, X: np.ndarray) -> np.ndarray:
        return np.clip(self.scaler_.transform(self.imputer_.transform(X)), -CLIP_SD, CLIP_SD)

    def transform(self, X: np.ndarray) -> np.ndarray:
        return self.pca_.transform(self.scaled(X))

    def to_scaled_space(self, Z: np.ndarray) -> np.ndarray:
        """Embedding coordinates -> scaled feature space (for centroid matching)."""
        return self.pca_.inverse_transform(np.asarray(Z, dtype="float64"))

    def describe(self) -> dict:
        return {"kind": self.kind, "n_components": int(self.pca_.n_components_),
                "explained_variance_ratio": [round(v, 5) for v in self.explained_],
                "cumulative_explained": round(float(np.sum(self.explained_)), 5)}


class _AEEmbedder:
    """A compact torch autoencoder over the same scaled matrix.

    Kept ONLY if it beats `_PCAEmbedder` on the graded tables. An autoencoder
    that merely reproduces PCA's partition at ten times the runtime is a
    slower PCA, and the receipt reports the comparison rather than the
    author's preference.
    """

    kind = "autoencoder"

    def __init__(self, n_components: int = N_PCA, seed: int = SEED,
                 epochs: int = 12, batch: int = 4096, hidden: int = 64):
        self.n_components = n_components
        self.seed = seed
        self.epochs = epochs
        self.batch = batch
        self.hidden = hidden

    def fit(self, X: np.ndarray):
        import torch
        from torch import nn

        torch.manual_seed(self.seed)
        self.imputer_ = SimpleImputer(strategy="median").fit(X)
        Xi = self.imputer_.transform(X)
        self.scaler_ = RobustScaler().fit(Xi)
        Xs = np.clip(self.scaler_.transform(Xi), -CLIP_SD, CLIP_SD).astype("float32")

        d = Xs.shape[1]
        k = min(self.n_components, d)
        self.enc_ = nn.Sequential(nn.Linear(d, self.hidden), nn.ReLU(),
                                  nn.Linear(self.hidden, k))
        self.dec_ = nn.Sequential(nn.Linear(k, self.hidden), nn.ReLU(),
                                  nn.Linear(self.hidden, d))
        params = list(self.enc_.parameters()) + list(self.dec_.parameters())
        opt = torch.optim.Adam(params, lr=1e-3)
        lossf = nn.MSELoss()
        T = torch.from_numpy(Xs)
        n = T.shape[0]
        rng = np.random.default_rng(self.seed)
        self.train_loss_ = []
        for _ in range(self.epochs):
            idx = rng.permutation(n)
            tot, nb = 0.0, 0
            for s in range(0, n, self.batch):
                b = T[idx[s:s + self.batch]]
                opt.zero_grad()
                out = self.dec_(self.enc_(b))
                loss = lossf(out, b)
                loss.backward()
                opt.step()
                tot += float(loss.item()); nb += 1
            self.train_loss_.append(round(tot / max(nb, 1), 6))
        self.enc_.train(False)
        self.dec_.train(False)
        self.k_ = k
        return self

    def scaled(self, X: np.ndarray) -> np.ndarray:
        return np.clip(self.scaler_.transform(self.imputer_.transform(X)), -CLIP_SD, CLIP_SD)

    def transform(self, X: np.ndarray) -> np.ndarray:
        import torch
        with torch.no_grad():
            return self.enc_(torch.from_numpy(self.scaled(X).astype("float32"))).numpy().astype("float64")

    def to_scaled_space(self, Z: np.ndarray) -> np.ndarray:
        import torch
        with torch.no_grad():
            return self.dec_(torch.from_numpy(np.asarray(Z, dtype="float32"))).numpy().astype("float64")

    def describe(self) -> dict:
        return {"kind": self.kind, "n_components": int(self.k_),
                "epochs": self.epochs, "hidden": self.hidden,
                "train_loss_by_epoch": self.train_loss_}


def make_embedder(kind: str, seed: int = SEED, n_components: int = N_PCA):
    if kind == "pca":
        return _PCAEmbedder(n_components=n_components, seed=seed)
    if kind in ("ae", "autoencoder"):
        return _AEEmbedder(n_components=n_components, seed=seed)
    raise ValueError(f"unknown embedder {kind!r}")


# ------------------------------------------------------------------- fitting

def fit_block(train: pd.DataFrame, ks: Sequence[int], seed: int = SEED,
              embedder: str = "pca", n_pca: int = N_PCA,
              nn_pool_cap: int = NN_POOL_CAP,
              nn_reference_cutoff=None) -> dict:
    """Fit the whole ladder on ONE training window. Sees no target column.

    `nn_reference_cutoff` restricts the retrieval pool to rows whose OWN 1m
    target had already matured before the block's first assigned day, so the
    neighbour's realised return is a fact that was on the table at assignment
    time rather than one that arrived later.
    """
    cols = list(STATE_FEATURES)
    assert_no_target_columns(cols)
    X = train[cols].to_numpy(dtype="float64")

    emb = make_embedder(embedder, seed=seed, n_components=n_pca).fit(X)
    Z = emb.transform(X)
    rng = np.random.default_rng(seed)

    out: dict = {"embedder": emb, "embed_meta": emb.describe(), "kmeans": {},
                 "gmm": {}, "n_train": int(len(train))}

    for k in ks:
        km = KMeans(n_clusters=k, n_init=5, random_state=seed).fit(Z)
        out["kmeans"][k] = km
        gsub = Z if len(Z) <= GMM_FIT_CAP else Z[rng.choice(len(Z), GMM_FIT_CAP, replace=False)]
        out["gmm"][k] = GaussianMixture(n_components=k, covariance_type="diag",
                                        random_state=seed, max_iter=100).fit(gsub)

    out["iforest"] = IsolationForest(n_estimators=200, max_samples=256,
                                     random_state=seed, n_jobs=4).fit(Z)

    # ---- retrieval pool: matured rows only, capped, seeded.
    pool = train
    if nn_reference_cutoff is not None and "mat_date_1m" in train.columns:
        pool = train[train["mat_date_1m"].notna()
                     & (train["mat_date_1m"] < nn_reference_cutoff)]
    if len(pool) > nn_pool_cap:
        pool = pool.iloc[np.sort(rng.choice(len(pool), nn_pool_cap, replace=False))]
    if len(pool) >= N_NEIGHBOURS + 1:
        Zp = emb.transform(pool[cols].to_numpy(dtype="float64"))
        out["nn"] = NearestNeighbors(n_neighbors=N_NEIGHBOURS).fit(Zp)
        out["nn_ids"] = pool[["permno", "month"]].reset_index(drop=True)
        out["nn_excess"] = (pool["excess_vw_1m"].to_numpy(dtype="float64")
                            if "excess_vw_1m" in pool.columns else None)
        out["nn_pool_rows"] = int(len(pool))
    else:
        out["nn"] = None
        out["nn_pool_rows"] = 0
    return out


def assign_block(fitted: dict, test: pd.DataFrame, ks: Sequence[int]) -> pd.DataFrame:
    """Label `test` out of sample with a representation it did not touch."""
    cols = list(STATE_FEATURES)
    X = test[cols].to_numpy(dtype="float64")
    emb = fitted["embedder"]
    Z = emb.transform(X)

    res = pd.DataFrame({"permno": test["permno"].to_numpy(),
                        "month": test["month"].to_numpy()})
    for j in range(min(4, Z.shape[1])):
        res[f"pc{j + 1}"] = Z[:, j]
    for k in ks:
        res[f"state_k{k}"] = fitted["kmeans"][k].predict(Z).astype("int16")
        res[f"gmm_k{k}"] = fitted["gmm"][k].predict(Z).astype("int16")
    # IsolationForest: score_samples is HIGHER for normal points, so negate --
    # `anomaly` is read as "how unusual", which is the direction the name says.
    res["anomaly"] = -fitted["iforest"].score_samples(Z)

    if fitted.get("nn") is not None:
        dist, idx = fitted["nn"].kneighbors(Z, n_neighbors=N_NEIGHBOURS)
        ids = fitted["nn_ids"]
        for j in range(N_NEIGHBOURS):
            res[f"nn{j + 1}_permno"] = ids["permno"].to_numpy()[idx[:, j]]
            res[f"nn{j + 1}_month"] = ids["month"].to_numpy()[idx[:, j]]
            res[f"nn{j + 1}_dist"] = dist[:, j]
        ex = fitted.get("nn_excess")
        if ex is not None:
            res["nn_excess_1m_mean"] = np.nanmean(ex[idx], axis=1)
    return res


# ---------------------------------------------------- stable state identities

def centroids_in_reference_space(fitted: dict, k: int, ref_embedder) -> np.ndarray:
    """Centroids expressed in a FIXED space so two blocks can be compared.

    A block's own scaled space drifts with its expanding training window, so
    centroids are pushed back to raw feature units and re-scaled by the
    reference (block 0) scaler. Without this, Hungarian matching would be
    matching two different rulers.
    """
    emb = fitted["embedder"]
    C = fitted["kmeans"][k].cluster_centers_
    scaled = emb.to_scaled_space(C)
    raw = emb.scaler_.inverse_transform(scaled)
    return ref_embedder.scaler_.transform(raw)


def stabilise_block_labels(fitted: dict, res: pd.DataFrame, ks: Sequence[int],
                           prev_ref: dict, ref_embedder) -> dict:
    """Rewrite this block's KMeans labels into STABLE ids, in place on `res`.

    This lives here rather than in the runner because the first version of it
    lived in the runner, and the test's own loop -- which did not have it --
    recovered a planted two-group structure and then FAILED its own null: the
    two blocks had named the same group 0 and 1, and averaging across blocks
    cancelled a 2%/month planted difference down to 0.36%. One implementation,
    two callers.

    `prev_ref` is mutated: `prev_ref[k]` becomes this block's centroids in
    stable-id order, ready to be the next block's reference.
    """
    drifts: dict = {}
    for k in ks:
        cur = centroids_in_reference_space(fitted, k, ref_embedder)
        if prev_ref.get(k) is None:
            perm = np.arange(k)
            drift, sep = float("nan"), float("nan")
        else:
            perm, drift, sep = match_states(prev_ref[k], cur)
        ordered = np.empty_like(cur)
        for cur_label, stable in enumerate(perm):
            ordered[stable] = cur[cur_label]
        prev_ref[k] = ordered
        col = f"state_k{k}"
        res[col] = perm[res[col].to_numpy()].astype("int16")
        entry = {
            "centroid_drift": (None if drift != drift else round(drift, 4)),
            "centroid_separation": (None if sep != sep else round(sep, 4)),
            "drift_over_separation": (None if (drift != drift or sep != sep or sep == 0)
                                      else round(drift / sep, 4)),
            "state_shares": {str(int(s)): round(float(v), 5) for s, v
                             in res[col].value_counts(normalize=True).sort_index().items()},
        }
        gcol = f"gmm_k{k}"
        if gcol in res.columns:
            from sklearn.metrics import adjusted_rand_score
            entry["kmeans_gmm_adjusted_rand"] = round(
                float(adjusted_rand_score(res[col], res[gcol])), 4)
        drifts[int(k)] = entry
    return drifts


def match_states(prev: np.ndarray, cur: np.ndarray):
    """Hungarian match `cur` centroids onto `prev`. Returns (perm, drift, sep).

    `perm[i]` is the STABLE id assigned to current label i. `drift` is the mean
    matched-pair distance; `sep` is the mean distance between two DIFFERENT
    previous centroids. drift/sep near 1 means the "same" state moved as far as
    the states are apart, i.e. the identity is fiction.
    """
    d = np.linalg.norm(prev[:, None, :] - cur[None, :, :], axis=2)
    r, c = linear_sum_assignment(d)
    perm = np.empty(cur.shape[0], dtype="int64")
    perm[c] = r
    drift = float(d[r, c].mean())
    if prev.shape[0] > 1:
        pdm = np.linalg.norm(prev[:, None, :] - prev[None, :, :], axis=2)
        sep = float(pdm[np.triu_indices(prev.shape[0], 1)].mean())
    else:
        sep = float("nan")
    return perm, drift, sep


# ---------------------------------------------------------- market-level state

def market_month_features(df: pd.DataFrame) -> pd.DataFrame:
    """One row per month of TRAILING cross-sectional aggregates.

    Nothing here is a forward return. `mkt_vw_1m` in the train table is the
    market's return over the NEXT month and is deliberately not touched: a
    "market state" built from next month's return would grade itself.
    """
    g = df.groupby("month")
    out = pd.DataFrame({
        "xs_disp_ret_1m": g["ret_1m"].std(),
        "xs_disp_ret_12m": g["ret_12m"].std(),
        "breadth_pos_1m": g["ret_1m"].apply(lambda s: float((s > 0).mean())),
        "breadth_pos_12m": g["ret_12m"].apply(lambda s: float((s > 0).mean())),
        "med_ret_1m": g["ret_1m"].median(),
        "med_ret_12m": g["ret_12m"].median(),
        "med_vol_20d": g["vol_20d"].median(),
        "p90_vol_20d": g["vol_20d"].quantile(0.9),
        "med_drawdown_60d": g["drawdown_60d"].median(),
        "med_ratio": g["ratio"].median(),
        "share_toxic_ge_5": g["band"].apply(lambda s: float((s == "toxic_ge_5").mean())),
        "share_b_3_5": g["band"].apply(lambda s: float((s == "b_3_5").mean())),
        "med_disagreement": g["disagreement"].median(),
        "med_net_rev_4w": g["net_rev_4w"].median(),
        "log_n_names": np.log(g.size()),
    })
    assert_no_target_columns(out.columns)
    return out.sort_index()


def run_market_states(mf: pd.DataFrame, k: int, seed: int = SEED,
                      min_train_months: int = MIN_TRAIN_MONTHS):
    """EXPANDING-WINDOW monthly market state. Fit on < M, assign M. Every month.

    Cheap enough (a 144 x 15 matrix) that there is no excuse for blocking it,
    so this one is the strict version: month M's state comes from a KMeans that
    saw only months strictly before M.
    """
    months = list(mf.index)
    rows = []
    prev_ref = None
    ref_scaler = None
    for i in range(min_train_months, len(months)):
        tr = mf.iloc[:i].to_numpy(dtype="float64")
        te = mf.iloc[i:i + 1].to_numpy(dtype="float64")
        imp = SimpleImputer(strategy="median").fit(tr)
        sc = RobustScaler().fit(imp.transform(tr))
        Xtr = np.clip(sc.transform(imp.transform(tr)), -CLIP_SD, CLIP_SD)
        Xte = np.clip(sc.transform(imp.transform(te)), -CLIP_SD, CLIP_SD)
        km = KMeans(n_clusters=k, n_init=5, random_state=seed).fit(Xtr)
        if ref_scaler is None:
            ref_scaler = sc
        cur_ref = ref_scaler.transform(sc.inverse_transform(km.cluster_centers_))
        if prev_ref is None:
            perm = np.arange(k)
            drift, sep = float("nan"), float("nan")
        else:
            perm, drift, sep = match_states(prev_ref, cur_ref)
        # re-order the current centroids into stable-id order for the next step
        ordered = np.empty_like(cur_ref)
        for cur_label, stable in enumerate(perm):
            ordered[stable] = cur_ref[cur_label]
        prev_ref = ordered
        lab = int(perm[int(km.predict(Xte)[0])])
        rows.append({"month": months[i], "market_state": lab,
                     "train_months": int(len(tr)),
                     "centroid_drift": drift, "centroid_sep": sep})
    out = pd.DataFrame(rows)
    drifts = [r["centroid_drift"] for r in rows if r["centroid_drift"] == r["centroid_drift"]]
    seps = [r["centroid_sep"] for r in rows if r["centroid_sep"] == r["centroid_sep"]]
    meta = {
        "k": k,
        "assigned_months": int(len(out)),
        "burn_in_months": int(min_train_months),
        "protocol": "expanding window, refit EVERY month on months strictly before M",
        "mean_centroid_drift": round(float(np.mean(drifts)), 4) if drifts else None,
        "mean_centroid_separation": round(float(np.mean(seps)), 4) if seps else None,
        "drift_over_separation": (round(float(np.mean(drifts) / np.mean(seps)), 4)
                                  if drifts and seps and np.mean(seps) else None),
        "state_month_counts": {str(kk): int(v) for kk, v
                               in out["market_state"].value_counts().sort_index().items()},
    }
    return out, meta


# ------------------------------------------------------------------- grading
# Everything BELOW this line may see matured future returns. Everything above
# it may not. The line is the contract.

def monthly_ic(df: pd.DataFrame, pred: str, target: str, min_names: int = 20,
               min_distinct: int = 2) -> dict:
    """Mean within-month Spearman IC, t over MONTHS (date blocks, never rows).

    `min_distinct` is 2, not 5, ON PURPOSE. BAND_PRIOR v2 emits at most FIVE
    distinct numbers in the whole panel and often two inside one state; a
    threshold of 5 silently returned `months: 0` for the incumbent, which reads
    as "no signal" and actually means "the ruler was never measured". A gate
    that cannot go green is a broken gate. `mean_distinct_predictions` is
    returned so a reader can see how coarse the ordering was -- an IC computed
    over two distinct values is a group difference, not a ranking, and is not
    comparable in magnitude to a continuous predictor's IC.
    """
    sub = df[[pred, target, "month"]].dropna()
    ics, distincts = [], []
    for _, g in sub.groupby("month"):
        nd = g[pred].nunique()
        if len(g) < min_names or nd < min_distinct:
            continue
        ics.append(float(g[pred].corr(g[target], method="spearman")))
        distincts.append(int(nd))
    keep = [i for i, v in enumerate(ics) if v == v]
    ics = [ics[i] for i in keep]
    distincts = [distincts[i] for i in keep]
    if len(ics) < 6:
        return {"months": len(ics), "note": "too few months to read"}
    a = np.asarray(ics)
    sd = a.std(ddof=1)
    t = float(a.mean() / (sd / np.sqrt(len(a)))) if sd > 0 else float("nan")
    return {"months": len(a), "mean_ic": round(float(a.mean()), 5),
            "median_ic": round(float(np.median(a)), 5), "t_stat": round(t, 3),
            "share_months_positive": round(float((a > 0).mean()), 4),
            "mean_distinct_predictions": round(float(np.mean(distincts)), 1)}


def _tstat_of_monthly_means(sub: pd.DataFrame, col: str):
    m = sub.groupby("month")[col].mean().dropna()
    if len(m) < 6:
        return float("nan"), len(m), float("nan")
    sd = float(m.std(ddof=1))
    t = float(m.mean() / (sd / np.sqrt(len(m)))) if sd > 0 else float("nan")
    return float(m.mean()), len(m), t


def conditional_table(df: pd.DataFrame, state_col: str,
                      targets: Sequence[str] = ("excess_vw_1m", "excess_vw_3m"),
                      upside_col: str = "fwd_3m", upside_threshold: float = 0.20) -> list:
    """Per state: the future the state was followed by. Grading, so targets allowed."""
    rows = []
    for s, g in df.groupby(state_col):
        row: dict = {"state": int(s), "rows": int(len(g)),
                     "share": round(float(len(g) / len(df)), 5),
                     "names": int(g["permno"].nunique()),
                     "months": int(g["month"].nunique())}
        for tcol in targets:
            v = g[tcol].dropna()
            if len(v) < 100:
                row[tcol] = {"n": int(len(v)), "note": "too few matured rows"}
                continue
            mean_m, n_m, t = _tstat_of_monthly_means(g, tcol)
            row[tcol] = {
                "n": int(len(v)),
                "mean": round(float(v.mean()), 5),
                "median": round(float(v.median()), 5),
                "monthly_mean_of_means": round(mean_m, 5),
                "months": int(n_m),
                "t_stat_months": round(t, 3),
                "p05": round(float(v.quantile(0.05)), 5),
                "p95": round(float(v.quantile(0.95)), 5),
                "tail_loss_mean_worst_5pct": round(float(v[v <= v.quantile(0.05)].mean()), 5),
                "share_negative": round(float((v < 0).mean()), 4),
            }
        up = g[upside_col].dropna() if upside_col in g.columns else pd.Series(dtype="float64")
        row[f"large_upside_freq__{upside_col}_gt_{upside_threshold}"] = (
            round(float((up > upside_threshold).mean()), 5) if len(up) >= 100 else None)
        rows.append(row)
    return sorted(rows, key=lambda r: r["state"])


def state_ic_table(df: pd.DataFrame, state_col: str, pred_cols: Sequence[str],
                   target: str = "excess_vw_1m") -> dict:
    """Per (model, state) rank IC. THE money question lives in this table.

    A model that is positive in one state and negative in another is a
    mixture-of-experts candidate; a model that is the same everywhere is one
    expert and the states buy it nothing.
    """
    out: dict = {}
    for p in pred_cols:
        if p not in df.columns:
            continue
        per_state = {}
        for s, g in df.groupby(state_col):
            per_state[str(int(s))] = monthly_ic(g, p, target)
        out[p] = {"overall": monthly_ic(df, p, target), "by_state": per_state}
    return out


def spread_statistic(df: pd.DataFrame, state_col: str, target: str) -> float:
    """The one number the null is run against: max-min of per-state mean target.

    Computed on monthly means so a state that only exists in three big months
    cannot win the spread on calendar luck alone.
    """
    per = df.groupby([state_col, "month"])[target].mean().groupby(level=0).mean()
    return float(per.max() - per.min()) if len(per) > 1 else float("nan")


def shuffled_null(df: pd.DataFrame, state_col: str, target: str,
                  n_shuffles: int = 200, seed: int = SEED) -> dict:
    """Permute state labels WITHIN each month and recompute the spread.

    Within-month is the right shuffle: it keeps the calendar, the per-month
    state sizes and the cross-sectional return distribution fixed, so the null
    answers "would a random partition of the SAME months look like this?"
    rather than "would a random partition of a different market?".
    (S24: a shuffled-date null that did not hold the day fixed measured the
    calendar and reported it as a signal.)

    KNOWN LIMIT (S36, stamped in the output): each draw RE-RANDOMISES the
    labels, so any tilt a draw picks up washes out across months -- while the
    real state assignment is PERSISTENT per name (that persistence is graded
    as a virtue by `transition_matrix`). A random-but-persistent partition
    could hold one tilt for the whole window and beat this null the same way
    a model fitted on noise beats a random ranking (learner/nullbar.py). The
    honest null is `persistent_shuffled_null` (built 2026-09-04): it shifts
    each name's own sequence in time, preserving the transition structure.
    This one stays for leak-checks and sealed-receipt comparability;
    `beats_random_partition` reads "beats a random NON-persistent partition"
    and no more.
    """
    rng = np.random.default_rng(seed)
    sub = df[[state_col, "month", target]].dropna(subset=[target]).reset_index(drop=True)
    obs = spread_statistic(sub, state_col, target)
    vals = sub[state_col].to_numpy().copy()
    pos = [g.index.to_numpy() for _, g in sub.groupby("month")]
    draws = []
    for _ in range(n_shuffles):
        shuffled = vals.copy()
        for p in pos:
            shuffled[p] = rng.permutation(vals[p])
        sub["_sh"] = shuffled
        draws.append(spread_statistic(sub, "_sh", target))
    a = np.asarray([d for d in draws if d == d])
    return {
        "statistic": "max-minus-min of per-state mean monthly excess",
        "target": target,
        "observed": round(obs, 6),
        "null_shuffles": int(len(a)),
        "null_mean": round(float(a.mean()), 6) if len(a) else None,
        "null_p95": round(float(np.quantile(a, 0.95)), 6) if len(a) else None,
        "null_max": round(float(a.max()), 6) if len(a) else None,
        "percentile_of_observed_in_null": round(float((a < obs).mean()), 4) if len(a) else None,
        "p_value_one_sided": round(float((a >= obs).mean()), 4) if len(a) else None,
        "beats_random_partition": bool(len(a) and (a >= obs).mean() < 0.05),
        # S36: each draw re-randomises, so this null cannot catch a PERSISTENT
        # random partition -- the same wash-out that let a model fitted on
        # noise beat every random ranking. Stamped so no reader trusts it as
        # more than "beats a random non-persistent partition".
        "null_bar": NB.LEGACY_SHUFFLED_RANKING,
    }


def circular_shift_labels(df: pd.DataFrame, state_col: str, rng) -> np.ndarray:
    """One persistent-null draw: each name's chronological state sequence,
    circularly shifted by a random non-zero offset. Aligned to df's row order.

    What one draw PRESERVES, exactly and per name: the state composition, the
    run-length structure and the cyclic transition multiset -- i.e. all the
    persistence the real assignment carries. What it DESTROYS: the alignment
    of those states with the calendar and therefore with returns. That is the
    null a persistent partition owes (see `persistent_shuffled_null`); the
    same construction the repo already trusts for treatment masks
    (`research_gym.null_invariance.circular_block_shift`, and N9's
    block-shifted transfer null).

    A name observed once (or with a constant state) shifts onto itself --
    deliberately: such a name contributes no persistence evidence, so its
    draw contributes no variance. Requires `permno` and `month` columns and
    REFUSES without them: a guard derives its inputs or refuses.
    """
    for c in ("permno", "month", state_col):
        if c not in df.columns:
            raise ValueError(f"circular_shift_labels: REFUSED -- column {c!r} is "
                             "missing; shifting needs the name and the clock")
    order = np.lexsort((df["month"].to_numpy(), df["permno"].to_numpy()))
    labels = df[state_col].to_numpy()[order].copy()
    pn = df["permno"].to_numpy()[order]
    starts = np.flatnonzero(np.r_[True, pn[1:] != pn[:-1]])
    ends = np.r_[starts[1:], len(pn)]
    for s, e in zip(starts, ends):
        n = e - s
        if n > 1:
            k = int(rng.integers(1, n))          # never the identity shift
            labels[s:e] = np.roll(labels[s:e], k)
    out = np.empty_like(labels)
    out[order] = labels
    return out


def persistent_shuffled_null(df: pd.DataFrame, state_col: str, target: str,
                             n_shuffles: int = 200, seed: int = SEED) -> dict:
    """The null `shuffled_null` cannot be: one that keeps the persistence.

    S36 (learner/nullbar.py): a null that re-randomises every draw lets its
    tilts wash out, so it cannot represent a PERSISTENT random partition --
    and the real state assignments are persistent by construction (the
    transition diagonal is graded as a virtue). This null shifts each name's
    own state sequence in time (`circular_shift_labels`), so every draw is a
    partition exactly as persistent as the observed one, with only the
    alignment to outcomes destroyed. The observed spread is then a percentile
    of draws that share its persistence, not of confetti.

    Two readings this construction gets RIGHT that the within-month shuffle
    got wrong:

    * a constant-per-name partition (every name keeps one state forever)
      shifts onto itself, every draw equals the observed, and the p-value is
      ~1 -- "a fixed random grouping of persistent name effects" is correctly
      not a discovery. The within-month shuffle CLEARS that partition
      whenever the target has persistent name effects, which is the S36
      false positive wearing state labels.
    * a partition whose states genuinely time a name's returns keeps its
      spread only when aligned, so shifting kills it and the observed clears.

    The verdict refuses below `nullbar.MIN_DRAWS` draws rather than quoting
    a p-value it cannot resolve. Statistic, keys and seed discipline mirror
    `shuffled_null` so receipts can carry both side by side; the invocation
    on a sealed study is one call per (k, grouping) with the SAME df/columns
    the LEGACY block used, e.g.

        S.persistent_shuffled_null(g, "state_k4", "excess_vw_1m",
                                   n_shuffles=200)
    """
    rng = np.random.default_rng(seed)
    sub = (df[["permno", state_col, "month", target]]
           .dropna(subset=[target]).reset_index(drop=True))
    obs = spread_statistic(sub, state_col, target)
    draws = []
    for _ in range(n_shuffles):
        sub["_sh"] = circular_shift_labels(sub, state_col, rng)
        draws.append(spread_statistic(sub, "_sh", target))
    a = np.asarray([d for d in draws if d == d])
    n_ok = int(len(a))
    if n_ok >= NB.MIN_DRAWS:
        beats: bool | str = bool((a >= obs).mean() < 0.05)
    else:
        beats = (f"{NB.CANNOT_DETERMINE} (usable draws {n_ok} < {NB.MIN_DRAWS}; "
                 "a p-value from fewer draws would be quoted as if it resolved "
                 "what it cannot)")
    return {
        "statistic": "max-minus-min of per-state mean monthly excess",
        "target": target,
        "observed": round(obs, 6),
        "null_shuffles": n_ok,
        "null_mean": round(float(a.mean()), 6) if n_ok else None,
        "null_p95": round(float(np.quantile(a, 0.95)), 6) if n_ok else None,
        "null_max": round(float(a.max()), 6) if n_ok else None,
        "percentile_of_observed_in_null": round(float((a < obs).mean()), 4) if n_ok else None,
        "p_value_one_sided": round(float((a >= obs).mean()), 4) if n_ok else None,
        "beats_persistent_relabelling": beats,
        "null_bar": ("PERSISTENCE_PRESERVING_CIRCULAR_SHIFT "
                     "(learner/states.persistent_shuffled_null; supersedes the "
                     "LEGACY within-month shuffle)"),
    }


def transition_matrix(assign: pd.DataFrame, state_col: str) -> dict:
    """Month-over-month state transitions PER NAME, and the diagonal's mean.

    A state you leave every month is a coin flip with a name; persistence is
    the minimum evidence that the partition found something with a duration.
    """
    a = assign[["permno", "month", state_col]].dropna().copy()
    a["mnum"] = pd.PeriodIndex(a["month"], freq="M").astype("int64")
    a = a.sort_values(["permno", "mnum"]).reset_index(drop=True)
    nxt_state = a.groupby("permno")[state_col].shift(-1)
    nxt_m = a.groupby("permno")["mnum"].shift(-1)
    ok = (nxt_m - a["mnum"]) == 1
    pairs = pd.DataFrame({"frm": a.loc[ok, state_col].astype(int).to_numpy(),
                          "to": nxt_state[ok].astype(int).to_numpy()})
    if pairs.empty:
        return {"note": "no consecutive-month pairs"}
    ct = pd.crosstab(pairs["frm"], pairs["to"], normalize="index").round(4)
    diag = float(np.mean([ct.loc[i, i] for i in ct.index if i in ct.columns]))
    return {"pairs": int(len(pairs)),
            "rows_are_from_state": {str(i): {str(c): float(ct.loc[i, c]) for c in ct.columns}
                                    for i in ct.index},
            "mean_persistence_diagonal": round(diag, 4),
            "random_baseline": round(1.0 / ct.shape[0], 4)}


def mixture_of_experts_summary(ic_table: dict, t_bar: float = 2.0) -> dict:
    """Read `state_ic_table` and answer the money question mechanically.

    A model is a MIXTURE-OF-EXPERTS CANDIDATE only if it is reliable in some
    states and not in others -- a uniformly good model is one expert, and
    routing it buys nothing but turnover. `states_positive_t` / `states_negative_t`
    counts the states where the sign is established at |t| >= `t_bar`; the
    verdict is deliberately conservative, because an IC that merely gets
    smaller in one state is a model that still works there.
    """
    out = {}
    for model, blk in ic_table.items():
        per = blk.get("by_state", {})
        readable = {s: v for s, v in per.items() if "mean_ic" in v}
        if not readable:
            out[model] = {"note": "no state had enough months to read"}
            continue
        ics = {s: v["mean_ic"] for s, v in readable.items()}
        ts = {s: v["t_stat"] for s, v in readable.items()}
        pos = sorted([s for s, t in ts.items() if t is not None and t >= t_bar])
        neg = sorted([s for s, t in ts.items() if t is not None and t <= -t_bar])
        best = max(ics, key=lambda s: ics[s])
        worst = min(ics, key=lambda s: ics[s])
        out[model] = {
            "overall": blk.get("overall", {}),
            "states_read": len(readable),
            "best_state": {"state": best, "mean_ic": ics[best], "t_stat": ts[best]},
            "worst_state": {"state": worst, "mean_ic": ics[worst], "t_stat": ts[worst]},
            "ic_range_across_states": round(float(ics[best] - ics[worst]), 5),
            "states_positive_t": pos,
            "states_negative_t": neg,
            "sign_flips_across_states": bool(pos and neg),
            "verdict": (
                "MIXTURE_OF_EXPERTS_CANDIDATE -- established both signs across states"
                if (pos and neg) else
                "CONDITIONAL -- established in some states, not established in others"
                if (pos and len(pos) < len(readable)) else
                "UNIFORM -- established in every state it could be read in"
                if pos and len(pos) == len(readable) else
                "NOT ESTABLISHED IN ANY STATE"),
        }
    return out


def name_states(profiles: pd.DataFrame, top: int = 2) -> dict:
    """A readable hint per state from its two most extreme scaled features.

    A hint, not a claim. `state 3` is the identity; "hi_vol|lo_mktcap" is a
    reading aid, and calling it the name would smuggle an interpretation into
    a table of numbers.
    """
    hints = {}
    for s in profiles.index:
        z = profiles.loc[s]
        top_f = z.abs().sort_values(ascending=False).index[:top]
        hints[int(s)] = "|".join(f"{'hi' if z[f] > 0 else 'lo'}_{f}" for f in top_f)
    return hints


__all__ = [
    "SCHEMA_VERSION", "SEED", "STATE_FEATURES", "MARKET_FEATURES", "TARGET_PREFIXES",
    "K_LADDER", "MARKET_K_LADDER", "STATES_DIR", "REFIT_EVERY_MONTHS",
    "MIN_TRAIN_MONTHS", "N_PCA", "N_NEIGHBOURS", "MAX_DRIFT_RATIO", "MIN_STATE_SHARE",
    "SILHOUETTE_SAMPLE", "CLIP_SD",
    "schema", "schema_hash", "assert_no_target_columns", "assert_block_ordering",
    "Block", "month_blocks", "make_embedder", "fit_block", "assign_block",
    "match_states", "centroids_in_reference_space", "stabilise_block_labels",
    "market_month_features", "run_market_states",
    "monthly_ic", "conditional_table", "state_ic_table", "spread_statistic",
    "shuffled_null", "circular_shift_labels", "persistent_shuffled_null",
    "transition_matrix", "name_states",
    "mixture_of_experts_summary",
]
