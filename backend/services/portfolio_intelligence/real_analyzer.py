"""
Aegis Finance — Real Portfolio Analyzer
=========================================

Analyzes the user's actual holdings using existing Aegis services.
Pure orchestration — no new computation logic.

Reuses:
  - data_fetcher.fetch_safe() for price data
  - factor_model.decompose_portfolio() for FF5 exposures
  - attribution.compute_risk_contributions() for MCTR
  - tail_risk.compute_tail_risk_metrics() for downside metrics
  - drawdown_analyzer.analyze_drawdowns() for max DD + duration

Usage:
    from backend.services.portfolio_intelligence.real_analyzer import (
        analyze_portfolio, compute_concentration_flags,
    )
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

from backend.config import config
from backend.schemas.portfolio_intelligence import (
    HoldingInput,
    MetricPack,
    RiskFlag,
    SnapshotResponse,
)

logger = logging.getLogger(__name__)

_SECTOR_MAP: dict[str, str] = {}


_PI_SECTOR_LABELS = {
    "technology": "Technology",
    "semiconductors": "Technology",
    "consumer_internet": "Consumer Disc.",
    "healthcare_biotech": "Healthcare",
    "financials": "Financials",
    "energy_materials": "Energy",
    "industrials_defense": "Industrials",
    "consumer_staples": "Consumer Staples",
    "emerging_tech": "Technology",
    "quantum_cleantech": "Technology",
}

_FIXTURE_SECTORS = {
    "TVTX": "Healthcare",
    "ALMS": "Healthcare",
    "APLT": "Healthcare",
    "NTLA": "Healthcare",
    "APMX": "Healthcare",
}


def _get_sector_map() -> dict[str, str]:
    """Build ticker → sector mapping from config + paper_portfolios universe."""
    global _SECTOR_MAP
    if _SECTOR_MAP:
        return _SECTOR_MAP

    sector_stocks = config.get("stock_universe", {}).get("sector_stocks", {})
    for sector, tickers in sector_stocks.items():
        for ticker in tickers:
            _SECTOR_MAP[ticker] = sector

    try:
        from backend.config import paper_portfolios
        universe = paper_portfolios.get("universe", {})
        individual = universe.get("individual_stocks", {})
        for category, tickers in individual.items():
            label = _PI_SECTOR_LABELS.get(category, "Other")
            for ticker in tickers:
                if ticker not in _SECTOR_MAP:
                    _SECTOR_MAP[ticker] = label
    except Exception as e:
        # Degraded, not fatal: PI-universe tickers fall through to "Other"/
        # fixture labels. But say so — a silently blank sector breakdown
        # reads as "no exposure" to the user, which is wrong data.
        logger.warning("PI universe sector labels unavailable (%s) — "
                       "sector breakdown may be incomplete", e)

    for ticker, sector in _FIXTURE_SECTORS.items():
        if ticker not in _SECTOR_MAP:
            _SECTOR_MAP[ticker] = sector

    return _SECTOR_MAP


def _fetch_prices(
    tickers: list[str],
    lookback_days: int = 504,
) -> Optional[pd.DataFrame]:
    """Fetch closing prices for a list of tickers. Returns DataFrame or None."""
    try:
        import yfinance as yf

        end = datetime.now()
        start = end - timedelta(days=int(lookback_days * 1.5))

        prices = yf.download(
            tickers,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=True,
        )

        if prices.empty:
            return None

        if isinstance(prices.columns, pd.MultiIndex):
            close = prices["Close"]
        else:
            close = prices.to_frame() if isinstance(prices, pd.Series) else prices

        return close.ffill().dropna(how="all")

    except Exception as e:
        logger.warning("Failed to fetch prices: %s", e)
        return None


def _compute_weights(
    holdings: list[HoldingInput],
    prices: pd.DataFrame,
) -> dict[str, float]:
    """Compute portfolio weights from holdings and current prices."""
    values = {}
    for h in holdings:
        if h.ticker in prices.columns and len(prices[h.ticker].dropna()) > 0:
            current_price = float(prices[h.ticker].dropna().iloc[-1])
            values[h.ticker] = h.shares * current_price

    total = sum(values.values())
    if total <= 0:
        return {}
    return {t: v / total for t, v in values.items()}


def _compute_portfolio_returns(
    weights: dict[str, float],
    prices: pd.DataFrame,
) -> pd.Series:
    """Compute daily portfolio returns from weights and price data."""
    available = [t for t in weights if t in prices.columns]
    if not available:
        return pd.Series(dtype=float)

    returns = prices[available].pct_change().dropna()
    if returns.empty:
        return pd.Series(dtype=float)

    w = np.array([weights[t] for t in available])
    w_total = w.sum()
    if w_total <= 0:
        return pd.Series(dtype=float)
    w = w / w_total

    portfolio_returns = (returns.values @ w)
    return pd.Series(portfolio_returns, index=returns.index)


def _compute_basic_metrics(
    daily_returns: pd.Series,
    risk_free_rate: float | None = None,
) -> dict:
    """Compute return, volatility, Sharpe from daily returns."""
    if risk_free_rate is None:
        risk_free_rate = config.get("risk_free_rate", 0.04)

    returns = daily_returns.dropna()
    if len(returns) < 20:
        return {
            "total_return": 0.0,
            "annualized_return": 0.0,
            "annualized_volatility": 0.0,
            "sharpe_ratio": None,
        }

    total_return = float((1 + returns).prod() - 1)
    n_years = len(returns) / 252.0
    ann_return = float((1 + total_return) ** (1 / n_years) - 1) if n_years > 0 else 0.0
    ann_vol = float(returns.std() * np.sqrt(252))
    sharpe = float((ann_return - risk_free_rate) / ann_vol) if ann_vol > 1e-10 else None

    return {
        "total_return": round(total_return, 6),
        "annualized_return": round(ann_return, 6),
        "annualized_volatility": round(ann_vol, 6),
        "sharpe_ratio": round(sharpe, 4) if sharpe is not None else None,
    }


def _compute_beta_tracking(
    portfolio_returns: pd.Series,
    benchmark_ticker: str = "SPY",
    prices: pd.DataFrame | None = None,
) -> dict:
    """Compute beta, tracking error, and information ratio vs benchmark."""
    result = {
        "beta_vs_spy": None,
        "tracking_error_vs_spy": None,
        "information_ratio_vs_spy": None,
    }

    if prices is None or benchmark_ticker not in prices.columns:
        return result

    bench_returns = prices[benchmark_ticker].pct_change().dropna()
    aligned = pd.DataFrame({
        "port": portfolio_returns,
        "bench": bench_returns,
    }).dropna()

    if len(aligned) < 60:
        return result

    port = aligned["port"].values
    bench = aligned["bench"].values

    cov = np.cov(port, bench)
    bench_var = cov[1, 1]
    if bench_var > 1e-12:
        result["beta_vs_spy"] = round(float(cov[0, 1] / bench_var), 4)

    active = port - bench
    te = float(np.std(active) * np.sqrt(252))
    result["tracking_error_vs_spy"] = round(te, 4)

    if te > 1e-10:
        ann_active = float(np.mean(active) * 252)
        result["information_ratio_vs_spy"] = round(ann_active / te, 4)

    return result


def _compute_beta_map(
    available_tickers: list[str],
    prices,
    factor_exposure: dict,
) -> dict[str, float]:
    """Per-ticker market beta for concentration flags.

    Each ticker is isolated: one failed decomposition is logged and skipped
    instead of silently aborting every remaining ticker (the old behavior left
    beta_map partial with no signal, so concentration flags were computed on
    wrong data presented as right).
    """
    beta_map: dict[str, float] = {}
    if factor_exposure.get("Mkt-RF") is None:
        return beta_map
    try:
        from backend.services.factor_model import decompose_stock
    except Exception as e:
        logger.warning("Factor model unavailable — beta-based flags skipped: %s", e)
        return beta_map
    for t in available_tickers:
        if t not in prices.columns:
            continue
        try:
            result = decompose_stock(t, price_series=prices[t])
            if result:
                beta_map[t] = result["factors"]["Mkt-RF"]["loading"]
        except Exception as e:
            logger.warning("Beta decomposition failed for %s — "
                           "concentration flags will exclude it: %s", t, e)
    return beta_map


def compute_concentration_flags(
    weights: dict[str, float],
    sector_map: dict[str, str] | None = None,
    beta_map: dict[str, float] | None = None,
) -> list[RiskFlag]:
    """Check for concentration risks: single-name, sector, and beta warnings."""
    if sector_map is None:
        sector_map = _get_sector_map()

    flags: list[RiskFlag] = []

    for ticker, weight in weights.items():
        if weight > 0.10:
            flags.append(RiskFlag(
                flag_type="single_name",
                severity="critical" if weight > 0.20 else "warning",
                message=f"{ticker} is {weight:.0%} of portfolio (limit: 10%)",
                details={"ticker": ticker, "weight": round(weight, 4), "limit": 0.10},
            ))

    sector_weights: dict[str, float] = {}
    for ticker, weight in weights.items():
        sector = sector_map.get(ticker, "Other")
        sector_weights[sector] = sector_weights.get(sector, 0.0) + weight

    for sector, sw in sector_weights.items():
        if sw > 0.40:
            flags.append(RiskFlag(
                flag_type="sector",
                severity="critical" if sw > 0.50 else "warning",
                message=f"{sector} sector is {sw:.0%} of portfolio (limit: 40%)",
                details={"sector": sector, "weight": round(sw, 4), "limit": 0.40},
            ))

    if beta_map:
        portfolio_beta = sum(
            weights.get(t, 0) * b for t, b in beta_map.items()
        )
        if portfolio_beta > 1.5:
            flags.append(RiskFlag(
                flag_type="beta",
                severity="warning",
                message=f"Portfolio beta is {portfolio_beta:.2f} (elevated market exposure)",
                details={"portfolio_beta": round(portfolio_beta, 4)},
            ))
        elif portfolio_beta < 0.3:
            flags.append(RiskFlag(
                flag_type="beta",
                severity="info",
                message=f"Portfolio beta is {portfolio_beta:.2f} (very low market exposure)",
                details={"portfolio_beta": round(portfolio_beta, 4)},
            ))

    return flags


def compute_correlation_clusters(
    returns: pd.DataFrame,
    threshold: float = 0.70,
    min_cluster_size: int = 3,
) -> list[dict]:
    """Find groups of holdings with high pairwise correlation."""
    if returns.shape[1] < 3 or len(returns) < 60:
        return []

    corr = returns.corr()
    tickers = list(corr.columns)
    visited = set()
    clusters = []

    for i, t1 in enumerate(tickers):
        if t1 in visited:
            continue
        cluster = [t1]
        for j in range(i + 1, len(tickers)):
            t2 = tickers[j]
            if t2 in visited:
                continue
            if corr.loc[t1, t2] >= threshold:
                cluster.append(t2)

        if len(cluster) >= min_cluster_size:
            avg_corr = float(corr.loc[cluster, cluster].values[
                np.triu_indices(len(cluster), k=1)
            ].mean())
            clusters.append({
                "tickers": cluster,
                "avg_correlation": round(avg_corr, 4),
                "size": len(cluster),
            })
            visited.update(cluster)

    return clusters


def analyze_portfolio(
    holdings: list[HoldingInput],
    benchmark_ticker: str = "SPY",
    lookback_days: int = 504,
) -> SnapshotResponse:
    """Analyze a real portfolio. Returns SnapshotResponse with MetricPack and risk flags.

    This is the main entry point for Phase 2. It orchestrates existing services:
      - Price data via yfinance
      - Factor decomposition via factor_model.decompose_portfolio()
      - Risk contributions via attribution.compute_risk_contributions()
      - Tail risk via tail_risk.compute_tail_risk_metrics()
      - Drawdown analysis via drawdown_analyzer.analyze_drawdowns()
    """
    tickers = [h.ticker for h in holdings]
    all_tickers = list(set(tickers + [benchmark_ticker]))

    prices = _fetch_prices(all_tickers, lookback_days=lookback_days)
    if prices is None or prices.empty:
        return SnapshotResponse(
            portfolio_id="real",
            date=datetime.now().strftime("%Y-%m-%d"),
            weights={},
            metrics=None,
            flags=[RiskFlag(
                flag_type="data",
                severity="critical",
                message="Unable to fetch price data for holdings",
            )],
        )

    weights = _compute_weights(holdings, prices)
    if not weights:
        return SnapshotResponse(
            portfolio_id="real",
            date=datetime.now().strftime("%Y-%m-%d"),
            weights={},
            metrics=None,
            flags=[RiskFlag(
                flag_type="data",
                severity="critical",
                message="Unable to compute portfolio weights from holdings",
            )],
        )

    available_tickers = list(weights.keys())
    port_returns = _compute_portfolio_returns(weights, prices)

    basic = _compute_basic_metrics(port_returns)

    beta_tracking = _compute_beta_tracking(port_returns, benchmark_ticker, prices)

    # Tail risk
    sortino = None

    if len(port_returns) >= 60:
        try:
            from backend.services.tail_risk import compute_tail_risk_metrics
            tail = compute_tail_risk_metrics(port_returns.values)
            sortino = tail.get("sortino_ratio")
            if sortino is not None:
                sortino = round(sortino, 4)
        except Exception as e:
            logger.warning("Tail risk computation failed: %s", e)

    # Max drawdown — computed directly from cumulative returns
    max_dd = 0.0
    max_dd_duration = None
    if len(port_returns) >= 20:
        cum = (1 + port_returns).cumprod()
        peak = cum.cummax()
        dd_series = cum / peak - 1
        max_dd = round(float(dd_series.min()), 6)

        # Duration: longest streak below previous peak
        in_dd = dd_series < 0
        if in_dd.any():
            groups = (~in_dd).cumsum()
            dd_lengths = in_dd.groupby(groups).sum()
            if len(dd_lengths) > 0:
                max_dd_duration = int(dd_lengths.max())

    # Factor exposure
    sector_exposure: dict[str, float] = {}
    factor_exposure: dict[str, float] = {}
    try:
        from backend.services.factor_model import decompose_portfolio
        factor_result = decompose_portfolio(weights)
        if factor_result:
            factor_exposure = factor_result.get("portfolio_factors", {})
    except Exception as e:
        logger.warning("Factor decomposition failed: %s", e)

    # Sector exposure from weights
    sector_map = _get_sector_map()
    for ticker, weight in weights.items():
        sector = sector_map.get(ticker, "Other")
        sector_exposure[sector] = round(
            sector_exposure.get(sector, 0.0) + weight, 4
        )

    metrics = MetricPack(
        total_return=basic["total_return"],
        annualized_return=basic["annualized_return"],
        annualized_volatility=basic["annualized_volatility"],
        sharpe_ratio=basic["sharpe_ratio"],
        sortino_ratio=sortino,
        max_drawdown=max_dd,
        max_drawdown_duration_days=max_dd_duration,
        beta_vs_spy=beta_tracking["beta_vs_spy"],
        tracking_error_vs_spy=beta_tracking["tracking_error_vs_spy"],
        information_ratio_vs_spy=beta_tracking["information_ratio_vs_spy"],
        sector_exposure=sector_exposure,
        factor_exposure=factor_exposure,
    )

    # Risk flags
    beta_map = _compute_beta_map(available_tickers, prices, factor_exposure)

    flags = compute_concentration_flags(weights, sector_map, beta_map)

    # Correlation clusters
    asset_returns = prices[available_tickers].pct_change().dropna()
    clusters = compute_correlation_clusters(asset_returns)
    for cluster in clusters:
        flags.append(RiskFlag(
            flag_type="correlation",
            severity="warning",
            message=(
                f"High correlation cluster ({cluster['avg_correlation']:.0%} avg): "
                + ", ".join(cluster["tickers"])
            ),
            details=cluster,
        ))

    return SnapshotResponse(
        portfolio_id="real",
        date=datetime.now().strftime("%Y-%m-%d"),
        weights={t: round(w, 6) for t, w in weights.items()},
        metrics=metrics,
        flags=flags,
    )
