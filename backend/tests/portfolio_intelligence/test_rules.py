"""
Tests for the reference portfolio rules engine.

All functions are pure — no DB, no network. Tests verify:
  - Asset classification
  - Target weight computation (equal-weight fallback)
  - Rebalance trigger logic (drift, schedule, initialization)
  - Crash overlay exact threshold boundaries
  - Position limit clipping with weight normalization
  - hypothesis property tests for position limits and crash overlay
"""

from datetime import date

import pytest
from hypothesis import given, settings, strategies as st

from backend.services.portfolio_intelligence.rules import (
    classify_asset,
    compute_target_weights,
    should_rebalance,
    apply_crash_overlay,
    enforce_position_limits,
    _equal_weight,
    _get_sleeve_tickers,
)
from backend.config import paper_portfolios


# ── classify_asset ──────────────────────────────────────────────────────────


class TestClassifyAsset:
    def test_bond_etfs(self):
        for ticker in ["AGG", "TLT", "IEF", "SHY", "LQD", "HYG", "TIP"]:
            assert classify_asset(ticker) == "bond", f"{ticker} should be bond"

    def test_alternatives(self):
        for ticker in ["GLD", "IAU", "USO", "VNQ"]:
            assert classify_asset(ticker) == "alternative", f"{ticker} should be alternative"

    def test_equities(self):
        for ticker in ["AAPL", "SPY", "XLK", "AMZN", "MSTR"]:
            assert classify_asset(ticker) == "equity", f"{ticker} should be equity"

    def test_unknown_defaults_to_equity(self):
        assert classify_asset("ZZZZ") == "equity"


# ── _get_sleeve_tickers ────────────────────────────────────────────────────


class TestSleeveTickers:
    def test_sleeves_non_empty(self):
        universe = paper_portfolios.get("universe", {})
        sleeves = _get_sleeve_tickers(universe)
        assert len(sleeves["equity"]) > 20
        assert len(sleeves["bond"]) == 7
        assert len(sleeves["alternative"]) == 4

    def test_no_overlap(self):
        universe = paper_portfolios.get("universe", {})
        sleeves = _get_sleeve_tickers(universe)
        eq = set(sleeves["equity"])
        bond = set(sleeves["bond"])
        alt = set(sleeves["alternative"])
        assert not eq & bond, f"Equity/bond overlap: {eq & bond}"
        assert not eq & alt, f"Equity/alt overlap: {eq & alt}"
        assert not bond & alt, f"Bond/alt overlap: {bond & alt}"


# ── _equal_weight ───────────────────────────────────────────────────────────


class TestEqualWeight:
    def test_basic(self):
        result = _equal_weight(["A", "B", "C"], 0.60)
        assert len(result) == 3
        assert abs(sum(result.values()) - 0.60) < 1e-10

    def test_single_ticker(self):
        result = _equal_weight(["A"], 0.40)
        assert result["A"] == 0.40

    def test_zero_target(self):
        result = _equal_weight(["A", "B"], 0.0)
        assert result == {}

    def test_empty_tickers(self):
        result = _equal_weight([], 0.50)
        assert result == {}


# ── compute_target_weights ──────────────────────────────────────────────────


class TestComputeTargetWeights:
    def test_conservative_weights_sum_to_one(self):
        cfg = paper_portfolios["conservative"]
        weights = compute_target_weights(cfg)
        assert abs(sum(weights.values()) - 1.0) < 1e-6

    def test_balanced_weights_sum_to_one(self):
        cfg = paper_portfolios["balanced"]
        weights = compute_target_weights(cfg)
        assert abs(sum(weights.values()) - 1.0) < 1e-6

    def test_aggressive_weights_sum_to_one(self):
        cfg = paper_portfolios["aggressive"]
        weights = compute_target_weights(cfg)
        assert abs(sum(weights.values()) - 1.0) < 1e-6

    def test_conservative_has_bonds(self):
        cfg = paper_portfolios["conservative"]
        weights = compute_target_weights(cfg)
        bond_weight = sum(w for t, w in weights.items() if classify_asset(t) == "bond")
        assert bond_weight > 0.40, f"Conservative should have >40% bonds, got {bond_weight:.0%}"

    def test_aggressive_mostly_equity(self):
        cfg = paper_portfolios["aggressive"]
        weights = compute_target_weights(cfg)
        eq_weight = sum(w for t, w in weights.items() if classify_asset(t) == "equity")
        assert eq_weight > 0.85, f"Aggressive should have >85% equity, got {eq_weight:.0%}"

    def test_all_weights_positive(self):
        for lane in ["conservative", "balanced", "aggressive"]:
            cfg = paper_portfolios[lane]
            weights = compute_target_weights(cfg)
            for t, w in weights.items():
                assert w >= 0, f"{lane}/{t} has negative weight {w}"

    def test_no_zero_weight_tickers(self):
        cfg = paper_portfolios["conservative"]
        weights = compute_target_weights(cfg)
        for t, w in weights.items():
            assert w > 0, f"Ticker {t} has zero weight"


