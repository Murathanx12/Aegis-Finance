"""Sizing on the SIZE of the move: the engine's one demonstrated skill, put to money.

Licence: PRODUCT_EXPERIMENT ($0, no LLM, no broker). The research note is
`docs/research_notes/2026-09-29/sizing_on_move_size_2026-09-29.md`; the runner is
`scripts/sizing_lab.py`; receipts go to `backend/data/optimus/sizing_lab/` with a
run id in every file name.

WHAT IS ESTABLISHED (nn_lab post-review, contest desk): direction is not predictable
by anything tested, but the size of a move is. A ridge on |excess| ranks next
month's |move| at IC 0.358 vs trailing volatility's 0.342, and past earnings-move
size beats trailing volatility for the next earnings move. Nothing used it.

THE QUESTION: with NO view on direction, can a better forecast of move size raise
terminal wealth or log utility? Four routes, each with the same read-out:
inverse-size weights (1), earnings-event avoidance / seeking (2), a fractional-Kelly
risk budget with a FIXED assumed edge (3), and forecast size vs option-implied
size as a straddle-selection paper test (4).

This module holds the pure pieces (forecast, weights, gross, statistics, verdict)
so they are testable offline; the runner owns every file read and write.

THE VERDICT RULE (declared here, in code, before the first run of 2026-09-29).
The objective is LOG UTILITY (mean monthly log(1 + r), i.e. terminal-wealth growth),
read on the sizing variant MINUS its matched twin -- the SAME names on the SAME
calendar sized by the baseline input -- so selection cancels and only the size
input differs:

* ALPHA_DETECTED: mean diff > 0 AND t on non-overlapping date blocks >= 2 AND the
  leave-one-hold-year-out worst mean > 0 AND the diff's alpha after a market
  regression keeps t >= 2.
* BETA_EXPLAINS: mean diff > 0 with t >= 2, but the alpha after regressing the
  diff on the market's monthly return falls below t 2 (the "improvement" is a
  lower or higher market exposure, not a better size read).
* FAILED_VARIANT: mean diff <= 0 and t <= -1 (the variant is measurably worse).
* CANNOT_DISTINGUISH: anything else. Always printed beside the MDE.
"""
from __future__ import annotations

import math
from typing import Iterable, Optional

import numpy as np
import pandas as pd

ALPHA = "ALPHA_DETECTED"
CANNOT = "CANNOT_DISTINGUISH"
BETA = "BETA_EXPLAINS"
FAILED = "FAILED_VARIANT"
VERDICTS = (ALPHA, CANNOT, BETA, FAILED)
#: z for a two-sided 5% test at 80% power: the MDE multiplier the library uses
MDE_Z = 2.8
T_BAR = 2.0
FAIL_T = -1.0

VERDICT_RULE = (
    "objective = log utility (mean monthly log(1+r)); read on variant MINUS its matched twin (same "
    "names, same calendar, baseline size input). ALPHA_DETECTED: mean > 0, t_blocks >= 2, LOYO worst "
    "> 0, and the alpha after regressing the diff on the market keeps t >= 2. BETA_EXPLAINS: mean > 0 "
    "and t_blocks >= 2 but the market-regression alpha has t < 2. FAILED_VARIANT: mean <= 0 and "
    "t_blocks <= -1. CANNOT_DISTINGUISH: otherwise. Declared in backend/services/move_size_sizing.py "
    "before the first run of 2026-09-29.")

# ── risk-budget constants (experiment 3), declared before the run ────────────
#: the FIXED assumed edge of every selected name over cash, per month (6%/yr).
KELLY_MU_MONTHLY = 0.005
#: half Kelly
KELLY_FRACTION = 0.5
#: the assumed average pairwise correlation of the names' monthly returns
KELLY_RHO = 0.30
#: the vol-target variant's annual target (monthly = / sqrt 12)
VOL_TARGET_ANNUAL = 0.15
#: no leverage in any variant
GROSS_CAP = 1.0
#: per-name weight cap for every inverse-size book (renormalised, iterated)
NAME_CAP = 0.10


# ═════════════════════════ the size forecast ═════════════════════════════════

