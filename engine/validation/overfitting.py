"""
Backtest Overfitting Guards
============================

Statistical guards that separate genuine out-of-sample skill from the
selection bias you get when you pick the best of many configurations.
These are the tools that make a backtest *honest*: when you grid-search
N weight combinations and report the winner's Sharpe, that number is
inflated by the search itself. The functions here deflate it.

Implements:
  - probabilistic_sharpe_ratio  (PSR)   — Bailey & López de Prado (2012)
  - expected_max_sharpe                  — expected max SR under N trials
  - deflated_sharpe_ratio       (DSR)   — Bailey & López de Prado (2014)
  - min_track_record_length    (MinTRL)
  - probability_of_backtest_overfitting (PBO) via CSCV
                                         — Bailey, Borwein, LdP & Zhu (2017)
  - CombinatorialPurgedCV                — distribution of backtest paths
  - passes_multiple_testing_hurdle       — Harvey, Liu & Zhu (2016) t≥3.0

Conventions
-----------
* Sharpe ratios passed to PSR/DSR are PER-OBSERVATION (not annualized),
  estimated from the same `n_obs` returns. Use `*_from_returns` helpers
  when you have a raw returns array and want this handled for you.
* `kurtosis` is the non-excess kurtosis (Normal = 3.0), matching the
  finance literature. The `*_from_returns` helpers convert from SciPy's
  excess kurtosis automatically.

References
----------
Bailey, D. & López de Prado, M. (2012). "The Sharpe Ratio Efficient Frontier."
Bailey, D. & López de Prado, M. (2014). "The Deflated Sharpe Ratio."
Bailey, Borwein, López de Prado & Zhu (2017). "The Probability of Backtest
    Overfitting." Journal of Computational Finance.
Harvey, Liu & Zhu (2016). "...and the Cross-Section of Expected Returns."
"""

from __future__ import annotations

import math
from itertools import combinations
from typing import Iterator, Optional

import numpy as np
from scipy.stats import norm

# Euler–Mascheroni constant (used in the expected-max-Sharpe estimator)
_EULER_GAMMA = 0.5772156649015329

# Harvey, Liu & Zhu (2016): factors should clear t≈3.0, not the classic 2.0,
# once you account for the hundreds of strategies already mined.
DEFAULT_TSTAT_HURDLE = 3.0


# ─────────────────────────────────────────────────────────────────────────
# Probabilistic & Deflated Sharpe Ratio
# ─────────────────────────────────────────────────────────────────────────


def probabilistic_sharpe_ratio(
    observed_sr: float,
    n_obs: int,
    skew: float = 0.0,
    kurtosis: float = 3.0,
    benchmark_sr: float = 0.0,
) -> float:
    """Probability that the true Sharpe exceeds `benchmark_sr`.

    PSR(SR*) = Φ( (SR_obs - SR*)·√(n-1) / √(1 - γ3·SR_obs + (γ4-1)/4·SR_obs²) )

    Args:
        observed_sr: Per-observation Sharpe ratio estimate.
        n_obs: Number of return observations the SR was estimated from.
        skew: Skewness (γ3) of the returns.
        kurtosis: Non-excess kurtosis (γ4, Normal = 3.0).
        benchmark_sr: Per-observation Sharpe to test against (0 = "has skill").

    Returns:
        Probability in [0, 1]. Higher = more confident the SR is real.
    """
    if n_obs < 2:
        return float("nan")

    denom_var = 1.0 - skew * observed_sr + ((kurtosis - 1.0) / 4.0) * observed_sr ** 2
    # Guard against pathological moment estimates driving the variance negative.
    if denom_var <= 1e-12:
        denom_var = 1e-12

    z = (observed_sr - benchmark_sr) * math.sqrt(n_obs - 1) / math.sqrt(denom_var)
    return float(norm.cdf(z))


def expected_max_sharpe(n_trials: int, sr_variance: float) -> float:
    """Expected maximum Sharpe ratio across N *independent* trials under H0.

    This is the Sharpe you'd expect to see from the luckiest of N random
    strategies — the bar a real strategy must clear. Uses the extreme-value
    approximation of Bailey & López de Prado (2014):

        E[max SR] ≈ √V · [ (1-γ)·Φ⁻¹(1 - 1/N) + γ·Φ⁻¹(1 - 1/(N·e)) ]

    Args:
        n_trials: Number of configurations tried (the multiple-testing count).
        sr_variance: Variance of the Sharpe ratios across those trials.

    Returns:
        The expected-max Sharpe (same per-observation units as the inputs).
    """
    if n_trials < 2 or sr_variance <= 0:
        return 0.0
    sqrt_v = math.sqrt(sr_variance)
    term1 = (1.0 - _EULER_GAMMA) * norm.ppf(1.0 - 1.0 / n_trials)
    term2 = _EULER_GAMMA * norm.ppf(1.0 - 1.0 / (n_trials * math.e))
    return float(sqrt_v * (term1 + term2))


