"""
Aegis Finance — Master Configuration
======================================

Single source of truth for all engine parameters.
Converted from V7 engine_config.yaml into a pure Python module.

Usage:
    from backend.config import config, api_keys
    from backend.config import get_institutional_return, get_forecast_days, get_scenario_configs
"""

import os
from pathlib import Path
from dataclasses import dataclass

from dotenv import load_dotenv

# ── Project root ──────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.parent
BACKEND_DIR = Path(__file__).parent
MODEL_DIR = BACKEND_DIR / "models"
load_dotenv(PROJECT_ROOT / ".env")


# ── API Keys ──────────────────────────────────────────────────────────────────


@dataclass
class APIKeys:
    """API keys loaded from .env file."""

    fred: str = ""
    finnhub: str = ""
    fmp: str = ""

    @classmethod
    def from_env(cls) -> "APIKeys":
        return cls(
            fred=os.getenv("FRED_API_KEY", ""),
            finnhub=os.getenv("FINNHUB_API_KEY", ""),
            fmp=os.getenv("FMP_API_KEY", ""),
        )

    def has(self, key: str) -> bool:
        """Check if a key is set and not a placeholder."""
        val = getattr(self, key, "")
        return bool(val) and val != "" and "placeholder" not in val.lower()


api_keys: APIKeys = APIKeys.from_env()


# ── Master Configuration ─────────────────────────────────────────────────────

