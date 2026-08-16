"""World Model v0 — a conditional DISTRIBUTION over the forward state.

WHAT THIS IS, AND WHY IT IS NOT A RETURN FORECASTER
===================================================
N6 measured forward-return SIGN at AUC 0.497-0.509 — not detectable — while
|return| IC ran 0.17-0.29 and volatility IC 0.53-0.62 on the *same* features
and the *same* folds. The direction of the next move is not in this state
vector. The SHAPE of the next move's distribution is.

So v0 predicts the conditional distribution of the H-day forward return, as a
set of quantiles, and is scored with a proper scoring rule. It is a world model
in the only sense that matters downstream: a sizing policy needs
`P(outcome | state)`, not `E[outcome | state]`, and every gate above G5 is
waiting on a distribution it can integrate a utility against.

THE BASELINE IS THE POINT
=========================
The roadmap's standing ruling is that realised volatility is commoditised **for
ranking**, so a learned model has to earn its keep on tail, drawdown and
co-movement rather than on ordering securities by vol. That makes the honest
baseline a strong one, not a weak one:

  climatology         unconditional training quantiles. Knows nothing.
  gaussian_vol        mu + z_q * rv20 * sqrt(H/252). The textbook answer.
  scaled_empirical    training-window standardised residual quantiles, rescaled
                      by today's rv20. Fat-tailed AND conditionally scaled —
                      this is the one to beat, and beating climatology instead
                      would be the flattering comparison.

A model that cannot beat `scaled_empirical` has not learned anything that cheap
volatility scaling did not already know. That is a legitimate v0 outcome and is
reported as one.

WHAT IS DELIBERATELY ABSENT FROM v0
===================================
No security identity feature, so the model must generalise across securities
and can be transfer-tested on unseen ones. No macro or options inputs. No
learned sizing policy — this produces the distribution a policy would consume,
and stops there.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

#: The quantiles v0 predicts. Denser in the tails than the middle, because the
#: tails are where the claim is that a learned model earns its keep.
QUANTILES: tuple[float, ...] = (0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95)

#: Trading days per year, for annualisation.
TRADING_DAYS = 252.0

#: z(alpha=.05 two-sided) + z(power=.80) — the same constant R13's linter uses,
#: so a bootstrap MDE and a registration-time floor are directly comparable.
_Z_MDE = 1.959963985 + 0.8416212336


# ── scoring ─────────────────────────────────────────────────────────────────

def pinball_loss(y: np.ndarray, q_pred: np.ndarray,
                 quantiles: Sequence[float] = QUANTILES) -> np.ndarray:
    """Per-observation, per-quantile pinball loss. Lower is better.

    Averaged over quantiles this is a discrete approximation to CRPS, which is
    a STRICTLY PROPER scoring rule: it is minimised only by the true
    distribution, so a model cannot win by being confidently wrong or by
    hedging everything to the median.

    Returns shape (n_obs, n_quantiles) — never pre-averaged, because the whole
    hypothesis is that the gain lives in specific quantiles and an average over
    all of them would hide it.
    """
    y = np.asarray(y, dtype=float).reshape(-1, 1)
    q_pred = np.asarray(q_pred, dtype=float)
    taus = np.asarray(quantiles, dtype=float).reshape(1, -1)
    diff = y - q_pred
    return np.maximum(taus * diff, (taus - 1.0) * diff)


def pit_coverage(y: np.ndarray, q_pred: np.ndarray,
                 quantiles: Sequence[float] = QUANTILES) -> np.ndarray:
    """Empirical P(y <= predicted q_tau), which should equal tau.

    Calibration, separately from sharpness. A model can win on pinball loss and
    still be systematically over- or under-dispersed, and a sizing policy eats
    the dispersion error directly.
    """
    y = np.asarray(y, dtype=float).reshape(-1, 1)
    q_pred = np.asarray(q_pred, dtype=float)
    return (y <= q_pred).mean(axis=0)


def enforce_monotone(q_pred: np.ndarray) -> np.ndarray:
    """Sort quantile predictions within each row.

    Independently fitted quantile models can cross — predicting a 10th
    percentile above the 25th — which is not a distribution at all. Sorting is
    the standard repair and it cannot worsen pinball loss.
    """
    return np.sort(np.asarray(q_pred, dtype=float), axis=1)


# ── baselines ───────────────────────────────────────────────────────────────

def climatology_quantiles(y_train: np.ndarray, n_obs: int,
                          quantiles: Sequence[float] = QUANTILES) -> np.ndarray:
    """Unconditional training quantiles, repeated. Knows nothing about today."""
    q = np.quantile(np.asarray(y_train, dtype=float), quantiles)
    return np.tile(q, (n_obs, 1))


def gaussian_vol_quantiles(y_train: np.ndarray, rv20_test: np.ndarray,
                           horizon_days: int,
                           quantiles: Sequence[float] = QUANTILES
                           ) -> np.ndarray:
    """mu_train + z_tau * rv20 * sqrt(H/252). The textbook answer.

    `rv20` is an ANNUALISED percentage; scaling to the H-day horizon is the
    square-root-of-time rule, which is wrong in detail and is exactly what a
    baseline should be.
    """
    from scipy.stats import norm

    mu = float(np.mean(y_train))
    z = norm.ppf(np.asarray(quantiles, dtype=float)).reshape(1, -1)
    scale = (np.asarray(rv20_test, dtype=float).reshape(-1, 1)
             * np.sqrt(horizon_days / TRADING_DAYS))
    return mu + z * scale


def scaled_empirical_quantiles(y_train: np.ndarray, rv20_train: np.ndarray,
                               rv20_test: np.ndarray, horizon_days: int,
                               quantiles: Sequence[float] = QUANTILES
                               ) -> np.ndarray:
    """Standardise training outcomes by their own vol, take EMPIRICAL quantiles,
    rescale by today's vol.

    Fat-tailed and conditionally scaled. This is the baseline that matters: if
    a learned model does not beat this, it has learned nothing that volatility
    scaling did not already contain, and saying so is the result.
    """
    y_train = np.asarray(y_train, dtype=float)
    s_train = (np.asarray(rv20_train, dtype=float)
               * np.sqrt(horizon_days / TRADING_DAYS))
    ok = s_train > 0
    std_resid = np.zeros_like(y_train)
    std_resid[ok] = y_train[ok] / s_train[ok]
    q = np.quantile(std_resid[ok], quantiles).reshape(1, -1)
    s_test = (np.asarray(rv20_test, dtype=float).reshape(-1, 1)
              * np.sqrt(horizon_days / TRADING_DAYS))
    return q * s_test


# ── the model ───────────────────────────────────────────────────────────────

@dataclass
class WorldModelV0:
    """Independent LightGBM quantile regressors, one per quantile.

    Independent rather than joint because v0's job is to establish whether the
    conditional distribution is learnable AT ALL against a strong baseline.
    Crossing is repaired by `enforce_monotone`; a joint or monotone-by-
    construction head is a v1 question and only worth the complexity if v0
    finds signal.
    """

    quantiles: tuple[float, ...] = QUANTILES
    n_estimators: int = 300
    learning_rate: float = 0.05
    num_leaves: int = 31
    min_child_samples: int = 200
    seed: int = 20260816
    models: list = field(default_factory=list)
    feature_names: tuple[str, ...] = ()

    def fit(self, X: np.ndarray, y: np.ndarray,
            feature_names: Sequence[str] = ()) -> "WorldModelV0":
        import lightgbm as lgb

        self.models = []
        self.feature_names = tuple(feature_names)
        for tau in self.quantiles:
            m = lgb.LGBMRegressor(
                objective="quantile", alpha=tau,
                n_estimators=self.n_estimators,
                learning_rate=self.learning_rate,
                num_leaves=self.num_leaves,
                min_child_samples=self.min_child_samples,
                random_state=self.seed, verbose=-1,
            )
            # NaN is passed through: LightGBM handles it natively and
            # fillna(0) on a feature matrix is banned in this codebase.
            m.fit(X, y)
            self.models.append(m)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        preds = np.column_stack([m.predict(X) for m in self.models])
        return enforce_monotone(preds)


# ── walk-forward ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PairedInference:
    """A paired difference with an interval that survives the panel's shape."""

    mean: float
    ci_lo: float
    ci_hi: float
    se: float
    mde_80pct_power: float
    n_rows: int
    n_dates: int
    n_securities: int
    n_effective: float
    block_days: int
    dependence_unit: str

    def as_dict(self) -> dict:
        return {f: getattr(self, f) for f in self.__dataclass_fields__}


