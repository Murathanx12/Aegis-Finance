"""Portable pure launch-policy checks; never import or run a native reader."""

import pytest

from scripts.beta_v2_reader_tab_limit import TabLimitRefused, supervisor_limit, tab_limit


def test_initial_supervised_qualification_and_direct_pool_default_are_distinct():
    assert supervisor_limit(configured=6) == 2
    assert tab_limit(configured=6) == 6
    assert supervisor_limit(configured=6, preferred=3) == 3
    assert supervisor_limit(2, configured=6, preferred=4) == 2


@pytest.mark.parametrize("limit", [1, 2, 3, 4, 5, 6])
def test_explicit_ceiling_is_retained_for_both_launch_routes(limit):
    assert tab_limit(limit, configured=6) == limit
    assert supervisor_limit(limit, configured=6) == limit


@pytest.mark.parametrize("bad", [0, -1, 7, True, False, 2.0, "2", float("inf")])
def test_invalid_requests_refuse_instead_of_falling_back(bad):
    with pytest.raises(TabLimitRefused):
        tab_limit(bad, configured=6)
    with pytest.raises(TabLimitRefused):
        supervisor_limit(bad, configured=6)


@pytest.mark.parametrize("bad", [None, 0, -1, 7, True, 6.0, "6"])
def test_missing_or_invalid_configuration_refuses_even_with_valid_cli(bad):
    with pytest.raises(TabLimitRefused):
        supervisor_limit(2, configured=bad)


def test_preference_cannot_exceed_configured_ceiling():
    with pytest.raises(TabLimitRefused):
        supervisor_limit(configured=1)
    assert supervisor_limit(1, configured=1) == 1
    with pytest.raises(TabLimitRefused):
        supervisor_limit(configured=6, preferred=7)
