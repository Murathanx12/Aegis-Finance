"""J3 -- the morning report's five rule-answered questions, and its refusal to
invent a number.

The night folder is built under `tmp_path` from three synthetic receipts.
Nothing here reads `backend/data`: a test that asserts "Q1 is NO" off the live
folder passes until the night it matters.
"""

from __future__ import annotations

import json

import pytest

from scripts import night_morning_report as J3


@pytest.fixture()
def night(tmp_path):
    """A folder with three receipts: one improvement, one belief, one refusal."""
    f = tmp_path / "night_factory_2026-09-22"
    f.mkdir()
    (f / "E1_event_head_run01.json").write_text(json.dumps({
        "job": "E1_event_head", "status": "done",
        "headline": "the typed-event head on 276 date blocks",
        "verdict": ("the challenger beats the champion out of sample.\n"
                    "MODEL_IMPROVED: test IC 0.0031 -> 0.0074 on 276 date blocks"),
    }), encoding="utf-8")
    (f / "E5_stopping_rules_run01.json").write_text(json.dumps({
        "job": "E5_stopping_rules", "status": "done",
        "headline": "251 lineages deflated",
        "verdict": "rejected: no lineage survives its own multiplicity budget",
        "notes": ["HYPOTHESIS_KILLED: shared-broker co-coverage is closed at "
                  "this universe and this horizon"],
    }), encoding="utf-8")
    (f / "S1_social_features_run01.json").write_text(json.dumps({
        "job": "S1_social_features", "status": "REFUSED",
        "verdict": "REFUSED: NO_SOCIAL_ROWS -- neither social key exists",
    }), encoding="utf-8")
    return f


