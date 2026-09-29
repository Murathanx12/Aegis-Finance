"""Every constant nn_lab uses, in one place. Paths resolve from the repo root."""
from __future__ import annotations

import os
from pathlib import Path

REPO = Path(os.environ.get("AEGIS_REPO_ROOT", Path(__file__).resolve().parent.parent))
OPTIMUS = REPO / "backend" / "data" / "optimus"

# ---- inputs (read-only) ----------------------------------------------------
BARS_DEEP = OPTIMUS / "prices_deep" / "bars.parquet"              # 2016-> living names (selected 2026-09-01)
BARS_DELISTED = OPTIMUS / "prices_deep" / "bars_delisted.parquet"  # 1,784 inactive listed names
BARS_RECENT = OPTIMUS / "prices_2025_26" / "bars.parquet"          # refreshed nightly by pull_bars_refresh
SEC_FACTS = OPTIMUS / "fundamentals_sec" / "sec_facts_history.parquet"
ANALYST_REVISIONS = OPTIMUS / "analyst" / "target_revisions.parquet"
NEWS_PANEL = OPTIMUS / "text_return_panel" / "news_returns_2025_26.parquet"
FORECAST_LEDGER = OPTIMUS / "predictions.jsonl"

# ---- outputs ----------------------------------------------------------------
OUT = OPTIMUS / "nn_lab"
TABLE_DIR = OUT / "table"            # gitignored (large)
MODEL_DIR = OUT / "models"           # gitignored (checkpoints)
PRED_DIR = OUT / "predictions"       # gitignored (grows nightly); sha256 of each file is in the tracked receipt
RECEIPT_DIR = OUT / "receipts"       # TRACKED
LOCAL_PC = OPTIMUS / "local_pc" / "nn_lab"   # gitignored machine records (logs, pids)
TABLE_PATH = TABLE_DIR / "train_table.parquet"
SEEDS_LEDGER = OUT / "seeds_used.jsonl"      # tracked, tiny
GRADES_LEDGER = OUT / "grades.jsonl"         # tracked-able; small
INCUMBENT_PTR = MODEL_DIR / "incumbent.json"   # the 2026-09-28 pointer; read by nothing since 09-29
STOP_FILE = OUT / "STOP"

# ---- panel construction ------------------------------------------------------
HORIZONS = (5, 21, 63)
GRID_STEP = 5                 # one decision date every 5 sessions (weekly) in the training table
MIN_PRICE = 3.0   # applied ONLY to an unadjusted close (`close_raw`); none is on disk (review F1)
MIN_MEDIAN_DOLLAR_VOL = 3_000_000.0   # same floor as xs_ranker / the universe pull
MIN_HISTORY_SESSIONS = 126
INDEX_PROXIES = frozenset({"SPY", "QQQ", "IWM", "RSP", "DIA", "VTI", "VOO"})
MARKET = "SPY"
DEAD_GAP_SESSIONS = 10        # a series ending this many sessions before the panel end is a delisting

# Round-trip cost in bps by liquidity band: the library's band costs, copied
# from backend/services/xs_ranker.COST_BPS_BY_BAND (2026-09-12 cost curve) so
# that nn_lab does not import the live path.
COST_BPS_BY_BAND = {"mega": 6.0, "large": 10.0, "mid": 18.0, "small": 35.0}

# A feature group whose non-null share of TRAINING rows is below this is not fed
# to any model (it is still built and its coverage printed).
MIN_GROUP_COVERAGE = 0.02

# ---- walk-forward -----------------------------------------------------------
TEST_YEARS = (2020, 2021, 2022, 2023, 2024, 2025, 2026)
VAL_GRID_DATES = 26                   # ~6 months of weekly decision dates
EMBARGO_SESSIONS = max(HORIZONS)      # 63: one longest horizon between train/val and val/test
TOP_K = 20

# ---- nightly ----------------------------------------------------------------
# (PROMOTION_MARGIN_IC / PROMOTION_BRIER_SLACK retired 2026-09-29: promotion on a validation
# block was a coin flip, review F5. The model in charge now changes only on graded forward
# evidence: IN_CHARGE_MARGIN below, nn_lab/loop.py.)
MIN_FREE_DISK_GB = 5.0
MIN_FREE_RAM_GB = 1.5
NIGHT_TIME_BOX_MIN = 90