def _transform(panel: pd.DataFrame, spec: dict) -> np.ndarray:
    """spec {column: 'log' | 'abs' | 'abslog' | 'raw'} -> float matrix (rows x features).

    Non-positive inputs to a log become NaN (missing, never zero)."""
    cols = []
    for c, how in spec.items():
        x = pd.to_numeric(panel[c], errors="coerce").to_numpy(dtype=float) if c in panel else \
            np.full(len(panel), np.nan)
        with np.errstate(divide="ignore", invalid="ignore"):
            if how == "log":
                x = np.where(x > 0, np.log(x), np.nan)
            elif how == "abs":
                x = np.abs(x)
            elif how == "abslog":
                x = np.log1p(np.abs(x))
        cols.append(x)
    return np.column_stack(cols) if cols else np.empty((len(panel), 0))


def abs_excess(panel: pd.DataFrame, ret_col: str = "fwd_ret", date_col: str = "date",
               mask_col: Optional[str] = "eligible") -> pd.Series:
    """|forward return minus that date's cross-sectional median| (the median over the
    mask rows). The target a size model is graded on, as nn_lab does."""
    r = pd.to_numeric(panel[ret_col], errors="coerce")
    m = panel[mask_col].astype(bool) if mask_col and mask_col in panel else pd.Series(True, index=panel.index)
    med = r.where(m).groupby(panel[date_col]).transform("median")
    return (r - med).abs()


def _fit_ridge(X: np.ndarray, y: np.ndarray, alpha: float) -> tuple:
    mu = np.nanmean(X, axis=0)
    X = np.where(np.isfinite(X), X, mu)
    sd = X.std(axis=0)
    sd = np.where(sd > 0, sd, 1.0)
    Z = (X - mu) / sd
    ym = float(y.mean())
    A = Z.T @ Z + alpha * np.eye(Z.shape[1])
    b = np.linalg.solve(A, Z.T @ (y - ym))
    return mu, sd, b, ym


def _predict_ridge(model: tuple, X: np.ndarray) -> np.ndarray:
    mu, sd, b, ym = model
    X = np.where(np.isfinite(X), X, mu)
    return ym + ((X - mu) / sd) @ b


