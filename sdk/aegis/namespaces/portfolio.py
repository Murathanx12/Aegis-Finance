"""Portfolio construction, optimization, and tearsheet endpoints."""

from __future__ import annotations

from typing import Optional

from aegis.client import default_client


Holdings = list[dict]


def analyze(holdings: Holdings, *, client=None) -> dict:
    """Full portfolio analytics: risk number, factors, stress, attribution, MCTR."""
    c = client or default_client()
    return c.post("/api/portfolio/analyze", json={"holdings": holdings})


def optimize(
    tickers: list[str],
    method: str = "mean_variance",
    *,
    lookback_days: int = 504,
    client=None,
) -> dict:
    """Classical optimizer (CVaR / risk parity / HRP via riskfolio-lib)."""
    c = client or default_client()
    return c.post(
        "/api/portfolio/optimize",
        json={
            "tickers": tickers,
            "method": method,
            "lookback_days": lookback_days,
        },
    )


def optimize_mpc(
    tickers: list[str],
    *,
    current_weights: Optional[dict[str, float]] = None,
    benchmark_weights: Optional[dict[str, float]] = None,
    sector_map: Optional[dict[str, str]] = None,
    sector_caps: Optional[dict[str, float]] = None,
    gamma: float = 3.0,
    transaction_cost_bps: float = 5.0,
    holding_penalty: float = 0.0,
    max_weight: float = 0.35,
    min_weight: float = 0.0,
    tracking_error_limit: Optional[float] = None,
    allow_shorts: bool = False,
    horizon: int = 1,
    return_decay: float = 0.0,
    lookback_days: int = 504,
    client=None,
) -> dict:
    """Convex optimizer with TX costs + TE + factor/sector budgets (+ optional
    rolling multi-period). Full-fidelity wrapper around the MPC endpoint."""
    c = client or default_client()
    body = {
        "tickers": tickers,
        "current_weights": current_weights,
        "benchmark_weights": benchmark_weights,
        "sector_map": sector_map,
        "sector_caps": sector_caps,
        "gamma": gamma,
        "transaction_cost_bps": transaction_cost_bps,
        "holding_penalty": holding_penalty,
        "max_weight": max_weight,
        "min_weight": min_weight,
        "tracking_error_limit": tracking_error_limit,
        "allow_shorts": allow_shorts,
        "horizon": horizon,
        "return_decay": return_decay,
        "lookback_days": lookback_days,
    }
    body = {k: v for k, v in body.items() if v is not None}
    return c.post("/api/portfolio/optimize-mpc", json=body)


def factor_exposures(holdings: Holdings, *, client=None) -> dict:
    c = client or default_client()
    return c.post("/api/portfolio/factor-exposures", json={"holdings": holdings})


def risk_contributions(holdings: Holdings, *, client=None) -> dict:
    c = client or default_client()
    return c.post("/api/portfolio/risk-contributions", json={"holdings": holdings})


def copula_risk(holdings: Holdings, *, client=None) -> dict:
    c = client or default_client()
    return c.post("/api/portfolio/copula-risk", json={"holdings": holdings})


def benchmark(holdings: Holdings, ticker: str = "SPY", *, client=None) -> dict:
    c = client or default_client()
    return c.post(
        "/api/portfolio/benchmark",
        json={"holdings": holdings, "benchmark_ticker": ticker},
    )


def attribution(holdings: Holdings, period: str = "1mo", *, client=None) -> dict:
    c = client or default_client()
    return c.post(
        "/api/portfolio/attribution",
        json={"holdings": holdings, "period": period},
    )


def tearsheet_html(
    holdings: Holdings,
    title: str = "Portfolio Tearsheet",
    *,
    client=None,
) -> str:
    """Return the full HTML tearsheet as a string."""
    c = client or default_client()
    return c.post(
        "/api/portfolio/tearsheet.html",
        json={"holdings": holdings, "title": title},
    )


def tearsheet_xlsx(
    holdings: Holdings,
    title: str = "Portfolio Tearsheet",
    *,
    client=None,
) -> bytes:
    """Return an Excel (.xlsx) tearsheet as raw bytes."""
    c = client or default_client()
    return c.post(
        "/api/portfolio/tearsheet.xlsx",
        json={"holdings": holdings, "title": title},
    )
