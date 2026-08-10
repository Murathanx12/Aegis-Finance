"""Optimus morning brief — the thing to read before the market opens.

    python scripts/morning_brief.py [--mode moonshot] [--no-watchlist] [--json]

Prints, in this order: what you hold and what it is worth right now, what to do
about it, what threatens it, what could replace the weakest of it, where the
account lands in twelve months WITH the downside beside the upside and under
three different sets of assumptions — and finally MODEL STATUS, which says how
much of the above you should believe today.

An unconfirmed book never prints "TODAY'S TICKETS". It prints SIMULATED
TICKETS — DO NOT EXECUTE, in the same place, so the two states cannot be
mistaken for one another at a glance.
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


def prob(x) -> str:
    return " n/a" if x is None else f"{x:.1%}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", default=None,
                    help="an alternate book YAML — use this to dry-run a "
                         "confirmed book before flipping the real flag")
    ap.add_argument("--mode", choices=list(pm_engine.MODES))
    ap.add_argument("--no-watchlist", action="store_true")
    ap.add_argument("--candidates", type=int, default=10)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--record", action="store_true",
                    help="freeze today's instructions into the journal")
    ap.add_argument("--snapshot", action="store_true",
                    help="append today's analyst state to the PIT ledger "
                         "(this is how target-revision history accrues)")
    a = ap.parse_args()

    try:
        book = pm_engine.load_book(a.book)
    except pm_engine.BookError as e:
        print(f"BOOK REJECTED\n\n{e}\n\nNothing was computed. A confirmed book "
              f"must be able to mark to market.")
        return 2
    if a.mode:
        book.sizing_mode = a.mode
    b = pm_actions.daily_brief(book, include_watchlist=not a.no_watchlist,
                              max_candidates=a.candidates,
                              record_snapshots=a.snapshot)
    if a.json:
        print(json.dumps(b, indent=2, default=str))
        return 0

    print(BAR)
    print(f"OPTIMUS MORNING BRIEF   {b['generated_at']}   "
          f"account={b['account']}   mode={b['sizing_mode']}")
    print(BAR)
    if not b["actionable"]:
        print("\n!! " + b["banner"] + "\n")

    v = b["valuation"]
    print(f"PORTFOLIO {money(b['portfolio_value'])}   "
          f"invested {money(v['invested'])}   cash {money(b['cash'])}")
    print(f"          valued on: {v['basis']}  [{v['valuation_grade']}]")

    w = b["wealth"]
    if w.get("available"):
        base = w["base"]
        rng = w.get("range", {})
        print(f"\n{base['horizon_months']}-MONTH VIEW (BASE)   "
              f"median {money(base['median'])}   "
              f"p25 {money(base['p25'])}   p75 {money(base['p75'])}")
        print(f"                     P(reach target) {prob(base['p_reach_target'])}"
              f"    P(below floor) {prob(base['p_below_floor'])}"
              f"    P(below ruin) {prob(base['p_below_ruin'])}")
        print(f"                     expected max drawdown "
              f"{base['expected_max_drawdown']:.1%}   "
              f"P(worse than -50%) {prob(base['p_drawdown_worse_than_50pct'])}")
        print(f"                     required return for the target "
              f"{base['required_return_for_target']:+.1%}")

        print("\nMODEL SENSITIVITY — the same book, three sets of assumptions")
        print(f"  {'scenario':<14}{'haircut':>8}{'corr':>7}{'vol x':>7}"
              f"{'median':>11}{'P(target)':>11}{'P(<floor)':>11}{'P(<ruin)':>10}"
              f"{'E[maxDD]':>10}")
        for name in ("conservative", "base", "optimistic"):
            s = w["scenarios"].get(name, {})
            if not s.get("available"):
                continue
            cfg = s["assumptions"]
            print(f"  {name:<14}{cfg['target_haircut']:>8.2f}"
                  f"{cfg['average_pairwise_correlation']:>7.2f}"
                  f"{cfg['volatility_multiplier']:>7.2f}"
                  f"{money(s['median']):>11}"
                  f"{prob(s['p_reach_target']):>11}"
                  f"{prob(s['p_below_floor']):>11}"
                  f"{prob(s['p_below_ruin']):>10}"
                  f"{s['expected_max_drawdown']:>9.1%}")
        pr = rng.get("p_reach_target") or {}
        if pr:
            print(f"  => scenario-model range for P(reach target): "
                  f"{prob(pr['low'])} to {prob(pr['high'])}, "
                  f"base {prob(pr['base'])}. The spread is MODEL uncertainty, "
                  f"not Monte Carlo error.")

    print("\n" + "-" * 78)
    print(f"{'HOLDINGS':<7}{'SHARES':>9}{'PRICE':>9}{'VALUE':>10}{'P&L':>9}"
          f"{'WGT':>7}{'TGT':>7}{'UPSIDE':>9}  ACTION")
    print("-" * 78)
    for r in sorted(b["holdings"],
                    key=lambda x: -(x.get("market_value") or 0)):
        st, rec = r["state"], r["recommendation"]
        px = st.get("price")
        sh = r.get("shares")
        print(f"{r['ticker']:<7}"
              f"{(f'{sh:,.0f}' if sh is not None else '-'):>9}"
              f"{('$%.2f' % px) if px else 'n/a':>9}"
              f"{money(r.get('market_value')):>10}"
              f"{pct(r.get('pnl_pct')):>9}"
              f"{r['current_weight'] * 100:>6.1f}%"
              f"{rec['target_weight'] * 100:>6.1f}%"
              f"{pct(st.get('implied_upside')):>9}"
              f"  {rec['action']:<6}"
              f"{('' if not rec['dollars'] else money(rec['dollars']))}")
    if v.get("no_shares"):
        print(f"  ! no share count: {', '.join(v['no_shares'])} — these values "
              f"are placeholders and do NOT move with the price")
    if v.get("no_quote"):
        u = b["nav_uncertainty"]
        print(f"  ! no live quote: {', '.join(v['no_quote'])} — "
              f"{u['unpriced_share_of_nav']:.1%} of NAV is unpriced "
              f"(tolerance {u['tolerance']:.0%}"
              f"{', BREACHED' if u['material'] else ''})")

    print("\n" + b["ticket_label"])
    if b["actions"]:
        for x in b["actions"]:
            print(f"  {x['action']:<6} {money(abs(x['dollars'])):>9}  "
                  f"{x['ticker']:<6} "
                  f"{x['current_weight'] * 100:.1f}% -> "
                  f"{x['target_weight'] * 100:.1f}%"
                  f"{'  [scaled to available cash]' if x.get('scaled_for_cash') else ''}")
            if x.get("why"):
                print(f"        {x['why']}")
            if x.get("kill_condition"):
                print(f"        kill condition: {x['kill_condition']}")
    else:
        print("  none — every position is inside its band.")

    rev = [r for r in b["holdings"]
           if r["recommendation"]["action"] == "REVIEW"]
    if rev:
        print("\nREVIEW — held, and the engine cannot see it. NOT a sell signal.")
        for r in rev:
            print(f"  {r['ticker']:<6} "
                  f"{'; '.join(r['recommendation'].get('missing') or [])}")

    c = b["cash_reconciliation"]
    print(f"\nCASH   before {money(c['cash_before'])}  "
          f"raised by sales {money(c['raised_by_sales'])}  "
          f"buys {money(c['buys_final'])}  after {money(c['cash_after'])}"
          f"{'   [BUYS SCALED]' if c['scaled'] else ''}")

    cal = b.get("catalysts") or {}
    print("\nUPCOMING CATALYSTS")
    for label, key in (("0-7d  ", "0_7d"), ("8-30d ", "8_30d"),
                       ("31-90d", "31_90d")):
        evs = cal.get(key) or []
        if not evs:
            print(f"  {label}  none found")
            continue
        for e in evs:
            print(f"  {label}  {e['event_time']}  {e['ticker']:<6} "
                  f"{e['kind']:<10} {e['affected_metric'][:44]}")
    cov = cal.get("coverage") or {}
    print(f"  coverage: {cov.get('grade', '?')} — NOT covered: "
          f"{', '.join(cov.get('uncovered', [])[:5])}")
    print(f"  {cov.get('warning', '')}")

    if b["threats"]:
        print("\nTHREATS")
        for t in b["threats"]:
            print(f"  {t['ticker']:<6} {t['why']}")

    if b["opportunities"]:
        print(f"\nOPPORTUNITY RADAR — {b['opportunity_scope']}")
        for o in b["opportunities"]:
            mark = "IN TARGET" if o["in_target_portfolio"] else "         "
            print(f"  {o['ticker']:<6} {mark}  CE "
                  f"{(o['certainty_equivalent'] or 0):+.3f}  E[R] "
                  f"{pct(o['expected_return'])}  upside "
                  f"{pct(o['implied_upside'])}  "
                  f"{o['state'].get('n_analysts') or 0:>3} analysts"
                  f"{'  BINARY' if o['state'].get('binary_event_risk') else ''}")

    if b["replacements"]:
        print("\nREPLACEMENTS — decomposition of the one solved target portfolio")
        for s in b["replacements"]:
            flag = "OK    " if s["clears_own_cost_hurdle"] else "DISSENT"
            print(f"  {flag} {s['candidate']} funded by "
                  f"{s['funded_by']}  {money(s['dollars'])}")
            print(f"        edge {s['replacement_edge']:+.3f} = gross "
                  f"{s['gross_edge']:+.3f} - switch cost {s['switch_cost']:.4f} "
                  f"(expected-return units, CE lambda=1)")
            if not s["clears_own_cost_hurdle"]:
                print(f"        {s['reading']}")

    ms = b["model_status"]
    print("\n" + BAR)
    print("MODEL STATUS — how much of the above to believe today")
    print(BAR)
    print(f"  book confirmed          {ms['book_confirmed']}"
          f"{'' if ms['book_confirmed'] else '   <- every dollar above is SIMULATED'}")
    print(f"  valuation               {ms['valuation_basis']} "
          f"[{ms['valuation_grade']}], NAV complete: {ms['nav_complete']}")
    print(f"  positions               {ms['positions']} "
          f"({ms['decisionable_positions']} decisionable, "
          f"{ms['review_positions']} in REVIEW)")
    print(f"  evidence completeness   {ms['mean_evidence_completeness']:.0%} of "
          f"the fields we would want")
    print(f"  reliability discount    "
          f"{ms['mean_reliability_multiplier']} (UNCALIBRATED heuristic)")
    print(f"  analyst sources         {', '.join(ms['analyst_sources'])}")
    print(f"  target revisions        {ms['target_revision_fields']}")
    print(f"  analyst PIT ledger      {ms['analyst_ledger'].get('rows', 0)} rows, "
          f"{ms['analyst_ledger'].get('distinct_days', 0)} distinct day(s)")
    print(f"  catalyst coverage       {ms['catalyst_coverage'][:120]}")
    print(f"  return model            {ms['return_model_grade']}")
    if ms.get("volatility_fallbacks"):
        print(f"  ! GUESSED VOLATILITY    {', '.join(ms['volatility_fallbacks'])}"
              f" — sized off a fallback, not a measurement")
    if ms.get("binary_check_did_not_run"):
        print(f"  ! BINARY CHECK SKIPPED  "
              f"{', '.join(ms['binary_check_did_not_run'])}"
              f" — treated as non-binary, the LESS conservative assumption")
    if (ms.get("analyst_ledger") or {}).get("malformed_rows"):
        print(f"  ! LEDGER CORRUPTION     "
              f"{ms['analyst_ledger']['malformed_rows']} unreadable row(s)")
    ss = ms.get("scenario_sensitivity")
    if ss:
        print(f"  scenario sensitivity    P(target) "
              f"{prob(ss['p_reach_target_low'])} .. "
              f"{prob(ss['p_reach_target_high'])} "
              f"(base {prob(ss['p_reach_target_base'])})")
    print(f"  last refresh            {ms['last_refresh']}")
    if ms["book_problems"]:
        print("  book problems:")
        for p in ms["book_problems"]:
            print(f"    - {p}")

    print("\n" + b["evidence_note"])
    if w.get("available"):
        print(w["headline"])

    if a.record:
        out = pm_journal.record_brief(b, note="morning_brief CLI")
        print(f"\njournal: {out['written']} instructions recorded at "
              f"{out['path']}")
        if out.get("caveat"):
            print(f"         {out['caveat']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
