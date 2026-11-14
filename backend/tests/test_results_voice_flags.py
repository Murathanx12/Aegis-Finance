"""claims-none (owner 2026-11-14): CLAIMS PROMOTED prints "none" until a label RISES against
the previous run's receipt, a fall prints LABELS LOWERED, and book_dna's FLAGS say beside the
label what the S69 fleet review had to work out by hand.

Every flag is pinned three ways (set, clear, CANNOT DETERMINE) on synthetic inputs. Dates are
derived from today (CLAUDE.md protocol item 5); the previous-receipt lookup is pinned to run
ids, with file mtimes deliberately inverted (protocol item 7). No network, no disk outside
tmp_path.
"""
from __future__ import annotations

import json
import os
import shutil
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend.services import book_dna as D
from backend.services import results_voice as RV

FIX = Path(__file__).parent / "fixtures" / "results_voice"
RID = "2026-10-06T235345Z"
CD = D.CANNOT_DETERMINE


def _sessions(n: int) -> list[str]:
    d = date.today() - timedelta(days=1)
    out = []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d -= timedelta(days=1)
    return sorted(out)


P = D.params()


def _series(dates: list[str], rb, rs) -> list:
    """[(date, r_book, r_spy)] for the periods ending dates[1:]."""
    return [(d, float(b), float(s)) for d, b, s in zip(dates[1:], rb, rs)]


def _book(**kw) -> dict:
    s = kw.pop("sessions", None)
    b = {"account": "bk", "family": "alpaca_fleet", "category": "strategy", "excess_pp": 1.0,
         "return_pct": 1.0, "sessions_graded": s, "inception": None, "last_mark": None,
         "weights": None, "_series": [], "tail": {}, "market_exposure": {}, "book_id": None}
    b.update(kw)
    return b


# ── IDLE_CASH / NEVER_INVESTED / from cash ───────────────────────────────

def test_idle_cash_set_since_the_first_idle_read_and_never_invested_clear():
    s = _sessions(30)
    e = _book(account="hack9")
    gp = D.gross_path(e, {"fleet_gross": {"hack9": [(s[0], 0.95), (s[-8], 0.0)]}}, s)
    idle, never, _ = D.idle_flags(e, gp, P)
    assert idle["status"] == "SET" and idle["since"] == s[-8] and idle["sessions"] == 8
    assert never["status"] == "CLEAR" and never["max_gross"] == pytest.approx(0.95)


def test_idle_cash_clear_when_the_idle_stretch_is_shorter_than_the_minimum():
    s = _sessions(30)
    e = _book(account="hack9")
    gp = D.gross_path(e, {"fleet_gross": {"hack9": [(s[0], 0.95), (s[-3], 0.01)]}}, s)
    idle, _, _ = D.idle_flags(e, gp, P)
    assert idle["status"] == "CLEAR" and idle["trailing_idle_sessions"] == 3


def test_idle_cannot_determine_without_a_gross_source_or_series():
    s = _sessions(30)
    e = _book(account="murat", family="murat_book")
    idle, never, wi = D.idle_flags(e, D.gross_path(e, {}, s), P)
    assert idle["status"] == never["status"] == wi["status"] == CD
    assert "no gross source" in idle["why"]


def test_never_invested_needs_the_path_to_start_at_inception():
    s = _sessions(30)
    e = _book(account="hack9")
    gp = D.gross_path(e, {"fleet_gross": {"hack9": [(s[10], 0.0)]}}, s)
    idle, never, _ = D.idle_flags(e, gp, P)
    assert idle["status"] == "SET"                       # idle since the first read ...
    assert never["status"] == CD and "after inception" in never["why"]   # ... but not "never"


def test_never_invested_llm_book_and_its_whole_excess_is_from_cash():
    s = _sessions(30)
    e = _book(account="allcash", family="llm_portfolio:personal", weights={}, excess_pp=0.7)
    idle, never, wi = D.idle_flags(e, D.gross_path(e, {}, s), P)
    assert never["status"] == "SET" and never["sessions"] == 30
    assert wi["from_cash"] is True and wi["excess_while_idle_pp"] == pytest.approx(0.7)


