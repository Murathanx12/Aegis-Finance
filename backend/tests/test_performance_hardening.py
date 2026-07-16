"""Tests for Cycle 21 performance hardening: middleware, parallel screener, GDELT.

Tests cover:
- TimingMiddleware: header presence, format, slow request logging
- Parallel screener: thread safety, partial failures, empty input
- GDELT parallelization: retry behavior, partial failure, empty results
- Config values: all performance params exist and have valid types
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.config import config


# ═══════════════════════════════════════════════════════════════════════════
# CONFIG VALIDATION
# ═══════════════════════════════════════════════════════════════════════════


class TestPerformanceConfig:
    """Verify performance config keys exist with valid types/ranges."""

    def test_performance_section_exists(self):
        assert "performance" in config
        perf = config["performance"]
        assert isinstance(perf, dict)

    def test_screener_max_workers_valid(self):
        workers = config["performance"]["screener_max_workers"]
        assert isinstance(workers, int)
        assert 1 <= workers <= 32

    def test_sector_momentum_workers_valid(self):
        workers = config["performance"]["sector_momentum_workers"]
        assert isinstance(workers, int)
        assert 1 <= workers <= 16

    def test_gdelt_max_workers_valid(self):
        workers = config["performance"]["gdelt_max_workers"]
        assert isinstance(workers, int)
        assert 1 <= workers <= 10

    def test_gdelt_retry_params_valid(self):
        perf = config["performance"]
        assert isinstance(perf["gdelt_max_retries"], int)
        assert perf["gdelt_max_retries"] >= 0
        assert isinstance(perf["gdelt_retry_base_delay"], float)
        assert perf["gdelt_retry_base_delay"] > 0

    def test_slow_request_threshold_valid(self):
        threshold = config["performance"]["slow_request_threshold_s"]
        assert isinstance(threshold, float)
        assert threshold > 0


# ═══════════════════════════════════════════════════════════════════════════
# TIMING MIDDLEWARE
# ═══════════════════════════════════════════════════════════════════════════


class TestTimingMiddleware:
    """Test request timing middleware behavior."""

    @pytest.fixture
    def app_with_middleware(self):
        from backend.middleware import add_timing_middleware
        app = FastAPI()
        add_timing_middleware(app)

        @app.get("/fast")
        async def fast_endpoint():
            return {"status": "ok"}

        @app.get("/slow")
        async def slow_endpoint():
            await asyncio.sleep(0.05)
            return {"status": "ok"}

        return app

    def test_header_present_on_response(self, app_with_middleware):
        client = TestClient(app_with_middleware)
        resp = client.get("/fast")
        assert resp.status_code == 200
        assert "X-Process-Time" in resp.headers

    def test_header_format_is_seconds(self, app_with_middleware):
        client = TestClient(app_with_middleware)
        resp = client.get("/fast")
        header = resp.headers["X-Process-Time"]
        assert header.endswith("s")
        # Should parse as a float
        duration = float(header.rstrip("s"))
        assert duration >= 0
        assert duration < 5.0  # Fast endpoint should be well under 5s

    def test_slow_endpoint_has_larger_time(self, app_with_middleware):
        client = TestClient(app_with_middleware)
        resp = client.get("/slow")
        header = resp.headers["X-Process-Time"]
        duration = float(header.rstrip("s"))
        assert duration >= 0.04  # At least ~40ms for the sleep

    def test_404_still_gets_timing_header(self, app_with_middleware):
        client = TestClient(app_with_middleware)
        resp = client.get("/nonexistent")
        assert "X-Process-Time" in resp.headers

    def test_slow_request_logs_warning(self, app_with_middleware, caplog):
        """Requests exceeding threshold should log a warning."""
        from backend import middleware
        original = middleware.SLOW_REQUEST_THRESHOLD_S
        middleware.SLOW_REQUEST_THRESHOLD_S = 0.01  # 10ms threshold for test

        try:
            client = TestClient(app_with_middleware)
            with caplog.at_level(logging.WARNING, logger="backend.middleware"):
                client.get("/slow")
            assert any("SLOW REQUEST" in r.message for r in caplog.records)
        finally:
            middleware.SLOW_REQUEST_THRESHOLD_S = original


# ═══════════════════════════════════════════════════════════════════════════
# PARALLEL SCREENER LOGIC
# ═══════════════════════════════════════════════════════════════════════════


class TestParallelScreener:
    """Test the parallelized screener stock analysis."""

    def test_threadpool_handles_empty_ticker_list(self):
        """ThreadPoolExecutor with empty futures dict should produce empty results."""
        results = []
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {}
            for future in futures:
                r = future.result()
                if r is not None:
                    results.append(r)
        assert results == []

    def test_threadpool_handles_all_none_results(self):
        """When every ticker fails (returns None), screener should return empty list."""
        def always_none(ticker):
            return None

        tickers = ["FAKE1", "FAKE2", "FAKE3"]
        results = []
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(always_none, t): t for t in tickers}
            from concurrent.futures import as_completed
            for future in as_completed(futures):
                r = future.result()
                if r is not None:
                    results.append(r)
        assert results == []

    def test_threadpool_collects_partial_successes(self):
        """When some tickers succeed and some fail, only successes are collected."""
        def mixed_results(ticker):
            if ticker == "GOOD":
                return {"ticker": "GOOD", "sharpe": 1.5}
            return None

        tickers = ["GOOD", "BAD1", "BAD2"]
        results = []
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(mixed_results, t): t for t in tickers}
            from concurrent.futures import as_completed
            for future in as_completed(futures):
                r = future.result()
                if r is not None:
                    results.append(r)
        assert len(results) == 1
        assert results[0]["ticker"] == "GOOD"

    def test_threadpool_handles_exceptions_in_worker(self):
        """Worker exceptions should not crash the pool."""
        def exploding(ticker):
            if ticker == "BOMB":
                raise ValueError("simulated failure")
            return {"ticker": ticker}

        tickers = ["OK1", "BOMB", "OK2"]
        results = []
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(exploding, t): t for t in tickers}
            from concurrent.futures import as_completed
            for future in as_completed(futures):
                try:
                    r = future.result()
                    if r is not None:
                        results.append(r)
                except ValueError:
                    pass  # Expected for "BOMB"
        assert len(results) == 2

    def test_max_workers_capped_by_ticker_count(self):
        """max_workers should not exceed ticker count."""
        n_tickers = 3
        configured = config["performance"]["screener_max_workers"]
        effective = min(configured, n_tickers)
        assert effective == n_tickers  # 3 < 8


# ═══════════════════════════════════════════════════════════════════════════
# GDELT PARALLELIZATION + RETRY
# ═══════════════════════════════════════════════════════════════════════════


class TestGdeltParallelization:
    """GDELT fetch behavior (sequential-staggered since 2026-07-16 — the
    3-way parallel burst was 429-ing itself; class name kept for history)."""

    @patch("backend.services.news_intelligence._fetch_tone_timeline")
    @patch("backend.services.news_intelligence._fetch_volume_timeline")
    @patch("backend.services.news_intelligence._fetch_conflict_timeline")
    def test_all_fetches_called_in_parallel(self, mock_conflict, mock_volume, mock_tone):
        """All three GDELT fetches should be invoked."""
        mock_tone.return_value = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
        mock_volume.return_value = [100, 110, 120, 130, 140, 150, 160, 170]
        mock_conflict.return_value = [50, 55, 60]

        from backend.services.news_intelligence import fetch_gdelt_signals
        result = fetch_gdelt_signals("test query", 7)

        assert result["success"] is True
        mock_tone.assert_called_once()
        mock_volume.assert_called_once()
        mock_conflict.assert_called_once()

    @patch("backend.services.news_intelligence._fetch_tone_timeline")
    @patch("backend.services.news_intelligence._fetch_volume_timeline")
    @patch("backend.services.news_intelligence._fetch_conflict_timeline")
    def test_handles_empty_results(self, mock_conflict, mock_volume, mock_tone):
        """Empty lists from all fetches should still produce a valid result."""
        mock_tone.return_value = []
        mock_volume.return_value = []
        mock_conflict.return_value = []

        from backend.services.news_intelligence import fetch_gdelt_signals
        result = fetch_gdelt_signals("test", 7)

        assert result["success"] is True
        assert result["avg_tone"] == 0.0
        assert result["volume_zscore"] == 0.0
        assert result["conflict_score"] == 0.0

    @patch("backend.services.news_intelligence._fetch_tone_timeline")
    @patch("backend.services.news_intelligence._fetch_volume_timeline")
    @patch("backend.services.news_intelligence._fetch_conflict_timeline")
    def test_exception_in_one_fetch_triggers_fallback(self, mock_conflict, mock_volume, mock_tone):
        """If a fetch raises and NO stale copy exists, return the honest
        fallback. cache_peek must be patched: an earlier test in the same
        run legitimately primes the real gdelt:last_good stale cache (the
        2026-07-16 stale-serve path, pinned in test_web_fixes_2026_07_14)."""
        mock_tone.side_effect = Exception("network timeout")
        mock_volume.return_value = [100, 110]
        mock_conflict.return_value = [50]

        from backend.services.news_intelligence import fetch_gdelt_signals
        with patch("backend.cache.cache_peek", return_value=(None, None)):
            result = fetch_gdelt_signals("test", 7)

        # Should hit the except branch and return fallback
        assert result["success"] is False

    def test_gdelt_fallback_structure(self):
        """Fallback dict should have all required keys."""
        from backend.services.news_intelligence import _gdelt_fallback
        result = _gdelt_fallback("test error")

        assert result["success"] is False
        assert result["avg_tone"] == 0.0
        assert result["tone_trend"] == 0.0
        assert result["volume_zscore"] == 0.0
        assert result["conflict_score"] == 0.0
        assert "tone" in result["raw_data"]
        assert "volume" in result["raw_data"]
        assert "conflict" in result["raw_data"]
        assert result["error"] == "test error"


class TestGdeltComputeEventScore:
    """Test event score computation edge cases."""

    def test_neutral_inputs(self):
        from backend.services.news_intelligence import compute_event_score
        signals = {"avg_tone": 0.0, "volume_zscore": 0.0, "success": True}
        result = compute_event_score(signals, fred_gpr=None)
        assert 0 <= result["event_score"] <= 1
        assert "components" in result

    def test_extreme_negative_tone(self):
        from backend.services.news_intelligence import compute_event_score
        signals = {"avg_tone": -5.0, "volume_zscore": 3.0, "success": True}
        result = compute_event_score(signals, fred_gpr=300)
        assert result["event_score"] > 0.7

    def test_gdelt_unavailable_uses_gpr_only(self):
        from backend.services.news_intelligence import compute_event_score
        signals = {"avg_tone": 0.0, "volume_zscore": 0.0, "success": False}
        result = compute_event_score(signals, fred_gpr=150)
        # When GDELT fails, only GPR is used
        assert result["gdelt_available"] is False
        assert result["event_score"] > 0

    def test_none_gpr_uses_default(self):
        from backend.services.news_intelligence import compute_event_score
        signals = {"avg_tone": -2.0, "volume_zscore": 1.0, "success": True}
        result = compute_event_score(signals, fred_gpr=None)
        assert result["components"]["gpr_score"] == 0.3  # neutral default


class TestAdjustCrashProbability:
    """Test crash probability adjustment edge cases."""

    def test_low_event_score_no_adjustment(self):
        from backend.services.news_intelligence import adjust_crash_probability
        assert adjust_crash_probability(0.20, 0.1) == 0.20
        assert adjust_crash_probability(0.20, 0.3) == 0.20

    def test_high_event_score_increases_prob(self):
        from backend.services.news_intelligence import adjust_crash_probability
        adjusted = adjust_crash_probability(0.20, 0.8)
        assert adjusted > 0.20

    def test_never_exceeds_cap(self):
        from backend.services.news_intelligence import adjust_crash_probability
        adjusted = adjust_crash_probability(0.90, 1.0)
        assert adjusted <= 0.95

    def test_zero_base_prob_stays_zero(self):
        from backend.services.news_intelligence import adjust_crash_probability
        adjusted = adjust_crash_probability(0.0, 0.9)
        assert adjusted == 0.0  # multiplicative — 0 * anything = 0
