"""Tests for the data-integrity gate (directional vs sizing grade).

Offline by design — the survivorship probe takes an injected fetch function, so
no test touches the network."""

import pandas as pd
import pytest

from backend.services.data_integrity import (
    DataGrade,
    DataIntegrityError,
    KNOWN_DELISTED,
    SurvivorshipReport,
    assert_survivorship_safe,
    data_grade,
    get_guarantees,
    is_sizing_grade,
    require_sizing_grade,
    survivorship_probe,
)


class TestGradeClassification:
    def test_yfinance_is_directional(self):
        assert data_grade("yfinance") is DataGrade.DIRECTIONAL
        assert is_sizing_grade("yfinance") is False

    def test_sharadar_is_sizing(self):
        assert data_grade("sharadar") is DataGrade.SIZING
        assert is_sizing_grade("sharadar") is True

    def test_unknown_source_assumed_directional(self):
        g = get_guarantees("some_random_feed")
        assert g.grade is DataGrade.DIRECTIONAL
        assert "assumed directional" in g.notes.lower()

    def test_case_insensitive(self):
        assert data_grade("YFinance") is DataGrade.DIRECTIONAL

    def test_sizing_requires_both_guarantees(self):
        # A source with only one of the two guarantees is still directional.
        from backend.services.data_integrity import SourceGuarantees
        prices_only = SourceGuarantees("x", survivorship_free=True, point_in_time_fundamentals=False)
        funds_only = SourceGuarantees("y", survivorship_free=False, point_in_time_fundamentals=True)
        assert prices_only.grade is DataGrade.DIRECTIONAL
        assert funds_only.grade is DataGrade.DIRECTIONAL


class TestRequireSizingGrade:
    def test_directional_source_fails_loud(self):
        with pytest.raises(DataIntegrityError, match="directional-grade, not sizing-grade"):
            require_sizing_grade("yfinance", context="single-stock momentum backtest")

    def test_sizing_source_passes(self):
        require_sizing_grade("sharadar")  # must not raise

    def test_error_message_names_the_context(self):
        with pytest.raises(DataIntegrityError, match="my-candidate"):
            require_sizing_grade("yfinance", context="my-candidate")


class TestSurvivorshipProbe:
    def test_yfinance_like_source_flagged_biased(self):
        # yfinance returns nothing for delisted names → biased.
        def fetch_none(_ticker):
            return None

        report = survivorship_probe(fetch_none, source="yfinance")
        assert report.survivorship_biased is True
        assert report.n_returned == 0
        assert set(report.missing) == set(KNOWN_DELISTED)
        # consistent: a directional source being biased is expected, no raise
        assert_survivorship_safe(report)

    def test_clean_source_not_biased(self):
        # A source that returns full history for every delisted name is clean.
        def fetch_full(_ticker):
            return pd.Series(range(250), dtype=float)

        report = survivorship_probe(fetch_full, source="sharadar")
        assert report.survivorship_biased is False
        assert report.n_returned == report.n_probed
        assert report.missing == []
        assert_survivorship_safe(report)  # sizing + clean → no raise

    def test_registered_sizing_but_biased_fails_loud(self):
        # The key protection: a source CLAIMING sizing-grade that empirically
        # fails the probe must blow up, not silently taint a backtest.
        def fetch_none(_ticker):
            return None

        report = survivorship_probe(fetch_none, source="sharadar")  # sizing in registry
        assert report.grade is DataGrade.SIZING
        with pytest.raises(DataIntegrityError, match="FAILED the survivorship probe"):
            assert_survivorship_safe(report)

    def test_short_series_counts_as_missing(self):
        def fetch_short(_ticker):
            return pd.Series(range(10), dtype=float)  # < min_points

        report = survivorship_probe(fetch_short, source="yfinance", min_points=60)
        assert report.n_returned == 0
        assert report.survivorship_biased is True

    def test_fetch_exception_counts_as_missing(self):
        def fetch_raises(_ticker):
            raise RuntimeError("api down")

        report = survivorship_probe(fetch_raises, source="yfinance")
        assert report.survivorship_biased is True
        assert report.n_returned == 0
