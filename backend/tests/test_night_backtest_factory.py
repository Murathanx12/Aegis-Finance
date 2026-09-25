"""The nightly backtest factory: ranks honestly, resumes, freezes twins, one ruler.

Spec `docs/research_notes/2026-09-26/spec_chunk3b_strategy_library_and_backtest_factory.md`,
"Tests first":
1. a planted panel where one signal has a known net edge: the library ranks it
   first, prints by-year, LOO, DSR at the count looked at, and the random-twin
   freeze happens;
2. (in test_strategy_library.py) a rule registered after 2024-06 has no
   quotable number before its registration;
3. (in test_strategy_library.py) the zero-cost refusal is inherited;
4. checkpoint/resume: stopped after 15 rules, the resume finishes 100 without
   recomputing the 15; a CRASH loses at most 10;
5. the SPY leg comes from `learner.benchmark` and its stamp validates.

Everything here is offline and writes only under tmp_path.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from backend import config as C
from backend.services import strategy_library as SL
from backend.tests.test_strategy_library import planted_panel, planted_spy
from learner import benchmark as bm
from scripts import night_backtest_factory as F

TODAY = date.today()


def _library(n_noise: int = 99) -> list:
    rules = [SL.Strategy("planted", "planted_family", "the planted alpha", SL.col("alpha"))]
    for i in range(n_noise):
        rules.append(SL.Strategy(f"noise_{i:02d}", f"fam_{i % 5}", "hash noise",
                                 SL.seeded_noise(1000 + i)))
    rules.append(SL.Strategy("random_ctl", "control", "random k", SL.seeded_noise(7),
                             control=True))
    return rules


def _spy_meta(spy: pd.Series) -> dict:
    return {"source": "test_matched",
            "market_benchmark": bm.matched(spy, "test_spy", construction=(
                "synthetic monthly market for an offline test"), freq="M").stamp()}


@pytest.fixture()
def ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "OPTIMUS_LEDGER_DIR", tmp_path)
    return tmp_path


def _bars_for(panel: pd.DataFrame, n: int = 30) -> pd.DataFrame:
    """Recent daily bars ending TODAY (twins draw only live names)."""
    syms = sorted(panel["symbol"].unique()) + ["SPY"]
    mdv = panel.drop_duplicates("symbol").set_index("symbol")["median_dollar_vol"]
    days = [TODAY - timedelta(days=n - 1 - i) for i in range(n)]
    rows = []
    for s in syms:
        px = 100.0
        vol = float(mdv.get(s, 1e9)) / px
        for d in days:
            rows.append({"symbol": s, "date": pd.Timestamp(d), "open": px, "high": px,
                         "low": px, "close": px, "volume": vol})
    return pd.DataFrame(rows)


def test_the_planted_rule_ranks_first_with_its_honest_columns(ledger):
    p = planted_panel()
    spy = planted_spy(p)
    board = F.run_factory(p, spy, _spy_meta(spy), today=TODAY, rules=_library(),
                          out=ledger / "lib", log=lambda *_: None)
    top = board["top_by_dsr"][0]
    assert top["id"] == "planted"
    assert board["multiplicity"]["n_candidate_rules"] == 100
    # every candidate cell (100 rules x k 10/20/50) is a trial; the control is not
    assert board["multiplicity"]["n_cells_looked_at"] == 300
    assert top["dsr_n_trials"] == 300
    assert board["multiplicity"]["controls_excluded_from_trials"] == ["random_ctl"]
    assert all(r["id"] != "random_ctl" for r in board["top_by_dsr"])
    # the honest columns are present and filled
    assert top["by_year_signs"] and len(top["by_year_signs"]) == 8
    assert top["loo_worst_mean_active"] is not None
    assert top["worst_cell"]["k"] in (10, 20, 50)
    assert top["t_active_horizon_blocks"] > 3
    assert top["dsr"] > 0.95
    assert board["read_me_first"].startswith("HINDSIGHT")


def test_the_md_prints_multiplicity_before_the_first_table(ledger):
    p = planted_panel(40, 60)
    spy = planted_spy(p)
    board = F.run_factory(p, spy, _spy_meta(spy), today=TODAY, rules=_library(20),
                          out=ledger / "lib", log=lambda *_: None)
    md = F.render_md(board)
    assert md.index("## Multiplicity") < md.index("## Top 10 by deflated Sharpe")
    assert "HINDSIGHT" in md.splitlines()[2]
    head = [ln for ln in md.splitlines() if ln.startswith("| id |")][0]
    assert head.index("by-year") < head.index("CAGR since 2020")
    assert head.index("LOO-worst") < head.index("CAGR since 2020")
    assert head.index("DSR") < head.index("CAGR since 2020")


def test_a_rule_whose_input_is_absent_is_refused_by_name(ledger):
    p = planted_panel(30, 40)
    spy = planted_spy(p)
    rules = _library(5) + [SL.Strategy("ghost", "g", "absent column", SL.col("nope"))]
    board = F.run_factory(p, spy, _spy_meta(spy), today=TODAY, rules=rules,
                          out=ledger / "lib", log=lambda *_: None)
    assert "ghost" in board["refused"] and "nope" in board["refused"]["ghost"]


def test_a_stop_after_15_resumes_to_100_without_recomputing(ledger):
    p = planted_panel(36, 60)
    spy = planted_spy(p)
    rules = _library()[:100]
    out = ledger / "lib"
    first = F.run_factory(p, spy, _spy_meta(spy), today=TODAY, rules=rules, out=out,
                          stop_after=15, log=lambda *_: None)
    assert first["partial"] == "stop_after=15" and first["n_rules_done"] == 15
    second = F.run_factory(p, spy, _spy_meta(spy), today=TODAY, rules=rules, out=out,
                           resume=True, log=lambda *_: None)
    assert second["n_computed_this_run"] == 85
    assert second["n_rules_done"] == 100 and second["partial"] is None


def test_a_crash_loses_at_most_ten_rules(ledger, monkeypatch):
    p = planted_panel(36, 60)
    spy = planted_spy(p)
    rules = _library()[:100]
    out = ledger / "lib"
    real = F.evaluate_rule
    calls = {"n": 0}

    def dies_on_16th(*a, **kw):
        calls["n"] += 1
        if calls["n"] == 16:
            raise KeyboardInterrupt("the PC died")
        return real(*a, **kw)

    monkeypatch.setattr(F, "evaluate_rule", dies_on_16th)
    with pytest.raises(KeyboardInterrupt):
        F.run_factory(p, spy, _spy_meta(spy), today=TODAY, rules=rules, out=out,
                      log=lambda *_: None)
    monkeypatch.setattr(F, "evaluate_rule", real)
    board = F.run_factory(p, spy, _spy_meta(spy), today=TODAY, rules=rules, out=out,
                          resume=True, log=lambda *_: None)
    assert board["n_computed_this_run"] == 90          # 10 survived the crash
    assert board["n_rules_done"] == 100


def test_a_resume_under_a_changed_library_is_refused(ledger):
    p = planted_panel(30, 40)
    spy = planted_spy(p)
    out = ledger / "lib"
    F.run_factory(p, spy, _spy_meta(spy), today=TODAY, rules=_library(10), out=out,
                  stop_after=3, log=lambda *_: None)
    with pytest.raises(ValueError, match="REFUSED to resume"):
        F.run_factory(p, spy, _spy_meta(spy), today=TODAY, rules=_library(11), out=out,
                      resume=True, log=lambda *_: None)


def test_the_leaderboard_is_idempotent_per_day(ledger):
    p = planted_panel(40, 60)
    spy = planted_spy(p)
    out = ledger / "lib"
    b1 = F.run_factory(p, spy, _spy_meta(spy), today=TODAY, rules=_library(20), out=out,
                       log=lambda *_: None)
    F.write_outputs(b1, out=out, today=TODAY)
    one = (out / f"leaderboard_{TODAY}.json").read_bytes()
    md1 = (out / "LEADERBOARD.md").read_bytes()
    b2 = F.run_factory(p, spy, _spy_meta(spy), today=TODAY, rules=_library(20), out=out,
                       log=lambda *_: None)
    b2.pop("n_computed_this_run")
    b1.pop("n_computed_this_run")
    F.write_outputs(b2, out=out, today=TODAY)
    assert b1 == b2
    assert (out / "LEADERBOARD.md").read_bytes() == md1
    assert (out / f"leaderboard_{TODAY}.json").read_bytes() != b"" and one


def test_the_dsr_leader_gets_a_frozen_forward_book_with_four_twins(ledger, capsys):
    from backend.services import llm_portfolio as LP
    p = planted_panel()
    spy = planted_spy(p)
    rules = _library(30)
    board = F.run_factory(p, spy, _spy_meta(spy), today=TODAY, rules=rules,
                          out=ledger / "lib", log=lambda *_: None)
    bars = _bars_for(p)
    lines = []
    books = F.freeze_forward(board, p, bars, today=TODAY, rules=rules, log=lines.append)
    assert books["planted"]["status"] == "FROZEN"
    assert books["planted"]["name"] == f"lib_planted_{TODAY}"
    assert books["planted"]["twins"] == ["ew", "random_same_band", "sector_etf", "spy"]
    assert any(ln.startswith(f"WORST CASE lib_planted_{TODAY}") and "$1,000,000" in ln
               for ln in lines)
    recs = LP.read_books()
    names = [r["name"] for r in recs]
    assert f"lib_planted_{TODAY}" in names
    twins = [r for r in recs if r.get("parent_book_id") == books["planted"]["book_id"]]
    assert {t["twin"] for t in twins} == {"ew", "sector_etf", "spy", "random_same_band"}
    # the planted top-20 is what the book holds
    held = {p_["ticker"] for p_ in recs[names.index(f"lib_planted_{TODAY}")]["positions"]}
    want = {x["symbol"] for x in SL.latest_selection(p, rules[0])}
    assert want <= held
    # a second night does not freeze it again
    n_before = len(LP.read_books())
    again = F.freeze_forward(board, p, bars, today=TODAY, rules=rules, log=lines.append)
    assert again["planted"]["status"] == "ALREADY_HAS_A_FORWARD_BOOK"
    assert len(LP.read_books()) - n_before <= 2 * 5    # only forward-only rules could add
    # and the forward/backtest line exists for it
    fwd = F.backtest_vs_forward(board, bars, today=TODAY)
    assert any(ln.startswith(f"lib_planted_{TODAY}: forward_21d_vs_spy=") for ln in fwd)


def test_the_spy_leg_comes_from_learner_benchmark_offline(ledger):
    """Offline, the canonical id refuses; the bars leg is stamped by the ONE ruler."""
    dates = pd.bdate_range("2019-01-01", "2021-12-31")
    syms = np.array(["AAA", "SPY"])
    px = np.cumprod(1 + np.full((len(dates), 2), 0.0004), axis=0) * 100
    W = {"dates": pd.DatetimeIndex(dates), "symbols": syms, "open": px, "close": px}
    me = pd.Series(np.arange(len(dates)), index=dates).groupby(dates.to_period("M")).max()
    panel = pd.DataFrame({"date": dates[me.to_numpy()], "is_month_end": True})
    s, meta = F.spy_leg(panel, W, network=False)
    ok, why = bm.validate_stamp(meta["market_benchmark"])
    assert ok, why
    assert meta["source"] == "matched:spy_bars_entry_aligned"
    assert len(s) == len(me) - 2 and (s > 0).all()


def test_the_worst_case_line_is_in_dollars():
    ln = F.worst_case_line("lib_x_2026-09-26", 20, 1_000_000.0)
    assert "20 names x 5.00%" in ln and "-$300,000" in ln and "-$50,000" in ln


def test_when_every_dsr_rounds_to_zero_the_order_is_by_evidence_not_by_name(ledger, monkeypatch):
    """Regression, 2026-09-26: 336 DSRs of 0.000 were ranked by id, reversed,
    and the 'top 10' that got forward books was the end of the alphabet."""
    p = planted_panel(60, 80)
    spy = planted_spy(p)
    real = SL.deflate

    def flattened(cells, **kw):
        real(cells, **kw)
        for c in cells:
            c["dsr"] = 0.0

    monkeypatch.setattr(SL, "deflate", flattened)
    rules = _library(20)
    rules[0] = SL.Strategy("aaa_planted", "planted_family", "alpha, named first (reverse-id order puts it LAST)", SL.col("alpha"))
    board = F.run_factory(p, spy, _spy_meta(spy), today=TODAY, rules=rules,
                          out=ledger / "lib", log=lambda *_: None)
    assert all(r["dsr"] == 0.0 for r in board["top_by_dsr"])
    assert board["top_by_dsr"][0]["id"] == "aaa_planted"
    zs = [r["dsr_z"] for r in board["top_by_dsr"]]
    assert zs == sorted(zs, reverse=True)
