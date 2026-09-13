"""THE NIGHTLY NN LAB (chunk 14, loop 5) — synthetic tables, no job run.

The three things pinned here are the three ways "did tonight beat last night"
can be answered wrongly:

* **by moving the month.** The held-out month is the most recent FULLY-CLOSED
  calendar month and is FIXED for the comparison. Re-evaluating last night's
  head on a NEW month confounds "did the head improve" with "did the month get
  easier", and the answer looks like learning either way.
* **by defaulting.** With fewer than two nights of history the answer is
  `null`, not False and not True. Nothing to compare against yet is a state.
* **by comparing different heads.** The pairing is on (head, month), never on
  position in a list.

`SEQUENCE` is walked with an injected runner, so no test runs E1, E4 or E5.
Dates come from `date.today()`; the held-out month is derived, never written.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from backend import config as _config
from backend.services import lab_nn as NN


@pytest.fixture
def nn_dir(tmp_path, monkeypatch):
    (tmp_path / "optimus").mkdir(parents=True)
    monkeypatch.setattr(_config, "DATA_DIR", tmp_path)
    return tmp_path


def _daily_csv(path, month: str, rows: dict) -> str:
    """A minimal E1 daily table: one date column plus `ic_*` columns."""
    import pandas as pd
    dates = [f"{month}-{d:02d}" for d in (3, 10, 17, 24)]
    frame = {"date": dates}
    for head, ic in rows.items():
        frame[f"ic_{head}"] = [ic] * len(dates)
    pd.DataFrame(frame).to_csv(path, index=False)
    return str(path)


# --------------------------------------------------------------------------
# the fixed held-out month


def test_the_held_out_month_is_the_most_recent_fully_closed_one():
    assert NN.held_out_month(date(2026, 9, 13)) == "2026-08"
    assert NN.held_out_month(date(2026, 9, 1)) == "2026-08"
    assert NN.held_out_month(date(2026, 1, 4)) == "2025-12", "the year rolls back"
    today = date.today()
    got = NN.held_out_month(today)
    assert got < today.strftime("%Y-%m"), "the current month is not closed"


def test_the_month_is_derived_from_today_and_never_a_literal():
    """CLAUDE.md rule 5. Two calls a month apart must not return the same thing."""
    a = NN.held_out_month(date(2026, 3, 15))
    b = NN.held_out_month(date(2026, 4, 15))
    assert a != b and (a, b) == ("2026-02", "2026-03")


# --------------------------------------------------------------------------
# reading the IC out of E1's own table


def test_held_out_ic_reads_the_jobs_own_daily_table(nn_dir):
    month = NN.held_out_month(date.today())
    p = nn_dir / "e1_daily.csv"
    _daily_csv(p, month, {"GBM_EVENT": 0.012, "GBM_SHUFFLE": 0.001})
    out = NN.held_out_ic(p, month)
    assert out["status"] == "ok"
    assert out["heads"]["GBM_EVENT"]["ic"] == pytest.approx(0.012)
    assert out["heads"]["GBM_EVENT"]["n_date_blocks"] == 4


def test_a_month_absent_from_the_table_is_named_not_zero(nn_dir):
    p = nn_dir / "e1_daily.csv"
    _daily_csv(p, "2020-01", {"GBM_EVENT": 0.01})
    out = NN.held_out_ic(p, NN.held_out_month(date.today()))
    assert out["status"] == "MONTH_NOT_IN_TABLE"
    assert out["heads"] == {}


def test_an_absent_table_is_named_not_an_empty_result(nn_dir):
    out = NN.held_out_ic(nn_dir / "nope.csv", "2026-08")
    assert out["status"] == "DAILY_TABLE_ABSENT"


# --------------------------------------------------------------------------
# beat_last_night


def test_the_first_night_is_null_not_false(nn_dir):
    out = NN.compare_to_last_night("GBM_EVENT", 0.01, "2026-08", history=[])
    assert out["beat_last_night"] is None
    assert out["n_nights_compared"] == 1
    assert "Null, not False" in out["why"]
    assert out["ic_last_night"] is None


def test_the_second_night_compares_against_the_same_head_and_month(nn_dir):
    history = [
        {"date": "2026-09-12", "head": "GBM_EVENT", "held_out_month": "2026-08",
         "ic": 0.009},
        # a DIFFERENT month and a DIFFERENT head: neither may be compared against
        {"date": "2026-09-12", "head": "GBM_EVENT", "held_out_month": "2026-07",
         "ic": 0.900},
        {"date": "2026-09-12", "head": "GBM_SHUFFLE", "held_out_month": "2026-08",
         "ic": 0.900},
    ]
    out = NN.compare_to_last_night("GBM_EVENT", 0.012, "2026-08",
                                   history=history, today="2026-09-13")
    assert out["ic_last_night"] == 0.009
    assert out["beat_last_night"] is True
    assert out["delta"] == pytest.approx(0.003)
    assert out["n_nights_compared"] == 2


def test_a_worse_night_is_reported_as_worse(nn_dir):
    history = [{"date": "2026-09-12", "head": "H", "held_out_month": "2026-08",
                "ic": 0.02}]
    out = NN.compare_to_last_night("H", 0.01, "2026-08", history=history,
                                   today="2026-09-13")
    assert out["beat_last_night"] is False
    assert out["delta"] == pytest.approx(-0.01)


def test_tonights_own_row_is_not_compared_against_itself(nn_dir):
    """A re-run on the same date must not read this evening's earlier write as
    "last night" — that would report improvement against itself."""
    history = [{"date": "2026-09-13", "head": "H", "held_out_month": "2026-08",
                "ic": 0.05}]
    out = NN.compare_to_last_night("H", 0.01, "2026-08", history=history,
                                   today="2026-09-13")
    assert out["beat_last_night"] is None
    assert out["n_nights_compared"] == 1


# --------------------------------------------------------------------------
# the sequence


def test_the_sequence_is_e1_then_e4_then_e5(nn_dir):
    assert [j for j, _ in NN.SEQUENCE] == [
        "E1_event_head", "E4_adwin_gated_refit", "E5_stopping_rules"]
    from scripts.night_factory_jobs import JOBS
    for job, _ in NN.SEQUENCE:
        assert job in JOBS, f"{job} is not in the job registry the factory walks"


def test_a_failing_job_leaves_a_row_and_the_night_continues(nn_dir):
    seen = []

    def _runner(job, minutes):
        seen.append(job)
        if job == "E4_adwin_gated_refit":
            return {"job": job, "status": "error", "detail": "ValueError: boom"}
        return {"job": job, "status": "done", "daily_csv": None}

    out = NN.run_nn_lab(today=date.today(), runner=_runner,
                        history_file=nn_dir / "h.jsonl")
    assert seen == [j for j, _ in NN.SEQUENCE], "one failure did not stop the night"
    assert out["refusals"] == ["E4_adwin_gated_refit: ValueError: boom"]
    assert out["n_heads"] == 0


def test_a_full_night_writes_history_and_the_next_night_compares(nn_dir):
    month = NN.held_out_month(date.today())
    csv = nn_dir / "e1_daily.csv"
    hist = nn_dir / "h.jsonl"
    _daily_csv(csv, month, {"GBM_EVENT": 0.010})

    def _runner(job, minutes):
        return {"job": job, "status": "done",
                "daily_csv": str(csv) if job == "E1_event_head" else None,
                "event_source": "keyword_proxy"}

    night1 = NN.run_nn_lab(today=date.today() - timedelta(days=1), runner=_runner,
                           history_file=hist)
    assert night1["n_heads"] == 1
    assert night1["comparisons"][0]["beat_last_night"] is None
    assert night1["event_source"] == "keyword_proxy", (
        "the receipt says which event source it ran on, unprompted, every night")

    _daily_csv(csv, month, {"GBM_EVENT": 0.014})
    night2 = NN.run_nn_lab(today=date.today(), runner=_runner, history_file=hist)
    c = night2["comparisons"][0]
    assert c["beat_last_night"] is True and c["n_nights_compared"] == 2
    assert night2["n_beat_last_night"] == 1

    rows = [json.loads(x) for x in hist.read_text(encoding="utf-8").splitlines() if x]
    assert len(rows) == 2 and {r["held_out_month"] for r in rows} == {month}


def test_the_receipt_states_what_the_refit_may_never_do(nn_dir):
    out = NN.run_nn_lab(today=date.today(),
                        runner=lambda j, m: {"job": j, "status": "done"},
                        history_file=nn_dir / "h.jsonl")
    joined = " ".join(out["never"]).lower()
    assert "future information" in joined
    assert "target leakage" in joined
    assert "frozen strategy" in joined
    assert "deprioritized" in joined
    assert out["licence"] == "PRODUCT_EXPERIMENT"
    assert out["llm_spend_usd"] == 0.0


def test_the_receipt_is_written_atomically(nn_dir):
    out = NN.run_nn_lab(today=date.today(),
                        runner=lambda j, m: {"job": j, "status": "done"},
                        history_file=nn_dir / "h.jsonl")
    p = NN.write_receipt(out, out=nn_dir)
    assert p.name == f"NN_lab_{date.today().isoformat()}.json"
    assert not p.with_suffix(".json.tmp").exists()


def test_an_unknown_job_is_refused_by_name(nn_dir):
    row = NN.run_job("E9_does_not_exist", 10)
    assert row["status"] == "refused"
    assert "night_factory_jobs.JOBS" in row["why"]
