"""What the TAQ panel is allowed to retire, and what it is not.

The band retires ONE NAME AT A TIME. Every test here is aimed at the failure
where an entitlement — a fact about a subscription — quietly becomes a cost for
a name nobody measured.
"""

from __future__ import annotations

import json

import pytest

from backend.services import cost_model as CM
from backend.services import taq_calibration as TC


# ── fixtures: a small panel with a known answer ────────────────────────────
def _rows(ticker, median_bps, *, mid=230.0, days=22, quotes=500_000,
          jitter=0.0):
    return [{"date": f"2026-07-{d:02d}", "ticker": ticker, "n_quotes": quotes,
             "mean_bps": median_bps, "median_bps": median_bps + jitter * (d % 3),
             "mid": mid}
            for d in range(1, days + 1)]


@pytest.fixture()
def panel():
    # AAPL: ~1bp full spread at $230 -> one tick is 0.43bp, so ~2.2 ticks wide.
    # PLUG: wide and cheap-priced -> its own tick floor is large.
    # THIN: covered on too few days to resolve.
    return (_rows("AAPL", 0.97, mid=230.0)
            + _rows("PLUG", 38.0, mid=2.10)
            + _rows("THIN", 12.0, mid=50.0, days=4))


# ── the panel refuses rather than guesses ──────────────────────────────────
def test_a_missing_panel_refuses_and_says_the_band_does_not_retire(tmp_path):
    with pytest.raises(TC.TaqRefused, match="does NOT retire"):
        TC.load_panel(tmp_path / "nope.csv")


def test_schema_drift_is_refused_not_mapped_by_guesswork(tmp_path):
    p = tmp_path / "panel.csv"
    p.write_text("date,ticker,n_quotes,spread_bps,mid_price_mean\n"
                 "2026-07-01,AAPL,1,1.0,230.0\n", encoding="utf-8")
    with pytest.raises(TC.TaqRefused, match="schema drift"):
        TC.load_panel(p)


def test_an_empty_panel_is_refused_because_it_reads_as_nothing_to_retire(
        tmp_path):
    p = tmp_path / "panel.csv"
    p.write_text(",".join(sorted(TC.REQUIRED_COLUMNS)) + "\n", encoding="utf-8")
    with pytest.raises(TC.TaqRefused, match="empty"):
        TC.load_panel(p)


def test_metadata_is_required_because_units_must_not_be_folklore(tmp_path):
    p = tmp_path / "panel.csv"
    p.write_text("x\n", encoding="utf-8")
    with pytest.raises(TC.TaqRefused, match="metadata"):
        TC.load_meta(p)


def test_a_real_panel_round_trips(tmp_path):
    p = tmp_path / "panel.csv"
    p.write_text(
        "date,ticker,sym_root,sym_suffix,n_quotes,quoted_spread_bps_mean,"
        "quoted_spread_bps_median,mid_price_mean\n"
        "2026-07-01,AAPL,AAPL,,560000,1.02,0.97,230.11\n", encoding="utf-8")
    (tmp_path / "panel.meta.json").write_text(json.dumps({"measure": "quoted"}),
                                              encoding="utf-8")
    rows = TC.load_panel(p)
    assert rows[0]["median_bps"] == 0.97 and rows[0]["mid"] == 230.11
    assert TC.load_meta(p)["measure"] == "quoted"


# ── one name at a time ─────────────────────────────────────────────────────
def test_an_uncovered_name_keeps_its_band_and_absent_is_not_cheap(panel):
    out = TC.cost_for(panel, "NVDA")
    assert out["band_retired"] is False
    assert out["branch"] == CM.DECLARED_CONSERVATIVE
    assert isinstance(out["band"], CM.CostBand)
    assert "not in the TAQ panel" in out["reason"]


def test_thin_coverage_does_not_retire_a_band(panel):
    """A name sampled on four days has been sampled, not measured."""
    out = TC.cost_for(panel, "THIN")
    assert out["band_retired"] is False
    assert "MIN_DAYS" in out["reason"] or "usable day" in out["reason"]