def test_night_book_with_no_decision_is_never_invested_but_an_unread_table_is_not():
    s = _sessions(30)
    e = _book(account="night", family="night_books", book_id="book:x", excess_pp=0.5)
    _, never, _ = D.idle_flags(e, D.gross_path(e, {"night_decisions": {}}, s), P)
    assert never["status"] == "SET" and "no recorded decision" in never["note"]
    # decisions not read (None): falls back to the NAV proxy, which has no series here -> CD
    _, never2, _ = D.idle_flags(e, D.gross_path(e, {"night_decisions": None}, s), P)
    assert never2["status"] == CD


def _idle_world(spy_drop: float):
    s = _sessions(30)
    rs = [0.001] * 29
    rs[-3] = spy_drop                                   # SPY moves while the book is in cash
    rb = [0.002] * 23 + [0.0] * 6                        # flat once idle
    e = _book(account="hack9", _series=_series(s, rb, rs))
    ex = 100 * (np.prod([1 + x for x in rb]) - np.prod([1 + x for x in rs]))
    e["excess_pp"] = float(ex)
    gp = D.gross_path(e, {"fleet_gross": {"hack9": [(s[0], 0.9), (s[-7], 0.0)]}}, s)
    return e, gp


def test_excess_from_cash_when_more_than_half_of_it_accrued_while_idle():
    e, gp = _idle_world(-0.05)
    _, _, wi = D.idle_flags(e, gp, P)
    assert wi["status"] == "OK" and wi["from_cash"] is True
    assert wi["excess_while_idle_pp"] > 0.5 * e["excess_pp"] > 0


def test_excess_not_from_cash_when_the_idle_stretch_was_flat():
    e, gp = _idle_world(0.001)
    _, _, wi = D.idle_flags(e, gp, P)
    assert wi["status"] == "OK" and wi["from_cash"] is False


def test_excess_while_idle_cannot_determine_when_the_series_misses_the_idle_stretch():
    e, gp = _idle_world(-0.05)
    e["_series"] = e["_series"][:-6]
    _, _, wi = D.idle_flags(e, gp, P)
    assert wi["status"] == CD and "not in the period-return series" in wi["why"]


# ── SAME_BET ──────────────────────────────────────────────────────────────

def _corr_books(n: int = 30, seed: int = 5):
    rng = np.random.default_rng(seed)
    s = _sessions(n + 1)
    spy = rng.normal(0, 0.01, n)
    a = spy + rng.normal(0.001, 0.01, n)
    b = a + rng.normal(0, 0.001, n)                      # A's excess plus a little noise
    c = spy + rng.normal(0, 0.01, n)                     # independent excess
    return s, spy, [_book(account="A", _series=_series(s, a, spy)),
                    _book(account="B", _series=_series(s, b, spy)),
                    _book(account="C", _series=_series(s, c, spy))]


def test_same_bet_peers_set_clear_and_cannot_determine():
    s, spy, books = _corr_books()
    books.append(_book(account="short", _series=_series(s[:11], spy[:10], spy[:10])))
    pe = D.same_bet_peers(books, P)
    assert [q["account"] for q in pe["A"]["peers"]] == ["B"] and pe["A"]["peers"][0]["corr"] >= 0.9
    assert pe["C"]["status"] == "OK" and pe["C"]["peers"] == []
    assert pe["short"]["status"] == CD


def test_same_bet_as_names_the_earlier_listed_account():
    s, spy, books = _corr_books()
    pe = D.same_bet_peers(books, P)
    by = {b["account"]: {"flags": {"SAME_BET": pe[b["account"]]}} for b in books}
    sb = RV.same_bet_as(["B", "C", "A"], by)
    assert sb["A"]["status"] == "SET" and sb["A"]["account"] == "B"
    assert sb["B"]["status"] == "CLEAR" and sb["C"]["status"] == "CLEAR"
    assert RV.same_bet_as(["A"], {"A": {"evidence": {}}})["A"]["status"] == CD


