"""
Aegis Finance — Portfolio Intelligence Schemas
================================================

Pydantic request/response models for the portfolio intelligence subsystem.
Separated from routers per guardrails (no business logic in routers).

Usage:
    from backend.schemas.portfolio_intelligence import (
        HoldingInput, AnalyzeRequest, MetricPack, SnapshotResponse,
    )
"""

from __future__ import annotations

import re
from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


_TICKER_RE = re.compile(r"^[A-Z0-9.\-]{1,10}$")


# ── Enums ─────────────────────────────────────────────────────────────────────


class PortfolioLane(str, Enum):
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"
    PERSONAL = "personal"


class DecisionAction(str, Enum):
    ENTER = "enter"
    ADD = "add"
    TRIM = "trim"
    EXIT = "exit"


class TriggerReason(str, Enum):
    MONTHLY = "monthly"
    WEEKLY = "weekly_aggressive"
    DRIFT = "drift"
    CRASH_OVERLAY = "crash_overlay"
    MANUAL = "manual"
    INITIALIZATION = "initialization"


# ── Request Models ────────────────────────────────────────────────────────────


class HoldingInput(BaseModel):
    """A single holding in a real portfolio."""
    ticker: str = Field(..., min_length=1, max_length=10)
    shares: float = Field(..., gt=0)
    cost_basis: Optional[float] = Field(None, ge=0)
    purchase_date: Optional[date] = None

    @field_validator("ticker")
    @classmethod
    def validate_ticker(cls, v: str) -> str:
        v = v.upper()
        if not _TICKER_RE.match(v):
            raise ValueError("Ticker must be 1-10 uppercase alphanumeric characters, dots, or hyphens")
        return v


class AnalyzePortfolioRequest(BaseModel):
    """Request to analyze a real portfolio."""
    holdings: list[HoldingInput] = Field(..., min_length=1, max_length=100)


class PersonalDecisionRequest(BaseModel):
    """Request to log a personal conviction decision."""
    ticker: str = Field(..., min_length=1, max_length=10)
    action: DecisionAction
    shares_delta: float = Field(..., gt=0)
    price: float = Field(..., gt=0)
    rationale: str = Field(..., min_length=50)
    thesis_tags: list[str] = Field(default_factory=list)
    conviction: int = Field(..., ge=1, le=5)
    target_price: Optional[float] = Field(None, gt=0)
    stop_price: Optional[float] = Field(None, gt=0)
    planned_exit_trigger: Optional[str] = None
    catalyst_dates: list[date] = Field(default_factory=list)

    @field_validator("ticker")
    @classmethod
    def validate_ticker(cls, v: str) -> str:
        v = v.upper()
        if not _TICKER_RE.match(v):
            raise ValueError("Ticker must be 1-10 uppercase alphanumeric characters, dots, or hyphens")
        return v


class CompareRequest(BaseModel):
    """Request for side-by-side comparison."""
    lane_ids: list[str] = Field(
        default=["conservative", "balanced", "aggressive", "personal"],
        min_length=1,
    )
    benchmarks: list[str] = Field(default=["SPY", "AGG", "60-40"])
    period: str = Field("1Y", pattern="^(1M|3M|6M|YTD|1Y|3Y|ALL)$")


# ── Response Models ───────────────────────────────────────────────────────────


class MetricPack(BaseModel):
    """Standardized performance metric pack. Computed for every portfolio and benchmark."""
    total_return: float
    annualized_return: float
    annualized_volatility: float
    sharpe_ratio: Optional[float] = None
    sortino_ratio: Optional[float] = None
    max_drawdown: float
    max_drawdown_duration_days: Optional[int] = None
    beta_vs_spy: Optional[float] = None
    tracking_error_vs_spy: Optional[float] = None
    information_ratio_vs_spy: Optional[float] = None
    sector_exposure: dict[str, float] = Field(default_factory=dict)
    factor_exposure: dict[str, float] = Field(default_factory=dict)


class RiskFlag(BaseModel):
    """A concentration or risk warning."""
    flag_type: str          # 'single_name', 'sector', 'correlation', 'beta', 'illiquidity'
    severity: str           # 'info', 'warning', 'critical'
    message: str
    details: dict = Field(default_factory=dict)


