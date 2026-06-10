"""
Aegis Finance — Walk-Forward Replay Engine
=============================================

Replays reference portfolio rules over historical data with zero look-ahead
leakage. The MarketDataAtTimestamp wrapper is the sole defense against
future-data contamination.

Algorithm:
  1. Pre-fetch all data for [start - 2y, end] (need lookback for covariance)
  2. Create MarketDataAtTimestamp wrapper
  3. For each rebalance check date:
     a. Slice data to as_of(check_date) — ONLY past data
     b. Compute crash probability from sliced features
     c. Run rules.compute_target_weights() with sliced prices
     d. Check rebalance trigger
     e. If yes: apply crash overlay, enforce limits, compute trades
     f. Record weights, trades, metrics
  4. Compute daily returns between check dates using actual next-period prices
  5. Aggregate into equity curve, drawdowns, Sharpe, etc.

Usage:
    engine = ReplayEngine()
    result = engine.run("conservative", "2021-01-01", "2025-12-31")
"""

import logging
from datetime import date, timedelta

import numpy as np
import pandas as pd

from backend.config import paper_portfolios
from backend.schemas.portfolio_intelligence import ReplayResult, MetricPack
from backend.services.portfolio_intelligence.market_data_wrapper import MarketDataAtTimestamp
from backend.services.portfolio_intelligence.nav import (
    nav_series,
    weights_to_shares,
)
from backend.services.portfolio_intelligence.rebalancer import compute_trades, estimate_turnover
from backend.services.portfolio_intelligence.rules import (
    apply_crash_overlay,
    compute_target_weights,
    enforce_position_limits,
    lane_sector_map,
    should_rebalance,
)

logger = logging.getLogger(__name__)

_TRADING_DAYS_PER_YEAR = 252

_shared_predictor = None
_shared_predictor_loaded = False


def _get_shared_predictor():
    """Lazy-load the crash model once per process, not per check date."""
    global _shared_predictor, _shared_predictor_loaded
    if _shared_predictor_loaded:
        return _shared_predictor
    _shared_predictor_loaded = True
    try:
        from backend.config import MODEL_DIR
        from backend.services.crash_model import CrashPredictor
        p = CrashPredictor()
        model_path = MODEL_DIR / "crash_model.pkl"
        if model_path.exists():
            try:
                p.load_model(str(model_path))
            except Exception as e:
                logger.warning("Crash model load failed: %s", e)
        _shared_predictor = p
    except Exception as e:
        logger.warning("Crash predictor init failed: %s", e)
        _shared_predictor = None
    return _shared_predictor


def _generate_check_dates(
    start: date,
    end: date,
    frequency: str,
) -> list[date]:
    """Generate rebalance check dates between start and end."""
    dates = []
    current = start
    if frequency == "weekly":
        step = timedelta(days=7)
    elif frequency == "monthly":
        step = timedelta(days=28)
    else:
        step = timedelta(days=28)

    while current <= end:
        dates.append(current)
        current += step

    return dates


def _compute_daily_returns(
    weights: dict[str, float],
    price_df: pd.DataFrame,
    start_date: date,
    end_date: date,
) -> pd.Series:
    """Compute portfolio daily returns between two dates given fixed weights.

    Uses actual prices (not as-of sliced) because this measures what
    WOULD have happened — this is correct for backtest performance.
    """
    ts_start = pd.Timestamp(start_date)
    ts_end = pd.Timestamp(end_date)
    sliced = price_df.loc[ts_start:ts_end]

    if sliced.empty or len(sliced) < 2:
        return pd.Series(dtype=float)

    available = [t for t in weights if t in sliced.columns]
    if not available:
        return pd.Series(dtype=float)

    returns = sliced[available].pct_change().dropna()
    if returns.empty:
        return pd.Series(dtype=float)

    w = np.array([weights.get(t, 0.0) for t in available])
    w_total = w.sum()
    if w_total > 0:
        w = w / w_total

    port_returns = returns.values @ w
    return pd.Series(port_returns, index=returns.index)