def _run(folder, tmp_path, day="2026-09-22", **kw):
    out = tmp_path / "report.md"
    rec = tmp_path / "receipt.json"
    argv = ["--date", day, "--folder", str(folder), "--out", str(out),
            "--receipt-out", str(rec)]
    assert J3.main(argv) == 0
    return out.read_text(encoding="utf-8"), json.loads(rec.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# the five questions
# ---------------------------------------------------------------------------


def test_q1_is_yes_only_with_a_measured_before_after(night, tmp_path, monkeypatch):
    monkeypatch.setattr(J3, "data_dir", lambda: tmp_path / "nowhere")
    md, rec = _run(night, tmp_path)
    q = rec["five_questions"]
    assert q["Q1_better_than_last_night"] == "YES"
    assert len(q["Q2_improvement_lines"]) == 1
    assert q["Q2_improvement_lines"][0]["line"].startswith("MODEL_IMPROVED:")
    assert "0.0031 -> 0.0074" in q["Q2_improvement_lines"][0]["line"]
    assert "Q1 — Is AEGIS objectively better than last night? YES" in md


def test_q1_is_no_when_no_receipt_carries_the_line(tmp_path, monkeypatch):
    f = tmp_path / "night_factory_2026-09-22"
    f.mkdir()
    (f / "X_run01.json").write_text(json.dumps({
        "job": "X", "status": "done", "verdict": "thirty engineering changes shipped",
    }), encoding="utf-8")
    monkeypatch.setattr(J3, "data_dir", lambda: tmp_path / "nowhere")
    md, rec = _run(f, tmp_path)
    q = rec["five_questions"]
    assert q["Q1_better_than_last_night"] == "NO"
    assert "nothing measurable moved" in q["Q1_why"]
    assert "**Q2 — What measurably improved?**" in md
    assert "- none" in md


def test_a_prefixed_line_without_numbers_does_not_earn_a_yes(tmp_path, monkeypatch):
    f = tmp_path / "night_factory_2026-09-22"
    f.mkdir()
    (f / "Y_run01.json").write_text(json.dumps({
        "job": "Y", "status": "done",
        "verdict": "MODEL_IMPROVED: it feels better this morning",
    }), encoding="utf-8")
    monkeypatch.setattr(J3, "data_dir", lambda: tmp_path / "nowhere")
    _md, rec = _run(f, tmp_path)
    q = rec["five_questions"]
    assert q["Q1_better_than_last_night"] == "NO"
    assert len(q["Q2_prefixed_lines_without_a_measured_before_after"]) == 1
    assert "do not count" in q["Q1_why"]


def test_q3_collects_every_belief_line_at_any_depth(night, tmp_path, monkeypatch):
    monkeypatch.setattr(J3, "data_dir", lambda: tmp_path / "nowhere")
    _md, rec = _run(night, tmp_path)
    lines = rec["five_questions"]["Q3_belief_lines"]
    assert len(lines) == 1
    assert lines[0]["line"].startswith("HYPOTHESIS_KILLED:")
    assert lines[0]["at"].startswith("notes[")


def test_q4_names_the_first_grade_dates_and_weak_cells(night, tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "decisions").mkdir(parents=True)
    (data / "decisions" / "2026-09-22.json").write_text(json.dumps({
        "date": "2026-09-22",
        "count_by_direction": {"BUY": 1, "PROBE": 1},
        "roi_ranking": {"rule": "roi", "calibration_seen": {
            "CVLG": {"signal": "profitability_small", "calibration_verdict": "WEAK",
                     "spread_t": 1.59, "holm_p": 1.0, "decile_mean_pct": 0.357}}},
        "rows": [
            {"ticker": "AAPL", "direction": "PROBE", "authority": "PROBE",
             "expiry_utc": "2026-09-29T00:00:00+00:00"},
            {"ticker": "CVLG", "direction": "BUY", "authority": "EXPLORE",
             "expiry_utc": "2027-03-22T00:00:00+00:00"},
        ],
    }), encoding="utf-8")
    monkeypatch.setattr(J3, "data_dir", lambda: data)
    md, rec = _run(night, tmp_path)
    q = rec["five_questions"]
    assert any("AAPL" in s and "2026-09-29" in s for s in q["Q4_first_grade_dates_owed"])
    assert any("CVLG" in s and "2027-03-22" in s for s in q["Q4_first_grade_dates_owed"])
    assert q["Q4_weak_calibration_cells"] and "WEAK" in q["Q4_weak_calibration_cells"][0]
    assert "CVLG (profitability_small)" in md


def test_q5_is_j1s_top_curriculum_item(night, tmp_path, monkeypatch):
    (night / "J1_error_dataset_run01.json").write_text(json.dumps({
        "job": "J1_error_dataset", "status": "done",
        "headline": "25,039 error rows",
        "largest_errors": [{"ticker": "NVDA", "date": "2026-08-11",
                            "mechanism": "skeptic", "expected": 0.9,
                            "actual": 0, "cluster": "HIGH_CONFIDENCE_WRONG"}],
        "curriculum": [{"cluster": "WRONG_DIRECTION", "count": 2200,
                        "priority": 1302.47, "experiment": "split the sign misses"}],
    }), encoding="utf-8")
    monkeypatch.setattr(J3, "data_dir", lambda: tmp_path / "nowhere")
    md, rec = _run(night, tmp_path)
    assert "WRONG_DIRECTION" in rec["five_questions"]["Q5_top_curriculum_item"]
    assert "split the sign misses" in md
    assert "NVDA 2026-08-11 skeptic" in md


def test_q5_says_cannot_determine_with_the_path_when_j1_did_not_run(night, tmp_path,
                                                                    monkeypatch):
    monkeypatch.setattr(J3, "data_dir", lambda: tmp_path / "nowhere")
    md, rec = _run(night, tmp_path)
    q5 = rec["five_questions"]["Q5_top_curriculum_item"]
    assert q5.startswith("CANNOT DETERMINE")
    assert "J1_error_dataset" in q5
    assert "CANNOT DETERMINE" in md


# ---------------------------------------------------------------------------
# never invent a number
# ---------------------------------------------------------------------------


def test_a_missing_input_prints_cannot_determine_with_the_file(night, tmp_path,
                                                               monkeypatch):
    monkeypatch.setattr(J3, "data_dir", lambda: tmp_path / "nowhere")
    md, _rec = _run(night, tmp_path)
    for section in ("## 1. Paper NAV vs SPY", "## 6. Missed opportunities",
                    "## 7. Drift"):
        assert section in md
    assert "looked for" in md, "a missing input names the path it looked for"
    assert md.count("CANNOT DETERMINE") >= 4


def test_the_nav_block_passes_the_scoreboard_sentence_through_verbatim(
        night, tmp_path, monkeypatch):
    sentence = ("CANNOT DETERMINE: no NAV series exists on this machine -- "
                "`paper_nav` is empty here")
    (night / "daily_pass_2026-09-22.json").write_text(json.dumps({
        "receipt": "daily_pass",
        "scoreboard": {"nav_vs_spy": sentence, "exploit_pnl": "CANNOT DETERMINE: none",
                       "explore_pnl": "CANNOT DETERMINE: none"},
    }), encoding="utf-8")
    monkeypatch.setattr(J3, "data_dir", lambda: tmp_path / "nowhere")
    md, _rec = _run(night, tmp_path)
    assert sentence in md, "the scoreboard's own sentence is not re-derived here"


def test_the_missed_opportunity_block_reads_j2_defensively(night, tmp_path,
                                                           monkeypatch):
    (night / "J2_missed_opportunity_run01.json").write_text(json.dumps({
        "job": "J2_missed_opportunity", "status": "done",
        "headline": "11 names cleared the bar and were not bought",
        "paired": {"n": 11, "controls": 11},
        "top_missed": [{"ticker": "MU", "excess": 0.19}],
    }), encoding="utf-8")
    monkeypatch.setattr(J3, "data_dir", lambda: tmp_path / "nowhere")
    md, _rec = _run(night, tmp_path)
    assert "11 names cleared the bar" in md
    assert "MU" in md


def test_a_j2_receipt_missing_its_keys_does_not_crash(night, tmp_path, monkeypatch):
    (night / "J2_missed_opportunity_run01.json").write_text(
        json.dumps({"job": "J2_missed_opportunity"}), encoding="utf-8")
    monkeypatch.setattr(J3, "data_dir", lambda: tmp_path / "nowhere")
    md, _rec = _run(night, tmp_path)
    assert "## 6. Missed opportunities" in md


def test_a_receipt_with_no_status_is_reported_not_counted_as_finished(night, tmp_path,
                                                                      monkeypatch):
    (night / "silent_run01.json").write_text(json.dumps({"job": "silent"}),
                                             encoding="utf-8")
    monkeypatch.setattr(J3, "data_dir", lambda: tmp_path / "nowhere")
    md, _rec = _run(night, tmp_path)
    assert "declared NO status at all" in md
    assert "silent_run01" in md


def test_the_refused_job_is_named_in_the_did_not_finish_block(night, tmp_path,
                                                              monkeypatch):
    monkeypatch.setattr(J3, "data_dir", lambda: tmp_path / "nowhere")
    md, _rec = _run(night, tmp_path)
    assert "S1_social_features_run01: REFUSED" in md


def test_the_stop_block_reads_night_stopped_when_present(night, tmp_path, monkeypatch):
    (night / "NIGHT_STOPPED.json").write_text(
        json.dumps({"stopped_utc": "2026-09-22T07:29:00+00:00", "by": "time_box"}),
        encoding="utf-8")
    monkeypatch.setattr(J3, "data_dir", lambda: tmp_path / "nowhere")
    md, _rec = _run(night, tmp_path)
    assert "STOP CONFIRMED" in md and "time_box" in md


def test_the_cap_trims_the_body_and_never_the_five_questions(night, tmp_path,
                                                             monkeypatch):
    data = tmp_path / "data"
    (data / "decisions").mkdir(parents=True)
    (data / "decisions" / "2026-09-22.json").write_text(json.dumps({
        "date": "2026-09-22",
        "rows": [{"ticker": f"T{i}", "direction": "PROBE", "authority": "PROBE",
                  "expiry_utc": "2026-09-29T00:00:00+00:00"} for i in range(40)],
    }), encoding="utf-8")
    for i in range(80):
        (night / f"filler{i}_run01.json").write_text(json.dumps({
            "job": f"filler{i}", "status": "REFUSED",
            "verdict": "REFUSED: " + "x" * 50}), encoding="utf-8")
    monkeypatch.setattr(J3, "data_dir", lambda: data)
    # Every block bounds its own length, so the real report does not reach 120
    # lines even on an 83-receipt night. The cap is still a live code path, and
    # a cap nothing can exercise is a cap nobody knows is broken: squeeze it.
    monkeypatch.setattr(J3, "MAX_LINES", 45)
    md, rec = _run(night, tmp_path)
    assert rec["report_lines"] <= J3.MAX_LINES
    assert "truncated" in md
    # the questions survive the trim -- that is the whole point of the rule
    assert "## THE FIVE QUESTIONS" in md
    assert "Q5 — What should tonight test?" in md


def test_an_empty_night_folder_still_produces_a_report(tmp_path, monkeypatch):
    f = tmp_path / "night_factory_2026-09-22"
    f.mkdir()
    monkeypatch.setattr(J3, "data_dir", lambda: tmp_path / "nowhere")
    md, rec = _run(f, tmp_path)
    assert rec["n_receipts_read"] == 0
    assert rec["five_questions"]["Q1_better_than_last_night"] == "NO"
    assert "MORNING REPORT 2026-09-22" in md


# ---------------------------------------------------------------------------
# the receipt and the registry
# ---------------------------------------------------------------------------


def test_the_receipt_declares_the_contract(night, tmp_path, monkeypatch):
    monkeypatch.setattr(J3, "data_dir", lambda: tmp_path / "nowhere")
    _md, rec = _run(night, tmp_path)
    assert rec["job"] == "J3_morning_report"
    assert rec["licence"] == "PRODUCT_EXPERIMENT"
    assert rec["llm_spend_usd"] == 0.0
    assert rec["stage"] == "pnl"
    assert rec["status"] == "done"
    assert rec["headline"] and rec["verdict"]


def test_has_before_after_needs_an_arrow_and_two_numbers():
    assert J3.has_before_after("MODEL_IMPROVED: IC 0.003 -> 0.007")
    assert J3.has_before_after("WEIGHT_CHANGED: 0.10 to 0.25 of equity")
    assert not J3.has_before_after("MODEL_IMPROVED: much better")
    assert not J3.has_before_after("MODEL_IMPROVED: IC rose to 0.007")


def test_the_job_is_registered_with_its_stage():
    from scripts import night_factory_jobs as NF
    assert "J3_morning_report" in NF.JOBS
    assert NF.JOB_STAGES["J3_morning_report"] == "pnl"


def test_the_module_calls_no_model():
    text = open(J3.__file__, encoding="utf-8").read()
    for banned in ("llm_analyzer", "deepseek_client", "requests.post", "httpx"):
        assert banned not in text, f"J3 must charge nothing: found {banned}"