def test_a_cash_book_is_not_the_same_bet_as_a_low_beta_book():
    rng = np.random.default_rng(9)
    s = _sessions(31)
    spy = rng.normal(0, 0.01, 30)
    low = 0.3 * spy + rng.normal(0, 0.0005, 30)          # excess ~ -0.7 SPY
    books = [_book(account="cash", _series=_series(s, [0.0] * 30, spy)),
             _book(account="lowbeta", _series=_series(s, low, spy))]
    assert D.same_bet_peers(books, P)["lowbeta"]["peers"]          # by excess alone they link ...
    pe = D.same_bet_peers(books, P, never={"cash"})
    assert pe["lowbeta"]["peers"] == [] and pe["cash"]["peers"] == []   # ... but cash is not a bet


# ── BELOW_MDE / ABOVE_MDE ────────────────────────────────────────────────

def _mde_book(excess: float, n: int = 30, sessions: int = 30):
    rng = np.random.default_rng(3)
    s = _sessions(n + 1)
    spy = rng.normal(0, 0.01, n)
    rb = spy + rng.normal(0, 0.01, n)
    return _book(excess_pp=excess, sessions_graded=sessions, _series=_series(s, rb, spy)), s


def test_mde_below_above_and_cannot_determine():
    e, s = _mde_book(1.0)
    f = D.mde_flag(e, s, P)
    sd = float(np.std([b - x for _, b, x in e["_series"]], ddof=1))
    assert f["se_pp"] == pytest.approx(100 * sd * np.sqrt(30), abs=1e-3)
    assert f["mde_pp"] == pytest.approx(P["mde_z"] * f["se_pp"], abs=1e-2)
    assert f["status"] == "BELOW_MDE"
    e2, _ = _mde_book(f["mde_pp"] + 1.0)
    assert D.mde_flag(e2, s, P)["status"] == "ABOVE_MDE"
    e3, s3 = _mde_book(5.0, n=10)
    assert D.mde_flag(e3, s3, P)["status"] == CD


def test_mde_scales_to_the_receipt_sessions_not_the_series_length():
    e, s = _mde_book(1.0, n=30, sessions=120)
    f = D.mde_flag(e, s, P)
    sd = float(np.std([b - x for _, b, x in e["_series"]], ddof=1))
    assert f["se_pp"] == pytest.approx(100 * sd * np.sqrt(120), abs=1e-3)


# ── ONE_MONTH ─────────────────────────────────────────────────────────────

def _month_book(kind: str, sessions_graded: int = None):
    s = _sessions(46)
    months: dict = {}
    for d in s[1:]:
        months[d[:7]] = months.get(d[:7], 0) + 1
    big = max(months, key=lambda m: (months[m], m))
    rs = [0.0005] * 45
    if kind == "one":
        rb = [x + (0.01 if d[:7] == big else -0.001) for d, x in zip(s[1:], rs)]
    else:
        rb = [x + 0.001 for x in rs]
    ser = _series(s, rb, rs)
    ex = 100 * (np.prod([1 + b for _, b, _ in ser]) - np.prod([1 + x for _, _, x in ser]))
    return _book(excess_pp=float(ex), sessions_graded=sessions_graded or 45, _series=ser), s, big


def test_one_month_set_names_the_month_and_the_excess_without_it():
    e, s, big = _month_book("one")
    f = D.one_month_flag(e, s, P)
    assert f["status"] == "SET" and f["month"] == big and f["excess_without_month_pp"] < 0


def test_one_month_clear_when_the_excess_is_spread():
    e, s, _ = _month_book("spread")
    assert D.one_month_flag(e, s, P)["status"] == "CLEAR"


