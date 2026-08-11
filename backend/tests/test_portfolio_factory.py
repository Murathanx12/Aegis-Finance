"""Portfolio factory + capital frontier: the rules the programme paid for.

Equal weight is the control in every comparison (PF-2: winner-copying lost to
it; ARENA-1: a random book ranked 4th of 384). Kelly is refused rather than fed
a ranking score dressed as an expected return. Capacity numbers are delay-only
lower bounds and say so, because G7 cannot price impact (CANON §17).
"""

from __future__ import annotations

import pytest

from backend.services import capital_frontier as CF
from backend.services import portfolio_factory as PF
from backend.services.recommendation import Recommendation


def _rec(ticker, score, conf="LOW", grade="SUPPORTED", er=None, rank=1):
    return Recommendation(ticker=ticker, rank=rank, ranking_score=score,
                          confidence=conf, evidence_grade=grade,
                          expected_return=er)


@pytest.fixture
def recs():
    return [_rec(f"T{i:02d}", 1.0 - 0.04 * i, rank=i + 1) for i in range(25)]


# ── weights ──────────────────────────────────────────────────────────────────

def test_equal_weight_control_is_flat(recs):
    book = PF.build(recs, next(a for a in PF.ARCHETYPES
                               if a.name == "CONTROL_EQUAL_WEIGHT"))
    ws = list(book["weights"].values())
    assert book["is_control"] is True
    assert max(ws) - min(ws) < 1e-9, "the control must not tilt"
    assert abs(sum(ws) - 1.0) < 1e-6


def test_weights_sum_to_one_and_respect_the_cap(recs):
    for arch in PF.ARCHETYPES:
        if arch.needs_calibrated_er:
            continue
        try:
            book = PF.build(recs, arch, vols={r.ticker: 0.3 for r in recs})
        except PF.ArchetypeRefused:
            continue
        ws = book["weights"]
        assert abs(sum(ws.values()) - 1.0) < 1e-6, arch.name
        assert max(ws.values()) <= arch.max_weight + 1e-9, (
            f"{arch.name} breached its own {arch.max_weight:.0%} cap")


def test_cap_redistribution_reaches_a_fixed_point():
    """Capping one name pushes weight onto others, which can push THEM over.

    A single pass leaves a breach behind; this is the case that catches it.
    """
    rs = [_rec("BIG", 100.0), _rec("A", 1.0), _rec("B", 1.0),
          _rec("C", 1.0), _rec("D", 1.0), _rec("E", 1.0),
          _rec("F", 1.0), _rec("G", 1.0), _rec("H", 1.0), _rec("I", 1.0)]
    arch = PF.Archetype("T", 10, 0.10, "signal", "NONE", "test")
    book = PF.build(rs, arch)
    assert max(book["weights"].values()) <= 0.10 + 1e-9
    assert abs(sum(book["weights"].values()) - 1.0) < 1e-6


def test_signal_weighting_prefers_the_stronger_name(recs):
    arch = next(a for a in PF.ARCHETYPES if a.name == "OPTIMUS_AGGRESSIVE")
    book = PF.build(recs, arch)
    w = book["weights"]
    assert w["T00"] > w["T05"], "signal weighting must follow the ranking"


def test_inverse_vol_prefers_the_calmer_name():
    rs = [_rec("CALM", 0.5), _rec("WILD", 0.5)] + \
         [_rec(f"X{i}", 0.4) for i in range(10)]
    vols = {"CALM": 0.10, "WILD": 1.00, **{f"X{i}": 0.3 for i in range(10)}}
    arch = PF.Archetype("T", 12, 0.30, "inverse_vol", "NONE", "test")
    book = PF.build(rs, arch, vols=vols)
    assert book["weights"]["CALM"] > book["weights"]["WILD"]


def test_unknown_volatility_does_not_win_the_book():
    """A missing vol must not read as a low vol — that would hand the biggest
    weight to the name we know least about."""
    rs = [_rec("KNOWN", 0.5), _rec("UNKNOWN", 0.5)] + \
         [_rec(f"X{i}", 0.4) for i in range(10)]
    vols = {"KNOWN": 0.20, **{f"X{i}": 0.3 for i in range(10)}}
    arch = PF.Archetype("T", 12, 0.30, "inverse_vol", "NONE", "test")
    book = PF.build(rs, arch, vols=vols)
    assert book["weights"]["UNKNOWN"] <= book["weights"]["KNOWN"]


