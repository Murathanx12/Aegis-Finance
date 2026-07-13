"""Regression tests for the 2026-07-14 web fixes.

1. Ticker resolver: company names ("MARVELL") resolve to symbols offline.
2. Rate-limit honesty: a throttled Yahoo fetch surfaces as RateLimited → 503,
   never as "Could not analyze {ticker}" (404) — the prod bug where 429
   storms made valid tickers look invalid.
3. Shared per-ticker fetch: one canonical history per ticker, sliced per
   period; stale copy served while throttled.
4. Daily brief: assembles offline with mocked fetches; a failed GDELT read
   is DISCLOSED as unavailable, never reported as "quiet" (silent-fragility).
"""

import pandas as pd
import numpy as np
import pytest
from unittest.mock import patch, MagicMock


# ── 1. Ticker resolver ──────────────────────────────────────────────────────


class TestTickerResolver:
    def test_company_name_resolves_offline(self):
        from backend.services.ticker_resolver import resolve_ticker
        r = resolve_ticker("MARVELL", allow_network=False)
        assert r is not None and r["ticker"] == "MRVL"

    def test_name_with_suffixes_resolves(self):
        from backend.services.ticker_resolver import resolve_ticker
        r = resolve_ticker("Marvell Technology, Inc.", allow_network=False)
        assert r is not None and r["ticker"] == "MRVL"

    def test_known_ticker_identity(self):
        from backend.services.ticker_resolver import resolve_ticker
        r = resolve_ticker("AAPL", allow_network=False)
        assert r is not None and r["ticker"] == "AAPL"

    def test_ampersand_name(self):
        from backend.services.ticker_resolver import resolve_ticker
        r = resolve_ticker("Johnson & Johnson", allow_network=False)
        assert r is not None and r["ticker"] == "JNJ"

    def test_unknown_returns_none_offline(self):
        from backend.services.ticker_resolver import resolve_ticker
        assert resolve_ticker("XQZV9 UNKNOWN CO", allow_network=False) is None

    def test_empty_query(self):
        from backend.services.ticker_resolver import resolve_ticker
        assert resolve_ticker("", allow_network=False) is None
        assert resolve_ticker("   ", allow_network=False) is None


# ── 2 + 3. Shared fetch & rate-limit honesty ───────────────────────────────


def _fake_hist(rows=2600):
    dates = pd.bdate_range("2016-01-04", periods=rows)
    close = pd.Series(np.linspace(50, 150, rows), index=dates)
    return pd.DataFrame({
        "Open": close, "High": close * 1.01, "Low": close * 0.99,
        "Close": close, "Volume": 1_000_000,
    })


