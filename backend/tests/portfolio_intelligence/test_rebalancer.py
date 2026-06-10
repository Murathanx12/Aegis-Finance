"""
Tests for the rebalancer (trade computation).

All functions are pure — no DB, no network. Tests verify:
  - Turnover calculation
  - Trade list correctness (old + trades ≈ new)
  - Transaction cost and slippage
  - Zero-turnover edge case
  - Proportional trade sizing
  - hypothesis property tests for pre+trades==post invariant
"""

from hypothesis import given, settings, strategies as st

from backend.services.portfolio_intelligence.rebalancer import (
    compute_trades,
    estimate_turnover,
)


# ── estimate_turnover ──────────────────────────────────────────────────────


class TestEstimateTurnover:
    def test_identical_weights(self):
        w = {"A": 0.50, "B": 0.50}
        assert estimate_turnover(w, w) == 0.0

    def test_full_swap(self):
        old = {"A": 1.0}
        new = {"B": 1.0}
        assert abs(estimate_turnover(old, new) - 1.0) < 1e-10

    def test_partial_rebalance(self):
        old = {"A": 0.60, "B": 0.40}
        new = {"A": 0.40, "B": 0.60}
        assert abs(estimate_turnover(old, new) - 0.20) < 1e-10

    def test_new_ticker_added(self):
        old = {"A": 0.50, "B": 0.50}
        new = {"A": 0.33, "B": 0.33, "C": 0.34}
        turnover = estimate_turnover(old, new)
        assert turnover > 0

    def test_ticker_removed(self):
        old = {"A": 0.33, "B": 0.33, "C": 0.34}
        new = {"A": 0.50, "B": 0.50}
        turnover = estimate_turnover(old, new)
        assert turnover > 0

    def test_symmetric(self):
        old = {"A": 0.70, "B": 0.30}
        new = {"A": 0.40, "B": 0.60}
        assert abs(estimate_turnover(old, new) - estimate_turnover(new, old)) < 1e-10

    def test_empty_old(self):
        turnover = estimate_turnover({}, {"A": 0.50, "B": 0.50})
        assert abs(turnover - 0.50) < 1e-10

    def test_empty_both(self):
        assert estimate_turnover({}, {}) == 0.0


# ── compute_trades ─────────────────────────────────────────────────────────


