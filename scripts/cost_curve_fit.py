"""FIT the spread-extrapolation regression and SOLVE the impact eta. Once.

WHY THIS IS A SCRIPT AND NOT A FUNCTION THE CURVE CALLS AT IMPORT
=================================================================
`backend/services/cost_curve.py` READS the coefficients this script writes and
never fits them. A cost model that re-fits itself every time it is imported is
a cost model whose number depends on which parquet happened to be on disk that
night -- and every receipt that quoted it would be unreproducible for exactly
the reason nobody would think to check. The fit is a dated artefact with
standard errors, committed beside the code, and re-running this script is a
deliberate, reviewed act that produces a NEW receipt.

THE THREE INPUTS, AND WHERE EACH COMES FROM
===========================================
LHS  `log(half_effective_spread_bps)` -- `taq_effective_spreads_v1.jsonl`,
     `effective_full_bps_median` halved, aggregated per name as the MEDIAN OF
     DAILY MEDIANS (the same aggregation `taq_calibration.reading_for` uses for
     the quoted panel; a pooled mean over trades would weight a name by how
     chatty its tape was that day).
RHS  `log(dollar_volume_usd)`, `log(price_usd)`, `volatility_ann` -- the local
     `prices_2025_26/bars.parquet`, over a trailing window ENDING on the
     panel's last day, declared below before the fit was run.

The window, the gates and the eta calibration target are all declared as
module constants ABOVE the code that uses them, so that "which window flatters
the fit" is not a question this script can answer for itself.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PANEL = ROOT / "backend" / "data" / "optimus" / "taq_effective_spreads_v1.jsonl"
BARS = ROOT / "backend" / "data" / "optimus" / "prices_2025_26" / "bars.parquet"
OUT_DIR = ROOT / "backend" / "data" / "optimus" / "cost_curve"

#: Sessions of local bars, ending on the panel's LAST day, used for every
#: right-hand-side variable. Declared before the fit. 60 is one quarter: long
#: enough for a volatility estimate to mean something, short enough that it
#: describes the same market the panel measured.
RHS_WINDOW_SESSIONS = 60

#: Coverage gates, mirroring `taq_calibration.MIN_DAYS` / `MIN_QUOTES_PER_DAY`.
#: On v1 the thinnest name-day carries 9,597 trades, so the per-day gate drops
#: ZERO rows here, and the receipt says so. It is kept anyway because the next
#: pull will be wider, and a gate added after seeing the data it would have
#: dropped is not a gate.
MIN_DAYS = 15
MIN_TRADES_PER_DAY = 5_000

#: The eta calibration target, from the spec (roadmap lane E #1,
#: `docs/research_notes/2026-09-12/spec_cost_model.md` S1.4), which cites
#: Frazzini, Israel and Moskowitz (2018), "Trading Costs" (AQR) for a ONE-WAY
#: cost of roughly 30-50bp at 1% of ADV across a large live-trade dataset. The
#: midpoint is used and BOTH ends are carried onto the receipt, because the
#: solved eta is linear in the target and a reader must be able to see the
#: range the single frozen constant came from.
#:
#: NOT INDEPENDENTLY VERIFIED. This session had no network; the proximate
#: source for the 30-50bp figure is the spec, not the paper. The receipt says
#: so, and re-checking the paper's own table is owed before any RESEARCH_CLAIM
#: leans on the level.
FIM_ONE_WAY_BPS_AT_1PCT_ADV = (30.0, 50.0)
CALIBRATION_PARTICIPATION = 0.01


def load_effective_panel(path: Path = PANEL) -> pd.DataFrame:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    df = pd.DataFrame(rows)
    need = {"date", "ticker", "n_trades", "effective_full_bps_median"}
    missing = need - set(df.columns)
    if missing:
        raise SystemExit(f"REFUSED: effective panel missing {sorted(missing)}")
    return df


def per_name_half_spread(df: pd.DataFrame) -> pd.DataFrame:
    """One row per name: the median of daily medians, halved to ONE WAY."""
    keep = df[df["n_trades"] >= MIN_TRADES_PER_DAY]
    g = keep.groupby("ticker")["effective_full_bps_median"]
    out = pd.DataFrame({"full_bps": g.median(), "n_days": g.size(),
                        "day_low": g.min(), "day_high": g.max()})
    out["half_bps"] = out["full_bps"] / 2.0
    out["resolves"] = out["n_days"] >= MIN_DAYS
    return out.reset_index()


def rhs_from_bars(tickers: set[str], last_date: pd.Timestamp) -> pd.DataFrame:
    bars = pd.read_parquet(BARS, columns=["symbol", "date", "close", "volume"])
    bars = bars[bars["symbol"].isin(tickers) & (bars["date"] <= last_date)]
    rows = []
    for sym, d in bars.groupby("symbol", sort=True):
        d = d.sort_values("date").tail(RHS_WINDOW_SESSIONS)
        if len(d) < RHS_WINDOW_SESSIONS // 2:
            continue
        close = d["close"].to_numpy(dtype=float)
        vol = d["volume"].to_numpy(dtype=float)
        if not (np.all(np.isfinite(close)) and close.min() > 0):
            continue
        r = np.diff(np.log(close))
        rows.append({
            "ticker": sym,
            "dollar_volume_usd": float(np.median(close * vol)),
            "price_usd": float(np.median(close)),
            "volatility_ann": float(np.std(r, ddof=1) * math.sqrt(252.0)),
            "n_sessions": int(len(d)),
        })
    return pd.DataFrame(rows)


def ols(X: np.ndarray, y: np.ndarray) -> dict:
    """Plain OLS with classical standard errors. n=177, k=4 -- nothing here
    needs a library, and a hand-rolled fit is one whose residual convention
    the receipt can state exactly."""
    n, k = X.shape
    xtx_inv = np.linalg.inv(X.T @ X)
    beta = xtx_inv @ X.T @ y
    resid = y - X @ beta
    dof = n - k
    s2 = float(resid @ resid) / dof
    se = np.sqrt(np.diag(xtx_inv) * s2)
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - float(resid @ resid) / ss_tot
    return {"beta": beta, "se": se, "r2": r2,
            "adj_r2": 1 - (1 - r2) * (n - 1) / dof,
            "n": n, "dof": dof, "sigma": math.sqrt(s2), "resid": resid}


def loo_predictions(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Leave-one-out fitted values via the hat matrix -- exact, and cheaper
    than n refits. Fitting and validating on the same rows and calling it
    validated is the in-sample mistake this package exists to avoid."""
    xtx_inv = np.linalg.inv(X.T @ X)
    h = np.einsum("ij,jk,ik->i", X, xtx_inv, X)
    beta = xtx_inv @ X.T @ y
    resid = y - X @ beta
    return y - resid / (1.0 - h)


