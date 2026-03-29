"""
Aegis Finance — Unified Data Fetcher
======================================

Fetches market data from Yahoo Finance and macroeconomic data from FRED.
Merged from V7's separate fetchers.py and fred_fetcher.py into one class.

Usage:
    from backend.services.data_fetcher import DataFetcher

    fetcher = DataFetcher()
    data, sector_data = fetcher.fetch_market_data()
    fred_data = fetcher.fetch_fred_data()
"""

import math
import logging
import threading
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import yfinance as yf

from backend.config import config, api_keys
from backend.cache import cached

logger = logging.getLogger(__name__)

# yfinance is NOT thread-safe — concurrent downloads corrupt DataFrames.
# Serialize all yfinance calls through a lock.
_yf_lock = threading.Lock()


# ── Safe Ticker Fetch ────────────────────────────────────────────────────────


def fetch_safe(
    ticker: str, start: str, end: str, name: str = ""
) -> Optional[pd.Series]:
    """
    Safely download a single ticker's closing prices from Yahoo Finance.

    Returns:
        pd.Series of closing prices (forward-filled), or None if fetch fails.
    """
    try:
        with _yf_lock:
            df = yf.download(ticker, start=start, end=end, progress=False)
        if df.empty:
            logger.warning("No data for %s", name or ticker)
            return None
        if isinstance(df.columns, pd.MultiIndex):
            series = df["Close"].iloc[:, 0]
        else:
            series = df["Close"]
        return series.ffill()
    except Exception as e:
        logger.warning("Failed to fetch %s: %s", name or ticker, e)
        return None


def _add_treasury(
    data: pd.DataFrame,
    ticker: str,
    column: str,
    start: str,
    end: str,
    name: str,
) -> pd.DataFrame:
    """Fetch a Treasury yield and convert from percentage points to decimal.

    Yahoo Finance reports yields as percentage points (e.g., 4.09 = 4.09%).
    We divide by 100 to get decimal form (0.0409).
    """
    series = fetch_safe(ticker, start, end, name)
    if series is not None:
        data[column] = series / 100
    return data


# ── DataFetcher Class ────────────────────────────────────────────────────────


