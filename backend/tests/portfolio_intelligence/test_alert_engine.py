"""
V4 alert engine — offline tests.

Invariants: change rules fire only on actual transitions; cooldown suppresses
repeats; state memory survives missing readings (no spurious change when a
reading comes back); delivery failure is never fatal; no buy/sell language.
"""

import json
from datetime import datetime, timedelta

import pytest

from backend.db import get_connection, init_db, insert_audit_log
from backend.services.portfolio_intelligence import alert_engine as ae


@pytest.fixture()
def db(tmp_path):
    p = tmp_path / "alerts.db"
    init_db(p)
    return p


def _seed_fragility(db, composite, level):
    conn = get_connection(db)
    try:
        insert_audit_log(conn, datetime.now().isoformat(), "_market",
                         "fragility_eval",
                         {"composite": composite, "level": level})
    finally:
        conn.close()


class TestPureRules:
    def test_no_alerts_when_nothing_changed(self):
        cur = {"regime": "Bull", "fragility_composite": 0.2, "fragility_level": "low"}
        assert ae.evaluate_rules(cur, dict(cur)) == []

    def test_regime_change_fires(self):
        alerts = ae.evaluate_rules({"regime": "Volatile"}, {"regime": "Bull"})
        assert [a.rule for a in alerts] == ["regime_change"]
        assert alerts[0].state == "Volatile"

    def test_no_regime_alert_when_previous_unknown(self):
        assert ae.evaluate_rules({"regime": "Bull"}, {}) == []

    def test_fragility_level_change_fires(self):
        alerts = ae.evaluate_rules(
            {"fragility_level": "elevated", "fragility_composite": 0.6},
            {"fragility_level": "moderate", "fragility_composite": 0.5},
        )
        assert "fragility_level_change" in [a.rule for a in alerts]

    def test_fragility_jump_rising_only(self):
        up = ae.evaluate_rules({"fragility_composite": 0.45},
                               {"fragility_composite": 0.20})
        down = ae.evaluate_rules({"fragility_composite": 0.20},
                                 {"fragility_composite": 0.45})
        assert [a.rule for a in up] == ["fragility_jump"]
        assert down == []

    def test_no_order_language(self):
        alerts = ae.evaluate_rules(
            {"regime": "Bear", "fragility_level": "high", "fragility_composite": 0.9},
            {"regime": "Bull", "fragility_level": "low", "fragility_composite": 0.1},
        )
        assert len(alerts) == 3
        for a in alerts:
            low = a.message.lower()
            assert "buy" not in low and "sell" not in low
            assert "not advice" in low


class TestRunner:
    def test_first_run_emits_nothing_but_stores_state(self, db):
        _seed_fragility(db, 0.22, "low")
        out = ae.run_alert_check(current_regime="Bull", db_path=db)
        assert out["status"] == "ok"
        assert out["emitted"] == []
        # second run with a changed regime now has memory to compare against
        out2 = ae.run_alert_check(current_regime="Volatile", db_path=db)
        assert [e["rule"] for e in out2["emitted"]] == ["regime_change"]

    def test_cooldown_suppresses_repeat(self, db):
        _seed_fragility(db, 0.22, "low")
        ae.run_alert_check(current_regime="Bull", db_path=db)
        out1 = ae.run_alert_check(current_regime="Bear", db_path=db)
        assert out1["emitted"]
        # regime flaps back then to Bear again within the cooldown window:
        ae.run_alert_check(current_regime="Bull", db_path=db)  # Bull alert (new state)
        out2 = ae.run_alert_check(current_regime="Bear", db_path=db)
        assert out2["emitted"] == []
        assert out2["suppressed_by_cooldown"] == 1

    def test_cooldown_expires(self, db):
        _seed_fragility(db, 0.22, "low")
        t0 = datetime(2026, 7, 8, 12, 0, 0)
        ae.run_alert_check(current_regime="Bull", db_path=db, now=t0)
        ae.run_alert_check(current_regime="Bear", db_path=db,
                           now=t0 + timedelta(hours=1))
        ae.run_alert_check(current_regime="Bull", db_path=db,
                           now=t0 + timedelta(hours=2))
        out = ae.run_alert_check(current_regime="Bear", db_path=db,
                                 now=t0 + timedelta(hours=2 + ae.COOLDOWN_HOURS + 1))
        assert [e["rule"] for e in out["emitted"]] == ["regime_change"]

    def test_missing_reading_does_not_erase_memory(self, db):
        """Regime fetch fails one run → no spurious change alert when it returns."""
        _seed_fragility(db, 0.22, "low")
        ae.run_alert_check(current_regime="Bull", db_path=db)
        ae.run_alert_check(current_regime=None, db_path=db)  # fetch failed
        out = ae.run_alert_check(current_regime="Bull", db_path=db)  # back, unchanged
        assert out["emitted"] == []

    def test_fragility_change_read_from_persisted_evals(self, db):
        _seed_fragility(db, 0.22, "low")
        ae.run_alert_check(db_path=db)
        _seed_fragility(db, 0.60, "elevated")
        out = ae.run_alert_check(db_path=db)
        rules = [e["rule"] for e in out["emitted"]]
        assert "fragility_level_change" in rules
        assert "fragility_jump" in rules

    def test_alerts_persisted_and_readable(self, db):
        _seed_fragility(db, 0.22, "low")
        ae.run_alert_check(current_regime="Bull", db_path=db)
        ae.run_alert_check(current_regime="Bear", db_path=db)
        rows = ae.recent_alerts(db_path=db)
        assert len(rows) == 1
        assert rows[0]["rule"] == "regime_change"
        assert rows[0]["delivered"] == ["log"]
        assert rows[0]["payload"]["to"] == "Bear"

    def test_telegram_failure_is_not_fatal(self, db, monkeypatch):
        _seed_fragility(db, 0.22, "low")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
        import requests as req

        def _boom(*a, **k):
            raise req.exceptions.ConnectionError("blocked")

        monkeypatch.setattr("requests.post", _boom)
        ae.run_alert_check(current_regime="Bull", db_path=db)
        out = ae.run_alert_check(current_regime="Bear", db_path=db)
        assert out["emitted"]  # alert still emitted via log
        rows = ae.recent_alerts(db_path=db)
        assert rows[0]["delivered"] == ["log"]


class TestRiskWatchSurface:
    def test_latest_persisted_composite_reads_without_network(self, db):
        from backend.services.portfolio_intelligence.fragility import (
            latest_persisted_composite,
        )
        assert latest_persisted_composite(db_path=db)["status"] == "no_reading"
        _seed_fragility(db, 0.31, "moderate")
        out = latest_persisted_composite(db_path=db)
        assert out["composite"] == 0.31
        assert out["level"] == "moderate"
        assert out["evaluated_at"]
        assert "descriptive" in out["label"]