# ── refusals are findings ────────────────────────────────────────────────────

def test_kelly_is_refused_without_a_calibrated_expected_return(recs):
    arch = next(a for a in PF.ARCHETYPES if a.name == "OPTIMUS_MAX_GROWTH")
    with pytest.raises(PF.ArchetypeRefused) as e:
        PF.build(recs, arch)
    assert "CALIBRATED" in str(e.value)


def test_too_few_names_refuses_rather_than_breaching_the_cap():
    arch = next(a for a in PF.ARCHETYPES if a.name == "OPTIMUS_DIVERSIFIED_ALPHA")
    with pytest.raises(PF.ArchetypeRefused):
        PF.build([_rec("ONLY", 1.0)], arch)


def test_no_evidence_names_are_never_held(recs):
    rs = recs + [_rec("BLANK", 5.0, grade="NO_EVIDENCE")]
    for arch in PF.ARCHETYPES:
        if arch.needs_calibrated_er:
            continue
        try:
            book = PF.build(rs, arch, vols={r.ticker: 0.3 for r in rs})
        except PF.ArchetypeRefused:
            continue
        assert "BLANK" not in book["weights"], (
            f"{arch.name} held a name with no licensed evidence")


def test_build_all_records_refusals(recs):
    out = PF.build_all(recs, vols={r.ticker: 0.3 for r in recs})
    assert "OPTIMUS_MAX_GROWTH" in out["refused"]
    assert out["control"] is not None


# ── capacity ─────────────────────────────────────────────────────────────────

def test_capacity_blocks_a_big_position_in_a_thin_name():
    rows = {r.capital: r for r in CF.capacity_for(
        weight=0.10, median_dollar_vol=2_000_000.0)}
    assert rows[10_000.0].tradeable is True
    assert rows[250_000_000.0].tradeable is False
    assert "days to exit" in rows[250_000_000.0].binding_constraint


def test_capacity_without_volume_is_not_tradeable():
    rows = CF.capacity_for(weight=0.1, median_dollar_vol=None)
    assert all(not r.tradeable for r in rows)
    assert "cannot be checked" in rows[0].binding_constraint


def test_days_to_exit_scales_with_capital():
    rows = CF.capacity_for(weight=0.10, median_dollar_vol=50_000_000.0)
    days = [r.days_to_exit for r in rows]
    assert days == sorted(days), "more capital cannot mean a faster exit"


def test_corwin_schultz_is_not_the_raw_range():
    """(high-low)/2 is the intraday RANGE, not the spread — CANON §15."""
    high = [101.0, 102.0, 101.5, 103.0, 102.5]
    low = [99.0, 100.0, 99.5, 101.0, 100.5]
    s = CF.corwin_schultz_spread(high, low)
    assert s is not None
    naive_range = (high[0] - low[0]) / 2 / low[0]
    assert s < naive_range, (
        "the estimator must come in below the naive half-range, which "
        "overstates the spread by roughly an order of magnitude")
    assert 0.0 <= s < 0.5


def test_corwin_schultz_needs_two_days():
    assert CF.corwin_schultz_spread([100.0], [99.0]) is None
    assert CF.corwin_schultz_spread([], []) is None


def test_frontier_reports_the_impact_caveat():
    fr = CF.frontier([{"ticker": "A", "median_dollar_vol": 1e7}], {"A": 1.0})
    assert "DELAY-ONLY" in fr["impact_caveat"]
    assert "CANON" in fr["impact_caveat"]
    caps = [lv["capital"] for lv in fr["levels"]]
    assert caps == sorted(caps)


def test_frontier_blocked_weight_grows_with_capital():
    fr = CF.frontier([{"ticker": "A", "median_dollar_vol": 2e6},
                      {"ticker": "B", "median_dollar_vol": 5e9}],
                     {"A": 0.5, "B": 0.5})
    blocked = [lv["weight_blocked"] for lv in fr["levels"]]
    assert blocked == sorted(blocked)
    assert blocked[0] == 0.0 and blocked[-1] > 0.0
