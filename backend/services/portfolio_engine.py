"""
Aegis Finance — Stateless Portfolio Analytics
================================================

Computes portfolio metrics from a list of holdings.
No server-side state — portfolio lives in browser localStorage.

Optimization methods:
    - Template: Goal-based hardcoded allocations (default, fast)
    - Black-Litterman: Bayesian optimization with market-implied priors (Phase 3.1)
    - HRP: Hierarchical Risk Parity — no covariance inversion needed (Phase 3.2)

All covariance computations use Ledoit-Wolf shrinkage (Phase 3.3).

Usage:
    from backend.services.portfolio_engine import PortfolioEngine
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

from backend.config import config
from backend.models.garch import fit_garch, get_standardized_residuals
from backend.services.monte_carlo import _generate_block_bootstrap_residuals
from backend.services.tail_risk import compute_tail_risk_metrics

logger = logging.getLogger(__name__)

# Goal-based allocation templates.
# 2026-07-11 revision (direction-checked in the allocation backtester, 3y AND
# 2015→ windows): ARKK removed from aggressive (its negative expectation is
# our own pre-registered TRIAL-ARK-IC prior), a momentum-factor sleeve (MTUM)
# added — the strongest documented cross-sectional premium and the direction
# T6 adopted — and international trimmed. Caveat that ships with the tilts:
# they lean on US growth/momentum leadership continuing; in a value/intl
# rotation they lag. Backtests are direction-checks, not alpha proof (T7).
_ALLOCATION_TEMPLATES = {
    "conservative": {
        "description": "Capital preservation, low volatility",
        "allocations": {
            "BND": 0.40, "VTIP": 0.10, "VTI": 0.25,
            "VXUS": 0.10, "GLD": 0.10, "VNQ": 0.05,
        },
    },
    "moderate": {
        "description": "Balanced growth and income",
        "allocations": {
            "VTI": 0.40, "VXUS": 0.15, "BND": 0.20,
            "VNQ": 0.10, "GLD": 0.05, "QQQ": 0.10,
        },
    },
    "aggressive": {
        "description": "Growth with a momentum tilt, higher volatility",
        "allocations": {
            "VTI": 0.35, "QQQ": 0.25, "MTUM": 0.15,
            "VGT": 0.10, "VXUS": 0.10, "GLD": 0.05,
        },
    },
    "max_growth": {
        "description": ("Highest expected return: 100% equity, growth + "
                        "momentum tilted, no ballast — expect the deepest "
                        "drawdowns and regime dependence"),
        "allocations": {
            "VTI": 0.30, "QQQ": 0.35, "MTUM": 0.20, "VGT": 0.15,
        },
    },
}

# Goal-based allocation adjustments applied on top of risk tolerance templates.
# Each goal shifts weights toward asset classes aligned with the goal's objective.
_GOAL_ADJUSTMENTS = {
    "preservation": {
        # Maximize capital stability — overweight bonds, underweight equities
        "bond_boost": 0.15,   # shift 15% from equities to bonds
        "dividend_tickers": [],
    },
    "income": {
        # Maximize dividend yield — overweight dividend/REIT ETFs
        "bond_boost": 0.05,
        "dividend_tickers": ["VNQ", "XLV"],  # boost these by 5% each
    },
    "growth": {
        # Balanced growth — no adjustment (default behavior)
        "bond_boost": 0.0,
        "dividend_tickers": [],
    },
    "aggressive_growth": {
        # Maximum equity exposure — underweight bonds, overweight tech
        "bond_boost": -0.10,  # shift 10% from bonds to equities
        "dividend_tickers": [],
    },
    "retirement": {
        # Glide path — bond allocation increases with shorter horizon
        # Bond boost is per-horizon: 1y=+20%, 3y=+15%, 5y=+10%, 10y=+5%
        "bond_boost": 0.10,   # default (5y), overridden by horizon
        "dividend_tickers": ["VNQ"],
    },
}

# Risk aversion mapping for Black-Litterman
_RISK_AVERSION = {
    "conservative": 5.0,
    "moderate": 2.5,
    "aggressive": 1.0,
    "max_growth": 0.7,
}

# Default ETF universe for BL/HRP
_ETF_UNIVERSE = ["VTI", "VXUS", "BND", "QQQ", "VGT", "VNQ", "GLD", "VTIP", "XLE", "XLV"]

# Approximate AUM-based market cap proxies (billions, as of 2026-03)
# Used for BL equilibrium return estimation — order-of-magnitude matters more than precision
_ETF_MARKET_CAPS = {
    "VTI": 400, "VXUS": 75, "BND": 120, "QQQ": 280, "VGT": 80,
    "VNQ": 35, "GLD": 70, "VTIP": 25, "XLE": 40, "XLV": 45,
}


def _apply_goal_adjustment(
    allocations: dict[str, float],
    goal: str,
    time_horizon: str,
) -> dict[str, float]:
    """Apply goal-based shifts to allocation weights.

    Adjusts bond/equity balance and boosts specific tickers based on
    the investor's goal (preservation, income, growth, aggressive_growth, retirement).
    """
    adj = _GOAL_ADJUSTMENTS.get(goal, _GOAL_ADJUSTMENTS["growth"])
    bond_boost = adj["bond_boost"]

    # Retirement glide path: more bonds for shorter horizons
    if goal == "retirement":
        glide = {"1y": 0.20, "3y": 0.15, "5y": 0.10, "10y": 0.05}
        bond_boost = glide.get(time_horizon, 0.10)

    bond_tickers = [t for t in allocations if t in ("BND", "VTIP")]
    equity_tickers = [t for t in allocations if t not in ("BND", "VTIP", "GLD")]

    if bond_boost != 0.0 and bond_tickers and equity_tickers:
        shift_per_equity = bond_boost / len(equity_tickers)
        shift_per_bond = bond_boost / len(bond_tickers)
        for t in equity_tickers:
            allocations[t] = max(0.02, allocations[t] - shift_per_equity)
        for t in bond_tickers:
            allocations[t] = max(0.02, allocations[t] + shift_per_bond)

    # Boost dividend/income tickers for income-oriented goals
    for t in adj.get("dividend_tickers", []):
        if t in allocations:
            allocations[t] = allocations[t] + 0.05

    # Re-normalize
    total = sum(allocations.values())
    if total > 0:
        allocations = {k: v / total for k, v in allocations.items()}

    return allocations


# ══════════════════════════════════════════════════════════════════════════════
# COVARIANCE SHRINKAGE (Phase 3.3)
# ══════════════════════════════════════════════════════════════════════════════


def _shrunk_covariance(
    data: pd.DataFrame,
    returns_data: bool = False,
    use_denoised: bool = True,
) -> pd.DataFrame:
    """Compute covariance matrix using the best available method.

    Priority:
    1. Marchenko-Pastur RMT denoising (covariance.py) — best for portfolio optimization
    2. Ledoit-Wolf shrinkage (pypfopt) — good fallback
    3. Sample covariance (annualized) — last resort

    Denoised covariance removes noise eigenvalues from the correlation matrix
    using Random Matrix Theory, producing more stable portfolio weights than
    even Ledoit-Wolf for typical T/N ratios (252 days / 10-50 assets).

    Args:
        data: Price DataFrame (default) or returns DataFrame.
        returns_data: If True, data contains returns instead of prices.
        use_denoised: If True, try RMT denoising first.

    Falls back to Ledoit-Wolf, then sample covariance.
    """
    returns = data if returns_data else data.pct_change().dropna()

    # Try denoised covariance (Marchenko-Pastur RMT)
    if use_denoised and len(returns) > 60 and len(returns.columns) >= 3:
        try:
            from backend.services.covariance import denoise_covariance
            cov = denoise_covariance(returns, detone=False)
            # Annualize
            cov = cov * 252
            logger.debug("Using denoised (RMT) covariance matrix")
            return cov
        except Exception as e:
            logger.debug("Denoised covariance failed, falling back: %s", e)

    # Ledoit-Wolf shrinkage
    try:
        from pypfopt import risk_models
        cov = risk_models.CovarianceShrinkage(
            data, returns_data=returns_data
        ).ledoit_wolf()
        return cov
    except ImportError:
        logger.warning("pypfopt not available, using sample covariance")
        return returns.cov() * 252


def _fetch_prices(tickers: list[str], period: str = "2y") -> Optional[pd.DataFrame]:
    """Fetch historical prices for a list of tickers."""
    try:
        price_data = yf.download(tickers, period=period, progress=False)["Close"]
        if isinstance(price_data, pd.Series):
            price_data = price_data.to_frame(name=tickers[0])
        return price_data
    except Exception as e:
        logger.warning("Failed to fetch price data: %s", e)
        return None


# ══════════════════════════════════════════════════════════════════════════════
# RISK PROFILE SCORING
# ══════════════════════════════════════════════════════════════════════════════


def score_risk_profile(answers: dict) -> dict:
    """Convert questionnaire answers into a risk score and allocation style.

    Args:
        answers: Dict with keys: horizon, risk_tolerance, loss_reaction,
                 experience, income_stability, goal

    Returns:
        Dict with risk_score (1-10), allocation_style, description
    """
    score = 5  # baseline

    # Time horizon: longer = more aggressive
    horizon_scores = {"1y": -2, "3y": -1, "5y": 0, "10y": 1, "20y": 2}
    score += horizon_scores.get(answers.get("horizon", "5y"), 0)

    # Risk tolerance
    risk_scores = {"conservative": -2, "moderate": 0, "aggressive": 2}
    score += risk_scores.get(answers.get("risk_tolerance", "moderate"), 0)

    # Loss reaction: how they react to a -20% drop
    loss_scores = {"sell": -2, "hold": 0, "buy_more": 2}
    score += loss_scores.get(answers.get("loss_reaction", "hold"), 0)

    # Investment experience
    exp_scores = {"none": -1, "beginner": 0, "intermediate": 1, "advanced": 1}
    score += exp_scores.get(answers.get("experience", "beginner"), 0)

    # Income stability
    income_scores = {"unstable": -1, "stable": 0, "very_stable": 1}
    score += income_scores.get(answers.get("income_stability", "stable"), 0)

    # Goal
    goal_scores = {"preservation": -2, "income": -1, "growth": 1, "aggressive_growth": 2}
    score += goal_scores.get(answers.get("goal", "growth"), 0)

    # Clamp to 1-10
    score = max(1, min(10, score))

    # Map score to allocation style
    if score <= 3:
        style = "conservative"
        desc = "Capital preservation focus — heavy bonds and gold, limited equity exposure"
    elif score <= 6:
        style = "moderate"
        desc = "Balanced growth — diversified mix of equity and fixed income"
    else:
        style = "aggressive"
        desc = "Growth-oriented — mostly equities with sector tilts for maximum upside"

    return {
        "risk_score": score,
        "allocation_style": style,
        "description": desc,
        "factors": {
            "horizon": answers.get("horizon", "5y"),
            "risk_tolerance": answers.get("risk_tolerance", "moderate"),
            "loss_reaction": answers.get("loss_reaction", "hold"),
            "experience": answers.get("experience", "beginner"),
            "income_stability": answers.get("income_stability", "stable"),
            "goal": answers.get("goal", "growth"),
        },
    }


# ══════════════════════════════════════════════════════════════════════════════
# PORTFOLIO ENGINE
# ══════════════════════════════════════════════════════════════════════════════


class PortfolioEngine:
    """Stateless portfolio analytics."""

    @staticmethod
    def analyze_portfolio(holdings: list[dict]) -> dict:
        """Analyze a portfolio of holdings.

        Uses Ledoit-Wolf shrunk covariance for correlation and risk metrics.

        Args:
            holdings: List of {"ticker": str, "shares": float, "current_price": float}

        Returns:
            Dict with allocation, correlations, VaR, CVaR, expected metrics
        """
        if not holdings:
            return {"error": "No holdings provided"}

        tickers = [h["ticker"] for h in holdings]
        values = [h["shares"] * h["current_price"] for h in holdings]
        total_value = sum(values)

        if total_value <= 0:
            return {"error": "Portfolio value is zero"}

        weights = [v / total_value for v in values]

        # Fetch historical returns
        price_data = _fetch_prices(tickers)
        if price_data is None:
            return {
                "total_value": total_value,
                "allocations": [
                    {"ticker": h["ticker"], "weight": w * 100, "value": v}
                    for h, w, v in zip(holdings, weights, values)
                ],
                "error": "Could not fetch historical data",
            }

        returns = price_data.pct_change().dropna()

        # Portfolio returns
        available = [t for t in tickers if t in returns.columns]
        if not available:
            return {"total_value": total_value, "error": "No price data available"}

        ret_matrix = returns[available].values
        w_available = np.array([weights[tickers.index(t)] for t in available])
        w_available = w_available / w_available.sum()

        port_returns = ret_matrix @ w_available
        port_annual_return = float(np.mean(port_returns) * 252) * 100
        port_annual_vol = float(np.std(port_returns) * np.sqrt(252)) * 100

        # VaR and CVaR (95% confidence)
        var_95 = float(np.percentile(port_returns, 5)) * 100
        tail = port_returns[port_returns <= np.percentile(port_returns, 5)]
        cvar_95 = float(np.mean(tail)) * 100 if len(tail) > 0 else var_95

        # Correlation matrix — use Ledoit-Wolf shrunk covariance
        try:
            shrunk_cov = _shrunk_covariance(returns[available], returns_data=True)
            # Convert to correlation matrix
            std_devs = np.sqrt(np.diag(shrunk_cov.values))
            std_outer = np.outer(std_devs, std_devs)
            corr_matrix = shrunk_cov.values / np.where(std_outer > 0, std_outer, 1.0)
            np.fill_diagonal(corr_matrix, 1.0)
            corr_data = {
                "tickers": available,
                "matrix": corr_matrix.tolist(),
            }
        except (ImportError, ValueError, np.linalg.LinAlgError) as e:
            logger.debug("Shrunk covariance failed, using sample: %s", e)
            corr = returns[available].corr()
            corr_data = {
                "tickers": available,
                "matrix": corr.values.tolist(),
            }

        # Max drawdown
        cum_returns = (1 + pd.Series(port_returns)).cumprod()
        peak = cum_returns.cummax()
        drawdown = (cum_returns - peak) / peak
        max_dd = float(drawdown.min()) * 100

        # Sharpe ratio
        rf_daily = config.get("risk_free_rate", 0.04) / 252
        sharpe = float((np.mean(port_returns) - rf_daily) / np.std(port_returns) * np.sqrt(252))

        # Tail risk analytics (Sortino, Omega, Calmar, etc.)
        tail_metrics = compute_tail_risk_metrics(port_returns)

        # Copula-based tail risk (captures joint crash dependence)
        copula_risk = None
        if len(available) >= 2:
            try:
                from backend.services.copula_tail import compute_copula_risk_from_returns
                copula_risk = compute_copula_risk_from_returns(
                    returns[available], w_available
                )
            except Exception as e:
                logger.debug("Copula risk computation skipped: %s", e)

        # Brinson-Fachler performance attribution vs SPY (auto-compute)
        attribution = None
        risk_contributions = None
        try:
            from backend.services.attribution import (
                brinson_fachler_attribution, _build_sector_map,
            )
            # Fetch benchmark (SPY) returns over same period
            benchmark_ticker = "SPY"
            if benchmark_ticker in returns.columns:
                bench_returns_series = returns[benchmark_ticker]
            else:
                try:
                    bench_prices = yf.download(
                        benchmark_ticker, period="2y", progress=False, auto_adjust=True
                    )
                    if not bench_prices.empty:
                        if isinstance(bench_prices.columns, pd.MultiIndex):
                            bench_close = bench_prices["Close"]
                        else:
                            bench_close = bench_prices
                        bench_returns_series = bench_close.pct_change().dropna().iloc[:, 0] if isinstance(bench_close, pd.DataFrame) else bench_close.pct_change().dropna()
                    else:
                        bench_returns_series = None
                except Exception:
                    bench_returns_series = None

            if bench_returns_series is not None and len(bench_returns_series) > 21:
                # 1-month period returns for attribution
                sector_map = _build_sector_map()
                port_weights_dict = {t: w_available[i] for i, t in enumerate(available)}
                bench_weights_dict = {benchmark_ticker: 1.0}

                # Compute 1-month returns for each holding and benchmark
                port_1m_returns = {}
                for t in available:
                    r = returns[t].iloc[-21:]
                    port_1m_returns[t] = float((1 + r).prod() - 1) if len(r) >= 21 else 0.0

                bench_1m = float((1 + bench_returns_series.iloc[-21:]).prod() - 1) if len(bench_returns_series) >= 21 else 0.0
                bench_returns_dict = {benchmark_ticker: bench_1m}

                attribution = brinson_fachler_attribution(
                    portfolio_weights=port_weights_dict,
                    benchmark_weights=bench_weights_dict,
                    portfolio_returns=port_1m_returns,
                    benchmark_returns=bench_returns_dict,
                    sector_map=sector_map,
                )

            # MCTR (Marginal Contribution to Risk) from already-fetched data
            cov_annual = returns[available].cov().values * 252
            w_arr = np.array(w_available)
            port_var = w_arr @ cov_annual @ w_arr
            port_vol = np.sqrt(port_var) if port_var > 0 else 1e-10
            sigma_w = cov_annual @ w_arr
            mctr = w_arr * sigma_w / port_vol
            total_mctr = mctr.sum()
            pct_contrib = mctr / total_mctr if total_mctr > 0 else mctr

            risk_contributions = {}
            for i, t in enumerate(available):
                risk_contributions[t] = {
                    "weight_pct": round(float(w_arr[i]) * 100, 2),
                    "mctr": round(float(mctr[i]) * 100, 3),
                    "risk_contribution_pct": round(float(pct_contrib[i]) * 100, 2),
                    "risk_weight_ratio": round(float(pct_contrib[i]) / max(w_arr[i], 1e-10), 2),
                }
        except Exception as e:
            logger.debug("Attribution/MCTR computation skipped: %s", e)

        result = {
            "total_value": total_value,
            "annual_return": port_annual_return,
            "annual_volatility": port_annual_vol,
            "sharpe_ratio": sharpe,
            "var_95_daily": var_95,
            "cvar_95_daily": cvar_95,
            "max_drawdown": max_dd,
            "tail_risk": tail_metrics,
            "allocations": [
                {"ticker": h["ticker"], "weight": w * 100, "value": v}
                for h, w, v in zip(holdings, weights, values)
            ],
            "correlation": corr_data,
        }
        if copula_risk is not None:
            result["copula_risk"] = copula_risk
        if attribution is not None:
            result["attribution"] = attribution
        if risk_contributions is not None:
            result["risk_contributions"] = {
                "portfolio_volatility_annual": round(float(port_vol) * 100, 2) if port_vol else None,
                "contributions": risk_contributions,
            }
        return result

    @staticmethod
    def build_portfolio(
        risk_tolerance: str = "moderate",
        investment_amount: float = 10000,
        time_horizon: str = "5y",
        method: str = "template",
        views: Optional[dict] = None,
        goal: str = "growth",
    ) -> dict:
        """Build a portfolio allocation.

        Args:
            risk_tolerance: "conservative", "moderate", or "aggressive"
            investment_amount: Dollar amount to invest
            time_horizon: "1y", "3y", "5y", "10y"
            method: "template" (default), "black-litterman", or "hrp"
            views: Optional dict of {ticker: expected_return} for BL
            goal: "preservation", "income", "growth", "aggressive_growth", or "retirement"

        Returns:
            Dict with target allocations and rationale
        """
        if method == "black-litterman":
            result = PortfolioEngine._build_bl(
                risk_tolerance, investment_amount, time_horizon, views
            )
        elif method == "hrp":
            result = PortfolioEngine._build_hrp(
                risk_tolerance, investment_amount, time_horizon
            )
        else:
            result = PortfolioEngine._build_template(
                risk_tolerance, investment_amount, time_horizon
            )

        # Apply goal-based adjustment if goal is not default
        if goal != "growth" and "holdings" in result:
            raw_alloc = {h["ticker"]: h["weight"] / 100 for h in result["holdings"]}
            adjusted = _apply_goal_adjustment(raw_alloc, goal, time_horizon)
            result = PortfolioEngine._allocations_to_response(
                adjusted, risk_tolerance, investment_amount, time_horizon,
                result.get("description", "") + f" | Goal: {goal}",
                result.get("method", method),
            )
            result["goal"] = goal

        if "goal" not in result:
            result["goal"] = goal

        return result

    @staticmethod
    def _build_template(
        risk_tolerance: str,
        investment_amount: float,
        time_horizon: str,
    ) -> dict:
        """Build portfolio from hardcoded goal-based templates."""
        template = _ALLOCATION_TEMPLATES.get(risk_tolerance, _ALLOCATION_TEMPLATES["moderate"])

        # Adjust for time horizon
        allocations = dict(template["allocations"])
        if time_horizon in ("1y", "3y"):
            bond_boost = 0.10 if time_horizon == "1y" else 0.05
            equity_tickers = [t for t in allocations if t not in ("BND", "VTIP", "GLD")]
            bond_tickers = [t for t in allocations if t in ("BND", "VTIP")]

            if equity_tickers and bond_tickers:
                reduce_each = bond_boost / len(equity_tickers)
                add_each = bond_boost / len(bond_tickers)
                for t in equity_tickers:
                    allocations[t] = max(0.02, allocations[t] - reduce_each)
                for t in bond_tickers:
                    allocations[t] = allocations[t] + add_each

        # Normalize weights
        total = sum(allocations.values())
        allocations = {k: v / total for k, v in allocations.items()}

        return PortfolioEngine._allocations_to_response(
            allocations, risk_tolerance, investment_amount, time_horizon,
            template["description"], "template",
        )

    @staticmethod
    def _build_bl(
        risk_tolerance: str,
        investment_amount: float,
        time_horizon: str,
        views: Optional[dict] = None,
    ) -> dict:
        """Build portfolio using Black-Litterman optimization.

        Uses market-implied prior returns from equilibrium, optionally
        blended with user views, then optimizes for max Sharpe.
        """
        try:
            from pypfopt import BlackLittermanModel, risk_models, expected_returns  # noqa: F401 — availability probe
            from pypfopt.efficient_frontier import EfficientFrontier
        except ImportError:
            logger.warning("pypfopt not available, falling back to template")
            return PortfolioEngine._build_template(risk_tolerance, investment_amount, time_horizon)

        tickers = list(_ETF_UNIVERSE)
        price_data = _fetch_prices(tickers, period="5y")
        if price_data is None:
            return PortfolioEngine._build_template(risk_tolerance, investment_amount, time_horizon)

        # Filter to available tickers
        available = [t for t in tickers if t in price_data.columns]
        if len(available) < 3:
            return PortfolioEngine._build_template(risk_tolerance, investment_amount, time_horizon)

        prices = price_data[available].ffill().dropna()

        # Ledoit-Wolf shrunk covariance (pass prices — pypfopt computes returns internally)
        cov = _shrunk_covariance(prices)

        # Market-cap weights from AUM proxies
        market_caps = {t: _ETF_MARKET_CAPS.get(t, 30.0) for t in available}
        cap_total = sum(market_caps.values())
        market_weights = {t: v / cap_total for t, v in market_caps.items()}

        # Risk aversion parameter
        delta = _RISK_AVERSION.get(risk_tolerance, 2.5)

        try:
            # Compute equilibrium returns (market-implied prior)
            from pypfopt.black_litterman import market_implied_prior_returns
            rf = config.get("risk_free_rate", 0.04)
            pi = market_implied_prior_returns(market_caps, delta, cov, risk_free_rate=rf)

            # Build BL model — only use BL posterior if views are provided
            if views and any(t in available for t in views):
                abs_views = {t: v for t, v in views.items() if t in available}
                bl = BlackLittermanModel(cov, pi=pi, absolute_views=abs_views)
                posterior_returns = bl.bl_returns()
            else:
                # No views: posterior = prior (equilibrium returns)
                posterior_returns = pi

            # Optimize with weight bounds to prevent extreme concentration
            n_assets = len(available)
            max_weight = min(0.40, 1.0 / max(n_assets * 0.3, 1))
            rf = config.get("risk_free_rate", 0.04)
            ef = EfficientFrontier(posterior_returns, cov, weight_bounds=(0.0, max_weight))
            try:
                ef.max_sharpe(risk_free_rate=rf)
            except ValueError:
                # max_sharpe fails when no asset exceeds risk-free rate;
                # fall back to max quadratic utility which always works
                ef = EfficientFrontier(posterior_returns, cov, weight_bounds=(0.0, max_weight))
                ef.max_quadratic_utility(risk_aversion=delta)
            weights = ef.clean_weights()

            # Filter zero-weight assets
            allocations = {t: w for t, w in weights.items() if w > 0.01}

            if not allocations:
                allocations = dict(market_weights)

            # Normalize
            total = sum(allocations.values())
            allocations = {k: v / total for k, v in allocations.items()}

            # Blend with template to enforce risk tolerance.
            # BL max_sharpe ignores risk profile, so we blend:
            #   conservative: 70% template + 30% BL
            #   moderate:     50% template + 50% BL
            #   aggressive:   30% template + 70% BL
            blend_ratios = {"conservative": 0.30, "moderate": 0.40,
                            "aggressive": 0.65, "max_growth": 0.75}
            bl_weight = blend_ratios.get(risk_tolerance, 0.50)
            template_alloc = dict(_ALLOCATION_TEMPLATES.get(
                risk_tolerance, _ALLOCATION_TEMPLATES["moderate"]
            )["allocations"])

            all_tickers = set(list(allocations.keys()) + list(template_alloc.keys()))
            blended = {}
            for t in all_tickers:
                bl_w = allocations.get(t, 0.0) * bl_weight
                tmpl_w = template_alloc.get(t, 0.0) * (1 - bl_weight)
                blended[t] = bl_w + tmpl_w

            allocations = {t: w for t, w in blended.items() if w > 0.01}
            total = sum(allocations.values())
            allocations = {k: v / total for k, v in allocations.items()}

            # Get portfolio performance
            try:
                perf = ef.portfolio_performance(risk_free_rate=rf)
                description = (
                    f"Black-Litterman optimized ({risk_tolerance}). "
                    f"Expected return: {perf[0]*100:.1f}%, "
                    f"Volatility: {perf[1]*100:.1f}%, "
                    f"Sharpe: {perf[2]:.2f}"
                )
            except (ValueError, AttributeError) as e:
                logger.debug("BL portfolio_performance failed: %s", e)
                description = f"Black-Litterman optimized ({risk_tolerance})"

        except (ImportError, ValueError, np.linalg.LinAlgError, KeyError) as e:
            logger.warning("BL optimization failed: %s, falling back to template", e)
            return PortfolioEngine._build_template(risk_tolerance, investment_amount, time_horizon)

        return PortfolioEngine._allocations_to_response(
            allocations, risk_tolerance, investment_amount, time_horizon,
            description, "black-litterman",
        )

    @staticmethod
    def _build_hrp(
        risk_tolerance: str,
        investment_amount: float,
        time_horizon: str,
    ) -> dict:
        """Build portfolio using Hierarchical Risk Parity.

        HRP uses hierarchical clustering to build a diversified portfolio
        without requiring covariance matrix inversion. More stable than
        mean-variance optimization, especially with noisy data.
        """
        try:
            from pypfopt import HRPOpt
        except ImportError:
            logger.warning("pypfopt not available, falling back to template")
            return PortfolioEngine._build_template(risk_tolerance, investment_amount, time_horizon)

        tickers = list(_ETF_UNIVERSE)
        price_data = _fetch_prices(tickers, period="5y")
        if price_data is None:
            return PortfolioEngine._build_template(risk_tolerance, investment_amount, time_horizon)

        available = [t for t in tickers if t in price_data.columns]
        if len(available) < 3:
            return PortfolioEngine._build_template(risk_tolerance, investment_amount, time_horizon)

        returns = price_data[available].ffill().dropna().pct_change().dropna()

        try:
            hrp = HRPOpt(returns)
            weights = hrp.optimize()
            weights = dict(weights)

            # Blend with template to enforce risk tolerance.
            # HRP naturally over-weights low-vol assets (bonds), so blend
            # with template to get the right equity/bond mix.
            blend_ratios = {"conservative": 0.50, "moderate": 0.45,
                            "aggressive": 0.35, "max_growth": 0.25}
            hrp_weight = blend_ratios.get(risk_tolerance, 0.50)
            template_alloc = dict(_ALLOCATION_TEMPLATES.get(
                risk_tolerance, _ALLOCATION_TEMPLATES["moderate"]
            )["allocations"])

            all_tickers = set(list(weights.keys()) + list(template_alloc.keys()))
            blended = {}
            for t in all_tickers:
                h_w = weights.get(t, 0.0) * hrp_weight
                tmpl_w = template_alloc.get(t, 0.0) * (1 - hrp_weight)
                blended[t] = h_w + tmpl_w
            weights = blended

            # Cap any single position at 30% to ensure diversification
            max_weight = 0.30
            n_assets = len(weights)
            for _ in range(5):  # Iterate to redistribute excess
                excess = 0.0
                for t in weights:
                    if weights[t] > max_weight:
                        excess += weights[t] - max_weight
                        weights[t] = max_weight
                if excess < 0.001:
                    break
                # Redistribute excess proportionally to under-cap positions
                under_cap = {t: w for t, w in weights.items() if w < max_weight}
                if under_cap:
                    total_under = sum(under_cap.values())
                    for t in under_cap:
                        weights[t] += excess * (under_cap[t] / total_under)

            # Filter and normalize
            allocations = {t: w for t, w in weights.items() if w > 0.01}
            total = sum(allocations.values())
            allocations = {k: v / total for k, v in allocations.items()}

            # Get performance metrics
            try:
                perf = hrp.portfolio_performance()
                description = (
                    f"Hierarchical Risk Parity ({risk_tolerance}). "
                    f"Expected return: {perf[0]*100:.1f}%, "
                    f"Volatility: {perf[1]*100:.1f}%, "
                    f"Sharpe: {perf[2]:.2f}"
                )
            except (ValueError, AttributeError) as e:
                logger.debug("HRP portfolio_performance failed: %s", e)
                description = f"Hierarchical Risk Parity ({risk_tolerance})"

        except (ImportError, ValueError, np.linalg.LinAlgError, KeyError) as e:
            logger.warning("HRP optimization failed: %s, falling back to template", e)
            return PortfolioEngine._build_template(risk_tolerance, investment_amount, time_horizon)

        return PortfolioEngine._allocations_to_response(
            allocations, risk_tolerance, investment_amount, time_horizon,
            description, "hrp",
        )

    @staticmethod
    def _allocations_to_response(
        allocations: dict,
        risk_tolerance: str,
        investment_amount: float,
        time_horizon: str,
        description: str,
        method: str,
    ) -> dict:
        """Convert allocation weights to API response with share counts."""
        holdings = []
        for ticker, weight in allocations.items():
            dollar_amount = investment_amount * weight
            try:
                stock = yf.Ticker(ticker)
                price = stock.info.get("regularMarketPrice") or stock.info.get("previousClose", 100)
                shares = dollar_amount / price if price > 0 else 0
            except (KeyError, AttributeError, TypeError, ValueError) as e:
                logger.debug("Price fetch for %s failed, using $100 fallback: %s", ticker, e)
                price = 100
                shares = dollar_amount / price

            holdings.append({
                "ticker": ticker,
                "weight": weight * 100,
                "dollar_amount": dollar_amount,
                "shares": round(shares, 4),
                "price": price,
            })

        return {
            "risk_tolerance": risk_tolerance,
            "time_horizon": time_horizon,
            "investment_amount": investment_amount,
            "description": description,
            "method": method,
            "holdings": holdings,
        }

    @staticmethod
    def project_portfolio(
        holdings: list[dict],
        years: int = 1,
        monthly_add: float = 0,
    ) -> dict:
        """Project portfolio value forward using GARCH-enhanced jump-diffusion MC.

        Uses the same quality MC engine as SP500/stock simulations:
        - GARCH conditional volatility and tail thickness (nu)
        - GARCH-standardized residuals for block bootstrap
        - Log-space simulation (prevents negative prices)
        - Ito correction for correct expected returns
        - OU volatility dynamics

        Args:
            holdings: List of {"ticker": str, "shares": float, "current_price": float}
            years: Projection horizon in years
            monthly_add: Monthly additional investment (distributed by current weights)

        Returns:
            Dict with projected_values, expected_final, range
        """
        tickers = [h["ticker"] for h in holdings]
        values = [h["shares"] * h["current_price"] for h in holdings]
        total_value = sum(values)
        weights = [v / total_value for v in values] if total_value > 0 else [1 / len(values)] * len(values)

        price_data = _fetch_prices(tickers, period="5y")
        if price_data is None:
            return {"error": "Could not fetch price data for projection"}

        returns = price_data.pct_change().dropna()
        available = [t for t in tickers if t in returns.columns]
        if not available:
            return {"error": "No price data for projection"}

        w_arr = np.array([weights[tickers.index(t)] for t in available])
        w_arr = w_arr / w_arr.sum()

        port_returns_arr = returns[available].values @ w_arr
        port_returns_series = pd.Series(port_returns_arr, index=returns.index)

        mu_daily = float(np.mean(port_returns_arr))
        sigma_daily = float(np.std(port_returns_arr))
        sigma_annual = sigma_daily * np.sqrt(252)

        trading_days = years * 252

        # ── GARCH fit on portfolio returns ───────────────────────────
        garch_result = fit_garch(port_returns_series)
        if garch_result.success:
            garch_vol = garch_result.current_vol  # annualized
            garch_nu = garch_result.nu
            garch_persistence = (
                garch_result.alpha
                + garch_result.gamma * np.sqrt(2 / np.pi)
                + garch_result.beta
            )
            # GARCH-standardized residuals for block bootstrap
            std_residuals = get_standardized_residuals(garch_result, port_returns_series)
        else:
            garch_vol = sigma_annual
            garch_nu = 8.0
            garch_persistence = 0.97
            std_residuals = None

        # ── Simulation parameters ────────────────────────────────────
        sim_cfg = config["simulation"]
        dt = 1.0 / sim_cfg["trading_days_per_year"]
        jd = sim_cfg["jump_diffusion"]
        jump_rate = jd["annual_rate"]
        jump_mean = jd["mean"]
        jump_std = jd["std"]
        t_df = garch_nu if 2.5 < garch_nu < 30 else jd.get("t_degrees_of_freedom", 8)

        rng = np.random.default_rng(42)
        n_sims = sim_cfg["num_simulations"]

        # ── Drift with Ito correction ────────────────────────────────
        # Convert arithmetic daily mean to annualized arithmetic return
        annual_arith_return = mu_daily * 252
        # Ito correction: log drift = log(1+r) - 0.5*sigma^2
        base_drift = (np.log(1 + annual_arith_return) - 0.5 * garch_vol**2) * dt

        # Merton jump compensator (daily)
        daily_jump_prob = jump_rate * dt
        jump_k = np.exp(jump_mean + 0.5 * jump_std**2) - 1
        jump_compensator = daily_jump_prob * jump_k

        # ── OU volatility parameters ─────────────────────────────────
        kappa_vol = max(0.5, (1 - garch_persistence) * 252)
        long_run_vol = sigma_annual
        garch_params = sim_cfg.get("garch_derived_params", {})
        xi = np.clip(0.06, garch_params.get("xi_min", 0.02), garch_params.get("xi_max", 0.15))

        # ── Pre-generate random numbers ──────────────────────────────
        use_bootstrap = (
            sim_cfg.get("use_block_bootstrap", False)
            and std_residuals is not None
            and len(std_residuals) > sim_cfg.get("block_bootstrap_size", 21)
        )
        block_size = sim_cfg.get("block_bootstrap_size", 21)

        if use_bootstrap:
            Z_price = _generate_block_bootstrap_residuals(
                std_residuals, trading_days, n_sims, block_size, rng
            )
        else:
            Z_price = rng.standard_t(df=t_df, size=(trading_days, n_sims))
            if t_df > 2:
                Z_price /= np.sqrt(t_df / (t_df - 2))

        Z_vol_raw = rng.standard_normal(size=(trading_days, n_sims))
        Z_jump = rng.uniform(size=(trading_days, n_sims))
        Z_jump_size = rng.normal(jump_mean, jump_std, size=(trading_days, n_sims))

        # Leverage effect
        rho_leverage = -0.7
        Z_vol = rho_leverage * Z_price + np.sqrt(1 - rho_leverage**2) * Z_vol_raw

        # ── Run log-space simulation ─────────────────────────────────
        paths = np.zeros((trading_days + 1, n_sims))
        paths[0] = total_value
        sigma_t = np.full(n_sims, float(garch_vol))
        base_vol_sq = float(garch_vol) ** 2

        for t in range(trading_days):
            # OU volatility dynamics
            d_sigma = (
                kappa_vol * (long_run_vol - sigma_t) * dt
                + xi * sigma_t * np.sqrt(dt) * Z_vol[t]
            )
            sigma_t = np.clip(sigma_t + d_sigma, 0.04, 1.0)

            # Adaptive Ito correction for OU vol dynamics
            ito_adj = 0.5 * (base_vol_sq - sigma_t**2) * dt
            drift_daily = base_drift + ito_adj - jump_compensator

            # Diffusion
            diffusion = sigma_t * np.sqrt(dt) * Z_price[t]

            # Jump component
            jumps = np.where(Z_jump[t] < daily_jump_prob, Z_jump_size[t], 0.0)

            # Log-price step (prevents negative prices)
            log_return = drift_daily + diffusion + jumps
            paths[t + 1] = paths[t] * np.exp(log_return)

            # Add monthly contribution at end of each month (~21 trading days)
            if monthly_add > 0 and (t + 1) % 21 == 0:
                paths[t + 1] += monthly_add

        # Apply return cap
        max_return = sim_cfg.get("max_5y_return", 3.0)
        max_price = total_value * (1 + max_return)
        paths = np.clip(paths, 0.01, max_price)

        final = paths[-1]

        # Total invested = initial + all monthly contributions
        n_months = years * 12
        total_invested = total_value + monthly_add * n_months

        # Sample quarterly snapshots
        quarterly = []
        for q in range(1, years * 4 + 1):
            day_idx = min(q * 63, trading_days)
            vals = paths[day_idx]
            quarterly.append({
                "quarter": q,
                "median": round(float(np.median(vals)), 2),
                "p10": round(float(np.percentile(vals, 10)), 2),
                "p25": round(float(np.percentile(vals, 25)), 2),
                "p75": round(float(np.percentile(vals, 75)), 2),
                "p90": round(float(np.percentile(vals, 90)), 2),
            })

        return {
            "current_value": round(total_value, 2),
            "horizon_years": years,
            "monthly_add": monthly_add,
            "expected_final": round(float(np.median(final)), 2),
            "p10_final": round(float(np.percentile(final, 10)), 2),
            "p90_final": round(float(np.percentile(final, 90)), 2),
            "prob_gain": round(float(np.mean(final > total_invested)) * 100, 1),
            "expected_return_pct": round(float(np.median(final) / total_invested - 1) * 100, 1),
            "quarterly": quarterly,
        }

    @staticmethod
    def stress_test(holdings: list[dict], scenario: str = "2008") -> dict:
        """Estimate portfolio impact under historical crisis scenarios.

        Args:
            holdings: Portfolio holdings
            scenario: "2008", "2020", "2022", "1987"
        """
        # Historical drawdowns by scenario (approximate sector-level)
        scenarios = {
            "2008": {"name": "2008 Financial Crisis", "sp500_dd": -0.56, "duration_months": 17},
            "2020": {"name": "COVID-19 Crash", "sp500_dd": -0.34, "duration_months": 1},
            "2022": {"name": "2022 Bear Market", "sp500_dd": -0.25, "duration_months": 10},
            "1987": {"name": "Black Monday", "sp500_dd": -0.34, "duration_months": 2},
        }

        if scenario not in scenarios:
            scenario = "2008"

        sc = scenarios[scenario]
        total_value = sum(h["shares"] * h["current_price"] for h in holdings)

        # Estimate per-ticker impact (beta-adjusted)
        results = []
        portfolio_dd = 0
        for h in holdings:
            weight = (h["shares"] * h["current_price"]) / total_value if total_value > 0 else 0
            try:
                beta = yf.Ticker(h["ticker"]).info.get("beta", 1.0) or 1.0
            except (KeyError, AttributeError, TypeError, ValueError) as e:
                logger.debug("Beta fetch for %s failed, using 1.0: %s", h["ticker"], e)
                beta = 1.0

            ticker_dd = sc["sp500_dd"] * beta
            ticker_dd = max(ticker_dd, -0.95)  # Cap at 95% loss
            portfolio_dd += weight * ticker_dd

            results.append({
                "ticker": h["ticker"],
                "beta": beta,
                "estimated_drawdown": ticker_dd * 100,
                "estimated_loss": h["shares"] * h["current_price"] * ticker_dd,
            })

        return {
            "scenario": sc["name"],
            "sp500_drawdown": sc["sp500_dd"] * 100,
            "duration_months": sc["duration_months"],
            "portfolio_drawdown": portfolio_dd * 100,
            "portfolio_loss": total_value * portfolio_dd,
            "holdings": results,
        }
