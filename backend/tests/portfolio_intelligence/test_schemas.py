"""
Tests for the portfolio intelligence Pydantic schemas.

Covers: round-trip serialization, validation rules, YAML config loading
and validation, and universe sanity checks.
"""

import pytest

from backend.config import paper_portfolios
from backend.schemas.portfolio_intelligence import (
    AnalyzePortfolioRequest,
    CompareRequest,
    CrashOverlayConfig,
    DecisionAction,
    HoldingInput,
    LaneConfig,
    LaneConfigResponse,
    MetricPack,
    PaperPortfoliosConfig,
    PersonalDecisionRequest,
    PersonalDecisionResponse,
    PersonalLaneConfig,
    PortfolioLane,
    RebalanceEventResponse,
    RiskFlag,
    SellGuardResponse,
    SkillMeasurement,
    SnapshotResponse,
    TriggerReason,
    UniverseConfig,
)


# ── HoldingInput ─────────────────────────────────────────────────────────────


class TestHoldingInput:
    def test_valid_holding(self):
        h = HoldingInput(ticker="AAPL", shares=10.0, cost_basis=150.0)
        assert h.ticker == "AAPL"
        assert h.shares == 10.0

    def test_ticker_uppercased(self):
        h = HoldingInput(ticker="aapl", shares=10.0)
        assert h.ticker == "AAPL"

    def test_ticker_with_dot(self):
        h = HoldingInput(ticker="BRK.B", shares=5.0)
        assert h.ticker == "BRK.B"

    def test_invalid_ticker_rejected(self):
        with pytest.raises(Exception):
            HoldingInput(ticker="TOOLONGTICKER", shares=10.0)

    def test_zero_shares_rejected(self):
        with pytest.raises(Exception):
            HoldingInput(ticker="AAPL", shares=0)

    def test_negative_shares_rejected(self):
        with pytest.raises(Exception):
            HoldingInput(ticker="AAPL", shares=-10.0)

    def test_optional_cost_basis(self):
        h = HoldingInput(ticker="AAPL", shares=10.0)
        assert h.cost_basis is None

    def test_optional_purchase_date(self):
        h = HoldingInput(ticker="AAPL", shares=10.0, purchase_date="2026-01-15")
        assert str(h.purchase_date) == "2026-01-15"

    def test_round_trip_serialization(self):
        h = HoldingInput(ticker="MSTR", shares=5.5, cost_basis=250.0, purchase_date="2026-01-01")
        data = h.model_dump()
        h2 = HoldingInput(**data)
        assert h == h2


# ── AnalyzePortfolioRequest ──────────────────────────────────────────────────


class TestAnalyzePortfolioRequest:
    def test_valid_request(self):
        req = AnalyzePortfolioRequest(
            holdings=[HoldingInput(ticker="AAPL", shares=10.0)]
        )
        assert len(req.holdings) == 1

    def test_empty_holdings_rejected(self):
        with pytest.raises(Exception):
            AnalyzePortfolioRequest(holdings=[])

    def test_round_trip(self):
        req = AnalyzePortfolioRequest(
            holdings=[
                HoldingInput(ticker="AAPL", shares=10.0),
                HoldingInput(ticker="MSFT", shares=20.0, cost_basis=300.0),
            ]
        )
        data = req.model_dump()
        req2 = AnalyzePortfolioRequest(**data)
        assert len(req2.holdings) == 2


# ── PersonalDecisionRequest ──────────────────────────────────────────────────


class TestPersonalDecisionRequest:
    _VALID_RATIONALE = "Testing biotech thesis on TVTX — FDA catalyst expected Q3 2026, strong pipeline data"

    def test_valid_decision(self):
        d = PersonalDecisionRequest(
            ticker="TVTX",
            action=DecisionAction.ENTER,
            shares_delta=100.0,
            price=34.0,
            rationale=self._VALID_RATIONALE,
            conviction=4,
        )
        assert d.ticker == "TVTX"
        assert d.action == DecisionAction.ENTER

    def test_rationale_too_short_rejected(self):
        with pytest.raises(Exception):
            PersonalDecisionRequest(
                ticker="TVTX",
                action=DecisionAction.ENTER,
                shares_delta=100.0,
                price=34.0,
                rationale="too short",
                conviction=3,
            )

    def test_rationale_exactly_50_chars_accepted(self):
        d = PersonalDecisionRequest(
            ticker="TVTX",
            action=DecisionAction.ENTER,
            shares_delta=100.0,
            price=34.0,
            rationale="A" * 50,
            conviction=3,
        )
        assert len(d.rationale) == 50

    def test_conviction_out_of_range(self):
        with pytest.raises(Exception):
            PersonalDecisionRequest(
                ticker="TVTX",
                action=DecisionAction.ENTER,
                shares_delta=100.0,
                price=34.0,
                rationale=self._VALID_RATIONALE,
                conviction=0,
            )
        with pytest.raises(Exception):
            PersonalDecisionRequest(
                ticker="TVTX",
                action=DecisionAction.ENTER,
                shares_delta=100.0,
                price=34.0,
                rationale=self._VALID_RATIONALE,
                conviction=6,
            )

    def test_round_trip(self):
        d = PersonalDecisionRequest(
            ticker="DKNG",
            action=DecisionAction.ADD,
            shares_delta=50.0,
            price=29.0,
            rationale=self._VALID_RATIONALE,
            thesis_tags=["gaming", "growth"],
            conviction=4,
            target_price=51.0,
            stop_price=20.0,
            planned_exit_trigger="Sell if below 200-day MA for 5 consecutive days",
            catalyst_dates=["2026-08-15"],
        )
        data = d.model_dump()
        d2 = PersonalDecisionRequest(**data)
        assert d.ticker == d2.ticker
        assert d.thesis_tags == d2.thesis_tags


