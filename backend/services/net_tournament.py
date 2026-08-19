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
def bootstrap_block_dates(dates: np.ndarray, horizon_days: int) -> int:
    """How many consecutive PANEL DATES one bootstrap block must span.

    `block_bootstrap_paired` blocks over *unique panel dates*, not calendar
    days. On a daily panel those coincide; on this month-end panel a block of
    20 dates is 20 MONTHS — n_effective collapses ~20× and the run-time MDE
    silently disagrees with the registered analytic power basis (145 monthly
    units). The block must therefore be derived from the panel's own spacing:
    enough dates that one block covers the outcome-overlap horizon, never
    more. Found 2026-08-19 while aligning the prereg's units.
    """
    uniq = np.unique(np.asarray(dates, dtype="datetime64[D]"))
    if uniq.size < 2:
        return 1
    spacing = float(np.median(np.diff(uniq).astype(float)))
    # calendar-day spacing vs a trading-day horizon: ~1.4 calendar/trading
    return max(1, int(np.ceil(horizon_days * 1.4 / max(spacing, 1.0))))


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

    # Block size in PANEL-DATE units, derived from the panel's own spacing —
    # 20 trading days is ~1 month-end date, not 20 of them.
    block_dates = bootstrap_block_dates(dates[scored], horizon_days)

    # PRIMARY (amendment 2026-08-19): paired per-date rank-IC difference vs
    # the baseline, same units as the registered economic bar (ΔIC 0.01).
    base_ics = rank_ic_by_date(preds[BASELINE_ARM][scored], y[scored],
                               dates[scored])
    ic_contrasts = {}
    loss_contrasts = {}
    base_sq = (preds[BASELINE_ARM][scored] - y[scored]) ** 2
    for arm in arms:
        if arm == BASELINE_ARM:
            continue
        arm_ics = rank_ic_by_date(preds[arm][scored], y[scored],
                                  dates[scored])
        joined = pd.concat([arm_ics, base_ics], axis=1, join="inner")
        d = (joined.iloc[:, 0] - joined.iloc[:, 1]).dropna()
        inf = block_bootstrap_paired(
            d.to_numpy(), d.index.to_numpy(dtype="datetime64[D]"),
            block_days=block_dates, seed=seed)
        ic_contrasts[arm] = inf.as_dict()

        # squared loss stays as a DIAGNOSTIC, never deciding
        arm_sq = (preds[arm][scored] - y[scored]) ** 2
        loss_contrasts[arm] = block_bootstrap_paired(
            arm_sq - base_sq, dates[scored], block_days=block_dates,
            seed=seed).as_dict()

    return {
        "tournament": TOURNAMENT, "head": target_col,
        "baseline_arm": BASELINE_ARM,
        "n_rows_scored": int(scored.sum()),
        "n_rows_dropped_missing_target": n_dropped_target,
        "bootstrap_block_dates": block_dates,
        "folds": fold_meta,
        "arms": out_arms,
        "ic_contrast_vs_baseline": ic_contrasts,
        "loss_contrast_vs_baseline": loss_contrasts,
        "contrast_note": ("PRIMARY: per-date rank-IC difference, positive "
                          "mean = arm beats baseline; squared loss is a "
                          "diagnostic. Criterion lives in the "
                          "pre-registration, not here"),
    }


# ── verdicts (amendment 2026-08-19: three-way, never two) ──────────────────
VERDICTS = ("COMPLEX_WINS", "LINEAR_NONINFERIOR", "NOT_ESTABLISHED")


def head_verdicts(ic_contrasts: dict, *, economic_bar: float = 0.01,
                  fwer: float = 0.05) -> dict:
    """Three-way verdict per complex arm, Holm across the declared arms.

    An underpowered miss is NOT_ESTABLISHED, never "linear". Canon: a null
    owes TWO tests — its MDE, and equivalence against an economic margin.

    - COMPLEX_WINS: mean ΔIC > 0, |mean| ≥ its own bootstrap MDE(80%), and
      the arm survives Holm at `fwer` across the m declared arms.
    - LINEAR_NONINFERIOR: the instrument could see the margin (MDE ≤ bar)
      AND the 90% CI's upper edge sits below the bar — the complex arm's
      advantage is bounded under economic relevance.
    - NOT_ESTABLISHED: everything else, including every underpowered cell.
    """
    from math import erf, sqrt

    def _p(mean: float, se: float) -> float:
        if se <= 0:
            return 1.0
        z = abs(mean) / se
        return max(2.0 * (1.0 - 0.5 * (1.0 + erf(z / sqrt(2.0)))), 1e-12)

    arms = sorted(ic_contrasts)
    pvals = {a: _p(ic_contrasts[a]["mean"], ic_contrasts[a]["se"])
             for a in arms}
    # Holm step-down at fwer across m = len(arms): reject while
    # p_(i) <= fwer/(m-i); the first failure stops all later rejections.
    holm_pass: dict[str, bool] = {a: False for a in arms}
    for rank, a in enumerate(sorted(arms, key=lambda a: pvals[a])):
        if pvals[a] <= fwer / (len(arms) - rank):
            holm_pass[a] = True
        else:
            break

    out = {}
    for a in arms:
        c = ic_contrasts[a]
        mean, mde, ci_hi = c["mean"], c["mde_80pct_power"], c["ci_hi"]
        if mean > 0 and abs(mean) >= mde and holm_pass[a]:
            v = "COMPLEX_WINS"
        elif mde <= economic_bar and ci_hi < economic_bar:
            v = "LINEAR_NONINFERIOR"
        else:
            v = "NOT_ESTABLISHED"
        out[a] = {"verdict": v, "mean_dIC": mean, "mde": mde,
                  "ci_90": [c["ci_lo"], ci_hi], "p_normal_approx": pvals[a],
                  "holm_pass": holm_pass[a], "economic_bar": economic_bar}
    return out


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
                      "concordance_basis": "IN-SAMPLE — diagnostic only; "
                                           "the registered comparison uses "
                                           "run_barrier_head's held-out "
                                           "concordance",
                      "n_rows_fit": int(len(frame))}
    return out


