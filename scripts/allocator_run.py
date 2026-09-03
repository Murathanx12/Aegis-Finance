"""Run the Capital Allocator v0 (SHADOW ONLY) on a PotentialUniverse vintage.

Licence: PRODUCT_EXPERIMENT (shadow). This script writes DecisionArtifact
JSON files and prints their tables. It places nothing, and nothing reads its
output for execution -- the artifact's own `authority` field says so on every
line of output it produces.

    python -m scripts.allocator_run                          # latest vintage,
                                                             # balanced+aggressive
    python -m scripts.allocator_run --day 2026-09-02 \
        --personality balanced --personality aggressive
    python -m scripts.allocator_run --cash-thesis "..."      # thesis-gated cash

The default personalities are the review's first two asks (PART B run once on
the real 2026-09-02 vintage for balanced + aggressive). `--cash-thesis` exists
so a human can hand the allocator an explicit bearish/deleveraging thesis;
without it cash can never receive the residual, by design.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from learner import allocator as A  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--day", default=None,
                    help="PotentialUniverse vintage day (default: latest "
                         "file in backend/data/optimus/potential_universe/)")
    ap.add_argument("--personality", action="append", default=None,
                    choices=sorted(A.PERSONALITIES),
                    help="repeatable; default: balanced + aggressive")
    ap.add_argument("--equity", type=float, default=100_000.0,
                    help="equity USD for the worst-case-in-dollars line")
    ap.add_argument("--cash-thesis", default=None,
                    help="explicit bearish/deleveraging thesis; without it "
                         "cash never receives the residual")
    ap.add_argument("--out-dir", default=None,
                    help="override the decision_artifacts directory")
    args = ap.parse_args(argv)

    day = args.day or A.latest_pu_day()
    if day is None:
        print("REFUSED: no PotentialUniverse vintage exists and no --day "
              "given. An allocator with no universe has no opinion to record.")
        return 2
    pu_path = A.PU_DIR / f"{day}.jsonl"
    if not pu_path.exists():
        print(f"REFUSED: no PotentialUniverse vintage at {pu_path}. "
              "Absence of the input is a finding, not a default.")
        return 2

    personalities = args.personality or ["balanced", "aggressive"]
    out_dir = Path(args.out_dir) if args.out_dir else None
    pu = A.read_potential_universe(pu_path)

    for personality in personalities:
        artifact = A.build_decision_artifact(
            day, personality, pu=pu, equity_usd=args.equity,
            cash_thesis=args.cash_thesis)
        path = A.write_decision_artifact(artifact, out_dir=out_dir)
        print()
        print(A.format_table(artifact))
        print(f"written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
