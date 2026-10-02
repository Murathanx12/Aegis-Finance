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
# Amended 2026-09-29 (REVIEW_2026-09-29_SHADOW_BOOK_AND_TRUST_WEIGHTS F1): DIRECTION trust is
# earned from FORWARD graded blocks only. The walk-forward receipt is printed beside it and
# never enters it (it had made every weight a ratio of backtest ICs that moved whenever a
# new wf_*.json appeared). The ensemble weight is a SCALE, not a share:
#   weight_m = max(0, trust_m) / TRUST_FULL_IC, the rest goes to the neutral (no-view) sleeve;
# weights are scaled down only if they would sum above 1. With no forward grade every trust
# is its prior mean 0, every weight is 0 and the ensemble is the zero.
TRUST_FULL_IC = 0.05       # posterior rank IC at which one model alone would carry the whole ensemble
MAG_TOLERANCE = 0.01       # the simplest magnitude model within this of the best is used
CONFORMAL_MIN_ROWS = 500   # graded rows needed before forward coverage replaces walk-forward coverage

# ---- 2026-09-30 night (JOB4): universe hygiene + size members -----------------------
# F3: deaths the inactive-asset list never listed, recovered from CRSP (nn_lab/deaths_crsp.py).
BARS_DELISTED_CRSP = OPTIMUS / "prices_deep" / "bars_delisted_crsp.parquet"
USE_CRSP_DEATHS = True            # table.build reads the file when it exists
# F3: a dead company whose ticker a later company reuses becomes `SYM#d` (its own dead name)
# instead of being dropped, when its bars end before the living company's first bar.
RENAME_REUSED_DEAD = True
# Universe: ETFs / ETNs / funds are not companies; their structural decay is free "skill".
ETF_EXCLUSIONS = OUT / "universe_meta" / "etf_exclusions.json"
EXCLUDE_ETFS = True               # price_rows skips every symbol in ETF_EXCLUSIONS
# Size members (nn_lab/size_members.py): the earnings-cadence prior and the TF-IDF text member
# are frozen and graded nightly as MAGNITUDE models; they earn weight only through forward
# graded blocks (prior 0). Off = the roster is exactly MAGNITUDE_ROSTER above.
SIZE_MEMBERS_NIGHTLY = True    # ON 2026-09-30: the earnings-cadence member, frozen + graded; weight only from forward blocks
SIZE_MEMBER_ROSTER = ("vol_earn",)   # vol_text measured NEGATIVE at h5/h21 (size_20260929T141548Z); available, not rostered
if SIZE_MEMBERS_NIGHTLY:
    # frozen, graded and trusted exactly like the other magnitude models (forward blocks only)
    MAGNITUDE_ROSTER = MAGNITUDE_ROSTER + tuple(m for m in SIZE_MEMBER_ROSTER if m not in MAGNITUDE_ROSTER)
# F1 remedy (nn_lab/raw_prices.py): close_raw from monthly RAW bars; OFF until the nightly has a
# monthly raw refresh (a live row without close_raw would differ from its training rows).
USE_CLOSE_RAW = False
