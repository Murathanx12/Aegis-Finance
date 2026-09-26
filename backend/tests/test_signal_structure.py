"""signal_structure: clustering, factor regression, the 12-month refusal. Offline."""
import numpy as np
import pandas as pd
import pytest

from backend.services import signal_structure as SS


def _dates(n):
    return pd.date_range("2017-01-31", periods=n, freq="ME")


def test_three_known_blocks_give_three_clusters():
    rng = np.random.default_rng(7)
    n = 120
    base = [rng.normal(0, 0.03, n) for _ in range(3)]
    cols = {}
    for b in range(3):
        for j in range(4):                      # 4 members per block, rho ~ 0.96 within
            cols[f"b{b}_{j}"] = base[b] + rng.normal(0, 0.006, n)
    active = pd.DataFrame(cols, index=_dates(n))
    corr = SS.corr_matrix(active)
    lab = SS.cluster(corr, rho_cut=0.8)
    assert lab.nunique() == 3
    for b in range(3):
        assert lab[[f"b{b}_{j}" for j in range(4)]].nunique() == 1


def test_nan_correlation_splits_never_merges():
    # a pair without enough overlap has rho NaN: treated as distance 1
    corr = pd.DataFrame([[1.0, np.nan], [np.nan, 1.0]], index=["a", "b"], columns=["a", "b"])
    assert SS.cluster(corr).nunique() == 2


def test_regression_recovers_a_known_smh_beta():
    rng = np.random.default_rng(11)
    n = 96
    X = pd.DataFrame({f"{t}-SPY": rng.normal(0, 0.04, n) for t in SS.FACTOR_SPREADS},
                     index=_dates(n))
    y = 0.004 + 0.8 * X["SMH-SPY"] + 0.3 * X["IWM-SPY"] + rng.normal(0, 0.005, n)
    out = SS.ols(pd.Series(y, index=X.index), X)
    assert abs(out["betas"]["SMH-SPY"] - 0.8) < 0.05
    assert abs(out["betas"]["IWM-SPY"] - 0.3) < 0.05
    assert abs(out["betas"]["MTUM-SPY"]) < 0.05
    assert abs(out["alpha_monthly"] - 0.004) < 0.002
    assert out["r2"] > 0.9
    # the decomposition identity: mean active = alpha + sum(beta x mean spread)
    assert abs(out["alpha_monthly"] + sum(out["contribution_monthly"].values())
               - out["mean_active_monthly"]) < 1e-10


def test_receipt_refuses_below_twelve_months():
    X = pd.DataFrame({"SMH-SPY": np.arange(11) * 0.01}, index=_dates(11))
    y = pd.Series(np.arange(11) * 0.02, index=X.index)
    with pytest.raises(SS.InsufficientHistory):
        SS.ols(y, X)
    with pytest.raises(SS.InsufficientHistory):
        SS.require_months(11)
    SS.require_months(12)                        # exactly 12 passes


def test_active_frame_places_cells_on_the_grid_and_refuses_off_grid():
    grid = pd.DatetimeIndex(_dates(20))
    cells = {"r@k20": {"span": [str(grid[2].date()), str(grid[6].date())], "active": [0.01] * 5},
             "bad@k20": {"span": [str(grid[2].date()), str(grid[9].date())], "active": [0.01] * 5}}
    frame, refused = SS.active_frame(cells, grid)
    assert frame["r@k20"].notna().sum() == 5
    assert frame["r@k20"].first_valid_index() == grid[2]
    assert [c for c, _ in refused] == ["bad@k20"]


def test_period_returns_compounds_over_half_open_month():
    idx = pd.bdate_range("2020-01-01", "2020-03-31")
    daily = pd.Series(0.001, index=idx)
    dd = SS.month_end_sessions(idx)
    pr = SS.period_returns(daily, dd)
    n_feb = ((idx > dd[0]) & (idx <= dd[1])).sum()
    assert abs(pr.iloc[0] - ((1.001 ** n_feb) - 1)) < 1e-12


def test_lagged_corr_detects_a_planted_lead():
    rng = np.random.default_rng(3)
    x = pd.Series(rng.normal(0, 1, 100), index=_dates(100))
    y = x.shift(1) + rng.normal(0, 0.3, 100)     # x leads y by one month
    rho1, n1 = SS.lagged_corr(y, x, 1)
    rho0, _ = SS.lagged_corr(y, x, 0)
    assert rho1 > 0.9 and n1 == 99
    assert abs(rho0) < 0.3


# ───────────── review 2026-09-27: MDE beside every alpha, the ex-ante hedge ─────────────

def _spreads(n, seed=5):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({f"{t}-SPY": rng.normal(0, 0.04, n) for t in SS.FACTOR_SPREADS},
                        index=_dates(n))


