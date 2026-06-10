"""Tests for multi-currency portfolio analytics."""

from __future__ import annotations


import pytest

from backend.services import portfolio_currency as pc


# ── Currency inference ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "ticker,expected",
    [
        ("AAPL", "USD"),
        ("ASML.AS", "EUR"),
        ("ROCHE.SW", "CHF"),
        ("7203.T", "JPY"),
        ("0700.HK", "HKD"),
        ("RIO.L", "GBP"),
        ("BABA.HK", "HKD"),
        ("VALE3.SA", "BRL"),
        ("SAP.DE", "EUR"),
        ("RIO.AX", "AUD"),
        ("RY.TO", "CAD"),
    ],
)
def test_infer_listing_currency(ticker, expected):
    assert pc.infer_listing_currency(ticker) == expected


def test_infer_listing_currency_override_takes_precedence():
    assert pc.infer_listing_currency("BABA.HK", override="USD") == "USD"


def test_infer_listing_currency_empty():
    assert pc.infer_listing_currency("") == "USD"


# ── FX rate lookup ─────────────────────────────────────────────────────────


def test_fx_rate_same_currency_is_one():
    assert pc.fx_rate("USD", "USD") == 1.0
    assert pc.fx_rate("EUR", "EUR") == 1.0


def test_fx_rate_uses_direct_pair(monkeypatch):
    """When EURUSD spot is available, fx_rate('EUR', 'USD') uses it directly."""
    monkeypatch.setattr(
        "backend.services.fx_curves.fetch_spot",
        lambda pair: 1.0850 if pair == "EURUSD" else None,
    )
    assert abs(pc.fx_rate("EUR", "USD") - 1.0850) < 1e-9


def test_fx_rate_inverts_when_only_inverse_available(monkeypatch):
    """If USDJPY is available, fx_rate('JPY', 'USD') should invert it."""
    monkeypatch.setattr(
        "backend.services.fx_curves.fetch_spot",
        lambda pair: 110.0 if pair == "USDJPY" else None,
    )
    rate = pc.fx_rate("JPY", "USD")
    assert rate is not None and abs(rate - 1.0 / 110.0) < 1e-9


def test_fx_rate_returns_none_when_unavailable(monkeypatch):
    monkeypatch.setattr(
        "backend.services.fx_curves.fetch_spot",
        lambda pair: None,
    )
    assert pc.fx_rate("EUR", "USD") is None


# ── Position translation ──────────────────────────────────────────────────


def test_translate_position_usd_no_op(monkeypatch):
    p = {"ticker": "AAPL", "shares": 10, "current_price": 200.0}
    out = pc.translate_position(p, base="USD")
    assert out["listing_currency"] == "USD"
    assert out["fx_rate_to_base"] == 1.0
    assert out["market_value_local"] == 2000.0
    assert out["market_value_base"] == 2000.0
    assert not out["fx_translated"]


def test_translate_position_eur_listing(monkeypatch):
    monkeypatch.setattr(pc, "fx_rate", lambda quote, base: 1.10 if quote == "EUR" else 1.0)
    p = {"ticker": "ASML.AS", "shares": 5, "current_price": 800.0}
    out = pc.translate_position(p, base="USD")
    assert out["listing_currency"] == "EUR"
    assert out["market_value_local"] == 4000.0
    assert out["market_value_base"] == 4400.0
    assert out["fx_translated"]


def test_translate_position_marks_fx_unavailable(monkeypatch):
    monkeypatch.setattr(pc, "fx_rate", lambda *a, **k: None)
    p = {"ticker": "ASML.AS", "shares": 5, "current_price": 800.0}
    out = pc.translate_position(p, base="USD")
    assert out["fx_unavailable"] is True
    assert out["market_value_base"] is None


# ── Currency exposure ─────────────────────────────────────────────────────


def test_currency_exposure_aggregates_two_currencies(monkeypatch):
    monkeypatch.setattr(
        pc, "fx_rate",
        lambda quote, base: 1.10 if quote == "EUR" else 1.0,
    )
    positions = [
        {"ticker": "AAPL", "shares": 10, "current_price": 200.0},   # 2000 USD
        {"ticker": "ASML.AS", "shares": 5, "current_price": 800.0}, # 4400 USD
    ]
    out = pc.currency_exposure(positions, base="USD")
    assert out["n_currencies"] == 2
    assert out["total_market_value_base"] == 6400.0
    assert out["exposures"]["EUR"]["weight"] == 0.6875  # 4400/6400
    assert out["exposures"]["USD"]["weight"] == 0.3125
    # HHI = 0.6875^2 + 0.3125^2 ≈ 0.5703
    assert 0.55 < out["currency_hhi"] < 0.60
    assert not out["is_pure_base_currency"]


def test_currency_exposure_pure_base_flag(monkeypatch):
    positions = [{"ticker": "AAPL", "shares": 10, "current_price": 200.0}]
    out = pc.currency_exposure(positions, base="USD")
    assert out["is_pure_base_currency"]
    assert out["n_currencies"] == 1


def test_hedged_vs_unhedged_decomposition(monkeypatch):
    monkeypatch.setattr(
        pc, "fx_rate",
        lambda quote, base: 1.10 if quote == "EUR" else 1.0,
    )
    monkeypatch.setattr(
        pc, "_fx_return_pct",
        lambda quote, base, days=30: {"EUR": 0.02, "USD": 0.0}.get(quote),
    )
    positions = [
        {
            "ticker": "AAPL", "shares": 10, "current_price": 200.0,
            "return_local_pct": 0.05,
        },
        {
            "ticker": "ASML.AS", "shares": 5, "current_price": 800.0,
            "return_local_pct": 0.03,
        },
    ]
    out = pc.hedged_vs_unhedged(positions, base="USD")
    assert "portfolio_return_local_pct" in out
    assert "portfolio_return_fx_pct" in out
    # FX should contribute approximately weight(EUR)*2% = 0.6875*2 ≈ 1.375%
    assert 1.0 < out["portfolio_return_fx_pct"] < 1.7


def test_portfolio_currency_report_empty():
    out = pc.portfolio_currency_report([], base="USD")
    assert "error" in out


def test_portfolio_currency_report_single_currency():
    positions = [{"ticker": "AAPL", "shares": 10, "current_price": 200.0}]
    out = pc.portfolio_currency_report(positions, base="USD")
    assert "Single-currency" in out["interpretation"]
