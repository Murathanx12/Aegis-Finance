"""RECO-1 — the BUY ranking may only be led by signals licensed to lead it.

These tests exist because BUILD-1.2 shipped a brief that printed
`EVIDENCE CONFLICT (HIGH)` on itself every morning and kept ranking anyway. A
warning nobody can act on is not a control. Each test here fails loudly if the
structural property it guards is broken:

  * a CLOSED signal cannot reorder the BUY list (invariance, Spearman == 1)
  * a RISK_INPUT cannot reorder it either — it may only cap SIZE
  * a FILTER may nudge but may never be the largest contributor
  * a PICKER outside its licensed universe contributes nothing
  * the gate REFUSES to publish a ranking rather than warning about it
"""

from __future__ import annotations

import pytest

from backend import config
from backend.services import recommendation as rec
from backend.services import signal_registry as registry_mod


def _cand(ticker, *, quality=None, mcap=1_000_000_000.0, upside=None,
          mom=None, vol=0.30, price=50.0, sector="Test", insider_score=None):
    return {"ticker": ticker, "quality": quality, "market_cap": mcap,
            "analyst_upside": upside, "mom_12_1": mom, "vol_annual": vol,
            "price": price, "sector": sector, "insider_score": insider_score}


@pytest.fixture(scope="module")
def registry():
    return registry_mod.load()


@pytest.fixture
def small_caps():
    """Five SMALL-cap names — inside `profitability_small`'s licensed universe —
    whose analyst upside runs exactly OPPOSITE to their profitability.

    If the closed upside signal has any influence at all, it shows up here as a
    reordering, because the two orderings are constructed to disagree.
    """
    return [
        _cand("AAA", quality=0.90, mcap=0.5e9, upside=-0.10, mom=0.40),
        _cand("BBB", quality=0.70, mcap=0.8e9, upside=0.05, mom=0.30),
        _cand("CCC", quality=0.50, mcap=1.0e9, upside=0.20, mom=0.20),
        _cand("DDD", quality=0.30, mcap=1.2e9, upside=0.45, mom=0.10),
        _cand("EEE", quality=0.10, mcap=1.5e9, upside=0.90, mom=0.05),
    ]


# ── the ranking is led by the picker, not by the corpse ──────────────────────

def test_ranking_is_led_by_a_permitted_picker(small_caps, registry):
    recs = rec.score_candidates(small_caps, registry=registry)
    assert [r.ticker for r in recs] == ["AAA", "BBB", "CCC", "DDD", "EEE"], (
        "the order should follow profitability, the licensed PICKER")
    for r in recs:
        lead = r.leader()
        assert lead is not None, f"{r.ticker} has no rank-bearing signal"
        assert registry.permits(lead.signal_id, "PICKER"), (
            f"{r.ticker} is led by {lead.signal_id}, which is not a PICKER")


def test_highest_analyst_upside_ranks_last(small_caps, registry):
    """The specific regression. EEE has +90% implied upside and the worst
    profitability; the old CE chain ranked it first."""
    recs = rec.score_candidates(small_caps, registry=registry)
    assert recs[-1].ticker == "EEE"
    assert recs[0].ticker == "AAA"


@pytest.mark.parametrize("signal_id", ["analyst_target_upside_xs",
                                       "momentum_12_1",
                                       "analyst_target_level_haircut"])
def test_closed_and_risk_input_signals_cannot_reorder(small_caps, registry,
                                                      signal_id):
    out = rec.rank_invariance(small_caps, signal_id, registry=registry)
    assert out["invariant_holds"], out["reading"]
    assert out["spearman_rho"] == 1.0
    assert out["n_names_moved"] == 0, (
        f"{signal_id} reordered {out['names_moved']} — it is steering the BUY list")


