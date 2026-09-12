"""5c -- the TAQ empirical cost curve: known answers, and the refusals.

Spec: `docs/research_notes/2026-09-12/spec_cost_model.md` S4. Fixed panels,
exact arithmetic asserted, refusals asserted by `pytest.raises` -- the style of
`test_taq_calibration.py`. No network, no live data.

ONE DELIBERATE DEPARTURE FROM THE SPEC'S OWN ARITHMETIC. Spec S4 item 1 writes
the expected total as `1.0 + eta * 0.30 * sqrt(0.005)`, which drops the
basis-point conversion: `eta * sigma * sqrt(POV)` is a FRACTION of price, so in
bps it is `1e4 *` that. S1.4, the definitional section, has the `1e4` and is
what is implemented; this test asserts S1.4's arithmetic and says so here
rather than quietly matching a typo.
"""

from __future__ import annotations

import json
import math

import pytest

from backend.services import cost_curve as CC
from backend.services import cost_model as CM

FIXTURE_ROWS = [
    # effective_full_bps_median = 2.0 -> half spread exactly 1.0bp
    {"date": f"2026080{d}", "ticker": "KNOWN", "n_trades": 50_000,
     "full_bps": 2.0, "basis": "fixture"}
    for d in range(1, 10)
] + [
    {"date": f"202608{d:02d}", "ticker": "KNOWN", "n_trades": 50_000,
     "full_bps": 2.0, "basis": "fixture"}
    for d in range(10, 26)
]

FIXTURE_FIT = {
    "n": 100, "r2": 0.5, "loo_r2": 0.4, "residual_sigma_log": 0.45,
    "coefficients": {
        "intercept": {"estimate": 7.0, "std_error": 0.7},
        "log_dollar_volume_usd": {"estimate": -0.4, "std_error": 0.04},
        "log_price_usd": {"estimate": 0.08, "std_error": 0.04},
        "volatility_ann": {"estimate": 1.4, "std_error": 0.17},
    },
}


# --------------------------------------------------------------- spec S4.1

def test_a_1bp_half_spread_name_at_half_a_percent_participation():
    """SPEC S4 ITEM 1. Half spread 1.0bp, participation 0.5%, sigma_ann 0.30."""
    q = CC.taq_empirical_one_way("KNOWN", participation=0.005,
                                 volatility_ann=0.30, rows=FIXTURE_ROWS)
    assert isinstance(q, CC.CostQuote)
    assert q.spread_bps == pytest.approx(1.0)
    want_impact = 1e4 * CC.ETA_SQRT_IMPACT * 0.30 * math.sqrt(0.005)
    assert q.impact_bps == pytest.approx(want_impact, rel=1e-9)
    assert q.one_way_bps == pytest.approx(1.0 + want_impact, rel=1e-9)
    assert q.round_trip_bps == pytest.approx(2.0 * q.one_way_bps)
    assert q.provenance == CM.MEASURED_TAQ_EFFECTIVE


def test_eta_is_PINNED_and_matches_the_receipt_that_solved_it():
    """A re-calibration is a deliberate edit to a named test, never a drift --
    and the module constant and the receipt must not disagree, because the
    receipt is what a reader checks the number against."""
    assert CC.ETA_SQRT_IMPACT == 0.120620
    fit = json.loads(CC.REGRESSION_PATH.read_text(encoding="utf-8"))
    assert fit["eta_solve"]["eta"] == pytest.approx(CC.ETA_SQRT_IMPACT, abs=5e-7)
    # The solve closes: impact at 1% ADV plus the median half spread IS the
    # Frazzini-Israel-Moskowitz target the spec named.
    got = (CC.impact_bps(fit["eta_solve"]["volatility_ann_used"], 0.01)
           + fit["eta_solve"]["half_spread_subtracted_bps"])
    assert got == pytest.approx(fit["eta_solve"]["target_used_bps"], abs=0.01)


def test_the_impact_term_is_the_VENDORED_function_and_not_a_second_copy():
    from backend.strategy.vendor.impact import sqrt_impact
    fill = sqrt_impact(1.0, 1, 0.04, 1.0, 0.25, eta=CC.ETA_SQRT_IMPACT)
    assert CC.impact_bps(0.25, 0.04) == pytest.approx(1e4 * (fill - 1.0))


def test_zero_participation_is_zero_impact_not_a_refusal():
    q = CC.taq_empirical_one_way("KNOWN", participation=0.0,
                                 volatility_ann=0.30, rows=FIXTURE_ROWS)
    assert q.impact_bps == 0.0
    assert q.one_way_bps == pytest.approx(1.0)


def test_participation_without_volatility_REFUSES():
    """Charging zero impact for a missing sigma understates every large order
    in silence, which is the failure mode this whole module exists to stop."""
    with pytest.raises(CM.CostRefused, match="no volatility"):
        CC.taq_empirical_one_way("KNOWN", participation=0.05, rows=FIXTURE_ROWS)


# --------------------------------------------------------------- spec S4.2

