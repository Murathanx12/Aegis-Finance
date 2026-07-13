"""
Aegis Finance — Unified Data Fetcher (Optimized)
==================================================

Fetches market data from Yahoo Finance and macroeconomic data from FRED.
Optimized with batch Yahoo downloads and parallel FRED fetching.

Usage:
    from backend.services.data_fetcher import DataFetcher

    fetcher = DataFetcher()
    data, sector_data = fetcher.fetch_market_data()
    fred_data = fetcher.fetch_fred_data()
"""

import math
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import yfinance as yf

from backend.config import config, api_keys
from backend.cache import cached, retry_with_backoff, cache_get, cache_set, cache_peek
from backend.services.providers import registry as provider_registry
from backend.services.providers.base import EquitySnapshot

logger = logging.getLogger(__name__)

# yfinance is NOT thread-safe — concurrent downloads corrupt DataFrames.
# Serialize all yfinance calls through a lock.
_yf_lock = threading.Lock()


# ── Shared per-ticker fetch (rate-limit aware) ───────────────────────────────
#
# The stock page fans out to many services (analyzer, liquidity, drawdown,
# options IV-rank, news) that each used to make their OWN yf.Ticker() call for
# the SAME symbol — 5-6 uncached history fetches per page view, which is what
# tripped Yahoo's per-IP limiter in prod (429 storms → spurious 404s).
# All per-ticker history/info reads now go through ONE canonical fetch:
# a single 10y history per ticker per 15 min, sliced to the requested period.


class RateLimited(Exception):
    """Yahoo Finance is throttling this process — NOT an invalid ticker.

    Callers must never translate this into "ticker not found"; routers
    should surface it as 503 + Retry-After, not 404.
    """


_HIST_TTL = 900          # one real history fetch per ticker per 15 min
_INFO_TTL = 3600
_STALE_OK = 24 * 3600    # prefer a stale copy over failing while throttled
_RL_BREAKER_KEY = "yf:rate_limit_breaker"
_RL_COOLDOWN = 90        # after a 429, stop hitting Yahoo entirely for this long

# Requested period → trading-day row count sliced off the canonical 10y frame.
_PERIOD_ROWS = {
    "1d": 1, "5d": 5, "1mo": 22, "3mo": 66, "6mo": 126,
    "1y": 252, "2y": 504, "5y": 1260, "10y": None, "max": None,
}


def _is_rate_limit(exc: Exception) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    return "too many requests" in text or "rate limit" in text or "429" in text


def _rl_breaker_active() -> bool:
    return cache_get(_RL_BREAKER_KEY, _RL_COOLDOWN) is not None


def _trip_rl_breaker() -> None:
    cache_set(_RL_BREAKER_KEY, True)
    logger.warning("Yahoo rate limit hit — pausing all yfinance calls for %ds",
                   _RL_COOLDOWN)


def fetch_ticker_history(ticker: str, period: str = "5y"):
    """Shared OHLCV history for one ticker, sliced to `period`.

    Returns a DataFrame copy, or None when the symbol has no data (unknown /
    delisted). Raises RateLimited when Yahoo is throttling AND no cached copy
    (fresh or stale) exists — so callers can distinguish "bad ticker" from
    "provider throttled".
    """
    ticker = ticker.upper()
    key = f"tkr:hist10y:{ticker}"
    full = cache_get(key, _HIST_TTL)

    if full is None:
        stale, _age = cache_peek(key, _STALE_OK)
        if _rl_breaker_active():
            if stale is None:
                raise RateLimited("Yahoo Finance throttling (cooldown active)")
            full = stale
        else:
            try:
                with _yf_lock:
                    full = yf.Ticker(ticker).history(period="10y")
            except Exception as e:
                if _is_rate_limit(e):
                    _trip_rl_breaker()
                    if stale is not None:
                        logger.warning("%s: serving stale history (Yahoo throttling)", ticker)
                        full = stale
                    else:
                        raise RateLimited(str(e)) from e
                else:
                    logger.warning("%s: history fetch failed — %s", ticker, e)
                    return None
            if full is None or full.empty:
                return None
            cache_set(key, full)

    rows = _PERIOD_ROWS.get(period)
    return (full if rows is None else full.iloc[-rows:]).copy()


def fetch_ticker_info(ticker: str) -> dict:
    """Shared yf .info for one ticker. Never raises — info is enrichment,
    every caller has defaults. Returns {} on any failure."""
    ticker = ticker.upper()
    key = f"tkr:info:{ticker}"
    hit = cache_get(key, _INFO_TTL)
    if hit is not None:
        return hit

    stale, _age = cache_peek(key, _STALE_OK)
    if _rl_breaker_active():
        return stale or {}
    try:
        with _yf_lock:
            info = yf.Ticker(ticker).info or {}
    except Exception as e:
        if _is_rate_limit(e):
            _trip_rl_breaker()
        else:
            logger.warning("%s: info fetch failed — %s", ticker, e)
        return stale or {}
    if info:
        cache_set(key, info)
    return info