def test_closed_signals_are_printed_not_hidden(small_caps, registry):
    """Suppressing the corpse is not the fix; it has to stay visible."""
    recs = rec.score_candidates(small_caps, registry=registry)
    ids = {c.signal_id for c in recs[0].signal_contributions}
    assert "analyst_target_upside_xs" in ids
    for c in recs[0].signal_contributions:
        if c.signal_id == "analyst_target_upside_xs":
            assert c.contribution == 0.0
            assert c.rank_bearing is False
            assert "ZERO rank influence" in c.basis
            assert c.raw_value is not None, "the value is still read and shown"


def test_gate_passes_on_a_clean_ranking(small_caps, registry):
    out = rec.assert_registry_discipline(small_caps, registry=registry)
    assert out["status"] == "CLEAN"
    assert out["violations"] == []
    assert any(c["signal_id"] == "analyst_target_upside_xs"
               for c in out["invariance_checks"])


# ── the gate must REFUSE, not warn ───────────────────────────────────────────

def test_gate_raises_when_a_closed_signal_is_promoted(small_caps, registry,
                                                      monkeypatch):
    """Simulate the BUILD-1.2 defect: let the corpse become rank-bearing.

    The gate must raise. If this test ever passes silently, the product has
    gone back to warning about its own ranking instead of refusing to print it.

    Note `analyst_target_upside_xs` is licensed on all three cap bands, so the
    universe gate does NOT cover for the role gate here. This test isolates the
    role gate, which is the one that failed in BUILD-1.2.
    """
    assert config.SIGNAL_UNIVERSE_BANDS[
        registry.get("analyst_target_upside_xs").universe], (
        "fixture assumption: the corpse is not size-limited, so only its ROLE "
        "can stop it")
    real_permits = registry.permits

    def permissive(signal_id, role):
        if signal_id == "analyst_target_upside_xs" and role == "PICKER":
            return True
        return real_permits(signal_id, role)

    monkeypatch.setattr(registry, "permits", permissive)
    with pytest.raises(rec.RankLeadershipError) as excinfo:
        rec.assert_registry_discipline(small_caps, registry=registry)
    assert "analyst_target_upside_xs" in str(excinfo.value) or \
           "violation" in str(excinfo.value).lower()


def test_audit_flags_a_never_picks_grade_that_is_ranking(small_caps, registry,
                                                         monkeypatch):
    real_permits = registry.permits
    monkeypatch.setattr(registry, "permits",
                        lambda s, r: True if s == "analyst_target_upside_xs"
                        and r == "PICKER" else real_permits(s, r))
    recs = rec.score_candidates(small_caps, registry=registry)
    violations = rec.audit_leadership(recs, registry=registry)
    assert violations, "a PERVERSE grade ranking names must be flagged"
    assert all(v["severity"] == "HIGH" for v in violations
               if v["signal"] == "analyst_target_upside_xs")


# ── universe discipline ──────────────────────────────────────────────────────

def test_picker_outside_its_universe_contributes_nothing(registry):
    """`profitability_small` says "Net-dead in large/mid" in its own entry.

    Before NIGHT-10 it was the leading contributor to NVDA, AAPL and META.
    """
    big = [_cand("MEGA1", quality=0.90, mcap=4_000e9),
           _cand("MEGA2", quality=0.20, mcap=3_000e9)]
    recs = rec.score_candidates(big, registry=registry)
    for r in recs:
        assert r.ranking_score == 0.0
        assert r.evidence_grade == "NO_EVIDENCE"
        assert r.recommendation == "NO_ACTION"
        contrib = next(c for c in r.signal_contributions
                       if c.signal_id == "profitability_small")
        assert contrib.contribution == 0.0
        assert "OUT OF UNIVERSE" in contrib.basis


def test_cap_bands():
    assert rec.cap_band(1e9) == "small"
    assert rec.cap_band(5e9) == "mid"
    assert rec.cap_band(500e9) == "large"
    assert rec.cap_band(None) is None
    assert rec.cap_band(0) is None


