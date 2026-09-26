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
from pathlib import Path

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
    top_hd = "## Top 10 by net return vs SPY in the " + SL.SELECTION_WINDOW_LABEL
    assert md.index("## Multiplicity") < md.index(top_hd)
    # review 2026-09-26: the dev-selected read is printed BEFORE the 2024-26 sort
    assert md.index("## Dev-selected, 2024-26-evaluated") < md.index(top_hd)
    # never "sealed" without the qualifier
    assert "SEALED" not in md and "sealed vs SPY" not in md
    # the FIRST id table is the 2024-26 sort's, and its first number is 2024-26-vs-SPY
    head = [ln for ln in md.splitlines() if ln.startswith("| id |")][0]
    assert head.index("2024-26 vs SPY") < head.index("dev CAGR")
    assert head.index("2024-26 DSR") < head.index("dev CAGR")
    for col in ("LOO-worst", "top-5-mo share", "turnover/yr", "cost bps/yr", "max DD",
                "recent-126", "DSR full"):
        assert col in head
    hind = [ln for ln in md.splitlines() if ln.startswith("| id |") and "CAGR since 2020" in ln][0]
    assert hind.index("by-year") < hind.index("CAGR since 2020")
    assert hind.index("DSR") < hind.index("CAGR since 2020")


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
    """Same panel -> same board. Each RUN writes its own receipt (run id in the
    name, never overwritten); the date-named file and LEADERBOARD.md are the
    refreshed 'latest' copies (review 2026-09-26 finding 0)."""
    import json
    p = planted_panel(40, 60)
    spy = planted_spy(p)
    out = ledger / "lib"
    b1 = F.run_factory(p, spy, _spy_meta(spy), today=TODAY, rules=_library(20), out=out,
                       log=lambda *_: None)
    w1 = F.write_outputs(b1, out=out, today=TODAY, run_id=f"{TODAY}T010000Z")
    b2 = F.run_factory(p, spy, _spy_meta(spy), today=TODAY, rules=_library(20), out=out,
                       log=lambda *_: None)
    b2.pop("n_computed_this_run")
    b1.pop("n_computed_this_run")
    w2 = F.write_outputs(b2, out=out, today=TODAY, run_id=f"{TODAY}T020000Z")
    assert b1 == b2
    r1, r2 = Path(w1["leaderboard"]), Path(w2["leaderboard"])
    assert r1.name == f"leaderboard_{TODAY}T010000Z.json" and r1.exists()
    assert r2.name == f"leaderboard_{TODAY}T020000Z.json" and r2.exists()
    d1, d2 = (json.loads(x.read_text(encoding="utf-8")) for x in (r1, r2))
    assert d1["run_id"] != d2["run_id"] and d1["receipt"].endswith(r1.name)
    assert {k: v for k, v in d1.items() if k not in ("run_id", "receipt", "n_computed_this_run")} ==         {k: v for k, v in d2.items() if k not in ("run_id", "receipt", "n_computed_this_run")}
    latest = json.loads((out / f"leaderboard_{TODAY}.json").read_text(encoding="utf-8"))
    assert latest["run_id"] == d2["run_id"]
    assert r2.name in (out / "LEADERBOARD.md").read_text(encoding="utf-8")
    with pytest.raises(FileExistsError):
        F.write_outputs(b1, out=out, today=TODAY, run_id=f"{TODAY}T010000Z")
    assert F.new_run_id().startswith(str(date.today())[:4]) and F.new_run_id().endswith("Z")


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


# ═════════════════ chunk D: sealed columns, the sort, the replication file ═════

_NEW_COLS = ("dev_cagr", "sealed_cagr", "sealed_vs_spy", "recent_126_return", "turnover_annual",
             "cost_bps_paid", "max_dd", "sealed_dsr", "dsr", "loo_worst_mean_active",
             "top5_months_share_of_log_return", "economic_reason", "n_sealed_months")


def test_every_row_carries_the_sealed_columns(ledger):
    p = planted_panel()
    spy = planted_spy(p)
    board = F.run_factory(p, spy, _spy_meta(spy), today=TODAY, rules=_library(20),
                          out=ledger / "lib", log=lambda *_: None)
    for r in board["all_rows"]:
        for c in _NEW_COLS:
            assert c in r, (r["id"], c)
        assert r["sealed_vs_spy"] is not None and r["n_sealed_months"] == 24
    ob = board["objective"]
    assert ob["dev_end"] == "2023-12-31" and ob["sealed_start"] == "2024-01-01"
    assert board["multiplicity"]["cells_looked_at"] == 63        # 21 rules x k 10/20/50
    assert ob["noise_sharpe_ceiling_monthly_sealed"] > ob["noise_sharpe_ceiling_monthly_full"] > 0
    assert SL.SELECTION_WINDOW_LABEL in ob["honest_note"]
    assert "nobody's eyes were closed" in ob["honest_note"]


