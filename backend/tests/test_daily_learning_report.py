"""Chunk I: the daily learning report answers from receipts, or says it cannot.

Every date is derived from `today` (protocol 5): nothing here encodes a
calendar moment that could pass.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

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


def _synthetic_day(base: Path, day: str) -> None:
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
    ])
    _w(base / f"night_factory_{day}" / f"grade_forecasts_{day}.json",
       {"date": day, "written_utc": f"{day}T02:00:00+00:00", "newly_resolved": 1,
        "graded_after_this_run": 1, "n_records": 2, "totals": {"not_yet_due": 1}})
    _w(base / "reputation" / f"reputation_{day}.json", {"arms": [
        {"arm": "investigator:D_all", "family": "investigator", "n": 100, "skill": 0.06},
        {"arm": "biotech_pharma", "family": "biotech_pharma", "n": 80, "skill": -0.30}]})
    _w(base / "llm_portfolio" / f"leaderboard_{day}.json", {"bars_through": prev, "books": [
        {"name": "winner_book", "twin": None, "benchmark": "SPY", "sessions": 3,
         "vs_benchmark": 0.02, "net_to_date": 0.03},
        {"name": "winner_book__spy", "twin": "spy", "benchmark": "SPY", "sessions": 3,
         "vs_benchmark": 0.0}]})
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

    # compute: the purpose that spent and produced nothing graded gets LESS
    dec = S["compute"]["decisions"]
    assert dec["idle_research"]["verdict"] == "LESS"
    assert dec["u_forecast"]["verdict"] == "MORE"
    assert any(ln.startswith("LESS: `idle_research`") for ln in S["compute"]["lines"])

    # chunk A join: the library book held AAA before its entry
    assert any(f"lib_mom_" in ln and "AAA" in ln for ln in S["capture"]["lines"])
    assert S["capture"]["n_captured"] == 1
    assert S["features"]["n_surviving"] == 1
    assert any("PREDICTED_MECHANISM 1 of 1" in ln for ln in S["mechanism"]["lines"])

    # every number carries a path (a `no data today` line has no number to source)
    for ln in S["resolved"]["lines"] + S["books_vs_spy"]["lines"] + S["compute"]["lines"]:
        if DLR.NO_DATA not in ln:
            assert "(`" in ln, ln

    c = rep["closing"]
    assert "investigator:D_all" in c["works"] and "n=100" in c["works"]
    assert "winner_book" in c["works"] and "n=3 sessions" in c["works"]
    assert "biotech_pharma" in c["does_not"] and "n=80" in c["does_not"]
    assert "HIGHEST-EV NEXT EXPERIMENT: `" in c["next_experiment"]
    assert "none eligible" not in c["next_experiment"]
    # the ranking is the declared formula, not a choice
    elig = [e for e in c["experiments"] if e["eligible"]]
    best = max(elig, key=lambda e: e["ev_usd"])
    assert f"`{best['id']}`" in c["next_experiment"]
    for e in elig:
        assert e["ev_usd"] == pytest.approx(e["p_used"] * e["value_usd"] - e["cost_usd"])


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
