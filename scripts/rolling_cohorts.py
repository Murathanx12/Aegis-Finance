"""Rolling live cohorts of the branching population (CH-16 / M3).

    python -m scripts.rolling_cohorts compile-specs
    python -m scripts.rolling_cohorts step --data-root <optimus> [--out <dir>] [--asof <date>]
    python -m scripts.rolling_cohorts backfill --data-root <optimus> --from 2026-10-15 [--to <date>]

`step` is one idempotent pass: birth the due weekly cohort if its entry has not
opened, mark every live cohort, write the scoreboard. `backfill` births the
cohorts that should have existed since the anchor, from inputs dated before
each cohort's cutoff, every row flagged `backfilled: true` (backtest data,
never forward evidence). Neither writes under --data-root.

Exit codes: 0 ok (a WAIT is ok), 2 refused (RollingCohortRefused), 1 crash.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SPECS_V1 = ROOT / "docs/TRIALS/POPULATION-1000-SPECIFICATIONS.json"
SPECS_V2 = ROOT / "docs/TRIALS/ROLLING-COHORTS-SPECIFICATIONS-v2.json"


def output_dir(data_root: Path, out: Path | None) -> Path:
    """Default `<data-root>/rolling_cohorts`. Inside the data root nothing else is allowed."""
    from backend.services.portfolio_intelligence import branch_population_rolling as R

    own = (Path(data_root) / "rolling_cohorts").resolve()
    o = (Path(out) if out is not None else own).resolve()
    root = Path(data_root).resolve()
    if (o == root or root in o.parents) and not (o == own or own in o.parents):
        raise R.RollingCohortRefused(f"--out {o} is inside the data root; only {own} is allowed there")
    return o


def main(argv: list[str] | None = None) -> int:
    from backend.services.portfolio_intelligence import branch_population_rolling as R

    ap = argparse.ArgumentParser(prog="rolling_cohorts", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("compile-specs", help="write the v2 spec file from the 10-15 file (attended)")
    for name in ("step", "backfill"):
        p = sub.add_parser(name)
        p.add_argument("--data-root", required=True, type=Path, help="the optimus ledger dir (read only)")
        p.add_argument("--out", type=Path, default=None, help="default <data-root>/rolling_cohorts")
        p.add_argument("--specs", type=Path, default=SPECS_V2)
        p.add_argument("--asof", default=None, help="bars through this date (default: today)")
        if name == "backfill":
            p.add_argument("--from", dest="date_from", default=None)
            p.add_argument("--to", dest="date_to", default=None)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "compile-specs":
            v1 = json.loads(SPECS_V1.read_bytes())
            specs = R.compile_specs(v1)
            if SPECS_V2.exists():
                raise R.RollingCohortRefused(f"{SPECS_V2.name} exists; a declared spec file is never "
                                             f"rewritten. Declare a v3 file instead")
            SPECS_V2.write_text(json.dumps(specs, indent=1, sort_keys=True) + "\n", encoding="utf8", newline="\n")
            print(json.dumps({"written": str(SPECS_V2), "counts": specs["counts"],
                              "manifest_sha256": R.digest(specs)}, indent=1))
            return 0
        out = output_dir(a.data_root, a.out)
        row = R.run(a.cmd, data_root=a.data_root, out=out, specs_path=a.specs, asof=a.asof,
                    date_from=getattr(a, "date_from", None), date_to=getattr(a, "date_to", None))
    except R.RollingCohortRefused as exc:
        refusal = {"task": R.TASK_NAME, "action": "REFUSED", "rc": 2, "reason": str(exc),
                   "utc": datetime.now(timezone.utc).isoformat()}
        print(json.dumps(refusal))
        if a.cmd != "compile-specs":
            try:
                R.Store(output_dir(a.data_root, a.out)).journal(refusal)
            except (OSError, R.RollingCohortRefused):
                pass
        return 2
    print(json.dumps(row, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
