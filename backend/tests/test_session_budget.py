"""Session budget (Q10): the DECLARED worker/priority receipt plus the one
MEASURED number it carries (paid-API spend, pulled from `llm_telemetry`).

What these tests pin:
 * open -> log -> close is a working round trip, and `close` is idempotent;
 * a row with no priority is REFUSED (ValueError), not defaulted or dropped;
 * a row with a bad worker, blank task, or blank EV is likewise refused;
 * the summary's opus-share arithmetic is exact, including the empty-session
   `None` (not a fabricated 0.0) and the all-opus / no-opus edges;
 * the handoff block always carries the literal `DECLARED` label, and the
   `MEASURED` label whenever paid-API spend is reported;
 * the CLI (`main`) refuses a missing-priority row with exit code 2 and never
   writes the row.
"""

from __future__ import annotations

import json

import pytest

from backend.services import session_budget as SB


# ---------------------------------------------------------------- open/log/close


def test_open_creates_a_session_file(tmp_path):
    doc = SB.open_session("S1", date_="2026-10-07", base=tmp_path)
    assert doc["session_id"] == "S1"
    assert doc["date"] == "2026-10-07"
    assert doc["closed_utc"] is None
    assert doc["rows"] == []
    assert SB.session_path("S1", tmp_path).exists()


def test_open_refuses_to_clobber_an_existing_session(tmp_path):
    SB.open_session("S1", date_="2026-10-07", base=tmp_path)
    second = SB.open_session("S1", date_="2026-10-08", base=tmp_path)
    assert "error" in second
    # the original is untouched
    doc = json.loads(SB.session_path("S1", tmp_path).read_text(encoding="utf-8"))
    assert doc["date"] == "2026-10-07"


def test_log_then_close_round_trip(tmp_path):
    SB.open_session("S1", date_="2026-10-07", base=tmp_path)
    SB.log_row("S1", task="fix the thing", worker="opus", priority=2,
              ev="P(fix)=0.9 x high value - low cost", base=tmp_path)
    SB.log_row("S1", task="write docs", worker="sonnet", priority=6,
              ev="mechanical, low risk", tokens=1200, usd=0.03, base=tmp_path)
    doc = SB.close_session("S1", base=tmp_path)
    assert doc["closed_utc"] is not None
    assert doc["summary"]["n_rows"] == 2
    assert doc["summary"]["by_worker"] == {"opus": 1, "sonnet": 1}
    assert doc["summary"]["by_priority"] == {"2": 1, "6": 1}
    assert doc["summary"]["opus_share_of_rows"] == 0.5
    assert "handoff_block" in doc["summary"]


def test_close_is_idempotent(tmp_path):
    SB.open_session("S1", date_="2026-10-07", base=tmp_path)
    SB.log_row("S1", task="t1", worker="opus", priority=1, ev="x", base=tmp_path)
    first = SB.close_session("S1", base=tmp_path)
    second = SB.close_session("S1", base=tmp_path)
    assert first["closed_utc"] == second["closed_utc"]
    assert first["summary"] == second["summary"]


def test_log_refuses_once_closed(tmp_path):
    SB.open_session("S1", date_="2026-10-07", base=tmp_path)
    SB.close_session("S1", base=tmp_path)
    with pytest.raises(ValueError, match="closed"):
        SB.log_row("S1", task="late row", worker="opus", priority=1, ev="x",
                  base=tmp_path)


def test_log_refuses_without_opening_first(tmp_path):
    with pytest.raises(ValueError, match="never opened"):
        SB.log_row("ghost", task="t", worker="opus", priority=1, ev="x",
                  base=tmp_path)


# ---------------------------------------------------------------- refusals


def test_a_row_without_a_priority_is_refused(tmp_path):
    SB.open_session("S1", date_="2026-10-07", base=tmp_path)
    with pytest.raises(ValueError, match="priority"):
        SB.log_row("S1", task="t", worker="opus", priority=None, ev="x",
                  base=tmp_path)
    # and the row was NOT written
    doc = json.loads(SB.session_path("S1", tmp_path).read_text(encoding="utf-8"))
    assert doc["rows"] == []


@pytest.mark.parametrize("bad_priority", [0, 8, -1, 100])
def test_a_priority_outside_1_to_7_is_refused(tmp_path, bad_priority):
    SB.open_session("S1", date_="2026-10-07", base=tmp_path)
    with pytest.raises(ValueError, match="priority"):
        SB.log_row("S1", task="t", worker="opus", priority=bad_priority, ev="x",
                  base=tmp_path)