class RebalanceEventResponse(BaseModel):
    """A single rebalance event with human-readable explanation."""
    id: int
    portfolio_id: str
    triggered_at: str
    trigger_reason: str
    pre_weights: dict[str, float]
    post_weights: dict[str, float]
    crash_prob_3m: Optional[float] = None
    regime: Optional[str] = None
    explanation: str


class SnapshotResponse(BaseModel):
    """Current state of a portfolio lane."""
    portfolio_id: str
    date: str
    weights: dict[str, float]
    metrics: Optional[MetricPack] = None
    flags: list[RiskFlag] = Field(default_factory=list)
    latest_rebalance: Optional[RebalanceEventResponse] = None


class PersonalDecisionResponse(BaseModel):
    """A logged personal decision (immutable once created)."""
    id: int
    timestamp: str
    ticker: str
    action: str
    shares_delta: float
    price: float
    rationale: str
    thesis_tags: list[str]
    conviction: int
    target_price: Optional[float] = None
    stop_price: Optional[float] = None
    planned_exit_trigger: Optional[str] = None
    catalyst_dates: list[str] = Field(default_factory=list)
    is_amendment: bool = False
    amends_id: Optional[int] = None


class SkillMeasurement(BaseModel):
    """Honest skill assessment for personal conviction lane."""
    has_sufficient_data: bool
    months_tracked: int
    message: str
    information_ratio: Optional[float] = None
    hit_rate: Optional[float] = None
    alpha_annualized: Optional[float] = None
    t_statistic: Optional[float] = None


class SellGuardResponse(BaseModel):
    """Information surfaced before a sale — informational only, never prescriptive."""
    ticker: str
    entry_thesis: Optional[str] = None
    current_attribution: dict = Field(default_factory=dict)
    position_vs_plan: dict = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    holding_period_days: Optional[int] = None


class ComparisonResponse(BaseModel):
    """Side-by-side comparison of multiple lanes and benchmarks.

    Phase 5b: lanes/benchmarks values may be None if computation failed
    (e.g. data fetch error) rather than raising — this lets the frontend
    render partial results gracefully. start_date/end_date are returned
    by the router compare endpoint but optional so older callers
    (compute_comparison service) don't break.
    """
    lanes: dict[str, Optional[MetricPack]]
    benchmarks: dict[str, Optional[MetricPack]]
    period: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class HistoryEquityPoint(BaseModel):
    """A single point on a portfolio equity curve.

    config_version marks the track-record segment the point belongs to, so a
    versioned rule/optimization change renders as a clean segment boundary.
    """
    date: str
    value: float
    config_version: Optional[str] = None


class HistoryRebalanceEntry(BaseModel):
    """A single rebalance event for the history response."""
    date: str
    reason: str
    crash_prob: Optional[float] = None
    overlay_armed: bool = False
    explanation: str


class HistoryResponse(BaseModel):
    """Reference lane history — live forward equity curve + rebalance log.

    The equity curve comes from paper_nav (real mark-to-market rows). An empty
    curve with has_nav_data=false means "no data yet" — any rendered line is
    always real NAV, never a synthetic placeholder.
    """
    portfolio_id: str
    period: str
    equity_curve: list[HistoryEquityPoint] = Field(default_factory=list)
    rebalance_log: list[HistoryRebalanceEntry] = Field(default_factory=list)
    has_rebalance_events: bool = False
    has_nav_data: bool = False
    inception_date: Optional[str] = None
    inception_value: Optional[float] = None


class ExplainResponse(BaseModel):
    """Most-recent rebalance explanation. Shape is consistent whether or not events exist."""
    portfolio_id: str
    explanation: str
    last_rebalance_date: Optional[str] = None
    has_rebalance_events: bool = False


class ReplayResult(BaseModel):
    """Result of a walk-forward replay backtest."""
    lane: str
    start_date: str
    end_date: str
    equity_curve: list[dict]     # [{date, value, daily_return}]
    metrics: Optional[MetricPack] = None
    rebalance_log: list[dict] = Field(default_factory=list)
    crash_guard_activations: int = 0
    total_rebalances: int = 0
    total_turnover: float = 0.0
    total_cost_bps: float = 0.0


