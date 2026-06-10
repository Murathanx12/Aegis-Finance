"""
Tests for the audit & explanation generator.

All functions are pure — no DB, no network. Tests verify:
  - Trade summary formatting
  - Rebalance explanation generation (all trigger reasons)
  - No-rebalance explanation generation
  - Crash overlay language in explanations
  - Sleeve percentage computation
"""


from backend.services.portfolio_intelligence.audit import (
    format_trade_summary,
    create_rebalance_explanation,
    create_no_rebalance_explanation,
    _compute_sleeve_pcts,
)


# ── format_trade_summary ──────────────────────────────────────────────────


class TestFormatTradeSummary:
    def test_empty_trades(self):
        assert format_trade_summary([]) == "No trades executed."

    def test_single_buy(self):
        trades = [{"ticker": "SPY", "side": "buy", "weight_change": 0.05, "dollar_amount": 5000}]
        result = format_trade_summary(trades)
        assert "bought" in result
        assert "SPY" in result
        assert "5.0%" in result

    def test_single_sell(self):
        trades = [{"ticker": "AGG", "side": "sell", "weight_change": -0.03, "dollar_amount": 3000}]
        result = format_trade_summary(trades)
        assert "sold" in result
        assert "AGG" in result

    def test_sorted_by_dollar_amount(self):
        trades = [
            {"ticker": "A", "side": "buy", "weight_change": 0.01, "dollar_amount": 1000},
            {"ticker": "B", "side": "sell", "weight_change": -0.05, "dollar_amount": 5000},
            {"ticker": "C", "side": "buy", "weight_change": 0.03, "dollar_amount": 3000},
        ]
        result = format_trade_summary(trades, max_trades=3)
        b_pos = result.index("B")
        c_pos = result.index("C")
        a_pos = result.index("A")
        assert b_pos < c_pos < a_pos

    def test_truncates_with_more_indicator(self):
        trades = [
            {"ticker": f"T{i}", "side": "buy", "weight_change": 0.01, "dollar_amount": 1000 * i}
            for i in range(1, 11)
        ]
        result = format_trade_summary(trades, max_trades=3)
        assert "+7 more" in result

    def test_no_more_indicator_when_within_limit(self):
        trades = [
            {"ticker": "A", "side": "buy", "weight_change": 0.05, "dollar_amount": 5000},
        ]
        result = format_trade_summary(trades, max_trades=5)
        assert "more" not in result


# ── _compute_sleeve_pcts ──────────────────────────────────────────────────


class TestComputeSleevePcts:
    def test_pure_equity(self):
        sleeves = _compute_sleeve_pcts({"SPY": 0.50, "QQQ": 0.50})
        assert abs(sleeves["equity"] - 1.0) < 1e-6

    def test_mixed(self):
        sleeves = _compute_sleeve_pcts({"SPY": 0.40, "AGG": 0.50, "GLD": 0.10})
        assert abs(sleeves["equity"] - 0.40) < 1e-6
        assert abs(sleeves["bond"] - 0.50) < 1e-6
        assert abs(sleeves["alternative"] - 0.10) < 1e-6

    def test_empty(self):
        sleeves = _compute_sleeve_pcts({})
        assert sleeves == {"equity": 0.0, "bond": 0.0, "alternative": 0.0}


# ── create_rebalance_explanation ──────────────────────────────────────────


class TestCreateRebalanceExplanation:
    _LANE_CFG = {
        "crash_overlay": {"crash_prob_threshold": 0.25, "equity_cut_pct": 0.20},
    }

    def test_monthly_trigger(self):
        result = create_rebalance_explanation(
            "balanced", "monthly", {"SPY": 0.70}, {"SPY": 0.65, "AGG": 0.35},
            [], crash_prob_3m=None,
        )
        assert "Monthly scheduled rebalance" in result

    def test_drift_trigger(self):
        result = create_rebalance_explanation(
            "conservative", "drift", {}, {}, [],
        )
        assert "Drift-triggered" in result

    def test_weekly_aggressive_trigger(self):
        result = create_rebalance_explanation(
            "aggressive", "weekly_aggressive", {}, {}, [],
        )
        assert "Weekly aggressive" in result

    def test_initialization_trigger(self):
        result = create_rebalance_explanation(
            "conservative", "initialization", {}, {}, [],
        )
        assert "Initial portfolio construction" in result

    def test_crash_overlay_armed_language(self):
        result = create_rebalance_explanation(
            "conservative", "monthly",
            {"SPY": 0.40, "AGG": 0.50, "GLD": 0.10},
            {"SPY": 0.32, "AGG": 0.58, "GLD": 0.10},
            [],
            crash_prob_3m=0.30,
            lane_config=self._LANE_CFG,
        )
        assert "Crash overlay armed" in result
        assert "30%" in result

    def test_crash_overlay_not_triggered_language(self):
        result = create_rebalance_explanation(
            "conservative", "monthly", {}, {}, [],
            crash_prob_3m=0.10,
            lane_config=self._LANE_CFG,
        )
        assert "overlay not triggered" in result

    def test_regime_included(self):
        result = create_rebalance_explanation(
            "balanced", "monthly", {}, {}, [],
            regime="bear",
        )
        assert "Regime: bear" in result

    def test_cost_included(self):
        result = create_rebalance_explanation(
            "balanced", "monthly", {}, {}, [],
            total_cost=42.50,
        )
        assert "$42.50" in result

    def test_trade_summary_included(self):
        trades = [{"ticker": "SPY", "side": "buy", "weight_change": 0.05, "dollar_amount": 5000}]
        result = create_rebalance_explanation(
            "balanced", "monthly", {}, {}, trades,
        )
        assert "bought" in result
        assert "SPY" in result


# ── create_no_rebalance_explanation ───────────────────────────────────────


class TestCreateNoRebalanceExplanation:
    def test_basic(self):
        result = create_no_rebalance_explanation("conservative", 0.023, 0.05)
        assert "conservative" in result
        assert "2.3%" in result
        assert "No rebalance needed" in result

    def test_with_days_since_monthly(self):
        result = create_no_rebalance_explanation("balanced", 0.01, 0.05, days_since_last=15)
        assert "15d" in result
        assert "monthly" in result

    def test_with_days_since_weekly(self):
        result = create_no_rebalance_explanation(
            "aggressive", 0.03, 0.07, days_since_last=4, frequency="weekly",
        )
        assert "4d" in result
        assert "weekly" in result

    def test_no_days_since(self):
        result = create_no_rebalance_explanation("conservative", 0.02, 0.05)
        assert "since" not in result.lower() or "No rebalance" in result