def test_an_unknown_worker_is_refused(tmp_path):
    SB.open_session("S1", date_="2026-10-07", base=tmp_path)
    with pytest.raises(ValueError, match="worker"):
        SB.log_row("S1", task="t", worker="gpt5", priority=1, ev="x",
                  base=tmp_path)


def test_a_blank_task_or_ev_is_refused(tmp_path):
    SB.open_session("S1", date_="2026-10-07", base=tmp_path)
    with pytest.raises(ValueError, match="task"):
        SB.log_row("S1", task="  ", worker="opus", priority=1, ev="x",
                  base=tmp_path)
    with pytest.raises(ValueError, match="EV"):
        SB.log_row("S1", task="t", worker="opus", priority=1, ev="",
                  base=tmp_path)


def test_tokens_and_usd_are_never_guessed(tmp_path):
    """Omitting tokens/usd leaves them `None`, not `0` -- a fabricated zero
    reads as 'this task was free'."""
    SB.open_session("S1", date_="2026-10-07", base=tmp_path)
    row = SB.log_row("S1", task="t", worker="opus", priority=1, ev="x",
                     base=tmp_path)
    assert row["tokens"] is None
    assert row["usd"] is None
    assert row["tokens_label"] is None
    assert row["usd_label"] is None
    row2 = SB.log_row("S1", task="t2", worker="sonnet", priority=5, ev="y",
                      tokens=500, usd=0.01, base=tmp_path)
    assert row2["tokens"] == 500
    assert row2["tokens_label"] == SB.DECLARED
    assert row2["usd_label"] == SB.DECLARED


# ---------------------------------------------------------------- opus share


def test_opus_share_is_none_for_an_empty_session():
    assert SB.opus_share([]) is None


def test_opus_share_arithmetic():
    rows = [{"worker": "opus"}, {"worker": "opus"}, {"worker": "sonnet"},
            {"worker": "deepseek"}]
    assert SB.opus_share(rows) == 0.5


def test_opus_share_all_opus_and_no_opus():
    assert SB.opus_share([{"worker": "opus"}, {"worker": "opus"}]) == 1.0
    assert SB.opus_share([{"worker": "sonnet"}, {"worker": "deepseek"}]) == 0.0


# ---------------------------------------------------------------- paid-API spend + handoff


def test_paid_api_spend_is_labelled_measured(tmp_path, monkeypatch):
    from backend.services import llm_telemetry

    def _fake_summary(since=None, path=None, predictions_path=None):
        assert since == "2026-10-07"
        return {"total_cost_usd": 1.23, "n_calls": 7, "total_is_lower_bound": False,
                "cost_is_estimate": True, "n_unpriced_calls": 0}

    monkeypatch.setattr(llm_telemetry, "summary", _fake_summary)
    out = SB._paid_api_spend("2026-10-07")
    assert out["label"] == SB.MEASURED
    assert out["available"] is True
    assert out["total_cost_usd"] == 1.23
    assert out["n_calls"] == 7
    assert "llm_telemetry" in out["ledger"]


def test_paid_api_spend_reports_unavailable_rather_than_zero(monkeypatch):
    from backend.services import llm_telemetry

    def _boom(since=None, path=None, predictions_path=None):
        raise RuntimeError("ledger read failed")

    monkeypatch.setattr(llm_telemetry, "summary", _boom)
    out = SB._paid_api_spend("2026-10-07")
    assert out["label"] == SB.MEASURED
    assert out["available"] is False
    assert "RuntimeError" in out["reason"]
    assert "total_cost_usd" not in out


def test_handoff_block_carries_declared_and_measured_labels(tmp_path, monkeypatch):
    from backend.services import llm_telemetry

    monkeypatch.setattr(llm_telemetry, "summary",
                        lambda since=None, path=None, predictions_path=None:
                        {"total_cost_usd": 0.5, "n_calls": 3,
                         "total_is_lower_bound": True, "cost_is_estimate": True,
                         "n_unpriced_calls": 0})
    SB.open_session("S1", date_="2026-10-07", base=tmp_path)
    SB.log_row("S1", task="t1", worker="opus", priority=1, ev="x", base=tmp_path)
    SB.log_row("S1", task="t2", worker="sonnet", priority=4, ev="y", base=tmp_path)
    doc = SB.close_session("S1", base=tmp_path)
    block = doc["summary"]["handoff_block"]
    assert SB.DECLARED in block
    assert SB.MEASURED in block
    assert "$0.5" in block
    assert "lower bound" in block


