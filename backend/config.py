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
    "deepseek-flash": {"in": 0.169413, "cached_in": 0.00338826, "out": 1.284835},
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
}

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
)

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
