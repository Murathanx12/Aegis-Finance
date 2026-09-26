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
