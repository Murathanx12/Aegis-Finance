"""The academic lane's caller (Q12, 2026-10-07).

    python -m scripts.research_lane --card <slug>   # run the lane for ONE card
    python -m scripts.research_lane --list          # which cards qualify today, run nothing
    python -m scripts.research_lane --due            # the weekly owner's own pick (task_keeper)

Reads a research-intake card (`docs/research_intake/cards/<slug>.md`), runs the
decision table in `backend/services/research_instruments.py` over its own
`## Needs evidence` questions, writes a per-card evidence file and the yield
receipt, and prints a one-line summary. Nothing is ever written into the card.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend.services import research_instruments as RI


def list_seed_cards(cards_dir: Path | None = None) -> list[str]:
    """Card slugs that both QUALIFY (an open-question verdict) and carry a
    `## Needs evidence` list -- the lane's own candidate set."""
    cards_dir = Path(cards_dir or RI.CARDS_DIR)
    out = []
    for p in sorted(cards_dir.glob("*.md")):
        text = p.read_text(encoding="utf-8")
        if RI.card_qualifies(text) and RI.card_needs_evidence(text):
            out.append(p.stem)
    return out


def pick_due_card(cards_dir: Path | None = None, opt: Path | None = None) -> str | None:
    """The least-recently-probed qualifying card (never probed sorts first)."""
    seeds = list_seed_cards(cards_dir)
    if not seeds:
        return None
    last: dict[str, str] = {}
    for r in RI._read_jsonl(RI.academic_ledger_path(opt)):
        slug = r.get("card_slug")
        if slug:
            last[slug] = max(last.get(slug, ""), str(r.get("t") or ""))
    seeds.sort(key=lambda s: last.get(s, ""))
    return seeds[0]


def _summary(rec: dict) -> dict:
    return {k: rec.get(k) for k in
            ("status", "refusal", "run_id", "path", "evidence_path", "queries_issued",
             "day_cap", "zero_kind", "card_verdicts", "needs_evidence", "instruments")}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--card", help="run the academic lane for this card slug")
    g.add_argument("--list", action="store_true", help="print qualifying card slugs, run nothing")
    g.add_argument("--due", action="store_true",
                   help="pick the least-recently-probed qualifying card and run it")
    a = ap.parse_args(argv)
    if a.list:
        print(json.dumps(list_seed_cards(), indent=2))
        return 0
    slug = a.card
    if a.due:
        slug = pick_due_card()
        if slug is None:
            print(json.dumps({"status": "NOTHING_TO_DO",
                              "reason": "no qualifying card carries a ## Needs evidence list"}))
            return 0
    rec = RI.probe_card(slug)
    print(json.dumps(_summary(rec), indent=2, default=str))
    return 0 if rec.get("status") == "OK" else 2


if __name__ == "__main__":
    sys.exit(main())
