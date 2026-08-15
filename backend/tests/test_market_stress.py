"""The atlas was unreachable in principle. This is the feature that unblocks it.

N2 measured eleven international candidate transfer slices supplying 152 stress
episodes, and **not one of those episodes could be evaluated by a single rule
in the mechanism library** — because every precursor is written over `vix` and
exactly one market has a VIX.

The obvious substitute fails for a reason worth pinning: `realised_vol_20d` is
portable as a number and meaningless as a threshold. N2's frequency-matched
bars came out at 57.3% annualised for Korea and 27.2% for Australia, so a rule
reading `realised_vol_20d >= 40` selects a country rather than a state.
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.services.research_gym import autopsy as AU
from backend.services.research_gym import market_stress as MS


def _rets(n=3000, seed=7, scale=0.01):
    rng = np.random.default_rng(seed)
    return list(rng.normal(0.0004, scale, n))


# ── the point-in-time property, which is the whole design ──────────────────

def test_the_percentile_NEVER_sees_the_future():
    """A percentile against the full sample knows the future distribution:
    2008 would rank differently depending on whether 2020 had happened yet."""
    r = _rets()
    vol = MS.realised_vol(r)
    full = MS.stress_pctile(vol)

    # Truncating the series must not change any value computed before the cut.
    cut = 2000
    partial = MS.stress_pctile(vol[:cut])
    for i in range(cut):
        assert full[i] == partial[i], (
            f"day {i} changed when later data was removed — the rank is being "
            f"taken against the whole sample, which is lookahead")


def test_the_percentile_excludes_the_day_it_labels():
    """Including today makes a new all-time high rank below 1.0 by exactly
    1/n, which is small, systematic and in the flattering direction."""
    vol = [1.0] * MS.MIN_HISTORY_DAYS + [99.0]
    out = MS.stress_pctile(vol)
    assert out[-1] == pytest.approx(1.0), (
        "a value above every prior observation must rank at 1.0; ranking it "
        "against a history that already contains it does not")


def test_unmeasurable_days_are_None_and_never_zero():
    r = _rets(n=100)
    vol = MS.realised_vol(r)
    pct = MS.stress_pctile(vol)
    assert vol[0] is None and vol[MS.VOL_WINDOW - 2] is None
    assert vol[MS.VOL_WINDOW - 1] is not None
    # 100 days is far short of the history requirement.
    assert all(p is None for p in pct), (
        "a percentile was reported before enough history existed — an "
        "unmeasurable state must never print as a measured one")


def test_history_is_required_before_a_percentile_appears():
    r = _rets(n=MS.MIN_HISTORY_DAYS + MS.VOL_WINDOW + 50)
    pct = MS.stress_pctile(MS.realised_vol(r))
    assert pct[MS.MIN_HISTORY_DAYS] is None
    assert any(p is not None for p in pct)
    for p in pct:
        assert p is None or 0.0 <= p <= 1.0


# ── the reason it exists: comparability across markets ─────────────────────

def test_the_LEVEL_is_not_comparable_across_markets_but_the_PERCENTILE_IS():
    """The measurement that made N2's frequency-matching necessary.

    Two markets with the same shape and different scale. A threshold on the
    LEVEL fires constantly in one and never in the other; a threshold on the
    percentile fires at the same rate in both, which is what a transferable
    rule has to do.
    """
    calm = _rets(n=4000, seed=11, scale=0.006)     # ~9.5% annualised
    wild = _rets(n=4000, seed=11, scale=0.024)     # ~38% annualised

    v_calm = MS.realised_vol(calm)
    v_wild = MS.realised_vol(wild)
    lvl_calm = [v for v in v_calm if v is not None]
    lvl_wild = [v for v in v_wild if v is not None]
    assert np.median(lvl_wild) > 3 * np.median(lvl_calm)

    LEVEL_BAR = 25.0
    fire_calm = sum(1 for v in lvl_calm if v >= LEVEL_BAR) / len(lvl_calm)
    fire_wild = sum(1 for v in lvl_wild if v >= LEVEL_BAR) / len(lvl_wild)
    assert fire_calm < 0.01 and fire_wild > 0.90, (
        "the fixture is not making the point: a level threshold must be "
        "near-dead in one market and near-always in the other")

    bar = MS.frequency_matched_threshold(0.05)
    p_calm = [p for p in MS.stress_pctile(v_calm) if p is not None]
    p_wild = [p for p in MS.stress_pctile(v_wild) if p is not None]
    r_calm = sum(1 for p in p_calm if p >= bar) / len(p_calm)
    r_wild = sum(1 for p in p_wild if p >= bar) / len(p_wild)
    assert abs(r_calm - r_wild) < 0.04, (
        f"the percentile fires at {r_calm:.1%} in one market and {r_wild:.1%} "
        f"in the other — it is not market-relative after all")


def test_the_frequency_matched_bar_reproduces_the_incumbents_rate():
    """VIX >= 35 holds on 3.83% of days since 1990 (measured in N2)."""
    bar = MS.frequency_matched_threshold()
    assert bar == pytest.approx(1.0 - 0.038274)
    assert MS.frequency_matched_threshold(0.10) == pytest.approx(0.90)


# ── and the grammar now accepts it ─────────────────────────────────────────

def test_a_precursor_can_be_WRITTEN_over_stress_pctile():
    assert "stress_pctile" in AU.TRANSFERABLE_FEATURES
    fn = AU.compile_precursor(
        {"all": [{"feature": "stress_pctile", "op": ">=", "value": 0.96}]})
    assert fn({"stress_pctile": 0.99}) is True
    assert fn({"stress_pctile": 0.50}) is False


def test_a_precursor_over_stress_pctile_REFUSES_a_state_that_lacks_it():
    """A missing feature raises rather than evaluating False — otherwise a
    mechanism that was never RUN reads as 'tested and did not transfer'."""
    fn = AU.compile_precursor(
        {"all": [{"feature": "stress_pctile", "op": ">=", "value": 0.96}]})
    with pytest.raises(AU.PrecursorRefused):
        fn({"vix": 40.0})


def test_stress_state_supplies_both_terms_together():
    r = _rets(n=MS.MIN_HISTORY_DAYS + 200)
    st = MS.stress_state(r)
    assert len(st) == len(r)
    assert set(st[-1]) == {"realised_vol_20d", "stress_pctile"}
    assert st[-1]["stress_pctile"] is not None
    assert st[0]["realised_vol_20d"] is None