# ── should_rebalance ───────────────────────────────────────────────────────


class TestShouldRebalance:
    def test_drift_triggers(self):
        current = {"A": 0.50, "B": 0.50}
        target = {"A": 0.40, "B": 0.60}
        trigger, reason = should_rebalance(current, target, 0.05, "monthly", date(2026, 4, 1))
        assert trigger is True
        assert reason == "drift"

    def test_drift_below_threshold_no_trigger(self):
        current = {"A": 0.50, "B": 0.50}
        target = {"A": 0.48, "B": 0.52}
        trigger, reason = should_rebalance(
            current, target, 0.05, "monthly",
            date(2026, 4, 20), as_of_date=date(2026, 4, 25),
        )
        assert trigger is False
        assert reason == "no_rebalance"

    def test_exact_threshold_no_trigger(self):
        current = {"A": 0.75, "B": 0.25}
        target = {"A": 0.50, "B": 0.50}  # drift = 0.25 exactly (power-of-2, no FP error)
        # Pin as_of_date to 1 day after last_rebalance so monthly schedule
        # cannot fire — we're isolating the drift-threshold rule here.
        trigger, reason = should_rebalance(
            current, target, 0.25, "monthly",
            date(2026, 4, 1), as_of_date=date(2026, 4, 2),
        )
        assert trigger is False  # > not >=

    def test_monthly_schedule_triggers(self):
        current = {"A": 0.50, "B": 0.50}
        target = {"A": 0.50, "B": 0.50}  # no drift
        trigger, reason = should_rebalance(
            current, target, 0.05, "monthly",
            date(2026, 3, 1), as_of_date=date(2026, 4, 1),
        )
        assert trigger is True
        assert reason == "monthly"

    def test_weekly_schedule_triggers(self):
        current = {"A": 0.50, "B": 0.50}
        target = {"A": 0.50, "B": 0.50}
        trigger, reason = should_rebalance(
            current, target, 0.07, "weekly",
            date(2026, 4, 14), as_of_date=date(2026, 4, 21),
        )
        assert trigger is True
        assert reason == "weekly_aggressive"

    def test_weekly_too_soon(self):
        current = {"A": 0.50, "B": 0.50}
        target = {"A": 0.50, "B": 0.50}
        trigger, reason = should_rebalance(
            current, target, 0.07, "weekly",
            date(2026, 4, 18), as_of_date=date(2026, 4, 21),
        )
        assert trigger is False

    def test_no_last_rebalance_triggers_initialization(self):
        current = {"A": 0.50, "B": 0.50}
        target = {"A": 0.50, "B": 0.50}
        trigger, reason = should_rebalance(current, target, 0.05, "monthly", None)
        assert trigger is True
        assert reason == "initialization"

    def test_new_ticker_counts_as_drift(self):
        current = {"A": 0.50, "B": 0.50}
        target = {"A": 0.33, "B": 0.33, "C": 0.34}
        trigger, reason = should_rebalance(current, target, 0.05, "monthly", date(2026, 4, 20))
        assert trigger is True
        assert reason == "drift"


# ── apply_crash_overlay ─────────────────────────────────────────────────────