def block_bootstrap_paired(diff: np.ndarray, dates: np.ndarray,
                           block_days: int, *, n_boot: int = 2000,
                           seed: int = 0) -> PairedInference:
    """Interval on a per-row paired difference over a POOLED PANEL.

    The unit resampled is a **contiguous run of calendar dates**, and every
    panel row on a sampled date travels with it. Two dependencies make that
    mandatory and either one alone is enough:

    - **Overlap.** An H-day forward outcome at date t shares H-1 days with the
      outcome at t+1, so neighbouring rows are near-copies.
    - **Cross-section.** On any single date the whole universe moves together.
      Eighteen ETFs on one day are closer to one observation than to eighteen.

    Resampling **rows** instead gets both wrong, and gets them wrong in the
    flattering direction — it manufactures independent observations out of a
    panel and narrows every interval it produces. In a date-sorted panel it is
    worse still: a block of `k` consecutive ROWS spans only `k / n_securities`
    days, so a block chosen to span the outcome horizon spans a fraction of it.

    This is the same arithmetic as R13b, one level up: `n_effective` is the
    number of non-overlapping **date blocks**, never the number of rows.
    """
    diff = np.asarray(diff, dtype=float)
    dates = np.asarray(dates)
    if diff.shape[0] != dates.shape[0]:
        raise ValueError("diff and dates must be row-aligned")

    uniq, inv = np.unique(dates, return_inverse=True)
    n_dates = int(uniq.size)
    # rows grouped by date index, so a sampled date carries its whole cross-section
    order = np.argsort(inv, kind="stable")
    sorted_inv = inv[order]
    starts = np.searchsorted(sorted_inv, np.arange(n_dates), side="left")
    ends = np.searchsorted(sorted_inv, np.arange(n_dates), side="right")

    block = max(1, int(block_days))
    n_blocks = int(np.ceil(n_dates / block))
    rng = np.random.default_rng(seed)
    boots = np.empty(n_boot, dtype=float)
    for b in range(n_boot):
        s = rng.integers(0, max(1, n_dates - block), size=n_blocks)
        picked = np.concatenate([np.arange(x, min(x + block, n_dates))
                                 for x in s])
        rows = np.concatenate([order[starts[j]:ends[j]] for j in picked])
        boots[b] = float(diff[rows].mean())

    lo, hi = float(np.quantile(boots, 0.05)), float(np.quantile(boots, 0.95))
    se = float(np.std(boots, ddof=1))
    return PairedInference(
        mean=float(diff.mean()), ci_lo=lo, ci_hi=hi, se=se,
        mde_80pct_power=float(_Z_MDE * se),
        n_rows=int(diff.size), n_dates=n_dates,
        n_securities=int(round(diff.size / max(1, n_dates))),
        n_effective=float(n_dates) / block, block_days=block,
        dependence_unit=f"contiguous {block}-trading-day block of the whole "
                        f"cross-section",
    )


