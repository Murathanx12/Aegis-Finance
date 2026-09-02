"""Seal today's LEARNER SHADOW book. Writes a file. Places nothing.

    python -m scripts.learner_shadow_seal                 # latest tracker day
    python -m scripts.learner_shadow_seal --day 2026-09-02
    python -m scripts.learner_shadow_seal --print-only    # do not write

WHAT "SHADOW" MEANS HERE
========================
The learner has no broker authority and this script does not give it any. It
reads `aegis-alpha-terminal/state/tracker/<day>.jsonl` READ-ONLY, scores it
with the sealed champion, and writes
`backend/data/optimus/learner/shadow_book_<day>.json`. Nothing downstream reads
that file; no order path imports `learner`. Promotion to any book that trades
is a separate, attended decision under CANON, and it is not this script.

REFUSAL IS A RESULT
===================
If the day file is missing, the sealed model's schema hash does not match, too
few names carry the core features, or fewer than ten names survive the
execution gates, the book is written with `status: REFUSED` and the reasons
named. The exit code is 0 either way -- a refusal is the correct output of a
day that could not be scored honestly, not a crash -- and `--strict` flips that
for a scheduler that wants to be paged.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from learner import shadow as S      # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--day", default=None, help="YYYY-MM-DD; default: latest tracker day")
    ap.add_argument("--k", type=int, default=S.SHADOW_K)
    ap.add_argument("--weight-pct", type=float, default=S.SHADOW_WEIGHT_PCT)
    ap.add_argument("--tag", default="shadow", choices=("shadow", "full"),
                    help="which sealed champion to score with")
    ap.add_argument("--print-only", action="store_true")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 on REFUSED (for a scheduler that wants to be paged)")
    a = ap.parse_args(argv)

    book = S.build_shadow_book(day=a.day, k=a.k, weight_pct=a.weight_pct, tag=a.tag)

    print(f"  day: {book.get('day')}   status: {book.get('status')}")
    m = book.get("model", {})
    if m:
        print(f"  model: {m.get('kind')}/{m.get('arm')} vintage "
              f"{m.get('model_vintage_sha256_16')} trained through "
              f"{m.get('trained_through_month')} on {m.get('trained_rows')} rows")
    cov = book.get("feature_coverage", {})
    if cov:
        print(f"  coverage: {cov.get('n_scoreable')}/{cov.get('n_rows')} scoreable "
              f"({cov.get('core_coverage')}), columns {cov.get('column_coverage')}")
    g = book.get("execution_gates")
    if g:
        print(f"  gates: {g.get('start')} scoreable -> "
              f"-{g.get('removed_below_3m_dollar_vol')} illiquid "
              f"-{g.get('removed_not_tradable')} untradable -> {g.get('eligible')} eligible")
    if book.get("status") == "REFUSED":
        for r in book.get("reasons", []):
            print(f"  REFUSED: {r}")
    else:
        print(f"  score unit: {book.get('score_unit')}")
        print(f"  {'symbol':<8} {'score':>9} {'prior':>9} {'delta':>9} "
              f"{'band':<12} {'ratio':>7} {'cons':>6} {'cov':>5}")
        for h in book.get("holdings", []):
            d = h.get("learner_delta_vs_prior")
            print(f"  {str(h['symbol']):<8} {h['score']:>9.5f} "
                  f"{h['engine_prior_1m']:>9.5f} "
                  f"{('n/a' if d is None else f'{d:.5f}'):>9} "
                  f"{h['band']:<12} {h['ratio']:>7.3f} {h['consensus']:>6.2f} "
                  f"{h['coverage']:>5.0f}")
        bs = book.get("book_summary", {})
        print(f"  bands held: {bs.get('bands_held')}   toxic held: "
              f"{bs.get('n_toxic_band_held')}")
        print(f"  worst case, every name stopping at -3%: "
              f"{bs.get('worst_case_if_every_name_stops_at_-3pct')}% of equity "
              f"(gross {book['mandate']['gross_pct']}%)")

    if a.print_only:
        print(json.dumps(book, indent=2, default=str)[:400])
    else:
        path = S.write_shadow_book(book)
        print(f"  -> {path}   (this file is written, never sent)")

    return 1 if (a.strict and book.get("status") == "REFUSED") else 0


if __name__ == "__main__":
    raise SystemExit(main())