class TestCrashOverlay:
    _CONSERVATIVE_CFG = paper_portfolios["conservative"]
    _BALANCED_CFG = paper_portfolios["balanced"]
    _AGGRESSIVE_CFG = paper_portfolios["aggressive"]

    def test_conservative_triggers_at_threshold(self):
        """Conservative threshold = 0.25. Prob = 0.251 should trigger."""
        weights = {"SPY": 0.40, "AGG": 0.50, "GLD": 0.10}
        adjusted, triggered = apply_crash_overlay(weights, 0.251, self._CONSERVATIVE_CFG)
        assert triggered is True
        assert adjusted["SPY"] < 0.40

    def test_conservative_no_trigger_below_threshold(self):
        """Conservative threshold = 0.25. Prob = 0.249 should NOT trigger."""
        weights = {"SPY": 0.40, "AGG": 0.50, "GLD": 0.10}
        adjusted, triggered = apply_crash_overlay(weights, 0.249, self._CONSERVATIVE_CFG)
        assert triggered is False
        assert adjusted == weights

    def test_exact_threshold_no_trigger(self):
        """Prob exactly at threshold should NOT trigger (> not >=)."""
        weights = {"SPY": 0.40, "AGG": 0.50, "GLD": 0.10}
        adjusted, triggered = apply_crash_overlay(weights, 0.25, self._CONSERVATIVE_CFG)
        assert triggered is False

    def test_balanced_threshold_higher_than_conservative(self):
        """Balanced threshold (0.30) > conservative (0.25)."""
        weights = {"SPY": 0.70, "AGG": 0.25, "GLD": 0.05}
        _, triggered_bal = apply_crash_overlay(weights, 0.27, self._BALANCED_CFG)
        _, triggered_con = apply_crash_overlay(weights, 0.27, self._CONSERVATIVE_CFG)
        assert triggered_con is True  # 0.27 > 0.25
        assert triggered_bal is False  # 0.27 < 0.30

    def test_aggressive_threshold_highest(self):
        weights = {"SPY": 0.95, "AGG": 0.05}
        _, triggered = apply_crash_overlay(weights, 0.35, self._AGGRESSIVE_CFG)
        assert triggered is False  # 0.35 < 0.40

    def test_equity_cut_redistributed_to_cash(self):
        from backend.services.portfolio_intelligence.nav import CASH_TICKER

        weights = {"SPY": 0.40, "AGG": 0.50, "GLD": 0.10}
        adjusted, _ = apply_crash_overlay(weights, 0.30, self._CONSERVATIVE_CFG)
        # Conservative cuts equity 20%: the cut rotates to CASH (zero-duration,
        # earns rf), NOT into bonds — genuinely defensive in a rates selloff.
        assert adjusted.get(CASH_TICKER, 0.0) > 0.0
        bond_after = sum(w for t, w in adjusted.items() if classify_asset(t) == "bond")
        assert bond_after == pytest.approx(0.50, abs=1e-6)  # bonds untouched

    def test_weights_sum_to_one_after_overlay(self):
        for lane_name, cfg in [
            ("conservative", self._CONSERVATIVE_CFG),
            ("balanced", self._BALANCED_CFG),
            ("aggressive", self._AGGRESSIVE_CFG),
        ]:
            weights = {"SPY": 0.50, "QQQ": 0.20, "AGG": 0.20, "GLD": 0.10}
            adjusted, _ = apply_crash_overlay(weights, 0.50, cfg)
            assert abs(sum(adjusted.values()) - 1.0) < 1e-6, f"{lane_name} weights don't sum to 1"

    @pytest.mark.parametrize("lane_name,cfg", [
        ("conservative", paper_portfolios["conservative"]),
        ("balanced", paper_portfolios["balanced"]),
        ("aggressive", paper_portfolios["aggressive"]),
    ])
    @pytest.mark.parametrize("crash_prob", [0.01, 0.05, 0.10, 0.20])
    def test_overlay_never_levers_up(self, lane_name, cfg, crash_prob):
        """Defensive-only: equity must NEVER increase, for any lane, at any low crash prob."""
        weights = {"SPY": 0.50, "QQQ": 0.20, "AGG": 0.20, "GLD": 0.10}
        adjusted, triggered = apply_crash_overlay(weights, crash_prob, cfg)
        eq_before = sum(w for t, w in weights.items() if classify_asset(t) == "equity")
        eq_after = sum(w for t, w in adjusted.items() if classify_asset(t) == "equity")
        assert eq_after <= eq_before + 1e-10, (
            f"{lane_name} at crash_prob={crash_prob}: equity went from "
            f"{eq_before:.4f} to {eq_after:.4f} — overlay levered up!"
        )

    @given(crash_prob=st.floats(min_value=0.0, max_value=1.0))
    @settings(max_examples=50)
    def test_overlay_never_levers_up_hypothesis(self, crash_prob):
        """Property: for ANY crash probability, equity never increases (hypothesis-generated)."""
        weights = {"SPY": 0.50, "QQQ": 0.20, "AGG": 0.20, "GLD": 0.10}
        for lane_name, cfg in [
            ("conservative", self._CONSERVATIVE_CFG),
            ("balanced", self._BALANCED_CFG),
            ("aggressive", self._AGGRESSIVE_CFG),
        ]:
            adjusted, _ = apply_crash_overlay(weights, crash_prob, cfg)
            eq_before = sum(w for t, w in weights.items() if classify_asset(t) == "equity")
            eq_after = sum(w for t, w in adjusted.items() if classify_asset(t) == "equity")
            assert eq_after <= eq_before + 1e-10, (
                f"{lane_name} at crash_prob={crash_prob}: equity levered up"
            )


