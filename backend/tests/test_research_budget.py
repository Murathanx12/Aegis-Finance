"""The research governor's tests.

The failure this module was written against is subtle: the production cap was
believed to be throttling research when in fact research had NO governor. So
these tests care most about the cases where a budget quietly stops being a
budget — unreadable telemetry, an unpriced model, a refusal that pollutes the
denominator it is supposed to protect.
"""

import pytest

from backend.services import research_budget as rb


def _state(monkeypatch, summary):
    monkeypatch.setattr(rb, "_summary", lambda since, path: summary)


def test_a_fresh_campaign_is_allowed(monkeypatch):
    _state(monkeypatch, {"n_calls": 0, "total_cost_usd": 0.0})
    st = rb.check()
    assert st.ok and st.calls_remaining == rb.RESEARCH_LLM_MAX_CALLS


def test_the_call_ceiling_stops_the_campaign(monkeypatch):
    _state(monkeypatch, {"n_calls": rb.RESEARCH_LLM_MAX_CALLS,
                         "total_cost_usd": 1.0})
    st = rb.check()
    assert not st.ok and "call ceiling" in st.reason
    with pytest.raises(rb.ResearchBudgetExhausted):
        rb.require()


def test_the_dollar_ceiling_stops_the_campaign(monkeypatch):
    _state(monkeypatch, {"n_calls": 10,
                         "total_cost_usd": rb.RESEARCH_LLM_MAX_USD + 0.01})
    st = rb.check()
    assert not st.ok and "estimated spend" in st.reason


def test_an_unpriced_model_makes_the_dollar_ceiling_say_lower_bound(monkeypatch):
    """A ledger containing unpriced calls understates spend. The refusal must
    say so, because 'you are at the limit' and 'you are at LEAST at the limit'
    call for different responses."""
    _state(monkeypatch, {"n_calls": 10,
                         "total_cost_usd": rb.RESEARCH_LLM_MAX_USD + 0.01,
                         "total_is_lower_bound": True})
    st = rb.check()
    assert not st.ok and "LOWER BOUND" in st.reason


def test_unreadable_telemetry_refuses_rather_than_assuming_zero_spend(monkeypatch):
    """The dangerous case. If the accounting is broken, treating spend as zero
    would disarm every ceiling at exactly the wrong moment."""
    _state(monkeypatch, {})
    st = rb.check()
    assert not st.ok
    assert "unknown balance" in st.reason
    assert st.cost_usd is None


def test_the_zero_yield_brake_halts_a_campaign_buying_tokens(monkeypatch):
    _state(monkeypatch, {
        "n_calls": 500, "total_cost_usd": 1.0,
        "zero_gradeable_output": {
            "share_of_calls": rb.RESEARCH_LLM_MAX_ZERO_YIELD_RATE + 0.05}})
    st = rb.check()
    assert not st.ok
    assert "buying tokens" in st.reason


def test_the_zero_yield_brake_is_not_armed_on_a_tiny_sample(monkeypatch):
    """Halting a campaign because the first three parses failed would be its
    own kind of stupidity."""
    _state(monkeypatch, {
        "n_calls": rb.RESEARCH_LLM_ZERO_YIELD_MIN_N - 1, "total_cost_usd": 0.1,
        "zero_gradeable_output": {"share_of_calls": 0.99}})
    assert rb.check().ok


def test_a_healthy_campaign_mid_flight_reports_what_remains(monkeypatch):
    _state(monkeypatch, {"n_calls": 100, "total_cost_usd": 0.5,
                         "zero_gradeable_output": {"share_of_calls": 0.1}})
    st = rb.check()
    assert st.ok
    assert st.calls_remaining == rb.RESEARCH_LLM_MAX_CALLS - 100
    assert st.usd_remaining == pytest.approx(rb.RESEARCH_LLM_MAX_USD - 0.5)


def test_disabled_means_disabled(monkeypatch):
    monkeypatch.setattr(rb, "RESEARCH_LLM_ENABLED", False)
    st = rb.check()
    assert not st.ok and "disabled" in st.reason


def test_health_distinguishes_never_ran_from_spent(monkeypatch):
    _state(monkeypatch, {"n_calls": 0, "total_cost_usd": 0.0})
    assert "no research calls recorded" in rb.health()["reading"]

    _state(monkeypatch, {"n_calls": rb.RESEARCH_LLM_MAX_CALLS,
                         "total_cost_usd": 1.0})
    assert "REFUSING" in rb.health()["reading"]


def test_require_returns_the_state_when_it_allows(monkeypatch):
    """The caller gets the budget state back, so a long campaign can log what
    remains without a second read."""
    _state(monkeypatch, {"n_calls": 5, "total_cost_usd": 0.05})
    st = rb.require()
    assert st.ok and st.n_calls == 5


def test_the_production_cap_is_untouched():
    """The whole point of a separate governor: production's guard stays where
    it is. If this ever fails, the two budgets have been merged and the
    user-facing balance is exposed to a research loop again."""
    from backend.config import config
    assert config["llm"]["daily_call_cap"] == 150

    # And the enforcement really does read that value, rather than a copy that
    # could drift away from it.
    from backend.services import llm_analyzer
    assert llm_analyzer._DAILY_CAP == 150