# ── Safe Ticker Fetch ────────────────────────────────────────────────────────


def fetch_safe(
    ticker: str, start: str, end: str, name: str = ""
) -> Optional[pd.Series]:
    """
    Safely download a single ticker's closing prices from Yahoo Finance.
    Retries up to 3 times with exponential backoff on transient failures.

    Returns:
        pd.Series of closing prices (forward-filled), or None if fetch fails.
    """
    try:
        series = _fetch_yahoo(ticker, start, end, name)
        return series
    except Exception as e:
        logger.warning("Failed to fetch %s after retries: %s", name or ticker, e)
        return None


@retry_with_backoff(max_retries=3, base_delay=1.0, max_delay=15.0)
def _fetch_yahoo(
    ticker: str, start: str, end: str, name: str = ""
) -> Optional[pd.Series]:
    """Internal Yahoo fetch with retry."""
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


def _fetch_batch_yahoo(
    tickers: list[str], start: str, end: str
) -> dict[str, pd.Series]:
    """Fetch multiple tickers in a single yf.download() call.

    Uses group_by='ticker' to get per-ticker DataFrames, then extracts Close.
    Much faster than sequential downloads (~10s vs ~50s for 12 tickers).
    """
    if not tickers:
        return {}

    try:
        with _yf_lock:
            df = yf.download(tickers, start=start, end=end, progress=False, group_by="ticker")

        if df.empty:
            logger.warning("Batch download returned empty for %d tickers", len(tickers))
            return {}

        results = {}
        if len(tickers) == 1:
            # Single ticker: no MultiIndex on columns
            tick = tickers[0]
            if isinstance(df.columns, pd.MultiIndex):
                series = df["Close"].iloc[:, 0]
            else:
                series = df["Close"] if "Close" in df.columns else None
            if series is not None and not series.empty:
                results[tick] = series.ffill()
        else:
            # Multiple tickers: columns are MultiIndex (ticker, field)
            for tick in tickers:
                try:
                    if tick in df.columns.get_level_values(0):
                        close = df[tick]["Close"]
                        if close is not None and not close.dropna().empty:
                            results[tick] = close.ffill()
                except Exception as e:
                    logger.debug("Batch extract failed for %s: %s", tick, e)

        logger.info("Batch fetched %d/%d tickers", len(results), len(tickers))
        _record_batch_outcome(len(results), len(tickers))
        return results

    except Exception as e:
        logger.warning("Batch download failed, falling back to sequential: %s", e)
        # Fallback: fetch individually
        results = {}
        for tick in tickers:
            s = fetch_safe(tick, start, end, tick)
            if s is not None:
                results[tick] = s
        _record_batch_outcome(len(results), len(tickers))
        return results


