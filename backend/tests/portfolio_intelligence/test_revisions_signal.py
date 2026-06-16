"""
Offline tests for the analyst revision-momentum signal (TRIAL-REVISIONS-IC):
the pure scorer (net dated actions, leak-safe + windowed) and the forward
collector (injected fetch → PIT store, via the generic collector engine).
"""

import pytest

from backend.db import get_connection, get_series_observable, init_db
from backend.services.estimate_revisions import compute_revision_momentum_score
from backend.services.portfolio_intelligence.revisions_collector import (
    KEY_PREFIX, collect_revision_scores,
)


def _a(date, action="main", target=""):
    return {"date": date, "action": action, "target": target}


class TestRevisionScore:
    def test_net_raises_minus_lowers(self):
        data = {"actions": [_a("2026-05-01", target="Raises"),
                            _a("2026-05-02", target="Raises"),
                            _a("2026-05-03", target="Lowers")]}
        s = compute_revision_momentum_score(data, as_of="2026-06-17")
        assert s["raises"] == 2 and s["lowers"] == 1
        assert s["revisions_score"] == 1.0

    def test_upgrades_and_downgrades_count(self):
        data = {"actions": [_a("2026-06-01", action="up"),
                            _a("2026-06-02", action="up"),
                            _a("2026-06-03", action="down")]}
        s = compute_revision_momentum_score(data, as_of="2026-06-17")
        assert s["upgrades"] == 2 and s["downgrades"] == 1
        assert s["revisions_score"] == 1.0

    def test_leak_safe_future_actions_excluded(self):
        # an action dated AFTER as_of must not count (no lookahead)
        data = {"actions": [_a("2026-06-20", target="Raises"),
                            _a("2026-06-10", target="Raises")]}
        s = compute_revision_momentum_score(data, as_of="2026-06-17")
        assert s["raises"] == 1 and s["n_actions"] == 1

    def test_window_excludes_old_actions(self):
        # default 90d window; an action 200d before as_of must drop out
        data = {"actions": [_a("2025-11-01", target="Raises"),  # >90d old
                            _a("2026-06-01", target="Raises")]}
        s = compute_revision_momentum_score(data, as_of="2026-06-17", window_days=90)
        assert s["raises"] == 1 and s["n_actions"] == 1

    def test_empty_and_none(self):
        assert compute_revision_momentum_score(None)["revisions_score"] == 0.0
        assert compute_revision_momentum_score({"actions": []})["revisions_score"] == 0.0

    def test_rating_drift_in_payload_not_score(self):
        data = {"actions": [],
                "rec_counts": [
                    {"period": "0m", "strongBuy": 5, "buy": 3, "hold": 1, "sell": 0, "strongSell": 0},
                    {"period": "-2m", "strongBuy": 2, "buy": 3, "hold": 3, "sell": 1, "strongSell": 0}]}
        s = compute_revision_momentum_score(data, as_of="2026-06-17")
        assert s["revisions_score"] == 0.0           # drift not folded into score
        assert s["rating_drift"] > 0                 # got more bullish → positive


@pytest.fixture
def db_path(tmp_path):
    p = tmp_path / "rev.db"
    init_db(p)
    return p


def _fetch_stub(actions_by_ticker):
    return lambda t: {"ticker": t, "actions": actions_by_ticker.get(t, []), "rec_counts": []}


class TestRevisionCollector:
    def test_writes_pit_rows_with_sign(self, db_path):
        fetch = _fetch_stub({
            "AAA": [_a("2026-06-01", target="Raises"), _a("2026-06-02", target="Raises")],
            "BBB": [_a("2026-06-01", target="Lowers")],          # negative score
        })
        res = collect_revision_scores(db_path=db_path, tickers=["AAA", "BBB", "CCC"],
                                      fetch=fetch, as_of="2026-06-17")
        assert res["status"] == "collected" and res["n"] == 3
        assert res["scores"]["AAA"] == 2.0
        assert res["scores"]["BBB"] == -1.0
        assert res["scores"]["CCC"] == 0.0
        assert res["nonzero"] == 2                    # negative counts as nonzero

    def test_value_lands_in_pit_store_leak_safe(self, db_path):
        fetch = _fetch_stub({"AAA": [_a("2026-06-01", target="Raises")]})
        collect_revision_scores(db_path=db_path, tickers=["AAA"], fetch=fetch,
                                as_of="2026-06-17")
        conn = get_connection(db_path)
        try:
            series = get_series_observable(conn, KEY_PREFIX + "AAA")
        finally:
            conn.close()
        assert len(series) == 1 and series[0]["value"] == 1.0
        assert series[0]["source"] == "yfinance"

    def test_throttle_skips_within_window(self, db_path):
        fetch = _fetch_stub({"AAA": [_a("2026-06-01", target="Raises")]})
        collect_revision_scores(db_path=db_path, tickers=["AAA"], fetch=fetch,
                                as_of="2026-06-17")
        res = collect_revision_scores(db_path=db_path, tickers=["AAA"], fetch=fetch,
                                      as_of="2026-06-19")
        assert res["status"] == "throttled"

    def test_fetch_failure_isolated(self, db_path):
        def fetch(t):
            if t == "BBB":
                raise RuntimeError("yf down")
            return {"ticker": t, "actions": [_a("2026-06-01", target="Raises")], "rec_counts": []}
        res = collect_revision_scores(db_path=db_path, tickers=["AAA", "BBB"], fetch=fetch,
                                      as_of="2026-06-17")
        assert res["status"] == "collected"
        assert res["scores"]["BBB"] == 0.0            # failed ticker → 0, not a crash
