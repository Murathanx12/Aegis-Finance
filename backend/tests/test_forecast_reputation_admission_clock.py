"""A private refit holds future and malformed grading dates before tuning."""

import hashlib
import json
from datetime import date, datetime, timezone

import pytest

from backend.services import forecast_reputation as FR


def test_refit_admission_uses_utc_cutoff_and_preserves_legacy_rows(tmp_path, monkeypatch):
    class SingaporeDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 10, 15)

    class FrozenUtc(datetime):
        @classmethod
        def now(cls, tz=None):
            instant = cls(2026, 10, 14, 16, 16, tzinfo=timezone.utc)
            return instant if tz is None else instant.astimezone(tz)

    monkeypatch.setattr(FR, "date", SingaporeDate)
    monkeypatch.setattr(FR, "datetime", FrozenUtc)
    tuned_rows = []

    def stop_before_tuning(frame, grid=None):
        tuned_rows.append(len(frame))
        return {"status": "REFUSED", "reason": "fixture stop"}

    monkeypatch.setattr(FR, "tune", stop_before_tuning)
    base = {"specialist": "fixture", "probability": 0.6, "outcome": 1,
            "made_at": "2026-10-05T01:00:00+00:00", "ticker": "AAA",
            "observable": "return_sign", "horizon_days": 1}
    rows = [
        {**base, "resolves_after": "2026-10-12", "resolved_at": "2026-10-13"},
        {**base, "resolves_after": "2026-10-15", "resolved_at": "2026-10-15"},
        {**base, "resolves_after": "2026-10-12", "resolved_at": "2026-10-15"},
        {**base, "resolves_after": "2026-10-xx", "resolved_at": "2026-10-13"},
        {**base, "resolves_after": "2026-10-12", "resolved_at": "2026-10-xx"},
        {**base, "resolves_after": None, "resolved_at": None},
    ]
    ledger = tmp_path / "predictions.jsonl"
    ledger.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    original = hashlib.sha256(ledger.read_bytes()).hexdigest()
    out = tmp_path / "private_reputation"

    receipt = FR.refit(ledger, out_dir=out)
    assert receipt["date"] == "2026-10-14"
    assert receipt["n_graded"] == 2
    assert receipt["admission"]["n_held"] == 4
    assert receipt["admission"]["held_reasons"] == {
        "future_resolves_after": 1, "future_resolved_at": 2,
        "malformed_resolves_after": 1, "malformed_resolved_at": 1,
    }
    assert receipt["admission"]["admitted_missing_dates"] == {
        "resolves_after": 1, "resolved_at": 1,
    }
    assert tuned_rows == [2]
    assert hashlib.sha256(ledger.read_bytes()).hexdigest() == original

    with pytest.raises(ValueError, match="future refit as-of"):
        FR.refit(ledger, today="2026-10-16", out_dir=out)
    assert not (out / "reputation_2026-10-16.json").exists()
    assert tuned_rows == [2]
    assert hashlib.sha256(ledger.read_bytes()).hexdigest() == original

    historical = FR.refit(ledger, today="2026-10-12", out_dir=out)
    assert historical["admission"]["cutoff_utc"] == "2026-10-12"
    assert historical["n_graded"] == 1  # only legacy row lacks a later date
    assert tuned_rows == [2, 1]
