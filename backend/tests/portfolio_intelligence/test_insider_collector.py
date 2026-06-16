"""
Offline tests for the TRIAL-INSIDER-IC forward collector. No network: a stub
`fetch` is injected. Verifies PIT writes, leak-safe idempotence, the weekly
throttle, and that scores land in the point-in-time store.
"""

import pytest

from backend.db import get_connection, get_series_observable, init_db
from backend.services.portfolio_intelligence.insider_collector import (
    KEY_PREFIX, collect_insider_opp_scores,
)

_TICKERS = ["AAA", "BBB", "CCC"]


def _fetch_stub(buys_by_ticker):
    def _f(ticker):
        return {"ticker": ticker, "buys": buys_by_ticker.get(ticker, [])}
    return _f


@pytest.fixture
def db_path(tmp_path):
    p = tmp_path / "ins.db"
    init_db(p)
    return p


def _buy(name, shares, value):
    return {"name": name, "shares": shares, "value": value, "type": "P"}


class TestCollect:
    def test_writes_a_pit_row_per_ticker(self, db_path):
        fetch = _fetch_stub({"AAA": [_buy("Jane", 1000, 500_000)]})
        res = collect_insider_opp_scores(db_path=db_path, tickers=_TICKERS,
                                         fetch=fetch, as_of="2026-06-16")
        assert res["status"] == "collected"
        assert res["n"] == 3 and res["written"] == 3
        assert res["nonzero"] == 1                       # only AAA had a P-buy
        assert res["scores"]["AAA"] > 1.0
        assert res["scores"]["BBB"] == 0.0

    def test_value_lands_in_pit_store_leak_safe(self, db_path):
        fetch = _fetch_stub({"AAA": [_buy("Jane", 1000, 500_000)]})
        collect_insider_opp_scores(db_path=db_path, tickers=["AAA"], fetch=fetch,
                                   as_of="2026-06-16")
        conn = get_connection(db_path)
        try:
            series = get_series_observable(conn, KEY_PREFIX + "AAA")
        finally:
            conn.close()
        assert len(series) == 1
        assert series[0]["as_of"] == "2026-06-16"
        assert series[0]["value"] > 1.0
        assert series[0]["source"] == "sec_form4"

    def test_idempotent_same_as_of_no_duplicate(self, db_path):
        fetch = _fetch_stub({"AAA": [_buy("Jane", 1000, 500_000)]})
        collect_insider_opp_scores(db_path=db_path, tickers=["AAA"], fetch=fetch,
                                   as_of="2026-06-16", throttle_days=0)
        res2 = collect_insider_opp_scores(db_path=db_path, tickers=["AAA"], fetch=fetch,
                                          as_of="2026-06-16", throttle_days=0)
        assert res2["written"] == 0  # unchanged value → snapshot no-ops

    def test_throttle_skips_within_window(self, db_path):
        fetch = _fetch_stub({"AAA": [_buy("Jane", 1000, 500_000)]})
        collect_insider_opp_scores(db_path=db_path, tickers=["AAA"], fetch=fetch,
                                   as_of="2026-06-16")
        # 2 days later, default 5-day throttle → skipped
        res = collect_insider_opp_scores(db_path=db_path, tickers=["AAA"], fetch=fetch,
                                         as_of="2026-06-18")
        assert res["status"] == "throttled" and res["n"] == 0

    def test_throttle_passes_after_window(self, db_path):
        fetch = _fetch_stub({"AAA": [_buy("Jane", 1000, 500_000)]})
        collect_insider_opp_scores(db_path=db_path, tickers=["AAA"], fetch=fetch,
                                   as_of="2026-06-16")
        res = collect_insider_opp_scores(db_path=db_path, tickers=["AAA"], fetch=fetch,
                                         as_of="2026-06-23")  # 7 days later
        assert res["status"] == "collected"

    def test_one_ticker_failure_does_not_break_run(self, db_path):
        def fetch(t):
            if t == "BBB":
                raise RuntimeError("SEC down")
            return {"ticker": t, "buys": [_buy("Jane", 10, 1000)] if t == "AAA" else []}
        res = collect_insider_opp_scores(db_path=db_path, tickers=_TICKERS, fetch=fetch,
                                         as_of="2026-06-16")
        assert res["status"] == "collected" and res["n"] == 3
        assert res["scores"]["BBB"] == 0.0  # failed ticker → zero, not a crash
