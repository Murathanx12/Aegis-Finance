"""
Aegis Finance — Stateless Portfolio Analytics
================================================

Computes portfolio metrics from a list of holdings.
No server-side state — portfolio lives in browser localStorage.

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


class PortfolioEngine:
    """Stateless portfolio analytics."""

    @staticmethod
    def analyze_portfolio(holdings: list[dict]) -> dict:
        """Analyze a portfolio of holdings.

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
        try:
            price_data = yf.download(tickers, period="2y", progress=False)["Close"]
            if isinstance(price_data, pd.Series):
                price_data = price_data.to_frame(name=tickers[0])
            returns = price_data.pct_change().dropna()
        except Exception as e:
            logger.warning("Failed to fetch price data: %s", e)
            return {
                "total_value": total_value,
                "allocations": [
                    {"ticker": h["ticker"], "weight": w * 100, "value": v}
                    for h, w, v in zip(holdings, weights, values)
                ],
                "error": f"Could not fetch historical data: {e}",
            }

        # Portfolio returns
        w_arr = np.array(weights)
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
        cvar_95 = float(np.mean(port_returns[port_returns <= np.percentile(port_returns, 5)])) * 100

        # Correlation matrix
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
    ) -> dict:
        """Build a goal-based portfolio allocation.

        Args:
            risk_tolerance: "conservative", "moderate", or "aggressive"
            investment_amount: Dollar amount to invest
            time_horizon: "1y", "3y", "5y", "10y"

        Returns:
            Dict with target allocations and rationale
        """
        template = _ALLOCATION_TEMPLATES.get(risk_tolerance, _ALLOCATION_TEMPLATES["moderate"])

        # Adjust for time horizon
        allocations = dict(template["allocations"])
        if time_horizon in ("1y", "3y"):
            # Shorter horizon → more bonds, less equity
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
            "description": template["description"],
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

        try:
            price_data = yf.download(tickers, period="5y", progress=False)["Close"]
            if isinstance(price_data, pd.Series):
                price_data = price_data.to_frame(name=tickers[0])
            returns = price_data.pct_change().dropna()
        except Exception:
            return {"error": "Could not fetch price data for projection"}

        available = [t for t in tickers if t in returns.columns]
        if not available:
            return {"error": "No price data for projection"}

        w_arr = np.array([weights[tickers.index(t)] for t in available])
        w_arr = w_arr / w_arr.sum()

        port_returns = returns[available].values @ w_arr
        mu_daily = float(np.mean(port_returns))
        sigma_daily = float(np.std(port_returns))

        trading_days = years * 252
        months = years * 12

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
            "prob_gain": round(float(np.mean(final > total_value)) * 100, 1),
            "expected_return_pct": round(float(np.median(final) / total_value - 1) * 100, 1),
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
