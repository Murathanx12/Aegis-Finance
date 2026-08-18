"""AEGIS-NET-TOURNAMENT-1 — the harness. It refuses to run unsigned.

Order 20 §3: "Deliverable is a scoreboard, not a module. Draft the tournament
pre-registration now; it runs only after Murat signs (canon §6)."

This module is the machinery that will produce the scoreboard: five frozen
arms, walk-forward folds with a 2H embargo (`world_model.walk_forward_folds`),
paired differences with date-block bootstrap (`block_bootstrap_paired` — the
unit is the DATE BLOCK, §58), and the competing-risks barrier formulation
(adjudication A5) as a baseline family beside the classifiers.

THE GATE IS IN CODE, NOT IN PROSE
=================================
`assert_signed()` reads the pre-registration and refuses unless a line
`SIGNED-BY:` names a human. Every entry point that would touch the registered
panel calls it first. The synthetic path does not — a harness you cannot
smoke-test is a harness you first test on the real data, which is the thing
being prevented.

DETERMINISM
===========
LightGBM is run `deterministic=True, force_row_wise=True, n_jobs=1` — the
reproducibility postmortem found the seed did nothing while multithreaded
histogram summation drifted. Slower and identical beats fast and almost.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from backend import config as _config
from backend.services.world_model import (block_bootstrap_paired,
                                          walk_forward_folds)

log = logging.getLogger(__name__)

TOURNAMENT = "AEGIS-NET-TOURNAMENT-1"
PREREG_PATH = (Path(_config.BACKEND_DIR).parent / "docs" / "TRIALS"
               / "PREREG_AEGIS_NET_TOURNAMENT_1.md")

#: The baseline every complex arm must beat by more than its own MDE.
BASELINE_ARM = "linear_ridge"

ARM_NAMES = ("linear_ridge", "lightgbm", "mlp_1", "mlp_2", "mlp_3")

SEED = 20260819


class TournamentRefused(RuntimeError):
    """A required input or authorization is missing. Refused, not defaulted."""


def assert_signed(prereg_path: Path | str | None = None) -> str:
    """Refuse unless the pre-registration exists and a human signed it.

    The check is crude on purpose — it cannot verify intent, but it can
    refuse the case that actually happens: a harness run on the registered
    basis while the signature line still reads UNSIGNED.
    """
    p = Path(prereg_path or PREREG_PATH)
    if not p.exists():
        raise TournamentRefused(
            f"no pre-registration at {p}. The tournament runs a declared "
            f"protocol or it does not run (canon §6).")
    text = p.read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.strip().upper().startswith("SIGNED-BY:"):
            signer = line.split(":", 1)[1].strip()
            if signer and "UNSIGNED" not in signer.upper():
                return signer
            raise TournamentRefused(
                f"pre-registration at {p} is UNSIGNED ({line.strip()!r}). "
                f"Drafting is a session's job; signing is Murat's.")
    raise TournamentRefused(
        f"pre-registration at {p} has no SIGNED-BY line at all — add one "
        f"reading 'SIGNED-BY: (unsigned)' to the draft so the gate has "
        f"something to refuse on.")


# ── arms (frozen; hyperparameters are part of the registration) ────────────
def build_arm(name: str, seed: int = SEED):
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    def _mlp(layers: tuple[int, ...]):
        from sklearn.neural_network import MLPRegressor
        return MLPRegressor(hidden_layer_sizes=layers, max_iter=500,
                            early_stopping=True, n_iter_no_change=20,
                            random_state=seed)

    if name == "linear_ridge":
        from sklearn.linear_model import Ridge
        est = Ridge(alpha=1.0, random_state=seed)
    elif name == "lightgbm":
        import lightgbm as lgb
        est = lgb.LGBMRegressor(
            n_estimators=300, learning_rate=0.05, num_leaves=31,
            min_child_samples=50, subsample=0.9, subsample_freq=1,
            colsample_bytree=0.9, random_state=seed,
            deterministic=True, force_row_wise=True, n_jobs=1, verbose=-1)
    elif name == "mlp_1":
        est = _mlp((32,))
    elif name == "mlp_2":
        est = _mlp((32, 16))
    elif name == "mlp_3":
        est = _mlp((32, 16, 8))
    else:
        raise TournamentRefused(f"unknown arm {name!r}; arms are frozen: "
                                f"{ARM_NAMES}")
    return Pipeline([("impute", SimpleImputer(strategy="median")),
                     ("scale", StandardScaler()), ("model", est)])


# ── scoring ────────────────────────────────────────────────────────────────
def rank_ic_by_date(pred: np.ndarray, actual: np.ndarray,
                    dates: np.ndarray) -> pd.Series:
    """Per-date Spearman IC. Dates with < 5 names are dropped AND counted in
    the result's attrs, never averaged in as noise."""
    df = pd.DataFrame({"p": pred, "a": actual, "d": dates})
    thin = 0
    out = {}
    for d, g in df.groupby("d"):
        if len(g) < 5:
            thin += 1
            continue
        out[d] = float(g["p"].rank().corr(g["a"].rank()))
    s = pd.Series(out, dtype=float)
    s.attrs["thin_dates_dropped"] = thin
    return s


@dataclass
class HeadResult:
    head: str
    arm: str
    per_fold: list[dict]
    pooled_ic_mean: float | None
    n_pred_rows: int


