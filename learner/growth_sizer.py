"""THE NN'S JOB IN THE GROWTH BOOK — sizing, not selection.

`ROADMAP_2026-09-07_GROWTH_BOOK_AMENDMENT.md` §3, "The NN's job in this lane
(the workaround)". Murat's ruling was *"the NN focuses on noise — find a
workaround with the NN and the engine."* The workaround is to stop asking the
network which stocks to buy and ask it **how much of the book to hold**.

WHAT IT FORECASTS
=================
Next month's return DISTRIBUTION of one frozen book — three quantile heads
q05 / q50 / q95, trained with the pinball loss — from market and regime
features only. It never sees a stock, a ranking, or the book's holdings; it
sees the world the book will be held in.

HOW THE FORECAST BECOMES AN EXPOSURE
====================================
Fractional Kelly. `mu = q50 - rf`, and the spread of the quantile pair is read
as a normal scale, `sigma = (q95 - q05) / (2 * 1.6449)`. Then

    exposure = KELLY_FRACTION * mu / sigma^2,  clipped to [0, the budget cap]

The quarter-Kelly fraction is DECLARED, not tuned: a Kelly fraction fitted on
the same development months that fitted the network is a second free parameter
hiding inside a first.

WHAT IT IS GRADED AGAINST, AND HOW
==================================
Moreira-Muir trailing-volatility targeting — the same overlay `growth_lab` calls
`bsc`, exposure = a PIT target vol over the trailing realised vol. That baseline
is not a straw man: it is the published recipe, it uses no learning at all, and
on this repo's own tape it is one of the few overlays that raises
leverage-neutral wealth.

The comparison is made **at equal drawdown**: both sized books are re-levered to
the SAME drawdown budget by `growth.admissible_leverage`, and the terminal
wealths compared at that common risk. Comparing two exposure rules at whatever
risk each happens to run is a comparison of two leverages.

WHAT IT NEVER SEES
==================
2016-2024. `assert_development_only` runs on every arm this module grades, and
the module has no path to `growth_lab.sealed`. The sizer's own sealed-era test
belongs to a later session, after the champion's contract is frozen.

EIGHT SEEDS, AND THE SEED-MEAN IS THE OBJECT JUDGED
===================================================
A3 of the Labor Day lab found the neural family's CPCV champion was an
individual SEED in 15 of 15 partitions and never the seed-mean — i.e. the object
that wins is not the object that can be chosen in advance. So the seed-mean is
what is graded here, every seed is reported beside it as a family cell, and the
DSR deflates by the whole sizer family.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np
import pandas as pd

from learner import growth as GR
from learner import growth_lab as GL

try:                                                        # pragma: no cover
    import torch
    import torch.nn as nn
    _TORCH = True
except Exception:                                           # pragma: no cover
    _TORCH = False

# ------------------------------------------------------------ the declaration
#: quantile heads. Declared, never searched.
QUANTILES = (0.05, 0.50, 0.95)
#: the normal z that turns a 5/95 spread into a scale.
_Z95 = 1.6448536269514722
#: fractional Kelly. Quarter-Kelly, declared. Fitting this on the same months
#: that fitted the network is a second free parameter inside a first.
KELLY_FRACTION = 0.25
#: how many months of features the sequence model sees.
LOOKBACK = 12
#: walk-forward: the first fit needs this many months, then refit every year.
WARMUP_MONTHS = 60
REFIT_EVERY = 12
#: eight seeds, always. The seed-MEAN is the object judged.
SEEDS = tuple(20260907 + i for i in range(8))
HIDDEN = 32
MAX_EPOCHS = 200
PATIENCE = 20
LR = 3e-3
WEIGHT_DECAY = 1e-4
#: exposure bounds before the drawdown budget is applied.
EXPOSURE_MIN, EXPOSURE_MAX = 0.0, GL.GROSS_CAP

FEATURES = (
    "spy_vol_21d", "spy_vol_63d", "spy_dd_12m", "spy_mom_12_1",
    "rf_level_annual", "rf_change_12m",
    "breadth_positive_1m", "dispersion_1m",
    "book_vol_6m", "book_ret_3m", "book_dd_12m",
)

__all__ = [
    "QUANTILES", "KELLY_FRACTION", "LOOKBACK", "WARMUP_MONTHS", "REFIT_EVERY",
    "SEEDS", "FEATURES", "EXPOSURE_MIN", "EXPOSURE_MAX",
    "regime_features", "kelly_exposure", "trailing_vol_exposure",
    "apply_exposure", "walk_forward_quantiles", "compare_at_equal_drawdown",
    "torch_available", "describe",
]


def torch_available() -> bool:
    return _TORCH


def describe() -> dict:
    return {
        "role": "SIZING, never selection",
        "target": "next-month return distribution of ONE frozen book",
        "quantiles": list(QUANTILES),
        "loss": "pinball (quantile) loss, three heads",
        "exposure_rule": (f"fractional Kelly at {KELLY_FRACTION}: "
                          "mu = q50 - rf, sigma = (q95 - q05) / (2 * 1.6449), "
                          f"exposure = f * mu / sigma^2 clipped to "
                          f"[{EXPOSURE_MIN}, {EXPOSURE_MAX}] and then to the "
                          "drawdown budget"),
        "baseline": ("Moreira-Muir trailing-volatility targeting -- a PIT target "
                     "vol over trailing realised vol, no learning"),
        "comparison": ("after-cost terminal wealth AT EQUAL DRAWDOWN: both books "
                       "re-levered to the same budget by "
                       "growth.admissible_leverage before their wealths are "
                       "compared"),
        "seeds": list(SEEDS),
        "object_judged": "the seed-MEAN forecast; every seed is a family cell",
        "features": list(FEATURES),
        "sealed_era": "NEVER SEEN. This module has no path to growth_lab.sealed.",
        "torch_available": _TORCH,
    }


# ----------------------------------------------------------------- features

def regime_features(ctx: pd.DataFrame, book: pd.Series,
                    panel: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Market and regime state, every column OBSERVABLE AT ENTRY of the month.

    Nothing here is a function of the month's own outcome. `ctx["spy"]` and
    `ctx["rf"]` ARE outcomes, so where they are used at all they are SHIFTED --
    a feature that reads the month it is sizing is the single most profitable
    bug available in this file, and it does not announce itself.
    """
    idx = pd.Index([str(x) for x in ctx.index], name="month")
    f = pd.DataFrame(index=idx)
    f["spy_vol_21d"] = ctx["spy_vol_21d"].to_numpy()             # read at entry
    spy = pd.Series(ctx["spy"].to_numpy(), index=idx)
    rf = pd.Series(ctx["rf"].to_numpy(), index=idx)
    f["spy_vol_63d"] = (spy.rolling(3, min_periods=3).std(ddof=1)
                        * math.sqrt(12)).shift(1)
    w = (1.0 + spy.fillna(0.0)).cumprod()
    f["spy_dd_12m"] = (w / w.rolling(12, min_periods=1).max() - 1.0).shift(1)
    f["spy_mom_12_1"] = ((1.0 + spy.fillna(0.0)).rolling(11).apply(
        np.prod, raw=True) - 1.0).shift(2)
    f["rf_level_annual"] = (rf * 12.0).shift(1)
    f["rf_change_12m"] = f["rf_level_annual"].diff(12)

    if panel is not None and "ret_1m" in panel.columns:
        # BREADTH AND DISPERSION FROM THE PANEL'S OWN TRAILING COLUMN.
        # `ret_1m` is the return over the month BEFORE entry -- it is a feature
        # in the panel, not a target -- so no shift is applied and none is
        # needed. `fwd_1m` would have been the outcome and is never touched.
        p = panel[["month", "ret_1m"]].dropna()
        g = p.groupby(p["month"].astype(str))["ret_1m"]
        f["breadth_positive_1m"] = g.apply(lambda s: float((s > 0).mean())).reindex(idx)
        f["dispersion_1m"] = g.std(ddof=1).reindex(idx)
    else:
        f["breadth_positive_1m"] = np.nan
        f["dispersion_1m"] = np.nan

    b = pd.Series(book.to_numpy(), index=pd.Index([str(x) for x in book.index]))
    b = b.reindex(idx)
    f["book_vol_6m"] = (b.rolling(6, min_periods=6).std(ddof=1) * math.sqrt(12)).shift(1)
    f["book_ret_3m"] = ((1.0 + b.fillna(0.0)).rolling(3).apply(np.prod, raw=True)
                        - 1.0).shift(1)
    bw = (1.0 + b.fillna(0.0)).cumprod()
    f["book_dd_12m"] = (bw / bw.rolling(12, min_periods=1).max() - 1.0).shift(1)
    return f[list(FEATURES)]


