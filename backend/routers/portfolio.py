"""
Portfolio Analytics Router
============================

POST /api/portfolio/analyze           — Analyze existing portfolio
POST /api/portfolio/build             — Build goal-based portfolio
POST /api/portfolio/optimize          — Advanced optimization (CVaR, risk parity, etc.)
POST /api/portfolio/compare           — Compare all optimization methods
POST /api/portfolio/factor-exposures  — Fama-French 5-factor decomposition
POST /api/portfolio/copula-risk       — Copula-based tail risk (joint crash probability)
POST /api/portfolio/benchmark         — Benchmark analytics (tracking error, IR, active share, capture)
"""

import asyncio
import logging
import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field, field_validator

from backend.services.portfolio_engine import PortfolioEngine, score_risk_profile

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])
logger = logging.getLogger(__name__)

_TICKER_RE = re.compile(r"^[A-Z0-9.\-]{1,10}$")


class Holding(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=10)
    shares: float = Field(..., gt=0)
    current_price: float = Field(..., gt=0)

    @field_validator("ticker")
    @classmethod
    def validate_ticker(cls, v: str) -> str:
        v = v.upper()
        if not _TICKER_RE.match(v):
            raise ValueError("Ticker must be 1-10 uppercase alphanumeric characters or dots")
        return v


class AnalyzeRequest(BaseModel):
    holdings: list[Holding] = Field(..., min_length=1, max_length=50)


class BuildRequest(BaseModel):
    risk_tolerance: str = Field("moderate", pattern="^(conservative|moderate|aggressive)$")
    investment_amount: float = Field(10000, gt=0)
    time_horizon: str = Field("5y", pattern="^(1y|3y|5y|10y)$")
    method: str = Field("template", pattern="^(template|black-litterman|hrp)$")
    goal: str = Field("growth", pattern="^(preservation|income|growth|aggressive_growth|retirement)$")


class QuestionnaireRequest(BaseModel):
    horizon: str = Field("5y", pattern="^(1y|3y|5y|10y|20y)$")
    risk_tolerance: str = Field("moderate", pattern="^(conservative|moderate|aggressive)$")
    loss_reaction: str = Field("hold", pattern="^(sell|hold|buy_more)$")
    experience: str = Field("beginner", pattern="^(none|beginner|intermediate|advanced)$")
    income_stability: str = Field("stable", pattern="^(unstable|stable|very_stable)$")
    goal: str = Field("growth", pattern="^(preservation|income|growth|aggressive_growth)$")


@router.post("/questionnaire")
async def portfolio_questionnaire(request: QuestionnaireRequest):
    """Score a risk profile from questionnaire answers and return recommended allocation."""
    try:
        profile = score_risk_profile(request.model_dump())
        # Auto-build a portfolio from the profile
        portfolio = await asyncio.to_thread(
            PortfolioEngine.build_portfolio,
            risk_tolerance=profile["allocation_style"],
            investment_amount=10000,
            time_horizon=request.horizon,
        )
        return {**profile, "recommended_portfolio": portfolio}
    except Exception as e:
        logger.error("portfolio questionnaire failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze")