class ReplaySnapshotResponse(BaseModel):
    """Cached-or-missing wrapper around ReplayResult.

    status: "cached" = computed today, "stale" = older than 24h, "missing" = no cache.
    Frontend uses status to decide whether to show a "stale" badge or prompt for refresh.
    """
    lane_id: str
    status: str
    cached_at: Optional[str] = None
    fresh: bool = False
    result: Optional[ReplayResult] = None


class LaneConfigResponse(BaseModel):
    """Public-facing configuration for a portfolio lane."""
    lane_id: str
    target_equity_pct: float
    target_bond_pct: float
    target_alt_pct: float
    optimizer: str
    max_single_name: float
    max_sector: float
    rebalance_frequency: str
    crash_threshold: float
    equity_cut_pct: float


# ── Config Validation ─────────────────────────────────────────────────────────


class CrashOverlayConfig(BaseModel):
    """Crash overlay configuration within a lane."""
    crash_prob_threshold: float = Field(..., ge=0, le=1)
    equity_cut_pct: float = Field(..., ge=0, le=1)


class LaneConfig(BaseModel):
    """Validated configuration for a single portfolio lane."""
    target_equity_pct: float = Field(..., ge=0, le=1)
    target_bond_pct: float = Field(..., ge=0, le=1)
    target_alt_pct: float = Field(..., ge=0, le=1)
    target_cash_pct: float = Field(0.0, ge=0, le=1)  # explicit cash/T-bill sleeve
    # Active optimizer the engine actually runs. 'equal_weight' is honest today;
    # real HRP/BL land as versioned config changes (intent in planned_optimizer).
    optimizer: str = Field(..., pattern="^(equal_weight|hrp|black-litterman)$")
    planned_optimizer: str = Field(
        "equal_weight", pattern="^(equal_weight|hrp|black-litterman)$"
    )
    max_single_name: float = Field(..., ge=0.01, le=1)
    max_sector: float = Field(..., ge=0.05, le=1)
    rebalance_trigger_drift: float = Field(..., ge=0.01, le=0.5)
    rebalance_frequency: str = Field(..., pattern="^(weekly|monthly|quarterly)$")
    crash_overlay: CrashOverlayConfig
    transaction_cost_bps: float = Field(..., ge=0, le=100)
    slippage_bps: float = Field(..., ge=0, le=100)

    @field_validator("target_alt_pct")
    @classmethod
    def allocations_sum_to_one(cls, v: float, info) -> float:
        equity = info.data.get("target_equity_pct", 0)
        bond = info.data.get("target_bond_pct", 0)
        total = equity + bond + v
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"Allocations must sum to 1.0 (got {total:.4f})")
        return v


class UniverseConfig(BaseModel):
    """Validated universe configuration."""
    frozen_until: str
    sector_etfs: list[str]
    broad_equity: list[str]
    bond_etfs: list[str]
    alternatives: list[str]
    individual_stocks: dict[str, list[str]]

    @property
    def all_tickers(self) -> list[str]:
        """Flat list of all tickers in the universe."""
        tickers = (
            self.sector_etfs
            + self.broad_equity
            + self.bond_etfs
            + self.alternatives
        )
        for sector_tickers in self.individual_stocks.values():
            tickers.extend(sector_tickers)
        return tickers

    @property
    def total_count(self) -> int:
        return len(self.all_tickers)


class PersonalLaneConfig(BaseModel):
    """Validated personal conviction lane configuration."""
    test_fixture_tickers: list[str]
    benchmark: str
    skill_min_months: int = Field(..., ge=1)
    skill_min_t_stat: float = Field(..., gt=0)
    rationale_min_chars: int = Field(..., ge=10)


class PaperPortfoliosConfig(BaseModel):
    """Top-level validated config from paper_portfolios.yaml."""
    universe: UniverseConfig
    conservative: LaneConfig
    balanced: LaneConfig
    aggressive: LaneConfig
    personal: PersonalLaneConfig
    inception: dict
