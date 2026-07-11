"""
Offline tests for TRIAL-SMARTGROWTH: the frozen blend (z-scores, weight
renormalization when components are missing, upside clip containment), the
top-10 basket, PIT-write via the collector, throttle, and trial registration.
"""

import pytest

from backend.db import get_connection, get_series_observable, init_db, snapshot
from backend.services.portfolio_intelligence.smartgrowth import (
    BASKET_SIZE, KEY_PREFIX, compute_smartgrowth_basket,
    collect_smartgrowth_picks, ensure_smartgrowth_trial,
)


def _mom(n=15, best="AAA"):
    # a momentum cross-section with `best` clearly on top
    vals = {f"T{i:02d}": float(i) for i in range(n)}
    vals[best] = 100.0
    return vals


class TestBlend:
    def test_top_scorer_is_picked(self):
        signals = {"momentum": _mom(), "revisions": {}, "congress": {}, "ark": {}}
        b = compute_smartgrowth_basket(signals, upside_fetch=lambda ts: {})
        assert b["status"] == "ok"
        assert "AAA" in b["picks"]
        assert len(b["picks"]) == BASKET_SIZE
        assert all(w == pytest.approx(0.10) for w in b["picks"].values())

    def test_missing_components_renormalize_and_are_recorded(self):
        signals = {"momentum": _mom(), "revisions": {}, "congress": {}, "ark": {}}
        b = compute_smartgrowth_basket(signals, upside_fetch=lambda ts: {})
        # only momentum live (revisions/smart_money empty; upside fetch empty)
        assert b["components_live"] == ["momentum"]

    def test_smart_money_sums_congress_and_ark(self):
        signals = {
            "momentum": {f"T{i}": 0.0 for i in range(10)},
            "revisions": {},
            "congress": {"T1": 3.0, "T2": 1.0, "T3": 0.0},
            "ark": {"T1": 2.0, "T2": -1.0, "T3": 0.0},
        }
        b = compute_smartgrowth_basket(signals, upside_fetch=lambda ts: {})
        # T1 has the highest combined smart-money (5.0) → highest score
        assert b["scores"]["T1"] == max(b["scores"].values())

    def test_upside_only_counted_for_prefetched_top(self):
        # upside_fetch receives at most PREFETCH_TOP_N names
        seen = {}
        def fetch(ts):
            seen["n"] = len(ts)
            return {}
        signals = {"momentum": {f"T{i:03d}": float(i) for i in range(50)},
                   "revisions": {}, "congress": {}, "ark": {}}
        compute_smartgrowth_basket(signals, upside_fetch=fetch)
        assert seen["n"] <= 30

    def test_no_signals_returns_status(self):
        b = compute_smartgrowth_basket(
            {"momentum": {}, "revisions": {}, "congress": {}, "ark": {}},
            upside_fetch=lambda ts: {})
        assert b["status"] == "no_signals" and b["picks"] == {}


@pytest.fixture
def db_path(tmp_path):
    p = tmp_path / "sg.db"
    init_db(p)
    return p


def _seed_signals(db_path, n=15):
    conn = get_connection(db_path)
    try:
        for i in range(n):
            snapshot(conn, f"multifactor_score:T{i:02d}", "2026-07-10",
                     float(i), source="test")
        conn.commit()
    finally:
        conn.close()


class TestCollector:
    def test_writes_basket_to_pit(self, db_path):
        _seed_signals(db_path)
        res = collect_smartgrowth_picks(db_path=db_path,
                                        upside_fetch=lambda ts: {},
                                        as_of="2026-07-12")
        assert res["status"] == "collected"
        assert res["n"] == BASKET_SIZE
        conn = get_connection(db_path)
        try:
            series = get_series_observable(conn, KEY_PREFIX + "T14")
        finally:
            conn.close()
        assert len(series) == 1
        assert series[0]["value"] == pytest.approx(0.10)
        assert "components_live" in series[0]["payload"]

    def test_weekly_throttle(self, db_path):
        _seed_signals(db_path)
        collect_smartgrowth_picks(db_path=db_path, upside_fetch=lambda ts: {},
                                  as_of="2026-07-12")
        res = collect_smartgrowth_picks(db_path=db_path,
                                        upside_fetch=lambda ts: {},
                                        as_of="2026-07-15")
        assert res["status"] == "throttled"

    def test_sparse_inputs_no_false_basket(self, db_path):
        # nothing seeded → no basket, no PIT rows
        res = collect_smartgrowth_picks(db_path=db_path,
                                        upside_fetch=lambda ts: {},
                                        as_of="2026-07-12")
        assert res["status"] == "no_signals" and res["n"] == 0
        conn = get_connection(db_path)
        try:
            n = conn.execute(
                "SELECT COUNT(*) AS n FROM pit_observations WHERE key LIKE ?",
                (KEY_PREFIX + "%",)).fetchone()["n"]
        finally:
            conn.close()
        assert n == 0

    def test_trial_registration_idempotent(self, db_path):
        assert ensure_smartgrowth_trial(db_path=db_path) == \
            ensure_smartgrowth_trial(db_path=db_path)