def _drift_weights(
    weights: dict[str, float],
    price_df: pd.DataFrame,
    start_date: date,
    end_date: date,
) -> dict[str, float]:
    """Drift weights forward based on actual price movements between two dates."""
    if not weights or price_df.empty:
        return dict(weights)

    ts_start = pd.Timestamp(start_date)
    ts_end = pd.Timestamp(end_date)

    drifted = {}
    for ticker, w in weights.items():
        if ticker not in price_df.columns or w <= 0:
            drifted[ticker] = w
            continue

        series = price_df[ticker].loc[ts_start:ts_end].dropna()
        if len(series) < 2:
            drifted[ticker] = w
            continue

        ticker_return = series.iloc[-1] / series.iloc[0] - 1
        drifted[ticker] = w * (1 + ticker_return)

    total = sum(drifted.values())
    if total > 1e-10:
        drifted = {t: v / total for t, v in drifted.items()}

    return drifted


def _prices_as_of(price_df: pd.DataFrame, as_of: date) -> dict[str, float]:
    """Last available price per ticker at or before `as_of` (no look-ahead)."""
    if price_df.empty:
        return {}
    ts = pd.Timestamp(as_of)
    out: dict[str, float] = {}
    for t in price_df.columns:
        s = price_df[t].loc[:ts].dropna()
        if not s.empty:
            out[t] = float(s.iloc[-1])
    return out


def _shares_to_weights(shares: dict[str, float], prices: dict[str, float],
                       cash: float = 0.0) -> dict[str, float]:
    """Mark a share book to weights at the given prices (for the drift trigger)."""
    vals = {t: shares[t] * prices.get(t, 0.0) for t in shares}
    total = sum(vals.values()) + cash
    if total <= 0:
        return {}
    return {t: v / total for t, v in vals.items() if v > 0}


def _compute_replay_metrics(equity_curve: pd.Series) -> MetricPack | None:
    """Compute standard metrics from an equity curve Series."""
    if equity_curve is None or len(equity_curve) < 20:
        return None

    daily_returns = equity_curve.pct_change().dropna()
    if daily_returns.empty:
        return None

    n_days = len(daily_returns)
    total_return = float(equity_curve.iloc[-1] / equity_curve.iloc[0] - 1)

    years = n_days / _TRADING_DAYS_PER_YEAR
    ann_return = float((1 + total_return) ** (1 / max(years, 0.01)) - 1) if years > 0 else 0.0
    ann_vol = float(daily_returns.std() * np.sqrt(_TRADING_DAYS_PER_YEAR))

    rf_annual = 0.04
    sharpe = float((ann_return - rf_annual) / ann_vol) if ann_vol > 1e-6 else None

    downside = daily_returns[daily_returns < 0]
    downside_vol = float(downside.std() * np.sqrt(_TRADING_DAYS_PER_YEAR)) if len(downside) > 1 else None
    sortino = float((ann_return - rf_annual) / downside_vol) if downside_vol and downside_vol > 1e-6 else None

    peak = equity_curve.cummax()
    dd = equity_curve / peak - 1
    max_dd = float(dd.min())

    dd_duration = None
    if max_dd < 0:
        in_dd = dd < 0
        if in_dd.any():
            groups = (~in_dd).cumsum()
            dd_groups = in_dd.groupby(groups).sum()
            dd_duration = int(dd_groups.max()) if not dd_groups.empty else None

    return MetricPack(
        total_return=round(total_return, 6),
        annualized_return=round(ann_return, 6),
        annualized_volatility=round(ann_vol, 6),
        sharpe_ratio=round(sharpe, 4) if sharpe is not None else None,
        sortino_ratio=round(sortino, 4) if sortino is not None else None,
        max_drawdown=round(max_dd, 6),
        max_drawdown_duration_days=dd_duration,
    )