def test_a_name_with_no_TAQ_row_falls_back_to_the_regression_and_SAYS_SO():
    """SPEC S4 ITEM 2. The provenance is never `MEASURED_*`, and the fit's own
    R2 / LOO R2 / residual sigma travel on the object."""
    q = CC.taq_empirical_one_way("ABSENT", participation=0.0,
                                 volatility_ann=0.30,
                                 dollar_volume_usd=5_000_000.0,
                                 price_usd=20.0, rows=FIXTURE_ROWS,
                                 fit=FIXTURE_FIT)
    assert q.provenance == CM.EXTRAPOLATED_REGRESSION
    assert q.provenance != CM.MEASURED_TAQ_EFFECTIVE
    row = q.as_row()
    assert row["regression_r2"] == 0.5
    assert row["regression_loo_r2"] == 0.4
    assert row["regression_residual_sigma_log"] == 0.45
    assert any("extrapolated" in n for n in q.notes)
    want = math.exp(7.0 - 0.4 * math.log(5_000_000.0) + 0.08 * math.log(20.0)
                    + 1.4 * 0.30)
    assert q.spread_bps == pytest.approx(want, rel=1e-12)


def test_the_regression_falls_with_dollar_volume_and_rises_with_volatility():
    """The signs the five-band precedent already measured (148.9bp at
    $100k-1m/day down to 6.7bp at $50m+/day). A fit whose liquidity slope had
    the wrong sign would still have an R2."""
    b0, b1, b2, b3 = CC.regression_coefficients()
    assert b1 < 0, "more dollar volume must not cost MORE"
    assert b3 > 0, "more volatility must not cost LESS"


# --------------------------------------------------------------- spec S4.3

def test_no_TAQ_row_AND_a_missing_regression_input_gives_a_BAND_not_a_number():
    """SPEC S4 ITEM 3. The return is a `CostBand`, which has no `.value` and no
    `__float__` -- a test that could `float()` the result would itself prove
    the refusal had been defeated."""
    band = CC.taq_empirical_one_way("ABSENT", participation=0.0,
                                    dollar_volume_usd=5_000_000.0,
                                    price_usd=20.0, rows=FIXTURE_ROWS)
    assert isinstance(band, CM.CostBand)
    assert band.provenance == CM.DECLARED_CONSERVATIVE
    assert not hasattr(band, "value")
    with pytest.raises(TypeError):
        float(band)
    assert "volatility_ann" in band.reason
    assert "NOT an average name" in band.reason


def test_a_thinly_printed_name_is_sampled_not_measured():
    rows = [{"date": "20260801", "ticker": "THIN", "n_trades": 10,
             "full_bps": 9.0, "basis": "fixture"}]
    with pytest.raises(CM.CostRefused, match="trades"):
        CC.reading_for(rows, "THIN")


def test_too_few_days_does_not_resolve_and_does_not_become_a_measurement():
    rows = [{"date": f"2026080{d}", "ticker": "SHORT", "n_trades": 50_000,
             "full_bps": 4.0, "basis": "fixture"} for d in range(1, 5)]
    reading = CC.reading_for(rows, "SHORT")
    assert reading.resolves is False
    band = CC.taq_empirical_one_way("SHORT", participation=0.0, rows=rows)
    assert isinstance(band, CM.CostBand)


# ------------------------------------------------------ panel and provenance

def test_the_half_spread_is_HALF_and_the_aggregation_is_median_of_medians():
    rows = [{"date": f"2026080{d}", "ticker": "X", "n_trades": 50_000,
             "full_bps": v, "basis": ""}
            for d, v in enumerate([1.0, 2.0, 3.0, 100.0] * 5, start=1)]
    r = CC.reading_for(rows, "X")
    assert r.full_bps == pytest.approx(2.5)      # median of the 20 dailies
    assert r.half_bps == pytest.approx(1.25)


def test_the_real_panel_reproduces_its_own_meta_headline():
    """4,224 rows, 184 names, every one resolving at MIN_DAYS=15.

    The meta's headline one-way median is 1.076bp; THIS reader's
    median-of-daily-medians over all 184 names is 1.07223. The two differ in
    the fourth significant figure because they aggregate slightly differently,
    not because they describe different data -- and the number pinned here is
    the one this module actually charges, with the meta's quoted beside it so
    a reader can see the gap is 0.35% and not 35%.
    """
    import statistics
    rows = CC.panel()
    assert len(rows) == 4_224
    names = {r["ticker"] for r in rows}
    assert len(names) == 184
    readings = [CC.reading_for(rows, t) for t in names]
    assert all(r.resolves for r in readings)
    ours = statistics.median([r.half_bps for r in readings])
    assert ours == pytest.approx(1.07223, abs=1e-4)
    meta_headline = 1.076
    assert abs(ours / meta_headline - 1.0) < 0.005


def test_the_DEFERRED_caveat_travels_on_every_measured_quote():
    q = CC.taq_empirical_one_way("KNOWN", participation=0.0, rows=FIXTURE_ROWS)
    assert "v1_unfiltered" in q.basis
    assert any("DEFERRED" in n for n in q.notes)


