"""CLI for the LLM portfolio experiment. Build a briefing, freeze a book, grade.

    python -m scripts.llm_portfolio brief                 # -> briefing_<date>.json
    python -m scripts.llm_portfolio freeze book.json      # commit it, immutably
    python -m scripts.llm_portfolio freeze book.json --twins [--ai-draft d.json]
    python -m scripts.llm_portfolio freeze draft.json --twins --accept-draft
    python -m scripts.llm_portfolio grade                 # the DAILY leaderboard
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
    "kind": "personal",
    "objective": "maximise absolute return over 126 sessions, no benchmark constraint",
    "model": "fable-5.1",
    "strategy": "Say in a paragraph WHY this book is shaped the way it is. What "
                "you are betting on, what would make you wrong, and what you "
                "deliberately did not buy. This is read when the book is graded.",
    "horizon_days": [1, 5, 21, 126],
    "positions": [
        {"ticker": "EXAMPLE", "weight": 0.10,
         "theme": "semis",
         "thesis": "one or two sentences, specific, naming the fields in the "
                   "briefing that drove it",
         "falsifier": "the dated observation that would prove this wrong"},
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


def _us_bars():
    from backend.services import xs_ranker as XR
    return XR.load_bars(XR.survivorship_free_paths())


def freeze_with_twins(books: list[dict], *, brief=None, us_bars=None,
                      resolve=None, twins: bool = False, seed: int = 20260925,
                      ai_draft=None, check_prices: bool = True,
                      accept_draft: bool = False,
                      out=print) -> tuple[int, list[dict]]:
    """Freeze each book (and optionally its twins) and append them to the
    ledger. Returns (rc, frozen records). Shared by `freeze` and the factory.

    A book that declares `twins_requested` gets exactly those twins (plus
    `ai_only` when a draft is given); otherwise all of them."""
    universe = (set(us_bars["symbol"].unique())
                if (check_prices and us_bars is not None) else None)
    rc, frozen = 0, []
    for b in books:
        try:
            rec = LP.freeze(b, briefing=brief, universe=universe, resolve=resolve,
                            accept_draft=accept_draft)
        except LP.Refusal as exc:
            # A refusal is a finding: it names exactly what the model got wrong
            # about the contract, which is the feedback that improves the next
            # book. It is not repaired here.
            out(f"  {b.get('name', '?')}: {exc}")
            rc = 2
            continue
        LP.append_book(rec)
        frozen.append(rec)
        out(f"  FROZEN {rec['name']:<28} {rec['book_id']}  {rec['kind']:<11} "
            f"{rec['n_positions']:>3} pos, max {rec['max_weight']*100:.1f}%, "
            f"cash {rec['cash_weight']*100:.1f}%"
            + (f", global-priced {rec['priced_by'].get('global_prices')}"
               if rec['priced_by'].get('global_prices') else ""))
        if twins:
            try:
                tw = LP.twins(rec, asof=rec["asof"], seed=seed, bars=us_bars,
                              ai_draft=ai_draft)
            except LP.Refusal as exc:
                out(f"    twins REFUSED: {exc}")
                rc = 2
                continue
            want = rec.get("twins_requested")
            if want:
                want = set(want) | ({"ai_only"} if ai_draft is not None else set())
                skipped = sorted(set(tw) - want)
                if skipped:
                    out(f"    twins not requested, not frozen: {skipped}")
                tw = {k: v for k, v in tw.items() if k in want}
            for k, t in tw.items():
                LP.append_book(t)
                frozen.append(t)
                out(f"    twin {k:<17} {t['book_id']}  "
                    f"{', '.join(p['ticker'] for p in t['positions'][:6])}"
                    + (" ..." if len(t['positions']) > 6 else ""))
    return rc, frozen


def cmd_freeze(a) -> int:
    raw = json.loads(Path(a.file).read_text(encoding="utf-8"))
    books = raw if isinstance(raw, list) else [raw]
    brief = None
    if a.briefing:
        brief = json.loads(Path(a.briefing).read_text(encoding="utf-8"))
    elif LP.briefing_path().exists():
        brief = json.loads(LP.briefing_path().read_text(encoding="utf-8"))
    ai_draft = (json.loads(Path(a.ai_draft).read_text(encoding="utf-8"))
                if a.ai_draft else None)

    from backend.services import global_prices as GP
    us_bars = _us_bars() if (a.twins or not a.no_price_check) else None
    rc, _ = freeze_with_twins(books, brief=brief, us_bars=us_bars,
                              resolve=GP.resolve, twins=a.twins, seed=a.seed,
                              ai_draft=ai_draft,
                              check_prices=not a.no_price_check,
                              accept_draft=a.accept_draft)
    if rc == 0:
        print(f"-> {LP.books_path()}")
    return rc


def _pct(v, w=7):
    return f"{v*100:+{w}.2f}%" if v is not None else " " * (w - 1) + "n/a"


def print_table(lb: dict, *, rows: int = 20, out=print) -> None:
    """The 20-line daily check: parents sorted by vs-benchmark, twins as columns."""
    parents = [r for r in lb["books"] if not r["parent_book_id"]]
    parents.sort(key=lambda r: (r["vs_benchmark"] is None,
                                -(r["vs_benchmark"] or 0.0)))
    out(f"{'book':<30}{'kind':<12}{'sess':>5}{'net':>9}{'bench':>9}"
        f"{'vs_b':>9}{'vs_ew':>9}{'vs_etf':>9}{'vs_rnd':>9}")
    for r in parents[:max(rows - 2, 1)]:
        if r["status"] != "OK":
            out(f"{r['name'][:29]:<30}{(r['kind'] or ''):<12} {r['status']}: "
                f"{(r['why'] or '')[:60]}")
            continue
        out(f"{r['name'][:29]:<30}{(r['kind'] or ''):<12}{r['sessions'] or 0:>5}"
            f"{_pct(r['net_to_date'], 8)}{_pct(r['benchmark_to_date'], 8)}"
            f"{_pct(r['vs_benchmark'], 8)}{_pct(r.get('vs_ew'), 8)}"
            f"{_pct(r.get('vs_sector_etf'), 8)}{_pct(r.get('vs_random_same_band'), 8)}")
    kinds = "  ".join(f"{k}: {v['n_beat_benchmark']}/{v['n_graded']} beat bench, "
                      f"mean {_pct(v['mean_vs_benchmark'], 6)}"
                      for k, v in sorted(lb["by_kind"].items()))
    out(f"{lb['n_books']} books + {lb['n_twins']} twins, bars through "
        f"{lb['bars_through']}.  {kinds}")


def cmd_grade(a) -> int:
    from datetime import timedelta

    import pandas as pd

    from backend.services import global_prices as GP

    books = LP.read_books()
    if not books:
        print("no frozen books yet. `freeze` one first.")
        return 2
    need = LP.book_tickers(books)
    us = _us_bars()
    us = us[us["symbol"].isin(need)]
    glob = None
    if not a.no_pull:
        start = (min(pd.Timestamp(b["asof"]) for b in books)
                 - timedelta(days=120)).date()
        # Every book ticker, not only the non-US ones: the US panel is refreshed
        # by hand and a book frozen after its last bar would sit PENDING forever.
        glob = GP.ensure(sorted(need), start=start)
        rc_ = glob.attrs.get("receipt", {})
        print(f"global_prices: {rc_.get('n_ok')}/{rc_.get('n_requested')} priced, "
              f"{rc_.get('n_pulled_now')} pulled now, failed {rc_.get('failed', [])[:10]}")
    else:
        glob = GP.read_cache()
        glob = glob[glob["symbol"].isin(need)] if len(glob) else None
    bars = LP.union_bars(us, glob)
    lb = LP.leaderboard(books, bars)
    print_table(lb)
    if any(r.get("benchmark_is_proxy") for r in lb["books"]):
        print("CAVEAT: " + lb["wls_caveat"])
    lb.update({"receipt": "llm_portfolio_leaderboard",
               "licence": "PRODUCT_EXPERIMENT",
               "read_me_first": ("Every book is NET of an empirical entry cost by "
                                 "liquidity band and measured against its benchmark "
                                 "over the same window, and against its own twins. "
                                 "A book that returns +8% while SPY returns +11% "
                                 "has LOST.")})
    day = datetime.now(timezone.utc).date()
    p = LP.ledger_dir() / f"leaderboard_{day}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(lb, indent=1, default=str), encoding="utf-8")
    tmp.replace(p)                                  # idempotent per day
    print(f"-> {p}")
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
    f.add_argument("--twins", action="store_true",
                   help="also freeze ew / sector_etf / spy|urth / random_same_band")
    f.add_argument("--ai-draft", default=None,
                   help="the AI-only draft JSON; adds an `ai_only` twin")
    f.add_argument("--seed", type=int, default=20260925,
                   help="seed of the random_same_band twin")
    f.add_argument("--accept-draft", action="store_true",
                   help="freeze a DRAFT* state anyway; recorded on the book as "
                        "draft_accepted_by_override")
    f.add_argument("--no-price-check", action="store_true",
                   help="skip the US-panel / global_prices priceability refusal")
    f.set_defaults(fn=cmd_freeze)

    g = sub.add_parser("grade", help="daily leaderboard: every book and twin "
                                     "vs its benchmark and its twins")
    g.add_argument("--no-pull", action="store_true",
                   help="use the global price cache as is (no yfinance call)")
    g.set_defaults(fn=cmd_grade)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
