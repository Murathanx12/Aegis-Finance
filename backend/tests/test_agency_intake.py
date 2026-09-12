"""Lane A1 — the IPS: its hash, its questionnaire, its refusals, its prose.

Spec: `docs/research_notes/2026-09-12/spec_agency_intake.md` §1 and test T1.

The test that matters most here is the dullest one: `ips_hash` must be stable
across key order. It is the single property that a future refactor can break
without anything else noticing — a hash call without `sort_keys=True` produces
a different identity for the same policy, and every book created under the old
one silently stops belonging to it.
"""

from __future__ import annotations

import json

import pytest

from backend.services import agency as A

ANSWERS = [3, 3, 2, 3, 2, 2, 1, 2]        # ability 2.75, willingness 1.75


def make_ips(**kw):
    base = dict(capital=50_000.0, horizon_months=36, personality="balanced",
                constraints=["NO_SECTOR:XLE"], liquidity_need=0.05,
                answers=list(ANSWERS), draft=False)
    base.update(kw)
    return A.intake(**base)


# ---------------------------------------------------------------- T1, the hash


def test_the_hash_is_stable_across_key_order():
    """Spec test T1. Build the same document twice with the two big sub-objects
    inserted in reversed key order; the hash is identical."""
    ips = make_ips()
    d1 = dict(ips.document)
    d2 = {k: (dict(reversed(list(v.items()))) if isinstance(v, dict) else v)
          for k, v in reversed(list(d1.items()))}
    assert list(d1) != list(d2), "the fixture must actually reorder the keys"
    assert A.ips_hash(d1) == A.ips_hash(d2) == ips.ips_hash


def test_the_hash_excludes_itself_and_the_timestamp():
    """An identical policy submitted a second later is the SAME policy."""
    a = make_ips(created_utc="2026-09-12T09:00:00+00:00")
    b = make_ips(created_utc="2026-09-12T09:00:01+00:00", ips_id=a.ips_id)
    assert a.ips_hash == b.ips_hash
    assert a.document["created_utc"] != b.document["created_utc"]


def test_a_changed_number_changes_the_hash():
    assert make_ips().ips_hash != make_ips(capital=50_001.0).ips_hash


def test_the_document_validates_against_its_own_schema():
    ips = make_ips()
    assert A.validate_document(ips.document)["validator"]
    # and the schema is a real gate, not decoration
    broken = dict(ips.document)
    broken["personality"] = "reckless"
    with pytest.raises(A.AgencyError):
        A.validate_document(broken)


def test_an_extra_field_is_refused_rather_than_carried():
    ips = make_ips()
    doc = dict(ips.document)
    doc["favourite_ticker"] = "NVDA"
    with pytest.raises(A.AgencyError, match="additional properties"):
        A.validate_document(doc)


def test_the_document_is_json_serialisable_as_written():
    json.dumps(make_ips().document)


# ------------------------------------------------------- the questionnaire


def test_the_composite_is_the_lower_of_ability_and_willingness():
    s = A.score_questionnaire(ANSWERS)
    assert s["ability_score"] == 2.75
    assert s["willingness_score"] == 1.75
    assert s["composite_score"] == 1.75
    assert s["bounded_by"] == "willingness"


def test_stated_willingness_cannot_raise_measured_ability():
    """The CFA convention, as a test: max willingness against low ability."""
    s = A.score_questionnaire([0, 0, 0, 0, 4, 4, 4, 4])
    assert s["composite_score"] == 0.0
    assert s["suggested_personality"] == "preservation"


def test_each_band_maps_to_its_personality():
    assert A.personality_for(0.0) == "preservation"
    assert A.personality_for(0.99) == "preservation"
    assert A.personality_for(1.0) == "balanced"
    assert A.personality_for(2.0) == "aggressive"
    assert A.personality_for(3.0) == "extreme_growth"
    assert A.personality_for(4.0) == "extreme_growth"


@pytest.mark.parametrize("bad", [None, [1, 2, 3], [0] * 9, [0, 1, 2, 3, 4, 5, 0, 0],
                                 [0, 1, 2, 3, 4, 0, 0, "2"]])
