"""OPTIMUS INVESTMENT COMMITTEE — the morning decision page.

Turns the market funnel into an answer to "what should I own, why, and what
would make me wrong" — at $10k or at $250m. Machine-readable JSON beside a
human-readable page, both from the same objects.

    python -m scripts.investment_committee [--funnel PATH] [--out DIR]

What it refuses to do
---------------------

It never prints an expected return the engine cannot calibrate. Where the
evidence supports only an ORDERING, the page says "ranking score, percentile,
NOT CALIBRATED" and gives no dollar forecast. A number that looks like an
expected return and is not one is worse than no number, because it will be
multiplied by something.

It never lets a CLOSED signal rank a name. That is enforced upstream in
`recommendation.assert_registry_discipline`, which RAISES rather than warns —
so a broken ranking stops this page from printing at all.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# The build itself now lives in the service, shared with the API router and
# the composer. The strict contract is unchanged: build() RAISES when the
# ranking gate is dirty, and this script refuses to print.
from backend.services.investment_committee import build_page as build  # noqa: E402

DEFAULT_FUNNEL = ROOT / "docs" / "BUILD1" / "funnel_night10.json"
DEFAULT_OUT = ROOT / "docs" / "BUILD1"

HEADLINE_CAPITALS = (40_000.0, 1_000_000.0, 50_000_000.0)


def render(page: dict) -> str:
    L: list[str] = []
    add = L.append
    add("=" * 78)
    add("OPTIMUS INVESTMENT COMMITTEE".center(78))
    add(f"{page['generated_at']}  ·  {page['universe_screened']:,} US names screened"
        .center(78))
    add("=" * 78)

    add(f"\nRANKING GATE: {page['registry_gate']['status']}")
    for c in page["registry_gate"]["invariance_checks"]:
        add(f"  {c['signal_id']:<32} {c['grade']}/{c['role']}: "
            f"rho={c['spearman_rho']}, {c['n_names_moved']} names moved "
            f"-> {'cannot reorder the BUY list' if c['invariant_holds'] else 'CAN REORDER — VIOLATION'}")

    n, lic = page["n_candidates"], page["n_with_licensed_evidence"]
    add(f"\nEVIDENCE COVERAGE: {lic} of {n} candidates carry a signal this "
        f"programme licenses.")
    if lic < n:
        add(f"  The other {n - lic} are screened, liquid and priced — and the "
            f"engine has NOTHING it is allowed to say about them.")

    add("\n" + "-" * 78)
    add("TOP OPPORTUNITIES")
    add("-" * 78)
    add(f"{'#':>3} {'ticker':<7}{'price':>9}{'$bn':>9}{'score':>8}{'pct':>6}"
        f"  {'verdict':<9}{'conf':<7}{'grade':<10} led by")
    shown = 0
    for o in page["opportunities"]:
        if o["evidence_grade"] == "NO_EVIDENCE":
            continue
        shown += 1
        if shown > 25:
            break
        add(f"{o['rank']:>3} {o['ticker']:<7}{(o['price'] or 0):>9.2f}"
            f"{(o['market_cap'] or 0)/1e9:>9.2f}{o['ranking_score']:>8.3f}"
            f"{(o['percentile'] or 0):>6.0f}  {o['recommendation']:<9}"
            f"{o['confidence']:<7}{o['evidence_grade']:<10} {o['rank_led_by']}")
    if not shown:
        add("  (none — no candidate carries licensed evidence today)")

    add("\n" + "-" * 78)
    add("THE DETAIL")
    add("-" * 78)
    detail = [o for o in page["opportunities"]
              if o["evidence_grade"] != "NO_EVIDENCE"][:10]
    for o in detail:
        add(f"\n{o['rank']}. {o['ticker']} — {o['sector']}  "
            f"${(o['market_cap'] or 0)/1e9:.2f}bn  ${o['price']:.2f}")
        add(f"   VERDICT {o['recommendation']}  ·  ranking score "
            f"{o['ranking_score']:+.3f} ({o['percentile']:.0f}th pct)  ·  "
            f"confidence {o['confidence']}  ·  evidence {o['evidence_grade']}")
        add(f"   EXPECTED RETURN: {o['expected_return_basis']} — "
            f"the engine has an ordering here, not a forecast.")
        add(f"   WHY IT RANKS: {o['reason_for_rank']}")
        for c in o["signal_contributions"]:
            if c["rank_bearing"] and c["available"]:
                add(f"     + {c['signal_id']:<30} {c['contribution']:+.3f}  "
                    f"[{c['grade']}/{c['role']}] {c['basis']}")
        for c in o["signal_contributions"]:
            if not c["rank_bearing"] and c["available"] and c["role"] == "CLOSED":
                add(f"     · {c['signal_id']:<30} raw {c['raw_value']:+.3f}  "
                    f"NOT USED — {c['grade']}/{c['role']}")
        for c in o["signal_contributions"]:
            if not c["available"]:
                add(f"     ? {c['signal_id']:<30} ABSENT — {c['missing_reason']}")
        if o["risk_factors"]:
            add(f"   RISKS: {'; '.join(o['risk_factors'])}")
        if o["kill_condition"]:
            add(f"   KILL CONDITION ({o['kill_condition_status']}): "
                f"{o['kill_condition']}")
        if o["better_alternatives"]:
            add(f"   RANKED BELOW: {', '.join(o['better_alternatives'])}")
        cap = {c["capital"]: c for c in o["capacity"]}
        bits = []
        for lvl in HEADLINE_CAPITALS:
            row = cap.get(lvl)
            if row and row["weight"] > 0:
                bits.append(f"${lvl:,.0f}: ${row['position_usd']:,.0f} "
                            f"({row['days_to_exit']:.2f}d to exit"
                            f"{'' if row['tradeable'] else ' — BLOCKED'})")
        if bits:
            add(f"   CAPACITY: {' | '.join(bits)}")

    add("\n" + "-" * 78)
    add("THE BOOKS")
    add("-" * 78)
    for name, book in page["books"]["built"].items():
        tag = "  [CONTROL]" if book["is_control"] else ""
        add(f"\n{name}{tag} — {book['n_names']} names, {book['weighting']}, "
            f"cap {book['max_weight']:.0%}")
        add(f"   {book['description']}")
        row = " ".join(f"{n['ticker']} {100*n['weight']:.1f}%"
                       for n in book["names"][:12])
        add(f"   {row}")
    for name, why in page["books"]["refused"].items():
        add(f"\n{name} — REFUSED")
        add(f"   {why}")

    add("\n" + "-" * 78)
    add("CAPITAL FRONTIER — OPTIMUS_BALANCED")
    add("-" * 78)
    fr = page["capital_frontier"].get("OPTIMUS_BALANCED")
    if not fr:
        add("  OPTIMUS_BALANCED was refused, so there is no book to size. A "
            "frontier over an empty book would be a table of zeros pretending "
            "to be an answer.")
    if fr:
        add(f"{'capital':>14}{'tradeable':>11}{'blocked':>9}"
            f"{'wt blocked':>12}{'round trip':>12}")
        for lv in fr["levels"]:
            add(f"{lv['capital']:>14,.0f}{lv['n_names_tradeable']:>11}"
                f"{lv['n_names_blocked']:>9}{100*lv['weight_blocked']:>11.1f}%"
                f"{lv['round_trip_cost_pct_of_capital']:>11.3f}%")
        add(f"\n  {fr['impact_caveat']}")

    add("\n" + "-" * 78)
    add("HONESTY")
    add("-" * 78)
    for k, v in page["honesty"].items():
        add(f"  {k.upper()}: {v}")
    add("\n" + "=" * 78)
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--funnel", type=Path, default=DEFAULT_FUNNEL)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    a = ap.parse_args()

    page = build(a.funnel)
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "investment_committee.json").write_text(
        json.dumps(page, indent=1), encoding="utf-8")
    text = render(page)
    (a.out / "investment_committee.txt").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
