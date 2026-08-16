"""The ex-post guard must actually refuse, and must refuse where it matters.

SS47: the test proving a guard fires had never made it fire. So every test here
executes the refusing path and asserts on the exception, not on the presence of
the class.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pytest

from backend.services.research_gym.ex_post import (ExPostScale,
                                                   ExPostUsageError,
                                                   matched_vol_scale)

REPO = Path(__file__).resolve().parents[2]


def _scale() -> ExPostScale:
    return matched_vol_scale(18.0, 9.0, basis="full-sample realised vol")


def test_the_scale_is_correct_when_you_ask_for_it_properly():
    s = _scale()
    assert s.for_comparison_only() == pytest.approx(2.0)


def test_multiplying_an_exposure_array_raises():
    """The exact line the guard exists for: `exposures * scale`."""
    expo = np.full(100, 0.5)
    with pytest.raises(ExPostUsageError, match="EX-POST"):
        _ = expo * _scale()


def test_multiplying_the_other_way_round_raises():
    with pytest.raises(ExPostUsageError):
        _ = _scale() * np.full(10, 0.5)


def test_float_coercion_raises():
    """`float(scale)` is the obvious way around the guard, so it is closed."""
    with pytest.raises(ExPostUsageError):
        float(_scale())


def test_scalar_arithmetic_raises():
    for op in (lambda s: s * 2.0, lambda s: 2.0 * s, lambda s: s + 1.0,
               lambda s: s / 2.0):
        with pytest.raises(ExPostUsageError):
            op(_scale())


def test_the_refusal_names_the_hindsight():
    """A refusal that does not say WHY gets worked around."""
    with pytest.raises(ExPostUsageError) as e:
        float(matched_vol_scale(18.0, 9.0,
                                basis="vol_target_1x over the full 6591-day sample"))
    assert "6591-day sample" in str(e.value)


def test_an_anonymous_ex_post_quantity_cannot_be_constructed():
    with pytest.raises(ExPostUsageError, match="basis"):
        ExPostScale(2.0, basis="   ")


def test_degenerate_policy_vol_does_not_silently_become_a_live_number():
    s = matched_vol_scale(18.0, 0.0, basis="degenerate case")
    assert s.for_comparison_only() == 1.0
    with pytest.raises(ExPostUsageError):          # still not deployable
        _ = np.ones(3) * s


def test_n12_routes_its_matched_scale_through_the_guard():
    """The call site, not just the class.

    n12_vol_targeted_sizing.py:126 was `scale = ref_vol / pv`. If that ever
    returns, this fails.
    """
    src = (REPO / "scripts" / "n12_vol_targeted_sizing.py").read_text(
        encoding="utf-8")
    assert "matched_vol_scale" in src, \
        "N12 must build its matched-vol scale through the ex_post guard"
    assert not re.search(r"scale\s*=\s*\(?\s*ref_vol\s*/\s*pv", src), \
        "N12 recomputes the ex-post scale inline, bypassing the guard"


def test_no_inline_full_sample_scaling_outside_this_module():
    """The guard stops leaks THROUGH the object; this stops leaks around it.

    Any other script that divides a reference vol by a policy's own realised
    vol is reintroducing the hindsight the guard was built to contain.
    """
    offenders = []
    pat = re.compile(r"ref_vol\s*/\s*(pv|policy_vol)\b")
    for p in (REPO / "scripts").glob("*.py"):
        if pat.search(p.read_text(encoding="utf-8")):
            offenders.append(p.name)
    assert not offenders, (
        f"inline ex-post vol matching found in {offenders} — build it with "
        f"ex_post.matched_vol_scale so it cannot reach an exposure path")
