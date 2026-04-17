"""Tests for the multi-source provider registry (Chunk 1)."""

from __future__ import annotations

import pandas as pd
import pytest

from backend.services.providers import (
    AnalystEstimates,
    BaseProvider,
    EquitySnapshot,
    FundamentalMetrics,
    ProviderRegistry,
    ProviderUnavailable,
    registry,
)


# ── Fake providers for deterministic testing ──────────────────────────────────


class _FakeProvider(BaseProvider):
    def __init__(
        self,
        name: str,
        caps: list,
        available: bool = True,
        returns: dict | None = None,
        raises: dict | None = None,
    ):
        self.name = name
        self.capabilities = caps
        self._available = available
        self._returns = returns or {}
        self._raises = raises or {}
        self.calls: list[str] = []

    def is_available(self) -> bool:
        return self._available

    def _dispatch(self, cap: str, default=None):
        self.calls.append(cap)
        if cap in self._raises:
            raise self._raises[cap]
        return self._returns.get(cap, default)

    def get_equity_history(self, ticker, start, end):
        return self._dispatch("equity_history")

    def get_equity_snapshot(self, ticker):
        return self._dispatch("equity_snapshot")

    def get_fundamentals(self, ticker):
        return self._dispatch("fundamentals")

    def get_analyst_estimates(self, ticker):
        return self._dispatch("analyst_estimates")


# ── Registry behavior ────────────────────────────────────────────────────────


class TestRegistryFallback:
    def test_first_provider_wins(self):
        r = ProviderRegistry()
        a = _FakeProvider("a", ["equity_snapshot"], returns={"equity_snapshot": EquitySnapshot(ticker="AAPL", price=100.0, source="a")})
        b = _FakeProvider("b", ["equity_snapshot"], returns={"equity_snapshot": EquitySnapshot(ticker="AAPL", price=101.0, source="b")})
        r._providers = {"a": a, "b": b}
        r.set_priority("equity_snapshot", ["a", "b"])
        snap = r.get_equity_snapshot("AAPL")
        assert snap.source == "a"
        assert snap.price == 100.0
        assert a.calls == ["equity_snapshot"]
        assert b.calls == []

    def test_falls_back_on_none(self):
        r = ProviderRegistry()
        a = _FakeProvider("a", ["equity_snapshot"], returns={"equity_snapshot": None})
        b = _FakeProvider("b", ["equity_snapshot"], returns={"equity_snapshot": EquitySnapshot(ticker="AAPL", price=101.0, source="b")})
        r._providers = {"a": a, "b": b}
        r.set_priority("equity_snapshot", ["a", "b"])
        snap = r.get_equity_snapshot("AAPL")
        assert snap.source == "b"
        assert a.calls == ["equity_snapshot"]
        assert b.calls == ["equity_snapshot"]

    def test_falls_back_on_unavailable(self):
        r = ProviderRegistry()
        a = _FakeProvider("a", ["equity_snapshot"], raises={"equity_snapshot": ProviderUnavailable("no key")})
        b = _FakeProvider("b", ["equity_snapshot"], returns={"equity_snapshot": EquitySnapshot(ticker="AAPL", price=99.0, source="b")})
        r._providers = {"a": a, "b": b}
        r.set_priority("equity_snapshot", ["a", "b"])
        snap = r.get_equity_snapshot("AAPL")
        assert snap.source == "b"

    def test_skips_providers_not_declaring_capability(self):
        r = ProviderRegistry()
        a = _FakeProvider("a", [], returns={"equity_snapshot": EquitySnapshot(ticker="AAPL", price=1.0, source="a")})
        b = _FakeProvider("b", ["equity_snapshot"], returns={"equity_snapshot": EquitySnapshot(ticker="AAPL", price=2.0, source="b")})
        r._providers = {"a": a, "b": b}
        r.set_priority("equity_snapshot", ["a", "b"])
        snap = r.get_equity_snapshot("AAPL")
        assert snap.source == "b"
        assert a.calls == []  # capability filter prevented the call

    def test_skips_unavailable_providers(self):
        r = ProviderRegistry()
        a = _FakeProvider("a", ["equity_snapshot"], available=False)
        b = _FakeProvider("b", ["equity_snapshot"], returns={"equity_snapshot": EquitySnapshot(ticker="AAPL", price=50.0, source="b")})
        r._providers = {"a": a, "b": b}
        r.set_priority("equity_snapshot", ["a", "b"])
        snap = r.get_equity_snapshot("AAPL")
        assert snap.source == "b"
        assert a.calls == []

    def test_unexpected_exception_still_falls_back(self):
        r = ProviderRegistry()
        a = _FakeProvider("a", ["equity_snapshot"], raises={"equity_snapshot": RuntimeError("boom")})
        b = _FakeProvider("b", ["equity_snapshot"], returns={"equity_snapshot": EquitySnapshot(ticker="AAPL", price=42.0, source="b")})
        r._providers = {"a": a, "b": b}
        r.set_priority("equity_snapshot", ["a", "b"])
        snap = r.get_equity_snapshot("AAPL")
        assert snap.source == "b"

    def test_all_fail_returns_none(self):
        r = ProviderRegistry()
        a = _FakeProvider("a", ["equity_snapshot"], returns={"equity_snapshot": None})
        b = _FakeProvider("b", ["equity_snapshot"], returns={"equity_snapshot": None})
        r._providers = {"a": a, "b": b}
        r.set_priority("equity_snapshot", ["a", "b"])
        assert r.get_equity_snapshot("AAPL") is None

    def test_empty_series_triggers_fallback(self):
        r = ProviderRegistry()
        a = _FakeProvider("a", ["equity_history"], returns={"equity_history": pd.Series(dtype=float)})
        good = pd.Series({pd.Timestamp("2024-01-01"): 100.0})
        good.attrs["source"] = "b"
        b = _FakeProvider("b", ["equity_history"], returns={"equity_history": good})
        r._providers = {"a": a, "b": b}
        r.set_priority("equity_history", ["a", "b"])
        s = r.get_equity_history("AAPL", "2024-01-01", "2024-01-31")
        assert s is not None
        assert len(s) == 1
        assert s.attrs["source"] == "b"


