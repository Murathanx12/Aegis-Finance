"""An INVERSE mapping must be earned, and earning it must be hard.

The instinct behind "inverse Cramer" is sound — a reliably wrong actor carries
information. The method is not: the real Inverse Cramer ETF returned negative
and was liquidated, because reputation is not evidence.

The tests that carry weight here are the REFUSALS. Inverting an actor is free
in a way that measuring one is not: scan enough actors against a 0.50 null and
the worst few sit below it from noise alone, and flipping them costs nothing
and adds no evidence. So the suite spends most of its effort proving the gate
says no.
"""

from __future__ import annotations

import pytest

from backend.services import actor_intelligence as AI


def _claim(actor="jim", day="2026-01-05", direction=1, outcome=1,
           actor_type="commentator", entity="AAPL", domain="tech",
           claim_type="directional_call", horizon=20) -> dict:
    return {
        "actor": actor, "actor_type": actor_type, "entity": entity,
        "direction": direction, "claim_type": claim_type, "domain": domain,
        "horizon_days": horizon, "public_at": f"{day}T12:00:00+00:00",
        "observed_at": f"{day}T12:00:00+00:00", "regime": "normal",
        "outcome": outcome,
    }


def _corpus(actor: str, n_days: int, hit_rate: float, start_day: int = 1,
            **kw) -> list[dict]:
    """One claim per DAY, so decision days == claims by construction."""
    out = []
    for i in range(n_days):
        d = f"2026-{(start_day + i) // 28 + 1:02d}-{(start_day + i) % 28 + 1:02d}"
        out.append(_claim(actor=actor, day=d,
                          outcome=1 if i < round(n_days * hit_rate) else 0,
                          **kw))
    return out


# ----------------------------------------------------------- claim schema


def test_a_nondirectional_claim_is_refused():
    """An actor who said nothing cannot be right or wrong."""
    with pytest.raises(AI.ActorEvidenceRefused):
        AI.make_claim(actor="a", actor_type="commentator", entity="AAPL",
                      direction=0, claim_type="c", domain="tech",
                      horizon_days=20, public_at="2026-01-05")


def test_a_claim_with_no_horizon_is_refused():
    with pytest.raises(AI.ActorEvidenceRefused):
        AI.make_claim(actor="a", actor_type="commentator", entity="AAPL",
                      direction=1, claim_type="c", domain="tech",
                      horizon_days=0, public_at="2026-01-05")


def test_observing_a_claim_before_it_was_public_is_refused():
    """The shape lookahead takes in an actor corpus."""
    with pytest.raises(AI.ActorEvidenceRefused) as e:
        AI.make_claim(actor="a", actor_type="commentator", entity="AAPL",
                      direction=1, claim_type="c", domain="tech",
                      horizon_days=20, public_at="2026-01-05",
                      observed_at="2026-01-01T00:00:00+00:00")
    assert "lookahead" in str(e.value)


def test_disclosure_lag_is_recorded():
    """A 13F is public 45 days after the position was taken; grading it from
    the position date credits foresight no follower could have acted on."""
    c = AI.make_claim(actor="fund", actor_type="institution", entity="AAPL",
                      direction=1, claim_type="13f_position", domain="tech",
                      horizon_days=60, public_at="2026-01-05",
                      observed_at="2026-02-19T00:00:00+00:00")
    assert c.disclosure_lag_days == 45


# --------------------------------------------------------------- skill


def test_unknown_conditioning_key_is_refused():
    claims = _corpus("jim", 30, 0.5)
    with pytest.raises(AI.ActorEvidenceRefused):
        AI.actor_skill(claims, actor="jim", context={"mood": "grumpy"})


def test_an_actor_with_no_corpus_is_refused_not_scored_neutral():
    claims = _corpus("jim", 30, 0.5)
    with pytest.raises(AI.ActorEvidenceRefused):
        AI.actor_skill(claims, actor="nobody")


def test_decision_days_not_claims(monkeypatch):
    """Forty names on one broadcast is ONE decision, not forty."""
    same_day = [_claim(actor="jim", day="2026-01-05", entity=f"T{i}")
                for i in range(40)]
    s = AI.actor_skill(same_day, actor="jim")
    assert s["n_claims"] == 40
    assert s["n_decision_days"] == 1, (
        "forty claims on one day counted as forty independent decisions")


def test_thin_actor_gets_an_estimate_but_no_verdict():
    s = AI.actor_skill(_corpus("jim", 5, 0.2), actor="jim")
    assert s["verdict"] == "THIN"
    assert s["thin_reason"]
    assert s["shrunk_hit_rate"] is not None


def test_shrinkage_pulls_a_thin_extreme_toward_the_null():
    """A 5-day 0% actor must not be reported as a 0% actor."""
    s = AI.actor_skill(_corpus("jim", 5, 0.0), actor="jim")
    assert s["raw_hit_rate"] == 0.0
    assert s["shrunk_hit_rate"] > 0.2, (
        f"thin extreme was not shrunk: {s['shrunk_hit_rate']}")


def test_hit_rate_is_labelled_as_direction_only():
    """Timing, sizing and magnitude are different skills and are not measured."""
    s = AI.actor_skill(_corpus("jim", 30, 0.5), actor="jim")
    assert "timing" in s["note"] and "sizing" in s["note"]


