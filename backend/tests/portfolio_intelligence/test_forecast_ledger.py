"""TRIAL-FORECAST-LEDGER — pre-registration invariants + collector contract.

All offline: the collector reads the screener CACHE, so tests patch
cache_peek. Contract under test:
- trial registration is idempotent and counts toward cumulative trials
- decision rule is frozen, measurement-only, no buy/sell language
- collection pairs model+street from one snapshot; missing-forecast rows are
  recorded as missing (excluded from scoring), never fabricated
- a missing screener cache is DISCLOSED (status), never silent
- scorer returns insufficient_forward_data until the frozen minimum window
"""

import pytest
from unittest.mock import patch

from backend.services.portfolio_intelligence import forecast_ledger as fl


@pytest.fixture
def tmp_db(tmp_path):
    return tmp_path / "test_pi.db"


def _screener_stub():
    return {
        "stocks": [
            {"ticker": "AAPL", "current_price": 100.0,
             "mc_median_5y_return": 40.0, "analyst_target": 120.0},
            {"ticker": "XOM", "current_price": 50.0,
             "mc_median_5y_return": 25.0, "analyst_target": None},  # no street
        ],
    }


class TestRegistration:
    def test_idempotent(self, tmp_db):
        rid1 = fl.ensure_forecast_ledger_trial(db_path=tmp_db)
        rid2 = fl.ensure_forecast_ledger_trial(db_path=tmp_db)
        assert rid1 == rid2

    def test_counts_toward_cumulative(self, tmp_db):
        from backend.db import count_cumulative_trials, get_connection, init_db
        init_db(tmp_db)
        conn = get_connection(tmp_db)
        before = count_cumulative_trials(conn)
        conn.close()
        fl.ensure_forecast_ledger_trial(db_path=tmp_db)
        conn = get_connection(tmp_db)
        after = count_cumulative_trials(conn)
        conn.close()
        assert after == before + 1

    def test_rule_frozen_measurement_only(self):
        rule = fl.DECISION_RULE
        assert rule["trial"] == "TRIAL-FORECAST-LEDGER"
        assert rule["earliest_decision"] == "2027-07-16"
        assert "never arms a lane" in rule["constraints"]
        assert "MAE" in rule["primary_metric"]
        text = " ".join(str(v) for v in rule.values()).lower()
        assert "buy " not in text.replace("buy/sell", "")
        assert " sell " not in text.replace("buy/sell", "")


class TestCollection:
    def test_pairs_from_one_snapshot(self, tmp_db):
        from backend.db import init_db
        init_db(tmp_db)
        with patch.object(fl, "_SCREENER_MAX_STALE_S", 10 ** 9), \
             patch("backend.cache.cache_peek",
                   return_value=(_screener_stub(), 60.0)):
            out = fl.collect_forecast_snapshots(db_path=tmp_db)
        assert out["status"] == "collected"
        assert out["n"] == 2
        # model 1y from 40% 5y median = (1.4)^0.2 - 1 ≈ 6.96%
        assert abs(out["scores"]["AAPL"] - 6.96) < 0.05
        # XOM has no street target → recorded as 0 with missing payload
        assert out["scores"]["XOM"] == 0.0

        import json
        from backend.db import get_connection
        conn = get_connection(tmp_db)
        rows = conn.execute(
            "SELECT key, payload FROM pit_observations WHERE key LIKE ?",
            (fl.KEY_PREFIX + "%",),
        ).fetchall()
        conn.close()
        payloads = {r["key"][len(fl.KEY_PREFIX):]: json.loads(r["payload"])
                    for r in rows}
        assert payloads["AAPL"]["street_1y_pct"] == 20.0
        assert payloads["AAPL"]["price"] == 100.0
        assert payloads["XOM"]["missing"] is True

    def test_missing_cache_disclosed(self, tmp_db):
        with patch("backend.cache.cache_peek", return_value=(None, None)):
            out = fl.collect_forecast_snapshots(db_path=tmp_db)
        assert out["status"] == "no_screener_cache"

    def test_throttled_second_run(self, tmp_db):
        from backend.db import init_db
        init_db(tmp_db)
        with patch("backend.cache.cache_peek",
                   return_value=(_screener_stub(), 60.0)):
            first = fl.collect_forecast_snapshots(db_path=tmp_db)
            second = fl.collect_forecast_snapshots(db_path=tmp_db)
        assert first["status"] == "collected"
        assert second["status"] == "throttled"


class TestScoring:
    def test_insufficient_before_maturity(self, tmp_db):
        from backend.db import init_db
        init_db(tmp_db)
        with patch("backend.cache.cache_peek",
                   return_value=(_screener_stub(), 60.0)):
            fl.collect_forecast_snapshots(db_path=tmp_db)
        out = fl.score_matured_forecasts(db_path=tmp_db)
        assert out["status"] == "insufficient_forward_data"
        assert out["earliest_decision"] == "2027-07-16"
