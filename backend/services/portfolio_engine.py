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

logger = logging.getLogger(__name__)

# Goal-based allocation templates
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
        "description": "Maximum growth, higher volatility",
        "allocations": {
            "VTI": 0.35, "QQQ": 0.25, "VXUS": 0.15,
            "VGT": 0.10, "ARKK": 0.05, "BND": 0.05,
            "GLD": 0.05,
        },
    },
}

# Risk aversion mapping for Black-Litterman
_RISK_AVERSION = {
    "conservative": 5.0,
    "moderate": 2.5,
    "aggressive": 1.0,
}

# Default ETF universe for BL/HRP
_ETF_UNIVERSE = ["VTI", "VXUS", "BND", "QQQ", "VGT", "VNQ", "GLD", "VTIP", "XLE", "XLV"]


# ══════════════════════════════════════════════════════════════════════════════
# COVARIANCE SHRINKAGE (Phase 3.3)
# ══════════════════════════════════════════════════════════════════════════════


def _shrunk_covariance(
    data: pd.DataFrame,
    returns_data: bool = False,
) -> pd.DataFrame:
    """Compute Ledoit-Wolf shrunk covariance matrix.

    Ledoit-Wolf shrinkage reduces estimation error by shrinking the sample
    covariance toward a structured estimator. This dramatically improves
    portfolio optimization stability.

    Args:
        data: Price DataFrame (default) or returns DataFrame.
        returns_data: If True, data contains returns instead of prices.

    Falls back to sample covariance if pypfopt is not available.
    """
    try:
        from pypfopt import risk_models
        cov = risk_models.CovarianceShrinkage(
            data, returns_data=returns_data
        ).ledoit_wolf()
        return cov
    except ImportError:
        logger.warning("pypfopt not available, using sample covariance")
        if returns_data:
            return data.cov() * 252
        return data.pct_change().dropna().cov() * 252


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
        except Exception:
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
        rf_daily = 0.04 / 252
        sharpe = float((np.mean(port_returns) - rf_daily) / np.std(port_returns) * np.sqrt(252))

        return {
            "total_value": total_value,
            "annual_return": port_annual_return,
            "annual_volatility": port_annual_vol,
            "sharpe_ratio": sharpe,
            "var_95_daily": var_95,
            "cvar_95_daily": cvar_95,
            "max_drawdown": max_dd,
            "allocations": [
                {"ticker": h["ticker"], "weight": w * 100, "value": v}
                for h, w, v in zip(holdings, weights, values)
            ],
            "correlation": corr_data,
        }

    @staticmethod
    def build_portfolio(
        risk_tolerance: str = "moderate",
        investment_amount: float = 10000,
        time_horizon: str = "5y",
        method: str = "template",
        views: Optional[dict] = None,
    ) -> dict:
        """Build a portfolio allocation.

        Args:
            risk_tolerance: "conservative", "moderate", or "aggressive"
            investment_amount: Dollar amount to invest
            time_horizon: "1y", "3y", "5y", "10y"
            method: "template" (default), "black-litterman", or "hrp"
            views: Optional dict of {ticker: expected_return} for BL

        Returns:
            Dict with target allocations and rationale
        """
        if method == "black-litterman":
            return PortfolioEngine._build_bl(
                risk_tolerance, investment_amount, time_horizon, views
            )
        elif method == "hrp":
            return PortfolioEngine._build_hrp(
                risk_tolerance, investment_amount, time_horizon
            )
        else:
            return PortfolioEngine._build_template(
                risk_tolerance, investment_amount, time_horizon
            )

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
            from pypfopt import BlackLittermanModel, risk_models, expected_returns
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

        # Market-cap weights (approximate — use equal weight as proxy)
        # In production, fetch actual market caps
        market_caps = {t: 1.0 for t in available}
        cap_total = sum(market_caps.values())
        market_weights = {t: v / cap_total for t, v in market_caps.items()}

        # Risk aversion parameter
        delta = _RISK_AVERSION.get(risk_tolerance, 2.5)

        try:
            # Compute equilibrium returns (market-implied prior)
            from pypfopt.black_litterman import market_implied_prior_returns
            pi = market_implied_prior_returns(market_caps, delta, cov)

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
            ef = EfficientFrontier(posterior_returns, cov, weight_bounds=(0.0, max_weight))
            ef.max_sharpe(risk_free_rate=0.04)
            weights = ef.clean_weights()

            # Filter zero-weight assets
            allocations = {t: w for t, w in weights.items() if w > 0.01}

            if not allocations:
                allocations = dict(market_weights)

            # Normalize
            total = sum(allocations.values())
            allocations = {k: v / total for k, v in allocations.items()}

            # Get portfolio performance
            try:
                perf = ef.portfolio_performance(risk_free_rate=0.04)
                description = (
                    f"Black-Litterman optimized ({risk_tolerance}). "
                    f"Expected return: {perf[0]*100:.1f}%, "
                    f"Volatility: {perf[1]*100:.1f}%, "
                    f"Sharpe: {perf[2]:.2f}"
                )
            except Exception:
                description = f"Black-Litterman optimized ({risk_tolerance})"

        except Exception as e:
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

            # Adjust for risk tolerance: scale equity vs bond exposure
            equity_etfs = {"VTI", "VXUS", "QQQ", "VGT", "XLE", "XLV"}
            bond_etfs = {"BND", "VTIP"}

            if risk_tolerance == "conservative":
                # Boost bonds, reduce equity
                for t in weights:
                    if t in equity_etfs:
                        weights[t] *= 0.7
                    elif t in bond_etfs:
                        weights[t] *= 1.5
            elif risk_tolerance == "aggressive":
                # Boost equity, reduce bonds
                for t in weights:
                    if t in equity_etfs:
                        weights[t] *= 1.3
                    elif t in bond_etfs:
                        weights[t] *= 0.5

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
            except Exception:
                description = f"Hierarchical Risk Parity ({risk_tolerance})"

        except Exception as e:
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
            except Exception:
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
        """Project portfolio value forward using historical returns.

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

        port_returns = returns[available].values @ w_arr
        mu_daily = float(np.mean(port_returns))
        sigma_daily = float(np.std(port_returns))

        trading_days = years * 252

        # Simple projection using historical stats
        rng = np.random.default_rng(42)
        n_sims = 2000
        paths = np.zeros((trading_days + 1, n_sims))
        paths[0] = total_value

        for t in range(1, trading_days + 1):
            daily_r = mu_daily + sigma_daily * rng.standard_normal(n_sims)
            paths[t] = paths[t - 1] * (1 + daily_r)
            # Add monthly contribution at end of each month (~21 trading days)
            if monthly_add > 0 and t % 21 == 0:
                paths[t] += monthly_add

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
            except Exception:
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