def effective_number_of_trials(returns_matrix, min_obs: int = 30) -> dict:
    """Effective number of *independent* trials among correlated return streams.

    When candidate strategies / paper lanes share holdings their return series
    are correlated, so a raw count of N streams overstates how many independent
    bets were actually taken. The participation ratio of the eigenvalues of the
    N×N return-correlation matrix estimates the effective count:

        N_eff = (Σ λ_i)² / Σ λ_i²        (λ_i = eigenvalues of the corr matrix)

    Since the trace of a correlation matrix is N, Σλ_i = N, so N_eff = N²/Σλ_i².
    N_eff = N for mutually orthogonal streams and collapses toward 1 as the
    streams become collinear (a near-duplicate stream adds ≈0).

    **Reported, never gating.** This is estimated from a noisy, small-sample
    correlation matrix; per the TRIAL-001 design review it is surfaced as the
    "estimated independent-trials" view but must NEVER loosen the DSR adoption
    bar below the raw cumulative-trial count. On any non-ok status `n_eff`
    falls back to ``float(n_streams)`` so that even a caller that ignored this
    rule could not be made *more lenient* by a degenerate estimate.

    Args:
        returns_matrix: (T observations × N streams) array of per-period returns.
        min_obs: minimum aligned (NaN-free) observations for a stable estimate.

    Returns:
        ``{n_eff, n_streams, n_obs, status}`` with status ∈
        {ok, single_stream, insufficient_history, degenerate}.
    """
    M = np.asarray(returns_matrix, dtype=float)
    if M.ndim != 2:
        raise ValueError("returns_matrix must be 2-D (T observations × N streams)")
    n_streams = int(M.shape[1])

    if n_streams < 2:
        return {"n_eff": float(n_streams), "n_streams": n_streams,
                "n_obs": int(M.shape[0]), "status": "single_stream"}

    # Keep only rows where every stream has an observation (aligned history).
    aligned = M[~np.isnan(M).any(axis=1)]
    n_obs = int(aligned.shape[0])
    if n_obs < min_obs:
        return {"n_eff": float(n_streams), "n_streams": n_streams,
                "n_obs": n_obs, "status": "insufficient_history"}

    # Zero-variance streams make the correlation matrix undefined.
    if np.any(aligned.std(axis=0, ddof=1) < 1e-12):
        return {"n_eff": float(n_streams), "n_streams": n_streams,
                "n_obs": n_obs, "status": "degenerate"}

    corr = np.corrcoef(aligned, rowvar=False)
    if not np.all(np.isfinite(corr)):
        return {"n_eff": float(n_streams), "n_streams": n_streams,
                "n_obs": n_obs, "status": "degenerate"}

    eig = np.linalg.eigvalsh(corr)
    eig = np.clip(eig, 0.0, None)  # numerical: tiny negatives → 0
    sum_sq = float(np.sum(eig ** 2))
    if sum_sq <= 1e-12:
        return {"n_eff": float(n_streams), "n_streams": n_streams,
                "n_obs": n_obs, "status": "degenerate"}

    n_eff = float(np.sum(eig)) ** 2 / sum_sq
    n_eff = float(min(max(n_eff, 1.0), n_streams))  # clamp to [1, N]
    return {"n_eff": round(n_eff, 4), "n_streams": n_streams,
            "n_obs": n_obs, "status": "ok"}


def deflated_sharpe_ratio(
    observed_sr: float,
    n_obs: int,
    n_trials: int,
    sr_variance: float,
    skew: float = 0.0,
    kurtosis: float = 3.0,
) -> float:
    """Deflated Sharpe Ratio — PSR against the expected-max-under-N-trials bar.

    DSR = PSR(SR0)  where  SR0 = expected_max_sharpe(n_trials, sr_variance).

    A high observed Sharpe selected from many trials can still yield a LOW
    DSR — that's the whole point: it tells you the winner is probably luck.

    Returns:
        Probability in [0, 1]. A common ship/no-ship bar is DSR ≥ 0.95.
    """
    sr0 = expected_max_sharpe(n_trials, sr_variance)
    return probabilistic_sharpe_ratio(
        observed_sr, n_obs, skew=skew, kurtosis=kurtosis, benchmark_sr=sr0
    )


