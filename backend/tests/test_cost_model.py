"""The cost ruling's contract: a declared band cannot become a number.

Every test here is aimed at a failure that produces a REPORTABLE result rather
than an error — a band collapsed to its convenient end, a declared cost read as
a measurement, a floor value charged as a spread. None of those raise anything
by default; they all just make a verdict appear.
"""

from __future__ import annotations

import math
import random

import pytest

from backend.services import cost_model as CM
from backend.services import spread_estimators as SE


def _bars(n=250, spread=0.0, sigma=0.02, seed=7, ticks=60):
    """Synthetic OHLC with a KNOWN spread — the same construction Track R used
    to find the floor, reused so the two agree by build rather than by claim."""
    rng = random.Random(seed)
    step = sigma / math.sqrt(ticks)
    p = 100.0
    o, h, lo, c = [], [], [], []
    for _ in range(n):
        px = []
        for _ in range(ticks):
            p *= math.exp(rng.gauss(0.0, step))
            # A trade prints at the bid or the ask, never at the mid.
            px.append(p * (1.0 + (spread / 2.0) * rng.choice((-1.0, 1.0))))
        o.append(px[0])
        h.append(max(px))
        lo.append(min(px))
        c.append(px[-1])
    return o, h, lo, c


# ── the unit lives in the type ─────────────────────────────────────────────
def test_a_cost_without_provenance_is_refused():
    with pytest.raises(CM.CostRefused, match="provenance"):
        CM.OneWayBps(2.0, "looks_about_right")


def test_a_negative_cost_is_refused_because_it_pays_the_book_to_trade():
    with pytest.raises(CM.CostRefused, match="not a cost"):
        CM.OneWayBps(-1.0, CM.MEASURED_AGK)


def test_declared_is_not_measured_and_the_object_knows_which():
    assert CM.OneWayBps(2.0, CM.MEASURED_AGK).measured is True
    assert CM.OneWayBps(2.0, CM.DECLARED_CONSERVATIVE).measured is False


# ── the band is not a number ───────────────────────────────────────────────
def test_a_band_has_no_value_and_cannot_be_floated():
    """The property that makes it a band. If `float(band)` worked, every
    downstream arithmetic site would silently pick one."""
    band = CM.declared_liquid_band()
    assert not hasattr(band, "value")
    with pytest.raises(TypeError):
        float(band)


def test_picking_an_end_of_the_band_is_a_named_refusal():
    """Kept in the obvious place so its absence cannot read as an oversight
    to the next person, who would helpfully add it."""
    with pytest.raises(CM.CostRefused, match="COST_MODEL_SENSITIVE"):
        CM.resolve_band_by_picking(CM.declared_liquid_band(), end="low")


def test_an_inverted_band_is_refused():
    lo = CM.OneWayBps(5.0, CM.DECLARED_CONSERVATIVE)
    hi = CM.OneWayBps(1.0, CM.DECLARED_CONSERVATIVE)
    with pytest.raises(CM.CostRefused, match="inverted"):
        CM.CostBand(low=lo, high=hi, reason="")


def test_a_band_mixing_measured_and_declared_ends_is_refused():
    lo = CM.OneWayBps(1.0, CM.MEASURED_AGK)
    hi = CM.OneWayBps(5.0, CM.DECLARED_CONSERVATIVE)
    with pytest.raises(CM.CostRefused, match="two different claims"):
        CM.CostBand(low=lo, high=hi, reason="")


# ── the verdict rule, which is the whole ruling ────────────────────────────
def test_a_verdict_that_survives_both_ends_is_a_verdict():
    band = CM.declared_liquid_band()
    out = CM.verdict_across_band(lambda bps: "SURVIVES", band)
    assert out["verdict"] == "SURVIVES"
    assert out["cost_model_sensitive"] is False
    assert out["evaluated_at_bps"] == [1.0, 5.0]


def test_a_verdict_that_FLIPS_inside_the_band_is_COST_MODEL_SENSITIVE():
    """The case the ruling exists for.

    A strategy earning 3bp/turn survives at a 1bp cost and dies at 5bp. Neither
    answer is wrong; the point is that the DATA cannot choose between them, and
    reporting either one as the verdict would be reporting the band's endpoint
    as a measurement.
    """
    band = CM.declared_liquid_band()
    out = CM.verdict_across_band(lambda bps: "SURVIVES" if bps < 3.0 else "DIES",
                                 band)
    assert out["verdict"] == CM.COST_MODEL_SENSITIVE
    assert out["cost_model_sensitive"] is True
    assert out["verdict_at_low"] == "SURVIVES"
    assert out["verdict_at_high"] == "DIES"


def test_a_measured_cost_is_evaluated_once_and_keeps_its_provenance():
    cost = CM.OneWayBps(37.0, CM.MEASURED_AGK)
    out = CM.verdict_across_band(lambda bps: bps > 20.0, cost)
    assert out["verdict"] is True
    assert out["cost_model_sensitive"] is False
    assert out["provenance"] == CM.MEASURED_AGK
    assert out["evaluated_at_bps"] == [37.0]


