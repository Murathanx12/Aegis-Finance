"""ft_lab configuration. Every parameter of the first run lives here."""
from __future__ import annotations

from pathlib import Path

LAB = Path(__file__).resolve().parent
REPO = LAB.parent
DATA_ROOT = REPO / "backend" / "data" / "optimus"

PANEL = DATA_ROOT / "text_return_panel" / "news_returns_2025_26.parquet"
BARS = DATA_ROOT / "prices_deep" / "bars.parquet"
TEACHER = DATA_ROOT / "typed_events" / "panel_2026-09-13.jsonl"

WORK = LAB / "data"          # derived tables (gitignored)
MODELS = LAB / "models"      # downloaded + fine-tuned weights (gitignored)
RUNS = LAB / "runs"          # logs, checkpoints (gitignored)
RECEIPTS = DATA_ROOT / "ft_lab" / "receipts"   # small JSON receipts (tracked)

LICENCE = "PRODUCT_EXPERIMENT"

# ---- time split (entry_date, inclusive bounds). Train oldest, test newest. ----
# Embargo: >= EMBARGO_SESSIONS trading sessions between the end of one block and the start
# of the next. The target is a one-session move, so 10 sessions is generous; it also keeps
# a re-sent wire story from straddling the boundary on consecutive days.
SPLITS = {
    "train": ("2025-01-02", "2025-12-31"),
    "val": ("2026-01-16", "2026-04-30"),
    "test": ("2026-05-15", "2026-09-28"),
}
EMBARGO_SESSIONS = 10

# ---- target ----
TARGET = "x_oc"   # open-to-close of the first session whose OPEN is after publication, minus SPY
EPS = 1e-4
# the typed-event vocabulary's own magnitude thresholds (|move|), so DeepSeek's
# magnitude_bucket can be graded against the realised bucket without a mapping
MAG_EDGES = [0.0, 0.005, 0.02, 0.05, 0.10, float("inf")]
MAG_NAMES = ["NEGLIGIBLE", "SMALL", "MODERATE", "LARGE", "EXTREME"]

VOL_WINDOW = 21
TEXT_CHARS = 1200         # first document: title + body truncated
OTHER_TITLES = 3          # plus up to three more headlines from the same cell

# ---- models ----
EXTRACT_BASE = "Qwen/Qwen2.5-1.5B-Instruct"
SIZE_BASE = "Qwen/Qwen2.5-0.5B-Instruct"
SEED = 20260929

# ---- machine safety ----
VRAM_FRACTION = 0.78          # torch per-process cap; the card is shared
TRAIN_TIME_BOX_MIN = 90       # total awake training minutes across both fine-tunes
MIN_FREE_RAM_GB = 3.0          # required to START a GPU stage
# DEVIATION, stated: with other agents running, this machine had only 2.7-4.8 GB available
# BEFORE any ft_lab process started, and a CUDA torch process holds ~1.3 GB steady-state after
# a working-set trim. A 3 GB floor held DURING the run could never be met, so mid-run the job
# PAUSES (trims its own working set to ~0 and waits) whenever available RAM < 2.0 GB, and
# refuses after 15 minutes of pausing. Measured 2026-09-29 and recorded in the run notes.
RUN_FLOOR_RAM_GB = 2.0
CHECKPOINT_EVERY = 200        # optimizer steps

# ---- DeepSeek (the only paid provider) ----
DEEPSEEK_CAP_USD = 0.90
# conservative own bill: the PEAK list price of deepseek-v4-flash (per 1M tokens),
# so the cap binds even if the ledger prices a served model at $0
DEEPSEEK_PRICE_IN = 0.30
DEEPSEEK_PRICE_OUT = 1.20
