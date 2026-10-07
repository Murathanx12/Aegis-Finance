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


def _repo_root() -> Path:
    """The checkout this configuration describes.

    Mirrors `backend.routers.control._repo_root` deliberately: inside a
    PyInstaller build `__file__` is `<dist>/_internal/backend/config.py`, so the
    default root resolves to `_internal` -- a directory that has no `.env`, no
    trained models and no `backend/data`. The packaged app therefore ran with
    EVERY key absent and said nothing, because `load_dotenv` on a missing file
    is a silent no-op (the frozen-path defect family, 2026-09-10).

    `AEGIS_REPO_ROOT` is set by the desktop shell to the real checkout. The
    fallback stays the source layout, which is correct when running from source.
    """
    env = os.getenv("AEGIS_REPO_ROOT")
    if env and Path(env).is_dir():
        return Path(env).resolve()
    return Path(__file__).resolve().parent.parent


PROJECT_ROOT = _repo_root()

#: Where this module physically sits. Identical to `PROJECT_ROOT / "backend"` on
#: every source run; they differ ONLY inside a frozen build whose shell pointed
#: `AEGIS_REPO_ROOT` at the checkout.
_MODULE_BACKEND_DIR = Path(__file__).resolve().parent

#: `BACKEND_DIR` follows the ROOT, so `DATA_DIR` below (and everything keyed off
#: it) reads the checkout's `backend/data` rather than a fresh empty tree inside
#: the bundle. Unchanged for source runs by construction.
BACKEND_DIR = (PROJECT_ROOT / "backend") if os.getenv("AEGIS_REPO_ROOT") else _MODULE_BACKEND_DIR

#: MODEL_DIR follows BACKEND_DIR, i.e. the checkout — NOT the bundle. It is read
#: only for TRAINED ARTEFACTS (`crash_model.pkl`, `conformal_scores.pkl`), and
#: those are gitignored (`.gitignore` line 14), so they are trained into the
#: checkout and are never in a bundle built anywhere else. The Python modules
#: that live in the same directory (`garch.py`, `hmm.py`) are imported by
#: package name and do not travel through this path, so pointing it at the
#: checkout cannot break an import.
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


# ── Lane D's own Alpaca paper role (chunk 12, T6) ────────────────────────────
#
# Lane D is the 30-minute day-trading book, and its fill-quality receipt (D2) is
# the only thing that can turn `cost_curve.retail_paper` from a DECLARED band
# into a measured rate. It needs its OWN paper account: a fill receipt collected
# on the default or the arena account is a receipt about a different book's
# order flow, and the cost number it produced would be attributed to lane D.
#
# So the names follow the pattern the repo already uses -- `ALPACA_API_KEY_ID` /
# `ALPACA_API_SECRET_KEY` for the default role and `ALPACA_ARENA_*` for the
# arena -- and there is NO FALLBACK. If either half is absent, every consumer
# refuses BY NAME. A fallback to the default account would quietly trade lane D
# on the wrong book, and the failure would look like a working system.
#
# NAMES ONLY EVER LEAVE THIS MODULE. `lane_d_role_status()` returns
# `configured` / `absent` and the two NAMES; it never returns, logs or prints a
# value, and `test_lane_d_alpaca_role.py` reads the AST to say so.

LANE_D_KEY_ID_ENV = "ALPACA_LANE_D_API_KEY_ID"
LANE_D_SECRET_ENV = "ALPACA_LANE_D_API_SECRET_KEY"

#: The names a consumer must NOT silently substitute. Declared rather than
#: implied, because "never fall back" is only enforceable if the thing not to
#: fall back to is written down.
LANE_D_FORBIDDEN_FALLBACKS = ("ALPACA_API_KEY_ID", "ALPACA_API_SECRET_KEY",
                              "ALPACA_ARENA_API_KEY_ID",
                              "ALPACA_ARENA_API_SECRET_KEY")

LANE_D_ROLE_REFUSAL = (
    "lane D's paper role is not configured: set ALPACA_LANE_D_API_KEY_ID and "
    "ALPACA_LANE_D_API_SECRET_KEY")


def lane_d_role_configured() -> bool:
    """True when BOTH halves of lane D's own paper role resolve.

    Both, not either: a key id with no secret is an account nobody can reach,
    and reporting it as configured would move the failure from this line to the
    first request.
    """
    return bool(os.getenv(LANE_D_KEY_ID_ENV, "").strip()
                and os.getenv(LANE_D_SECRET_ENV, "").strip())


def lane_d_role_status() -> dict:
    """`configured` / `absent`, by NAME. Never a value, never a fingerprint.

    The board and every lane-D receipt print this. A status line that said
    nothing when the role was missing would be indistinguishable from a role
    that was working, which is this programme's house failure mode.
    """
    kid = bool(os.getenv(LANE_D_KEY_ID_ENV, "").strip())
    sec = bool(os.getenv(LANE_D_SECRET_ENV, "").strip())
    present = [n for n, ok in ((LANE_D_KEY_ID_ENV, kid),
                               (LANE_D_SECRET_ENV, sec)) if ok]
    absent = [n for n, ok in ((LANE_D_KEY_ID_ENV, kid),
                              (LANE_D_SECRET_ENV, sec)) if not ok]
    return {
        "lane_d_role": "configured" if (kid and sec) else "absent",
        "names_required": [LANE_D_KEY_ID_ENV, LANE_D_SECRET_ENV],
        "names_present": present,
        "names_absent": absent,
        "refusal": None if (kid and sec) else LANE_D_ROLE_REFUSAL,
        "no_fallback": (
            "there is no fallback. Lane D never reads "
            + ", ".join(LANE_D_FORBIDDEN_FALLBACKS)
            + ": a fill-quality receipt collected on another account is a "
              "receipt about another book's order flow, and the cost number it "
              "produced would be attributed to lane D."),
    }


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


# ── THE ROI RULE (chunk 18c, 2026-09-20) ─────────────────────────────────────
# `backend/services/roi_rank.py`, spec
# `docs/research_notes/2026-09-20/spec_decision_engine_and_scenario_gym.md` §B.
# Murat: "it shouldnt make bad dessicions but it cant be sure so it doesnt make
# one. from good decisions and return potetnials it should go with the highest
# ROI." The rule ranks admissible candidates by expected-net-return over
# downside and sizes by fractional Kelly — and it applies to a candidate ONLY
# when both numbers are measured. Everything below is the declared half of that
# sentence; the measured half is `SIGNAL_MEASURED_RETURN`.

#: ONE flag. False restores the verdict x confidence sizing and removes every
#: `roi*` key from the book and from the decision contract, byte for byte.
IC_ROI_RANKING = True


# ── THE EXPLOIT / EXPLORE AUTHORITY SPLIT (chunk 21, 2026-09-20) ─────────────
# `backend/services/decision_authority.py`, roadmap §15.2, from Murat's review
# of the same evening: "the ROI rule scored 0 of 43 while the old heuristic
# still says BUY four — that is internally inconsistent with 'if it can't be
# sure, don't make the bad decision'." Every admissible candidate now carries
# exactly one authority: EXPLOIT (calibrated), EXPLORE (measured but unproven,
# on a fixed paper-risk budget) or REFUSED.

#: The retirement switch for the verdict x confidence heuristic. False — the
#: default from 2026-09-20 — means a name is EXPLOIT, EXPLORE or REFUSED and
#: NOTHING else: `investment_committee._tilt_size` no longer sizes anything on
#: the daily path. True restores the 18c behaviour (ROI where it scored, the
#: heuristic everywhere else) as a one-line revert. `IC_ROI_RANKING = False`
#: still overrides both and restores the pre-18c book byte for byte.
IC_LEGACY_HEURISTIC_SIZING = False

#: The total paper-risk budget for EXPLORE, as a fraction of equity. ADDITIVE
#: to `IC_TOTAL_TILT_BUDGET`, so the day's worst case rises by at most this and
#: the contract prints the addition beside the existing worst case. 2% is
#: Murat's own number ("a tiny fixed paper-risk budget"); at $40,000 of
#: declared capital it is $800 if every explored name goes to zero.
EXPLORE_BUDGET_PCT = 0.02

#: One explored name's slice. 0.25% of equity — deliberately small enough that
#: being wrong about eight of them at once costs 2%, and large enough to buy
#: one share of most names at the configured capital levels.
EXPLORE_PER_NAME_PCT = 0.0025

#: The posterior width when the receipt states NO t on its return: se =
#: this x |monthly_net_pct|. Three sigma of the point estimate is the widest
#: of the three rows in `SIGNAL_MEASURED_RETURN` by construction — "nobody
#: measured the t" must be MORE uncertain than "the t is 1.4", never less, and
#: never a zero.
EXPLORE_UNKNOWN_T_SE_MULT = 3.0

#: The floor a measured read must clear to be worth paper risk at all, in
#: percent per month. Zero: a hypothesis with no positive expected value is
#: not explored, it is refused. (The t floor is `ROI_MIN_T` and governs
#: EXPLOIT only — Murat: "do not require t >= 2 before AEGIS is allowed to
#: learn".)
EXPLORE_MIN_NET_PCT = 0.0

#: The round-trip cost charged to an exploration score, in bps, amortised over
#: the horizon. Charged ON TOP of the receipt's own net ruler — a deliberate
#: double charge that can only lower a score, never raise one. 50 bps is the
#: ruler the explore leg of the measured library declares.
EXPLORE_COST_ROUND_TRIP_BPS = 50.0

#: `exploration_score = draw - cost - COEF x monthly_vol% + bonus`. 0.01 means
#: a 50%-annualised-vol name pays 0.144 %/month of score for its wildness —
#: enough to order two otherwise equal hypotheses, not enough to freeze the
#: explorer, which is the failure this whole split exists to end.
EXPLORE_RISK_PENALTY_COEF = 0.01

#: The bonus on posterior width: what a paper-risk dollar buys here is
#: INFORMATION, so a wider posterior is worth more, not less. 0.25 x se.
EXPLORE_UNCERTAINTY_BONUS_COEF = 0.25

#: The seed namespace for the Thompson draws. Bump it only to deliberately
#: redraw every historical allocation — the seed is derived from the AS-OF
#: date and the name, so a past contract reproduces exactly.
EXPLORE_SEED_NAMESPACE = "AEGIS_EXPLORE_v1"

# ── PROBE (chunk 23a, roadmap §16.2) ───────────────────────────────────────
# Murat, 2026-09-21: *"We should be skeptical about claims, not skeptical about
# experiments. High confidence determines how much capital we risk. It should
# not determine whether we are allowed to learn."* A name whose leading signal
# has NO measured read is refused capital correctly and refused LEARNING
# wrongly: nothing accrues, so the read can never become measured. A PROBE row
# costs nothing, is graded by the same grader at its own expiry, and
# accumulates under its `hypothesis_id` into exactly the measured read EXPLORE
# requires (§16.5 item 39).

#: The horizons every PROBE name is written at, in SESSIONS. Four and not one,
#: because a mechanism that shows up at a week and dies by a quarter is a
#: different finding from one that needs a quarter to appear, and a single
#: horizon would make the two indistinguishable for ever. The shortest is what
#: makes the panel start filling within a week of the chunk landing.
PROBE_HORIZONS_SESSIONS: tuple = (5, 21, 63, 126)

#: The notional a PROBE row is quoted at, in dollars. It buys NOTHING: the
#: weight is zero by construction and the capital resolution never sees it.
#: The number exists so a graded PROBE return can be read as a dollar figure
#: on the same scale as an EXPLORE name (0.25% of $40,000 = $100), which is
#: the only comparison a reader of the panel actually wants.
PROBE_VIRTUAL_NOTIONAL_USD = 100.0

#: At most this many PROBE NAMES on one day, best rank first. PROBE rows are
#: exempt from `decision_contract.MAX_REFUSED_ROWS` — they are the panel, and
#: trimming the panel to 50 would silently cap what can ever be measured — so
#: they carry their own ceiling, and the count that was cut is on the receipt.
PROBE_MAX_NAMES_PER_DAY = 200

#: The panel is a MEASURED read only at both of these, never one: `n` graded
#: rows AND `n_blocks` distinct asof MONTHS (CANON §58 — n_effective counts
#: DATE BLOCKS, and forty rows from one week are one observation wearing forty
#: hats). Below either, `probe_panel.read_for` returns the read with
#: `measured = False` and names the shortfall.
PROBE_MIN_GRADED = 30
PROBE_MIN_BLOCKS = 6

#: Block-bootstrap draws for the panel's standard error, resampling MONTHS
#: with replacement. 200 is the same order the replay receipts use; the draw is
#: seeded from the hypothesis id and the horizon, so a panel read reproduces.
PROBE_BOOTSTRAP_DRAWS = 200

# ── PROBE on the PC-PAPER account (chunk C3, 2026-09-25) ───────────────────
# §16.2's PROBE row is VIRTUAL ($0). C3 is a different thing wearing the same
# state name on purpose: the committee SHORTLIST reaching `sim_run.u_plan` as
# real PAPER orders, small, so that the shortlist's own forward grade can
# exist. No cap for paper PROBE orders was registered before this block, so
# these three are the registration. They are RISK LIMITS, not preferences:
# they live here and not in `policy_state`, which the night may move.
#
# Worst case for the largest admissible PROBE book (session protocol item 4),
# printed on every plan receipt in dollars, not only here:
#   n x notional% = 10 x 2% = 20% gross = PROBE_GROSS_CAP (Σ|notional|/equity
#   0.20). u_plan declares NO stop, so the ceiling is the whole 20% of equity
#   ($200,000 on the $1,000,000 PC-PAPER account); a PROBE_WORST_CASE_SIGMA
#   session with every name moving together is 20% x 3 x daily sigma
#   (~2.2%/day at the funnel's ~35%/yr vol) ~ 1.3% of equity (~$13,000).
#: Largest weight one PROBE name may carry, fraction of equity.
PROBE_MAX_WEIGHT = 0.02
#: Most PROBE names held from one plan (best shortlist score first). Not the
#: same number as PROBE_MAX_NAMES_PER_DAY (200 VIRTUAL contract rows).
PROBE_MAX_NAMES = 10
#: Σ PROBE weight ceiling. n x weight is clipped to this, never exceeds it.
PROBE_GROSS_CAP = 0.20
#: The adverse session the plan receipt prices in dollars, in DAILY SIGMAS of
#: each name (stops are quoted in sigma, not percent: 2026-09-24's -2% stop was
#: 0.93 sigma on the median name and stopped out 89% of trades).
PROBE_WORST_CASE_SIGMA = 3.0
#: Daily sigma used when a shortlist row carries no `vol_annual`: the measured
#: median name, 2.16%/day (2026-09-24, fleet counterfactual on real bars).
PROBE_REF_DAILY_SIGMA = 0.0216
#: The shortlist's own forward grade becomes MEASURED at this many distinct
#: decision days carrying a SCORED `decision_ledger` row for the C3 PROBE
#: hypothesis; below it the verdict is UNMEASURED_TRADE_SMALL.
PROBE_GRADE_MIN_SESSIONS = 21
#: The hypothesis every C3 PROBE row is written under; the grade joins on it.
PROBE_SHORTLIST_HYPOTHESIS_ID = "C3_committee_shortlist_probe_v0"

#: WHICH REFUSALS ARE AN ABSENCE OF MEASUREMENT rather than evidence
#: (chunk 23a-ii). A refused, ranked name whose refusal means one of these
#: becomes PROBE at the contract level: weight 0, a virtual row per horizon,
#: the original refusal sentence kept on the row as `probe_basis`.
#:
#: These are `decision_contract.LOCAL_REFUSAL_CLASSES` members, NOT the
#: execution repo's pinned 31. The pinned vocabulary cannot make the
#: distinction: its `EDGE_BELOW_BAR` covers both "verdict HOLD, nothing
#: measured" and "the measurement came back negative", and PROBE must take the
#: first and refuse the second. The two spellings a reader may be looking for
#: map like this: "NO_ACTION" is `NO_ACTION_VERDICT` (the HOLD/NO_ACTION
#: verdict refusal, pinned class EDGE_BELOW_BAR) and "NO_EVIDENCE" is
#: `NO_LICENSED_SIGNAL` (the evidence-grade NO_EVIDENCE refusal, pinned class
#: UNCLASSIFIED / terminal DATA_MISSING).
#:
#: Everything NOT in this tuple stays REFUSED and is meant to: `MEASURED_NO_EV`
#: (a read that came back at or below the floor), `CALIBRATED_OUTRANKED`,
#: `EXPLORE_BUDGET_FULL`, `VOL_MISSING`, `LIQUIDITY`, `CAPACITY`, `MDE`,
#: `STRUCTURE`, `MANDATE`, `INPUT_MISSING`, `UNTYPED`.
PROBE_REFUSAL_CLASSES: tuple = ("NO_ACTION_VERDICT", "NO_LICENSED_SIGNAL")

#: The verdicts that mean the engine has NO VIEW. `_refusal_sentence` writes
#: one sentence for every non-BUY/WATCH verdict, so HOLD and SELL arrive
#: wearing the same words and only the verdict separates them — and a SELL is a
#: view AGAINST the name, not an absence of one. A probe of a SELL would be a
#: virtual long against the engine's own opinion.
PROBE_REFUSAL_VERDICTS: tuple = ("HOLD", "NO_ACTION", "")

#: How many times the Thompson draw is REPLAYED to estimate each candidate's
#: probability of being selected. The selection probability is what a
#: doubly-robust off-policy estimator divides by (chunk 24's Vowpal Wabbit
#: benchmark, and Murat's item 12): without it, the rows this repo logs can
#: only ever be scored by Thompson's own math. It changes no decision today.
EXPLORE_SELECTION_REPLAYS = 2000

# ── THE EXPECTED-RETURN LAYER (chunk 2, 2026-09-25) ────────────────────────
# `backend/services/expected_return.py`. Spec:
# `docs/research_notes/2026-09-25/spec_chunk2_expected_return_layer.md`.
# E[r_h] = regime_scale * sum_c w_c x_c over the AWAKE components; the weights
# come from each component's own forward grade (never hand-set). What is set
# here is the machinery's shape, not any component's weight.

#: The horizons E[r] is computed at, in sessions.
ER_HORIZONS: tuple = (5, 21, 63)
#: A ledger horizon -> the E[r] horizon it grades. The forecast grid is
#: (1, 2, 5, 20, 60, 120, 252); 20 ~ 21 and 60 ~ 63 are the same question.
ER_HORIZON_ALIASES: dict = {5: 5, 20: 21, 21: 21, 60: 63, 63: 63}
#: Below this many graded DATE BLOCKS (CANON §58) a component is shrunk to the
#: prior (half an equal share), not zeroed and not trusted.
ER_MIN_GRADED = 30
#: The prior share of an ungraded component, as a fraction of an equal share.
ER_PRIOR_SHARE = 0.5
#: forecast_reputation's recipe on an IC skill: s = n/(n+k) * IC ; w = clip(s, 0, 1)**gamma.
#: Declared, not tuned: IC lives on a different scale from Brier skill, so the
#: Brier-tuned constants in the reputation receipt do not transfer.
ER_K_PRIOR = 30.0
ER_GAMMA = 1.0
ER_FLOOR = 0.0
#: Calibration shrink (p-bin -> realised relative return), toward the median (0).
ER_CALIB_K = 30.0
#: The reputation blend is used by u_plan only when its held-out advantage over
#: the equal-weight blend is positive on at least this many evaluable dates.
ER_OOS_MIN_DATES = 20
#: The blend's OWN forward grade that licenses EXPLOIT: distinct scored decision
#: days at this horizon (same count as the PROBE grade).
ER_BLEND_GRADE_HORIZON = 21
ER_BLEND_GRADE_MIN_SESSIONS = 21
#: EXPLOIT per-name cap when sized on E[r] (weights proportional to E[r]+).
ER_EXPLOIT_MAX_WEIGHT = 0.10
#: Sizing multipliers are never above 1: a scale can shrink a position, never
#: lift it past the caps the worst-case line was computed on.
ER_SIZE_SCALE_MIN = 0.25
#: market_sensor regime -> the scalar on every component's weight. A declared
#: prior, printed on every receipt; `unknown` does not invent a regime.
ER_REGIME_SCALE: dict = {"risk_on": 1.0, "risk_off": 0.5, "unknown": 1.0}
#: PDUFA: approval +5% vs CRL -33% over five days (our own receipt, review
#: 2026-09-25) puts break-even at p ~ 0.87. The CRL loss is DERIVED from the
#: break-even so the sign flips exactly there.
ER_PDUFA_BREAKEVEN_P = 0.87
ER_PDUFA_UP_RETURN = 0.05
#: No card p_approval -> the ~70% first-cycle rate (first-cycle CR ~30%,
#: research_fda_catalysts.md), i.e. a NEGATIVE term by default.
ER_PDUFA_PRIOR_P_APPROVAL = 0.70
#: source_reliability multiplier on revision_flow, clipped.
ER_SR_MULT_MIN = 0.5
ER_SR_MULT_MAX = 1.5
#: Revision-flow rule: minimum distinct firms (revision_flow.rule_score).
ER_REVISION_MIN_FIRMS = 3

# ── THE MORNING SCOREBOARD (chunk 21, Murat's item 12) ──────────────────────
# `backend/services/morning_scoreboard.py`. Reads receipts, writes nothing.

#: The benchmark the scoreboard differences NAV against. SPY, and named here
#: rather than spelled in the module, because the fleet's own benchmark is a
#: control LANE and the two must never be confused on one page.
SCOREBOARD_BENCHMARK_SYMBOL = "SPY"

#: The benchmark the DECISION GRADER differences every scored row against
#: (`decision_ledger.score_due`, chunk 23a). The same symbol as the scoreboard
#: and a SEPARATE constant on purpose: one is a NAV comparison and the other is
#: a per-row close-to-close excess, and a single name shared between them would
#: make a future change to either silently change the other. A row whose
#: benchmark could not be priced carries `benchmark_return = None` with the
#: reason — never a zero, which would read as "the market did nothing".
DECISION_BENCHMARK_SYMBOL = "SPY"

#: How far back "strongest NEW positive / killed" looks, in days, dated by each
#: receipt's OWN stamp (never `st_mtime`: session protocol 7).
SCOREBOARD_WINDOW_DAYS = 7

#: How far back the scoreboard reads contract files to attribute a realised
#: return to the authority that took the decision. A year, the same window
#: `decision_contract.find_contract_row` scans.
SCOREBOARD_JOIN_DAYS = 366

#: Most per-name rows carried on a P&L block before it is truncated.
SCOREBOARD_MAX_NAMES = 25

#: The verdict prefixes that count as a hypothesis KILLED. `STOP` is not among
#: them and is retired from exploratory work (CLAUDE.md, EXPLORE DIRTY).
SCOREBOARD_KILL_VERDICTS: tuple = ("FAILED_VARIANT", "MECHANISM_REJECTED")

#: The cash floor in the daily capital resolution: every dollar resolves to
#: benchmark / active_exploit / active_explore / cash (Murat's item 11), and
#: the benchmark core is the residual. Zero because the committee's core IS
#: the low-cost default and holding cash beside it is a second decision nobody
#: has declared — a non-zero value here is a policy choice, not a tuning knob.
IC_CASH_FLOOR_PCT = 0.0

#: The confidence floor, on the LEADING signal's own measured t. A signal
#: measured at t below this does not rank a name: the engine is not sure enough
#: about the return to order anything on it, so it does not — it keeps today's
#: sizing and prints the t it refused on. 2.0 is the conventional two-sigma bar
#: and is deliberately NOT tuned to admit any particular signal; with the table
#: as it stands (2026-09-20) it admits none, which is a fact about the
#: programme's measured evidence and not a setting to relax.
ROI_MIN_T = 2.0

#: The downside is `z x vol_annual x sqrt(horizon/12)`. One sigma, because the
#: numerator is a POINT estimate: mean over one-sigma spread is the
#: Sharpe-shaped ratio the spec asks for. Raising z scales every candidate
#: identically and reorders nothing — it only shrinks the Kelly weights.
ROI_DOWNSIDE_Z = 1.0

#: The four declared personalities as fractions of FULL Kelly (the same names
#: `agency.py` uses). Full Kelly maximises log wealth and is famously too
#: violent to hold; every tier here is a fraction of it, and NONE of them can
#: raise the book's worst case, because `IC_SINGLE_NAME_TILT_CAP` and
#: `IC_TOTAL_TILT_BUDGET` still bind after sizing (`roi_rank._refuse_cap_breach`
#: REFUSES rather than trims if they ever stop binding).
ROI_KELLY_FRACTION_BY_PERSONALITY: dict = {
    "preservation": 0.10,
    "balanced": 0.25,
    "aggressive": 0.50,
    "extreme_growth": 1.00,
}

#: The personality the committee book composes under. The committee page is the
#: default product surface and its core-and-tilts framing is the balanced one;
#: an aggressive book is a DECLARED choice a person makes, not a default.
ROI_DEFAULT_PERSONALITY = "balanced"

#: THE MEASURED HALF. One row per signal that may LEAD a ranking
#: (`recommendation._ADAPTERS` x the registry's PICKER permission) and that has
#: a per-name NET forward return with a receipt IN THIS CHECKOUT. Every row
#: carries all of `roi_rank.REQUIRED_FIELDS`, every number was copied off the
#: receipt named beside it, and `test_roi_rank.py` fails if any receipt path is
#: not on disk. **A signal with no receipt gets no row, and a name whose
#: leading signal has no row is not ROI-ranked.**
#:
#: WHY THERE ARE ONLY THREE ROWS, AND WHY NONE OF THEM CLEARS ROI_MIN_T TODAY
#: --------------------------------------------------------------------------
#: A sweep of `docs/TRIALS/`, `docs/archive/`, `NEGATIVE_RESULTS.md`, the
#: measured strategy library and every `night_factory_*` receipt (2026-09-20)
#: found a per-name net magnitude for exactly three of the eight adapter
#: signals, and the registry independently permits exactly those three to lead
#: (the other five are FILTER / SHELF / CLOSED, so writing a return for them
#: would be licensing a filter to pick). The three carry t 1.40, t 1.66 and no
#: t on the return at all.
#:
#: That is the answer to *"it can't be sure so it doesn't make one"*, and it is
#: a fact about the programme's evidence rather than a setting: the rule is
#: wired, armed and currently ranks nothing, and every row on the daily
#: contract now prints WHICH number was missing instead of one flat string.
#: The day a signal earns a t >= ROI_MIN_T read, it gets a row and the rule
#: fires without a code change.
#:
#: NOT IN THE TABLE, AND WHY (each checked, none of them an oversight):
#:   * `low_volatility` — registry: "ZERO net excess return", role FILTER. The
#:     one in-repo magnitude (+4.37%/yr net,
#:     `docs/STRATEGY_LIBRARY_MEASURED_2006_2019.md`) fails that doc's own FDR
#:     screen, and the adapter is `higher_is_better=False` on vol: a positive
#:     return here would license a risk filter to lead the order.
#:   * `short_interest_level` — no per-name net magnitude anywhere in this
#:     repo; a net t 3.4/3.0 with no return beside it
#:     (`docs/archive/ROADMAP_BRAIN_V2.md`), and the one BOOK that used it is
#:     -0.94%/mo t -2.09 (`docs/research_notes/2026-09-13/research_registry.md`).
#:   * `earnings_surprise_monthly` — measured INVERTED (IC t -2.6,
#:     `NEGATIVE_RESULTS.md` §14); the family's only net magnitude is
#:     -3.74%/yr.
#:   * `rating_drift_3m` — `known_effect: null`, `reliability_weight: null`, a
#:     4-row yfinance table. Nothing has ever been measured for it.
#:   * `momentum_12_1` — registry CLOSED/REJECTED; -1.11%/yr net in the
#:     measured library. Structurally barred from the order already.
#:   * Books E/F/G/C (the §14 scoreboard's +0.43%/mo t 3.12 and friends) are
#:     BOOK-level engine reads against their own random-universe twins, with no
#:     per-name column. Attaching F's seasonality number to a
#:     `profitability_small` candidate would be a category error wearing the
#:     best number on the board.
SIGNAL_MEASURED_RETURN: dict = {
    "profitability_small": {
        "monthly_net_pct": 0.241,
        "t": "CANNOT DETERMINE: the receipt states IC t 4.29, which is a RANK "
             "statistic about the ordering, not a t on the return",
        "t_basis": ("BRAIN-008's confirm window reports the net return and an "
                    "information-coefficient t. A rank IC t may not be read as "
                    "the return's t — that substitution is the exact shape of "
                    "the defect `recommendation.py` was written to stop — so "
                    "this row can never clear ROI_MIN_T until a t on the "
                    "RETURN is measured."),
        "n_blocks": 72,
        "net_basis": ("+24.1 bps/mo on the HELD-OUT 2019-2024 confirm window, "
                      "net at the 50 bps ruler the explore leg declared; "
                      "n_blocks 72 = the 72 months of that stated window. "
                      "Caveat carried on the same receipt: DSR ~ 0.10 after "
                      "61-candidate deflation, and BRAIN-008's FF6 alpha is "
                      "negative (the edge may be a factor tilt). The spanning "
                      "test in docs/archive/SESSION_2026-08-09_NIGHT4_PF4.md "
                      "cuts the annual incremental from +4.23%/yr t 3.65 to "
                      "+1.04%/yr t 1.07."),
        "receipt": "docs/TRIALS/TRIAL-SMQ-FWD.md",
        "measured_on": "2026-07-22",
    },
    "insider_opportunistic": {
        "monthly_net_pct": 0.17,
        "t": 1.40,
        "t_basis": "a t on the NET return, as quoted on the receipt",
        "n_blocks": "CANNOT DETERMINE: the receipt quotes BRAIN-003's headline "
                    "and not its window; the underlying run is in the brain "
                    "module repo, which is a separate checkout",
        "net_basis": ("BRAIN-003 opportunistic insider, +17 bps/mo NET, t 1.40, "
                      "microcap null, DSR 0.26 — the receipt does NOT name the "
                      "cost ruler, so this net is not comparable like-for-like "
                      "with the 50 bps rows above it. The project's own prior, "
                      "quoted beside the literature it matches. The registry "
                      "grades it SUPPORTED with the forward clock running to "
                      "2027-07, so this is a backtest prior and not yet a "
                      "forward record."),
        "receipt": "docs/AEGIS_FINANCE_DOSSIER_2026-08-02.md",
        "measured_on": "2026-08-02",
    },
    "fusion_insider_profitability": {
        "monthly_net_pct": 0.153,
        "t": 1.66,
        "t_basis": "a Newey-West t on the NET return, as quoted on the receipt",
        "n_blocks": "CANNOT DETERMINE: the receipt quotes BRAIN-007's headline "
                    "and not its window; the underlying run is in the brain "
                    "module repo, which is a separate checkout",
        "net_basis": ("BRAIN-007, the frozen equal-weight z-composite of the "
                      "other two: +15.3 bps/mo net, NW t 1.66, beating the "
                      "best single signal on 3.6x the names. Inherits the "
                      "PF4 spanning caveat through its profitability leg, and "
                      "the same receipt's caveat line: DSR ~ 0.10 after "
                      "61-candidate deflation, deploy gate NOT met anywhere."),
        "receipt": "docs/TRIALS/TRIAL-SMQ-FWD.md",
        "measured_on": "2026-07-22",
    },
}


