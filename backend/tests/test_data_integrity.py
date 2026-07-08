"""Tests for the data-integrity gate (directional vs sizing grade).

Offline by design — the survivorship probe takes an injected fetch function, so
no test touches the network."""

import pandas as pd
import pytest

from backend.services.data_integrity import (
    DataGrade,
    DataIntegrityError,
    KNOWN_DELISTED,
    SOURCE_GUARANTEES,
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


class TestSizingGradeBypassAttempts:
    """Adversarial: prove require_sizing_grade fails loud on EVERY directional
    path, and that the registry can't quietly mislabel a source."""

    @pytest.mark.parametrize("source", sorted(SOURCE_GUARANTEES))
    def test_every_registered_source_gate_matches_grade(self, source):
        if SOURCE_GUARANTEES[source].grade is DataGrade.SIZING:
            require_sizing_grade(source)  # must NOT raise
        else:
            with pytest.raises(DataIntegrityError):
                require_sizing_grade(source)

    @pytest.mark.parametrize("source", ["yfinance", "fmp", "alpha_vantage",
                                        "polygon", "finnhub", "unknown_feed", "YFINANCE"])
    def test_directional_paths_all_raise(self, source):
        with pytest.raises(DataIntegrityError):
            require_sizing_grade(source)

    def test_only_sizing_sources_pass(self):
        passing = [s for s in SOURCE_GUARANTEES if not _raises(s)]
        assert passing == ["sharadar"]  # the ONLY sizing-grade source today

    def test_registry_has_no_accidental_sizing_source(self):
        # A source is sizing ONLY if it declares BOTH guarantees.
        for name, g in SOURCE_GUARANTEES.items():
            if g.grade is DataGrade.SIZING:
                assert g.survivorship_free and g.point_in_time_fundamentals


def _raises(source: str) -> bool:
    try:
        require_sizing_grade(source)
        return False
    except DataIntegrityError:
        return True


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


class TestB6B10Hardening:
    """B6: non-string sources fail the gate as DataIntegrityError, never
    AttributeError (FINDINGS F4). B10: malformed fetcher returns count as
    missing, never TypeError (FINDINGS F6)."""

    @pytest.mark.parametrize("bad_source", [None, 42, 3.14, ["yfinance"], object()])
    def test_non_string_source_raises_integrity_error(self, bad_source):
        with pytest.raises(DataIntegrityError):
            require_sizing_grade(bad_source)

    def test_non_string_source_is_directional(self):
        from backend.services.data_integrity import get_guarantees
        g = get_guarantees(None)
        assert g.survivorship_free is False
        assert g.point_in_time_fundamentals is False

    def test_probe_scalar_return_counts_as_missing(self):
        report = survivorship_probe(lambda _t: 42.0, source="yfinance")
        assert report.n_returned == 0
        assert report.survivorship_biased is True

    def test_probe_generator_return_counts_as_missing(self):
        report = survivorship_probe(lambda _t: (x for x in range(300)),
                                    source="yfinance")
        assert report.n_returned == 0
        assert report.survivorship_biased is True