def test_a_bare_float_cannot_price_a_verdict():
    """A float carries no provenance, so a declared number and a measured one
    become the same object one call downstream — which is the defect."""
    with pytest.raises(CM.CostRefused, match="raw float"):
        CM.verdict_across_band(lambda bps: bps > 3.0, 5.0)


# ── segmentation: which branch a real name falls into ──────────────────────
@pytest.mark.parametrize("spread_bps,expect_branch", [
    (2.0, CM.DECLARED_CONSERVATIVE),    # a megacap: far below AGK's floor
    (400.0, CM.MEASURED_AGK),           # a genuinely illiquid name
])
def test_the_branch_follows_the_estimator_s_own_floor(spread_bps, expect_branch):
    pytest.importorskip("bidask")
    o, h, lo, c = _bars(spread=spread_bps / 1e4)
    out = CM.cost_for_bars(o, h, lo, c, label="T")
    assert out["branch"] == expect_branch
    # And exactly one of the two keys is present — never both, never a float.
    assert ("cost" in out) != ("band" in out)


def test_an_unresolvable_name_gets_a_band_and_NOT_the_floor_value():
    """The specific error the ruling names: the floor is ~23-49bp and a
    megacap's true cost is 1-2bp, so charging the floor is a 10x over-charge
    that looks exactly like a strategy failing to clear costs."""
    pytest.importorskip("bidask")
    o, h, lo, c = _bars(spread=2.0 / 1e4)
    out = CM.cost_for_bars(o, h, lo, c)
    assert "cost" not in out
    band = out["band"]
    floor_bps = out["floor_diagnostic"]["floor"]["floor_full_spread_bps"]
    assert band.high.value < floor_bps, (
        "the declared band must sit BELOW the floor it replaces, or it is just "
        "the floor with a different label")
    assert band.provenance == CM.DECLARED_CONSERVATIVE


# ── TAQ: the check that ran ────────────────────────────────────────────────
def test_the_taq_refusal_was_discharged_by_running_the_check_not_by_waiting():
    """This test used to assert a refusal reading "nobody has tried".

    It is inverted deliberately, and the inversion is the finding: the WRDS
    entitlement record listed TAQ as absent, the standing lesson said a
    catalogue read is not an entitlement check, the check ran on 2026-08-18 and
    returned entitled. A refusal grounded in NOT-RUN is discharged by running,
    which is the whole reason it was worded that way rather than as "we do not
    have TAQ".
    """
    assert CM.TAQ_ENTITLEMENT == "VERIFIED_2026-08-18"
    assert CM.MEASURED_TAQ_QUOTED in CM._PROVENANCES


def test_entitlement_alone_retires_no_band():
    """The distinction the flip above is most likely to erase.

    Entitlement is a fact about a subscription. A retired band is a fact about
    a NAME, and it needs a measurement of that name. A verified entitlement with
    no panel must still refuse.
    """
    from backend.services import taq_calibration as TC
    with pytest.raises(TC.TaqRefused, match="no TAQ panel"):
        TC.load_panel(path="does-not-exist.csv")


def test_quoted_and_effective_taq_are_different_provenances():
    """A quoted spread and an effective spread are different quantities, and
    the name is the only thing still carrying that distinction three call sites
    downstream. Both count as measured; neither is the other."""
    assert CM.MEASURED_TAQ != CM.MEASURED_TAQ_QUOTED
    assert CM.OneWayBps(1.0, CM.MEASURED_TAQ_QUOTED).measured


# ── the split is the reportable fact ───────────────────────────────────────
def test_the_segmentation_summary_reports_the_declared_fraction():
    rows = ([{"branch": CM.MEASURED_AGK}] * 3
            + [{"branch": CM.DECLARED_CONSERVATIVE}] * 7)
    s = CM.summarise_segmentation(rows)
    assert s["n_names"] == 10 and s["fraction_declared"] == 0.7
    assert s["taq_entitlement"] == CM.TAQ_ENTITLEMENT


def test_an_empty_segmentation_is_refused_not_reported_as_full_coverage():
    with pytest.raises(CM.CostRefused, match="empty segmentation"):
        CM.summarise_segmentation([])


# ── the convention this module inherits ────────────────────────────────────
def test_the_one_way_rate_is_half_the_full_spread_end_to_end():
    """Restated here because the two modules must not drift: the panel charges
    `turn * rate` where `turn = sum(|dw|)` counts both legs."""
    est = SE.SpreadEstimate(value=0.0020, convention=SE.CONVENTION_FULL_SPREAD,
                            estimator="t", n_obs=100)
    assert est.as_one_way_bps() == pytest.approx(10.0)
    assert est.as_full_spread_bps() == pytest.approx(20.0)