# ----------------------------------------------------------------- the model

if _TORCH:                                                   # pragma: no cover

    class QuantileGRU(nn.Module):
        """A small GRU over `LOOKBACK` months of regime features, three heads.

        Small on purpose: 202 development months is not a sequence-modelling
        dataset, and a network with more parameters than months would be
        measuring its own initialisation.
        """

        def __init__(self, n_features: int, hidden: int = HIDDEN):
            super().__init__()
            self.gru = nn.GRU(n_features, hidden, batch_first=True)
            self.head = nn.Linear(hidden, len(QUANTILES))

        def forward(self, x):
            out, _ = self.gru(x)
            return self.head(out[:, -1, :])


def _pinball(pred, target):                                  # pragma: no cover
    q = torch.tensor(QUANTILES, dtype=pred.dtype, device=pred.device)
    e = target.unsqueeze(1) - pred
    return torch.maximum(q * e, (q - 1.0) * e).mean()


def _windows(F: np.ndarray, y: np.ndarray, lookback: int):
    """(n, lookback, k) sequences ending at t, predicting y[t]."""
    X, Y, ends = [], [], []
    for t in range(lookback - 1, len(F)):
        w = F[t - lookback + 1:t + 1]
        if not np.isfinite(w).all() or not np.isfinite(y[t]):
            continue
        X.append(w)
        Y.append(y[t])
        ends.append(t)
    if not X:
        return (np.empty((0, lookback, F.shape[1])), np.empty(0),
                np.empty(0, dtype="int64"))
    return np.stack(X), np.asarray(Y), np.asarray(ends, dtype="int64")