@dataclass
class Fold:
    """One temporal split. `embargo_days` is not optional and not cosmetic."""

    train_end: str
    test_start: str
    test_end: str
    n_train: int
    n_test: int


def walk_forward_folds(dates: np.ndarray, first_test_year: int,
                       horizon_days: int, min_train: int = 1000
                       ) -> list[tuple[np.ndarray, np.ndarray, Fold]]:
    """Expanding-window annual refits with an H-day purge at the boundary.

    The purge is the point. A forward return computed at date t uses prices up
    to t+H, so training rows within H days of the test start have outcomes that
    overlap the test period. Without the embargo the model is scored partly on
    data it was fitted on, which is the standard way a walk-forward reports a
    number it has not earned.
    """
    dates = np.asarray(dates)
    years = dates.astype("datetime64[Y]").astype(int) + 1970
    out = []
    for y in range(first_test_year, int(years.max()) + 1):
        test_mask = years == y
        if not test_mask.any():
            continue
        test_start = dates[test_mask].min()
        # embargo: drop training rows whose outcome window reaches into test
        cutoff = test_start - np.timedelta64(horizon_days * 2, "D")
        train_mask = dates < cutoff
        if train_mask.sum() < min_train:
            continue
        out.append((
            np.where(train_mask)[0], np.where(test_mask)[0],
            Fold(train_end=str(dates[train_mask].max())[:10],
                 test_start=str(test_start)[:10],
                 test_end=str(dates[test_mask].max())[:10],
                 n_train=int(train_mask.sum()), n_test=int(test_mask.sum())),
        ))
    return out