def run_barrier_head(df: pd.DataFrame, feature_cols: list[str], *,
                     barrier: str = "up20_down10", horizon_days: int = 20,
                     first_test_year: int, min_train: int = 1000,
                     penalizer: float = 0.1, seed: int = SEED) -> dict:
    """The registered competing-risks comparison, walk-forward and HELD OUT.

    Amendment 2026-08-19: `fit_cause_specific` reports in-sample concordance
    and was never called by the runner — a registered head the harness could
    not execute. This runs the declared comparison on the SAME fold structure
    as every other head: per fold, cause-specific Cox and a timing-blind
    multinomial are fit on train and scored on the test rows only, per cause,
    as concordance of the model's risk score against the held-out
    (duration, event) pairs. Sub-30-event causes refuse per fold and the
    refusal is counted, not averaged in.
    """
    from lifelines import CoxPHFitter
    from lifelines.utils import concordance_index
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression

    cr = competing_risk_frame(df, barrier=barrier, horizon_days=horizon_days)
    dates = df["date"].to_numpy(dtype="datetime64[D]")
    folds = walk_forward_folds(dates, first_test_year, horizon_days,
                               min_train=min_train)
    if not folds:
        raise TournamentRefused(
            f"no walk-forward fold has enough training rows before "
            f"{first_test_year}; the panel cannot answer this head")

    X_raw = df[feature_cols].to_numpy(dtype=float)
    oc = f"barrier_{barrier}"
    outcome3 = df[oc].to_numpy()          # {"up","down","neither"}

    per_fold = []
    for tr, te, fold in folds:
        imp = SimpleImputer(strategy="median")
        Xtr, Xte = imp.fit_transform(X_raw[tr]), imp.transform(X_raw[te])
        rec: dict = {"fold": fold.__dict__, "causes": {}}

        # timing-blind comparator: one multinomial on the 3-class outcome
        mn = LogisticRegression(max_iter=1000, random_state=seed)
        mn.fit(Xtr, outcome3[tr])
        classes = list(mn.classes_)
        probs = mn.predict_proba(Xte)

        for cause in ("up", "down"):
            ev_tr = cr[f"event_{cause}"].to_numpy()[tr]
            ev_te = cr[f"event_{cause}"].to_numpy()[te]
            n_ev_tr, n_ev_te = int(ev_tr.sum()), int(ev_te.sum())
            if n_ev_tr < 30 or n_ev_te < 30:
                rec["causes"][cause] = {
                    "refused": f"train/test events {n_ev_tr}/{n_ev_te}; "
                               f"below the 30-event floor"}
                continue
            frame = pd.DataFrame(Xtr, columns=feature_cols)
            frame["duration"] = cr["duration"].to_numpy()[tr]
            frame["event"] = ev_tr
            cph = CoxPHFitter(penalizer=penalizer)
            cph.fit(frame, duration_col="duration", event_col="event")
            risk = cph.predict_partial_hazard(
                pd.DataFrame(Xte, columns=feature_cols)).to_numpy()
            dur_te = cr["duration"].to_numpy()[te]
            c_cox = float(concordance_index(dur_te, -risk, ev_te))
            if cause in classes:
                p_cause = probs[:, classes.index(cause)]
                c_mn = float(concordance_index(dur_te, -p_cause, ev_te))
            else:
                c_mn = None
            rec["causes"][cause] = {
                "n_events_train": n_ev_tr, "n_events_test": n_ev_te,
                "concordance_holdout_cox": c_cox,
                "concordance_holdout_multinomial": c_mn,
            }
        per_fold.append(rec)

    # pooled: mean held-out concordance and the per-fold paired difference.
    summary: dict = {}
    for cause in ("up", "down"):
        pairs = [(r["causes"][cause]["concordance_holdout_cox"],
                  r["causes"][cause]["concordance_holdout_multinomial"])
                 for r in per_fold
                 if "refused" not in r["causes"].get(cause, {"refused": 1})
                 and r["causes"][cause]["concordance_holdout_multinomial"]
                 is not None]
        n_refused = sum(1 for r in per_fold
                        if "refused" in r["causes"].get(cause, {}))
        if pairs:
            diffs = [a - b for a, b in pairs]
            summary[cause] = {
                "n_folds_scored": len(pairs), "n_folds_refused": n_refused,
                "mean_holdout_cox": float(np.mean([a for a, _ in pairs])),
                "mean_holdout_multinomial": float(
                    np.mean([b for _, b in pairs])),
                "mean_paired_diff_cox_minus_mn": float(np.mean(diffs)),
                "screen_note": ("n is FOLDS (~single digits) — SCREEN-grade "
                                "by construction, never deciding"),
            }
        else:
            summary[cause] = {"n_folds_scored": 0,
                              "n_folds_refused": n_refused,
                              "status": "NOT_ANSWERABLE_AT_N"}

    return {"tournament": TOURNAMENT, "head": f"barrier_{barrier}",
            "barrier": barrier, "horizon_days": horizon_days,
            "per_fold": per_fold, "summary": summary}