# ── RANK -> RETURN CALIBRATION (chunk 22, 2026-09-21) ────────────────────────
# `scripts/calibrate_signal_return.py` (night job `C7_signal_calibration`) and
# `backend/services/signal_calibration.py`. Murat's review of 2026-09-20,
# issue 1: "the ROI engine is not yet an ROI engine. Expected return comes from
# the leading signal FAMILY's average; downside from the ticker's vol. Needed:
# calibrate signal strength into return magnitude — an out-of-sample map from
# signal decile to expected abnormal return and downside at 5/21/63/126
# sessions, with uncertainty, so each company gets its own mu_i."
#
# Everything here is the DECLARED half of that construction. The measured half
# lives on disk, one JSON per signal per run date, and `roi_rank` reads it by
# receipt path (`mu_basis` on the row) rather than by import.

#: The four horizons, in SESSIONS. Named in Murat's review, kept in sessions
#: rather than months because the forward return is computed on the session
#: index of the CRSP tape, where a "month" is 21 sessions by convention and not
#: by calendar.
CALIB_HORIZONS_SESSIONS: tuple = (5, 21, 63, 126)

#: The horizon the VERDICT is taken at, and the one `roi_rank` reads a per-name
#: mu from. 21 sessions ~ one month, which is the unit every measured net read
#: in `SIGNAL_MEASURED_RETURN` is already quoted in — so the calibrated number
#: and the family number it replaces are the same quantity.
CALIB_DECIDING_HORIZON_SESSIONS = 21

#: Sessions per month on the tape. One constant, so nothing anywhere turns 21
#: sessions into "about a month" twice with two different numbers.
CALIB_SESSIONS_PER_MONTH = 21.0

#: Deciles. Ten buckets of the cross-sectional score, cut on TRAINING data only.
CALIB_N_DECILES = 10

#: The downside percentile. Murat asked for "downside" beside the mean; the
#: 20th percentile of the decile's own abnormal-return distribution is what a
#: name in that decile actually risks in a bad fifth of outcomes, and it is a
#: MEASURED quantity rather than a distributional assumption about vol.
CALIB_DOWNSIDE_PCTILE = 20.0

#: Walk-forward: expanding window, refit yearly, first test year = the panel's
#: first year + this. Three years of training before the first out-of-sample
#: read; nothing before that year is ever scored.
CALIB_FIRST_TEST_YEAR_OFFSET = 3

#: Block bootstrap on the decile statistics: MONTH blocks (the dependence unit,
#: CANON §58), drawn with replacement.
CALIB_BOOTSTRAP_DRAWS = 400
CALIB_BOOTSTRAP_SEED = 20260921

#: The cost ruler, per side, on the implied turnover of a monthly-rebalanced
#: decile portfolio. A replaced name is sold and bought, so a one-way turnover
#: of tau costs 2 x tau x this per month. 25 bps/side is the ruler the roadmap
#: names for this chunk; quote the rate or do not quote the count.
CALIB_COST_BPS_PER_SIDE = 25.0

#: Holm alpha over the family of (signal x horizon) spreads. EXPORT rule
#: (CANON §63): this table sizes positions, so it is judged at the family-wise
#: error rate and not at an FDR.
CALIB_HOLM_ALPHA = 0.05

#: A CALIBRATED verdict needs the decile map to be MONOTONE, not merely to have
#: a positive end-to-end spread: a U-shape with a high top decile is not a map
#: from signal strength to return magnitude. Spearman of decile index against
#: decile mean, over the non-empty deciles.
CALIB_MONOTONE_MIN_SPEARMAN = 0.60

#: Refusal floors. A decile-month cell with fewer names than this contributes
#: no spread observation; a signal with fewer month blocks than this is
#: REFUSED by name rather than graded on a window nobody would believe.
CALIB_MIN_NAMES_PER_DECILE = 5
CALIB_MIN_BLOCKS = 24

#: How many NON-EMPTY deciles the monotonicity test needs before it is allowed
#: to answer at all. A score with a large tied block — the insider score is
#: zero for every name with no open-market Form 4 in its lookback — collapses
#: the bottom deciles into one bucket, and a Spearman over two points is
#: trivially +/-1. Below this the monotone test reports CANNOT DETERMINE and
#: the signal cannot reach CALIBRATED, which is the conservative direction:
#: EXPLORE still funds it, EXPLOIT does not.
CALIB_MIN_NONEMPTY_DECILES = 4

#: Draws in the second null test — the shuffled-panel DISTRIBUTION the real
#: spread and the real monotonicity are placed against. The first null test is
#: one full end-to-end shuffled replication (cut points refit on the shuffled
#: training panel); this is the same shuffle repeated on the out-of-sample
#: panel to give an empirical percentile. A null owes two tests.
CALIB_NULL_DRAWS = 200

#: The first calendar year the panel may start at. 2006 is when the SEC Form 4
#: bulk panel begins (`sec_insider/insider_events_v1.parquet`); the price tape
#: reaches back to 1990 and the JKP characteristics to 1926, so this is the
#: binding constraint for the insider and fusion legs and is applied to all
#: three so the three verdicts are read on the same window.
CALIB_START_YEAR = 2006

#: The insider score's own lookback, in CALENDAR days. It must equal the live
#: path's (`insider_trading.get_insider_transactions(lookback_days=90)`) or the
#: calibration is a map for a score the engine does not compute.
CALIB_INSIDER_LOOKBACK_DAYS = 90

#: Where the per-signal calibration JSONs are written and read, relative to the
#: repo root. One directory, so `roi_rank` reads by path and the path IS the
#: receipt.
CALIB_OUTPUT_DIR = "backend/data/optimus/calibration"

#: How stale a calibration file may be before `roi_rank` refuses to size on it,
#: in days, dated by the file's OWN `asof` stamp and never by `st_mtime`
#: (session protocol 7). A year: the map is an out-of-sample read over two
#: decades and does not turn over weekly, but a file nobody has rebuilt in over
#: a year is a number that has stopped being maintained.
CALIB_MAX_AGE_DAYS = 366

#: The time box for the night job, in minutes. A job killed at its limit writes
#: no receipt (2026-09-10, G3 at generation 340), so this job writes each
#: signal's file as it finishes and treats an existing file as its cursor.
CALIB_TIME_BOX_MINUTES = 60

#: WHERE THE PER-NAME DOWNSIDE COMES FROM once a signal is CALIBRATED.
#: "decile_p20" — the measured 20th percentile of that decile's own abnormal
#: returns. "vol" restores chunk 18c's `z x vol_annual x sqrt(h/12)` for every
#: name. The vol path is NEVER deleted: it is the fallback whenever the decile
#: has no usable p20 (a non-negative 20th percentile, or too few names), and
#: `roi_rank` PRINTS which of the two produced the number on every row.
ROI_DOWNSIDE_SOURCE = "decile_p20"