# ---- review 2026-09-29 (F1 / F2) -------------------------------------------------
# F1: `close` in every bar file is split- AND dividend-adjusted (adjustment=all), so
# close x as-filed shares is scaled by every FUTURE split (VAL-01). Market cap and the
# three yields are computed ONLY from an unadjusted close (`close_raw`); a row without
# one gets NaN (missing, never zero). The $3 floor likewise needs `close_raw`; without
# it only the dollar-volume floor applies (adjusted close x adjusted volume is the
# unadjusted dollar volume: splits cancel).
MCAP_FEATURES = ("f_log_mcap", "f_ey", "f_sy", "f_bm")
# F2: how each feature group's COVERAGE was decided. A group decided by a LATER PULL
# (a 2026 snapshot that can only list names alive then) gets no missing-indicator, and
# a SNAPSHOT group is unavailable for ALL names before its first point-in-time pull.
GROUP_COVERAGE = {
    "price": "AT_THE_TIME",            # bars <= t
    "fund": "LATER_PULL_ARCHIVAL",     # 2026 pull of EDGAR's archive; dead names covered (measured 100% vs 99.4%)
    "analyst": "LATER_PULL_SNAPSHOT",  # 2026 yfinance snapshot: covers names alive in 2026 only (dead 0% vs 87-97%)
    "news": "LATER_PULL_ARCHIVAL",     # 2025-26 panel; dead 93.4% vs living 94.2% in 2025
    "ledger": "AT_THE_TIME",           # forecasts appended as they were made
}
ANALYST_PULL_GLOB = "analyst_pull_20??-??-??.json"   # the first one dates the snapshot's PIT start

# ---- the learning loop (review 2026-09-29 F5 / item 8) -------------------------
FROZEN_DIR = OUT / "frozen"                  # gitignored: one immutable parquet per (decision date, model)
FROZEN_LEDGER = OUT / "frozen_ledger.jsonl"  # TRACKED: sha256 of every frozen file, append-only
OUTCOMES_DIR = OUT / "outcomes"              # gitignored: realised excess per (decision date, horizon)
FORWARD_GRADES = OUT / "forward_grades.jsonl"  # TRACKED: one row per (model, decision date, horizon), append-only
TRUST_LEDGER = OUT / "trust.jsonl"           # TRACKED: one row per night, every model's trust
IN_CHARGE = OUT / "in_charge.json"
SIZE_DIR = OUT / "size_forecast"             # one file per night for the contest desk / sizing rule
DIRECTION_ROSTER = ("nn", "lgbm", "ridge", "mom_12_1", "zero")
MAGNITUDE_ROSTER = ("trailing_vol", "ridge_abs", "nn_width")   # ordered simplest first
MAGNITUDE_HORIZONS = (5, 21)
# Trust = posterior mean of a model's per-block rank IC. Prior N(0, TRUST_PRIOR_SD^2);
# a block is max(h, 21) sessions (blocks share almost no forward window), per-block IC
# noise sd TRUST_BLOCK_SD (walk-forward: NN SE 0.0109 x sqrt(80 blocks) = 0.097).
# Prior strength k = (0.10 / 0.03)^2 = 11.1 blocks: 1 block -> 8% of its mean, 11 -> 50%,
# 44 -> 80%. Walk-forward blocks count WF_BLOCK_WEIGHT each, fading to 0 as forward blocks
# reach k (they are in-sample for the design choices and pre-date the fixes).
TRUST_PRIOR_SD = 0.03
TRUST_BLOCK_SD = 0.10
WF_BLOCK_WEIGHT = 0.10
IN_CHARGE_MARGIN = 0.002   # a rival replaces the model in charge only by this much posterior IC
MAG_TOLERANCE = 0.01       # the simplest magnitude model within this of the best is used
CONFORMAL_MIN_ROWS = 500   # graded rows needed before forward coverage replaces walk-forward coverage
