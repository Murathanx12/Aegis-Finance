"""REVISION-FORECASTER-1 re-run with the consensus AS QUOTED (unadjusted IBES).

    python -m scripts.night.revision_forecaster_rerun --runtime C:/Users/mrthn/aegis-finance

The 2026-08 run read `ibes_consensus_monthly*` (split-adjusted, cents) and scaled
`meanest_t1 - meanest_t0` by the RAW CRSP price at the event, so a firm that later
split F-fold had its revision divided by F and rounded toward 0.00 -- the target was
attenuated exactly for future winners. This wrapper changes the input and nothing
else: `load_consensus` reads `ibes_pit_consensus` (as quoted at statpers), and after
`attach_revision` the t0 values are restated in t1's shares with IBES's own factors
(a split between the two cuts is rare at a ~20-day lag, and is counted). Runtime data
is read-only; outputs go to this checkout's `night_2026-11-11/revision_forecaster_<run>/`.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runtime", required=True, help="the runtime checkout (read-only)")
    a = ap.parse_args()
    from backend.services import ibes_pit_consensus as PIT
    from scripts import revision_forecaster_v1 as RFV

    run = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rt = Path(a.runtime) / "backend" / "data" / "optimus"
    RFV.WRDS = rt / "wrds"
    RFV.PANEL = rt / "event_response" / RFV.PANEL.name
    RFV.OUT = ROOT / "backend" / "data" / "optimus" / "night_2026-11-11" / f"revision_forecaster_{run}"
    old = json.loads((rt / "revision_forecaster" / "receipt.json").read_text(encoding="utf-8"))
    counts = {}
    adj_of = {}
    orig_attach = RFV.attach_revision

    def load_consensus(permnos: set) -> pd.DataFrame:
        c = PIT.load_consensus(fpi=RFV.FROZEN["fpi"])
        c = c[c["permno"].isin({int(p) for p in permnos})]
        c["fpedats"] = pd.to_datetime(c["fpedats"])
        for (p, s), f in zip(zip(c["permno"], c["statpers"]), c["adj_factor"]):
            adj_of[(int(p), pd.Timestamp(s))] = f
        counts["consensus_rows"] = int(len(c))
        cols = ["permno", "statpers", "measure", "fpi", "meanest", "stdev",
                "numest", "numup", "numdown", "fpedats"]
        return (c[cols].dropna(subset=["permno", "statpers", "meanest", "fpedats"])
                .sort_values(["permno", "statpers"]).reset_index(drop=True))

    def attach_revision(ev, cons):
        j = orig_attach(ev, cons)
        perm = dict(zip(ev["event_id"], ev["permno"].astype("int64")))
        a0 = [adj_of.get((perm.get(e), pd.Timestamp(t))) for e, t in zip(j["event_id"], j["t0"])]
        a1 = [adj_of.get((perm.get(e), pd.Timestamp(t))) for e, t in zip(j["event_id"], j["t1"])]
        r = pd.Series(a1, index=j.index, dtype="float64") / pd.Series(a0, index=j.index, dtype="float64")
        counts["events"] = int(len(j))
        counts["split_between_t0_t1"] = int((r.notna() & (r != 1.0)).sum())
        counts["factor_unknown"] = int(r.isna().sum())
        if len(j) and counts["factor_unknown"] == len(j):
            raise SystemExit("REFUSED: no IBES adj factor for any event -- set "
                             "AEGIS_IBES_ADJ_PATH (or AEGIS_DATA_DIR) to the runtime's ibes__adj")
        j = j[r.notna()].copy()
        j["meanest_t0"] = j["meanest_t0"] * r[r.notna()]
        j["stdev_t0"] = j["stdev_t0"] * r[r.notna()]
        return j

    RFV.load_consensus = load_consensus
    RFV.attach_revision = attach_revision
    t0 = time.time()
    rec = RFV.run()
    out = {"run_id": run, "job": "revision_forecaster_rerun", "input": "ibes_pit_consensus (as quoted)",
           "counts": counts, "new": {k: rec.get(k) for k in ("decisive_cell", "verdict", "coverage")},
           "old": {k: old.get(k) for k in ("decisive_cell", "verdict", "coverage")},
           "new_Q1": rec.get("Q1_realised_revision_ranks_returns"),
           "old_Q1": old.get("Q1_realised_revision_ranks_returns"),
           "new_Q2": rec.get("Q2_revision_is_predictable"), "old_Q2": old.get("Q2_revision_is_predictable"),
           "new_Q3_paired": rec.get("Q3_paired_routed_minus_direct"),
           "old_Q3_paired": old.get("Q3_paired_routed_minus_direct"),
           "wall_s": round(time.time() - t0, 1)}
    p = RFV.OUT.parent / f"revision_forecaster_rerun_{run}.json"
    p.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print(json.dumps({"counts": counts, "new": out["new"], "old": out["old"]}, default=str))
    print(f"receipt -> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
