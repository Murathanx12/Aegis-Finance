"""MANAGER-BEHAVIOR-LIBRARY-1 substrate — quarterly action states.

    python -m scripts.manager_actions_build

Construction only (no verdicts, no skill claims): for every
(manager, stock) across consecutive report quarters, classify
INITIATE / ADD / HOLD / TRIM / EXIT from share counts, then aggregate
per manager-quarter. PIT note carried from the pull: `fdate` is the
knowledge date; `rdate` (the described quarter) orders transitions but
may never be used as knowledge time by any downstream feature.

Thresholds are DECLARED here, prospectively: ADD/TRIM = share change
beyond ±10% (split-safe only approximately — share splits inflate
ADD/TRIM counts; the split-adjusted v2 needs cfacshr joined and is
recorded as a known limitation, not silently absorbed).
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

WRDS = _config.OPTIMUS_LEDGER_DIR / "wrds"
OUT = _config.OPTIMUS_LEDGER_DIR / "teacher_library"
THRESH = 0.10


def quarter_frames():
    frames: dict[pd.Period, list] = {}
    for yr in range(2013, 2025):
        p = WRDS / f"tr13f_s34_{yr}.parquet"
        if not p.exists():
            continue
        df = pd.read_parquet(p, columns=["rdate", "mgrno", "cusip",
                                         "shares"])
        df["q"] = pd.to_datetime(df["rdate"]).dt.to_period("Q")
        for q, g in df.groupby("q"):
            frames.setdefault(q, []).append(
                g[["mgrno", "cusip", "shares"]])
    return {q: pd.concat(v, ignore_index=True)
            .groupby(["mgrno", "cusip"], as_index=False)["shares"].last()
            for q, v in frames.items()}


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass
    print("loading quarter frames...")
    QF = quarter_frames()
    quarters = sorted(QF)
    print(f"{len(quarters)} quarters, "
          f"{quarters[0]}..{quarters[-1]}")
    rows = []
    for prev_q, q in zip(quarters, quarters[1:]):
        a = QF[prev_q].rename(columns={"shares": "sh0"})
        b = QF[q].rename(columns={"shares": "sh1"})
        m = a.merge(b, on=["mgrno", "cusip"], how="outer")
        chg = (m["sh1"] - m["sh0"]) / m["sh0"].replace(0, np.nan)
        m["action"] = np.select(
            [m["sh0"].isna(), m["sh1"].isna(),
             chg > THRESH, chg < -THRESH],
            ["INITIATE", "EXIT", "ADD", "TRIM"], default="HOLD")
        agg = (m.groupby(["mgrno", "action"]).size()
               .unstack(fill_value=0).reset_index())
        agg["q"] = str(q)
        rows.append(agg)
        if q.quarter == 4:
            print(f"  through {q}: {sum(len(r) for r in rows):,} "
                  "mgr-quarter rows")
    out = pd.concat(rows, ignore_index=True).fillna(0)
    for c in ("INITIATE", "ADD", "HOLD", "TRIM", "EXIT"):
        if c not in out:
            out[c] = 0
        out[c] = out[c].astype(int)
    out["n_positions"] = out[["ADD", "HOLD", "TRIM"]].sum(axis=1) \
        + out["EXIT"]
    OUT.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT / "manager_actions_quarterly_v1.parquet",
                   index=False)
    meta = {"dataset": "manager_actions_quarterly_v1 (construction)",
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "rows": int(len(out)),
            "n_managers": int(out["mgrno"].nunique()),
            "quarters": [str(quarters[0]), str(quarters[-1])],
            "thresholds": {"add_trim": THRESH},
            "known_limits": ["share-count based (splits inflate "
                            "ADD/TRIM; cfacshr v2 declared)",
                            "universe-restricted holdings only (our "
                            "6,894 PERMNOs' cusips)"],
            "pit": "downstream features key on fdate, never rdate",
            "no_verdicts": "construction; behavioral trials need their "
                           "own preregs"}
    (OUT / "manager_actions_quarterly_v1.meta.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in meta.items()
                      if k != "known_limits"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