async def analyze_portfolio(request: AnalyzeRequest):
    """Analyze a portfolio: allocations, correlations, VaR/CVaR, Sharpe, risk number."""
    try:
        holdings = [h.model_dump() for h in request.holdings]
        result = await asyncio.to_thread(_analyze_with_risk_number, holdings)
        return result
    except Exception as e:
        logger.error("portfolio analyze failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


def _analyze_with_risk_number(holdings: list[dict]) -> dict:
    """Run portfolio analysis and attach risk number (1-100)."""
    result = PortfolioEngine.analyze_portfolio(holdings)

    # Compute risk number
    tickers = [h["ticker"] for h in holdings]
    total_value = sum(h["shares"] * h["current_price"] for h in holdings)
    weights = {}
    for h in holdings:
        w = (h["shares"] * h["current_price"]) / total_value if total_value > 0 else 0
        weights[h["ticker"]] = w

    try:
        import yfinance as yf
        import pandas as pd
        from backend.services.risk_number import compute_risk_number

        # Fetch returns for all tickers
        data = yf.download(tickers, period="2y", progress=False)
        if data is not None and "Close" in data.columns.get_level_values(0) if hasattr(data.columns, 'get_level_values') else "Close" in data.columns:
            if len(tickers) == 1:
                close = data["Close"].to_frame(tickers[0])
            else:
                close = data["Close"]
            returns = close.pct_change().dropna()

            # Also get S&P 500 for beta calculation
            bench = yf.download("SPY", period="2y", progress=False)
            bench_returns = None
            if bench is not None and len(bench) > 30:
                bench_returns = bench["Close"].pct_change().dropna()

            risk = compute_risk_number(returns, weights, benchmark_returns=bench_returns)
            result["risk_number"] = risk
    except Exception as e:
        logger.warning("Risk number computation failed: %s", e)

    # Factor exposures (FF5 decomposition at portfolio level)
    try:
        from backend.services.factor_model import decompose_portfolio
        factor_result = decompose_portfolio(weights)
        if factor_result:
            result["factor_exposures"] = {
                "r_squared": factor_result.get("portfolio", {}).get("r_squared"),
                "alpha_annual": factor_result.get("portfolio", {}).get("alpha_annual"),
                "market_beta": factor_result.get("portfolio", {}).get("market_beta"),
                "style": factor_result.get("portfolio", {}).get("style"),
                "stocks": {
                    t: {
                        "market_beta": s.get("market_beta"),
                        "style": s.get("style"),
                    }
                    for t, s in factor_result.get("stocks", {}).items()
                },
            }
    except Exception as e:
        logger.warning("Factor exposure computation failed: %s", e)

    # Stress test summary (historical scenario impacts on this portfolio)
    try:
        from backend.services.stress_testing import stress_test_portfolio
        stress = stress_test_portfolio(weights)
        if stress and "scenarios" in stress:
            scenario_summaries = {}
            for sid, s in stress["scenarios"].items():
                scenario_summaries[s["name"]] = {
                    "portfolio_drawdown_pct": round(s.get("portfolio_drawdown", 0) * 100, 2),
                    "sp500_drawdown_pct": round(s.get("sp500_drawdown", 0) * 100, 2),
                    "relative_to_market": s.get("relative_to_market"),
                }
            worst = stress.get("worst_case", {})
            result["stress_test"] = {
                "scenarios": scenario_summaries,
                "worst_scenario": worst.get("name"),
                "worst_drawdown_pct": round(worst.get("drawdown", 0) * 100, 2) if worst.get("drawdown") is not None else None,
            }
    except Exception as e:
        logger.warning("Stress test computation failed: %s", e)

    # Inline attribution + MCTR (Brinson-Fachler performance decomposition)
    try:
        from backend.services.attribution import full_portfolio_analytics
        attr_result = full_portfolio_analytics(holdings, benchmark_ticker="SPY", period="1mo")
        if attr_result:
            attribution = attr_result.get("attribution", {})
            result["attribution_summary"] = {
                "period": attr_result.get("period"),
                "total_allocation_effect": attribution.get("total_allocation_effect"),
                "total_selection_effect": attribution.get("total_selection_effect"),
                "total_interaction_effect": attribution.get("total_interaction_effect"),
                "total_active_return": attribution.get("total_active_return"),
                "portfolio_return": attribution.get("portfolio_return"),
                "benchmark_return": attribution.get("benchmark_return"),
            }
            risk_contrib = attr_result.get("risk_contributions")
            if risk_contrib and "contributions" in risk_contrib:
                result["mctr_summary"] = {
                    "portfolio_vol": risk_contrib.get("portfolio_volatility"),
                    "top_risk_contributors": [
                        {
                            "ticker": c.get("ticker"),
                            "weight_pct": c.get("weight_pct"),
                            "risk_contrib_pct": c.get("risk_contribution_pct"),
                            "mctr": c.get("mctr"),
                        }
                        for c in sorted(
                            risk_contrib["contributions"],
                            key=lambda x: abs(x.get("risk_contribution_pct", 0)),
                            reverse=True,
                        )[:5]
                    ],
                }
    except Exception as e:
        logger.warning("Inline attribution/MCTR failed: %s", e)

    # Benchmark analytics (tracking error, information ratio, active share, capture ratios)
    try:
        from backend.services.benchmark_analytics import compute_benchmark_analytics
        bench_result = compute_benchmark_analytics(weights, benchmark="SPY")
        if bench_result:
            result["benchmark_analytics"] = {
                "tracking_error_pct": bench_result["tracking_error_pct"],
                "information_ratio": bench_result["information_ratio"],
                "active_return_annual_pct": bench_result["active_return_annual_pct"],
                "active_share": bench_result.get("active_share", {}).get("active_share_pct") if bench_result.get("active_share") else None,
                "active_share_label": bench_result.get("active_share", {}).get("label") if bench_result.get("active_share") else None,
                "up_capture": bench_result["capture_ratios"].get("up_capture"),
                "down_capture": bench_result["capture_ratios"].get("down_capture"),
                "beta_vs_benchmark": bench_result["regression"].get("beta") if bench_result["regression"].get("available") else None,
                "r_squared": bench_result["regression"].get("r_squared") if bench_result["regression"].get("available") else None,
                "management_style": bench_result["interpretation"].get("management_style"),
                "insights": bench_result["interpretation"].get("insights", []),
            }
    except Exception as e:
        logger.warning("Benchmark analytics failed: %s", e)

    # Portfolio-level drawdown analysis (rolling returns + max drawdown history)
    try:
        import yfinance as yf
        import pandas as pd
        import numpy as np
        from backend.services.drawdown_analyzer import analyze_drawdowns, compute_rolling_returns

        # Build portfolio return series from holdings
        _ptickers = [h["ticker"] for h in holdings]
        _pdata = yf.download(_ptickers, period="5y", progress=False)
        if _pdata is not None and len(_pdata) > 60:
            if len(_ptickers) == 1:
                _pclose = _pdata["Close"].to_frame(_ptickers[0])
            else:
                _pclose = _pdata["Close"]
            _preturns = _pclose.pct_change().dropna()

            # Weighted portfolio returns
            _pw = np.array([weights.get(t, 0) for t in _preturns.columns])
            if _pw.sum() > 0:
                _pw = _pw / _pw.sum()
                _port_returns = (_preturns * _pw).sum(axis=1)
                _port_prices = (1 + _port_returns).cumprod() * 100  # Normalize to 100

                dd_result = analyze_drawdowns(_port_prices)
                rolling = compute_rolling_returns(_port_prices, windows=[252])

                result["portfolio_drawdowns"] = {
                    "total_drawdowns": dd_result["summary"].get("n_drawdowns", 0),
                    "max_drawdown_pct": dd_result["summary"].get("max_depth_pct"),
                    "avg_recovery_days": dd_result["summary"].get("avg_recovery_days"),
                    "current_drawdown_pct": dd_result["current"]["depth_pct"] if dd_result.get("current") else 0.0,
                    "rolling_return_1y": rolling.get(252, {}).get("current"),
                }
    except Exception as e:
        logger.warning("Portfolio drawdown analysis failed: %s", e)

    return result


class ProjectRequest(BaseModel):
    holdings: list[Holding] = Field(..., min_length=1, max_length=50)
    years: int = Field(1, ge=1, le=30)
    monthly_add: float = Field(0, ge=0, le=1_000_000)


@router.post("/project")
async def project_portfolio(request: ProjectRequest):
    """Project portfolio value forward."""
    try:
        holdings = [h.model_dump() for h in request.holdings]
        result = await asyncio.to_thread(
            PortfolioEngine.project_portfolio,
            holdings,
            years=request.years,
            monthly_add=request.monthly_add,
        )
        return result
    except Exception as e:
        logger.error("portfolio projection failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/build")
async def build_portfolio(request: BuildRequest):
    """Build a goal-based portfolio allocation."""
    try:
        result = await asyncio.to_thread(
            PortfolioEngine.build_portfolio,
            risk_tolerance=request.risk_tolerance,
            investment_amount=request.investment_amount,
            time_horizon=request.time_horizon,
            method=request.method,
            goal=request.goal,
        )
        return result
    except Exception as e:
        logger.error("portfolio build failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ── Advanced Optimization ──────────────────────────────────────────


class OptimizeRequest(BaseModel):
    tickers: list[str] = Field(..., min_length=2, max_length=50)
    method: str = Field("mean_cvar", pattern="^(mean_cvar|risk_parity|max_diversification|hrp)$")
    lookback_days: int = Field(504, ge=126, le=1260)


@router.post("/optimize")
async def optimize_portfolio(request: OptimizeRequest):
    """Advanced portfolio optimization with institutional methods.

    Methods:
    - mean_cvar: Minimize Conditional VaR (tail risk)
    - risk_parity: Equal risk contribution
    - max_diversification: Maximize diversification ratio
    - hrp: Hierarchical Risk Parity
    """
    from backend.services.portfolio_optimizer import (
        optimize_mean_cvar, optimize_risk_parity,
        optimize_max_diversification, optimize_hrp,
    )

    tickers = [t.upper() for t in request.tickers]
    method_map = {
        "mean_cvar": optimize_mean_cvar,
        "risk_parity": optimize_risk_parity,
        "max_diversification": optimize_max_diversification,
        "hrp": optimize_hrp,
    }

    fn = method_map.get(request.method)
    if not fn:
        raise HTTPException(status_code=422, detail=f"Unknown method: {request.method}")

    try:
        result = await asyncio.to_thread(fn, tickers, request.lookback_days)
        if result is None:
            raise HTTPException(status_code=404, detail="Insufficient data for optimization")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("portfolio optimization failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


class AttributionRequest(BaseModel):
    holdings: list[Holding] = Field(..., min_length=1, max_length=50)
    benchmark: str = Field("SPY", min_length=1, max_length=10)
    period: str = Field("1mo", pattern="^(1mo|3mo|1y|ytd)$")


@router.post("/attribution")
async def portfolio_attribution(request: AttributionRequest):
    """Brinson-Fachler performance attribution vs benchmark (Bloomberg PORT style).

    Decomposes active return into: allocation effect, selection effect, interaction effect.
    """
    from backend.services.attribution import full_portfolio_analytics

    holdings_data = [h.model_dump() for h in request.holdings]
    try:
        result = await asyncio.to_thread(
            full_portfolio_analytics, holdings_data, request.benchmark, request.period
        )
        if result is None:
            raise HTTPException(status_code=404, detail="Insufficient data for attribution")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("portfolio attribution failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


class RiskContribRequest(BaseModel):
    tickers: list[str] = Field(..., min_length=2, max_length=50)
    weights: list[float] = Field(..., min_length=2, max_length=50)

    @field_validator("weights")
    @classmethod
    def validate_weights(cls, v: list[float], info) -> list[float]:
        tickers = info.data.get("tickers")
        if tickers is not None and len(v) != len(tickers):
            raise ValueError(
                f"weights length ({len(v)}) must match tickers length ({len(tickers)})"
            )
        if any(w < 0 for w in v):
            raise ValueError("weights must be non-negative")
        return v


@router.post("/risk-contributions")
async def risk_contributions(request: RiskContribRequest):
    """Marginal Contribution to Risk (MCTR) — which holdings drive portfolio risk."""
    from backend.services.attribution import compute_risk_contributions

    tickers = [t.upper() for t in request.tickers]
    try:
        result = await asyncio.to_thread(
            compute_risk_contributions, tickers, request.weights
        )
        if result is None:
            raise HTTPException(status_code=404, detail="Insufficient data for risk contribution")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("risk contribution failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/commentary")
async def portfolio_commentary(request: AnalyzeRequest):
    """AI-generated portfolio commentary (Bloomberg PORT Enterprise style)."""
    from backend.services.llm_analyzer import generate_portfolio_commentary, is_available

    if not is_available():
        raise HTTPException(status_code=503, detail="No LLM provider configured (set ANTHROPIC_API_KEY or DEEPSEEK_API_KEY)")

    holdings_data = [
        {"ticker": h.ticker, "weight": h.shares * h.current_price, "sector": ""}
        for h in request.holdings
    ]
    # Normalize weights
    total = sum(h["weight"] for h in holdings_data)
    if total > 0:
        for h in holdings_data:
            h["weight"] /= total

    try:
        result = await asyncio.to_thread(
            generate_portfolio_commentary, holdings_data, {}, None, None
        )
        if result is None:
            raise HTTPException(status_code=500, detail="LLM analysis failed")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("portfolio commentary failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


class FactorExposureRequest(BaseModel):
    holdings: list[Holding] = Field(..., min_length=1, max_length=50)
    lookback_days: int = Field(756, ge=126, le=1260)


@router.post("/factor-exposures")
async def portfolio_factor_exposures(request: FactorExposureRequest):
    """Fama-French 5-factor decomposition for a portfolio.

    Shows factor loadings (market beta, size, value, profitability, investment),
    alpha, R², and style interpretation for each holding and the portfolio overall.
    """
    from backend.services.factor_model import decompose_portfolio

    # Convert holdings to weights dict
    total_value = sum(h.shares * h.current_price for h in request.holdings)
    if total_value <= 0:
        raise HTTPException(status_code=400, detail="Portfolio has no value")

    weights = {
        h.ticker: (h.shares * h.current_price) / total_value
        for h in request.holdings
    }

    try:
        result = await asyncio.to_thread(
            decompose_portfolio, weights, request.lookback_days
        )
        if result is None:
            raise HTTPException(
                status_code=404,
                detail="Insufficient data for factor decomposition",
            )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("portfolio factor exposure failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


class CopulaRiskRequest(BaseModel):
    holdings: list[Holding] = Field(..., min_length=2, max_length=50)
    lookback_days: int = Field(504, ge=126, le=1260)


@router.post("/copula-risk")
async def portfolio_copula_risk(request: CopulaRiskRequest):
    """Copula-based tail risk analysis for a portfolio.

    Measures joint crash risk using Clayton/Gumbel/Frank/Student-t copulas.
    Returns tail dependence coefficients and copula-based VaR/CVaR.
    """
    from backend.services.copula_tail import compute_copula_risk_from_returns
    import numpy as np
    import yfinance as yf

    tickers = [h.ticker for h in request.holdings]
    total_value = sum(h.shares * h.current_price for h in request.holdings)
    if total_value <= 0:
        raise HTTPException(status_code=400, detail="Portfolio has no value")

    weights_arr = np.array([
        (h.shares * h.current_price) / total_value for h in request.holdings
    ])

    try:
        import pandas as pd
        # Fetch aligned price data for all tickers
        data = yf.download(tickers, period=f"{max(request.lookback_days // 252, 2)}y", progress=False)
        prices = data["Close"] if "Close" in data.columns or len(tickers) > 1 else pd.DataFrame(data["Close"])
        if prices.empty or len(prices) < 60:
            raise HTTPException(
                status_code=404,
                detail="Insufficient price data for copula analysis",
            )

        returns = prices.pct_change().dropna()

        result = await asyncio.to_thread(
            compute_copula_risk_from_returns, returns, weights_arr
        )
        if result is None:
            raise HTTPException(
                status_code=404,
                detail="Copula fitting failed — need at least 2 assets with sufficient history",
            )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("portfolio copula risk failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


class BenchmarkRequest(BaseModel):
    holdings: list[Holding] = Field(..., min_length=1, max_length=50)
    benchmark: str = Field("SPY", min_length=1, max_length=10)
    lookback_days: int = Field(504, ge=63, le=1260)


@router.post("/benchmark")
async def portfolio_benchmark_analytics(request: BenchmarkRequest):
    """Bloomberg PORT-style benchmark-relative analytics.

    Tracking error, information ratio, active share (Cremers & Petajisto),
    up/down capture ratios, rolling tracking error, regression stats,
    and period return comparison vs benchmark.
    """
    from backend.services.benchmark_analytics import compute_benchmark_analytics

    total_value = sum(h.shares * h.current_price for h in request.holdings)
    if total_value <= 0:
        raise HTTPException(status_code=400, detail="Portfolio has no value")

    weights = {
        h.ticker: (h.shares * h.current_price) / total_value
        for h in request.holdings
    }

    try:
        result = await asyncio.to_thread(
            compute_benchmark_analytics,
            weights,
            request.benchmark.upper(),
            request.lookback_days,
        )
        if result is None:
            raise HTTPException(
                status_code=404,
                detail="Insufficient data for benchmark analytics",
            )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("benchmark analytics failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


class CompareRequest(BaseModel):
    tickers: list[str] = Field(..., min_length=2, max_length=50)
    lookback_days: int = Field(504, ge=126, le=1260)


@router.post("/compare")
async def compare_portfolios(request: CompareRequest):
    """Compare all optimization methods side-by-side (Bloomberg PORT style)."""
    from backend.services.portfolio_optimizer import compare_methods

    tickers = [t.upper() for t in request.tickers]
    try:
        result = await asyncio.to_thread(compare_methods, tickers, request.lookback_days)
        return result
    except Exception as e:
        logger.error("portfolio comparison failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


class MPCRequest(BaseModel):
    tickers: list[str] = Field(..., min_length=2, max_length=30)
    current_weights: dict[str, float] | None = None
    benchmark_weights: dict[str, float] | None = None
    sector_map: dict[str, str] | None = None
    sector_caps: dict[str, float] | None = None
    gamma: float = Field(3.0, gt=0, le=100)
    transaction_cost_bps: float = Field(5.0, ge=0, le=500)
    holding_penalty: float = Field(0.0, ge=0, le=10)
    max_weight: float = Field(0.35, gt=0, le=1.0)
    min_weight: float = Field(0.0, ge=-0.5, le=0.5)
    tracking_error_limit: float | None = Field(None, ge=0.001, le=1.0)
    allow_shorts: bool = False
    horizon: int = Field(1, ge=1, le=12)
    return_decay: float = Field(0.0, ge=0, le=0.95)
    lookback_days: int = Field(504, ge=126, le=1260)

    @field_validator("tickers")
    @classmethod
    def upper_tickers(cls, v: list[str]) -> list[str]:
        out = [t.upper() for t in v]
        for t in out:
            if not _TICKER_RE.match(t):
                raise ValueError(f"Invalid ticker: {t}")
        return out


@router.post("/optimize-mpc")
async def optimize_mpc(request: MPCRequest):
    """Convex single-/multi-period portfolio optimizer.

    Solves mean-variance with explicit transaction costs, tracking error
    constraint, sector caps, and optional short-sale permission. When
    horizon > 1, re-solves each step (rolling MPC) with optional
    alpha-decay across steps.
    """
    import yfinance as yf
    import pandas as pd
    import numpy as np
    from backend.services.mpc_optimizer import (
        optimize_single_period,
        optimize_multi_period,
    )

    tickers = request.tickers
    try:
        # Fetch price history once, compute returns + Sigma + mu
        period_days = request.lookback_days
        start = (pd.Timestamp.today() - pd.Timedelta(days=int(period_days * 1.6))).strftime(
            "%Y-%m-%d"
        )
        end = pd.Timestamp.today().strftime("%Y-%m-%d")
        frame = await asyncio.to_thread(
            yf.download, tickers, start=start, end=end, progress=False, group_by="ticker"
        )
        if frame is None or frame.empty:
            raise HTTPException(status_code=422, detail="Could not fetch price data")

        closes: dict[str, pd.Series] = {}
        if len(tickers) == 1:
            # Single-ticker shape is different
            if "Close" in frame.columns:
                closes[tickers[0]] = frame["Close"].dropna()
        else:
            for t in tickers:
                try:
                    if t in frame.columns.get_level_values(0):
                        closes[t] = frame[t]["Close"].dropna()
                except Exception:
                    continue

        available = [t for t in tickers if t in closes and len(closes[t]) > 30]
        if len(available) < 2:
            raise HTTPException(
                status_code=422,
                detail="Need ≥2 tickers with sufficient history",
            )

        price_df = pd.DataFrame({t: closes[t] for t in available}).dropna()
        if len(price_df) < 30:
            raise HTTPException(status_code=422, detail="Not enough overlapping history")

        rets = price_df.pct_change().dropna()
        mu = rets.mean() * 252  # annualised
        sigma = rets.cov() * 252

        # Restrict weight dictionaries to available tickers
        cw = {k: v for k, v in (request.current_weights or {}).items() if k in available}
        bw = {k: v for k, v in (request.benchmark_weights or {}).items() if k in available}
        sm = {k: v for k, v in (request.sector_map or {}).items() if k in available}

        kwargs = dict(
            gamma=request.gamma,
            transaction_cost_bps=request.transaction_cost_bps,
            holding_penalty=request.holding_penalty,
            max_weight=request.max_weight,
            min_weight=request.min_weight,
            tracking_error_limit=request.tracking_error_limit,
            benchmark_weights=bw if bw else None,
            sector_map=sm if sm else None,
            sector_caps=request.sector_caps,
            allow_shorts=request.allow_shorts,
        )

        if request.horizon == 1:
            result = await asyncio.to_thread(
                optimize_single_period,
                expected_returns=mu,
                cov_matrix=sigma,
                current_weights=cw if cw else None,
                **kwargs,
            )
        else:
            result = await asyncio.to_thread(
                optimize_multi_period,
                expected_returns=mu,
                cov_matrix=sigma,
                current_weights=cw if cw else None,
                horizon=request.horizon,
                return_decay=request.return_decay,
                **kwargs,
            )

        result["tickers"] = available
        result["lookback_days"] = request.lookback_days
        result["mu_annualised"] = {t: float(mu[t]) for t in available}
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("optimize-mpc failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


class TearsheetRequest(BaseModel):
    holdings: list[Holding] = Field(..., min_length=1, max_length=50)
    title: str = Field("Portfolio Tearsheet", max_length=80)


@router.post("/tearsheet.html", response_class=HTMLResponse)
async def portfolio_tearsheet_html(request: TearsheetRequest):
    """Return a self-contained HTML tearsheet (print-to-PDF from the browser)."""
    try:
        holdings = [h.model_dump() for h in request.holdings]
        from backend.routers.portfolio import _analyze_with_risk_number
        from backend.services.tearsheet import render_portfolio_tearsheet_html

        analysis = await asyncio.to_thread(_analyze_with_risk_number, holdings)
        html_doc = render_portfolio_tearsheet_html(analysis, title=request.title)
        return HTMLResponse(content=html_doc)
    except Exception as e:
        logger.error("tearsheet HTML failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tearsheet.xlsx")
async def portfolio_tearsheet_xlsx(request: TearsheetRequest):
    """Return a multi-sheet .xlsx workbook with tearsheet data."""
    try:
        holdings = [h.model_dump() for h in request.holdings]
        from backend.routers.portfolio import _analyze_with_risk_number
        from backend.services.tearsheet import render_portfolio_tearsheet_xlsx

        analysis = await asyncio.to_thread(_analyze_with_risk_number, holdings)
        blob = await asyncio.to_thread(render_portfolio_tearsheet_xlsx, analysis)
        filename = f"aegis-tearsheet-{request.title.replace(' ', '_')[:40]}.xlsx"
        return Response(
            content=blob,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("tearsheet xlsx failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