def _record_batch_outcome(fetched: int, requested: int) -> None:
    """Feed the /api/health/full source-health counters (never raises)."""
    try:
        from backend.observability import record_yfinance_batch
        record_yfinance_batch(fetched, requested)
    except Exception:
        pass


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
        Fetch all market data from Yahoo Finance using batch downloads.

        Returns:
            data: DataFrame with all market series indexed by date
            sector_data: dict mapping sector names to price series
        """
        logger.info("Fetching market data from Yahoo Finance (batch mode)...")

        tickers_cfg = config["data"]["tickers"]
        start = config["data"]["training_start"]
        end = (datetime.today() + timedelta(days=1)).strftime("%Y-%m-%d")

        # ── Batch 1: Market tickers ──────────────────────────────────
        market_tickers = [
            tickers_cfg["index"],      # ^GSPC
            tickers_cfg["vix"],        # ^VIX
            tickers_cfg["treasury_10y"],  # ^TNX
            tickers_cfg["treasury_3m"],   # ^IRX
            tickers_cfg["treasury_30y"],  # ^TYX
            tickers_cfg["high_yield"],    # HYG
            tickers_cfg["inv_grade"],     # LQD
            tickers_cfg["gold"],          # GC=F
            tickers_cfg["nasdaq"],        # ^IXIC
            tickers_cfg["russell"],       # ^RUT
        ]
        if "vix3m" in tickers_cfg:
            market_tickers.append(tickers_cfg["vix3m"])
        if "skew" in tickers_cfg:
            market_tickers.append(tickers_cfg["skew"])

        market_batch = _fetch_batch_yahoo(market_tickers, start, end)

        # Build DataFrame from batch results
        sp500_tick = tickers_cfg["index"]
        if sp500_tick not in market_batch:
            raise RuntimeError("Cannot fetch S&P 500 data. Check internet connection.")

        data = pd.DataFrame({"SP500": market_batch[sp500_tick]})

        # Map batch results to named columns
        ticker_to_col = {
            tickers_cfg["vix"]: "VIX",
            tickers_cfg["high_yield"]: "HYG",
            tickers_cfg["inv_grade"]: "LQD",
            tickers_cfg["gold"]: "Gold",
            tickers_cfg["nasdaq"]: "NASDAQ",
            tickers_cfg["russell"]: "Russell",
        }
        if "vix3m" in tickers_cfg:
            ticker_to_col[tickers_cfg["vix3m"]] = "VIX3M"
        if "skew" in tickers_cfg:
            ticker_to_col[tickers_cfg["skew"]] = "SKEW"

        for tick, col in ticker_to_col.items():
            if tick in market_batch:
                data[col] = market_batch[tick]

        # Treasuries: divide by 100 for decimal form
        treasury_map = {
            tickers_cfg["treasury_10y"]: "T10Y",
            tickers_cfg["treasury_3m"]: "T3M",
            tickers_cfg["treasury_30y"]: "T30Y",
        }
        for tick, col in treasury_map.items():
            if tick in market_batch:
                data[col] = market_batch[tick] / 100

        # ── Batch 2: Sector ETFs ─────────────────────────────────────
        sector_tickers = config["data"]["sectors"]
        sector_start = config["data"]["sector_start"]
        sector_tick_list = list(sector_tickers.values())

        sector_batch = _fetch_batch_yahoo(sector_tick_list, sector_start, end)

        sector_data: dict[str, pd.Series] = {}
        for name, tick in sector_tickers.items():
            if tick in sector_batch:
                data[f"Sector_{name}"] = sector_batch[tick]
                sector_data[name] = sector_batch[tick]

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
        """Fetch all configured FRED series using parallel threads.

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

        logger.info("Fetching macroeconomic indicators from FRED (parallel)...")
        fred = Fred(api_key=api_keys.fred)

        series_ids = config["data"]["fred_series"]
        results: dict[str, pd.Series] = {}

        def _fetch_one(name: str, series_id: str) -> tuple[str, Optional[pd.Series]]:
            try:
                data = fred.get_series(series_id)
                if data is not None and len(data) > 0:
                    return name, data.dropna()
            except Exception as e:
                logger.warning("Failed to fetch %s (%s): %s", name, series_id, e)
            return name, None

        # Parallel fetch with ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(_fetch_one, name, sid): name
                for name, sid in series_ids.items()
            }
            for future in as_completed(futures):
                name, series = future.result()
                if series is not None:
                    results[name] = series
                    latest = float(series.iloc[-1])
                    logger.info("  %s: %.2f", name, latest)

        logger.info(
            "Loaded %d/%d FRED series", len(results), len(series_ids)
        )
        try:
            from backend.observability import record_fred_fetch
            failed = [n for n in series_ids if n not in results]
            record_fred_fetch(list(results.keys()), failed)
        except Exception:
            pass
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
        """Get the latest S&P 500 closing price (tries real-time providers first)."""
        ticker = config["data"]["tickers"]["index"]
        snap = get_snapshot(ticker)
        if snap is not None and snap.price is not None:
            return float(snap.price)
        end = (datetime.today() + timedelta(days=1)).strftime("%Y-%m-%d")
        start = (datetime.today() - timedelta(days=10)).strftime("%Y-%m-%d")
        series = fetch_safe(ticker, start, end, "S&P 500")
        if series is not None and len(series) > 0:
            return float(series.iloc[-1])
        return None

    def get_vix(self) -> Optional[float]:
        """Get the latest VIX value (tries real-time providers first)."""
        ticker = config["data"]["tickers"]["vix"]
        snap = get_snapshot(ticker)
        if snap is not None and snap.price is not None:
            return float(snap.price)
        end = (datetime.today() + timedelta(days=1)).strftime("%Y-%m-%d")
        start = (datetime.today() - timedelta(days=10)).strftime("%Y-%m-%d")
        series = fetch_safe(ticker, start, end, "VIX")
        if series is not None and len(series) > 0:
            return float(series.iloc[-1])
        return None


def get_snapshot(ticker: str) -> Optional[EquitySnapshot]:
    """Fetch a live equity snapshot from the best available provider.

    Order: Finnhub (real-time) → Polygon (real-time) → yfinance (15-min) → FMP.
    Returns None if no provider can serve the ticker.
    """
    try:
        return provider_registry.get_equity_snapshot(ticker)
    except Exception as e:
        logger.debug("Snapshot fetch failed for %s: %s", ticker, e)
        return None


def _exp_safe(x: float) -> float:
    """Safe exponential that avoids overflow."""
    return math.exp(min(700, max(-700, x)))
