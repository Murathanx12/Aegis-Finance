"""The slice register must refuse, and must refuse the evasion too.

Every test here drives the refusing path (SS47). The register is constructed
against a tmp_path so no test can write the real ledger.
"""

from __future__ import annotations

import json

import pytest

from backend.services.research_gym.slice_register import (NON_INDEPENDENT,
                                                          SliceIdentity,
                                                          SliceRefusal,
                                                          SliceRegister)

SIX = ("DIA", "XLV", "XLI", "XLP", "XLU", "XLB")
OUTCOME = "exceptional move, precursor grammar"


def _ident(secs=SIX, start="1999-01-01", end="2026-08-15", hz=20,
           outcome=OUTCOME) -> SliceIdentity:
    return SliceIdentity(securities=tuple(secs), start=start, end=end,
                         outcome_horizon_days=hz, outcome_definition=outcome,
                         information_cutoff=end)


def _reg(tmp_path) -> SliceRegister:
    return SliceRegister(tmp_path / "slice_register.jsonl")


def _consume_n9(reg) -> None:
    reg.claim(_ident(), "CONFIRM", trial="N9",
              consumed_at="2026-08-16T04:00:00Z")


# ── identity ───────────────────────────────────────────────────────────────

def test_identity_is_order_and_case_insensitive_in_the_universe():
    a = SliceIdentity(("spy", "qqq"), "2000-01-01", "2020-01-01", 20, "x")
    b = SliceIdentity(("QQQ", "SPY"), "2000-01-01", "2020-01-01", 20, "x")
    assert a.slice_id == b.slice_id


def test_identity_changes_with_each_leg_of_the_four_tuple():
    base = _ident()
    assert _ident(secs=SIX[:5]).slice_id != base.slice_id      # universe
    assert _ident(start="2001-01-01").slice_id != base.slice_id  # period
    assert _ident(hz=60).slice_id != base.slice_id             # horizon
    assert _ident(outcome="something else").slice_id != base.slice_id


# ── the refusal ────────────────────────────────────────────────────────────

def test_a_second_confirmation_on_a_consumed_slice_is_refused(tmp_path):
    reg = _reg(tmp_path)
    _consume_n9(reg)
    v = reg.check(_ident(), "CONFIRM", trial="N21")
    assert v["allowed"] is False
    assert v["prior_readers"] == ["N9"]
    assert "not an independent confirmation" in v["why"]


def test_claim_raises_so_the_verdict_cannot_be_ignored(tmp_path):
    reg = _reg(tmp_path)
    _consume_n9(reg)
    with pytest.raises(SliceRefusal, match="CONFIRM refused"):
        reg.claim(_ident(), "CONFIRM", trial="N21",
                  consumed_at="2026-08-17T00:00:00Z")


def test_the_shifted_window_evasion_is_caught(tmp_path):
    """Same six names, window nudged — a different slice_id, same data.

    This is the reason the register detects OVERLAP rather than comparing ids.
    """
    reg = _reg(tmp_path)
    _consume_n9(reg)
    shifted = _ident(start="1999-06-01")
    assert shifted.slice_id != _ident().slice_id
    assert reg.check(shifted, "CONFIRM", trial="N21")["allowed"] is False


def test_one_shared_security_is_enough_to_contaminate(tmp_path):
    """A confirmation contaminated on part of its universe is contaminated."""
    reg = _reg(tmp_path)
    _consume_n9(reg)
    mostly_new = _ident(secs=("EEM", "EFA", "TLT", "GLD", "XLV"))
    assert reg.check(mostly_new, "CONFIRM", trial="N21")["allowed"] is False


# ── what is deliberately allowed ───────────────────────────────────────────

def test_a_different_horizon_is_a_different_slice(tmp_path):
    reg = _reg(tmp_path)
    _consume_n9(reg)
    assert reg.check(_ident(hz=60), "CONFIRM", trial="N21")["allowed"] is True


def test_a_disjoint_period_is_a_different_slice(tmp_path):
    reg = _reg(tmp_path)
    _consume_n9(reg)
    later = _ident(start="2026-09-01", end="2027-09-01")
    assert reg.check(later, "CONFIRM", trial="N21")["allowed"] is True


def test_exploration_may_revisit_freely(tmp_path):
    """Only CONFIRM is refused; re-reading data is what exploring is."""
    reg = _reg(tmp_path)
    _consume_n9(reg)
    for purpose in ("EXPLORE", "FOREIGN", "REANALYSIS", "PAIRED"):
        assert reg.check(_ident(), purpose, trial="N21")["allowed"] is True


def test_a_declared_non_independent_confirm_is_allowed_but_stripped(tmp_path):
    """It may run. It may not be called confirmation."""
    reg = _reg(tmp_path)
    _consume_n9(reg)
    v = reg.check(_ident(), "CONFIRM", trial="N9B",
                  declared_non_independent=True)
    assert v["allowed"] is True
    assert v["may_claim_confirmation"] is False


