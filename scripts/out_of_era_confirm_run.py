"""OUT-OF-ERA-CONFIRM-1 runner — the frozen m=4 cells on 1990–2012.

    python -m scripts.out_of_era_confirm_run --audit   # masked §64 only
    python -m scripts.out_of_era_confirm_run           # audits + verdicts

Protocol: docs/TRIALS/PREREG_OUT_OF_ERA_CONFIRM_1.md (frozen while the
pull was in flight). Verdict per cell, Holm FWER 0.05 across m=4:
  CONFIRMED        declared-sign mean >= run-time MDE and Holm-passes
  ANTI_CONFIRMED   opposite-sign |mean| >= MDE and Holm-passes
  NOT_ESTABLISHED  everything else (underpowered licenses nothing)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from math import erf, sqrt
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config                        # noqa: E402
from backend.services import streak_evidence as SE           # noqa: E402
from backend.services.lane_factory_sim import (load_panel,   # noqa: E402
                                               prepare_extras, run_book)
from backend.services.net_tournament import (assert_signed,  # noqa: E402
                                             bootstrap_block_dates)
from backend.services.world_model import (                   # noqa: E402
    block_bootstrap_paired)

PREREG = REPO / "docs" / "TRIALS" / "PREREG_OUT_OF_ERA_CONFIRM_1.md"
OUT = _config.OPTIMUS_LEDGER_DIR / "lane_factory"
PIT_DIR = _config.OPTIMUS_LEDGER_DIR / "crsp_pit"
WRDS_DIR = _config.OPTIMUS_LEDGER_DIR / "wrds"
START, END = "1991-06-30", "2012-11-30"

#: (cell, declared_sign, economic bar per unit of the cell's contrast)
CELLS = (("mom63_book", -1, 0.005 / 12),
         ("value_exempt_book", +1, 0.005 / 12),
         ("streak_up7", -1, 0.0025),
         ("streak_up5", -1, 0.0025))


def _inf(d, dates, horizon):
    block = bootstrap_block_dates(dates, horizon)
    out = block_bootstrap_paired(d, dates, block_days=block,
                                 seed=20260819).as_dict()
    out["block_days_derived"] = block
    return out


def contrasts() -> dict:
    panel = load_panel(years=(1990, 2012),
                       univ_path=PIT_DIR / "crsp_pit_monthly_early.parquet")
    extras = prepare_extras(
        panel, finratio_path=WRDS_DIR / "finratio_monthly_early.parquet")
    out = {}

    base = {h: run_book(panel, signal="none", weighting="equal",
                        winner_handling=h, top_n=None,
                        start=START, end=END)["monthly_returns"]
            for h in ("trim", "exempt")}
    for cell, sig, wgt, hand in (
            ("mom63_book", "mom_63", "rank", "trim"),
            ("value_exempt_book", "value_bm", "inverse_vol", "exempt")):
        b = run_book(panel, signal=sig, weighting=wgt,
                     winner_handling=hand, top_n=50,
                     start=START, end=END, extras=extras)
        mret, bl = b["monthly_returns"], base[hand]
        ix = mret.index.intersection(bl.index)
        d = (mret.loc[ix] - bl.loc[ix]).to_numpy(float)
        out[cell] = _inf(d, ix.to_numpy(dtype="datetime64[D]"), 21)
        out[cell]["ann_diff"] = round(float(np.mean(d) * 12), 5)
        out[cell]["book_risk"] = {k: b[k] for k in
                                  ("ann_vol", "max_drawdown",
                                   "n_delist_exits",
                                   "n_winner_exemptions")}

    for cell, ln in (("streak_up7", 7), ("streak_up5", 5)):
        ev = SE.build_events(panel, streak_len=ln)
        d = (ev["fwd_event"] - ev["fwd_control"]).to_numpy(float)
        dates = pd.to_datetime(ev["date"]).to_numpy(dtype="datetime64[D]")
        out[cell] = _inf(d, dates, 21)
        out[cell]["n_events"] = int(len(ev))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="out_of_era_confirm_run")
    ap.add_argument("--audit", action="store_true")
    a = ap.parse_args(argv)
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass
    signer = assert_signed(PREREG)
    print("signed by:", signer[:40])
    C = contrasts()

    audit = {c: {"se": round(C[c]["se"], 6),
                 "mde": round(C[c]["mde_80pct_power"], 6),
                 "n_effective": C[c]["n_effective"],
                 "block_days": C[c]["block_days_derived"],
                 "bar": bar, "declared_sign": sign,
                 "informative_limb_answerable": True,
                 "equivalence_limb_answerable":
                     bool(C[c]["mde_80pct_power"] <= bar)}
             for c, sign, bar in CELLS}
    ap_path = OUT / "out_of_era_audit_2026-08-19.json"
    ap_path.write_text(json.dumps(
        {"audit": "OUT-OF-ERA §64 (means masked in this file)",
         "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
         "cells": audit}, indent=2), encoding="utf-8")
    print(json.dumps(audit, indent=2))
    if a.audit:
        print("audit only — no verdicts read")
        return 0

    # Holm across the m=4 declared cells, two-sided p
    ps = {}
    for c, _s, _b in CELLS:
        z = C[c]["mean"] / C[c]["se"] if C[c]["se"] > 0 else 0.0
        ps[c] = 2 * (1 - 0.5 * (1 + erf(abs(z) / sqrt(2))))
    order = sorted(ps, key=ps.get)
    holm = {}
    for rank, c in enumerate(order):
        alpha = 0.05 / (len(order) - rank)
        if ps[c] <= alpha:
            holm[c] = True
        else:
            for cc in order[rank:]:
                holm[cc] = False
            break

    verdicts = {}
    for c, sign, bar in CELLS:
        mean, mde = C[c]["mean"], C[c]["mde_80pct_power"]
        if np.sign(mean) == sign and abs(mean) >= mde and holm.get(c):
            v = "CONFIRMED"
        elif np.sign(mean) == -sign and abs(mean) >= mde and holm.get(c):
            v = "ANTI_CONFIRMED"
        else:
            v = "NOT_ESTABLISHED"
        verdicts[c] = {"verdict": v, "mean": round(C[c]["mean"], 6),
                       "mde": round(mde, 6), "p": round(ps[c], 5),
                       "holm_pass": bool(holm.get(c)),
                       "declared_sign": sign}
        extra = C[c].get("ann_diff")
        tail = f"  ann {extra:+.4f}" if extra is not None else ""
        print(f"  {c:<20} {v:<16} mean {C[c]['mean']:+.5f}  "
              f"mde {mde:.5f}  p {ps[c]:.4f}{tail}")

    receipt = {"trial": "OUT-OF-ERA-CONFIRM-1", "mode": "REGISTERED",
               "signed_by": signer,
               "at": datetime.now(timezone.utc).isoformat(
                   timespec="seconds"),
               "era": [START, END], "m": len(CELLS),
               "verdicts": verdicts, "contrasts": C,
               "scope_note": "nominal screen drift disclosed (frozen "
                             "cuts are stricter in real terms in 1990)"}
    p = OUT / "out_of_era_trial_2026-08-19.json"
    p.write_text(json.dumps(receipt, indent=2, default=str),
                 encoding="utf-8")
    print("receipt:", p.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
