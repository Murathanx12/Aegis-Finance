"""VALIDATE the cost curve: how wrong is it, and does it move a verdict.

Spec S3. Two measurements and one confession, in one receipt:

  S3.1  predicted vs MEASURED half spread on the 4,224 name-days the panel
        actually measured, leave-one-out, MAE by liquidity tercile.
  S3.2  the deflated Sharpe of the best night result under three cost rulers.
  S3.3  what the curve CANNOT know, quoted verbatim from the spec, because a
        validation that only reports the errors it can measure is a report on
        the errors it can measure.

LEAVE-ONE-OUT, NOT IN-SAMPLE. Fitting on 177 names and validating on the same
177 is the mistake `Policy`'s own docstring calls out; the hat-matrix LOO used
here is exact and costs one matrix inverse.

THE TERCILE CUT IS DECLARED BEFORE THE ERROR IS COMPUTED: equal COUNT by
trailing dollar volume. A cut chosen after seeing which one flatters the fit
is not a cut, and "either a fresh tercile or the band script's cuts is fine as
long as it is declared first" is the spec's own wording.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from backend.services import cost_curve as CC
from backend.strategy.multipletesting import deflated_sharpe_ratio
from scripts.cost_curve_fit import (BARS, RHS_WINDOW_SESSIONS,
                                    load_effective_panel, loo_predictions,
                                    per_name_half_spread, rhs_from_bars)

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "backend" / "data" / "optimus" / "cost_curve"

#: The night result the sensitivity is run on: the top genome of the G1 search,
#: read ONCE on its holdout by G2. Named here rather than discovered, so that
#: a future run of this script against a different result is a visible edit.
NIGHT_RECEIPT = (ROOT / "backend" / "data" / "optimus"
                 / "night_factory_2026-09-08" / "G2_holdout_once_run02.json")
G1_RECEIPT = (ROOT / "backend" / "data" / "optimus"
              / "night_factory_2026-09-08" / "G1_evolve_run01.json")

#: The flat rate every night receipt charges today (`scripts/night_*.py`).
NIGHT_FLAT_BPS_PER_SIDE = 25.0

#: The C2 over-charge, kept as a worst-case sanity floor: 25bp a side on BOTH
#: legs at 100% turnover, i.e. the shape that turned +30.6%/yr gross into
#: -221%/yr net in `HANDOFF_2026-09-10_THE_REPLAY_AND_THE_EXE.md` S4. It is
#: here to bracket, not because anybody believes it.
C2_OVERCHARGE_MONTHLY_COST = 2.0 * 2.0 * NIGHT_FLAT_BPS_PER_SIDE / 1e4

#: The universe floor the night books declare (`learner.evaluate`).
TRADABLE_DOLLAR_VOL = 3_000_000.0

WHAT_THE_CURVE_CANNOT_KNOW = [
    ("FILLS",
     "TAQ's effective spread is what OTHER trades reportedly paid; it says "
     "nothing about whether Aegis's own hypothetical order would have been "
     "filled at that price, partially filled, or filled worse under queue "
     "position it does not model. The retail curve's D2 dependency is the "
     "only piece of this program that measures actual fills, and it does not "
     "exist yet."),
    ("ADVERSE SELECTION AT THE OPEN",
     "The TAQ panel is explicitly 09:45-15:45 -- the open and the close, the "
     "two most expensive and most information-laden windows, are structurally "
     "absent from both the quoted and the effective panels. Any book that "
     "trades at or near the open (Lane D; tif=opg already shown unreliable on "
     "paper) is using a curve calibrated on a DIFFERENT, calmer part of the "
     "session, and the receipt must say so rather than implying open-auction "
     "costs are covered."),
    ("THE 2020 MARCH REGIME",
     "The panel is 23 days in 2026, a single calm-vol regime. Spread widens "
     "mechanically in stress; the vendored sqrt_impact's volatility term "
     "partially captures this for the IMPACT leg, but the measured spread "
     "term does not -- it is a fixed historical read, not a live one. A book "
     "run through a volatility regime the panel never saw is extrapolating "
     "the spread term outside its measured domain in the same way "
     "taq_calibration.apply_calibration already refuses to do for the AGK/TAQ "
     "ratio, and this curve has no equivalent refusal yet. That absence is "
     "itself worth naming rather than silently inheriting."),
    ("THE FARM'S OWN KEY",
     "Added by the 5c builder, not in the spec: the farm's CRSP panel is "
     "keyed on PERMNO and the measured branch of this curve on TICKER, so "
     "every fill the farm prices under `taq_empirical` is the REGRESSION and "
     "never the measurement. A receipt that said 'TAQ empirical' without the "
     "provenance mix beside it would be read as the opposite."),
]


def validate_spread(fit: dict) -> dict:
    """S3.1. Predicted vs measured, leave-one-out, by declared tercile."""
    panel = load_effective_panel()
    names = per_name_half_spread(panel)
    last_date = max(panel["date"])
    import pandas as pd
    rhs = rhs_from_bars(set(names["ticker"]), pd.Timestamp(last_date))
    merged = names.merge(rhs, on="ticker", how="inner")
    rows = merged[merged["resolves"] & (merged["half_bps"] > 0)].copy()

    X = np.column_stack([
        np.ones(len(rows)),
        np.log(rows["dollar_volume_usd"].to_numpy(dtype=float)),
        np.log(rows["price_usd"].to_numpy(dtype=float)),
        rows["volatility_ann"].to_numpy(dtype=float)])
    y = np.log(rows["half_bps"].to_numpy(dtype=float))
    loo_log = loo_predictions(X, y)
    rows["pred_half_bps_loo"] = np.exp(loo_log)
    rows["abs_err"] = (rows["pred_half_bps_loo"] - rows["half_bps"]).abs()

    # DECLARED BEFORE THE ERROR IS COMPUTED: equal-count terciles by trailing
    # dollar volume, ascending, so tercile 1 is the LEAST liquid.
    q = rows["dollar_volume_usd"].rank(pct=True)
    rows["tercile"] = np.where(q <= 1 / 3, "T1_least_liquid",
                               np.where(q <= 2 / 3, "T2_middle",
                                        "T3_most_liquid"))

    by_tercile = {}
    for name, g in rows.groupby("tercile"):
        worst = g.loc[g["abs_err"].idxmax()]
        best = g.loc[g["abs_err"].idxmin()]
        by_tercile[name] = {
            "n_names": int(len(g)),
            "dollar_volume_usd_median": round(float(g["dollar_volume_usd"].median()), 0),
            "measured_half_bps_median": round(float(g["half_bps"].median()), 4),
            "predicted_half_bps_median": round(float(g["pred_half_bps_loo"].median()), 4),
            "MAE_bps": round(float(g["abs_err"].mean()), 4),
            "median_abs_err_bps": round(float(g["abs_err"].median()), 4),
            "MAE_as_pct_of_measured_median": round(
                100.0 * float(g["abs_err"].mean()) / float(g["half_bps"].median()), 1),
            "worst_name": {"ticker": worst["ticker"],
                           "measured_half_bps": round(float(worst["half_bps"]), 4),
                           "predicted_half_bps": round(float(worst["pred_half_bps_loo"]), 4)},
            "best_name": {"ticker": best["ticker"],
                          "measured_half_bps": round(float(best["half_bps"]), 4),
                          "predicted_half_bps": round(float(best["pred_half_bps_loo"]), 4)},
        }

    # The same LOO prediction against every one of the 4,224 name-DAYS, not
    # just the per-name aggregate: a curve charged per fill is charged on a
    # day, and the day-to-day dispersion is error the per-name table hides.
    pred_by_name = dict(zip(rows["ticker"], rows["pred_half_bps_loo"], strict=True))
    day_err, n_days_used = [], 0
    for r in panel.itertuples():
        p = pred_by_name.get(r.ticker)
        if p is None:
            continue
        day_err.append(abs(p - r.effective_full_bps_median / 2.0))
        n_days_used += 1

    mae_t1 = by_tercile["T1_least_liquid"]["MAE_bps"]
    mae_t3 = by_tercile["T3_most_liquid"]["MAE_bps"]
    return {
        "method": ("leave-one-out via the hat matrix on the 177 fitted names; "
                   "terciles by trailing dollar volume, EQUAL COUNT, declared "
                   "before the error was computed"),
        "n_names": int(len(rows)),
        "n_name_days_checked": n_days_used,
        "overall_MAE_bps_per_name": round(float(rows["abs_err"].mean()), 4),
        "overall_median_abs_err_bps_per_name": round(float(rows["abs_err"].median()), 4),
        "overall_MAE_bps_per_name_day": round(float(np.mean(day_err)), 4),
        "loo_r2_in_logs": fit.get("loo_r2"),
        "by_tercile": by_tercile,
        "prestated_expectation": (
            "MAE worst in the ILLIQUID tercile and best in the LIQUID one; if "
            "the reverse holds, the regression is fitting noise in dollar "
            "volume rather than the liquidity relationship, and THAT is the "
            "finding."),
        "expectation_held": bool(mae_t1 > mae_t3),
        "expectation_note": (
            f"MAE least-liquid {mae_t1}bp vs most-liquid {mae_t3}bp"),
    }


def _representative_curve_bps(fit: dict) -> dict:
    """One half-spread number for a book whose HOLDINGS we cannot recover.

    The night books are graded on a CRSP panel keyed on permno over 1999-2024;
    this curve is keyed on ticker over 23 days of 2026. There is no honest
    join. What CAN be computed is the regression's prediction over a real
    cross-section above the same $3m execution floor those books declare --
    and that is what this returns, labelled a REPRESENTATIVE and not the
    book's own cost.
    """
    import pandas as pd
    bars = pd.read_parquet(BARS, columns=["symbol", "date", "close", "volume"])
    last = bars["date"].max()
    out = []
    for sym, d in bars.groupby("symbol", sort=True):
        d = d.sort_values("date").tail(RHS_WINDOW_SESSIONS)
        if len(d) < RHS_WINDOW_SESSIONS // 2:
            continue
        close = d["close"].to_numpy(dtype=float)
        vol = d["volume"].to_numpy(dtype=float)
        if not (np.all(np.isfinite(close)) and close.min() > 0):
            continue
        dv = float(np.median(close * vol))
        if dv < TRADABLE_DOLLAR_VOL:
            continue
        r = np.diff(np.log(close))
        out.append(CC.regression_half_spread_bps(
            dv, float(np.median(close)), float(np.std(r, ddof=1) * math.sqrt(252.0)),
            fit))
    arr = np.asarray(out)
    return {
        "n_symbols_above_floor": int(arr.size),
        "floor_dollar_vol_usd": TRADABLE_DOLLAR_VOL,
        "cross_section_date": str(pd.Timestamp(last).date()),
        "half_spread_bps_median": round(float(np.median(arr)), 4),
        "half_spread_bps_p25": round(float(np.percentile(arr, 25)), 4),
        "half_spread_bps_p75": round(float(np.percentile(arr, 75)), 4),
        "caveat": ("a REPRESENTATIVE rate over a 2025-26 cross-section above "
                   "the same $3m floor, NOT the 1999-2024 books' own names. "
                   "There is no honest permno-to-ticker join for those books."),
    }


def validate_dsr(fit: dict) -> dict:
    """S3.2. The top night result's DSR under three cost rulers."""
    g2 = json.loads(NIGHT_RECEIPT.read_text(encoding="utf-8"))
    g1 = json.loads(G1_RECEIPT.read_text(encoding="utf-8"))
    best = max(g2["archive_on_holdout"], key=lambda r: r["dev_fitness"])
    h = best["holdout"]
    n = int(h["months"])

    # EVERY INPUT BELOW IS DERIVED FROM THE RECEIPT OR REFUSED. The monthly
    # excess mean is geometric (terminal wealth is what the receipt records),
    # and its standard deviation is back-solved from the paired t -- stated
    # because both are approximations of the series nobody kept.
    mean_net = h["terminal_wealth_net"] ** (1.0 / n) - 1.0
    mean_mkt = h["terminal_wealth_market"] ** (1.0 / n) - 1.0
    mean_excess = mean_net - mean_mkt
    t = float(h["t_raw_paired"])
    sharpe_excess_monthly = t / math.sqrt(n)
    sd_excess = mean_excess / sharpe_excess_monthly

    # The cross-trial Sharpe dispersion, derived from the 200 random genomes'
    # own t distribution rather than assumed. It is the dispersion of the
    # RANDOM population, which is narrower than the searched population's --
    # said here because it makes the DSR below OPTIMISTIC, not conservative.
    nul = g2["null_random_genomes"]
    sd_t_random = (nul["t_bm_p95"] - nul["t_bm_p50"]) / 1.645
    trial_sharpe_std = sd_t_random / math.sqrt(n)

    rep = _representative_curve_bps(fit)
    turn = float(h["mean_turnover"])
    rulers = {
        "flat_25bps_per_side": turn * 2.0 * NIGHT_FLAT_BPS_PER_SIDE / 1e4,
        "C2_overcharge_100pct_turnover_both_legs": C2_OVERCHARGE_MONTHLY_COST,
        "taq_empirical_representative": turn * 2.0 * rep["half_spread_bps_median"] / 1e4,
    }
    base = rulers["flat_25bps_per_side"]

    out = {}
    for name, monthly_cost in rulers.items():
        m = mean_excess + (base - monthly_cost)     # the receipt's net is at `base`
        s = m / sd_excess
        row = {"monthly_cost": round(monthly_cost, 6),
               "monthly_cost_bps": round(1e4 * monthly_cost, 2),
               "monthly_mean_excess": round(m, 6),
               "sharpe_monthly": round(s, 4),
               "sharpe_annualised": round(s * math.sqrt(12.0), 4)}
        for n_trials in (35, int(g1["evaluations_this_run"])):
            d = deflated_sharpe_ratio(observed_sharpe=s, n_trials=n_trials,
                                      n_observations=n,
                                      trial_sharpe_std=trial_sharpe_std)
            row[f"dsr_at_{n_trials}_trials"] = round(d.deflated_sharpe_ratio, 4)
            row[f"survives_at_{n_trials}_trials"] = bool(d.survives)
        out[name] = row

    order = sorted(out, key=lambda k: -out[k]["sharpe_monthly"])
    return {
        "result": {"source": str(NIGHT_RECEIPT.relative_to(ROOT)).replace("\\", "/"),
                   "genome": best["key"], "window": g2["holdout"],
                   "months": n, "mean_turnover_monthly": turn,
                   "terminal_wealth_net": h["terminal_wealth_net"],
                   "terminal_wealth_market": h["terminal_wealth_market"],
                   "t_raw_paired": t},
        "derived_inputs": {
            "monthly_mean_excess_geometric": round(mean_excess, 6),
            "monthly_sd_excess_backsolved_from_t": round(sd_excess, 6),
            "trial_sharpe_std": round(trial_sharpe_std, 6),
            "trial_sharpe_std_basis": (
                "sd of the 200 RANDOM genomes' t, (p95-p50)/1.645, divided by "
                "sqrt(months). The searched population is wider, so every DSR "
                "here is OPTIMISTIC."),
            "approximations": [
                "the monthly mean is GEOMETRIC (terminal wealth is what the "
                "receipt kept); the arithmetic mean is slightly higher",
                "the excess sd is back-solved from the paired t, not measured "
                "from a series nobody stored",
                "costs are assumed to shift the MEAN and not the VOL, which is "
                "true to first order for a near-constant per-month charge",
            ]},
        "representative_curve": rep,
        "impact_term": {
            "included": False,
            "why": ("the night books declare no NOTIONAL, so participation is "
                    "undefined and the impact term is OMITTED rather than "
                    "guessed. At a $10k book it would round to zero; the two "
                    "sensitivities below say what it would add if it did not."),
            "would_add_bps_at_0.1pct_adv": round(
                CC.impact_bps(0.32, 0.001), 3),
            "would_add_bps_at_1pct_adv": round(CC.impact_bps(0.32, 0.01), 3),
            "volatility_ann_assumed": 0.32,
        },
        "by_ruler": out,
        "ranking_by_sharpe": order,
        "ranking_unchanged_across_rulers": order == sorted(
            out, key=lambda k: -out[k]["monthly_mean_excess"]),
        "roadmap_prediction": (
            "'the ranking of nothing may change and the LEVEL of everything "
            "will'. With ONE result there is no ranking to change: this row "
            "measures the LEVEL only, and the ranking claim is tested in the "
            "T4 migration, where families of arms are re-graded together."),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="validate the cost curve")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    fit = CC.load_regression()
    receipt = {
        "artefact": "COST-CURVE-VALIDATION-1",
        "licence": "PRODUCT_EXPERIMENT (infrastructure; makes no claim)",
        "generated_at": datetime.now(UTC).isoformat(),
        "curve": "taq_empirical",
        "eta": CC.ETA_SQRT_IMPACT,
        "regression_receipt": "backend/data/optimus/cost_curve/taq_spread_regression_v1.json",
        "source_panel_verdict_status": "DEFERRED (v1: no trade-condition / "
                                       "odd-lot / venue filtering)",
        "convention_multiplier_range": list(CC.convention_multiplier_range()),
        "rulers_that_disagree": fit["rulers_that_disagree"],
        "spread_validation_S3_1": validate_spread(fit),
        "dsr_sensitivity_S3_2": validate_dsr(fit),
        "what_the_curve_cannot_know_S3_3": [
            {"heading": h, "text": t} for h, t in WHAT_THE_CURVE_CANNOT_KNOW],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = (Path(args.out) if args.out
           else OUT_DIR / f"validate_{datetime.now(UTC).date()}.json")
    out.write_text(json.dumps(receipt, indent=1) + "\n", encoding="utf-8")

    s = receipt["spread_validation_S3_1"]
    print(f"wrote {out}")
    print(f"S3.1  n={s['n_names']} names / {s['n_name_days_checked']} name-days; "
          f"overall MAE {s['overall_MAE_bps_per_name']}bp")
    for k, v in sorted(s["by_tercile"].items()):
        print(f"      {k:16s} n={v['n_names']:3d}  measured med "
              f"{v['measured_half_bps_median']:7.3f}bp  MAE {v['MAE_bps']:7.3f}bp "
              f"({v['MAE_as_pct_of_measured_median']}%)")
    print(f"      prestated expectation held: {s['expectation_held']} "
          f"({s['expectation_note']})")
    d = receipt["dsr_sensitivity_S3_2"]
    print(f"S3.2  {d['result']['genome']} on {d['result']['window']}, "
          f"{d['result']['months']} months")
    for k, v in d["by_ruler"].items():
        print(f"      {k:42s} cost {v['monthly_cost_bps']:7.2f}bp/mo  "
              f"SR {v['sharpe_annualised']:+.3f}  "
              f"DSR@35 {v['dsr_at_35_trials']:.4f}  "
              f"DSR@40680 {v['dsr_at_40680_trials']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