config: dict = {
    # ── DATA SETTINGS ────────────────────────────────────────────────────
    "data": {
        "training_start": "1990-01-01",
        "backtest_start": "2000-01-01",
        "sector_start": "1998-01-01",
        # Yahoo Finance tickers
        "tickers": {
            "index": "^GSPC",           # S&P 500
            "vix": "^VIX",              # CBOE Volatility Index
            "treasury_10y": "^TNX",     # 10-Year Treasury Yield
            "treasury_3m": "^IRX",      # 13-Week T-Bill (3-month proxy)
            "treasury_30y": "^TYX",     # 30-Year Treasury Yield
            "high_yield": "HYG",        # High Yield Corporate Bond ETF
            "inv_grade": "LQD",         # Investment Grade Corporate Bond ETF
            "gold": "GC=F",             # Gold Futures
            "nasdaq": "^IXIC",          # NASDAQ Composite
            "russell": "^RUT",          # Russell 2000 Small Cap
            "vix3m": "^VIX3M",          # 90-day VIX (for term structure slope)
            "skew": "^SKEW",            # CBOE Tail Risk / SKEW Index
        },
        # Sector ETFs (name -> ticker)
        "sectors": {
            "Technology": "XLK",
            "Healthcare": "XLV",
            "Financials": "XLF",
            "Energy": "XLE",
            "Consumer Disc.": "XLY",
            "Consumer Staples": "XLP",
            "Industrials": "XLI",
            "Utilities": "XLU",
            "Real Estate": "XLRE",
            "Materials": "XLB",
            "Communications": "XLC",
        },
        # FRED series IDs (22 series including leading indicators ICSA, NFCI)
        "fred_series": {
            "yield_spread": "T10Y3M",           # 10Y-3M Treasury spread (recession predictor)
            "sahm_rule": "SAHMREALTIME",         # Sahm Rule recession indicator
            "recession_prob": "RECPROUSM156N",   # Chauvet-Piger smoothed recession probability
            "unemployment": "UNRATE",            # Unemployment rate
            "cpi": "CPIAUCSL",                   # Consumer Price Index
            "fed_funds": "FEDFUNDS",             # Federal Funds Rate
            "consumer_sentiment": "UMCSENT",     # U of Michigan Consumer Sentiment
            "vix_fred": "VIXCLS",                # VIX (FRED version, longer history)
            "hy_oas": "BAMLH0A0HYM2",           # High Yield OAS spread
            "ig_oas": "BAMLC0A0CM",             # Investment Grade OAS spread
            "gpr_world": "GPRH",                 # Geopolitical Risk Index
            "consumer_credit": "TOTALSL",        # Total consumer credit outstanding
            "tips_10y": "DFII10",                # 10Y TIPS real yield
            "margin_credit": "BOGZ1FL663067003Q",  # Security credit (margin debt proxy)
            "mfg_employment": "MANEMP",          # Manufacturing employment
            "industrial_prod": "INDPRO",         # Industrial production index
            "business_loans": "BUSLOANS",        # C&I loans outstanding
            "lei": "USSLIND",                    # Leading Economic Index
            "sloos_ci": "DRTSCILM",             # Senior Loan Officer Survey: C&I tightening
            "sloos_cc": "DRTSCLCC",             # Senior Loan Officer Survey: CC tightening
            "initial_claims": "ICSA",            # Initial jobless claims (leading, weekly)
            "initial_claims_4wk": "IC4WSA",      # 4-week avg initial claims (smoother leading)
            "nfci": "NFCI",                      # Chicago Fed NFCI (leading)
        },
    },

    # ── ML SETTINGS ──────────────────────────────────────────────────────
    "ml": {
        "crash_base_rate_fallback": 0.12,
        "purge_gaps": {
            "3m": 70,
            "6m": 140,
            "12m": 265,
        },
        # Purged CV settings (Phase 1.1)
        "purged_cv": {
            "n_splits": 5,
            "embargo_days": {"3m": 21, "6m": 63, "12m": 126},
        },
        # Walk-forward settings (Phase 1.2)
        "walk_forward": {
            "holdout_years": 2,
            "step_days": 126,
            "bootstrap_n": 1000,
        },
        # Sample uniqueness weighting (Phase 1.5)
        "sample_uniqueness": True,
        # Drift detection (Phase 4.4)
        "drift": {
            "psi_threshold": 0.2,
            "ks_p_threshold": 0.01,
            "n_bins": 10,
        },
        # Calibration output bounds (Phase 5.1)
        "calibration": {
            "prob_floor": 0.001,       # min crash probability (was 0.02 — too aggressive)
            "prob_ceil": 0.999,        # max crash probability
            "floor_warn_pct": 0.50,    # warn when >50% of predictions hit the floor
            "fallback_to_base_rate": True,  # use training base rate when calibrator is degenerate
            "isotonic_y_min": 0.01,    # IsotonicRegression lower bound
            "isotonic_y_max": 0.99,    # IsotonicRegression upper bound
        },
    },

    # ── GLOBAL MARKET PARAMETERS ────────────────────────────────────────
    "risk_free_rate": 0.04,  # Annual risk-free rate (10Y Treasury approx, updated 2026-03)

    # ── SIGNAL ENGINE WEIGHTS ─────────────────────────────────────────────
    # Composite buy/sell signal weights (must sum to 1.0).
    # Derived from grid search over 2020-2025 S&P 500 data (signal_optimizer.py).
    "signal_weights": {
        "crash_prob": 0.20,       # ML crash probability (leading indicator)
        "regime": 0.16,           # Bull/Bear/Volatile regime detection
        "valuation": 0.11,        # VIX-based fear/opportunity proxy
        "momentum": 0.12,         # 1M + 3M price momentum
        "mean_reversion": 0.09,   # Oversold/overbought contrarian signal
        "external": 0.12,         # External consensus (LEI, SLOOS, sentiment)
        "macro_risk": 0.10,       # 9-factor composite risk score (risk_scorer)
        "drawdown": 0.10,         # Current drawdown from 52-week high
    },
    # Crash probability base rate — the neutral point for the crash signal.
    # When crash_prob equals this, the crash component = 0 (neither bullish nor bearish).
    # Historical 3M crash frequency is ~12%.  Old formula used 40% as neutral,
    # which made the crash component permanently bullish in normal markets.
    "crash_base_rate_pct": 12.0,
    # Action thresholds: composite score ranges for each action
    "signal_thresholds": {
        "strong_buy": 0.45,
        "buy": 0.15,
        "sell": -0.15,
        "strong_sell": -0.45,
    },
    # Drawdown signal thresholds: stepped mapping from drawdown % to signal value
    # Each tuple is (drawdown_threshold_pct, signal_value)
    # Drawdown is negative (e.g., -10 means 10% below 52-week high)
    "drawdown_thresholds": {
        "near_high": -2,       # above this → bullish confirmation (+0.2)
        "pullback": -5,        # -2% to -5% → neutral (0.0)
        "correction": -10,     # -5% to -10% → correction (-0.3)
        "bear": -20,           # -10% to -20% → bear approach (-0.7)
        # below -20% → crisis (-0.9)
    },
    "drawdown_signals": {
        "near_high": 0.2,
        "pullback": 0.0,
        "correction": -0.3,
        "bear": -0.7,
        "crisis": -0.9,
    },
    # Per-stock signal adjustment weights (additive on top of market signal)
    "stock_signal_weights": {
        "analyst_target": 0.12,    # was 0.30 (convex combo) — now additive
        "sector_momentum": 0.012,  # per 1% sector return (was /20 = 0.05 per 1%)
        "pe_bonus": 0.10,          # bonus/penalty for extreme P/E
        "earnings_growth": 0.30,   # scale factor for fwd/trailing PE compression
    },

    # ── SIMULATION SETTINGS ──────────────────────────────────────────────
    "simulation": {
        "forecast_years": 5,
        "num_simulations": 10000,
        "trading_days_per_year": 252,
        # Jump-diffusion parameters
        "jump_diffusion": {
            "annual_rate": 0.07,          # ~7% annual prob of sudden jump (~1/14yr)
            "mean": -0.10,                # Average jump size (-10%)
            "std": 0.05,                  # Jump size volatility
            "t_degrees_of_freedom": 8,    # Student-t df default (used when GARCH fit unavailable)
            "min_t_degrees_of_freedom": 3, # Floor to prevent degenerate distributions
        },
        # Antithetic variates (Phase 2.2)
        "use_antithetic": True,
        # Tail estimation (Phase 2.2)
        "tail_mode_paths": 50000,
        # HMM regime blending
        "hmm_drift_blend": 0.15,
        "hmm_vol_blend": 0.15,
        # HMM fitting parameters
        "hmm": {
            "n_states": 3,
            "n_fits": 10,                    # Random restarts to avoid local optima
            "n_iter": 200,                   # EM iterations per fit
            "min_data_rows": 500,            # Minimum rows for HMM fitting
            "smoothing_window": 5,           # Return smoothing window (days)
            "vol_window": 20,                # Realized vol window (days)
            # Fallback values when HMM fitting fails
            "fallback_state_means": [0.10, -0.05, -0.30],
            "fallback_state_vols": [0.15, 0.20, 0.35],
            "fallback_regime_probs": [0.50, 0.30, 0.20],
        },
        # Block bootstrap
        "use_block_bootstrap": True,
        "block_bootstrap_size": 21,       # ~1 trading month
        # Mean reversion
        "mean_reversion": {
            "strength_up": 0.08,          # Annualized boost when below fair value
            "strength_down": 0.04,        # Annualized drag when above fair value
            "threshold_low": 0.20,        # Activate when 20% below fair value
            "threshold_high": 0.30,       # Activate when 30% above fair value
        },
        # Return constraints
        "max_5y_return": 3.0,             # 300% cap
        "max_annual_volatility": 1.2,     # 120% vol cap
        # GARCH-derived param bounds
        "garch_derived_params": {
            "rho_leverage_min": -0.95,
            "rho_leverage_max": -0.30,
            "xi_min": 0.02,
            "xi_max": 0.15,
        },
        # Valuation constraints
        "valuation": {
            "long_run_real_return": 0.067,
            "inflation_target": 0.025,
            "cape_long_run_average": 17.0,
            "cape_penalty_factor": 0.03,
            "val_penalty_cap": 0.015,   # Max 1.5% annual drag from CAPE (Phase 1G)
            "current_cape_fallback": 37.0,  # Shiller CAPE as of March 2026 (~36-39 range)
        },
    },

    # ── RISK SETTINGS ────────────────────────────────────────────────────
    "risk": {
        "crash_threshold": 0.20,          # 20% drawdown = crash
        "severe_threshold": 0.35,         # 35% drawdown = severe crash
        "confidence_level": 0.95,         # VaR/CVaR confidence
        # 9-factor composite risk score weights
        "indicator_weights": {
            "vix": 2.0,
            "yield_curve": 1.8,
            "credit_spread": 1.9,
            "long_yield_vol": 1.0,
            "momentum_exhaustion": 1.5,
            "short_term_vol": 1.3,
            "gold_stock_ratio": 1.2,
            "market_breadth": 1.0,
            "small_cap_divergence": 1.1,
        },
        # Momentum exhaustion threshold (z-score above which exhaustion signal activates)
        "momentum_exhaustion_threshold": 1.5,
        # Regime detection thresholds
        "regimes": {
            "high_vol_threshold": 0.30,
            "bull_return_threshold": 0.08,
            "neutral_return_threshold": -0.02,
            "bear_return_threshold": -0.05,
            "vix_stress_threshold": 25,
            "risk_stress_threshold": 1.5,
            "vix_calm_threshold": 16,
            "risk_calm_threshold": -0.5,
            # Short-window drawdown overrides (Phase 1A)
            "short_bear_1m": -0.05,     # 21d return < -5% → override Bull
            "short_bear_3m": -0.08,     # 63d return < -8% → override Bull
        },
    },

    # ── SCENARIO DEFINITIONS ─────────────────────────────────────────────
    # ~70% positive/neutral, ~30% bearish (matches historical base rates)
    "scenarios": {
        "Base Case": {
            "base_probability": 0.42,
            "return_multiplier": None,
            "absolute_return": 0.06,
            "volatility": 0.16,
            "crash_multiplier": 1.0,
            "category": "neutral",
            "description": "Historical trends continue with moderate growth",
        },
        "AI Productivity Boom": {
            "base_probability": 0.15,
            "return_multiplier": None,
            "absolute_return": 0.14,
            "volatility": 0.22,
            "crash_multiplier": 0.6,
            "category": "bullish",
            "description": "AI drives sustained productivity gains across sectors",
        },
        "Soft Landing": {
            "base_probability": 0.13,
            "return_multiplier": None,
            "absolute_return": 0.04,
            "volatility": 0.14,
            "crash_multiplier": 0.8,
            "category": "bullish",
            "description": "Fed engineers 2-3% inflation, steady growth, no recession",
        },
        "Market Correction": {
            "base_probability": 0.12,
            "return_multiplier": None,
            "absolute_return": -0.02,
            "volatility": 0.24,
            "crash_multiplier": 1.5,
            "category": "neutral",
            "description": "Valuation normalization, P/E compression, slower growth",
        },
        "Stagflation": {
            "base_probability": 0.08,
            "return_multiplier": None,
            "absolute_return": -0.04,
            "volatility": 0.23,
            "crash_multiplier": 1.8,
            "category": "bearish",
            "description": "1970s replay: persistent inflation + stagnant growth",
        },
        "Recession": {
            "base_probability": 0.06,
            "return_multiplier": None,
            "absolute_return": -0.10,
            "volatility": 0.30,
            "crash_multiplier": 2.5,
            "category": "bearish",
            "description": "Economic contraction, rising unemployment, credit stress",
        },
        "Geopolitical Crisis": {
            "base_probability": 0.04,
            "return_multiplier": None,
            "absolute_return": -0.15,
            "volatility": 0.35,
            "crash_multiplier": 3.0,
            "category": "bearish",
            "description": "Major conflict, supply chains collapse, sanctions escalate",
        },
    },

    # ── INSTITUTIONAL BENCHMARKS ─────────────────────────────────────────
    # Updated 2026-03 — current published capital market assumptions
    "institutional_benchmarks": {
        "Vanguard": {"annual": 0.047, "horizon": "10Y"},
        "Schwab": {"annual": 0.059, "horizon": "10Y"},
        "BlackRock": {"annual": 0.055, "horizon": "10Y"},
        "BNY Mellon": {"annual": 0.076, "horizon": "10Y"},
        "Morgan Stanley": {"annual": 0.068, "horizon": "10Y"},
        "Goldman Sachs": {"annual": 0.065, "horizon": "10Y"},
        "J.P. Morgan": {"annual": 0.067, "horizon": "10Y"},
        "AQR": {"annual": 0.042, "horizon": "10Y"},
        "Research Affiliates": {"annual": 0.035, "horizon": "10Y"},
        # 5Y vs 10Y horizon adjustment
        "horizon_adjustment": 1.05,
    },

    # ── REGIME VALIDATION ────────────────────────────────────────────────
    "regime_validation": {
        # Consensus annual return threshold for bull/bear classification.
        # If consensus return >= this, aligns with bull; below, aligns with bear.
        "consensus_bull_threshold": 0.03,
        # Minimum declining sectors for bear breadth confirmation
        "min_declining_sectors": 6,
    },

    # ── SECTOR FACTOR MODEL ──────────────────────────────────────────────
    "sector_model": {
        "min_history_days": 504,          # ~2 years required for factor estimation
        "beta_lookback_long": 504,        # 2-year rolling beta window
        "beta_lookback_short": 252,       # 1-year fallback beta window
        "beta_clip": (0.3, 2.5),          # Beta bounds
        "momentum_6m_weight": 0.4,        # Weight on 6M relative strength
        "momentum_12m_weight": 0.2,       # Weight on 12M relative strength
        "mean_reversion_coeff": -0.15,    # Mean-reversion factor loading
        "mean_reversion_lookback": 1260,  # 5-year lookback for MR
        "vol_lookback_long": 504,         # 2-year vol estimation window
        "vol_lookback_short": 63,         # 63-day short-term vol window
        "vol_ratio_threshold": 1.3,       # Vol ratio above which vol_adj activates
        "vol_adj_coeff": -0.02,           # Annualized drag per unit vol ratio excess
        "sigma_cap": 0.80,               # Maximum annualized vol
        "sigma_default": 0.20,           # Fallback when insufficient data
        "expected_return_clip": (-0.30, 0.50),  # Annualized return bounds
    },

    # ── STOCK ANALYSIS ───────────────────────────────────────────────────
    "stocks": {
        "screener_count": 20,
        "max_cagr_cap": 0.50,
        "min_history_days": 252,
        # CAGR caps by market-cap tier: (min, max) annualized log return
        # Wider than original hard caps to allow high-growth stocks realistic drift
        "cagr_caps": {
            "mega":  (0.04, 0.30),    # >$200B — was 0.15, widened for growth mega-caps
            "large": (0.05, 0.35),    # $10-200B — was 0.20
            "mid":   (0.06, 0.40),    # $2-10B — was 0.25
            "small": (0.08, 0.45),    # <$2B — was 0.30
        },
        # Bayesian shrinkage: blend historical drift toward long-run equity prior
        # More data = less shrinkage (trust history more); less data = shrink to prior
        "drift_shrinkage": {
            "prior_equity_premium": 0.07,   # Long-run real equity return (~7%)
            "min_shrinkage": 0.25,          # Even with 5yr data, keep 25% weight on prior
            "max_shrinkage": 0.60,          # With 1yr data, 60% weight on prior
            "data_years_for_min": 5.0,      # Years of data to reach min_shrinkage
        },
    },

    # ── CACHE TTLs (seconds) ──────────────────────────────────────────────
    "cache": {
        "ttl_hours": 1,
        "ttl_stock": 900,           # 15 min for per-ticker data
        "ttl_market": 300,          # 5 min for market-level endpoints
        "ttl_sectors": 3600,        # 1 hr for sector analysis
        "ttl_crash": 1800,          # 30 min for crash predictions
        "ttl_news": 900,            # 15 min for news
        "ttl_macro": 300,           # 5 min for macro indicators
        "ttl_simulation": 3600,     # 1 hr for Monte Carlo sims
        "ttl_portfolio": 0,         # No cache — unique per request body
        "ttl_backtest": 86400,      # 24 hr for backtest results
    },

    # ── EXTERNAL VALIDATION THRESHOLDS ──────────────────────────────────
    "external_validator": {
        "lei_warning_months": 3,          # Consecutive declines for WARNING
        "lei_recession_months": 6,        # Consecutive declines for RECESSION
        "sloos_tightening_threshold": 20, # Net % tightening → TIGHTENING
        "sloos_easing_threshold": -20,    # Net % easing → EASING
        "fed_hawkish_bps": 0.25,          # YoY rate change > 25bps → HAWKISH
        "fed_dovish_bps": -0.25,          # YoY rate change < -25bps → DOVISH
        "fed_lookback_days": 252,         # ~1 year of trading days
        "sentiment_extreme_fear": 60,     # UMich < 60 → EXTREME_FEAR
        "sentiment_fear": 80,             # UMich < 80 → FEAR
        "sentiment_greed": 100,           # UMich >= 100 → GREED
        "bearish_consensus_min": 3,       # >= 3 bearish signals → BEARISH consensus
        "bullish_consensus_max": 1,       # <= 1 bearish signal → BULLISH consensus
        "crash_prob_bearish": 0.50,       # crash_prob > 50% → engine is bearish
    },

    # ── NET LIQUIDITY ────────────────────────────────────────────────────
    "net_liquidity": {
        "wow_bullish_threshold": 0.05,   # WoW change (trillions) above this → BULLISH
        "wow_bearish_threshold": -0.05,  # WoW change (trillions) below this → BEARISH
    },

    # ── LLM / DEEPSEEK ──────────────────────────────────────────────────
    "llm": {
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "max_tokens": 500,
        "temperature": 0.3,
    },

    # ── DATA QUALITY ─────────────────────────────────────────────────────
    "data_quality": {
        "staleness_threshold_days": 3,
        "nan_threshold_pct": 0.20,
        "sp500_max_daily_return": 0.10,
        "sp500_max_daily_jump": 0.30,
        "vix_range": [5, 90],
        "yield_range": [-1.0, 20.0],
    },

    # ── TAIL RISK ANALYTICS ───────────────────────────────────────────────
    "tail_risk": {
        "tail_percentile": 5,          # Worst N% of days for tail concentration
        "min_observations": 60,        # Minimum trading days for reliable metrics
    },

    # ── PERFORMANCE ──────────────────────────────────────────────────────
    "performance": {
        "screener_max_workers": 8,       # ThreadPoolExecutor workers for screener
        "sector_momentum_workers": 6,    # Workers for parallel sector ETF fetches
        "gdelt_max_workers": 3,          # Workers for parallel GDELT API calls
        "gdelt_max_retries": 2,          # Retry attempts per GDELT endpoint
        "gdelt_retry_base_delay": 1.0,   # Base delay for GDELT retry backoff (seconds)
        "slow_request_threshold_s": 10.0,# Requests slower than this get a warning log
    },

    # ── SENTIMENT ANALYSIS ───────────────────────────────────────────────
    "sentiment": {
        "bullish_threshold": 0.15,          # avg_numeric > 0.15 → bullish
        "slightly_bullish_threshold": 0.05, # avg_numeric > 0.05 → slightly_bullish
        "bearish_threshold": -0.15,         # avg_numeric < -0.15 → bearish
        "slightly_bearish_threshold": -0.05,# avg_numeric < -0.05 → slightly_bearish
    },
}


