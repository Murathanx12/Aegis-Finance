"""Chunk I: the daily learning report answers from receipts, or says it cannot.

Post-review (2026-09-26 H+I): the sentences read skill at (arm, observable,
horizon); an LLM magnitude cell must beat the free sigma_63 prior; a weight-0
arm is never named; the experiment list derives P from measured spreads and
refuses what already runs; compute verdicts read the cell, not the family.

Every date is derived from `today` (protocol 5): nothing here encodes a
calendar moment that could pass.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts import daily_learning_report as DLR


def _w(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj), encoding="utf-8")


def _jl(p: Path, rows: list[dict]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


@pytest.fixture()
def day() -> str:
    return date.today().isoformat()


def _vol_world(base: Path, day: str, *, llm: str = "flat", n_days: int = 8,
               n_names: int = 20, seed: int = 3) -> list[dict]:
    """Bars for names of very different vol, and graded `abs_move_exceeds` h=1
    rows by the live arm `investigator:X` on the `n_days` sessions before `day`.
    llm="flat": the LLM says 0.3 everywhere (the prior must win);
    llm="oracle": the LLM nearly knows the outcome (the LLM must win)."""
    from scipy.stats import norm
    rng = np.random.default_rng(seed)
    end = pd.Timestamp(day) - pd.Timedelta(days=1)
    days = pd.bdate_range(end=end, periods=150 + n_days)
    vols = {f"V{i}": 0.004 + 0.003 * i for i in range(n_names)}
    bars = []
    for t, s in vols.items():
        px = 100 * np.exp(np.cumsum(rng.normal(0, s, len(days))))
        bars += [{"symbol": t, "date": d, "close": float(c)} for d, c in zip(days, px)]
    p = base / DLR.BARS_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(bars).to_parquet(p)
    rows = []
    for k, d in enumerate(days[150:]):
        for t, s in vols.items():
            y = int(rng.random() < 2 * (1 - norm.cdf(0.02 / s)))
            pr = 0.3 if llm == "flat" else (0.95 if y else 0.05)
            rows.append({"prediction_id": f"m_{k}_{t}", "specialist": "investigator:X",
                         "ticker": t, "observable": "abs_move_exceeds", "horizon_days": 1,
                         "threshold": 0.02, "probability": pr, "prior": pr,
                         "made_at": f"{d.date()}T11:00:00+00:00",
                         "resolves_after": str(d.date()), "resolved_at": str(d.date()),
                         "outcome": y, "brier": (pr - y) ** 2})
    return rows


def _direction_rows(day: str, n: int = 120, seed: int = 5) -> list[dict]:
    """Graded `return_sign` h=5 rows by the live arm that are ANTI-signal."""
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n):
        y = int(rng.random() < 0.5)
        pr = 0.35 if y else 0.65
        d = (date.fromisoformat(day) - timedelta(days=30 - i // 10)).isoformat()
        out.append({"prediction_id": f"d_{i}", "specialist": "investigator:X", "ticker": "AAA",
                    "observable": "return_sign", "horizon_days": 5, "probability": pr,
                    "made_at": f"{d}T11:00:00+00:00", "resolves_after": d, "resolved_at": d,
                    "outcome": y, "brier": (pr - y) ** 2})
    return out


def _synthetic_day(base: Path, day: str, *, llm: str = "flat") -> None:
    prev = (date.fromisoformat(day) - timedelta(days=1)).isoformat()
    early = (date.fromisoformat(day) - timedelta(days=10)).isoformat()
    _jl(base / "predictions.jsonl", [
        {"prediction_id": "p_resolved", "specialist": "investigator:evidence_v3", "ticker": "AAA",
         "observable": "return_sign", "horizon_days": 1, "probability": 0.6,
         "made_at": f"{prev}T00:00:00+00:00", "resolves_after": day,
         "resolved_at": day, "outcome": 1, "brier": 0.16},
        {"prediction_id": "p_open", "specialist": "investigator:evidence_v3", "ticker": "BBB",
         "observable": "return_sign", "horizon_days": 5, "probability": 0.5,
         "made_at": f"{day}T00:00:00+00:00", "resolves_after": "2999-01-01",
         "resolved_at": None, "outcome": None, "brier": None},
        {"prediction_id": "p_late", "specialist": "investigator:evidence_v3", "ticker": "CCC",
         "observable": "beats_benchmark", "horizon_days": 1, "probability": 0.52,
         "made_at": f"{early}T00:00:00+00:00", "resolves_after": prev,
         "resolved_at": None, "outcome": None, "brier": None},
        {"prediction_id": "p_dir_new", "specialist": "investigator:evidence_v3", "ticker": "DDD",
         "observable": "beats_benchmark", "horizon_days": 5, "probability": 0.51,
         "made_at": f"{day}T01:00:00+00:00", "resolves_after": "2999-01-01",
         "resolved_at": None, "outcome": None, "brier": None},
    ] + _vol_world(base, day, llm=llm) + _direction_rows(day))
    _w(base / f"night_factory_{day}" / f"grade_forecasts_{day}.json",
       {"date": day, "written_utc": f"{day}T02:00:00+00:00", "newly_resolved": 1,
        "graded_after_this_run": 1, "n_records": 2, "totals": {"not_yet_due": 1}})
    _w(base / "reputation" / f"reputation_{day}.json", {
        "arms": [
            {"arm": "investigator:X", "family": "investigator", "n": 200, "skill": 0.06, "weight": 0.6},
            {"arm": "investigator:evidence_v3", "family": "investigator", "n": 100, "skill": 0.02,
             "weight": 0.4},
            {"arm": "biotech_pharma", "family": "biotech_pharma", "n": 80, "skill": -0.70,
             "weight": 0.0}],
        "arms_by_observable": [
            {"arm": "investigator:X", "observable": "abs_move_exceeds", "horizon_days": 1.0,
             "n": 80, "skill": 0.05},
            {"arm": "investigator:X", "observable": "return_sign", "horizon_days": 5.0,
             "n": 60, "skill": -0.09},
            {"arm": "investigator:evidence_v3", "observable": "return_sign", "horizon_days": 1.0,
             "n": 100, "skill": 0.04},
            {"arm": "biotech_pharma", "observable": "abs_move_exceeds", "horizon_days": 20.0,
             "n": 82, "skill": -0.70}]})
    _w(base / "llm_portfolio" / f"leaderboard_{day}.json", {"bars_through": prev, "books": [
        {"name": "winner_book", "twin": None, "benchmark": "SPY", "sessions": 3,
         "vs_benchmark": 0.02, "net_to_date": 0.03},
        {"name": "winner_book__spy", "twin": "spy", "benchmark": "SPY", "sessions": 3,
         "vs_benchmark": 0.0}]})
    _w(base / "paper_accounts" / f"roi_{day}.json", {
        "aggregate": {"n_ahead_of_spy": 1, "n_behind_spy": 3, "all_priced": {"n": 4, "roi_pct": -1.0}},
        "rows": [{"account": "PC-PAPER", "family": "pc_paper", "status": "LIVE",
                  "start_capital": 1_000_000.0, "equity": 999_000.0, "vs_spy_pp": 0.1,
                  "inception": early, "last_mark": prev}]})
    _jl(base / "llm_portfolio" / "books.jsonl", [
        {"name": f"lib_mom_{early}", "model": "rule:strategy_library:mom", "asof": early,
         "positions": [{"ticker": "AAA", "weight": 0.5}, {"ticker": "CCC", "weight": 0.5}]}])
    _w(base / "forecasts" / f"day_{day}.json",
       {"direction_rows": "none: direction skill unmeasured", "spent_usd": 0.1})
    _w(base / "forensics" / f"fast_movers_{day}.json", {"cases": [
        {"ticker": "AAA", "book": "lib", "S": prev, "direction": 1, "move": 0.08,
         "class": "PREDICTED_MECHANISM", "predicted": True, "credit": "credited",
         "ex_post_catalyst": {"titles": ["AAA wins contract"]},
         "candidate_feature": {"name": "news_contract_count_7d", "observable_pre_entry": True}}]})
    _jl(base / f"llm_calls_{day[:7]}.jsonl", [
        {"call_id": "c1", "ts": f"{day}T01:00:00+00:00", "provider": "deepseek",
         "purpose": "u_forecast", "cost_usd": 0.1, "row_type": "call", "prediction_ids": []},
        {"call_id": "c1", "ts": f"{day}T01:00:01+00:00", "provider": "", "purpose": "",
         "cost_usd": None, "row_type": "amendment", "prediction_ids": ["p_resolved"]},
        {"call_id": "c2", "ts": f"{day}T03:00:00+00:00", "provider": "deepseek",
         "purpose": "idle_research", "cost_usd": 0.5, "row_type": "call", "prediction_ids": []},
        {"call_id": "c3", "ts": f"{day}T04:00:00+00:00", "provider": "deepseek",
         "purpose": "smoke", "cost_usd": 0.0, "row_type": "call", "prediction_ids": []},
        {"call_id": "c4", "ts": f"{day}T05:00:00+00:00", "provider": "deepseek",
         "purpose": "late_graded", "cost_usd": 0.2, "row_type": "call",
         "prediction_ids": ["p_late"]},
        {"call_id": "c5", "ts": f"{day}T06:00:00+00:00", "provider": "deepseek",
         "purpose": "direction_writer", "cost_usd": 0.3, "row_type": "call",
         "prediction_ids": ["d_0", "d_1", "d_2"]},
    ])


def test_synthetic_day_answers_every_question_from_receipts(tmp_path, day):
    base = tmp_path / "optimus"
    _synthetic_day(base, day)
    rep = DLR.build(day, base=base, repo=tmp_path, db_path=None, code_audit=False)
    S = rep["sections"]

    assert S["resolved"]["n_resolved_today"] == 1
    assert any("n=1" in ln for ln in S["resolved"]["lines"])
    assert any("1 beat their benchmark" in ln for ln in S["books_vs_spy"]["lines"])
    assert any("winner_book" in ln for ln in S["books_vs_spy"]["lines"])

    # chunk A join: the library book held AAA before its entry
    assert any(f"lib_mom_" in ln and "AAA" in ln for ln in S["capture"]["lines"])
    assert S["capture"]["n_captured"] == 1
    assert S["features"]["n_surviving"] == 1
    assert any("PREDICTED_MECHANISM 1 of 1" in ln for ln in S["mechanism"]["lines"])

    # every number carries a path (a `no data today` line has no number to source)
    for ln in S["resolved"]["lines"] + S["books_vs_spy"]["lines"] + S["compute"]["lines"]:
        if DLR.NO_DATA not in ln:
            assert "(`" in ln, ln
    assert "winner_book" in rep["closing"]["works"] and "n=3 sessions" in rep["closing"]["works"]


def test_compute_reads_the_cell_not_the_family(tmp_path, day):
    base = tmp_path / "optimus"
    _synthetic_day(base, day)
    dec = DLR.build(day, base=base, repo=tmp_path, db_path=None,
                    code_audit=False)["sections"]["compute"]["decisions"]
    assert dec["u_forecast"]["verdict"] == "MORE"          # its cell: return_sign h=1 +4%
    assert "return_sign h=1" in dec["u_forecast"]["why"]
    # the arm's MAGNITUDE cell is positive, but this purpose writes DIRECTION rows
    assert dec["direction_writer"]["verdict"] == "LESS"
    assert "return_sign h=5" in dec["direction_writer"]["why"]
    assert dec["idle_research"]["verdict"] == "LESS"       # spent, no gradeable row
    assert dec["smoke"]["verdict"] == "NO_VERDICT"         # spent $0
    assert dec["late_graded"]["verdict"] == "WAITING_ON_GRADER"
    assert "grader" in dec["late_graded"]["why"]


def test_works_names_the_prior_when_the_free_formula_beats_the_llm(tmp_path, day):
    base = tmp_path / "optimus"
    _synthetic_day(base, day, llm="flat")
    c = DLR.build(day, base=base, repo=tmp_path, db_path=None, code_audit=False)["closing"]
    w = c["works"]
    assert "abs_move_exceeds h=1" in w and "sigma_63" in w
    assert "the prior works and the LLM does not add" in w
    v = c["vol_prior"]["1"]
    assert v["winner"] == "prior" and v["skill_prior"] > v["skill_llm"]
    assert f"{DLR._pct(v['skill_prior'])} vs the live LLM arms' posterior {DLR._pct(v['skill_llm'])}" in w


def test_works_names_the_llm_only_when_it_beats_the_prior(tmp_path, day):
    base = tmp_path / "optimus"
    _synthetic_day(base, day, llm="oracle")
    c = DLR.build(day, base=base, repo=tmp_path, db_path=None, code_audit=False)["closing"]
    assert c["vol_prior"]["1"]["winner"] == "llm"
    assert "the LLM beats the free prior" in c["works"]
    assert "does not add" not in c["works"]


def test_a_magnitude_cell_without_bars_is_not_called_working(tmp_path, day):
    base = tmp_path / "optimus"
    _synthetic_day(base, day)
    (base / DLR.BARS_REL).unlink()
    c = DLR.build(day, base=base, repo=tmp_path, db_path=None, code_audit=False)["closing"]
    assert "NOT ADMITTED" in c["works"] and "investigator:X" in c["works"]


def test_does_not_names_live_surfaces_never_a_weight_zero_arm(tmp_path, day):
    base = tmp_path / "optimus"
    _synthetic_day(base, day)
    d = DLR.build(day, base=base, repo=tmp_path, db_path=None, code_audit=False)["closing"]["does_not"]
    assert "biotech_pharma" not in d                       # retired at weight 0: a corpse
    assert "LLM direction" in d and "`return_sign` h=5" in d and "n=60" in d
    assert "3 of 4 behind SPY" in d and "n=4 accounts" in d


def test_experiments_are_derived_and_refuse_what_already_runs(tmp_path, day):
    base = tmp_path / "optimus"
    _synthetic_day(base, day)
    c = DLR.build(day, base=base, repo=tmp_path, db_path=None, code_audit=False)["closing"]
    ex = {e["id"]: e for e in c["experiments"]}
    assert not hasattr(DLR, "EXPERIMENTS")                 # the hand-set table is gone
    pw = ex["PROBE_WEIGHTING_3WAYS"]
    assert pw["eligible"] and pw["capital_usd"] == 1_000_000.0
    assert pw["ev_usd"] == pytest.approx(pw["p_used"] * pw["capital_usd"] * pw["delta"] * pw["years"]
                                         - pw["cost_usd"])
    assert pw["p_used"] == pytest.approx(pw["power"]["power"] * DLR.PRIOR_FACTOR["positive"])
    # direction rows are being written today -> already running -> never ranked
    dc = ex["INVESTIGATOR_DIRECTION_CALIBRATION"]
    assert not dc["eligible"] and "already running" in dc["why"]
    assert "`PROBE_WEIGHTING_3WAYS`" in c["next_experiment"]
    # once the three twins are frozen, PROBE is running too
    _jl(base / "llm_portfolio" / "books.jsonl", [
        {"name": f"probe_invvol_{day}", "model": "rule:probe", "asof": day, "positions": []}])
    c = DLR.build(day, base=base, repo=tmp_path, db_path=None, code_audit=False)["closing"]
    ex = {e["id"]: e for e in c["experiments"]}
    assert not ex["PROBE_WEIGHTING_3WAYS"]["eligible"]
    assert "PROBE_WEIGHTING_3WAYS" not in c["next_experiment"].split("--")[0]


def test_power_line_caps_skill_by_the_stated_p_spread():
    # an arm whose p sits within ~0.02-0.03 of 0.5 cannot earn more than ~0.3%
    pl = DLR.power_line(0.028, 0.5, 2000)
    assert pl["ceiling"] == pytest.approx(0.028 ** 2 / 0.25)
    assert pl["ceiling"] < 0.0035
    assert pl["t_max"] == pytest.approx(0.028 * np.sqrt(2000) / 1.0)
    assert pl["power"] < 0.3
    assert DLR.power_line(0.16, 0.15, 4000)["power"] > 0.99


def test_reachability_excludes_tests_and_reds_an_unreasoned_orphan(tmp_path, day, monkeypatch):
    from backend.services import signal_reachability as SR
    fake = {"n_modules": 10, "orphans": [
        {"module": "backend.tests.test_a", "reason": "test"},
        {"module": "backend.tests.test_b", "reason": None},
        {"module": "backend.services.kept", "reason": "AWAITS -- a consumer"},
        {"module": "backend.services.lost", "reason": None}],
        "tooling_only": [], "unclassified": ["backend.services.lost"]}
    monkeypatch.setattr(SR, "audit", lambda *a, **k: fake)
    base = tmp_path / "optimus"
    base.mkdir()
    sec = DLR.build(day, base=base, repo=tmp_path, db_path=None, code_audit=True)["sections"]["unconsumed"]
    head = next(ln for ln in sec["lines"] if "computes for nobody" in ln)
    assert "2 of 8 non-test modules" in head and "1 with no recorded reason -- RED" in head
    assert "2 test modules excluded" in head
    assert sec["orphans"] == ["backend.services.kept", "backend.services.lost"]
    assert any("`backend.services.kept`: AWAITS" in ln for ln in sec["lines"])
    assert any(ln.strip().startswith("RED `backend.services.lost`") for ln in sec["lines"])
    assert sec["status"] == "RED"


def test_a_day_with_no_receipts_says_so_everywhere(tmp_path, day):
    base = tmp_path / "optimus"
    base.mkdir()
    rep = DLR.build(day, base=base, repo=tmp_path, db_path=None, code_audit=False)
    for sid, sec in rep["sections"].items():
        assert sec["status"] == "NO_DATA", sid
        assert any(DLR.NO_DATA in ln for ln in sec["lines"]), sid
    c = rep["closing"]
    assert "nothing admissible" in c["works"] and DLR.NO_DATA in c["works"]
    assert "nothing admissible" in c["does_not"] and DLR.NO_DATA in c["does_not"]
    assert "none eligible" in c["next_experiment"] and DLR.NO_DATA in c["next_experiment"]


def test_write_report_writes_md_and_json(tmp_path, day):
    base = tmp_path / "optimus"
    _synthetic_day(base, day)
    res = DLR.write_report(day, base=base, repo=tmp_path, db_path=None, code_audit=False)
    md = Path(res["md"]).read_text(encoding="utf-8")
    js = json.loads(Path(res["json"]).read_text(encoding="utf-8"))
    assert Path(res["md"]).parent == base / "learning_reports"
    assert md.count("WHAT CURRENTLY WORKS") == 1 and "## Data nobody consumed" in md
    assert js["closing"]["works"] == res["closing"]["works"]
    assert js["llm_spend_usd"] == 0.0


def _fake_session(monkeypatch, tmp_path, *, report):
    from scripts import sim_run as R
    calls = []
    monkeypatch.setattr(R.SS, "status", lambda: {"session": {"id": "s1", "mode": "observe"}})
    monkeypatch.setattr(R.SS, "should_continue", lambda s: (False, "requested duration elapsed"))
    monkeypatch.setattr(R.SS, "finish", lambda *a, **k: calls.append("finish"))
    monkeypatch.setattr(R.SS, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(R._config, "OPTIMUS_LEDGER_DIR", tmp_path / "ledger")
    monkeypatch.setattr(R, "keep_awake", lambda on: "noop")

    def _report(day, **kw):
        calls.append(("report", day))
        return report(day)
    monkeypatch.setattr(DLR, "write_report", _report)
    return R, calls


def test_the_hook_runs_once_at_session_end_after_the_checkpoint(monkeypatch, tmp_path):
    R, calls = _fake_session(monkeypatch, tmp_path, report=lambda d: {"md": "x"})
    assert R.run("s1") == 0
    assert calls[0] == "finish"
    reports = [c for c in calls if isinstance(c, tuple)]
    assert len(reports) == 1
    assert len(reports[0][1]) == 10          # a UTC ISO day


def test_a_failing_report_never_blocks_the_exit(monkeypatch, tmp_path):
    def boom(d):
        raise RuntimeError("receipt unreadable")
    R, calls = _fake_session(monkeypatch, tmp_path, report=boom)
    assert R.run("s1") == 0
    assert calls[0] == "finish"
