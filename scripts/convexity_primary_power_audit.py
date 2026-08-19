"""§64 power audit for CONVEXITY-PRESERVATION-1's EXACT primary cell.

    python -m scripts.convexity_primary_power_audit

Amendment 1 repair: the registered MDE (0.0045) was measured on the
trim_25-vs-hold contrast with month-sized blocks. An answerability
declaration must be measured on the arm it declares — trail_stop_20 vs
hold at +40 — under the dependence structure the trial will actually use
(blocks spanning the 60-trading-day outcome overlap, derived from the
panel's own crossing-date spacing).

MEAN-MASKED by construction: this audit reports dispersion only (SE, MDE,
block structure). The mean of the primary contrast is never printed,
never persisted, never returned — the first read of that number is the
registered run itself.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config                        # noqa: E402
from backend.services.convexity_episodes import OUTCOME_DAYS  # noqa: E402
from backend.services.net_tournament import (                # noqa: E402
    bootstrap_block_dates)
from backend.services.world_model import (                   # noqa: E402
    block_bootstrap_paired)

EPISODES = _config.OPTIMUS_LEDGER_DIR / "convexity" / "episodes_v2.parquet"
OUT = _config.OPTIMUS_LEDGER_DIR / "convexity"


def main() -> int:
    df = pd.read_parquet(EPISODES)
    prim = df[df["threshold"] == 0.4]
    d = (prim["tw_trail_stop_20"] - prim["tw_hold"]).to_numpy(float)
    dates = pd.to_datetime(prim["crossing_date"]).to_numpy(
        dtype="datetime64[D]")
    uniq = np.unique(dates)
    block = bootstrap_block_dates(dates, OUTCOME_DAYS)
    inf = block_bootstrap_paired(d, dates, block_days=block,
                                 seed=20260819).as_dict()
    # MASK: dispersion only. 2.8 sigma = one-sided alpha .05 / power .80.
    receipt = {
        "audit": "CONVEXITY-PRIMARY-POWER-1 (mean-masked)",
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cell": "trail_stop_20 vs hold @ +40, 60-trading-day outcome",
        "n_episodes": int(len(prim)),
        "n_unique_crossing_dates": int(uniq.size),
        "block_days_derived": int(block),
        "n_effective_blocks": int(np.ceil(uniq.size / block)),
        "bootstrap_se": round(float(inf["se"]), 6),
        "mde_80pct_power": round(float(inf["mde_80pct_power"]), 6),
        "economic_margin": 0.005,
        "answerable_at_margin": bool(inf["mde_80pct_power"] <= 0.005),
    }
    p = OUT / "primary_power_audit_2026-08-19.json"
    p.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    for k, v in receipt.items():
        print(f"  {k}: {v}")
    print(f"receipt: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
