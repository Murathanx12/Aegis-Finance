"""Tests for Morningstar-style Style Box classification."""

from unittest.mock import patch

import pytest

from backend.services import style_box as sb


def _make_metrics(ticker: str, **overrides):
    base = {
        "ticker": ticker,
        "name": ticker + " Inc",
        "sector": "Technology",
        "market_cap": 50e9,
        "pe_trailing": 25.0,
        "pe_forward": 22.0,
        "price_to_book": 6.0,
        "dividend_yield": 0.012,
        "revenue_growth": 0.10,
        "earnings_growth": 0.12,
        "peg_ratio": 1.5,
        "ev_ebitda": 20.0,
        "price_to_sales": 7.0,
        "fcf_yield": 0.04,
        "profit_margin": 0.20,
        "roe": 0.30,
        "debt_to_equity": 0.5,
    }
    base.update(overrides)
    return base


def test_size_label_boundaries():
    assert sb._size_label(None) == "Unknown"
    assert sb._size_label(1e9) == "Small"
    assert sb._size_label(5e9) == "Mid"
    assert sb._size_label(50e9) == "Large"
    assert sb._size_label(sb.SIZE_THRESHOLDS["small_upper"]) == "Mid"
    assert sb._size_label(sb.SIZE_THRESHOLDS["mid_upper"]) == "Large"


def test_classify_style_returns_labels():
    assert sb._classify_style(None) == "Blend"
    assert sb._classify_style(-1.0) == "Value"
    assert sb._classify_style(0.0) == "Blend"
    assert sb._classify_style(1.0) == "Growth"


def test_zscore_returns_zero_when_std_zero():
    # All peers identical → std=0 → z=0 (not NaN)
    z = sb._zscore(5.0, [5.0, 5.0, 5.0])
    assert z == 0.0


def test_zscore_clamped_to_pm3():
    peers = [10.0, 10.0, 10.0, 10.0]
    # A value that would otherwise blow up well past 3
    z = sb._zscore(1_000.0, peers)
    assert -3.0 <= z <= 3.0


def test_zscore_with_too_few_peers_returns_none():
    assert sb._zscore(5.0, [1.0]) is None


def test_classify_style_box_returns_full_grid():
    """Growth-heavy target inside a mixed sector → Large-Growth cell."""
    target = _make_metrics("HIGH", market_cap=80e9, earnings_growth=0.40, revenue_growth=0.35, pe_forward=35.0, dividend_yield=0.002)
    peers = [
        _make_metrics("P1", earnings_growth=0.05, revenue_growth=0.04, pe_forward=15.0, dividend_yield=0.03),
        _make_metrics("P2", earnings_growth=0.06, revenue_growth=0.05, pe_forward=16.0, dividend_yield=0.028),
        _make_metrics("P3", earnings_growth=0.08, revenue_growth=0.07, pe_forward=17.0, dividend_yield=0.025),
        _make_metrics("P4", earnings_growth=0.10, revenue_growth=0.09, pe_forward=18.0, dividend_yield=0.02),
    ]

    with patch.object(sb, "_fetch_ticker_metrics", return_value=target), \
         patch.object(sb, "_find_sector_peers", return_value=[p["ticker"] for p in peers]), \
         patch.object(sb, "_fetch_peer_metrics", return_value=peers):
        result = sb.classify_style_box("HIGH")

    assert result is not None
    assert result["size"] == "Large"
    assert result["style"] == "Growth"
    assert result["cell"] == "Large-Growth"
    # Full 9-cell grid with exactly one active
    assert len(result["cells"]) == 9
    active = [c for c in result["cells"] if c["active"]]
    assert len(active) == 1
    assert active[0]["key"] == "Large-Growth"
    assert result["peer_count"] == 4


def test_classify_style_box_value_tilt():
    target = _make_metrics("LOW", market_cap=3e9, pe_trailing=8.0, price_to_book=1.1,
                           dividend_yield=0.06, earnings_growth=0.01, revenue_growth=0.0,
                           pe_forward=9.0)
    peers = [
        _make_metrics("P1", pe_trailing=25.0, price_to_book=6.0, dividend_yield=0.015, earnings_growth=0.15, revenue_growth=0.10, pe_forward=22.0),
        _make_metrics("P2", pe_trailing=30.0, price_to_book=8.0, dividend_yield=0.01, earnings_growth=0.20, revenue_growth=0.14, pe_forward=27.0),
        _make_metrics("P3", pe_trailing=28.0, price_to_book=7.0, dividend_yield=0.012, earnings_growth=0.18, revenue_growth=0.12, pe_forward=24.0),
        _make_metrics("P4", pe_trailing=24.0, price_to_book=5.5, dividend_yield=0.014, earnings_growth=0.14, revenue_growth=0.11, pe_forward=21.0),
    ]

    with patch.object(sb, "_fetch_ticker_metrics", return_value=target), \
         patch.object(sb, "_find_sector_peers", return_value=[p["ticker"] for p in peers]), \
         patch.object(sb, "_fetch_peer_metrics", return_value=peers):
        result = sb.classify_style_box("LOW")

    assert result is not None
    assert result["size"] == "Mid"
    assert result["style"] == "Value"
    assert result["value_score"] > result["growth_score"]


def test_classify_style_box_handles_missing_target():
    with patch.object(sb, "_fetch_ticker_metrics", return_value=None):
        assert sb.classify_style_box("GHOST") is None