class TestSharedTickerFetch:
    def test_period_slicing(self):
        from backend.services import data_fetcher as df_mod
        mock_tk = MagicMock()
        mock_tk.history.return_value = _fake_hist()
        with patch.object(df_mod.yf, "Ticker", return_value=mock_tk):
            with patch.object(df_mod, "cache_get", return_value=None), \
                 patch.object(df_mod, "cache_peek", return_value=(None, None)), \
                 patch.object(df_mod, "cache_set"):
                h5y = df_mod.fetch_ticker_history("FAKE1", period="5y")
                h1y = df_mod.fetch_ticker_history("FAKE1", period="1y")
        assert len(h5y) == 1260
        assert len(h1y) == 252

    def test_rate_limit_raises_ratelimited_when_no_stale(self):
        from backend.services import data_fetcher as df_mod
        mock_tk = MagicMock()
        mock_tk.history.side_effect = Exception(
            "Too Many Requests. Rate limited. Try after a while.")
        with patch.object(df_mod.yf, "Ticker", return_value=mock_tk):
            with patch.object(df_mod, "cache_get", return_value=None), \
                 patch.object(df_mod, "cache_peek", return_value=(None, None)), \
                 patch.object(df_mod, "cache_set"):
                with pytest.raises(df_mod.RateLimited):
                    df_mod.fetch_ticker_history("FAKE2", period="5y")

    def test_rate_limit_serves_stale_copy(self):
        from backend.services import data_fetcher as df_mod
        stale = _fake_hist(300)
        mock_tk = MagicMock()
        mock_tk.history.side_effect = Exception("429 Too Many Requests")
        with patch.object(df_mod.yf, "Ticker", return_value=mock_tk):
            with patch.object(df_mod, "cache_get", return_value=None), \
                 patch.object(df_mod, "cache_peek", return_value=(stale, 3600.0)), \
                 patch.object(df_mod, "cache_set"):
                out = df_mod.fetch_ticker_history("FAKE3", period="1y")
        assert out is not None and len(out) == 252

    def test_unknown_ticker_returns_none(self):
        from backend.services import data_fetcher as df_mod
        mock_tk = MagicMock()
        mock_tk.history.return_value = pd.DataFrame()
        with patch.object(df_mod.yf, "Ticker", return_value=mock_tk):
            with patch.object(df_mod, "cache_get", return_value=None), \
                 patch.object(df_mod, "cache_peek", return_value=(None, None)), \
                 patch.object(df_mod, "cache_set"):
                assert df_mod.fetch_ticker_history("ZZXXQQ") is None

    def test_analyze_stock_propagates_ratelimited(self):
        """analyze_stock must NOT swallow RateLimited into None (the 404 bug)."""
        from backend.services.data_fetcher import RateLimited
        with patch("backend.services.data_fetcher.fetch_ticker_history",
                   side_effect=RateLimited("throttled")):
            from backend.services.stock_analyzer import analyze_stock
            with pytest.raises(RateLimited):
                analyze_stock("AAPL")

    def test_router_maps_ratelimited_to_503(self):
        from fastapi.testclient import TestClient
        from backend.main import app
        from backend.services.data_fetcher import RateLimited

        with patch("backend.routers.stock._analyze_stock",
                   side_effect=RateLimited("throttled")), \
             patch("backend.routers.stock.cache_swr",
                   side_effect=RateLimited("throttled")):
            client = TestClient(app)
            resp = client.get("/api/stock/AAPL")
        assert resp.status_code == 503
        assert "rate-limiting" in resp.json()["detail"].lower()
        assert resp.headers.get("retry-after") == "60"

    def test_resolve_endpoint(self):
        from fastapi.testclient import TestClient
        from backend.main import app
        client = TestClient(app)
        resp = client.get("/api/stock/resolve", params={"q": "marvell"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["resolved"] is True
        assert body["match"]["ticker"] == "MRVL"


# ── 4. Daily brief ──────────────────────────────────────────────────────────


class TestDailyBrief:
    def test_changes_math(self):
        from backend.services.daily_brief import _changes
        s = pd.Series([100, 100, 100, 100, 100, 100, 110.0])
        d1, d5 = _changes(s)
        assert d1 == 10.0
        assert d5 == 10.0

    def test_changes_insufficient(self):
        from backend.services.daily_brief import _changes
        assert _changes(pd.Series([100.0])) == (None, None)

    def test_failed_gdelt_is_disclosed_not_quiet(self):
        """A zero-default GDELT dict (failed fetch) must NOT read as 'quiet'."""
        from backend.services import daily_brief as db
        failed_gdelt = {"conflict_score": 0.0,
                        "raw_data": {"tone": [], "volume": [], "conflict": []}}
        with patch.object(db, "cache_peek", return_value=(None, None)), \
             patch("backend.services.news_intelligence.fetch_gdelt_signals",
                   return_value=failed_gdelt), \
             patch("backend.services.news_intelligence.compute_event_score",
                   return_value={}):
            geo = db._geopolitical_block()
        assert geo["conflict_score"] is None
        assert "unavailable" in geo["note"].lower()

    def test_real_gdelt_quiet_reads_quiet(self):
        from backend.services import daily_brief as db
        ok_gdelt = {"conflict_score": 0.1,
                    "raw_data": {"conflict": [1.0, 2.0, 1.5]}}
        with patch.object(db, "cache_peek", return_value=(None, None)), \
             patch("backend.services.news_intelligence.fetch_gdelt_signals",
                   return_value=ok_gdelt), \
             patch("backend.services.news_intelligence.compute_event_score",
                   return_value={"score": 0.2, "label": "calm"}):
            geo = db._geopolitical_block()
        assert geo["conflict_score"] == 0.1
        assert "quiet" in geo["note"].lower()

    def test_build_brief_offline(self):
        from backend.services import daily_brief as db
        dates = pd.bdate_range("2026-05-01", periods=30)
        closes = {sym: pd.Series(np.linspace(90, 110, 30), index=dates)
                  for sym in ["SPY", "QQQ", "IWM", "^VIX", "CL=F", "GC=F",
                              "^TNX", "DX-Y.NYB", "NVDA", "XOM"]}
        with patch.object(db, "_fetch_all_closes", return_value=closes), \
             patch.object(db, "_geopolitical_block",
                          return_value={"conflict_score": None, "event_score": None,
                                        "event_label": None, "note": "n/a"}), \
             patch.object(db, "_headlines_for", return_value=[]), \
             patch.object(db, "cache_peek", return_value=(None, None)), \
             patch("backend.services.llm_analyzer.is_available", return_value=False):
            brief = db.build_daily_brief(["NVDA", "XOM"])

        assert brief["date"]
        assert len(brief["market"]) == 8
        assert {t["ticker"] for t in brief["your_tickers"]} == {"NVDA", "XOM"}
        assert brief["summary"]["source"] == "template"
        assert brief["disclaimer"]
        # No buy/sell language in the template (honesty contract)
        text = " ".join(str(v) for v in brief["summary"].values()).lower()
        for banned in ("you should buy", "you should sell", " buy ", " sell "):
            assert banned not in text

    def test_brief_endpoint_validates_tickers(self):
        from fastapi.testclient import TestClient
        from backend.main import app
        with patch("backend.routers.news.cache_swr") as mock_swr:
            async def _fake(key, ttl, fn):
                return {"ok": True, "key": key}
            mock_swr.side_effect = _fake
            client = TestClient(app)
            resp = client.get("/api/news/brief",
                              params={"tickers": "nvda, bad!!ticker, MRVL, nvda"})
        assert resp.status_code == 200
        # invalid ticker dropped, duplicates deduped, order-insensitive key
        assert "MRVL,NVDA" in resp.json()["key"]
