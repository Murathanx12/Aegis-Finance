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

# Mutable runtime state (the PI SQLite DB + APScheduler job store) lives here.
# On Railway this MUST point at a persistent volume mounted at a path that does
# NOT shadow the image: set AEGIS_DATA_DIR=/data and mount the volume at /data.
# Locally it defaults to backend/data, alongside the immutable config YAML.
# IMPORTANT: paper_portfolios.yaml and MODEL_DIR are immutable, version-controlled,
# and baked into the image — they are deliberately NOT under DATA_DIR, so a volume
# mounted for persistence can never shadow them on first boot.
DATA_DIR = Path(os.getenv("AEGIS_DATA_DIR", str(BACKEND_DIR / "data")))

load_dotenv(PROJECT_ROOT / ".env")


# ── US market calendar ────────────────────────────────────────────────────────
# NYSE full-closure holidays, used by the scheduler freshness canary to compute
# the expected last trading day. Extend annually. If the list expires, the
# canary degrades to weekday-only logic: a holiday then shows one false "stale"
# day — loud, not silent — which is the acceptable failure mode.
US_MARKET_HOLIDAYS = {
    # 2026
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
    "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
    # 2027
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31",
    "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
}


# ── API Keys ──────────────────────────────────────────────────────────────────


@dataclass
class APIKeys:
    """API keys loaded from .env file."""

    fred: str = ""
    finnhub: str = ""
    fmp: str = ""
    alpha_vantage: str = ""
    polygon: str = ""

    @classmethod
    def from_env(cls) -> "APIKeys":
        return cls(
            fred=os.getenv("FRED_API_KEY", ""),
            finnhub=os.getenv("FINNHUB_API_KEY", ""),
            fmp=os.getenv("FMP_API_KEY", ""),
            alpha_vantage=os.getenv("ALPHA_VANTAGE_API_KEY", ""),
            polygon=os.getenv("POLYGON_API_KEY", ""),
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
        # Drift detection (Phase 4.4 + 4.5)
        "drift": {
            "psi_threshold": 0.2,
            "ks_p_threshold": 0.01,
            "n_bins": 10,
            # Drift-aware confidence discounting (Phase 4.5)
            # Maps drift severity to a confidence multiplier for crash predictions.
            "confidence_multiplier": {
                "none": 1.0,
                "low": 0.95,
                "moderate": 0.80,
                "high": 0.60,
                "critical": 0.40,
            },
            # Multiplier applied to crash_prob signal weight under drift
            "signal_weight_multiplier": {
                "none": 1.0,
                "low": 1.0,
                "moderate": 0.7,
                "high": 0.4,
                "critical": 0.2,
            },
            # Multi-scale drift windows: check drift at multiple time horizons.
            # Short-scale stability can override long-scale severity.
            "multi_scale_windows": [
                {"name": "long", "reference_days": 504, "inference_days": 252},
                {"name": "medium", "reference_days": 252, "inference_days": 126},
                {"name": "short", "reference_days": 126, "inference_days": 63},
            ],
            # Feature group classification for drift decomposition.
            # Maps regex patterns to group names. Order matters — first match wins.
            # Groups allow per-category drift reporting so users can distinguish
            # expected drift (momentum in a bull run) from concerning drift (macro shifts).
            "feature_groups": {
                "interaction": [
                    "_x_",
                ],
                "momentum": ["mom_", "trend_strength"],
                "volatility": ["vol_", "vol_of_vol", "vol_zscore", "vol_ratio_"],
                "tail_risk": [
                    "max_daily_loss", "max_drawdown", "lower_partial",
                    "cvar_", "neg_day_ratio", "down_streak",
                    "skew_index", "skew_zscore", "skew_elevated",
                    "realized_skew", "realized_kurt",
                ],
                "price_distance": [
                    "dist_52w", "drawdown_from_peak", "daily_ret", "log_ret",
                ],
                "technical": [
                    "sma_", "golden_cross", "macd_", "rsi_",
                    "bollinger_",
                ],
                "vix": [
                    "vix",
                ],
                "credit_yields": [
                    "credit_spread", "yield_", "term_spread",
                    "long_short_spread",
                ],
                "cross_asset": [
                    "gold_equity", "sp_nasdaq", "small_large",
                    "sector_dispersion", "bond_equity",
                ],
                "macro": [
                    "fred_",
                ],
            },
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

    # ── TAIL RISK ANALYTICS ────────────────────────────────────────────
    "tail_risk": {
        "tail_percentile": 5,       # worst N% of loss days for tail concentration
        "min_observations": 60,     # minimum daily returns needed for valid metrics
    },

    # ── CROSS-ASSET TAIL DEPENDENCE ──────────────────────────────────────
    "tail_dependence": {
        "lookback_days": 756,         # 3 years of trading days
        "quantile_lo": 0.02,          # lower bound for tail quantile grid
        "quantile_hi": 0.10,          # upper bound for tail quantile grid
        "n_quantile_steps": 9,        # grid resolution for averaging λ_L
        "rolling_window": 126,        # 6-month rolling window
        "min_observations": 120,      # minimum returns for valid estimate
        "contagion_threshold": 0.15,  # contagion score above this = elevated
        "cluster_threshold": 0.20,    # tail dep threshold for cluster membership
    },

    # ── GLOBAL MARKET PARAMETERS ────────────────────────────────────────
    "risk_free_rate": 0.04,  # Annual risk-free rate (10Y Treasury approx, updated 2026-03)

    # ── SIGNAL ENGINE WEIGHTS ─────────────────────────────────────────────
    # Composite buy/sell signal weights (must sum to 1.0).
    # Derived from grid search over 2020-2025 S&P 500 data (signal_optimizer.py).
    "signal_weights": {
        "crash_prob": 0.16,       # ML crash probability (leading indicator)
        "regime": 0.13,           # Bull/Bear/Volatile regime detection
        "valuation": 0.09,        # VIX-based fear/opportunity proxy
        "momentum": 0.10,         # 1M + 3M price momentum
        "mean_reversion": 0.07,   # Oversold/overbought contrarian signal
        "external": 0.09,         # External consensus (LEI, SLOOS, sentiment)
        "macro_risk": 0.08,       # 9-factor composite risk score (risk_scorer)
        "drawdown": 0.08,         # Current drawdown from 52-week high
        "systemic_risk": 0.09,    # Turbulence + absorption ratio (Kritzman)
        "economic_surprise": 0.05, # Economic data surprise index (FRED actual vs trend)
        "momentum_breadth": 0.06, # Market breadth (% stocks with positive momentum)
    },
    # Regime-adaptive signal weights — override defaults per market regime.
    # Research: momentum dominates bull markets (Jegadeesh & Titman), mean
    # reversion and crash risk dominate bear/volatile markets (DeBondt & Thaler),
    # VIX-based signals matter more in volatile regimes (Ang et al. 2006).
    # Weights are re-normalized at runtime so they sum to 1.0.
    "regime_signal_weights": {
        "Bull": {
            "crash_prob": 0.10,       # less relevant when trending up
            "regime": 0.11,
            "valuation": 0.06,
            "momentum": 0.17,         # momentum is strongest in trends
            "mean_reversion": 0.04,   # rarely triggers in bull
            "external": 0.10,
            "macro_risk": 0.08,
            "drawdown": 0.12,         # confirm trend via proximity to highs
            "systemic_risk": 0.08,    # less critical in calm trends
            "economic_surprise": 0.06, # macro confirmation of bull trend
            "momentum_breadth": 0.08, # breadth confirms broad rally vs narrow
        },
        "Bear": {
            "crash_prob": 0.18,       # crash risk is critical
            "regime": 0.10,
            "valuation": 0.09,
            "momentum": 0.04,         # momentum breaks down in bears
            "mean_reversion": 0.12,   # contrarian opportunities
            "external": 0.08,
            "macro_risk": 0.09,
            "drawdown": 0.05,         # everything is in drawdown, less informative
            "systemic_risk": 0.12,    # contagion risk matters most in bears
            "economic_surprise": 0.07, # macro deterioration confirms bear
            "momentum_breadth": 0.06, # breadth collapse = widespread selling
        },
        "Volatile": {
            "crash_prob": 0.12,
            "regime": 0.09,
            "valuation": 0.12,        # VIX signals matter most
            "momentum": 0.05,         # unreliable in whipsaws
            "mean_reversion": 0.10,   # mean reversion opportunities
            "external": 0.09,
            "macro_risk": 0.09,
            "drawdown": 0.07,
            "systemic_risk": 0.14,    # coupling/contagion risk critical in volatile regimes
            "economic_surprise": 0.06, # macro data can confirm or deny panic
            "momentum_breadth": 0.07, # breadth divergence = selective damage vs broad
        },
        # "Neutral" and "Unknown" fall through to default signal_weights
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
        "stock_crash_risk": 0.15,  # weight for per-stock crash risk adjustment
        "stock_drawdown": 0.25,    # weight for stock-specific drawdown signal
        "stock_momentum": 0.20,    # weight for stock-specific momentum signal
        "options_iv": 0.12,        # weight for options-implied signal (IV skew, P/C ratio)
        "earnings_quality": 0.10,  # weight for earnings surprise/growth signal
        "insider_trading": 0.10,   # weight for insider buy/sell signal (cluster buy = strong)
        "technical_analysis": 0.08,  # weight for TA composite (RSI, MACD, Bollinger, ADX)
    },
    # Per-stock crash probability adjustment parameters.
    # Market-level crash prob is scaled by stock-specific risk factors (beta,
    # volatility, drawdown) so high-beta/high-vol stocks get higher crash risk.
    "stock_crash_adjustment": {
        "beta_sensitivity": 0.6,       # how much beta scales crash prob (0=ignore, 1=linear)
        "vol_sensitivity": 0.4,        # how much excess vol scales crash prob
        "drawdown_sensitivity": 0.3,   # how much drawdown from peak increases crash prob
        "vol_baseline": 0.20,          # annualized vol considered "neutral" (20%)
        "min_multiplier": 0.4,         # floor: defensive stocks get at least 40% of market crash
        "max_multiplier": 2.5,         # ceiling: no stock gets more than 2.5x market crash
    },

    # ── SIGNAL ANALYTICS ────────────────────────────────────────────────
    "signal_analytics": {
        "concentration_warning_pct": 60,  # warn if top N picks are >60% in one sector
        "top_n_for_concentration": 5,     # check top 5 stocks for sector concentration
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

    # ── OPTIONS CALIBRATION ──────────────────────────────────────────────
    # Parameters for options-implied Monte Carlo calibration
    "options_calibration": {
        "iv_blend_weight": 0.35,        # How much to trust IV vs GARCH (0=GARCH, 1=IV)
        "skew_neutral": 1.1,            # Normal skew level (puts always slightly premium)
        "skew_elevated": 1.4,           # High fear level
        "pc_ratio_neutral": 0.9,        # Below = bullish positioning
        "pc_ratio_elevated": 1.5,       # Above = heavy put buying
        "iv_rank_low": 25.0,            # Below = complacent (low vol regime)
        "iv_rank_high": 75.0,           # Above = elevated fear
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
            # VIX term structure thresholds (contango/backwardation)
            # VIX/VIX3M ratio: >1 = backwardation (stress), <1 = contango (normal)
            "vix_backwardation_threshold": 1.05,  # Mild backwardation
            "vix_severe_backwardation": 1.15,     # Severe stress (VIX 15%+ above VIX3M)
            "vix_deep_contango": 0.80,            # Deep contango = complacency risk
        },
    },

    # ── EXECUTION COST MODEL ────────────────────────────────────────────
    "execution_costs": {
        "slippage_bps": 5,              # Bid-ask spread proxy (one-way)
        "commission_bps": 1,            # Broker commission (one-way)
        "market_impact_factor": 0.1,    # Square-root model coefficient (η)
    },

    # ── LPPL BUBBLE DETECTION ──────────────────────────────────────────
    "bubble_detection": {
        "confidence_threshold": 0.5,     # Fraction of valid LPPL fits to flag bubble
        "min_window_days": 120,          # Minimum fitting window
        "max_window_days": 750,          # Maximum fitting window
        "n_fits": 25,                    # Number of nested fits per evaluation
    },

    # ── SYSTEMIC RISK (Turbulence Index + Absorption Ratio) ────────────
    "systemic_risk": {
        "turbulence_window": 252,          # Rolling covariance lookback (days)
        "absorption_n_components": 5,      # Top PCA components for absorption ratio
        "absorption_window": 252,          # Rolling PCA lookback (days)
        "turbulence_threshold_pctl": 90,   # Percentile above which turbulence = stress
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

    # ── DIVIDEND INTELLIGENCE ────────────────────────────────────────────
    "dividend_intelligence": {
        "safety_weights": {
            "payout_ratio": 0.30,
            "fcf_coverage": 0.25,
            "earnings_stability": 0.25,
            "debt_equity": 0.20,
        },
        "ddm_discount_rate": 0.10,       # Gordon Growth Model cost of equity
        "ddm_terminal_growth": 0.03,     # Long-run dividend growth assumption
        "income_projection_amount": 10000,  # Default investment for income calc
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

    # ── LLM (Claude preferred, DeepSeek fallback) ──────────────────────
    "llm": {
        # Claude (if ANTHROPIC_API_KEY is set)
        "claude_model_fast": "claude-haiku-4-5-20251001",
        "claude_model_quality": "claude-sonnet-4-6",
        # DeepSeek (if DEEPSEEK_API_KEY is set, Claude not available)
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        # Shared settings
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

    # ── STOCK UNIVERSE ───────────────────────────────────────────────────
    # Expanded universe: S&P 100 constituents + popular growth/value names
    # Organized by GICS sector for screener and factor analysis
    "stock_universe": {
        "default_watchlist": [
            "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META",
            "TSLA", "JPM", "JNJ", "V", "UNH", "XOM",
            "BRK-B", "LLY", "AVGO", "MA", "COST", "HD",
        ],
        "sector_stocks": {
            "Technology": [
                "AAPL", "MSFT", "NVDA", "AVGO", "CRM", "AMD", "ADBE", "ACN",
                "CSCO", "ORCL", "INTC", "NOW", "PLTR", "INTU", "TXN", "QCOM",
                "AMAT", "MU", "PANW", "SNPS", "CDNS", "FTNT", "CRWD",
            ],
            "Healthcare": [
                "UNH", "LLY", "JNJ", "ABBV", "MRK", "PFE", "TMO", "ABT",
                "ISRG", "VRTX", "DXCM", "GEHC", "MDT", "SYK", "BMY",
                "AMGN", "GILD", "CI", "ELV", "HCA", "ZTS",
            ],
            "Financials": [
                "JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "BLK",
                "SPGI", "C", "AXP", "SCHW", "CB", "MMC", "ICE",
                "PGR", "CME", "AON", "COIN", "SQ",
            ],
            "Energy": [
                "XOM", "CVX", "COP", "SLB", "EOG", "PXD", "MPC", "OKE",
                "PSX", "VLO", "WMB", "KMI", "FSLR", "ENPH", "HAL",
            ],
            "Consumer Disc.": [
                "AMZN", "TSLA", "HD", "MCD", "NKE", "BKNG", "LOW", "TJX",
                "SBUX", "ABNB", "CMG", "ORLY", "ROST", "DHI", "GM",
                "F", "LULU", "YUM", "DKNG",
            ],
            "Industrials": [
                "CAT", "GE", "RTX", "HON", "UPS", "BA", "DE", "LMT",
                "UBER", "AXON", "TT", "ETN", "WM", "GD", "NOC",
                "FDX", "CSX", "NSC", "EMR",
            ],
            "Communications": [
                "META", "GOOGL", "NFLX", "DIS", "CMCSA", "TMUS", "VZ", "T",
                "RBLX", "SPOT", "EA", "TTWO", "WBD", "CHTR",
            ],
            "Consumer Staples": [
                "COST", "PG", "KO", "WMT", "PEP", "PM", "MO", "CL",
                "MDLZ", "GIS", "KHC", "STZ", "MNST", "KR", "SYY",
            ],
            "Materials": [
                "LIN", "APD", "SHW", "FCX", "NEM", "ECL", "DD", "VMC",
                "NUE", "DOW", "PPG", "MLM",
            ],
            "Utilities": [
                "NEE", "SO", "DUK", "AEP", "D", "SRE", "EXC", "XEL",
                "VST", "CEG", "PCG", "WEC",
            ],
            "Real Estate": [
                "PLD", "AMT", "EQIX", "CCI", "O", "SPG", "PSA", "WELL",
                "DLR", "AVB", "VICI",
            ],
        },
        # How many stocks per sector to include in screener (top N by market cap)
        "screener_per_sector": 5,
        # Maximum total tickers in screener (performance guard)
        "screener_max_tickers": 80,
    },

    # ── RELATIVE VALUATION ──────────────────────────────────────────────
    # Koyfin-style peer comparison: rank a stock vs sector peers on valuation metrics
    "relative_valuation": {
        "peer_fetch_workers": 6,         # Parallel yfinance fetches for peer metrics
        "history_years": 5,              # Years of historical data for valuation ranges
        "composite_weights": {
            "pe_trailing": 0.15,         # Trailing P/E
            "pe_forward": 0.15,          # Forward P/E
            "peg_ratio": 0.12,           # PEG ratio (growth-adjusted P/E)
            "ev_ebitda": 0.15,           # Enterprise Value / EBITDA
            "price_to_sales": 0.10,      # Price-to-Sales
            "price_to_book": 0.08,       # Price-to-Book
            "dividend_yield": 0.05,      # Dividend Yield (higher = better)
            "revenue_growth": 0.08,      # Revenue Growth (higher = better)
            "earnings_growth": 0.07,     # Earnings Growth (higher = better)
            "profit_margin": 0.05,       # Profit Margin (higher = better)
        },
        "verdict_thresholds": {
            "deep_value": 75,            # Composite score ≥ 75 → Deep Value
            "undervalued": 60,           # Composite score ≥ 60 → Undervalued
            "fair_value_upper": 55,      # 45-55 → Fair Value
            "fair_value_lower": 45,
            "overvalued": 35,            # 35-45 → Overvalued
        },
    },

    # ── BENCHMARK ANALYTICS ──────────────────────────────────────────────
    # Bloomberg PORT-style benchmark-relative analytics
    "benchmark_analytics": {
        "default_benchmark": "SPY",          # Default benchmark ticker
        "default_lookback_days": 504,        # 2 years of trading days
        "rolling_te_window": 63,             # 3-month rolling window for tracking error
        "annualization_factor": 252,         # Trading days per year
        "risk_free_rate": 0.045,             # For Sharpe/Sortino calculation (4.5% in 2026)
        "sp500_approximate_mcap": 50_000_000_000_000,  # ~$50T for active share approximation
    },

    # ── VOLATILITY ANALYTICS ────────────────────────────────────────────
    # Bloomberg-style vol cone, term structure, regime, risk premium, GARCH forecast
    "volatility_analytics": {
        "cone_windows": [10, 30, 60, 90, 180, 252],  # Lookback windows (trading days)
        "vovol_window": 60,              # Rolling window for vol-of-vol
        "history_years": 5,              # Years of price history for percentile computation
        "annualization_factor": 252,     # Trading days per year
        "regime_low_pctl": 25,           # Below this percentile → low vol regime
        "regime_high_pctl": 75,          # Above this percentile → high vol regime
        "arch_test_lags": 10,            # Lags for Ljung-Box test on squared returns
    },

    # ── CHART PATTERN RECOGNITION ──────────────────────────────────────
    # TradingView-style automatic chart pattern detection
    "pattern_recognition": {
        "pivot_window": 5,             # Bars on each side to confirm a pivot
        "sr_cluster_pct": 0.015,       # 1.5% tolerance for S/R level clustering
        "min_pattern_bars": 10,        # Minimum bars between pattern points
        "max_pattern_bars": 120,       # Maximum bars for pattern span
        "breakout_threshold": 0.005,   # 0.5% beyond level = confirmed breakout
        "double_tolerance": 0.03,      # 3% tolerance for double top/bottom peak matching
        "hs_shoulder_tolerance": 0.05, # 5% tolerance for H&S shoulder symmetry
    },

    # ── SIGNAL ENGINE THRESHOLDS ─────────────────────────────────────────
    # Centralized from signal_engine.py and risk_scorer.py hardcoded values
    "signal_thresholds_vix": {
        "low": 15,        # VIX below → complacent / bullish
        "moderate": 20,   # VIX 15-20 → normal
        "elevated": 25,   # VIX 20-25 → cautious
        "high": 30,       # VIX above → fear / bearish
    },

    # ── STRESS TESTING ───────────────────────────────────────────────────
    # Historical crisis scenarios for portfolio stress testing
    "stress_testing": {
        "scenarios": {
            "2008_GFC": {
                "name": "2008 Global Financial Crisis",
                "start": "2007-10-09",
                "end": "2009-03-09",
                "sp500_drawdown": -0.568,
                "description": "Subprime mortgage crisis, Lehman collapse, global contagion",
            },
            "2020_COVID": {
                "name": "2020 COVID Crash",
                "start": "2020-02-19",
                "end": "2020-03-23",
                "sp500_drawdown": -0.339,
                "description": "Pandemic lockdowns, fastest 30% decline in history",
            },
            "2000_DOTCOM": {
                "name": "2000-02 Dot-Com Bust",
                "start": "2000-03-24",
                "end": "2002-10-09",
                "sp500_drawdown": -0.491,
                "description": "Tech bubble burst, corporate fraud (Enron, WorldCom)",
            },
            "1987_BLACK_MONDAY": {
                "name": "1987 Black Monday",
                "start": "1987-08-25",
                "end": "1987-12-04",
                "sp500_drawdown": -0.336,
                "description": "Program trading cascade, 22.6% single-day drop",
            },
            "2022_RATE_SHOCK": {
                "name": "2022 Rate Shock",
                "start": "2022-01-03",
                "end": "2022-10-12",
                "sp500_drawdown": -0.254,
                "description": "Aggressive Fed tightening, inflation spike, growth-to-value rotation",
            },
            "2018_VOLMAGEDDON": {
                "name": "2018 Volmageddon + Q4 Selloff",
                "start": "2018-01-26",
                "end": "2018-12-24",
                "sp500_drawdown": -0.199,
                "description": "VIX spike, trade war fears, Fed tightening",
            },
        },
    },

    # ── FACTOR MODEL ─────────────────────────────────────────────────────
    # Fama-French 5-factor model configuration
    "factor_model": {
        "lookback_days": 756,          # 3 years of daily returns for factor regression
        "min_observations": 126,       # Minimum trading days for valid regression
        "significance_level": 0.05,    # p-value threshold for significant factor exposure
        "french_data_url": "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/",
        "factors": ["Mkt-RF", "SMB", "HML", "RMW", "CMA"],
    },

    # ── LIQUIDITY RISK ──────────────────────────────────────────────────
    "liquidity_risk": {
        "lookback_days": 252,            # 1 year of trading days
        "min_observations": 60,          # Minimum days for valid analysis
        "amihud_window": 21,             # Rolling window for Amihud illiquidity
        "roll_window": 21,               # Rolling window for Roll spread
        # Liquidity-adjusted position sizing parameters
        "position_sizing": {
            "enabled": True,             # Apply liquidity adjustment by default
            "min_dollar_volume_mm": 1.0, # Hard floor: skip stocks < $1M avg daily volume
            "penalty_exponent": 0.5,     # How aggressively to penalize illiquidity (0=off, 1=linear)
            "max_weight_reduction": 0.50,# Never reduce a position by more than 50%
            "score_threshold": 40,       # Liquidity score below which penalty kicks in
        },
    },

    # ── COPULA TAIL DEPENDENCE ──────────────────────────────────────────
    # Parametric copula models (Clayton, Gumbel, Frank, Student-t) for
    # proper tail dependence estimation — replaces pure empirical approach.
    "copula_config": {
        "lookback_days": 756,            # 3 years of daily returns
        "min_observations": 252,         # Minimum for reliable copula fit
        "copula_families": ["clayton", "gumbel", "frank", "student_t"],
        "confidence_level": 0.05,        # VaR/CVaR quantile
        "n_simulations": 10000,          # MC simulations for copula VaR
        "aic_selection": True,           # Select best copula by AIC
    },

    # ── PAIR TRADING & COINTEGRATION ───────────────────────────────────
    # Statistical arbitrage pair detection (Engle-Granger + Johansen)
    "pair_trading": {
        "lookback_days": 504,            # 2 years of daily prices
        "min_observations": 126,         # Minimum for reliable cointegration test
        "cointegration_pvalue": 0.05,    # ADF p-value threshold for cointegration
        "entry_z": 2.0,                  # Z-score to enter a pair trade
        "exit_z": 0.5,                   # Z-score to close (mean reversion done)
        "stop_z": 4.0,                   # Z-score stop-loss (spread blowout)
        "max_half_life_days": 126,       # Max acceptable half-life (6 months)
        "min_half_life_days": 5,         # Min half-life (filter out noise)
        "z_score_window": 63,            # Rolling window for z-score (3 months)
        "hedge_ratio_window": 63,        # Rolling OLS hedge ratio window
        "scan_workers": 6,               # Parallel workers for universe scan
        "top_pairs": 20,                 # Return top N pairs from scanner
        "scan_tickers": [                # Default tickers for pair scanning
            "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META",
            "JPM", "BAC", "GS", "MS", "V", "MA",
            "XOM", "CVX", "COP", "SLB",
            "UNH", "JNJ", "LLY", "ABBV", "PFE", "MRK",
            "HD", "LOW", "COST", "WMT",
            "CAT", "DE", "HON", "GE",
        ],
    },

    # ── DENOISED COVARIANCE ─────────────────────────────────────────────
    # Marchenko-Pastur denoising + Ledoit-Wolf shrinkage for covariance
    "covariance_config": {
        "method": "denoised",            # "denoised" | "ledoit_wolf" | "empirical"
        "lookback_days": 504,            # 2 years for covariance estimation
        "detone": True,                  # Remove market mode (1st eigenvector)
        "target_explained": 0.95,        # Target cumulative variance for signal cutoff
    },

    # ── CROSS-ASSET MACRO REGIME MONITOR ────────────────────────────────
    # Bloomberg MAC3-style cross-asset intelligence
    "cross_asset": {
        "correlation_window": 63,        # Rolling correlation window (3 months)
        "lookback_years": 3,             # Price history for all computations
        "momentum_windows": {            # Multi-timeframe momentum
            "1w": 5, "1m": 21, "3m": 63, "6m": 126, "1y": 252,
        },
        "roro_thresholds": {             # Risk-On/Risk-Off classification
            "risk_on": 65,               # Score above → Risk-On
            "risk_off": 35,              # Score below → Risk-Off
        },
        "divergence_threshold": 0.25,    # Correlation divergence alert threshold
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


# ── Paper Portfolio Configuration ────────────────────────────────────────────


def load_paper_portfolios() -> dict:
    """Load paper portfolio definitions from YAML.

    Returns raw dict — validated by Pydantic schemas at use site.
    Read-only at process start; never modified at runtime.
    """
    yaml_path = BACKEND_DIR / "data" / "paper_portfolios.yaml"
    if not yaml_path.exists():
        return {}
    try:
        import yaml
        with open(yaml_path, "r") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        import json as _json
        raise ImportError("PyYAML required for paper portfolio config: pip install pyyaml")


paper_portfolios: dict = load_paper_portfolios()
