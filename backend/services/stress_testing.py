"""
Aegis Finance — Historical Stress Testing Framework
=====================================================

Replays historical crisis scenarios against current portfolios to estimate
projected losses. Uses actual sector/factor returns from each crisis period
to model how a given portfolio would have performed.

Scenarios:
  - 2008 GFC: Subprime mortgage crisis
  - 2020 COVID: Pandemic crash
  - 2000 Dot-Com: Tech bubble burst
  - 1987 Black Monday: Program trading cascade
  - 2022 Rate Shock: Fed tightening cycle
  - 2018 Volmageddon: VIX spike + Q4 selloff

Usage:
    from backend.services.stress_testing import (
        stress_test_portfolio, stress_test_single, get_scenario_list
    )
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

from backend.config import config

logger = logging.getLogger(__name__)

# Cache for crisis-period returns (fetched once per scenario)
_CRISIS_RETURNS_CACHE: dict = {}


def get_scenario_list() -> list[dict]:
    """Return the list of available stress test scenarios."""
    scenarios = config.get("stress_testing", {}).get("scenarios", {})
    return [
        {
            "id": k,
            "name": v["name"],
            "start": v["start"],
            "end": v["end"],
            "sp500_drawdown": v["sp500_drawdown"],
            "description": v["description"],
        }
        for k, v in scenarios.items()
    ]


def _fetch_crisis_returns(
    scenario_id: str,
    tickers: list[str],
) -> Optional[pd.DataFrame]:
    """Fetch actual returns for given tickers during a crisis period.

    Returns DataFrame of cumulative returns (1.0 = no change) for each ticker
    over the crisis window, or None if data unavailable.
    """
    scenarios = config.get("stress_testing", {}).get("scenarios", {})
    scenario = scenarios.get(scenario_id)
    if scenario is None:
        return None

    cache_key = f"{scenario_id}_{'_'.join(sorted(tickers))}"
    if cache_key in _CRISIS_RETURNS_CACHE:
        return _CRISIS_RETURNS_CACHE[cache_key]

    try:
        import yfinance as yf

        start = scenario["start"]
        end = scenario["end"]

        # Fetch historical data for all tickers + SPY as benchmark
        all_tickers = list(set(tickers + ["SPY"]))
        data = yf.download(
            all_tickers, start=start, end=end,
            auto_adjust=True, progress=False, threads=True,
        )

        if data.empty:
            logger.warning("No data for scenario %s", scenario_id)
            return None

        # Extract close prices
        if isinstance(data.columns, pd.MultiIndex):
            prices = data["Close"]
        else:
            prices = data[["Close"]].rename(columns={"Close": all_tickers[0]})

        # Compute cumulative returns from start
        cumulative = prices / prices.iloc[0]

        _CRISIS_RETURNS_CACHE[cache_key] = cumulative
        return cumulative

    except Exception as e:
        logger.warning("Failed to fetch crisis data for %s: %s", scenario_id, e)
        return None


def _estimate_crisis_return(
    ticker: str,
    scenario_id: str,
    sector: Optional[str] = None,
    beta: Optional[float] = None,
    sp500_drawdown: float = -0.30,
) -> float:
    """Estimate a stock's return during a crisis when actual data is unavailable.

    Uses scenario-specific sector multipliers and beta to approximate.
    Different crises hit different sectors: GFC destroyed Financials,
    Dot-Com destroyed Tech, COVID destroyed Energy/Travel while Tech
    was resilient. Using the same multipliers for all scenarios produced
    systematically wrong estimates.
    """
    # Scenario-specific sector sensitivity multipliers.
    # These reflect actual sector drawdowns relative to S&P 500 in each crisis.
    _SCENARIO_SECTOR_MULTS = {
        "2008_GFC": {
            "Technology": 1.1,
            "Financials": 1.8,         # Epicenter — banks lost 70-90%
            "Energy": 1.3,
            "Consumer Disc.": 1.4,
            "Communications": 1.0,
            "Industrials": 1.3,
            "Materials": 1.2,
            "Real Estate": 1.6,        # Mortgage crisis hit RE hard
            "Healthcare": 0.7,
            "Consumer Staples": 0.5,   # Defensive — outperformed significantly
            "Utilities": 0.5,
        },
        "2020_COVID": {
            "Technology": 0.6,         # Tech was resilient, quick recovery
            "Financials": 1.2,
            "Energy": 2.0,             # Oil crash + demand destruction
            "Consumer Disc.": 1.5,     # Travel/hospitality devastated
            "Communications": 0.7,
            "Industrials": 1.3,
            "Materials": 1.1,
            "Real Estate": 1.4,
            "Healthcare": 0.8,
            "Consumer Staples": 0.6,
            "Utilities": 0.8,
        },
        "2000_DOTCOM": {
            "Technology": 2.0,         # Epicenter — Nasdaq lost ~78%
            "Financials": 0.7,
            "Energy": 0.6,
            "Consumer Disc.": 1.2,
            "Communications": 1.8,     # Telecom bust (WorldCom)
            "Industrials": 0.9,
            "Materials": 0.8,
            "Real Estate": 0.5,
            "Healthcare": 0.7,
            "Consumer Staples": 0.4,
            "Utilities": 0.5,
        },
        "1987_BLACK_MONDAY": {
            "Technology": 1.2,
            "Financials": 1.3,
            "Energy": 0.9,
            "Consumer Disc.": 1.1,
            "Communications": 1.0,
            "Industrials": 1.1,
            "Materials": 1.0,
            "Real Estate": 1.0,
            "Healthcare": 0.8,
            "Consumer Staples": 0.7,
            "Utilities": 0.6,
        },
        "2022_RATE_SHOCK": {
            "Technology": 1.5,         # Growth-to-value rotation hit tech hard
            "Financials": 0.8,         # Banks benefit from higher rates
            "Energy": 0.3,             # Energy rallied (oil spike)
            "Consumer Disc.": 1.4,
            "Communications": 1.6,     # META, GOOGL hit hard
            "Industrials": 0.9,
            "Materials": 0.8,
            "Real Estate": 1.3,        # Rate-sensitive
            "Healthcare": 0.7,
            "Consumer Staples": 0.6,
            "Utilities": 0.7,
        },
        "2018_VOLMAGEDDON": {
            "Technology": 1.2,
            "Financials": 1.1,
            "Energy": 1.5,             # Oil crash Q4 2018
            "Consumer Disc.": 1.2,
            "Communications": 1.1,
            "Industrials": 1.2,
            "Materials": 1.1,
            "Real Estate": 0.9,
            "Healthcare": 0.8,
            "Consumer Staples": 0.6,
            "Utilities": 0.5,
        },
    }

    # Default fallback if scenario not in the map
    _DEFAULT_SECTOR_MULTS = {
        "Technology": 1.3, "Financials": 1.4, "Energy": 1.2,
        "Consumer Disc.": 1.2, "Communications": 1.1, "Industrials": 1.1,
        "Materials": 1.0, "Real Estate": 1.1, "Healthcare": 0.8,
        "Consumer Staples": 0.7, "Utilities": 0.6,
    }

    scenario_mults = _SCENARIO_SECTOR_MULTS.get(scenario_id, _DEFAULT_SECTOR_MULTS)
    sector_mult = scenario_mults.get(sector, 1.0)
    beta_adj = beta if beta and beta > 0 else 1.0

    # Estimated drawdown = SP500 drawdown × beta × sector sensitivity
    estimated = sp500_drawdown * beta_adj * sector_mult

    # Cap at -95% (no worse than near-total loss)
    return max(estimated, -0.95)


def stress_test_single(
    ticker: str,
    scenario_id: Optional[str] = None,
    sector: Optional[str] = None,
    beta: Optional[float] = None,
) -> dict:
    """Stress test a single stock against all or a specific scenario.

    Returns projected drawdowns under each crisis scenario.
    """
    scenarios = config.get("stress_testing", {}).get("scenarios", {})
    if scenario_id:
        scenarios = {k: v for k, v in scenarios.items() if k == scenario_id}

    results = {}
    for sid, scenario in scenarios.items():
        # Try actual historical data first
        crisis_data = _fetch_crisis_returns(sid, [ticker])
        if crisis_data is not None and ticker in crisis_data.columns:
            cumret = crisis_data[ticker].dropna()
            if len(cumret) >= 2:
                peak_to_trough = float(cumret.min() - 1.0)
                final_return = float(cumret.iloc[-1] - 1.0)
                results[sid] = {
                    "name": scenario["name"],
                    "projected_drawdown": round(peak_to_trough, 4),
                    "period_return": round(final_return, 4),
                    "data_source": "historical",
                    "description": scenario["description"],
                }
                continue

        # Fall back to estimation
        estimated = _estimate_crisis_return(
            ticker, sid, sector=sector, beta=beta,
            sp500_drawdown=scenario["sp500_drawdown"],
        )
        results[sid] = {
            "name": scenario["name"],
            "projected_drawdown": round(estimated, 4),
            "period_return": round(estimated, 4),
            "data_source": "estimated",
            "description": scenario["description"],
        }

    return {"ticker": ticker, "scenarios": results}


def stress_test_portfolio(
    weights: dict[str, float],
    sector_map: Optional[dict[str, str]] = None,
    beta_map: Optional[dict[str, float]] = None,
) -> dict:
    """Stress test a portfolio against all historical crisis scenarios.

    Args:
        weights: {ticker: weight} — weights should sum to ~1.0
        sector_map: Optional {ticker: sector_name} for estimation fallback
        beta_map: Optional {ticker: beta} for estimation fallback

    Returns:
        Portfolio-level stress test results with per-stock contributions.
    """
    scenarios = config.get("stress_testing", {}).get("scenarios", {})
    tickers = list(weights.keys())

    portfolio_results = {}
    for sid, scenario in scenarios.items():
        # Fetch actual crisis returns for all tickers
        crisis_data = _fetch_crisis_returns(sid, tickers)

        stock_drawdowns = {}
        portfolio_drawdown = 0.0
        total_weight = sum(weights.values())

        for ticker, weight in weights.items():
            w = weight / total_weight if total_weight > 0 else 0

            if crisis_data is not None and ticker in crisis_data.columns:
                cumret = crisis_data[ticker].dropna()
                if len(cumret) >= 2:
                    dd = float(cumret.min() - 1.0)
                    stock_drawdowns[ticker] = {
                        "weight": round(w, 4),
                        "drawdown": round(dd, 4),
                        "contribution": round(w * dd, 4),
                        "data_source": "historical",
                    }
                    portfolio_drawdown += w * dd
                    continue

            # Estimation fallback
            sector = (sector_map or {}).get(ticker)
            beta = (beta_map or {}).get(ticker)
            dd = _estimate_crisis_return(
                ticker, sid, sector=sector, beta=beta,
                sp500_drawdown=scenario["sp500_drawdown"],
            )
            stock_drawdowns[ticker] = {
                "weight": round(w, 4),
                "drawdown": round(dd, 4),
                "contribution": round(w * dd, 4),
                "data_source": "estimated",
            }
            portfolio_drawdown += w * dd

        # Value at risk context
        portfolio_results[sid] = {
            "name": scenario["name"],
            "portfolio_drawdown": round(portfolio_drawdown, 4),
            "sp500_drawdown": scenario["sp500_drawdown"],
            "relative_to_market": round(
                portfolio_drawdown / scenario["sp500_drawdown"], 4
            ) if scenario["sp500_drawdown"] != 0 else None,
            "description": scenario["description"],
            "stock_contributions": stock_drawdowns,
        }

    # Worst-case scenario
    worst = min(portfolio_results.items(), key=lambda x: x[1]["portfolio_drawdown"])
    best = max(portfolio_results.items(), key=lambda x: x[1]["portfolio_drawdown"])

    return {
        "portfolio_size": len(weights),
        "scenarios": portfolio_results,
        "worst_case": {
            "scenario": worst[0],
            "name": worst[1]["name"],
            "drawdown": worst[1]["portfolio_drawdown"],
        },
        "best_case": {
            "scenario": best[0],
            "name": best[1]["name"],
            "drawdown": best[1]["portfolio_drawdown"],
        },
    }


# ══════════════════════════════════════════════════════════════════════════════
# HYPOTHETICAL (USER-DEFINED) STRESS SCENARIOS
# ══════════════════════════════════════════════════════════════════════════════


def hypothetical_stress_test(
    weights: dict[str, float],
    shocks: dict[str, float],
    beta_map: Optional[dict[str, float]] = None,
) -> dict:
    """Apply user-defined hypothetical shocks to a portfolio.

    This is the "what-if" scenario builder that Bloomberg MARS provides.
    Users define shocks to macro factors, and we propagate them through
    factor sensitivities to estimate portfolio impact.

    Args:
        weights: {ticker: weight}
        shocks: Dict of macro shocks to apply. Supported shocks:
            - "sp500": S&P 500 return shock (e.g., -0.15 = -15%)
            - "rates": Interest rate change in bps (e.g., 200 = +200bp)
            - "vix": VIX level change (e.g., 20 = VIX rises by 20 points)
            - "oil": Oil price change pct (e.g., -0.30 = -30%)
            - "gold": Gold price change pct (e.g., 0.10 = +10%)
            - "usd": USD index change pct (e.g., 0.05 = +5%)
            - "credit_spread": HY OAS widening in bps (e.g., 300 = +300bp)
        beta_map: Optional {ticker: beta} for each holding

    Returns:
        Portfolio impact estimate with per-holding breakdown.
    """
    # Default factor sensitivities (empirical estimates)
    # These map macro shocks → equity return impact
    _FACTOR_SENSITIVITIES = {
        # How much does a 1% equity shock affect different stock types?
        "sp500_beta": 1.0,  # Beta-scaled
        # How much does a 100bp rate rise affect equities?
        "rates_equity_sensitivity": -0.04,  # -4% per 100bp (growth stocks: -6%, value: -2%)
        "rates_growth_extra": -0.02,  # Extra impact on growth stocks
        "rates_financial_benefit": 0.01,  # Financials benefit from higher rates
        # VIX spike impact (per 10 VIX points)
        "vix_equity_sensitivity": -0.03,
        # Oil shock impact
        "oil_energy_sensitivity": 0.6,  # Energy stocks track oil
        "oil_other_sensitivity": -0.05,  # Other sectors hurt by oil spikes
        # Credit spread widening impact (per 100bp)
        "credit_equity_sensitivity": -0.03,
        "credit_financial_sensitivity": -0.05,
    }

    # Sector classification for differential sensitivity
    sector_map = _build_sector_map_from_config()

    total_weight = sum(weights.values())
    if total_weight <= 0:
        return {"error": "Empty portfolio"}

    # Compute per-stock estimated impact
    stock_impacts = {}
    portfolio_impact = 0.0

    for ticker, weight in weights.items():
        w = weight / total_weight
        beta = (beta_map or {}).get(ticker, 1.0)
        sector = sector_map.get(ticker, "Other")

        # Start with zero impact
        total_impact = 0.0

        # S&P 500 shock → beta-scaled
        if "sp500" in shocks:
            sp_shock = shocks["sp500"]
            impact = sp_shock * beta
            total_impact += impact

        # Interest rate shock
        if "rates" in shocks:
            rate_bps = shocks["rates"]
            rate_impact = (rate_bps / 100) * _FACTOR_SENSITIVITIES["rates_equity_sensitivity"]
            # Growth stocks more sensitive to rates
            if sector in ("Technology", "Communications", "Consumer Disc."):
                rate_impact += (rate_bps / 100) * _FACTOR_SENSITIVITIES["rates_growth_extra"]
            # Financials benefit
            elif sector == "Financials":
                rate_impact += (rate_bps / 100) * _FACTOR_SENSITIVITIES["rates_financial_benefit"]
            total_impact += rate_impact

        # VIX shock
        if "vix" in shocks:
            vix_change = shocks["vix"]
            vix_impact = (vix_change / 10) * _FACTOR_SENSITIVITIES["vix_equity_sensitivity"] * beta
            total_impact += vix_impact

        # Oil shock
        if "oil" in shocks:
            oil_pct = shocks["oil"]
            if sector == "Energy":
                oil_impact = oil_pct * _FACTOR_SENSITIVITIES["oil_energy_sensitivity"]
            else:
                # Rising oil hurts non-energy (negative); falling oil mildly helps
                oil_impact = oil_pct * _FACTOR_SENSITIVITIES["oil_other_sensitivity"] if abs(oil_pct) > 0.1 else 0
            total_impact += oil_impact

        # Credit spread widening
        if "credit_spread" in shocks:
            spread_bps = shocks["credit_spread"]
            credit_impact = (spread_bps / 100) * _FACTOR_SENSITIVITIES["credit_equity_sensitivity"]
            if sector == "Financials":
                credit_impact = (spread_bps / 100) * _FACTOR_SENSITIVITIES["credit_financial_sensitivity"]
            total_impact += credit_impact

        # Gold shock (positive for gold-related, mildly negative for equities)
        if "gold" in shocks:
            gold_pct = shocks["gold"]
            if sector == "Materials":
                total_impact += gold_pct * 0.3
            # Gold rise often signals risk-off
            elif gold_pct > 0.05:
                total_impact += -0.01

        stock_impacts[ticker] = {
            "weight_pct": round(w * 100, 2),
            "beta": round(beta, 2),
            "sector": sector,
            "estimated_return": round(total_impact * 100, 2),
            "contribution": round(w * total_impact * 100, 3),
        }

        portfolio_impact += w * total_impact

    # Sort by impact
    sorted_stocks = sorted(stock_impacts.items(), key=lambda x: x[1]["estimated_return"])

    return {
        "shocks_applied": shocks,
        "portfolio_estimated_return": round(portfolio_impact * 100, 2),
        "portfolio_estimated_pnl_pct": round(portfolio_impact * 100, 2),
        "stock_impacts": stock_impacts,
        "worst_hit": sorted_stocks[0][0] if sorted_stocks else None,
        "best_performer": sorted_stocks[-1][0] if sorted_stocks else None,
        "interpretation": _interpret_hypothetical(shocks, portfolio_impact, stock_impacts),
    }


def _build_sector_map_from_config() -> dict[str, str]:
    """Build ticker → sector mapping from config."""
    sector_stocks = config.get("stock_universe", {}).get("sector_stocks", {})
    mapping = {}
    for sector, tickers in sector_stocks.items():
        for ticker in tickers:
            mapping[ticker] = sector
    return mapping


def _interpret_hypothetical(
    shocks: dict,
    portfolio_impact: float,
    stock_impacts: dict,
) -> str:
    """Human-readable interpretation of hypothetical stress test."""
    parts = []

    # Describe the scenario
    shock_descriptions = []
    if "sp500" in shocks:
        shock_descriptions.append(f"S&P 500 {shocks['sp500']*100:+.0f}%")
    if "rates" in shocks:
        shock_descriptions.append(f"rates {shocks['rates']:+.0f}bp")
    if "vix" in shocks:
        shock_descriptions.append(f"VIX {shocks['vix']:+.0f} points")
    if "oil" in shocks:
        shock_descriptions.append(f"oil {shocks['oil']*100:+.0f}%")
    if "credit_spread" in shocks:
        shock_descriptions.append(f"credit spreads {shocks['credit_spread']:+.0f}bp")

    scenario_str = " + ".join(shock_descriptions) if shock_descriptions else "custom scenario"
    parts.append(f"Under {scenario_str}:")

    if portfolio_impact < -0.10:
        parts.append(f"Portfolio would lose an estimated {abs(portfolio_impact)*100:.1f}%. This is a severe scenario.")
    elif portfolio_impact < -0.05:
        parts.append(f"Portfolio would lose an estimated {abs(portfolio_impact)*100:.1f}%. Moderate stress.")
    elif portfolio_impact < 0:
        parts.append(f"Portfolio would lose an estimated {abs(portfolio_impact)*100:.1f}%. Mild impact.")
    else:
        parts.append(f"Portfolio would gain an estimated {portfolio_impact*100:.1f}%. Positioned favorably for this scenario.")

    return " ".join(parts)
