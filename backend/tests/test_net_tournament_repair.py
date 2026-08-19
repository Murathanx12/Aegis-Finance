"""Amendment-1 repairs to the NET tournament harness (2026-08-19).

Four external-review defects plus one found in-house (the bootstrap blocked
20 panel DATES — 20 months — instead of the 20-trading-day overlap). Every
repair ships with the test that would have caught it:

- block size is DERIVED from panel spacing, not conflated with trading days;
- verdicts are three-way and every branch is reachable (house rule);
- Holm is step-down and the first failure stops later rejections;
- the barrier head scores HELD-OUT concordance on the same folds as every
  other head, with the timing-blind multinomial on identical rows;
- the known-answer worlds behave: nonlinear world → the nonlinear arm sees
  what ridge cannot; null world → nobody earns COMPLEX_WINS.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend.services import net_tournament as NT

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.net_tournament_run import synthetic_panel  # noqa: E402


# ── block-size derivation ──────────────────────────────────────────────────
def test_monthly_panel_gets_monthly_blocks():
    dates = pd.bdate_range("2020-01-31", periods=48, freq="ME").to_numpy(
        dtype="datetime64[D]")
    b = NT.bootstrap_block_dates(dates, horizon_days=20)
    assert b == 1, (
        f"a 20-trading-day horizon on a month-end panel is ~one panel date "
        f"per block, got {b} — 20 would be 20 MONTHS, the amendment-1 defect")


def test_daily_panel_gets_horizon_sized_blocks():
    dates = pd.bdate_range("2020-01-01", periods=500).to_numpy(
        dtype="datetime64[D]")
    b = NT.bootstrap_block_dates(dates, horizon_days=20)
    assert 15 <= b <= 30, f"daily spacing should give ~20-28 dates, got {b}"


def test_single_date_panel_blocks_at_one():
    dates = np.array(["2020-01-31"], dtype="datetime64[D]")
    assert NT.bootstrap_block_dates(dates, horizon_days=20) == 1


# ── three-way verdicts: every branch reachable ─────────────────────────────
def _contrast(mean, se, mde, ci_lo, ci_hi):
    return {"mean": mean, "se": se, "mde_80pct_power": mde,
            "ci_lo": ci_lo, "ci_hi": ci_hi}


def test_complex_wins_branch_reachable():
    v = NT.head_verdicts({"lightgbm": _contrast(0.05, 0.005, 0.014,
                                                0.04, 0.06)})
    assert v["lightgbm"]["verdict"] == "COMPLEX_WINS"


def test_noninferior_branch_reachable():
    # instrument sees the bar (mde <= 0.01) and CI upper edge under it
    v = NT.head_verdicts({"mlp_1": _contrast(0.001, 0.003, 0.008,
                                             -0.004, 0.006)})
    assert v["mlp_1"]["verdict"] == "LINEAR_NONINFERIOR"


def test_underpowered_miss_is_not_established_never_linear():
    # mde far above the economic bar: the instrument cannot see the margin
    v = NT.head_verdicts({"mlp_2": _contrast(0.002, 0.02, 0.056,
                                             -0.03, 0.035)})
    assert v["mlp_2"]["verdict"] == "NOT_ESTABLISHED"


def test_positive_mean_without_holm_is_not_a_win():
    # strong-looking single arm but a second arm with tiny p takes the
    # smallest Holm alpha; the weak one must fail the step-down
    v = NT.head_verdicts({
        "lightgbm": _contrast(0.05, 0.004, 0.011, 0.04, 0.06),
        "mlp_3": _contrast(0.012, 0.011, 0.031, -0.006, 0.03),
    })
    assert v["lightgbm"]["verdict"] == "COMPLEX_WINS"
    assert v["mlp_3"]["verdict"] == "NOT_ESTABLISHED"


def test_holm_first_failure_stops_later_rejections():
    # three arms, middle one fails: the last may NOT be rejected even if its
    # raw p would pass its own threshold
    v = NT.head_verdicts({
        "a": _contrast(0.05, 0.005, 0.014, 0.04, 0.06),    # tiny p
        "b": _contrast(0.005, 0.02, 0.056, -0.03, 0.04),   # big p, fails
        "c": _contrast(0.04, 0.006, 0.017, 0.03, 0.05),    # small p
    })
    # step-down order is by p: a, c, b — c is evaluated before b fails, so
    # c may still win; b never does
    assert v["a"]["verdict"] == "COMPLEX_WINS"
    assert v["b"]["verdict"] == "NOT_ESTABLISHED"


# ── the barrier head: held out, refusals counted ───────────────────────────
@pytest.fixture(scope="module")
def barrier_world():
    return synthetic_panel(world="barrier", n_dates=72, n_names=80)


def test_barrier_head_scores_holdout_not_insample(barrier_world):
    out = NT.run_barrier_head(barrier_world, list(
        barrier_world.columns[2:9]), first_test_year=2017, min_train=800)
    scored = [r for r in out["per_fold"]
              if "refused" not in r["causes"].get("up", {})]
    assert scored, "no fold scored the planted up-cause"
    for r in scored:
        c = r["causes"]["up"]
        assert "concordance_holdout_cox" in c
        assert "concordance_holdout_multinomial" in c
        assert c["n_events_test"] >= 30


def test_barrier_head_recovers_planted_hazard(barrier_world):
    feature_cols = [c for c in barrier_world.columns
                    if c.startswith(("mom_", "vol_", "drawdown_"))]
    out = NT.run_barrier_head(barrier_world, feature_cols,
                              first_test_year=2017, min_train=800)
    s = out["summary"]["up"]
    assert s["n_folds_scored"] > 0
    # mom_63 drives the planted up-hazard: held-out concordance must beat
    # coin-flip by a clear margin on this declared world
    assert s["mean_holdout_cox"] > 0.55, s


def test_barrier_head_refuses_thin_causes():
    df = synthetic_panel(world="null", n_dates=72, n_names=80)
    # make the down cause vanishingly rare
    df.loc[df["barrier_up20_down10"] == "down", "barrier_up20_down10"] = \
        "neither"
    df.loc[df["barrier_up20_down10"] == "neither",
           "barrier_up20_down10_days"] = np.nan
    feature_cols = [c for c in df.columns
                    if c.startswith(("mom_", "vol_", "drawdown_"))]
    out = NT.run_barrier_head(df, feature_cols, first_test_year=2017,
                              min_train=800)
    assert out["summary"]["down"].get("status") == "NOT_ANSWERABLE_AT_N"
    assert out["summary"]["down"]["n_folds_refused"] > 0


# ── known-answer worlds ────────────────────────────────────────────────────
def test_nonlinear_world_is_invisible_to_ridge():
    df = synthetic_panel(world="nonlinear", n_dates=84, n_names=90)
    res = NT.run_head(df, feature_cols=[
        "mom_21", "mom_63", "mom_252", "mom_12_1", "vol_21", "vol_63",
        "drawdown_252"], target_col="cs_rank", horizon_days=20,
        first_test_year=2018, arms=("linear_ridge", "lightgbm"),
        min_train=800)
    ridge_ic = res["arms"]["linear_ridge"]["ic_mean"]
    lgbm_ic = res["arms"]["lightgbm"]["ic_mean"]
    assert lgbm_ic > ridge_ic + 0.05, (
        f"planted interaction world: lightgbm {lgbm_ic:+.4f} must clearly "
        f"beat ridge {ridge_ic:+.4f}")
    assert res["ic_contrast_vs_baseline"]["lightgbm"]["mean"] > 0


def test_null_world_earns_no_win():
    df = synthetic_panel(world="null", n_dates=84, n_names=90)
    res = NT.run_head(df, feature_cols=[
        "mom_21", "mom_63", "mom_252", "mom_12_1", "vol_21", "vol_63",
        "drawdown_252"], target_col="cs_rank", horizon_days=20,
        first_test_year=2018, arms=("linear_ridge", "lightgbm"),
        min_train=800)
    v = NT.head_verdicts(res["ic_contrast_vs_baseline"])
    assert v["lightgbm"]["verdict"] != "COMPLEX_WINS", v


# ── receipt shape ──────────────────────────────────────────────────────────
def test_run_head_reports_block_size_and_both_contrasts():
    df = synthetic_panel(world="linear", n_dates=60, n_names=40)
    res = NT.run_head(df, feature_cols=["mom_63", "vol_63"],
                      target_col="cs_rank", horizon_days=20,
                      first_test_year=2018,
                      arms=("linear_ridge", "lightgbm"), min_train=500)
    assert res["bootstrap_block_dates"] == 1
    assert "ic_contrast_vs_baseline" in res
    assert "loss_contrast_vs_baseline" in res
    assert "lightgbm" in res["ic_contrast_vs_baseline"]


def test_prereg_carries_amendment_and_frozen_params():
    text = NT.PREREG_PATH.read_text(encoding="utf-8")
    assert "AMENDMENT 1" in text
    assert "first_test_year = 2016" in text
    assert "LINEAR_NONINFERIOR" in text
    assert "UNIVERSE-SURVIVAL-STRESS-1" in text
