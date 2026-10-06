"""book_dna (chunk C3, 2026-10-06): "N ahead of SPY" never travels without its
collapse factor.

Pins: twins collapse onto their parent; two books sharing 90% of their names are
one cluster and disjoint books are not; no label from this module exceeds
REPLICATED; the collapse sentence is in the rendered PAPER_ACCOUNTS markdown
(and says NOT COMPUTED rather than vanishing when book_dna could not run); a
book whose top holding carries > 50% of its excess is `one_name_dependence`.

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
    r"\d+ ahead of SPY = \d+ non-twin = \d+ independent clusters; largest cluster = .+ \(\d+%\)")


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


def _row(account, family, *, excess, book_id=None, inception=None, last_mark=None,
         spy=0.5, graded_against=None):
    return {"account": account, "family": family, "book_id": book_id,
            "inception": inception, "last_mark": last_mark, "start_capital": 1e6,
            "equity": 1e6 * (1 + (spy + excess) / 100), "roi_pct": spy + excess,
            "spy_same_window_pct": spy, "vs_spy_pp": excess, "status": "LIVE",
            "spy_base": "grade_entry_open", "graded_against": graded_against, "note": "",
            "n_positions": None, "source": "test"}


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
             _book("cc", "conc", ["C0", "B1", "B2", "B3"], weights=[0.7, 0.1, 0.1, 0.1])]
    rows = [_row("parent_a", "llm_portfolio:personal", excess=3.0, book_id="pa", inception=entry, last_mark=last),
            _row("parent_a__ew", "llm_portfolio:twin", excess=2.0, book_id="tw", inception=entry, last_mark=last),
            _row("near_copy", "llm_portfolio:personal", excess=2.5, book_id="p9", inception=entry, last_mark=last),
            _row("disjoint_b", "llm_portfolio:lib", excess=1.0, book_id="pb", inception=entry, last_mark=last),
            _row("conc", "llm_portfolio:personal", excess=20.0, book_id="cc", inception=entry, last_mark=last),
            _row("loser", "llm_portfolio:lib", excess=-4.0, book_id="pb", inception=entry, last_mark=last)]
    rc = {"generated_utc": f"{date.today().isoformat()}T05:00:00+00:00", "rows": rows,
          "aggregate": {"n_ahead_of_spy": 5, "honest_sentence": "Of 6 priced accounts, 5 are ahead of SPY."}}
    px = D.Prices(_bars(paths, dates))
    return rc, _inputs(books), px


def test_twins_collapse_and_overlap_clusters(world):
    rc, inp, px = world
    dna = D.build(rc, inp, px)
    s = dna["summary"]
    assert s["n_ahead_raw"] == 5
    assert s["n_ahead_non_twin"] == 4            # the twin is not a bet
    clusters = {frozenset(c["members"]) for c in dna["clusters"]}
    # 90% shared names -> one cluster; the disjoint book stands alone
    assert frozenset({"parent_a", "near_copy"}) in clusters
    assert frozenset({"disjoint_b"}) in clusters
    # 'conc' shares three B names with disjoint_b: Jaccard 3/11 < the 0.30 threshold
    assert s["n_independent_clusters_ahead"] == 3
    assert s["collapse_factor"] == round(5 / 3, 2)
    assert dna["twins_ahead"]["n"] == 1
    assert dna["twins_ahead"]["by_parent"] == {"parent_a": 1}
    assert COLLAPSE_RE.search(s["collapse_line"])


def test_cluster_function_directly():
    a = {"account": "a", "tickers": NAMES_A}
    b = {"account": "b", "tickers": NAMES_A9}
    c = {"account": "c", "tickers": NAMES_B}
    comps, edges = D.cluster([a, b, c], jaccard_threshold=0.5, corr_threshold=0.8, min_corr_obs=15)
    assert sorted(len(x) for x in comps) == [1, 2]
    assert edges and edges[0]["why"].startswith("jaccard")
    # identical return series link even with no holdings
    s = [("d1", 0.01, 0.0), ("d2", -0.02, 0.0), ("d3", 0.03, 0.0)]
    comps, _ = D.cluster([{"account": "x", "tickers": [], "_series": s},
                          {"account": "y", "tickers": [], "_series": list(s)}],
                         jaccard_threshold=0.5, corr_threshold=0.8, min_corr_obs=15)
    assert len(comps) == 1


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
    top = D.evidence_label(sessions=60, excess_pp=2.0, sub=ok_sub, fair_twin_excess_pp=1.0,
                           replicated_by=None, p=p)
    assert top["label"] == "REPLICATED"
    assert D.evidence_label(sessions=6, excess_pp=9.0, sub=ok_sub, fair_twin_excess_pp=9.0,
                            replicated_by="x", p=p)["label"] == "OBSERVED(6)"
    rc, inp, px = world
    for b in D.build(rc, inp, px)["books"]:
        assert not b["evidence"]["label"].startswith("VALIDATED")


def test_one_name_dependence(world):
    rc, inp, px = world
    books = {b["account"]: b for b in D.build(rc, inp, px)["books"]}
    conc = books["conc"]
    assert conc["tail"]["status"] == "OK"
    assert conc["tail"]["top1"]["ticker"] == "C0"
    assert conc["tail"]["top1"]["share"] > 0.5
    assert conc["one_name_dependence"] is True
    assert books["parent_a"]["one_name_dependence"] is False


def test_losers_carry_an_error_type(world):
    rc, inp, px = world
    dna = D.build(rc, inp, px)
    for l in dna["losers"]:
        assert l["error_type"] in D.ERROR_TYPES
    twin = {"family": "llm_portfolio:twin", "twin_of": "p"}
    assert D.classify_loser(twin, D.params())["error_type"] == "control_artifact"
    stale = {"family": "alpaca_fleet", "manager_sessions_since": 9, "manager_last_run": "x",
             "tail": {}, "subwindows": {}, "concentration": {}}
    assert D.classify_loser(stale, D.params())["error_type"] == "unmanaged"
    big = {"family": "alpaca_fleet", "manager_sessions_since": 0,
           "tail": {"status": "OK", "total": -100.0, "basis": "unrealized_pl",
                    "top1": {"ticker": "X", "share": 0.8}}, "subwindows": {}, "concentration": {}}
    assert D.classify_loser(big, D.params())["error_type"] == "sizing_concentration"


def _md_rc(world, tmp_path, runner=None):
    rc, inp, px = world
    rc = dict(rc)
    rc.update({"sources": {"spy_leg": "test", "website_lanes": {"source": "test", "fresh": True,
                                                                  "expected_nav_date": None}}})
    rc["aggregate"] = R.aggregate(rc["rows"])
    if runner is not None:
        R.attach_book_dna(rc, runner=runner)
    return rc


def test_markdown_prints_the_collapse_line(world, tmp_path):
    rc0, inp, px = world

    def runner(rc, run_id):
        dna = D.build(rc, inp, px)
        return dna, D.write(dna, tmp_path, run_id)

    rc = _md_rc(world, tmp_path, runner)
    md = R.render_markdown(rc, None)
    lines = md.splitlines()
    i = next(k for k, l in enumerate(lines) if "are ahead of SPY" in l)
    assert COLLAPSE_RE.search(lines[i + 1]), lines[i + 1]
    assert rc["aggregate"]["n_independent_clusters_ahead"] == 3
    assert "independent clusters" in rc["aggregate"]["honest_sentence"]
    assert list(tmp_path.glob("book_dna_*.json"))


def test_markdown_never_prints_the_count_alone(world, tmp_path):
    # a receipt book_dna never ran on, and one where it failed: the count is
    # still followed by a line saying it is NOT a count of independent bets
    rc = _md_rc(world, tmp_path)
    md = R.render_markdown(rc, None)
    assert "collapse NOT COMPUTED" in md

    def boom(rc, run_id):
        raise RuntimeError("no SPY bars")

    rc = _md_rc(world, tmp_path, boom)
    assert rc["aggregate"]["book_dna_status"] == "REFUSED"
    assert "no SPY bars" in rc["aggregate"]["collapse_line"]
    md = R.render_markdown(rc, None)
    lines = md.splitlines()
    i = next(k for k, l in enumerate(lines) if "are ahead of SPY" in l)
    assert "NOT a count of independent bets" in lines[i + 1]