def test_one_month_cannot_determine_on_a_short_series():
    e, s, _ = _month_book("one", sessions_graded=120)
    f = D.one_month_flag(e, s, P)
    assert f["status"] == CD and "covers" in f["why"]


# ── ONE_NAME ──────────────────────────────────────────────────────────────

def _tail(share: float, basis: str = "active_contribution") -> dict:
    return {"status": "OK", "basis": basis, "top1": {"ticker": "LLY", "share": share},
            "reconstructed_excess_pp": 5.0}


def test_one_name_set_clear_cannot_determine_and_not_applicable():
    assert D.one_name_flag(_book(excess_pp=5.0, tail=_tail(0.45)), P)["status"] == "SET"
    assert D.one_name_flag(_book(excess_pp=5.0, tail=_tail(0.30)), P)["status"] == "CLEAR"
    assert D.one_name_flag(_book(excess_pp=5.0, tail=_tail(0.9, "unrealized_pl")), P)["status"] == CD
    assert D.one_name_flag(_book(excess_pp=-5.0, tail=_tail(0.9)), P)["status"] == "N/A"


# ── SIZING_ADDED_NOTHING ──────────────────────────────────────────────────

def _sizing_pair(gap: float):
    rng = np.random.default_rng(4)
    s = _sessions(31)
    spy = rng.normal(0, 0.01, 30)
    rb = spy + rng.normal(0, 0.005, 30)
    rew = rb + rng.normal(0, 0.002, 30)
    book = _book(account="bk", family="llm_portfolio:personal", return_pct=5.0, sessions_graded=30,
                 weights={"A": 0.6, "B": 0.4}, _series=_series(s, rb, spy))
    ew = {"account": "bk__ew", "return_pct": 5.0 - gap, "_series": _series(s, rew, spy)}
    return book, ew, s


def test_sizing_added_nothing_set_clear_and_cannot_determine():
    px = D.Prices(None)
    book, ew, s = _sizing_pair(0.1)
    f = D.sizing_flag(book, ew, px, s, {})
    assert f["status"] == "SET" and f["ew_source"] == "ew twin bk__ew" and "difference" in f["se_basis"]
    book, ew, s = _sizing_pair(10.0)
    assert D.sizing_flag(book, ew, px, s, {})["status"] == "CLEAR"
    lane = _book(family="website_lane", weights={"A": 0.5})
    assert D.sizing_flag(lane, None, px, s, {})["status"] == CD


# ── IDENTICAL_TO_COMPARATOR ───────────────────────────────────────────────

def _night(account: str, bid: str) -> dict:
    return _book(account=account, family="night_books", book_id=bid)


def test_identical_to_comparator_set_clear_cannot_determine_and_not_applicable():
    s = _sessions(5)
    w = {"AAA": 0.5, "BBB": 0.5}
    book, comp = _night("abstain [11111111]", "book:1"), _night("Always invested - comparato [22222222]", "book:2")
    books = [book, comp]
    same = {"night_decisions": {"book:1": [(s[0], w)], "book:2": [(s[0], dict(w))]}}
    diff = {"night_decisions": {"book:1": [(s[0], w)], "book:2": [(s[0], {"CCC": 1.0})]}}
    markers = P["flag_control_name_markers"]
    comps = D.comparators_of(book, books, markers)
    assert [c["account"] for c in comps] == [comp["account"]]
    hs = {b["account"]: D.holdings_hash(b, same) for b in books}
    assert D.identical_flag(book, comps, hs)["status"] == "SET"
    hd = {b["account"]: D.holdings_hash(b, diff) for b in books}
    assert D.identical_flag(book, comps, hd)["status"] == "CLEAR"
    hn = {b["account"]: D.holdings_hash(b, {"night_decisions": None}) for b in books}
    assert D.identical_flag(book, comps, hn)["status"] == CD
    alone = _night("alone [33333333]", "book:3")
    assert D.identical_flag(alone, D.comparators_of(alone, [alone], markers), {})["status"] == "N/A"


# ── HIGH_BETA ─────────────────────────────────────────────────────────────

