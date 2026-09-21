"""J1 -- the error dataset's cluster rules, its refusal to drop a row, and its
Brier-vs-climatology arithmetic.

Every fixture is hand-built under `tmp_path`. Nothing here reads
`backend/data`: a test that asserts a cluster count off the live ledger is a
test that changes its own answer every night.
"""

from __future__ import annotations

import json

import pytest

from backend import config
from scripts import night_error_dataset as J1


# ---------------------------------------------------------------------------
# a tiny deterministic price panel
# ---------------------------------------------------------------------------


def _panel(series: dict) -> J1.Panel:
    """{'SPY': [('2026-01-02', 100.0), ...]} -> a Panel."""
    import numpy as np

    out = {}
    for sym, rows in series.items():
        dates = np.array([np.datetime64(d) for d, _ in rows])
        closes = np.array([float(c) for _, c in rows], dtype="float64")
        out[sym] = (dates, closes)
    return J1.Panel(out)


def _ramp(start_price: float, step: float, n: int = 40):
    from datetime import date, timedelta
    d0 = date(2026, 1, 2)
    return [(str(d0 + timedelta(days=i)), start_price + step * i) for i in range(n)]


@pytest.fixture()
def panel() -> J1.Panel:
    return _panel({
        "SPY": _ramp(100.0, 0.0),        # flat benchmark
        "UP": _ramp(100.0, 1.0),         # rises every day
        "DOWN": _ramp(100.0, -1.0),      # falls every day
        "FLAT": _ramp(100.0, 0.0),
    })


# ---------------------------------------------------------------------------
# the cluster rules, on hand-built rows
# ---------------------------------------------------------------------------


def _row(**kw) -> dict:
    base = {"observable": "return_sign", "expected": 0.6, "right": True,
            "excess_return": None, "decision": None, "authority": None,
            "gross_return": None, "net_return": None,
            "right_at_neighbour_horizon": None, "ungradeable_reason": None}
    base.update(kw)
    return base


def test_wrong_direction_fires_only_on_a_directional_observable():
    assert J1.cluster_of(_row(observable="return_sign", expected=0.6,
                              right=False))[0] == "WRONG_DIRECTION"
    assert J1.cluster_of(_row(observable="beats_benchmark", expected=0.6,
                              right=False))[0] == "WRONG_DIRECTION"


def test_a_threshold_miss_is_a_magnitude_miss_not_a_direction_miss():
    for obs in ("abs_move_exceeds", "drawdown_exceeds"):
        c, hits = J1.cluster_of(_row(observable=obs, expected=0.6, right=False))
        assert c == "RIGHT_DIRECTION_WRONG_MAGNITUDE"
        assert "WRONG_DIRECTION" not in hits


def test_high_confidence_wrong_outranks_plain_wrong_direction():
    c, hits = J1.cluster_of(_row(expected=0.85, right=False))
    assert c == "HIGH_CONFIDENCE_WRONG"
    assert "WRONG_DIRECTION" in hits, "the candidate list keeps every rule that fired"
    # one tick below the threshold it is a plain direction miss
    assert J1.cluster_of(_row(expected=config.J1_HIGH_CONFIDENCE_P - 0.01,
                              right=False))[0] == "WRONG_DIRECTION"


def test_low_confidence_right_is_bounded_by_the_declared_constant():
    assert J1.cluster_of(_row(expected=0.52, right=True))[0] == "LOW_CONFIDENCE_RIGHT"
    assert J1.cluster_of(_row(expected=config.J1_LOW_CONFIDENCE_P + 0.01,
                              right=True))[0] == "CORRECT_UNREMARKABLE"


def test_costs_killed_edge_needs_a_positive_gross_and_a_non_positive_net():
    assert J1.cluster_of(_row(right=True, gross_return=0.004,
                              net_return=-0.001))[0] == "COSTS_KILLED_EDGE"
    # a gross that survives the round trip is not this cluster
    assert "COSTS_KILLED_EDGE" not in J1.cluster_candidates(
        _row(right=True, gross_return=0.05, net_return=0.045))


def test_right_thesis_wrong_horizon_outranks_high_confidence_wrong():
    c, hits = J1.cluster_of(_row(expected=0.9, right=False,
                                 right_at_neighbour_horizon=True))
    assert c == "RIGHT_THESIS_WRONG_HORIZON"
    assert "HIGH_CONFIDENCE_WRONG" in hits


