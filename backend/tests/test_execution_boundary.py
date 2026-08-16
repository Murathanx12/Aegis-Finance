"""The gap defect is about when information ARRIVES, not how long the horizon is.

Getting the axis wrong in the strict direction is not free: a rule that flagged
every one-day close-to-close outcome would have condemned all 150 regime-tensor
rows, which are sound, and would then have been switched off.
"""

from __future__ import annotations

import pytest

from backend.services.execution_boundary import (AT_OR_BEFORE_CLOSE,
                                                 DURING_SESSION, NotReportable,
                                                 OUTSIDE_SESSION,
                                                 assert_reportable,
                                                 gap_is_lost,
                                                 tradable_fraction)


# ── the axis ───────────────────────────────────────────────────────────────
def test_a_close_decision_earns_the_overnight_gap():
    """A regime signal from Monday's close, acted on at Monday's close, holds
    through Tuesday's open. That gap belongs to the position."""
    r = assert_reportable(event_family="vix_regime", arrival=AT_OR_BEFORE_CLOSE,
                          gross=0.01, tradable=None)
    assert r["reportable"] and r["fraction"] == 1.0
    assert "belongs to the position" in r["why"]


def test_an_after_hours_announcement_does_not():
    with pytest.raises(NotReportable, match="may not be reported"):
        assert_reportable(event_family="eps", arrival=OUTSIDE_SESSION,
                          gross=0.0424, tradable=None)


def test_with_the_tradable_half_supplied_it_reports():
    r = assert_reportable(event_family="eps", arrival=OUTSIDE_SESSION,
                          gross=0.0424, tradable=0.0055)
    assert r["reportable"]
    assert r["lost_to_gap"] == pytest.approx(0.87, abs=0.01)


def test_an_undeclared_arrival_is_refused_not_defaulted_to_harmless():
    """Defaulting to the benign case is how an untradable result gets reported
    as an edge."""
    with pytest.raises(NotReportable, match="not one of"):
        gap_is_lost("whenever")


def test_intraday_arrival_is_not_the_lost_case():
    assert not gap_is_lost(DURING_SESSION)
    assert not gap_is_lost(AT_OR_BEFORE_CLOSE)
    assert gap_is_lost(OUTSIDE_SESSION)


# ── the ratio refusal, generalised ────────────────────────────────────────
def test_a_share_of_a_gross_below_its_own_mde_is_refused():
    """The rule was learned on `1 - tradable/gross` printing 253% for a gross
    of -0.05pp. It now covers every ratio here, lift included."""
    r = tradable_fraction(-0.0005, 0.0008, gross_mde=0.0037)
    assert r["fraction"] is None
    assert "ratio to noise" in r["why"]


def test_a_share_of_a_resolvable_gross_is_reported():
    r = tradable_fraction(0.0424, 0.0055, gross_mde=0.0025)
    assert r["fraction"] == pytest.approx(0.13, abs=0.01)
    assert "87%" in r["why"]


def test_zero_gross_does_not_divide_by_zero():
    assert tradable_fraction(0.0, 0.01)["fraction"] is None


def test_the_g4_numbers_round_trip():
    """The published figures, pinned so a later refactor cannot quietly move
    them: C-D was 4.24pp close-to-close and 0.55pp open-to-close."""
    r = tradable_fraction(0.0424, 0.0055)
    assert 0.86 <= r["lost_to_gap"] <= 0.88