def test_high_beta_set_clear_cannot_determine():
    mk = lambda v: _book(market_exposure={"beta": {"value": v, "se": 0.2} if v is not None else  # noqa: E731
                                          {"value": CD, "why": "flat NAV"}})
    assert D.high_beta_flag(mk(1.8), P)["status"] == "SET"
    assert D.high_beta_flag(mk(1.2), P)["status"] == "CLEAR"
    assert D.high_beta_flag(mk(None), P)["status"] == CD


def test_every_book_row_carries_every_flag():
    s = _sessions(8)
    paths = {"SPY": list(np.linspace(100, 101, 8)), "A0": list(np.linspace(50, 52, 8))}
    rows = [{"symbol": k, "date": pd.Timestamp(d), "open": c, "close": c}
            for k, v in paths.items() for d, c in zip(s, v)]
    px = D.Prices(pd.DataFrame(rows))
    books = [_book(account="x", family="llm_portfolio:personal", weights={"A0": 1.0},
                   inception=s[1], last_mark=s[-1])]
    D.attach_flags(books, {}, px, P)
    f = books[0]["flags"]
    for k in D.FLAG_ORDER:
        assert isinstance(f.get(k), dict) and f[k].get("status"), k


# ── CLAIMS PROMOTED / LABELS LOWERED ─────────────────────────────────────

def _labels(d: dict) -> dict:
    return {b["account"]: b for b in d["books"]}


def test_label_changes_promoted_lowered_none_and_new():
    now = {"a": {"evidence": {"label": "EARLY_EVIDENCE"}}, "b": {"evidence": {"label": "OBSERVED(40)"}},
           "c": {"evidence": {"label": "OBSERVED(30)"}}, "d": {"evidence": {"label": "OBSERVED(9)"}}}
    prev = {"run_id": "r0", "path": "p", "dna": {"books": [
        {"account": "a", "evidence": {"label": "OBSERVED(30)"}},
        {"account": "b", "evidence": {"label": "REPLICATED"}},
        {"account": "c", "evidence": {"label": "OBSERVED(29)"}}]}}
    ch = RV.label_changes(["a", "b", "c", "d"], now, prev)
    assert [x["account"] for x in ch["promoted"]] == ["a"]
    assert [x["account"] for x in ch["lowered"]] == ["b"]
    assert ch["new_accounts"] == ["d"] and ch["n_compared"] == 3     # OBSERVED(29) -> (30) is no rise
    assert RV.label_changes(["a"], now, None)["why"] == "no earlier run to compare"


def test_previous_receipt_is_found_by_run_id_never_by_mtime(tmp_path):
    ids = ["2026-01-01T000000Z", "2026-01-02T000000Z", "2026-01-03T000000Z"]
    for i, r in enumerate(ids):
        p = tmp_path / f"book_dna_{r}.json"
        p.write_text(json.dumps({"books": [], "generated_utc": r}), encoding="utf-8")
        t = 2_000_000_000 - i * 100_000                  # the OLDEST run id gets the NEWEST mtime
        os.utime(p, (t, t))
    (tmp_path / "book_dna_2026-01-02T000000Z_2.json").write_text("{}", encoding="utf-8")
    prev = RV.previous_dna(tmp_path, ids[2])
    assert prev["run_id"] == ids[1]
    assert RV.previous_dna(tmp_path, ids[0]) is None
    (tmp_path / f"book_dna_{ids[1]}.json").write_text("not json", encoding="utf-8")
    assert RV.previous_dna(tmp_path, ids[2])["error"]


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    d = tmp_path / "paper_accounts"
    shutil.copytree(FIX, d)
    return d


EARLIER = ["2026-10-03T235345Z", "2026-10-04T235345Z", "2026-10-05T235345Z"]   # the fixture RID's 3 days before


def _write_prev(folder: Path, edit, rid: str = EARLIER[-1]) -> None:
    d = json.loads((folder / f"book_dna_{RID}.json").read_text(encoding="utf-8"))
    edit(d)
    (folder / f"book_dna_{rid}.json").write_text(json.dumps(d), encoding="utf-8")