class DataFetcher:
    """Unified data fetcher for Yahoo Finance + FRED."""

    @cached(ttl=3600)
    def fetch_market_data(self) -> tuple[pd.DataFrame, dict[str, pd.Series]]:
        """
        Fetch all market data from Yahoo Finance.

        Returns:
            data: DataFrame with all market series indexed by date
            sector_data: dict mapping sector names to price series
        """
        logger.info("Fetching market data from Yahoo Finance...")

        tickers = config["data"]["tickers"]
        start = config["data"]["training_start"]
        end = (datetime.today() + timedelta(days=1)).strftime("%Y-%m-%d")

        # Core Index
        sp500 = fetch_safe(tickers["index"], start, end, "S&P 500")
        if sp500 is None:
            raise RuntimeError(
                "Cannot fetch S&P 500 data. Check internet connection."
            )
        data = pd.DataFrame({"SP500": sp500})

        # Volatility
        vix = fetch_safe(tickers["vix"], "1990-01-02", end, "VIX")
        if vix is not None:
            data["VIX"] = vix

        # Treasuries (divide by 100 for decimal)
        data = _add_treasury(
            data, tickers["treasury_10y"], "T10Y", start, end, "10Y Treasury"
        )
        data = _add_treasury(
            data, tickers["treasury_3m"], "T3M", "1976-01-02", end, "13-Week T-Bill"
        )
        data = _add_treasury(
            data, tickers["treasury_30y"], "T30Y", "1977-02-18", end, "30Y Treasury"
        )

        # Credit Spreads
        hyg = fetch_safe(tickers["high_yield"], "2007-04-04", end, "High Yield Bonds")
        if hyg is not None:
            data["HYG"] = hyg
        lqd = fetch_safe(tickers["inv_grade"], "2002-07-22", end, "Inv Grade Bonds")
        if lqd is not None:
            data["LQD"] = lqd

        # Alternative Assets
        gold = fetch_safe(tickers["gold"], "2000-01-01", end, "Gold")
        if gold is not None:
            data["Gold"] = gold

        # Breadth Indicators
        nasdaq = fetch_safe(tickers["nasdaq"], "1971-02-05", end, "NASDAQ")
        if nasdaq is not None:
            data["NASDAQ"] = nasdaq
        russell = fetch_safe(tickers["russell"], "1987-09-10", end, "Russell 2000")
        if russell is not None:
            data["Russell"] = russell

        # Options Market Signals
        if "vix3m" in tickers:
            vix3m = fetch_safe(tickers["vix3m"], "2008-01-03", end, "VIX3M (90-day)")
            if vix3m is not None:
                data["VIX3M"] = vix3m

        if "skew" in tickers:
            skew = fetch_safe(tickers["skew"], "1990-01-02", end, "CBOE SKEW")
            if skew is not None:
                data["SKEW"] = skew

        # Sector ETFs
        sector_tickers = config["data"]["sectors"]
        sector_start = config["data"]["sector_start"]
        sector_data: dict[str, pd.Series] = {}

        for name, tick in sector_tickers.items():
            s_data = fetch_safe(tick, sector_start, end, name)
            if s_data is not None:
                data[f"Sector_{name}"] = s_data
                sector_data[name] = s_data

        # Clean up
        data = data.ffill().bfill()

        logger.info(
            "Fetched %d observations, %d series, range %s to %s",
            len(data),
            len(data.columns),
            data.index[0].date(),
            data.index[-1].date(),
        )

        return data, sector_data

    @cached(ttl=86400)
    def fetch_fred_data(self) -> dict[str, pd.Series]:
        """Fetch all configured FRED series.

        Returns:
            dict mapping series name to pd.Series of values
        """
        if not api_keys.has("fred"):
            logger.warning("FRED_API_KEY not set, skipping FRED data")
            return {}

        try:
            from fredapi import Fred
        except ImportError:
            logger.warning("fredapi not installed, skipping FRED data")
            return {}

        logger.info("Fetching macroeconomic indicators from FRED...")
        fred = Fred(api_key=api_keys.fred)

        series_ids = config["data"]["fred_series"]
        results: dict[str, pd.Series] = {}

        for name, series_id in series_ids.items():
            try:
                data = fred.get_series(series_id)
                if data is not None and len(data) > 0:
                    results[name] = data.dropna()
                    latest = float(data.dropna().iloc[-1])
                    logger.info("  %s (%s): %.2f", name, series_id, latest)
            except Exception as e:
                logger.warning("Failed to fetch %s (%s): %s", name, series_id, e)

        logger.info(
            "Loaded %d/%d FRED series", len(results), len(series_ids)
        )
        return results

    def get_recession_probability(self, fred_data: dict) -> float:
        """Compute blended recession probability from FRED indicators.

        Uses three signals:
            1. Yield curve spread (T10Y3M) - inverted = recession warning
            2. Sahm Rule - triggers at +0.50 percentage points
            3. Chauvet-Piger smoothed probability - direct model output

        Returns:
            float between 0 and 1
        """
        signals: list[tuple[str, float, float]] = []

        if "yield_spread" in fred_data:
            spread = float(fred_data["yield_spread"].iloc[-1])
            yield_prob = 1 / (1 + _exp_safe(2.0 * spread))
            signals.append(("yield_curve", yield_prob, 0.35))

        if "sahm_rule" in fred_data:
            sahm = float(fred_data["sahm_rule"].iloc[-1])
            if sahm >= 0.50:
                sahm_prob = 0.90
            else:
                sahm_prob = sahm / 0.50 * 0.50
            signals.append(("sahm_rule", sahm_prob, 0.30))

        if "recession_prob" in fred_data:
            cp = float(fred_data["recession_prob"].iloc[-1])
            signals.append(("chauvet_piger", cp / 100.0, 0.35))

        if not signals:
            return 0.15  # Default base rate

        total_weight = sum(w for _, _, w in signals)
        blended = sum(prob * w for _, prob, w in signals) / total_weight

        return float(min(0.95, max(0.02, blended)))

    def get_macro_features(self, fred_data: dict) -> dict:
        """Extract current macro features for scenario weighting."""
        features: dict[str, float] = {}

        key_map = {
            "yield_spread": "yield_spread",
            "sahm_rule": "sahm_rule",
            "unemployment": "unemployment",
            "fed_funds": "fed_funds",
            "consumer_sentiment": "consumer_sentiment",
            "vix_fred": "vix",
            "hy_oas": "hy_oas",
            "initial_claims": "initial_claims",
            "nfci": "nfci",
            "lei": "lei",
        }

        for fred_key, feature_name in key_map.items():
            if fred_key in fred_data and len(fred_data[fred_key]) > 0:
                features[feature_name] = float(fred_data[fred_key].iloc[-1])

        return features

    def get_sp500_price(self) -> Optional[float]:
        """Get the latest S&P 500 closing price."""
        ticker = config["data"]["tickers"]["index"]
        end = (datetime.today() + timedelta(days=1)).strftime("%Y-%m-%d")
        start = (datetime.today() - timedelta(days=10)).strftime("%Y-%m-%d")
        series = fetch_safe(ticker, start, end, "S&P 500")
        if series is not None and len(series) > 0:
            return float(series.iloc[-1])
        return None

    def get_vix(self) -> Optional[float]:
        """Get the latest VIX value."""
        ticker = config["data"]["tickers"]["vix"]
        end = (datetime.today() + timedelta(days=1)).strftime("%Y-%m-%d")
        start = (datetime.today() - timedelta(days=10)).strftime("%Y-%m-%d")
        series = fetch_safe(ticker, start, end, "VIX")
        if series is not None and len(series) > 0:
            return float(series.iloc[-1])
        return None


def _exp_safe(x: float) -> float:
    """Safe exponential that avoids overflow."""
    return math.exp(min(700, max(-700, x)))
