"""Tests for analyst_intelligence — Wall Street consensus display service.

All offline: yf.Ticker is stubbed. Contract under test:
- every field is optional (partial data returns, fields degrade to None)
- None only when NOTHING is available
- firm-attributed actions parse Benzinga codes into readable labels
- endpoint 404s on no-coverage, 422s on bad ticker format
"""

import pandas as pd
import pytest
from unittest.mock import patch

from backend.services import analyst_intelligence as ai


class _StubTicker:
    ticker = "FAKE"
    analyst_price_targets = None
    recommendations = None
    upgrades_downgrades = None

    def __init__(self, *a, **k):
        pass


def _targets_stub():
    return {"current": 100.0, "low": 90.0, "mean": 120.0,
            "median": 118.0, "high": 150.0}


def _recs_stub():
    return pd.DataFrame({
        "period": ["0m", "-1m"],
        "strongBuy": [10, 9], "buy": [20, 21], "hold": [8, 8],
        "sell": [1, 2], "strongSell": [0, 0],
    })


def _grades_stub():
    idx = pd.DatetimeIndex([pd.Timestamp.now() - pd.Timedelta(days=d)
                            for d in (3, 40, 400)], name="GradeDate")
    return pd.DataFrame({
        "Firm": ["JP Morgan", "Goldman Sachs", "Old Firm"],
        "ToGrade": ["Overweight", "Neutral", "Buy"],
        "FromGrade": ["Neutral", "Buy", ""],
        "Action": ["up", "down", "init"],
    }, index=idx)


class TestBlocks:
    def test_price_targets_with_upside(self):
        stub = _StubTicker()
        stub.analyst_price_targets = _targets_stub()
        block = ai._price_target_block(stub)
        assert block["mean"] == 120.0
        assert block["upside_pct"] == 20.0

    def test_price_targets_missing(self):
        assert ai._price_target_block(_StubTicker()) is None

    def test_recommendation_trend(self):
        stub = _StubTicker()
        stub.recommendations = _recs_stub()
        trend = ai._recommendation_trend(stub)
        assert trend[0]["strongBuy"] == 10
        assert trend[0]["total"] == 39

    def test_consensus_rating(self):
        r = ai._consensus_rating({"recommendationMean": 1.8,
                                  "recommendationKey": "buy",
                                  "numberOfAnalystOpinions": 43})
        assert r["score"] == 1.8
        assert r["label"] == "buy"
        assert r["n_analysts"] == 43

    def test_consensus_rating_empty(self):
        assert ai._consensus_rating({}) is None

    def test_upgrades_downgrades_labels_and_lookback(self):
        stub = _StubTicker()
        stub.upgrades_downgrades = _grades_stub()
        items = ai._upgrades_downgrades(stub, max_items=30, lookback_days=365)
        # 400-day-old row excluded by lookback
        assert len(items) == 2
        assert items[0]["firm"] == "JP Morgan"
        assert items[0]["action"] == "upgrade"
        assert items[1]["action"] == "downgrade"

    def test_blocks_never_raise(self):
        class Boom:
            ticker = "X"

            def __getattr__(self, name):
                raise RuntimeError("network down")
        assert ai._price_target_block(Boom()) is None
        assert ai._recommendation_trend(Boom()) is None
        assert ai._upgrades_downgrades(Boom(), 30, 365) is None


class TestGetAnalystIntelligence:
    def test_partial_data_returns(self):
        stub = _StubTicker()
        stub.analyst_price_targets = _targets_stub()
        import yfinance as yf
        with patch.object(yf, "Ticker", return_value=stub), \
             patch("backend.services.data_fetcher.fetch_ticker_info",
                   return_value={"recommendationMean": 2.0,
                                 "recommendationKey": "buy",
                                 "numberOfAnalystOpinions": 12}):
            out = ai.get_analyst_intelligence.__wrapped__("FAKE")
        assert out["price_targets"]["mean"] == 120.0
        assert out["recommendation_trend"] is None
        assert out["consensus_rating"]["n_analysts"] == 12
        assert "Yahoo Finance" in out["attribution"]

    def test_nothing_available_returns_none(self):
        import yfinance as yf
        with patch.object(yf, "Ticker", return_value=_StubTicker()), \
             patch("backend.services.data_fetcher.fetch_ticker_info",
                   return_value={}):
            assert ai.get_analyst_intelligence.__wrapped__("ZZXQ") is None


class TestEndpoint:
    def test_bad_ticker_422(self):
        from fastapi.testclient import TestClient
        from backend.main import app
        client = TestClient(app)
        assert client.get("/api/stock/bad!!ticker/analysts").status_code == 422

    def test_no_coverage_404(self):
        from fastapi.testclient import TestClient
        from backend.main import app
        with patch("backend.services.analyst_intelligence.get_analyst_intelligence",
                   return_value=None):
            client = TestClient(app)
            resp = client.get("/api/stock/ZZXQ/analysts")
        assert resp.status_code == 404

    def test_ok_200(self):
        from fastapi.testclient import TestClient
        from backend.main import app
        payload = {"ticker": "AAPL", "price_targets": {"mean": 1.0},
                   "recommendation_trend": None, "consensus_rating": None,
                   "recent_actions": None, "attribution": "via Yahoo Finance"}
        with patch("backend.services.analyst_intelligence.get_analyst_intelligence",
                   return_value=payload):
            client = TestClient(app)
            resp = client.get("/api/stock/AAPL/analysts")
        assert resp.status_code == 200
        assert resp.json()["ticker"] == "AAPL"