def test_a_covered_name_retires_its_band_with_a_measured_provenance(panel):
    out = TC.cost_for(panel, "AAPL")
    assert out["band_retired"] is True
    cost = out["cost"]
    assert cost.provenance == CM.MEASURED_TAQ_QUOTED and cost.measured
    assert cost.value == pytest.approx(0.485, abs=1e-9), (
        "the panel is a FULL spread; the one-way rate is half of it")


def test_the_declared_band_over_charged_the_megacap_it_was_declared_for(panel):
    """The point of the whole exercise, stated as a comparison.

    Order 18 declared 1-5bp one-way for names AGK could not resolve. AAPL's
    measured one-way rate is BELOW the low end of that band — so the band was
    conservative in the intended direction, and by more than its own width.
    """
    cost = TC.cost_for(panel, "AAPL")["cost"]
    lo, hi = CM.LIQUID_BAND_ONE_WAY_BPS
    assert cost.value < lo < hi


# ── the quantisation floor, which is not the variance floor ────────────────
def test_the_tick_floor_is_derived_from_price_not_declared():
    assert TC.tick_floor_bps(100.0) == pytest.approx(1.0)
    assert TC.tick_floor_bps(230.0) == pytest.approx(0.4348, abs=1e-3)
    with pytest.raises(TC.TaqRefused):
        TC.tick_floor_bps(0.0)


def test_a_name_at_the_tick_floor_is_FLAGGED_not_refused():
    """The distinction from AGK, and the reason it is treated differently.

    AGK's floor is a VARIANCE floor: below it the estimator is blind and the
    reading carries no information about the truth, so the estimate is absent.
    A tick floor is QUANTISATION: the reading is a hard UPPER bound, the sign of
    the error is known, and an upper bound on a cost is usable — a conservative
    repricing wants exactly that. So the name still resolves; it is annotated.
    """
    # $10 stock: one tick = 10bp. A reading of 10bp IS the tick.
    at_floor = _rows("TICKY", 10.0, mid=10.0)
    r = TC.reading_for(at_floor, "TICKY")
    assert r.resolves is True and r.at_tick_floor is True
    assert any("UPPER bound" in n for n in r.notes)
    assert TC.one_way_cost(r).value == pytest.approx(5.0)


def test_a_name_well_above_its_tick_floor_is_not_flagged(panel):
    r = TC.reading_for(panel, "AAPL")
    assert r.at_tick_floor is False
    assert r.ticks_wide == pytest.approx(0.97 / TC.tick_floor_bps(230.0),
                                         rel=1e-6)


# ── the central estimate is robust by construction ─────────────────────────
def test_the_central_estimate_is_a_median_of_daily_medians(panel):
    """Not a pooled mean over quotes: pooling weights a name by how chatty its
    tape was, so one wide heavily-quoted afternoon would set the number."""
    rows = _rows("WOBBLY", 5.0, mid=100.0)
    rows[0]["median_bps"] = 500.0          # one catastrophic day
    rows[0]["n_quotes"] = 50_000_000       # ...that dominates any pooled mean
    r = TC.reading_for(rows, "WOBBLY")
    assert r.full_bps == pytest.approx(5.0)
    assert r.full_bps_day_high == 500.0, "the outlier is REPORTED, not hidden"


def test_days_below_the_quote_gate_are_dropped_and_the_drop_is_recorded():
    rows = _rows("SPARSE", 4.0, mid=100.0)
    rows[0]["n_quotes"] = 3
    r = TC.reading_for(rows, "SPARSE")
    assert r.n_days == len(rows) - 1
    assert any("below" in n for n in r.notes)


def test_a_name_with_no_usable_day_refuses_rather_than_retiring():
    rows = _rows("GHOST", 4.0, mid=100.0, quotes=10)
    with pytest.raises(TC.TaqRefused, match="thinly quoted"):
        TC.reading_for(rows, "GHOST")


# ── the bias ledger cannot be quietly halved ───────────────────────────────
def test_the_bias_ledger_carries_signs_and_they_do_not_agree():
    ledger = TC.bias_ledger()
    assert len(ledger) == 3
    assert {b["sign"] for b in ledger} == {"OVER", "UNDER"}
    assert all(b["resolvable_by"] for b in ledger)


def test_the_net_bias_sign_is_NOT_ESTABLISHED_rather_than_the_famous_one():
    """"Quoted over-states, so we are being conservative" is the sentence this
    guards against: it is true of one of the three biases and the other two
    point the other way."""
    assert TC.net_bias_sign() == "NOT_ESTABLISHED"