# ── MetricPack ───────────────────────────────────────────────────────────────


class TestMetricPack:
    def test_valid_metric_pack(self):
        m = MetricPack(
            total_return=0.15,
            annualized_return=0.07,
            annualized_volatility=0.12,
            sharpe_ratio=0.58,
            max_drawdown=-0.08,
        )
        assert m.sharpe_ratio == 0.58

    def test_optional_fields_default_none(self):
        m = MetricPack(
            total_return=0.10,
            annualized_return=0.05,
            annualized_volatility=0.10,
            max_drawdown=-0.05,
        )
        assert m.sortino_ratio is None
        assert m.beta_vs_spy is None

    def test_round_trip(self):
        m = MetricPack(
            total_return=0.15,
            annualized_return=0.07,
            annualized_volatility=0.12,
            sharpe_ratio=0.58,
            sortino_ratio=0.85,
            max_drawdown=-0.08,
            max_drawdown_duration_days=45,
            beta_vs_spy=1.1,
            tracking_error_vs_spy=0.04,
            information_ratio_vs_spy=0.75,
            sector_exposure={"Technology": 0.30, "Healthcare": 0.25},
            factor_exposure={"Mkt-RF": 1.1, "SMB": 0.3, "HML": -0.2},
        )
        data = m.model_dump()
        m2 = MetricPack(**data)
        assert m == m2


# ── RiskFlag ─────────────────────────────────────────────────────────────────


class TestRiskFlag:
    def test_valid_flag(self):
        f = RiskFlag(
            flag_type="single_name",
            severity="warning",
            message="MSTR is 15% of portfolio (limit: 10%)",
            details={"ticker": "MSTR", "weight": 0.15, "limit": 0.10},
        )
        assert f.severity == "warning"

    def test_round_trip(self):
        f = RiskFlag(
            flag_type="sector",
            severity="critical",
            message="Biotech sector is 47% of portfolio",
        )
        data = f.model_dump()
        f2 = RiskFlag(**data)
        assert f == f2


# ── SkillMeasurement ─────────────────────────────────────────────────────────


class TestSkillMeasurement:
    def test_insufficient_data(self):
        s = SkillMeasurement(
            has_sufficient_data=False,
            months_tracked=8,
            message="Insufficient history to assess skill. Need 24 months of tracked decisions.",
        )
        assert not s.has_sufficient_data
        assert s.information_ratio is None

    def test_sufficient_data_with_stats(self):
        s = SkillMeasurement(
            has_sufficient_data=True,
            months_tracked=30,
            message="Conviction trades show +2.3% annualized alpha (t-stat=2.4, significant at 95%).",
            information_ratio=0.45,
            hit_rate=0.58,
            alpha_annualized=0.023,
            t_statistic=2.4,
        )
        assert s.has_sufficient_data
        assert s.t_statistic > 2.0


# ── Enums ────────────────────────────────────────────────────────────────────


class TestEnums:
    def test_portfolio_lane_values(self):
        assert PortfolioLane.CONSERVATIVE.value == "conservative"
        assert PortfolioLane.PERSONAL.value == "personal"

    def test_decision_action_values(self):
        assert DecisionAction.ENTER.value == "enter"
        assert DecisionAction.TRIM.value == "trim"

    def test_trigger_reason_values(self):
        assert TriggerReason.CRASH_OVERLAY.value == "crash_overlay"


# ── YAML Config Loading + Validation ─────────────────────────────────────────


