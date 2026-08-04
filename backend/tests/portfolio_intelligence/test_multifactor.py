"""
Offline tests for the multi-factor selection model (TRIAL-MULTIFACTOR-IC): the
pure cross-sectional combiner and the forward collector (momentum injected;
insider/revisions read from the PIT store it writes alongside).
"""

import pytest

from backend.db import (
    get_connection, get_latest_observable, init_db, snapshot,
)
from backend.services.portfolio_intelligence.multifactor import (
    KEY_PREFIX, collect_multifactor_scores, compute_multifactor_scores,
)


class TestCombiner:
    def test_equal_weight_zscore_combine(self):
        comps = {
            "momentum": {"A": 90.0, "B": 50.0, "C": 10.0},
            "insider":  {"A": 2.0,  "B": 0.0,  "C": 0.0},
            "revisions": {"A": 5.0, "B": 0.0,  "C": -3.0},
        }
        out = compute_multifactor_scores(comps)
        # A is top on every factor → highest composite; C lowest
        assert out["A"] > out["B"] > out["C"]
        assert out["A"] > 0 > out["C"]

    def test_missing_factor_for_a_ticker_uses_the_rest(self):
        comps = {
            "momentum": {"A": 90.0, "B": 10.0},
            "insider":  {"A": 1.0},                 # B absent from insider
            "revisions": {"A": 2.0, "B": -1.0},
        }
        out = compute_multifactor_scores(comps)
        assert "B" in out and out["A"] > out["B"]

    def test_zero_spread_factor_contributes_nothing(self):
        comps = {
            "momentum": {"A": 50.0, "B": 50.0},     # no spread → z=0 for both
            "revisions": {"A": 3.0, "B": -3.0},
        }
        out = compute_multifactor_scores(comps)
        assert out["A"] > out["B"]                  # decided entirely by revisions

    def test_empty_components(self):
        assert compute_multifactor_scores({}) == {}


@pytest.fixture
def db_path(tmp_path):
    p = tmp_path / "mf.db"
    init_db(p)
    return p


class TestCollector:
    def _seed_pit(self, db_path, as_of="2026-06-17"):
        # No observed_at → snapshot stamps real UTC-now, so the leak-safe read
        # (cutoff = UTC now) always sees it. (Mirrors production: the insider/
        # revisions collectors write just before multifactor reads.)
        conn = get_connection(db_path)
        try:
            snapshot(conn, "insider_opp:AAA", as_of, 2.0, source="sec_form4")
            snapshot(conn, "insider_opp:BBB", as_of, 0.0, source="sec_form4")
            snapshot(conn, "revisions_score:AAA", as_of, 5.0, source="yfinance")
            snapshot(conn, "revisions_score:BBB", as_of, -2.0, source="yfinance")
        finally:
            conn.close()

    def test_composite_written_to_pit(self, db_path):
        self._seed_pit(db_path)
        mom = lambda ts: {"AAA": 80.0, "BBB": 20.0}
        res = collect_multifactor_scores(db_path=db_path, tickers=["AAA", "BBB"],
                                         as_of="2026-06-17", momentum_fn=mom)
        assert res["status"] == "collected" and res["n"] == 2
        assert res["scores"]["AAA"] > res["scores"]["BBB"]
        conn = get_connection(db_path)
        try:
            a = get_latest_observable(conn, KEY_PREFIX + "AAA")
        finally:
            conn.close()
        assert a is not None and a["source"] == "multifactor"

    def test_throttle_skips_within_window(self, db_path):
        self._seed_pit(db_path)
        mom = lambda ts: {"AAA": 80.0, "BBB": 20.0}
        collect_multifactor_scores(db_path=db_path, tickers=["AAA", "BBB"],
                                   as_of="2026-06-17", momentum_fn=mom)
        res = collect_multifactor_scores(db_path=db_path, tickers=["AAA", "BBB"],
                                         as_of="2026-06-19", momentum_fn=mom)
        assert res["status"] == "throttled"

    def test_momentum_failure_degrades_gracefully(self, db_path):
        self._seed_pit(db_path)
        def mom(ts):
            raise RuntimeError("yf down")
        # momentum drops out; insider+revisions still drive a composite
        res = collect_multifactor_scores(db_path=db_path, tickers=["AAA", "BBB"],
                                         as_of="2026-06-17", momentum_fn=mom)
        assert res["status"] == "collected"
        assert res["scores"]["AAA"] > res["scores"]["BBB"]


class TestC6AbsentIsNotZero:
    """C6 regression (2026-08-04): a dead factor must drop out of the
    composite entirely — absent used to become fabricated 0.0s and a
    degenerate cross-section became all-zero z-scores, so a dead factor
    silently consumed its 1/3 weight (the live 2-factor-as-3-factor bug)."""

    def test_dead_factor_does_not_consume_weight(self):
        live_only = {"momentum": {"A": 90.0, "B": 10.0}}
        with_dead = {
            "momentum": {"A": 90.0, "B": 10.0},
            "insider": {"A": 0.0, "B": 0.0},   # zero spread = dead
        }
        assert (compute_multifactor_scores(with_dead)
                == compute_multifactor_scores(live_only))

    def test_collector_reports_dead_factors(self, db_path):
        # nothing seeded: insider and revisions are absent everywhere
        mom = lambda ts: {"AAA": 80.0, "BBB": 20.0}
        res = collect_multifactor_scores(db_path=db_path,
                                         tickers=["AAA", "BBB"],
                                         as_of="2026-06-17", momentum_fn=mom)
        assert res["status"] == "collected"
        assert set(res["dead_factors"]) == {"insider", "revisions"}
        assert res["scores"]["AAA"] > res["scores"]["BBB"]

    def test_stale_observations_read_as_absent(self, db_path):
        conn = get_connection(db_path)
        try:
            # last insider print >45 days before as_of -> stale -> absent
            snapshot(conn, "insider_opp:AAA", "2026-01-02", 2.0, source="sec_form4")
            snapshot(conn, "insider_opp:BBB", "2026-01-02", -1.0, source="sec_form4")
        finally:
            conn.close()
        mom = lambda ts: {"AAA": 80.0, "BBB": 20.0}
        res = collect_multifactor_scores(db_path=db_path,
                                         tickers=["AAA", "BBB"],
                                         as_of="2026-06-17", momentum_fn=mom)
        assert "insider" in res["dead_factors"]
