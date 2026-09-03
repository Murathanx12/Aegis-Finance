"""Build and persist the POTENTIAL UNIVERSE for one day. Writes a file.
Places nothing.

    python -m scripts.potential_universe_run                  # latest tracker day
    python -m scripts.potential_universe_run --day 2026-09-02
    python -m scripts.potential_universe_run --print-only     # do not write

WHY THIS SCRIPT EXISTS
======================
The starved-seal incident (2026-09-03): `d_catalyst` was unreadable on all
810 candidates, hack4 sealed empty, and the exit pass turned the data gap
into sells. This script's one-screen summary is the object a seal-time
reader looks at FIRST: counts per engine verdict and capacity tier, the
refusal counts with their top reasons, and the field-readability block that
would have said "days_to_catalyst: unreadable on 810/810" before any book
was allowed to starve quietly.

Every number printed here is also in the persisted file
(`backend/data/optimus/potential_universe/<day>.jsonl`, header line) -- a
headline number that lives only in a terminal scrollback is not a receipt.

The exit code is 0 on a REFUSED day too: refusing to score a day that
cannot be scored honestly is the correct output, not a crash. `--strict`
flips that for a scheduler that wants to be paged.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from learner import potential_universe as PU     # noqa: E402


def summarise(pu: dict) -> str:
    h = pu["header"]
    lines = [
        f"POTENTIAL UNIVERSE {h.get('day')}  [{h.get('status', 'REFUSED')}]  "
        f"{h['version']}",
    ]
    if h.get("status") != "OK":
        for r in h.get("reasons", []):
            lines.append(f"  REFUSED: {r}")
        return "\n".join(lines)
    c = h["counts"]
    lines.append(f"  scorecards: {c['n_scorecards']} / rows {c['n_rows']}   "
                 f"pit_refused: {c['pit_refused']}")
    lines.append("  engine verdicts: " + "  ".join(
        f"{k}={v}" for k, v in c["by_engine_verdict"].items()))
    lines.append("  capacity tiers:  " + "  ".join(
        f"{k}={v}" for k, v in c["by_capacity_tier"].items())
        + f"  (observe_only={c['observe_only']})")
    lines.append(f"  learner v1: scored={c['v1_scored']} refused={c['v1_refused']}")
    for tr in c["v1_top_refusal_reasons"]:
        lines.append(f"    refusal x{tr['n']}: {tr['reason'][:100]}")
    wu = h["whole_universe_refusals"]
    lines.append(f"  learner v2: REFUSED on {wu['learner_v2']['refused_on']}/"
                 f"{wu['learner_v2']['of']} "
                 f"({len(wu['learner_v2']['missing_inputs'])} missing columns)")
    lines.append(f"  state:      CANNOT_DETERMINE on {wu['state']['refused_on']}/"
                 f"{wu['state']['of']} "
                 f"({len(wu['state']['missing_inputs'])} missing features)")
    lines.append(f"  sign disagreements (engine vs learner): {c['sign_disagreements']}")
    fr = h["field_readability"]
    lines.append("  field readability (the starved-seal sensor):")
    for k in ("days_to_catalyst", PU.LIQUIDITY_COLUMN, "mean_target",
              "coverage_rec_counts", "realised_vol_20d"):
        r = fr[k]
        flag = "  <-- WHOLE-UNIVERSE GAP" if r["readable"] == 0 else ""
        lines.append(f"    {k}: readable {r['readable']} / unreadable {r['unreadable']}{flag}")
    lines.append(f"  graded_like_a_book: {h['graded_like_a_book']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--day", default=None, help="YYYY-MM-DD (default: latest tracker day)")
    ap.add_argument("--print-only", action="store_true", help="do not write the file")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 on a REFUSED day (for schedulers)")
    args = ap.parse_args(argv)

    pu = PU.build_potential_universe(args.day)
    print(summarise(pu))
    if not args.print_only:
        path = PU.write_potential_universe(pu)
        print(f"  written -> {path}")
    if args.strict and pu["header"].get("status") != "OK":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