#: ONE flag for the whole of chunk 22. False and `roi_rank` reads only
#: `SIGNAL_MEASURED_RETURN`, exactly as it did on 2026-09-20.
ROI_USE_CALIBRATION = True


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
LLM_PRICE_AS_OF = "2026-09-05"
#: RE-DERIVED 2026-09-05 FROM THE PROVIDER BALANCE, not from a published list.
#: Receipt: `backend/data/optimus/continuation_2026-09-06b/
#: C3_deepseek_price_derivation_run01.json`; the derivation is
#: `scripts/c6b_deepseek_price_derivation.py` and it is re-runnable offline.
#:
#: The 2026-08-12 table below priced 55.8% of what DeepSeek actually charged.
#: Two balance readings bracket two windows, and the ledger's own token counts
#: sit inside them:
#:
#:   W1  2026-08-24T12:10Z  $23.99 -> 2026-09-05T11:58Z  $13.36   spend $10.63
#:       4,471 calls · 6,022,632 in · 1,893,504 cached · 7,474,321 out
#:       priced by the old table at $2.94  ->  multiple 3.61x
#:   W2  2026-09-05T11:58Z  $13.36 -> 2026-09-05T12:23Z   $9.38   spend  $3.98
#:       4,099 calls · 12,732,488 in · 7,601,792 cached · 1,398,775 out
#:       priced by the old table at $2.20  ->  multiple 1.81x
#:
#: THE TWO MULTIPLES DISAGREE BY 1.99x, so no scalar correction of the whole
#: table can be right — S4's "1.79-1.81x" was the 25-minute window alone.
#: Solving the 2x2 `in*Min + out*Mout = spend` (condition number 2.58, so the
#: windows genuinely differ in mix) gives **in $0.169413 / out $1.284835 per
#: Mtok**: the input leg was roughly right (1.21x) and the OUTPUT leg was
#: under-priced by 4.59x.
#:
#: WHY "THE TABLE IS WRONG" AND NOT "THE LEDGER IS INCOMPLETE" — the key is
#: shared with every other job on this machine, so missing rows were the rival
#: explanation. The two stories predict different SHAPES for the gap, and the
#: shape decides it: the gap is $1.03/Mtok-out in W1 and $1.28/Mtok-out in W2
#: (spread 1.24x) but $0.00172 vs $0.00044 per CALL (spread 3.95x) and $1.28 vs
#: $0.14 per Mtok-IN (spread 9.11x). Missing rows lose whole calls and would
#: show a constant gap per call; they do not. The incomplete-ledger story would
#: additionally have to claim 72.3% of a 12-day window's real money and 44.8%
#: of a supervised 25-minute window's real money left no trace, at unledgered
#: burn rates 160x apart.
#:
#: CROSS-CHECKS, all agreeing on the output leg: least squares over four
#: sub-windows recovered from this session's sibling receipts gives
#: 0.1166/1.3461; holding in=0.14 and solving only the output leg gives 1.3476
#: pooled (1.309 / 1.556 per window). The OUTPUT leg is bracketed [1.28, 1.35];
#: the INPUT leg is only bracketed [0.117, 0.169] and the old 0.14 is inside
#: it. The adopted numbers are the exact 2x2 on the only two readings that
#: carry a recorded timestamp — the high end of the input bracket, which is the
#: safe direction for a gate.
#:
#: WHAT IS MEASURED AND WHAT IS NOT:
#:  * `in` and `out` for the v4-flash family: MEASURED (2 windows, 2 unknowns).
#:  * `cached_in`: SCALED by the same factor as `in`, NOT MEASURED. Two windows
#:    cannot identify three legs, and the 50x discount is preserved rather than
#:    invented.
#:  * `deepseek-v4-pro`: PROPAGATED, NOT MEASURED — the ledger holds ZERO
#:    v4-pro rows in 70,664 lines, so this window says nothing about it. The
#:    old pro entry was EXACTLY 3.1071x flash on both legs, which is the
#:    signature of one reading of one list on one day; a correction to that
#:    reading therefore carries. The alternative — leaving out=0.87 — would
#:    price pro's output BELOW measured flash output, which is incoherent and
#:    under-binds a gate.
#:  * Anthropic rows: UNTOUCHED. Different vendor, no balance, no evidence.
#:
#: History is NOT rewritten. `llm_calls.jsonl` keeps every row at the price it
#: was written with (`pricing_as_of` travels on each row) — repairing an
#: append-only accounting file is the tampering. `llm_telemetry.reprice()` is
#: the audit helper that re-values stored TOKENS at this table, and
#: `llm_telemetry.spend()` — which `research_budget.require()` gates on —
#: already reads through `row_cost` -> `price_call`, so every dollar ceiling in
#: this repo begins binding at these rates with no further change.
#:
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
#: ($0.00338826 vs $0.169413 after the 2026-09-05 re-derivation; the 50x ratio
#: is carried, not re-measured). Sharing a long common prefix across the arms of an
#: experiment is therefore worth more than any other cost optimisation
#: available to us.
LLM_PRICE_PER_MTOK: dict[str, dict[str, float]] = {
    # DeepSeek — the workhorse for specialists and research roles.
    # in/out MEASURED from the balance (2026-09-05); cached_in scaled with `in`.
    "deepseek-v4-flash": {"in": 0.169413, "cached_in": 0.00338826,
                          "out": 1.284835},
    # PROPAGATED at the same per-leg multiples (1.2101x in, 4.5887x out), not
    # measured: no v4-pro call has ever been made. See the block above.
    "deepseek-v4-pro": {"in": 0.526390, "cached_in": 0.00438659,
                        "out": 3.992166},
    # Legacy aliases. Both resolve server-side to v4-flash, so they are priced
    # as v4-flash. Kept because call sites still send these strings.
    "deepseek-chat": {"in": 0.169413, "cached_in": 0.00338826, "out": 1.284835},
    "deepseek-reasoner": {"in": 0.169413, "cached_in": 0.00338826,
                          "out": 1.284835},
    # 2026-09-19, MEASURED: a `deepseek-chat` request now comes back with
    # `usage.model == "deepseek-flash"` (the V4.1-Flash rename of 2026-09-14).
    # The first N9 probe made every call at cost_usd=None, so its $1 cap read a
    # LOWER BOUND of $0 while the balance moved $0.21. Priced as v4-flash until
    # a balance re-derivation says otherwise; `deepseek-pro` propagated likewise.
    # 2026-09-27, CALIBRATED FROM THE BALANCE: 8 thesis-card quests through
    # OpenClaw moved the balance $0.26 ($33.79 -> $33.53, +/- $0.01) where the
    # row above priced them $0.412 -> k = 0.6146 [0.590, 0.639] on the 09-05
    # leg SHAPE (one route = one mix = the LEVEL only; the split is carried).
    # Receipt: backend/data/optimus/llm_price/calibration_2026-09-27.json
    # (see LLM_PRICE_CALIBRATION below; scripts/llm_price_calibrate.py).
    "deepseek-flash": {"in": 0.10411313, "cached_in": 0.00208226, "out": 0.7895982},
    "deepseek-pro": {"in": 0.526390, "cached_in": 0.00438659, "out": 3.992166},
    # ── FREE TIER (2026-09-07). Zeros, and in THIS table on purpose. ────────
    # A free model is not "no price"; it is a price of zero, and the difference
    # decides what a total means. `llm_telemetry.price_call` returns None for a
    # model it cannot find, callers treat None as "unpriced, this total is a
    # LOWER BOUND", and a free call left out of the table would therefore make
    # every spend figure it touched unreadable. A row of zeros keeps the token
    # count, keeps the accounting, and makes the spend line read $0.00 — which
    # is a LINE. An absent line and a $0.00 line look identical in a summary and
    # mean opposite things.
    #
    # A second "free models" list beside this one would be two tables answering
    # one question, which is roadmap X7's complaint. So `free_inference.
    # is_free_model` DERIVES freeness from these zeros instead of declaring it.
    #
    # NVIDIA NIM free tier — the twelve models that actually SERVED this account
    # on 2026-09-07 (81 were listed; the catalogue is not the grant). Receipt:
    # backend/data/optimus/free_inference_2026-09-07/L1_nim_probe.json
    "openai/gpt-oss-20b": {"in": 0.0, "cached_in": 0.0, "out": 0.0},
    "nvidia/nemotron-3.5-lightning-30b-a3b": {"in": 0.0, "cached_in": 0.0, "out": 0.0},
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning": {"in": 0.0, "cached_in": 0.0, "out": 0.0},
    "nvidia/nemotron-3-super-120b-a12b": {"in": 0.0, "cached_in": 0.0, "out": 0.0},
    "nvidia/nemotron-3-ultra-550b-a55b": {"in": 0.0, "cached_in": 0.0, "out": 0.0},
    "nvidia/ising-calibration-1.5-31b": {"in": 0.0, "cached_in": 0.0, "out": 0.0},
    "nvidia/nemotron-3.5-content-safety": {"in": 0.0, "cached_in": 0.0, "out": 0.0},
    "meta/muse-glimmer-30b": {"in": 0.0, "cached_in": 0.0, "out": 0.0},
    "minimaxai/minimax-m3": {"in": 0.0, "cached_in": 0.0, "out": 0.0},
    "moonshotai/kimi-k3": {"in": 0.0, "cached_in": 0.0, "out": 0.0},
    "google/gemma-4-31b-it": {"in": 0.0, "cached_in": 0.0, "out": 0.0},
    # served this account on 2026-09-26 (the G-fix adjudicator probe); free tier.
    "meta/llama-3.2-11b-vision-instruct": {"in": 0.0, "cached_in": 0.0, "out": 0.0},
    "poolside/laguna-xs-2.1": {"in": 0.0, "cached_in": 0.0, "out": 0.0},
    # On-box llama.cpp. The electricity is real and is NOT metered per token;
    # the honest per-token price is zero and the real cost is WALL CLOCK, which
    # `local_review` reports beside the dollars rather than pretending into here.
    "local": {"in": 0.0, "cached_in": 0.0, "out": 0.0},

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
#: HOW the DeepSeek rows of `LLM_PRICE_PER_MTOK` were obtained — machine-readable
#: so a test can assert the table still matches its own derivation, and so a
#: reader of a dashboard can find the receipt without reading this file.
#:
#: A price table whose provenance lives only in a comment is a table nobody can
#: check: the 2026-08-12 correction was a careful, documented edit that got the
#: output leg wrong by 4.6x and nothing failed for 24 days. This dict is what
#: `test_llm_price_from_balance.py` pins the table against.
LLM_PRICE_DERIVATION: dict[str, object] = {
    "method": "two_rate_linear_solve_on_provider_balance_windows",
    "derived_on": "2026-09-05",
    "receipt": ("backend/data/optimus/continuation_2026-09-06b/"
                "C3_deepseek_price_derivation_run01.json"),
    "script": "scripts/c6b_deepseek_price_derivation.py",
    "source_of_truth": ("the DeepSeek account balance "
                        "(backend/data/optimus/deepseek_balance.jsonl), NOT "
                        "our own telemetry and NOT a published list"),
    "balance_readings": [
        {"read_at": "2026-08-24T12:10:08+00:00", "total_usd": 23.99},
        {"read_at": "2026-09-05T11:58:34.953036+00:00", "total_usd": 13.36},
        {"read_at": "2026-09-05T12:23:33.325408+00:00", "total_usd": 9.38},
    ],
    "windows": [
        {"label": "W1", "provider_spend_usd": 10.63, "n_calls": 4471,
         "tokens_in": 6022632, "tokens_cached": 1893504, "tokens_out": 7474321,
         "old_table_usd": 2.94128, "multiple_of_old_table": 3.6141},
        {"label": "W2", "provider_spend_usd": 3.98, "n_calls": 4099,
         "tokens_in": 12732488, "tokens_cached": 7601792, "tokens_out": 1398775,
         "old_table_usd": 2.19549, "multiple_of_old_table": 1.8128},
    ],
    "condition_number": 2.5791,
    "measured_usd_per_mtok": {"in": 0.169413, "out": 1.284835},
    "multiple_of_the_2026_08_12_table": {"in": 1.2101, "out": 4.5887},
    #: The finding a single scalar multiple would have hidden: the two windows
    #: need 3.61x and 1.81x of the old table, so the SHAPE was wrong, not the
    #: level. S4's 1.79-1.81x was the 25-minute window read alone.
    "scalar_multiple_is_refuted": {"W1": 3.6141, "W2": 1.8128,
                                   "spread": 1.9936},
    #: Table-wrong vs ledger-incomplete. The gap is proportional to output
    #: tokens (per-window spread 1.24x), not to calls (3.95x) or input tokens
    #: (9.11x) — missing rows lose whole calls and would look constant per call.
    "gap_attribution_spread": {"per_mtok_out": 1.2402, "per_call": 3.954,
                               "per_mtok_in": 9.1088},
    "verdict": "TABLE_IS_WRONG_OUTPUT_LEG",
    "measured_entries": ["deepseek-v4-flash", "deepseek-chat",
                         "deepseek-reasoner"],
    "scaled_not_measured": {
        "cached_in": ("carried at the table's 50x discount; two windows cannot "
                      "identify three legs"),
        "deepseek-v4-pro": ("propagated at the same per-leg multiples; ZERO "
                            "v4-pro rows exist in the ledger, so this "
                            "measurement says nothing about it"),
    },
    "untouched": ["claude-opus-5", "claude-opus-4-8", "claude-sonnet-5",
                  "claude-sonnet-4-6", "claude-haiku-4-5"],
    "residual_uncertainty": {
        "in_bracket": [0.116643, 0.169413],
        "out_bracket": [1.284835, 1.347635],
        "what_would_close_it": ("two controlled calls with opposite in/out "
                                "mixes, each bracketed by a timestamped "
                                "GET /user/balance after the posting lag"),
        "unchecked_implication": (
            "repricing the whole ledger at these rates implies $97.61 of "
            "lifetime DeepSeek spend since 2026-08-12 vs $27.41 at the old "
            "table; most of that predates the first balance reading and "
            "cannot be checked without top-up history. The measurement "
            "INSIDE the two windows is direct; this extrapolation is not."),
    },
}

#: The `deepseek-flash` row's provenance, machine-readable (the model DeepSeek
#: has actually served since 2026-09-14). Separate from LLM_PRICE_DERIVATION on
#: purpose: that block pins the 09-05 v4-flash / chat / reasoner rows to their
#: two-window solve, and this one is a one-window LEVEL fit on the thesis-card
#: route. `test_llm_price_calibration.py` pins the row to this block.
LLM_PRICE_CALIBRATION: dict[str, object] = {
    "model": "deepseek-flash",
    "calibrated_on": "2026-09-27",
    "receipt": "backend/data/optimus/llm_price/calibration_2026-09-27.json",
    "script": "scripts/llm_price_calibrate.py",
    "method": "scalar_on_prior_shape",
    "route": "scripts.thesis_cards.run: OpenClaw quest (deepseek/deepseek-flash) + synth",
    "balance_before_usd": 33.79, "balance_after_usd": 33.53,
    "provider_delta_usd": 0.26, "offset_usd_other_rows": 0.00659859,
    "n_calls": 8, "tokens_in": 583175, "cached_tokens": 18901504, "tokens_out": 194184,
    "prior_row": {"in": 0.169413, "cached_in": 0.00338826, "out": 1.284835},
    "k_vs_prior": 0.614552, "k_bracket": [0.5903, 0.638804],
    "fitted_usd_per_mtok": {"in": 0.10411313, "cached_in": 0.00208226,
                            "out": 0.7895982},
    "granularity_usd": 0.01,
    "not_measured": ("the per-leg split: one route has one in/cached/out mix, so "
                     "the balance identifies one number (the level); the legs keep "
                     "the 2026-09-05 shape"),
    "finding": ("the 09-27 06:45 read that implied a 4-6x over-statement was taken "
                "before the earlier run's spend had posted; this settled batch "
                "measures table 1.61x and OpenClaw costUsd 2.01x the provider"),
}

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

#: PERSONAL MODE (chunk 17, `spec_decision_contract_and_path_audit.md` §5).
#:
#: Aegis is two deliverables out of one system: Murat's own capital, and a
#: public tool other people run. The public one carries "educational tool, not
#: financial advice" on every surface; the personal one is a man reading his own
#: research on his own desktop, and a disclaimer he wrote to himself is noise
#: that teaches him to skim the sentence beside it.
#:
#: OFF BY DEFAULT, and it stays off unless the environment says otherwise: the
#: deployed website, the public build and CI all read `0`. It hides exactly two
#: things on the backend -- the comparison framing's closing sentence in
#: `routers/market.py` and the copilot system prompt's closing-reminder clause
#: -- and the frontend banners behind `NEXT_PUBLIC_AEGIS_PERSONAL_MODE`.
#:
#: What it does NOT touch: `daily_brief.py`, `tearsheet.py` and
#: `portfolio_guidance.py`. Those are EXPORT artefacts — a saved tearsheet, a
#: shared brief — that can leave the machine that made them, and whether they
#: keep their disclaimer is Murat's call, not a session's (spec §5.2). It
#: changes no number, no sizing and no permission: nothing about a disclaimer's
#: visibility gives an LLM authority over capital.
PERSONAL_MODE = os.getenv("AEGIS_PERSONAL_MODE", "0") in ("1", "true", "yes")

#: 2026-09-20: the website backend's warm loop was the Railway bill. Measured
#: with `railway metrics` on `selfless-courage/Aegis-Finance`: 0.58 vCPU average
#: (peaks 29.8 vCPU) and 829 MB average, recomputing the 80-ticker screener,
#: the Monte Carlo and the sector pass every TTL for nobody -- ~$20/month of
#: the ~$47 total against Murat's $20 ceiling for the whole of Railway. With
#: this set the deployment starts no prewarm and no warm loop; every endpoint
#: still answers, the first caller pays the compute and the cache serves the
#: rest. `/api/health` reports `cache.status == "skipped"` rather than "ready"
#: so nobody reads a warm cache into an empty one. Set on Railway as
#: `AEGIS_WARM_SKIP=1`; the desktop app is unaffected (it has its own gate,
#: `main._desktop_background_off`).
WARM_SKIP = os.getenv("AEGIS_WARM_SKIP", "0") in ("1", "true", "yes")
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

#: How far back the live price/bar-date helpers ask for daily bars. Ten calendar
#: days clears a long weekend plus a holiday and still costs one cached fetch.
PI_PRICE_FETCH_LOOKBACK_DAYS = 10

#: Days added to `today` to form the price fetch's `end`. yfinance's `end` is
#: EXCLUSIVE, so an end of `today` returns bars up to YESTERDAY and the close
#: mark can never see the session it is marking — which is exactly what
#: P-day-2026-08-19a set out to fix and did not. Diagnosed 2026-09-03 from four
#: consecutive prod MTM runs that each reported "marked: 10, failed: 0" while
#: every lane's NAV sat one session behind. 1 makes the window inclusive of
#: today; it is a constant rather than a literal so the two helpers that must
#: agree on it cannot drift apart again.
PI_PRICE_FETCH_END_OFFSET_DAYS = 1

#: How many ACTIONABLE overdue forecasts `ledger_health` names on the health
#: row. The count alone sent a 2026-09-03 forensic pass differencing receipts
#: to work out which records were meant; the row is served on every poll, so
#: the list is capped rather than unbounded.
LEDGER_HEALTH_MAX_NAMED_OVERDUE = 20


# ── H1: the candidate surface (read-only) ────────────────────────────────────
# Roadmap `ROADMAP_2026-09-07_TWO_MODES_AMENDMENT.md` §2 H1. Mode A is Murat
# deciding with the machine beside him; the machine's candidate list has lived
# on disk as JSONL since 2026-09-03 with no way to look at it. These constants
# name every path and every threshold the `/api/candidates/*` router reads, so
# a deployment can move them without editing a router.
#
# READ-ONLY BY CONSTRUCTION: nothing under this heading is ever opened for
# write. `backend/tests/test_candidates_router.py` proves it two ways (an HTTP
# method audit and a source scan).

#: Stamped into every candidate-surface response so a screenshot is datable.
CANDIDATE_SURFACE_VERSION = "candidate_surface_v1/2026-09-07"

#: One scorecard per observable company-vintage, written by
#: `learner/potential_universe.py` via `scripts/potential_universe_run.py`.
#: Line 1 is the header, lines 2..N are scorecards.
CANDIDATE_POTENTIAL_UNIVERSE_DIR = OPTIMUS_LEDGER_DIR / "potential_universe"

#: `learner/allocator.py` decision artefacts, `<day>_<personality>.json`.
CANDIDATE_DECISION_ARTIFACT_DIR = OPTIMUS_LEDGER_DIR / "decision_artifacts"

#: The EXECUTION repo's state directory. The website backend cannot see it from
#: a container (grounding report A.5 gap 9), so it is an env var with a local
#: default rather than a hardcoded path: absent ⇒ the tracker legs report
#: NOT_REACHABLE instead of pretending the watchlist is empty. H5 replaces this
#: with a synced directory; until then this is the only bridge.
TERMINAL_STATE_DIR = Path(
    os.getenv("AEGIS_TERMINAL_STATE_DIR",
              str(Path.home() / "aegis-alpha-terminal" / "state")))

#: Whole-market tracker watchlist: `<day>.jsonl` day files plus `latest.json`
#: (schema `tracker-1`: summary + candidates).
CANDIDATE_TRACKER_DIR = TERMINAL_STATE_DIR / "tracker"

#: A vintage this many US WEEKDAYS behind today is FRESH; older is STALE.
#: Weekdays, not calendar days, because the nightly job follows the tape: on a
#: Monday the newest honest vintage is Friday's, and a calendar-day rule would
#: paint every Monday red. That is the "a gate that cannot go green is a broken
#: gate" lesson applied before the gate ships. No holiday calendar is consulted,
#: so a vintage the day after a market holiday reads STALE by one day — a false
#: alarm is the safe side of this particular error.
CANDIDATE_VINTAGE_FRESH_MAX_AGE_WEEKDAYS = 1

#: Page size ceiling for a candidate-list request. 3,056 scorecards at ~2 kB
#: each is a 6 MB response; the page pages instead.
CANDIDATE_PAGE_DEFAULT_LIMIT = 100
CANDIDATE_PAGE_MAX_LIMIT = 500

#: In-memory parse cache: how many distinct (path, mtime, size) artefacts to
#: hold. Four artefacts × a couple of vintages; the cache is a dict, not a
#: database (CLAUDE.md: "no database — this is a stateless API").
CANDIDATE_CACHE_MAX_ENTRIES = 8


# ── R6 / MODE A: the human loop (H2 · T2/H4 · H5) ────────────────────────────
# `ROADMAP_2026-09-07_TWO_MODES_AMENDMENT.md` §2 H and T. Mode A (Murat decides,
# the machine assists) and Mode B (the machine decides, Murat audits) are ONE
# system at two authority levels, and Mode A is how Mode B gets its labels.
# Every constant the journal bridge, the decision log, the four-counterfactual
# grader and the terminal-state reader read lives here, never in a service file.

#: Stamped onto every human-loop response and every stored row, so a screenshot
#: and a JSONL line can both be dated and re-derived.
HUMAN_LOOP_VERSION = "human_loop_v1/2026-09-08"

#: Append-only storage for Mode A. JSONL files, not a table: CLAUDE.md forbids
#: adding a database, and the immutable `personal_decisions` table already owns
#: the conviction log. These files are the THESIS and the GRADE that hang off it.
HUMAN_LOOP_DIR = DATA_DIR / "human_loop"
HUMAN_THESIS_LOG = HUMAN_LOOP_DIR / "human_theses.jsonl"
HUMAN_BOOK_LOG = HUMAN_LOOP_DIR / "human_book_entries.jsonl"
DECISION_LOG_PATH = HUMAN_LOOP_DIR / "decision_log.jsonl"
DECISION_GRADE_LOG_PATH = HUMAN_LOOP_DIR / "decision_grades.jsonl"

#: The author, and therefore the brain name. `alpha/human.py::Thesis.brain`
#: derives `human:<author>`; this constant exists so the string is declared once
#: and a test can assert the sealed row carries exactly it.
HUMAN_THESIS_AUTHOR = "murat"
HUMAN_BOOK_BRAIN = f"human:{HUMAN_THESIS_AUTHOR}"

#: The generator name written into a pre-open prediction-book row (schema
#: `prediction-book-3`, `state/predictions/<day>.json`). The execution repo's
#: rows carry `generator: "murat_rule_v1"`; a HUMAN row carries the brain.
HUMAN_BOOK_GENERATOR = HUMAN_BOOK_BRAIN

#: LOSS BUDGETS (invariant 19: declared before the first position). Keyed by the
#: `loss_budget_ref` a thesis must name. Values are the roadmap's F table — the
#: number of positions the book is JUDGED at and how many it EXPECTS to lose —
#: so "an idea is retired by its book's scoreboard, never by its own first loss"
#: is a lookup instead of an argument. `human_v1` is hack5, the HUMAN BOOK.
LOSS_BUDGETS: dict[str, dict] = {
    "human_v1": {"book": "hack5", "positions_judged": 20, "expected_losers": 8,
                 "note": "the HUMAN BOOK (roadmap F, hack5). Judged per journal "
                         "row; the 20 here is also the no-P&L-claim gate."},
    "event_v1": {"book": "hack2", "positions_judged": 40, "expected_losers": 24,
                 "note": "EVENT / day book, 1-3 sessions, min hold 0 BY DECLARATION."},
    "thesis_3m_v1": {"book": "hack3", "positions_judged": 20, "expected_losers": 8,
                     "note": "3-MONTH HOLD book, 63 sessions / 21 min hold."},
    "thesis_6m_v1": {"book": "hack4", "positions_judged": 15, "expected_losers": 6,
                     "note": "6-MONTH HOLD book, 126 sessions / 42 min hold."},
    "ensemble_v1": {"book": "hack6", "positions_judged": 100, "expected_losers": 50,
                    "note": "ENSEMBLE broad book, 42 sessions / 21 min hold."},
}

#: Default hold shape for a journal row that does not name one. A DEFAULT, not a
#: silent one: the bridge stamps `horizon_source` so a row that took the default
#: is distinguishable from a row that declared 21 on purpose.
HUMAN_DEFAULT_HORIZON_SESSIONS = 21
HUMAN_DEFAULT_MIN_HOLD_SESSIONS = 5
HUMAN_DEFAULT_LOSS_BUDGET_REF = "human_v1"

#: Sessions between scheduled reviews — the second counterfactual's clock.
#: 21 sessions ≈ one month, matching hack3/hack6's declared monthly review.
HUMAN_REVIEW_CADENCE_SESSIONS = 21

#: THE HONESTY GATE. Under this many GRADED rows (four counterfactuals each) the
#: surface reports PROCESS metrics only and says "a receipt, not a result".
#: Roadmap §2 H gate.
DECISION_LOG_MIN_GRADED_ROWS_FOR_PNL_CLAIM = 20

#: Counterfactual price sources, TRIED IN THIS ORDER, and every answer names the
#: one that served it. The `market` benchmark account (PA3I7VTCC0BM, contract
#: PASSIVE_BETA_v1) holds SPY and its keys are NOT in this .env, so the SPY leg
#: is computed from PRICE DATA and must say so. A source that cannot answer
#: yields NOT_AVAILABLE with a reason — never 0.0, which reads as "flat" and is
#: the difference between "SPY did nothing" and "we never asked".
COUNTERFACTUAL_PRICE_SOURCES = (
    "terminal_state_mirror",   # H5 mirror of the execution repo's marks
    "conviction_prices_csv",   # backend/data/conviction_prices.csv (offline)
    "yfinance_live",           # network; refused inside the fast suite
)

#: The benchmark the fourth counterfactual is measured against, and the account
#: that holds it in paper. The account is named for provenance only — no key for
#: it exists in this environment and nothing here tries to reach it.
COUNTERFACTUAL_BENCHMARK_SYMBOL = "SPY"
COUNTERFACTUAL_BENCHMARK_ACCOUNT = "PA3I7VTCC0BM"
COUNTERFACTUAL_BENCHMARK_CONTRACT = "PASSIVE_BETA_v1"

#: Free-inference backends for the 2-4 sentence reflection, in order. DeepSeek is
#: NOT in this tuple and a test asserts it never enters: the reflection is a
#: nice-to-have on a ~$9 balance reserved for the era replay.
DECISION_REFLECTION_BACKENDS = ("local_gguf", "nvidia_nim")
DECISION_REFLECTION_MAX_TOKENS = 220
DECISION_REFLECTION_MIN_SENTENCES = 2
DECISION_REFLECTION_MAX_SENTENCES = 4

# ── H5: the terminal-state MIRROR (read-only) ────────────────────────────────
#: Where the execution repo's artefacts are copied TO. The Docker backend mounts
#: or ships this directory; it never sees `TERMINAL_STATE_DIR` itself.
TERMINAL_MIRROR_DIR = DATA_DIR / "terminal_mirror"

#: WHAT is mirrored. A whitelist, because `state/` is 2.4 GB and most of it is
#: logs, caches and 16 MB of prediction books. Each entry is
#: (relative path under state/, kind, max files kept). A directory not on this
#: list is not synced and the receipt says how many were skipped.
TERMINAL_MIRROR_ARTEFACTS: tuple[tuple[str, str, int], ...] = (
    ("predictions/seals.jsonl", "seals", 1),
    ("contracts", "contracts", 50),
    ("autopsy", "autopsies", 30),
    ("learning_report", "learning_reports", 30),
    ("opportunity_recall", "opportunity_recall", 30),
    ("refusal_regret.json", "refusals", 1),
    ("fills.jsonl", "fills", 1),
)

#: Per-file ceiling for the mirror. `decisions.jsonl` is 18 MB and `fills.jsonl`
#: 2.1 MB; a file over this is TRUNCATED FROM THE TAIL (newest lines) for a
#: line-oriented artefact and SKIPPED for a JSON blob, and either way the
#: receipt records which happened. A silently half-copied file is the failure
#: this constant exists to make impossible.
TERMINAL_MIRROR_MAX_BYTES = 8 * 1024 * 1024


# ── THE IIF1 NIGHT LAUNCHER'S WALL-CLOCK START (chunk 16a, 2026-09-18) ───────
#
# MEASURED, from the launch receipts themselves. `AegisIIF1NightLauncher` is
# registered WEEKLY MON-FRI at 17:00 local and has refused
# `PAST_LATEST_SAFE_LAUNCH` with a margin of **-10.0 minutes** on every session
# date whose receipt survives from 2026-09-01 onward. The arithmetic, in the
# receipt's own numbers, for a US session on EDT:
#
#     next_open                13:30Z   (09:30 ET)
#     - duration_bound         235 min  (worst completed night 117.48 x 2.0)
#     = latest safe RUN START  09:35Z
#     - assembly_allowance      45 min  (MAX_DECISION_LAG_MINUTES; CAP_BINDS)
#     = latest safe LAUNCH     08:50Z = 16:50 local (UTC+8)
#
# and the task fires at 09:00Z = 17:00 local. Ten minutes late, every time.
#
# 16:00 rather than 16:50, and the reason is the safety factor. The duration
# bound is `worst completed night x 2.0`, so every extra minute a future night
# takes costs TWO minutes of launch window. Registering 16:50 buys zero margin
# and the very next night that runs a minute slower than 117.48 breaks it again;
# 16:00 leaves +50 min, which tolerates a worst completed night up to ~142 min.
# Verified by simulation against the live derivation (spends nothing):
# 17:00 -> -10.0, 16:50 -> 0.0, 16:30 -> +20.0, 16:00 -> +50.0.
#
# EDT is the binding case. From 2026-11-01 the open is 14:30Z and the same
# 16:00 leaves +110 min, so one number works on both sides of the change.
IIF1_LAUNCHER_LOCAL_START_TIME = "16:00"

# ── THE DAILY PASS'S OWN BOXES (chunk 16a, 2026-09-18) ───────────────────────
#
# MEASURED. The `AegisDailyPass` run of 2026-09-14 06:30 entered its analyst
# snapshot, checkpointed 1,500 of 2,362 symbols at 00:52:52Z, and then never
# returned. It stayed alive for FOUR DAYS: every scheduled firing on 09-15,
# 09-16, 09-17 and 09-18 reported Windows result 0x80070420 ("an instance of
# this task is already running") and no daily pass ran on any of them. The lab's
# news loop yielded to it (`DAILY_PASS_RUNNING`) the whole time.
#
# Every yfinance PROPERTY read in that sweep was already boxed at 25 s, so a
# per-call box is not enough: a driver needs a box on the STEP as well, or one
# wedged step is a dead day and then a dead week.

#: Hard wall-clock bound per declared step, in seconds. A step that outlives its
#: box is a `timeout` row in the receipt and the pass CONTINUES to the next step
#: -- half a day is still a day. The analyst sweep's number is the measured
#: 2.62 h (2,362 names at 4.0 s) with room, not a guess.
DAILY_PASS_STEP_BOX_S: dict = {
    # Review 2026-09-26 §5 item 1: the bar panels ended 2026-09-21 and nothing
    # refreshed them. An incremental tail pull (~5k symbols, ~10 days) plus a
    # full re-pull of the symbols whose adjustment base moved; measured
    # 2026-09-26 at a few minutes. The subprocess is given this box minus 60 s
    # so it is killed by its own handle, never orphaned.
    "bars_refresh": 1800,
    "news_pull": 2400,
    # ONE HOUR, down from four (2026-09-20). Four hours was the whole of a
    # working morning spent on a sweep that no other step of the pass reads:
    # the contract, the panel append and the cadence pass all run off artefacts
    # already on disk. The sweep itself now stops at
    # `DAILY_PASS_ANALYST_BUDGET_S` and returns a receipt that NAMES the
    # truncation, so this number is a backstop rather than the thing that
    # normally fires — a box that times out every single day would be a red
    # line the reader learns to skim (CLAUDE.md, "a gate that cannot go green").
    "analyst_snapshot": 3600,
    "e1_append": 600,
    "book_cadence": 900,
    # Chunk 18. It COMPOSES what the committee and the agency already computed
    # (a cached funnel state plus one book composition) and fetches nothing, so
    # the box is small on purpose: a decision contract that takes ten minutes is
    # a decision contract that is doing work it was specified not to do.
    "decision_contract": 600,
    # Chunk 18b. It reads one JSONL ledger and one local bars parquet and calls
    # `ledger_resolver.resolve_due` with a LOCAL price fetch — no vendor, no
    # network. 900 s is the same box `book_cadence` gets for the same reason:
    # both walk every record in a ledger, and a ledger that has grown enough to
    # outlive this has grown enough to be worth a look.
    "grade_forecasts": 900,
    "coverage": 300,
    # Chunk 21. It reads five receipts and a NAV map and computes nothing of
    # its own. 300 s is `coverage`'s box for `coverage`'s reason: a scoreboard
    # that takes five minutes is a scoreboard doing work it was specified not
    # to do, and the pass must never wait on the block it prints first.
    "scoreboard": 300,
    # G-fix owed hook 1 (docs/OPENCLAW_2026-09-26_LOCAL_SERVICE.md): numbered
    # promises vs the 8-K EX-99, no LLM, once per UTC day (the stamp is shared
    # with the Telegram digest, so the two callers never grade twice).
    "grade_promises": 600,
    # 2026-09-27: the health probes (`system_health.run`) -- file reads plus a
    # few read-only CLIs (schtasks, gh, railway, openclaw status), each with its
    # own timeout inside the probe. Sum of boxes 12,300 s < LAB_DRIVER_BOX_S.
    "health": 300,
    # 2026-09-27 (docs/REHEARSAL_2026-09-28_MONDAY_ENTRY.md, "nothing schedules
    # the book grade"). The three book-grading steps, each OUT of process (the
    # grade's bar load peaks in GB and pandas keeps those pages for the life of
    # an interpreter); each child is killed by its own handle at box - 60 s.
    # `grade_books` = `scripts.llm_portfolio grade` in PULL mode (a yfinance
    # batch for every book ticker once per UTC day, then ~306 grades in ~3 s);
    # `paper_accounts` = `scripts.paper_accounts_roi --no-broker` (one HTTP GET
    # for the lane track record plus the SPY leg); `bridge_report` = `report`
    # (measured 6.5 s for 31 books over 2 sessions, grows with sessions).
    # Sum of boxes 14,400 s < LAB_DRIVER_BOX_S["daily_pass"] = 21,600 s.
    "grade_books": 900,
    "paper_accounts": 600,
    "bridge_report": 600,
    # 2026-10-06 (C7). `dowjones_feeds` had no scheduled caller for nine days
    # (the health row went STALE while the corpus kept updating): ten plain-HTTP
    # RSS GETs, paced 2 s, no browser, no LLM. `query_planner_yield` reads the
    # planner's ledger, queue, page log, claims and forecast ledger -- files only.
    # Sum of boxes 14,820 s < LAB_DRIVER_BOX_S["daily_pass"] = 21,600 s.
    "dowjones_feeds": 300,
    "query_planner_yield": 120,
    # 2026-10-06 (C11, review F4). The regret ledger had no scheduled caller:
    # the decision stories' frozen alternatives priced on the bars once their
    # 5/21/63-session horizons mature. Out of process (a symbol-filtered bar
    # load plus a date-window universe for the same-band control).
    # Sum of boxes 15,420 s < LAB_DRIVER_BOX_S["daily_pass"] = 21,600 s.
    "regret": 600,
}

# ── SYSTEMS FIXES (review 2026-09-26) ────────────────────────────────────────
#: `sim_run.u_plan` REFUSES to act -- PROBE included -- when the ranker's bar
#: panel (or the ranking built on it) is older than this many CLOSED XNYS
#: sessions. Read from the parquet's own `date` column, never an mtime. 2 =
#: one missed daily refresh is tolerated, a second is a finding.
BARS_MAX_AGE_SESSIONS = 2
#: `forecast_grader` voids a due forecast as UNRESOLVABLE when its ticker's bars
#: STOPPED at least this many sessions before the panel's newest bar (the name
#: delisted: AVB and EA on 2026-09-26, both `inactive` at the venue) and its
#: window can no longer fill.
FORECAST_VOID_DELISTED_MIN_SESSIONS = 10
#: ...or when no local panel has ANY bar for its ticker and its resolution date
#: is this many calendar days in the past while the panel covers that date.
FORECAST_VOID_NO_BAR_GRACE_DAYS = 21
#: The Telegram agent is DEAD when its own heartbeat line is older than this
#: (it polls every `--interval` s, default 60). Read by `stack_health`-style
#: probes from `telegram/heartbeat.json`, never from the bot token.
TELEGRAM_AGENT_HEARTBEAT_MAX_AGE_S = 600

#: How long the analyst sweep is allowed to run INSIDE its box, in seconds.
#:
#: The box above abandons a wedged thread; this is the sweep stopping ITSELF.
#: The two are different findings and the difference is the whole point: a
#: thread abandoned at the box writes a `timeout` row and no receipt of its own,
#: while a sweep that reaches its budget flushes its parquet, writes a receipt
#: that says `truncated: N of M symbols`, and lets the pass report `ok` with the
#: shortfall NAMED. At the measured 4.45 s/symbol the 2,362-name tradable band
#: needs ~2.9 h, so this budget is a deliberate cap and not a bound anybody
#: expects the sweep to fit inside: it will truncate most days, visibly, in a
#: counted field, until the sweep is made cheaper.
#:
#: 3,300 s leaves 300 s of head-room under the 3,600 s box, so the ordinary day
#: is `ok` and a `timeout` row means something genuinely went wrong.
DAILY_PASS_ANALYST_BUDGET_S = 3300

#: How old another `scripts.daily_pass` process must be before this one kills it
#: and takes the day, in hours. Younger than this is a REFUSAL by name, exactly
#: as before: two passes launched minutes apart is a human doing something
#: deliberate, and a driver that killed its own operator's run would be worse
#: than the stall it is fixing.
#:
#: THE NUMBER IS NOT FREE. Every step above is boxed, so the longest a HEALTHY
#: pass can possibly take is the sum of the boxes: 2400 + 3600 + 600 + 900 +
#: 600 + 900 + 300 + 300 = 9,600 s = 2.67 h (it was 18,600 s = 5.17 h until the
#: analyst box came down to an hour and the grader arrived, both on
#: 2026-09-20). Six hours is above that, so a sibling
#: old enough to be killed is a sibling that has already outlived every box it
#: has — which is
#: only possible for a thread that was abandoned and a process that did not
#: exit. `test_daily_pass` pins the inequality, so raising a box without raising
#: this number turns the suite red instead of turning a healthy pass into a
#: victim.
DAILY_PASS_STALE_SIBLING_H = 6

# ── THE ALWAYS-ON LAB (chunk 14, `scripts/always_on_lab.py`) ─────────────────
#
# One supervisor that runs whenever the PC is on and drives ten loops at
# their own declared cadences. Every number it schedules on lives HERE, not in
# the script, because a cadence hardcoded in a driver is a cadence nobody can
# change without a commit to the driver.

#: The supervisor's own wake-up period, in minutes. It is the SHORTEST cadence
#: any sub-loop needs, so `lab_status.json`'s `last_tick_utc` is never staler
#: than this — a hung supervisor is detectable from its own status file inside
#: one heartbeat rather than from a human noticing the corpus stopped growing.
LAB_HEARTBEAT_MINUTES = 5

#: Per-loop period in minutes. The supervisor walks THIS dict; a loop without a
#: period here cannot run, and a period here without a handler is an
#: AssertionError at import (the `daily_pass.STEPS` discipline).
LAB_LOOP_PERIODS_MINUTES: dict = {
    # The two time-of-day drivers are checked every heartbeat; what makes them
    # fire once a day is the local-time gate plus the receipt, not the period.
    "daily_pass_dispatch": 5,
    "night_launcher_dispatch": 5,
    "news_pull": 15,
    # Chunk 20. Derived from `LAB_SOCIAL_PULL_PERIOD_S` rather than written
    # twice: the brief names the seconds constant, the supervisor walks this
    # dict in minutes, and two numbers that must agree are one number.
    "social_pull": 6 * 60,
    "l2_typing": 15,
    "decision_vs_reality": 60,
    "catalyst_calendar": 6 * 60,
    "nn_lab": 24 * 60,
    "idle_gpu_queue": 5,          # gated by LAB_IDLE_MINUTES, not by its period
    "thematic_streams": 24 * 60,
    # docs/HEALTH_PROBES_2026-09-26.md's owed caller: HEALTH.md is never older
    # than half an hour while the lab runs ($0, no model, no network order).
    "health": 30,
    "status": 5,
}

#: Hard wall-clock bound per loop call, in seconds. A loop that outlives its
#: box is recorded `timeout_after_<n>s`, its `last_tick_utc` stops advancing —
#: which is the detectable signal — and the supervisor's own heartbeat keeps
#: going, because each loop is issued FROM the top-level loop with this bound
#: and never awaited unboundedly.
LAB_LOOP_TIMEOUT_S: dict = {
    # The dispatch loops SPAWN and return; they never wait on the driver, so
    # their box bounds a process launch and a receipt read. The driver's own
    # bound is `LAB_DRIVER_BOX_S`.
    "daily_pass_dispatch": 120,
    "night_launcher_dispatch": 120,
    "news_pull": 900,
    "social_pull": 900,
    "l2_typing": 900,
    "decision_vs_reality": 300,
    "catalyst_calendar": 300,
    "nn_lab": 4 * 3600,
    "idle_gpu_queue": 60,
    "thematic_streams": 600,
    "health": 300,
    "status": 60,
}

#: How often the power plan is re-checked inside the main loop. `night_factory`
#: checks once because its longest run is hours; this supervisor runs for days,
#: and a plan that was "never sleep" at 09:00 can be changed by Windows Update
#: or a battery-saver mode by 15:00.
#: Per-source wall-clock budget for the LAB's 15-minute news increment (the daily
#: pass keeps the CLI's 600 s). 26 sources x 25 s = 650 s < the loop's 900 s box.
LAB_NEWS_SOURCE_BUDGET_S = 25.0

LAB_POWER_RECHECK_MINUTES = 60

#: Minutes with no model-touching call before the idle-GPU queue may dispatch.
LAB_IDLE_MINUTES = 20

#: The idle-GPU queue, in priority order, as `night_factory_jobs.JOBS` ids with
#: a time box in minutes. L2's backlog runs FIRST: every other item either
#: consumes its output or is orthogonal to it, and it is the single biggest
#: measured gap in the system (6,020 rows PENDING_MODEL on 2026-09-13).
LAB_IDLE_QUEUE: tuple[tuple[str, int], ...] = (
    ("L2_typed_events", 120),
    # 2026-09-19, chunk 19. Directly AFTER the backlog job and for its reason:
    # vocabulary v3 added two ids, and the rows L2 is still typing are the rows
    # this one re-reads. A 60-minute box, not 120: it reads only what a declared
    # keyword screen lets through, which is a small fraction of the corpus, and
    # it caps itself at `night_l2_retype_v3.MAX_ROWS_PER_RUN` so the box is a
    # number a pass can finish rather than one that guarantees a kill.
    ("L2_retype_v3", 60),
    # 2026-09-19, chunk 20. After the two typing jobs and for their reason: the
    # v3 rows L2_retype_v3 writes are two of this job's five variables, so
    # running it first would compute today's constraint counts from yesterday's
    # typing. A 30-MINUTE box: four of the five variables are arithmetic over
    # rows already on disk, and the fifth (comment stance) caps itself at
    # `night_social_features.MAX_STANCE_ROWS`, so the box is a number a pass can
    # finish rather than one that guarantees a kill and no receipt.
    ("S1_social_features", 30),
    # 2026-09-13 22:50: R2 panel B was read today (REJECT, 4.1 h) and a re-run
    # at temperature 0 is the same 4.1 h for the same answer. The three
    # model-dependent reads still unread take its place.
    ("X_anon_gap", 120),
    ("X2_elasticity", 120),
    ("E1_event_head", 60),
    ("X4_regime_route", 90),
    ("L4_qwen3_measure", 60),
    # 2026-09-27: the comparison that DECIDES whether the 30B replaces the 7B
    # for L2 typing -- the E-G1 240-item extraction set, local 7B vs local 30B,
    # $0. After L4 because it reads L4's best --n-cpu-moe setting.
    ("L4b_qwen3_extraction", 90),
)

# ── THE IDLE QUEUE'S SLOT (2026-09-27) ───────────────────────────────────────
#
# MEASURED: since at least 09-26 the health table read `idle_gpu_queue: timeout
# (GPU_BUSY)` and nothing in the queue ran. The loop ran each job INSIDE its own
# 60 s box; every real job outlives 60 s, the supervisor abandoned the thread,
# and the loop's name stayed in `inflight` for the life of the process -- one
# dispatch per lab restart, then "not re-issued" for ever. The job now runs on a
# worker the lab tracks as a SLOT; the loop polls it, reaps it BY PID past its
# box, and releases it.

#: Seconds a dispatching tick waits for its worker before returning `running`.
#: Well inside the loop's 60 s box; a job that finishes this fast is recorded in
#: the same tick.
LAB_IDLE_JOB_JOIN_S = 20.0

#: Seconds past a job's own box (its queue minutes) before the LAB reaps it.
#: `night_factory.run_job` kills its own tree at the box counting AWAKE seconds;
#: this is the backstop for a run_job that did not return, on the wall clock.
LAB_IDLE_JOB_REAP_GRACE_S = 600

#: A job that times out this many times in one date is skipped for the rest of
#: it, with a named row (`TIMED_OUT_TWICE_TODAY`), so one bad job cannot starve
#: the queue. A job that timed out fewer times is retried AFTER the untried ones.
LAB_IDLE_JOB_MAX_TIMEOUTS_PER_DAY = 2

#: Queue jobs that need the GPU for a DIFFERENT model than the 7B reader (L4
#: measures Qwen3-30B-A3B). While one holds the slot the typing loop does not
#: start the 7B (`GPU_BUSY`), and one is not dispatched while an Aegis 7B is
#: listening (`GPU_BUSY`): whoever holds the card first keeps it for that tick.
LAB_IDLE_JOBS_OWN_THE_GPU: tuple[str, ...] = ("L4_qwen3_measure", "L4b_qwen3_extraction")

# ── L4 / L4b: QWEN3-30B-A3B IS MEASURED, NOT ASSUMED (2026-09-27) ────────────
#
# Both jobs start and stop their OWN llama-server (a second, named server
# config on its own port) and never touch the default 7B serving config. They
# refuse while any llama-server is up on the default port, while the GPU is
# held (gpu_guard contention, a running sim session, another L4 holder), and
# on the RAM/disk floors below.

#: the candidate reader's file, beside the incumbent in `LLAMA_HOME/models`
L4_QWEN3_MODEL_FILE = "Qwen3-30B-A3B-Instruct-2507-Q4_K_M.gguf"
#: the incumbent's file, served by L4b's 7B arm on the SAME port and client
L4_INCUMBENT_MODEL_FILE = "Qwen2.5-7B-Instruct-Q4_K_M.gguf"
#: the named server's port -- NOT `LLAMA_PORT` (8080), so no caller of the
#: default reader can ever send a request to the 30B by accident
L4_PORT = 8093
#: the registered sweep, descending (fewer MoE layers on the CPU = more VRAM)
L4_N_CPU_MOE_SWEEP: tuple[int, ...] = (48, 40, 32, 24)
#: refuse below these. The 30B is 17.28 GiB mmapped; a machine with less free
#: RAM than that pages the weights and measures the disk, not the model.
L4_MIN_FREE_RAM_GB = 20.0
L4_MIN_FREE_DISK_GB = 25.0
#: /health must answer 200 within this per setting (a 17 GiB load from disk)
L4_HEALTH_WAIT_S = 600.0
#: L4's own budget, inside its 60-minute queue box, so it stops descending and
#: writes its receipt rather than being killed without one
L4_MAX_MINUTES = 50.0
#: after a stop, VRAM must be back within this of the pre-start baseline
L4_VRAM_BASELINE_TOL_MIB = 300
#: seconds to wait for VRAM to come back after the server's PID is gone
L4_VRAM_SETTLE_S = 20.0
#: tokens generated per generation probe (ignore_eos, so the count is exact)
L4_GEN_TOKENS = 128

#: L4b's own budget inside its 90-minute queue box
L4B_MAX_MINUTES = 80.0
#: the decision rule, written into the receipt BEFORE the first item is read:
#: the 30B replaces the 7B for L2 typing only if field accuracy is higher by
#: >= this many POINTS, with the paired difference's t >= L4B_MIN_T, AND the
#: nightly typing backlog at the 30B's measured seconds/item fits the night.
L4B_MIN_GAIN_PTS = 3.0
L4B_MIN_T = 2.0
L4B_NIGHT_HOURS = 8.0
#: days of news-corpus inflow averaged into "the nightly typing backlog"
L4B_BACKLOG_LOOKBACK_DAYS = 7
#: used ONLY when the inflow cannot be measured, and the receipt says so
L4B_BACKLOG_ROWS_FALLBACK = 3000
#: the 30B's --n-cpu-moe when no measured L4 receipt names a best setting
L4B_QWEN3_N_CPU_MOE_DEFAULT = 48

#: Rows the typing loop may take in one tick. One tick must not try to type a
#: 6,020-row backlog and block the next news pull.
LAB_L2_MAX_ROWS_PER_TICK = 40

#: The local/cloud overlap set for the reader-agreement (kappa) comparison. The
#: SAME rows are typed by both readers so kappa is computed on a paired sample
#: rather than on two different samples that happen to be the same size.
LAB_L2_OVERLAP_ROWS = 200

#: HARD daily cap on what the lab itself may spend at a cloud provider, in USD,
#: on the UTC day boundary `llm_analyzer._DAILY_CAP` already uses. It is a
#: PRE-CALL guard beside that module's CALL-COUNT cap (150/day, which bounds
#: calls and says nothing about spend) and beside `scripts/llm_cost_audit.py`,
#: which stays the ground-truth RECONCILIATION. `spec_always_on_lab.md` §5
#: proposed $5.00; the build brief set $3.00 and the lower number is the one
#: that ships — a cap is only a cap at the number actually enforced.
LAB_DAILY_SPEND_CAP_USD = 3.00
LAB_SPEND_CAP_ENV = "AEGIS_LAB_DAILY_SPEND_CAP_USD"

#: HARD per-RUN cap for `N9_library_autopsy` (chunk 19, re-test 3 of the
#: 2026-09-19 failure thesis), in USD. It is a PER-INVOCATION cap and not a day
#: cap, for the same reason `L2_typed_events`' `--max-usd` is: the run that has
#: to happen is a few dollars in one sitting, and a day cap that refused it
#: would be a gate that cannot go green. `LAB_DAILY_SPEND_CAP_USD` still binds
#: whenever the LAB is the caller; the receipt names which one was in force.
#:
#: The number: §51's own estimate is ~$0.001 per autopsy, and the failure
#: thesis ranks this the cheapest lever in the ledger. $10.00 buys several
#: thousand proposals at that rate and is small against the $56.98 balance --
#: it is a ceiling on a mistake, not a budget to spend.
N9_LIBRARY_AUTOPSY_MAX_USD = 10.00

#: How far the CAP's read of the call ledger and the RECEIPT's read of the same
#: ledger may differ before a metered run refuses to continue, in USD (chunk
#: 22c, 2026-09-21).
#:
#: THE NUMBER IS ONE CALL'S WORST CASE and it mirrors
#: `backend.services.investigator_night.WORST_CASE_CALL_USD` deliberately --
#: `test_cap_reader_agreement.py` fails if the two ever drift apart. The
#: tolerance exists only so that a row landing between two reads of a live
#: ledger is not a refusal; it is NOT a budget for disagreement. The failure it
#: was written for was 750x wide: N9 run 3 (2026-09-21) stopped "at $10.0479 of
#: $2.00" while `cap_block.estimated_spend_at_stop_usd` read **$0.013238** over
#: 167 ledger reads, because `_RunCap.refresh()` called `spend_from_ledger`
#: WITHOUT a purpose and so summed L2's rows (`l2_event_extraction`) while the
#: receipt summed N9's own 8,342 (`n9_library_autopsy`). Same file, same
#: instant, two views; a cap that compares a number the writer never produced
#: cannot bind at any tolerance.
CAP_READER_AGREEMENT_TOLERANCE_USD = 0.05

#: A run's two readers may also differ by this many CALLS -- one row, so that a
#: ledger appended to between the cap's read and the receipt's read is not a
#: refusal. Anything wider is a wiring fault, which is what 22c is about.
CAP_READER_AGREEMENT_TOLERANCE_CALLS = 1

#: Which loops touch the model. They are serialised against each other by an
#: in-process lock and paused wholesale when the power plan allows sleep.
LAB_MODEL_LOOPS: tuple[str, ...] = ("l2_typing", "nn_lab", "idle_gpu_queue")

#: Which loops touch the network. Paused with the model loops on a sleep
#: refusal only for the GPU half; the news pull keeps running (it cannot be
#: harmed by a suspend mid-call the way an 8-hour GPU job can).
LAB_NETWORK_LOOPS: tuple[str, ...] = ("news_pull", "social_pull",
                                      "catalyst_calendar", "thematic_streams")

# ── MODEL ROUTING (chunk G, 2026-09-26) ─────────────────────────────────────
#
# Murat's brief: "llama-server not permanently resident; idle shutdown; /ask
# local on demand; /deep DeepSeek or NVIDIA; /compare all three frozen and
# graded". The local model is started by the CALLER that needs it
# (`llama_server.ensure(reason)`), never at boot, and stopped by PID by the
# process that started it once nothing has used it for IDLE_SHUTDOWN_S.
# DeepSeek stays the sole PRIMARY (`llm_analyzer.SOLE_PROVISIONED_PROVIDER`);
# NVIDIA is a NAMED adjudicator and local is on-demand -- neither is a fallback.

#: THE boot switch. False = nothing starts llama-server at boot: not the desktop
#: shell, not `night_run_until`, not the always-on lab (whose own flag below now
#: READS this one). True restores the pre-2026-09-26 resident behaviour.
MODEL_ROUTING_START_AT_BOOT = False

#: Minutes without a call before the server is stopped by PID. Read by the
#: in-process watchdog AND by `scripts/llama_reaper.py`, the standalone process
#: `ensure()` spawns so the stop no longer dies with whichever client started
#: the server (G-fix, adjudication row 7, 2026-09-26).
MODEL_ROUTING_IDLE_MIN = 15

#: Seconds without a call before the starting process stops the server by PID.
MODEL_ROUTING_IDLE_SHUTDOWN_S = MODEL_ROUTING_IDLE_MIN * 60

#: How often the reaper reads the owner note. One file read and one socket probe.
MODEL_ROUTING_REAPER_TICK_S = 30

#: How often the idle watchdog looks. Cheap: one file read and, when due, a stop.
MODEL_ROUTING_WATCHDOG_TICK_S = 30

#: How long `ensure()` waits for /health after a start (a 30B-A3B loads from disk).
MODEL_ROUTING_ENSURE_WAIT_S = 240.0

#: Per-provider route. `cost_status` is DERIVED from `LLM_PRICE_PER_MTOK`, never
#: declared: LISTED means the telemetry row carries a dollar figure (a free
#: tier is LISTED at $0.00), UNPRICED means `cost_usd=None` and every total that
#: includes it is a lower bound.
#:
#: THE NVIDIA ADJUDICATOR (G-fix, adjudication row 7, chosen 2026-09-26).
#: `nvidia/nemotron-3-super-120b-a12b` was a rate-limited REASONING model whose
#: empty `content` got parsed out of its chain of thought. Replaced by a
#: NON-reasoning instruct model: `GET /v1/models` was queried once on 2026-09-26
#: (82 ids listed), the `*instruct*` Llama/Nemotron/Qwen ids were probed in
#: catalogue order with one 5-token call each, and the FIRST that served was
#: kept. Served: meta/llama-3.2-11b-vision-instruct (1.0 s, content "OK", no
#: reasoning_content). Timed out: meta/llama-3.2-90b-vision-instruct. 404 for
#: this account: nvidia/llama-3.1-nemotron-51b-instruct, -70b-instruct,
#: nvidia/nemotron-4-340b-instruct. Receipt:
#: backend/data/optimus/model_routing/nvidia_models_2026-09-26.json.
#: It is an 11B model: whether it is a GOOD second opinion is what bake-off
#: E-G1 measures, not what this line asserts.
NVIDIA_ADJUDICATOR_MODEL = "meta/llama-3.2-11b-vision-instruct"
NVIDIA_ADJUDICATOR_MODEL_CHOSEN = "2026-09-26"
MODEL_ROUTING_NVIDIA_MODEL = NVIDIA_ADJUDICATOR_MODEL
#: 429 handling on the NVIDIA path: tries, first backoff (s), jitter (s).
MODEL_ROUTING_NVIDIA_TRIES = 3
MODEL_ROUTING_NVIDIA_BACKOFF_S = 4.0
MODEL_ROUTING_NVIDIA_JITTER_S = 2.0
MODEL_ROUTING_NVIDIA_DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"
MODEL_ROUTING_LOCAL_MODEL = "local"
MODEL_ROUTING_MAX_TOKENS = 700
MODEL_ROUTING_TIMEOUT_S = 180.0
MODEL_ROUTING_PROVIDERS: dict[str, dict] = {
    name: {"model": model, "role": role,
           "cost_status": "LISTED" if model in LLM_PRICE_PER_MTOK else "UNPRICED"}
    for name, model, role in (
        ("deepseek", "deepseek-chat", "primary"),
        ("nvidia", MODEL_ROUTING_NVIDIA_MODEL, "adjudicator"),
        ("local", MODEL_ROUTING_LOCAL_MODEL, "on_demand"),
    )
}

#: RETIRED by the G-fix (2026-09-26): chunk G's direction /compare froze one
#: `beats_benchmark` row per provider at this horizon. It wrote 0 rows before it
#: was replaced by the E-G1 read below; kept only so an old receipt still reads.
MODEL_ROUTING_COMPARE_HORIZON = 5
MODEL_ROUTING_COMPARE_BENCHMARK = "SPY"

#: /compare was re-scoped by the G-fix (adjudication row 7): direction skill is
#: -7.9% held out, so a direction contest picks its winner by noise. It now
#: READS the extraction bake-off E-G1 (graded against the analyst-revisions
#: file the same day). Magnitude stays the forward test (already in u_forecast).
MODEL_ROUTING_BAKEOFF_N = 240
MODEL_ROUTING_BAKEOFF_N_MATCHED = 180          # the rest are no-revision controls
MODEL_ROUTING_BAKEOFF_SEEN_MAX = "2026-09-20"   # first_seen_utc <= this
MODEL_ROUTING_BAKEOFF_CAP_USD = 0.15
MODEL_ROUTING_BAKEOFF_FLUSH_EVERY = 20
MODEL_ROUTING_BAKEOFF_SESSIONS_AFTER = 5        # revision window: sessions after first_seen
MODEL_ROUTING_BAKEOFF_DAYS_BEFORE = 2           # ... and calendar days before published
MODEL_ROUTING_BAKEOFF_NVIDIA_MIN_GAP_S = 2.0    # ~30 RPM, under the ~40 RPM free tier

#: The Telegram daily digest grades numbered promises once per UTC day from this
#: date on (MU's FQ4 print, 2026-09-30, is the first due promise). Nothing else
#: in the repo called `source_reads --grade-promises` (G-fix task 6).
MODEL_ROUTING_GRADE_PROMISES_FROM = "2026-09-30"

#: MAY THE LAB START THE MODEL SERVER? (amended 2026-09-18, measured)
#:
#: The original rule was "the desktop app and a human are the only starters"
#: (`spec_always_on_lab.md` §1.4). On 2026-09-18 the PC rebooted at 06:57 after
#: an unclean shutdown (Kernel-Power 41, no bugcheck report; the 09-17 13:17
#: one WAS a 0x116 nvlddmkm bugcheck); the lab restarted itself from the Startup folder and then sat
#: at `PENDING_MODEL` / `MODEL_IN_USE` for the whole day, because NOTHING starts
#: `llama-server` after a reboot. "Live whenever the PC is on" cannot depend on
#: a human opening an app, so the lab is now a starter too.
#:
#: What does NOT change: the lab never STOPS a server, and a FOREIGN server --
#: one Aegis did not start -- is still not ours to touch.
LAB_STARTS_MODEL_SERVER = MODEL_ROUTING_START_AT_BOOT   # 2026-09-26: on demand, see MODEL ROUTING

#: How many times in ONE date the lab may start the model server. A server that
#: keeps dying is a finding, not a retry loop: at the cap the lab refuses BY
#: NAME (`MODEL_SERVER_START_CAP_REACHED`) and the refusal is in `lab_status.json`
#: where a reader can see it, rather than a silent restart every five minutes.
LAB_MODEL_SERVER_MAX_STARTS_PER_DAY = 3

#: 2026-09-27: `LAB_MODEL_SERVER_MAX_STARTS_PER_DAY` above now counts only
#: RESTARTS AFTER DEATH -- a start whose previous lab-started server ended with
#: no row in `llama_server`'s stop ledger (no idle stop by the reaper, no
#: operator stop). An idle stop is the reaper working as designed; counting it
#: spent the 3-a-day cap by mid-afternoon and typing waited until midnight.
#: THIS is the separate, generous ceiling on ALL starts in one date, so a loop
#: that flaps start -> idle stop -> start still stops, by name
#: (`MODEL_SERVER_TOTAL_START_CEILING_REACHED`).
LAB_MODEL_SERVER_MAX_TOTAL_STARTS_PER_DAY = 40

#: THE OPERATOR HOLD. A file of this name under `backend/data/optimus` makes the
#: lab refuse to start the server (`OPERATOR_HOLD`) for as long as it exists.
#: Needed the moment the lab became a starter: the fast suite must run with the
#: server STOPPED (9.5-12 GB resident; suites were killed for low memory on
#: 09-14), and a lab that restarts the server within one heartbeat of the stop
#: would undo the recipe mid-suite. Touch it, stop the server, run the suite,
#: delete it. The lab's status names the hold while it stands.
LAB_MODEL_SERVER_HOLD_NAME = "MODEL_SERVER_HOLD"

#: Seconds the lab waits for `/health` after a start. ZERO on purpose: the
#: idle-GPU queue's own box is 60 s and a multi-GB model takes longer than that
#: to load, so the lab starts the server, records the start, and lets the NEXT
#: heartbeat (five minutes) find it ready. `llama_server.start` calls that state
#: `starting`, which is a state and not a failure.
LAB_MODEL_SERVER_START_WAIT_S = 0.0

#: Seconds the L2 typing loop waits for `/health` after an ON-DEMAND start
#: (`llama_server.ensure`, 2026-09-27). NOT zero, unlike the boot starter above:
#: an on-demand server is reaped after `MODEL_ROUTING_IDLE_MIN` (15) idle, and
#: the typing loop's period is also 15 minutes -- a server started and left for
#: the next tick can be reaped before that tick arrives, which is PENDING_MODEL
#: for ever by a different road. It waits inside the loop's 900 s box instead.
LAB_L2_ON_DEMAND_WAIT_S = 240.0

#: Consecutive calendar DATES of real coverage before the lab is ACCEPTED.
#: Dates, not task runs: `ONLOGON` can fire and die repeatedly in a bad state
#: and still produce three "runs".
LAB_ACCEPTANCE_DATES = 3

#: Hours the machine must have been on for a date to COUNT toward acceptance.
LAB_ACCEPTANCE_MIN_HOURS = 6

# ── THE LAB OWNS ITS CLOCK (chunk 17, 2026-09-19) ────────────────────────────
#
# MEASURED, and twice. Both Windows scheduled tasks are registered
# "Interactive only": `AegisDailyPass` (06:30 daily) and
# `AegisIIF1NightLauncher` (16:00 Mon-Fri). On 2026-09-19 both reported
# `0x80070520` -- "a specified logon session does not exist" -- and for four
# days the week before both reported `0x80070420` -- "an instance of this task
# is already running", behind the daily pass that wedged for four days. Two
# distinct scheduler failure codes in one week, neither of them visible to
# anything but a `schtasks /Query /V` somebody happened to run.
#
# The always-on lab is the only process that is genuinely "live whenever the PC
# is on", so it dispatches these two on its own clock. The scheduled tasks stay
# registered as a FALLBACK: whichever fires first writes the receipt, and the
# other one's already-ran gate reads that receipt and stands down. Deleting
# them is Murat's decision, not a session's.

#: Local (machine) wall-clock time at or after which the lab dispatches the
#: daily pass, HH:MM. There is deliberately no upper bound on the window: a
#: machine switched on at 09:00 should still get its pass, and the receipt gate
#: is what stops a second one. A grace window would turn "late" into "never",
#: which is the silence this chunk exists to remove.
LAB_DAILY_PASS_LOCAL_TIME = "06:30"

#: Local time at or after which the lab dispatches the IIF-1 night launcher.
#: It MUST equal `IIF1_LAUNCHER_LOCAL_START_TIME` -- two clocks for one job is
#: how a launcher fires ten minutes late for three weeks (2026-09-18). Written
#: as a literal rather than as an alias so the equality is a TEST
#: (`test_always_on_lab.py`) rather than a tautology.
LAB_NIGHT_LAUNCHER_LOCAL_TIME = "16:00"

#: The launcher's coarse pre-filter, exactly as the scheduled task's
#: WEEKLY/MON-FRI is: NOT the calendar. `night_launcher.evaluate_launch` reads
#: XNYS and refuses holidays itself; this only avoids waking the launcher on a
#: Saturday.
LAB_NIGHT_LAUNCHER_WEEKDAYS_ONLY = True

#: Per-driver wall-clock box, in seconds, measured from the dispatch to the
#: moment its RECEIPT lands on disk. It does NOT bound the child process: the
#: lab starts these detached and never waits on them, and the launcher in
#: particular writes its receipt BEFORE it hands off to a night that may run
#: for hours. Past the box with no receipt the dispatch row goes `timeout`,
#: which is a finding a reader can see rather than a dispatch nobody can tell
#: from a success.
#:
#: THE DAILY PASS NUMBER IS NOT FREE. Every step of the pass is boxed
#: (`DAILY_PASS_STEP_BOX_S`), so the longest a HEALTHY pass can take is the sum
#: of those boxes -- 9,600 s since 2026-09-20 (18,600 s before it, and 9,300 s
#: before the scoreboard step). This must
#: exceed that sum with a margin, or a healthy pass would be reported as a
#: timeout; `test_always_on_lab.py` pins
#: the inequality, so raising a step box without raising this turns the suite
#: red instead of turning a healthy pass into a false alarm. 21,600 s (6 h) is
#: also `DAILY_PASS_STALE_SIBLING_H`, which is the hour at which the pass's own
#: sibling rule would call that process stale -- the two agree on purpose.
LAB_DRIVER_BOX_S: dict = {
    "daily_pass": 6 * 3600,
    "night_launcher": 900,
}


# ---------------------------------------------------------------------------
# SOCIAL PHASE 1 (chunk 20, 2026-09-19 —
# `docs/research_notes/2026-09-19/spec_social_video_pipeline.md`)
#
# Two sources behind two keys that DO NOT EXIST YET. Every number here is a
# ceiling on somebody else's allowance, not a target: the collector refuses by
# key NAME when a key is absent, and the refusal is the live path today.
# ---------------------------------------------------------------------------

#: YouTube Data API v3 quota units a `search.list` call costs. NOT a knob —
#: it is Google's price and it is here so the arithmetic on the receipt has one
#: source. The whole free day is 10,000 units, so this number times the query
#: list is the entire budget: 100 searches, total, per day.
SOCIAL_YOUTUBE_SEARCH_UNITS = 100

#: The free daily quota, in units, resetting at MIDNIGHT PACIFIC (not UTC — see
#: `social_pull.YOUTUBE_QUOTA_TZ`; getting the timezone wrong does not fail, it
#: silently spends tomorrow's allowance this evening). There is no paid tier
#: for this API, only a manual extension form that takes weeks, so an exhausted
#: day is exhausted.
SOCIAL_YOUTUBE_DAILY_UNITS = 10_000

#: Posts read per subreddit per pass. Reddit's documented ceiling is 100
#: queries/minute per OAuth client and each post costs one extra call for its
#: comment tree, so one pass over the seven declared subs is about
#: 7 x (1 + 50) = 357 calls — minutes at the paced rate, not seconds.
SOCIAL_REDDIT_POSTS_PER_SUB = 50

#: Comments kept per post. `replace_more(limit=0)` drops the "load more" stubs
#: rather than expanding them (each expansion is another API call), so this cap
#: and that rule TOGETHER are the dispersion variable's denominator — which is
#: why both are printed on the receipt instead of assumed.
SOCIAL_REDDIT_COMMENTS_PER_POST = 200

#: THE SOCIAL LOOP'S CADENCE, in seconds (chunk 20 T4). Six hours, and the
#: number is the YouTube quota's, not a preference: the whole free day is
#: 10,000 units and a `search.list` costs 100, so it is **100 searches a day,
#: total**. Four passes a day over the five declared queries spends 2,000 of
#: them; a fifteen-minute cadence like the news loop's would spend the day's
#: allowance before lunch and buy nothing, because the same query returns the
#: same videos.
#:
#: `LAB_LOOP_PERIODS_MINUTES["social_pull"]` is this in minutes and
#: `test_always_on_lab.py` pins the two to agree — two numbers that must match
#: are one number, and the brief names this one.
LAB_SOCIAL_PULL_PERIOD_S = 6 * 3600

#: Seconds between calls to ONE social provider inside a pass. Single-threaded,
#: so this IS the rate limit. Reddit's documented ceiling is 100 queries/minute
#: per OAuth client; 1.0 s is well inside it and PRAW paces itself on top.
LAB_SOCIAL_PACE_S = 1.0

# ---------------------------------------------------------------------------
# THE SCENARIO GYM (S2) — spec_decision_engine_and_scenario_gym.md §C
# ---------------------------------------------------------------------------
#
# Murat, 2026-09-20: *"we cant be fully sure but we can have a gut feeling ...
# test with llm and made up scenarios (make good and bad scenarios using data
# we have like same situation in a fiction setting to see what it will
# respond)"*. `scripts/night_scenario_gym.py` is that test. Every number it
# needs is here, because a gym whose N and whose adoption floor live in the
# script is a gym whose floor moves with the run that wanted it to move.

#: The cell draw's seed. Fixed per the spec (§C "seed 20260920") so a re-run
#: proves it asked the same question; the cells' sha256 is what checks it.
SCENARIO_GYM_SEED = 20260920

#: Decision points in a full run. §C's power table: at N=300 the per-decision
#: MDE on a 20-session mean is ±2.81 pp off the panel's 17.39% sd, and the
#: ~19 available month blocks are what the PRIMARY block-paired number is
#: computed over. N=1,000 buys only the calibration-decile read.
SCENARIO_GYM_CELLS = 300

#: `--smoke`. SIX arms per cell (real, good twin, bad twin, a sign-matched
#: control for each twin, and the shuffled control), so this is 120 local
#: completions. (2026-09-20: the comment said five and 100 after the control
#: arms were split by sign; the run was right and the comment was stale.)
SCENARIO_GYM_SMOKE_CELLS = 20

#: The job's own time box in minutes, the same 90 the night queue gives it.
#: The job stops ASKING at the box and grades what it has: a job killed at its
#: limit writes no receipt at all (2026-09-10, G3 at generation 340).
SCENARIO_GYM_BOX_MINUTES = 90

#: Completion budget for one decision. The schema is five fields and one short
#: falsifier sentence; 160 tokens is that with room, and a reply that runs past
#: it fails the schema and is counted as REFUSED_SCHEMA rather than repaired.
SCENARIO_GYM_MAX_TOKENS = 160

#: `size_pct` bounds in the committed-decision schema. 0..10 per §C.
SCENARIO_GYM_MAX_SIZE_PCT = 10.0

#: The per-cell date shift that makes a real month a FICTIONAL one, in days:
#: (minimum, maximum) magnitude, sign drawn from the same seeded hash. Numbers
#: — returns, volumes, prices — are kept verbatim; only date LITERALS move, and
#: a bare four-digit year is not a date literal (it is as often a count).
SCENARIO_GYM_DATE_SHIFT_DAYS = (120, 600)

#: Below this many gradeable decisions the calibration decomposition is refused
#: by name (INSUFFICIENT_N) rather than computed on tiny bins. It is
#: `calibration.MIN_N_FOR_DECOMPOSITION`'s own floor, named here so the gym's
#: receipt can print the number it refused against.
SCENARIO_GYM_MIN_N_FOR_CALIBRATION = 45

#: THE ADOPTION FLOOR, AND IT IS A CODE-ENFORCED CAP, NOT AN INTENTION.
#: §C's adoption rule 4: the gym's `reliability_weight` stays at 0 until it has
#: at least this many graded decisions AND its own forward record. Spec §E
#: names the failure this prevents — "`reliability_weight` computed once and
#: never re-measured is a thumb on the scale wearing a calibration label".
SCENARIO_GYM_ADOPT_MIN_N = 300
#: ... AND at least this many INDEPENDENT month blocks among the graded cells
#: (Murat, 2026-09-20: "three hundred correlated scenarios are not 300
#: independent observations"; canon section 58: n_effective counts date
#: blocks). Twelve is a year of months; the panel offers ~19. A receipt that
#: cannot count its blocks is CANNOT DETERMINE and is not adopted.
SCENARIO_GYM_ADOPT_MIN_BLOCKS = 12

# ---------------------------------------------------------------------------
# J1 -- THE ERROR DATASET (chunk 24, 2026-09-21). `scripts/night_error_dataset.py`
# ---------------------------------------------------------------------------

#: Round-trip cost is 2 x this. Pinned EQUAL to `night_g3_evolve_v2.COST_BPS` by
#: `test_night_error_dataset.py` so the error dataset and the evolutionary
#: search never price the same trade two ways -- a `COSTS_KILLED_EDGE` label
#: computed at a different cost rate than the search uses is a label about the
#: constant, not about the trade.
J1_COST_BPS_PER_SIDE = 25.0

#: `HIGH_CONFIDENCE_WRONG` fires at or above this probability. 0.70 is the
#: threshold the task declared; it is a constant here so the cluster rule and
#: the receipt can never disagree about it.
J1_HIGH_CONFIDENCE_P = 0.70

#: `LOW_CONFIDENCE_RIGHT` fires at or below this probability.
J1_LOW_CONFIDENCE_P = 0.55

#: A REFUSED/PROBE/EXPLORE name whose excess over its own horizon reaches this
#: many PERCENT is a refusal (or an under-funded exploration) worth a row of its
#: own. 5% is the task's declared bar; it is deliberately high, because the
#: point is to find gates that cost real money rather than to relabel noise.
J1_EXCESS_PERFORMED_PCT = 5.0


# ── J2_missed_opportunity (2026-09-21) ──────────────────────────────────────
# The night job that asks what the market did that we did not, and whether
# anything on our own disk said so beforehand. `scripts/night_missed_opportunity.py`.

#: sessions of tape the nightly screen looks back over.
MISSED_OPP_WINDOW_SESSIONS = 21
#: each name is scored on its BEST contiguous sub-window of excess return, not
#: on the window total: a name that gave 20% back over the month and a name
#: that never moved look identical on a 21-session sum, and the question is
#: about the MOVE.
MISSED_OPP_SUBWINDOW_SESSIONS = 5
#: how many names reach the precursor check and the paired read.
MISSED_OPP_TOP_K = 30
#: a smoke run proves the job runs end to end; no rate may be read from it.
MISSED_OPP_SMOKE_TOP_K = 3
#: the dollar-volume floor, and it is PRINTED on every receipt. Without one the
#: same sub-dollar tape wins every night and the job says nothing about
#: anything we could have traded.
MISSED_OPP_MIN_DOLLAR_VOL = 5_000_000.0

#: calendar days of history the PIT precursor check may read, all of it dated
#: strictly BEFORE the move's first session.
MISSED_OPP_PRECURSOR_LOOKBACK_DAYS = 30
#: distinct Form 4 open-market buyers that make a CLUSTER rather than a trade.
MISSED_OPP_INSIDER_CLUSTER_MIN = 2
#: |ΔMedian target| that counts as a revision, in percent.
MISSED_OPP_REVISION_PCT = 5.0
#: |Δanalyst count| that counts as a coverage change.
MISSED_OPP_COVERAGE_MIN = 1
#: a news burst is measured against the NAME'S OWN base rate — ten stories is a
#: quiet week for AAPL and a klaxon for a micro-cap — and needs both a floor
#: and a multiple, because 1 row against a base of 0.2 is not a burst.
MISSED_OPP_NEWS_BURST_MULT = 2.0
MISSED_OPP_NEWS_BURST_MIN_ROWS = 3

#: the digest handed to BOTH readers: rows and characters per row.
MISSED_OPP_DIGEST_ROWS = 12
MISSED_OPP_DIGEST_CHARS = 700
#: the answer ceiling. On a reasoning model the ceiling bounds thinking PLUS
#: answer, so a truncated reply is a refusal, not a short answer.
MISSED_OPP_MAX_TOKENS = 320

#: THE HARD CAP: the `_RunCap` backstop for billing that lands after the last
#: ledger read. `--max-usd` defaults to it.
MISSED_OPP_MAX_USD = 4.5
#: THE SOFT STOP: where the job stops ASKING. Two numbers on purpose — one
#: number has to be either too tight to finish or too loose to bind, and the
#: 2026-09-21 breach ($10.05 under a $2.00 cap) was a cap that never bound at
#: all because it was reading another job's rows.
MISSED_OPP_SOFT_STOP_USD = 4.0
#: rows between ledger re-reads. `read_calls()` is ~1.4 s cold over 120k rows;
#: paying that per row would cost more than the row.
MISSED_OPP_FLUSH_EVERY = 5

#: a precursor class PRESENT on at least this many missed names becomes a
#: CURRICULUM line — a named experiment, never a finding.
MISSED_OPP_CURRICULUM_MIN_NAMES = 3
#: the paired McNemar's alpha. It decides only whether tonight's receipt says
#: BELIEF_CHANGED; one night is one night, and the standing question is whether
#: the difference accumulates across nights.
MISSED_OPP_PAIRED_ALPHA = 0.05

# ── u_forecast: the sim's daily investigator forecasts (Builder O1, 2026-09-25) ──
#: Hard ceiling on names asked per UTC day. The union (Murat's book, every
#: frozen llm_portfolio book, the funnel shortlist, the top revision names) is
#: truncated in that priority order; the receipt names what was cut.
FORECAST_MAX_NAMES_PER_DAY = 160  # 60 cut MRK/ASML/VRTX/the Asia book on 2026-09-25 (reviewer row 7); ~$0.40/day at 160
#: Dollar cap per UTC day, read from the SAME telemetry ledger the calls are
#: written to (`llm_telemetry.spend(purpose=FORECAST_PURPOSE)`), never from a
#: counter this process keeps -- 2026-09-21's $10.05 under a $2.00 cap was a cap
#: that read another ledger.
FORECAST_DAILY_CAP_USD = 2.0
#: The telemetry `purpose` every u_forecast call is written under.
FORECAST_PURPOSE = "u_forecast"
#: The model OpenClaw is asked to route to. Priced in LLM_PRICE_PER_MTOK under
#: its bare name (`deepseek-flash`).
FORECAST_MODEL = "deepseek/deepseek-flash"
#: How many of the top 90-day revision-activity names join the union.
FORECAST_TOP_REVISION_NAMES = 20
#: The unit gives up on the day after this long, and says so.
FORECAST_UNIT_TIMEOUT_S = 7200
#: A DEPENDENCY failure is not a cap (2026-09-28 incident, backend/data/optimus/
#: incidents/u_forecast_dead_2026-09-27.json): on 2026-09-27 the OpenClaw gateway
#: dropped the first call (code 1006, `RC_NONZERO`) and the day was filed
#: `REFUSED_CAP` with $0.00 of a $2.00 cap spent, terminal for the UTC day.
#: Now a transport failure (`TIMEOUT` / `RC_NONZERO` / OSError launching the
#: CLI) is retried on the SAME name up to this many calls in one run...
FORECAST_DEP_RETRY_MAX_ATTEMPTS = 4
#: ...sleeping these seconds before call 2, 3 and 4 (450 s in all). Worst run:
#: 4 calls x 420 s agent timeout + 450 s = 2,130 s, inside
#: FORECAST_UNIT_TIMEOUT_S (7,200 s). A failed call costs $0 (0 tokens priced).
FORECAST_DEP_RETRY_BACKOFF_S = (30.0, 120.0, 300.0)
#: Then the run ends `REFUSED_DEPENDENCY_DOWN`, which does NOT end the day: a
#: later sim cycle resumes it, at most this many runs per UTC day...
FORECAST_DEP_MAX_RUNS_PER_DAY = 8
#: ...and no sooner than this many seconds after the last failed run (8 runs x
#: 1 h spans a reader night that holds the gateway for several hours).
FORECAST_DEP_RETRY_MIN_GAP_S = 3600
#: The forecast WRITERS the health probe `system_health.p_u_forecast` counts
#: one by one (2026-09-28: it counted every specialist, so 167 thesis-card and
#: source rows kept `u_forecast` ALIVE while evidence_v3 wrote 0). `prefix`
#: matches the row's `specialist`; `scheduled: "utc_day"` means a caller runs
#: it every UTC day, so ZERO rows since the start of the previous UTC day is
#: DEGRADED by name; `None` is reported, never graded.
FORECAST_WRITERS: dict = {
    "u_forecast": {"prefix": "investigator:evidence_v3", "scheduled": "utc_day",
                   "receipt": "forecasts/day_{day}.json"},
    "thesis_card": {"prefix": "thesis_card:", "scheduled": None},
    "source_claims": {"prefix": "source:", "scheduled": None},
    "review": {"prefix": "review:", "scheduled": None},
    "promise": {"prefix": "promise:", "scheduled": None},
}


# ── BOOK FACTORY / LLM PORTFOLIO BOOKS (Builder O2, 2026-09-25) ─────────────
# `llm_portfolio.freeze` constraints by `kind`, the twins' theme ETFs, the
# global price cache and the book factory's spend cap. Read by
# `backend/services/llm_portfolio.py`, `backend/services/global_prices.py` and
# `scripts/book_factory.py`.

#: The Bloomberg Global Trading Challenge contract, as far as a freeze can check
#: it. WLS membership itself is NOT checked here (chunk K's competition_book).
BOOK_COMPETITION_MAX_WEIGHT = 0.10
BOOK_COMPETITION_MIN_NAMES = 8
BOOK_COMPETITION_MAX_CASH = 0.02
BOOK_COMPETITION_OBJECTIVE_MUST_NAME = "Relative P&L vs WLS"
BOOK_COMPETITION_OBJECTIVE = "Relative P&L vs WLS, 2026-10-12 to 2026-11-13"
BOOK_PERSONAL_OBJECTIVE = "maximise 126-session return vs SPY, net of costs"

#: The WLS series is not on this machine. URTH (iShares MSCI World) is the
#: PROXY: developed markets only, large/mid only, so it omits EM and small caps
#: that WLS holds. Every competition grade prints this caveat.
BOOK_WLS_PROXY = "URTH"
BOOK_WLS_PROXY_CAVEAT = (
    "URTH (MSCI World: developed, large/mid) is a PROXY for Bloomberg WLS "
    "(World Large/Mid/Small incl. EM). Tracking error is UNMEASURED; the "
    "challenge portal's number is the truth, this is not.")

#: Exchange suffixes (yfinance convention) that the US bars panel never holds.
BOOK_GLOBAL_SUFFIXES = (".TW", ".KS", ".T", ".HK", ".AS", ".PA", ".DE", ".L",
                        ".ST", ".OL", ".MI", ".TO", ".AX", ".SW", ".KQ", ".SS",
                        ".SZ", ".NS", ".CO", ".HE", ".BR", ".MC", ".TWO")

#: Tickers a competition book may not hold (no ETFs). Not exhaustive -- a
#: freeze cannot look up a fund's legal form offline -- so a position may also
#: declare `is_etf: true`, and the theme ETFs below are always included.
BOOK_KNOWN_ETFS = frozenset({
    "SPY", "QQQ", "IWM", "RSP", "DIA", "VTI", "VOO", "URTH", "ACWI", "VT",
    "EFA", "EEM", "VEA", "VWO", "SMH", "SOXX", "XLK", "XLE", "XLF", "XLI",
    "XLV", "XLU", "XLB", "XLY", "XLP", "XLC", "XLRE", "XBI", "IBB", "LIT",
    "URA", "URNM", "QTUM", "BETZ", "BOTZ", "ROBO", "GRID", "ARKK", "TAN",
    "ICLN", "GLD", "SLV", "TLT", "HYG", "LQD", "ITA", "IGV", "KWEB", "FXI",
    "EWJ", "EWT", "EWY", "EWG", "INDA", "COPX", "REMX", "NLR", "HACK",
})

#: Theme -> the ETF a `sector_etf` twin holds at that theme's weight. A theme
#: not in the map falls to `default` (SPY for personal, BOOK_WLS_PROXY for
#: competition books -- see llm_portfolio.twins).
THEME_ETF_MAP = {
    "semis": "SMH", "memory": "SMH", "foundry": "SMH",
    "power_grid": "GRID", "ai_power": "GRID", "industrials": "XLI",
    "lithium": "LIT", "quantum": "QTUM", "nuclear": "URA", "uranium": "URA",
    "biotech": "XBI", "pharma": "XBI", "gambling": "BETZ",
    "robotics": "BOTZ", "policy": "SPY", "defense": "ITA", "energy": "XLE",
    "software": "IGV", "china": "KWEB", "materials": "XLB", "default": "SPY",
}

#: Ticker -> theme for names whose thesis text carries no theme keyword
#: ("Q3 earnings Oct 15" says nothing about semis). Consulted after a declared
#: `theme` and before keyword inference; recorded as `theme_source: ticker_map`.
BOOK_TICKER_THEMES = {
    "TSM": "semis", "2330.TW": "semis", "NVDA": "semis", "AMD": "semis",
    "AVGO": "semis", "MU": "semis", "ASML": "semis", "ASML.AS": "semis",
    "000660.KS": "semis", "005930.KS": "semis", "8035.T": "semis",
    "IONQ": "quantum", "RGTI": "quantum", "QUBT": "quantum", "QBTS": "quantum",
    "DKNG": "gambling", "FLUT": "gambling", "PENN": "gambling", "MGM": "gambling",
    "MP": "materials", "CCJ": "nuclear", "LEU": "nuclear", "OKLO": "nuclear",
    "SMR": "nuclear", "VRT": "power_grid", "GEV": "power_grid",
    "NVT": "power_grid", "ETN": "power_grid", "ALB": "lithium",
}

#: Global price cache (yfinance) -- one pull per ticker per UTC day.
BOOK_GLOBAL_HISTORY_DAYS = 400

#: THE MISSING-NAME RULE IS VERSIONED (adjudicated 2026-09-27, rehearsal
#: `docs/REHEARSAL_2026-09-28_MONDAY_ENTRY.md`). A book whose ENTRY SESSION is on
#: or after this date is graded under `grade_rule_version: 2`: a name with no
#: valid entry price (halted OR a NaN open -- one rule for both) enters at its
#: next valid open, and until then its weight sits in cash at 0% and is NOT
#: re-weighted onto the other names. A book that entered earlier keeps version 1
#: exactly, because numbers were already published under it.
LLM_BOOK_GRADE_RULE_V2_FROM = "2026-09-28"
#: Version 2 only: a book with less than this share of its weight priced as
#: frozen (declared cash + names that have entered) once it has had
#: `LLM_BOOK_UNDER_PRICED_AFTER_SESSIONS` sessions is `REFUSED_UNDER_PRICED`
#: rather than graded on a remnant.
LLM_BOOK_UNDER_PRICED_MIN_WEIGHT = 0.5
LLM_BOOK_UNDER_PRICED_AFTER_SESSIONS = 5
#: Series every grade PULLS (never assumes) before grading, from the earliest
#: book's entry: the competition benchmark proxy, the ten theme ETFs the
#: `sector_etf` twins hold that no local panel carries, and the factor ETFs the
#: bridge and the leads compare against. One that cannot be pulled is a named
#: refusal on the leaderboard (`series_refusals`).
LLM_BOOK_REQUIRED_SERIES = ("URTH", "BETZ", "BOTZ", "GRID", "IGV", "ITA", "LIT",
                            "QTUM", "URA", "XBI", "XLB", "SPY", "IWM", "SMH",
                            "MTUM")

#: Book factory: DeepSeek spend cap per RUN, read from the same telemetry
#: ledger `llm_analyzer` writes (purpose `book_factory`).
BOOK_FACTORY_CAP_USD = 1.0
BOOK_FACTORY_PURPOSE = "book_factory"
#: 8,000 (was 4,000): the 2026-09-25 smoke call hit 4,000 with 20 complete
#: positions and died inside `what_i_did_not_buy` (finish_reason=length).
BOOK_FACTORY_MAX_TOKENS = 8000
#: `what_i_did_not_buy` entries the prompt allows; that list ate 60% of the
#: truncated smoke answer.
BOOK_FACTORY_MAX_NOT_BOUGHT = 8
BOOK_FACTORY_NOTE_MAX_CHARS = 30_000
BOOK_FACTORY_MAX_CANDIDATES = 160
BOOK_FACTORY_NEWS_DAYS = 14
BOOK_FACTORY_REVISION_DAYS = 90
BOOK_FACTORY_LOCAL_LLM_URL = "http://127.0.0.1:8080"
BOOK_FACTORY_LOCAL_TIMEOUT_S = 600
#: Upper bound of one call, used to refuse a call that could cross the cap.
BOOK_FACTORY_EST_CALL_USD = 0.03

# ── Thesis cards (Builder O5, 2026-09-25) ───────────────────────────────────
#: One structured analysis per chosen stock: engine side + one OpenClaw web
#: quest + one DeepSeek synthesis. `backend/services/thesis_card.py`,
#: `scripts/thesis_cards.py`. Cards land in OPTIMUS_LEDGER_DIR/thesis_cards/<date>/.
THESIS_CARD_SUBDIR = "thesis_cards"
THESIS_CARD_MAX_QUESTS = 40
#: Per run-day cap, read from the SAME telemetry ledger the calls write
#: (`llm_telemetry.spend(purpose=...)` summed over both purposes below).
THESIS_CARD_CAP_USD = 5.0
THESIS_CARD_PARALLEL = 2
THESIS_CARD_MODEL = "deepseek/deepseek-flash"
THESIS_CARD_QUEST_TIMEOUT_S = 900
THESIS_CARD_QUEST_PURPOSE = "thesis_card_quest"
THESIS_CARD_SYNTH_PURPOSE = "thesis_card_synth"
#: Reserved per in-flight quest when checking the cap, so `--parallel` cannot
#: start N quests that together cross it. Measured 2026-09-25: VRT $0.056 / 158 s,
#: 000660.KS $0.063 / 314 s (OpenClaw), synthesis ~$0.0007 each.
THESIS_CARD_EST_QUEST_USD = 0.08
THESIS_CARD_NEWS_DAYS = 30
THESIS_CARD_REVISION_DAYS = 90

# ── LLM price calibration from the provider balance (2026-09-27) ────────────
#: `backend/services/llm_price_calibration.py`, `scripts/llm_price_calibrate.py`.
#: DeepSeek quotes the balance to the cent: every window delta is uncertain by
#: one step, so a calibration whose total delta is under the MIN reports
#: TOO_COARSE and is not adoptable.
DEEPSEEK_BALANCE_GRANULARITY_USD = 0.01
LLM_PRICE_CALIBRATION_MIN_DELTA_USD = 0.05
#: Seconds to wait after a run's last reply before the closing balance read.
DEEPSEEK_BALANCE_POSTING_LAG_S = 90
#: A run receipt's `provider_delta` line (balance delta vs ALL DeepSeek
#: telemetry over a bracketing snapshot pair) above this is a WARNING carrying
#: the calibration's age -- never a refusal: the balance is too coarse to refuse on.
LLM_PROVIDER_DISAGREE_WARN = 0.25
#: An answer whose SHAPE is unfinished (too few names, weights not summing to
#: 1) is re-asked this many times on the same cached prefix before freezing.
#: The 2026-09-25 smoke call returned one position of an 18-name strategy.
BOOK_FACTORY_MAX_REASKS = 1

# ── Strategy library + nightly backtest factory (chunk 3b, 2026-09-26) ──────
#: `backend/services/strategy_library.py` (rules) and
#: `scripts/night_backtest_factory.py` (the night unit). Output folder under
#: OPTIMUS_LEDGER_DIR. CPU only, no LLM, no broker.
STRATEGY_LIB_SUBDIR = "strategy_library"
#: First bar the panel reads; features need 252 sessions, so the first
#: decision month is ~a year later.
STRATEGY_LIB_START = "2016-01-01"
#: The "if Aegis had existed in 2020" line starts here (hindsight-labelled).
STRATEGY_LIB_SINCE = "2020-01-01"
#: Return credited to a held name whose bars stop before the exit session --
#: the same declared assumption as `portfolio_farm.Policy.delisting_return`.
STRATEGY_LIB_DELIST_RETURN = -0.30
#: A crash loses at most this many strategies of work.
STRATEGY_LIB_CHECKPOINT_EVERY = 10
#: The night's box, in awake minutes. Past it the factory checkpoints and
#: writes a PARTIAL leaderboard naming how many rules it reached.
STRATEGY_LIB_TIME_BOX_MIN = 90
#: Rows per leaderboard table, and how many DSR leaders get a forward book.
STRATEGY_LIB_TOP_N = 10
STRATEGY_LIB_FREEZE_TOP = 10


# ── LANE M: THE LEARNING LAYER (2026-09-26, adjudication row 9) ───────────────
#: The monthly ExpeL distillation (`learner.rule_distillation.distill_ledger`)
#: wrote 0 rules for a month because the local reader refused the connection and
#: nothing fell back. These are its knobs. A night that writes 0 rules writes a
#: `LEARN_DEGRADED` line naming the reason; these numbers decide which reason.
#: Hard ceiling on DeepSeek spend for the distillation per UTC day, read from
#: `llm_telemetry.spend(purpose=LEARN_PURPOSE)` -- the writer's own ledger.
LEARN_DAILY_CAP_USD = 0.50
#: Telemetry purpose every distillation call is recorded under.
LEARN_PURPOSE = "learn_distill"
#: A (group x observable x horizon) cell needs this many GRADED rows to become a
#: fact the model may write a rule about. Below it the cell is not shown.
LEARN_MIN_GROUP_N = 30
#: Facts per night, strongest evidence first (|held-out skill| x sqrt(n)).
LEARN_MAX_FACTS = 24
#: Facts per model call. DeepSeek via `llm_analyzer._call_llm` answers in at most
#: `llm.max_tokens` (500) tokens, so a call must fit its rules in that budget.
LEARN_FACTS_PER_CALL = 6
#: The local reader tried first (llama-server on 127.0.0.1:8080, 8k context).
LEARN_LOCAL_BACKEND = "local_gguf"
LEARN_LOCAL_TIMEOUT_S = 180
LEARN_LOCAL_MAX_TOKENS = 700
#: A percentage quoted in a rule must match a number of the fact it cites within
#: this many percentage points, or the rule is REFUSED (invented numbers).
LEARN_NUMBER_TOL_PP = 0.15


# ── CHUNK J: DOW JONES BUNDLE THROUGH MURAT'S OWN CHROME (2026-09-26) ─────────
#: Browser profiles Aegis may NAME (LANE O, 2026-09-28). ONE: `muratclaw`,
#: which OpenClaw now reaches ONLY by attaching to the dedicated Chrome at
#: `OPENCLAW_DEDICATED_USER_DATA_DIR` on 127.0.0.1:`OPENCLAW_DEDICATED_CDP_PORT`
#: (`openclaw.json`: `browser.profiles.muratclaw = {attachOnly: true, cdpUrl}`).
#: Murat, 2026-09-28: "configure to only murat claw like as if its controlling
#: my pc". Until 2026-09-28 this tuple also held `user` (his MAIN Chrome over
#: chrome-mcp) and `chrome` (the extension relay); twice a page opened in his
#: main account. A name outside this tuple refuses with
#: REFUSED_BROWSER_PROFILE_NOT_ALLOWED.
OPENCLAW_ALLOWED_PROFILES = ("muratclaw",)
#: The profile names that reach (or used to reach) Murat's MAIN Chrome. Named
#: so a request for one refuses BY NAME (REFUSED_MAIN_CHROME_PROFILE), from an
#: argument or from AEGIS_OPENCLAW_PROFILE. In `openclaw.json` both are
#: redefined as attachOnly on a closed loopback port, so OpenClaw itself cannot
#: attach them to anything either.
OPENCLAW_MAIN_CHROME_PROFILES = ("user", "chrome")
#: The operator contract (named tab, host allowlist before and after every
#: action, own-tab close, no typing) binds on the dedicated profile: it is a
#: SIGNED-IN browser (two Google accounts, Dow Jones, socials), so it is held to
#: the narrow contract, not the old managed-profile one.
OPENCLAW_OPERATOR_PROFILES = ("muratclaw",)
#: The profiles whose every action first PROVES the attached browser is the
#: dedicated one (`muratclaw_instance.prove`): the CDP endpoint answers on
#: loopback, Chrome's own `SystemInfo.getProcessInfo` names the browser PID,
#: that PID's command line carries the dedicated --user-data-dir and port, the
#: port's listener is that PID, and the tab acted on is listed by THAT endpoint.
OPENCLAW_DEDICATED_PROFILES = ("muratclaw",)
OPENCLAW_DEDICATED_CDP_HOST = "127.0.0.1"
OPENCLAW_DEDICATED_CDP_PORT = 18802
OPENCLAW_DEDICATED_USER_DATA_DIR = str(Path.home() / "ChromeMuratClaw")
OPENCLAW_CHROME_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
#: The dedicated Chrome's start page when the reader (re)launches it: blank.
#: A live news home page left open for the browser's life grows and can hang
#: (2026-09-29), and one hung tab fails every Playwright attach of the gateway.
OPENCLAW_CHROME_START_URL = "about:blank"
#: OpenClaw's own config (read for the instance check; never printed -- it
#: holds the gateway token) and the gateway's loopback address.
OPENCLAW_CONFIG_PATH = Path.home() / ".openclaw" / "openclaw.json"
OPENCLAW_GATEWAY_HOST = "127.0.0.1"
OPENCLAW_GATEWAY_PORT = 18789
#: How browser verbs reach the gateway (LANE O3): "cli" (a node process per
#: verb, ~7-12 s each measured 2026-09-28) or "http" (one keep-alive
#: `POST /tools/invoke`, ~0.4-2 s). Both run the SAME guards in
#: `openclaw_client`; `AEGIS_OPENCLAW_TRANSPORT` overrides. Default stays
#: "cli" until the owner flips it after reading the lane-O receipt.
OPENCLAW_BROWSER_TRANSPORT = "cli"
#: The transport for the DEDICATED profiles (2026-09-28): "http". The one
#: unexplained HTTP rc 1 of the lane-O build was reproduced and explained:
#: the gateway's Playwright `page.goto` waits for the "load" event with a 20 s
#: default and MarketWatch fires it after 50-60 s ("TimeoutError: page.goto:
#: Timeout 20000ms exceeded" in the gateway log; the HTTP reply only says "tool
#: execution failed"). HTTP `navigate`/`open` now send
#: `OPENCLAW_HTTP_NAVIGATE_TIMEOUT_MS`. Other profiles keep
#: `OPENCLAW_BROWSER_TRANSPORT`; `AEGIS_OPENCLAW_TRANSPORT` overrides both.
OPENCLAW_BROWSER_TRANSPORT_DEDICATED = "http"
#: `timeoutMs` sent with an HTTP navigate/open (the gateway clamps to 120 s).
OPENCLAW_HTTP_NAVIGATE_TIMEOUT_MS = 75000
#: A reader snapshot at least this long is treated as CUT (the CLI cuts at
#: ~40,000 chars, before the article links of a big stock page) and is re-read
#: interactive-only; the re-read is used when it carries more links.
WEB_READER_SNAPSHOT_CUT_CHARS = 38000
#: The OpenClaw agent id `POST /tools/invoke` is evaluated under (None -> the
#: gateway default, "main"). Set it to a dedicated agent entry if the owner
#: denies `browser` to the LLM agent `main` (LANE O4 proposal), so the guarded
#: HTTP transport keeps the browser while agent turns lose it.
OPENCLAW_HTTP_AGENT_ID = "aegis-browser"  # O4 applied 2026-09-28 (owner: "2-yes")
#: The Dow Jones hosts the dedicated browser may touch (Murat, 2026-09-26:
#: "wsj/barrons/marketwatch only").
OPENCLAW_USER_TAB_HOSTS = ("wsj.com", "barrons.com", "marketwatch.com")
#: Social hosts, READ-ONLY, added 2026-09-28. Murat: "dont read it too slow,
#: while its waiting make it read other pages then, reddit x and other socials
#: are logged in too". Absolute read-only on these (enforced in
#: `browser_policy`, both transports): no click at all, no typing, no post,
#: reply, like, repost, follow, vote, join or DM; a search is a NAVIGATION to a
#: search URL, never typing into a box. Rows read here carry
#: `source_kind = "social"`: never an alert's origin, never an order's.
#: X, Reddit and Dow Jones terms all restrict automated access; reading with a
#: signed-in account carries account risk on each, stated to Murat 2026-09-28.
OPENCLAW_SOCIAL_HOSTS = ("x.com", "reddit.com", "stocktwits.com")
#: Every host the dedicated browser may be on while it acts.
OPENCLAW_BROWSER_HOSTS = OPENCLAW_USER_TAB_HOSTS + OPENCLAW_SOCIAL_HOSTS
#: LANE O2: the night supervisor's dependency repair. At most this many
#: repairs (browser stop / gateway start / gateway restart) per rolling hour,
#: with exponential backoff between attempts from REPAIR_BACKOFF_S.
OPENCLAW_REPAIRS_PER_HOUR = 3
OPENCLAW_REPAIR_BACKOFF_S = 60.0
OPENCLAW_REPAIR_PORT_WAIT_S = 240.0
#: No gateway (re)start below this much free RAM: the kill test of 2026-09-28
#: 14:30 restarted it at 0.5-0.8 GB free and it did not bind its port for more
#: than 15 minutes (handoff 09-28: "would not open its port under 1 GB free").
OPENCLAW_REPAIR_MIN_FREE_GB = 1.5
#: LANE O5: after this many page reads a run prints and records links per page
#: and characters per page per lane; a lane at zero on EVERY page refuses.
READER_YIELD_CHECK_AFTER = 10
#: Human-pace throttle for `web_reader.read_article` (persisted across runs).
#: The gap between page loads is DRAWN from [MIN, MAX] (lognormal, clipped;
#: never the same interval twice) -- a constant interval is the machine tell.
#: 2026-09-27 22:5x HKT, Murat: "read it faster and read multiple pages dont just
#: wait, while waiting move to another page". His subscription, his call; the
#: account-flag risk under Dow Jones ToU 9.4.1 was stated to him and rises with
#: pace. Was 20-90 s, same host 60 s, 45/h, 300/day, 120/day/host. The gap is
#: still DRAWN (never constant) and the three sites are rotated, so a wait on
#: one host is spent loading a page on another.
WEB_READER_MIN_DELAY_S = 6.0
WEB_READER_MAX_DELAY_S = 20.0
WEB_READER_MIN_SAME_HOST_GAP_S = 18.0
#: CAPS RAISED 2026-09-28 22:30 HKT for the reader pool. Murat, 21:45: "can
#: openclaw read more, can it launch another chrome tabs to read too, this one
#: by one is very slow, it needs to read wsj, barron, marketwatch per stock and
#: the news from that too". Was 180/h, 1,500/day, 600/day per Dow Jones site.
#: Raised only to what the day's reading needs: per Dow Jones site ~130 stock
#: pages (MarketWatch twice: analyst + stock page) plus their news, ~120 section
#: fronts a day and the news they show -- about 1,000 pages a site in a ~10 h
#: night, so 120/h and 1,200/day per site (`READER_MAX_PER_HOUR_BY_HOST`); the
#: social hosts stay at 150/day each (one read per name a day fits) and 40/h.
#: Hourly total = 3 x 120 + 3 x 40. The gap stays DRAWN per host (never
#: constant); the account-risk statement to the owner stands.
WEB_READER_MAX_PER_HOUR = 480
WEB_READER_MAX_PER_DAY = 4000
#: Per-site daily cap (wsj / barrons / marketwatch each), inside the global one.
WEB_READER_MAX_PER_DAY_PER_HOST = 1200
#: Per-host daily caps that REPLACE the one above for these hosts (matched on
#: the host or a subdomain of it). The social hosts start at 150/day each
#: (orchestrator, 2026-09-28, on Murat's widening of the allowlist).
WEB_READER_MAX_PER_DAY_BY_HOST = {"x.com": 150, "reddit.com": 150, "stocktwits.com": 150}

# ── The reader pool: several tabs at once, paced PER HOST (2026-09-28) ──────
#: Murat, 2026-09-28 21:45 HKT: "can openclaw read more, can it launch another
#: chrome tabs to read too, this one by one is very slow, it needs to read wsj,
#: barron, marketwatch per stock and the news from that too, it should navigate
#: them, not just the stocks, and also the media too." Earlier the same day:
#: "it should always work and shouldnt be standing idle."
#: MEASURED on the live run of that evening (receipts plan_2026-09-28_123154_*):
#: per page, open ~2-7 s, settle+scroll+read ~10 s, and 46-73 s IDLE waiting for
#: the one shared throttle (a global drawn gap of 6-20 s serialised across all
#: three workers, the lock held through the sleep, plus a same-host floor of
#: 3x the draw, ~60 s). The bottleneck was the PACING, not the page load, so the
#: pool paces page OPENS per host (a drawn, jittered gap per host, reserved under
#: the lock and slept outside it) with a short drawn gap between any two opens.
#: More tabs are headroom for slow pages (a MarketWatch load, a CLI snapshot).
READER_POOL_ENABLED = True
READER_MAX_TABS = 6
READER_TABS_PER_HOST = {"wsj.com": 2, "barrons.com": 2, "marketwatch.com": 2,
                        "x.com": 1, "reddit.com": 1, "stocktwits.com": 1}
#: The memory governor: below READER_MIN_FREE_GB of free RAM no new tab is
#: opened (the count falls toward 1); one more tab is allowed only above
#: READER_GROW_FREE_GB (hysteresis, so the count does not flap).
READER_MIN_FREE_GB = 2.0
READER_GROW_FREE_GB = 2.6
#: 2026-09-29: the maximum ADAPTS -- the tabs held now plus as many more as fit
#: above the floor at READER_TAB_GB each (never above READER_MAX_TABS).
READER_TAB_GB = 0.5
#: A reader process alive with no page OK for READER_STALL_S is STALLED (a named
#: fault, not "reading"): the supervisor closes hung tabs, then restarts the
#: pool, then recycles the dedicated Chrome, one step per READER_STALL_STEP_S.
#: 2026-09-29 00:59-02:15 HKT the status said "reading" for 77 minutes of BLANK
#: pages behind one hung tab.
READER_STALL_S = 600.0
READER_STALL_STEP_S = 300.0
#: A page target that does not answer a one-line evaluate in this long is hung
#: (one hung renderer times out every Playwright attach of the gateway).
READER_HUNG_TAB_TIMEOUT_S = 4.0
#: A page of the dedicated Chrome not NAVIGATED for this long, and not the
#: pool's own, is closed by the supervisor (the pool's tabs live a minute or two;
#: a launcher's start page or another job's leftovers otherwise live for hours).
READER_STALE_TAB_S = 1800.0
#: Long-lived browsers grow: the dedicated Chrome is recycled gracefully (tabs
#: closed, Browser.close, relaunched with its port) when older than
#: READER_CHROME_RECYCLE_S, or holding more than READER_CHROME_MAX_GB (private
#: bytes), or more than READER_CHROME_SOFT_GB while free RAM is under
#: READER_CHROME_LOW_FREE_GB; at most READER_CHROME_RECYCLES_PER_HOUR an hour.
READER_CHROME_RECYCLE_S = 7200.0
READER_CHROME_MAX_GB = 8.0
READER_CHROME_SOFT_GB = 4.0
READER_CHROME_LOW_FREE_GB = 3.0
READER_CHROME_RECYCLES_PER_HOUR = 2
#: 2026-09-29: a recycle is decided BEFORE the pool is stopped. When it would be
#: refused (a tab the reader did not open is active, or the instance is not
#: proven), the pool keeps reading and the recycle is not asked again for
#: READER_CHROME_REFUSED_BACKOFF_S, doubling per consecutive refusal up to
#: READER_CHROME_REFUSED_BACKOFF_MAX_S. The refusal, the backoff and the hourly
#: recycle count persist in dowjones/chrome_recycle_state.json, so a restarted
#: supervisor does not ask again on its first check (it did, every ~15 min).
READER_CHROME_REFUSED_BACKOFF_S = 900.0
READER_CHROME_REFUSED_BACKOFF_MAX_S = 7200.0
#: 2026-09-29: the MEMORY_PRESSURE branch asks for a recycle only when the dedicated Chrome
#: holds at least this share of the memory in use (it is what squeezes the
#: machine; 2026-09-29 it held 4.6 of ~28.5 GB and was recycled for nothing).
READER_CHROME_PRESSURE_SHARE = 0.25
#: Drawn gap between two page OPENS on the same host, (lo, hi) seconds, a
#: right-skewed draw inside the range, never within 1 s of that host's previous
#: draw (never a constant interval).
READER_HOST_GAP_S = {"wsj.com": (10.0, 45.0), "barrons.com": (10.0, 45.0),
                     "marketwatch.com": (10.0, 45.0), "x.com": (25.0, 90.0),
                     "reddit.com": (25.0, 90.0), "stocktwits.com": (25.0, 90.0)}
#: Drawn gap between ANY two opens, whatever the host (no simultaneous burst).
READER_GLOBAL_GAP_S = (1.0, 4.0)
#: Hourly caps per host in the pool (inside WEB_READER_MAX_PER_HOUR).
READER_MAX_PER_HOUR_BY_HOST = {"wsj.com": 120, "barrons.com": 120, "marketwatch.com": 120,
                               "x.com": 40, "reddit.com": 40, "stocktwits.com": 40}
#: A host that showed a challenge, block, login wall or rate-limit page is not
#: opened again for this long (its lanes stop; the status file says why).
READER_HOST_COOL_S = 3600.0
#: Section fronts: the front page and markets every 30 min during US hours
#: (09:00-17:00 New York, weekdays), every other section every 2 h.
READER_FRONT_FAST_S = 1800.0
READER_FRONT_SLOW_S = 7200.0
#: Article links taken from one section front (newest / most prominent first).
READER_FRONT_LINKS_MAX = 12
#: Media (video / podcast) links taken from one section front.
READER_FRONT_MEDIA_LINKS_MAX = 3
#: "related / read next" links are followed to this depth, only from an article
#: that names a ticker in the universe, only on the same host.
READER_RELATED_DEPTH = 1
READER_RELATED_LINKS_MAX = 3
#: Freshness windows: a stock page or a social page is not re-read inside it; a
#: stored article url is never re-read.
READER_STOCK_FRESH_H = 20.0
READER_SOCIAL_FRESH_H = 12.0
#: Captions / transcript text files a player points to may be fetched from the
#: host it names (a CDN): text only, at most this many bytes.
READER_CAPTIONS_MAX_BYTES = 2_000_000
#: `dowjones_pull --archive` reads at most this many articles per archive day.
DOWJONES_ARCHIVE_MAX_PER_DAY = 80
#: `dowjones_pull --handoff` refuses unless this file exists. Murat creates it
#: when he steps away from the PC; nothing in the repo ever creates it.
DOWJONES_HANDOFF_FILE = OPTIMUS_LEDGER_DIR / "HANDOFF_PC"
#: Claim extraction (DeepSeek, `llm_analyzer._call_llm`) -- hard cap per run.
DOWJONES_CLAIMS_CAP_USD = 3.00
DOWJONES_CLAIMS_EST_USD_PER_ARTICLE = 0.004
DOWJONES_CLAIMS_PURPOSE = "dowjones_claims"
#: The operator's paste inbox (primary path from 2026-09-26: Murat copies the
#: text himself; nothing automated touches his subscription).
DIGEST_INBOX_DIR = OPTIMUS_LEDGER_DIR / "digest_inbox"
#: The dated-archive crawl (`dowjones_pull --archive`). OFF (Murat, 2026-09-26:
#: "the archive-by-date crawl stays OFF"); the paste inbox's reading list
#: carries the archive days as links for a human instead.
DOWJONES_ARCHIVE_ENABLED = True       # 2026-09-26 23:55 Murat's call (handoff-gated, human pace, ToU quoted on every run)
#: Lines shorter than 60 chars containing one of these are the signed-in
#: account's name in the page chrome and are stripped from stored text.
DOWJONES_ACCOUNT_NAME_PATTERNS = ("murat", "murathan", "abdullaev")

# ── Disk guard (2026-09-27, handoff §20: C: reached 0 bytes free) ───────────
#: `system_health.disk_free`: free space on the volume holding
#: OPTIMUS_LEDGER_DIR. ALIVE at or above STALE_GB, STALE below it, DEAD below
#: DEAD_GB. `disk_guard.require_free(DISK_FREE_DEAD_GB + 1, ...)` is the
#: start-up refusal of the night factory, the daily pass, the reader's queue
#: and the sim: a run that cannot finish its receipts must not start.
DISK_FREE_STALE_GB = 10
DISK_FREE_DEAD_GB = 2

# ── OpenClaw temp builds (2026-09-27: ~2,400 `openclaw-plugin-build-*` folders
# of ~70 MB each filled C:) -- `backend/services/openclaw_temp.py` ──────────
#: `sweep_plugin_builds`: only folders whose mtime is at least this old.
OPENCLAW_TEMP_SWEEP_MAX_AGE_MIN = 15
#: The client sweeps at most once per this many seconds.
OPENCLAW_TEMP_SWEEP_INTERVAL_S = 600
#: Wall-clock budget of one sweep; the rest is deferred to the next one.
OPENCLAW_TEMP_SWEEP_MAX_SECONDS = 30.0
#: A folder CREATED within this many seconds after a live OpenClaw node process
#: started may be that process's loaded plugin source; it is kept.
OPENCLAW_TEMP_PROTECT_WINDOW_S = 300
#: When the live-process scan fails, only folders older than this are deleted.
OPENCLAW_TEMP_UNSCANNED_MIN_AGE_H = 24
#: `system_health.openclaw_temp_builds` goes DEGRADED (verdict STALE) above either.
OPENCLAW_TEMP_DEGRADED_COUNT = 50
OPENCLAW_TEMP_DEGRADED_GB = 5.0
#: The probe's time box: counting always completes, sizing stops at this.
OPENCLAW_TEMP_PROBE_BUDGET_S = 1.5

# ── Process census (C14, 2026-10-07) ─────────────────────────────────────────
#: 2026-10-07: 590 python processes were alive -- one Optimus MCP server + one
#: `openclaw_api_bridge` per OpenClaw agent session (146 sessions, each a
#: venv shim + interpreter = 4 OS processes), 2.5 GB, never reaped, because
#: `release_session` ARCHIVED the session and archiving does not retire the
#: gateway's bundle-MCP runtime. Nothing counted them. `system_health`'s
#: `process_census` counts LOGICAL instances per command-line family (a venv
#: shim and its interpreter child count once): above the cap DEGRADED (verdict
#: STALE), above PROCESS_CENSUS_DEAD_MULT x cap DEAD. It never kills anything.
#: Family -> (case-insensitive regex on the command line, cap).
PROCESS_CENSUS_FAMILIES = {
    # one per Claude Code session + one per LIVE OpenClaw agent turn
    "optimus_mcp": (r"optimus[\\/]mcp[\\/]server\.py", 8),
    # only the OpenClaw gateway starts it: one per LIVE agent turn
    "api_bridge": (r"openclaw_api_bridge", 4),
    "sim_run": (r"scripts[.\\/]sim_run\b", 2),
    "reader": (r"scripts[.\\/](reader_pool|night_reader_supervisor|web_reader)\b", 3),
    "telegram": (r"scripts[.\\/]telegram_agent\b", 2),
}
PROCESS_CENSUS_DEAD_MULT = 2.0
#: the census reader's time box (one Win32_Process query)
PROCESS_CENSUS_TIMEOUT_S = 45
#: `openclaw_client.release_session` (C14): how a one-shot agent session is
#: released after its turn. "delete" retires the gateway's bundle-MCP runtime
#: (the stdio children) after snapshotting the session's tool calls for the
#: tool-scope audit; "archive" is the pre-C14 behaviour, which leaks them.
OPENCLAW_SESSION_RELEASE_MODE = "delete"

# ── Dow Jones reader: worker processes (2026-09-27) ──────────────────────────
#: `dowjones_pull --plan ... --workers N` splits the plan by SITE into N reader
#: processes (wsj / barrons / marketwatch), each with its own tab set and its
#: own `_reader_<site>.lock`. They share ONE throttle file (file-locked), so the
#: pacing above binds on the sum of their page loads. The gateway serialises
#: Chrome MCP operations per session and names a pageId on every call, so
#: concurrent CLI calls do not steal each other's tab. 1 = the old single
#: process. See docs/research_notes/2026-09-27/reader_throughput_2026-09-27.md.
DOWJONES_READER_WORKERS_DEFAULT = 3

# ── Alerts to Telegram, INFO level only (LANE A, 2026-09-28) ─────────────────
#: `backend/services/alerts.py` + `scripts/alert_pass.py`, run by the
#: `AegisAlerts` scheduled task. Template-rendered from fields already on disk;
#: NO LLM call anywhere on this path (spend reads $0.00 by construction).
#: SENDING: the owner's standing rule (2026-09-28) is "dont send any messages or
#: emails without asking me"; he then CONFIRMED Telegram alerts to his own phone
#: the same day ("telegram should work, send messages to my phone, short
#: notices"). Set False and every alert is still frozen to the ledger and closed
#: HELD_NOT_ENABLED, and the Telegram sender is never called.
#: 2026-09-28 review (docs/reviews/REVIEW_2026-09-28_LANE_A_ALERTS.md): held
#: while F1 (the message says what happened), F2 (the sent text is frozen) and
#: F3 (no "already moved" from a pre-filing close) were fixed; turned back on
#: after a dry run whose 8 rendered messages were read (lane_a_build note,
#: "AFTER REVIEW").
ALERTS_SEND_ENABLED = True
#: Hard caps, counted in the OWNER'S calendar day (Hong Kong), over alerts that
#: were sent OR would have been (DRY_RUN / HELD_NOT_ENABLED), so a held run
#: reports exactly what a live run would have delivered.
ALERT_DAILY_CAP = 8
ALERT_PER_TICKER_DAILY_CAP = 2
#: The owner's zone. The machine is UTC+8 too, but the code COMPUTES from UTC
#: with zoneinfo and never reads the machine's local clock (two-clocks trap).
ALERT_OWNER_TZ = "Asia/Hong_Kong"
#: Quiet hours, owner-local, [start, end). Alerts frozen inside are held and
#: delivered as ONE digest by the first pass at or after the end.
ALERT_QUIET_START_LOCAL = "00:30"
ALERT_QUIET_END_LOCAL = "07:30"
#: Dedup: five rewrites of one fact are one alert. Same (ticker, event type id,
#: normalised fact key) whose first publication is within this window of the
#: cluster's FIRST publication joins that cluster as a follow-up.
ALERT_DEDUP_WINDOW_H = 72
#: An event first seen longer ago than this is not alerted (it is history).
#: 72 h spans a weekend's Friday filings on a Monday morning.
ALERT_EVENT_MAX_AGE_H = 72
#: A price older than this many XNYS sessions before the alert makes the alert
#: UNPRICED by name, never a blank.
ALERT_PRICE_MAX_STALE_SESSIONS = 2
#: Trailing window for the stock's own daily sigma (log returns).
ALERT_SIGMA_LOOKBACK_SESSIONS = 63
#: |move| at or above this many sigma is flagged "already moved".
ALERT_ALREADY_MOVED_SIGMA = 2.0
#: The gate for any level above INFO, and the date count at which the kill rule
#: is read: >= this many distinct alert dates GRADED at the primary horizon.
ALERT_MIN_GRADED_DATES = 100
ALERT_GRADE_HORIZONS = (1, 5, 21)
ALERT_KILL_HORIZON = 5
#: A failed send is retried by later passes up to this many attempts, then GAVE_UP.
ALERT_MAX_SEND_ATTEMPTS = 3
#: Form 4 insider cluster: >= this many DISTINCT insiders with open-market
#: purchases (code P) whose filings became public within the lookback.
ALERT_INSIDER_CLUSTER_MIN_BUYERS = 2
ALERT_INSIDER_CLUSTER_LOOKBACK_DAYS = 30
#: Discovery-lane headlines may CONFIRM an alert inside this window around the
#: event, never originate one.
ALERT_CONFIRM_WINDOW_BEFORE_H = 24
ALERT_CONFIRM_WINDOW_AFTER_H = 72
#: (review 2026-09-28 F3) An alert whose event became PUBLIC (SEC acceptance
#: time; first-seen when there is none) longer ago than this at delivery time is
#: NOT sent: it is closed TOO_OLD and counted. Measured on acceptance, not on
#: when a collector first saw it, so a collector catching up after an outage
#: cannot make old filings look fresh. 72 h lets a Friday after-close filing
#: reach the owner before Monday's open (about 51-66 h later).
ALERT_SEND_MAX_AGE_H = 72
#: (review F4) The daily cap goes to the most important alerts, not the oldest.
#: Declared order of fact keys, most important first; unlisted keys rank after
#: every listed one. Ties: newer event first, then the larger |pre-alert move|
#: in sigma when known (unknown last), then the alert id. Deterministic.
ALERT_EVENT_TYPE_PRIORITY: tuple = (
    "8k_item:1.03",   # bankruptcy / receivership
    "8k_item:4.02",   # non-reliance on past financial statements
    "8k_item:2.04",   # an obligation accelerated
    "8k_item:3.01",   # delisting notice
    "8k_item:4.01",   # auditor change
    "8k_item:1.05",   # cybersecurity incident
    "8k_item:1.02",   # a material agreement ended
    "form4_purchase_cluster",
    "8k_item:5.02",   # officer / director change
    "8k_item:2.02",   # earnings
    "8k_item:2.01",   # acquisition / disposal completed
    "8k_item:3.02",   # unregistered share sale
    "8k_item:1.01",   # a material agreement entered
    "8k_item:2.03",   # debt taken on
    "8k_item:7.01",   # Reg FD (catch-all)
    "8k_item:8.01",   # other events (catch-all)
)
#: (review F4) Capped or held alerts from the last this-many hours are named in
#: ONE line at the next allowed send, so nothing silently vanishes.
ALERT_UNSENT_SUMMARY_LOOKBACK_H = 72
#: (review F4/F9) The 8-K Atom source is STALE when no new row arrived for more
#: than this many EDGAR filing hours (06:00-22:00 ET on session days).
ALERT_8K_SOURCE_STALE_FILING_HOURS = 4
#: (review F9) `system_health` probe `alert_receipts`: the newest pass receipt
#: older than this many minutes is STALE (the task runs every 30).
ALERT_RECEIPT_STALE_MIN = 75

# ── ISSUER-LEVEL IDENTITY (lane P, 2026-09-28; derived after review F4) ───────
#: One issuer, several listed share classes. `investment_committee.shortlist`
#: keeps ONE line per issuer (the larger 60-session median dollar volume the
#: funnel measured from its bars; score order when a line lacks it) and names
#: every dropped line on the row and on the u_plan receipt. Without it GOOGL
#: and GOOG entered the 2026-09-25 PROBE book as two names at 2% each: one
#: company at 4%, twice PROBE_MAX_WEIGHT.
#: Issuer identity is DERIVED from SEC CIK (`investment_committee.issuer_map`,
#: over edgar_8k/company_tickers.json): the first hand list held 14 of the 22
#: multi-class issuers in the 2026-09-24 funnel universe. THIS MAP IS ONLY AN
#: OVERRIDE for lines SEC's current-registrant file lacks (checked 2026-09-28:
#: CWEN-A and CUK; the other 26 hand pairs were confirmed by CIK and removed).
#: Changes no cap, stop or sizing value.
ISSUER_SHARE_CLASSES: dict = {
    "Clearway Energy": ("CWEN", "CWEN-A"),            # CWEN-A absent from SEC's file
    "Carnival": ("CCL", "CUK"),                       # plc ADR line; CUK absent from SEC's file
}


# -- lane M3 (2026-09-28): the backtest leaderboard's shelf life -----------------
#: `backtest_staleness.p_backtest_leaderboard`: the newest
#: strategy_library/leaderboard_<run id>.json older than this many days is STALE.
#: A week: the panel is monthly, but library code and inputs move daily, and the
#: factory has no scheduled caller (the board is as fresh as the last manual run).
BACKTEST_LEADERBOARD_STALE_DAYS = 7


# -- lane M5 (2026-09-28): a paper account's last mark older than this many
#: calendar days is STALE (`scripts/paper_accounts_roi.mark_status`). Four days
#: covers a Friday mark read on the following Monday night.
PAPER_ACCOUNT_MARK_STALE_DAYS = 4

# ── book_dna (chunk C3, 2026-10-06): "N ahead of SPY" is never printed alone ──
#: `backend/services/book_dna.py`, called by `scripts/paper_accounts_roi.py`
#: (the daily pass's `paper_accounts` step). Every threshold that decides how
#: many independent bets "N ahead" really is lives here, so a reader can see it.
#: Two books are LINKED (single linkage) when their ticker sets have Jaccard >=
#: this. 0.30 = "largely the same book"; the receipt also prints the cluster
#: count at every value of BOOK_DNA_JACCARD_SENSITIVITY so the choice is visible.
BOOK_DNA_JACCARD_THRESHOLD = 0.30
BOOK_DNA_JACCARD_SENSITIVITY: tuple = (0.15, 0.30, 0.50)
#: ...or when their period-return series correlate >= this over at least
#: BOOK_DNA_MIN_CORR_OBS common periods (identical series always link).
BOOK_DNA_CORR_THRESHOLD = 0.80
BOOK_DNA_MIN_CORR_OBS = 15
#: A beta vs SPY is fitted only on >= this many period returns; below it the
#: field says NOT_COMPUTABLE (no slope on 6 points).
BOOK_DNA_MIN_BETA_OBS = 20
#: EARLY_EVIDENCE needs >= this many sessions AND excess > 0 in >= 2 of 3
#: contiguous sub-windows. REPLICATED additionally needs a frozen replication
#: (same rule, another book) or a positive excess over a FAIR twin (below).
#: This module never labels anything above REPLICATED.
BOOK_DNA_EARLY_MIN_SESSIONS = 21
BOOK_DNA_FAIR_TWIN_KINDS: tuple = ("matched_twin21", "matched_random", "random_same_band")
#: TAIL check: `one_name_dependence` when the top holding carries more than this
#: share of the book's excess (or of its open P&L, for broker accounts).
BOOK_DNA_ONE_NAME_SHARE = 0.50
#: Loser error_type rules (in order): control_artifact (a twin) -> unmanaged (no
#: manager run in BOOK_DNA_UNMANAGED_SESSIONS sessions) -> sizing_concentration
#: (top-1 > BOOK_DNA_LOSER_SIZING_SHARE of the loss) -> timing_exit (the worst
#: contiguous third carries >= BOOK_DNA_TIMING_SHARE of the loss) -> selection.
BOOK_DNA_N_LOSERS = 10
BOOK_DNA_UNMANAGED_SESSIONS = 5
BOOK_DNA_LOSER_SIZING_SHARE = 0.40
BOOK_DNA_TIMING_SHARE = 0.70
#: When the P&L share is NOT computable (lanes: lots reopen at each rebalance),
#: a loser whose top holding is >= this fraction of the book NOW is still
#: sizing_concentration -- and its `why` says "by WEIGHT, not by P&L share".
BOOK_DNA_LOSER_WEIGHT_FALLBACK = 0.20
#: Review 2026-10-06 (docs/reviews/REVIEW_2026-10-06_C3_BOOK_DNA.md):
#: F3 -- a P&L rule (sizing / selection) may fire only when the P&L the module
#: can see explains >= this share of the shortfall; else `not_determinable`.
BOOK_DNA_LOSS_COVERAGE_MIN = 0.80
#: F6 -- `one_name_dependence` only on the excess basis, |excess| >= this, and a
#: reconstruction within BOOK_DNA_ONE_NAME_MAX_RECON_GAP_PP of the receipt.
BOOK_DNA_ONE_NAME_MIN_EXCESS_PP = 1.0
BOOK_DNA_ONE_NAME_MAX_RECON_GAP_PP = 0.25
#: F1 -- ex-ante effective bets: frozen weights priced over this many sessions
#: before the earliest inception (participation ratio, raw and SPY-residual).
BOOK_DNA_EXANTE_SESSIONS = 150
#: Website lanes whose daily returns correlate >= this form one risk-dial family;
#: lanes whose holdings have Jaccard >= BOOK_DNA_LANE_IDENTITY_JACCARD are
#: printed as one book with different treatment (mirror / conviction).
BOOK_DNA_LANE_FAMILY_CORR = 0.85
BOOK_DNA_LANE_IDENTITY_JACCARD = 0.90
#: How many tickers name a cluster's shared basket on the collapse line.
BOOK_DNA_BASKET_TOP = 5

# ── Telegram replies (LANE A phase 2, 2026-09-28) ────────────────────────────
#: `backend/services/alerts_replies.py`, called by the existing poller in
#: `scripts/telegram_agent.py`. Every reply READS FILES: no LLM, no browser, no
#: backtest, no order, no shell, no user-supplied path.
#: An inbound message longer than this is truncated, and the reply says so.
TELEGRAM_REPLY_MAX_INBOUND_CHARS = 4000
#: At most this many replies in any rolling 60 s; beyond it the message is
#: logged and not answered.
TELEGRAM_REPLY_MAX_PER_MIN = 10
#: `news <TICKER>` looks back this many days of the discovery corpus.
TELEGRAM_NEWS_LOOKBACK_DAYS = 14
TELEGRAM_NEWS_MAX_ITEMS = 8
#: (review 2026-09-28 F7) Rows ANY chat may add to `telegram/inbox.jsonl` per
#: rolling hour. Beyond it the message writes no row (and a stranger's gets no
#: reply anyway); the drops are counted and one summary row per hour records
#: them, so a stranger who knows the bot's name cannot fill the disk.
TELEGRAM_INBOUND_MAX_ROWS_PER_H_STRANGERS = 20
TELEGRAM_INBOUND_MAX_ROWS_PER_H_OWNER = 120
#: (review F7) `/ask`, `/deep`, `/research`: at most this many per owner-local
#: day, on top of TELEGRAM_REPLY_MAX_PER_MIN and the lab_budget spend cap.
#: `/deep` and `/research` spend money and wait for the owner's `/approve` tap;
#: a tap older than TELEGRAM_APPROVAL_MAX_AGE_MIN runs nothing.
TELEGRAM_MODEL_CMDS_MAX_PER_DAY = 20
TELEGRAM_APPROVAL_MAX_AGE_MIN = 60
#: (review F7) A `digest <text>` paste is stored WITH its line breaks, in full up
#: to this many characters (Telegram's own message limit is 4,096); the reply
#: states how much was stored. Longer articles: paste into DIGEST.md.
TELEGRAM_DIGEST_MAX_CHARS = 4096

# ── Telegram cockpit (C6, 2026-10-06, `backend/services/telegram_cockpit.py`) ──
#: Plain-text questions are mapped to the EXISTING receipt handlers by a fixed
#: keyword table. Only when nothing matches does ONE DeepSeek classification
#: call run (purpose `telegram_router`, reply validated against the intent
#: enum); at most this many per UTC day, counted in `telegram/router_llm.jsonl`.
TELEGRAM_ROUTER_LLM_MAX_PER_DAY = 20
#: A plain-text message longer than this never reaches the classifier (a paste
#: is not a question); it gets the deterministic help reply.
TELEGRAM_ROUTER_LLM_MAX_CHARS = 300
#: The per-chat conversational context ("and vs spy?") lives this long.
TELEGRAM_CONTEXT_TTL_MIN = 30
#: Inline-button ids older than this resolve to nothing (a stale tap is refused).
TELEGRAM_CALLBACK_TTL_H = 48
#: (review C6 F3) Every cockpit answer prints its receipt's age, read from the
#: receipt's OWN stamp, and says STALE past this many hours for its kind. The
#: ROI and snapshot receipts are written about daily; health a few times a day;
#: the reader rewrites its status every few minutes, so an hour-old status
#: means the reader is not reading; bars span a weekend. An unreadable stamp
#: is never fresh.
TELEGRAM_RECEIPT_STALE_H: dict = {
    "roi": 26.0, "snapshot": 26.0, "health": 12.0, "reader": 1.0, "digest": 26.0,
    "bars": 96.0, "default": 26.0,
}

# ── Stitched tickers (review 2026-09-29 F4, `backend/services/stitched_tickers.py`) ──
#: A symbol whose bars stop for MORE than this many market sessions and then
#: resume is a CANDIDATE stitch (two companies under one reused ticker). The gap
#: alone never decides: the registrant (SEC CIK), the source file and the price
#: level do (see the module docstring).
STITCH_GAP_SESSIONS = 20
#: A price level change across the gap by at least this factor (either way) is
#: evidence of a different security when no registrant evidence exists.
STITCH_PRICE_JUMP_RATIO = 3.0
#: A current CIK whose band's first filings on disk come this many days after
#: the old segment ended is evidence of a registrant created after it.
STITCH_CIK_BAND_MARGIN_DAYS = 180

# ── Bar defects (2026-09-29, `backend/services/bar_defects.py`) ──────────────
#: Runs inside `stitched_tickers.split_stitched`, so every bar reader gets it.
#: LINE was Linn Energy at $0.1641 as a ZERO-VOLUME bar every session from
#: 2016-05-24 to 2024-07-24 and Lineage at $73.66 the next day: no gap for the
#: stitch detector to see. Calibrated against CRSP daily 2016-2024 (docstring).
BAR_DEFECT_SCREEN = True
#: zero-volume rows in a run at least this long are removed (not trades)
BAR_DEFECT_DARK_RUN_MIN = 5
#: a single zero-volume row that moves the close more than this is removed
BAR_DEFECT_NONTRADE_PRINT_TOL = 0.01
#: a >= 4x one-day move that comes back to within 25% of it in 3 sessions is a bad print
BAR_DEFECT_SPIKE_RATIO = 4.0
BAR_DEFECT_SPIKE_RESIDUAL = 0.25
BAR_DEFECT_SPIKE_WINDOW = 3
#: a >= 3x level change on volume < 2x the trailing median, or across a missing
#: session, is a break: the symbol is cut there (no real >=3x CRSP move traded < 2.2x)
BAR_DEFECT_BREAK_RATIO = 3.0
BAR_DEFECT_QUIET_VOL_MULT = 2.0
#: kept, named SUSPECT: a >= 3x move on 2-10x volume (the spin-off defects and the
#: first real moves overlap there); a book leaning on them is refused
BAR_DEFECT_SUSPECT_VOL_MULT = 10.0
#: descriptive "implausible row" thresholds (printed, not a refusal), and the
#: share of a book's slots that may sit on a SUSPECT before the book is REFUSED
BAR_DEFECT_IMPLAUSIBLE_VOL = 3.0
BAR_DEFECT_IMPLAUSIBLE_MOM = 20.0
BAR_DEFECT_BOOK_MAX_SHARE = 0.02

# ── WORLD DIGEST (2026-09-29, `backend/services/world_digest.py`) ────────────
#: The owner, 2026-09-29: "digest the news see what they are implying is there
#: another path they are leading ... browse the news like a human to get the
#: context". PRODUCT_EXPERIMENT. Every implication is a typed, dated forecast row
#: under `news_digest:` that enters with a weight near ZERO: direction by any
#: LLM tested here is at or below 50% (docs/WHAT_WE_ALREADY_KNOW_LLM.md), so the
#: graded probability is shrunk to 0.5 and the model's own number is kept in
#: `raw_probability`. Nothing here reaches `expected_return` or `pc_broker`.
WORLD_DIGEST_HOURS = 36
#: Hard dollar cap per run, priced per call by `llm_analyzer.call_named` (the
#: served model's price); the provider's balance is printed beside it.
WORLD_DIGEST_BUDGET_USD = 0.90
#: Share of the budget the per-item extraction may use; the rest is reserved
#: for the synthesis so a large night cannot starve the digest itself.
WORLD_DIGEST_EXTRACT_SHARE = 0.70
WORLD_DIGEST_EXTRACT_MAX_CHARS = 3500
WORLD_DIGEST_HEADLINES_PER_CALL = 20
WORLD_DIGEST_MAX_SOCIAL_PAGES = 60
WORLD_DIGEST_MAX_THEMES = 10
WORLD_DIGEST_MAX_IMPLICATIONS_PER_THEME = 8
WORLD_DIGEST_WORKERS = 8
WORLD_DIGEST_PROMPT_VERSION = "wd_v1"
#: Forecast horizons (sessions) an implication may carry; the model's horizon is
#: snapped to the nearest. All are members of `belief_state.HORIZONS`.
WORLD_DIGEST_HORIZONS = (1, 5, 20)
#: Size bucket -> P(|return over h| > 1 trailing sigma_h), FROZEN. `normal` is
#: the Gaussian value (0.3173): a model that always says "normal" IS the vol
#: prior. sigma_h = 63-session daily sd x sqrt(h), measured before the write.
WORLD_DIGEST_SIZE_BUCKET_P = {"below_normal": 0.18, "normal": 0.3173,
                              "above_normal": 0.50, "extreme": 0.70}
#: Sector and macro subjects -> ONE liquid US-listed proxy and the sign that
#: turns the subject's direction into the proxy's (2026-09-29). "rates up" means
#: yields up, so TLT DOWN (-1). A subject not in this table stays ungraded
#: (`NOT_A_TICKER_NO_PROXY_IN_PANEL`): tariffs, fiscal, labor_market, volatility
#: and sector `other` have no single proxy whose sign is unambiguous. The proxy's
#: bars come from `prices_2025_26/bars_forecast_only.parquet` (FORECAST_PROXY_ETFS).
WORLD_DIGEST_SUBJECT_PROXIES = {
    "sector:semiconductors": ("SMH", 1), "sector:software": ("IGV", 1),
    "sector:internet": ("FDN", 1), "sector:hardware": ("XLK", 1),
    "sector:telecom": ("XLC", 1), "sector:media": ("XLC", 1),
    "sector:autos": ("XLY", 1), "sector:retail": ("XRT", 1),
    "sector:consumer_staples": ("XLP", 1), "sector:restaurants_travel": ("JETS", 1),
    "sector:banks": ("KBE", 1), "sector:insurance": ("KIE", 1),
    "sector:asset_managers": ("XLF", 1), "sector:fintech": ("XLF", 1),
    "sector:biotech_pharma": ("XBI", 1), "sector:medtech_health": ("XLV", 1),
    "sector:energy_oil_gas": ("XLE", 1), "sector:utilities_power": ("XLU", 1),
    "sector:industrials": ("XLI", 1), "sector:aerospace_defense": ("ITA", 1),
    "sector:materials_mining": ("XLB", 1), "sector:chemicals": ("XLB", 1),
    "sector:real_estate": ("XLRE", 1), "sector:transport_logistics": ("IYT", 1),
    "sector:crypto": ("IBIT", 1),
    "macro:rates": ("TLT", -1), "macro:inflation": ("TLT", -1),
    "macro:dollar": ("UUP", 1), "macro:oil": ("USO", 1), "macro:gold": ("GLD", 1),
    "macro:growth": ("IWM", 1), "macro:credit": ("HYG", 1), "macro:housing": ("XHB", 1),
    "macro:china": ("FXI", 1), "macro:japan": ("EWJ", 1), "macro:korea_taiwan": ("EWY", 1),
    "macro:europe": ("VGK", 1), "macro:emerging": ("EEM", 1),
    # free-text subjects the model writes outside the enum (counted on the
    # 2026-09-29 digest: 18 of 29 non-ticker subjects were such words)
    "sector:utilities": ("XLU", 1), "sector:defense": ("ITA", 1),
    "sector:regional_banks": ("KRE", 1), "sector:homebuilders": ("XHB", 1),
    "sector:airlines": ("JETS", 1), "sector:biotech": ("XBI", 1), "sector:pharma": ("XLV", 1),
    "sector:healthcare": ("XLV", 1), "sector:energy": ("XLE", 1), "sector:oil_gas": ("XLE", 1),
    "sector:financials": ("XLF", 1), "sector:technology": ("XLK", 1), "sector:tech": ("XLK", 1),
    "sector:semis": ("SMH", 1), "sector:chips": ("SMH", 1), "sector:hyperscalers": ("QQQ", 1),
    "sector:consumer_discretionary": ("XLY", 1), "sector:reits": ("XLRE", 1),
    "sector:retailers": ("XRT", 1), "sector:transports": ("IYT", 1), "sector:insurers": ("KIE", 1),
    "sector:materials": ("XLB", 1), "sector:mining": ("XLB", 1), "sector:staples": ("XLP", 1),
    "sector:communication_services": ("XLC", 1), "sector:small_caps": ("IWM", 1),
    "macro:emerging_markets": ("EEM", 1), "macro:usd": ("UUP", 1), "macro:us_dollar": ("UUP", 1),
    "macro:us_rates": ("TLT", -1), "macro:yields": ("TLT", -1), "macro:treasury_yields": ("TLT", -1),
    "macro:bonds": ("TLT", 1), "macro:treasuries": ("TLT", 1), "macro:crude": ("USO", 1),
    "macro:crude_oil": ("USO", 1), "macro:silver": ("SLV", 1), "macro:high_yield": ("HYG", 1),
    "macro:credit_spreads": ("HYG", -1), "macro:india": ("INDA", 1), "macro:brazil": ("EWZ", 1),
    "macro:germany": ("EWG", 1), "macro:uk": ("EWU", 1), "macro:canada": ("EWC", 1),
    "macro:korea": ("EWY", 1), "macro:taiwan": ("EWT", 1),
}
#: The fixed list of liquid proxies the grader's supplementary panel carries
#: (`scripts/pull_forecast_bars`, refreshed nightly by `scripts/pull_bars_refresh`):
#: every WORLD_DIGEST_SUBJECT_PROXIES target plus the sector SPDRs, rates/credit,
#: metals, dollar, and the main country ETFs. Names already in the main panel
#: (SPY, QQQ, IWM) are skipped by the puller.
FORECAST_PROXY_ETFS = tuple(sorted({v[0] for v in WORLD_DIGEST_SUBJECT_PROXIES.values()} | {
    "XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY",
    "IWM", "QQQ", "TLT", "IEF", "HYG", "LQD", "GLD", "SLV", "USO", "UUP",
    "KRE", "SMH", "XBI", "ITA", "JETS",
    "EWJ", "EWY", "EWT", "FXI", "VGK", "EEM", "EWZ", "INDA", "EWG", "EWU", "EWC"}))
#: Graded direction probability = 0.5 + SHRINK x (raw - 0.5); raw = 0.5 +/-
#: 0.25 x confidence. 0.2 keeps every graded direction row inside [0.45, 0.55].
WORLD_DIGEST_DIR_SHRINK = 0.2
#: Shadow trust: prior N(0, TAU^2) on the per-date Brier improvement over the
#: control (vol prior for size, 0.25 coin for direction). Trust =
#: clip(posterior mean / FULL, 0, MAX). No graded dates -> trust exactly 0.
WORLD_DIGEST_TRUST_TAU = 0.01
WORLD_DIGEST_TRUST_FULL = 0.02
WORLD_DIGEST_TRUST_MAX = 0.25
WORLD_DIGEST_TRUST_MIN_DATES = 3
#: The frozen shadow book the news tilt is applied to (SHADOW_BAYES_v0). It is
#: READ, never mutated; the tilted book is a separate shadow contract whose
#: matched twin is this base with trust pinned at 0.
WORLD_DIGEST_SHADOW_BASE_BOOK = "439fd84f869744e0"
WORLD_DIGEST_SHADOW_NEW_NAME_UNIT = 0.05
WORLD_DIGEST_EVERY_H = 6
FORECAST_WRITERS["news_digest"] = {"prefix": "news_digest:", "scheduled": None,
                                  "task": "AegisWorldDigest (every 6 h; reported only)"}

# ── WORLD STATE + REGIME ROWS + SCENARIOS (C17, 2026-10-07, `backend/services/world_state.py`) ──
#: Spec: docs/research_notes/2026-10-07/world_state_and_regime_rows_2026-10-07.md.
#: The belief table is UPDATED IN CODE from the digest's typed rows and
#: implications ($0, no new question to the model); the regime row is one
#: DeepSeek call per cycle, written once per session. PRODUCT_EXPERIMENT.
#: Half-life (days) of each belief's confidence: confidence x 0.5 ** (hours / (hl x 24)).
WORLD_STATE_HALF_LIFE_DAYS = {
    "ai_demand": 21, "semiconductor_capex": 21, "grid_power_demand": 21,
    "commodity_shortages": 10, "rates": 7, "inflation": 14, "credit": 10, "dollar": 10,
    "liquidity": 7, "consumer_conditions": 14, "china_policy": 10, "geopolitical_risk": 5,
    "defense_procurement": 21, "energy_security": 10, "biotech_regulatory": 14,
    "prediction_market_state": 5}
#: Weight of this cycle's evidence against the decayed prior (signed confidence).
WORLD_STATE_NEW_EVIDENCE_WEIGHT = 0.5
#: |signed score| a cycle needs before it calls a direction (below: mixed/none).
WORLD_STATE_DIRECTION_THRESHOLD = 0.10
#: Independent news sources at which a cycle's evidence counts at full strength.
WORLD_STATE_FULL_SOURCES = 5
#: Ceiling on any belief's confidence: a news-derived belief is never certain.
WORLD_STATE_MAX_CONFIDENCE = 0.90
#: A decayed belief below this confidence leaves the table (listed as expired).
WORLD_STATE_EXPIRE_CONFIDENCE = 0.02
#: Regime row (one DeepSeek call per cycle, once per session): horizons and the
#: stage cap. The graded probability is shrunk toward the 252-session base rate
#: by WORLD_DIGEST_DIR_SHRINK; the model's own number is `raw_probability`.
WORLD_STATE_REGIME_HORIZONS = (1, 5)
WORLD_STATE_REGIME_STAGE_CAP_USD = 0.05
#: regime_v1 (review 2026-10-07 F1): a FIXED event per variable, the model is shown
#: the base rate and persistence and asked for P(event) directly; sectors are 13
#: P(beats SPY) numbers. v0 graded a label's event that contradicted the label on
#: 5 of 14 rows: its rows stay in the ledger and are EXCLUDED from every grade by
#: this rule (labelled at read time; ledger rows are never rewritten).
WORLD_STATE_REGIME_PROMPT_VERSION = "regime_v1"
WORLD_STATE_REGIME_EXCLUDED_VERSIONS = {"regime_v0": "v0_incoherent"}
#: F7: the price panel must hold the last CLOSED XNYS session before the write
#: (lag-1 persistence, the just-closed session shown to the model); more lag -> REFUSED.
WORLD_STATE_REGIME_MAX_PANEL_LAG_SESSIONS = 0
#: F5: the declared effect a regime field must show, and the per-date sd assumed
#: before two dates exist (the review's simulation, 0.0335). N_needed =
#: ceil((2.8 x sd / delta)^2) independent entry sessions.
WORLD_STATE_REGIME_DELTA_BRIER = 0.005
WORLD_STATE_REGIME_SD_PRIOR = 0.0335
#: F3: the belief table is a Beta posterior on vote signs over ROOT EVENTS
#: (syndicated copies of one story = one vote), updated only by root events not
#: yet applied, decayed by elapsed time at each topic's half-life. A topic needs
#: this pseudo-count before its confidence is large: conf = |2m-1| x n/(n+PRIOR).
WORLD_STATE_BETA_PRIOR = 3.0
#: Root events already applied are remembered this long (a digest window is 24-36 h).
WORLD_STATE_APPLIED_MEMORY_DAYS = 7
#: belief_stability = share of beliefs whose direction changed since the last
#: cycle; above this the receipt says DEGRADED.
WORLD_STATE_STABILITY_MAX = 0.25
#: Baselines need this many h-session windows in the trailing 252 sessions, or
#: they are null with a reason (never a fabricated 0.5).
WORLD_STATE_REGIME_MIN_WINDOWS = 60
#: Scenario update: p = sigmoid(logit(prior) + K x sum(weight x signed belief)),
#: the shift capped at MAX_LOGIT_SHIFT. Computed from the CURRENT table, so it
#: is idempotent and cannot ratchet.
WORLD_STATE_SCENARIO_K = 0.6
WORLD_STATE_SCENARIO_MAX_LOGIT_SHIFT = 0.5
#: F8: scenarios read a SLOW average of the belief table, not the table itself:
#: smoothed += (1 - 0.5 ** (days / TIME_CONSTANT)) x (belief - smoothed), and the
#: probability moves at most MAX_DAILY_MOVE x elapsed days per update. Two
#: digests 45 minutes apart move a 2027 scenario by < 0.001.
WORLD_STATE_SCENARIO_TIME_CONSTANT_DAYS = 30
WORLD_STATE_SCENARIO_MAX_DAILY_MOVE = 0.01
#: F8: the declared priors, each with version, author and date. A changed value
#: is a RESTATEMENT (logged PRIOR_RESTATED), never a belief-driven move.
WORLD_STATE_SCENARIO_PRIORS = {
    sid: {"prior": p, "version": 1, "declared_by": "C17 builder (Opus), not the owner",
          "declared_at": "2026-10-07"}
    for sid, p in (("ai_capex_supercycle_2027", 0.40), ("ai_capex_digestion_2027", 0.25),
                   ("higher_for_longer_2027", 0.30), ("us_recession_2027", 0.25),
                   ("taiwan_strait_crisis_2027", 0.08), ("energy_supply_shock_2027", 0.15),
                   ("grid_electrification_2030", 0.50), ("biotech_regulatory_tailwind_2030", 0.35))}
#: A prediction-market match prices a scenario only from a snapshot this fresh.
WORLD_STATE_SCENARIO_MARKET_MAX_AGE_DAYS = 7
#: THE DORMANT NEWS WIRE (C17 B3). When True, `u_plan` applies
#: `world_digest.shadow_decision`'s tilt to its post-gate weights. Default OFF,
#: and a provable no-op while both trusts are 0 (`world_state.plan_news_tilt`
#: short-circuits; the receipt prints "news tilt: trust t, applied=False").
#: Flipping it is an OWNER decision, never a builder's.
NEWS_TILT_IN_PLAN = False
#: How trust may grow -- by rule only, never by edit. Both keys must hold before
#: the owner may set NEWS_TILT_IN_PLAN = True.
NEWS_TILT_TRUST_RULE = (
    "trust = world_digest.trust_from(): exactly 0 while graded news_digest dates < "
    "WORLD_DIGEST_TRUST_MIN_DATES (3); after that clip(posterior / WORLD_DIGEST_TRUST_FULL, 0, "
    "WORLD_DIGEST_TRUST_MAX) of the per-date Brier improvement over the row's own control, "
    "prior N(0, WORLD_DIGEST_TRUST_TAU^2). KEY 1 (per arm): n dates >= N_MDE, lower bound > 0, "
    "trust >= 0.05. KEY 2: "
    "the PC plan's own regret rows (decision_story plan_plus_shadow_news_full vs plan_full, "
    "net of round-trip cost): mean - 1.64 x se > 0 over >= NEWS_TILT_MIN_MDC_SESSIONS graded "
    "sessions. KEY 1 per arm: see NEWS_TILT_KEY1_*. Both, or the flag stays False.")
NEWS_TILT_MIN_MDC_SESSIONS = 20
#: KEY 1 (review 2026-10-07 F4), per ARM -- the direction trust gates only the d
#: term, the size trust only the s term, never max(). An arm's key holds only when
#: n independent dates >= N_MDE = ceil((2.8 x sd_date / DELTA)^2), posterior mean -
#: Z x posterior sd > 0, and trust >= MIN_TRUST. Below it the arm's trust is not used.
NEWS_TILT_KEY1_DELTA_BRIER = 0.02
NEWS_TILT_KEY1_Z = 1.64
NEWS_TILT_KEY1_MIN_TRUST = 0.05

# ── The reader's BROWSE lane: general news beyond Dow Jones (2026-09-29) ─────
#: Murat, 2026-09-29: "digest the news see what they are implying is there an
#: another path they are leading, not only the forecast from the websites but
#: the stocks news and the general news brose the news like a human to get the
#: context". FREE PUBLIC news, wire, and official-release sites, READ-ONLY, on
#: the same dedicated Chrome and under the same guards (instance proof before
#: every action, payment / message / social-write URL rules, NEVER_HOSTS,
#: DENIED_DOMAINS). No sign-in, no form, no search box. A bot check, block page,
#: paywall stub or a robots.txt disallow is RECORDED by class and the host is
#: left alone (a challenge cools it for READER_HOST_COOL_S); nothing here
#: disguises automation or works around a check.
OPENCLAW_NEWS_HOSTS = ("reuters.com", "apnews.com", "cnbc.com", "finance.yahoo.com",
                       "bbc.com", "ft.com", "asia.nikkei.com", "scmp.com",
                       "bls.gov", "sec.gov", "treasury.gov")
#: 2026-09-30: federalreserve.gov LEFT the visible browser. Its press releases,
#: speeches and testimony are read by feed (`official_sources` fed_rss) and each
#: item's full text is fetched by plain HTTP, so no page with a bank's name opens
#: in the window the owner watches and no content is lost. Every central bank is
#: feed / API only (the owner's check list: dowjones/WHAT_THE_READER_OPENS.md).
#: The allowlist is WIDENED by the news hosts (the Dow Jones and social hosts
#: and every rule on them are unchanged).
OPENCLAW_BROWSER_HOSTS = OPENCLAW_USER_TAB_HOSTS + OPENCLAW_SOCIAL_HOSTS + OPENCLAW_NEWS_HOSTS
#: The general-news fronts are in the pool's rotation (off -> Dow Jones + social only).
READER_NEWS_ENABLED = True
#: Per news host: 1 tab, a drawn 20-80 s gap between opens, 30 pages an hour and
#: 300 a day. The Dow Jones and social entries are NOT changed (merged, not raised).
READER_TABS_PER_HOST = {**READER_TABS_PER_HOST, **{h: 1 for h in OPENCLAW_NEWS_HOSTS}}
READER_HOST_GAP_S = {**READER_HOST_GAP_S, **{h: (20.0, 80.0) for h in OPENCLAW_NEWS_HOSTS}}
READER_MAX_PER_HOUR_BY_HOST = {**READER_MAX_PER_HOUR_BY_HOST,
                               **{h: 30 for h in OPENCLAW_NEWS_HOSTS}}
WEB_READER_MAX_PER_DAY_BY_HOST = {**WEB_READER_MAX_PER_DAY_BY_HOST,
                                  **{h: 300 for h in OPENCLAW_NEWS_HOSTS}}
#: THE REFILL RULE: a host whose pending list is at or below this many items has
#: its fronts revisited once they were read READER_FRONT_MIN_REVISIT_S ago
#: (instead of waiting for the 30-min / 2-h schedule). Empty with caps free is
#: QUEUE_EMPTY / REFILLING, never STALLED.
READER_QUEUE_LOW_WATER = 3
READER_FRONT_MIN_REVISIT_S = 1200.0
#: From an article reached from a front (depth 0), at most this many outbound
#: links (related blocks and in-article links, any allowed news host, matching
#: that host's article shape) are followed one hop; none from depth 1.
READER_BROWSE_FOLLOW_MAX = 3
#: Outbound links stored with each page record (url + text), for the digest.
READER_OUTBOUND_LINKS_STORED = 60
#: robots.txt of a news host is read (through the same browser, one page) and
#: kept this long; a disallowed path is never opened (class ROBOTS_DISALLOWED).
READER_ROBOTS_TTL_S = 86400.0
#: A host whose last READER_PAYWALL_STREAK article reads were paywall stubs or
#: signed-out pages reads only its FRONTS (the headlines) for READER_FRONTS_ONLY_S.
READER_PAYWALL_STREAK = 3
READER_FRONTS_ONLY_S = 21600.0
#: Licence line stored on a general-news record (not Dow Jones).
READER_NEWS_LICENCE = "public web page, read for personal research; not republished"
#: An item whose own publication date is more than this many days before AEGIS
#: first held it is ARCHIVE for the digest: counted, never a theme. The reader
#: stores old articles it reaches from stock pages (2025-10 and 2026-03 pieces
#: were read on 2026-09-27); a digest of "today" must not present them as news.
WORLD_DIGEST_MAX_ITEM_AGE_DAYS = 4

#: 2026-09-29 ft_lab: an OPTIONAL local first stage in the digest's per-article
#: extraction -- the fine-tuned Qwen2.5-1.5B typed-event student, run out of
#: process with the ft_lab interpreter. DEFAULT OFF; DeepSeek stays the extractor
#: of every row and the local reading only rides along as `local_event`. Any
#: refusal (no interpreter / adapter, RAM under the floor, GPU busy, crash,
#: timeout) falls back to DeepSeek alone (world_digest.local_event_stage).
WORLD_DIGEST_LOCAL_EXTRACT = False
WORLD_DIGEST_LOCAL_MIN_FREE_RAM_GB = 3.0
WORLD_DIGEST_LOCAL_TIMEOUT_S = 900.0

#: Review 2026-09-29 (REVIEW_2026-09-29_READER_POOL.md). F3: this many BLANK
#: pages in a row on one host cool it like a challenge (a load that reached the
#: site always counts against the caps). F6: a recurring item whose tab open
#: failed is retried after READER_OPEN_RETRY_S. F2: stall restarts of the pool
#: (and Chrome recycles) are at most READER_STALL_RESTARTS_PER_HOUR in any
#: rolling hour, doubling from READER_STALL_RESTART_BACKOFF_S; the ladder level
#: survives pool restarts and resets only after an OK page.
READER_BLANK_STREAK_COOL = 4
READER_OPEN_RETRY_S = 600.0
READER_STALL_RESTARTS_PER_HOUR = 3
READER_STALL_RESTART_BACKOFF_S = 300.0

#: 2026-09-29 (orchestrator, from the digest): the digest's asks in
#: news_digest/read_next.jsonl are adopted by the reader pool -- a URL on an
#: allowed host is read; a question becomes a navigation to the own search URL
#: of two sites (reader_scheduler.SEARCH_URLS), never typing -- at most this
#: many rows per refill, rows older than READER_READ_NEXT_MAX_AGE_H ignored,
#: READER_SEARCH_LINKS_MAX result links taken from each search page.
READER_READ_NEXT_PER_REFILL = 6
READER_READ_NEXT_MAX_AGE_H = 36.0
READER_SEARCH_LINKS_MAX = 3
#: A link whose visible date is older than this is not queued (fronts, stock
#: pages, searches); a stored article whose own dateline is older is flagged
#: `archive` and its links are not followed. Measured 2026-09-29: 455 of 995
#: Dow Jones pages stored in 36 h were archive articles, median 65 days old.
READER_MAX_ARTICLE_AGE_DAYS = 4.0

#: TRIAL-STRADDLE-FWD-1 (2026-09-29, backend/services/straddle_forward.py): a forward,
#: $0, paper-only log of ATM straddle SELECTION by the frozen size forecast vs the
#: option market's implied move (PRODUCT_EXPERIMENT; no broker, no orders, no LLM).
#: Universe = the top N bars names by 63-session median dollar volume; the standard
#: monthly expiry with calendar DTE in [MIN, MAX]; entry once per session inside the
#: ET window; quotes refused when a leg's spread over its mid > MAX_LEG_SPREAD, the
#: straddle's > MAX_STRADDLE_SPREAD, the strike is > MAX_STRIKE_DIST from spot, a leg's
#: open interest < MIN_OI, a leg's last trade is older than LEG_STALE_DAYS, or (during
#: a session) the underlying quote is older than UNDERLYING_STALE_MIN. IV inverted
#: from the mid at RATE, q = 0. BUDGET = premium per leg as a share of equity (the
#: utility read); EQUITY_NOTIONAL only sizes the worst-case print.
STRADDLE_FWD_UNIVERSE_CANDIDATES = 400
STRADDLE_FWD_MIN_PRICE = 5.0
STRADDLE_FWD_BREADTHS = (20, 50, 100)
STRADDLE_FWD_DTE_MIN = 21
STRADDLE_FWD_DTE_MAX = 35
STRADDLE_FWD_ENTRY_START_ET = "10:45"
STRADDLE_FWD_ENTRY_END_ET = "15:30"
STRADDLE_FWD_MAX_STRADDLE_SPREAD = 0.20
STRADDLE_FWD_MAX_LEG_SPREAD = 0.50
STRADDLE_FWD_MAX_STRIKE_DIST = 0.05
STRADDLE_FWD_MIN_OI = 10
STRADDLE_FWD_LEG_STALE_DAYS = 5.0
STRADDLE_FWD_UNDERLYING_STALE_MIN = 30.0
STRADDLE_FWD_RATE = 0.04
STRADDLE_FWD_BUDGET = 0.02
STRADDLE_FWD_EQUITY_NOTIONAL = 1_000_000.0

# ── the reader: X handle timelines (2026-09-29) ──────────────────────────────
# The source registry's X handles are read as profile/timeline pages inside
# x.com's EXISTING caps (WEB_READER_MAX_PER_DAY_BY_HOST is not raised). Once a
# day each: 37 handles spend ~37 of x.com's 150 daily loads.
READER_X_HANDLE_FRESH_H = 24.0

# ── hyp_lab: the hypothesis ledger that learns (2026-09-29 night) ────────────
# A ledger of typed hypotheses (mechanism, precursor known beforehand, what
# separates it from factor beta, test design with a declared split, status,
# verdict, receipts). Seeded from the day's notes, the world digest's
# second-order paths and LLM generation (DeepSeek + the local model), deduped
# against docs/TRIALS and the closed list, ranked by
# P(changes the roadmap) x value - cost. The nightly runner executes the top
# few PRE-DECLARED cells and writes verdicts back so the next generation sees
# them. PRODUCT_EXPERIMENT; no LLM authority over capital; nothing trades.
HYP_LAB_NIGHT_CAP_USD = 3.00          # every hyp_lab-owned DeepSeek call, per night
HYP_LAB_NIGHTLY_CAP_USD = 0.40        # the scheduled nightly's own cap (generation only)
HYP_LAB_PRICE_IN_PER_M = 0.30         # peak list price, so the cap binds even if the ledger prices $0
HYP_LAB_PRICE_OUT_PER_M = 1.20
HYP_LAB_MAX_CELLS_PER_NIGHT = 8
HYP_LAB_MIN_FREE_RAM_GB = 3.0
HYP_LAB_NIGHTLY_TIME_BOX_MIN = 60
#: CHUNK C12 / owner decision D6 (2026-10-06, borrowed from RD-Agent(Q)): each family's Beta
#: posterior (hyp_lab.family_record) is fed BACKWARD into generation. A family whose posterior
#: mean is below FLOOR gets weight max(MIN_WEIGHT, p / FLOOR): its generation quota is
#: floor(ceil(n x MAX_SHARE) x weight) (never below 1: a shrink, never a kill) and its EV in
#: ranking is multiplied by the weight, written to policy_state as a PREFERENCE
#: (`hyp_family_ev_weight`). Nothing is deleted or closed; rows over quota are DEFERRED and
#: re-admitted when the family's posterior returns to >= FLOOR. The $ caps above are untouched.
HYP_LAB_FAMILY_POSTERIOR_FLOOR = 0.15
HYP_LAB_FAMILY_MIN_WEIGHT = 0.25
HYP_LAB_FAMILY_MAX_SHARE = 0.5         # no family may take more than half of one generation round
#: Review 2026-10-06 (docs/reviews/REVIEW_2026-10-06_C12_THEORY_CELLS.md F6-F8):
#: a FIXED family taxonomy. A generated label outside it is filed under UNMAPPED and gets the
#: MEDIAN quota (renaming can no longer buy a fresh full quota); aliases fold known splits.
HYP_LAB_FAMILIES = (
    "macro_readthrough_commodity", "macro_readthrough_rates", "equity_readthrough_supply_chain",
    "event_readthrough_corr_peer", "event_readthrough_text_link", "event_readthrough_supply_chain",
    "size_attention", "size_disagreement", "size_event_prior", "llm_size_reading",
    "llm_belief_elasticity", "llm_leakage", "investable_spread", "risk_timing", "data_vintage",
    "insider_event", "digest_forward", "vol_compression", "official_disclosure",
    "price_location", "earnings_streak")
HYP_LAB_FAMILY_ALIASES = {"insider_hold": "insider_event"}
HYP_LAB_UNMAPPED_FAMILY = "family_unmapped"
#: the posterior counts only POWERED negatives (CANNOT_DISTINGUISH = 0, an unpowered
#: FAILED_VARIANT = 0, a re-read of an already-run rule = 0); a verdict older than
#: HYP_LAB_VERDICT_DECAY_DAYS counts half.
HYP_LAB_VERDICT_DECAY_DAYS = 180
#: a shrunk family keeps at least one cell RUN per this many days (exploration floor)
HYP_LAB_SHRUNK_FAMILY_MIN_RUN_DAYS = 7
#: theory-cell declaration gate (scripts/hyp_theory_cells.py): refuse when one class of the
#: separating variable holds more than MAX_CLASS_SHARE of events, or when the control's
#: labels-only MDE (2.8 x EVENT_SD / sqrt(n_control), a LOWER bound: i.i.d., no blocking)
#: exceeds MAX_MDE_MULT x the declared effect worth having.
THEORY_GATE_MAX_CLASS_SHARE = 0.90
THEORY_GATE_EVENT_SD = 0.25            # per-event sd of a 63-session single-name excess return (preset)
THEORY_GATE_MAX_MDE_MULT = 2.0


# ── FLEET DAILY MANAGER (2026-09-29 night; `backend/services/fleet_manager.py`) ──
#: Murat: "update the hacks positions daily. do either locally or with railway."
#: The Railway loops are down ($20/mo budget), so the hack1-hack6 paper accounts
#: are managed from this PC by `scripts/fleet_manager_run.py`. Every value below
#: is a HARD limit checked in code before any order; none is a target.
FLEET_MANAGER_ROLES: tuple = ("hack1", "hack2", "hack3", "hack4", "hack5", "hack6")
FLEET_MANAGER_MAX_GROSS_FRAC = 1.00        # sum|notional| / equity; 1.0 = no leverage
FLEET_MANAGER_MAX_NAME_FRAC = 0.10         # one name, as a fraction of equity
FLEET_MANAGER_DAILY_TURNOVER_FRAC = 0.50   # non-protective order notional per session / equity
FLEET_MANAGER_MAX_ORDERS_PER_RUN = 60      # circuit breaker per account per run
FLEET_MANAGER_MIN_ORDER_USD = 250.0        # below this the cost is the edge
#: Stops are quoted in DAILY SIGMA (63-session sd of close-to-close returns on
#: the bar-defect-screened panel), never a fixed percent: -2% is 0.93 sigma on
#: a 2.16%/day name (memory 09-24). Distance = clip(K x sigma, MIN, contract max).
FLEET_MANAGER_STOP_K_SIGMA = 3.0
FLEET_MANAGER_STOP_MIN_FRAC = 0.04
FLEET_MANAGER_SIGMA_WINDOW = 63
#: A resting GTC stop expiring within this many days is replaced.
FLEET_MANAGER_STOP_RENEW_DAYS = 7
#: Limit orders near the quote: buy at ask x (1+slip), sell at bid x (1-slip).
FLEET_MANAGER_LIMIT_SLIP_BPS = 10.0
#: A quote whose spread exceeds this fraction of the mid is not a quote to trade on.
FLEET_MANAGER_MAX_SPREAD_FRAC = 0.02
#: Orders only while the venue is open and at least this long before its close.
FLEET_MANAGER_MIN_MINUTES_TO_CLOSE = 5
#: Declared cost per side for every contract (paper fills are free; the grade is not).
FLEET_MANAGER_COST_BPS_PER_SIDE = 10.0
FLEET_MANAGER_OPTION_ALERT_DTE = 5
#: News sleeve (hack6 v2 proposal): SHADOW_NEWS_v0's typed `news_signal` over the
#: newest world digest, names with d > 0 only, this much equity each, at most N.
FLEET_MANAGER_NEWS_UNIT_FRAC = 0.01
FLEET_MANAGER_NEWS_MAX_NAMES = 10
FLEET_MANAGER_NEWS_HOLD_SESSIONS = 5
FLEET_MANAGER_NEWS_MAX_DIGEST_AGE_H = 36
#: A name that already moved more than this many 5-session sigmas is not entered.
FLEET_MANAGER_NEWS_MAX_ALREADY_MOVED_SIGMA = 2.0
#: Market CONTROL (hack5 v2, 2026-09-30): ~95% one broad ETF, the rest cash; a
#: disaster stop far outside noise (10% on SPY is ~12 daily sigma), so the
#: control is stopped out by a crash, never by a wiggle.
FLEET_MANAGER_CONTROL_SYMBOL = "SPY"
FLEET_MANAGER_CONTROL_WEIGHT = 0.95
FLEET_MANAGER_CONTROL_STOP_FRAC = 0.10
#: C26 (2026-10-07): NAMED GATES in `fleet_manager.GATES`, walked in this order
#: for every order proposal; each returns PASS / SHRINK(to) / KILL with a reason,
#: and the trace lands on the decision row and the run receipt. A gate may only
#: shrink or kill (pinned by test); an EXIT is blocked only by a LEASE gate.
#: `test_fleet_gates.py` fails if this tuple and the code's order differ.
FLEET_GATE_ORDER: tuple = ("kill_switch", "credential", "reconciliation", "venue_window",
                           "instrument", "order_shape", "long_only", "stop_never_loosened",
                           "min_order", "cooldown", "turnover_budget", "cash", "gross_cap",
                           "name_cap", "sector_concentration", "order_count")
#: No re-entry into a name a sell-STOP filled on within this many sessions
#: (weekday count, `fleet_manager.sessions_between`): blocked at N-1, allowed at N.
FLEET_GATE_COOLDOWN_SESSIONS = 5
#: No sector above this fraction of the account's gross, the denominator floored
#: at equity (so an account in cash can buy its first names). Sector from the
#: newest potential_universe identity.sector (the map book_dna reads); a name
#: with no sector joins ONE bucket named UNKNOWN. A contract's declared
#: name-cap override (the SPY control) is exempt: it is not a sector bet.
FLEET_GATE_SECTOR_MAX_FRAC = 0.40
#: The stop-fill lookback the cooldown gate reads, in calendar days (covers N
#: sessions with room for holidays).
FLEET_GATE_COOLDOWN_LOOKBACK_DAYS = 21
#: `cooldown` and `sector_concentration` are new (C26, 2026-10-07) and would
#: change a LIVE book's executed positions before the owner has decided --
#: hack2's Technology buys would be KILLED tonight at the 22:45 HKT open pass
#: because Technology is already 67% of hack2
#: (`docs/research_notes/2026-10-07/fleet_gates_and_eod_audit_2026-10-07.md`).
#: "shadow": both gates evaluate and the trace carries what they WOULD have
#: done (`shadow_verdict`: `SHADOW_WOULD_KILL` / `SHADOW_WOULD_SHRINK(to=...)`),
#: but `fleet_manager.run_gates` always returns PASS for them -- no size or
#: kill changes. "enforce": they bind like every other gate. Flip only on
#: Murat's decision; the flip is hashed onto `gates_config()["hash"]` so it is
#: visible on every receipt.
FLEET_NEW_GATES_MODE = "shadow"
#: Enforce mode is REFUSED for `sector_concentration` (it stays shadow, printed
#: on the receipt) when the sector map is older than this many days, or when
#: the UNKNOWN bucket exceeds this share of the account's gross: a stale or
#: blind taxonomy measures itself, not concentration (review 2026-10-07 F5).
FLEET_GATE_SECTOR_MAP_MAX_AGE_DAYS = 14
FLEET_GATE_SECTOR_MAX_UNKNOWN_FRAC = 0.20
#: The broker's 403 "potential wash trade" rejections (49 of 75 LIVE buys since
#: 2026-10-01: top-ups of names holding a resting GTC sell stop) are a KNOWN,
#: UNFIXED execution defect queued as its own chunk; every run receipt carries
#: this line so nobody reads C26 as having addressed it.
FLEET_KNOWN_DEFECT_WASH_TRADE = ("since 2026-10-01, 49 of 75 LIVE buys came back HTTP 403 'potential wash "
                                 "trade' (top-ups of names with a resting sell stop); NOT fixed by C26; "
                                 "C27 (gate_policy_version c27-wash-trade-sequence) sequences every top-up "
                                 "as cancel stop -> buy -> one combined stop, with rollback")
#: C27 WASH-TRADE SEQUENCE (2026-10-07, `fleet_manager.execute_topup_sequence`).
#: Alpaca rejects a LIMIT BUY while a SELL STOP rests on the same symbol in the
#: same account ("stop sell | limit buy | always rejected", and the reverse
#: "limit buy | stop sell | always rejected"), so a top-up cancels the resting
#: stop, buys, waits for the buy to be TERMINAL, then places ONE stop for the
#: combined quantity. Not a gate and not shadowed: a correctness fix to order
#: sequencing that binds from the first pass that runs it.
#: How long the buy may stay open before its remainder is cancelled (the
#: combined stop cannot be placed while any part of the buy is open).
FLEET_WASH_SEQ_BUY_WAIT_S = 8.0
#: How long to wait for a cancel (of the resting stop, or of a buy remainder)
#: to be confirmed terminal by the venue.
FLEET_WASH_SEQ_CANCEL_WAIT_S = 6.0
#: A sequence whose stop-less window exceeded this many seconds, or that ended
#: REFUSED / UNPROTECTED, makes every LATER top-up on the same account in the
#: same run REFUSED_WASH_TRADE_RULE (the venue is not answering fast enough to
#: open another window safely).
FLEET_WASH_SEQ_MAX_WINDOW_S = 45.0
#: Health: a fleet pass (or an EOD audit row) where more than this share of the
#: LIVE buys sent to the broker came back rejected is DEGRADED, with the counts
#: by reason (403 wash trade, 422, other) in the reason.
FLEET_REJECTED_BUY_DEGRADED_FRAC = 0.20
#: C26 END-OF-DAY AUDIT (`backend/services/fleet_eod_audit.py`): the Preclose
#: pass runs it last; `python -m scripts.fleet_eod_audit` runs it alone. It
#: never places or cancels anything (its transport refuses every non-GET).
#: A grade-ledger equity that differs from the broker's previous-close equity
#: by more than this fraction is a reconciliation mismatch.
FLEET_EOD_AUDIT_GRADE_TOL_FRAC = 0.005
#: Preclose receipts started before this instant predate the audit; the health
#: reader excuses their missing audit row (named), and requires it after.
FLEET_EOD_AUDIT_SINCE_UTC = "2026-10-07T12:00:00Z"
#: Source trust from fleet grades (forward only, nn_lab/loop.py style): trust is
#: the posterior mean of a source's mean DAILY excess over the control, prior
#: N(0, PRIOR_SD^2), from COMPLETED blocks of BLOCK_SESSIONS graded sessions only
#: -- a partial block counts nothing, so one night's grade cannot move a weight.
#: k = (BLOCK_SD/PRIOR_SD)^2 ~ 20 blocks (~100 sessions) to reach a 50% shrink.
FLEET_TRUST_BLOCK_SESSIONS = 5
FLEET_TRUST_PRIOR_SD = 0.001        # 10 bps/day prior sd of a source's true daily excess
FLEET_TRUST_BLOCK_SD = 0.0045       # sd of a 5-session mean of daily excess (~1%/day / sqrt 5)
FLEET_TRUST_FULL = 0.0005           # posterior excess (5 bps/day) at which a source earns full weight

# ── contest order sheet + dress rehearsal (2026-09-29 night) ─────────────────
# The Bloomberg challenge book as tickets the owner types into TMSG. The cap is
# applied as min(20% of current NAV, 20% of the $1M notional) at the LIMIT
# price, so a gap up to the limit cannot breach it. Contest capital, the cap's
# basis and board lots are OWNER-CONFIRM items (docs/CONTEST_RUNBOOK_2026-10.md).
CONTEST_NOTIONAL_USD = 1_000_000.0
CONTEST_POSITION_CAP = 0.20
CONTEST_BUY_LIMIT_BAND = 0.05        # buy limit = last close x 1.05
CONTEST_SPLIT_GUARD = 0.30           # Terminal price beyond +-30% of the sheet: split or gap check
CONTEST_DEFECT_LOOKBACK_DAYS = 730   # a bar-defect flag inside this window refuses the name

# ── THE READING BUDGET and the OFFICIAL sources (2026-09-30) ─────────────────
# Murat, 2026-09-29: "use openclaw to review stocks or the general news and the
# market positions, insider traders, politics etc anything needed", "digest
# everything". MEASURED: first-come spent the 4,000 browser loads by 10:44 UTC
# and the reader then stood WAITING_FOR_CAP for hours. The same total is now
# spent by lane (declared shares) and by hour (heavier before and during the
# Asian and US sessions): `reader_scheduler.budget_verdict`. The Dow Jones and
# social per-host caps are NOT changed. The page-load total is NOT raised; the
# owner's "read more" is met by the official APIs below, each with its own
# small daily cap (`official_sources.SOURCES`), which never touch the browser.
READER_BUDGET_ENABLED = True
#: 2026-10-06 (C7): `query_planner` (the search-led planner's admitted URLs,
#: `backend/services/query_planner.py`) gets 0.03 = ~120 loads/day INSIDE the
#: same 4,000, taken from markets_news (0.20 -> 0.18) and digest_asks (0.06 ->
#: 0.05). Work-conserving: an idle planner lane's share is borrowed by others.
READER_BUDGET_SHARES = {
    "book_names": 0.24, "universe_names": 0.12, "markets_news": 0.18, "macro_world": 0.12,
    "politics_policy": 0.08, "official_releases": 0.04, "social": 0.11,
    "digest_asks": 0.05, "query_planner": 0.03, "overhead": 0.03}

# ── THE QUERY PLANNER (2026-10-06, chunk C7) ─────────────────────────────────
# The reader revisits; this makes it SEARCH. Seeds (held names across the fleet
# and PC-PAPER, the newest world digest's themes, the opportunities shortlist)
# -> templated queries (no LLM writes the query text) -> ONE OpenClaw agent turn
# per query that may call only `web_search` / `x_search` (the read-only tool
# scope is unchanged and audited before and after) -> URLs -> the allowed-host
# classifier (refused stays refused; a NEW host is QUARANTINED, never admitted)
# -> `dowjones/query_planner_queue.jsonl`, adopted by the reader pool into the
# `query_planner` budget lane with its `query_id`. `--due` honours this cadence.
QUERY_PLANNER_ENABLED = True
QUERY_PLANNER_EVERY_H = 6.0
QUERY_PLANNER_MAX_QUERIES_DAY = 24
QUERY_PLANNER_MAX_QUERIES_RUN = 8
#: per seed lane, per UTC day (their sum may exceed the day cap; the day cap binds)
QUERY_PLANNER_LANE_QUERIES_DAY = {"held_names": 12, "themes": 8, "opportunities": 4}
QUERY_PLANNER_MAX_URLS_PER_QUERY = 6
#: admitted URLs queued per UTC day; equals the lane's share of the 4,000 loads
QUERY_PLANNER_MAX_ADMITTED_DAY = 120
QUERY_PLANNER_MODEL = "deepseek/deepseek-flash"
QUERY_PLANNER_TURN_TIMEOUT_S = 240.0
#: a run stops issuing queries once its priced spend passes this (an unpriced
#: turn is charged QUERY_PLANNER_UNKNOWN_COST_USD, never zero)
QUERY_PLANNER_RUN_USD_CAP = 0.30
QUERY_PLANNER_UNKNOWN_COST_USD = 0.03
#: Review 2026-10-06 F1. Agent search turns are issued ONLY when a search
#: provider is DECLARED here (measured: OpenClaw's `web_search` answers "disabled
#: or no provider is available" and `x_search` is not offered). None = no agent
#: turn at all; setting it is an OWNER decision (Brave is card-gated; "no
#: payments"). `x_search` templates exist only when the agent is offered it.
QUERY_PLANNER_SEARCH_PROVIDER = None
QUERY_PLANNER_X_SEARCH_OFFERED = False
#: With no provider, the SAME templates run against the $0 keyless sources:
#: Google News RSS search (publisher + headline -> the publisher's own search
#: page; the Google redirect is never opened) and EDGAR full-text search (the
#: company's own 8-Ks). No LLM turn, no gateway.
QUERY_PLANNER_FREE_SOURCES_ENABLED = True
#: the single-run lock; an older lock is a crashed run and is taken
QUERY_PLANNER_LOCK_MAX_S = 3600.0
#: hosts a search may return that are REFUSED on top of the browser's own
#: money / checkout / mail / message refusals (audit 2026-10-06 §C: ToS or
#: robots.txt; search-engine result pages; consumer-AI chat UIs; login walls)
QUERY_PLANNER_REFUSED_HOSTS = (
    "youtube.com", "youtu.be", "instagram.com", "facebook.com", "tiktok.com",
    "linkedin.com", "chatgpt.com", "openai.com", "perplexity.ai", "claude.ai",
    "consensus.app", "gemini.google.com", "duckduckgo.com", "bing.com", "google.com",
    "efdsearch.senate.gov", "pbc.gov.cn", "api.nasdaq.com")

#: 2026-10-06 (C7): a Dow Jones feed whose NEWEST item is older than this is
#: FROZEN_UPSTREAM and lands in the receipt's `refused_or_red`. Measured: the
#: five `feeds.a.dj.com/rss/*` WSJ URLs still answer 200 with 20 items, all
#: dated 2025-01-27 (~607 days) -- the parser was right, the URLs were retired;
#: the live copies are under `feeds.content.dowjones.io/public/rss/`.
DOWJONES_FEED_FROZEN_AGE_H = 14 * 24.0
#: UTC hours 0-23: Asia 00-07 (1.4), Europe 08-10 (0.8), US pre-open 11-12
#: (1.3), US session 13-19 (1.6), US evening 20-22 (0.7), Asia pre-open 23 (1.2)
READER_BUDGET_HOUR_WEIGHTS = (1.4, 1.4, 1.4, 1.4, 1.4, 1.4, 1.4, 1.4, 0.8, 0.8, 0.8, 1.3, 1.3,
                              1.6, 1.6, 1.6, 1.6, 1.6, 1.6, 1.6, 0.7, 0.7, 0.7, 1.2)
READER_BUDGET_MIN_PER_HOUR = 60
#: rolling-10-minute ceiling = hour allowance / 6 x this (smooths the hour)
READER_BUDGET_BURST = 1.25
#: a lane that has spent this multiple of its daily share borrows nothing while
#: another lane with something servable is under its own hourly share
READER_BUDGET_LANE_DAY_MULT = 1.6
#: the official API sources (backend/services/official_sources.py): launched by
#: the night reader supervisor out of process every this many seconds, each
#: source then read only when its own interval has passed; a bot check cools
#: a source for OFFICIAL_COOL_S
OFFICIAL_SOURCES_ENABLED = True
OFFICIAL_SOURCES_EVERY_S = 900.0
OFFICIAL_COOL_S = 86400.0

# ── THE ACADEMIC LANE (Q12, 2026-10-07) ──────────────────────────────────────
# `docs/research_notes/2026-10-07/research_instruments_2026-10-07.md`: a
# research-intake card (verdict NEEDS_DATA / READY_TO_CELL / NOT_A_HYPOTHESIS_
# YET) names open literature questions in its own `## Needs evidence` list;
# `backend/services/research_instruments.py` answers them with keyless, $0
# academic-citation fetchers (OpenAlex, CrossRef, NBER new-working-papers RSS)
# and writes a per-card evidence file -- never into the card itself. Own cap,
# own day, same "own per-day cap in config" shape as QUERY_PLANNER_LANE_
# QUERIES_DAY, but a SEPARATE budget: this lane never shares the web-search
# lane's queue/ledger, because a citation is not a URL for the reader to admit.
RESEARCH_INSTRUMENTS_ENABLED = True
#: per UTC day, across every card; $0 (OpenAlex + CrossRef + NBER RSS)
QUERY_PLANNER_ACADEMIC_QUERIES_DAY = 12
#: default tier queries per NEEDS-EVIDENCE question before escalating
RESEARCH_INSTRUMENTS_DEFAULT_BUDGET = 2
#: extra queries into the extended tier (Semantic Scholar / arXiv / NBER RSS),
#: only when the default tier's coverage of the card's own seed citations is
#: below this (note §3.3)
RESEARCH_INSTRUMENTS_EXTENDED_CAP = 3
RESEARCH_INSTRUMENTS_STOP_COVERAGE = 0.8
#: a question stops escalating once it holds this many citations with a
#: verified (resolvable) DOI, or the budget above is exhausted
RESEARCH_INSTRUMENTS_MIN_VERIFIED = 1
#: CrossRef/OpenAlex "polite pool" contact param -- an OWNER decision (never
#: defaulted to a personal address): None sends no `mailto`, which both
#: instruments measured working anyway on 2026-10-07 (no 429, no key).
RESEARCH_INSTRUMENTS_MAILTO = None
#: Semantic Scholar: $0 but measured unreliable keyless (HTTP 429 on 2 of 2
#: tries, twice over, 2026-10-07) -- a free API key is a cheap owner upgrade,
#: never required to start. None = the fetcher REFUSES (KEY_REQUIRED_OR_
#: RATE_LIMITED), the same declared-provider shape as QUERY_PLANNER_SEARCH_
#: PROVIDER.
RESEARCH_INSTRUMENTS_SEMANTIC_SCHOLAR_KEY = None
#: arXiv: $0, keyless by design, but real coverage is the quant/ML preprint
#: class only (classical asset-pricing journal mechanisms are not on arXiv) and
#: it was measured 429 on 2 of 2 tries the same day. An explicit owner opt-in
#: is required before this lane calls it automatically.
RESEARCH_INSTRUMENTS_ARXIV_ENABLED = False
RESEARCH_INSTRUMENTS_HTTP_TIMEOUT_S = 20.0
#: the weekly task_keeper owner (`AegisResearchLane`, additive -- daily_pass.py
#: is untouched): due when no probe has ever run, or the newest one is this old
RESEARCH_LANE_EVERY_DAYS = 7.0
RESEARCH_LANE_TIMEOUT_MIN = 10.0

# ── automation fixes 2026-10-02 ─────────────────────────────────────────────
#: The daily pass's `paper_accounts` step reads the brokers (READ-ONLY GETs:
#: /v2/account + /v2/positions per account, PC-PAPER via pc_broker.snapshot).
#: It ran `--no-broker` from 2026-09-28 to 10-02 and every receipt silently
#: dropped hack1-6 and PC-PAPER. False restores the narrow pass AND prints a
#: DEGRADED line at the top of the receipt; it is never silent.
DAILY_PASS_PAPER_ACCOUNTS_BROKER_READ = True
#: A kill-switch STOP file older than this is REPORTED (receipt + health) as a
#: stale stop the owner may have forgotten; it still stops (owner's call,
#: 2026-10-02: report, keep the stop). hyp_lab/STOP from 09-29 22:41 blocked
#: every nightly for three days with nobody told.
STOP_FILE_STALE_WARN_H = 48.0
#: `always_on_lab` stays OFF while this marker exists (2026-10-02). Every
#: launcher of the lab checks it (`always_on_lab.off_marker_state()`); the
#: health rows report it. Deleting the file is the owner's switch back ON.
ALWAYS_ON_LAB_OFF_MARKER = "always_on_lab_OFF"
#: Broker accounts known to be unreadable on purpose (retired keys). The daily
#: pass NOTES them and does not degrade on them; any OTHER unreadable broker
#: account is a DEGRADED line. hack3: key answers HTTP 401 since 2026-09-22.
PAPER_ACCOUNTS_RETIRED_UNREADABLE: tuple = ("hack3",)

# ── PC-PAPER mandate and the sim owner (2026-10-06, chunk C2) ───────────────
#: OWNER DECISION 2026-10-06: PC-PAPER is a ~$1,000,000 paper experiment. The
#: decision contract is sized on the BROKER'S equity read, never on a literal;
#: the owner's real capital is reported as a scaled view (IC_CAPITAL_LEVELS).
#: The contract's capital and the broker equity may differ by at most this
#: fraction of equity before the mandate prints UNRECONCILED.
PC_MANDATE_CAPITAL_TOLERANCE = 0.05
#: A broker equity read older than this (days, by the read's own stamp) is
#: UNRECONCILED (BROKER_EQUITY_STALE). Four days covers a long weekend.
PC_MANDATE_EQUITY_MAX_AGE_DAYS = 4.0
#: Session protocol item 4: the largest admissible book's one-day k-sigma loss
#: may not exceed this fraction of equity. Above it the mandate says REFUSE and
#: the sim owner will not start a trading session. Never widened to pass.
PC_WORST_CASE_MAX_FRAC_OF_EQUITY = 0.10
#: The scheduled sim owner (`python -m scripts.task_keeper sim`). It starts a
#: session on an XNYS trading day between these US/Eastern times (09:00 ET is
#: 21:00 HKT in EDT, 22:00 HKT after 2026-11-01) and otherwise writes a receipt
#: saying why not. The session runs to at least SIM_OWNER_END_AFTER_CLOSE_MIN
#: past the 16:00 ET close so the after-close grade lands inside it.
SIM_OWNER_FIRST_START_ET = (9, 0)
SIM_OWNER_LAST_START_ET = (15, 30)
SIM_OWNER_END_AFTER_CLOSE_MIN = 60
#: The mode the owner starts when the mandate is OK and the worst case passes;
#: otherwise it starts "observe" and names the refusal on its receipt.
SIM_OWNER_MODE = "paper_profit"
#: A sim_session health row trusts the owner's last receipt for this long
#: (the task fires every 30 min, plus logon / unlock / wake).
SIM_OWNER_RECEIPT_MAX_AGE_MIN = 75

# ── Data catalog + ledger archival (chunk C10, 2026-10-06) ─────────────────
#: A closed `<ledger>_<YYYY-MM>.jsonl` at or above this size is archived to
#: Parquet outside git with a committed manifest (`ledger_archive`).
LEDGER_ARCHIVE_MIN_BYTES = 50 * 1024 * 1024
#: Files below this get a full content sha256; above it, size + first/last
#: 1 MB, labelled as such (`data_catalog`). JSONL line counts obey it too.
DATA_CATALOG_FULL_HASH_MAX_BYTES = 200 * 1024 * 1024
#: A file of a non-dataset kind (small json receipts, logs, txt) gets its own
#: catalog row only at or above this size; below it, it is rolled up into its
#: directory's row.
DATA_CATALOG_OWN_ROW_MIN_BYTES = 5 * 1024 * 1024
#: Local GGUF model directory, outside the repo. Env override wins.
DATA_CATALOG_LLAMA_MODELS_ENV = "AEGIS_LLAMA_MODELS_DIR"

# ── Sticky matched twin (CHUNK C1b, 2026-10-07) ──────────────────────────────
#: `matched_twins.twin_series_sticky`: a partner is drawn once per rule holding (same
#: size x vol x 12-1 cell as of the entry date) and held until the rule exits that name,
#: so the twin's turnover equals the rule's by construction. Declared BEFORE the board was
#: run: a board row is REFUSED (named, with the gap) when the median over invested months
#: of |twin one-way turnover - rule one-way turnover| exceeds this. Residual gap is the
#: EW re-weighting of drifted books (different returns) and partner deaths/collisions.
STICKY_TWIN_TURNOVER_TOLERANCE = 0.03
#: independent sticky draws per rule (the registered twin21's count: draw 0 + 20 extra)
STICKY_TWIN_N_DRAWS = 21

# ── Opportunity Explorer (C4, 2026-10-06; review fixes F1-F6) ──────────────
#: The receipt is STALE on the page past this many days (scripts.opportunities_build;
#: the funnel_night10.json lesson: a static file with no age check is green forever).
OPPORTUNITIES_STALE_DAYS = 3
#: F1 "coverage" flag: fewer than this many DISTINCT firms with a dated target action
#: in the last OPPORTUNITIES_COVERAGE_WINDOW_DAYS (a target older than that is not coverage).
OPPORTUNITIES_COVERAGE_MIN_FIRMS = 3
OPPORTUNITIES_COVERAGE_WINDOW_DAYS = 180
#: F1 "binary event" flag: an FDA / trial event dated within this many weekdays.
OPPORTUNITIES_BINARY_WINDOW_SESSIONS = 63
#: F1 "runway" flag: cash and equivalents below this many quarters of operating loss.
OPPORTUNITIES_RUNWAY_MIN_QUARTERS = 4
#: F1: the High-Risk Innovation badge needs at least this many of the three flags.
OPPORTUNITIES_BADGE_MIN_FLAGS = 2
#: F3: a median-target upside below this is LOW UPSIDE (grey, never green).
OPPORTUNITIES_LOW_UPSIDE = 0.05
#: Q17 (2026-10-07): raw receipts (~5-8 MB each) are SUBSTRATE for the published, sanitised
#: copy (`backend/data/public_receipts/opportunities/latest.json`, <= 2.4 MB, committed) --
#: never git-tracked themselves (.gitignore). `opportunities_build.prune_raw_receipts` keeps
#: only the newest this many locally, ordered by the RUN ID IN THE FILENAME, never by mtime
#: (a fresh checkout's files are all "written today").
OPPORTUNITIES_KEEP_RAW = 7

# ── Analyst reputation + snowball shadow (CHUNK C18, 2026-10-07) ─────────────
# Declared and FROZEN here before any read of the weights or the snowball rows
# (spec docs/research_notes/2026-10-07/analyst_reputation_spec_2026-10-07.md):
# a prior chosen after the diagnostic is not a prior. K1 is NOT redeclared: it is
# pit_features.SKILL_SHRINK_K (= 20), unchanged, used at two levels.
#: (firm, sector, horizon) cell shrunk toward the firm's sector-anchored edge with
#: this pseudo-count (= 2 x K1: a cell is a strict subset of the firm's claims).
ANALYST_REP_K_SUB = 40
#: The only horizon on disk (12-month targets): the horizon level is DEGENERATE today.
ANALYST_REP_HORIZON = "12m"
#: A claim = a dated target raise/lower; outcome = sign x (stock - SPY) over this
#: many sessions from the close of the first session STRICTLY after the event day.
ANALYST_REP_CLAIM_SESSIONS = 63
#: A firm covers a ticker when its latest row on it is at most this many days old.
ANALYST_REP_COVER_DAYS = 365
#: Review F4 (2026-10-07): a covering firm's target enters the weighted target only
#: if its latest row is at most this old; otherwise null with `stale_target`.
ANALYST_REP_TARGET_MAX_AGE_DAYS = 90
#: Review F1: split-half persistence test, firm-bootstrap seed (outside board seeds).
ANALYST_REP_PERSIST_SEED = 7_100_020
#: Snowball follow-through shadow (TRIAL-ANALYST-SNOWBALL-1 primary 1, unsigned):
SNOWBALL_GAP_DAYS = 90              # the quiet spell first_movers() reads
SNOWBALL_HISTORY_DAYS = 90          # raise history required BEFORE the quiet window
SNOWBALL_HORIZON_SESSIONS = 63      # follow-through window, XNYS sessions
SNOWBALL_THRESHOLD = 2              # >= this many OTHER distinct firms raise
#: Expanding-window base rate = (k + a) / (n + 2a), a = PSEUDO / 2, prior 0.5:
#: a thin early history gets a wide prior, never the full-sample 36%.
SNOWBALL_PRIOR_PSEUDO = 20
#: Review F9 (2026-10-07): the base rate uses only events whose window closed in the
#: TRAILING this-many months before the t0 day (the all-history mean lagged the
#: coverage-driven drift by ~10pp). Declared before the ledger was rewritten.
SNOWBALL_BASE_WINDOW_MONTHS = 24
#: A row is FORWARD only when written within this many days of its t0 day; every
#: other row is REPLAY (historical, never forward evidence).
SNOWBALL_FORWARD_MAX_LAG_DAYS = 3
#: cross_sectional_rho bootstrap: month-block resamples and a seed outside every
#: seed used on this board (session protocol item 9).
SNOWBALL_RHO_BOOT = 1000
SNOWBALL_RHO_SEED = 7_100_018

# ── Progress-aware health (CHUNK C8, 2026-10-07) ─────────────────────────────
#: `task_receipts`: each scheduled task's DECLARED cadence in hours -- the longest
#: gap between two of its receipts while it is meant to be producing. The probe
#: allows cadence x (1 + system_health.GRACE); a `session_only` task also gets
#: 24 h per non-XNYS day since its newest receipt. Ages come from the receipt's
#: own stamp, never mtime. Read from the live triggers on 2026-10-07.
HEALTH_TASK_CADENCE_H = {
    "AegisDailyPass": 24.0, "AegisIIF1NightLauncher": 24.0, "AegisNNLabNightly": 24.0,
    "AegisSimOwner": 1.0, "AegisDataCatalog": 24.0, "AegisContestRehearsal": 24.0,
    "AegisContestDesk": 24.0, "AegisHypLabNightly": 24.0, "AegisWorldDigest": 6.0,
    "AegisAlerts": 0.5, "AegisStraddleForward": 0.5, "AegisFleetManagerOpen": 24.0,
    "AegisFleetManagerPreclose": 24.0, "AegisFleetDailyCheck": 24.0,
    "AegisReaderSupervisor": 0.5, "AegisCatchUp": 2.0, "AegisTelegramAgent": 0.05,
    "AegisAnalystPanelDaily": 24.0, "AegisAnalystPull": 168.0, "AegisBrainRefresh": 24.0,
    "AegisPublicFlow": 24.0, "AegisResearchLane": 168.0,
}
#: "Same output for too long": a receipt series whose SUBSTANCE hash (the receipt
#: with its stamps/run ids removed) is unchanged across at least this many
#: consecutive probes AND for longer than the allowed age, with no declared idle
#: reason, is STALE even though its stamps keep moving (roadmap §7).
HEALTH_PROGRESS_SAME_HASH_PROBES = 2
#: `task_keeper analyst`: the weekly analyst-target pull (~60-80 min measured).
ANALYST_PULL_TIMEOUT_MIN = 150
#: `task_keeper brain`: `tools/refresh_aegis.py` in the sibling Optimus repo.
BRAIN_REFRESH_TIMEOUT_MIN = 60
#: `openclaw_api_bridge` is called on demand by the agent; a last call older than
#: this is reported as idle (ALIVE_IDLE_EXPECTED), never as DEAD.
OPENCLAW_BRIDGE_IDLE_DAYS = 7
#: A name with no panel sigma is priced at the universe p90; when the panel is
#: unreadable, at this (the measured universe p90 on 2026-10-05, review C2 F1).
PC_SIGMA_FALLBACK_DAILY = 0.049
#: The paper account PC-PAPER must be. A broker read from any other account is
#: skipped by the mandate (review C2 F5); override only by env when the owner
#: rotates the account on purpose.
PC_PAPER_ACCOUNT_NUMBER = os.getenv("AEGIS_PC_PAPER_ACCOUNT", "PA37CSAUFCQR")

# ── Public-flow SENSORS (chunk C16, 2026-10-07) ───────────────────────────────
#: Provenance + latency sensors, NEVER a trade signal on their own (roadmap
#: 2026-10-06 §2 item 10: dollars of contracts and lobbying are variables;
#: identity groups never are). Tables + receipts live under this directory.
PUBLIC_FLOW_DIR = OPTIMUS_LEDGER_DIR / "public_flow"
#: Hand-curated recipient/client -> ticker crosswalk (confidence per entry).
PUBLIC_FLOW_CROSSWALK = BACKEND_DIR / "data" / "crosswalks" / "usaspending_recipient_ticker.yaml"
#: USAspending: documented global limit 1,000 requests / 300 s. We pace at one
#: request per 0.5 s (<= 600 / 300 s) and cap a rolling day well below it.
USASPENDING_API_BASE = "https://api.usaspending.gov/api/v2"
USASPENDING_MIN_GAP_S = 0.5
USASPENDING_DAY_CAP = 2000
USASPENDING_PAGE_LIMIT = 100
USASPENDING_MAX_PAGES_PER_RECIPIENT = 30
#: Contracts only (A=BPA call, B=purchase order, C=delivery order, D=definitive).
USASPENDING_CONTRACT_TYPES = ("A", "B", "C", "D")
#: Review F1 (2026-10-07): the daily job pulls by LAST-MODIFIED date, not action
#: date. DoD publishes contract actions ~90 days late, so a 14-day action-date
#: window could never see them; a transaction appears in the modified window on
#: the day it is published, whatever its action date. Rows are then kept when
#: their action date is inside a rolling ACTION window (older modifications are
#: counted, not stored). `first_seen_utc` keeps its meaning.
USASPENDING_MODIFIED_LOOKBACK_DAYS = 3
USASPENDING_ACTION_WINDOW_DAYS = 120
#: Review F2: page on a sort that does not tie ("Award ID"; "Action Date" ties
#: served 2 GD rows twice and 2 never). Every recipient is reconciled against
#: `spending_by_transaction_count`; a mismatch REFUSES that recipient.
USASPENDING_SORT = "Award ID"
#: Review F6: an agency-month total is SETTLED once the fetch date is this many
#: days past the month end (DoD's ~90-day publication delay + margin).
USASPENDING_SETTLE_DAYS = {"Department of Defense": 100, "_default": 45}
#: Review F12: a recipient whose expected rows in the window (its previous-90-day
#: rate x window) are at least this many and that returns ZERO is DEGRADED; a
#: first-contact backfill of >= 60 days that returns zero is DEGRADED too.
USASPENDING_EXPECTED_ROWS_FLOOR = 5
#: Toptier awarding agencies for the monthly x agency obligation snapshots
#: (the fiscal-year-end precursor). Snapshotted per fetch day: late reports
#: REVISE a month, and the revision path is itself the latency measurement.
USASPENDING_AGENCIES = ("Department of Defense", "Department of Health and Human Services",
                        "Department of Energy", "National Aeronautics and Space Administration",
                        "Department of Homeland Security", "Department of Veterans Affairs",
                        "General Services Administration")
#: Senate LDA (lda.senate.gov -> lda.gov): anonymous tier 15 requests/min.
LDA_API_BASE = "https://lda.gov/api/v1"
LDA_MIN_GAP_S = 4.2
LDA_DAY_CAP = 600
LDA_MAX_PAGES_PER_CLIENT = 5
#: `task_keeper public_flow` runs LDA when its last receipt is this old
#: (filings are quarterly; dated by the receipt's own stamp, never mtime).
LDA_EVERY_DAYS = 7.0
#: Crypto risk-appetite sensor endpoints (public, no key, no trading).
DEFILLAMA_STABLECOINS_BASE = "https://stablecoins.llama.fi"
BINANCE_FAPI_BASE = "https://fapi.binance.com"
OKX_API_BASE = "https://www.okx.com"
#: Kalshi storage mode (owner decision D18, C16 note). Kalshi's Developer
#: Agreement is quoted as barring "collecting, caching, aggregating, or storing"
#: API data except for one's own trading (the quote is UNVERIFIED first-hand:
#: review F9), and its Data Terms bar ML/AI use. Default "none" (review F9): the
#: receipt only, until the owner decides D18, because a derived daily aggregate
#: may itself be the prohibited "aggregating". "derived_only" keeps one derived
#: aggregate per mapped regime variable; "raw" is the pre-2026-10-07 behaviour.
#: Polymarket is unaffected. Existing files are not deleted.
PREDMARKET_KALSHI_STORAGE = os.getenv("AEGIS_PREDMARKET_KALSHI_STORAGE", "none")

# ── Legibility pages (C19, 2026-10-07): Paper Arena / Forecast Lab / Theory Lab / System Health ──
#: `backend/services/legibility.py` serves the newest receipt of each kind (chosen by the
#: stamp in its NAME or its own `generated_utc`, never the file mtime) and prints its age.
#: A receipt older than this many HOURS is STALE on the page: a red banner, never hidden.
#: Each limit is the producer's cadence plus a margin, so a missed run turns the page red.
LEGIBILITY_STALE_HOURS: dict = {
    "paper_accounts_roi": 48.0,     # daily pass + the evening ROI run
    "book_dna": 48.0,               # written with the ROI receipt
    "system_health": 26.0,          # the daily pass's last step (+ manual probes)
    "forecast_reputation": 48.0,    # nightly reputation refit
    "learning_report": 48.0,        # daily learning report
    "grade_forecasts": 48.0,        # the night factory's grade step
    "nn_lab_nightly": 48.0,         # AegisNNLabNightly
    "nn_lab_walkforward": 24.0 * 14,  # an ~8 min GPU refit, run by hand after reviews
    "world_state": 24.0,            # AegisWorldDigest every 6 h
    "hyp_lab_ledger": 24.0 * 7,     # AegisHypLabNightly; the theory folds change slowly
    "twin_board": 24.0 * 30,        # CRSP boards are rerun after a construction change
    "analyst_reputation": 24.0 * 40,  # monthly receipt
    "decision_story": 48.0,         # the PC-PAPER plan writes per session
    "regret": 48.0,                 # daily pass `regret` step
    "handoff_doc": 24.0 * 14,       # the handoff the CRSP sentence is quoted from (dated by its name)
    "opportunities": 24.0 * 3,      # C15: the published Opportunity Explorer copy (OPPORTUNITIES_STALE_DAYS)
    "world_state_beliefs": 24.0,    # brain page v2: AegisWorldDigest refreshes beliefs.json every ~6h
    "world_state_scenarios": 24.0,  # written the same cycle as beliefs.json
    "belief_updates": 24.0,         # the append log for "what changed since the last cycle"
}
#: C15 (2026-10-07): `backend/services/publish_receipts.py` copies each public page's
#: sanitised payload into the TRACKED `backend/data/public_receipts/`. The whole folder
#: is refused (nothing written) when the new set would exceed this many bytes.
PUBLIC_RECEIPTS_MAX_BYTES = 5_000_000
#: FIXED TO THE IMAGE, deliberately NOT derived from `DATA_DIR` / `OPTIMUS_LEDGER_DIR`.
#:
#: Found 2026-10-07 (prod deploy e041ec14): `/openapi.json` listed the six new routes,
#: `/api/health/full` was 200, and every one of the six 404'd. `public_dir()` computed
#: this as `OPTIMUS_LEDGER_DIR.parent / "public_receipts"`, i.e. it FOLLOWED
#: `AEGIS_DATA_DIR`. Railway sets `AEGIS_DATA_DIR=/data` (the persistent volume) for the
#: exact reason documented on `DATA_DIR` above -- so the volume does not shadow the
#: image -- but that same override pointed this fallback at `/data/public_receipts`, an
#: empty path on the volume, instead of the git-tracked `backend/data/public_receipts/`
#: baked into the image at `BACKEND_DIR/data/public_receipts`. Both the live receipts
#: (also under the fresh volume) and the "fallback" were therefore reading the same
#: empty tree; the committed copy was never consulted. Same family as the "path that
#: resolves differently when frozen" lesson (CLAUDE.md): correct from source (dev has no
#: `AEGIS_DATA_DIR`, so this constant and `OPTIMUS_LEDGER_DIR.parent` were byte-identical
#: and the bug was invisible), wrong once a deploy-time env var moves one of them.
#:
#: Override ONLY for test isolation, via `AEGIS_PUBLIC_RECEIPTS_DIR` or by monkeypatching
#: this constant directly -- never let it follow `AEGIS_DATA_DIR` again.
PUBLIC_RECEIPTS_DIR = Path(os.getenv("AEGIS_PUBLIC_RECEIPTS_DIR", str(BACKEND_DIR / "data" / "public_receipts")))
#: C15 review M2: the owner's identity, scrubbed (case-insensitive) from EVERY published
#: copy and refused by the leak scan if a form survives. The name and the public GitHub
#: handle only; the e-mail local part and the home-folder name are derived at runtime
#: (`publish_receipts._runtime_owner_tokens`) so they are never written into the repo.
#: Extras: env `AEGIS_OWNER_PATTERNS` (comma-separated regexes).
OWNER_NAME_PATTERNS: tuple = (r"(?<![a-z])murat(?:han)?(?:x12)?",)
#: C15 review H1: `scripts.publish_receipts --commit` commits ONLY the public_receipts
#: folder and pushes this branch to this remote; it refuses on any other branch.
PUBLIC_RECEIPTS_BRANCH = "main"
PUBLIC_RECEIPTS_REMOTE = "origin"
#: (C8 review F8) The Railway fleet loops (aat-loop-hack*) were stopped ON PURPOSE on
#: 2026-09-29 (session S60, to hold the bill at $20). While this is non-empty the
#: `railway_fleet` probe reads STOPPED_BY_OPERATOR with this reason instead of a
#: permanent UNKNOWN; empty it when the loops are restarted.
RAILWAY_FLEET_STOPPED_REASON = ("Railway fleet loops stopped on purpose 2026-09-29 (S60: bill held at "
                                "$20; the PC runs the fleet manager instead)")

# ── C20 (2026-10-07): six-role fleet v3 PREPARED + the PC-PAPER benchmark core ──
#: D14, OWNER DECISION, default OFF. When True, `sim_run.u_plan` adds ONE target:
#: `PC_BENCHMARK_CORE_SYMBOL` at `1 - active_gross` (the acting PROBE/EXPLOIT
#: weights after the order-path gate), and the receipt grades every sleeve as
#: EXCESS over that core. It goes through `pc_broker.plan_orders` like any other
#: target, so MAX_NAME_FRAC (12%) still clips it: the flag ALONE delivers at most
#: a 12% core and says so (CORE_CLIPPED_BY_MAX_NAME_FRAC). A full core needs a
#: second, separate owner decision about that limit; no builder loosens it.
#: Flag OFF: the plan is byte-identical to the pre-C20 plan (pinned by test).
PC_BENCHMARK_CORE = False
#: SPY is an ordinary listed equity order on the Alpaca paper venue (pc_broker
#: already samples it in BENCHMARKS); no proxy ETF is needed.
PC_BENCHMARK_CORE_SYMBOL = "SPY"
#: The six-role v3 fleet contracts are written HERE, never into
#: `fleet_manager/contracts/`: no seed path reads this folder, and
#: `fleet_manager.load_contract`/`freeze_contract` refuse a PREPARED body.
FLEET_V3_CONTRACTS_DIR = OPTIMUS_LEDGER_DIR / "paper_accounts" / "fleet_manager" / "contracts_v3"
FLEET_V3_STATUS_PREPARED = "PREPARED_NOT_SEEDED"
#: The equity every v3 worst case is printed at (session protocol item 4).
FLEET_V3_WORST_CASE_EQUITY = 100_000.0
#: A v3 book's one-day k-sigma loss (rho = 1 across names) may not exceed this
#: fraction of equity: over it, gross is scaled DOWN at entry (never a cap raised).
FLEET_V3_MAX_K_SIGMA_DAY_LOSS_FRAC = 0.10
#: No new paper book before this date (roadmap 2026-10-06 §7 "measure before you add").
FLEET_V3_EARLIEST_SEED = "2026-10-26"