def walk_forward_size(panel: pd.DataFrame, spec: dict, *, target: str, date_col: str = "date",
                      train_mask: Optional[np.ndarray] = None, gap: int = 2, min_train_dates: int = 12,
                      refit_every: int = 1, alpha: float = 10.0, winsor: float = 0.99,
                      floor_quantile: float = 0.01) -> tuple[pd.Series, list]:
    """Walk-forward ridge forecast of `target` (a size, >= 0), one refit per `refit_every`
    decision dates, trained ONLY on dates whose target window had closed by the decision:
    at date index j the training dates are 0 .. j - gap.

    `gap` = 2 for a monthly panel whose forward return of date s ends at the ENTRY
    after date s+1 (the open after the next decision): s = j-1 is not known at j's close.

    The target is winsorised at `winsor` on the training rows; predictions are floored at
    the training target's `floor_quantile` (a size forecast is never <= 0, so 1/size is
    defined). Returns (forecast Series on panel.index, fit log)."""
    dates = np.sort(pd.unique(panel[date_col]))
    di = np.searchsorted(dates, panel[date_col].to_numpy())
    X = _transform(panel, spec)
    y = pd.to_numeric(panel[target], errors="coerce").to_numpy(dtype=float)
    tm = np.ones(len(panel), dtype=bool) if train_mask is None else np.asarray(train_mask, dtype=bool)
    out = np.full(len(panel), np.nan)
    log = []
    model = None
    floor = None
    for j in range(len(dates)):
        last_train = j - gap
        if last_train + 1 < min_train_dates:
            continue
        if model is None or (j % refit_every == 0):
            tr = tm & (di <= last_train) & np.isfinite(y)
            ok_x = np.isfinite(X[tr]).any(axis=1)
            Xt, yt = X[tr][ok_x], y[tr][ok_x]
            if len(yt) < 200:
                continue
            cap = float(np.quantile(yt, winsor))
            yt = np.minimum(yt, cap)
            model = _fit_ridge(Xt, yt, alpha)
            floor = max(float(np.quantile(yt, floor_quantile)), 1e-6)
            log.append({"decision": str(pd.Timestamp(dates[j]).date()),
                        "train_last": str(pd.Timestamp(dates[last_train]).date()),
                        "n_train": int(len(yt)), "coef": [round(float(c), 6) for c in model[2]]})
        rows = di == j
        if rows.any():
            out[rows] = np.maximum(_predict_ridge(model, X[rows]), floor)
    return pd.Series(out, index=panel.index), log


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    """Pairwise-complete Spearman (average ranks), scipy-free."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 3:
        return float("nan")
    ra = pd.Series(a[m]).rank().to_numpy()
    rb = pd.Series(b[m]).rank().to_numpy()
    sa, sb = ra.std(), rb.std()
    if sa == 0 or sb == 0:
        return float("nan")
    return float(np.corrcoef(ra, rb)[0, 1])


def per_date_ic(panel: pd.DataFrame, score: str, target: str, date_col: str = "date",
                mask: Optional[np.ndarray] = None, min_n: int = 30) -> pd.Series:
    """{date: Spearman(score, target)} over the mask rows of each date."""
    df = panel if mask is None else panel.loc[np.asarray(mask, dtype=bool)]
    out = {}
    for d, g in df.groupby(date_col):
        if len(g) >= min_n:
            out[pd.Timestamp(d)] = spearman(g[score].to_numpy(), g[target].to_numpy())
    return pd.Series(out, dtype=float).sort_index()


def calibrate_scale(pred: np.ndarray, realised: np.ndarray) -> float:
    """kappa with sigma = kappa * pred in return units, from MEAN ABSOLUTE values:
    kappa = sqrt(pi/2) * sum|realised| / sum pred (a normal's sigma = sqrt(pi/2) E|x|).

    Mean absolute, not mean square: on 2026-09-29 the mean-square version gave trailing
    vol a kappa of 0.069 against a naive sqrt(21/252) = 0.289, because a few vol_63
    outliers dominate the squares. The SAME formula is applied to every input."""
    p = np.asarray(pred, dtype=float)
    r = np.asarray(realised, dtype=float)
    m = np.isfinite(p) & np.isfinite(r) & (p > 0)
    if m.sum() < 30:
        return float("nan")
    return float(math.sqrt(math.pi / 2.0) * np.abs(r[m]).sum() / p[m].sum())


def quantile_map(panel: pd.DataFrame, src: str, ref: str, mask: np.ndarray, date_col: str = "date") -> pd.Series:
    """Per date, give each row the value of `ref` at the same rank that the row holds in
    `src` (among mask rows with both finite). The mapped column has EXACTLY `ref`'s
    per-date distribution, so a book sized on it differs from one sized on `ref` only in
    which name gets which size: ranking skill with dispersion held equal."""
    out = np.full(len(panel), np.nan)
    a = panel[src].to_numpy(dtype=float)
    b = panel[ref].to_numpy(dtype=float)
    ok = np.asarray(mask, dtype=bool) & np.isfinite(a) & np.isfinite(b)
    idx_all = np.where(ok)[0]
    dates = panel[date_col].to_numpy()[idx_all]
    for d in pd.unique(dates):
        idx = idx_all[dates == d]
        order = np.argsort(a[idx], kind="mergesort")
        out[idx[order]] = np.sort(b[idx])
    return pd.Series(out, index=panel.index)


# ═════════════════════════ weights and gross ═════════════════════════════════

def capped_normalise(w: np.ndarray, cap: float = NAME_CAP, max_iter: int = 50) -> np.ndarray:
    """w >= 0 -> sum 1 with no weight above `cap` (excess spread pro rata over the rest).
    A cap below 1/n is infeasible and refuses."""
    w = np.asarray(w, dtype=float).copy()
    n = len(w)
    if n == 0:
        return w
    if cap * n < 1.0 - 1e-12:
        raise ValueError(f"cap {cap} infeasible for {n} names (needs >= {1.0 / n:.4f})")
    w = np.where(np.isfinite(w) & (w > 0), w, 0.0)
    if w.sum() <= 0:
        return np.full(n, 1.0 / n)
    w = w / w.sum()
    for _ in range(max_iter):
        over = w > cap + 1e-12
        if not over.any():
            break
        excess = float((w[over] - cap).sum())
        w[over] = cap
        free = ~over & (w < cap - 1e-12)
        if not free.any() or w[free].sum() <= 0:
            break
        w[free] += excess * w[free] / w[free].sum()
    return w


def inverse_size_weights(size: np.ndarray, power: float = 1.0, cap: float = NAME_CAP) -> np.ndarray:
    """w_i proportional to 1 / size_i^power, capped. A missing size takes the median of the
    finite ones (the name is kept, at an average weight -- never dropped, never zeroed)."""
    s = np.asarray(size, dtype=float)
    ok = np.isfinite(s) & (s > 0)
    if not ok.any():
        return np.full(len(s), 1.0 / max(len(s), 1))
    s = np.where(ok, s, np.median(s[ok]))
    return capped_normalise(1.0 / s ** power, cap=cap)


def portfolio_sigma(w: np.ndarray, sigma: np.ndarray, rho: float = KELLY_RHO) -> float:
    """sqrt((1 - rho) * sum w^2 s^2 + rho * (sum w s)^2): the constant-correlation model."""
    w = np.asarray(w, dtype=float)
    s = np.asarray(sigma, dtype=float)
    v = (1.0 - rho) * float(np.sum(w ** 2 * s ** 2)) + rho * float(np.sum(w * s)) ** 2
    return math.sqrt(max(v, 0.0))


def kelly_gross(w: np.ndarray, sigma: np.ndarray, *, mu: float = KELLY_MU_MONTHLY,
                fraction: float = KELLY_FRACTION, rho: float = KELLY_RHO,
                cap: float = GROSS_CAP) -> float:
    """Gross exposure g = min(cap, fraction * mu / sigma_p^2): a fixed assumed edge, so the
    ONLY input that moves g is the variance forecast."""
    sp = portfolio_sigma(w, sigma, rho)
    if not np.isfinite(sp) or sp <= 0:
        return float("nan")
    return float(min(cap, fraction * mu / sp ** 2))


def vol_target_gross(w: np.ndarray, sigma: np.ndarray, *, target_monthly: float =
                     VOL_TARGET_ANNUAL / math.sqrt(12.0), rho: float = KELLY_RHO,
                     cap: float = GROSS_CAP) -> float:
    """g = min(cap, target / sigma_p)."""
    sp = portfolio_sigma(w, sigma, rho)
    if not np.isfinite(sp) or sp <= 0:
        return float("nan")
    return float(min(cap, target_monthly / sp))


# ═════════════════════════ statistics ════════════════════════════════════════

def hold_years(index) -> np.ndarray:
    """The year each monthly period's money was HELD (entry = decision + 1 business day)."""
    return np.asarray((pd.DatetimeIndex(index) + pd.offsets.BDay(1)).year)


def block_stats(diff: pd.Series, block_len: int = 3) -> dict:
    """Mean monthly diff and its t / SE / MDE on non-overlapping `block_len`-month blocks
    (block value = the SUM of its months; monthly SE = block SE / mean block length)."""
    d = pd.Series(diff, dtype=float).dropna()
    n = len(d)
    out = {"n_months": int(n), "mean_monthly": float(d.mean()) if n else None, "n_blocks": 0,
           "t_blocks": None, "se_monthly": None, "mde_monthly": None}
    if n < 2:
        return out
    b = np.arange(n) // block_len
    sums = d.groupby(b).sum()
    lens = d.groupby(b).size()
    nb = len(sums)
    out["n_blocks"] = int(nb)
    if nb > 2:
        sb = float(sums.std(ddof=1))
        if sb > 0:
            se_b = sb / math.sqrt(nb)
            out["t_blocks"] = float(sums.mean() / se_b)
            out["se_monthly"] = se_b / float(lens.mean())
            out["mde_monthly"] = MDE_Z * out["se_monthly"]
    return out


def by_hold_year(diff: pd.Series) -> dict:
    s = pd.Series(diff, dtype=float)
    yrs = hold_years(s.index)
    out = {}
    for y in sorted(set(yrs.tolist())):
        v = s[yrs == y].dropna()
        out[str(int(y))] = {"sum": float(v.sum()), "mean": float(v.mean()) if len(v) else None,
                            "n_months": int(len(v))}
    return out


def loo_worst(diff: pd.Series) -> dict:
    s = pd.Series(diff, dtype=float)
    yrs = hold_years(s.index)
    loo = {}
    for y in sorted(set(yrs.tolist())):
        v = s[yrs != y].dropna()
        if len(v) > 1:
            loo[str(int(y))] = float(v.mean())
    if not loo:
        return {"worst": None, "dropped_year": None, "all": {}}
    k = min(loo, key=loo.get)
    return {"worst": loo[k], "dropped_year": k, "all": loo}


def carried_by(diff: pd.Series, n: int = 5) -> dict:
    """Which part of the sample carries the mean: the n best hold months, their share of
    the total, and the mean without them."""
    s = pd.Series(diff, dtype=float).dropna()
    if not len(s):
        return {"best_months": [], "share_of_total": None, "mean_without_best": None}
    hm = (pd.DatetimeIndex(s.index) + pd.offsets.BDay(1)).to_period("M").astype(str)
    order = np.argsort(-s.to_numpy(), kind="mergesort")
    top = order[:n]
    tot = float(s.sum())
    rest = np.delete(s.to_numpy(), top)
    return {"best_months": [str(hm[i]) for i in top],
            "share_of_total": (float(s.to_numpy()[top].sum() / tot) if tot != 0 else None),
            "mean_without_best": float(rest.mean()) if len(rest) else None}


def market_alpha(diff: pd.Series, market: pd.Series, block_len: int = 3) -> dict:
    """OLS diff = a + b * market; a's t on the same non-overlapping blocks (block sums of
    the residual-plus-alpha)."""
    df = pd.concat([pd.Series(diff, dtype=float), pd.Series(market, dtype=float)], axis=1,
                   keys=["d", "m"]).dropna()
    if len(df) < 12:
        return {"n": int(len(df)), "beta": None, "alpha_monthly": None, "t_alpha_blocks": None}
    X = np.c_[np.ones(len(df)), df["m"].to_numpy()]
    coef, *_ = np.linalg.lstsq(X, df["d"].to_numpy(), rcond=None)
    a, b = float(coef[0]), float(coef[1])
    adj = df["d"] - b * df["m"]
    st = block_stats(adj, block_len)
    return {"n": int(len(df)), "beta": b, "alpha_monthly": a, "t_alpha_blocks": st["t_blocks"],
            "mde_alpha_monthly": st["mde_monthly"]}


def book_metrics(r: pd.Series) -> dict:
    """CAGR, annual vol, Sharpe (vs 0: cash is credited 0 everywhere here), max drawdown,
    terminal wealth of $1, and mean monthly log utility."""
    x = pd.Series(r, dtype=float).dropna().to_numpy()
    if not len(x):
        return {"n_months": 0}
    tw = float(np.prod(1.0 + x))
    nav = np.cumprod(1.0 + x)
    peak = np.maximum.accumulate(np.concatenate([[1.0], nav]))[1:]
    sd = float(x.std(ddof=1)) if len(x) > 1 else float("nan")
    return {"n_months": int(len(x)),
            "cagr": (tw ** (12.0 / len(x)) - 1.0) if tw > 0 else -1.0,
            "vol_annual": sd * math.sqrt(12.0),
            "sharpe": (float(x.mean()) / sd * math.sqrt(12.0)) if sd and sd > 0 else None,
            "max_dd": float((nav / peak - 1.0).min()),
            "terminal_wealth": tw,
            "log_utility_monthly": float(np.mean(np.log1p(np.maximum(x, -0.999999))))}


def sharpe_diff_bootstrap(a: pd.Series, b: pd.Series, *, block_len: int = 3, n_boot: int = 2000,
                          seed: int = 20260929) -> dict:
    """Sharpe(a) - Sharpe(b) with a moving-block bootstrap 90% interval (paired months)."""
    df = pd.concat([pd.Series(a, dtype=float), pd.Series(b, dtype=float)], axis=1).dropna()
    x, y = df.iloc[:, 0].to_numpy(), df.iloc[:, 1].to_numpy()
    n = len(x)
    if n < 12:
        return {"diff": None, "lo90": None, "hi90": None}

    def sh(v):
        s = v.std(ddof=1)
        return v.mean() / s * math.sqrt(12.0) if s > 0 else 0.0

    rng = np.random.default_rng(seed)
    nb = int(math.ceil(n / block_len))
    starts_max = n - block_len
    ds = []
    for _ in range(n_boot):
        st = rng.integers(0, starts_max + 1, size=nb)
        idx = (st[:, None] + np.arange(block_len)[None, :]).ravel()[:n]
        ds.append(sh(x[idx]) - sh(y[idx]))
    ds = np.asarray(ds)
    return {"diff": float(sh(x) - sh(y)), "lo90": float(np.quantile(ds, 0.05)),
            "hi90": float(np.quantile(ds, 0.95)), "p_le_0": float((ds <= 0).mean())}


def verdict(stats: dict, loo: dict, alpha: dict) -> str:
    """The declared rule (module docstring) on a log-utility diff."""
    m, t = stats.get("mean_monthly"), stats.get("t_blocks")
    if m is None or t is None:
        return CANNOT
    if m <= 0 and t <= FAIL_T:
        return FAILED
    if m > 0 and t >= T_BAR:
        ta = alpha.get("t_alpha_blocks")
        if ta is None or ta < T_BAR:
            return BETA
        if (loo.get("worst") or -1.0) > 0:
            return ALPHA
    return CANNOT


def _lu(x: pd.Series) -> pd.Series:
    return np.log1p(pd.Series(x, dtype=float).clip(lower=-0.999999))


def report_from_diffs(lu: pd.Series, raw: pd.Series, market: Optional[pd.Series] = None,
                      block_len: int = 3) -> dict:
    """The protocol read-out of one monthly log-utility diff series (and its raw twin)."""
    lu = pd.Series(lu, dtype=float).dropna()
    st = block_stats(lu, block_len)
    loo = loo_worst(lu)
    al = (market_alpha(lu, market.reindex(lu.index), block_len) if market is not None
          else {"t_alpha_blocks": None, "note": "no market series"})
    v = verdict(st, loo, al if market is not None else {"t_alpha_blocks": st.get("t_blocks")})
    return {"objective": "log utility: mean monthly log(1+r_variant) - log(1+r_twin)",
            "span": [str(lu.index.min().date()), str(lu.index.max().date())] if len(lu) else None,
            "log_utility_diff": st, "raw_return_diff": block_stats(pd.Series(raw, dtype=float).dropna(),
                                                                    block_len),
            "by_hold_year": by_hold_year(lu), "loo": loo, "carried_by": carried_by(lu),
            "market_alpha": al, "verdict": v}


def diff_report(variant: pd.Series, twin: pd.Series, market: Optional[pd.Series] = None,
                block_len: int = 3) -> dict:
    """Everything the protocol owes one comparison: by hold year, LOYO worst, block SE / t /
    MDE, which months carry it, the market alpha, the Sharpe difference, both books'
    metrics, and the verdict on log utility."""
    df = pd.concat([pd.Series(variant, dtype=float), pd.Series(twin, dtype=float)], axis=1,
                   keys=["v", "t"]).dropna()
    rep = report_from_diffs(_lu(df["v"]) - _lu(df["t"]), df["v"] - df["t"], market, block_len)
    rep["sharpe_diff"] = sharpe_diff_bootstrap(df["v"], df["t"], block_len=block_len)
    rep["variant"] = book_metrics(df["v"])
    rep["twin"] = book_metrics(df["t"])
    return rep


def seed_diff_report(variant: dict, twin: dict, market: Optional[pd.Series] = None,
                     block_len: int = 3) -> dict:
    """The random-control version: {seed: monthly net} for variant and twin, same seeds.
    The diff is taken WITHIN each seed (same names) and averaged across seeds month by
    month; each seed's books are also scored on their own and summarised."""
    lus, raws, per = [], [], []
    for sd in sorted(set(variant) & set(twin)):
        df = pd.concat([variant[sd], twin[sd]], axis=1, keys=["v", "t"]).dropna()
        lus.append(_lu(df["v"]) - _lu(df["t"]))
        raws.append(df["v"] - df["t"])
        mv, mt = book_metrics(df["v"]), book_metrics(df["t"])
        per.append({"seed": sd, "tw_v": mv["terminal_wealth"], "tw_t": mt["terminal_wealth"],
                    "sh_v": mv["sharpe"], "sh_t": mt["sharpe"], "dd_v": mv["max_dd"], "dd_t": mt["max_dd"],
                    "lu_v": mv["log_utility_monthly"], "lu_t": mt["log_utility_monthly"]})
    if not lus:
        return {"status": "REFUSED", "why": "no common seeds"}
    lu = pd.concat(lus, axis=1).mean(axis=1)
    raw = pd.concat(raws, axis=1).mean(axis=1)
    rep = report_from_diffs(lu, raw, market, block_len)
    P = pd.DataFrame(per)
    rep["n_seeds"] = int(len(P))
    rep["seeds_variant_beats_twin_terminal_wealth"] = int((P["tw_v"] > P["tw_t"]).sum())
    rep["median_over_seeds"] = {c: float(P[c].median()) for c in P.columns if c != "seed"}
    return rep


# ═════════════════════════ worst case, in dollars ════════════════════════════

def worst_case_dollars(*, equity: float, n_names: int, name_cap: float, gross: float,
                       sigma_monthly: Optional[Iterable[float]] = None,
                       weights: Optional[Iterable[float]] = None, stop_sigma: Optional[float] = None,
                       k_sigma: float = 3.0) -> dict:
    """The CLAUDE.md protocol-4 print, for the largest admissible book.

    Without a stop the worst case of a long-only name is its whole notional (to zero).
    With a stop at `stop_sigma` monthly sigmas, a name's stop loss is w * stop_sigma * s
    (gaps through a stop are NOT modelled -- the no-stop line is the honest bound).
    `k_sigma` prints the k-sigma one-month adverse move of the actual book."""
    out = {"equity": float(equity), "n_names": int(n_names), "name_cap": float(name_cap),
           "gross_over_equity": float(gross),
           "max_notional_per_name": float(equity * name_cap),
           "worst_single_name_to_zero": -float(equity * name_cap),
           "worst_all_names_to_zero": -float(equity * gross),
           "n_x_notional_x_stop": None, "stop": "none (hold to rebalance)"}
    if stop_sigma is not None and sigma_monthly is not None and weights is not None:
        w = np.asarray(list(weights), dtype=float)
        s = np.asarray(list(sigma_monthly), dtype=float)
        out["stop"] = f"{stop_sigma:g} monthly sigma"
        out["n_x_notional_x_stop"] = -float(equity * gross * np.sum(w * stop_sigma * s))
    if sigma_monthly is not None and weights is not None:
        w = np.asarray(list(weights), dtype=float)
        s = np.asarray(list(sigma_monthly), dtype=float)
        per = equity * gross * w * k_sigma * s
        out[f"{k_sigma:g}_sigma_one_month_loss_per_name_max"] = -float(per.max())
        out[f"{k_sigma:g}_sigma_one_month_loss_per_name_median"] = -float(np.median(per))
        out[f"{k_sigma:g}_sigma_one_month_loss_all_names_same_sign"] = -float(per.sum())
    return out


def book_fingerprint(obj) -> str:
    import hashlib
    import json
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]