def _set(account: str, label: str):
    def edit(d):
        for b in d["books"]:
            if b["account"] == account:
                b["evidence"] = {"label": label}
    return edit


def _set_current(folder: Path, account: str, label: str) -> None:
    cur = folder / f"book_dna_{RID}.json"
    d = json.loads(cur.read_text(encoding="utf-8"))
    _set(account, label)(d)
    cur.write_text(json.dumps(d), encoding="utf-8")


def test_claims_none_when_no_label_rose_over_the_hold_window(folder):
    for r in EARLIER:
        _write_prev(folder, lambda d: None, r)
    v = RV.run(RID, folder, write_files=False)["voice"]
    assert v["claims"]["line"] == "CLAIMS PROMOTED: none"
    assert v["claims"]["compared_with"]["run_id"] == EARLIER[-1]
    assert [d["run_id"] for d in v["claims"]["promotion_days"]] == EARLIER
    assert v["headline_lines"][-1] == "CLAIMS PROMOTED: none."
    assert not any(ln.startswith(("LABELS LOWERED", "LABELS RISING")) for ln in v["headline_lines"])


def test_a_flicker_is_rising_not_promoted_and_a_fall_is_lowered_at_once(folder):
    """SHADOW_BAYES_v0 on 2026-11-11/13/14: EARLY_EVIDENCE -> OBSERVED -> EARLY_EVIDENCE."""
    acc, other = "revision_flow_v0", "pers_revision_flow_leaders_2026-09-25"
    _set_current(folder, acc, "EARLY_EVIDENCE")
    _write_prev(folder, _set(acc, "EARLY_EVIDENCE"), EARLIER[0])
    _write_prev(folder, _set(acc, "EARLY_EVIDENCE"), EARLIER[1])

    def last(d):
        _set(acc, "OBSERVED(6)")(d)
        _set(other, "EARLY_EVIDENCE")(d)
    _write_prev(folder, last, EARLIER[2])
    v = RV.run(RID, folder, write_files=False)["voice"]
    lines = v["headline_lines"]
    assert lines[-1] == "CLAIMS PROMOTED: none."
    assert lines[-2] == f"LABELS RISING, NOT YET HELD (1 of 3 runs): {acc} OBSERVED → EARLY_EVIDENCE."
    assert lines[-3] == f"LABELS LOWERED: {other} EARLY_EVIDENCE → OBSERVED (since run {EARLIER[2]})."
    assert lines[-4].startswith("Distinct bets ahead of SPY: ")
    md = RV.render_md(v)
    assert "LABELS RISING, NOT YET HELD" in md and "## Flags beside the labels" in md
    RV.run(RID, folder)
    _, block = RV.headline_block(folder)
    assert block[-2].startswith("LABELS RISING, NOT YET HELD") and block[-1].startswith("CLAIMS PROMOTED:")


def _hist(*days: dict) -> dict:
    return {"days": [{"day": f"d{i}", "run_id": f"r{i}", "path": f"p{i}", "labels": lab}
                     for i, lab in enumerate(days)]}


def _state(st: dict) -> str:
    if st["promoted"]:
        return "P"
    return f"R{st['rising'][0]['held_runs']}" if st["rising"] else "-"


def test_a_rise_held_three_runs_promotes_exactly_once():
    OB, E = "OBSERVED(30)", "EARLY_EVIDENCE"
    seq = [OB, OB, OB, E, E, E, E, E]                     # daily labels; the rise is on day 3
    seen = []
    for t in range(3, len(seq)):
        hist = _hist(*({"a": x} for x in seq[t - 3:t]))       # the 3 daily runs before t
        seen.append(_state(RV.promotion_status(["a"], {"a": {"evidence": {"label": seq[t]}}}, hist, 3)))
    assert seen == ["R1", "R2", "P", "-", "-"]
    st = RV.promotion_status(["a"], {"a": {"evidence": {"label": E}}}, _hist({"a": OB}, {"a": E}, {"a": E}), 3)
    assert st["promoted"][0]["previous_rung"] == "OBSERVED" and st["promoted"][0]["held_since_run"] == "r1"