# ------------------------------------------------ THE INVERSE GATE (refusals)


def _skill(actor, edge, z, days=40):
    return {"actor": actor, "edge": edge, "z": z, "n_decision_days": days}


def test_no_holdout_means_no_licence():
    """An inverse selected and confirmed on the same data is not confirmed."""
    out = AI.inverse_license([_skill("jim", -0.20, -4.0)], holdout=None)
    assert out["licensed"] == []
    assert any("holdout" in r for r in out["refused"][0]["refused_because"])


def test_a_holdout_that_does_not_repeat_the_deficit_refuses():
    out = AI.inverse_license(
        [_skill("jim", -0.20, -4.0)],
        holdout=[{"actor": "jim", "edge": +0.01}])
    assert out["licensed"] == []
    assert any("holdout" in r for r in out["refused"][0]["refused_because"])


def test_a_thin_actor_cannot_be_inverted():
    out = AI.inverse_license(
        [_skill("jim", -0.20, -4.0, days=5)],
        holdout=[{"actor": "jim", "edge": -0.20}])
    assert out["licensed"] == []
    assert any("decision days" in r
               for r in out["refused"][0]["refused_because"])


def test_a_small_deficit_cannot_be_inverted():
    out = AI.inverse_license(
        [_skill("jim", -0.01, -4.0)],
        holdout=[{"actor": "jim", "edge": -0.01}])
    assert out["licensed"] == []
    assert any("deficit" in r for r in out["refused"][0]["refused_because"])


def test_the_worst_of_many_noisy_actors_is_NOT_licensed():
    """THE multiplicity test.

    200 actors at the null: the worst will look terrible. Licensing it would
    be a multiplicity machine, not a discovery.
    """
    import random
    rng = random.Random(7)
    skills = [_skill(f"a{i}", edge=rng.gauss(0, 0.03),
                     z=rng.gauss(0, 1.0)) for i in range(200)]
    worst = min(skills, key=lambda s: s["z"])
    worst["edge"] = -0.10          # looks like a big deficit, purely by noise
    out = AI.inverse_license(
        skills, holdout=[{"actor": worst["actor"], "edge": -0.10}])
    assert worst["actor"] not in [x["actor"] for x in out["licensed"]], (
        "the worst of 200 null actors was licensed for inversion")
    assert out["m_considered"] == 200


def test_passing_only_the_losers_cannot_smuggle_a_licence():
    """m is the number of actors CONSIDERED. A shortlist inflates nothing."""
    full = AI.inverse_license(
        [_skill("jim", -0.20, -2.2)] + [_skill(f"a{i}", 0.0, 0.1)
                                        for i in range(199)],
        holdout=[{"actor": "jim", "edge": -0.20}])
    short = AI.inverse_license(
        [_skill("jim", -0.20, -2.2)],
        holdout=[{"actor": "jim", "edge": -0.20}])
    assert full["m_considered"] == 200 and short["m_considered"] == 1
    # The shortlist is easier — which is exactly why the caller must pass
    # everything it looked at. Documented, and asserted so it stays true.
    assert len(short["licensed"]) >= len(full["licensed"])


# --------------------------------------------------- THE INVERSE GATE (grant)


def test_a_genuinely_reliable_loser_IS_licensed():
    """The gate must be passable, or every refusal above is vacuous."""
    skills = ([_skill("jim", -0.18, -5.5, days=60)]
              + [_skill(f"a{i}", 0.0, 0.05) for i in range(20)])
    out = AI.inverse_license(
        skills, holdout=[{"actor": "jim", "edge": -0.16}])
    assert [x["actor"] for x in out["licensed"]] == ["jim"]
    assert out["licensed"][0]["mapping"] == "INVERSE"


def test_no_actor_is_contrarian_by_default():
    """Nothing anywhere hard-codes a name."""
    # The module may DISCUSS the example in prose; it must never BRANCH on a
    # person's name. A literal comparison against an actor string is the thing
    # being forbidden.
    text = open(AI.__file__, encoding="utf-8").read()
    assert 'actor == "' not in text and "actor == '" not in text
    assert 'actor.lower() ==' not in text

    # And behaviourally: a famous name with weak evidence gets nothing.
    out = AI.inverse_license([_skill("jim cramer", -0.02, -0.4)],
                             holdout=[{"actor": "jim cramer", "edge": -0.02}])
    assert out["licensed"] == [], "a famous name got a shortcut"


def test_the_hierarchy_still_backs_off_when_levels_really_differ():
    """The duplicate-level collapse must not disable real backoff.

    A thin actor inside a LARGE population of other actors should be pulled
    toward that population, not left shouting alone — that is the whole point
    of the hierarchy, and the fix for the identical-levels bug must not have
    thrown it away.
    """
    population = _corpus("crowd", 200, 0.50, start_day=1)
    thin_loser = _corpus("jim", 4, 0.0, start_day=210)
    s = AI.actor_skill(population + thin_loser, actor="jim")

    assert s["raw_hit_rate"] == 0.0
    assert s["shrunk_hit_rate"] > 0.25, (
        f"a 0-for-4 actor inside a 200-claim population was not pulled "
        f"toward it: {s['shrunk_hit_rate']}")
    assert s["verdict"] == "THIN"
