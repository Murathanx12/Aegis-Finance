"""
Aegis Finance SDK
=================

Python client for the Aegis Finance REST API. Zero external dependencies
beyond `requests`.

Quick start::

    import aegis

    # Live snapshot (real-time via Finnhub/Polygon fallback)
    snap = aegis.equity.snapshot("AAPL")
    print(snap["price"], snap["source"])

    # Portfolio analysis
    result = aegis.portfolio.analyze([
        {"ticker": "AAPL", "shares": 10, "current_price": 230.0},
        {"ticker": "MSFT", "shares": 5,  "current_price": 420.0},
    ])
    print(result["risk_number"])

    # Multi-period optimization with transaction costs + tracking error
    opt = aegis.portfolio.optimize_mpc(
        ["AAPL", "MSFT", "GOOGL", "NVDA"],
        benchmark_weights={"AAPL": 0.25, "MSFT": 0.25, "GOOGL": 0.25, "NVDA": 0.25},
        tracking_error_limit=0.05,
        horizon=4,
    )
    print(opt["final_weights"])

Configuration::

    aegis.configure(base_url="http://localhost:8000", timeout=30)

or set `AEGIS_API_URL` in the environment.
"""

from aegis.client import (
    AegisClient,
    AegisError,
    configure,
    default_client,
)
from aegis.namespaces import calendar, equity, macro, portfolio, risk, world

__version__ = "0.1.0"

__all__ = [
    "AegisClient",
    "AegisError",
    "__version__",
    "calendar",
    "configure",
    "default_client",
    "equity",
    "macro",
    "portfolio",
    "risk",
    "world",
]
