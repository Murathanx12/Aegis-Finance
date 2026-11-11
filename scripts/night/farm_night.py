"""Night farm runner (S65 night-backtests): the farm presets over the
runtime's CRSP data, receipts with a run id under night_2026-11-11/.

READS the runtime data (AEGIS_DATA_DIR must point at the runtime's
backend/data); WRITES only to OUT (the worktree). Prints the age/size of every
input before running.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
OUT = Path(__file__).resolve().parents[2] / "backend" / "data" / "optimus" / "night_2026-11-11"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preset", required=True)
    ap.add_argument("--start", type=int, default=1993)
    ap.add_argument("--end", type=int, default=2024)
    ap.add_argument("--extra-signals", default="",
                    help="comma list of extra registered signals at h=21 (signals preset)")
    a = ap.parse_args(argv)
    run_id = f"{a.preset}_{a.start}_{a.end}_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    from scripts import portfolio_farm_run as R
    from backend.services.portfolio_farm import farm, panel as P
    from backend.services.portfolio_farm.policy import grid
    farm.RESULTS_DIR = OUT
    print("RUN", run_id, "pid", os.getpid(), "AEGIS_DATA_DIR", os.environ.get("AEGIS_DATA_DIR"))
    inputs = {}
    for y in range(a.start, a.end + 1):
        p = P.WRDS_DIR / f"crsp_dsf_{y}.parquet"
        st = p.stat()
        inputs[p.name] = {"bytes": st.st_size, "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")}
    for p in (P.DELIST_PATH, P.FF_DAILY):
        st = p.stat() if p.exists() else None
        inputs[str(p)] = ({"bytes": st.st_size, "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")} if st else "MISSING")
    tot = sum(v["bytes"] for k, v in inputs.items() if isinstance(v, dict) and k.startswith("crsp_dsf"))
    print(f"inputs: {len(inputs)} files; CRSP dsf bytes {tot/1e9:.2f} GB; delist={inputs[str(P.DELIST_PATH)]}")
    pols = R.build(a.preset)
    if a.extra_signals:
        extra = [s for s in a.extra_signals.split(",") if s]
        pols += grid(signal=extra, holding_days=[21])
    t0 = time.time()
    # identical to portfolio_farm_run.main from here, with --reduce forced
    argv2 = ["--preset", a.preset, "--start", str(a.start), "--end", str(a.end),
             "--reduce", "--name", run_id]
    orig_build = R.build
    R.build = lambda preset: pols
    try:
        rc = R.main(argv2)
    finally:
        R.build = orig_build
    rec = {"run_id": run_id, "pid": os.getpid(), "preset": a.preset,
           "extra_signals": a.extra_signals, "n_policies": len(pols),
           "inputs": inputs, "elapsed_s": round(time.time() - t0, 1), "rc": rc,
           "farm_receipt": str(OUT / f"{run_id}.json")}
    (OUT / f"{run_id}.inputs.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
    print("DONE", json.dumps({k: rec[k] for k in ("run_id", "elapsed_s", "rc", "n_policies")}))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
