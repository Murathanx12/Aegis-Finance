"""Adjudication 2026-09-26 row 2: `raw_probability` / `shrink_basis` are
OPTIONAL fields on `PredictionRecord`. Adding them must not break reading the
26k rows already in the ledger, none of which carries either key."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from backend.services import belief_state as B

FIXTURE = Path(__file__).parent / "fixtures" / "predictions_pre_1_4_0.jsonl"


def _mk(**kw):
    base = dict(ticker="AAA", specialist="investigator:test",
                observable=B.Observable.BEATS_BENCHMARK, horizon_days=1,
                probability=0.6, benchmark="SPY", thesis="t", counter_thesis="c",
                next_observable="n", model="m", model_version="v", prompt="p",
                input_snapshot={"x": 1})
    base.update(kw)
    return B.make_prediction(**base)


def test_an_old_row_without_the_fields_still_parses():
    rows = [json.loads(x) for x in FIXTURE.read_text(encoding="utf-8").splitlines()
            if x.strip()]
    assert rows and all("raw_probability" not in r for r in rows)
    for r in rows:
        rec = B.PredictionRecord(**r)
        assert rec.raw_probability is None and rec.shrink_basis is None
        out = asdict(rec)
        assert all(out[k] == v for k, v in r.items())


def test_a_direction_row_carries_raw_equal_to_probability_and_its_basis():
    rec = _mk(raw_probability=0.6, shrink_basis="none: direction skill unmeasured")
    assert rec.raw_probability == rec.probability == pytest.approx(0.6)
    assert rec.shrink_basis == "none: direction skill unmeasured"
    back = B.PredictionRecord(**json.loads(json.dumps(asdict(rec))))
    assert back.raw_probability == pytest.approx(0.6)


def test_a_new_row_without_raw_defaults_to_none():
    rec = _mk()
    assert rec.raw_probability is None and rec.shrink_basis is None


def test_a_raw_probability_needs_a_basis_and_must_be_a_probability():
    with pytest.raises(ValueError, match="shrink_basis"):
        _mk(raw_probability=0.6)
    with pytest.raises(ValueError, match="raw_probability"):
        _mk(raw_probability=1.4, shrink_basis="x")
