"""Tests for ESG score blender (Finnhub + FMP)."""

from __future__ import annotations

from unittest.mock import patch


from backend.services import esg


def test_normalise_finnhub_flips_scale():
    """Finnhub uses risk-style 0..40 (lower=better); we flip to 0..100 higher=better."""
    blob = {
        "totalESG": 12.0,            # → 100 - 30 = 70
        "environmentScore": 8.0,     # → 100 - 20 = 80
        "socialScore": 16.0,          # → 100 - 40 = 60
        "governanceScore": 10.0,      # → 100 - 25 = 75
        "controversyLevel": 1,
        "controversyCategoriesNumber": 0,
    }
    out = esg._normalise_finnhub(blob)
    assert out["total_score"] == 70.0
    assert out["environmental"] == 80.0
    assert out["social"] == 60.0
    assert out["governance"] == 75.0
    assert out["controversy_level"] == "low"
    assert out["controversy_count"] == 0


def test_normalise_finnhub_severe_controversy():
    blob = {
        "totalESG": 30.0,
        "controversyLevel": 5,
        "controversyCategoriesNumber": 4,
    }
    out = esg._normalise_finnhub(blob)
    assert out["controversy_level"] == "severe"


def test_normalise_fmp_pass_through():
    blob = {
        "ESGScore": 78.0,
        "environmentalScore": 80.0,
        "socialScore": 75.0,
        "governanceScore": 79.0,
        "ESGRiskRating": "Low",
        "date": "2025-12-31",
    }
    out = esg._normalise_fmp(blob)
    assert out["total_score"] == 78.0
    assert out["environmental"] == 80.0
    assert out["controversy_level"] == "low"
    assert out["as_of"] == "2025-12-31"


def test_grade_buckets():
    assert esg._grade(90) == "A+"
    assert esg._grade(78) == "A"
    assert esg._grade(70) == "B"
    assert esg._grade(60) == "C"
    assert esg._grade(45) == "D"
    assert esg._grade(20) == "F"
    assert esg._grade(None) is None


def test_worst_controversy_picks_max():
    assert esg._worst_controversy("low", "high") == "high"
    assert esg._worst_controversy("low", None) == "low"
    assert esg._worst_controversy(None, "severe") == "severe"
    assert esg._worst_controversy(None, None) is None


def test_avg_handles_none():
    assert esg._avg(None, None) is None
    assert esg._avg(50, None, 70) == 60.0
    assert esg._avg(80) == 80.0


def test_compute_blends_two_sources():
    finnhub_norm = {
        "environmental": 70.0, "social": 60.0, "governance": 80.0,
        "total_score": 70.0,
        "controversy_level": "low", "controversy_count": 1,
    }
    fmp_norm = {
        "environmental": 80.0, "social": 70.0, "governance": 90.0,
        "total_score": 80.0,
        "controversy_level": "low", "controversy_count": None,
        "as_of": "2025-12-31",
    }
    with patch.object(esg, "fetch_finnhub_esg", return_value={"_raw": "fh"}), \
         patch.object(esg, "_normalise_finnhub", return_value=finnhub_norm), \
         patch.object(esg, "fetch_fmp_esg", return_value={"_raw": "fmp"}), \
         patch.object(esg, "_normalise_fmp", return_value=fmp_norm):
        # Bypass cache by using a unique ticker
        from backend.cache import cache_clear
        cache_clear()
        out = esg.compute_esg_score("TEST_BLEND_1")
    assert out["sources"] == ["finnhub", "fmp"]
    assert out["environmental"] == 75.0
    assert out["social"] == 65.0
    assert out["governance"] == 85.0
    assert out["total_score"] == 75.0
    assert out["grade"] == "A"
    assert out["controversies"]["level"] == "low"


def test_compute_no_data_returns_error():
    """Compute returns an error block when both providers return None."""
    with patch.object(esg, "fetch_finnhub_esg", return_value=None), \
         patch.object(esg, "fetch_fmp_esg", return_value=None):
        from backend.cache import cache_clear
        cache_clear()
        out = esg.compute_esg_score("TEST_NODATA_1")
    assert "error" in out
    assert out["sources"] == []


def test_compute_single_source():
    """Only one provider available — output should still be valid."""
    finnhub_norm = {
        "environmental": 70.0, "social": 60.0, "governance": 80.0,
        "total_score": 70.0,
        "controversy_level": "moderate", "controversy_count": 2,
    }
    with patch.object(esg, "fetch_finnhub_esg", return_value={"_raw": "fh"}), \
         patch.object(esg, "_normalise_finnhub", return_value=finnhub_norm), \
         patch.object(esg, "fetch_fmp_esg", return_value=None):
        from backend.cache import cache_clear
        cache_clear()
        out = esg.compute_esg_score("TEST_SOLO_1")
    assert out["sources"] == ["finnhub"]
    assert out["total_score"] == 70.0
    assert out["controversies"]["level"] == "moderate"
    assert out["controversies"]["count_12m"] == 2


def test_compute_empty_ticker():
    out = esg.compute_esg_score("")
    assert "error" in out
