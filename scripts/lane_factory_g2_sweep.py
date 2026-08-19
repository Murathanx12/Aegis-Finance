"""LANE-FACTORY-SIM-1 first sweep — the G2 candidates' historical twins.

    python -m scripts.lane_factory_g2_sweep

Four books on the real PIT panel (2014-06..2024-11, costs, delistings):
{equal, inverse_vol} x {trim, exempt}. Outputs the paired monthly
contrasts the G2 preregs need for their §64 power notes:
  - exempt - trim   (within each weighting)  [convexity transport]
  - inverse_vol - equal (within each handling) [risk-sizing transport]
Paired same-month differences with date-block bootstrap (§58; block from
panel spacing over the 21-day formation overlap).

SIMULATION receipts only; SCREEN discipline — nothing here decides a
lane launch, it powers the preregs that will.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config                        # noqa: E402
from backend.services.lane_factory_sim import (load_panel,   # noqa: E402
                                               run_book)
from backend.services.net_tournament import (                # noqa: E402
    bootstrap_block_dates)
from backend.services.world_model import (                   # noqa: E402
    block_bootstrap_paired)

OUT = _config.OPTIMUS_LEDGER_DIR / "lane_factory"


def paired(a: pd.Series, b: pd.Series) -> dict:
    ix = a.index.intersection(b.index)
    d = (a.loc[ix] - b.loc[ix]).to_numpy(float)
    dates = ix.to_numpy(dtype="datetime64[D]")
    block = bootstrap_block_dates(dates, 21)
    inf = block_bootstrap_paired(d, dates, block_days=block,
                                 seed=20260819).as_dict()
    inf["block_days_derived"] = block
    inf["ann_mean_diff"] = round(float(np.mean(d) * 12), 5)
    return inf


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass
    print("loading panel...")
    panel = load_panel()
    books = {}
    for wgt, hand in product(("equal", "inverse_vol"), ("trim", "exempt")):
        key = f"{wgt}|{hand}"
        print(f"running {key} ...")
        books[key] = run_book(panel, weighting=wgt, winner_handling=hand)
        b = books[key]
        print(f"  total {b['total_return']:+.3f}  vol {b['ann_vol']:.3f}  "
              f"maxDD {b['max_drawdown']:.3f}  cost {b['cost_paid_frac']:.4f}"
              f"  delist_exits {b['n_delist_exits']}"
              f"  exemptions {b['n_winner_exemptions']}")

    contrasts = {
        "exempt_minus_trim@equal": paired(
            books["equal|exempt"]["monthly_returns"],
            books["equal|trim"]["monthly_returns"]),
        "exempt_minus_trim@inverse_vol": paired(
            books["inverse_vol|exempt"]["monthly_returns"],
            books["inverse_vol|trim"]["monthly_returns"]),
        "inverse_vol_minus_equal@trim": paired(
            books["inverse_vol|trim"]["monthly_returns"],
            books["equal|trim"]["monthly_returns"]),
        "inverse_vol_minus_equal@exempt": paired(
            books["inverse_vol|exempt"]["monthly_returns"],
            books["equal|exempt"]["monthly_returns"]),
    }
    # the §59 risk view — the readable one at this n
    risk = {k: {"ann_vol": b["ann_vol"], "max_drawdown": b["max_drawdown"],
                "turnover": b["turnover_oneway_total"],
                "cost_paid_frac": b["cost_paid_frac"]}
            for k, b in books.items()}

    receipt = {
        "sweep": "LANE-FACTORY-G2-SWEEP-1 (SIMULATION, SCREEN)",
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "grid": sorted(books),
        "window": "2014-06-30..2024-11-30",
        "cost_basis": "flat 3bp one-way (declared v1)",
        "summary": {k: {kk: vv for kk, vv in b.items()
                        if kk not in ("monthly_returns", "nav")}
                    for k, b in books.items()},
        "paired_contrasts_monthly": contrasts,
        "risk_view": risk,
        "purpose": ("§64 power basis for the G2 lane preregs; nothing "
                    "here is a verdict"),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / "g2_sweep_2026-08-19.json"
    p.write_text(json.dumps(receipt, indent=2, default=str),
                 encoding="utf-8")
    for k, c in contrasts.items():
        print(f"  {k:<34} mean/mo {c['mean']:+.5f}  "
              f"ann {c['ann_mean_diff']:+.4f}  mde/mo "
              f"{c['mde_80pct_power']:.5f}  blocks~{c['n_effective']:.0f}")
    print(f"receipt: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
