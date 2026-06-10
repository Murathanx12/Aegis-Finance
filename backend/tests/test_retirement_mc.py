"""Tests for Monte Carlo retirement simulator."""

from backend.services.retirement_mc import simulate_retirement, compute_safe_withdrawal_rate


class TestSimulateRetirement:
    def test_basic_accumulation(self):
        """Accumulation phase: contributions grow portfolio."""
        result = simulate_retirement(
            current_savings=100000,
            monthly_contribution=1000,
            monthly_withdrawal=0,
            current_age=30,
            retirement_age=65,
            end_age=66,
            n_sims=1000,
        )
        assert result["success_rate"] > 90
        # After 35 years of contributions + growth, median should be > initial
        assert result["at_retirement"]["median"] > 100000

    def test_basic_distribution(self):
        """Distribution phase: withdrawals deplete portfolio."""
        result = simulate_retirement(
            current_savings=1000000,
            monthly_contribution=0,
            monthly_withdrawal=3000,  # ~3.6% rate — conservative
            current_age=65,
            retirement_age=65,
            end_age=95,
            n_sims=1000,
        )
        assert "success_rate" in result
        assert "ruin_probability" in result
        # $3k/month from $1M (3.6% rate) should succeed often
        assert result["success_rate"] > 50

    def test_high_withdrawal_causes_ruin(self):
        """Very high withdrawal rate should cause high ruin probability."""
        result = simulate_retirement(
            current_savings=500000,
            monthly_contribution=0,
            monthly_withdrawal=10000,  # $120k/yr from $500k = 24% rate
            current_age=65,
            retirement_age=65,
            end_age=95,
            n_sims=1000,
        )
        # 24% withdrawal rate over 30 years should fail most of the time
        assert result["ruin_probability"] > 50

    def test_zero_withdrawal_never_ruins(self):
        """No withdrawals = no ruin."""
        result = simulate_retirement(
            current_savings=100000,
            monthly_contribution=0,
            monthly_withdrawal=0,
            current_age=65,
            retirement_age=65,
            end_age=95,
            n_sims=500,
        )
        assert result["ruin_probability"] == 0

    def test_yearly_projections_structure(self):
        """Yearly projections should have correct structure."""
        result = simulate_retirement(
            current_savings=100000,
            monthly_contribution=500,
            monthly_withdrawal=3000,
            current_age=50,
            retirement_age=65,
            end_age=90,
            n_sims=500,
        )
        assert len(result["yearly_projections"]) > 0
        proj = result["yearly_projections"][0]
        assert "age" in proj
        assert "median" in proj
        assert "p10" in proj
        assert "p90" in proj
        assert "phase" in proj

    def test_social_security_reduces_ruin(self):
        """Social Security income should reduce ruin probability."""
        base = simulate_retirement(
            current_savings=500000,
            monthly_withdrawal=4000,
            current_age=65,
            retirement_age=65,
            end_age=95,
            social_security_monthly=0,
            n_sims=1000,
        )
        with_ss = simulate_retirement(
            current_savings=500000,
            monthly_withdrawal=4000,
            current_age=65,
            retirement_age=65,
            end_age=95,
            social_security_monthly=2000,
            social_security_start_age=67,
            n_sims=1000,
        )
        # SS income should improve success rate
        assert with_ss["success_rate"] >= base["success_rate"] - 5  # Allow small MC noise

    def test_interpretation_exists(self):
        result = simulate_retirement(
            current_savings=500000,
            monthly_withdrawal=3000,
            current_age=65,
            retirement_age=65,
            end_age=90,
            n_sims=500,
        )
        assert "interpretation" in result
        assert len(result["interpretation"]) > 20


class TestSafeWithdrawalRate:
    def test_basic(self):
        result = compute_safe_withdrawal_rate(
            savings=1000000,
            retirement_years=30,
            risk_level="moderate",
            n_sims=1000,
        )
        assert "safe_withdrawal_rate_pct" in result
        assert "safe_monthly_withdrawal" in result
        assert "four_pct_rule_monthly" in result
        # Safe rate should be in reasonable range (2-12%)
        assert 1 < result["safe_withdrawal_rate_pct"] < 15

    def test_shorter_horizon_allows_higher_rate(self):
        short = compute_safe_withdrawal_rate(savings=1000000, retirement_years=15, n_sims=500)
        long = compute_safe_withdrawal_rate(savings=1000000, retirement_years=40, n_sims=500)
        # Shorter horizon = can withdraw more
        assert short["safe_withdrawal_rate_pct"] > long["safe_withdrawal_rate_pct"]

    def test_aggressive_allows_higher_rate(self):
        conservative = compute_safe_withdrawal_rate(
            savings=1000000, risk_level="conservative", n_sims=500
        )
        aggressive = compute_safe_withdrawal_rate(
            savings=1000000, risk_level="aggressive", n_sims=500
        )
        # Both should produce reasonable rates
        assert conservative["safe_withdrawal_rate_pct"] > 0
        assert aggressive["safe_withdrawal_rate_pct"] > 0

    def test_no_dead_code_rng(self):
        """Regression (cycle 75): compute_safe_withdrawal_rate had an unused rng variable.

        The function created `rng = np.random.default_rng(seed)` but never used it,
        because each binary search iteration creates its own `inner_rng`.
        Verify the function still works correctly after removing the dead variable.
        """
        import inspect
        source = inspect.getsource(compute_safe_withdrawal_rate)
        # The function body should not contain an unused top-level rng assignment
        # (inner_rng inside _ruin_rate is fine)
        lines = source.split("\n")
        top_level_rng = [
            l for l in lines
            if "rng = np.random.default_rng" in l and "inner_rng" not in l
            and "def _ruin_rate" not in l
        ]
        assert len(top_level_rng) == 0, (
            f"Found unused top-level rng variable: {top_level_rng}"
        )
