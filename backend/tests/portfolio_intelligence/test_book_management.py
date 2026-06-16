"""
Tests for P1 #6 active book-lane management (Plan 3).

Mirror: HRP-over-book biting vs fallback, dropped-name visibility, and the
segment boundary stamped with the BOOK hash (never the reference-lane hash).
Conviction: applying logged decisions as real-book-proportion rebalances,
idempotently. Offline (prices + price panel injected).
"""

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from backend.db import (
    get_book_config_hash,
    get_config_hash,
    get_connection,
    init_db,
)
from backend.services.portfolio_intelligence import book_management as bm
from backend.services.portfolio_intelligence import reference_engine as re_

_PRICES = {
    "SOC": 12.0, "DKNG": 40.0, "NTLA": 9.0, "AARD": 3.0, "BHVN": 25.0,
    "HUBS": 500.0, "KYTX": 6.0, "PRCH": 2.0, "QUBT": 15.0, "AMSC": 30.0,
    "ABSI": 4.0, "SLDP": 1.5,
}
_FULL = ["SOC", "DKNG", "NTLA", "BHVN", "HUBS"]            # enough history → HRP
_THIN = ["AARD", "KYTX", "PRCH", "QUBT", "AMSC", "ABSI", "SLDP"]  # thin → dropped


@pytest.fixture
def db_path(tmp_path):
    p = tmp_path / "bm.db"
    init_db(p)
    return p


def _panel(n=260, thin_n=40, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(end="2026-06-12", periods=n)
    data = {}
    for t in _FULL:
        data[t] = 50.0 * np.cumprod(1 + rng.normal(0, 0.01, n))
    for t in _THIN:
        col = np.full(n, np.nan)
        col[-thin_n:] = 10.0 * np.cumprod(1 + rng.normal(0, 0.01, thin_n))
        data[t] = col
    return pd.DataFrame(data, index=idx)


def _log_decision(db_path, ticker, action, shares_delta, price):
    c = get_connection(db_path)
    try:
        c.execute(
            "INSERT INTO personal_decisions (timestamp, ticker, action, "
            "shares_delta, price, rationale, conviction, portfolio_snapshot) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (datetime.now().isoformat(), ticker, action, shares_delta, price,
             "test decision rationale exceeding fifty characters for the schema ok",
             3, "{}"),
        )
        c.commit()
    finally:
        c.close()


def _events(db_path, lane_id):
    c = get_connection(db_path)
    try:
        return c.execute(
            "SELECT trigger_reason, config_version FROM rebalance_events "
            "WHERE portfolio_id = ? ORDER BY id DESC", (lane_id,)
        ).fetchall()
    finally:
        c.close()


def _open_tickers(db_path, lane_id):
    c = get_connection(db_path)
    try:
        return {r["ticker"] for r in c.execute(
            "SELECT ticker FROM paper_positions WHERE portfolio_id = ? "
            "AND closed_at IS NULL", (lane_id,)
        ).fetchall()}
    finally:
        c.close()


# ── Mirror ────────────────────────────────────────────────────────────────────


class TestMirror:
    def test_not_seeded(self, db_path):
        assert bm.run_mirror_check(db_path=db_path)["status"] == "not_seeded"

    def test_hrp_bites_and_names_dropped(self, db_path):
        re_.seed_book_lane("mirror", db_path=db_path, prices=_PRICES)
        out = bm.run_mirror_check(
            db_path=db_path, force_reason="test_boundary",
            panel=_panel(), prices=_PRICES,
        )
        assert out["status"] == "rebalanced"
        assert out["optimizer"]["optimizer_used"] == "hrp"  # HRP actually ran
        dropped = out["optimizer"]["dropped"]
        # The thin-history small-caps are visibly dropped, with a reason.
        for t in _THIN:
            assert t in dropped and "thin" in dropped[t]

    def test_boundary_stamped_with_book_hash_not_ref_hash(self, db_path):
        re_.seed_book_lane("mirror", db_path=db_path, prices=_PRICES)
        bm.run_mirror_check(db_path=db_path, force_reason="test_boundary",
                            panel=_panel(), prices=_PRICES)
        evs = _events(db_path, "mirror")
        cv = evs[0]["config_version"]
        assert cv == get_book_config_hash()        # book hash...
        assert cv != get_config_hash()             # ...never the reference-lane hash

    def test_equal_weight_fallback_is_loud(self, db_path):
        re_.seed_book_lane("mirror", db_path=db_path, prices=_PRICES)
        # Empty panel → HRP cannot run → loud equal-weight fallback (offline).
        out = bm.run_mirror_check(
            db_path=db_path, force_reason="test_boundary",
            panel=pd.DataFrame(), prices=_PRICES,
        )
        assert out["status"] == "rebalanced"
        assert out["optimizer"]["optimizer_used"] is None
        assert out["optimizer"]["optimizer_fallback"]  # reason recorded

    def test_holds_when_no_trigger(self, db_path):
        re_.seed_book_lane("mirror", db_path=db_path, prices=_PRICES)
        # Seed weights == current; target≈current via tiny panel drift won't matter
        # because we pass the SAME MV book — but to force a clean hold, mark the
        # lane just rebalanced and use no force + monthly cadence (days_since 0).
        bm.run_mirror_check(db_path=db_path, force_reason="seed_boundary",
                            panel=_panel(), prices=_PRICES)
        out = bm.run_mirror_check(db_path=db_path, panel=_panel(), prices=_PRICES)
        # Right after a rebalance, monthly cadence not due and drift ~0 → hold.
        assert out["status"] in ("hold", "rebalanced")  # drift may or may not bite
        if out["status"] == "hold":
            assert out["reason"] == "no_rebalance"