def test_a_flicker_never_promotes():
    OB, E = "OBSERVED(30)", "EARLY_EVIDENCE"
    seq = [OB, E, OB, E, E, OB, E, OB, E, E, OB]
    for t in range(3, len(seq)):
        hist = _hist(*({"a": x} for x in seq[t - 3:t]))
        st = RV.promotion_status(["a"], {"a": {"evidence": {"label": seq[t]}}}, hist, 3)
        assert st["promoted"] == [], (t, seq[t - 3:t + 1])


def test_an_account_missing_from_an_earlier_run_is_not_promoted():
    E = "EARLY_EVIDENCE"
    st = RV.promotion_status(["a"], {"a": {"evidence": {"label": E}}},
                             _hist({"b": "OBSERVED(9)"}, {"a": E}, {"a": E}), 3)
    assert st["promoted"] == [] and st["rising"] == []


def _dna_file(folder: Path, rid: str, label: str) -> None:
    (folder / f"book_dna_{rid}.json").write_text(
        json.dumps({"books": [{"account": "a", "evidence": {"label": label}}]}), encoding="utf-8")


def test_two_runs_on_one_utc_day_count_once(tmp_path):
    OB, E = "OBSERVED(30)", "EARLY_EVIDENCE"
    _dna_file(tmp_path, "2026-01-01T010000Z", OB)
    _dna_file(tmp_path, "2026-01-02T010000Z", OB)
    _dna_file(tmp_path, "2026-01-03T010000Z", E)
    _dna_file(tmp_path, "2026-01-03T200000Z", E)       # same UTC day: counts once
    _dna_file(tmp_path, "2026-01-04T000500Z", OB)       # same UTC day as THIS run: left out
    for i, p in enumerate(sorted(tmp_path.iterdir())):
        os.utime(p, (2_000_000_000 - i * 1000,) * 2)   # mtimes inverted: must not matter
    h = RV.label_history(tmp_path, "2026-01-04T060000Z", 3)
    assert [d["run_id"] for d in h["days"]] == ["2026-01-01T010000Z", "2026-01-02T010000Z", "2026-01-03T200000Z"]
    st = RV.promotion_status(["a"], {"a": {"evidence": {"label": E}}}, h, 3)
    assert st["promoted"] == [] and st["rising"][0]["held_runs"] == 2


def test_missing_history_says_why(folder):
    _write_prev(folder, _set("revision_flow_v0", "OBSERVED(6)"))
    _set_current(folder, "revision_flow_v0", "EARLY_EVIDENCE")
    v = RV.run(RID, folder, write_files=False)["voice"]
    assert v["claims"]["line"] == "CLAIMS PROMOTED: none (not enough earlier runs to confirm a rise)"
    assert v["claims"]["rising_lines"] == ["LABELS RISING, NOT YET HELD (1 of 3 runs): revision_flow_v0 "
                                           "OBSERVED → EARLY_EVIDENCE"]
    (folder / f"book_dna_{EARLIER[-1]}.json").unlink()
    v0 = RV.run(RID, folder, write_files=False)["voice"]
    assert v0["claims"]["line"] == "CLAIMS PROMOTED: none (no earlier run to compare)"


def test_holding_a_high_label_is_not_a_promotion(folder):
    """The bug the owner saw: an account already at EARLY_EVIDENCE on every run is not promoted."""
    _set_current(folder, "revision_flow_v0", "EARLY_EVIDENCE")
    for r in EARLIER:
        _write_prev(folder, _set("revision_flow_v0", "EARLY_EVIDENCE"), r)
    v = RV.run(RID, folder, write_files=False)["voice"]
    assert v["claims"]["line"] == "CLAIMS PROMOTED: none" and v["claims"]["rising"] == []
    assert "EARLY_EVIDENCE" in v["claims"]["labels_held"]