# ═════════════════════════ the book engine ═══════════════════════════════════

def band_round_trip_bps(mdv: float, costs: dict) -> float:
    """The library's band toll (strategy_library._band_rt), round trip in bps."""
    if mdv is None or not np.isfinite(mdv):
        return costs["small"]
    if mdv >= 1e9:
        return costs["mega"]
    if mdv >= 1e8:
        return costs["large"]
    if mdv >= 2e7:
        return costs["mid"]
    return costs["small"]


def run_book(panel: pd.DataFrame, scores: np.ndarray, *, k: int, costs: dict,
             rebalance_months: Optional[Iterable[int]] = None, hold_months: int = 1,
             weight_fn=None, gross_fn=None, start_date=None, keep_holdings: bool = False,
             fwd: Optional[np.ndarray] = None) -> pd.DataFrame:
    """Monthly NAV of a top-k book, net of band costs -- `strategy_library.run_strategy`'s
    conventions (weights held constant between rebalances and drift not charged; a held
    name with no row later sits in cash; each weight bought or sold pays half its band
    round trip; cash earns 0), with two hooks it lacks:

    * `weight_fn(idx) -> weights summing to 1` over the selected panel rows `idx`
      (default equal);
    * `gross_fn(idx, w) -> g in [0, 1]`: the invested share; the rest is cash at 0;
    * `fwd`: an override of the forward-return column (e.g. an earnings window sat out).

    `panel` needs date, symbol, fwd_ret, median_dollar_vol and optionally tiebreak.
    `scores`: NaN = not selectable. Selection = top k by score, ties broken by
    `tiebreak` (ascending), exactly the library's lexsort.

    Refuses zero costs: `costs` must be the band toll (every band > 0)."""
    if not costs or min(float(v) for v in costs.values()) <= 0:
        raise ValueError("run_book refuses zero costs: pass the band toll (every band > 0)")
    dates = np.sort(pd.unique(panel["date"]))
    di = np.searchsorted(dates, panel["date"].to_numpy())
    order = np.argsort(di, kind="stable")
    bounds = np.searchsorted(di[order], np.arange(len(dates) + 1))
    fwd = (pd.to_numeric(panel["fwd_ret"], errors="coerce").to_numpy(dtype=float) if fwd is None
           else np.asarray(fwd, dtype=float))
    mdv = pd.to_numeric(panel["median_dollar_vol"], errors="coerce").to_numpy(dtype=float)
    sym = panel["symbol"].astype(str).to_numpy()
    scv = np.asarray(scores, dtype=float)
    tb = (panel["tiebreak"].to_numpy(dtype=float) if "tiebreak" in panel
          else np.zeros(len(panel)))
    rmonths = set(rebalance_months or ())
    start_ts = pd.Timestamp(start_date) if start_date is not None else None
    rows, hold_log = [], []
    held: dict = {}
    held_rt: dict = {}
    start = None
    for j, d in enumerate(dates):
        if start_ts is not None and pd.Timestamp(d) < start_ts:
            continue
        idx = order[bounds[j]:bounds[j + 1]]
        if not len(idx) or not np.isfinite(fwd[idx]).any():
            continue
        cand = idx[np.isfinite(scv[idx])]
        on_cal = (pd.Timestamp(d).month in rmonths) if rmonths else None
        rebalance = False
        if start is None:
            if len(cand) < k or on_cal is False:
                continue
            start, rebalance = j, True
        elif (on_cal if rmonths else (j - start) % hold_months == 0) and len(cand) >= k:
            rebalance = True
        cost = turnover = 0.0
        g = None
        if rebalance:
            top = cand[np.lexsort((tb[cand], -scv[cand]))[:k]]
            w = np.full(len(top), 1.0 / len(top)) if weight_fn is None else np.asarray(weight_fn(top), float)
            g = 1.0 if gross_fn is None else float(gross_fn(top, w))
            if not np.isfinite(g):
                g = 1.0
            g = min(max(g, 0.0), 1.0)
            new = {sym[t]: float(g * w_) for t, w_ in zip(top, w)}
            new_rt = {sym[t]: band_round_trip_bps(mdv[t], costs) for t in top}
            for s_, w_ in new.items():
                dw = w_ - held.get(s_, 0.0)
                if dw > 0:
                    cost += dw * new_rt[s_] / 2.0
                    turnover += dw
            for s_, w_ in held.items():
                dw = w_ - new.get(s_, 0.0)
                if dw > 0:
                    cost += dw * held_rt.get(s_, costs["small"]) / 2.0
            held, held_rt = new, new_rt
            if keep_holdings:
                hold_log.append({"date": pd.Timestamp(d), "idx": top.tolist(), "w": list(w), "g": g})
        cost /= 1e4
        pos = {sym[t]: t for t in idx}
        gross = 0.0
        for s_, w_ in held.items():
            t = pos.get(s_)
            r = fwd[t] if t is not None else np.nan
            gross += w_ * (float(r) if np.isfinite(r) else 0.0)
        rows.append({"date": pd.Timestamp(d), "gross": gross, "cost": cost, "net": gross - cost,
                     "turnover": turnover, "invested": float(sum(held.values())),
                     "n_held": len(held), "rebalanced": rebalance})
    out = pd.DataFrame(rows, columns=["date", "gross", "cost", "net", "turnover", "invested",
                                      "n_held", "rebalanced"])
    if keep_holdings:
        out.attrs["holdings"] = hold_log
    return out


def tranche(series: dict) -> pd.Series:
    """One third in each quarterly offset's book: the month-by-month mean over the
    offsets' common months (the calendar-neutral book)."""
    common = None
    for s in series.values():
        common = s.index if common is None else common.intersection(s.index)
    common = pd.DatetimeIndex(sorted(common))
    return pd.concat([s.reindex(common) for s in series.values()], axis=1).mean(axis=1)
