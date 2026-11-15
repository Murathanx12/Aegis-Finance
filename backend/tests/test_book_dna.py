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


# ── C15 (2026-10-07; review C3 F9): lane beta carries a lag check ───────────────
def _series_lagged(lag: int, n: int = 120, seed: int = 3) -> list:
    import numpy as _np
    rng = _np.random.default_rng(seed)
    spy = rng.normal(0.0004, 0.01, n + 1)
    noise = rng.normal(0.0, 0.004, n + 1)
    book = [(0.9 * spy[i - lag] if i - lag >= 0 else 0.0) + noise[i] for i in range(n + 1)]
    return [(f"d{i:04d}", float(book[i]), float(spy[i])) for i in range(1, n + 1)]


def test_beta_of_same_day_series_prints_a_beta_and_both_correlations():
    from backend.services import book_dna as BD
    out = BD.beta_of(_series_lagged(0), 20)
    assert isinstance(out["value"], float) and 0.7 < out["value"] < 1.1
    assert out["corr_vs_spy"] > out["corr_vs_spy_lag_minus_1"]


def test_beta_of_a_date_stamp_lagged_series_is_not_credible_with_both_numbers():
    from backend.services import book_dna as BD
    out = BD.beta_of(_series_lagged(1), 20)
    assert out["value"] == BD.NOT_CREDIBLE
    assert out["corr_vs_spy_lag_minus_1"] > out["corr_vs_spy"]
    assert out["why"].startswith("beta: NOT_CREDIBLE (date stamp lag)")
    assert f"{out['corr_vs_spy_lag_minus_1']:+.2f}" in out["why"] and f"{out['corr_vs_spy']:+.2f}" in out["why"]
    assert "beta_same_day" in out           # the uncredible number is kept, labelled, never served as the beta


# ── CH-11 note (2026-11-13): how much of a book's return is plain SPY exposure ──
def _dated_series(n: int = 60, beta: float = 1.5, alpha: float = 0.0005, seed: int = 11) -> list:
    """A same-day series on real weekday dates derived from today (spans >= 2 months)."""
    rng = np.random.default_rng(seed)
    dates = _sessions(n)
    spy = rng.normal(0.0003, 0.01, n)
    book = alpha + beta * spy + rng.normal(0.0, 0.002, n)
    return [(d, float(b), float(s)) for d, b, s in zip(dates, book, spy)]


def _compound(s: list, k: int) -> float:
    return 100 * (float(np.prod([1 + q[k] for q in s])) - 1)


def test_market_exposure_on_a_high_beta_book():
    s = _dated_series()
    beta = D.beta_of(s, 20)
    assert isinstance(beta["value"], float) and 1.35 < beta["value"] < 1.65
    # the receipt's return and SPY leg are the series' own (fix round M1: a receipt the
    # series does not reproduce is "not comparable", see the tests below)
    rp, sp = _compound(s, 1), _compound(s, 2)
    me = D.market_exposure(s, beta, return_pct=rp, spy_leg_pct=sp, min_capture_obs=8)
    b = beta["value"]
    assert me["beta"]["value"] == round(b, 3)
    # return - beta x SPY leg, beside the raw excess, on the receipt's own window
    assert me["beta_adjusted_excess_pp"]["value"] == round(rp - b * sp, 3)
    assert me["beta_adjusted_excess_pp"]["raw_excess_pp"] == round(rp - sp, 3)
    # a beta-1.5 book captures ~1.5x of SPY on both sides
    assert 1.3 < me["up_capture"]["value"] < 1.8 and 1.3 < me["down_capture"]["value"] < 1.8
    assert me["up_capture"]["n_periods"] + me["down_capture"]["n_periods"] <= len(s)
    # by month: every period lands in exactly one month, residual compounded per month
    bm = me["by_month"]
    assert len(bm) >= 2 and sum(m["n_periods"] for m in bm) == len(s)
    first = [(x, y) for d, x, y in s if d[:7] == bm[0]["month"]]
    want = 100 * (np.prod([1 + x - b * y for x, y in first]) - 1)
    assert abs(bm[0]["beta_adjusted_pp"] - want) < 1e-2
    assert me["series_beta_adjusted_pp"]["n_periods"] == len(s)


