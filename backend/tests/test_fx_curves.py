"""Tests for FX spot + CIP forward curve service."""

from __future__ import annotations


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


def _rate_ok(rate: float) -> dict:
    return {"rate": rate, "source": "FRED", "missing_because": None}


def _rate_missing(currency: str = "XXX") -> dict:
    return {"rate": None, "source": "UNAVAILABLE",
            "missing_because": f"no data for {currency}"}


def test_forward_curve_returns_all_tenors(monkeypatch):
    """Mock spot + rates and verify the curve has the right tenors."""
    monkeypatch.setattr(fx, "fetch_spot", lambda p: 1.0850)
    monkeypatch.setattr(
        fx,
        "fetch_short_rate",
        lambda c: _rate_ok({"EUR": 0.02, "USD": 0.045}.get(c)),
    )
    out = fx.forward_curve("EURUSD", tenors_months=(1, 3, 6, 12))
    assert out["pair"] == "EURUSD"
    assert out["spot"] == 1.0850
    tenors = [f["tenor_months"] for f in out["forwards"]]
    assert tenors == [1, 3, 6, 12]
    # 12m forward: USD rate higher than EUR → forward > spot (USD discount)
    assert out["forwards"][-1]["forward"] > 1.0850
    assert out["degraded"] is False
    assert out["method"] == "Covered interest parity (act/360) using FRED short rates"


def test_forward_curve_no_spot(monkeypatch):
    monkeypatch.setattr(fx, "fetch_spot", lambda p: None)
    out = fx.forward_curve("EURUSD")
    assert "error" in out


def test_forward_curve_missing_rates_falls_back_to_spot(monkeypatch):
    """When short rates unavailable, forwards should fall back to spot."""
    monkeypatch.setattr(fx, "fetch_spot", lambda p: 1.10)
    monkeypatch.setattr(fx, "fetch_short_rate", lambda c: _rate_missing(c))
    out = fx.forward_curve("EURUSD", tenors_months=(3,))
    assert out["spot"] == 1.10
    assert out["forwards"][0]["forward"] == 1.10
    assert out["forwards"][0]["forward_points"] == 0.0
    # Q15: missing rates must be disclosed, not reported as a FRED read.
    assert out["degraded"] is True
    assert out["rates"]["base_rate_source"] == "UNAVAILABLE"
    assert "NOT a FRED read" in out["method"]


def test_forward_curve_default_constant_is_disclosed(monkeypatch):
    """A DEFAULT_CONSTANT substitution must flip `degraded` and name itself,
    never read as 'using FRED short rates' (Q15, 2026-10-07)."""
    monkeypatch.setattr(fx, "fetch_spot", lambda p: 1.10)

    def _short_rate(c):
        if c == "USD":
            return {"rate": fx.DEFAULT_USD_RATE, "source": "DEFAULT_CONSTANT",
                     "missing_because": "FRED unkeyed"}
        return _rate_ok(0.02)

    monkeypatch.setattr(fx, "fetch_short_rate", _short_rate)
    out = fx.forward_curve("EURUSD", tenors_months=(3,))
    assert out["degraded"] is True
    assert out["rates"]["quote_rate_source"] == "DEFAULT_CONSTANT"
    assert out["missing_because"] == ["FRED unkeyed"]
    assert "DEFAULT_CONSTANT" in out["method"]


def test_forward_curve_pip_size_jpy(monkeypatch):
    """JPY pip is 0.01, others 0.0001 — verify pip arithmetic."""
    monkeypatch.setattr(fx, "fetch_spot", lambda p: 110.00)
    monkeypatch.setattr(
        fx, "fetch_short_rate",
        lambda c: _rate_ok({"USD": 0.045, "JPY": 0.001}.get(c)),
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
    monkeypatch.setattr(fx, "fetch_short_rate", lambda c: _rate_ok(0.04))
    out = fx.fx_dashboard(pairs=["EURUSD", "GBPUSD"])
    assert out["n"] == 2
    assert {r["pair"] for r in out["pairs"]} == {"EURUSD", "GBPUSD"}
    assert all(r["degraded"] is False for r in out["pairs"])


def test_fx_dashboard_rows_disclose_degraded_rate(monkeypatch):
    """Q15: a row built on a substituted rate must say `degraded: true` —
    the dashboard table is where a sizing/pricing reader actually looks."""
    monkeypatch.setattr(fx, "fetch_spot", lambda p: 1.10)
    monkeypatch.setattr(fx, "fetch_short_rate", lambda c: _rate_missing(c))
    out = fx.fx_dashboard(pairs=["EURUSD"])
    assert out["pairs"][0]["degraded"] is True