def test_a_malformed_questionnaire_is_refused(bad):
    with pytest.raises(A.AgencyError):
        A.score_questionnaire(bad)


def test_the_questionnaire_declares_its_sources():
    assert len(A.QUESTIONS) == A.N_QUESTIONS == 8
    assert all(q.source for q in A.QUESTIONS)
    joined = " ".join(q.source for q in A.QUESTIONS)
    assert "Grable" in joined and "Survey of Consumer Finances" in joined


def test_a_declared_personality_above_the_band_is_recorded_not_silent():
    ips = make_ips(personality="aggressive")
    assert ips.personality == "aggressive"
    assert any("above the questionnaire" in e for e in ips.echoes)


# ------------------------------------------------------------- §1.4 the table


def test_every_number_in_the_table_carries_a_source():
    for name, row in A.TABLE.items():
        for field_name in ("k", "max_single_name", "gross_cap", "stop_loss",
                           "drawdown_budget", "rebalance_frequency",
                           "cash_floor"):
            assert row.sources.get(field_name), f"{name}.{field_name} has no source"


def test_only_extreme_growth_may_lever_and_it_says_so():
    for name, row in A.TABLE.items():
        if name == "extreme_growth":
            assert row.gross_cap > 1.0
            assert row.extrapolated is True
            assert "gross" in row.note
        else:
            assert row.gross_cap == 1.0
            assert row.extrapolated is False


def test_the_rebalance_frequencies_match_the_lane_file_they_cite():
    """The three cited rows really do say monthly/monthly/weekly."""
    import yaml
    from pathlib import Path
    blob = yaml.safe_load(
        (Path(__file__).resolve().parents[1] / "data" / "paper_portfolios.yaml")
        .read_text(encoding="utf-8"))
    assert blob["conservative"]["rebalance_frequency"] == "monthly"
    assert blob["balanced"]["rebalance_frequency"] == "monthly"
    assert blob["aggressive"]["rebalance_frequency"] == "weekly"
    assert A.TABLE["preservation"].rebalance_frequency == "monthly"
    assert A.TABLE["balanced"].rebalance_frequency == "monthly"
    assert A.TABLE["aggressive"].rebalance_frequency == "weekly"


# ------------------------------------------------------- §1.5 the cash floor


def test_the_cash_floor_is_the_greater_of_the_two():
    assert A.cash_floor_for("balanced", 0.0) == 0.05        # personality minimum
    assert A.cash_floor_for("balanced", 0.30) == 0.30       # the declared need


def test_an_impossible_liquidity_need_is_refused_naming_both_inputs():
    with pytest.raises(A.AgencyError) as exc:
        A.cash_floor_for("aggressive", 0.80)
    msg = str(exc.value)
    assert "personality" in msg and "liquidity need" in msg
    assert "does not pick for you" in msg


def test_the_engine_never_downshifts_the_personality_by_itself():
    """The refusal path must not return a quietly different personality."""
    with pytest.raises(A.AgencyError):
        make_ips(personality="extreme_growth", liquidity_need=0.5)


# ------------------------------------------------------ §1.6 the constraints


def test_an_unknown_constraint_token_is_a_refusal():
    with pytest.raises(A.AgencyError, match="not in the vocabulary"):
        A.parse_constraints(["NO_CRYPTO"])


def test_an_esg_category_resolves_to_a_reviewed_list():
    out = A.parse_constraints(["ESG_EXCLUDE:gambling"])
    assert "DKNG" in out["excluded_tickers"]


def test_an_unmapped_esg_category_is_refused_not_ignored():
    with pytest.raises(A.AgencyError, match="reviewed exclusion list"):
        A.parse_constraints(["ESG_EXCLUDE:crypto"])


def test_tax_lot_deferred_echoes_rather_than_implying_a_check():
    out = A.parse_constraints(["TAX_LOT:DEFERRED"])
    assert out["echoes"] and "not implemented" in out["echoes"][0]


