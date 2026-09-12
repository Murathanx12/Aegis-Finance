"""E4: ADWIN has to fire where a change was planted, and stay quiet where none was.

The two failure modes are opposite and both silent. A detector that never fires
makes every refit policy look identical and costs nothing to ship; a detector
that fires constantly makes the ADWIN arm the fixed arm under another name. So
both are asserted from the same runs: the planted step must be found inside a
bounded number of observations, and 2,000 stationary steps must produce zero
alarms.

The sharpest thing in here is `test_an_unscaled_error_stream_never_fires`. It
pins a real measurement from this build: a clean 0.008 -> 0.052 step in mean
absolute error produced ZERO detections, because ADWIN's bound carries an
additive `2/(3m) ln(2/delta')` term that does not scale with the data, and at
that magnitude the term alone dwarfs the jump. The same step scaled into [0, 1]
fires 55 observations later. A future reader who "simplifies away" `to_unit`
gets a detector that is silent rather than wrong, which is the worse of the two
and would never show up as a failing assertion anywhere else.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import adwin as ad                            # noqa: E402
from scripts import night_e4_adwin_refit as e4                      # noqa: E402


# ---------------------------------------------------------------------------
# the detector
# ---------------------------------------------------------------------------
def test_the_window_mean_and_width_are_exact():
    d = ad.ADWIN()
    xs = [0.2, 0.4, 0.6, 0.8]
    for x in xs:
        d.update(x)
    assert d.width == 4
    assert d.mean == pytest.approx(sum(xs) / 4)


def test_bucket_compression_keeps_the_width_exact_over_a_long_stream():
    d = ad.ADWIN(delta=1e-12)              # effectively never cuts
    rng = np.random.default_rng(0)
    vals = [float(np.clip(rng.normal(0.5, 0.05), 0, 1)) for _ in range(1000)]
    for v in vals:
        d.update(v)
    assert d.width == 1000, "compression lost observations"
    assert d.mean == pytest.approx(float(np.mean(vals)), abs=1e-9)


def test_it_fires_after_a_planted_change_and_not_before():
    stream = e4.synthetic_drift()
    d = ad.ADWIN(delta=e4.DELTA)
    fired = [i for i, x in enumerate(stream) if d.update(float(x))]
    assert fired, "ADWIN never fired on a 0.10 -> 0.35 step"
    assert min(fired) >= 200, f"a false alarm before the change at {min(fired)}"
    assert min(fired) - 200 <= 120, f"detection took {min(fired) - 200} observations"


def test_it_stays_quiet_on_a_stationary_stream():
    d = ad.ADWIN(delta=e4.DELTA)
    rng = np.random.default_rng(3)
    alarms = sum(1 for _ in range(2000)
                 if d.update(float(np.clip(rng.normal(0.10, 0.02), 0, 1))))
    assert alarms == 0, f"{alarms} false alarms on a stationary stream at delta={e4.DELTA}"


def test_an_unscaled_error_stream_never_fires():
    """The measurement that put the [0,1] rule in the module docstring."""
    rng = np.random.default_rng(5)
    raw = np.concatenate([np.abs(rng.normal(0.0, 0.01, 200)),
                          np.abs(rng.normal(0.05, 0.03, 200))])
    blind = ad.ADWIN(delta=e4.DELTA)
    assert not any(blind.update(float(x)) for x in raw), (
        "an unscaled stream fired, which would make the scaling rule in adwin.py wrong -- "
        "check the bound before deleting `to_unit`")
    scale = ad.unit_scale(raw[:200])
    seeing = ad.ADWIN(delta=e4.DELTA)
    fired = [i for i, x in enumerate(raw) if seeing.update(ad.to_unit(x, scale))]
    assert fired and min(fired) >= 200, (
        "the same stream scaled into [0, 1] must find the change it was given")


def test_unit_scale_is_a_median_not_a_max():
    vals = [0.01] * 100 + [50.0]
    s = ad.unit_scale(vals)
    assert s == pytest.approx(0.04), (
        "one outlier set the scale, which would compress every later observation towards zero "
        "and blind the detector for the rest of the run")
    assert ad.to_unit(50.0, s) == 1.0, "values above the scale must saturate, not overflow"


def test_the_declaration_says_why_river_was_not_used():
    d = ad.declaration()
    assert d["library"] == "NONE -- implemented here"
    assert "river" in d["why_not_river"]
    assert "no-index" in d["why_not_river"] or "--no-index" in d["why_not_river"]
    assert "[0, 1]" in d["stream_domain"]
    assert "Bifet" in d["citation"]


# ---------------------------------------------------------------------------
# the known-answer block the receipt carries
# ---------------------------------------------------------------------------
def test_the_delta_sweep_is_reported_not_chosen_silently():
    ka = e4.known_answer()
    assert set(ka["delta_sweep"]) == {str(d) for d in e4.DELTA_GRID}
    for d, cell in ka["delta_sweep"].items():
        assert cell["false_alarms_before_the_change"] == 0, f"delta={d} fired before the change"
    assert ka["delta_used_in_the_real_run"] == e4.DELTA
    assert ka["first_detection_after_change"] is not None
    assert ka["false_alarms_on_2000_stationary_steps"] == 0
    assert "0.008" in ka["unscaled_stream_finding"]


def test_the_synthetic_stream_is_inside_the_unit_interval():
    s = e4.synthetic_drift()
    assert s.min() >= 0.0 and s.max() <= 1.0
    assert np.mean(s[:200]) < np.mean(s[200:]) - 0.1


# ---------------------------------------------------------------------------
# the comparison's own shape
# ---------------------------------------------------------------------------
def test_both_policies_are_graded_on_the_same_dates_and_staleness_is_logged():
    import pandas as pd
    rng = np.random.default_rng(2)
    n = 80
    dd = pd.DataFrame({
        "date": pd.bdate_range("2025-01-02", periods=n),
        "month": "2025-01", "n": 50, "n_tradable": 40,
        "adwin_model_fitted_for_month": "2025-01",
        "adwin_model_is_stale": [False] * 40 + [True] * 40,
        "adwin_model_age_months": [0] * 40 + [1] * 40,
        "adwin_mean_abs_error": 0.01,
    })
    for name in ("FIXED", "ADWIN"):
        dd[f"ic_{name}"] = rng.normal(0, 0.05, n)
        dd[f"gross_{name}"] = rng.normal(0, 0.002, n)
        dd[f"net_{name}"] = rng.normal(0, 0.002, n)
        dd[f"turnover_{name}"] = 0.5
    g = e4.grade(dd)
    assert g["arms"]["FIXED"]["ic"]["n_date_blocks"] == g["arms"]["ADWIN"]["ic"]["n_date_blocks"]
    sv = g["stale_vs_fresh"]
    assert sv["n_dates_on_a_stale_model"] == 40 and sv["n_dates_on_a_fresh_model"] == 40
    assert sv["max_model_age_months"] == 1
    assert "ic_on_stale_dates" in sv and "ic_on_fresh_dates" in sv


def test_the_fixed_control_is_the_existing_walk_forward_not_a_new_run():
    src = Path(e4.__file__).read_text(encoding="utf-8")
    assert "not a separate control run" in src
    assert "COST_BPS" in src, "a book number without its cost rate is not a book number"
