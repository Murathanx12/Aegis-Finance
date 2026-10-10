from datetime import datetime, timedelta, timezone
from copy import deepcopy

import pytest

from ft_lab.beta_news_pipeline import known, outcome_rows


def test_only_dated_known_resolved_news_can_enter_learning():
    now = datetime.now(timezone.utc)
    earlier = (now - timedelta(days=1)).isoformat()
    row = {"specialist": "news_digest:implication_v0", "made_at": earlier,
           "resolved_at": earlier, "outcome": 0}
    pending = {**row, "outcome": None}
    future = {**row, "resolved_at": (now + timedelta(seconds=1)).isoformat()}
    unknown = {**row, "resolved_at": None}
    other = {**row, "specialist": "investigator:test"}
    assert outcome_rows([row, pending, future, unknown, other], now) == [row]
    assert not known(earlier[:10], now)


def test_legacy_resolution_days_admit_only_prior_day_not_same_day():
    now = datetime.now(timezone.utc)
    earlier = (now - timedelta(days=1)).isoformat()
    row = {"specialist": "news_digest:implication_v0", "made_at": earlier,
           "resolved_at": earlier[:10], "outcome": 0}
    same_day = {**row, "resolved_at": now.date().isoformat()}
    assert outcome_rows([row, same_day], now) == [row]


@pytest.mark.parametrize("markers", [
    {"void_reason": "invalid source"}, {"voided_at": "recorded"}, {"voided": True},
    {"state": "VOID"}, {"status": "voided"}, {"quarantined": True},
    {"quarantine_reason": "invalid population"}, {"quarantined_at": "recorded"},
    {"resolution_state": "QUARANTINED"},
])
def test_persisted_invalid_learning_rows_are_excluded_without_mutation(markers):
    now = datetime.now(timezone.utc)
    earlier = (now - timedelta(days=1)).isoformat()
    row = {"specialist": "news_digest:implication_v0", "made_at": earlier,
           "resolved_at": earlier, "outcome": 0, **markers}
    original = deepcopy(row)
    assert outcome_rows([row], now) == []
    assert row == original


def test_chronology_compares_instants_across_timezone_offsets():
    now = datetime.now(timezone.utc)
    yesterday = (now - timedelta(days=1)).date().isoformat()
    row = {"specialist": "news_digest:implication_v0", "made_at": yesterday + "T10:00:00+00:00",
           "resolved_at": yesterday + "T10:30:00+01:00", "outcome": 0}
    assert outcome_rows([row], now) == [], "resolution is 09:30 UTC, before the 10:00 forecast"
    row["resolved_at"] = yesterday + "T09:30:00-01:00"
    assert outcome_rows([row], now) == [row], "resolution is 10:30 UTC; valid zero outcome"


def test_day_only_resolution_requires_strictly_prior_utc_day_even_at_day_end():
    now = datetime.now(timezone.utc).replace(hour=23, minute=59, second=59, microsecond=999999)
    row = {"specialist": "news_digest:implication_v0", "made_at": (now - timedelta(days=1)).isoformat(),
           "resolved_at": now.date().isoformat(), "outcome": 0}
    assert outcome_rows([row], now) == []
    assert outcome_rows([row], now.astimezone(timezone(timedelta(hours=-3)))) == []


@pytest.mark.parametrize("made,resolved", [("invalid", "invalid"), (None, None),
    ("2026-01-01T10:00:00", "2026-01-02T10:00:00+00:00"),
    ("2026-01-01T10:00:00+00:00", "2026-01-02T10:00:00")])
def test_malformed_or_naive_learning_times_are_unknown(made, resolved):
    row = {"specialist": "news_digest:implication_v0", "made_at": made,
           "resolved_at": resolved, "outcome": 0}
    assert outcome_rows([row], datetime.now(timezone.utc)) == []


def test_actual_grade_receipt_changes_subsequent_key_inputs_without_forcing_weights(tmp_path):
    """Zero evidence remains an explicit prior consumed by the actual reader.

Positive artificial trust is deliberately absent: this checks the file-to-real
consumer connection without inventing a successful forecast history.
"""
    from ft_lab.beta_news_pipeline import write
    from backend.services import world_digest as WD, world_state as WS
    grade = WD.grade([])
    digest = "world_digest_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json"
    write(tmp_path / "digest" / digest, {"shadow": {"grade": grade,
          "trust_dir": grade["direction"]["trust"], "trust_size": grade["size"]["trust"]}})
    weights = {"SPY": 0.10}
    result = WS.plan_news_tilt(weights, root=tmp_path)
    assert result["digest_file"] == digest
    assert result["two_key"]["key1_direction"]["n_dates"] == 0
    assert result["weights"] == weights and not result["applied"]
    assert not result["two_key"]["ready_for_owner"]