def solve_eta(target_one_way_bps: float, half_spread_bps: float,
              volatility_ann: float, participation: float) -> float:
    """eta such that `1e4 * eta * sigma * sqrt(POV)` closes the gap between the
    calibration target and the spread already charged separately.

    THE UNIT MATTERS AND IS THE ONE THING EASY TO GET WRONG HERE. The vendored
    `sqrt_impact` documents `volatility` as a DAILY return volatility; the spec
    passes an ANNUALISED one. Both are self-consistent as long as eta is solved
    in the same unit it is later used in, which is why this function takes the
    volatility explicitly and the receipt records which one.
    """
    impact_bps = target_one_way_bps - half_spread_bps
    if impact_bps <= 0:
        raise SystemExit("REFUSED: the calibration target is below the spread "
                         "term alone; there is no non-negative eta.")
    return impact_bps / 1e4 / (volatility_ann * math.sqrt(participation))


def main() -> int:
    ap = argparse.ArgumentParser(description="fit the cost curve, once")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    panel = load_effective_panel()
    last_date = pd.Timestamp(max(panel["date"]))
    names = per_name_half_spread(panel)
    rhs = rhs_from_bars(set(names["ticker"]), last_date)
    merged = names.merge(rhs, on="ticker", how="inner")
    dropped = sorted(set(names["ticker"]) - set(merged["ticker"]))
    fit_rows = merged[merged["resolves"] & (merged["half_bps"] > 0)].copy()

    X = np.column_stack([
        np.ones(len(fit_rows)),
        np.log(fit_rows["dollar_volume_usd"].to_numpy(dtype=float)),
        np.log(fit_rows["price_usd"].to_numpy(dtype=float)),
        fit_rows["volatility_ann"].to_numpy(dtype=float),
    ])
    y = np.log(fit_rows["half_bps"].to_numpy(dtype=float))
    f = ols(X, y)
    loo = loo_predictions(X, y)
    loo_r2 = 1.0 - (float(((y - loo) ** 2).sum())
                    / float(((y - y.mean()) ** 2).sum()))

    med_vol = float(np.median(fit_rows["volatility_ann"]))
    med_half = float(np.median(fit_rows["half_bps"]))
    lo, hi = FIM_ONE_WAY_BPS_AT_1PCT_ADV
    mid = 0.5 * (lo + hi)
    eta = solve_eta(mid, med_half, med_vol, CALIBRATION_PARTICIPATION)
    eta_lo = solve_eta(lo, med_half, med_vol, CALIBRATION_PARTICIPATION)
    eta_hi = solve_eta(hi, med_half, med_vol, CALIBRATION_PARTICIPATION)

    labels = ["intercept", "log_dollar_volume_usd", "log_price_usd",
              "volatility_ann"]
    receipt = {
        "artefact": "COST-CURVE-REGRESSION-1",
        "licence": "PRODUCT_EXPERIMENT (infrastructure; makes no claim)",
        "generated_at": datetime.now(UTC).isoformat(),
        "source_panel": "backend/data/optimus/taq_effective_spreads_v1.jsonl",
        "source_panel_verdict_status": "DEFERRED",
        "source_panel_caveat": (
            "v1 has NO trade-condition / odd-lot / venue filtering. The "
            "conventions probe (9 names x 10 conventions) found strict "
            "Holden-Jacobsen conventions RAISE the effective/quoted ratio "
            "toward 1 (NVDA composed-HJ 0.503 vs v1-all 0.716), so every "
            "half-spread fitted here is a LOWER bound on the refined "
            "computation -- up to roughly 40% low at the liquid end."),
        "rhs_source": "backend/data/optimus/prices_2025_26/bars.parquet",
        "rhs_window_sessions": RHS_WINDOW_SESSIONS,
        "rhs_window_ends": str(last_date.date()),
        "gates": {
            "min_days": MIN_DAYS,
            "min_trades_per_day": MIN_TRADES_PER_DAY,
            "min_trades_gate_dropped_rows": int(
                (panel["n_trades"] < MIN_TRADES_PER_DAY).sum()),
        },
        "n_names_in_panel": int(len(names)),
        "n_names_fitted": int(len(fit_rows)),
        "n_names_dropped_no_local_bars": len(dropped),
        "names_dropped_no_local_bars": dropped,
        "model": ("log(half_effective_spread_bps) = b0 "
                  "+ b1*log(dollar_volume_usd) + b2*log(price_usd) "
                  "+ b3*volatility_ann"),
        "coefficients": {
            n: {"estimate": round(float(b), 6), "std_error": round(float(s), 6),
                "t": round(float(b / s), 3)}
            for n, b, s in zip(labels, f["beta"], f["se"], strict=True)},
        "r2": round(f["r2"], 4),
        "adj_r2": round(f["adj_r2"], 4),
        "loo_r2": round(loo_r2, 4),
        "residual_sigma_log": round(f["sigma"], 4),
        "n": f["n"], "dof": f["dof"],
        "half_spread_bps_median_fitted": round(med_half, 4),
        "volatility_ann_median_fitted": round(med_vol, 4),
        "half_spread_bps_min_fitted": round(float(fit_rows["half_bps"].min()), 4),
        "half_spread_bps_max_fitted": round(float(fit_rows["half_bps"].max()), 4),
        "eta_solve": {
            "form": "impact_bps = 1e4 * eta * volatility_ann * sqrt(participation)",
            "vendored_function": ("backend.strategy.vendor.impact.sqrt_impact "
                                  "(byte-pinned, NOT edited)"),
            "volatility_convention": (
                "ANNUALISED, per spec S1.4. The vendor's docstring documents a "
                "DAILY volatility; eta is solved and used in the SAME unit, so "
                "the two are internally consistent, but this eta is NOT "
                "comparable to the vendor's 0.3-0.8 default range, which "
                "assumes daily vol."),
            "target_source": (
                "Frazzini, Israel and Moskowitz (2018), 'Trading Costs' (AQR), "
                "via spec_cost_model.md S1.4 -- NOT independently re-checked "
                "against the paper in this session (no network)."),
            "target_one_way_bps_at_1pct_adv": [lo, hi],
            "target_used_bps": mid,
            "participation": CALIBRATION_PARTICIPATION,
            "half_spread_subtracted_bps": round(med_half, 4),
            "volatility_ann_used": round(med_vol, 4),
            "eta": round(eta, 6),
            "eta_at_target_low": round(eta_lo, 6),
            "eta_at_target_high": round(eta_hi, 6),
            "eta_daily_vol_equivalent": round(eta * math.sqrt(252.0), 4),
            "note": (
                "the daily-vol equivalent is stated because it is the number "
                "comparable to Almgren, Thum, Hauptmann and Li (2005) and to "
                "the vendor default; where it lands far above 0.3-0.8 that is "
                "a FIFTH cost ruler disagreeing with the others, not a bug to "
                "hide."),
        },
        "rulers_that_disagree": {
            "NEGATIVE_RESULTS_25": (
                "Corwin-Schultz vs Kyle-Obizhaeva disagree 3.4-9.1x on LEVEL "
                "in the same segments (Spearman 0.66: they agree on ORDER, not "
                "magnitude); frozen verdict 'KO UNDERSTATES COSTS'"),
            "taq_quoted_median_one_way_bps": 2.726,
            "taq_effective_median_one_way_bps": 1.076,
            "this_curve": "a FOURTH ruler; it does not adjudicate the others",
        },
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = Path(args.out) if args.out else OUT_DIR / "taq_spread_regression_v1.json"
    out.write_text(json.dumps(receipt, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    print(f"  n={f['n']}  R2={f['r2']:.4f}  LOO R2={loo_r2:.4f}")
    for n, b, s in zip(labels, f["beta"], f["se"], strict=True):
        print(f"  {n:24s} {b:+10.5f}  (se {s:.5f}, t {b / s:+.2f})")
    print(f"  eta={eta:.6f} (ann-vol convention); daily-vol equivalent "
          f"{eta * math.sqrt(252.0):.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