class TestRegistryIntrospection:
    def test_available_providers_filters_by_capability(self):
        r = ProviderRegistry()
        a = _FakeProvider("a", ["equity_snapshot"])
        b = _FakeProvider("b", ["equity_history"])
        c = _FakeProvider("c", ["equity_snapshot"], available=False)
        r._providers = {"a": a, "b": b, "c": c}
        r.set_priority("equity_snapshot", ["a", "b", "c"])
        avail = r.available_providers("equity_snapshot")
        assert avail == ["a"]  # b lacks capability, c unavailable

    def test_set_priority_rejects_unknown_providers(self):
        r = ProviderRegistry()
        with pytest.raises(ValueError):
            r.set_priority("equity_snapshot", ["nonexistent"])

    def test_health_returns_all_providers(self):
        healths = registry.health()
        names = {h.name for h in healths}
        assert "yfinance" in names
        assert "fred" in names
        # Every entry has the three mandatory fields
        for h in healths:
            assert isinstance(h.available, bool)
            assert isinstance(h.capabilities, list)


class TestRegistryDefaultPriority:
    def test_snapshot_prioritizes_realtime_sources(self):
        """Real-time sources should precede 15-min-delayed yfinance."""
        prio = registry._priority["equity_snapshot"]
        yfin_idx = prio.index("yfinance")
        # Either Finnhub or Polygon must come before yfinance
        has_realtime_first = (
            ("finnhub" in prio[:yfin_idx]) or ("polygon" in prio[:yfin_idx])
        )
        assert has_realtime_first

    def test_fundamentals_prioritizes_fmp(self):
        prio = registry._priority["fundamentals"]
        assert prio.index("fmp") < prio.index("yfinance")


class TestBaseProviderDefaults:
    def test_base_methods_raise_unavailable(self):
        p = BaseProvider()
        with pytest.raises(ProviderUnavailable):
            p.get_equity_snapshot("AAPL")
        with pytest.raises(ProviderUnavailable):
            p.get_fundamentals("AAPL")
        with pytest.raises(ProviderUnavailable):
            p.get_analyst_estimates("AAPL")
        with pytest.raises(ProviderUnavailable):
            p.get_equity_history("AAPL", "2024-01-01", "2024-12-31")


class TestDataclasses:
    def test_equity_snapshot_to_dict_strips_none(self):
        s = EquitySnapshot(ticker="AAPL", price=100.0, source="test")
        d = s.to_dict()
        assert "price" in d
        assert "change" not in d  # None values dropped

    def test_fundamentals_to_dict(self):
        f = FundamentalMetrics(ticker="AAPL", market_cap=3e12, pe_ratio=30.0, source="test")
        d = f.to_dict()
        assert d["market_cap"] == 3e12
        assert d["pe_ratio"] == 30.0
        assert "roe" not in d

    def test_analyst_estimates_defaults(self):
        e = AnalystEstimates(ticker="AAPL", source="test")
        assert e.ticker == "AAPL"
        assert e.target_mean is None


class TestDataFetcherSnapshotIntegration:
    def test_get_snapshot_returns_registry_result(self, monkeypatch):
        from backend.services import data_fetcher

        fake = EquitySnapshot(ticker="AAPL", price=200.0, source="fake")
        monkeypatch.setattr(
            data_fetcher.provider_registry,
            "get_equity_snapshot",
            lambda t: fake,
        )
        result = data_fetcher.get_snapshot("AAPL")
        assert result is fake
        assert result.price == 200.0

    def test_sp500_prefers_registry_snapshot(self, monkeypatch):
        from backend.services import data_fetcher

        fake = EquitySnapshot(ticker="^GSPC", price=5500.0, source="fake")
        monkeypatch.setattr(
            data_fetcher.provider_registry,
            "get_equity_snapshot",
            lambda t: fake,
        )
        # fetch_safe should NOT be called when snapshot works
        called = {"fetch_safe": False}

        def boom(*a, **kw):
            called["fetch_safe"] = True
            return None

        monkeypatch.setattr(data_fetcher, "fetch_safe", boom)
        price = data_fetcher.DataFetcher().get_sp500_price()
        assert price == 5500.0
        assert called["fetch_safe"] is False

    def test_sp500_falls_back_to_historical_when_snapshot_none(self, monkeypatch):
        from backend.services import data_fetcher

        monkeypatch.setattr(
            data_fetcher.provider_registry,
            "get_equity_snapshot",
            lambda t: None,
        )
        series = pd.Series({pd.Timestamp("2024-01-01"): 4800.0})
        monkeypatch.setattr(data_fetcher, "fetch_safe", lambda *a, **kw: series)
        price = data_fetcher.DataFetcher().get_sp500_price()
        assert price == 4800.0
