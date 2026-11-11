"""CH-05 rescue R4: provisional NO_NEW_BET rows, outside the pinned contract file.

`backend/services/decision_contract.py` is byte-pinned by the prepared PC
policy epoch, so the runtime's +244 lines live in `provisional_decision.py`.
The last test here is the reason: it fails if the port is ever folded back.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.services import decision_contract as DC
from backend.services import provisional_decision as PD

ROOT = Path(__file__).resolve().parents[2]
SHA = "a" * 64


def _evidence(eid, value=None, *, at="2026-11-04T12:00:00+00:00"):
    item = {"evidence_id": eid, "quality": "AVAILABLE", "available_at": at,
            "observed_at": at, "source": "fixture", "source_sha256": SHA}
    if value is not None:
        item["value"] = value
    return item


def _request(**over):
    req = {"event_id": "EV1", "ticker": "ABC", "horizon": "through Q3 print",
           "mandate": {"max_loss_fraction": 0.1}, "asof": "2026-11-05T00:00:00Z",
           "deadline": "2026-11-06T00:00:00Z", "horizon_end": "2026-11-20T00:00:00Z",
           "exposure_kind": "fully_paid_long", "required_evidence": ["report"],
           "available_evidence": [_evidence("price_usd", 50.0), _evidence("shares", 10),
                                  _evidence("equity_usd", 10_000.0)],
           "conditional_loss_fractions": [0.2, 1.0],
           "conditional_return_fractions": [-0.3, 0.1]}
    req.update(over)
    return req


def test_a_provisional_row_is_no_new_bet_sealed_and_names_what_is_missing():
    (row,) = PD.provisional_contracts(_request())
    assert row["action"] == "NO_NEW_BET" and row["orders_authorized"] is False
    assert row["direction"] == "REFUSED" and row["licence"] == DC.LICENCE
    assert row["missing_evidence"] == ["report"]
    assert row["conditional_risk"]["position_value_usd"] == 500.0
    assert row["conditional_risk"]["portfolio_loss_fraction"] == pytest.approx(0.05)
    assert row["artifact_sha256"] == DC.seal(row)


def test_the_same_evidence_is_idempotent_and_new_evidence_is_a_child():
    first = PD.provisional_contracts(_request())
    assert PD.provisional_contracts(_request(asof="2026-11-05T06:00:00Z"),
                                    prior_records=first) == first
    more = _request(asof="2026-11-05T07:00:00Z",
                    available_evidence=_request()["available_evidence"] + [_evidence("report")])
    history = PD.provisional_contracts(more, prior_records=first)
    assert len(history) == 2
    child = history[-1]
    assert child["parent_decision_id"] == first[0]["decision_id"]
    assert child["original_pit"] == first[0]["original_pit"]
    assert child["missing_evidence"] == []


def test_a_mandate_cannot_change_within_an_event_and_a_tampered_parent_refuses():
    first = PD.provisional_contracts(_request())
    with pytest.raises(ValueError, match="mandate cannot change"):
        PD.provisional_contracts(_request(mandate={"max_loss_fraction": 0.5},
                                          available_evidence=[]), prior_records=first)
    tampered = [{**first[0], "ticker": "ABC", "rationale": "edited"}]
    with pytest.raises(ValueError, match="seal mismatch"):
        PD.provisional_contracts(_request(available_evidence=[]), prior_records=tampered)


def test_evidence_after_the_cut_is_unusable_not_silently_used():
    late = _evidence("report", at="2026-11-05T09:00:00+00:00")
    (row,) = PD.provisional_contracts(_request(
        available_evidence=_request()["available_evidence"] + [late]))
    assert "report" in row["missing_evidence"]
    assert any("outside PIT cut" in u["reason"] for u in row["unusable_evidence"])


def test_a_naive_timestamp_or_levered_exposure_refuses():
    with pytest.raises(ValueError, match="timezone"):
        PD.provisional_contracts(_request(asof="2026-11-05T00:00:00"))
    with pytest.raises(ValueError, match="fully_paid_long"):
        PD.provisional_contracts(_request(exposure_kind="margin_long"))


def test_cost_refusal_assessment_describes_the_failure_and_authorizes_nothing():
    exc = DC.CostModelRefused("zero cost without zero_cost_diagnostic")
    clock = lambda: datetime(2026, 11, 5, 22, 0, tzinfo=timezone.utc)  # noqa: E731
    row = PD.cost_refusal_assessment({"date": "2026-11-05"}, exc, observed_clock=clock)
    assert row["row_kind"] == "PROVISIONAL_REFUSAL_ASSESSMENT"
    assert row["decision_status"] == "PROVISIONAL"
    assert row["asof"] == "2026-11-05T22:00:00+00:00"
    assert row["action"] == "NO_NEW_BET" and row["orders_authorized"] is False
    assert row["original_failure"]["cause"].startswith("CostModelRefused: zero cost")
    assert row["context_cutoff"]["instant"] is None and row["mandate_status"] == "NOT_SUPPLIED"
    json.dumps(row, allow_nan=False)


def test_cost_refusal_with_a_bad_clock_is_untimed_not_invented():
    row = PD.cost_refusal_assessment({"date": "2026-11-05", "mandate": "not-an-object"},
                                     DC.CostModelRefused("x"),
                                     observed_clock=lambda: datetime(2026, 11, 5))
    assert row["asof"] is None and row["decision_status"] == "PROVISIONAL_UNTIMED"
    assert row["mandate_status"] == "INVALID"
    assert len(row["data_quality_warnings"]) == 2


def test_the_pinned_contract_file_still_matches_the_prepared_epoch():
    """Why this module exists: folding these functions back into
    decision_contract.py moves its bytes and the epoch refuses."""
    from backend.services import pc_policy_epoch as PE

    epoch = json.loads((ROOT / "backend/data/pc_policy_epochs/"
                        "pc_paper_no_index_2026_10_v1.json").read_text(encoding="utf-8"))
    rel = "backend/services/decision_contract.py"
    pinned = next(v[rel] for k, v in _walk(epoch) if k == "source_sha256")
    assert PE._source_sha(ROOT / rel) == pinned
    assert "provisional_contracts" not in (ROOT / rel).read_text(encoding="utf-8")


def _walk(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k, v
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)
