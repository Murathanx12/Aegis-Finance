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


def _us_bars(symbols=None):
    """The survivorship-free US panel, as `xs_ranker.load_bars` builds it.

    With `symbols`, the filter is pushed INTO the parquet read (pyarrow
    `filters=`), so only the held names' rows are ever materialised: the
    unfiltered read of both deep panels is 8.6M rows and peaked at 3.7 GB in the
    2026-09-28 rehearsal, which the daily pass must not need. The result is the
    same frame the full load gives for those symbols (first occurrence per
    (symbol, date) across the panels in order, sorted, index reset) --
    `test_llm_portfolio_cli.py` pins the equality."""
    import pandas as pd

    from backend.services import xs_ranker as XR
    paths = XR.survivorship_free_paths()
    if symbols is None:
        return XR.load_bars(paths)
    syms = sorted({str(x) for x in symbols})
    frames = []
    for pth in paths:
        pth = Path(pth)
        if not pth.exists():
            raise XR.RankerError(f"no bars panel at {pth}")
        df = pd.read_parquet(pth, filters=[("symbol", "in", syms)] if syms else None)
        if not syms:
            df = df.iloc[0:0]
        missing = XR._BAR_COLUMNS - set(df.columns)
        if missing:
            raise XR.RankerError(f"{pth.name} is missing columns {sorted(missing)}")
        frames.append(df)
    out = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]
    out["date"] = pd.to_datetime(out["date"])
    out = out.drop_duplicates(subset=["symbol", "date"], keep="first")
    return out.sort_values(["symbol", "date"], kind="mergesort").reset_index(drop=True)


def pull_today(now=None):
    """The `today` a grade passes to `global_prices.ensure`.

    `ensure` caches only bars dated BEFORE its `today` (a bar dated today could
    be intraday). With the UTC date, the 06:30 HKT daily pass (22:30 UTC, 18:30
    ET, after the close) would drop the session that has just CLOSED, and every
    URTH-benchmarked book and every ETF-only twin would sit a session behind
    the SPY books. So: the day after the last CLOSED XNYS session (16:20 ET, the
    system_health rule), never earlier than the UTC date. A bar dated on or
    before a closed US session is complete for US, European and Asian listings
    at that moment (Tokyo opens 00:00 UTC)."""
    from datetime import timedelta

    from backend.services import system_health as SH
    now = now or datetime.now(timezone.utc)
    return max(now.date(), SH.last_closed_session(now) + timedelta(days=1))


def required_series(books) -> list[str]:
    """Every series a grade must PULL rather than assume: each book's benchmark
    and `config.LLM_BOOK_REQUIRED_SERIES` (URTH, the sector-ETF twins' ETFs,
    SPY/IWM/SMH/MTUM)."""
    from backend import config as C
    out = set(C.LLM_BOOK_REQUIRED_SERIES) | {LP.benchmark_of(b) for b in books}
    return sorted(out)


def series_refusals(bars, want, *, failed=(), pulled: bool = True) -> list[dict]:
    """A required series with no bars at all, or whose newest bar is behind the
    union panel's newest SPY/union date, is a NAMED refusal on the grade."""
    import pandas as pd
    if len(bars):
        spy = bars.loc[bars["symbol"] == "SPY", "date"]
        ref = pd.Timestamp(spy.max() if len(spy) else bars["date"].max())
        newest = bars.groupby("symbol")["date"].max()
    else:
        ref, newest = None, {}
    out = []
    for sym in want:
        if sym not in newest:
            why = ("NO_BARS after the pull" if pulled
                   else "NO_BARS (--no-pull: the global cache as is)")
            out.append({"symbol": sym,
                        "why": why + (" (pull failed)" if sym in failed else "")})
        elif ref is not None and pd.Timestamp(newest[sym]) < ref:
            out.append({"symbol": sym,
                        "why": f"STALE: bars through {pd.Timestamp(newest[sym]).date()}, "
                               f"the panel reaches {ref.date()}"})
    return out


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


