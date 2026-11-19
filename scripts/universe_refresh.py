"""CH-59: `python -m scripts.universe_refresh` rebuilds the opportunity funnel's candidate
set and the universe graph, each out of process, and exits non-zero unless every answer
either moved or was already fresh. Logic and the full contract:
`backend/services/universe_refresh.py`.

    python -m scripts.universe_refresh                 the daily task (age-gated)
    python -m scripts.universe_refresh --force         rebuild both regardless of age
    python -m scripts.universe_refresh --dry-run       print the exact child commands; start
                                                       nothing, write nothing
    python -m scripts.universe_refresh --only graph    one stage

Exit codes: 0 every stage REFRESHED or SKIPPED_FRESH; 2 a stage REFUSED (no network, the
builder refused, the new answer was smaller or empty); 1 a stage FAILED or UNMOVED.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from backend.services import universe_refresh as UR


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m scripts.universe_refresh",
                                 description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--data-root", help="the optimus data folder (default: config.OPTIMUS_LEDGER_DIR)")
    ap.add_argument("--out", help="receipt + log folder (default: <data-root>/universe_refresh)")
    ap.add_argument("--funnel-path", help="the funnel snapshot to refresh (default: the LIVE "
                                          "funnel_night10.json beside the resolved data root)")
    ap.add_argument("--graph-dir", help="the graph folder to refresh (default: <data-root>/universe_graph)")
    ap.add_argument("--only", choices=UR.STAGES, action="append", help="run one stage (repeatable)")
    ap.add_argument("--force", action="store_true", help="rebuild even when the answer is fresh")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the plan and the exact child commands; start nothing, write nothing")
    a = ap.parse_args(argv)
    kw = dict(data_root=Path(a.data_root) if a.data_root else None,
              out=Path(a.out) if a.out else None,
              funnel_path=Path(a.funnel_path) if a.funnel_path else None,
              graph_dir=Path(a.graph_dir) if a.graph_dir else None,
              force=a.force, only=tuple(a.only or UR.STAGES))
    if a.dry_run:
        print(json.dumps(UR.plan(**kw), indent=1, default=str))
        return 0
    receipt = UR.refresh(argv=list(sys.argv[1:] if argv is None else argv), **kw)
    for line in UR.summary_lines(receipt):
        print(line, flush=True)
    return int(receipt["overall_rc"])


if __name__ == "__main__":
    raise SystemExit(main())
