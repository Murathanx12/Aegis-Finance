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

# ── BUILD1 artefacts: found, never assumed ────────────────────────────────────
#
# `docs/BUILD1/` holds fourteen artefacts that CODE reads and writes, not prose:
# `llm_ledger.jsonl` (the spend ledger that enforces `CAMPAIGN_BUDGET_USD`),
# `funnel_night10.json`, `mirror_challenge.json`, the analyst coverage matrix
# and its probe receipts.
#
# On 2026-08-29 a documentation clean-up `git mv`-ed all 92 dated docs -- and
# the whole of `docs/BUILD1/` with them -- into `docs/archive/`. Nothing in the
# move was wrong; every consumer that hardcoded the old path was.
#
# The consequence was not a broken import. `llm_research.spent_usd()` returns
# **0.0 when the ledger file is absent**, so the budget gate quietly forgot 71
# recorded calls and would have re-authorised the full $30 campaign budget. The
# only visible symptom was one red test out of 6,018, about a different file.
#
# The docstring on `llm_research._mirror` already warned that "re-pointing a
# budget gate during an instrumentation change is how budgets stop being
# enforced". It was right, and a comment cannot enforce itself -- which is why
# the fix is a RESOLVER plus `test_build1_paths.py`, not a corrected constant.
BUILD1_DIRS = (PROJECT_ROOT / "docs" / "BUILD1",
               PROJECT_ROOT / "docs" / "archive" / "BUILD1")


def build1_path(name: str) -> Path:
    """Where BUILD1 artefact `name` actually is, searching live then archive.

    An EXISTING file wins wherever it lives, so an append-only ledger keeps
    appending to its own history instead of starting a fresh empty one beside
    it. When the file does not exist yet, the first candidate DIRECTORY that
    exists is used, falling back to the live path so a first write lands in the
    live tree and an error message names somewhere a human recognises.
    """
    for d in BUILD1_DIRS:
        if (d / name).exists():
            return d / name
    for d in BUILD1_DIRS:
        if d.is_dir():
            return d / name
    return BUILD1_DIRS[0] / name

# Mutable runtime state (the PI SQLite DB + APScheduler job store) lives here.
# On Railway this MUST point at a persistent volume mounted at a path that does
# NOT shadow the image: set AEGIS_DATA_DIR=/data and mount the volume at /data.
# Locally it defaults to backend/data, alongside the immutable config YAML.
# IMPORTANT: paper_portfolios.yaml is immutable, version-controlled, and baked
# into the image — deliberately NOT under DATA_DIR, so a persistence volume can
# never shadow it on first boot. MODEL_DIR is on the image too, BUT its trained
# artifacts (crash_model.pkl etc.) are GITIGNORED (*.pkl) and therefore NOT
# shipped — production has no trained crash model, so the crash overlay is dark
# (surfaced in /api/health/full "overlay"). Arming the overlay requires shipping
# a provenance-documented, version-controlled model on NEW pre-registered lanes
# (do not retrofit the live track record). See docs/TRIALS/TRIAL-001 note.
DATA_DIR = Path(os.getenv("AEGIS_DATA_DIR", str(BACKEND_DIR / "data")))

#: CI has no `.env`; this machine does, and that difference is load-bearing —
#: eleven tests once passed locally BECAUSE a secrets file existed and failed in
#: CI. The documented way to reproduce CI was to `mv .env .env.hidden` inside a
#: subshell with an EXIT trap.
#:
#: THAT RECIPE FIRED ON 2026-08-24 AND LEFT THE MACHINE WITHOUT ITS KEYS. The
#: subshell died before its trap ran, `.env` stayed hidden, and every key on the
#: box was gone until someone noticed. The handoff warned about exactly this
#: failure and the warning did not prevent it, because a warning cannot.
#:
#: So there is now a way to reproduce CI that never touches the file:
#:
#:     AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/ -m "not slow"
#:
#: Read from the real environment rather than a config value, because config is
#: what this decides.
if os.getenv("AEGIS_IGNORE_DOTENV", "").strip().lower() not in ("1", "true", "yes"):
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


# ── Critical FRED inputs (services/fred_health.py) ────────────────────────────
# Series whose absence is a MODEL INPUT DEGRADATION, not a temporary source
# miss. The distinction is the whole point: `fetch_fred_data` drops a failed
# series from its result dict and `get_macro_features` skips any key that is not
# there, so a leading indicator can vanish for a day — the FRED cache TTL is
# 86,400s — while /api/health/full reads `ok` with an empty degraded_reasons.
# That is the house failure mode wearing a health page.
#
# These are the LEADING inputs. The programme's own feature-importance
# requirement is that leading indicators (ICSA, NFCI, the yield curve) rank
# ABOVE lagging ones, so their silent disappearance changes what the composite
# is measuring — not merely how precisely.
CRITICAL_FRED_SERIES = (
    "initial_claims",        # ICSA — weekly, the fastest labour signal there is
    "initial_claims_4wk",    # IC4WSA
    "nfci",                  # Chicago Fed National Financial Conditions Index
    "yield_spread",          # T10Y3M
    "hy_oas",                # high-yield spread
)
# A failed fetch may fall back to the last known good series for this long. The
# fallback is USED and DISCLOSED (STALE_USABLE), never silently substituted.
# 48h covers a weekly series missing one daily fetch plus a retry window.
FRED_LKG_TTL_HOURS = 48
# Consecutive failed fetch passes before a critical series enters
# degraded_reasons. One miss is a transient; two is a pattern.
FRED_DEGRADED_AFTER_MISSES = 2


# ── Prediction-ledger resolver (services/ledger_resolver.py) ──────────────────
# Calendar-day pad prepended to the earliest due record's made_at when fetching
# a fresh price panel — covers weekend/holiday gaps so the first bar of the
# window is never missing.
LEDGER_RESOLVER_FETCH_PAD_DAYS = 7
# The frozen conviction CSV counts as covering `today` only if its last bar is
# within this many calendar days — beyond that the resolver must fetch fresh
# rather than silently grade on a stale panel.
LEDGER_RESOLVER_CSV_GRACE_DAYS = 4
# Tickers per vendor request when the resolver fetches a fresh panel. One
# request for every due ticker was fine at ~12 names; LLM-SWARM-1 put hundreds
# of securities in the ledger in a night, and a single request that large fails
# as a UNIT — one slow symbol strands every due record at once and the ledger
# canary reports a problem that is not in the ledger. Chunking makes the
# failure proportional to the chunk instead of total.
LEDGER_RESOLVER_FETCH_BATCH = 100