def walk_forward_quantiles(features: pd.DataFrame, book: pd.Series, *,
                           seeds: Sequence[int] = SEEDS,
                           lookback: int = LOOKBACK,
                           warmup: int = WARMUP_MONTHS,
                           refit_every: int = REFIT_EVERY,
                           device=None, verbose: bool = False) -> dict:
    """Expanding-window walk-forward quantile forecasts. One frame per seed.

    The scaler is fitted on the TRAINING rows of each fold and applied to the
    test rows; fitting it on everything is the leak that survives every other
    guard because it moves no dates.
    """
    if not _TORCH:
        raise RuntimeError("REFUSED: torch is not importable, and this module "
                           "will not substitute a different model class under a "
                           "neural heading.")
    idx = [str(x) for x in features.index]
    F = features.to_numpy(dtype="float64")
    y = pd.Series(book.to_numpy(),
                  index=pd.Index([str(x) for x in book.index])).reindex(idx).to_numpy()
    dev = device or torch.device("cpu")

    out = {s: pd.DataFrame(index=pd.Index(idx, name="month"),
                           columns=[f"q{int(q*100):02d}" for q in QUANTILES],
                           dtype="float64") for s in seeds}
    folds = []
    for cut in range(warmup, len(idx), refit_every):
        tr_end = cut
        te = list(range(cut, min(cut + refit_every, len(idx))))
        if not te:
            continue
        Xtr, Ytr, _ = _windows(F[:tr_end], y[:tr_end], lookback)
        if len(Xtr) < 24:
            continue
        mu, sd = Xtr.reshape(-1, F.shape[1]).mean(0), Xtr.reshape(-1, F.shape[1]).std(0)
        sd = np.where(sd > 0, sd, 1.0)
        Xtr_s = (Xtr - mu) / sd
        n_val = max(6, int(0.2 * len(Xtr)))
        fit, val = slice(0, len(Xtr) - n_val), slice(len(Xtr) - n_val, len(Xtr))

        Xte, ends = [], []
        for t in te:
            if t - lookback + 1 < 0:
                continue
            w = F[t - lookback + 1:t + 1]
            if not np.isfinite(w).all():
                continue
            Xte.append((w - mu) / sd)
            ends.append(t)
        if not Xte:
            continue
        Xte = np.stack(Xte)
        folds.append({"train_months": [idx[0], idx[tr_end - 1]],
                      "test_months": [idx[ends[0]], idx[ends[-1]]],
                      "n_train_windows": int(len(Xtr)),
                      "n_test_months": int(len(ends))})

        for seed in seeds:
            torch.manual_seed(int(seed))
            net = QuantileGRU(F.shape[1]).to(dev)
            opt = torch.optim.AdamW(net.parameters(), lr=LR,
                                    weight_decay=WEIGHT_DECAY)
            xt = torch.tensor(Xtr_s[fit], dtype=torch.float32, device=dev)
            yt = torch.tensor(Ytr[fit], dtype=torch.float32, device=dev)
            xv = torch.tensor(Xtr_s[val], dtype=torch.float32, device=dev)
            yv = torch.tensor(Ytr[val], dtype=torch.float32, device=dev)
            best, best_state, bad = float("inf"), None, 0
            for _ep in range(MAX_EPOCHS):
                net.train(True)
                opt.zero_grad()
                loss = _pinball(net(xt), yt)
                loss.backward()
                opt.step()
                net.train(False)
                with torch.no_grad():
                    v = float(_pinball(net(xv), yv))
                if v < best - 1e-6:
                    best, bad = v, 0
                    best_state = {k: t.detach().clone()
                                  for k, t in net.state_dict().items()}
                else:
                    bad += 1
                    if bad >= PATIENCE:
                        break
            if best_state is not None:
                net.load_state_dict(best_state)
            net.train(False)
            with torch.no_grad():
                p = net(torch.tensor(Xte, dtype=torch.float32,
                                     device=dev)).cpu().numpy()
            # the three heads are not guaranteed monotone by construction; a
            # crossed quantile pair would give a NEGATIVE sigma and an exposure
            # with the wrong sign. Sorting is the standard repair and it is
            # recorded rather than assumed.
            p = np.sort(p, axis=1)
            for r, t in enumerate(ends):
                out[seed].iloc[t] = p[r]
    return {"per_seed": out, "folds": folds,
            "seed_mean": _seed_mean(out),
            "quantile_crossing_repair": "rows sorted across the three heads"}