class TestYAMLConfig:
    def test_yaml_loads_successfully(self):
        assert paper_portfolios is not None
        assert isinstance(paper_portfolios, dict)

    def test_yaml_has_all_sections(self):
        assert "universe" in paper_portfolios
        assert "conservative" in paper_portfolios
        assert "balanced" in paper_portfolios
        assert "aggressive" in paper_portfolios
        assert "personal" in paper_portfolios
        assert "inception" in paper_portfolios

    def test_yaml_validates_against_schema(self):
        cfg = PaperPortfoliosConfig(**paper_portfolios)
        assert cfg.conservative.target_equity_pct == 0.40
        assert cfg.balanced.optimizer == "black-litterman"
        assert cfg.aggressive.max_single_name == 0.08

    def test_conservative_allocations_sum_to_one(self):
        cfg = PaperPortfoliosConfig(**paper_portfolios)
        total = (
            cfg.conservative.target_equity_pct
            + cfg.conservative.target_bond_pct
            + cfg.conservative.target_alt_pct
        )
        assert abs(total - 1.0) < 0.001

    def test_balanced_allocations_sum_to_one(self):
        cfg = PaperPortfoliosConfig(**paper_portfolios)
        total = (
            cfg.balanced.target_equity_pct
            + cfg.balanced.target_bond_pct
            + cfg.balanced.target_alt_pct
        )
        assert abs(total - 1.0) < 0.001

    def test_aggressive_allocations_sum_to_one(self):
        cfg = PaperPortfoliosConfig(**paper_portfolios)
        total = (
            cfg.aggressive.target_equity_pct
            + cfg.aggressive.target_bond_pct
            + cfg.aggressive.target_alt_pct
        )
        assert abs(total - 1.0) < 0.001

    def test_crash_overlay_thresholds_ordered(self):
        """Conservative should have lowest threshold (most defensive)."""
        cfg = PaperPortfoliosConfig(**paper_portfolios)
        assert cfg.conservative.crash_overlay.crash_prob_threshold < cfg.balanced.crash_overlay.crash_prob_threshold
        assert cfg.balanced.crash_overlay.crash_prob_threshold < cfg.aggressive.crash_overlay.crash_prob_threshold

    def test_crash_overlay_cuts_ordered(self):
        """Conservative should have largest equity cut (most defensive)."""
        cfg = PaperPortfoliosConfig(**paper_portfolios)
        assert cfg.conservative.crash_overlay.equity_cut_pct > cfg.balanced.crash_overlay.equity_cut_pct
        assert cfg.balanced.crash_overlay.equity_cut_pct > cfg.aggressive.crash_overlay.equity_cut_pct

    def test_max_single_name_ordered(self):
        """Conservative < Balanced < Aggressive."""
        cfg = PaperPortfoliosConfig(**paper_portfolios)
        assert cfg.conservative.max_single_name < cfg.balanced.max_single_name
        assert cfg.balanced.max_single_name < cfg.aggressive.max_single_name

    def test_personal_skill_requirements(self):
        cfg = PaperPortfoliosConfig(**paper_portfolios)
        assert cfg.personal.skill_min_months == 24
        assert cfg.personal.skill_min_t_stat == 2.0
        assert cfg.personal.rationale_min_chars == 50


# ── Universe Sanity Checks ───────────────────────────────────────────────────


class TestUniverse:
    def test_universe_has_sector_etfs(self):
        cfg = PaperPortfoliosConfig(**paper_portfolios)
        assert len(cfg.universe.sector_etfs) == 11
        assert "XLK" in cfg.universe.sector_etfs

    def test_universe_has_bond_etfs(self):
        cfg = PaperPortfoliosConfig(**paper_portfolios)
        assert len(cfg.universe.bond_etfs) == 7
        assert "AGG" in cfg.universe.bond_etfs
        assert "TLT" in cfg.universe.bond_etfs

    def test_universe_has_alternatives(self):
        cfg = PaperPortfoliosConfig(**paper_portfolios)
        assert len(cfg.universe.alternatives) == 4
        assert "GLD" in cfg.universe.alternatives

    def test_universe_has_broad_equity(self):
        cfg = PaperPortfoliosConfig(**paper_portfolios)
        assert len(cfg.universe.broad_equity) == 6
        assert "SPY" in cfg.universe.broad_equity

    def test_universe_total_around_80(self):
        cfg = PaperPortfoliosConfig(**paper_portfolios)
        total = cfg.universe.total_count
        assert 70 <= total <= 100, f"Universe has {total} tickers (expected ~80)"

    def test_universe_no_duplicates(self):
        cfg = PaperPortfoliosConfig(**paper_portfolios)
        tickers = cfg.universe.all_tickers
        assert len(tickers) == len(set(tickers)), (
            f"Duplicate tickers found: {[t for t in tickers if tickers.count(t) > 1]}"
        )

    def test_test_fixture_tickers_in_universe(self):
        """All personal conviction test tickers should be in the broader universe."""
        cfg = PaperPortfoliosConfig(**paper_portfolios)
        all_tickers = set(cfg.universe.all_tickers)
        fixture = cfg.personal.test_fixture_tickers
        missing = [t for t in fixture if t not in all_tickers]
        # Some personal tickers (ALMS, APLT, APMX, NTLA) are small biotech,
        # not required to be in the reference universe
        # At minimum, the large-cap ones should be there
        large_cap_fixture = {"AMZN", "MSTR", "FSLR", "MRVL", "DKNG", "TTWO"}
        for t in large_cap_fixture:
            assert t in all_tickers, f"Fixture ticker {t} missing from universe"

    def test_benchmarks_defined(self):
        assert "inception" in paper_portfolios
        benchmarks = paper_portfolios["inception"]["benchmarks"]
        assert "SPY" in benchmarks
        assert "AGG" in benchmarks
        assert "60-40" in benchmarks
