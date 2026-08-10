"""Optimus morning brief — the thing to read before the market opens.

    python scripts/morning_brief.py [--mode moonshot] [--no-watchlist] [--json]

Prints, in this order: what you hold, what to do about it, what threatens it,
what could replace the weakest of it, and where the account lands in twelve
months WITH the downside beside the upside. Never the target alone.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.services import pm_actions, pm_engine, pm_journal   # noqa: E402

BAR = "=" * 78


def money(x) -> str:
    if x is None:
        return "     n/a"
    return f"${x:,.0f}"


def pct(x, nd=1) -> str:
    return "  n/a" if x is None else f"{x * 100:+.{nd}f}%"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=list(pm_engine.MODES))
    ap.add_argument("--no-watchlist", action="store_true")
    ap.add_argument("--candidates", type=int, default=10)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--record", action="store_true",
                    help="freeze today's instructions into the journal")
    a = ap.parse_args()

    book = pm_engine.load_book()
    if a.mode:
        book.sizing_mode = a.mode
    b = pm_actions.daily_brief(book, include_watchlist=not a.no_watchlist,
                               max_candidates=a.candidates)
    if a.json:
        print(json.dumps(b, indent=2, default=str))
        return 0

    print(BAR)
    print(f"OPTIMUS MORNING BRIEF   {b['generated_at']}   "
          f"account={b['account']}   mode={b['sizing_mode']}")
    print(BAR)
    if b["banner"]:
        print("\n!! " + b["banner"] + "\n")

    print(f"PORTFOLIO {money(b['portfolio_value'])}   cash {money(b['cash'])}")
    w = b["wealth"]
    if w.get("available"):
        t = w.get("p_reach_target")
        print(f"12-MONTH VIEW    median {money(w['median'])}   "
              f"p25 {money(w['p25'])}   p75 {money(w['p75'])}")
        print(f"                 P(reach target) {t:.1%}    "
              f"P(below floor) {w['p_below_floor']:.1%}    "
              f"P(below ruin) {w['p_below_ruin']:.1%}")
        print(f"                 expected max drawdown "
              f"{w['expected_max_drawdown']:.1%}   "
              f"P(worse than -50%) {w['p_drawdown_worse_than_50pct']:.1%}")
        print(f"                 required return for the target "
              f"{w['required_return_for_target']:+.1%}   "
              f"(analyst haircut {w['assumptions']['target_haircut']}, "
              f"corr {w['assumptions']['average_pairwise_correlation']})")

    print("\n" + "-" * 78)
    print(f"{'HOLDINGS':<8}{'PRICE':>9}{'P&L':>9}{'WEIGHT':>9}{'TARGET':>9}"
          f"{'UPSIDE':>9}{'SCORE':>8}  ACTION")
    print("-" * 78)
    for r in sorted(b["holdings"],
                    key=lambda x: -(x["alpha"].get("score") or -1)):
        st, rec = r["state"], r["recommendation"]
        px = st.get("price")
        print(f"{r['ticker']:<8}"
              f"{('$%.2f' % px) if px else 'n/a':>9}"
              f"{pct(r.get('pnl_pct')):>9}"
              f"{r['current_weight'] * 100:>8.1f}%"
              f"{rec['target_weight'] * 100:>8.1f}%"
              f"{pct(st.get('implied_upside')):>9}"
              f"{(r['alpha'].get('score') or 0):>8.3f}"
              f"  {rec['action']:<5}"
              f"{('' if not rec['dollars'] else money(rec['dollars']))}")

    if b["actions"]:
        print("\nTODAY'S TICKETS")
        for x in b["actions"]:
            print(f"  {x['action']:<5} {money(abs(x['dollars'])):>9}  "
                  f"{x['ticker']:<6} "
                  f"{x['current_weight'] * 100:.1f}% -> "
                  f"{x['target_weight'] * 100:.1f}%")
            if x.get("kill_condition"):
                print(f"        kill condition: {x['kill_condition']}")
    else:
        print("\nTODAY'S TICKETS: none — every position is inside its band.")

    if b["threats"]:
        print("\nTHREATS")
        for t in b["threats"]:
            print(f"  {t['ticker']:<6} {t['why']}")

    if b["opportunities"]:
        print("\nOPPORTUNITY RADAR (watchlist, ranked)")
        for c in b["opportunities"]:
            s = c["state"]
            print(f"  {c['ticker']:<6} score {c['score']:.3f}  upside "
                  f"{pct(c['implied_upside'])}  "
                  f"{s.get('n_analysts') or 0:>3} analysts  "
                  f"net90d {s.get('net_90d')}"
                  f"{'  BINARY' if s.get('binary_event_risk') else ''}")

    if b["replacements"]:
        print("\nREPLACEMENTS — a better use of the same dollar")
        for s in b["replacements"]:
            print(f"  {s['verdict']}: {s['candidate']} funded by "
                  f"{s['funded_by']}  edge {s['edge']:+.3f}")

    print("\n" + "-" * 78)
    print(b["evidence_note"])
    if w.get("available"):
        print(w["health_warning"])

    if a.record:
        out = pm_journal.record_brief(b, note="morning_brief CLI")
        print(f"\njournal: {out['written']} instructions recorded at "
              f"{out['path']}")
        if out.get("caveat"):
            print(f"         {out['caveat']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
