"""M1 (spec §4): the 1.4.0 additions are additive, and the old rows still load.

24,828 rows were written under 1.0.0, 1.2.0 and 1.3.0. Every one of them must
parse into the extended dataclass with the new fields at their declared
defaults, and the numbers the calibration surfaces compute on them must not
move — a migration that silently changes a historical Brier is the F7 failure
class one layer up, and it is not recoverable after the fact.

The fixture is ten REAL rows sampled from the ledger (three per schema version),
not ten rows written by this test: a fixture invented here would agree with
whatever the dataclass happens to do today.
"""

from __future__ import annotations

import json
from dataclasses import asdict, fields
from pathlib import Path

import pytest

from backend.services.belief_state import (SCHEMA_VERSION, PredictionRecord,
                                           calibration, calibration_bucket_of,
                                           era_of, ledger_health)

FIXTURE = Path(__file__).parent / "fixtures" / "predictions_pre_1_4_0.jsonl"

#: Everything 1.4.0 added. Listed here rather than derived from the dataclass so
#: the test fails when a field is added WITHOUT a decision about its default —
#: deriving the list from the class would make the assertion vacuous.
NEW_FIELDS: dict[str, object] = {
    "mechanism_id": None, "decision_date": None, "policy_hash": None,
    "inputs_used": {}, "confidence": None, "control_twin_id": None,
    "control_construction": None, "vs_benchmark": None, "vs_control": None,
    "costs_charged": False, "cost_rate_bps": None, "calibration_bucket": None,
    "LAP_score": None, "anonymization_gap": None, "era_tag": None,
    "licence": None, "n_effective_trials_at_time": None, "notes_text": "",
    "embedding_id": None,
}


def _rows() -> list[dict]:
    assert FIXTURE.is_file(), f"the pre-1.4.0 fixture is missing: {FIXTURE}"
    return [json.loads(x) for x in FIXTURE.read_text(encoding="utf-8").splitlines()
            if x.strip()]


def test_the_version_was_bumped():
    assert SCHEMA_VERSION == "1.4.0"


def test_the_fixture_holds_more_than_one_old_schema():
    versions = {r.get("schema_version") for r in _rows()}
    assert len(_rows()) == 10
    assert {"1.0.0", "1.2.0", "1.3.0"} <= versions, (
        f"the fixture must exercise every schema that exists in the ledger; "
        f"it holds {sorted(versions)}")


def test_every_new_field_is_declared_with_the_spec_default():
    declared = {f.name: f for f in fields(PredictionRecord)}
    for name, want in NEW_FIELDS.items():
        assert name in declared, f"1.4.0 field {name!r} is not on PredictionRecord"
        f = declared[name]
        got = (f.default_factory() if f.default is not None and callable(
            getattr(f, "default_factory", None)) and f.default.__class__.__name__
            == "_MISSING_TYPE" else f.default)
        if f.default.__class__.__name__ == "_MISSING_TYPE":
            got = f.default_factory()
        assert got == want, f"{name}: default {got!r}, spec says {want!r}"


@pytest.mark.parametrize("row", _rows(), ids=lambda r: r["prediction_id"])
def test_an_old_row_loads_with_every_new_field_at_its_default(row):
    rec = PredictionRecord(**row)
    for name, want in NEW_FIELDS.items():
        assert getattr(rec, name) == want, (
            f"{name} on a pre-1.4.0 row should be {want!r}, got "
            f"{getattr(rec, name)!r} — an old row must never arrive carrying a "
            f"value nobody wrote")


@pytest.mark.parametrize("row", _rows(), ids=lambda r: r["prediction_id"])
def test_a_round_trip_adds_keys_and_changes_none(row):
    """The additions are ADDITIVE. Not one existing key may move."""
    out = asdict(PredictionRecord(**row))
    for k, v in row.items():
        assert out[k] == v, f"{k} changed on round trip: {v!r} -> {out[k]!r}"
    added = set(out) - set(row)
    known = {f.name for f in fields(PredictionRecord)}
    assert added <= known, f"the round trip invented key(s) {sorted(added - known)}"
    # every 1.4.0 field arrives; older rows (1.0.0) also gain the 1.1-1.3 ones,
    # which is the same additive property one version earlier
    assert set(NEW_FIELDS) <= (added | set(row))
    # `schema_version` is the row's OWN stamp and must not be rewritten to 1.4.0
    assert out["schema_version"] == row["schema_version"], (
        "loading a row must not restamp it: the stamp is the only thing that "
        "can later tell 'never written' from 'written as None'")


def test_the_calibration_surfaces_read_the_old_fixture_unchanged(tmp_path):
    path = tmp_path / "predictions.jsonl"
    path.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    before = path.read_bytes()
    cal = calibration(path)
    health = ledger_health(path)
    assert path.read_bytes() == before, "reading a ledger must not write to it"
    # None of these ten is graded (the ledger's first resolution has not fallen
    # due), so calibration's honest answer is "nothing has resolved yet" -- and
    # saying that is the behaviour being pinned, not a number.
    assert cal["n_resolved"] == 0
    assert "nothing has resolved yet" in cal["reading"]
    assert health["status"]


# ── the two helpers the resolver uses ──────────────────────────────────────


@pytest.mark.parametrize("p,want", [
    (0.0, "p0-10"), (0.05, "p0-10"), (0.5, "p50-60"), (0.99, "p90-100"),
    (1.0, "p90-100"), (None, None),
])
def test_the_calibration_bucket_is_a_decile(p, want):
    assert calibration_bucket_of(p) == want


@pytest.mark.parametrize("made_at,want", [
    ("2026-09-12T10:00:00+00:00", "2025-2026"),
    ("2020-03-01", "2016-2024"),
    ("2010-06-30", "2008-2015"),
    ("1999-01-01", None),        # outside every declared era
    (None, None),
])
def test_the_era_tag_is_frozen_and_refuses_to_guess(made_at, want):
    """A row outside every declared era gets None, not the nearest match: an
    `era_unknown` bucket a report can name beats a silent reassignment."""
    assert era_of(made_at) == want