def test_refused_then_performed_and_explore_deserved_more():
    hi = config.J1_EXCESS_PERFORMED_PCT / 100.0
    assert J1.cluster_of(_row(decision="REFUSED", excess_return=hi,
                              right=None))[0] == "REFUSED_THEN_PERFORMED"
    assert J1.cluster_of(_row(decision="PROBE", excess_return=hi + 0.10,
                              right=None))[0] == "REFUSED_THEN_PERFORMED"
    assert J1.cluster_of(_row(decision="BUY", authority="EXPLORE",
                              excess_return=hi, right=None))[0] == "EXPLORE_DESERVED_MORE"
    # just below the bar, neither fires
    assert J1.cluster_of(_row(decision="REFUSED", excess_return=hi - 1e-6,
                              right=None))[0] == "CORRECT_UNREMARKABLE"


def test_ungradeable_wins_over_everything_and_keeps_its_reason():
    c, hits = J1.cluster_of(_row(expected=0.9, right=False,
                                 ungradeable_reason="VOID: bad threshold"))
    assert c == "UNGRADEABLE" and hits == ["UNGRADEABLE"]


def test_precedence_covers_every_declared_cluster():
    assert set(J1.CLUSTER_PRECEDENCE) == set(J1.CLUSTERS)
    assert set(J1.CURRICULUM_EXPERIMENT) == set(J1.CLUSTERS), \
        "every cluster owes the experiment it justifies"


def test_the_cost_constant_is_the_search_s_own_cost_constant():
    from scripts.night_g3_evolve_v2 import COST_BPS
    assert float(config.J1_COST_BPS_PER_SIDE) == float(COST_BPS), (
        "a COSTS_KILLED_EDGE label computed at a different rate than the search "
        "uses is a label about the constant, not about the trade")


# ---------------------------------------------------------------------------
# nothing is silently dropped
# ---------------------------------------------------------------------------


def _pred(**kw) -> dict:
    base = {"prediction_id": "x1", "ticker": "UP", "specialist": "test",
            "observable": "return_sign", "horizon_days": 5, "probability": 0.6,
            "made_at": "2026-01-02T00:00:00+00:00", "resolves_after": "2026-01-09",
            "resolved_at": "2026-01-10", "outcome": 1, "brier": 0.16,
            "resolution_detail": {"realised_return": 0.05}}
    base.update(kw)
    return base


def test_an_ungraded_record_is_kept_and_says_why(panel):
    r = J1.prediction_row(_pred(resolved_at=None, outcome=None), panel)
    assert r["cluster"] == "UNGRADEABLE"
    assert r["ungradeable_reason"].startswith("NOT_GRADED:")
    assert "2026-01-09" in r["ungradeable_reason"], "the reason names the due date"


def test_a_void_record_is_kept_and_named(panel):
    r = J1.prediction_row(_pred(void_reason="malformed threshold"), panel)
    assert r["cluster"] == "UNGRADEABLE"
    assert r["ungradeable_reason"].startswith("VOID:")


def test_every_row_carries_a_cluster(panel, tmp_path):
    recs = [_pred(prediction_id="a"), _pred(prediction_id="b", outcome=0, ticker="DOWN"),
            _pred(prediction_id="c", resolved_at=None, outcome=None),
            _pred(prediction_id="d", ticker="NOT_IN_PANEL")]
    rows = [J1.prediction_row(r, panel) for r in recs]
    assert len(rows) == len(recs), "no row leaves the dataset"
    assert all(r["cluster"] in J1.CLUSTERS for r in rows)


def test_a_ticker_absent_from_the_panel_is_still_graded_and_says_so(panel):
    r = J1.prediction_row(_pred(ticker="NOT_IN_PANEL"), panel)
    assert r["ungradeable_reason"] is None, "the LEDGER graded it; the panel did not"
    assert r["excess_return"] is None
    assert "CANNOT DETERMINE" in r["benchmark_note"]


def test_the_benchmark_leg_is_measured_against_spy(panel):
    r = J1.prediction_row(_pred(), panel)
    assert r["benchmark_return"] == pytest.approx(0.0), "SPY is flat in the fixture"
    assert r["excess_return"] == pytest.approx(r["actual_return"])
    assert r["gross_return"] is not None and r["net_return"] < r["gross_return"]