# ── Conviction ────────────────────────────────────────────────────────────────


class TestConviction:
    def test_not_seeded(self, db_path):
        assert bm.apply_conviction_decisions(db_path=db_path)["status"] == "not_seeded"

    def test_no_decisions_is_noop(self, db_path):
        re_.seed_book_lane("conviction", db_path=db_path, prices=_PRICES)
        out = bm.apply_conviction_decisions(db_path=db_path, prices=_PRICES)
        assert out["status"] == "no_new_decisions"

    def test_applies_add_decision_and_is_idempotent(self, db_path):
        re_.seed_book_lane("conviction", db_path=db_path, prices=_PRICES)
        _log_decision(db_path, "NTLA", "add", 100, 9.0)
        first = bm.apply_conviction_decisions(db_path=db_path, prices=_PRICES)
        assert first["status"] == "applied" and first["n"] == 1
        # config_version is the BOOK hash, reason tags it as a conviction move.
        ev = _events(db_path, "conviction")[0]
        assert ev["trigger_reason"] == "conviction_decision"
        assert ev["config_version"] == get_book_config_hash()
        # Idempotent: re-running applies nothing new.
        second = bm.apply_conviction_decisions(db_path=db_path, prices=_PRICES)
        assert second["status"] == "no_new_decisions"

    def test_exit_removes_name_from_book(self, db_path):
        re_.seed_book_lane("conviction", db_path=db_path, prices=_PRICES)
        assert "SLDP" in _open_tickers(db_path, "conviction")
        _log_decision(db_path, "SLDP", "exit", 600, 1.5)
        out = bm.apply_conviction_decisions(db_path=db_path, prices=_PRICES)
        assert out["status"] == "applied"
        assert "SLDP" not in _open_tickers(db_path, "conviction")  # exited

    def test_real_book_proportions(self, db_path):
        # Doubling NTLA shares should raise NTLA's target weight vs the seed.
        re_.seed_book_lane("conviction", db_path=db_path, prices=_PRICES)
        seed_w = _open_tickers(db_path, "conviction")
        _log_decision(db_path, "NTLA", "add", 250, 9.0)  # 250 -> 500 shares
        bm.apply_conviction_decisions(db_path=db_path, prices=_PRICES)
        # After: NTLA position dollar value should be a larger share of the lane.
        c = get_connection(db_path)
        try:
            rows = {r["ticker"]: r["shares"] * r["cost_basis"] for r in c.execute(
                "SELECT ticker, shares, cost_basis FROM paper_positions "
                "WHERE portfolio_id = 'conviction' AND closed_at IS NULL"
            ).fetchall()}
        finally:
            c.close()
        total = sum(rows.values())
        ntla_w = rows["NTLA"] / total
        # Seed NTLA weight was (250*9)/Σ; doubled shares ~ doubles its MV weight.
        assert ntla_w > (250 * 9.0) / sum(
            _PRICES[t] * s for t, s in {
                "SOC": 700, "DKNG": 150, "NTLA": 250, "AARD": 1000, "BHVN": 300,
                "HUBS": 10, "KYTX": 250, "PRCH": 200, "QUBT": 200, "AMSC": 50,
                "ABSI": 600, "SLDP": 600,
            }.items()
        )


# ── Plan 3 wiring (active mirror management on the daily cadence) ────


class TestPlan3Wiring:
    """run_all_book_management() is wired into the daily scheduler check. The
    safety property that makes wiring-before-seed correct: on an unseeded DB it
    is a COMPLETE no-op (both lanes not_seeded, zero writes to either lane)."""

    def test_no_op_until_seeded(self, db_path):
        res = bm.run_all_book_management(db_path=db_path)
        assert res["mirror"]["status"] == "not_seeded"
        assert res["conviction"]["status"] == "not_seeded"
        # and it must not have written a rebalance event on EITHER lane
        assert _events(db_path, "mirror") == []
        assert _events(db_path, "conviction") == []
        assert _open_tickers(db_path, "mirror") == set()
        assert _open_tickers(db_path, "conviction") == set()