def test_the_constraints_reach_the_eligible_universe():
    ips = make_ips(constraints=["NO_SINGLE_NAME:TSLA", "NO_SECTOR:XLE"])
    eu = ips.document["eligible_universe"]
    assert eu["excluded_tickers"] == ["TSLA"]
    assert eu["excluded_sectors"] == ["XLE"]


# ------------------------------------------------------- §1.8 the amendment


def test_a_small_capital_change_is_an_amendment():
    first = make_ips()
    second = make_ips(capital=55_000.0, prior_ips=first.document)
    assert second.document["amends_ips_hash"] == first.ips_hash
    assert second.ips_id == first.ips_id


def test_a_large_capital_change_starts_a_new_ips():
    first = make_ips()
    second = make_ips(capital=200_000.0, prior_ips=first.document)
    assert second.document["amends_ips_hash"] is None
    assert second.ips_id != first.ips_id


def test_a_changed_personality_is_a_new_ips_not_a_tweak():
    first = make_ips()
    second = make_ips(personality="aggressive", prior_ips=first.document)
    assert second.document["amends_ips_hash"] is None


def test_a_changed_horizon_is_a_new_ips():
    first = make_ips()
    second = make_ips(horizon_months=12, prior_ips=first.document)
    assert second.document["amends_ips_hash"] is None


# ------------------------------------------------ A1: the prose and its check


def test_the_template_prose_carries_no_number_the_engine_did_not_compute():
    ips = make_ips()
    prose = A.template_prose(ips.document, ips.row, ips.numbers)
    assert A.unexplained_numbers(prose, ips.numbers) == []
    assert "$50,000" in prose


def test_every_digit_in_the_drafted_prose_appears_in_the_numeric_fields(monkeypatch):
    """A1's acceptance, as the spec words it, on the path that actually runs."""
    ips = make_ips(draft=False)

    class _Reply:
        model = "test-gguf"
        text = ("Your money is $50,000 over 36 months, 5% in cash, at most 15 "
                "names, none above 10%.")

    import backend.services.free_inference as fi
    monkeypatch.setattr(fi, "complete", lambda **kw: _Reply())
    prose, source, rejected = A.draft_prose(ips.document, ips.row, ips.numbers)
    assert source.startswith("local_gguf")
    assert rejected == ""
    assert A.unexplained_numbers(prose, ips.numbers) == []


def test_a_draft_that_invents_a_number_is_discarded_not_repaired(monkeypatch):
    ips = make_ips(draft=False)

    class _Reply:
        model = "test-gguf"
        text = "This book targets a 27.3% annual return."

    import backend.services.free_inference as fi
    monkeypatch.setattr(fi, "complete", lambda **kw: _Reply())
    prose, source, rejected = A.draft_prose(ips.document, ips.row, ips.numbers)
    assert source == "template"
    assert "DISCARDED" in rejected
    assert "27.3" not in prose


def test_no_model_means_the_template_and_the_reason(monkeypatch):
    ips = make_ips(draft=False)

    def _boom(**kw):
        raise RuntimeError("llama-server is not listening")

    import backend.services.free_inference as fi
    monkeypatch.setattr(fi, "complete", _boom)
    prose, source, rejected = A.draft_prose(ips.document, ips.row, ips.numbers)
    assert source == "template"
    assert "not listening" in rejected
    assert prose


# ------------------------------------------------------------- the payload


def test_the_payload_always_carries_the_limits_sentence():
    payload = make_ips().as_payload()
    assert payload["limits"] == A.LIMITS_SENTENCE
    assert "not investment advice" in payload["limits"]
    assert "Investment Advisers Act" in payload["limits"]


def test_the_payload_names_the_validator_that_ran():
    payload = make_ips().as_payload()
    assert payload["validated_by"] in ("hand",) or \
        payload["validated_by"].startswith("jsonschema")


def test_the_worked_example_from_the_spec():
    """§2.4: $50,000 balanced at a 5% cash floor is -$4,750."""
    ips = make_ips()
    assert ips.numbers["worst_case_usd"] == pytest.approx(-4750.0, rel=1e-9)
    assert ips.numbers["cash_floor_pct"] == 0.05