# ── Convenience Accessors ────────────────────────────────────────────────────


def get_institutional_return() -> float:
    """Compute consensus institutional expected return, adjusted for horizon."""
    benchmarks = config["institutional_benchmarks"]
    adj = benchmarks.get("horizon_adjustment", 1.05)
    returns = [
        v["annual"]
        for k, v in benchmarks.items()
        if isinstance(v, dict) and "annual" in v
    ]
    return float(sum(returns) / len(returns)) * adj


def get_forecast_days() -> int:
    """Total trading days for the projection horizon."""
    sim = config["simulation"]
    return sim["forecast_years"] * sim["trading_days_per_year"]


def get_scenario_configs() -> dict:
    """Return scenario definitions with resolved returns.

    For scenarios with return_multiplier: return = institutional_return * multiplier
    For scenarios with absolute_return: return = absolute_return
    """
    inst_return = get_institutional_return()
    scenarios = {}
    for name, params in config["scenarios"].items():
        s = dict(params)
        if s.get("absolute_return") is not None:
            s["return"] = s["absolute_return"]
        elif s.get("return_multiplier") is not None:
            s["return"] = inst_return * s["return_multiplier"]
        else:
            s["return"] = inst_return
        s["probability"] = s.pop("base_probability")
        scenarios[name] = s
    return scenarios