def _seed_mean(per_seed: dict) -> pd.DataFrame:
    frames = list(per_seed.values())
    acc = frames[0].copy() * 0.0
    n = acc.copy() * 0.0
    for f in frames:
        acc = acc.add(f.fillna(0.0), fill_value=0.0)
        n = n.add(f.notna().astype(float), fill_value=0.0)
    return acc.div(n.where(n > 0))


# ---------------------------------------------------------------- exposures

def kelly_exposure(q: pd.DataFrame, rf: pd.Series, *,
                   fraction: float = KELLY_FRACTION,
                   lo: float = EXPOSURE_MIN, hi: float = EXPOSURE_MAX) -> pd.Series:
    """Fractional Kelly from a quantile forecast. Never negative, never > cap."""
    idx = pd.Index([str(x) for x in q.index])
    r = pd.Series(rf.to_numpy(),
                  index=pd.Index([str(x) for x in rf.index])).reindex(idx).fillna(0.0)
    mu = q["q50"].to_numpy() - r.to_numpy()
    sigma = (q["q95"].to_numpy() - q["q05"].to_numpy()) / (2.0 * _Z95)
    with np.errstate(divide="ignore", invalid="ignore"):
        e = fraction * mu / np.square(sigma)
    e = np.where(np.isfinite(e), e, np.nan)
    return pd.Series(np.clip(e, lo, hi), index=idx)


