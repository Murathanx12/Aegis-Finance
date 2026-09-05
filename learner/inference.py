"""learner/inference.py -- THE FOUR TESTS A SEARCH OWES ITS OWN RESULT.

WHY THIS FILE EXISTS (B4 §1, night lab 2026-09-05)
==================================================
`learner/nullbar.py` answers *"is this arm better than the same pipeline fitted
on noise?"* and it answers it well. It does not answer the three questions that
follow, and every one of them has already bitten this programme:

1. **How many things did you look at?** The v2 driver computed
   `family_max_p` and then never called it, so a champion selected from
   (arm x head x horizon) cells was quoted at its own single-cell percentile.
   `nullbar.family_max_p` fixes that for a permutation family. It does NOT fix
   a Sharpe ratio quoted from the best of N backtests, which is what
   **Deflated Sharpe** (Bailey & Lopez de Prado 2014) is for.
2. **Is the best arm better than the BEST ALTERNATIVE, not just than noise?**
   `#{null >= observed}` compares an arm with a shuffled version of itself.
   **Hansen's SPA** compares the best arm with every other arm in the family
   under a stationary bootstrap that keeps the serial dependence -- which is
   the exact failure mode measured on 2026-09-03: a model fitted on noise holds
   ONE persistent tilt, so its monthly statistics are serially correlated and a
   naive across-months t is mis-specified (t spans -9..+12 across seeds).
3. **Would the ranking have survived out of sample?** A leaderboard is a
   selection, and a selection has its own overfitting probability. **CSCV/PBO**
   (Bailey, Borwein, Lopez de Prado, Zhu 2015) measures it directly: how often
   does the in-sample champion land below the median out of sample?

Plus the thing all three need and nothing had: **per-draw persistence.** A null
distribution that lives only in a summary cannot be re-used, re-checked, or
pooled across jobs, and a receipt that quotes p = 0.03 from draws nobody kept
is a number on trust.

WHAT THIS MODULE REFUSES TO DO
==============================
It does not decide. Every function returns numbers and a verdict STRING that
includes `CANNOT DETERMINE` as a first-class outcome, because the honest answer
to most of tonight's questions is that the data does not resolve them. A test
that can only say PASS or FAIL will say one of them when neither is true.

CONVENTIONS
===========
* Returns/series are per-period (monthly unless the caller says otherwise) and
  are NOT annualised inside this module. Annualising before a test changes the
  test; annualise for the reader, afterwards.
* `d` series in SPA are PAIRED EXCESS: arm minus its benchmark, same index.
* Every p-value is one-sided upper (`P(null >= observed)`) with the add-one
  convention, matching `learner/nullbar.py`.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import numpy as np

try:                                                    # pragma: no cover
    from scipy.stats import norm as _scipy_norm
except Exception:                                       # pragma: no cover
    _scipy_norm = None

CANNOT_DETERMINE = "CANNOT DETERMINE"

#: Below this many bootstrap/permutation draws no p-value is reported. Same
#: floor and same reason as `nullbar.MIN_DRAWS`: a p-value from 8 draws
#: resolves nothing below 0.11 and will be quoted as if it did.
MIN_DRAWS = 64

#: Mean block length for the stationary bootstrap, in PERIODS. Three to six
#: months on monthly data: long enough to carry the serial correlation a
#: persistent tilt creates, short enough that a 132-month panel still has
#: independent information in it.
DEFAULT_BLOCK = 4.0

_EULER = 0.5772156649015329


# --------------------------------------------------------------------- normal


def _ncdf(x: float) -> float:
    if _scipy_norm is not None:
        return float(_scipy_norm.cdf(x))
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _nppf(p: float) -> float:
    """Inverse standard normal. Acklam's rational approximation when scipy is
    absent (|error| < 1.15e-9), because this module must run in an offline
    night job on a machine that may not have scipy."""
    if _scipy_norm is not None:
        return float(_scipy_norm.ppf(p))
    if not 0.0 < p < 1.0:
        return float("nan")
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
                ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q, r = p - 0.5, (p - 0.5) ** 2
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
           (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def _clean(x) -> np.ndarray:
    a = np.asarray(x, dtype="float64").ravel()
    return a[np.isfinite(a)]


# ------------------------------------------------------------ per-draw storage


@dataclass
class DrawStore:
    """Every null draw, on disk, keyed by (family, cell, seed).

    WHY EVERY DRAW AND NOT A SUMMARY. Three uses, all of which have already
    been wanted and been impossible: recomputing a family-max p over a DIFFERENT
    set of cells without re-running the nulls; pooling draws from two jobs that
    used the same pipeline; and checking, later, that a quoted p-value came from
    the draws it claims. A summary supports none of them.

    JSONL, append-only, one row per draw. Deliberately not a database: the file
    is greppable, diffable, and survives a killed job with everything written
    up to that moment intact.
    """

    path: Path
    family_id: str
    rows: list[dict] = field(default_factory=list)

    def add(self, cell: str, seed: int, stat: float, **extra) -> None:
        self.rows.append({"family_id": self.family_id, "cell": cell,
                          "seed": int(seed), "stat": float(stat), **extra})

    def flush(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            for r in self.rows:
                fh.write(json.dumps(r) + "\n")
        n = len(self.rows)
        self.rows = []
        self.path.with_suffix(self.path.suffix + ".count").write_text(str(n), encoding="utf-8")
        return self.path

    @staticmethod
    def load(path: Path, family_id: str | None = None) -> dict[str, list[float]]:
        """{cell: [stat, ...]} from a draw file."""
        out: dict[str, list[float]] = {}
        if not Path(path).exists():
            return out
        with Path(path).open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if family_id and r.get("family_id") != family_id:
                    continue
                out.setdefault(str(r.get("cell")), []).append(float(r.get("stat")))
        return out

    @staticmethod
    def per_draw_cells(path: Path, family_id: str | None = None) -> list[dict[str, float]]:
        """[{cell: stat}] grouped by SEED -- the shape `nullbar.family_max_p`
        wants. Grouping by seed is what makes the family maximum meaningful:
        the max must be taken across cells WITHIN one draw of the world, never
        across independent draws of different cells."""
        by_seed: dict[int, dict[str, float]] = {}
        if not Path(path).exists():
            return []
        with Path(path).open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if family_id and r.get("family_id") != family_id:
                    continue
                by_seed.setdefault(int(r.get("seed", -1)), {})[str(r.get("cell"))] = float(r.get("stat"))
        return [by_seed[k] for k in sorted(by_seed)]


# ------------------------------------------------------------ deflated Sharpe


def sharpe(returns: Sequence[float]) -> float | None:
    a = _clean(returns)
    if a.size < 2 or a.std(ddof=1) == 0:
        return None
    return float(a.mean() / a.std(ddof=1))


def deflated_sharpe(returns: Sequence[float], *, n_trials: int,
                    null_sharpes: Sequence[float] | None = None,
                    sr_benchmark: float | None = None) -> dict:
    """P(the true Sharpe is positive | this SR, this skew/kurtosis, N trials).

    THE NUMBER IT CORRECTS. A search that looked at N cells and quotes the best
    one's Sharpe is quoting the maximum of N draws. Even under a strictly zero
    edge that maximum grows like sqrt(2 log N) standard deviations of the null
    -- at N = 64 cells the expected best is ~2.3 null sd above zero, which on a
    132-month panel is a t of ~2.3 and reads as significance to anyone who was
    not told how many cells were opened.

    `sr_benchmark` (SR0) is the expected MAXIMUM Sharpe under the null across
    `n_trials`, from Bailey & Lopez de Prado's expression. Its scale is the
    null's own sd, which is estimated from `null_sharpes` when they are given
    -- draws we already paid for -- and falls back to the analytic
    `1/sqrt(T-1)` when they are not, WITH that stated in the receipt.

    Returns `dsr` in [0, 1]: the probability the observed SR exceeds SR0 after
    correcting for non-normal returns. Read it as a confidence, not a p-value:
    dsr >= 0.95 is the usual bar.
    """
    a = _clean(returns)
    T = a.size
    if T < 8:
        return {"verdict": f"{CANNOT_DETERMINE} (only {T} periods; DSR needs a sample)",
                "n_periods": int(T)}
    sr = sharpe(a)
    if sr is None:
        return {"verdict": f"{CANNOT_DETERMINE} (zero variance)", "n_periods": int(T)}
    mu, sd = a.mean(), a.std(ddof=1)
    g3 = float(((a - mu) ** 3).mean() / sd ** 3)
    g4 = float(((a - mu) ** 4).mean() / sd ** 4)          # raw kurtosis, not excess

    null = _clean(null_sharpes) if null_sharpes is not None else np.array([])
    if null.size >= MIN_DRAWS:
        sr_sd = float(null.std(ddof=1))
        sd_basis = f"sd of {null.size} null Sharpes"
    else:
        sr_sd = 1.0 / math.sqrt(max(1, T - 1))
        sd_basis = (f"analytic 1/sqrt(T-1) -- only {null.size} null draws, below the "
                    f"{MIN_DRAWS} floor")
    N = max(1, int(n_trials))
    if sr_benchmark is None:
        if N == 1:
            sr0 = 0.0
        else:
            sr0 = sr_sd * ((1 - _EULER) * _nppf(1 - 1.0 / N)
                           + _EULER * _nppf(1 - 1.0 / (N * math.e)))
    else:
        sr0 = float(sr_benchmark)

    denom = 1.0 - g3 * sr + ((g4 - 1.0) / 4.0) * sr ** 2
    if denom <= 0:
        return {"verdict": f"{CANNOT_DETERMINE} (non-normality term {denom:.3f} <= 0; "
                           "the DSR expression is undefined for these moments)",
                "sharpe": round(sr, 4), "skew": round(g3, 3), "kurtosis": round(g4, 3)}
    z = (sr - sr0) * math.sqrt(T - 1) / math.sqrt(denom)
    dsr = _ncdf(z)
    return {
        "sharpe": round(sr, 4),
        "sharpe_benchmark_sr0": round(sr0, 4),
        "n_trials": N,
        "null_sd_basis": sd_basis,
        "skew": round(g3, 3),
        "kurtosis": round(g4, 3),
        "n_periods": int(T),
        "z": round(z, 4),
        "dsr": round(float(dsr), 4),
        "verdict": ("CLEARS_DEFLATED_SHARPE" if dsr >= 0.95 else
                    "WITHIN_SELECTION_NOISE"),
        "reading": (f"after {N} cells were looked at, the Sharpe a zero-edge search would be "
                    f"expected to produce is {sr0:.3f}; this arm's is {sr:.3f}."),
    }


# ------------------------------------------------- stationary bootstrap + SPA


def stationary_bootstrap_indices(n: int, *, block: float = DEFAULT_BLOCK,
                                 n_boot: int = 1000, seed: int = 0) -> np.ndarray:
    """(n_boot, n) resampled indices, Politis-Romano stationary bootstrap.

    Geometric block lengths with mean `block` and wrap-around, which is what
    makes the resample STATIONARY -- a plain moving-block bootstrap under-weights
    the ends of the sample, and on a 132-month panel the ends are two whole
    market regimes.
    """
    rng = np.random.default_rng(seed)
    p = 1.0 / max(1.0, float(block))
    out = np.empty((n_boot, n), dtype="int64")
    for b in range(n_boot):
        idx = np.empty(n, dtype="int64")
        i = 0
        cur = int(rng.integers(0, n))
        while i < n:
            idx[i] = cur
            i += 1
            if rng.random() < p:
                cur = int(rng.integers(0, n))
            else:
                cur = (cur + 1) % n
        out[b] = idx
    return out


def spa(paired: Mapping[str, Sequence[float]], *, block: float = DEFAULT_BLOCK,
        n_boot: int = 1000, seed: int = 0) -> dict:
    """Hansen's Superior Predictive Ability test over a family of arms.

    H0: NO arm in the family has a positive expected paired excess. The
    alternative is "at least one does", which is exactly the claim a leaderboard
    makes when it prints its top row.

    Each `paired[arm]` is that arm's excess over its benchmark, per period, on a
    COMMON index -- pairing is what removes the market from both sides, and it
    is the reason this is not simply a t-test on the winner.

    Hansen's consistent recentring keeps arms whose sample mean is not too
    negative (|mean| below A_k = n^-1/4 * omega_k / 4) in the null distribution
    and drops the hopeless ones, which is what makes SPA less conservative than
    White's Reality Check without becoming liberal.

    Returns `p_spa_consistent` (the headline), the lower/upper bracket, and the
    winning arm. Refuses below the draw floor rather than reporting a p-value
    from too few resamples.
    """
    names = [k for k, v in paired.items() if _clean(v).size > 0]
    if not names:
        return {"verdict": f"{CANNOT_DETERMINE} (no usable arms)"}
    lengths = {len(_clean(paired[k])) for k in names}
    if len(lengths) != 1:
        return {"verdict": f"{CANNOT_DETERMINE} (arms have different lengths {sorted(lengths)}; "
                           "SPA needs a common index -- align before calling)"}
    n = lengths.pop()
    if n < 12:
        return {"verdict": f"{CANNOT_DETERMINE} (only {n} periods)", "n_periods": int(n)}
    if n_boot < MIN_DRAWS:
        return {"verdict": f"{CANNOT_DETERMINE} (n_boot {n_boot} < {MIN_DRAWS})"}

    D = np.vstack([_clean(paired[k]) for k in names])          # (L, n)
    L = D.shape[0]
    means = D.mean(axis=1)
    idx = stationary_bootstrap_indices(n, block=block, n_boot=n_boot, seed=seed)

    # omega_k: sd of sqrt(n) * mean, from the bootstrap itself, so the serial
    # dependence that a naive sd ignores is inside the scale.
    boot_means = np.empty((n_boot, L), dtype="float64")
    for b in range(n_boot):
        boot_means[b] = D[:, idx[b]].mean(axis=1)
    omega = np.sqrt(n) * boot_means.std(axis=0, ddof=1)
    omega = np.where(omega > 1e-12, omega, np.nan)

    t_stat = np.sqrt(n) * means / omega
    t_obs = float(np.nanmax(np.maximum(t_stat, 0.0)))
    best = names[int(np.nanargmax(np.where(np.isfinite(t_stat), t_stat, -np.inf)))]

    A = (omega / 4.0) * (n ** -0.25)                            # Hansen's threshold
    keep_c = means >= -A                                        # consistent
    centred_c = np.where(keep_c, means, 0.0)
    t_boot_c = np.empty(n_boot, dtype="float64")
    t_boot_l = np.empty(n_boot, dtype="float64")
    t_boot_u = np.empty(n_boot, dtype="float64")
    for b in range(n_boot):
        z = np.sqrt(n) * (boot_means[b] - centred_c) / omega
        t_boot_c[b] = np.nanmax(np.maximum(z, 0.0))
        zl = np.sqrt(n) * (boot_means[b] - means) / omega       # lower: recentre all
        t_boot_l[b] = np.nanmax(np.maximum(zl, 0.0))
        zu = np.sqrt(n) * (boot_means[b] - np.where(means >= 0, means, 0.0)) / omega
        t_boot_u[b] = np.nanmax(np.maximum(zu, 0.0))

    def _p(draws):
        d = _clean(draws)
        return float(((d >= t_obs).sum() + 1) / (d.size + 1))

    p_c = _p(t_boot_c)
    return {
        "best_arm": best,
        "n_arms": int(L),
        "n_periods": int(n),
        "n_boot": int(n_boot),
        "block_periods": float(block),
        "t_spa": round(t_obs, 4),
        "p_spa_consistent": round(p_c, 4),
        "p_spa_lower": round(_p(t_boot_l), 4),
        "p_spa_upper": round(_p(t_boot_u), 4),
        "arm_means": {k: round(float(m), 6) for k, m in zip(names, means)},
        "verdict": ("CLEARS_SPA" if p_c <= 0.05 else "WITHIN_SPA_NULL"),
        "reading": ("H0: no arm in this family has positive expected paired excess. "
                    "p is the share of stationary-bootstrap worlds in which the BEST arm "
                    "looks at least this good under that null."),
    }


# ---------------------------------------------------------------- CPCV + PBO


def cpcv_splits(n_obs: int, *, n_groups: int = 6, k_test: int = 2,
                purge: int = 1, embargo: int = 1) -> list[tuple[np.ndarray, np.ndarray]]:
    """Combinatorial purged cross-validation splits over a TIME index.

    `n_groups` contiguous blocks, every combination of `k_test` of them held
    out, and every training observation within `purge` periods BEFORE a test
    block or `embargo` periods AFTER one removed. Purging is what stops a
    12-month forward label from being in the training set of a fold whose test
    block starts eleven months later; the embargo removes the mirror image.

    Returns [(train_idx, test_idx)]. With 6 groups and k=2 that is 15 folds,
    each with a different train/test partition -- which is the point: the
    variance ACROSS partitions is the number PBO consumes.
    """
    if n_obs < n_groups * 2:
        return []
    bounds = np.linspace(0, n_obs, n_groups + 1).astype(int)
    groups = [np.arange(bounds[i], bounds[i + 1]) for i in range(n_groups)]
    out = []
    for combo in combinations(range(n_groups), k_test):
        test = np.concatenate([groups[i] for i in combo])
        blocked = set()
        for i in combo:
            lo, hi = groups[i][0], groups[i][-1]
            blocked.update(range(max(0, lo - purge), lo))
            blocked.update(range(hi + 1, min(n_obs, hi + 1 + embargo)))
        train = np.array([i for i in range(n_obs)
                          if i not in set(test.tolist()) and i not in blocked], dtype="int64")
        if train.size and test.size:
            out.append((train, test))
    return out


def pbo(performance: np.ndarray, *, n_splits: int = 8) -> dict:
    """Probability of Backtest Overfitting (CSCV, Bailey et al. 2015).

    `performance` is (T periods, N arms) of per-period returns -- the same
    matrix a leaderboard is built from. The sample is cut into `n_splits`
    contiguous blocks; for every way of assigning half the blocks to IS and the
    other half to OOS, the IS champion is found and its OOS RANK recorded. PBO
    is the share of those partitions in which the IS champion lands in the
    bottom half out of sample.

    A leaderboard with PBO near 0.5 is a leaderboard whose top row is a coin
    flip -- and every number on it is still, individually, exactly as computed.
    That is the point: PBO is a property of the SEARCH, not of any arm.
    """
    M = np.asarray(performance, dtype="float64")
    if M.ndim != 2 or M.shape[1] < 2:
        return {"verdict": f"{CANNOT_DETERMINE} (need >= 2 arms; got shape {M.shape})"}
    T, N = M.shape
    S = int(n_splits)
    if S % 2:
        S += 1
    if T < S * 2:
        return {"verdict": f"{CANNOT_DETERMINE} ({T} periods is too few for {S} blocks)",
                "n_periods": int(T), "n_arms": int(N)}
    bounds = np.linspace(0, T, S + 1).astype(int)
    blocks = [np.arange(bounds[i], bounds[i + 1]) for i in range(S)]
    lambdas: list[float] = []
    n_below = 0
    for combo in combinations(range(S), S // 2):
        is_idx = np.concatenate([blocks[i] for i in combo])
        oos_idx = np.concatenate([blocks[i] for i in range(S) if i not in combo])
        is_perf = np.array([_sr_or_nan(M[is_idx, j]) for j in range(N)])
        oos_perf = np.array([_sr_or_nan(M[oos_idx, j]) for j in range(N)])
        if not np.isfinite(is_perf).any() or not np.isfinite(oos_perf).any():
            continue
        champ = int(np.nanargmax(is_perf))
        finite = np.isfinite(oos_perf)
        if not finite[champ]:
            continue
        rank = float((oos_perf[finite] < oos_perf[champ]).sum() + 1) / (finite.sum() + 1)
        rank = min(max(rank, 1e-6), 1 - 1e-6)
        lam = math.log(rank / (1 - rank))
        lambdas.append(lam)
        n_below += int(lam <= 0)
    if not lambdas:
        return {"verdict": f"{CANNOT_DETERMINE} (no usable partitions)"}
    p = n_below / len(lambdas)
    return {
        "pbo": round(p, 4),
        "n_partitions": len(lambdas),
        "n_arms": int(N),
        "n_periods": int(T),
        "median_logit": round(float(np.median(lambdas)), 4),
        "verdict": ("SELECTION_IS_STABLE" if p <= 0.25 else
                    "SELECTION_IS_OVERFIT" if p >= 0.5 else "SELECTION_IS_FRAGILE"),
        "reading": ("share of in-sample/out-of-sample partitions in which the in-sample "
                    "champion finished BELOW the out-of-sample median. 0.5 is a coin flip."),
    }


def _sr_or_nan(x: np.ndarray) -> float:
    a = _clean(x)
    if a.size < 2 or a.std(ddof=1) == 0:
        return float("nan")
    return float(a.mean() / a.std(ddof=1))


# ------------------------------------------------ how much tape would it take?


def power_note(returns: Sequence[float], periods_per_year: int = 12,
               t_target: float = 2.0) -> dict:
    """`n_periods`, the observed t, and THE YEARS OF TAPE t = 2 WOULD NEED.

    WHY THIS BELONGS BESIDE EVERY SHARPE
    ------------------------------------
    A t-statistic on a mean return is `SR * sqrt(T)`. That single identity says
    the thing the night lab of 2026-09-05 spent a night discovering: the best
    learner cell was +14.4%/yr ahead of the market at a monthly Sharpe that
    needed **16.1 years** of out-of-sample months to reach t = 2, and the panel
    had 7.0. No model change moves that. Only tape does.

    So a receipt that quotes a t without quoting `years_needed_for_t2` invites
    the reader to treat an underpowered result as a negative one, which is a
    different -- and usually wrong -- claim. `CANNOT DETERMINE` is the honest
    verdict when `years_needed` exceeds `years_observed`; `NOISE` is only
    honest when the tape was long enough for the effect to have shown up.

    Inverting the identity: `T_needed = (t_target / SR)^2` periods. It is
    reported as `None` where the Sharpe is non-positive -- a negative arm does
    not "need" tape to become significant, it needs a different idea, and
    printing a number there would read as a promise.
    """
    a = _clean(returns)
    T = int(a.size)
    if T < 2 or a.std(ddof=1) == 0:
        # THE DEGENERATE BRANCH RETURNS THE FULL KEY SET, and it says which of
        # the two causes it was. The first version returned two keys, so
        # `power_note(x)["powered"]` raised KeyError on a short arm instead of
        # reading False -- a caller that indexes the flag would crash exactly
        # where the evidence is thinnest. And "fewer than 2 usable periods" is
        # the wrong sentence for a 50-period CONSTANT series; naming the wrong
        # cause sends the reader to look for missing data that is all present.
        why = ("fewer than 2 usable periods" if T < 2
               else f"all {T} periods are identical, so the Sharpe is undefined "
                    "(zero variance, not a short sample)")
        return {
            "n_periods": T,
            "periods_per_year": periods_per_year,
            "n_oos_months": T if periods_per_year == 12 else None,
            "sharpe_per_period": None,
            "t_observed": None,
            "years_observed": round(T / float(periods_per_year), 2),
            "t_target": t_target,
            "periods_needed_for_t_target": None,
            "years_needed_for_t2": None,
            "powered": False,
            "verdict": f"{CANNOT_DETERMINE} ({why})",
            "reading": f"{CANNOT_DETERMINE}: {why}",
        }
    sr = float(a.mean() / a.std(ddof=1))
    t_obs = sr * math.sqrt(T)
    years_obs = T / float(periods_per_year)
    if sr <= 0:
        needed_periods = None
        needed_years = None
        reading = (f"the arm's mean is not positive (SR {sr:.4f}); no amount of tape makes a "
                   "negative mean significant in the intended direction")
    else:
        needed_periods = (t_target / sr) ** 2
        needed_years = needed_periods / float(periods_per_year)
        reading = (f"t = {t_obs:.2f} on {years_obs:.1f} years; t = {t_target:g} would need "
                   f"{needed_years:.1f} years at this Sharpe -- "
                   f"{'ENOUGH TAPE' if needed_years <= years_obs else 'MORE TAPE THAN EXISTS HERE'}")
    return {
        "n_periods": T,
        "periods_per_year": periods_per_year,
        "n_oos_months": T if periods_per_year == 12 else None,
        "sharpe_per_period": round(sr, 4),
        "t_observed": round(float(t_obs), 4),
        "years_observed": round(float(years_obs), 2),
        "t_target": t_target,
        "periods_needed_for_t_target": (round(float(needed_periods), 1)
                                        if needed_periods is not None else None),
        "years_needed_for_t2": (round(float(needed_years), 1)
                                if needed_years is not None else None),
        # `powered` is decided on the UNROUNDED requirement, so at the boundary a
        # receipt can print `years_needed_for_t2 == years_observed` beside
        # `powered: false`. The flag is the correct one; the printed number lost
        # the information to rounding, so the exact value is carried too rather
        # than leaving a reader to reconcile two numbers that look contradictory.
        "years_needed_for_t2_exact": (float(needed_years)
                                      if needed_years is not None else None),
        "powered": (bool(needed_years is not None and needed_years <= years_obs)),
        "reading": reading,
    }


# --------------------------------------------------------------- the one call


def full_report(returns: Sequence[float], *, family: Mapping[str, Sequence[float]] | None = None,
                paired_excess: Mapping[str, Sequence[float]] | None = None,
                n_trials: int | None = None,
                null_sharpes: Sequence[float] | None = None,
                block: float = DEFAULT_BLOCK, n_boot: int = 1000,
                seed: int = 0, periods_per_year: int = 12) -> dict:
    """Every test this module has, on one arm and its family, in one dict.

    Written so a night-lab job cannot quote one of the four and forget the other
    three -- which is how a champion gets published on its own single-cell
    percentile. `n_trials` defaults to the family size; passing it explicitly is
    correct when the search looked at cells it did not keep.
    """
    fam = dict(family or {})
    n_cells = int(n_trials if n_trials is not None else max(1, len(fam) or 1))
    out = {
        "n_cells_looked_at": n_cells,
        "deflated_sharpe": deflated_sharpe(returns, n_trials=n_cells,
                                           null_sharpes=null_sharpes),
        # Beside the Sharpe, never in a different receipt: how much tape a t = 2
        # would have needed. Without it "NOISE" and "UNDERPOWERED" are printed
        # in the same words and read as the same verdict.
        "power": power_note(returns, periods_per_year=periods_per_year),
    }
    if paired_excess:
        out["spa"] = spa(paired_excess, block=block, n_boot=n_boot, seed=seed)
    if fam and len(fam) >= 2:
        lengths = {len(_clean(v)) for v in fam.values()}
        if len(lengths) == 1:
            M = np.column_stack([_clean(v) for v in fam.values()])
            out["pbo"] = pbo(M)
        else:
            out["pbo"] = {"verdict": f"{CANNOT_DETERMINE} (arms have different lengths)"}
    return out