def test_the_sensitivity_SPLITS_two_claims_that_look_like_one_claim():
    """The test that changed what this work is allowed to report.

    Both of these sound like "TAQ shows the megacap band over-charges", and at
    the declared 4x factor only one of them is established:

        "below the band's LOW end (1bp)"   -> 0.485 x 4 = 1.94  FAILS
        "below the band's HIGH end (5bp)"  -> 0.485 x 4 = 1.94  HOLDS

    So what the panel establishes is that the TOP of the declared band
    over-charges a megacap. Whether the truth is under the BOTTOM of the band
    is a point-estimate claim, and the point estimate has an unresolved bias
    sign. Lowering the factor to rescue the stronger sentence is the move this
    factor was declared in advance to prevent.
    """
    lo, hi = CM.LIQUID_BAND_ONE_WAY_BPS
    weak = TC.survives_bias_sensitivity(0.485, hi)
    strong = TC.survives_bias_sensitivity(0.485, lo)
    assert weak["survives"] is True
    assert strong["survives"] is False
    assert strong["breaks_at_factor"] == pytest.approx(1.0 / 0.485, rel=1e-6)


def test_the_agk_overcharge_finding_survives_the_declared_factor():
    """The headline that DOES earn its statement.

    AGK read megacaps at 15-20bp full spread; TAQ measures 0.97bp full. Even
    with the TAQ number inflated fourfold the gap is still severalfold, so the
    over-charge conclusion does not depend on resolving the bias sign.
    """
    s = TC.survives_bias_sensitivity(0.485, 15.0 / 2)
    assert s["survives"] is True
    assert s["breaks_at_factor"] > 4.0


def test_a_sensitivity_factor_below_one_tests_nothing_and_is_refused():
    with pytest.raises(TC.TaqRefused, match="tests nothing"):
        TC.survives_bias_sensitivity(1.0, 2.0, factor=0.5)


# ── the calibration knows the segment it was measured on ───────────────────
def test_calibration_refuses_when_the_two_instruments_see_disjoint_segments(
        panel):
    """A refusal that is a FINDING: AGK resolves the wide end, TAQ resolves
    everything, and if no name has both then the segmentation was the right
    call and there is nothing to calibrate."""
    with pytest.raises(TC.TaqRefused, match="disjoint segments"):
        TC.calibrate_against_agk(panel, {"NOT_IN_PANEL": 20.0})


def test_calibration_measures_the_overlap_and_names_its_range(panel):
    cal = TC.calibrate_against_agk(panel, {"PLUG": 38.0})
    assert cal["n_pairs"] == 1
    # AGK 38bp one-way vs TAQ 19bp one-way (38bp full, halved) -> ratio 2.
    assert cal["ratio_median"] == pytest.approx(2.0)
    assert cal["valid_taq_one_way_range_bps"] == [19.0, 19.0]
    assert "not applicable" in cal["scope"]


def test_the_calibration_refuses_outside_the_range_it_was_measured_on(panel):
    """§60 wearing cost-model clothes: the overlap is drawn entirely from the
    wide end, so carrying its ratio to a megacap is the original error again."""
    cal = TC.calibrate_against_agk(panel, {"PLUG": 38.0})
    assert TC.apply_calibration(cal, 38.0) == pytest.approx(19.0)
    with pytest.raises(TC.TaqRefused, match="outside the range"):
        TC.apply_calibration(cal, 2.0)


# ── the split is the reportable fact ───────────────────────────────────────
def test_the_retirement_summary_reports_what_did_NOT_retire(panel):
    rows = [TC.cost_for(panel, t) for t in ("AAPL", "PLUG", "THIN", "NVDA")]
    s = TC.summarise_retirement(rows)
    assert s["n_names"] == 4 and s["n_band_retired"] == 2
    assert s["n_band_stays"] == 2 and s["fraction_retired"] == 0.5
    assert s["net_bias_sign"] == "NOT_ESTABLISHED"


def test_an_empty_retirement_summary_is_refused():
    with pytest.raises(TC.TaqRefused, match="nothing needed retiring"):
        TC.summarise_retirement([])