def test_build_handoff_block_standalone_before_close(tmp_path, monkeypatch):
    """`build_handoff_block` must work even without a `summary` key yet (called
    directly on an open session's doc)."""
    from backend.services import llm_telemetry

    monkeypatch.setattr(llm_telemetry, "summary",
                        lambda since=None, path=None, predictions_path=None: {
                            "total_cost_usd": 0.0, "n_calls": 0,
                            "total_is_lower_bound": False,
                            "cost_is_estimate": True, "n_unpriced_calls": 0})
    SB.open_session("S1", date_="2026-10-07", base=tmp_path)
    SB.log_row("S1", task="t1", worker="opus", priority=1, ev="x", base=tmp_path)
    fresh = json.loads(SB.session_path("S1", tmp_path).read_text(encoding="utf-8"))
    block = SB.build_handoff_block(fresh)
    assert SB.DECLARED in block
    assert SB.MEASURED in block


# ---------------------------------------------------------------- status / find_open


def test_find_open_session_skips_closed_ones(tmp_path):
    SB.open_session("S1", date_="2026-10-06", base=tmp_path)
    SB.close_session("S1", base=tmp_path)
    SB.open_session("S2", date_="2026-10-07", base=tmp_path)
    found = SB.find_open_session(tmp_path)
    assert found["session_id"] == "S2"


def test_find_open_session_none_when_all_closed(tmp_path):
    SB.open_session("S1", date_="2026-10-07", base=tmp_path)
    SB.close_session("S1", base=tmp_path)
    assert SB.find_open_session(tmp_path) is None


def test_render_table_shows_opus_share_and_declared_label(tmp_path):
    SB.open_session("S1", date_="2026-10-07", base=tmp_path)
    SB.log_row("S1", task="t1", worker="opus", priority=1, ev="x", base=tmp_path)
    doc = json.loads(SB.session_path("S1", tmp_path).read_text(encoding="utf-8"))
    table = SB.render_table(doc)
    assert "OPEN" in table
    assert SB.DECLARED in table


# ---------------------------------------------------------------- CLI


def test_cli_log_without_priority_flag_is_refused(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(SB, "SESSION_DIR", tmp_path)
    assert SB.main(["open", "--session", "S1", "--date", "2026-10-07"]) == 0
    # argparse itself refuses (missing required --priority) by raising
    # SystemExit(2) -- a row is never reached, let alone written.
    with pytest.raises(SystemExit) as exc:
        SB.main(["log", "--session", "S1", "--task", "t", "--worker", "opus",
                "--ev", "x"])
    assert exc.value.code == 2
    doc = json.loads(SB.session_path("S1", tmp_path).read_text(encoding="utf-8"))
    assert doc["rows"] == []


def test_cli_log_with_out_of_range_priority_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(SB, "SESSION_DIR", tmp_path)
    assert SB.main(["open", "--session", "S1", "--date", "2026-10-07"]) == 0
    with pytest.raises(SystemExit) as exc:
        SB.main(["log", "--session", "S1", "--task", "t", "--worker", "opus",
                "--priority", "9", "--ev", "x"])
    assert exc.value.code == 2
    doc = json.loads(SB.session_path("S1", tmp_path).read_text(encoding="utf-8"))
    assert doc["rows"] == []


def test_cli_full_round_trip(tmp_path, monkeypatch):
    from backend.services import llm_telemetry

    monkeypatch.setattr(SB, "SESSION_DIR", tmp_path)
    monkeypatch.setattr(llm_telemetry, "summary",
                        lambda since=None, path=None, predictions_path=None: {
                            "total_cost_usd": 0.0, "n_calls": 0,
                            "total_is_lower_bound": False,
                            "cost_is_estimate": True, "n_unpriced_calls": 0})
    assert SB.main(["open", "--session", "S1", "--date", "2026-10-07"]) == 0
    assert SB.main(["log", "--session", "S1", "--task", "t", "--worker", "opus",
                    "--priority", "1", "--ev", "x"]) == 0
    assert SB.main(["close", "--session", "S1"]) == 0
    assert SB.main(["status", "--session", "S1"]) == 0
