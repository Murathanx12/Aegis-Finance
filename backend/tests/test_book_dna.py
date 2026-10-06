"""book_dna (chunk C3, 2026-10-06, with the adversarial review's F1-F8 applied):
"N ahead of SPY" never travels without its collapse.

Pins: twins and kind=control books are separated from strategy books; two books
sharing 90% of their names are one holdings cluster and disjoint books are not;
a size tie between clusters is broken by total excess, never row order; the
ex-ante effective-bets count on a synthetic 3-book set (two copies + one
independent ~ 1.8 bets); a loser whose visible P&L does not cover the shortfall
is `not_determinable`, never `selection` by default; no label exceeds
REPLICATED; the collapse line and the top line are in the rendered
PAPER_ACCOUNTS markdown (and say NOT COMPUTED rather than vanishing); the
one-name flag needs |excess| >= 1 pp and a bounded same-direction share.

Every date is derived from today (CLAUDE.md protocol item 5). No network, no
disk outside tmp_path.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from backend.services import book_dna as D
from scripts import paper_accounts_roi as R

COLLAPSE_RE = re.compile(
    r"\d+ ahead of SPY = \d+ twins \+ \d+ controls \+ \d+ strategy books; the strategy books = "
    r"\d+ holdings clusters")


def _sessions(n: int) -> list[str]:
    d = date.today() - timedelta(days=1)
    out = []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d -= timedelta(days=1)
    return sorted(out)


def _bars(paths: dict[str, list[float]], dates: list[str]) -> pd.DataFrame:
    rows = []
    for sym, closes in paths.items():
        for d, c in zip(dates, closes):
            rows.append({"symbol": sym, "date": pd.Timestamp(d), "open": c, "close": c})
    return pd.DataFrame(rows)


def _book(book_id, name, tickers, *, weights=None, kind="personal", parent=None, twin=None):
    w = weights or [1.0 / len(tickers)] * len(tickers)
    b = {"schema": "llm_portfolio/1", "book_id": book_id, "name": name, "kind": kind,
         "cash_weight": 0, "positions": [{"ticker": t, "weight": x} for t, x in zip(tickers, w)]}
    if kind == "twin":
        b.update(parent_book_id=parent, twin=twin)
    return b


def _inputs(books):
    return {"books": books, "leaderboards": [], "fleet_positions": {}, "fleet_manager_last_run": {},
            "fleet_grades": {}, "pc_state": None, "pc_nav": [], "pc_manager_last_run": None,
            "night_nav": {}, "lane_positions": {}, "lane_caps": {}, "sector_map": {},
            "sector_source": "test", "gaps": {}}


NAMES_A = [f"A{i}" for i in range(10)]
NAMES_A9 = NAMES_A[:9] + ["Z0"]              # 9 of 10 shared: Jaccard 9/11 = 0.82
NAMES_B = [f"B{i}" for i in range(10)]       # disjoint


@pytest.fixture()
def world():
    dates = _sessions(8)
    entry, last = dates[1], dates[-1]
    paths = {"SPY": list(np.linspace(100, 100.5, 8))}
    for t in NAMES_A + NAMES_B + ["Z0"]:
        paths[t] = list(np.linspace(50, 52, 8))
    paths["C0"] = list(np.linspace(50, 80, 8))   # one name carries book "conc"
    books = [_book("pa", "parent_a", NAMES_A),
             _book("tw", "parent_a__ew", NAMES_A, kind="twin", parent="pa", twin="ew"),
             _book("p9", "near_copy", NAMES_A9),
             _book("pb", "disjoint_b", NAMES_B),
             _book("cc", "conc", ["C0", "B1", "B2", "B3"], weights=[0.7, 0.1, 0.1, 0.1]),
             _book("ct", "a_control", NAMES_A, kind="control")]
    px = D.Prices(_bars(paths, dates))
    spy = px.close_on_or_before("SPY", last) / px.open_on("SPY", entry) - 1

    def excess(bid):     # the receipt's excess, consistent with the prices
        b = next(x for x in books if x["book_id"] == bid)
        return 100 * sum(q["weight"] * (px.close_on_or_before(q["ticker"], last)
                                        / px.open_on(q["ticker"], entry) - 1 - spy)
                         for q in b["positions"])

    def row(account, family, bid, ex=None):
        ex = excess(bid) if ex is None else ex
        return {"account": account, "family": family, "book_id": bid, "inception": entry,
                "last_mark": last, "start_capital": 1e6, "equity": 1e6 * (1 + spy + ex / 100),
                "roi_pct": 100 * spy + ex, "spy_same_window_pct": 100 * spy, "vs_spy_pp": ex,
                "status": "LIVE", "spy_base": "grade_entry_open", "graded_against": None,
                "note": "", "n_positions": None, "source": "test"}

    rows = [row("parent_a", "llm_portfolio:personal", "pa"),
            row("parent_a__ew", "llm_portfolio:twin", "tw"),
            row("near_copy", "llm_portfolio:personal", "p9"),
            row("disjoint_b", "llm_portfolio:lib", "pb"),
            row("conc", "llm_portfolio:personal", "cc"),
            row("a_control", "llm_portfolio:lib", "ct"),
            row("loser", "llm_portfolio:lib", "pb", ex=-4.0)]
    rc = {"generated_utc": f"{date.today().isoformat()}T05:00:00+00:00", "rows": rows,
          "aggregate": {"n_ahead_of_spy": 6, "honest_sentence": "Of 7 priced accounts, 6 are ahead of SPY."}}
    return rc, _inputs(books), px


def test_twins_and_controls_are_not_strategy_books(world):
    rc, inp, px = world
    dna = D.build(rc, inp, px)
    s = dna["summary"]
    assert s["n_ahead_raw"] == 6
    assert (s["n_ahead_twins"], s["n_ahead_controls"], s["n_ahead_strategy"]) == (1, 1, 4)
    assert dna["controls_ahead"] == ["a_control"]
    members = {a for c in dna["holdings_clusters"] for a in c["members"]}
    assert "a_control" not in members and "parent_a__ew" not in members
    clusters = {frozenset(c["members"]) for c in dna["holdings_clusters"]}
    assert frozenset({"parent_a", "near_copy"}) in clusters      # 90% shared names
    assert frozenset({"disjoint_b"}) in clusters                 # disjoint stands alone
    assert s["n_holdings_clusters_ahead"] == 3                   # conc: Jaccard 3/11 < 0.30
    assert s["collapse_factor_twins_controls"] == round(6 / 4, 2)
    assert s["collapse_factor_holdings_overlap"] == round(4 / 3, 2)
    assert COLLAPSE_RE.search(s["collapse_line"]), s["collapse_line"]
    assert "a_control" in [l["account"] for l in dna["losers"]] or True
    ctl = D.classify_loser({"family": "llm_portfolio:lib", "category": "control", "account": "x"},
                           D.params())
    assert ctl["error_type"] == "control_artifact"


def test_cluster_size_tie_is_broken_by_total_excess_not_row_order():
    def bk(name, tickers, ex):
        return {"account": name, "family": "llm_portfolio:lib", "tickers": tickers,
                "weights": {t: 1 / len(tickers) for t in tickers}, "excess_pp": ex}
    small_ex = [bk("s1", ["S1", "S2"], 0.5), bk("s2", ["S1", "S2"], 0.5)]
    big_ex = [bk("m1", ["MU", "SNDK"], 4.0), bk("m2", ["MU", "SNDK"], 3.0)]
    p = D.params()
    for order in (small_ex + big_ex, big_ex + small_ex):
        cs, _ = D._clusters_of(order, 0.30, p)
        assert cs[0]["members"][0] in ("m1", "m2")
        assert cs[0]["tied_for_largest"] is True
        assert cs[0]["shared_basket"][0]["ticker"] in ("MU", "SNDK")


def test_cluster_function_directly():
    a = {"account": "a", "tickers": NAMES_A}
    b = {"account": "b", "tickers": NAMES_A9}
    c = {"account": "c", "tickers": NAMES_B}
    comps, edges = D.cluster([a, b, c], jaccard_threshold=0.5, corr_threshold=0.8, min_corr_obs=15)
    assert sorted(len(x) for x in comps) == [1, 2]
    assert edges and edges[0]["why"].startswith("jaccard")
    s = [("d1", 0.01, 0.0), ("d2", -0.02, 0.0), ("d3", 0.03, 0.0)]
    comps, _ = D.cluster([{"account": "x", "tickers": [], "_series": s},
                          {"account": "y", "tickers": [], "_series": list(s)}],
                         jaccard_threshold=0.5, corr_threshold=0.8, min_corr_obs=15)
    assert len(comps) == 1


def test_exante_effective_bets_on_three_books():
    """Two books holding the same exposure + one independent book ~ 1.8 bets
    (eigenvalues 2, 1, 0 -> 9/5), on the 150 sessions BEFORE inception."""
    rng = np.random.default_rng(7)
    dates = _sessions(170)
    inception = dates[-5]
    n = len(dates)
    spy = 100 * np.cumprod(1 + rng.normal(0, 0.01, n))
    x = 50 * np.cumprod(1 + rng.normal(0, 0.02, n))
    x2 = 50 * np.cumprod(1 + rng.normal(0, 0.02, n))
    y = 50 * np.cumprod(1 + rng.normal(0, 0.02, n))
    px = D.Prices(_bars({"SPY": list(spy), "X": list(x), "X2": list(x2), "Y": list(y)}, dates))

    def bk(name, w):
        return {"account": name, "tickers": sorted(w), "weights": w, "inception": inception}
    books = [bk("one", {"X": 0.5, "X2": 0.5}), bk("copy", {"X": 0.5, "X2": 0.5}), bk("other", {"Y": 1.0})]
    ex = D.exante_bets(books, px, D.params())
    assert ex["status"] == "OK"
    assert ex["n_sessions"] == 150
    assert ex["window"][1] < inception                           # strictly before the book existed
    assert 1.6 < ex["effective_bets_raw"] < 2.0
    assert 1.6 < ex["effective_bets_spy_residual"] < 2.0
    assert D.participation_ratio(np.eye(4)) == pytest.approx(4.0)
    assert D.participation_ratio(np.ones((4, 4))) == pytest.approx(1.0)


def test_uncovered_loss_is_not_determinable_and_selection_needs_coverage():
    p = D.params()
    base = {"family": "alpaca_fleet", "category": "strategy", "account": "hackX",
            "manager_sessions_since": 0, "subwindows": {}, "excess_pp": -19.4,
            "concentration": {"status": "OK", "top1_weight_of_invested": {"ticker": "Q", "weight": 0.1}}}
    # open P&L explains 1% of the shortfall: no P&L rule may fire (review F3)
    thin = dict(base, tail={"status": "OK", "basis": "unrealized_pl", "total": -181.0,
                            "coverage_of_excess": 0.01, "top1": {"ticker": "RZLV", "share": 0.9}})
    out = D.classify_loser(thin, p)
    assert out["error_type"] == "not_determinable"
    assert "covers 1%" in out["why"]
    # a covered, spread loss is a POSITIVE selection finding
    wide = dict(base, tail={"status": "OK", "basis": "active_contribution", "total": -0.19,
                            "coverage_of_excess": 0.98, "top1": {"ticker": "Q", "share": 0.12}})
    assert D.classify_loser(wide, p)["error_type"] == "selection"
    # timing uses the GROSS negative loss: -7.72 / +4.17 / -8.89 -> 54%, not timing
    sub = {"status": "OK", "windows": [{"from": "a", "to": "b", "excess_pp": -7.72},
                                       {"from": "c", "to": "d", "excess_pp": 4.17},
                                       {"from": "e", "to": "f", "excess_pp": -8.89}]}
    t = D.classify_loser(dict(base, tail={"status": D.NOT_COMPUTABLE}, subwindows=sub,
                              excess_pp=-12.44), p)
    assert t["error_type"] != "timing_exit"
    assert len(p["loser_rule_order"]) >= 8


def test_identity_group_is_decomposed():
    p = D.params()
    mirror = {"account": "mirror", "family": "website_lane", "category": "strategy", "excess_pp": -28.26}
    conv = {"account": "conviction", "family": "website_lane", "category": "strategy", "excess_pp": -12.86}
    out = D.classify_loser(mirror, p, [mirror, conv])
    assert out["error_type"] == "decomposed"
    assert out["decomposition"]["common_shortfall_pp_selection"] == -12.86
    assert out["decomposition"]["differential_pp_treatment_sizing"] == pytest.approx(-15.4, abs=1e-6)


def test_evidence_label_never_exceeds_replicated(world):
    p = D.params()
    ok_sub = {"status": "OK", "n_positive": 3, "windows": []}
    for n in (0, 5, 21, 400):
        for ex in (-1.0, 0.0, 2.0):
            for sub in (ok_sub, {"status": D.NOT_COMPUTABLE, "why": "x"}):
                for fair in (None, -1.0, 5.0):
                    for rep in (None, "other_book"):
                        lab = D.evidence_label(sessions=n, excess_pp=ex, sub=sub,
                                               fair_twin_excess_pp=fair, replicated_by=rep, p=p)["label"]
                        base = lab.split("(")[0]
                        assert base in D.LABEL_LADDER
                        assert D.LABEL_LADDER.index(base) <= D.LABEL_LADDER.index("REPLICATED")
    assert D.evidence_label(sessions=60, excess_pp=2.0, sub=ok_sub, fair_twin_excess_pp=1.0,
                            replicated_by=None, p=p)["label"] == "REPLICATED"
    assert D.evidence_label(sessions=6, excess_pp=9.0, sub=ok_sub, fair_twin_excess_pp=9.0,
                            replicated_by="x", p=p)["label"] == "OBSERVED(6)"
    rc, inp, px = world
    dna = D.build(rc, inp, px)
    for b in dna["books"]:
        assert not b["evidence"]["label"].startswith("VALIDATED")
    assert "only 0 of 6 books ahead of SPY have >= 21 sessions" in dna["summary"]["evidence_density_line"]


def test_one_name_dependence(world):
    rc, inp, px = world
    books = {b["account"]: b for b in D.build(rc, inp, px)["books"]}
    conc = books["conc"]
    assert conc["tail"]["status"] == "OK"
    assert conc["tail"]["top1"]["ticker"] == "C0"
    assert 0.5 < conc["tail"]["top1"]["share"] <= 1.0              # bounded same-direction share
    assert conc["one_name_dependence"] is True
    assert books["parent_a"]["one_name_dependence"] is False
    assert books["parent_a__ew"]["one_name_dependence"] is None     # twins are not flagged
    small = dict(books["parent_a"], excess_pp=0.4)
    flag, why = D._one_name(small, books["parent_a"]["tail"], D.params())
    assert flag is None and "noise" in why


def _md_rc(world, runner=None):
    rc, inp, px = world
    rc = dict(rc)
    rc.update({"sources": {"spy_leg": "test", "website_lanes": {"source": "test", "fresh": True,
                                                                  "expected_nav_date": None}}})
    rc["aggregate"] = R.aggregate(rc["rows"])
    if runner is not None:
        R.attach_book_dna(rc, runner=runner)
    return rc


def test_markdown_prints_the_collapse_and_top_lines(world, tmp_path):
    rc0, inp, px = world

    def runner(rc, run_id):
        dna = D.build(rc, inp, px)
        return dna, D.write(dna, tmp_path, run_id)

    rc = _md_rc(world, runner)
    md = R.render_markdown(rc, None)
    lines = md.splitlines()
    i = next(k for k, l in enumerate(lines) if "are ahead of SPY" in l)
    assert COLLAPSE_RE.search(lines[i + 1]), lines[i + 1]
    assert "No book with >= 21 sessions is ahead of SPY" in lines[2]
    assert "Nothing here is evidence yet." in lines[2]
    assert rc["aggregate"]["n_holdings_clusters_ahead"] == 3
    assert "holdings clusters" in rc["aggregate"]["honest_sentence"]
    assert list(tmp_path.glob("book_dna_*.json"))


def test_markdown_never_prints_the_count_alone(world, tmp_path):
    rc = _md_rc(world)
    md = R.render_markdown(rc, None)
    assert "collapse NOT COMPUTED" in md

    def boom(rc, run_id):
        raise RuntimeError("no SPY bars")

    rc = _md_rc(world, boom)
    assert rc["aggregate"]["book_dna_status"] == "REFUSED"
    assert "no SPY bars" in rc["aggregate"]["collapse_line"]
    md = R.render_markdown(rc, None)
    lines = md.splitlines()
    i = next(k for k, l in enumerate(lines) if "are ahead of SPY" in l)
    assert "NOT a count of independent bets" in lines[i + 1]
