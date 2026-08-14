"""The belief-change contract (ledger schema 1.1.0) — additive, and pinned.

WHY THESE TESTS EXIST
=====================
The contract replaces the `p != 0.50` refusal. That old rule kept coin flips out
of the ledger and, in doing so, taught forecasters that 0.50 was rejected — an
incentive to say 0.51 rather than to say "this evidence changed nothing".
Under the new contract `belief_change = 0` is a valid, gradeable answer and the
candidate signal is `posterior - prior` rather than the level.

The change is purely ADDITIVE to a LIVE ledger holding ~20k records, so the
first job of these tests is to prove nothing old broke, and the second is to
stop the new fields from ever becoming a second, disagreeing forecast.
"""

from __future__ import annotations

import pytest

from backend.services.belief_state import (SCHEMA_VERSION, Observable,
                                           PredictionRecord, make_prediction)


def _base(**kw):
    args = dict(ticker="AAPL", specialist="investigator",
                observable=Observable.ABS_MOVE_EXCEEDS, horizon_days=5,
                probability=0.40, threshold=0.05, thesis="t",
                counter_thesis="c", next_observable="earnings",
                model="deepseek-v4-flash", model_version="deepseek-v4-flash",
                prompt="p", input_snapshot={"a": 1})
    args.update(kw)
    return make_prediction(**args)


# ── backward compatibility with the live ledger ─────────────────────────────

def test_a_record_without_the_contract_still_writes_and_carries_nulls():
    r = _base()
    assert r.prior is None and r.posterior is None
    assert r.belief_change is None and r.arm is None
    assert r.probability == 0.40


def test_schema_version_advanced_so_the_generations_are_distinguishable():
    # 1.1.0 added the belief-change contract; 1.2.0 added the evidence
    # population. Both are additive, and the version is what lets a reader tell
    # a record that COULD have carried a field from one that could not.
    assert SCHEMA_VERSION == "1.2.0"
    assert _base().schema_version == "1.2.0"


def test_the_new_fields_are_the_only_thing_added():
    # A field renamed or removed would break resolution on 20k live records.
    names = set(PredictionRecord.__dataclass_fields__)
    for required in ("prediction_id", "ticker", "specialist", "observable",
                     "horizon_days", "probability", "threshold", "benchmark",
                     "made_at", "resolves_after", "model", "model_version",
                     "resolved_at", "outcome", "brier", "void_reason"):
        assert required in names
    for added in ("prior", "posterior", "belief_change", "arm"):
        assert added in names


# ── the contract itself ─────────────────────────────────────────────────────

def test_belief_change_is_computed_not_supplied():
    r = _base(probability=0.62, prior=0.45, posterior=0.62)
    assert r.belief_change == pytest.approx(0.17)


def test_zero_belief_change_is_a_valid_gradeable_answer():
    """The whole point of retiring `p != 0.50`.

    "This evidence changed nothing" must be expressible, must be storable, and
    must be graded like any other forecast — including at exactly 0.50, which
    the old contract refused outright.
    """
    r = _base(probability=0.50, prior=0.50, posterior=0.50)
    assert r.belief_change == 0.0
    assert r.probability == 0.50
    assert r.prior == 0.50


def test_half_a_contract_is_refused():
    with pytest.raises(ValueError, match="BOTH prior and posterior"):
        _base(posterior=0.6)
    with pytest.raises(ValueError, match="BOTH prior and posterior"):
        _base(prior=0.4)


def test_the_graded_quantity_may_not_disagree_with_the_stated_belief():
    """Two numbers called "the forecast" is one number too many.

    If `probability` and `posterior` could differ, the ledger would grade one
    while the reasoning chain justified the other, and no reader could tell
    which the forecaster meant.
    """
    with pytest.raises(ValueError, match="must equal posterior"):
        _base(probability=0.40, prior=0.30, posterior=0.62)


def test_out_of_range_priors_are_refused():
    with pytest.raises(ValueError, match="not a probability"):
        _base(probability=0.5, prior=1.4, posterior=0.5)


def test_arm_is_recorded_on_the_record_not_inferred_later():
    assert _base(arm="B_tools").arm == "B_tools"
    # and it is independent of the specialist field, so an arm cannot be
    # reconstructed (or mis-reconstructed) from a prompt label after the fact
    assert _base(arm="A_snapshot", specialist="investigator").arm == "A_snapshot"
