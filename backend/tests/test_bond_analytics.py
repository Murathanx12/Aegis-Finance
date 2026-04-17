"""Tests for bond analytics — YTM, duration, convexity, KRDs, ladders."""

import math

import pytest

from backend.services.bond_analytics import (
    Bond,
    CashFlow,
    bond_analytics,
    convexity,
    estimate_price_change,
    key_rate_durations,
    ladder_analytics,
    macaulay_duration,
    modified_duration,
    present_value,
    solve_ytm,
)


def test_par_bond_ytm_equals_coupon():
    """A bond priced at par must have YTM == coupon rate."""
    bond = Bond(face=100, coupon_rate=0.05, maturity_years=10, freq=2)
    y = solve_ytm(bond.cashflows(), 100.0)
    assert y is not None
    assert abs(y - 0.05) < 1e-5


def test_zero_coupon_pv_matches_formula():
    """Zero-coupon: PV = F / (1 + y/freq)^(t*freq) at any yield."""
    cfs = [CashFlow(t_years=5.0, amount=100.0)]
    y = 0.04
    pv = present_value(cfs, y, freq=2)
    expected = 100.0 / (1 + y / 2) ** (5 * 2)
    assert abs(pv - expected) < 1e-9


def test_premium_bond_ytm_below_coupon():
    """Bond at premium → YTM < coupon."""
    bond = Bond(face=100, coupon_rate=0.06, maturity_years=10, freq=2)
    y = solve_ytm(bond.cashflows(), 110.0)
    assert y is not None and y < 0.06


def test_discount_bond_ytm_above_coupon():
    """Bond at discount → YTM > coupon."""
    bond = Bond(face=100, coupon_rate=0.03, maturity_years=10, freq=2)
    y = solve_ytm(bond.cashflows(), 90.0)
    assert y is not None and y > 0.03


def test_zero_coupon_macaulay_duration_equals_maturity():
    """Macaulay duration of a zero-coupon bond equals its maturity."""
    cfs = [CashFlow(t_years=7.0, amount=100.0)]
    y = solve_ytm(cfs, 75.0)
    mac = macaulay_duration(cfs, y)
    assert abs(mac - 7.0) < 1e-3


def test_modified_duration_below_macaulay():
    bond = Bond(face=100, coupon_rate=0.04, maturity_years=10, freq=2)
    cfs = bond.cashflows()
    y = solve_ytm(cfs, 100.0)
    mac = macaulay_duration(cfs, y)
    mod = modified_duration(cfs, y)
    assert mod < mac
    assert mod > 0


def test_convexity_positive_for_normal_bond():
    bond = Bond(face=100, coupon_rate=0.04, maturity_years=10, freq=2)
    cfs = bond.cashflows()
    y = solve_ytm(cfs, 100.0)
    c = convexity(cfs, y)
    assert c > 0


def test_duration_predicts_small_price_change():
    """Duration+convexity ≈ actual price change for ±25bp shock."""
    bond = Bond(face=100, coupon_rate=0.045, maturity_years=10, freq=2)
    cfs = bond.cashflows()
    y0 = solve_ytm(cfs, 100.0)
    pv0 = present_value(cfs, y0)
    dur = modified_duration(cfs, y0)
    conv = convexity(cfs, y0)

    # Actual price for +25 bp shock
    pv_up = present_value(cfs, y0 + 0.0025)
    actual_pct = (pv_up - pv0) / pv0
    est_pct = estimate_price_change(dur, conv, +25)
    # Should match within ~5 bp
    assert abs(actual_pct - est_pct) < 5e-4


def test_bond_analytics_full_block():
    bond = Bond(face=100, coupon_rate=0.045, maturity_years=10, freq=2)
    out = bond_analytics(bond, 100.0)
    assert "error" not in out
    assert abs(out["ytm_pct"] - 4.5) < 1e-3
    assert out["modified_duration_years"] > 0
    assert out["convexity_years2"] > 0
    assert out["dv01_dollars_per_100"] > 0
    assert "+100bp" in out["price_shock_pct"]
    # +100bp shock should produce a negative price change
    assert out["price_shock_pct"]["+100bp"] < 0


def test_bond_analytics_rejects_zero_price():
    bond = Bond(face=100, coupon_rate=0.05, maturity_years=5, freq=2)
    out = bond_analytics(bond, 0.0)
    assert "error" in out


def test_key_rate_durations_sum_close_to_modified():
    """For a smooth shift, KRDs should sum approximately to modified duration."""
    bond = Bond(face=100, coupon_rate=0.04, maturity_years=10, freq=2)
    out = key_rate_durations(bond, 100.0, shock_bp=25)
    assert "error" not in out
    krds = out["key_rate_durations"]
    sum_krd = out["sum_krd"]
    mod = out["modified_duration_years"]
    # Within 25% of modified duration (triangular hat decomposition is approximate)
    assert abs(sum_krd - mod) / mod < 0.25
    # 10y KRD should dominate for a 10y bond
    assert max(krds.items(), key=lambda kv: kv[1])[0] == "10y"


def test_ladder_analytics_weights():
    positions = [
        {"maturity_years": 2, "coupon_rate": 0.04, "weight": 1},
        {"maturity_years": 5, "coupon_rate": 0.04, "weight": 1},
        {"maturity_years": 10, "coupon_rate": 0.04, "weight": 1},
    ]
    out = ladder_analytics(positions)
    assert "error" not in out
    assert out["n_positions"] == 3
    assert abs(out["weighted_avg_maturity_years"] - (2 + 5 + 10) / 3) < 1e-3
    # Each position should have a weight ~1/3
    assert all(abs(p["weight"] - 1 / 3) < 1e-6 for p in out["positions"])
    assert out["weighted_modified_duration"] > 0


def test_ladder_rejects_empty():
    out = ladder_analytics([])
    assert "error" in out


def test_solve_ytm_handles_unsolvable():
    """A bond priced absurdly (e.g. 10x par) should not crash the solver."""
    bond = Bond(face=100, coupon_rate=0.04, maturity_years=5, freq=2)
    y = solve_ytm(bond.cashflows(), 1000.0)
    # Either returns a very negative yield or None — must not raise
    assert y is None or math.isfinite(y)