def test_every_alpha_carries_its_se_and_mde():
    X = _spreads(32)
    y = pd.Series(np.random.default_rng(1).normal(0.01, 0.05, 32), index=X.index)
    out = SS.ols(y, X)
    assert out["se_alpha"] > 0
    assert out["mde_alpha_80"] == pytest.approx(SS.MDE_Z * out["se_alpha"])
    assert out["t_alpha"] == pytest.approx(out["alpha_monthly"] / out["se_alpha"])


def test_exante_hedge_removes_a_known_beta_and_keeps_the_alpha():
    X = _spreads(60)
    rng = np.random.default_rng(2)
    y = pd.Series(0.01 + 1.2 * X["SMH-SPY"] + rng.normal(0, 0.002, 60), index=X.index)
    h = SS.exante_hedge(y, X, {"SMH-SPY": 1.2})
    assert h["alpha_monthly"] == pytest.approx(0.01, abs=0.001)
    assert h["t"] > 10 and SS.verdict(h, 0.01) == "ALPHA_DETECTED"
    # the WRONG (stale) beta leaves the factor in the "alpha": its SE balloons
    stale = SS.exante_hedge(y, X, {"SMH-SPY": 0.0})
    assert stale["se"] > 5 * h["se"]
    with pytest.raises(SS.InsufficientHistory):
        SS.exante_hedge(y.iloc[:11], X, {"SMH-SPY": 1.2})


def test_the_verdict_separates_beta_from_no_power():
    # |t| < 1 with an MDE ABOVE the observed excess: the test could not have seen it
    assert SS.verdict({"t": 0.3, "mde_80": 0.025}, 0.01) == "CANNOT_DISTINGUISH"
    # |t| < 1 with an MDE BELOW the observed excess: an alpha that size would show
    assert SS.verdict({"t": 0.3, "mde_80": 0.004}, 0.01) == "BETA_EXPLAINS"
    # 1 <= |t| < 2 is never "beta"
    assert SS.verdict({"t": -1.5, "mde_80": 0.001}, 0.01) == "CANNOT_DISTINGUISH"
    assert SS.verdict({"t": -2.5, "mde_80": 0.01}, 0.01) == "ALPHA_DETECTED"
    assert SS.verdict({"t": float("nan"), "mde_80": 0.01}, 0.01) == "CANNOT_DISTINGUISH"
    assert set(SS.VERDICTS) == {"ALPHA_DETECTED", "CANNOT_DISTINGUISH", "BETA_EXPLAINS"}


def test_residual_clustering_splits_what_a_shared_factor_merged():
    """Four series = one factor + independent noise: on active returns they are
    one bet at rho 0.8; after the factor is removed they are four."""
    n = 120
    X = _spreads(n, seed=9)
    rng = np.random.default_rng(4)
    act = pd.DataFrame({f"s{i}": 1.5 * X["IWM-SPY"] + rng.normal(0, 0.01, n) for i in range(4)},
                       index=X.index)
    raw = SS.cluster_curve(SS.corr_matrix(act))
    res = SS.cluster_curve(SS.corr_matrix(SS.residualise(act, X)))
    assert raw["0.8"] == 1 and res["0.8"] == 4
    assert list(raw) == [f"{c:.1f}" for c in SS.RHO_CURVE]
    assert SS.pair_rho_summary(SS.corr_matrix(act))["share_pairs_ge_cut"] == 1.0


def test_the_beta_label_is_gone_from_the_receipt_builder():
    """Review 2026-09-27 §7: "MOSTLY SMH/MTUM BETA" and the SMH+MTUM share read
    no power as no alpha. The builder must not compute them any more."""
    import ast
    import inspect

    from scripts import signal_structure as SX
    tree = ast.parse(inspect.getsource(SX))
    consts = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    assert "mostly_smh_or_mtum_beta" not in consts
    assert "smh_mtum_share_of_sealed_active" not in consts
    assert not hasattr(SX, "SHARE_FLOOR")


def test_base_signal_and_member_axis():
    from scripts import signal_structure as SX
    assert SX.base_signal("mom_6_1_large") == "mom_6_1"
    assert SX.base_signal("inflection_mid_plus") == "inflection"
    assert SX.base_signal("mom_12_1_q") == "mom_12_1"
    m = {"universe_rule": "all", "weight_rule": "equal", "hold_months": 1, "rebalance_months": None}
    assert SX.member_axis(dict(m, universe_rule="large"), m, 20, 20, "x_large", "x") == "universe"
    assert SX.member_axis(m, m, 20, 20, "mom_no_downgrades", "mom_12_1") == "signal/filter"
    assert SX.member_axis(dict(m, hold_months=3), m, 20, 20, "mom_12_1_q", "mom_12_1") == "hold/offset"
