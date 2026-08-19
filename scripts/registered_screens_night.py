"""Registered SCREEN grids for the two signed 08-19 trials.

    python -m scripts.registered_screens_night

FACTOR-MOMENTUM-1 screen (prereg §SCREEN): formation 1/3/6/12 months ×
top tercile/quintile. Theme-level cells: NOT RUN (no theme mapping in
the downloaded series) — reported missing, never silently re-specified.

STREAK-EVIDENCE-1 screen (prereg §SCREEN): up-streak lengths 5/10 and
down-streak length 7. Volume-confirmed cells: NOT RUN (volume not in
the loaded panel columns) — reported missing.

All cells BH-FDR 0.10 with m = cells RUN, per §63 SCREEN discipline.
"""

from __future__ import annotations

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
from backend.services import factor_momentum as FM           # noqa: E402
from backend.services import streak_evidence as SE           # noqa: E402
from backend.services.lane_factory_sim import (Panel,        # noqa: E402
                                               load_panel)
from backend.services.net_tournament import (                # noqa: E402
    bootstrap_block_dates)
from backend.services.world_model import (                   # noqa: E402
    block_bootstrap_paired)


def _p_from(inf) -> float:
    z = inf["mean"] / inf["se"] if inf["se"] > 0 else 0.0
    return 2 * (1 - 0.5 * (1 + erf(abs(z) / sqrt(2))))


def fm_screen() -> list[dict]:
    wide = FM.load_jkp()
    out = []
    for formation in (1, 3, 6, 12):
        for frac, fname in ((1 / 3, "tercile"), (1 / 5, "quintile")):
            if formation == 12 and fname == "tercile":
                continue      # the registered primary, already reported
            books = FM.build_books(wide, formation=formation,
                                   top_fraction=frac)
            c = FM.paired_contrast(books)
            out.append({"cell": f"form{formation}_{fname}",
                        "ann_diff": round(c["ann_mean_diff"], 5),
                        "p": round(_p_from(c), 5),
                        "n_months": int(len(books))})
    return out


def streak_screen(panel: Panel) -> list[dict]:
    out = []
    for label, kwargs in (
            ("up5", {"streak_len": 5}),
            ("up10", {"streak_len": 10}),
    ):
        ev = SE.build_events(panel, **kwargs)
        if len(ev) < 50:
            out.append({"cell": label, "note": f"only {len(ev)} events"})
            continue
        d = (ev["fwd_event"] - ev["fwd_control"]).to_numpy(float)
        dates = pd.to_datetime(ev["date"]).to_numpy(dtype="datetime64[D]")
        inf = block_bootstrap_paired(
            d, dates, block_days=bootstrap_block_dates(dates, 21),
            seed=20260819).as_dict()
        out.append({"cell": label, "n_events": int(len(ev)),
                    "diff_21d": round(inf["mean"], 5),
                    "p": round(_p_from(inf), 5)})
    # down-streak 7: negate returns, reuse the machinery verbatim
    neg = Panel(px=panel.px, ret=-panel.ret,
                elig_by_month=panel.elig_by_month, dlret=panel.dlret,
                last_day=panel.last_day)
    ev = SE.build_events(neg, streak_len=7)
    if len(ev) >= 50:
        # forward returns computed on the NEGATED panel are negated
        d = -(ev["fwd_event"] - ev["fwd_control"]).to_numpy(float)
        dates = pd.to_datetime(ev["date"]).to_numpy(dtype="datetime64[D]")
        inf = block_bootstrap_paired(
            d, dates, block_days=bootstrap_block_dates(dates, 21),
            seed=20260819).as_dict()
        out.append({"cell": "down7", "n_events": int(len(ev)),
                    "diff_21d": round(-inf["mean"], 5),
                    "p": round(_p_from(inf), 5),
                    "note": "sign convention: event-minus-control on the "
                            "REAL forward return"})
    else:
        out.append({"cell": "down7", "note": f"only {len(ev)} events"})
    return out


def bh(cells: list[dict], q: float = 0.10) -> list[str]:
    scored = [c for c in cells if "p" in c]
    ranked = sorted(scored, key=lambda c: c["p"])
    m = len(scored)
    passed = []
    for i, c in enumerate(ranked, start=1):
        if c["p"] <= q * i / m:
            passed = [x["cell"] for x in ranked[:i]]
    return passed


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass
    fm = fm_screen()
    print("FM screen:", json.dumps(fm))
    panel = load_panel()
    st = streak_screen(panel)
    print("Streak screen:", json.dumps(st))
    receipt = {
        "screens": "registered SCREEN grids, 2026-08-19 night",
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "factor_momentum": {"cells": fm, "bh_fdr_survivors": bh(fm),
                            "not_run": ["theme-level (no theme mapping "
                                        "in downloaded series)"]},
        "streak": {"cells": st, "bh_fdr_survivors": bh(st),
                   "not_run": ["volume-confirmed (volume not loaded)"]},
        "discipline": "SCREEN §63; survivors are leads, never verdicts",
    }
    p = (_config.OPTIMUS_LEDGER_DIR / "research_daemon" /
         "registered_screens_2026-08-19.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print("receipt:", p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
