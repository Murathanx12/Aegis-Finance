"""Tests for Seeking Alpha-style A–F factor grades."""

from unittest.mock import patch

import pytest

from backend.services import factor_grades as fg


@pytest.mark.parametrize("pct,expected", [
    (100.0, "A+"),
    (95.0, "A+"),
    (92.0, "A"),
    (87.0, "A-"),
    (75.0, "B"),
    (55.0, "C+"),
    (35.0, "C-"),
    (15.0, "D"),
    (5.0, "F"),
    (0.0, "F"),
])
def test_percentile_to_grade_bands(pct, expected):
    assert fg.percentile_to_grade(pct) == expected


def test_percentile_to_grade_none():
    assert fg.percentile_to_grade(None) is None


def test_percentile_to_grade_clamps_outside_range():
    assert fg.percentile_to_grade(120.0) == "A+"
    assert fg.percentile_to_grade(-20.0) == "F"


def test_grade_color_categories():
    assert fg._grade_color("A+") == "green"
    assert fg._grade_color("B-") == "emerald"
    assert fg._grade_color("C+") == "amber"
    assert fg._grade_color("D") == "orange"
    assert fg._grade_color("F") == "red"
    assert fg._grade_color(None) == "gray"


def _stub_relval(composite: float = 65.0):
    return {
        "ticker": "STUB",
        "sector": "Technology",
        "peer_count": 8,
        "composite_score": composite,
        "rankings": {
            "pe_trailing": {"value": 18.0, "percentile": 30.0, "valuation_percentile": 70.0},
            "pe_forward": {"value": 16.0, "percentile": 25.0, "valuation_percentile": 75.0},
            "peg_ratio": {"value": 1.2, "percentile": 35.0, "valuation_percentile": 65.0},
            "ev_ebitda": {"value": 12.0, "percentile": 40.0, "valuation_percentile": 60.0},
            "price_to_book": {"value": 3.0, "percentile": 20.0, "valuation_percentile": 80.0},
            "revenue_growth": {"value": 0.18, "percentile": 82.0, "valuation_percentile": 82.0},
            "earnings_growth": {"value": 0.22, "percentile": 85.0, "valuation_percentile": 85.0},
            "roe": {"value": 0.28, "percentile": 90.0, "valuation_percentile": 90.0},
            "profit_margin": {"value": 0.18, "percentile": 88.0, "valuation_percentile": 88.0},
            "fcf_yield": {"value": 0.05, "percentile": 70.0, "valuation_percentile": 70.0},
        },
    }


def test_value_grade_uses_composite():
    grade, pct, detail = fg._value_grade_from_relval(_stub_relval(75.0))
    assert grade == "B"  # 70-80 band → B
    assert pct == 75.0
    assert "pe_trailing" in detail


def test_growth_grade_averages_revenue_and_earnings_percentiles():
    grade, pct, detail = fg._growth_grade_from_relval(_stub_relval())
    assert pct == pytest.approx(83.5)
    assert grade == "B+"  # 80-85 band → B+
    assert "revenue_growth" in detail
    assert "earnings_growth" in detail


def test_profitability_grade_averages_roe_margin_fcf():
    _, pct, detail = fg._profitability_grade_from_relval(_stub_relval())
    assert pct == pytest.approx((90 + 88 + 70) / 3)
    assert set(detail.keys()) == {"roe", "profit_margin", "fcf_yield"}


def test_full_report_card_shape():
    with patch.object(fg, "get_relative_valuation", return_value=_stub_relval()):
        # Force momentum + revisions paths to return nothing so we deterministically
        # verify the value/growth/profit columns
        with patch.object(fg, "_momentum_grade", return_value=(None, None, {})), \
             patch.object(fg, "_revisions_grade", return_value=(None, None, {})):
            card = fg.get_factor_report_card("STUB")

    assert card is not None
    assert card["ticker"] == "STUB"
    assert set(card["components"].keys()) == {"value", "growth", "profitability", "momentum", "revisions"}
    assert card["components"]["value"]["grade"] is not None
    assert card["components"]["momentum"]["grade"] is None
    # Overall grade averages only the populated factors
    assert card["overall_grade"] is not None


def test_report_card_none_when_no_relval():
    with patch.object(fg, "get_relative_valuation", return_value=None):
        assert fg.get_factor_report_card("GHOST") is None