class TestComputeTrades:
    _PRICES = {"A": 100.0, "B": 50.0, "C": 200.0}

    def test_basic_trade_list(self):
        old = {"A": 0.60, "B": 0.40}
        new = {"A": 0.40, "B": 0.60}
        trades, cost = compute_trades(old, new, self._PRICES, 100_000)
        assert len(trades) == 2
        assert cost > 0

    def test_trade_sides(self):
        old = {"A": 0.60, "B": 0.40}
        new = {"A": 0.40, "B": 0.60}
        trades, _ = compute_trades(old, new, self._PRICES, 100_000)
        trade_map = {t["ticker"]: t for t in trades}
        assert trade_map["A"]["side"] == "sell"
        assert trade_map["B"]["side"] == "buy"

    def test_zero_turnover_empty_trades(self):
        w = {"A": 0.50, "B": 0.50}
        trades, cost = compute_trades(w, w, self._PRICES, 100_000)
        assert trades == []
        assert cost == 0.0

    def test_dollar_amounts(self):
        old = {"A": 1.0}
        new = {"A": 0.50, "B": 0.50}
        trades, _ = compute_trades(old, new, self._PRICES, 100_000)
        trade_map = {t["ticker"]: t for t in trades}
        assert abs(trade_map["A"]["dollar_amount"] - 50_000) < 1.0
        assert abs(trade_map["B"]["dollar_amount"] - 50_000) < 1.0

    def test_shares_from_price(self):
        old = {"A": 1.0}
        new = {"B": 1.0}
        trades, _ = compute_trades(old, new, self._PRICES, 100_000)
        trade_map = {t["ticker"]: t for t in trades}
        assert abs(trade_map["A"]["shares"] - 1000.0) < 0.01  # $100k / $100
        assert abs(trade_map["B"]["shares"] - 2000.0) < 0.01  # $100k / $50

    def test_transaction_cost_calculation(self):
        old = {"A": 1.0}
        new = {"B": 1.0}
        trades, total_cost = compute_trades(
            old, new, self._PRICES, 100_000, cost_bps=10, slippage_bps=0,
        )
        expected = 100_000 * (10 / 10_000) * 2  # two trades, each $100k
        assert abs(total_cost - expected) < 0.01

    def test_slippage_calculation(self):
        old = {"A": 1.0}
        new = {"B": 1.0}
        trades, total_cost = compute_trades(
            old, new, self._PRICES, 100_000, cost_bps=0, slippage_bps=5,
        )
        expected = 100_000 * (5 / 10_000) * 2
        assert abs(total_cost - expected) < 0.01

    def test_missing_price_skips_ticker(self):
        old = {"A": 0.50, "B": 0.50}
        new = {"A": 0.30, "B": 0.30, "C": 0.40}
        prices = {"A": 100.0, "B": 50.0}  # no price for C
        trades, _ = compute_trades(old, new, prices, 100_000)
        tickers = {t["ticker"] for t in trades}
        assert "C" not in tickers

    def test_weight_change_recorded(self):
        old = {"A": 0.60, "B": 0.40}
        new = {"A": 0.40, "B": 0.60}
        trades, _ = compute_trades(old, new, self._PRICES, 100_000)
        trade_map = {t["ticker"]: t for t in trades}
        assert abs(trade_map["A"]["weight_change"] - (-0.20)) < 1e-4
        assert abs(trade_map["B"]["weight_change"] - 0.20) < 1e-4

    def test_new_ticker_is_buy(self):
        old = {"A": 1.0}
        new = {"A": 0.50, "C": 0.50}
        trades, _ = compute_trades(old, new, self._PRICES, 100_000)
        trade_map = {t["ticker"]: t for t in trades}
        assert trade_map["C"]["side"] == "buy"

    def test_removed_ticker_is_sell(self):
        old = {"A": 0.50, "C": 0.50}
        new = {"A": 1.0}
        trades, _ = compute_trades(old, new, self._PRICES, 100_000)
        trade_map = {t["ticker"]: t for t in trades}
        assert trade_map["C"]["side"] == "sell"

    def test_zero_price_skipped(self):
        old = {"A": 1.0}
        new = {"B": 1.0}
        trades, _ = compute_trades(old, new, {"A": 100.0, "B": 0.0}, 100_000)
        tickers = {t["ticker"] for t in trades}
        assert "B" not in tickers

    def test_trades_applying_to_old_gives_new_basic(self):
        """Sanity check: old_weights + trade weight_changes ≈ new_weights."""
        old = {"A": 0.40, "B": 0.35, "C": 0.25}
        new = {"A": 0.20, "B": 0.50, "C": 0.30}
        trades, _ = compute_trades(old, new, self._PRICES, 100_000)
        reconstructed = dict(old)
        for t in trades:
            reconstructed[t["ticker"]] = reconstructed.get(t["ticker"], 0) + t["weight_change"]
        for ticker in new:
            assert abs(reconstructed.get(ticker, 0) - new[ticker]) < 1e-4, (
                f"{ticker}: reconstructed={reconstructed.get(ticker, 0):.6f}, expected={new[ticker]:.6f}"
            )

    @given(
        n=st.integers(min_value=2, max_value=10),
        notional=st.floats(min_value=10_000, max_value=10_000_000),
        seed=st.integers(min_value=0, max_value=2**31),
    )
    @settings(max_examples=100)
    def test_pre_plus_trades_equals_post(self, n, notional, seed):
        """Property: old_weights + trade weight_changes ≈ new_weights (hypothesis-generated)."""
        import numpy as np
        rng = np.random.default_rng(seed)
        tickers = [f"T{i}" for i in range(n)]
        old_raw = rng.dirichlet(np.ones(n))
        new_raw = rng.dirichlet(np.ones(n))
        prices = {t: float(50 + rng.random() * 450) for t in tickers}
        old = dict(zip(tickers, old_raw))
        new = dict(zip(tickers, new_raw))
        trades, _ = compute_trades(old, new, prices, notional)
        reconstructed = dict(old)
        for t in trades:
            reconstructed[t["ticker"]] = reconstructed.get(t["ticker"], 0) + t["weight_change"]
        for ticker in tickers:
            assert abs(reconstructed.get(ticker, 0) - new[ticker]) < 1e-3, (
                f"{ticker}: reconstructed={reconstructed.get(ticker, 0):.6f}, expected={new[ticker]:.6f}"
            )
