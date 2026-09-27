"""Grade every stored WSJ / Barron's / MarketWatch claim against what happened.

    python -m scripts.source_scorecard                 # DJ corpus + yfinance revisions leg
    python -m scripts.source_scorecard --no-yf         # Dow Jones corpus only
    python -m scripts.source_scorecard --yf-start 2026-01-01

Re-runnable: grades whatever the corpus holds at run time, prints
`new_rows_since_last_run` against the previous receipt, and writes
`backend/data/optimus/source_scorecard/source_scorecard_<run id>.json`
atomically (disk_guard). $0: no LLM, no browser, no network. The logic lives in
`backend.services.source_scorecard`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend.services import source_scorecard as SS


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus-root", type=Path, default=None)
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--no-yf", action="store_true", help="skip the yfinance revisions leg")
    ap.add_argument("--yf-start", default=SS.YF_LEG_START)
    ap.add_argument("--min-graded", type=int, default=1, help="hide cells with fewer graded units")
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    try:
        rc = SS.run(corpus_root=a.corpus_root, include_yf=not a.no_yf, yf_start=a.yf_start,
                    out_dir=a.out_dir, write=not a.no_write)
    except SS.ScorecardRefused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    print(SS.format_table(rc, min_graded=a.min_graded))
    print("\nunits:", json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "by_horizon"}
                                  for k, v in rc["units"].items()}, indent=1))
    print("\nwinner_vs_loser (already-moved shares):",
          json.dumps({k: {kk: v.get(kk) for kk in ("share_pub_after_move_gt_1sigma",
                                                  "share_pub_after_move_gt_2sigma",
                                                  "n_units_with_pre_move")}
                      for k, v in rc["winner_vs_loser"].items()}, indent=1))
    print(f"\nreceipt: {rc.get('_path', '(not written)')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
