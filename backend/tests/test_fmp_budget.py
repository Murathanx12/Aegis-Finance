"""FMP daily-budget ledger (2026-07-17).

The congress-IC collector died on 402 at its 07:30 ET slot because
fallback-provider traffic burned the shared 250/day quota overnight.
These tests pin the meter: non-priority callers stop at budget-reserve,
priority callers may draw the reserve, a live 402 fast-fails everyone,
and the ledger rolls at the UTC day boundary. All offline.
"""

from unittest.mock import MagicMock, patch

import pytest

from backend.services import fmp_budget


@pytest.fixture(autouse=True)
def _fresh_ledger():
    fmp_budget._reset_for_tests()
    yield
    fmp_budget._reset_for_tests()


class TestLedger:
    def test_non_priority_stops_at_reserve_priority_continues(self):
        budget, reserve = fmp_budget._cfg()
        ceiling = budget - reserve
        for _ in range(ceiling):
            assert fmp_budget.try_spend() is True
        # non-priority ceiling reached
        assert fmp_budget.try_spend() is False
        # the reserved slice is still open to priority callers
        for _ in range(reserve):
            assert fmp_budget.try_spend(priority=True) is True
        # and then the hard ceiling applies to priority too
        assert fmp_budget.try_spend(priority=True) is False

    def test_mark_exhausted_fast_fails_everyone(self):
        assert fmp_budget.try_spend() is True
        fmp_budget.mark_exhausted()
        assert fmp_budget.try_spend() is False
        assert fmp_budget.try_spend(priority=True) is False

    def test_utc_day_rollover_resets_spend_and_exhaustion(self):
        fmp_budget.mark_exhausted()
        assert fmp_budget.try_spend(priority=True) is False
        with fmp_budget._LOCK:
            fmp_budget._STATE["date"] = "2000-01-01"  # force a stale day
        assert fmp_budget.try_spend(priority=True) is True

    def test_snapshot_reports_state(self):
        fmp_budget.try_spend()
        fmp_budget.try_spend()
        snap = fmp_budget.snapshot()
        assert snap["spent"] == 2
        assert snap["exhausted"] is False
        assert snap["daily_budget"] > snap["priority_reserve"] > 0

    def test_multi_unit_spend(self):
        budget, reserve = fmp_budget._cfg()
        assert fmp_budget.try_spend(n=budget - reserve) is True
        assert fmp_budget.try_spend(n=1) is False
        assert fmp_budget.try_spend(n=reserve, priority=True) is True


class TestCallerWiring:
    def test_fmp_provider_skips_http_when_budget_denied(self):
        from backend.services.providers.base import ProviderUnavailable
        from backend.services.providers.fmp_provider import FMPProvider

        provider = FMPProvider()
        with patch.object(fmp_budget, "try_spend", return_value=False), \
             patch.object(provider, "is_available", return_value=True), \
             patch("backend.services.providers.fmp_provider.requests.get") as http:
            with pytest.raises(ProviderUnavailable):
                provider._get("quote/AAPL")
        http.assert_not_called()

    def test_fmp_provider_402_marks_exhausted(self):
        from backend.services.providers.base import ProviderUnavailable
        from backend.services.providers.fmp_provider import FMPProvider

        provider = FMPProvider()
        resp = MagicMock(status_code=402)
        with patch.object(provider, "is_available", return_value=True), \
             patch("backend.services.providers.fmp_provider.requests.get",
                   return_value=resp), \
             patch("backend.services.providers.fmp_provider.api_keys") as keys:
            keys.fmp = "test-key"
            with pytest.raises(ProviderUnavailable):
                provider._get("quote/AAPL")
        assert fmp_budget.snapshot()["exhausted"] is True

    def test_congress_collector_skips_http_when_budget_denied(self):
        from backend.services import congress_trades

        with patch.object(fmp_budget, "try_spend", return_value=False), \
             patch.object(congress_trades.api_keys, "has", return_value=True), \
             patch("backend.services.congress_trades.requests.get") as http:
            with pytest.raises(RuntimeError, match="budget exhausted"):
                congress_trades._fmp_get("senate-latest", page=0, limit=100)
        http.assert_not_called()

    def test_congress_collector_402_marks_exhausted(self):
        from backend.services import congress_trades

        resp = MagicMock(status_code=402)
        with patch.object(congress_trades.api_keys, "has", return_value=True), \
             patch.object(congress_trades.api_keys, "fmp", "test-key", create=True), \
             patch("backend.services.congress_trades.requests.get",
                   return_value=resp):
            with pytest.raises(RuntimeError, match="402"):
                congress_trades._fmp_get("senate-latest", page=0, limit=100)
        assert fmp_budget.snapshot()["exhausted"] is True

    def test_esg_returns_none_when_budget_denied(self):
        from backend.services import esg

        with patch.object(fmp_budget, "try_spend", return_value=False), \
             patch.object(esg.api_keys, "has", return_value=True), \
             patch("backend.services.esg.cache_get", return_value=None), \
             patch("backend.services.esg.requests.get") as http:
            assert esg.fetch_fmp_esg("AAPL") is None
        http.assert_not_called()