def min_track_record_length(
    observed_sr: float,
    skew: float = 0.0,
    kurtosis: float = 3.0,
    benchmark_sr: float = 0.0,
    confidence: float = 0.95,
) -> float:
    """Minimum number of observations for PSR(benchmark) to reach `confidence`.

    MinTRL = 1 + (1 - γ3·SR + (γ4-1)/4·SR²) · (Φ⁻¹(conf) / (SR - SR*))²

    Returns inf when the observed SR does not exceed the benchmark.
    """
    edge = observed_sr - benchmark_sr
    if edge <= 0:
        return float("inf")
    denom_var = 1.0 - skew * observed_sr + ((kurtosis - 1.0) / 4.0) * observed_sr ** 2
    if denom_var <= 0:
        denom_var = 1e-12
    z = norm.ppf(confidence)
    return float(1.0 + denom_var * (z / edge) ** 2)


# --- Convenience wrappers that work directly from a returns array ----------


def _moments(returns: np.ndarray) -> tuple[float, int, float, float]:
    """Return (per-obs Sharpe, n, skew, non-excess kurtosis) for a returns array."""
    from scipy.stats import kurtosis as _kurt
    from scipy.stats import skew as _skew

    r = np.asarray(returns, dtype=float)
    r = r[~np.isnan(r)]
    n = len(r)
    if n < 2:
        return 0.0, n, 0.0, 3.0
    std = r.std(ddof=1)
    sr = float(r.mean() / std) if std > 1e-12 else 0.0
    sk = float(_skew(r)) if n > 2 else 0.0
    # SciPy returns EXCESS kurtosis (Normal = 0); convert to non-excess (Normal = 3).
    ku = float(_kurt(r, fisher=True)) + 3.0 if n > 3 else 3.0
    return sr, n, sk, ku


def deflated_sharpe_from_returns(
    returns: np.ndarray,
    n_trials: int,
    sr_variance: float,
) -> dict:
    """DSR + PSR + components computed straight from a returns array.

    Returns a dict suitable for logging next to a recommendation.
    """
    sr, n, sk, ku = _moments(returns)
    sr0 = expected_max_sharpe(n_trials, sr_variance)
    psr = probabilistic_sharpe_ratio(sr, n, skew=sk, kurtosis=ku, benchmark_sr=0.0)
    dsr = probabilistic_sharpe_ratio(sr, n, skew=sk, kurtosis=ku, benchmark_sr=sr0)
    return {
        "observed_sharpe": round(sr, 4),
        "n_obs": n,
        "skew": round(sk, 4),
        "kurtosis": round(ku, 4),
        "n_trials": n_trials,
        "expected_max_sharpe_h0": round(sr0, 4),
        "psr": round(psr, 4),
        "dsr": round(dsr, 4),
    }


def passes_multiple_testing_hurdle(
    t_stat: float, hurdle: float = DEFAULT_TSTAT_HURDLE
) -> bool:
    """True if |t_stat| clears the Harvey/Liu/Zhu multiple-testing hurdle (≈3.0)."""
    return abs(t_stat) >= hurdle


# ─────────────────────────────────────────────────────────────────────────
# Probability of Backtest Overfitting (CSCV)
# ─────────────────────────────────────────────────────────────────────────


