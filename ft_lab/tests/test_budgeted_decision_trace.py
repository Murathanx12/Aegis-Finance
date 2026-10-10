"""Source-semantic regressions and boundaries for the offline trace runner."""
import copy
import json
from pathlib import Path

import pytest

from ft_lab import budgeted_decision_trace as T


def cacc_fixture():
    spec = copy.deepcopy(T.SPECS[-1])
    # Exact source fragments, assembled solely for unit tests; the actual batch
    # binds the complete stored article to SPECS[-1]'s original body hash.
    body = " ".join([spec["entity"], spec["date_span"], *spec["spans"], "pay $15.5 million"])
    spec["sha"] = T.sha_bytes(body.encode())
    doc = dict(body=body, raw_id=spec["id"], tickers=["CACC"], source="sec_edgar_8k_ex99_body",
               url="https://www.sec.gov/Archives/edgar/data/885550/000088555026000192/cacc_8k20260917pr.htm",
               published_utc="2026-09-18T21:29:13+00:00", first_seen_utc="2026-09-19T09:35:27+00:00")
    return doc, spec


def test_mixed_entered_or_will_enter_does_not_license_settlement_day():
    doc, spec = cacc_fixture()
    result = T.extract(doc, spec, Path("stored_source.jsonl"))
    assert result["reporting_date"] == "2026-09-17"
    assert result["facts"]["event_type"] == "litigation_settlement"
    assert result["facts"]["event_date"] is None
    assert result["facts"]["abstain"] is False
    attempted = {**result["facts"], "event_date": "2026-09-17", "date_precision": "day"}
    with pytest.raises(ValueError, match="unsupported_operative_event_day"):
        T.validate_candidate(attempted, doc["body"], spec)
    for role in ["settlement", "completion", "estimated"]:
        with pytest.raises(ValueError, match="unsupported event-date role"):
            T.event_day(spec, role)


def test_source_drift_and_future_first_seen_fail_loud():
    doc, spec = cacc_fixture()
    with pytest.raises(ValueError, match="identity/content changed"):
        T.extract({**doc, "body": doc["body"] + "changed"}, spec, Path("x"))
    with pytest.raises(ValueError, match="information cutoff"):
        T.extract({**doc, "first_seen_utc": "2026-10-11T00:00:00Z"}, spec, Path("x"))


def test_spans_are_canonical_source_offsets():
    doc, spec = cacc_fixture()
    result = T.extract(doc, spec, Path("x"))
    for span in result["source_spans"]:
        assert doc["body"][span["start"]:span["end"]] == span["text"]


def test_output_cannot_be_runtime_or_outside_scoped_trace(tmp_path):
    with pytest.raises(ValueError, match="isolated trace directory"):
        T.run(tmp_path / "runtime", tmp_path / "unapproved_output")
    assert not (tmp_path / "unapproved_output").exists()


def test_stored_actual_failed_reply_is_rejected_and_hash_bound():
    # Integration against the locally frozen actual batch input. No network.
    folder = T.DEFAULT_OUT / "reviewed-final"
    if not (folder / "failed_reply_input.json").exists():
        pytest.skip("attended local source/checkpoint batch not available")
    cacc = json.loads((folder / "sources.json").read_text(encoding="utf-8"))["documents"][-1]
    receipt = T.reject_stored_reply(folder / "failed_reply_input.json", cacc)
    assert receipt["candidate_origin"] == "actual_stored_failed_local_reply"
    assert receipt["verdict"] == "REJECTED"
    assert receipt["candidate"]["event_date"] == "2026-09-17"
    assert "entered or will enter" in receipt["operative_source_span"]


def test_unknown_nonfinite_values_stay_null_not_zero():
    assert T.json_safe({"unknown": float("nan"), "bad": float("inf")}) == {"unknown": None, "bad": None}
