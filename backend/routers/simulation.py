"""
Monte Carlo Simulation Router
================================

GET /api/simulation/sp500     — S&P 500 5-year projection (scenario-weighted)
GET /api/simulation/scenarios — Individual scenario results
"""

import asyncio
import logging

import numpy as np
from fastapi import APIRouter, HTTPException, Query

from backend.cache import cache_get, cache_set
from backend.config import config

router = APIRouter(prefix="/api/simulation", tags=["simulation"])
logger = logging.getLogger(__name__)

_CACHE_TTL = config["cache"]


@router.get("/sp500")
async def get_sp500_projection(
    n_sims: int = Query(10000, ge=1000, le=50000),
    years: int = Query(5, ge=1, le=10),
):
    """S&P 500 scenario-weighted Monte Carlo projection."""
    cache_key = f"sp500_projection:{n_sims}:{years}"
    cached = cache_get(cache_key, _CACHE_TTL["ttl_simulation"])
    if cached is not None:
        return cached

    try:
        result = await asyncio.to_thread(_run_sp500_projection, n_sims, years)
        cache_set(cache_key, result)
        return result
    except Exception as e:
        logger.error("sp500 projection failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


def _run_sp500_projection(n_sims: int, years: int) -> dict:
    from backend.config import config
    from backend.services.data_fetcher import DataFetcher
    from backend.services.monte_carlo import run_monte_carlo
    from backend.services.risk_scorer import build_risk_score
    from backend.services.regime_detector import detect_regimes

    fetcher = DataFetcher()
    data, _ = fetcher.fetch_market_data()

    start_price = float(data["SP500"].iloc[-1])
    forecast_days = years * 252

    # Compute required inputs for run_monte_carlo
    data["Risk_Score"] = build_risk_score(data)
    risk_score = float(data["Risk_Score"].iloc[-1])

    _, current_regime = detect_regimes(data)

    current_vix = float(data["VIX"].iloc[-1]) if "VIX" in data.columns else 20.0
    yield_curve = 0.0
    if "T10Y" in data.columns and "T3M" in data.columns:
        yield_curve = float(data["T10Y"].iloc[-1] - data["T3M"].iloc[-1])

    crash_freq = config["simulation"]["jump_diffusion"]["annual_rate"]

    results = run_monte_carlo(
        current_price=start_price,
        current_regime=current_regime,
        risk_score=risk_score,
        crash_freq=crash_freq,
        current_vix=current_vix,
        yield_curve=yield_curve,
        val_penalty=0.0,
        n_sims_override=n_sims,
        forecast_days_override=forecast_days,
    )

    # Extract percentile paths for charting
    paths = results["paths"]
    percentiles = {}
    for p in [5, 25, 50, 75, 95]:
        pct_path = np.percentile(paths, p, axis=1).tolist()
        # Downsample for frontend (every 5 days)
        percentiles[f"p{p}"] = pct_path[::5]

    final_prices = paths[-1]
    total_return = float(np.median(final_prices) / start_price - 1)
    annual_return = (1 + total_return) ** (1 / years) - 1

    return {
        "start_price": start_price,
        "forecast_years": years,
        "n_sims": n_sims,
        "median_final": float(np.median(final_prices)),
        "mean_final": float(np.mean(final_prices)),
        "p05_final": float(np.percentile(final_prices, 5)),
        "p95_final": float(np.percentile(final_prices, 95)),
        "median_total_return": round(total_return * 100, 1),
        "median_annual_return": round(annual_return * 100, 1),
        "prob_loss": round(float(np.mean(final_prices < start_price)) * 100, 1),
        "percentile_paths": percentiles,
        "scenario_weights": results.get("scenarios", {}),
        "last_updated": str(data.index[-1].date()),
    }


@router.get("/scenarios")
async def get_scenario_results():
    """Individual scenario breakdown with metrics."""
    cached = cache_get("scenario_results", _CACHE_TTL["ttl_simulation"])
    if cached is not None:
        return cached

    try:
        result = await asyncio.to_thread(_compute_scenarios)
        cache_set("scenario_results", result)
        return result
    except Exception as e:
        logger.error("scenarios failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


def _compute_scenarios() -> dict:
    from backend.config import get_scenario_configs, get_institutional_return
    from backend.services.data_fetcher import DataFetcher
    from backend.services.monte_carlo import simulate_paths

    fetcher = DataFetcher()
    data, _ = fetcher.fetch_market_data()
    start_price = float(data["SP500"].iloc[-1])

    returns = data["SP500"].pct_change().dropna()
    hist_mu = float(np.log(1 + returns).mean() * 252)
    hist_sigma = float(returns.std() * np.sqrt(252))

    inst_return = get_institutional_return()
    inst_mu = np.log(1 + inst_return)

    scenarios = get_scenario_configs()
    results = []

    for name, sc in scenarios.items():
        # Compute drift_adj/vol_mult from resolved scenario config
        scenario_return = sc.get("return", inst_return)
        drift_adj = np.log(1 + scenario_return) - inst_mu
        vol_mult = sc.get("volatility", hist_sigma) / max(hist_sigma, 0.01)
        crash_mult = sc.get("crash_multiplier", 1.0)

        scenario_dict = {
            "drift_adj": drift_adj,
            "vol_mult": vol_mult,
            "crash_mult": crash_mult,
        }

        paths = simulate_paths(
            start_price, hist_mu, hist_sigma,
            1260, 3000, 1.0 / 9.0, 0.0, scenario_dict,
        )

        final = paths[-1]
        total_return = float(np.median(final) / start_price - 1)

        results.append({
            "name": name,
            "weight": sc.get("probability", 0),
            "description": sc.get("description", ""),
            "median_return": round(total_return * 100, 1),
            "p05_return": round(float(np.percentile(final, 5) / start_price - 1) * 100, 1),
            "p95_return": round(float(np.percentile(final, 95) / start_price - 1) * 100, 1),
            "prob_loss": round(float(np.mean(final < start_price)) * 100, 1),
        })

    return {"scenarios": results, "start_price": start_price}