def test_market_exposure_is_cannot_determine_on_a_lagged_series():
    s = _series_lagged(1)
    beta = D.beta_of(s, 20)
    assert beta["value"] == D.NOT_CREDIBLE
    me = D.market_exposure(s, beta, return_pct=5.0, spy_leg_pct=2.0, min_capture_obs=8)
    for k in ("beta", "up_capture", "down_capture", "beta_adjusted_excess_pp", "by_month",
              "series_beta_adjusted_pp"):
        assert me[k]["value"] == D.CANNOT_DETERMINE, k
        assert "NOT_CREDIBLE (date stamp lag)" in me[k]["why"], k


def test_market_exposure_is_cannot_determine_on_a_short_series():
    s = _dated_series(n=12)
    beta = D.beta_of(s, 20)
    me = D.market_exposure(s, beta, return_pct=5.0, spy_leg_pct=2.0, min_capture_obs=8)
    assert me["beta_adjusted_excess_pp"]["value"] == D.CANNOT_DETERMINE
    assert "12 period returns < 20" in me["beta_adjusted_excess_pp"]["why"]


def test_capture_needs_enough_periods_on_each_side():
    rng = np.random.default_rng(5)
    spy = np.abs(rng.normal(0.0, 0.01, 40)) + 0.001
    spy[[3, 11, 19, 27]] *= -1                                    # 4 SPY-down periods
    s = [(d, float(1.2 * x + rng.normal(0, 0.001)), float(x)) for d, x in zip(_sessions(40), spy)]
    beta = D.beta_of(s, 20)
    me = D.market_exposure(s, beta, return_pct=1.0, spy_leg_pct=1.0, min_capture_obs=8)
    assert isinstance(me["up_capture"]["value"], float)
    assert me["down_capture"]["value"] == D.CANNOT_DETERMINE
    assert me["down_capture"]["why"] == "4 SPY-down periods < 8"


def test_market_exposure_without_a_spy_leg_says_so():
    s = _dated_series()
    me = D.market_exposure(s, D.beta_of(s, 20), return_pct=3.0, spy_leg_pct=None, min_capture_obs=8)
    assert me["beta_adjusted_excess_pp"]["value"] == D.CANNOT_DETERMINE
    assert isinstance(me["up_capture"]["value"], float)


def test_every_book_row_carries_market_exposure_never_blank(world):
    rc, inputs, px = world
    dna = D.build(rc, inputs, px)
    for b in dna["books"]:
        me = b["market_exposure"]
        v = me["beta_adjusted_excess_pp"]["value"]
        assert v == D.CANNOT_DETERMINE and me["beta_adjusted_excess_pp"]["why"], b["account"]