def test_the_conventions_range_is_DERIVED_from_the_probe_not_asserted():
    """And it is NOT one-signed: the spec said strict conventions raise the
    ratio, the probe says `no_midpoint` raises WEC 2.98x while
    `round_lots_only` lowers MSFT to 0.47x."""
    lo, hi = CC.convention_multiplier_range()
    assert lo < 1.0 < hi
    assert hi > 2.5, "the probe's widest upward move must not be rounded away"
    out = CC.survives_convention_sensitivity(lambda bps: bps < 1.0, 1.0)
    assert out["survives"] is False
    assert out["verdict"] == CM.COST_MODEL_SENSITIVE
    assert CC.survives_convention_sensitivity(
        lambda bps: bps < 1e6, 1.0)["survives"] is True


def test_the_provenance_mix_is_the_reportable_fact():
    measured = CC.taq_empirical_one_way("KNOWN", participation=0.0,
                                        rows=FIXTURE_ROWS)
    extrap = CC.taq_empirical_one_way("ABSENT", participation=0.0,
                                      volatility_ann=0.3,
                                      dollar_volume_usd=1e7, price_usd=30.0,
                                      rows=FIXTURE_ROWS, fit=FIXTURE_FIT)
    mix = CC.curve_provenance_mix([measured] * 4 + [extrap])
    assert mix["counts"] == {CM.EXTRAPOLATED_REGRESSION: 1,
                             CM.MEASURED_TAQ_EFFECTIVE: 4}
    assert mix["mix"][CM.MEASURED_TAQ_EFFECTIVE] == 0.8


def test_a_negative_rate_is_not_a_cost():
    with pytest.raises(CM.CostRefused):
        CC.CostQuote(spread_bps=-1.0, impact_bps=0.0,
                     provenance=CM.MEASURED_TAQ_EFFECTIVE)


# ------------------------------------------------------------ retail regime

def test_the_retail_curve_REFUSES_until_D2s_fill_receipt_exists(tmp_path):
    """SPEC S1.5. Falling back to the institutional curve would understate
    retail cost BY CONSTRUCTION, so the stub refuses and names its blocker."""
    st = CC.retail_paper_status(tmp_path)
    assert st["state"] == "STUB_REFUSES"
    assert st["available"] is False
    assert "D2" in st["blocked_on"]
    with pytest.raises(CM.CostRefused, match="no fill-quality receipt"):
        CC.retail_paper_one_way(directory=tmp_path)


def test_the_retail_stand_in_is_a_BAND_and_cannot_be_below_the_NBBO(tmp_path):
    band = CC.retail_paper_band(tmp_path)
    assert isinstance(band, CM.CostBand)
    assert band.low.value == CC.RETAIL_FLOOR_ONE_WAY_BPS == 1.076
    assert band.high.value == CC.RETAIL_CEILING_ONE_WAY_BPS == 25.0
    assert band.provenance == CM.DECLARED_CONSERVATIVE


def test_the_retail_curve_is_declared_and_MEASURED_RETAIL_PAPER_is_unreachable():
    """Nothing on disk may carry the measured-retail provenance yet."""
    assert CM.MEASURED_RETAIL_PAPER in CM._PROVENANCES
    assert CC.retail_paper_status()["n_fill_quality_receipts"] == 0


# ------------------------------------------------------------ curve floors

def test_the_curve_floor_is_strictly_positive_so_zero_cost_still_refuses():
    assert CC.curve_floor_one_way_bps("taq_empirical") > 0
    assert CC.curve_floor_one_way_bps("retail_paper") > 0


def test_asking_flat_for_a_curve_floor_REFUSES():
    """'flat' has no curve: answering would silently replace a DECLARED rate
    with a measured one."""
    with pytest.raises(CC.CurveError, match="no curve floor"):
        CC.curve_floor_one_way_bps("flat")
    with pytest.raises(CC.CurveError, match="unknown cost curve"):
        CC.curve_floor_one_way_bps("free_lunch")


def test_a_missing_regression_receipt_REFUSES_rather_than_fitting_itself(tmp_path):
    CC.load_regression.cache_clear()
    try:
        with pytest.raises(CM.CostRefused, match="cost_curve_fit"):
            CC.load_regression(str(tmp_path / "nope.json"))
    finally:
        CC.load_regression.cache_clear()


def test_a_missing_panel_does_not_fall_back_to_a_flat_rate(tmp_path):
    with pytest.raises(CM.CostRefused, match="does not fall back"):
        CC.load_effective_panel(tmp_path / "nope.jsonl")


def test_the_vectorised_twin_agrees_with_the_scalar_and_NaNs_the_unusable():
    import numpy as np
    dv = np.array([5e6, 1e8, -1.0, np.nan])
    px = np.array([20.0, 300.0, 10.0, 10.0])
    vl = np.array([0.3, 0.25, 0.3, 0.3])
    got = CC.regression_half_spread_bps_array(dv, px, vl, FIXTURE_FIT)
    assert got[0] == pytest.approx(
        CC.regression_half_spread_bps(5e6, 20.0, 0.3, FIXTURE_FIT))
    assert got[1] == pytest.approx(
        CC.regression_half_spread_bps(1e8, 300.0, 0.25, FIXTURE_FIT))
    assert np.isnan(got[2]) and np.isnan(got[3])