def test_neighbour_horizons_come_from_the_declared_grid():
    assert J1.neighbours(20) == (5, 60)
    assert J1.neighbours(1) == (2,)
    assert J1.neighbours(252) == (120,)
    assert J1.neighbours(7) == (5, 20), "off-grid horizons take their bracket"


# ---------------------------------------------------------------------------
# the Brier arithmetic
# ---------------------------------------------------------------------------


def test_brier_vs_climatology_arithmetic_by_hand():
    rows = [
        {"observable": "return_sign", "brier": 0.04, "actual_outcome": 1},   # p=0.8
        {"observable": "return_sign", "brier": 0.36, "actual_outcome": 0},   # p=0.6
        {"observable": "return_sign", "brier": 0.25, "actual_outcome": 1},   # p=0.5
        {"observable": "return_sign", "brier": 0.25, "actual_outcome": 0},   # p=0.5
    ]
    b = J1.brier_vs_climatology(rows)["overall"]
    assert b["n"] == 4
    assert b["brier"] == pytest.approx((0.04 + 0.36 + 0.25 + 0.25) / 4)
    assert b["climatology_p"] == pytest.approx(0.5)
    assert b["brier_climatology"] == pytest.approx(0.25)
    assert b["skill"] == pytest.approx(1.0 - b["brier"] / 0.25)


def test_a_worse_than_climatology_ledger_reports_negative_skill():
    rows = [{"observable": "return_sign", "brier": 0.81, "actual_outcome": 1},
            {"observable": "return_sign", "brier": 0.81, "actual_outcome": 0}]
    assert J1.brier_vs_climatology(rows)["overall"]["skill"] < 0


def test_ungradeable_rows_never_enter_the_brier():
    rows = [{"observable": "return_sign", "brier": 0.04, "actual_outcome": 1},
            {"observable": "return_sign", "brier": None, "actual_outcome": None}]
    assert J1.brier_vs_climatology(rows)["overall"]["n"] == 1


# ---------------------------------------------------------------------------
# the curriculum
# ---------------------------------------------------------------------------


def test_curriculum_ranks_by_count_times_mean_abs_error_and_drops_the_residual():
    rows = ([{"cluster": "WRONG_DIRECTION", "abs_error": 0.6}] * 10
            + [{"cluster": "HIGH_CONFIDENCE_WRONG", "abs_error": 0.9}] * 3
            + [{"cluster": "CORRECT_UNREMARKABLE", "abs_error": 0.4}] * 100)
    curr = J1.curriculum(rows)
    assert [c["cluster"] for c in curr] == ["WRONG_DIRECTION", "HIGH_CONFIDENCE_WRONG"]
    assert curr[0]["priority"] == pytest.approx(6.0)
    assert all(c["experiment"] for c in curr)


# ---------------------------------------------------------------------------
# end to end on a tmp ledger
# ---------------------------------------------------------------------------


def test_build_reads_decision_day_files_not_the_state_log(tmp_path, panel):
    dec = tmp_path / "decisions"
    dec.mkdir()
    (dec / "ledger.jsonl").write_text(
        json.dumps({"state": "DECIDED", "decision_id": "z"}) + "\n", encoding="utf-8")
    (dec / "2026-01-02.json").write_text(json.dumps({
        "date": "2026-01-02",
        "rows": [{"decision_id": "d1", "ticker": "UP", "direction": "PROBE",
                  "authority": "PROBE", "signal": "s",
                  "horizon": {"sessions": 5},
                  "information_cutoff_utc": "2026-01-02T00:00:00+00:00"}],
    }), encoding="utf-8")
    preds = tmp_path / "predictions.jsonl"
    preds.write_text(json.dumps(_pred()) + "\n", encoding="utf-8")

    rows, meta = J1.build(predictions=preds, decisions_dir=dec, panel=panel,
                          today="2026-01-20")
    assert meta == {"n_prediction_records": 1, "n_decision_rows": 1}
    d = [r for r in rows if r["source"] == "decision"][0]
    # UP rises 1/day on a flat SPY, so 5 sessions is a >+5% excess on a PROBE
    assert d["excess_return"] > 0.05
    assert d["cluster"] == "REFUSED_THEN_PERFORMED"
    assert J1.ledger_states(dec) == {"DECIDED": 1}