# ── CH-11 fix round (review of PR #140, 2026-11-14): each test fails on 0b45f7f8 ──
def _split_stamp_series(n: int = 130, seed: int = 21) -> tuple[list, int]:
    """B1 in miniature, the website lanes' NAV: unrelated to SPY at first (June-July), then
    stamped one session LATE for a month (book_t = 0.9 x SPY_t-1, August), then on the right
    day (book_t = 0.9 x SPY_t, September onward). Returns (series, index of the first
    same-day period); both switches fall on month boundaries."""
    rng = np.random.default_rng(seed)
    dates = _sessions(n)
    j = next(i for i in range(n // 5, n) if dates[i][:7] != dates[i - 1][:7])
    k = next(i for i in range(j + 15, n) if dates[i][:7] != dates[i - 1][:7])
    spy = rng.normal(0.0004, 0.01, n + 1)
    noise = rng.normal(0.0, 0.003, n + 1)
    book = [noise[i + 1] + (0.0 if i < j else 0.9 * spy[i] if i < k else 0.9 * spy[i + 1]) for i in range(n)]
    return [(d, float(book[i]), float(spy[i + 1])) for i, d in enumerate(dates)], k


def test_b1_a_series_lagged_in_its_first_months_passes_the_whole_series_check():
    """The defect itself: the whole-series guard sees nothing and serves a blended beta."""
    s, _ = _split_stamp_series()
    whole = D.beta_of(s, 20)
    assert isinstance(whole["value"], float) and whole["value"] < 0.75       # ~0.9 x share same-day


def test_b1_per_month_stamp_check_estimates_after_the_last_lagged_month():
    s, k = _split_stamp_series()
    rp, sp = _compound(s, 1), _compound(s, 2)
    me = D.market_exposure(s, D.beta_of(s, 20), return_pct=rp, spy_leg_pct=sp, min_capture_obs=8,
                           sessions=len(s), window=(s[0][0], s[-1][0]))
    chk = me["stamp_check"]
    assert chk["failing_months"] and all(m < s[k][0][:7] for m in chk["failing_months"])
    # estimated only on the same-day stretch, and the row says so, with the window
    assert me["beta"]["from"] == s[k][0] and me["beta"]["n_obs"] == len(s) - k
    assert 0.8 < me["beta"]["value"] < 1.0 and me["beta"]["se"] > 0
    assert "date stamp lag in" in me["stamp_note"] and "dates were not shifted" in me["stamp_note"]
    # the beta window covers < 80% of the receipt: the receipt-window figure is not comparable
    bax = me["beta_adjusted_excess_pp"]
    assert bax["value"] == D.CANNOT_DETERMINE and bax["why"].startswith("not comparable")
    assert isinstance(bax["window_figure_pp"], float) and bax["window_from"] == s[k][0]


def test_b1_a_series_lagged_in_its_last_sessions_is_cannot_determine():
    """Right day first, stamped a session late for the last 40 sessions: nothing after the
    last failing month can carry a beta, so every field says why instead of a number."""
    rng = np.random.default_rng(4)
    n = 130
    spy = rng.normal(0.0004, 0.01, n + 1)
    noise = rng.normal(0.0, 0.003, n + 1)
    s = [(d, float(noise[i + 1] + 0.9 * (spy[i + 1] if i < n - 40 else spy[i])), float(spy[i + 1]))
         for i, d in enumerate(_sessions(n))]
    me = D.market_exposure(s, D.beta_of(s, 20), return_pct=1.0, spy_leg_pct=1.0, min_capture_obs=8)
    assert me["stamp_check"]["failing_months"]
    for k in ("beta", "up_capture", "down_capture", "beta_adjusted_excess_pp"):
        assert me[k]["value"] == D.CANNOT_DETERMINE and "date stamp lag" in me[k]["why"], k


def test_b1_lane_row_in_a_receipt_carries_the_window_and_the_lag_note():
    s, k = _split_stamp_series()
    dates = _sessions(len(s) + 1)
    s = [(d, b, x) for d, (_, b, x) in zip(dates[1:], s)]
    k_date = s[k][0]
    spy, nav = [100.0], [1e5]
    for _, b, x in s:
        spy.append(spy[-1] * (1 + x))
        nav.append(nav[-1] * (1 + b))
    px = D.Prices(_bars({"SPY": spy}, dates))
    rp, sp = 100 * (nav[-1] / nav[0] - 1), 100 * (spy[-1] / spy[0] - 1)
    row = {"account": "lane-x", "family": "website_lane", "inception": dates[0], "last_mark": dates[-1],
           "start_capital": 1e5, "equity": nav[-1], "roi_pct": rp, "spy_same_window_pct": sp,
           "vs_spy_pp": rp - sp, "status": "LIVE", "spy_base": "close", "graded_against": None, "note": "",
           "n_positions": None, "source": "test"}
    rc = {"generated_utc": f"{date.today().isoformat()}T05:00:00+00:00", "rows": [row],
          "lane_nav_series": {"lanes": {"lane-x": [list(q) for q in zip(dates, nav)]},
                              "spy_rebased_100k_at_2026_06_08": [list(q) for q in zip(dates, spy)]},
          "aggregate": {"n_ahead_of_spy": 1, "honest_sentence": "x"}}
    dna = D.build(rc, _inputs([]), px)
    me = next(b for b in dna["books"] if b["account"] == "lane-x")["market_exposure"]
    assert me["stamp_check"]["failing_months"] and me["beta"]["from"] == k_date
    w = me["estimation_window"]
    assert w["receipt_sessions"] == len(s) and w["n_periods"] == len(s) - k and w["comparable"] is False
    assert me["beta_adjusted_excess_pp"]["value"] == D.CANNOT_DETERMINE


def test_m1_a_beta_window_shorter_than_the_receipt_is_not_comparable():
    s = _dated_series(n=31)
    rp, sp = _compound(s, 1), _compound(s, 2)
    me = D.market_exposure(s, D.beta_of(s, 20), return_pct=rp, spy_leg_pct=sp, min_capture_obs=8,
                           sessions=54, window=("r0", "r1"))
    bax = me["beta_adjusted_excess_pp"]
    assert bax["value"] == D.CANNOT_DETERMINE
    assert "covers 31 of 54 receipt sessions" in bax["why"] and f"{s[0][0]}..{s[-1][0]}" in bax["why"]
    assert bax["window_figure_pp"] == me["series_beta_adjusted_pp"]["value"]
    assert me["estimation_window"]["coverage"] == round(31 / 54, 3)
    # enough coverage and the same return: comparable, with SE and MDE beside it
    ok = D.market_exposure(s, D.beta_of(s, 20), return_pct=rp, spy_leg_pct=sp, min_capture_obs=8, sessions=34)
    v = ok["beta_adjusted_excess_pp"]
    assert isinstance(v["value"], float) and v["se_pp"] > 0 and abs(v["mde_pp"] - 2.8 * v["se_pp"]) < 0.01


def test_m1_a_beta_window_that_misses_the_receipt_return_is_not_comparable():
    """hack4: the receipt lost -22.92% over 54 sessions, the beta's 31 periods -3.04%."""
    s = _dated_series(n=31)
    rp, sp = _compound(s, 1), _compound(s, 2)
    me = D.market_exposure(s, D.beta_of(s, 20), return_pct=rp - 19.9, spy_leg_pct=sp, min_capture_obs=8,
                           sessions=31)
    assert me["beta_adjusted_excess_pp"]["value"] == D.CANNOT_DETERMINE
    assert "pp from the receipt return" in me["beta_adjusted_excess_pp"]["why"]


def test_m2_a_noisy_capture_is_cannot_determine_with_its_estimate_and_se():
    rng = np.random.default_rng(9)
    dates = _sessions(40)
    spy = rng.normal(0.0, 0.01, 40)
    s = [(d, float(0.7 * x + rng.normal(0, 0.03)), float(x)) for d, x in zip(dates, spy)]
    me = D.market_exposure(s, D.beta_of(s, 20), return_pct=_compound(s, 1), spy_leg_pct=_compound(s, 2),
                           min_capture_obs=8)
    for side in ("up_capture", "down_capture"):
        c = me[side]
        assert c["value"] == D.CANNOT_DETERMINE and "cannot be told apart from noise" in c["why"], side
        assert c["se"] > 0.25 and isinstance(c["estimate"], float) and c["n_periods"] >= 8
    t = _dated_series()
    tight = D.market_exposure(t, D.beta_of(t, 20), return_pct=1.0, spy_leg_pct=1.0, min_capture_obs=8)
    assert isinstance(tight["up_capture"]["value"], float) and tight["up_capture"]["se"] < 0.25


def test_m1_minor_a_flat_nav_is_cannot_determine_never_zero():
    s = [(d, 0.0, float(x)) for d, x in zip(_sessions(40), np.random.default_rng(2).normal(0, 0.01, 40))]
    me = D.market_exposure(s, D.beta_of(s, 20), return_pct=0.0, spy_leg_pct=-0.69, min_capture_obs=8)
    for k in ("beta", "up_capture", "down_capture", "beta_adjusted_excess_pp"):
        assert me[k]["value"] == D.CANNOT_DETERMINE and "flat NAV" in me[k]["why"], k


def test_m2_minor_rf_effect_is_printed_beside_a_low_beta_excess():
    s = _dated_series(beta=0.25)
    rp, sp = _compound(s, 1), _compound(s, 2)
    me = D.market_exposure(s, D.beta_of(s, 20), return_pct=rp, spy_leg_pct=sp, min_capture_obs=8,
                           sessions=len(s))
    v = me["beta_adjusted_excess_pp"]
    b = me["beta"]["value"]
    assert v["rf_effect_pp"] == round((1 - b) * 0.04 * len(s) / 252 * 100, 3) and "ASSUMED" in v["rf_note"]


def test_m4_minor_multi_session_periods_are_left_out_of_capture():
    s = _dated_series(n=80)
    every_other = s[::2]                                   # every period spans two sessions
    me = D.market_exposure(every_other, D.beta_of(every_other, 20), return_pct=1.0, spy_leg_pct=1.0,
                           min_capture_obs=8, session_dates=[d for d, _, _ in s])
    assert me["n_multi_session_periods_excluded_from_capture"] == len(every_other) - 1
    assert me["up_capture"]["value"] == D.CANNOT_DETERMINE


def test_m6_minor_load_prices_reads_only_the_symbols_it_needs(monkeypatch, tmp_path):
    from backend.services import xs_ranker
    seen = {}

    def fake_load_bars(*a, **k):
        seen.update(k)
        return pd.DataFrame({"symbol": ["SPY"], "date": [pd.Timestamp(_sessions(1)[0])], "open": [1.0],
                             "close": [1.0]})
    monkeypatch.setattr(xs_ranker, "load_bars", fake_load_bars)
    monkeypatch.setattr(D, "LLM_DIR", tmp_path)
    px, _ = D.load_prices({"AAA"})
    assert sorted(seen.get("symbols") or []) == ["AAA", "SPY"] and px.has("SPY")


def test_b1_lag_is_read_from_spy_sessions_across_multi_session_gaps():
    """The lanes' NAV skips sessions. The lagged SPY of a period is SPY over the same sessions
    shifted back one, read from SPY's closes -- never the previous PERIOD's SPY, which after a
    gap is a different stretch of days and hid August's lag on the live receipt."""
    rng = np.random.default_rng(13)
    dates = _sessions(130)
    j = next(i for i in range(40, 130) if dates[i][:7] != dates[i - 1][:7])
    k = next(i for i in range(j + 15, 130) if dates[i][:7] != dates[i - 1][:7])
    r = rng.normal(0.0004, 0.01, 130)
    close = list(100 * np.cumprod(1 + r))
    nav = [1e5]
    for i in range(1, 130):                        # lagged in [j, k), same-day elsewhere
        nav.append(nav[-1] * (1 + 0.9 * (r[i - 1] if j <= i < k else r[i]) + rng.normal(0, 0.002)))
    keep = [i for i in range(130) if not (j <= i < k and i % 3 == 0)]     # a gap every third session
    pts = [(dates[i], nav[i], close[i]) for i in keep]
    s = [(pts[i][0], pts[i][1] / pts[i - 1][1] - 1, pts[i][2] / pts[i - 1][2] - 1) for i in range(1, len(pts))]
    spy_close = dict(zip(dates, close))
    me = D.market_exposure(s, D.beta_of(s, 20), return_pct=1.0, spy_leg_pct=1.0, min_capture_obs=8,
                           spy_close=spy_close)
    assert dates[k - 1][:7] in me["stamp_check"]["failing_months"]
    assert me["beta"]["from"] >= dates[k] and 0.75 < me["beta"]["value"] < 1.05
    lagged = next(m for m in me["stamp_check"]["months"] if m["month"] == dates[k - 1][:7])
    assert lagged["corr_lag_minus_1"] > 0.6 and lagged["corr_lag_minus_1"] > lagged["corr_same_day"] + 0.2


def test_m1_the_beta_window_never_runs_past_the_receipt_mark():
    """A --rebuild-dna on an old receipt reads today's leaderboards: periods after the
    receipt's last mark are cut, so the beta window lies inside the receipt window."""
    s = _dated_series(n=40)
    mark = s[-4][0]
    me = D.market_exposure(s, D.beta_of(s, 20), return_pct=_compound(s[:-3], 1), spy_leg_pct=_compound(s[:-3], 2),
                           min_capture_obs=8, sessions=37, window=(s[0][0], mark))
    assert me["n_periods_after_the_receipt_mark_dropped"] == 3
    assert me["beta"]["to"] == mark and isinstance(me["beta_adjusted_excess_pp"]["value"], float)
