"""Pins the conventions of the S65 night backtest scripts (synthetic data, offline)."""
import numpy as np

from scripts.night import dip_add as D
from scripts.night.family_board import block_stats


def test_dip_trigger_uses_only_returns_known_at_close():
    r = np.zeros(10)
    r[4] = -0.025                      # a -2.5% day: the 3-session sum crosses -2% at t=4
    dip, bounce = D.triggers(r, "dip3")
    assert dip.tolist().index(True) == 4
    assert not bounce.any()


def test_decay_add_expires_after_hold_sessions():
    dip = np.zeros(12, bool)
    dip[2] = True
    tgt, adds = D.target_path(dip, np.zeros(12, bool), base=0.8, step=0.1, cap=1.0, exit_="decay", hold=3)
    assert adds == 1
    assert np.allclose(tgt[:2], 0.8) and np.allclose(tgt[2:5], 0.9) and np.allclose(tgt[5:], 0.8)


def test_trade_executes_at_next_close_so_weight_lags_two_sessions():
    tgt = np.array([0.8, 0.8, 1.0, 1.0, 1.0])
    out = D.run_book(np.full(5, 0.01), np.zeros(5), tgt, cost=0.0, base=0.8)
    # decided at close 2, traded at close 3, held from session 4
    assert out["w"].tolist() == [0.8, 0.8, 0.8, 0.8, 1.0]


def test_costs_are_charged_on_traded_weight():
    tgt = np.array([0.8, 0.8, 1.0, 1.0, 1.0])
    free = D.run_book(np.zeros(5), np.zeros(5), tgt, cost=0.0, base=0.8)
    paid = D.run_book(np.zeros(5), np.zeros(5), tgt, cost=0.001, base=0.8)
    assert free["nav"][-1] == 1.0
    assert abs(paid["nav"][-1] - (1 - 0.001 * 0.2)) < 1e-12


def test_block_stats_mde_is_2_8_standard_errors():
    rng = np.random.default_rng(0)
    d = rng.normal(0.001, 0.01, 120)
    s = block_stats(d)
    assert s["n_blocks"] == 40
    assert abs(s["mde_monthly"] - 2.8 * s["se_monthly"]) < 1e-15
