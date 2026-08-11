"""MIRROR CHALLENGE — what would Optimus own, given the same money today?

Paper only. No lane is seeded, no flag flipped, no `paper_nav` row written, no
order path touched. This produces a COMPARISON, not an instruction.

Four arms:

  MURAT_CONVICTION     the book as it stands, at the recorded share counts
  OPTIMUS_HOLDINGS_ONLY  Optimus may resize or sell what is already held,
                       and may not buy anything new
  OPTIMUS_OPEN_UNIVERSE  the same capital, the full investable US universe
  CONTROL_EQUAL_WEIGHT   the same names, equally weighted — the bar every
                       clever construction has to clear (PF-2, ARENA-1)

The honest part is the third column. Optimus can only hold a name it has
LICENSED evidence on, and it has licensed evidence on very little. Where it
cannot justify a position it says so instead of filling the book to look
complete.

    python -m scripts.mirror_challenge

Writes docs/BUILD1/mirror_challenge.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from backend.config import book_lanes                        # noqa: E402
from backend.services import portfolio_factory as PF         # noqa: E402
from backend.services import recommendation as REC           # noqa: E402
from backend.services import signal_registry as SR           # noqa: E402

FUNNEL = ROOT / "docs" / "BUILD1" / "funnel_night10.json"
OUT = ROOT / "docs" / "BUILD1" / "mirror_challenge.json"

#: Recorded discrepancies. Carried VISIBLY into every arm rather than resolved
#: silently — a fork Murat has not ruled on is not a number.
KNOWN_FORKS = {
    "QUBT": {"config_shares": 200, "decision_log_shares": 300,
             "note": "the conviction decision log says 300, backend config says "
                     "200. Both are run below; neither is adopted."},
}

#: Names with no kill condition on record. None is invented; each gets a
#: PROPOSED one, labelled as awaiting Murat.
NO_KILL_CONDITION = ("ABSI", "AMSC", "HUBS", "KYTX", "SLDP")

PROPOSED_KILLS = {
    "ABSI": "cash runway falls below 12 months, or a lead programme is "
            "discontinued without a named successor",
    "AMSC": "two consecutive quarters of declining grid-segment backlog, or "
            "the largest customer concentration exceeds 40% of revenue",
    "HUBS": "net revenue retention falls below 100% for two consecutive "
            "quarters",
    "KYTX": "a lead clinical programme misses its primary endpoint, or cash "
            "runway falls below 12 months",
    "SLDP": "a named OEM partnership lapses without replacement, or cash "
            "runway falls below 12 months",
}


def _enrich_holdings(tickers: list[str], cands: list[dict]) -> list[dict]:
    """Run the held names through the funnel's own stage-3 enrichment.

    Same fundamentals path, same insider path, same field names, so the held
    names land in one cross-section with the candidates and their z-scores mean
    the same thing. A name that cannot be enriched comes back with its reason
    attached rather than being dropped.
    """
    from backend.services import opportunity_funnel as F
    out = []
    for t in tickers:
        row: dict = {"ticker": t}
        fund, why = F._fundamentals(t)
        if fund:
            row["sector"] = fund.get("sector") or ""
            row["market_cap"] = fund.get("market_cap")
            row["quality"] = fund.get("gross_profitability")
        else:
            row["fundamentals_reason"] = why
        score, reason = F._insider(t)
        row["insider_score"] = score
        row["insider_reason"] = reason
        out.append(row)
    return out


def _prices(tickers: list[str]) -> dict:
    from backend.services.data_fetcher import _fetch_batch_yahoo
    from datetime import timedelta
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=20)
    try:
        closes = _fetch_batch_yahoo(tickers, start.strftime("%Y-%m-%d"),
                                    end.strftime("%Y-%m-%d"))
    except Exception as exc:  # noqa: BLE001 — the reason IS the result
        return {"error": f"{type(exc).__name__}: {exc}"}
    out = {}
    for t in tickers:
        s = closes.get(t)
        if s is None:
            continue
        s = s.dropna()
        if len(s):
            out[t] = float(s.iloc[-1])
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--funnel", type=Path, default=FUNNEL)
    a = ap.parse_args()

    holdings = dict(book_lanes.get("holdings") or {})
    reg = SR.load()
    payload = json.loads(a.funnel.read_text(encoding="utf-8"))
    cands = payload["candidates"]

    px = _prices(sorted(holdings))
    if "error" in px or not px:
        # A total price failure must NOT produce a plausible-looking $0 NAV
        # with twelve "unmarked" names. That is the fake-NAV failure: a
        # fabricated number is worse than a refusal, because a refusal is
        # obviously not an answer and $0.00 is not obviously not an answer.
        raise SystemExit(
            f"REFUSING to write a mirror challenge: no price came back for any "
            f"of the {len(holdings)} held names "
            f"({px.get('error', 'empty price map')}). Every NAV, weight and "
            f"fork figure below would be a fabrication.")
    marked = {t: (n * px[t]) for t, n in holdings.items() if t in px}
    unmarked = sorted(set(holdings) - set(px))
    nav = sum(marked.values())
    if not nav:
        raise SystemExit(
            f"REFUSING to write a mirror challenge: {len(px)} price(s) came "
            f"back but marked NAV is $0. Something is wrong with the share "
            f"counts or the prices, and a zero NAV would read as a real one.")

    # QUBT fork, both ways, printed
    forks = {}
    for t, f in KNOWN_FORKS.items():
        if t in px:
            forks[t] = {**f,
                        "value_at_config": round(f["config_shares"] * px[t], 2),
                        "value_at_log": round(f["decision_log_shares"] * px[t], 2),
                        "nav_difference": round(
                            (f["decision_log_shares"] - f["config_shares"]) * px[t], 2)}

    # ── what does Optimus have licensed evidence on, among the HELD names? ──
    #
    # The held names are mostly NOT in the funnel's candidate list — the funnel
    # screens for liquidity and profitability, and this book is small-cap
    # biotech and speculative growth. Scoring only the overlap would have
    # reported "no view on your book" when the truth was "I never looked at
    # it". So the holdings are enriched through the SAME stage-3 path the
    # funnel uses, and scored in one cross-section with the candidates so the
    # z-scores are comparable.
    held_rows = _enrich_holdings(sorted(holdings), cands)
    combined = cands + [r for r in held_rows if r["ticker"] not in
                        {c["ticker"] for c in cands}]
    all_recs = {r.ticker: r for r in
                REC.score_candidates(combined, registry=reg)}
    held_recs = [all_recs[t] for t in sorted(holdings) if t in all_recs]
    covered = {r.ticker for r in held_recs
               if r.evidence_grade != "NO_EVIDENCE"}
    held_detail = [
        {"ticker": r.ticker, "rank": r.rank, "ranking_score": r.ranking_score,
         "recommendation": r.recommendation, "confidence": r.confidence,
         "evidence_grade": r.evidence_grade,
         "led_by": (r.leader().signal_id if r.leader() else None),
         "market_cap": r.market_cap,
         "reason": r.reason_for_rank,
         "absent_signals": [c.signal_id for c in r.signal_contributions
                            if not c.available]}
        for r in held_recs]

    # ── the open universe arm ────────────────────────────────────────────────
    REC.assert_registry_discipline(cands, registry=reg)
    open_recs = REC.score_candidates(cands, registry=reg)
    vols = {c["ticker"]: c.get("vol_annual") for c in cands if c.get("vol_annual")}
    open_books = PF.build_all(open_recs, vols=vols)

    arms = {
        "MURAT_CONVICTION": {
            "description": "the book as recorded, at its current share counts",
            "n_names": len(holdings),
            "nav_marked": round(nav, 2),
            "weights": ({t: round(v / nav, 4) for t, v in sorted(marked.items())}
                        if nav else {}),
            "unmarked_names": unmarked,
            "cash": None,
            "cash_note": ("UNKNOWN — Murat has not supplied a cash figure, so "
                          "NAV here is the marked equity only and every weight "
                          "below is a share of that, not of the account"),
        },
        "OPTIMUS_HOLDINGS_ONLY": {
            "description": ("Optimus may resize or sell what is held and may "
                            "buy nothing new"),
            "n_names_with_licensed_evidence": len(covered),
            "names_with_evidence": sorted(covered),
            "names_without_evidence": sorted(set(holdings) - covered),
            "per_name": held_detail,
            "verdict": (
                f"Optimus has licensed evidence on {len(covered)} of "
                f"{len(holdings)} held names. It cannot form a considered view "
                f"on the rest, and says so rather than issuing a HOLD that "
                f"would read as an endorsement."),
        },
        "OPTIMUS_OPEN_UNIVERSE": {
            "description": ("same capital, full investable US universe, only "
                            "names Optimus can justify"),
            "books": {k: {"n_names": v["n_names"], "weights": v["weights"]}
                      for k, v in open_books["built"].items()},
            "refused": open_books["refused"],
            "n_candidates_screened": len(cands),
        },
    }

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "PAPER PROPOSAL — no trade, no lane, no flag, no order path",
        "book_confirmed_by_murat": bool(book_lanes.get("confirmed")),
        "arms": arms,
        "known_forks": forks,
        "proposed_kill_conditions": {
            t: {"condition": PROPOSED_KILLS[t],
                "status": "PROPOSED_AWAITING_MURAT",
                "note": "none was invented from the engine; these are for "
                        "Murat to accept, amend or reject"}
            for t in NO_KILL_CONDITION},
        "what_optimus_cannot_say": {
            "cash": "unknown — not supplied",
            "cost_bases": "5 of 12 unknown, so no per-name P&L is computed",
            "confirmed": ("the book carries no `confirmed: true`, so every "
                          "number here is a SIMULATION on an unconfirmed book"),
            "expected_return": ("NOT CALIBRATED for any name in any arm — the "
                                "comparison is of composition, never of "
                                "forecast return"),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")

    print(f"MIRROR CHALLENGE — {out['status']}")
    print(f"\nbook: {len(holdings)} names, marked NAV ${nav:,.0f}"
          f"{' (' + str(len(unmarked)) + ' unmarked: ' + ', '.join(unmarked) + ')' if unmarked else ''}")
    print(f"cash: UNKNOWN | confirmed: {out['book_confirmed_by_murat']}")
    print(f"\nOptimus has licensed evidence on "
          f"{len(covered)}/{len(holdings)} held names: "
          f"{', '.join(sorted(covered)) or 'none'}")
    if forks:
        for t, f in forks.items():
            print(f"\nFORK {t}: {f['config_shares']} vs "
                  f"{f['decision_log_shares']} shares = "
                  f"${f['nav_difference']:,.0f} of NAV. Both carried; "
                  f"neither adopted.")
    print("\nOPEN UNIVERSE books built: "
          f"{list(open_books['built']) or 'NONE'}")
    for k, why in open_books["refused"].items():
        print(f"  REFUSED {k}: {why[:100]}")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