def grade_run(*, no_pull: bool = False, now=None, ensure=None, read_cache=None,
              us_bars=None, books=None, write: bool = True, out=print) -> dict:
    """The daily leaderboard, as a function (the CLI and the daily pass call it).

    Returns a summary: `status` (ok | nothing_to_do | refused), the leaderboard
    path, `bars_through`, `status_counts`, `series_refusals` and the counts a
    reader checks first. Never raises for a missing series: it is NAMED."""
    from datetime import timedelta

    import pandas as pd

    from backend.services import global_prices as GP

    books = LP.read_books() if books is None else books
    if not books:
        return {"status": "nothing_to_do", "why": "no frozen books yet"}
    need = LP.book_tickers(books)
    want = required_series(books)
    us = (us_bars if us_bars is not None else _us_bars)(need | set(want))
    us = us[us["symbol"].isin(need | set(want))]
    start = (min(pd.Timestamp(b["asof"]) for b in books) - timedelta(days=120)).date()
    failed: list = []
    pull = None
    if not no_pull:
        # Every book ticker, not only the non-US ones: the US panel is refreshed
        # by hand and a book frozen after its last bar would sit PENDING forever.
        # Plus the REQUIRED series (URTH, the twins' ETFs, the factor ETFs): pulled,
        # never assumed to be in some local panel.
        today = pull_today(now)
        glob = (ensure or GP.ensure)(sorted(need | set(want)), start=start, today=today)
        rc_ = glob.attrs.get("receipt", {})
        failed = list(rc_.get("failed", []))
        pull = {"today": str(today), "n_ok": rc_.get("n_ok"),
                "n_requested": rc_.get("n_requested"),
                "n_pulled_now": rc_.get("n_pulled_now"), "failed": failed[:50]}
        out(f"global_prices (today={today}): {rc_.get('n_ok')}/{rc_.get('n_requested')} "
            f"priced, {rc_.get('n_pulled_now')} pulled now, failed {failed[:10]}")
    else:
        glob = (read_cache or GP.read_cache)()
        glob = glob[glob["symbol"].isin(need | set(want))] if len(glob) else None
    bars = LP.union_bars(us, glob)
    refusals = series_refusals(bars, want, failed=failed, pulled=not no_pull)
    lb = LP.leaderboard(books, bars)
    print_table(lb, out=out)
    if any(r.get("benchmark_is_proxy") for r in lb["books"]):
        out("CAVEAT: " + lb["wls_caveat"])
    for r in refusals:
        out(f"SERIES REFUSED: {r['symbol']}: {r['why']}")
    lb.update({"receipt": "llm_portfolio_leaderboard",
               "licence": "PRODUCT_EXPERIMENT",
               "pull": pull or {"mode": "--no-pull (global cache as is)"},
               "required_series": want,
               "series_refusals": refusals,
               "read_me_first": ("Every book is NET of an empirical entry cost by "
                                 "liquidity band and measured against its benchmark "
                                 "over the same window, and against its own twins. "
                                 "A book that returns +8% while SPY returns +11% "
                                 "has LOST. `grade_rule_version` 2 (entry on or after "
                                 "2026-09-28): a name without a valid entry open waits "
                                 "in cash at 0%, never re-weighted.")})
    path = None
    if write:
        day = (now or datetime.now(timezone.utc)).date()
        path = LP.ledger_dir() / f"leaderboard_{day}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(lb, indent=1, default=str), encoding="utf-8")
        tmp.replace(path)                               # idempotent per day
        out(f"-> {path}")
    sc = lb.get("status_counts") or {}
    return {"status": "ok" if sc.get("OK") else "nothing_to_do",
            "leaderboard": str(path) if path else None,
            "bars_through": lb.get("bars_through"), "status_counts": sc,
            "n_books": lb.get("n_books"), "n_twins": lb.get("n_twins"),
            "n_refused": len(lb.get("refused") or []),
            "n_benchmark_missing": lb.get("n_benchmark_missing"),
            "n_deferred_entry": len(lb.get("deferred_entry") or []),
            "n_suspect_splits": len(lb.get("suspect_splits") or []),
            "grade_rule_versions": lb.get("grade_rule_versions"),
            "series_refusals": refusals, "pull": pull}


def cmd_grade(a) -> int:
    summary = grade_run(no_pull=a.no_pull)
    if getattr(a, "json", False):
        # one machine-readable line for the daily pass (`<<<{...}>>>`)
        print("<<<" + json.dumps(summary, default=str) + ">>>")
    if summary.get("status") == "nothing_to_do" and summary.get("why"):
        print(summary["why"] + ". `freeze` one first.")
        return 2
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
                   help="use the global price cache as is (no yfinance call). Offline "
                        "rehearsals only: URTH and the sector ETFs are in no local "
                        "panel, so competition books and ETF twins go ungraded")
    g.add_argument("--json", action="store_true",
                   help="end with one `<<<{summary}>>>` line (the daily pass reads it)")
    g.set_defaults(fn=cmd_grade)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