def run_head(df: pd.DataFrame, *, feature_cols: list[str], target_col: str,
             horizon_days: int, first_test_year: int,
             arms: tuple[str, ...] = ARM_NAMES, seed: int = SEED,
             min_train: int = 1000) -> dict:
    """One head, all arms, walk-forward. Returns predictions + the paired
    contrast of every arm against BASELINE_ARM with date-block inference.

    `df` must carry `date`, `ticker`, the features and the target. Rows with
    a missing TARGET are dropped and counted (features may be NaN — the
    imputer owns those); a missing target imputed would be a label invented.
    """
    for c in ("date", "ticker", target_col, *feature_cols):
        if c not in df.columns:
            raise TournamentRefused(f"column {c!r} absent from the panel")
    n0 = len(df)
    df = df.dropna(subset=[target_col]).reset_index(drop=True)
    n_dropped_target = n0 - len(df)

    dates = df["date"].to_numpy(dtype="datetime64[D]")
    folds = walk_forward_folds(dates, first_test_year, horizon_days,
                               min_train=min_train)
    if not folds:
        raise TournamentRefused(
            f"no walk-forward fold has enough training rows before "
            f"{first_test_year}; the panel cannot answer this head")

    X = df[feature_cols].to_numpy(dtype=float)
    y = df[target_col].to_numpy(dtype=float)

    preds: dict[str, np.ndarray] = {a: np.full(len(df), np.nan) for a in arms}
    fold_meta = []
    for tr, te, fold in folds:
        fold_meta.append(fold.__dict__)
        for arm in arms:
            model = build_arm(arm, seed)
            model.fit(X[tr], y[tr])
            preds[arm][te] = model.predict(X[te])

    scored = ~np.isnan(preds[arms[0]])
    out_arms = {}
    for arm in arms:
        ics = rank_ic_by_date(preds[arm][scored], y[scored], dates[scored])
        out_arms[arm] = {
            "ic_mean": float(ics.mean()) if len(ics) else None,
            "ic_n_dates": int(len(ics)),
            "thin_dates_dropped": ics.attrs.get("thin_dates_dropped", 0),
        }

    contrasts = {}
    base_sq = (preds[BASELINE_ARM][scored] - y[scored]) ** 2
    for arm in arms:
        if arm == BASELINE_ARM:
            continue
        arm_sq = (preds[arm][scored] - y[scored]) ** 2
        # Paired per-row loss difference; negative mean = arm beats baseline.
        inf = block_bootstrap_paired(arm_sq - base_sq, dates[scored],
                                     block_days=horizon_days, seed=seed)
        contrasts[arm] = inf.as_dict()

    return {
        "tournament": TOURNAMENT, "head": target_col,
        "baseline_arm": BASELINE_ARM,
        "n_rows_scored": int(scored.sum()),
        "n_rows_dropped_missing_target": n_dropped_target,
        "folds": fold_meta,
        "arms": out_arms,
        "loss_contrast_vs_baseline": contrasts,
        "contrast_note": ("negative mean = arm beats baseline on squared "
                          "loss; the deciding comparison and its criterion "
                          "live in the pre-registration, not here"),
    }


# ── the competing-risks barrier formulation (adjudication A5) ──────────────
def competing_risk_frame(df: pd.DataFrame, *, barrier: str = "up20_down10",
                         horizon_days: int = 20) -> pd.DataFrame:
    """(duration, event) per cause from the barrier labels.

    `neither` is CENSORING at the horizon, not a loser class — the label
    carries `days_to_barrier` and this frame is where that timing information
    finally gets consumed instead of thrown away.
    """
    oc, dc = f"barrier_{barrier}", f"barrier_{barrier}_days"
    if oc not in df.columns or dc not in df.columns:
        raise TournamentRefused(f"barrier columns {oc!r}/{dc!r} absent")
    out = df[["date", "ticker"]].copy()
    outcome = df[oc]
    days = df[dc]
    out["duration"] = np.where(outcome == "neither", horizon_days, days)
    out["event_up"] = (outcome == "up").astype(int)
    out["event_down"] = (outcome == "down").astype(int)
    bad = pd.isna(out["duration"])
    if bad.any():
        raise TournamentRefused(
            f"{int(bad.sum())} rows have a barrier outcome but no "
            f"days_to_barrier — the label contract promises both")
    return out


def fit_cause_specific(df: pd.DataFrame, feature_cols: list[str], *,
                       barrier: str = "up20_down10", horizon_days: int = 20,
                       penalizer: float = 0.1) -> dict:
    """Cause-specific Cox for the up- and down-barrier hazards.

    For the up-hazard, hitting DOWN first censors (and vice versa) — the
    standard cause-specific treatment. Returns per-cause concordance; the
    tournament compares this against the multinomial treatment that discards
    timing. Refuses (with the reason) when a cause has too few events —
    the h=20 coverage audit says up75/down30 fires on 0.6% of rows, and a
    fit on nothing pretending to converge is how impossible constraints
    oscillate.
    """
    from lifelines import CoxPHFitter

    cr = competing_risk_frame(df, barrier=barrier, horizon_days=horizon_days)
    X = df[feature_cols].reset_index(drop=True)
    out: dict = {"barrier": barrier, "horizon_days": horizon_days}
    for cause in ("up", "down"):
        events = cr[f"event_{cause}"]
        n_events = int(events.sum())
        if n_events < 30:
            out[cause] = {"refused": f"only {n_events} {cause}-barrier "
                                     f"events; below the 30-event floor"}
            continue
        frame = X.copy()
        frame["duration"] = cr["duration"].to_numpy()
        frame["event"] = events.to_numpy()
        frame = frame.dropna()
        cph = CoxPHFitter(penalizer=penalizer)
        cph.fit(frame, duration_col="duration", event_col="event")
        out[cause] = {"n_events": n_events,
                      "concordance": float(cph.concordance_index_),
                      "n_rows_fit": int(len(frame))}
    return out