def test_unknown_market_cap_is_not_permission(registry):
    """Not knowing the size is not a licence to apply a size-limited signal."""
    sig = registry.get("profitability_small")
    ok, why = rec.in_universe(sig, None)
    assert ok is False
    assert "unknown" in why.lower()


def test_unknown_universe_string_is_not_permission(registry):
    sig = registry.get("profitability_small")
    fake = registry_mod.Signal(signal_id="x", universe="Martian equities")
    ok, why = rec.in_universe(fake, 1e9)
    assert ok is False
    assert "not a recognised band" in why
    assert rec.in_universe(sig, 1e9)[0] is True


# ── honesty of the output ────────────────────────────────────────────────────

def test_expected_return_is_never_invented(small_caps, registry):
    """No calibrated picker->E[R] map exists, so none may be printed."""
    recs = rec.score_candidates(small_caps, registry=registry)
    for r in recs:
        assert r.expected_return is None
        assert r.expected_return_basis == "NOT_CALIBRATED"
        assert r.percentile is not None, "a ranking score still gets a percentile"


def test_confidence_is_about_evidence_not_volatility(registry):
    """Murat's ruling: risk and evidence are separate dimensions."""
    calm = _cand("CALM", quality=0.8, mcap=1e9, vol=0.10)
    wild = _cand("WILD", quality=0.8, mcap=1e9, vol=1.20)
    recs = {r.ticker: r for r in rec.score_candidates([calm, wild],
                                                     registry=registry)}
    assert recs["CALM"].confidence == recs["WILD"].confidence, (
        "volatility must not change the CONFIDENCE column")


def test_missing_signal_records_a_reason(small_caps, registry):
    """Silent fragility is the house failure mode: absent != neutral."""
    recs = rec.score_candidates(small_caps, registry=registry)
    absent = [c for c in recs[0].signal_contributions if not c.available]
    assert absent, "these fixtures carry no insider data, so some must be absent"
    for c in absent:
        assert c.missing_reason, f"{c.signal_id} is missing with no stated reason"
        assert c.contribution == 0.0


def test_empty_candidate_list_is_empty_not_an_error(registry):
    assert rec.score_candidates([], registry=registry) == []


def test_better_alternatives_point_upward(small_caps, registry):
    recs = rec.score_candidates(small_caps, registry=registry)
    assert recs[0].better_alternatives == []
    assert recs[-1].better_alternatives[:1] == [recs[0].ticker]


# ── ties are not an order ────────────────────────────────────────────────────

def test_tied_scores_share_a_rank(registry):
    """Most candidates score at the modal insider reading. Printing them in
    list order would be a confident ranking of a coin flip."""
    tied = [_cand(f"T{i}", quality=0.5, mcap=1e9) for i in range(6)]
    recs = rec.score_candidates(tied, registry=registry)
    assert len({r.ranking_score for r in recs}) == 1
    assert {r.rank for r in recs} == {1}, "tied names must share a rank"
    assert all(r.tied_with == 5 for r in recs)


def test_a_tied_name_is_never_a_buy(registry):
    """A BUY has to be earned by evidence, not by list position."""
    tied = [_cand(f"T{i}", quality=0.5, mcap=1e9) for i in range(6)]
    recs = rec.score_candidates(tied, registry=registry)
    assert all(r.recommendation != "BUY" for r in recs)


def test_untied_leader_can_still_buy(registry):
    cands = [_cand("LEAD", quality=0.95, mcap=1e9, insider_score=3.0)] + \
            [_cand(f"T{i}", quality=0.5, mcap=1e9, insider_score=0.0)
             for i in range(6)]
    recs = rec.score_candidates(cands, registry=registry)
    top = recs[0]
    assert top.ticker == "LEAD"
    assert top.tied_with == 0
    assert top.confidence in ("MEDIUM", "HIGH")
    assert top.recommendation == "BUY"