# ── enforce_position_limits ─────────────────────────────────────────────────


class TestEnforcePositionLimits:
    def test_clips_single_name(self):
        tickers = {f"T{i}": 1.0 / 15 for i in range(15)}
        tickers["T0"] = 0.50  # way over 10%
        total = sum(tickers.values())
        weights = {t: w / total for t, w in tickers.items()}
        result = enforce_position_limits(weights, max_single_name=0.10, max_sector=1.0)
        assert result["T0"] <= 0.10 + 1e-4
        assert abs(sum(result.values()) - 1.0) < 1e-6

    def test_conservative_name_limit(self):
        """Conservative max_single_name = 0.03. Top-heavy 40-ticker portfolio should be clipped."""
        tickers = [f"T{i}" for i in range(40)]
        weights = {t: 1.0 / 40 for t in tickers}
        weights["T0"] = 0.20  # force one position way over 3%
        total = sum(weights.values())
        weights = {t: w / total for t, w in weights.items()}
        result = enforce_position_limits(weights, max_single_name=0.03, max_sector=1.0)
        for t, w in result.items():
            assert w <= 0.03 + 1e-4, f"{t} exceeds 3% limit: {w:.4f}"
        assert abs(sum(result.values()) - 1.0) < 1e-6

    def test_clips_sector(self):
        sector_map = {"A": "Tech", "B": "Tech", "C": "Health", "D": "Energy", "E": "Energy"}
        weights = {"A": 0.30, "B": 0.25, "C": 0.20, "D": 0.15, "E": 0.10}
        result = enforce_position_limits(
            weights, max_single_name=1.0, max_sector=0.40, sector_map=sector_map,
        )
        tech_total = result.get("A", 0) + result.get("B", 0)
        assert tech_total <= 0.40 + 1e-4
        assert abs(sum(result.values()) - 1.0) < 1e-6

    @given(
        n=st.integers(min_value=3, max_value=30),
        cap_pct=st.floats(min_value=0.04, max_value=0.50),
        seed=st.integers(min_value=0, max_value=2**31),
    )
    @settings(max_examples=100)
    def test_weights_always_sum_to_one(self, n, cap_pct, seed):
        """Property: output weights always sum to 1.0 (hypothesis-generated)."""
        import numpy as np
        rng = np.random.default_rng(seed)
        raw = rng.dirichlet(np.ones(n))
        tickers = [f"T{i}" for i in range(n)]
        weights = dict(zip(tickers, raw))
        result = enforce_position_limits(weights, max_single_name=cap_pct, max_sector=1.0)
        assert abs(sum(result.values()) - 1.0) < 1e-6

    @given(
        n=st.integers(min_value=15, max_value=50),
        seed=st.integers(min_value=0, max_value=2**31),
    )
    @settings(max_examples=100)
    def test_no_weight_exceeds_cap(self, n, seed):
        """Property: no weight exceeds max_single_name when constraint is feasible (hypothesis-generated)."""
        import numpy as np
        rng = np.random.default_rng(seed)
        raw = rng.dirichlet(np.ones(n))
        tickers = [f"T{i}" for i in range(n)]
        weights = dict(zip(tickers, raw))
        cap = max(0.03, 1.0 / n + 0.01)  # ensure n * cap > 1.0 (feasible)
        result = enforce_position_limits(weights, max_single_name=cap, max_sector=1.0)
        for t, w in result.items():
            assert w <= cap + 1e-4, f"{t} = {w:.4f} exceeds cap {cap:.4f}"

    def test_empty_weights(self):
        result = enforce_position_limits({}, max_single_name=0.05, max_sector=0.30)
        assert result == {}

    def test_already_compliant(self):
        weights = {"A": 0.25, "B": 0.25, "C": 0.25, "D": 0.25}
        result = enforce_position_limits(weights, max_single_name=0.30, max_sector=1.0)
        for t in weights:
            assert abs(result[t] - weights[t]) < 1e-6

    def test_excess_redistributed_proportionally(self):
        weights = {"BIG": 0.60, "SMALL1": 0.20, "SMALL2": 0.20}
        result = enforce_position_limits(weights, max_single_name=0.10, max_sector=1.0)
        # BIG clipped from 60% to 10%, 50% redistributed to SMALL1/SMALL2
        # SMALL1 and SMALL2 had equal weight → should receive equal redistribution
        assert abs(result["SMALL1"] - result["SMALL2"]) < 1e-6
        assert result["SMALL1"] > 0.20  # should have increased
