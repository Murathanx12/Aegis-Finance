"""Tests for FX spot + CIP forward curve service."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.services import fx_curves as fx


def test_split_pair():
    assert fx._split_pair("EURUSD") == ("EUR", "USD")
    assert fx._split_pair("usdjpy") == ("USD", "JPY")
    with pytest.raises(ValueError):
        fx._split_pair("USD")


def test_yf_pair_ticker():
    assert fx._yf_pair_ticker("EURUSD") == "EURUSD=X"


def test_cip_forward_higher_quote_rate_means_premium():
    """If quote rate > base rate, forward should trade at a premium to spot."""
    spot = 1.0850   # EURUSD
    fwd = fx.cip_forward(spot, base_rate=0.02, quote_rate=0.05, days=180)
    assert fwd > spot


def test_cip_forward_zero_days_returns_spot():
    assert fx.cip_forward(1.10, 0.02, 0.05, 0) == 1.10


def test_cip_forward_lower_quote_rate_means_discount():
    spot = 110.0  # USDJPY
    # JPY rates lower than USD → forward should fall (USD weaker forward)
    fwd = fx.cip_forward(spot, base_rate=0.04, quote_rate=0.001, days=365)
    assert fwd < spot


def test_forward_curve_returns_all_tenors(monkeypatch):
    """Mock spot + rates and verify the curve has the right tenors."""
    monkeypatch.setattr(fx, "fetch_spot", lambda p: 1.0850)
    monkeypatch.setattr(
        fx,
        "fetch_short_rate",
        lambda c: {"EUR": 0.02, "USD": 0.045}.get(c),
    )
    out = fx.forward_curve("EURUSD", tenors_months=(1, 3, 6, 12))
    assert out["pair"] == "EURUSD"
    assert out["spot"] == 1.0850
    tenors = [f["tenor_months"] for f in out["forwards"]]
    assert tenors == [1, 3, 6, 12]
    # 12m forward: USD rate higher than EUR → forward > spot (USD discount)
    assert out["forwards"][-1]["forward"] > 1.0850


def test_forward_curve_no_spot(monkeypatch):
    monkeypatch.setattr(fx, "fetch_spot", lambda p: None)
    out = fx.forward_curve("EURUSD")
    assert "error" in out


def test_forward_curve_missing_rates_falls_back_to_spot(monkeypatch):
    """When short rates unavailable, forwards should fall back to spot."""
    monkeypatch.setattr(fx, "fetch_spot", lambda p: 1.10)
    monkeypatch.setattr(fx, "fetch_short_rate", lambda c: None)
    out = fx.forward_curve("EURUSD", tenors_months=(3,))
    assert out["spot"] == 1.10
    assert out["forwards"][0]["forward"] == 1.10
    assert out["forwards"][0]["forward_points"] == 0.0


def test_forward_curve_pip_size_jpy(monkeypatch):
    """JPY pip is 0.01, others 0.0001 — verify pip arithmetic."""
    monkeypatch.setattr(fx, "fetch_spot", lambda p: 110.00)
    monkeypatch.setattr(
        fx, "fetch_short_rate",
        lambda c: {"USD": 0.045, "JPY": 0.001}.get(c),
    )
    out = fx.forward_curve("USDJPY", tenors_months=(12,))
    fwd_pts = out["forwards"][0]["forward_points"]
    # Forward should be < spot (JPY rate << USD rate); pip size 0.01, so
    # forward points should be in tens to low hundreds (negative)
    assert fwd_pts < 0
    assert abs(fwd_pts) < 1000


def test_fx_dashboard_aggregates(monkeypatch):
    """Dashboard should produce a row per pair."""
    monkeypatch.setattr(fx, "fetch_spot", lambda p: 1.10)
    monkeypatch.setattr(fx, "fetch_short_rate", lambda c: 0.04)
    out = fx.fx_dashboard(pairs=["EURUSD", "GBPUSD"])
    assert out["n"] == 2
    assert {r["pair"] for r in out["pairs"]} == {"EURUSD", "GBPUSD"}