def _sharpe_per_column(matrix: np.ndarray) -> np.ndarray:
    """Per-observation Sharpe for each column (strategy) of a (T × N) matrix."""
    if matrix.shape[0] < 2:
        return np.full(matrix.shape[1], np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = matrix.mean(axis=0)
        std = matrix.std(axis=0, ddof=1)
        std = np.where(std < 1e-12, np.nan, std)
        return mean / std


def probability_of_backtest_overfitting(
    perf_matrix: np.ndarray,
    n_partitions: int = 8,
    performance_fn=None,
) -> dict:
    """PBO via Combinatorially-Symmetric Cross-Validation (CSCV).

    `perf_matrix` is shape (T, N): T time observations × N candidate
    configurations, each cell a per-period performance (e.g., return).

    Procedure (Bailey et al. 2017):
      1. Split the T rows into S disjoint, contiguous partitions.
      2. For every way of choosing S/2 partitions as the in-sample (IS) set
         (the complement is out-of-sample, OOS):
           - pick the config that is best IS,
           - find that config's relative rank OOS, ω ∈ (0, 1),
           - record the logit λ = ln(ω / (1-ω)).
      3. PBO = fraction of splits where λ ≤ 0 — i.e. the IS-best config
         lands below the OOS median. PBO near 0 = robust; near 0.5+ = the
         selection is essentially noise.

    Args:
        perf_matrix: (T, N) array of per-period performance.
        n_partitions: S, even. Reduced automatically if T is too small.
        performance_fn: maps an (rows × N) sub-matrix → (N,) scores.
            Defaults to per-observation Sharpe.

    Returns:
        Dict with pbo, n_splits, median_logit, and the logit list.
    """
    M = np.asarray(perf_matrix, dtype=float)
    if M.ndim != 2:
        raise ValueError("perf_matrix must be 2-D (T observations × N configs)")
    T, N = M.shape
    if N < 2:
        return {"pbo": float("nan"), "n_splits": 0, "reason": "need ≥2 configs"}

    perf = performance_fn or _sharpe_per_column

    # Ensure S is even and small enough that each partition has ≥2 rows
    # (a per-observation Sharpe needs at least two points to be defined).
    S = min(n_partitions, T // 2)
    if S % 2 == 1:
        S -= 1
    if S < 2:
        return {"pbo": float("nan"), "n_splits": 0, "reason": "too few observations"}

    # Contiguous, near-equal partitions of the row index.
    bounds = np.linspace(0, T, S + 1).astype(int)
    partitions = [np.arange(bounds[i], bounds[i + 1]) for i in range(S)]
    partitions = [p for p in partitions if len(p) > 0]
    S = len(partitions)
    if S < 2:
        return {"pbo": float("nan"), "n_splits": 0, "reason": "too few observations"}

    logits: list[float] = []
    half = S // 2
    for is_combo in combinations(range(S), half):
        is_rows = np.concatenate([partitions[i] for i in is_combo])
        oos_idx = [i for i in range(S) if i not in is_combo]
        oos_rows = np.concatenate([partitions[i] for i in oos_idx])

        is_perf = perf(M[is_rows])
        oos_perf = perf(M[oos_rows])
        if np.all(np.isnan(is_perf)):
            continue

        best = int(np.nanargmax(is_perf))
        # Relative OOS rank of the IS-best config (1 = worst … N = best).
        order = np.argsort(np.argsort(np.nan_to_num(oos_perf, nan=-np.inf)))
        rank = order[best] + 1
        omega = rank / (N + 1)
        omega = min(max(omega, 1e-6), 1 - 1e-6)
        logits.append(math.log(omega / (1.0 - omega)))

    if not logits:
        return {"pbo": float("nan"), "n_splits": 0, "reason": "no valid splits"}

    arr = np.array(logits)
    pbo = float(np.mean(arr <= 0.0))
    return {
        "pbo": round(pbo, 4),
        "n_splits": len(logits),
        "n_partitions": S,
        "median_logit": round(float(np.median(arr)), 4),
        "interpretation": (
            "robust" if pbo < 0.25 else "fragile" if pbo < 0.5 else "overfit"
        ),
    }


# ─────────────────────────────────────────────────────────────────────────
# Combinatorial Purged Cross-Validation (path generator)
# ─────────────────────────────────────────────────────────────────────────


class CombinatorialPurgedCV:
    """Combinatorial Purged CV — yields many backtest paths, not one.

    Where PurgedKFold gives a single train/test partition per fold, CPCV
    chooses k of N groups as the test set in every combination, producing
    C(N, k) splits and hence a *distribution* of out-of-sample paths. Each
    split purges train groups whose label window overlaps a test group and
    applies an embargo, exactly like PurgedKFold.

    This complements `probability_of_backtest_overfitting` (which detects
    selection bias): CPCV is for estimating the dispersion of a single
    strategy's performance across plausible histories.

    Args:
        n_groups: N — number of contiguous groups to split the timeline into.
        n_test_groups: k — groups held out per split (paths = C(N, k)).
        embargo_td: Embargo in observations applied around each test group.
    """

    def __init__(
        self, n_groups: int = 6, n_test_groups: int = 2, embargo_td: int = 0
    ):
        if n_test_groups >= n_groups:
            raise ValueError("n_test_groups must be < n_groups")
        self.n_groups = n_groups
        self.n_test_groups = n_test_groups
        self.embargo_td = embargo_td

    def n_paths(self) -> int:
        return math.comb(self.n_groups, self.n_test_groups)

    def split(self, n_samples: int) -> Iterator[tuple[np.ndarray, np.ndarray]]:
        """Yield (train_idx, test_idx) integer arrays for each combination."""
        if n_samples < self.n_groups:
            raise ValueError(
                f"Cannot split {n_samples} samples into {self.n_groups} groups"
            )
        bounds = np.linspace(0, n_samples, self.n_groups + 1).astype(int)
        groups = [np.arange(bounds[i], bounds[i + 1]) for i in range(self.n_groups)]

        for test_combo in combinations(range(self.n_groups), self.n_test_groups):
            test_idx = np.concatenate([groups[i] for i in test_combo])
            train_mask = np.ones(n_samples, dtype=bool)
            train_mask[test_idx] = False

            # Embargo a buffer on both sides of each contiguous test group.
            if self.embargo_td > 0:
                for g in test_combo:
                    lo = max(0, bounds[g] - self.embargo_td)
                    hi = min(n_samples, bounds[g + 1] + self.embargo_td)
                    train_mask[lo:bounds[g]] = False
                    train_mask[bounds[g + 1]:hi] = False

            train_idx = np.arange(n_samples)[train_mask]
            if len(train_idx) < 1:
                continue
            yield train_idx, np.sort(test_idx)