def test_an_unknown_purpose_is_rejected_rather_than_treated_as_safe(tmp_path):
    with pytest.raises(ValueError, match="unknown purpose"):
        _reg(tmp_path).check(_ident(), "probably_fine", trial="N21")


# ── the ledger ─────────────────────────────────────────────────────────────

def test_the_register_is_append_only_and_survives_reload(tmp_path):
    reg = _reg(tmp_path)
    _consume_n9(reg)
    reg.claim(_ident(), "PAIRED", trial="N9B",
              consumed_at="2026-08-16T06:00:00Z",
              declared_non_independent=True)
    reloaded = _reg(tmp_path)
    assert [r.trial for r in reloaded.records] == ["N9", "N9B"]
    assert reloaded.check(_ident(), "CONFIRM", trial="N21")["allowed"] is False


def test_consumed_at_is_supplied_not_read_from_the_clock(tmp_path):
    """A register that stamps its own times cannot be replayed."""
    reg = _reg(tmp_path)
    reg.claim(_ident(), "EXPLORE", trial="N4",
              consumed_at="2026-08-16T00:00:00Z")
    line = json.loads((tmp_path / "slice_register.jsonl").read_text().strip())
    assert line["consumed_at"] == "2026-08-16T00:00:00Z"


def test_it_can_say_where_a_clean_confirmation_could_run(tmp_path):
    """Refusing is only useful alongside naming an unread slice."""
    reg = _reg(tmp_path)
    _consume_n9(reg)
    free = reg.unread_candidates(
        ["DIA", "XLV", "EEM", "EFA", "TLT", "GLD"], _ident())
    assert free == ["EEM", "EFA", "GLD", "TLT"]
    assert "DIA" not in free and "XLV" not in free


def test_non_independent_purposes_are_declared_in_one_place():
    """So a fifth purpose cannot leave a caller silently covering four."""
    assert set(NON_INDEPENDENT) == {"REANALYSIS", "PAIRED"}


def test_the_seeded_register_records_both_consumptions_of_the_slice():
    """The real ledger, not a fixture: N9 and N9B both read the six.

    If this ever reads one reader, the history has been rewritten.
    """
    from backend.services.research_gym.slice_register import SliceRegister as SR
    reg = SR()
    if not reg.records:                       # unseeded checkout
        pytest.skip("slice register not seeded in this checkout")
    readers = [r.trial for r in reg.prior_readers(_ident())]
    assert "N9" in readers and "N9B" in readers
    n9b = next(r for r in reg.records if r.trial == "N9B")
    assert n9b.purpose in NON_INDEPENDENT, \
        "N9B must not be recorded as an independent confirmation"


# ── a trial must be able to re-run its own analysis ────────────────────────

def test_a_trial_may_reread_the_slice_it_already_claimed(tmp_path):
    """Otherwise the only way to add a diagnostic is an escape hatch, and an
    escape hatch is what actually gets abused."""
    reg = _reg(tmp_path)
    ident = SliceIdentity(securities=("AAA", "BBB"), start="2006-01-01",
                          end="2026-01-01", outcome_horizon_days=20,
                          outcome_definition="drawdown vs buy-hold")
    reg.claim(ident, "CONFIRM", trial="N21", consumed_at="2026-08-16T00:00:00Z")
    again = reg.check(ident, "CONFIRM", trial="N21")
    assert again["allowed"] is True
    assert again.get("rerun_of_own_claim") is True
    assert "one consumption" in again["why"]


def test_a_DIFFERENT_trial_is_still_refused_after_that(tmp_path):
    """The property being protected. If this passed, the allowance would be a
    hole rather than a fix."""
    reg = _reg(tmp_path)
    ident = SliceIdentity(securities=("AAA", "BBB"), start="2006-01-01",
                          end="2026-01-01", outcome_horizon_days=20,
                          outcome_definition="drawdown vs buy-hold")
    reg.claim(ident, "CONFIRM", trial="N21", consumed_at="2026-08-16T00:00:00Z")
    other = reg.check(ident, "CONFIRM", trial="N22")
    assert other["allowed"] is False
    assert "N21" in other["why"]


def test_an_anonymous_rerun_is_not_a_rerun(tmp_path):
    """An empty trial name must not match every prior reader."""
    reg = _reg(tmp_path)
    ident = SliceIdentity(securities=("AAA",), start="2006-01-01",
                          end="2026-01-01", outcome_horizon_days=20,
                          outcome_definition="drawdown vs buy-hold")
    reg.claim(ident, "CONFIRM", trial="N21", consumed_at="2026-08-16T00:00:00Z")
    assert reg.check(ident, "CONFIRM", trial="")["allowed"] is False