def test_a_decision_whose_window_has_not_closed_is_ungradeable_by_name(tmp_path, panel):
    r = J1.decision_row({"decision_id": "d2", "ticker": "UP", "direction": "BUY",
                         "horizon": {"sessions": 5000}, "asof": "2026-01-02"},
                        panel, today="2026-01-02")
    assert r["cluster"] == "UNGRADEABLE"
    assert r["ungradeable_reason"].startswith("WINDOW_NOT_CLOSED:")
    assert "5001-bar" in r["ungradeable_reason"]


def test_a_decision_with_no_horizon_is_named_rather_than_guessed(panel):
    r = J1.decision_row({"decision_id": "d3", "ticker": "UP", "direction": "BUY",
                         "asof": "2026-01-02"}, panel, today="2026-01-02")
    assert r["ungradeable_reason"].startswith("NO_HORIZON:")


def test_a_months_horizon_is_converted_to_sessions(panel):
    r = J1.decision_row({"decision_id": "d4", "ticker": "UP", "direction": "BUY",
                         "horizon": {"months": 1}, "asof": "2026-01-02"},
                        panel, today="2026-01-02")
    assert r["horizon_days"] == 21


def test_a_corrupt_day_file_does_not_take_the_run_down(tmp_path):
    dec = tmp_path / "decisions"
    dec.mkdir()
    (dec / "bad.json").write_text("{not json", encoding="utf-8")
    (dec / "2026-01-02.json").write_text(
        json.dumps({"date": "2026-01-02", "rows": []}), encoding="utf-8")
    assert J1.decision_rows_on_disk(dec) == []


def test_main_writes_a_receipt_and_rows_and_declares_zero_spend(tmp_path, panel,
                                                                monkeypatch):
    d = tmp_path / "optimus"
    (d / "decisions").mkdir(parents=True)
    (d / "predictions.jsonl").write_text(
        "\n".join(json.dumps(_pred(prediction_id=f"p{i}")) for i in range(5)),
        encoding="utf-8")
    (d / "decisions" / "2026-01-02.json").write_text(json.dumps({
        "date": "2026-01-02", "rows": []}), encoding="utf-8")
    monkeypatch.setattr(J1, "data_dir", lambda: d)
    monkeypatch.setattr(J1.Panel, "local", classmethod(lambda cls: panel))

    out = tmp_path / "J1.json"
    assert J1.main(["--out", str(out), "--date", "2026-01-20"]) == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["job"] == "J1_error_dataset"
    assert payload["licence"] == "PRODUCT_EXPERIMENT"
    assert payload["llm_spend_usd"] == 0.0
    assert payload["stage"] == "pnl"
    assert payload["status"] == "done"
    assert payload["headline"] and payload["verdict"]
    assert payload["n_rows"] == 5
    rows = [json.loads(ln) for ln in
            (tmp_path / "J1_error_dataset_rows.jsonl").read_text(
                encoding="utf-8").splitlines()]
    assert len(rows) == 5
    assert sum(payload["counts_by_cluster"].values()) == 5


def test_main_refuses_an_empty_ledger_rather_than_reporting_zero_errors(
        tmp_path, panel, monkeypatch):
    d = tmp_path / "optimus"
    (d / "decisions").mkdir(parents=True)
    (d / "predictions.jsonl").write_text("", encoding="utf-8")
    monkeypatch.setattr(J1, "data_dir", lambda: d)
    monkeypatch.setattr(J1.Panel, "local", classmethod(lambda cls: panel))
    out = tmp_path / "J1.json"
    assert J1.main(["--out", str(out), "--date", "2026-01-20"]) == 2
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "REFUSED"
    assert "REFUSED" in payload["verdict"]


def test_the_job_is_registered_with_its_stage():
    from scripts import night_factory_jobs as NF
    assert "J1_error_dataset" in NF.JOBS
    assert NF.JOB_STAGES["J1_error_dataset"] == "pnl"


def test_the_module_calls_no_model():
    src = (J1.__file__)
    text = open(src, encoding="utf-8").read()
    for banned in ("llm_analyzer", "deepseek", "requests.post", "httpx"):
        assert banned not in text.replace("There is no call site", ""), \
            f"J1 must charge nothing: found {banned}"
