"""
Tests for the P1 #6 book-lane config layer (Option A — separate book_lanes.yaml).

The load-bearing invariant: adding book lanes must NOT perturb the 4 reference
lanes or their whole-file config hash (TRIAL-001 protection).
"""

import pytest

from backend.config import book_lanes
from backend.db import get_book_config_hash, get_config_hash
from backend.services.portfolio_intelligence.rules import (
    BOOK_LANES,
    REFERENCE_LANES,
    compute_book_mv_weights,
)


class TestLaneSetsIsolated:
    def test_reference_lanes_are_the_four(self):
        assert set(REFERENCE_LANES) == {
            "conservative", "balanced", "aggressive", "balanced-ew-control",
        }

    def test_book_lanes_are_mirror_and_conviction(self):
        assert set(BOOK_LANES) == {"mirror", "conviction"}

    def test_book_lanes_not_in_reference_lanes(self):
        # The corruption guard: book lanes must never leak into the set that
        # apply_config_change_rebalances iterates against the whole-file hash.
        for lane in BOOK_LANES:
            assert lane not in REFERENCE_LANES

    def test_config_hashes_are_independent(self):
        # Different files → different, independent hashes. A book-lane edit can
        # never change the reference-lane hash.
        assert get_config_hash() != get_book_config_hash()
        assert get_config_hash() and get_book_config_hash()  # both resolve


class TestBookConfig:
    def test_holdings_match_confirmed_book(self):
        h = book_lanes["holdings"]
        assert h == {
            "SOC": 700, "DKNG": 150, "NTLA": 250, "AARD": 1000, "BHVN": 300,
            "HUBS": 10, "KYTX": 250, "PRCH": 200, "QUBT": 200, "AMSC": 50,
            "ABSI": 600, "SLDP": 600,
        }

    def test_inception_notional_is_100k(self):
        assert book_lanes["inception"]["notional_usd"] == 100000.0

    def test_purposes(self):
        assert book_lanes["mirror"]["purpose"] == "portfolio-mirror"
        assert book_lanes["conviction"]["purpose"] == "conviction"
        assert book_lanes["conviction"]["optimizer"] == "none"
        assert book_lanes["mirror"]["optimizer"] == "hrp"


class TestComputeBookMVWeights:
    def test_happy_path_sums_to_one_and_proportional(self):
        holdings = {"A": 10, "B": 5}
        prices = {"A": 20.0, "B": 40.0}  # MV: A=200, B=200 → equal weights
        w = compute_book_mv_weights(holdings, prices)
        assert w["A"] == pytest.approx(0.5)
        assert w["B"] == pytest.approx(0.5)
        assert sum(w.values()) == pytest.approx(1.0)

    def test_proportional_to_market_value(self):
        holdings = {"A": 1, "B": 1}
        prices = {"A": 75.0, "B": 25.0}  # 3:1
        w = compute_book_mv_weights(holdings, prices)
        assert w["A"] == pytest.approx(0.75)
        assert w["B"] == pytest.approx(0.25)

    @pytest.mark.parametrize("bad_prices", [
        {"A": 20.0},                 # B missing entirely
        {"A": 20.0, "B": 0.0},       # B zero price
        {"A": 20.0, "B": -5.0},      # B negative price
        {"A": 20.0, "B": None},      # B None
    ])
    def test_fail_loud_on_unpriceable_book(self, bad_prices):
        with pytest.raises(ValueError):
            compute_book_mv_weights({"A": 10, "B": 5}, bad_prices)

    def test_fail_loud_on_empty(self):
        with pytest.raises(ValueError):
            compute_book_mv_weights({}, {})

    def test_fail_loud_on_zero_shares(self):
        with pytest.raises(ValueError):
            compute_book_mv_weights({"A": 0}, {"A": 20.0})
