"""Is `P(beat) = 0.494` a probability, or a ranking score wearing a decimal point?

THE QUESTION THIS FILE EXISTS TO ANSWER
=======================================
v1's champion is `lgbm_clf`, whose output is documented as "P(excess > 0) over
the horizon -- a probability, NOT a return". The 2026-09-02 shadow book
published a top score of **0.494** and a mean of **0.4918** across ten held
names, and there was nothing on disk that could tell a reader whether that
meant *"the model dislikes today"* or merely *"these scores are uncalibrated
and 0.49 is a good one"*.

The reference that decides it is NOT 0.5. The unconditional base rate of a US
common stock beating the VALUE-WEIGHTED market over one month is **0.4532** on
the 2016-2024 OOS rows of this panel (0.4576 over 2013-2024, 0.3855 at 12m):
individual-stock excess returns are right-skewed, so most names lose to a
cap-weighted index most months and a 50/50 reference is simply the wrong
reference. Read against 0.4532, a score of 0.494 is roughly **+4 percentage
points of lift**, not pessimism.

That is the arithmetic. Whether the number is a LITERAL probability is a
separate, measurable question, and this module measures it three ways:

  * **Brier score** and **log loss**, against the base-rate-only forecast. A
    model whose Brier is no better than "always predict the base rate" has
    ordering skill at best.
  * **Reliability**, ten equal-count bins: mean predicted vs realised frequency
    per bin, plus ECE and the slope of realised on predicted. Slope 1 through
    the origin-of-the-base-rate is calibration; slope < 1 is the classic
    overconfident-in-the-middle shape; a positive slope with a large intercept
    gap is a RANKING that happens to be numbered.
  * **Temporal recalibration** -- Platt and isotonic, both fitted ONLY on
    trailing out-of-sample predictions and evaluated on the months AFTER the
    fit window. House rule, `CLAUDE.md`: never evaluate a calibrator on the
    data it was fitted on. If recalibration moves Brier materially, the raw
    scores were not probabilities; if it does not, they already were.

WHY TRAILING AND NOT POOLED
===========================
A calibrator fitted on the pooled OOS predictions knows 2024 while scoring
2016. That is the same lookahead the walk-forward split exists to prevent, one
level up, and it is the easy way to publish a beautifully calibrated model that
could never have been run. Every calibrated number here comes from a mapping
fitted strictly on months BEFORE the month it scores, with a minimum history;
months without enough history are NaN and are excluded from BOTH the raw and
the calibrated metric so the comparison is on the same rows.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

EPS = 1e-6
MIN_CALIB_MONTHS = 12
N_BINS = 10


def _clean(y, p):
    y = np.asarray(y, dtype="float64")
    p = np.asarray(p, dtype="float64")
    ok = np.isfinite(y) & np.isfinite(p)
    return y[ok], p[ok], ok


def brier(y, p) -> float | None:
    y, p, _ = _clean(y, p)
    if len(y) == 0:
        return None
    return float(np.mean((p - y) ** 2))


def log_loss(y, p) -> float | None:
    y, p, _ = _clean(y, p)
    if len(y) == 0:
        return None
    q = np.clip(p, EPS, 1 - EPS)
    return float(-np.mean(y * np.log(q) + (1 - y) * np.log(1 - q)))


def base_rate(y) -> float | None:
    y = np.asarray(y, dtype="float64")
    y = y[np.isfinite(y)]
    return float(y.mean()) if len(y) else None


def reliability(y, p, n_bins: int = N_BINS) -> dict:
    """Equal-COUNT bins, not equal-width.

    Equal-width bins on a score that lives inside [0.40, 0.55] would put every
    row in two bins and report a beautiful curve made of two points. The bin
    edges are therefore quantiles of the prediction, and the bin count is
    printed so a reader can see the n behind each point.
    """
    y, p, _ = _clean(y, p)
    if len(y) < n_bins * 10:
        return {"note": f"only {len(y)} rows -- fewer than {n_bins * 10} needed for "
                        f"{n_bins} bins", "n": int(len(y))}
    ranks = pd.Series(p).rank(method="first")
    b = pd.qcut(ranks, n_bins, labels=False, duplicates="drop")
    rows = []
    for k in sorted(pd.unique(b)):
        sel = (b == k).to_numpy()
        rows.append({
            "bin": int(k) + 1,
            "n": int(sel.sum()),
            "mean_predicted": round(float(p[sel].mean()), 5),
            "observed_frequency": round(float(y[sel].mean()), 5),
            "gap": round(float(p[sel].mean() - y[sel].mean()), 5),
        })
    ece = float(np.sum([r["n"] * abs(r["gap"]) for r in rows]) / len(y))
    xs = np.array([r["mean_predicted"] for r in rows])
    ys = np.array([r["observed_frequency"] for r in rows])
    slope = intercept = r2 = None
    if len(rows) >= 3 and np.std(xs) > 0:
        res = stats.linregress(xs, ys)
        slope, intercept, r2 = (round(float(res.slope), 3),
                                round(float(res.intercept), 5),
                                round(float(res.rvalue ** 2), 3))
    return {"n": int(len(y)), "n_bins": len(rows), "bins": rows,
            "ece": round(ece, 5),
            "reliability_slope": slope, "reliability_intercept": intercept,
            "reliability_r2": r2}


def score_block(y, p, label: str = "") -> dict:
    """Brier / log loss / base rate / skill vs the base-rate-only forecast."""
    y, p, _ = _clean(y, p)
    if len(y) == 0:
        return {"n": 0, "note": "no finite rows"}
    br = base_rate(y)
    b = brier(y, p)
    b0 = float(np.mean((br - y) ** 2))
    ll = log_loss(y, p)
    ll0 = log_loss(y, np.full(len(y), br))
    return {
        "label": label or None,
        "n": int(len(y)),
        "base_rate_realised": round(br, 5),
        "mean_predicted": round(float(p.mean()), 5),
        "mean_predicted_minus_base_rate": round(float(p.mean() - br), 5),
        "brier": round(b, 6),
        "brier_base_rate_forecast": round(b0, 6),
        "brier_skill_score": round(1.0 - b / b0, 5) if b0 > 0 else None,
        "log_loss": round(ll, 6),
        "log_loss_base_rate_forecast": round(ll0, 6),
        "sd_predicted": round(float(p.std()), 5),
    }


# ----------------------------------------------------- temporal calibrators

def _fit_platt(p_tr, y_tr):
    q = np.clip(p_tr, EPS, 1 - EPS)
    z = np.log(q / (1 - q)).reshape(-1, 1)
    lr = LogisticRegression(C=1e6, solver="lbfgs", max_iter=1000)
    lr.fit(z, y_tr)
    return lr


def _apply_platt(model, p):
    q = np.clip(p, EPS, 1 - EPS)
    z = np.log(q / (1 - q)).reshape(-1, 1)
    return model.predict_proba(z)[:, 1]


def temporal_calibrate(y, p, months, method: str = "platt",
                       min_train_months: int = MIN_CALIB_MONTHS,
                       window_months: int | None = None) -> tuple[np.ndarray, dict]:
    """Recalibrate month by month using ONLY earlier months' OOS predictions.

    For each month m, the mapping is fitted on every row whose month is < m
    (optionally only the trailing `window_months`), then applied to month m.
    Months with fewer than `min_train_months` of history come back NaN -- they
    are not silently left raw, because a table half-raw and half-calibrated
    labelled "calibrated" is worse than an honest hole.
    """
    y = np.asarray(y, dtype="float64")
    p = np.asarray(p, dtype="float64")
    # Month labels -> ordered integer codes ONCE. The obvious `mo == m` inside
    # the loop is a full 332k-row object comparison 107 times over, which made
    # one arm's report take 28 seconds and would have made the full receipt an
    # hour of string compares.
    codes, uniq = pd.factorize(pd.Series(months), sort=True)
    codes = np.asarray(codes)
    order = np.argsort(codes, kind="stable")
    starts = np.searchsorted(codes[order], np.arange(len(uniq)), side="left")
    ends = np.searchsorted(codes[order], np.arange(len(uniq)), side="right")
    finite = np.isfinite(y) & np.isfinite(p)
    out = np.full(len(p), np.nan, dtype="float64")
    used, skipped = [], []
    for i, m in enumerate(uniq):
        sel = order[starts[i]:ends[i]]
        sel = sel[finite[sel]]
        lo = 0 if window_months is None else max(0, i - window_months)
        if (i - lo) < min_train_months or len(sel) == 0:
            skipped.append(m)
            continue
        # Rows whose month code is in [lo, i) -- strictly BEFORE the scored month.
        hist = order[starts[lo]:starts[i]]
        hist = hist[finite[hist]]
        if len(hist) < 200 or len(np.unique(y[hist])) < 2:
            skipped.append(m)
            continue
        try:
            if method == "platt":
                model = _fit_platt(p[hist], y[hist])
                out[sel] = _apply_platt(model, p[sel])
            elif method == "isotonic":
                iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
                iso.fit(p[hist], y[hist])
                out[sel] = iso.predict(p[sel])
            else:
                raise ValueError(f"unknown calibration method {method!r}")
        except Exception as exc:                       # a refusal is a finding
            skipped.append(f"{m}: {type(exc).__name__}")
            continue
        used.append(m)
    meta = {"method": method, "min_train_months": min_train_months,
            "window_months": window_months,
            "months_calibrated": len(used), "months_without_history": len(skipped),
            "fit_rule": "fitted on months STRICTLY BEFORE the scored month; never on "
                        "the rows it scores"}
    return out, meta


def calibration_report(y, p, months, n_bins: int = N_BINS,
                       min_train_months: int = MIN_CALIB_MONTHS) -> dict:
    """The whole answer for one (arm, horizon): raw, Platt, isotonic.

    The raw block is reported twice -- once on all rows, and once restricted to
    exactly the rows a temporal calibrator could score. Comparing a calibrated
    Brier on 80 months against a raw Brier on 107 would be a comparison of two
    different samples, which is how a recalibration gets credit for a regime.
    """
    y = np.asarray(y, dtype="float64")
    p = np.asarray(p, dtype="float64")
    out: dict = {"raw_all_rows": score_block(y, p, "raw"),
                 "reliability_raw": reliability(y, p, n_bins)}
    for method in ("platt", "isotonic"):
        pc, meta = temporal_calibrate(y, p, months, method=method,
                                      min_train_months=min_train_months)
        same = np.isfinite(pc) & np.isfinite(y) & np.isfinite(p)
        block = {"meta": meta}
        if same.sum() == 0:
            block["note"] = "no month had enough trailing history to calibrate"
        else:
            block["raw_on_the_same_rows"] = score_block(y[same], p[same], "raw|calibratable")
            block["calibrated"] = score_block(y[same], pc[same], method)
            block["reliability_calibrated"] = reliability(y[same], pc[same], n_bins)
            b_raw = block["raw_on_the_same_rows"]["brier"]
            b_cal = block["calibrated"]["brier"]
            block["brier_improvement"] = round(b_raw - b_cal, 6)
            block["brier_improvement_pct"] = (round(100.0 * (b_raw - b_cal) / b_raw, 3)
                                              if b_raw else None)
        out[method] = block
    out["verdict"] = _verdict(out)
    return out


def _verdict(rep: dict) -> dict:
    """Literal probability, or a ranking score? Stated mechanically."""
    rel = rep.get("reliability_raw", {})
    raw = rep.get("raw_all_rows", {})
    ece = rel.get("ece")
    slope = rel.get("reliability_slope")
    bss = raw.get("brier_skill_score")
    imp = []
    for m in ("platt", "isotonic"):
        v = (rep.get(m) or {}).get("brier_improvement")
        if v is not None:
            imp.append(v)
    best_imp = max(imp) if imp else None
    if ece is None:
        return {"reading": "CANNOT DETERMINE -- too few rows to bin"}
    # A score is a LITERAL probability when its bins land on the diagonal.
    literal = (ece <= 0.02 and slope is not None and 0.5 <= slope <= 1.5)
    orders = bss is not None and bss > 0
    return {
        "ece": ece,
        "reliability_slope": slope,
        "brier_skill_score_vs_base_rate": bss,
        "best_brier_improvement_from_temporal_recalibration": best_imp,
        "reading": (
            "LITERAL PROBABILITY (bins land on the diagonal; recalibration has little "
            "left to take)" if literal and orders else
            "RANKING SCORE WITH A DECIMAL POINT (it orders, but the level is not a "
            "frequency)" if orders else
            "NEITHER -- it does not even order better than the base rate"),
        "how_to_read_0_49": (
            "against 0.5 a score of 0.49 looks bearish; against the REALISED base rate it "
            "is the only comparison that means anything. The base rate is printed in every "
            "block above as `base_rate_realised`."),
    }


def describe() -> dict:
    return {
        "why": "v1 shipped a classifier champion and zero calibration numbers, so the "
               "shadow book's P(beat)=0.494 had no on-disk reading.",
        "reference_is_the_base_rate_not_0_5": (
            "individual-stock excess returns are right-skewed, so most names lose to a "
            "cap-weighted market most months. The 1m OOS base rate on this panel is "
            "0.4532; at 12m it is 0.3855."),
        "metrics": ["brier", "log_loss", "reliability (10 equal-COUNT bins)", "ECE",
                    "reliability slope/intercept", "brier skill score vs base rate"],
        "calibrators": ["temporal Platt (logistic on the logit)",
                        "temporal isotonic (monotone, out_of_bounds=clip)"],
        "fit_rule": "fitted on months STRICTLY BEFORE the month scored, minimum "
                    f"{MIN_CALIB_MONTHS} months of history; never on the rows it scores. "
                    "Months without history are NaN and are dropped from BOTH sides of "
                    "the comparison.",
        "n_bins": N_BINS,
    }


__all__ = ["brier", "log_loss", "base_rate", "reliability", "score_block",
           "temporal_calibrate", "calibration_report", "describe",
           "MIN_CALIB_MONTHS", "N_BINS"]
