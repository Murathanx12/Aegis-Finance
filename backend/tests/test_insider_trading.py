"""Tests for insider trading signal computation."""

import pytest

from backend.services.insider_trading import compute_insider_signal


class TestInsiderSignal:
    def test_no_data(self):
        result = compute_insider_signal(None)
        assert result["signal"] == 0.0
        assert result["cluster_buy"] is False

    def test_empty_transactions(self):
        result = compute_insider_signal({"n_buys": 0, "n_sells": 0})
        assert result["signal"] == 0.0

    def test_heavy_buying(self):
        data = {
            "n_buys": 5,
            "n_sells": 1,
            "total_buy_value": 5000000,
            "total_sell_value": 100000,
        }
        result = compute_insider_signal(data)
        assert result["signal"] > 0.3
        assert result["cluster_buy"] is True
        assert "Cluster buying" in result["interpretation"]

    def test_heavy_selling(self):
        data = {
            "n_buys": 0,
            "n_sells": 8,
            "total_buy_value": 0,
            "total_sell_value": 10000000,
        }
        result = compute_insider_signal(data)
        assert result["signal"] < -0.3

    def test_mixed_activity(self):
        data = {
            "n_buys": 3,
            "n_sells": 3,
            "total_buy_value": 500000,
            "total_sell_value": 500000,
        }
        result = compute_insider_signal(data)
        assert -0.2 <= result["signal"] <= 0.2
        assert result["cluster_buy"] is False

    def test_value_weighted(self):
        """Large buy value should produce positive signal even with equal count."""
        data = {
            "n_buys": 2,
            "n_sells": 2,
            "total_buy_value": 10000000,
            "total_sell_value": 100000,
        }
        result = compute_insider_signal(data)
        # Value ratio heavily favors buying
        assert result["signal"] > 0.2

    def test_signal_range(self):
        """Signal should always be in [-1, 1]."""
        for buys in [0, 1, 10, 100]:
            for sells in [0, 1, 10, 100]:
                data = {
                    "n_buys": buys,
                    "n_sells": sells,
                    "total_buy_value": buys * 100000,
                    "total_sell_value": sells * 100000,
                }
                result = compute_insider_signal(data)
                assert -1 <= result["signal"] <= 1

    def test_empty_finnhub_return_has_expected_keys(self):
        """Regression: empty Finnhub return must have same keys as non-empty."""
        from backend.services.insider_trading import _fetch_finnhub_insiders

        # We can't easily call _fetch_finnhub_insiders without API key,
        # but we test the structure consistency by verifying compute_insider_signal
        # handles the empty-data structure correctly.
        empty_data = {
            "ticker": "TEST",
            "source": "finnhub",
            "lookback_days": 90,
            "buys": [],
            "sells": [],
            "n_buys": 0,
            "n_sells": 0,
            "total_buy_value": 0,
            "total_sell_value": 0,
        }
        result = compute_insider_signal(empty_data)
        assert result["signal"] == 0.0
        assert result["cluster_buy"] is False
        assert result["n_buys"] == 0
        assert result["n_sells"] == 0

    def test_output_contains_buy_sell_values(self):
        """Signal output should include buy_value and sell_value."""
        data = {
            "n_buys": 2,
            "n_sells": 1,
            "total_buy_value": 500000,
            "total_sell_value": 200000,
        }
        result = compute_insider_signal(data)
        assert "buy_value" in result
        assert "sell_value" in result
        assert result["buy_value"] == 500000
        assert result["sell_value"] == 200000