def trailing_vol_exposure(book: pd.Series, *, lookback: int = 6,
                          min_history: int = 24,
                          lo: float = EXPOSURE_MIN,
                          hi: float = EXPOSURE_MAX) -> pd.Series:
    """The Moreira-Muir baseline. PIT target, no learning, no free parameter."""
    b = pd.Series(book.to_numpy(), index=pd.Index([str(x) for x in book.index]))
    v = (b.rolling(lookback, min_periods=lookback).std(ddof=1)
         * math.sqrt(12)).shift(1)
    tgt = v.expanding(min_periods=min_history).median()
    return (tgt / v).clip(lo, hi)


def apply_exposure(book: pd.Series, rf: pd.Series, exposure: pd.Series, *,
                   cost_bps: float,
                   financing_bps: float = GL.FINANCING_BPS) -> tuple[pd.Series, dict]:
    """Run the book at `exposure`, paying financing and the spread. Warm-up = 1.

    A month with no forecast is held at exposure 1.0 rather than dropped: an
    exposure rule that quietly sits out its own warm-up is being graded on a
    shorter, later window than its baseline.
    """
    idx = pd.Index([str(x) for x in book.index])
    b = pd.Series(book.to_numpy(), index=idx)
    e = pd.Series(exposure.to_numpy(),
                  index=pd.Index([str(x) for x in exposure.index])).reindex(idx)
    n_missing = int(e.isna().sum())
    e = e.fillna(1.0)
    r = pd.Series(rf.to_numpy(),
                  index=pd.Index([str(x) for x in rf.index])).reindex(idx).fillna(0.0)
    net, meta = GL._exposure_return(b, r, e, cost_bps=cost_bps,
                                    financing_bps=financing_bps)
    meta["months_held_at_exposure_1_for_want_of_a_forecast"] = n_missing
    return net, meta


# -------------------------------------------------------------- the compare

def compare_at_equal_drawdown(arms: dict, spy: pd.Series, rf: pd.Series, *,
                              cost_bps: float) -> dict:
    """Every arm re-levered to the SAME drawdown budget, then compared.

    Two exposure rules run at whatever risk each happens to produce are not
    comparable on terminal wealth; that comparison is between two leverages.
    `growth.admissible_leverage` puts both on the budget first.
    """
    rows = {}
    for name, s in arms.items():
        GL.assert_development_only(s, f"sizer arm {name}")
        ev = GR.evaluate_growth(s, spy, rf, cost_bps=cost_bps, label=name,
                                n_boot=500)
        adm = ev.get("largest_admissible") or {}
        rows[name] = {
            "beta": ev.get("beta"),
            "intercept_annual_pct": (ev.get("market_model") or {}).get("intercept_annualised_pct"),
            "intercept_t_hac": (ev.get("market_model") or {}).get("intercept_t_hac"),
            "tw_unlevered": (ev.get("book") or {}).get("terminal_wealth"),
            "maxdd_unlevered": (ev.get("book") or {}).get("max_drawdown"),
            "leverage_at_budget": adm.get("leverage"),
            "tw_at_budget": adm.get("terminal_wealth"),
            "maxdd_at_budget": adm.get("max_drawdown"),
            "leverage_neutral_tw": (ev.get("leverage_neutral") or {}).get("terminal_wealth"),
            "realized_vol": (ev.get("book") or {}).get("realized_vol_annual"),
            "constraints_pass": (ev.get("constraints") or {}).get("passes"),
            "months": ev.get("months"),
            "cost_bps_per_side": cost_bps,
        }
    return rows
