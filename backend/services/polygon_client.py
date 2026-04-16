"""
Aegis Finance — Polygon.io Data Client
=========================================

Real-time and historical market data from Polygon.io.
Supplements yfinance with:
  - Real-time price snapshots (near-zero latency vs yfinance's 15min delay)
  - Intraday bars (1min, 5min, 15min, 1hr)
  - Previous day OHLCV (official close, not delayed)
  - Ticker details (market cap, SIC code, share count)
  - Stock splits and dividends

Free tier: 5 API calls/minute. We use aggressive caching to stay within limits.

Usage:
    from backend.services.polygon_client import PolygonClient
    client = PolygonClient()
    snapshot = client.get_snapshot("AAPL")
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from backend.config import api_keys
from backend.cache import cache_get, cache_set

logger = logging.getLogger(__name__)

try:
    from polygon import RESTClient
    HAS_POLYGON = True
except ImportError:
    HAS_POLYGON = False


class PolygonClient:
    """Thin wrapper around Polygon.io REST API with caching."""

    def __init__(self):
        self.available = HAS_POLYGON and api_keys.has("polygon")
        self._client = None
        if self.available:
            self._client = RESTClient(api_key=api_keys.polygon)

    def get_snapshot(self, ticker: str) -> Optional[dict]:
        """Get real-time price snapshot for a ticker.

        Returns dict with: price, change, change_pct, volume, vwap,
        prev_close, prev_volume, market_cap, timestamp
        """
        if not self.available:
            return None

        cache_key = f"polygon_snapshot:{ticker}"
        cached = cache_get(cache_key, 60)  # 1 min cache
        if cached is not None:
            return cached

        try:
            snapshot = self._client.get_snapshot_ticker("stocks", ticker)
            if snapshot is None:
                return None

            result = {
                "ticker": ticker,
                "price": getattr(snapshot, "last_trade", {}).get("price") if hasattr(snapshot, "last_trade") else None,
                "updated_ts": snapshot.updated / 1e9 if hasattr(snapshot, "updated") and snapshot.updated else None,
            }

            # Day data
            if hasattr(snapshot, "day") and snapshot.day:
                day = snapshot.day
                result["day"] = {
                    "open": getattr(day, "open", None),
                    "high": getattr(day, "high", None),
                    "low": getattr(day, "low", None),
                    "close": getattr(day, "close", None),
                    "volume": getattr(day, "volume", None),
                    "vwap": getattr(day, "vwap", None),
                }

            # Previous day
            if hasattr(snapshot, "prev_day") and snapshot.prev_day:
                prev = snapshot.prev_day
                result["prev_day"] = {
                    "open": getattr(prev, "open", None),
                    "high": getattr(prev, "high", None),
                    "low": getattr(prev, "low", None),
                    "close": getattr(prev, "close", None),
                    "volume": getattr(prev, "volume", None),
                    "vwap": getattr(prev, "vwap", None),
                }

            # Change
            if hasattr(snapshot, "todays_change") and snapshot.todays_change is not None:
                result["change"] = snapshot.todays_change
            if hasattr(snapshot, "todays_change_perc") and snapshot.todays_change_perc is not None:
                result["change_pct"] = snapshot.todays_change_perc

            cache_set(cache_key, result)
            return result

        except Exception as e:
            logger.warning("Polygon snapshot failed for %s: %s", ticker, e)
            return None

    def get_previous_close(self, ticker: str) -> Optional[dict]:
        """Get previous day's official OHLCV."""
        if not self.available:
            return None

        cache_key = f"polygon_prev:{ticker}"
        cached = cache_get(cache_key, 3600)  # 1hr cache (doesn't change intraday)
        if cached is not None:
            return cached

        try:
            aggs = self._client.get_previous_close_agg(ticker)
            if not aggs:
                return None
            bar = aggs[0]
            result = {
                "ticker": ticker,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
                "vwap": getattr(bar, "vwap", None),
                "date": datetime.fromtimestamp(bar.timestamp / 1000).strftime("%Y-%m-%d") if bar.timestamp else None,
            }
            cache_set(cache_key, result)
            return result
        except Exception as e:
            logger.warning("Polygon previous close failed for %s: %s", ticker, e)
            return None

    def get_ticker_details(self, ticker: str) -> Optional[dict]:
        """Get company details: name, market_cap, SIC, share count."""
        if not self.available:
            return None

        cache_key = f"polygon_details:{ticker}"
        cached = cache_get(cache_key, 86400)  # 24hr cache
        if cached is not None:
            return cached

        try:
            details = self._client.get_ticker_details(ticker)
            if details is None:
                return None

            result = {
                "ticker": ticker,
                "name": getattr(details, "name", None),
                "market_cap": getattr(details, "market_cap", None),
                "share_class_shares_outstanding": getattr(details, "share_class_shares_outstanding", None),
                "weighted_shares_outstanding": getattr(details, "weighted_shares_outstanding", None),
                "sic_code": getattr(details, "sic_code", None),
                "sic_description": getattr(details, "sic_description", None),
                "primary_exchange": getattr(details, "primary_exchange", None),
                "type": getattr(details, "type", None),
                "description": getattr(details, "description", None),
                "homepage_url": getattr(details, "homepage_url", None),
                "total_employees": getattr(details, "total_employees", None),
                "list_date": getattr(details, "list_date", None),
            }
            cache_set(cache_key, result)
            return result
        except Exception as e:
            logger.warning("Polygon details failed for %s: %s", ticker, e)
            return None

    def get_intraday_bars(
        self, ticker: str, multiplier: int = 5, timespan: str = "minute", days: int = 1,
    ) -> Optional[list]:
        """Get intraday bars (default: 5-minute bars for today).

        Args:
            ticker: Stock ticker
            multiplier: Bar size multiplier (e.g., 5 for 5-minute bars)
            timespan: "minute", "hour", "day"
            days: How many days of data

        Returns:
            List of {timestamp, open, high, low, close, volume, vwap} dicts
        """
        if not self.available:
            return None

        cache_key = f"polygon_intraday:{ticker}:{multiplier}{timespan}:{days}"
        cached = cache_get(cache_key, 300)  # 5 min cache for intraday
        if cached is not None:
            return cached

        try:
            end = datetime.now()
            start = end - timedelta(days=days)

            aggs = self._client.get_aggs(
                ticker, multiplier, timespan,
                start.strftime("%Y-%m-%d"),
                end.strftime("%Y-%m-%d"),
                limit=5000,
            )

            if not aggs:
                return None

            bars = []
            for bar in aggs:
                bars.append({
                    "timestamp": datetime.fromtimestamp(bar.timestamp / 1000).isoformat() if bar.timestamp else None,
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                    "vwap": getattr(bar, "vwap", None),
                })

            cache_set(cache_key, bars)
            return bars

        except Exception as e:
            logger.warning("Polygon intraday failed for %s: %s", ticker, e)
            return None

    def get_market_status(self) -> Optional[dict]:
        """Check if the market is currently open."""
        if not self.available:
            return None

        cache_key = "polygon_market_status"
        cached = cache_get(cache_key, 60)
        if cached is not None:
            return cached

        try:
            status = self._client.get_market_status()
            result = {
                "market": getattr(status, "market", None),
                "exchanges": {},
            }
            if hasattr(status, "exchanges") and status.exchanges:
                for name, state in status.exchanges.items():
                    result["exchanges"][name] = state

            cache_set(cache_key, result)
            return result
        except Exception as e:
            logger.warning("Polygon market status failed: %s", e)
            return None