def test_the_primary_sort_is_sealed_net_return_vs_spy(ledger):
    p = planted_panel()
    spy = planted_spy(p)
    board = F.run_factory(p, spy, _spy_meta(spy), today=TODAY, rules=_library(30),
                          out=ledger / "lib", log=lambda *_: None)
    top = board["top_by_sealed_vs_spy"]
    v = [r["sealed_vs_spy"] for r in top]
    assert v == sorted(v, reverse=True)
    assert top[0]["id"] == "planted"
    best = max(board["all_rows"], key=lambda r: r["sealed_vs_spy"])
    assert top[0]["id"] == best["id"]
    # the sort key is the sealed number even when full-sample DSR disagrees
    rows = [{"id": "a", "sealed_vs_spy": 0.10, "sealed_dsr_z": -1.0, "dsr": 0.0},
            {"id": "b", "sealed_vs_spy": 0.02, "sealed_dsr_z": 3.0, "dsr": 0.99}]
    assert sorted(rows, key=F.sealed_sort_key, reverse=True)[0]["id"] == "a"


def test_the_replication_file_round_trips(ledger):
    import json
    p = planted_panel()
    spy = planted_spy(p)
    rules = _library(12)
    out = ledger / "lib"
    board = F.run_factory(p, spy, _spy_meta(spy), today=TODAY, rules=rules, out=out,
                          log=lambda *_: None)
    path = F.write_replication(board, p, spy, rules, out=out, today=TODAY,
                               run_id=f"{TODAY}T030405Z")
    assert path.name == f"top10_for_replication_{TODAY}T030405Z.json"
    assert (out / f"top10_for_replication_{TODAY}.json").read_bytes() == path.read_bytes()
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert len(doc["rows"]) == 10
    assert set(doc["cost_model"]["bands_bps_round_trip"]) == {"mega", "large", "mid", "small"}
    assert doc["split"]["sealed_start"] == "2024-01-01"
    by_id = {r["id"]: r for r in board["all_rows"]}
    for row, chk in zip(doc["rows"], F.check_replication(doc)):
        assert row["id"] == [r["id"] for r in board["top_by_sealed_vs_spy"]][doc["rows"].index(row)]
        assert row["universe_filter"] and row["rule_one_line"] and row["fingerprint"]
        assert row["rebalance_dates"] and all(
            len(row["held_symbols_by_date"][d]) == row["k"] for d in row["rebalance_dates"])
        assert chk["gross_minus_cost_equals_net"]
        # the file's own monthly series reproduces the board's sealed CAGR
        assert chk["sealed_cagr"] == pytest.approx(by_id[row["id"]]["sealed_cagr"], abs=1e-5)
        spy_s = [x["spy"] for x in row["monthly_return_series"] if x["window"].startswith("sealed")]
        assert SL._cagr(spy_s) == pytest.approx(by_id[row["id"]]["sealed_spy_cagr"], abs=1e-5)


def test_a_forward_only_rule_is_refused_not_backtested(ledger):
    p = planted_panel(30, 40)
    spy = planted_spy(p)
    rules = _library(5) + [SL.Strategy("fwd", "attention", "thesis cards", SL.col("alpha"),
                                       forward_only=True)]
    board = F.run_factory(p, spy, _spy_meta(spy), today=TODAY, rules=rules,
                          out=ledger / "lib", log=lambda *_: None)
    assert "FORWARD_ONLY" in board["refused"]["fwd"]
    assert board["multiplicity"]["cells_looked_at"] == 6 * 2     # 40 names: k=50 never fills


# ── the freeze gate (review 2026-09-26 chunks D+E, adjudicated) ─────────────

_GOOD_ROW = {"id": "g", "family": "momentum", "dev_vs_spy": 0.05, "sealed_vs_spy": 0.08,
             "top5_months_share_of_log_return": 0.4, "max_dd": -0.30,
             "loo_worst_mean_active": 0.004}


def _gate_bars(names, end, *, corr_pair=None, n=90, seed=5):
    """Daily closes; `corr_pair` names share one return stream (rho ~ 1)."""
    rng = np.random.default_rng(seed)
    days = pd.bdate_range(end=end, periods=n)
    common = rng.normal(0, 0.02, n)
    rows = []
    for s in list(names) + ["SPY"]:
        r = common if corr_pair and s in corr_pair else rng.normal(0, 0.02, n)
        px = 100 * np.cumprod(1 + r)
        rows += [{"symbol": s, "date": d, "open": c, "high": c, "low": c, "close": c,
                  "volume": 1e6} for d, c in zip(days, px)]
    return pd.DataFrame(rows), pd.DatetimeIndex(days)


