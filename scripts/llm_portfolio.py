"""CLI for the LLM portfolio experiment. Build a briefing, freeze a book, grade.

    python -m scripts.llm_portfolio brief                 # -> briefing_<date>.json
    python -m scripts.llm_portfolio freeze book.json      # commit it, immutably
    python -m scripts.llm_portfolio grade                 # NAV every frozen book
    python -m scripts.llm_portfolio template              # an empty book to fill

THE WORKFLOW THIS SUPPORTS
==========================
1. `brief` writes one JSON file holding every point-in-time fact we have on the
   whole eligible universe -- and an explicit list of what we do NOT have, so
   the model is not invited to hallucinate analyst targets that are 403 on this
   tier.
2. A session (Fable, or any model) reads that file and returns one or more
   books in the `template` shape. Several at once is the point: an aggressive
   ROI-maximising book and a beat-SPY book are different objectives and should
   be graded as different objects, not averaged.
3. `freeze` validates and content-hashes each one. After that it is evidence.
   The briefing's own hash is recorded inside the book, so there is no question
   later about what the allocator could see.
4. `grade` NAVs each book from the OPEN after its as-of date, net of the
   empirical entry cost, against SPY, at every horizon the book declared.

The point of the exercise is the comparison, so the honest report is the whole
table of books -- including the ones that lose.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import llm_portfolio as LP     # noqa: E402

TEMPLATE = {
    "name": "aggressive_roi_v1",
    "objective": "maximise absolute return over 126 sessions, no benchmark constraint",
    "model": "fable-5.1",
    "strategy": "Say in a paragraph WHY this book is shaped the way it is. What "
                "you are betting on, what would make you wrong, and what you "
                "deliberately did not buy. This is read when the book is graded.",
    "horizon_days": [1, 5, 21, 126],
    "positions": [
        {"ticker": "EXAMPLE", "weight": 0.10,
         "thesis": "one or two sentences, specific, naming the fields in the "
                   "briefing that drove it"},
        {"ticker": "CASH", "weight": 0.90,
         "thesis": "cash is a position and must be declared as one"},
    ],
}


def cmd_brief(a) -> int:
    brief = LP.build_briefing(asof=a.asof, max_names=a.max_names)
    p = Path(a.out) if a.out else LP.briefing_path(brief["asof"])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(brief, indent=1, default=str), encoding="utf-8")
    kb = p.stat().st_size // 1024
    print(f"briefing asof {brief['asof']}: {brief['n_names']:,} names, "
          f"hash {brief['briefing_hash']}, {kb:,} KB")
    print(f"  fundamentals attached to "
          f"{sum(1 for r in brief['rows'] if r.get('rev_qoq') is not None):,} names")
    print(f"  inflection_flag set on "
          f"{sum(1 for r in brief['rows'] if r.get('inflection_flag')):,} names")
    print(f"  NOT in the briefing: {len(brief['what_is_NOT_here'])} declared gaps")
    print(f"-> {p}")
    return 0


def cmd_template(a) -> int:
    print(json.dumps(TEMPLATE, indent=1))
    return 0


def cmd_freeze(a) -> int:
    raw = json.loads(Path(a.file).read_text(encoding="utf-8"))
    books = raw if isinstance(raw, list) else [raw]
    brief = None
    if a.briefing:
        brief = json.loads(Path(a.briefing).read_text(encoding="utf-8"))
    elif LP.briefing_path().exists():
        brief = json.loads(LP.briefing_path().read_text(encoding="utf-8"))

    rc = 0
    for b in books:
        try:
            rec = LP.freeze(b, briefing=brief)
        except LP.Refusal as exc:
            # A refusal is a finding: it names exactly what the model got wrong
            # about the contract, which is the feedback that improves the next
            # book. It is not repaired here.
            print(f"  {b.get('name', '?')}: {exc}")
            rc = 2
            continue
        LP.append_book(rec)
        print(f"  FROZEN {rec['name']:<24} {rec['book_id']}  "
              f"{rec['n_positions']:>3} positions, max weight "
              f"{rec['max_weight']*100:.1f}%, {rec['n_tiny_positions']} below "
              f"{LP.TINY_WEIGHT*100:.1f}%")
    if rc == 0:
        print(f"-> {LP.books_path()}")
    return rc


def cmd_grade(a) -> int:
    from backend.services import xs_ranker as XR
    books = LP.read_books()
    if not books:
        print("no frozen books yet. `freeze` one first.")
        return 2
    bars = XR.load_bars(XR.survivorship_free_paths())
    print(f"{len(books)} book(s), bars through {str(bars['date'].max())[:10]}\n")
    out = []
    for rec in books:
        g = LP.grade(rec, bars)
        out.append(g)
        if g.get("status") != "OK":
            print(f"{g['name']:<26} {g['status']}: {g.get('why')}")
            continue
        print(f"{g['name']:<26} {g['n_positions']:>3} pos, entry cost "
              f"{g['entry_cost_bps']:.0f}bps"
              + (f", {g['n_unpriceable']} unpriceable" if g['n_unpriceable'] else ""))
        for h, c in g["horizons"].items():
            if c.get("status") != "OK":
                print(f"     {h:>4}d  {c['status']}: {c.get('why')}")
                continue
            print(f"     {h:>4}d  net {c['net']*100:+7.2f}%  "
                  f"NAV ${c['nav_usd']:>12,.0f}  SPY "
                  f"{(c['spy'] or 0)*100:+6.2f}%  -> vs SPY "
                  f"{(c['vs_spy'] or 0)*100:+7.2f}%")
    res = {"receipt": "llm_portfolio_grade", "licence": "PRODUCT_EXPERIMENT",
           "graded_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "n_books": len(books), "books": out,
           "read_me_first": ("Every book is NET of an empirical entry cost by "
                             "liquidity band and measured against SPY over the "
                             "same window. A book that returns +8% while SPY "
                             "returns +11% has LOST.")}
    p = LP.ledger_dir() / f"grade_{date.today()}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(f"\n-> {p}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("brief", help="write the point-in-time briefing")
    b.add_argument("--asof", default=None)
    b.add_argument("--max-names", type=int, default=4000)
    b.add_argument("--out", default=None)
    b.set_defaults(fn=cmd_brief)

    t = sub.add_parser("template", help="print an empty book")
    t.set_defaults(fn=cmd_template)

    f = sub.add_parser("freeze", help="validate and commit a book (or a list)")
    f.add_argument("file")
    f.add_argument("--briefing", default=None)
    f.set_defaults(fn=cmd_freeze)

    g = sub.add_parser("grade", help="NAV every frozen book against SPY")
    g.set_defaults(fn=cmd_grade)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
