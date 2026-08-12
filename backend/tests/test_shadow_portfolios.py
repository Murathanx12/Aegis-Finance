"""The firewall between an outcome and a position size must be structural.

Murat wants the system to learn from what happens. The failure mode is the
obvious loop: it made money, so the model is smart, so size it bigger. These
tests pin the properties that make that loop impossible to write by accident.
"""
from __future__ import annotations

import json

import pytest

from backend.services import shadow_portfolios as S


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "DECISIONS", tmp_path / "d.jsonl")
    monkeypatch.setattr(S, "LEARNING", tmp_path / "l.jsonl")
    S.MALFORMED_ROWS.clear()
    yield


def _decision(**kw):
    base = dict(
        shadow_id="CHALLENGER_X", decided_at="2026-08-11T00:00:00+00:00",
        as_of="2026-08-11",
        weights={"AAA": 0.5, "BBB": 0.5},
        signal_contributions={"AAA": {"profitability_small": 0.6},
                              "BBB": {"profitability_small": 0.4}},
        evidence_grades={"profitability_small": "SUPPORTED"},
        expected_return={"AAA": 0.10, "BBB": 0.08},
        expected_risk={"AAA": 0.30, "BBB": 0.25},
        cost_assumption={"round_trip": 0.004, "model": "retail flat"})
    base.update(kw)
    return S.ShadowDecision(**base)


# ─────────────────────────── the firewall ───────────────────────────────────

def test_record_outcome_returns_nothing():
    """A function that records a P&L and hands it back will be misused."""
    sample = S.LearningSample(
        shadow_id="X", decision_hash="abc", decided_as_of="2026-01-01",
        resolved_as_of="2026-04-01", horizon_days=90,
        realised_return=0.25, expected_return=0.05)
    assert S.record_outcome(sample) is None


def test_reliability_stays_uncalibrated_until_there_is_evidence():
    out = S.update_reliability("profitability_small")
    assert out["status"] == "UNCALIBRATED"
    assert out["proposed_weight"] == out["current_weight"]
    assert not out["applied"]
    assert "never as 1.0" in out["why"]


def test_a_big_win_cannot_move_the_weight_far():
    """30 perfect samples must still move a weight by at most one step."""
    samples = [{"shadow_id": "X",
                "signal_contributions": {"profitability_small": 1.0},
                "realised_return": 0.9, "benchmark_return": 0.0}
               for _ in range(60)]
    out = S.update_reliability("profitability_small", samples=samples,
                               prior=0.5)
    assert out["status"] == "CALIBRATED"
    assert out["hit_rate"] == 1.0
    assert out["proposed_weight"] <= 0.5 + S.MAX_STEP + 1e-9, (
        "a perfect quarter may not rewrite what the PM believes")
    assert not out["applied"], "the update is a proposal, never an auto-write"


def test_a_losing_streak_cannot_move_it_far_either():
    samples = [{"shadow_id": "X",
                "signal_contributions": {"profitability_small": 1.0},
                "realised_return": -0.5, "benchmark_return": 0.0}
               for _ in range(60)]
    out = S.update_reliability("profitability_small", samples=samples, prior=0.5)
    assert out["proposed_weight"] >= 0.5 - S.MAX_STEP - 1e-9


def test_the_update_never_leaves_the_unit_interval():
    for prior in (0.0, 0.02, 0.98, 1.0):
        for realised in (0.9, -0.9):
            samples = [{"shadow_id": "X",
                        "signal_contributions": {"profitability_small": 1.0},
                        "realised_return": realised, "benchmark_return": 0.0}
                       for _ in range(60)]
            out = S.update_reliability("profitability_small", samples=samples,
                                       prior=prior)
            assert 0.0 <= out["proposed_weight"] <= 1.0


def test_the_firewall_report_states_the_path():
    r = S.firewall_report()
    assert r["record_outcome_returns"] is None
    assert "P&L" in r["llm_may_not_read"]
    assert r["max_single_update_step"] == S.MAX_STEP


# ────────────────────── decisions freeze their evidence ─────────────────────

def test_a_decision_must_say_what_it_expected():
    d = _decision(expected_return={"AAA": 0.1})     # BBB missing
    with pytest.raises(S.ShadowError) as e:
        S.record_decision(d)
    assert "its outcome cannot grade it" in str(e.value)


def test_a_decision_with_no_weights_is_not_a_decision():
    with pytest.raises(S.ShadowError):
        S.record_decision(_decision(weights={}))


def test_leverage_is_refused():
    with pytest.raises(S.ShadowError) as e:
        S.record_decision(_decision(
            weights={"AAA": 0.8, "BBB": 0.8},
            expected_return={"AAA": 0.1, "BBB": 0.1}))
    assert "leverage is not modelled" in str(e.value)


def test_short_weights_are_refused():
    with pytest.raises(S.ShadowError) as e:
        S.record_decision(_decision(
            weights={"AAA": 1.2, "BBB": -0.2},
            expected_return={"AAA": 0.1, "BBB": 0.1}))
    assert "long only" in str(e.value)


def test_a_recorded_decision_round_trips_with_its_evidence():
    row = S.record_decision(_decision())
    back = S.decisions("CHALLENGER_X")
    assert len(back) == 1
    r = back[0]
    assert r["payload_hash"] == row["payload_hash"]
    assert r["signal_contributions"]["AAA"]["profitability_small"] == 0.6
    assert r["evidence_grades"]["profitability_small"] == "SUPPORTED"
    assert r["cost_assumption"]["round_trip"] == 0.004