def test_a_concentrated_book_is_frozen_as_a_control_with_every_reason():
    """The liqw case: two correlated names at 60/40 with one printing in week one."""
    end = pd.Timestamp("2026-09-25")
    bars, cal = _gate_bars(["MU", "SNDK"], end, corr_pair=("MU", "SNDK"))
    g = F.freeze_gate(dict(_GOOD_ROW, dev_vs_spy=-0.06, top5_months_share_of_log_return=0.91,
                           max_dd=-0.706), {"MU": 0.603, "SNDK": 0.372, "AXTI": 0.025},
                      bars, cal, decision_date="2026-09-26",
                      earnings={"MU": {"status": "DUE"}, "SNDK": {"status": "NOT_DUE"}})
    assert g["verdict"] == "CONTROL" and g["label"].startswith("CONTROL(")
    d = g["detail"]
    assert d["effective_n"] == pytest.approx(1 / (0.603**2 + 0.372**2 + 0.025**2), abs=1e-3)
    assert d["effective_n"] < 2.1
    for reason in ("DEV_NOT_ABOVE_SPY", "TOP5_MONTH_SHARE", "MAX_DD", "NAME_WEIGHT",
                   "EFFECTIVE_N", "CORRELATED_CLUSTER", "EARNINGS", "WORST_CASE_NAME"):
        assert reason in g["reasons"], reason
    assert set(d["max_cluster"]) == {"MU", "SNDK"} and d["max_cluster_share"] > 0.9
    assert d["largest_name_to_zero_usd"] == pytest.approx(603_000)
    # every boolean is printed, grouped
    assert g["selection"]["dev_vs_spy_gt_0"] is False
    assert g["construction"]["effective_n_ge_8"] is False
    assert g["timing"]["bars_le_1_session_old"] is True        # Friday bars, Saturday decision
    assert d["bar_date"] == "2026-09-25" and d["staleness_sessions"] == 0
    assert "chained" in g["todo"]


def test_a_diversified_fresh_book_on_a_good_row_passes():
    end = pd.Timestamp("2026-09-25")
    names = [f"N{i:02d}" for i in range(20)]
    bars, cal = _gate_bars(names, end)
    g = F.freeze_gate(_GOOD_ROW, {t: 0.05 for t in names}, bars, cal,
                      decision_date="2026-09-25")
    assert g["verdict"] == "PASS" and g["label"] == "PASS", g["reasons"]
    assert g["detail"]["effective_n"] == pytest.approx(20.0)


def test_stale_bars_family_cap_and_unknown_earnings_never_pass():
    names = [f"N{i:02d}" for i in range(20)]
    bars, cal = _gate_bars(names, pd.Timestamp("2026-09-21"))      # Monday bars
    g = F.freeze_gate(_GOOD_ROW, {t: 0.05 for t in names}, bars, cal,
                      decision_date="2026-09-26", family_books_before=2)
    assert "STALE_BARS" in g["reasons"] and "FAMILY_CAP" in g["reasons"]
    assert g["detail"]["staleness_sessions"] == 4
    ten = [f"N{i:02d}" for i in range(8)]
    g2 = F.freeze_gate(_GOOD_ROW, {t: 0.125 for t in ten}, *_gate_bars(ten, "2026-09-25"),
                       decision_date="2026-09-25", earnings={})
    assert "EARNINGS_UNKNOWN" in g2["reasons"]                     # unknown is not a pass
    assert g2["construction"]["no_name_gt_10pct_printing_in_first_5_sessions"] is None
    g3 = F.freeze_gate(None, {t: 0.05 for t in names}, bars, cal, decision_date="2026-09-21")
    assert "NO_BACKTEST_ROW" in g3["reasons"]


def test_earnings_due_reads_the_8k_calendar_point_in_time(tmp_path):
    p = tmp_path / "ek.parquet"
    pd.DataFrame({"ticker": ["MU", "SNDK", "OLD"],
                  "filing_date": ["2026-06-24", "2026-08-05", "2026-09-01"],
                  "items_joined": ["2.02,9.01", "2.02", "8.01"]}).to_parquet(p)
    e = F.earnings_due(["MU", "SNDK", "OLD"], "2026-09-26", path=p)
    assert e["MU"]["status"] == "DUE" and e["SNDK"]["status"] == "NOT_DUE"
    assert e["OLD"]["status"] == "UNKNOWN"                          # no 2.02 history
    stale = F.earnings_due(["MU"], "2026-12-26", path=p)             # file 3 months old
    assert stale["MU"]["status"] == "UNKNOWN"


def test_a_gate_failure_freezes_a_control_book_not_a_headline(ledger):
    from backend.services import llm_portfolio as LP
    p = planted_panel()
    rules = _library(3)
    bars = _bars_for(p)
    gate = {"verdict": "CONTROL", "label": "CONTROL(EFFECTIVE_N)", "reasons": ["EFFECTIVE_N"]}
    picks = SL.latest_selection(p, rules[0])
    out = F.freeze_book("planted", "x", picks, today=TODAY, bars=bars, note="n",
                        log=lambda *_: None, gate=gate)
    assert out["name"] == f"lib_planted_{TODAY}__control" and out["kind"] == "control"
    rec = next(r for r in LP.read_books() if r["name"] == out["name"])
    assert rec["kind"] == "control" and rec["freeze_gate"]["label"] == "CONTROL(EFFECTIVE_N)"
    assert "planted" in F._existing_lib_ids(LP.read_books())