def test_the_fixture_promotes_a_rise_held_through_the_window(folder):
    _set_current(folder, "revision_flow_v0", "EARLY_EVIDENCE")
    for r, lab in zip(EARLIER, ("OBSERVED(5)", "EARLY_EVIDENCE", "EARLY_EVIDENCE")):
        _write_prev(folder, _set("revision_flow_v0", lab), r)
    v = RV.run(RID, folder, write_files=False)["voice"]
    assert v["headline_lines"][-1] == ("CLAIMS PROMOTED: revision_flow_v0 OBSERVED → EARLY_EVIDENCE (held 3 "
                                       f"daily runs since run {EARLIER[1]}).")


def test_old_receipt_flags_cannot_determine_and_the_distinct_bets_line(folder):
    v = RV.run(RID, folder, write_files=False)["voice"]
    for x in v["flags_rows"]:
        assert set(x["flags"]["cannot_determine"]) == set(D.FLAG_ORDER)
        assert RV.FLAGS_PREDATE in x["flags"]["line"]
    sbc = v["headline"]["same_bet_clustering"]
    assert sbc["line"].startswith(f"Distinct bets ahead of SPY: {sbc['n_bets_ahead']} of {sbc['n_bets']} "
                                  "(after SAME_BET clustering); above their MDE: 0")


def _flagged(folder: Path, account: str, flags: dict, me: dict) -> None:
    cur = folder / f"book_dna_{RID}.json"
    d = json.loads(cur.read_text(encoding="utf-8"))
    base = {k: {"status": "CLEAR"} for k in D.FLAG_ORDER}
    base["SAME_BET"] = {"status": "OK", "peers": []}
    base["MDE"] = {"status": "BELOW_MDE", "excess_pp": 5.0, "mde_pp": 20.0}
    for b in d["books"]:
        b["flags"] = json.loads(json.dumps(base))
        if b["account"] == account:
            b["flags"].update(flags)
            b["market_exposure"] = me
    cur.write_text(json.dumps(d), encoding="utf-8")


def test_high_beta_prints_the_beta_adjusted_excess_first(folder):
    me = {"beta": {"value": 1.9, "se": 0.3},
          "beta_adjusted_excess_pp": {"value": -1.25, "se_pp": 4.0, "mde_pp": 11.2}}
    _flagged(folder, "revision_flow_v0", {"HIGH_BETA": {"status": "SET", "beta": 1.9, "se": 0.3}}, me)
    v = RV.run(RID, folder, write_files=False)["voice"]
    lead = v["headline_lines"][1]
    assert lead.startswith("LEADER revision_flow_v0 (with hack2: same names): beta-adjusted -1.25 pp")
    assert lead.index("beta-adjusted -1.25") < lead.index("vs SPY")
    assert "HIGH_BETA 1.9 ±0.30" in lead and "BELOW_MDE (|+5.00| < MDE 20.00 pp)" in lead


def test_idle_book_prints_from_cash_and_never_invested_subsumes_idle(folder):
    _flagged(folder, "revision_flow_v0", {
        "NEVER_INVESTED": {"status": "SET", "sessions": 7, "threshold_gross": 0.05},
        "IDLE_CASH": {"status": "SET", "since": "x", "sessions": 7, "threshold_gross": 0.05},
        "EXCESS_WHILE_IDLE": {"status": "OK", "from_cash": True, "excess_while_idle_pp": 5.7,
                              "receipt_excess_pp": 5.7}}, {})
    v = RV.run(RID, folder, write_files=False)["voice"]
    f = v["leaders"][0]["flags"]
    assert f["set"][0].startswith("NEVER_INVESTED") and not any(t.startswith("IDLE_CASH") for t in f["set"])
    assert f["from_cash"].startswith("excess from cash, not from positions (+5.70 of +5.70 pp")