# ── Optimus prediction ledger (services/belief_state.py) ──────────────────────
# The ledger is WRITTEN state, so it belongs under DATA_DIR (the persistent
# volume on Railway), not inside the image. Until NIGHT-14 it resolved to
# BACKEND_DIR/data/optimus unconditionally, which on Railway is a path inside
# the container filesystem: every PredictionRecord the nightly specialists wrote
# was destroyed by the next deploy, and forward calibration — which accrues from
# the first written record and from no earlier date — would have silently reset
# to zero before the first resolution fell due (2026-09-12). This is defect F7
# in docs/NIGHT13_DISCHARGE.md §7.
# Locally AEGIS_DATA_DIR is unset, so DATA_DIR is BACKEND_DIR/data and this path
# is byte-identical to the pre-NIGHT-14 one — dev behaviour is unchanged.
OPTIMUS_LEDGER_DIR = DATA_DIR / "optimus"
# Where the ledger used to live. Kept ONLY as the source of the one-time
# migration in belief_state.ensure_ledger_migrated(); when AEGIS_DATA_DIR is
# unset the two are the same directory and the migration is a documented no-op.
OPTIMUS_LEDGER_LEGACY_DIR = BACKEND_DIR / "data" / "optimus"


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

    def redact(self, text: str) -> str:
        """Strip every configured key value out of *text*. Error messages from
        HTTP clients embed the full request URL — including ``apikey=`` query
        params — so anything that might reach a log line goes through here."""
        for field_name in ("fred", "finnhub", "fmp", "alpha_vantage", "polygon"):
            val = getattr(self, field_name, "")
            if val:
                text = text.replace(val, "***")
        return text


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
        # FRED series IDs (23 series including leading indicators ICSA, NFCI)
        "fred_series": {
            "yield_spread": "T10Y3M",           # 10Y-3M Treasury spread (recession predictor)
            "sahm_rule": "SAHMREALTIME",         # Sahm Rule recession indicator
            "insured_unemployment_rate": "IURSA",  # Insured unemployment rate (weekly) — Richmond Fed SOS input
            "recession_prob": "RECPROUSM156N",   # Chauvet-Piger smoothed recession probability
            "unemployment": "UNRATE",            # Unemployment rate
            "cpi": "CPIAUCSL",                   # Consumer Price Index
            "fed_funds": "FEDFUNDS",             # Federal Funds Rate
            "consumer_sentiment": "UMCSENT",     # U of Michigan Consumer Sentiment
            "vix_fred": "VIXCLS",                # VIX (FRED version, longer history)
            "hy_oas": "BAMLH0A0HYM2",           # High Yield OAS spread
            "ig_oas": "BAMLC0A0CM",             # Investment Grade OAS spread
            # "gpr_world" removed 2026-06-10: GPRH/GPRD/GPR do not exist on
            # FRED (Caldara-Iacoviello GPR is not FRED-hosted) — the fetch
            # failed on every run, so no feature ever existed and removal is
            # behavior-identical. FRED-hosted uncertainty proxies exist
            # (USEPUINDXD daily, GEPUCURRENT monthly); adding one is a NEW
            # feature → registered evolution-loop candidate, not a hand-edit.
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
        # C4 (2026-08-04): FRED indexes observations by REFERENCE-PERIOD date,
        # not release date. Features built by reindex+ffill on that index see
        # prints weeks before the public did. Each series' index is shifted
        # forward by this many calendar days before it may enter a feature
        # matrix (conservative release lags, rounded up). None = the series is
        # EXCLUDED from model features entirely: RECPROUSM156N is published
        # ~3 months late AND retrospectively re-smoothed, so its historical
        # values were never observable as recorded — irreparable look-ahead.
        # (Dashboard/display uses may still read it; models may not.)
        "fred_publication_lag_days": {
            "yield_spread": 1,           # daily market rate
            "sahm_rule": 40,             # real-time version, out with jobs report
            "insured_unemployment_rate": 14,   # weekly, ~2wk release delay
            "recession_prob": None,      # EXCLUDED — see above
            "unemployment": 40,          # jobs report, first Friday next month
            "cpi": 45,                   # mid-next-month release
            "fed_funds": 35,             # monthly avg, early next month
            "consumer_sentiment": 30,    # final print ~end of reference month
            "vix_fred": 1,
            "hy_oas": 2,
            "ig_oas": 2,
            "consumer_credit": 70,       # G.19: ~5th business day, 2 months on
            "tips_10y": 1,
            "margin_credit": 165,        # Z.1 quarterly, ~10 weeks after quarter
            "mfg_employment": 40,        # jobs report
            "industrial_prod": 45,       # G.17 mid-next-month
            "business_loans": 45,        # H.8 monthly aggregation
            "lei": 60,                   # state leading index, ~2 months
            "sloos_ci": 40,              # quarterly survey, ~5wk after quarter start
            "sloos_cc": 40,
            "initial_claims": 7,         # weekly, following Thursday
            "initial_claims_4wk": 7,
            "nfci": 7,                   # weekly, following Wednesday
        },
        # Unknown/new series get this until a real lag is assigned.
        "fred_publication_lag_default": 45,
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
        # 15 min: users always get an instant SWR hit; the warm loop recomputes
        # on expiry, so this TTL is the compute-cost dial (300s had the two
        # market endpoints recomputing 6x/hr on Railway for a product that
        # refreshes hourly anyway).
        "ttl_market": 900,
        "ttl_sectors": 3600,        # 1 hr for sector analysis
        "ttl_crash": 1800,          # 30 min for crash predictions
        "ttl_news": 900,            # 15 min for news
        "ttl_macro": 300,           # 5 min for macro indicators
        "ttl_simulation": 3600,     # 1 hr for Monte Carlo sims
        "ttl_portfolio": 0,         # No cache — unique per request body
        "ttl_backtest": 86400,      # 24 hr for backtest results
        # Off-hours cost dial (2026-07-16): when US markets are closed the
        # inputs to screener/MC/sector computes don't change, so the warm loop
        # stretches every TTL by this factor — same outputs, ~6x fewer
        # recomputes overnight/weekends. 1 = always-on behavior.
        "offhours_ttl_multiplier": 6,
        # Purge memory-cache entries this old each warm cycle (disk unaffected).
        "sweep_max_age_hours": 24,
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
        # Spend guards: hard daily cap on LLM calls (all providers combined);
        # billing errors (401/402) trip a cooldown breaker so a dead key
        # doesn't get retried on every cache expiry.
        "daily_call_cap": 150,
        "billing_breaker_cooldown_s": 6 * 3600,
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

    # ── PERFORMANCE ──────────────────────────────────────────────────────
    "performance": {
        "screener_max_workers": 8,       # ThreadPoolExecutor workers for screener
        "sector_momentum_workers": 6,    # Workers for parallel sector ETF fetches
        "gdelt_max_workers": 3,          # Workers for parallel GDELT API calls
        "gdelt_max_retries": 2,          # Retry attempts per GDELT endpoint
        "gdelt_retry_base_delay": 1.0,   # Base delay for GDELT retry backoff (seconds)
        # GDELT result cache (2026-07-17): a 30-day tone/volume timeline does
        # not change in 15 minutes, but the endpoint warm loop was refetching
        # it ~3x/hour around the clock — the source of the perpetual 429
        # storm. Successful reads are served for gdelt_cache_ttl; after a
        # failure the (stale-served or unavailable) result is held for
        # gdelt_fail_cooldown so a dead GDELT is not hammered every cycle.
        "gdelt_cache_ttl": 3600,
        "gdelt_fail_cooldown": 900,
        "slow_request_threshold_s": 10.0,# Requests slower than this get a warning log
    },

    # ── FMP DAILY QUOTA BUDGET ───────────────────────────────────────────
    # FMP free tier is ~250 requests/day shared by ALL callers (provider
    # fallback, ESG, congress collector). The pre-registered congress-IC
    # collector died on 402 at its 07:30 ET slot (2026-07-17) because
    # fallback traffic had burned the whole quota overnight — scheduling
    # cannot protect an unmetered shared resource. fmp_budget.py meters it.
    "fmp": {
        "daily_budget": 240,       # spend ceiling (free tier 250; keep headroom)
        "priority_reserve": 40,    # slice only priority callers may draw from
    },

    # ── SENTIMENT ANALYSIS ───────────────────────────────────────────────
    "sentiment": {
        "bullish_threshold": 0.15,          # avg_numeric > 0.15 → bullish
        "slightly_bullish_threshold": 0.05, # avg_numeric > 0.05 → slightly_bullish
        "bearish_threshold": -0.15,         # avg_numeric < -0.15 → bearish
        "slightly_bearish_threshold": -0.05,# avg_numeric < -0.05 → slightly_bearish
        # Unload the ~2 GB FinBERT model after this many minutes without a
        # scoring call (reload from local HF cache ~5-10s). 0 = never unload.
        "finbert_idle_unload_minutes": 45,
    },

    # ── ANALYST INTELLIGENCE (Wall Street consensus display) ────────────
    "analyst_intelligence": {
        "max_actions": 30,             # firm-attributed actions returned
        "actions_lookback_days": 365,  # ignore rating actions older than this
    },

    # ── FIRM BASELINES (published capital market assumptions) ───────────
    # For the model-vs-firm comparison surface. Nominal annualized US
    # large-cap expected returns as PUBLISHED by each firm — display-only
    # anchors, refreshed on the firms' annual cycle (next ~Oct-Dec 2026).
    # Sources + verification: docs/research/DATA_SOURCES_AND_BASELINES_2026-07-16.md
    "firm_baselines": {
        "us_large_cap_expected_return": [
            {"firm": "J.P. Morgan LTCMA 2026", "horizon": "10-15y",
             "low_pct": 6.7, "high_pct": 6.7, "as_of": "2025-10"},
            {"firm": "Vanguard VEMO 2026", "horizon": "5-10y",
             "low_pct": 4.0, "high_pct": 5.0, "as_of": "2025-12"},
            {"firm": "BlackRock CMA", "horizon": "10y",
             "low_pct": 8.5, "high_pct": 8.5, "as_of": "2026-03-31"},
            {"firm": "Schwab", "horizon": "2026-2035",
             "low_pct": 5.9, "high_pct": 5.9, "as_of": "2025"},
            {"firm": "Invesco CMA", "horizon": "10y",
             "low_pct": 5.0, "high_pct": 5.0, "as_of": "2025"},
            {"firm": "AQR", "horizon": "5-10y",
             "low_pct": 6.3, "high_pct": 6.3, "as_of": "2025",
             "note": "3.9% real, ~6.3% nominal-equivalent"},
            {"firm": "Goldman Sachs", "horizon": "10y",
             "low_pct": 6.5, "high_pct": 6.5, "as_of": "2025-11",
             "note": "updated from the Oct-2024 3% call; secondary-sourced "
                     "(primary paywalled) — verify before UI display"},
        ],
        # Documented street 12m price-target behavior (cited, for UI caveats
        # and the TRIAL-FORECAST-LEDGER prior — never our own claim):
        "street_target_hit_rate_note": (
            "Studies: 24% of 12m targets met at horizon end (~100k targets "
            "1997-2002, Bradshaw & Brown WP; peer-reviewed 2013 version on "
            "2000-2009: 38% at horizon end, 64% at some point); S&P 500 "
            "ratings Dec 2025: 57.5% Buy vs 4.8% Sell."
        ),
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
                # MRSH was MMC until 2026-01-14 (Marsh rebrand); XYZ was SQ
                # (Block). Stale entries fetched nothing and read as quiet.
                "SPGI", "C", "AXP", "SCHW", "CB", "MRSH", "ICE",
                "PGR", "CME", "AON", "COIN", "XYZ",
            ],
            "Energy": [
                # PXD delisted 2024 (ExxonMobil acquisition) — removed, not
                # renamed; a dead ticker in a sector list reads as a calm one.
                "XOM", "CVX", "COP", "SLB", "EOG", "MPC", "OKE",
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
                # EA delisted 2026-08-04 (PIF-led $55B buyout completed;
                # quotes ghosted on for days after trades stopped — found by
                # the trades-vs-quotes count in the effective-spread pull).
                "RBLX", "SPOT", "TTWO", "WBD", "CHTR",
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

    # ── EXIT ENGINE & POSITION SIZING ────────────────────────────────────
    # The research-backed fix for the disposition effect ("sold NVDA too
    # early" — Odean 1998): mechanical ATR trailing stops that let winners
    # run, plus volatility-targeted / fractional-Kelly sizing. Pure,
    # stateless helpers in services/exit_engine.py. DESCRIPTIVE until a
    # pre-registered backtest (TRIAL-THEME, see docs/research/) clears the
    # DSR/PBO gate — NO live lane uses these yet. Grid params feed the sweep
    # so every variant is counted against the cumulative trial count.
    "exit_engine": {
        "atr_period": 14,              # Wilder ATR lookback (trading days)
        "atr_stop_multiple": 3.0,      # Chandelier exit: stop = peak_close - k*ATR
        "atr_multiple_grid": [2.0, 2.5, 3.0, 3.5, 4.0],  # registered sweep variants
        "vol_target_annual": 0.20,     # target per-position annualized vol
        "vol_lookback_days": 63,       # realized-vol window for sizing
        "max_position_weight": 0.25,   # hard cap per name (concentration guard)
        "kelly_fraction": 0.25,        # fractional Kelly multiplier (quarter-Kelly)
        "kelly_cap": 0.25,             # never size above this from Kelly alone
        "trading_days_year": 252,
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

    # ── EVENT-INTEL (descriptive news brain) ────────────────────────────
    # Structured events over EXISTING feeds. Adopted 2026-07-29B under a
    # binding acceptance spec (docs/research/ROADMAP_2026-07-29_POST_FREEZE.md):
    # descriptive-only, no buy/sell language, failed feed = disclosed
    # unavailable, direction always relative to the scope entity. The LLM
    # classifies into ENUMS only — every rendered sentence is templated, so
    # the no-advice playbook is enforced by construction.
    "event_intel": {
        "max_headlines_per_ticker": 8,   # LLM batch size; 500-token responses cap this
        "max_tickers_per_brief": 10,
        "news_window_days": 7,           # headlines older than this are not events
        "edgar_days_back": 30,
        "earnings_window_days": 30,      # past results + upcoming dates within this
        "cache_ttl": 900,                # matches ttl_news
        "canary_ticker": "AAPL",         # high-volume filer/newsmaker; empty canary
        "canary_ttl": 3600,              #   = feed suspect, disclosed (never quiet zero)
        # Deterministic direction keywords (fallback when LLM unavailable).
        # Matched case-insensitively on headline text -> direction IMPLIED, tier LOW.
        "positive_keywords": [
            "beats", "beat estimates", "tops estimates", "raises guidance",
            "raises outlook", "approval", "approves", "wins", "record revenue",
            "record profit", "upgrade", "upgraded", "buyback", "dividend increase",
            "exceeds expectations", "settles", "clears",
        ],
        "negative_keywords": [
            "misses", "missed estimates", "cuts guidance", "lowers outlook",
            "recall", "probe", "investigation", "lawsuit", "downgrade",
            "downgraded", "layoffs", "bankruptcy", "default", "delisting",
            "restatement", "resigns", "halts", "warns", "shortfall",
        ],
        # 8-K item codes with an EXPLICIT direction (the filing type itself
        # carries it). Everything else in the taxonomy -> direction unknown.
        "edgar_item_direction": {
            "1.03": "negative",          # bankruptcy/receivership
            "2.04": "negative",          # triggering events accelerating obligations
            "3.01": "negative",          # delisting / listing-standard notice
            "4.02": "negative",          # non-reliance on prior financials
        },
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
        raise ImportError("PyYAML required for paper portfolio config: pip install pyyaml")


paper_portfolios: dict = load_paper_portfolios()


def load_book_lanes() -> dict:
    """Load book-lane definitions (P1 #6 mirror/conviction) from a SEPARATE YAML.

    Kept apart from paper_portfolios.yaml on purpose: that file's whole-file hash
    versions the 4 reference lanes, so adding book lanes there would fire a
    spurious config-change rebalance and corrupt TRIAL-001. See book_lanes.yaml.
    Read-only at process start.
    """
    yaml_path = BACKEND_DIR / "data" / "book_lanes.yaml"
    if not yaml_path.exists():
        return {}
    try:
        import yaml
        with open(yaml_path, "r") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        raise ImportError("PyYAML required for book-lane config: pip install pyyaml")


book_lanes: dict = load_book_lanes()

#: Cash sweep for a book whose cash balance is UNRECOVERABLE (murat_book.yaml
#: `cash: null`). NIGHT-13 §0: unknown cash is a SENSITIVITY PARAMETER, never a
#: silent zero. Each entry is cash as a FRACTION of the marked equity NAV; the
#: engine reports NAV and weights across the whole grid and probabilities as
#: ranges over its endpoints. House pattern: grid-report-never-pick — a ranking
#: over a convex sweep is a theorem, not a finding (counterfactual_replay
#: INTERPOLATING; conviction_replay.measure_mde).
CASH_SENSITIVITY_GRID: tuple[float, ...] = (0.0, 0.02, 0.05, 0.10, 0.20)


def load_conservative_atr_lanes() -> dict:
    """Load the conservative-ATR lane definition (TRIAL-EXIT) from a SEPARATE YAML.

    Kept apart from paper_portfolios.yaml for the same load-bearing reason as the
    book lanes: that file's whole-file hash versions the 4 reference lanes, so
    adding this lane there would fire a spurious config-change rebalance and
    corrupt TRIAL-001 / alter the frozen conservative control. See
    conservative_atr_lanes.yaml. Read-only at process start.
    """
    yaml_path = BACKEND_DIR / "data" / "conservative_atr_lanes.yaml"
    if not yaml_path.exists():
        return {}
    try:
        import yaml
        with open(yaml_path, "r") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        raise ImportError("PyYAML required for conservative-ATR config: pip install pyyaml")


conservative_atr_lanes: dict = load_conservative_atr_lanes()


def load_smallmid_quality_lanes() -> dict:
    """Load the smallmid-quality lane definition (TRIAL-SMQ-FWD) from a SEPARATE
    YAML — same load-bearing isolation reasoning as the book and ATR lanes: its
    holdings ARE the strategy, so the file carries its OWN hash and a quarterly
    refresh is a stamped config-version change, never a silent edit."""
    yaml_path = BACKEND_DIR / "data" / "smallmid_quality_lanes.yaml"
    if not yaml_path.exists():
        return {}
    try:
        import yaml
        with open(yaml_path, "r") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        raise ImportError("PyYAML required for smallmid-quality config: pip install pyyaml")


smallmid_quality_lanes: dict = load_smallmid_quality_lanes()


def load_tsmom_xa_lanes() -> dict:
    """Load the TSMOM-XA lane pair (TRIAL-TSMOM-XA) from a SEPARATE YAML —
    same load-bearing isolation reasoning as the book/ATR/SMQ lanes: the
    frozen signal params ARE the strategy, so the file carries its OWN hash
    and any change is a stamped config-version boundary, never a silent edit."""
    yaml_path = BACKEND_DIR / "data" / "tsmom_xa_lanes.yaml"
    if not yaml_path.exists():
        return {}
    try:
        import yaml
        with open(yaml_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        raise ImportError("PyYAML required for TSMOM-XA config: pip install pyyaml")


tsmom_xa_lanes: dict = load_tsmom_xa_lanes()


# ─────────────── signal universe bands (NIGHT-10, RECO-1) ────────────────────
# The signal registry records the universe each signal was measured in, and
# until NIGHT-10 nothing enforced it: `profitability_small` — whose own registry
# entry says "Net-dead in large/mid" — was ranking NVDA, AAPL and META in the
# opportunity funnel. Borrowing evidence from a segment where the effect was
# measured to be absent is the same defect as ranking on a closed signal; it
# just had no printed name. `backend/services/recommendation.py` gates on these.
#
# Bands are dollar market cap. CRSP's small segment is a percentile breakpoint,
# not a dollar one, so these are a deliberately conservative operationalisation:
# a name only counts as small if it is unambiguously small.
SIGNAL_UNIVERSE_SMALL_MAX_USD = 2_000_000_000.0
SIGNAL_UNIVERSE_MID_MAX_USD = 10_000_000_000.0

#: registry `universe` string -> the cap band(s) a signal may be applied to.
#: A signal whose universe string is not listed here is treated as UNKNOWN and
#: gets no rank influence — unknown is not a free pass (same rule as
#: `reliability_weight: null` resolving to UNCALIBRATED rather than to 1.0).
#
# Every universe string that appears in the registry is listed, so that a
# signal blocked here is blocked by the SIZE gate deliberately, and never by an
# accidental gap in this table. Strings describing a non-equity or non-size
# scope (index level, asset classes) map to the empty set: they can never lead
# a cross-sectional stock ranking, which is the correct reading of their own
# registry entries.
SIGNAL_UNIVERSE_BANDS: dict = {
    "CRSP": {"small", "mid", "large"},
    "CRSP small segment": {"small"},
    "CRSP small/mid": {"small", "mid"},
    "CRSP largemid": {"mid", "large"},
    "CRSP US common, large/mid and small segments": {"small", "mid", "large"},
    "CRSP + Form 4": {"small", "mid", "large"},
    "CRSP + IBES": {"small", "mid", "large"},
    "CRSP + Thomson 13F": {"small", "mid", "large"},
    "CRSP + link tables": {"small", "mid", "large"},
    "US listed": {"small", "mid", "large"},
    "optionable US equity": {"mid", "large"},
    "optionable names in the book": {"mid", "large"},
    "biotech": {"small", "mid", "large"},
    "masked profitability slate": {"small", "mid", "large"},
    "Murat's book + watchlist": {"small", "mid", "large"},
    "Murat's book + funnel candidates": {"small", "mid", "large"},
    "news/filings for the book": {"small", "mid", "large"},
    # Not cross-sectional stock scopes at all — never licensed to rank names.
    "index level": set(),
    "asset classes, never single stocks": set(),
    # Universes a trial has not declared yet. Undeclared is not permission.
    "to be declared": set(),
    "to be declared by ANALYST-REVISION-1": set(),
}


# ─────────── Investment Committee (NIGHT-13 §2: graceful degradation) ────────
# Adopted ruling: when evidence cannot fill a book, the answer is a low-cost
# benchmark core plus evidence-scaled tilts — never an empty page, never a
# refusal. Every parameter of that composition lives here.

#: Funnel run the IC page reads. Missing file degrades to pure benchmark core
#: with degradation_reason "no funnel run available" — never a 500.
#: Lives under backend/data (NOT docs/): .dockerignore excludes docs, so a
#: docs path would make the IC permanently degraded in every prod image while
#: green locally — the insider-collector failure shape (NIGHT-13 audit F1).
IC_FUNNEL_PATH = BACKEND_DIR / "data" / "funnel_night10.json"

#: TTL for the funnel-derived state (gate + ranking + archetype books). The
#: funnel is a nightly artifact; composition itself is computed per request.
IC_FUNNEL_TTL = 3600

#: Headline capital levels the committee page composes a book for. A subset of
#: capital_frontier.CAPITAL_LEVELS — the retail-to-small-fund range the page
#: is answering for.
IC_CAPITAL_LEVELS: tuple = (10_000.0, 40_000.0, 1_000_000.0)

#: Benchmark core template (portfolio_engine._ALLOCATION_TEMPLATES key).
#: "moderate", not "aggressive", deliberately: the IC book exists BECAUSE the
#: evidence could not fill an archetype on its own. Pairing thin evidence with
#: the highest-volatility template would take risk the evidence does not
#: license — and Murat's own record shows the damage is done by SIZING, not
#: timing (NIGHT-12: dd 22.9% vs SPY 8.9% at beta 2.15). The core must be the
#: thing that is defensible with ZERO tilts.
IC_BENCHMARK_TEMPLATE = "moderate"

#: Hard cap on any single evidence-led tilt. CVLG-sized: even the one name
#: that clears the BUY gate today is a single-name bet resting on one or two
#: SUPPORTED (not VALIDATED) signals with no calibrated expected return.
IC_SINGLE_NAME_TILT_CAP = 0.03

#: Ceiling on the SUM of all evidence tilts. The core is the product; the
#: tilts are the garnish, and they stay that way until the evidence grows.
IC_TOTAL_TILT_BUDGET = 0.10

#: At most this many tilt names (best rank first) — a page of 0.5% slivers is
#: noise wearing a book's clothes.
IC_MAX_TILT_NAMES = 10

#: Evidence-strength scaling for tilt size: tilt = cap x verdict x confidence.
#: WATCH is half a BUY; confidence steps follow recommendation._confidence
#: (count of independent licensed pickers). NONE-confidence never tilts.
IC_TILT_VERDICT_SCALE: dict = {"BUY": 1.0, "WATCH": 0.5}
IC_TILT_CONFIDENCE_SCALE: dict = {"NONE": 0.0, "LOW": 1 / 3,
                                  "MEDIUM": 2 / 3, "HIGH": 1.0}

# Ruin-beside-dream defaults for pm_actions.simulate_wealth, scaled to the
# capital being composed. 1.5x at 24 months is a STRETCH target (~22.5%/yr) —
# printed as a dream precisely so the ruin number beside it stays honest;
# floor/ruin at 70%/50% of starting capital match the pm wealth-target idiom.
IC_WEALTH_HORIZON_MONTHS = 24
IC_WEALTH_TARGET_MULT = 1.5
IC_WEALTH_FLOOR_MULT = 0.7
IC_WEALTH_RUIN_MULT = 0.5
#: Monte Carlo draws for the IC wealth simulation (endpoint-latency bound;
#: pm_actions defaults to 20k, the IC runs one sim per capital level).
IC_WEALTH_DRAWS = 8000

#: Scenario assumptions (annual mu, vol) for the benchmark-core ETFs, used
#: ONLY by the wealth simulation. These are long-run institutional-consensus
#: style numbers (cf. "MC 5Y annualized +2% to +8%" healthy range), NOT
#: engine forecasts — the page says so in its honesty block.
IC_CORE_ASSUMPTIONS: dict = {
    "VTI":  {"mu": 0.059, "vol": 0.16},
    "VXUS": {"mu": 0.060, "vol": 0.17},
    "BND":  {"mu": 0.045, "vol": 0.06},
    "VTIP": {"mu": 0.035, "vol": 0.05},
    "GLD":  {"mu": 0.030, "vol": 0.15},
    "VNQ":  {"mu": 0.055, "vol": 0.20},
    "QQQ":  {"mu": 0.065, "vol": 0.22},
    "MTUM": {"mu": 0.060, "vol": 0.18},
    "VGT":  {"mu": 0.065, "vol": 0.23},
}

#: Evidence tilts get the EQUITY-CORE drift in the wealth sim, not a premium:
#: the licensed pickers are an ORDERING, not a magnitude, so the simulation
#: grants a tilt extra volatility (its own) and zero extra expected return.
IC_TILT_ASSUMED_RETURN = 0.059
IC_TILT_FALLBACK_VOL = 0.50


# ── TRANSACTION-ENSEMBLE-1 (prereg frozen at Aegis module c5b81aa) ───────────
# Generator parameters for the licensed substitute for Murat's missing broker
# records: an ensemble of transaction histories consistent with declared
# maximal-consistent anchor subsets. SYNTHETIC — no member is his history.
# The range across members IS the result; nothing here may be collapsed to a
# preferred member (that would be the outcome-shopping the prereg refuses).

#: Master seed; member i uses np.random.default_rng([TE_MASTER_SEED, i]).
TE_MASTER_SEED = 20260811
#: Members per declared-subset arm x 8 arms ({} plus the 7 subsets of {7,8,9})
#: x 2 QUBT arms. 8 x 2 x 15 = 240 >= the prereg's 200.
TE_MEMBERS_PER_ARM = 15
#: Attempts before a (subset, seed) slot is reported unfilled (a finding).
TE_MAX_ATTEMPTS_PER_MEMBER = 500
#: Anchor 6 — cash unknown at every date, swept 0-30% of NAV. Checked at the
#: dates the record actually pins the book (Jan sheet date, conviction log date).
TE_CASH_FRAC_RANGE = (0.0, 0.30)
#: The three annotated exits (TVTX 34.4 / ALMS 10 / SLDP 8.1) must land on a
#: day whose close is within this fraction of the stated fill.
TE_EXIT_PRICE_TOL = 0.06
#: Unknown-share positions sized as U(range) x the median dollar value of the
#: KNOWN positions (DKNG 150, NTLA 250 at the same date's close).
TE_WEIGHT_MULT_RANGE = (0.3, 3.0)
#: Probability a known-final-count position was built in two tranches, and the
#: initial fraction range. Buy-constant-shares-per-episode is otherwise forced,
#: which would narrow the family more than the records justify.
TE_TRANCHE_PROB = 0.5
TE_TRANCHE_INITIAL_FRAC = (0.3, 1.0)
#: Price bars start 2025-10-27; anchors 7/8/9 reach back further. The uncovered
#: months enter as ONE bounded free parameter per anchor — the book's return
#: over the gap — and the report states how much work the gap does. An anchor
#: satisfiable only by a gap outside these bounds is INCONSISTENT for that
#: member.
TE_GAP_RETURN_BOUNDS = (-0.50, 1.50)
#: Tolerance on the dollar anchors (7's $15,165 / implied levels, 9's $45k).
TE_DOLLAR_TOL = 0.10
#: Anchor 7 — "+73.7% / +$15,165 over ~1yr" (docs/NIGHT13_BRIEFING.md §1).
#: Implies start ~$20,577 and end ~$35,742; the ~1yr window's end date is
#: unknown and swept over this window (disclosure was 2026-08).
TE_ANCHOR7_PCT = 0.737
TE_ANCHOR7_DOLLARS = 15165.0
TE_ANCHOR7_END_WINDOW = ("2026-06-01", "2026-08-10")
#: Anchor 8 — "2025 +115%" (raw_text_2026-01-13.txt line 2).
TE_ANCHOR8_PCT = 1.15
#: Anchor 9 — "$25k -> $45k" legacy figure (docs/PORTFOLIO_MANAGER_v1.md).
TE_ANCHOR9_START = 25000.0
TE_ANCHOR9_END = 45000.0
#: Anchor 5 — QUBT 300 is Murat-authoritative; 200 (book_lanes) kept as a
#: bound arm, never dropped.
TE_QUBT_ARMS = (300.0, 200.0)
#: Anchor 10 takeout-proceeds treatments (the `reinvest_in` sensitivity
#: CONVICTION-REPLAY-1 named but never implemented).
TE_TAKEOUT_TREATMENTS = ("idle_cash", "spy", "pro_rata")
#: APLT has NO surviving bars: 0.80 on his Nov sheet, 0.09 on his Jan sheet,
#: $0.088 cash on 2026-02-03. WHEN it collapsed inside Nov->Jan is unknown, so
#: the drop date is a sampled ensemble dimension, not an assumption.
TE_APLT_JAN_MARK = 0.09
#: Declared-subset arms over the mutually unreconciled anchors {7,8,9};
#: () = always-on anchors 1-6,10 only.
TE_SUBSETS = ((), (7,), (8,), (9,), (7, 8), (7, 9), (8, 9), (7, 8, 9))
#: Magnitude classes for the frozen grading rule (pts): |x| < 5 small,
#: 5 <= |x| < 20 moderate, >= 20 large. sign+class must agree across every
#: member of every maximal consistent subset for `ensemble_robust`.
TE_MAGNITUDE_CLASS_EDGES = (5.0, 20.0)
#: The covered window (price panel) and the war sub-window (FACTORIAL-PM-1 H3).
TE_WINDOW = ("2025-11-07", "2026-08-10")
TE_WAR_WINDOW = ("2026-06-04", "2026-07-29")

# ── LLM CALL TELEMETRY (NIGHT-14) ────────────────────────────────────────────
#: Per-model list prices in USD per 1,000,000 tokens, used by
#: `backend/services/llm_telemetry.py` to price every recorded inference call.
#:
#: THESE ARE POINT-IN-TIME LIST PRICES AND THEY DRIFT. Nothing here is a billed
#: amount: the provider invoice is the only authority, and every cost this table
#: produces is labelled an ESTIMATE all the way out to the summary. If a rate
#: changes and this table does not, the ledger is wrong by exactly that drift
#: and by nothing else — which is a knowable error, unlike the alternative.
#:
#: A model absent from this table is priced None, not 0.0, and the caller logs a
#: WARNING (see `llm_telemetry.price_call`). A fabricated zero would be summed
#: into a spend total and read as "free" on every dashboard — the house failure
#: mode of a number that is wrong in the direction of looking fine. Adding a
#: model here is the fix; guessing its price is not.
#:
#: `cached_in` is the discounted rate for input tokens served from a prompt
#: cache. Anthropic's cache-read rate is 0.1x list input; DeepSeek publishes its
#: own cache-hit rate. The two providers disagree about whether cached tokens
#: are counted inside or beside the input count — `llm_telemetry.extract_usage`
#: normalises that, so this table only needs the three rates.
LLM_PRICE_AS_OF = "2026-08-12"
#: CORRECTED 2026-08-12 against the live account. `GET /models` returns EXACTLY
#: TWO ids — `deepseek-v4-flash` and `deepseek-v4-pro`. The names this codebase
#: has always used are SERVER-SIDE ALIASES, verified by reading `model` off the
#: response body:
#:
#:     asked "deepseek-chat"     -> served deepseek-v4-flash
#:     asked "deepseek-reasoner" -> served deepseek-v4-flash   <- SILENT ALIAS
#:     asked "deepseek-v4-pro"   -> served deepseek-v4-pro
#:
#: Two consequences, both paid for:
#:  1. Any experiment whose ARMS were "chat vs reasoner" compared v4-flash with
#:     ITSELF. That is a null manufactured by a config bug, not a finding.
#:     Callers that care about the model MUST read `served_model` off the
#:     response and store it — never trust the requested name.
#:  2. The old prices below (0.27/1.10 and 0.55/2.19) were for models that no
#:     longer exist under those names, and they overstated the true cost by
#:     ~2.8x. The governor was braking on a number that was wrong in the
#:     direction of looking expensive, which is the safe direction and still
#:     wrong. Real rates from api-docs.deepseek.com/quick_start/pricing.
#:
#: Note `cached_in` for v4-flash is FIFTY TIMES cheaper than a cache miss
#: ($0.0028 vs $0.14). Sharing a long common prefix across the arms of an
#: experiment is therefore worth more than any other cost optimisation
#: available to us.
LLM_PRICE_PER_MTOK: dict[str, dict[str, float]] = {
    # DeepSeek — the workhorse for specialists and research roles.
    "deepseek-v4-flash": {"in": 0.14, "cached_in": 0.0028, "out": 0.28},
    "deepseek-v4-pro": {"in": 0.435, "cached_in": 0.003625, "out": 0.87},
    # Legacy aliases. Both resolve server-side to v4-flash, so they are priced
    # as v4-flash. Kept because call sites still send these strings.
    "deepseek-chat": {"in": 0.14, "cached_in": 0.0028, "out": 0.28},
    "deepseek-reasoner": {"in": 0.14, "cached_in": 0.0028, "out": 0.28},
    # Anthropic — used by llm_analyzer/copilot when ANTHROPIC_API_KEY is set.
    "claude-opus-5": {"in": 5.00, "cached_in": 0.50, "out": 25.00},
    "claude-opus-4-8": {"in": 5.00, "cached_in": 0.50, "out": 25.00},
    "claude-sonnet-5": {"in": 3.00, "cached_in": 0.30, "out": 15.00},
    "claude-sonnet-4-6": {"in": 3.00, "cached_in": 0.30, "out": 15.00},
    "claude-haiku-4-5": {"in": 1.00, "cached_in": 0.10, "out": 5.00},
}
#: Env var that overrides the telemetry ledger path. Named here rather than
#: hardcoded in the service so a deploy can move the file with the rest of the
#: data-dir configuration.
LLM_TELEMETRY_PATH_ENV = "AEGIS_LLM_TELEMETRY_PATH"

# ── WHY-MOVED (NIGHT-14): explaining a day's move, gradeably ────────────────
# The deterministic attribution is arithmetic; everything below it is a
# parameter of how the LANGUAGE MODEL's explanations get CHECKED. None of it
# decides what caused the move — see backend/services/why_moved.py.

#: The market leg of the decomposition. Book beta x this instrument's return.
WHY_MOVED_BENCHMARK = "SPY"
#: Trading days of history used to estimate each position's beta. One year is
#: long enough to be an estimate and short enough to be about the current book.
WHY_MOVED_BETA_LOOKBACK_DAYS = 252
#: Fewer overlapping bars than this and the beta is not estimated at all — the
#: position is carried at beta 1.0 and NAMED in `beta_fallbacks`, because a
#: beta fitted on eleven days is a random number with a t-stat.
WHY_MOVED_MIN_BETA_OBS = 60
#: Calendar days of price history requested so the beta window can be filled.
WHY_MOVED_PRICE_PAD_DAYS = 420
#: Sector leg: the traded proxy for each GICS sector. A sector return that is
#: not a tradeable instrument cannot be checked, so the proxy is an ETF.
WHY_MOVED_SECTOR_ETFS = {
    "Health Care": "XLV",
    "Information Technology": "XLK",
    "Industrials": "XLI",
    "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP",
    "Energy": "XLE",
    "Financials": "XLF",
    "Materials": "XLB",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Communication Services": "XLC",
}
#: Ticker -> GICS sector for the securities the book actually holds. Declared
#: here rather than fetched: a vendor sector field that changes silently would
#: re-cut a past attribution, and an unmapped ticker is reported by name
#: (`sector_unmapped`) instead of being quietly folded into the market leg.
WHY_MOVED_TICKER_SECTOR = {
    "AARD": "Health Care",
    "ABSI": "Health Care",
    "AMSC": "Industrials",
    "BHVN": "Health Care",
    "DKNG": "Consumer Discretionary",
    "HUBS": "Information Technology",
    "KYTX": "Health Care",
    "NTLA": "Health Care",
    "PRCH": "Information Technology",
    "QUBT": "Information Technology",
    "SLDP": "Consumer Discretionary",
    "SOC": "Energy",
}
#: The instruments a specialist may point at when it states a cross-asset
#: signature. Offered in the prompt and used as the ONLY whitelist for a
#: forward claim's subject, so every assertion lands on something the resolver
#: can actually price. ^TNX is the 10-year yield ITSELF (not a bond price):
#: "^TNX up" means yields rose.
WHY_MOVED_CORROBORATION_UNIVERSE = (
    "SPY", "QQQ", "IWM", "DIA", "RSP",
    "TLT", "IEF", "SHY", "HYG", "LQD", "^TNX", "^IRX",
    "GLD", "SLV", "USO", "CL=F", "BZ=F", "NG=F", "DBC",
    "^VIX", "^VIX3M", "UUP", "FXE",
    "XLE", "XLK", "XLV", "XLF", "XLI", "XLY", "XLP", "XLB", "XLU", "XLRE",
    "XLC", "XBI", "IBB", "ITA", "SMH", "ARKK", "KRE",
    "EEM", "EFA", "FXI", "EWZ", "BTC-USD",
)
#: Ceilings on what one specialist may return. Not a style preference: an
#: unbounded list of assertions lets a forecaster spray until something hits,
#: and the hit RATE is the number this module exists to measure.
WHY_MOVED_MAX_HYPOTHESES_PER_SPECIALIST = 4
WHY_MOVED_MAX_CORROBORATION_PER_HYPOTHESIS = 4
#: `min_abs_move_pct` on a magnitude assertion is stated in PERCENT (3.0 = 3%),
#: deliberately unlike belief_state thresholds, which are decimal fractions.
#: Both bounds are refusals, not clamps: below the floor the assertion is not a
#: claim (anything moves 0.01%), above the ceiling it is a units error.
WHY_MOVED_MAGNITUDE_MIN_PCT_FLOOR = 0.25
WHY_MOVED_MAGNITUDE_MAX_PCT = 100.0
#: CANON §20. Two hypotheses are the SAME idea when they assert the same
#: cross-asset signature, or when their claim wording overlaps at least this
#: much (Jaccard over content tokens). Components, not rows, are the
#: denominator for any statement about a batch.
WHY_MOVED_IDEA_JACCARD = 0.6
#: Tokens carrying no idea; excluded before the Jaccard so "the market fell on
#: rates" and "the market fell on earnings" do not read as one idea.
WHY_MOVED_STOPWORDS = (
    "the", "a", "an", "of", "on", "in", "to", "and", "or", "for", "with",
    "as", "at", "by", "from", "that", "this", "is", "was", "were", "be",
    "been", "its", "it", "their", "was", "has", "have", "had", "s",
)
#: DeepSeek settings for the seven lenses. Cheap by design — the point is to
#: spend calls on output that can be graded within days.
WHY_MOVED_MODEL = "deepseek-chat"
WHY_MOVED_TEMPERATURE = 0.4
#: 2400 truncated the geopolitical lens mid-JSON on the first live run
#: (2026-08-10) — the module counted it as a rejection rather than crashing,
#: which is correct behaviour but a wasted call. Seven hypotheses with causal
#: chains and evidence rows run to ~9k characters.
WHY_MOVED_MAX_TOKENS = 4000
WHY_MOVED_LLM_TIMEOUT_S = 180
#: Price panels are stable once the day has closed; an hour is plenty and
#: keeps a page refresh off the vendor.
WHY_MOVED_PRICE_CACHE_TTL = 3600
#: Descriptive only, house rule. A hypothesis whose text reaches for an action
#: is refused rather than sanitised — the sanitised version would still have
#: been written by a forecaster that thought it was allowed to advise.
WHY_MOVED_FORBIDDEN_PATTERN = (
    r"\b(buy|sell|hold|trim|add to|overweight|underweight|allocate|"
    r"position size|take profit|stop loss|we recommend|you should)\b"
)


# ── RESEARCH LLM BUDGET (GRAND-ARENA-1 Phase 0) ──────────────────────────────
#: PRODUCTION AND RESEARCH ARE DIFFERENT BUDGETS, AND UNTIL NOW ONLY ONE OF
#: THEM EXISTED.
#:
#: `llm.daily_call_cap = 150` guards the PRODUCTION path (llm_analyzer) and was
#: sized for a $20 prepaid balance. It is the right shape for a user-facing
#: endpoint: a runaway loop there burns a balance the product depends on.
#:
#: The premise worth correcting is that this cap was throttling research. It was
#: not — it never applied. `why_moved` and `optimus_specialists` construct their
#: own client and call DeepSeek directly, so the research swarm was not
#: throttled, it was UNGOVERNED. For a campaign of thousands of calls that is
#: the more dangerous of the two failures: nothing would have stopped a bad loop
#: except the vendor's balance running out, and the first symptom would have
#: been a dead key on the production path that shares it.
#:
#: So the fix is not "raise the cap". It is a SEPARATE, explicit research budget
#: that the swarm paths actually consult, leaving the production guard where it
#: is. Both a call ceiling and a dollar ceiling, because they fail differently:
#: a cheap-model loop hits the call ceiling first, an expensive-model or
#: long-context run hits the dollar ceiling first.
#:
#: Enforcement reads the telemetry ledger, which is the only place that knows
#: what was actually spent. A budget checked against a counter that resets on
#: process restart is not a budget.
RESEARCH_LLM_ENABLED = os.getenv("AEGIS_RESEARCH_LLM", "1") not in ("0", "false", "")
#: Per-campaign ceilings. Deliberately generous relative to observed cost
#: (~$5.26 for 40M tokens historically) and deliberately FINITE.
#: THE CEILING MUST BIND BEFORE THE VENDOR BALANCE DOES.
#:
#: Amendment A12 raised this to $150 on "don't worry about the cost". That was
#: wrong, and not because $150 is a lot to spend — because the account holds
#: ~$10. A ceiling above the balance is not a ceiling at all: the vendor balance
#: becomes the real limit, and the first symptom of hitting it is a 402 on the
#: PRODUCTION path, which shares the key. That is precisely the failure this
#: governor was built to prevent, reintroduced by setting the number too high.
#:
#: RULE: keep the dollar ceiling BELOW the actual DeepSeek balance, with
#: headroom. Raise it in the same motion as a top-up, not before one, via
#: AEGIS_RESEARCH_LLM_MAX_USD.
#: 2026-08-12: balance topped up to ~$50, so the ceiling moves to $40 —
#: still below it, still with headroom, per the rule above.
#:
#: Measured unit cost, for sizing this: the 8,014-call swarm cost $12.04, i.e.
#: **$0.0015 per call** (~2,500 tokens in / 900 out). Nightly WHY-MOVED is ~7
#: lens calls with a larger prompt, roughly $0.03/night — under $1/month.
#: RAISED 2026-08-13, 40,000 -> 120,000, and the reason is not "we hit it".
#:
#: The call ceiling was a PROXY for the dollar ceiling, sized when a call was
#: believed to cost $0.0015. At that price 40,000 calls was ~$60 and the dollar
#: ceiling bound first, which is correct: dollars are what is actually scarce
#: and what the vendor balance limits. The measured price is $0.00039, so the
#: proxy became the binding constraint and halted LLM-ARCHITECTURE-ARENA-1 at
#: 89% coverage while only $16.53 of $40 had been spent.
#:
#: A proxy that binds before the thing it stands for is not a safety mechanism;
#: it is an arbitrary stop whose number no longer means anything. 120,000 at the
#: measured rate is ~$47, so the $40 dollar ceiling binds again — and that
#: ceiling remains BELOW the vendor balance, which is the rule that matters.
RESEARCH_LLM_MAX_CALLS = int(os.getenv("AEGIS_RESEARCH_LLM_MAX_CALLS", "120000"))
RESEARCH_LLM_MAX_USD = float(os.getenv("AEGIS_RESEARCH_LLM_MAX_USD", "40.0"))
#: A call is only worth its money if it produces something gradeable. If the
#: share of calls yielding NO prediction and NO hypothesis exceeds this, the
#: campaign is buying tokens rather than information and should halt for
#: inspection rather than spend the rest of the budget the same way.
RESEARCH_LLM_MAX_ZERO_YIELD_RATE = float(
    os.getenv("AEGIS_RESEARCH_LLM_MAX_ZERO_YIELD", "0.40"))
#: Below this many calls the zero-yield brake is not armed — an early run of
#: unlucky parses would otherwise halt a campaign on n=3.
RESEARCH_LLM_ZERO_YIELD_MIN_N = 50


# ── LLM-SWARM-1 (GRAND-ARENA-1 chunk 3) ──────────────────────────────────────
# Thousands of independent specialist calls, each of which must produce
# something a machine can later grade. Every knob of that campaign lives here;
# `backend/services/llm_swarm.py` reads them and hardcodes none.

#: The workhorse. deepseek-chat is priced in LLM_PRICE_PER_MTOK, so every call
#: lands in the telemetry ledger with a cost rather than as a LOWER BOUND.
SWARM_MODEL = os.getenv("AEGIS_SWARM_MODEL", "deepseek-chat")
#: Warm enough that fourteen roles do not collapse into one voice, cool enough
#: that the JSON contract survives. The §20 measurement is what actually checks
#: this: if the ratio collapses, temperature is the first thing to look at.
SWARM_TEMPERATURE = float(os.getenv("AEGIS_SWARM_TEMPERATURE", "0.6"))
#: The reply is one security's structured view. Generous, because a truncated
#: reply is an unparseable reply and an unparseable reply is money spent for
#: nothing — the single most expensive failure this campaign can have.
SWARM_MAX_TOKENS = int(os.getenv("AEGIS_SWARM_MAX_TOKENS", "1800"))
SWARM_TIMEOUT_S = float(os.getenv("AEGIS_SWARM_TIMEOUT_S", "180"))
#: Concurrency. Measured, not guessed: 12 concurrent trivial requests returned
#: in 2.4s with zero 429s, so 24 is inside the observed envelope and is backed
#: off only on evidence (a counted 429), never pre-emptively.
SWARM_WORKERS = int(os.getenv("AEGIS_SWARM_WORKERS", "24"))
#: Retries on 429/5xx/timeout, with exponential backoff and jitter. A dropped
#: call is never silent: it is counted as failed and reported.
SWARM_MAX_RETRIES = int(os.getenv("AEGIS_SWARM_MAX_RETRIES", "4"))
SWARM_BACKOFF_BASE_S = float(os.getenv("AEGIS_SWARM_BACKOFF_BASE_S", "1.5"))

#: How many forecasts one call may mint. A cap, because an unbounded list lets
#: a forecaster spray until something resolves in its favour, and because the
#: ledger is a shared resource — 8,000 calls x 8 forecasts would bury 112
#: existing records under 64,000 correlated ones.
SWARM_MAX_FORECASTS_PER_CALL = 3
#: A non-abstaining call that produces fewer than this many gradeable forecasts
#: has not met the contract it was asked for. It is still recorded — the
#: shortfall is the finding — but it is counted separately.
SWARM_MIN_FORECASTS_PER_CALL = 2

#: p = 0.50 IS REFUSED, AND THIS IS THE MOST OPINIONATED LINE IN THE FILE.
#: The first WHY-MOVED batch was 23 of 25 one-day `return_sign` claims at
#: exactly 0.50. That accrues records at full speed and says nothing: a coin
#: flip you called a coin flip is not a forecast, it is the absence of one
#: wearing a number. The ABSTAIN channel exists precisely so a specialist with
#: no view has somewhere honest to put it, and abstentions are counted. So an
#: exact 0.50 is a counted rejection rather than a minted record.
SWARM_COIN_FLIP_EPS = 0.005
#: Scenario branch probabilities must sum to one within this tolerance. Same
#: band belief_state.expected_value() uses, so a tree this module accepts is a
#: tree the ledger can price.
SWARM_SCENARIO_PROB_TOL = 0.03
#: The benchmark every `beats_benchmark` forecast is graded against.
SWARM_BENCHMARK = "SPY"
#: Records are appended to the prediction ledger in batches of this size.
#: `belief_state.append` re-reads the whole ledger to dedupe, so appending per
#: call would be quadratic; appending only at the end would lose a crashed
#: run's work.
SWARM_LEDGER_BATCH = 200
#: Trading days of history a security must have at the observation timestamp to
#: enter the universe. A name we cannot price cannot be forecast about and its
#: records could never resolve — the failure would look exactly like a growing
#: pending backlog (belief_state warns about that case for a reason).
SWARM_MIN_HISTORY_BARS = 252


# ── Prediction markets (TRIAL-PREDMARKET-1, registered 2026-08-21) ────────────
#: Kalshi public market-data API. No key, no account, NO EXECUTION — R1
#: (docs/research/R1_LLM_FORECAST_CALIBRATION_2026-08-08.md) recorded 6/6 LLM
#: forecasters losing real capital on Kalshi at crowd-matching Brier, which is
#: why this integration is a measurement feed and can never become an order
#: path. The corpus is DESCRIPTIVE CONTEXT: nothing in any scoring path may
#: read it before a successor trial passes (prereg:
#: "Aegis module"/TRIALS/PREREG_PREDMARKET_1.md).
KALSHI_API_BASE = "https://api.elections.kalshi.com/trade-api/v2"
#: FROZEN in the prereg. Widening the watched categories mid-trial is a
#: parameter change (successor trial), not a config tweak.
PREDICTION_MARKET_CATEGORIES = frozenset({"Economics", "Financials", "Companies"})
#: Collection scope, declared not tuned: contracts closing within this many
#: days (the trial grades <=12mo; the margin covers month boundaries) and with
#: nonzero open interest. Both filters are printed in every receipt.
PREDICTION_MARKET_MAX_CLOSE_DAYS = 400
#: Pagination cap — a runaway cursor loop is an outage, not a bigger snapshot.
#: Hitting it sets pages_truncated in the receipt, which the prereg's
#: contamination clause excludes from grading. 60 was calibrated on a dev
#: smoke that used 57 pages; the FIRST prod snapshot (2026-08-21 17:55 ET)
#: hit the cap and contaminated the day — the open-event universe is larger
#: at the evening snapshot hour. 120 leaves ~2x headroom over the measured
#: 60-page day.
PREDICTION_MARKET_MAX_PAGES = 120
PREDICTION_MARKET_DIR = OPTIMUS_LEDGER_DIR / "prediction_markets"
#: Polymarket Gamma public API (TRIAL-PREDMARKET-2, registered 2026-08-21).
#: Same contract as Kalshi: measurement feed, never an order path. The
#: divergence trial's ESCALATE branch produces a WRITTEN proposal for Murat,
#: never execution.
POLYMARKET_API_BASE = "https://gamma-api.polymarket.com"
#: FROZEN in PREREG_PREDMARKET_2: liquidity floor (USDC) for collection.
POLYMARKET_MIN_LIQUIDITY = 1000.0


# ── Arena personality grading read (OPTIMUS_OBJECTIVE §0.9) ──────────────────
#: DECLARED 2026-08-22, at a moment when ZERO arena NAV rows existed — these
#: are preferences, and preferences are never tuned against history (mission
#: rule 3 / roadmap). Standard CRRA brackets: log utility (rho=1) IS the
#: extreme-growth "maximise expected log wealth" personality; 8 is deep
#: capital preservation. Changing any value is an ATTENDED declaration
#: change, and test_arena_personality_read pins them so it cannot happen
#: silently.
ARENA_PERSONALITY_RHO = {
    "preservation": 8.0,
    "balanced": 4.0,
    "aggressive": 2.0,
    "extreme_growth": 1.0,
}
#: Below this many NAV days a book's CE is four events wearing a statistic —
#: the read refuses it (REFUSED_THIN), mirroring reliability.MIN_CELL_N.
ARENA_PERSONALITY_MIN_DAYS = 60

#: P-day-2026-08-19a (shipped 2026-08-22). From this date, paper_nav rows are
#: stamped with the DATE OF THE PRICE BAR THAT VALUED THEM. Rows BEFORE this
#: date were stamped with the run date while pricing the previous close
#: (measured corr(NAV_t, close_{t-1}) = 0.974 — the 14-pt-gap investigation).
#: Consumers aligning NAV to benchmark closes must use lag-1 for rows before
#: this date and lag-0 from it onward. The mark REFUSES to write a bar-dated
#: row before this date: INSERT OR REPLACE would silently rewrite pre-flip
#: history under the new semantics.
PI_NAV_PRICED_DATE_FROM = "2026-08-23"
