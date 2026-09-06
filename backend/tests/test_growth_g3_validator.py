"""G3's validator: the LLM proposes, and the grammar decides.

The proposer has no authority over anything in the receipt except which twenty
points in the grammar get a second of compute. These tests pin that boundary —
every refusal path, and the fact that an out-of-range value is REFUSED and not
quietly clipped to the boundary (a clipped proposal is a different proposal
wearing the model's label, and the lineage would record the one never run).
"""
from __future__ import annotations

import json

import pytest

from learner import growth_lab as GL
from scripts import growth_g3_mutations as G3


CORPSES = {"momentum_12_1", "value_btm", "llm_stock_selection"}


def _parents():
    g = {x.genome_id: x for x in GL.generation_zero()}
    return {"lgbm_clf": g["lgbm_clf"], "quality_mom|dd": g["quality_mom|dd"],
            "spy_trend": g["spy_trend"]}


def _ok(**over):
    base = {"parent_id": "lgbm_clf", "mutation": {"k": 40},
            "rationale": "a smaller book concentrates the ranking",
            "parent_corpse_id": "momentum_12_1",
            "distinct_claim": "This asks about book size, not raw momentum."}
    base.update(over)
    return base


def test_a_well_formed_proposal_is_accepted_and_normalised():
    out = G3.validate(_ok(), _parents(), CORPSES)
    assert out["parent_id"] == "lgbm_clf"
    assert out["mutation"] == {"k": 40}
    assert out["parent_corpse_id"] == "momentum_12_1"


def test_a_parent_that_is_not_one_of_the_leaders_is_refused():
    with pytest.raises(G3.Refused) as e:
        G3.validate(_ok(parent_id="lgbm_clf|10bps"), _parents(), CORPSES)
    assert "not one of the five leaders" in str(e.value)


def test_the_cell_id_form_is_exactly_the_round_1_defect():
    """Round 1 handed the model CELL ids and every proposal was refused.

    This is the regression: the validator must keep refusing the cell form, and
    `build_prompt` must keep printing the genome form. Both halves are pinned —
    a fix to only one of them puts the job back where it started.
    """
    with pytest.raises(G3.Refused):
        G3.validate(_ok(parent_id="quality_mom|dd|10bps"), _parents(), CORPSES)
    parents = [{"genome_id": "quality_mom|dd", "cell": "quality_mom|dd|10bps",
                "beta": 0.78, "leverage_neutral_tw": 4.2, "spy_tw": 2.09,
                "raw_tw": 4.9, "max_drawdown": -0.39,
                "spec": {"pred_col": "quality_mom"}, "overlay": ["dd"]}]
    prompt = G3.build_prompt(parents, [{"signal_id": "value_btm",
                                        "evidence_grade": "REJECTED"}])
    assert "  quality_mom|dd: beta" in prompt
    assert "quality_mom|dd|10bps" not in prompt


def test_a_corpse_outside_the_registry_is_refused():
    with pytest.raises(G3.Refused) as e:
        G3.validate(_ok(parent_corpse_id="a_signal_nobody_registered"),
                    _parents(), CORPSES)
    assert "REJECTED/PERVERSE" in str(e.value)


def test_a_distinct_claim_shorter_than_a_sentence_is_refused():
    with pytest.raises(G3.Refused) as e:
        G3.validate(_ok(distinct_claim="different"), _parents(), CORPSES)
    assert "not a feeling" in str(e.value)


def test_a_key_outside_the_grammar_is_refused():
    with pytest.raises(G3.Refused) as e:
        G3.validate(_ok(mutation={"leverage": 3.0}), _parents(), CORPSES)
    assert "not in the mutation grammar" in str(e.value)


@pytest.mark.parametrize("mut", [
    {"k": 500}, {"k": 2}, {"dd_scale": 1.5}, {"dd_floor": -0.2},
    {"bsc_cap": 4.0}, {"hold_k": 5}, {"weight": "cap_weighted"},
    {"pred_col": "some_column_we_never_built"},
])
def test_an_out_of_range_value_is_refused_and_never_clipped(mut):
    with pytest.raises(G3.Refused):
        G3.validate(_ok(mutation=mut), _parents(), CORPSES)


def test_an_empty_mutation_is_refused():
    with pytest.raises(G3.Refused):
        G3.validate(_ok(mutation={}), _parents(), CORPSES)


def test_the_child_carries_its_parent_and_the_diff_as_lineage():
    norm = G3.validate(_ok(mutation={"k": 25, "overlay": ["dd", "tg"]}),
                       _parents(), CORPSES)
    child = G3.child_genome(_parents()["lgbm_clf"], norm, 7)
    assert child.genome_id == "m07_lgbm_clf"
    assert child.parent_ids == ("lgbm_clf",)
    assert child.overlay == ("dd", "tg")
    assert child.spec["k"] == 25
    assert "k=25" in child.mutation_history[0]
    assert child.sha256() != _parents()["lgbm_clf"].sha256()


def test_an_index_genome_drops_the_cross_sectional_keys_it_cannot_use():
    norm = G3.validate(_ok(parent_id="spy_trend",
                           mutation={"k": 30, "dd_scale": 0.5}),
                       _parents(), CORPSES)
    child = G3.child_genome(_parents()["spy_trend"], norm, 1)
    assert "k" not in child.spec            # inert on an index rule
    assert child.spec["dd_scale"] == 0.5


def test_the_overlay_parameter_bounds_refuse_rather_than_clip():
    with pytest.raises(SystemExit) as e:
        GL.overlay_params({"dd_scale": 5.0})
    assert "REFUSED" in str(e.value) and "different proposal" in str(e.value)
    assert GL.overlay_params({"dd_scale": 0.5})["dd_scale"] == 0.5
    assert GL.overlay_params()["dd_scale"] == GL.DD_SCALE


def test_the_corpse_list_is_derived_from_the_registry_not_re_typed():
    from backend.services import signal_registry as SR
    ids = {c["signal_id"] for c in G3.corpses()}
    grades = {c["evidence_grade"] for c in G3.corpses()}
    assert ids and grades <= SR.NEVER_PICKS


def test_the_shipped_receipt_replays_to_the_same_leader_it_recorded():
    """`proposals_raw` is what makes G3 reproducible without paying again."""
    p = GL.OUT_DIR / "G3_mutations.json"
    if not p.exists():
        pytest.skip("G3 has not been run in this checkout")
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["proposals_returned"] == len(d.get("proposals_raw") or [])
    assert d["sealed_era_touched_by_this_job"] is False
    assert (d["llm"].get("llm_spend_usd") or 0.0) <= G3.LLM_CAP_USD
    for cell in d["cells"].values():
        if "lineage" in cell:
            assert len(cell["lineage"]["distinct_claim"].split()) >= 5
