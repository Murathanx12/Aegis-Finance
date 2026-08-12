"""Explain one day of Murat's book, and grade the explanations that can be.

Usage:
    python scripts/run_why_moved.py                     # last completed session
    python scripts/run_why_moved.py --date 2026-08-10
    python scripts/run_why_moved.py --no-ledger         # do not write forecasts
    python scripts/run_why_moved.py --lenses geopolitical,skeptic

What it does, in order:
  1. loads the book (backend/data/murat_book.yaml) and one price panel;
  2. computes the deterministic attribution — this is the answer, and it does
     not need a language model;
  3. asks seven specialists SEPARATELY for hypotheses that could be caught
     being wrong, and throws away the ones that could not;
  4. grades every cross-asset assertion against that same (already past) day;
  5. mints the surviving forward claims into the Optimus prediction ledger, so
     the existing resolver grades them on schedule.

It never names a cause. See backend/services/why_moved.py for why that is a
property of the data rather than a limitation of the implementation.

Writes:
    docs/conviction_replay/why_moved_<date>.json
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:                                    # pragma: no cover
    print("python-dotenv missing — relying on the ambient environment")

from backend.services import why_moved as wm            # noqa: E402

OUT_DIR = ROOT / "docs" / "conviction_replay"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None,
                    help="day to explain (ISO); default = yesterday, walked "
                         "back to the last session with data")
    ap.add_argument("--lenses", default=None, help="comma-separated subset")
    ap.add_argument("--no-ledger", action="store_true",
                    help="do not append the minted forecasts to the ledger")
    ap.add_argument("--book", default=None, help="alternate book YAML")
    ap.add_argument("--regrade", default=None,
                    help="re-score an existing artifact under the current "
                         "grading rules; calls no model and mints no records")
    ap.add_argument("--suffix", default="",
                    help="artifact filename suffix; use it when re-running a "
                         "SUBSET of lenses so the full run's artifact is not "
                         "overwritten by a partial one")
    ap.add_argument("--max-walkback", type=int, default=5,
                    help="how many sessions back to look for one that prices "
                         "the WHOLE book (each skipped day is printed)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("yfinance").setLevel(logging.ERROR)

    positions = wm.book_positions(args.book)
    if args.regrade:
        # Re-score an existing artifact under the current rules. No model call,
        # no ledger write: a scoring fix must never mint a second batch of
        # forecasts about the same day.
        p = Path(args.regrade)
        art = json.loads(p.read_text(encoding="utf-8"))
        panel = wm.panel_for(wm.universe_for(positions), art["attribution"]["as_of"])
        art = wm.regrade(art, panel)
        p.write_text(json.dumps(art, indent=1, ensure_ascii=False, default=str),
                     encoding="utf-8")
        c = art["batch"]["corroboration"]
        print(f"regraded {p.name}: external "
              f"{c['corroboration_hits_external']}/"
              f"{c['corroboration_hits_external'] + c['corroboration_misses_external']}"
              f" = {c['corroboration_hit_rate_external']}, derivable "
              f"{c['corroboration_hits_derivable']}/"
              f"{c['corroboration_hits_derivable'] + c['corroboration_misses_derivable']}"
              f" = {c['corroboration_hit_rate_derivable']}")
        return 0

    print(f"book: {len(positions)} positions — "
          f"{', '.join(t for t, _ in positions)}")

    requested = args.date or str(date.today() - timedelta(days=1))
    lenses = ([x.strip() for x in args.lenses.split(",")] if args.lenses
              else None)

    # One panel, then choose the day. The vendor publishes SPY hours before it
    # publishes a $2 biotech, so the last session on the tape is routinely NOT
    # the last session the whole book prints on — and grading the book on a day
    # eleven of twelve names are missing from would report a P&L it never took.
    panel = wm.panel_for(wm.universe_for(positions), requested)
    graded_day, skipped = wm.last_priceable_session(
        positions, panel, requested, max_walkback=args.max_walkback)
    for s in skipped:
        print(f"SKIPPED {s.splitlines()[0]}")
    if graded_day != str(requested)[:10]:
        print(f"NOTE: {requested} does not price the whole book; graded "
              f"{graded_day} instead")

    out = wm.run_why_moved(positions, graded_day, panel=panel, lenses=lenses,
                           write_ledger=not args.no_ledger)

    a = out["attribution"]

    print(f"\n{a['as_of']}  book {a['pnl_usd']:+,.0f} USD "
          f"({a['pnl_pct']:+.2f}%)   {a['benchmark']} "
          f"{a['benchmark_return_pct']:+.2f}%   beta {a['book_beta']:.2f}")
    print(f"  market {a['market_component_usd']:+,.0f} | sector "
          f"{a['sector_component_usd']:+,.0f} | idiosyncratic "
          f"{a['idiosyncratic_usd']:+,.0f}")
    for p in a["positions"]:
        print(f"    {p['ticker']:<6} {p['return_pct']:+7.2f}%  "
              f"{p['pnl_usd']:+9,.0f} USD  {p['contribution_bps']:+8.1f} bps")

    print(f"\nstatus: {out['status']} — {out['status_detail']}")
    print("corroboration is a COHERENCE check on a past day, never skill; the "
          "quoted rate counts only instruments the prompt did not disclose.")
    for lens, v in (out.get("lenses") or {}).items():
        ext = v["corroboration_hit_rate_external"]
        der = v["corroboration_hit_rate_derivable"]
        n_ext = v["corroboration_hits_external"] + v["corroboration_misses_external"]
        n_der = v["corroboration_hits_derivable"] + v["corroboration_misses_derivable"]
        print(f"  {lens:<14} hypotheses {v['n_hypotheses']}  rejected "
              f"{v['n_rejected']}  external "
              f"{'n/a' if ext is None else f'{ext:.0%}'} "
              f"({v['corroboration_hits_external']}/{n_ext})  derivable "
              f"{'n/a' if der is None else f'{der:.0%}'} "
              f"({v['corroboration_hits_derivable']}/{n_der})  unavailable "
              f"{v['corroboration_unavailable']}  minted "
              f"{v['n_predictions_minted']}")
    b = out.get("batch") or {}
    if b:
        print(f"\n§20 effective distinct ideas: "
              f"{b['effective_distinct_ideas']} of {b['n_hypotheses']} "
              f"(ratio {b['ratio']})")
        c = b["corroboration"]
        ext, der = c["corroboration_hit_rate_external"], c["corroboration_hit_rate_derivable"]
        print(f"corroboration EXTERNAL (the headline): "
              f"{c['corroboration_hits_external']}/"
              f"{c['corroboration_hits_external'] + c['corroboration_misses_external']}"
              f" = {'n/a' if ext is None else f'{ext:.0%}'}   "
              f"derivable-from-prompt (instruction-following): "
              f"{c['corroboration_hits_derivable']}/"
              f"{c['corroboration_hits_derivable'] + c['corroboration_misses_derivable']}"
              f" = {'n/a' if der is None else f'{der:.0%}'}   "
              f"unavailable {c['corroboration_unavailable']}")
    print(f"predictions minted: {out.get('n_predictions_minted', 0)}  "
          f"ledger: {out.get('ledger_written', 'not written')}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"why_moved_{a['as_of']}{args.suffix}.json"
    path.write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str),
                    encoding="utf-8")
    print(f"\nartifact: {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