class ReplayEngine:
    """Walk-forward replay of reference portfolio rules over historical data."""

    def __init__(self, wrapper: MarketDataAtTimestamp | None = None):
        self._wrapper = wrapper

    def _fetch_data(self, start: date, end: date) -> MarketDataAtTimestamp:
        """Fetch all required data and create the anti-leakage wrapper."""
        if self._wrapper is not None:
            return self._wrapper

        from backend.services.data_fetcher import DataFetcher

        # NOTE: fetch_market_data() takes no date args — it returns its own
        # default historical range (which spans well before any replay start),
        # and the MarketDataAtTimestamp wrapper slices it as-of each check date.
        # Earlier code computed lookback_start/fetcher_start/fetcher_end and
        # never used them (fetch_market_data has no parameters); removed to
        # avoid implying a lookback window that isn't actually honored here.
        fetcher = DataFetcher()
        data, _ = fetcher.fetch_market_data()
        fred_data = fetcher.fetch_fred_data()

        return MarketDataAtTimestamp(data, fred_data)

    def _get_crash_prob_as_of(
        self,
        wrapper: MarketDataAtTimestamp,
        dt: date,
    ) -> float | None:
        """Get crash probability using only data available as-of dt.

        Short-circuits when the crash model is untrained; otherwise we'd burn
        ~200ms per check date on a doomed CrashPredictor() + raise cycle.
        """
        predictor = _get_shared_predictor()
        if predictor is None or not getattr(predictor, "is_trained", False):
            return None

        features = wrapper.crash_features_as_of(dt)
        if features is None:
            return None

        try:
            prob = predictor.predict_proba(
                features, horizon="3m", external_features=features,
            )
            if prob is not None and len(prob) > 0:
                return float(prob[0])
        except Exception as e:
            logger.warning("Crash model failed for %s: %s", dt, e)

        return None

    def _get_ticker_universe_prices(
        self,
        wrapper: MarketDataAtTimestamp,
        lane_config: dict,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        """Fetch price data for the ticker universe."""
        from backend.services.portfolio_intelligence.rules import _get_sleeve_tickers

        universe = paper_portfolios.get("universe", {})
        sleeves = _get_sleeve_tickers(universe)
        all_tickers = sleeves["equity"] + sleeves["bond"] + sleeves["alternative"]

        from backend.services.data_fetcher import fetch_safe

        start_str = (start - timedelta(days=30)).strftime("%Y-%m-%d")
        end_str = end.strftime("%Y-%m-%d")

        price_dict = {}
        for ticker in all_tickers:
            try:
                series = fetch_safe(ticker, start_str, end_str, name=ticker)
                if series is not None and len(series) > 0:
                    price_dict[ticker] = series
            except Exception as e:
                # A silently shrunken universe makes the replay look valid
                # while computed from partial data — log every drop.
                logger.warning("Replay universe: dropping %s (fetch failed: %s)",
                               ticker, e)

        if price_dict:
            return pd.DataFrame(price_dict)
        return pd.DataFrame()

    def run(
        self,
        lane_id: str,
        start_date: str = "2021-01-01",
        end_date: str | None = None,
        initial_notional: float = 100_000.0,
        crash_prob_override: float | None = None,
        rf_daily: float = 0.0,
    ) -> ReplayResult:
        """Run walk-forward replay for a single lane.

        Args:
            lane_id: 'conservative', 'balanced', or 'aggressive'
            start_date: Replay start (YYYY-MM-DD)
            end_date: Replay end (default: today)
            initial_notional: Starting portfolio value
            crash_prob_override: Fixed crash prob for all dates (testing)
        """
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date) if end_date else date.today()

        lane_config = paper_portfolios.get(lane_id)
        if lane_config is None:
            raise ValueError(f"Unknown lane: {lane_id}")

        universe_cfg = paper_portfolios.get("universe", {})
        frequency = lane_config["rebalance_frequency"]
        drift_threshold = lane_config["rebalance_trigger_drift"]
        sector_map = lane_sector_map(universe_cfg)

        logger.info("Replay %s: %s to %s, $%s notional", lane_id, start, end, f"{initial_notional:,.0f}")

        # Fetch data
        wrapper = self._fetch_data(start, end)

        # Fetch universe prices for daily returns
        ticker_prices = self._get_ticker_universe_prices(wrapper, lane_config, start, end)

        # Generate check dates
        check_dates = _generate_check_dates(start, end, frequency)

        # State: we hold a SHARE BOOK (+ cash sleeve), not weights — the value
        # path is shares × real price via the shared nav.py engine, identical to
        # the live mark-to-market. current_weights is derived (marked) only for
        # the drift trigger.
        current_shares: dict[str, float] = {}
        current_cash: float = 0.0
        last_rebalance: date | None = None
        portfolio_value = initial_notional
        equity_curve_points: list[dict] = []
        rebalance_log: list[dict] = []
        crash_guard_activations = 0
        total_rebalances = 0
        total_turnover = 0.0
        total_cost = 0.0

        daily_values = [initial_notional]
        daily_dates = [pd.Timestamp(start)]

        for i, check_date in enumerate(check_dates):
            # Value the held book over (prev_date, check_date] via nav_series —
            # the SAME engine the live path uses (one engine, two modes).
            prev_date = check_dates[i - 1] if i > 0 else start
            if current_shares and not ticker_prices.empty:
                seg = ticker_prices.loc[
                    pd.Timestamp(prev_date):pd.Timestamp(check_date)
                ]
                # Drop the segment's first row if it's the prev check date we
                # already recorded, to avoid duplicate points.
                if len(seg) > 1 and i > 0 and seg.index[0] == pd.Timestamp(prev_date):
                    seg = seg.iloc[1:]
                if not seg.empty:
                    seg_nav = nav_series(
                        current_shares, seg, cash=current_cash, rf_daily=rf_daily,
                    )
                    for dt, v in seg_nav.items():
                        daily_values.append(float(v))
                        daily_dates.append(dt)
                    portfolio_value = float(seg_nav.iloc[-1])

            # Mark the held book to weights at current prices (for the trigger).
            prices_at_date = _prices_as_of(ticker_prices, check_date)
            current_weights = _shares_to_weights(
                current_shares, prices_at_date, current_cash,
            )

            # Compute target weights (equal-weight within sleeves today)
            target_weights = compute_target_weights(lane_config, universe_cfg)

            # Get crash probability
            if crash_prob_override is not None:
                crash_prob = crash_prob_override
            else:
                crash_prob = self._get_crash_prob_as_of(wrapper, check_date)

            # Apply crash overlay
            overlay_triggered = False
            if crash_prob is not None:
                target_weights, overlay_triggered = apply_crash_overlay(
                    target_weights, crash_prob, lane_config,
                )
                if overlay_triggered:
                    crash_guard_activations += 1

            # Enforce position limits
            target_weights = enforce_position_limits(
                target_weights,
                lane_config["max_single_name"],
                lane_config["max_sector"],
                sector_map,
            )

            # Check rebalance trigger
            trigger, reason = should_rebalance(
                current_weights,
                target_weights,
                drift_threshold,
                frequency,
                last_rebalance,
                check_date,
            )

            if trigger:
                trades, trade_cost = compute_trades(
                    current_weights, target_weights, prices_at_date,
                    portfolio_value,
                    lane_config.get("transaction_cost_bps", 5),
                    lane_config.get("slippage_bps", 1),
                )

                turnover = estimate_turnover(current_weights, target_weights)
                total_turnover += turnover
                total_cost += trade_cost

                # Transaction cost is paid out of the book, then the new target
                # is converted to a fresh share book via the shared nav engine.
                portfolio_value = max(0.0, portfolio_value - trade_cost)
                current_shares, current_cash = weights_to_shares(
                    target_weights, prices_at_date, portfolio_value,
                )

                rebalance_log.append({
                    "date": check_date.isoformat(),
                    "reason": reason,
                    "turnover": round(turnover, 4),
                    "cost": round(trade_cost, 2),
                    "crash_prob": crash_prob,
                    "overlay_armed": overlay_triggered,
                    "n_trades": len(trades),
                    "portfolio_value": round(portfolio_value, 2),
                })

                last_rebalance = check_date
                total_rebalances += 1

            equity_curve_points.append({
                "date": check_date.isoformat(),
                "value": round(portfolio_value, 2),
            })

        # Build equity curve Series for metrics
        eq_series = pd.Series(daily_values, index=pd.DatetimeIndex(daily_dates))
        eq_series = eq_series[~eq_series.index.duplicated(keep='last')]

        metrics = _compute_replay_metrics(eq_series)

        cost_bps = (total_cost / initial_notional) * 10_000 if initial_notional > 0 else 0

        logger.info(
            "Replay %s complete: %d rebalances, %.1f%% total return, "
            "%.1f%% turnover, %d crash guard activations",
            lane_id, total_rebalances,
            (portfolio_value / initial_notional - 1) * 100,
            total_turnover * 100, crash_guard_activations,
        )

        return ReplayResult(
            lane=lane_id,
            start_date=start_date,
            end_date=end.isoformat(),
            equity_curve=equity_curve_points,
            metrics=metrics,
            rebalance_log=rebalance_log,
            crash_guard_activations=crash_guard_activations,
            total_rebalances=total_rebalances,
            total_turnover=round(total_turnover, 4),
            total_cost_bps=round(cost_bps, 2),
        )
