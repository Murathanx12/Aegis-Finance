"""Tests for commodity curve service (mocked yfinance)."""

from __future__ import annotations

import pytest

from backend.services import commodity_curves as cc


def test_default_commodities_have_required_keys():
    for sym, info in cc.DEFAULT_COMMODITIES.items():
        assert "name" in info
        assert "front" in info
        assert "prefix" in info
        assert "exchange" in info
        assert "unit" in info


def test_contract_symbol_format():
    sym = cc._contract_symbol("CL", 2026, 6, "NYM")
    # June = 'M' month code, year 26
    assert sym == "CLM26.NYM"


def test_contract_symbol_invalid_month():
    with pytest.raises(ValueError):
        cc._contract_symbol("CL", 2026, 13, "NYM")


def test_next_n_months_count():
    assert len(cc._next_n_months(6)) == 6


def test_next_n_months_advances_year():
    out = cc._next_n_months(24)
    # Across 24 months we must see at least 2 distinct years
    years = {y for y, m in out}
    assert len(years) >= 2


def test_slope_diagnostics_contango():
    contracts = [
        {"tenor_months": 0, "price": 80.0},
        {"tenor_months": 3, "price": 82.0},
        {"tenor_months": 6, "price": 85.0},
    ]
    out = cc.slope_diagnostics(contracts)
    assert out["shape"] == "contango"
    assert out["contango_pct"] > 0
    assert out["roll_yield_3m_pct"] is not None


def test_slope_diagnostics_backwardation():
    contracts = [
        {"tenor_months": 0, "price": 90.0},
        {"tenor_months": 3, "price": 86.0},
        {"tenor_months": 6, "price": 82.0},
    ]
    out = cc.slope_diagnostics(contracts)
    assert out["shape"] == "backwardation"
    assert out["contango_pct"] < 0


def test_slope_diagnostics_flat():
    contracts = [
        {"tenor_months": 0, "price": 100.0},
        {"tenor_months": 6, "price": 100.2},
    ]
    out = cc.slope_diagnostics(contracts)
    assert out["shape"] == "flat"


def test_slope_diagnostics_empty():
    out = cc.slope_diagnostics([])
    assert out["shape"] == "unknown"


def test_fetch_curve_unknown_symbol():
    out = cc.fetch_curve("NOT_A_COMMODITY")
    assert "error" in out
