"""The Oct 14 UTC premature grades stay out after the date rolls over."""

import hashlib
import json
from datetime import date, datetime, timezone

import pytest

from backend.services import forecast_reputation as fr


def _digest(row):
    return hashlib.sha256(json.dumps(row, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode()).hexdigest()


def _fixture(tmp_path, monkeypatch):
    rows = [{"prediction_id": f"{i:016x}", "probability": 0.6,
             "outcome": i % 2, "resolves_after": "2026-10-15",
             "resolved_at": "2026-10-15"} for i in range(214)]
    ids = sorted(row["prediction_id"] for row in rows)
    idsha = hashlib.sha256("\n".join(ids).encode()).hexdigest()
    data = {"schema": "aegis_premature_resolution_hold/1",
            "status": "HOLD_UNTIL_ATTENDED_CANONICAL_REGRADE", "count": 214,
            "idset_sha256": idsha,
            "entries": [{"prediction_id": row["prediction_id"],
                         "premature_grade_sha256": _digest(row)} for row in rows]}
    path = tmp_path / "private_hold.json"
    path.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
    monkeypatch.setattr(fr, "_PREMATURE_HOLD_SHA256",
                        hashlib.sha256(path.read_bytes()).hexdigest())
    monkeypatch.setattr(fr, "_PREMATURE_IDSET_SHA256", idsha)
    monkeypatch.setattr(fr, "_PREMATURE_ID_HASHES", frozenset(
        hashlib.blake2b(pid.encode(), digest_size=16).digest() for pid in ids))
    return rows, path


def test_rollover_does_not_admit_premature_rows(tmp_path, monkeypatch):
    rows, path = _fixture(tmp_path, monkeypatch)
    hold = fr._premature_hold(rows, path)
    good = {"prediction_id": "good", "probability": 0.7, "outcome": 1,
            "resolves_after": "2026-10-15", "resolved_at": "2026-10-15"}
    admitted, audit = fr._admit_for_refit(rows + [good], date(2026, 10, 15), hold)
    assert admitted == [good]
    assert audit["n_held"] == 214
    assert audit["held_reasons"] == {"premature_resolution_2026_10_14": 214}


def test_changed_or_missing_hold_fails_closed(tmp_path, monkeypatch):
    rows, path = _fixture(tmp_path, monkeypatch)
    with pytest.raises(FileNotFoundError):
        fr._premature_hold(rows, tmp_path / "not_installed.json")
    rows[0] = {**rows[0], "outcome": 1 - rows[0]["outcome"]}
    with pytest.raises(ValueError, match="changed"):
        fr._premature_hold(rows, path)
    with pytest.raises(ValueError, match="absent"):
        fr._premature_hold(rows[1:], path)
    path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(ValueError, match="content mismatch"):
        fr._premature_hold(rows, path)


def test_only_captured_grades_require_hold(tmp_path, monkeypatch):
    rows, _ = _fixture(tmp_path, monkeypatch)
    old = {**rows[0], "outcome": None, "resolved_at": None}
    assert not fr._premature_hold_required([old], date(2026, 10, 15), "old.jsonl")
    assert not fr._premature_hold_required(rows, date(2026, 10, 14), None)
    assert fr._premature_hold_required(rows, date(2026, 10, 15), "capture.jsonl")
    other = {**rows[0], "prediction_id": "independent-ledger-id"}
    assert not fr._premature_hold_required([other], date(2026, 10, 15), None)


def test_refit_refuses_missing_required_hold_before_output(tmp_path, monkeypatch):
    rows, _ = _fixture(tmp_path, monkeypatch)
    class AtRollover(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 15, 0, 1, tzinfo=timezone.utc)

    monkeypatch.setattr(fr, "datetime", AtRollover)
    ledger = tmp_path / "predictions.jsonl"
    ledger.write_text(json.dumps(rows[0]) + "\n",
                      encoding="utf-8")
    out = tmp_path / "reputation"
    with pytest.raises(FileNotFoundError):
        fr.refit(ledger, today="2026-10-15", out_dir=out,
                 premature_hold_path=tmp_path / "missing.json")
    assert not out.exists()