def test_kill_condition_provenance_rounds_trips_and_is_optional():
    """NIGHT-13 §0: kill_conditions values may now be auto-adopted default
    texts, so a decision can say WHOSE words each one is. The field is
    optional — an old-style decision without it still records fine (its rows
    on disk keep their old hashes; only NEW payloads hash the new field)."""
    with_prov = _decision(
        kill_conditions={"AAA": "cash runway falls below 12 months"},
        kill_condition_provenance={"AAA": "auto_adopted_default"})
    S.record_decision(with_prov)
    back = S.decisions("CHALLENGER_X")[-1]
    assert back["kill_condition_provenance"] == {"AAA": "auto_adopted_default"}

    without = _decision(shadow_id="LEGACY_SHAPE")
    row = S.record_decision(without)
    assert row["kill_condition_provenance"] == {}

    # provenance is part of what a decision SAYS, so it moves the hash
    a = _decision(kill_conditions={"AAA": "k"})
    b = _decision(kill_conditions={"AAA": "k"},
                  kill_condition_provenance={"AAA": "murat_stated"})
    assert a.payload_hash() != b.payload_hash()


def test_the_hash_ignores_when_it_was_written_but_not_what_it_says():
    a = _decision(decided_at="2026-08-11T00:00:00+00:00")
    b = _decision(decided_at="2026-09-01T00:00:00+00:00")
    assert a.payload_hash() == b.payload_hash()
    c = _decision(weights={"AAA": 0.6, "BBB": 0.4},
                  expected_return={"AAA": 0.1, "BBB": 0.08})
    assert c.payload_hash() != a.payload_hash()


# ─────────────────────────── ledger integrity ───────────────────────────────

def test_a_corrupt_row_is_reported_not_swallowed(tmp_path):
    S.DECISIONS.parent.mkdir(parents=True, exist_ok=True)
    S.record_decision(_decision())
    with S.DECISIONS.open("a", encoding="utf-8") as fh:
        fh.write("{not json at all\n")
    S.record_decision(_decision(shadow_id="OTHER"))
    rows = S.decisions()
    assert len(rows) == 2
    assert S.MALFORMED_ROWS, (
        "a shorter but healthy-looking history is the BUILD-1.1 ledger bug")
    assert S.MALFORMED_ROWS[0]["line"] == 2


def test_forecast_error_is_realised_minus_expected():
    s = S.LearningSample(
        shadow_id="X", decision_hash="h", decided_as_of="a",
        resolved_as_of="b", horizon_days=90,
        realised_return=0.12, expected_return=0.05)
    assert s.forecast_error == pytest.approx(0.07)


# ── the registry's headline number must trace to a receipt ──────────────────
# The register shipped saying the false-discovery bar was +4.87 %/yr and that
# two challengers had cleared it. Neither survived contact with the measurement:
# 4.87 was the real-data equal-weight CONTROL genome, quoted a second time as
# the threshold its own challengers were judged against, and the bar measured
# over 60 null worlds is +6.90 %/yr, which nothing in the pool clears.
#
# The defect was not that someone computed a number wrong. It was that a
# headline number sat in a file with no link to the run that produced it, so
# nothing could notice when the run was superseded. These tests are that link.

MEASURED_BAR_PCT_YR = 6.90          # runs/ARENA1/null_bar.json, Aegis module
RETIRED_BAR_PCT_YR = 4.87           # the control genome it was confused with


def _registry() -> dict:
    import yaml
    return yaml.safe_load(S.REGISTRY_PATH.read_text(encoding="utf-8"))


def test_the_registry_bar_is_the_measured_one():
    reg = _registry()
    assert reg["false_discovery_bar_pct_yr"] == pytest.approx(
        MEASURED_BAR_PCT_YR), (
        "the shadow register's false-discovery bar no longer matches the "
        "measured null bar; a forward record labelled with a stale bar "
        "mislabels every book in it")
    assert reg["false_discovery_bar_receipt"], (
        "the bar must name the run that produced it — an unsourced headline "
        "number is exactly how 4.87 survived")


def test_the_retired_bar_is_recorded_not_deleted():
    """A number that was wrong is part of the record, not an embarrassment."""
    reg = _registry()
    assert reg["superseded_bar_pct_yr"] == pytest.approx(RETIRED_BAR_PCT_YR)
    assert "counted twice" in reg["superseded_bar_note"]


def test_no_book_claims_to_have_cleared_the_bar():
    reg = _registry()
    for book in reg["books"]:
        excess = book.get("arena_excess")
        if excess is None:
            continue
        assert book.get("cleared_false_discovery_bar") is False, (
            f"{book['shadow_id']} carries no explicit clearance flag; the "
            "previous register implied clearance in prose instead")
        assert excess < MEASURED_BAR_PCT_YR, (
            f"{book['shadow_id']} reports {excess} %/yr against a bar of "
            f"{MEASURED_BAR_PCT_YR} — if a genome genuinely clears the bar "
            "that is a finding and must be adjudicated, not asserted in YAML")
    assert reg["genomes_clearing_the_bar"] == 0


def test_nothing_in_the_register_is_seeded_without_an_attended_decision():
    """Seeding changes what the record MEANS, so it is not a code change."""
    reg = _registry()
    assert "inception_note" in reg
